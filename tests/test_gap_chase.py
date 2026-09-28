"""Tests für das Chase-Reel."""

from datetime import datetime, timedelta, timezone

from stintlab.reels.gap_chase import gap_series, neutral_blocks, pick_pair

T0 = datetime(2026, 9, 26, 11, 0, tzinfo=timezone.utc)


def ends(times):
    out, t = {}, T0
    for n, lt in enumerate(times, start=1):
        t = t + timedelta(seconds=lt)
        out[n] = t
    return out


def test_gap_is_positive_when_first_driver_is_ahead():
    data = {"lap_ends": {"RUS": ends([100.0] * 5), "VER": ends([101.0, 101.0, 100.5, 100.2, 100.1])}}
    x, y = gap_series(data, "RUS", "VER")
    assert list(x) == [1, 2, 3, 4, 5]
    assert abs(y[0] - 1.0) < 1e-9 and abs(y[-1] - 2.8) < 1e-9


def test_default_pair_is_winner_and_second():
    data = {"results": [{"driver": "VER", "position": 2, "gap": 0.196, "duration": None, "laps": 51},
                        {"driver": "RUS", "position": 1, "gap": 0, "duration": 5882.1, "laps": 51},
                        {"driver": "HAD", "position": 3, "gap": 10.7, "duration": None, "laps": 51}]}
    assert pick_pair(data, None) == ["RUS", "VER"]


def test_sc_laps_are_grouped_into_blocks():
    rc = [{"lap": 31, "category": "SafetyCar", "flag": None, "message": "SAFETY CAR DEPLOYED"},
          {"lap": 35, "category": "SafetyCar", "flag": None, "message": "SAFETY CAR IN THIS LAP"}]
    assert neutral_blocks(rc, 1, 51) == [(31, 35)]


def test_last_race_lap_uses_official_gap():
    # Echter Fall Baku 2026: geschätztes Ende der letzten Runde ergibt −0,003 s,
    # offiziell +0,196 s
    rus, ver = ends([100.0] * 3), ends([100.5, 100.0, 99.0])
    data = {"lap_ends": {"RUS": rus, "VER": ver},
            "results": [{"driver": "RUS", "position": 1, "gap": 0, "duration": 300.0, "laps": 3},
                        {"driver": "VER", "position": 2, "gap": 0.196, "duration": None, "laps": 3}]}
    x, y = gap_series(data, "RUS", "VER")
    assert abs(y[-1] - 0.196) < 1e-9


def test_skip_removes_outlier_laps():
    data = {"lap_ends": {"RUS": ends([100.0] * 5), "VER": ends([101.0, 100.0, 104.0, 96.0, 100.0])}}
    x, _ = gap_series(data, "RUS", "VER", skip=[3])
    assert 3 not in x
