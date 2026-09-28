"""Reel „Comeback“: wie sich ein Fahrer durchs Feld nach vorne arbeitet.

ABLAUF (1080 × 1920, 9:16, 60 Bilder/s, ~18 s):
  1. Hook 3D (3,5 s):     Verfolgerkamera hinter dem Fahrer im entscheidenden
                          Überholmanöver – Schnitt KURZ BEVOR er vorbei ist.
                          Große weiße Schrift „P19 → P1“ über der fahrenden Szene.
                          Kein Schwarzbild, keine lila Schrift auf Schwarz: Baku
                          wischten beim schwarzen Titel-Screen ~50 % sofort weg.
  2. Positionskurve (5 s): Platz Runde für Runde bis KURZ VOR dem Manöver (die
                          Auflösung P1 zeigt erst die 3D-Szene), großer Zähler oben. Jedes
                          Überholmanöver blitzt mit dem Kürzel des Überholten auf,
                          unten zählen die Überholmanöver auf der Strecke mit.
                          Rote Flagge rot, SC/VSC gelb, eigener Boxenstopp markiert.
  3. Das Manöver (6,5 s): dieselbe Szene wie am Anfang, jetzt bis er klar vorne ist
                          (~3 s danach), um den Moment herum auf 50 % verlangsamt.
  4. Ziel (4 s):          Schnitt auf die letzte Runde: Zieldurchfahrt unter dem
                          Portal, „CHEQUERED FLAG“. Danach läuft eine Uhr hoch, bis
                          der Zweite die Linie erreicht – am Ende steht der
                          OFFIZIELLE Abstand (Ergebnis), nicht der geschätzte.
  5. Auflösung (2–4 s):   Zahlen über der weiterlaufenden Szene. So lang, dass
                          die Uhr den Abstand erreicht (max. RESULT_MAX_S). Kein
                          Logo-Screen – das Reel läuft direkt in die Schleife.

ÜBERHOLMANÖVER ZÄHLEN (position_events): aus den Positionen an der Ziellinie.
Liegt ein Gegner in Runde n nicht mehr vor dem Fahrer, obwohl er es in n−1 tat:
  - Gegner hat Runde n nicht beendet          → "dnf"   (geschenkt)
  - Gegner war in Runde n oder n−1 an der Box → "pit"   (geschenkt)
    Stopps unter roter Flagge (Dauer > RED_FLAG_STOP_S) zählen nicht – da
    wechseln alle, an der Reihenfolge ändert das nichts.
  - sonst                                     → "track" (echtes Überholmanöver)
Grenze: Mehrere Wechsel innerhalb einer Runde (vorbei und wieder zurück) sieht
man an der Linie nicht. Geprüft an Monza 2026: ANT P19 → P1 bis Runde 18 mit
17 × "track" + LEC "dnf", nach dem Stopp in Runde 28 noch 5 × "track".

DAS MANÖVER: der letzte "track"-Gewinn, der ihn auf seinen Zielplatz bringt
(überschreibbar mit pass = { lap = 50, rival = "RUS" }). Der Zeitpunkt kommt aus
den Positionsdaten: Abstand mit Vorzeichen (dahinter +, davor −), Nulldurchgang.

DIE SEITE (innen/außen) steht NICHT in den Daten – OpenF1 legt alle Autos auf
eine Linie (siehe chase3d). Standard: Innenseite der nächsten Kurve. Mit
pass = { ..., side = "left" | "right" } nach TV-Bildern festlegen.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
from matplotlib import animation
from matplotlib import patheffects as pe
from matplotlib import pyplot as plt
from matplotlib.colors import to_rgb

from stintlab.analyses.positions import compute_positions
from stintlab.race_control import neutral_phases
from stintlab.reels.ghost_lap import _ffmpeg
from stintlab.reels.race_story import live_gap, smooth
from stintlab.style import COLORS, NEUTRAL_STYLE, neutral_legend, resolve_font, team_color

WIDTH_PX, HEIGHT_PX, DPI, FPS = 1080, 1920, 150, 60
HOOK_S, CHART_S, PASS_S, FINISH_S, RESULT_S, RESULT_MAX_S = 3.5, 5.0, 6.5, 4.0, 2.0, 4.0
FINISH_LEAD_S = 2.2      # Ziel-Szene beginnt so viele Sekunden vor der Linie
HOOK_CUT_S = 0.5         # Hook endet so viele Sekunden VOR dem Vorbeiziehen
PASS_LEAD_S = 2.0        # Manöver-Szene beginnt so viele Sekunden davor und läuft ~3 s danach weiter
                         # (bei 4 s Szene war er nur ~1 s vorbei – „man sieht das Überholen kaum“)
SLOWMO = 0.5             # um den Moment herum auf 50 % Tempo
SLOWMO_WIDTH_S = 1.0
RED_FLAG_STOP_S = 300.0
LABEL_LAPS = 5.0         # so viele Runden lang bleibt ein Kürzel an der Kurve stehen
CHART_BOX = [0.14, 0.27, 0.78, 0.45]
WHITE = "#ffffff"
STROKE = [pe.withStroke(linewidth=5, foreground="black", alpha=0.75)]


def ink(background: str) -> str:
    """Schwarz oder Weiß – was auf dieser Farbe lesbar ist."""
    r, g, b = to_rgb(background)
    return "black" if 0.299 * r + 0.587 * g + 0.114 * b > 0.6 else WHITE


# ── Überholmanöver ───────────────────────────────────────────────────────────

def _pit_laps(data: dict) -> dict[str, set[int]]:
    """{Fahrer: Runden mit echtem Boxenstopp} – ohne Stopps unter roter Flagge."""
    out: dict[str, set[int]] = {}
    for p in data.get("pit_stops", []):
        if p.get("lap") and (p.get("duration") or 0) < RED_FLAG_STOP_S:
            out.setdefault(p["driver"], set()).add(int(p["lap"]))
    return out


def position_events(data: dict, drv: str) -> tuple[dict[int, int], dict[str, dict[int, int]], list[dict]]:
    """(eigene Positionen, alle Positionen, Ereignisse). Ereignis:
    {"lap", "rival", "gain": bool, "kind": "track" | "dnf" | "pit"}."""
    pos = compute_positions(data["lap_ends"], data.get("grid"), data.get("results"))
    if drv not in pos:
        raise ValueError(f"Keine Positionen für {drv} – Kürzel prüfen")
    mine = pos[drv]
    pits = _pit_laps(data)
    events = []
    laps = sorted(mine)
    for prev, n in zip(laps, laps[1:]):
        before = {d for d, p in pos.items() if d != drv and p.get(prev, 99) < mine[prev]}
        after = {d for d, p in pos.items() if d != drv and p.get(n, 99) < mine[n]}
        for d in sorted(before - after, key=lambda d: pos[d].get(prev, 99)):
            if n not in pos[d]:
                kind = "dnf"
            elif pits.get(d, set()) & {n, n - 1}:
                kind = "pit"
            else:
                kind = "track"
            events.append({"lap": n, "rival": d, "gain": True, "kind": kind})
        for d in sorted(after - before, key=lambda d: pos[d].get(n, 99)):
            kind = "pit" if pits.get(drv, set()) & {n, n - 1} else "track"
            events.append({"lap": n, "rival": d, "gain": False, "kind": kind})
    return mine, pos, events


def count(events: list[dict], gain: bool, kind: str, upto: float = float("inf")) -> int:
    return sum(1 for e in events if e["gain"] == gain and e["kind"] == kind and e["lap"] <= upto)


def decisive_pass(mine: dict[int, int], pos: dict, events: list[dict]) -> tuple[int, str]:
    """(Runde, Gegner) des letzten Überholmanövers auf der Strecke, das ihn
    auf seinen Zielplatz bringt – sonst des letzten überhaupt."""
    final = mine[max(mine)]
    track = [e for e in events if e["gain"] and e["kind"] == "track"]
    if not track:
        raise ValueError("Kein Überholmanöver auf der Strecke gefunden")
    to_final = [e for e in track if mine[e["lap"]] == final]
    lap = (to_final or track)[-1]["lap"]
    rivals = [e["rival"] for e in track if e["lap"] == lap]
    # mehrere in einer Runde: der, der jetzt direkt hinter ihm liegt
    direct = [r for r in rivals if pos[r].get(lap) == mine[lap] + 1]
    return lap, (direct or rivals)[-1]


def signed_gap(scene, t: float) -> float:
    """Abstand Fahrer (b) zu Gegner (a): + = dahinter, − = davor, NaN = unbekannt."""
    md = 40.0 * scene.scale
    g = live_gap(scene.ta, scene.tb, t, 4.0, md)
    if np.isfinite(g) and g > 0.02:
        return g
    back = live_gap(scene.tb, scene.ta, t, 4.0, md)
    return -back if np.isfinite(back) else (0.0 if np.isfinite(g) else float("nan"))


def pass_time(scene, data: dict, drv: str, lap: int) -> float:
    """Sekunde (ab scene.t0), in der drv vorbeizieht – letzter Wechsel von + nach −."""
    ends = data["lap_ends"][drv]
    lo = (ends.get(lap - 1, ends[lap]) - scene.t0).total_seconds() - 10.0
    hi = (ends[lap] - scene.t0).total_seconds() + 3.0
    ts = np.arange(lo, hi, 0.1)
    g = np.array([signed_gap(scene, t) for t in ts])
    ok = np.isfinite(g)
    ts, g = ts[ok], g[ok]
    cross = np.where((g[:-1] > 0) & (g[1:] <= 0))[0]
    if not len(cross):
        raise ValueError(f"{drv}: Überholmanöver in Runde {lap} nicht in den Positionsdaten gefunden")
    i = int(cross[-1])
    # linear zwischen den beiden Proben
    return float(ts[i] + (ts[i + 1] - ts[i]) * g[i] / (g[i] - g[i + 1]))


def finish_time(scene, data: dict, drv: str) -> float:
    """Sekunde (ab scene.t0), in der drv in seiner letzten Runde die Ziellinie
    (Anfang der Referenzrunde, scene.P[0]) überquert."""
    ends = data["lap_ends"][drv]
    guess = (ends[max(ends)] - scene.t0).total_seconds()
    ts = np.arange(guess - 8.0, guess + 8.0, 0.02)
    xy = scene.world(drv, ts)[:, :2] - scene.P[0, :2]
    along = xy @ scene.T[0]
    near = np.hypot(xy[:, 0], xy[:, 1]) < 60.0
    cross = np.where(near[:-1] & (along[:-1] < 0) & (along[1:] >= 0))[0]
    if not len(cross):
        return guess
    i = int(cross[np.argmin(np.abs(ts[cross] - guess))])
    return float(ts[i] + (ts[i + 1] - ts[i]) * -along[i] / (along[i + 1] - along[i]))


def runner_up(data: dict, drv: str) -> tuple[str, float] | None:
    """(Zweiter, offizieller Abstand) – nur wenn drv gewonnen hat."""
    rows = {r.get("position"): r for r in data.get("results", []) if r.get("position")}
    if rows.get(1, {}).get("driver") != drv or 2 not in rows:
        return None
    gap = rows[2].get("gap")
    return (rows[2]["driver"], float(gap)) if isinstance(gap, (int, float)) else None


def slowmo_times(t_pass: float, duration: float, lead: float = PASS_LEAD_S, fps: int = FPS) -> np.ndarray:
    """Echtzeit, die um t_pass herum weich auf (1 − SLOWMO) abbremst."""
    t = t_pass - lead
    out = []
    for _ in range(int(duration * fps)):
        out.append(t)
        speed = 1.0 - SLOWMO * np.exp(-((t - t_pass) / SLOWMO_WIDTH_S) ** 2)
        t += speed / fps
    return np.array(out)


# ── Vorbereitung (ohne Zeichnen, testbar) ────────────────────────────────────

def prepare(data: dict, reel: dict) -> dict:
    drivers = reel.get("drivers") or []
    if not drivers:
        raise ValueError('comeback braucht einen Fahrer, z. B. drivers = ["ANT"]')
    drv = drivers[0]
    mine, pos, events = position_events(data, drv)
    if reel.get("pass"):
        lap, rival = int(reel["pass"]["lap"]), reel["pass"]["rival"]
    else:
        lap, rival = decisive_pass(mine, pos, events)

    from stintlab.reels.chase3d import Scene
    scene = Scene(data, rival, drv, ref=drv)     # Kamera hinter drv, Gegner vor ihm
    scene.configure(reel)
    # Hauptfigur immer in Teamfarbe; bei Teamkollegen bekommt der GEGNER das Weiß
    teams = data.get("teams", {})
    scene.col[drv] = team_color(teams.get(drv))
    if team_color(teams.get(rival)) == scene.col[drv]:
        scene.col[rival] = COLORS["text"]
    t_pass = pass_time(scene, data, drv, lap)
    side_cfg = (reel.get("pass") or {}).get("side")
    if side_cfg not in (None, "left", "right"):
        raise ValueError('pass.side muss "left" oder "right" sein')
    side = {"left": 1.0, "right": -1.0}.get(side_cfg) or scene.corner_side(t_pass - 1.0)
    scene.set_pass(t_pass, side)
    hook_times = t_pass - HOOK_CUT_S - HOOK_S + np.arange(int(HOOK_S * FPS)) / FPS
    pass_times = slowmo_times(t_pass, PASS_S)
    t_fin = finish_time(scene, data, drv)
    finish_times = slowmo_times(t_fin, FINISH_S, lead=FINISH_LEAD_S)
    runner = runner_up(data, drv)
    after = finish_times[-1] - t_fin          # echte Sekunden nach der Linie am Ende der Ziel-Szene
    res_s = float(np.clip(runner[1] - after + 0.6, RESULT_S, RESULT_MAX_S)) if runner else RESULT_S
    result_times = finish_times[-1] + np.arange(1, int(res_s * FPS) + 1) / FPS
    gaps = {k: smooth(np.array([signed_gap(scene, t) for t in ts]), 9)
            for k, ts in (("hook", hook_times), ("pass", pass_times))}

    laps = sorted(mine)
    start, final = mine[laps[0]], mine[laps[-1]]
    return {"drv": drv, "rival": rival, "lap": lap, "scene": scene, "t_pass": t_pass,
            "side": "left" if side > 0 else "right", "side_given": side_cfg is not None,
            "mine": mine, "pos": pos, "events": events, "laps": laps, "start": start, "final": final,
            "last_lap": laps[-1], "n_track": count(events, True, "track"),
            "n_dnf": count(events, True, "dnf"), "n_pit": count(events, True, "pit"),
            "hook_times": hook_times, "pass_times": pass_times, "finish_times": finish_times,
            "result_times": result_times, "t_fin": t_fin, "runner": runner,
            "hook_gap": gaps["hook"], "pass_gap": gaps["pass"],
            "phases": neutral_phases(data.get("race_control", []), laps[0], laps[-1]),
            "own_pits": sorted(n for n in _pit_laps(data).get(drv, set()) if laps[0] <= n <= laps[-1])}


def frame_list(prep: dict) -> list[tuple[str, float]]:
    frames = [("hook", i) for i in range(len(prep["hook_times"]))]
    n = int(CHART_S * FPS)
    lo = prep["laps"][0]
    hi = max(lo, prep["lap"] - 1)       # stoppt vor der Runde des Manövers: P1 zeigt erst die 3D-Szene
    u = np.linspace(0.0, 1.0, n)
    ease = 0.75 * u + 0.25 * (1 - (1 - u) ** 2)      # zum Ende hin etwas langsamer
    frames += [("chart", lo + (hi - lo) * e) for e in ease]
    frames += [("pass", i) for i in range(len(prep["pass_times"]))]
    frames += [("finish", i) for i in range(len(prep["finish_times"]))]
    frames += [("result", i) for i in range(len(prep["result_times"]))]
    return frames


def _report(prep: dict) -> None:
    ev = prep["events"]
    print(f"  Comeback {prep['drv']}: P{prep['start']} → P{prep['final']} · auf der Strecke "
          f"{prep['n_track']} · Ausfälle {prep['n_dnf']} · fremde Stopps {prep['n_pit']} · "
          f"verloren {sum(1 for e in ev if not e['gain'])}")
    if prep.get("runner"):
        print(f"    Ziel: t = {prep['t_fin']:.1f} s · {prep['runner'][0]} +{prep['runner'][1]:.3f} s (offiziell)")
    print(f"    Manöver: Runde {prep['lap']} gegen {prep['rival']} bei t = {prep['t_pass']:.1f} s · Seite "
          f"{prep['side']}" + ("" if prep["side_given"] else " (geschätzt: Innenseite der nächsten Kurve – "
                                                             "mit pass.side nach TV-Bildern prüfen)"))


# ── Video ────────────────────────────────────────────────────────────────────

def _fmt(g: float) -> str:
    if not np.isfinite(g):
        return "–"
    return f"{abs(g):.1f} s" if abs(g) >= 1 else f"{abs(g):.2f} s"


def render_comeback(data: dict, reel: dict, path: Path) -> Path:
    prep = prepare(data, reel)
    _report(prep)
    drv, rival, scene = prep["drv"], prep["rival"], prep["scene"]
    mine, pos, events, laps = prep["mine"], prep["pos"], prep["events"], prep["laps"]
    last_lap, lap = prep["last_lap"], prep["lap"]
    col = scene.col[drv]
    n_cars = max(max(p.values()) for p in pos.values())

    # Hatte er den Zielplatz schon einmal und hat ihn wieder verloren? Dann ist das die Story.
    first_reach = next((n for n in laps if mine[n] == prep["final"]), None)
    again = first_reach is not None and any(mine[n] != prep["final"] for n in laps if first_reach < n < lap)
    hook = reel.get("hook") or (f"P{prep['start']} → P{prep['final']} – then he had to do it again" if again else
                                f"P{prep['start']} → P{prep['final']} – {prep['n_track']} places gained on track")
    hook_1, _, hook_2 = hook.partition(" – ")
    result = reel.get("result") or f"P{prep['start']} → P{prep['final']}"
    gifts = []
    if prep["n_dnf"]:
        gifts.append(f"{prep['n_dnf']} from retirements")
    if prep["n_pit"]:
        gifts.append(f"{prep['n_pit']} from others' pit stops")
    result_sub = reel.get("result_sub") or (f"{prep['n_track']} places gained on track"
                                            + (f" · {' · '.join(gifts)}" if gifts else ""))

    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [resolve_font()]
    fig = plt.figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI, facecolor=COLORS["bg"])

    # ── 3D-Ebene + Verlauf oben/unten, damit weiße Schrift immer lesbar ist ──
    ax_3d = fig.add_axes([0, 0, 1, 1], zorder=-2)
    ax_shade = fig.add_axes([0, 0, 1, 1], zorder=-1)
    ax_shade.axis("off")
    yy = np.linspace(0, 1, 400)
    alpha = np.clip(np.maximum((yy - 0.66) / 0.34, (0.24 - yy) / 0.24), 0, 1) * 0.8
    shade = np.zeros((400, 1, 4))
    shade[:, 0, 3] = alpha
    ax_shade.imshow(shade, extent=(0, 1, 0, 1), origin="lower", aspect="auto", interpolation="bilinear")
    ax_shade.set_xlim(0, 1)
    ax_shade.set_ylim(0, 1)
    from stintlab.reels.chase3d import MiniMap, draw_scene
    minimap = MiniMap(fig, scene)

    # ── Positionskurve ───────────────────────────────────────────────────────
    ax = fig.add_axes(CHART_BOX)
    ax.set_facecolor(COLORS["bg"])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(COLORS["grid"])
    ax.tick_params(colors=COLORS["muted"], labelsize=14)
    ax.grid(color=COLORS["grid"], linewidth=0.6, axis="y")
    ax.set_xlim(laps[0] - 0.5, last_lap + 0.5)
    ax.set_ylim(n_cars + 0.7, 0.3)
    ticks = [1] + list(range(5, n_cars + 1, 5))
    ax.set_yticks(ticks, [f"P{t}" for t in ticks])
    ax.set_xlabel("Lap", color=COLORS["muted"], fontsize=14)
    for lo, hi, kind in prep["phases"]:
        c, _, short, _ = NEUTRAL_STYLE[kind]
        ax.axvspan(lo - 0.5, hi + 0.5, color=c, alpha=0.22 if kind == "RED" else 0.14, linewidth=0, zorder=0)
        ax.text((lo + hi) / 2, 0.45, short, ha="center", va="bottom", fontsize=11, fontweight="bold", color=c)
    others = {d: ax.plot([], [], color=COLORS["muted"], linewidth=0.8, alpha=0.22, zorder=1)[0]
              for d in pos if d != drv}
    line, = ax.plot([], [], color=col, linewidth=3.2, zorder=4, solid_capstyle="round")
    head = ax.scatter([], [], s=120, color=col, edgecolor="white", linewidth=1.4, zorder=5)
    pit_marks = [ax.text(n, max(mine.get(k, 0) for k in (n, n + 1, n + 2)) + 0.9, "PIT", ha="center", va="top", fontsize=13,
                         fontweight="bold", color=WHITE, visible=False) for n in prep["own_pits"]]
    pop = ax.text(0, 0, "", ha="left", va="center", fontsize=17, fontweight="bold", color=WHITE, zorder=6,
                  path_effects=STROKE)
    xs_all = np.array(laps, dtype=float)
    ys_all = np.array([mine[n] for n in laps], dtype=float)

    # ── Texte ────────────────────────────────────────────────────────────────
    t_hook1 = fig.text(0.5, 0.905, hook_1, ha="center", va="center", fontsize=58 if len(hook_1) < 12 else 36,
                       fontweight="black", color=WHITE, path_effects=STROKE)
    t_hook2 = fig.text(0.5, 0.848, hook_2, ha="center", va="center", fontsize=22 if len(hook_2) < 30 else 17,
                       fontweight="bold", color=WHITE, path_effects=STROKE)
    t_tag = fig.text(0.5, 0.805, "", ha="center", va="center", fontsize=12, fontweight="bold", color=ink(col),
                     bbox={"boxstyle": "round,pad=0.45", "facecolor": col, "edgecolor": "none"})
    t_gap = fig.text(0.5, 0.115, "", ha="center", va="center", fontsize=44, fontweight="bold", color=WHITE,
                     path_effects=STROKE)
    t_gap_sub = fig.text(0.5, 0.07, "", ha="center", va="center", fontsize=14, color=WHITE, path_effects=STROKE)
    t_p1 = fig.text(0.5, 0.60, "", ha="center", va="center", fontsize=64, fontweight="black", color=ink(col),
                    bbox={"boxstyle": "round,pad=0.3", "facecolor": col, "edgecolor": "none"})
    t_big = fig.text(0.5, 0.885, "", ha="center", va="center", fontsize=72, fontweight="black", color=WHITE)
    t_sub = fig.text(0.5, 0.815, "", ha="center", va="center", fontsize=18, color=COLORS["muted"])
    t_tense = fig.text(0.5, 0.768, "", ha="center", va="center", fontsize=18, fontweight="bold", color=WHITE)
    t_count = fig.text(0.5, 0.165, "", ha="center", va="center", fontsize=21, fontweight="bold", color=WHITE)
    t_res1 = fig.text(0.5, 0.135, result, ha="center", va="center", fontsize=46, fontweight="black", color=WHITE,
                      path_effects=STROKE)
    t_res2 = fig.text(0.5, 0.088, result_sub, ha="center", va="center", fontsize=14, fontweight="bold",
                      color=WHITE, path_effects=STROKE, wrap=True)
    fig.text(0.94, 0.965, "STINTLAB", ha="right", va="center", fontsize=11, fontweight="bold",
             color=COLORS["accent"], path_effects=STROKE)
    t_foot = fig.text(0.06, 0.225, "", ha="left", va="top", fontsize=7.5, color=COLORS["muted"], linespacing=1.5)
    t_fin_gap = fig.text(0.5, 0.235, "", ha="center", va="center", fontsize=40, fontweight="black", color=WHITE,
                         path_effects=STROKE)
    t_fin_sub = fig.text(0.5, 0.197, "", ha="center", va="center", fontsize=14, fontweight="bold", color=WHITE,
                         path_effects=STROKE)

    groups = {
        "hook": [ax_3d, ax_shade, t_hook1, t_hook2, t_tag, t_gap, t_gap_sub],
        "chart": [ax, t_big, t_sub, t_count, t_foot, t_tense],
        "pass": [ax_3d, ax_shade, t_tag, t_gap, t_gap_sub, t_p1],
        "finish": [ax_3d, ax_shade, t_tag, t_gap, t_gap_sub, t_p1, t_fin_gap, t_fin_sub],
        "result": [ax_3d, ax_shade, t_res1, t_res2, t_fin_gap, t_fin_sub],
    }
    everything = {a for g in groups.values() for a in g}

    def show(phase: str) -> None:
        for art in everything:
            art.set_visible(art in groups[phase])
        minimap.set_visible(phase in ("hook", "pass", "finish"))

    def gap_text(g: float) -> None:
        if not np.isfinite(g):
            t_gap.set_text("")
            t_gap_sub.set_text("")
        elif g > 0.005:
            t_gap.set_text(_fmt(g))
            t_gap_sub.set_text(f"{drv} behind {rival}")
        else:
            t_gap.set_text(_fmt(g) if abs(g) >= 0.05 else "0.00 s")
            t_gap_sub.set_text(f"{drv} ahead of {rival}")

    tag_3d = f"LAP {lap} / {last_lap} · FOR P{prep['final']}"
    chart_end = max(laps[0], lap - 1)
    ends = data["lap_ends"]
    gap_before = ((ends[drv][chart_end] - ends[rival][chart_end]).total_seconds()
                  if chart_end in ends.get(drv, {}) and chart_end in ends.get(rival, {}) else None)

    def draw_chart(p: float) -> None:
        show("chart")
        m = xs_all <= p
        xs = np.append(xs_all[m], p)
        ys = np.interp(xs, xs_all, ys_all)
        line.set_data(xs, ys)
        head.set_offsets([[xs[-1], ys[-1]]])
        for d, art in others.items():
            s = pos[d]
            ox = [n for n in sorted(s) if n <= p]
            art.set_data(ox, [s[n] for n in ox])
        for mark, n in zip(pit_marks, prep["own_pits"]):
            mark.set_visible(p >= n)
        now = int(np.floor(p))
        place = mine.get(now) or int(round(ys[-1]))
        t_big.set_text(f"P{place}")
        t_big.set_color(col if place == prep["final"] and now >= lap else WHITE)
        t_sub.set_text(f"{drv} · LAP {now} / {last_lap}" if now > 0 else f"{drv} · GRID")
        n_track = count(events, True, "track", now)
        t_count.set_text(f"PLACES GAINED ON TRACK   {n_track}")
        # Kürzel der letzten Positionswechsel an der Kurve
        recent = [e for e in events if now - LABEL_LAPS < e["lap"] <= now]
        if recent:
            n = recent[-1]["lap"]
            here = [e for e in recent if e["lap"] == n]
            words = []
            for e in here:
                if e["gain"]:
                    words.append(e["rival"] if e["kind"] == "track" else
                                 f"{e['rival']} OUT" if e["kind"] == "dnf" else f"{e['rival']} PITS")
                elif e["kind"] == "track":
                    words.append(f"{e['rival']} PASSES")
            if any(not e["gain"] and e["kind"] == "pit" for e in here):
                words = ["PIT STOP"]
            gains = sum(1 for e in here if e["gain"])
            lost = len(here) - gains
            head_txt = f"+{gains} " if gains and not lost else (f"−{lost} " if lost and not gains else "")
            pop.set_text(head_txt + " · ".join(words[:3]) + (" …" if len(words) > 3 else ""))
            right = n > (laps[0] + last_lap) * 0.6
            pop.set_position((n + (-0.8 if right else 0.8), mine[n] + (1.3 if mine[n] < 4 else -1.2)))
            pop.set_ha("right" if right else "left")
            pop.set_color(WHITE if gains else COLORS["muted"])
            pop.set_visible(True)
        else:
            pop.set_visible(False)
        # Spannung vor dem Schnitt in 3D: wer vorne ist und wie weit (über der Grafik, nicht auf der Kurve)
        tense = p >= chart_end - 3.0 and gap_before is not None and not recent
        t_tense.set_text(f"{rival} {gap_before:.1f} s AHEAD · {last_lap - chart_end} LAPS LEFT" if tense else "")
        t_foot.set_text("Data: OpenF1 · position at the finish line each lap · "
                        + neutral_legend(k for *_, k in prep["phases"])
                        + "\nplaces gained on track = not from retirements or other cars' pit stops")

    def draw_3d(phase: str, i: int) -> None:
        show(phase)
        ts = prep[f"{phase}_times"]
        t = ts[i]
        draw_scene(ax_3d, scene, t)
        minimap.update(t)
        if phase in ("finish", "result"):
            draw_finish(phase, t)
            return
        t_tag.set_text(tag_3d)
        g = prep[f"{phase}_gap"][i]
        gap_text(g)
        if phase == "pass":
            passed = t >= prep["t_pass"]
            t_p1.set_text(f"P{prep['final']}" if passed else "")
            t_p1.set_visible(passed and t <= prep["t_pass"] + 2.0)

    t_fin, runner = prep["t_fin"], prep["runner"]

    def draw_finish(phase: str, t: float) -> None:
        el = t - t_fin
        if el < 0:
            t_tag.set_text(f"LAP {last_lap} / {last_lap} · FINAL LAP")
            pb, _ = scene.pos(drv, t)
            to_go = -float((pb[:2] - scene.P[0, :2]) @ scene.T[0])
            t_gap.set_text(f"{max(to_go, 0):.0f} m")
            t_gap_sub.set_text("to the chequered flag")
            t_p1.set_visible(False)
            t_fin_gap.set_text("")
            t_fin_sub.set_text("")
            return
        t_tag.set_text("CHEQUERED FLAG")
        t_gap.set_text("")
        t_gap_sub.set_text("")
        t_p1.set_text("WINNER" if prep["final"] == 1 else f"P{prep['final']}")
        t_p1.set_visible(phase == "finish" and el < 1.6)
        if runner:
            name, gap = runner
            if el < gap:     # Uhr läuft, bis der Zweite die Linie erreicht
                t_fin_gap.set_text(f"+{el:.1f} s")
                t_fin_sub.set_text(f"{name} still to cross the line")
            else:
                t_fin_gap.set_text(f"{gap:.3f} s")
                t_fin_sub.set_text(f"ahead of {name} · official gap")
        else:
            t_fin_gap.set_text(f"P{prep['final']}")
            t_fin_sub.set_text("")

    def draw(phase: str, v) -> None:
        if phase == "chart":
            draw_chart(float(v))
        else:
            draw_3d(phase, int(v))

    matplotlib.rcParams["animation.ffmpeg_path"] = _ffmpeg()
    writer = animation.FFMpegWriter(fps=FPS, codec="libx264", extra_args=["-pix_fmt", "yuv420p", "-crf", "20"])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = frame_list(prep)
    step = max(len(frames) // 10, 1)
    with writer.saving(fig, str(path), dpi=DPI):
        last = None
        for i, (phase, v) in enumerate(frames):
            key = (phase, round(float(v), 4))
            if key != last:
                draw(phase, v)
                last = key
            writer.grab_frame(facecolor=COLORS["bg"])
            if i % step == 0:
                print(f"  {100 * i // len(frames):3d} %  ({i}/{len(frames)} Bilder)", flush=True)
    plt.close(fig)
    return path

