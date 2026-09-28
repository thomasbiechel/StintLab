"""Künstliches Rennen mit Positionsdaten für Tests und Vorschauen der Reels.

B fährt exakt A's Linie mit der Verzögerung gap(t) – der laufende Abstand
ist also bekannt und kann in Tests geprüft werden.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

T0 = datetime(2026, 9, 27, 11, 0, tzinfo=timezone.utc)
LENGTH_M = 6000.0
UNIT = 10.0          # Positionen in Dezimetern, wie vermutlich bei OpenF1
RATE_HZ = 3.7


def _curve(n: int = 4000) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Geschlossene Strecke, breiter als hoch, mit Weglänge LENGTH_M."""
    u = np.linspace(0, 2 * np.pi, n)
    x = 1.6 * np.cos(u) + 0.25 * np.cos(3 * u)
    y = 0.7 * np.sin(u) + 0.15 * np.sin(5 * u)
    seg = np.hypot(np.diff(x), np.diff(y))
    s = np.concatenate([[0.0], np.cumsum(seg)])
    k = LENGTH_M / s[-1]
    return s * k, x * k, y * k


def make_race(gaps: list[float], sc_laps: tuple[int, int] | None = None, lap_s: float = 100.0,
              sc_lap_s: float = 150.0, drivers=("RUS", "VER"), official: float | None = None) -> dict:
    """gaps[n-1] = Abstand B hinter A am Ende von Runde n."""
    n_laps = len(gaps)
    s_curve, cx, cy = _curve()
    lap_times = [sc_lap_s if sc_laps and sc_laps[0] <= n <= sc_laps[1] else lap_s for n in range(1, n_laps + 1)]
    a_ends = np.cumsum(lap_times)                      # Sekunden ab Start
    a_starts = np.concatenate([[0.0], a_ends[:-1]])

    def s_a(t):
        """Gefahrene Strecke von A (m) – innerhalb der Runde leicht ungleichmäßig."""
        t = np.asarray(t, dtype=float)
        n = np.clip(np.searchsorted(a_ends, t), 0, n_laps - 1)
        tau = np.clip((t - a_starts[n]) / np.array(lap_times)[n], -1, 2)
        frac = tau + 0.03 * np.sin(2 * np.pi * tau)
        return (n + frac) * LENGTH_M

    gap_knots_t = np.concatenate([[0.0], a_ends])
    gap_knots = np.concatenate([[gaps[0] * 0.3], gaps])

    def gap(t):
        return np.interp(t, gap_knots_t, gap_knots)

    def xy(s):
        s = np.mod(s, LENGTH_M)
        return np.interp(s, s_curve, cx) * UNIT, np.interp(s, s_curve, cy) * UNIT

    ts = np.arange(-10.0, a_ends[-1] + 30.0, 1 / RATE_HZ)
    sa = s_a(ts)
    sb = s_a(ts - gap(ts))
    a, b = drivers
    loc = {a: [], b: []}
    for t, p, q in zip(ts, sa, sb):
        date = (T0 + timedelta(seconds=float(t))).isoformat()
        (ax_, ay_), (bx_, by_) = xy(p), xy(q)
        loc[a].append({"date": date, "x": float(ax_), "y": float(ay_)})
        loc[b].append({"date": date, "x": float(bx_), "y": float(by_)})
    speed = np.gradient(sa, ts) * 3.6
    car = [{"date": (T0 + timedelta(seconds=float(t))).isoformat(), "speed": float(v)} for t, v in zip(ts, speed)]

    # B überquert die Linie, wenn t − gap(t) = Durchfahrt von A (eine Näherungsstufe reicht)
    b_ends = [e + gap(e - gap(e)) for e in a_ends]
    at = lambda sec: T0 + timedelta(seconds=float(sec))
    lap_ends = {a: {n: at(e) for n, e in enumerate(a_ends, 1)},
                b: {n: at(e) for n, e in enumerate(b_ends, 1)}}
    laps = []
    for drv, ends in ((a, a_ends), (b, b_ends)):
        starts = np.concatenate([[0.0], ends[:-1]])
        for n, (s, e) in enumerate(zip(starts, ends), 1):
            laps.append({"Driver": drv, "LapNumber": n, "LapStart": at(s) if n > 1 else None,
                         "LapTime": float(e - s) if n > 1 else None, "IsPitOutLap": False})
    rc = []
    if sc_laps:
        rc = [{"lap": sc_laps[0], "category": "SafetyCar", "flag": None, "message": "SAFETY CAR DEPLOYED"},
              {"lap": sc_laps[1], "category": "SafetyCar", "flag": None, "message": "SAFETY CAR IN THIS LAP"}]
    final = gaps[-1] if official is None else official
    return {"lap_ends": lap_ends, "laps": laps, "location": loc, "car_data": {a: car},
            "teams": {a: "Mercedes", b: "Red Bull Racing"}, "race_control": rc, "pit_stops": [],
            "results": [{"driver": a, "position": 1, "gap": 0, "duration": float(a_ends[-1]), "laps": n_laps},
                        {"driver": b, "position": 2, "gap": final, "duration": None, "laps": n_laps}]}


def baku_like() -> dict:
    g = list(np.linspace(4.3, 12.55, 30)) + list(np.linspace(9.0, 0.31, 8)) + \
        [0.34, 0.5, 0.62, 0.71, 0.6, 0.55, 0.48, 0.52, 0.45, 0.4, 0.38, 0.35] + [0.196]
    return make_race([float(v) for v in g], sc_laps=(31, 38))
