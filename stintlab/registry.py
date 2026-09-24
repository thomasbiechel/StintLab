"""Verzeichnis aller Analysen, die in einer post.toml benutzt werden können.

Jeder Eintrag sagt:
- render:   Funktion (ax, data, slide) -> zeichnet auf ax
- sessions: für welche Session-Typen die Analyse sinnvoll ist
            (R = Rennen, S = Sprint, Q = Qualifying, FP = Training)

Eine neue Analyse = neue Funktion in stintlab/analyses/ + ein Eintrag hier.
"""

from stintlab.analyses.gap_between import render_gap_between


def _gap_between(ax, data, slide):
    drivers = slide.get("drivers", [])
    if len(drivers) != 2:
        raise ValueError("gap_between braucht genau zwei Fahrer, z. B. drivers = [\"ANT\", \"NOR\"]")
    render_gap_between(ax, data, drivers[0], drivers[1])


ANALYSES = {
    "gap_between": {"render": _gap_between, "sessions": {"R", "S"}},
}