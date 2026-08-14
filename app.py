import argparse
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

import cache
import weather_client
from weather_client import WeatherAPIError

load_dotenv()

app = Flask(__name__)
HISTORY_TEMP_CHANGE_THRESHOLD = 1.0
SUPPORTED_TEMPERATURE_UNITS = ("imperial", "metric")
SUPPORTED_WIND_UNITS = ("kmh", "ms", "mph", "kn")


def _parse_command_line_args():
    parser = argparse.ArgumentParser(description="Run the weather dashboard or print a name.")
    parser.add_argument("firstname", nargs="?")
    parser.add_argument("lastname", nargs="?")
    args = parser.parse_args()
    if (args.firstname is None) != (args.lastname is None):
        parser.error("provide both a firstname and a lastname")
    return args.firstname, args.lastname


def _run_from_command_line():
    firstname, lastname = _parse_command_line_args()
    if firstname is not None:
        print(f"{firstname} {lastname}")
        return

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")


def _coordinates_from_request():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    if lat is None or lon is None:
        return None, None, ("lat and lon query parameters are required", 400)
    try:
        latitude = float(lat)
        longitude = float(lon)
    except ValueError:
        return None, None, ("lat and lon must be valid numbers", 400)
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None, None, ("lat or lon is outside the valid range", 400)
    return lat, lon, None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "")
    try:
        results = weather_client.search_locations(query)
    except WeatherAPIError as err:
        return jsonify({"error": str(err)}), 502
    return jsonify(results)


@app.route("/api/reverse")
def api_reverse():
    lat, lon, error = _coordinates_from_request()
    if error:
        return jsonify({"error": error[0]}), error[1]
    try:
        place = weather_client.reverse_geocode(lat, lon)
    except WeatherAPIError as err:
        return jsonify({"error": str(err)}), 502
    return jsonify(place)


@app.route("/api/weather")
def api_weather():
    lat, lon, error = _coordinates_from_request()
    units = request.args.get("units", "imperial")
    wind_unit = request.args.get("wind_unit", "kmh")
    place_name = request.args.get("name", "Selected location")

    if error:
        return jsonify({"error": error[0]}), error[1]
    if units not in SUPPORTED_TEMPERATURE_UNITS:
        return jsonify({"error": "units must be 'imperial' or 'metric'"}), 400
    if wind_unit not in SUPPORTED_WIND_UNITS:
        return jsonify({"error": "wind_unit must be 'kmh', 'ms', 'mph', or 'kn'"}), 400

    effective_units = _effective_temperature_units(units, wind_unit)
    cache_units = f"{effective_units}:{wind_unit}"
    cached = cache.get_cached_weather(lat, lon, cache_units)
    if cached is not None:
        return jsonify({**cached, "from_cache": True})

    try:
        current_raw = weather_client.get_current_weather(lat, lon, effective_units)
        forecast_raw = weather_client.get_forecast(lat, lon, effective_units)
    except WeatherAPIError as err:
        return jsonify({"error": str(err)}), 502

    payload = _build_weather_payload(
        current_raw, forecast_raw, place_name, effective_units, wind_unit
    )
    cache.store_weather_in_cache(lat, lon, cache_units, payload)
    _maybe_record_history(lat, lon, effective_units, place_name, current_raw)

    return jsonify({**payload, "from_cache": False})


@app.route("/api/history")
def api_history():
    lat, lon, error = _coordinates_from_request()
    units = request.args.get("units", "imperial")
    if error:
        return jsonify({"error": error[0]}), error[1]
    if units not in SUPPORTED_TEMPERATURE_UNITS:
        return jsonify({"error": "units must be 'imperial' or 'metric'"}), 400
    return jsonify(cache.get_history(lat, lon, units))


@app.route("/api/date-weather")
def api_date_weather():
    lat, lon, error = _coordinates_from_request()
    units = request.args.get("units", "imperial")
    date_str = request.args.get("date")

    if error:
        return jsonify({"error": error[0]}), error[1]
    if date_str is None:
        return jsonify({"error": "date query parameter is required"}), 400
    if units not in SUPPORTED_TEMPERATURE_UNITS:
        return jsonify({"error": "units must be 'imperial' or 'metric'"}), 400

    try:
        target_date = datetime.fromisoformat(date_str).date()
    except ValueError:
        return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400

    history_for_date = [
        row
        for row in cache.get_history(lat, lon, units, limit=500)
        if row.get("recorded_at", "")[:10] == date_str
    ]

    forecast_for_date = None
    try:
        forecast_raw = weather_client.get_forecast(lat, lon, units) or {}
        daily = _bucket_forecast_by_day(forecast_raw.get("list", []))
        forecast_for_date = next((day for day in daily if day.get("date") == date_str), None)
    except WeatherAPIError:
        forecast_for_date = None

    return jsonify(
        {
            "date": target_date.isoformat(),
            "forecast": forecast_for_date,
            "history": history_for_date,
            "has_data": bool(forecast_for_date or history_for_date),
        }
    )


def _maybe_record_history(lat, lon, units, place_name, current_raw):
    condition = current_raw["weather"][0]["main"] if current_raw.get("weather") else "Unknown"
    icon = current_raw["weather"][0]["icon"] if current_raw.get("weather") else ""
    temperature = current_raw["main"]["temp"]
    feels_like = current_raw["main"]["feels_like"]

    latest = cache.get_latest_snapshot(lat, lon, units)
    condition_changed = latest is None or latest["condition"] != condition
    temp_moved = latest is None or abs(latest["temperature"] - temperature) >= HISTORY_TEMP_CHANGE_THRESHOLD

    if condition_changed or temp_moved:
        cache.record_history_snapshot(
            lat=lat,
            lon=lon,
            units=units,
            place_name=place_name,
            temperature=temperature,
            feels_like=feels_like,
            condition=condition,
            icon=icon,
        )


def _build_weather_payload(current_raw, forecast_raw, place_name, units, wind_unit):
    wind_deg = current_raw.get("wind", {}).get("deg")
    raw_wind_speed = current_raw.get("wind", {}).get("speed", 0)
    current = {
        "temperature": round(current_raw["main"]["temp"]),
        "feels_like": round(current_raw["main"]["feels_like"]),
        "low": round(current_raw["main"].get("temp_min", current_raw["main"]["temp"])),
        "high": round(current_raw["main"].get("temp_max", current_raw["main"]["temp"])),
        "humidity": current_raw["main"]["humidity"],
        "pressure": _convert_pressure(current_raw["main"]["pressure"], units),
        "wind_speed": _convert_wind_speed(raw_wind_speed, units, wind_unit),
        "wind_direction": weather_client.degrees_to_compass(wind_deg),
        "visibility": _convert_visibility(current_raw.get("visibility"), units),
        "condition": current_raw["weather"][0]["main"] if current_raw.get("weather") else "Unknown",
        "description": current_raw["weather"][0]["description"] if current_raw.get("weather") else "",
        "icon": current_raw["weather"][0]["icon"] if current_raw.get("weather") else "",
    }

    hourly = [_format_forecast_block(block) for block in forecast_raw.get("list", [])[:8]]
    daily = _bucket_forecast_by_day(forecast_raw.get("list", []))

    return {
        "place_name": place_name,
        "units": units,
        "wind_unit": wind_unit,
        "pressure_unit": "inHg" if units == "imperial" else "hPa",
        "visibility_unit": "mi" if units == "imperial" else "km",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "current": current,
        "hourly": hourly,
        "daily": daily,
    }


def _format_forecast_block(block):
    return {
        "time": block["dt_txt"],
        "temperature": round(block["main"]["temp"]),
        "condition": block["weather"][0]["main"] if block.get("weather") else "Unknown",
        "icon": block["weather"][0]["icon"] if block.get("weather") else "",
        "precipitation_probability": round(block.get("pop", 0) * 100),
    }


def _convert_wind_speed(speed, temperature_units, wind_unit):
    source_to_kmh = 1.609344 if temperature_units == "imperial" else 3.6
    target_from_kmh = {"kmh": 1, "ms": 1 / 3.6, "mph": 1 / 1.609344, "kn": 1 / 1.852}
    return round(float(speed) * source_to_kmh * target_from_kmh[wind_unit], 1)


def _effective_temperature_units(temperature_units, wind_unit):
    if wind_unit == "mph":
        return "imperial"
    if wind_unit in ("kmh", "ms"):
        return "metric"
    return temperature_units


def _convert_pressure(pressure_hpa, temperature_units):
    if temperature_units == "imperial":
        return round(float(pressure_hpa) * 0.0295299833, 2)
    return round(float(pressure_hpa), 1)


def _convert_visibility(visibility_meters, temperature_units):
    if visibility_meters is None:
        return None
    if temperature_units == "imperial":
        return round(float(visibility_meters) / 1609.344, 1)
    return round(float(visibility_meters) / 1000, 1)


def _bucket_forecast_by_day(blocks):
    days = defaultdict(list)
    for block in blocks:
        date_str = block["dt_txt"].split(" ")[0]
        days[date_str].append(block)

    daily_summary = []
    for date_str, day_blocks in days.items():
        temps = [b["main"]["temp"] for b in day_blocks]
        pop_values = [b.get("pop", 0) for b in day_blocks]

        conditions = [b["weather"][0]["main"] for b in day_blocks if b.get("weather")]
        most_common_condition = Counter(conditions).most_common(1)[0][0] if conditions else "Unknown"
        representative_block = next(
            (b for b in day_blocks if b.get("weather") and b["weather"][0]["main"] == most_common_condition),
            day_blocks[0],
        )
        icon = representative_block["weather"][0]["icon"] if representative_block.get("weather") else ""

        daily_summary.append(
            {
                "date": date_str,
                "low": round(min(temps)),
                "high": round(max(temps)),
                "condition": most_common_condition,
                "icon": icon,
                "avg_precip_chance": round(sum(pop_values) / len(pop_values) * 100) if pop_values else 0,
            }
        )
    return daily_summary


if __name__ == "__main__":
    _run_from_command_line()