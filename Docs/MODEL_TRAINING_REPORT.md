# WellCast v2: AI Model Training & Validation Report

> **Active Model Artifact:** `xgb-dual-specialist-cqr-v2-20261127` (`ml/artifacts_local/`)  
> **Training Script:** [`ml/train.py`](../ml/train.py) · **Evaluation Module:** [`ml/evaluate.py`](../ml/evaluate.py)  
> **Dataset Scope:** **356 Maharashtra Blocks (Talukas)** across **36 Districts** (`7,860` causal block-season rows, `5,549` supervised 6-month transition pairs from `756,542` raw CGWB & GSDA well observations + `6,048` NASA POWER district-months)

---

## 1. Model Architecture (`v2` Upgrade)

Rather than fitting a single naive regressor directly to raw depth, WellCast v2 models **6-month residual drawdown/recovery over the Seasonal Naive anchor** (`y_delta = target_depth_next - prev_depth_mbgl`) using a **Dual Season-Specialist + Global Monotone XGBoost Ensemble** paired with **Conformalized Quantile Regression (CQR)**:

1. **Global Residual Monotone XGBoost (`model_p50.json`):** `226` trees (`objective = reg:absoluteerror`, `max_depth = 5`, `min_child_weight = 16`, `lr = 0.025`, `L1 = 1.5`, `L2 = 6.0`) trained across all `5,549` historical transitions with **strictly negative (`-1`) monotone constraints** on all 7 precipitation & drought-anomaly features (`rain_3m_mm`, `rain_6m_mm`, `rain_12m_mm`, `rain_24m_mm`, `rain_departure_6m_pct`, `rain_departure_12m_pct`, `rain_departure_24m_pct`).
2. **Pre-Monsoon Drawdown Specialist (`model_pre_p50.json`):** `192` trees specialized exclusively on `Post-Monsoon (Nov) -> Pre-Monsoon (May)` summer pumping + dry-season depletion physics (`w_global = 0.45`, `w_specialist = 0.45`).
3. **Post-Monsoon Recharge Specialist (`model_post_p50.json`):** `192` trees specialized exclusively on `Pre-Monsoon (May) -> Post-Monsoon (Nov)` monsoon aquifer recovery physics with shrinkage regularization (`w_global = 0.10`, `w_specialist = 0.30`).
4. **Conformalized Quantile Regression (`model_p10.json` + `model_p90.json` + CQR offset `-0.1236 m`):** Finite-sample conformal calibration (Romano et al., 2019) computed on out-of-fold `2023–2024` predictions, tightening mean interval width by **29%** (`3.71 m -> 2.62 m`) while preserving **`76.92%`** empirical coverage on untouched `2025` data.

---

## 2. 4-Fold Expanding-Window Walk-Forward CV (`2021–2024`)

All hyperparameter selection and blend weights were tuned strictly on pre-holdout walk-forward folds (`Train <= Y-1`, `Validate == Y` for `Y in {2021, 2022, 2023, 2024}`):

| Candidate Configuration | Walk-Forward Mean OOF MAE (`m`) | Walk-Forward Baseline MAE (`m`) | OOF Skill vs Baseline | Median Trees |
|---|---|---|---|---|
| Seasonal Naive Baseline (`prev_depth_mbgl`) | `0.9950` | `0.9950` | `0.00%` | — |
| `shallow_l1_strong_reg` (`depth=3`) | `0.9202` | `0.9950` | `+7.52%` | `121` |
| `balanced_l1_med_reg` (`depth=4`) | `0.9136` | `0.9950` | `+8.18%` | `198` |
| `huber_smooth_reg` (`pseudohuber, depth=4`) | `0.9102` | `0.9950` | `+8.52%` | `94` |
| **`deep_l1_conserv_lr` (`depth=5`, Selected)** | **`0.9061`** | **`0.9950`** | **`+8.93%`** | **`226`** |

---

## 3. Untouched `2025` Final Holdout Benchmark (`247` Block-Seasons)

Zero `2025` target observations were used during feature scaling, hyperparameter selection, blend optimization, or CQR calibration (`max_train_target_date = 2023-11-01` / `val = 2024`, `min_test_target_date = 2025-05-01`).

| Model / Benchmark | Overall MAE (`m`) | RMSE (`m`) | `R²` | Pre-Monsoon MAE (`140` rows) | MAE Skill vs Baseline | P10–P90 Coverage (`Width`) |
|---|---|---|---|---|---|---|
| Historical Block Seasonal Climatology | `1.3968` | `1.7034` | `0.7896` | `1.2820` | `-60.05%` | — |
| Seasonal Naive Baseline (Same Season Last Yr) | `0.8727` | `1.2246` | `0.8913` | `1.0226` | `0.00%` | — |
| WellCast `v1` (Single Residual XGBoost) | `0.8703` | `1.1723` | `0.9004` | `0.9441` (`+7.68%`) | `+0.28%` | `91.90%` (`3.71 m`) |
| **WellCast `v2` (Dual-Specialist + CQR)** | **`0.8147`** | **`1.1078`** | **`0.9110`** | **`0.8881` (`+13.15%`)** | **`+6.65%` (`+9.54%` RMSE)** | **`76.92%` (`2.62 m`)** |

---

## 4. Top Hydrological & Spatial Feature Importances (`26` Features)

| Rank | Feature | Importance | Hydrogeological Role |
|---|---|---|---|
| 1 | `prev_anomaly_vs_target_mean` | `13.30%` | Mean-reversion pull toward block's causal seasonal aquifer equilibrium |
| 2 | `prev_change_mbgl` | `9.78%` | Preceding 6-month seasonal drawdown / monsoon recharge amplitude |
| 3 | `rain_3m_mm` | `5.03%` | Recent 3-month recharge pulse (monotone `-1`) |
| 4 | `same_season_last_year_depth` | `5.00%` | 1-year prior reference depth for current season |
| 5 | `season_code` | `4.98%` | Distinguishes summer drawdown vs monsoon recharge cycle |
| 6 | `yoy_change_mbgl` | `4.96%` | Net 12-month depletion velocity |
| 7 | `rain_12m_mm` | `4.77%` | Full annual precipitation budget (monotone `-1`) |
| 8 | `block_hist_std` | `4.09%` | Local basalt aquifer storage elasticity / historical volatility |
| 9 | `rain_departure_6m_pct` | `3.93%` | 6-month rainfall anomaly % vs 12-year normal (monotone `-1`) |
| 10 | `target_season_2yr_ago_depth` | `3.93%` | Multi-year target-season memory |
| 11 | `prev_depth_mbgl` | `3.87%` | Baseline depth anchor |
| 12 | `district_seasonal_shift` | `3.48%` | Regional district-wide seasonal water shift (denoises single-well blocks) |
| 13 | `curr_anomaly_vs_season_mean` | `3.36%` | Current aquifer stress relative to block historical average |
| 14 | `district_curr_depth_mean` | `3.17%` | Regional district aquifer table context |
| 15 | `depth_trend_5yr` | `3.06%` | Structural 5-year depletion slope (`m/yr`) |
| 16 | `rain_24m_mm` | `3.02%` | Multi-monsoon 24-month cumulative drought memory (monotone `-1`) |

---

## 5. Precomputed Drought Scenario Sensitivity (All `356` Blocks)

| Scenario | Rainfall % of Normal | Statewide Mean Predicted Depth (`m bgl`) | Physical Monotonicity |
|---|---|---|---|
| `normal` | `100%` | `7.028 m` | Baseline |
| `minus10` | `90%` (`-10%`) | `7.083 m` (`+0.055 m` deeper) | Strictly deeper |
| `minus20` | `80%` (`-20%`) | `7.156 m` (`+0.128 m` deeper) | Strictly deeper |
| `minus30` | `70%` (`-30%`) | `7.181 m` (`+0.153 m` deeper) | Strictly deeper |
