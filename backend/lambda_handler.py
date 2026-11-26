"""WellCast Serverless API Handler (AWS Lambda + Local Dev Compatible).

Serves precomputed groundwater forecasts, confidence intervals, historical observations,
and planner block rankings from Amazon S3 (`api/` prefix) with an in-memory TTL cache.
When `USE_LOCAL_API=1` or `FORECAST_BUCKET` is unset, reads the identical relative keys
from `LOCAL_API_DIR` (`data/processed_local/api`) for zero-cost local development and testing.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("wellcast.api")
logger.setLevel(logging.INFO)

ALLOWED_SCENARIOS = ("normal", "minus10", "minus20", "minus30")
BLOCK_ID_PATTERN = re.compile(r"^[A-Z]{2}-[A-Z0-9]{3}-[0-9]{3}$")

_CACHE: dict[str, tuple[float, Any]] = {}
_S3_CLIENT = None


def _get_s3_client():
    global _S3_CLIENT
    if _S3_CLIENT is None:
        import boto3

        _S3_CLIENT = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
    return _S3_CLIENT


def clear_cache() -> None:
    """Clear in-memory response cache (used in unit tests)."""
    _CACHE.clear()


def _cors_headers() -> dict[str, str]:
    allowed_origin = os.environ.get("ALLOWED_ORIGIN", "*")
    return {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": allowed_origin,
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Cache-Control": "public, max-age=300",
    }


def _json_response(status_code: int, payload: Any) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": _cors_headers(),
        "body": json.dumps(payload, ensure_ascii=False),
    }


class ObjectNotFoundError(Exception):
    """Raised when an API JSON object does not exist in S3 or local storage."""


def _read_api_json(rel_key: str) -> Any:
    """Read and parse `api/<rel_key>` with TTL caching from S3 or local directory."""
    ttl = int(os.environ.get("CACHE_TTL_SECONDS", "300"))
    now = time.monotonic()
    cached = _CACHE.get(rel_key)
    if cached is not None and (now - cached[0]) < ttl:
        return cached[1]

    bucket = os.environ.get("FORECAST_BUCKET", "").strip()
    use_local = os.environ.get("USE_LOCAL_API", "").strip() == "1" or not bucket

    if use_local:
        base_dir = Path(os.environ.get("LOCAL_API_DIR", "data/processed_local/api"))
        target = (base_dir / rel_key).resolve()
        if not str(target).startswith(str(base_dir.resolve())) or not target.is_file():
            raise ObjectNotFoundError(rel_key)
        data = json.loads(target.read_text(encoding="utf-8"))
    else:
        s3 = _get_s3_client()
        s3_key = f"api/{rel_key.lstrip('/')}"
        try:
            obj = s3.get_object(Bucket=bucket, Key=s3_key)
            data = json.loads(obj["Body"].read().decode("utf-8"))
        except Exception as exc:
            err_code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if err_code in ("NoSuchKey", "404", "NotFound") or exc.__class__.__name__ == "NoSuchKey":
                raise ObjectNotFoundError(rel_key) from exc
            raise

    _CACHE[rel_key] = (now, data)
    return data


def _extract_request(event: dict[str, Any]) -> tuple[str, str, dict[str, str], dict[str, str]]:
    """Normalize API Gateway HTTP API v2 and REST API v1 event shapes."""
    method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
        or "GET"
    ).upper()
    raw_path = event.get("rawPath") or event.get("path") or "/"
    # Strip stage prefix such as /prod if present
    for stage_prefix in ("/prod/", "/stage/", "/dev/"):
        if raw_path.startswith(stage_prefix):
            raw_path = "/" + raw_path[len(stage_prefix) :]
            break
    if raw_path == "/prod":
        raw_path = "/"
    path_params = event.get("pathParameters") or {}
    query_params = {k: v for k, v in (event.get("queryStringParameters") or {}).items() if v is not None}
    return method, raw_path.rstrip("/") or "/", path_params, query_params


def _normalize_state_code(state_param: str | None) -> str:
    if not state_param:
        return "MH"
    val = state_param.strip().upper()
    if val in ("MH", "MAHARASHTRA"):
        return "MH"
    return val[:2]


def _handle_health() -> dict[str, Any]:
    try:
        meta = _read_api_json("meta.json")
    except ObjectNotFoundError:
        meta = {}
    payload = {
        "status": "ok",
        "service": "wellcast-api",
        "region": os.environ.get("AWS_REGION", "ap-south-1"),
        "model_version": meta.get("model_version", "uninitialized"),
        "forecast_season": meta.get("forecast_season", "unknown"),
        "blocks_indexed": meta.get("blocks_indexed", 0),
        "generated_at": meta.get("generated_at"),
    }
    return _json_response(200, payload)


def _handle_blocks(query: dict[str, str]) -> dict[str, Any]:
    scenario = query.get("scenario", "normal").strip().lower()
    if scenario not in ALLOWED_SCENARIOS:
        return _json_response(
            400,
            {"error": f"Invalid scenario '{scenario}'. Allowed values: {', '.join(ALLOWED_SCENARIOS)}"},
        )

    key = f"blocks_{scenario}.json" if scenario != "normal" else "blocks.json"
    try:
        doc = _read_api_json(key)
    except ObjectNotFoundError:
        doc = _read_api_json("blocks.json")

    blocks = doc.get("blocks", [])
    state_filter = query.get("state", "").strip().upper()
    if state_filter and state_filter not in ("MH", "MAHARASHTRA"):
        blocks = [
            b
            for b in blocks
            if b.get("state", "").upper() == state_filter or b.get("block_id", "").startswith(state_filter + "-")
        ]

    district_filter = query.get("district", "").strip().lower()
    if district_filter:
        blocks = [b for b in blocks if district_filter in b.get("district", "").lower()]

    return _json_response(
        200,
        {
            "state": doc.get("state", "Maharashtra"),
            "granularity": doc.get("granularity", "block"),
            "scenario": scenario,
            "forecast_season": doc.get("forecast_season"),
            "count": len(blocks),
            "blocks": blocks,
        },
    )


def _handle_forecast(block_id: str, query: dict[str, str]) -> dict[str, Any]:
    block_id_clean = block_id.strip().upper()
    if not BLOCK_ID_PATTERN.match(block_id_clean):
        return _json_response(
            400,
            {"error": "Malformed block_id. Expected format like MH-PUN-012.", "block_id": block_id},
        )

    scenario = query.get("scenario", "normal").strip().lower()
    if scenario not in ALLOWED_SCENARIOS:
        return _json_response(
            400,
            {"error": f"Invalid scenario '{scenario}'. Allowed values: {', '.join(ALLOWED_SCENARIOS)}"},
        )

    try:
        payload = _read_api_json(f"forecasts/{scenario}/{block_id_clean}.json")
    except ObjectNotFoundError:
        return _json_response(404, {"error": "Block not found", "block_id": block_id_clean})

    return _json_response(200, payload)


def _handle_history(block_id: str) -> dict[str, Any]:
    block_id_clean = block_id.strip().upper()
    if not BLOCK_ID_PATTERN.match(block_id_clean):
        return _json_response(
            400,
            {"error": "Malformed block_id. Expected format like MH-PUN-012.", "block_id": block_id},
        )

    try:
        payload = _read_api_json(f"history/{block_id_clean}.json")
    except ObjectNotFoundError:
        return _json_response(404, {"error": "Block not found", "block_id": block_id_clean})

    return _json_response(200, payload)


def _handle_rankings(query: dict[str, str]) -> dict[str, Any]:
    scenario = query.get("scenario", "normal").strip().lower()
    if scenario not in ALLOWED_SCENARIOS:
        return _json_response(
            400,
            {"error": f"Invalid scenario '{scenario}'. Allowed values: {', '.join(ALLOWED_SCENARIOS)}"},
        )

    raw_limit = query.get("limit", "20").strip()
    try:
        limit = int(raw_limit)
    except ValueError:
        return _json_response(400, {"error": "Parameter 'limit' must be an integer between 1 and 500."})
    if limit < 1 or limit > 500:
        return _json_response(400, {"error": "Parameter 'limit' must be between 1 and 500."})

    state_code = _normalize_state_code(query.get("state"))
    try:
        doc = _read_api_json(f"rankings/{state_code}_{scenario}.json")
    except ObjectNotFoundError:
        try:
            doc = _read_api_json(f"rankings/{state_code}.json")
        except ObjectNotFoundError:
            return _json_response(404, {"error": f"No rankings available for state '{state_code}'."})

    rows = doc.get("rankings", [])
    district_filter = query.get("district", "").strip().lower()
    if district_filter:
        rows = [r for r in rows if district_filter in r.get("district", "").lower()]

    sliced = []
    for idx, item in enumerate(rows[:limit], start=1):
        entry = dict(item)
        entry["rank"] = idx
        sliced.append(entry)

    return _json_response(
        200,
        {
            "state": doc.get("state", "Maharashtra"),
            "scenario": scenario,
            "forecast_season": doc.get("forecast_season"),
            "summary": doc.get("summary", {}),
            "count": len(sliced),
            "rankings": sliced,
        },
    )


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """AWS Lambda entry point for API Gateway HTTP API / REST API."""
    t0 = time.perf_counter()
    method, path, path_params, query = _extract_request(event)

    if method == "OPTIONS":
        return {"statusCode": 204, "headers": _cors_headers(), "body": ""}

    try:
        if method != "GET":
            resp = _json_response(405, {"error": f"Method {method} not allowed."})
        elif path == "/health":
            resp = _handle_health()
        elif path == "/blocks":
            resp = _handle_blocks(query)
        elif path == "/rankings":
            resp = _handle_rankings(query)
        else:
            m_forecast = re.match(r"^/blocks/([^/]+)/forecast$", path)
            m_history = re.match(r"^/blocks/([^/]+)/history$", path)
            if m_forecast:
                block_id = path_params.get("block_id") or path_params.get("id") or m_forecast.group(1)
                resp = _handle_forecast(block_id, query)
            elif m_history:
                block_id = path_params.get("block_id") or path_params.get("id") or m_history.group(1)
                resp = _handle_history(block_id)
            else:
                resp = _json_response(404, {"error": f"Route not found: {path}"})
    except Exception as exc:
        logger.exception("Unhandled error serving %s %s", method, path)
        resp = _json_response(500, {"error": "Internal server error", "detail": type(exc).__name__})

    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    logger.info(
        json.dumps(
            {
                "method": method,
                "path": path,
                "status": resp["statusCode"],
                "latency_ms": latency_ms,
            }
        )
    )
    return resp
