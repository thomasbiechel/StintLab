"""Smoke-Test für blender_render.py – nur mit dem bpy-Modul (pip install bpy), sonst übersprungen.
Baut die Szene aus einem Test-Export und prüft Objekte, Kamera und Schlüsselbilder; rendert nicht."""

import json

import numpy as np
import pytest

pytest.importorskip("bpy")

import bpy  # noqa: E402

from stintlab.reels import blender_render as br  # noqa: E402
from stintlab.reels.blender_export import scene_to_dict  # noqa: E402
from stintlab.reels.chase3d import Scene  # noqa: E402
from tests.fake_race import make_race  # noqa: E402


@pytest.fixture(scope="module")
def data():
    s = Scene(make_race([0.6] * 8), "RUS", "VER")
    s.scenery = "city"
    s._env = None
    t0 = float(s.ta.t[0] + (s.ta.t[-1] - s.ta.t[0]) * 0.4)
    return scene_to_dict(s, t0, t0 + 1.0, fps=12)


def test_scene_is_built_with_cars_camera_and_keyframes(data):
    args = br.parse_args(["x.json", "out", "--scale", "0.25"])
    cars, cam = br.build_scene(data, args)
    sc = bpy.context.scene
    assert set(cars) == {"RUS", "VER"} and sc.camera is cam
    assert (sc.frame_start, sc.frame_end) == (1, 12)
    assert sc.render.resolution_x == 270 and sc.render.resolution_y == 480
    names = {o.name for o in bpy.data.objects}
    assert {"Strecke", "Häuser", "Randsteine", "Horizont"} <= names
    sc.frame_set(6)
    assert cam.matrix_world.translation.z > cars["VER"].matrix_world.translation.z   # Kamera über dem Auto


def test_unknown_schema_is_rejected(data):
    bad = dict(data, schema=99)
    with pytest.raises(ValueError):
        br.build_scene(bad, br.parse_args(["x.json", "out"]))


def test_light_presets_cover_all_chase3d_lights():
    from stintlab.reels.chase3d import LIGHTS
    assert set(LIGHTS) <= set(br.LIGHT_PRESETS)


def test_placeholder_car_has_the_expected_parts_and_scale(data):
    args = br.parse_args(["x.json", "out"])
    cars, _ = br.build_scene(data, args)
    assert tuple(cars["RUS"].scale) == (br.PLACEHOLDER_SCALE,) * 3
    parts = [o.name for o in bpy.data.objects if o.parent == cars["VER"]]
    for needle in ("Heckflügel", "Halo", "Rücklicht", "Rad vorn 1", "Rad hinten -1", "Nase", "Frontflügel"):
        assert any(needle in n for n in parts), needle


def test_car_scale_and_fov_options(data):
    args = br.parse_args(["x.json", "out", "--car-scale", "2", "--fov", "40"])
    cars, cam = br.build_scene(data, args)
    assert tuple(cars["RUS"].scale) == (2.0, 2.0, 2.0)
    import math
    assert cam.data.lens == pytest.approx(cam.data.sensor_height / (2 * math.tan(math.radians(20))), rel=1e-3)
    assert br.parse_args(["x.json", "out"]).fov == br.FOV_V


# ── aufbereitetes Modell (F1 2026 concept): reine Geometrie-Logik, ohne die große Datei ────────────────

def _box(cx, cy, cz, dx, dy, dz):
    return (cx - dx / 2, cx + dx / 2, cy - dy / 2, cy + dy / 2, cz - dz / 2, cz + dz / 2)


def _fake_boxes():
    boxes = [_box(1.7, 0.75, 0.36, 0.72, 0.34, 0.72), _box(1.7, -0.75, 0.36, 0.72, 0.34, 0.72),      # Reifen vorn
             _box(-1.7, 0.75, 0.36, 0.72, 0.40, 0.72), _box(-1.7, -0.75, 0.36, 0.72, 0.40, 0.72),   # hinten
             _box(0.0, 0.0, 0.5, 3.0, 0.6, 0.6),                    # 4 Karosserie
             _box(1.7, 0.75, 0.36, 0.4, 0.3, 0.4),                  # 5 Felge vorn links
             _box(1.7, 0.60, 0.36, 0.1, 0.1, 0.1),                  # 6 Nabe/Bremse ragt zur Mitte hin über den Reifen
             _box(1.2, 0.6, 0.4, 1.4, 0.05, 0.05)]                  # 7 Querlenker ragt aus dem Rad heraus
    return boxes


def test_wheel_parts_are_found_by_geometry():
    cls = br.classify_wheel_parts(_fake_boxes())
    assert sorted(cls["tyres"]) == [0, 1, 2, 3]
    assert set(cls["members"][0]) == {5, 6}                # Felge und Nabe gehören zum Rad …
    assert 7 not in {i for m in cls["members"].values() for i in m}    # … der Querlenker nicht
    assert 4 not in {i for m in cls["members"].values() for i in m}    # und die Karosserie auch nicht


def test_wrong_model_is_rejected_when_there_are_not_four_tyres():
    with pytest.raises(ValueError):
        br.classify_wheel_parts(_fake_boxes()[:3] + [_fake_boxes()[4]])


def test_carbon_only_at_floor_and_wings():
    import numpy as np
    c = np.array([[0.0, 0.0, 0.05], [0.0, 0.0, 0.6], [2.5, 0.0, 0.4], [-2.2, 0.0, 0.9], [-1.0, 0.0, 0.7]])
    assert br.carbon_faces(c).tolist() == [True, False, True, True, False]


def test_wheels_roll_with_the_distance_driven(data):
    cars, cam = br.build_scene(data, br.parse_args(["x.json", "out"]))
    wheel = bpy.data.objects.new("Testrad", None)
    br.link(wheel)
    br.CAR_WHEELS.clear()
    br.CAR_WHEELS["VER"] = [(wheel, 0.36)]
    br.key_motion(data, cars, cam, None)
    br.CAR_WHEELS.clear()
    sc = bpy.context.scene
    sc.frame_set(1)
    a0 = wheel.rotation_euler[1]
    sc.frame_set(12)
    assert a0 == pytest.approx(0.0) and wheel.rotation_euler[1] > 1.0


def test_other_models_are_not_touched_by_the_preparation():
    assert br.CAR_MODEL_MATCH == "f1_2026_concept"


def test_relative_car_path_is_made_absolute(data, monkeypatch, tmp_path):
    seen = {}
    monkeypatch.chdir(tmp_path)
    (tmp_path / "f1_2026_concept_x.glb").write_bytes(b"")
    monkeypatch.setattr(br, "build_model_cars", lambda d, path, *a: seen.setdefault("p", path) and {})
    br.build_cars(data, "f1_2026_concept_x.glb", None, 0.0)
    assert seen["p"].is_absolute() and seen["p"].parent == tmp_path.resolve()


# ── Umgebung: Material, Bäume, Leitplanken, Laternen, Dunst ───────────────────────────────────────

def test_environment_objects_exist(data):
    br.build_scene(data, br.parse_args(["x.json", "out"]))
    names = {o.name for o in bpy.data.objects}
    assert {"Strecke", "Rand links", "Rand rechts", "Horizont", "Häuser", "Planke links", "Planke rechts"} <= names   # Teststadt: Häuser statt Bäume
    assert "Laternenmasten" not in names                                  # nur nachts


def test_terrain_follows_track_height(data):
    br.build_scene(data, br.parse_args(["x.json", "out"]))
    assert "Gelände" in {o.name for o in bpy.data.objects}
    T = br.terrain_for(data)
    c = np.array(data["track"]["centre"])
    h = T.height(c[::25, :2], hills=False)
    assert np.abs(h - c[::25, 2]).max() < 1.5                              # Gelände liegt an der Strecke an
    far = np.array([[c[:, 0].max() + 3000.0, c[:, 1].max() + 3000.0]])
    assert T.height(far, hills=False)[0] == pytest.approx(T.base, abs=0.05)  # weit weg: Grundhöhe


def test_terrain_slopes_with_hilly_track(data):
    hill = json.loads(json.dumps(data))
    n = len(hill["track"]["centre"])
    for k in ("centre", "left", "right"):
        for i, p in enumerate(hill["track"][k]):
            p[2] = 20.0 * np.sin(2 * np.pi * (i % n) / n * 3)
    br.build_scene(hill, br.parse_args(["x.json", "out"]))
    T = br.terrain_for(hill)
    c = np.array(hill["track"]["centre"])
    assert np.ptp(T.height(c[::20, :2], hills=False)) > 25.0


def test_format_duration():
    assert br.format_duration(5.4) == "5 s"
    assert br.format_duration(123.4) == "2 min 3 s"
    assert br.format_duration(3725) == "1 h 2 min 5 s"


def test_lamps_only_at_night(data):
    night = dict(data, meta=dict(data["meta"], light="night"))
    br.build_scene(night, br.parse_args(["x.json", "out"]))
    names = {o.name for o in bpy.data.objects}
    assert {"Laternenmasten", "Laternenköpfe"} <= names


def test_track_has_uv_in_meters(data):
    br.build_scene(data, br.parse_args(["x.json", "out"]))
    me = bpy.data.objects["Strecke"].data
    uv = [tuple(l.uv) for l in me.uv_layers["UVMap"].data]
    assert max(u for u, _ in uv) == pytest.approx(data["track"]["width_m"], abs=1e-6)
    assert max(v for _, v in uv) > 100                                     # Meter längs, nicht 0–1


def test_ground_materials_are_hazed(data):
    br.build_scene(data, br.parse_args(["x.json", "out"]))
    for name in ("Asphalt", "Boden", "Ferne"):
        nodes = {n.bl_idname for n in bpy.data.materials[name].node_tree.nodes}
        assert {"ShaderNodeMixShader", "ShaderNodeCameraData"} <= nodes, name


def test_tree_geometry_is_valid_and_varied():
    import numpy as np
    base = np.zeros((40, 3))
    base[:, 0] = np.arange(40) * 10.0
    v, f, c = br.tree_geometry(base, np.full(40, 14.0), np.tile([0.2, 0.4, 0.15], (40, 1)))
    assert f.max() < len(v) and len(c) == len(v) and (c >= 0).all() and (c <= 1).all()
    assert v[:, 2].min() >= -0.01 and v[:, 2].max() < 14.0 * 1.05          # nichts unter dem Boden, nicht höher als der Baum
    assert np.unique(np.round(v[:, 2], 1)).size > 20                       # Laub- und Nadelbäume gemischt


def test_extra_forest_keeps_away_from_the_track(data):
    import numpy as np
    base = np.zeros((1, 3))
    xy, h, _ = br.extra_forest(data, base, np.array([[0.2, 0.4, 0.15]]), n=400)
    centre = np.array(data["track"]["centre"])[:, :2]
    nearest = np.min(np.linalg.norm(xy[:, None, :2] - centre[None, ::4], axis=2), axis=1)
    assert len(xy) > 50 and nearest.min() > 30.0 and (h >= 9).all()


def test_haze_density_follows_the_light_preset(data):
    day = br.haze_for(data)[1]
    rain = br.haze_for(dict(data, meta=dict(data["meta"], light="rain")))[1]
    assert rain > day > 0


def test_window_pattern_is_in_the_facade_material():
    mat = br.facade_material({"window_lit": 0.3}, 0.3)
    kinds = {n.bl_idname for n in mat.node_tree.nodes}
    assert "ShaderNodeTexWhiteNoise" in kinds and "ShaderNodeVertexColor" in kinds
