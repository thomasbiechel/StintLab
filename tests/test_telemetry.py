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


def test_frozen_speed_is_detected_and_bridged():
    import numpy as np
    from stintlab.analyses.telemetry import _drop_frozen, frozen_runs
    t = np.arange(0, 10, 0.25)
    v = 300 - t * 5.0
    v[12:30] = 308.0                        # 4,25 s derselbe Wert
    runs = frozen_runs(t, v)
    assert runs == [(3.0, 7.25)]
    t2, v2 = _drop_frozen(t, v, runs)
    assert 3.0 in t2 and 5.0 not in t2 and len(t2) == len(t) - 17
    # kurzes Plateau (0,5 s) ist normal – z. B. Vollgas am Limiter
    assert frozen_runs(np.arange(0, 2, 0.25), np.array([300, 301, 301, 301, 302, 303, 304, 305.0])) == []


def test_gap_is_not_smeared_across_a_frozen_gap():
    """Monza 2026 Q3: Die S1-Linie lag in Gaslys Datenlücke. Die Korrektur an der
    offiziellen Sektorzeit darf den Fehler aus der Lücke nicht in den ganzen
    Sektor davor verteilen (vorher: +0,35 s vor der Linie)."""
    import numpy as np
    from stintlab.analyses.telemetry import compare
    t = np.linspace(0, 90, 901)
    v = np.full_like(t, 250.0)
    a = {"t": t.copy(), "v": v.copy(), "lap_time": 90.0, "sectors": [30.0, 30.0, 30.0], "frozen": []}
    b = {"t": t * 90.3 / 90, "v": v * 90 / 90.3, "lap_time": 90.3, "sectors": [30.1, 30.1, 30.1], "frozen": []}
    # A: Lücke um die S1-Linie, dort falsches (zu langsames) Tempo
    hole = (t > 27) & (t < 34)
    a["v"][hole] = 150.0
    a["frozen"] = [(27.0, 34.0)]
    res = compare(a, b)
    before = res["frac"] < 0.28              # Sektor 1 vor der Lücke
    # B ist gleichmäßig langsamer → vor der Lücke wächst der Abstand nur langsam bis ~0,1 s
    assert np.nanmax(res["delta"][before]) < 0.15
