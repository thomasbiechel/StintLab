"""Tests für den Windschatten-Effekt: Abstand zum Auto davor und Basislinie."""

from datetime import datetime, timedelta, timezone

from stintlab.analyses.tow_effect import binned, compute_tow_effect

T0 = datetime(2026, 9, 26, 11, 0, tzinfo=timezone.utc)


def race(follow_gap=0.5, n_laps=10):
    """RUS allein vorne (320 km/h), VER dicht dahinter (330), BOT weit weg."""
    ends, laps = {}, []
    for drv, offset, st in (("RUS", 0.0, 320), ("VER", follow_gap, 330), ("BOT", 20.0, 310)):
        ends[drv] = {n: T0 + timedelta(seconds=100 * n + offset) for n in range(1, n_laps + 1)}
        laps += [{"Driver": drv, "LapNumber": n, "SpeedST": st, "IsPitOutLap": False}
                 for n in range(1, n_laps + 1)]
    return {"lap_ends": ends, "laps": laps, "race_control": [], "pit_stops": []}


def test_gap_to_car_ahead_and_baseline():
    data = race()
    # BOT bekommt ein paar Runden direkt hinter VER → mit Windschatten
    for n in (8, 9, 10):
        data["lap_ends"]["BOT"][n] = data["lap_ends"]["VER"][n] + timedelta(seconds=0.4)
        next(l for l in data["laps"] if l["Driver"] == "BOT" and l["LapNumber"] == n)["SpeedST"] = 322
    pts = compute_tow_effect(data)
    bot = {p["lap"]: p for p in pts if p["driver"] == "BOT"}
    assert round(bot[9]["gap"], 2) == 0.4
    assert bot[9]["delta"] == 12          # 322 − Basislinie 310
    assert bot[3]["delta"] == 0


def test_driver_without_free_air_has_no_baseline():
    pts = compute_tow_effect(race())
    assert "VER" not in {p["driver"] for p in pts}      # nie mehr als 3 s frei


def test_lap_one_and_sc_laps_are_skipped():
    data = race()
    data["race_control"] = [{"lap": 5, "category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"},
                            {"lap": 5, "category": "SafetyCar", "message": "SAFETY CAR IN THIS LAP"}]
    laps = {p["lap"] for p in compute_tow_effect(data) if p["driver"] == "RUS"}
    assert 1 not in laps and 5 not in laps and 6 not in laps


def test_binned_medians():
    pts = [{"gap": 0.2, "delta": 12}, {"gap": 0.4, "delta": 14}, {"gap": 4.0, "delta": 0}]
    assert binned(pts)[0] == (0.25, 13.0, 2)
