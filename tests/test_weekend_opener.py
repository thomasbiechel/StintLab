"""Test: weekend.py legt Reels mit dem Blender-Anfang an."""

import tomllib

from stintlab.templates import reel_toml

MEETING = {"meeting_key": 1296, "location": "Sepang", "year": 2026}


def test_reels_get_the_blender_opener_when_asked():
    meeting = MEETING
    facts = {"P1": "Russell", "P2": "Verstappen", "gap": 0.196, "p1": True}
    for stype in ("R", "Q"):
        on = tomllib.loads(reel_toml(meeting, stype, facts, opener="blender"))
        assert all(r["opener"] == "blender" for r in on["reels"])
        off = tomllib.loads(reel_toml(meeting, stype, facts))
        assert all("opener" not in r for r in off["reels"])                # Standard der Funktion: alt (weekend.py setzt blender)
    prev = tomllib.loads(reel_toml(meeting, "R", facts, opener="blender", opener_quality="preview"))
    assert prev["reels"][0]["opener_quality"] == "preview"
