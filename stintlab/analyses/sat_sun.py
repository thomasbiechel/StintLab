"""Samstags- oder Sonntagsfahrer? Quali-Platz gegen Rennpace.

FRAGE: Wer ist im Rennen stärker als im Qualifying – und wer umgekehrt?

METHODE, pro Rennen:
- Rennpace = Median der sauberen Rennrunden (race_pace.clean_laps: ohne Runde 1,
  Boxen-Runden, SC/VSC/rote Flagge, Ausreißer > 107 %); nur Fahrer mit
  mindestens MIN_CLEAN_LAPS sauberen Runden.
- Unter GENAU diesen Fahrern: Rang im Qualifying (offizielle Quali-Position,
  vor Startplatzstrafen) und Rang nach Rennpace.
- Differenz = Quali-Rang − Pace-Rang. > 0: im Rennen weiter vorne einzuordnen
  als im Qualifying → „Sonntagsfahrer“.
- Pro Fahrer: Mittel über die Saison.

GRENZE: Rennpace hängt auch an Verkehr, Strategie und Reifen – wer im Pulk
feststeckt, fährt langsamere Runden, ohne selbst langsamer zu sein. Das
betrifft eher Fahrer im Mittelfeld. Der Mittelwert über viele Rennen dämpft es.
"""

from __future__ import annotations

from statistics import mean, median

from stintlab.analyses.race_pace import MIN_CLEAN_LAPS, clean_laps
from stintlab.preview import team_name
from stintlab.style import COLORS, style_axes, team_color

MIN_RACES = 5


def race_deltas(race: dict, quali: dict) -> list[dict]:
    """[{driver, team, delta}] eines Rennens. quali = light_session(…, "Q")."""
    clean, _ = clean_laps(race)
    pace = {d: median(t) for d, t in clean.items() if len(t) >= MIN_CLEAN_LAPS}
    qpos = {r["driver"]: r["position"] for r in quali.get("results", []) if isinstance(r.get("position"), int)}
    drivers = [d for d in pace if d in qpos]
    if len(drivers) < 5:
        return []
    q_rank = {d: i for i, d in enumerate(sorted(drivers, key=lambda d: qpos[d]), start=1)}
    p_rank = {d: i for i, d in enumerate(sorted(drivers, key=lambda d: pace[d]), start=1)}
    teams = race.get("teams", {})
    return [{"driver": d, "team": team_name(teams.get(d)), "delta": q_rank[d] - p_rank[d]} for d in drivers]


def sat_sun_rows(pairs: list[tuple[dict, dict]], min_races: int = MIN_RACES) -> tuple[list[dict], int]:
    """pairs = [(Rennen, Qualifying)] → ([{driver, team, delta, n}], gewertete Rennen)."""
    by: dict[str, list[dict]] = {}
    counted = 0
    for race, quali in pairs:
        ds = race_deltas(race, quali)
        counted += bool(ds)
        for x in ds:
            by.setdefault(x["driver"], []).append(x)
    rows = [{"driver": d, "team": xs[-1]["team"], "n": len(xs), "delta": mean(x["delta"] for x in xs)}
            for d, xs in by.items() if len(xs) >= min_races]
    return sorted(rows, key=lambda r: -r["delta"]), counted


def render_saturday_sunday(ax, pairs: list[tuple[dict, dict]], top: int | None = 20) -> list[dict]:
    rows, counted = sat_sun_rows(pairs)
    if not rows:
        raise ValueError("Zu wenige gewertete Rennen – mehr Rennen oder min_races senken")
    rows = rows[:top] if top else rows
    style_axes(ax, grid_axis="x")
    n = len(rows)
    lim = max(max(abs(r["delta"]) for r in rows) * 1.25, 0.5)
    for i, r in enumerate(rows):
        y = n - 1 - i
        col = team_color(r["team"])
        ax.barh(y, r["delta"], color=col, height=0.6, alpha=0.9, zorder=3)
        ax.text(-lim * 1.02, y, r["driver"], ha="right", va="center", fontsize=10, fontweight="bold", color=col)
        right = r["delta"] >= 0
        ax.text(r["delta"] + (lim * 0.03 if right else -lim * 0.03), y, f"{r['delta']:+.1f}",
                ha="left" if right else "right", va="center", fontsize=9, fontweight="bold", color=COLORS["text"])
    ax.axvline(0, color=COLORS["muted"], linewidth=0.8)
    ax.text(lim * 0.97, n - 0.35, "SUNDAY DRIVER →", ha="right", va="bottom", fontsize=8.5, fontweight="bold",
            color=COLORS["accent"])
    ax.text(-lim * 0.97, n - 0.35, "← SATURDAY DRIVER", ha="left", va="bottom", fontsize=8.5, fontweight="bold",
            color=COLORS["muted"])
    ax.set_xlim(-lim * 1.25, lim * 1.15)
    ax.set_xticks([t for t in ax.get_xticks() if -lim * 1.02 <= t <= lim * 1.15])
    # Platz für die zweizeilige Fußnote, wächst mit der Zeilenzahl (sonst überlappt sie)
    ax.set_ylim(-0.7 - 0.09 * n - 0.6, n + 0.2)
    ax.set_yticks([])
    ax.set_xlabel("Race-pace rank vs. qualifying rank (places, average per race)")
    note = ax.text(0.99, 0.01, f"{counted} races · pace = median of clean race laps (≥ {MIN_CLEAN_LAPS}) · "
            f"both ranks among the same drivers\ntraffic and strategy affect race pace · "
            f"drivers with fewer than {MIN_RACES} races left out",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7.5, color=COLORS["muted"], linespacing=1.5)
    note.keep_font = True
    return rows
