"""Verzeichnis aller Analysen, die in einer post.toml benutzt werden können.

Jeder Eintrag sagt:
- render:   Funktion (ax, data, slide) -> zeichnet auf ax
- sessions: für welche Session-Typen die Analyse sinnvoll ist
            (R = Rennen, S = Sprint, Q = Qualifying, FP = Training)

Eine neue Analyse = neue Funktion in stintlab/analyses/ + ein Eintrag hier.
"""

from stintlab.analyses.gap_between import render_gap_between
from stintlab.analyses.gap_on_lap import render_gap_on_lap
from stintlab.analyses.ideal_lap import render_ideal_lap
from stintlab.analyses.lap_times import render_lap_times
from stintlab.analyses.long_runs import render_long_runs
from stintlab.analyses.pit_cycle import render_pit_cycle
from stintlab.analyses.podium import render_podium
from stintlab.analyses.positions import render_positions
from stintlab.analyses.race_pace import render_driver_pace, render_team_pace
from stintlab.analyses.preview import render_chances, render_form, render_track, render_weather
from stintlab.analyses.results import render_results
from stintlab.analyses.sectors import render_sectors
from stintlab.analyses.sector_delta import render_sector_delta
from stintlab.analyses.speed import render_speed_vs_sector, render_top_speed
from stintlab.reels.gap_chase import render_gap_chase
from stintlab.reels.race_story import render_race_story
from stintlab.reels.comeback import render_comeback
from stintlab.reels.ghost_lap import render_ghost_lap
from stintlab.reels.gain_loss import render_gain_loss
from stintlab.analyses.telemetry import render_telemetry
from stintlab.analyses.championship import render_championship, render_title_fight
from stintlab.analyses.teammate_duel import render_teammate_duel
from stintlab.analyses.starts import render_best_starters
from stintlab.analyses.sat_sun import render_saturday_sunday
from stintlab.analyses.tow_effect import render_tow_effect, render_tow_split


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


def _long_runs(ax, data, slide):
    min_laps = slide.get("min_laps", 5)
    if not isinstance(min_laps, int) or min_laps < 3:
        raise ValueError("min_laps muss eine ganze Zahl ab 3 sein, z. B. min_laps = 5")
    show_deg = slide.get("show_deg", False)
    if not isinstance(show_deg, bool):
        raise ValueError("show_deg muss true oder false sein (klein geschrieben, ohne Anführungszeichen)")
    render_long_runs(ax, data, slide.get("drivers") or None, slide.get("compound"), min_laps, show_deg)


def _ideal_lap(ax, data, slide):
    top = slide.get("top")
    if top is not None and (not isinstance(top, int) or top < 2):
        raise ValueError("top muss eine ganze Zahl ab 2 sein, z. B. top = 10")
    render_ideal_lap(ax, data, slide.get("drivers") or None, slide.get("compound"), top,
                     slide.get("view", "both"), slide.get("part"))


def _sectors(ax, data, slide):
    render_sectors(ax, data, slide.get("compound"), slide.get("part"))


def _telemetry(ax, data, slide):
    render_telemetry(ax, data, slide.get("drivers") or None, slide.get("compound"), slide.get("part"))


def _min_laps(slide):
    n = slide.get("min_laps", 10)
    if not isinstance(n, int) or n < 3:
        raise ValueError("min_laps muss eine ganze Zahl ab 3 sein")
    return n


def _laps_window(slide):
    laps = slide.get("laps")
    if laps is not None and len(laps) != 2:
        raise ValueError("laps braucht genau zwei Werte, z. B. laps = [41, 50]")
    return tuple(laps) if laps else None


def _driver_pace(ax, data, slide):
    render_driver_pace(ax, data, _min_laps(slide), _laps_window(slide))


def _two_drivers(slide, name):
    drivers = slide.get("drivers", [])
    if len(drivers) != 2:
        raise ValueError(f"{name} braucht genau zwei Fahrer, z. B. drivers = [\"RUS\", \"VER\"]")
    return drivers


def _gap_on_lap(ax, data, slide):
    laps = _laps_window(slide)
    if not laps:
        raise ValueError("gap_on_lap braucht laps = [erste, letzte], z. B. laps = [40, 50]")
    render_gap_on_lap(ax, data, *_two_drivers(slide, "gap_on_lap"), laps)


def _sector_delta(ax, data, slide):
    render_sector_delta(ax, data, *_two_drivers(slide, "sector_delta"), _laps_window(slide))


def _positions(ax, data, slide):
    render_positions(ax, data, slide.get("drivers") or None, _laps_window(slide))


def _team_pace(ax, data, slide):
    render_team_pace(ax, data, _min_laps(slide))


def _top_speed(ax, data, slide):
    render_top_speed(ax, data, slide.get("part"), slide.get("compound"))


def _speed_vs_sector(ax, data, slide):
    render_speed_vs_sector(ax, data, slide.get("sector", 2), slide.get("part"), slide.get("compound"))


def _podium(ax, data, slide):
    render_podium(ax, data)


def _results(ax, data, slide):
    render_results(ax, data)


def _championship(ax, data, slide):
    kind = slide.get("kind", "drivers")
    if kind not in ("drivers", "teams"):
        raise ValueError('kind muss "drivers" oder "teams" sein')
    top = slide.get("top", 10 if kind == "drivers" else None)
    if top is not None and (not isinstance(top, int) or top < 3):
        raise ValueError("top muss eine ganze Zahl ab 3 sein, z. B. top = 10")
    render_championship(ax, data, kind, top)


def _title_fight(ax, data, slide):
    top = slide.get("top", 8)
    if not isinstance(top, int) or top < 2:
        raise ValueError("top muss eine ganze Zahl ab 2 sein, z. B. top = 8")
    render_title_fight(ax, data, top)


def _top(slide):
    top = slide.get("top", 20)
    if not isinstance(top, int) or top < 3:
        raise ValueError("top muss eine ganze Zahl ab 3 sein, z. B. top = 15")
    return top


def _best_starters(ax, data, slide):
    # alle Rennen des Jahres bis einschließlich dieses Wochenendes (season.py)
    from stintlab.season import race_session, season_sessions
    render_best_starters(ax, season_sessions(data["meeting_key"], "R", load=race_session), _top(slide),
                         slide.get("measure", "turn1"), slide.get("at_frac"))


def _saturday_sunday(ax, data, slide):
    from stintlab.season import race_session, season_sessions
    races = season_sessions(data["meeting_key"], "R", load=race_session)
    quali = {q["meeting_key"]: q for q in season_sessions(data["meeting_key"], "Q")}
    pairs = [(r, quali[r["meeting_key"]]) for r in races if r["meeting_key"] in quali]
    render_saturday_sunday(ax, pairs, _top(slide))


def _teammate_duel(ax, data, slide):
    # alle Qualifyings des Jahres bis einschließlich dieses Wochenendes (season.py)
    from stintlab.season import season_sessions
    render_teammate_duel(ax, season_sessions(data["meeting_key"], "Q"))


ANALYSES = {
    "podium": {"render": _podium, "sessions": {"Q", "SQ", "R", "S"}},
    "gap_between": {"render": _gap_between, "sessions": {"R", "S"}},
    "pit_cycle": {"render": _pit_cycle, "sessions": {"R", "S"}},
    "lap_times": {"render": _lap_times, "sessions": {"R", "S", "FP1", "FP2", "FP3"}},
    "long_runs": {"render": _long_runs, "sessions": {"FP1", "FP2", "FP3"}},
    "ideal_lap": {"render": _ideal_lap, "sessions": {"FP1", "FP2", "FP3", "Q", "SQ"}},
    "championship": {"render": _championship, "sessions": {"R", "S"}},
    "title_fight": {"render": _title_fight, "sessions": {"R", "S"}},
    "teammate_duel": {"render": _teammate_duel, "sessions": {"Q"}},
    "best_starters": {"render": _best_starters, "sessions": {"R"}},
    "saturday_sunday": {"render": _saturday_sunday, "sessions": {"R"}},
    "results": {"render": _results, "sessions": {"FP1", "FP2", "FP3", "Q", "SQ", "R", "S"}},
    "sectors": {"render": _sectors, "sessions": {"FP1", "FP2", "FP3", "Q", "SQ"}},
    "telemetry": {"render": _telemetry, "sessions": {"FP1", "FP2", "FP3", "Q", "SQ"}},
    "driver_pace": {"render": _driver_pace, "sessions": {"R", "S"}},
    "positions": {"render": _positions, "sessions": {"R", "S"}},
    "gap_on_lap": {"render": _gap_on_lap, "sessions": {"R", "S"}},
    "tow_effect": {"render": lambda ax, data, slide: render_tow_effect(ax, data), "sessions": {"R", "S"}},
    "tow_split": {"render": lambda ax, data, slide: render_tow_split(ax, data), "sessions": {"R", "S"}},
    "sector_delta": {"render": _sector_delta, "sessions": {"R", "S", "FP1", "FP2", "FP3"}},
    "top_speed": {"render": _top_speed, "sessions": {"FP1", "FP2", "FP3", "Q", "SQ", "R", "S"}},
    "speed_vs_sector": {"render": _speed_vs_sector, "sessions": {"FP1", "FP2", "FP3", "Q", "SQ", "R", "S"}},
    "team_pace": {"render": _team_pace, "sessions": {"R", "S"}},
    # Race Preview (Donnerstag) – Daten aus stintlab.preview, keine einzelne Session
    "preview_track": {"render": lambda ax, data, slide: render_track(ax, data), "sessions": {"PREVIEW"}},
    "preview_weather": {"render": lambda ax, data, slide: render_weather(ax, data), "sessions": {"PREVIEW"},
                        "source": "Data: OpenF1 · Open-Meteo"},
    "preview_form": {"render": lambda ax, data, slide: render_form(ax, data), "sessions": {"PREVIEW"}},
    "preview_chances": {"render": lambda ax, data, slide: render_chances(ax, data), "sessions": {"PREVIEW"}},
}

# Reels (Videos 9:16) – in der post.toml unter [[reels]]
REELS = {
    "ghost_lap": render_ghost_lap,
    "gap_chase": render_gap_chase,
    "race_story": render_race_story,
    "comeback": render_comeback,
    "gain_loss": render_gain_loss,
}
