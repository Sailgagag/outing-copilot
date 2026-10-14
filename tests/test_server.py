"""End-to-end tests through a real MCP client, with all HTTP served from fixtures."""
from pathlib import Path

import pytest
from mcp import Client

from outing_copilot.clients import fixture_transport
from outing_copilot.server import create_server
from outing_copilot.store import Store

FX = Path(__file__).parent / "fixtures"


@pytest.fixture
def server(tmp_path):
    return create_server(transport=fixture_transport(FX), store=Store(tmp_path / "state.json"))


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
    s2 = create_server(transport=fixture_transport(FX), store=Store(tmp_path / "state.json"))
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
