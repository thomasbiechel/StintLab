"""Tests: beste Starter (fair zum Startplatz) und Samstags-/Sonntagsfahrer."""

from datetime import datetime, timedelta

import pytest

from stintlab.analyses.sat_sun import race_deltas, sat_sun_rows
from stintlab.analyses.starts import expected_gain, race_starts, starter_rows

T0 = datetime(2026, 9, 27, 11, 0)


def _race(grid, lap1_order, place="X", rc=None, pits=None):
    """grid {Fahrer: Startplatz}, lap1_order = Reihenfolge an der Linie nach Runde 1."""
    ends = {d: {1: T0 + timedelta(seconds=90 + i)} for i, d in enumerate(lap1_order)}
    for d in grid:
        ends.setdefault(d, {})
    return {"grid": grid, "lap_ends": ends, "teams": {d: "Ferrari" for d in grid},
            "race_control": rc or [], "pit_stops": pits or [], "place": place}


GRID = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}


def test_gain_ignores_lap_one_retirement():
    # C fällt in Runde 1 aus → D rückt nach, das ist KEIN gewonnener Platz
    starts = {s["driver"]: s for s in race_starts(_race(GRID, ["A", "B", "D", "E", "F"]))}
    assert "C" not in starts
    assert starts["D"]["gain"] == 0 and starts["D"]["grid_rank"] == 3


def test_gain_counts_real_overtakes():
    starts = {s["driver"]: s for s in race_starts(_race(GRID, ["A", "E", "B", "C", "D", "F"]))}
    assert starts["E"]["gain"] == 3 and starts["B"]["gain"] == -1


def test_safety_car_on_lap_one_skips_the_race():
    rc = [{"lap": 1, "category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"},
          {"lap": 2, "category": "SafetyCar", "message": "SAFETY CAR IN THIS LAP"}]
    assert race_starts(_race(GRID, ["A", "B", "C", "D", "E", "F"], rc=rc)) == []


def test_expected_gain_pools_neighbouring_slots():
    starts = [{"grid_rank": 1, "gain": 0}, {"grid_rank": 2, "gain": 1}, {"grid_rank": 3, "gain": 2},
              {"grid_rank": 10, "gain": 4}]
    exp = expected_gain(starts)
    assert exp[2] == pytest.approx(1.0) and exp[10] == 4


def test_starter_score_is_relative_to_the_grid_slot():
    # F gewinnt jedes Mal 1 Platz von hinten; A hält Platz 1 – beide „normal“ für ihren Platz?
    races = [_race(GRID, ["A", "B", "C", "D", "F", "E"], place=str(i)) for i in range(5)]
    rows, counted = starter_rows(races)
    by = {r["driver"]: r for r in rows}
    assert counted == 5
    assert by["F"]["raw"] == 1 and by["E"]["raw"] == -1
    assert by["F"]["score"] > 0 > by["E"]["score"]


def _pace_race(times):
    """times {Fahrer: Rundenzeit} → Rennen mit 12 sauberen Runden je Fahrer."""
    laps = [{"Driver": d, "LapNumber": n, "LapTime": t, "IsPitOutLap": False}
            for d, t in times.items() for n in range(1, 14)]
    return {"laps": laps, "lap_ends": {}, "race_control": [], "pit_stops": [],
            "teams": {d: "McLaren" for d in times}}


def test_sunday_driver_has_positive_delta():
    race = _pace_race({"A": 90.0, "B": 90.5, "C": 91.0, "D": 91.5, "E": 92.0})
    quali = {"results": [{"driver": d, "position": p} for d, p in (("C", 1), ("A", 2), ("B", 3), ("D", 4), ("E", 5))]}
    d = {x["driver"]: x["delta"] for x in race_deltas(race, quali)}
    assert d["A"] == 1 and d["C"] == -2 and d["E"] == 0


def test_sat_sun_needs_enough_races():
    race = _pace_race({"A": 90.0, "B": 90.5, "C": 91.0, "D": 91.5, "E": 92.0})
    quali = {"results": [{"driver": d, "position": i} for i, d in enumerate("ABCDE", start=1)]}
    rows, counted = sat_sun_rows([(race, quali)] * 4)
    assert rows == [] and counted == 4
    rows, _ = sat_sun_rows([(race, quali)] * 5)
    assert len(rows) == 5
