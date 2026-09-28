"""Lädt ein Qualifying eines früheren Jahres für den Vorjahresvergleich (Ghost Lap).

Aufruf:  python fetch_compare.py baku 2025
         python fetch_compare.py baku 2025 2026   (zusätzlich Wetter des aktuellen Jahres)

Meist nicht nötig: weekend.py <ort> Q erledigt das beim Qualifying automatisch.
"""

import sys

from stintlab import openf1
from stintlab.compare import fetch_quali, weather_summary


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("Aufruf: python fetch_compare.py <Strecke> <Jahr> [aktuelles Jahr]")
    query, year = sys.argv[1], int(sys.argv[2])
    meeting = openf1.find_meeting(query, year)
    mk = meeting["meeting_key"]
    print(f"{year}: {meeting.get('meeting_name')} ({meeting.get('location')}) · meeting_key {mk}")
    info = fetch_quali(mk)
    print(f"  Pole {info['pole']} · Positionen + Telemetrie geladen für {', '.join(info['drivers'])}")
    print(f"  Wetter {year}: {info['weather']}")
    if info["no_laps"]:
        print("  ℹ OpenF1 ohne Rundendaten – die Pole-Runde wird beim Rendern rekonstruiert")
    if len(sys.argv) > 3:
        now = openf1.find_meeting(query, int(sys.argv[3]))
        print(f"  Wetter {sys.argv[3]}: {weather_summary(openf1.find_session_key(now['meeting_key'], 'Q'))[0]}")
    print(f"\nFertig – in der post.toml: compare = {{ meeting_key = {mk} }}")


if __name__ == "__main__":
    main()
