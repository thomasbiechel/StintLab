"""Tests für den Wochenend-Autopiloten: Wochenende finden, Vorlagen, Titel."""

from datetime import datetime, timezone

import tomllib

from stintlab.openf1 import match_meetings
from stintlab.templates import headline_facts, long_run_compound, post_toml, reel_toml
from weekend import slug

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
MEETINGS = [
    {"meeting_key": 1270, "meeting_name": "Bahrain Grand Prix", "location": "Sakhir", "country_name": "Bahrain",
     "circuit_short_name": "Sakhir", "date_start": "2026-04-10T11:30:00+00:00"},
    {"meeting_key": 1295, "meeting_name": "Azerbaijan Grand Prix", "location": "Baku", "country_name": "Azerbaijan",
     "circuit_short_name": "Baku", "date_start": "2026-09-24T08:30:00+00:00"},
    # 2026: das Rennen in Sepang läuft unter dem Namen „Bahrain Grand Prix“
    {"meeting_key": 1296, "meeting_name": "Bahrain Grand Prix", "location": "Sepang", "country_name": "Malaysia",
     "circuit_short_name": "Sepang", "date_start": "2026-10-02T04:30:00+00:00"},
]


def test_sepang_is_found_by_location_and_country():
    assert match_meetings(MEETINGS, "sepang", NOW)[0]["meeting_key"] == 1296
    assert match_meetings(MEETINGS, "Malaysia", NOW)[0]["meeting_key"] == 1296


def test_same_name_prefers_the_nearest_weekend():
    # „bahrain“ passt auf April (Sakhir) und Oktober (Sepang) – nächstliegend zuerst
    assert [m["meeting_key"] for m in match_meetings(MEETINGS, "bahrain", NOW)] == [1296, 1270]


def test_latest_and_meeting_key():
    assert match_meetings(MEETINGS, "latest", NOW)[0]["meeting_key"] == 1295   # Sepang noch nicht begonnen
    assert match_meetings(MEETINGS, "1270", NOW)[0]["location"] == "Sakhir"
    assert match_meetings(MEETINGS, "monza", NOW) == []


def test_headline_facts_handle_quali_gap_lists():
    results = [{"driver": "RUS", "position": 1, "gap": [0.0, 0.0, 0.0]},
               {"driver": "LEC", "position": 2, "gap": [0.3, 0.5, 0.837]},
               {"driver": "BOT", "position": None, "gap": None}]
    f = headline_facts(results, {"RUS": "Russell", "LEC": "Leclerc"})
    assert (f["p1"], f["P1"], f["P2"], f["gap"]) == ("RUS", "RUSSELL", "LECLERC", 0.837)


def test_templates_are_valid_toml_with_suggested_titles():
    facts = headline_facts([{"driver": "RUS", "position": 1, "gap": 0},
                            {"driver": "VER", "position": 2, "gap": 0.196}], {"RUS": "Russell", "VER": "Verstappen"})
    meeting = MEETINGS[2] | {"year": 2026}
    for stype in ("FP1", "FP2", "FP3", "SQ", "S", "Q", "R"):
        cfg = tomllib.loads(post_toml(meeting, stype, facts))
        assert cfg["session"] == {"meeting_key": 1296, "type": stype}
        # Qualifying/Sprint/Rennen: Podium als Titelseite, dann die Ergebnistabelle
        first = ["podium", "results"] if stype in ("SQ", "S", "Q", "R") else ["results"]
        assert [x["analysis"] for x in cfg["slides"][:len(first)]] == first
    race = tomllib.loads(post_toml(meeting, "R", facts))
    assert race["slides"][0]["title"] == "RUSSELL WINS BY 0.196 S"
    reel = tomllib.loads(reel_toml(meeting, "R", facts))
    assert reel["reels"][0]["result"] == "Russell wins by 0.196 s"
    assert reel_toml(meeting, "FP2", facts) is None


def test_slug_uses_the_location():
    assert slug(MEETINGS[2]) == "sepang"
    assert slug({"location": "São Paulo"}) == "sao-paulo"


def test_long_run_slide_uses_the_most_common_compound():
    runs = [{"driver": d, "compound": c} for d, c in
            (("ANT", "HARD"), ("RUS", "HARD"), ("LEC", "SOFT"), ("HAM", "SOFT"), ("SAI", "SOFT"),
             ("VER", "MEDIUM"), ("LEC", "HARD"))]
    assert long_run_compound(runs) == "SOFT"
    facts = headline_facts([{"driver": "RUS", "position": 1, "gap": 0}], {"RUS": "Russell"})
    cfg = tomllib.loads(post_toml(MEETINGS[2] | {"year": 2026}, "FP2", facts, "SOFT"))
    lr = next(s for s in cfg["slides"] if s["analysis"] == "long_runs")
    assert lr["compound"] == "SOFT" and "on Softs" in lr["subtitle"]
    cfg = tomllib.loads(post_toml(MEETINGS[2] | {"year": 2026}, "FP2", facts, None))
    assert "compound" not in next(s for s in cfg["slides"] if s["analysis"] == "long_runs")


def test_small_pole_gap_is_not_rounded_up():
    from stintlab.templates import slide_title
    facts = {"P1": "GASLY", "P2": "RUSSELL", "gap": 0.06}
    assert slide_title("telemetry", "Q", facts)[0] == "WHERE GASLY FOUND 0.06 S"
    assert slide_title("telemetry", "Q", facts | {"gap": 0.837})[0] == "WHERE GASLY FOUND 0.8 S"
