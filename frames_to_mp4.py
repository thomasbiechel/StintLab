"""PNG-Folge aus Blender zu einem MP4 zusammensetzen.

    python frames_to_mp4.py output\\spa_lap --fps 20
    python frames_to_mp4.py output\\spa_lap --fps 60 --out output\\spa_lap.mp4

Der Ordner enthält frame_0001.png, frame_0002.png, … (so schreibt blender_render.py ohne --video
bzw. wenn Blender kein MP4 kann). --fps muss zu dem Wert passen, mit dem du make_scene_json.py
exportiert hast (Standard dort: 60).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def build_command(ffmpeg: str, folder: Path, fps: int, out: Path) -> list[str]:
    return [ffmpeg, "-y", "-framerate", str(fps), "-i", str(folder / "frame_%04d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-movflags", "+faststart", str(out)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder", help="Ordner mit frame_0001.png …")
    ap.add_argument("--fps", type=int, required=True, help="Bildrate des Exports (make_scene_json --fps)")
    ap.add_argument("--out", help="Ziel (Standard: <Ordner>.mp4)")
    args = ap.parse_args()
    folder = Path(args.folder)
    if not (folder / "frame_0001.png").exists():
        sys.exit(f"In {folder} liegt kein frame_0001.png")
    out = Path(args.out) if args.out else folder.with_suffix(".mp4")
    import imageio_ffmpeg
    subprocess.run(build_command(imageio_ffmpeg.get_ffmpeg_exe(), folder, args.fps, out), check=True)
    print(f"✓ {out}")


if __name__ == "__main__":
    main()
