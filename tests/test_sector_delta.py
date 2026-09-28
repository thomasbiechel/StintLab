"""Tests für den Sektorvergleich zweier Fahrer."""

from stintlab.analyses.sector_delta import compute_sector_delta


def lap(drv, n, s1, s2, s3, **extra):
    return {"Driver": drv, "LapNumber": n, "Sector1": s1, "Sector2": s2, "Sector3": s3,
            "LapTime": s1 + s2 + s3, "IsPitOutLap": False, **extra}


def test_delta_is_b_minus_a_per_sector():
    data = {"laps": [lap("RUS", 40, 37.0, 42.7, 25.2), lap("VER", 40, 37.2, 43.0, 24.8)],
            "race_control": [], "pit_stops": []}
    d = compute_sector_delta(data, "RUS", "VER")
    assert round(d["Sector1"][40], 3) == 0.2
    assert round(d["Sector3"][40], 3) == -0.4
    assert round(d["LapTime"][40], 3) == 0.1


def test_sc_pit_and_window_laps_are_skipped():
    laps = [lap(d, n, 37.0, 42.7, 25.2) for d in ("RUS", "VER") for n in (30, 31, 32, 40)]
    data = {"laps": laps, "pit_stops": [{"driver": "VER", "lap": 30}],
            "race_control": [{"lap": 31, "category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"},
                             {"lap": 31, "category": "SafetyCar", "message": "SAFETY CAR IN THIS LAP"}]}
    d = compute_sector_delta(data, "RUS", "VER", laps=(30, 35))
    assert sorted(d["LapTime"]) == [32]


def test_missing_sector_only_drops_that_sector():
    data = {"laps": [lap("RUS", 40, 37.0, 42.7, 25.2), lap("VER", 40, 37.2, 43.0, 24.8)],
            "race_control": [], "pit_stops": []}
    data["laps"][1]["Sector1"] = None
    d = compute_sector_delta(data, "RUS", "VER")
    assert 40 not in d["Sector1"] and 40 in d["Sector2"]
