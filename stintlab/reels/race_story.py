"""Reel „Race Story“: wie ein Vorsprung entsteht, verschwindet und hält.

ABLAUF (1080 × 1920, 9:16, 60 Bilder/s, ~20 s):
  1. Anfang 3D (3,5 s):  Verfolgerkamera (chase3d) in der Zielrunde, Haken-Text groß
                         oben, laufender Abstand unten. Ersetzt den schwarzen
                         Titel-Screen: Baku 2026 wischten dort ~50 % in der
                         ersten Sekunde weg (Instagram „Übersprungen“ 52 %).
  2. Karte (3,5 s):      eine ganze Runde (track_lap, Standard: die Runde vor dem
                         ersten Safety Car) auf der Streckenkarte, ~20-fach.
                         Beide Autos zur SELBEN Uhrzeit – die markierte Strecke
                         zwischen ihnen ist der Abstand.
  3. Graph (4 s):      Abstand Runde für Runde; beim Safety Car blitzt es gelb,
                         die Zahl fällt zusammen
  4. Graph-Zoom (2 s): die Achsen zoomen weich auf die Runden nach dem SC,
                         damit die Zehntel sichtbar werden
  5. Zielrunde (6 s):    die halbe letzte Runde im mitfahrenden Zoom – Zeitraffer,
                         der zum Ziel weich auf Echtzeit abbremst, Zoom zieht mit zu
  6. Auflösung (1,5 s) – kein Logo-Screen mehr: dort fiel die Zuschauerkurve
     noch einmal ab, und ohne ihn läuft das Reel direkt in die Schleife

LAUFENDER ABSTAND AUF DER KARTE: Zu jedem Zeitpunkt t steht A an Punkt P.
Der Abstand ist die Zeit, bis B denselben Punkt P erreicht. Das ist genau
das, was die Zeitnahme an jeder Messstelle macht – nur hier an jedem Punkt.
Er kommt aus den Positionsdaten, nicht aus date_start (das ist einige
Zehntel ungenau). Am Ziel zeigt das Video den OFFIZIELLEN Abstand.

MASSSTAB: OpenF1 location hat keine dokumentierte Einheit. Meter pro
Einheit werden aus der Runde berechnet: Rundenlänge aus der Geschwindigkeit
(car_data, wie bei der Telemetrie-Slide) geteilt durch die Weglänge der
Positionspunkte.

ZIELLINIE: Median der Positionen von A zu Beginn jeder Runde. Der einzelne
date_start ist ungenau, der Median über viele Runden deutlich weniger.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
from matplotlib import animation
from matplotlib import pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import to_rgba

from stintlab import openf1
from stintlab.analyses.telemetry import distance, lap_trace
from stintlab.race_control import neutral_phases
from stintlab.reels.gap_chase import gap_series, neutral_blocks, pick_pair
from stintlab.reels.ghost_lap import _ffmpeg, needs_rotation
from stintlab.session import _parse
from stintlab.trackpos import retime
from stintlab.style import COLORS, NEUTRAL_STYLE, neutral_legend, resolve_font, team_color

WIDTH_PX, HEIGHT_PX, DPI, FPS = 1080, 1920, 150, 60
OPEN_S, MAP_S, CHART_S, CHART_ZOOM_S, FINAL_S, RESULT_S = 3.5, 3.5, 4.0, 2.0, 6.0, 1.5
OPEN_END_MIN_S = 8.0    # 3D-Anfang endet mindestens so lange vor dem Ziel (Ziel nicht vorwegnehmen)
FINAL_FRACTION = 0.5    # Zielrunde: so viel der Runde vor dem Ziel (Standard, final_window überschreibt)
FINAL_AFTER_S = 1.0     # echte Sekunden nach dem Ziel
FINAL_END_SPEED = 1.0   # an der Ziellinie: Echtzeit
ZOOM_PER_SPEED_M = 110.0          # Zoombreite ∝ Tempo → Strecke bewegt sich immer gleich schnell übers Bild
ZOOM_MIN_M, ZOOM_MAX_M = 150.0, 1400.0
TRACK_LW_AT_200M = 46.0
MAX_MATCH_M = 40.0      # B muss P auf so viele Meter treffen, sonst kein Wert
SC_YELLOW = "#f5c518"
MAP_BOX = [0.06, 0.30, 0.88, 0.48]
CHART_BOX = [0.14, 0.30, 0.78, 0.44]


# ── Positionen ───────────────────────────────────────────────────────────────

class Track:
    """Alle Positionen eines Fahrers als weiche Kurve über die Zeit.

    Zeit in Sekunden ab t0. Steigungen werden einmal vorberechnet – bei
    ~37 000 Punkten pro Rennen wäre das pro Bild zu langsam.
    """

    def __init__(self, location: list[dict], t0, rotate: bool | None = None):
        pts = []
        for p in location:
            when = _parse(p.get("date"))
            if when is None or p.get("x") is None or p.get("y") is None:
                continue
            pts.append(((when - t0).total_seconds(), float(p["x"]), float(p["y"])))
        pts.sort()
        pts = [p for i, p in enumerate(pts) if i == 0 or p[0] > pts[i - 1][0]]
        if len(pts) < 10:
            raise ValueError("zu wenige Positionsdaten")
        arr = np.array(pts)
        # Zeitstempel glätten, hängende Punkte raus (siehe stintlab.trackpos) – sonst „Jojo“
        self.t, x, y = retime(arr[:, 0], arr[:, 1], arr[:, 2])
        self.rotate = needs_rotation(x, y) if rotate is None else rotate
        self.x, self.y = (y, -x) if self.rotate else (x, y)
        self.mx, self.my = np.gradient(self.x, self.t), np.gradient(self.y, self.t)

    def at(self, t) -> tuple[np.ndarray, np.ndarray]:
        t = np.clip(np.atleast_1d(np.asarray(t, dtype=float)), self.t[0], self.t[-1])
        i = np.clip(np.searchsorted(self.t, t) - 1, 0, len(self.t) - 2)
        h = self.t[i + 1] - self.t[i]
        s = (t - self.t[i]) / h
        h00, h10 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s
        h01, h11 = -2 * s**3 + 3 * s**2, s**3 - s**2
        return (h00 * self.x[i] + h10 * h * self.mx[i] + h01 * self.x[i + 1] + h11 * h * self.mx[i + 1],
                h00 * self.y[i] + h10 * h * self.my[i] + h01 * self.y[i + 1] + h11 * h * self.my[i + 1])

    def path_length(self, t0: float, t1: float, n: int = 400) -> float:
        if t1 <= t0:
            return 0.0
        x, y = self.at(np.linspace(t0, t1, n))
        return float(np.sum(np.hypot(np.diff(x), np.diff(y))))


def live_gap(ta: Track, tb: Track, t: float, max_gap: float, max_dist: float) -> float:
    """Zeit, bis B den Punkt erreicht, an dem A zur Zeit t steht (NaN, wenn
    B ihn innerhalb von max_gap Sekunden nicht auf max_dist genau trifft)."""
    px, py = ta.at(t)
    ts = t + np.arange(0.0, max_gap, 0.05)
    bx, by = tb.at(ts)
    d = np.hypot(bx - px[0], by - py[0])
    i = int(np.argmin(d))
    fine = np.linspace(ts[max(i - 1, 0)], ts[min(i + 1, len(ts) - 1)], 101)
    fx, fy = tb.at(fine)
    fd = np.hypot(fx - px[0], fy - py[0])
    j = int(np.argmin(fd))
    return float(fine[j] - t) if fd[j] <= max_dist else float("nan")


def smooth(values: np.ndarray, width: int = 7) -> np.ndarray:
    """Gleitender Mittelwert, der NaN überspringt (gegen Zittern der Zahl)."""
    out = np.full(len(values), np.nan)
    half = width // 2
    for i in range(len(values)):
        win = values[max(i - half, 0): i + half + 1]
        win = win[~np.isnan(win)]
        if len(win):
            out[i] = win.mean()
    return out


def lap_window(data: dict, drv: str, lap: int, t0) -> tuple[float, float]:
    """(Beginn, Ende) von Runde `lap` des Fahrers in Sekunden ab t0."""
    ends = data.get("lap_ends", {}).get(drv, {})
    if lap not in ends:
        raise ValueError(f"{drv}: Runde {lap} nicht gefunden")
    end = (ends[lap] - t0).total_seconds()
    row = next((l for l in data.get("laps", []) if l["Driver"] == drv and l.get("LapNumber") == lap), {})
    if row.get("LapStart") is not None:
        return (row["LapStart"] - t0).total_seconds(), end
    if lap - 1 in ends:
        return (ends[lap - 1] - t0).total_seconds(), end
    if row.get("LapTime"):
        return end - float(row["LapTime"]), end
    # Runde 1 im Rennen hat oft weder Beginn noch Zeit
    times = sorted(float(l["LapTime"]) for l in data.get("laps", []) if l["Driver"] == drv and l.get("LapTime"))
    return end - 1.1 * (times[len(times) // 2] if times else 100.0), end


def default_track_lap(data: dict, x: np.ndarray, y: np.ndarray) -> int:
    """Runde vor dem ersten SC/VSC – sonst die Runde mit dem größten Abstand."""
    blocks = neutral_blocks(data.get("race_control", []), int(x[0]), int(x[-1]))
    if blocks and blocks[0][0] > int(x[0]):
        return int(blocks[0][0] - 1)
    return int(x[int(np.argmax(y))])


def finish_point(data: dict, drv: str, track: Track, t0) -> tuple[float, float]:
    xs, ys = [], []
    for n, end in data.get("lap_ends", {}).get(drv, {}).items():
        x, y = track.at((end - t0).total_seconds())
        xs.append(x[0])
        ys.append(y[0])
    if not xs:
        raise ValueError(f"{drv}: keine Rundenenden")
    return float(np.median(xs)), float(np.median(ys))


def crossing_time(track: Track, point: tuple[float, float], t_from: float, t_to: float) -> float:
    ts = np.arange(t_from, t_to, 0.01)
    x, y = track.at(ts)
    return float(ts[int(np.argmin(np.hypot(x - point[0], y - point[1])))])


def reference_lap(data: dict, drv: str) -> dict:
    """Schnellste Runde mit Beginn und Zeit – für Maßstab und Streckenumriss.
    (Runde 1 hat im Rennen oft keinen Beginn, SC-Runden sind unnötig lang.)"""
    rows = [l for l in data.get("laps", []) if l["Driver"] == drv and l.get("LapStart") is not None
            and l.get("LapTime") and not l.get("IsPitOutLap")]
    if not rows:
        raise ValueError(f"{drv}: keine Runde mit Beginn und Zeit")
    return min(rows, key=lambda l: float(l["LapTime"]))


def units_per_metre(data: dict, drv: str, row: dict, track: Track, t0) -> float:
    car = data.get("car_data", {}).get(drv)
    if car is None:
        car = openf1.cached_fetch_driver("car_data", data["session_key"], data["numbers"][drv])
    t, v = lap_trace(car, row)
    start = (row["LapStart"] - t0).total_seconds()
    return track.path_length(start, start + float(row["LapTime"]), n=2000) / float(distance(t, v)[-1])


# ── Vorbereitung (ohne Zeichnen, testbar) ────────────────────────────────────

def prepare(data: dict, reel: dict) -> dict:
    a, b = pick_pair(data, reel.get("drivers") or None)
    x, y = gap_series(data, a, b, tuple(reel["laps"]) if reel.get("laps") else None, reel.get("skip"))
    blocks = neutral_blocks(data.get("race_control", []), int(x[0]), int(x[-1]))
    track_lap = int(reel.get("track_lap") or default_track_lap(data, x, y))
    before = y[x < blocks[0][0]] if blocks else y
    peak = float(before.max() if len(before) else y.max())

    t0 = data["lap_ends"][a][min(data["lap_ends"][a])]
    locs = []
    for d in (a, b):
        loc = data.get("location", {}).get(d)
        if loc is None:
            loc = openf1.cached_fetch_driver("location", data["session_key"], data["numbers"][d])
        locs.append(loc)
    ta = Track(locs[0], t0)
    tb = Track(locs[1], t0, rotate=ta.rotate)

    win = lap_window(data, a, track_lap, t0)
    ref = reference_lap(data, a)
    ref_start = (ref["LapStart"] - t0).total_seconds()
    ref_win = (ref_start, ref_start + float(ref["LapTime"]))
    scale = units_per_metre(data, a, ref, ta, t0)
    finish = finish_point(data, a, ta, t0)
    last_lap = max(data["lap_ends"][a])
    last_start, last_end = lap_window(data, a, last_lap, t0)
    t_finish = crossing_time(ta, finish, last_end - 8.0, last_end + 8.0)
    window = float(reel.get("final_window") or FINAL_FRACTION * float(ref["LapTime"]))
    fin_times, fin_speed, fin_zoom = final_timeline(t_finish, window)
    final_win = (fin_times[0], fin_times[-1])

    max_gap = float(np.nanmax(np.abs(y))) + 5.0
    max_dist = MAX_MATCH_M * scale
    map_times = np.linspace(*win, int(MAP_S * FPS))
    map_gap = smooth(np.array([live_gap(ta, tb, t, max_gap, max_dist) for t in map_times]))
    fin_gap = smooth(np.array([live_gap(ta, tb, t, 3.0, max_dist) for t in fin_times]))

    from stintlab.reels.chase3d import Scene   # hier importiert: chase3d nutzt Track aus diesem Modul
    scene = Scene(data, a, b)
    if reel.get("open_at") is not None:
        t_open = t_finish - float(reel["open_at"])
    else:
        t_open = pick_open_start(ta, tb, last_start, t_finish, max_dist)
    open_times = t_open + np.arange(int(OPEN_S * FPS)) / FPS

    phases = neutral_phases(data.get("race_control", []), int(x[0]), int(x[-1]))
    return {"a": a, "b": b, "x": x, "y": y, "blocks": blocks, "phases": phases, "peak": peak, "scene": scene,
            "open_times": open_times,
            "final": float(y[-1]), "track_lap": track_lap, "ta": ta, "tb": tb,
            "win": win, "ref_win": ref_win, "final_win": final_win, "t_finish": t_finish, "finish": finish,
            "scale": scale, "map_times": map_times, "map_gap": map_gap,
            "fin_times": fin_times, "fin_gap": fin_gap,
            "fin_speed": fin_speed, "fin_zoom": fin_zoom}


def pick_open_start(ta: Track, tb: Track, lap_start: float, t_finish: float, max_dist: float) -> float:
    """Beginn des 3D-Anfangs: das OPEN_S-Fenster der Zielrunde mit dem kleinsten
    Abstand – spannend, aber mindestens OPEN_END_MIN_S vor dem Ziel."""
    latest = t_finish - OPEN_END_MIN_S - OPEN_S
    starts = np.arange(lap_start, max(latest, lap_start) + 1e-9, 1.0)
    if len(starts) == 0:
        return max(lap_start, latest)
    probe = np.arange(lap_start, latest + OPEN_S + 1e-9, 0.5)
    g = np.array([live_gap(ta, tb, t, 5.0, max_dist) for t in probe])
    score = []
    for s0 in starts:
        w = g[(probe >= s0) & (probe <= s0 + OPEN_S)]
        w = w[~np.isnan(w)]
        score.append(w.mean() if len(w) else np.inf)
    return float(starts[int(np.argmin(score))])


def _report(prep: dict) -> None:
    """Plausibilität: Positionsdaten gegen Zieldurchfahrten und offizielles Ergebnis."""
    lap = prep["track_lap"]
    lap_gaps = dict(zip(prep["x"].astype(int), prep["y"]))
    g = prep["map_gap"]
    print(f"  Race Story: Maßstab {prep['scale']:.2f} Einheiten/m · Karte Runde {lap}")
    print(f"    laufender Abstand Runde {lap}: {np.nanmin(g):.2f}–{np.nanmax(g):.2f} s "
          f"(Zieldurchfahrten: Runde {lap - 1} {lap_gaps.get(lap - 1, float('nan')):.2f} s, "
          f"Runde {lap} {lap_gaps.get(lap, float('nan')):.2f} s) · fehlend {np.isnan(g).mean():.0%}")
    before = prep["fin_gap"][prep["fin_times"] <= prep["t_finish"]]
    at_line = before[~np.isnan(before)][-5:]
    if len(at_line):
        diff = float(np.mean(at_line)) - prep["final"]
        mark = "⚠" if abs(diff) > 0.1 else "ℹ"
        print(f"  {mark} Ziel: Positionsdaten {np.mean(at_line):.3f} s · offiziell {prep['final']:.3f} s")


def final_timeline(t_finish: float, window: float, duration: float = FINAL_S, fps: int = FPS,
                   after: float = FINAL_AFTER_S, v_end: float = FINAL_END_SPEED):
    """Zeiten, Tempo und Zoombreite der Zielrunde – mit Zeitraffer, der zum
    Ziel hin weich auf Echtzeit abbremst.

    Tempo v(u) = v_end + (v0 − v_end)·(1 − u)², u = 0…1 über das Video.
    v0 wird so gewählt, dass genau `window` + `after` echte Sekunden in
    `duration` Video-Sekunden passen. Baku (halbe Runde ≈ 52 s in 8 s):
    Start ~17-fach, Ziel 1-fach.
    """
    total = window + after
    v0 = max(3 * (total / duration - v_end) + v_end, v_end)
    u = np.linspace(0.0, 1.0, int(duration * fps))
    real = duration * (v_end * u + (v0 - v_end) * (1 - (1 - u) ** 3) / 3)
    real *= total / real[-1]
    speed = v_end + (v0 - v_end) * (1 - u) ** 2
    zoom = np.clip(ZOOM_PER_SPEED_M * speed, ZOOM_MIN_M, ZOOM_MAX_M)
    return t_finish - window + real, speed, zoom


def chart_frames(x: np.ndarray, blocks: list[tuple[int, int]]) -> list[tuple[str, float, float]]:
    """[(Phase, Rundenwert, Zoom-Fortschritt 0–1)] für Graph und Graph-Zoom.

    Ohne SC gibt es keinen Zoom – der Graph läuft über beide Zeiten."""
    n1, n2 = int(CHART_S * FPS), int(CHART_ZOOM_S * FPS)
    if not blocks:
        n = n1 + n2
        return [("chart", x[0] + (x[-1] - x[0]) * i / (n - 1), 0.0) for i in range(n)]
    split = min(blocks[-1][1] + 1.0, x[-1])
    out = [("chart", x[0] + (split - x[0]) * i / (n1 - 1), 0.0) for i in range(n1)]
    for i in range(n2):
        s = i / (n2 - 1)
        out.append(("chart", split + (x[-1] - split) * s, s * s * (3 - 2 * s)))
    return out


def frame_list(prep: dict) -> list[tuple]:
    frames = [("open", i, 0.0) for i in range(len(prep["open_times"]))]
    frames += [("map", i, 0.0) for i in range(len(prep["map_times"]))]
    frames += chart_frames(prep["x"], prep["blocks"])
    frames += [("final", i, 0.0) for i in range(len(prep["fin_times"]))]
    frames += [("result", len(prep["fin_times"]) - 1, 0.0)] * int(RESULT_S * FPS)
    return frames


def _fmt_gap(g: float) -> str:
    if np.isnan(g):
        return "–"
    return f"{g:.1f} s" if abs(g) >= 1 else f"{g:.2f} s"


# ── Video ────────────────────────────────────────────────────────────────────

def _trail(ax, color: str, width: float) -> LineCollection:
    lc = LineCollection([], linewidths=width, capstyle="round", zorder=4)
    lc.base_rgba = to_rgba(color)
    ax.add_collection(lc)
    return lc


def _set_trail(lc: LineCollection, track: Track, t: float, length: float) -> None:
    x, y = track.at(np.linspace(t - length, t, 24))
    pts = np.column_stack([x, y])
    r, g, b, _ = lc.base_rgba
    lc.set_segments(np.stack([pts[:-1], pts[1:]], axis=1))
    lc.set_color([(r, g, b, al) for al in np.linspace(0.0, 0.8, 23)])


def render_race_story(data: dict, reel: dict, path: Path) -> Path:
    prep = prepare(data, reel)
    a, b, x, y = prep["a"], prep["b"], prep["x"], prep["y"]
    _report(prep)
    ta, tb, scale = prep["ta"], prep["tb"], prep["scale"]
    teams = data.get("teams", {})
    ca, cb = team_color(teams.get(a)), team_color(teams.get(b))
    if ca == cb:
        cb = COLORS["text"]
    final, peak = prep["final"], prep["peak"]
    phases = prep["phases"]
    first_kind = phases[0][2] if phases else "SC"
    first_name = {"SC": "safety car", "VSC": "virtual safety car", "RED": "red flag"}[first_kind]
    hook = reel.get("hook") or f"{a}'s lead – and what the {first_name} did to it"
    result = reel.get("result") or f"{a} holds on by {final:.3f} s"
    blocks = prep["blocks"]

    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [resolve_font()]
    fig = plt.figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI, facecolor=COLORS["bg"])

    # Streckenumriss = schnellste Runde von A
    outline = ta.at(np.linspace(*prep["ref_win"], 1500))
    finish = prep["finish"]

    # ── Karte, Zoom (Zielrunde), Mini-Karte ──────────────────────────────────
    ax_map = fig.add_axes(MAP_BOX)
    ax_zoom = fig.add_axes(MAP_BOX)
    ax_mini = fig.add_axes([0.07, 0.62, 0.22, 0.14])
    zoom_aspect = (MAP_BOX[3] * HEIGHT_PX) / (MAP_BOX[2] * WIDTH_PX)
    layers, track_lines = {}, {}
    for key, ax, lw, dot, trail_w in (("map", ax_map, (10, 6), 240, 4), ("zoom", ax_zoom, (46, 38), 520, 7),
                                      ("mini", ax_mini, (4, 2), 30, 0)):
        ax.set_facecolor(COLORS["bg"])
        ax.set_aspect("auto" if key == "zoom" else "equal")
        ax.axis("off")
        track_lines[key] = (
            ax.plot(*outline, color=COLORS["grid"], linewidth=lw[0], solid_capstyle="round", zorder=1)[0],
            ax.plot(*outline, color=COLORS["plot"], linewidth=lw[1], solid_capstyle="round", zorder=2)[0])
        trails = (_trail(ax, ca, trail_w), _trail(ax, cb, trail_w)) if trail_w else ()
        dots = (ax.scatter([], [], s=dot, color=ca, edgecolor="white", linewidth=1.5, zorder=6),
                ax.scatter([], [], s=dot, color=cb, edgecolor="white", linewidth=1.5, zorder=5))
        layers[key] = (ax, trails, dots)
    ax_zoom.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax_zoom.transAxes, fill=False,
                                    edgecolor=COLORS["grid"], linewidth=1.2, zorder=10, clip_on=False))
    zoom_box, = ax_mini.plot([], [], color=COLORS["accent"], linewidth=1.2, zorder=7)

    # Ziellinie: quer zur Fahrtrichtung, so breit wie die Strecke im Zoom
    tf = prep["t_finish"]
    (dx0, dy0), (dx1, dy1) = [(float(v[0]), float(w[0])) for v, w in (ta.at(tf - 0.1), ta.at(tf + 0.1))]
    d = np.array([dx1 - dx0, dy1 - dy0])
    nrm = np.array([-d[1], d[0]]) / (np.hypot(*d) or 1.0)
    fx, fy = finish
    fin_white, = ax_zoom.plot([], [], color="white", linewidth=7, zorder=3, solid_capstyle="butt")
    fin_black, = ax_zoom.plot([], [], color="black", linewidth=7, zorder=3, linestyle=(0, (1.2, 1.2)))
    fin_text = ax_zoom.text(fx, fy, "FINISH", fontsize=11, fontweight="bold", color=COLORS["text"],
                            ha="center", va="center", zorder=8, clip_on=True)

    def set_zoom(width_m: float) -> tuple[float, float]:
        """Zoombreite setzen: Strecke und Ziellinie passend dick zeichnen."""
        half = width_m * scale / 2
        lw_out = float(np.clip(TRACK_LW_AT_200M * 200.0 / width_m, 8.0, TRACK_LW_AT_200M))
        track_lines["zoom"][0].set_linewidth(lw_out)
        track_lines["zoom"][1].set_linewidth(lw_out * 38 / 46)
        px_per_unit = MAP_BOX[2] * WIDTH_PX / (2 * half)
        w_half = (lw_out * DPI / 72) / 2 / px_per_unit
        lx = [fx - nrm[0] * w_half, fx + nrm[0] * w_half]
        ly = [fy - nrm[1] * w_half, fy + nrm[1] * w_half]
        for ln in (fin_white, fin_black):
            ln.set_data(lx, ly)
            ln.set_linewidth(max(lw_out / 6.5, 2.5))
        off = w_half + 12 / px_per_unit * 3
        fin_text.set_position((fx + nrm[0] * off, fy + nrm[1] * off))
        return half, half * zoom_aspect
    for ax in (ax_mini, ax_map):
        ax.scatter([fx], [fy], s=40 if ax is ax_map else 14, marker="s", color="white", zorder=3)

    # markierter Abstand zwischen den Autos auf der Karte
    gap_band = LineCollection([], linewidths=6, colors=[to_rgba(COLORS["accent"], 0.75)], zorder=3,
                              capstyle="round")
    ax_map.add_collection(gap_band)
    gap_label = ax_map.text(0, 0, "", fontsize=12, fontweight="bold", color=COLORS["accent"], ha="center",
                            va="center", zorder=8,
                            bbox={"boxstyle": "round,pad=0.3", "facecolor": COLORS["bg"], "edgecolor": "none",
                                  "alpha": 0.85})

    # ── Abstandsgraph ────────────────────────────────────────────────────────
    ax_chart = fig.add_axes(CHART_BOX)
    ax_chart.set_facecolor(COLORS["plot"])
    for side in ("top", "right"):
        ax_chart.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax_chart.spines[side].set_color(COLORS["grid"])
    ax_chart.tick_params(colors=COLORS["muted"], labelsize=10)
    ax_chart.grid(color=COLORS["grid"], linewidth=0.6)
    full_x = (x[0], x[-1])
    full_y = (min(0.0, float(y.min()) * 1.1), max(float(y.max()) * 1.12, 0.5))
    after = y[x > blocks[-1][1]] if blocks else y
    zoom_x = ((blocks[-1][0] - 1.0) if blocks else x[0], x[-1])
    zoom_y = (min(0.0, float(after.min()) * 1.2) if len(after) else 0.0,
              max(float(after.max()) * 1.6, 0.5) if len(after) else full_y[1])
    ax_chart.axhline(0, color=COLORS["muted"], linewidth=1)
    ax_chart.set_xlabel("Lap", color=COLORS["muted"], fontsize=11)
    ax_chart.set_ylabel(f"{b} behind {a} (s)", color=COLORS["muted"], fontsize=11)
    for lo, hi, kind in phases:
        ax_chart.axvspan(lo - 0.5, hi + 0.5, color=NEUTRAL_STYLE[kind][0],
                         alpha=0.20 if kind == "RED" else 0.12, zorder=0)
    line, = ax_chart.plot([], [], color=cb, linewidth=2.6, zorder=4)
    head = ax_chart.scatter([], [], s=90, color=cb, edgecolor="white", linewidth=1.2, zorder=5)
    fill = [None]
    flash = fig.add_artist(plt.Rectangle((0, 0), 1, 1, transform=fig.transFigure, color=SC_YELLOW,
                                         alpha=0.0, zorder=20))

    # ── 3D-Anfang ────────────────────────────────────────────────────────────
    ax_3d = fig.add_axes([0, 0, 1, 1], zorder=-1)
    hook_1, _, hook_2 = hook.partition(" – ")
    open_txt = [fig.text(0.5, 0.925, hook_1, ha="center", va="center", fontsize=30 if len(hook_1) < 28 else 24,
                         fontweight="bold", color=COLORS["text"]),
                fig.text(0.5, 0.878, hook_2, ha="center", va="center", fontsize=30 if len(hook_2) < 28 else 24,
                         fontweight="bold", color=COLORS["accent"]),
                fig.text(0.5, 0.835, "FINAL LAP", ha="center", va="center", fontsize=14, fontweight="bold",
                         color=COLORS["muted"])]
    open_gap = fig.text(0.5, 0.11, "", ha="center", va="center", fontsize=44, fontweight="bold",
                        color=COLORS["text"])
    open_txt += [open_gap, fig.text(0.5, 0.07, f"{b} behind {a}", ha="center", va="center", fontsize=14,
                                    color=COLORS["muted"])]
    open_hist: list[float] = []
    from stintlab.reels.chase3d import MiniMap
    minimap = MiniMap(fig, prep["scene"])

    # ── Texte ────────────────────────────────────────────────────────────────
    txt_big = fig.text(0.5, 0.885, "", ha="center", va="center", fontsize=44, fontweight="bold")
    txt_sub = fig.text(0.5, 0.835, "", ha="center", va="center", fontsize=15, color=COLORS["muted"])
    txt_tag = fig.text(0.5, 0.795, "", ha="center", va="center", fontsize=12, fontweight="bold",
                       color=COLORS["accent"])
    txt_banner = fig.text(0.5, 0.785, "", ha="center", va="center", fontsize=24, fontweight="black",
                          color="black", zorder=21,
                          bbox={"boxstyle": "square,pad=0.4", "facecolor": SC_YELLOW, "edgecolor": "none"})
    txt_legend = [fig.text(0.48, 0.275, f"● {a}", ha="right", va="center", fontsize=13, fontweight="bold",
                           color=ca),
                  fig.text(0.52, 0.275, f"● {b}", ha="left", va="center", fontsize=13, fontweight="bold",
                           color=cb)]
    txt_center = fig.text(0.5, 0.58, "", ha="center", va="center", fontsize=46, fontweight="bold",
                          color=COLORS["accent"])
    txt_center_sub = fig.text(0.5, 0.52, "", ha="center", va="center", fontsize=17, color=COLORS["muted"],
                              wrap=True)
    fig.text(0.94, 0.965, "STINTLAB", ha="right", va="center", fontsize=11, fontweight="bold",
             color=COLORS["accent"])
    txt_foot = fig.text(0.06, 0.245, "", ha="left", va="top", fontsize=7.5, color=COLORS["muted"])

    def visible(*shown) -> None:
        for art in (ax_map, ax_zoom, ax_mini, ax_chart, ax_3d, *open_txt, *txt_legend, txt_tag):
            art.set_visible(art in shown)
        minimap.set_visible(ax_3d in shown)
        txt_banner.set_visible(False)
        flash.set_alpha(0.0)

    def place(key: str, t: float, trail_s: float) -> list:
        _, trails, dots = layers[key]
        now = []
        for i, tr in enumerate((ta, tb)):
            px, py = tr.at(t)
            now.append((float(px[0]), float(py[0])))
            dots[i].set_offsets([now[-1]])
            if trails:
                _set_trail(trails[i], tr, t, trail_s)
        return now

    def headline(g: float, sub: str) -> None:
        txt_big.set_text(_fmt_gap(g))
        txt_big.set_fontsize(44)
        txt_big.set_color(cb)
        txt_sub.set_text(sub)

    def draw_map(i: int) -> None:
        visible(ax_map, *txt_legend, txt_tag)
        t = prep["map_times"][i]
        place("map", t, 4.0)
        g = prep["map_gap"][i]
        if not np.isnan(g) and g > 0.3:
            bx, by = tb.at(np.linspace(t, t + g, 80))
            pts = np.column_stack([bx, by])
            gap_band.set_segments(np.stack([pts[:-1], pts[1:]], axis=1))
            metres = tb.path_length(t, t + g) / scale
            mid = len(bx) // 2
            gap_label.set_position((bx[mid], by[mid]))
            gap_label.set_text(f"≈ {metres:,.0f} m")
        else:
            gap_band.set_segments([])
            gap_label.set_text("")
        headline(g, f"{b} behind {a}")
        txt_tag.set_text(f"LAP {prep['track_lap']}" + (f" · BEFORE THE {NEUTRAL_STYLE[first_kind][1]}" if blocks and
                                                         prep["track_lap"] < blocks[0][0] else ""))
        txt_foot.set_text("Data: OpenF1 positions · both cars at the same moment · highlighted = gap on track")

    def draw_chart(pos: float, zoom: float) -> None:
        visible(ax_chart)
        xs = np.append(x[x <= pos], pos)
        ys = np.interp(xs, x, y)
        line.set_data(xs, ys)
        head.set_offsets([[xs[-1], ys[-1]]])
        if fill[0] is not None:
            fill[0].remove()
        fill[0] = ax_chart.fill_between(xs, ys, 0, color=cb, alpha=0.15, linewidth=0, zorder=3)
        lerp = lambda p, q: (p[0] + (q[0] - p[0]) * zoom, p[1] + (q[1] - p[1]) * zoom)
        ax_chart.set_xlim(*lerp(full_x, zoom_x))
        ax_chart.set_ylim(*lerp(full_y, zoom_y))
        g = float(ys[-1])
        headline(g, f"Lap {int(round(pos))} / {int(x[-1])}  ·  {b} {'behind' if g >= 0 else 'ahead'}")
        for lo, hi, kind in phases:
            if lo - 0.5 <= pos <= hi + 0.5:
                color, name, _, fg = NEUTRAL_STYLE[kind]
                txt_banner.set_text(name)
                txt_banner.set_color(fg)
                txt_banner.get_bbox_patch().set_facecolor(color)
                txt_banner.set_visible(True)
                # kurzer Blitz in der Farbe der Flagge beim Einsatz
                flash.set_color(color)
                flash.set_alpha(max(0.0, 0.35 * (1 - (pos - (lo - 0.5)) / 1.2)))
        txt_foot.set_text("Data: OpenF1 · gap at the finish line each lap · "
                          + neutral_legend(k for *_, k in phases))

    def draw_final(i: int, is_result: bool) -> None:
        visible(ax_zoom, ax_mini, *txt_legend, txt_tag)
        t = prep["fin_times"][i]
        now = place("zoom", t, 0.15 * prep["fin_speed"][i] + 0.5)
        half, hy = set_zoom(prep["fin_zoom"][i])
        place("mini", t, 0.0)
        cx, cy = (now[0][0] + now[1][0]) / 2, (now[0][1] + now[1][1]) / 2
        ax_zoom.set_xlim(cx - half, cx + half)
        ax_zoom.set_ylim(cy - hy, cy + hy)
        zoom_box.set_data([cx - half, cx + half, cx + half, cx - half, cx - half],
                          [cy - hy, cy - hy, cy + hy, cy + hy, cy - hy])
        metres = np.hypot(now[0][0] - now[1][0], now[0][1] - now[1][1]) / scale
        to_go = ta.path_length(t, tf) / scale if t < tf else 0.0
        speed = prep["fin_speed"][i]
        txt_tag.set_text((f"FINAL LAP · {to_go:,.0f} m TO GO" + (f" · {speed:.0f}× SPEED" if speed >= 1.5 else ""))
                         if to_go > 0 else "CHEQUERED FLAG")
        txt_foot.set_text(f"Data: OpenF1 positions · live gap from positions, "
                          "final gap official")
        if is_result:
            txt_big.set_text(result.upper())
            txt_big.set_fontsize(26)
            txt_big.set_color(ca)
            txt_sub.set_text(f"Official gap {final:.3f} s")
            return
        g = final if t >= tf else prep["fin_gap"][i]
        headline(g, f"{metres:.0f} m  ·  {b} behind {a}")
        if t >= tf:
            txt_big.set_text(f"{final:.3f} s")

    def draw(phase: str, v, zoom: float) -> None:
        txt_center.set_text("")
        txt_center_sub.set_text("")
        if phase == "open":
            visible(ax_3d, *open_txt)
            txt_big.set_text("")
            txt_sub.set_text("")
            txt_foot.set_text("")
            from stintlab.reels.chase3d import draw_scene
            g = draw_scene(ax_3d, prep["scene"], prep["open_times"][v])
            minimap.update(prep["open_times"][v])
            if np.isfinite(g):
                open_hist.append(g)
            recent = open_hist[-9:]      # geglättet, sonst flackern die Hundertstel
            open_gap.set_text(_fmt_gap(float(np.mean(recent))) if recent else "")
            return
        if phase == "map":
            draw_map(v)
        elif phase == "chart":
            draw_chart(v, zoom)
        else:
            draw_final(v, phase == "result")

    matplotlib.rcParams["animation.ffmpeg_path"] = _ffmpeg()
    writer = animation.FFMpegWriter(fps=FPS, codec="libx264", extra_args=["-pix_fmt", "yuv420p", "-crf", "20"])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = frame_list(prep)
    step = max(len(frames) // 10, 1)
    with writer.saving(fig, str(path), dpi=DPI):
        last = None
        for i, (phase, v, zoom) in enumerate(frames):
            key = (phase, round(float(v), 4), round(zoom, 4))
            if key != last:
                draw(phase, v, zoom)
                last = key
            writer.grab_frame(facecolor=COLORS["bg"])
            if i % step == 0:
                print(f"  {100 * i // len(frames):3d} %  ({i}/{len(frames)} Bilder)", flush=True)
    plt.close(fig)
    return path
