"""„Chase 3D“: Verfolgerkamera hinter B, beide Autos und die Strecke in Perspektive.

Wird als Anfang der Reels benutzt: Im Feed entscheidet die erste Sekunde (Baku:
~50 % weggewischt, solange das erste Bild ein schwarzer Titel war). Ab Bild 1
Bewegung, zwei erkennbare Autos in Teamfarben und der Abstand als Band.

Gezeichnet wird mit matplotlib (keine 3D-Engine): Punkte werden mit einer
einfachen Lochkamera projiziert, Flächen von hinten nach vorne gemalt.

Welt in Metern: x, y aus /location (÷ Maßstab), z = Höhe aus /location, leicht überhöht.
Kamera: BACK m hinter B, HEIGHT m darüber, Blick auf die Mitte zwischen A und B + AHEAD m.
Blickrichtung aus B's Bewegung der letzten CAM_SMOOTH_S Sekunden → ruhige Kamera.
"""
from __future__ import annotations

import numpy as np
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.colors import to_rgb

from stintlab import openf1
from stintlab.session import _parse
from stintlab.reels.race_story import Track, live_gap, reference_lap, units_per_metre
from stintlab.style import COLORS, team_color

BACK, HEIGHT, AHEAD, FOC = 40.0, 22.0, 25.0, 1.7
TRACK_W, Z_EXAG, CAR = 13.0, 1.5, 1.6
CAM_SMOOTH_S = 1.0
VIEW_M = 1400.0          # weiter entfernte Strecke nicht zeichnen
GRID_M, GRID_HALF = 50.0, 900.0

OUTLINE = [(2.95, 0.10), (2.5, 0.16), (1.9, 0.22), (1.2, 0.28), (0.75, 0.42), (0.55, 0.78), (-0.2, 0.80),
           (-0.9, 0.62), (-1.5, 0.40), (-2.1, 0.28), (-2.35, 0.24)]


class Scene:
    def __init__(self, data: dict, a: str, b: str, t0s: dict | None = None, ref: str | None = None):
        """t0s: Nullpunkt der Zeit je Fahrer. Standard (Rennen): für beide der
        Start des Rennens – beide Autos zur selben Uhrzeit. Ghost Lap: der Beginn
        der jeweils eigenen Runde – beide Autos zur selben verstrichenen Rundenzeit.
        ref: Fahrer für Maßstab und Streckenumriss (Standard a). Beim Comeback-Reel
        ist das der Verfolger – seine Telemetrie liegt sicher im Cache."""
        self.a, self.b = a, b
        ends = data["lap_ends"]
        self.t0 = ends[a][min(ends[a])] if t0s is None else t0s[a]
        self.t0s = t0s or {a: self.t0, b: self.t0}
        loc = {d: data.get("location", {}).get(d) or
               openf1.cached_fetch_driver("location", data["session_key"], data["numbers"][d]) for d in (a, b)}
        self.ta = Track(loc[a], self.t0s[a], rotate=False)
        self.tb = Track(loc[b], self.t0s[b], rotate=False)
        rd = ref or a
        lap = reference_lap(data, rd)
        self.scale = units_per_metre(data, rd, lap, self.ta if rd == a else self.tb, self.t0s[rd])
        self.z = {d: self._zfun(loc[d], self.t0s[d]) for d in (a, b)}
        rs = (lap["LapStart"] - self.t0s[rd]).total_seconds()
        tt = np.linspace(rs, rs + float(lap["LapTime"]), 3000)
        P = self.world(rd, tt)
        self.z_off = P[:, 2].min()
        P[:, 2] -= self.z_off
        P[:, 2] = np.convolve(np.pad(P[:, 2], 30, mode="wrap"), np.ones(61) / 61, mode="same")[30:-30]
        T = np.gradient(P[:, :2], axis=0)
        T /= np.linalg.norm(T, axis=1, keepdims=True)
        N = np.column_stack([-T[:, 1], T[:, 0]])
        self.P = P
        self.L = np.column_stack([P[:, :2] + N * TRACK_W / 2, P[:, 2]])
        self.R = np.column_stack([P[:, :2] - N * TRACK_W / 2, P[:, 2]])
        teams = data.get("teams", {})
        self.col = {d: team_color(teams.get(d)) for d in (a, b)}
        if self.col[a] == self.col[b]:
            self.col[b] = COLORS["text"]

    def _zfun(self, location, t0):
        """Höhe über die Zeit; ohne z-Werte (z. B. Testdaten) flach."""
        pts = sorted(((_parse(p["date"]) - t0).total_seconds(), float(p["z"]))
                     for p in location if p.get("z") is not None and p.get("date"))
        if len(pts) < 2:
            return lambda t: np.zeros(len(np.atleast_1d(t)))
        arr = np.array(pts)
        return lambda t: np.interp(np.atleast_1d(t), arr[:, 0], arr[:, 1])

    def world(self, d, t):
        tr = self.ta if d == self.a else self.tb
        x, y = tr.at(t)
        return np.column_stack([x / self.scale, y / self.scale, self.z[d](t) / self.scale * Z_EXAG])

    def pos(self, d, t):
        p = self.world(d, [t - 0.15, t, t + 0.15])
        p[:, 2] -= getattr(self, "z_off", 0.0)
        fw = p[2] - p[0]
        fw[2] = 0
        return p[1], fw / (np.linalg.norm(fw) or 1.0)

    def gap(self, t):
        return live_gap(self.ta, self.tb, t, 3.0, 40.0 * self.scale)


class Camera:
    def __init__(self, scene: Scene, t: float):
        pb, _ = scene.pos(scene.b, t)
        pa, _ = scene.pos(scene.a, t)
        hist = scene.world(scene.b, np.linspace(t - CAM_SMOOTH_S, t, 12))
        fwd = hist[-1] - hist[0]
        fwd[2] = 0
        fwd /= np.linalg.norm(fwd) or 1.0
        self.C = pb - fwd * BACK + np.array([0, 0, HEIGHT])
        target = 0.5 * (pa + pb) + fwd * AHEAD
        f = target - self.C
        self.f = f / np.linalg.norm(f)
        r = np.cross(self.f, [0, 0, 1])
        self.r = r / np.linalg.norm(r)
        self.u = np.cross(self.r, self.f)

    def proj(self, Q):
        v = np.atleast_2d(Q) - self.C
        zc = v @ self.f
        return FOC * (v @ self.r) / zc, FOC * (v @ self.u) / zc, zc


def _ring(pos, fw, side, pts, zz):
    loop = list(pts) + [(x, -w) for x, w in reversed(pts)]
    return np.array([pos + fw * x * CAR + side * w * CAR + np.array([0, 0, zz * CAR]) for x, w in loop])


def _rect(pos, fw, side, x0, x1, w0, w1, zz):
    return np.array([pos + fw * x * CAR + side * w * CAR + np.array([0, 0, zz * CAR])
                     for x, w in ((x0, w0), (x1, w0), (x1, w1), (x0, w1))])


def draw_car(ax, cam: Camera, pos, fw, col, name, z):
    side = np.array([-fw[1], fw[0], 0])
    rgb = np.array(to_rgb(col))
    dark = np.clip(rgb * 0.45, 0, 1)
    black = (0.07, 0.07, 0.08)
    sh = _ring(pos, fw, side, [(3.0, 0.5), (1.8, 0.95), (-1.9, 0.95), (-2.6, 0.6)], 0.0)
    sx, sy, sz = cam.proj(sh)
    if np.any(sz < 1):
        return
    ax.fill(sx, sy, color="black", alpha=0.3, zorder=z, linewidth=0)
    items = []

    def add(poly, c, bias=0.0):
        items.append((cam.proj(poly)[2].mean() + bias, poly, c))
    for x0 in (1.45, -2.15):
        for sgn in (-1, 1):
            add(_rect(pos, fw, side, x0, x0 + 0.72, sgn * 0.62, sgn * 1.0, 0.62), black)
            add(np.array([pos + fw * x * CAR + side * sgn * CAR + np.array([0, 0, zz * CAR])
                          for x, zz in ((x0, 0.0), (x0 + 0.72, 0.0), (x0 + 0.72, 0.62), (x0, 0.62))]),
                (0.12, 0.12, 0.13))
    lo, hi = _ring(pos, fw, side, OUTLINE, 0.12), _ring(pos, fw, side, OUTLINE, 0.45)
    for i in range(len(lo)):
        j = (i + 1) % len(lo)
        add(np.array([lo[i], lo[j], hi[j], hi[i]]), dark)
    body = cam.proj(hi)[2].mean()
    add(_rect(pos, fw, side, 2.6, 2.95, -0.95, 0.95, 0.12), dark, 0.3)
    wing = np.clip(rgb * 0.75, 0, 1)
    add(_rect(pos, fw, side, -2.72, -2.5, -0.58, 0.58, 0.98), wing, -0.3)       # Heckflügel, schmal
    for sgn in (-1, 1):                                                           # Endplatten
        add(np.array([pos + fw * x * CAR + side * sgn * 0.58 * CAR + np.array([0, 0, zz * CAR])
                      for x, zz in ((-2.75, 0.45), (-2.45, 0.45), (-2.45, 0.98), (-2.75, 0.98))]), dark, -0.2)
    items.append((body, hi, rgb))
    items.append((body - 0.01, _ring(pos, fw, side, [(0.9, 0.12), (0.5, 0.2), (-0.2, 0.2), (-0.35, 0.12)], 0.47), black))
    items.append((body - 0.02, _ring(pos, fw, side, [(2.8, 0.03), (1.0, 0.06)], 0.47), (1, 1, 1)))
    for _, poly, c in sorted(items, key=lambda it: -it[0]):
        px, py, pz = cam.proj(poly)
        if np.any(pz < 1):
            continue
        ax.fill(px, py, color=c, zorder=z + 0.5, linewidth=0.4, edgecolor=np.clip(np.array(to_rgb(c)) * 0.6, 0, 1))
    cx, cy, _ = cam.proj(pos + [0, 0, 0.5 * CAR])
    lx, ly = cx[0] + 0.13, cy[0] + 0.02
    ax.plot([cx[0], lx - 0.01], [cy[0], ly], color=col, linewidth=1.2, zorder=z + 1)
    r, g, b = to_rgb(col)
    label_ink = "black" if 0.299 * r + 0.587 * g + 0.114 * b > 0.6 else "white"   # weißes Auto → schwarze Schrift
    ax.text(lx, ly, name, fontsize=13, fontweight="bold", color=label_ink, ha="left", va="center", zorder=z + 1,
            bbox={"boxstyle": "round,pad=0.28", "facecolor": col, "edgecolor": "none"})


def draw_scene(ax, scene: Scene, t: float) -> float:
    """Zeichnet ein Bild zur Zeit t (Sekunden ab t0). Gibt den laufenden Abstand zurück."""
    ax.clear()
    ax.set_facecolor(COLORS["bg"])
    ax.axis("off")
    ax.set_xlim(-0.5625, 0.5625)
    ax.set_ylim(-1.0, 1.0)
    cam = Camera(scene, t)
    pa, fa = scene.pos(scene.a, t)
    pb, fb = scene.pos(scene.b, t)

    # Bodenraster, am Weltraster ausgerichtet → läuft beim Fahren mit
    g0 = np.round(pb[:2] / GRID_M) * GRID_M
    ks = np.arange(-GRID_HALF, GRID_HALF + 1, GRID_M)
    lines = []
    for k in ks:
        for line in (np.column_stack([np.full(40, g0[0] + k), g0[1] + np.linspace(-GRID_HALF, GRID_HALF, 40), np.zeros(40)]),
                     np.column_stack([g0[0] + np.linspace(-GRID_HALF, GRID_HALF, 40), np.full(40, g0[1] + k), np.zeros(40)])):
            x, y, z = cam.proj(line)
            m = z > 5
            if m.sum() > 1:
                lines.append(np.column_stack([x[m], y[m]]))
    ax.add_collection(LineCollection(lines, colors=COLORS["grid"], linewidths=0.6, alpha=0.7, zorder=0))

    # Strecke: nur der Teil vor der Kamera und in Sichtweite
    xl, yl, zl = cam.proj(scene.L)
    xr, yr, zr = cam.proj(scene.R)
    ok = (np.minimum(zl, zr) > 3) & (np.minimum(zl, zr) < VIEW_M)
    idx = np.where(ok[:-1] & ok[1:])[0]
    quads = np.stack([np.column_stack([xl[idx], yl[idx]]), np.column_stack([xl[idx + 1], yl[idx + 1]]),
                      np.column_stack([xr[idx + 1], yr[idx + 1]]), np.column_stack([xr[idx], yr[idx]])], axis=1)
    order = np.argsort(-zl[idx])
    shade = np.clip(1 - zl[idx][order] / 1800, 0.3, 1)[:, None]
    face = np.column_stack([0.16 * shade + 0.03, 0.16 * shade + 0.03, 0.19 * shade + 0.04, np.ones_like(shade)])
    ax.add_collection(PolyCollection(quads[order], facecolors=face, edgecolors=face, linewidths=0.3, zorder=2))
    for ex, ey in ((xl, yl), (xr, yr)):
        ax.plot(np.where(ok, ex, np.nan), np.where(ok, ey, np.nan), color="#6b6b78", linewidth=0.8, zorder=3)

    # Abstand als Band: B's Weg der nächsten `gap` Sekunden endet genau dort, wo A jetzt ist
    g = scene.gap(t)
    if np.isfinite(g) and g > 0.02:
        band = scene.world(scene.b, np.linspace(t, t + g, 30))
        band[:, 2] -= scene.z_off - 0.05
        bx, by, bz = cam.proj(band)
        m = bz > 2
        ax.plot(bx[m], by[m], color=COLORS["accent"], linewidth=5, alpha=0.85, zorder=4, solid_capstyle="round")

    # Wer näher an der Kamera ist, wird zuletzt gezeichnet
    cars = sorted(((cam.proj(pa)[2][0], pa, fa, scene.a), (cam.proj(pb)[2][0], pb, fb, scene.b)), key=lambda c: -c[0])
    for i, (_, p, fw, d) in enumerate(cars):
        draw_car(ax, cam, p, fw, scene.col[d], d, 7 + 2 * i)
    return g


class MiniMap:
    """Kontext für den 3D-Anfang: kleine Streckenkarte oben links mit Ziellinie,
    beiden Autos und einer Zeile „KM 1.2 / 5.8 · SECTOR 1“. Ohne sie weiß im
    Feed niemand, wo auf der Runde die Szene spielt."""

    def __init__(self, fig, scene: Scene, box=(0.05, 0.60, 0.26, 0.19), sector_fracs: list[float] | None = None):
        self.scene = scene
        self.ax = fig.add_axes(list(box))
        self.ax.set_aspect("equal")
        self.ax.axis("off")
        P = scene.P
        self.ax.plot(P[:, 0], P[:, 1], color=COLORS["grid"], linewidth=5, solid_capstyle="round", zorder=1)
        self.ax.plot(P[:, 0], P[:, 1], color="#3a3a44", linewidth=2.5, solid_capstyle="round", zorder=2)
        self.ax.scatter([P[0, 0]], [P[0, 1]], s=26, marker="s", color="white", zorder=3)
        self.dots = {d: self.ax.scatter([], [], s=42, color=scene.col[d], edgecolor="white", linewidth=1.0, zorder=5)
                     for d in (scene.a, scene.b)}
        self.cum = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(P[:, 0]), np.diff(P[:, 1])))])
        self.sector_fracs = sector_fracs or []
        self.label = fig.text(box[0] + box[2] / 2, box[1] - 0.012, "", ha="center", va="top", fontsize=10,
                              fontweight="bold", color=COLORS["muted"])

    def lap_position(self, point) -> float:
        """Anteil der Runde (0–1) am nächstgelegenen Punkt der Referenzrunde."""
        i = int(np.argmin(np.hypot(self.scene.P[:, 0] - point[0], self.scene.P[:, 1] - point[1])))
        return float(self.cum[i] / self.cum[-1])

    def update(self, t: float) -> None:
        for d, dot in self.dots.items():
            p, _ = self.scene.pos(d, t)
            dot.set_offsets([[p[0], p[1]]])
        pa, _ = self.scene.pos(self.scene.a, t)
        f = self.lap_position(pa)
        sector = 1 + sum(f >= s for s in self.sector_fracs) if self.sector_fracs else None
        text = f"KM {f * self.cum[-1] / 1000:.1f} / {self.cum[-1] / 1000:.1f}"
        self.label.set_text(text + (f"  ·  SECTOR {sector}" if sector else ""))

    def set_visible(self, on: bool) -> None:
        self.ax.set_visible(on)
        self.label.set_visible(on)
