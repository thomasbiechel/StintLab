"""Tests für die Bereinigung der Rundenzeiten."""

from stintlab.analyses.lap_times import clean_lap_times, rolling_median


def make_data():
    laps = [{"Driver": "NOR", "LapNumber": n, "LapTime": 92.0, "IsPitOutLap": False}
            for n in range(1, 11)]
    laps[4]["IsPitOutLap"] = True          # Runde 5: Out-Lap
    laps[7]["LapTime"] = 120.0             # Runde 8: Ausreißer > 107 %
    laps[8]["LapTime"] = None              # Runde 9: keine Zeit
    return {
        "laps": laps,
        "pit_stops": [{"driver": "NOR", "lap": 4}],   # Runde 4: In-Lap
        "race_control": [
            {"lap": 2, "category": "SafetyCar", "message": "VSC DEPLOYED"},
            {"lap": 2, "category": "SafetyCar", "message": "VSC ENDING"},
        ],
    }


def test_pit_vsc_outlier_and_missing_laps_are_removed():
    kept = clean_lap_times(make_data(), ["NOR"])["NOR"]
    assert sorted(kept) == [1, 3, 6, 7, 10]


def test_lap_window_is_applied():
    kept = clean_lap_times(make_data(), ["NOR"], laps=(6, 10))["NOR"]
    assert sorted(kept) == [6, 7, 10]


def test_rolling_median_ignores_single_outlier():
    assert rolling_median([92.0, 92.1, 99.0, 92.2, 92.3]) == [92.05, 92.1, 92.2, 92.3, 92.25]


def test_consecutive_runs_split_at_gaps():
    from stintlab.analyses.lap_times import _consecutive_runs
    assert _consecutive_runs([16, 17, 18, 21, 22]) == [[16, 17, 18], [21, 22]]