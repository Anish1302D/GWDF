# 💧 WellCast: Groundwater Depletion Forecaster
 
> **See groundwater stress before it hits.**
> Block-level groundwater forecasts for Indian farmers and water planners, built on AWS.
 
Built for the **Campus to Cloud Hackathon sponsored by AWS** (Techfest 2026-27, IIT Bombay).
 
| | |
|---|---|
| **Live prototype** | `https://<your-cloudfront-id>.cloudfront.net` *(replace after deploy)* |
| **Demo video** | `<link>` *(under 3 minutes)* |
| **AWS Builder Center alias** | `<your-alias>` |
| **Team** | `<names>` |
 
---
 
## Table of contents
 
1. [Problem](#1-problem)
2. [Who it helps](#2-who-it-helps)
3. [Solution overview](#3-solution-overview)
4. [Architecture](#4-architecture)
5. [AWS services and why](#5-aws-services-and-why)
6. [Data](#6-data)
7. [ML approach](#7-ml-approach)
8. [API reference](#8-api-reference)
9. [Repository structure](#9-repository-structure)
10. [Implementation plan](#10-implementation-plan)
11. [Setup and deployment](#11-setup-and-deployment)
12. [Cost guardrails](#12-cost-guardrails)
13. [Impact and metrics](#13-impact-and-metrics)
14. [Limitations and honest caveats](#14-limitations-and-honest-caveats)
15. [Roadmap](#15-roadmap)
16. [Hackathon submission checklist](#16-hackathon-submission-checklist)
---
 
## 1. Problem
 
India is the world's largest extractor of groundwater, and a large share of irrigation and drinking water depends on it. The problem is not only that water is depleting, but that **nobody sees it coming at a local level**.
 
- **Farmers** decide what to sow and whether to drill deeper without knowing if the aquifer beneath them will last the season.
- **Block and district planners** rely on periodic assessments that are outdated by the time they are published.
- **The data exists** (rainfall, monitoring-well levels, extraction stage) but is scattered across portals and spreadsheets, and is rarely turned into a *forward-looking*, *local* warning.
## 2. Who it helps
 
| User | What they get |
|---|---|
| Farmers | A simple block-level risk rating (Safe / Watch / Critical), a forecast for the coming season and crop-water advice |
| Block and district planners | A ranked list of blocks most at risk, trends, and scenario analysis for allocating tankers, recharge structures and subsidies |
| NGOs and researchers | Explorable data and downloadable forecasts |
 
## 3. Solution overview
 
WellCast ingests rainfall and groundwater-level data, joins them at **block level**, trains a forecasting model, and serves the predictions through:
 
- a **farmer-facing web app** (map, risk badge, plain-language advice), and
- a **planner dashboard** (ranked blocks, trends, scenarios).
**Key features**
 
- 🗺️ Interactive block-level risk map
- 📈 Next-season water-level forecast with a confidence range
- 🌧️ "What if rainfall is 10–30% below normal?" scenario slider (precomputed scenarios)
- 🌾 Plain-language advice per risk level
- 🌐 English plus regional language toggle (Hindi/Marathi)
- 📊 Planner dashboard with ranked at-risk blocks
---
 
## 4. Architecture
 
### 4.1 High-level architecture
 
```mermaid
flowchart LR
    subgraph Sources["Public data sources"]
        A1[Rainfall data]
        A2[Groundwater level data]
        A3[Extraction stage data]
    end
 
    subgraph Storage["Amazon S3 data lake"]
        S1[(raw/)]
        S2[(curated/)]
        S3[(forecasts/)]
    end
 
    subgraph Analytics["Analytics and ML"]
        G[AWS Glue Crawler]
        AT[Amazon Athena]
        SM[Amazon SageMaker<br/>training job]
    end
 
    subgraph Serving["Serving layer"]
        APIGW[API Gateway]
        L[AWS Lambda]
        CF[CloudFront + S3<br/>React web app]
        QS[Amazon QuickSight<br/>planner dashboard]
    end
 
    Sources --> S1
    S1 --> G --> AT
    AT -->|feature SQL| S2
    S2 --> SM
    SM -->|forecasts| S3
    S3 --> AT
    AT --> L --> APIGW --> CF
    AT --> QS
 
    EB[EventBridge schedule] -.->|monthly refresh| AT
    CW[CloudWatch] -.->|logs and alarms| L
```
 
### 4.2 Data pipeline (sequence)
 
```mermaid
sequenceDiagram
    autonumber
    participant Dev as Data script
    participant S3 as S3 (raw)
    participant Glue as Glue Crawler
    participant Ath as Athena
    participant SM as SageMaker
    participant S3F as S3 (forecasts)
    participant API as Lambda + API Gateway
    participant UI as React app
 
    Dev->>S3: Upload cleaned CSV/Parquet
    S3->>Glue: Crawl and register schema
    Glue->>Ath: Tables available in Data Catalog
    Ath->>S3: CTAS creates feature table (curated/)
    S3->>SM: Training data
    SM->>S3F: Model artifacts and forecast Parquet
    UI->>API: GET /blocks/{id}/forecast
    API->>Ath: Query forecast table
    Ath->>S3F: Read results
    API-->>UI: JSON (risk, forecast, confidence)
```
 
### 4.3 Request flow for a farmer
 
```mermaid
flowchart TD
    U[Farmer opens WellCast] --> M[Selects state, district, block on map]
    M --> R[React app calls API Gateway]
    R --> L[Lambda]
    L --> C{Cached in memory<br/>or S3 JSON?}
    C -- yes --> J[Return JSON]
    C -- no --> Q[Run Athena query]
    Q --> J
    J --> V[UI shows risk badge, forecast chart, advice]
```
 
### 4.4 Data model
 
```mermaid
erDiagram
    BLOCK ||--o{ RAINFALL_MONTHLY : has
    BLOCK ||--o{ WATER_LEVEL : has
    BLOCK ||--o{ FORECAST : has
    BLOCK {
        string block_id PK
        string state
        string district
        string block_name
        string extraction_stage
        float lat
        float lon
    }
    RAINFALL_MONTHLY {
        string block_id FK
        date month
        float rainfall_mm
        float departure_from_normal_pct
    }
    WATER_LEVEL {
        string block_id FK
        date obs_date
        string season
        float depth_mbgl
    }
    FORECAST {
        string block_id FK
        date forecast_season
        float predicted_depth_mbgl
        float lower_bound
        float upper_bound
        string risk_class
        string scenario
    }
```
 
---
 
## 5. AWS services and why
 
| Service | Role in WellCast | Why this choice |
|---|---|---|
| **Amazon S3** | Data lake (`raw/`, `curated/`, `forecasts/`) and static hosting for the web app | Cheap, durable, free-tier friendly |
| **AWS Glue (Crawler)** | Detects schema and registers tables | Lets Athena query files without running a database |
| **Amazon Athena** | Serverless SQL for joins, feature engineering and serving queries | Pay per query, no servers to keep alive |
| **Amazon SageMaker** | Trains the forecasting model in a short-lived training job | Managed training; no idle cost when the job ends |
| **Amazon QuickSight** | Planner dashboard (ranked blocks, trends, maps) | Fast BI without custom front-end work |
| **AWS Lambda + API Gateway** | Thin JSON API that queries Athena or reads precomputed JSON | Serverless, near-zero idle cost |
| **Amazon CloudFront** | HTTPS global delivery of the React app | Fast, free-tier friendly, stable public URL |
| **Amazon EventBridge** | Monthly scheduled refresh | Automates re-ingestion and re-forecasting |
| **Amazon CloudWatch** | Logs, metrics, alarms | Visibility into Lambda and pipeline failures |
| **AWS IAM** | Least-privilege roles per component | Security baseline |
 
---
 
## 6. Data
 
> ⚠️ **Verify availability and licence terms of every dataset before use, and cite each one in the final submission.**
 
| Dataset | Typical source | Use |
|---|---|---|
| Groundwater level (monitoring wells, pre- and post-monsoon) | CGWB / India-WRIS | Target variable |
| Rainfall (monthly, district or gridded) | IMD / data.gov.in | Main predictor |
| Block extraction stage (Safe / Semi-critical / Critical / Over-exploited) | CGWB assessment reports | Context feature and label cross-check |
| Block boundaries (GeoJSON) | Public administrative boundary datasets | Map rendering |
 
**Scope for the prototype:** start with **one state** (for example Maharashtra), then show a clear path to national coverage.
 
**Rules we follow**
 
- No fabricated data. Where data is missing, we say so in the UI.
- Interpolated or imputed values are flagged.
- Every dataset is credited in `DATA_SOURCES.md`.
---
 
## 7. ML approach
 
**Goal:** predict next-season groundwater depth (metres below ground level) per block and derive a risk class.
 
**Features**
 
- Rolling 3- and 6-month rainfall totals
- Rainfall departure from the long-term normal
- Previous season's water-level change
- Current depth and 5-year trend
- Extraction stage (encoded)
- Season (pre-monsoon / post-monsoon)
**Models**
 
| Stage | Model | Reason |
|---|---|---|
| Baseline | Seasonal naive (last year's same season) | A sanity benchmark to beat |
| Main | XGBoost regressor (SageMaker built-in or script mode) | Strong on small tabular data, fast to train |
| Uncertainty | Quantile regression (10th / 90th percentile) | Shows a confidence range, not one number |
 
**Risk classes** (thresholds to be calibrated on the chosen state)
 
| Class | Meaning |
|---|---|
| 🟢 Safe | Stable or recovering water level |
| 🟡 Watch | Falling beyond a set rate or nearing a critical depth |
| 🔴 Critical | Rapid decline or very deep and still falling |
 
**Evaluation:** time-based split (train on earlier years, test on the latest). Report MAE against the baseline. Never use random splits for time-series data.
 
**Scenarios:** run the model with rainfall set to 100%, 90%, 80% and 70% of normal and store all results, so the UI slider is instant and costs nothing at runtime.
 
---
 
## 8. API reference
 
Base URL: `https://<api-id>.execute-api.ap-south-1.amazonaws.com/prod`
 
| Method | Path | Description |
|---|---|---|
| `GET` | `/blocks?state=&district=` | List blocks with current risk class |
| `GET` | `/blocks/{block_id}/forecast?scenario=normal` | Forecast, confidence range and risk class |
| `GET` | `/blocks/{block_id}/history` | Historical water level and rainfall |
| `GET` | `/rankings?state=&limit=20` | Top at-risk blocks (planner view) |
| `GET` | `/health` | Health check |
 
**Example response**
 
```json
{
  "block_id": "MH-PUN-012",
  "block_name": "Example Block",
  "scenario": "normal",
  "forecast_season": "2027-pre-monsoon",
  "predicted_depth_mbgl": 14.2,
  "lower_bound": 12.9,
  "upper_bound": 15.6,
  "risk_class": "Watch",
  "advice": "Prefer low-water crops and plan recharge before the dry season."
}
```
 
---
 
## 9. Repository structure
 
```
wellcast/
├── README.md
├── DATA_SOURCES.md
├── LICENSE
├── docs/
│   ├── architecture.png
│   ├── idea-brief.md
│   └── build-summary.md
├── data/
│   ├── sample/                  # small sample files only
│   └── scripts/
│       ├── fetch_and_clean.py
│       └── upload_to_s3.sh
├── sql/
│   ├── 01_create_tables.sql
│   ├── 02_features.sql
│   └── 03_serving_views.sql
├── ml/
│   ├── train.py                 # SageMaker script-mode entry point
│   ├── evaluate.py
│   ├── make_forecasts.py
│   └── requirements.txt
├── backend/
│   ├── lambda_handler.py
│   ├── athena_client.py
│   └── requirements.txt
├── frontend/
│   ├── package.json
│   ├── public/
│   └── src/
│       ├── components/          # Map, RiskBadge, ForecastChart, ScenarioSlider
│       ├── i18n/                # en.json, hi.json, mr.json
│       └── App.jsx
└── infra/
    ├── iam-policies/
    └── deploy.sh
```
 
---
