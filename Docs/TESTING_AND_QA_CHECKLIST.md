# WellCast: Testing Strategy, Hardening, Submission & Demo Day Playbook

This document covers layer-by-layer testing (**Phases 1–6**), production hardening (**Phase 8**), final hackathon packaging & submission (**Phases 9–10**), the 3-minute demo video production script, and the **17 Dec 2026 IIT Bombay Demo Day** Judge Q&A preparation guide.

---

## 1. Layer-by-Layer Testing & Verification Suite

### Layer 1: Data Cleaning & Schema Verification (Phase 1)
- [ ] `data/scripts/fetch_and_clean.py` runs end-to-end deterministically from clean inputs without manual edits.
- [ ] Zero duplicate `(block_id)` in `blocks.parquet`, zero duplicate `(block_id, month)` in `rainfall_monthly.parquet`, zero duplicate `(block_id, obs_date)` in `water_level.parquet`.
- [ ] All `depth_mbgl` values satisfy `0.0 <= depth_mbgl <= 300.0`; all `rainfall_mm >= 0.0`.
- [ ] Join match rate between `water_level` and `rainfall_monthly` is **>= 90%** (log exact % in `ai_logs/`).
- [ ] Every dataset in `raw/` is documented with URL & licence in `DATA_SOURCES.md`.

### Layer 2: Athena Feature & Anti-Leakage Verification (Phase 2)
- [ ] All 3 raw tables queryable via Athena under workgroup `wellcast-wg` (`100 MB` scan limit enforced).
- [ ] Anti-leakage SQL checks (`ARCHITECTURE_AND_DATA_SPEC.md` §6) confirm:
  - `0` duplicate `(block_id, obs_date)` rows in `wellcast.features`.
  - `obs_date < target_obs_date` on 100% of training rows, with season gap `5–7` months.
  - Spot-check 5 blocks manually by inspecting consecutive years side by side.

### Layer 3: ML Validation & Scenario Sanity Checks (Phases 3–4)
- [ ] Time-based split strictly separates train/val/test years (assert `max(train.target_obs_date) < min(test.target_obs_date)`).
- [ ] Holdout metrics logged in `ml/metrics.json` comparing Seasonal Naive vs XGBoost (MAE, RMSE, Skill Score %).
- [ ] Quantile interval validation: `0.0 <= lower_bound <= predicted_depth_mbgl <= upper_bound` holds on 100% of forecast rows; empirical holdout coverage % recorded.
- [ ] Scenario monotonicity check: across blocks, average `predicted_depth_mbgl` increases (or stays non-decreasing) from `normal` (100%) -> `minus10` -> `minus20` -> `minus30`.
- [ ] SageMaker training job reached `Completed` status; `list-endpoints`, `list-notebook-instances`, and `list-apps` are all empty.
- [ ] Athena query `SELECT * FROM wellcast.v_top_at_risk_normal LIMIT 10` returns sensible high-stress blocks.

### Layer 4: Backend API Smoke Suite (Phase 5)
Run against live API Gateway Base URL (`$API = "https://<api-id>.execute-api.ap-south-1.amazonaws.com/prod"`):

```powershell
# 1. Health check (expect 200 + status=ok)
curl.exe -i "$API/health"

# 2. List blocks (expect 200 + non-empty blocks array)
curl.exe -s "$API/blocks?state=MH" | ConvertFrom-Json | Select-Object state, count

# 3. Valid forecast normal & drought scenario (expect 200)
curl.exe -i "$API/blocks/MH-PUN-012/forecast?scenario=normal"
curl.exe -i "$API/blocks/MH-PUN-012/forecast?scenario=minus30"

# 4. Unknown block ID (expect 404 + clean JSON error)
curl.exe -i "$API/blocks/MH-ZZZ-999/forecast?scenario=normal"

# 5. Invalid scenario param (expect 400 + clean JSON error)
curl.exe -i "$API/blocks/MH-PUN-012/forecast?scenario=invalid"

# 6. Historical water levels + rainfall (expect 200)
curl.exe -i "$API/blocks/MH-PUN-012/history"

# 7. Planner rankings (expect 200 + sorted risk_score descending)
curl.exe -i "$API/rankings?state=MH&limit=10"

# 8. CORS preflight check from CloudFront origin (expect Access-Control-Allow-Origin header)
curl.exe -i -X OPTIONS "$API/blocks" -H "Origin: https://<DIST_ID>.cloudfront.net" -H "Access-Control-Request-Method: GET"
```

### Layer 5: Frontend End-to-End, Mobile & Resilience Checks (Phases 6 & 8)
- [ ] Live `https://<dist-id>.cloudfront.net` opens over HTTPS with valid certificate and zero console errors.
- [ ] Tested on a **physical smartphone on mobile cellular data** (different device & network) in Incognito mode.
- [ ] Mobile viewport (`375px` width) has zero horizontal scroll, readable map legend, and usable scenario slider.
- [ ] Clicking map blocks, using district/block dropdown, moving rainfall slider (`100% -> 70%`), toggling EN/HI/MR, and opening Planner View all work smoothly.
- [ ] Direct navigation to any SPA sub-route (e.g., `/planner`) followed by browser refresh returns `200 OK` (CloudFront SPA error mapping works).
- [ ] **Chaos / Error-State Tests:**
  - Block with `"Insufficient Data"` displays clear honest notice instead of broken chart or fake numbers.
  - Simulating offline network (DevTools -> Offline) shows a friendly retry banner instead of a blank white screen.
- [ ] Visible **"Data Sources & Limitations"** button/footer displays full dataset attribution and caveats.

---

## 2. Phase 8 Hardening Sign-Off Checklist

- [ ] **UI Hardening:** Loading skeletons, empty states, offline error banner, imputed-data badge, and limitations disclaimer deployed & verified.
- [ ] **Observability:** CloudWatch Log Group retention set to 14 days; Lambda logs structured request metadata & errors; CloudWatch Error Alarm active.
- [ ] **IAM & Storage Security:** Both S3 buckets have `Block Public Access = ON`; CloudFront uses OAC; Lambda IAM role scoped strictly to `s3:GetObject` on `api/*`; API Gateway CORS locked to CloudFront domain.
- [ ] **Secret Scan Passed:** `git grep -E "(AKIA[0-9A-Z]{16}|aws_secret_access_key|BEGIN PRIVATE KEY)"` returns 0 matches; no `.env` or credential CSVs in working tree or git history.
- [ ] **AWS Cost Check Passed:** Idle resource audit script returns empty lists for SageMaker/EC2/RDS; AWS Budgets alert confirmed active; Billing Cost Explorer reviewed.

---

## 3. Phase 9–10 Hackathon Submission Checklist

### 3.1 Deliverables Checklist (Target Complete: Sun 29 Nov Afternoon)
- [ ] **AWS Builder Center:** Profile active, alias recorded, **student verification approved**.
- [ ] **Public GitHub Repository:**
  - `README.md` finalized with live CloudFront URL, Demo Video link, Builder Center alias, Team names, complete sections 1–16, and `Docs/architecture.png`.
  - `DATA_SOURCES.md` complete with verified URLs & licences.
  - `LICENSE` present.
  - Repository set to **Public** and verified in an incognito browser.
- [ ] **Idea Brief (`Docs/idea-brief.md` -> PDF):** Concise, visual, problem + users + how it works + real metrics + impact.
- [ ] **Build Summary (`Docs/build-summary.md` -> PDF):** AWS service justification table + architecture diagram + ML evaluation results + cost guardrails.
- [ ] **Demo Video (< 3:00 strictly):** Crisp audio, 1080p screen recording of live deployed CloudFront app (not `localhost`!).
- [ ] **Single Google Drive Folder (`WellCast_CampusToCloud_Submission/`):**
  - `01_WellCast_Idea_Brief.pdf`
  - `02_WellCast_Build_Summary.pdf`
  - `03_WellCast_Demo_Video.mp4`
  - `04_WellCast_Links.pdf` (Live CloudFront URL, Public GitHub Repo URL, AWS Builder Center Alias, Techfest Team ID)
  - `05_Screenshots/` (Architecture PNG, Mobile UI screenshot, Planner View, QuickSight backup screenshots)
- [ ] **Incognito Link Check:** Folder set to `Anyone with the link -> Viewer`; opened in a logged-out incognito window on a separate device to confirm every file opens and the video streams cleanly.
- [ ] **Techfest Submission (`T10.1`):** Submitted by **Team Leader** on evening of **Sun 29 Nov 2026**; confirmation receipt screenshot saved!

---

## 4. Demo Video Production Script (Target: 2:45 — Strictly Under 3:00)

| Time | Duration | Visual on Screen | Voiceover Talking Points |
|---|---|---|---|
| `0:00–0:25` | 25s | Title card + relatable rural farmer / dry borewell graphic + Maharashtra groundwater stress stat | *"Every year across India, farmers spend lakhs drilling deeper borewells without knowing whether the aquifer beneath them will survive the next season. Data exists across government portals, but it's backward-looking and scattered. Meet WellCast — seeing groundwater stress before it hits."* |
| `0:25–0:45` | 20s | Split slide: Farmer persona (simple risk + crop advice) & District Planner persona (ranked blocks + scenarios) | *"WellCast serves two users: farmers who need a clear Safe/Watch/Critical warning and crop advice in their own language, and block/district planners who need ranked priorities for water tankers and recharge structures."* |
| `0:45–1:45` | 60s | **Live CloudFront URL** (show HTTPS bar!): select a stressed Maharashtra block on the Leaflet map -> show Risk Badge + inverted Forecast Chart with P10–P90 confidence band -> slide Rainfall Scenario from 100% down to 70% -> toggle Hindi/Marathi advice | *"Here is our live prototype running on CloudFront. Picking `<Block Name>` shows historical monitoring-well levels and our next-season forecast with an 80% confidence band. Watch what happens if monsoon rainfall falls 20% or 30% below normal — risk shifts immediately because scenarios are precomputed, with plain-language advice available in English, Hindi, and Marathi."* |
| `1:45–2:15` | 30s | Switch to **Planner View** (ranked at-risk table + district filter) + 8-second flash of QuickSight backup / Athena view if built | *"For district planners, our Planner View ranks the most vulnerable blocks across the state, lets officers filter by district or drought scenario, and download the shortlist for targeted recharge allocation."* |
| `2:15–2:40` | 25s | Clean `Docs/architecture.png` diagram walking left-to-right + real Baseline vs XGBoost MAE metric callout | *"Under the hood on AWS Mumbai (`ap-south-1`): public CGWB and IMD data land in S3 as Parquet, Glue and Athena engineer zero-leakage features, a short-lived SageMaker job trains our XGBoost and quantile models beating the seasonal-naive baseline, and precomputed JSON is served via Lambda, API Gateway, and CloudFront OAC — keeping monthly cost under \$1 with zero idle servers."* |
| `2:40–2:55` | 15s | Impact summary + multi-state India roadmap + closing card with Live URL & GitHub link | *"Starting with Maharashtra, the exact same serverless pipeline scales block-by-block across all Indian states on public CGWB and IMD feeds. Thank you — try WellCast live at the link below."* |

---

## 5. Demo Day (17 Dec 2026) Runbook & Judge Q&A Prep

### Pre-Demo Day Checklist (6 Dec – 16 Dec)
- [ ] Re-verify live CloudFront URL & `/health` on 6 Dec, 12 Dec, and 16 Dec.
- [ ] Check AWS Billing Console on 15 Dec to confirm actual spend matches expectations.
- [ ] Keep offline backup ready on laptop: `03_WellCast_Demo_Video.mp4` + high-res screenshots in case auditorium Wi-Fi drops.
- [ ] Rehearse **3-minute live demo** with a stopwatch until it consistently finishes at **2:45–2:50** (never get cut off mid-sentence!).

### Honest Answers for the 6 Expected Judge Questions

1. **"How did you obtain the data, and what are its limits?"**
   - Cite exact verified portals from `DATA_SOURCES.md` (CGWB/India-WRIS groundwater wells, IMD/data.gov.in monthly rainfall, CGWB extraction assessment).
   - State limits transparently: monitoring wells are sampled semi-annually (not real-time IoT), rainfall may be district-mapped where block gauges aren't public, and blocks with `<4` seasons are explicitly labelled `"Insufficient Data"` rather than fabricated.

2. **"How accurate is the model compared to a simple baseline?"**
   - Quote the exact time-split holdout numbers from `ml/metrics.json`: *"We evaluated strictly on a future holdout year — zero random splits. Our seasonal-naive baseline achieved `X.XX m` MAE; our XGBoost model achieved `Y.YY m` MAE (`Z%` improvement), with P10–P90 quantile bounds capturing `C%` of actual outcomes."* (If fallback model was used, state why honestly — judges deeply respect scientific rigor!)

3. **"Why did you choose each AWS service?"**
   - Emphasize **serverless + zero-idle-cost discipline**: S3 + Parquet + Glue + Athena avoids paying for a 24/7 database; SageMaker Training Jobs avoid 24/7 GPU/endpoint billing; precomputed S3 JSON + Lambda + API Gateway HTTP API + CloudFront OAC delivers sub-200 ms responses for farmers on 3G/4G phones at near-zero cost.

4. **"How would it scale to other states?"**
   - The data schema (`block_id = <STATE2>-<DIST3>-<SEQ3>`), Athena SQL, SageMaker training script, and React map are **state-agnostic**. Onboarding a new state requires adding its CGWB/IMD files and name alias map, re-running Glue + Athena + SageMaker (partitioned by `state_code`), and syncing the new `<STATE>_blocks.geojson` + JSONs to S3. EventBridge automates seasonal refreshes.

5. **"Who would actually use this, and have you talked to a real user?"**
   - Be 100% honest: if you spoke with a farmer, Krishi Vigyan Kendra (KVK) advisor, NGO water worker, or district groundwater officer during the week, share one concrete insight they gave (e.g., needing Marathi/Hindi advice and simple 3-tier badges instead of raw `mbgl` charts). If you haven't yet before submission, aim to do 2–3 quick 10-minute user feedback calls before 17 Dec Demo Day!

6. **"What does it cost to run?"**
   - Cite your actual AWS Cost Explorer number (target `< $1/month` for prototype scale) and explain unit economics at national scale (~7,000 blocks across India = ~50 MB Parquet + ~28,000 tiny 2 KB JSON files = ~60 MB in S3 + 1 periodic 5-minute SageMaker job per season -> **still only a few dollars per month** for the entire country!).
