# Design notes: picking the idea

## What the judges reward (from the Official Rules, section 6)

Four equally weighted criteria: Tech Implementation, Design, Potential Impact, Quality of the Idea.
For Alexa+ the rules call out "basic MCP wrapper around an existing API" and "single-turn Q&A bot"
as *obvious*, and "agentic workflow that orchestrates across services", "context-aware add-on that
maintains state across sessions" and "media support (cards...)" as *creative*. Friction-log entries
can add up to a 10% bonus.

Constraints we set ourselves: only free, key-less public APIs; nothing that needs hardware;
buildable and testable well before 2026-10-23 12:00 PT.

## Candidates

| | A. Outing Copilot | B. Household Safety Briefing | C. Pantry-to-Plate |
|---|---|---|---|
| Pitch | "When's the best time to walk the dog / go for a run / picnic?" | Morning brief: weather alerts, earthquakes, air quality, pollen | "What can I cook with eggs and spinach that's nut-free?" |
| Services (key-less) | Open-Meteo geocode + forecast + air quality, Nager.Date, NWS alerts | NWS, USGS earthquakes, Open-Meteo AQ | TheMealDB, Open Food Facts |
| Orchestration | 5 services, combined into one decision | 3–4 services, mostly listed side by side | 2 services, mostly lookups |
| Value for an Alexa+ household | Daily, recurring, very voice-native question | High, but mostly read-out of existing alerts | Medium; recipes need screens; TheMealDB catalogue is small |
| "Obvious wrapper" risk | Low: it returns a decision (window + verdict + gear), not raw data | Medium: risks looking like an alert relay | High |
| State across sessions | Saved places, household air sensitivity | Saved address | Saved allergens |
| Key-less risk | Low (all verified working 2026-10-14) | Low | Open Food Facts rate limits |

## Decision: A, Outing Copilot

- It fits the "orchestrates across services" and "state across sessions" examples directly.
- The output is a decision written for voice (`speech`) plus a `card` for Echo Show-style screens.
- It's genuinely useful daily (dog owners, runners, parents) and easy to show in a 3-minute video.
- Everything can be tested offline with recorded fixtures.

## Architecture

```
Alexa+ (or the demo client) --Streamable HTTP /mcp--> MCPServer (mcp 2.3.0)
   find_best_time / week_outlook
      -> geocode (or saved nickname)
      -> forecast  ┐ parallel
      -> air quality┘
      -> holidays + NWS alerts (parallel)
      -> scoring.py: per-hour 0-100 score per activity, daylight only, future hours only
      -> best contiguous window, verdict, concerns, gear tips
      -> {speech, card, structured data, sources}
```

## Possible next steps (not built)

- Optional AWS Builder mini-challenge: deploy on AWS (e.g. AgentCore Runtime or Lambda) — needs an
  AWS account, so it's left to the entrant.
- MCP Apps / richer cards; proactive "rain starts in 20 minutes" notifications.
- Pollen data (Open-Meteo has a European pollen feed only).
