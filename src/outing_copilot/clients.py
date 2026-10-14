"""Thin async clients for free, key-less public APIs.

Every request goes through one ``httpx.AsyncClient`` so tests (and the offline
demo) can swap in a fixture-backed ``httpx.MockTransport``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

# api.weather.gov requires an identifying User-Agent with contact details.
USER_AGENT = "outing-copilot (+https://github.com/Sailgagag/outing-copilot; https://github.com/Sailgagag/outing-copilot/issues)"

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
HOLIDAY_URL = "https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active"


class UpstreamError(RuntimeError):
    """Raised when a public API fails. ``str()`` is a sentence safe to speak; details stay in ``detail``."""

    def __init__(self, detail: str):
        super().__init__("I couldn't reach the weather service just now. Please try again in a minute.")
        self.detail = detail


def fixture_transport(fixture_dir: str | Path) -> httpx.MockTransport:
    """Serve recorded JSON instead of hitting the network.

    Routing is by host (+ a path hint for holidays). Unknown places return the
    geocoder's empty result so "place not found" can be tested.
    """
    d = Path(fixture_dir)

    def load(name: str) -> Any:
        return json.loads((d / name).read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "geocoding-api.open-meteo.com":
            name = request.url.params.get("name", "").lower()
            for city in ("seattle", "portland", "paris"):
                if city in name:
                    return httpx.Response(200, json=load(f"geocode_{city}.json"))
            return httpx.Response(200, json={"generationtime_ms": 0.1})
        if host == "api.open-meteo.com":
            return httpx.Response(200, json=load("forecast_seattle.json"))
        if host == "air-quality-api.open-meteo.com":
            return httpx.Response(200, json=load("airquality_seattle.json"))
        if host == "date.nager.at":
            return httpx.Response(200, json=load("holidays_us_2026.json"))
        if host == "api.weather.gov":
            alerts = os.environ.get("OUTING_ALERTS_FIXTURE", "alerts_seattle.json")
            return httpx.Response(200, json=load(alerts))
        return httpx.Response(404, json={"error": f"no fixture for {host}"})

    return httpx.MockTransport(handler)


def make_http_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    if transport is None and os.environ.get("OUTING_FIXTURE_DIR"):
        transport = fixture_transport(os.environ["OUTING_FIXTURE_DIR"])
    return httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(10.0),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )


async def _get(
    http: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
) -> Any:
    last: Exception | None = None
    for _attempt in range(2):  # one retry for transient network/TLS hiccups
        try:
            r = await http.get(url, params=params, headers=headers)
            if r.status_code >= 500:
                r.raise_for_status()
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            last = exc
            if exc.response.status_code < 500:
                break
        except (httpx.HTTPError, ValueError) as exc:
            last = exc
    raise UpstreamError(f"{url} failed: {last}") from last


# Another same-named place this big makes the name worth disambiguating out loud.
AMBIGUOUS_MIN_POPULATION = 20_000


def _label(r: dict[str, Any]) -> str:
    """'Portland, Oregon' for US places, 'Paris, France' elsewhere."""
    if r.get("country_code") == "US" and r.get("admin1"):
        return f"{r['name']}, {r['admin1']}"
    return f"{r['name']}, {r.get('country') or r.get('country_code') or ''}".rstrip(", ")


def _matches(r: dict[str, Any], qualifier: str) -> bool:
    q = qualifier.strip().lower()
    return any(q == (r.get(k) or "").lower() for k in ("admin1", "country", "country_code"))


async def geocode(http: httpx.AsyncClient, place: str) -> dict[str, Any] | None:
    """Resolve a place name. Accepts 'Portland' or 'Portland, Maine'.

    The result carries a spoken ``label`` and, if other sizeable places share the
    name, ``alternatives`` (their labels) so the assistant can say which one it used.
    """
    name, _, qualifier = place.partition(",")
    data = await _get(http, GEOCODE_URL, {"name": name.strip(), "count": 5, "language": "en", "format": "json"})
    results = data.get("results") or []
    if qualifier.strip():
        results = [r for r in results if _matches(r, qualifier)]
    if not results:
        return None
    r = results[0]
    alternatives = [
        _label(o) for o in results[1:]
        if o["name"].lower() == r["name"].lower() and (o.get("population") or 0) >= AMBIGUOUS_MIN_POPULATION
    ] if not qualifier.strip() else []
    return {
        "name": r["name"],
        "region": r.get("admin1"),
        "country_code": r.get("country_code"),
        "label": _label(r),
        "alternatives": alternatives,
        "qualified": bool(qualifier.strip()),
        "population": r.get("population"),
        "latitude": r["latitude"],
        "longitude": r["longitude"],
        "timezone": r.get("timezone", "auto"),
    }


async def forecast(http: httpx.AsyncClient, lat: float, lon: float, days: int = 7) -> dict[str, Any]:
    return await _get(
        http,
        FORECAST_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m,apparent_temperature,precipitation_probability,precipitation,"
            "wind_speed_10m,uv_index,weather_code",
            "daily": "sunrise,sunset",
            "timezone": "auto",
            "forecast_days": days,
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
        },
    )


# Open-Meteo Air Quality accepts forecast_days 0..7 (8 is rejected), but measured on 2026-10-14
# it only fills us_aqi for roughly the first 4.8 days; later hours come back as null.
# We request all 7 days to line up with the weather forecast and treat nulls as "unknown".
AIR_FORECAST_DAYS = 7


async def air_quality(http: httpx.AsyncClient, lat: float, lon: float) -> dict[str, Any]:
    return await _get(
        http,
        AIR_URL,
        {"latitude": lat, "longitude": lon, "hourly": "us_aqi,pm2_5", "timezone": "auto",
         "forecast_days": AIR_FORECAST_DAYS},
    )


async def holidays(http: httpx.AsyncClient, year: int, country: str) -> list[dict[str, Any]]:
    return await _get(http, HOLIDAY_URL.format(year=year, country=country.upper()))


async def nws_alerts(http: httpx.AsyncClient, lat: float, lon: float) -> list[dict[str, Any]]:
    """Active US National Weather Service alerts (US locations only)."""
    data = await _get(
        http,
        NWS_ALERTS_URL,
        {"point": f"{lat:.4f},{lon:.4f}"},
        headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"},
    )
    out = []
    for f in data.get("features", []):
        p = f.get("properties", {})
        out.append(
            {
                "event": p.get("event"),
                "severity": p.get("severity"),
                "headline": p.get("headline"),
                "ends": p.get("ends") or p.get("expires"),
            }
        )
    return out
