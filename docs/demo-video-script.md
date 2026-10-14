# Demo video script (≈2:13, hard limit < 2:55)

Format: screen frames rendered from real captured output + English voice-over (edge-tts) with
burned-in subtitles. Built by `video/build.py` from `video/raw/` (live public APIs, MCP 2025-11-25).

| # | Screen | Voice-over |
|---|---|---|
| 1 | Title card: "Outing Copilot" / "an MCP server for Alexa+". Subtitle: "Alexa+ track · MCP 2025-11-25 · Streamable HTTP". | "Every day, millions of people ask a voice assistant about the weather. But what they actually want to know is: should I go out, and when? Outing Copilot answers that." |
| 2 | Five services (Geocoding, Forecast, Air Quality, Holidays, NWS Alerts) → one decision box. | "It's a self-hosted MCP server. For each question it chains five free public services: location, hourly forecast, air quality, public holidays and official weather alerts. And it turns them into one decision: the best window, a go, maybe or skip verdict, and what to bring." |
| 3 | `outing-copilot --port 8765`, then curl initialize → `"protocolVersion": "2025-11-25"`. | "It runs over Streamable HTTP on the official MCP Python SDK. Here it negotiates spec version 2025-11-25." |
| 4 | `python demo/alexa_sim.py` → connected, protocol 2025-11-25, tool list. | "This is a simulated Alexa+ session. A real MCP client connects to the server, and the household starts talking." |
| 5 | Turn 1: remember home as Seattle. | "First, it learns where home is. That's saved, so it still knows next week." |
| 6 | Turn 2: dog walk today → "8 AM to 9 AM", card score 100/100 GO; then `scoring.py` daylight-only window code. | "When's the best time to walk the dog? It only looks at hours that start after sunrise and end by sunset, and scores each one for that activity. Dogs don't mind a drizzle, picnics do. The answer: 8 to 9 AM, in one sentence, plus a card for screen devices." |
| 7 | Turns 3–4: asthma → Saturday 3–5 PM picnic, "feels like 55°F (chilly)", score 76/100. | "Tell it someone in the family has asthma, and it uses a stricter air-quality limit from then on. Ask about a two-hour picnic this weekend, and it compares Saturday and Sunday, and warns you it'll be chilly." |
| 8 | Turn 5: run week "Wed 94 \| Thu 91 \| Fri 94 \| Sat 95 \| Sun 98 \| Mon 81 \| Tue 85" and the spoken note; then `scoring.py` unknown-AQI rule. | "Or plan ahead: it ranks the whole week for a run, and Sunday wins with 98. It's upfront about gaps, too: 'Heads up: air-quality data isn't available that far out, so I've docked those days.' It knows what it doesn't know." |
| 9 | Turn 6: Portland → "Portland, Oregon tomorrow is 10 AM to 11 AM. I picked Portland, Oregon; say Portland, Maine if you meant that one." | "Some city names are ambiguous. Ask about Portland, and it tells you which one it picked, Portland, Oregon, with a 10 to 11 AM walk tomorrow, and how to switch if you meant Portland, Maine." |
| 10 | Per-file test counts, fixtures, `pytest -q` → "47 passed". | "All 47 tests pass, offline, against recorded API responses, including weather alerts, missing air-quality data, ambiguous places and upstream errors." |
| 11 | Closing card: github.com/Sailgagag/outing-copilot · MIT licensed · no API keys. | "Outing Copilot: from forecast to decision. The code is open source, and it needs no API keys. Thanks for watching." |

Notes
- Numbers come from a live run captured in `video/raw/sim.txt`; `build.py` refuses to build if any
  spoken number is missing from that capture. If you re-record live, times and scores may differ.
- `python demo/alexa_sim.py --offline` replays fixtures (Portland then reuses the Seattle forecast,
  so record the video live).
