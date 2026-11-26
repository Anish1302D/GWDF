"""Unit & contract tests for `backend/lambda_handler.py` covering all 5 API routes."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.lambda_handler import clear_cache, handler


@pytest.fixture()
def mock_api_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    api_dir = tmp_path / "api"
    (api_dir / "forecasts" / "normal").mkdir(parents=True)
    (api_dir / "forecasts" / "minus30").mkdir(parents=True)
    (api_dir / "history").mkdir(parents=True)
    (api_dir / "rankings").mkdir(parents=True)

    (api_dir / "meta.json").write_text(
        json.dumps(
            {
                "model_version": "xgb-v1-test",
                "forecast_season": "2026-pre-monsoon",
                "blocks_indexed": 2,
                "generated_at": "2026-11-26T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    (api_dir / "blocks.json").write_text(
        json.dumps(
            {
                "state": "Maharashtra",
                "granularity": "block",
                "scenario": "normal",
                "forecast_season": "2026-pre-monsoon",
                "count": 2,
                "blocks": [
                    {
                        "block_id": "MH-PUN-001",
                        "state": "Maharashtra",
                        "district": "Pune",
                        "block_name": "Baramati",
                        "lat": 18.15,
                        "lon": 74.58,
                        "extraction_stage": "Semi-Critical",
                        "current_depth_mbgl": 11.2,
                        "predicted_depth_mbgl": 12.6,
                        "risk_class": "Watch",
                        "risk_score": 58.4,
                    },
                    {
                        "block_id": "MH-NAS-001",
                        "state": "Maharashtra",
                        "district": "Nashik",
                        "block_name": "Peint",
                        "lat": 20.21,
                        "lon": 73.60,
                        "extraction_stage": "Safe",
                        "current_depth_mbgl": 4.5,
                        "predicted_depth_mbgl": 5.1,
                        "risk_class": "Safe",
                        "risk_score": 19.2,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    for scen, pred, risk in [("normal", 12.6, "Watch"), ("minus30", 14.9, "Critical")]:
        (api_dir / "forecasts" / scen / "MH-PUN-001.json").write_text(
            json.dumps(
                {
                    "block_id": "MH-PUN-001",
                    "state": "Maharashtra",
                    "district": "Pune",
                    "block_name": "Baramati",
                    "granularity": "block",
                    "scenario": scen,
                    "rainfall_pct_of_normal": 100 if scen == "normal" else 70,
                    "forecast_season": "2026-pre-monsoon",
                    "current_depth_mbgl": 11.2,
                    "predicted_depth_mbgl": pred,
                    "lower_bound": round(pred - 1.3, 2),
                    "upper_bound": round(pred + 1.4, 2),
                    "predicted_yoy_change_mbgl": 1.1,
                    "extraction_stage": "Semi-Critical",
                    "risk_class": risk,
                    "risk_score": 58.4 if scen == "normal" else 79.1,
                    "advice": {"en": "Test advice", "hi": "परीक्षण सलाह", "mr": "चाचणी सल्ला"},
                    "available_scenarios": ["normal", "minus10", "minus20", "minus30"],
                }
            ),
            encoding="utf-8",
        )

    (api_dir / "history" / "MH-PUN-001.json").write_text(
        json.dumps(
            {
                "block_id": "MH-PUN-001",
                "block_name": "Baramati",
                "district": "Pune",
                "water_levels": [
                    {"obs_date": "2024-05-01", "season": "pre-monsoon", "depth_mbgl": 11.5, "well_count": 5, "is_imputed": False}
                ],
                "rainfall_seasonal": [
                    {"period": "2024-monsoon", "rainfall_mm": 510.0, "normal_mm": 540.0, "departure_pct": -5.6}
                ],
            }
        ),
        encoding="utf-8",
    )

    (api_dir / "rankings" / "MH_normal.json").write_text(
        json.dumps(
            {
                "state": "Maharashtra",
                "scenario": "normal",
                "forecast_season": "2026-pre-monsoon",
                "summary": {"total_blocks": 2, "critical": 0, "watch": 1, "safe": 1, "insufficient_data": 0},
                "rankings": [
                    {
                        "rank": 1,
                        "block_id": "MH-PUN-001",
                        "district": "Pune",
                        "block_name": "Baramati",
                        "risk_class": "Watch",
                        "risk_score": 58.4,
                        "predicted_depth_mbgl": 12.6,
                    },
                    {
                        "rank": 2,
                        "block_id": "MH-NAS-001",
                        "district": "Nashik",
                        "block_name": "Peint",
                        "risk_class": "Safe",
                        "risk_score": 19.2,
                        "predicted_depth_mbgl": 5.1,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("USE_LOCAL_API", "1")
    monkeypatch.setenv("LOCAL_API_DIR", str(api_dir))
    monkeypatch.setenv("ALLOWED_ORIGIN", "https://d123.cloudfront.net")
    clear_cache()
    return api_dir


def test_health_endpoint(mock_api_dir: Path) -> None:
    resp = handler({"rawPath": "/prod/health", "requestContext": {"http": {"method": "GET"}}})
    assert resp["statusCode"] == 200
    assert resp["headers"]["Access-Control-Allow-Origin"] == "https://d123.cloudfront.net"
    body = json.loads(resp["body"])
    assert body["status"] == "ok"
    assert body["blocks_indexed"] == 2


def test_blocks_list_and_district_filter(mock_api_dir: Path) -> None:
    resp = handler({"rawPath": "/blocks", "queryStringParameters": {"district": "pune"}})
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["count"] == 1
    assert body["blocks"][0]["block_id"] == "MH-PUN-001"


def test_forecast_scenarios_and_errors(mock_api_dir: Path) -> None:
    r_norm = handler({"rawPath": "/blocks/MH-PUN-001/forecast", "queryStringParameters": {"scenario": "normal"}})
    assert r_norm["statusCode"] == 200
    assert json.loads(r_norm["body"])["risk_class"] == "Watch"

    r_drought = handler({"rawPath": "/blocks/MH-PUN-001/forecast", "queryStringParameters": {"scenario": "minus30"}})
    assert r_drought["statusCode"] == 200
    assert json.loads(r_drought["body"])["risk_class"] == "Critical"

    r_missing = handler({"rawPath": "/blocks/MH-ZZZ-999/forecast"})
    assert r_missing["statusCode"] == 404

    r_bad_scen = handler({"rawPath": "/blocks/MH-PUN-001/forecast", "queryStringParameters": {"scenario": "minus99"}})
    assert r_bad_scen["statusCode"] == 400

    r_bad_id = handler({"rawPath": "/blocks/bad_id/forecast"})
    assert r_bad_id["statusCode"] == 400


def test_history_and_rankings(mock_api_dir: Path) -> None:
    r_hist = handler({"rawPath": "/blocks/MH-PUN-001/history"})
    assert r_hist["statusCode"] == 200
    assert len(json.loads(r_hist["body"])["water_levels"]) == 1

    r_rank = handler({"rawPath": "/rankings", "queryStringParameters": {"state": "MH", "limit": "1"}})
    assert r_rank["statusCode"] == 200
    body = json.loads(r_rank["body"])
    assert body["count"] == 1
    assert body["rankings"][0]["rank"] == 1
    assert body["rankings"][0]["block_id"] == "MH-PUN-001"


def test_cors_options_preflight(mock_api_dir: Path) -> None:
    resp = handler({"rawPath": "/blocks", "requestContext": {"http": {"method": "OPTIONS"}}})
    assert resp["statusCode"] == 204
    assert "GET" in resp["headers"]["Access-Control-Allow-Methods"]
