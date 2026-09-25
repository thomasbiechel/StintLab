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

ENDPOINTS = ["drivers", "laps", "race_control", "pit", "position", "intervals", "stints", "session_result"]


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
        "numbers": {abbr(n): n for n in num_to_abbr},
        "laps": [
            {"Driver": abbr(l.get("driver_number")), "LapNumber": l.get("lap_number"),
             "LapTime": l.get("lap_duration"), "IsPitOutLap": l.get("is_pit_out_lap"),
             "Sector1": l.get("duration_sector_1"), "Sector2": l.get("duration_sector_2"),
             "Sector3": l.get("duration_sector_3"), "LapStart": _parse(l.get("date_start"))}
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
             "flag": m.get("flag"), "message": m.get("message") or "",
             "date": _parse(m.get("date"))}
            for m in raw["race_control"]
        ],
        # Reifen pro Stint: Mischung, Runden und Alter der Reifen beim Aufziehen
        "stints": [
            {"driver": abbr(st.get("driver_number")), "stint": st.get("stint_number"),
             "compound": (st.get("compound") or "UNKNOWN").upper(),
             "lap_start": st.get("lap_start"), "lap_end": st.get("lap_end"),
             "tyre_age_at_start": st.get("tyre_age_at_start")}
            for st in sorted(raw.get("stints", []),
                             key=lambda x: (str(x.get("driver_number")), x.get("stint_number") or 0))
        ],
        # Offizielles Ergebnis (OpenF1 /session_result, Beta). duration und
        # gap_to_leader sind im Qualifying Listen [Q1, Q2, Q3], sonst Zahlen.
        "results": [
            {"driver": abbr(r.get("driver_number")), "position": r.get("position"),
             "duration": r.get("duration"), "gap": r.get("gap_to_leader"),
             "laps": r.get("number_of_laps"), "points": r.get("points"),
             "dnf": bool(r.get("dnf")), "dns": bool(r.get("dns")), "dsq": bool(r.get("dsq"))}
            for r in raw.get("session_result", [])
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
    data = build_session_data(raw)
    data["session_type"] = session_type
    data["session_key"] = session_key
    return data


def sign_mismatches(data: dict, driver_a: str, driver_b: str) -> list[tuple[int, bool]]:
    """Plausibilitätstest für genau das, was gap_between zeichnet.

    Für jede Runde: Liegt laut Zieldurchfahrt derjenige vorne, der laut
    Positionsdaten vorne liegt? Gibt [(Runde, Boxenstopp-Runde?), ...] der
    Runden zurück, in denen beides nicht übereinstimmt. Leer = stimmig.

    In Boxenstopp-Runden sind Abweichungen oft erklärbar: Die Linie in der
    Boxengasse und die Positionsdaten werden nicht exakt gleichzeitig erfasst.
    """
    ends = data["lap_ends"]
    pos = {(r["Driver"], r["LapNumber"]): r["Position"] for r in data["positions"]}
    pit_laps = {(p["driver"], p["lap"]) for p in data["pit_stops"]}
    a, b = ends.get(driver_a, {}), ends.get(driver_b, {})

    bad = []
    for n in sorted(set(a) & set(b)):
        if (driver_a, n) not in pos or (driver_b, n) not in pos:
            continue
        a_ahead_by_time = a[n] < b[n]
        a_ahead_by_pos = pos[(driver_a, n)] < pos[(driver_b, n)]
        if a_ahead_by_time != a_ahead_by_pos:
            is_pit = (driver_a, n) in pit_laps or (driver_b, n) in pit_laps
            bad.append((n, is_pit))
    return bad