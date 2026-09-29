"""Die besten Starter der Saison: Plätze in Runde 1 – fair gerechnet.

FRAGE: Wer gewinnt am Start am meisten Plätze?

DAS PROBLEM (Confounder Startplatz): Von P18 gewinnt man fast automatisch
Plätze, von der Pole kann man keine gewinnen. Ein einfacher Durchschnitt würde
messen, wer oft hinten startet – nicht, wer gut startet.

METHODE, pro Rennen:
- nur Fahrer, die Runde 1 beendet haben. Ihr Startplatz wird UNTER IHNEN neu
  durchgezählt – ein Ausfall in Runde 1 ist kein gewonnener Platz.
- Gewinn = Startrang − Position nach Runde 1 (an der Ziellinie)
- Rennen mit Safety Car / roter Flagge in Runde 1 zählen nicht
- ERWARTUNG je Startrang = mittlerer Gewinn aller Starts von diesem Rang
  (± 1 Rang zusammengefasst, sonst zu wenige Starts pro Platz)
- Wertung pro Fahrer = Mittel von (Gewinn − Erwartung): „so viele Plätze mehr
  als üblich von dort“. Dazu der rohe Mittelwert als Text.

GRENZE: Position an der Linie nach Runde 1 – Überholmanöver, die in derselben
Runde wieder verloren gehen, sieht man nicht. Boxenstopp in Runde 1 = Start zählt nicht.
"""

from __future__ import annotations

from statistics import mean

from stintlab.analyses.positions import compute_positions
from stintlab.preview import team_name
from stintlab.race_control import neutral_laps
from stintlab.style import COLORS, style_axes, team_color

MIN_STARTS = 5


def race_starts(race: dict) -> list[dict]:
    """[{driver, team, grid_rank, gain}] eines Rennens; [] wenn Runde 1 neutralisiert war."""
    if 1 in neutral_laps(race.get("race_control", [])):
        return []
    grid = race.get("grid", {})
    lap1 = {d: ends[1] for d, ends in race.get("lap_ends", {}).items() if 1 in ends}
    pit1 = {p["driver"] for p in race.get("pit_stops", []) if p.get("lap") == 1}
    drivers = [d for d in lap1 if d in grid and d not in pit1]
    if len(drivers) < 5:
        return []
    by_grid = sorted(drivers, key=lambda d: grid[d])
    grid_rank = {d: i for i, d in enumerate(by_grid, start=1)}
    pos = compute_positions({d: {1: lap1[d]} for d in drivers})
    teams = race.get("teams", {})
    return [{"driver": d, "team": team_name(teams.get(d)), "grid_rank": grid_rank[d],
             "gain": grid_rank[d] - pos[d][1], "place": race.get("place")} for d in drivers]


def expected_gain(starts: list[dict]) -> dict[int, float]:
    """{Startrang: mittlerer Gewinn aller Starts von Rang ±1}."""
    ranks = sorted({s["grid_rank"] for s in starts})
    out = {}
    for g in ranks:
        near = [s["gain"] for s in starts if abs(s["grid_rank"] - g) <= 1]
        out[g] = mean(near)
    return out


def starter_rows(races: list[dict], min_starts: int = MIN_STARTS) -> tuple[list[dict], int]:
    """([{driver, team, score, raw, n}], Anzahl gewerteter Rennen), score absteigend."""
    starts, counted = [], 0
    for r in races:
        s = race_starts(r)
        counted += bool(s)
        starts += s
    exp = expected_gain(starts) if starts else {}
    by: dict[str, list[dict]] = {}
    for s in starts:
        by.setdefault(s["driver"], []).append(s)
    rows = []
    for d, ss in by.items():
        if len(ss) < min_starts:
            continue
        rows.append({"driver": d, "team": ss[-1]["team"], "n": len(ss),
                     "score": mean(s["gain"] - exp[s["grid_rank"]] for s in ss),
                     "raw": mean(s["gain"] for s in ss)})
    return sorted(rows, key=lambda r: -r["score"]), counted


def render_best_starters(ax, races: list[dict], top: int | None = 20) -> list[dict]:
    rows, counted = starter_rows(races)
    if not rows:
        raise ValueError("Zu wenige gewertete Starts – mehr Rennen oder min_starts senken")
    rows = rows[:top] if top else rows
    style_axes(ax, grid_axis="x")
    n = len(rows)
    lim = max(max(abs(r["score"]) for r in rows) * 1.25, 0.5)
    for i, r in enumerate(rows):
        y = n - 1 - i
        col = team_color(r["team"])
        ax.barh(y, r["score"], color=col, height=0.6, alpha=0.9, zorder=3)
        ax.text(-lim * 1.02, y, r["driver"], ha="right", va="center", fontsize=10, fontweight="bold", color=col)
        right = r["score"] >= 0
        ax.text(r["score"] + (lim * 0.03 if right else -lim * 0.03), y, f"{r['score']:+.1f}",
                ha="left" if right else "right", va="center", fontsize=9, fontweight="bold", color=COLORS["text"])
    ax.axvline(0, color=COLORS["muted"], linewidth=0.8)
    ax.set_xlim(-lim * 1.25, lim * 1.15)
    ax.set_xticks([t for t in ax.get_xticks() if -lim * 1.02 <= t <= lim * 1.15])
    # Platz für die zweizeilige Fußnote, wächst mit der Zeilenzahl (sonst überlappt sie)
    ax.set_ylim(-0.7 - 0.09 * n - 0.6, n - 0.3)
    ax.set_yticks([])
    ax.set_xlabel("Lap-1 places gained per start, vs. what that grid slot usually gains")
    note = ax.text(0.99, 0.01, f"{counted} races · lap-1 retirements, lap-1 pit stops and SC/red flag on lap 1 left out\n"
            f"drivers with fewer than {MIN_STARTS} counted starts left out",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7.5, color=COLORS["muted"], linespacing=1.5)
    note.keep_font = True
    return rows
