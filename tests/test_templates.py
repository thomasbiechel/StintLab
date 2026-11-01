"""Tests für die Titel-Vorschläge."""

from stintlab.templates import _short, slide_title


def test_short_gap_keeps_precision_for_tiny_gaps():
    assert _short(0.837) == "0.8"
    assert _short(0.060) == "0.06"
    assert _short(0.009) == "0.009"      # nicht „0.01“ (+11 %)
    assert _short(0.0196) == "0.020"


def test_telemetry_title_does_not_split_number_and_unit():
    title, suggested = slide_title("telemetry", "Q", {"gap": 0.009, "P1": "HAMILTON", "P2": "RUSSELL"})
    assert suggested and title == "WHERE HAMILTON FOUND 0.009 S"
