"""Reel „Ghost Lap“: zwei Fahrer fahren ihre schnellste Runde gleichzeitig.

ABLAUF (1080 × 1920, 9:16, 60 Bilder/s, ~17 s) – mit replay = false entfällt
die Zeitlupe und die Runde läuft stattdessen 12 s:
  1. Anfang 3D (3,5 s): Verfolgerkamera (chase3d) an der Stelle, an der sich der
                        Abstand am stärksten ändert (wie die Zeitlupe, oder open_at =
                        Sekunde der Runde), Haken-Text groß oben. Ersetzt den
                        schwarzen Titel-Screen: Baku 2026 wischten dort ~50 % in
                        der ersten Sekunde weg.
  2. Runde (7 s):       ganze Streckenkarte, beide Punkte fahren synchron,
                        ~15-fach beschleunigt; oben der laufende Abstand
  3. Zeitlupe (5 s):    die Stelle, an der sich der Abstand am stärksten
                        verändert hat – im 160-m-Zoom, leicht verlangsamt
  4. Auflösung (1,5 s): Ergebnis über der Karte – kein Logo-Screen (dort fiel die
                        Zuschauerkurve noch einmal ab)

WARUM DIESE AUFTEILUNG: Bei 10-facher Geschwindigkeit legt ein Auto mit
250 km/h pro Videobild über 10 m zurück. Auf der ganzen Karte (~2 m/Pixel)
ist das flüssig, im Zoom wären es über 60 Pixel pro Bild – die Punkte würden
springen. Deshalb Zoom nur in der Zeitlupe (~5 Pixel pro Bild). Umgekehrt
sind kleine Abstände (0,1 s ≈ 7 m) auf der ganzen Karte kaum zu sehen –
im Zoom schon.

SYNCHRON: Jeder Fahrer startet bei 0 s am Beginn seiner eigenen Runde. In
jedem Bild werden beide Positionen zur selben verstrichenen Zeit gezeigt –
die Lücke auf der Strecke IST der Zeitabstand.

DATEN: OpenF1 location (x/y, ~3,6 Punkte/s). Madring Q3: Start und Ziel der
Pole-Runde liegen ~4 m auseinander. Zwischen den Punkten wird mit weichen
Kurven (Hermite-Interpolation) statt geraden Stücken verbunden. Der laufende
Abstand kommt aus compare() der Telemetrie-Slide und ist an den offiziellen
Sektorzeiten ausgerichtet.

VORJAHRESVERGLEICH (compare = { meeting_key = 1234 }): A = schnellste Runde
dieser Session (Standard: Pole), B = schnellste Runde desselben Teils im
Qualifying des anderen Wochenendes (Daten vorher mit fetch_compare.py laden).
Beschriftung mit Jahr („RUS '26“, „VER '25“), damit auch derselbe Fahrer geht.
  - Koordinaten: OpenF1 garantiert nicht, dass die Strecke in zwei Jahren gleich
    liegt. B wird per Ähnlichkeitstransformation (Drehung, Verschiebung, Maßstab,
    Umeyama + ICP) auf A gelegt; die Restabweichung wird gemeldet.
  - Prüfungen (Warnung, kein Abbruch): Restabweichung > ALIGN_WARN_M,
    Rundenlänge laut Telemetrie > LENGTH_WARN weg (Umbau?), Regen in einer der
    Sessions (Wetter aus dem Cache, falls geladen).
  - A ist hier NICHT unbedingt schneller – Texte sagen „faster“/„slower“.

WO GEWONNEN / VERLOREN (paint = true, Standard): Während die Runde auf der Karte
läuft, färbt sich die Strecke hinter den Autos – in der Farbe dessen, der an dieser
Stelle Zeit gewinnt (Steigung des geglätteten Abstands, blasser = weniger).
Nach jedem Sektor erscheint oben dessen Bilanz („S2  VER +0.12“), im Ergebnis
stehen alle drei. Die Sektorwerte kommen aus demselben Abstand wie die große Zahl
(an den offiziellen Sektorzeiten ausgerichtet), ergeben also zusammen genau den
Abstand der Runde. Sind die Teamfarben zu ähnlich (Red Bull / Alpine, gleiches
Team), nimmt die Karte Lila/Rot statt der Teamfarben – das 3D-Bild bleibt in
Teamfarben. Vorbild: das Gain/Loss-Reel (Baku 2026).

ERGEBNIS ALS BILANZ: Mit Färbung (paint = true) ist das Ergebnis kein Standbild der
Karte mehr, sondern drei Balken S1/S2/S3, die nacheinander wachsen – nach oben, wo A
gewinnt, nach unten, wo B gewinnt –, darunter die Summen je Fahrer.
FRAGE AM ENDE (question = "…", Standard je nach Reel, question = "" = keine):
letztes Bild vor der Schleife, bringt Kommentare. Grund: São Paulo Rewind 2026 –
0 Kommentare bei 2.141 Aufrufen, das Reel stellte den Zuschauern keine Frage.

SICHERE ZONE: Instagram legt unten Caption/Buttons und rechts die Like-Leiste
über das Video – unten ~20 % bleiben frei, Wichtiges steht in der Mitte.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib import animation
from matplotlib import patheffects
from matplotlib import pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import to_rgba

from stintlab import openf1
from stintlab.analyses.ideal_lap import _valid_laps
from stintlab.analyses.long_runs import _fmt
from stintlab.analyses.telemetry import _driver_trace, compare, fastest_lap
from stintlab.session import _parse
from stintlab.trackpos import retime
from stintlab.style import COLORS, resolve_font, team_color

WIDTH_PX, HEIGHT_PX, DPI, FPS = 1080, 1920, 150, 60
OPEN_S, LAP_S, REPLAY_S, RESULT_S = 3.5, 7.0, 5.0, 3.5   # Ergebnis länger: Sektor-Balken wachsen nacheinander
ASK_S = 2.5            # Frage an die Zuschauer am Ende
REPLAY_WINDOW_S = 4.0  # so viele echte Sekunden zeigt die Zeitlupe (5 s Video → 0,8-fach)
TRAIL_S = 2.0          # Schweif hinter den Punkten, in echten Sekunden
ZOOM_M = 160.0         # Breite des Zoom-Ausschnitts in Metern
MAP_BOX = [0.06, 0.36, 0.88, 0.44]
ALIGN_WARN_M = 4.0     # mittlere Restabweichung der Strecken nach dem Übereinanderlegen
LENGTH_WARN = 0.01     # 1 % Unterschied der Rundenlänge → vermutlich Umbau
PAINT_SMOOTH = 0.015   # Glättung des Abstands für die Färbung (Anteil der Runde, ~80 m)
PAINT_GRID = 1000      # Stützstellen der Runde für die Färbung
COLOR_MIN_DIST = 0.35  # Teamfarben näher als das (RGB-Abstand) → Lila/Rot auf der Karte
LOSS_COLOR = "#ff5a5f"


# ── Daten ────────────────────────────────────────────────────────────────────

def lap_positions(location: list[dict], lap: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(Zeit ab Rundenbeginn, x, y) für eine Runde, mit etwas Rand davor/danach."""
    start, lap_time = lap["LapStart"], float(lap["LapTime"])
    pts = []
    for p in location:
        when = _parse(p.get("date"))
        if when is None or p.get("x") is None or p.get("y") is None:
            continue
        t = (when - start).total_seconds()
        if -2.0 <= t <= lap_time + 2.0:
            pts.append((t, float(p["x"]), float(p["y"])))
    pts.sort()
    # doppelte Zeitstempel entfernen – die Interpolation braucht steigende Zeiten
    clean = [p for i, p in enumerate(pts) if i == 0 or p[0] > pts[i - 1][0]]
    if len(clean) < 10:
        raise ValueError(f"{lap['Driver']}: zu wenige Positionsdaten für Runde {lap['LapNumber']}")
    arr = np.array(clean)
    return retime(arr[:, 0], arr[:, 1], arr[:, 2])   # gegen „Jojo“ und Hänger, siehe stintlab.trackpos


def orient(x: np.ndarray, y: np.ndarray, rotate: bool) -> tuple[np.ndarray, np.ndarray]:
    """Karte ins Hochformat drehen, falls die Strecke breiter als hoch ist."""
    return (y, -x) if rotate else (x, y)


def needs_rotation(x: np.ndarray, y: np.ndarray) -> bool:
    return (x.max() - x.min()) > (y.max() - y.min())


def smooth_interp(t: np.ndarray | float, tt: np.ndarray, vv: np.ndarray) -> np.ndarray:
    """Weiche Interpolation (kubische Hermite-Kurve) statt gerader Stücke.

    Steigung an jedem Punkt aus den Nachbarn – dadurch keine Ecken in Kurven.
    Außerhalb der Daten wird der Randwert gehalten.
    """
    t = np.clip(np.atleast_1d(np.asarray(t, dtype=float)), tt[0], tt[-1])
    m = np.gradient(vv, tt)
    i = np.clip(np.searchsorted(tt, t) - 1, 0, len(tt) - 2)
    h = tt[i + 1] - tt[i]
    s = (t - tt[i]) / h
    h00, h10 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s
    h01, h11 = -2 * s**3 + 3 * s**2, s**3 - s**2
    return h00 * vv[i] + h10 * h * m[i] + h01 * vv[i + 1] + h11 * h * m[i + 1]


def pick_drivers(data: dict, drivers: list[str] | None, part: str | None,
                 compound: str | None = None) -> tuple[list[str], list[dict]]:
    """Zwei Fahrer (angegeben oder die zwei schnellsten) und ihre schnellsten
    Runden – der Schnellere zuerst."""
    if not drivers:
        best = sorted((l for l in (fastest_lap(data, d, compound, part) for d in _valid_laps(data, compound, part))
                       if l), key=lambda l: float(l["LapTime"]))
        drivers = [l["Driver"] for l in best[:2]]
    if len(drivers) != 2:
        raise ValueError("Ghost Lap braucht genau zwei Fahrer")
    laps = [fastest_lap(data, d, compound, part) for d in drivers]
    for d, lap in zip(drivers, laps):
        if lap is None:
            raise ValueError(f"{d}: keine gültige Runde{' in ' + part if part else ''}")
    if float(laps[1]["LapTime"]) < float(laps[0]["LapTime"]):
        drivers, laps = drivers[::-1], laps[::-1]
    return list(drivers), laps


def pace_positions(t: np.ndarray, x: np.ndarray, y: np.ndarray, trace: dict,
                   lap_time: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Position über die Zeit aus TEMPO + BAHN statt aus den Zeitstempeln.

    Die Positionsdaten liefern die Form der Bahn (wo liegt die Strecke), das
    Tempo aus car_data liefert, wann das Auto wo ist: Anteil der Runde laut
    Tempo → Punkt auf der Bahn. Monza 2026 Q3: Gaslys Position hängt ~1,4 s
    und holt die ~60 m nie auf; das Tempo ist dort repariert (frozen_runs) und
    an den offiziellen Sektorzeiten ausgerichtet. Außerhalb der Runde (Rand
    für den Schweif) bleiben die geglätteten Rohdaten.
    """
    inside = (t >= 0) & (t <= lap_time)
    if inside.sum() < 10 or "frac" not in trace:
        return t, x, y
    xi, yi = x[inside], y[inside]
    s = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(xi), np.diff(yi)))])
    keep = np.concatenate([[True], np.diff(s) > 0])        # hängende Punkte = gleiche Stelle
    s, xi, yi = s[keep], xi[keep], yi[keep]
    f = s / s[-1]
    tt, ff = trace["t"], trace["frac"]
    before, after = t < 0, t > lap_time
    return (np.concatenate([t[before], tt, t[after]]),
            np.concatenate([x[before], np.interp(ff, f, xi), x[after]]),
            np.concatenate([y[before], np.interp(ff, f, yi), y[after]]))


def _clean_location(loc: list[dict], lap: dict, t: np.ndarray, x: np.ndarray, y: np.ndarray) -> list[dict]:
    """Aufbereitete Positionen wieder als /location-Liste (für den 3D-Anfang),
    Höhe z aus den Rohdaten zur selben Zeit."""
    raw = sorted(((_parse(p["date"]) - lap["LapStart"]).total_seconds(), float(p.get("z") or 0.0))
                 for p in loc if p.get("date"))
    rt, rz = np.array([r[0] for r in raw]), np.array([r[1] for r in raw])
    z = np.interp(t, rt, rz)
    return [{"date": (lap["LapStart"] + timedelta(seconds=float(ti))).isoformat(), "x": float(xi), "y": float(yi),
             "z": float(zi)} for ti, xi, yi, zi in zip(t, x, y, z)]


def prepare(data: dict, drivers: list[str] | None = None, part: str | None = None) -> dict:
    """Alles, was das Video braucht – ohne Zeichnen, damit testbar."""
    drivers, laps = pick_drivers(data, drivers, part)
    traces = [_driver_trace(data, d, l) for d, l in zip(drivers, laps)]
    res = compare(*traces)

    pos, clean_loc = [], {}
    for d, lap, tr in zip(drivers, laps, traces):
        loc = data.get("location", {}).get(d)
        if loc is None:
            loc = openf1.cached_fetch_driver("location", data["session_key"], data["numbers"][d])
        t, x, y = pace_positions(*lap_positions(loc, lap), tr, float(lap["LapTime"]))
        pos.append((t, x, y))
        clean_loc[d] = _clean_location(loc, lap, t, x, y)
    rotate = needs_rotation(pos[0][1], pos[0][2])
    pos = [(t, *orient(x, y, rotate)) for t, x, y in pos]

    a, b = traces
    return {"drivers": drivers, "laps": laps, "traces": traces, "res": res, "pos": pos,
            "a_frac": (a["t"], a["frac"]), "gap": b["lap_time"] - a["lap_time"],
            "teams": [data.get("teams", {}).get(d) for d in drivers], "clean_location": clean_loc}


# ── Vorjahresvergleich ───────────────────────────────────────────────────────

def _resample(x: np.ndarray, y: np.ndarray, n: int = 1500) -> np.ndarray:
    s = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
    keep = np.concatenate([[True], np.diff(s) > 0])
    u = np.linspace(0, s[keep][-1], n)
    return np.column_stack([np.interp(u, s[keep], x[keep]), np.interp(u, s[keep], y[keep])])


def _umeyama(src: np.ndarray, dst: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """Ähnlichkeitstransformation dst ≈ s·R·src + t (kleinste Quadrate)."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    U, D, Vt = np.linalg.svd(xd.T @ xs / len(src))
    S = np.eye(2)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[1, 1] = -1
    R = U @ S @ Vt
    scale = float(np.trace(np.diag(D) @ S) / xs.var(0).sum())
    return scale, R, mu_d - scale * R @ mu_s


def align_track(a: np.ndarray, b: np.ndarray, iters: int = 15) -> tuple[float, np.ndarray, np.ndarray, float]:
    """Legt Bahn b (n×2) auf Bahn a. Start: Punkte gleichen Rundenanteils
    (beide Runden beginnen an der Ziellinie), dann ICP mit nächsten Nachbarn.
    Rückgabe (s, R, t, mittlere Restabweichung in Einheiten von a)."""
    A, B = _resample(a[:, 0], a[:, 1]), _resample(b[:, 0], b[:, 1])
    # Startpunkt der Bahnen muss nicht gleich sein: beste zyklische Zuordnung suchen
    best = None
    for shift in range(0, len(B), max(len(B) // 120, 1)):
        Bs = np.roll(B, -shift, axis=0)
        s_, R, t = _umeyama(Bs, A)
        err = float(((s_ * (R @ Bs.T)).T + t - A).__pow__(2).sum(1).mean())
        if best is None or err < best[0]:
            best = (err, s_, R, t)
    _, s_, R, t = best
    for _ in range(iters):
        Bt = (s_ * (R @ B.T)).T + t
        d2 = ((Bt[:, None, :] - A[None, ::3, :]) ** 2).sum(-1)
        nn = A[::3][d2.argmin(1)]
        s_, R, t = _umeyama(B, nn)
    Bt = (s_ * (R @ B.T)).T + t
    resid = float(np.sqrt(((Bt[:, None, :] - A[None, :, :]) ** 2).sum(-1).min(1)).mean())
    return s_, R, t, resid


def rebuild_lap(data: dict, drv: str, part: str | None, ref_path: np.ndarray, ref_start: np.ndarray) -> dict:
    """Runde ohne OpenF1-Rundendaten (Baku 2025 Q: laps.json leer) aus Positionen
    + offizieller Zeit rekonstruieren:
      1. im Zeitfenster des Abschnitts das Stück der offiziellen Länge T suchen,
         nach dem das Auto wieder an derselben Stelle ist (= die fliegende Runde)
      2. dieses Stück auf die Referenzbahn legen → Ziellinie in eigenen Koordinaten
      3. Rundenbeginn = Überqueren der Ziellinie, Kontrolle: T später wieder dort
    Sektorzeiten gibt es dann nicht (None)."""
    from stintlab.quali import PARTS, session_parts
    row = next((r for r in data.get("results", []) if r.get("driver") == drv), None)
    times = row.get("duration") if row else None
    if isinstance(times, list):
        idx = PARTS.index(part) if part in PARTS else int(np.nanargmin([x or np.nan for x in times]))
        T = times[idx]
    else:
        T, idx = times, None
    if not T:
        raise ValueError(f"{drv}: keine offizielle Zeit{' in ' + part if part else ''} im Ergebnis")
    T = float(T)
    loc = data.get("location", {}).get(drv) or openf1.cached_fetch_driver("location", data["session_key"],
                                                                           data["numbers"][drv])
    pts = sorted((_parse(p["date"]), float(p["x"]), float(p["y"])) for p in loc
                 if p.get("date") and p.get("x") is not None and (p["x"] or p["y"]))
    origin = pts[0][0]
    tt = np.array([(d - origin).total_seconds() for d, _, _ in pts])
    xx, yy = np.array([p[1] for p in pts]), np.array([p[2] for p in pts])
    keep = np.concatenate([[True], np.diff(tt) > 0])
    tt, xx, yy = tt[keep], xx[keep], yy[keep]
    parts = session_parts(data.get("race_control", []))
    if idx is not None and idx < len(parts):
        lo, hi = ((w - origin).total_seconds() for w in parts[idx])
    else:
        lo, hi = tt[0], tt[-1]
    P = lambda t: np.column_stack([np.interp(t, tt, xx), np.interp(t, tt, yy)])
    # Eine Runde zählt, wenn sie VOR der Zielflagge beginnt – sie darf danach enden
    cand = np.arange(lo, min(hi + 5.0, tt[-1] - T), 0.2)
    if not len(cand):
        raise ValueError(f"{drv}: Abschnitt kürzer als die Runde")
    d = np.hypot(*(P(cand) - P(cand + T)).T)
    # Nur Stücke, in denen wirklich eine ganze Runde gefahren wird – ein stehendes
    # Auto (Box) ist nach T Sekunden auch „wieder an derselben Stelle“
    arc = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(xx), np.diff(yy)))])
    travelled = np.interp(cand + T, tt, arc) - np.interp(cand, tt, arc)
    d = np.where(travelled >= 0.97 * travelled.max(), d, np.inf)
    t0 = float(cand[int(np.argmin(d))])
    loop = P(np.linspace(t0, t0 + T, 1500))
    s_, R, t, resid = align_track(ref_path, loop)
    F = np.linalg.inv(s_ * R) @ (ref_start - t)                 # Ziellinie in eigenen Koordinaten
    win = np.arange(t0 - T / 2, t0 + T / 2, 0.02)
    score = np.hypot(*(P(win) - F).T) + np.hypot(*(P(win + T) - F).T)
    start = float(win[int(np.argmin(score))])
    miss = float(np.hypot(*(P(np.array([start + T])) - F)[0]))
    lap = {"Driver": drv, "LapNumber": 9000 + (idx or 0), "LapTime": T,
           "LapStart": origin + timedelta(seconds=start), "IsPitOutLap": False, "rebuilt": True,
           "rebuilt_miss": miss, "rebuilt_align": resid}
    for k in ("Sector1Time", "Sector2Time", "Sector3Time"):
        lap[k] = None
    return lap


def _year(data: dict) -> str:
    for lap in data.get("laps", []):
        if lap.get("LapStart") is not None:
            return str(lap["LapStart"].year)
    return "?"


def _rain(data: dict) -> bool | None:
    """Regen laut OpenF1-Wetter (None = kein Wetter im Cache)."""
    path = openf1.CACHE_DIR / str(data["session_key"]) / "weather.json"
    if not path.exists():
        return None
    import json
    return any(w.get("rainfall") for w in json.loads(path.read_text(encoding="utf-8")))


def prepare_compare(data: dict, data_b: dict, driver_a: str | None, driver_b: str | None,
                    part: str | None, part_b: str | None = None) -> dict:
    """Wie prepare(), aber B aus einer anderen Session (Vorjahr), auf A's Strecke gelegt."""
    def best(d: dict, drv: str | None, prt: str | None) -> tuple[str, dict]:
        if not drv:
            laps = [l for l in (fastest_lap(d, x, None, prt) for x in _valid_laps(d, None, prt)) if l]
            if not laps:
                raise ValueError(f"keine gültige Runde{' in ' + prt if prt else ''}")
            lap = min(laps, key=lambda l: float(l["LapTime"]))
            return lap["Driver"], lap
        lap = fastest_lap(d, drv, None, prt)
        if lap is None:
            raise ValueError(f"{drv}: keine gültige Runde{' in ' + prt if prt else ''}")
        return drv, lap

    da, lap_a = best(data, driver_a, part)
    if data_b.get("laps"):
        db, lap_b = best(data_b, driver_b, part_b or part)
    else:
        # OpenF1 ohne Rundendaten → Runde aus Positionen + offizieller Zeit (Standard: Pole)
        db = driver_b or next(r["driver"] for r in data_b.get("results", []) if r.get("position") == 1)
        loc_a = data.get("location", {}).get(da) or openf1.cached_fetch_driver("location", data["session_key"],
                                                                              data["numbers"][da])
        t_a, x_a, y_a = lap_positions(loc_a, lap_a)
        ins = (t_a >= 0) & (t_a <= float(lap_a["LapTime"]))
        start_a = np.array([np.interp(0.0, t_a, x_a), np.interp(0.0, t_a, y_a)])
        lap_b = rebuild_lap(data_b, db, part_b or part, np.column_stack([x_a[ins], y_a[ins]]), start_a)
        data_b = {**data_b, "laps": [lap_b]}
    ya, yb = _year(data), _year(data_b)
    name_a, name_b = f"{da} '{ya[-2:]}", f"{db} '{yb[-2:]}"
    traces = [_driver_trace(data, da, lap_a), _driver_trace(data_b, db, lap_b)]
    res = compare(*traces)

    raw = []
    for d, drv, lap, tr in ((data, da, lap_a, traces[0]), (data_b, db, lap_b, traces[1])):
        loc = d.get("location", {}).get(drv)
        if loc is None:
            loc = openf1.cached_fetch_driver("location", d["session_key"], d["numbers"][drv])
        raw.append((loc, lap, pace_positions(*lap_positions(loc, lap), tr, float(lap["LapTime"]))))

    # B auf A legen
    (_, _, (ta, xa, ya_)), (loc_b, _, (tb, xb, yb_)) = raw
    ins_a, ins_b = (ta >= 0) & (ta <= float(lap_a["LapTime"])), (tb >= 0) & (tb <= float(lap_b["LapTime"]))
    scale, R, t, resid = align_track(np.column_stack([xa[ins_a], ya_[ins_a]]), np.column_stack([xb[ins_b], yb_[ins_b]]))
    xy = (scale * (R @ np.vstack([xb, yb_]))).T + t
    xb2, yb2 = xy[:, 0], xy[:, 1]
    per_m = float(np.sum(np.hypot(np.diff(xa[ins_a]), np.diff(ya_[ins_a])))) / traces[0]["length"]
    checks = {"align_m": resid / per_m, "scale": scale,
              "length_a": traces[0]["length"], "length_b": traces[1]["length"],
              "rain_a": _rain(data), "rain_b": _rain(data_b)}

    clean_loc = {name_a: _clean_location(raw[0][0], lap_a, ta, xa, ya_),
                 name_b: _clean_location(loc_b, lap_b, tb, xb2, yb2)}
    # Höhe: gleiche Einheit/Nullpunkt wie A (Maßstab + Median-Versatz)
    za = np.median([p["z"] for p in clean_loc[name_a]])
    zb = np.median([p["z"] for p in clean_loc[name_b]]) * scale
    for p in clean_loc[name_b]:
        p["z"] = p["z"] * scale + (za - zb)

    pos = [(ta, xa, ya_), (tb, xb2, yb2)]
    rotate = needs_rotation(xa, ya_)
    pos = [(tt, *orient(x, y, rotate)) for tt, x, y in pos]
    team_a, team_b = data.get("teams", {}).get(da), data_b.get("teams", {}).get(db)
    # Daten für die 3D-Szene: A unter neuem Namen (Referenzrunde, Telemetrie, Maßstab aus A)
    scene_data = {**data, "location": clean_loc,
                  "laps": [dict(l, Driver=name_a) for l in data.get("laps", []) if l["Driver"] == da],
                  "numbers": {name_a: data["numbers"][da]}, "teams": {name_a: team_a, name_b: team_b},
                  "car_data": {name_a: data.get("car_data", {}).get(da)} if data.get("car_data", {}).get(da) else {}}
    a, b = traces
    return {"drivers": [name_a, name_b], "laps": [lap_a, lap_b], "traces": traces, "res": res, "pos": pos,
            "a_frac": (a["t"], a["frac"]), "gap": b["lap_time"] - a["lap_time"],
            "teams": [team_a, team_b], "clean_location": clean_loc, "scene_data": scene_data,
            "years": (ya, yb), "checks": checks, "compare": True}


def check_messages(checks: dict, years: tuple[str, str]) -> list[str]:
    """Warnungen, wenn der Vorjahresvergleich hinken könnte."""
    msgs = []
    if checks["align_m"] > ALIGN_WARN_M:
        msgs.append(f"Strecken passen nicht gut übereinander: im Mittel {checks['align_m']:.1f} m daneben "
                    f"(Umbau? andere Koordinaten?)")
    diff = checks["length_b"] / checks["length_a"] - 1
    if abs(diff) > LENGTH_WARN:
        msgs.append(f"Rundenlänge laut Telemetrie {years[1]} {diff:+.1%} gegenüber {years[0]} – Streckenänderung?")
    for key, y in (("rain_a", years[0]), ("rain_b", years[1])):
        if checks[key]:
            msgs.append(f"Regen im Qualifying {y} – Vergleich nicht fair")
        elif checks[key] is None:
            msgs.append(f"Kein Wetter für {y} im Cache – Regen nicht geprüft (fetch_compare.py)")
    return msgs


def _filled_delta(res: dict) -> tuple[np.ndarray, np.ndarray]:
    """Abstand auf gleichmäßigem Raster über die Runde, Lücken (NaN) linear gefüllt."""
    grid = np.linspace(0.0, 1.0, PAINT_GRID)
    frac, delta = np.asarray(res["frac"], float), np.asarray(res["delta"], float)
    ok = ~np.isnan(delta)
    if ok.sum() < 2:
        raise ValueError("zu wenige Abstandswerte für die Färbung")
    return grid, np.interp(grid, frac[ok], delta[ok])


def gain_profile(frac: np.ndarray, res: dict, width: float = PAINT_SMOOTH) -> tuple[np.ndarray, np.ndarray]:
    """Für jede Stelle `frac`: wer gewinnt dort Zeit (+1 = A, −1 = B) und wie stark (0,2–1)."""
    grid, d = _filled_delta(res)
    n = max(int(round(width * PAINT_GRID)) | 1, 1)
    padded = np.concatenate([np.full(n // 2, d[0]), d, np.full(n // 2, d[-1])])
    sm = np.convolve(padded, np.ones(n) / n, mode="valid")
    slope = np.gradient(sm)
    ref = np.percentile(np.abs(slope), 85) or 1.0
    at = np.interp(np.asarray(frac, float), grid, slope)
    return np.where(at >= 0, 1.0, -1.0), np.clip(np.abs(at) / ref, 0.2, 1.0)


def sector_gains(res: dict) -> list[float]:
    """Zeit, die A in jedem Sektor gewinnt (> 0) oder verliert (< 0). Summe = Abstand der Runde.
    Leer, wenn die Sektorgrenzen fehlen."""
    marks = [0.0] + list(res.get("sector_marks") or []) + [1.0]
    if len(marks) != 4:
        return []
    grid, d = _filled_delta(res)
    v = np.interp(marks, grid, d)
    return [float(v[i + 1] - v[i]) for i in range(3)]


def colors_too_close(c1: str, c2: str) -> bool:
    from matplotlib.colors import to_rgb
    return float(np.linalg.norm(np.subtract(to_rgb(c1), to_rgb(c2)))) < COLOR_MIN_DIST


def gap_at(prep: dict, t: float) -> float:
    """Laufender Abstand (> 0 = A vorne) zur Rundenzeit t von A."""
    at, afrac = prep["a_frac"]
    frac = float(np.interp(t, at, afrac))
    return float(np.interp(frac, prep["res"]["frac"], prep["res"]["delta"]))


def replay_start(prep: dict, lap_time: float, window: float = REPLAY_WINDOW_S) -> float:
    """Beginn des Zeitlupen-Fensters: dort, wo sich der Abstand innerhalb von
    `window` Sekunden am stärksten verändert (Madring Q3: letzte Kurve)."""
    ts = np.arange(0.0, max(lap_time - window, 0.0) + 1e-9, 0.1)
    gaps = np.array([gap_at(prep, t) for t in np.arange(0.0, lap_time + 1e-9, 0.1)])
    shift = int(round(window / 0.1))
    change = np.array([abs(gaps[min(i + shift, len(gaps) - 1)] - gaps[i]) for i in range(len(ts))])
    # Fenster mit eingefrorenen Messwerten meiden: dort ist der Verlauf nur
    # interpoliert – und ändert sich scheinbar am stärksten (Monza 2026 Q3, Gasly:
    # Anfang und Zeitlupe landeten genau in der Lücke, Russell „überholte“)
    blocked = [(t0 - 1.0, t1 + 1.0) for tr in prep.get("traces", []) for t0, t1 in tr.get("frozen", [])]
    ok = np.array([not any(a0 < t + window and t < a1 for a0, a1 in blocked) for t in ts], dtype=bool)
    if len(ts) and ok.any():
        change = np.where(ok, change, -1.0)
    return float(ts[int(np.argmax(change))]) if len(ts) else 0.0


def replay_from_config(prep: dict, reel: dict, lap_time: float) -> float:
    """Beginn der Zeitlupe in Sekunden der Runde von A.

    replay_km = 3.0     → ab Streckenkilometer 3,0 (wie auf der Telemetrie-Slide)
    replay_start = 80   → ab Sekunde 80 der Runde
    nichts              → automatisch, wo sich der Abstand am stärksten ändert.
    Vorsicht automatisch: In langsamen Passagen (Baku, Burgabschnitt) kann der
    Abstand durch kleine Messfehler springen – dann lieber replay_km setzen.
    """
    if reel.get("replay_km") is not None:
        frac = float(reel["replay_km"]) * 1000 / prep["res"]["length_m"]
        if not 0 <= frac < 1:
            raise ValueError(f"replay_km liegt außerhalb der Runde (0 bis {prep['res']['length_m'] / 1000:.2f} km)")
        at, afrac = prep["a_frac"]
        return float(np.interp(frac, afrac, at))
    if reel.get("replay_start") is not None:
        return float(reel["replay_start"])
    return replay_start(prep, lap_time)


def open_from_config(reel: dict, replay_from: float | None, prep: dict, lap_time: float) -> float:
    """Beginn des 3D-Anfangs in Sekunden der Runde von A: open_at, sonst kurz
    vor der Stelle der Zeitlupe (bzw. der stärksten Abstandsänderung)."""
    if reel.get("open_at") is not None:
        start = float(reel["open_at"])
    else:
        start = (replay_from if replay_from is not None else replay_start(prep, lap_time)) - 0.5
    return float(np.clip(start, 0.0, max(lap_time - OPEN_S, 0.0)))


ORDERS = ("classic", "moment_first")


def frame_times(lap_time: float, replay_from: float | None,
                open_from: float | None = None, order: str = "classic") -> list[tuple[str, float]]:
    """[(Phase, Rundenzeit in s), ...] – ein Eintrag pro Videobild.

    replay_from = None: keine Zeitlupe – die Runde bekommt deren Zeit dazu und
    läuft langsamer (Gesamtlänge bleibt gleich).
    open_from = None: ohne 3D-Anfang (z. B. in Tests ohne Positionsdaten).
    order:
      "classic"      3D-Anfang → ganze Runde (Karte) → Zeitlupe → Ergebnis
      "moment_first" 3D-Anfang → Zeitlupe → ganze Runde (Karte) → Ergebnis.
                     Grund (Reel Baku Pole '26 vs '25): Die Hälfte der Zuschauer
                     ging zwischen 0:02 und 0:06 – genau beim Schnitt vom 3D-Bild
                     auf die flache Karte, deren Abstand wieder bei 0,00 s beginnt.
                     So bleibt es bis ~8,5 s in 3D, die Karte fasst danach zusammen.
    """
    if order not in ORDERS:
        raise ValueError(f"order muss einer von {', '.join(ORDERS)} sein")
    opening = [] if open_from is None else [("open", open_from + i / FPS) for i in range(int(OPEN_S * FPS))]
    n = int((LAP_S if replay_from is not None else LAP_S + REPLAY_S) * FPS)
    lap = [("lap", lap_time * i / (n - 1)) for i in range(n)]
    replay = []
    if replay_from is not None:
        n = int(REPLAY_S * FPS)
        end = min(replay_from + REPLAY_WINDOW_S, lap_time)
        replay = [("replay", replay_from + (end - replay_from) * i / (n - 1)) for i in range(n)]
    middle = replay + lap if order == "moment_first" else lap + replay
    return opening + middle + [("result", lap_time)] * int(RESULT_S * FPS)


def _position(p: tuple, t: float | np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tt, x, y = p
    return smooth_interp(t, tt, x), smooth_interp(t, tt, y)


# ── Video ────────────────────────────────────────────────────────────────────

def _fading_trail(ax, color: str, width: float, dashed: bool = False) -> LineCollection:
    lc = LineCollection([], linewidths=width, capstyle="round", zorder=3,
                        linestyles="--" if dashed else "-")
    lc.base_rgba = to_rgba(color)
    ax.add_collection(lc)
    return lc


def _update_trail(lc: LineCollection, p: tuple, t: float) -> None:
    """Schweif, der nach hinten ausblendet – wirkt wie Bewegungsunschärfe."""
    ts = np.linspace(max(t - TRAIL_S, 0.0), t, 24)
    x, y = _position(p, ts)
    pts = np.column_stack([x, y])
    segs = np.stack([pts[:-1], pts[1:]], axis=1)
    r, g, b, _ = lc.base_rgba
    alphas = np.linspace(0.0, 0.75, len(segs))
    lc.set_segments(segs)
    lc.set_color([(r, g, b, a) for a in alphas])


def render_ghost_lap(data: dict, reel: dict, path: Path) -> Path:
    if reel.get("compare"):
        from stintlab.session import load_session
        cmp_cfg = reel["compare"]
        if not isinstance(cmp_cfg, dict) or "meeting_key" not in cmp_cfg:
            raise ValueError("compare braucht die meeting_key des Vorjahres, z. B. compare = { meeting_key = 1266 }")
        data_b = load_session(int(cmp_cfg["meeting_key"]), cmp_cfg.get("type", data.get("session_type", "Q")))
        drivers = reel.get("drivers") or [None, None]
        prep = prepare_compare(data, data_b, drivers[0], drivers[1] if len(drivers) > 1 else None,
                               reel.get("part"), cmp_cfg.get("part"))
        c = prep["checks"]
        print(f"  Vorjahresvergleich {prep['drivers'][0]} vs {prep['drivers'][1]}: Strecke um {c['align_m']:.1f} m "
              f"genau übereinander (Maßstab {c['scale']:.3f}) · Rundenlänge {c['length_a']:.0f} / "
              f"{c['length_b']:.0f} m")
        for msg in check_messages(c, prep["years"]):
            print(f"  ⚠ {msg}")
    else:
        prep = prepare(data, reel.get("drivers") or None, reel.get("part"))
    drv_a, drv_b = prep["drivers"]
    ca, cb = (team_color(t) for t in prep["teams"])
    same_team = prep["teams"][0] == prep["teams"][1]
    lap_a = prep["traces"][0]["lap_time"]
    t_a, t_b = (_fmt(tr["lap_time"]) for tr in prep["traces"])
    is_pole = reel.get("part") == "Q3"
    if prep.get("compare"):
        ya, yb = prep["years"]
        word = "faster" if prep["gap"] > 0 else "slower"
        hook = reel.get("hook") or f"Pole {ya} vs pole {yb} – {abs(prep['gap']):.3f} s {word}"
        result = reel.get("result") or f"{ya} pole {abs(prep['gap']):.3f} s {word}"
    else:
        hook = reel.get("hook") or ("Where pole was decided" if is_pole else "Head to head")
        result = reel.get("result") or f"{drv_a} {'on pole' if is_pole else 'ahead'} by {prep['gap']:.3f} s"
    with_replay = reel.get("replay", True)
    if not isinstance(with_replay, bool):
        raise ValueError("replay muss true oder false sein (klein geschrieben, ohne Anführungszeichen)")
    rep_from = replay_from_config(prep, reel, lap_a) if with_replay else None
    rep_to = min(rep_from + REPLAY_WINDOW_S, lap_a) if with_replay else None
    open_from = open_from_config(reel, rep_from, prep, lap_a)
    from stintlab.reels.chase3d import Scene, draw_scene
    # 3D mit denselben aufbereiteten Positionen wie die Karte (kein Hänger, kein Jojo)
    scene_data = prep.get("scene_data") or {**data, "location": {**data.get("location", {}), **prep["clean_location"]}}
    # Kamera hinter dem Auto, das an der Stelle des 3D-Anfangs ZURÜCKLIEGT – sonst ist
    # das andere Auto hinter der Kamera (Baku '26 vs '25: 1 s ≈ 90 m, nur ein Auto im Bild)
    # (gemessen in der Mitte des 3D-Anfangs – am Start mit open_at = 0 ist der Abstand dort noch 0)
    lead, chase = (drv_a, drv_b) if gap_at(prep, open_from + OPEN_S / 2) >= 0 else (drv_b, drv_a)
    scene = Scene(scene_data, lead, chase, t0s={d: lap["LapStart"] for d, lap in zip(prep["drivers"], prep["laps"])},
                  ref=drv_a)      # Maßstab + Streckenumriss immer aus A (beim Vorjahresvergleich: aktuelle Session)
    scene.configure(reel)
    scene.ghost = drv_b            # Vergleichsfahrer als „Geist“: halbtransparent
    # Zeitlupe als zweite 3D-Szene (Standard) statt Karten-Zoom (replay_view = "map")
    replay_view = reel.get("replay_view", "3d")
    if replay_view not in ("3d", "map"):
        raise ValueError('replay_view muss "3d" oder "map" sein')
    replay_3d = with_replay and replay_view == "3d"
    scene_r = scene
    if replay_3d:
        g_mid = gap_at(prep, rep_from + (rep_to - rep_from) / 2)
        lead_r, chase_r = (drv_a, drv_b) if g_mid >= 0 else (drv_b, drv_a)
        if (lead_r, chase_r) != (lead, chase):      # anderes Auto vorne → eigene Kamera-Reihenfolge
            scene_r = Scene(scene_data, lead_r, chase_r,
                            t0s={d: lap["LapStart"] for d, lap in zip(prep["drivers"], prep["laps"])}, ref=drv_a)
            scene_r.configure(reel)
            scene_r.ghost = drv_b

    # Titelbild: die Szene, in der beide Autos am nächsten beieinander sind (3D-Anfang oder Mitte
    # der Zeitlupe) – bei 1 s Abstand wäre das andere Auto sonst nur ein Punkt am Horizont
    from stintlab.reels.cover import make_cover, session_meta
    if prep.get("compare"):
        ya_, yb_ = (str(y)[2:] for y in prep["years"])
        c_title = f"Pole '{ya_} vs '{yb_}"
        c_sub = f"{drv_a} vs {drv_b} · {abs(prep['gap']):.3f} s {'faster' if prep['gap'] > 0 else 'slower'}"
    else:
        c_title, c_sub = f"{drv_a} vs {drv_b}", result
    shots = []
    if open_from is not None:
        shots.append((scene, open_from + OPEN_S / 2))
    if replay_3d:
        shots.append((scene_r, rep_from + (rep_to - rep_from) / 2))
    if shots:
        def spread(shot):
            sc, t = shot
            return float(np.linalg.norm(sc.pos(sc.a, t)[0] - sc.pos(sc.b, t)[0]))
        c_scene, c_t = min(shots, key=spread)
        make_cover(reel, path, c_scene, c_t, c_title, kicker="Ghost lap", sub=c_sub, meta=session_meta(data))

    paint = reel.get("paint", True)
    if not isinstance(paint, bool):
        raise ValueError("paint muss true oder false sein (klein geschrieben, ohne Anführungszeichen)")
    if paint and colors_too_close(ca, cb):      # 3D behält die Teamfarben (Scene hat eigene)
        ca, cb = COLORS["accent"], LOSS_COLOR

    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [resolve_font(), "DejaVu Sans"]   # Ersatz für →, ▲▼ (fehlen in Barlow)
    fig = plt.figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI, facecolor=COLORS["bg"])

    ta, xa, ya = prep["pos"][0]
    inside = (ta >= 0) & (ta <= lap_a)
    path_len = float(np.sum(np.hypot(np.diff(xa[inside]), np.diff(ya[inside]))))
    half = ZOOM_M * path_len / prep["res"]["length_m"] / 2        # unabhängig von der Einheit

    # ── Karte (Runde, Ergebnis), Zoom (Zeitlupe), Mini-Karte (Zeitlupe) ─────
    ax_map = fig.add_axes(MAP_BOX)
    ax_zoom = fig.add_axes(MAP_BOX)
    ax_mini = fig.add_axes([0.07, 0.66, 0.22, 0.13])
    zoom_aspect = (MAP_BOX[3] * HEIGHT_PX) / (MAP_BOX[2] * WIDTH_PX)
    layers = {}
    for key, ax, lw, dot_size, trail_w in (("map", ax_map, (10, 6), 240, 4), ("zoom", ax_zoom, (46, 38), 520, 7),
                                           ("mini", ax_mini, (4, 2), 30, 0)):
        ax.set_facecolor(COLORS["bg"])
        ax.set_aspect("auto" if key == "zoom" else "equal")
        ax.axis("off")
        ax.plot(xa, ya, color=COLORS["grid"], linewidth=lw[0], solid_capstyle="round", zorder=1)
        ax.plot(xa, ya, color=COLORS["plot"], linewidth=lw[1], solid_capstyle="round", zorder=2)
        trails = (_fading_trail(ax, ca, trail_w), _fading_trail(ax, cb, trail_w, same_team)) if trail_w else ()
        dots = (ax.scatter([], [], s=dot_size, color=ca, edgecolor="white", linewidth=1.5, zorder=5),
                ax.scatter([], [], s=dot_size, color=COLORS["bg"] if same_team else cb,
                           edgecolor=cb if same_team else "white", linewidth=2.5 if same_team else 1.5, zorder=4))
        layers[key] = (ax, trails, dots)
    ax_zoom.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax_zoom.transAxes, fill=False,
                                    edgecolor=COLORS["grid"], linewidth=1.2, zorder=10, clip_on=False))
    zoom_box, = ax_mini.plot([], [], color=COLORS["accent"], linewidth=1.2, zorder=6)

    # ── Abstandsgraph ────────────────────────────────────────────────────────
    res = dict(prep["res"])
    # Eingefrorene Messwerte: dort keinen erfundenen Abstand zeigen (Linie unterbrochen, Zahl „–“)
    holes = []
    for tr in prep["traces"]:
        for t0, t1 in tr.get("frozen", []):
            holes.append(tuple(float(np.interp(x, tr["t"], tr["frac"])) for x in (t0, t1)))
    in_hole = lambda f: any(f0 < f < f1 for f0, f1 in holes)
    res["delta"] = np.array([np.nan if in_hole(f) else d for f, d in zip(res["frac"], res["delta"])])
    km = res["frac"] * res["length_m"] / 1000
    ax_gap = fig.add_axes([0.10, 0.23, 0.80, 0.10])
    ax_gap.set_facecolor(COLORS["plot"])
    for side in ax_gap.spines.values():
        side.set_visible(False)
    ax_gap.tick_params(colors=COLORS["muted"], labelsize=8)
    ax_gap.axhline(0, color=COLORS["muted"], linewidth=0.8)
    lim = max(np.nanmax(np.abs(res["delta"])) * 1.2, 0.05)
    ax_gap.set_xlim(0, km[-1])
    ax_gap.set_ylim(-lim, lim)
    ax_gap.set_xticks([])
    at, afrac = prep["a_frac"]
    frac_of = lambda t: float(np.interp(t, at, afrac))
    replay_span = ax_gap.axvspan(frac_of(rep_from or 0.0) * km[-1], frac_of(rep_to or 0.0) * km[-1],
                                 color=COLORS["accent"], alpha=0.0, zorder=0)
    gap_line, = ax_gap.plot([], [], color=COLORS["text"], linewidth=1.6)

    # ── Wo gewonnen / verloren: Strecke färbt sich, Sektor-Bilanz ──────────
    pts = np.column_stack([xa[inside], ya[inside]])
    seg_frac = np.interp(ta[inside][:-1], at, afrac)
    painted = LineCollection(np.stack([pts[:-1], pts[1:]], axis=1), linewidths=6, capstyle="round",
                             zorder=2.5)
    ax_map.add_collection(painted)
    if paint:
        who, strength = gain_profile(seg_frac, res)
        seg_rgba = np.array([to_rgba(ca if w > 0 else cb, 0.3 + 0.7 * k) for w, k in zip(who, strength)])
    else:
        seg_rgba = np.zeros((len(seg_frac), 4))
    # Vorjahresvergleich mit rekonstruierter Runde (OpenF1 ohne Rundendaten, z. B. Baku 2025): B hat keine
    # Sektorzeiten → compare() setzt keine sector_marks → vorher keine Chips/Balken. Dann gelten die
    # Sektorgrenzen von A (offizielle Zeiten dieser Session); B's Sektorwerte kommen dort nur aus dem
    # Abstandsverlauf, nicht aus offiziellen Zeiten.
    if paint and not res.get("sector_marks"):
        tr_a = prep["traces"][0]
        if tr_a.get("sectors") and all(tr_a["sectors"]) and "frac" in tr_a:
            res["sector_marks"] = [float(np.interp(x, tr_a["t"], tr_a["frac"])) for x in np.cumsum(tr_a["sectors"][:2])]
            print(f"  ℹ Sektorgrenzen aus {drv_a} ({drv_b} ohne offizielle Sektorzeiten) – Sektorwerte aus dem Abstandsverlauf")
    gains = sector_gains(res) if paint else []
    sector_end = list(res.get("sector_marks") or []) + [1.0]
    chips = []
    for i, g in enumerate(gains):
        winner = drv_a if g >= 0 else drv_b
        chips.append(fig.text(0.2 + 0.3 * i, 0.80, f"S{i + 1}  {winner} +{abs(g):.2f}", ha="center",
                              va="center", fontsize=14, fontweight="bold", color=ca if g >= 0 else cb,
                              path_effects=[patheffects.withStroke(linewidth=3, foreground="black", alpha=0.7)]))
    paint_hint = fig.text(0.5, 0.772, "track colour = who was faster there" if paint else "", ha="center",
                          va="center", fontsize=10, color=COLORS["muted"])

    # ── Ergebnis als Sektor-Balken ──────────────────────────────────────────
    sector_view = len(gains) == 3
    ax_sec = fig.add_axes([0.14, 0.43, 0.72, 0.30])
    ax_sec.set_facecolor(COLORS["bg"])
    for side in ax_sec.spines.values():
        side.set_visible(False)
    ax_sec.tick_params(colors=COLORS["text"], labelsize=14, left=False, labelleft=False, length=0)
    ax_sec.axhline(0, color=COLORS["muted"], linewidth=1.2)
    sec_top = max([abs(g) for g in gains] + [0.05]) * 1.45
    ax_sec.set_ylim(-sec_top, sec_top)
    ax_sec.set_xlim(-0.6, 2.6)
    ax_sec.set_xticks([0, 1, 2], ["S1", "S2", "S3"])
    for lbl in ax_sec.get_xticklabels():
        lbl.set_fontweight("bold")
    sec_bars = ax_sec.bar([0, 1, 2], [0.0, 0.0, 0.0], width=0.55,
                          color=[ca if g >= 0 else cb for g in gains] or None)
    sec_vals = [ax_sec.text(i, 0, "", ha="center", fontsize=15, fontweight="bold",
                            color=ca if g >= 0 else cb) for i, g in enumerate(gains)]
    ax_sec.text(-0.55, sec_top * 0.95, f"{drv_a} faster", color=ca, fontsize=12, fontweight="bold", va="top")
    ax_sec.text(-0.55, -sec_top * 0.95, f"{drv_b} faster", color=cb, fontsize=12, fontweight="bold",
                va="bottom")
    sec_kicker = fig.text(0.5, 0.775, "WHERE IT WAS DECIDED", ha="center", va="center", fontsize=13,
                          fontweight="bold", color=COLORS["muted"])
    sum_txt = [fig.text(0.5, 0.36, "", ha="center", va="center", fontsize=22, fontweight="bold", color=ca),
               fig.text(0.5, 0.315, "", ha="center", va="center", fontsize=22, fontweight="bold", color=cb)]
    won_a = [f"S{i + 1}" for i, g in enumerate(gains) if g >= 0]
    won_b = [f"S{i + 1}" for i, g in enumerate(gains) if g < 0]
    sum_a = sum(g for g in gains if g >= 0)
    sum_b = -sum(g for g in gains if g < 0)

    # ── Frage an die Zuschauer ──────────────────────────────────────────────
    if prep.get("compare"):
        default_q = f"Which lap was better – '{str(prep['years'][0])[2:]} or '{str(prep['years'][1])[2:]}?"
    else:
        default_q = f"Where could {drv_b} have found {abs(prep['gap']):.2f} s?"
    question = reel.get("question", default_q)
    if not isinstance(question, str):
        raise ValueError('question muss ein Text sein, z. B. question = "Who had the better lap?" (oder "" = keine Frage)')
    ask_txt = [fig.text(0.5, 0.65, "YOUR TURN", ha="center", va="center", fontsize=13, fontweight="bold",
                        color=COLORS["muted"]),
               fig.text(0.5, 0.58, question, ha="center", va="center", fontsize=28 if len(question) < 32 else 22,
                        fontweight="bold", color=COLORS["text"]),
               fig.text(0.5, 0.52, "Tell us in the comments", ha="center", va="center", fontsize=20,
                        fontweight="bold", color=COLORS["accent"])]

    def draw_sectors(u: float) -> None:
        """Ergebnis: Balken wachsen nacheinander (erste 60 %), dann Summen."""
        grow = min(u / 0.6, 1.0)
        for i, (bar, g) in enumerate(zip(sec_bars, gains)):
            h = min(max(grow * 3 - i, 0.0), 1.0)
            h = h * h * (3 - 2 * h)
            bar.set_height(g * h)
            sec_vals[i].set_text(f"+{abs(g):.2f}" if h > 0.95 else "")
            off = sec_top * 0.06
            sec_vals[i].set_position((i, g + off if g >= 0 else g - off))
            sec_vals[i].set_va("bottom" if g >= 0 else "top")
        done = grow >= 1.0
        sum_txt[0].set_text(f"{drv_a} +{sum_a:.2f} s in {' + '.join(won_a)}" if done and won_a else "")
        sum_txt[1].set_text(f"{drv_b} +{sum_b:.2f} s in {' + '.join(won_b)}" if done and won_b else "")

    def show_paint(frac_now: float | None) -> None:
        """Färbung bis frac_now (None = ganze Runde), Chips der fertigen Sektoren mit kurzem „Pop“."""
        f = 1.0 if frac_now is None else frac_now
        cols = seg_rgba.copy()
        cols[seg_frac > f, 3] = 0.0
        painted.set_color(cols)
        painted.set_visible(paint)
        paint_hint.set_visible(paint)
        for i, chip in enumerate(chips):
            done = f >= sector_end[i] - 1e-6
            chip.set_visible(done)
            if done:
                pop = 0.0 if frac_now is None else max(0.0, 1.0 - (f - sector_end[i]) / 0.04)
                chip.set_fontsize(14 * (1.0 + 0.4 * pop))
    cursor = ax_gap.axvline(0, color=COLORS["accent"], linewidth=1.2, visible=False)
    gap_fills = []

    # ── 3D-Anfang ────────────────────────────────────────────────────────────
    ax_3d = fig.add_axes([0, 0, 1, 1], zorder=-1)
    hook_1, _, hook_2 = hook.partition(" – ")
    open_txt = [fig.text(0.5, 0.925, hook_1, ha="center", va="center", fontsize=30 if len(hook_1) < 28 else 24,
                         fontweight="bold", color=COLORS["text"]),
                fig.text(0.5, 0.878, hook_2, ha="center", va="center", fontsize=30 if len(hook_2) < 28 else 24,
                         fontweight="bold", color=COLORS["text"]),     # weiß: Lila auf Dunkel las sich schlecht
                fig.text(0.5, 0.835 if hook_2 else 0.878, "POLE LAP · Q3" if is_pole else "FASTEST LAPS",
                         ha="center", va="center", fontsize=14, fontweight="bold", color=COLORS["muted"])]
    open_gap = fig.text(0.5, 0.11, "", ha="center", va="center", fontsize=44, fontweight="bold",
                        color=COLORS["text"])
    open_sub = fig.text(0.5, 0.07, "", ha="center", va="center", fontsize=14, color=COLORS["muted"])
    open_txt += [open_gap, open_sub]
    for _tx in open_txt:       # dunkle Kontur: bei Tageslicht steht die Schrift auf hellem Himmel
        _tx.set_path_effects([patheffects.withStroke(linewidth=4, foreground="black", alpha=0.75)])
    from stintlab.reels.chase3d import MiniMap
    minimap = MiniMap(fig, scene, sector_fracs=prep["res"].get("sector_marks"))
    # eigene Minikarte für die Zeitlupe, tiefer gesetzt – oben stehen Abstand, Tempo und Hinweis
    minimap_r = MiniMap(fig, scene_r, box=(0.05, 0.47, 0.26, 0.19), sector_fracs=prep["res"].get("sector_marks"))

    # ── Texte ────────────────────────────────────────────────────────────────
    txt_big = fig.text(0.5, 0.88, "", ha="center", va="center", fontsize=40, fontweight="bold")
    txt_sub = fig.text(0.5, 0.835, "", ha="center", va="center", fontsize=15, color=COLORS["muted"])
    # Zeitlupe: beide Geschwindigkeiten live + optionale Zeile aus der post.toml (replay_note)
    txt_speed_a = fig.text(0.48, 0.805, "", ha="right", va="center", fontsize=15, fontweight="bold", color=ca)
    txt_speed_b = fig.text(0.52, 0.805, "", ha="left", va="center", fontsize=15, fontweight="bold", color=cb)
    txt_note = fig.text(0.5, 0.385, reel.get("replay_note", ""), ha="center", va="center", fontsize=17,
                        fontweight="bold", color=COLORS["text"], zorder=12,
                        bbox={"boxstyle": "round,pad=0.4", "facecolor": COLORS["bg"], "edgecolor": "none", "alpha": 0.85})
    speed_of = [lambda t, tr=tr: float(np.interp(t, tr["t"], tr["v"])) for tr in prep["traces"]]
    txt_tag = fig.text(0.925, 0.785, "", ha="right", va="top", fontsize=10, fontweight="bold",
                       color=COLORS["accent"])
    txt_leg_a = fig.text(0.48, 0.345, f"● {drv_a}  {t_a}", ha="right", va="center", fontsize=12,
                         fontweight="bold", color=ca)
    txt_leg_b = fig.text(0.52, 0.345, f"{'○' if same_team else '●'} {drv_b}  {t_b}", ha="left", va="center",
                         fontsize=12, fontweight="bold", color=cb)
    txt_center = fig.text(0.5, 0.58, "", ha="center", va="center", fontsize=56, fontweight="bold",
                          color=COLORS["accent"])
    txt_center_sub = fig.text(0.5, 0.52, "", ha="center", va="center", fontsize=18, color=COLORS["muted"])
    fig.text(0.94, 0.965, "STINTLAB", ha="right", va="center", fontsize=11, fontweight="bold", color=COLORS["accent"],
             path_effects=[patheffects.withStroke(linewidth=3, foreground="black", alpha=0.6)])
    txt_data = fig.text(0.06, 0.215, "Data: OpenF1 · positions ~4 Hz", ha="left", va="top", fontsize=8,
                        color=COLORS["muted"])

    in_replay = [False]
    for _tx in (txt_big, txt_sub, txt_speed_a, txt_speed_b, txt_tag):   # lesbar auch über der 3D-Szene
        _tx.set_path_effects([patheffects.withStroke(linewidth=3.5, foreground="black", alpha=0.7)])

    def visible(*shown) -> None:
        for art in (ax_map, ax_zoom, ax_mini, ax_gap, ax_3d, *open_txt, txt_leg_a, txt_leg_b, txt_tag,
                    txt_speed_a, txt_speed_b, txt_note):
            art.set_visible(art in shown)
        txt_note.set_visible(txt_note in shown and bool(txt_note.get_text()))
        minimap.set_visible(ax_3d in shown and not in_replay[0])
        minimap_r.set_visible(ax_3d in shown and in_replay[0])
        txt_data.set_visible(ax_3d not in shown)   # über der 3D-Strecke würde die Zeile stören
        for chip in chips:
            chip.set_visible(False)
        paint_hint.set_visible(False)
        for art in (ax_sec, sec_kicker, *sum_txt, *ask_txt):
            art.set_visible(False)

    def place(key: str, t: float) -> list:
        ax, trails, dots = layers[key]
        now = []
        for i, p in enumerate(prep["pos"]):
            x, y = _position(p, t)
            now.append((float(x[0]), float(y[0])))
            dots[i].set_offsets([now[-1]])
            if trails:
                _update_trail(trails[i], p, t)
        return now

    def draw_gap(t: float, full: bool) -> None:
        nonlocal gap_fills
        frac = 1.0 if full else frac_of(t)
        upto = res["frac"] <= frac
        gap_line.set_data(km[upto], res["delta"][upto])
        for f in gap_fills:
            f.remove()
        gap_fills = [ax_gap.fill_between(km[upto], res["delta"][upto], 0, where=res["delta"][upto] >= 0,
                                         color=ca, alpha=0.35, linewidth=0),
                     ax_gap.fill_between(km[upto], res["delta"][upto], 0, where=res["delta"][upto] < 0,
                                         color=cb, alpha=0.35, linewidth=0)]

    def running_gap(t: float) -> None:
        if in_hole(frac_of(t)):
            txt_big.set_text("–")
            txt_sub.set_text("no data here")
            return
        g = gap_at(prep, t)
        txt_big.set_text(f"{abs(g):.2f} s")
        txt_big.set_fontsize(40)
        txt_big.set_color(ca if g >= 0 else cb)
        txt_sub.set_text(f"{drv_a if g >= 0 else drv_b} ahead")

    def draw(phase: str, t: float) -> None:
        txt_center.set_text("")
        txt_center_sub.set_text("")
        if phase == "open":
            visible(ax_3d, *open_txt)
            txt_big.set_text("")
            txt_sub.set_text("")
            draw_scene(ax_3d, scene, t)
            minimap.update(t)
            g = gap_at(prep, t)      # Abstand aus der Telemetrie, wie im Rest des Reels
            open_gap.set_text(f"{abs(g):.2f} s")
            # Wer vorne liegt, wechselt in der Runde – der Text muss mitgehen
            ahead, behind = (drv_a, drv_b) if g >= 0 else (drv_b, drv_a)
            open_gap.set_color(ca if g >= 0 else cb)
            open_sub.set_text(f"{behind} behind {ahead} · same lap time")
            return
        if phase == "lap":
            visible(ax_map, ax_gap, txt_leg_a, txt_leg_b)
            place("map", t)
            running_gap(t)
            draw_gap(t, full=False)
            show_paint(frac_of(t))
            cursor.set_visible(False)
            replay_span.set_alpha(0.0)
            return
        if phase == "replay" and replay_3d:
            in_replay[0] = True
            visible(ax_3d, txt_tag, txt_speed_a, txt_speed_b, txt_note)
            in_replay[0] = False
            draw_scene(ax_3d, scene_r, t)
            minimap_r.update(t)
            txt_speed_a.set_text(f"{drv_a}  {speed_of[0](t):.0f} km/h")
            txt_speed_b.set_text(f"{speed_of[1](t):.0f} km/h  {drv_b}")
            txt_note.set_position((0.5, 0.765))
            running_gap(t)
            txt_tag.set_text("SLOW-MO")
            txt_tag.set_position((0.06, 0.965))
            txt_tag.set_ha("left")
            txt_tag.set_va("center")
            return
        if phase == "replay":
            visible(ax_zoom, ax_mini, ax_gap, txt_leg_a, txt_leg_b, txt_tag, txt_speed_a, txt_speed_b, txt_note)
            txt_speed_a.set_text(f"{drv_a}  {speed_of[0](t):.0f} km/h")
            txt_speed_b.set_text(f"{speed_of[1](t):.0f} km/h  {drv_b}")
            now = place("zoom", t)
            place("mini", t)
            cx, cy = (now[0][0] + now[1][0]) / 2, (now[0][1] + now[1][1]) / 2
            hy = half * zoom_aspect
            ax_zoom.set_xlim(cx - half, cx + half)
            ax_zoom.set_ylim(cy - hy, cy + hy)
            zoom_box.set_data([cx - half, cx + half, cx + half, cx - half, cx - half],
                              [cy - hy, cy - hy, cy + hy, cy + hy, cy - hy])
            running_gap(t)
            txt_tag.set_text(f"SLOW-MO · ZOOM {ZOOM_M:.0f} m")
            draw_gap(t, full=True)
            cursor.set_xdata([frac_of(t) * km[-1]] * 2)
            cursor.set_visible(True)
            replay_span.set_alpha(0.18)
            return
        if phase == "ask":
            visible()
            txt_big.set_text("")
            txt_sub.set_text("")
            for art in ask_txt:
                art.set_visible(True)
            return
        if phase == "result" and sector_view:
            visible()
            for art in (ax_sec, sec_kicker, *sum_txt):
                art.set_visible(True)
            draw_sectors(t)            # hier ist t der Fortschritt 0–1 (siehe unten)
            txt_big.set_text(result.upper())
            txt_big.set_fontsize(30)
            txt_big.set_color(ca)
            txt_sub.set_text(f"{drv_a} {t_a}  ·  {drv_b} {t_b}")
            return
        # result (ohne Sektoren: Karte wie früher)
        visible(ax_map, ax_gap, txt_leg_a, txt_leg_b)
        place("map", t)
        draw_gap(t, full=True)
        show_paint(None)
        cursor.set_visible(False)
        replay_span.set_alpha(0.0)
        txt_big.set_text(result.upper())
        txt_big.set_fontsize(30)
        txt_big.set_color(ca)
        txt_sub.set_text(f"{drv_a} {t_a}  ·  {drv_b} {t_b}")

    matplotlib.rcParams["animation.ffmpeg_path"] = _ffmpeg()
    writer = animation.FFMpegWriter(fps=FPS, codec="libx264",
                                    extra_args=["-pix_fmt", "yuv420p", "-crf", "20"])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = frame_times(lap_a, rep_from, open_from, reel.get("order", "classic"))
    if sector_view:                    # Ergebnis-Bilder bekommen ihren Fortschritt 0–1 statt der Rundenzeit
        n_res = sum(1 for ph, _ in frames if ph == "result")
        k = iter(range(n_res))
        frames = [(ph, next(k) / max(n_res - 1, 1)) if ph == "result" else (ph, t) for ph, t in frames]
    if question:
        frames += [("ask", 0.0)] * int(ASK_S * FPS)
    step = max(len(frames) // 10, 1)
    with writer.saving(fig, str(path), dpi=DPI):
        last = None
        for i, (phase, t) in enumerate(frames):
            key = (phase, round(t, 4))
            if key != last:            # Standbilder nur einmal zeichnen
                draw(phase, t)
                last = key
            writer.grab_frame(facecolor=COLORS["bg"])
            if i % step == 0:
                print(f"  {100 * i // len(frames):3d} %  ({i}/{len(frames)} Bilder)", flush=True)
    plt.close(fig)
    return path


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("Für Reels fehlt ffmpeg: python -m pip install imageio-ffmpeg") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()
