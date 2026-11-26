# Upload cleaned WellCast raw Parquet, forecast Parquet, and static API JSONs to Amazon S3 (PowerShell)
param(
    [Parameter(Mandatory = $false)]
    [string]$Bucket = $env:FORECAST_BUCKET,
    [string]$Profile = $(if ($env:AWS_PROFILE) { $env:AWS_PROFILE } else { "wellcast" }),
    [string]$Region = $(if ($env:AWS_REGION) { $env:AWS_REGION } else { "ap-south-1" }),
    [string]$LocalBase = "data/processed_local"
)

$ErrorActionPreference = "Stop"
if (-not $Bucket) {
    throw "FORECAST_BUCKET is required. Pass -Bucket <name> or set `$env:FORECAST_BUCKET."
}

Write-Host "Syncing raw/ Parquet tables to s3://$Bucket/raw/ ..." -ForegroundColor Cyan
aws s3 sync "$LocalBase/raw/" "s3://$Bucket/raw/" --delete --region $Region --profile $Profile

if (Test-Path "$LocalBase/curated") {
    Write-Host "Syncing curated/ Parquet tables to s3://$Bucket/curated/ ..." -ForegroundColor Cyan
    aws s3 sync "$LocalBase/curated/" "s3://$Bucket/curated/" --delete --region $Region --profile $Profile
}

if (Test-Path "$LocalBase/forecasts") {
    Write-Host "Syncing forecasts/ Parquet tables to s3://$Bucket/forecasts/ ..." -ForegroundColor Cyan
    aws s3 sync "$LocalBase/forecasts/" "s3://$Bucket/forecasts/" --delete --region $Region --profile $Profile
}

if (Test-Path "$LocalBase/api") {
    Write-Host "Syncing api/ static JSON files to s3://$Bucket/api/ ..." -ForegroundColor Cyan
    aws s3 sync "$LocalBase/api/" "s3://$Bucket/api/" --delete --region $Region --profile $Profile
}

Write-Host "Upload to s3://$Bucket/ completed." -ForegroundColor Green
