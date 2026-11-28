"""Pan-India Data Cleaning, Spatial Standardization & S3 Raw Parquet Builder.

Ingests authentic public datasets cached in `data/raw_local/`:
  1. All-India Sub-District (Block/Tehsil/Taluka/Mandal) Boundaries (`india_subdistricts.geojson`, ~5,966 units across 36 States/UTs)
  2. All-India State Boundaries (`india_states.geojson`)
  3. Central Ground Water Board (CGWB) Manual Quarterly Groundwater Levels across ALL States/UTs (`cgwb_all_india/*.csv`, 1991-2025)
  4. GSDA-Maharashtra Manual Groundwater Levels (`gsda_mh_1970_2025.csv`)
  5. NASA POWER Agroclimatology 1.5-deg All-India Monthly Precipitation Grid (`2012-2025`)

Outputs:
  - `data/processed_local/raw/{block,water_level,rainfall_monthly}/*.parquet`
  - `frontend/public/geo/INDIA_states.geojson` & `frontend/public/geo/states/<STATE_CODE>_blocks.geojson`
  - `data/sample/*.csv` & `data/processed_local/cleaning_report.json`
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
    s = s.replace("&", " AND ")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\b(TALUKA|TEHSIL|TAHSIL|BLOCK|MANDAL|SUBDISTRICT|SUB DISTRICT|CIRCLE|C D BLOCK)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_state(val: Any, aliases: dict[str, dict[str, str]]) -> str:
    raw = str(val or "").strip().upper()
    if raw in aliases["states"]:
        return aliases["states"][raw]
    norm = normalize_text(val)
    return aliases["states"].get(norm, norm)


def normalize_district(val: Any, state_code: str, aliases: dict[str, dict[str, str]]) -> str:
    norm = normalize_text(val)
    if state_code != "MH" and norm in ("AURANGABAD", "HAMIRPUR", "PRATAPGARH", "BILASPUR", "BALRAMPUR", "RAIGARH"):
        return norm  # Preserve Bihar's Aurangabad, Chhattisgarh's Raigarh/Bilaspur, HP's Hamirpur, etc.
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


def _assign_district_codes(districts_sorted: list[str]) -> dict[str, str]:
    """Generate unique deterministic 3-char uppercase alphanumeric codes `[A-Z0-9]{3}` per district within a state."""
    used: set[str] = set()
    mapping_out: dict[str, str] = {}
    for d in districts_sorted:
        letters = re.sub(r"[^A-Z0-9]", "", d)
        cands = [
            letters[:3].ljust(3, "X"),
            (letters[:2] + letters[-1:]).ljust(3, "X"),
            (letters[:1] + letters[2:4]).ljust(3, "X"),
        ]
        for idx in range(1, 100):
            cands.append(f"{letters[:2].ljust(2, 'X')}{idx % 10}")
            cands.append(f"{letters[:1].ljust(1, 'X')}{idx:02d}")
        chosen = next(c for c in cands if len(c) == 3 and c not in used)
        used.add(chosen)
        mapping_out[d] = chosen
    return mapping_out


def build_all_india_blocks_and_geojsons(
    aliases: dict[str, dict[str, str]]
) -> tuple[pd.DataFrame, list[Any], dict[str, int]]:
    sub_gj = json.loads((RAW_LOCAL / "india_subdistricts.geojson").read_text(encoding="utf-8"))

    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for feat in sub_gj["features"]:
        props = feat["properties"]
        st_norm = normalize_state(props.get("stname", ""), aliases)
        st_code = aliases["state_codes"].get(st_norm)
        if not st_code:
            continue
        dt_norm = normalize_district(props.get("dtname", ""), st_code, aliases)
        blk_norm = normalize_block(props.get("sdtname", ""), aliases) or dt_norm
        geom = shape(feat["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)

        key = (st_code, dt_norm, blk_norm)
        if key not in grouped:
            c = geom.centroid
            grouped[key] = {
                "state_code": st_code,
                "state_display": st_norm.title(),
                "district_norm": dt_norm,
                "district_display": dt_norm.title(),
                "block_norm": blk_norm,
                "block_display": (props.get("sdtname") or dt_norm).strip().title(),
                "lat": round(float(c.y), 4),
                "lon": round(float(c.x), 4),
                "geom": geom,
            }
        else:
            merged = grouped[key]["geom"].union(geom)
            c = merged.centroid
            grouped[key]["geom"] = merged
            grouped[key]["lat"] = round(float(c.y), 4)
            grouped[key]["lon"] = round(float(c.x), 4)

    # Assign deterministic district codes per state
    states_districts: dict[str, set[str]] = {}
    for st_code, dt_norm, _ in grouped:
        states_districts.setdefault(st_code, set()).add(dt_norm)

    state_dist_codes: dict[tuple[str, str], str] = {}
    for st_code, dset in states_districts.items():
        dc_map = _assign_district_codes(sorted(dset))
        for d_n, code3 in dc_map.items():
            state_dist_codes[(st_code, d_n)] = code3

    sorted_keys = sorted(grouped.keys())
    seq_tracker: dict[tuple[str, str], int] = {}
    block_rows: list[dict[str, Any]] = []
    polys: list[Any] = []
    state_features: dict[str, list[dict[str, Any]]] = {}

    for st_code, dt_norm, blk_norm in sorted_keys:
        rec = grouped[(st_code, dt_norm, blk_norm)]
        d_code = state_dist_codes[(st_code, dt_norm)]
        seq_tracker[(st_code, d_code)] = seq_tracker.get((st_code, d_code), 0) + 1
        seq = seq_tracker[(st_code, d_code)]
        block_id = f"{st_code}-{d_code}-{seq:03d}"

        block_rows.append(
            {
                "block_id": block_id,
                "state_code": st_code,
                "state": rec["state_display"],
                "district": rec["district_display"],
                "block_name": rec["block_display"],
                "district_norm": dt_norm,
                "block_norm": blk_norm,
                "extraction_stage": "Unknown",
                "extraction_stage_code": -1,
                "lat": rec["lat"],
                "lon": rec["lon"],
                "granularity": "block",
            }
        )
        polys.append(rec["geom"])

        simp = rec["geom"].simplify(0.0065, preserve_topology=True)
        g_json = mapping(simp)
        g_json["coordinates"] = _round_coords(g_json["coordinates"], 4)
        state_features.setdefault(st_code, []).append(
            {
                "type": "Feature",
                "properties": {
                    "block_id": block_id,
                    "state_code": st_code,
                    "state": rec["state_display"],
                    "district": rec["district_display"],
                    "block_name": rec["block_display"],
                },
                "geometry": g_json,
            }
        )

    # Write per-state block GeoJSONs
    states_geo_dir = FRONTEND_GEO_DIR / "states"
    states_geo_dir.mkdir(parents=True, exist_ok=True)
    state_file_sizes_kb: dict[str, int] = {}
    for st_code, feats in state_features.items():
        fc_txt = json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":"))
        out_p = states_geo_dir / f"{st_code}_blocks.geojson"
        out_p.write_text(fc_txt, encoding="utf-8")
        state_file_sizes_kb[st_code] = int(round(len(fc_txt.encode("utf-8")) / 1024.0))
        if st_code == "MH":
            (FRONTEND_GEO_DIR / "MH_blocks.geojson").write_text(fc_txt, encoding="utf-8")

    # Build simplified INDIA_states.geojson
    st_gj_raw = json.loads((RAW_LOCAL / "india_states.geojson").read_text(encoding="utf-8"))
    st_merged: dict[str, Any] = {}
    st_names: dict[str, str] = {}
    for feat in st_gj_raw["features"]:
        props = feat["properties"]
        s_raw = props.get("STNAME") or props.get("STNAME_SH") or ""
        s_norm = normalize_state(s_raw, aliases)
        s_code = aliases["state_codes"].get(s_norm)
        if not s_code:
            continue
        geom = shape(feat["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        st_merged[s_code] = geom if s_code not in st_merged else st_merged[s_code].union(geom)
        st_names[s_code] = s_norm.title()

    india_st_feats = []
    for s_code in sorted(st_merged.keys()):
        simp_s = st_merged[s_code].simplify(0.015, preserve_topology=True)
        gs_json = mapping(simp_s)
        gs_json["coordinates"] = _round_coords(gs_json["coordinates"], 3)
        c = st_merged[s_code].centroid
        india_st_feats.append(
            {
                "type": "Feature",
                "properties": {
                    "state_code": s_code,
                    "state": st_names[s_code],
                    "lat": round(float(c.y), 3),
                    "lon": round(float(c.x), 3),
                },
                "geometry": gs_json,
            }
        )
    (FRONTEND_GEO_DIR / "INDIA_states.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": india_st_feats}, separators=(",", ":")),
        encoding="utf-8",
    )

    return pd.DataFrame(block_rows), polys, state_file_sizes_kb


def build_all_india_water_levels(
    blocks_df: pd.DataFrame,
    polys: list[Any],
    aliases: dict[str, dict[str, str]],
    min_year: int = 2013,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    exact_map: dict[tuple[str, str, str], str] = {
        (r.state_code, r.district_norm, r.block_norm): r.block_id for r in blocks_df.itertuples()
    }
    dist_to_blocks: dict[tuple[str, str], list[str]] = {}
    for r in blocks_df.itertuples():
        dist_to_blocks.setdefault((r.state_code, r.district_norm), []).append(r.block_norm)

    tree = STRtree(polys)
    idx_to_block_id = blocks_df["block_id"].tolist()

    frames: list[pd.DataFrame] = []
    cgwb_dir = RAW_LOCAL / "cgwb_all_india"
    csv_files = sorted(cgwb_dir.glob("*.csv")) if cgwb_dir.exists() else []
    if not csv_files:
        csv_files = [RAW_LOCAL / "cgwb_mh_1991_2020.csv", RAW_LOCAL / "cgwb_mh_2021_2025.csv"]

    for p in csv_files:
        if not p.exists() or p.stat().st_size < 500:
            continue
        try:
            df = pd.read_csv(p, low_memory=False)
        except Exception:
            continue
        if "Groundwater Level Quarterly Manual (meter)" not in df.columns:
            continue
        tehsil_s = df["Tehsil"].astype(str).str.strip() if "Tehsil" in df.columns else pd.Series([""] * len(df))
        blk_s = df["Block"].astype(str).str.strip() if "Block" in df.columns else tehsil_s
        frames.append(
            pd.DataFrame(
                {
                    "well_id": "CGWB_" + df["Station"].astype(str).str.strip() + "_" + df["State"].astype(str).str[:4],
                    "state_raw": df["State"],
                    "district_raw": df["District"],
                    "block_raw": np.where(tehsil_s.isin(["-", "", "nan", "None"]), blk_s, tehsil_s),
                    "lat": pd.to_numeric(df["Latitude"], errors="coerce"),
                    "lon": pd.to_numeric(df["Longitude"], errors="coerce"),
                    "obs_dt": pd.to_datetime(df["Data Acquisition Time"], dayfirst=True, errors="coerce"),
                    "depth_mbgl": pd.to_numeric(
                        df["Groundwater Level Quarterly Manual (meter)"], errors="coerce"
                    ),
                }
            )
        )

    # Merge high-density GSDA Maharashtra well network as well
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
        frames.append(
            pd.DataFrame(
                {
                    "well_id": "GSDA_" + gsda["Well ID"].astype(str).str.strip(),
                    "state_raw": "MAHARASHTRA",
                    "district_raw": gsda["District Name "],
                    "block_raw": gsda["Block Name "],
                    "lat": pd.to_numeric(gsda["Latitude "], errors="coerce"),
                    "lon": pd.to_numeric(gsda["Longitude "], errors="coerce"),
                    "obs_dt": pd.to_datetime(gsda["Date of Monitoring"], dayfirst=True, errors="coerce"),
                    "depth_mbgl": pd.to_numeric(gsda["Water Level, m bgl"], errors="coerce"),
                }
            )
        )

    combined = pd.concat(frames, ignore_index=True)
    total_scanned = int(len(combined))

    combined = combined.dropna(subset=["obs_dt", "depth_mbgl"]).copy()
    combined["year"] = combined["obs_dt"].dt.year
    combined["month"] = combined["obs_dt"].dt.month
    combined = combined[
        (combined["year"] >= min_year)
        & (combined["depth_mbgl"] > 0.0)
        & (combined["depth_mbgl"] <= 250.0)
        & (combined["month"].isin([3, 4, 5, 10, 11]))
    ].copy()

    combined["season"] = np.where(combined["month"].isin([3, 4, 5]), "pre-monsoon", "post-monsoon")
    combined["season_code"] = np.where(combined["season"] == "pre-monsoon", 0, 1)
    combined["month_priority"] = np.where(
        combined["season_code"] == 0, (5 - combined["month"]).abs(), (11 - combined["month"]).abs()
    )
    combined = combined.sort_values(["well_id", "year", "season_code", "month_priority"])
    combined = combined.drop_duplicates(subset=["well_id", "year", "season_code"], keep="first").copy()

    # Map unique stations -> block_id (fast per-station resolution instead of per-row!)
    stations = combined[["well_id", "state_raw", "district_raw", "block_raw", "lat", "lon"]].drop_duplicates(
        subset=["well_id"]
    )
    station_to_block: dict[str, str | None] = {}

    for row in stations.itertuples(index=False):
        st_norm = normalize_state(row.state_raw, aliases)
        st_code = aliases["state_codes"].get(st_norm, "")
        dt_norm = normalize_district(row.district_raw, st_code, aliases)
        blk_norm = normalize_block(row.block_raw, aliases)

        bid = exact_map.get((st_code, dt_norm, blk_norm))
        if bid is None and (st_code, dt_norm) in dist_to_blocks and blk_norm:
            m = difflib.get_close_matches(blk_norm, dist_to_blocks[(st_code, dt_norm)], n=1, cutoff=0.82)
            if m:
                bid = exact_map[(st_code, dt_norm, m[0])]

        if bid is None and pd.notna(row.lat) and pd.notna(row.lon):
            la, lo = float(row.lat), float(row.lon)
            if 6.0 <= la <= 37.5 and 68.0 <= lo <= 98.0:
                pt = Point(lo, la)
                for idx in tree.query(pt):
                    if polys[int(idx)].contains(pt):
                        bid = idx_to_block_id[int(idx)]
                        break

        station_to_block[row.well_id] = bid

    combined["block_id"] = combined["well_id"].map(station_to_block)
    matched_rows = int(combined["block_id"].notna().sum())
    match_pct = round(100.0 * matched_rows / max(len(combined), 1), 2)
    combined = combined.dropna(subset=["block_id"]).copy()

    combined["obs_date"] = np.where(
        combined["season_code"] == 0,
        combined["year"].astype(str) + "-05-01",
        combined["year"].astype(str) + "-11-01",
    )

    wl_agg = (
        combined.groupby(["block_id", "obs_date", "year", "season", "season_code"], as_index=False)
        .agg(depth_mbgl=("depth_mbgl", "median"), well_count=("well_id", "nunique"))
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
        "total_raw_well_readings_scanned": total_scanned,
        "valid_seasonal_well_readings_2013_plus": int(len(combined)),
        "block_match_rate_pct": match_pct,
        "unique_blocks_with_water_levels": int(wl_agg["block_id"].nunique()),
        "states_with_water_levels": int(wl_agg["block_id"].str.slice(0, 2).nunique()),
        "block_season_rows": int(len(wl_agg)),
        "min_obs_date": str(wl_agg["obs_date"].min()),
        "max_obs_date": str(wl_agg["obs_date"].max()),
    }
    return wl_agg, stats


def build_all_india_rainfall(blocks_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    grid_csv = RAW_LOCAL / "nasa_power_india_grid_monthly_2012_2025.csv"
    gdf = pd.read_csv(grid_csv)
    gdf["month_dt"] = pd.to_datetime(gdf["month"])
    gdf["cal_month"] = gdf["month_dt"].dt.month
    gdf["year"] = gdf["month_dt"].dt.year

    clim = (
        gdf[(gdf["year"] >= 2013) & (gdf["year"] <= 2024)]
        .groupby(["grid_id", "cal_month"], as_index=False)["rainfall_mm"]
        .mean()
        .rename(columns={"rainfall_mm": "normal_rainfall_mm"})
    )
    clim["normal_rainfall_mm"] = clim["normal_rainfall_mm"].round(2)
    gdf = gdf.merge(clim, on=["grid_id", "cal_month"], how="left")
    gdf["departure_from_normal_pct"] = np.where(
        gdf["normal_rainfall_mm"] > 1.0,
        ((gdf["rainfall_mm"] - gdf["normal_rainfall_mm"]) / gdf["normal_rainfall_mm"]) * 100.0,
        0.0,
    ).round(2)

    # Snap every block to nearest available NASA POWER grid cell
    cells = gdf[["grid_id", "grid_lat", "grid_lon"]].drop_duplicates().reset_index(drop=True)
    cell_lats = cells["grid_lat"].to_numpy()
    cell_lons = cells["grid_lon"].to_numpy()
    cell_ids = cells["grid_id"].tolist()

    blk_grid_ids: list[str] = []
    for r in blocks_df.itertuples(index=False):
        d2 = (cell_lats - float(r.lat)) ** 2 + (cell_lons - float(r.lon)) ** 2
        blk_grid_ids.append(cell_ids[int(np.argmin(d2))])

    blk_map = pd.DataFrame({"block_id": blocks_df["block_id"], "grid_id": blk_grid_ids})
    expanded = blk_map.merge(
        gdf[["grid_id", "month_dt", "rainfall_mm", "normal_rainfall_mm", "departure_from_normal_pct"]],
        on="grid_id",
        how="inner",
    )
    expanded["month"] = expanded["month_dt"].dt.date
    expanded["rainfall_source_level"] = "nasa_power_gridded"
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
        "grid_cells_covered": int(len(cells)),
        "blocks_mapped": int(expanded["block_id"].nunique()),
        "block_month_rows": int(len(expanded)),
        "min_month": str(expanded["month"].min()),
        "max_month": str(expanded["month"].max()),
    }
    return expanded, stats


def main() -> None:
    aliases = _load_aliases()
    blocks_df, polys, st_geo_kb = build_all_india_blocks_and_geojsons(aliases)
    wl_df, wl_stats = build_all_india_water_levels(blocks_df, polys, aliases, min_year=2013)
    rain_df, rain_stats = build_all_india_rainfall(blocks_df)

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

    assert blocks_clean["block_id"].is_unique, "Duplicate block_id!"
    assert not wl_df.duplicated(subset=["block_id", "obs_date"]).any(), "Duplicate water_level keys!"
    assert not rain_df.duplicated(subset=["block_id", "month"]).any(), "Duplicate rainfall keys!"

    for sub in ("block", "water_level", "rainfall_monthly"):
        (PROCESSED_LOCAL / "raw" / sub).mkdir(parents=True, exist_ok=True)

    blocks_clean.to_parquet(PROCESSED_LOCAL / "raw" / "block" / "blocks.parquet", index=False)
    wl_df.to_parquet(PROCESSED_LOCAL / "raw" / "water_level" / "water_level.parquet", index=False)
    rain_df.to_parquet(PROCESSED_LOCAL / "raw" / "rainfall_monthly" / "rainfall_monthly.parquet", index=False)

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    blocks_clean.head(50).to_csv(SAMPLE_DIR / "blocks_sample.csv", index=False)
    wl_df.head(50).to_csv(SAMPLE_DIR / "water_level_sample.csv", index=False)
    rain_df.head(50).to_csv(SAMPLE_DIR / "rainfall_monthly_sample.csv", index=False)

    report = {
        "scope": "All-India (Pan-India Sub-Districts / Blocks)",
        "total_states_and_uts": int(blocks_clean["state_code"].nunique()),
        "total_districts": int(blocks_clean[["state_code", "district"]].drop_duplicates().shape[0]),
        "total_canonical_blocks": int(len(blocks_clean)),
        "india_states_geojson_kb": round((FRONTEND_GEO_DIR / "INDIA_states.geojson").stat().st_size / 1024.0, 1),
        "per_state_geojson_avg_kb": round(float(np.mean(list(st_geo_kb.values()))), 1),
        "water_level": wl_stats,
        "rainfall_monthly": rain_stats,
    }
    (PROCESSED_LOCAL / "cleaning_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
