"""Tests für die Studio-Logik (ohne Oberfläche)."""

import tomllib
from datetime import datetime, timezone

import pytest

from stintlab.registry import ANALYSES, REELS
from stintlab.studio_core import (PARAMS, REEL_PARAMS, clean_values, countdown, current_or_last, default_folder,
                                  next_weekend, reel_entry, session_types, to_toml)

CAL = [{"meeting_key": 1, "meeting_name": "Pre-Season Testing", "date_start": "2026-02-11T08:00:00+00:00",
        "date_end": "2026-02-13T17:00:00+00:00", "location": "Bahrain"},
       {"meeting_key": 2, "meeting_name": "Azerbaijan GP", "date_start": "2026-09-24T09:00:00+00:00",
        "date_end": "2026-09-27T13:00:00+00:00", "location": "Baku", "year": 2026},
       {"meeting_key": 3, "meeting_name": "Malaysia GP", "date_start": "2026-10-02T04:00:00+00:00",
        "date_end": "2026-10-04T09:00:00+00:00", "location": "Kuala Lumpur"},
       {"meeting_key": 4, "meeting_name": "Cancelled GP", "date_start": "2026-10-05T04:00:00+00:00",
        "date_end": "2026-10-06T09:00:00+00:00", "location": "X", "is_cancelled": True}]
NOW = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)


def test_every_param_belongs_to_a_real_analysis_or_reel():
    assert set(PARAMS) <= set(ANALYSES)
    assert set(REEL_PARAMS) <= set(REELS)


def test_next_and_current_weekend():
    assert next_weekend(CAL, NOW)["meeting_key"] == 3              # Baku vorbei, Tests zählen nicht
    assert current_or_last(CAL, NOW)["meeting_key"] == 2
    during = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    assert next_weekend(CAL, during)["meeting_key"] == 3           # läuft gerade


def test_default_folder_matches_weekend_py():
    assert default_folder(CAL[1], "Q") == "posts/2026-baku/quali"
    assert default_folder({"location": "São Paulo", "date_start": "2024-11-01"}, "R", "-reel") == "posts/2024-sao-paulo/race-reel"


def test_clean_values_drops_defaults_and_checks_required():
    params = PARAMS["gap_between"]
    assert clean_values({"drivers": ["RUS", "VER"], "laps": [39, 50]}, params) == {"drivers": ["RUS", "VER"], "laps": [39, 50]}
    with pytest.raises(ValueError, match="genau 2"):
        clean_values({"drivers": ["RUS"]}, params)
    with pytest.raises(ValueError, match="fehlt"):
        clean_values({}, params)
    assert clean_values({"kind": "drivers", "top": 10}, PARAMS["championship"]) == {}      # alles Standard


def test_comeback_reel_entry_builds_pass_table():
    e = reel_entry("comeback", {"drivers": ["VER"], "pass_lap": 43, "pass_rival": "OCO", "pass_side": "left",
                                "order": "moment_first", "rain": True})
    assert e == {"analysis": "comeback", "drivers": ["VER"], "order": "moment_first", "rain": True,
                 "pass": {"lap": 43, "rival": "OCO", "side": "left"}}
    with pytest.raises(ValueError, match="Runde UND Gegner"):
        reel_entry("comeback", {"drivers": ["VER"], "pass_lap": 43})


def test_toml_round_trip_is_what_make_post_reads():
    config = {"session": {"meeting_key": 1295, "type": "R"},
              "slides": [{"analysis": "championship", "kind": "teams", "title": "MERCEDES \"CLEAR\"", "reel": True}],
              "reels": [{"analysis": "ghost_lap", "part": "Q3", "compare": {"meeting_key": 1269},
                         "cover": {"title": "Pole '26 vs '25", "kicker": "Russell"}}]}
    back = tomllib.loads(to_toml(config, "Test\nzweite Zeile"))
    assert back["slides"][0]["title"] == 'MERCEDES "CLEAR"' and back["slides"][0]["reel"] is True
    assert back["reels"][0]["compare"] == {"meeting_key": 1269}
    assert back["reels"][0]["cover"]["kicker"] == "Russell"


def test_session_types_in_weekend_order():
    ss = [{"session_name": "Race", "date_start": "2026-09-27T11:00:00+00:00"},
          {"session_name": "Qualifying", "date_start": "2026-09-26T12:00:00+00:00"},
          {"session_name": "Practice 1", "date_start": "2026-09-25T08:30:00+00:00"}]
    assert session_types(ss) == ["FP1", "Q", "R"]


def test_countdown_text():
    assert countdown(datetime(2026, 10, 2, 13, 0, tzinfo=timezone.utc), NOW) == "in 3 T 3 Std"
    assert countdown(datetime(2026, 9, 29, 11, 30, tzinfo=timezone.utc), NOW) == "in 1 Std 30 Min"
    assert countdown(datetime(2026, 9, 28, tzinfo=timezone.utc), NOW) == "läuft / vorbei"
