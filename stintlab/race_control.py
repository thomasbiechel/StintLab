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
    """Rundennummern unter SC, VSC oder roter Flagge.

    Abweichung vom Original im Analyser: Es wird gemerkt, WELCHE Art von
    Unterbrechung läuft. Ein SC/VSC endet nur durch seine eigene Ende-Meldung.
    Grüne/Clear-Flaggen beenden nur eine rote Flagge – und auch nur, wenn sie
    für die ganze Strecke gelten, nicht für einen einzelnen Sektor. Sonst würde
    "CLEAR IN TRACK SECTOR 7" mitten in einer SC-Phase diese vorzeitig beenden.
    """
    restricted: set[int] = set()
    active_kind: str | None = None   # None, "SC" (gilt auch für VSC) oder "RED"
    start_lap: int | None = None

    for msg in race_control:
        lap = msg.get("lap")
        if lap is None:
            continue
        category = (msg.get("category") or "").strip()
        flag = (msg.get("flag") or "").strip().upper()
        text = (msg.get("message") or "").upper()

        if active_kind is None:
            if category == "SafetyCar" and "DEPLOYED" in text:
                active_kind, start_lap = "SC", lap
            elif category == "Flag" and flag == "RED":
                active_kind, start_lap = "RED", lap
            continue

        sc_ends = (active_kind == "SC" and category == "SafetyCar"
                   and ("IN THIS LAP" in text or "ENDING" in text))
        red_ends = (active_kind == "RED" and category == "Flag"
                    and flag in ("GREEN", "CLEAR") and "SECTOR" not in text)

        if sc_ends or red_ends:
            restricted.update(range(start_lap, lap + 1))
            active_kind, start_lap = None, None

    # Phase ohne Ende-Meldung (z. B. Rennende unter Neutralisation)
    if active_kind is not None and start_lap is not None:
        last_lap = max((m.get("lap") or start_lap) for m in race_control)
        restricted.update(range(start_lap, last_lap + 1))

    return restricted