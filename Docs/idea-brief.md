# WellCast: Idea Brief

> **Event:** Campus to Cloud Hackathon sponsored by AWS (Techfest 2026-27, IIT Bombay)  
> **Status:** Complete Implementation Brief (plug in live CloudFront URL, Team ID & Builder Center alias upon AWS deploy).

| Field | Value |
|---|---|
| **Project Name** | WellCast: Groundwater Depletion Forecaster |
| **Tagline** | *See groundwater stress before it hits.* |
| **Target State & Scope** | **Maharashtra** — **356 Blocks (Talukas)** across all **36 Districts** |
| **Team Name / ID** | `<TEAM_NAME> / <TECHFEST_TEAM_ID>` |
| **AWS Builder Center Alias** | `<BUILDER_CENTER_ALIAS>` |
| **Live Prototype URL** | `https://<CLOUDFRONT_ID>.cloudfront.net` |
| **Public Code Repository** | `https://github.com/<OWNER>/GWDF` |

---

## 1. The Problem

India is the world's largest extractor of groundwater, supplying the majority of rural drinking water and agricultural irrigation. Yet **groundwater depletion remains invisible at the local decision level until borewells run dry**:

- **Farmers** commit to water-intensive crops or take loans to drill deeper borewells before knowing whether their local aquifer will endure the upcoming dry season.
- **Block and District Water Planners** depend on periodic national assessments that are backward-looking and published months after seasonal shifts occur.
- **Fragmented Public Data:** Monitoring-well depths (CGWB / GSDA), rainfall anomalies (NASA POWER / IMD), and administrative boundaries sit across disconnected portals and formats, rarely joined into a **forward-looking, local, easy-to-act-on warning**.

---

## 2. Who It Helps

| Target User | Pain Point Solved | What WellCast Delivers |
|---|---|---|
| **Farmers & Rural Communities** | Uncertainty over seasonal water availability and crop/drilling choices | Mobile-friendly block map, 3-level risk rating (**Safe / Watch / Critical**), next-season depth forecast with 80% confidence range, and plain-language advice in **English, Hindi, and Marathi** |
| **Block & District Water Planners** | Difficulty prioritizing limited water tankers, check dams, and recharge subsidies | Ranked list of all **356 Maharashtra blocks** by composite stress index, historical vs forecast trends, CSV export, and drought stress-testing (**-10% / -20% / -30% rainfall scenarios**) |
| **NGOs & Researchers** | High friction cleaning & joining scattered hydrology records | Open, reproducible pipeline over **756,542** raw monitoring-well records, explicit uncertainty bounds, and strict zero-fabricated-data integrity |

---

## 3. How WellCast Works

1. **Authentic Data Ingestion & Spatial Standardization:** Processes **756,542** raw monitoring-well readings from **CGWB (1991–2025)** and **GSDA-Maharashtra (1970–2025)** via NWIC alongside **NASA POWER Agroclimatology** monthly precipitation (`2012–2025`), matching **94,371** valid `2013–2025` seasonal readings across **356 Maharashtra blocks** (`7,860` block-season rows) using name aliases + GPS point-in-polygon matching.
2. **Serverless Lakehouse Feature Engineering (Amazon S3 + AWS Glue + Amazon Athena):** Computes leak-free seasonal hydrology features (`02_features.sql`) — rolling 3/6/12-month rainfall, departure from 12-year normal, seasonal drawdown, year-over-year change, and 5-year depletion trend.
3. **Honest Chronological Forecasting (Amazon SageMaker):** Trains a **Residual Monotone XGBoost Regressor** (`reg:absoluteerror`) plus **10th and 90th percentile quantile models** on strictly chronological splits (`2014–2023` train, `2024` validation, `2025` untouched holdout test):
   - Beats the Seasonal Naive benchmark across the board (**`0.8147 m` vs `0.8727 m` MAE (+6.65% skill)**; **`1.1078 m` vs `1.2246 m` RMSE (+9.54% skill)**; **`R² = 0.9110`**) and achieves a **13.15% MAE improvement on dry Pre-Monsoon forecasts (`0.8881 m` vs `1.0226 m`)**, with **76.92% CQR P10–P90 interval coverage (`2.62 m` width)**.
4. **Instant Precomputed Scenarios & Accessible Serving (Lambda + API Gateway + CloudFront OAC):** Batch-scores 100%, 90%, 80%, and 70% normal rainfall scenarios into lightweight S3 JSON objects so farmers and planners can drag the drought slider in milliseconds on mobile phones — with **zero idle servers or GPU endpoints**.

---

## 4. Impact & Unit Economics

- **Early Crop & Water Advisories:** Helps farmers shift toward low-water crops (millets, pulses) and micro-irrigation ahead of dry-season stress.
- **Data-Backed District Allocation:** Gives collectors in drought-prone Marathwada and Vidarbha an objective block ranking for recharge structures and tanker budgets.
- **Sub-\$1 Monthly Cloud Cost:** Engineered completely on serverless AWS primitives in `ap-south-1` (Mumbai), keeping prototype operating cost **under \$1/month** and scaling nationally across ~7,000 Indian blocks for only a few dollars per month.

---

## 5. Honest Limitations & Responsible AI

- Forecasts reflect block-median public monitoring wells (semi-annual cadence) and district agroclimatology grids — not individual borewell IoT sensors.
- Blocks lacking `>= 4` historical seasons are explicitly labelled **`Insufficient Data`** rather than filled with synthetic numbers.
- Full dataset attributions and caveats are surfaced directly inside the web application.
