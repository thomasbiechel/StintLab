"""Race Preview für den Donnerstag-Post: vier Slides zum kommenden Wochenende.

Aufruf:
    python preview.py next              # das nächste Wochenende
    python preview.py sepang            # oder per Ort/Land/Strecke/meeting_key
    python preview.py next --refresh    # Rennen/Strecke neu von OpenF1 laden

Slides (posts/<jahr>-<ort>/preview/):
1. Strecke mit Kurvennummern + Sieger, Pole, schnellste Rennrunde der letzten Ausgabe
2. Wetter Fr–So (Open-Meteo) mit Regenchance zum Start von Quali und Rennen
3. Form: Teampace der letzten drei Rennen, das neueste zählt am meisten
4. Chancen: Form + Pace hier bei der letzten Ausgabe → Favoriten / im Rennen / Außenseiter

Die Wettervorhersage wird bei jedem Aufruf neu geholt – am besten Donnerstag
kurz vor dem Posten laufen lassen. Existiert die post.toml schon, bleibt sie
unverändert (deine Titel bleiben), die Slides werden neu erzeugt.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from stintlab import openf1
from stintlab.analyses.preview import short_team
from stintlab.preview import build_preview
from weekend import slug

REPO = Path(__file__).resolve().parent
FAN_NAMES = {12: "Sepang"}


def _q(s: str) -> str:
    return '"' + s.replace('"', '\\"') + '"'


def preview_toml(meeting: dict, data: dict) -> str:
    # Titel mit dem Namen, den Fans kennen (OpenF1 sagt „Kuala Lumpur“)
    place = FAN_NAMES.get(meeting.get("circuit_key")) or meeting.get("location") or meeting.get("circuit_short_name")
    hist, rows = data.get("history"), data.get("chances") or []
    races = data.get("races") or []

    old = bool(hist) and hist.get("source") == "jolpica"
    if old and int(meeting.get("year") or 0) - hist["year"] >= 3:
        track_title = f"{place} is back after {int(meeting['year']) - hist['year']} years"
        track_sub = f"Last race here in {hist['year']}"
    elif hist:
        track_title = f"{place} – what to know"
        track_sub = f"Last race here in {hist['year']}"
    else:
        track_title = f"{place} – what to know"
        track_sub = "Track layout"
    lay = data.get("layout")
    if lay and lay.get("source") == "multiviewer":
        track_sub += " · corner numbers as used by F1"
    elif lay and lay.get("source") == "openf1":
        track_sub += " · track drawn from car positions"

    form_title = "Who's in form"
    if data.get("form"):
        best = min(data["form"].items(), key=lambda x: x[1])[0]
        form_title = f"{short_team(best)} set the race pace"
    places = ", ".join(r["place"] for r in races)
    form_sub = f"Team race pace in {places} · newest race counts most" if places else "Team race pace in recent races"

    fav = [short_team(r["team"]) for r in rows if r["tier"] == "FAVOURITES"]
    if len(fav) == 1:
        chances_title = f"{fav[0]} start as favourites"
    elif len(fav) == 2:
        chances_title = f"{fav[0]} vs {fav[1]} in {place}?"
    else:
        chances_title = f"Who can win in {place}?"
    if hist and hist.get("track_pace"):
        chances_sub = f"Recent form plus {hist['year']} pace here · an assessment, not a prediction"
    elif hist:
        chances_sub = f"Recent form only – {hist['year']} is too long ago to count · an assessment, not a prediction"
    else:
        chances_sub = "Recent form only · an assessment, not a prediction"

    extra = (["Jolpica-F1"] if old else []) + (["f1-circuits"] if lay and lay.get("source") == "geojson" else [])
    track_source = "Data: " + " · ".join(["OpenF1"] + extra) if extra else None
    slides = [
        ("preview_track", track_title, track_sub),
        ("preview_weather", f"{place} weekend forecast", "Friday to Sunday at the circuit · local times"),
        ("preview_form", form_title, form_sub),
        ("preview_chances", chances_title, chances_sub),
    ]
    out = [f"# Race Preview {place} {meeting.get('year')} – erzeugt von preview.py, Titel frei änderbar",
           "", "[session]", f"meeting_key = {meeting['meeting_key']}", 'type = "PREVIEW"', ""]
    for name, title, sub in slides:
        out += ["[[slides]]", f"analysis = {_q(name)}", f"title = {_q(title)}", f"subtitle = {_q(sub)}"]
        if name == "preview_track" and track_source:
            out.append(f"source = {_q(track_source)}")
        out.append("")
    return "\n".join(out)


def report(data: dict) -> None:
    hist = data.get("history")
    if hist:
        f = hist.get("fastest") or {}
        src = " (Jolpica-F1, nur Ergebnisse)" if hist.get("source") == "jolpica" else ""
        print(f"  Letzte Ausgabe {hist['year']}{src}: Sieg {hist.get('winner')} · Pole {hist.get('pole', '–')} · "
              f"schnellste Runde {f.get('text', '–')} ({f.get('driver', '–')})")
    else:
        print("  ⚠ Keine frühere Ausgabe gefunden (OpenF1 ab 2023, Jolpica-F1 nicht erreichbar?)")
    lay = data.get("layout")
    kind = ("MultiViewer mit Kurvennummern" if lay and lay["source"] == "multiviewer"
            else "Positionsdaten, ohne Kurvennummern" if lay else "⚠ keine Karte")
    print(f"  Strecke: {kind}")
    w = data.get("weather")
    print(f"  Wetter: {len(w['days'])} Tage Vorhersage" if w else "  ⚠ Wetter: keine Vorhersage (Slide wird übersprungen)")
    print(f"  Form aus: {', '.join(r['place'] for r in data.get('races', [])) or '–'}")
    for r in data.get("chances", []):
        print(f"    {r['tier']:<11} {r['team']:<16} {r['score']:.2f} %  (Form {r['form']:.2f}"
              + ("" if r["track"] is None else f", hier {r['track']:.2f}") + ")")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", help="'next', Ort/Land/Strecke/Name oder meeting_key")
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--refresh", action="store_true", help="Rennen und Strecke neu von OpenF1 laden")
    args = parser.parse_args()

    meeting = openf1.find_meeting(args.query, args.year, refresh=args.refresh)
    print(f"▶ Preview {meeting.get('meeting_name')} · {meeting.get('location')} · meeting_key {meeting['meeting_key']}")
    data = build_preview(meeting["meeting_key"], refresh=args.refresh)
    report(data)

    path = REPO / "posts" / f"{args.year}-{slug(meeting)}" / "preview" / "post.toml"
    if path.exists():
        print(f"  post.toml existiert – unverändert: {path.relative_to(REPO)}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(preview_toml(meeting, data), encoding="utf-8")
        print(f"  angelegt: {path.relative_to(REPO)}")

    from make_post import build   # make_post lädt die Daten noch einmal – alles aus dem Cache
    failed = build(path, refresh=False, keep_going=True)
    print("\n── Zusammenfassung ──")
    for f in failed:
        print(f"✗ {f}")
    if not failed:
        print("✓ Alle Preview-Slides erzeugt")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
