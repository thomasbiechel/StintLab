"""Tests für die Zuordnung von Runden zu Q1/Q2/Q3 – mit echten Werten aus
dem Madring-Qualifying 2026 (RUS)."""

from datetime import datetime, timezone

from stintlab.analyses.ideal_lap import ideal_laps
from stintlab.quali import lap_parts, quali_mismatches, session_parts


def ts(text):
    return datetime.fromisoformat(f"2026-09-12T{text}+00:00")


STATUS = [
    ("14:00:00.045", "SESSION STARTED"), ("14:18:00.039", "SESSION FINISHED"),
    ("14:25:00.033", "SESSION STARTED"), ("14:40:00.030", "SESSION FINISHED"),
    ("14:47:00.046", "SESSION STARTED"), ("15:00:00.053", "SESSION FINISHED"),
]
RACE_CONTROL = [{"date": ts(t), "category": "SessionStatus", "flag": None, "message": m} for t, m in STATUS]

# (Runde, Zeit, Out-Lap, Beginn) – Beginn = Ende der vorigen Runde
RUS = [(8, 190.586, True, "14:14:50.000"), (9, 93.211, False, "14:18:00.242"),
       (10, 117.655, False, "14:19:33.333"), (11, 323.257, True, "14:25:10.409"),
       (12, 92.85, False, "14:26:54.269"), (15, 93.518, False, "14:38:03.397"),
       (16, 126.762, False, "14:39:36.896"), (17, 434.604, True, "14:47:08.451"),
       (18, 92.265, False, "14:48:58.224"), (21, 92.149, False, "14:57:46.516")]


def laps():
    return [{"Driver": "RUS", "LapNumber": n, "LapTime": t, "IsPitOutLap": out, "LapStart": ts(start),
             "Sector1": t * 0.3, "Sector2": t * 0.4, "Sector3": t * 0.3}
            for n, t, out, start in RUS]


def test_three_parts_are_found():
    assert len(session_parts(RACE_CONTROL)) == 3


def test_lap_starting_just_after_the_flag_still_counts_for_that_part():
    # Echter Fall: RUS' schnellste Q1-Runde beginnt 0,2 s nach der Zielflagge
    parts = lap_parts({"laps": laps(), "race_control": RACE_CONTROL})
    assert parts[("RUS", 9)] == "Q1"
    assert parts[("RUS", 12)] == "Q2"
    assert parts[("RUS", 15)] == "Q2"
    assert parts[("RUS", 21)] == "Q3"
    assert ("RUS", 10) not in parts      # Abkühlrunde, beginnt erst nach der Flagge
    assert parts[("RUS", 16)] == "Q2"    # Abkühlrunde, beginnt noch vor der Flagge


def test_official_times_match_madrid():
    data = {"laps": laps(), "race_control": RACE_CONTROL,
            "results": [{"driver": "RUS", "duration": [93.211, 92.85, 92.149]}]}
    assert quali_mismatches(data) == []


def test_wrong_assignment_would_be_reported():
    data = {"laps": laps(), "race_control": RACE_CONTROL,
            "results": [{"driver": "RUS", "duration": [93.100, 92.85, 92.149]}]}
    assert any("RUS Q1" in p for p in quali_mismatches(data))


def test_ideal_lap_uses_only_sectors_of_the_chosen_part():
    data = {"laps": laps(), "race_control": RACE_CONTROL}
    [q3] = ideal_laps(data, part="Q3")
    assert q3["best"] == 92.149          # nicht die 92.85 aus Q2 o. Ä.
    [q2] = ideal_laps(data, part="Q2")
    assert q2["best"] == 92.85


def test_unexpected_number_of_parts_stops_with_clear_error():
    import pytest
    with pytest.raises(ValueError, match="Qualifying-Abschnitte"):
        lap_parts({"laps": laps(), "race_control": RACE_CONTROL[:4]})
