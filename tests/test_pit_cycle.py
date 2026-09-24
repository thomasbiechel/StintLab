"""Tests für die Zerlegung des Boxenstopp-Zyklus – mit den Madrid-Werten."""

from datetime import datetime, timedelta, timezone

import pytest

from stintlab.analyses.pit_cycle import compute_pit_cycle

T0 = datetime(2026, 9, 13, 13, 0, tzinfo=timezone.utc)


def madrid_like():
    # NOR 6,12 s vor ANT nach Runde 13, ANT 15,61 s vor NOR nach Runde 16
    return {
        "lap_ends": {
            "NOR": {13: T0, 16: T0 + timedelta(seconds=300 + 15.61)},
            "ANT": {13: T0 + timedelta(seconds=6.12), 16: T0 + timedelta(seconds=300)},
        },
        "pit_stops": [{"driver": "ANT", "lap": 14, "duration": 31.8},
                      {"driver": "NOR", "lap": 15, "duration": 35.1}],
    }


def test_parts_add_up_to_total_swing():
    v = compute_pit_cycle(madrid_like(), "ANT", "NOR", 13, 16)
    assert v["start"] == pytest.approx(-6.12)
    assert v["end"] == pytest.approx(15.61)
    assert v["stop_diff"] == pytest.approx(3.3)          # längere Durchfahrt NOR = Gewinn ANT
    assert v["rest"] == pytest.approx(21.73 - 3.3)
    assert v["start"] + v["stop_diff"] + v["rest"] == pytest.approx(v["end"])


def test_missing_stop_in_window_is_an_error():
    data = madrid_like()
    data["lap_ends"]["NOR"][14] = T0 + timedelta(seconds=90)
    data["lap_ends"]["ANT"][14] = T0 + timedelta(seconds=100)
    # Fenster 14–16: ANTs Stopp in Runde 14 liegt nicht mehr darin
    with pytest.raises(ValueError, match="genau einen Stopp"):
        compute_pit_cycle(data, "ANT", "NOR", 14, 16)