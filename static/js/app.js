const state = {
  units: "imperial",
  windUnit: "mph",
  location: null,
  searchTimer: null,
  activeResultIndex: -1,
  lastSearchResults: [],
};

const el = (id) => document.getElementById(id);

const ICONS = {
  Clear: `<circle cx="12" cy="12" r="5"/><g stroke-linecap="round"><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.2" y1="4.2" x2="5.6" y2="5.6"/><line x1="18.4" y1="18.4" x2="19.8" y2="19.8"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.2" y1="19.8" x2="5.6" y2="18.4"/><line x1="18.4" y1="5.6" x2="19.8" y2="4.2"/></g>`,
  Clouds: `<path d="M17 18a4 4 0 000-8 5.5 5.5 0 00-10.7 1.7A3.5 3.5 0 007.5 18h9.5z"/>`,
  Rain: `<path d="M17 15a4 4 0 000-8 5.5 5.5 0 00-10.7 1.7A3.5 3.5 0 007.5 15h9.5z"/><g stroke-linecap="round"><line x1="9" y1="18" x2="8" y2="21"/><line x1="13" y1="18" x2="12" y2="21"/><line x1="17" y1="18" x2="16" y2="21"/></g>`,
  Drizzle: `<path d="M17 14a4 4 0 000-8 5.5 5.5 0 00-10.7 1.7A3.5 3.5 0 007.5 14h9.5z"/><line x1="10" y1="17" x2="9.5" y2="19" stroke-linecap="round"/><line x1="14" y1="17" x2="13.5" y2="19" stroke-linecap="round"/>`,
  Thunderstorm: `<path d="M17 13a4 4 0 000-8 5.5 5.5 0 00-10.7 1.7A3.5 3.5 0 007.5 13h9.5z"/><path d="M12 14l-2 4h3l-2 4" stroke-linejoin="round" stroke-linecap="round"/>`,
  Snow: `<path d="M17 13a4 4 0 000-8 5.5 5.5 0 00-10.7 1.7A3.5 3.5 0 007.5 13h9.5z"/><g stroke-linecap="round"><line x1="8" y1="17" x2="8" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/><line x1="16" y1="17" x2="16" y2="21"/></g>`,
  Mist: `<g stroke-linecap="round"><line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="13" x2="20" y2="13"/><line x1="4" y1="17" x2="20" y2="17"/></g>`,
};
ICONS.Haze = ICONS.Mist;
ICONS.Fog = ICONS.Mist;
ICONS.Smoke = ICONS.Mist;

function iconSvg(condition, extraClass = "w-6 h-6") {
  const paths = ICONS[condition] || ICONS.Clouds;
  return `<svg class="${extraClass} text-aurora" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">${paths}</svg>`;
}

function unitSuffix() {
  return state.units === "imperial" ? "°F" : "°C";
}
function speedSuffix() {
  return { kmh: "km/h", ms: "m/s", mph: "mph", kn: "kn" }[state.windUnit];
}
function pressureSuffix() {
  return state.units === "imperial" ? "inHg" : "hPa";
}
function visibilitySuffix() {
  return state.units === "imperial" ? "mi" : "km";
}

function uvRisk(index) {
  if (index == null) return { label: "Unavailable", explanation: "UV data is not available for this location." };
  if (index < 3) return { label: "Low risk", explanation: "Minimal risk for most people." };
  if (index < 6) return { label: "Moderate risk", explanation: "Unprotected skin can burn; protection is recommended." };
  if (index < 8) return { label: "High risk", explanation: "Unprotected skin can burn quickly; protection is important." };
  if (index < 11) return { label: "Very high risk", explanation: "Skin and eye damage can happen quickly; avoid midday sun and use strong protection." };
  return { label: "Extreme risk", explanation: "Unprotected skin can burn rapidly; limit exposure to reduce long-term skin-cancer risk." };
}

el("unitsToggle").addEventListener("click", () => {
  state.units = state.units === "imperial" ? "metric" : "imperial";
  if (state.windUnit !== "kn") {
    state.windUnit = state.units === "imperial" ? "mph" : "kmh";
    el("windUnitSelect").value = state.windUnit;
  }
  el("unitsToggle").textContent = state.units === "imperial" ? "°F" : "°C";
  if (state.location) loadWeather(state.location);
});

el("windUnitSelect").addEventListener("change", (event) => {
  state.windUnit = event.target.value;
  if (state.windUnit === "mph") state.units = "imperial";
  if (["kmh", "ms"].includes(state.windUnit)) state.units = "metric";
  el("unitsToggle").textContent = state.units === "imperial" ? "°F" : "°C";
  if (state.location) loadWeather(state.location);
});

el("dateLookupBtn").addEventListener("click", () => {
  const dateValue = el("datePicker").value;
  if (!dateValue) {
    el("dateResult").textContent = "Choose a date first.";
    return;
  }
  if (!state.location) {
    el("dateResult").textContent = "Load a location first, then pick a date.";
    return;
  }
  loadDateWeather(dateValue);
});

el("searchInput").addEventListener("input", (event) => {
  clearTimeout(state.searchTimer);
  const query = event.target.value.trim();
  if (query.length < 2) {
    closeSearchResults();
    return;
  }
  state.searchTimer = setTimeout(() => runSearch(query), 300);
});

document.addEventListener("click", (event) => {
  if (!el("searchResults").contains(event.target) && event.target !== el("searchInput")) {
    closeSearchResults();
  }
});

async function runSearch(query) {
  try {
    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    const results = await response.json();
    renderSearchResults(results);
  } catch (err) {
    console.error("Search failed:", err);
  }
}

function closeSearchResults() {
  const list = el("searchResults");
  list.classList.add("hidden");
  list.innerHTML = "";
  state.activeResultIndex = -1;
  state.lastSearchResults = [];
  el("searchInput").setAttribute("aria-expanded", "false");
  el("searchInput").removeAttribute("aria-activedescendant");
}

function renderSearchResults(results) {
  const list = el("searchResults");
  state.lastSearchResults = results;
  state.activeResultIndex = -1;

  if (!results.length) {
    closeSearchResults();
    return;
  }

  list.innerHTML = results
    .map(
      (place, index) => `
      <li id="search-result-${index}" data-index="${index}" role="option" aria-selected="false"
        class="px-4 py-2.5 text-sm cursor-pointer hover:bg-panel2 transition-colors">
        ${place.name}${place.state ? ", " + place.state : ""}${place.country ? ", " + place.country : ""}
      </li>`
    )
    .join("");
  list.classList.remove("hidden");
  el("searchInput").setAttribute("aria-expanded", "true");

  [...list.children].forEach((li, index) => {
    li.addEventListener("click", () => selectSearchResult(index));
    li.addEventListener("mouseenter", () => setActiveResult(index));
  });
}

function setActiveResult(index) {
  const items = [...el("searchResults").children];
  if (!items.length) return;

  state.activeResultIndex = index;
  items.forEach((li, i) => {
    const isActive = i === index;
    li.setAttribute("aria-selected", isActive ? "true" : "false");
    li.classList.toggle("bg-panel2", isActive);
  });
  el("searchInput").setAttribute("aria-activedescendant", `search-result-${index}`);
  if (typeof items[index].scrollIntoView === "function") {
    items[index].scrollIntoView({ block: "nearest" });
  }
}

function selectSearchResult(index) {
  const place = state.lastSearchResults[index];
  if (!place) return;
  el("searchInput").value = `${place.name}${place.country ? ", " + place.country : ""}`;
  closeSearchResults();
  loadWeather({ name: place.name, lat: place.lat, lon: place.lon });
}

el("searchInput").addEventListener("keydown", (event) => {
  const items = [...el("searchResults").children];
  if (!items.length) return;

  if (event.key === "ArrowDown") {
    event.preventDefault();
    const next = (state.activeResultIndex + 1) % items.length;
    setActiveResult(next);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    const prev = (state.activeResultIndex - 1 + items.length) % items.length;
    setActiveResult(prev);
  } else if (event.key === "Enter") {
    if (state.activeResultIndex >= 0) {
      event.preventDefault();
      selectSearchResult(state.activeResultIndex);
    }
  } else if (event.key === "Escape") {
    closeSearchResults();
  }
});

el("locateBtn").addEventListener("click", () => {
  if (!navigator.geolocation) {
    setStatus("Geolocation isn't available in this browser.");
    return;
  }
  setStatus("Locating you...");
  navigator.geolocation.getCurrentPosition(
    async (position) => {
      const { latitude, longitude } = position.coords;
      try {
        const response = await fetch(`/api/reverse?lat=${latitude}&lon=${longitude}`);
        const place = await response.json();
        loadWeather({ name: place.name, lat: latitude, lon: longitude });
      } catch (err) {
        loadWeather({ name: "Current location", lat: latitude, lon: longitude });
      }
    },
    () => setStatus("Location permission was denied - try searching for a place instead.")
  );
});

function setStatus(message) {
  el("statusLine").textContent = message;
}

async function loadWeather(location) {
  state.location = location;
  setStatus(`Loading weather for ${location.name}...`);
  el("searchInput").value = location.name;

  const url = `/api/weather?lat=${location.lat}&lon=${location.lon}&units=${state.units}&wind_unit=${state.windUnit}&name=${encodeURIComponent(location.name)}`;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || `HTTP ${response.status}`);
    }
    const data = await response.json();
    renderWeather(data);
    setStatus(data.from_cache ? "Served from cache (refreshes every 5 minutes)." : "");
    loadHistory(location);
    el("dateResult").textContent = "Pick a date to view forecast/history details for that day.";
  } catch (err) {
    setStatus(`Couldn't load weather: ${err.message}`);
  }
}

function renderWeather(data) {
  el("weatherApp").classList.remove("hidden");

  el("placeName").textContent = data.place_name;
  el("currentTemp").textContent = data.current.temperature;
  el("currentUnit").textContent = unitSuffix();
  el("observationLine").textContent = `${data.current.description || data.current.condition}.`;
  el("feelsLikeLine").textContent =
    `Feels like ${data.current.feels_like}${unitSuffix()} · Low ${data.current.low}${unitSuffix()} · High ${data.current.high}${unitSuffix()}`;

  el("statHumidity").textContent = `${data.current.humidity}%`;
  el("statWind").textContent = data.current.wind_direction
    ? `${data.current.wind_speed} ${speedSuffix()} ${data.current.wind_direction}`
    : `${data.current.wind_speed} ${speedSuffix()}`;
  el("statPressure").textContent = `${data.current.pressure} ${pressureSuffix()}`;
  el("statVisibility").textContent = data.current.visibility != null
    ? `${data.current.visibility.toFixed(1)} ${visibilitySuffix()}`
    : "—";
  const uv = uvRisk(data.current.uv_index);
  el("statUv").textContent = data.current.uv_index != null
    ? `${Number(data.current.uv_index).toFixed(1)} · ${uv.label}`
    : uv.label;
  el("uvExplanation").textContent = uv.explanation;

  renderHourly(data.hourly);
  renderDaily(data.daily);
  drawPrecipChart(data.hourly);
}

function renderHourly(hourly) {
  el("hourlyStrip").innerHTML = hourly
    .map((block) => {
      const time = new Date(block.time.replace(" ", "T")).toLocaleTimeString([], { hour: "numeric" });
      return `
        <div class="flex flex-col items-center gap-1.5 bg-panel rounded-lg px-3 py-3 min-w-[64px] shrink-0">
          <span class="text-xs text-fog">${time}</span>
          ${iconSvg(block.condition, "w-5 h-5")}
          <span class="text-sm tabular-nums">${block.temperature}°</span>
          <span class="text-[10px] text-aurora/80">${block.precipitation_probability}%</span>
        </div>`;
    })
    .join("");
}

function renderDaily(daily) {
  if (!daily.length) {
    el("dailyList").innerHTML = `<p class="text-sm text-fog py-3">No forecast data available.</p>`;
    return;
  }
  const globalLow = Math.min(...daily.map((d) => d.low));
  const globalHigh = Math.max(...daily.map((d) => d.high));
  const span = Math.max(globalHigh - globalLow, 1);

  el("dailyList").innerHTML = daily
    .map((day) => {
      const label = new Date(day.date + "T12:00:00").toLocaleDateString([], { weekday: "short" });
      const leftPct = ((day.low - globalLow) / span) * 100;
      const widthPct = ((day.high - day.low) / span) * 100;
      const precipLabel = day.avg_precip_chance != null
        ? `<span class="w-9 text-right text-aurora/70 text-xs tabular-nums">${day.avg_precip_chance}%</span>`
        : "";
      return `
        <div class="flex items-center gap-3 py-3 text-sm">
          <span class="w-10 text-fog">${label}</span>
          ${iconSvg(day.condition, "w-5 h-5 shrink-0")}
          ${precipLabel}
          <span class="w-8 text-right tabular-nums text-fog">${day.low}°</span>
          <div class="flex-1 h-1.5 bg-white/5 rounded-full relative">
            <div class="absolute h-1.5 bg-gradient-to-r from-aurora to-ember rounded-full" style="left:${leftPct}%; width:${widthPct}%"></div>
          </div>
          <span class="w-8 tabular-nums">${day.high}°</span>
        </div>`;
    })
    .join("");
}

function drawPrecipChart(hourly) {
  const svg = el("precipChart");
  const width = 600;
  const height = 120;
  const padding = 10;

  if (!hourly.length) {
    svg.innerHTML = "";
    return;
  }

  const points = hourly.map((block, index) => {
    const x = padding + (index / (hourly.length - 1 || 1)) * (width - padding * 2);
    const y = height - padding - (block.precipitation_probability / 100) * (height - padding * 2);
    return [x, y];
  });

  const linePath = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point[0]} ${point[1]}`).join(" ");
  const areaPath = `${linePath} L ${points[points.length - 1][0]} ${height} L ${points[0][0]} ${height} Z`;

  svg.innerHTML = `
    <defs>
      <linearGradient id="precipFill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#5EEAD4" stop-opacity="0.35" />
        <stop offset="100%" stop-color="#5EEAD4" stop-opacity="0" />
      </linearGradient>
      <linearGradient id="precipStroke" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="#5EEAD4" />
        <stop offset="100%" stop-color="#F5A25D" />
      </linearGradient>
    </defs>
    <path d="${areaPath}" fill="url(#precipFill)" />
    <path d="${linePath}" fill="none" stroke="url(#precipStroke)" stroke-width="2" stroke-linecap="round" class="precip-line" />
  `;
}

async function loadHistory(location) {
  try {
    const response = await fetch(`/api/history?lat=${location.lat}&lon=${location.lon}&units=${state.units}`);
    const history = await response.json();
    renderHistory(history);
  } catch (err) {
    console.error("History load failed:", err);
  }
}

function renderHistory(history) {
  const container = el("historyList");
  if (!history.length) {
    container.innerHTML = `<p class="text-fog text-sm">No history recorded yet for this location - check back after a few visits.</p>`;
    return;
  }
  container.innerHTML = history
    .map((snapshot) => {
      const when = new Date(snapshot.recorded_at).toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
      return `
        <div class="flex items-center gap-3 bg-panel rounded-lg px-3 py-2">
          ${iconSvg(snapshot.condition, "w-4 h-4 shrink-0")}
          <span class="text-fog w-36 shrink-0">${when}</span>
          <span class="tabular-nums">${Math.round(snapshot.temperature)}${unitSuffix()}</span>
          <span class="text-fog">${snapshot.condition}</span>
        </div>`;
    })
    .join("");
}

async function loadDateWeather(dateValue) {
  const { lat, lon } = state.location;
  el("dateResult").textContent = "Loading date details...";

  try {
    const response = await fetch(
      `/api/date-weather?lat=${lat}&lon=${lon}&units=${state.units}&date=${encodeURIComponent(dateValue)}`
    );
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || `HTTP ${response.status}`);
    }

    const payload = await response.json();
    renderDateWeather(payload);
  } catch (err) {
    el("dateResult").textContent = `Couldn't load date details: ${err.message}`;
  }
}

function renderDateWeather(payload) {
  const forecast = payload.forecast;
  const history = payload.history || [];

  if (!payload.has_data) {
    el("dateResult").innerHTML =
      `<p>No forecast/history data found for ${payload.date}.</p>`;
    return;
  }

  const forecastLine = forecast
    ? `<p><span class="text-paper">Forecast:</span> ${forecast.condition}, ${forecast.low}${unitSuffix()} to ${forecast.high}${unitSuffix()}, rain chance ${forecast.avg_precip_chance}%.</p>`
    : `<p><span class="text-paper">Forecast:</span> Not available for that date.</p>`;

  const historyLine = history.length
    ? `<p class="mt-1"><span class="text-paper">Recorded snapshots:</span> ${history.length} check-in(s) stored for that date.</p>`
    : `<p class="mt-1"><span class="text-paper">Recorded snapshots:</span> No stored check-ins for that date yet.</p>`;

  el("dateResult").innerHTML = `${forecastLine}${historyLine}`;
}

(function boot() {
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        try {
          const response = await fetch(`/api/reverse?lat=${latitude}&lon=${longitude}`);
          const place = await response.json();
          loadWeather({ name: place.name, lat: latitude, lon: longitude });
        } catch {
          loadWeather({ name: "Current location", lat: latitude, lon: longitude });
        }
      },
      () => setStatus("Search for a place, or allow location access, to get started.")
    );
  } else {
    setStatus("Search for a place to get started.");
  }
})();