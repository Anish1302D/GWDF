"""Amazon Athena query helper for WellCast verification & fallback ad-hoc queries."""

from __future__ import annotations

import os
import time
from typing import Any


def run_athena_query(
    sql: str,
    database: str | None = None,
    workgroup: str | None = None,
    region: str | None = None,
    timeout_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    """Execute a SQL statement in Amazon Athena and return rows as list of dicts."""
    import boto3

    db = database or os.environ.get("GLUE_DATABASE", "wellcast")
    wg = workgroup or os.environ.get("ATHENA_WORKGROUP", "wellcast-wg")
    reg = region or os.environ.get("AWS_REGION", "ap-south-1")

    athena = boto3.client("athena", region_name=reg)
    start_resp = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": db},
        WorkGroup=wg,
    )
    qid = start_resp["QueryExecutionId"]

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status_resp = athena.get_query_execution(QueryExecutionId=qid)
        state = status_resp["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            reason = status_resp["QueryExecution"]["Status"].get("StateChangeReason", "Unknown")
            raise RuntimeError(f"Athena query {qid} {state}: {reason}")
        time.sleep(0.5)
    else:
        athena.stop_query_execution(QueryExecutionId=qid)
        raise TimeoutError(f"Athena query {qid} exceeded {timeout_seconds}s timeout")

    paginator = athena.get_paginator("get_query_results")
    rows_out: list[dict[str, Any]] = []
    headers: list[str] | None = None

    for page in paginator.paginate(QueryExecutionId=qid):
        result_rows = page["ResultSet"]["Rows"]
        for row in result_rows:
            values = [col.get("VarCharValue") for col in row.get("Data", [])]
            if headers is None:
                headers = [h or f"col_{i}" for i, h in enumerate(values)]
            else:
                rows_out.append(dict(zip(headers, values)))

    return rows_out
