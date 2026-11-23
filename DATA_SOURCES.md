# WellCast Data Sources & Attribution Registry

> **Core Integrity Policy (Non-Negotiable):**
> 1. **Zero fabricated data.** Every groundwater reading, rainfall record, extraction category, and boundary polygon used in WellCast must come from an authentic, verifiable public dataset.
> 2. **Explicit gaps.** Where a block or season has missing observations, WellCast surfaces `"Insufficient Data"` rather than inventing numbers.
> 3. **Flagged imputations.** Any short-gap interpolation or district-to-block fallback mapping is explicitly flagged (`is_imputed = true`, `imputation_method`) in both Parquet tables and API responses.
> 4. **Verify before ship.** Confirm exact URLs, download timestamps, and licence terms for every row below during Phase 0–1 before launching Phase 3.

---

## 1. Locked Scope Metadata (Fill on Day 1 — Task `T0.7`)

| Field | Value |
|---|---|
| **Target State (`D-01`)** | `Maharashtra` *(confirm on Day 1; switch only if multi-year coverage is inadequate)* |
| **Forecast Granularity (`D-02`)** | `Block (Taluka)` *(fallback: District level, declared openly in UI & README)* |
| **Temporal Coverage** | `<START_YEAR>` to `<END_YEAR>` *(target: >= 5 continuous years)* |
| **Observation Cadence** | Semi-annual (`pre-monsoon` Apr–May, `post-monsoon` Nov) or quarterly |
| **Total Blocks Covered** | `<COUNT>` *(of total `<TOTAL>` in state)* |
| **Last Verified Date** | `<YYYY-MM-DD>` |

---

## 2. Dataset Registry

Complete all `<VERIFY_ON_DAY_1>` placeholders in Phase 0–1 when actual files are downloaded into `data/raw_local/`.

### Dataset 1: Groundwater Monitoring Well Levels (Target Variable)
| Attribute | Details |
|---|---|
| **Canonical Table** | `wellcast.water_level` |
| **Primary Agency / Portal** | Central Ground Water Board (CGWB) / India Water Resources Information System (India-WRIS) / State GSDA (Maharashtra) |
| **Candidate Portal URLs** | `https://indiawris.gov.in/wris/` · `https://cgwb.gov.in/` · `https://data.gov.in/` |
| **Exact Downloaded URL** | `<FILL_ON_DAY_1>` |
| **Download Date** | `<YYYY-MM-DD>` |
| **File Format & Size** | `<CSV / XLSX, e.g., 14.2 MB>` |
| **Licence / Terms of Use** | Government Open Data License – India (GODL) / Public Government Portal Terms *(verify exact page notice)* |
| **Spatial Resolution** | Point (monitoring well lat/lon) -> aggregated via median/mean to Block (or District) |
| **Temporal Coverage** | `<YYYY to YYYY>` (Pre-monsoon & Post-monsoon readings) |
| **Key Raw Columns** | State, District, Block/Taluka, Station/Well ID, Date/Season, Water Level (`mbgl` — metres below ground level) |
| **Known Caveats** | Seasonal well network changes over years; occasional negative/sentinel values (`-999`, `0.00` dry well codes) require explicit cleaning and removal |

### Dataset 2: Monthly Rainfall & Departure from Normal (Primary Predictor)
| Attribute | Details |
|---|---|
| **Canonical Table** | `wellcast.rainfall_monthly` |
| **Primary Agency / Portal** | India Meteorological Department (IMD) / `data.gov.in` / India-WRIS Rainfall Module |
| **Candidate Portal URLs** | `https://mausam.imd.gov.in/` · `https://data.gov.in/` · `https://indiawris.gov.in/wris/` |
| **Exact Downloaded URL** | `<FILL_ON_DAY_1>` |
| **Download Date** | `<YYYY-MM-DD>` |
| **File Format & Size** | `<CSV / NetCDF / XLSX>` |
| **Licence / Terms of Use** | Government Open Data License – India (GODL) / IMD Open Research Use *(verify exact dataset terms)* |
| **Spatial Resolution** | District monthly (mapped to child blocks via district key) or Block/Gridded (`0.25° x 0.25°` spatially joined to block centroids) |
| **Temporal Coverage** | `<YYYY-MM to YYYY-MM>` (must start >= 12 months earlier than first groundwater target for rolling windows) |
| **Key Raw Columns** | State, District (or Block/Grid), Year, Month, Actual Rainfall (`mm`), Normal Rainfall (`mm`), Departure (`%`) |
| **Known Caveats** | If district rainfall is assigned to blocks, set `rainfall_granularity = "district_mapped"` and disclose clearly in UI limitations note |

### Dataset 3: Dynamic Ground Water Resources Extraction Stage (Context Feature & Calibration Cross-Check)
| Attribute | Details |
|---|---|
| **Canonical Table** | `wellcast.block` (`extraction_stage` column) |
| **Primary Agency / Portal** | Central Ground Water Board (CGWB) — National Compilation on Dynamic Ground Water Resources of India / IN-GRES Portal |
| **Candidate Portal URLs** | `https://ingres.iith.ac.in/` · `https://cgwb.gov.in/` |
| **Exact Downloaded URL** | `<FILL_ON_DAY_1>` |
| **Download Date** | `<YYYY-MM-DD>` |
| **File Format & Size** | `<CSV / XLSX / PDF table extract>` |
| **Licence / Terms of Use** | Public CGWB Assessment Report (cite assessment year, e.g., 2023/2024 Dynamic GW Resource Assessment) |
| **Spatial Resolution** | Assessment Unit (Block / Taluka / Watershed) |
| **Categories** | `Safe` (<70% extraction), `Semi-Critical` (70–90%), `Critical` (90–100%), `Over-Exploited` (>100%), `Saline` |
| **Known Caveats** | Assessment unit names occasionally combine or split talukas; log all fuzzy/manual alias resolutions in `data/scripts/name_aliases.json` |

### Dataset 4: Administrative Boundaries GeoJSON (Interactive Map Layer)
| Attribute | Details |
|---|---|
| **Canonical Output** | `s3://<bucket>/api/geojson/<state>_blocks.geojson` |
| **Primary Agency / Portal** | Public Open Administrative Boundaries (e.g., DataMeet Community Maps / Survey of India / Census Sub-district GeoJSON) |
| **Candidate Portal URLs** | `https://github.com/datameet/maps` · `https://data.gov.in/` |
| **Exact Downloaded URL** | `<FILL_ON_DAY_1>` |
| **Download Date** | `<YYYY-MM-DD>` |
| **Licence / Terms of Use** | `<e.g., Creative Commons Attribution-ShareAlike 2.5 India / GODL — verify exact repo LICENSE>` |
| **Spatial Resolution** | Sub-district / Taluka / Block polygons (simplified to <1.5 MB via Douglas-Peucker for fast mobile Leaflet loading) |
| **Known Caveats** | Administrative renamings in Maharashtra (e.g., `Aurangabad` -> `Chhatrapati Sambhajinagar`, `Osmanabad` -> `Dharashiv`, `Ahmadnagar` -> `Ahilyanagar`) and newly carved districts (`Palghar` from `Thane`) must be normalized in `name_aliases.json` |

---

## 3. Data Quality, Cleaning & Imputation Rules

All cleaning transformations happen deterministically inside `data/scripts/fetch_and_clean.py`:

| Check Category | Exact Rule | Action Taken | Flag Recorded |
|---|---|---|---|
| **Impossible Depth** | `depth_mbgl < 0` or `depth_mbgl > 300` or sentinel (`-999`, `9999`) | Drop reading before block aggregation | Log dropped row count in cleaning summary |
| **Impossible Rainfall** | `rainfall_mm < 0` or `rainfall_mm > 3000` (single month extreme check) | Inspect & drop invalid sentinel rows | Log dropped row count |
| **Well-to-Block Aggregation** | Multiple monitoring wells in one block & season | Compute **median** `depth_mbgl` (robust to outliers) + record `well_count` | `well_count` stored on every row |
| **Single Missing Season** | Isolated 1-season gap between two valid seasons for the same block | Optional flag-only (preferred: leave null for target; only interpolate non-target lag if strictly bounded) | `is_imputed = true`, `imputation_method = "linear_prev_next"` (never impute `target_depth_next`!) |
| **Sparse Blocks** | Block has `< 4` valid historical seasonal readings | Exclude from ML training & mark as `"Insufficient Data"` on map | `risk_class = "Insufficient Data"` |
| **District-to-Block Rainfall** | Rainfall dataset available only at district granularity | Join on normalized `(state, district, month)` | `rainfall_source_level = "district"` |

---

## 4. Fallback Sourcing Hierarchy (Day 1 Gate `GATE-0`)

If any primary portal is unavailable or incomplete during Phase 0, apply these fallbacks in order and document the choice immediately:

1. **Rainfall Fallback:** Block rainfall unavailable -> use **District monthly rainfall** mapped to all blocks in that district (`D-02` stays Block level; disclose clearly).
2. **Groundwater Density Fallback:** Block-level well observations < 50% coverage -> aggregate all available wells per block; if still too sparse, switch `D-02` cleanly to **District level** and update UI labels (`"District Forecast"`).
3. **Boundary Polygon Fallback:** Clean sub-district GeoJSON has unresolvable geometry/name mismatches -> render accurate **block/district centroid circle markers** on Leaflet with proportional risk styling until polygons align.
4. **State Fallback:** Target state data cannot be verified by Day 1 8:00 PM IST -> switch `D-01` to another well-documented Indian state (e.g., Gujarat, Rajasthan, Punjab, or Tamil Nadu).

---

## 5. Attribution Text for App Footer & Submission Docs

Copy this template into the frontend "Data Sources & Limitations" modal and `Docs/idea-brief.md` after filling in verified details:

> **Data Attribution:** Historical groundwater level observations are sourced from the Central Ground Water Board (CGWB) / India-WRIS (`<YEARS>`). Monthly rainfall records are sourced from the India Meteorological Department (IMD) / Open Government Data Platform (`data.gov.in`, `<YEARS>`). Block extraction classifications reference the CGWB Dynamic Ground Water Resources Assessment (`<YEAR>`). Administrative boundaries are derived from `<BOUNDARY_SOURCE>` under `<LICENCE>`.  
> **Limitations:** Forecasts are statistical estimates derived from historical monitoring well medians and rainfall anomalies; they do not substitute for site-specific hydrogeological surveys or official government advisories. Blocks without sufficient monitoring history are explicitly marked as having insufficient data.
