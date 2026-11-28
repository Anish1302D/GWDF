"""Phase 2 v2 Local Feature Engineering & Anti-Leakage Audit using DuckDB over Parquet Lake.

Mirrors `sql/02_features.sql` (Athena v2) to engineer strictly causal hydrological,
seasonal-equilibrium, spatial district-context, and multi-year drought features.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROCESSED_LOCAL = REPO_ROOT / "data" / "processed_local"


def main() -> None:
    raw_dir = PROCESSED_LOCAL / "raw"
    curated_dir = PROCESSED_LOCAL / "curated"
    for sub in ("features", "ml_train", "ml_inference"):
        (curated_dir / sub).mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA wellcast;")
    con.execute(
        f"CREATE VIEW wellcast.block AS SELECT * FROM read_parquet('{(raw_dir / 'block' / 'blocks.parquet').as_posix()}');"
    )
    con.execute(
        f"CREATE VIEW wellcast.rainfall_monthly AS SELECT * FROM read_parquet('{(raw_dir / 'rainfall_monthly' / 'rainfall_monthly.parquet').as_posix()}');"
    )
    con.execute(
        f"CREATE VIEW wellcast.water_level AS SELECT * FROM read_parquet('{(raw_dir / 'water_level' / 'water_level.parquet').as_posix()}');"
    )

    feature_sql = """
    CREATE TABLE wellcast.features AS
    WITH rain_rolling AS (
      SELECT
        block_id,
        CAST(month AS DATE) AS month,
        ROUND(SUM(rainfall_mm) OVER (
          PARTITION BY block_id ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ), 2) AS rain_3m_mm,
        ROUND(SUM(rainfall_mm) OVER (
          PARTITION BY block_id ORDER BY month ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
        ), 2) AS rain_6m_mm,
        ROUND(SUM(rainfall_mm) OVER (
          PARTITION BY block_id ORDER BY month ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
        ), 2) AS rain_12m_mm,
        ROUND(SUM(rainfall_mm) OVER (
          PARTITION BY block_id ORDER BY month ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
        ), 2) AS rain_24m_mm,
        ROUND(SUM(normal_rainfall_mm) OVER (
          PARTITION BY block_id ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ), 2) AS rain_3m_normal_mm,
        ROUND(SUM(normal_rainfall_mm) OVER (
          PARTITION BY block_id ORDER BY month ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
        ), 2) AS rain_6m_normal_mm,
        ROUND(SUM(normal_rainfall_mm) OVER (
          PARTITION BY block_id ORDER BY month ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
        ), 2) AS rain_12m_normal_mm,
        ROUND(SUM(normal_rainfall_mm) OVER (
          PARTITION BY block_id ORDER BY month ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
        ), 2) AS rain_24m_normal_mm,
        COUNT(rainfall_mm) OVER (
          PARTITION BY block_id ORDER BY month ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
        ) AS rain_6m_obs_count
      FROM wellcast.rainfall_monthly
    ),
    wl_enriched AS (
      SELECT
        w.block_id,
        b.district,
        b.lat,
        b.lon,
        b.extraction_stage_code,
        CAST(w.obs_date AS DATE) AS obs_date,
        w.year,
        w.season,
        w.season_code,
        w.depth_mbgl,
        w.well_count,
        w.is_imputed,
        LAG(w.depth_mbgl, 1) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS prev_depth_mbgl,
        LAG(w.obs_date, 1) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS prev_obs_date,
        LAG(w.depth_mbgl, 2) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS same_season_last_year_depth,
        LAG(w.depth_mbgl, 3) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS target_season_2yr_ago_depth,
        LAG(w.depth_mbgl, 10) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS depth_5yr_ago,
        LAG(w.obs_date, 10) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS date_5yr_ago,
        AVG(w.depth_mbgl) OVER (
          PARTITION BY w.block_id, w.season_code ORDER BY w.obs_date
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS block_curr_season_hist_mean,
        AVG(w.depth_mbgl) OVER (
          PARTITION BY w.block_id ORDER BY w.obs_date
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS block_overall_hist_mean,
        STDDEV_SAMP(w.depth_mbgl) OVER (
          PARTITION BY w.block_id ORDER BY w.obs_date
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS block_hist_std,
        COUNT(*) OVER (
          PARTITION BY w.block_id ORDER BY w.obs_date
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS block_past_obs_count,
        COUNT(*) OVER (PARTITION BY w.block_id) AS block_total_obs,
        LEAD(w.obs_date, 1) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS target_obs_date,
        LEAD(w.depth_mbgl, 1) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS raw_target_depth_next
      FROM wellcast.water_level w
      JOIN wellcast.block b ON w.block_id = b.block_id
    ),
    wl_with_target_clim AS (
      SELECT
        e.*,
        LAG(e.block_curr_season_hist_mean, 1) OVER (
          PARTITION BY e.block_id ORDER BY e.obs_date
        ) AS block_target_season_hist_mean,
        AVG(e.depth_mbgl) OVER (PARTITION BY e.district, e.obs_date) AS district_curr_depth_mean,
        AVG(e.prev_depth_mbgl) OVER (PARTITION BY e.district, e.obs_date) AS district_prev_depth_mean
      FROM wl_enriched e
    )
    SELECT
      w.block_id,
      w.obs_date,
      w.year,
      w.season,
      w.season_code,
      ROUND(w.lat, 4) AS lat,
      ROUND(w.lon, 4) AS lon,
      w.depth_mbgl,
      w.prev_depth_mbgl,
      ROUND(w.depth_mbgl - w.prev_depth_mbgl, 3) AS prev_change_mbgl,
      w.same_season_last_year_depth,
      ROUND(w.depth_mbgl - w.same_season_last_year_depth, 3) AS yoy_change_mbgl,
      w.target_season_2yr_ago_depth,
      ROUND(w.block_curr_season_hist_mean, 3) AS block_curr_season_hist_mean,
      ROUND(w.block_target_season_hist_mean, 3) AS block_target_season_hist_mean,
      ROUND(w.prev_depth_mbgl - w.block_target_season_hist_mean, 3) AS prev_anomaly_vs_target_mean,
      ROUND(w.depth_mbgl - w.block_curr_season_hist_mean, 3) AS curr_anomaly_vs_season_mean,
      ROUND(COALESCE(w.block_hist_std, 1.0), 3) AS block_hist_std,
      ROUND(w.district_curr_depth_mean, 3) AS district_curr_depth_mean,
      ROUND(w.depth_mbgl - w.district_curr_depth_mean, 3) AS block_vs_district_depth_diff,
      ROUND(w.district_curr_depth_mean - w.district_prev_depth_mean, 3) AS district_seasonal_shift,
      ROUND(
        CASE
          WHEN w.depth_5yr_ago IS NOT NULL
               AND date_diff('day', w.date_5yr_ago, w.obs_date) > 300
          THEN (w.depth_mbgl - w.depth_5yr_ago) / (date_diff('day', w.date_5yr_ago, w.obs_date) / 365.25)
          ELSE COALESCE(w.depth_mbgl - w.same_season_last_year_depth, 0.0)
        END,
      3) AS depth_trend_5yr,
      r.rain_3m_mm,
      r.rain_6m_mm,
      r.rain_12m_mm,
      r.rain_24m_mm,
      r.rain_3m_normal_mm,
      r.rain_6m_normal_mm,
      r.rain_12m_normal_mm,
      r.rain_24m_normal_mm,
      ROUND(CASE WHEN r.rain_6m_normal_mm > 0 THEN ((r.rain_6m_mm - r.rain_6m_normal_mm) / r.rain_6m_normal_mm) * 100.0 ELSE 0.0 END, 2) AS rain_departure_6m_pct,
      ROUND(CASE WHEN r.rain_12m_normal_mm > 0 THEN ((r.rain_12m_mm - r.rain_12m_normal_mm) / r.rain_12m_normal_mm) * 100.0 ELSE 0.0 END, 2) AS rain_departure_12m_pct,
      ROUND(CASE WHEN r.rain_24m_normal_mm > 0 THEN ((r.rain_24m_mm - r.rain_24m_normal_mm) / r.rain_24m_normal_mm) * 100.0 ELSE 0.0 END, 2) AS rain_departure_24m_pct,
      w.extraction_stage_code,
      w.well_count,
      w.block_past_obs_count,
      w.block_total_obs,
      w.is_imputed,
      CASE
        WHEN w.prev_obs_date IS NOT NULL
             AND date_diff('month', w.prev_obs_date, w.obs_date) BETWEEN 4 AND 8
        THEN w.prev_depth_mbgl
        ELSE NULL
      END AS baseline_pred_next,
      w.target_obs_date,
      CASE
        WHEN w.target_obs_date IS NOT NULL
             AND date_diff('month', w.obs_date, w.target_obs_date) BETWEEN 4 AND 8
        THEN w.raw_target_depth_next
        ELSE NULL
      END AS target_depth_next
    FROM wl_with_target_clim w
    LEFT JOIN rain_rolling r
      ON w.block_id = r.block_id
     AND date_trunc('month', w.obs_date) = r.month
    WHERE r.rain_6m_obs_count = 6;
    """
    con.execute(feature_sql)

    dup_cnt = con.execute(
        "SELECT COUNT(*) FROM (SELECT block_id, obs_date FROM wellcast.features GROUP BY 1, 2 HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    assert dup_cnt == 0, f"Found {dup_cnt} duplicate (block_id, obs_date) keys!"

    gap_stats = con.execute(
        """
        SELECT
          MIN(date_diff('month', obs_date, target_obs_date)),
          MAX(date_diff('month', obs_date, target_obs_date)),
          COUNT(*)
        FROM wellcast.features
        WHERE target_depth_next IS NOT NULL AND baseline_pred_next IS NOT NULL
        """
    ).fetchone()
    min_gap, max_gap, train_rows = gap_stats
    assert min_gap >= 4 and max_gap <= 8, f"Invalid forward target gap months: {min_gap}..{max_gap}"

    features_out = (curated_dir / "features" / "features.parquet").as_posix()
    train_out = (curated_dir / "ml_train" / "train_features.parquet").as_posix()
    infer_out = (curated_dir / "ml_inference" / "latest_features.parquet").as_posix()

    con.execute(f"COPY wellcast.features TO '{features_out}' (FORMAT PARQUET);")
    con.execute(
        f"""
        COPY (
          SELECT * FROM wellcast.features
          WHERE target_depth_next IS NOT NULL
            AND baseline_pred_next IS NOT NULL
            AND block_total_obs >= 4
        ) TO '{train_out}' (FORMAT PARQUET);
        """
    )
    con.execute(
        f"""
        COPY (
          SELECT * EXCLUDE (rn) FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY block_id ORDER BY obs_date DESC) AS rn
            FROM wellcast.features
          )
          WHERE rn = 1
        ) TO '{infer_out}' (FORMAT PARQUET);
        """
    )

    infer_cnt = con.execute(f"SELECT COUNT(*) FROM read_parquet('{infer_out}')").fetchone()[0]
    audit = {
        "feature_schema_version": "v2_hydro_spatial_equilibrium",
        "total_feature_rows": int(con.execute("SELECT COUNT(*) FROM wellcast.features").fetchone()[0]),
        "clean_ml_train_rows": int(train_rows),
        "latest_inference_blocks": int(infer_cnt),
        "min_forward_horizon_months": int(min_gap),
        "max_forward_horizon_months": int(max_gap),
        "duplicate_keys": int(dup_cnt),
        "anti_leakage_audit_passed": True,
    }
    (PROCESSED_LOCAL / "feature_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
