"""Tests für den Vorjahresvergleich im Ghost-Lap-Reel."""

import numpy as np
import pytest

from stintlab.reels.ghost_lap import align_track, check_messages


def _track(n=800):
    """Strecke mit Kurven (keine Symmetrie, sonst ist die Drehung nicht eindeutig)."""
    u = np.linspace(0, 2 * np.pi, n, endpoint=False)
    x = 3000 * np.cos(u) + 800 * np.cos(3 * u) + 300 * np.sin(5 * u)
    y = 1800 * np.sin(u) + 500 * np.sin(2 * u)
    return np.column_stack([x, y])


def test_align_recovers_rotation_offset_and_scale():
    a = _track()
    ang = np.radians(23.0)
    R = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    b = (0.97 * (R @ a.T)).T + [1234.0, -567.0]            # „Vorjahr“ in anderen Koordinaten
    b += np.random.default_rng(1).normal(0, 2.0, b.shape)     # Messrauschen
    s, R2, t, resid = align_track(a, b)
    back = (s * (R2 @ b.T)).T + t
    assert s == pytest.approx(1 / 0.97, rel=0.005)
    assert np.abs(back - a).mean() < 5.0
    assert resid < 5.0


def test_align_flags_a_different_layout():
    a = _track()
    b = a.copy()
    b[200:260, 1] += 400.0                                   # „Umbau“: ein Streckenteil woanders
    *_, resid = align_track(a, b)
    assert resid > 10.0


def test_check_messages():
    ok = {"align_m": 1.0, "scale": 1.0, "length_a": 6000.0, "length_b": 6010.0, "rain_a": False, "rain_b": False}
    assert check_messages(ok, ("2026", "2025")) == []
    bad = dict(ok, align_m=9.0, length_b=6200.0, rain_b=True, rain_a=None)
    msgs = check_messages(bad, ("2026", "2025"))
    assert any("übereinander" in m for m in msgs)
    assert any("Rundenlänge" in m for m in msgs)
    assert any("Regen im Qualifying 2025" in m for m in msgs)
    assert any("Kein Wetter für 2026" in m for m in msgs)
