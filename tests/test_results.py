"""Tests für die Ergebnis-Slide (Training)."""

from stintlab.analyses.results import practice_rows, result_mismatches


def base(results, laps, stints=None, race_control=None):
    return {"session_type": "FP3", "results": results, "laps": laps,
            "stints": stints or [], "race_control": race_control or []}


def res(driver, pos, best, gap, laps=20):
    return {"driver": driver, "position": pos, "duration": best, "gap": gap, "laps": laps,
            "points": 0, "dnf": False, "dns": False, "dsq": False}


def lap(driver, num, t, out=False):
    return {"Driver": driver, "LapNumber": num, "LapTime": t, "IsPitOutLap": out}


def test_rows_sorted_by_position_and_no_time_last():
    data = base([res("ALO", None, None, None, 0), res("VER", 2, 104.2, 0.2), res("RUS", 1, 104.0, None)],
                [lap("RUS", 5, 104.0), lap("VER", 6, 104.2)])
    assert [r["driver"] for r in practice_rows(data)] == ["RUS", "VER", "ALO"]


def test_tyre_of_best_lap_comes_from_its_stint():
    data = base([res("RUS", 1, 104.0, None)], [lap("RUS", 3, 105.5), lap("RUS", 12, 104.0)],
                stints=[{"driver": "RUS", "compound": "MEDIUM", "lap_start": 1, "lap_end": 8},
                        {"driver": "RUS", "compound": "SOFT", "lap_start": 9, "lap_end": 15}])
    assert practice_rows(data)[0]["compound"] == "SOFT"


def test_matching_data_gives_no_warning():
    data = base([res("RUS", 1, 104.0, None)], [lap("RUS", 12, 104.0)],
                stints=[{"driver": "RUS", "compound": "SOFT", "lap_start": 1, "lap_end": 15}])
    assert result_mismatches(data) == []


def test_mismatch_is_reported():
    # Offizielle Zeit 104.0, schnellste gültige Runde in den Daten 104.5
    data = base([res("RUS", 1, 104.0, None)], [lap("RUS", 12, 104.5)],
                stints=[{"driver": "RUS", "compound": "SOFT", "lap_start": 1, "lap_end": 15}])
    problems = result_mismatches(data)
    assert any("offiziell" in p for p in problems)


def test_deleted_lap_does_not_count_as_fastest():
    # Gestrichene 103.5 darf nicht mit der offiziellen 104.0 verglichen werden
    msgs = [{"message": "CAR 63 (RUS) TIME 1:43.500 DELETED - TRACK LIMITS AT TURN 1 LAP 10 14:00:00"}]
    data = base([res("RUS", 1, 104.0, None)], [lap("RUS", 10, 103.5), lap("RUS", 12, 104.0)],
                stints=[{"driver": "RUS", "compound": "SOFT", "lap_start": 1, "lap_end": 15}],
                race_control=msgs)
    assert result_mismatches(data) == []


def test_session_result_is_loaded_from_openf1():
    from stintlab.session import build_session_data
    raw = {"drivers": [{"driver_number": 63, "name_acronym": "RUS", "team_name": "Mercedes"}],
           "laps": [], "intervals": [], "position": [], "race_control": [], "pit": [], "stints": [],
           "session_result": [{"driver_number": 63, "position": 1, "duration": 103.759,
                               "gap_to_leader": 0, "number_of_laps": 24, "points": 0,
                               "dnf": False, "dns": False, "dsq": False}]}
    [r] = build_session_data(raw)["results"]
    assert (r["driver"], r["position"], r["duration"], r["laps"]) == ("RUS", 1, 103.759, 24)


def test_qualifying_rows_and_eliminations():
    from stintlab.analyses.results import qualifying_rows
    data = {"session_type": "Q", "results": [
        {"driver": "NOR", "position": 1, "duration": [93.469, 92.873, 91.824], "dnf": False, "dns": False, "dsq": False},
        {"driver": "RUS", "position": 6, "duration": [93.211, 92.85, 92.149], "dnf": False, "dns": False, "dsq": False},
        {"driver": "ALB", "position": 14, "duration": [93.9, 93.4, None], "dnf": False, "dns": False, "dsq": False},
        {"driver": "STR", "position": 20, "duration": [94.8, None, None], "dnf": False, "dns": False, "dsq": False},
    ]}
    rows = qualifying_rows(data)
    assert [r["driver"] for r in rows] == ["NOR", "RUS", "ALB", "STR"]
    assert rows[2]["times"] == [93.9, 93.4, None]
    assert rows[3]["times"] == [94.8, None, None]


def test_drivers_without_time_are_named_not_hidden():
    # Echter Fall Madring Q 2026: BEA und STR gemeldet, aber ohne Zeit
    from stintlab.analyses.results import unclassified
    data = {"teams": {"NOR": "McLaren", "BEA": "Haas F1 Team", "STR": "Aston Martin"},
            "results": [{"driver": "NOR", "position": 1, "duration": [93.469, 92.873, 91.824]}]}
    assert unclassified(data) == ["BEA", "STR"]
