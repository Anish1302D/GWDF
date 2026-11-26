-- WellCast: Raw Table Definitions for Amazon Athena (Database: wellcast)
-- Backup manual DDL accompanying AWS Glue Crawler over s3://${DATA_BUCKET}/raw/

CREATE DATABASE IF NOT EXISTS wellcast;

CREATE EXTERNAL TABLE IF NOT EXISTS wellcast.block (
  block_id              STRING,
  state_code            STRING,
  state                 STRING,
  district              STRING,
  block_name            STRING,
  extraction_stage      STRING,
  extraction_stage_code INT,
  lat                   DOUBLE,
  lon                   DOUBLE,
  granularity           STRING
)
STORED AS PARQUET
LOCATION 's3://${DATA_BUCKET}/raw/block/';

CREATE EXTERNAL TABLE IF NOT EXISTS wellcast.rainfall_monthly (
  block_id                  STRING,
  month                     DATE,
  rainfall_mm               DOUBLE,
  normal_rainfall_mm        DOUBLE,
  departure_from_normal_pct DOUBLE,
  rainfall_source_level     STRING,
  is_imputed                BOOLEAN
)
STORED AS PARQUET
LOCATION 's3://${DATA_BUCKET}/raw/rainfall_monthly/';

CREATE EXTERNAL TABLE IF NOT EXISTS wellcast.water_level (
  block_id    STRING,
  obs_date    DATE,
  year        INT,
  season      STRING,
  season_code INT,
  depth_mbgl  DOUBLE,
  well_count  INT,
  is_imputed  BOOLEAN
)
STORED AS PARQUET
LOCATION 's3://${DATA_BUCKET}/raw/water_level/';
