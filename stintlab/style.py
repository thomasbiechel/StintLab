"""StintLab – einheitlicher Stil für Instagram-Slides (4:5, 1080 x 1350 px).

Trennung der Aufgaben:
- Analyse-Funktionen zeichnen nur Daten auf eine Matplotlib-Achse (ax).
- Dieses Modul kümmert sich um alles andere: Format, Farben, Schrift,
  Titel, Quelle und das StintLab-Logo.

DESIGN (Sept. 2026, „Lower Third“): Kopfzeile in Monospace (Strecke · Session ·
Jahr, rechts Seitenzahl), Titel in Barlow Condensed Bold, links davon ein lila
Balken, Untertitel direkt darunter; unten dünne Linie, Quelle und Wortzeichen
STINT+LAB. Zahlen und Achsen in JetBrains Mono. Beim Speichern werden alle
Texte der Grafik um TEXT_SCALE vergrößert – vorher waren sie auf dem Handy
~1,5 mm hoch. Schriften liegen in assets/fonts (SIL Open Font License).
"""

from functools import lru_cache
from pathlib import Path
import textwrap

import matplotlib
matplotlib.use("Agg")  # nur Dateien rendern, kein Fenster – braucht kein Tk
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle

# Mitgelieferte Schriften registrieren (keine Installation in Windows nötig)
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
for _f in sorted(FONT_DIR.glob("*.ttf")):
    try:
        font_manager.fontManager.addfont(str(_f))
    except (OSError, RuntimeError):
        pass

# ── Format ─────────────────────────────────────────────────────────────
WIDTH_PX, HEIGHT_PX, DPI = 1080, 1350, 150
FIGSIZE = (WIDTH_PX / DPI, HEIGHT_PX / DPI)  # (7.2, 9.0) Zoll

# ── Farben (übernommen aus report_style.py des F1 Data Analyser) ───────
# Regel: Daten werden IMMER in Teamfarben gezeichnet. Die Akzentfarbe ist nur
# für Marke und neutrale Hervorhebungen da – sonst verwechselt man sie mit
# einem Team (z. B. Orange = McLaren) oder einer Reifenmischung (Rot = Soft).
COLORS = {
    "bg": "#0a0b0e",       # Hintergrund der Slide (die Grafik steht ohne eigenen Kasten darauf)
    "plot": "#14161c",     # Zeilenstreifen in Tabellen (Ergebnis, Sektoren)
    "text": "#e9e9ed",     # Haupttext
    "muted": "#8b93a1",    # Untertitel, Achsen, Quelle
    "grid": "#1d2029",     # Gitternetz, Fußlinie
    "accent": "#a855f7",   # StintLab-Lila ("schnellster Sektor"), kein Team, keine Mischung
}

# Neutralisationen – feste Signalfarben wie die echten Flaggen/Tafeln.
# (Farbe, langer Name, kurzes Label, Textfarbe auf der Farbe)
NEUTRAL_STYLE = {
    "SC":  ("#f5c518", "SAFETY CAR", "SC", "black"),
    "VSC": ("#f5c518", "VIRTUAL SAFETY CAR", "VSC", "black"),
    "RED": ("#e10600", "RED FLAG", "RED FLAG", "white"),
}


def neutral_legend(kinds) -> str:
    """Fußzeilen-Text zu den Farben, z. B. "yellow = SC/VSC · red = red flag"."""
    kinds = set(kinds)
    parts = []
    if kinds & {"SC", "VSC"} or not kinds:
        parts.append("yellow = SC/VSC")
    if "RED" in kinds:
        parts.append("red = red flag")
    return " · ".join(parts)


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

# Mitgeliefert (assets/fonts) – Fallback auf Windows- bzw. Standardschrift
FONT_FAMILY = ["Barlow", "Inter", "Segoe UI", "DejaVu Sans"]
FONT_HEAD = "Barlow Condensed"     # Titel, Wortzeichen
FONT_NUM = "JetBrains Mono"        # Zahlen, Achsen, Kopfzeile
TEXT_SCALE = 1.3                   # Grafiktexte beim Speichern vergrößern (Handy)
TITLE_WIDTH = 26                   # Zeichen pro Titelzeile (schmale Großbuchstaben)


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
        # Liste direkt in font.family: nur so nimmt matplotlib für fehlende Zeichen die
        # nächste Schrift (Barlow hat kein ▲ ▼ – Telemetrie, ideale Runde)
        "font.family": [resolve_font(), "DejaVu Sans"],
        "font.sans-serif": [resolve_font(), "DejaVu Sans"],
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


def _has_font(name: str) -> bool:
    return any(f.name == name for f in font_manager.fontManager.ttflist)


def _font(name: str) -> str:
    return name if _has_font(name) else resolve_font()


def new_slide(title, subtitle="", source="Data: OpenF1", meta: str | None = None, page: str | None = None):
    """Erstellt eine leere Slide mit Kopf- und Fußzeile.

    meta: Kopfzeile links, z. B. "Baku · Qualifying · 2026"; page: rechts, z. B. "02 / 05".
    Gibt (fig, ax) zurück – auf ax zeichnet die Analyse-Funktion.
    """
    apply_theme()
    fig = plt.figure(figsize=FIGSIZE, dpi=DPI)
    head, num = _font(FONT_HEAD), _font(FONT_NUM)

    # Kopfzeile
    if meta:
        fig.text(0.075, 0.962, meta.upper(), fontsize=9, color=COLORS["muted"], family=num, va="center")
    if page:
        fig.text(0.94, 0.962, page, fontsize=9, color=COLORS["muted"], family=num, va="center", ha="right")

    # Titel – schmale Großbuchstaben, lange Titel werden umgebrochen
    t_title = fig.text(0.075, 0.935, textwrap.fill(title.upper(), width=TITLE_WIDTH), fontsize=34,
                       fontweight="bold", family=head, color=COLORS["text"], va="top", ha="left", linespacing=0.95)
    fig.canvas.draw()
    bb = t_title.get_window_extent().transformed(fig.transFigure.inverted())
    # lila Balken links neben dem Titel, genau so hoch wie der Titel
    fig.add_artist(Rectangle((0.045, bb.y0 - 0.004), 0.013, bb.height + 0.008, transform=fig.transFigure,
                             color=COLORS["accent"], linewidth=0))
    bottom = bb.y0
    if subtitle:
        # Untertitel umbrechen, aber höchstens zwei Zeilen – mehr liest auf
        # Instagram niemand, und darunter beginnt schon die Grafik
        lines = textwrap.wrap(subtitle, width=SUBTITLE_WIDTH)
        if len(lines) > SUBTITLE_MAX_LINES:
            raise ValueError(
                f"Untertitel zu lang ({len(subtitle)} Zeichen, {len(lines)} Zeilen). "
                f"Maximal {SUBTITLE_MAX_LINES} Zeilen à ~{SUBTITLE_WIDTH} Zeichen – bitte kürzen."
            )
        t_sub = fig.text(0.075, bb.y0 - 0.018, "\n".join(lines), fontsize=11.5, linespacing=1.35,
                         color=COLORS["muted"], va="top", ha="left")
        fig.canvas.draw()
        bottom = t_sub.get_window_extent().transformed(fig.transFigure.inverted()).y0

    # Fußzeile: dünne Linie, Quelle, Wortzeichen STINT + LAB
    fig.add_artist(Rectangle((0.06, 0.047), 0.88, 0.0012, transform=fig.transFigure, color=COLORS["grid"],
                             linewidth=0))
    fig.text(0.06, 0.028, source.upper().replace(": ", " · "), fontsize=8.5, color=COLORS["muted"], family=num,
             va="center")
    lab = fig.text(0.94, 0.028, "LAB", fontsize=15, fontweight="bold", family=head, color=COLORS["accent"],
                   ha="right", va="center")
    fig.canvas.draw()
    x0 = lab.get_window_extent().transformed(fig.transFigure.inverted()).x0
    fig.text(x0, 0.028, "STINT", fontsize=15, fontweight="bold", family=head, color=COLORS["text"],
             ha="right", va="center")

    # Zeichenfläche: direkt unter dem Untertitel (Platz für Beschriftungen oberhalb der Achse),
    # höchstens bis 0,76 – bei kurzen Titeln bekommt die Grafik mehr Höhe statt einer Lücke
    top = min(bottom - 0.06, 0.76)
    ax = fig.add_axes([0.11, 0.115, 0.83, top - 0.115])
    return fig, ax


def scale_chart_texts(fig, factor: float = TEXT_SCALE) -> None:
    """Alle Texte in den Zeichenflächen vergrößern und Zahlen/Achsen in Monospace –
    die Analysen setzen 7,5–9 pt, auf dem Handy ~1,5 mm. Kopf- und Fußzeile
    (Texte der Figur, nicht der Achsen) bleiben unverändert."""
    num = _font(FONT_NUM)
    for ax in fig.axes:
        texts = list(ax.texts) + ax.get_xticklabels() + ax.get_yticklabels()
        legend = ax.get_legend()
        if legend:
            texts += legend.get_texts()
        for t in texts:
            t.set_fontsize(t.get_fontsize() * factor)
            # Monospace nur für Texte mit Ziffern (Zeiten, Abstände, Achsenwerte) – Namen bleiben in
            # Barlow, sonst werden lange Achsenbeschriftungen („Aston Martin“) links abgeschnitten
            if not getattr(t, "keep_font", False) and any(ch.isdigit() for ch in t.get_text()):
                t.set_fontfamily(num)
        for lab in (ax.xaxis.label, ax.yaxis.label, ax.title):
            lab.set_fontsize(lab.get_fontsize() * factor)


def save_slide(fig, path):
    """Speichert die Slide exakt in 1080 x 1350 px und schließt die Figur."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    scale_chart_texts(fig)
    # Kein bbox_inches="tight" – das würde die Pixelgröße verändern
    fig.savefig(path, dpi=DPI, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def shade_neutral(ax, race_control: list[dict], first: int, last: int) -> None:
    """Neutralisierte Runden hinterlegen: SC/VSC grau, rote Flagge rot mit Label."""
    from matplotlib.transforms import blended_transform_factory
    from stintlab.race_control import neutral_phases
    for lo, hi, kind in neutral_phases(race_control, first, last):
        if kind == "RED":
            color = NEUTRAL_STYLE["RED"][0]
            ax.axvspan(lo - 0.5, hi + 0.5, color=color, alpha=0.22, linewidth=0, zorder=0)
            ax.text((lo + hi) / 2, 0.985, "RED FLAG", transform=blended_transform_factory(ax.transData, ax.transAxes),
                    ha="center", va="top", fontsize=7, fontweight="bold", color=color, zorder=6)
        else:
            ax.axvspan(lo - 0.5, hi + 0.5, color=COLORS["muted"], alpha=0.15, linewidth=0, zorder=0)
