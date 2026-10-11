from pathlib import Path

from frames_to_mp4 import build_command


def test_command_has_framerate_and_pattern():
    cmd = build_command("ffmpeg", Path("out/spa"), 20, Path("out/spa.mp4"))
    assert cmd[cmd.index("-framerate") + 1] == "20"
    assert cmd[cmd.index("-i") + 1].endswith("frame_%04d.png")
    assert cmd[-1].endswith("spa.mp4")
