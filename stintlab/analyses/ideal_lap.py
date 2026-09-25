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
from stintlab.quali import PARTS, lap_parts
from stintlab.race_control import deleted_laps
from stintlab.style import COLORS, style_axes, team_color

SECTORS = ("Sector1", "Sector2", "Sector3")


def _valid_laps(data: dict, compound: str | None, part: str | None = None) -> dict[str, list[dict]]:
    """{Fahrer: [gültige Runden]} nach den Regeln im Modul-Docstring.

    part: nur Runden eines Qualifying-Abschnitts ("Q1", "Q2", "Q3").
    """
    deleted = deleted_laps(data.get("race_control", []), data.get("laps", []), data.get("lap_ends", {}))
    part_of = lap_parts(data) if part else {}
    stints = data.get("stints", [])
    result: dict[str, list[dict]] = {}
    for lap in data.get("laps", []):
        drv, num = lap.get("Driver"), lap.get("LapNumber")
        if num is None or lap.get("IsPitOutLap") or (drv, num) in deleted:
            continue
        if part and part_of.get((drv, num)) != part:
            continue
        if compound and _compound(stints, drv, num) != compound.upper():
            continue
        result.setdefault(drv, []).append(lap)
    return result


def best_laps(data: dict, compound: str | None = None, part: str | None = None) -> list[dict]:
    """Tatsächliche Bestzeit pro Fahrer (gültige Runden), schnellste zuerst.

    Unabhängig von den Sektoren: Wer eine gültige Rundenzeit hat, aber einen
    fehlenden Sektor, taucht hier trotzdem auf.
    """
    results = []
    for drv, laps in _valid_laps(data, compound, part).items():
        times = [float(l["LapTime"]) for l in laps if l.get("LapTime")]
        if times:
            results.append({"driver": drv, "best": min(times)})
    return sorted(results, key=lambda r: r["best"])


def ideal_laps(data: dict, compound: str | None = None, part: str | None = None) -> list[dict]:
    """Ideale Runde pro Fahrer, sortiert (schnellste zuerst).

    Nur Fahrer, die in allen drei Sektoren eine gültige Zeit haben.
    """
    results = []
    for drv, laps in _valid_laps(data, compound, part).items():
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
                     view: str = "both", part: str | None = None) -> list[dict]:
    """view:
    - "best":  Rangliste der tatsächlichen Bestzeiten
    - "ideal": Rangliste der idealen Runden, mit Plätzen gewonnen/verloren
               gegenüber der Bestzeiten-Rangliste (▲2 / ▼1)
    - "both":  ideale Runde als Balken, Bestzeit als Umriss – beides als
               Abstand zur SCHNELLSTEN ECHTEN Runde (im Q3 also zur Pole).
               Negativ = die ideale Runde wäre schneller gewesen.
    part: nur ein Qualifying-Abschnitt, z. B. "Q3".
    """
    if view not in ("both", "best", "ideal"):
        raise ValueError('view muss "both", "best" oder "ideal" sein')
    if part is not None and part not in PARTS:
        raise ValueError(f'part muss einer von {", ".join(PARTS)} sein')

    if view == "best":
        rows = best_laps(data, compound, part)
        key = "best"
    else:
        rows = ideal_laps(data, compound, part)
        key = "ideal"
    if drivers:
        rows = [r for r in rows if r["driver"] in drivers]
    if not rows:
        raise ValueError("Keine gültigen Runden gefunden – compound/part prüfen")
    # Fehlende: im Qualifying-Abschnitt nur, wer dort gefahren ist
    candidates = drivers or (sorted({d for d in _valid_laps(data, None, part)}) if part else None)
    missing = missing_drivers(data, rows, candidates)

    # Platz in der Bestzeiten-Rangliste – für ▲/▼ auf der Ideal-Slide
    best_list = best_laps(data, compound, part)
    best_rank = {r["driver"]: i for i, r in enumerate(
        [r for r in best_list if not drivers or r["driver"] in drivers])}
    if top:
        rows = rows[:top]

    teams = data.get("teams", {})
    if view == "both":
        # Bezug: schnellste echte Runde (Pole) – dann zeigt ein negativer
        # Balken, dass jemand mit seiner idealen Runde schneller gewesen wäre
        fastest = min(r["best"] for r in rows if r["best"] is not None)
    else:
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
    ax.axvline(0, color=COLORS["muted"], linewidth=0.8, zorder=1)
    ax.invert_yaxis()

    ax.set_yticks(y)
    ax.set_yticklabels([r["driver"] for r in rows], fontsize=9, fontweight="bold")
    for tick, c in zip(ax.get_yticklabels(), colors):
        tick.set_color(c)

    lo = min(min(deltas), min(outline), 0.0)
    hi = max(max(deltas), max(outline), 0.0)
    span = (hi - lo) or 1.0
    for i, (r, d, o) in enumerate(zip(rows, deltas, outline)):
        if view == "both":
            if r["best"] == fastest:
                # Pole: echte Zeit nennen, dazu die ideale Runde
                label = f"{'POLE' if part == 'Q3' else 'FASTEST'} {_fmt(r['best'])}"
                if r["unused"] is not None and r["unused"] >= 0.005:
                    label += f"  ·  ideal {d:+.2f} s"
            else:
                label = f"{d:+.2f} s"
                # "0.00 s left" ist keine Information – nur zeigen, wenn es etwas gibt
                if r["unused"] is not None and r["unused"] >= 0.005:
                    label += f"  ·  {r['unused']:.2f} s left"
        else:
            label = f"{_fmt(r[key])}" if d == 0 else f"+{d:.2f} s"
        if view == "ideal" and r["driver"] in best_rank:
            change = best_rank[r["driver"]] - i
            if change:
                label += f"  ·  {'▲' if change > 0 else '▼'}{abs(change)}"
        ax.text(max(d, o, 0.0) + span * 0.02, i, label, va="center", fontsize=8, color=COLORS["text"])

    ax.set_xlim(lo - span * 0.05, hi + span * 0.75)
    ref = "pole" if part == "Q3" else "fastest lap"
    ax.set_xlabel({"best": "Best lap, gap to fastest (s)",
                   "ideal": "Ideal lap (best sectors), gap to fastest (s)",
                   "both": f"Gap to {ref} (s)"}[view])

    notes = {"both": [f"solid = ideal lap  ·  outline = actual best lap  ·  0 = {ref}"],
             "ideal": ["▲▼ = places gained/lost vs. best-lap order"],
             "best": []}[view]
    if missing:
        what = "valid lap" if view == "best" else "full lap"
        head = f"No {what}{' on ' + compound.capitalize() + 's' if compound else ''}{' in ' + part if part else ''}: "
        notes = textwrap.wrap(head + ", ".join(missing), width=70) + notes
    if notes:
        ax.set_ylim(len(rows) - 0.5 + 0.55 * len(notes) + 0.3, -0.6)
        ax.text(0.99, 0.02, "\n".join(notes), transform=ax.transAxes, ha="right", va="bottom",
                fontsize=7.5, color=COLORS["muted"], linespacing=1.5)
    return rows
