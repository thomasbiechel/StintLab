"""Ergebnis-Slide: offizielles Session-Ergebnis als Tabelle.

DATENQUELLE: OpenF1 /session_result (Beta). Deshalb gibt es mit
result_mismatches() eine Plausibilitätsprüfung gegen die Rundendaten.

JE SESSION andere Spalten – aktuell umgesetzt:
- Training: Pos, Fahrer, Reifen der schnellsten Runde, Bestzeit, Abstand, Runden
- Qualifying: Pos, Fahrer, Q1, Q2, Q3, Abstand zur Pole, Trennlinien
- Rennen/Sprint: Pos, Fahrer, Startplatz, Plätze gewonnen/verloren, Abstand
  bzw. Ausfall, Boxengassen-Durchfahrten, Punkte

FARBEN: Fahrer in Teamfarbe. Lila (StintLab-Akzent) nur für die schnellste
Runde der Session – in der Zeitnahme bedeutet Lila genau das.
"""

from __future__ import annotations

from matplotlib.patches import Rectangle

from stintlab.analyses.long_runs import COMPOUND_COLORS, _compound, _fmt
from stintlab.race_control import deleted_laps
from stintlab.style import COLORS, team_color

PRACTICE = {"FP1", "FP2", "FP3"}
TOLERANCE = 0.0015   # Rundung: offizielle Zeit vs. Rundendaten


def _num(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def practice_rows(data: dict) -> list[dict]:
    """Ergebniszeilen fürs Training, sortiert: mit Zeit nach Position, ohne Zeit am Ende."""
    stints = data.get("stints", [])
    laps_by_driver: dict[str, list[dict]] = {}
    for lap in data.get("laps", []):
        laps_by_driver.setdefault(lap["Driver"], []).append(lap)

    rows = []
    for r in data.get("results", []):
        best = _num(r["duration"])
        compound = None
        if best is not None:
            # Die Runde mit der offiziellen Bestzeit suchen → Mischung über den Stint
            match = next((l for l in laps_by_driver.get(r["driver"], [])
                          if l.get("LapTime") and abs(float(l["LapTime"]) - best) <= TOLERANCE), None)
            if match:
                compound = _compound(stints, r["driver"], match["LapNumber"])
        rows.append({"driver": r["driver"], "position": r["position"], "best": best,
                     "gap": _num(r["gap"]), "laps": r["laps"], "compound": compound})
    with_time = sorted((x for x in rows if x["best"] is not None),
                       key=lambda x: (x["position"] or 99, x["best"]))
    without = sorted((x for x in rows if x["best"] is None), key=lambda x: x["driver"])
    return with_time + without


def result_mismatches(data: dict) -> list[str]:
    """Plausibilitätsprüfung: offizielle Bestzeit vs. schnellste gültige Runde
    in den Rundendaten (ohne Out-Laps und gestrichene Runden). Leer = stimmig."""
    if data.get("session_type") in RACE:
        return race_mismatches(data)
    if data.get("session_type") not in PRACTICE:
        return []
    deleted = deleted_laps(data.get("race_control", []), data.get("laps", []), data.get("lap_ends", {}))
    fastest: dict[str, float] = {}
    for lap in data.get("laps", []):
        if not lap.get("LapTime") or lap.get("IsPitOutLap") or (lap["Driver"], lap["LapNumber"]) in deleted:
            continue
        t = float(lap["LapTime"])
        fastest[lap["Driver"]] = min(t, fastest.get(lap["Driver"], t))
    problems = []
    for row in practice_rows(data):
        own = fastest.get(row["driver"])
        if row["best"] is None or own is None:
            continue
        if abs(own - row["best"]) > TOLERANCE:
            problems.append(f"{row['driver']}: offiziell {_fmt(row['best'])}, Rundendaten {_fmt(own)}")
        if row["compound"] is None:
            problems.append(f"{row['driver']}: Runde mit der Bestzeit nicht gefunden – Reifen unbekannt")
    return problems


def unclassified(data: dict) -> list[str]:
    """Fahrer, die für die Session gemeldet sind, aber im Ergebnis fehlen.

    OpenF1 lässt Fahrer ohne Zeit aus session_result weg (Madring Q 2026:
    BEA und STR konnten nicht fahren und fehlen dort ganz). Die offizielle
    Wertung führt sie unten ohne Zeit – die Slide soll sie nicht verschweigen.
    """
    classified = {r["driver"] for r in data.get("results", [])}
    return sorted(d for d in data.get("teams", {}) if d not in classified)


def _note(ax, drivers: list[str]) -> None:
    if drivers:
        ax.text(0.99, -0.02, "No time set: " + ", ".join(drivers), transform=ax.transAxes,
                ha="right", va="top", fontsize=7.5, color=COLORS["muted"])


def _table(ax, header: list[tuple[str, float, str]], rows: list[list[tuple]],
           separators: dict[int, str] | None = None) -> None:
    """Zeichnet eine Tabelle in Achsen-Koordinaten (0–1).

    header: [(Text, x, Ausrichtung)]
    rows:   pro Zeile [(Text, Farbe, fett?), ...] passend zum header,
            dazu am Anfang ein Eintrag ("__stripe__", Farbe) für den Teamstreifen.
    """
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    n = len(rows)
    top, bottom = 0.965, 0.0
    h = (top - bottom) / (n + 1)

    for text, x, ha in header:
        ax.text(x, top - h / 2, text, ha=ha, va="center", fontsize=7.5,
                color=COLORS["muted"], fontweight="bold")
    ax.plot([0, 1], [top - h, top - h], color=COLORS["grid"], linewidth=0.8)

    for i, label in (separators or {}).items():
        y = top - h * (i + 2)          # Linie unter Zeile i
        ax.plot([0, 1], [y, y], color=COLORS["muted"], linewidth=0.9, linestyle="--", zorder=4)
        # unter der Linie – dort sind die Spalten der Ausgeschiedenen leer
        ax.text(0.99, y - h * 0.5, label, ha="right", va="center", fontsize=7, color=COLORS["muted"])

    for i, row in enumerate(rows):
        y = top - h * (i + 1.5)
        if i % 2 == 0:
            ax.add_patch(Rectangle((0, y - h / 2), 1, h, color=COLORS["plot"], zorder=0, linewidth=0))
        stripe = row[0][1]
        ax.add_patch(Rectangle((0.095, y - h * 0.3), 0.008, h * 0.6, color=stripe, linewidth=0))
        for (text, color, bold), (_, x, ha) in zip(row[1:], header):
            if text == "●":
                ax.scatter([x], [y], s=45, color=color, edgecolor=COLORS["bg"], linewidth=1, zorder=5)
            else:
                ax.text(x, y, text, ha=ha, va="center", fontsize=9, color=color,
                        fontweight="bold" if bold else "normal")


def render_practice(ax, data: dict) -> list[dict]:
    rows = practice_rows(data)
    if not rows:
        raise ValueError("Kein Ergebnis von OpenF1 – die Session ist evtl. noch nicht klassifiziert. "
                         "Ein paar Minuten warten und mit --refresh erneut versuchen")
    teams = data.get("teams", {})
    header = [("POS", 0.06, "right"), ("DRIVER", 0.125, "left"), ("TYRE", 0.36, "center"),
              ("BEST LAP", 0.60, "right"), ("GAP", 0.80, "right"), ("LAPS", 0.97, "right")]
    fastest = rows[0]["best"]
    table = []
    for r in rows:
        tc = team_color(teams.get(r["driver"]))
        if r["best"] is None:
            best, gap, best_color = "No time", "", COLORS["muted"]
        else:
            best = _fmt(r["best"])
            best_color = COLORS["accent"] if r["best"] == fastest else COLORS["text"]
            gap = "—" if r["best"] == fastest else f"+{(r['gap'] if r['gap'] is not None else r['best'] - fastest):.3f}"
        table.append([
            ("__stripe__", tc),
            (str(r["position"]) if r["best"] is not None and r["position"] else "–", COLORS["muted"], False),
            (r["driver"], tc, True),
            ("●" if r["compound"] else "", COMPOUND_COLORS.get(r["compound"] or "", COLORS["muted"]), False),
            (best, best_color, r["best"] == fastest),
            (gap, COLORS["text"], False),
            (str(r["laps"] or 0), COLORS["muted"], False),
        ])
    _table(ax, header, table)
    _note(ax, unclassified(data))
    return rows


QUALI = {"Q", "SQ"}


def qualifying_rows(data: dict) -> list[dict]:
    """Ergebniszeilen fürs Qualifying: Q1-, Q2-, Q3-Zeit je Fahrer, nach Position.

    session_result liefert im Qualifying duration als Liste [Q1, Q2, Q3]
    (geprüft am Madring 2026); ausgeschiedene Fahrer haben dort None.
    """
    rows = []
    for r in data.get("results", []):
        times = r["duration"] if isinstance(r["duration"], list) else [r["duration"]]
        times = [_num(t) for t in (list(times) + [None, None, None])[:3]]
        rows.append({"driver": r["driver"], "position": r["position"], "times": times,
                     "status": "DSQ" if r.get("dsq") else "DNS" if r.get("dns") else
                               "DNF" if r.get("dnf") else None})
    return sorted(rows, key=lambda x: (x["position"] or 99, x["driver"]))


def part_sizes(data: dict, rows: list[dict]) -> tuple[int, int]:
    """(Teilnehmer Q2, Teilnehmer Q3).

    NICHT aus den Zeiten ableiten: Wer in Q2 ohne Zeit bleibt, sähe sonst wie
    in Q1 ausgeschieden aus (Baku 2026: ANT, P16). Stattdessen aus dem Format:
    Q3 = 10, in Q1 und Q2 scheidet jeweils die Hälfte der übrigen aus
    (22 Gemeldete → 16 in Q2, 20 → 15). Gezählt werden alle Gemeldeten, auch
    ohne Zeit. Zeigen die Daten mehr Teilnehmer, gewinnen die Daten.
    """
    entries = max(len(data.get("teams", {})), len(rows))
    q3 = 10
    q2 = q3 + (entries - q3) // 2
    by_time_q3 = sum(r["times"][2] is not None for r in rows)
    by_time_q2 = sum(r["times"][1] is not None for r in rows)
    return max(q2, by_time_q2), max(q3, by_time_q3)


def render_qualifying(ax, data: dict) -> list[dict]:
    rows = qualifying_rows(data)
    if not rows:
        raise ValueError("Kein Ergebnis von OpenF1 – die Session ist evtl. noch nicht klassifiziert. "
                         "Ein paar Minuten warten und mit --refresh erneut versuchen")
    teams = data.get("teams", {})
    header = [("POS", 0.06, "right"), ("DRIVER", 0.125, "left"), ("Q1", 0.45, "right"),
              ("Q2", 0.64, "right"), ("Q3", 0.83, "right"), ("GAP", 0.97, "right")]
    fastest = [min((r["times"][k] for r in rows if r["times"][k] is not None), default=None) for k in range(3)]
    pole = fastest[2]

    table = []
    for r in rows:
        tc = team_color(teams.get(r["driver"]))
        cells = []
        for k, t in enumerate(r["times"]):
            if t is None:
                cells.append(("", COLORS["muted"], False))
            else:
                best = t == fastest[k]
                cells.append((_fmt(t), COLORS["accent"] if best else COLORS["text"], best))
        q3 = r["times"][2]
        gap = "—" if q3 is not None and q3 == pole else f"+{q3 - pole:.3f}" if q3 is not None and pole else ""
        if r["status"] and all(t is None for t in r["times"]):
            cells[0] = (r["status"], COLORS["muted"], False)
        table.append([("__stripe__", tc),
                      (str(r["position"]) if r["position"] else "–", COLORS["muted"], False),
                      (r["driver"], tc, True), *cells, (gap, COLORS["text"], False)])

    in_q2, in_q3 = part_sizes(data, rows)
    # Wer in einem Abschnitt war, aber keine Zeit hat (Baku 2026: ANT nach Crash
    # in Q1 auf P16, in Q2 nicht gefahren) → "no time" statt leerer Zelle
    for i, row in enumerate(table):
        for k, size in ((1, in_q2), (2, in_q3)):
            if i < size and rows[i]["times"][k] is None:
                row[3 + k] = ("no time", COLORS["muted"], False)
    separators = {}
    if 0 < in_q3 < len(rows):
        separators[in_q3 - 1] = "out in Q2"
    if in_q3 < in_q2 < len(rows):
        separators[in_q2 - 1] = "out in Q1"
    _table(ax, header, table, separators)
    _note(ax, unclassified(data))
    return rows


RACE = {"R", "S"}


def race_rows(data: dict) -> list[dict]:
    """Ergebniszeilen fürs Rennen (Format geprüft am Madring 2026):
    gap_to_leader ist eine Zahl (Sekunden) oder ein Text wie "+1 LAP";
    Ausfälle haben position None und dnf True. Wertung: erst die Klassierten
    nach Position, dann Ausfälle nach gefahrenen Runden (wie offiziell)."""
    grid = data.get("grid", {})
    pits: dict[str, int] = {}
    for p in data.get("pit_stops", []):
        pits[p["driver"]] = pits.get(p["driver"], 0) + 1
    rows = []
    for r in data.get("results", []):
        start = grid.get(r["driver"])
        pos = r["position"]
        rows.append({"driver": r["driver"], "position": pos, "grid": start,
                     "change": (start - pos) if start and pos else None,
                     "gap": r["gap"], "duration": _num(r["duration"]), "laps": r["laps"],
                     "points": r.get("points") or 0, "pits": pits.get(r["driver"], 0),
                     "status": "DSQ" if r.get("dsq") else "DNS" if r.get("dns") else
                               "DNF" if r.get("dnf") else None})
    classified = sorted((x for x in rows if x["position"]), key=lambda x: x["position"])
    out = sorted((x for x in rows if not x["position"]), key=lambda x: -(x["laps"] or 0))
    return classified + out


def _race_time(seconds: float) -> str:
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{int(h)}:{int(m):02d}:{s:06.3f}"


def render_race(ax, data: dict) -> list[dict]:
    rows = race_rows(data)
    if not rows:
        raise ValueError("Kein Ergebnis von OpenF1 – das Rennen ist evtl. noch nicht klassifiziert. "
                         "Ein paar Minuten warten und mit --refresh erneut versuchen")
    teams = data.get("teams", {})
    header = [("POS", 0.06, "right"), ("DRIVER", 0.125, "left"), ("GRID", 0.33, "right"),
              ("+/–", 0.43, "right"), ("GAP", 0.70, "right"), ("PIT", 0.82, "right"), ("PTS", 0.97, "right")]
    table = []
    for r in rows:
        tc = team_color(teams.get(r["driver"]))
        if r["status"]:
            gap = f"{r['status']} · {r['laps'] or 0} laps"
        elif r["position"] == 1 and r["duration"]:
            gap = _race_time(r["duration"])
        elif isinstance(r["gap"], (int, float)):
            gap = f"+{r['gap']:.3f}"
        else:
            gap = str(r["gap"] or "")
        change = r["change"]
        if change is None or change == 0:
            ch = ("", COLORS["muted"], False) if change is None else ("–", COLORS["muted"], False)
        else:
            ch = (f"{'▲' if change > 0 else '▼'}{abs(change)}", COLORS["text"], False)
        pts = r["points"]
        table.append([("__stripe__", tc),
                      (str(r["position"]) if r["position"] else "–", COLORS["muted"], False),
                      (r["driver"], tc, True),
                      (str(r["grid"]) if r["grid"] else "", COLORS["muted"], False),
                      ch,
                      (gap, COLORS["accent"] if r["position"] == 1 else
                            COLORS["muted"] if r["status"] else COLORS["text"], r["position"] == 1),
                      (str(r["pits"]), COLORS["muted"], False),
                      (f"{pts:g}" if pts else "", COLORS["text"], bool(pts))])
    in_race = sum(1 for r in rows if r["position"])
    separators = {in_race - 1: "not classified"} if 0 < in_race < len(rows) else None
    _table(ax, header, table, separators)
    notes = []
    if unclassified(data):
        notes.append("No result: " + ", ".join(unclassified(data)))
    notes.append("PIT = pit lane visits (incl. penalties) · +/– = places vs. starting grid")
    ax.text(0.99, -0.02, "\n".join(notes), transform=ax.transAxes, ha="right", va="top",
            fontsize=7.5, color=COLORS["muted"], linespacing=1.5)
    return rows


def race_mismatches(data: dict) -> list[str]:
    """Plausibilität Rennen: Rundenzahl im Ergebnis vs. Rundendaten, und
    ob zu jedem Klassierten ein Startplatz existiert."""
    if data.get("session_type") not in RACE:
        return []
    done: dict[str, int] = {}
    for lap in data.get("laps", []):
        if lap.get("LapNumber"):
            done[lap["Driver"]] = max(done.get(lap["Driver"], 0), lap["LapNumber"])
    problems = []
    for r in race_rows(data):
        own = done.get(r["driver"])
        if own is not None and r["laps"] is not None and abs(own - r["laps"]) > 1:
            problems.append(f"{r['driver']}: {r['laps']} Runden laut Ergebnis, {own} in den Rundendaten")
        if r["position"] and r["grid"] is None:
            problems.append(f"{r['driver']}: kein Startplatz gefunden")
    return problems


def render_results(ax, data: dict) -> list[dict]:
    stype = data.get("session_type")
    if stype in PRACTICE:
        return render_practice(ax, data)
    if stype in QUALI:
        return render_qualifying(ax, data)
    if stype in RACE:
        return render_race(ax, data)
    raise ValueError(f"Ergebnis-Slide für '{stype}' gibt es nicht")
