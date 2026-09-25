"""Qualifying: Welche Runde gehört zu Q1, Q2 oder Q3?

OpenF1 liefert in den Rundendaten keinen Abschnitt. Die Rennleitung meldet
aber jeden Abschnitt mit "SESSION STARTED" und "SESSION FINISHED"
(geprüft am Madring-Qualifying 2026). Eine Runde gehört zu dem Abschnitt,
in dem sie BEGINNT.

TOLERANZ: Die Zeitstempel sind nicht auf Zehntel genau. RUS' schnellste
Q1-Runde in Madrid beginnt laut Daten 0,2 s NACH der Zielflagge – er war
natürlich rechtzeitig über der Linie. Runden, die bis zu GRACE_S nach dem
Ende beginnen, zählen deshalb noch zum Abschnitt. Die Pausen zwischen den
Abschnitten dauern Minuten, die Toleranz sammelt also nichts Falsches ein.
"""

from __future__ import annotations

from datetime import timedelta

from stintlab.race_control import deleted_laps

GRACE_S = 5.0
PARTS = ("Q1", "Q2", "Q3")


def session_parts(race_control: list[dict]) -> list[tuple]:
    """[(Start, Ende), ...] der Abschnitte, in zeitlicher Reihenfolge."""
    parts, start = [], None
    for msg in sorted((m for m in race_control if m.get("date")), key=lambda m: m["date"]):
        if (msg.get("category") or "") != "SessionStatus":
            continue
        text = (msg.get("message") or "").upper()
        if "STARTED" in text and start is None:
            start = msg["date"]
        elif "FINISHED" in text and start is not None:
            parts.append((start, msg["date"]))
            start = None
    return parts


def lap_parts(data: dict) -> dict[tuple[str, int], str]:
    """{(Fahrer, Runde): "Q1" | "Q2" | "Q3"} – Runden außerhalb bleiben weg."""
    parts = session_parts(data.get("race_control", []))
    if len(parts) != len(PARTS):
        # Lieber abbrechen als still falsch zuordnen (z. B. rote Flagge mit
        # eigener STARTED/FINISHED-Folge) – dann Meldungen ansehen
        raise ValueError(f"{len(parts)} Qualifying-Abschnitte in den Race-Control-Meldungen gefunden, "
                         f"erwartet {len(PARTS)} – SessionStatus-Meldungen prüfen")
    grace = timedelta(seconds=GRACE_S)
    result = {}
    for lap in data.get("laps", []):
        begin = lap.get("LapStart")
        if begin is None:
            continue
        for name, (start, end) in zip(PARTS, parts):
            if start <= begin <= end + grace:
                result[(lap["Driver"], lap["LapNumber"])] = name
                break
    return result


def quali_mismatches(data: dict) -> list[str]:
    """Plausibilitätstest: Bestzeit pro Abschnitt aus den Rundendaten (ohne
    Out-Laps und gestrichene Runden) vs. offizielle Q-Zeiten. Leer = stimmig."""
    part_of = lap_parts(data)
    deleted = deleted_laps(data.get("race_control", []), data.get("laps", []), data.get("lap_ends", {}))
    ours: dict[tuple[str, str], float] = {}
    for lap in data.get("laps", []):
        key = (lap["Driver"], lap["LapNumber"])
        if not lap.get("LapTime") or lap.get("IsPitOutLap") or key in deleted or key not in part_of:
            continue
        k = (lap["Driver"], part_of[key])
        ours[k] = min(float(lap["LapTime"]), ours.get(k, float("inf")))

    problems = []
    for r in data.get("results", []):
        official = r.get("duration")
        if not isinstance(official, list):
            continue
        for name, value in zip(PARTS, official):
            own = ours.get((r["driver"], name))
            if value is None and own is None:
                continue
            if value is None or own is None or abs(own - value) > 0.0015:
                problems.append(f"{r['driver']} {name}: offiziell {value}, Rundendaten {own}")
    return problems
