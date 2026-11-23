# WellCast: AWS Infrastructure, IAM Security & Cost Guardrails Guide

This document provides the concrete AWS setup sequence, least-privilege IAM policy blueprints, Athena/Lambda/CloudWatch hardening configs, QuickSight verification rules, and cost-audit commands for deploying WellCast safely in **`ap-south-1` (Mumbai)**.

---

## 1. Day 1 AWS Account Hygiene (Tasks `T0.3`, `T0.4`)

Execute immediately upon creating the AWS account — **before creating any buckets or ML jobs**:

1. **Enable Root MFA:** Sign in as root -> IAM -> Security Credentials -> Assign authenticator app MFA -> sign out of root and **never use root for daily work**.
2. **Create Non-Root IAM User:** Create IAM user `wellcast-dev` (Console + Access Key for CLI only), attach scoped permissions (or temporary AdministratorAccess for hackathon setup while enforcing strict least-privilege roles for every AWS service runtime).
3. **Configure Local AWS CLI Profile (`ap-south-1`):**
   ```powershell
   aws configure --profile wellcast
   # Default region name: ap-south-1
   # Default output format: json
   aws sts get-caller-identity --profile wellcast
   ```
   Confirm the returned `Arn` is `arn:aws:iam::<ACCOUNT_ID>:user/wellcast-dev`, NOT `:root`.
4. **Create AWS Budgets Alert Immediately:**
   - AWS Billing & Cost Management -> Budgets -> Create Budget -> Cost budget (Monthly).
   - Set budget amount to **`$5.00 USD`** (or **`$1.00 USD`** Zero-Spend template if purely Free Tier) with email alerts at **50% Actual**, **80% Actual**, and **100% Forecasted**.
   - Also enable **Free Tier Usage Alerts** under Billing Preferences.

---

## 2. Least-Privilege IAM Roles & Policy Blueprints

Save these policies in `infra/iam-policies/` (replace `<DATA_BUCKET>`, `<WEB_BUCKET>`, `<ACCOUNT_ID>`, and `<DIST_ID>` before applying).

### 2.1 `infra/iam-policies/glue-crawler-policy.json` (`wellcast-glue-crawler-role`)
Attach AWS managed `AWSGlueServiceRole` + inline scoped S3 read policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadRawDataLakeOnly",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::<DATA_BUCKET>",
        "arn:aws:s3:::<DATA_BUCKET>/raw/*",
        "arn:aws:s3:::<DATA_BUCKET>/forecasts/*"
      ]
    }
  ]
}
```

### 2.2 `infra/iam-policies/sagemaker-training-policy.json` (`wellcast-sagemaker-training-role`)
Trust principal: `sagemaker.amazonaws.com`. Scoped solely to training inputs, model outputs, ECR pull for AWS XGBoost image, and CloudWatch training logs:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3TrainReadAndModelWrite",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::<DATA_BUCKET>",
        "arn:aws:s3:::<DATA_BUCKET>/curated/*",
        "arn:aws:s3:::<DATA_BUCKET>/models/*"
      ]
    },
    {
      "Sid": "CloudWatchTrainingLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams"
      ],
      "Resource": "arn:aws:logs:ap-south-1:<ACCOUNT_ID>:log-group:/aws/sagemaker/TrainingJobs:*"
    },
    {
      "Sid": "PullOfficialSageMakerECR",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage"
      ],
      "Resource": "*"
    }
  ]
}
```

### 2.3 `infra/iam-policies/lambda-api-policy.json` (`wellcast-lambda-api-role`)
Trust principal: `lambda.amazonaws.com`. **Strictly read-only on `api/*` prefix — no write access, no access to `raw/` or `models/`.**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadPrecomputedApiJsonOnly",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::<DATA_BUCKET>/api/*"
    },
    {
      "Sid": "LambdaCloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-south-1:<ACCOUNT_ID>:log-group:/aws/lambda/wellcast-api:*"
    }
  ]
}
```

### 2.4 `infra/iam-policies/cloudfront-oac-bucket-policy.json` (on `<WEB_BUCKET>`)
Keeps `<WEB_BUCKET>` 100% private (`Block Public Access = ON`) while allowing only your CloudFront distribution to fetch static files:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCloudFrontOACReadOnly",
      "Effect": "Allow",
      "Principal": { "Service": "cloudfront.amazonaws.com" },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::<WEB_BUCKET>/*",
      "Condition": {
        "StringEquals": {
          "AWS:SourceArn": "arn:aws:cloudfront::<ACCOUNT_ID>:distribution/<DIST_ID>"
        }
      }
    }
  ]
}
```

---

## 3. Athena Workgroup & S3 Lifecycle Guardrails

1. **Create Athena Workgroup `wellcast-wg`:**
   - Query result location: `s3://<DATA_BUCKET>/athena-results/`
   - **Per-query data usage control limit:** `100 MB` (prevents any accidental runaway full-bucket scan; our entire state Parquet dataset is < 20 MB!).
   - Enforce workgroup settings = `ON`.
2. **S3 Lifecycle Rule on `<DATA_BUCKET>`:**
   - Prefix: `athena-results/` -> Expire current objects after **7 days** (prevents stale CSV query result buildup).

---

## 4. Lambda, API Gateway & CloudWatch Configuration

| Component | Exact Recommended Setting | Why |
|---|---|---|
| **Lambda Runtime** | Python 3.12 (`arm64` Graviton2) | Faster cold starts, ~20% cheaper per ms |
| **Lambda Memory / Timeout** | `256 MB` RAM / `10 seconds` timeout | Fast JSON parsing; prevents runaway billing on stuck sockets |
| **Lambda Env Vars** | `FORECAST_BUCKET=<DATA_BUCKET>`, `ALLOWED_ORIGIN=https://<DIST_ID>.cloudfront.net`, `CACHE_TTL_SECONDS=300` | Zero hardcoded bucket names or domains |
| **API Gateway Type** | **HTTP API (v2)** | ~70% cheaper than REST API v1, native CORS & Lambda proxy |
| **API Gateway Throttling** | Burst `50` req, Rate `25` req/s | Protects against accidental traffic loops or bot hammering |
| **CloudWatch Log Retention** | `14 days` on `/aws/lambda/wellcast-api` | Prevents indefinite log storage cost |
| **CloudWatch Alarm** | Metric `Errors` on `wellcast-api` >= `5` over 5 minutes -> SNS email | Early warning if live Demo URL breaks during judging |

---

## 5. Amazon QuickSight Setup & Risk Check (Phase 7 — P2 Bonus)

QuickSight pricing/trials vary by AWS account and region. Follow this strict gate before enabling:

1. **Verify Terms First (`T7.1`):** Inspect the QuickSight sign-up screen in `ap-south-1`. Confirm whether a 30-day free trial covers through **17 Dec 2026** (Demo Day) with zero surprise charges on cancellation. If billing is unclear or immediate subscription cost applies, **skip Phase 7 cleanly** — the React Planner View already delivers ranked at-risk blocks!
2. **IAM Access Inside QuickSight:** Under QuickSight -> Manage QuickSight -> Security & Permissions -> Enable **Amazon Athena** and grant read-only S3 access ONLY to `<DATA_BUCKET>` (specifically `forecasts/`, `raw/block/`, and `athena-results/`).
3. **Immediate Backup Rule (`T7.3`):** Take high-res PNG screenshots + a 30-second MP4 walkthrough right after building the dashboard, then store in `Docs/assets/quicksight/`. Remember to note a calendar reminder before trial end if you don't plan to keep QuickSight after Demo Day.

---

## 6. Cost Guardrails & Zero-Idle Verification Script

Run this PowerShell audit script at the end of **Day 3 (after SageMaker)**, **Day 5 (after deploy)**, **Day 6 (before submit)**, and **weekly until 17 Dec**:

```powershell
# WellCast AWS Idle Resource & Cost Hygiene Audit (ap-south-1)
$PROFILE = "wellcast"
$REGION  = "ap-south-1"

Write-Host "1. Checking SageMaker Endpoints (must be empty)..." -ForegroundColor Cyan
aws sagemaker list-endpoints --region $REGION --profile $PROFILE

Write-Host "2. Checking SageMaker Notebook Instances (must be empty)..." -ForegroundColor Cyan
aws sagemaker list-notebook-instances --region $REGION --profile $PROFILE

Write-Host "3. Checking SageMaker Studio Apps (must be empty)..." -ForegroundColor Cyan
aws sagemaker list-apps --region $REGION --profile $PROFILE

Write-Host "4. Checking EC2 Running Instances (must be empty)..." -ForegroundColor Cyan
aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --query "Reservations[].Instances[].InstanceId" --region $REGION --profile $PROFILE

Write-Host "5. Checking RDS Instances (must be empty)..." -ForegroundColor Cyan
aws rds describe-db-instances --query "DBInstances[].DBInstanceIdentifier" --region $REGION --profile $PROFILE

Write-Host "6. Checking S3 Buckets Public Access Block..." -ForegroundColor Cyan
aws s3api get-public-access-block --bucket <DATA_BUCKET> --profile $PROFILE
aws s3api get-public-access-block --bucket <WEB_BUCKET> --profile $PROFILE
```

### Expected Cost Footprint (Hackathon Scale — Single State)
| Service | Expected Monthly Cost | Guardrail |
|---|---|---|
| S3 Storage (<100 MB total) | \$0.00 (Free Tier) | Lifecycle rule on `athena-results/` |
| Glue Crawler (2–3 manual runs) | < \$0.10 | Manual trigger only (no hourly schedule) |
| Athena (<500 MB scanned total) | < \$0.01 | `100 MB` per-query scan limit + Parquet |
| SageMaker Training Job (1–2 runs, 2 min on `ml.m5.large`) | < \$0.05 (or Free Tier/Credits) | Short-lived training job + `max_run=600` + teardown audit |
| Lambda + API Gateway HTTP API (<50k requests) | \$0.00 (Free Tier) | Precomputed JSON + 5m cache + throttling |
| CloudFront (<5 GB transfer) | \$0.00 (Free Tier: 1 TB/mo) | Static compressed bundle + GeoJSON <1.5 MB |
| **Total Estimated Build + Judging + Demo Day Spend** | **< \$1.00 USD** | Protected by \$5 AWS Budgets alert |

---

## 7. Repository Security & `.gitignore` Standard

Include all of the following patterns in `.gitignore` on Day 1 (`T0.5`):
```gitignore
# Secrets & Environment
.env
.env.*
!.env.example
*.pem
*.key
*.p12
credentials.csv
aws_credentials*

# Local Large Raw Data & Model Artifacts
data/raw_local/
data/processed_local/
ml/artifacts_local/
*.parquet
!data/sample/*.parquet

# Python & Notebooks
__pycache__/
*.py[cod]
.venv/
venv/
.ipynb_checkpoints/

# Frontend Build & Dependencies
frontend/node_modules/
frontend/dist/
frontend/.env.local

# OS / Editor
.DS_Store
Thumbs.db
```
