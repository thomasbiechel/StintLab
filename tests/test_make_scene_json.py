"""Test für make_scene_json.py: Reel vorbereiten und den 3D-Anfang exportieren."""

import json

import pytest

from make_scene_json import export_reel, times_of
from tests.fake_race import make_race

GAPS = [2.0, 3.0, 4.0, 5.0, 6.0, 3.0, 1.0, 0.8, 0.6, 0.5]


def test_race_story_open_is_exported(tmp_path):
    data = make_race(GAPS, sc_laps=(6, 7), official=0.45)
    p = export_reel(data, {"analysis": "race_story"}, tmp_path / "scene.json", fps=30)
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["schema"] == 1 and d["meta"]["fps"] == 30
    assert len(d["frames"]["t"]) == pytest.approx(3.5 * 30, abs=2)         # OPEN_S = 3,5 s
    assert d["frames"]["t"][-1] > d["frames"]["t"][0]


def test_full_lap_is_exported(tmp_path):
    data = make_race(GAPS, sc_laps=(6, 7), official=0.45)
    p = export_reel(data, {"analysis": "race_story"}, tmp_path / "lap.json", fps=10, full_lap=True)
    d = json.loads(p.read_text(encoding="utf-8"))
    t = d["frames"]["t"]
    assert (t[-1] - t[0]) == pytest.approx(100.0, abs=1.0)                  # ganze Runde (fake_race: 100 s)


def test_reel_without_3d_part_is_rejected():
    with pytest.raises(ValueError):
        times_of({"hook_times": []})
    with pytest.raises(ValueError):
        times_of({})


def test_unknown_analysis_is_rejected(tmp_path):
    with pytest.raises(ModuleNotFoundError):
        export_reel(make_race(GAPS), {"analysis": "gibt_es_nicht"}, tmp_path / "x.json")
