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


# ── Rennen, echte Werte Madring 2026 ────────────────────────────────────────
def _race_data():
    res = [
        {"driver": "ANT", "position": 1, "gap": 0, "duration": 5663.754, "laps": 57, "points": 25.0},
        {"driver": "VER", "position": 2, "gap": 4.351, "duration": 5668.105, "laps": 57, "points": 18.0},
        {"driver": "LIN", "position": 9, "gap": "+1 LAP", "duration": None, "laps": 56, "points": 2.0},
        {"driver": "BEA", "position": 16, "gap": "+1 LAP", "duration": None, "laps": 56, "points": 0.0},
        {"driver": "PER", "position": None, "gap": None, "duration": None, "laps": 31, "points": 0.0, "dnf": True},
        {"driver": "SAI", "position": None, "gap": None, "duration": None, "laps": 43, "points": 0.0, "dnf": True},
    ]
    for r in res:
        r.setdefault("dnf", False); r.setdefault("dns", False); r.setdefault("dsq", False)
    return {"session_type": "R", "results": res,
            "grid": {"NOR": 1, "ANT": 2, "VER": 3, "LIN": 10, "BEA": 22, "PER": 18, "SAI": 20},
            "pit_stops": [{"driver": "ANT", "lap": 14}, {"driver": "SAI", "lap": 23}, {"driver": "SAI", "lap": 31}],
            "laps": [{"Driver": "ANT", "LapNumber": 57}, {"Driver": "SAI", "LapNumber": 43}]}


def test_race_rows_order_and_places_gained():
    from stintlab.analyses.results import race_rows
    rows = race_rows(_race_data())
    # Klassierte nach Position, dann Ausfälle nach Runden (SAI 43 vor PER 31)
    assert [r["driver"] for r in rows] == ["ANT", "VER", "LIN", "BEA", "SAI", "PER"]
    by = {r["driver"]: r for r in rows}
    assert by["ANT"]["change"] == 1        # Start 2 → Ziel 1
    assert by["VER"]["change"] == 1
    assert by["BEA"]["change"] == 6        # Start 22 → Ziel 16
    assert by["SAI"]["change"] is None     # Ausfall: kein ▲▼
    assert by["SAI"]["pits"] == 2 and by["ANT"]["pits"] == 1


def test_race_plausibility_is_quiet_on_matching_data():
    from stintlab.analyses.results import race_mismatches
    assert race_mismatches(_race_data()) == []


def test_race_plausibility_reports_lap_mismatch():
    from stintlab.analyses.results import race_mismatches
    data = _race_data()
    data["laps"] = [{"Driver": "ANT", "LapNumber": 52}]
    assert any("ANT" in p for p in race_mismatches(data))


def test_grid_maps_numeric_driver_numbers_to_abbreviations():
    # Echter Fehler: numbers speichert "12" (Text), starting_grid liefert 12 (Zahl)
    from stintlab.session import build_grid
    numbers = {"ANT": "12", "NOR": "1", "SAI": "55"}
    raw = [{"position": 1, "driver_number": 1}, {"position": 2, "driver_number": 12},
           {"position": 20, "driver_number": 55}]
    assert build_grid(raw, numbers) == {"NOR": 1, "ANT": 2, "SAI": 20}


def test_driver_in_q2_without_time_is_not_shown_as_out_in_q1():
    # Echter Fall Baku 2026: ANT crasht in Q1, ist P16 (in Q2), fährt dort nicht
    from stintlab.analyses.results import part_sizes, qualifying_rows
    drivers = [f"D{i:02d}" for i in range(1, 23)]
    res = []
    for i, d in enumerate(drivers, start=1):
        q2 = 104.0 + i * 0.01 if i <= 15 else None      # P16 ohne Q2-Zeit
        q3 = 103.0 + i * 0.01 if i <= 10 else None
        res.append({"driver": d, "position": i, "duration": [105.0 + i * 0.01, q2, q3],
                    "dnf": False, "dns": False, "dsq": False})
    data = {"session_type": "Q", "results": res, "teams": {d: "X" for d in drivers}}
    assert part_sizes(data, qualifying_rows(data)) == (16, 10)


def test_part_sizes_for_twenty_entries():
    from stintlab.analyses.results import part_sizes
    rows = [{"times": [100.0, None, None]}] * 20
    assert part_sizes({"teams": {f"D{i}": "X" for i in range(20)}}, rows) == (15, 10)
