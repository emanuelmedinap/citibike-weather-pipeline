"""
NYC weather vs. Citibike ridership (2013-06 .. 2026-05).

Reads a LOCAL parquet bundle (app/data/daily_summary_weather.parquet) — there is
NO BigQuery client and no network access at runtime, so the public app carries
zero query cost and needs no credentials. The bundle is one row per
trip_date x system, with Central Park weather joined onto NYC rows (JC weather
is null by design).
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

DATA_PATH = Path(__file__).parent / "data" / "daily_summary_weather.parquet"
EXPECTED_TOTAL_TRIPS = 314_774_609          # locked verify anchor
SEASONS = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring",
           5: "Spring", 6: "Summer", 7: "Summer", 8: "Summer", 9: "Fall",
           10: "Fall", 11: "Fall"}


@st.cache_data
def load_data() -> pd.DataFrame:
    df = pd.read_parquet(DATA_PATH)
    # Startup integrity check: the bundle MUST be the verified dataset.
    total = int(df["trips"].sum())
    assert total == EXPECTED_TOTAL_TRIPS, (
        f"bundle integrity check failed: trips sum = {total:,} "
        f"(expected {EXPECTED_TOTAL_TRIPS:,})"
    )
    df["trip_date"] = pd.to_datetime(df["trip_date"])
    df["month"] = df["trip_date"].dt.to_period("M").dt.to_timestamp()
    df["year"] = df["trip_date"].dt.year
    df["month_num"] = df["trip_date"].dt.month
    df["season"] = df["month_num"].map(SEASONS)
    return df


def metric_col(rider: str) -> str:
    return {"All riders": "trips", "Members": "member_trips",
            "Casual": "casual_trips"}[rider]


# ---------------------------------------------------------------- page + load
st.set_page_config(page_title="NYC Weather & Citibike Ridership", layout="wide",
                   page_icon="🚲")
df = load_data()

st.title("How NYC weather moves Citibike ridership")
st.caption("Daily Citibike trips (2013-06 → 2026-05) vs. Central Park weather · "
           "NYC & Jersey City · static bundle, no live queries")

# ------------------------------------------------------------------ sidebar
st.sidebar.header("Filters")
systems = st.sidebar.multiselect("System", ["NYC", "JC"], default=["NYC", "JC"])
rider = st.sidebar.radio("Rider type", ["All riders", "Members", "Casual"])
dmin, dmax = df["trip_date"].min().date(), df["trip_date"].max().date()
date_range = st.sidebar.date_input("Date range", value=(dmin, dmax),
                                    min_value=dmin, max_value=dmax)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
else:                                   # single date picked mid-interaction
    start, end = dmin, dmax

m = metric_col(rider)
mask = (df["system"].isin(systems)
        & (df["trip_date"] >= pd.Timestamp(start))
        & (df["trip_date"] <= pd.Timestamp(end)))
d = df[mask].copy()

if d.empty:
    st.warning("No data for the selected filters — widen the system or date range.")
    st.stop()

# Weather is Central Park / NYC-only; weather panels & KPIs use this subset.
nyc = d[(d["system"] == "NYC") & d["tmax_f"].notna()].copy()

# ---------------------------------------------------------------- KPI rows
daily_totals = d.groupby("trip_date", as_index=False)[m].sum()
busiest = daily_totals.loc[daily_totals[m].idxmax()]
total_sel = int(d[m].sum())
avg_per_day = daily_totals[m].mean()
member_share = d["member_trips"].sum() / max(d["trips"].sum(), 1) * 100

# warm-vs-cold ratio: avg trips/day at >=60F divided by avg trips/day at <60F (NYC)
warm = nyc.loc[nyc["tmax_f"] >= 60, m]
cold = nyc.loc[nyc["tmax_f"] < 60, m]
ratio = (warm.mean() / cold.mean()) if (len(warm) and len(cold) and cold.mean()) else None

r1 = st.columns(3)
r1[0].metric(f"Total trips ({rider.lower()})", f"{total_sel:,}")
r1[1].metric("Avg trips/day", f"{avg_per_day:,.0f}")
r1[2].metric("Warm-vs-cold ratio", f"{ratio:.2f}×" if ratio is not None else "—",
             help="avg trips/day at ≥60°F ÷ avg trips/day at <60°F (NYC, Central Park)")
r2 = st.columns(3)
r2[0].metric("Systems", " + ".join(systems) if systems else "—")
r2[1].metric("Member share", f"{member_share:,.1f}%")
r2[2].metric("Busiest day", f"{busiest[m]:,.0f}", help=f"{busiest['trip_date'].date()}")

st.divider()

# ---------------------------------- 1) ridership + temperature (dual axis)
st.subheader("Ridership & temperature over time")
weekly = (d.assign(week=d["trip_date"].dt.to_period("W").dt.start_time)
            .groupby("week", as_index=False)[m].sum())
temp_weekly = (nyc.assign(week=nyc["trip_date"].dt.to_period("W").dt.start_time)
                 .groupby("week", as_index=False)["tmax_f"].mean())
fig = make_subplots(specs=[[{"secondary_y": True}]])
fig.add_trace(go.Scatter(x=weekly["week"], y=weekly[m], name="trips / week",
                         line=dict(color="#1f77b4")), secondary_y=False)
if not temp_weekly.empty:
    fig.add_trace(go.Scatter(x=temp_weekly["week"], y=temp_weekly["tmax_f"],
                             name="NYC high (°F)",
                             line=dict(color="#d62728", width=1)),
                  secondary_y=True)
fig.update_yaxes(title_text="trips per week", secondary_y=False)
fig.update_yaxes(title_text="NYC daily high (°F)", secondary_y=True)
fig.update_layout(height=430, legend_title="", margin=dict(t=10),
                  hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)
st.caption("Weekly trips (left axis) rise and fall with NYC temperature "
           "(right axis, Central Park) — the seasonal lockstep is the core story.")

# --------------------------------------------- 2) weather vs ridership (NYC)
st.subheader("Weather vs. ridership")
if nyc.empty:
    st.info("No weather data for Jersey City — the Central Park station "
            "represents NYC only. Select NYC to see this panel.")
else:
    if "JC" in systems:
        st.caption("Jersey City is excluded from this panel — Central Park "
                   "weather represents NYC only.")
    fig2 = px.scatter(nyc, x="tmax_f", y=m, color="season",
                      opacity=0.55,
                      category_orders={"season": ["Winter", "Spring",
                                                  "Summer", "Fall"]},
                      labels={"tmax_f": "Daily high (°F)", m: "NYC trips"})
    # OLS trend line (numpy, no statsmodels dependency)
    if len(nyc) > 2:
        b, a = np.polyfit(nyc["tmax_f"], nyc[m], 1)
        xs = np.linspace(nyc["tmax_f"].min(), nyc["tmax_f"].max(), 100)
        fig2.add_trace(go.Scatter(x=xs, y=a + b * xs, mode="lines",
                                  name="trend", line=dict(color="black",
                                                          dash="dash")))
    fig2.update_layout(height=380, legend_title="", margin=dict(t=10))
    st.plotly_chart(fig2, use_container_width=True)
    st.caption("Each dot is one NYC day. Ridership rises with temperature; "
               "cold days sit low.")

# ------------------------------------------------------ 3) rain & snow (NYC)
st.subheader("Rain & snow")
if nyc.empty:
    st.info("No weather data for Jersey City — the Central Park station "
            "represents NYC only. Select NYC to see this panel.")
else:
    fig_rs = px.scatter(nyc, x="prcp_mm", y=m, color="snow_mm",
                        color_continuous_scale="Blues",
                        labels={"prcp_mm": "Daily precipitation (mm)",
                                m: "NYC trips", "snow_mm": "snow (mm)"})
    noreaster = nyc[nyc["trip_date"] == pd.Timestamp("2021-02-01")]
    if not noreaster.empty:
        row = noreaster.iloc[0]
        fig_rs.add_annotation(
            x=float(row["prcp_mm"]), y=float(row[m]),
            text=f"2021-02-01 nor'easter — snow {row['snow_mm']:.0f} mm",
            showarrow=True, arrowhead=2, ax=60, ay=-40,
            bgcolor="white", bordercolor="black")
    fig_rs.update_layout(height=380, margin=dict(t=10))
    st.plotly_chart(fig_rs, use_container_width=True)
    st.caption("Each dot is one NYC day. Wet days pull ridership down; the "
               "2021-02-01 blizzard (376 mm snow) sits at the low, high-precip corner.")

# ------------------------------------------------ 4) member vs casual mix
st.subheader("Member vs. casual mix")
mix = d.groupby("month", as_index=False)[["member_trips", "casual_trips"]].sum()
mix_long = mix.melt(id_vars="month",
                    value_vars=["member_trips", "casual_trips"],
                    var_name="rider", value_name="n")
mix_long["rider"] = mix_long["rider"].map({"member_trips": "Member",
                                           "casual_trips": "Casual"})
fig3 = px.area(mix_long, x="month", y="n", color="rider", groupnorm="fraction",
               color_discrete_map={"Member": "#2ca02c", "Casual": "#d62728"},
               labels={"n": "share", "month": ""})
fig3.update_layout(height=320, yaxis_tickformat=".0%", legend_title="",
                   margin=dict(t=10))
st.plotly_chart(fig3, use_container_width=True)
st.caption("Share of trips by rider type (always shows both, regardless of the "
           "rider filter). Casual share spikes each summer and in 2020–21.")

# ---------------------------------------------------------- 5) seasonality
st.subheader("Seasonality")
daily = d.groupby(["trip_date", "year", "month_num"],
                  as_index=False)[m].sum()
season_piv = (daily.groupby(["year", "month_num"])[m].mean()
              .reset_index()
              .pivot(index="year", columns="month_num", values=m))
season_piv.columns = [pd.Timestamp(2000, c, 1).strftime("%b")
                      for c in season_piv.columns]
fig4 = px.imshow(season_piv, aspect="auto", color_continuous_scale="YlGnBu",
                 labels=dict(color="avg daily trips", x="", y=""))
fig4.update_layout(height=380, margin=dict(t=10))
st.plotly_chart(fig4, use_container_width=True)
st.caption("Average daily trips by month × year — strong summer peak, winter "
           "trough, repeating every year.")
