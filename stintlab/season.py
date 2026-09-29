"""Saison-Ebene: mehrere Wochenenden eines Jahres gemeinsam auswerten.

Bisher arbeitete jede Analyse mit EINER Session. Saison-Analysen (Teamkollegen-
Duell, WM-Status, Titelrechnung) brauchen dagegen alle Wochenenden bis zu einem
bestimmten Rennen – oder alle, die danach noch kommen.

LEICHTES LADEN (light_session): nur Fahrerliste + offizielles Ergebnis, keine
Runden, Positionen oder Telemetrie. Für 20 Qualifyings sind das ein paar hundert
KB statt vieler MB – und nach dem ersten Mal liegt alles im Cache.

PUNKTE 2026: Rennen 25 für den Sieg, Sprint 8. Keinen Punkt mehr für die
schnellste Runde (seit 2025 abgeschafft).
"""

from __future__ import annotations

from stintlab import openf1
from stintlab.preview import _is_race_weekend, _start, _year

RACE_WIN_PTS = 25
SPRINT_WIN_PTS = 8


def race_weekends(year: int, refresh: bool = False) -> list[dict]:
    """Alle Rennwochenenden eines Jahres (ohne Tests und Absagen), nach Datum sortiert."""
    ms = [m for m in openf1.meetings_of(year, refresh) if _is_race_weekend(m) and _start(m)]
    return sorted(ms, key=_start)


def split_at(meeting_key: int, refresh: bool = False, meeting: dict | None = None,
             weekends: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    """(Wochenenden bis EINSCHLIESSLICH diesem, Wochenenden danach) – gleiches Jahr."""
    meeting = meeting or openf1.meeting_by_key(meeting_key)
    if meeting is None:
        raise ValueError(f"Wochenende {meeting_key} nicht in den gemerkten Jahreslisten – "
                         "einmal mit Netz laden (make_post.py … --refresh)")
    weekends = weekends if weekends is not None else race_weekends(_year(meeting), refresh)
    begin = _start(meeting)
    done = [m for m in weekends if _start(m) <= begin]
    left = [m for m in weekends if _start(m) > begin]
    return done, left


def has_sprint(meeting_key: int, refresh: bool = False, sessions_of=None) -> bool:
    sessions_of = sessions_of or openf1.sessions_of
    return any(s.get("session_name") == openf1.SESSION_NAMES["S"] for s in sessions_of(meeting_key, refresh))


def max_points_left(meeting_key: int, refresh: bool = False, weekends_left: list[dict] | None = None,
                    sessions_of=None) -> dict:
    """Wie viele Punkte ein Fahrer nach diesem Wochenende höchstens noch holen kann.

    {"races", "sprints", "points", "unknown"}; unknown = Wochenenden, deren
    Session-Liste nicht zu laden war (dann ohne Sprint gerechnet → eher zu wenig
    Punkte; die Slide nennt das)."""
    if weekends_left is None:
        _, weekends_left = split_at(meeting_key, refresh)
    sprints, unknown = 0, 0
    for m in weekends_left:
        try:
            sprints += has_sprint(m["meeting_key"], refresh, sessions_of)
        except Exception:                                  # noch keine Sessions veröffentlicht, kein Netz
            unknown += 1
    races = len(weekends_left)
    return {"races": races, "sprints": sprints, "unknown": unknown,
            "points": races * RACE_WIN_PTS + sprints * SPRINT_WIN_PTS}


def light_session(meeting_key: int, session_type: str, refresh: bool = False, fetch=None) -> dict:
    """Nur Ergebnis + Fahrer einer Session:
    {"meeting_key", "session_key", "session_type", "results": [{driver, position, duration, …}],
     "teams": {Kürzel: Team}, "place"}.
    Doppelte Fahrernummern (Wechsel im Wochenende) → erster Eintrag gilt, wie in session.py."""
    fetch = fetch or openf1.cached_fetch
    key = openf1.find_session_key(meeting_key, session_type, refresh)
    drivers = fetch("drivers", key, refresh)
    abbr, teams = {}, {}
    for d in drivers:
        num = str(d.get("driver_number"))
        abbr.setdefault(num, d.get("name_acronym") or num)
        teams.setdefault(abbr[num], d.get("team_name") or "")
    results = []
    for r in fetch("session_result", key, refresh):
        results.append({**r, "driver": abbr.get(str(r.get("driver_number")), str(r.get("driver_number")))})
    m = openf1.meeting_by_key(meeting_key) or {}
    return {"meeting_key": meeting_key, "session_key": key, "session_type": session_type,
            "results": results, "teams": teams,
            "place": m.get("location") or m.get("circuit_short_name") or str(meeting_key)}


def season_sessions(meeting_key: int, session_type: str, refresh: bool = False, load=None) -> list[dict]:
    """light_session für alle Wochenenden des Jahres bis einschließlich diesem.
    Wochenenden ohne diese Session (z. B. kein Sprint) oder ohne Daten werden übersprungen."""
    load = load or light_session
    done, _ = split_at(meeting_key, refresh)
    out = []
    for m in done:
        try:
            s = load(m["meeting_key"], session_type, refresh)
        except Exception as exc:
            print(f"  ℹ {m.get('location') or m['meeting_key']} übersprungen: {exc}")
            continue
        if s.get("results"):
            out.append(s)
    return out


# Rennen „leicht“: Runden, Rennleitung, Boxenstopps, Ergebnis, Fahrer + Startaufstellung –
# ohne Abstände/Positionen (intervals ~3 MB pro Rennen) und ohne Telemetrie.
RACE_ENDPOINTS = ("drivers", "laps", "race_control", "pit", "session_result")


def race_session(meeting_key: int, session_type: str = "R", refresh: bool = False, fetch=None) -> dict:
    """Rennen im Format von session.build_session_data (lap_ends, laps, pit_stops, results …)
    plus "grid" (Startaufstellung) und "place". Für Saison-Analysen über viele Rennen."""
    from stintlab.session import build_grid, build_session_data
    fetch = fetch or openf1.cached_fetch
    key = openf1.find_session_key(meeting_key, session_type, refresh)
    raw = {ep: fetch(ep, key, refresh) for ep in RACE_ENDPOINTS}
    raw.update({"intervals": [], "position": [], "stints": []})
    data = build_session_data(raw)
    grid_type = {"R": "Q", "S": "SQ"}[session_type]
    grid_key = openf1.find_session_key(meeting_key, grid_type, refresh)
    data["grid"] = build_grid(fetch("starting_grid", grid_key, refresh), data["numbers"])
    m = openf1.meeting_by_key(meeting_key) or {}
    data.update({"meeting_key": meeting_key, "session_key": key, "session_type": session_type,
                 "place": m.get("location") or m.get("circuit_short_name") or str(meeting_key)})
    return data
