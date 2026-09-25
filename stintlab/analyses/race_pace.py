"""Rennpace: Wer war im Rennen wirklich schnell – Fahrer und Teams.

SAUBERE RUNDEN – es zählen nur Runden, die das Tempo zeigen:
- nicht Runde 1 (Start im Pulk)
- keine In- und Out-Laps (Boxenstopps)
- keine Runde, die sich zeitlich mit SC, VSC oder roter Flagge überschneidet.
  Die Phasen kommen aus restricted_laps() (dieselbe Logik wie im Madrid-Post)
  und gelten für die Runden des FÜHRENDEN. Sie werden über deren Start- und
  Endzeit in Zeitfenster umgerechnet – so werden auch überrundete Fahrer
  richtig behandelt, deren Rundennummern andere sind.
- keine Ausreißer über 107 % der eigenen besten sauberen Runde (Dreher,
  Verkehr beim Überrunden, langsamer Stopp)

GRENZEN: Strategie (ein oder zwei Stopps, Mischungen) und Verkehr beeinflussen
die Werte. Wer lange hinter einem langsameren Auto hing, sieht langsamer aus,
als sein Auto war. Das gehört in den Untertitel.
"""

from __future__ import annotations

from datetime import timedelta
from statistics import median

from stintlab.analyses.long_runs import _fmt
from stintlab.race_control import restricted_laps
from stintlab.style import COLORS, style_axes, team_color

MIN_CLEAN_LAPS = 10
OUTLIER = 1.07
# Kurze Teamnamen, damit die Beschriftung links nicht abgeschnitten wird
SHORT_TEAM = {"Red Bull Racing": "Red Bull", "Haas F1 Team": "Haas", "Racing Bulls": "RB",
              "Aston Martin": "Aston Martin", "Kick Sauber": "Sauber"}


def _lap_window(lap: dict, ends: dict) -> tuple | None:
    start = lap.get("LapStart")
    if start is None:
        return None
    end = ends.get(lap["LapNumber"])
    if end is None and lap.get("LapTime"):
        end = start + timedelta(seconds=float(lap["LapTime"]))
    return (start, end) if end else None


def restricted_windows(data: dict) -> list[tuple]:
    """Zeitfenster [(Start, Ende)] der neutralisierten Runden des Führenden."""
    laps = data.get("laps", [])
    if not laps:
        return []
    leader = max(laps, key=lambda l: l.get("LapNumber") or 0)["Driver"]
    numbers = restricted_laps(data.get("race_control", []))
    ends = data.get("lap_ends", {}).get(leader, {})
    windows = []
    for lap in laps:
        if lap["Driver"] == leader and lap.get("LapNumber") in numbers:
            w = _lap_window(lap, ends)
            if w:
                windows.append(w)
    return windows


def clean_laps(data: dict) -> tuple[dict[str, list[float]], dict[str, int]]:
    """({Fahrer: [saubere Rundenzeiten]}, {Ausschlussgrund: Anzahl})."""
    windows = restricted_windows(data)
    pit_laps = {(p["driver"], p["lap"]) for p in data.get("pit_stops", []) if p.get("lap")}
    stats = {"total": 0, "lap 1": 0, "pit": 0, "SC/VSC/red": 0, "outlier": 0}
    candidates: dict[str, list[float]] = {}
    for lap in data.get("laps", []):
        if not lap.get("LapTime") or lap.get("LapNumber") is None:
            continue
        stats["total"] += 1
        drv, num = lap["Driver"], lap["LapNumber"]
        if num == 1:
            stats["lap 1"] += 1
            continue
        if lap.get("IsPitOutLap") or (drv, num) in pit_laps:
            stats["pit"] += 1
            continue
        w = _lap_window(lap, data.get("lap_ends", {}).get(drv, {}))
        if w and any(w[0] < end and start < w[1] for start, end in windows):
            stats["SC/VSC/red"] += 1
            continue
        candidates.setdefault(drv, []).append(float(lap["LapTime"]))

    clean = {}
    for drv, times in candidates.items():
        limit = min(times) * OUTLIER
        kept = [t for t in times if t <= limit]
        stats["outlier"] += len(times) - len(kept)
        clean[drv] = kept
    return clean, stats


def _report(stats: dict, clean: dict) -> None:
    kept = sum(len(v) for v in clean.values())
    parts = ", ".join(f"{k} {v}" for k, v in stats.items() if k != "total" and v)
    print(f"  Rennpace: {kept} von {stats['total']} Runden sauber ({parts})")


def _lap_axis(ax) -> None:
    ax.xaxis.set_major_formatter(lambda x, _: _fmt(x))


def render_driver_pace(ax, data: dict, min_laps: int = MIN_CLEAN_LAPS) -> list[tuple[str, float]]:
    clean, stats = clean_laps(data)
    _report(stats, clean)
    rows = sorted(((d, t) for d, t in clean.items() if len(t) >= min_laps), key=lambda x: median(x[1]))
    if not rows:
        raise ValueError(f"Kein Fahrer mit mindestens {min_laps} sauberen Runden")
    too_few = sorted(d for d, t in clean.items() if len(t) < min_laps)
    teams = data.get("teams", {})
    colors = [team_color(teams.get(d)) for d, _ in rows]

    style_axes(ax, grid_axis="x")
    y = list(range(len(rows)))
    box = ax.boxplot([t for _, t in rows], positions=y, vert=False, widths=0.6, showfliers=False,
                     patch_artist=True, medianprops={"color": COLORS["text"], "linewidth": 1.4},
                     whiskerprops={"color": COLORS["muted"]}, capprops={"color": COLORS["muted"]})
    for patch, c in zip(box["boxes"], colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.85)
        patch.set_edgecolor(c)
    ax.invert_yaxis()
    ax.set_yticks(y)
    ax.set_yticklabels([d for d, _ in rows], fontsize=9, fontweight="bold")
    for tick, c in zip(ax.get_yticklabels(), colors):
        tick.set_color(c)

    best = median(rows[0][1])
    right = max(max(t) for _, t in rows)
    for i, (d, t) in enumerate(rows):
        m = median(t)
        label = _fmt(m) if i == 0 else f"+{m - best:.3f}"
        ax.text(right, i, f"  {label}  ·  {len(t)} laps", va="center", fontsize=7.5, color=COLORS["text"])
    lo = min(min(t) for _, t in rows)
    ax.set_xlim(lo - 0.3, right + (right - lo) * 0.45)
    _lap_axis(ax)
    ax.set_xlabel("Clean race laps (box = middle 50 %, line = median)")

    notes = ["Excluded: lap 1, pit laps, SC/VSC/red flag, laps over 107 % of own best"]
    if too_few:
        notes.insert(0, f"Fewer than {min_laps} clean laps: " + ", ".join(too_few))
    ax.set_ylim(len(rows) - 0.5 + 0.55 * len(notes) + 0.3, -0.6)
    ax.text(0.99, 0.02, "\n".join(notes), transform=ax.transAxes, ha="right", va="bottom",
            fontsize=7.5, color=COLORS["muted"], linespacing=1.5)
    return [(d, median(t)) for d, t in rows]


def render_team_pace(ax, data: dict, min_laps: int = MIN_CLEAN_LAPS) -> list[tuple[str, float]]:
    clean, stats = clean_laps(data)
    _report(stats, clean)
    teams = data.get("teams", {})
    by_team: dict[str, list[float]] = {}
    counted: dict[str, list[str]] = {}          # Fahrer mit genug sauberen Runden
    for drv, times in clean.items():
        team = teams.get(drv) or drv
        by_team.setdefault(team, []).extend(times)
        if len(times) >= min_laps:
            counted.setdefault(team, []).append(drv)
    rows = sorted(((t, median(v), len(v)) for t, v in by_team.items() if len(v) >= min_laps),
                  key=lambda x: x[1])
    if not rows:
        raise ValueError(f"Kein Team mit mindestens {min_laps} sauberen Runden")
    best = rows[0][1]
    colors = [team_color(t) for t, _, _ in rows]

    # Platz für Teamnamen wie "Aston Martin": Diagramm etwas nach rechts
    x0, y0, w0, h0 = ax.get_position().bounds
    ax.set_position([x0 + 0.05, y0, w0 - 0.05, h0])
    style_axes(ax, grid_axis="x")
    y = list(range(len(rows)))
    gaps = [m - best for _, m, _ in rows]
    ax.barh(y, gaps, height=0.62, color=colors, alpha=0.9)
    ax.invert_yaxis()
    ax.set_yticks(y)
    ax.set_yticklabels([SHORT_TEAM.get(t, t) for t, _, _ in rows], fontsize=9, fontweight="bold")
    for tick, c in zip(ax.get_yticklabels(), colors):
        tick.set_color(c)
    right = max(gaps) if max(gaps) > 0 else 1.0
    for i, ((t, m, n), g) in enumerate(zip(rows, gaps)):
        label = _fmt(m) if i == 0 else f"+{g:.3f} s"
        label += f"  ·  {n} laps"
        if len(counted.get(t, [])) == 1:
            # Teamwert kommt im Wesentlichen von einem Fahrer – sagen, von wem
            label += f"  ·  {counted[t][0]} only"
        ax.text(g + right * 0.02, i, label, va="center", fontsize=8, color=COLORS["text"])
    ax.set_xlim(-right * 0.02, right * 1.45)
    ax.set_xlabel("Median of both drivers' clean race laps, gap to fastest team (s)")
    ax.text(0.99, 0.02, "Excluded: lap 1, pit laps, SC/VSC/red flag, laps over 107 % of own best",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7.5, color=COLORS["muted"])
    ax.set_ylim(len(rows) - 0.5 + 0.9, -0.6)
    return [(t, m) for t, m, _ in rows]
