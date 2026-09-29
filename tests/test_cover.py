"""Tests für die Reel-Titelbilder (ohne 3D-Rendern)."""

from pathlib import Path

import pytest

from stintlab.reels import cover


def test_cover_next_to_video():
    assert cover.cover_path(Path("x/slides/reel_01_comeback.mp4")) == Path("x/slides/reel_01_comeback_cover.png")


def test_cover_config_on_by_default_and_can_be_switched_off():
    assert cover.cover_config({}) == {}
    assert cover.cover_config({"cover": {"title": "P19 → P1"}})["title"] == "P19 → P1"
    assert cover.cover_config({"cover": {"enabled": False}}) is None
    assert cover.cover_config({"cover": False}) is None
    with pytest.raises(ValueError):
        cover.cover_config({"cover": "ja"})


def test_long_titles_get_smaller():
    assert cover._fit_size("P19 → P1") > cover._fit_size("RUSSELL HOLDS ON")


def test_cover_only_stops_after_cover(monkeypatch):
    monkeypatch.setattr(cover, "ONLY", True)
    monkeypatch.setattr(cover, "render_cover", lambda *a, **k: Path("c.png"))
    with pytest.raises(cover.CoverOnly):
        cover.make_cover({}, Path("r.mp4"), None, 0.0, "T")
    with pytest.raises(cover.CoverOnly):                       # auch ohne Cover kein Video
        cover.make_cover({"cover": False}, Path("r.mp4"), None, 0.0, "T")


def test_cover_error_does_not_break_reel(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaputt")
    monkeypatch.setattr(cover, "render_cover", boom)
    assert cover.make_cover({}, Path("r.mp4"), None, 0.0, "T") is None
