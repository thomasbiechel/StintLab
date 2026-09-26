"""Erzeugt alle Slides eines Posts aus seiner post.toml.

Aufruf:
    python make_post.py posts/2026-madrid/post.toml
    python make_post.py posts/2026-madrid/post.toml --refresh   # Daten neu von OpenF1 laden

Eine Slide kann mit session = "FP2" eine andere Session des Wochenendes
verwenden als die in [session] – so passen z. B. Long Runs aus FP2 und die
ideale Runde aus FP3 in ein Karussell.
"""

import argparse
import sys
import tomllib
from pathlib import Path

from stintlab.analyses.results import pit_notes, result_mismatches
from stintlab.quali import quali_mismatches
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
        stype = slide.get("session", session["type"])
        if name not in ANALYSES:
            sys.exit(f"Unbekannte Analyse '{name}'. Verfügbar: {', '.join(ANALYSES)}")
        if stype not in ANALYSES[name]["sessions"]:
            sys.exit(f"'{name}' passt nicht zu Session-Typ '{stype}' "
                     f"(erlaubt: {', '.join(sorted(ANALYSES[name]['sessions']))})")

    # Jede benötigte Session genau einmal laden
    sessions = {}
    for stype in {slide.get("session", session["type"]) for slide in config["slides"]}:
        sessions[stype] = load_session(session["meeting_key"], stype, refresh=args.refresh)

    # Plausibilitätstest: Passt der gezeichnete Abstand zu den Positionsdaten?
    for slide in config["slides"]:
        drivers = slide.get("drivers", [])
        if slide["analysis"] != "gap_between" or len(drivers) != 2:
            continue
        bad = sign_mismatches(sessions[slide.get("session", session["type"])], drivers[0], drivers[1])
        pit = [n for n, is_pit in bad if is_pit]
        other = [n for n, is_pit in bad if not is_pit]
        if pit:
            print(f"ℹ {drivers[0]}/{drivers[1]}: Abweichung nur in Boxenstopp-Runde(n) {pit} – meist erklärbar")
        if other:
            print(f"⚠ {drivers[0]}/{drivers[1]}: Abstand widerspricht Position in Runde(n) {other} – vor dem Posten prüfen!")

    # Plausibilitätstest: Offizielles Ergebnis (OpenF1-Beta) vs. Rundendaten
    for stype in {slide.get("session", session["type"]) for slide in config["slides"]
                  if slide["analysis"] == "results"}:
        for problem in result_mismatches(sessions[stype]):
            print(f"⚠ Ergebnis {stype}: {problem} – vor dem Posten prüfen!")
        if stype in ("R", "S"):
            for note in pit_notes(sessions[stype]):
                print(f"ℹ Ergebnis {stype}: {note}")

    # Plausibilitätstest Qualifying: Runden richtig Q1/Q2/Q3 zugeordnet?
    for stype in {slide.get("session", session["type"]) for slide in config["slides"]
                  if slide.get("part") or (slide["analysis"] == "results"
                                           and slide.get("session", session["type"]) in ("Q", "SQ"))}:
        for problem in quali_mismatches(sessions[stype]):
            print(f"⚠ Qualifying {stype}: {problem} – vor dem Posten prüfen!")

    out_dir = config_file.parent / "slides"
    for i, slide in enumerate(config["slides"], start=1):
        fig, ax = new_slide(slide["title"], slide.get("subtitle", ""))
        ANALYSES[slide["analysis"]]["render"](ax, sessions[slide.get("session", session["type"])], slide)
        filename = f"{i:02d}_{slide['analysis']}.png"
        path = save_slide(fig, out_dir / filename)
        print(f"✓ {path}")


if __name__ == "__main__":
    main()