"""
Citibike ridership dashboard (2013-06 .. 2026-05).

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
st.set_page_config(page_title="Citibike Ridership", layout="wide",
                   page_icon="🚲")
df = load_data()

st.title("🚲 Citibike Ridership — NYC & Jersey City")
st.caption("2013-06 → 2026-05 · daily rollup with Central Park weather · "
           "served from a static bundle (no live queries)")

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

# ---------------------------------------------------------------- KPI row
daily_totals = d.groupby("trip_date", as_index=False)[m].sum()
busiest = daily_totals.loc[daily_totals[m].idxmax()]
total_sel = int(d[m].sum())
member_share = d["member_trips"].sum() / max(d["trips"].sum(), 1) * 100

k1, k2, k3, k4 = st.columns(4)
k1.metric(f"Trips ({rider.lower()})", f"{total_sel:,}")
k2.metric("Systems", " + ".join(systems) if systems else "—")
k3.metric("Member share", f"{member_share:,.1f}%")
k4.metric("Busiest day",
          f"{busiest[m]:,.0f}",
          help=f"{busiest['trip_date'].date()}")

st.divider()

# ------------------------------------------------------ 1) ridership trend
st.subheader("Ridership trend")
trend = d.groupby(["month", "system"], as_index=False)[m].sum()
fig = px.area(trend, x="month", y=m, color="system",
              labels={m: "trips", "month": ""},
              color_discrete_map={"NYC": "#1f77b4", "JC": "#ff7f0e"})
fig.update_layout(height=360, legend_title="", margin=dict(t=10))
st.plotly_chart(fig, use_container_width=True)
st.caption("Monthly trips. Note the 2020 COVID dip and the climb to all-time highs.")

# --------------------------------------------- 2) weather vs ridership (NYC)
st.subheader("Weather vs. ridership")
nyc = d[(d["system"] == "NYC") & d["tmax_f"].notna()]
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
               "cold/rain/snow days sit low.")

# ------------------------------------------------ 3) member vs casual mix
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

# ---------------------------------------------------------- 4) seasonality
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
