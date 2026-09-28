"""Lädt ein Qualifying eines früheren Jahres für den Vorjahresvergleich (Ghost Lap).

Aufruf:  python fetch_compare.py baku 2025
         python fetch_compare.py baku 2025 2026   (zusätzlich Wetter des aktuellen Jahres)

Holt (und merkt sich in data/cache): Session-Daten, Positionen + Telemetrie der
ersten drei der Startaufstellung (Pole ± Reserve) und das Wetter. Gibt am Ende
eine kurze Übersicht aus, ob der Vergleich fair ist (Regen, Temperatur, Wind).
"""

import sys

from stintlab import openf1
from stintlab.session import load_session


def weather_summary(session_key: int) -> str:
    w = openf1.cached_fetch("weather", session_key)
    if not w:
        return "kein Wetter in OpenF1"
    air = [x["air_temperature"] for x in w if x.get("air_temperature") is not None]
    track = [x["track_temperature"] for x in w if x.get("track_temperature") is not None]
    wind = [x["wind_speed"] for x in w if x.get("wind_speed") is not None]
    rain = any(x.get("rainfall") for x in w)
    return (f"Luft {min(air):.0f}–{max(air):.0f} °C · Strecke {min(track):.0f}–{max(track):.0f} °C · "
            f"Wind bis {max(wind):.1f} m/s · Regen: {'JA' if rain else 'nein'}")


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("Aufruf: python fetch_compare.py <Strecke> <Jahr> [aktuelles Jahr]")
    query, year = sys.argv[1], int(sys.argv[2])
    meeting = openf1.find_meeting(query, year)
    mk = meeting["meeting_key"]
    print(f"{year}: {meeting.get('meeting_name')} ({meeting.get('location')}) · meeting_key {mk}")
    data = load_session(mk, "Q")
    sk = data["session_key"]
    rows = sorted((r for r in data.get("results", []) if r.get("position")), key=lambda r: r["position"])
    for r in rows[:3]:
        num = data["numbers"][r["driver"]]
        for ep in ("location", "car_data"):
            openf1.cached_fetch_driver(ep, sk, num)
        print(f"  P{r['position']} {r['driver']} (#{num}) – Positionen + Telemetrie geladen")
    print(f"  Wetter {year}: {weather_summary(sk)}")
    if len(sys.argv) > 3:
        now = openf1.find_meeting(query, int(sys.argv[3]))
        sk_now = openf1.find_session_key(now["meeting_key"], "Q")
        print(f"  Wetter {sys.argv[3]}: {weather_summary(sk_now)}")
    print(f"\nFertig – in der post.toml: compare = {{ meeting_key = {mk} }}")


if __name__ == "__main__":
    main()
