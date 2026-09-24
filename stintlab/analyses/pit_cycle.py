"""Zerlegt, wie sich der Abstand zweier Fahrer über einen Boxenstopp-Zyklus ändert.

Wasserfall aus vier Balken, aus Sicht von driver_a (positiv = driver_a vorne):

  1. Abstand vor dem Zyklus         gemessen (Zieldurchfahrt, Runde "before")
  2. Unterschied der Boxendurchfahrt gemessen (pit_duration beider Fahrer)
  3. Rest des Zyklus                BERECHNET als Differenz – enthält alles,
                                    was nicht die Boxendurchfahrt ist: Zeitpunkt
                                    der Stopps (z. B. unter VSC), In- und Out-Lap
  4. Abstand nach dem Zyklus        gemessen (Zieldurchfahrt, Runde "after")

Balken 3 ist ausdrücklich kein direkt gemessener VSC-Effekt, sondern ein Rest.
So ist er auch beschriftet.
"""

from __future__ import annotations

from stintlab.analyses.gap_between import compute_gap_between
from stintlab.style import COLORS, style_axes, team_color


def compute_pit_cycle(data: dict, driver_a: str, driver_b: str,
                      before: int, after: int) -> dict[str, float]:
    """Zahlen für den Wasserfall. Alle Werte aus Sicht von driver_a."""
    gaps = compute_gap_between(data["lap_ends"], driver_a, driver_b)
    for lap in (before, after):
        if lap not in gaps:
            raise ValueError(f"Kein Abstand {driver_a}/{driver_b} für Runde {lap}")

    def stop(driver: str) -> float:
        stops = [p for p in data["pit_stops"]
                 if p["driver"] == driver and before < p["lap"] <= after and p.get("duration")]
        if len(stops) != 1:
            raise ValueError(f"{driver} braucht genau einen Stopp zwischen Runde {before} "
                             f"und {after}, gefunden: {len(stops)}")
        return float(stops[0]["duration"])

    start, end = gaps[before], gaps[after]
    # Längere Durchfahrt von b = Zeitgewinn für a
    stop_diff = stop(driver_b) - stop(driver_a)
    return {
        "start": start,
        "stop_diff": stop_diff,
        "rest": (end - start) - stop_diff,
        "end": end,
    }


def render_pit_cycle(ax, data: dict, driver_a: str, driver_b: str,
                     before: int, after: int) -> dict[str, float]:
    v = compute_pit_cycle(data, driver_a, driver_b, before, after)
    teams = data.get("teams", {})
    color_a = team_color(teams.get(driver_a))
    color_b = team_color(teams.get(driver_b))

    def color(value: float) -> str:
        return color_a if value >= 0 else color_b

    style_axes(ax, grid_axis="y")

    # (Beschriftung, Balkenanfang, Balkenende)
    after_stop = v["start"] + v["stop_diff"]
    bars = [
        (f"Gap after\nlap {before}", 0.0, v["start"]),
        (f"Pit lane time\n{driver_b} vs {driver_a}", v["start"], after_stop),
        ("Rest of pit cycle\n(stop timing, VSC,\nin-/out-laps)", after_stop, v["end"]),
        (f"Gap after\nlap {after}", 0.0, v["end"]),
    ]

    for i, (label, low, high) in enumerate(bars):
        is_total = i in (0, 3)
        value = high - low
        ax.bar(i, value, bottom=low, width=0.6, color=color(high if is_total else value),
               alpha=0.9 if is_total else 0.6, edgecolor=COLORS["bg"], linewidth=1)
        shown = high if is_total else value
        # Positive Werte über dem Balken, negative darunter
        above = shown >= 0
        ax.annotate(f"{shown:+.1f} s", (i, max(low, high) if above else min(low, high)),
                    xytext=(0, 6 if above else -6), textcoords="offset points",
                    ha="center", va="bottom" if above else "top",
                    fontsize=10, fontweight="bold", color=COLORS["text"])
        # Verbindungslinie zum nächsten Balken
        if i < len(bars) - 1:
            ax.plot([i + 0.3, i + 0.7], [high, high], color=COLORS["muted"],
                    linewidth=0.8, linestyle="--")

    ax.axhline(0, color=COLORS["muted"], linewidth=0.8)
    ax.set_xticks(range(len(bars)))
    ax.set_xticklabels([b[0] for b in bars], fontsize=8.5, color=COLORS["muted"])
    ax.tick_params(axis="x", length=0)

    top = max(0.0, *(b[2] for b in bars), *(b[1] for b in bars))
    bottom = min(0.0, *(b[2] for b in bars), *(b[1] for b in bars))
    pad = (top - bottom) * 0.15
    ax.set_ylim(bottom - pad, top + pad)
    ax.set_ylabel(f"Gap {driver_a} ↔ {driver_b} (s) · + = {driver_a} ahead")

    return v