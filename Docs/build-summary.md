# WellCast: AWS Build Summary

> **Event:** Campus to Cloud Hackathon sponsored by AWS (Techfest 2026-27, IIT Bombay)  
> **Region:** `ap-south-1` (Mumbai)  
> **Status:** Structured Draft — Fill `<FINAL_VALUE>` placeholders and embed `Docs/architecture.png` on Day 6 (`T9.2`) before exporting PDF.

---

## 1. Architecture Overview

WellCast follows a **serverless, zero-idle-compute AWS lakehouse and precomputed-serving architecture** engineered for high reliability, sub-200 ms mobile response times, and near-zero operating cost.

```text
Public Datasets (CGWB / IMD / GeoJSON)
   │  (data/scripts/fetch_and_clean.py -> Parquet)
   ▼
Amazon S3 Data Lake (raw/ -> curated/ -> models/ -> forecasts/ -> api/)
   │
   ├──► AWS Glue Crawler (Data Catalog: database `wellcast`)
   │        │
   │        ▼
   │    Amazon Athena (Workgroup `wellcast-wg`, 100 MB scan limit)
   │        ├──► Feature Engineering CTAS (sql/02_features.sql -> curated/features/)
   │        └──► Serving Views & Amazon QuickSight Planner BI (Bonus)
   │
   ├──► Amazon SageMaker (Short-Lived Training Job: ml/train.py -> model.tar.gz)
   │        └──► Batch Inference + 4 Rainfall Scenarios (100/90/80/70%) -> S3 forecasts/ & api/
   │
   └──► AWS Lambda (Python 3.12, S3 read-only + 5m cache)
            └──► Amazon API Gateway (HTTP API, CORS + throttling)
                     └──► React + Leaflet App on Private S3 + Amazon CloudFront (HTTPS + OAC)
```

*(Insert exported `Docs/architecture.png` here when converting to PDF.)*

---

## 2. AWS Services Used & Engineering Justification

| AWS Service | Exact Role in WellCast | Engineering Justification |
|---|---|---|
| **Amazon S3** | Private Data Lake (`raw/`, `curated/`, `models/`, `forecasts/`, `api/`, `athena-results/`) + Private Static Web bucket | Durable, Apache Parquet-friendly object storage with near-zero cost and lifecycle expiry on Athena scratch outputs |
| **AWS Glue (Crawler & Catalog)** | Auto-discovers Parquet schemas in `raw/` and registers tables in database `wellcast` | Eliminates need to provision or pay for an always-on relational database |
| **Amazon Athena** | Serverless SQL engine for zero-leakage window feature engineering (`02_features.sql`) and planner aggregations | Pay-per-TB scanned; paired with Snappy Parquet and a `100 MB` workgroup scan cap, full runs cost fractions of a cent |
| **Amazon SageMaker** | Executes managed script-mode Training Job (`ml/train.py`) on `ml.m5.large` to train XGBoost + P10/P90 quantile models | Managed, reproducible cloud training that automatically terminates after ~2 minutes (zero idle notebook/endpoint spend) |
| **AWS Lambda** | Thin Python 3.12 API serving precomputed block forecasts, histories, and rankings from S3 `api/` with in-memory TTL cache | Serverless scaling with sub-200 ms warm responses and zero idle compute |
| **Amazon API Gateway** | HTTP API exposing 5 versioned REST routes (`/blocks`, `/forecast`, `/history`, `/rankings`, `/health`) with strict CORS & throttling | Managed HTTPS endpoint with built-in request throttling (~70% lower cost than REST API v1) |
| **Amazon CloudFront** | Global HTTPS CDN serving the React + Leaflet SPA from a private S3 bucket via **Origin Access Control (OAC)** | Fast mobile asset delivery, automatic HTTPS, and clean SPA routing without exposing S3 publicly |
| **Amazon QuickSight** *(P2 Bonus — keep only if deployed)* | Executive planner dashboard connected to Athena `wellcast.forecasts` | Rapid BI exploration of district risk distributions and ranked blocks |
| **Amazon CloudWatch** | Structured Lambda logs (14-day retention) and Error Rate alarm | Operational visibility into API errors or latency regressions during judging |
| **Amazon EventBridge** *(Optional)* | Scheduled monthly/seasonal pipeline trigger blueprint | Demonstrates automated production re-ingestion and re-forecasting |
| **AWS IAM & AWS Budgets** | Scoped least-privilege roles per component + Root MFA + \$5 monthly cost alert | Security and FinOps hygiene enforced from Day 1 |

---

## 3. ML Pipeline & Honest Evaluation Summary

*(Replace placeholders after Phase 3 `T3.6` completes.)*

| Metric / Property | Result |
|---|---|
| **Target State & Granularity** | `<STATE>` — `<BLOCK / DISTRICT>` (`<N_UNITS>` units) |
| **Temporal Evaluation Split** | Train: `<START_YR>–<TRAIN_END_YR>` · Holdout Test: `<TEST_YR>` (strict time split, zero random shuffle) |
| **Seasonal Naive Baseline MAE** | `<BASE_MAE> mbgl` |
| **XGBoost Main Model MAE** | `<XGB_MAE> mbgl` (`<IMPROVEMENT_PCT>%` vs baseline) |
| **P10–P90 Confidence Interval Coverage** | `<COVERAGE_PCT>%` on holdout test year |
| **Precomputed Rainfall Scenarios** | `normal` (100%), `minus10` (90%), `minus20` (80%), `minus30` (70%) |
| **SageMaker Training Job ID** | `<SAGEMAKER_JOB_NAME>` (`Completed` in `<DURATION>` sec) |

---

## 4. Security & Cost Guardrails Verified

- **Zero Public S3 Buckets:** `Block Public Access = ON` on both Data Lake and Static Web buckets; CloudFront OAC enforces private origin reads.
- **Least-Privilege IAM:** `wellcast-lambda-api-role` has `s3:GetObject` strictly on `api/*` only; zero AWS keys in the GitHub repository.
- **Zero Idle Paid Compute:** Verified 0 running SageMaker endpoints, 0 Notebook instances, 0 EC2/RDS instances.
- **Actual Spend During Build:** `$<ACTUAL_COST> USD` (guarded by AWS Budgets alert).

---

## 5. Live Verification Links

- **Live Web App (CloudFront):** `https://<CLOUDFRONT_ID>.cloudfront.net`
- **API Health Endpoint:** `https://<API_ID>.execute-api.ap-south-1.amazonaws.com/prod/health`
- **Public GitHub Repo:** `https://github.com/<OWNER>/<REPO>`
- **Demo Video (<3 min):** `<VIDEO_LINK>`
