# WellCast: Zero-CLI AWS Browser Console Deployment Guide

Deploy the entire WellCast architecture in **`ap-south-1` (Mumbai)** using **only your web browser** (AWS Management Console + browser-based AWS CloudShell).
- **Zero AWS CLI installation** on your Windows machine.
- **Zero permanent AWS Access Keys (`AKIA...`)** stored on your laptop.

---

## Pre-Built Upload Bundles on Your Machine

Run this local Python command once (uses standard library only) whenever you want to refresh the upload archives:

```powershell
.\.venv\Scripts\python.exe infra/package_for_console_upload.py
```

This creates 4 ready-to-upload files in `d:\Projects\GWDF\infra\build\`:
1. `lambda_api.zip` (~5 KB) — uploaded directly in the AWS Lambda Console
2. `data_lake_bundle.zip` (~2–3 MB) — contains `raw/`, `curated/`, `forecasts/`, `api/` JSONs, and `models/code/sourcedir.tar.gz`
3. `sagemaker_sourcedir.tar.gz` (~6 KB) — SageMaker training code archive
4. `frontend_dist.zip` (~300–650 KB) — production React + Leaflet web app bundle

---

## Step 1: Account Security & \$5 Budget Alert (5 min)

1. Sign in to the **AWS Management Console** and switch the top-right region selector to **Asia Pacific (Mumbai) `ap-south-1`**. Note your **12-digit Account ID** (top-right menu -> copy Account ID).
2. **Root MFA + IAM User:**
   - Open **IAM -> Security credentials** -> enable **MFA** on Root.
   - Open **IAM -> Users -> Create user** -> name `wellcast-admin`, check *Provide user access to the AWS Management Console*, attach `AdministratorAccess` for console setup, sign out of root, and sign back in as `wellcast-admin`.
3. **Create AWS Budget Alert:**
   - Search **Budgets** -> **Create budget** -> **Customize (advanced) -> Cost budget**.
   - Budget name: `wellcast-monthly-guardrail` · Period: `Monthly` · Budgeted amount: **`$5.00`**.
   - Add alert thresholds at **50% Actual**, **80% Actual**, and **100% Forecasted** -> enter your email -> **Create budget**.

---

## Step 2: Create the 2 Private S3 Buckets & Upload Data Lake via Browser CloudShell (5 min)

1. Open **Amazon S3 -> Create bucket** (ensure region is `ap-south-1`):
   - **Bucket 1 (Data Lake):** `wellcast-data-<YOUR_12_DIGIT_ACCOUNT_ID>-ap-south-1`
     - Keep **Block all public access = ON** -> **Create bucket**.
   - **Bucket 2 (Frontend Web):** `wellcast-web-<YOUR_12_DIGIT_ACCOUNT_ID>-ap-south-1`
     - Keep **Block all public access = ON** -> **Create bucket**.
2. **Add 7-Day Cleanup Rule on Athena Scratch Folder:**
   - Open `wellcast-data-...` -> **Management** tab -> **Create lifecycle rule**:
     - Name: `cleanup-athena-results` -> Prefix: `athena-results/` -> Check *Permanently delete / Expire current versions of objects* -> Days after creation: `7` -> **Create rule**.
3. **Upload All Parquet Tables & 1,800+ API JSONs in One Shot Using Browser CloudShell:**
   - Click the **CloudShell icon (`[>_]`)** in the top navigation bar of the AWS Console (next to the search bar / bell icon). Wait ~15 seconds for the browser terminal to open in `ap-south-1`.
   - Click **Actions (top-right of CloudShell) -> Upload file** -> select `d:\Projects\GWDF\infra\build\data_lake_bundle.zip`.
   - Run these 4 commands inside the **browser CloudShell**:
     ```bash
     export DATA_BUCKET="wellcast-data-$(aws sts get-caller-identity --query Account --output text)-ap-south-1"
     mkdir -p ~/lake && unzip -q ~/data_lake_bundle.zip -d ~/lake
     aws s3 sync ~/lake/ "s3://${DATA_BUCKET}/"
     rm -rf ~/lake ~/data_lake_bundle.zip
     ```
   - Verify in the S3 Console that `wellcast-data-...` now contains folders: `raw/`, `curated/`, `forecasts/`, `api/`, and `models/`.

---

## Step 3: AWS Glue Crawler & Amazon Athena Verification (5 min)

1. **Configure Athena Workgroup (`100 MB` Scan Guardrail):**
   - Open **Amazon Athena -> Workgroups -> Create workgroup**:
     - Name: `wellcast-wg`
     - Query result location: `s3://wellcast-data-<ACCOUNT_ID>-ap-south-1/athena-results/`
     - Expand **Data usage controls -> Per-query data usage control** -> set **`100` MB** -> **Create workgroup**.
   - Switch to workgroup `wellcast-wg` in the Athena Query Editor.
2. **Register Tables (Choose Option A: Glue Crawler OR Option B: Direct SQL DDL):**
   - **Option A (Glue Crawler):**
     - Open **AWS Glue -> Databases -> Add database** -> Name: `wellcast`.
     - Go to **Crawlers -> Create crawler** -> Name: `wellcast-raw-crawler` -> Data source: `s3://wellcast-data-<ACCOUNT_ID>-ap-south-1/raw/` -> Create new IAM role `wellcast-glue-crawler-role` -> Target database: `wellcast` -> Schedule: *On demand* -> **Create & Run crawler**.
   - **Option B (Instant SQL in Athena Query Editor):**
     - Paste the contents of [`sql/01_create_tables.sql`](../sql/01_create_tables.sql) and [`sql/03_serving_views.sql`](../sql/03_serving_views.sql) (replacing `${DATA_BUCKET}` with `wellcast-data-<ACCOUNT_ID>-ap-south-1`) and click **Run**.
3. **Verify Athena Exit Check:**
   ```sql
   SELECT * FROM wellcast.v_top_at_risk_normal LIMIT 10;
   ```
   Confirm the top 10 Maharashtra blocks return immediately (take a screenshot for your Build Summary!).

---

## Step 4: Run One Short-Lived Amazon SageMaker Training Job (5 min)

1. **Create Scoped SageMaker IAM Role:**
   - Open **IAM -> Roles -> Create role** -> AWS Service -> Use case: **SageMaker** (`SageMaker - Execution`) -> Name: `wellcast-sagemaker-training-role`.
   - Open the newly created role -> **Add permissions -> Create inline policy -> JSON** -> paste [`infra/iam-policies/sagemaker-training-policy.json`](../infra/iam-policies/sagemaker-training-policy.json) (replace `${DATA_BUCKET}` and `${ACCOUNT_ID}`) -> Save as `WellCastSageMakerS3Scoped`.
2. **Launch Ephemeral Training Job in Console:**
   - Open **Amazon SageMaker AI -> Training -> Training jobs -> Create training job**:
     - **Job name:** `wellcast-xgb-mh-prod`
     - **IAM role:** `wellcast-sagemaker-training-role`
     - **Algorithm source:** *Your own algorithm container in ECR* (or *Amazon SageMaker built-in -> XGBoost* in Script Mode):
       - Container image URI (`ap-south-1` official XGBoost 1.7-1): `720646828776.dkr.ecr.ap-south-1.amazonaws.com/sagemaker-xgboost:1.7-1`
       - Training input mode: `File`
     - **Resource configuration:** Instance type `ml.m5.large` · Instance count `1` · Additional volume `10 GB`.
     - **Stopping condition:** Maximum runtime **`10` minutes (`600` seconds)**.
     - **Hyperparameters:**
       - `sagemaker_program` = `train.py`
       - `sagemaker_submit_directory` = `s3://wellcast-data-<ACCOUNT_ID>-ap-south-1/models/code/sourcedir.tar.gz`
     - **Input data configuration:** Channel name `train` · S3 location `s3://wellcast-data-<ACCOUNT_ID>-ap-south-1/curated/ml_train/`.
     - **Output data configuration:** `s3://wellcast-data-<ACCOUNT_ID>-ap-south-1/models/`.
   - Click **Create training job**. Wait ~2 minutes until Status turns **`Completed`** (take a screenshot!). Because this is a Training Job (not a Notebook or Endpoint), compute automatically shuts down to **\$0/hr** the moment it finishes.

---

## Step 5: Deploy Backend API (AWS Lambda + API Gateway HTTP API) (6 min)

1. **Create Least-Privilege Lambda IAM Role:**
   - Open **IAM -> Roles -> Create role** -> AWS Service -> **Lambda** -> click Next (skip managed policies) -> Name: `wellcast-lambda-api-role` -> Create role.
   - Open `wellcast-lambda-api-role` -> **Add permissions -> Create inline policy -> JSON** -> paste [`infra/iam-policies/lambda-api-policy.json`](../infra/iam-policies/lambda-api-policy.json) (replacing `${DATA_BUCKET}` and `${ACCOUNT_ID}`) -> Save as `WellCastLambdaReadApiOnly`.
2. **Create Lambda Function:**
   - Open **AWS Lambda -> Create function -> Author from scratch**:
     - Function name: `wellcast-api`
     - Runtime: **Python 3.12** · Architecture: **`arm64`**
     - Execution role: *Use an existing role* -> `wellcast-lambda-api-role` -> **Create function**.
   - Under **Code** tab -> **Upload from -> .zip file** -> upload `d:\Projects\GWDF\infra\build\lambda_api.zip` -> **Save**.
   - Scroll to **Runtime settings -> Edit** -> change **Handler** from `lambda_function.lambda_handler` to:
     ```text
     lambda_handler.handler
     ```
     Click **Save**.
   - Under **Configuration -> General configuration -> Edit**: Memory `256 MB`, Timeout `10 sec` -> **Save**.
   - Under **Configuration -> Environment variables -> Edit**, add:
     - `FORECAST_BUCKET` = `wellcast-data-<ACCOUNT_ID>-ap-south-1`
     - `ALLOWED_ORIGIN` = `*` *(you will lock this to your CloudFront URL in Step 6)*
     - `CACHE_TTL_SECONDS` = `300`
3. **Create CloudWatch Log Retention & Error Alarm:**
   - Open **CloudWatch -> Log groups** -> find `/aws/lambda/wellcast-api` (after 1 test invoke) -> **Actions -> Edit retention setting -> 2 weeks (14 days)**.
4. **Create API Gateway HTTP API:**
   - Open **Amazon API Gateway -> Create API -> HTTP API -> Build**:
     - Integrations: **Add integration -> Lambda** -> select `wellcast-api` · API name: `wellcast-http-api` -> **Next**.
     - **Configure routes** (all pointing to `wellcast-api`):
       - `GET` `/health`
       - `GET` `/blocks`
       - `GET` `/blocks/{block_id}/forecast`
       - `GET` `/blocks/{block_id}/history`
       - `GET` `/rankings`
     - **Define stages:** Stage name `prod` (Auto-deploy ON) -> **Create**.
   - In the left sidebar of `wellcast-http-api`, click **CORS -> Configure**:
     - `Access-Control-Allow-Origin`: `*` *(update to `https://<dist>.cloudfront.net` after Step 6)*
     - `Access-Control-Allow-Methods`: `GET`, `OPTIONS`
     - `Access-Control-Allow-Headers`: `content-type` -> **Save**.
   - Copy your **Invoke URL**: `https://<API_ID>.execute-api.ap-south-1.amazonaws.com/prod` and open `.../prod/health` in a browser tab — confirm `"status": "ok"` and `"blocks_indexed": 356`!

---

## Step 6: Build Frontend with Live API URL & Deploy via Private S3 + CloudFront OAC (8 min)

1. **Rebuild Frontend Locally Pointing to Your Live API Gateway URL:**
   On your Windows PC in PowerShell (still zero AWS CLI needed!):
   ```powershell
   Set-Content -Path "d:\Projects\GWDF\frontend\.env.production" -Value "VITE_API_BASE_URL=https://<YOUR_API_ID>.execute-api.ap-south-1.amazonaws.com/prod"
   Push-Location d:\Projects\GWDF\frontend
   npm run build
   Pop-Location
   ```
2. **Upload `frontend/dist/` Directly in the S3 Web Console:**
   - Open **Amazon S3** -> click `wellcast-web-<ACCOUNT_ID>-ap-south-1` -> click **Upload**.
   - Drag and drop **all contents inside** `d:\Projects\GWDF\frontend\dist\` (`index.html`, the `assets` folder, and the `geo` folder — only 7 files total!) -> click **Upload**.
3. **Create CloudFront Distribution with Origin Access Control (OAC):**
   - Open **Amazon CloudFront -> Create distribution**:
     - **Origin domain:** select `wellcast-web-<ACCOUNT_ID>-ap-south-1.s3.ap-south-1.amazonaws.com`
     - **Origin access:** select **Origin access control settings (recommended)** -> click **Create new OAC** -> Create.
     - **Viewer protocol policy:** **Redirect HTTP to HTTPS**.
     - **Web Application Firewall (WAF):** **Do not enable security protections** *(WAF has a fixed monthly base fee — keep it OFF to stay Free Tier!)*.
     - **Default root object:** `index.html` *(type `index.html` without a leading slash)*.
     - Click **Create distribution**.
   - **Copy S3 Bucket Policy:** A yellow banner appears at the top saying *"The S3 bucket policy needs to be updated"* -> click **Copy policy**, open `wellcast-web-...` in S3 -> **Permissions -> Bucket policy -> Edit** -> paste & **Save changes**.
   - **Add SPA Error Routing:** Inside your CloudFront distribution -> **Error pages** tab -> **Create custom error response** (do this for both `403` and `404`):
     - HTTP error code: `403` (and repeat for `404`) -> Customize error response: `Yes` -> Response page path: `/index.html` -> HTTP response code: `200` -> Create.
4. **Lock CORS to Your CloudFront Domain:**
   - Once CloudFront status changes from *Deploying* to *Enabled* (~5 minutes), copy `https://<DIST_ID>.cloudfront.net`.
   - Update Lambda `wellcast-api` environment variable `ALLOWED_ORIGIN` = `https://<DIST_ID>.cloudfront.net`.
   - Update API Gateway `wellcast-http-api` -> **CORS** -> replace `*` with `https://<DIST_ID>.cloudfront.net`.
5. **Phone Verification:** Open `https://<DIST_ID>.cloudfront.net` on your smartphone over mobile data in an Incognito tab!

---

## Step 7: Console Zero-Idle Cost Check (1 min)

Before logging out of the AWS Console:
- **SageMaker -> Endpoints:** Confirm `0` endpoints.
- **SageMaker -> Notebook instances / Studio:** Confirm `0` running instances/apps.
- **EC2 -> Instances (running):** Confirm `0`.
- **CloudFront -> WAF:** Confirm no Web ACL attached.
