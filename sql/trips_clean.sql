-- citibike_raw.trips_clean  —  unified, typed view over the two raw tables.
-- Canonical = the new 13-col schema (see DECISIONS.md, "Two raw tables"). Unification happens
-- HERE, not on load. All source columns are raw STRING; this view types them,
-- maps legacy -> canonical, and surfaces provenance. DRAFT — validate parsing
-- (esp. legacy timestamp formats) before trusting; see sql/validate_clean.sql.
--
-- Timestamps are emitted as DATETIME = naive America/New_York wall-clock, exactly
-- as published (decision #10). Add a UTC TIMESTAMP later if a consumer needs it.

CREATE OR REPLACE VIEW `YOUR_GCP_PROJECT.citibike_raw.trips_clean` AS
WITH legacy AS (
  SELECT
    -- legacy has no ride_id -> synthesize a stable surrogate (decision #5).
    CONCAT('leg_', TO_HEX(MD5(CONCAT(
      IFNULL(starttime,''), '|', IFNULL(stoptime,''), '|', IFNULL(bikeid,''), '|',
      IFNULL(start_station_id,''), '|', IFNULL(end_station_id,''), '|', source_file
    )))) AS ride_id,
    CAST(NULL AS STRING) AS rideable_type,                       -- didn't exist pre-2020
    COALESCE(
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%S',   starttime),
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%E*S', starttime),   -- fractional secs (2018-2019)
      SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M:%S',   starttime),
      SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M',      starttime)
    ) AS started_at,
    COALESCE(
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%S',   stoptime),
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%E*S', stoptime),
      SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M:%S',   stoptime),
      SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M',      stoptime)
    ) AS ended_at,
    SAFE_CAST(tripduration AS INT64) AS trip_duration_s,         -- legacy: provided (seconds)
    NULLIF(TRIM(start_station_id),   '') AS start_station_id,    -- station_id as STRING (decision #9)
    NULLIF(TRIM(start_station_name), '') AS start_station_name,
    NULLIF(TRIM(end_station_id),     '') AS end_station_id,
    NULLIF(TRIM(end_station_name),   '') AS end_station_name,
    SAFE_CAST(start_station_latitude  AS FLOAT64) AS start_lat,
    SAFE_CAST(start_station_longitude AS FLOAT64) AS start_lng,
    SAFE_CAST(end_station_latitude    AS FLOAT64) AS end_lat,
    SAFE_CAST(end_station_longitude   AS FLOAT64) AS end_lng,
    CASE LOWER(TRIM(usertype))                                   -- usertype -> member_casual (#4)
      WHEN 'subscriber' THEN 'member'
      WHEN 'customer'   THEN 'casual'
      ELSE NULL END AS member_casual,
    SAFE_CAST(NULLIF(birth_year, '\\N') AS INT64) AS birth_year, -- legacy-only (#4)
    CASE TRIM(gender)                                            -- 0/1/2 -> label
      WHEN '1' THEN 'male' WHEN '2' THEN 'female' WHEN '0' THEN 'unknown'
      ELSE NULL END AS gender,
    system,
    'legacy' AS schema_era,
    source_file
  FROM `YOUR_GCP_PROJECT.citibike_raw.trips_legacy`
),
new_rows AS (
  SELECT
    * EXCEPT(started_at, ended_at),
    started_at, ended_at,
    DATETIME_DIFF(ended_at, started_at, SECOND) AS trip_duration_s   -- new: derived (#6)
  FROM (
    SELECT
      ride_id,
      NULLIF(TRIM(rideable_type), '') AS rideable_type,
      COALESCE(
        SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%S',    started_at),
        SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%E*S',  started_at)     -- tolerate fractional secs
      ) AS started_at,
      COALESCE(
        SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%S',    ended_at),
        SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%E*S',  ended_at)
      ) AS ended_at,
      NULLIF(TRIM(start_station_id),   '') AS start_station_id,
      NULLIF(TRIM(start_station_name), '') AS start_station_name,
      NULLIF(TRIM(end_station_id),     '') AS end_station_id,
      NULLIF(TRIM(end_station_name),   '') AS end_station_name,
      SAFE_CAST(start_lat AS FLOAT64) AS start_lat,
      SAFE_CAST(start_lng AS FLOAT64) AS start_lng,
      SAFE_CAST(end_lat   AS FLOAT64) AS end_lat,
      SAFE_CAST(end_lng   AS FLOAT64) AS end_lng,
      LOWER(TRIM(member_casual)) AS member_casual,
      CAST(NULL AS INT64)  AS birth_year,                          -- absent in new schema (#4)
      CAST(NULL AS STRING) AS gender,
      system,
      'new' AS schema_era,
      source_file
    FROM `YOUR_GCP_PROJECT.citibike_raw.trips_new`
  )
)
SELECT ride_id, rideable_type, started_at, ended_at, trip_duration_s,
       start_station_id, start_station_name, end_station_id, end_station_name,
       start_lat, start_lng, end_lat, end_lng, member_casual,
       birth_year, gender, system, schema_era, source_file
FROM legacy
UNION ALL
SELECT ride_id, rideable_type, started_at, ended_at, trip_duration_s,
       start_station_id, start_station_name, end_station_id, end_station_name,
       start_lat, start_lng, end_lat, end_lng, member_casual,
       birth_year, gender, system, schema_era, source_file
FROM new_rows;
