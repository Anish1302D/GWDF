#!/usr/bin/env bash
# Upload cleaned WellCast raw Parquet, forecast Parquet, and static API JSONs to Amazon S3
set -euo pipefail

BUCKET="${FORECAST_BUCKET:?Set FORECAST_BUCKET environment variable first}"
PROFILE="${AWS_PROFILE:-wellcast}"
REGION="${AWS_REGION:-ap-south-1}"
LOCAL_BASE="data/processed_local"

echo "Uploading raw Parquet tables to s3://${BUCKET}/raw/ ..."
aws s3 sync "${LOCAL_BASE}/raw/" "s3://${BUCKET}/raw/" --delete --region "${REGION}" --profile "${PROFILE}"

if [ -d "${LOCAL_BASE}/curated" ]; then
  echo "Uploading curated ML feature tables to s3://${BUCKET}/curated/ ..."
  aws s3 sync "${LOCAL_BASE}/curated/" "s3://${BUCKET}/curated/" --delete --region "${REGION}" --profile "${PROFILE}"
fi

if [ -d "${LOCAL_BASE}/forecasts" ]; then
  echo "Uploading forecast Parquet tables to s3://${BUCKET}/forecasts/ ..."
  aws s3 sync "${LOCAL_BASE}/forecasts/" "s3://${BUCKET}/forecasts/" --delete --region "${REGION}" --profile "${PROFILE}"
fi

if [ -d "${LOCAL_BASE}/api" ]; then
  echo "Uploading precomputed static API JSON payloads to s3://${BUCKET}/api/ ..."
  aws s3 sync "${LOCAL_BASE}/api/" "s3://${BUCKET}/api/" --delete --region "${REGION}" --profile "${PROFILE}"
fi

echo "Done syncing data lake to s3://${BUCKET}/."
