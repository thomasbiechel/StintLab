"""Leere Fahrerliste im Cache → Fahrer aus einer anderen Session desselben Wochenendes."""

import json

from stintlab import openf1, session


def test_empty_drivers_use_other_session_of_same_meeting(tmp_path, monkeypatch):
    monkeypatch.setattr(openf1, "CACHE_DIR", tmp_path)
    (tmp_path / "200").mkdir()
    (tmp_path / "200" / "drivers.json").write_text(json.dumps(
        [{"driver_number": 3, "name_acronym": "VER", "team_name": "Red Bull Racing"}]))

    def offline(*a, **k):
        raise RuntimeError("kein Netz")

    monkeypatch.setattr(openf1, "cached_fetch", offline)
    monkeypatch.setattr(openf1, "sessions_of", lambda mk, refresh=False: [
        {"session_key": 201, "session_name": "Race"}, {"session_key": 200, "session_name": "Qualifying"}])
    drivers = session._drivers_fallback(1308, 201)
    assert drivers[0]["name_acronym"] == "VER"
