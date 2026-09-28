"""Tests für das Race-Story-Reel."""

import numpy as np
import pytest

from stintlab.reels.race_story import (FPS, CHART_S, CHART_ZOOM_S, chart_frames, frame_list,
                                       live_gap, prepare, smooth)
from tests.fake_race import LENGTH_M, UNIT, make_race

GAPS = [2.0, 3.0, 4.0, 5.0, 6.0, 3.0, 1.0, 0.8, 0.6, 0.5]


@pytest.fixture(scope="module")
def prep():
    return prepare(make_race(GAPS, sc_laps=(6, 7), official=0.45), {})


def test_default_track_lap_is_the_lap_before_the_safety_car(prep):
    assert prep["track_lap"] == 5
    assert prep["peak"] == pytest.approx(6.0, abs=0.1)


def test_live_gap_on_the_map_matches_the_known_gap(prep):
    # Runde 5: Abstand wächst von 5 auf 6 s
    g = prep["map_gap"][~np.isnan(prep["map_gap"])]
    assert len(g) > 0.9 * len(prep["map_gap"])
    assert 4.9 < g.min() and g.max() < 6.1


def test_final_lap_live_gap_and_official_final(prep):
    g = prep["fin_gap"]
    assert np.nanmedian(g) == pytest.approx(0.5, abs=0.08)
    assert prep["final"] == pytest.approx(0.45)


def test_scale_is_found_from_speed(prep):
    assert prep["scale"] == pytest.approx(UNIT, rel=0.03)


def test_finish_is_crossed_at_the_end_of_the_last_lap(prep):
    lap_end = 5 * 100 + 2 * 150 + 3 * 100
    # t0 ist das Ende von Runde 1 (100 s) → Ziel bei lap_end − 100
    assert prep["t_finish"] == pytest.approx(lap_end - 100, abs=0.3)


def test_track_lap_from_config():
    p = prepare(make_race(GAPS, sc_laps=(6, 7)), {"track_lap": 2})
    assert p["track_lap"] == 2
    assert np.nanmedian(p["map_gap"]) == pytest.approx(2.5, abs=0.3)


def test_track_lap_one_without_lap_start():
    p = prepare(make_race(GAPS, sc_laps=(6, 7)), {"track_lap": 1})
    assert p["win"][1] - p["win"][0] > 50


def test_chart_zooms_only_after_the_safety_car():
    x = np.arange(1, 11, dtype=float)
    fr = chart_frames(x, [(6, 7)])
    assert len(fr) == int((CHART_S + CHART_ZOOM_S) * FPS)
    assert fr[0][2] == 0.0 and fr[-1][2] == pytest.approx(1.0)
    assert fr[int(CHART_S * FPS) - 1][1] == pytest.approx(8.0)
    assert all(z == 0.0 for _, _, z in chart_frames(x, []))


def test_frame_list_order(prep):
    phases = []
    for p, _, _ in frame_list(prep):
        if not phases or phases[-1] != p:
            phases.append(p)
    assert phases == ["open", "map", "chart", "final", "result"]


def test_smooth_skips_nan():
    out = smooth(np.array([1.0, np.nan, 3.0]), 3)
    assert list(out) == [1.0, 2.0, 3.0]


def test_final_timeline_slows_to_real_time_at_the_finish():
    from stintlab.reels.race_story import FINAL_AFTER_S, final_timeline
    t, v, zoom = final_timeline(1000.0, 52.0)
    assert t[0] == pytest.approx(948.0)
    assert t[-1] == pytest.approx(1000.0 + FINAL_AFTER_S)
    assert np.all(np.diff(t) > 0)
    assert v[0] > 10 and v[-1] == pytest.approx(1.0)
    assert zoom[0] > zoom[-1]
    # Echtzeit am Ende: ein Videobild ≈ 1/60 s echte Zeit
    assert (t[-1] - t[-2]) * FPS == pytest.approx(1.0, rel=0.1)


def test_final_window_from_config():
    p = prepare(make_race(GAPS, sc_laps=(6, 7)), {"final_window": 20})
    assert p["t_finish"] - p["fin_times"][0] == pytest.approx(20.0)


def test_open_window_ends_well_before_the_finish(prep):
    from stintlab.reels.race_story import OPEN_END_MIN_S
    assert prep["open_times"][-1] <= prep["t_finish"] - OPEN_END_MIN_S + 0.05
    assert prep["open_times"][0] >= prep["t_finish"] - 200   # innerhalb der Zielrunde (100 s) + Rand


def test_open_at_from_config():
    p = prepare(make_race(GAPS, sc_laps=(6, 7), official=0.45), {"open_at": 30})
    assert p["open_times"][0] == pytest.approx(p["t_finish"] - 30, abs=0.01)
