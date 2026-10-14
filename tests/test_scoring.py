import json
from datetime import date
from pathlib import Path

import pytest

from outing_copilot.scoring import (
    best_window, gear_tips, resolve_activity, resolve_day, score_hour, score_hours,
)

FX = Path(__file__).parent / "fixtures"


def test_perfect_hour_scores_100():
    s, why = score_hour(resolve_activity("walk"), feels_f=65, rain_pct=0, wind_mph=5, uv=3, aqi=20)
    assert s == 100 and why == []


def test_rain_hurts_picnic_more_than_dog_walk():
    kw = dict(feels_f=65, rain_pct=80, wind_mph=5, uv=2, aqi=20)
    picnic, _ = score_hour(resolve_activity("picnic"), **kw)
    dog, _ = score_hour(resolve_activity("dog"), **kw)
    assert picnic < dog


def test_sensitive_air_uses_stricter_limit():
    act = resolve_activity("run")
    normal, _ = score_hour(act, feels_f=60, rain_pct=0, wind_mph=0, uv=0, aqi=80)
    strict, why = score_hour(act, feels_f=60, rain_pct=0, wind_mph=0, uv=0, aqi=80, sensitive_to_air=True)
    assert normal == 100 and strict < 100 and any("AQI" in w for w in why)


def test_aliases_and_unknown_activity():
    assert resolve_activity("Jogging").key == "run"
    with pytest.raises(ValueError):
        resolve_activity("skydiving")


def test_resolve_day():
    wed = date(2026, 10, 14)
    assert resolve_day("tomorrow", wed) == [date(2026, 10, 15)]
    assert resolve_day("weekend", wed) == [date(2026, 10, 17), date(2026, 10, 18)]
    assert resolve_day("friday", wed) == [date(2026, 10, 16)]
    with pytest.raises(ValueError):
        resolve_day("someday", wed)


def test_best_window_on_recorded_forecast_is_daylight_and_contiguous():
    fc = json.loads((FX / "forecast_seattle.json").read_text())
    air = json.loads((FX / "airquality_seattle.json").read_text())
    hours = score_hours(resolve_activity("walk"), fc, air)
    w = best_window(hours, date(2026, 10, 15), 2)
    assert w is not None
    assert 6 <= w.start.hour <= 18
    assert (w.end - w.start).total_seconds() == 7200
    assert 0 <= w.score <= 100
    assert isinstance(gear_tips(w), list)


def test_unknown_aqi_never_perfect_when_sensitive():
    act = resolve_activity("run")
    plain, _ = score_hour(act, feels_f=60, rain_pct=0, wind_mph=0, uv=0, aqi=None)
    strict, why = score_hour(act, feels_f=60, rain_pct=0, wind_mph=0, uv=0, aqi=None, sensitive_to_air=True)
    assert plain == 100
    assert strict < 100 and "air quality unknown" in why


def test_air_fixture_covers_seven_days_with_trailing_nulls():
    air = json.loads((FX / "airquality_seattle.json").read_text())
    times, aqi = air["hourly"]["time"], air["hourly"]["us_aqi"]
    assert len(times) == 168  # 7 days requested
    assert aqi[0] is not None and aqi[-1] is None  # tail is unknown upstream


def test_hours_are_strictly_within_daylight():
    fc = json.loads((FX / "forecast_seattle.json").read_text())
    hours = score_hours(resolve_activity("walk"), fc, None)
    from datetime import datetime, timedelta
    sun = {d: (datetime.fromisoformat(r), datetime.fromisoformat(s))
           for d, r, s in zip(fc["daily"]["time"], fc["daily"]["sunrise"], fc["daily"]["sunset"])}
    for h in hours:
        rise, sset = sun[h.time.date().isoformat()]
        assert h.time >= rise and h.time + timedelta(hours=1) <= sset
    first = min(h.time for h in hours if h.time.date().isoformat() == "2026-10-14")
    assert first.hour == 8  # sunrise 07:26 -> first full daylight hour starts 08:00
