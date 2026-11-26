# WellCast AWS Idle Resource & Cost Hygiene Audit (ap-south-1)
param(
    [string]$Profile = $(if ($env:AWS_PROFILE) { $env:AWS_PROFILE } else { "wellcast" }),
    [string]$Region = $(if ($env:AWS_REGION) { $env:AWS_REGION } else { "ap-south-1" }),
    [string]$DataBucket = $env:FORECAST_BUCKET,
    [string]$WebBucket = $env:WEB_BUCKET
)

$ErrorActionPreference = "Stop"

Write-Host "1. Checking SageMaker Endpoints (must be empty)..." -ForegroundColor Cyan
aws sagemaker list-endpoints --region $Region --profile $Profile

Write-Host "2. Checking SageMaker Notebook Instances (must be empty)..." -ForegroundColor Cyan
aws sagemaker list-notebook-instances --region $Region --profile $Profile

Write-Host "3. Checking SageMaker Studio Apps (must be empty)..." -ForegroundColor Cyan
aws sagemaker list-apps --region $Region --profile $Profile

Write-Host "4. Checking Running EC2 Instances (must be empty)..." -ForegroundColor Cyan
aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --query "Reservations[].Instances[].InstanceId" --region $Region --profile $Profile

Write-Host "5. Checking RDS Databases (must be empty)..." -ForegroundColor Cyan
aws rds describe-db-instances --query "DBInstances[].DBInstanceIdentifier" --region $Region --profile $Profile

if ($DataBucket) {
    Write-Host "6. Checking Data Lake S3 Public Access Block ($DataBucket)..." -ForegroundColor Cyan
    aws s3api get-public-access-block --bucket $DataBucket --profile $Profile
}
if ($WebBucket) {
    Write-Host "7. Checking Web S3 Public Access Block ($WebBucket)..." -ForegroundColor Cyan
    aws s3api get-public-access-block --bucket $WebBucket --profile $Profile
}
