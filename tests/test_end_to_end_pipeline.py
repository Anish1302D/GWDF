"""End-to-end verification tests for Pan-India WellCast (35 States/UTs, SQL Anti-Leakage, ML, and API)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backend.lambda_handler import clear_cache, handler

REPO_ROOT = Path(__file__).resolve().parent.parent
PROCESSED = REPO_ROOT / "data" / "processed_local"
ARTIFACTS = REPO_ROOT / "ml" / "artifacts_local"


def test_all_india_raw_parquet_tables_and_quality() -> None:
    blocks = pd.read_parquet(PROCESSED / "raw" / "block" / "blocks.parquet")
    wl = pd.read_parquet(PROCESSED / "raw" / "water_level" / "water_level.parquet")
    rain = pd.read_parquet(PROCESSED / "raw" / "rainfall_monthly" / "rainfall_monthly.parquet")

    assert len(blocks) >= 5500
    assert blocks["state_code"].nunique() >= 30
    assert blocks["block_id"].is_unique

    assert len(wl) > 50000
    assert (wl["depth_mbgl"] > 0).all() and (wl["depth_mbgl"] <= 250).all()
    assert not wl.duplicated(subset=["block_id", "obs_date"]).any()

    assert len(rain) > 500000
    assert (rain["rainfall_mm"] >= 0).all()


def test_anti_leakage_features_and_pan_india_ml_artifacts() -> None:
    audit = json.loads((PROCESSED / "feature_audit.json").read_text(encoding="utf-8"))
    assert audit["anti_leakage_audit_passed"] is True
    assert audit["duplicate_keys"] == 0
    assert 4 <= audit["min_forward_horizon_months"] <= audit["max_forward_horizon_months"] <= 8

    metrics = json.loads((ARTIFACTS / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["split"]["max_train_target_date"] < metrics["split"]["min_test_target_date"]
    assert metrics["holdout_evaluation"]["beats_baseline"] is True
    assert metrics["holdout_evaluation"]["p10_p90_coverage_pct"] >= 70.0


def test_pan_india_scenarios_and_lambda_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    forecasts = pd.read_parquet(PROCESSED / "forecasts" / "forecasts.parquet")
    valid = forecasts[forecasts["risk_class"] != "Insufficient Data"]
    assert len(valid) >= 3500 * 4
    assert (valid["lower_bound"] <= valid["predicted_depth_mbgl"]).all()
    assert (valid["predicted_depth_mbgl"] <= valid["upper_bound"]).all()

    means = valid.groupby("scenario")["predicted_depth_mbgl"].mean().to_dict()
    assert means["normal"] <= means["minus10"] <= means["minus20"] <= means["minus30"]

    monkeypatch.setenv("USE_LOCAL_API", "1")
    monkeypatch.setenv("LOCAL_API_DIR", str(PROCESSED / "api"))
    clear_cache()

    # 1. Health check
    h = json.loads(handler({"rawPath": "/health"})["body"])
    assert h["states_indexed"] >= 30
    assert h["blocks_forecasted"] >= 3500

    # 2. National states summary
    st_res = handler({"rawPath": "/states", "queryStringParameters": {"scenario": "normal"}})
    assert st_res["statusCode"] == 200
    states = json.loads(st_res["body"])["states"]
    assert len(states) >= 30

    # 3. Multi-state block queries (Punjab, Rajasthan, Tamil Nadu, Maharashtra)
    for st_code in ("PB", "RJ", "TN", "MH"):
        b_res = handler({"rawPath": "/blocks", "queryStringParameters": {"state": st_code}})
        assert b_res["statusCode"] == 200
        blks = json.loads(b_res["body"])["blocks"]
        assert len(blks) >= 20
        pick = next(b for b in blks if b["risk_class"] != "Insufficient Data")
        f_norm = json.loads(
            handler({"rawPath": f"/blocks/{pick['block_id']}/forecast", "queryStringParameters": {"scenario": "normal"}})["body"]
        )
        f_dry = json.loads(
            handler({"rawPath": f"/blocks/{pick['block_id']}/forecast", "queryStringParameters": {"scenario": "minus30"}})["body"]
        )
        assert f_norm["predicted_depth_mbgl"] <= f_dry["predicted_depth_mbgl"]
        assert f_norm["normal_monsoon_mm"] > 0

    # 4. GPS Nearest Block Locator (New Delhi / NCR coordinates)
    near_res = handler({"rawPath": "/blocks/nearest", "queryStringParameters": {"lat": "28.6139", "lon": "77.2090"}})
    assert near_res["statusCode"] == 200
    assert json.loads(near_res["body"])["distance_km"] < 80

    # 5. All-India Rankings
    r_res = handler({"rawPath": "/rankings", "queryStringParameters": {"state": "ALL", "limit": "25"}})
    assert r_res["statusCode"] == 200
    ranks = json.loads(r_res["body"])["rankings"]
    assert len(ranks) == 25
    assert ranks[0]["risk_score"] >= ranks[-1]["risk_score"]
