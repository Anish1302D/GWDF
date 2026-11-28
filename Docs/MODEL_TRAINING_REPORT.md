# WellCast Pan-India: AI Model Training & Validation Report

> **Active Model Artifact:** `xgb-dual-specialist-cqr-v2-20261128` (`ml/artifacts_local/`)  
> **National Scope:** **35 Indian States & Union Territories** · **675 Districts** · **5,795 Sub-Districts / Blocks** (`3,998` actively forecasted blocks; `1,797` sparse/unmonitored blocks transparently marked `Insufficient Data`)  
> **Raw Observations Processed:** **2,035,145** official CGWB & GSDA monitoring-well readings + **28,896** NASA POWER agroclimatology grid-months (`172` cells across India)

---

## 1. Pan-India ML Architecture

WellCast models **6-month seasonal residual change over the Seasonal Naive baseline** (`y_delta = target_depth_next - prev_depth_mbgl`) across **`45,964` leak-free block-season transitions** (`72,385` total causal feature rows) using:

1. **Global Residual Monotone XGBoost (`model_p50.json`):** `90` trees (`objective = reg:absoluteerror`, `max_depth = 6`, `min_child_weight = 24`, `lr = 0.025`, `L1 = 2.0`, `L2 = 8.0`) with **strictly negative (`-1`) monotone constraints** on all 7 precipitation & drought-anomaly features (`3m`, `6m`, `12m`, `24m` totals and departures).
2. **Pre-Monsoon Drawdown Specialist (`model_pre_p50.json`):** `76` trees dedicated to `Post-Monsoon (Nov) -> Pre-Monsoon (May)` dry-season drawdown (`w_global = 0.75`, `w_specialist = 0.40`).
3. **Post-Monsoon Recharge Specialist (`model_post_p50.json`):** `76` trees dedicated to `Pre-Monsoon (May) -> Post-Monsoon (Nov)` monsoon aquifer recharge (`w_specialist = 0.95`).
4. **Conformalized Quantile Regression (`model_p10.json` + `model_p90.json` + CQR offset `-0.6785 m`):** Calibrated on out-of-fold walk-forward predictions to produce reliable uncertainty bounds across shallow coastal aquifers (`2–6 m`) and deep Indo-Gangetic/Thar aquifers (`30–110 m`).
5. **State-Aware Hydrogeological Risk Calibration (`ml/risk_rules.py`):** Pairs state-specific depth percentiles (`P65`/`P85`) with universal deep-aquifer stress ceilings (`26 m`) and drawdown velocity rules (`yoy_delta`, `depth_trend_5yr`).

---

## 2. 4-Fold Expanding-Window Walk-Forward CV (`2019–2022`)

| Candidate Configuration | Walk-Forward Mean OOF MAE (`m`) | Walk-Forward Baseline MAE (`m`) | OOF Skill vs Baseline | Median Trees |
|---|---|---|---|---|
| Seasonal Naive Baseline (`prev_depth_mbgl`) | `1.9579` | `1.9579` | `0.00%` | — |
| `shallow_l1_strong_reg` (`depth=3`) | `1.8192` | `1.9579` | `+7.08%` | `88` |
| `balanced_l1_med_reg` (`depth=4`) | `1.8111` | `1.9579` | `+7.50%` | `98` |
| `deep_l1_conserv_lr` (`depth=5`) | `1.8044` | `1.9579` | `+7.84%` | `92` |
| **`med_depth6_l1_national` (`depth=6`, Selected)** | **`1.8020`** | **`1.9579`** | **`+7.96%`** | **`90`** |

---

## 3. Untouched Multi-State National Holdout Evaluation (`3,651` Block-Seasons)

Evaluated strictly chronologically across all monitored Indian states (`Train: 2014–2021` `37,577` rows · `Val: 2022` `3,678` rows · `Untouched Holdout Test: 2023` `3,651` rows; final production models then refit on all `45,964` rows through `2025`):

| Model / Benchmark | Overall MAE (`m`) | Median AE (`m`) | RMSE (`m`) | `R²` | Pre-Monsoon MAE (`2,835` rows) | Post-Monsoon MAE (`816` rows) | Skill vs Baseline |
|---|---|---|---|---|---|---|---|
| Historical Block Seasonal Climatology | `2.6061` | `1.298` | `5.0835` | `0.6901` | `2.6523` | `2.4457` | `-7.41%` |
| Seasonal Naive Baseline (Same Season Last Yr) | `2.4264` | `1.250` | `4.9775` | `0.7028` | `2.3186` | `2.8011` | `0.00%` |
| **WellCast Pan-India Dual-Specialist + CQR** | **`2.0970`** | **`1.010`** | **`4.5560`** | **`0.7510`** | **`1.9914` (`+14.11%`)** | **`2.4640` (`+12.03%`)** | **`+13.58%` MAE (`+19.2%` MedAE)** |

---

## 4. Top Pan-India Hydrological & Spatial Features (`26` Features)

1. `prev_anomaly_vs_target_mean` (`19.32%`) — Causal mean-reversion pull toward each block's historical seasonal equilibrium
2. `prev_change_mbgl` (`14.33%`) — Preceding 6-month seasonal drawdown / recharge amplitude
3. `target_season_2yr_ago_depth` (`6.31%`) — Multi-year target-season memory
4. `season_code` (`5.63%`) — Dry pre-monsoon vs wet post-monsoon transition indicator
5. `block_hist_std` (`4.87%`) — Aquifer storage elasticity / historical variability signature
6. `curr_anomaly_vs_season_mean` (`4.05%`) — Current stress relative to block normal
7. `prev_depth_mbgl` (`3.95%`), `depth_mbgl` (`3.56%`), `same_season_last_year_depth` (`3.34%`), `block_target_season_hist_mean` (`3.28%`), `depth_trend_5yr` (`2.95%`), `lat` (`2.71%`), `district_seasonal_shift` (`2.60%`), and 7 monotone rainfall totals/anomalies (`3m`, `6m`, `12m`, `24m`).
