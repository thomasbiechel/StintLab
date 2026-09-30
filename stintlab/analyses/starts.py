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

MESSPUNKT (measure in der post.toml):
- "turn1" (Standard seit 30.09.2026): Reihenfolge kurz nach der ersten Kurve,
  aus den Positionsdaten (analyses/first_corner.py). Das misst den START.
- "lap1": Position an der Ziellinie nach Runde 1 (bisher). Misst Start + ganze
  erste Runde – wer am Start gewinnt und in Kurve 4 wieder verliert, zählt null.
Rennen, deren Messung nach der ersten Kurve scheitert (keine Positionsdaten),
fallen bei "turn1" heraus – nicht mit der Linie mischen, sonst misst die Wertung
zwei verschiedene Dinge.

GRENZE ("lap1"): Position an der Linie nach Runde 1 – Überholmanöver, die in derselben
Runde wieder verloren gehen, sieht man nicht. Boxenstopp in Runde 1 = Start zählt nicht.
"""

from __future__ import annotations

from statistics import mean

from stintlab.analyses.positions import compute_positions
from stintlab.preview import team_name
from stintlab.race_control import neutral_laps
from stintlab.style import COLORS, style_axes, team_color

MIN_STARTS = 5


def race_starts(race: dict, order: dict[str, int] | None = None) -> list[dict]:
    """[{driver, team, grid_rank, gain}] eines Rennens; [] wenn Runde 1 neutralisiert war.
    order: {Fahrer: Position am Messpunkt} (z. B. nach der ersten Kurve) – sonst die Linie nach Runde 1.
    Fahrer ohne Wert in order fallen heraus."""
    if 1 in neutral_laps(race.get("race_control", [])):
        return []
    grid = race.get("grid", {})
    lap1 = {d: ends[1] for d, ends in race.get("lap_ends", {}).items() if 1 in ends}
    pit1 = {p["driver"] for p in race.get("pit_stops", []) if p.get("lap") == 1}
    # mit order: alle gemessenen Fahrer – auch wenn OpenF1 ihre erste Zieldurchfahrt nicht hat (Melbourne 2026)
    drivers = ([d for d in lap1 if d in grid and d not in pit1] if order is None
               else [d for d in order if d in grid and d not in pit1])
    if len(drivers) < 5:
        return []
    by_grid = sorted(drivers, key=lambda d: grid[d])
    grid_rank = {d: i for i, d in enumerate(by_grid, start=1)}
    if order is None:
        pos = compute_positions({d: {1: lap1[d]} for d in drivers})
    else:                                   # unter den gezählten Fahrern neu durchnummerieren
        ranked = sorted(drivers, key=lambda d: order[d])
        pos = {d: {1: i} for i, d in enumerate(ranked, start=1)}
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


def turn1_order(race: dict, at_frac: float | dict | None = None, refresh: bool = False) -> dict[str, int] | None:
    """Reihenfolge nach der ersten Kurve (first_corner.py) – None, wenn die Messung scheitert."""
    from stintlab.analyses import first_corner as fc
    if isinstance(at_frac, dict):          # at_frac = { Spielberg = 0.09 } – nur für einzelne Rennen
        at_frac = at_frac.get(race.get("place"))
    if 1 in neutral_laps(race.get("race_control", [])):
        return None
    lap1 = {d: ends[1] for d, ends in race.get("lap_ends", {}).items() if 1 in ends}
    grid = race.get("grid", {})
    starters = sorted((d for d in lap1 if d in grid), key=lambda d: grid[d])   # nur für den Referenzfahrer
    if not starters:
        return None
    t0 = min(lap1.values())
    try:
        tracks = fc.tracks_by_driver(fc.fetch_lap1_location(race, refresh), race["numbers"], t0)
        ref_drv = next(d for d in starters if d in tracks and 2 in race["lap_ends"].get(d, {}))
        ends = race["lap_ends"][ref_drv]
        laps = [float(l["LapTime"]) for l in race.get("laps", []) if l.get("LapTime")]
        lap_time = sorted(laps)[len(laps) // 2] if laps else 100.0
        line1 = {d: (t - t0).total_seconds() for d, t in lap1.items()}
        order, at, lines = fc.order_after_turn1(tracks, ref_drv, line1,
                                         ((ends[1] - t0).total_seconds(), (ends[2] - t0).total_seconds()),
                                         lap_time, at_frac)
    except Exception as exc:
        print(f"  ℹ Start {race.get('place')}: nach der ersten Kurve nicht messbar ({exc}) – Rennen fällt heraus")
        return None
    line = {d: {1: i} for i, d in enumerate(sorted((d for d in order if d in lines), key=lines.get), start=1)}
    same = sum(1 for d in order if d in line and line[d][1] == order[d])
    print(f"  Start {race.get('place')}: Messpunkt bei {at:.1%} der Runde · {len(order)} Fahrer · "
          f"Führender dort {min(order, key=order.get)} · {same}/{len(order)} am Ende von Runde 1 auf demselben Platz")
    return order


def starter_rows(races: list[dict], min_starts: int = MIN_STARTS, measure: str = "lap1",
                 at_frac: float | dict | None = None) -> tuple[list[dict], int]:
    """([{driver, team, score, raw, n}], Anzahl gewerteter Rennen), score absteigend.
    measure: "lap1" (Linie nach Runde 1) oder "turn1" (nach der ersten Kurve)."""
    if measure not in ("lap1", "turn1"):
        raise ValueError('measure muss "turn1" oder "lap1" sein')
    starts, counted = [], 0
    for r in races:
        if measure == "turn1":
            order = turn1_order(r, at_frac)
            s = race_starts(r, order) if order else []
        else:
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


def render_best_starters(ax, races: list[dict], top: int | None = 20, measure: str = "turn1",
                         at_frac: float | None = None) -> list[dict]:
    rows, counted = starter_rows(races, measure=measure, at_frac=at_frac)
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
    where = "after turn 1" if measure == "turn1" else "on lap 1"
    ax.set_xlabel(f"Places gained {where} per start, vs. what that grid slot usually gains")
    how = "order just after turn 1 from car positions · " if measure == "turn1" else ""
    note = ax.text(0.99, 0.01, f"{counted} races · {how}lap-1 retirements, lap-1 pit stops and SC/red flag on lap 1 left out\n"
            f"drivers with fewer than {MIN_STARTS} counted starts left out",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7.5, color=COLORS["muted"], linespacing=1.5)
    note.keep_font = True
    return rows
