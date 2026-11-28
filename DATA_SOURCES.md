# WellCast Pan-India Data Sources & Attribution Registry

> **Core Integrity Policy (Verified Across All 35 States & UTs):**
> 1. **Zero fabricated data.** All **2,035,145** groundwater readings, **28,896** grid-month precipitation values, and **5,795** sub-district boundary polygons originate from authentic public government and scientific archives.
> 2. **Explicit gaps.** `1,797` sub-districts lacking `>= 4` valid historical CGWB seasonal observations (e.g., high-altitude Himalayan blocks or unmonitored islands) are transparently marked `"Insufficient Data"` on the map.
> 3. **Flagged provenance.** `is_imputed = False` and `rainfall_source_level = "nasa_power_gridded"` are carried in Parquet tables and API JSON bundles.

---

## 1. Verified Pan-India Scope Summary

| Field | Verified Value |
|---|---|
| **Geographic Scope** | **All-India (`35` States & Union Territories, `675` Districts, `5,795` Sub-Districts / Blocks)** |
| **Actively Forecasted Blocks** | **`3,998` Sub-Districts / Blocks** (`>= 4` historical seasons & active recent monitoring) |
| **Temporal Coverage** | Groundwater: `2013-05-01` to `2025-11-01` · Precipitation: `2012-01-01` to `2025-12-01` |
| **Supervised ML Transitions** | `45,964` leak-free 6-month transitions (`72,385` total block-season rows) |
| **Last Verified Date** | `2026-11-28` |

---

## 2. Verified Dataset Registry

### Dataset 1A: Central Ground Water Board (CGWB) Pan-India Manual Quarterly Network
- **Agency / Portal:** Central Ground Water Board (CGWB), Ministry of Jal Shakti — via National Water Data Portal (`NWIC` CKAN package `956add67-cba9-41a5-9d5c-96d73db44aef`)
- **Coverage:** **63 official state CSV files (`187.9 MB`)** spanning all Indian States & UTs (`1991–2020` and `2021–2025`)
- **Licence:** Government Open Data License – India (GODL) / NWIC Open Data

### Dataset 1B: GSDA-Maharashtra Manual Groundwater Network
- **Agency / Portal:** Groundwater Surveys and Development Agency (GSDA), Government of Maharashtra — via NWIC (`aab57261-b0d1-487b-8f9f-7ae2fb16637a`, `91.49 MB`, `1970–2025`)
- **Combined Raw Observations Scanned (CGWB + GSDA):** **`2,035,145` well readings** -> **`353,010`** valid `2013–2025` seasonal (`pre-monsoon` / `post-monsoon`) station-seasons matched at **`96.02%`** via normalized name aliases + `STRtree` GPS point-in-polygon lookup.

### Dataset 2: All-India Monthly Agroclimatology Precipitation Grid
- **Agency / Portal:** NASA Langley Research Center — `NASA POWER` Agroclimatology Archive (`PRECTOTCORR`, `https://power.larc.nasa.gov/api/temporal/monthly/point`)
- **Coverage:** **`172` nationwide `1.5°` agro-climatic grid cells** (`28,896` cell-months, `2012–2025`) mapped to **`973,560`** block-month rows, benchmarked against `2013–2024` calendar-month climatological normals.
- **Licence:** Open Scientific Data / Public Domain (credit: NASA POWER Project).

### Dataset 3: All-India State & Sub-District Administrative Boundaries
- **Source:** Census of India / Local Government Directory (LGD) Shapefile/GeoJSON mirror (`datta07/INDIAN-SHAPEFILES`: `INDIA_STATES.geojson` & `INDIAN_SUB_DISTRICTS.geojson`)
- **Web Optimization:** Simplified into `INDIA_states.geojson` (**`212.4 KB`**) plus `35` lazy-loaded per-state block GeoJSON files (`frontend/public/geo/states/<STATE_CODE>_blocks.geojson`, averaging **`134.3 KB`** per state).
