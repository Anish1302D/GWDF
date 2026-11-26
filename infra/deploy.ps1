# End-to-End WellCast AWS Deployment Script for Windows PowerShell
param(
    [string]$ForecastBucket = $env:FORECAST_BUCKET,
    [string]$WebBucket = $env:WEB_BUCKET,
    [string]$CloudFrontDistId = $env:CLOUDFRONT_DIST_ID,
    [string]$LambdaName = $(if ($env:LAMBDA_FUNCTION_NAME) { $env:LAMBDA_FUNCTION_NAME } else { "wellcast-api" }),
    [string]$Profile = $(if ($env:AWS_PROFILE) { $env:AWS_PROFILE } else { "wellcast" }),
    [string]$Region = $(if ($env:AWS_REGION) { $env:AWS_REGION } else { "ap-south-1" })
)

$ErrorActionPreference = "Stop"
if (-not $ForecastBucket -or -not $WebBucket) {
    throw "Set `$env:FORECAST_BUCKET and `$env:WEB_BUCKET (or pass -ForecastBucket and -WebBucket) before running deploy.ps1."
}

Write-Host "=== 1. Syncing Data Lake & Static API JSONs ===" -ForegroundColor Cyan
& "$PSScriptRoot\..\data\scripts\upload_to_s3.ps1" -Bucket $ForecastBucket -Profile $Profile -Region $Region

Write-Host "=== 2. Packaging & Updating AWS Lambda ($LambdaName) ===" -ForegroundColor Cyan
$pkgDir = Join-Path $PSScriptRoot "build\lambda_pkg"
$zipPath = Join-Path $PSScriptRoot "build\lambda_api.zip"
if (Test-Path $pkgDir) { Remove-Item -Recurse -Force $pkgDir }
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
New-Item -ItemType Directory -Force -Path $pkgDir | Out-Null

New-Item -ItemType Directory -Force -Path (Join-Path $pkgDir "backend") | Out-Null
Copy-Item "$PSScriptRoot\..\backend\lambda_handler.py" $pkgDir
Copy-Item "$PSScriptRoot\..\backend\athena_client.py" $pkgDir
Compress-Archive -Path "$pkgDir\*" -DestinationPath $zipPath

aws lambda update-function-code `
    --function-name $LambdaName `
    --zip-file "fileb://$zipPath" `
    --region $Region `
    --profile $Profile | Out-Null

Write-Host "=== 3. Building React Production Bundle ===" -ForegroundColor Cyan
Push-Location "$PSScriptRoot\..\frontend"
try {
    npm run build
} finally {
    Pop-Location
}

Write-Host "=== 4. Syncing Frontend Bundle to Private Web S3 (s3://$WebBucket/) ===" -ForegroundColor Cyan
aws s3 sync "$PSScriptRoot\..\frontend\dist/" "s3://$WebBucket/" `
    --exclude "index.html" `
    --cache-control "public, max-age=31536000, immutable" `
    --delete `
    --region $Region `
    --profile $Profile

aws s3 cp "$PSScriptRoot\..\frontend\dist\index.html" "s3://$WebBucket/index.html" `
    --cache-control "no-cache, no-store, must-revalidate" `
    --content-type "text/html; charset=utf-8" `
    --region $Region `
    --profile $Profile

if ($CloudFrontDistId) {
    Write-Host "=== 5. Invalidating CloudFront Distribution ($CloudFrontDistId) ===" -ForegroundColor Cyan
    aws cloudfront create-invalidation --distribution-id $CloudFrontDistId --paths "/*" --profile $Profile | Out-Null
}

Write-Host "=== WellCast Deployment Complete ===" -ForegroundColor Green
