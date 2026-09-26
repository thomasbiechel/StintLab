"""Reel „Ghost Lap“: zwei Fahrer fahren ihre schnellste Runde gleichzeitig.

ABLAUF (1080 × 1920, 9:16, 60 Bilder/s, ~20 s) – mit replay = false entfällt
die Zeitlupe und die Runde läuft stattdessen 14 s:
  1. Haken (2 s):       große Zahl = Endabstand, darunter der Haken-Text
  2. Runde (9 s):       ganze Streckenkarte, beide Punkte fahren synchron,
                        ~10-fach beschleunigt; oben der laufende Abstand
  3. Zeitlupe (5 s):    die Stelle, an der sich der Abstand am stärksten
                        verändert hat – im 160-m-Zoom, leicht verlangsamt
  4. Auflösung (2,5 s): Ergebnis über der Karte
  5. Logo (1 s)

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

SICHERE ZONE: Instagram legt unten Caption/Buttons und rechts die Like-Leiste
über das Video – unten ~20 % bleiben frei, Wichtiges steht in der Mitte.
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
from stintlab.analyses.ideal_lap import _valid_laps
from stintlab.analyses.long_runs import _fmt
from stintlab.analyses.telemetry import _driver_trace, compare, fastest_lap
from stintlab.session import _parse
from stintlab.style import COLORS, resolve_font, team_color

WIDTH_PX, HEIGHT_PX, DPI, FPS = 1080, 1920, 150, 60
HOOK_S, LAP_S, REPLAY_S, RESULT_S, LOGO_S = 2.0, 9.0, 5.0, 2.5, 1.0
REPLAY_WINDOW_S = 4.0  # so viele echte Sekunden zeigt die Zeitlupe (5 s Video → 0,8-fach)
TRAIL_S = 2.0          # Schweif hinter den Punkten, in echten Sekunden
ZOOM_M = 160.0         # Breite des Zoom-Ausschnitts in Metern
MAP_BOX = [0.06, 0.36, 0.88, 0.44]


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
    return arr[:, 0], arr[:, 1], arr[:, 2]


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


def prepare(data: dict, drivers: list[str] | None = None, part: str | None = None) -> dict:
    """Alles, was das Video braucht – ohne Zeichnen, damit testbar."""
    drivers, laps = pick_drivers(data, drivers, part)
    traces = [_driver_trace(data, d, l) for d, l in zip(drivers, laps)]
    res = compare(*traces)

    pos = []
    for d, lap in zip(drivers, laps):
        loc = data.get("location", {}).get(d)
        if loc is None:
            loc = openf1.cached_fetch_driver("location", data["session_key"], data["numbers"][d])
        pos.append(lap_positions(loc, lap))
    rotate = needs_rotation(pos[0][1], pos[0][2])
    pos = [(t, *orient(x, y, rotate)) for t, x, y in pos]

    a, b = traces
    return {"drivers": drivers, "laps": laps, "traces": traces, "res": res, "pos": pos,
            "a_frac": (a["t"], a["frac"]), "gap": b["lap_time"] - a["lap_time"],
            "teams": [data.get("teams", {}).get(d) for d in drivers]}


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
    change = [abs(gaps[min(i + shift, len(gaps) - 1)] - gaps[i]) for i in range(len(ts))]
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


def frame_times(lap_time: float, replay_from: float | None) -> list[tuple[str, float]]:
    """[(Phase, Rundenzeit in s), ...] – ein Eintrag pro Videobild.

    replay_from = None: keine Zeitlupe – die Runde bekommt deren Zeit dazu und
    läuft langsamer (Gesamtlänge bleibt gleich).
    """
    frames = [("hook", 0.0)] * int(HOOK_S * FPS)
    n = int((LAP_S if replay_from is not None else LAP_S + REPLAY_S) * FPS)
    frames += [("lap", lap_time * i / (n - 1)) for i in range(n)]
    if replay_from is not None:
        n = int(REPLAY_S * FPS)
        end = min(replay_from + REPLAY_WINDOW_S, lap_time)
        frames += [("replay", replay_from + (end - replay_from) * i / (n - 1)) for i in range(n)]
    frames += [("result", lap_time)] * int(RESULT_S * FPS)
    frames += [("logo", lap_time)] * int(LOGO_S * FPS)
    return frames


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
    prep = prepare(data, reel.get("drivers") or None, reel.get("part"))
    drv_a, drv_b = prep["drivers"]
    ca, cb = (team_color(t) for t in prep["teams"])
    same_team = prep["teams"][0] == prep["teams"][1]
    lap_a = prep["traces"][0]["lap_time"]
    t_a, t_b = (_fmt(tr["lap_time"]) for tr in prep["traces"])
    is_pole = reel.get("part") == "Q3"
    hook = reel.get("hook") or ("Where pole was decided" if is_pole else "Head to head")
    result = reel.get("result") or f"{drv_a} {'on pole' if is_pole else 'ahead'} by {prep['gap']:.3f} s"
    with_replay = reel.get("replay", True)
    if not isinstance(with_replay, bool):
        raise ValueError("replay muss true oder false sein (klein geschrieben, ohne Anführungszeichen)")
    rep_from = replay_from_config(prep, reel, lap_a) if with_replay else None
    rep_to = min(rep_from + REPLAY_WINDOW_S, lap_a) if with_replay else None

    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [resolve_font()]
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
    res = prep["res"]
    km = res["frac"] * res["length_m"] / 1000
    ax_gap = fig.add_axes([0.10, 0.23, 0.80, 0.10])
    ax_gap.set_facecolor(COLORS["plot"])
    for side in ax_gap.spines.values():
        side.set_visible(False)
    ax_gap.tick_params(colors=COLORS["muted"], labelsize=8)
    ax_gap.axhline(0, color=COLORS["muted"], linewidth=0.8)
    lim = max(abs(res["delta"]).max() * 1.2, 0.05)
    ax_gap.set_xlim(0, km[-1])
    ax_gap.set_ylim(-lim, lim)
    ax_gap.set_xticks([])
    at, afrac = prep["a_frac"]
    frac_of = lambda t: float(np.interp(t, at, afrac))
    replay_span = ax_gap.axvspan(frac_of(rep_from or 0.0) * km[-1], frac_of(rep_to or 0.0) * km[-1],
                                 color=COLORS["accent"], alpha=0.0, zorder=0)
    gap_line, = ax_gap.plot([], [], color=COLORS["text"], linewidth=1.6)
    cursor = ax_gap.axvline(0, color=COLORS["accent"], linewidth=1.2, visible=False)
    gap_fills = []

    # ── Texte ────────────────────────────────────────────────────────────────
    txt_big = fig.text(0.5, 0.88, "", ha="center", va="center", fontsize=40, fontweight="bold")
    txt_sub = fig.text(0.5, 0.835, "", ha="center", va="center", fontsize=15, color=COLORS["muted"])
    txt_tag = fig.text(0.94, 0.81, "", ha="right", va="bottom", fontsize=10, fontweight="bold",
                       color=COLORS["accent"])
    txt_leg_a = fig.text(0.48, 0.345, f"● {drv_a}  {t_a}", ha="right", va="center", fontsize=12,
                         fontweight="bold", color=ca)
    txt_leg_b = fig.text(0.52, 0.345, f"{'○' if same_team else '●'} {drv_b}  {t_b}", ha="left", va="center",
                         fontsize=12, fontweight="bold", color=cb)
    txt_center = fig.text(0.5, 0.58, "", ha="center", va="center", fontsize=56, fontweight="bold",
                          color=COLORS["accent"])
    txt_center_sub = fig.text(0.5, 0.52, "", ha="center", va="center", fontsize=18, color=COLORS["muted"])
    fig.text(0.94, 0.965, "STINTLAB", ha="right", va="center", fontsize=11, fontweight="bold", color=COLORS["accent"])
    fig.text(0.06, 0.215, "Data: OpenF1 · positions ~4 Hz", ha="left", va="top", fontsize=8, color=COLORS["muted"])

    def visible(*shown) -> None:
        for art in (ax_map, ax_zoom, ax_mini, ax_gap, txt_leg_a, txt_leg_b, txt_tag):
            art.set_visible(art in shown)

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
        g = gap_at(prep, t)
        txt_big.set_text(f"{abs(g):.2f} s")
        txt_big.set_fontsize(40)
        txt_big.set_color(ca if g >= 0 else cb)
        txt_sub.set_text(f"{drv_a if g >= 0 else drv_b} ahead")

    def draw(phase: str, t: float) -> None:
        txt_center.set_text("")
        txt_center_sub.set_text("")
        if phase in ("hook", "logo"):
            visible()
            txt_big.set_text("")
            txt_sub.set_text("")
            txt_center.set_text(f"{prep['gap']:.3f} s" if phase == "hook" else "STINTLAB")
            txt_center_sub.set_text(hook if phase == "hook" else "F1 data, explained")
            return
        if phase == "lap":
            visible(ax_map, ax_gap, txt_leg_a, txt_leg_b)
            place("map", t)
            running_gap(t)
            draw_gap(t, full=False)
            cursor.set_visible(False)
            replay_span.set_alpha(0.0)
            return
        if phase == "replay":
            visible(ax_zoom, ax_mini, ax_gap, txt_leg_a, txt_leg_b, txt_tag)
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
        # result
        visible(ax_map, ax_gap, txt_leg_a, txt_leg_b)
        place("map", t)
        draw_gap(t, full=True)
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
    frames = frame_times(lap_a, rep_from)
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
