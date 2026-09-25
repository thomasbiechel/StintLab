"""Speed Trap: Topspeed und der Kompromiss zwischen Gerade und Kurven.

DATEN: OpenF1 misst auf JEDER Runde an drei Punkten (i1, i2 und die Speed Trap
st auf der Geraden) – auch auf Abkühlrunden (Baku Q: RUS 280–286 km/h auf
Abkühlrunden, 323–328 km/h auf schnellen Runden).

WINDSCHATTEN: Der Höchstwert einer Session kann aus einer zufälligen Runde
hinter einem anderen Auto stammen. Deshalb zählt als Hauptwert die Speed Trap
auf der SCHNELLSTEN Runde jedes Fahrers – dort hat jeder ernsthaft gepusht.
Der Session-Höchstwert wird nur zusätzlich angezeigt.

Slide 1 (top_speed): Punktdiagramm, keine Balken – Balken ab einem Wert über
null würden die Unterschiede optisch übertreiben.
Slide 2 (speed_vs_sector): Topspeed gegen Zeit im kurvigen Sektor. Zeigt den
Abstimmungskompromiss: wenig Luftwiderstand vs. viel Abtrieb.
"""

from __future__ import annotations

from statistics import median

from stintlab.analyses.ideal_lap import _valid_laps
from stintlab.quali import lap_parts
from stintlab.style import COLORS, style_axes, team_color

SECTOR_KEYS = {1: "Sector1", 2: "Sector2", 3: "Sector3"}


def speed_rows(data: dict, part: str | None = None, compound: str | None = None,
               sector: int = 2) -> tuple[list[dict], list[str]]:
    """Pro Fahrer: Speed Trap und Sektorzeit seiner schnellsten gültigen Runde,
    dazu der Speed-Trap-Höchstwert aller seiner Runden im gleichen Abschnitt.
    Zweiter Rückgabewert: Fahrer ohne Speed-Trap-Wert auf der schnellsten Runde."""
    valid = _valid_laps(data, compound, part)
    part_of = lap_parts(data) if part else {}
    key = SECTOR_KEYS[sector]
    rows, missing = [], []
    for drv, laps in valid.items():
        timed = [l for l in laps if l.get("LapTime")]
        if not timed:
            continue
        best = min(timed, key=lambda l: float(l["LapTime"]))
        if best.get("SpeedST") is None:
            missing.append(drv)
            continue
        # Höchstwert: alle Runden des Fahrers (auch Out-Laps, Abkühlrunden),
        # im selben Q-Abschnitt, falls part gesetzt ist
        all_laps = [l for l in data.get("laps", []) if l["Driver"] == drv
                    and (not part or part_of.get((drv, l["LapNumber"])) == part)]
        top = max((l["SpeedST"] for l in all_laps if l.get("SpeedST") is not None), default=best["SpeedST"])
        rows.append({"driver": drv, "st": best["SpeedST"], "max": max(top, best["SpeedST"]),
                     "sector": float(best[key]) if best.get(key) else None,
                     "lap": float(best["LapTime"])})
    return sorted(rows, key=lambda r: -r["st"]), sorted(missing)


def render_top_speed(ax, data: dict, part: str | None = None, compound: str | None = None) -> list[dict]:
    rows, missing = speed_rows(data, part, compound)
    if not rows:
        raise ValueError("Keine Speed-Trap-Werte gefunden – part/compound prüfen")
    teams = data.get("teams", {})
    colors = [team_color(teams.get(r["driver"])) for r in rows]

    style_axes(ax, grid_axis="x")
    y = list(range(len(rows)))
    lo = min(r["st"] for r in rows) - 4
    hi = max(r["max"] for r in rows) + 2
    for i, (r, c) in enumerate(zip(rows, colors)):
        ax.plot([lo, r["st"]], [i, i], color=c, linewidth=1.2, alpha=0.5)
        ax.scatter([r["st"]], [i], s=70, color=c, zorder=5)
        if r["max"] > r["st"]:
            ax.scatter([r["max"]], [i], s=45, facecolor="none", edgecolor=c, linewidth=1.2, zorder=5)
        label = f"{r['st']:.0f} km/h" + (f"  ·  max {r['max']:.0f}" if r["max"] > r["st"] else "")
        ax.text(hi + 0.5, i, label, va="center", fontsize=8, color=COLORS["text"])
    ax.invert_yaxis()
    ax.set_yticks(y)
    ax.set_yticklabels([r["driver"] for r in rows], fontsize=9, fontweight="bold")
    for tick, c in zip(ax.get_yticklabels(), colors):
        tick.set_color(c)
    ax.set_xlim(lo, hi + (hi - lo) * 0.45)
    ax.set_xlabel("Speed trap (km/h)")

    notes = ["● on fastest lap  ·  ○ session max (may include slipstream)"]
    if missing:
        notes.insert(0, "No speed trap value: " + ", ".join(missing))
    ax.set_ylim(len(rows) - 0.5 + 0.55 * len(notes) + 0.3, -0.6)
    ax.text(0.99, 0.02, "\n".join(notes), transform=ax.transAxes, ha="right", va="bottom",
            fontsize=7.5, color=COLORS["muted"], linespacing=1.5)
    return rows


def render_speed_vs_sector(ax, data: dict, sector: int = 2, part: str | None = None,
                           compound: str | None = None) -> list[dict]:
    if sector not in SECTOR_KEYS:
        raise ValueError("sector muss 1, 2 oder 3 sein")
    rows, _ = speed_rows(data, part, compound, sector)
    rows = [r for r in rows if r["sector"] is not None]
    if len(rows) < 3:
        raise ValueError("Zu wenige Fahrer mit Speed Trap und Sektorzeit")
    teams = data.get("teams", {})

    style_axes(ax, grid_axis="both")
    xs, ys = [r["st"] for r in rows], [r["sector"] for r in rows]
    mx, my = median(xs), median(ys)
    ax.axvline(mx, color=COLORS["grid"], linewidth=1, linestyle="--", zorder=1)
    ax.axhline(my, color=COLORS["grid"], linewidth=1, linestyle="--", zorder=1)
    for r in rows:
        c = team_color(teams.get(r["driver"]))
        ax.scatter([r["st"]], [r["sector"]], s=80, color=c, zorder=5)
        ax.annotate(r["driver"], (r["st"], r["sector"]), xytext=(6, 4), textcoords="offset points",
                    fontsize=8, color=c, fontweight="bold")
    ax.invert_yaxis()                     # schnellere Sektorzeit oben
    pad_x = (max(xs) - min(xs)) * 0.12 or 1
    pad_y = (max(ys) - min(ys)) * 0.12 or 0.1
    ax.set_xlim(min(xs) - pad_x, max(xs) + pad_x * 2)
    ax.set_ylim(max(ys) + pad_y, min(ys) - pad_y)
    ax.set_xlabel("Speed trap on fastest lap (km/h)  →  faster on the straight")
    ax.set_ylabel(f"Sector {sector} time on fastest lap (s)  ↑ faster")

    # Ecken beschriften – beschreibend, keine Behauptung über einzelne Teams
    kw = dict(transform=ax.transAxes, fontsize=7.5, color=COLORS["muted"])
    ax.text(0.98, 0.98, "fast on both", ha="right", va="top", **kw)
    ax.text(0.02, 0.98, "strong in the corners", ha="left", va="top", **kw)
    ax.text(0.98, 0.02, "strong on the straight", ha="right", va="bottom", **kw)
    return rows
