# Outing Copilot — an MCP server for Alexa+

> "Alexa, when's the best time to walk the dog today?"

Outing Copilot is a self-hosted **MCP server (Streamable HTTP)** that answers the most common
household weather question with a decision instead of a forecast: *when* to go, *whether* to go,
and *what to bring*, for a specific activity.

Each request chains **five free, key-less public services**:

| Step | Service | Used for |
|---|---|---|
| 1 | [Open-Meteo Geocoding](https://open-meteo.com/en/docs/geocoding-api) | place name → coordinates, timezone, country |
| 2 | [Open-Meteo Forecast](https://open-meteo.com/en/docs) | hourly feels-like temp, rain chance, wind, UV, sunrise/sunset |
| 3 | [Open-Meteo Air Quality](https://open-meteo.com/en/docs/air-quality-api) | hourly US AQI |
| 4 | [Nager.Date](https://date.nager.at/) | public holidays ("parks may be busy") |
| 5 | [api.weather.gov](https://www.weather.gov/documentation/services-web-api) | active NWS alerts (US locations) |

No API keys, no accounts, no secrets in this repo.

## Tools

| Tool | What it does |
|---|---|
| `find_best_time(place, activity, day, duration_hours)` | Best daylight window, verdict (go / maybe / skip), concerns, gear tips, alerts, holiday |
| `week_outlook(place, activity, duration_hours)` | Ranks the next 7 days and picks the best one |
| `remember_place(nickname, place)` | Saves "home", "grandma", etc. — persists across sessions |
| `list_saved_places()` | Lists saved places |
| `set_preferences(sensitive_to_air, default_activity)` | e.g. asthma in the household → stricter AQI limit (50 instead of 100) |

Activities: `walk`, `run`, `bike`, `picnic`, `playground`, `dog_walk` (with aliases like "jogging",
"cycling"). Every result carries a short `speech` string written to be spoken and a `card` for
screen devices.

## Protocol

Built on the official MCP Python SDK (`mcp==2.3.0`), served over **Streamable HTTP** at `/mcp`.
The server negotiates **2025-11-25** with handshake-era clients and 2026-07-28 with newer ones:

```bash
curl -s -X POST http://127.0.0.1:8765/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
```

## Run

```bash
outing-copilot --port 8765        # MCP endpoint: http://127.0.0.1:8765/mcp
```

State (saved places, preferences) lives in `~/.outing-copilot/state.json`; override with
`OUTING_STATE_FILE`.

## Demo: simulated Alexa+ conversation

```bash
python demo/alexa_sim.py            # live public APIs
python demo/alexa_sim.py --offline  # recorded fixtures, no network
```

The demo launches the server as its own process, connects with the official MCP client over
Streamable HTTP, and plays a short household conversation. The utterance → tool mapping in the demo
is a hard-coded stand-in for the Alexa+ LLM; every answer comes from the server.

## Tests

```bash
pytest -q
```

All upstream HTTP is served from `tests/fixtures/` (real responses recorded on 2026-10-14, plus one
clearly-marked synthetic NWS alert), so tests are offline and deterministic.

## Layout

```
src/outing_copilot/
  clients.py   # public API clients + fixture transport
  scoring.py   # pure scoring: activities, hourly scores, best window, gear tips
  store.py     # JSON persistence for places and preferences
  server.py    # MCP tools, Streamable HTTP entry point
demo/alexa_sim.py
tests/
docs/          # design notes, demo video script, Devpost draft
```

## Data & attribution

Weather and air-quality data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0). Holidays by
Nager.Date. Alerts by the US National Weather Service. This is an independent project and isn't
affiliated with or endorsed by Amazon or these providers.

## License

MIT
