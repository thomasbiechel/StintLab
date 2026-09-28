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


_RED_FLAG = re.compile(r"\bRED FLAG\b")


_PRIORITY = {"VSC": 0, "SC": 1, "RED": 2}


def restricted_laps(race_control: list[dict]) -> set[int]:
    """Rundennummern unter SC, VSC oder roter Flagge (Art egal, siehe neutral_laps)."""
    return set(neutral_laps(race_control))


def neutral_laps(race_control: list[dict]) -> dict[int, str]:
    """{Runde: "SC" | "VSC" | "RED"} aller neutralisierten Runden.

    Abweichung vom Original im Analyser: Es wird gemerkt, WELCHE Art von
    Unterbrechung läuft. Ein SC/VSC endet nur durch seine eigene Ende-Meldung.
    Grüne/Clear-Flaggen beenden nur eine rote Flagge – und auch nur, wenn sie
    für die ganze Strecke gelten, nicht für einen einzelnen Sektor. Sonst würde
    "CLEAR IN TRACK SECTOR 7" mitten in einer SC-Phase diese vorzeitig beenden.

    ROTE FLAGGE (Monza 2026, Runde 3): Die Meldung kommt als Kategorie "Other"
    ("RED FLAG - RACE SUSPENDED", dazu SessionStatus "SESSION ABORTED"), nicht
    als Flag – und direkt davor "SAFETY CAR DEPLOYED". Ohne Sonderbehandlung
    blieb das SC bis Runde 29 "offen" (erst ein VSC-Ende schloss es), und das
    halbe Rennen galt als neutralisiert. Deshalb:
    - rote Flagge auch am Text / SESSION ABORTED erkennen, sie ersetzt ein SC
      (Runden des SC vor der roten Flagge bleiben SC, ab ihr zählt RED)
    - sie endet mit "SESSION STARTED" oder einer Flagge für die ganze Strecke
    - Formationsrunden und die Runde mit dem stehenden Start zählen dazu
      (wie Runde 1 beim normalen Start – keine Rennpace), als RED
    Fällt eine Runde unter mehrere Arten, gewinnt RED vor SC vor VSC.
    """
    kinds: dict[int, str] = {}
    restart_laps: set[int] = set()
    active_kind: str | None = None   # None, "SC", "VSC" oder "RED"
    start_lap: int | None = None

    def mark(lo: int, hi: int, kind: str) -> None:
        for n in range(lo, hi + 1):
            if n not in kinds or _PRIORITY[kind] >= _PRIORITY[kinds[n]]:
                kinds[n] = kind

    for msg in race_control:
        lap = msg.get("lap")
        if lap is None:
            continue
        category = (msg.get("category") or "").strip()
        flag = (msg.get("flag") or "").strip().upper()
        text = (msg.get("message") or "").upper()

        # \b: "CHEQUERED FLAG" enthält sonst "RED FLAG" -> Zielflagge galt als rot
        is_red = (category == "Flag" and flag == "RED") or bool(_RED_FLAG.search(text)) or \
            (category == "SessionStatus" and "ABORTED" in text)
        if is_red and active_kind != "RED":
            # rote Flagge ersetzt ein laufendes SC/VSC
            if active_kind is not None and start_lap is not None and lap > start_lap:
                mark(start_lap, lap - 1, active_kind)
            active_kind, start_lap = "RED", lap
            continue
        if "FORMATION LAP" in text or "STANDING START" in text:
            restart_laps.update({lap, lap + 1})   # Formationsrunde + Runde mit dem Start
        if active_kind is None:
            if category == "SafetyCar" and "DEPLOYED" in text:
                virtual = "VIRTUAL" in text or bool(re.search(r"\bVSC\b", text))
                active_kind, start_lap = ("VSC" if virtual else "SC"), lap
            continue

        sc_ends = (active_kind in ("SC", "VSC") and category == "SafetyCar"
                   and ("IN THIS LAP" in text or "ENDING" in text))
        red_ends = active_kind == "RED" and (
            (category == "Flag" and flag in ("GREEN", "CLEAR") and "SECTOR" not in text)
            or (category == "SessionStatus" and "STARTED" in text))

        if sc_ends or red_ends:
            mark(start_lap, lap, active_kind)
            active_kind, start_lap = None, None

    # Phase ohne Ende-Meldung (z. B. Rennende unter Neutralisation)
    if active_kind is not None and start_lap is not None:
        last_lap = max((m.get("lap") or start_lap) for m in race_control)
        mark(start_lap, last_lap, active_kind)

    # Neustart nach roter Flagge: Formationsrunden + stehender Start. Beim ersten
    # Start des Rennens (Runde 1) nicht nötig – Runde 1 fällt ohnehin überall raus.
    if kinds:
        for n in sorted(restart_laps):
            if n > 1:
                mark(n, n, "RED")
    return kinds


def neutral_phases(race_control: list[dict], first: int | None = None,
                   last: int | None = None) -> list[tuple[int, int, str]]:
    """Zusammenhängende Phasen gleicher Art als [(von, bis, Art)], optional
    auf den Rundenbereich first..last beschränkt."""
    phases: list[tuple[int, int, str]] = []
    for n, kind in sorted(neutral_laps(race_control).items()):
        if (first is not None and n < first) or (last is not None and n > last):
            continue
        if phases and n == phases[-1][1] + 1 and kind == phases[-1][2]:
            phases[-1] = (phases[-1][0], n, kind)
        else:
            phases.append((n, n, kind))
    return phases


# Zwei Formate kommen vor (echte Meldungen aus Baku FP2):
#   "CAR 44 (HAM) TIME 2:10.489 DELETED - TRACK LIMITS AT TURN 1 LAP 6 16:12:28"
#   "CAR 43 (COL) LAP DELETED - TRACK LIMITS AT TURN 2 LAP 2 16:00:36"
_DELETED = re.compile(r"\((?P<drv>[A-Z]{3})\)\s+(?:LAP\s+)?(?:TIME\s+(?P<time>[\d:.]+)\s+)?DELETED"
                      r".*?\bLAP\s+(?P<lap>\d+)")
# Aufhebung – mit Zeit oder mit Rundennummer, je nach Format
_REINSTATED = re.compile(r"\((?P<drv>[A-Z]{3})\)\s+(?:LAP\s+(?P<lap>\d+)\s+)?(?:LAP\s+)?"
                         r"(?:TIME\s+(?P<time>[\d:.]+)\s+)?REINSTATED")


def _seconds(time_text: str) -> float | None:
    """"2:13.440" → 133.44"""
    try:
        minutes, rest = time_text.split(":") if ":" in time_text else ("0", time_text)
        return int(minutes) * 60 + float(rest)
    except ValueError:
        return None


def _resolve(drv: str, lap_text: int, time_text: str | None, date,
             laps_by_driver: dict[str, list[dict]], lap_ends: dict) -> int:
    """Welche OpenF1-Runde meint eine Streichung?

    Die Rundennummer im Meldungstext ist NICHT zuverlässig: In Baku FP2 meldete
    die Rennleitung "RUS TIME 2:13.440 DELETED … LAP 14", bei OpenF1 war das
    Runde 13 – Runde 14 war seine schnellste. Deshalb, in dieser Reihenfolge:
      1. Meldung mit Zeit → die Runde des Fahrers mit genau dieser Zeit
      2. Meldung ohne Zeit → die Runde, die zum Zeitpunkt der Meldung LÄUFT
         (letzte beendete + 1). Sie hat noch keine Zeit, deshalb steht keine
         in der Meldung. Geprüft an Baku FP2: SAI, HAD und ALB (In-Laps vor
         "(PIT)") und COL (schnelle Runde, noch vor dem Ziel gestrichen).
      3. Notlösung: Rundennummer aus dem Text
    """
    seconds = _seconds(time_text) if time_text else None
    if seconds is not None:
        same = [l for l in laps_by_driver.get(drv, [])
                if l.get("LapTime") and abs(float(l["LapTime"]) - seconds) <= 0.0015]
        if same:
            return min(same, key=lambda l: abs(l["LapNumber"] - lap_text))["LapNumber"]
    ends = lap_ends.get(drv, {})
    if date is not None and ends:
        finished = [n for n, end in ends.items() if end <= date]
        return max(finished) + 1 if finished else min(ends)
    return lap_text


def deleted_laps(race_control: list[dict], laps: list[dict] | None = None,
                 lap_ends: dict | None = None) -> set[tuple[str, int]]:
    """{(Fahrerkürzel, OpenF1-Runde)} aller gestrichenen Runden.

    Mit laps (und lap_ends) wird jede Streichung über Zeit bzw. Zeitstempel der
    richtigen Runde zugeordnet, siehe _resolve(). Ohne diese Daten bleibt nur
    die unzuverlässige Rundennummer aus dem Text – das ist nur für Tests gedacht.
    Eine spätere "REINSTATED"-Meldung (gleiche Zeit oder gleiche Runde im Text)
    hebt die Streichung auf.
    """
    laps_by_driver: dict[str, list[dict]] = {}
    for lap in laps or []:
        if lap.get("LapNumber") is not None:
            laps_by_driver.setdefault(lap["Driver"], []).append(lap)

    # (Fahrer, Runde laut Text, Zeit laut Text, Zeitstempel)
    deleted: list[tuple[str, int, str | None, object]] = []
    for msg in race_control:
        text = (msg.get("message") or "").upper()
        if m := _DELETED.search(text):
            deleted.append((m["drv"], int(m["lap"]), m["time"], msg.get("date")))
        elif m := _REINSTATED.search(text):
            deleted = [(d, lap, t, dt) for d, lap, t, dt in deleted
                       if not (d == m["drv"] and ((m["time"] and t == m["time"])
                                                   or (m["lap"] and lap == int(m["lap"]))))]
    return {(d, _resolve(d, lap, t, dt, laps_by_driver, lap_ends or {})) for d, lap, t, dt in deleted}
