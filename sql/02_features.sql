-- WellCast v2: Zero-Leakage Hydrological, Spatial & Multi-Year Drought Feature Engineering CTAS
-- Produces one row per (block_id, obs_date) using ONLY information observed at or before obs_date (<= t),
-- plus strictly forward 6-month target_depth_next (t+1) for supervised training.

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
      PARTITION BY block_id ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rain_3m_mm,
    SUM(rainfall_mm) OVER (
      PARTITION BY block_id ORDER BY month ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
    ) AS rain_6m_mm,
    SUM(rainfall_mm) OVER (
      PARTITION BY block_id ORDER BY month ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
    ) AS rain_12m_mm,
    SUM(rainfall_mm) OVER (
      PARTITION BY block_id ORDER BY month ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
    ) AS rain_24m_mm,
    SUM(normal_rainfall_mm) OVER (
      PARTITION BY block_id ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rain_3m_normal_mm,
    SUM(normal_rainfall_mm) OVER (
      PARTITION BY block_id ORDER BY month ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
    ) AS rain_6m_normal_mm,
    SUM(normal_rainfall_mm) OVER (
      PARTITION BY block_id ORDER BY month ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
    ) AS rain_12m_normal_mm,
    SUM(normal_rainfall_mm) OVER (
      PARTITION BY block_id ORDER BY month ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
    ) AS rain_24m_normal_mm,
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
    w.obs_date,
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
    -- Strictly causal expanding mean for the CURRENT season (<= t)
    AVG(w.depth_mbgl) OVER (
      PARTITION BY w.block_id, w.season_code ORDER BY w.obs_date
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS block_curr_season_hist_mean,
    -- Strictly causal expanding mean across ALL past observations of this block (<= t)
    AVG(w.depth_mbgl) OVER (
      PARTITION BY w.block_id ORDER BY w.obs_date
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS block_overall_hist_mean,
    STDDEV_SAMP(w.depth_mbgl) OVER (
      PARTITION BY w.block_id ORDER BY w.obs_date
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS block_hist_std,
    LEAD(w.obs_date, 1) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS target_obs_date,
    LEAD(w.depth_mbgl, 1) OVER (PARTITION BY w.block_id ORDER BY w.obs_date) AS raw_target_depth_next
  FROM wellcast.water_level w
  JOIN wellcast.block b ON w.block_id = b.block_id
),
wl_with_target_clim AS (
  SELECT
    e.*,
    -- Strictly causal expanding mean for the OPPOSITE (upcoming target) season:
    -- Since rows alternate seasons, LAG of block_curr_season_hist_mean by 1 step is the exact
    -- expanding historical mean of the target season up to t-1!
    LAG(e.block_curr_season_hist_mean, 1) OVER (
      PARTITION BY e.block_id ORDER BY e.obs_date
    ) AS block_target_season_hist_mean,
    -- Concurrent district-level aquifer summary at exact same obs_date t (0 future leakage!)
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
  w.lat,
  w.lon,
  w.depth_mbgl,
  w.prev_depth_mbgl,
  w.depth_mbgl - w.prev_depth_mbgl AS prev_change_mbgl,
  w.same_season_last_year_depth,
  w.depth_mbgl - w.same_season_last_year_depth AS yoy_change_mbgl,
  w.target_season_2yr_ago_depth,
  w.block_curr_season_hist_mean,
  w.block_target_season_hist_mean,
  w.prev_depth_mbgl - w.block_target_season_hist_mean AS prev_anomaly_vs_target_mean,
  w.depth_mbgl - w.block_curr_season_hist_mean AS curr_anomaly_vs_season_mean,
  COALESCE(w.block_hist_std, 1.0) AS block_hist_std,
  w.district_curr_depth_mean,
  w.depth_mbgl - w.district_curr_depth_mean AS block_vs_district_depth_diff,
  w.district_curr_depth_mean - w.district_prev_depth_mean AS district_seasonal_shift,
  CASE
    WHEN w.depth_5yr_ago IS NOT NULL
         AND date_diff('day', w.date_5yr_ago, w.obs_date) > 300
    THEN (w.depth_mbgl - w.depth_5yr_ago) / (date_diff('day', w.date_5yr_ago, w.obs_date) / 365.25)
    ELSE COALESCE(w.depth_mbgl - w.same_season_last_year_depth, 0.0)
  END AS depth_trend_5yr,
  r.rain_3m_mm,
  r.rain_6m_mm,
  r.rain_12m_mm,
  r.rain_24m_mm,
  r.rain_3m_normal_mm,
  r.rain_6m_normal_mm,
  r.rain_12m_normal_mm,
  r.rain_24m_normal_mm,
  CASE WHEN r.rain_6m_normal_mm > 0 THEN ((r.rain_6m_mm - r.rain_6m_normal_mm) / r.rain_6m_normal_mm) * 100.0 ELSE 0.0 END AS rain_departure_6m_pct,
  CASE WHEN r.rain_12m_normal_mm > 0 THEN ((r.rain_12m_mm - r.rain_12m_normal_mm) / r.rain_12m_normal_mm) * 100.0 ELSE 0.0 END AS rain_departure_12m_pct,
  CASE WHEN r.rain_24m_normal_mm > 0 THEN ((r.rain_24m_mm - r.rain_24m_normal_mm) / r.rain_24m_normal_mm) * 100.0 ELSE 0.0 END AS rain_departure_24m_pct,
  w.extraction_stage_code,
  w.well_count,
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
