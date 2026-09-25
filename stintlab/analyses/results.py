"""Ergebnis-Slide: offizielles Session-Ergebnis als Tabelle.

DATENQUELLE: OpenF1 /session_result (Beta). Deshalb gibt es mit
result_mismatches() eine Plausibilitätsprüfung gegen die Rundendaten.

JE SESSION andere Spalten – aktuell umgesetzt:
- Training: Pos, Fahrer, Reifen der schnellsten Runde, Bestzeit, Abstand, Runden
Qualifying und Rennen folgen.

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


def _table(ax, header: list[tuple[str, float, str]], rows: list[list[tuple]]) -> None:
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
        raise ValueError("Kein Ergebnis von OpenF1 – Session läuft noch oder Cache ist alt "
                         "(make_post.py mit --refresh aufrufen)")
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
    return rows


def render_results(ax, data: dict) -> list[dict]:
    stype = data.get("session_type")
    if stype in PRACTICE:
        return render_practice(ax, data)
    raise ValueError(f"Ergebnis-Slide für '{stype}' gibt es noch nicht – bisher nur Training")
