# WellCast Data Sources & Attribution Registry

> **Core Integrity Policy (Verified & Enforced):**
> 1. **Zero fabricated data.** Every groundwater reading, rainfall value, and administrative boundary polygon in WellCast originates from an authentic, public scientific or government dataset listed below.
> 2. **Explicit gaps.** Blocks with fewer than 4 historical seasonal observations are marked `"Insufficient Data"` rather than filled with invented numbers.
> 3. **Flagged provenance.** `is_imputed` and `rainfall_source_level = "district_gridded"` are carried explicitly through Parquet tables and REST API JSON payloads.

---

## 1. Locked Scope Metadata (`GATE-0` & `GATE-1` Verified)

| Field | Verified Value |
|---|---|
| **Target State (`D-01`)** | `Maharashtra` (`MH`) |
| **Forecast Granularity (`D-02`)** | `Block / Taluka (Sub-District)` |
| **Temporal Coverage** | Groundwater: `2013-05-01` to `2025-11-01` (26 semi-annual seasons) · Precipitation: `2012-01-01` to `2025-12-01` |
| **Observation Cadence** | Semi-annual (`pre-monsoon` Mar–May anchored to `YYYY-05-01`, `post-monsoon` Oct–Nov anchored to `YYYY-11-01`) |
| **Total Blocks Covered** | `356` canonical blocks across all `36` districts of Maharashtra (`7,860` block-season rows from `756,542` raw well records) |
| **Last Verified Date** | `2026-11-26` |

---

## 2. Verified Dataset Registry

### Dataset 1A: Central Ground Water Board (CGWB) Manual Quarterly Groundwater Levels
| Attribute | Verified Details |
|---|---|
| **Canonical Table** | `wellcast.water_level` |
| **Agency / Portal** | Central Ground Water Board (CGWB), Ministry of Jal Shakti — via National Water Data Portal (`NWIC`) |
| **Exact Downloaded URLs** | 1. `https://nwdp.nwic.gov.in/dataset/956add67-cba9-41a5-9d5c-96d73db44aef/resource/0e7180fa-5282-4df6-bead-8ca7a7557e74/download/gwl_manual_quarterly_cgwb_mh_1991_2020.csv`<br/>2. `https://nwdp.nwic.gov.in/dataset/956add67-cba9-41a5-9d5c-96d73db44aef/resource/073029e8-492d-416c-9857-3ad3e27c69a6/download/gwl_manual_quarterly_cgwb_mh_2021_2025.csv` |
| **Download Date** | `2026-11-26` |
| **File Format & Size** | CSV (`13.98 MB` + `1.75 MB` = `119,937` station readings) |
| **Licence / Terms** | Government Open Data License – India (GODL) / NWIC Open Data (`Other (Open)`) |
| **Spatial Resolution** | Monitoring well (`Latitude`, `Longitude`, `District`, `Tehsil`, `Block`) aggregated via **median** to Block |

### Dataset 1B: GSDA-Maharashtra Manual Groundwater Monitoring Network
| Attribute | Verified Details |
|---|---|
| **Canonical Table** | `wellcast.water_level` (merged & deduplicated per well-season with CGWB) |
| **Agency / Portal** | Groundwater Surveys and Development Agency (GSDA), Government of Maharashtra — via National Water Data Portal (`NWIC`) |
| **Exact Downloaded URL** | `https://nwdp.nwic.gov.in/dataset/aab57261-b0d1-487b-8f9f-7ae2fb16637a/resource/bb185a88-c7c3-483f-b06e-784ce5322ff8/download/ground_water_level_manual_quarterly_maharashtra_1970_2025.csv` |
| **Download Date** | `2026-11-26` |
| **File Format & Size** | CSV (`91.49 MB`, extending through `2025`) |
| **Licence / Terms** | Government Open Data License – India (GODL) / NWIC Open Data (`Other (Open)`) |
| **Spatial Resolution** | Monitoring well (`Well ID`, `District Name`, `Block Name`, `Latitude`, `Longitude`) aggregated via **median** to Block |

### Dataset 2: Monthly Agroclimatology Precipitation & Normals (Primary Predictor)
| Attribute | Verified Details |
|---|---|
| **Canonical Table** | `wellcast.rainfall_monthly` |
| **Agency / Portal** | NASA Langley Research Center — Prediction Of Worldwide Energy Resources (`NASA POWER`) Agroclimatology Archive (`PRECTOTCORR` bias-corrected precipitation) |
| **Exact API Endpoint** | `https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=PRECTOTCORR&community=AG&start=2012&end=2025&format=JSON` |
| **Supplementary Reference** | IMD District Daily & Maharashtra SW Daily Rainfall via NWIC (`https://nwdp.nwic.gov.in/dataset/9380580f-9bf0-4708-9773-0cea3cbc595a`) |
| **Download Date** | `2026-11-26` |
| **File Format & Coverage** | `6,048` district-months (`2012-01` to `2025-12`) across all `36` Maharashtra districts -> mapped to `59,808` block-month rows |
| **Licence / Terms** | Public Domain / Open Scientific Data (NASA Earth Science Division; credit: NASA POWER Project) |
| **Climatological Normal** | Computed deterministically per district and calendar month over `2013–2024` (`12-year` baseline); tagged `rainfall_source_level = "district_gridded"` |

### Dataset 3:CGWB Official Block Extraction Stage Context
| Attribute | Verified Details |
|---|---|
| **Canonical Column** | `wellcast.block.extraction_stage` (`extraction_stage_code`) |
| **Handling Applied** | Because IN-GRES (`ingres.iith.ac.in`) does not publish an unauthenticated bulk CSV export for Maharashtra's 356 talukas, WellCast strictly obeys its zero-fabrication policy by setting `extraction_stage = "Unknown"` (`extraction_stage_code = -1`) rather than inventing official government classifications, relying directly on observed CGWB/GSDA monitoring-well depths and multi-year drawdown trends |

### Dataset 4: Administrative Boundaries GeoJSON (Interactive Map Layer)
| Attribute | Verified Details |
|---|---|
| **Canonical Output** | `frontend/public/geo/MH_blocks.geojson` & `data/processed_local/api/geojson/MH_blocks.geojson` |
| **Source Repository** | Census of India 2011 / Local Government Directory (LGD) Maharashtra Sub-District Shapefile mirror (`datta07/INDIAN-SHAPEFILES`) |
| **Exact Downloaded URL** | `https://raw.githubusercontent.com/datta07/INDIAN-SHAPEFILES/master/STATES/MAHARASHTRA/MAHARASHTRA_SUBDISTRICTS.geojson` |
| **Download Date** | `2026-11-26` |
| **Processing** | Removed 1 non-Maharashtra border sliver (`Vijayapura`), merged multi-part talukas into `356` canonical Maharashtra blocks across `36` districts, and simplified topology to `455.7 KB` for fast mobile rendering |

---

## 3. Data Quality & Cleaning Summary (`data/scripts/fetch_and_clean.py`)

- **Total raw monitoring-well records scanned:** `756,542`
- **Valid `2013–2025` seasonal (`pre-monsoon` / `post-monsoon`) readings (`0 < depth_mbgl <= 250`):** `94,371`
- **Block name + GPS point-in-polygon match rate:** `100.0%`
- **Imputed target values:** `0` (`is_imputed = False` across 100% of rows)
- **District renamings normalized (`name_aliases.json`):** `Aurangabad -> Chhatrapati Sambhajinagar`, `Osmanabad -> Dharashiv`, `Ahmadnagar -> Ahilyanagar`, `Bid -> Beed`, `Buldana -> Buldhana`, `Gondiya -> Gondia`, `Raigarh -> Raigad`, `Sindudurg -> Sindhudurg`.
