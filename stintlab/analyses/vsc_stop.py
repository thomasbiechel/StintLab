"""Was wäre gewesen, wenn ein Fahrer unter VSC/SC gestoppt hätte?

Entstanden in Singapur 2026: LEC und ANT stoppten in Runde 39 unter VSC und
nahmen frische Softs, HAM (P3, danach P2 auf der Strecke) blieb draußen und
fuhr seine Softs aus Runde 19 bis ins Ziel (47 Runden alt) – P6.

Das ist KEINE Messung, sondern ein Modell. Es nimmt an: Der Fahrer macht in der
Stopp-Runde dasselbe wie ein Referenzfahrer, der dort tatsächlich gestoppt hat.

METHODE (alles relativ zum Referenzfahrer R, der wirklich gestoppt hat):
  1. Abstand vor dem Stopp: wie weit liegt der Fahrer nach Runde stop_lap−1
     hinter R (line_gaps – offizielle Rundenzeiten, nicht die ungenauen
     Zeitstempel).
  2. Tempo-Unterschied δ: Median von (Rundenzeit Fahrer − Rundenzeit R) über
     die sauberen Runden vor dem Stopp (ohne Boxen-, Out- und SC/VSC-Runden).
  3. Ab stop_lap fährt der Fahrer die Rundenzeiten von R + δ. Damit stecken
     Boxenverlust unter VSC (Stopp von R, Rundenzeiten in/out) und die
     Leistung frischer Reifen in R's echten Rundenzeiten.
  4. Zielabstand = Abstand vor dem Stopp + (Runden bis ins Ziel) · (δ + Zuschlag).
     Der Zuschlag (Standard 0 / 0,3 / 0,6 s pro Runde) ist die Unsicherheit:
     Das Auto kann auf denselben Reifen langsamer sein, als die Vorrunden zeigen
     (vorher andere Mischung und anderes Reifenalter als R!).
  5. Position = 1 + Zahl der echten Fahrer, die im Ziel vor diesem Abstand lagen.

ZWEI REFERENZEN: Mit mehreren R (Singapur: LEC und ANT) entsteht ein Band
statt einer Zahl – so sieht man, wie stark das Ergebnis an der Wahl hängt.

RÜCKWÄRTSTEST (backtest): Dieselbe Methode auf einen Fahrer anwenden, der
wirklich gestoppt hat (ANT mit LEC als Referenz) und mit seinem echten Ziel
vergleichen. Das ist die einzige Prüfung, die das Modell hier hat.

GRENZEN – gehören auf die Slide:
- Verkehr: Die anderen Fahrer sind so gefahren, wie sie gefahren sind. Kommt der
  Fahrer nach dem Stopp hinter einem langsameren Auto heraus, kostet das Zeit,
  die im Band nicht steht. rejoin() zeigt, wer in der Out-Lap in der Nähe wäre,
  traffic_floor() ist die ehrliche Untergrenze: das ganze Rennen hinter diesem
  Auto festhängen (kommt 1 s hinter dessen echtem Ziel an). Die Wahrheit liegt
  dazwischen – wie lange er hängt, sagen die Daten nicht.
- Reifen: δ kommt aus Runden VOR dem Stopp, also von anderen Reifen als danach.
- Echte Fahrer wurden vom Fahrer selbst beeinflusst (Überholen, Verkehr).
- Es ist ein Fall (Singapur 2026), kein Beweis für „Stopp unter VSC ist immer besser“.
"""

from __future__ import annotations

from statistics import median

from matplotlib.ticker import MaxNLocator

from stintlab.analyses.gap_between import line_gaps
from stintlab.race_control import restricted_laps
from stintlab.style import COLORS, shade_neutral, style_axes, team_color

EXTRAS = (0.0, 0.3, 0.6)        # Zuschlag auf δ in s pro Runde (Unsicherheit)
WINDOW = 9                      # so viele Runden vor dem Stopp bestimmen δ
MIN_PACE_LAPS = 3
NEIGHBOUR_S = 3.0               # „in der Nähe“ in rejoin()
HOLD_S = 1.0                    # so weit liegt man im Ziel hinter dem Auto, hinter dem man festhängt


# ── Bausteine ────────────────────────────────────────────────────────────────

def final_lap(data: dict) -> int:
    return max(n for ends in data["lap_ends"].values() for n in ends)


def winner_of(data: dict) -> str:
    """Sieger laut offiziellem Ergebnis, sonst wer die Ziellinie zuerst überquert."""
    for r in data.get("results", []):
        if r.get("position") == 1 and r.get("driver") in data["lap_ends"]:
            return r["driver"]
    last = final_lap(data)
    return min((ends[last], d) for d, ends in data["lap_ends"].items() if last in ends)[1]


def behind(data: dict, ahead_ref: str, drv: str, lap: int) -> float | None:
    """Wie viele Sekunden liegt drv nach Runde `lap` hinter ahead_ref (negativ = davor)."""
    if ahead_ref == drv:
        return 0.0
    gaps, _ = line_gaps(data, ahead_ref, drv)
    return gaps.get(lap)


def _clean_times(data: dict, drivers: tuple[str, ...], first: int, last: int) -> dict[str, dict[int, float]]:
    """Rundenzeiten ohne Boxen-/Out-/SC-/VSC-Runden im Fenster first..last."""
    restricted = restricted_laps(data.get("race_control", []))
    pits = {(p["driver"], p["lap"]) for p in data.get("pit_stops", [])}
    out: dict[str, dict[int, float]] = {d: {} for d in drivers}
    for lap in data.get("laps", []):
        d, n, t = lap.get("Driver"), lap.get("LapNumber"), lap.get("LapTime")
        if d not in out or n is None or not t or not (first <= n <= last):
            continue
        if lap.get("IsPitOutLap") or (d, n) in pits or n in restricted:
            continue
        out[d][n] = float(t)
    return out


def pace_delta(data: dict, driver: str, ref: str, first: int, last: int) -> tuple[float, int]:
    """(Median von Rundenzeit(driver) − Rundenzeit(ref) in s, Zahl der Runden)."""
    times = _clean_times(data, (driver, ref), first, last)
    common = sorted(set(times[driver]) & set(times[ref]))
    if len(common) < MIN_PACE_LAPS:
        raise ValueError(f"Zu wenige saubere Runden für {driver} und {ref} in {first}–{last} "
                         f"(gefunden: {len(common)}, nötig: {MIN_PACE_LAPS})")
    return median(times[driver][n] - times[ref][n] for n in common), len(common)


def lead_lap_finishers(data: dict, winner: str, last: int) -> dict[str, float]:
    """{Fahrer: Rückstand auf den Sieger im Ziel (s)} – nur Fahrer in der Führungsrunde."""
    out = {winner: 0.0}
    for d in data["lap_ends"]:
        if d == winner:
            continue
        gap = behind(data, winner, d, last)
        if gap is not None:
            out[d] = gap
    return out


# ── Simulation ───────────────────────────────────────────────────────────────

def simulate_stop(data: dict, driver: str, refs: list[str], stop_lap: int,
                  extras: tuple[float, ...] = EXTRAS, window: int = WINDOW) -> dict:
    """Siehe Moduldoku. Rückgabe:
    {driver, refs, stop_lap, last, winner, real: {Fahrer: Rückstand auf Sieger},
     real_behind, real_rank, scenarios: [{ref, delta, n_laps, extra, behind_winner, rank}]}"""
    if not refs:
        raise ValueError("vsc_stop braucht mindestens einen Referenzfahrer (refs)")
    last = final_lap(data)
    winner = winner_of(data)
    k = stop_lap - 1
    if stop_lap <= 1 or stop_lap > last:
        raise ValueError(f"stop_lap muss zwischen 2 und {last} liegen")
    real = lead_lap_finishers(data, winner, last)
    if driver not in real:
        raise ValueError(f"{driver} ist nicht in der Führungsrunde ins Ziel gekommen")
    others = {d: v for d, v in real.items() if d != driver}
    real_rank = 1 + sum(1 for v in others.values() if v < real[driver])

    scenarios = []
    for ref in refs:
        if ref not in real:
            raise ValueError(f"Referenzfahrer {ref} ist nicht in der Führungsrunde ins Ziel gekommen")
        g_k = behind(data, ref, driver, k)
        if g_k is None:
            raise ValueError(f"Kein Abstand {ref}/{driver} nach Runde {k}")
        delta, n_laps = pace_delta(data, driver, ref, k - window + 1, k)
        to_go = last - k
        for extra in extras:
            bw = real[ref] + g_k + to_go * (delta + extra)       # Rückstand auf den Sieger
            scenarios.append({"ref": ref, "delta": delta, "n_laps": n_laps, "extra": extra,
                              "behind_winner": bw,
                              "rank": 1 + sum(1 for v in others.values() if v < bw)})
    return {"driver": driver, "refs": list(refs), "stop_lap": stop_lap, "last": last,
            "winner": winner, "real": real, "real_behind": real[driver], "real_rank": real_rank,
            "scenarios": scenarios}


def summarize(sim: dict) -> dict:
    """Band über alle Szenarien: kleinster/größter Rückstand, beste/schlechteste Position."""
    bw = [s["behind_winner"] for s in sim["scenarios"]]
    ranks = [s["rank"] for s in sim["scenarios"]]
    counts = {r: ranks.count(r) for r in sorted(set(ranks))}
    return {"min": min(bw), "max": max(bw), "median": median(bw),
            "best": min(ranks), "worst": max(ranks), "counts": counts, "n": len(ranks),
            "gain_s": sim["real_behind"] - median(bw)}


def backtest(data: dict, driver: str, ref: str, stop_lap: int, window: int = WINDOW) -> dict:
    """Dieselbe Methode (ohne Zuschlag) auf einen Fahrer, der wirklich gestoppt hat.
    Fehler = vorhergesagter minus echter Rückstand auf R im Ziel (s)."""
    last, k = final_lap(data), stop_lap - 1
    g_k = behind(data, ref, driver, k)
    real = behind(data, ref, driver, last)
    if g_k is None or real is None:
        raise ValueError(f"Kein Abstand {ref}/{driver} für den Rückwärtstest")
    delta, _ = pace_delta(data, driver, ref, k - window + 1, k)
    predicted = g_k + (last - k) * delta
    return {"driver": driver, "ref": ref, "predicted": predicted, "real": real,
            "error": predicted - real, "laps": last - k}


def rejoin(data: dict, driver: str, ref: str, stop_lap: int, window: int = WINDOW,
           radius: float = NEIGHBOUR_S) -> dict:
    """Wo käme der Fahrer nach der Out-Lap (Ende Runde stop_lap+1) heraus – und wer ist dann in der Nähe?
    Verkehr ist nicht modelliert; das hier zeigt nur, ob welcher da wäre."""
    k, n = stop_lap - 1, stop_lap + 1
    g_k = behind(data, ref, driver, k)
    delta, _ = pace_delta(data, driver, ref, k - window + 1, k)
    mine = g_k + (n - k) * delta                       # Rückstand auf ref nach der Out-Lap
    cars = {}
    for d in data["lap_ends"]:
        if d == driver:
            continue
        gap = behind(data, ref, d, n)
        if gap is not None:
            cars[d] = gap
    ahead = sorted((v, d) for d, v in cars.items() if v < mine)
    rank = len(ahead) + 1
    near = sorted(((d, v - mine) for d, v in cars.items() if abs(v - mine) <= radius), key=lambda x: x[1])
    return {"lap": n, "rank": rank, "near": near}


def traffic_floor(data: dict, sim: dict, radius: float = NEIGHBOUR_S, hold: float = HOLD_S) -> dict | None:
    """Untere Grenze, wenn Verkehr zuschlägt: Der Fahrer hängt nach dem Stopp das ganze Rennen hinter dem
    Auto fest, das nach der Out-Lap am nächsten bei ihm liegt, und kommt `hold` s hinter dessen echtem
    Ziel an. Nie besser als das schlechteste Szenario des Bandes. None, wenn in der Out-Lap niemand
    innerhalb von `radius` s liegt (dann gibt es kein Verkehrsproblem, das man hier abschätzen könnte)."""
    cars = []
    for ref in sim["refs"]:
        near = rejoin(data, sim["driver"], ref, sim["stop_lap"], radius=radius)["near"]
        if near:
            car = min(near, key=lambda item: abs(item[1]))[0]
            if car in sim["real"]:
                cars.append(car)
    if not cars:
        return None
    car = max(cars, key=lambda c: sim["real"][c])               # das Auto, das am längsten aufhält
    worst_band = max(s["behind_winner"] for s in sim["scenarios"])
    bw = max(sim["real"][car] + hold, worst_band)
    others = {d: v for d, v in sim["real"].items() if d != sim["driver"]}
    return {"car": car, "behind_winner": bw, "hold": hold, "rank": 1 + sum(1 for v in others.values() if v < bw)}


# ── Slide: Ergebnis der Simulation ──────────────────────────────────────────

def render_vsc_stop(ax, data: dict, driver: str, refs: list[str], stop_lap: int,
                    extras: tuple[float, ...] = EXTRAS, top: int = 8) -> dict:
    sim = simulate_stop(data, driver, refs, stop_lap, extras)
    band = summarize(sim)
    teams = data.get("teams", {})
    order = sorted(sim["real"].items(), key=lambda kv: kv[1])[:top]
    if driver not in dict(order):                      # Fahrer weit hinten: trotzdem zeigen
        order = order[:-1] + [(driver, sim["real_behind"])]

    style_axes(ax, grid_axis="x")
    color = team_color(teams.get(driver))
    n = len(order)
    # Band über alle Zeilen: hier würde der Fahrer im Ziel liegen
    ax.axvspan(band["min"], band["max"], color=color, alpha=0.12, linewidth=0, zorder=0)
    for x in (band["min"], band["max"]):
        ax.axvline(x, color=color, alpha=0.5, linewidth=0.8, linestyle=":", zorder=1)

    for i, (drv, gap) in enumerate(order):
        c = team_color(teams.get(drv))
        if drv == driver:
            ax.scatter([gap], [i], s=70, facecolor=COLORS["bg"], edgecolor=c, linewidth=2, zorder=4)
            label = f"{gap:+.1f} s  (real)"
        else:
            ax.scatter([gap], [i], s=55, color=c, zorder=3, edgecolor=COLORS["bg"], linewidth=0.8)
            label = "winner" if gap == 0 else f"{gap:+.1f} s"
        ax.annotate(label, (gap, i), xytext=(9, 0), textcoords="offset points", va="center",
                    fontsize=7.5, color=COLORS["muted"])

    floor = traffic_floor(data, sim)
    y_sim, y_floor = (-2.5, -1.3) if floor else (-1.3, None)   # oben: Simulation, darunter Verkehrsgrenze
    ax.barh(y_sim, band["max"] - band["min"], left=band["min"], height=0.6, color=color, alpha=0.6,
            zorder=3)
    ax.scatter([band["median"]], [y_sim], s=40, color=COLORS["text"], zorder=5, edgecolor=color)
    counts = " · ".join(f"P{r} in {c} of {band['n']}" for r, c in band["counts"].items())
    ax.annotate(f"{counts}\n{band['min']:+.1f} to {band['max']:+.1f} s", (band["max"], y_sim),
                xytext=(9, 0), textcoords="offset points", va="center", fontsize=8,
                color=COLORS["text"], fontweight="bold", linespacing=1.35)
    ticks, tick_labels = [y_sim], [f"{driver} sim"]
    if floor:
        # Hängt er das ganze Rennen hinter einem Auto fest: schmaler Streifen hinter dessen Ziel
        left = floor["behind_winner"] - floor["hold"]
        ax.barh(y_floor, floor["hold"], left=left, height=0.6, color=color, alpha=0.25, hatch="////",
                edgecolor=color, linewidth=0.8, zorder=3)
        ax.axvline(floor["behind_winner"], color=color, alpha=0.35, linewidth=0.8, linestyle=":", zorder=1)
        ax.annotate(f"P{floor['rank']} · stuck behind {floor['car']} all race\n{floor['behind_winner']:+.1f} s",
                    (floor["behind_winner"], y_floor), xytext=(9, 0), textcoords="offset points",
                    va="center", fontsize=8, color=COLORS["text"], fontweight="bold", linespacing=1.35)
        ticks.append(y_floor)
        tick_labels.append(f"{driver} stuck")

    ax.set_yticks(ticks + list(range(n)))
    labels = [f"P{i + 1}  {drv}" for i, (drv, _) in enumerate(order)]
    if driver in dict(order):
        j = [d for d, _ in order].index(driver)
        labels[j] = f"P{sim['real_rank']}  {driver}"
    ax.set_yticklabels(tick_labels + labels, fontsize=8)
    for tick, (drv, _) in zip(ax.get_yticklabels(), [(driver, 0)] * len(ticks) + order):
        tick.set_color(team_color(teams.get(drv)))
    ax.set_ylim(n + 0.8, y_sim - 0.8)                  # unten Platz für den Hinweistext
    ax.set_xlim(-2, max(band["max"], floor["behind_winner"] if floor else 0, order[-1][1]) * 1.28)
    ax.set_xlabel("Seconds behind the winner at the flag")
    ax.tick_params(axis="y", length=0)

    refs_txt = " & ".join(refs)
    ax.text(0.99, 0.015, f"Band = same stop as {refs_txt}, pace {extras[0]:+.1f} to {extras[-1]:+.1f} s/lap\n"
            "Traffic only as the stuck-behind bound · one race, not a rule", transform=ax.transAxes, ha="right", va="bottom",
            fontsize=7, color=COLORS["muted"], linespacing=1.4)
    return {**sim, "band": band, "floor": floor}


# ── Slide: Rundenzeiten nach dem Stopp, mit Reifenalter ─────────────────────

def tyre_at_flag(data: dict, driver: str) -> tuple[str, int, int] | None:
    """(Mischung, Alter bei Ziel in Runden, Runde des Aufziehens) des letzten Stints."""
    stints = [s for s in data.get("stints", []) if s.get("driver") == driver and s.get("lap_start")]
    if not stints:
        return None
    s = max(stints, key=lambda x: x["lap_start"])
    end = s.get("lap_end") or final_lap(data)
    age = (s.get("tyre_age_at_start") or 0) + (end - s["lap_start"] + 1)
    return s["compound"], age, s["lap_start"]


def render_vsc_pace(ax, data: dict, drivers: list[str], first: int, last: int | None = None) -> dict:
    """Rundenzeiten der Fahrer ab `first`. Der ERSTE Fahrer ist der Hauptfahrer (Teamfarbe, dick),
    Teamkollegen bekommen Weiß gestrichelt. In der Legende steht das Reifenalter im Ziel."""
    last = last or final_lap(data)
    times = _clean_times(data, tuple(drivers), first, last)
    if not any(times.values()):
        raise ValueError(f"Keine sauberen Rundenzeiten für {drivers} in {first}–{last}")
    teams = data.get("teams", {})
    style_axes(ax, grid_axis="y")
    shade_neutral(ax, data.get("race_control", []), first, last)

    used: set[str] = set()
    for i, drv in enumerate(drivers):
        series = times[drv]
        if not series:
            continue
        team = teams.get(drv)
        color = COLORS["text"] if team in used else team_color(team)
        used.add(team)
        xs = sorted(series)
        ys = [series[x] for x in xs]
        tyre = tyre_at_flag(data, drv)
        info = f" · {tyre[0].title()}, {tyre[1]} laps old" if tyre else ""
        ax.scatter(xs, ys, s=14 if i == 0 else 9, color=color, alpha=0.55, linewidth=0, zorder=3)
        ax.plot(xs, ys, color=color, linewidth=2.4 if i == 0 else 1.5, linestyle="-" if i == 0 else "--",
                alpha=0.95 if i == 0 else 0.7, label=f"{drv}{info}", zorder=4)

    all_t = sorted(t for v in times.values() for t in v.values())
    pad = (all_t[-1] - all_t[0]) * 0.1 or 0.5
    ax.set_ylim(all_t[-1] + pad, all_t[0] - pad)
    ax.yaxis.set_major_formatter(lambda y, _: f"{int(y // 60)}:{y % 60:04.1f}")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlim(first - 0.5, last + 0.5)
    ax.text(0.99, 0.97, "▲ faster", transform=ax.transAxes, ha="right", va="top", fontsize=8,
            color=COLORS["muted"])
    ax.text(0.99, 0.03, "Pit, out- and VSC laps excluded", transform=ax.transAxes, ha="right",
            va="bottom", fontsize=7.5, color=COLORS["muted"])
    ax.legend(loc="lower left", fontsize=8.5)          # unten links ist nach der VSC leer (alle fahren oben)
    ax.set_xlabel("Lap")
    return times
