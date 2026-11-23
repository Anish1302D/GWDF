# WellCast: Machine Learning, Uncertainty, Risk & Scenario Specification

This document specifies the complete ML methodology for **Phase 3 (Modelling)** and **Phase 4 (Forecasts & Scenarios)**, ensuring scientific honesty, zero temporal leakage, interpretable risk thresholds, and low-cost AWS SageMaker execution.

---

## 1. Domain Note & Problem Formulation

> **Crucial Hydrogeological Sign Convention:**  
> Groundwater level is measured in **metres below ground level (`mbgl`)**.
> - **Lower `mbgl` (e.g., `4.5 m`)** = shallower water table = **healthier / more water available**.
> - **Higher `mbgl` (e.g., `22.8 m`)** = deeper water table = **more depleted / higher stress**.
> - **Positive change (`+1.8 m`)** = water level dropped deeper (**worsening**).
> - **Negative change (`-1.2 m`)** = water level rose closer to surface (**recharging / improving**).
>
> Always preserve this convention consistently in SQL, ML targets, quantile bounds (`lower_bound` = shallower/optimistic P10; `upper_bound` = deeper/pessimistic P90), and inverted Y-axis charts in the UI!

### Prediction Task
- **Unit of Prediction:** One administrative Block (`block_id`, or District if fallback `D-02` triggered) for the **next upcoming season** (`t+1`, e.g., predicting upcoming Pre-Monsoon depth from latest Post-Monsoon state + trailing rainfall).
- **Primary Target (`y`):** `target_depth_next` (continuous, `>= 0` in `mbgl`).  
  *(Optional experiment in Phase 3: compare predicting direct `target_depth_next` vs residual `delta = target_depth_next - baseline_pred_next`; keep whichever yields lower holdout MAE!)*

---

## 2. Feature Catalog & Anti-Leakage Audit

| Feature Name | Type | Formula / Source | Physical Meaning | Leakage Audit |
|---|---|---|---|---|
| `depth_mbgl` | `float` | Observed depth at `t` | Current aquifer level | Safe (`<= t`) |
| `prev_depth_mbgl` | `float` | Observed depth at `t-1` | Same season last year (semi-annual) | Safe (`< t`) |
| `prev_change_mbgl` | `float` | `depth(t) - depth(t-1)` | Seasonal drawdown or monsoon recharge amplitude | Safe (`<= t`) |
| `same_season_last_year_depth` | `float` | Observed depth at `t-2` | Prior year reference for current season | Safe (`< t`) |
| `yoy_change_mbgl` | `float` | `depth(t) - depth(t-2)` | Recent 1-year net depletion velocity | Safe (`<= t`) |
| `depth_trend_5yr` | `float` | `(depth(t) - depth(t-5yr)) / years` | Multi-year structural decline rate (`mbgl/yr`) | Safe (`<= t`) |
| `rain_3m_mm` | `float` | Sum of rainfall `[t-2m .. t]` | Immediate short-term recharge pulse | Safe (`<= t`) |
| `rain_6m_mm` | `float` | Sum of rainfall `[t-5m .. t]` | Full monsoon / half-year rainfall total | Safe (`<= t`) |
| `rain_12m_mm` | `float` | Sum of rainfall `[t-11m .. t]` | Annual rainfall context | Safe (`<= t`) |
| `rain_departure_6m_pct` | `float` | `(rain_6m - normal_6m) / normal_6m * 100` | Relative drought/surplus anomaly | Safe (`<= t`) |
| `extraction_stage_code` | `int` | `0=Safe, 1=Semi-Crit, 2=Crit, 3=Over-Exp, -1=Unk` | Chronic human pumping pressure | Static CGWB assessment (note assessment year transparently) |
| `season_code` | `int` | `0=Pre-Monsoon, 1=Post-Monsoon` | Identifies which half-cycle is being forecast next | Safe (deterministic calendar) |

**Explicitly Excluded from `X`:** `block_id`, `obs_date`, `year`, `target_obs_date`, `target_depth_next`, `well_count`, `is_imputed`.

---

## 3. Strict Time-Based Evaluation Protocol

**Never use `train_test_split(..., shuffle=True)` or random K-Fold on time-series groundwater data** (that leaks future weather & aquifer states across nearby years and produces artificially optimistic MAE).

### Split Design
Assuming available historical years run from `Y_min` to `Y_max` (e.g., `2016` to `2025`):

| Split | Target Date Range | Purpose |
|---|---|---|
| **Train** | `target_year <= Y_max - 2` | Fit model parameters |
| **Validation** | `target_year == Y_max - 1` | Early stopping & hyperparameter selection |
| **Holdout Test** | `target_year == Y_max` | Unbiased final benchmark reported in `README.md`, `build-summary.md`, and Judge Q&A |
| **Final Production Fit** | All rows `target_depth_next IS NOT NULL` (`<= Y_max`) | Retrain with locked hyperparameters in SageMaker to generate upcoming `Y_max + 1` forecasts |

*(If only 4–5 years exist total, use `<= Y_max - 1` for Train/CV with expanding-window folds and `Y_max` as final Holdout Test.)*

### Metrics to Report in `ml/metrics.json`
1. **MAE (`mbgl`)** — primary metric (directly interpretable: "average forecast error in metres").
2. **RMSE (`mbgl`)** — captures sensitivity to large outlier errors.
3. **Skill Score vs Baseline (%)** — `(MAE_baseline - MAE_model) / MAE_baseline * 100`.
4. **Stratified MAE** — broken down by season (`pre-monsoon` vs `post-monsoon`) and by CGWB extraction stage (`Safe` vs `Critical/Over-Exploited`).
5. **Quantile Interval Coverage (%)** — fraction of holdout observations falling inside `[lower_bound (P10), upper_bound (P90)]` (target: `75%`–`85%` for a nominal 80% interval).

---

## 4. Model Specifications

### 4.1 Model 0: Seasonal Naive Baseline (Mandatory Benchmark)
- **Rule:** Predict next season's depth as the exact depth observed in the **same season one year prior** (`baseline_pred_next = prev_depth_mbgl` for semi-annual data).
- **Why:** Groundwater has strong monsoon seasonality; predicting "last year's same season" is surprisingly strong and provides a rigorous honesty bar for ML.

### 4.2 Model 1: Main XGBoost Point Forecast (`model_p50.json`)
- **Objective:** `reg:squarederror` (or `reg:absoluteerror` if heavy outliers exist; test both on Validation).
- **Recommended Conservative Hyperparameters (to prevent overfitting on small tabular datasets):**
  ```python
  xgb.XGBRegressor(
      n_estimators=400,
      max_depth=4,              # Keep shallow (3-5) to prevent memorizing block quirks
      learning_rate=0.04,
      subsample=0.8,
      colsample_bytree=0.8,
      min_child_weight=5,
      reg_alpha=0.5,
      reg_lambda=2.0,
      random_state=42,
      early_stopping_rounds=30,
  )
  ```
- **Monotonicity Consideration (Recommended):** Test setting `monotone_constraints` so that **higher rainfall (`rain_6m_mm`, `rain_departure_6m_pct`) has a non-positive effect (`-1`) on `depth_mbgl`** (more rain -> shallower/equal depth, never deeper). This guarantees physically coherent Scenario Slider behavior when users slide rainfall from 100% down to 70%!

### 4.3 Model 2: Uncertainty Quantification (`model_p10.json` & `model_p90.json`)
- **Algorithm:** XGBoost Quantile Regression (`objective="reg:quantileerror"` in XGBoost >= 2.0):
  - `model_p10`: `quantile_alpha=0.10` (optimistic / shallower water bound)
  - `model_p90`: `quantile_alpha=0.90` (pessimistic / deeper stress bound)
- **Post-Processing Guardrails (mandatory on every prediction row):**
  1. Floor all depth predictions at `0.0 mbgl` (`max(0.0, val)`).
  2. Enforce non-crossing quantiles:
     ```python
     lower_bound = min(pred_p10, pred_p50)
     upper_bound = max(pred_p90, pred_p50)
     ```
  3. Enforce minimum physical uncertainty floor (e.g., if `upper_bound - lower_bound < 0.2`, pad symmetrically by `0.1 m` so the UI confidence band never collapses to a misleading razor-thin line).

### 4.4 Honest Fallback Specification
If after tuning, XGBoost does **not** beat Seasonal Naive on the Holdout Test year:
1. Log the exact comparison honestly in `ml/metrics.json` and `ai_logs/`.
2. Ship **Seasonal Naive + Damped 5-Year Trend**: `pred = same_season_last_year + 0.5 * clip(depth_trend_5yr, -2.0, 2.0) + rain_sensitivity_adjustment`.
3. Compute `lower_bound` / `upper_bound` from the empirical 10th and 90th percentiles of holdout residuals.
4. Explain transparently in `README.md` and Demo Q&A why the simpler model won on limited historical rows.

---

## 5. Risk Classification & Calibration (`ml/risk_rules.py`)

A block's risk class combines **how deep the water is predicted to be** AND **how fast it is falling** (because a shallow aquifer dropping 3 m/year is in trouble, just as a 20 m deep aquifer dropping slowly is in trouble).

### Initial Thresholds (Calibrate Against Target State Distribution on Day 3)
Let:
- `d_pred` = `predicted_depth_mbgl`
- `yoy_delta` = `predicted_depth_mbgl - same_season_prev_year_depth` (positive = worsening depletion)
- `trend_5yr` = `depth_trend_5yr` (`mbgl/yr`)

| Risk Class | Criteria (OR logic — triggers highest applicable severity) | Color Token | Farmer Interpretation |
|---|---|---|---|
| **Critical** | `d_pred >= 18.0` OR (`d_pred >= 12.0` AND `yoy_delta >= 1.5`) OR `yoy_delta >= 2.5` OR (`trend_5yr >= 1.0` AND `d_pred >= 10.0`) | `#DC2626` (Red) | Rapid decline or severely deep aquifer; high drought/borewell failure risk |
| **Watch** | `d_pred >= 10.0` OR `yoy_delta >= 0.75` OR `trend_5yr >= 0.4` | `#D97706` (Amber) | Notable depletion pressure; conserve water and favor low-water crops |
| **Safe** | Otherwise (stable or recovering depth `< 10.0 m` and `yoy_delta < 0.75`) | `#16A34A` (Green) | Aquifer relatively stable; maintain standard water budgeting |
| **Insufficient Data** | Fewer than 4 valid historical observations | `#6B7280` (Gray) | Not enough monitoring history for a reliable forecast |

### Continuous `risk_score` (0 to 100) for Deterministic Planner Ranking
```python
depth_component = min(max(d_pred / 25.0, 0.0), 1.0) * 45.0
yoy_component   = min(max(yoy_delta / 3.0, 0.0), 1.0) * 35.0
trend_component = min(max(trend_5yr / 1.5, 0.0), 1.0) * 20.0
risk_score      = round(depth_component + yoy_component + trend_component, 1)
```

### Mandatory Calibration Sanity Check (Task `T3.5`)
- Cross-tabulate `risk_class` (under `normal` scenario) against official CGWB `extraction_stage`.
- Verify that blocks marked `Critical` / `Over-Exploited` by CGWB predominantly appear in WellCast's `Watch` or `Critical` tiers. Adjust depth percentiles (`P70`/`P85` of state depth distribution) if Maharashtra's basaltic hard-rock aquifers sit shallower (e.g., 6–15 m vs deep alluvial aquifers in Punjab/Rajasthan at 20–40 m) and document the calibrated thresholds in `ml/metrics.json`!

---

## 6. Precomputed Rainfall Scenario Engine (Phase 4)

The React UI features a **"What if rainfall is 10–30% below normal?"** slider. To make this instant and free at runtime, `ml/make_forecasts.py` batch-scores **4 deterministic scenarios** for every block:

| Scenario Key | Rainfall Multiplier (`k`) | Feature Perturbation Applied to Latest Inference Row |
|---|---|---|
| `normal` | `1.00` (100%) | Use observed/baseline rainfall (`rain_3m`, `rain_6m`, `rain_12m`, `rain_departure_6m_pct` as-is or set to 100% normal — pick one convention and label clearly in UI: e.g., `k * normal_rainfall`) |
| `minus10` | `0.90` (90% of normal) | `rain_6m_s = 0.90 * rain_6m_normal_mm`; `rain_3m_s = 0.90 * rain_3m_normal_mm`; `rain_departure_6m_pct = -10.0` |
| `minus20` | `0.80` (80% of normal) | `rain_6m_s = 0.80 * rain_6m_normal_mm`; `rain_3m_s = 0.80 * rain_3m_normal_mm`; `rain_departure_6m_pct = -20.0` |
| `minus30` | `0.70` (70% of normal) | `rain_6m_s = 0.70 * rain_6m_normal_mm`; `rain_3m_s = 0.70 * rain_3m_normal_mm`; `rain_departure_6m_pct = -30.0` |

**Scenario Sanity Assertion (Mandatory in `make_forecasts.py`):**
For every block, verify across scenarios:
`predicted_depth(normal) <= predicted_depth(minus10) <= predicted_depth(minus20) <= predicted_depth(minus30)` (within minor tree-split tolerance, or guaranteed strictly if `monotone_constraints` is enabled on rainfall features!).

---

## 7. AWS SageMaker Script-Mode Training Specification (Task `T3.6`)

To legitimately leverage managed AWS SageMaker while staying near \$0 cost:

- **Mode:** Managed Short-Lived **Training Job** (never Notebook Instance left idle, never Studio Space left idle, never real-time Endpoint).
- **Instance Type:** `ml.m5.large` (CPU — tabular XGBoost on thousands of rows finishes in **< 2 minutes**, costing only a few cents or covered by credits).
- **Framework Container:** AWS SageMaker built-in `xgboost` framework container (`framework_version="1.7-1"` or custom script mode with `sagemaker.xgboost.XGBoost` estimator).
- **Inputs / Outputs:**
  - Input channel `train`: `s3://<DATA_BUCKET>/curated/ml_train/`
  - Output path: `s3://<DATA_BUCKET>/models/`
- **Script Contract (`ml/train.py`):**
  - Reads `--train` (`/opt/ml/input/data/train`) and writes to `--model-dir` (`/opt/ml/model`):
    - `model_p50.json`
    - `model_p10.json`
    - `model_p90.json`
    - `metrics.json` (train/val/test MAE, baseline MAE, coverage %, feature importances, calibrated risk thresholds)
- **Launch Script (`ml/launch_sagemaker_job.py`):**
  - Launches training job via `boto3` / `sagemaker` SDK with `max_run=600` (10-minute hard safety cap!).
  - Waits for `Completed`, downloads `model.tar.gz` locally or reads directly in `make_forecasts.py`.
- **Mandatory Post-Job Cleanup Check (`T3.7`):**
  ```powershell
  aws sagemaker list-endpoints --region ap-south-1 --profile wellcast
  aws sagemaker list-notebook-instances --region ap-south-1 --profile wellcast
  aws sagemaker list-apps --region ap-south-1 --profile wellcast
  ```
  All three commands **must return empty lists**.
