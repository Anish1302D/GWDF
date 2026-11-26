const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

const memCache = new Map();

async function fetchJson(url, useCache = true) {
  if (useCache && memCache.has(url)) {
    return memCache.get(url);
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
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

export function fetchBlocks(scenario = "normal") {
  return fetchJson(`${API_BASE}/blocks?state=MH&scenario=${encodeURIComponent(scenario)}`);
}

export function fetchForecast(blockId, scenario = "normal") {
  return fetchJson(
    `${API_BASE}/blocks/${encodeURIComponent(blockId)}/forecast?scenario=${encodeURIComponent(scenario)}`
  );
}

export function fetchHistory(blockId) {
  return fetchJson(`${API_BASE}/blocks/${encodeURIComponent(blockId)}/history`);
}

export function fetchRankings(scenario = "normal", limit = 400) {
  return fetchJson(
    `${API_BASE}/rankings?state=MH&scenario=${encodeURIComponent(scenario)}&limit=${limit}`
  );
}

export function fetchGeoJson() {
  return fetchJson(`/geo/MH_blocks.geojson`, true);
}
