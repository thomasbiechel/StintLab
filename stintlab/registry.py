"""Verzeichnis aller Analysen, die in einer post.toml benutzt werden können.

Jeder Eintrag sagt:
- render:   Funktion (ax, data, slide) -> zeichnet auf ax
- sessions: für welche Session-Typen die Analyse sinnvoll ist
            (R = Rennen, S = Sprint, Q = Qualifying, FP = Training)

Eine neue Analyse = neue Funktion in stintlab/analyses/ + ein Eintrag hier.
"""

from stintlab.analyses.gap_between import render_gap_between
from stintlab.analyses.lap_times import render_lap_times
from stintlab.analyses.pit_cycle import render_pit_cycle


def _gap_between(ax, data, slide):
    drivers = slide.get("drivers", [])
    if len(drivers) != 2:
        raise ValueError("gap_between braucht genau zwei Fahrer, z. B. drivers = [\"ANT\", \"NOR\"]")
    laps = slide.get("laps")
    if laps is not None and len(laps) != 2:
        raise ValueError("laps braucht genau zwei Werte, z. B. laps = [15, 48]")
    render_gap_between(ax, data, drivers[0], drivers[1], tuple(laps) if laps else None)


def _pit_cycle(ax, data, slide):
    drivers, laps = slide.get("drivers", []), slide.get("laps", [])
    if len(drivers) != 2 or len(laps) != 2:
        raise ValueError("pit_cycle braucht drivers = [A, B] und laps = [vorher, nachher], "
                         "z. B. laps = [13, 16]")
    render_pit_cycle(ax, data, drivers[0], drivers[1], laps[0], laps[1])


def _lap_times(ax, data, slide):
    drivers, laps = slide.get("drivers", []), slide.get("laps")
    if not drivers:
        raise ValueError("lap_times braucht mindestens einen Fahrer, z. B. drivers = [\"NOR\"]")
    if laps is not None and len(laps) != 2:
        raise ValueError("laps braucht genau zwei Werte, z. B. laps = [16, 57]")
    show_median = slide.get("show_median", True)
    if not isinstance(show_median, bool):
        raise ValueError("show_median muss true oder false sein (klein geschrieben, ohne Anführungszeichen)")
    render_lap_times(ax, data, drivers, tuple(laps) if laps else None, show_median)


ANALYSES = {
    "gap_between": {"render": _gap_between, "sessions": {"R", "S"}},
    "pit_cycle": {"render": _pit_cycle, "sessions": {"R", "S"}},
    "lap_times": {"render": _lap_times, "sessions": {"R", "S", "FP1", "FP2", "FP3"}},
}