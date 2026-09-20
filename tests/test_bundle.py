"""
Tests that would be expensive to get wrong.

They run against the committed data bundle (app/data/daily_summary_weather.parquet)
with no cloud, no credentials and no network. Every number below is the one the
pipeline was reconciled to; see DECISIONS.md for where each comes from.

    pip install -r requirements.txt
    pytest
"""
from pathlib import Path

import pandas as pd
import pytest

BUNDLE = Path(__file__).resolve().parents[1] / "app" / "data" / "daily_summary_weather.parquet"


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    d = pd.read_parquet(BUNDLE)
    d["trip_date"] = pd.to_datetime(d["trip_date"])
    return d


def test_total_trips_is_the_reconciled_number(df):
    # The one number everything reconciles to (three independent ways in sql/verification.sql).
    assert int(df["trips"].sum()) == 314_774_609


def test_systems_add_up(df):
    by_system = df.groupby("system")["trips"].sum().to_dict()
    assert by_system == {"NYC": 308_193_797, "JC": 6_580_812}


def test_2013_and_2018_are_not_double_counted(df):
    # The first full load silently doubled these two years: the archive stores each
    # month twice (whole-month CSV + split parts). These are the corrected values.
    nyc = df[df["system"] == "NYC"]
    year = nyc["trip_date"].dt.year
    assert int(nyc.loc[year == 2013, "trips"].sum()) == 5_614_888
    assert int(nyc.loc[year == 2018, "trips"].sum()) == 17_548_339


def test_snow_is_whole_millimetres_not_tenths(df):
    # GHCN stores TMAX/TMIN/PRCP in tenths but SNOW in whole mm. A naive /10 would
    # turn the 2021-02-01 nor'easter into 37.6 mm.
    peak = df.loc[df["snow_mm"].idxmax()]
    assert peak["trip_date"].date().isoformat() == "2021-02-01"
    assert peak["snow_mm"] == 376.0


def test_jersey_city_has_no_weather_by_design(df):
    # Central Park weather is NYC weather. JC rows keep NULL rather than a proxy.
    jc = df[df["system"] == "JC"]
    assert jc["tmax_c"].isna().all()
    nyc = df[df["system"] == "NYC"]
    assert nyc["tmax_c"].notna().all()


def test_date_span(df):
    assert df["trip_date"].min().date().isoformat() == "2013-06-01"
    assert df["trip_date"].max().date().isoformat() == "2026-05-31"
