"""3D-Anfang der Reels mit Blender statt matplotlib.

In der post.toml, beim Reel:

    opener = "blender"                  # Standard: "matplotlib" (das bisherige 3D-Bild)
    opener_quality = "final"            # "final" (64 Samples, volle Auflösung) oder "preview" (16 Samples, halbe Auflösung)
    opener_car = "assets/models/f1_2026_concept_polygon_model.glb"      # optional; ohne Datei: Platzhalter-Auto
    blender_exe = "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"      # optional (siehe find_blender)

make_post.py rendert dann die 3D-Zeitabschnitte des Reels mit Blender (stintlab/reels/blender_render.py), legt
die Bilder als Hintergrund unter Hooktext, Minimap, Abstandsanzeige und Namensschilder und mischt den Rest
unverändert. Die Bilder liegen neben dem Reel in `_blender/` und werden wiederverwendet, solange sich weder
die Szene noch das Render-Skript noch die Qualität geändert haben (zweiter Lauf: Sekunden statt Minuten).

Klappt Blender nicht (nicht gefunden, Render-Fehler), meldet make_post das und rendert das Reel mit dem
alten matplotlib-3D-Bild weiter – weekend.py bricht dadurch nie ab.

Nicht dabei (noch): das Abstandsband auf der Strecke (die Zahl oben bleibt) und die Zeitlupe von Ghost Lap
(bleibt matplotlib).

PFLICHT bei dem Modell „F1 2026 concept": Credit-Zeile (assets/CREDITS.md) in die Caption – make_post
erinnert nach dem Rendern daran.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from matplotlib import image as mpimg

from stintlab.reels.blender_export import export_scene
from stintlab.reels.chase3d import FOC, draw_label

REPO = Path(__file__).resolve().parents[2]
RENDER_SCRIPT = REPO / "stintlab" / "reels" / "blender_render.py"
DEFAULT_CAR = "assets/models/f1_2026_concept_polygon_model.glb"
QUALITY = {"preview": {"samples": 16, "scale": 0.5}, "final": {"samples": 64, "scale": 1.0}}
HALF_W = 0.5625
CREDIT = ('Car model: „F1 2026 concept (polygon model)" by Qvist_designs (https://skfb.ly/pIGZP), '
          "CC BY 4.0, modified (recoloured)")
LABEL_ANCHOR_M = 1.2        # Namensschild hängt so hoch über dem Auto (m)


def format_duration(seconds: float) -> str:
    s = int(round(seconds))
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    if h:
        return f"{h} h {m} min {sec} s"
    return f"{m} min {sec} s" if m else f"{sec} s"


def find_blender(reel: dict | None = None) -> str:
    """Blender suchen: blender_exe im Reel, Umgebungsvariable BLENDER_EXE, PATH, übliche Windows-Ordner."""
    cands = [(reel or {}).get("blender_exe"), os.environ.get("BLENDER_EXE"), shutil.which("blender")]
    cands += sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender *\blender.exe"), reverse=True)
    for c in cands:
        if c and Path(c).exists():
            return str(c)
    raise FileNotFoundError(
        "Blender nicht gefunden. Setze in der post.toml beim Reel blender_exe = \"C:/Program Files/Blender "
        "Foundation/Blender 5.2/blender.exe\" oder die Umgebungsvariable BLENDER_EXE.")


class _View:
    """Blender-Kamera eines Bildes in den Bildkoordinaten von chase3d (x ±0.5625, y ±1) – für die Namensschilder."""

    def __init__(self, C, F):
        self.C = np.asarray(C, float)
        self.f = np.asarray(F, float) / np.linalg.norm(F)
        r = np.cross(self.f, [0, 0, 1.0])
        self.r = r / np.linalg.norm(r)
        self.u = np.cross(self.r, self.f)

    def proj(self, q) -> tuple[float, float, float]:
        v = np.asarray(q, float) - self.C
        zc = float(v @ self.f)
        if zc < 1e-6:
            return 0.0, 0.0, zc
        return FOC * float(v @ self.r) / zc, FOC * float(v @ self.u) / zc, zc


class BlenderFrames:
    """Vorgerenderte Blender-Bilder für einzelne Zeitabschnitte einer Szene (jeder gleichmäßig mit fps)."""

    def __init__(self, scene, segments: list[np.ndarray], fps: int, work: Path, car: str | None, quality: str,
                 reel: dict):
        self.scene, self.fps, self.work, self.car, self.quality, self.reel = scene, fps, Path(work), car, quality, reel
        self.segments = []
        for ts in segments:
            ts = np.asarray(ts, float)
            if len(ts) >= 2:
                self.segments.append(ts)
        self._cache: dict[tuple[int, int], np.ndarray] = {}
        self._views: dict[int, dict] = {}

    # ── Rendern ──────────────────────────────────────────────────────────────────────────────────
    def render(self) -> None:
        blender = find_blender(self.reel)
        q = QUALITY[self.quality]
        self.work.mkdir(parents=True, exist_ok=True)
        script_hash = hashlib.sha1(RENDER_SCRIPT.read_bytes()).hexdigest()
        for k, seg in enumerate(self.segments):
            jpath, folder = self.work / f"seg{k}.json", self.work / f"seg{k}"
            export_scene(self.scene, float(seg[0]), float(seg[-1]), jpath, fps=self.fps, times=seg)
            key = hashlib.sha1(jpath.read_bytes() + json.dumps([q, self.car, script_hash]).encode()).hexdigest()
            marker = self.work / f"seg{k}.done"
            have = len(list(folder.glob("frame_*.png"))) if folder.exists() else 0
            if marker.exists() and marker.read_text() == key and have == len(seg):
                print(f"  Blender-Anfang Abschnitt {k + 1}/{len(self.segments)}: aus dem Zwischenspeicher")
                continue
            if folder.exists():
                shutil.rmtree(folder)
            marker.unlink(missing_ok=True)
            cmd = [blender, "--background", "--python", str(RENDER_SCRIPT), "--", str(jpath), str(folder),
                   "--samples", str(q["samples"]), "--scale", str(q["scale"])]
            if self.car:
                cmd += ["--car", str(Path(self.car).resolve())]
            print(f"  Blender-Anfang Abschnitt {k + 1}/{len(self.segments)}: {len(seg)} Bilder …", flush=True)
            t0 = time.perf_counter()
            res = subprocess.run(cmd, cwd=str(REPO))
            got = len(list(folder.glob("frame_*.png"))) if folder.exists() else 0
            if res.returncode != 0 or got != len(seg):
                raise RuntimeError(f"Blender-Render fehlgeschlagen ({got}/{len(seg)} Bilder, Code {res.returncode})")
            marker.write_text(key)
            print(f"  → fertig in {format_duration(time.perf_counter() - t0)}", flush=True)

    # ── Abruf ────────────────────────────────────────────────────────────────────────────────────
    def _locate(self, t: float) -> tuple[int, int] | None:
        tol = 0.5 / self.fps + 1e-9
        for k, ts in enumerate(self.segments):
            if ts[0] - tol <= t <= ts[-1] + tol:
                i = int(np.argmin(np.abs(ts - t)))
                if abs(ts[i] - t) <= tol:
                    return k, i
        return None

    def _view_data(self, k: int) -> dict:
        if k not in self._views:
            d = json.loads((self.work / f"seg{k}.json").read_text(encoding="utf-8"))
            fr = d["frames"]
            self._views[k] = {"C": np.array(fr["camera"]["pos"]), "F": np.array(fr["camera"]["forward"]),
                              "cars": {c: np.array(v["pos"]) for c, v in fr["cars"].items()}}
        return self._views[k]

    def image(self, t: float) -> np.ndarray | None:
        loc = self._locate(t)
        if loc is None:
            return None
        if loc not in self._cache:
            if len(self._cache) > 6:
                self._cache.pop(next(iter(self._cache)))
            k, i = loc
            self._cache[loc] = mpimg.imread(str(self.work / f"seg{k}" / f"frame_{i + 1:04d}.png"))
        return self._cache[loc]

    def draw(self, ax, t: float) -> float | None:
        """Bild + Namensschilder auf ax; Rückgabe wie chase3d.draw_scene (laufender Abstand) oder None, wenn für
        dieses t kein Blender-Bild existiert (dann zeichnet matplotlib wie früher)."""
        img = self.image(t)
        if img is None:
            return None
        sc = self.scene
        k, i = self._locate(t)
        vd = self._view_data(k)
        view = _View(vd["C"][i], vd["F"][i])
        ax.clear()
        ax.axis("off")
        ax.imshow(img, extent=(-HALF_W, HALF_W, -1.0, 1.0), aspect="auto", interpolation="nearest", zorder=-3)
        ax.set_xlim(-HALF_W, HALF_W)
        ax.set_ylim(-1.0, 1.0)
        pos = {d: vd["cars"][d][i] for d in (sc.a, sc.b)}
        scr = {d: view.proj(pos[d] + [0, 0, LABEL_ANCHOR_M]) for d in pos}
        beside = sc.separation(t) > 1.0
        for n, d in enumerate((sc.a, sc.b)):
            x, y, depth = scr[d]
            if depth <= 1.0:
                continue
            other = sc.b if d == sc.a else sc.a
            is_left = x < scr[other][0]
            draw_label(ax, sc.col[d], d, x, y, 7 + 2 * n, label_side=-1 if (beside and is_left) else 1)
        return sc.gap(t)


def attach_blender_opener(scene, reel: dict, segments: list[np.ndarray], out_path: Path, fps: int = 60) -> bool:
    """Von den Reel-Funktionen direkt nach prepare() aufgerufen. Gibt True zurück, wenn der Blender-Anfang aktiv ist.
    segments: die Zeiten (Sekunden ab t0), die das Reel mit draw_scene zeichnet, je Abschnitt eine Liste."""
    mode = reel.get("opener", "matplotlib")
    if mode not in ("matplotlib", "blender"):
        raise ValueError('opener muss "matplotlib" oder "blender" sein')
    if mode == "matplotlib":
        return False
    quality = reel.get("opener_quality", "final")
    if quality not in QUALITY:
        raise ValueError('opener_quality muss "final" oder "preview" sein')
    car = reel.get("opener_car", DEFAULT_CAR)
    if car and not (REPO / car).exists() and not Path(car).exists():
        print(f"⚠ Auto-Modell {car} nicht gefunden – Blender nimmt das Platzhalter-Auto (keine Credit-Pflicht)")
        car = None
    elif car and not Path(car).is_absolute():
        car = str(REPO / car)
    t0 = time.perf_counter()
    frames = BlenderFrames(scene, segments, fps, Path(out_path).parent / "_blender" / Path(out_path).stem, car,
                           quality, reel)
    print(f"… rendere den 3D-Anfang mit Blender ({quality})")
    try:
        frames.render()
    except (FileNotFoundError, RuntimeError) as exc:       # nie das ganze Wochenende daran scheitern lassen
        print(f"⚠ Blender-Anfang nicht möglich ({exc}) – dieses Reel bekommt das alte 3D-Bild (kein Modell, keine Credit-Pflicht)")
        return False
    scene.blender = frames
    print(f"✓ 3D-Anfang aus Blender ({format_duration(time.perf_counter() - t0)})")
    if car and "f1_2026_concept" in Path(car).name:
        print("⚠ Caption-Pflicht (CC BY 4.0, Link muss dabei sein):\n  " + CREDIT)
    return True
