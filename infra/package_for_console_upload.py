"""Package WellCast artifacts into clean archive files for browser-only AWS Console / CloudShell upload.

No AWS CLI or AWS credentials are required on this machine.
Produces in `infra/build/`:
  1. `lambda_api.zip`           -> Upload directly in AWS Lambda Console ("Upload from .zip file")
  2. `data_lake_bundle.zip`     -> Upload to AWS CloudShell (browser) & unzip/sync to S3 Data Lake bucket
  3. `sagemaker_sourcedir.tar.gz` -> Included inside `data_lake_bundle.zip` under `models/code/sourcedir.tar.gz`
  4. `frontend_dist.zip`        -> Upload to S3 Web Console (or unzip in CloudShell) for CloudFront hosting
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "infra" / "build"
PROCESSED = REPO_ROOT / "data" / "processed_local"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


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


def build_data_lake_zip(sm_tar: Path) -> Path:
    out = BUILD_DIR / "data_lake_bundle.zip"
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for subdir in ("raw", "curated", "forecasts", "api"):
            base = PROCESSED / subdir
            if not base.exists():
                continue
            for fp in sorted(base.rglob("*")):
                if fp.is_file():
                    rel = fp.relative_to(PROCESSED).as_posix()
                    zf.write(fp, arcname=rel)
        zf.write(sm_tar, arcname="models/code/sourcedir.tar.gz")
    return out


def build_frontend_zip() -> Path:
    out = BUILD_DIR / "frontend_dist.zip"
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for fp in sorted(FRONTEND_DIST.rglob("*")):
            if fp.is_file():
                rel = fp.relative_to(FRONTEND_DIST).as_posix()
                zf.write(fp, arcname=rel)
    return out


def main() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    lam = build_lambda_zip()
    sm = build_sagemaker_tarball()
    lake = build_data_lake_zip(sm)
    fe = build_frontend_zip()

    for p in (lam, sm, lake, fe):
        kb = round(p.stat().st_size / 1024.0, 1)
        print(f"BUILT {p.name:30s} -> {kb:8.1f} KB ({p})")


if __name__ == "__main__":
    main()
