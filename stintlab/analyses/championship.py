"""WM-Status nach dem Rennen und „Wer kann noch Weltmeister werden?“.

DATENQUELLE: OpenF1 /championship_drivers und /championship_teams (Beta) –
pro Rennen/Sprint Punkte und WM-Platz VOR (…_start) und NACH (…_current)
dieser Session. Wir zählen also keine Punkte selbst zusammen; Strafen nach dem
Rennen kommen erst mit OpenF1 an → kurz nach dem Rennen notfalls mit --refresh
neu laden.

TITELRECHNUNG: Ein Fahrer kann noch Weltmeister werden, wenn seine Punkte plus
das Maximum der restlichen Saison (jeder Sieg 25, jeder Sprintsieg 8, siehe
season.py) den Punktestand des Führenden mindestens erreichen. Das ist die
übliche „rechnerisch noch möglich“-Regel: Sie nimmt an, dass der Führende nichts
mehr holt. Gleichstand (entscheidet über Siege) wird nicht aufgelöst.
"""

from __future__ import annotations

from stintlab import openf1
from stintlab.preview import team_name
from stintlab.style import COLORS, style_axes, team_color

ENDPOINTS = {"drivers": "championship_drivers", "teams": "championship_teams"}


def standings(data: dict, kind: str = "drivers", fetch=None) -> list[dict]:
    """[{name, team, points, gained, pos, pos_before, moved}] nach WM-Platz sortiert.
    moved > 0 = Plätze nach vorne. Fahrer: name = Kürzel; Teams: name = Teamname."""
    if kind not in ENDPOINTS:
        raise ValueError('kind muss "drivers" oder "teams" sein')
    fetch = fetch or openf1.cached_fetch
    raw = fetch(ENDPOINTS[kind], data["session_key"])
    if not raw:
        raise ValueError("OpenF1 hat für diese Session noch keine WM-Wertung – später mit --refresh erneut versuchen")
    by_num = {str(n): a for a, n in data.get("numbers", {}).items()}
    teams = data.get("teams", {})
    rows = []
    for r in raw:
        if kind == "drivers":
            name = by_num.get(str(r.get("driver_number")), str(r.get("driver_number")))
            team = teams.get(name)
        else:
            name = team = r.get("team_name")
        pts, before = float(r.get("points_current") or 0), float(r.get("points_start") or 0)
        pos, pos0 = r.get("position_current"), r.get("position_start")
        rows.append({"name": name, "team": team, "points": pts, "gained": pts - before,
                     "pos": pos, "pos_before": pos0,
                     "moved": (pos0 - pos) if isinstance(pos, int) and isinstance(pos0, int) else 0})
    return sorted(rows, key=lambda x: (x["pos"] if isinstance(x["pos"], int) else 99, -x["points"]))


def title_contenders(rows: list[dict], points_left: float) -> list[dict]:
    """rows + {"max": höchstmögliche Punkte, "alive": kann den Führenden noch erreichen}."""
    if not rows:
        return []
    lead = max(r["points"] for r in rows)
    return [{**r, "max": r["points"] + points_left, "alive": r["points"] + points_left >= lead} for r in rows]


def _pts(v: float) -> str:
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"


def render_championship(ax, data: dict, kind: str = "drivers", top: int | None = 10, fetch=None) -> list[dict]:
    """Balken: WM-Punkte nach dem Rennen, dazu +Punkte dieses Rennens und ▲▼ Plätze."""
    rows = standings(data, kind, fetch)
    shown = rows[:top] if top else rows
    style_axes(ax, grid_axis="x")
    n = len(shown)
    lead = max(r["points"] for r in shown) or 1.0
    name_w = lead * (0.13 if kind == "drivers" else 0.36)
    for i, r in enumerate(shown):
        y = n - 1 - i
        col = team_color(team_name(r["team"]) if kind == "drivers" else team_name(r["name"]))
        before = r["points"] - r["gained"]
        ax.barh(y, before, color=col, height=0.62, alpha=0.9, zorder=3)
        if r["gained"] > 0:        # Punkte dieses Rennens heller obendrauf
            ax.barh(y, r["gained"], left=before, color=col, height=0.62, alpha=0.4, zorder=3)
        # Platz und Name links neben der Achse – in kurzen Balken (Haas, Audi …) war kein Platz
        label = r["name"] if kind == "drivers" else team_name(r["name"])
        ax.text(-name_w - lead * 0.02, y, f"{r['pos']}", ha="right", va="center", fontsize=10,
                fontweight="bold", color=COLORS["muted"])
        ax.text(-name_w, y, label, ha="left", va="center", fontsize=10, fontweight="bold", color=col)
        txt = _pts(r["points"])
        ax.text(r["points"] + lead * 0.015, y, txt, ha="left", va="center", fontsize=11, fontweight="bold",
                color=COLORS["text"])
        extra = []
        if r["gained"]:
            extra.append(f"+{_pts(r['gained'])}")
        if r["moved"]:
            extra.append(("▲" if r["moved"] > 0 else "▼") + str(abs(r["moved"])))
        if extra:
            ax.text(r["points"] + lead * (0.03 + 0.022 * len(txt)), y, "  ".join(extra), ha="left", va="center",
                    fontsize=9, color=COLORS["accent"] if r["moved"] > 0 else COLORS["muted"], fontweight="bold")
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_xlim(-name_w - lead * 0.07, lead * 1.28)
    ax.set_xticks([t for t in ax.get_xticks() if 0 <= t <= lead * 1.28])
    ax.set_yticks([])
    ax.set_xlabel("Championship points after this race")
    ax.text(0.99, 0.01, "lighter part = points from this race · ▲▼ = places vs. before the race",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7.5, color=COLORS["muted"])
    return rows


def render_title_fight(ax, data: dict, top: int = 8, left: dict | None = None, fetch=None) -> list[dict]:
    """Wer kann noch Weltmeister werden? Punkte jetzt + höchstens noch möglich."""
    if left is None:
        from stintlab.season import max_points_left
        left = max_points_left(data["meeting_key"])
    rows = title_contenders(standings(data, "drivers", fetch), left["points"])
    alive = [r for r in rows if r["alive"]]
    shown = rows[:max(top, len(alive))]
    lead = rows[0]["points"]
    style_axes(ax, grid_axis="x")
    n = len(shown)
    xmax = max(r["max"] for r in shown)
    for i, r in enumerate(shown):
        y = n - 1 - i
        col = team_color(team_name(r["team"])) if r["alive"] else COLORS["grid"]
        ax.barh(y, r["points"], color=col, height=0.62, alpha=0.9 if r["alive"] else 0.8, zorder=3)
        ax.barh(y, r["max"] - r["points"], left=r["points"], height=0.62, zorder=2,
                color=col, alpha=0.18 if r["alive"] else 0.35, edgecolor=col, linewidth=0.8)
        ax.text(-xmax * 0.012, y, r["name"], ha="right", va="center", fontsize=10, fontweight="bold",
                color=COLORS["text"] if r["alive"] else COLORS["muted"])
        ax.text(r["max"] + xmax * 0.012, y, f"max {_pts(r['max'])}" if r["alive"] else "out",
                ha="left", va="center", fontsize=9, fontweight="bold",
                color=COLORS["text"] if r["alive"] else COLORS["muted"])
    ax.axvline(lead, color=COLORS["accent"], linewidth=1.6, linestyle="--", zorder=5)
    ax.text(lead, n - 0.35, f"  leader {_pts(lead)}", ha="left", va="bottom", fontsize=9, fontweight="bold",
            color=COLORS["accent"])
    ax.set_ylim(-0.7, n - 0.1)
    ax.set_xlim(-xmax * 0.1, xmax * 1.15)
    ax.set_yticks([])
    ax.set_xlabel("Championship points · solid = now, pale = still possible")
    note = (f"{left['races']} races + {left['sprints']} sprints left = max {left['points']} points "
            f"(every win, leader scores nothing) · ties not resolved")
    if left.get("unknown"):
        note += f"\n{left['unknown']} weekends without a session list – counted without sprint"
    ax.text(0.99, 0.01, note, transform=ax.transAxes, ha="right", va="bottom", fontsize=7.5,
            color=COLORS["muted"], linespacing=1.5)
    return rows
