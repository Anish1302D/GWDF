"""Phase 4 v2 Batch Forecast & Precomputed Scenario Engine + Static API JSON Exporter.

Scores next-season groundwater depth (`mbgl`), CQR-calibrated P10-P90 uncertainty bounds,
and calibrated risk classes across 4 rainfall scenarios (`normal` 100%, `minus10` 90%,
`minus20` 80%, `minus30` 70%) using the Dual Season-Specialist + Global Monotone XGBoost ensemble.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import xgboost as xgb

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.evaluate import FEATURE_COLUMNS, enforce_prediction_bounds  # noqa: E402
from ml.risk_rules import classify_risk, get_advice  # noqa: E402
from ml.train import predict_blended_delta  # noqa: E402

SCENARIO_CONFIG: list[tuple[str, int, float]] = [
    ("normal", 100, 1.00),
    ("minus10", 90, 0.90),
    ("minus20", 80, 0.80),
    ("minus30", 70, 0.70),
]


def _next_season_label(obs_date_str: str, season: str) -> str:
    yr = int(str(obs_date_str)[:4])
    if season == "pre-monsoon":
        return f"{yr}-post-monsoon"
    return f"{yr + 1}-pre-monsoon"


def _load_models(
    artifacts_dir: Path,
) -> tuple[xgb.XGBRegressor, xgb.XGBRegressor | None, xgb.XGBRegressor | None, xgb.XGBRegressor, xgb.XGBRegressor, dict[str, Any]]:
    metrics = json.loads((artifacts_dir / "metrics.json").read_text(encoding="utf-8"))
    m_p50 = xgb.XGBRegressor()
    m_p10 = xgb.XGBRegressor()
    m_p90 = xgb.XGBRegressor()
    m_p50.load_model(str(artifacts_dir / "model_p50.json"))
    m_p10.load_model(str(artifacts_dir / "model_p10.json"))
    m_p90.load_model(str(artifacts_dir / "model_p90.json"))

    m_pre = None
    m_post = None
    if (artifacts_dir / "model_pre_p50.json").is_file() and (artifacts_dir / "model_post_p50.json").is_file():
        m_pre = xgb.XGBRegressor()
        m_post = xgb.XGBRegressor()
        m_pre.load_model(str(artifacts_dir / "model_pre_p50.json"))
        m_post.load_model(str(artifacts_dir / "model_post_p50.json"))

    return m_p50, m_pre, m_post, m_p10, m_p90, metrics


def _build_scenario_features(infer_df: pd.DataFrame, mult: float) -> pd.DataFrame:
    df_s = infer_df.copy()
    r3_norm = df_s["rain_3m_normal_mm"].fillna(df_s["rain_3m_mm"]).clip(lower=0.0)
    r6_norm = df_s["rain_6m_normal_mm"].fillna(df_s["rain_6m_mm"]).clip(lower=0.0)
    r12_norm = df_s["rain_12m_normal_mm"].fillna(df_s["rain_12m_mm"]).clip(lower=1.0)
    r24_norm = df_s["rain_24m_normal_mm"].fillna(df_s["rain_24m_mm"]).clip(lower=1.0)

    # Perturb full annual/seasonal monsoon recharge budget by multiplier `mult`
    prior_12m = (df_s["rain_24m_mm"] - df_s["rain_12m_mm"]).clip(lower=0.0)

    df_s["rain_3m_mm"] = (mult * r3_norm).round(2)
    df_s["rain_6m_mm"] = (mult * r6_norm).round(2)
    df_s["rain_12m_mm"] = (mult * r12_norm).round(2)
    df_s["rain_24m_mm"] = (prior_12m + df_s["rain_12m_mm"]).round(2)

    df_s["rain_departure_6m_pct"] = round((mult - 1.0) * 100.0, 2)
    df_s["rain_departure_12m_pct"] = round((mult - 1.0) * 100.0, 2)
    df_s["rain_departure_24m_pct"] = (
        ((df_s["rain_24m_mm"] - r24_norm) / r24_norm) * 100.0
    ).round(2)

    X = df_s[FEATURE_COLUMNS].copy()
    for c in FEATURE_COLUMNS:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    return X


def main() -> None:
    processed = REPO_ROOT / "data" / "processed_local"
    artifacts_dir = REPO_ROOT / "ml" / "artifacts_local"
    api_dir = processed / "api"
    forecasts_parquet_dir = processed / "forecasts"
    forecasts_parquet_dir.mkdir(parents=True, exist_ok=True)

    blocks_df = pd.read_parquet(processed / "raw" / "block" / "blocks.parquet")
    wl_df = pd.read_parquet(processed / "raw" / "water_level" / "water_level.parquet")
    rain_df = pd.read_parquet(processed / "raw" / "rainfall_monthly" / "rainfall_monthly.parquet")
    infer_df = pd.read_parquet(processed / "curated" / "ml_inference" / "latest_features.parquet")

    m_p50, m_pre, m_post, m_p10, m_p90, metrics = _load_models(artifacts_dir)
    thresholds = metrics["calibrated_risk_thresholds"]
    model_version = metrics["model_version"]
    cqr_offset = float(metrics.get("cqr_offset_mbgl", 0.0))
    blend_weights = metrics.get("season_blend_weights")
    res_q10 = float(metrics.get("residual_q10_mbgl", -1.2))
    res_q90 = float(metrics.get("residual_q90_mbgl", 1.2))
    use_fallback = metrics.get("active_serving_strategy") == "baseline_plus_trend_fallback"
    is_residual = metrics.get("target_formulation") == "residual_over_seasonal_naive"
    generated_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    infer_df["obs_date_str"] = infer_df["obs_date"].astype(str)
    infer_df["next_season_label"] = [
        _next_season_label(d, s) for d, s in zip(infer_df["obs_date_str"], infer_df["season"])
    ]
    dominant_forecast_season = str(infer_df["next_season_label"].mode().iloc[0])

    infer_df["latest_year"] = infer_df["obs_date_str"].str.slice(0, 4).astype(int)
    eligible_mask = (infer_df["block_total_obs"] >= 4) & (infer_df["latest_year"] >= 2022)
    eligible_df = infer_df[eligible_mask].copy().reset_index(drop=True)

    scenario_predictions: dict[str, dict[str, dict[str, Any]]] = {}
    s_codes = eligible_df["season_code"].to_numpy()
    base_anchor = eligible_df["prev_depth_mbgl"].fillna(eligible_df["depth_mbgl"]).to_numpy(dtype=float)

    for scen_key, rain_pct, mult in SCENARIO_CONFIG:
        X_s = _build_scenario_features(eligible_df, mult)
        if use_fallback:
            trend = np.clip(eligible_df["depth_trend_5yr"].fillna(0.0).to_numpy(dtype=float), -2.0, 2.0)
            drought_bump = (1.0 - mult) * 3.5
            p50_raw = base_anchor + 0.5 * trend + drought_bump
            p10_raw = p50_raw + res_q10
            p90_raw = p50_raw + res_q90
        else:
            offset = base_anchor if is_residual else 0.0
            if m_pre is not None and m_post is not None and blend_weights is not None:
                delta_pred = predict_blended_delta(X_s, s_codes, m_p50, m_pre, m_post, blend_weights)
            else:
                delta_pred = m_p50.predict(X_s)
            p50_raw = offset + delta_pred
            p10_raw = offset + m_p10.predict(X_s) - cqr_offset
            p90_raw = offset + m_p90.predict(X_s) + cqr_offset

        p50, low, high = enforce_prediction_bounds(p50_raw, p10_raw, p90_raw)
        scen_map: dict[str, dict[str, Any]] = {}
        for idx, row in enumerate(eligible_df.itertuples(index=False)):
            ref_same_season = (
                float(row.prev_depth_mbgl) if pd.notna(row.prev_depth_mbgl) else float(row.depth_mbgl)
            )
            yoy_delta = round(float(p50[idx]) - ref_same_season, 2)
            trend_5 = float(row.depth_trend_5yr) if pd.notna(row.depth_trend_5yr) else 0.0
            r_class, r_score = classify_risk(float(p50[idx]), yoy_delta, trend_5, thresholds)
            scen_map[row.block_id] = {
                "scenario": scen_key,
                "rainfall_pct_of_normal": rain_pct,
                "forecast_season": _next_season_label(str(row.obs_date), str(row.season)),
                "current_obs_date": str(row.obs_date),
                "current_depth_mbgl": round(float(row.depth_mbgl), 2),
                "predicted_depth_mbgl": float(p50[idx]),
                "lower_bound": float(low[idx]),
                "upper_bound": float(high[idx]),
                "predicted_yoy_change_mbgl": yoy_delta,
                "depth_trend_5yr": round(trend_5, 2),
                "well_count": int(row.well_count),
                "risk_class": r_class,
                "risk_score": r_score,
            }
        scenario_predictions[scen_key] = scen_map

    means = {
        s: round(float(np.mean([v["predicted_depth_mbgl"] for v in scenario_predictions[s].values()])), 3)
        for s, _, _ in SCENARIO_CONFIG
    }
    assert means["normal"] <= means["minus10"] + 1e-6 <= means["minus20"] + 2e-6 <= means["minus30"] + 3e-6, (
        f"Scenario monotonicity violated! Mean predicted depths: {means}"
    )

    for scen_key, _, _ in SCENARIO_CONFIG:
        (api_dir / "forecasts" / scen_key).mkdir(parents=True, exist_ok=True)
    (api_dir / "history").mkdir(parents=True, exist_ok=True)
    (api_dir / "rankings").mkdir(parents=True, exist_ok=True)

    parquet_rows: list[dict[str, Any]] = []

    for scen_key, rain_pct, _ in SCENARIO_CONFIG:
        blocks_list: list[dict[str, Any]] = []
        rankings_list: list[dict[str, Any]] = []
        summary_counts = {
            "total_blocks": int(len(blocks_df)),
            "critical": 0,
            "watch": 0,
            "safe": 0,
            "insufficient_data": 0,
        }

        for b in blocks_df.itertuples(index=False):
            pred_info = scenario_predictions[scen_key].get(b.block_id)
            if pred_info is None:
                summary_counts["insufficient_data"] += 1
                payload = {
                    "block_id": b.block_id,
                    "state": b.state,
                    "district": b.district,
                    "block_name": b.block_name,
                    "granularity": b.granularity,
                    "scenario": scen_key,
                    "rainfall_pct_of_normal": rain_pct,
                    "forecast_season": dominant_forecast_season,
                    "current_obs_date": None,
                    "current_depth_mbgl": None,
                    "predicted_depth_mbgl": None,
                    "lower_bound": None,
                    "upper_bound": None,
                    "predicted_yoy_change_mbgl": None,
                    "depth_trend_5yr": None,
                    "extraction_stage": b.extraction_stage,
                    "risk_class": "Insufficient Data",
                    "risk_score": 0.0,
                    "well_count": 0,
                    "is_imputed_history": False,
                    "rainfall_source_level": "district_gridded",
                    "advice": get_advice("Insufficient Data"),
                    "available_scenarios": [s[0] for s in SCENARIO_CONFIG],
                }
            else:
                rc = pred_info["risk_class"]
                summary_counts[rc.lower()] += 1
                payload = {
                    "block_id": b.block_id,
                    "state": b.state,
                    "district": b.district,
                    "block_name": b.block_name,
                    "granularity": b.granularity,
                    "scenario": scen_key,
                    "rainfall_pct_of_normal": rain_pct,
                    "forecast_season": pred_info["forecast_season"],
                    "current_obs_date": pred_info["current_obs_date"],
                    "current_depth_mbgl": pred_info["current_depth_mbgl"],
                    "predicted_depth_mbgl": pred_info["predicted_depth_mbgl"],
                    "lower_bound": pred_info["lower_bound"],
                    "upper_bound": pred_info["upper_bound"],
                    "predicted_yoy_change_mbgl": pred_info["predicted_yoy_change_mbgl"],
                    "depth_trend_5yr": pred_info["depth_trend_5yr"],
                    "extraction_stage": b.extraction_stage,
                    "risk_class": rc,
                    "risk_score": pred_info["risk_score"],
                    "well_count": pred_info["well_count"],
                    "is_imputed_history": False,
                    "rainfall_source_level": "district_gridded",
                    "advice": get_advice(rc),
                    "available_scenarios": [s[0] for s in SCENARIO_CONFIG],
                }
                rankings_list.append(
                    {
                        "block_id": b.block_id,
                        "district": b.district,
                        "block_name": b.block_name,
                        "extraction_stage": b.extraction_stage,
                        "current_depth_mbgl": pred_info["current_depth_mbgl"],
                        "predicted_depth_mbgl": pred_info["predicted_depth_mbgl"],
                        "lower_bound": pred_info["lower_bound"],
                        "upper_bound": pred_info["upper_bound"],
                        "predicted_yoy_change_mbgl": pred_info["predicted_yoy_change_mbgl"],
                        "well_count": pred_info["well_count"],
                        "risk_class": rc,
                        "risk_score": pred_info["risk_score"],
                    }
                )

            (api_dir / "forecasts" / scen_key / f"{b.block_id}.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            blocks_list.append(
                {
                    "block_id": b.block_id,
                    "state": b.state,
                    "district": b.district,
                    "block_name": b.block_name,
                    "lat": float(b.lat),
                    "lon": float(b.lon),
                    "extraction_stage": b.extraction_stage,
                    "current_depth_mbgl": payload["current_depth_mbgl"],
                    "predicted_depth_mbgl": payload["predicted_depth_mbgl"],
                    "lower_bound": payload["lower_bound"],
                    "upper_bound": payload["upper_bound"],
                    "well_count": payload["well_count"],
                    "risk_class": payload["risk_class"],
                    "risk_score": payload["risk_score"],
                }
            )
            parquet_rows.append(
                {
                    "block_id": b.block_id,
                    "state": b.state,
                    "district": b.district,
                    "block_name": b.block_name,
                    "scenario": scen_key,
                    "rainfall_pct_of_normal": rain_pct,
                    "forecast_season": payload["forecast_season"],
                    "current_depth_mbgl": payload["current_depth_mbgl"],
                    "predicted_depth_mbgl": payload["predicted_depth_mbgl"],
                    "lower_bound": payload["lower_bound"],
                    "upper_bound": payload["upper_bound"],
                    "predicted_yoy_change_mbgl": payload["predicted_yoy_change_mbgl"],
                    "risk_class": payload["risk_class"],
                    "risk_score": payload["risk_score"],
                    "model_version": model_version,
                    "generated_at": pd.Timestamp.now(tz="UTC"),
                }
            )

        blocks_doc = {
            "state": "Maharashtra",
            "granularity": "block",
            "scenario": scen_key,
            "forecast_season": dominant_forecast_season,
            "count": len(blocks_list),
            "blocks": blocks_list,
        }
        (api_dir / f"blocks_{scen_key}.json").write_text(json.dumps(blocks_doc, ensure_ascii=False), encoding="utf-8")
        if scen_key == "normal":
            (api_dir / "blocks.json").write_text(json.dumps(blocks_doc, ensure_ascii=False), encoding="utf-8")

        rankings_list.sort(key=lambda r: (r["risk_score"], r["predicted_depth_mbgl"] or 0.0), reverse=True)
        for idx, item in enumerate(rankings_list, start=1):
            item["rank"] = idx

        rank_doc = {
            "state": "Maharashtra",
            "scenario": scen_key,
            "forecast_season": dominant_forecast_season,
            "summary": summary_counts,
            "rankings": rankings_list,
        }
        (api_dir / "rankings" / f"MH_{scen_key}.json").write_text(
            json.dumps(rank_doc, ensure_ascii=False), encoding="utf-8"
        )
        if scen_key == "normal":
            (api_dir / "rankings" / "MH.json").write_text(
                json.dumps(rank_doc, ensure_ascii=False), encoding="utf-8"
            )

    wl_sorted = wl_df.sort_values(["block_id", "obs_date"])
    wl_by_blk = {k: g for k, g in wl_sorted.groupby("block_id")}

    rain_df["month_dt"] = pd.to_datetime(rain_df["month"])
    rain_df["yr"] = rain_df["month_dt"].dt.year
    rain_df["mo"] = rain_df["month_dt"].dt.month
    monsoon_df = (
        rain_df[rain_df["mo"].isin([6, 7, 8, 9])]
        .groupby(["block_id", "yr"], as_index=False)
        .agg(rainfall_mm=("rainfall_mm", "sum"), normal_mm=("normal_rainfall_mm", "sum"))
        .sort_values(["block_id", "yr"])
    )
    monsoon_df["departure_pct"] = np.where(
        monsoon_df["normal_mm"] > 1.0,
        ((monsoon_df["rainfall_mm"] - monsoon_df["normal_mm"]) / monsoon_df["normal_mm"]) * 100.0,
        0.0,
    ).round(1)
    rain_by_blk = {k: g for k, g in monsoon_df.groupby("block_id")}

    for b in blocks_df.itertuples(index=False):
        g_wl = wl_by_blk.get(b.block_id)
        wl_items = [
            {
                "obs_date": str(r.obs_date),
                "season": r.season,
                "depth_mbgl": float(r.depth_mbgl),
                "well_count": int(r.well_count),
                "is_imputed": bool(r.is_imputed),
            }
            for r in (g_wl.tail(24).itertuples(index=False) if g_wl is not None else [])
        ]
        g_rn = rain_by_blk.get(b.block_id)
        rn_items = [
            {
                "period": f"{int(r.yr)}-monsoon",
                "rainfall_mm": round(float(r.rainfall_mm), 1),
                "normal_mm": round(float(r.normal_mm), 1),
                "departure_pct": float(r.departure_pct),
            }
            for r in (g_rn.tail(12).itertuples(index=False) if g_rn is not None else [])
        ]
        (api_dir / "history" / f"{b.block_id}.json").write_text(
            json.dumps(
                {
                    "block_id": b.block_id,
                    "block_name": b.block_name,
                    "district": b.district,
                    "water_levels": wl_items,
                    "rainfall_seasonal": rn_items,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    forecasts_df = pd.DataFrame(parquet_rows)
    f_parquet_path = forecasts_parquet_dir / "forecasts.parquet"
    forecasts_df.to_parquet(f_parquet_path, index=False)

    meta_doc = {
        "model_version": model_version,
        "serving_strategy": metrics.get("active_serving_strategy"),
        "forecast_season": dominant_forecast_season,
        "blocks_indexed": int(len(blocks_df)),
        "blocks_forecasted": int(len(eligible_df)),
        "holdout_mae_mbgl": metrics["holdout_evaluation"]["xgboost_model"]["mae"],
        "baseline_mae_mbgl": metrics["holdout_evaluation"]["baseline_seasonal_naive"]["mae"],
        "skill_vs_baseline_pct": metrics["holdout_evaluation"]["skill_vs_baseline_pct"],
        "rmse_skill_vs_baseline_pct": metrics["holdout_evaluation"]["rmse_skill_vs_baseline_pct"],
        "p10_p90_coverage_pct": metrics["holdout_evaluation"]["p10_p90_coverage_pct"],
        "mean_interval_width_mbgl": metrics["holdout_evaluation"]["mean_interval_width_mbgl"],
        "scenario_mean_predicted_depth_mbgl": means,
        "generated_at": generated_ts,
    }
    (api_dir / "meta.json").write_text(json.dumps(meta_doc, indent=2), encoding="utf-8")

    con = duckdb.connect(":memory:")
    con.execute(f"CREATE VIEW forecasts AS SELECT * FROM read_parquet('{f_parquet_path.as_posix()}');")
    top5 = con.execute(
        """
        SELECT block_id, district, block_name, current_depth_mbgl, predicted_depth_mbgl, risk_class, risk_score
        FROM forecasts
        WHERE scenario = 'normal' AND risk_class <> 'Insufficient Data'
        ORDER BY risk_score DESC
        LIMIT 5
        """
    ).fetchdf()
    print("=== V2 FORECAST GENERATION SUMMARY ===")
    print(json.dumps(meta_doc, indent=2))
    print("=== TOP 5 AT-RISK BLOCKS (NORMAL SCENARIO) ===")
    print(top5.to_string(index=False))


if __name__ == "__main__":
    main()
