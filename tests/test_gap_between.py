"""Tests für die Vorzeichen-Konvention – genau hier gab es im PDF-Report schon Fehler."""

from stintlab.analyses.gap_between import compute_gap_between
from stintlab.race_control import restricted_laps


def test_driver_a_ahead_gives_positive_gap():
    # NOR führt (Gap 0), ANT liegt 1,5 s dahinter
    rows = [
        {"Driver": "NOR", "LapNumber": 1, "Gap": 0.0},
        {"Driver": "ANT", "LapNumber": 1, "Gap": 1.5},
    ]
    assert compute_gap_between(rows, "NOR", "ANT") == {1: 1.5}
    assert compute_gap_between(rows, "ANT", "NOR") == {1: -1.5}


def test_laps_missing_for_one_driver_are_skipped():
    rows = [
        {"Driver": "NOR", "LapNumber": 1, "Gap": 0.0},
        {"Driver": "ANT", "LapNumber": 1, "Gap": 1.0},
        {"Driver": "NOR", "LapNumber": 2, "Gap": 0.0},  # ANT fehlt in Runde 2
    ]
    assert compute_gap_between(rows, "NOR", "ANT") == {1: 1.0}


def test_vsc_marks_all_laps_from_deploy_to_ending():
    msgs = [
        {"lap": 20, "category": "SafetyCar", "message": "VIRTUAL SAFETY CAR DEPLOYED"},
        {"lap": 22, "category": "SafetyCar", "message": "VIRTUAL SAFETY CAR ENDING"},
    ]
    assert restricted_laps(msgs) == {20, 21, 22}