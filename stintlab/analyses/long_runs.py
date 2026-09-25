"""Long-Run-Pace im freien Training.

ERKENNUNG eines Long Runs, pro Fahrer:
  1. Gültige Runden: mit Zeit, keine Out-Lap, keine In-Lap (Runde vor einer
     Out-Lap oder mit Boxenstopp), nicht unter SC/VSC/roter Flagge.
  2. Aufeinanderfolgende gültige Runden bilden einen Run.
  3. Runden über 107 % der besten Runde des Fahrers werden am Anfang und
     Ende des Runs abgeschnitten (Aufwärmen, Abkühlen, rote Flagge – im
     Training haben Race-Control-Meldungen keine Rundennummer, rote Flaggen
     lassen sich also nicht über Runden sperren).
  4. Solche langsamen Runden in der Mitte (Verkehr) werden entfernt, aber
     höchstens ein Drittel des Runs. Eine Quali-Simulation (schnell – langsam
     – schnell …) hat die Hälfte langsamer Runden und fällt dadurch heraus.
  5. Ein Long Run liegt vor, wenn danach mindestens 80 % der Runden innerhalb
     von 2 % um den Median liegen. Runden außerhalb werden entfernt.
     Übrig bleiben müssen mindestens min_laps Runden.
Pro Fahrer wird der längste Long Run gezeigt.

KENNZAHLEN: Median-Rundenzeit und Abbau pro Runde (Steigung einer Geraden
durch die Rundenzeiten). Der Abbau ist NICHT spritkorrigiert: Das Auto wird
mit jeder Runde leichter, der echte Reifenabbau ist also größer.

GRENZEN: Spritmenge und Motor-Modus der Teams sind unbekannt. Die Rangliste
zeigt eine Tendenz, keine Vorhersage fürs Rennen.
"""

from __future__ import annotations

import numpy as np

from stintlab.race_control import restricted_laps
from stintlab.style import COLORS, style_axes, team_color

COMPOUND_COLORS = {
    "SOFT": "#e8002d", "MEDIUM": "#ffd700", "HARD": "#f0f0f0",
    "INTERMEDIATE": "#39b54a", "WET": "#0067ff",
}
BAND = 0.02              # ±2 % um den Median des Runs
MIN_SHARE = 0.8          # so viele Runden müssen im Band liegen
SLOW = 1.07              # langsamer als 107 % der besten Runde = keine Push-Runde
MAX_INTERIOR_SLOW = 1/3  # höchstens so viele langsame Runden mitten im Run


def _compound(stints: list[dict], driver: str, lap: int) -> str:
    for st in stints:
        if st["driver"] == driver and st.get("lap_start") and st.get("lap_end") \
                and st["lap_start"] <= lap <= st["lap_end"]:
            return st["compound"]
    return "UNKNOWN"


def _valid_segments(data: dict) -> dict[str, list[list[tuple[int, float]]]]:
    """{Fahrer: [Run, ...]} – Runs aus aufeinanderfolgenden gültigen Runden."""
    restricted = restricted_laps(data.get("race_control", []))
    pit_laps = {(p["driver"], p["lap"]) for p in data.get("pit_stops", [])}

    by_driver: dict[str, dict[int, dict]] = {}
    for lap in data.get("laps", []):
        if lap.get("LapNumber") is not None:
            by_driver.setdefault(lap["Driver"], {})[lap["LapNumber"]] = lap

    result: dict[str, list[list[tuple[int, float]]]] = {}
    for drv, laps in by_driver.items():
        valid = []
        for num in sorted(laps):
            lap = laps[num]
            next_lap = laps.get(num + 1, {})
            is_in_lap = bool(next_lap.get("IsPitOutLap")) or (drv, num) in pit_laps
            if lap.get("LapTime") and not lap.get("IsPitOutLap") and not is_in_lap \
                    and num not in restricted:
                valid.append((num, float(lap["LapTime"])))

        segments: list[list[tuple[int, float]]] = []
        for num, t in valid:
            if segments and num == segments[-1][-1][0] + 1:
                segments[-1].append((num, t))
            else:
                segments.append([(num, t)])
        result[drv] = segments
    return result


def _evaluate(seg: list[tuple[int, float]], best: float,
              min_laps: int) -> tuple[list[tuple[int, float]] | None, str]:
    """Prüft einen Run nach den Schritten 3–5. Gibt (Runden, Grund) zurück;
    Runden ist None, wenn es kein Long Run ist."""
    limit = best * SLOW
    # 3. langsame Runden am Anfang und Ende abschneiden
    while seg and seg[0][1] > limit:
        seg = seg[1:]
    while seg and seg[-1][1] > limit:
        seg = seg[:-1]
    if len(seg) < min_laps:
        return None, "zu kurz"
    # 4. langsame Runden in der Mitte
    fast = [(n, t) for n, t in seg if t <= limit]
    if len(seg) - len(fast) > MAX_INTERIOR_SLOW * len(seg):
        return None, "zu viele langsame Runden (Quali-Simulation?)"
    # 5. Gleichmäßigkeit
    median = float(np.median([t for _, t in fast]))
    in_band = [(n, t) for n, t in fast if abs(t - median) <= median * BAND]
    if len(in_band) < MIN_SHARE * len(fast):
        return None, "zu ungleichmäßig"
    if len(in_band) < min_laps:
        return None, "zu kurz"
    return in_band, "OK"


def find_long_runs(data: dict, min_laps: int = 5) -> list[dict]:
    """Alle Long Runs der Session, siehe Modul-Docstring."""
    runs = []
    for drv, segments in _valid_segments(data).items():
        all_times = [t for seg in segments for _, t in seg]
        if not all_times:
            continue
        best = min(all_times)
        for seg in segments:
            kept, _ = _evaluate(seg, best, min_laps)
            if kept is None:
                continue
            nums = [n for n, _ in kept]
            times = [t for _, t in kept]
            slope = float(np.polyfit(nums, times, 1)[0]) if len(nums) >= 3 else 0.0
            runs.append({
                "driver": drv,
                "compound": _compound(data.get("stints", []), drv, nums[0]),
                "laps": nums,
                "median": float(np.median(times)),
                "deg_per_lap": slope,
            })
    return runs


def diagnose(data: dict, min_laps: int = 5) -> list[str]:
    """Erklärt pro Fahrer, warum (k)ein Long Run gefunden wurde – zur Fehlersuche."""
    lines = []
    for drv, segments in sorted(_valid_segments(data).items()):
        if not segments:
            lines.append(f"{drv}: keine gültige Runde")
            continue
        best = min(t for seg in segments for _, t in seg)
        results = [(seg, *_evaluate(seg, best, min_laps)) for seg in segments]
        ok = [r for r in results if r[1] is not None]
        seg, kept, reason = max(ok, key=lambda r: len(r[1])) if ok else max(results, key=lambda r: len(r[0]))
        times = ", ".join(f"{t:.1f}" for _, t in seg)
        used = f", {len(kept)} Runden verwendet" if kept else ""
        lines.append(f"{drv}: Run Runde {seg[0][0]}–{seg[-1][0]} → {reason}{used}  [{times}]")
    return lines


def best_run_per_driver(runs: list[dict], compound: str | None = None) -> list[dict]:
    """Längster Long Run pro Fahrer, sortiert nach Median (schnellster zuerst)."""
    best: dict[str, dict] = {}
    for run in runs:
        if compound and run["compound"] != compound.upper():
            continue
        current = best.get(run["driver"])
        if current is None or len(run["laps"]) > len(current["laps"]):
            best[run["driver"]] = run
    return sorted(best.values(), key=lambda r: r["median"])


def _fmt(seconds: float) -> str:
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}:{rest:06.3f}"


def render_long_runs(ax, data: dict, drivers: list[str] | None = None,
                     compound: str | None = None, min_laps: int = 5) -> list[dict]:
    runs = best_run_per_driver(find_long_runs(data, min_laps), compound)
    if drivers:
        runs = [r for r in runs if r["driver"] in drivers]
    if not runs:
        raise ValueError("Keine Long Runs gefunden – min_laps verringern oder compound prüfen")

    teams = data.get("teams", {})
    fastest = runs[0]["median"]
    deltas = [r["median"] - fastest for r in runs]

    style_axes(ax, grid_axis="x")
    y = list(range(len(runs)))
    ax.barh(y, deltas, height=0.62,
            color=[team_color(teams.get(r["driver"])) for r in runs], alpha=0.9)
    ax.invert_yaxis()  # schnellster oben

    ax.set_yticks(y)
    ax.set_yticklabels([r["driver"] for r in runs], fontsize=9, fontweight="bold")
    for tick, r in zip(ax.get_yticklabels(), runs):
        tick.set_color(team_color(teams.get(r["driver"])))

    right = max(deltas) if max(deltas) > 0 else 1.0
    for i, (r, d) in enumerate(zip(runs, deltas)):
        ax.scatter([-right * 0.06], [i], s=55, color=COMPOUND_COLORS.get(r["compound"], COLORS["muted"]),
                   edgecolor=COLORS["bg"], linewidth=1, zorder=5, clip_on=False)
        label = f"{_fmt(r['median'])}" if d == 0 else f"+{d:.2f} s"
        ax.text(d + right * 0.02, i, f"{label}  ·  {len(r['laps'])} laps  ·  {r['deg_per_lap']:+.2f} s/lap",
                va="center", fontsize=8, color=COLORS["text"])

    ax.set_xlim(-right * 0.1, right * 1.75)
    ax.set_xlabel(f"Median long-run lap time, gap to fastest (s)")
    ax.text(0.99, 0.02, "● tyre compound · s/lap = trend, not fuel-corrected",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7.5, color=COLORS["muted"])
    return runs