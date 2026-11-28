"""Package Pan-India WellCast artifacts for pure-GUI S3 & Lambda Web Console upload.

Produces:
  1. `infra/build/lambda_api.zip`       -> Upload in AWS Lambda Console ("Upload from .zip file")
  2. `infra/s3_data_bucket_upload/`     -> Compact state-sharded Data Lake + API folder ready to
                                           drag-and-drop into your S3 Data Bucket in the browser.
"""

from __future__ import annotations

import shutil
import tarfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "infra" / "build"
S3_FOLDER = REPO_ROOT / "infra" / "s3_data_bucket_upload"
PROCESSED = REPO_ROOT / "data" / "processed_local"


def build_lambda_zip() -> Path:
    out = BUILD_DIR / "lambda_api.zip"
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(REPO_ROOT / "backend" / "lambda_handler.py", arcname="lambda_handler.py")
        zf.write(REPO_ROOT / "backend" / "athena_client.py", arcname="athena_client.py")
    return out


def build_sagemaker_tarball() -> Path:
    out = BUILD_DIR / "sagemaker_sourcedir.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        for fname in ("train.py", "evaluate.py", "risk_rules.py", "requirements.txt"):
            tar.add(REPO_ROOT / "ml" / fname, arcname=fname)
        for fname in ("train.py", "evaluate.py", "risk_rules.py"):
            tar.add(REPO_ROOT / "ml" / fname, arcname=f"ml/{fname}")
    return out


def build_s3_drag_and_drop_folder(sm_tar: Path) -> tuple[int, float]:
    if S3_FOLDER.exists():
        shutil.rmtree(S3_FOLDER)

    parquet_rels = [
        Path("raw/block/blocks.parquet"),
        Path("raw/rainfall_monthly/rainfall_monthly.parquet"),
        Path("raw/water_level/water_level.parquet"),
        Path("curated/features/features.parquet"),
        Path("curated/ml_train/train_features.parquet"),
        Path("forecasts/forecasts.parquet"),
    ]
    for rel in parquet_rels:
        src = PROCESSED / rel
        dst = S3_FOLDER / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    sm_dst = S3_FOLDER / "models" / "code" / "sourcedir.tar.gz"
    sm_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sm_tar, sm_dst)

    shutil.copytree(PROCESSED / "api", S3_FOLDER / "api", dirs_exist_ok=True)

    all_files = [p for p in S3_FOLDER.rglob("*") if p.is_file()]
    total_mb = round(sum(p.stat().st_size for p in all_files) / (1024.0 * 1024.0), 2)
    return len(all_files), total_mb


def main() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    lam = build_lambda_zip()
    sm = build_sagemaker_tarball()
    n_files, mb = build_s3_drag_and_drop_folder(sm)
    print(f"BUILT {lam.name} -> {round(lam.stat().st_size / 1024.0, 1)} KB")
    print(f"BUILT Pan-India S3 upload folder: {S3_FOLDER} -> {n_files} files ({mb} MB)")


if __name__ == "__main__":
    main()
