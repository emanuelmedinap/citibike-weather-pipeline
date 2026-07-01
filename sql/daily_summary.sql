-- citibike_marts.daily_summary — reporting-layer daily rollup of trips_clean,
-- one row per trip_date x system. Small (~9,500 rows); the dashboard hits this
-- and it joins to daily NYC weather on trip_date. Rebuild to refresh.
--
-- avg/median are computed over a bounded "typical ride" window
-- (0 < trip_duration_s <= 86400 s); `duration_outliers` counts everything
-- excluded (NULL, <=0, or >24h) so nothing is hidden. `trips` is the full count.

CREATE OR REPLACE TABLE `msbai-dwd-em5844.citibike_marts.daily_summary` AS
SELECT
  DATE(started_at) AS trip_date,
  system,
  COUNT(*) AS trips,
  ROUND(AVG(IF(trip_duration_s > 0 AND trip_duration_s <= 86400,
              trip_duration_s, NULL)), 1) AS avg_duration_s,
  APPROX_QUANTILES(IF(trip_duration_s > 0 AND trip_duration_s <= 86400,
                      trip_duration_s, NULL), 2 IGNORE NULLS)[OFFSET(1)] AS median_duration_s,
  COUNTIF(member_casual = 'member') AS member_trips,
  COUNTIF(member_casual = 'casual') AS casual_trips,
  COUNTIF(member_casual IS NULL)    AS unknown_member_trips,
  COUNT(DISTINCT start_station_id)  AS distinct_start_stations,
  COUNTIF(trip_duration_s IS NULL OR trip_duration_s <= 0
          OR trip_duration_s > 86400) AS duration_outliers
FROM `msbai-dwd-em5844.citibike_raw.trips_clean`
GROUP BY trip_date, system;
