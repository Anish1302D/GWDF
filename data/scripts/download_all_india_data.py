"""Download authentic Pan-India CGWB Manual Quarterly Groundwater CSVs (all states/UTs, 1991-2025)
from the Government of India National Water Data Portal (NWIC) + NASA POWER 1.5-deg Agroclimatology
Monthly Precipitation Grid (2012-2025) covering all 36 Indian States & Union Territories.
"""

from __future__ import annotations

import calendar
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import ssl
import time
import urllib.request

import pandas as pd
from shapely.geometry import shape

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_LOCAL = REPO_ROOT / "data" / "raw_local"
CGWB_ALL_DIR = RAW_LOCAL / "cgwb_all_india"


def _ssl_ctx() -> ssl.SSLContext:
    return ssl.create_default_context()


def download_all_cgwb_csvs() -> int:
    CGWB_ALL_DIR.mkdir(parents=True, exist_ok=True)
    ctx = _ssl_ctx()
    pkg_url = "https://nwdp.nwic.gov.in/api/3/action/package_show?id=956add67-cba9-41a5-9d5c-96d73db44aef"
    req = urllib.request.Request(pkg_url, headers={"User-Agent": "WellCast-India/2.0"})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        pkg = json.loads(resp.read().decode("utf-8"))

    resources = [
        r for r in pkg["result"]["resources"]
        if (r.get("url") or "").lower().endswith(".csv") and (r.get("size") or 0) > 1000
    ]

    def _fetch_one(res: dict) -> tuple[str, int]:
        url = res["url"]
        fname = url.split("/")[-1].lower()
        dest = CGWB_ALL_DIR / fname
        expected = int(res.get("size") or 0)
        if dest.exists() and dest.stat().st_size >= max(1000, int(expected * 0.95)):
            return fname, dest.stat().st_size
        for attempt in range(3):
            try:
                r_req = urllib.request.Request(url, headers={"User-Agent": "WellCast-India/2.0"})
                with urllib.request.urlopen(r_req, timeout=90, context=_ssl_ctx()) as r, open(dest, "wb") as f:
                    while chunk := r.read(1024 * 256):
                        f.write(chunk)
                return fname, dest.stat().st_size
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1.5)
        return fname, 0

    total_bytes = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_fetch_one, r) for r in resources]
        for idx, fut in enumerate(as_completed(futs), 1):
            _, sz = fut.result()
            total_bytes += sz
            if idx % 20 == 0 or idx == len(resources):
                print(f"CGWB downloaded {idx}/{len(resources)} files ({round(total_bytes / 1e6, 1)} MB)...")
    return len(resources)


def download_all_india_rainfall_grid() -> int:
    out_csv = RAW_LOCAL / "nasa_power_india_grid_monthly_2012_2025.csv"
    if out_csv.exists() and out_csv.stat().st_size > 500_000:
        df_existing = pd.read_csv(out_csv)
        print(f"Existing India rainfall grid found: {len(df_existing)} rows across {df_existing['grid_id'].nunique()} cells")
        return int(df_existing["grid_id"].nunique())

    # Snap all 5,966 Indian subdistrict centroids to a 1.5-degree agro-climatic grid
    gj = json.loads((RAW_LOCAL / "india_subdistricts.geojson").read_text(encoding="utf-8"))
    grid_cells: dict[tuple[float, float], str] = {}
    for feat in gj["features"]:
        c = shape(feat["geometry"]).centroid
        glat = round(round(c.y / 1.5) * 1.5, 2)
        glon = round(round(c.x / 1.5) * 1.5, 2)
        grid_cells[(glat, glon)] = f"G_{glat:.2f}_{glon:.2f}"

    pts = sorted(grid_cells.items())
    print(f"Fetching NASA POWER Agroclimatology (2012-2025) for {len(pts)} All-India 1.5-deg grid cells...")

    def _fetch_grid_cell(item: tuple[tuple[float, float], str]) -> list[dict]:
        (glat, glon), gid = item
        url = (
            f"https://power.larc.nasa.gov/api/temporal/monthly/point?"
            f"parameters=PRECTOTCORR&community=AG&longitude={glon}&latitude={glat}&start=2012&end=2025&format=JSON"
        )
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "WellCast-India-Hydrology/2.0"})
                with urllib.request.urlopen(req, timeout=35, context=_ssl_ctx()) as r:
                    data = json.loads(r.read().decode("utf-8"))
                vals = data["properties"]["parameter"]["PRECTOTCORR"]
                cell_rows = []
                for ym, mm_day in vals.items():
                    yr, mo = int(ym[:4]), int(ym[4:6])
                    if mo < 1 or mo > 12 or mm_day < 0:
                        continue
                    days = calendar.monthrange(yr, mo)[1]
                    cell_rows.append(
                        {
                            "grid_id": gid,
                            "grid_lat": glat,
                            "grid_lon": glon,
                            "month": f"{yr:04d}-{mo:02d}-01",
                            "rainfall_mm": round(float(mm_day) * days, 2),
                        }
                    )
                return cell_rows
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(1.5 * (attempt + 1))
        return []

    all_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(_fetch_grid_cell, it) for it in pts]
        for idx, fut in enumerate(as_completed(futs), 1):
            all_rows.extend(fut.result())
            if idx % 30 == 0 or idx == len(pts):
                print(f"NASA POWER fetched {idx}/{len(pts)} grid cells...")

    df = pd.DataFrame(all_rows).sort_values(["grid_id", "month"]).reset_index(drop=True)
    df.to_csv(out_csv, index=False)
    print(f"Saved {len(df)} grid-month rows across {df['grid_id'].nunique()} All-India cells to {out_csv.name}")
    return int(df["grid_id"].nunique())


if __name__ == "__main__":
    n_cgwb = download_all_cgwb_csvs()
    n_grid = download_all_india_rainfall_grid()
    print(f"ALL_INDIA_DOWNLOAD_COMPLETE: cgwb_files={n_cgwb}, rain_grid_cells={n_grid}")
