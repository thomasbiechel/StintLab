"""Tests für die Speed-Trap-Slides – Werte angelehnt an Baku Q 2026 (RUS)."""

from stintlab.analyses.speed import speed_rows


def lap(drv, n, t, st, s2=42.0, out=False):
    return {"Driver": drv, "LapNumber": n, "LapTime": t, "IsPitOutLap": out,
            "Sector1": 36.0, "Sector2": s2, "Sector3": t - 36.0 - s2, "SpeedST": st}


def test_speed_on_fastest_lap_and_session_max():
    # RUS: schnellste Runde 102.526 mit 328; Abkühlrunde 131.0 mit 282;
    # eine langsamere Runde mit Windschatten 331
    data = {"laps": [lap("RUS", 23, 103.037, 331), lap("RUS", 24, 131.007, 282),
                     lap("RUS", 25, 102.526, 328, s2=41.659)]}
    [r], _ = speed_rows(data)
    assert r["st"] == 328 and r["max"] == 331
    assert r["sector"] == 41.659


def test_sorted_by_speed_on_fastest_lap_and_missing_reported():
    data = {"laps": [lap("RUS", 5, 102.5, 328), lap("LEC", 5, 103.3, 325),
                     {**lap("VER", 5, 104.0, 0), "SpeedST": None}]}
    rows, missing = speed_rows(data)
    assert [r["driver"] for r in rows] == ["RUS", "LEC"]
    assert missing == ["VER"]


def test_cool_down_laps_count_for_max_only():
    data = {"laps": [lap("HAM", 3, 103.9, 322), lap("HAM", 4, 125.0, 326)]}
    [r], _ = speed_rows(data)
    assert r["st"] == 322 and r["max"] == 326
