"""Nur die Titelbilder (Cover) der Reels einer post.toml erzeugen – ohne Video.

Aufruf:
    python make_cover.py posts/2026-monza/race-reel/post.toml

Dauert Sekunden statt Minuten: gut zum Ausprobieren von Titel, Untertitel und
Zeitpunkt ([reels.cover] in der post.toml, siehe stintlab/reels/cover.py).
Beim normalen Rendern (make_post.py / weekend.py) entsteht das Cover automatisch
neben dem Video: reel_01_comeback_cover.png.
"""

import sys
import tomllib
from pathlib import Path

from stintlab.registry import REELS
from stintlab.reels import cover
from stintlab.session import load_session


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Aufruf: python make_cover.py <post.toml>")
    config_file = Path(sys.argv[1])
    config = tomllib.loads(config_file.read_text(encoding="utf-8"))
    session = config["session"]
    out_dir = config_file.parent / "slides"
    cover.ONLY = True
    loaded = {}
    for i, reel in enumerate(config.get("reels", []), start=1):
        name = reel.get("analysis")
        if name not in cover.WITH_COVER:
            print(f"– reel_{i:02d}_{name}: kein Cover für diesen Reel-Typ")
            continue
        stype = reel.get("session", session["type"])
        if stype not in loaded:
            loaded[stype] = load_session(session["meeting_key"], stype)
        try:
            REELS[name](loaded[stype], reel, out_dir / f"reel_{i:02d}_{name}.mp4")
        except cover.CoverOnly:
            pass


if __name__ == "__main__":
    main()
