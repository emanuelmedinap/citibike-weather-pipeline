# DECISIONS.md — Citibike end-to-end pipeline & dashboard

This documents the design decisions across both parts of the project — Part 1
(the BigQuery data pipeline) and Part 2 (the public dashboard) — with the
reasoning and tradeoffs behind each, plus the verification evidence. Everything
reconciles to a single number: **314,774,609 trips**.

## Reference (project, objects, URL)

| Thing | Value |
|---|---|
| GCP project | `msbai-dwd-em5844` |
| GCS staging bucket | `gs://msbai-dwd-em5844-citibike-raw` (US) |
| Raw tables | `citibike_raw.trips_legacy`, `citibike_raw.trips_new` |
| Clean view | `citibike_raw.trips_clean` |
| Marts | `citibike_marts.daily_summary`, `citibike_marts.weather`, `citibike_marts.daily_summary_weather` |
| Ingest script | `ingest/ingest.py` |
| Dashboard app | `app/` (Streamlit) |
| Public dashboard | https://citibike-dashboard-272987333238.us-central1.run.app |
| Source data | Public Citibike archive — `https://s3.amazonaws.com/tripdata/` (169 zip files) |

Architecture is a straight line: **S3 archive → GCS staging → two raw tables →
one clean view → marts (daily rollup + weather) → static bundle → Cloud Run app.**

---

## Part 1 — Data pipeline decisions

### Source & scope
The Citibike archive is 169 zip files, NYC (`YYYY`/`YYYYMM`) and Jersey City
(`JC-YYYYMM`), spanning **2013-06 → 2026-05**. Two facts drove everything: the
CSV **schema changed** partway through, and the archive is **structurally messy**
(nested zips, split CSVs, subfolders, filename typos, duplicated months).

### Two raw tables, split by schema era (not one table)
Citibike published two column layouts: a **legacy 15-column** format
(`tripduration, starttime, …, birth year, gender`) and a **new 13-column**
format (`ride_id, rideable_type, started_at, …, member_casual`). We land these
in **separate** raw tables — `trips_legacy` and `trips_new` — rather than
forcing them into one shape on load.

- **Why:** the two eras genuinely differ (new drops `birth_year`/`gender`, adds
  `ride_id`/`rideable_type`, renames time columns). Keeping them apart means the
  raw layer never guesses or coerces — it stays a faithful mirror of the source.
- **Tradeoff:** consumers must union the two, which we handle once in the clean
  view instead of pushing that burden downstream.

### Raw = all-STRING, no normalization on load
Every source column lands as `STRING`, untouched, plus two provenance columns
(`system` ∈ {NYC, JC}, `source_file`). No typing, no renaming of values, no
unit math at load time.

- **Why:** load is the wrong place to lose fidelity. Type coercion at ingest
  silently drops malformed values; keeping raw-as-text means a bad value is
  visible, not erased. All interpretation lives in one auditable place (the view).
- **Tradeoff:** every query pays a `SAFE_CAST`/parse cost, and the raw tables
  aren't directly analyzable. Acceptable — the clean view exists for that.
- **Loads are `bq load` (free)**, not external-table `INSERT…SELECT`, so ingest
  never bills query bytes or touches the 200 GB cap.

### Per-system schema boundaries: NYC 2020-01, JC 2021-02 (they differ!)
The single most important correctness detail. We verified by reading header rows
directly (HTTP range requests, no full downloads):

- **NYC** flips legacy→new at the **2019→2020** file boundary — the archive was
  *retroactively normalized*, so all of 2020–2021 is already new-schema.
- **JC** flips at **2021-02** — it follows the *original live* cutover (Jan 2021
  is still legacy).

- **Why it matters:** a single global cutoff date would mis-file an entire
  system's worth of data. The ingest classifier keys era on `(system, yearmonth)`.

### Surrogate `ride_id` for legacy rows
The new schema has a `ride_id`; legacy has none. In the clean view we synthesize
`leg_<md5(starttime|stoptime|bikeid|stations|source_file)>`.

- **Why:** downstream joins/dedupe need a stable primary key across both eras.
- **Tradeoff:** two byte-identical legacy rows would collide to one id (rare, and
  acceptable for a surrogate — it's not a natural key and we don't claim it is).

### The 2013 / 2018 double-count catch (data-quality win)
The first full load reconciled arithmetically but was **wrong**: the `2013` and
`2018` archives store **every month twice** — once as a flat whole-month CSV and
again as size-split parts under a month subfolder (different filenames, so naive
dedup missed them). This silently **doubled** those two years in `trips_legacy`.

- **The fix:** within a source file, if a month has a whole-month file, keep it
  and **skip that month's split parts** (name-only rule). The hardened
  `ingest.py` also content-hashes same-named members (identical → skip; divergent
  → abort for review).
- **Evidence:** 2018 went from a doubled 35,096,678 to the true **17,548,339**;
  2013 to **5,614,888**; other legacy years unchanged. `trips_legacy` rebuilt
  legacy-only from 116,810,308 (wrong) → **93,647,081** (correct).
- **Lesson/tradeoff:** an exact staged-vs-loaded reconciliation is *necessary but
  not sufficient* — the duplication lived in both sides of the equation. Only
  inspecting the archive structure exposed it.

### SNOW is whole millimeters, not tenths
GHCN stores most elements in tenths (TMAX/TMIN in tenths °C, PRCP in tenths mm),
so the obvious move is "divide everything by 10." But **SNOW (and SNWD) are
already whole mm.** We divide only TMAX/TMIN/PRCP; SNOW passes through.

- **Why it matters:** dividing SNOW by 10 is a silent 10× error. The 2021-02-01
  nor'easter reads **376 mm** — correct; a naive `/10` would show 37.6 mm.

### Timestamps as naive America/New-York DATETIME
`started_at`/`ended_at` are emitted as `DATETIME` (wall-clock, no timezone),
exactly as Citibike publishes them. We deliberately did **not** add a UTC
`TIMESTAMP`.

- **Why:** the source is local wall-clock. Converting to UTC would imply a
  precision/zone the data doesn't carry and introduces DST ambiguity. For a
  ridership dashboard, "the local time the ride happened" is what matters.
- **Legacy parsing gotcha:** 2018–2019 timestamps carry **fractional seconds**
  (`2019-04-08 17:01:41.6950`). Our first parse missed them → 39.2M null
  timestamps; adding `%Y-%m-%d %H:%M:%E*S` to the `SAFE` `COALESCE` fixed it to
  **0 parse failures**.

### Verification evidence (Part 1)
Validated by direct query (~18.7 GB scan, under the cap):

| Check | Value |
|---|---|
| **Total trips** | **314,774,609** |
| `trips_legacy` / `trips_new` | 93,647,081 / 221,127,528 |
| NYC / JC | 308,193,797 / 6,580,812 |
| member / casual / unknown | 258,410,354 / 56,311,978 / 52,277 |
| Date span | 2013-06-01 → 2026-05-31 |
| Timestamp parse failures | **0** (both eras) |
| 2013 / 2018 NYC (post de-dup) | 5,614,888 / 17,548,339 |

`member + casual + unknown` and `legacy + new` and `NYC + JC` all sum to
314,774,609 — the number is internally consistent from three independent angles.

---

## Part 2 — Marts & dashboard decisions

### A dedicated `citibike_marts` reporting layer
Analytics-facing tables live in their own dataset, separate from `raw`/`clean`.

- **Why:** clean separation of concerns — `raw` is fidelity, `clean` is
  interpretation, `marts` is the small, fast, dashboard-shaped output.

### `daily_summary`: one row per day × system
Aggregates `trips_clean` to **~8,634 rows**: trip count, bounded avg + approx
median duration, member/casual/unknown, distinct start stations, outlier count.

- **Bounded avg/median** over `0 < trip_duration_s ≤ 86400`, with a
  `duration_outliers` column. *Why:* unreturned-bike trips (>24h) and a few
  negative durations skew the mean; bounding gives a "typical ride" number while
  the outlier count keeps it honest (nothing hidden).
- **No partitioning.** *Why:* ~4,738 daily partitions would exceed BigQuery's
  4,000-partition limit, and the table is sub-MB anyway — partitioning would add
  cost, not save it.

### `weather`: Central Park daily, from BigQuery public GHCN
`weather` pivots `bigquery-public-data.ghcn_d` (station **USW00094728**,
elements TMAX/TMIN/PRCP/SNOW) to one row per date, with °C, °F, and mm.

- **Why a public dataset:** no extra ingest pipeline; NOAA data is authoritative
  and already in BigQuery. Filtered to `qflag` blank (passed QC).

### NYC-only weather — an honesty decision
`daily_summary_weather` LEFT JOINs `weather` onto **all** daily rows, but the
`system = 'NYC'` predicate sits in the **`ON` clause**, so JC rows are preserved
with **NULL weather**.

- **Why:** Central Park weather represents NYC, not Jersey City (across the
  river). Rather than silently attach NYC weather to JC as a proxy, we leave it
  null — visibly, so nobody mistakes it for real JC weather. The dashboard shows
  a "no weather for Jersey City" note.
- **Tradeoff:** JC gets no weather analysis. Correct over convenient.
- **Coverage:** 100% — 0 of 4,738 NYC trip-days are missing a weather row.

### Static bundle, no runtime BigQuery
The dashboard reads a **parquet file baked into the container**
(`app/data/daily_summary_weather.parquet`, 8,634 rows, ~267 KB). There is **no
BigQuery client at runtime.**

- **Why:** the data is tiny and the app is public. Bundling it means the public
  app needs **no credentials**, makes **zero queries**, and **cannot run up a
  bill** no matter the traffic. It also scales to zero and starts fast.
- **Tradeoff:** refreshing data requires a rebuild+redeploy (re-run the export,
  redeploy). For a monthly-updated dataset that's the right call over a live
  connection with per-request cost and a credential to leak.
- **Integrity guard:** the app asserts `df.trips.sum() == 314_774_609` at
  startup, so a stale or corrupt bundle fails loudly instead of showing wrong
  numbers.

### Streamlit on Cloud Run, public
`python:3.12-slim`, non-root, binds `$PORT`; deployed to Cloud Run
`us-central1`, `--allow-unauthenticated`.

- **Why:** Streamlit gives rich interactive panels for little code; Cloud Run
  scales to zero (no idle cost) and serves the public URL. Cloud Run region is
  independent of the US BigQuery data since there are no runtime queries.

### Verify targets (what the dashboard must show)
Locked numbers we confirm against the live app:
`314,774,609` total; NYC `308,193,797` / JC `6,580,812`; member share 82.1%;
busiest NYC day `2025-09-26` = 202,031 (206,848 combined); span 2013-06 → 2026-05.
The startup assert is the automated half of this check.

---

## Guardrails (cost controls)

Both were set **before** any ingest, deliberately.

- **Budget:** 200 MXN/month (≈ $10–11 USD) on the project's billing account,
  scoped to this project, alerts at 50/90/100%. *Notification-only — GCP budgets
  never hard-cap spend*, so it's an alarm, not a brake. (The account is
  MXN-denominated, hence 200 MXN rather than a `$10` code.)
- **Per-query cap:** `maximum_bytes_billed = 214748364800` (**200 GB**) — enforced
  for the `bq` CLI via `~/.bigqueryrc [query]`, and required in code via
  `job_config.maximum_bytes_billed`. Any query estimated over 200 GB is rejected
  before it runs. This is a *per-query* scan cap; it complements, not replaces,
  the monthly budget.

Together: the cap stops a single runaway query; the budget warns if steady usage
creeps up. Every build query stayed well under the cap (largest ~20.6 GB).

---

## Tooling & environment

- **Built with the Claude Code CLI**, using a **PR-based, repo-as-memory
  workflow**: each step landed as its own branch → pull request → squash-merge,
  so the git history is the audit trail of what was decided and why.
- **Runs on a personal GCP project and GitHub account (not Stern-managed) —
  deliberately.** Keeping it off Stern infrastructure makes the whole thing a
  portable, self-owned **portfolio artifact** that outlives the course and
  doesn't depend on institutional access.
- **The instructor and Ilias were granted explicit access** (GitHub repo + GCP
  project) per Part 0, so the graders can review everything despite it living on
  personal accounts.
