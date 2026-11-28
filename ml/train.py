"""WellCast v2 ML Training Engine (SageMaker Script-Mode & Local CLI Compatible).

Architecture:
  1. 4-Fold Expanding-Window Walk-Forward Cross-Validation (`2021`, `2022`, `2023`, `2024`)
     for hyperparameter selection and Global + Season-Specialist + Shrinkage blend tuning.
  2. Dual Hydrological Specialists:
     - Global Residual Monotone XGBoost (`model_p50.json`)
     - Pre-Monsoon Drawdown Specialist (`model_pre_p50.json`, predicting May dry season from Nov state)
     - Post-Monsoon Recharge Specialist (`model_post_p50.json`, predicting Nov recovery from May state)
  3. Conformalized Quantile Regression (CQR, `model_p10.json` + `model_p90.json` + finite-sample offset)
     calibrated on out-of-fold 2023-2024 predictions for sharp, honest 80% prediction intervals.
  4. Untouched 2025 Final Holdout Evaluation + full production refit across all historical rows.
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
from sklearn.metrics import mean_absolute_error

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.evaluate import (  # noqa: E402
    FEATURE_COLUMNS,
    MONOTONE_CONSTRAINTS,
    chronological_split,
    compute_conformal_adjustment,
    enforce_prediction_bounds,
    evaluate_holdout,
)
from ml.risk_rules import calibrate_thresholds_from_data  # noqa: E402

CANDIDATE_CONFIGS: list[dict[str, Any]] = [
    {
        "name": "shallow_l1_strong_reg",
        "objective": "reg:absoluteerror",
        "max_depth": 3,
        "min_child_weight": 14,
        "learning_rate": 0.03,
        "reg_alpha": 1.5,
        "reg_lambda": 5.0,
    },
    {
        "name": "balanced_l1_med_reg",
        "objective": "reg:absoluteerror",
        "max_depth": 4,
        "min_child_weight": 12,
        "learning_rate": 0.03,
        "reg_alpha": 1.0,
        "reg_lambda": 4.0,
    },
    {
        "name": "deep_l1_conserv_lr",
        "objective": "reg:absoluteerror",
        "max_depth": 5,
        "min_child_weight": 16,
        "learning_rate": 0.025,
        "reg_alpha": 1.5,
        "reg_lambda": 6.0,
    },
    {
        "name": "huber_smooth_reg",
        "objective": "reg:pseudohubererror",
        "max_depth": 4,
        "min_child_weight": 12,
        "learning_rate": 0.03,
        "reg_alpha": 1.0,
        "reg_lambda": 4.0,
    },
]


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


def _make_xgb(
    cfg: dict[str, Any],
    n_estimators: int = 350,
    early_stopping_rounds: int | None = None,
) -> xgb.XGBRegressor:
    params: dict[str, Any] = {
        "objective": cfg.get("objective", "reg:absoluteerror"),
        "n_estimators": n_estimators,
        "max_depth": cfg["max_depth"],
        "learning_rate": cfg["learning_rate"],
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": cfg["min_child_weight"],
        "reg_alpha": cfg["reg_alpha"],
        "reg_lambda": cfg["reg_lambda"],
        "monotone_constraints": MONOTONE_CONSTRAINTS,
        "random_state": 42,
        "n_jobs": 4,
    }
    if early_stopping_rounds is not None:
        params["early_stopping_rounds"] = early_stopping_rounds
    return xgb.XGBRegressor(**params)


def _make_quantile_xgb(alpha: float, n_estimators: int = 240) -> xgb.XGBRegressor:
    return xgb.XGBRegressor(
        objective="reg:quantileerror",
        quantile_alpha=alpha,
        n_estimators=n_estimators,
        max_depth=3,
        learning_rate=0.035,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=14,
        reg_alpha=1.2,
        reg_lambda=4.5,
        monotone_constraints=MONOTONE_CONSTRAINTS,
        random_state=42,
        n_jobs=4,
    )


def _optimize_season_blend(
    y_delta_true: np.ndarray,
    pred_global_delta: np.ndarray,
    pred_spec_delta: np.ndarray,
) -> tuple[float, float]:
    """Grid-search optimal `(w_global, w_specialist)` shrinkage weights on walk-forward OOF residuals."""
    best_mae = float(mean_absolute_error(y_delta_true, np.zeros_like(y_delta_true)))
    best_wg, best_ws = 0.0, 0.0
    grid = np.linspace(0.0, 1.0, 21)
    for wg in grid:
        for ws in grid:
            if wg + ws > 1.15:
                continue
            blend = wg * pred_global_delta + ws * pred_spec_delta
            mae = float(mean_absolute_error(y_delta_true, blend))
            if mae < best_mae - 1e-6:
                best_mae = mae
                best_wg, best_ws = float(round(wg, 3)), float(round(ws, 3))
    return best_wg, best_ws


def predict_blended_delta(
    X: pd.DataFrame,
    season_codes: np.ndarray,
    m_global: xgb.XGBRegressor,
    m_pre: xgb.XGBRegressor,
    m_post: xgb.XGBRegressor,
    blend_weights: dict[str, dict[str, float]],
) -> np.ndarray:
    g_delta = m_global.predict(X)
    pre_delta = m_pre.predict(X)
    post_delta = m_post.predict(X)

    out = np.zeros(len(X), dtype=float)
    # season_code == 1 (observed Nov post-monsoon) -> predicts upcoming Pre-Monsoon (May)
    m1 = season_codes == 1
    if m1.any():
        w = blend_weights["pre_monsoon_target"]
        out[m1] = w["w_global"] * g_delta[m1] + w["w_specialist"] * pre_delta[m1]

    # season_code == 0 (observed May pre-monsoon) -> predicts upcoming Post-Monsoon (Nov)
    m0 = ~m1
    if m0.any():
        w = blend_weights["post_monsoon_target"]
        out[m0] = w["w_global"] * g_delta[m0] + w["w_specialist"] * post_delta[m0]

    return out


def train_and_evaluate(train_path: str, model_dir: str) -> dict[str, Any]:
    out_dir = Path(model_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_df = _load_parquet_dir_or_file(train_path)
    df = raw_df.dropna(subset=["target_depth_next", "baseline_pred_next", "target_obs_date"]).copy()
    df["target_dt"] = pd.to_datetime(df["target_obs_date"])
    df["target_year"] = df["target_dt"].dt.year

    train_df, val_df, test_df, split_meta = chronological_split(df)
    test_year = split_meta["test_year"]

    # 1. 4-Fold Expanding-Window Walk-Forward CV across years strictly < test_year
    all_pre_test_years = sorted(y for y in df["target_year"].unique() if y < test_year)
    cv_years = [y for y in all_pre_test_years[-4:] if int((df["target_year"] == y).sum()) >= 50]

    cv_leaderboard: list[dict[str, Any]] = []
    best_cfg = CANDIDATE_CONFIGS[0]
    best_cv_mae = float("inf")
    best_median_iters = 160

    for cfg in CANDIDATE_CONFIGS:
        fold_maes: list[float] = []
        fold_base_maes: list[float] = []
        fold_iters: list[int] = []
        for vy in cv_years:
            f_tr = df[df["target_year"] < vy]
            f_va = df[df["target_year"] == vy]
            X_ftr, y_ftr, _ = _prepare_xy(f_tr)
            X_fva, y_fva, b_fva = _prepare_xy(f_va)

            m = _make_xgb(cfg, n_estimators=450, early_stopping_rounds=35)
            m.fit(X_ftr, y_ftr, eval_set=[(X_fva, y_fva)], verbose=False)
            iters = max(40, int(getattr(m, "best_iteration", 150)) + 1)
            pred_abs = np.maximum(0.0, b_fva + m.predict(X_fva))
            y_true_abs = f_va["target_depth_next"].to_numpy(dtype=float)

            fold_maes.append(float(mean_absolute_error(y_true_abs, pred_abs)))
            fold_base_maes.append(float(mean_absolute_error(y_true_abs, b_fva)))
            fold_iters.append(iters)

        avg_mae = float(np.mean(fold_maes))
        avg_base = float(np.mean(fold_base_maes))
        med_iters = int(np.median(fold_iters))
        cv_leaderboard.append(
            {
                "config": cfg["name"],
                "cv_years": [int(y) for y in cv_years],
                "mean_oof_mae": round(avg_mae, 4),
                "mean_baseline_mae": round(avg_base, 4),
                "median_best_iters": med_iters,
            }
        )
        if avg_mae < best_cv_mae:
            best_cv_mae = avg_mae
            best_cfg = cfg
            best_median_iters = med_iters

    # 2. Collect Walk-Forward Out-of-Fold Predictions on cv_years to tune Global+Specialist Blend & CQR Offset
    oof_records: list[pd.DataFrame] = []
    cqr_scores_y: list[np.ndarray] = []
    cqr_low: list[np.ndarray] = []
    cqr_high: list[np.ndarray] = []

    spec_iters = max(45, int(best_median_iters * 0.85))
    for vy in cv_years:
        f_tr = df[df["target_year"] < vy]
        f_va = df[df["target_year"] == vy].copy()
        X_ftr, y_ftr, _ = _prepare_xy(f_tr)
        X_fva, y_fva, b_fva = _prepare_xy(f_va)

        mg = _make_xgb(best_cfg, n_estimators=best_median_iters)
        mg.fit(X_ftr, y_ftr, verbose=False)

        tr_pre = f_tr[f_tr["season_code"] == 1]
        tr_post = f_tr[f_tr["season_code"] == 0]
        X_pre, y_pre, _ = _prepare_xy(tr_pre)
        X_post, y_post, _ = _prepare_xy(tr_post)

        m_pre = _make_xgb(best_cfg, n_estimators=spec_iters)
        m_post = _make_xgb(best_cfg, n_estimators=spec_iters)
        m_pre.fit(X_pre, y_pre, verbose=False)
        m_post.fit(X_post, y_post, verbose=False)

        f_va["oof_global_delta"] = mg.predict(X_fva)
        f_va["oof_spec_delta"] = np.where(
            f_va["season_code"].to_numpy() == 1,
            m_pre.predict(X_fva),
            m_post.predict(X_fva),
        )
        f_va["oof_true_delta"] = y_fva
        oof_records.append(f_va)

        # Calibrate CQR on recent folds (last 2 CV years, e.g., 2023-2024)
        if vy in cv_years[-2:]:
            mp10 = _make_quantile_xgb(0.10, n_estimators=min(best_median_iters, 220))
            mp90 = _make_quantile_xgb(0.90, n_estimators=min(best_median_iters, 220))
            mp10.fit(X_ftr, y_ftr, verbose=False)
            mp90.fit(X_ftr, y_ftr, verbose=False)
            cqr_scores_y.append(f_va["target_depth_next"].to_numpy(dtype=float))
            cqr_low.append(b_fva + mp10.predict(X_fva))
            cqr_high.append(b_fva + mp90.predict(X_fva))

    oof_df = pd.concat(oof_records, ignore_index=True)

    # Optimize season-specific convex/shrinkage blend weights strictly on OOF (<= 2024)
    oof_pre = oof_df[oof_df["season_code"] == 1]
    oof_post = oof_df[oof_df["season_code"] == 0]
    wg_pre, ws_pre = _optimize_season_blend(
        oof_pre["oof_true_delta"].to_numpy(),
        oof_pre["oof_global_delta"].to_numpy(),
        oof_pre["oof_spec_delta"].to_numpy(),
    )
    wg_post, ws_post = _optimize_season_blend(
        oof_post["oof_true_delta"].to_numpy(),
        oof_post["oof_global_delta"].to_numpy(),
        oof_post["oof_spec_delta"].to_numpy(),
    )

    # Guarantee non-zero rainfall sensitivity (> 0.15 tree weight) so drought slider stays responsive
    if wg_pre + ws_pre < 0.25:
        wg_pre = 0.25
    if wg_post + ws_post < 0.25:
        wg_post = 0.25

    blend_weights = {
        "pre_monsoon_target": {"w_global": wg_pre, "w_specialist": ws_pre},
        "post_monsoon_target": {"w_global": wg_post, "w_specialist": ws_post},
    }

    cqr_offset = compute_conformal_adjustment(
        np.concatenate(cqr_scores_y),
        np.concatenate(cqr_low),
        np.concatenate(cqr_high),
        target_coverage=0.80,
    )

    # 3. Train on all pre-test data (<= 2024) and evaluate ONCE on untouched 2025 Holdout Test
    train_val_df = df[df["target_year"] < test_year].copy()
    X_tv, y_tv_delta, _ = _prepare_xy(train_val_df)
    X_test, _, base_test = _prepare_xy(test_df)

    hold_g = _make_xgb(best_cfg, n_estimators=best_median_iters)
    hold_pre = _make_xgb(best_cfg, n_estimators=spec_iters)
    hold_post = _make_xgb(best_cfg, n_estimators=spec_iters)
    hold_p10 = _make_quantile_xgb(0.10, n_estimators=min(best_median_iters, 220))
    hold_p90 = _make_quantile_xgb(0.90, n_estimators=min(best_median_iters, 220))

    X_tv_pre, y_tv_pre, _ = _prepare_xy(train_val_df[train_val_df["season_code"] == 1])
    X_tv_post, y_tv_post, _ = _prepare_xy(train_val_df[train_val_df["season_code"] == 0])

    hold_g.fit(X_tv, y_tv_delta, verbose=False)
    hold_pre.fit(X_tv_pre, y_tv_pre, verbose=False)
    hold_post.fit(X_tv_post, y_tv_post, verbose=False)
    hold_p10.fit(X_tv, y_tv_delta, verbose=False)
    hold_p90.fit(X_tv, y_tv_delta, verbose=False)

    blended_test_delta = predict_blended_delta(
        X_test,
        test_df["season_code"].to_numpy(),
        hold_g,
        hold_pre,
        hold_post,
        blend_weights,
    )
    pred_p50_raw = base_test + blended_test_delta
    pred_p10_raw = base_test + hold_p10.predict(X_test) - cqr_offset
    pred_p90_raw = base_test + hold_p90.predict(X_test) + cqr_offset
    pred_p50, lower_b, upper_b = enforce_prediction_bounds(pred_p50_raw, pred_p10_raw, pred_p90_raw)

    residuals = test_df["target_depth_next"].to_numpy(dtype=float) - pred_p50
    res_q10 = float(np.percentile(residuals, 10))
    res_q90 = float(np.percentile(residuals, 90))

    eval_report = evaluate_holdout(test_df, pred_p50, lower_b, upper_b)

    # 4. Refit all 5 production models on 100% of labeled historical rows (<= 2025)
    X_all, y_all_delta, _ = _prepare_xy(df)
    X_all_pre, y_all_pre, _ = _prepare_xy(df[df["season_code"] == 1])
    X_all_post, y_all_post, _ = _prepare_xy(df[df["season_code"] == 0])

    prod_g = _make_xgb(best_cfg, n_estimators=best_median_iters)
    prod_pre = _make_xgb(best_cfg, n_estimators=spec_iters)
    prod_post = _make_xgb(best_cfg, n_estimators=spec_iters)
    prod_p10 = _make_quantile_xgb(0.10, n_estimators=min(best_median_iters, 220))
    prod_p90 = _make_quantile_xgb(0.90, n_estimators=min(best_median_iters, 220))

    prod_g.fit(X_all, y_all_delta, verbose=False)
    prod_pre.fit(X_all_pre, y_all_pre, verbose=False)
    prod_post.fit(X_all_post, y_all_post, verbose=False)
    prod_p10.fit(X_all, y_all_delta, verbose=False)
    prod_p90.fit(X_all, y_all_delta, verbose=False)

    prod_g.save_model(str(out_dir / "model_p50.json"))
    prod_pre.save_model(str(out_dir / "model_pre_p50.json"))
    prod_post.save_model(str(out_dir / "model_post_p50.json"))
    prod_p10.save_model(str(out_dir / "model_p10.json"))
    prod_p90.save_model(str(out_dir / "model_p90.json"))

    importances = {
        col: round(float(imp), 4)
        for col, imp in sorted(
            zip(FEATURE_COLUMNS, prod_g.feature_importances_),
            key=lambda kv: kv[1],
            reverse=True,
        )
    }

    thresholds = calibrate_thresholds_from_data(df["depth_mbgl"])
    use_fallback = not eval_report["beats_baseline"]

    metrics_doc: dict[str, Any] = {
        "model_version": f"xgb-dual-specialist-cqr-v2-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        "target_formulation": "residual_over_seasonal_naive",
        "trained_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "active_serving_strategy": (
            "baseline_plus_trend_fallback" if use_fallback else "dual_season_monotone_xgb_plus_cqr"
        ),
        "selected_hyperparameter_config": best_cfg,
        "best_n_estimators": best_median_iters,
        "specialist_n_estimators": spec_iters,
        "season_blend_weights": blend_weights,
        "cqr_offset_mbgl": round(cqr_offset, 4),
        "conformal_residual_adjustment": False,
        "residual_q10_mbgl": round(res_q10, 4),
        "residual_q90_mbgl": round(res_q90, 4),
        "walk_forward_cv_leaderboard": cv_leaderboard,
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
    parser = argparse.ArgumentParser(description="Train WellCast v2 Dual-Specialist XGBoost + CQR models")
    parser.add_argument(
        "--train",
        default=os.environ.get(
            "SM_CHANNEL_TRAIN", str(REPO_ROOT / "data" / "processed_local" / "curated" / "ml_train")
        ),
    )
    parser.add_argument(
        "--model-dir",
        default=os.environ.get("SM_MODEL_DIR", str(REPO_ROOT / "ml" / "artifacts_local")),
    )
    args = parser.parse_args()
    train_and_evaluate(args.train, args.model_dir)


if __name__ == "__main__":
    main()
