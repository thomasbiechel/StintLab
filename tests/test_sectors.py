"""Tests für die Sektor-Slide."""

from stintlab.analyses.sectors import best_sectors


def lap(driver, num, s1, s2, s3, out=False):
    return {"Driver": driver, "LapNumber": num, "LapTime": s1 + s2 + s3, "IsPitOutLap": out,
            "Sector1": s1, "Sector2": s2, "Sector3": s3}


def test_each_column_is_its_own_ranking():
    data = {"laps": [lap("VER", 2, 30.0, 41.0, 33.0), lap("RUS", 2, 30.2, 40.8, 32.9)]}
    s1, s2, s3 = best_sectors(data)
    assert [d for d, _ in s1] == ["VER", "RUS"]
    assert [d for d, _ in s2] == ["RUS", "VER"]
    assert [d for d, _ in s3] == ["RUS", "VER"]


def test_best_sector_can_come_from_different_laps():
    data = {"laps": [lap("VER", 2, 30.0, 41.0, 33.0), lap("VER", 4, 30.5, 40.5, 33.5)]}
    s1, s2, _ = best_sectors(data)
    assert s1 == [("VER", 30.0)] and s2 == [("VER", 40.5)]


def test_deleted_and_out_laps_do_not_count():
    msgs = [{"message": "CAR 1 (VER) TIME 1:43.000 DELETED - TRACK LIMITS AT TURN 15 LAP 4 14:00:00"}]
    data = {"laps": [lap("VER", 1, 29.0, 40.0, 32.0, out=True),   # Out-Lap
                     lap("VER", 2, 30.0, 41.0, 33.0),
                     lap("VER", 3, 29.5, 40.5, 33.0)],            # 103.0 → gestrichen
            "race_control": msgs}
    s1, _, _ = best_sectors(data)
    assert s1 == [("VER", 30.0)]


def test_driver_missing_one_sector_still_appears_in_the_others():
    data = {"laps": [{"Driver": "HAM", "LapNumber": 2, "LapTime": None, "IsPitOutLap": False,
                      "Sector1": 30.1, "Sector2": None, "Sector3": 33.2}]}
    s1, s2, s3 = best_sectors(data)
    assert s1 == [("HAM", 30.1)] and s2 == [] and s3 == [("HAM", 33.2)]
