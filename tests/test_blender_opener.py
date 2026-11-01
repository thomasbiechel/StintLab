"""Tests für den Blender-Anfang (ohne Blender): Zeitzuordnung, Zeichnen mit Namensschildern, Rückfall, Prüfungen."""

import json

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import image as mpimg  # noqa: E402

from stintlab.reels.blender_opener import BlenderFrames, attach_blender_opener, find_blender  # noqa: E402


class FakeScene:
    a, b = "RUS", "VER"
    col = {"RUS": "#00d2be", "VER": "#3671c6"}

    def separation(self, t):
        return 0.0

    def gap(self, t):
        return 0.6


@pytest.fixture
def frames(tmp_path):
    ts = np.array([10.0, 10.01, 10.03, 10.06])                      # ungleichmäßig (Zeitlupe)
    n = len(ts)
    cars = {"RUS": [[0.0, 40.0, 0.0]] * n, "VER": [[0.0, 20.0, 0.0]] * n}
    cam = {"pos": [[0.0, 0.0, 5.0]] * n, "forward": [[0.0, 1.0, -0.1]] * n}
    (tmp_path / "seg0.json").write_text(json.dumps({"frames": {"camera": cam, "cars": {d: {"pos": p} for d, p in cars.items()}}}))
    (tmp_path / "seg0").mkdir()
    for i in range(n):
        mpimg.imsave(str(tmp_path / "seg0" / f"frame_{i + 1:04d}.png"), np.full((8, 4, 3), 0.5, dtype=np.float32))
    return BlenderFrames(FakeScene(), [ts], 60, tmp_path, None, "preview", {})


def test_locate_matches_exact_and_nearby_times_only(frames):
    assert frames._locate(10.03) == (0, 2)
    assert frames._locate(10.0605) == (0, 3)                      # innerhalb eines halben Bildes
    assert frames._locate(11.0) is None
    assert frames._locate(9.0) is None


def test_draw_puts_the_image_and_both_name_tags_on_the_axes(frames):
    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1])
    gap = frames.draw(ax, 10.03)
    assert gap == 0.6
    assert len(ax.images) == 1
    assert {t.get_text() for t in ax.texts} == {"RUS", "VER"}
    plt.close(fig)


def test_draw_returns_none_without_an_image_so_matplotlib_takes_over(frames):
    fig = plt.figure()
    assert frames.draw(fig.add_axes([0, 0, 1, 1]), 99.0) is None
    plt.close(fig)


def test_default_opener_is_off_and_invalid_values_are_rejected(tmp_path):
    assert attach_blender_opener(FakeScene(), {}, [np.arange(3.0)], tmp_path / "r.mp4") is False
    with pytest.raises(ValueError):
        attach_blender_opener(FakeScene(), {"opener": "unity"}, [np.arange(3.0)], tmp_path / "r.mp4")
    with pytest.raises(ValueError):
        attach_blender_opener(FakeScene(), {"opener": "blender", "opener_quality": "ultra"}, [np.arange(3.0)],
                              tmp_path / "r.mp4")


def test_find_blender_uses_the_reel_setting_and_explains_when_missing(tmp_path, monkeypatch):
    exe = tmp_path / "blender.exe"
    exe.write_text("")
    assert find_blender({"blender_exe": str(exe)}) == str(exe)
    monkeypatch.delenv("BLENDER_EXE", raising=False)
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.setattr("glob.glob", lambda _: [])
    with pytest.raises(FileNotFoundError, match="blender_exe"):
        find_blender({})


def test_missing_blender_falls_back_to_matplotlib_instead_of_failing(tmp_path, monkeypatch):
    monkeypatch.delenv("BLENDER_EXE", raising=False)
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.setattr("glob.glob", lambda _: [])
    scene = FakeScene()
    scene.blender = None
    ok = attach_blender_opener(scene, {"opener": "blender", "opener_car": ""}, [np.arange(3.0)], tmp_path / "r.mp4")
    assert ok is False and scene.blender is None                  # Reel läuft mit dem alten 3D-Bild weiter
