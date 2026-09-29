"""Windschatten-Effekt: Speed Trap in Abhängigkeit vom Abstand zum Auto davor.

FRAGE: Wie viel Top-Speed bringt es, direkt hinter einem Auto zu fahren?

METHODE, pro grüner Runde jedes Fahrers:
- Abstand zum Auto davor = Zeit seit das nächste Auto (egal welches, auch ein
  Überrundeter) die Ziellinie am Ende dieser Runde überquert hat.
  Baku 2026: das passt besser zur Speed Trap als der Rundenbeginn
  (Korrelation −0,34 gegenüber −0,22).
- Speed-Trap-Gewinn = SpeedST minus Median des Fahrers in Runden OHNE Auto
  innerhalb von 3 s davor ("freie Fahrt"). So fallen Unterschiede zwischen
  Autos und Abtrieb heraus; übrig bleibt der Effekt des Hinterherfahrens.
- Raus: Runde 1, SC/VSC/rote Flagge (auch die Runde danach), Boxen-In/Out-Laps.
- Fahrer mit weniger als MIN_FREE Runden in freier Fahrt haben keine
  Basislinie und fehlen (Baku: VER fuhr nie frei).

GRENZE: Enthält alles, was hinter einem Auto passiert – Windschatten UND
z. B. den Overtake Mode, der erst innerhalb einer Sekunde freigeschaltet wird.
Die Aufteilung dazu macht compute_tow_split / render_tow_split (unten).

AUFTEILUNG (tow_split): Der Overtake Mode wird an EINER Messlinie
entschieden (≤ 1 s → frei), der Windschatten wirkt überall. Runden mit
Auto ≤ 1 s davor an der Speed Trap werden deshalb getrennt nach:
- "mode":    auch an der Messlinie ≤ 1 s → Windschatten + Overtake Mode
- "tow":     an der Messlinie > 1 s, erst danach herangekommen → nur Windschatten
- "restart": erste grüne Runde nach SC/VSC/roter Flagge – der Modus ist dann
             vermutlich noch gesperrt (wie früher DRS). IM REGLEMENT PRÜFEN.
             Eigene Gruppe, weil kalte Reifen/Pulk die Werte verzerren können.
Differenz "mode" minus "tow" ≈ Anteil des Overtake Mode.

MESSLINIE = PROXY: Die Position der Messlinie steckt nicht in den Daten.
Standard ist der Abstand an der Ziellinie am BEGINN der Runde
(detection_gaps kann echte Werte pro (Fahrer, Runde) liefern, z. B. aus
gap_on_lap an der Messlinie). Wie gut der Proxy ist, hängt von der Strecke
ab – kleine Gruppen (n < MIN_GROUP) werden grau und als unsicher markiert.
"""

from __future__ import annotations

import bisect
from statistics import median

import numpy as np

from stintlab.race_control import restricted_laps
from stintlab.style import COLORS, style_axes, team_color

FREE_AIR_S = 3.0
MIN_FREE = 5
MAX_GAP_S = 5.0
BINS = [(0, 0.5), (0.5, 1), (1, 1.5), (1.5, 2), (2, 3), (3, 5)]
MODE_GAP_S = 1.0      # Freischaltgrenze Overtake Mode
MIN_GROUP = 8         # darunter gilt eine Gruppe als unsicher
GROUPS = [("mode", "Tow + overtake mode"), ("tow", "Tow only\n(>1 s at detection)"),
          ("restart", "Restart lap\n(mode locked?)")]


def _laps_with_gaps(data: dict) -> list[dict]:
    """Alle auswertbaren Runden mit Abstand an der Linie am Ende ("gap") und am
    Beginn der Runde ("gap_start"); "restart" = erste grüne Runde nach SC/VSC/RED."""
    restricted = restricted_laps(data.get("race_control", []))
    pit = {(p["driver"], p["lap"]) for p in data.get("pit_stops", [])}
    lap_ends = data.get("lap_ends", {})
    crossings = sorted((t, drv) for drv, ends in lap_ends.items() for t in ends.values())
    times = [t for t, _ in crossings]

    def gap_ahead(drv, t):
        i = bisect.bisect_left(times, t) - 1
        while i >= 0 and crossings[i][1] == drv:
            i -= 1
        return (t - times[i]).total_seconds() if i >= 0 else float("inf")

    pts = []
    for lap in data.get("laps", []):
        drv, n, st = lap.get("Driver"), lap.get("LapNumber"), lap.get("SpeedST")
        if not st or n is None or n < 2 or lap.get("IsPitOutLap"):
            continue
        if n in restricted or (drv, n) in pit or (drv, n - 1) in pit:
            continue
        end = lap_ends.get(drv, {}).get(n)
        if end is None:
            continue
        start = lap_ends.get(drv, {}).get(n - 1)
        pts.append({"driver": drv, "lap": n, "gap": gap_ahead(drv, end),
                    "gap_start": gap_ahead(drv, start) if start is not None else float("inf"),
                    "speed": float(st), "restart": n - 1 in restricted})
    return pts


def _with_baseline(pts: list[dict]) -> list[dict]:
    """Basislinie = Median in freier Fahrt, nur aus normalen Runden (kein Restart)."""
    base = {}
    for drv in {p["driver"] for p in pts}:
        free = [p["speed"] for p in pts if p["driver"] == drv and p["gap"] > FREE_AIR_S and not p["restart"]]
        if len(free) >= MIN_FREE:
            base[drv] = median(free)
    return [{**p, "delta": p["speed"] - base[p["driver"]]} for p in pts if p["driver"] in base]


def compute_tow_effect(data: dict) -> list[dict]:
    """[{driver, lap, gap, delta, ...}] für alle Fahrer mit Basislinie (ohne Restart-Runden)."""
    return [p for p in _with_baseline(_laps_with_gaps(data)) if not p["restart"]]


def compute_tow_split(data: dict, detection_gaps: dict | None = None) -> dict[str, dict]:
    """{Gruppe: {"median", "n", "deltas"}} für "free", "mode", "tow", "restart".

    detection_gaps: optional {(Fahrer, Runde): Abstand an der Messlinie} –
    ersetzt den Proxy (Abstand an der Ziellinie am Rundenbeginn)."""
    detection_gaps = data.get("detection_gaps", {}) if detection_gaps is None else detection_gaps
    groups: dict[str, list[float]] = {"free": [], "mode": [], "tow": [], "restart": []}
    for p in _with_baseline(_laps_with_gaps(data)):
        if p["gap"] > FREE_AIR_S and not p["restart"]:
            groups["free"].append(p["delta"])
            continue
        if p["gap"] > MODE_GAP_S:
            continue                       # 1–3 s: halber Windschatten, in keiner Gruppe
        if p["restart"]:
            groups["restart"].append(p["delta"])
            continue
        det = detection_gaps.get((p["driver"], p["lap"]), p["gap_start"])
        groups["mode" if det <= MODE_GAP_S else "tow"].append(p["delta"])
    return {k: {"median": float(median(v)) if v else None, "n": len(v), "deltas": v}
            for k, v in groups.items()}


def binned(points: list[dict]) -> list[tuple[float, float, int]]:
    """[(Mitte des Bereichs, Median-Gewinn, Anzahl)]"""
    out = []
    for lo, hi in BINS:
        vals = [p["delta"] for p in points if lo <= p["gap"] < hi]
        if vals:
            out.append(((lo + hi) / 2, float(median(vals)), len(vals)))
    return out


def render_tow_effect(ax, data: dict) -> list[tuple[float, float, int]]:
    pts = compute_tow_effect(data)
    shown = [p for p in pts if p["gap"] <= MAX_GAP_S]
    if len(shown) < 20:
        raise ValueError("Zu wenige Runden mit Auto davor für den Windschatten-Effekt")
    teams = data.get("teams", {})
    style_axes(ax, grid_axis="y")
    rng = np.random.default_rng(0)   # leichtes Streuen, damit gleiche km/h-Werte nicht übereinander liegen
    ax.scatter([p["gap"] for p in shown], [p["delta"] + rng.uniform(-0.3, 0.3) for p in shown],
               s=11, c=[team_color(teams.get(p["driver"])) for p in shown], alpha=0.45, linewidth=0)
    bins = binned(shown)
    xs, ys = [b[0] for b in bins], [b[1] for b in bins]
    ax.plot(xs, ys, color=COLORS["text"], linewidth=2.4, marker="o", markersize=6, zorder=5)
    for x, y, n in bins:
        ax.annotate(f"{y:+.0f}", (x, y), xytext=(0, 9), textcoords="offset points", ha="center",
                    fontsize=10, fontweight="bold", color=COLORS["text"])
    ax.axhline(0, color=COLORS["muted"], linewidth=0.8)
    # Einzelne Ausreißer (Baku: bis −120 km/h, Ursache unklar) nicht
    # die Achse bestimmen lassen – 1.–99. Perzentil, Anzahl außerhalb wird genannt
    deltas = np.array([p["delta"] for p in shown])
    lo, hi = np.percentile(deltas, 1), np.percentile(deltas, 99)
    pad = (hi - lo) * 0.12
    ax.set_ylim(lo - pad, hi + pad * 2)
    outside = int(np.sum((deltas < lo - pad) | (deltas > hi + pad * 2)))
    ax.axvline(1.0, color=COLORS["muted"], linewidth=0.8, linestyle="--")
    ax.text(1.04, hi + pad * 1.6, "1 s", fontsize=8.5, color=COLORS["muted"], va="top")
    ax.set_xlim(0, MAX_GAP_S)
    ax.set_xlabel("Gap to the car ahead at the line (s)")
    ax.set_ylabel("Speed trap vs. own free-air median (km/h)")
    missing = sorted({l["Driver"] for l in data.get("laps", [])} - {p["driver"] for p in pts})
    notes = [f"line = median per gap range · {len(shown)} green laps, all drivers"]
    if outside:
        notes.append(f"{outside} outliers outside the axis")
    if missing:
        notes.append("no free-air laps, not shown: " + ", ".join(missing))
    ax.text(0.99, 0.02, "\n".join(notes), transform=ax.transAxes, ha="right", va="bottom",
            fontsize=7.5, color=COLORS["muted"], linespacing=1.5)
    return bins


def render_tow_split(ax, data: dict) -> dict[str, dict]:
    """Balken: Speed-Trap-Gewinn für Windschatten + Modus / nur Windschatten / Restart."""
    res = compute_tow_split(data)
    if res["mode"]["n"] + res["tow"]["n"] < 10:
        raise ValueError("Zu wenige Runden innerhalb 1 s für die Aufteilung Windschatten/Overtake Mode")
    style_axes(ax, grid_axis="y")
    rng = np.random.default_rng(0)
    top = 0.0
    for i, (key, label) in enumerate(GROUPS):
        g = res[key]
        if not g["n"]:
            ax.text(i, 0.5, "no laps", ha="center", va="bottom", fontsize=9, color=COLORS["muted"])
            continue
        weak = g["n"] < MIN_GROUP
        color = COLORS["muted"] if weak else (COLORS["accent"] if key == "mode" else COLORS["text"])
        ax.bar(i, g["median"], width=0.55, color=color, alpha=0.35 if weak else 0.9, zorder=3)
        ax.scatter(i + rng.uniform(-0.18, 0.18, g["n"]), g["deltas"], s=9, color=color, alpha=0.5,
                   linewidth=0, zorder=4)
        ax.annotate(f"{g['median']:+.1f} km/h", (i, max(g["median"], 0)), xytext=(0, 8),
                    textcoords="offset points", ha="center", fontsize=11, fontweight="bold",
                    color=COLORS["text"])
        ax.text(i, -0.02, f"n = {g['n']}" + (" · uncertain" if weak else ""), transform=ax.get_xaxis_transform(),
                ha="center", va="top", fontsize=8, color=COLORS["muted"])
        top = max(top, g["median"], float(np.percentile(g["deltas"], 90)))
    ax.axhline(0, color=COLORS["muted"], linewidth=0.8)
    ax.set_ylim(min(-3.0, ax.get_ylim()[0]), top * 1.25 + 1)
    ax.set_xticks(range(len(GROUPS)), [label for _, label in GROUPS])
    ax.tick_params(axis="x", pad=18)
    ax.set_xlim(-0.6, len(GROUPS) - 0.4)
    ax.set_ylabel("Speed trap vs. own free-air median (km/h)")
    m, t = res["mode"]["median"], res["tow"]["median"]
    notes = [f"0 = free air (>{FREE_AIR_S:.0f} s gap, {res['free']['n']} laps) · bar = median, dots = single laps",
             "detection gap ≈ gap at the line at lap start (proxy)"]
    if m is not None and t is not None:
        notes.insert(0, f"overtake mode share ≈ {m - t:+.1f} km/h")
    ax.text(0.99, 0.98, "\n".join(notes), transform=ax.transAxes, ha="right", va="top",
            fontsize=7.5, color=COLORS["muted"], linespacing=1.5)
    return res
