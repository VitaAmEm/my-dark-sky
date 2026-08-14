import os
import time

import requests

GEO_BASE_URL = "https://api.openweathermap.org/geo/1.0"
DATA_BASE_URL = "https://api.openweathermap.org/data/2.5"
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("WEATHER_REQUEST_TIMEOUT", 8))

MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 0.5

COMPASS_DIRECTIONS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


class WeatherAPIError(Exception):
    pass


def _api_key():
    key = os.environ.get("OPENWEATHER_API_KEY")
    if not key:
        raise WeatherAPIError(
            "OPENWEATHER_API_KEY is not set. Add it to your .env file or "
            "your hosting provider's environment variables."
        )
    return key


def _get(url, params):
    params = {**params, "appid": _api_key()}

    for attempt in range(MAX_RETRIES + 1):
        is_last_attempt = attempt == MAX_RETRIES
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as err:
            if is_last_attempt:
                raise WeatherAPIError(
                    f"Could not reach OpenWeatherMap after {attempt + 1} attempt(s): {err}"
                ) from err
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
            continue

        if response.status_code == 401:
            raise WeatherAPIError("OpenWeatherMap rejected the API key (401 Unauthorized).")
        if response.status_code == 429:
            raise WeatherAPIError("OpenWeatherMap rate limit exceeded (429 Too Many Requests).")

        if response.status_code >= 500:
            if is_last_attempt:
                raise WeatherAPIError(
                    f"OpenWeatherMap kept failing after {attempt + 1} attempts "
                    f"(last status: HTTP {response.status_code})."
                )
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
            continue

        if not response.ok:
            raise WeatherAPIError(f"OpenWeatherMap returned HTTP {response.status_code}: {response.text[:200]}")

        try:
            return response.json()
        except ValueError as err:
            raise WeatherAPIError("OpenWeatherMap returned invalid JSON.") from err

    raise WeatherAPIError("OpenWeatherMap request ended without a response.")


def search_locations(query, limit=5):
    if not query or not query.strip():
        return []
    raw_results = _get(f"{GEO_BASE_URL}/direct", {"q": query.strip(), "limit": limit}) or []
    return [_format_place(place) for place in raw_results]


def reverse_geocode(lat, lon):
    raw_results = _get(f"{GEO_BASE_URL}/reverse", {"lat": lat, "lon": lon, "limit": 1}) or []
    if not raw_results:
        return {"name": "Unknown location", "lat": lat, "lon": lon, "country": "", "state": ""}
    return _format_place(raw_results[0])


def _format_place(place):
    return {
        "name": place.get("name", "Unknown"),
        "state": place.get("state", ""),
        "country": place.get("country", ""),
        "lat": place.get("lat"),
        "lon": place.get("lon"),
    }


def get_current_weather(lat, lon, units="imperial"):
    return _get(f"{DATA_BASE_URL}/weather", {"lat": lat, "lon": lon, "units": units})


def get_forecast(lat, lon, units="imperial"):
    return _get(f"{DATA_BASE_URL}/forecast", {"lat": lat, "lon": lon, "units": units})


def degrees_to_compass(degrees):
    if degrees is None:
        return None
    index = round(float(degrees) / 22.5) % 16
    return COMPASS_DIRECTIONS[index]