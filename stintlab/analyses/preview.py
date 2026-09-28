"""Die vier Slides des Race Previews (Session-Typ "PREVIEW").

Daten: stintlab.preview.build_preview – einmal geladen, hier nur gezeichnet.
Alle Schriftgrößen sind Endgrößen (save_slide vergrößert Grafiktexte um
TEXT_SCALE, deshalb hier · k).
"""

from __future__ import annotations

import math

import numpy as np
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

from stintlab.style import COLORS, FONT_HEAD, FONT_NUM, TEXT_SCALE, _font, team_color

k = 1 / TEXT_SCALE
SHORT = {"Red Bull Racing": "Red Bull", "Haas F1 Team": "Haas"}
WEEKDAY = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def short_team(team: str | None) -> str:
    return SHORT.get(team, team or "–")


def _text(ax, *a, keep=True, **kw):
    t = ax.text(*a, **kw)
    t.keep_font = keep
    return t


def _blank(ax):
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)


def _pct(v: float | None) -> str:
    return "–" if v is None else f"+{v:.2f} %"


# ------------------------------------------------------------------ 1 Strecke + Eckdaten
def _facts(hist: dict | None, meeting: dict) -> list[tuple[str, str, str, str | None]]:
    """[(Überschrift, großer Wert, kleine Zeile, Teamfarbe)]."""
    if not hist:
        return [("LAST RACE HERE", "–", "no results found", None)]
    y = hist["year"]
    out = []
    if hist.get("winner"):
        out.append((f"WINNER {y}", hist["winner"], short_team(hist.get("winner_team")), hist.get("winner_team")))
    if hist.get("pole"):
        out.append((f"POLE {y}", hist["pole"], short_team(hist.get("pole_team")), hist.get("pole_team")))
    f = hist.get("fastest")
    if f:
        lap = f" · lap {f['lap']}" if f.get("lap") else ""
        out.append((f"FASTEST LAP {y}", f["text"], f"{f['driver']}{lap}", f.get("team")))
    if hist.get("laps"):
        out.append(("RACE LAPS", str(hist["laps"]), f"{y} distance", None))
    return out


def render_track(ax, data: dict) -> dict:
    _blank(ax)
    fig = ax.figure
    x0, y0, w, h = ax.get_position().bounds
    layout = data.get("layout")
    head, num = _font(FONT_HEAD), _font(FONT_NUM)

    # Strecke oben (≈ 70 %), Eckdaten unten
    tax = fig.add_axes([x0 - 0.04, y0 + h * 0.27, w + 0.06, h * 0.75])
    tax.set_axis_off()
    if layout:
        xs, ys = np.asarray(layout["x"], float), np.asarray(layout["y"], float)
        xs, ys = np.append(xs, xs[0]), np.append(ys, ys[0])      # Runde schließen
        tax.plot(xs, ys, color=COLORS["grid"], linewidth=13, solid_capstyle="round", zorder=1)
        tax.plot(xs, ys, color=COLORS["text"], linewidth=4.2, solid_capstyle="round", zorder=2)
        span = max(np.ptp(xs), np.ptp(ys))
        # Fahrtrichtung: Pfeil ein Stück nach dem Start
        i = max(3, len(xs) // 40)
        tax.annotate("", xy=(xs[i + 2], ys[i + 2]), xytext=(xs[i - 2], ys[i - 2]), zorder=4,
                     arrowprops={"arrowstyle": "-|>", "color": COLORS["accent"], "lw": 2.5, "mutation_scale": 22})
        if layout.get("source") == "openf1":
            # Start/Ziel: Linie quer zur Strecke am Rundenanfang (echter Zeitpunkt der Linie)
            dx, dy = xs[2] - xs[0], ys[2] - ys[0]
            n = math.hypot(dx, dy) or 1
            px, py = -dy / n * span * 0.03, dx / n * span * 0.03
            tax.plot([xs[0] - px, xs[0] + px], [ys[0] - py, ys[0] + py], color=COLORS["accent"], lw=4, zorder=3)
        for c in layout.get("corners", []):
            lx, ly = c.get("lx", c["x"]), c.get("ly", c["y"])
            tax.add_patch(Circle((lx, ly), span * 0.021, color=COLORS["bg"], ec=COLORS["muted"], lw=0.8, zorder=5))
            _text(tax, lx, ly, c["number"], ha="center", va="center", fontsize=7.5 * k, color=COLORS["text"],
                  family=num, zorder=6, keep=False)
        tax.set_aspect("equal", adjustable="datalim")
        pad = span * 0.05
        tax.set_xlim(xs.min() - pad, xs.max() + pad)
        tax.set_ylim(ys.min() - pad, ys.max() + pad)
    else:
        _text(tax, 0.5, 0.5, "TRACK MAP NOT AVAILABLE", ha="center", va="center", fontsize=18 * k,
              family=head, fontweight="bold", color=COLORS["muted"], transform=tax.transAxes)

    # Eckdaten-Kacheln
    facts = _facts(data.get("history"), data["meeting"])
    n = len(facts)
    gap = 0.025
    cw = (1 - gap * (n - 1)) / n
    for j, (label, big, small, team) in enumerate(facts):
        cx = j * (cw + gap)
        ax.add_patch(FancyBboxPatch((cx, 0.0), cw, 0.23, boxstyle="round,pad=0,rounding_size=0.015",
                                    color=COLORS["plot"], linewidth=0, transform=ax.transAxes))
        if team:
            ax.add_patch(Rectangle((cx, 0.0), 0.012, 0.23, color=team_color(team), linewidth=0))
        _text(ax, cx + 0.035, 0.19, label, fontsize=8 * k, family=num, color=COLORS["muted"], va="center", keep=True)
        size = 30 if len(big) <= 4 else 23
        _text(ax, cx + 0.035, 0.105, big, fontsize=size * k, family=head, fontweight="bold",
              color=COLORS["text"], va="center")
        _text(ax, cx + 0.035, 0.035, small, fontsize=8.5 * k, color=COLORS["muted"], va="center",
              keep=not any(ch.isdigit() for ch in small))
    return {"facts": facts}


# ------------------------------------------------------------------ 2 Wetter
def _icon(ax, cx, cy, r, code, rain_pct):
    """Einfaches Symbol aus Formen: Sonne, Wolke, Regen, Gewitter (WMO-Code von Open-Meteo)."""
    sun, cloud = "#f5c518", "#9aa3b2"
    code = code if code is not None else (61 if (rain_pct or 0) >= 55 else 3 if (rain_pct or 0) >= 25 else 0)
    if code <= 2:
        sx, sy = (cx, cy) if code <= 1 else (cx + r * 0.35, cy + r * 0.35)
        ax.add_patch(Circle((sx, sy), r * 0.42, color=sun, lw=0, zorder=3))
        for a in np.linspace(0, 2 * np.pi, 8, endpoint=False):
            ax.plot([sx + r * 0.58 * np.cos(a), sx + r * 0.78 * np.cos(a)],
                    [sy + r * 0.58 * np.sin(a) * 0.8, sy + r * 0.78 * np.sin(a) * 0.8], color=sun, lw=2.2, zorder=3)
        if code <= 1:
            return
    for dx, dy, rr in ((-0.35, -0.1, 0.36), (0.05, 0.08, 0.46), (0.42, -0.1, 0.34)):
        ax.add_patch(Circle((cx + dx * r, cy + dy * r * 0.8), rr * r, color=cloud, lw=0, zorder=4))
    ax.add_patch(Rectangle((cx - 0.35 * r, cy - 0.44 * r * 0.8), 0.77 * r, 0.3 * r * 0.8, color=cloud, lw=0, zorder=4))
    if code >= 51:
        drop = "#4ea8ff"
        for dx in (-0.35, 0.0, 0.35):
            ax.plot([cx + dx * r, cx + (dx - 0.1) * r], [cy - 0.6 * r * 0.8, cy - 0.95 * r * 0.8],
                    color=drop, lw=2.4, solid_capstyle="round", zorder=4)
    if code >= 95:
        ax.plot([cx + 0.05 * r, cx - 0.1 * r, cx + 0.08 * r, cx - 0.05 * r],
                [cy - 0.45 * r * 0.8, cy - 0.75 * r * 0.8, cy - 0.75 * r * 0.8, cy - 1.05 * r * 0.8],
                color="#f5c518", lw=2.2, zorder=5)


def render_weather(ax, data: dict) -> list[dict]:
    w = data.get("weather")
    if not w or not w.get("days"):
        raise ValueError("Keine Wettervorhersage – Open-Meteo reicht 16 Tage voraus; "
                         "preview.py näher am Wochenende noch einmal ausführen")
    _blank(ax)
    head, num = _font(FONT_HEAD), _font(FONT_NUM)
    days = w["days"][-3:]
    n = len(days)
    gap = 0.03
    cw = (1 - gap * (n - 1)) / n
    for j, d in enumerate(days):
        x = j * (cw + gap)
        mid = x + cw / 2
        ax.add_patch(FancyBboxPatch((x, 0.1), cw, 0.9, boxstyle="round,pad=0,rounding_size=0.02",
                                    color=COLORS["plot"], linewidth=0))
        is_race = "RACE" in d["sessions"]
        if is_race:
            ax.add_patch(Rectangle((x, 0.985), cw, 0.015, color=COLORS["accent"], linewidth=0))
        _text(ax, mid, 0.93, WEEKDAY[d["date"].weekday()], ha="center", va="center", fontsize=26 * k,
              family=head, fontweight="bold", color=COLORS["text"])
        _text(ax, mid, 0.875, d["date"].strftime("%d %b").upper(), ha="center", va="center", fontsize=9 * k,
              family=num, color=COLORS["muted"], keep=False)
        _text(ax, mid, 0.83, " · ".join(d["sessions"]) or "–", ha="center", va="center", fontsize=9 * k,
              family=head, fontweight="bold", color=COLORS["accent"] if is_race else COLORS["muted"],
              keep=True)
        _icon(ax, mid, 0.715, cw * 0.28, d.get("code"), d.get("rain_pct"))
        if d.get("tmax") is not None:
            _text(ax, mid, 0.55, f"{d['tmax']:.0f}°", ha="center", va="center", fontsize=40 * k, family=head,
                  fontweight="bold", color=COLORS["text"])
        if d.get("tmin") is not None:
            _text(ax, mid, 0.475, f"min {d['tmin']:.0f}°", ha="center", va="center", fontsize=10 * k,
                  family=num, color=COLORS["muted"], keep=False)
        # Regen: Wahrscheinlichkeit als Balken
        rp = d.get("rain_pct") or 0
        _text(ax, x + 0.03, 0.39, "RAIN", fontsize=8 * k, family=num, color=COLORS["muted"], va="center")
        _text(ax, x + cw - 0.03, 0.39, f"{rp:.0f} %", fontsize=11 * k, family=num, color=COLORS["text"],
              va="center", ha="right", fontweight="bold", keep=False)
        ax.add_patch(Rectangle((x + 0.03, 0.345), cw - 0.06, 0.018, color=COLORS["grid"], linewidth=0))
        ax.add_patch(Rectangle((x + 0.03, 0.345), (cw - 0.06) * min(rp, 100) / 100, 0.018,
                               color="#4ea8ff", linewidth=0))
        if d.get("wind") is not None:
            _text(ax, x + 0.03, 0.29, "WIND", fontsize=8 * k, family=num, color=COLORS["muted"], va="center")
            _text(ax, x + cw - 0.03, 0.29, f"{d['wind']:.0f} km/h", fontsize=10 * k, family=num,
                  color=COLORS["text"], va="center", ha="right", keep=False)
        key = d.get("key")
        if key:
            ax.plot([x + 0.03, x + cw - 0.03], [0.245, 0.245], color=COLORS["grid"], lw=1)
            _text(ax, mid, 0.205, f"{key['session']} {key['time']}", ha="center", va="center", fontsize=11 * k,
                  family=head, fontweight="bold", color=COLORS["text"])
            parts = []
            if key.get("rain_pct") is not None:
                parts.append(f"{key['rain_pct']:.0f} % rain")
            if key.get("temp") is not None:
                parts.append(f"{key['temp']:.0f}°")
            _text(ax, mid, 0.15, " · ".join(parts) or "–", ha="center", va="center", fontsize=9 * k,
                  family=num, color=COLORS["muted"], keep=False)
    note = "Forecast: Open-Meteo · local times · rain = highest hourly chance of the day"
    if w.get("fetched"):
        note += f" · as of {str(w['fetched'])[:16].replace('T', ' ')} UTC"
    _text(ax, 0.0, 0.04, note, fontsize=7.5 * k, color=COLORS["muted"], va="center", keep=True)
    return days


# ------------------------------------------------------------------ 3 Form
MARKERS = ("o", "s", "D")


def render_form(ax, data: dict) -> list[tuple[str, float]]:
    races, form = data.get("races") or [], data.get("form") or {}
    if not races:
        raise ValueError("Keine Rennen vor diesem Wochenende mit Rundendaten – Form nicht berechenbar")
    rows = sorted(form.items(), key=lambda x: x[1])
    y = np.arange(len(rows))
    colors = [team_color(t) for t, _ in rows]
    x0, y0, w, h = ax.get_position().bounds
    ax.set_position([x0 + 0.06, y0 + 0.02, w - 0.06, h - 0.02])
    ax.barh(y, [v for _, v in rows], height=0.6, color=colors, alpha=0.9, zorder=2)
    weights = list(data.get("weights") or (1, 2, 3))[-len(races):]
    for m, (race, wt) in enumerate(zip(races, weights)):
        xs = [race["pace"].get(t) for t, _ in rows]
        pts = [(v, i) for i, v in enumerate(xs) if v is not None]
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], marker=MARKERS[m % 3], s=26, zorder=3,
                   facecolor=COLORS["bg"], edgecolor=COLORS["text"], linewidth=1.1,
                   label=f"{race['place']} ×{wt}")
    ax.invert_yaxis()
    ax.set_yticks(y)
    ax.set_yticklabels([short_team(t) for t, _ in rows], fontsize=9, fontweight="bold")
    for tick, c in zip(ax.get_yticklabels(), colors):
        tick.set_color(c)
    right = max(max(r["pace"].values()) for r in races)
    for i, (t, v) in enumerate(rows):
        ax.text(right * 1.1, i, f"{v:.2f} %", va="center", fontsize=8.5, color=COLORS["text"])
    ax.set_xlim(0, right * 1.32)
    ax.set_ylim(len(rows) - 0.4, -0.9)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(COLORS["grid"])
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", colors=COLORS["muted"], labelsize=8)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.1f} %")
    ax.grid(axis="x", color=COLORS["grid"], linewidth=0.6, zorder=0)
    ax.set_xlabel("Race pace gap to the fastest team (median of clean laps) · bar = weighted average",
                  color=COLORS["muted"], fontsize=8)
    leg = ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=len(races), frameon=False,
                    fontsize=8.5, handletextpad=0.3, columnspacing=1.2, labelcolor=COLORS["text"])
    for t in leg.get_texts():
        t.keep_font = True
    return rows


# ------------------------------------------------------------------ 4 Chancen
def render_chances(ax, data: dict) -> list[dict]:
    rows = data.get("chances") or []
    if not rows:
        raise ValueError("Keine Form-Daten – Chancen nicht berechenbar")
    _blank(ax)
    head, num = _font(FONT_HEAD), _font(FONT_NUM)
    hist = data.get("history")
    if hist and not hist.get("track_pace"):
        hist = None                      # nur Ergebnisse (z. B. 2017) – fließt nicht in die Chancen ein
    tiers = []
    for r in rows:
        if not tiers or tiers[-1][0] != r["tier"]:
            tiers.append((r["tier"], []))
        tiers[-1][1].append(r)
    lines = len(rows) + len(tiers) * 1.3
    step = 0.86 / lines
    y = 0.98
    rank = 0
    worst = max(r["score"] for r in rows) or 1
    best = rows[0]["score"]
    for tier, members in tiers:
        _text(ax, 0.0, y - step * 0.6, tier, fontsize=12 * k, family=head, fontweight="bold",
              color=COLORS["accent"] if tier == "FAVOURITES" else COLORS["muted"], va="center")
        y -= step * 1.3
        for r in members:
            rank += 1
            yc = y - step * 0.5
            col = team_color(r["team"])
            if rank % 2:
                ax.add_patch(Rectangle((0, y - step), 1, step, color=COLORS["plot"], linewidth=0, zorder=0))
            ax.add_patch(Rectangle((0, y - step), 0.008, step, color=col, linewidth=0, zorder=1))
            _text(ax, 0.045, yc, f"{rank}", fontsize=11 * k, family=num, color=COLORS["muted"], va="center",
                  ha="center", keep=False)
            _text(ax, 0.085, yc, short_team(r["team"]).upper(), fontsize=15 * k, family=head, fontweight="bold",
                  color=COLORS["text"], va="center")
            if r["trend"]:
                up = r["trend"] > 0
                _text(ax, 0.39, yc, "▲" if up else "▼", fontsize=10 * k, color="#22c55e" if up else "#ef4444",
                      va="center", ha="center", family="DejaVu Sans")
            # Balken: Abstand zum besten Wert (kurz = gut)
            bw = 0.2 * (r["score"] - best) / max(worst - best, 1e-9)
            ax.add_patch(Rectangle((0.43, yc - step * 0.16), max(bw, 0.004), step * 0.32, color=col,
                                   alpha=0.9, linewidth=0, zorder=2))
            _text(ax, 0.66, yc, "top" if rank == 1 else f"+{r['score'] - best:.2f} %", fontsize=10 * k,
                  family=num, color=COLORS["text"], va="center", keep=False)
            detail = f"form {r['form']:.2f}"
            if hist:
                detail += f" · '{str(hist['year'])[2:]} " + ("–" if r["track"] is None else f"{r['track']:.2f}")
            _text(ax, 0.995, yc, detail, fontsize=8 * k, family=num, color=COLORS["muted"], va="center",
                  ha="right", keep=False)
            y -= step
    if hist:
        note = (f"Assessment from data, not a prediction · 75 % race pace of the last {len(data.get('races', []))} "
                f"races (newest counts most)\n+ 25 % pace here in {hist['year']} · values = % gap to the fastest team")
    else:
        note = (f"Assessment from data, not a prediction · race pace of the last {len(data.get('races', []))} "
                f"races (newest counts most)\nno recent race here to compare · values = % gap to the fastest team")
    _text(ax, 0.0, 0.035, note, fontsize=7.5 * k, color=COLORS["muted"], va="center", linespacing=1.5)
    return rows
