"""Story-Finder: Fragen-Kandidaten für die tiefe Analyse nach dem Rennen.

Aufruf:
    python find_stories.py sepang            # Rennen (R)
    python find_stories.py sepang S          # Sprint
    python find_stories.py latest --top 5

Ergebnis: Rangliste in der Konsole und posts/<jahr>-<ort>/stories.md mit
Frage, Kennzahlen und fertigen [[slides]]-Blöcken zum Kopieren.
Danach selbst prüfen (Leitfaden): Stellen sich Fans diese Frage? Sieht man
die Antwort im TV? Wenn nein → nächste Story.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from stintlab import openf1
from stintlab.session import load_session
from stintlab.stories import find_stories
from stintlab.templates import _toml_value
from weekend import slug

REPO = Path(__file__).resolve().parent


def slides_block(slides: list[dict]) -> str:
    out = []
    for s in slides:
        out.append("[[slides]]")
        out += [f"{k:<8} = {_toml_value(v)}" for k, v in s.items()]
        out += ['title    = "TITLE TODO"', 'subtitle = "SUBTITLE TODO"', ""]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query")
    parser.add_argument("session", nargs="?", default="R", choices=["R", "S"])
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--top", type=int, default=8)
    args = parser.parse_args()

    meeting = openf1.find_meeting(args.query, args.year)
    data = load_session(meeting["meeting_key"], args.session)
    stories = find_stories(data)[: args.top]

    md = [f"# Story-Kandidaten · {meeting.get('meeting_name')} {args.year} · {meeting.get('location')}", "",
          "Leitfaden: eine Frage, die Fans sich stellen · Antwort nicht im TV sichtbar · jede Slide ein Schritt · "
          "letzte Slide = Antwort mit Grenzen", ""]
    for i, s in enumerate(stories, 1):
        print(f"\n{i}. [{s.kind}] {s.question}")
        for f in s.facts:
            print(f"     · {f}")
        md += [f"## {i}. {s.question}", f"*{s.kind} · Score {s.score:.1f}*", ""] + [f"- {f}" for f in s.facts]
        md += ["", "```toml", slides_block(s.slides), "```", ""]
    out = REPO / "posts" / f"{args.year}-{slug(meeting)}" / "stories.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"\n→ {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
