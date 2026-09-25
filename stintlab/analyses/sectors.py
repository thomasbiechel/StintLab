"""Sektor-Slide: beste Zeit jedes Fahrers in Sektor 1, 2 und 3.

Drei Spalten nebeneinander, jede eine eigene Rangliste. Zeigt, WO ein Fahrer
schnell ist – z. B. auf den Geraden oder im kurvigen Teil.

GÜLTIGE RUNDEN: dieselben Regeln wie bei der idealen Runde (keine Out-Laps,
keine gestrichenen Runden, optional nur eine Mischung oder ein Q-Abschnitt).
Dadurch passen Sektor-Slide und Ideal-Slide zahlenmäßig zusammen.

FARBEN: Fahrer in Teamfarbe, schnellste Zeit pro Sektor in Lila.
"""

from __future__ import annotations

from matplotlib.patches import Rectangle

from stintlab.analyses.ideal_lap import SECTORS, _valid_laps
from stintlab.style import COLORS, team_color


def best_sectors(data: dict, compound: str | None = None,
                 part: str | None = None) -> list[list[tuple[str, float]]]:
    """[[(Fahrer, Zeit), ...] für S1, S2, S3] – jeweils schnellste zuerst.

    Ein Fahrer erscheint in jeder Spalte, in der er eine gültige Zeit hat –
    auch wenn ihm in einem anderen Sektor eine fehlt.
    """
    columns = []
    laps_by_driver = _valid_laps(data, compound, part)
    for key in SECTORS:
        best = []
        for drv, laps in laps_by_driver.items():
            times = [float(l[key]) for l in laps if l.get(key)]
            if times:
                best.append((drv, min(times)))
        columns.append(sorted(best, key=lambda x: x[1]))
    return columns


def render_sectors(ax, data: dict, compound: str | None = None,
                   part: str | None = None) -> list[list[tuple[str, float]]]:
    columns = best_sectors(data, compound, part)
    if not any(columns):
        raise ValueError("Keine Sektorzeiten gefunden – compound/part prüfen")
    teams = data.get("teams", {})

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    n = max(len(c) for c in columns)
    top = 0.965
    h = top / (n + 1)
    width = 1 / 3

    for c, (name, col) in enumerate(zip(("SECTOR 1", "SECTOR 2", "SECTOR 3"), columns)):
        x0 = c * width
        ax.text(x0 + width / 2, top - h / 2, name, ha="center", va="center",
                fontsize=8, color=COLORS["muted"], fontweight="bold")
        ax.plot([x0 + 0.01, x0 + width - 0.01], [top - h, top - h], color=COLORS["grid"], linewidth=0.8)
        if not col:
            continue
        fastest = col[0][1]
        for i, (drv, t) in enumerate(col):
            y = top - h * (i + 1.5)
            if i % 2 == 0:
                ax.add_patch(Rectangle((x0 + 0.01, y - h / 2), width - 0.02, h,
                                       color=COLORS["plot"], zorder=0, linewidth=0))
            tc = team_color(teams.get(drv))
            ax.add_patch(Rectangle((x0 + 0.02, y - h * 0.3), 0.006, h * 0.6, color=tc, linewidth=0))
            ax.text(x0 + 0.035, y, drv, ha="left", va="center", fontsize=8.5, color=tc, fontweight="bold")
            is_best = t == fastest
            ax.text(x0 + 0.215, y, f"{t:.3f}", ha="right", va="center", fontsize=8.5,
                    color=COLORS["accent"] if is_best else COLORS["text"],
                    fontweight="bold" if is_best else "normal")
            if not is_best:
                ax.text(x0 + width - 0.02, y, f"+{t - fastest:.3f}", ha="right", va="center",
                        fontsize=7.5, color=COLORS["muted"])
    return columns
