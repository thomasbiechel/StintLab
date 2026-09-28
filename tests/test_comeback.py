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
    assert speed[i] == pytest.approx(0.45, abs=0.02)
    assert speed[0] > 0.95
    assert ts[0] == pytest.approx(100.0 - 2.2)
