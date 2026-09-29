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

from matplotlib import pyplot as plt

from stintlab.analyses.results import pit_notes, result_mismatches
from stintlab.openf1 import SESSION_NAMES, meeting_by_key
from stintlab.quali import quali_mismatches
from stintlab.registry import ANALYSES, REELS
from stintlab.session import load_session, sign_mismatches
from stintlab.style import new_slide, save_slide


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="Pfad zur post.toml")
    parser.add_argument("--refresh", action="store_true", help="Cache ignorieren, neu laden")
    parser.add_argument("--keep-going", action="store_true",
                        help="Bei einer fehlerhaften Slide weitermachen statt abzubrechen")
    args = parser.parse_args()
    build(Path(args.config), args.refresh, args.keep_going)


def build(config_file: Path, refresh: bool = False, keep_going: bool = False) -> list[str]:
    """Alle Slides und Reels einer post.toml erzeugen. Gibt die Fehler zurück
    (nur mit keep_going – sonst bricht der erste Fehler ab)."""
    config_file = Path(config_file)
    config = tomllib.loads(config_file.read_text(encoding="utf-8"))
    failed: list[str] = []
    session = config["session"]
    if not session.get("meeting_key"):
        sys.exit("In der post.toml fehlt meeting_key.")

    config.setdefault("slides", [])
    reels = config.get("reels", [])
    for reel in reels:
        if reel.get("analysis") not in REELS:
            sys.exit(f"Unbekanntes Reel '{reel.get('analysis')}'. Verfügbar: {', '.join(REELS)}")

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
    for stype in {item.get("session", session["type"]) for item in config["slides"] + reels}:
        if stype == "PREVIEW":           # Race Preview: mehrere Rennen + Wetter, keine einzelne Session
            from stintlab.preview import build_preview
            sessions[stype] = build_preview(session["meeting_key"], refresh=refresh)
        else:
            sessions[stype] = load_session(session["meeting_key"], stype, refresh=refresh)

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
    # Kopfzeile jeder Slide: „Baku · Qualifying · 2026“, rechts „02 / 05“
    meeting = meeting_by_key(session["meeting_key"]) or {}
    place = meeting.get("location") or meeting.get("circuit_short_name") or ""
    year = str(meeting.get("date_start") or "")[:4]
    names = {**SESSION_NAMES, "PREVIEW": "Race Preview"}
    meta_for = lambda stype: " · ".join(x for x in (place, names.get(stype, stype), year) if x)
    n_slides = len(config["slides"])
    for i, slide in enumerate(config["slides"], start=1):
        filename = f"{i:02d}_{slide['analysis']}.png"
        try:
            fig, ax = new_slide(slide["title"], slide.get("subtitle", ""),
                                source=slide.get("source") or ANALYSES[slide["analysis"]].get("source", "Data: OpenF1"),
                                meta=meta_for(slide.get("session", session["type"])), page=f"{i:02d} / {n_slides:02d}")
            ANALYSES[slide["analysis"]]["render"](ax, sessions[slide.get("session", session["type"])], slide)
            as_reel = slide.get("reel", False)
            if not isinstance(as_reel, bool):
                raise ValueError("reel muss true oder false sein (klein geschrieben, ohne Anführungszeichen)")
            if as_reel:
                # dieselbe Slide als Reel: Balken bauen sich Zeile für Zeile auf (reels/animate.py)
                from stintlab.reels.animate import animate_slide
                reel_path = animate_slide(fig, ax, out_dir / f"{i:02d}_{slide['analysis']}_reel.mp4")
                print(f"✓ {reel_path}")
            path = save_slide(fig, out_dir / filename, scaled=as_reel)
            print(f"✓ {path}")
        except Exception as exc:
            if not keep_going:
                raise
            plt.close("all")
            failed.append(f"{filename}: {exc}")
            print(f"✗ {filename} übersprungen: {exc}")

    for i, reel in enumerate(reels, start=1):
        filename = f"reel_{i:02d}_{reel['analysis']}.mp4"
        print(f"… rendere {filename} (dauert etwa eine Minute)")
        try:
            path = REELS[reel["analysis"]](sessions[reel.get("session", session["type"])], reel,
                                           out_dir / filename)
            print(f"✓ {path}")
        except Exception as exc:
            if not keep_going:
                raise
            plt.close("all")
            failed.append(f"{filename}: {exc}")
            print(f"✗ {filename} übersprungen: {exc}")
    return failed


if __name__ == "__main__":
    main()
