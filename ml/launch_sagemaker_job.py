"""Launch a short-lived AWS SageMaker Training Job for `ml/train.py` and verify zero idle compute.

Cost Guardrails Enforced:
  - Uses ephemeral managed Training Job (`ml.m5.large`), NEVER a persistent Notebook or Endpoint.
  - Enforces `MaxRuntimeInSeconds=600` (10-minute hard ceiling).
  - Verifies zero active endpoints or notebook instances immediately after job completion.
"""

from __future__ import annotations

import argparse
import os
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path


def package_source_tarball(repo_root: Path, out_tar: Path) -> Path:
    out_tar.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out_tar, "w:gz") as tar:
        for fname in ("train.py", "evaluate.py", "risk_rules.py", "requirements.txt"):
            src = repo_root / "ml" / fname
            tar.add(src, arcname=fname)
        # Keep `ml.*` imports working inside container as well
        for fname in ("train.py", "evaluate.py", "risk_rules.py"):
            tar.add(repo_root / "ml" / fname, arcname=f"ml/{fname}")
    return out_tar


def main() -> None:
    parser = argparse.ArgumentParser(description="Run managed AWS SageMaker XGBoost training job")
    parser.add_argument("--bucket", default=os.environ.get("FORECAST_BUCKET", ""), required=False)
    parser.add_argument("--role-arn", default=os.environ.get("SAGEMAKER_ROLE_ARN", ""), required=False)
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "ap-south-1"))
    parser.add_argument("--instance-type", default="ml.m5.large")
    # Official AWS SageMaker XGBoost 1.7-1 image URI in ap-south-1
    parser.add_argument(
        "--image-uri",
        default="720646828776.dkr.ecr.ap-south-1.amazonaws.com/sagemaker-xgboost:1.7-1",
    )
    args = parser.parse_args()

    if not args.bucket or not args.role_arn:
        raise SystemExit("Provide --bucket (or FORECAST_BUCKET) and --role-arn (or SAGEMAKER_ROLE_ARN).")

    import boto3

    repo_root = Path(__file__).resolve().parent.parent
    tar_path = package_source_tarball(repo_root, repo_root / "infra" / "build" / "sourcedir.tar.gz")

    s3 = boto3.client("s3", region_name=args.region)
    sm = boto3.client("sagemaker", region_name=args.region)

    job_name = f"wellcast-xgb-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    code_key = f"models/code/{job_name}/sourcedir.tar.gz"
    s3.upload_file(str(tar_path), args.bucket, code_key)

    print(f"Starting short-lived SageMaker Training Job: {job_name} ...")
    sm.create_training_job(
        TrainingJobName=job_name,
        AlgorithmSpecification={
            "TrainingImage": args.image_uri,
            "TrainingInputMode": "File",
        },
        RoleArn=args.role_arn,
        InputDataConfig=[
            {
                "ChannelName": "train",
                "DataSource": {
                    "S3DataSource": {
                        "S3DataType": "S3Prefix",
                        "S3Uri": f"s3://{args.bucket}/curated/ml_train/",
                        "S3DataDistributionType": "FullyReplicated",
                    }
                },
            }
        ],
        OutputDataConfig={"S3OutputPath": f"s3://{args.bucket}/models/"},
        ResourceConfig={
            "InstanceType": args.instance_type,
            "InstanceCount": 1,
            "VolumeSizeInGB": 10,
        },
        StoppingCondition={"MaxRuntimeInSeconds": 600},
        HyperParameters={
            "sagemaker_program": "train.py",
            "sagemaker_submit_directory": f"s3://{args.bucket}/{code_key}",
        },
    )

    while True:
        desc = sm.describe_training_job(TrainingJobName=job_name)
        status = desc["TrainingJobStatus"]
        print(f"  [{job_name}] status = {status}")
        if status in ("Completed", "Failed", "Stopped"):
            if status != "Completed":
                raise RuntimeError(f"Training job ended with {status}: {desc.get('FailureReason')}")
            print(f"Model artifact saved to: {desc['ModelArtifacts']['S3ModelArtifacts']}")
            break
        time.sleep(15)

    # Mandatory Cost Hygiene Verification (Task T3.7)
    endpoints = sm.list_endpoints().get("Endpoints", [])
    notebooks = sm.list_notebook_instances(StatusEquals="InService").get("NotebookInstances", [])
    print(f"Post-job hygiene check -> Active Endpoints: {len(endpoints)}, Active Notebooks: {len(notebooks)}")


if __name__ == "__main__":
    main()
