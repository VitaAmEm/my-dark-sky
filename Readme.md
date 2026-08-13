## Task

Dark Sky shut down after Apple acquired it. The challenge: rebuild its
core experience - current conditions, a multi-day forecast, location
search, and a look back at past weather - on a free weather API, hosted
in the cloud and looking good.

The real difficulty is what free APIs don't give you: no provider bundles
current + forecast + historical data for free (historical is almost
always paid), and the spec's 5-minute cache means the app needs real
persistent state, not just a stateless proxy.

## Description

**Weather data**: [OpenWeatherMap](https://openweathermap.org/current)'s
free tier - current conditions, a 5-day/3-hour forecast, and geocoding
for search and "use my location." Failed requests retry automatically on
transient errors (network issues, 5xx), but fail fast on 401/429 since
retrying can't fix those.

**Historical data**: instead of faking data the free tier doesn't
provide, the app logs a real snapshot whenever conditions meaningfully
change for a location you've checked. The "Time Machine" panel shows that
recorded history honestly - real data, starting from whenever you first
looked a place up, not a fabricated archive.

**Cache**: a SQLite table stores each location's last fetched result for
5 minutes, satisfying the spec's caching requirement and protecting the
API quota.

**UI**: Flask + Jinja, Tailwind via CDN, vanilla JS - no framework needed
for a single-page dashboard. Visual direction: "an instrument reading the
sky" - navy/slate palette, serif italic for plain-language observations,
monospace for all numbers, and a gradient precipitation sparkline scaled
honestly to a 3-hour-step forecast. Search is a real keyboard-navigable
combobox (arrow keys, Enter, Escape, matching ARIA attributes).

## Installation

```bash
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then add your OpenWeatherMap API key (free at
# https://home.openweathermap.org/users/sign_up)
```

## Usage

```bash
python app.py
```

Open `http://localhost:8080`. Allow location access or search for a
place - arrow keys and Enter work in the results list. Toggle °F/°C and
choose km/h, m/s, or knots for wind speed in the top-right controls.

The entry point also accepts exactly two positional arguments and prints
them, which is useful for command-line checks:

```bash
python app.py Firstname Lastname
```

```bash
curl "http://localhost:8080/api/weather?lat=42.36&lon=-71.06&units=imperial&wind_unit=kmh&name=Boston"
```

## Live Deployment

- URL: https://my-dark-sky-9tmi.onrender.com
- Submission file: [my_dark_sky_url.txt](my_dark_sky_url.txt)

## Deploy to Render

1. Push this repo to GitHub.
2. Create a new Web Service in Render and connect the repository.
3. Render will read the existing [render.yaml](render.yaml) file.
4. Add this environment variable in Render:
   - `OPENWEATHER_API_KEY`

5. Start the service and open the provided URL.

## Environment Variables

Create a `.env` file locally with:

```env
OPENWEATHER_API_KEY=your_api_key_here
```

## Requirement Checklist

- Python + Flask app: yes
- Cloud hosted: yes (Render)
- Location by search: yes
- Location by current geolocation: yes
- Today's weather: yes
- Future forecast: yes
- Forecast on selected date: yes
- Time machine/history view: yes
- 5-minute cache: yes (SQLite)
