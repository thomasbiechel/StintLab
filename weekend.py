"""Ein Befehl pro Session: Wochenende finden, post.toml anlegen, alles erzeugen.

Aufruf:
    python weekend.py sepang FP2          # Suchbegriff: Ort, Land, Strecke oder Name
    python weekend.py latest Q            # das zuletzt begonnene Wochenende
    python weekend.py 1295 R --refresh    # meeting_key direkt, Daten neu laden
    python weekend.py sepang R --no-reels # nur Slides, Reels später

Ablauf:
1. Wochenende suchen (Liste wird gemerkt, offline nutzbar). Achtung 2026: das
   Rennen in Sepang heißt offiziell „Bahrain Grand Prix“ – gesucht wird deshalb
   auch in Ort, Land und Strecke.
2. Beim ersten Aufruf pro Session: posts/<jahr>-<ort>/<session>/post.toml aus
   der Vorlage anlegen, Titel aus dem Ergebnis vorgeschlagen, Rest mit # TODO.
   Für Quali und Rennen zusätzlich <session>-reel/post.toml.
   Existiert die Datei schon, bleibt sie unverändert (deine Titel bleiben).
3. Alle Slides und Reels erzeugen – eine fehlerhafte Slide wird übersprungen
   und am Ende gemeldet, statt alles abzubrechen.
4. Zusammenfassung: P1/P2/Abstand, offene TODOs, übersprungene Slides.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

from stintlab import openf1
from stintlab.session import load_session
from stintlab.templates import FOLDERS, headline_facts, post_toml, reel_toml

REPO = Path(__file__).resolve().parent


def slug(meeting: dict) -> str:
    """Ordnername fürs Wochenende: Ort, klein, ohne Sonderzeichen („sepang“)."""
    raw = meeting.get("location") or meeting.get("circuit_short_name") or meeting.get("meeting_name") or "weekend"
    ascii_ = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()   # São Paulo → Sao Paulo
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")


def driver_names(session_key: int) -> dict[str, str]:
    """Kürzel → Nachname (für Titel wie „RUSSELL ON POLE“)."""
    try:
        drivers = openf1.cached_fetch("drivers", session_key)
    except Exception:
        return {}
    return {d.get("name_acronym"): d.get("last_name") for d in drivers if d.get("name_acronym")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", help="Ort/Land/Strecke/Name, meeting_key oder 'latest'")
    parser.add_argument("session", choices=list(FOLDERS), help="FP1, FP2, FP3, SQ, S, Q oder R")
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--refresh", action="store_true", help="Daten neu von OpenF1 laden")
    parser.add_argument("--no-reels", action="store_true", help="Reels auslassen (dauern je ~1–2 min)")
    args = parser.parse_args()

    meeting = openf1.find_meeting(args.query, args.year, refresh=args.refresh)
    print(f"▶ {meeting.get('meeting_name')} · {meeting.get('location')} ({meeting.get('country_name')}) · "
          f"meeting_key {meeting['meeting_key']} · {args.session}")

    data = load_session(meeting["meeting_key"], args.session, refresh=args.refresh)
    facts = headline_facts(data.get("results", []), driver_names(data["session_key"]))
    if facts["p1"]:
        gap = f" · Abstand P2 {facts['gap']:.3f} s" if facts["gap"] else ""
        print(f"  P1 {facts['P1']} · P2 {facts['P2']}{gap}")
    else:
        print("  ⚠ Noch kein offizielles Ergebnis – Titel bitte selbst setzen")

    base = REPO / "posts" / f"{args.year}-{slug(meeting)}"
    configs = [(base / FOLDERS[args.session] / "post.toml", post_toml(meeting, args.session, facts))]
    reels = reel_toml(meeting, args.session, facts)
    if reels and not args.no_reels:
        configs.append((base / f"{FOLDERS[args.session]}-reel" / "post.toml", reels))

    from make_post import build   # erst hier: make_post braucht Python 3.11 (tomllib)
    failed, todos = [], []
    for path, content in configs:
        if path.exists():
            print(f"  post.toml existiert – unverändert: {path.relative_to(REPO)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"  angelegt: {path.relative_to(REPO)}")
        failed += build(path, refresh=False, keep_going=True)
        todos += [f"{path.relative_to(REPO)}: {line.strip()}" for line in path.read_text(encoding="utf-8").splitlines()
                  if "TODO" in line and not line.lstrip().startswith("#")]

    print("\n── Zusammenfassung ──")
    for f in failed:
        print(f"✗ {f}")
    for t in todos:
        print(f"✎ {t}")
    if not failed and not todos:
        print("✓ Alles erzeugt, keine offenen TODOs")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
