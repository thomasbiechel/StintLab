"""Abstand zwischen zwei Fahrern, Runde für Runde.

METHODE: Der Abstand nach Runde N ist die Zeitdifferenz, mit der beide Fahrer
die Ziellinie am Ende von Runde N überqueren. Das ist genau der Abstand, den
eine Zeitnahme an der Linie messen würde.

Bewusst NICHT verwendet: die Differenz zweier "Gap to Leader"-Werte. Die
werden für jeden Fahrer zu einem eigenen Zeitpunkt abgelesen. Wechselt
dazwischen der Führende (z. B. weil er an die Box fährt), beziehen sich die
beiden Werte auf verschiedene Führende, und die Differenz ist falsch.

VORZEICHEN (fest):
    gap > 0  →  driver_a liegt VOR driver_b, um gap Sekunden
    gap < 0  →  driver_a liegt HINTER driver_b
"""

from __future__ import annotations

from datetime import datetime

from stintlab.race_control import restricted_laps
from stintlab.style import COLORS, style_axes, team_color


def compute_gap_between(lap_ends: dict[str, dict[int, datetime]],
                        driver_a: str, driver_b: str) -> dict[int, float]:
    """{Runde: Abstand in Sekunden} aus den Zeitpunkten der Zieldurchfahrt.

    Wer die Linie früher überquert, liegt vorne:
        gap = Durchfahrt_b - Durchfahrt_a
    Runden, die einer der beiden nicht beendet hat, werden ausgelassen.
    """
    a, b = lap_ends.get(driver_a, {}), lap_ends.get(driver_b, {})
    return {lap: (b[lap] - a[lap]).total_seconds() for lap in sorted(set(a) & set(b))}


def render_gap_between(ax, data: dict, driver_a: str, driver_b: str,
                       laps: tuple[int, int] | None = None) -> dict[int, float]:
    """Zeichnet den Abstand driver_a ↔ driver_b auf ax. Gibt die Werte zurück.

    laps: optionales Fenster (erste, letzte Runde), z. B. (15, 48), um eine
          Phase des Rennens herauszuzoomen.

    Erwartet in data (siehe stintlab.session):
      "lap_ends", "race_control", "pit_stops", "teams"
    """
    gaps = compute_gap_between(data.get("lap_ends", {}), driver_a, driver_b)
    if laps:
        first, last = laps
        gaps = {n: g for n, g in gaps.items() if first <= n <= last}
    if len(gaps) < 3:
        raise ValueError(f"Zu wenige gemeinsame Runden für {driver_a} und {driver_b}")

    teams = data.get("teams", {})
    color_a = team_color(teams.get(driver_a))
    color_b = team_color(teams.get(driver_b))

    style_axes(ax, grid_axis="y")

    # Neutralisierte Runden grau hinterlegen
    for lap in sorted(restricted_laps(data.get("race_control", []))):
        if lap not in gaps:
            continue
        ax.axvspan(lap - 0.5, lap + 0.5, color=COLORS["muted"], alpha=0.15, linewidth=0)

    laps = list(gaps)
    values = list(gaps.values())

    # Fläche in der Farbe dessen, der gerade vorne liegt
    ax.fill_between(laps, values, 0, where=[v >= 0 for v in values],
                    color=color_a, alpha=0.25, interpolate=True, linewidth=0)
    ax.fill_between(laps, values, 0, where=[v < 0 for v in values],
                    color=color_b, alpha=0.25, interpolate=True, linewidth=0)
    ax.plot(laps, values, color=COLORS["text"], linewidth=1.4)
    ax.axhline(0, color=COLORS["muted"], linewidth=0.8)

    # Boxenstopps: Beschriftung von driver_a nach links, von driver_b nach
    # rechts, damit sie sich bei nahen Stopps nicht überlagern
    for stop in data.get("pit_stops", []):
        drv, lap = stop.get("driver"), stop.get("lap")
        if drv in (driver_a, driver_b) and lap in gaps:
            is_a = drv == driver_a
            color = color_a if is_a else color_b
            ax.scatter([lap], [gaps[lap]], s=45, color=color, zorder=5,
                       edgecolor=COLORS["bg"], linewidth=1)
            label = f"{drv} pit"
            if stop.get("duration"):
                label += f" · {stop['duration']:.1f} s"
            ax.annotate(label, (lap, gaps[lap]), xytext=(-8 if is_a else 8, 0),
                        textcoords="offset points", ha="right" if is_a else "left",
                        va="center", fontsize=8, color=color, fontweight="bold")

    # y-Achse: symmetrisch, wenn die Führung wechselt – sonst nur die Seite,
    # auf der die Werte liegen, damit keine halbe Grafik leer bleibt
    limit = max(abs(v) for v in values) * 1.25
    margin = limit * 0.12  # etwas Platz für die Beschriftung auf der leeren Seite
    if min(values) >= 0:
        ax.set_ylim(-margin, limit)
    elif max(values) <= 0:
        ax.set_ylim(-limit, margin)
    else:
        ax.set_ylim(-limit, limit)

    if max(values) > 0:
        ax.text(0.01, 0.97, f"▲ {driver_a} ahead", transform=ax.transAxes,
                color=color_a, fontsize=9, fontweight="bold", va="top")
    if min(values) < 0:
        ax.text(0.01, 0.03, f"▼ {driver_b} ahead", transform=ax.transAxes,
                color=color_b, fontsize=9, fontweight="bold", va="bottom")
    ax.set_xlabel("Lap")
    ax.set_ylabel(f"Gap {driver_a} ↔ {driver_b} (s)")

    return gaps