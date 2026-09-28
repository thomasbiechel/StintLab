"""Vorlagen für die Standard-Posts eines Rennwochenendes.

weekend.py legt damit beim ersten Aufruf pro Session eine post.toml an. Die
Titel werden aus dem Ergebnis vorgeschlagen („RUSSELL ON POLE BY 0.837 S“),
Titel ohne echte Aussage sind mit # TODO markiert – die schreibt man selbst,
nachdem man die Slides gesehen hat. Beim nächsten Aufruf bleibt die
bearbeitete post.toml unangetastet.

Welche Slides pro Session: übernommen aus Baku 2026 (FP2, FP3, Quali, Rennen).
"""

from __future__ import annotations

# Ordnername pro Session-Typ
FOLDERS = {"FP1": "fp1", "FP2": "fp2", "FP3": "fp3", "SQ": "sprint-quali", "S": "sprint",
           "Q": "quali", "R": "race"}

# (analysis, zusätzliche Felder, Titel-Schlüssel, Untertitel)
SLIDES = {
    "FP1": [("results", {}, "results", "Official classification · tyre = compound of each driver's fastest lap"),
            ("ideal_lap", {"view": "ideal"}, "todo",
             "Best {s} sectors added up – the lap each driver had in him · ▲▼ = places vs. best lap"),
            ("long_runs", {}, "todo", "Median lap time of each driver's longest {s} run · fuel loads unknown")],
    "FP2": [("results", {}, "results", "Official classification · tyre = compound of each driver's fastest lap"),
            ("ideal_lap", {"view": "ideal", "compound": "SOFT"}, "todo",
             "Best {s} sectors on Softs added up · ▲▼ = places vs. best lap · fuel loads unknown"),
            ("long_runs", {}, "todo", "Median lap time of each driver's longest {s} run · fuel loads unknown")],
    "FP3": [("results", {}, "results", "Official classification · tyre = compound of each driver's fastest lap"),
            ("ideal_lap", {"view": "ideal", "compound": "SOFT"}, "todo",
             "Best {s} sectors on Softs added up · ▲▼ = places gained vs. best lap · fuel loads unknown"),
            ("sectors", {"compound": "SOFT"}, "todo", "Each driver's best valid {s} sector time on Softs")],
    "SQ": [("results", {}, "pole", "Official sprint qualifying classification"),
           ("ideal_lap", {"view": "both"}, "todo", "Each driver's best sectors added up vs. the fastest lap")],
    "Q": [("results", {}, "pole", "Official qualifying classification · fastest time in each part in purple"),
          ("telemetry", {"part": "Q3"}, "telemetry", "Fastest Q3 laps of the top two · speed and gap over the lap"),
          ("ideal_lap", {"part": "Q3", "view": "both"}, "todo", "Each Q3 driver's best sectors added up vs. the pole lap"),
          ("sectors", {"part": "Q3"}, "todo", "Each Q3 driver's best valid sector time")],
    "S": [("results", {}, "win", "Official sprint classification · +/– = places vs. starting grid"),
          ("driver_pace", {}, "todo", "Clean sprint laps only · traffic affects the numbers")],
    "R": [("results", {}, "win", "Official race classification · +/– = places vs. starting grid"),
          ("driver_pace", {}, "todo", "Clean race laps only · strategy and traffic affect the numbers"),
          ("team_pace", {}, "todo", "Median of both drivers' clean race laps")],
}

# Reels, die zu einer Session gehören (eigener Ordner <folder>-reel)
REELS = {
    "Q": [("ghost_lap", {"part": "Q3"}, "Where {name} found {gap1} s", "{name} on pole by {gap} s")],
    "R": [("race_story", {}, "{name}'s race – how it was decided", "{name} wins by {gap} s")],
}

SESSION_LABEL = {"FP1": "FP1", "FP2": "FP2", "FP3": "FP3", "SQ": "sprint qualifying", "S": "sprint",
                 "Q": "qualifying", "R": "race"}


def _num(v) -> float | None:
    """Abstand aus session_result: Zahl, Liste (Quali: Q1–Q3) oder Text."""
    if isinstance(v, list):
        v = next((x for x in reversed(v) if isinstance(x, (int, float))), None)
    return float(v) if isinstance(v, (int, float)) else None


def headline_facts(results: list[dict], names: dict[str, str]) -> dict:
    """P1, P2 und Abstand aus dem Ergebnis – für Titel und Zusammenfassung."""
    rows = sorted((r for r in results if r.get("position")), key=lambda r: r["position"])
    p1 = rows[0]["driver"] if rows else None
    p2 = rows[1]["driver"] if len(rows) > 1 else None
    gap = _num(rows[1].get("gap")) if len(rows) > 1 else None
    name = lambda d: (names.get(d) or d or "?").upper()
    return {"p1": p1, "p2": p2, "P1": name(p1), "P2": name(p2), "gap": gap}


def slide_title(kind: str, stype: str, facts: dict) -> tuple[str, bool]:
    """(Titel, ist_vorschlag). Bei False steht ein Platzhalter mit # TODO."""
    gap = facts["gap"]
    label = SESSION_LABEL[stype].upper()
    if kind == "results":
        return f"{facts['P1']} FASTEST IN {label}", True
    if kind == "pole":
        return (f"{facts['P1']} ON POLE BY {gap:.3f} S" if gap else f"{facts['P1']} ON POLE"), True
    if kind == "win":
        return (f"{facts['P1']} WINS BY {gap:.3f} S" if gap else f"{facts['P1']} WINS"), True
    if kind == "telemetry":
        return (f"WHERE {facts['P1']} FOUND {gap:.1f} S" if gap else f"{facts['P1']} VS {facts['P2']}"), True
    return "TITLE TODO", False


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    return '"' + str(v).replace('"', '\\"') + '"'


def post_toml(meeting: dict, stype: str, facts: dict) -> str:
    """Inhalt der post.toml für die Slides einer Session."""
    lines = [f"# {meeting.get('meeting_name', '')} {meeting.get('year', '')} · {meeting.get('location', '')} · "
             f"{SESSION_LABEL[stype]} – angelegt von weekend.py",
             "# Titel mit TODO selbst formulieren, dann: python weekend.py <ort> " + stype,
             "[session]", f"meeting_key = {meeting['meeting_key']}", f'type = "{stype}"', ""]
    s_label = SESSION_LABEL[stype] if stype not in ("FP1", "FP2", "FP3") else stype
    for analysis, extra, kind, subtitle in SLIDES[stype]:
        title, ok = slide_title(kind, stype, facts)
        lines.append("[[slides]]")
        lines.append(f'analysis = "{analysis}"')
        for k, v in extra.items():
            lines.append(f"{k} = {_toml_value(v)}")
        lines.append(f"title    = {_toml_value(title)}" + ("" if ok else "   # TODO"))
        lines.append(f"subtitle = {_toml_value(subtitle.format(s=s_label))}")
        lines.append("")
    return "\n".join(lines)


def reel_toml(meeting: dict, stype: str, facts: dict) -> str | None:
    """Inhalt der post.toml für die Reels einer Session (oder None)."""
    if stype not in REELS:
        return None
    gap = facts["gap"]
    fmt = {"name": (facts["P1"] or "").title(),          # „Russell“, nicht das Kürzel
           "gap": f"{gap:.3f}" if gap else "?", "gap1": f"{gap:.1f}" if gap else "?"}
    lines = [f"# Reels {meeting.get('location', '')} {meeting.get('year', '')} · {SESSION_LABEL[stype]} – "
             "angelegt von weekend.py", "# hook: Zeile 1 – Zeile 2 (wird am „ – “ geteilt). "
             "open_at = Stelle des 3D-Anfangs (siehe Reel-Doku)",
             "[session]", f"meeting_key = {meeting['meeting_key']}", f'type = "{stype}"', ""]
    for analysis, extra, hook, result in REELS[stype]:
        lines.append("[[reels]]")
        lines.append(f'analysis = "{analysis}"')
        for k, v in extra.items():
            lines.append(f"{k} = {_toml_value(v)}")
        lines.append(f"hook     = {_toml_value(hook.format(**fmt))}   # TODO schärfen")
        lines.append(f"result   = {_toml_value(result.format(**fmt))}")
        lines.append("")
    return "\n".join(lines)
