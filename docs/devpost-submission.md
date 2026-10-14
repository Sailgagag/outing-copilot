# Devpost submission draft (do not submit until reviewed)

**Project name:** Outing Copilot

**Tagline:** From forecast to decision — an MCP server that tells Alexa+ households the best time to go outside.

**Primary track:** Alexa+
**Mini challenges:** none by default. (Open Source only if a separate, *additional* repo/PR is
made; AWS Builder only if an AWS service is actually used — see notes at the end.)

**Repository:** https://github.com/Sailgagag/outing-copilot
**Video:** <YouTube/Vimeo public URL>

---

## Inspiration
Most weather questions to a voice assistant are really decisions: *can I walk the dog before it
rains? is the air OK for my kid today? which day this weekend works for a picnic?* A forecast
read-out leaves the user to do the maths. We wanted Alexa+ to just answer.

## What it does
Outing Copilot is a self-hosted MCP server. Ask about an activity — walk, run, bike ride, picnic,
playground trip or dog walk — for a place and a day, and it returns:
- the best daylight window (whole hours between sunrise and sunset, only future hours, 1–6 hours long),
- a verdict: go, maybe, or skip,
- the concerns behind it (rain chance, feels-like temperature, wind, UV, air quality),
- what to bring (rain jacket, warm layer, sunscreen, water, mask),
- any active US National Weather Service alert, and whether it's a public holiday.

Answers come as a one-sentence `speech` field for voice, a `card` for screen devices, and full
structured data. It also remembers things across sessions: nicknamed places ("home", "grandma")
and household preferences such as asthma (which switches to a stricter AQI limit).

It is careful about what it doesn't know. Air-quality forecasts only cover the first four to five
days, so later days are marked unknown; in asthma mode those days are scored cautiously and the
answer says so ("Air-quality data isn't available yet for Monday and Tuesday…"). Ambiguous places
are named out loud ("I picked Portland, Oregon; say Portland, Maine if you meant that one"), and a
nickname that is also a real city triggers a heads-up. Every error — a missing place, an
out-of-range duration, an unknown activity, a service outage — comes back as one speakable sentence.

## How we built it
- Official MCP Python SDK (`mcp` 2.3.0), `MCPServer`, served over Streamable HTTP at `/mcp`.
  Negotiates protocol 2025-11-25 with handshake-era clients (and 2026-07-28 with newer ones).
- Five free, key-less public services per request: Open-Meteo Geocoding, Open-Meteo Forecast,
  Open-Meteo Air Quality, Nager.Date, and api.weather.gov. Forecast and air quality are fetched in
  parallel, then holidays and alerts.
- A pure-Python scoring engine gives every daylight hour a 0–100 score per activity (each activity
  has its own comfort range, wind limit and rain tolerance) and finds the best contiguous window.
- A small JSON store keeps places and preferences between sessions.
- 47 automated tests run fully offline against recorded API responses; a demo script plays a
  simulated Alexa+ conversation through a real MCP client.

## Challenges we ran into
- Air-quality coverage is shorter than the weather forecast. We measured it (the API accepts up to 7
  days but fills AQI for only about 4–5), then treated the gap as "unknown" instead of "clean air".
- Making answers short enough to speak but still explain *why*. We cap each spoken answer at the
  window, the top concerns, one tip, and an alert.
- Not suggesting a time that has already passed: the forecast is in the location's local time, so
  we filter with the location's UTC offset (and made the clock injectable for tests).
- Keeping tests deterministic while using live data: every upstream call goes through one HTTP
  client whose transport can be swapped for recorded fixtures.

## Accomplishments we're proud of
- One question orchestrates five services and comes back as a single decision.
- Zero API keys: anyone can clone it and run it in two commands.

## What we learned
MCP tool design for voice is different from tool design for chat: structured data for the model,
plus a ready-to-speak sentence and a card, works better than raw numbers.

## What's next
- Hosting it publicly so Alexa+ can reach it, with rate limiting and caching.
- Proactive nudges ("rain starts in 20 minutes — head home now").
- Rich visual cards / MCP Apps on Echo Show.

## Built with
python, mcp (Model Context Protocol Python SDK), streamable-http, httpx, open-meteo, nager-date, national-weather-service-api, pytest

## Was this project created or significantly updated during the submission period?
Created from scratch in October 2026, during the submission period.

---

## Product feedback (required)

**Which developer tools, APIs and SDKs did you use, and for what?**
- Model Context Protocol (spec 2025-11-25, docs at modelcontextprotocol.io) and the official MCP
  Python SDK 2.3.0: server (`MCPServer`, tools, resource, Streamable HTTP) and client (`Client`) for
  tests and the demo.
- Open-Meteo (geocoding, forecast, air quality), Nager.Date and api.weather.gov as data sources.

**What worked well?**
- The SDK's in-process `Client(server)` made end-to-end tool tests very quick to write.
- Type hints turned straight into tool input schemas and structured output.
- Streamable HTTP worked out of the box with one `run("streamable-http")` call.

**What needs work?**
- The SDK's 2.x major version renamed `FastMCP` to `MCPServer`. Most tutorials and examples online
  still show the 1.x API, so the first import failed; the error message pointing to the migration
  guide helped.
- The hackathon rules ask for spec 2025-11-25 "or a later version, once confirmed", while the
  current SDK negotiates 2026-07-28 by default with new clients. It wasn't clear which version
  Alexa+ will negotiate; we verified 2025-11-25 with a manual `initialize` call.
- We couldn't find a way to test a self-hosted MCP server against the real Alexa+ without Preview
  access, so we built a simulated client. A public sandbox or test console would help a lot.

**How was your onboarding (zero to hello world)?**
About an hour from `pip install` to a working Streamable HTTP tool, most of it spent on the 1.x→2.x
API differences.

**Would you build with these again?**
Yes — MCP lets one server work across assistants, and Alexa+ is a natural home for short,
decision-style answers. We'd like a way to test against Alexa+ directly.

## Friction log (optional, up to 10% bonus) — FILL IN FROM REAL EXPERIENCE ONLY
| Task | Steps | Expected | Actual | Severity | Workaround | Suggestion |
|---|---|---|---|---|---|---|
| Start an MCP server from a tutorial | `from mcp.server.fastmcp import FastMCP` with mcp 2.3.0 | Import works | `ModuleNotFoundError` pointing to migration guide | Medium | Use `mcp.server.mcpserver.MCPServer` | Link the 2.x quickstart from the hackathon Resources page |
| Confirm required spec version | Connected with the default client | 2025-11-25 | Negotiated 2026-07-28 | Low | Legacy-mode client / manual `initialize` with 2025-11-25 | State which versions Alexa+ accepts |
| Test against Alexa+ | Looked for a way to register a self-hosted MCP server | A test console | None found without Preview access | High | Simulated Alexa+ client | Provide a sandbox endpoint for hackathon entrants |
