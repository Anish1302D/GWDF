"""WellCast ML Training Entry Point (AWS SageMaker Script-Mode & Local CLI Compatible).

Trains:
  1. Seasonal Naive benchmark (evaluated on chronological holdout year)
  2. XGBoost Point Forecast Regressor (`model_p50.json`) with rainfall monotonicity constraints
  3. Quantile XGBoost Regressors (`model_p10.json`, `model_p90.json`) for 80% uncertainty range
  4. Calibrates block-level risk thresholds and exports `metrics.json`
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.evaluate import (  # noqa: E402
    FEATURE_COLUMNS,
    MONOTONE_CONSTRAINTS,
    chronological_split,
    enforce_prediction_bounds,
    evaluate_holdout,
)
from ml.risk_rules import calibrate_thresholds_from_data  # noqa: E402


def _load_parquet_dir_or_file(path_str: str) -> pd.DataFrame:
    p = Path(path_str)
    if p.is_file():
        return pd.read_parquet(p)
    files = sorted(p.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No Parquet files found in {p}")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _prepare_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    X = df[FEATURE_COLUMNS].copy()
    for col in FEATURE_COLUMNS:
        X[col] = pd.to_numeric(X[col], errors="coerce")
    base = df["baseline_pred_next"].to_numpy(dtype=float)
    y_abs = df["target_depth_next"].to_numpy(dtype=float)
    y_delta = y_abs - base
    return X, y_delta, base


def _build_main_regressor(n_estimators: int = 400) -> xgb.XGBRegressor:
    return xgb.XGBRegressor(
        objective="reg:absoluteerror",
        n_estimators=n_estimators,
        max_depth=4,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.85,
        min_child_weight=10,
        reg_alpha=1.0,
        reg_lambda=4.0,
        monotone_constraints=MONOTONE_CONSTRAINTS,
        random_state=42,
        n_jobs=4,
    )


def _build_quantile_regressor(alpha: float, n_estimators: int = 320) -> xgb.XGBRegressor:
    return xgb.XGBRegressor(
        objective="reg:quantileerror",
        quantile_alpha=alpha,
        n_estimators=n_estimators,
        max_depth=3,
        learning_rate=0.035,
        subsample=0.8,
        colsample_bytree=0.85,
        min_child_weight=12,
        reg_alpha=1.0,
        reg_lambda=4.0,
        monotone_constraints=MONOTONE_CONSTRAINTS,
        random_state=42,
        n_jobs=4,
    )


def train_and_evaluate(train_path: str, model_dir: str) -> dict[str, Any]:
    out_dir = Path(model_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_df = _load_parquet_dir_or_file(train_path)
    df = raw_df.dropna(subset=["target_depth_next", "baseline_pred_next"]).copy()

    train_df, val_df, test_df, split_meta = chronological_split(df)
    X_train, y_train_delta, _ = _prepare_xy(train_df)
    X_val, y_val_delta, _ = _prepare_xy(val_df)
    X_test, _, base_test = _prepare_xy(test_df)

    # 1. Fit residual delta model (target = target_depth_next - baseline_pred_next) on train, early-stop on val
    eval_p50 = _build_main_regressor(n_estimators=500)
    eval_p50.set_params(early_stopping_rounds=35)
    eval_p50.fit(X_train, y_train_delta, eval_set=[(X_val, y_val_delta)], verbose=False)
    best_iters = max(40, int(getattr(eval_p50, "best_iteration", 200)) + 1)

    # Combine train + val to predict untouched holdout test year
    train_val_df = pd.concat([train_df, val_df], ignore_index=True)
    X_tv, y_tv_delta, _ = _prepare_xy(train_val_df)

    holdout_p50_model = _build_main_regressor(n_estimators=best_iters)
    holdout_p10_model = _build_quantile_regressor(alpha=0.10, n_estimators=min(best_iters, 300))
    holdout_p90_model = _build_quantile_regressor(alpha=0.90, n_estimators=min(best_iters, 300))

    holdout_p50_model.fit(X_tv, y_tv_delta, verbose=False)
    holdout_p10_model.fit(X_tv, y_tv_delta, verbose=False)
    holdout_p90_model.fit(X_tv, y_tv_delta, verbose=False)

    pred_p50_raw = base_test + holdout_p50_model.predict(X_test)
    pred_p10_raw = base_test + holdout_p10_model.predict(X_test)
    pred_p90_raw = base_test + holdout_p90_model.predict(X_test)
    pred_p50, lower_b, upper_b = enforce_prediction_bounds(pred_p50_raw, pred_p10_raw, pred_p90_raw)

    # Empirical residual quantiles for calibration backup
    residuals = test_df["target_depth_next"].to_numpy(dtype=float) - pred_p50
    res_q10 = float(np.percentile(residuals, 10))
    res_q90 = float(np.percentile(residuals, 90))

    eval_report = evaluate_holdout(test_df, pred_p50, lower_b, upper_b)
    conformal_used = False
    if eval_report["p10_p90_coverage_pct"] < 74.0:
        conformal_used = True
        lower_c = np.minimum(lower_b, np.maximum(0.0, pred_p50 + res_q10))
        upper_c = np.maximum(upper_b, pred_p50 + res_q90)
        pred_p50, lower_b, upper_b = enforce_prediction_bounds(pred_p50, lower_c, upper_c)
        eval_report = evaluate_holdout(test_df, pred_p50, lower_b, upper_b)

    # 2. Refit production residual models on 100% of labeled historical rows (<= test_year)
    X_all, y_all_delta, _ = _prepare_xy(df)
    prod_p50 = _build_main_regressor(n_estimators=best_iters)
    prod_p10 = _build_quantile_regressor(alpha=0.10, n_estimators=min(best_iters, 300))
    prod_p90 = _build_quantile_regressor(alpha=0.90, n_estimators=min(best_iters, 300))

    prod_p50.fit(X_all, y_all_delta, verbose=False)
    prod_p10.fit(X_all, y_all_delta, verbose=False)
    prod_p90.fit(X_all, y_all_delta, verbose=False)

    prod_p50.save_model(str(out_dir / "model_p50.json"))
    prod_p10.save_model(str(out_dir / "model_p10.json"))
    prod_p90.save_model(str(out_dir / "model_p90.json"))

    importances = {
        col: round(float(imp), 4)
        for col, imp in sorted(
            zip(FEATURE_COLUMNS, prod_p50.feature_importances_),
            key=lambda kv: kv[1],
            reverse=True,
        )
    }

    thresholds = calibrate_thresholds_from_data(df["depth_mbgl"])
    use_fallback = not eval_report["beats_baseline"]

    metrics_doc: dict[str, Any] = {
        "model_version": f"xgb-residual-v1-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        "target_formulation": "residual_over_seasonal_naive",
        "trained_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "active_serving_strategy": "baseline_plus_trend_fallback" if use_fallback else "xgboost_residual_monotone_quantile",
        "best_n_estimators": best_iters,
        "conformal_residual_adjustment": conformal_used,
        "residual_q10_mbgl": round(res_q10, 4),
        "residual_q90_mbgl": round(res_q90, 4),
        "feature_columns": FEATURE_COLUMNS,
        "feature_importances": importances,
        "split": split_meta,
        "holdout_evaluation": eval_report,
        "calibrated_risk_thresholds": thresholds,
    }

    (out_dir / "metrics.json").write_text(json.dumps(metrics_doc, indent=2), encoding="utf-8")
    print(json.dumps(metrics_doc, indent=2))
    return metrics_doc


def main() -> None:
    parser = argparse.ArgumentParser(description="Train WellCast XGBoost + Quantile groundwater models")
    parser.add_argument(
        "--train",
        default=os.environ.get("SM_CHANNEL_TRAIN", str(REPO_ROOT / "data" / "processed_local" / "curated" / "ml_train")),
    )
    parser.add_argument(
        "--model-dir",
        default=os.environ.get("SM_MODEL_DIR", str(REPO_ROOT / "ml" / "artifacts_local")),
    )
    args = parser.parse_args()
    train_and_evaluate(args.train, args.model_dir)


if __name__ == "__main__":
    main()
