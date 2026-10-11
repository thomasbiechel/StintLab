"""3D-Anfang eines Reels als scene.json für Blender exportieren.

    python make_scene_json.py posts/2026-monza/race-reel/post.toml
    python make_scene_json.py posts/2026-monza/race-reel/post.toml --reel 1 --out output/monza.json

Nimmt das Reel Nr. --reel (Standard 1) aus der post.toml, bereitet es wie make_post.py vor und
schreibt den Zeitraum des 3D-Anfangs (open_times bzw. hook_times) als JSON.
Danach (Blender, siehe stintlab/reels/blender_render.py):

    blender.exe --background --python stintlab\\reels\\blender_render.py -- scene.json out\\test --still 20
"""
from __future__ import annotations

import argparse
import importlib
import sys
import tomllib
from pathlib import Path

from stintlab.reels.blender_export import CAM_AHEAD, CAM_BACK, CAM_HEIGHT, export_scene
from stintlab.session import load_session


def times_of(prep: dict):
    """Zeitpunkte des 3D-Anfangs aus dem vorbereiteten Reel (race_story, gain_loss: open_times;
    comeback: hook_times, danach das Manöver)."""
    for key in ("open_times", "hook_times"):
        t = prep.get(key)
        if t is not None and len(t) > 1:
            return t
    raise ValueError("Dieses Reel hat keinen 3D-Anfang (weder open_times noch hook_times)")


def export_reel(data: dict, reel: dict, out: Path, fps: int = 60, z_exag: float = 1.0, **cam) -> Path:
    """Reel vorbereiten und den 3D-Anfang exportieren. data wie von load_session."""
    module = importlib.import_module(f"stintlab.reels.{reel['analysis']}")
    if not hasattr(module, "prepare"):
        raise ValueError(f"stintlab.reels.{reel['analysis']} hat kein prepare()")
    prep = module.prepare(data, reel)
    scene = prep.get("scene")
    if scene is None:
        raise ValueError("Dieses Reel hat keine 3D-Szene")
    t = times_of(prep)
    return export_scene(scene, float(t[0]), float(t[-1]) + 1.0 / fps, out, fps=fps, z_exag=z_exag, **cam)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("config", help="Pfad zur post.toml")
    ap.add_argument("--reel", type=int, default=1, help="Nummer des Reels in der post.toml (ab 1)")
    ap.add_argument("--out", default="scene.json")
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--z-exag", type=float, default=1.0, help="Höhen-Überhöhung (1.0 = echt, 1.5 = altes Bild)")
    ap.add_argument("--cam-back", type=float, default=CAM_BACK, help=f"Meter hinter dem Verfolger (Standard {CAM_BACK})")
    ap.add_argument("--cam-height", type=float, default=CAM_HEIGHT, help=f"Kamerahöhe in m (Standard {CAM_HEIGHT})")
    ap.add_argument("--cam-ahead", type=float, default=CAM_AHEAD, help=f"Blickziel vor den Autos in m (Standard {CAM_AHEAD})")
    args = ap.parse_args()

    config = tomllib.loads(Path(args.config).read_text(encoding="utf-8"))
    reels = config.get("reels", [])
    if not 1 <= args.reel <= len(reels):
        sys.exit(f"Reel {args.reel} gibt es nicht ({len(reels)} Reels in der post.toml)")
    reel = reels[args.reel - 1]
    session = config["session"]
    data = load_session(session["meeting_key"], reel.get("session", session["type"]))
    path = export_reel(data, reel, Path(args.out), fps=args.fps, z_exag=args.z_exag, cam_back=args.cam_back,
                       cam_height=args.cam_height, cam_ahead=args.cam_ahead)
    print(f"✓ {path}")


if __name__ == "__main__":
    main()
