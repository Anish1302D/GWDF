"""WellCast Pan-India Serverless API Handler (AWS Lambda + Local Dev Compatible).

Supports all 36 Indian States & Union Territories:
  - `GET /health`
  - `GET /states?scenario=normal`               (National state-by-state groundwater risk summary)
  - `GET /blocks?state=MH&district=&scenario=`  (Per-state or ALL-India block index)
  - `GET /blocks/nearest?lat=&lon=&scenario=`   (GPS "Locate My Farm" nearest block finder)
  - `GET /blocks/{block_id}/forecast?scenario=` (Block forecast, CQR bounds, advice)
  - `GET /blocks/{block_id}/history`            (Historical levels + monsoon rainfall)
  - `GET /rankings?state=ALL|MH|PB|...&limit=`  (National or State top at-risk rankings)
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("wellcast.api")
logger.setLevel(logging.INFO)

ALLOWED_SCENARIOS = ("normal", "minus10", "minus20", "minus30")
BLOCK_ID_PATTERN = re.compile(r"^[A-Z]{2}-[A-Z0-9]{3}-[0-9]{3}$")

STATE_NAME_TO_CODE: dict[str, str] = {
    "ALL": "ALL",
    "INDIA": "ALL",
    "ANDAMAN AND NICOBAR ISLANDS": "AN",
    "ANDHRA PRADESH": "AP",
    "ARUNACHAL PRADESH": "AR",
    "ASSAM": "AS",
    "BIHAR": "BR",
    "CHANDIGARH": "CH",
    "CHHATTISGARH": "CG",
    "DADRA AND NAGAR HAVELI AND DAMAN AND DIU": "DN",
    "DELHI": "DL",
    "GOA": "GA",
    "GUJARAT": "GJ",
    "HARYANA": "HR",
    "HIMACHAL PRADESH": "HP",
    "JAMMU AND KASHMIR": "JK",
    "JHARKHAND": "JH",
    "KARNATAKA": "KA",
    "KERALA": "KL",
    "LADAKH": "LA",
    "LAKSHADWEEP": "LD",
    "MADHYA PRADESH": "MP",
    "MAHARASHTRA": "MH",
    "MANIPUR": "MN",
    "MEGHALAYA": "ML",
    "MIZORAM": "MZ",
    "NAGALAND": "NL",
    "ODISHA": "OD",
    "PUDUCHERRY": "PY",
    "PUNJAB": "PB",
    "RAJASTHAN": "RJ",
    "SIKKIM": "SK",
    "TAMIL NADU": "TN",
    "TELANGANA": "TG",
    "TRIPURA": "TR",
    "UTTAR PRADESH": "UP",
    "UTTARAKHAND": "UK",
    "WEST BENGAL": "WB",
}

_CACHE: dict[str, tuple[float, Any]] = {}
_S3_CLIENT = None


def _get_s3_client():
    global _S3_CLIENT
    if _S3_CLIENT is None:
        import boto3

        _S3_CLIENT = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-southeast-2"))
    return _S3_CLIENT


def clear_cache() -> None:
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
    pass


def _read_api_json(rel_key: str) -> Any:
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
    method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
        or "GET"
    ).upper()
    raw_path = event.get("rawPath") or event.get("path") or "/"
    for stage_prefix in ("/prod/", "/stage/", "/dev/"):
        if raw_path.startswith(stage_prefix):
            raw_path = "/" + raw_path[len(stage_prefix) :]
            break
    if raw_path == "/prod":
        raw_path = "/"
    path_params = event.get("pathParameters") or {}
    query_params = {k: v for k, v in (event.get("queryStringParameters") or {}).items() if v is not None}
    return method, raw_path.rstrip("/") or "/", path_params, query_params


def _normalize_state_code(state_param: str | None, default: str = "MH") -> str:
    if not state_param:
        return default
    val = state_param.strip().upper()
    if len(val) == 2 and val.isalpha():
        return val
    return STATE_NAME_TO_CODE.get(val, val[:2])


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2.0 * r * math.asin(math.sqrt(a))


def _handle_health() -> dict[str, Any]:
    try:
        meta = _read_api_json("meta.json")
    except ObjectNotFoundError:
        meta = {}
    return _json_response(
        200,
        {
            "status": "ok",
            "service": "wellcast-api",
            "scope": meta.get("scope", "All-India"),
            "region": os.environ.get("AWS_REGION", "ap-southeast-2"),
            "model_version": meta.get("model_version", "uninitialized"),
            "forecast_season": meta.get("forecast_season", "unknown"),
            "states_indexed": meta.get("states_indexed", 1),
            "blocks_indexed": meta.get("blocks_indexed", 0),
            "blocks_forecasted": meta.get("blocks_forecasted", 0),
            "generated_at": meta.get("generated_at"),
        },
    )


def _handle_states(query: dict[str, str]) -> dict[str, Any]:
    scenario = query.get("scenario", "normal").strip().lower()
    if scenario not in ALLOWED_SCENARIOS:
        return _json_response(
            400,
            {"error": f"Invalid scenario '{scenario}'. Allowed values: {', '.join(ALLOWED_SCENARIOS)}"},
        )
    for cand in (f"states_summary_{scenario}.json", "states_summary.json"):
        try:
            return _json_response(200, _read_api_json(cand))
        except ObjectNotFoundError:
            continue
    return _json_response(404, {"error": "States summary not found"})


def _handle_blocks(query: dict[str, str]) -> dict[str, Any]:
    scenario = query.get("scenario", "normal").strip().lower()
    if scenario not in ALLOWED_SCENARIOS:
        return _json_response(
            400,
            {"error": f"Invalid scenario '{scenario}'. Allowed values: {', '.join(ALLOWED_SCENARIOS)}"},
        )

    st_code = _normalize_state_code(query.get("state"), default="MH")
    doc = None
    candidates = [
        f"blocks/{st_code}_{scenario}.json",
        f"blocks/{st_code}_normal.json",
        f"blocks_{scenario}.json" if scenario != "normal" else "blocks.json",
        "blocks.json",
    ]
    for cand in candidates:
        try:
            doc = _read_api_json(cand)
            break
        except ObjectNotFoundError:
            continue

    if doc is None:
        return _json_response(404, {"error": f"No blocks found for state '{st_code}'."})

    blocks = doc.get("blocks", [])
    if st_code != "ALL" and doc.get("state_code") in (None, "ALL"):
        blocks = [b for b in blocks if b.get("block_id", "").startswith(st_code + "-")]

    district_filter = query.get("district", "").strip().lower()
    if district_filter:
        blocks = [b for b in blocks if district_filter in b.get("district", "").lower()]

    return _json_response(
        200,
        {
            "state_code": doc.get("state_code", st_code),
            "state": doc.get("state", st_code),
            "granularity": doc.get("granularity", "block"),
            "scenario": scenario,
            "forecast_season": doc.get("forecast_season"),
            "count": len(blocks),
            "blocks": blocks,
        },
    )


def _handle_nearest(query: dict[str, str]) -> dict[str, Any]:
    try:
        lat = float(query.get("lat", ""))
        lon = float(query.get("lon", ""))
    except ValueError:
        return _json_response(400, {"error": "Provide numeric 'lat' and 'lon' query parameters."})

    scenario = query.get("scenario", "normal").strip().lower()
    if scenario not in ALLOWED_SCENARIOS:
        scenario = "normal"

    doc = None
    for cand in (f"blocks/ALL_{scenario}.json", "blocks/ALL_normal.json", "blocks.json"):
        try:
            doc = _read_api_json(cand)
            break
        except ObjectNotFoundError:
            continue
    if not doc or not doc.get("blocks"):
        return _json_response(404, {"error": "Block coordinate index unavailable."})

    best_blk = None
    best_dist = float("inf")
    for b in doc["blocks"]:
        blat, blon = b.get("lat"), b.get("lon")
        if blat is None or blon is None:
            continue
        # Prefer blocks with active forecasts if within comparable distance
        d = _haversine_km(lat, lon, float(blat), float(blon))
        penalty = 25.0 if b.get("risk_class") == "Insufficient Data" else 0.0
        if d + penalty < best_dist:
            best_dist = d + penalty
            best_blk = b

    if best_blk is None:
        return _json_response(404, {"error": "No nearby block found."})

    actual_km = round(_haversine_km(lat, lon, float(best_blk["lat"]), float(best_blk["lon"])), 1)
    return _json_response(
        200,
        {
            "distance_km": actual_km,
            "block": best_blk,
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

    st_code = block_id_clean[:2]
    for bundle_key in (f"forecasts_bundle/{st_code}_{scenario}.json", f"forecasts_bundle_{scenario}.json"):
        try:
            bundle = _read_api_json(bundle_key)
            if block_id_clean in bundle:
                return _json_response(200, bundle[block_id_clean])
        except ObjectNotFoundError:
            pass

    try:
        payload = _read_api_json(f"forecasts/{scenario}/{block_id_clean}.json")
        return _json_response(200, payload)
    except ObjectNotFoundError:
        return _json_response(404, {"error": "Block not found", "block_id": block_id_clean})


def _handle_history(block_id: str) -> dict[str, Any]:
    block_id_clean = block_id.strip().upper()
    if not BLOCK_ID_PATTERN.match(block_id_clean):
        return _json_response(
            400,
            {"error": "Malformed block_id. Expected format like MH-PUN-012.", "block_id": block_id},
        )

    st_code = block_id_clean[:2]
    for bundle_key in (f"history_bundle/{st_code}.json", "history_bundle.json"):
        try:
            bundle = _read_api_json(bundle_key)
            if block_id_clean in bundle:
                return _json_response(200, bundle[block_id_clean])
        except ObjectNotFoundError:
            pass

    try:
        payload = _read_api_json(f"history/{block_id_clean}.json")
        return _json_response(200, payload)
    except ObjectNotFoundError:
        return _json_response(404, {"error": "Block not found", "block_id": block_id_clean})


def _handle_rankings(query: dict[str, str]) -> dict[str, Any]:
    scenario = query.get("scenario", "normal").strip().lower()
    if scenario not in ALLOWED_SCENARIOS:
        return _json_response(
            400,
            {"error": f"Invalid scenario '{scenario}'. Allowed values: {', '.join(ALLOWED_SCENARIOS)}"},
        )

    raw_limit = query.get("limit", "50").strip()
    try:
        limit = int(raw_limit)
    except ValueError:
        return _json_response(400, {"error": "Parameter 'limit' must be an integer between 1 and 1000."})
    if limit < 1 or limit > 1000:
        return _json_response(400, {"error": "Parameter 'limit' must be between 1 and 1000."})

    state_code = _normalize_state_code(query.get("state"), default="ALL")
    doc = None
    for cand in (f"rankings/{state_code}_{scenario}.json", f"rankings/{state_code}.json"):
        try:
            doc = _read_api_json(cand)
            break
        except ObjectNotFoundError:
            continue
    if doc is None:
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
            "state_code": state_code,
            "state": doc.get("state", "All India" if state_code == "ALL" else state_code),
            "scenario": scenario,
            "forecast_season": doc.get("forecast_season"),
            "summary": doc.get("summary", {}),
            "count": len(sliced),
            "rankings": sliced,
        },
    )


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    t0 = time.perf_counter()
    method, path, path_params, query = _extract_request(event)

    if method == "OPTIONS":
        return {"statusCode": 204, "headers": _cors_headers(), "body": ""}

    try:
        if method != "GET":
            resp = _json_response(405, {"error": f"Method {method} not allowed."})
        elif path == "/health":
            resp = _handle_health()
        elif path == "/states":
            resp = _handle_states(query)
        elif path == "/blocks":
            resp = _handle_blocks(query)
        elif path == "/blocks/nearest":
            resp = _handle_nearest(query)
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
        json.dumps({"method": method, "path": path, "status": resp["statusCode"], "latency_ms": latency_ms})
    )
    return resp
