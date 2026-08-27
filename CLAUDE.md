# CLAUDE.md — Citibike Trip Archive

Working notes for ingesting the public Citibike trip archive.

**Source bucket:** `https://s3.amazonaws.com/tripdata/` (public, unauthenticated, single
non-truncated listing of ~160 data files + `index.html`).

> Status: the **Confirmed facts** below were verified firsthand by reading only the
> header row of representative files via HTTP Range requests (no full archive downloaded).
> The **Confirmed decisions** below have been reviewed and approved.

## STANDING ORDER, 2026-08-27. No unrequested files.

**NO AGENT CREATES OR GENERATES ANY FILE, ARTIFACT, DOCUMENT, EXPORT OR DOWNLOAD UNLESS EMANUEL EXPLICITLY ASKS FOR IT.**

Answer in the thread. If you believe a file would help, **say so in one line and wait.** Do not produce it and then offer it. Producing it first is the violation, whether or not he keeps it.

This is a **standing order, not a preference**, and it does not get softened, reinterpreted as a default, or treated as advice about tidiness. Three reasons, so no future session argues with it:

1. **Unrequested files become his filing work.** Every one he did not ask for is a decision he now has to make and a place he now has to put it.
2. **They break the architecture rule.** Memory in GitHub, documents in Drive, nothing generated sideways into either.
3. **They spend tokens he is watching.**

Scope: every agent, every repo, every session. It covers documents, exports, decks, spreadsheets, diagrams, reports, scripts written to disk as deliverables, and anything staged in `~/Downloads`. It does not cover the memory `.md` files an agent maintains as part of its own record, or work he has already asked for in the same thread.

When in doubt: **ask in one line, then wait.**

Canonical source is Meta (`2_strategic_agent_personality/OPERATING_NORM.md`). This repo has no `OPERATING_NORM.md`, so the rule is carried here. Do not edit it locally.

---

## ⛔ Hard cost rule — 200 GB query cap (non-negotiable)

**EVERY BigQuery query MUST enforce a 200 GB scan cap = `214748364800` bytes. No query runs without it.**

- **`bq` CLI:** inherits the cap from `~/.bigqueryrc`:
  ```
  [query]
  maximum_bytes_billed=214748364800
  ```
- **Python client (and any SDK):** the file is NOT read — set it on every job explicitly:
  ```python
  job_config = bigquery.QueryJobConfig(maximum_bytes_billed=214748364800)
  client.query(sql, job_config=job_config)
  ```
- Any query estimated to scan more than 200 GB is **rejected before it runs** (zero bytes billed).
- This caps **per-query** scan, not monthly spend — it complements the 200 MXN/month project
  budget, it does not replace it.

---

## Confirmed facts

### File naming & coverage

| Series | Pattern | Range observed |
|---|---|---|
| NYC annual | `YYYY-citibike-tripdata.zip` | `2013` → `2023` |
| NYC monthly | `YYYYMM-citibike-tripdata.zip` | `202401` → `202605` |
| Jersey City | `JC-YYYYMM-citibike-tripdata.csv.zip` | `JC-201509` → `JC-202605` |

- NYC switched from **annual** to **monthly** files at **2024-01**. JC has always been monthly.
- Earliest data: NYC **2013** (system launched Jun 2013); JC **2015-09**.
- Latest data: **2026-05** (`202605`) for both NYC and JC.
- `JC-` prefix = Jersey City; everything else = NYC. The two series never mix rows.

**Filename anomalies (do not assume a clean pattern):**
- `JC-201708 citibike-tripdata.csv.zip` — space instead of a hyphen.
- `JC-202207-citbike-tripdata.csv.zip` — "citbike" misspelled.
- Extension drift: most JC files are `.csv.zip`, but `JC-202510`, `JC-202601`, `JC-202604`
  are plain `.zip`.

### Schema map (verified header rows)

The archive has **two schemas**, and **NYC and JC flip on different dates**:

| System | Legacy schema | New schema | Boundary |
|---|---|---|---|
| **NYC** | 2013 – 2019 | **2020-01** onward | between the `2019` and `2020` annual files |
| **JC** | 2015-09 – **2021-01** | **2021-02** onward | inside the JC monthly series |

NYC's archive was **retroactively normalized** (all of 2020 and 2021 read as new-schema,
even Jan 2020). JC follows the **original live cutover** (Feb 2021). Verified: NYC `2019-12`
LEGACY / `2020-01` NEW; JC `2021-01` LEGACY / `2021-02` NEW.

### Columns

**Legacy (15 columns):**
```
tripduration, starttime, stoptime,
start station id, start station name, start station latitude, start station longitude,
end station id, end station name, end station latitude, end station longitude,
bikeid, usertype, birth year, gender
```

**New (13 columns):**
```
ride_id, rideable_type, started_at, ended_at,
start_station_name, start_station_id, end_station_name, end_station_id,
start_lat, start_lng, end_lat, end_lng, member_casual
```

Legacy→new notable changes: `starttime`/`stoptime` → `started_at`/`ended_at`; precomputed
`tripduration` dropped; `bikeid` → `ride_id`; `usertype` (Subscriber/Customer) →
`member_casual` (member/casual); `birth year` and `gender` dropped; `rideable_type` added.

> **`birth_year` / `gender` are legacy-era only.** They exist only in legacy-schema files
> (NYC ≤ 2019, JC ≤ 2021-01) and are **absent — stored as null** for all new-schema data
> (NYC ≥ 2020-01, JC ≥ 2021-02). We keep both columns as nullable in the canonical schema.

### Per-era / structural quirks

- **NYC 2017**: month-named subfolders, each CSV split (`…csv_1.csv`, `…csv_2.csv`); archive
  also carries `.DS_Store` and `__MACOSX/` junk entries.
- **NYC 2018–2019**: flat, directly-stored split CSVs (no nested zips).
- **NYC 2020–2021 annual**: a folder of **nested monthly `.zip` files**, each containing a
  *stored* (uncompressed) CSV — i.e. a zip inside a zip.
- **NYC 2024+ monthly**: flat split CSVs (`…_1.csv` … `_5.csv`).
- **Header formatting differs by source:** NYC headers are unquoted; JC headers are
  double-quoted. JC's 2015 files use **Title-Case-with-spaces** (`Trip Duration,Start Time,…`)
  before settling into lowercase legacy names — normalize headers on ingest.

### Reading a header cheaply (no full download)

`remotezip` + HTTP Range requests reads a zip's central directory and just the first KB of a
member. For the **nested** 2020/2021 zips, stream-decompress the outer member from its data
start only until the inner CSV's first newline (the inner zip's first local-file-header sits at
offset 0, so its central directory is never needed). Each header was read with ≤64 KB fetched.

---

## Confirmed decisions

Each is an approved project decision, with a one-line rationale.

1. **Canonical schema = the New 13-column layout.** _It's the current format and covers the most-recent + largest share of data._
2. **Schema gating is per-system-and-date, not one global date.** _NYC flips at 2020-01 but JC flips at 2021-02; a single cutoff would mis-parse one system._
3. **Add a `system` column (`NYC`/`JC`) on ingest.** _Files are separate series and station IDs can overlap across systems._
4. **Map legacy → new explicitly; keep `birth_year`/`gender` as nullable columns.** _Legacy carries these two demographic columns; new-schema rows lack them, so they are null for NYC ≥ 2020-01 and JC ≥ 2021-02._
5. **Synthesize a surrogate key for legacy rows lacking `ride_id`.** _Downstream dedupe/joins need a stable primary key across both eras._
6. **Derive a `trip_duration_s` from `started_at`/`ended_at` for new-schema rows.** _New files dropped the precomputed `tripduration`; recompute for parity with legacy._
7. **Normalize headers on read: strip quotes/whitespace, lowercase, snake_case.** _JC quoting and JC-2015 Title-Case mean the same logical column appears under several spellings._
8. **Parse filenames with a tolerant regex (allow the space/typo and `.zip`/`.csv.zip`).** _Three known filenames break a strict pattern and would be silently skipped._
9. **Treat `station_id` as a string, not an integer.** _Legacy IDs are small ints; new IDs are longer float-like/string codes — numeric parsing loses data._
10. **Treat timestamps as `America/New_York` local time (no offset in source).** _Citibike publishes wall-clock local time; assuming UTC would shift every trip._
11. **Stream from S3 (range/unzip on the fly); do not commit raw trip data to git.** _Archives are multi-GB; the bucket is the source of truth._
12. **JC scope = IN.** _Jersey City data is in scope and is distinguished from NYC by the `system` column (see decision 3)._
13. **Trip distance = out of scope (not in source, not computed).** _The CSVs carry no distance; straight-line from station coordinates understates real routes, and a Maps/Directions API won't scale to 300M+ trips — so distance is disclosed as out of scope rather than estimated._
14. **Definition of day = the trip's START time, as an America/New_York local date.** _A trip counts toward the NY-local calendar date of `started_at`, so daily rollups line up with the daily Central Park weather join._
