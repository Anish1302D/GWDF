-- WellCast: Athena Serving Table & Planner Views (QuickSight & Verification)

CREATE EXTERNAL TABLE IF NOT EXISTS wellcast.forecasts (
  block_id                  STRING,
  state                     STRING,
  district                  STRING,
  block_name                STRING,
  scenario                  STRING,
  rainfall_pct_of_normal    INT,
  forecast_season           STRING,
  current_depth_mbgl        DOUBLE,
  predicted_depth_mbgl      DOUBLE,
  lower_bound               DOUBLE,
  upper_bound               DOUBLE,
  predicted_yoy_change_mbgl DOUBLE,
  risk_class                STRING,
  risk_score                DOUBLE,
  model_version             STRING,
  generated_at              TIMESTAMP
)
STORED AS PARQUET
LOCATION 's3://${DATA_BUCKET}/forecasts/';

CREATE OR REPLACE VIEW wellcast.v_top_at_risk_normal AS
SELECT
  f.block_id,
  f.state,
  f.district,
  f.block_name,
  b.extraction_stage,
  f.forecast_season,
  f.current_depth_mbgl,
  f.predicted_depth_mbgl,
  f.lower_bound,
  f.upper_bound,
  f.predicted_yoy_change_mbgl,
  f.risk_class,
  f.risk_score
FROM wellcast.forecasts f
JOIN wellcast.block b ON f.block_id = b.block_id
WHERE f.scenario = 'normal'
  AND f.risk_class <> 'Insufficient Data'
ORDER BY f.risk_score DESC;

CREATE OR REPLACE VIEW wellcast.v_district_risk_summary AS
SELECT
  state,
  district,
  scenario,
  COUNT(*) AS total_blocks,
  SUM(CASE WHEN risk_class = 'Critical' THEN 1 ELSE 0 END) AS critical_blocks,
  SUM(CASE WHEN risk_class = 'Watch' THEN 1 ELSE 0 END) AS watch_blocks,
  SUM(CASE WHEN risk_class = 'Safe' THEN 1 ELSE 0 END) AS safe_blocks,
  ROUND(AVG(predicted_depth_mbgl), 2) AS avg_predicted_depth_mbgl
FROM wellcast.forecasts
GROUP BY state, district, scenario;
