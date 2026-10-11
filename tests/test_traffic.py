"""Tests für stintlab/traffic.py – Autos vor einem Fahrer erkennen."""

import numpy as np

from stintlab.traffic import UNITS_PER_M, cars_ahead, closest

V = 80.0                      # m/s ≈ 288 km/h
LAP = 60.0
T0 = 1_000_000.0


def _straight(start_m: float, speed: float, t0: float = T0, dur: float = LAP, lateral_m: float = 0.0):
    """Auto auf einer langen Geraden (x in OpenF1-Einheiten), 4 Hz."""
    t = np.arange(0.0, dur, 0.25)
    x = (start_m + speed * t) * UNITS_PER_M
    y = np.full_like(t, lateral_m * UNITS_PER_M)
    return t0 + t, x, y


def _path():
    t = np.arange(0.0, LAP + 0.25, 0.25)
    return t, V * t * UNITS_PER_M, np.zeros_like(t)


def test_car_40_m_ahead_at_same_speed_is_half_a_second():
    ev = cars_ahead(T0, LAP, _path(), {"BOT": _straight(40.0, V)})
    near = closest(ev)
    assert "BOT" in near and abs(near["BOT"]["gap_s"] - 0.5) < 0.05
    assert abs(near["BOT"]["gap_m"] - 40.0) < 2.0


def test_pit_lane_car_standing_next_to_the_track_is_ignored():
    # steht 10 m neben der Strecke, 2 m „vor ihm“ – wie die Box in Kuala Lumpur
    t = np.arange(0.0, LAP, 0.25)
    standing = (T0 + t, np.full_like(t, 2.0 * UNITS_PER_M), np.full_like(t, 10.0 * UNITS_PER_M))
    assert cars_ahead(T0, LAP, _path(), {"PIT": standing}) == []


def test_slower_car_being_overtaken_gives_no_tow():
    # Abkühlrunde mit halbem Tempo direkt vor ihm
    ev = cars_ahead(T0, LAP, _path(), {"SLOW": _straight(30.0, V * 0.5)})
    assert ev == []


def test_car_behind_or_beyond_window_is_not_reported():
    ev = cars_ahead(T0, LAP, _path(), {"BEHIND": _straight(-50.0, V), "FAR": _straight(900.0, V)})
    assert ev == []


def test_zone_filter():
    ev = cars_ahead(T0, LAP, _path(), {"BOT": _straight(40.0, V)})
    assert closest(ev, (100.0, 200.0)) == {}               # km 100–200 gibt es auf der Runde nicht
    assert "BOT" in closest(ev, (0.0, 1.0))
