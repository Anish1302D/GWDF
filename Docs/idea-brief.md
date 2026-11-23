# WellCast: Idea Brief

> **Event:** Campus to Cloud Hackathon sponsored by AWS (Techfest 2026-27, IIT Bombay)  
> **Status:** Structured Draft — Fill `<FINAL_METRIC>` / `<LINK>` slots on Day 6 (`T9.1`) before exporting PDF for submission.

| Field | Value |
|---|---|
| **Project Name** | WellCast: Groundwater Depletion Forecaster |
| **Tagline** | *See groundwater stress before it hits.* |
| **Team Name / ID** | `<TEAM_NAME> / <TECHFEST_TEAM_ID>` |
| **AWS Builder Center Alias** | `<BUILDER_CENTER_ALIAS>` |
| **Live Prototype URL** | `https://<CLOUDFRONT_ID>.cloudfront.net` |
| **Public Code Repository** | `https://github.com/<OWNER>/<REPO>` |

---

## 1. The Problem

India is the world's largest extractor of groundwater, supplying the majority of rural drinking water and agricultural irrigation. Yet **groundwater depletion remains invisible at the local decision level until borewells run dry**:

- **Farmers** commit to water-intensive crops or take loans to drill deeper borewells before knowing whether their local aquifer will endure the upcoming dry season.
- **Block and District Water Planners** depend on periodic national assessments that are often backward-looking and published months or years after seasonal shifts occur.
- **Fragmented Public Data:** Monitoring-well depths (CGWB / India-WRIS), rainfall departures (IMD), and extraction assessments exist across separate portals and spreadsheets, rarely combined into a **forward-looking, local, easy-to-act-on forecast**.

---

## 2. Who It Helps

| Target User | Pain Point Solved | What WellCast Delivers |
|---|---|---|
| **Farmers & Rural Communities** | Uncertainty over seasonal water availability and crop/drilling choices | Mobile-friendly block map, 3-level risk rating (**Safe / Watch / Critical**), next-season depth forecast with confidence range, and plain-language advice in **English, Hindi, and Marathi** |
| **Block & District Water Planners** | Difficulty prioritizing limited water tankers, check dams, and recharge subsidies | Ranked list of highest-risk blocks, historical vs forecast trends, and drought stress-testing (**-10% / -20% / -30% rainfall scenarios**) |
| **NGOs & Researchers** | High friction joining scattered public hydrology spreadsheets | Clean open methodology, transparent uncertainty bands, explicit missing-data flags, and downloadable rankings |

---

## 3. How WellCast Works

1. **Public Data Ingestion & Standardization:** Cleans and aligns multi-year public groundwater monitoring well depths (`mbgl`), monthly rainfall anomalies, and CGWB extraction stages at **block level** for `<TARGET_STATE>` (`<BLOCK_COUNT>` blocks, `<YEAR_SPAN>`), following a strict **zero-fabricated-data** policy.
2. **Serverless Lakehouse Feature Engineering (AWS S3 + Glue + Athena):** Builds leak-free seasonal hydrology features — rolling 3/6/12-month rainfall, departure from normal, seasonal drawdown, 5-year depletion trend, and extraction stage.
3. **Honest Time-Split Forecasting (Amazon SageMaker):** Trains an XGBoost regressor alongside **10th and 90th percentile quantile models** on strictly chronological splits, benchmarked transparently against a Seasonal Naive baseline (`MAE: <MODEL_MAE> m vs Baseline <BASE_MAE> m`).
4. **Instant Precomputed Scenarios & Accessible Serving (Lambda + API Gateway + CloudFront):** Precomputes next-season forecasts for 100%, 90%, 80%, and 70% normal rainfall so farmers and planners can drag a live **"What if rainfall drops?"** slider in milliseconds on mobile networks — with zero idle GPU or database costs.

---

## 4. Impact & Measurable Value

- **Preventive Agricultural Decisions:** Enables earlier switching toward drought-resilient crops (millets, pulses) and micro-irrigation before peak dry-season drawdown.
- **Targeted Public Spending:** Helps district collectors and Jal Jeevan / watershed teams direct recharge structures and emergency tankers to the top `<TOP_CRITICAL_COUNT>` critical blocks ahead of summer.
- **Ultra-Low-Cost National Scalability:** Built entirely on serverless AWS primitives (`ap-south-1`), the single-state prototype runs for **`< $1/month`**, and the state-agnostic pipeline scales cleanly across India's ~7,000 blocks for only a few dollars per month.

---

## 5. Honest Limitations & Responsible AI

- Forecasts rely on historical monitoring-well medians (semi-annual cadence) and public rainfall records — not real-time borewell IoT sensors.
- Blocks with insufficient monitoring history are clearly marked **`Insufficient Data`** rather than filled with invented predictions.
- Every dataset, resolution fallback (such as district-mapped rainfall), and uncertainty interval is transparently disclosed inside the app.
