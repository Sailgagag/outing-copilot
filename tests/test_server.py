"""End-to-end tests through a real MCP client, with all HTTP served from fixtures."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
from mcp import Client

from outing_copilot.clients import fixture_transport
from outing_copilot.server import create_server
from outing_copilot.store import Store

FX = Path(__file__).parent / "fixtures"
# Fixtures were recorded 2026-10-14 ~02:30 Seattle time; pin the clock there.
NOW = lambda: datetime(2026, 10, 14, 9, 30, tzinfo=timezone.utc)  # noqa: E731


@pytest.fixture
def server(tmp_path):
    return create_server(transport=fixture_transport(FX), store=Store(tmp_path / "state.json"), now=NOW)


async def call(server, name, args=None):
    async with Client(server) as c:
        r = await c.call_tool(name, args or {})
        return r.structured_content


async def test_lists_expected_tools(server):
    async with Client(server) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert {"find_best_time", "week_outlook", "remember_place", "list_saved_places", "set_preferences"} <= names


async def test_find_best_time_chains_services(server):
    r = await call(server, "find_best_time", {"place": "Seattle", "activity": "walk", "day": "tomorrow"})
    assert r["ok"] and r["day"] == "2026-10-15"
    assert r["verdict"] in {"go", "maybe", "skip"}
    assert "Seattle" in r["speech"] and len(r["speech"]) < 400
    assert len(r["sources"]) == 5


async def test_unknown_place_is_friendly(server):
    r = await call(server, "find_best_time", {"place": "Atlantisville"})
    assert r["ok"] is False and "couldn't find" in r["speech"]


async def test_bad_day_is_friendly(server):
    r = await call(server, "find_best_time", {"place": "Seattle", "day": "next century"})
    assert r["ok"] is False


async def test_memory_persists_across_sessions(server, tmp_path):
    await call(server, "remember_place", {"nickname": "Home", "place": "Seattle"})
    # brand new server instance, same state file = a later session
    s2 = create_server(transport=fixture_transport(FX), store=Store(tmp_path / "state.json"), now=NOW)
    places = await call(s2, "list_saved_places")
    assert "home" in places["places"]
    r = await call(s2, "find_best_time", {"place": "home", "activity": "bike"})
    assert r["ok"] and r["place"]["name"] == "Seattle"


async def test_alerts_are_spoken(server, monkeypatch):
    monkeypatch.setenv("OUTING_ALERTS_FIXTURE", "alerts_synthetic_wind.json")
    r = await call(server, "find_best_time", {"place": "Seattle", "activity": "bike"})
    assert r["alerts"][0]["event"] == "Wind Advisory"
    assert "Wind Advisory" in r["speech"]


async def test_week_outlook_ranks_seven_days(server):
    r = await call(server, "week_outlook", {"place": "Seattle", "activity": "picnic", "duration_hours": 2})
    assert r["ok"] and len(r["days"]) == 7
    assert r["best"]["score"] == max(d["score"] for d in r["days"])


async def test_preferences(server):
    r = await call(server, "set_preferences", {"sensitive_to_air": True, "default_activity": "cycling"})
    assert r["prefs"] == {"sensitive_to_air": True, "default_activity": "bike"}


async def test_streamable_http_app_builds(server):
    app = server.streamable_http_app()
    assert any(getattr(r, "path", "") == "/mcp" for r in app.routes)


async def test_past_hours_are_never_suggested(tmp_path):
    late = lambda: datetime(2026, 10, 15, 0, 30, tzinfo=timezone.utc)  # 17:30 in Seattle  # noqa: E731
    s = create_server(transport=fixture_transport(FX), store=Store(tmp_path / "s.json"), now=late)
    r = await call(s, "find_best_time", {"place": "Seattle", "activity": "walk", "day": "today"})
    assert r["ok"] and r["window"]["start"] >= "2026-10-14T17:00"


async def test_week_outlook_asthma_flags_unknown_air_days(server):
    await call(server, "set_preferences", {"sensitive_to_air": True})
    r = await call(server, "week_outlook", {"place": "Seattle", "activity": "run"})
    unknown = [d for d in r["days"] if d["air_quality"] == "unknown"]
    assert unknown, "days 6-7 have no AQI upstream"
    assert all(d["score"] < 100 for d in unknown)
    assert "air-quality data isn't available that far out" in r["speech"]
    assert unknown[-1]["weekday"] in r["speech"]


@pytest.mark.parametrize("tool", ["find_best_time", "week_outlook"])
@pytest.mark.parametrize("hours", [0, 7, -2, 24])
async def test_duration_out_of_range_is_spoken(server, tool, hours):
    r = await call(server, tool, {"place": "Seattle", "duration_hours": hours})
    assert r["ok"] is False
    assert r["speech"].startswith("I can plan outings from 1 to 6 hours long")


async def test_duration_bounds_accepted(server):
    for hours in (1, 6):
        r = await call(server, "find_best_time", {"place": "Seattle", "day": "tomorrow", "duration_hours": hours})
        assert r["ok"]


async def test_set_preferences_bad_activity_is_friendly(server):
    r = await call(server, "set_preferences", {"default_activity": "skydiving"})
    assert r["ok"] is False
    assert "skydiving" in r["speech"] and "Try a walk" in r["speech"]
    assert set(r) >= {"ok", "speech", "card"}


@pytest.mark.parametrize("nick", ["", "   ", "\t"])
async def test_remember_place_rejects_blank_nickname(server, nick):
    r = await call(server, "remember_place", {"nickname": nick, "place": "Seattle"})
    assert r["ok"] is False and "What should I call this place" in r["speech"]


async def test_remember_place_strips_nickname(server):
    r = await call(server, "remember_place", {"nickname": "  Grandma  ", "place": "Seattle"})
    assert r["nickname"] == "grandma"
    assert "remember Grandma as" in r["speech"]
    assert "grandma" in (await call(server, "list_saved_places"))["places"]


async def test_ambiguous_city_is_named_in_speech(server):
    r = await call(server, "find_best_time", {"place": "Portland", "activity": "walk", "day": "tomorrow"})
    assert r["ok"]
    assert "in Portland, Oregon" in r["speech"]
    assert "say Portland, Maine if you meant that one" in r["speech"]
    assert r["place"]["alternatives"][0] == "Portland, Maine"


async def test_qualified_city_is_not_ambiguous(server):
    r = await call(server, "find_best_time", {"place": "Portland, Maine", "day": "tomorrow"})
    assert r["ok"] and r["place"]["region"] == "Maine"
    assert "in Portland, Maine" in r["speech"]
    assert "if you meant" not in r["speech"]


async def test_unambiguous_city_keeps_short_name(server):
    r = await call(server, "find_best_time", {"place": "Seattle", "day": "tomorrow"})
    assert "in Seattle tomorrow" in r["speech"] and "I picked" not in r["speech"]


async def test_nickname_that_is_a_real_city_warns(server):
    r = await call(server, "remember_place", {"nickname": "Paris", "place": "Seattle"})
    assert r["ok"] and "Paris, France is also a real place" in r["speech"]
    r = await call(server, "find_best_time", {"place": "paris", "day": "tomorrow"})
    assert r["place"]["name"] == "Seattle"
    assert "saved place paris, not the city" in r["speech"]


async def test_ordinary_nickname_has_no_warning(server):
    r = await call(server, "remember_place", {"nickname": "home", "place": "Seattle"})
    assert "Heads up" not in r["speech"]


@pytest.mark.parametrize(
    "tool,args,expected",
    [
        ("find_best_time", {}, "I need the place to do that."),
        ("find_best_time", {"place": "Seattle", "duration_hours": "lots"}, "For how many hours, please use a whole number"),
        ("week_outlook", {"place": 42}, "For the place, please use a word or name"),
        ("set_preferences", {"sensitive_to_air": "kinda"}, "please answer yes or no"),
        ("remember_place", {"place": "Seattle"}, "I need a name for the place"),
    ],
)
async def test_validation_errors_are_spoken(server, tool, args, expected):
    async with Client(server) as c:
        r = await c.call_tool(tool, args)
    assert r.is_error
    text = r.content[0].text
    assert expected in text
    assert "validation error" not in text and "pydantic" not in text
    assert r.structured_content["ok"] is False and r.structured_content["speech"] == text
