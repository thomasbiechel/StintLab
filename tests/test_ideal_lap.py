"""Tests für die ideale Runde und die Erkennung gestrichener Runden."""

import pytest

from stintlab.analyses.ideal_lap import ideal_laps
from stintlab.race_control import deleted_laps


def lap(driver, num, s1, s2, s3, out=False):
    return {"Driver": driver, "LapNumber": num, "LapTime": s1 + s2 + s3,
            "IsPitOutLap": out, "Sector1": s1, "Sector2": s2, "Sector3": s3}


def deleted_msg(driver, time, num):
    return {"lap": None, "category": "Other", "flag": None,
            "message": f"CAR 1 ({driver}) TIME {time} DELETED - TRACK LIMITS AT TURN 15 LAP {num} 14:23:11"}


def test_best_sectors_from_different_laps_are_combined():
    data = {"laps": [lap("VER", 3, 30.0, 40.5, 35.0), lap("VER", 5, 30.4, 40.0, 35.2)]}
    [r] = ideal_laps(data)
    assert r["sectors"] == [30.0, 40.0, 35.0]
    assert r["ideal"] == pytest.approx(105.0)
    assert r["best"] == pytest.approx(105.5)
    assert r["unused"] == pytest.approx(0.5)


def test_deleted_lap_is_ignored_with_all_its_sectors():
    # Runde 5 hat den schnellsten Sektor 3 – wurde aber gestrichen
    data = {"laps": [lap("LEC", 3, 30.0, 40.0, 35.0), lap("LEC", 5, 30.0, 40.0, 34.0)],
            "race_control": [deleted_msg("LEC", "1:44.000", 5)]}
    [r] = ideal_laps(data)
    assert r["sectors"][2] == 35.0
    assert r["best"] == pytest.approx(105.0)


def test_out_lap_and_other_compound_are_ignored():
    data = {"laps": [lap("NOR", 1, 29.0, 39.0, 34.0, out=True),   # Out-Lap
                     lap("NOR", 2, 30.0, 40.0, 35.0),              # Soft
                     lap("NOR", 8, 29.5, 39.5, 34.5)],             # Medium
            "stints": [{"driver": "NOR", "compound": "SOFT", "lap_start": 1, "lap_end": 4},
                       {"driver": "NOR", "compound": "MEDIUM", "lap_start": 5, "lap_end": 12}]}
    [r] = ideal_laps(data, compound="soft")
    assert r["ideal"] == pytest.approx(105.0)


def test_driver_without_all_three_sectors_is_left_out_and_sorting():
    data = {"laps": [lap("PIA", 2, 30.2, 40.0, 35.0), lap("VER", 2, 30.0, 40.0, 35.0),
                     {"Driver": "HAM", "LapNumber": 2, "LapTime": None, "IsPitOutLap": False,
                      "Sector1": 30.0, "Sector2": None, "Sector3": 35.0}]}
    assert [r["driver"] for r in ideal_laps(data)] == ["VER", "PIA"]


def test_reinstated_lap_counts_again():
    msgs = [deleted_msg("HAM", "1:45.100", 7),
            {"lap": None, "category": "Other", "flag": None,
             "message": "CAR 44 (HAM) TIME 1:45.100 REINSTATED"}]
    assert deleted_laps(msgs) == set()
    assert deleted_laps(msgs[:1]) == {("HAM", 7)}


def test_sector_times_are_loaded_from_openf1():
    from stintlab.session import build_session_data
    raw = {"drivers": [{"driver_number": 1, "name_acronym": "VER", "team_name": "Red Bull Racing"}],
           "laps": [{"driver_number": 1, "lap_number": 2, "lap_duration": 105.0, "is_pit_out_lap": False,
                     "duration_sector_1": 30.0, "duration_sector_2": 40.0, "duration_sector_3": 35.0,
                     "date_start": "2026-09-25T10:00:00+00:00"}],
           "intervals": [], "position": [], "race_control": [], "pit": [], "stints": []}
    [l] = build_session_data(raw)["laps"]
    assert (l["Sector1"], l["Sector2"], l["Sector3"]) == (30.0, 40.0, 35.0)


def test_best_lap_ranking_includes_driver_without_sectors():
    from stintlab.analyses.ideal_lap import best_laps
    data = {"laps": [lap("VER", 2, 30.0, 40.0, 35.0),
                     {"Driver": "HAM", "LapNumber": 2, "LapTime": 104.8, "IsPitOutLap": False,
                      "Sector1": None, "Sector2": 40.0, "Sector3": 35.0}]}
    assert [r["driver"] for r in best_laps(data)] == ["HAM", "VER"]
    assert [r["driver"] for r in ideal_laps(data)] == ["VER"]


def test_unknown_view_is_rejected():
    import matplotlib.pyplot as plt
    from stintlab.registry import ANALYSES
    _, ax = plt.subplots()
    with pytest.raises(ValueError, match="view"):
        ANALYSES["ideal_lap"]["render"](ax, {"laps": [lap("VER", 2, 30.0, 40.0, 35.0)]}, {"view": "beste"})
    plt.close("all")


def test_both_real_deletion_formats_are_recognised():
    msgs = [{"message": m} for m in [
        "CAR 43 (COL) LAP DELETED - TRACK LIMITS AT TURN 2 LAP 2 16:00:36",
        "CAR 44 (HAM) TIME 2:10.489 DELETED - TRACK LIMITS AT TURN 1 LAP 6 16:12:28",
        "CAR 6 (HAD) LAP DELETED - TRACK LIMITS AT TURN 1 LAP 7 16:15:01 (PIT)",
    ]]
    assert deleted_laps(msgs) == {("COL", 2), ("HAM", 6), ("HAD", 7)}


def test_reinstated_by_lap_number():
    msgs = [{"message": "CAR 43 (COL) LAP DELETED - TRACK LIMITS AT TURN 2 LAP 2 16:00:36"},
            {"message": "CAR 43 (COL) LAP 2 REINSTATED"}]
    assert deleted_laps(msgs) == set()
