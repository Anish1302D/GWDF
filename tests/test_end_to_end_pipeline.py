"""End-to-end verification tests across Data Lake Parquet, Anti-Leakage Features, ML Artifacts, and Real API JSONs."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backend.lambda_handler import clear_cache, handler

REPO_ROOT = Path(__file__).resolve().parent.parent
PROCESSED = REPO_ROOT / "data" / "processed_local"
ARTIFACTS = REPO_ROOT / "ml" / "artifacts_local"


def test_raw_parquet_tables_and_quality() -> None:
    blocks = pd.read_parquet(PROCESSED / "raw" / "block" / "blocks.parquet")
    wl = pd.read_parquet(PROCESSED / "raw" / "water_level" / "water_level.parquet")
    rain = pd.read_parquet(PROCESSED / "raw" / "rainfall_monthly" / "rainfall_monthly.parquet")

    assert len(blocks) >= 350
    assert blocks["district"].nunique() == 36
    assert blocks["block_id"].is_unique

    assert len(wl) > 5000
    assert (wl["depth_mbgl"] > 0).all() and (wl["depth_mbgl"] <= 250).all()
    assert not wl.duplicated(subset=["block_id", "obs_date"]).any()

    assert len(rain) > 50000
    assert (rain["rainfall_mm"] >= 0).all()
    assert not rain.duplicated(subset=["block_id", "month"]).any()


def test_anti_leakage_features_and_ml_artifacts() -> None:
    audit = json.loads((PROCESSED / "feature_audit.json").read_text(encoding="utf-8"))
    assert audit["anti_leakage_audit_passed"] is True
    assert audit["duplicate_keys"] == 0
    assert 4 <= audit["min_forward_horizon_months"] <= audit["max_forward_horizon_months"] <= 8

    metrics = json.loads((ARTIFACTS / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["split"]["max_train_target_date"] < metrics["split"]["min_test_target_date"]
    assert metrics["holdout_evaluation"]["p10_p90_coverage_pct"] >= 65.0
    assert (ARTIFACTS / "model_p50.json").is_file()
    assert (ARTIFACTS / "model_p10.json").is_file()
    assert (ARTIFACTS / "model_p90.json").is_file()


def test_forecast_scenarios_and_live_lambda_against_real_data(monkeypatch: pytest.MonkeyPatch) -> None:
    forecasts = pd.read_parquet(PROCESSED / "forecasts" / "forecasts.parquet")
    valid = forecasts[forecasts["risk_class"] != "Insufficient Data"]
    assert len(valid) >= 300 * 4
    assert (valid["lower_bound"] <= valid["predicted_depth_mbgl"]).all()
    assert (valid["predicted_depth_mbgl"] <= valid["upper_bound"]).all()

    # Check aggregate drought monotonicity: normal <= minus10 <= minus20 <= minus30
    means = valid.groupby("scenario")["predicted_depth_mbgl"].mean().to_dict()
    assert means["normal"] <= means["minus10"] <= means["minus20"] <= means["minus30"]

    # Invoke real Lambda handler against real generated Maharashtra API JSONs
    monkeypatch.setenv("USE_LOCAL_API", "1")
    monkeypatch.setenv("LOCAL_API_DIR", str(PROCESSED / "api"))
    clear_cache()

    h = handler({"rawPath": "/health"})
    assert h["statusCode"] == 200
    assert json.loads(h["body"])["blocks_indexed"] >= 350

    b_res = handler({"rawPath": "/blocks", "queryStringParameters": {"district": "Pune"}})
    assert b_res["statusCode"] == 200
    pune_blocks = json.loads(b_res["body"])["blocks"]
    assert len(pune_blocks) >= 10
    sample_id = pune_blocks[0]["block_id"]

    f_norm = json.loads(
        handler({"rawPath": f"/blocks/{sample_id}/forecast", "queryStringParameters": {"scenario": "normal"}})["body"]
    )
    f_drought = json.loads(
        handler({"rawPath": f"/blocks/{sample_id}/forecast", "queryStringParameters": {"scenario": "minus30"}})["body"]
    )
    assert f_norm["predicted_depth_mbgl"] <= f_drought["predicted_depth_mbgl"]
    assert set(f_norm["advice"].keys()) == {"en", "hi", "mr"}

    r_res = handler({"rawPath": "/rankings", "queryStringParameters": {"state": "MH", "limit": "15"}})
    assert r_res["statusCode"] == 200
    ranks = json.loads(r_res["body"])["rankings"]
    assert len(ranks) == 15
    assert ranks[0]["risk_score"] >= ranks[-1]["risk_score"]
