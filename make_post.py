"""Erzeugt alle Slides eines Posts aus seiner post.toml.

Aufruf:
    python make_post.py posts/2026-madrid/post.toml
    python make_post.py posts/2026-madrid/post.toml --refresh   # Daten neu von OpenF1 laden
"""

import argparse
import sys
import tomllib
from pathlib import Path

from stintlab.registry import ANALYSES
from stintlab.session import load_session, sign_mismatches
from stintlab.style import new_slide, save_slide


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="Pfad zur post.toml")
    parser.add_argument("--refresh", action="store_true", help="Cache ignorieren, neu laden")
    args = parser.parse_args()

    config_file = Path(args.config)
    config = tomllib.loads(config_file.read_text(encoding="utf-8"))
    session = config["session"]
    if not session.get("meeting_key"):
        sys.exit("In der post.toml fehlt meeting_key.")

    # Zuerst alles prüfen, dann erst Daten laden – Fehler sollen früh auffallen
    for slide in config["slides"]:
        name = slide["analysis"]
        if name not in ANALYSES:
            sys.exit(f"Unbekannte Analyse '{name}'. Verfügbar: {', '.join(ANALYSES)}")
        if session["type"] not in ANALYSES[name]["sessions"]:
            sys.exit(f"'{name}' passt nicht zu Session-Typ '{session['type']}' "
                     f"(erlaubt: {', '.join(sorted(ANALYSES[name]['sessions']))})")

    data = load_session(session["meeting_key"], session["type"], refresh=args.refresh)

    # Plausibilitätstest: Passt der gezeichnete Abstand zu den Positionsdaten?
    for slide in config["slides"]:
        drivers = slide.get("drivers", [])
        if slide["analysis"] != "gap_between" or len(drivers) != 2:
            continue
        bad = sign_mismatches(data, drivers[0], drivers[1])
        pit = [n for n, is_pit in bad if is_pit]
        other = [n for n, is_pit in bad if not is_pit]
        if pit:
            print(f"ℹ {drivers[0]}/{drivers[1]}: Abweichung nur in Boxenstopp-Runde(n) {pit} – meist erklärbar")
        if other:
            print(f"⚠ {drivers[0]}/{drivers[1]}: Abstand widerspricht Position in Runde(n) {other} – vor dem Posten prüfen!")

    out_dir = config_file.parent / "slides"
    for i, slide in enumerate(config["slides"], start=1):
        fig, ax = new_slide(slide["title"], slide.get("subtitle", ""))
        ANALYSES[slide["analysis"]]["render"](ax, data, slide)
        filename = f"{i:02d}_{slide['analysis']}.png"
        path = save_slide(fig, out_dir / filename)
        print(f"✓ {path}")


if __name__ == "__main__":
    main()