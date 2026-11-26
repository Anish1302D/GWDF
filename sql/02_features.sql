-- WellCast: Zero-Leakage Feature Engineering CTAS (Amazon Athena / Trino SQL)
-- Produces one row per (block_id, obs_date) with strictly historical features (<= obs_date)
-- and next-season target depth (LEAD by 1 semi-annual observation).

DROP TABLE IF EXISTS wellcast.features;

CREATE TABLE wellcast.features
WITH (
  format = 'PARQUET',
  parquet_compression = 'SNAPPY',
  external_location = 's3://${DATA_BUCKET}/curated/features/'
) AS
WITH rain_rolling AS (
  SELECT
    block_id,
    month,
    SUM(rainfall_mm) OVER (
      PARTITION BY block_id ORDER BY month
      ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rain_3m_mm,
    SUM(rainfall_mm) OVER (
      PARTITION BY block_id ORDER BY month
      ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
    ) AS rain_6m_mm,
    SUM(rainfall_mm) OVER (
      PARTITION BY block_id ORDER BY month
      ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
    ) AS rain_12m_mm,
    SUM(normal_rainfall_mm) OVER (
      PARTITION BY block_id ORDER BY month
      ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rain_3m_normal_mm,
    SUM(normal_rainfall_mm) OVER (
      PARTITION BY block_id ORDER BY month
      ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
    ) AS rain_6m_normal_mm,
    SUM(normal_rainfall_mm) OVER (
      PARTITION BY block_id ORDER BY month
      ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
    ) AS rain_12m_normal_mm,
    COUNT(rainfall_mm) OVER (
      PARTITION BY block_id ORDER BY month
      ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
    ) AS rain_6m_obs_count
  FROM wellcast.rainfall_monthly
),
wl_lags AS (
  SELECT
    w.block_id,
    w.obs_date,
    w.year,
    w.season,
    w.season_code,
    w.depth_mbgl,
    w.well_count,
    w.is_imputed,
    LAG(w.depth_mbgl, 1) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS prev_depth_mbgl,
    LAG(w.depth_mbgl, 2) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS same_season_last_year_depth,
    LAG(w.depth_mbgl, 10) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS depth_5yr_ago,
    LAG(w.obs_date, 10) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS date_5yr_ago,
    LEAD(w.obs_date, 1) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS target_obs_date,
    LEAD(w.depth_mbgl, 1) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS target_depth_next
  FROM wellcast.water_level w
)
SELECT
  w.block_id,
  w.obs_date,
  w.year,
  w.season,
  w.season_code,
  w.depth_mbgl,
  w.prev_depth_mbgl,
  w.depth_mbgl - w.prev_depth_mbgl AS prev_change_mbgl,
  w.same_season_last_year_depth,
  w.depth_mbgl - w.same_season_last_year_depth AS yoy_change_mbgl,
  CASE
    WHEN w.depth_5yr_ago IS NOT NULL
         AND date_diff('day', w.date_5yr_ago, w.obs_date) > 300
    THEN (w.depth_mbgl - w.depth_5yr_ago) / (date_diff('day', w.date_5yr_ago, w.obs_date) / 365.25)
    ELSE COALESCE(w.depth_mbgl - w.same_season_last_year_depth, 0.0)
  END AS depth_trend_5yr,
  r.rain_3m_mm,
  r.rain_6m_mm,
  r.rain_12m_mm,
  r.rain_3m_normal_mm,
  r.rain_6m_normal_mm,
  r.rain_12m_normal_mm,
  CASE
    WHEN r.rain_6m_normal_mm > 0
    THEN ((r.rain_6m_mm - r.rain_6m_normal_mm) / r.rain_6m_normal_mm) * 100.0
    ELSE 0.0
  END AS rain_departure_6m_pct,
  b.extraction_stage_code,
  w.well_count,
  w.is_imputed,
  w.prev_depth_mbgl AS baseline_pred_next,
  w.target_obs_date,
  CASE
    WHEN w.target_obs_date IS NOT NULL
         AND date_diff('month', w.obs_date, w.target_obs_date) BETWEEN 4 AND 8
    THEN w.target_depth_next
    ELSE NULL
  END AS target_depth_next
FROM wl_lags w
JOIN wellcast.block b
  ON w.block_id = b.block_id
LEFT JOIN rain_rolling r
  ON w.block_id = r.block_id
 AND date_trunc('month', w.obs_date) = r.month
WHERE r.rain_6m_obs_count = 6;
