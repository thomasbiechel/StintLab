"""Tests für die Vorzeichen-Konvention – genau hier gab es im PDF-Report schon Fehler."""

from datetime import datetime, timedelta, timezone

from stintlab.analyses.gap_between import compute_gap_between
from stintlab.race_control import restricted_laps

T0 = datetime(2026, 9, 13, 13, 0, tzinfo=timezone.utc)


def test_driver_a_ahead_gives_positive_gap():
    # NOR überquert die Linie 1,5 s vor ANT
    ends = {"NOR": {1: T0}, "ANT": {1: T0 + timedelta(seconds=1.5)}}
    assert compute_gap_between(ends, "NOR", "ANT") == {1: 1.5}
    assert compute_gap_between(ends, "ANT", "NOR") == {1: -1.5}


def test_laps_missing_for_one_driver_are_skipped():
    ends = {"NOR": {1: T0, 2: T0 + timedelta(seconds=90)},
            "ANT": {1: T0 + timedelta(seconds=1)}}  # ANT ohne Runde 2
    assert compute_gap_between(ends, "NOR", "ANT") == {1: 1.0}


def test_leader_change_between_crossings_does_not_matter():
    # Genau der Fehlerfall der Gap-to-Leader-Differenz: Dazwischen fährt der
    # Führende an die Box. Mit Zieldurchfahrten spielt das keine Rolle.
    ends = {"ANT": {46: T0}, "NOR": {46: T0 + timedelta(seconds=3.4)}}
    assert compute_gap_between(ends, "ANT", "NOR") == {46: 3.4}


def test_vsc_marks_all_laps_from_deploy_to_ending():
    msgs = [
        {"lap": 20, "category": "SafetyCar", "message": "VIRTUAL SAFETY CAR DEPLOYED"},
        {"lap": 22, "category": "SafetyCar", "message": "VIRTUAL SAFETY CAR ENDING"},
    ]
    assert restricted_laps(msgs) == {20, 21, 22}


def test_madrid_vsc_format_is_detected():
    # Echtes Format aus den Madrid-Daten 2026: abgekürzt "VSC"
    msgs = [
        {"lap": 14, "category": "SafetyCar", "flag": None, "message": "VSC DEPLOYED"},
        {"lap": 15, "category": "Flag", "flag": "CLEAR", "message": "CLEAR IN TRACK SECTOR 22"},
        {"lap": 15, "category": "SafetyCar", "flag": None, "message": "VSC ENDING"},
    ]
    assert restricted_laps(msgs) == {14, 15}


def test_sector_clear_does_not_end_safety_car_early():
    # Safety Car von Runde 20 bis 25, zwischendurch wird ein Sektor freigegeben
    msgs = [
        {"lap": 20, "category": "SafetyCar", "flag": None, "message": "SAFETY CAR DEPLOYED"},
        {"lap": 21, "category": "Flag", "flag": "CLEAR", "message": "CLEAR IN TRACK SECTOR 7"},
        {"lap": 25, "category": "SafetyCar", "flag": None, "message": "SAFETY CAR IN THIS LAP"},
    ]
    assert restricted_laps(msgs) == {20, 21, 22, 23, 24, 25}

def _race_with_noisy_timestamps():
    """A und B, B jede Runde 0,1 s langsamer; Zeitstempel mit bis zu ±0,2 s Fehler."""
    from stintlab.analyses.gap_between import line_gaps  # noqa: F401
    noise = [0.0, 0.15, -0.2, 0.1, -0.05]
    ends = {"A": {}, "B": {}}
    laps = []
    t_a, t_b = 0.0, 0.5
    for n in range(1, 6):
        t_a += 100.0
        t_b += 100.1
        ends["A"][n] = T0 + timedelta(seconds=t_a)
        ends["B"][n] = T0 + timedelta(seconds=t_b + noise[n - 1])
        laps += [{"Driver": "A", "LapNumber": n, "LapTime": 100.0},
                 {"Driver": "B", "LapNumber": n, "LapTime": 100.1}]
    results = [{"driver": "A", "position": 1, "gap": 0.0}, {"driver": "B", "position": 2, "gap": 1.0}]
    return {"lap_ends": ends, "laps": laps, "results": results}


def test_line_gaps_count_back_from_the_official_finish_gap():
    from stintlab.analyses.gap_between import line_gaps
    gaps, exact_from = line_gaps(_race_with_noisy_timestamps(), "A", "B")
    assert exact_from == 1
    assert [round(gaps[n], 3) for n in range(1, 6)] == [0.6, 0.7, 0.8, 0.9, 1.0]


def test_line_gaps_fall_back_to_timestamps_without_official_gap():
    from stintlab.analyses.gap_between import line_gaps
    data = _race_with_noisy_timestamps()
    data["results"][1]["gap"] = "+1 LAP"
    gaps, exact_from = line_gaps(data, "A", "B")
    assert exact_from is None and round(gaps[3], 3) == round(0.8 - 0.2, 3)


def test_red_flag_after_safety_car_and_standing_restart():
    # Echte Reihenfolge Monza 2026 (gekürzt): SC, dann rote Flagge als "Other",
    # Neustart mit Formationsrunde und stehendem Start, später ein VSC
    msgs = [
        {"lap": 1, "category": "Other", "message": "RACE START"},
        {"lap": 3, "category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"},
        {"lap": 3, "category": "SessionStatus", "message": "SESSION ABORTED"},
        {"lap": 3, "category": "Other", "message": "RED FLAG - RACE SUSPENDED"},
        {"lap": 4, "category": "Flag", "flag": "CLEAR", "message": "TRACK CLEAR"},
        {"lap": 4, "category": "SessionStatus", "message": "SESSION STARTED"},
        {"lap": 4, "category": "Other", "message": "STANDING START"},
        {"lap": 5, "category": "Other", "message": "EXTRA FORMATION LAP"},
        {"lap": 5, "category": "Other", "message": "STANDING START"},
        {"lap": 28, "category": "SafetyCar", "message": "VSC DEPLOYED"},
        {"lap": 29, "category": "SafetyCar", "message": "VSC ENDING"},
    ]
    assert restricted_laps(msgs) == {3, 4, 5, 6, 28, 29}


def test_standing_start_at_race_start_is_not_restricted():
    msgs = [{"lap": 1, "category": "Other", "message": "STANDING START"}]
    assert restricted_laps(msgs) == set()


def test_chequered_flag_is_not_a_red_flag():
    """"CHEQUERED FLAG" enthält "RED FLAG" – darf die letzte Runde nicht sperren."""
    from stintlab.race_control import restricted_laps
    rc = [
        {"lap": 31, "category": "SafetyCar", "flag": None, "message": "SAFETY CAR DEPLOYED"},
        {"lap": 35, "category": "SafetyCar", "flag": None, "message": "SAFETY CAR IN THIS LAP"},
        {"lap": 51, "category": "Flag", "flag": "CHEQUERED", "message": "CHEQUERED FLAG"},
        {"lap": 51, "category": "SessionStatus", "flag": None, "message": "SESSION FINISHED"},
    ]
    assert restricted_laps(rc) == set(range(31, 36))


def test_red_flag_is_labelled_red_not_safety_car():
    # Monza 2026: SC und rote Flagge in derselben Runde -> ab dort RED,
    # Neustartrunden gehören zur roten Flagge, das spätere VSC bleibt VSC
    from stintlab.race_control import neutral_phases
    msgs = [
        {"lap": 1, "category": "Other", "message": "RACE START"},
        {"lap": 3, "category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"},
        {"lap": 3, "category": "SessionStatus", "message": "SESSION ABORTED"},
        {"lap": 3, "category": "Other", "message": "RED FLAG - RACE SUSPENDED"},
        {"lap": 4, "category": "Flag", "flag": "CLEAR", "message": "TRACK CLEAR"},
        {"lap": 4, "category": "SessionStatus", "message": "SESSION STARTED"},
        {"lap": 5, "category": "Other", "message": "EXTRA FORMATION LAP"},
        {"lap": 5, "category": "Other", "message": "STANDING START"},
        {"lap": 28, "category": "SafetyCar", "message": "VSC DEPLOYED"},
        {"lap": 29, "category": "SafetyCar", "message": "VSC ENDING"},
    ]
    assert neutral_phases(msgs) == [(3, 6, "RED"), (28, 29, "VSC")]


def test_safety_car_before_red_flag_keeps_its_laps():
    from stintlab.race_control import neutral_phases
    msgs = [
        {"lap": 10, "category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"},
        {"lap": 12, "category": "Flag", "flag": "RED", "message": "RED FLAG"},
        {"lap": 13, "category": "SessionStatus", "message": "SESSION STARTED"},
    ]
    assert neutral_phases(msgs) == [(10, 11, "SC"), (12, 13, "RED")]
