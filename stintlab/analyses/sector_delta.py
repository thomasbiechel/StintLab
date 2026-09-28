"""Wo gewinnt, wo verliert B gegenüber A – Sektor für Sektor, Runde für Runde.

Für jede Runde im Fenster: Sektorzeit B minus Sektorzeit A (> 0 = B langsamer).
Gezeigt: jede Runde als Punkt, der Median als Balken. Runden, in denen einem
der beiden eine Sektorzeit fehlt oder die unter SC/VSC oder mit Boxenstopp
liefen, fallen für diesen Sektor raus.

Nutzen: Zeigt ein wiederkehrendes Muster (z. B. schneller auf der Geraden,
langsamer in den Kurven), das in der Rundenzeit verschwindet, weil es sich
aufhebt.
"""

from __future__ import annotations

from statistics import median

from stintlab.race_control import restricted_laps
from stintlab.style import COLORS, style_axes, team_color

PARTS = ["Sector1", "Sector2", "Sector3", "LapTime"]
LABELS = ["Sector 1", "Sector 2", "Sector 3", "Lap"]


def compute_sector_delta(data: dict, a: str, b: str,
                         laps: tuple[int, int] | None = None) -> dict[str, dict[int, float]]:
    """{Teil: {Runde: Zeit B − Zeit A}}"""
    restricted = restricted_laps(data.get("race_control", []))
    pit = {(p["driver"], p["lap"]) for p in data.get("pit_stops", [])}
    rows = {(l["Driver"], l["LapNumber"]): l for l in data.get("laps", [])}
    out: dict[str, dict[int, float]] = {p: {} for p in PARTS}
    numbers = sorted({n for d, n in rows if d == a})
    for n in numbers:
        if laps and not (laps[0] <= n <= laps[1]):
            continue
        if n in restricted or (a, n) in pit or (b, n) in pit:
            continue
        ra, rb = rows.get((a, n)), rows.get((b, n))
        if not ra or not rb or ra.get("IsPitOutLap") or rb.get("IsPitOutLap"):
            continue
        for p in PARTS:
            if ra.get(p) and rb.get(p):
                out[p][n] = float(rb[p]) - float(ra[p])
    return out


def render_sector_delta(ax, data: dict, a: str, b: str, laps: tuple[int, int] | None = None) -> dict:
    deltas = compute_sector_delta(data, a, b, laps)
    if not any(deltas.values()):
        raise ValueError(f"Keine gemeinsamen Sektorzeiten für {a}/{b}")
    teams = data.get("teams", {})
    ca, cb = team_color(teams.get(a)), team_color(teams.get(b))
    style_axes(ax, grid_axis="y")

    all_vals = [v for d in deltas.values() for v in d.values()]
    span = max(abs(v) for v in all_vals)
    for i, p in enumerate(PARTS):
        vals = list(deltas[p].values())
        if not vals:
            continue
        m = median(vals)
        c = ca if m > 0 else cb       # Farbe dessen, der in diesem Teil schneller ist
        ax.bar(i, m, width=0.6, color=c, alpha=0.85)
        ax.scatter([i + (k - len(vals) / 2) * 0.025 for k in range(len(vals))], vals, s=12,
                   color=COLORS["text"], alpha=0.55, zorder=4, linewidth=0)
        # Beschriftung neben dem Balken, damit sie nicht in den Punkten verschwindet
        ax.text(i + 0.33, m, f"{m:+.2f} s", ha="left", va="center",
                fontsize=10, fontweight="bold", color=COLORS["text"])
    ax.axhline(0, color=COLORS["muted"], linewidth=0.8)
    ax.set_xlim(-0.5, len(PARTS) - 0.5 + 0.45)   # Platz für die Beschriftung rechts
    ax.set_xticks(range(len(PARTS)))
    ax.set_xticklabels(LABELS, fontsize=9.5)
    ax.set_ylim(-span * 1.35, span * 1.35)
    ax.set_ylabel(f"{b} minus {a} (s)")
    ax.text(0.01, 0.97, f"▲ {b} slower", transform=ax.transAxes, color=ca, fontsize=9,
            fontweight="bold", va="top")
    ax.text(0.01, 0.03, f"▼ {b} faster", transform=ax.transAxes, color=cb, fontsize=9,
            fontweight="bold", va="bottom")
    n = len(deltas["LapTime"])
    ax.text(0.99, 0.03, f"bar = median · dots = single laps ({n})", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=7.5, color=COLORS["muted"])
    return deltas
