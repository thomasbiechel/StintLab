"""Logik hinter dem Studio (studio.py) – ohne Oberfläche, damit testbar.

- PARAMS / REEL_PARAMS: welche Einstellungen jede Analyse bzw. jedes Reel kennt
  (spiegelt, was registry.py und die Reels aus der post.toml lesen)
- to_toml(): Konfiguration → post.toml-Text (mit Rundlauf-Prüfung über tomllib)
- next_weekend(): das nächste bzw. laufende Wochenende
- existing_posts() / outputs(): vorhandene post.toml und erzeugte Dateien

Neue Analyse = Eintrag in registry.ANALYSES + (falls sie Einstellungen hat) hier in PARAMS.
Fehlt sie hier, bietet das Studio sie trotzdem an – nur ohne Einstellungsfelder.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
POSTS = REPO / "posts"

# Ordnername je Session – wie weekend.py/templates.FOLDERS
FOLDERS = {"FP1": "fp1", "FP2": "fp2", "FP3": "fp3", "SQ": "sprint-quali", "S": "sprint",
           "Q": "quali", "R": "race", "PREVIEW": "preview"}
SESSION_LABELS = {"FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3", "SQ": "Sprint Qualifying",
                  "S": "Sprint", "Q": "Qualifying", "R": "Race", "PREVIEW": "Race Preview (Donnerstag)"}
COMPOUNDS = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]
PARTS = ["Q1", "Q2", "Q3"]


@dataclass
class P:
    """Eine Einstellung. kind: drivers, laps, bool, int, float, select, text."""
    name: str
    kind: str
    label: str
    default: object = None
    options: list = field(default_factory=list)
    n: int | None = None          # drivers: genau so viele Fahrer (None = beliebig)
    required: bool = False
    help: str = ""


_part = P("part", "select", "Abschnitt", None, PARTS, help="nur Qualifying: Q1/Q2/Q3")
_compound = P("compound", "select", "Reifen", None, COMPOUNDS)
_laps = P("laps", "laps", "Runden eingrenzen")
_top = lambda d, h="": P("top", "int", "Anzahl Zeilen", d, help=h)

PARAMS: dict[str, list[P]] = {
    "gap_between": [P("drivers", "drivers", "Fahrer (vorne, hinten)", n=2, required=True), _laps],
    "pit_cycle": [P("drivers", "drivers", "Fahrer", n=2, required=True),
                  P("laps", "laps", "Runde vor / nach dem Stopp", required=True)],
    "lap_times": [P("drivers", "drivers", "Fahrer", required=True), _laps,
                  P("show_median", "bool", "Median-Linie", True)],
    "long_runs": [P("drivers", "drivers", "Fahrer (leer = alle)"), _compound,
                  P("min_laps", "int", "Mindestrunden pro Run", 5), P("show_deg", "bool", "Abbau zeigen", False)],
    "ideal_lap": [P("drivers", "drivers", "Fahrer (leer = alle)"), _compound, _top(None),
                  P("view", "select", "Ansicht", "both", ["both", "best", "ideal"]), _part],
    "sectors": [_compound, _part],
    "telemetry": [P("drivers", "drivers", "Fahrer (leer = Top 2)"), _compound, _part],
    "driver_pace": [P("min_laps", "int", "Mindestrunden", 10), _laps],
    "team_pace": [P("min_laps", "int", "Mindestrunden", 10)],
    "gap_on_lap": [P("drivers", "drivers", "Fahrer (vorne, hinten)", n=2, required=True),
                   P("laps", "laps", "Runden", required=True)],
    "sector_delta": [P("drivers", "drivers", "Fahrer", n=2, required=True), _laps],
    "positions": [P("drivers", "drivers", "Fahrer hervorheben"), _laps],
    "top_speed": [_part, _compound],
    "speed_vs_sector": [P("sector", "select", "Sektor", 2, [1, 2, 3]), _part, _compound],
    "championship": [P("kind", "select", "Wertung", "drivers", ["drivers", "teams"]), _top(10)],
    "title_fight": [_top(8)],
    "best_starters": [_top(20)],
    "saturday_sunday": [_top(20)],
}

# Analysen mit waagrechten Balken → können zusätzlich als animiertes Reel raus (reel = true)
BAR_ANALYSES = {"championship", "title_fight", "teammate_duel", "best_starters", "saturday_sunday",
                "tow_split", "ideal_lap", "team_pace", "driver_pace", "top_speed"}

_hook = P("hook", "text", "Hook (Zeile 1 – Zeile 2)", help="leer = automatisch aus den Daten")
_result = P("result", "text", "Ergebniszeile", help="leer = automatisch")
_order = P("order", "select", "Reihenfolge", "classic", ["classic", "moment_first"],
           help="moment_first: Höhepunkt direkt nach dem Hook – bessere Retention")
_rain = P("rain", "bool", "Regen (Gischt, bedeckter Himmel)", False)

REEL_PARAMS: dict[str, list[P]] = {
    "ghost_lap": [P("part", "select", "Abschnitt", "Q3", PARTS), P("drivers", "drivers", "Fahrer (leer = Top 2)", n=2),
                  P("compare", "int", "Vorjahr: meeting_key", help="Pole gegen Pole im Vorjahr; leer = gleiche Session"),
                  P("replay_km", "float", "Zeitlupe ab km", help="leer = automatisch"),
                  P("replay_note", "text", "Hinweis in der Zeitlupe"), _hook, _result, _order, _rain],
    "gap_chase": [P("drivers", "drivers", "Fahrer (vorne, hinten)", n=2, required=True),
                  P("laps", "laps", "Runden", required=True), _hook, _result],
    "race_story": [P("drivers", "drivers", "Fahrer (vorne, hinten)", n=2, required=True),
                   P("laps", "laps", "Runden", required=True), _hook, _result],
    "comeback": [P("drivers", "drivers", "Fahrer", n=1, required=True),
                 P("pass_lap", "int", "Entscheidendes Manöver: Runde", help="leer = automatisch"),
                 P("pass_rival", "text", "… gegen (Kürzel)"),
                 P("pass_side", "select", "… Seite (nach TV-Bildern)", None, ["left", "right"]),
                 _order, _rain, _hook, _result],
}
REEL_SESSIONS = {"ghost_lap": {"Q", "SQ", "FP1", "FP2", "FP3"}, "gap_chase": {"R", "S"},
                 "race_story": {"R", "S"}, "comeback": {"R", "S"}}


def slug(meeting: dict) -> str:
    """Ordnername fürs Wochenende – wie weekend.slug („São Paulo“ → „sao-paulo“)."""
    raw = meeting.get("location") or meeting.get("circuit_short_name") or meeting.get("meeting_name") or "weekend"
    ascii_ = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")


def default_folder(meeting: dict, stype: str, suffix: str = "") -> str:
    year = str(meeting.get("year") or str(meeting.get("date_start", ""))[:4])
    return f"posts/{year}-{slug(meeting)}/{FOLDERS.get(stype, stype.lower())}{suffix}"


def clean_values(values: dict, params: list[P]) -> dict:
    """Formularwerte → Einträge der post.toml: leere/Standardwerte weglassen, Pflicht prüfen.
    Wirft ValueError mit verständlicher Meldung."""
    out = {}
    for p in params:
        v = values.get(p.name)
        empty = v is None or v == "" or v == [] or (p.kind == "laps" and not v)
        if empty:
            if p.required:
                raise ValueError(f"„{p.label}“ fehlt")
            continue
        if p.kind == "drivers":
            if p.n and len(v) != p.n:
                raise ValueError(f"„{p.label}“: genau {p.n} Fahrer auswählen (sind {len(v)})")
            v = list(v)
        if p.kind == "laps":
            a, b = int(v[0]), int(v[1])
            if b < a:
                raise ValueError(f"„{p.label}“: zweite Runde muss ≥ erste sein")
            v = [a, b]
        if p.kind == "int":
            v = int(v)
        if p.kind == "float":
            v = float(v)
        if v == p.default and not p.required:
            continue
        out[p.name] = v
    return out


def reel_entry(analysis: str, values: dict) -> dict:
    """Reel-Eintrag: compare / pass werden zu den Tabellen, die die Reels erwarten."""
    d = clean_values(values, REEL_PARAMS.get(analysis, []))
    if "compare" in d:
        d["compare"] = {"meeting_key": d["compare"]}
    pas = {k: d.pop(f"pass_{k}") for k in ("lap", "rival", "side") if f"pass_{k}" in d}
    if pas:
        if "lap" not in pas or "rival" not in pas:
            raise ValueError("Manöver: Runde UND Gegner angeben (oder beides leer lassen)")
        d["pass"] = pas
    return {"analysis": analysis, **d}


# ── TOML schreiben ───────────────────────────────────────────────────────────

def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, list):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {_value(x)}" for k, x in v.items()) + " }"
    raise TypeError(f"Nicht in TOML darstellbar: {v!r}")


def to_toml(config: dict, comment: str = "") -> str:
    """{"session": {...}, "slides": [...], "reels": [...]} → post.toml-Text.
    Ein Reel darf "cover" (Titelbild) enthalten → eigene [reels.cover]-Tabelle."""
    lines = [f"# {c}" for c in comment.splitlines()] if comment else []
    lines.append("[session]")
    lines += [f"{k} = {_value(v)}" for k, v in config["session"].items()]
    for slide in config.get("slides", []):
        lines += ["", "[[slides]]"] + [f"{k} = {_value(v)}" for k, v in slide.items()]
    for reel in config.get("reels", []):
        lines += ["", "[[reels]]"] + [f"{k} = {_value(v)}" for k, v in reel.items() if k != "cover"]
        if reel.get("cover"):
            lines += ["", "[reels.cover]"] + [f"{k} = {_value(v)}" for k, v in reel["cover"].items() if v != ""]
    text = "\n".join(lines) + "\n"
    import tomllib                                   # Rundlauf: was wir schreiben, muss make_post lesen können
    back = tomllib.loads(text)
    assert back["session"] == config["session"], "TOML-Rundlauf fehlgeschlagen"
    return text


# ── Wochenenden ──────────────────────────────────────────────────────────────

def _start(m: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(str(m.get("date_start")).replace("Z", "+00:00"))
    except ValueError:
        return None


def _end(m: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(str(m.get("date_end")).replace("Z", "+00:00"))
    except ValueError:
        return None


def race_weekends(meetings: list[dict]) -> list[dict]:
    ms = [m for m in meetings if not m.get("is_cancelled")
          and "testing" not in str(m.get("meeting_name", "")).lower() and _start(m)]
    return sorted(ms, key=_start)


def next_weekend(meetings: list[dict], now: datetime | None = None) -> dict | None:
    """Das laufende Wochenende (Start vorbei, Ende noch nicht) oder sonst das nächste."""
    now = now or datetime.now(timezone.utc)
    for m in race_weekends(meetings):
        end = _end(m) or _start(m)
        if end and end >= now:
            return m
    return None


def current_or_last(meetings: list[dict], now: datetime | None = None) -> dict | None:
    """Das zuletzt begonnene Wochenende – Standard für „Post erstellen“."""
    now = now or datetime.now(timezone.utc)
    started = [m for m in race_weekends(meetings) if _start(m) <= now]
    return started[-1] if started else None


def countdown(target: datetime, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    s = int((target - now).total_seconds())
    if s <= 0:
        return "läuft / vorbei"
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    return f"in {d} T {h} Std" if d else f"in {h} Std {r // 60} Min"


def session_times(sessions: list[dict]) -> list[tuple[str, datetime]]:
    """[(Sessionname, Start in lokaler Zeit des Rechners)] nach Zeit sortiert."""
    out = []
    for s in sessions:
        t = _start(s)
        if t:
            out.append((s.get("session_name", "?"), t.astimezone()))
    return sorted(out, key=lambda x: x[1])


def session_types(sessions: list[dict]) -> list[str]:
    """Kürzel (FP1, Q, R …) der Sessions eines Wochenendes, in Wochenend-Reihenfolge."""
    by_name = {v: k for k, v in SESSION_LABELS.items()}
    names = [s.get("session_name") for s in sorted(sessions, key=lambda s: _start(s) or datetime.max.replace(tzinfo=timezone.utc))]
    return [by_name[n] for n in names if n in by_name]


# ── Vorhandene Posts ─────────────────────────────────────────────────────────

def existing_posts(root: Path = POSTS) -> list[Path]:
    """Alle post.toml, neueste zuerst (nach Änderungszeit)."""
    return sorted(root.glob("**/post.toml"), key=lambda p: p.stat().st_mtime, reverse=True)


def outputs(post_toml: Path) -> dict[str, list[Path]]:
    """Erzeugte Dateien neben einer post.toml: {"images": [...], "videos": [...]}."""
    d = post_toml.parent / "slides"
    if not d.exists():
        return {"images": [], "videos": []}
    return {"images": sorted(d.glob("*.png")), "videos": sorted(d.glob("*.mp4"))}
