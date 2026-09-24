"""Tests für die Zuordnung von Messpunkten zu Runden."""

from datetime import datetime, timedelta, timezone

from stintlab.session import assign_to_laps, build_session_data, sign_mismatches

T0 = datetime(2026, 9, 13, 13, 0, tzinfo=timezone.utc)


def at(seconds):
    return T0 + timedelta(seconds=seconds)


def test_each_lap_gets_last_sample_before_its_end():
    samples = {"4": [(at(10), 1.0), (at(85), 2.0), (at(95), 3.0)]}
    ends = {("4", 1): at(90), ("4", 2): at(180)}
    assert assign_to_laps(samples, ends) == {("4", 1): 2.0, ("4", 2): 3.0}


def test_long_vsc_lap_does_not_shift_later_laps():
    # Runde 2 dauert unter VSC 150 s statt 90 s und hat viele Messpunkte.
    # Gleichmäßiges Verteilen würde danach alle Runden verschieben –
    # die Zuordnung über Zeitstempel darf das nicht.
    ends = {("4", 1): at(90), ("4", 2): at(240), ("4", 3): at(330)}
    samples = {"4": [(at(80), 1.0)] + [(at(100 + i), 9.9) for i in range(0, 130, 5)] + [(at(320), 3.0)]}
    result = assign_to_laps(samples, ends)
    assert result[("4", 1)] == 1.0
    assert result[("4", 3)] == 3.0


def test_stale_sample_is_dropped():
    samples = {"4": [(at(10), 1.0)]}
    ends = {("4", 1): at(90), ("4", 5): at(500)}
    assert assign_to_laps(samples, ends) == {("4", 1): 1.0}


def test_build_session_data_and_order_check():
    iso = lambda s: at(s).isoformat()
    raw = {
        "drivers": [{"driver_number": 4, "name_acronym": "NOR", "team_name": "McLaren"},
                    {"driver_number": 12, "name_acronym": "ANT", "team_name": "Mercedes"}],
        "laps": [{"driver_number": 4, "lap_number": 1, "date_start": iso(0), "lap_duration": 90},
                 {"driver_number": 12, "lap_number": 1, "date_start": iso(0), "lap_duration": 91}],
        "intervals": [{"driver_number": 4, "date": iso(88), "gap_to_leader": None},
                      {"driver_number": 12, "date": iso(88), "gap_to_leader": 0.8}],
        "position": [{"driver_number": 4, "date": iso(5), "position": 1},
                     {"driver_number": 12, "date": iso(5), "position": 2}],
        "race_control": [], "pit": [],
    }
    data = build_session_data(raw)
    assert data["teams"] == {"NOR": "McLaren", "ANT": "Mercedes"}
    assert {(r["Driver"], r["Gap"]) for r in data["gap_to_leader"]} == {("NOR", 0.0), ("ANT", 0.8)}
    assert sign_mismatches(data, "NOR", "ANT") == []

    # Positionen vertauscht → muss als Widerspruch erkannt werden
    raw["position"] = [{"driver_number": 4, "date": iso(5), "position": 2},
                       {"driver_number": 12, "date": iso(5), "position": 1}]
    assert sign_mismatches(build_session_data(raw), "NOR", "ANT") == [(1, False)]

    # Dieselbe Abweichung in einer Boxenstopp-Runde wird als solche markiert
    raw["pit"] = [{"driver_number": 12, "lap_number": 1, "pit_duration": 30.0}]
    assert sign_mismatches(build_session_data(raw), "NOR", "ANT") == [(1, True)]


def test_stints_are_mapped_to_driver_abbreviations():
    raw = {
        "drivers": [{"driver_number": 16, "name_acronym": "LEC", "team_name": "Ferrari"}],
        "laps": [], "intervals": [], "position": [], "race_control": [], "pit": [],
        "stints": [{"driver_number": 16, "stint_number": 2, "compound": "hard",
                    "lap_start": 49, "lap_end": 57, "tyre_age_at_start": 0},
                   {"driver_number": 16, "stint_number": 1, "compound": "MEDIUM",
                    "lap_start": 1, "lap_end": 48, "tyre_age_at_start": 0}],
    }
    stints = build_session_data(raw)["stints"]
    assert [(s["driver"], s["stint"], s["compound"]) for s in stints] == [
        ("LEC", 1, "MEDIUM"), ("LEC", 2, "HARD")]