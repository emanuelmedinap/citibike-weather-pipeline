-- verification.sql — reproducible reconciliation of the Citibike counts.
-- Every row's total_trips must equal 314,774,609, from three independent angles:
--   1) trips_clean  — the canonical unified view (source of truth)
--   2) daily_summary — the marts daily rollup, re-summed (proves the mart matches)
--   3) raw legacy+new — the two raw tables' row counts (metadata only, 0 bytes)
-- Within rows 1-2, nyc+jc and member+casual+unknown must each also sum to the total.
-- (For parse-coverage checks, see sql/validate_clean.sql.)

WITH clean AS (
  SELECT
    'trips_clean (canonical view)'      AS source,
    COUNT(*)                             AS total_trips,
    COUNTIF(system = 'NYC')              AS nyc,
    COUNTIF(system = 'JC')               AS jc,
    COUNTIF(member_casual = 'member')    AS member,
    COUNTIF(member_casual = 'casual')    AS casual,
    COUNTIF(member_casual IS NULL)       AS unknown
  FROM `YOUR_GCP_PROJECT.citibike_raw.trips_clean`
),
mart AS (
  SELECT
    'daily_summary (mart re-sum)'        AS source,
    SUM(trips)                           AS total_trips,
    SUM(IF(system = 'NYC', trips, 0))    AS nyc,
    SUM(IF(system = 'JC',  trips, 0))    AS jc,
    SUM(member_trips)                    AS member,
    SUM(casual_trips)                    AS casual,
    SUM(unknown_member_trips)            AS unknown
  FROM `YOUR_GCP_PROJECT.citibike_marts.daily_summary`
),
raw AS (
  SELECT
    'raw legacy+new (row counts)'        AS source,
    (SELECT COUNT(*) FROM `YOUR_GCP_PROJECT.citibike_raw.trips_legacy`)
      + (SELECT COUNT(*) FROM `YOUR_GCP_PROJECT.citibike_raw.trips_new`) AS total_trips,
    CAST(NULL AS INT64) AS nyc, CAST(NULL AS INT64) AS jc,
    CAST(NULL AS INT64) AS member, CAST(NULL AS INT64) AS casual,
    CAST(NULL AS INT64) AS unknown
)
SELECT *, (total_trips = 314774609) AS matches_expected FROM clean
UNION ALL SELECT *, (total_trips = 314774609) FROM mart
UNION ALL SELECT *, (total_trips = 314774609) FROM raw
ORDER BY source;
