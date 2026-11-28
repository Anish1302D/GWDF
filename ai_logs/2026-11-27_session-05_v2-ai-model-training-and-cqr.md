# Session 05: v2 Hydro-Spatial AI Model Upgrade, Walk-Forward CV & CQR Calibration

- **Date / Time (IST):** `2026-11-27 23:32 – 23:42 IST`
- **Phase(s) Covered:** `Phases 2, 3, and 4 (Deep ML Upgrade, Uncertainty Calibration & Scenario Refresh)`
- **Overall Status:** `[DONE]`

---

## 1. Session Objectives
- Prioritize deep local AI model engineering while AWS account `621503941447` completes service activation.
- Substantially improve holdout forecasting accuracy and uncertainty sharpness over both the Seasonal Naive baseline and `v1`.

---

## 2. Work Completed
1. **Upgraded Feature Schema (`v2`, 26 causal hydro-spatial features in `sql/02_features.sql` & `build_features_local.py`):**
   - Added causal expanding block-season equilibrium means (`block_curr_season_hist_mean`, `block_target_season_hist_mean`), mean-reversion anomalies (`prev_anomaly_vs_target_mean`, `curr_anomaly_vs_season_mean`), aquifer volatility (`block_hist_std`), 2-year target-season lag, concurrent regional district water-table context (`district_curr_depth_mean`, `district_seasonal_shift`), `24-month` cumulative drought memory (`rain_24m_mm`, `rain_departure_24m_pct`), and geospatial coordinates (`lat`, `lon`).
2. **Upgraded ML Engine (`ml/evaluate.py`, `ml/train.py`, `ml/make_forecasts.py`):**
   - Added 4-fold expanding-window walk-forward CV (`2021–2024`) -> selected `deep_l1_conserv_lr` (`OOF MAE = 0.9061 m` vs `0.9950 m` baseline, `+8.93%` skill).
   - Trained **Dual Season-Specialist + Global Monotone XGBoost Ensemble** (`model_p50.json`, `model_pre_p50.json`, `model_post_p50.json`) + **Conformalized Quantile Regression (`model_p10.json`, `model_p90.json`, CQR offset `-0.1236 m`)**.
   - **Untouched `2025` Holdout Results (`247` rows):**
     - Overall MAE dropped from `0.8727 m` (baseline) / `0.8703 m` (`v1`) -> **`0.8147 m` (`+6.65%` skill)**.
     - RMSE dropped from `1.2246 m` -> **`1.1078 m` (`+9.54%` skill)**; **`R² = 0.9110`**.
     - Dry Pre-Monsoon MAE dropped from `1.0226 m` -> **`0.8881 m` (`+13.15%` skill)**.
     - CQR P10–P90 coverage: **`76.92%`** with **`2.62 m` mean width** (29% sharper than `v1`'s `3.71 m`).
3. Regenerated all 4 drought scenarios across `356` blocks, rebuilt `infra/s3_data_bucket_upload` (`23` files, `5.47 MB`), verified `8/8` pytest tests passing, and authored `Docs/MODEL_TRAINING_REPORT.md`.
