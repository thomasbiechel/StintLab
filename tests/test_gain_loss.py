"""Tests für das Gain/Loss-Reel (nur die Rechenteile, ohne Video)."""

import numpy as np
import pytest

from stintlab.reels.gain_loss import (FPS, fmt_net, pick_open_lap, sector_balance, smooth_circular,
                                      timeline)

# Baku-artig: B schneller in S3, langsamer in S1 und S2
DELTAS = {
    "Sector1": {40: 0.2, 41: 0.1, 42: 0.3},
    "Sector2": {40: 0.3, 41: 0.2, 42: 0.2},
    "Sector3": {40: -0.4, 41: -0.5, 42: -0.45},
}


def test_sector_balance_splits_gain_and_loss():
    bal = sector_balance(DELTAS)
    assert bal["gain_sectors"] == ["Sector3"]
    assert bal["loss_sectors"] == ["Sector1", "Sector2"]
    assert bal["gain"] == pytest.approx(0.45)
    assert bal["loss"] == pytest.approx(0.2 + 0.2)
    assert bal["per_lap"][0] == (40, pytest.approx(0.4), pytest.approx(0.5))


def test_sector_balance_refuses_one_sided_duel():
    with pytest.raises(ValueError):
        sector_balance({s: {1: 0.1, 2: 0.2} for s in DELTAS})


def test_net_close_to_zero_is_not_shown_as_false_precision():
    assert fmt_net(0.016) == "≈ 0.0 s"
    assert fmt_net(-0.2) == "−0.20 s"


def test_smooth_circular_fills_gaps_across_the_line():
    v = np.array([1.0, np.nan, 1.0, 1.0, np.nan])
    out = smooth_circular(v, width=3)
    assert len(out) == len(v)
    assert np.allclose(out, 1.0)


def test_open_lap_is_the_closest_one_after_the_line():
    x = np.linspace(0, 1000, 100)
    per_lap = {1: np.full(100, 0.8), 2: np.full(100, 0.3), 3: np.full(100, 0.5)}
    per_lap[3][50] = 0.1           # nah dran, aber nicht nach der Ziellinie → zählt nicht
    assert pick_open_lap(per_lap, x, 1000) == 2


def test_timeline_length():
    frames = timeline()
    assert len(frames) == pytest.approx(21 * FPS, abs=5)
    assert frames[0][0] == "open"
    assert frames[-1][0] == "ask"
