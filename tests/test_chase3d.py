"""Tests für die 3D-Verfolgerkamera: Projektion, Abstand und Bildausschnitt."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from stintlab.reels.chase3d import Camera, Scene, draw_scene
from tests.fake_race import T0, make_race


@pytest.fixture(scope="module")
def scene():
    return Scene(make_race([0.6] * 8), "RUS", "VER")


def _t(scene, lap=5, frac=0.5):
    e = scene.ta.t  # beliebiger Zeitpunkt mitten im Rennen
    return float(e[0] + (e[-1] - e[0]) * (lap - 0.5 + frac) / 9)


def test_both_cars_are_in_frame_and_follower_is_nearer(scene):
    t = _t(scene)
    cam = Camera(scene, t)
    (pa, _), (pb, _) = scene.pos("RUS", t), scene.pos("VER", t)
    xa, ya, za = cam.proj(pa)
    xb, yb, zb = cam.proj(pb)
    for x, y in ((xa, ya), (xb, yb)):
        assert abs(x[0]) < 0.56 and abs(y[0]) < 1.0
    assert zb[0] < za[0]          # Kamera sitzt hinter dem Verfolger
    assert yb[0] < ya[0]          # der Führende ist weiter oben im Bild


def test_draw_scene_returns_the_known_gap(scene):
    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1])
    g = draw_scene(ax, scene, _t(scene))
    plt.close(fig)
    assert g == pytest.approx(0.6, abs=0.08)


def test_point_behind_camera_has_negative_depth(scene):
    t = _t(scene)
    cam = Camera(scene, t)
    behind = cam.C - cam.f * 10
    assert cam.proj(behind)[2][0] < 0


def test_light_from_local_session_time(monkeypatch):
    from datetime import datetime, timezone
    import stintlab.reels.chase3d as c3
    monkeypatch.setattr(c3, "meeting_for", lambda key: {"gmt_offset": "04:00:00"})
    assert c3.light_for(1, datetime(2026, 9, 25, 13, 2, tzinfo=timezone.utc)) == "day"      # Baku Q3 17:02
    assert c3.light_for(1, datetime(2026, 9, 25, 14, 30, tzinfo=timezone.utc)) == "dusk"    # 18:30
    monkeypatch.setattr(c3, "meeting_for", lambda key: {"gmt_offset": "08:00:00"})
    assert c3.light_for(1, datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)) == "night"    # Singapur 20:00
    monkeypatch.setattr(c3, "meeting_for", lambda key: {"gmt_offset": "-08:00:00"})
    assert c3.light_for(1, datetime(2026, 11, 22, 6, 0, tzinfo=timezone.utc)) == "night"    # Las Vegas 22:00
    monkeypatch.setattr(c3, "meeting_for", lambda key: None)
    assert c3.light_for(1, datetime(2026, 9, 25, 13, 0, tzinfo=timezone.utc)) == "day"      # ohne Zeitzone: Tag


def test_rain_option_switches_light_and_rejects_non_bool():
    import pytest
    from stintlab.reels.chase3d import LIGHTS, Scene
    s = Scene.__new__(Scene)
    s.scenery, s.light, s.rain, s._env = "park", "day", False, None
    Scene.configure(s, {"rain": True})
    assert s.rain and s.light == "rain" and "rain" in LIGHTS
    s.light = "day"
    Scene.configure(s, {"rain": True, "light": "dusk"})      # ausdrückliches Licht gewinnt
    assert s.light == "dusk"
    with pytest.raises(ValueError):
        Scene.configure(s, {"rain": "yes"})


def test_rain_and_spray_draw_without_errors():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from stintlab.reels.chase3d import draw_rain, draw_spray

    class Cam:
        def proj(self, Q):
            Q = np.atleast_2d(Q)
            return Q[:, 0] / 50, Q[:, 2] / 50, np.full(len(Q), 20.0)

    fig, ax = plt.subplots()
    draw_rain(ax, 12.3)
    draw_spray(ax, Cam(), np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]), 12.3, 5)
    assert len(ax.collections) == 2
    plt.close(fig)
