"""Blender-Export: eine fertige `Scene` (chase3d) als JSON, das Blender einlesen kann.

WOZU: chase3d zeichnet mit matplotlib (Polygone von hinten nach vorne). Für ein schöneres
Bild soll Blender rendern – mit Z-Buffer, Licht und Schatten. Dieses Modul trennt die DATEN
(Positionen, Kamera, Strecke) vom Zeichnen: alles, was chase3d schon berechnet (Überholen
nebeneinander, Kamerapfad, Umgebung), bleibt gleich und wird nur anders dargestellt.

KOORDINATEN: Meter, x/y wie in chase3d (aus OpenF1), z = oben, rechtshändig – so wie Blender.
Die Höhe ist in chase3d um Z_EXAG überhöht; hier standardmäßig NICHT (z_exag=1.0 → echte
Höhe), das sieht in einem echten 3D-Bild natürlicher aus. Mit z_exag=Z_EXAG gibt es das alte Bild.

GLÄTTUNG: Die Höhe der Autos wird in chase3d nur linear zwischen den OpenF1-Punkten
interpoliert (≈ 4 Punkte pro Sekunde) – das gibt Knicke. Hier werden Höhe, Fahrtrichtung
und Kamera über die Bilder leicht gefaltet (Gauß). x/y sind schon glatt (Hermite).

FORMAT (schema 1):
  meta   – fps, Größe, Brennweite (Sichtfeld), Fahrer, Teamfarben, Licht, Szenerie, Regen
  track  – Mittellinie, linker/rechter Rand, Breite, Rundenlänge
  env    – Randsteine, Leitplanken, Bäume, Start/Ziel-Portal, (Stadt:) Häuser
  frames – pro Bild: t, Position+Richtung beider Autos, Kamera, Abstand
Nicht exportiert (noch): Fenster der Häuser, Himmel – das macht das Blender-Skript selbst.
"""
from __future__ import annotations

import json
import math
from contextlib import contextmanager
from pathlib import Path

import numpy as np

import stintlab.reels.chase3d as c3
from stintlab.reels.chase3d import FOC, GRASS_W, TRACK_W, Z_EXAG, Camera, Scene

SCHEMA = 1
ASPECT = (1080, 1920)            # 9:16 wie die Reels
HALF_W = 0.5625                  # halbe Bildbreite in chase3d-Bildkoordinaten (Höhe: ±1)
# Z nur leicht glätten: die Strecke selbst ist schon geglättet, und bei 80 m/s wären 0,3 s ein Versatz von 25 m
# entlang der Strecke – an Kuppen (Raidillon) schwebte das Auto bis zu 0,5 m über dem Asphalt.
Z_SMOOTH_S, YAW_SMOOTH_S, CAM_SMOOTH_S, PITCH_SMOOTH_S = 0.08, 0.10, 0.15, 0.15

# Wegkamera (cam_mode="path"): hängt auf dem Weg des Verfolgers, back Meter dahinter, und schaut ahead Meter
# auf dem Weg voraus – so bleibt das Auto in Kurven in der Bildmitte (die klassische Kamera blickt geradeaus).
RETIME_SIGMA_S = 0.30                     # Tempo-Glättung der Autos (siehe retime_xy)
PATH_PRE_S, PATH_POST_S = 2.5, 1.5        # Weg vor/nach dem Zeitraum, damit Anfang und Ende Kameraziele haben
PATH_SMOOTH_S, PATH_CAM_SMOOTH_S, PATH_AIM_SMOOTH_S = 0.12, 0.20, 0.25
AIM_SHARE = 0.0                           # Blickziel = das Auto selbst (Kurve: ein Blick weiter voraus schiebt es zum Bildrand)
LEADER_PULL, LEADER_RANGE_M = 0.30, 80.0  # Blick wandert bis zu 30 % zum Führenden, wenn er näher als 80 m vor uns ist

# Kamera für Blender: viel näher und tiefer als im matplotlib-Bild (dort 40 m / 22 m / 25 m) – im Hochformat
# sollen die Autos das Bild füllen. back = Meter hinter dem Verfolger, height = Höhe über der Strecke,
# ahead = Meter, die der Blick hinter die Mitte der beiden Autos zielt.
CAM_BACK, CAM_HEIGHT, CAM_AHEAD = 13.0, 4.8, 12.0


@contextmanager
def camera_rig(back: float, height: float, ahead: float):
    """chase3d.Camera liest BACK/HEIGHT/AHEAD aus dem Modul – hier nur für die Dauer des Exports ändern."""
    old = c3.BACK, c3.HEIGHT, c3.AHEAD
    c3.BACK, c3.HEIGHT, c3.AHEAD = back, height, ahead
    try:
        yield
    finally:
        c3.BACK, c3.HEIGHT, c3.AHEAD = old


def gauss_smooth(a: np.ndarray, sigma_frames: float) -> np.ndarray:
    """Gauß-Faltung entlang Achse 0, Ränder werden fortgesetzt (kein Einknicken am Anfang/Ende)."""
    a = np.asarray(a, dtype=float)
    if sigma_frames <= 0 or len(a) < 3:
        return a.copy()
    r = max(int(math.ceil(3 * sigma_frames)), 1)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma_frames) ** 2)
    k /= k.sum()
    pad = [(r, r)] + [(0, 0)] * (a.ndim - 1)
    p = np.pad(a, pad, mode="edge")
    out = np.empty_like(a)
    flat_in = p.reshape(len(p), -1)
    flat_out = out.reshape(len(a), -1)
    for j in range(flat_in.shape[1]):
        flat_out[:, j] = np.convolve(flat_in[:, j], k, mode="valid")
    return out


def _round(a, nd: int = 3):
    """Zahlenfeld → verschachtelte Liste (gerundet, NaN → None), JSON-tauglich."""
    arr = np.round(np.asarray(a, dtype=float), nd)
    if arr.ndim == 0:
        return None if not np.isfinite(arr) else float(arr)
    out = arr.tolist()

    def clean(x):
        if isinstance(x, list):
            return [clean(v) for v in x]
        return None if (x != x or x in (math.inf, -math.inf)) else x

    return clean(out)


def _zfix(arr: np.ndarray, z_exag: float) -> np.ndarray:
    """z-Spalte (letzte) von chase3d-Überhöhung auf die gewünschte umrechnen."""
    out = np.array(arr, dtype=float, copy=True)
    out[..., -1] *= z_exag / Z_EXAG
    return out


def fov_degrees() -> tuple[float, float]:
    """Sichtfeld (horizontal, vertikal) der chase3d-Kamera aus FOC."""
    return (math.degrees(2 * math.atan(HALF_W / FOC)), math.degrees(2 * math.atan(1.0 / FOC)))


def _track(scene: Scene, z_exag: float) -> dict:
    return {
        "width_m": TRACK_W,
        "length_m": float(scene.cum[-1]),
        "centre": _round(_zfix(scene.P, z_exag)),
        "left": _round(_zfix(scene.L, z_exag)),       # geschlossene Schleife (erster Punkt am Ende)
        "right": _round(_zfix(scene.R, z_exag)),
    }


def _env(scene: Scene, z_exag: float) -> dict:
    env = scene.environment()
    out: dict = {"city": bool(env.city)}
    out["kerbs"] = {str(s): {"inner": _round(_zfix(a, z_exag)), "outer": _round(_zfix(b, z_exag))}
                    for s, (a, b) in env.kerbs.items()}
    out["kerb_on"] = [bool(v) for v in env.kerb]
    out["kerb_red"] = [bool(v) for v in env.kerb_red]
    out["barriers"] = {str(s): {"low": _round(_zfix(lo, z_exag)), "high": _round(_zfix(hi, z_exag)),
                                "ok": [bool(v) for v in ok]}
                       for s, (lo, hi, ok) in env.barriers.items()}
    out["trees"] = {"base": _round(_zfix(env.tree_base, z_exag)), "height_m": _round(env.tree_h, 2),
                    "rgb": _round(env.tree_rgb, 3)}
    out["palette"] = {
        "asphalt": _round(env.asphalt, 3), "ground": _round(env.ground_rgb, 3),
        "barrier": _round(env.barrier_rgb, 3), "fog": _round(env.fog, 3), "far": _round(env.far, 3),
        "sky_top": env.sky[0], "sky_hor": env.sky[1], "edge": env.edge,
        "grass_w_m": GRASS_W, "window_lit": float(env.window_lit),
    }
    out["gantry"] = _round(_zfix(env.gantry, z_exag))
    out["finish"] = {"quads": _round(_zfix(env.finish, z_exag)), "rgb": _round(env.finish_rgb, 3)}
    if env.city:
        z0 = np.asarray(env.bld_z0, dtype=float) * z_exag / Z_EXAG
        out["buildings"] = {"foot": _round(env.bld_foot), "z0": _round(z0), "height_m": _round(env.bld_h, 2),
                            "rgb": _round(env.bld_rgb, 3)}
    return out


def surface_z(centre: np.ndarray, xy: np.ndarray) -> np.ndarray:
    """Höhe der Streckenoberfläche an den Stellen xy (n,2): Mittellinie (m,3), nächstes Segment, linear.
    Die Höhe des Autos aus den OpenF1-Daten stimmt nicht mit der gemittelten Strecke überein (Monza 2026:
    Auto bis 13 cm unter dem Asphalt) – Räder würden einsinken. Deshalb wird das Auto auf die Fläche gesetzt."""
    m = len(centre)
    d = np.hypot(xy[:, None, 0] - centre[None, :, 0], xy[:, None, 1] - centre[None, :, 1])
    near = d.argmin(axis=1)
    out = np.empty(len(xy))
    for k, j in enumerate(near):
        best = (np.inf, centre[j, 2])
        for a, b in (((j - 1) % m, j), (j, (j + 1) % m)):
            A, B = centre[a], centre[b]
            ab = B[:2] - A[:2]
            l2 = float(ab @ ab)
            if l2 < 1e-9:
                continue
            t = float(np.clip((xy[k] - A[:2]) @ ab / l2, 0.0, 1.0))
            dist = float(np.hypot(*(xy[k] - (A[:2] + t * ab))))
            if dist < best[0]:
                best = (dist, A[2] + t * (B[2] - A[2]))
        out[k] = best[1]
    return out


def retime_xy(xy: np.ndarray, fps: int, sigma_s: float = RETIME_SIGMA_S) -> np.ndarray:
    """Fahrweg unverändert lassen, nur das Tempo glätten. OpenF1 liefert Positionen nur ein paar Mal pro Sekunde;
    dazwischen wird linear aufgefüllt, daher springt die Geschwindigkeit von Bild zu Bild (bei 20 fps sah man
    Spitzen bis 400 km/h und Beschleunigungen von über 400 m/s²). Hier: zurückgelegte Strecke s(t) mit
    Medianfilter von Ausreißern befreien, glätten und die Position wieder auf dem ursprünglichen Weg ablesen."""
    xy = np.asarray(xy, dtype=float)
    if len(xy) < 7:
        return xy.copy()
    inc = np.hypot(*np.diff(xy, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(inc)])
    if s[-1] < 1e-6:
        return xy.copy()
    pad = np.pad(inc, 2, mode="edge")
    med = np.median(np.lib.stride_tricks.sliding_window_view(pad, 5), axis=1)
    s2 = np.concatenate([[0.0], np.cumsum(med)])
    s2 *= s[-1] / max(s2[-1], 1e-9)
    g = np.maximum.accumulate(gauss_smooth(s2, sigma_s * fps))
    return np.column_stack([np.interp(g, s, xy[:, 0]), np.interp(g, s, xy[:, 1])])


def _along(s_path: np.ndarray, vals: np.ndarray, s_q: np.ndarray) -> np.ndarray:
    """Werte entlang des Weges bei Weglängen s_q; außerhalb wird entlang der Randrichtung fortgesetzt."""
    out = np.column_stack([np.interp(s_q, s_path, vals[:, k]) for k in range(vals.shape[1])])

    def slope(i: int, j: int) -> np.ndarray:                 # Änderung je Meter Weg zwischen Index i und j
        ds = s_path[j] - s_path[i]
        return (vals[j] - vals[i]) / ds if ds > 1e-9 else np.zeros(vals.shape[1])

    lo, hi = s_q < s_path[0], s_q > s_path[-1]
    if lo.any():
        out[lo] = vals[0] + np.outer(s_q[lo] - s_path[0], slope(0, min(5, len(vals) - 1)))
    if hi.any():
        out[hi] = vals[-1] + np.outer(s_q[hi] - s_path[-1], slope(max(len(vals) - 6, 0), len(vals) - 1))
    return out


def _path_camera(scene: Scene, n: int, pre: int, xy_ext: np.ndarray, fps: int, z_exag: float, back: float,
                 height: float, ahead: float, car_a: np.ndarray, car_b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Kamera auf dem Weg des Verfolgers B (xy_ext: sein Weg mit pre Bildern davor und danach Auslauf).
    Gibt Position (n,3) und Blickrichtung (n,3) zurück."""
    xy = gauss_smooth(xy_ext, PATH_SMOOTH_S * fps)
    z = surface_z(_zfix(scene.P, z_exag), xy)
    path = np.column_stack([xy, z])
    s_path = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    s_now = s_path[pre:pre + n]
    cam_pt = _along(s_path, path, s_now - back)
    aim_pt = _along(s_path, path, s_now + AIM_SHARE * ahead)
    # Führenden leicht mit ins Bild nehmen, solange er nahe VOR dem Verfolger fährt
    to_a = car_a[:, :2] - car_b[:, :2]
    dist = np.hypot(*to_a.T)
    tan = _along(s_path, path, s_now + 1.0)[:, :2] - path[pre:pre + n, :2]
    in_front = np.einsum("ij,ij->i", to_a, tan) > 0
    w = LEADER_PULL * np.clip(1.0 - dist / LEADER_RANGE_M, 0.0, 1.0) * in_front
    aim_xy = (1 - w)[:, None] * aim_pt[:, :2] + w[:, None] * car_a[:, :2]
    aim = np.column_stack([aim_xy, aim_pt[:, 2] + 0.9])
    C = np.column_stack([cam_pt[:, :2], cam_pt[:, 2] + height])
    # Den Versatz zum Auto glätten, nicht die Weltposition: Glätten einer Kurve zieht sie nach innen (bei 85 m/s
    # und 0,25 s sind das in einer 100-m-Kurve über 2 m) – das Auto rutschte dadurch zum Bildrand.
    here = path[pre:pre + n]
    C = here + gauss_smooth(C - here, PATH_CAM_SMOOTH_S * fps)
    aim = here + gauss_smooth(aim - here, PATH_AIM_SMOOTH_S * fps)
    F = aim - C
    F /= np.linalg.norm(F, axis=1, keepdims=True)
    return C, F


def _frames(scene: Scene, t_start: float, t_end: float, fps: int, z_exag: float, cam_mode: str = "path",
            back: float = CAM_BACK, height: float = CAM_HEIGHT, ahead: float = CAM_AHEAD) -> dict:
    n = int(round((t_end - t_start) * fps))
    if n < 2:
        raise ValueError("Zeitraum zu kurz: mindestens 2 Bilder")
    ts = t_start + np.arange(n) / fps
    pre, post = (int(round(PATH_PRE_S * fps)), int(round(PATH_POST_S * fps))) if cam_mode == "path" else (0, 0)
    t_ext = np.concatenate([ts[0] - np.arange(pre, 0, -1) / fps, ts, ts[-1] + np.arange(1, post + 1) / fps])
    car = {}
    xy_ext = {}
    for d in (scene.a, scene.b):
        raw = [scene.pos(d, float(t)) for t in t_ext]
        pos_e = np.array([p for p, _ in raw])
        yaw_e = np.array([math.atan2(fw[1], fw[0]) for _, fw in raw])
        if cam_mode == "path":                                 # Tempo glätten (Ruckeln bei 20 fps)
            pos_e[:, :2] = retime_xy(pos_e[:, :2], fps)
        xy_ext[d] = pos_e[:, :2].copy()
        pos, yaw = pos_e[pre:pre + n].copy(), yaw_e[pre:pre + n]
        pos = _zfix(pos, z_exag)
        # Auto auf die Straßenoberfläche setzen (nicht die z-Werte des Autos aus OpenF1) und der Neigung folgen
        pos[:, 2] = gauss_smooth(surface_z(_zfix(scene.P, z_exag), pos[:, :2]), Z_SMOOTH_S * fps)
        yaw = gauss_smooth(np.unwrap(yaw), YAW_SMOOTH_S * fps)
        ds = np.maximum(np.hypot(*np.gradient(pos[:, :2], axis=0).T), 1e-3)
        pitch = gauss_smooth(np.arctan2(np.gradient(pos[:, 2]), ds), PITCH_SMOOTH_S * fps)
        car[d] = (pos, yaw, pitch)
    C = np.empty((n, 3))
    F = np.empty((n, 3))
    gap = np.empty(n)
    sep = np.empty(n)
    for i, t in enumerate(ts):
        if cam_mode == "classic":
            cam = Camera(scene, float(t))
            C[i], F[i] = cam.C, cam.f
        g = scene.gap(float(t))
        gap[i] = g if np.isfinite(g) else np.nan
        sep[i] = scene.separation(float(t))
    if cam_mode == "path":
        C, F = _path_camera(scene, n, pre, xy_ext[scene.b], fps, z_exag, back, height, ahead,
                            car[scene.a][0], car[scene.b][0])
    else:
        C, F = _zfix(C, z_exag), F.copy()
        # Blickrichtung mit derselben Höhenskala: z-Anteil von f umrechnen, dann neu normieren
        F[:, 2] *= z_exag / Z_EXAG
        F /= np.linalg.norm(F, axis=1, keepdims=True)
        C = gauss_smooth(C, CAM_SMOOTH_S * fps)
        F = gauss_smooth(F, CAM_SMOOTH_S * fps)
        F /= np.linalg.norm(F, axis=1, keepdims=True)
    return {
        "t": _round(ts, 4),
        "cars": {d: {"pos": _round(p), "yaw_rad": _round(y, 4), "pitch_rad": _round(pt, 4)}
                 for d, (p, y, pt) in car.items()},
        "camera": {"pos": _round(C), "forward": _round(F, 4)},
        "gap_s": _round(gap, 3),
        "separation_m": _round(sep, 2),
    }


def scene_to_dict(scene: Scene, t_start: float, t_end: float, fps: int = 60, z_exag: float = 1.0,
                  cam_back: float = CAM_BACK, cam_height: float = CAM_HEIGHT,
                  cam_ahead: float = CAM_AHEAD, cam_mode: str = "path") -> dict:
    """Szene im Zeitraum [t_start, t_end) (Sekunden ab t0 wie in chase3d) als Wörterbuch."""
    fov_h, fov_v = fov_degrees()
    with camera_rig(cam_back, cam_height, cam_ahead):
        frames = _frames(scene, t_start, t_end, fps, z_exag, cam_mode, cam_back, cam_height, cam_ahead)
    return {
        "schema": SCHEMA,
        "meta": {
            "fps": fps, "width_px": ASPECT[0], "height_px": ASPECT[1],
            "fov_h_deg": round(fov_h, 3), "fov_v_deg": round(fov_v, 3),
            "z_exag": z_exag, "units": "m, z up, right-handed",
            "a": scene.a, "b": scene.b, "ghost": scene.ghost,
            "colors": {d: str(scene.col[d]) for d in (scene.a, scene.b)},
            "light": scene.light, "scenery": scene.scenery, "rain": bool(scene.rain),
            "pass_t": scene.pass_t, "pass_side": scene.pass_side,
            "t_start": float(t_start), "t_end": float(t_end),
            "camera_rig": {"back_m": cam_back, "height_m": cam_height, "ahead_m": cam_ahead},
            "camera_mode": cam_mode,
        },
        "track": _track(scene, z_exag),
        "env": _env(scene, z_exag),
        "frames": frames,
    }


def export_scene(scene: Scene, t_start: float, t_end: float, path: str | Path, fps: int = 60,
                 z_exag: float = 1.0, **cam) -> Path:
    """Schreibt die Szene als JSON (für blender_render.py). Gibt den Pfad zurück.
    cam: cam_back, cam_height, cam_ahead (Meter) überschreiben die Kamera."""
    data = scene_to_dict(scene, t_start, t_end, fps=fps, z_exag=z_exag, **cam)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path
