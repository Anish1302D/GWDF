#!/usr/bin/env bash
# End-to-end WellCast AWS Deployment Script (Lambda API + S3 Data Lake + Private Web S3 + CloudFront Invalidation)
set -euo pipefail

BUCKET="${FORECAST_BUCKET:?Set FORECAST_BUCKET}"
WEB_BUCKET="${WEB_BUCKET:?Set WEB_BUCKET}"
DIST_ID="${CLOUDFRONT_DIST_ID:-}"
LAMBDA_NAME="${LAMBDA_FUNCTION_NAME:-wellcast-api}"
PROFILE="${AWS_PROFILE:-wellcast}"
REGION="${AWS_REGION:-ap-south-1}"

echo "=== 1. Syncing Data Lake & Precomputed API JSONs to s3://${BUCKET}/ ==="
bash data/scripts/upload_to_s3.sh

echo "=== 2. Packaging & Updating AWS Lambda (${LAMBDA_NAME}) ==="
mkdir -p infra/build/lambda_pkg
cp backend/lambda_handler.py backend/athena_client.py infra/build/lambda_pkg/
(cd infra/build/lambda_pkg && zip -qr ../lambda_api.zip .)
aws lambda update-function-code \
  --function-name "${LAMBDA_NAME}" \
  --zip-file fileb://infra/build/lambda_api.zip \
  --region "${REGION}" \
  --profile "${PROFILE}" >/dev/null

echo "=== 3. Building React Production Bundle ==="
(cd frontend && npm run build)

echo "=== 4. Syncing Frontend Assets to Private S3 (s3://${WEB_BUCKET}/) ==="
aws s3 sync frontend/dist/ "s3://${WEB_BUCKET}/" \
  --exclude "index.html" \
  --cache-control "public, max-age=31536000, immutable" \
  --delete \
  --region "${REGION}" \
  --profile "${PROFILE}"

aws s3 cp frontend/dist/index.html "s3://${WEB_BUCKET}/index.html" \
  --cache-control "no-cache, no-store, must-revalidate" \
  --content-type "text/html; charset=utf-8" \
  --region "${REGION}" \
  --profile "${PROFILE}"

if [ -n "${DIST_ID}" ]; then
  echo "=== 5. Creating CloudFront Cache Invalidation (${DIST_ID}) ==="
  aws cloudfront create-invalidation \
    --distribution-id "${DIST_ID}" \
    --paths "/*" \
    --profile "${PROFILE}" >/dev/null
fi

echo "=== WellCast Deployment Complete ==="
