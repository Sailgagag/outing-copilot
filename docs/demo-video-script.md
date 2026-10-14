# Demo video script (target 2:45, hard limit < 3:00)

Format: screen recording + voice-over in English. No third-party music; no Amazon logos beyond
naming the track in text. Record at 1080p. Upload as Public to YouTube or Vimeo.

| # | Time | Screen | Voice-over |
|---|---|---|---|
| 1 | 0:00–0:15 | Title card: "Outing Copilot — an MCP server for Alexa+". Subtitle: "Alexa+ track · MCP 2025-11-25 · Streamable HTTP". | "Every day, millions of people ask a voice assistant about the weather. But what they actually want to know is: should I go out, and when? Outing Copilot answers that." |
| 2 | 0:15–0:35 | Slide: the five services in a row (Geocoding → Forecast + Air Quality → Holidays → NWS Alerts) with arrows into one "decision" box. | "It's a self-hosted MCP server. For each question it chains five free public services — location, hourly forecast, air quality, public holidays and official weather alerts — and turns them into one decision: the best window, a go, maybe or skip verdict, and what to bring." |
| 3 | 0:35–0:55 | Terminal: `outing-copilot --port 8765` starting. Then the curl initialize call showing `"protocolVersion":"2025-11-25"`. | "It runs over Streamable HTTP on the official MCP Python SDK. Here it negotiates spec version 2025-11-25." |
| 4 | 0:55–1:10 | Terminal: `python demo/alexa_sim.py`. Show the "connected … tools: …" lines. | "This is a simulated Alexa+ session. A real MCP client connects to the server and the household starts talking." |
| 5 | 1:10–1:25 | Highlight turn 1: "remember home as Seattle" → reply. | "First, it learns where home is. That's saved, so it still knows next week." |
| 6 | 1:25–1:45 | Highlight turn 2: dog walk today → "9 AM to 10 AM … GO" and the card line. | "'When's the best time to walk the dog?' It scores every daylight hour for that activity — dogs don't mind a drizzle, picnics do — and answers in one sentence, plus a card for screen devices." |
| 7 | 1:45–2:05 | Highlight turns 3–4: asthma preference → weekend picnic, "Saturday 3 to 5 PM … feels like 55°F (chilly)". | "Tell it someone in the family has asthma, and it uses a stricter air-quality limit from then on. Ask about a two-hour picnic this weekend, and it compares Saturday and Sunday and warns you it'll be chilly." |
| 8 | 2:05–2:20 | Highlight turn 5: week outlook card "Wed 90 | Thu 90 | … Sun 100". | "Or plan ahead: it ranks the whole week for a run." |
| 9 | 2:20–2:35 | Editor: `tests/` folder, then `pytest -q` → "16 passed". | "Everything is tested offline against recorded API responses, including weather alerts and errors like unknown places." |
| 10 | 2:35–2:48 | Closing card: repo URL, "MIT licensed · no API keys". | "Outing Copilot: from forecast to decision. The code is open source, and it needs no API keys. Thanks for watching." |

Notes for recording
- Use `python demo/alexa_sim.py --offline` if the network is slow; the output matches the script's
  numbers. If you record live, the times and scores will differ — update the voice-over lines 6–8.
- Keep the terminal font large (≥ 18 pt).
