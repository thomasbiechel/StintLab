"""Reel „Chase“: der Abstand zwischen zwei Fahrern über das Rennen.

ABLAUF (1080 × 1920, 9:16, 60 Bilder/s, ~18 s):
  1. Haken (2 s):       große Zahl = Abstand im Ziel, darunter der Haken-Text
  2. Rennen (12 s):     die Abstandslinie zeichnet sich Runde für Runde,
                        oben laufen Abstand und Runde mit; SC/VSC-Phasen sind
                        hinterlegt, Boxenstopps markiert
  3. Auflösung (2,5 s): Ergebnis über dem fertigen Graphen
  4. Logo (1 s)

ABSTAND: über die Zieldurchfahrten (compute_gap_between, wie im Madrid-Post),
nicht über die Differenz zweier Gap-to-Leader-Werte.
Vorzeichen: > 0 = A (der Vordere) liegt vorne.

Zwischen zwei Runden wird linear weitergezeichnet, damit die Linie fließt
statt pro Runde zu springen.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
from matplotlib import animation
from matplotlib import pyplot as plt

from stintlab.analyses.gap_between import line_gaps
from stintlab.analyses.results import race_rows
from stintlab.race_control import neutral_phases, restricted_laps
from stintlab.reels.ghost_lap import _ffmpeg
from stintlab.style import COLORS, NEUTRAL_STYLE, neutral_legend, resolve_font, team_color

WIDTH_PX, HEIGHT_PX, DPI, FPS = 1080, 1920, 150, 60
HOOK_S, RACE_S, RESULT_S, LOGO_S = 2.0, 12.0, 2.5, 1.0


def pick_pair(data: dict, drivers: list[str] | None) -> list[str]:
    """Zwei Fahrer: angegeben oder Sieger und Zweiter laut Ergebnis."""
    if drivers:
        if len(drivers) != 2:
            raise ValueError("Chase braucht genau zwei Fahrer, z. B. drivers = [\"RUS\", \"VER\"]")
        return list(drivers)
    top = [r["driver"] for r in race_rows(data) if r["position"] in (1, 2)]
    if len(top) != 2:
        raise ValueError("Kein Ergebnis mit P1 und P2 – drivers in der post.toml angeben")
    return top


def official_final_gap(data: dict, a: str, b: str) -> float | None:
    """Offizieller Abstand B hinter A im Ziel, falls A gewonnen hat und B eine
    Zahl als Abstand hat (sonst None)."""
    rows = {r["driver"]: r for r in race_rows(data)}
    ra, rb = rows.get(a), rows.get(b)
    if ra and rb and ra["position"] == 1 and isinstance(rb["gap"], (int, float)):
        return float(rb["gap"])
    return None


def gap_series(data: dict, a: str, b: str, laps: tuple[int, int] | None = None,
               skip: list[int] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(Runden, Abstand) – A vorne = positiv.

    LETZTE RUNDE: Ihr Ende wird aus Beginn + Rundenzeit geschätzt (es gibt
    keine nächste Runde), und der Beginn ist bei OpenF1 einige Zehntel
    ungenau. Baku 2026: −0,003 s statt offiziell +0,196 s. Deshalb wird
    für die letzte Rennrunde der offizielle Abstand verwendet.
    skip: Runden auslassen, z. B. Boxenstopp-Runden mit Ausreißern.
    """
    gaps, _ = line_gaps(data, a, b)   # letzte Runde = offizieller Abstand, davor Rundenzeiten
    if gaps:
        official = official_final_gap(data, a, b)
        last = max(gaps)
        race_laps = max((r["laps"] or 0) for r in race_rows(data)) if data.get("results") else None
        if official is not None and race_laps and last == race_laps:
            gaps[last] = official
    if skip:
        gaps = {n: g for n, g in gaps.items() if n not in set(skip)}
    if laps:
        gaps = {n: g for n, g in gaps.items() if laps[0] <= n <= laps[1]}
    if len(gaps) < 3:
        raise ValueError(f"Zu wenige gemeinsame Runden von {a} und {b}")
    x = np.array(sorted(gaps), dtype=float)
    return x, np.array([gaps[int(n)] for n in x])


def neutral_blocks(race_control: list[dict], first: int, last: int) -> list[tuple[int, int]]:
    """Zusammenhängende SC/VSC/Rot-Phasen als [(von, bis)] im Rundenbereich."""
    laps = sorted(n for n in restricted_laps(race_control) if first <= n <= last)
    blocks = []
    for n in laps:
        if blocks and n == blocks[-1][1] + 1:
            blocks[-1] = (blocks[-1][0], n)
        else:
            blocks.append((n, n))
    return blocks


def frame_positions(x: np.ndarray) -> list[tuple[str, float]]:
    """[(Phase, Rundenwert), ...] – ein Eintrag pro Videobild."""
    frames = [("hook", x[0])] * int(HOOK_S * FPS)
    n = int(RACE_S * FPS)
    frames += [("race", x[0] + (x[-1] - x[0]) * i / (n - 1)) for i in range(n)]
    frames += [("result", x[-1])] * int(RESULT_S * FPS)
    frames += [("logo", x[-1])] * int(LOGO_S * FPS)
    return frames


def render_gap_chase(data: dict, reel: dict, path: Path) -> Path:
    a, b = pick_pair(data, reel.get("drivers") or None)
    laps = tuple(reel["laps"]) if reel.get("laps") else None
    x, y = gap_series(data, a, b, laps, reel.get("skip"))
    teams = data.get("teams", {})
    ca, cb = team_color(teams.get(a)), team_color(teams.get(b))
    final = float(y[-1])
    hook = reel.get("hook") or f"{b} hunting {a}"
    result = reel.get("result") or f"{a} holds on by {final:.3f} s"

    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [resolve_font()]
    fig = plt.figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI, facecolor=COLORS["bg"])

    ax = fig.add_axes([0.14, 0.30, 0.78, 0.44])
    ax.set_facecolor(COLORS["plot"])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(COLORS["grid"])
    ax.tick_params(colors=COLORS["muted"], labelsize=10)
    ax.grid(color=COLORS["grid"], linewidth=0.6)
    ymax = float(reel.get("ymax") or max(y.max() * 1.1, 0.5))
    ax.set_xlim(x[0], x[-1])
    ax.set_ylim(min(0.0, y.min() * 1.1), ymax)
    ax.axhline(0, color=COLORS["muted"], linewidth=1)
    ax.set_xlabel("Lap", color=COLORS["muted"], fontsize=11)
    ax.set_ylabel(f"{b} behind {a} (s)", color=COLORS["muted"], fontsize=11)

    phases = neutral_phases(data.get("race_control", []), int(x[0]), int(x[-1]))
    for lo, hi, kind in phases:
        color, _, short, _ = NEUTRAL_STYLE[kind]
        ax.axvspan(lo - 0.5, hi + 0.5, color=color, alpha=0.18 if kind == "RED" else 0.10, zorder=0)
        ax.text((lo + hi) / 2, ymax * 0.97, short, ha="center", va="top", fontsize=9,
                color=color, fontweight="bold")
    for p in data.get("pit_stops", []):
        if p.get("lap") and x[0] <= p["lap"] <= x[-1] and p["driver"] in (a, b):
            ax.axvline(p["lap"], color=ca if p["driver"] == a else cb, linewidth=0.8,
                       linestyle=":", alpha=0.6, zorder=1)

    line, = ax.plot([], [], color=cb, linewidth=2.6, zorder=4)
    head = ax.scatter([], [], s=90, color=cb, edgecolor="white", linewidth=1.2, zorder=5)
    fill = [None]

    txt_big = fig.text(0.5, 0.875, "", ha="center", va="center", fontsize=44, fontweight="bold")
    txt_sub = fig.text(0.5, 0.825, "", ha="center", va="center", fontsize=15, color=COLORS["muted"])
    txt_names = [fig.text(0.48, 0.775, f"{a}", ha="right", va="center", fontsize=14, fontweight="bold", color=ca),
                 fig.text(0.5, 0.775, "vs", ha="center", va="center", fontsize=11, color=COLORS["muted"]),
                 fig.text(0.52, 0.775, f"{b}", ha="left", va="center", fontsize=14, fontweight="bold", color=cb)]
    txt_center = fig.text(0.5, 0.58, "", ha="center", va="center", fontsize=56, fontweight="bold",
                          color=COLORS["accent"])
    txt_center_sub = fig.text(0.5, 0.52, "", ha="center", va="center", fontsize=18, color=COLORS["muted"])
    fig.text(0.94, 0.965, "STINTLAB", ha="right", va="center", fontsize=11, fontweight="bold", color=COLORS["accent"])
    fig.text(0.06, 0.225, f"Data: OpenF1 · gap at the finish line each lap · {neutral_legend(k for *_, k in phases)} · dotted = pit stop",
             ha="left", va="top", fontsize=7.5, color=COLORS["muted"])

    def show_race(on: bool) -> None:
        ax.set_visible(on)
        for t in txt_names:
            t.set_visible(on)

    def draw(phase: str, pos: float) -> None:
        txt_center.set_text("")
        txt_center_sub.set_text("")
        if phase in ("hook", "logo"):
            show_race(False)
            txt_big.set_text("")
            txt_sub.set_text("")
            txt_center.set_text(f"{final:.3f} s" if phase == "hook" else "STINTLAB")
            txt_center_sub.set_text(hook if phase == "hook" else "F1 data, explained")
            return
        show_race(True)
        xs = np.append(x[x <= pos], pos)
        ys = np.interp(xs, x, y)
        line.set_data(xs, ys)
        head.set_offsets([[xs[-1], ys[-1]]])
        if fill[0] is not None:
            fill[0].remove()
        fill[0] = ax.fill_between(xs, ys, 0, color=cb, alpha=0.15, linewidth=0, zorder=3)
        if phase == "result":
            txt_big.set_text(result.upper())
            txt_big.set_fontsize(28)
            txt_big.set_color(ca)
            txt_sub.set_text(f"Lap {int(x[-1])} · {b} {final:.3f} s behind")
        else:
            g = float(ys[-1])
            txt_big.set_text(f"{abs(g):.1f} s" if abs(g) >= 1 else f"{abs(g):.3f} s")
            txt_big.set_fontsize(44)
            txt_big.set_color(cb if g >= 0 else ca)
            txt_sub.set_text(f"Lap {int(round(pos))} / {int(x[-1])}  ·  {b} {'behind' if g >= 0 else 'ahead'}")

    matplotlib.rcParams["animation.ffmpeg_path"] = _ffmpeg()
    writer = animation.FFMpegWriter(fps=FPS, codec="libx264", extra_args=["-pix_fmt", "yuv420p", "-crf", "20"])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = frame_positions(x)
    step = max(len(frames) // 10, 1)
    with writer.saving(fig, str(path), dpi=DPI):
        last = None
        for i, (phase, pos) in enumerate(frames):
            key = (phase, round(pos, 4))
            if key != last:
                draw(phase, pos)
                last = key
            writer.grab_frame(facecolor=COLORS["bg"])
            if i % step == 0:
                print(f"  {100 * i // len(frames):3d} %  ({i}/{len(frames)} Bilder)", flush=True)
    plt.close(fig)
    return path
