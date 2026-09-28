"""Tests für den automatischen Vorjahresvergleich (weekend.py → Ghost-Lap-Reel)."""

import tomllib

import stintlab.openf1 as openf1
from stintlab.compare import previous_edition
from stintlab.templates import headline_facts, reel_toml

Y2025 = [{"meeting_key": 1253, "meeting_name": "Pre-Season Testing", "circuit_key": 63, "year": 2025},
         {"meeting_key": 1257, "meeting_name": "Bahrain Grand Prix", "circuit_key": 63, "year": 2025},
         {"meeting_key": 1269, "meeting_name": "Azerbaijan Grand Prix", "circuit_key": 144, "year": 2025}]


def test_same_circuit_not_same_name(monkeypatch):
    monkeypatch.setattr(openf1, "meetings_of", lambda year, refresh=False: Y2025)
    baku = {"meeting_name": "Azerbaijan Grand Prix", "circuit_key": 144, "year": 2026}
    assert previous_edition(baku)["meeting_key"] == 1269
    # 2026 heißt das Rennen in Sepang „Bahrain Grand Prix“ – anderes circuit_key, kein Vorjahr
    sepang = {"meeting_name": "Bahrain Grand Prix", "circuit_key": 12, "year": 2026}
    assert previous_edition(sepang) is None
    # Sakhir: das Rennen, nicht die Testfahrten
    sakhir = {"meeting_name": "Bahrain Grand Prix", "circuit_key": 63, "year": 2026}
    assert previous_edition(sakhir)["meeting_key"] == 1257


def test_reel_toml_gets_compare_reel_only_for_quali():
    meeting = {"meeting_key": 1295, "location": "Baku", "year": 2026}
    facts = headline_facts([{"driver": "RUS", "position": 1, "gap": 0},
                            {"driver": "LEC", "position": 2, "gap": 0.837}], {"RUS": "Russell"})
    cmp = {"meeting_key": 1269, "year": 2025, "pole": "VER", "weather": "Luft 20–22 °C", "rain": True,
           "no_laps": True}
    cfg = tomllib.loads(reel_toml(meeting, "Q", facts, cmp))
    last = cfg["reels"][-1]
    assert last["compare"] == {"meeting_key": 1269} and last["open_at"] == 0 and last["part"] == "Q3"
    text = reel_toml(meeting, "Q", facts, cmp)
    assert "Regen im Qualifying 2025" in text and "rekonstruiert" in text
    assert len(tomllib.loads(reel_toml(meeting, "Q", facts))["reels"]) == 1          # ohne Vorjahr
    assert all("compare" not in r for r in tomllib.loads(reel_toml(meeting, "R", facts, cmp))["reels"])
