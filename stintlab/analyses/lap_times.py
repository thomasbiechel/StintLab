"""Rundenzeiten mehrerer Fahrer im Vergleich.

Bereinigung (sonst verzerren Ausreißer die Achse und den Vergleich):
  - Out-Laps (Runde aus der Box) und In-Laps (Runde des Boxenstopps)
  - Runden unter SC, VSC oder roter Flagge
  - Runden ohne Zeit
  - Runden langsamer als 107 % der schnellsten gezeigten Runde

Darstellung: einzelne Runden als blasse Punkte, darüber der gleitende Median
über 3 Runden als Linie. Der Median glättet einzelne Ausreißer (Verkehr,
Verbremser), ohne echte Trends über mehrere Runden zu verwischen.

Die y-Achse ist umgedreht: schneller = weiter oben.
"""

from __future__ import annotations

import numpy as np

from stintlab.race_control import restricted_laps
from stintlab.style import COLORS, style_axes, team_color


def clean_lap_times(data: dict, drivers: list[str],
                    laps: tuple[int, int] | None = None) -> dict[str, dict[int, float]]:
    """{Fahrer: {Runde: Rundenzeit}} nach der Bereinigung oben."""
    restricted = restricted_laps(data.get("race_control", []))
    pit_laps = {(p["driver"], p["lap"]) for p in data.get("pit_stops", [])}

    times: dict[str, dict[int, float]] = {d: {} for d in drivers}
    for lap in data.get("laps", []):
        drv, num, t = lap.get("Driver"), lap.get("LapNumber"), lap.get("LapTime")
        if drv not in times or num is None or not t:
            continue
        if laps and not (laps[0] <= num <= laps[1]):
            continue
        if lap.get("IsPitOutLap") or (drv, num) in pit_laps or num in restricted:
            continue
        times[drv][num] = float(t)

    all_times = [t for d in times.values() for t in d.values()]
    if not all_times:
        return times
    threshold = min(all_times) * 1.07
    return {d: {n: t for n, t in v.items() if t <= threshold} for d, v in times.items()}


def rolling_median(values: list[float], window: int = 3) -> list[float]:
    """Zentrierter gleitender Median; am Rand wird das Fenster kleiner."""
    half = window // 2
    return [float(np.median(values[max(0, i - half):i + half + 1])) for i in range(len(values))]


def _consecutive_runs(laps: list[int]) -> list[list[int]]:
    """[16, 17, 18, 21, 22] → [[16, 17, 18], [21, 22]]"""
    runs: list[list[int]] = []
    for lap in laps:
        if runs and lap == runs[-1][-1] + 1:
            runs[-1].append(lap)
        else:
            runs.append([lap])
    return runs


def _fmt(seconds: float, decimals: int = 1) -> str:
    minutes, rest = divmod(seconds, 60)
    width = 3 + decimals
    return f"{int(minutes)}:{rest:0{width}.{decimals}f}"


def render_lap_times(ax, data: dict, drivers: list[str],
                     laps: tuple[int, int] | None = None,
                     show_median: bool = True) -> dict[str, dict[int, float]]:
    """show_median: Median jedes Fahrers in der Legende anzeigen. Abschalten,
    wenn Titel oder Untertitel mit Werten einer Teilphase argumentieren –
    sonst widersprechen sich die Zahlen scheinbar."""
    times = clean_lap_times(data, drivers, laps)
    if not any(times.values()):
        raise ValueError(f"Keine gültigen Rundenzeiten für {drivers}")
    teams = data.get("teams", {})

    style_axes(ax, grid_axis="y")
    for drv in drivers:
        series = times[drv]
        if not series:
            continue
        xs = sorted(series)
        ys = [series[x] for x in xs]
        color = team_color(teams.get(drv))
        ax.scatter(xs, ys, s=10, color=color, alpha=0.3, linewidth=0)
        # Linie an Lücken (Boxenstopp, VSC) unterbrechen, statt sie zu überbrücken
        label = f"{drv} · median {_fmt(float(np.median(ys)))}" if show_median else drv
        for segment in _consecutive_runs(xs):
            seg_ys = [series[x] for x in segment]
            ax.plot(segment, rolling_median(seg_ys), color=color, linewidth=1.8, label=label)
            label = None  # nur ein Legendeneintrag pro Fahrer

    # Achse auf den Bereich der Daten zoomen, schneller oben
    all_times = sorted(t for v in times.values() for t in v.values())
    low, high = all_times[0], all_times[-1]
    pad = (high - low) * 0.1 or 0.5  # alle Zeiten gleich → trotzdem sinnvoller Bereich
    ax.set_ylim(high + pad, low - pad)
    ax.yaxis.set_major_formatter(lambda y, _: _fmt(y, decimals=2))

    ax.text(0.99, 0.97, "▲ faster", transform=ax.transAxes, ha="right", va="top",
            fontsize=9, color=COLORS["muted"])
    ax.text(0.99, 0.03, "Pit, out- and VSC laps excluded", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8, color=COLORS["muted"])
    ax.legend(loc="upper left", fontsize=9)
    ax.set_xlabel("Lap")
    ax.set_ylabel("Lap time")
    return times