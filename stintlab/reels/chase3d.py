"""„Chase 3D“: Verfolgerkamera hinter B, beide Autos und die Strecke in Perspektive.

Wird als Anfang der Reels benutzt: Im Feed entscheidet die erste Sekunde (Baku:
~50 % weggewischt, solange das erste Bild ein schwarzer Titel war). Ab Bild 1
Bewegung, zwei erkennbare Autos in Teamfarben und der Abstand als Band.

Gezeichnet wird mit matplotlib (keine 3D-Engine): Punkte werden mit einer
einfachen Lochkamera projiziert, Flächen von hinten nach vorne gemalt.

Welt in Metern: x, y aus /location (÷ Maßstab), z = Höhe aus /location, leicht überhöht.
Kamera: BACK m hinter B, HEIGHT m darüber, Blick auf die Mitte zwischen A und B + AHEAD m.
Blickrichtung aus B's Bewegung der letzten CAM_SMOOTH_S Sekunden → ruhige Kamera.

TAGESZEIT (light = "day" | "dusk" | "night", siehe LIGHTS): aus Startzeit der Session
+ Zeitzone der Strecke (vor 18 Uhr Ortszeit Tag, bis 19:30 Dämmerung, danach Nacht).
Baku-Qualifying 17 Uhr → Tag; Singapur, Las Vegas → Nacht. In der post.toml mit
light = "..." überschreibbar, ebenso scenery = "city" | "park".

UMGEBUNG (Environment): Gras neben der Strecke, rot-weiße Randsteine in Kurven,
Leitplanken, Bäume und ein Horizont. Auf Stadtkursen (scenery = "city", erkannt am
Streckennamen, siehe STREET_CIRCUITS) stattdessen Häuserblöcke mit einzelnen
beleuchteten Fenstern, Mauern direkt an der Strecke und Gehweg statt Gras. Alles aus der Referenzrunde abgeleitet und
bewusst dunkel gehalten – die Autos und die weiße Schrift bleiben das Hellste
im Bild. Die Bäume sind erfunden (Zufall mit festem Startwert), nicht die echten.

ÜBERHOLEN NEBENEINANDER (Scene.set_pass): Die OpenF1-Positionen liegen auf einer
einzigen Linie – Monza 2026, ANT und RUS: über 2 Minuten im Mittel 9 cm
auseinander, beim Überholen max. 8 cm. Wer innen oder außen war, steht NICHT in
den Daten. Ohne Korrektur fahren die Autos ineinander. set_pass schiebt beide
seitlich auseinander, solange sie sich überlappen würden; die Seite muss man
vorgeben (TV-Bilder) oder schätzen (Innenseite der nächsten Kurve).
"""
from __future__ import annotations

import numpy as np
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.colors import to_rgb
from matplotlib.patches import Rectangle as plt_Rectangle

from stintlab import openf1
from stintlab.session import _parse
from stintlab.reels.race_story import Track, live_gap, reference_lap, units_per_metre
from stintlab.style import COLORS, team_color

BACK, HEIGHT, AHEAD, FOC = 40.0, 22.0, 25.0, 1.7
TRACK_W, Z_EXAG, CAR = 13.0, 1.5, 1.5
CAM_SMOOTH_S = 1.0
VIEW_M = 1400.0          # weiter entfernte Strecke nicht zeichnen
GRID_M, GRID_HALF = 50.0, 900.0
FOG_M = 1800.0

# Umgebung (Meter)
GRASS_W = 45.0
KERB_W, KERB_LEN, KERB_RADIUS = 1.5, 4.0, 180.0
BARRIER_OFF, BARRIER_H = 16.0, 1.1       # Abstand vom Streckenrand, Höhe
TREE_N, TREE_MIN, TREE_MAX = 900, 30.0, 140.0
ENV_STEP = 2                             # jeden 2. Punkt der Referenzrunde (≈ 4 m)
GRASS_RGB = np.array([0.055, 0.105, 0.065])
BARRIER_RGB = np.array([0.42, 0.43, 0.47])
SKY_HORIZON, SKY_TOP = "#1a2233", COLORS["bg"]

# Stadtkurse
STREET_CIRCUITS = ("baku", "monaco", "monte carlo", "singapore", "marina bay", "jeddah", "las vegas",
                   "madring", "madrid")
CITY_WALL_OFF, CITY_WALL_H = 2.5, 1.3
PAVEMENT_RGB = np.array([0.075, 0.075, 0.085])
WALL_RGB = np.array([0.5, 0.5, 0.52])
FACADES = np.array([[0.36, 0.31, 0.24], [0.30, 0.30, 0.32], [0.40, 0.38, 0.34], [0.32, 0.22, 0.17],
                    [0.26, 0.28, 0.30]]) * 0.75
WINDOW_RGB = np.array([0.95, 0.78, 0.45])
WINDOW_MAX = 0.35        # so viele Fenster werden angelegt; wie viele leuchten, sagt LIGHTS[..]["windows"]

_BG = tuple(to_rgb(COLORS["bg"]))
LIGHTS = {
    "day": {"sky_top": "#3f78b5", "sky_hor": "#c9d7e3", "fog": (0.70, 0.76, 0.81),
            "far_park": (0.19, 0.26, 0.15), "far_city": (0.33, 0.33, 0.34),
            "grass": (0.17, 0.32, 0.12), "pavement": (0.40, 0.40, 0.41), "asphalt": (0.27, 0.27, 0.29),
            "barrier": (0.72, 0.72, 0.75), "wall": (0.80, 0.79, 0.76), "facade": 2.1, "windows": 0.0,
            "trees": 2.2, "grid": 0.0, "edge": "#ececf0"},
    "dusk": {"sky_top": COLORS["bg"], "sky_hor": "#1a2233", "fog": _BG, "far_park": _BG, "far_city": _BG,
             "grass": (0.055, 0.105, 0.065), "pavement": (0.075, 0.075, 0.085), "asphalt": (0.19, 0.19, 0.23),
             "barrier": (0.42, 0.43, 0.47), "wall": (0.5, 0.5, 0.52), "facade": 1.0, "windows": 0.18,
             "trees": 1.0, "grid": 0.5, "edge": "#8a8a96"},
    "night": {"sky_top": "#030405", "sky_hor": "#0f1420", "fog": (0.03, 0.03, 0.04), "far_park": _BG,
              "far_city": _BG, "grass": (0.035, 0.07, 0.04), "pavement": (0.055, 0.055, 0.06),
              "asphalt": (0.17, 0.17, 0.2), "barrier": (0.38, 0.39, 0.42), "wall": (0.44, 0.44, 0.46),
              "facade": 0.65, "windows": 0.35, "trees": 0.8, "grid": 0.35, "edge": "#9a9aa6"},
    # Regen (rain = true in der post.toml): bedeckter Tag, dunkler nasser Asphalt, dichter Dunst
    "rain": {"sky_top": "#4b545e", "sky_hor": "#8d969e", "fog": (0.52, 0.56, 0.60),
             "far_park": (0.16, 0.20, 0.15), "far_city": (0.30, 0.30, 0.31),
             "grass": (0.13, 0.24, 0.11), "pavement": (0.30, 0.30, 0.31), "asphalt": (0.16, 0.16, 0.18),
             "barrier": (0.60, 0.60, 0.63), "wall": (0.65, 0.65, 0.64), "facade": 1.6, "windows": 0.05,
             "trees": 1.7, "grid": 0.0, "edge": "#d4d4da"},
}
_FOG = np.array(_BG)     # Dunstfarbe des aktuellen Bildes (draw_scene setzt sie)
RAIN_STREAKS, RAIN_FALL = 170, 1.6       # Anzahl Striche, Fallgeschwindigkeit (Bildhöhen pro Sekunde)
SPRAY_M, SPRAY_POINTS = 14.0, 260        # Gischt hinter jedem Auto: Länge, Punkte
FLOOR_M, WIN_EVERY_M = 3.5, 3.2


def meeting_for(session_key) -> dict | None:
    """Wochenende zur Session: meetings/<key>_sessions.json → meetings/<Jahr>.json
    (die Session-Listen selbst enthalten weder Ort noch Zeitzone)."""
    import json
    folder = openf1.CACHE_DIR / "meetings"
    meeting_key = None
    for f in folder.glob("*_sessions.json"):
        try:
            if any(sess.get("session_key") == session_key for sess in json.loads(f.read_text(encoding="utf-8"))):
                meeting_key = int(f.name.split("_")[0])
                break
        except (OSError, ValueError):
            continue
    if meeting_key is None:
        return None
    for f in folder.glob("[0-9][0-9][0-9][0-9].json"):
        try:
            for m in json.loads(f.read_text(encoding="utf-8")):
                if m.get("meeting_key") == meeting_key:
                    return m
        except (OSError, ValueError):
            continue
    return None


def scenery_for(session_key) -> str:
    """ "city" für Stadtkurse, sonst "park"."""
    m = meeting_for(session_key)
    if not m:
        return "park"
    name = " ".join(str(m.get(k) or "") for k in ("location", "circuit_short_name", "meeting_name"))
    return "city" if any(w in name.lower() for w in STREET_CIRCUITS) else "park"


def light_for(session_key, when) -> str:
    """Tageszeit aus Ortszeit der Session: vor 18 Uhr Tag, bis 19:30 Dämmerung, sonst Nacht.
    Baku 2026 Q3 um 17:02 ist heller Tag (Sonnenuntergang ~19 Uhr) – 17 Uhr als Grenze war zu früh."""
    from datetime import timedelta
    m = meeting_for(session_key)
    off = (m or {}).get("gmt_offset")
    if not off or when is None:
        return "day"
    sign = -1 if str(off).startswith("-") else 1
    h, mi, *_ = (int(x) for x in str(off).lstrip("+-").split(":"))
    local = when + sign * timedelta(hours=h, minutes=mi)
    hour = local.hour + local.minute / 60
    return "day" if 6 <= hour < 18 else ("dusk" if 18 <= hour < 19.5 else "night")

# Überholen nebeneinander
PASS_WINDOW_S = 6.0
CAR_LEN_M = 6.1 * CAR                    # Länge des Modells (Frontflügel bis Heckflügel)
CAR_WID_M = 2.0 * CAR
SEP_FULL_X = CAR_LEN_M * 1.05            # ab hier ganz nebeneinander
SEP_OUT_X = SEP_FULL_X + 12.0            # ab hier beginnt das Ausscheren
SEP_M = CAR_WID_M * 1.25
ATTACKER_SHARE = 0.7                     # der Angreifer schert weiter aus als der Verteidiger

LIGHT = np.array([0.35, -0.45, 0.82]) / np.linalg.norm([0.35, -0.45, 0.82])


def _smoothstep(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


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
        N = np.column_stack([-T[:, 1], T[:, 0]])          # zeigt nach links
        self.P, self.T, self.N = P, T, N
        # Ränder als geschlossene Schleife (erster Punkt am Ende wiederholt) – sonst fehlt an
        # der Ziellinie ein Stück Asphalt (Monza 2026: 4,5 m Lücke → dunkler Balken quer im Bild)
        self.L = np.column_stack([P[:, :2] + N * TRACK_W / 2, P[:, 2]])
        self.R = np.column_stack([P[:, :2] - N * TRACK_W / 2, P[:, 2]])
        self.L, self.R = np.vstack([self.L, self.L[:1]]), np.vstack([self.R, self.R[:1]])
        self.cum = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(P[:, 0]), np.diff(P[:, 1])))])
        teams = data.get("teams", {})
        self.col = {d: team_color(teams.get(d)) for d in (a, b)}
        if self.col[a] == self.col[b]:
            self.col[b] = COLORS["text"]
        self.pass_side: float | None = None
        self.pass_t: float | None = None
        self.ghost: str | None = None     # dieser Fahrer wird halbtransparent gezeichnet (Ghost Lap)
        self.scenery = scenery_for(data.get("session_key"))    # vor dem ersten Bild überschreibbar
        # Uhrzeit der Referenz-Session (beim Vorjahresvergleich die aktuelle, nicht das Vorjahr)
        self.light = light_for(data.get("session_key"), self.t0s.get(rd, self.t0))
        self.rain = False                 # Regenstriche + Gischt (configure: rain = true)
        self._env = None

    def configure(self, reel: dict) -> None:
        """scenery / light aus der post.toml übernehmen (vor dem ersten Bild)."""
        if reel.get("scenery") is not None:
            if reel["scenery"] not in ("city", "park"):
                raise ValueError('scenery muss "city" oder "park" sein')
            self.scenery = reel["scenery"]
        if reel.get("light") is not None:
            if reel["light"] not in LIGHTS:
                raise ValueError(f'light muss eins von {", ".join(LIGHTS)} sein')
            self.light = reel["light"]
        rain = reel.get("rain", False)
        if not isinstance(rain, bool):
            raise ValueError("rain muss true oder false sein (klein geschrieben, ohne Anführungszeichen)")
        self.rain = rain
        if rain and reel.get("light") is None:
            self.light = "rain"
        self._env = None

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

    def _pos_raw(self, d, t):
        p = self.world(d, [t - 0.15, t, t + 0.15])
        p[:, 2] -= getattr(self, "z_off", 0.0)
        fw = p[2] - p[0]
        fw[2] = 0
        return p[1], fw / (np.linalg.norm(fw) or 1.0)

    # ── Überholen nebeneinander ──────────────────────────────────────────────
    def set_pass(self, t_pass: float, side: float) -> None:
        """B überholt A um t_pass herum auf der Seite side (+1 links, −1 rechts,
        in Fahrtrichtung)."""
        self.pass_t, self.pass_side = float(t_pass), float(np.sign(side) or 1.0)

    def separation(self, t: float) -> float:
        """Seitlicher Abstand (m), um den die Autos gerade auseinandergeschoben sind."""
        if self.pass_side is None or abs(t - self.pass_t) >= PASS_WINDOW_S:
            return 0.0
        pa, fa = self._pos_raw(self.a, t)
        pb, _ = self._pos_raw(self.b, t)
        along = abs(float((pb - pa) @ fa))
        ramp = _smoothstep((SEP_OUT_X - along) / (SEP_OUT_X - SEP_FULL_X))
        window = _smoothstep((PASS_WINDOW_S - abs(t - self.pass_t)) / 2.0)
        return float(SEP_M * ramp * window)

    def pos(self, d, t):
        p, fw = self._pos_raw(d, t)
        sep = self.separation(t)
        if sep:
            left = np.array([-fw[1], fw[0], 0.0])
            share = ATTACKER_SHARE if d == self.b else -(1 - ATTACKER_SHARE)
            p = p + left * self.pass_side * share * sep
        return p, fw

    def corner_side(self, t: float, ahead_m: tuple[float, float] = (60.0, 350.0)) -> float:
        """+1, wenn die nächste Kurve (ahead_m vor B) links herum geht, sonst −1."""
        pb, _ = self._pos_raw(self.b, t)
        i = int(np.argmin(np.hypot(self.P[:, 0] - pb[0], self.P[:, 1] - pb[1])))
        s = (self.cum - self.cum[i]) % self.cum[-1]
        m = (s >= ahead_m[0]) & (s <= ahead_m[1])
        ang = np.unwrap(np.arctan2(self.T[:, 1], self.T[:, 0]))
        turn = np.diff(ang)[m[:-1]] if m[:-1].any() else np.array([0.0])
        return 1.0 if turn.sum() >= 0 else -1.0

    def gap(self, t):
        return live_gap(self.ta, self.tb, t, 3.0, 40.0 * self.scale)

    def environment(self) -> "Environment":
        if self._env is None:
            self._env = Environment(self)
        return self._env


class Camera:
    def __init__(self, scene: Scene, t: float):
        pb, _ = scene.pos(scene.b, t)
        pa, _ = scene.pos(scene.a, t)
        hist = scene.world(scene.b, np.linspace(t - CAM_SMOOTH_S, t, 12))
        fwd = hist[-1] - hist[0]
        fwd[2] = 0
        fwd /= np.linalg.norm(fwd) or 1.0
        self.C = pb - fwd * BACK + np.array([0, 0, HEIGHT])
        # Liegt A HINTER B (z. B. an der Ziellinie, der Zweite 300 m zurück), würde die
        # Mitte zwischen beiden hinter der Kamera liegen → dann weich nur auf B schauen.
        # Bei A == B sind beide Ziele gleich, der Übergang ist also stetig.
        behind = max(0.0, -float((pa - pb) @ fwd))
        w = float(_smoothstep(behind / 40.0))
        target = (1 - w) * (0.5 * (pa + pb) + fwd * AHEAD) + w * (pb + fwd * AHEAD)
        f = target - self.C
        self.f = f / np.linalg.norm(f)
        r = np.cross(self.f, [0, 0, 1])
        self.r = r / np.linalg.norm(r)
        self.u = np.cross(self.r, self.f)
        self.fwd = fwd

    def proj(self, Q):
        v = np.atleast_2d(Q) - self.C
        zc = v @ self.f
        return FOC * (v @ self.r) / zc, FOC * (v @ self.u) / zc, zc

    def horizon_y(self) -> float:
        """Bildhöhe des Horizonts (Punkt sehr weit voraus auf Kamerahöhe)."""
        d = self.fwd / (np.linalg.norm(self.fwd) or 1.0)
        return float(FOC * (d @ self.u) / (d @ self.f))


# ── Umgebung ─────────────────────────────────────────────────────────────────

def _fog(rgb: np.ndarray, depth: np.ndarray) -> np.ndarray:
    k = np.clip(1 - depth / FOG_M, 0.3, 1.0)[:, None]
    return rgb * k + _FOG * (1 - k)


class Environment:
    """Einmal berechnete Welt um die Strecke; draw_*() zeichnet den sichtbaren Teil."""

    def __init__(self, scene: Scene):
        # geschlossene Schleife: erster Punkt am Ende noch einmal (siehe Scene.L)
        P = np.vstack([scene.P[::ENV_STEP], scene.P[:1]])
        N = np.vstack([scene.N[::ENV_STEP], scene.N[:1]])
        z = P[:, 2:3]
        half = TRACK_W / 2
        self.city = scene.scenery == "city"
        L = LIGHTS[scene.light]
        self.fog = np.array(to_rgb(L["fog"]))
        self.sky = (L["sky_top"], L["sky_hor"])
        self.far = to_rgb(L["far_city" if self.city else "far_park"])
        self.asphalt, self.edge, self.grid_alpha = np.array(L["asphalt"]), L["edge"], L["grid"]
        self.ground_rgb = np.array(L["pavement"] if self.city else L["grass"])
        self.barrier_rgb = np.array(L["wall"] if self.city else L["barrier"])
        self.facade_gain, self.window_lit, self.tree_gain = L["facade"], L["windows"], L["trees"]
        wall_off = CITY_WALL_OFF if self.city else BARRIER_OFF
        wall_h = CITY_WALL_H if self.city else BARRIER_H
        self.edges = {}
        for side in (1, -1):
            inner = np.column_stack([P[:, :2] + side * N * half, z])
            outer = np.column_stack([P[:, :2] + side * N * (half + GRASS_W), z - 0.05])
            self.edges[side] = (inner, outer)

        # Kurven: Krümmung aus der Richtungsänderung, geglättet
        ang = np.unwrap(np.arctan2(scene.T[:, 1], scene.T[:, 0]))
        ds = np.gradient(scene.cum)
        k = np.gradient(ang) / np.maximum(ds, 1e-6)
        k = np.convolve(np.pad(k, 10, mode="wrap"), np.ones(21) / 21, mode="same")[10:-10]
        k = np.append(k[::ENV_STEP], k[0])
        s = np.append(scene.cum[::ENV_STEP], scene.cum[-1])
        self.kerb = np.abs(k) > 1.0 / KERB_RADIUS
        self.kerb_red = (np.floor(s / KERB_LEN) % 2) == 0
        self.kerbs = {}
        for side in (1, -1):
            a = np.column_stack([P[:, :2] + side * N * half, z + 0.03])
            b = np.column_stack([P[:, :2] + side * N * (half + KERB_W), z + 0.03])
            self.kerbs[side] = (a, b)

        # Leitplanken – nicht dort, wo sie einen anderen Teil der Strecke kreuzen würden
        allp = scene.P[::4, :2]
        self.barriers = {}
        for side in (1, -1):
            base = P[:, :2] + side * N * (half + wall_off)
            near = np.array([np.min(np.hypot(allp[:, 0] - x, allp[:, 1] - y)) for x, y in base])
            ok = near > half + wall_off - 2.0
            lo = np.column_stack([base, z])
            hi = np.column_stack([base, z + wall_h])
            self.barriers[side] = (lo, hi, ok)

        self._build_city(scene) if self.city else None
        # Bäume: zufällig, aber immer gleich (fester Startwert), mit Abstand zur Strecke
        rng = np.random.default_rng(7)
        n = len(P)
        idx = rng.integers(0, n, TREE_N * 2)
        side = rng.choice([-1, 1], TREE_N * 2)
        off = half + rng.uniform(TREE_MIN, TREE_MAX, TREE_N * 2)
        cand = P[idx, :2] + (side * off)[:, None] * N[idx] + rng.normal(0, 6, (TREE_N * 2, 2))
        near = np.array([np.min(np.hypot(allp[:, 0] - x, allp[:, 1] - y)) for x, y in cand])
        keep = np.where(near > half + TREE_MIN - 4)[0][:0 if self.city else TREE_N]
        self.tree_base = np.column_stack([cand[keep], P[idx[keep], 2] - 0.05])
        self.tree_h = rng.uniform(9.0, 17.0, len(keep))
        g = rng.uniform(0.0, 1.0, len(keep))
        self.tree_rgb = np.clip(np.column_stack([0.05 + 0.04 * g, 0.12 + 0.07 * g, 0.07 + 0.03 * g]) * self.tree_gain, 0, 1)

        # Start/Ziel: Karomuster quer über die Strecke + Portal darüber
        p0, n0, t0 = scene.P[0], scene.N[0], scene.T[0]
        z0 = p0[2] + 0.04
        cols, rows = 12, 2
        self.finish, self.finish_rgb = [], []
        for r_ in range(rows):
            for c_ in range(cols):
                w0, w1 = -half + TRACK_W * c_ / cols, -half + TRACK_W * (c_ + 1) / cols
                x0, x1 = -1.0 + r_ * 1.0, r_ * 1.0
                self.finish.append([np.r_[p0[:2] + n0 * w + t0 * x, z0] for w, x in ((w0, x0), (w1, x0), (w1, x1), (w0, x1))])
                self.finish_rgb.append([0.9, 0.9, 0.92] if (r_ + c_) % 2 else [0.04, 0.04, 0.05])
        self.finish = np.array(self.finish)
        self.finish_rgb = np.array(self.finish_rgb)
        post, top, beam = 0.5, 7.5, 1.4
        g = []
        for sgn in (1, -1):
            w = sgn * (half + 1.2)
            g.append([np.r_[p0[:2] + n0 * (w - post) , p0[2]], np.r_[p0[:2] + n0 * (w + post), p0[2]],
                      np.r_[p0[:2] + n0 * (w + post), p0[2] + top], np.r_[p0[:2] + n0 * (w - post), p0[2] + top]])
        w = half + 1.2 + post
        g.append([np.r_[p0[:2] + n0 * w, p0[2] + top - beam], np.r_[p0[:2] - n0 * w, p0[2] + top - beam],
                  np.r_[p0[:2] - n0 * w, p0[2] + top], np.r_[p0[:2] + n0 * w, p0[2] + top]])
        self.gantry = np.array(g)

    def _build_city(self, scene: Scene) -> None:
        """Häuserblöcke in zwei Reihen entlang der Strecke – zufällig, aber immer gleich."""
        rng = np.random.default_rng(11)
        half = TRACK_W / 2
        allp = scene.P[::2, :2]
        spacing = scene.cum[-1] / len(scene.P)
        step = max(int(26.0 / spacing), 1)
        foot, z0s, hs, cols, centers, radii = [], [], [], [], [], []
        for side in (1, -1):
            for i in range(0, len(scene.P), step):
                for o0, o1, h0, h1 in ((9.0, 20.0, 10.0, 28.0), (36.0, 60.0, 18.0, 55.0)):
                    if rng.random() < 0.2:
                        continue
                    off, w, dp = half + rng.uniform(o0, o1), rng.uniform(16, 32), rng.uniform(12, 24)
                    p, t, n = scene.P[i], scene.T[i], scene.N[i] * side
                    c0 = p[:2] + n * off - t * w / 2
                    corners = np.array([c0, c0 + t * w, c0 + t * w + n * dp, c0 + n * dp])
                    probe = np.vstack([corners, corners.mean(0)])
                    d = np.sqrt(((probe[:, None, :] - allp[None, :, :]) ** 2).sum(-1)).min()
                    if d < half + 6.0:
                        continue
                    c, r = corners.mean(0), np.hypot(w, dp) / 2
                    if centers and (np.hypot(*(np.array(centers) - c).T) < (np.array(radii) + r) * 0.75).any():
                        continue
                    foot.append(corners)
                    z0s.append(p[2] - 0.1)
                    hs.append(rng.uniform(h0, h1))
                    cols.append(np.clip(FACADES[rng.integers(len(FACADES))] * rng.uniform(0.85, 1.1) * self.facade_gain, 0, 1))
                    centers.append(c)
                    radii.append(r)
        self.bld_foot = np.array(foot).reshape(-1, 4, 2)
        self.bld_z0, self.bld_h, self.bld_rgb = np.array(z0s), np.array(hs), np.array(cols).reshape(-1, 3)
        # beleuchtete Fenster: pro Haus und Fassade (Welt-Koordinaten), einmal ausgewürfelt
        self.bld_windows: list[list[tuple[int, np.ndarray]]] = []
        for b in range(len(self.bld_foot)):
            wins = []
            for f in range(4):
                a, c = self.bld_foot[b][f], self.bld_foot[b][(f + 1) % 4]
                length = float(np.hypot(*(c - a)))
                u = (c - a) / (length or 1.0)
                for fl in range(1, int(self.bld_h[b] / FLOOR_M)):
                    for k in range(int(length / WIN_EVERY_M)):
                        r = rng.random()
                        if r > WINDOW_MAX:
                            continue
                        x0 = a + u * (k * WIN_EVERY_M + 0.9)
                        x1 = x0 + u * 1.4
                        zb = self.bld_z0[b] + fl * FLOOR_M - 2.3
                        wins.append((f, np.array([np.r_[x0, zb], np.r_[x1, zb], np.r_[x1, zb + 1.5], np.r_[x0, zb + 1.5]]), r))
            self.bld_windows.append(wins)

    def draw_buildings(self, ax, cam: Camera) -> None:
        if not self.city or not len(self.bld_foot):
            return
        n = len(self.bld_foot)
        bot = np.concatenate([self.bld_foot, self.bld_z0[:, None, None].repeat(4, 1)], axis=2)
        top = bot.copy()
        top[:, :, 2] += self.bld_h[:, None]
        px, py, pz = cam.proj(np.concatenate([bot, top], axis=1).reshape(-1, 3))
        px, py, pz = (a.reshape(n, 8) for a in (px, py, pz))
        ok = (pz.min(1) > 3) & (pz.min(1) < VIEW_M) & (np.abs(px).min(1) < 1.2) & (py.min(1) < 1.2)
        polys, colors = [], []
        for b in np.where(ok)[0][np.argsort(-pz[ok].mean(1))]:
            depth = pz[b].mean()
            center = np.r_[self.bld_foot[b].mean(0), self.bld_z0[b] + self.bld_h[b] / 2]
            faces = []
            for f in range(4):
                i, j = f, (f + 1) % 4
                mid = (bot[b, i] + bot[b, j] + top[b, i] + top[b, j]) / 4
                normal = np.cross(bot[b, j] - bot[b, i], [0, 0, 1.0])
                normal /= np.linalg.norm(normal) or 1.0
                if normal @ (mid - center) < 0:
                    normal = -normal
                if normal @ (cam.C - mid) <= 0:
                    continue                                   # Rückseite
                shade = 0.55 + 0.45 * abs(float(normal @ LIGHT))
                faces.append(f)
                polys.append(np.column_stack([px[b, [i, j, 4 + j, 4 + i]], py[b, [i, j, 4 + j, 4 + i]]]))
                colors.append(_fog(self.bld_rgb[b][None] * shade, np.array([depth]))[0])
            polys.append(np.column_stack([px[b, 4:], py[b, 4:]]))           # Dach
            colors.append(_fog(self.bld_rgb[b][None] * 0.6, np.array([depth]))[0])
            wins = [q for f, q, r in self.bld_windows[b] if f in faces and r < self.window_lit]
            if wins:
                wx, wy, wz = cam.proj(np.concatenate(wins))
                for k in range(len(wins)):
                    polys.append(np.column_stack([wx[4 * k:4 * k + 4], wy[4 * k:4 * k + 4]]))
                    colors.append(_fog(WINDOW_RGB[None], np.array([depth]))[0])
        if polys:
            ax.add_collection(PolyCollection(polys, facecolors=colors, edgecolors=np.clip(np.array(colors) * 0.8, 0, 1),
                                             linewidths=0.3, zorder=4))

    @staticmethod
    def _strip(cam: Camera, a: np.ndarray, b: np.ndarray, mask: np.ndarray | None = None):
        """Vierecke zwischen zwei Linien a und b (je n Punkte) → (Polygone, Tiefe, Index)."""
        xa, ya, za = cam.proj(a)
        xb, yb, zb = cam.proj(b)
        ok = (np.minimum(za, zb) > 3) & (np.minimum(za, zb) < VIEW_M)
        seg = ok[:-1] & ok[1:]
        if mask is not None:
            seg &= mask[:-1] & mask[1:]
        i = np.where(seg)[0]
        quads = np.stack([np.column_stack([xa[i], ya[i]]), np.column_stack([xa[i + 1], ya[i + 1]]),
                          np.column_stack([xb[i + 1], yb[i + 1]]), np.column_stack([xb[i], yb[i]])], axis=1)
        return quads, (za[i] + zb[i]) / 2, i

    def draw_sky(self, ax, cam: Camera) -> None:
        y_h = cam.horizon_y()
        if y_h >= 1.0:
            return
        top, hor = np.array(to_rgb(self.sky[0])), np.array(to_rgb(self.sky[1]))
        u = np.linspace(0, 1, 64)[:, None]
        img = (hor * (1 - u) ** 2 + top * (1 - (1 - u) ** 2))[:, None, :]
        ax.imshow(img, extent=(-0.5625, 0.5625, max(y_h, -1.0), 1.0), origin="lower", aspect="auto",
                  interpolation="bilinear", zorder=-1)

    def draw_ground(self, ax, cam: Camera) -> None:
        polys, colors = [], []
        for side in (1, -1):
            q, d, _ = self._strip(cam, *self.edges[side])
            polys.append(q)
            colors.append(_fog(np.tile(self.ground_rgb, (len(q), 1)), d))
        q = np.concatenate(polys)
        c = np.concatenate(colors)
        if len(q):
            ax.add_collection(PolyCollection(q, facecolors=c, edgecolors=c, linewidths=0.3, zorder=1))

    def draw_track_details(self, ax, cam: Camera) -> None:
        polys, colors = [], []
        for side in (1, -1):
            q, d, i = self._strip(cam, *self.kerbs[side], mask=self.kerb)
            rgb = np.where(self.kerb_red[i][:, None], [[0.62, 0.09, 0.09]], [[0.78, 0.78, 0.8]])
            polys.append(q)
            colors.append(_fog(rgb, d))
        fx, fy, fz = cam.proj(self.finish.reshape(-1, 3))
        fz = fz.reshape(len(self.finish), 4)
        ok = np.all((fz > 3) & (fz < VIEW_M), axis=1)
        if ok.any():
            polys.append(np.stack([fx, fy], axis=1).reshape(len(self.finish), 4, 2)[ok])
            colors.append(_fog(self.finish_rgb[ok], fz[ok].mean(axis=1)))
        q = np.concatenate(polys)
        c = np.concatenate(colors)
        if len(q):
            ax.add_collection(PolyCollection(q, facecolors=c, edgecolors="none", zorder=2.5))

    def draw_gantry(self, ax, cam: Camera, zorder: float) -> float | None:
        """Portal über der Ziellinie. Gibt seine Tiefe zurück (None = nicht sichtbar)."""
        gx, gy, gz = cam.proj(self.gantry.reshape(-1, 3))
        gz = gz.reshape(len(self.gantry), 4)
        if np.any(gz < 3) or gz.min() > VIEW_M:
            return None
        polys = np.stack([gx, gy], axis=1).reshape(len(self.gantry), 4, 2)
        c = _fog(np.tile([0.2, 0.2, 0.23], (len(polys), 1)), gz.mean(axis=1))
        ax.add_collection(PolyCollection(polys, facecolors=c, edgecolors=np.clip(c * 1.6, 0, 1),
                                         linewidths=0.5, zorder=zorder))
        return float(gz.mean())

    def gantry_depth(self, cam: Camera) -> float:
        return float(cam.proj(self.gantry.reshape(-1, 3))[2].mean())

    def draw_barriers(self, ax, cam: Camera) -> None:
        polys, depth = [], []
        for side in (1, -1):
            lo, hi, ok = self.barriers[side]
            q, d, _ = self._strip(cam, lo, hi, mask=ok)
            polys.append(q)
            depth.append(d)
        q, d = np.concatenate(polys), np.concatenate(depth)
        if not len(q):
            return
        order = np.argsort(-d)
        c = _fog(np.tile(self.barrier_rgb, (len(q), 1)), d)
        ax.add_collection(PolyCollection(q[order], facecolors=c[order], edgecolors=c[order] * 0.8,
                                         linewidths=0.3, zorder=3.5))

    def draw_trees(self, ax, cam: Camera) -> None:
        x, y, zc = cam.proj(self.tree_base)
        ok = (zc > 8) & (zc < VIEW_M) & (np.abs(x) < 0.75) & (y < 1.2)
        i = np.where(ok)[0]
        if not len(i):
            return
        i = i[np.argsort(-zc[i])]
        base = self.tree_base[i]
        h = self.tree_h[i][:, None]
        up = np.array([0, 0, 1.0])
        r = cam.r
        # Silhouette: Stamm + Krone, immer zur Kamera gedreht
        shape = [(-0.06, 0.0), (0.06, 0.0), (0.06, 0.18), (0.32, 0.22), (0.18, 0.55), (0.1, 0.8), (0.0, 1.0),
                 (-0.1, 0.8), (-0.18, 0.55), (-0.32, 0.22), (-0.06, 0.18)]
        pts = np.stack([base + (sx * h) * r + (sz * h) * up for sx, sz in shape], axis=1)   # (n, k, 3)
        px, py, _ = cam.proj(pts.reshape(-1, 3))
        polys = np.stack([px, py], axis=1).reshape(len(i), len(shape), 2)
        c = _fog(self.tree_rgb[i], zc[i])
        ax.add_collection(PolyCollection(polys, facecolors=c, edgecolors=c * 0.7, linewidths=0.3, zorder=4))


# ── Auto ─────────────────────────────────────────────────────────────────────
# Einheiten: x nach vorn, w nach links, z nach oben, jeweils × CAR Meter.
# Rollen: body (Teamfarbe), dark (Teamfarbe dunkel), carbon, tyre, side, rim, helmet, light
def _mirror(poly):
    return [(x, -w, z) for x, w, z in poly]


def _car_model() -> list[tuple[np.ndarray, str, float]]:
    parts: list[tuple[list, str, float]] = []

    def both(poly, role, bias=0.0):
        parts.append((poly, role, bias))
        parts.append((_mirror(poly), role, bias))

    parts.append(([(1.45, -0.9, 0.06), (1.45, 0.9, 0.06), (-2.35, 0.9, 0.06), (-2.35, -0.9, 0.06)], "carbon", 0.8))
    # Seitenkästen
    both([(0.95, 0.30, 0.52), (0.95, 0.86, 0.46), (-1.15, 0.62, 0.30), (-1.15, 0.30, 0.38)], "body")
    both([(0.95, 0.86, 0.46), (0.95, 0.86, 0.12), (-1.15, 0.62, 0.12), (-1.15, 0.62, 0.30)], "dark")
    both([(0.95, 0.30, 0.52), (0.95, 0.86, 0.46), (0.95, 0.86, 0.12), (0.95, 0.30, 0.12)], "carbon")
    both([(-1.15, 0.30, 0.38), (-1.15, 0.62, 0.30), (-1.15, 0.62, 0.12), (-1.15, 0.30, 0.12)], "carbon")
    # Monocoque und Nase
    both([(1.35, 0.24, 0.58), (1.35, 0.24, 0.14), (-0.25, 0.30, 0.14), (-0.25, 0.30, 0.64)], "dark")
    parts.append(([(1.35, -0.24, 0.58), (1.35, 0.24, 0.58), (0.55, 0.28, 0.62), (0.55, -0.28, 0.62)], "body", 0.0))
    parts.append(([(3.0, -0.07, 0.26), (3.0, 0.07, 0.26), (1.35, 0.24, 0.58), (1.35, -0.24, 0.58)], "body", 0.0))
    both([(3.0, 0.07, 0.26), (3.0, 0.07, 0.15), (1.35, 0.24, 0.15), (1.35, 0.24, 0.58)], "dark")
    # Cockpit, Helm, Halo
    parts.append(([(0.55, -0.22, 0.63), (0.55, 0.22, 0.63), (-0.2, 0.24, 0.66), (-0.2, -0.24, 0.66)], "carbon", 0.0))
    parts.append(([(0.12, -0.11, 0.8), (0.12, 0.11, 0.8), (-0.14, 0.11, 0.8), (-0.14, -0.11, 0.8)], "helmet", -0.05))
    ring = [(0.62, 0.0), (0.5, 0.17), (0.25, 0.25), (-0.05, 0.25), (-0.22, 0.2)]
    for (x0, w0), (x1, w1) in zip(ring, ring[1:]):
        both([(x0, w0, 0.8), (x1, w1, 0.8), (x1, w1, 0.86), (x0, w0, 0.86)], "carbon", -0.1)
    parts.append(([(0.78, -0.03, 0.6), (0.78, 0.03, 0.6), (0.62, 0.03, 0.86), (0.62, -0.03, 0.86)], "carbon", -0.1))
    # Motorabdeckung mit Airbox und Finne
    parts.append(([(-0.3, -0.12, 1.0), (-0.3, 0.12, 1.0), (-2.2, 0.06, 0.42), (-2.2, -0.06, 0.42)], "body", 0.0))
    both([(-0.3, 0.28, 0.64), (-0.3, 0.12, 1.0), (-2.2, 0.06, 0.42), (-2.2, 0.18, 0.3)], "dark")
    parts.append(([(-0.3, -0.12, 1.0), (-0.3, 0.12, 1.0), (-0.3, 0.28, 0.64), (-0.3, -0.28, 0.64)], "carbon", 0.05))
    parts.append(([(-0.7, 0.0, 1.02), (-2.35, 0.0, 0.55), (-2.35, 0.0, 0.9), (-1.0, 0.0, 1.07)], "body", -0.02))
    # Frontflügel
    parts.append(([(3.12, -0.98, 0.10), (3.12, 0.98, 0.10), (2.72, 0.98, 0.14), (2.72, -0.98, 0.14)], "carbon", 0.2))
    both([(2.8, 0.98, 0.2), (2.8, 0.25, 0.16), (2.52, 0.25, 0.22), (2.52, 0.98, 0.3)], "body", 0.1)
    both([(3.12, 0.98, 0.06), (2.45, 0.98, 0.06), (2.45, 0.98, 0.34), (3.0, 0.98, 0.26)], "dark")
    # Heck: Diffusor, Beam Wing, Heckflügel, Endplatten, Regenlicht
    parts.append(([(-2.3, -0.62, 0.06), (-2.3, 0.62, 0.06), (-2.72, 0.62, 0.3), (-2.72, -0.62, 0.3)], "carbon", 0.1))
    parts.append(([(-2.6, -0.45, 0.4), (-2.6, 0.45, 0.4), (-2.8, 0.45, 0.43), (-2.8, -0.45, 0.43)], "carbon", 0.0))
    parts.append(([(-2.55, -0.6, 0.92), (-2.55, 0.6, 0.92), (-2.9, 0.6, 0.88), (-2.9, -0.6, 0.88)], "carbon", 0.0))
    parts.append(([(-2.6, -0.6, 1.05), (-2.6, 0.6, 1.05), (-2.85, 0.6, 1.12), (-2.85, -0.6, 1.12)], "body", 0.0))
    parts.append(([(-2.9, -0.6, 0.86), (-2.9, 0.6, 0.86), (-2.88, 0.6, 1.13), (-2.88, -0.6, 1.13)], "dark", -0.3))
    both([(-2.45, 0.62, 0.4), (-2.95, 0.62, 0.4), (-2.95, 0.62, 1.15), (-2.5, 0.62, 1.1)], "body", -0.2)
    parts.append(([(-2.95, -0.07, 0.44), (-2.95, 0.07, 0.44), (-2.95, 0.07, 0.53), (-2.95, -0.07, 0.53)], "light", -0.5))
    # Räder: Zylinder aus 12 Flächen + Flanken + Felge
    k = 12
    ang = np.linspace(0, 2 * np.pi, k, endpoint=False)
    for xc, wc, r, hw in ((1.85, 0.79, 0.37, 0.16), (-1.75, 0.75, 0.40, 0.22)):
        for sgn in (1, -1):
            w_out, w_in = sgn * (wc + hw), sgn * (wc - hw)
            ring_x, ring_z = xc + r * np.cos(ang), r + r * np.sin(ang)
            for j in range(k):
                j2 = (j + 1) % k
                parts.append(([(ring_x[j], w_out, ring_z[j]), (ring_x[j2], w_out, ring_z[j2]),
                               (ring_x[j2], w_in, ring_z[j2]), (ring_x[j], w_in, ring_z[j])], "tyre", 0.0))
            parts.append(([(x, w_out, z) for x, z in zip(ring_x, ring_z)], "side", -0.02))
            parts.append(([(xc + 0.55 * r * np.cos(a), w_out + sgn * 0.01, r + 0.55 * r * np.sin(a)) for a in ang],
                          "rim", -0.04))
            parts.append(([(x, w_in, z) for x, z in zip(ring_x, ring_z)], "side", 0.02))
    return [(np.array(p, dtype=float), role, bias) for p, role, bias in parts]


_MODEL = _car_model()
_SIZES = np.array([len(p) for p, _, _ in _MODEL])
_FLAT = np.concatenate([p for p, _, _ in _MODEL])
_BIAS = np.array([b for _, _, b in _MODEL])
_ROLES = [r for _, r, _ in _MODEL]
_STARTS = np.concatenate([[0], np.cumsum(_SIZES)[:-1]])


def _normals(W: np.ndarray) -> np.ndarray:
    out = np.empty((len(_SIZES), 3))
    for j, (s, n) in enumerate(zip(_STARTS, _SIZES)):
        p = W[s:s + n]
        v = np.cross(p[1] - p[0], p[min(2, n - 1)] - p[0])
        out[j] = v / (np.linalg.norm(v) or 1.0)
    return out


def draw_car(ax, cam: Camera, pos, fw, col, name, z, label_side: int = 1, alpha: float = 1.0):
    side = np.array([-fw[1], fw[0], 0])
    up = np.array([0.0, 0.0, 1.0])
    rgb = np.array(to_rgb(col))
    palette = {"body": rgb, "dark": np.clip(rgb * 0.5, 0, 1), "carbon": np.array([0.07, 0.07, 0.08]),
               "tyre": np.array([0.05, 0.05, 0.055]), "side": np.array([0.1, 0.1, 0.11]),
               "rim": np.array([0.32, 0.32, 0.34]), "helmet": np.array([0.8, 0.8, 0.82]),
               "light": np.array([0.55, 0.05, 0.05])}

    # Schatten
    sh = [(3.1, 0.55), (2.0, 1.0), (-2.3, 1.0), (-3.0, 0.65)]
    ring = sh + [(x, -w) for x, w in reversed(sh)]
    shadow = np.array([pos + fw * x * CAR + side * w * CAR + up * 0.02 for x, w in ring])
    sx, sy, sz = cam.proj(shadow)
    if np.any(sz < 1):
        return
    ax.fill(sx, sy, color="black", alpha=0.35 * alpha, zorder=z, linewidth=0)

    W = pos + np.outer(_FLAT[:, 0] * CAR, fw) + np.outer(_FLAT[:, 1] * CAR, side) + np.outer(_FLAT[:, 2] * CAR, up)
    px, py, pz = cam.proj(W)
    if np.any(pz < 1):
        return
    shade = 0.55 + 0.45 * np.abs(_normals(W) @ LIGHT)
    polys, depth, colors = [], [], []
    for s, n, role, bias, sh_ in zip(_STARTS, _SIZES, _ROLES, _BIAS, shade):
        polys.append(np.column_stack([px[s:s + n], py[s:s + n]]))
        depth.append(pz[s:s + n].mean() + bias)
        c = palette[role] * (1.0 if role == "light" else sh_)
        colors.append(np.clip(c, 0, 1))
    order = np.argsort(-np.array(depth))
    polys = [polys[i] for i in order]
    colors = np.array(colors)[order]
    ax.add_collection(PolyCollection(polys, facecolors=colors, edgecolors=np.clip(colors * 0.7, 0, 1), alpha=alpha,
                                     linewidths=0.3, zorder=z + 0.5))

    cx, cy, _ = cam.proj(pos + [0, 0, 0.6 * CAR])
    lx, ly = cx[0] + 0.13 * label_side, cy[0] + 0.02
    ax.plot([cx[0], lx - 0.01 * label_side], [cy[0], ly], color=col, linewidth=1.2, zorder=z + 1)
    r, g, b = rgb
    label_ink = "black" if 0.299 * r + 0.587 * g + 0.114 * b > 0.6 else "white"   # weißes Auto → schwarze Schrift
    ax.text(lx, ly, name, fontsize=13, fontweight="bold", color=label_ink, ha="left" if label_side > 0 else "right",
            va="center", zorder=z + 1,
            bbox={"boxstyle": "round,pad=0.28", "facecolor": col, "edgecolor": "none"})


def draw_scene(ax, scene: Scene, t: float) -> float:
    """Zeichnet ein Bild zur Zeit t (Sekunden ab t0). Gibt den laufenden Abstand zurück."""
    global _FOG
    ax.clear()
    ax.axis("off")
    cam = Camera(scene, t)
    pa, fa = scene.pos(scene.a, t)
    pb, fb = scene.pos(scene.b, t)
    env = scene.environment()
    _FOG = env.fog
    # Boden bis zum Horizont (jenseits von Gras/Gehweg), darüber der Himmel
    ax.add_patch(plt_Rectangle((-1, -1.5), 2, 3, facecolor=env.far, edgecolor="none", zorder=-2))
    env.draw_sky(ax, cam)
    ax.set_xlim(-0.5625, 0.5625)
    ax.set_ylim(-1.0, 1.0)

    # Bodenraster, am Weltraster ausgerichtet → läuft beim Fahren mit (nur jenseits des Grases sichtbar)
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
    if env.grid_alpha:
        ax.add_collection(LineCollection(lines, colors=COLORS["grid"], linewidths=0.6, alpha=env.grid_alpha, zorder=0))

    env.draw_ground(ax, cam)

    # Strecke: nur der Teil vor der Kamera und in Sichtweite
    xl, yl, zl = cam.proj(scene.L)
    xr, yr, zr = cam.proj(scene.R)
    ok = (np.minimum(zl, zr) > 3) & (np.minimum(zl, zr) < VIEW_M)
    idx = np.where(ok[:-1] & ok[1:])[0]
    quads = np.stack([np.column_stack([xl[idx], yl[idx]]), np.column_stack([xl[idx + 1], yl[idx + 1]]),
                      np.column_stack([xr[idx + 1], yr[idx + 1]]), np.column_stack([xr[idx], yr[idx]])], axis=1)
    order = np.argsort(-zl[idx])
    face = _fog(np.tile(env.asphalt, (len(order), 1)), zl[idx][order])
    ax.add_collection(PolyCollection(quads[order], facecolors=face, edgecolors=face, linewidths=0.3, zorder=2))
    for ex, ey in ((xl, yl), (xr, yr)):
        ax.plot(np.where(ok, ex, np.nan), np.where(ok, ey, np.nan), color=env.edge, linewidth=0.9, zorder=3)
    env.draw_track_details(ax, cam)
    env.draw_barriers(ax, cam)
    env.draw_trees(ax, cam)
    env.draw_buildings(ax, cam)

    # Abstand als Band: B's Weg der nächsten `gap` Sekunden endet genau dort, wo A jetzt ist
    # (nicht, während die Autos nebeneinander auseinandergeschoben sind – dann läge es neben B)
    g = scene.gap(t)
    if np.isfinite(g) and g > 0.02 and scene.separation(t) < 0.5:
        band = scene.world(scene.b, np.linspace(t, t + g, 30))
        band[:, 2] -= scene.z_off - 0.05
        bx, by, bz = cam.proj(band)
        m = bz > 2
        ax.plot(bx[m], by[m], color=COLORS["accent"], linewidth=5, alpha=0.85, zorder=4.5, solid_capstyle="round")

    # Portal über der Ziellinie – vor oder hinter dem Auto, je nach Tiefe; ganz nah an der
    # Kamera nicht mehr (es läge dann als grauer Balken am unteren Bildrand)
    # nur Autos VOR der Kamera zählen (an der Ziellinie liegt der Zweite oft weit hinter ihr)
    car_depth = min([z for z in (cam.proj(pa)[2][0], cam.proj(pb)[2][0]) if z > 1] or [np.inf])
    gd = env.gantry_depth(cam)
    if 22.0 < gd < VIEW_M:
        env.draw_gantry(ax, cam, zorder=12 if gd < car_depth else 6)

    # Wer näher an der Kamera ist, wird zuletzt gezeichnet
    cars = sorted(((cam.proj(pa)[2][0], pa, fa, scene.a), (cam.proj(pb)[2][0], pb, fb, scene.b)), key=lambda c: -c[0])
    # Ghost zuletzt (obenauf) und halbtransparent – überlappen sich die Autos (Ghost Lap am Start),
    # sieht man beide
    cars.sort(key=lambda c: c[3] == scene.ghost)
    # Namensschilder nach außen: nebeneinander bekommt das linke Auto sein Schild links
    xa_s, xb_s = cam.proj(pa)[0][0], cam.proj(pb)[0][0]
    beside = scene.separation(t) > 1.0
    for i, (_, p, fw, d) in enumerate(cars):
        is_left = (xa_s < xb_s) if d == scene.a else (xb_s < xa_s)
        if scene.rain:
            draw_spray(ax, cam, p, fw, t, 6.5 + 2 * i)
        draw_car(ax, cam, p, fw, scene.col[d], d, 7 + 2 * i, label_side=-1 if (beside and is_left) else 1,
                 alpha=0.45 if d == scene.ghost else 1.0)
    if scene.rain:
        draw_rain(ax, t)
    return g


def draw_spray(ax, cam: Camera, pos, fw, t: float, z: float) -> None:
    """Gischt hinter einem Auto: graue Wolke, die nach hinten breiter und blasser wird.
    Zufall pro Bild (Gischt flimmert auch in echt), aber reproduzierbar über t."""
    rng = np.random.default_rng(int(round(t * 120)) % (2 ** 32))
    fw = np.asarray(fw, dtype=float)
    side = np.array([-fw[1], fw[0], 0.0])
    k = rng.uniform(0.0, 1.0, SPRAY_POINTS) ** 1.5            # dichter direkt am Heck
    back = CAR_LEN_M * 0.45 + k * SPRAY_M
    Q = (np.asarray(pos)[None] - fw[None] * back[:, None]
         + side[None] * (rng.normal(0, 1, SPRAY_POINTS) * (0.5 + 1.6 * k))[:, None]
         + np.array([0, 0, 1.0])[None] * (0.2 + rng.uniform(0, 1, SPRAY_POINTS) * (0.6 + 1.6 * k))[:, None])
    x, y, zc = cam.proj(Q)
    m = zc > 2
    if not m.any():
        return
    size = np.clip(16000.0 * (0.6 + 2.5 * k[m]) / zc[m] ** 1.3, 6, 1600)
    alpha = np.clip(0.09 * (1 - k[m]) + 0.015, 0, 1)
    rgba = np.column_stack([np.full((m.sum(), 3), 0.86), alpha])
    ax.scatter(x[m], y[m], s=size, c=rgba, linewidths=0, zorder=z)


def draw_rain(ax, t: float) -> None:
    """Regenstriche über dem ganzen Bild. Feste Startpunkte, die mit der Zeit t nach
    unten laufen – in der Zeitlupe fällt der Regen also mit langsamer (gewollt)."""
    rng = np.random.default_rng(7)
    x0 = rng.uniform(-0.6, 0.6, RAIN_STREAKS)
    y0 = rng.uniform(0.0, 2.0, RAIN_STREAKS)
    speed = RAIN_FALL * rng.uniform(0.8, 1.25, RAIN_STREAKS)
    length = rng.uniform(0.035, 0.075, RAIN_STREAKS)
    y = (y0 - t * speed) % 2.0 - 1.0
    x = x0 + 0.08 * y                                          # leicht schräg (Fahrtwind)
    segs = np.stack([np.column_stack([x, y]), np.column_stack([x - 0.1 * length, y - length])], axis=1)
    ax.add_collection(LineCollection(segs, colors=[(0.85, 0.88, 0.92, 0.38)], linewidths=0.9, zorder=30))


class MiniMap:
    """Kontext für den 3D-Anfang: kleine Streckenkarte oben links mit Ziellinie,
    beiden Autos und einer Zeile „KM 1.2 / 5.8 · SECTOR 1“. Ohne sie weiß im
    Feed niemand, wo auf der Runde die Szene spielt."""

    def __init__(self, fig, scene: Scene, box=(0.05, 0.60, 0.26, 0.19), sector_fracs: list[float] | None = None):
        self.scene = scene
        # dunkler Hintergrund – vor Häusern (Stadtkurs) war die Karte sonst kaum zu sehen
        from matplotlib.patches import FancyBboxPatch
        self.backdrop = FancyBboxPatch((box[0] - 0.01, box[1] - 0.03), box[2] + 0.02, box[3] + 0.035,
                                       boxstyle="round,pad=0.0,rounding_size=0.012", transform=fig.transFigure,
                                       facecolor=COLORS["bg"], edgecolor="none", alpha=0.6, zorder=-0.5)
        fig.add_artist(self.backdrop)
        self.ax = fig.add_axes(list(box))
        self.ax.set_aspect("equal")
        self.ax.axis("off")
        P = scene.P
        self.ax.plot(P[:, 0], P[:, 1], color=COLORS["grid"], linewidth=5, solid_capstyle="round", zorder=1)
        self.ax.plot(P[:, 0], P[:, 1], color="#3a3a44", linewidth=2.5, solid_capstyle="round", zorder=2)
        self.ax.scatter([P[0, 0]], [P[0, 1]], s=26, marker="s", color="white", zorder=3)
        self.dots = {d: self.ax.scatter([], [], s=42, color=scene.col[d], edgecolor="white", linewidth=1.0, zorder=5)
                     for d in (scene.a, scene.b)}
        self.cum = scene.cum
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
        self.backdrop.set_visible(on)
