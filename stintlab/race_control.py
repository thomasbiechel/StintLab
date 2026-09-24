"""Erkennung von Safety-Car-, VSC- und Rote-Flagge-Phasen.

Übernommen aus data_prep.py des F1 Data Analyser, unverändert in der Logik,
damit StintLab und der Analyser dieselben Runden als neutralisiert werten.

OpenF1 liefert kein Feld "Track Status" pro Runde. Deshalb werden die
Race-Control-Meldungen der Reihe nach abgespielt: Jede Runde zwischen einer
"DEPLOYED"- bzw. Rote-Flagge-Meldung und der passenden Ende-Meldung zählt als
neutralisiert.

Erwartetes Format einer Meldung:
    {"lap": 23, "category": "SafetyCar", "flag": None,
     "message": "VIRTUAL SAFETY CAR DEPLOYED"}
"""

from __future__ import annotations


def restricted_laps(race_control: list[dict]) -> set[int]:
    """Rundennummern unter SC, VSC oder roter Flagge."""
    restricted: set[int] = set()
    active = False
    start_lap: int | None = None

    for msg in race_control:
        lap = msg.get("lap")
        if lap is None:
            continue
        category = (msg.get("category") or "").strip()
        flag = (msg.get("flag") or "").strip().upper()
        text = (msg.get("message") or "").upper()

        is_start = (
            (category == "SafetyCar" and "DEPLOYED" in text)
            or (category == "Flag" and flag == "RED")
        )
        is_end = (
            (category == "SafetyCar" and ("IN THIS LAP" in text or "ENDING" in text))
            or (category == "Flag" and flag in ("GREEN", "CLEAR") and active)
        )

        if is_start and not active:
            active = True
            start_lap = lap
        elif is_end and active:
            restricted.update(range(start_lap, lap + 1))
            active = False
            start_lap = None

    # Phase ohne Ende-Meldung (z. B. Rennende unter Neutralisation)
    if active and start_lap is not None:
        last_lap = max((m.get("lap") or start_lap) for m in race_control)
        restricted.update(range(start_lap, last_lap + 1))

    return restricted