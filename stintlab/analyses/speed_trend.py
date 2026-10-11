"""Topspeed-Trend eines Teams über mehrere Wochenenden.

IDEE: Ist ein Team plötzlich langsamer auf der Geraden (z. B. nach einem
Update mit mehr Luftwiderstand)? Absolute Speed-Trap-Werte sind zwischen
Strecken nicht vergleichbar (Monza ~330, Kuala Lumpur ~310 km/h). Deshalb
zählt der ABSTAND ZUM FELD: Mittelwert der beiden Fahrer eines Teams minus
Median aller Fahrer derselben Session. 0 = so schnell wie das Feld.

DATEN: Speed Trap auf der schnellsten Runde jedes Fahrers (wie top_speed) –
nicht der Session-Höchstwert, der oft aus dem Windschatten kommt.

GRENZEN: Ein Team kann auf einer kurvigen Strecke bewusst mehr Flügel fahren
als die anderen; das sieht genauso aus wie ein Update mit mehr Luftwiderstand.
Die Speed Trap steht auf jeder Strecke woanders. Die Slide zeigt deshalb ein
Muster, keinen Beweis.

Kuala Lumpur 2026: Mercedes in Zandvoort/Monza/Baku +6 bis +9 km/h über dem
Feld, in allen vier Sessions in Kuala Lumpur darunter (Wolff: Update kostet
Topspeed).
"""

from __future__ import annotations

from statistics import median

from stintlab.analyses.speed import speed_rows
from stintlab.style import COLORS, style_axes, team_color


def team_offsets(data: dict) -> dict[str, float]:
    """{Team: Mittelwert seiner Fahrer minus Median aller Fahrer} in km/h."""
    rows, _ = speed_rows(data)
    teams = data.get("teams", {})
    vals = [r["st"] for r in rows if r.get("st") is not None]
    if not vals:
        return {}
    med = median(vals)
    by_team: dict[str, list[float]] = {}
    for r in rows:
        if r.get("st") is not None and teams.get(r["driver"]):
            by_team.setdefault(teams[r["driver"]], []).append(r["st"])
    return {t: sum(v) / len(v) - med for t, v in by_team.items()}


def render_speed_trend(ax, points: list[tuple[str, dict]], team: str,
                       split_after: int | None = None, split_label: str = "") -> list[float | None]:
    """points: [(Beschriftung, Session-Daten), ...] in zeitlicher Reihenfolge.
    split_after: senkrechte Linie nach diesem Index (z. B. zwischen Vorwochen und
    diesem Wochenende), mit split_label beschriftet."""
    if not points:
        raise ValueError("Keine Sessions für den Topspeed-Trend")
    offs = [team_offsets(d) for _, d in points]
    if not any(team in o for o in offs):
        raise ValueError(f"Team '{team}' kommt in keiner Session vor – Schreibweise wie in OpenF1, z. B. \"Mercedes\"")
    x = list(range(len(points)))
    style_axes(ax, grid_axis="y")
    others = sorted({t for o in offs for t in o} - {team})
    for t in others:
        ys = [o.get(t) for o in offs]
        ax.plot([i for i, v in zip(x, ys) if v is not None], [v for v in ys if v is not None],
                color=COLORS["muted"], linewidth=0.8, alpha=0.25, zorder=2)
    col = team_color(team)
    ys = [o.get(team) for o in offs]
    xs = [i for i, v in zip(x, ys) if v is not None]
    vs = [v for v in ys if v is not None]
    ax.plot(xs, vs, color=col, linewidth=2.6, zorder=4)
    ax.scatter(xs, vs, s=90, color=col, zorder=5)
    lo = min(min(v for o in offs for v in o.values()), 0.0)
    hi = max(max(v for o in offs for v in o.values()), 0.0)
    span = (hi - lo) or 1.0
    for i, v in zip(xs, vs):
        ax.text(i, v + span * (0.06 if v >= 0 else -0.06), f"{v:+.1f}", ha="center",
                va="bottom" if v >= 0 else "top", fontsize=10, fontweight="bold", color=col, zorder=6)
    ax.axhline(0, color=COLORS["text"], linewidth=0.9, alpha=0.6, zorder=3)
    ax.text(len(points) - 0.55, 0, "field median", ha="right", va="bottom", fontsize=8, color=COLORS["muted"])
    if split_after is not None and 0 <= split_after < len(points) - 1:
        ax.axvline(split_after + 0.5, color=COLORS["accent"], linewidth=1.0, linestyle="--", zorder=1)
        if split_label:
            ax.text(split_after + 0.55, hi + span * 0.14, split_label, ha="left", va="top",
                    fontsize=8, fontweight="bold", color=COLORS["accent"])
    ax.set_xticks(x)
    ax.set_xticklabels([lab for lab, _ in points], fontsize=8.5)
    ax.set_xlim(-0.5, len(points) - 0.5)
    ax.set_ylim(lo - span * 0.2, hi + span * 0.2)
    ax.set_ylabel("Speed trap vs. field median (km/h)")
    ax.text(0.01, 0.02, f"bold = {team} (avg of both cars)  ·  grey = other teams\n"
                        "speed trap on each driver's fastest lap · earlier weekends: qualifying",
            transform=ax.transAxes, ha="left", va="bottom", fontsize=7.5, color=COLORS["muted"], linespacing=1.5)
    return ys
