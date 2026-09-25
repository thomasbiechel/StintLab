"""Telemetrie-Vergleich: Geschwindigkeit und Zeitabstand über eine Runde.

DATENQUELLE: OpenF1 car_data, etwa 3–4 Messpunkte pro Sekunde. Bei 300 km/h
liegen zwischen zwei Punkten gut 20 m – Geschwindigkeitsverläufe sind
aussagekräftig, exakte Bremspunkte NICHT.

STRECKE: OpenF1 liefert keine zurückgelegte Distanz. Sie wird aus der
Geschwindigkeit aufsummiert (Trapezregel) und je Fahrer auf 0–100 % der Runde
normiert, damit beide Linien übereinanderliegen.

ZEITABSTAND: Direkt aus den Telemetriezeiten wäre er ungenau – kleine Fehler
summieren sich über die Runde. Deshalb wird er an den OFFIZIELLEN Sektorzeiten
ausgerichtet: An jeder Sektorgrenze und im Ziel stimmt der Abstand exakt,
dazwischen zeigt die Telemetrie den Verlauf.
"""

from __future__ import annotations

import numpy as np

from stintlab import openf1
from stintlab.analyses.ideal_lap import SECTORS, _valid_laps
from stintlab.analyses.long_runs import _fmt
from stintlab.session import _parse
from stintlab.style import COLORS, style_axes, team_color

GRID = 600            # Stützpunkte über die Runde
MIN_RATE_HZ = 2.0     # darunter: Warnung, Daten zu dünn
MAX_LENGTH_DIFF = 0.03  # 3 % Unterschied der berechneten Rundenlänge → Warnung
MAX_SECTOR_MISMATCH = 0.005  # Sektorgrenze bei A und B mehr als 0,5 % der Runde auseinander → Warnung
# (Madring Q3, NOR vs ANT: 3 m bzw. 6 m bei 5,34 km – also rund 0,1 %)


def fastest_lap(data: dict, driver: str, compound: str | None, part: str | None) -> dict | None:
    laps = [l for l in _valid_laps(data, compound, part).get(driver, []) if l.get("LapTime")]
    return min(laps, key=lambda l: float(l["LapTime"])) if laps else None


def lap_trace(car_data: list[dict], lap: dict) -> tuple[np.ndarray, np.ndarray]:
    """(Zeit ab Rundenbeginn [s], Geschwindigkeit [km/h]) für genau eine Runde.

    Anfang und Ende werden aus den Nachbarpunkten interpoliert, damit die
    Kurve exakt bei 0 s beginnt und bei der Rundenzeit endet.
    """
    start, lap_time = lap["LapStart"], float(lap["LapTime"])
    points = []
    for row in car_data:
        when = _parse(row.get("date"))
        if when is None or row.get("speed") is None:
            continue
        t = (when - start).total_seconds()
        if -2.0 <= t <= lap_time + 2.0:
            points.append((t, float(row["speed"])))
    points.sort()
    if len(points) < 4:
        raise ValueError(f"{lap['Driver']}: zu wenige Telemetriepunkte für Runde {lap['LapNumber']}")
    t_all = np.array([p[0] for p in points])
    v_all = np.array([p[1] for p in points])
    inside = (t_all > 0) & (t_all < lap_time)
    t = np.concatenate([[0.0], t_all[inside], [lap_time]])
    v = np.concatenate([[np.interp(0.0, t_all, v_all)], v_all[inside],
                        [np.interp(lap_time, t_all, v_all)]])
    return t, v


def distance(t: np.ndarray, v_kmh: np.ndarray) -> np.ndarray:
    """Zurückgelegte Strecke in Metern (Trapezregel)."""
    v = v_kmh / 3.6
    return np.concatenate([[0.0], np.cumsum((v[1:] + v[:-1]) / 2 * np.diff(t))])


def compare(a: dict, b: dict) -> dict:
    """a, b: {"t", "v", "sectors": [s1, s2, s3] | None, "lap_time"}.

    Ergebnis auf gemeinsamem Raster (Anteil der Runde 0–1):
    speed_a, speed_b, delta (> 0 = A vorne), sector_marks (Anteile), length_m.
    """
    frac = np.linspace(0, 1, GRID)
    out = {"frac": frac}
    for key, d in (("a", a), ("b", b)):
        dist = distance(d["t"], d["v"])
        d["length"] = dist[-1]
        d["frac"] = dist / dist[-1]
        out[f"speed_{key}"] = np.interp(frac, d["frac"], d["v"])
        out[f"time_{key}"] = np.interp(frac, d["frac"], d["t"])
    raw = out["time_b"] - out["time_a"]

    # Ausrichtung an den offiziellen Sektorzeiten
    knots, targets = [0.0], [0.0]
    marks = []
    if a.get("sectors") and b.get("sectors") and all(a["sectors"]) and all(b["sectors"]):
        ca = np.cumsum(a["sectors"][:2])
        cb = np.cumsum(b["sectors"][:2])
        for ta, tb in zip(ca, cb):
            f = float(np.interp(ta, a["t"], a["frac"]))
            marks.append(f)
            knots.append(f)
            targets.append(tb - ta)
            # Gegenprobe: Bei B muss die Sektorgrenze am selben Punkt liegen
            out.setdefault("sector_mismatch", []).append(abs(f - float(np.interp(tb, b["t"], b["frac"]))))
    knots.append(1.0)
    targets.append(b["lap_time"] - a["lap_time"])
    correction = np.interp(frac, knots, np.array(targets) - np.interp(knots, frac, raw))
    out["delta"] = raw + correction
    out["sector_marks"] = marks
    out["length_m"] = (a["length"] + b["length"]) / 2
    out["length_diff"] = abs(a["length"] - b["length"]) / out["length_m"]
    return out


def _driver_trace(data: dict, drv: str, lap: dict, refresh: bool = False) -> dict:
    car_data = data.get("car_data", {}).get(drv)
    if car_data is None:
        car_data = openf1.cached_fetch_driver("car_data", data["session_key"], data["numbers"][drv], refresh)
    t, v = lap_trace(car_data, lap)
    sectors = [lap.get(k) for k in SECTORS]
    return {"t": t, "v": v, "lap_time": float(lap["LapTime"]),
            "sectors": [float(s) for s in sectors] if all(sectors) else None}


def render_telemetry(ax, data: dict, drivers: list[str] | None = None,
                     compound: str | None = None, part: str | None = None) -> dict:
    # Fahrer: angegeben oder die zwei schnellsten
    if not drivers:
        best = sorted((l for l in (fastest_lap(data, d, compound, part) for d in _valid_laps(data, compound, part))
                       if l), key=lambda l: float(l["LapTime"]))
        drivers = [l["Driver"] for l in best[:2]]
    if len(drivers) != 2:
        raise ValueError("Telemetrie braucht genau zwei Fahrer")
    laps = [fastest_lap(data, d, compound, part) for d in drivers]
    for d, lap in zip(drivers, laps):
        if lap is None:
            raise ValueError(f"{d}: keine gültige Runde{' in ' + part if part else ''}")
    # A = der Schnellere
    if float(laps[1]["LapTime"]) < float(laps[0]["LapTime"]):
        drivers, laps = drivers[::-1], laps[::-1]
    a, b = (_driver_trace(data, d, l) for d, l in zip(drivers, laps))
    res = compare(a, b)

    # Plausibilität
    for d, tr in zip(drivers, (a, b)):
        rate = (len(tr["t"]) - 2) / tr["lap_time"]
        if rate < MIN_RATE_HZ:
            print(f"⚠ Telemetrie {d}: nur {rate:.1f} Messpunkte/s – Verlauf grob")
    for i, diff in enumerate(res.get("sector_mismatch", []), start=1):
        if diff > MAX_SECTOR_MISMATCH:
            print(f"⚠ Telemetrie: Sektorgrenze {i} liegt bei beiden Fahrern {diff:.1%} der Runde auseinander – Daten prüfen")
    if res["length_diff"] > MAX_LENGTH_DIFF:
        print(f"⚠ Telemetrie: berechnete Rundenlänge weicht um {res['length_diff']:.1%} ab – Daten prüfen")

    teams = data.get("teams", {})
    ca, cb = team_color(teams.get(drivers[0])), team_color(teams.get(drivers[1]))
    same_team = teams.get(drivers[0]) == teams.get(drivers[1])
    km = res["frac"] * res["length_m"] / 1000

    # Zwei Bereiche: oben Geschwindigkeit, unten Abstand
    fig = ax.figure
    x, y, w, h = ax.get_position().bounds
    ax.set_position([x, y + h * 0.34, w, h * 0.66])
    ax_d = fig.add_axes([x, y, w, h * 0.26], sharex=ax)
    ax_d.set_facecolor(ax.get_facecolor())
    for a_ in (ax, ax_d):
        style_axes(a_, grid_axis="both")

    ax.plot(km, res["speed_a"], color=ca, linewidth=1.4,
            label=f"{drivers[0]}  {_fmt(a['lap_time'])}")
    ax.plot(km, res["speed_b"], color=cb, linewidth=1.4, linestyle="--" if same_team else "-",
            label=f"{drivers[1]}  {_fmt(b['lap_time'])}")
    ax.set_ylabel("Speed (km/h)")
    ax.legend(loc="lower left", fontsize=8, frameon=False, labelcolor=COLORS["text"])
    ax.tick_params(labelbottom=False)

    ax_d.axhline(0, color=COLORS["muted"], linewidth=0.8)
    ax_d.plot(km, res["delta"], color=COLORS["text"], linewidth=1.2)
    ax_d.fill_between(km, res["delta"], 0, where=res["delta"] >= 0, color=ca, alpha=0.35, linewidth=0)
    ax_d.fill_between(km, res["delta"], 0, where=res["delta"] < 0, color=cb, alpha=0.35, linewidth=0)
    ax_d.set_ylabel(f"Gap (s)\n▲ {drivers[0]} ahead", fontsize=7.5)
    ax_d.set_xlabel("Lap distance (km)")
    ax_d.set_xlim(0, km[-1])

    # Sektorgrenzen und Sektorabstände
    bounds = [0.0] + [m * res["length_m"] / 1000 for m in res["sector_marks"]] + [km[-1]]
    for bx in bounds[1:-1]:
        for a_ in (ax, ax_d):
            a_.axvline(bx, color=COLORS["grid"], linewidth=1, linestyle=":")
    if a["sectors"] and b["sectors"]:
        top = ax.get_ylim()[1]
        for i, (x0, x1) in enumerate(zip(bounds[:-1], bounds[1:])):
            diff = b["sectors"][i] - a["sectors"][i]
            leader = drivers[0] if diff >= 0 else drivers[1]
            ax.text((x0 + x1) / 2, top, f"S{i + 1}  {leader} {abs(diff):.3f}", ha="center", va="bottom",
                    fontsize=8, color=ca if diff >= 0 else cb, fontweight="bold")

    ax_d.text(0.99, 0.04, "OpenF1 car data · ~4 Hz · braking points approximate",
              transform=ax_d.transAxes, ha="right", va="bottom", fontsize=7, color=COLORS["muted"])
    return res
