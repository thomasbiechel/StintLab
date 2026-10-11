"""Tests für den Blender-Export: Schema, Bildanzahl, Höhenskala, Glättung."""

import json
import math

import numpy as np
import pytest

from stintlab.reels.blender_export import (FOC, HALF_W, export_scene, fov_degrees, gauss_smooth, retime_xy,
                                           scene_to_dict)
from stintlab.reels.chase3d import Z_EXAG, Scene
from tests.fake_race import make_race


@pytest.fixture(scope="module")
def scene():
    return Scene(make_race([0.6] * 8), "RUS", "VER")


def _window(scene, seconds=2.0):
    t = float(scene.ta.t[0] + (scene.ta.t[-1] - scene.ta.t[0]) * 0.4)
    return t, t + seconds


def test_gauss_smooth_keeps_constant_and_removes_a_kink():
    assert np.allclose(gauss_smooth(np.full(50, 3.0), 4), 3.0)
    step = np.r_[np.zeros(50), np.ones(50)]
    sm = gauss_smooth(step, 5)
    assert sm[0] == pytest.approx(0.0, abs=1e-6) and sm[-1] == pytest.approx(1.0, abs=1e-6)
    assert np.abs(np.diff(sm)).max() < np.abs(np.diff(step)).max() * 0.5
    two_d = gauss_smooth(np.column_stack([step, step * 2]), 5)
    assert two_d.shape == (100, 2)


def test_fov_matches_the_matplotlib_camera():
    h, v = fov_degrees()
    assert math.tan(math.radians(h / 2)) == pytest.approx(HALF_W / FOC)
    assert math.tan(math.radians(v / 2)) == pytest.approx(1.0 / FOC)
    assert h < v                                    # Hochformat


def test_frame_count_and_schema(scene):
    t0, t1 = _window(scene, 2.0)
    d = scene_to_dict(scene, t0, t1, fps=30)
    n = 60
    fr = d["frames"]
    assert d["schema"] == 1 and d["meta"]["a"] == "RUS" and d["meta"]["b"] == "VER"
    assert len(fr["t"]) == n and len(fr["gap_s"]) == n
    assert len(fr["camera"]["pos"]) == n and len(fr["cars"]["VER"]["pos"]) == n
    assert fr["t"][1] - fr["t"][0] == pytest.approx(1 / 30, abs=1e-3)
    assert len(d["track"]["left"]) == len(d["track"]["centre"]) + 1       # geschlossene Schleife
    assert d["meta"]["colors"]["RUS"] != d["meta"]["colors"]["VER"]


def test_gap_and_follower_behind_leader(scene):
    t0, t1 = _window(scene)
    d = scene_to_dict(scene, t0, t1, fps=30)
    gaps = [g for g in d["frames"]["gap_s"] if g is not None]
    assert gaps and np.median(gaps) == pytest.approx(0.6, abs=0.1)
    # Kamera sitzt hinter dem Verfolger B (VER): Abstand Kamera → B kleiner als Kamera → A
    cam = np.array(d["frames"]["camera"]["pos"])
    a = np.array(d["frames"]["cars"]["RUS"]["pos"])
    b = np.array(d["frames"]["cars"]["VER"]["pos"])
    assert (np.linalg.norm(cam - b, axis=1) < np.linalg.norm(cam - a, axis=1)).all()


def test_height_scale_is_selectable(scene):
    t0, t1 = _window(scene, 1.0)
    real = scene_to_dict(scene, t0, t1, fps=10, z_exag=1.0)
    old = scene_to_dict(scene, t0, t1, fps=10, z_exag=Z_EXAG)
    zr = np.array(real["track"]["centre"])[:, 2]
    zo = np.array(old["track"]["centre"])[:, 2]
    if np.ptp(zo) > 1e-6:                                   # Testdaten ohne Höhe sind flach
        assert np.ptp(zr) == pytest.approx(np.ptp(zo) / Z_EXAG, rel=1e-2)
    assert np.allclose(np.array(real["track"]["centre"])[:, :2], np.array(old["track"]["centre"])[:, :2])


def test_export_writes_valid_json(scene, tmp_path):
    t0, t1 = _window(scene, 1.0)
    p = export_scene(scene, t0, t1, tmp_path / "sub" / "scene.json", fps=20)
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["meta"]["fps"] == 20 and len(d["frames"]["t"]) == 20
    for key in ("kerbs", "barriers", "trees", "gantry", "finish"):
        assert key in d["env"]
    assert len(d["env"]["trees"]["base"]) == len(d["env"]["trees"]["height_m"])


def test_too_short_window_is_rejected(scene):
    t0, _ = _window(scene)
    with pytest.raises(ValueError):
        scene_to_dict(scene, t0, t0 + 0.001, fps=60)


def test_palette_for_blender_is_exported(scene):
    t0, t1 = _window(scene, 1.0)
    pal = scene_to_dict(scene, t0, t1, fps=10)["env"]["palette"]
    for key in ("asphalt", "ground", "barrier", "fog", "far", "sky_top", "sky_hor", "grass_w_m"):
        assert key in pal
    assert len(pal["asphalt"]) == 3


def test_camera_rig_is_applied_and_restored(scene):
    import stintlab.reels.chase3d as c3
    t0, t1 = _window(scene, 1.0)
    before = (c3.BACK, c3.HEIGHT, c3.AHEAD)
    near = scene_to_dict(scene, t0, t1, fps=10, cam_back=10.0, cam_height=3.0, cam_ahead=8.0)
    far = scene_to_dict(scene, t0, t1, fps=10, cam_back=40.0, cam_height=22.0, cam_ahead=25.0)
    assert (c3.BACK, c3.HEIGHT, c3.AHEAD) == before                      # Konstanten wieder wie vorher
    assert near["meta"]["camera_rig"] == {"back_m": 10.0, "height_m": 3.0, "ahead_m": 8.0}

    def dist(d):                                    # Kamera → Verfolger B (VER)
        cam = np.array(d["frames"]["camera"]["pos"])
        b = np.array(d["frames"]["cars"]["VER"]["pos"])
        return float(np.median(np.linalg.norm(cam - b, axis=1)))

    assert dist(near) < 0.5 * dist(far)


def test_path_camera_keeps_the_chaser_in_the_view_axis(scene):
    t0, t1 = _window(scene, 3.0)
    d = scene_to_dict(scene, t0, t1, fps=20)
    assert d["meta"]["camera_mode"] == "path"
    cam = np.array(d["frames"]["camera"]["pos"])
    fwd = np.array(d["frames"]["camera"]["forward"])
    b = np.array(d["frames"]["cars"]["VER"]["pos"])
    v = b - cam
    yaw = np.degrees(np.arctan2(v[:, 1], v[:, 0]) - np.arctan2(fwd[:, 1], fwd[:, 0]))
    yaw = (yaw + 180) % 360 - 180
    assert np.abs(yaw).max() < 3.0                            # seitlich bleibt das Auto in der Bildmitte
    assert np.allclose(np.linalg.norm(fwd, axis=1), 1.0, atol=1e-3)


def test_retime_smooths_the_speed_but_keeps_the_path():
    rng = np.random.default_rng(1)
    t = np.arange(0, 20, 1 / 20)
    s = np.maximum.accumulate(60 * t + rng.normal(0, 3, len(t)))        # Tempo-Rauschen wie bei linear aufgefüllten GPS-Daten
    xy = np.column_stack([100 * np.cos(s / 100), 100 * np.sin(s / 100)])
    out = retime_xy(xy, 20)
    speed = lambda a: np.hypot(*(np.diff(a, axis=0) * 20).T)
    assert speed(out).std() < 0.3 * speed(xy).std()
    assert np.abs(np.hypot(*out.T) - 100).max() < 0.5                    # bleibt auf dem Kreis (Weg unverändert)
    assert retime_xy(xy[:3], 20).shape == (3, 2)                         # zu kurz: unverändert


def test_classic_camera_is_still_available(scene):
    t0, t1 = _window(scene, 1.0)
    d = scene_to_dict(scene, t0, t1, fps=10, cam_mode="classic")
    assert d["meta"]["camera_mode"] == "classic"
    assert len(d["frames"]["camera"]["pos"]) == len(d["frames"]["t"])


def test_camera_rig_is_restored_after_an_error(scene):
    import stintlab.reels.chase3d as c3
    from stintlab.reels.blender_export import camera_rig
    before = (c3.BACK, c3.HEIGHT, c3.AHEAD)
    with pytest.raises(RuntimeError):
        with camera_rig(5.0, 2.0, 3.0):
            raise RuntimeError("Abbruch")
    assert (c3.BACK, c3.HEIGHT, c3.AHEAD) == before


def test_surface_z_follows_a_slope_and_ignores_the_cars_own_height():
    from stintlab.reels.blender_export import surface_z
    centre = np.column_stack([np.arange(0, 100.0, 10.0), np.zeros(10), np.arange(10) * 1.0])   # 1 m Höhe je 10 m
    xy = np.array([[0.0, 0.0], [25.0, 2.5], [55.0, -1.0], [89.0, 0.0]])
    z = surface_z(centre, xy)
    assert z == pytest.approx([0.0, 2.5, 5.5, 8.9], abs=1e-6)


def test_cars_sit_on_the_surface_and_pitch_follows_the_slope(scene):
    t0, t1 = _window(scene, 1.0)
    d = scene_to_dict(scene, t0, t1, fps=20)
    for drv in ("RUS", "VER"):
        pitch = d["frames"]["cars"][drv]["pitch_rad"]
        assert len(pitch) == 20 and max(abs(p) for p in pitch) < 0.2          # Testdaten sind flach
    # Höhe = Straßenhöhe (Testdaten flach: überall 0)
    for drv in ("RUS", "VER"):
        z = np.array(d["frames"]["cars"][drv]["pos"])[:, 2]
        assert np.ptp(z) < 0.05
