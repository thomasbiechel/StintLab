"""Reel „Pass Map“: Überholmanöver auf der 2D-Streckenkarte – echte Uhrzeit.

IDEE (Kuala Lumpur 2026): Das erfolgreichste StintLab-Video war eine flache
Streckenkarte mit zwei Punkten (Quali-Ghost-Lap, ohne 3D). Dieses Reel nutzt
dieselbe Optik für Zweikämpfe im Rennen: alle Autos zur SELBEN Uhrzeit auf der
Karte, nicht jeder ab seinem eigenen Rundenbeginn wie im Ghost-Lap-Reel – sonst
wäre ein Überholmanöver gar nicht zu sehen.

ABLAUF (1080 × 1920, 60 Bilder/s, ~15 s):
  - ab Bild 1 fahren die Autos (kein Titel-Screen); die ersten HOOK_S Sekunden
    steht der Haken groß über der Karte
  - schnell (FAST-fach) auf der ganzen Karte, um jedes Manöver herum weich
    abbremsen (SLOW-fach) und auf die Autos zoomen
  - nach jedem Manöver ein Banner („HAM PASSES HAD · P3“)
  - Auflösung (RESULT_S) über der weiterlaufenden Karte, kein Logo-Screen

post.toml:
    [[reels]]
    analysis = "pass_map"
    drivers  = ["HAM", "LEC"]    # Angreifer, in der Reihenfolge ihrer Manöver
    rival    = "HAD"             # der Überholte
    laps     = [53, 54]          # in diesen Runden wird das Manöver gesucht (je Angreifer)
    hook     = "..."
    result   = "..."

MANÖVER-ZEITPUNKT: aus den Positionsdaten. Vorzeichen-Abstand Angreifer ↔ Gegner
(live_gap aus dem Race-Story-Reel: Zeit, bis der Hintere den Punkt des Vorderen
erreicht), Nulldurchgang = vorbei. Die Seite (innen/außen) steht nicht in den
Daten – OpenF1 legt alle Autos auf eine Linie, auf der Karte fahren sie also
„durcheinander durch“. Deshalb Zoom nur so weit, dass das nicht stört.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
from matplotlib import animation
from matplotlib import patheffects as pe
from matplotlib import pyplot as plt

from stintlab import openf1
from stintlab.analyses.positions import compute_positions
from stintlab.reels.ghost_lap import _ffmpeg
from stintlab.reels.race_story import Track, lap_window, live_gap
from stintlab.style import COLORS, resolve_font, team_color

WIDTH_PX, HEIGHT_PX, DPI, FPS = 1080, 1920, 150, 60
FAST, SLOW = 14.0, 1.6        # Echtzeit-Sekunden pro Video-Sekunde
SLOW_HALF_S = 2.5             # so lange (Echtzeit) vor/nach dem Manöver langsam
RAMP_S = 5.0                  # Übergang schnell ↔ langsam (Echtzeit)
LEAD_S, TAIL_S = 18.0, 5.0    # Echtzeit vor dem ersten / nach dem letzten Manöver
HOOK_S, RESULT_S = 3.0, 2.5   # Video-Sekunden
ZOOM_FRACTION = 0.16          # Zoom-Breite als Anteil der Streckenausdehnung
MAP_BOX = [0.04, 0.20, 0.92, 0.60]
TRAIL_S = 2.5
# (dx, dy, ha, va) je Fahrer: Gegner rechts oben, 1. Angreifer links, 2. Angreifer rechts unten
LABEL_SIDES = [(1, 1, "left", "bottom"), (-1.4, 0, "right", "center"), (1, -1, "left", "top")]


def signed_gap(rival: Track, att: Track, t: float) -> float:
    """> 0: Angreifer liegt so viele Sekunden HINTER dem Gegner, < 0: davor."""
    g = live_gap(rival, att, t, 6.0, 40.0)
    if np.isfinite(g):
        return g
    g2 = live_gap(att, rival, t, 6.0, 40.0)
    return -g2 if np.isfinite(g2) else float("nan")


def find_pass(rival: Track, att: Track, t_from: float, t_to: float) -> float:
    """Zeitpunkt, an dem der Angreifer vorbei ist (Nulldurchgang des Abstands)."""
    ts = np.arange(t_from, t_to, 0.25)
    g = np.array([signed_gap(rival, att, t) for t in ts])
    for i in range(1, len(ts)):
        if np.isfinite(g[i - 1]) and np.isfinite(g[i]) and g[i - 1] > 0 >= g[i]:
            return float(ts[i - 1] + (ts[i] - ts[i - 1]) * g[i - 1] / (g[i - 1] - g[i]))
    raise ValueError("Kein Überholmanöver im Zeitfenster gefunden – Runde prüfen")


def find_crossings(rival: Track, att: Track, t_from: float, t_to: float) -> list[tuple[float, int]]:
    """Alle Platzwechsel im Fenster: [(Zeit, +1 = Angreifer geht vorbei, −1 = Gegner zurück)].

    Für Duelle mit Rück-Überholmanövern (Kuala Lumpur 2026, letzte Runde:
    LIN vorbei, HUL zurück, LIN wieder vorbei)."""
    ts = np.arange(t_from, t_to, 0.25)
    g = np.array([signed_gap(rival, att, t) for t in ts])
    out = []
    for i in range(1, len(ts)):
        a_, b_ = g[i - 1], g[i]
        if np.isfinite(a_) and np.isfinite(b_) and (a_ > 0) != (b_ > 0) and a_ != b_:
            out.append((float(ts[i - 1] + (ts[i] - ts[i - 1]) * a_ / (a_ - b_)), 1 if a_ > 0 else -1))
    if not out or out[-1][1] != 1:
        raise ValueError("Kein abschließendes Überholmanöver im Zeitfenster – Runde prüfen")
    return out


def slow_weight(t: float, passes: list[float]) -> float:
    """1 um ein Manöver herum, 0 weit weg, dazwischen weich (smoothstep)."""
    w = 0.0
    for p in passes:
        d = abs(t - p) - SLOW_HALF_S
        if d <= 0:
            return 1.0
        if d < RAMP_S:
            u = 1 - d / RAMP_S
            w = max(w, u * u * (3 - 2 * u))
    return w


def frame_times(start: float, end: float, passes: list[float]) -> list[float]:
    """Echtzeit pro Videobild – schnell, um die Manöver herum langsam."""
    times, t = [], start
    while t < end:
        times.append(t)
        w = slow_weight(t, passes)
        t += (FAST * (1 - w) + SLOW * w) / FPS
    return times


def render_pass_map(data: dict, reel: dict, path: Path) -> Path:
    attackers = reel.get("drivers") or []
    rival = reel.get("rival")
    laps = reel.get("laps") or []
    if not attackers or not rival or len(laps) != len(attackers):
        raise ValueError('pass_map braucht drivers = ["HAM", ...], rival = "HAD" und laps = [53, ...] (eine Runde je Angreifer)')
    teams, numbers = data.get("teams", {}), data.get("numbers", {})
    t0 = data["lap_ends"][rival][min(laps) - 1]

    def track(drv, rotate=None):
        loc = openf1.cached_fetch_driver("location", data["session_key"], numbers[drv])
        return Track(loc, t0, rotate)

    tr_rival = track(rival)
    tracks = {rival: tr_rival}
    for a in attackers:
        tracks[a] = track(a, tr_rival.rotate)

    # Manöver suchen: im Fenster der angegebenen Runde des Angreifers (± Puffer).
    # repasses = true: alle Platzwechsel (vorbei – zurück – wieder vorbei), sonst nur der erste.
    positions = compute_positions(data["lap_ends"], data.get("grid"), data.get("results"))
    def lap_at(drv, t):
        return 1 + sum(1 for e in data["lap_ends"][drv].values() if (e - t0).total_seconds() <= t)
    events = []                                    # (Zeit, Angreifer, +1/−1)
    for a, lap in zip(attackers, laps):
        lo, hi = lap_window(data, a, lap, t0)
        if reel.get("repasses"):
            events += [(t, a, k) for t, k in find_crossings(tr_rival, tracks[a], lo - 5, hi + 5)]
        else:
            events.append((find_pass(tr_rival, tracks[a], lo - 5, hi + 5), a, 1))
    events.sort()
    passes = [t for t, _, _ in events]
    ev_att = [a for _, a, _ in events]
    attackers = list(dict.fromkeys(ev_att))

    banners, seen = [], set()
    for i, (t, a, k) in enumerate(events):
        last_for_a = all(a2 != a for _, a2, _ in events[i + 1:])
        if k < 0:
            text = f"{rival} FIGHTS BACK"
        else:
            text = f"{a} {'AGAIN' if a in seen else 'PASSES ' + rival}"
            seen.add(a)
            if last_for_a:
                pos = positions.get(a, {}).get(lap_at(a, t))
                text += f" · P{pos}" if pos else ""
        banners.append((t, text))

    # Hintergrund: eine ganze Runde des Gegners
    r_lo, r_hi = lap_window(data, rival, min(laps), t0)
    bx, by = tr_rival.at(np.linspace(r_lo, r_hi, 900))
    cx, cy = (bx.max() + bx.min()) / 2, (by.max() + by.min()) / 2
    box_w, box_h = MAP_BOX[2] * WIDTH_PX, MAP_BOX[3] * HEIGHT_PX
    aspect = box_h / box_w
    full_half = max((bx.max() - bx.min()) / 2, (by.max() - by.min()) / 2 / aspect) * 1.08
    zoom_half = full_half * ZOOM_FRACTION

    start, end = passes[0] - LEAD_S, passes[-1] + TAIL_S
    times = frame_times(start, end, passes)
    n_result = int(RESULT_S * FPS)
    # Auflösung: Karte läuft langsam weiter
    times += [end + i * (FAST / 3) / FPS for i in range(n_result)]
    n_race = len(times) - n_result

    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [resolve_font(), "DejaVu Sans"]
    fig = plt.figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI, facecolor=COLORS["bg"])
    ax = fig.add_axes(MAP_BOX)
    ax.set_facecolor(COLORS["bg"])
    ax.set_axis_off()
    ax.plot(bx, by, color="#2a2e36", linewidth=9, solid_capstyle="round", zorder=1)
    ax.plot(bx, by, color="#3a3f4a", linewidth=1.2, zorder=2)

    # Pass-Stellen markieren, sobald sie passiert sind
    pass_marks = []
    for p, a in zip(passes, ev_att):
        px, py = tracks[a].at(p)
        m = ax.scatter(px, py, s=500, facecolor="none", edgecolor=COLORS["accent"], linewidth=2, zorder=3)
        m.set_visible(False)
        pass_marks.append((p, m))

    outline = [pe.withStroke(linewidth=3, foreground=COLORS["bg"])]
    dots, labels, trails = {}, {}, {}
    drivers = [rival] + attackers
    for i, d in enumerate(drivers):
        col = team_color(teams.get(d))
        # Gleiche Teamfarbe (zwei Ferraris): zweiter Angreifer mit weißem Rand
        edge = "white" if (d != rival and attackers.index(d) > 0) else COLORS["bg"]
        trails[d], = ax.plot([], [], color=col, linewidth=4, alpha=0.5, solid_capstyle="round", zorder=4)
        dots[d] = ax.scatter([], [], s=220, color=col, edgecolor=edge, linewidth=2.2, zorder=6)
        # Kürzel in verschiedene Richtungen versetzt – sonst überlagern sie sich,
        # wenn die Autos dicht beieinander fahren („HLEC“)
        side = LABEL_SIDES[i % len(LABEL_SIDES)]
        labels[d] = ax.text(0, 0, d, fontsize=15, fontweight="bold", color=col, zorder=7,
                            ha=side[2], va=side[3], path_effects=outline)
        labels[d].side = side
        labels[d].set_clip_on(True)      # Auto außerhalb des Zooms → Kürzel nicht über die Überschrift

    # „→“ fehlt in Barlow (Kästchen) – als Mathe-Pfeil setzen, wie im Comeback-Reel
    arrow = lambda txt: txt.replace("→", r"$\rightarrow$")
    hook = arrow(reel.get("hook") or f"{' & '.join(attackers)} vs {rival}")
    result = arrow(reel.get("result") or f"{len(attackers)} passes on {rival}")
    result_sub = arrow(reel.get("result_sub", ""))
    txt_head = fig.text(0.5, 0.895, "", ha="center", va="center", fontsize=26, fontweight="bold",
                        color=COLORS["text"], linespacing=1.1)
    txt_sub = fig.text(0.5, 0.835, "", ha="center", va="center", fontsize=15, color=COLORS["muted"])
    txt_banner = fig.text(0.5, 0.165, "", ha="center", va="center", fontsize=22, fontweight="bold",
                          color=COLORS["accent"])
    fig.text(0.94, 0.965, "STINTLAB", ha="right", va="center", fontsize=11, fontweight="bold", color=COLORS["accent"])
    fig.text(0.06, 0.06, "Data: OpenF1 · all cars at the same moment · position data puts all cars on one line",
             ha="left", va="center", fontsize=7.5, color=COLORS["muted"])

    import textwrap
    wrap = lambda s, w: "\n".join(textwrap.wrap(s, w))
    leader = attackers[0]

    def draw(i: int, t: float) -> None:
        w = slow_weight(t, passes)
        # Kamera: Mitte zwischen Angreifer und Gegner des nächsten Manövers
        k = int(np.argmin([abs(t - p) for p in passes]))
        ax_, ay_ = tracks[ev_att[k]].at(t)
        rx_, ry_ = tr_rival.at(t)
        mx, my = (ax_[0] + rx_[0]) / 2, (ay_[0] + ry_[0]) / 2
        half = full_half * (1 - w) + zoom_half * w
        ccx, ccy = cx * (1 - w) + mx * w, cy * (1 - w) + my * w
        ax.set_xlim(ccx - half, ccx + half)
        ax.set_ylim(ccy - half * aspect, ccy + half * aspect)
        off = half * 0.035
        for d in drivers:
            x, y = tracks[d].at(t)
            dots[d].set_offsets([[x[0], y[0]]])
            tx, ty = tracks[d].at(np.linspace(t - TRAIL_S, t, 20))
            trails[d].set_data(tx, ty)
            sx, sy = labels[d].side[:2]
            labels[d].set_position((x[0] + sx * off, y[0] + sy * off))
        for p, m in pass_marks:
            m.set_visible(t >= p)
        done = [b for p, b in banners if t >= p]
        txt_banner.set_text(done[-1] if done else "")
        lap = min(lap_at(leader, t), max(data["lap_ends"][leader]))
        if i >= n_race:
            txt_head.set_text(wrap(result.upper(), 22))
            txt_head.set_color(COLORS["accent"])
            txt_sub.set_text(result_sub)
        elif i < HOOK_S * FPS:
            txt_head.set_text(wrap(hook, 30))
            txt_head.set_color(COLORS["text"])
            txt_sub.set_text(f"Lap {lap} / {max(data['lap_ends'][leader])}")
        else:
            txt_head.set_text(f"LAP {lap}")
            txt_head.set_color(COLORS["text"])
            g = signed_gap(tr_rival, tracks[ev_att[k]], t)
            if np.isfinite(g) and abs(g) < 3:
                txt_sub.set_text(f"{ev_att[k]} {abs(g):.1f} s {'behind' if g > 0 else 'ahead of'} {rival}")
            else:
                txt_sub.set_text(f"{' & '.join(attackers)} chasing {rival}")

    matplotlib.rcParams["animation.ffmpeg_path"] = _ffmpeg()
    writer = animation.FFMpegWriter(fps=FPS, codec="libx264", extra_args=["-pix_fmt", "yuv420p", "-crf", "20"])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Manöver: " + ", ".join(f"{a}{'+' if k > 0 else '−'} @ {t:.1f} s" for t, a, k in events) +
          f" · {len(times)} Bilder ({len(times) / FPS:.1f} s)")
    step = max(len(times) // 10, 1)
    with writer.saving(fig, str(path), dpi=DPI):
        for i, t in enumerate(times):
            draw(i, t)
            writer.grab_frame(facecolor=COLORS["bg"])
            if i % step == 0:
                print(f"  {100 * i // len(times):3d} %  ({i}/{len(times)} Bilder)", flush=True)
    plt.close(fig)
    return path
