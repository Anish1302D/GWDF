const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

const memCache = new Map();

async function fetchJson(url, useCache = true) {
  if (useCache && memCache.has(url)) {
    return memCache.get(url);
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const errBody = await res.json();
        detail = errBody.error || detail;
      } catch {
        // ignore JSON parse error
      }
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    const data = await res.json();
    if (useCache) {
      memCache.set(url, data);
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

export function clearApiCache() {
  memCache.clear();
}

export function fetchHealth() {
  return fetchJson(`${API_BASE}/health`, false);
}

  export function fetchStatesSummary(scenario = "normal") {
    return fetchJson(`${API_BASE}/states?scenario=${encodeURIComponent(scenario)}`);
  }

  export function fetchBlocks(stateCode = "MH", scenario = "normal") {
    return fetchJson(
      `${API_BASE}/blocks?state=${encodeURIComponent(stateCode)}&scenario=${encodeURIComponent(scenario)}`
    );
  }

  export function fetchNearestBlock(lat, lon, scenario = "normal") {
    return fetchJson(
      `${API_BASE}/blocks/nearest?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&scenario=${encodeURIComponent(scenario)}`,
      false
    );
  }

  export function fetchForecast(blockId, scenario = "normal") {
    return fetchJson(
      `${API_BASE}/blocks/${encodeURIComponent(blockId)}/forecast?scenario=${encodeURIComponent(scenario)}`
    );
  }

  export function fetchHistory(blockId) {
    return fetchJson(`${API_BASE}/blocks/${encodeURIComponent(blockId)}/history`);
  }

    export function fetchRankings(stateCode = "ALL", scenario = "normal", limit = 400) {
      return fetchJson(
          `${API_BASE}/rankings?state=${encodeURIComponent(stateCode)}&scenario=${encodeURIComponent(scenario)}&limit=${limit}`
      );
    }

      export function fetchIndiaStatesGeoJson() {
        return fetchJson(`/geo/INDIA_states.geojson`, true);
      }

      export function fetchStateBlocksGeoJson(stateCode) {
        return fetchJson(`/geo/states/${encodeURIComponent(stateCode)}_blocks.geojson`, true);
      }
