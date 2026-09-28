"""Podium: die ersten drei als Titel-Slide – typografisch, ohne Fotos.

Warum ohne Fotos: Offizielle Fahrer-Porträts (auch die headshot_url von OpenF1)
sind urheberrechtlich geschützt. Kürzel, Startnummer und Teamfarbe reichen zum
Erkennen und sind unbedenklich.

Qualifying/Sprint-Qualifying: Zeit von P1 im letzten Abschnitt (Q3/SQ3),
Abstände von P2/P3 in diesem Abschnitt. Rennen/Sprint: P1 „WINNER“, dahinter
der offizielle Abstand (oder „+1 LAP“).
"""

from __future__ import annotations

from matplotlib.patches import Polygon

from stintlab.style import COLORS, FONT_HEAD, FONT_NUM, TEXT_SCALE, _font, team_color

HEIGHTS = {1: 0.62, 2: 0.47, 3: 0.36}          # Höhe der Podeste
ORDER = (2, 1, 3)                               # links P2, Mitte P1, rechts P3


def _last(value):
    """Letzter gültiger Wert einer Qualifying-Liste [Q1, Q2, Q3] – sonst der Wert selbst."""
    if isinstance(value, list):
        vals = [v for v in value if v not in (None, "")]
        return vals[-1] if vals else None
    return value


def _fmt_time(sec: float) -> str:
    m, s = divmod(float(sec), 60)
    return f"{int(m)}:{s:06.3f}"


def podium_rows(data: dict) -> list[dict]:
    rows = sorted((r for r in data.get("results", []) if r.get("position") in (1, 2, 3)),
                  key=lambda r: r["position"])
    if len(rows) < 3:
        raise ValueError("Podium braucht ein Ergebnis mit den ersten drei")
    quali = data.get("session_type") in ("Q", "SQ")
    out = []
    for r in rows:
        if r["position"] == 1:
            line = _fmt_time(_last(r.get("duration"))) if quali and _last(r.get("duration")) else "WINNER"
        else:
            g = _last(r.get("gap"))
            line = f"+{g:.3f} s" if isinstance(g, (int, float)) else str(g or "")
        out.append({"pos": r["position"], "driver": r["driver"], "line": line,
                    "team": data.get("teams", {}).get(r["driver"]),
                    "number": data.get("numbers", {}).get(r["driver"])})
    return out


def render_podium(ax, data: dict) -> list[dict]:
    rows = {r["pos"]: r for r in podium_rows(data)}
    head, num = _font(FONT_HEAD), _font(FONT_NUM)
    k = 1 / TEXT_SCALE                      # save_slide vergrößert Grafiktexte – hier schon Endgröße
    ax.set_axis_off()
    ax.set_xlim(0, 3)
    ax.set_ylim(0, 1)

    def text(*a, keep=True, **kw):
        t = ax.text(*a, **kw)
        t.keep_font = keep                  # Titel-Schrift behalten (sonst Monospace)
        return t

    for slot, pos in enumerate(ORDER):
        r = rows[pos]
        h, x0, big = HEIGHTS[pos], slot + 0.08, pos == 1
        col = team_color(r["team"])
        ax.add_patch(Polygon([(x0, 0), (x0 + 0.84, 0), (x0 + 0.84, h), (x0 + 0.1, h + 0.04)], closed=True,
                             color=col, alpha=0.92, linewidth=0))
        text(x0 + 0.44, h - 0.06, f"P{pos}", ha="center", va="top", fontsize=(40 if big else 32) * k,
             family=head, fontweight="bold", color="white")
        text(x0 + 0.44, h + 0.13, r["driver"], ha="center", va="bottom", fontsize=(40 if big else 32) * k,
             family=head, fontweight="bold", color=COLORS["text"])
        text(x0 + 0.44, h + 0.06, r["line"], ha="center", va="bottom", fontsize=15 * k, family=num,
             color=COLORS["muted"], keep=False)
        if r["number"]:
            text(x0 + 0.44, 0.04, f"#{r['number']}", ha="center", va="bottom", fontsize=16 * k, family=num,
                 color="white", alpha=0.85, keep=False)
        text(x0 + 0.44, 0.105, (r["team"] or "").upper(), ha="center", va="bottom", fontsize=8.5 * k,
             family=head, fontweight="bold", color="white", alpha=0.85)
    return list(rows.values())
