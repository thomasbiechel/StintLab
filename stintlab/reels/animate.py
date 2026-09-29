"""Animierte Slide als Reel: eine fertige Balken-Slide baut sich Zeile für Zeile auf.

WOZU: Standbilder als Reel werden sofort weggewischt – es passiert nichts. Hier
wachsen die Balken von unten nach oben, eine Zeile nach der anderen; die
spannendste Zeile (Platz 1, das einseitigste Duell) kommt zuletzt, danach steht
das fertige Bild ein paar Sekunden. Titel/Frage sind von Anfang an da (Hook).

GENERISCH: Funktioniert mit jeder Analyse, die waagrechte Balken (barh) in
Datenkoordinaten zeichnet – championship, title_fight, teammate_duel, … Es
wird nichts neu berechnet: Die fertige Figur wird zerlegt.
  - Zeile = alle Balken und Texte in Datenkoordinaten mit derselben y-Position
  - Balken wachsen von ihrem linken Rand auf die volle Breite
  - Texte der Zeile blenden ein, wenn der Balken fast fertig ist
  - alles andere (Achsen, Linien, Fußnoten, Kopf-/Fußzeile) ist immer sichtbar

FORMAT: Die Slide bleibt 1080 × 1350 (4:5) und wird mittig auf 1080 × 1920
(9:16) gesetzt – oben und unten Hintergrundfarbe (unten liegt ohnehin die
Instagram-Leiste).

In der post.toml: bei einer [[slides]] reel = true → zusätzlich NN_<analyse>_reel.mp4.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
from matplotlib import animation
from matplotlib.patches import Rectangle

from stintlab.style import COLORS, scale_chart_texts

FPS = 30
INTRO_S = 0.6          # nur Titel und leere Achse
ROW_S = 0.55           # so lange wächst ein Balken
STAGGER_S = 0.32       # Abstand zwischen zwei Zeilen
HOLD_S = 3.5           # fertiges Bild am Ende
REEL_W, REEL_H = 1080, 1920


def _ease(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return 1 - (1 - u) ** 3


def rows_of(ax) -> dict[float, dict[str, list]]:
    """{y: {"bars": [...], "texts": [...]}} – nur Artists in Datenkoordinaten.
    Balken = Rechtecke aus barh (Mitte = y + Höhe/2), Texte = ax.text(x, y, …)."""
    rows: dict[float, dict[str, list]] = {}

    def row(y):
        return rows.setdefault(round(float(y), 1), {"bars": [], "texts": []})

    for p in ax.patches:
        # get_data_transform, nicht get_transform: bei Rechtecken ist Letztere mit der
        # Patch-Transformation zusammengesetzt und nie gleich ax.transData
        if isinstance(p, Rectangle) and p.get_data_transform() == ax.transData and p.get_width() != 0:
            row(p.get_y() + p.get_height() / 2)["bars"].append(p)
    for t in ax.texts:
        if t.get_transform() == ax.transData:
            row(t.get_position()[1])["texts"].append(t)
    # Zeilen nur aus Texten ohne Balken (z. B. eine Zahl über der Achse) gelten nicht als Zeile
    return {y: r for y, r in rows.items() if r["bars"]}


def timeline(n_rows: int) -> tuple[float, list[float]]:
    """(Gesamtdauer, Startzeit jeder Zeile von unten nach oben)."""
    starts = [INTRO_S + k * STAGGER_S for k in range(n_rows)]
    end = (starts[-1] + ROW_S) if starts else INTRO_S
    return end + HOLD_S, starts


def animate_slide(fig, ax, path: Path, ffmpeg: str | None = None) -> Path:
    """Schreibt das Reel und lässt die Figur im fertigen Zustand zurück
    (Texte schon vergrößert → danach save_slide(fig, …, scaled=True))."""
    scale_chart_texts(fig)
    rows = rows_of(ax)
    if not rows:
        raise ValueError("Keine waagrechten Balken gefunden – reel = true geht nur bei Balken-Slides")
    order = sorted(rows)                                   # unten (kleines y) zuerst
    total, starts = timeline(len(order))
    widths = {id(b): b.get_width() for r in rows.values() for b in r["bars"]}
    alphas = {id(t): (t.get_alpha() if t.get_alpha() is not None else 1.0)
              for r in rows.values() for t in r["texts"]}

    def draw(t: float) -> None:
        for y, start in zip(order, starts):
            u = _ease((t - start) / ROW_S)
            for b in rows[y]["bars"]:
                b.set_width(widths[id(b)] * u)
            a = min(max((t - start - ROW_S * 0.6) / (ROW_S * 0.5), 0.0), 1.0)
            for tx in rows[y]["texts"]:
                tx.set_alpha(alphas[id(tx)] * a)

    if ffmpeg is None:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    matplotlib.rcParams["animation.ffmpeg_path"] = ffmpeg
    w, h = (int(round(v)) for v in fig.get_size_inches() * fig.dpi)
    bg = COLORS["bg"].lstrip("#")
    pad = f"pad={REEL_W}:{REEL_H}:{(REEL_W - w) // 2}:{(REEL_H - h) // 2}:color=0x{bg}"
    writer = animation.FFMpegWriter(fps=FPS, codec="libx264",
                                    extra_args=["-vf", pad, "-pix_fmt", "yuv420p", "-crf", "20"])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(round(total * FPS))
    with writer.saving(fig, str(path), dpi=fig.dpi):
        for i in range(n):
            draw(i / FPS)
            writer.grab_frame(facecolor=fig.get_facecolor())
    draw(total)                                            # fertiger Zustand für das PNG
    return path
