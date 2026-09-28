"""Tests für die Podium-Slide."""

import pytest

from stintlab.analyses.podium import podium_rows


def test_quali_podium_shows_q3_time_and_gaps():
    data = {"session_type": "Q", "teams": {"RUS": "Mercedes"}, "numbers": {"RUS": "63"},
            "results": [{"driver": "RUS", "position": 1, "duration": [103.6, 103.4, 102.526], "gap": [0, 0, 0]},
                        {"driver": "LEC", "position": 2, "duration": [104.3, 103.7, 103.363], "gap": [0.7, 0.3, 0.837]},
                        {"driver": "PIA", "position": 3, "duration": [105.0, 103.8, 103.364], "gap": [1.4, 0.4, 0.838]},
                        {"driver": "BOT", "position": 22, "duration": [108.3, None, None], "gap": [4.7, None, None]}]}
    rows = podium_rows(data)
    assert [r["line"] for r in rows] == ["1:42.526", "+0.837 s", "+0.838 s"]
    assert rows[0]["number"] == "63"


def test_race_podium_winner_and_lapped_gap():
    data = {"session_type": "R", "results": [{"driver": "ANT", "position": 1, "gap": 0},
                                             {"driver": "RUS", "position": 2, "gap": 3.857},
                                             {"driver": "VER", "position": 3, "gap": "+1 LAP"}]}
    assert [r["line"] for r in podium_rows(data)] == ["WINNER", "+3.857 s", "+1 LAP"]


def test_podium_needs_three_finishers():
    with pytest.raises(ValueError, match="ersten drei"):
        podium_rows({"session_type": "R", "results": [{"driver": "ANT", "position": 1}]})
