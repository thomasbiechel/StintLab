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

import re


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

# Zwei Formate kommen vor (echte Meldungen aus Baku FP2):
#   "CAR 44 (HAM) TIME 2:10.489 DELETED - TRACK LIMITS AT TURN 1 LAP 6 16:12:28"
#   "CAR 43 (COL) LAP DELETED - TRACK LIMITS AT TURN 2 LAP 2 16:00:36"
_DELETED = re.compile(r"\((?P<drv>[A-Z]{3})\)\s+(?:LAP\s+)?(?:TIME\s+(?P<time>[\d:.]+)\s+)?DELETED"
                      r".*?\bLAP\s+(?P<lap>\d+)")
# Aufhebung – mit Zeit oder mit Rundennummer, je nach Format
_REINSTATED = re.compile(r"\((?P<drv>[A-Z]{3})\)\s+(?:LAP\s+(?P<lap>\d+)\s+)?(?:LAP\s+)?"
                         r"(?:TIME\s+(?P<time>[\d:.]+)\s+)?REINSTATED")


def deleted_laps(race_control: list[dict]) -> set[tuple[str, int]]:
    """{(Fahrerkürzel, Runde)} aller gestrichenen Runden (z. B. Track Limits).

    Im Training haben Race-Control-Meldungen oft keine Rundennummer im Feld
    "lap" – sie steht aber im Text, deshalb wird der Text ausgewertet.
    Eine spätere "REINSTATED"-Meldung (gleiche Zeit oder gleiche Runde) hebt
    die Streichung auf.
    """
    deleted: list[tuple[str, int, str | None]] = []   # (Fahrer, Runde, Zeit)
    for msg in race_control:
        text = (msg.get("message") or "").upper()
        if m := _DELETED.search(text):
            deleted.append((m["drv"], int(m["lap"]), m["time"]))
        elif m := _REINSTATED.search(text):
            deleted = [(d, lap, t) for d, lap, t in deleted
                       if not (d == m["drv"] and ((m["time"] and t == m["time"])
                                                   or (m["lap"] and lap == int(m["lap"]))))]
    return {(d, lap) for d, lap, _ in deleted}
