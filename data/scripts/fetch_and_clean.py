"""Phase 1 Data Cleaning, Spatial Standardization & S3 Raw Parquet Builder.

Ingests authentic public datasets cached in `data/raw_local/`:
  1. Maharashtra Sub-District (Taluka/Block) Boundaries GeoJSON (359 blocks across 36 districts)
  2. CGWB Manual Quarterly Groundwater Levels (1991-2025, National Water Data Portal / NWIC)
  3. GSDA-Maharashtra Manual Groundwater Levels (1970-2025, NWIC)
  4. NASA POWER Agroclimatology Gridded Monthly Precipitation (2012-2025, 36 districts)

Outputs:
  - `data/processed_local/raw/block/blocks.parquet`
  - `data/processed_local/raw/rainfall_monthly/rainfall_monthly.parquet`
  - `data/processed_local/raw/water_level/water_level.parquet`
  - `data/processed_local/api/geojson/MH_blocks.geojson` & `frontend/public/geo/MH_blocks.geojson`
  - `data/sample/*.csv` (lightweight 40-row samples tracked in Git)
  - `data/processed_local/cleaning_report.json`
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from shapely.geometry import Point, mapping, shape
from shapely.strtree import STRtree

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_LOCAL = REPO_ROOT / "data" / "raw_local"
PROCESSED_LOCAL = REPO_ROOT / "data" / "processed_local"
SAMPLE_DIR = REPO_ROOT / "data" / "sample"
FRONTEND_GEO_DIR = REPO_ROOT / "frontend" / "public" / "geo"
ALIASES_PATH = Path(__file__).resolve().parent / "name_aliases.json"


def _load_aliases() -> dict[str, dict[str, str]]:
    return json.loads(ALIASES_PATH.read_text(encoding="utf-8"))


def normalize_text(val: Any) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    s = str(val).strip().upper()
    if s in ("-", "--", "NA", "N/A", "NONE", "NULL", "NAN"):
        return ""
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\b(TALUKA|TEHSIL|TAHSIL|BLOCK|SUBDISTRICT|SUB DISTRICT)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_district(val: Any, aliases: dict[str, dict[str, str]]) -> str:
    norm = normalize_text(val)
    return aliases["districts"].get(norm, norm)


def normalize_block(val: Any, aliases: dict[str, dict[str, str]]) -> str:
    norm = normalize_text(val)
    return aliases["blocks"].get(norm, norm)


def _round_coords(coords: Any, decimals: int = 4) -> Any:
    if isinstance(coords, (list, tuple)):
        if coords and isinstance(coords[0], (int, float)):
            return [round(float(coords[0]), decimals), round(float(coords[1]), decimals)]
        return [_round_coords(c, decimals) for c in coords]
    return coords


def build_master_blocks_and_geojson(aliases: dict[str, dict[str, str]]) -> tuple[pd.DataFrame, list[Any], dict[str, Any]]:
    gj_path = RAW_LOCAL / "mh_subdistricts.geojson"
    gj = json.loads(gj_path.read_text(encoding="utf-8"))

    records: list[dict[str, Any]] = []
    for feat in gj["features"]:
        props = feat["properties"]
        raw_dist = props.get("dtname", "")
        if normalize_text(raw_dist) == "VIJAYAPURA":
            continue  # Exclude non-Maharashtra border sliver
        dist_norm = normalize_district(raw_dist, aliases)
        blk_norm = normalize_block(props.get("sdtname", ""), aliases)
        geom = shape(feat["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        centroid = geom.centroid
        records.append(
            {
                "district_norm": dist_norm,
                "block_norm": blk_norm,
                "district_display": dist_norm.title(),
                "block_display": props.get("sdtname", "").strip().title(),
                "lat": round(float(centroid.y), 4),
                "lon": round(float(centroid.x), 4),
                "geom": geom,
            }
        )

    # Deduplicate any split polygon parts by unioning geometries per (district_norm, block_norm)
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for rec in records:
        key = (rec["district_norm"], rec["block_norm"])
        if key not in grouped:
            grouped[key] = rec
        else:
            merged_geom = grouped[key]["geom"].union(rec["geom"])
            c = merged_geom.centroid
            grouped[key]["geom"] = merged_geom
            grouped[key]["lat"] = round(float(c.y), 4)
            grouped[key]["lon"] = round(float(c.x), 4)

    sorted_keys = sorted(grouped.keys())
    dist_seq: dict[str, int] = {}
    block_rows: list[dict[str, Any]] = []
    polys: list[Any] = []
    out_features: list[dict[str, Any]] = []

    for dist_norm, blk_norm in sorted_keys:
        rec = grouped[(dist_norm, blk_norm)]
        dist_code = aliases["district_codes"].get(dist_norm, dist_norm[:3])
        dist_seq[dist_code] = dist_seq.get(dist_code, 0) + 1
        block_id = f"MH-{dist_code}-{dist_seq[dist_code]:03d}"

        block_rows.append(
            {
                "block_id": block_id,
                "state_code": "MH",
                "state": "Maharashtra",
                "district": rec["district_display"],
                "block_name": rec["block_display"],
                "district_norm": dist_norm,
                "block_norm": blk_norm,
                "extraction_stage": "Unknown",
                "extraction_stage_code": -1,
                "lat": rec["lat"],
                "lon": rec["lon"],
                "granularity": "block",
            }
        )
        polys.append(rec["geom"])

        simp = rec["geom"].simplify(0.0055, preserve_topology=True)
        geom_json = mapping(simp)
        geom_json["coordinates"] = _round_coords(geom_json["coordinates"], 4)
        out_features.append(
            {
                "type": "Feature",
                "properties": {
                    "block_id": block_id,
                    "state": "Maharashtra",
                    "district": rec["district_display"],
                    "block_name": rec["block_display"],
                },
                "geometry": geom_json,
            }
        )

    blocks_df = pd.DataFrame(block_rows)
    out_gj = {"type": "FeatureCollection", "features": out_features}
    return blocks_df, polys, out_gj


def build_water_levels(
    blocks_df: pd.DataFrame,
    polys: list[Any],
    aliases: dict[str, dict[str, str]],
    min_year: int = 2013,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    # Build lookup indexes
    exact_map: dict[tuple[str, str], str] = {
        (r.district_norm, r.block_norm): r.block_id for r in blocks_df.itertuples()
    }
    dist_to_blocks: dict[str, list[str]] = {}
    for r in blocks_df.itertuples():
        dist_to_blocks.setdefault(r.district_norm, []).append(r.block_norm)

    tree = STRtree(polys)
    idx_to_block_id = blocks_df["block_id"].tolist()

    raw_frames: list[pd.DataFrame] = []

    # 1. CGWB Manual Quarterly (1991-2020 & 2021-2025)
    for fn in ("cgwb_mh_1991_2020.csv", "cgwb_mh_2021_2025.csv"):
        p = RAW_LOCAL / fn
        if p.exists():
            df = pd.read_csv(p, low_memory=False)
            sub = pd.DataFrame(
                {
                    "well_id": "CGWB_" + df["Station"].astype(str).str.strip(),
                    "district_raw": df["District"],
                    "block_raw": np.where(
                        df["Tehsil"].astype(str).str.strip().isin(["-", "", "nan"]),
                        df["Block"],
                        df["Tehsil"],
                    ),
                    "lat": pd.to_numeric(df["Latitude"], errors="coerce"),
                    "lon": pd.to_numeric(df["Longitude"], errors="coerce"),
                    "obs_dt": pd.to_datetime(df["Data Acquisition Time"], dayfirst=True, errors="coerce"),
                    "depth_mbgl": pd.to_numeric(
                        df["Groundwater Level Quarterly Manual (meter)"], errors="coerce"
                    ),
                    "agency": "CGWB",
                }
            )
            raw_frames.append(sub)

    # 2. GSDA-Maharashtra Manual (1970-2025)
    gsda_p = RAW_LOCAL / "gsda_mh_1970_2025.csv"
    if gsda_p.exists():
        gsda = pd.read_csv(
            gsda_p,
            usecols=[
                "Well ID",
                "District Name ",
                "Block Name ",
                "Latitude ",
                "Longitude ",
                "Date of Monitoring",
                "Water Level, m bgl",
            ],
            low_memory=False,
        )
        sub_g = pd.DataFrame(
            {
                "well_id": "GSDA_" + gsda["Well ID"].astype(str).str.strip(),
                "district_raw": gsda["District Name "],
                "block_raw": gsda["Block Name "],
                "lat": pd.to_numeric(gsda["Latitude "], errors="coerce"),
                "lon": pd.to_numeric(gsda["Longitude "], errors="coerce"),
                "obs_dt": pd.to_datetime(gsda["Date of Monitoring"], dayfirst=True, errors="coerce"),
                "depth_mbgl": pd.to_numeric(gsda["Water Level, m bgl"], errors="coerce"),
                "agency": "GSDA",
            }
        )
        raw_frames.append(sub_g)

    combined = pd.concat(raw_frames, ignore_index=True)
    total_raw_rows = int(len(combined))

    # Filter date >= min_year and physically valid depth (0.0 < depth <= 250.0 m bgl)
    combined = combined.dropna(subset=["obs_dt", "depth_mbgl"]).copy()
    combined["year"] = combined["obs_dt"].dt.year
    combined["month"] = combined["obs_dt"].dt.month
    combined = combined[
        (combined["year"] >= min_year)
        & (combined["depth_mbgl"] > 0.0)
        & (combined["depth_mbgl"] <= 250.0)
    ].copy()

    # Map calendar month to Pre-Monsoon (Mar-May -> anchor YYYY-05-01) and Post-Monsoon (Oct-Nov -> YYYY-11-01)
    combined = combined[combined["month"].isin([3, 4, 5, 10, 11])].copy()
    combined["season"] = np.where(combined["month"].isin([3, 4, 5]), "pre-monsoon", "post-monsoon")
    combined["season_code"] = np.where(combined["season"] == "pre-monsoon", 0, 1)
    # Priority closeness to canonical May (month 5) or Nov (month 11) per well-season
    combined["month_priority"] = np.where(
        combined["season_code"] == 0, (5 - combined["month"]).abs(), (11 - combined["month"]).abs()
    )
    combined = combined.sort_values(["well_id", "year", "season_code", "month_priority"])
    combined = combined.drop_duplicates(subset=["well_id", "year", "season_code"], keep="first").copy()

    # Resolve (district_raw, block_raw, lat, lon) -> canonical block_id
    combined["dist_norm"] = [normalize_district(x, aliases) for x in combined["district_raw"]]
    combined["blk_norm"] = [normalize_block(x, aliases) for x in combined["block_raw"]]

    unique_pairs = combined[["dist_norm", "blk_norm"]].drop_duplicates()
    pair_lookup: dict[tuple[str, str], str | None] = {}
    for d_n, b_n in unique_pairs.itertuples(index=False):
        if (d_n, b_n) in exact_map:
            pair_lookup[(d_n, b_n)] = exact_map[(d_n, b_n)]
        elif d_n in dist_to_blocks and b_n:
            matches = difflib.get_close_matches(b_n, dist_to_blocks[d_n], n=1, cutoff=0.80)
            pair_lookup[(d_n, b_n)] = exact_map[(d_n, matches[0])] if matches else None
        else:
            pair_lookup[(d_n, b_n)] = None

    combined["block_id"] = [pair_lookup.get((d, b)) for d, b in zip(combined["dist_norm"], combined["blk_norm"])]

    # Spatial point-in-polygon fallback for rows with valid GPS coordinates
    missing_mask = combined["block_id"].isna() & combined["lat"].between(15.5, 22.5) & combined["lon"].between(72.5, 81.0)
    if missing_mask.any():
        unresolved_coords = combined.loc[missing_mask, ["lon", "lat"]].drop_duplicates()
        coord_map: dict[tuple[float, float], str | None] = {}
        for lon_v, lat_v in unresolved_coords.itertuples(index=False):
            pt = Point(float(lon_v), float(lat_v))
            cand_idxs = tree.query(pt)
            matched_id = None
            for idx in cand_idxs:
                if polys[int(idx)].contains(pt):
                    matched_id = idx_to_block_id[int(idx)]
                    break
            coord_map[(lon_v, lat_v)] = matched_id

        combined.loc[missing_mask, "block_id"] = [
            coord_map.get((lo, la))
            for lo, la in zip(combined.loc[missing_mask, "lon"], combined.loc[missing_mask, "lat"])
        ]

    matched_rows = int(combined["block_id"].notna().sum())
    match_rate_pct = round(100.0 * matched_rows / max(len(combined), 1), 2)
    combined = combined.dropna(subset=["block_id"]).copy()

    combined["obs_date"] = np.where(
        combined["season_code"] == 0,
        combined["year"].astype(str) + "-05-01",
        combined["year"].astype(str) + "-11-01",
    )

    wl_agg = (
        combined.groupby(["block_id", "obs_date", "year", "season", "season_code"], as_index=False)
        .agg(
            depth_mbgl=("depth_mbgl", "median"),
            well_count=("well_id", "nunique"),
        )
        .sort_values(["block_id", "obs_date"])
        .reset_index(drop=True)
    )
    wl_agg["depth_mbgl"] = wl_agg["depth_mbgl"].round(2)
    wl_agg["obs_date"] = pd.to_datetime(wl_agg["obs_date"]).dt.date
    wl_agg["year"] = wl_agg["year"].astype("int32")
    wl_agg["season_code"] = wl_agg["season_code"].astype("int32")
    wl_agg["well_count"] = wl_agg["well_count"].astype("int32")
    wl_agg["is_imputed"] = False

    stats = {
        "total_raw_well_readings_scanned": total_raw_rows,
        "valid_seasonal_well_readings_2013_plus": int(len(combined)),
        "block_match_rate_pct": match_rate_pct,
        "unique_blocks_with_water_levels": int(wl_agg["block_id"].nunique()),
        "block_season_rows": int(len(wl_agg)),
        "min_obs_date": str(wl_agg["obs_date"].min()),
        "max_obs_date": str(wl_agg["obs_date"].max()),
    }
    return wl_agg, stats


def build_monthly_rainfall(
    blocks_df: pd.DataFrame, aliases: dict[str, dict[str, str]]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rain_csv = RAW_LOCAL / "nasa_power_mh_district_monthly_2012_2025.csv"
    df = pd.read_csv(rain_csv)
    df["district_norm"] = [normalize_district(x, aliases) for x in df["district_raw"]]
    df["month_dt"] = pd.to_datetime(df["month"])
    df["cal_month"] = df["month_dt"].dt.month
    df["year"] = df["month_dt"].dt.year

    # Compute 2013-2024 climatological monthly normal per district
    clim = (
        df[(df["year"] >= 2013) & (df["year"] <= 2024)]
        .groupby(["district_norm", "cal_month"], as_index=False)["rainfall_mm"]
        .mean()
        .rename(columns={"rainfall_mm": "normal_rainfall_mm"})
    )
    clim["normal_rainfall_mm"] = clim["normal_rainfall_mm"].round(2)

    df = df.merge(clim, on=["district_norm", "cal_month"], how="left")
    df["departure_from_normal_pct"] = np.where(
        df["normal_rainfall_mm"] > 1.0,
        ((df["rainfall_mm"] - df["normal_rainfall_mm"]) / df["normal_rainfall_mm"]) * 100.0,
        0.0,
    ).round(2)

    # Expand district monthly series to child blocks cleanly via district_norm
    blk_map = blocks_df[["block_id", "district_norm"]].copy()
    expanded = blk_map.merge(
        df[["district_norm", "month_dt", "rainfall_mm", "normal_rainfall_mm", "departure_from_normal_pct"]],
        on="district_norm",
        how="inner",
    )
    expanded["month"] = expanded["month_dt"].dt.date
    expanded["rainfall_source_level"] = "district_gridded"
    expanded["is_imputed"] = False

    out_cols = [
        "block_id",
        "month",
        "rainfall_mm",
        "normal_rainfall_mm",
        "departure_from_normal_pct",
        "rainfall_source_level",
        "is_imputed",
    ]
    expanded = expanded[out_cols].sort_values(["block_id", "month"]).reset_index(drop=True)

    stats = {
        "districts_covered": int(df["district_norm"].nunique()),
        "blocks_mapped": int(expanded["block_id"].nunique()),
        "block_month_rows": int(len(expanded)),
        "min_month": str(expanded["month"].min()),
        "max_month": str(expanded["month"].max()),
    }
    return expanded, stats


def main() -> None:
    aliases = _load_aliases()
    blocks_df, polys, out_gj = build_master_blocks_and_geojson(aliases)
    wl_df, wl_stats = build_water_levels(blocks_df, polys, aliases, min_year=2013)
    rain_df, rain_stats = build_monthly_rainfall(blocks_df, aliases)

    # Clean final block table columns matching sql/01_create_tables.sql
    block_cols = [
        "block_id",
        "state_code",
        "state",
        "district",
        "block_name",
        "extraction_stage",
        "extraction_stage_code",
        "lat",
        "lon",
        "granularity",
    ]
    blocks_clean = blocks_df[block_cols].copy()
    blocks_clean["extraction_stage_code"] = blocks_clean["extraction_stage_code"].astype("int32")

    # Data quality assertions (Task T1.3)
    assert blocks_clean["block_id"].is_unique, "Duplicate block_id in blocks!"
    assert not wl_df.duplicated(subset=["block_id", "obs_date"]).any(), "Duplicate (block_id, obs_date) in water_level!"
    assert not rain_df.duplicated(subset=["block_id", "month"]).any(), "Duplicate (block_id, month) in rainfall_monthly!"
    assert (wl_df["depth_mbgl"] >= 0).all() and (wl_df["depth_mbgl"] <= 300).all(), "Invalid depth_mbgl!"
    assert (rain_df["rainfall_mm"] >= 0).all(), "Negative rainfall_mm!"

    # Write Parquet raw lake
    for sub in ("block", "water_level", "rainfall_monthly"):
        (PROCESSED_LOCAL / "raw" / sub).mkdir(parents=True, exist_ok=True)

    blocks_clean.to_parquet(PROCESSED_LOCAL / "raw" / "block" / "blocks.parquet", index=False)
    wl_df.to_parquet(PROCESSED_LOCAL / "raw" / "water_level" / "water_level.parquet", index=False)
    rain_df.to_parquet(PROCESSED_LOCAL / "raw" / "rainfall_monthly" / "rainfall_monthly.parquet", index=False)

    # Write simplified GeoJSON to API dir and Frontend public dir
    for gj_dir in (PROCESSED_LOCAL / "api" / "geojson", FRONTEND_GEO_DIR):
        gj_dir.mkdir(parents=True, exist_ok=True)
        (gj_dir / "MH_blocks.geojson").write_text(
            json.dumps(out_gj, separators=(",", ":")), encoding="utf-8"
        )

    # Write lightweight Git-tracked sample files (40 rows each)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    blocks_clean.head(40).to_csv(SAMPLE_DIR / "blocks_sample.csv", index=False)
    wl_df.head(40).to_csv(SAMPLE_DIR / "water_level_sample.csv", index=False)
    rain_df.head(40).to_csv(SAMPLE_DIR / "rainfall_monthly_sample.csv", index=False)

    gj_size_kb = round((FRONTEND_GEO_DIR / "MH_blocks.geojson").stat().st_size / 1024.0, 1)
    report = {
        "total_canonical_blocks": int(len(blocks_clean)),
        "total_districts": int(blocks_clean["district"].nunique()),
        "simplified_geojson_kb": gj_size_kb,
        "water_level": wl_stats,
        "rainfall_monthly": rain_stats,
    }
    (PROCESSED_LOCAL / "cleaning_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
