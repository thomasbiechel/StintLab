"""Tests für die Aufbereitung der Positionsdaten (Jojo und hängende Punkte)."""

import numpy as np

from stintlab.trackpos import drop_stalls, retime


def _circle(t, speed=85.0, r=500.0):
    a = speed * t / r
    return r * np.cos(a), r * np.sin(a)


def test_jittery_timestamps_give_smooth_speed():
    rng = np.random.default_rng(1)
    t_true = np.arange(0, 20, 0.25)
    x, y = _circle(t_true)
    t_meas = t_true + rng.uniform(-0.1, 0.1, len(t_true))      # Zeitstempel zittern
    order = np.argsort(t_meas)
    t, x, y = t_meas[order], x[order], y[order]
    raw = np.hypot(np.diff(x), np.diff(y)) / np.diff(t)
    t2, x2, y2 = retime(t, x, y)
    v = np.hypot(np.diff(x2), np.diff(y2)) / np.diff(t2)
    assert raw.std() > 15                     # vorher: starkes Jojo
    assert v[5:-5].std() < 0.25 * raw.std()   # nachher: fast gleichmäßig


def test_stalled_points_are_dropped_but_real_slow_corner_stays():
    t = np.arange(0, 12, 0.25)
    speed = np.where((t > 5) & (t < 7), 20.0, 80.0)          # echte langsame Kurve 5–7 s
    s = np.concatenate([[0], np.cumsum(speed[1:] * 0.25)])
    x, y = s.copy(), np.zeros_like(s)
    t2, _, _ = drop_stalls(t, x, y)
    assert len(t2) == len(t)                                  # nichts entfernt
    x_st = x.copy()
    x_st[40:44] = x_st[40]                                    # 1 s „hängen“ bei vollem Tempo
    t3, _, _ = drop_stalls(t, x_st, y)
    assert len(t3) < len(t) and 10.25 not in t3
