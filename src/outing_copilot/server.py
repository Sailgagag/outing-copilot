"""Outing Copilot MCP server (Streamable HTTP).

Chains five free, key-less public services per request:
Open-Meteo Geocoding -> Open-Meteo Forecast + Open-Meteo Air Quality ->
Nager.Date public holidays -> US National Weather Service alerts (US only).
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Callable
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ValidationError

from . import clients
from .scoring import (
    best_window, fmt_time, gear_tips, resolve_activity, resolve_day, score_hours, ACTIVITIES,
)
from .store import Store

INSTRUCTIONS = (
    "Outing Copilot answers 'when should I go outside?' for a walk, run, bike ride, picnic, playground "
    "trip or dog walk. Prefer find_best_time for a specific day and week_outlook for 'which day this week'. "
    "Every result has a short 'speech' field written to be read aloud by a voice assistant, and a 'card' "
    "for screens. Users can save places by nickname (e.g. 'home', 'grandma') and then use the nickname."
)

MIN_DURATION, MAX_DURATION = 1, 6

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


FIELD_LABELS = {
    "place": "the place",
    "activity": "the activity",
    "day": "the day",
    "duration_hours": "how many hours",
    "nickname": "a name for the place",
    "sensitive_to_air": "whether anyone is sensitive to air quality",
    "default_activity": "the default activity",
}


def spoken_validation_error(exc: ValidationError) -> str:
    """Turn a raw pydantic error into one sentence a voice assistant can read out."""
    err = exc.errors()[0]
    field = str(err["loc"][0]) if err.get("loc") else ""
    label = FIELD_LABELS.get(field, field.replace("_", " ") or "that")
    kind = err.get("type", "")
    if kind == "missing":
        return f"I need {label} to do that. Could you tell me?"
    if kind.startswith("int") or kind.startswith("float"):
        return f"For {label}, please use a whole number, like 2."
    if kind.startswith("bool"):
        return f"For {label}, please answer yes or no."
    if kind.startswith("string"):
        return f"For {label}, please use a word or name, like Seattle."
    return f"Sorry, I didn't understand {label}. Could you say it another way?"


class OutingServer(MCPServer):
    """MCPServer whose argument-validation errors come back as friendly, speakable results."""

    async def call_tool(self, name, arguments, context=None):  # type: ignore[override]
        try:
            return await super().call_tool(name, arguments, context)
        except ToolError as exc:
            if not isinstance(exc.__cause__, ValidationError):
                raise
            speech = spoken_validation_error(exc.__cause__)
            return CallToolResult(
                content=[TextContent(type="text", text=speech)],
                structured_content={"ok": False, "speech": speech, "card": {"title": "Outing Copilot", "text": speech}},
                is_error=True,
            )


def create_server(
    transport: httpx.AsyncBaseTransport | None = None,
    store: Store | None = None,
    now: Callable[[], datetime] | None = None,
) -> MCPServer:
    """Build the server. ``now`` (UTC) is injectable so tests with recorded data stay deterministic."""
    store = store or Store()
    now = now or (lambda: datetime.now(timezone.utc))

    def _drop_past(hours, fc):
        local_now = (now() + timedelta(seconds=fc.get("utc_offset_seconds", 0))).replace(tzinfo=None)
        cutoff = local_now.replace(minute=0, second=0, microsecond=0)
        return [h for h in hours if h.time >= cutoff]

    def _dedupe(reasons):
        seen, out = set(), []
        for r in reasons:
            key = r.split(" (")[-1] if "feels like" in r else r.split(" ")[-1] if "%" in r else r.split(" ")[0]
            if key not in seen:
                seen.add(key); out.append(r)
        return out

    mcp = OutingServer(name="outing-copilot", title="Outing Copilot", version="0.1.0", instructions=INSTRUCTIONS)

    async def _locate(http: httpx.AsyncClient, place: str) -> dict[str, Any]:
        saved = store.get_place(place)
        if saved:
            # Saved places are already settled: don't re-announce their ambiguity.
            return {**saved, "alternatives": [], "nickname": place.strip().lower()}
        loc = await clients.geocode(http, place)
        if not loc:
            raise ValueError(f"I couldn't find a place called '{place}'.")
        return loc

    async def _context(http: httpx.AsyncClient, loc: dict[str, Any]):
        fc, air = await asyncio.gather(
            clients.forecast(http, loc["latitude"], loc["longitude"]),
            clients.air_quality(http, loc["latitude"], loc["longitude"]),
        )
        return fc, air

    async def _holidays(http: httpx.AsyncClient, loc: dict[str, Any], days: list[date]) -> dict[str, str]:
        cc = loc.get("country_code")
        if not cc:
            return {}
        out: dict[str, str] = {}
        try:
            for year in sorted({d.year for d in days}):
                for h in await clients.holidays(http, year, cc):
                    if h.get("global", True):
                        out[h["date"]] = h["name"]
        except clients.UpstreamError:
            return {}
        return out

    async def _alerts(http: httpx.AsyncClient, loc: dict[str, Any]) -> list[dict[str, Any]]:
        if loc.get("country_code") != "US":
            return []
        try:
            return await clients.nws_alerts(http, loc["latitude"], loc["longitude"])
        except clients.UpstreamError:
            return []

    def _check_duration(duration_hours: int) -> None:
        if not MIN_DURATION <= duration_hours <= MAX_DURATION:
            raise ValueError(
                f"I can plan outings from {MIN_DURATION} to {MAX_DURATION} hours long. "
                f"How many hours would you like?"
            )

    def _where(loc: dict[str, Any]) -> str:
        """Name to speak: the full label when the name is ambiguous, else the short name."""
        return loc.get("label", loc["name"]) if (loc.get("alternatives") or loc.get("qualified")) else loc["name"]

    def _place_notes(loc: dict[str, Any]) -> str:
        notes = ""
        if loc.get("alternatives"):
            notes += f" I picked {loc['label']}; say {loc['alternatives'][0]} if you meant that one."
        if loc.get("shadows_city"):
            notes += f" I used your saved place {loc['nickname']}, not the city with that name."
        return notes

    def _err(msg: str) -> dict[str, Any]:
        return {"ok": False, "speech": msg, "card": {"title": "Outing Copilot", "text": msg}}

    @mcp.tool(annotations=READ_ONLY)
    async def find_best_time(place: str, activity: str = "walk", day: str = "today", duration_hours: int = 1) -> dict[str, Any]:
        """Find the best daylight window for an outdoor activity.

        Combines hourly forecast, air quality, active weather alerts and public holidays.
        place: city name or a saved nickname like 'home'. activity: walk, run, bike, picnic,
        playground or dog_walk. day: today, tomorrow, weekend, a weekday name, or YYYY-MM-DD.
        """
        try:
            _check_duration(duration_hours)
            act = resolve_activity(activity)
            async with clients.make_http_client(transport) as http:
                loc = await _locate(http, place)
                fc, air = await _context(http, loc)
                today = date.fromisoformat(fc["hourly"]["time"][0][:10])
                days = resolve_day(day, today)
                hol, alerts = await asyncio.gather(_holidays(http, loc, days), _alerts(http, loc))
        except (ValueError, clients.UpstreamError) as exc:
            return _err(str(exc))

        sensitive = bool(store.prefs().get("sensitive_to_air"))
        hours = _drop_past(score_hours(act, fc, air, sensitive_to_air=sensitive), fc)
        wins = [(d, best_window(hours, d, duration_hours)) for d in days]
        wins = [(d, w) for d, w in wins if w]
        if not wins:
            return _err("That day is outside my 7-day forecast window, or there's no daylight left today.")
        d, w = max(wins, key=lambda x: x[1].score)
        reasons = [r for r in _dedupe([r for hs in w.hours for r in hs.reasons]) if r != "air quality unknown"]  # spoken separately below
        tips = gear_tips(w)
        dayname = "today" if d == today else ("tomorrow" if (d - today).days == 1 else "on " + d.strftime("%A"))
        verdict = w.verdict()
        lead = {"go": "Good news", "maybe": "It's doable", "skip": "Honestly, I'd skip it"}[verdict]
        speech = f"{lead}: the best time for a {act.label} in {_where(loc)} {dayname} is {fmt_time(w.start)} to {fmt_time(w.end)}."
        if reasons:
            speech += " Watch out for " + ", ".join(reasons[:2]) + "."
        if tips:
            speech += " Tip: " + tips[0] + "."
        if w.aqi_unknown and sensitive:
            speech += " Heads up: air-quality data isn't available that far out, so I've docked that time slot."
        if alerts:
            speech += f" There's an active {alerts[0]['event']} for this area."
        if d.isoformat() in hol:
            speech += f" It's {hol[d.isoformat()]}, so parks may be busy."
        speech += _place_notes(loc)
        return {
            "ok": True,
            "speech": speech,
            "verdict": verdict,
            "score": round(w.score),
            "place": loc,
            "activity": act.key,
            "day": d.isoformat(),
            "window": {"start": w.start.isoformat(), "end": w.end.isoformat()},
            "concerns": reasons,
            "gear_tips": tips,
            "alerts": alerts,
            "holiday": hol.get(d.isoformat()),
            "air_quality": "unknown" if w.aqi_unknown else "known",
            "card": {
                "title": f"{act.label.title()} · {loc['name']} · {d.strftime('%a %b %d')}",
                "text": f"{fmt_time(w.start)}–{fmt_time(w.end)} · score {round(w.score)}/100 · {verdict.upper()}",
            },
            "sources": ["Open-Meteo Geocoding", "Open-Meteo Forecast", "Open-Meteo Air Quality", "Nager.Date", "api.weather.gov"],
        }

    @mcp.tool(annotations=READ_ONLY)
    async def week_outlook(place: str, activity: str = "walk", duration_hours: int = 1) -> dict[str, Any]:
        """Rank the next 7 days for an activity and return the best day with its best window."""
        try:
            _check_duration(duration_hours)
            act = resolve_activity(activity)
            async with clients.make_http_client(transport) as http:
                loc = await _locate(http, place)
                fc, air = await _context(http, loc)
                days = [date.fromisoformat(x) for x in fc["daily"]["time"]]
                hol = await _holidays(http, loc, days)
        except (ValueError, clients.UpstreamError) as exc:
            return _err(str(exc))
        sensitive = bool(store.prefs().get("sensitive_to_air"))
        hours = _drop_past(score_hours(act, fc, air, sensitive_to_air=sensitive), fc)
        ranked = []
        for d in days:
            w = best_window(hours, d, duration_hours)
            if w:
                ranked.append({
                    "day": d.isoformat(), "weekday": d.strftime("%A"), "score": round(w.score),
                    "verdict": w.verdict(), "start": w.start.isoformat(), "end": w.end.isoformat(),
                    "holiday": hol.get(d.isoformat()),
                    "air_quality": "unknown" if w.aqi_unknown else "known",
                })
        if not ranked:
            return _err("I couldn't build a weekly outlook for that place.")
        best = max(ranked, key=lambda r: r["score"])
        from datetime import datetime as _dt
        bname = "today" if best["day"] == ranked[0]["day"] else best["weekday"]
        speech = (
            f"For a {act.label} in {_where(loc)}, {bname} looks best, around "
            f"{fmt_time(_dt.fromisoformat(best['start']))}."
        )
        worst = min(ranked, key=lambda r: r["score"])
        if worst["score"] < 50:
            speech += f" Avoid {worst['weekday']}."
        unknown = [r["weekday"] for r in ranked if r["air_quality"] == "unknown"]
        if unknown and sensitive:
            listed = unknown[0] if len(unknown) == 1 else ", ".join(unknown[:-1]) + " and " + unknown[-1]
            speech += f" Heads up: air-quality data isn't available that far out for {listed}, so I've docked those days."
        speech += _place_notes(loc)
        return {"ok": True, "speech": speech, "place": loc, "activity": act.key, "best": best, "days": ranked,
                "card": {"title": f"{act.label.title()} week · {loc['name']}",
                         "text": " | ".join(f"{r['weekday'][:3]} {r['score']}" for r in ranked)}}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True, openWorldHint=True))
    async def remember_place(nickname: str, place: str) -> dict[str, Any]:
        """Save a place under a nickname (e.g. 'home', 'the office', 'grandma') for later requests."""
        nickname = (nickname or "").strip()
        if not nickname:
            return _err("What should I call this place? Please give it a short name, like home or work.")
        try:
            async with clients.make_http_client(transport) as http:
                loc, same_name = await asyncio.gather(clients.geocode(http, place), clients.geocode(http, nickname))
        except clients.UpstreamError as exc:
            return _err(str(exc))
        if not loc:
            return _err(f"I couldn't find a place called '{place}'.")
        # Only warn for real, sizeable places with exactly that name (not hamlets or fuzzy matches).
        shadows = bool(
            same_name
            and same_name["name"].lower() == nickname.lower()
            and (same_name.get("population") or 0) >= clients.AMBIGUOUS_MIN_POPULATION
        )
        store.save_place(nickname, {**loc, "shadows_city": shadows})
        msg = f"Got it. I'll remember {nickname} as {loc['label']}."
        if loc.get("alternatives"):
            msg += f" If you meant {loc['alternatives'][0]} instead, tell me."
        if shadows:
            msg += (f" Heads up: {same_name['label']} is also a real place. When you say {nickname}, "
                    f"I'll use your saved place, {loc['label']}.")
        return {"ok": True, "speech": msg, "nickname": nickname.lower(), "place": loc,
                "card": {"title": "Place saved", "text": msg}}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def list_saved_places() -> dict[str, Any]:
        """List the nicknamed places the household has saved."""
        p = store.places()
        names = ", ".join(p) if p else "none yet"
        return {"ok": True, "speech": f"Your saved places: {names}.", "places": p}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True))
    def set_preferences(sensitive_to_air: bool | None = None, default_activity: str | None = None) -> dict[str, Any]:
        """Set household preferences. sensitive_to_air=True (asthma, kids, seniors) uses a stricter AQI limit of 50."""
        if default_activity is not None:
            try:
                default_activity = resolve_activity(default_activity).key
            except ValueError as exc:
                return _err(str(exc))
        prefs = store.set_prefs(sensitive_to_air=sensitive_to_air, default_activity=default_activity)
        return {"ok": True, "speech": "Preferences updated.", "prefs": prefs}

    @mcp.resource("outing://activities")
    def activities() -> str:
        """Supported activities and their comfort ranges."""
        return "\n".join(f"{a.key}: {a.comfort_low_f}-{a.comfort_high_f}°F, max wind {a.max_wind_mph} mph" for a in ACTIVITIES.values())

    return mcp


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the Outing Copilot MCP server over Streamable HTTP")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    import os
    fixed = os.environ.get("OUTING_NOW")  # e.g. 2026-10-14T16:00:00+00:00, used by the offline demo
    clock = (lambda: datetime.fromisoformat(fixed)) if fixed else None
    create_server(now=clock).run("streamable-http", host=a.host, port=a.port)


if __name__ == "__main__":
    main()
