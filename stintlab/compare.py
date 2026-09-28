"""Vorjahresvergleich: dasselbe Wochenende ein Jahr früher finden und laden.

Gleiche Strecke = gleiche circuit_key von OpenF1, nicht der Name: 2026 heißt
das Rennen in Sepang „Bahrain Grand Prix“ (circuit_key 12), 2025 war Bahrain
in Sakhir (63) – ein Namensvergleich würde zwei verschiedene Strecken paaren.
Testfahrten (gleiche circuit_key wie das Rennen) und abgesagte Wochenenden
zählen nicht.

Benutzt von weekend.py (Qualifying: Vergleichs-Reel automatisch) und
fetch_compare.py (von Hand).
"""

from __future__ import annotations

from stintlab import openf1
from stintlab.session import load_session


def previous_edition(meeting: dict, refresh: bool = False) -> dict | None:
    """Das Wochenende auf derselben Strecke im Vorjahr – oder None."""
    year = int(meeting.get("year") or str(meeting.get("date_start", ""))[:4])
    try:
        previous = openf1.meetings_of(year - 1, refresh)
    except Exception:
        return None
    hits = [m for m in previous
            if m.get("circuit_key") == meeting.get("circuit_key") and not m.get("is_cancelled")
            and "testing" not in str(m.get("meeting_name", "")).lower()]
    return hits[0] if hits else None


def weather_summary(session_key: int) -> tuple[str, bool | None]:
    """(Text, Regen ja/nein) aus dem OpenF1-Wetter der Session."""
    w = openf1.cached_fetch("weather", session_key)
    if not w:
        return "kein Wetter in OpenF1", None
    air = [x["air_temperature"] for x in w if x.get("air_temperature") is not None]
    track = [x["track_temperature"] for x in w if x.get("track_temperature") is not None]
    wind = [x["wind_speed"] for x in w if x.get("wind_speed") is not None]
    rain = any(x.get("rainfall") for x in w)
    text = (f"Luft {min(air):.0f}–{max(air):.0f} °C · Strecke {min(track):.0f}–{max(track):.0f} °C · "
            f"Wind bis {max(wind):.1f} m/s · Regen: {'JA' if rain else 'nein'}")
    return text, rain


def fetch_quali(meeting_key: int, top: int = 3, refresh: bool = False) -> dict:
    """Qualifying laden, dazu Positionen + Telemetrie der ersten `top` und das Wetter.
    Rückgabe: {"meeting_key", "session_key", "pole", "drivers", "weather", "rain"}."""
    data = load_session(meeting_key, "Q", refresh=refresh)
    sk = data["session_key"]
    rows = sorted((r for r in data.get("results", []) if r.get("position")), key=lambda r: r["position"])
    if not rows:
        raise ValueError(f"Qualifying {meeting_key}: kein Ergebnis")
    for r in rows[:top]:
        num = data["numbers"][r["driver"]]
        for ep in ("location", "car_data"):
            openf1.cached_fetch_driver(ep, sk, num, refresh)
    text, rain = weather_summary(sk)
    return {"meeting_key": meeting_key, "session_key": sk, "pole": rows[0]["driver"],
            "drivers": [r["driver"] for r in rows[:top]], "weather": text, "rain": rain,
            "no_laps": not data.get("laps")}
