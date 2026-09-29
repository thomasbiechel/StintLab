"""Tests für das Race Preview (Daten, ohne Netz)."""

import tomllib
from datetime import date, datetime, timezone

import pytest

from stintlab import openf1
from stintlab import preview as pv


def test_form_weights_newest_most_and_missing_team():
    races = [{"place": "A", "pace": {"MER": 0.0, "FER": 1.0}},
             {"place": "B", "pace": {"MER": 0.0, "FER": 0.5}},
             {"place": "C", "pace": {"MER": 0.3, "FER": 0.0, "CAD": 2.0}}]
    form = pv.form_table(races)
    assert form["FER"] == pytest.approx((1 * 1.0 + 2 * 0.5 + 3 * 0.0) / 6)
    assert form["MER"] == pytest.approx(0.9 / 6)
    assert form["CAD"] == pytest.approx(2.0)                 # nur ein Rennen → dessen Wert


def test_form_with_fewer_races_uses_newest_weights():
    races = [{"place": "B", "pace": {"X": 1.0}}, {"place": "C", "pace": {"X": 0.0}}]
    assert pv.form_table(races)["X"] == pytest.approx(2 / 5)   # Gewichte 2, 3


def test_chances_mix_track_tiers_and_trend():
    races = [{"pace": {"MER": 0.0, "FER": 1.2, "CAD": 3.0}}, {"pace": {"MER": 0.1, "FER": 0.2, "CAD": 3.0}}]
    rows = pv.chances({"MER": 0.05, "FER": 0.5, "CAD": 3.0}, {"MER": 1.0, "FER": 0.0})
    by = {r["team"]: r for r in rows}
    assert by["MER"]["score"] == pytest.approx(0.75 * 0.05 + 0.25 * 1.0)
    assert by["CAD"]["score"] == 3.0                           # keine Vorjahresdaten → nur Form
    assert rows[0]["tier"] == "FAVOURITES" and by["CAD"]["tier"] == "OUTSIDERS"
    trend = {r["team"]: r["trend"] for r in pv.chances({"MER": 0, "FER": 0.5, "CAD": 3}, None, races)}
    assert trend == {"MER": 0, "FER": 1, "CAD": 0}


def test_team_alias_old_names():
    assert pv.team_name("Kick Sauber") == "Audi" and pv.team_name("Mercedes") == "Mercedes"


def _meeting():
    return {"meeting_key": 1308, "circuit_key": 12, "gmt_offset": "08:00:00",
            "date_start": "2026-10-02T04:30:00+00:00", "date_end": "2026-10-04T09:00:00+00:00"}


def test_weekend_days_local_dates_and_sessions():
    sessions = [{"session_name": "Practice 1", "date_start": "2026-10-02T04:30:00+00:00"},
                {"session_name": "Qualifying", "date_start": "2026-10-03T08:00:00+00:00"},
                {"session_name": "Race", "date_start": "2026-10-04T07:00:00+00:00"}]
    days = pv.weekend_days(_meeting(), sessions)
    assert [d["date"] for d in days] == [date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 4)]
    assert days[2]["sessions"] == [("RACE", datetime(2026, 10, 4, 15, 0))]


def test_parse_forecast_key_session_hour():
    days = [{"date": date(2026, 10, 4), "sessions": [("RACE", datetime(2026, 10, 4, 15, 0))]}]
    raw = {"daily": {"time": ["2026-10-04"], "weather_code": [61], "temperature_2m_max": [33.0],
                     "temperature_2m_min": [24.0], "precipitation_probability_max": [80],
                     "precipitation_sum": [12.0], "wind_speed_10m_max": [14.0]},
           "hourly": {"time": [f"2026-10-04T{h:02d}:00" for h in range(24)],
                      "temperature_2m": [20.0 + h for h in range(24)],
                      "precipitation_probability": [h for h in range(24)]}}
    (d,) = pv.parse_forecast(raw, days)["days"]
    assert d["tmax"] == 33.0 and d["code"] == 61 and d["sessions"] == ["RACE"]
    assert d["key"] == {"session": "RACE", "time": "15:00", "rain_pct": 15, "temp": 35.0}


def test_forecast_falls_back_to_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "WEATHER_DIR", tmp_path)
    days = [{"date": date(2026, 10, 4), "sessions": []}]
    good = {"daily": {"time": ["2026-10-04"], "temperature_2m_max": [30.0]}}
    assert pv.forecast(_meeting(), days, fetch=lambda *a: dict(good))["days"][0]["tmax"] == 30.0

    def offline(*a):
        raise OSError("kein Netz")
    assert pv.forecast(_meeting(), days, fetch=offline)["days"][0]["tmax"] == 30.0
    assert pv.forecast({**_meeting(), "circuit_key": 999}, days, fetch=offline) is None


def test_multiviewer_rotation_and_corners():
    raw = {"x": [0, 10, 10, 0], "y": [0, 0, 5, 5], "rotation": 90,
           "corners": [{"number": 1, "letter": "a", "angle": 0, "trackPosition": {"x": 10, "y": 0}}]}
    lay = pv.layout_from_multiviewer(raw)
    assert lay["x"][1] == pytest.approx(0) and lay["y"][1] == pytest.approx(10)   # 90° gedreht
    c = lay["corners"][0]
    assert c["number"] == "1a" and c["x"] == pytest.approx(0) and c["y"] == pytest.approx(10)
    assert c["ly"] > c["y"]                                   # Beschriftung nach außen versetzt


def test_query_aliases_and_next():
    ms = [{"meeting_key": 1, "location": "Baku", "date_start": "2026-09-24T04:00:00+00:00"},
          {"meeting_key": 2, "location": "Kuala Lumpur", "date_start": "2026-10-02T04:00:00+00:00"},
          {"meeting_key": 3, "location": "Marina Bay", "date_start": "2026-10-09T04:00:00+00:00"}]
    now = datetime(2026, 9, 28, tzinfo=timezone.utc)
    assert openf1.match_meetings(ms, "sepang", now)[0]["meeting_key"] == 2
    assert openf1.match_meetings(ms, "next", now)[0]["meeting_key"] == 2


def test_preview_toml_parses_and_names_favourites():
    from preview import preview_toml
    data = {"history": {"year": 2025}, "layout": {"source": "multiviewer"},
            "races": [{"place": "Monza"}], "form": {"Mercedes": 0.0, "Ferrari": 0.4},
            "chances": [{"team": "Mercedes", "tier": "FAVOURITES"}, {"team": "Ferrari", "tier": "IN THE MIX"}]}
    cfg = tomllib.loads(preview_toml({"meeting_key": 1308, "location": "Kuala Lumpur", "year": 2026}, data))
    assert cfg["session"]["type"] == "PREVIEW"
    assert [s["analysis"] for s in cfg["slides"]] == ["preview_track", "preview_weather", "preview_form",
                                                     "preview_chances"]
    assert cfg["slides"][3]["title"] == "Mercedes start as favourites"


def _ergast(races):
    return {"MRData": {"RaceTable": {"Races": races}}}


def _res(code, team, **kw):
    return {"Driver": {"code": code}, "Constructor": {"name": team}, **kw}


def test_jolpica_history_for_track_last_raced_before_2023(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "JOLPICA_DIR", tmp_path)
    answers = {
        "circuits/sepang/results/1": _ergast([
            {"season": "2016", "round": "16", "Results": [_res("RIC", "Red Bull")]},
            {"season": "2017", "round": "15", "Results": [_res("VER", "Red Bull")]}]),
        "2017/15/results": _ergast([{"season": "2017", "round": "15", "Results": [
            _res("VER", "Red Bull", laps="56"), _res("HAM", "Mercedes", laps="56"),
            _res("VET", "Ferrari", laps="56", FastestLap={"rank": "1", "lap": "50", "Time": {"time": "1:34.080"}})]}]),
        "2017/15/qualifying/1": _ergast([{"QualifyingResults": [_res("HAM", "Mercedes")]}]),
    }
    hist = pv.jolpica_history(_meeting() | {"year": 2026}, get=answers.__getitem__)
    assert (hist["year"], hist["winner"], hist["winner_team"], hist["pole"], hist["laps"]) == \
        (2017, "VER", "Red Bull Racing", "HAM", 56)
    assert hist["fastest"]["text"] == "1:34.080" and hist["fastest"]["time"] == pytest.approx(94.08)
    assert hist["track_pace"] == {}                            # zählt nicht in die Chancen

    def offline(path):
        raise OSError
    assert pv.jolpica_history(_meeting() | {"year": 2026}, get=offline)["winner"] == "VER"   # aus dem Cache


def test_preview_toml_old_track_is_back_not_new():
    from preview import preview_toml
    data = {"history": {"year": 2017, "source": "jolpica", "track_pace": {}}, "layout": None, "races": [],
            "form": {}, "chances": []}
    cfg = tomllib.loads(preview_toml({"meeting_key": 1308, "location": "Kuala Lumpur", "year": 2026}, data))
    assert cfg["slides"][0]["title"] == "Kuala Lumpur is back after 9 years"
    assert "Jolpica" in cfg["slides"][0]["source"]
    assert "2017 is too long ago" in cfg["slides"][3]["subtitle"]


def test_geojson_layout_in_metres_with_length():
    raw = {"features": [{"properties": {"length": 5543}, "geometry": {"type": "LineString", "coordinates": [
        [101.735, 2.760], [101.745, 2.760], [101.745, 2.770], [101.735, 2.770]]}}]}
    lay = pv.layout_from_geojson(raw)
    assert lay["source"] == "geojson" and lay["length_m"] == 5543 and lay["corners"] == []
    assert max(lay["x"]) - min(lay["x"]) == pytest.approx(1112, rel=0.01)     # 0,01° Länge am Äquator ≈ 1,1 km


def test_corner_labels_pushed_apart():
    from stintlab.analyses.preview import spread_labels
    (a, b, c) = spread_labels([(0, 0), (0.1, 0), (5, 5)], min_dist=1.0)
    assert abs(b[0] - a[0]) >= 0.99 and c == (5.0, 5.0)


def test_preview_toml_credits_geojson_track():
    from preview import preview_toml
    data = {"history": {"year": 2017, "source": "jolpica", "track_pace": {}}, "layout": {"source": "geojson"},
            "races": [], "form": {}, "chances": []}
    cfg = tomllib.loads(preview_toml({"meeting_key": 1308, "location": "Kuala Lumpur", "year": 2026}, data))
    assert cfg["slides"][0]["source"] == "Data: OpenF1 · Jolpica-F1 · f1-circuits"
