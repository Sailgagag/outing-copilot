"""Pure, network-free scoring logic. Easy to unit test."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class Activity:
    key: str
    label: str
    comfort_low_f: float
    comfort_high_f: float
    max_wind_mph: float
    rain_tolerance: float  # 0..1, higher = cares less about rain
    uv_sensitive: bool = True


ACTIVITIES: dict[str, Activity] = {
    "walk": Activity("walk", "walk", 45, 82, 22, 0.5),
    "run": Activity("run", "run", 38, 72, 20, 0.6),
    "bike": Activity("bike", "bike ride", 50, 85, 15, 0.3),
    "picnic": Activity("picnic", "picnic", 60, 85, 12, 0.1),
    "playground": Activity("playground", "playground trip", 50, 86, 18, 0.2),
    "dog_walk": Activity("dog_walk", "dog walk", 35, 80, 25, 0.7, uv_sensitive=False),
}

ALIASES = {
    "walking": "walk", "hike": "walk", "hiking": "walk", "stroll": "walk",
    "running": "run", "jog": "run", "jogging": "run",
    "biking": "bike", "cycling": "bike", "cycle": "bike",
    "park": "playground", "kids": "playground",
    "dog": "dog_walk", "walk the dog": "dog_walk", "dog walk": "dog_walk",
}


def resolve_activity(name: str) -> Activity:
    k = (name or "walk").strip().lower()
    k = ALIASES.get(k, k).replace(" ", "_")
    if k not in ACTIVITIES:
        raise ValueError(f"Unknown activity '{name}'. Try one of: {', '.join(ACTIVITIES)}")
    return ACTIVITIES[k]


@dataclass
class HourScore:
    time: datetime
    score: float  # 0..100
    reasons: list[str] = field(default_factory=list)
    temp_f: float | None = None
    rain_pct: float | None = None
    wind_mph: float | None = None
    uv: float | None = None
    aqi: float | None = None


def score_hour(
    act: Activity,
    *,
    feels_f: float | None,
    rain_pct: float | None,
    wind_mph: float | None,
    uv: float | None,
    aqi: float | None,
    sensitive_to_air: bool = False,
) -> tuple[float, list[str]]:
    s = 100.0
    why: list[str] = []
    if rain_pct is not None and rain_pct > 10:
        p = (rain_pct - 10) * (1.0 - act.rain_tolerance) * 1.1
        s -= p
        if rain_pct >= 40:
            why.append(f"{rain_pct:.0f}% chance of rain")
    if feels_f is not None:
        if feels_f < act.comfort_low_f:
            s -= (act.comfort_low_f - feels_f) * 3.0
            why.append(f"feels like {feels_f:.0f}°F (chilly)")
        elif feels_f > act.comfort_high_f:
            s -= (feels_f - act.comfort_high_f) * 2.5
            why.append(f"feels like {feels_f:.0f}°F (hot)")
    if wind_mph is not None and wind_mph > act.max_wind_mph:
        s -= (wind_mph - act.max_wind_mph) * 3
        why.append(f"wind {wind_mph:.0f} mph")
    if act.uv_sensitive and uv is not None and uv >= 7:
        s -= (uv - 6) * 4
        why.append(f"UV index {uv:.0f}")
    if aqi is not None:
        limit = 50 if sensitive_to_air else 100
        if aqi > limit:
            s -= (aqi - limit) * 0.8
            why.append(f"air quality AQI {aqi:.0f}")
    return max(0.0, min(100.0, s)), why


def _idx(times: list[str]) -> dict[str, int]:
    return {t: i for i, t in enumerate(times)}


def score_hours(
    act: Activity,
    forecast: dict[str, Any],
    air: dict[str, Any] | None,
    *,
    sensitive_to_air: bool = False,
) -> list[HourScore]:
    """Score every daylight hour in the forecast."""
    h = forecast["hourly"]
    aqi_by_time: dict[str, float | None] = {}
    if air and "hourly" in air:
        for t, v in zip(air["hourly"]["time"], air["hourly"].get("us_aqi", [])):
            aqi_by_time[t] = v
    daylight: dict[str, tuple[datetime, datetime]] = {}
    d = forecast.get("daily", {})
    for day, rise, sset in zip(d.get("time", []), d.get("sunrise", []), d.get("sunset", [])):
        daylight[day] = (datetime.fromisoformat(rise), datetime.fromisoformat(sset))

    out: list[HourScore] = []
    for i, t in enumerate(h["time"]):
        ts = datetime.fromisoformat(t)
        win = daylight.get(ts.date().isoformat())
        if win and not (win[0] - timedelta(minutes=30) <= ts <= win[1] - timedelta(minutes=30)):
            continue
        get = lambda k: (h.get(k) or [None] * len(h["time"]))[i]  # noqa: E731
        feels = get("apparent_temperature")
        if feels is None:
            feels = get("temperature_2m")
        score, why = score_hour(
            act,
            feels_f=feels,
            rain_pct=get("precipitation_probability"),
            wind_mph=get("wind_speed_10m"),
            uv=get("uv_index"),
            aqi=aqi_by_time.get(t),
            sensitive_to_air=sensitive_to_air,
        )
        out.append(
            HourScore(ts, score, why, feels, get("precipitation_probability"), get("wind_speed_10m"),
                      get("uv_index"), aqi_by_time.get(t))
        )
    return out


@dataclass
class Window:
    start: datetime
    end: datetime
    score: float
    hours: list[HourScore]

    def verdict(self) -> str:
        if self.score >= 75:
            return "go"
        if self.score >= 50:
            return "maybe"
        return "skip"


def best_window(hours: list[HourScore], day: date, duration: int) -> Window | None:
    todays = [x for x in hours if x.time.date() == day]
    if not todays:
        return None
    duration = max(1, min(duration, len(todays)))
    best: Window | None = None
    for i in range(len(todays) - duration + 1):
        chunk = todays[i : i + duration]
        # require contiguous hours
        if (chunk[-1].time - chunk[0].time) != timedelta(hours=duration - 1):
            continue
        avg = sum(c.score for c in chunk) / duration
        if best is None or avg > best.score:
            best = Window(chunk[0].time, chunk[-1].time + timedelta(hours=1), avg, chunk)
    return best


def gear_tips(window: Window) -> list[str]:
    tips: list[str] = []
    hs = window.hours
    if any((x.rain_pct or 0) >= 30 for x in hs):
        tips.append("bring a rain jacket or umbrella")
    if any((x.temp_f or 99) < 50 for x in hs):
        tips.append("wear a warm layer")
    if any((x.temp_f or 0) > 85 for x in hs):
        tips.append("bring extra water")
    if any((x.uv or 0) >= 6 for x in hs):
        tips.append("put on sunscreen")
    if any((x.aqi or 0) > 100 for x in hs):
        tips.append("consider a mask; air quality is poor")
    return tips


def fmt_time(dt: datetime) -> str:
    h = dt.hour % 12 or 12
    return f"{h}{'' if dt.minute == 0 else f':{dt.minute:02d}'} {'AM' if dt.hour < 12 else 'PM'}"


def resolve_day(spec: str, today: date) -> list[date]:
    s = (spec or "today").strip().lower()
    if s == "today":
        return [today]
    if s == "tomorrow":
        return [today + timedelta(days=1)]
    if s in ("weekend", "this weekend"):
        sat = today + timedelta(days=(5 - today.weekday()) % 7)
        days = [sat, sat + timedelta(days=1)]
        if today.weekday() == 6:
            days = [today]
        return days
    names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if s in names:
        return [today + timedelta(days=(names.index(s) - today.weekday()) % 7)]
    try:
        return [date.fromisoformat(s)]
    except ValueError as exc:
        raise ValueError(f"I didn't understand the day '{spec}'. Use today, tomorrow, weekend, a weekday, or YYYY-MM-DD.") from exc
