# SPEC.md — Part 2 dashboard specification

Drafted from what is built and deployed. Owner: reviewer/author to confirm.

**Live:** https://citibike-dashboard-272987333238.us-central1.run.app (public, no login)

## Thesis / purpose
A public dashboard that answers one question in plain sight: **how does NYC
weather move Citibike ridership?** Weather leads the narrative; rider mix and
seasonality support it.

## Target visitor
A **non-technical journalist or city planner** — someone who wants the story at a
glance, can read a chart, but will not write SQL or open BigQuery. The dashboard
must be legible with zero setup and no account.

## Business questions it answers
1. Does ridership rise and fall with **temperature**? (headline: warm-vs-cold ratio)
2. How much do **rain and snow** suppress ridership? (e.g. the 2021-02-01 blizzard)
3. What is the **13-year growth trend**, and where are the shocks (2020 COVID dip)?
4. How does the **member vs. casual** mix shift over time and by season?
5. How **seasonal** is ridership, year over year?
6. How do **NYC and Jersey City** compare in volume?

## Filters / slices exposed
- **System:** NYC, JC, or both.
- **Date range:** any window within 2013-06 → 2026-05.
- **Rider type:** All riders / Members / Casual (drives KPIs and volume panels;
  the member-vs-casual mix panel always shows both).
- Weather panels are **NYC-only** (Central Park); JC shows a "no weather" note.

## Panels (each carries a one-sentence English claim)
1. **Ridership & temperature over time** (dual-axis) — weekly trips track NYC temperature.
2. **Weather vs. ridership** (scatter + trend) — ridership rises with temperature.
3. **Rain & snow** — wet days pull ridership down; the 2021-02-01 nor'easter (376 mm snow) sits at the low corner.
4. **Member vs. casual mix** — members dominate; casual share spikes each summer and in 2020–21.
5. **Seasonality** (month × year heatmap) — strong summer peak, winter trough, every year.

## Verify targets (concrete, measurable)
1. **Load-time number** — the page renders and shows the headline KPI
   **314,774,609 total trips**. **Warm load: under 3 seconds** (typical). **Cold
   start: ~15 seconds** on the first hit after scale-to-zero. Reads a 267 KB
   local parquet bundle (no live queries).
2. **Correctness check** — the "Total trips" KPI equals **314,774,609**, enforced
   at startup by `assert df.trips.sum() == 314_774_609`, and independently
   reproducible via `sql/verification.sql` (reconciles to the same total three ways).
3. **Public-reach test** — open the URL in a fresh incognito window with **no
   Google/GitHub login** → HTTP 200 and the dashboard renders (Cloud Run IAM
   grants `allUsers` the invoker role).
4. **Clarity bar** — a non-technical reader can state the weather → ridership
   takeaway within ~30 seconds: every chart has a one-sentence claim, and the
   **warm-vs-cold ratio (≈1.84×)** headlines the thesis in the KPI row.

## Data & refresh
The dashboard reads a static bundle (`app/data/daily_summary_weather.parquet`,
one row per day × system, weather pre-joined for NYC). No BigQuery at runtime →
zero query cost, no credentials. Refresh = re-export the
`citibike_marts.daily_summary_weather` view and redeploy.
