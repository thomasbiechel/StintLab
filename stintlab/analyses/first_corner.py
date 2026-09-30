"""Reihenfolge KURZ NACH DER ERSTEN KURVE in Runde 1 – für die echte Startwertung.

WARUM: best_starters maß bisher die Position an der Ziellinie nach Runde 1.
Das ist Start PLUS die ganze erste Runde: Wer am Start zwei Plätze gewinnt und
sie in Kurve 4 wieder verliert, zählte mit null. Hier wird die Reihenfolge
gemessen, sobald das Feld die erste Kurve verlassen hat.

DATEN: /location (x/y, ~3,7 Punkte/s) für ALLE Fahrer, aber nur ein Zeitfenster
um Runde 1 (date>…&date<…) – ~1 MB pro Rennen statt der ganzen Positionsdaten.
Cache: data/cache/<session_key>/location_lap12.json (Runde 1 + Runde 2 des Führenden)

ACHTUNG OpenF1: „Runde 1“ im Rennen enthält die EINFÜHRUNGSRUNDE (Melbourne 2026:
date_start von Runde 1 = Beginn der Einführungsrunde, Runde 1 „dauert“ 184 s bei
85-s-Runden). Den Startmoment zu suchen ist deshalb unzuverlässig – die Methode
braucht ihn nicht:

METHODE, pro Rennen:
1. Referenz = Runde 2 des Pole-Fahrers (von Ziellinie zu Ziellinie, saubere
   fliegende Runde), gleichmäßig nach Weglänge neu abgetastet. 0 = Ziellinie.
2. (entfällt – kein Startmoment nötig)
3. Messpunkt = Ausgang der ersten Kurve + AFTER_EXIT: erste Stelle, an der sich
   die Fahrtrichtung innerhalb CORNER_WIN der Runde um mehr als CORNER_DEG dreht;
   Ausgang = danach QUIET der Runde lang weniger als QUIET_DEG Drehung.
   Mit at_frac (Anteil der Runde) in der post.toml überschreibbar.
4. Für jeden Fahrer: LETZTE Durchfahrt am Messpunkt vor seiner ersten Zieldurchfahrt
   (die Durchfahrt in der Einführungsrunde liegt eine ganze Runde früher) – (Positionspunkte auf die Referenz projiziert, dazwischen linear).
   Reihenfolge dieser Zeitpunkte = Position nach der ersten Kurve.

GRENZEN: Autos im Pulk liegen am Messpunkt oft nur Zehntel auseinander; bei
~3,7 Punkten/s kann die Reihenfolge dicht beieinander liegender Autos falsch
sein. Schikane als erste Kurve (Monza): Ausgang = nach der ganzen Schikane,
weil zwischen den Kurven nicht QUIET lang geradeaus gefahren wird.
"""

from __future__ import annotations

import json
from datetime import timedelta, timezone
from statistics import median

import numpy as np
import requests

from stintlab import openf1
from stintlab.session import _parse

CORNER_WIN, CORNER_DEG = 0.02, 45.0     # Kurve: > 45° Drehung innerhalb 2 % der Runde
QUIET, QUIET_DEG = 0.02, 15.0           # Ausgang: danach 2 % der Runde < 15° Drehung
AFTER_EXIT = 0.01                       # Messpunkt 1 % der Runde nach dem Ausgang (mehr verschob Miami/Budapest ins Chaos danach; Einzelfälle per at_frac)
REF_N = 2000
WINDOW_BEFORE = 1.6                     # Fenster beginnt so viele Median-Runden vor der ersten Zieldurchfahrt


# ── Daten ────────────────────────────────────────────────────────────────────

def _iso(t) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def fetch_lap1_location(race: dict, refresh: bool = False) -> list[dict]:
    """Positionsdaten aller Fahrer im Zeitfenster um Runde 1 (mit Cache)."""
    key = race["session_key"]
    path = openf1.CACHE_DIR / str(key) / "location_lap12.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    ends = [e[1] for e in race["lap_ends"].values() if 1 in e]
    ends2 = [e[2] for e in race["lap_ends"].values() if 2 in e]
    laps = [float(l["LapTime"]) for l in race.get("laps", []) if l.get("LapTime")]
    med = median(laps) if laps else 100.0
    t_from = min(ends) - timedelta(seconds=WINDOW_BEFORE * med + 20)
    t_to = (min(ends2) if ends2 else max(ends)) + timedelta(seconds=3)   # Runde 2 des Führenden = Referenz
    t_to = max(t_to, max(ends) + timedelta(seconds=2))
    # „>“ und „<“ müssen unkodiert in der URL stehen – deshalb die URL von Hand setzen
    req = requests.Request("GET", f"{openf1.BASE_URL}/location",
                           headers={"Authorization": f"Bearer {openf1._get_token()}"}).prepare()
    req.url = f"{openf1.BASE_URL}/location?session_key={key}&date>{_iso(t_from)}&date<{_iso(t_to)}"
    with requests.Session() as s:
        for attempt in range(5):
            r = s.send(req, timeout=180)
            if r.status_code != 429:
                break
            import time
            time.sleep(2 * (attempt + 1))
    r.raise_for_status()
    data = r.json()
    # Falls der Server den Zeitfilter nicht angewendet hat: selbst zuschneiden
    data = [p for p in data if p.get("date") and t_from <= _parse(p["date"]) <= t_to]
    if not data:
        raise ValueError("keine Positionsdaten um Runde 1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def tracks_by_driver(location: list[dict], numbers: dict[str, str], t0) -> dict[str, np.ndarray]:
    """{Kürzel: Array [[t, x, y], …]} – t in Sekunden ab t0, sortiert, ohne doppelte Zeiten."""
    to_abbr = {str(n): a for a, n in numbers.items()}
    raw: dict[str, list] = {}
    for p in location:
        d = to_abbr.get(str(p.get("driver_number")))
        if d is None or p.get("x") is None or p.get("y") is None:
            continue
        raw.setdefault(d, []).append(((_parse(p["date"]) - t0).total_seconds(), float(p["x"]), float(p["y"])))
    out = {}
    for d, pts in raw.items():
        pts.sort()
        arr = np.array([p for i, p in enumerate(pts) if i == 0 or p[0] > pts[i - 1][0]])
        if len(arr) >= 10:
            out[d] = arr
    return out


# ── Rechnen (ohne Netz, testbar) ─────────────────────────────────────────────

def resample(xy: np.ndarray, n: int = REF_N) -> np.ndarray:
    s = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1])))])
    keep = np.concatenate([[True], np.diff(s) > 0])
    xy, s = xy[keep], s[keep]
    u = np.linspace(0, s[-1], n)
    return np.column_stack([np.interp(u, s, xy[:, 0]), np.interp(u, s, xy[:, 1])])


def first_corner_exit(ref: np.ndarray) -> float:
    """Anteil der Runde am Ausgang der ersten Kurve (siehe Modul-Doku)."""
    n = len(ref)
    h = np.unwrap(np.arctan2(np.diff(ref[:, 1]), np.diff(ref[:, 0])))
    w, q = max(int(CORNER_WIN * n), 2), max(int(QUIET * n), 2)
    turn = np.abs(h[w:] - h[:-w])
    entry = np.where(turn > np.radians(CORNER_DEG))[0]
    if not len(entry):
        raise ValueError("keine erste Kurve gefunden")
    j = int(entry[0]) + w
    while j + q < len(h):
        if abs(h[j + q] - h[j]) < np.radians(QUIET_DEG):
            return j / n
        j += 1
    raise ValueError("Ausgang der ersten Kurve nicht gefunden")


def crossing_time(pts: np.ndarray, ref: np.ndarray, at: float, t_before: float,
                  t_after: float) -> float | None:
    """Letzte Durchfahrt am Anteil `at` der Referenz zwischen t_after und t_before."""
    n = len(ref)
    pts = pts[(pts[:, 0] >= t_after) & (pts[:, 0] <= t_before)]
    if len(pts) < 2:
        return None
    d = np.hypot(pts[:, 1, None] - ref[None, :, 0], pts[:, 2, None] - ref[None, :, 1])
    f = np.argmin(d, axis=1) / n
    hit = None
    for i in range(len(f) - 1):
        # beide Punkte nahe am Messpunkt – sonst falsch zugeordnet (Strecke kreuzt sich, Sprung an der Linie)
        if abs(f[i] - at) < 0.05 and abs(f[i + 1] - at) < 0.05 and f[i] < at <= f[i + 1]:
            hit = float(pts[i, 0] + (pts[i + 1, 0] - pts[i, 0]) * (at - f[i]) / (f[i + 1] - f[i]))
    return hit


def line_crossing(pts: np.ndarray, ref: np.ndarray, t_lo: float, t_hi: float) -> float | None:
    """Erste Zieldurchfahrt (Anteil springt von ~1 auf ~0) zwischen t_lo und t_hi."""
    pts = pts[(pts[:, 0] >= t_lo) & (pts[:, 0] <= t_hi)]
    if len(pts) < 2:
        return None
    d = np.hypot(pts[:, 1, None] - ref[None, :, 0], pts[:, 2, None] - ref[None, :, 1])
    f = np.argmin(d, axis=1) / len(ref)
    for i in range(len(f) - 1):
        if f[i] > 0.9 and f[i + 1] < 0.1:
            return float(pts[i, 0] + (pts[i + 1, 0] - pts[i, 0]) * (1 - f[i]) / (f[i + 1] + 1 - f[i]))
    return None


def order_after_turn1(tracks: dict[str, np.ndarray], ref_driver: str, line1: dict[str, float],
                      ref_lap2: tuple[float, float], lap_time: float,
                      at_frac: float | None = None) -> tuple[dict[str, int], float, dict[str, float]]:
    """({Fahrer: Position am Messpunkt}, Messpunkt als Anteil der Runde, {Fahrer: erste Zieldurchfahrt}).

    line1: erste Zieldurchfahrt (s) laut Rundendaten – bei OpenF1 fehlt sie manchmal (Melbourne 2026:
    RUS, LEC, HAM ohne Runde 2). Deshalb wird sie für alle Fahrer aus den Positionsdaten gemessen;
    line1 dient nur als Zeitfenster und als Ersatz, wo die Messung scheitert.
    ref_lap2: (Beginn, Ende) von Runde 2 des Referenzfahrers (irgendein Fahrer mit sauberer Runde 2)."""
    if ref_driver not in tracks:
        raise ValueError(f"keine Positionsdaten für den Referenzfahrer {ref_driver}")
    pp = tracks[ref_driver]
    lap = pp[(pp[:, 0] >= ref_lap2[0]) & (pp[:, 0] <= ref_lap2[1])]
    if len(lap) < 50:
        raise ValueError("Runde 2 des Referenzfahrers fehlt in den Positionsdaten")
    ref = resample(lap[:, 1:])
    at = float(at_frac) if at_frac is not None else first_corner_exit(ref) + AFTER_EXIT
    first = min(line1.values())
    lines = {}
    for d, p in tracks.items():
        t = line_crossing(p, ref, first - 15.0, first + 0.6 * lap_time)
        if t is None and d in line1:
            t = line1[d]
        if t is not None:
            lines[d] = t
    times = {}
    for d, t_line in lines.items():
        t = crossing_time(tracks[d], ref, at, t_line, t_line - 1.2 * lap_time)
        if t is not None:
            times[d] = t
    if not times:
        raise ValueError("niemand am Messpunkt gefunden")
    ranked = sorted(times, key=times.get)
    return {d: i for i, d in enumerate(ranked, start=1)}, at, lines
