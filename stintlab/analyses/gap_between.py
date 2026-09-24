"""Abstand zwischen zwei Fahrern, Runde für Runde.

Beantwortet Fragen wie: "Wie knapp war es vor dem Stopp, und was hat das
VSC am Abstand verändert?"

Zwei getrennte Teile:
- compute_gap_between(): reine Rechnung, ohne Matplotlib – dadurch testbar.
- render_gap_between(): zeichnet das Ergebnis auf eine Achse.

VORZEICHEN (fest, nicht verhandelbar):
    gap > 0  →  driver_a liegt VOR driver_b, um gap Sekunden
    gap < 0  →  driver_a liegt HINTER driver_b
"""

from __future__ import annotations

from stintlab.race_control import restricted_laps
from stintlab.style import COLORS, style_axes, team_color


def compute_gap_between(gap_to_leader: list[dict], driver_a: str, driver_b: str) -> dict[int, float]:
    """{Runde: Abstand} zwischen zwei Fahrern aus den Gap-to-Leader-Daten.

    gap_to_leader: Einträge wie {"Driver": "NOR", "LapNumber": 12, "Gap": 1.4}
    Gap = Rückstand auf den Führenden in Sekunden (Führender = 0).

    Wer weniger Rückstand auf den Führenden hat, liegt vorne. Daher:
        gap = Rückstand_b - Rückstand_a
    Runden, in denen einer der beiden keinen Wert hat, werden ausgelassen.
    """
    by_driver: dict[str, dict[int, float]] = {driver_a: {}, driver_b: {}}
    for row in gap_to_leader:
        drv = row.get("Driver")
        if drv in by_driver and row.get("Gap") is not None:
            by_driver[drv][row["LapNumber"]] = float(row["Gap"])

    common_laps = sorted(set(by_driver[driver_a]) & set(by_driver[driver_b]))
    return {lap: by_driver[driver_b][lap] - by_driver[driver_a][lap] for lap in common_laps}


def render_gap_between(ax, data: dict, driver_a: str, driver_b: str) -> dict[int, float]:
    """Zeichnet den Abstand driver_a ↔ driver_b auf ax. Gibt die Werte zurück.

    Erwartet in data:
      "gap_to_leader": siehe compute_gap_between
      "race_control":  siehe stintlab.race_control
      "pit_stops":     Einträge wie {"driver": "NOR", "lap": 23}
      "teams":         {"NOR": "McLaren", "ANT": "Mercedes"}  (optional –
                       sonst aus data["laps_valid"] gelesen, wie im Analyser)
    """
    gaps = compute_gap_between(data.get("gap_to_leader", []), driver_a, driver_b)
    if len(gaps) < 3:
        raise ValueError(f"Zu wenige gemeinsame Runden für {driver_a} und {driver_b}")

    teams = data.get("teams") or {
        lap["Driver"]: lap["Team"] for lap in data.get("laps_valid", []) if lap.get("Team")
    }
    color_a = team_color(teams.get(driver_a))
    color_b = team_color(teams.get(driver_b))

    style_axes(ax, grid_axis="y")

    # Neutralisierte Runden grau hinterlegen – der Abstand schrumpft dort,
    # ohne dass jemand schneller fährt
    for lap in sorted(restricted_laps(data.get("race_control", []))):
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

    # Boxenstopps der beiden Fahrer markieren
    for stop in data.get("pit_stops", []):
        drv, lap = stop.get("driver"), stop.get("lap")
        if drv in (driver_a, driver_b) and lap in gaps:
            color = color_a if drv == driver_a else color_b
            ax.scatter([lap], [gaps[lap]], s=45, color=color, zorder=5,
                       edgecolor=COLORS["bg"], linewidth=1)
            ax.annotate(f"{drv} pit", (lap, gaps[lap]), xytext=(0, 10),
                        textcoords="offset points", ha="center",
                        fontsize=8, color=color, fontweight="bold")

    # Symmetrische y-Achse, damit "vorne" und "hinten" gleich viel Platz haben
    limit = max(abs(v) for v in values) * 1.25
    ax.set_ylim(-limit, limit)

    # Beschriftung macht das Vorzeichen unmissverständlich
    ax.text(0.01, 0.97, f"▲ {driver_a} ahead", transform=ax.transAxes,
            color=color_a, fontsize=9, fontweight="bold", va="top")
    ax.text(0.01, 0.03, f"▼ {driver_b} ahead", transform=ax.transAxes,
            color=color_b, fontsize=9, fontweight="bold", va="bottom")
    ax.set_xlabel("Lap")
    ax.set_ylabel(f"Gap {driver_a} ↔ {driver_b} (s)")

    return gaps