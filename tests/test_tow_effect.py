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


# --- Aufteilung Windschatten / Overtake Mode --------------------------------

from stintlab.analyses.tow_effect import compute_tow_split, render_tow_split  # noqa: E402


def _set(data, drv, n, gap_to_ver=None, speed=None):
    if gap_to_ver is not None:
        data["lap_ends"][drv][n] = data["lap_ends"]["VER"][n] + timedelta(seconds=gap_to_ver)
    if speed is not None:
        next(l for l in data["laps"] if l["Driver"] == drv and l["LapNumber"] == n)["SpeedST"] = speed


def test_split_mode_vs_tow_only():
    data = race(n_laps=12)
    # BOT Runde 8: schon am Rundenbeginn (Linie nach Runde 7) 0,5 s hinter VER → Modus
    _set(data, "BOT", 7, gap_to_ver=0.5)
    _set(data, "BOT", 8, gap_to_ver=0.5, speed=324)
    # BOT Runde 11: am Rundenbeginn 1,8 s, am Ende 0,6 s → nur Windschatten
    _set(data, "BOT", 10, gap_to_ver=1.8)
    _set(data, "BOT", 11, gap_to_ver=0.6, speed=317)
    res = compute_tow_split(data)
    assert res["mode"]["deltas"] == [14]        # 324 − 310
    # Runde 7 (Anfahrt von 20 s auf 0,5 s, 310 km/h) ist ebenfalls "nur Windschatten"
    assert sorted(res["tow"]["deltas"]) == [0, 7]   # 317 − 310
    assert res["restart"]["n"] == 0


def test_split_real_detection_gap_overrides_proxy():
    data = race(n_laps=12)
    _set(data, "BOT", 10, gap_to_ver=1.8)
    _set(data, "BOT", 11, gap_to_ver=0.6, speed=317)
    res = compute_tow_split(data, detection_gaps={("BOT", 11): 0.9})
    assert res["mode"]["deltas"] == [7] and res["tow"]["n"] == 0


def test_split_restart_lap_is_own_group_and_not_in_baseline():
    data = race(n_laps=12)
    data["race_control"] = [{"lap": 5, "category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"},
                            {"lap": 5, "category": "SafetyCar", "message": "SAFETY CAR IN THIS LAP"}]
    _set(data, "BOT", 5, gap_to_ver=0.5)
    _set(data, "BOT", 6, gap_to_ver=0.4, speed=321)
    res = compute_tow_split(data)
    assert res["restart"]["deltas"] == [11]
    assert 11 not in res["mode"]["deltas"] + res["tow"]["deltas"]
    # tow_effect selbst bleibt unverändert: Restart-Runde nicht drin
    assert 6 not in {p["lap"] for p in compute_tow_effect(data) if p["driver"] == "BOT"}


def test_split_renders(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    data = race(n_laps=40)
    for n in range(20, 40, 2):                  # abwechselnd Modus / nur Windschatten
        _set(data, "BOT", n, gap_to_ver=0.5)
        _set(data, "BOT", n + 1, gap_to_ver=0.7, speed=322)
    for n in range(21, 40, 4):
        _set(data, "BOT", n - 1, gap_to_ver=1.6)
    fig, ax = plt.subplots()
    res = render_tow_split(ax, data)
    assert res["mode"]["n"] + res["tow"]["n"] >= 10
    fig.savefig(tmp_path / "split.png")
