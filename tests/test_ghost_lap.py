"""Tests für das Ghost-Lap-Reel (ohne Video zu rendern)."""

from datetime import datetime, timedelta, timezone

import numpy as np

from stintlab.reels.ghost_lap import (FPS, HOOK_S, LAP_S, LOGO_S, REPLAY_S, REPLAY_WINDOW_S, RESULT_S,
                                      frame_times, gap_at, lap_positions, needs_rotation, orient,
                                      replay_start, smooth_interp)

START = datetime(2026, 9, 12, 14, 50, tzinfo=timezone.utc)


def test_frame_plan_covers_all_phases():
    frames = frame_times(91.824, 86.0)
    assert len(frames) == int((HOOK_S + LAP_S + REPLAY_S + RESULT_S + LOGO_S) * FPS)
    laps = [t for phase, t in frames if phase == "lap"]
    assert laps[0] == 0.0 and abs(laps[-1] - 91.824) < 1e-9
    replay = [t for phase, t in frames if phase == "replay"]
    assert replay[0] == 86.0 and abs(replay[-1] - 90.0) < 1e-9   # 4 echte Sekunden


def test_replay_window_is_where_the_gap_changes_most():
    # Abstand steigt langsam und bricht bei 85–88 s ein (wie NOR in Madrid)
    t = np.arange(0.0, 92.0, 0.5)
    delta = np.where(t < 85, t / 85 * 0.37, 0.37 - (np.clip(t, 85, 88) - 85) / 3 * 0.36)
    prep = {"a_frac": (t, t / t[-1]), "res": {"frac": t / t[-1], "delta": delta}}
    start = replay_start(prep, 91.5)
    assert start <= 85.0 and start + REPLAY_WINDOW_S >= 88.0


def test_smooth_interp_hits_points_and_has_no_corners():
    tt = np.array([0.0, 1.0, 2.0, 3.0])
    vv = np.array([0.0, 1.0, 0.0, 1.0])
    assert np.allclose(smooth_interp(tt, tt, vv), vv)          # trifft die Messpunkte
    # zwischen den Punkten gekrümmt statt gerade (lineare Mitte wäre 0.5)
    assert abs(float(smooth_interp(0.5, tt, vv)[0]) - 0.5) > 0.01


def test_wide_track_is_rotated_to_portrait():
    x, y = np.array([0.0, 100.0]), np.array([0.0, 30.0])
    assert needs_rotation(x, y)
    rx, ry = orient(x, y, True)
    assert (ry.max() - ry.min()) > (rx.max() - rx.min())
    assert not needs_rotation(np.array([0.0, 30.0]), np.array([0.0, 100.0]))


def test_lap_positions_only_around_the_lap():
    # Echte Beobachtung Madring: Punkte aus der Garage vor der Runde müssen weg
    loc = [{"date": (START + timedelta(seconds=s)).isoformat(), "x": s, "y": 0}
           for s in list(np.arange(-600, -590, 0.3)) + list(np.arange(-1, 93, 0.28))]
    lap = {"Driver": "NOR", "LapNumber": 18, "LapStart": START, "LapTime": 91.824}
    t, x, y = lap_positions(loc, lap)
    assert t.min() >= -2.0 and t.max() <= 91.824 + 2.0


def test_gap_sign_and_value_follow_compare():
    prep = {"a_frac": (np.array([0.0, 50.0, 100.0]), np.array([0.0, 0.5, 1.0])),
            "res": {"frac": np.array([0.0, 0.5, 1.0]), "delta": np.array([0.0, 0.4, 0.011])}}
    assert abs(gap_at(prep, 50.0) - 0.4) < 1e-9       # A liegt zur Rundenmitte 0,4 s vorne
    assert abs(gap_at(prep, 100.0) - 0.011) < 1e-9    # im Ziel exakt der Rundenabstand


def test_replay_can_be_set_by_track_kilometre():
    from stintlab.reels.ghost_lap import replay_from_config
    t = np.linspace(0.0, 100.0, 101)
    prep = {"a_frac": (t, t / 100.0), "res": {"frac": t / 100.0, "delta": t * 0.0, "length_m": 6000.0}}
    assert abs(replay_from_config(prep, {"replay_km": 3.0}, 100.0) - 50.0) < 1e-9   # 3 km von 6 km = Hälfte
    assert replay_from_config(prep, {"replay_start": 80}, 100.0) == 80.0


def test_without_replay_the_lap_runs_longer_and_total_stays_the_same():
    with_replay = frame_times(102.526, 60.0)
    without = frame_times(102.526, None)
    assert len(without) == len(with_replay)
    assert not any(phase == "replay" for phase, _ in without)
    assert sum(phase == "lap" for phase, _ in without) == int((LAP_S + REPLAY_S) * FPS)
