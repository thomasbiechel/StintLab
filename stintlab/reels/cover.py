"""Titelbild (Cover) für ein Reel: 1080 × 1920 PNG neben dem Video.

Warum: Instagram nimmt sonst ein Bild aus dem Video als Vorschau – bei uns der
erste Frame mit halb eingeblendetem Text. Das Cover ist ein sauberes 3D-Bild
aus dem Reel (die entscheidende Szene) mit großem Titel im StintLab-Design.
In Instagram beim Hochladen: „Cover bearbeiten“ → „Aus Galerie hinzufügen“.

Profilraster: Instagram zeigt im Profil nur einen 3:4-Ausschnitt aus der Mitte
(1080 × 1440). Alles Wichtige steht deshalb zwischen 12,5 % und 87,5 % der Höhe.

In der post.toml (alles optional):
    [reels.cover]
    title = "P19 → P1"                  # großer Titel („→“ geht, wird passend gesetzt)
    kicker = "ANTONELLI · MONZA 2026"   # kleine Zeile darüber
    sub = "22 places gained on track"   # Zeile darunter
    at = 6301.2                         # Szenenzeit (s) statt der automatisch gewählten
    enabled = false                     # kein Cover
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle

from stintlab.style import COLORS, FONT_HEAD, FONT_NUM, _font

WIDTH_PX, HEIGHT_PX, DPI = 1080, 1920, 150
SAFE_TOP, SAFE_BOTTOM = 0.875, 0.125          # 3:4-Ausschnitt im Profilraster
ARROW = "→"


def session_meta(data: dict) -> str:
    """„Monza · Race · 2026“ aus der Session."""
    from stintlab.openf1 import SESSION_NAMES
    from stintlab.reels.chase3d import meeting_for
    m = meeting_for(data.get("session_key")) or {}
    return " · ".join(x for x in (m.get("location"), SESSION_NAMES.get(data.get("session_type"), ""),
                                  str(m.get("year") or "")) if x)


def last_name(data: dict, drv: str) -> str:
    """Nachname (für den Kicker) – sonst das Kürzel."""
    from stintlab.openf1 import cached_fetch
    try:
        for d in cached_fetch("drivers", data["session_key"]):
            if d.get("name_acronym") == drv and d.get("last_name"):
                return d["last_name"]
    except Exception:
        pass
    return drv


def cover_path(video: Path) -> Path:
    video = Path(video)
    return video.with_name(video.stem + "_cover.png")


def cover_config(reel: dict) -> dict | None:
    cfg = reel.get("cover", {})
    if cfg is False or (isinstance(cfg, dict) and cfg.get("enabled") is False):
        return None
    if not isinstance(cfg, dict):
        raise ValueError("cover muss eine Tabelle sein, z. B. [reels.cover] mit title = \"…\"")
    return cfg


def _title(fig, x: float, y: float, text: str, size: float, color: str) -> float:
    """Titel links ab x, Grundlinie y. „→“ kommt aus DejaVu (fehlt in Barlow Condensed).
    Gibt die rechte Kante zurück."""
    head = _font(FONT_HEAD)
    fig.canvas.draw()
    inv = fig.transFigure.inverted()
    parts = text.split(ARROW)
    for i, part in enumerate(parts):
        if part:
            t = fig.text(x, y, part, fontsize=size, family=head, fontweight="bold", color=color, va="baseline")
            x = inv.transform(t.get_window_extent(fig.canvas.get_renderer()))[1][0]
        if i < len(parts) - 1:
            t = fig.text(x, y + 0.004, ARROW, fontsize=size * 0.8, family="DejaVu Sans", fontweight="bold",
                         color=COLORS["accent"], va="baseline")
            x = inv.transform(t.get_window_extent(fig.canvas.get_renderer()))[1][0]
    return x


def _fit_size(text: str, base: float = 96) -> float:
    """Große Schrift für kurze Titel, kleiner für lange (Barlow Condensed ≈ 0,42 em pro Zeichen)."""
    n = max(len(line) for line in text.split("\n"))
    return min(base, 1080 * 0.8 / (n * 0.42) * 72 / DPI)


ZOOM = 0.7          # Ausschnitt des Reel-Bildes: Autos ~1,4× größer als im Video
CARS_AT = 0.3       # Höhe des vorderen Autos im Bild (unter dem Titel, über der Wortmarke)


def _zoom_on_cars(ax, scene, t: float) -> None:
    """Bildausschnitt auf die beiden Autos: waagerecht mittig, senkrecht bei CARS_AT."""
    from stintlab.reels.chase3d import Camera
    cam = Camera(scene, t)
    pts = []
    for d in (scene.a, scene.b):
        p, _ = scene.pos(d, t)
        x, y, z = cam.proj(p)
        if z[0] > 1:
            pts.append((x[0], y[0]))
    if not pts:
        return
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    # weit auseinander (Ghost Lap mit Abstand): weniger zoomen, damit beide unter den Titel passen
    z = float(np.clip((max(ys) - min(ys)) / (2 * 0.25), ZOOM, 1.0))
    cx = float(np.clip(np.mean(xs), -0.5625 * (1 - z), 0.5625 * (1 - z)))
    lo = max(-1.0, min(min(ys) - CARS_AT * 2 * z, 1.0 - 2 * z))
    ax.set_xlim(cx - 0.5625 * z, cx + 0.5625 * z)
    ax.set_ylim(lo, lo + 2 * z)


def render_cover(scene, t: float, path: Path, title: str, kicker: str = "", sub: str = "",
                 meta: str = "") -> Path:
    """Ein 3D-Bild der Szene zur Zeit t, darüber Kicker, Titel, Untertitel und Wortmarke."""
    from stintlab.reels.chase3d import draw_scene
    path = Path(path)
    fig = plt.figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI, facecolor=COLORS["bg"])
    ax = fig.add_axes([0, 0, 1, 1], zorder=-2)
    draw_scene(ax, scene, t)
    _zoom_on_cars(ax, scene, t)

    # Abdunkeln oben (Titel) und unten (Wortmarke) – die Mitte bleibt hell
    shade_ax = fig.add_axes([0, 0, 1, 1], zorder=-1)
    shade_ax.axis("off")
    yy = np.linspace(0, 1, 500)
    alpha = np.clip(np.maximum((yy - 0.52) / 0.3, (0.3 - yy) / 0.25), 0, 1) * 0.88
    shade = np.zeros((500, 1, 4))
    shade[:, 0, :3] = [int(COLORS["bg"][i:i + 2], 16) / 255 for i in (1, 3, 5)]
    shade[:, 0, 3] = alpha
    shade_ax.imshow(shade, extent=(0, 1, 0, 1), origin="lower", aspect="auto", interpolation="bilinear")
    shade_ax.set_xlim(0, 1)
    shade_ax.set_ylim(0, 1)

    num, head = _font(FONT_NUM), _font(FONT_HEAD)
    x0 = 0.085
    y = SAFE_TOP - 0.035
    if meta:
        fig.text(x0, y, meta.upper(), fontsize=10, family=num, color=COLORS["muted"], va="center")
        y -= 0.04
    if kicker:
        fig.text(x0, y, kicker.upper(), fontsize=15, family=head, fontweight="bold", color=COLORS["accent"],
                 va="center")
        y -= 0.03
    lines = textwrap.wrap(title.upper(), width=16) or [""]
    size = _fit_size("\n".join(lines))
    line_h = size / 72 * DPI / HEIGHT_PX * 0.98
    top = y
    for line in lines:
        y -= line_h
        _title(fig, x0, y, line, size, COLORS["text"])
    # lila Balken wie auf den Slides
    fig.add_artist(Rectangle((x0 - 0.04, y - 0.006), 0.014, top - y - 0.004, transform=fig.transFigure,
                             color=COLORS["accent"], linewidth=0))
    if sub:
        fig.text(x0, y - 0.035, "\n".join(textwrap.wrap(sub, width=36)), fontsize=16, color=COLORS["text"],
                 va="top", linespacing=1.3, family=_font("Barlow"), fontweight="medium")

    # Wortmarke unten, innerhalb des Profil-Ausschnitts
    yb = SAFE_BOTTOM + 0.05
    lab = fig.text(0.915, yb, "LAB", fontsize=22, fontweight="bold", family=head, color=COLORS["accent"],
                   ha="right", va="center")
    fig.canvas.draw()
    xl = fig.transFigure.inverted().transform(lab.get_window_extent(fig.canvas.get_renderer()))[0][0]
    fig.text(xl, yb, "STINT", fontsize=22, fontweight="bold", family=head, color=COLORS["text"], ha="right",
             va="center")
    fig.text(x0, yb, "DATA · OPENF1", fontsize=9.5, family=num, color=COLORS["muted"], va="center")

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


class CoverOnly(Exception):
    """Wird nach dem Cover geworfen, wenn nur Cover erzeugt werden sollen (make_cover.py) –
    das Reel bricht dann vor dem langen Video-Rendern ab."""


ONLY = False
WITH_COVER = {"comeback", "ghost_lap", "race_story", "gain_loss"}     # Reels mit 3D-Szene


def make_cover(reel: dict, video: Path, scene, t: float, title: str, kicker: str = "", sub: str = "",
               meta: str = "") -> Path | None:
    """Von den Reels aufgerufen: Cover mit den Standardtexten des Reels, post.toml kann alles überschreiben.
    Ein Fehler hier bricht das Reel nicht ab."""
    cfg = cover_config(reel)
    if cfg is None:
        if ONLY:
            raise CoverOnly()
        return None
    try:
        out = render_cover(scene, float(cfg.get("at", t)), cover_path(video), cfg.get("title", title),
                           cfg.get("kicker", kicker), cfg.get("sub", sub), cfg.get("meta", meta))
        print(f"✓ {out}")
    except Exception as exc:
        plt.close("all")
        print(f"⚠ Cover übersprungen: {exc}")
        out = None
    if ONLY:
        raise CoverOnly()
    return out
