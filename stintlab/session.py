"""Baut aus OpenF1-Rohdaten das data-Dictionary, das die Analysen erwarten.

Zwei Teile:
- load_session():       lädt die Rohdaten (über den Cache in openf1.py)
- build_session_data(): reine Umrechnung ohne Netzwerk – dadurch testbar

KERNPUNKT – Zuordnung von Messwerten zu Runden:
OpenF1 liefert Abstände (/intervals) und Positionen (/position) nicht pro
Runde, sondern als Messpunkte mit Zeitstempel. Jede Runde bekommt hier den
LETZTEN Messpunkt vor ihrem ENDE, also den Stand "nach Runde N".
Zugeordnet wird über die echten Zeitstempel – nie durch gleichmäßiges
Verteilen der Messpunkte auf die Runden (der Fehler im Demo-Skript).
"""

from __future__ import annotations

import bisect
from datetime import datetime, timedelta

from stintlab import openf1

# Ein Messpunkt, der älter ist als das, gilt als veraltet: Der Fahrer ist
# ausgeschieden oder überrundet und liefert keine Abstände mehr.
STALE_AFTER_S = 150.0

ENDPOINTS = ["drivers", "laps", "race_control", "pit", "position", "intervals"]


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def lap_end_times(laps_raw: list[dict]) -> dict[tuple[str, int], datetime]:
    """{(Fahrernummer, Runde): Zeitpunkt, an dem die Runde endet}.

    Ende = Start der nächsten Runde desselben Fahrers, also der Moment, in dem
    er die Ziellinie überquert. Nur für die letzte Runde (keine nächste) wird
    Start + Rundendauer verwendet.
    """
    starts: dict[str, dict[int, datetime]] = {}
    durations: dict[tuple[str, int], float] = {}
    for lap in laps_raw:
        drv, num = str(lap.get("driver_number")), lap.get("lap_number")
        start = _parse(lap.get("date_start"))
        if num is None or start is None:
            continue
        starts.setdefault(drv, {})[num] = start
        if lap.get("lap_duration"):
            durations[(drv, num)] = float(lap["lap_duration"])

    ends: dict[tuple[str, int], datetime] = {}
    for drv, by_lap in starts.items():
        for num, start in by_lap.items():
            if num + 1 in by_lap:
                ends[(drv, num)] = by_lap[num + 1]
            elif (drv, num) in durations:
                ends[(drv, num)] = start + timedelta(seconds=durations[(drv, num)])
    return ends


def assign_to_laps(samples: dict[str, list[tuple[datetime, float]]],
                   lap_ends: dict[tuple[str, int], datetime]) -> dict[tuple[str, int], float]:
    """Ordnet jeder Runde den letzten Messpunkt vor ihrem Ende zu.

    samples:  {Fahrernummer: [(Zeitpunkt, Wert), ...]}  – beliebig sortiert
    lap_ends: {(Fahrernummer, Runde): Endzeitpunkt}
    """
    result: dict[tuple[str, int], float] = {}
    sorted_samples = {d: sorted(s) for d, s in samples.items()}
    times = {d: [t for t, _ in s] for d, s in sorted_samples.items()}

    for (drv, num), end in lap_ends.items():
        if drv not in times:
            continue
        idx = bisect.bisect_right(times[drv], end) - 1
        if idx < 0:
            continue  # noch kein Messpunkt vor Ende dieser Runde
        sample_time, value = sorted_samples[drv][idx]
        if (end - sample_time).total_seconds() > STALE_AFTER_S:
            continue  # veraltet – Linie endet hier, statt einzufrieren
        result[(drv, num)] = value
    return result


def build_session_data(raw: dict[str, list[dict]]) -> dict:
    """Rechnet die OpenF1-Rohdaten in das Format der Analysen um."""
    num_to_abbr: dict[str, str] = {}
    num_to_team: dict[str, str] = {}
    for d in raw["drivers"]:
        num = str(d.get("driver_number"))
        num_to_abbr.setdefault(num, d.get("name_acronym") or num)
        num_to_team.setdefault(num, d.get("team_name") or "")

    def abbr(num) -> str:
        return num_to_abbr.get(str(num), str(num))

    ends = lap_end_times(raw["laps"])

    # Abstand zum Führenden. Führender = null bei OpenF1 → 0.
    # Texte wie "+1 LAP" lassen sich nicht darstellen und werden übersprungen.
    gap_samples: dict[str, list[tuple[datetime, float]]] = {}
    for iv in raw["intervals"]:
        t, gap = _parse(iv.get("date")), iv.get("gap_to_leader")
        if t is None:
            continue
        if gap is None:
            gap = 0.0
        elif not isinstance(gap, (int, float)):
            continue
        gap_samples.setdefault(str(iv.get("driver_number")), []).append((t, float(gap)))

    pos_samples: dict[str, list[tuple[datetime, float]]] = {}
    for p in raw["position"]:
        t = _parse(p.get("date"))
        if t is not None and p.get("position"):
            pos_samples.setdefault(str(p.get("driver_number")), []).append((t, p["position"]))

    gaps = assign_to_laps(gap_samples, ends)
    positions = assign_to_laps(pos_samples, ends)

    return {
        # Zeitpunkt, an dem ein Fahrer Runde N beendet: {"NOR": {1: datetime, ...}}
        "lap_ends": {
            abbr(d): {n: t for (dd, n), t in ends.items() if dd == d}
            for d in {dd for dd, _ in ends}
        },
        "teams": {abbr(n): t for n, t in num_to_team.items()},
        "laps": [
            {"Driver": abbr(l.get("driver_number")), "LapNumber": l.get("lap_number"),
             "LapTime": l.get("lap_duration"), "IsPitOutLap": l.get("is_pit_out_lap")}
            for l in raw["laps"]
        ],
        "gap_to_leader": [
            {"Driver": abbr(d), "LapNumber": n, "Gap": g} for (d, n), g in sorted(gaps.items())
        ],
        "positions": [
            {"Driver": abbr(d), "LapNumber": n, "Position": int(p)}
            for (d, n), p in sorted(positions.items())
        ],
        "race_control": [
            {"lap": m.get("lap_number"), "category": m.get("category") or "",
             "flag": m.get("flag"), "message": m.get("message") or ""}
            for m in raw["race_control"]
        ],
        "pit_stops": [
            {"driver": abbr(p.get("driver_number")), "lap": p.get("lap_number"),
             "duration": p.get("pit_duration") or p.get("lane_duration")}
            for p in raw["pit"]
        ],
    }


def load_session(meeting_key: int, session_type: str, refresh: bool = False) -> dict:
    """Lädt eine Session (beim ersten Mal von OpenF1, danach aus dem Cache)."""
    session_key = openf1.find_session_key(meeting_key, session_type)
    raw = {ep: openf1.cached_fetch(ep, session_key, refresh) for ep in ENDPOINTS}
    return build_session_data(raw)


def order_mismatches(data: dict, drivers: list[str] | None = None) -> list[int]:
    """Plausibilitätstest: Runden, in denen die Reihenfolge nach Abstand nicht
    zur Reihenfolge nach Position passt. Leer = Daten sind in sich stimmig."""
    gap = {(r["Driver"], r["LapNumber"]): r["Gap"] for r in data["gap_to_leader"]}
    pos = {(r["Driver"], r["LapNumber"]): r["Position"] for r in data["positions"]}
    laps = sorted({n for _, n in gap})
    bad = []
    for n in laps:
        present = [d for (d, lap) in gap if lap == n and (d, n) in pos]
        if drivers:
            present = [d for d in present if d in drivers]
        by_gap = sorted(present, key=lambda d: (gap[(d, n)], pos[(d, n)]))
        by_pos = sorted(present, key=lambda d: pos[(d, n)])
        if by_gap != by_pos:
            bad.append(n)
    return bad