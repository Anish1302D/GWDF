"""Strict chronological & walk-forward evaluation utilities for WellCast v2."""

from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, median_absolute_error, r2_score

FEATURE_COLUMNS: list[str] = [
    "depth_mbgl",
    "prev_depth_mbgl",
    "prev_change_mbgl",
    "same_season_last_year_depth",
    "yoy_change_mbgl",
    "target_season_2yr_ago_depth",
    "block_curr_season_hist_mean",
    "block_target_season_hist_mean",
    "prev_anomaly_vs_target_mean",
    "curr_anomaly_vs_season_mean",
    "block_hist_std",
    "district_curr_depth_mean",
    "block_vs_district_depth_diff",
    "district_seasonal_shift",
    "depth_trend_5yr",
    "rain_3m_mm",
    "rain_6m_mm",
    "rain_12m_mm",
    "rain_24m_mm",
    "rain_departure_6m_pct",
    "rain_departure_12m_pct",
    "rain_departure_24m_pct",
    "lat",
    "lon",
    "well_count",
    "season_code",
]

# Monotone constraints matching FEATURE_COLUMNS:
# Higher precipitation & positive rainfall departures (indices 15..21) -> non-positive (-1) effect on depth_mbgl
MONOTONE_CONSTRAINTS = (
    "(" + ",".join("-1" if col.startswith("rain_") else "0" for col in FEATURE_COLUMNS) + ")"
)


def chronological_split(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Split dataset chronologically by `target_obs_date` year (zero random shuffle)."""
    work = df.dropna(subset=["target_depth_next", "target_obs_date", "baseline_pred_next"]).copy()
    work["target_dt"] = pd.to_datetime(work["target_obs_date"])
    work["target_year"] = work["target_dt"].dt.year

    years = sorted(work["target_year"].unique())
    if len(years) < 3:
        raise ValueError(f"Need at least 3 distinct target years, got {years}")

    year_counts = work["target_year"].value_counts()
    viable_years = [y for y in years if year_counts[y] >= 50]
    test_year = viable_years[-1] if len(viable_years) >= 3 else years[-1]
    prior_years = [y for y in years if y < test_year]
    val_year = prior_years[-1]

    train_df = work[work["target_year"] < val_year].copy()
    val_df = work[work["target_year"] == val_year].copy()
    test_df = work[work["target_year"] == test_year].copy()

    assert train_df["target_dt"].max() < val_df["target_dt"].min(), "Temporal leak between train and val!"
    assert val_df["target_dt"].max() < test_df["target_dt"].min(), "Temporal leak between val and test!"

    split_meta = {
        "train_years": [int(train_df["target_year"].min()), int(train_df["target_year"].max())],
        "val_year": int(val_year),
        "test_year": int(test_year),
        "train_rows": int(len(train_df)),
        "val_rows": int(len(val_df)),
        "test_rows": int(len(test_df)),
        "max_train_target_date": str(train_df["target_dt"].max().date()),
        "min_test_target_date": str(test_df["target_dt"].min().date()),
    }
    return train_df, val_df, test_df, split_meta


def enforce_prediction_bounds(
    pred_p50: np.ndarray,
    pred_p10: np.ndarray,
    pred_p90: np.ndarray,
    min_half_width: float = 0.25,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Guarantee `0.0 <= lower_bound <= predicted_depth <= upper_bound` and non-degenerate width."""
    p50 = np.maximum(0.0, np.asarray(pred_p50, dtype=float))
    low = np.maximum(0.0, np.minimum(np.asarray(pred_p10, dtype=float), p50))
    high = np.maximum(np.asarray(pred_p90, dtype=float), p50)

    too_narrow = (high - low) < (2.0 * min_half_width)
    low = np.where(too_narrow, np.maximum(0.0, p50 - min_half_width), low)
    high = np.where(too_narrow, p50 + min_half_width, high)
    return np.round(p50, 2), np.round(low, 2), np.round(high, 2)


def compute_conformal_adjustment(
    y_cal: np.ndarray,
    q_low_cal: np.ndarray,
    q_high_cal: np.ndarray,
    target_coverage: float = 0.80,
) -> float:
    """Romano et al. (2019) Conformalized Quantile Regression (CQR) finite-sample offset."""
    scores = np.maximum(q_low_cal - y_cal, y_cal - q_high_cal)
    n = len(scores)
    level = min(1.0, np.ceil((n + 1) * target_coverage) / n)
    return float(np.quantile(scores, level))


def compute_regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    mae = float(mean_absolute_error(y_true, y_pred))
    medae = float(median_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2 = float(r2_score(y_true, y_pred)) if len(y_true) > 2 else 0.0
    return {
        "mae": round(mae, 4),
        "medae": round(medae, 4),
        "rmse": round(rmse, 4),
        "r2": round(r2, 4),
    }


def evaluate_holdout(
    test_df: pd.DataFrame,
    pred_p50: np.ndarray,
    lower_bound: np.ndarray,
    upper_bound: np.ndarray,
) -> dict[str, Any]:
    """Compare model predictions against Seasonal Naive & Climatology benchmarks on untouched holdout."""
    y_true = test_df["target_depth_next"].to_numpy(dtype=float)
    y_base = test_df["baseline_pred_next"].to_numpy(dtype=float)
    y_clim = (
        test_df["block_target_season_hist_mean"]
        .fillna(test_df["baseline_pred_next"])
        .to_numpy(dtype=float)
    )

    base_metrics = compute_regression_metrics(y_true, y_base)
    clim_metrics = compute_regression_metrics(y_true, y_clim)
    xgb_metrics = compute_regression_metrics(y_true, pred_p50)

    skill_pct = (
        round(((base_metrics["mae"] - xgb_metrics["mae"]) / base_metrics["mae"]) * 100.0, 2)
        if base_metrics["mae"] > 0
        else 0.0
    )
    rmse_skill_pct = (
        round(((base_metrics["rmse"] - xgb_metrics["rmse"]) / base_metrics["rmse"]) * 100.0, 2)
        if base_metrics["rmse"] > 0
        else 0.0
    )

    inside = (y_true >= lower_bound) & (y_true <= upper_bound)
    coverage_pct = round(float(np.mean(inside) * 100.0), 2)
    mean_width = round(float(np.mean(upper_bound - lower_bound)), 2)

    by_season: dict[str, Any] = {}
    for s_code in (0, 1):
        mask = (test_df["season_code"] == s_code).to_numpy()
        target_season = "post-monsoon" if s_code == 0 else "pre-monsoon"
        if int(mask.sum()) >= 5:
            b_mae = float(mean_absolute_error(y_true[mask], y_base[mask]))
            m_mae = float(mean_absolute_error(y_true[mask], pred_p50[mask]))
            by_season[target_season] = {
                "rows": int(mask.sum()),
                "baseline_mae": round(b_mae, 4),
                "climatology_mae": round(float(mean_absolute_error(y_true[mask], y_clim[mask])), 4),
                "model_mae": round(m_mae, 4),
                "skill_pct": round(((b_mae - m_mae) / b_mae) * 100.0, 2) if b_mae > 0 else 0.0,
            }

    return {
        "baseline_seasonal_naive": base_metrics,
        "historical_seasonal_climatology": clim_metrics,
        "xgboost_model": xgb_metrics,
        "skill_vs_baseline_pct": skill_pct,
        "rmse_skill_vs_baseline_pct": rmse_skill_pct,
        "beats_baseline": bool(xgb_metrics["mae"] < base_metrics["mae"]),
        "p10_p90_coverage_pct": coverage_pct,
        "mean_interval_width_mbgl": mean_width,
        "by_target_season": by_season,
    }
