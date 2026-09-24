"""StintLab – einheitlicher Stil für Instagram-Slides (4:5, 1080 x 1350 px).

Trennung der Aufgaben:
- Analyse-Funktionen zeichnen nur Daten auf eine Matplotlib-Achse (ax).
- Dieses Modul kümmert sich um alles andere: Format, Farben, Schrift,
  Titel, Quelle und das StintLab-Logo.
"""

from pathlib import Path
import textwrap

import matplotlib.pyplot as plt

# ── Format ─────────────────────────────────────────────────────────────
WIDTH_PX, HEIGHT_PX, DPI = 1080, 1350, 150
FIGSIZE = (WIDTH_PX / DPI, HEIGHT_PX / DPI)  # (7.2, 9.0) Zoll

# ── Farben (Platzhalter – durch deine Palette aus dem PDF-Report ersetzen) ─
COLORS = {
    "bg": "#0f1115",       # Hintergrund
    "text": "#f2f2f2",     # Haupttext
    "muted": "#9aa0a6",    # Untertitel, Achsen, Quelle
    "grid": "#2a2f36",     # Gitternetz
    "accent": "#ff5a1f",   # Hervorhebung (bewusst kein F1-Rot)
}

# Inter, falls installiert – sonst Fallback auf Windows- bzw. Standardschrift
FONT_FAMILY = ["Inter", "Segoe UI", "DejaVu Sans"]


def apply_theme():
    """Setzt die Matplotlib-Grundeinstellungen für alle folgenden Plots."""
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": FONT_FAMILY,
        "figure.facecolor": COLORS["bg"],
        "axes.facecolor": COLORS["bg"],
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
        fig.text(0.06, 0.845, subtitle, fontsize=10.5,
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