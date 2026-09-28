"""Tests für den Story-Finder mit kleinen künstlichen Rennen."""

from datetime import datetime, timedelta, timezone

from stintlab.stories import find_battles, find_incidents, find_movers, find_stories

T0 = datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc)
LAP = 100.0


def race(offsets: dict[str, list[float]], sector_split=(0.35, 0.40, 0.25)):
    """offsets[d][n-1] = Rückstand von d auf eine gedachte Referenz am Ende von Runde n."""
    ends, laps = {}, []
    for d, offs in offsets.items():
        ends[d] = {n: T0 + timedelta(seconds=LAP * n + o) for n, o in enumerate(offs, 1)}
        prev = 0.0
        for n, o in enumerate(offs, 1):
            t = LAP + o - prev
            prev = o
            laps.append({"Driver": d, "LapNumber": n, "LapTime": t, "IsPitOutLap": False,
                         "Sector1": t * sector_split[0], "Sector2": t * sector_split[1], "Sector3": t * sector_split[2]})
    return {"lap_ends": ends, "laps": laps, "race_control": [], "pit_stops": [], "results": [], "grid": {}}


def test_close_battle_without_pass_is_found():
    n = 12
    data = race({"RUS": [0.0] * n, "VER": [0.5] * n, "HAD": [8.0] * n})
    data["results"] = [{"driver": d, "position": i, "gap": g} for i, (d, g) in
                       enumerate((("RUS", 0), ("VER", 0.5), ("HAD", 8.0)), 1)]
    battles = find_battles(data)
    assert len(battles) == 1
    b = battles[0]
    assert b.slides[0]["drivers"] == ["RUS", "VER"]
    assert "kein Überholmanöver" in b.facts and "Kampf um P1" in b.facts


def test_gap_over_one_second_is_no_battle():
    data = race({"RUS": [0.0] * 12, "VER": [1.5] * 12})
    assert find_battles(data) == []


def test_incident_lap_with_lost_places():
    n = 12
    offs = {d: [i * 0.5] * n for i, d in enumerate(("RUS", "VER", "PIA", "HAD", "LEC"))}
    offs["VER"] = [0.5] * 6 + [12.0] * 6          # Runde 7: +11,5 s, fällt von P2 auf P5
    data = race(offs)
    inc = find_incidents(data)
    assert len(inc) == 1 and "VER" in inc[0].question and "Runde 7" in inc[0].question
    assert "P2 → P5" in inc[0].facts[1]


def test_mover_counts_places_gifted_by_retirements():
    data = race({"ANT": [5.0] * 10, "NOR": [1.0] * 4})       # NOR fällt nach Runde 4 aus, lag vorne
    data["grid"] = {"ANT": 16, "NOR": 3}
    data["results"] = [{"driver": "ANT", "position": 5, "gap": 20.0}, {"driver": "NOR", "position": None, "dnf": True}]
    m = find_movers(data)
    assert len(m) == 1 and "Ausfälle vor ihm: 1 (NOR)" in m[0].facts[1]


def test_best_story_of_each_kind_comes_first():
    n = 12
    offs = {d: [i * 0.5] * n for i, d in enumerate(("RUS", "VER", "PIA", "HAD", "LEC", "ALB", "SAI"))}
    offs["VER"] = [0.5] * 6 + [20.0] * 6          # VER fällt von P2 ans Ende
    data = race(offs)
    kinds = [s.kind for s in find_stories(data)]
    assert kinds.index("incident") < len(set(kinds))       # nicht hinter lauter Duellen versteckt
