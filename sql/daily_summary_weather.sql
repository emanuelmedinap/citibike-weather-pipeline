-- citibike_marts.daily_summary_weather — the single object the dashboard hits.
-- All daily_summary rows (both systems) LEFT JOINed to Central Park weather.
-- The system='NYC' predicate is in the JOIN's ON clause (not WHERE) on purpose:
-- every daily_summary row is kept, but only NYC rows match a weather row. JC rows
-- get NULL weather by design — Central Park does not represent Jersey City.
-- Dashboard filters by `system`.

CREATE OR REPLACE VIEW `YOUR_GCP_PROJECT.citibike_marts.daily_summary_weather` AS
SELECT
  d.trip_date,
  d.system,
  d.trips,
  d.avg_duration_s,
  d.median_duration_s,
  d.member_trips,
  d.casual_trips,
  d.unknown_member_trips,
  d.distinct_start_stations,
  d.duration_outliers,
  w.tmax_c,
  w.tmin_c,
  w.tmax_f,
  w.tmin_f,
  w.prcp_mm,
  w.snow_mm
FROM `YOUR_GCP_PROJECT.citibike_marts.daily_summary` d
LEFT JOIN `YOUR_GCP_PROJECT.citibike_marts.weather` w
  ON d.system = 'NYC' AND w.date = d.trip_date;
