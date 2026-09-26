"""StintLab – einheitlicher Stil für Instagram-Slides (4:5, 1080 x 1350 px).

Trennung der Aufgaben:
- Analyse-Funktionen zeichnen nur Daten auf eine Matplotlib-Achse (ax).
- Dieses Modul kümmert sich um alles andere: Format, Farben, Schrift,
  Titel, Quelle und das StintLab-Logo.
"""

from functools import lru_cache
from pathlib import Path
import textwrap

import matplotlib
matplotlib.use("Agg")  # nur Dateien rendern, kein Fenster – braucht kein Tk
import matplotlib.pyplot as plt

# ── Format ─────────────────────────────────────────────────────────────
WIDTH_PX, HEIGHT_PX, DPI = 1080, 1350, 150
FIGSIZE = (WIDTH_PX / DPI, HEIGHT_PX / DPI)  # (7.2, 9.0) Zoll

# ── Farben (übernommen aus report_style.py des F1 Data Analyser) ───────
# Regel: Daten werden IMMER in Teamfarben gezeichnet. Die Akzentfarbe ist nur
# für Marke und neutrale Hervorhebungen da – sonst verwechselt man sie mit
# einem Team (z. B. Orange = McLaren) oder einer Reifenmischung (Rot = Soft).
COLORS = {
    "bg": "#0a0a0a",       # Hintergrund der Slide
    "plot": "#141418",     # Hintergrund der Zeichenfläche
    "text": "#e9e9ed",     # Haupttext
    "muted": "#8a8a92",    # Untertitel, Achsen, Quelle
    "grid": "#26262e",     # Gitternetz
    "accent": "#a855f7",   # StintLab-Lila ("schnellster Sektor"), kein Team, keine Mischung
}

# Offizielle team_colour-Werte von OpenF1 (/drivers), Saison 2026
TEAM_COLORS = {
    "Alpine": "#00A1E8",
    "Aston Martin": "#229971",
    "Audi": "#F50537",
    "Cadillac": "#909090",
    "Ferrari": "#ED1131",
    "Haas F1 Team": "#9C9FA2",
    "McLaren": "#F47600",
    "Mercedes": "#00D7B6",
    "Racing Bulls": "#6C98FF",
    "Red Bull Racing": "#4781D7",
    "Williams": "#1868DB",
}


def team_color(team):
    """Teamfarbe als Hex-Wert – neutrales Grau für unbekannte Teams."""
    return TEAM_COLORS.get(team or "", COLORS["muted"])

# Untertitel: Zeichen pro Zeile und maximale Zeilenzahl
SUBTITLE_WIDTH = 88
SUBTITLE_MAX_LINES = 2

# Inter, falls installiert – sonst Fallback auf Windows- bzw. Standardschrift
FONT_FAMILY = ["Inter", "Segoe UI", "DejaVu Sans"]


@lru_cache(maxsize=1)
def resolve_font() -> str:
    """Erste installierte Schrift aus FONT_FAMILY – einmal ermittelt.

    Übergibt man matplotlib die ganze Liste, meldet es bei JEDEM Text
    "findfont: Font family 'Inter' not found". Beim Reel (>1000 Bilder)
    füllte das die Konsole und bremste das Rendern.
    """
    from matplotlib import font_manager
    installed = {f.name for f in font_manager.fontManager.ttflist}
    return next((f for f in FONT_FAMILY if f in installed), "DejaVu Sans")


def apply_theme():
    """Setzt die Matplotlib-Grundeinstellungen für alle folgenden Plots."""
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": [resolve_font()],
        "figure.facecolor": COLORS["bg"],
        "axes.facecolor": COLORS["plot"],
        "axes.edgecolor": COLORS["grid"],
        "axes.labelcolor": COLORS["muted"],
        "axes.grid": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "grid.color": COLORS["grid"],
        "grid.linewidth": 0.6,
        "xtick.color": COLORS["muted"],
        "ytick.color": COLORS["muted"],
        "text.color": COLORS["text"],
        "legend.frameon": False,
        "legend.labelcolor": COLORS["text"],
    })


def style_axes(ax, grid_axis="y"):
    """Einheitlicher Achsen-Look: nur die untere Achsenlinie, dezentes Gitter."""
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(COLORS["grid"])
    ax.tick_params(colors=COLORS["muted"], labelsize=9)
    ax.grid(False)
    if grid_axis:
        ax.grid(axis=grid_axis, color=COLORS["grid"], linewidth=0.6)
    ax.set_axisbelow(True)


def new_slide(title, subtitle="", source="Data: OpenF1"):
    """Erstellt eine leere Slide mit Kopf- und Fußzeile.

    Gibt (fig, ax) zurück – auf ax zeichnet die Analyse-Funktion.
    """
    apply_theme()
    fig = plt.figure(figsize=FIGSIZE, dpi=DPI)

    # Feste Position der Zeichenfläche: [links, unten, Breite, Höhe] in Anteilen
    ax = fig.add_axes([0.12, 0.10, 0.82, 0.68])

    # Kopfzeile – lange Titel werden automatisch umgebrochen
    wrapped = textwrap.fill(title, width=32)
    fig.text(0.06, 0.95, wrapped, fontsize=19, fontweight="bold",
             color=COLORS["text"], va="top", ha="left")
    if subtitle:
        # Untertitel umbrechen, aber höchstens zwei Zeilen – mehr liest auf
        # Instagram niemand, und darunter beginnt schon die Grafik
        lines = textwrap.wrap(subtitle, width=SUBTITLE_WIDTH)
        if len(lines) > SUBTITLE_MAX_LINES:
            raise ValueError(
                f"Untertitel zu lang ({len(subtitle)} Zeichen, {len(lines)} Zeilen). "
                f"Maximal {SUBTITLE_MAX_LINES} Zeilen à ~{SUBTITLE_WIDTH} Zeichen – bitte kürzen."
            )
        subtitle = "\n".join(lines)
        fig.text(0.06, 0.845, subtitle, fontsize=10.5, linespacing=1.4,
                 color=COLORS["muted"], va="top", ha="left")

    # Fußzeile
    fig.text(0.06, 0.03, source, fontsize=8, color=COLORS["muted"])
    fig.text(0.94, 0.03, "STINTLAB", fontsize=9, fontweight="bold",
             color=COLORS["accent"], ha="right")

    return fig, ax


def save_slide(fig, path):
    """Speichert die Slide exakt in 1080 x 1350 px und schließt die Figur."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Kein bbox_inches="tight" – das würde die Pixelgröße verändern
    fig.savefig(path, dpi=DPI, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path