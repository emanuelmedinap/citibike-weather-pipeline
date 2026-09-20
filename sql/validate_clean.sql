WITH parsed AS (
  SELECT 'legacy' AS era,
    starttime AS raw_start, stoptime AS raw_stop,
    COALESCE(SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%S',   starttime),
             SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%E*S', starttime),
             SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M:%S',   starttime),
             SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M',      starttime)) AS st,
    COALESCE(SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%S',   stoptime),
             SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%E*S', stoptime),
             SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M:%S',   stoptime),
             SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M',      stoptime)) AS en,
    SAFE_CAST(tripduration AS INT64) AS dur,
    CASE LOWER(TRIM(usertype)) WHEN 'subscriber' THEN 'member'
                               WHEN 'customer'   THEN 'casual' ELSE NULL END AS mc
  FROM `YOUR_GCP_PROJECT.citibike_raw.trips_legacy`
  UNION ALL
  SELECT 'new' AS era,
    started_at AS raw_start, ended_at AS raw_stop,
    COALESCE(SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%S',   started_at),
             SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%E*S', started_at)) AS st,
    COALESCE(SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%S',   ended_at),
             SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%E*S', ended_at)) AS en,
    CAST(NULL AS INT64) AS dur,
    LOWER(TRIM(member_casual)) AS mc
  FROM `YOUR_GCP_PROJECT.citibike_raw.trips_new`
)
SELECT era, COUNT(*) AS total,
  COUNTIF(st IS NULL AND TRIM(IFNULL(raw_start,'')) != '') AS start_parse_fail,
  COUNTIF(en IS NULL AND TRIM(IFNULL(raw_stop, '')) != '') AS end_parse_fail,
  COUNTIF(mc IS NULL) AS member_casual_null,
  ROUND(100*COUNTIF(mc IS NULL)/COUNT(*),4) AS mc_null_pct,
  COUNTIF(COALESCE(dur, DATETIME_DIFF(en, st, SECOND)) < 0) AS dur_negative,
  COUNTIF(COALESCE(dur, DATETIME_DIFF(en, st, SECOND)) > 86400) AS dur_over_24h
FROM parsed GROUP BY era ORDER BY era;
