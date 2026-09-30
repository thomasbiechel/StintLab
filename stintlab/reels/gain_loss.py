"""Reel „Gain / Loss“: Wo holt der Verfolger auf, wo verliert er – und warum reicht es nie?

Gebaut nach der Auswertung des São-Paulo-Rewinds (Instagram: 0,4 % geteilt,
TikTok: die meisten weg bei 0:01, Antwort stand nur in der Caption):
  - Die ANTWORT steht als Behauptung im ersten Bild, nicht erst am Ende.
  - Die Animation zeigt, was das TV nicht zeigt (Abstand an jedem Punkt der Runde).
  - Am Ende eine konkrete Frage an die Zuschauer (Kommentare).

ABLAUF (1080 × 1920, 9:16, 60 Bilder/s, ~21 s):
  1. Anfang 3D (4 s):   Verfolgerkamera hinter B auf der Geraden, B kommt heran.
                        Oben die Behauptung (hook), unten der laufende Abstand.
  2. Karte (7 s):       eine Durchschnittsrunde (Median über `laps`) läuft einmal
                        um die Strecke. Die Strecke färbt sich: Lila = B holt auf,
                        Rot = B verliert. Nach jedem Sektor erscheint dessen Bilanz
                        (offizielle Sektorzeiten, Median).
  3. Bilanz (4,5 s):    ein Balken pro Runde – oben, was B gewinnt, unten, was er
                        verliert. Darunter die beiden Summen und das Netto.
  4. Antwort (3 s):     die Antwort in einem Satz (answer), darunter der kleinste
                        Abstand aus dem 3D-Anfang.
  5. Frage (2,5 s):     Frage an die Zuschauer (question) – letztes Bild, danach Schleife.

ZAHLEN: Gewinn/Verlust kommen aus den offiziellen Sektorzeiten (sector_delta,
Median je Sektor, ohne SC/VSC- und Boxenrunden) – dieselben Werte wie auf der
Karussell-Slide. Sektoren mit Median < 0 zählen als Gewinn von B, die anderen
als Verlust. Die Färbung der Karte kommt aus den Positionsdaten (gap_on_lap)
und ist nur qualitativ (Steigung des geglätteten Abstands).

NETTO: Summe der Sektor-Mediane ist nicht gleich dem Median der Rundenzeiten
(Baku 40–50: −0,016 s vs. +0,015 s). Liegt das Netto unter NET_ZERO_S, zeigt
das Reel deshalb „≈ 0.0 s“ statt einer Scheingenauigkeit.

In der post.toml:
    [[reels]]
    analysis   = "gain_loss"
    drivers    = ["RUS", "VER"]          # [vorne, Verfolger]
    laps       = [40, 50]
    hook       = "Faster on every straight – and never passed"   # Zeile 1 – Zeile 2
    gain_label = "on the straight"       # Standard: Sektornamen, z. B. "in S3"
    loss_label = "in the corners"
    answer     = "The tow gave him the speed – the corners took it back"
    question   = "Where should Verstappen have attacked?"
    open_lap   = 46                      # optional: Runde für den 3D-Anfang
    open_tag   = "LAP 46 · THE LONG STRAIGHT"   # optional
"""

from __future__ import annotations

from pathlib import Path
from statistics import median

import matplotlib
import numpy as np
from matplotlib import animation, patheffects
from matplotlib import pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import to_rgba

from stintlab.analyses.gap_on_lap import compute_gap_on_lap
from stintlab.analyses.sector_delta import compute_sector_delta
from stintlab.reels.ghost_lap import _ffmpeg, needs_rotation
from stintlab.style import COLORS, resolve_font, team_color

WIDTH_PX, HEIGHT_PX, DPI, FPS = 1080, 1920, 150, 60
OPEN_S, MAP_RUN_S, MAP_HOLD_S, TRADE_GROW_S, TRADE_HOLD_S, ANSWER_S, ASK_S = 4.0, 5.5, 1.5, 2.5, 2.0, 3.0, 2.5
GAIN = COLORS["accent"]          # Lila = B holt auf
LOSS = "#ff5a5f"                 # Rot = B verliert (bewusst kein Teamrot, heller)
NET_ZERO_S = 0.05                # darunter: „≈ 0.0 s“
SMOOTH_BINS = 9                  # Glättung der Abstandskurve für die Färbung (Abschnitte)
OPEN_SEARCH_S = (-9.0, 5.0)      # Suchfenster um den Rundenbeginn für den 3D-Anfang
SECTORS = ["Sector1", "Sector2", "Sector3"]
MAP_BOX = [0.07, 0.30, 0.86, 0.43]
CHART_BOX = [0.12, 0.50, 0.78, 0.24]


# ── Rechnen (ohne Zeichnen, testbar) ─────────────────────────────────────────

def smooth_circular(values: np.ndarray, width: int = SMOOTH_BINS) -> np.ndarray:
    """Gleitender Mittelwert über eine geschlossene Runde; Lücken (NaN) werden
    vorher linear gefüllt, ebenfalls über die Ziellinie hinweg."""
    v = np.asarray(values, dtype=float)
    n = len(v)
    ok = ~np.isnan(v)
    if not ok.any():
        raise ValueError("keine Abstandswerte")
    idx = np.arange(n)
    filled = np.interp(idx, idx[ok], v[ok], period=n)
    half = width // 2
    padded = np.concatenate([filled[-half:], filled, filled[:half]]) if half else filled
    return np.convolve(padded, np.ones(width) / width, mode="valid")


def sector_balance(deltas: dict[str, dict[int, float]]) -> dict:
    """Aus {Sektor: {Runde: Zeit B − Zeit A}}: welche Sektoren B gewinnt, welche er
    verliert, die Summen (positiv) und je Runde Gewinn/Verlust."""
    med = {s: median(deltas[s].values()) for s in SECTORS if deltas.get(s)}
    if len(med) < 2:
        raise ValueError("zu wenige Sektorzeiten für eine Bilanz")
    gain_s = [s for s in med if med[s] < 0]
    loss_s = [s for s in med if med[s] >= 0]
    if not gain_s or not loss_s:
        raise ValueError("B gewinnt oder verliert in allen Sektoren – dafür passt dieses Reel nicht")
    laps = sorted(set.intersection(*(set(deltas[s]) for s in med)))
    per_lap = [(n, -sum(deltas[s][n] for s in gain_s), sum(deltas[s][n] for s in loss_s)) for n in laps]
    gain = -sum(med[s] for s in gain_s)
    loss = sum(med[s] for s in loss_s)
    return {"median": med, "gain_sectors": gain_s, "loss_sectors": loss_s, "gain": gain, "loss": loss,
            "net": gain - loss, "per_lap": per_lap}


def sector_names(sectors: list[str]) -> str:
    return " + ".join(s.replace("Sector", "S") for s in sectors)


def fmt_signed(v: float) -> str:
    return f"{'+' if v >= 0 else '−'}{abs(v):.2f} s"


def fmt_net(v: float) -> str:
    return "≈ 0.0 s" if abs(v) < NET_ZERO_S else fmt_signed(v)


def pick_open_lap(per_lap: dict[int, np.ndarray], x_m: np.ndarray, length: float) -> int:
    """Runde, in der B nach der Ziellinie (Ende der Start-Ziel-Geraden) am nächsten dran war."""
    near = (x_m < 0.08 * length)
    best = {n: float(np.nanmin(g[near])) for n, g in per_lap.items() if np.any(~np.isnan(g[near]))}
    if not best:
        return min(per_lap)
    return min(best, key=best.get)


def timeline() -> list[tuple[str, float]]:
    """[(Phase, Fortschritt 0–1)] für jedes Bild."""
    out = []
    for phase, secs in (("open", OPEN_S), ("map", MAP_RUN_S), ("map_hold", MAP_HOLD_S),
                        ("trade", TRADE_GROW_S), ("trade_hold", TRADE_HOLD_S), ("answer", ANSWER_S),
                        ("ask", ASK_S)):
        n = int(round(secs * FPS))
        out += [(phase, i / max(n - 1, 1)) for i in range(n)]
    return out


def prepare(data: dict, reel: dict) -> dict:
    drivers = reel.get("drivers") or []
    laps = reel.get("laps") or []
    if len(drivers) != 2:
        raise ValueError('gain_loss braucht drivers = [vorne, Verfolger], z. B. ["RUS", "VER"]')
    if len(laps) != 2:
        raise ValueError("gain_loss braucht laps = [erste, letzte], z. B. laps = [40, 50]")
    a, b = drivers
    laps = (int(laps[0]), int(laps[1]))
    bal = sector_balance(compute_sector_delta(data, a, b, laps))
    gol = compute_gap_on_lap(data, a, b, laps)
    curve = smooth_circular(gol["median"])

    from stintlab.reels.chase3d import Scene
    scene = Scene(data, a, b)
    scene.configure(reel)

    open_lap = int(reel.get("open_lap") or pick_open_lap(gol["per_lap"], gol["x_m"], gol["length_m"]))
    ends = data["lap_ends"][a]
    if open_lap - 1 not in ends:
        raise ValueError(f"open_lap {open_lap}: Rundenbeginn von {a} fehlt")
    line_t = (ends[open_lap - 1] - scene.t0).total_seconds()
    probe = np.arange(line_t + OPEN_SEARCH_S[0], line_t + OPEN_SEARCH_S[1], 0.25)
    g = np.array([scene.gap(t) for t in probe])
    if np.all(np.isnan(g)):
        raise ValueError(f"Runde {open_lap}: kein Abstand aus den Positionsdaten")
    t_close = float(probe[int(np.nanargmin(g))])
    open_times = t_close - OPEN_S + 0.6 + np.arange(int(OPEN_S * FPS)) / FPS
    open_gaps = np.array([scene.gap(t) for t in open_times[::6]])

    return {"a": a, "b": b, "laps": laps, "bal": bal, "gol": gol, "curve": curve, "scene": scene,
            "open_lap": open_lap, "open_times": open_times, "closest": float(np.nanmin(open_gaps))}


def _report(prep: dict) -> None:
    bal, a, b = prep["bal"], prep["a"], prep["b"]
    meds = " · ".join(f"{s.replace('Sector', 'S')} {v:+.3f}" for s, v in bal["median"].items())
    print(f"  Gain/Loss {b} vs {a}, Runden {prep['laps'][0]}–{prep['laps'][1]} "
          f"({len(bal['per_lap'])} Runden mit allen Sektoren)")
    print(f"    Sektor-Median (B − A): {meds}")
    print(f"    {b} gewinnt {bal['gain']:.3f} s ({sector_names(bal['gain_sectors'])}), "
          f"verliert {bal['loss']:.3f} s ({sector_names(bal['loss_sectors'])}) → netto {bal['net']:+.3f} s")
    print(f"    3D-Anfang: Runde {prep['open_lap']}, kleinster Abstand {prep['closest']:.2f} s")


# ── Video ────────────────────────────────────────────────────────────────────

def _stroke(*texts) -> None:
    for tx in texts:
        tx.set_path_effects([patheffects.withStroke(linewidth=4, foreground="black", alpha=0.75)])


def _ease(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def render_gain_loss(data: dict, reel: dict, path: Path) -> Path:
    prep = prepare(data, reel)
    _report(prep)
    a, b, bal, gol, scene = prep["a"], prep["b"], prep["bal"], prep["gol"], prep["scene"]
    lap_lo, lap_hi = prep["laps"]
    teams = data.get("teams", {})
    cb = team_color(teams.get(b))
    gain_label = reel.get("gain_label") or f"in {sector_names(bal['gain_sectors'])}"
    loss_label = reel.get("loss_label") or f"in {sector_names(bal['loss_sectors'])}"
    hook = reel.get("hook") or f"{b} gained {bal['gain']:.2f} s every lap – and never passed"
    answer = reel.get("answer") or f"Faster {gain_label} – slower {loss_label}"
    question = reel.get("question") or f"Where should {b} have attacked?"
    open_tag = reel.get("open_tag") or f"LAP {prep['open_lap']}"

    from stintlab.reels.cover import last_name, make_cover, session_meta
    hook_1, _, hook_2 = hook.partition(" – ")
    make_cover(reel, path, scene, float(prep["open_times"][-1] - 0.6), hook_1,
               kicker=f"{last_name(data, b)} vs {last_name(data, a)}", sub=hook_2, meta=session_meta(data))

    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [resolve_font(), "DejaVu Sans"]   # DejaVu als Ersatz für fehlende Zeichen
    fig = plt.figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI, facecolor=COLORS["bg"])

    # ── 3D-Anfang ────────────────────────────────────────────────────────────
    ax_3d = fig.add_axes([0, 0, 1, 1], zorder=-1)
    from stintlab.reels.chase3d import MiniMap, draw_scene
    minimap = MiniMap(fig, scene, box=(0.05, 0.56, 0.24, 0.17),
                      sector_fracs=[s / gol["length_m"] for s in gol["sectors_m"]])
    open_txt = [fig.text(0.5, 0.855, hook_1, ha="center", va="center", fontsize=30 if len(hook_1) < 26 else 25,
                         fontweight="bold", color=COLORS["text"]),
                fig.text(0.5, 0.81, hook_2, ha="center", va="center", fontsize=30 if len(hook_2) < 26 else 25,
                         fontweight="bold", color=COLORS["accent"]),
                fig.text(0.5, 0.772, open_tag, ha="center", va="center", fontsize=13, fontweight="bold",
                         color=COLORS["muted"])]
    # Abstand oben unter dem Haken: unten lag er über dem Auto (und unter der TikTok-Caption)
    open_gap = fig.text(0.62, 0.705, "", ha="center", va="center", fontsize=40, fontweight="bold",
                        color=COLORS["text"])
    open_txt += [open_gap, fig.text(0.62, 0.668, f"{b} behind {a}", ha="center", va="center", fontsize=14,
                                    fontweight="bold", color=COLORS["text"])]
    _stroke(*open_txt)
    open_hist: list[float] = []

    # ── Karte ────────────────────────────────────────────────────────────────
    P = scene.P[:, :2].copy()
    if needs_rotation(P[:, 0], P[:, 1]):
        P = np.column_stack([P[:, 1], -P[:, 0]])
    frac = scene.cum / scene.cum[-1]
    ax_map = fig.add_axes(MAP_BOX)
    ax_map.set_aspect("equal")
    ax_map.axis("off")
    ax_map.plot(P[:, 0], P[:, 1], color=COLORS["grid"], linewidth=16, solid_capstyle="round", zorder=1)
    ax_map.plot(P[:, 0], P[:, 1], color="#2a2d38", linewidth=9, solid_capstyle="round", zorder=2)
    ax_map.scatter([P[0, 0]], [P[0, 1]], s=70, marker="s", color="white", zorder=6)

    curve, n_bins = prep["curve"], len(prep["curve"])
    slope = np.gradient(np.concatenate([curve[-1:], curve, curve[:1]]))[1:-1]
    strength = np.clip(np.abs(slope) / (np.percentile(np.abs(slope), 85) or 1.0), 0.25, 1.0)
    seg_bin = np.clip((frac[:-1] * n_bins).astype(int), 0, n_bins - 1)
    seg_rgba = np.array([to_rgba(GAIN if slope[k] < 0 else LOSS, strength[k]) for k in seg_bin])
    painted = LineCollection(np.stack([P[:-1], P[1:]], axis=1), linewidths=9, capstyle="round", zorder=3)
    ax_map.add_collection(painted)
    dot = ax_map.scatter([], [], s=260, color=cb, edgecolor="white", linewidth=2, zorder=8)
    dot_label = ax_map.text(0, 0, b, fontsize=12, fontweight="bold", color="white", ha="left", va="center",
                            zorder=9, bbox={"boxstyle": "round,pad=0.28", "facecolor": cb, "edgecolor": "none"})
    for s_m in gol["sectors_m"]:
        i = int(np.searchsorted(frac, s_m / gol["length_m"]))
        ax_map.scatter([P[min(i, len(P) - 1), 0]], [P[min(i, len(P) - 1), 1]], s=46, color=COLORS["muted"],
                       zorder=5)

    txt_kicker = fig.text(0.5, 0.875, "", ha="center", va="center", fontsize=13, fontweight="bold",
                          color=COLORS["muted"])
    txt_big = fig.text(0.5, 0.83, "", ha="center", va="center", fontsize=40, fontweight="bold")
    txt_sub = fig.text(0.5, 0.785, "", ha="center", va="center", fontsize=14, color=COLORS["muted"])
    # farbige Kästchen statt „●“ (fehlt in Barlow)
    legend = [fig.text(0.47, 0.75, f"{b} GAINING", ha="right", va="center", fontsize=12, fontweight="bold",
                       color="white", bbox={"boxstyle": "round,pad=0.35", "facecolor": GAIN, "edgecolor": "none"}),
              fig.text(0.53, 0.75, f"{b} LOSING", ha="left", va="center", fontsize=12, fontweight="bold",
                       color="white", bbox={"boxstyle": "round,pad=0.35", "facecolor": LOSS, "edgecolor": "none"})]
    chips = []
    for i, s in enumerate(SECTORS):
        v = -bal["median"].get(s, float("nan"))          # aus Sicht von B: + = gewonnen
        chips.append(fig.text(0.2 + 0.3 * i, 0.265, f"{s.replace('Sector', 'S')}  {fmt_signed(v)}",
                              ha="center", va="center", fontsize=17, fontweight="bold",
                              color=GAIN if v > 0 else LOSS))
    sector_end = [s / gol["length_m"] for s in gol["sectors_m"]] + [1.0]

    # ── Bilanz ───────────────────────────────────────────────────────────────
    ax_bar = fig.add_axes(CHART_BOX)
    ax_bar.set_facecolor(COLORS["bg"])
    for side in ("top", "right", "left"):
        ax_bar.spines[side].set_visible(False)
    ax_bar.spines["bottom"].set_visible(False)
    ax_bar.tick_params(colors=COLORS["muted"], labelsize=10, left=False, labelleft=False, length=0)
    lap_n = [n for n, _, _ in bal["per_lap"]]
    gains = np.array([g for _, g, _ in bal["per_lap"]])
    losses = np.array([l for _, _, l in bal["per_lap"]])
    top = max(gains.max(), losses.max()) * 1.2
    ax_bar.set_ylim(-top, top)
    ax_bar.set_xlim(-0.7, len(lap_n) - 0.3)
    ax_bar.set_xticks(range(len(lap_n)), [str(n) for n in lap_n])
    ax_bar.axhline(0, color=COLORS["muted"], linewidth=1)
    bars_up = ax_bar.bar(range(len(lap_n)), np.zeros(len(lap_n)), width=0.62, color=GAIN)
    bars_dn = ax_bar.bar(range(len(lap_n)), np.zeros(len(lap_n)), width=0.62, color=LOSS)
    ax_bar.text(-0.6, top * 0.92, f"{b} gains {gain_label}", color=GAIN, fontsize=11, fontweight="bold",
                va="top")
    ax_bar.text(-0.6, -top * 0.92, f"{b} loses {loss_label}", color=LOSS, fontsize=11, fontweight="bold",
                va="bottom")
    ax_bar.set_xlabel("Lap", color=COLORS["muted"], fontsize=11)
    sum_gain = fig.text(0.5, 0.405, "", ha="center", va="center", fontsize=34, fontweight="bold", color=GAIN)
    sum_loss = fig.text(0.5, 0.345, "", ha="center", va="center", fontsize=34, fontweight="bold", color=LOSS)
    sum_net = fig.text(0.5, 0.275, "", ha="center", va="center", fontsize=26, fontweight="bold",
                       color=COLORS["text"])

    # ── Antwort, Frage ───────────────────────────────────────────────────────
    ans_1, _, ans_2 = answer.partition(" – ")
    txt_c1 = fig.text(0.5, 0.60, "", ha="center", va="center", fontsize=30, fontweight="bold",
                      color=COLORS["text"], wrap=True)
    txt_c2 = fig.text(0.5, 0.53, "", ha="center", va="center", fontsize=30, fontweight="bold", color=LOSS,
                      wrap=True)
    txt_c3 = fig.text(0.5, 0.44, "", ha="center", va="center", fontsize=15, color=COLORS["muted"])

    fig.text(0.94, 0.965, "STINTLAB", ha="right", va="center", fontsize=11, fontweight="bold",
             color=COLORS["accent"], path_effects=[patheffects.withStroke(linewidth=3, foreground="black",
                                                                          alpha=0.6)])
    txt_src = fig.text(0.06, 0.965, "DATA · OPENF1", ha="left", va="center", fontsize=9, fontweight="bold",
                       color=COLORS["muted"])
    _stroke(txt_src)

    groups = {
        "open": [ax_3d, *open_txt],
        "map": [ax_map, txt_kicker, txt_big, txt_sub, *legend],
        "trade": [ax_bar, txt_kicker, txt_big, txt_sub, sum_gain, sum_loss, sum_net],
        "text": [txt_c1, txt_c2, txt_c3, txt_kicker],
    }
    everything = {art for arts in groups.values() for art in arts} | set(chips)

    def show(*names, extra=()) -> None:
        on = {art for n in names for art in groups[n]} | set(extra)
        for art in everything:
            art.set_visible(art in on)
        minimap.set_visible("open" in names)

    def draw_open(u: float) -> None:
        show("open")
        i = min(int(round(u * (len(prep["open_times"]) - 1))), len(prep["open_times"]) - 1)
        t = prep["open_times"][i]
        g = draw_scene(ax_3d, scene, t)
        minimap.update(t)
        if np.isfinite(g):
            open_hist.append(g)
        recent = open_hist[-9:]              # geglättet, sonst flackern die Hundertstel
        open_gap.set_text(f"{np.mean(recent):.2f} s" if recent else "")

    def draw_map(u: float) -> None:
        f = _ease(u)
        done = [s for s, end in zip(SECTORS, sector_end) if f >= end - 1e-6]
        show("map", extra=[chips[SECTORS.index(s)] for s in done])
        cols = seg_rgba.copy()
        cols[frac[:-1] > f, 3] = 0.0
        painted.set_color(cols)
        i = min(int(np.searchsorted(frac, f)), len(P) - 1)
        dot.set_offsets([P[i]])
        span = np.ptp(P[:, 0])
        dot_label.set_position((P[i, 0] + 0.06 * span, P[i, 1]))
        k = min(int(f * n_bins), n_bins - 1)
        txt_kicker.set_text(f"AVERAGE LAP · LAPS {lap_lo}–{lap_hi}")
        txt_big.set_text(f"{curve[k]:.2f} s")
        txt_big.set_color(cb)
        txt_big.set_fontsize(40)
        txt_sub.set_text(f"{b} behind {a} · at every point of the lap")

    def draw_trade(u: float, hold: bool) -> None:
        show("trade")
        grow = 1.0 if hold else u
        n = len(lap_n)
        for j in range(n):
            h = _ease(grow * n - j)            # Runde für Runde
            bars_up[j].set_height(gains[j] * h)
            bars_dn[j].set_height(-losses[j] * h)
        txt_kicker.set_text(f"LAPS {lap_lo}–{lap_hi} · EVERY LAP")
        txt_big.set_text("THE SAME TRADE")
        txt_big.set_color(COLORS["text"])
        txt_big.set_fontsize(34)
        txt_sub.set_text(f"{b} vs {a}, official sector times")
        sum_gain.set_text(f"+{bal['gain']:.2f} s  {gain_label}" if grow > 0.35 else "")
        sum_loss.set_text(f"−{bal['loss']:.2f} s  {loss_label}" if grow > 0.65 else "")
        sum_net.set_text(f"Net: {fmt_net(bal['net'])} per lap" if hold else "")

    def draw_text(phase: str) -> None:
        show("text")
        txt_kicker.set_text("THE ANSWER" if phase == "answer" else "YOUR TURN")
        if phase == "answer":
            txt_c1.set_text(ans_1)
            txt_c2.set_text(ans_2)
            txt_c2.set_color(LOSS)
            txt_c3.set_text(f"Closest after the straight: {prep['closest']:.2f} s – never alongside")
        else:
            txt_c1.set_text(question)
            txt_c2.set_text("Tell us in the comments")
            txt_c2.set_color(COLORS["accent"])
            txt_c3.set_text("")
        txt_c1.set_fontsize(30 if len(txt_c1.get_text()) < 32 else 25)
        txt_c2.set_fontsize(30 if phase == "answer" and len(ans_2) < 32 else 22)

    def draw(phase: str, u: float) -> None:
        if phase == "open":
            draw_open(u)
        elif phase in ("map", "map_hold"):
            draw_map(1.0 if phase == "map_hold" else u)
        elif phase in ("trade", "trade_hold"):
            draw_trade(u, phase == "trade_hold")
        else:
            draw_text(phase)

    matplotlib.rcParams["animation.ffmpeg_path"] = _ffmpeg()
    writer = animation.FFMpegWriter(fps=FPS, codec="libx264", extra_args=["-pix_fmt", "yuv420p", "-crf", "20"])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = timeline()
    step = max(len(frames) // 10, 1)
    static = {"map_hold", "trade_hold", "answer", "ask"}
    with writer.saving(fig, str(path), dpi=DPI):
        last = None
        for i, (phase, u) in enumerate(frames):
            key = phase if phase in static else (phase, round(u, 5))
            if key != last:
                draw(phase, u)
                last = key
            writer.grab_frame(facecolor=COLORS["bg"])
            if i % step == 0:
                print(f"  {100 * i // len(frames):3d} %  ({i}/{len(frames)} Bilder)", flush=True)
    plt.close(fig)
    return path
