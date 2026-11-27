# WellCast: Pure Browser GUI Deployment Guide (No AWS CLI, No CloudShell)

Deploy the entire WellCast architecture in your project's assigned AWS region (**`ap-southeast-2`**, Account ID **`621503941447`**) using **only standard AWS Web Console screens** — no AWS CLI and no CloudShell needed!

---

## Ready-to-Upload Folders on Your PC

Already built for you on disk:
1. **`d:\Projects\GWDF\infra\s3_data_bucket_upload\`** (**only 23 compact files total!**) — contains `raw/`, `curated/`, `forecasts/`, `models/`, and consolidated `api/` JSON bundles. Drag-and-drop straight into S3 in 5 seconds!
2. **`d:\Projects\GWDF\infra\build\lambda_api.zip`** (`4.7 KB`) — upload directly in AWS Lambda Console.
3. **`d:\Projects\GWDF\frontend\dist\`** (`7 files`) — drag-and-drop straight into your S3 Web bucket.

*(To regenerate at any time: `.\.venv\Scripts\python.exe infra/package_for_console_upload.py`)*

---

## Step 1: Budget / Spend Guardrail (Already Done!)

- Project `WellCast` (`621503941447`, `ap-southeast-2`) created with **\$20.00 spend limit** active.

---

## Step 2: Create the 2 Private S3 Buckets & Drag-and-Drop the Data Lake (3 min)

1. Close the CloudShell panel at the bottom (`X`), type **`S3`** in the top AWS Console `Search` bar, and open **S3**.
2. Click **`Create bucket`**:
   - **Bucket name:** `wellcast-data-621503941447-ap-southeast-2`
   - Leave **Block all public access = ON** (checked) -> scroll down and click **`Create bucket`**.
3. Click **`Create bucket`** a second time:
   - **Bucket name:** `wellcast-web-621503941447-ap-southeast-2`
   - Leave **Block all public access = ON** (checked) -> click **`Create bucket`**.
4. **Upload the Data Lake via Drag-and-Drop (Zero CloudShell!):**
   - Click into **`wellcast-data-621503941447-ap-southeast-2`** -> click **`Upload`**.
   - Open Windows File Explorer to:
     ```text
     d:\Projects\GWDF\infra\s3_data_bucket_upload
     ```
   - Select **all 5 folders inside it** (`api`, `curated`, `forecasts`, `models`, `raw`) and **drag them into the S3 Upload page** in Firefox -> scroll down and click **`Upload`**.
   - Wait ~10 seconds until all **23 files** show **Succeeded**, then click **Close**.
5. *(Optional 30s hygiene)* Inside `wellcast-data-621503941447-ap-southeast-2` -> **Management** tab -> **Create lifecycle rule**: Name `cleanup-athena`, Prefix `athena-results/`, check *Expire current versions of objects* after `7` days -> **Create rule**.

---

## Step 3: Amazon Athena Setup & Top-10 Verification (3 min)

1. Type **`Athena`** in the top Search bar -> open **Amazon Athena** -> launch **Query editor**.
2. Create the `100 MB`-capped workgroup:
   - Left menu -> **Workgroups -> Create workgroup**:
     - Workgroup name: `wellcast-wg`
     - Query result location: `s3://wellcast-data-621503941447-ap-southeast-2/athena-results/`
     - Expand **Data usage controls -> Per-query data usage control** -> set **`100` MB** -> **Create workgroup**.
   - Switch to **`wellcast-wg`** in the top-right Workgroup dropdown of the Query editor.
3. Run these statements one by one in the Athena Query Editor:

```sql
CREATE DATABASE IF NOT EXISTS wellcast;
```

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS wellcast.block (
  block_id STRING, state_code STRING, state STRING, district STRING, block_name STRING,
  extraction_stage STRING, extraction_stage_code INT, lat DOUBLE, lon DOUBLE, granularity STRING
)
STORED AS PARQUET
LOCATION 's3://wellcast-data-621503941447-ap-southeast-2/raw/block/';
```

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS wellcast.rainfall_monthly (
  block_id STRING, month DATE, rainfall_mm DOUBLE, normal_rainfall_mm DOUBLE,
  departure_from_normal_pct DOUBLE, rainfall_source_level STRING, is_imputed BOOLEAN
)
STORED AS PARQUET
LOCATION 's3://wellcast-data-621503941447-ap-southeast-2/raw/rainfall_monthly/';
```

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS wellcast.water_level (
  block_id STRING, obs_date DATE, year INT, season STRING, season_code INT,
  depth_mbgl DOUBLE, well_count INT, is_imputed BOOLEAN
)
STORED AS PARQUET
LOCATION 's3://wellcast-data-621503941447-ap-southeast-2/raw/water_level/';
```

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS wellcast.forecasts (
  block_id STRING, state STRING, district STRING, block_name STRING, scenario STRING,
  rainfall_pct_of_normal INT, forecast_season STRING, current_depth_mbgl DOUBLE,
  predicted_depth_mbgl DOUBLE, lower_bound DOUBLE, upper_bound DOUBLE,
  predicted_yoy_change_mbgl DOUBLE, risk_class STRING, risk_score DOUBLE,
  model_version STRING, generated_at TIMESTAMP
)
STORED AS PARQUET
LOCATION 's3://wellcast-data-621503941447-ap-southeast-2/forecasts/';
```

```sql
SELECT block_id, district, block_name, current_depth_mbgl, predicted_depth_mbgl, risk_class, risk_score
FROM wellcast.forecasts
WHERE scenario = 'normal' AND risk_class <> 'Insufficient Data'
ORDER BY risk_score DESC
LIMIT 10;
```
*(Take a screenshot of that Top-10 Athena query result!)*

---

## Step 4: Run One Short-Lived Amazon SageMaker Training Job (5 min)

1. Open **IAM -> Roles -> Create role**:
   - Trusted entity: **AWS service** -> Use case: **SageMaker** (`SageMaker - Execution`) -> Next -> Name: `wellcast-sagemaker-training-role` -> **Create role**.
   - Open `wellcast-sagemaker-training-role` -> **Add permissions -> Create inline policy -> JSON** -> paste:
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [
         {
           "Effect": "Allow",
           "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
           "Resource": [
             "arn:aws:s3:::wellcast-data-621503941447-ap-southeast-2",
             "arn:aws:s3:::wellcast-data-621503941447-ap-southeast-2/curated/*",
             "arn:aws:s3:::wellcast-data-621503941447-ap-southeast-2/models/*"
           ]
         }
       ]
     }
     ```
     Name it `WellCastSageMakerS3` -> **Create policy**.
2. Open **Amazon SageMaker AI -> Training -> Training jobs -> Create training job**:
   - **Job name:** `wellcast-xgb-mh-prod`
   - **IAM role:** `wellcast-sagemaker-training-role`
   - **Algorithm options:** Choose *Your own algorithm container in ECR*:
     - **Container:** `783357654285.dkr.ecr.ap-southeast-2.amazonaws.com/sagemaker-xgboost:1.7-1` *(official `ap-southeast-2` SageMaker XGBoost image)*
     - **Training input mode:** `File`
   - **Resource configuration:** Instance type `ml.m5.large` · Instance count `1` · Additional volume `10 GB`
   - **Stopping condition:** Maximum runtime **`10` minutes (`600` seconds)**
   - **Hyperparameters** (click *Add hyperparameter* twice):
     - Key `sagemaker_program` -> Value `train.py`
     - Key `sagemaker_submit_directory` -> Value `s3://wellcast-data-621503941447-ap-southeast-2/models/code/sourcedir.tar.gz`
   - **Input data configuration:** Channel name `train` · S3 location `s3://wellcast-data-621503941447-ap-southeast-2/curated/ml_train/`
   - **Output data configuration:** S3 output path `s3://wellcast-data-621503941447-ap-southeast-2/models/`
   - Click **`Create training job`**. Wait ~2 minutes until status is **`Completed`** (auto-terminates to \$0/hr immediately!).

---

## Step 5: Deploy Backend API (AWS Lambda + API Gateway HTTP API) (5 min)

1. **Create Least-Privilege Lambda IAM Role:**
   - Open **IAM -> Roles -> Create role** -> AWS service -> **Lambda** -> Next (don't check any managed policies) -> Name: `wellcast-lambda-api-role` -> **Create role**.
   - Open `wellcast-lambda-api-role` -> **Add permissions -> Create inline policy -> JSON** -> paste:
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [
         {
           "Sid": "ReadPrecomputedApiJsonOnly",
           "Effect": "Allow",
           "Action": ["s3:GetObject"],
           "Resource": "arn:aws:s3:::wellcast-data-621503941447-ap-southeast-2/api/*"
         },
         {
           "Sid": "LambdaCloudWatchLogs",
           "Effect": "Allow",
           "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
           "Resource": "arn:aws:logs:ap-southeast-2:621503941447:log-group:/aws/lambda/wellcast-api:*"
         }
       ]
     }
     ```
     Name it `WellCastLambdaReadOnly` -> **Create policy**.
2. **Create Lambda Function:**
   - Open **AWS Lambda -> Create function -> Author from scratch**:
     - Name: `wellcast-api` · Runtime: **Python 3.12** · Architecture: **`arm64`**
     - Change default execution role -> **Use an existing role** -> `wellcast-lambda-api-role` -> **Create function**.
   - **Code tab -> Upload from -> .zip file** -> select `d:\Projects\GWDF\infra\build\lambda_api.zip` -> **Save**.
   - Scroll down to **Runtime settings -> Edit** -> set **Handler** to `lambda_handler.handler` -> **Save**.
   - **Configuration -> General configuration -> Edit:** Memory `256 MB`, Timeout `10 sec` -> **Save**.
   - **Configuration -> Environment variables -> Edit**, add:
     - `FORECAST_BUCKET` = `wellcast-data-621503941447-ap-southeast-2`
     - `AWS_REGION_OVERRIDE` *(not needed; Lambda auto-sets `AWS_REGION`)*
     - `ALLOWED_ORIGIN` = `*` *(lock to CloudFront URL in Step 6)*
     - `CACHE_TTL_SECONDS` = `300`
3. **Create API Gateway HTTP API:**
   - Open **Amazon API Gateway -> Create API -> HTTP API -> Build**:
     - Add integration: **Lambda** -> select `wellcast-api` · API name: `wellcast-http-api` -> **Next**.
     - Add 5 routes (all pointing to `wellcast-api`):
       - `GET` `/health`
       - `GET` `/blocks`
       - `GET` `/blocks/{block_id}/forecast`
       - `GET` `/blocks/{block_id}/history`
       - `GET` `/rankings`
     - Stage name: `prod` (Auto-deploy ON) -> **Create**.
   - Left sidebar -> **CORS -> Configure**:
     - `Access-Control-Allow-Origin`: `*`
     - `Access-Control-Allow-Methods`: `GET`, `OPTIONS`
     - `Access-Control-Allow-Headers`: `content-type` -> **Save**.
   - Open `https://<API_ID>.execute-api.ap-southeast-2.amazonaws.com/prod/health` in Firefox — confirm `"status": "ok"` and `"blocks_indexed": 356`!

---

## Step 6: Build React App & Deploy via Private S3 + CloudFront OAC (6 min)

1. Tell me your `<API_ID>` invoke URL (or run locally in PowerShell):
   ```powershell
   Set-Content -Path "d:\Projects\GWDF\frontend\.env.production" -Value "VITE_API_BASE_URL=https://<API_ID>.execute-api.ap-southeast-2.amazonaws.com/prod"
   Push-Location d:\Projects\GWDF\frontend
   npm run build
   Pop-Location
   ```
2. Open **S3 -> `wellcast-web-621503941447-ap-southeast-2` -> Upload** -> drag everything inside `d:\Projects\GWDF\frontend\dist\` (`index.html`, `assets`, `geo`) -> **Upload**.
3. Open **CloudFront -> Create distribution**:
   - Origin domain: `wellcast-web-621503941447-ap-southeast-2.s3.ap-southeast-2.amazonaws.com`
   - Origin access: **Origin access control settings (recommended)** -> **Create new OAC** -> Create.
   - Viewer protocol policy: **Redirect HTTP to HTTPS**.
   - Web Application Firewall (WAF): **Do not enable security protections**.
   - Default root object: `index.html` -> **Create distribution**.
   - Click **Copy policy** banner -> paste into `wellcast-web-...` -> **Permissions -> Bucket policy**.
   - Under CloudFront **Error pages**, map `403` and `404` -> `/index.html` with HTTP `200`.
4. Lock `ALLOWED_ORIGIN` in Lambda and API Gateway CORS to `https://<DIST_ID>.cloudfront.net`.
