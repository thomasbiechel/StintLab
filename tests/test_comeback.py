"""Tests für das Comeback-Reel: Überholmanöver richtig einordnen."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from stintlab.reels.comeback import count, decisive_pass, position_events, slowmo_times

T0 = datetime(2026, 9, 6, 13, 0)


def _race():
    """A startet P4 und gewinnt: B überholt (Strecke), D fällt aus, C an der Box,
    C holt sich den Platz zurück, A überholt C in Runde 4 zum Sieg."""
    order = {1: ["D", "C", "A", "B"], 2: ["A", "C", "B"], 3: ["C", "A", "B"], 4: ["A", "C", "B"]}
    lap_ends = {d: {} for d in "ABCD"}
    for n, drivers in order.items():
        for i, d in enumerate(drivers):
            lap_ends[d][n] = T0 + timedelta(seconds=90 * n + i)
    return {"lap_ends": lap_ends, "grid": {"D": 1, "C": 2, "B": 3, "A": 4},
            "results": [{"driver": "A", "position": 1}, {"driver": "C", "position": 2},
                        {"driver": "B", "position": 3}, {"driver": "D", "position": None, "dnf": True}],
            # B: Stopp unter roter Flagge (zählt nicht), C: echter Stopp in Runde 2
            "pit_stops": [{"driver": "B", "lap": 1, "duration": 1840.0},
                          {"driver": "C", "lap": 2, "duration": 23.0}]}


def test_gains_are_split_into_track_retirement_and_pit():
    mine, _, events = position_events(_race(), "A")
    assert mine == {0: 4, 1: 3, 2: 1, 3: 2, 4: 1}
    got = [(e["lap"], e["rival"], e["gain"], e["kind"]) for e in events]
    assert got == [(1, "B", True, "track"), (2, "D", True, "dnf"), (2, "C", True, "pit"),
                   (3, "C", False, "track"), (4, "C", True, "track")]
    assert count(events, True, "track") == 2
    assert count(events, True, "track", upto=3) == 1


def test_decisive_pass_is_the_last_one_onto_the_final_place():
    mine, pos, events = position_events(_race(), "A")
    assert decisive_pass(mine, pos, events) == (4, "C")


def test_unknown_driver_is_a_clear_error():
    with pytest.raises(ValueError, match="XYZ"):
        position_events(_race(), "XYZ")


def test_slowmo_is_slowest_at_the_pass_and_normal_far_away():
    ts = slowmo_times(100.0, 4.5)
    speed = np.diff(ts) * 60
    i = int(np.argmin(np.abs(ts[:-1] - 100.0)))
    assert speed[i] == pytest.approx(0.5, abs=0.02)
    assert speed[0] > 0.95
    assert ts[0] == pytest.approx(100.0 - 2.0)


def test_runner_up_only_for_the_winner_with_official_gap():
    from stintlab.reels.comeback import runner_up
    data = {"results": [{"driver": "ANT", "position": 1, "gap": 0},
                        {"driver": "RUS", "position": 2, "gap": 3.857},
                        {"driver": "VER", "position": 3, "gap": "+1 LAP"}]}
    assert runner_up(data, "ANT") == ("RUS", 3.857)
    assert runner_up(data, "RUS") is None        # nicht gewonnen → kein Abstand „zum Zweiten“


def test_runner_up_without_numeric_gap_is_none():
    from stintlab.reels.comeback import runner_up
    data = {"results": [{"driver": "ANT", "position": 1}, {"driver": "RUS", "position": 2, "gap": "+1 LAP"}]}
    assert runner_up(data, "ANT") is None


def _prep_for_frames():
    from stintlab.reels.comeback import FPS, HOOK_CUT_S, HOOK_S, PASS_S
    t_pass = 1000.0
    return {"hook_times": t_pass - HOOK_CUT_S - HOOK_S + np.arange(int(HOOK_S * FPS)) / FPS,
            "pass_times": slowmo_times(t_pass, PASS_S), "finish_times": np.arange(10.0),
            "result_times": np.arange(5.0), "laps": list(range(0, 54)), "lap": 50, "last_lap": 53}


def test_moment_first_shows_the_pass_before_the_chart_and_does_not_rewind():
    from stintlab.reels.comeback import frame_list
    prep = _prep_for_frames()
    frames = frame_list(prep, "moment_first")
    phases = [p for p, _ in frames]
    order = [phases[0]] + [phases[i] for i in range(1, len(phases)) if phases[i] != phases[i - 1]]
    assert order == ["hook", "pass", "chart", "finish", "result"]
    first_pass = next(v for p, v in frames if p == "pass")
    assert prep["pass_times"][int(first_pass)] > prep["hook_times"][-1]     # kein Zurückspringen
    assert max(v for p, v in frames if p == "chart") == pytest.approx(53)    # Rückblende bis zum Ende
    assert len(frames) < len(frame_list(prep))                              # etwas kürzer als klassisch


def test_classic_order_unchanged_and_unknown_order_rejected():
    from stintlab.reels.comeback import frame_list
    phases = [p for p, _ in frame_list(_prep_for_frames())]
    order = [phases[0]] + [phases[i] for i in range(1, len(phases)) if phases[i] != phases[i - 1]]
    assert order == ["hook", "chart", "pass", "finish", "result"]
    with pytest.raises(ValueError):
        frame_list(_prep_for_frames(), "random")

def test_moment_first_timing_has_no_jump_at_the_cut():
    """Hook und Manöver bilden eine Kurve: kein Tempo-Sprung beim Schnitt (war: 1,0 → 0,6)."""
    from stintlab.reels.comeback import FPS, moment_times
    hook, pas = moment_times(1000.0)
    speed = np.diff(np.concatenate([hook, pas])) * FPS
    assert np.abs(np.diff(speed)).max() < 0.02
    assert hook[-1] < 1000.0 < pas[-1]
    assert speed.min() == pytest.approx(0.5, abs=0.02)      # am Überholpunkt halbe Geschwindigkeit
