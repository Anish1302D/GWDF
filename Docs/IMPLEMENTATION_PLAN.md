# WellCast: End-to-End Implementation Plan

> Timeline: **24 Nov to 30 Nov 2026**, with 30 Nov kept as a buffer.
> Submission deadline: **30 Nov 2026, 11:59 PM IST**. Demo Day: **17 Dec 2026** at IIT Bombay.

Each phase has an **exit check** (how you know you're done) and **fallbacks** for the things most likely to go wrong.

---

## Decisions to lock on Day 1

| Decision | Recommendation |
|---|---|
| State | One state only (Maharashtra is a natural fit) |
| Granularity | Block level if the data allows; otherwise district level, stated openly |
| Region | `ap-south-1` (Mumbai) |
| Runtime serving | Precomputed forecasts as static JSON in S3, served via Lambda |
| Model | Seasonal-naive baseline, then XGBoost |
| Frontend | React plus a map library (Leaflet is the simplest) |

---

## Timeline at a glance

| Day | Date | Phase | Goal |
|---|---|---|---|
| 1 | Tue 24 Nov | 0 | Accounts, repo, budget alert, data located |
| 2 | Wed 25 Nov | 1, 2 | Data in S3, queryable in Athena, features started |
| 3 | Thu 26 Nov | 2, 3 | Features done, model trained |
| 4 | Fri 27 Nov | 4, 5 | Forecasts generated, API live |
| 5 | Sat 28 Nov | 6, 7 | Frontend deployed, QuickSight view |
| 6 | Sun 29 Nov | 8, 9 | Hardening, video, docs, Drive folder |
| 7 | Mon 30 Nov | 10 | Buffer. Submit on the evening of the 29th if possible |

---

## Phase 0: Foundation (Day 1, Tue 24 Nov)

- [ ] Create your AWS Builder Center profile, note the alias, and **start student verification now** (recommended to finish by 27 Nov)
- [ ] Create the AWS account and add a **budget alert** immediately
- [ ] Don't work from the root user: create an IAM user or role for yourself and enable MFA on root
- [ ] Create a public GitHub repo with the folder structure from the README
- [ ] Register on techfest.org and note the **Team ID**
- [ ] Decide who the **Team Leader** is, since only they can submit
- [ ] Find and download data for your state: groundwater levels, rainfall, extraction stage, block boundaries

**Exit check:** you can open real files containing groundwater levels *and* rainfall for your state, covering several years.

**Fallbacks**
- Rainfall only at district level → map each block to its district's rainfall.
- Well data sparse at block level → aggregate wells per block, or move to district level.
- Data too thin for any state → pick a different state. Never invent values.

---

## Phase 1: Data cleaning and the S3 data lake (Day 2, Wed 25 Nov)

- [ ] Create the S3 bucket with folders: `raw/`, `curated/`, `forecasts/`, `athena-results/`
- [ ] In `data/scripts/fetch_and_clean.py`:
  - [ ] Standardise block and district names (spelling variants are the biggest time sink)
  - [ ] Convert dates to a consistent monthly or seasonal format
  - [ ] Remove impossible values and flag missing ones
  - [ ] Save as **Parquet** or clean CSV
- [ ] Upload to `raw/`
- [ ] Record every dataset's source and licence in `DATA_SOURCES.md`
- [ ] Create a Glue database and run a **Crawler** over `raw/`
- [ ] In Athena, set the query-results location and confirm `SELECT * ... LIMIT 10` works on each table

**Exit check:** all tables are queryable in Athena, and a join on block and month returns rows.

---

## Phase 2: Feature engineering in Athena (Day 2 evening to Day 3 morning)

- [ ] Write `sql/02_features.sql` to build one row per block per season with:
  - rolling 3- and 6-month rainfall
  - rainfall departure from normal
  - previous season's water-level change
  - current depth and multi-year trend
  - extraction stage
- [ ] Create the **target**: next season's depth (or change in depth)
- [ ] Save the result to `curated/features/` as Parquet
- [ ] Sanity-check: row counts, nulls, and a few blocks by hand

**Exit check:** a feature table with a defined target and **no data leakage** (no future information in the features).

```sql
-- sql/02_features.sql (illustrative)
CREATE TABLE wellcast.features
WITH (format = 'PARQUET',
      external_location = 's3://<bucket>/curated/features/') AS
SELECT
  w.block_id,
  w.obs_date,
  w.season,
  w.depth_mbgl,
  w.depth_mbgl - LAG(w.depth_mbgl) OVER (
      PARTITION BY w.block_id ORDER BY w.obs_date) AS prev_change,
  SUM(r.rainfall_mm) OVER (
      PARTITION BY w.block_id ORDER BY r.month
      ROWS BETWEEN 5 PRECEDING AND CURRENT ROW)   AS rain_6m,
  r.departure_from_normal_pct,
  b.extraction_stage
FROM wellcast.water_level w
JOIN wellcast.rainfall_monthly r
  ON w.block_id = r.block_id
 AND date_trunc('month', w.obs_date) = r.month
JOIN wellcast.block b
  ON w.block_id = b.block_id;
```

---

## Phase 3: Modelling (Day 3, Thu 26 Nov)

- [ ] **Develop locally first** (laptop or notebook) so iteration is fast and free
- [ ] Split **by time**: train on earlier years, test on the most recent. No random splits
- [ ] Build the baseline (same season last year) and record its MAE
- [ ] Train XGBoost and compare against the baseline
- [ ] Add quantile models (10th and 90th percentile) for the confidence range
- [ ] Define risk thresholds (Safe / Watch / Critical) and check them against known extraction categories
- [ ] Run **one final SageMaker training job** using `ml/train.py`, so the AWS build genuinely uses SageMaker
- [ ] **Stop or delete all SageMaker resources** afterwards (notebooks, endpoints)

**Exit check:** the model beats the baseline, or you can honestly explain where it doesn't.

**Fallback:** if XGBoost doesn't beat the baseline, ship the baseline plus trend with clearly labelled uncertainty. An honest simple model scores better than an unexplained complex one.

```python
# ml/train.py (sketch)
import argparse, pandas as pd, xgboost as xgb

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--train", default="/opt/ml/input/data/train")
    p.add_argument("--model-dir", default="/opt/ml/model")
    args = p.parse_args()

    df = pd.read_parquet(args.train)
    X = df.drop(columns=["target_depth_next", "block_id", "obs_date"])
    y = df["target_depth_next"]

    model = xgb.XGBRegressor(n_estimators=300, max_depth=5,
                             learning_rate=0.05, subsample=0.8)
    model.fit(X, y)
    model.save_model(f"{args.model_dir}/model.json")
```

---

## Phase 4: Forecasts and scenarios (Day 4 morning, Fri 27 Nov)

- [ ] Generate next-season forecasts for every block
- [ ] Re-run with rainfall at **100%, 90%, 80% and 70%** of normal to create scenarios
- [ ] Write results to `forecasts/` as Parquet and register an Athena table
- [ ] Export one JSON file per block (or per district) for fast serving
- [ ] Write short advice text per risk class in English plus Hindi/Marathi

**Exit check:** you can query "top 10 at-risk blocks" in Athena and see sensible output.

---

## Phase 5: Backend API (Day 4 afternoon)

- [ ] Create a Lambda function (Python) that reads forecast JSON from S3
- [ ] Create API Gateway routes:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/blocks` | List blocks with current risk class |
| `GET` | `/blocks/{id}/forecast` | Forecast, confidence range, risk class |
| `GET` | `/blocks/{id}/history` | Historical water level and rainfall |
| `GET` | `/rankings` | Top at-risk blocks (planner view) |
| `GET` | `/health` | Health check |

- [ ] Enable **CORS** for your CloudFront domain
- [ ] Scope the Lambda IAM role to exactly the bucket it needs
- [ ] Test every route with `curl` or Postman

**Exit check:** every endpoint returns correct JSON, including a clear error for an unknown block.

```python
# backend/lambda_handler.py (sketch)
import json, os, boto3

s3 = boto3.client("s3")
BUCKET = os.environ["FORECAST_BUCKET"]

def handler(event, context):
    block_id = event["pathParameters"]["block_id"]
    scenario = (event.get("queryStringParameters") or {}).get("scenario", "normal")
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=f"api/{scenario}/{block_id}.json")
        body = obj["Body"].read().decode()
        status = 200
    except s3.exceptions.NoSuchKey:
        body, status = json.dumps({"error": "Block not found"}), 404
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"},
        "body": body,
    }
```

---

## Phase 6: Frontend (Day 4 evening to Day 5, Sat 28 Nov)

Build in this order so you always have something demoable:

- [ ] 1. Block selector and a basic risk badge using live API data
- [ ] 2. Map with colour-coded blocks
- [ ] 3. Forecast chart with the confidence band
- [ ] 4. Scenario slider
- [ ] 5. Advice panel and language toggle
- [ ] 6. Mobile layout check (many real users will be on phones)
- [ ] 7. Planner view: ranked at-risk blocks

**Deploy**
- [ ] `npm run build`
- [ ] Sync `dist/` to a **private** S3 bucket
- [ ] Create a CloudFront distribution with Origin Access Control
- [ ] Set the default root object to `index.html` and handle SPA routing with an error response
- [ ] Note the `*.cloudfront.net` URL and test it from a different device and network

**Exit check:** a stranger can open the URL on their phone and use it without help.

---

## Phase 7: QuickSight planner dashboard (Day 5 evening)

- [ ] Check the current QuickSight sign-up terms and trial length in your account first
- [ ] Connect it to the Athena forecast table
- [ ] Build visuals: ranked blocks, district risk distribution, trend lines
- [ ] **Take screenshots and a screen recording immediately**, in case access lapses before Demo Day
- [ ] Treat this as a bonus view: the React app is the primary, always-on interface

---

## Phase 8: Hardening (Day 5 night to Day 6 morning)

- [ ] Add error and empty states in the UI (no data, API down)
- [ ] Set Lambda timeouts and sensible logging in CloudWatch
- [ ] Re-check the budget alert and confirm nothing billable is left running
- [ ] Review IAM and make sure **no keys are in the repo**
- [ ] Add a visible data-sources and limitations note in the app

---

## Phase 9: Submission assets (Day 6, Sun 29 Nov)

- [ ] **Idea Brief:** problem, who it's for, how it works, impact
- [ ] **Build Summary:** AWS services used and why (reuse the README table)
- [ ] **Demo video, under 3 minutes** (script below)
- [ ] Finalise the README and add architecture images to `docs/`
- [ ] Make the GitHub repo public
- [ ] Create **one Google Drive folder** containing:
  - [ ] Idea brief
  - [ ] Build summary
  - [ ] Prototype URL
  - [ ] Code repository link
  - [ ] Demo video
- [ ] Set sharing so the link works for anyone with it
- [ ] Open the folder link in an incognito window to confirm it works

### Demo video script (under 3 minutes)

| Time | Content |
|---|---|
| 0:00 to 0:25 | The problem: a farmer deciding whether to drill deeper, with no warning |
| 0:25 to 0:45 | Who it helps: farmers and planners |
| 0:45 to 1:45 | Live demo: pick a block, see risk and forecast, move the rainfall slider |
| 1:45 to 2:15 | Planner view: ranked at-risk blocks |
| 2:15 to 2:40 | Architecture: S3 → Athena → SageMaker → Lambda / CloudFront / QuickSight, and why each |
| 2:40 to 3:00 | Impact and next steps: scale to more states |

---

## Phase 10: Submit (Day 6 night or Day 7, Mon 30 Nov)

- [ ] **Team Leader** submits on the Techfest site: Drive folder link, Builder Center alias, idea and live URL
- [ ] Aim to submit on the **evening of 29 Nov**, leaving 30 Nov as a pure buffer
- [ ] Don't wait for 11:59 PM on the 30th
- [ ] Keep a screenshot of the confirmation

---

## After submission

| When | What to do |
|---|---|
| 1 to 5 Dec | Don't change the live system. Watch the portal and email for updates |
| By 5 Dec | Round 1 results are announced. Check techfest.org |
| Before 17 Dec | Re-test the live URL regularly, check the AWS bill, rehearse the 3-minute demo |
| 17 Dec | Demo Day at IIT Bombay: 3 minutes live demo plus 2 minutes of judge Q&A |

---

## Prepare for judges' Q&A

Have an honest answer ready for each:

- How did you obtain the data, and what are its limits?
- How accurate is the model compared to a simple baseline?
- Why did you choose each AWS service?
- How would it scale to other states?
- Who would actually use this, and have you talked to a real user?
- What does it cost to run?

---

## Team roles (if you're not solo)

| Role | Owns |
|---|---|
| Data and ML | Phases 1 to 4 |
| Backend and AWS | Phases 5 and 8, IAM, budget |
| Frontend | Phases 6 and 7 |
| Storytelling and docs | Phase 9, video, Q&A prep |

**If you're solo,** prioritise in this order: working data → forecast → live URL → video. Cut QuickSight first if time runs short.

---

## Biggest risks

1. **Data availability and cleanliness:** settle it on Day 1 and don't start building until it's confirmed.
2. **Unexpected AWS cost:** keep the budget alert, train then stop, and serve precomputed results.
3. **Scope creep:** protect the core path of data → forecast → live map. Extras (languages, scenarios, QuickSight) come after.
4. **Late submission:** submit the evening before the deadline.

---

## Cost guardrails

- Set an **AWS Budgets** alert on day one
- Use SageMaker **training jobs**, not always-on endpoints or notebooks left running
- **Precompute** forecasts and scenarios so the live app needs no model hosting
- Store data as **Parquet** and use an Athena workgroup with a per-query scan limit
- Cache Lambda responses and CloudFront assets
- Verify QuickSight access will still be active on Demo Day
- Check the exact free-tier and credit terms in your own AWS account, as they change
