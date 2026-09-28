"""Tests für den Abstand über die Runde – mit künstlichem Rennen, dessen Abstand bekannt ist."""

import numpy as np

from stintlab.analyses.gap_on_lap import compute_gap_on_lap
from tests.fake_race import LENGTH_M, make_race


def test_constant_gap_is_found_everywhere_on_the_lap():
    data = make_race([0.8] * 8)
    res = compute_gap_on_lap(data, "RUS", "VER", (3, 6))
    assert sorted(res["per_lap"]) == [3, 4, 5, 6]
    med = res["median"][~np.isnan(res["median"])]
    assert len(med) > 0.9 * len(res["median"])
    assert np.allclose(med, 0.8, atol=0.08)


def test_growing_gap_rises_through_the_lap():
    # Abstand wächst in Runde 5 von 1,0 auf 2,0 s
    data = make_race([1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 2.0])
    g = compute_gap_on_lap(data, "RUS", "VER", (5, 5))["per_lap"][5]
    first, last = np.nanmean(g[:10]), np.nanmean(g[-10:])
    assert first < 1.3 and last > 1.7


def test_lap_length_in_metres():
    res = compute_gap_on_lap(make_race([0.5] * 6), "RUS", "VER", (3, 4))
    assert abs(res["length_m"] - LENGTH_M) / LENGTH_M < 0.03
