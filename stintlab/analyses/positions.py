"""Positionsverlauf: Wer lag nach jeder Runde auf welchem Platz.

METHODE: Die Position nach Runde N ist die Reihenfolge, in der die Fahrer die
Ziellinie am Ende von Runde N überqueren (lap_ends) – dieselbe Grundlage wie
bei gap_between. Wer Runde N nicht beendet hat (ausgeschieden), zählt ab da
nicht mehr mit. Überrundete Fahrer beenden Runde N später und landen damit
automatisch hinter allen, die sie schon beendet haben.

Bewusst NICHT verwendet: /position von OpenF1. Das liefert nur Änderungen mit
Zeitstempel und ist im Rennen lückenhaft (Baku 2026: für viele Runden kein
Eintrag).

ZWEI KORREKTUREN:
- Runde 0 = Startaufstellung (data["grid"], enthält Strafen).
- Letzte Runde = offizielles Ergebnis (data["results"]), falls vorhanden.
  Die Zeitstempel der Zielrunde sind ungenau: In Baku 2026 lag VER dort
  0,00 s "vor" RUS, offiziell gewann RUS mit 0,196 s.
"""

from __future__ import annotations

from datetime import datetime

from matplotlib.ticker import MaxNLocator

from stintlab.race_control import restricted_laps
from stintlab.style import COLORS, style_axes, team_color


def compute_positions(lap_ends: dict[str, dict[int, datetime]],
                      grid: dict[str, int] | None = None,
                      results: list[dict] | None = None) -> dict[str, dict[int, int]]:
    """{Fahrer: {Runde: Position}}, Runde 0 = Startplatz (falls grid)."""
    positions: dict[str, dict[int, int]] = {d: {} for d in lap_ends}
    for drv, pos in (grid or {}).items():
        if pos:
            positions.setdefault(drv, {})[0] = pos

    all_laps = sorted({n for ends in lap_ends.values() for n in ends})
    for n in all_laps:
        order = sorted((ends[n], d) for d, ends in lap_ends.items() if n in ends)
        for pos, (_, drv) in enumerate(order, start=1):
            positions[drv][n] = pos

    # Offizielles Ergebnis überschreibt die Position in der letzten Runde
    for r in results or []:
        drv, pos = r.get("driver"), r.get("position")
        if drv in positions and pos and not (r.get("dnf") or r.get("dns") or r.get("dsq")):
            laps = [n for n in positions[drv] if n > 0]
            if laps:
                positions[drv][max(laps)] = pos
    return {d: p for d, p in positions.items() if p}


def render_positions(ax, data: dict, drivers: list[str] | None = None,
                     laps: tuple[int, int] | None = None) -> dict[str, dict[int, int]]:
    """Alle Fahrer als dünne graue Linien, die gewählten in Teamfarbe.

    drivers: hervorgehobene Fahrer, z. B. ["ANT", "PIA"] – leer = alle farbig
    laps:    optionales Fenster (erste, letzte Runde); Runde 0 = Startplatz
    """
    positions = compute_positions(data.get("lap_ends", {}), data.get("grid"), data.get("results"))
    if laps:
        first, last = laps
        positions = {d: {n: p for n, p in v.items() if first <= n <= last} for d, v in positions.items()}
        positions = {d: v for d, v in positions.items() if v}
    if not positions:
        raise ValueError("Keine Positionsdaten im gewählten Rundenfenster")
    highlight = drivers or list(positions)
    missing = [d for d in highlight if d not in positions]
    if missing:
        raise ValueError(f"Keine Positionen für {', '.join(missing)} – Kürzel prüfen")

    teams = data.get("teams", {})
    style_axes(ax, grid_axis="y")
    all_laps = sorted({n for v in positions.values() for n in v})
    for lap in sorted(restricted_laps(data.get("race_control", []))):
        if all_laps[0] <= lap <= all_laps[-1]:
            ax.axvspan(lap - 0.5, lap + 0.5, color=COLORS["muted"], alpha=0.15, linewidth=0)

    for drv, series in positions.items():
        if drv in highlight:
            continue
        xs = sorted(series)
        ax.plot(xs, [series[x] for x in xs], color=COLORS["muted"], alpha=0.35, linewidth=0.8)

    seen_teams: set[str] = set()
    for drv in highlight:
        series = positions[drv]
        xs = sorted(series)
        ys = [series[x] for x in xs]
        team = teams.get(drv)
        color = team_color(team)
        # Zweiter Fahrer desselben Teams gestrichelt, sonst nicht unterscheidbar
        style = "--" if team in seen_teams else "-"
        seen_teams.add(team)
        ax.plot(xs, ys, color=color, linewidth=2.2, linestyle=style, zorder=4)
        ax.scatter([xs[0], xs[-1]], [ys[0], ys[-1]], s=28, color=color, zorder=5,
                   edgecolor=COLORS["bg"], linewidth=1)
        ax.annotate(f"{drv} P{ys[-1]}", (xs[-1], ys[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=8.5, color=color, fontweight="bold")
        ax.annotate(f"P{ys[0]}", (xs[0], ys[0]), xytext=(-6, 0), textcoords="offset points",
                    va="center", ha="right", fontsize=8, color=color)

    n_drivers = max(p for v in positions.values() for p in v.values())
    ax.set_ylim(n_drivers + 0.7, 0.3)
    ax.set_yticks(range(1, n_drivers + 1))
    ax.tick_params(axis="y", labelsize=7.5)
    span = all_laps[-1] - all_laps[0]
    ax.set_xlim(all_laps[0] - span * 0.06, all_laps[-1] + span * 0.12)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    if all_laps[0] == 0:
        ax.set_xticks([0] + [t for t in ax.get_xticks() if 0 < t <= all_laps[-1]])
        ax.set_xticklabels(["Grid"] + [str(int(t)) for t in ax.get_xticks()[1:]])
    ax.set_xlabel("Lap")
    ax.set_ylabel("Position")
    ax.text(0.99, 0.02, "Order at the line after each lap · final lap = official result",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7.5, color=COLORS["muted"])
    return positions
