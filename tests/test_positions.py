"""Tests für den Positionsverlauf: Reihenfolge an der Linie, Startplatz, Zielrunde."""

from datetime import datetime, timedelta, timezone

from stintlab.analyses.positions import compute_positions

T0 = datetime(2026, 9, 27, 11, 0, tzinfo=timezone.utc)


def at(seconds):
    return T0 + timedelta(seconds=seconds)


def test_order_at_the_line_gives_positions():
    ends = {"RUS": {1: at(100), 2: at(200)},
            "VER": {1: at(101), 2: at(199)}}   # VER überholt in Runde 2
    pos = compute_positions(ends)
    assert pos["RUS"] == {1: 1, 2: 2}
    assert pos["VER"] == {1: 2, 2: 1}


def test_grid_is_lap_zero():
    ends = {"ANT": {1: at(100)}, "PIA": {1: at(101)}}
    pos = compute_positions(ends, grid={"ANT": 16, "PIA": 3})
    assert pos["ANT"][0] == 16 and pos["PIA"][0] == 3


def test_retired_driver_stops_counting():
    ends = {"NOR": {1: at(100)},                        # nach Runde 1 raus
            "GAS": {1: at(101), 2: at(201)}}
    pos = compute_positions(ends)
    assert 2 not in pos["NOR"]
    assert pos["GAS"][2] == 1


def test_lapped_driver_ranks_behind():
    # BOT beendet Runde 2 erst, nachdem RUS schon Runde 3 beendet hat
    ends = {"RUS": {1: at(100), 2: at(200), 3: at(300)},
            "BOT": {1: at(150), 2: at(305)}}
    pos = compute_positions(ends)
    assert pos["BOT"][2] == 2


def test_official_result_overrides_final_lap():
    # Baku 2026: Zeitstempel sagen VER vorne, offiziell gewinnt RUS
    ends = {"RUS": {51: at(100.001)}, "VER": {51: at(100.000)}}
    results = [{"driver": "RUS", "position": 1}, {"driver": "VER", "position": 2}]
    pos = compute_positions(ends, results=results)
    assert pos["RUS"][51] == 1 and pos["VER"][51] == 2


def test_dnf_result_does_not_override():
    ends = {"NOR": {1: at(100)}, "GAS": {1: at(101)}}
    results = [{"driver": "NOR", "position": None, "dnf": True}]
    assert compute_positions(ends, results=results)["NOR"][1] == 1
