"""Tests für die Rennpace: welche Runden als sauber zählen."""

from datetime import datetime, timedelta, timezone

from stintlab.analyses.race_pace import clean_laps

T0 = datetime(2026, 9, 26, 11, 0, tzinfo=timezone.utc)


def race(driver, lap_times, start=T0):
    """Runden hintereinander; LapStart und lap_ends aus den Zeiten."""
    laps, ends, t = [], {}, start
    for n, lt in enumerate(lap_times, start=1):
        laps.append({"Driver": driver, "LapNumber": n, "LapTime": lt, "IsPitOutLap": False, "LapStart": t})
        t = t + timedelta(seconds=lt)
        ends[n] = t
    return laps, ends


def test_lap_one_pit_laps_and_outliers_are_excluded():
    laps, ends = race("VER", [110.0, 100.0, 100.2, 115.0, 101.0, 100.1, 99.9])
    laps[4]["IsPitOutLap"] = True                                  # Runde 5 = Out-Lap
    data = {"laps": laps, "lap_ends": {"VER": ends}, "race_control": [],
            "pit_stops": [{"driver": "VER", "lap": 4}]}            # Runde 4 = In-Lap
    clean, stats = clean_laps(data)
    assert clean["VER"] == [100.0, 100.2, 100.1, 99.9]
    assert stats["lap 1"] == 1 and stats["pit"] == 2


def test_outlier_over_107_percent_is_dropped():
    laps, ends = race("VER", [110.0, 100.0, 100.3, 108.0, 100.1])  # 108 > 107 % von 100
    clean, stats = clean_laps({"laps": laps, "lap_ends": {"VER": ends}, "race_control": []})
    assert 108.0 not in clean["VER"] and stats["outlier"] == 1


def test_sc_laps_of_leader_are_excluded_for_lapped_driver_too():
    # Führender VER: SC in seinen Runden 3–4. Überrundeter BOT hat andere
    # Rundennummern, aber seine Runden in diesem Zeitraum müssen ebenfalls raus.
    ver, ver_ends = race("VER", [100.0] * 6)
    bot, bot_ends = race("BOT", [104.0] * 5, start=T0 + timedelta(seconds=30))
    rc = [{"lap": 3, "category": "SafetyCar", "flag": None, "message": "SAFETY CAR DEPLOYED"},
          {"lap": 4, "category": "SafetyCar", "flag": None, "message": "SAFETY CAR IN THIS LAP"}]
    clean, stats = clean_laps({"laps": ver + bot, "lap_ends": {"VER": ver_ends, "BOT": bot_ends},
                               "race_control": rc})
    # VER: Runden 3, 4 raus → 2, 5, 6 bleiben
    assert len(clean["VER"]) == 3
    # BOT: Runden, die sich mit 200–400 s überschneiden (seine 2, 3, 4) raus → nur 5 bleibt
    assert len(clean["BOT"]) == 1
    assert stats["SC/VSC/red"] == 2 + 3


def test_short_team_names_are_used():
    from stintlab.analyses.race_pace import SHORT_TEAM
    assert SHORT_TEAM["Red Bull Racing"] == "Red Bull" and SHORT_TEAM["Haas F1 Team"] == "Haas"
