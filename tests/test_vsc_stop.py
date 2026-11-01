"""Tests für die Was-wäre-wenn-Rechnung „Stopp unter VSC“ – mit einem Mini-Rennen mit bekannten Zahlen."""

from datetime import datetime, timedelta, timezone

import pytest
from matplotlib import pyplot as plt

from stintlab.analyses.vsc_stop import (backtest, pace_delta, rejoin, render_vsc_pace, render_vsc_stop,
                                        simulate_stop, summarize, traffic_floor, tyre_at_flag)

T0 = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
LAPS = 12
STOP = 7          # REF stoppt in Runde 7 (In-Lap) und 8 (Out-Lap), je +10 s
REF_LAPS = [100.0] * 6 + [110.0, 110.0] + [99.0] * 4


def race(extra_laps=None, ref_laps=None):
    """AAA bleibt draußen (0,5 s/Runde langsamer als REF vor dem Stopp), REF stoppt in 7/8 und fährt danach
    1 s schneller, OTH fährt konstant 102 s. Mit extra_laps kommen weitere Fahrer dazu (BBB: macht denselben
    Stopp wie REF, in den Tests des Rückwärtstests)."""
    ref = ref_laps or REF_LAPS
    times = {
        "REF": ref,
        "AAA": [100.5] * 6 + [101.0] * 6,
        "OTH": [102.0] * LAPS,
    }
    times.update(extra_laps or {})
    ends, laps = {}, []
    for drv, ts in times.items():
        t = 0.0
        ends[drv] = {}
        for n, lt in enumerate(ts, 1):
            t += lt
            ends[drv][n] = T0 + timedelta(seconds=t)
            laps.append({"Driver": drv, "LapNumber": n, "LapTime": lt, "IsPitOutLap": False})
    return {"lap_ends": ends, "laps": laps, "race_control": [], "pit_stops": [], "results": [],
            "teams": {"REF": "Ferrari", "AAA": "Ferrari", "BBB": "Mercedes", "OTH": "McLaren"}, "stints": []}


def test_pace_delta_is_median_and_ignores_pit_laps():
    data = race()
    # Ausreißer in AAA Runde 3 (Out-Lap) darf den Median nicht beeinflussen
    for lap in data["laps"]:
        if lap["Driver"] == "AAA" and lap["LapNumber"] == 3:
            lap["LapTime"], lap["IsPitOutLap"] = 130.0, True
    delta, n = pace_delta(data, "AAA", "REF", 2, 6)
    assert delta == pytest.approx(0.5)
    assert n == 4                                  # Runde 3 fehlt


def test_pace_delta_needs_enough_clean_laps():
    with pytest.raises(ValueError, match="Zu wenige saubere Runden"):
        pace_delta(race(), "AAA", "REF", 5, 6)


def test_simulation_numbers_and_ranks():
    sim = simulate_stop(race(), "AAA", ["REF"], STOP, extras=(0.0, 0.3, 0.6), window=5)
    assert sim["winner"] == "AAA"                  # echt gewinnt AAA: Draußenbleiben war hier schneller
    assert sim["real"]["REF"] == pytest.approx(7.0)
    assert sim["real_rank"] == 1
    bw = [s["behind_winner"] for s in sim["scenarios"]]
    # Rückstand auf den Sieger = 7 (REF) + 3 (Abstand nach Runde 6) + 6 Runden · (0,5 + Zuschlag)
    assert bw == pytest.approx([13.0, 14.8, 16.6])
    assert [s["rank"] for s in sim["scenarios"]] == [2, 2, 3]    # OTH liegt 15 s hinter dem Sieger


def test_summary_counts_ranks_over_all_scenarios():
    s = summarize(simulate_stop(race(), "AAA", ["REF"], STOP, extras=(0.0, 0.3, 0.6), window=5))
    assert s["best"] == 2 and s["worst"] == 3
    assert s["counts"] == {2: 2, 3: 1}
    assert s["min"] == pytest.approx(13.0) and s["max"] == pytest.approx(16.6)
    assert s["gain_s"] == pytest.approx(0.0 - 14.8)    # real 0 s hinter dem Sieger, simuliert 14,8 s dahinter


def test_backtest_is_exact_when_the_driver_really_did_the_same():
    data = race(extra_laps={"BBB": [t + 0.5 for t in REF_LAPS]})
    result = backtest(data, "BBB", "REF", STOP, window=5)
    assert result["error"] == pytest.approx(0.0)
    assert result["real"] == pytest.approx(6.0)
    assert result["laps"] == 6


def test_backtest_error_has_the_sign_prediction_minus_real():
    # BBB ist nach dem Stopp 4 Runden lang 0,7 s/Runde langsamer als vorhergesagt → Vorhersage zu optimistisch (< real)
    data = race(extra_laps={"BBB": [t + 0.5 for t in [100.0] * 6 + [110.0, 110.0]] + [99.0 + 0.5 + 0.7] * 4})
    result = backtest(data, "BBB", "REF", STOP, window=5)
    assert result["error"] == pytest.approx(-4 * 0.7)


def test_rejoin_names_the_cars_around_the_driver():
    # nach der Out-Lap (Runde 8): AAA wäre 4,0 s hinter REF, OTH liegt dann 4,0 s VOR REF (also 8 s vor AAA)
    r = rejoin(race(), "AAA", "REF", STOP, window=5, radius=3.0)
    assert r["lap"] == 8
    assert r["rank"] == 3
    assert r["near"] == []
    close = rejoin(race(), "AAA", "REF", STOP, window=5, radius=5.0)
    assert [d for d, _ in close["near"]] == ["REF"]                # 4 s davor
    wide = rejoin(race(), "AAA", "REF", STOP, window=5, radius=9.0)
    assert [d for d, _ in wide["near"]] == ["OTH", "REF"]        # sortiert: wer weiter vorne liegt, zuerst
    assert wide["near"][0][1] == pytest.approx(-8.0)


def test_traffic_floor_is_none_without_cars_nearby():
    data = race()
    sim = simulate_stop(data, "AAA", ["REF"], STOP, window=5)
    assert traffic_floor(data, sim, radius=3.0) is None        # nach der Out-Lap niemand innerhalb von 3 s


def test_traffic_floor_is_never_better_than_the_pace_band():
    data = race()
    sim = simulate_stop(data, "AAA", ["REF"], STOP, window=5)
    floor = traffic_floor(data, sim, radius=5.0, hold=1.0)     # REF liegt 4 s davor
    assert floor["car"] == "REF"
    # REF kommt 7 s hinter dem Sieger ins Ziel (+1 s = 8 s) – besser als das Band (bis 16,6 s): Band gilt
    assert floor["behind_winner"] == pytest.approx(16.6)


def test_traffic_floor_sticks_behind_the_car_next_to_the_driver():
    # OTH liegt nach der Out-Lap 3,0 s vor AAAs simulierter Position und kommt 22,5 s hinter dem Sieger ins Ziel
    data = race(extra_laps={"OTH": [102.625] * LAPS})
    sim = simulate_stop(data, "AAA", ["REF"], STOP, window=5)
    floor = traffic_floor(data, sim, radius=3.0, hold=1.0)
    assert floor["car"] == "OTH"
    assert floor["behind_winner"] == pytest.approx(23.5)       # 22,5 + 1,0 s
    assert floor["rank"] == 3                                  # hinter REF und OTH
    assert summarize(sim)["worst"] == 2                        # das Band selbst hatte P2


def test_bad_inputs_are_clear_errors():
    data = race()
    with pytest.raises(ValueError, match="Referenzfahrer"):
        simulate_stop(data, "AAA", ["XXX"], STOP)
    with pytest.raises(ValueError, match="mindestens einen Referenzfahrer"):
        simulate_stop(data, "AAA", [], STOP)
    with pytest.raises(ValueError, match="stop_lap"):
        simulate_stop(data, "AAA", ["REF"], 99)


def test_tyre_at_flag_counts_laps_including_tyre_age_at_start():
    data = race()
    data["stints"] = [{"driver": "AAA", "stint": 1, "compound": "MEDIUM", "lap_start": 1, "lap_end": 5,
                       "tyre_age_at_start": 0},
                      {"driver": "AAA", "stint": 2, "compound": "SOFT", "lap_start": 6, "lap_end": 12,
                       "tyre_age_at_start": 3}]
    assert tyre_at_flag(data, "AAA") == ("SOFT", 10, 6)           # 3 + 7 Runden
    assert tyre_at_flag(data, "OTH") is None


def test_slides_render_without_errors():
    data = race()
    data["stints"] = [{"driver": "AAA", "stint": 1, "compound": "SOFT", "lap_start": 1, "lap_end": 12,
                       "tyre_age_at_start": 0}]
    fig, ax = plt.subplots()
    result = render_vsc_stop(ax, data, "AAA", ["REF"], STOP, top=4)
    assert result["band"]["n"] == 3
    assert result["floor"] is None                                # keine Autos in 3 s Nähe → keine zweite Zeile
    data2 = race(extra_laps={"OTH": [102.625] * LAPS})
    fig, ax = plt.subplots()
    assert render_vsc_stop(ax, data2, "AAA", ["REF"], STOP, top=4)["floor"]["car"] == "OTH"
    fig, ax = plt.subplots()
    times = render_vsc_pace(ax, data, ["AAA", "REF"], 9, 12)
    assert sorted(times["AAA"]) == [9, 10, 11, 12]
    plt.close("all")
