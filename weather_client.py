"""
weather_client.py

A small wrapper around the OpenWeatherMap "classic" free-tier endpoints:
  - /geo/1.0/direct    -> turn a typed search string into lat/lon candidates
  - /geo/1.0/reverse   -> turn lat/lon into a human-readable place name
  - /data/2.5/weather  -> current conditions for a lat/lon
  - /data/2.5/forecast -> 5-day / 3-hour forecast for a lat/lon

Kept deliberately separate from app.py so the rest of the app never talks
to `requests` or knows OpenWeatherMap's URL shapes directly - if we ever
swap providers, this is the only file that needs to change.
"""

import os
import time

import requests

GEO_BASE_URL = "https://api.openweathermap.org/geo/1.0"
DATA_BASE_URL = "https://api.openweathermap.org/data/2.5"
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("WEATHER_REQUEST_TIMEOUT", 8))

# How many extra attempts to make after the first one fails, and how long
# to wait (in seconds) before each retry - only for failures that are
# plausibly transient (network errors, 5xx). 401/429 are never retried,
# since retrying won't fix a bad key or a quota that's already exhausted.
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 0.5

COMPASS_DIRECTIONS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


class WeatherAPIError(Exception):
    """Raised when OpenWeatherMap can't give us a usable answer."""


def _api_key():
    key = os.environ.get("OPENWEATHER_API_KEY")
    if not key:
        raise WeatherAPIError(
            "OPENWEATHER_API_KEY is not set. Add it to your .env file or "
            "your hosting provider's environment variables."
        )
    return key


def _get(url, params):
    """
    Make a GET request, retrying transient failures (network errors, 5xx)
    up to MAX_RETRIES extra times with a short backoff between attempts.
    401/429 are raised immediately instead - retrying can't fix a bad key
    or an already-exhausted quota, so there's no point waiting first.

    Every branch below either returns a result or raises - the loop never
    falls through, so there's deliberately no "raise after the loop"
    fallback: that would be unreachable dead code.
    """
    params = {**params, "appid": _api_key()}
    is_last_attempt = lambda attempt: attempt == MAX_RETRIES

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as err:
            if is_last_attempt(attempt):
                raise WeatherAPIError(
                    f"Could not reach OpenWeatherMap after {attempt + 1} attempt(s): {err}"
                ) from err
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
            continue

        # Not worth retrying: the key is wrong, or we're out of quota.
        if response.status_code == 401:
            raise WeatherAPIError("OpenWeatherMap rejected the API key (401 Unauthorized).")
        if response.status_code == 429:
            raise WeatherAPIError("OpenWeatherMap rate limit exceeded (429 Too Many Requests).")

        # Worth retrying: OpenWeatherMap's own server had a problem, not us.
        if response.status_code >= 500:
            if is_last_attempt(attempt):
                raise WeatherAPIError(
                    f"OpenWeatherMap kept failing after {attempt + 1} attempts "
                    f"(last status: HTTP {response.status_code})."
                )
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
            continue

        if not response.ok:
            raise WeatherAPIError(f"OpenWeatherMap returned HTTP {response.status_code}: {response.text[:200]}")

        return response.json()


def search_locations(query, limit=5):
    """Turn a typed search string ('Boston', 'Riga, Latvia', ...) into candidate places."""
    if not query or not query.strip():
        return []
    raw_results = _get(f"{GEO_BASE_URL}/direct", {"q": query.strip(), "limit": limit}) or []
    return [_format_place(place) for place in raw_results]


def reverse_geocode(lat, lon):
    """Turn a lat/lon (e.g. from the browser's geolocation API) into a place name."""
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
    """Returns the raw 5-day/3-hour forecast payload (40 x 3-hour blocks)."""
    return _get(f"{DATA_BASE_URL}/forecast", {"lat": lat, "lon": lon, "units": units})


def degrees_to_compass(degrees):
    """
    Convert a wind direction in degrees (0-360, as OpenWeatherMap reports
    it in wind.deg) into a 16-point compass label like 'NNW'. Returns None
    if degrees is missing, since calm/variable wind often omits it.
    """
    if degrees is None:
        return None
    index = round(float(degrees) / 22.5) % 16
    return COMPASS_DIRECTIONS[index]