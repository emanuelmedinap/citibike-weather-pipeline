-- citibike_marts.weather — daily Central Park (GHCN station USW00094728) weather,
-- one row per date, for joining to daily_summary on trip_date (NYC rows).
-- GHCN long->wide pivot with unit conversion:
--   TMAX/TMIN: tenths degC -> degC (and degF); PRCP: tenths mm -> mm;
--   SNOW: already whole mm (NOT tenths). qflag blank => passed NOAA QC.
-- Rebuild to refresh (adds new dates as public GHCN tables update).

CREATE OR REPLACE TABLE `YOUR_GCP_PROJECT.citibike_marts.weather` AS
WITH daily AS (
  SELECT
    date,
    MAX(IF(element = 'TMAX', value, NULL)) / 10.0 AS tmax_c,
    MAX(IF(element = 'TMIN', value, NULL)) / 10.0 AS tmin_c,
    MAX(IF(element = 'PRCP', value, NULL)) / 10.0 AS prcp_mm,
    MAX(IF(element = 'SNOW', value, NULL))        AS snow_mm
  FROM `bigquery-public-data.ghcn_d.ghcnd_*`
  WHERE _TABLE_SUFFIX BETWEEN '2013' AND '2026'
    AND id = 'USW00094728'
    AND element IN ('TMAX','TMIN','PRCP','SNOW')
    AND (qflag IS NULL OR qflag = '')
  GROUP BY date
)
SELECT
  date,
  tmax_c,
  tmin_c,
  ROUND(tmax_c * 9 / 5 + 32, 1) AS tmax_f,
  ROUND(tmin_c * 9 / 5 + 32, 1) AS tmin_f,
  prcp_mm,
  snow_mm
FROM daily;
