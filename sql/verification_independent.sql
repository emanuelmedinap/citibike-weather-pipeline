-- verification_independent.sql — independent verification (audit gap 6).
--   PART 1: per-month completeness of our daily_summary — flags any MISSING month.
--   PART 2: yearly trip counts cross-checked against the independent external
--           source of truth, nyu-datasets.citibike.m_trips_unified (~319M rows,
--           both regions). A DOUBLE-COUNTED month/year would inflate our year vs
--           theirs (the former 2013/2018 double-count showed ~2x; now reconciled).
-- Both queries stay well under the 200 GB cap (~2.6 GB scan for PART 2).
-- Note: `theirs` groups on start_time as stored; small year-boundary/snapshot
-- differences vs our NY-local trip_date are expected — this is a sanity
-- cross-check, not an exact reconciliation.

-- ===== PART 1: per-month completeness (no month missing) =====
WITH expected AS (
  SELECT DATE_TRUNC(d, MONTH) AS mo
  FROM UNNEST(GENERATE_DATE_ARRAY(DATE '2013-06-01', DATE '2026-05-01',
                                  INTERVAL 1 MONTH)) AS d
),
actual AS (
  SELECT DATE_TRUNC(trip_date, MONTH) AS mo, SUM(trips) AS trips
  FROM `YOUR_GCP_PROJECT.citibike_marts.daily_summary`
  GROUP BY mo
)
SELECT
  COUNT(*)                                  AS expected_months,
  COUNTIF(a.mo IS NOT NULL)                 AS present_months,
  COUNTIF(a.mo IS NULL)                     AS missing_months,
  STRING_AGG(IF(a.mo IS NULL, FORMAT_DATE('%Y-%m', e.mo), NULL),
             ', ' ORDER BY e.mo)            AS missing_list
FROM expected e LEFT JOIN actual a USING (mo);

-- ===== PART 2: yearly cross-check vs independent source =====
WITH ours AS (
  SELECT EXTRACT(YEAR FROM trip_date) AS yr, SUM(trips) AS ours_trips
  FROM `YOUR_GCP_PROJECT.citibike_marts.daily_summary` GROUP BY yr
),
theirs AS (
  SELECT EXTRACT(YEAR FROM start_time) AS yr, COUNT(*) AS their_trips
  FROM `nyu-datasets.citibike.m_trips_unified` GROUP BY yr
)
SELECT COALESCE(o.yr, t.yr) AS yr, o.ours_trips, t.their_trips,
       o.ours_trips - t.their_trips AS diff,
       ROUND(100 * SAFE_DIVIDE(o.ours_trips - t.their_trips, t.their_trips), 2) AS pct_diff
FROM ours o FULL OUTER JOIN theirs t USING (yr)
ORDER BY yr;
