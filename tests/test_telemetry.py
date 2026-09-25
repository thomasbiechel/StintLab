"""Tests für den Telemetrie-Vergleich."""

from datetime import datetime, timedelta, timezone

import numpy as np

from stintlab.analyses.telemetry import compare, distance, lap_trace

START = datetime(2026, 9, 12, 14, 50, tzinfo=timezone.utc)


def test_distance_of_constant_speed():
    t = np.array([0.0, 1.0, 2.0])
    assert distance(t, np.array([360.0, 360.0, 360.0]))[-1] == 200.0   # 100 m/s × 2 s


def test_lap_trace_starts_at_zero_and_ends_at_lap_time():
    car = [{"date": (START + timedelta(seconds=s)).isoformat(), "speed": 200 + s}
           for s in np.arange(-1.0, 92.0, 0.27)]
    lap = {"Driver": "NOR", "LapNumber": 18, "LapStart": START, "LapTime": 90.5}
    t, v = lap_trace(car, lap)
    assert t[0] == 0.0 and t[-1] == 90.5
    assert abs(v[0] - 200.0) < 0.01 and abs(v[-1] - 290.5) < 0.01


def _trace(v_straight, lap_time, sectors):
    t = np.linspace(0, lap_time, 400)
    v = np.full_like(t, v_straight)
    return {"t": t, "v": v, "lap_time": lap_time, "sectors": sectors}


def test_delta_matches_official_sector_gaps_exactly():
    a = _trace(250.0, 90.0, [30.0, 35.0, 25.0])
    b = _trace(248.0, 90.3, [30.1, 35.05, 25.15])
    res = compare(a, b)
    # Am Ziel exakt der Rundenabstand, an den Sektorgrenzen die Sektorabstände
    assert abs(res["delta"][-1] - 0.3) < 1e-9
    for mark, expected in zip(res["sector_marks"], (0.1, 0.15)):
        assert abs(np.interp(mark, res["frac"], res["delta"]) - expected) < 1e-3


def test_without_sector_times_only_the_lap_gap_is_anchored():
    res = compare(_trace(250.0, 90.0, None), _trace(248.0, 90.3, None))
    assert res["sector_marks"] == []
    assert abs(res["delta"][-1] - 0.3) < 1e-9


def test_sector_boundaries_are_cross_checked():
    a = _trace(250.0, 90.0, [30.0, 35.0, 25.0])
    b = _trace(248.0, 90.3, [30.1, 35.05, 25.15])
    res = compare(a, b)
    assert len(res["sector_mismatch"]) == 2
    assert all(m < 0.005 for m in res["sector_mismatch"])
