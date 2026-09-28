"""Abstand zweier Fahrer ÜBER DIE RUNDE – nicht nur an der Ziellinie.

FRAGE: Wo auf der Strecke kommt der Verfolger heran, wo verliert er wieder?
gap_between zeigt nur einen Wert pro Runde (Ziellinie) und versteckt das.

METHODE (dieselbe wie im Race-Story-Reel): Zu jedem Zeitpunkt t steht A an
Punkt P. Der Abstand ist die Zeit, bis B denselben Punkt P erreicht – also
eine Zeitnahme an jedem Punkt der Strecke statt nur an drei Messstellen.
Grundlage sind die Positionsdaten (/location), ~4 Punkte pro Sekunde,
dazwischen weich interpoliert.

STRECKE (x-Achse): Weg von A seit Rundenbeginn in Metern. Die Einheit der
Positionsdaten ist nicht dokumentiert; Meter pro Einheit kommen aus der
Geschwindigkeit (car_data von A), wie beim Reel.

SEKTORGRENZEN: dort, wo A nach Sektor-1- bzw. Sektor-1+2-Zeit war (Median
über die gezeigten Runden).

VORZEICHEN: > 0 = B liegt hinter A, um so viele Sekunden.
"""

from __future__ import annotations

import numpy as np

from stintlab import openf1
from stintlab.reels.race_story import Track, live_gap, reference_lap, units_per_metre
from stintlab.style import COLORS, style_axes, team_color

BINS = 120            # Abschnitte pro Runde (~50 m in Baku)
STEP_S = 0.25         # Abstand der Messpunkte in Sekunden
MAX_GAP_S = 5.0       # größerer Abstand = kein "Hinterherfahren" mehr
MAX_MATCH_M = 40.0    # B muss P auf so viele Meter treffen


def _location(data: dict, drv: str) -> list[dict]:
    loc = data.get("location", {}).get(drv)
    if loc is None:
        loc = openf1.cached_fetch_driver("location", data["session_key"], data["numbers"][drv])
    return loc


def compute_gap_on_lap(data: dict, a: str, b: str, laps: tuple[int, int]) -> dict:
    """{"x_m": Mitte jedes Abschnitts, "per_lap": {Runde: Abstände}, "median",
        "sectors_m": [Ende S1, Ende S2], "length_m"}"""
    ends = data["lap_ends"]
    t0 = ends[a][min(ends[a])]
    ta = Track(_location(data, a), t0)
    tb = Track(_location(data, b), t0, rotate=ta.rotate)
    scale = units_per_metre(data, a, reference_lap(data, a), ta, t0)
    rows = {l["LapNumber"]: l for l in data.get("laps", []) if l["Driver"] == a}

    per_lap, lengths, sector_fracs = {}, [], []
    edges = np.linspace(0.0, 1.0, BINS + 1)
    for lap in range(laps[0], laps[1] + 1):
        if lap not in ends[a] or lap - 1 not in ends[a]:
            continue
        start, end = (ends[a][lap - 1] - t0).total_seconds(), (ends[a][lap] - t0).total_seconds()
        ts = np.arange(start, end, STEP_S)
        x, y = ta.at(ts)
        path = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
        if path[-1] <= 0:
            continue
        frac = path / path[-1]
        gaps = np.array([live_gap(ta, tb, t, MAX_GAP_S, MAX_MATCH_M * scale) for t in ts])
        idx = np.clip(np.digitize(frac, edges) - 1, 0, BINS - 1)
        per_lap[lap] = np.array([np.nanmean(gaps[idx == k]) if np.any((idx == k) & ~np.isnan(gaps))
                                 else np.nan for k in range(BINS)])
        lengths.append(path[-1] / scale)
        row = rows.get(lap, {})
        if row.get("Sector1") and row.get("Sector2"):
            fr = []
            for s in (row["Sector1"], row["Sector1"] + row["Sector2"]):
                fr.append(float(np.interp(start + s, ts, frac)))
            sector_fracs.append(fr)
    if not per_lap:
        raise ValueError(f"Keine gemeinsamen Runden für {a}/{b} in {laps}")

    length = float(np.median(lengths))
    stack = np.array(list(per_lap.values()))
    with np.errstate(all="ignore"):
        med = np.nanmedian(stack, axis=0)
    sectors = [float(v) * length for v in np.median(sector_fracs, axis=0)] if sector_fracs else []
    return {"x_m": (edges[:-1] + edges[1:]) / 2 * length, "per_lap": per_lap, "median": med,
            "sectors_m": sectors, "length_m": length}


def render_gap_on_lap(ax, data: dict, a: str, b: str, laps: tuple[int, int]) -> dict:
    res = compute_gap_on_lap(data, a, b, laps)
    teams = data.get("teams", {})
    color = team_color(teams.get(b))
    x_km = res["x_m"] / 1000
    style_axes(ax, grid_axis="y")

    for g in res["per_lap"].values():
        ax.plot(x_km, g, color=color, alpha=0.22, linewidth=0.9)
    med = res["median"]
    ax.plot(x_km, med, color=COLORS["text"], linewidth=2.2, label=f"Median laps {laps[0]}–{laps[1]}")

    top = float(np.nanmax(np.array(list(res["per_lap"].values())))) * 1.12
    ax.set_ylim(0, top)
    for i, s in enumerate(res["sectors_m"]):
        ax.axvline(s / 1000, color=COLORS["muted"], linewidth=0.8, linestyle="--")
    bounds = [0.0] + [s / 1000 for s in res["sectors_m"]] + [res["length_m"] / 1000]
    if len(bounds) == 4:
        for i in range(3):
            ax.text((bounds[i] + bounds[i + 1]) / 2, top * 0.97, f"S{i + 1}", ha="center", va="top",
                    fontsize=9, color=COLORS["muted"], fontweight="bold")

    lo, hi = int(np.nanargmin(med)), int(np.nanargmax(med))
    for k, va, off in ((lo, "top", -10), (hi, "bottom", 8)):
        ax.scatter([x_km[k]], [med[k]], s=40, color=COLORS["text"], zorder=5)
        ax.annotate(f"{med[k]:.2f} s", (x_km[k], med[k]), xytext=(0, off), textcoords="offset points",
                    ha="center", va=va, fontsize=9, color=COLORS["text"], fontweight="bold")

    ax.set_xlim(0, res["length_m"] / 1000)
    ax.set_xlabel(f"Distance along the lap (km) · start/finish line at 0")
    ax.set_ylabel(f"{b} behind {a} (s)")
    ax.legend(loc="lower left", fontsize=8.5)
    ax.text(0.99, 0.02, f"thin lines = single laps · gap measured at every point, not just the line",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7.5, color=COLORS["muted"])
    return res
