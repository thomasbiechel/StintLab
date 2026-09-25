"""Ideale Runde: beste Sektorzeiten eines Fahrers, addiert.

IDEE: Die ideale Runde ist die Runde, die ein Fahrer gefahren wäre, wenn
seine besten Sektoren aus einer einzigen Runde stammten. Der Abstand zu seiner
tatsächlichen Bestzeit zeigt, wie viel Zeit er noch liegen gelassen hat.

GÜLTIGE RUNDEN: keine Out-Lap, nicht gestrichen (Track Limits o. Ä.) und –
falls gewünscht – auf der gewählten Reifenmischung. Eine gestrichene Runde
fällt komplett heraus, auch mit ihren Sektoren: Sonst stünde ein Fahrer mit
einem Sektor, in dem er die Strecke abgekürzt hat, zu weit vorne.

GRENZEN (Training): Spritmenge und Motor-Modus sind unbekannt. Die Rangliste
zeigt, was das Training hergibt – keine Vorhersage mit Modell dahinter.
Sektoren aus verschiedenen Sessions werden nie gemischt, weil die Strecke
im Lauf des Wochenendes schneller wird.
"""

from __future__ import annotations

import textwrap

from stintlab.analyses.long_runs import _compound, _fmt, missing_drivers
from stintlab.race_control import deleted_laps
from stintlab.style import COLORS, style_axes, team_color

SECTORS = ("Sector1", "Sector2", "Sector3")


def _valid_laps(data: dict, compound: str | None) -> dict[str, list[dict]]:
    """{Fahrer: [gültige Runden]} nach den Regeln im Modul-Docstring."""
    deleted = deleted_laps(data.get("race_control", []))
    stints = data.get("stints", [])
    result: dict[str, list[dict]] = {}
    for lap in data.get("laps", []):
        drv, num = lap.get("Driver"), lap.get("LapNumber")
        if num is None or lap.get("IsPitOutLap") or (drv, num) in deleted:
            continue
        if compound and _compound(stints, drv, num) != compound.upper():
            continue
        result.setdefault(drv, []).append(lap)
    return result


def best_laps(data: dict, compound: str | None = None) -> list[dict]:
    """Tatsächliche Bestzeit pro Fahrer (gültige Runden), schnellste zuerst.

    Unabhängig von den Sektoren: Wer eine gültige Rundenzeit hat, aber einen
    fehlenden Sektor, taucht hier trotzdem auf.
    """
    results = []
    for drv, laps in _valid_laps(data, compound).items():
        times = [float(l["LapTime"]) for l in laps if l.get("LapTime")]
        if times:
            results.append({"driver": drv, "best": min(times)})
    return sorted(results, key=lambda r: r["best"])


def ideal_laps(data: dict, compound: str | None = None) -> list[dict]:
    """Ideale Runde pro Fahrer, sortiert (schnellste zuerst).

    Nur Fahrer, die in allen drei Sektoren eine gültige Zeit haben.
    """
    results = []
    for drv, laps in _valid_laps(data, compound).items():
        best_sectors = []
        for key in SECTORS:
            times = [float(l[key]) for l in laps if l.get(key)]
            if not times:
                break
            best_sectors.append(min(times))
        if len(best_sectors) < 3:
            continue
        lap_times = [float(l["LapTime"]) for l in laps if l.get("LapTime")]
        ideal = sum(best_sectors)
        best = min(lap_times) if lap_times else None
        results.append({
            "driver": drv,
            "sectors": best_sectors,
            "ideal": ideal,
            "best": best,
            # Kann durch Rundung minimal negativ werden – dann 0
            "unused": max(best - ideal, 0.0) if best is not None else None,
        })
    return sorted(results, key=lambda r: r["ideal"])


def render_ideal_lap(ax, data: dict, drivers: list[str] | None = None,
                     compound: str | None = None, top: int | None = None,
                     view: str = "both") -> list[dict]:
    """view:
    - "best":  Rangliste der tatsächlichen Bestzeiten
    - "ideal": Rangliste der idealen Runden, mit Plätzen gewonnen/verloren
               gegenüber der Bestzeiten-Rangliste (▲2 / ▼1)
    - "both":  ideale Runde als Balken, Bestzeit als Umriss
    """
    if view not in ("both", "best", "ideal"):
        raise ValueError('view muss "both", "best" oder "ideal" sein')

    if view == "best":
        rows = best_laps(data, compound)
        key = "best"
    else:
        rows = ideal_laps(data, compound)
        key = "ideal"
    if drivers:
        rows = [r for r in rows if r["driver"] in drivers]
    if not rows:
        raise ValueError("Keine gültigen Runden gefunden – compound prüfen")
    missing = missing_drivers(data, rows, drivers)

    # Platz in der Bestzeiten-Rangliste – für ▲/▼ auf der Ideal-Slide
    best_rank = {r["driver"]: i for i, r in enumerate(
        [r for r in best_laps(data, compound) if not drivers or r["driver"] in drivers])}
    if top:
        rows = rows[:top]

    teams = data.get("teams", {})
    fastest = rows[0][key]
    deltas = [r[key] - fastest for r in rows]
    colors = [team_color(teams.get(r["driver"])) for r in rows]

    style_axes(ax, grid_axis="x")
    y = list(range(len(rows)))
    if view == "both":
        outline = [(r["best"] - fastest) if r["best"] is not None else d for r, d in zip(rows, deltas)]
        ax.barh(y, outline, height=0.62, color="none", edgecolor=colors, linewidth=1.1)
    else:
        outline = deltas
    ax.barh(y, deltas, height=0.62, color=colors, alpha=0.9)
    ax.invert_yaxis()

    ax.set_yticks(y)
    ax.set_yticklabels([r["driver"] for r in rows], fontsize=9, fontweight="bold")
    for tick, c in zip(ax.get_yticklabels(), colors):
        tick.set_color(c)

    right = max(outline) if max(outline) > 0 else 1.0
    for i, (r, d, o) in enumerate(zip(rows, deltas, outline)):
        label = f"{_fmt(r[key])}" if d == 0 else f"+{d:.2f} s"
        if view == "both" and r["unused"] is not None:
            label += f"  ·  {r['unused']:.2f} s left"
        if view == "ideal" and r["driver"] in best_rank:
            change = best_rank[r["driver"]] - i
            if change:
                label += f"  ·  {'▲' if change > 0 else '▼'}{abs(change)}"
        ax.text(max(d, o) + right * 0.02, i, label, va="center", fontsize=8, color=COLORS["text"])

    ax.set_xlim(-right * 0.03, right * 1.6)
    ax.set_xlabel({"best": "Best lap, gap to fastest (s)",
                   "ideal": "Ideal lap (best sectors), gap to fastest (s)",
                   "both": "Ideal lap (best sectors), gap to fastest (s)"}[view])

    notes = {"both": ["solid = ideal lap  ·  outline = actual best lap"],
             "ideal": ["▲▼ = places gained/lost vs. best-lap order"],
             "best": []}[view]
    if missing:
        what = "valid lap" if view == "best" else "full lap"
        head = f"No {what}{' on ' + compound.capitalize() + 's' if compound else ''}: "
        notes = textwrap.wrap(head + ", ".join(missing), width=70) + notes
    if notes:
        ax.set_ylim(len(rows) - 0.5 + 0.55 * len(notes) + 0.3, -0.6)
        ax.text(0.99, 0.02, "\n".join(notes), transform=ax.transAxes, ha="right", va="bottom",
                fontsize=7.5, color=COLORS["muted"], linespacing=1.5)
    return rows
