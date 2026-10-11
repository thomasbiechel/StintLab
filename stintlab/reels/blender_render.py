"""Blender-Render: baut aus der JSON von blender_export.py die 3D-Szene und rendert sie.

LÄUFT NUR IN BLENDER (importiert bpy). Aufruf, alles nach dem „--“ gehört diesem Skript:

  blender --background --python stintlab/reels/blender_render.py -- ^
      scene.json out/chase --video            (ganzes Video, out/chase.mp4)
  blender --background --python stintlab/reels/blender_render.py -- ^
      scene.json out/test --still 100         (ein Bild: Index 100 → out/test.png)

Optionen:
  --engine eevee|cycles   Standard eevee (schnell, GPU). cycles = schöner, deutlich langsamer.
  --samples N             Qualität (EEVEE ~32–64, Cycles ~64–256)
  --scale 0.5             Auflösung verkleinern (Test!) – 1.0 = 1080×1920
  --still I               nur Bild I (0 = erstes) als PNG
  --frames A:B            nur Bilder A bis B−1
  --video                 MP4 (H.264) statt PNG-Folge
  --car datei.glb         eigenes Auto-Modell statt Platzhalter (siehe unten)
  --car-scale S           Maßstab der Autos (Standard 1.25 beim Platzhalter und dem aufbereiteten Modell, sonst 1.0)
  --car-decimate R        Anteil der Flächen des aufbereiteten Modells (Standard 0.35 ≈ 300 000 Flächen)
  --car-rebuild           Zwischenspeicher des aufbereiteten Modells neu erzeugen
  --car-yaw GRAD          Drehung, damit die Nase nach +x zeigt (Standard 0)
  --motion-blur 0|1       Bewegungsunschärfe (Standard 1)
  --fov GRAD              vertikaler Bildwinkel (Standard 46°; das alte matplotlib-Bild hatte 61°)
  --fog                   Dunst wie im alten Bild (experimentell, kann das Bild schwarz machen)

KOORDINATEN: wie im Export (Meter, z oben). Ein Auto zeigt lokal mit der Nase nach +x, Boden bei z = 0.

AUTO: Ohne --car ein Platzhalter aus einfachen Formen in der Teamfarbe (alle Teile eines Fahrers
gehören einem Empty, das bewegt wird). Mit --car wird die GLB importiert und an dieses Empty gehängt.
Heißt die Datei f1_2026_concept_polygon_model.glb (Qvist_designs, CC BY 4.0, https://skfb.ly/pIGZP), wird
sie aufbereitet: ausgerichtet, vereinfacht, Räder abgetrennt (drehen sich), Teamfarbe auf der Karosserie.
Das dauert beim ersten Mal ~1 Minute; danach liegt <modell>.prep1-d035.blend daneben (steht in der
.gitignore über *.blend). Andere Modelle werden unverändert importiert (Livery bleibt).
NAMENSNENNUNG (CC BY 4.0) nicht vergessen – siehe assets/CREDITS.md.

UMGEBUNG (automatisch aus den Streckendaten, ohne Handarbeit je Strecke): Asphalt mit Rennlinie und Randlinien,
Kiesbett, Rasen mit Mähstreifen und Feldern, Leitplanken, Laub- und Nadelbäume plus Zusatzwald, ferne Hügel,
Wolken, Dunst nach Entfernung; Städte mit Fensterfassaden; nachts Laternen und leuchtende Fenster.

Nicht enthalten (bleibt im bisherigen matplotlib-Teil): Hook-Text, Minimap, Abstandsband.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from pathlib import Path

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

PREVIEW_SAMPLES = 32
FOV_V = 46.0                 # enger als das alte Bild (61°): die Autos füllen mehr vom Hochformat
PLACEHOLDER_SCALE = 1.25     # etwas größer als echt – im Hochformat wirken Autos sonst klein
warnings.filterwarnings("ignore", message=".*use_nodes.*", category=DeprecationWarning)   # nur Hinweis auf Blender 6.0


# ── Farben ───────────────────────────────────────────────────────────────────

def srgb_to_linear(c):
    c = np.asarray(c, dtype=float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_rgb(c) -> np.ndarray:
    """"#rrggbb" oder (r, g, b) in 0–1 → sRGB-Array."""
    if isinstance(c, str):
        h = c.lstrip("#")
        if len(h) == 6:
            return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])
        raise ValueError(f"Farbe nicht lesbar: {c!r}")
    return np.asarray(c, dtype=float)[:3]


def rgba(c, a: float = 1.0) -> tuple:
    return (*srgb_to_linear(to_rgb(c)), a)


# ── kleine Helfer ────────────────────────────────────────────────────────────

def set_safe(obj, name: str, value) -> bool:
    """Eigenschaft setzen, wenn es sie in dieser Blender-Version gibt."""
    try:
        setattr(obj, name, value)
        return True
    except (AttributeError, TypeError, ValueError):
        return False


def inp(node, *names):
    for n in names:
        if n in node.inputs:
            return node.inputs[n]
    return None


def new_material(name: str):
    m = bpy.data.materials.new(name)
    set_safe(m, "use_nodes", True)       # ab Blender 6.0 entfällt use_nodes (immer an)
    return m


def set_specular(bsdf, level: float):
    """Glanz verringern: bei flachem Blick (Kamera knapp über dem Asphalt) spiegelt sonst jede
    Fläche den hellen Himmel (Fresnel) und wirkt weiß statt dunkel."""
    s = inp(bsdf, "Specular IOR Level", "Specular")
    if s is not None:
        s.default_value = level


def solid_material(name: str, color, roughness=0.5, metallic=0.0, emission=0.0, alpha=1.0, specular=0.15):
    m = new_material(name)
    bsdf = m.node_tree.nodes["Principled BSDF"]
    inp(bsdf, "Base Color").default_value = rgba(color)
    inp(bsdf, "Roughness").default_value = roughness
    set_specular(bsdf, specular)
    inp(bsdf, "Metallic").default_value = metallic
    if emission:
        e = inp(bsdf, "Emission Color", "Emission")
        if e is not None:
            e.default_value = rgba(color)
        s = inp(bsdf, "Emission Strength")
        if s is not None:
            s.default_value = emission
    if alpha < 1.0:
        a = inp(bsdf, "Alpha")
        if a is not None:
            a.default_value = alpha
        set_safe(m, "surface_render_method", "BLENDED")
        set_safe(m, "blend_method", "BLEND")
    return m


def vertex_color_material(name: str, roughness=0.85):
    m = new_material(name)
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    nt.links.new(vc.outputs["Color"], inp(bsdf, "Base Color"))
    inp(bsdf, "Roughness").default_value = roughness
    set_specular(bsdf, 0.1)
    return m


def horizon_color(pal) -> np.ndarray:
    """Farbe am Horizont (sRGB): das Grün der Ferne, zu gut einem Drittel zur Himmelsfarbe gemischt –
    Ferne-Ebene und unterster Himmel haben dieselbe Farbe, es gibt keine harte Linie."""
    return 0.65 * to_rgb(pal["far"]) + 0.35 * to_rgb(pal["sky_hor"])


def _node_out(node, kind: str):
    return next(o for o in node.outputs if o.type == kind)


def noise_material(name: str, color, roughness=0.9, strength=0.2, coarse=0.03, fine=0.9, specular=0.1):
    """Fläche mit Farbvariation: großes Rauschen (Flecken) plus feines (Körnung), Objekt-Koordinaten.
    strength = wie stark die Farbe schwankt (0,2 → ±20 %)."""
    m = new_material(name)
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    base = to_rgb(color)
    tc = nt.nodes.new("ShaderNodeTexCoord")

    def noise(scale, detail):
        n = nt.nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
        return n.outputs["Fac"]

    big, small = noise(coarse, 4.0), noise(fine, 5.0)
    m1 = nt.nodes.new("ShaderNodeMath")
    m1.operation = "MULTIPLY"
    nt.links.new(big, m1.inputs[0])
    m1.inputs[1].default_value = 0.7
    m2 = nt.nodes.new("ShaderNodeMath")
    m2.operation = "MULTIPLY_ADD"
    nt.links.new(small, m2.inputs[0])
    m2.inputs[1].default_value = 0.3
    nt.links.new(m1.outputs["Value"], m2.inputs[2])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    nt.links.new(m2.outputs["Value"], mix.inputs[0])
    a_in, b_in = [i for i in mix.inputs if i.type == "RGBA"][:2]
    a_in.default_value = rgba(np.clip(base * (1 - strength), 0, 1))
    b_in.default_value = rgba(np.clip(base * (1 + strength * 1.3), 0, 1))
    nt.links.new(_node_out(mix, "RGBA"), inp(bsdf, "Base Color"))
    inp(bsdf, "Roughness").default_value = roughness
    set_specular(bsdf, specular)
    return m


# ── Umgebungs-Materialien: Asphalt mit Rennlinie, Rasen, Kies, Dunst ─────────────────────────────

class Nodes:
    """Kleine Hilfe zum Knotenbau: als Eingänge gehen Zahlen oder Buchsen."""

    def __init__(self, m):
        self.nt = m.node_tree          # Material oder Welt

    def put(self, sock, v):
        if v is None:
            return
        if isinstance(v, bpy.types.NodeSocket):
            self.nt.links.new(v, sock)
        else:
            sock.default_value = v

    def math(self, op, a, b=None, c=None, clamp=False):
        n = self.nt.nodes.new("ShaderNodeMath")
        n.operation = op
        n.use_clamp = clamp
        for i, v in enumerate((a, b, c)):
            self.put(n.inputs[i], v)
        return n.outputs[0]

    def smooth(self, x, lo, hi):
        """0 bis lo, 1 ab hi, dazwischen weich (lo < hi)."""
        n = self.nt.nodes.new("ShaderNodeMapRange")
        n.interpolation_type = "SMOOTHSTEP"
        n.clamp = True
        self.put(n.inputs["Value"], x)
        n.inputs["From Min"].default_value, n.inputs["From Max"].default_value = lo, hi
        return n.outputs["Result"]

    def noise(self, vec, scale, detail=4.0):
        n = self.nt.nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        self.put(n.inputs["Vector"], vec)
        return n.outputs["Fac"]

    def mix(self, fac, a, b):
        n = self.nt.nodes.new("ShaderNodeMix")
        n.data_type = "RGBA"
        self.put(n.inputs[0], fac)
        ia, ib = [i for i in n.inputs if i.type == "RGBA"][:2]
        self.put(ia, a)
        self.put(ib, b)
        return _node_out(n, "RGBA")

    def obj_coords(self):
        return self.nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]

    def uv(self):
        tc = self.nt.nodes.new("ShaderNodeTexCoord")
        sep = self.nt.nodes.new("ShaderNodeSeparateXYZ")
        self.nt.links.new(tc.outputs["UV"], sep.inputs["Vector"])
        return sep.outputs["X"], sep.outputs["Y"]


def asphalt_material(pal, width: float):
    """Asphalt mit Rennlinie: dunkles, glatteres Reifengummi-Band um die Mitte (schlängelt leicht),
    weiße Randlinien, Flecken und Körnung. UV: u = Meter vom linken Rand (0…Breite), v = Meter längs."""
    m = new_material("Asphalt")
    N = Nodes(m)
    bsdf = m.node_tree.nodes["Principled BSDF"]
    base = to_rgb(pal["asphalt"])
    u, v = N.uv()
    obj = N.obj_coords()
    patches, grain = N.noise(obj, 0.12, 5.0), N.noise(obj, 3.0, 4.0)
    wob = N.math("MULTIPLY", N.math("SINE", N.math("MULTIPLY", v, 0.015)), 0.9)
    d = N.math("ABSOLUTE", N.math("SUBTRACT", u, N.math("ADD", wob, width / 2)))
    band = N.math("SUBTRACT", 1.0, N.smooth(d, 0.4, 2.8))
    rubber = N.math("MULTIPLY", band, N.math("ADD", 0.55, N.math("MULTIPLY", N.smooth(patches, 0.3, 0.7), 0.45)))
    shade = N.math("SUBTRACT",
                   N.math("ADD", 0.5, N.math("ADD", N.math("MULTIPLY", N.math("SUBTRACT", patches, 0.5), 0.5),
                                              N.math("MULTIPLY", N.math("SUBTRACT", grain, 0.5), 0.3))),
                   N.math("SUBTRACT", N.math("MULTIPLY", rubber, 0.58),
                          N.math("MULTIPLY", N.math("MULTIPLY", N.smooth(d, 2.8, 4.5), N.smooth(patches, 0.35, 0.8)), 0.12)),
                   clamp=True)
    col = N.mix(shade, rgba(np.clip(base * 0.70, 0, 1)), rgba(np.clip(base * 1.30, 0, 1)))
    edge = N.math("MINIMUM", N.math("ABSOLUTE", N.math("SUBTRACT", u, 0.45)),
                  N.math("ABSOLUTE", N.math("SUBTRACT", u, width - 0.45)))
    line = N.math("SUBTRACT", 1.0, N.smooth(edge, 0.07, 0.11))
    col = N.mix(N.math("MULTIPLY", line, 0.9), col, rgba((0.93, 0.93, 0.94)))
    N.put(inp(bsdf, "Base Color"), col)
    N.put(inp(bsdf, "Roughness"), N.math("SUBTRACT", 0.93, N.math("MULTIPLY", rubber, 0.30)))
    set_specular(bsdf, 0.22)
    return m


def ground_material(pal, near: bool = True):
    """Rasen: Felder/Flecken in drei Größen, Mähstreifen, bei near=True Kiesbett am Streckenrand.
    UV (nur near): u = Meter vom Streckenrand nach außen, v = Meter längs."""
    m = new_material("Boden" if near else "Ferne")
    N = Nodes(m)
    bsdf = m.node_tree.nodes["Principled BSDF"]
    base = to_rgb(pal["ground"])
    obj = N.obj_coords()
    fields, patches, blades = N.noise(obj, 0.004, 3.0), N.noise(obj, 0.03, 4.0), N.noise(obj, 1.6, 5.0)
    tone = N.math("ADD", N.math("MULTIPLY", N.math("SUBTRACT", fields, 0.5), 0.55),
                  N.math("ADD", N.math("MULTIPLY", N.math("SUBTRACT", patches, 0.5), 0.35),
                         N.math("MULTIPLY", N.math("SUBTRACT", blades, 0.5), 0.30)))
    if near:
        u, v = N.uv()
        stripe = N.math("MULTIPLY", N.math("SINE", N.math("MULTIPLY", v, 2 * math.pi / 16.0)), 0.07)
        tone = N.math("ADD", tone, stripe)
    shade = N.math("ADD", 0.5, tone, clamp=True)
    grass = N.mix(shade, rgba(np.clip(base * np.array([0.62, 0.66, 0.55]), 0, 1)),
                  rgba(np.clip(base * np.array([1.30, 1.28, 1.05]), 0, 1)))
    col, rough = grass, 0.95
    if near:
        stones = N.noise(obj, 25.0, 3.0)
        gravel = N.mix(N.math("ADD", 0.5, N.math("MULTIPLY", N.math("SUBTRACT", stones, 0.5), 0.9), clamp=True),
                       rgba((0.36, 0.34, 0.31)), rgba((0.60, 0.57, 0.51)))
        jitter = N.math("ADD", u, N.math("MULTIPLY", N.math("SUBTRACT", N.noise(obj, 0.15, 2.0), 0.5), 5.0))
        in_gravel = N.math("SUBTRACT", 1.0, N.smooth(jitter, 5.5, 7.0))
        col = N.mix(in_gravel, grass, gravel)
        rough = 0.97
    N.put(inp(bsdf, "Base Color"), col)
    inp(bsdf, "Roughness").default_value = rough
    set_specular(bsdf, 0.08)
    return m


def hazeify(m, fog_rgb, density: float):
    """Dunst nach Entfernung: je weiter von der Kamera, desto mehr geht die Fläche in die Horizontfarbe
    über (Emission in der Dunstfarbe über einen Mix-Shader). So verschwimmt die Ferne in den Himmel."""
    if density <= 0:
        return m
    nt = m.node_tree
    out = nt.nodes.get("Material Output") or next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    surf = out.inputs["Surface"]
    if not surf.links:
        return m
    src = surf.links[0].from_socket
    N = Nodes(m)
    cam = nt.nodes.new("ShaderNodeCameraData")
    dist = cam.outputs["View Z Depth"]
    fac = N.math("SUBTRACT", 1.0, N.math("EXPONENT", N.math("MULTIPLY", dist, -float(density))), clamp=True)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = rgba(fog_rgb)
    em.inputs["Strength"].default_value = 1.0
    mixs = nt.nodes.new("ShaderNodeMixShader")
    N.put(mixs.inputs["Fac"], fac)
    nt.links.new(src, mixs.inputs[1])
    nt.links.new(em.outputs["Emission"], mixs.inputs[2])
    nt.links.new(mixs.outputs["Shader"], surf)
    return m


def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def mesh_object(name, verts, faces, material=None, loop_colors=None, loop_uv=None, smooth=False):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(np.asarray(verts, float).tolist(), [], np.asarray(faces, int).tolist())
    mesh.update()
    if smooth and hasattr(mesh, "shade_smooth"):
        mesh.shade_smooth()
    if loop_uv is not None:
        uv = np.asarray(loop_uv, float)
        if len(uv) != len(mesh.loops):
            raise ValueError(f"{name}: {len(uv)} UV für {len(mesh.loops)} Ecken")
        mesh.uv_layers.new(name="UVMap").data.foreach_set("uv", uv.ravel())
    if loop_colors is not None:
        attr = mesh.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
        lc = np.asarray(loop_colors, float)
        if len(lc) != len(mesh.loops):
            raise ValueError(f"{name}: {len(lc)} Farben für {len(mesh.loops)} Ecken")
        attr.data.foreach_set("color", lc.ravel())
    obj = bpy.data.objects.new(name, mesh)
    if material is not None:
        obj.data.materials.append(material)
    return link(obj)


def quads_object(name, quads, material, rgb=None, face_up=False, uv=None):
    """Viereck-Fläche je Eintrag in quads (n,4,3). rgb (n,3) = sRGB-Farbe je Viereck, uv (n,4,2) = Texturkoordinaten."""
    q = np.array(quads, dtype=float).reshape(-1, 4, 3)
    if len(q) == 0:
        return None
    uvq = None if uv is None else np.array(uv, dtype=float).reshape(-1, 4, 2)
    if face_up:
        nrm = np.cross(q[:, 2] - q[:, 0], q[:, 3] - q[:, 1])
        flip = nrm[:, 2] < 0
        q[flip] = q[flip][:, ::-1]
        if uvq is not None:
            uvq[flip] = uvq[flip][:, ::-1]
    verts = q.reshape(-1, 3)
    faces = np.arange(len(verts)).reshape(-1, 4)
    colors = None
    if rgb is not None:
        lin = srgb_to_linear(np.asarray(rgb, float).reshape(-1, 3))
        colors = np.repeat(np.column_stack([lin, np.ones(len(lin))]), 4, axis=0)
    return mesh_object(name, verts, faces, material, colors, None if uvq is None else uvq.reshape(-1, 2))


# ── Szene aufbauen ───────────────────────────────────────────────────────────

def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for item in list(coll):
            coll.remove(item)


HAZE_SCALE = 1.0


# ── Gelände: Höhe neben der Strecke aus der Streckenhöhe ableiten ────────────────────────────────

def _smoothstep(x, lo, hi):
    t = np.clip((np.asarray(x, float) - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3 - 2 * t)


class Terrain:
    """Höhenfeld rund um die Strecke. Jeder Punkt übernimmt die Höhe der nächsten Streckenstücke (gewichteter
    Mittelwert, σ = 40 m, damit es an Spitzkehren keine Sprünge gibt) und fällt mit der Entfernung zur Grundhöhe
    ab (Gauß, 450 m). Weit weg kommen Hügel dazu (Stadt: eben). Nahe der Strecke bleibt es ohne Hügel, damit
    nichts die Sicht verdeckt."""
    SIGMA, FADE, HILL_M = 40.0, 450.0, 12.0

    def __init__(self, centre, grass_w: float, city: bool = False):
        c = np.asarray(centre, float)
        self.c = c[::3]
        self.base = float(c[:, 2].min()) - 0.3
        self.gw, self.city = float(grass_w), bool(city)

    def near(self, xy):
        """(Abstand zum nächsten Streckenpunkt, geglättete Streckenhöhe dort) je Punkt."""
        xy = np.atleast_2d(np.asarray(xy, float))[:, :2]
        dd, zz = [], []
        for i in range(0, len(xy), 1200):
            p = xy[i:i + 1200]
            d2 = ((p[:, None, :] - self.c[None, :, :2]) ** 2).sum(axis=2)
            m = d2.min(axis=1, keepdims=True)
            w = np.exp(-(d2 - m) / (2 * self.SIGMA ** 2))
            zz.append((w * self.c[None, :, 2]).sum(axis=1) / w.sum(axis=1))
            dd.append(np.sqrt(m[:, 0]))
        return np.concatenate(dd), np.concatenate(zz)

    @staticmethod
    def rolling(xy):
        """Sanfte Hügel 0…1 (Summe schiefer Sinuswellen, ohne Zufall: gleiche Strecke → gleiches Gelände)."""
        x, y = xy[:, 0], xy[:, 1]
        n = 0.45 * np.sin(x / 260 + 1.3) * np.sin(y / 310 + 0.4) + 0.30 * np.sin(x / 130 + y / 170 + 2.0) \
            + 0.15 * np.sin(x / 70 - y / 90 + 0.7) + 0.10 * np.sin((x + y) / 45)
        return 0.5 + 0.5 * np.clip(n, -1, 1)

    def height(self, xy, hills: bool = True):
        xy = np.atleast_2d(np.asarray(xy, float))[:, :2]
        d, zl = self.near(xy)
        z = self.base + (zl - self.base) * np.exp(-(d / self.FADE) ** 2)
        if hills and not self.city:
            z = z + self.HILL_M * _smoothstep(d, 150.0, 600.0) * self.rolling(xy)
        return z

    def surface(self, xy):
        """Höhe der Rasenfläche (Rasenstreifen: knapp unter der Strecke, nach außen etwas tiefer)."""
        xy = np.atleast_2d(np.asarray(xy, float))[:, :2]
        d, zl = self.near(xy)
        z = self.base + (zl - self.base) * np.exp(-(d / self.FADE) ** 2)
        t = np.clip((d - 6.5) / self.gw, 0.0, 1.0)
        return z - (0.05 + 0.25 * t)


_TERRAIN_CACHE: dict = {}


def terrain_for(d: dict) -> Terrain:
    c0 = d["track"]["centre"]
    key = (id(d["track"]), len(c0), tuple(c0[0]), tuple(c0[len(c0) // 2]), bool(d["env"].get("city")))
    if key not in _TERRAIN_CACHE:
        _TERRAIN_CACHE.clear()
        _TERRAIN_CACHE[key] = Terrain(d["track"]["centre"], max(float(d["env"]["palette"]["grass_w_m"]), RIBBON_MIN_W),
                                      bool(d["env"].get("city")))
    return _TERRAIN_CACHE[key]


RIBBON_MIN_W = 55.0


def build_terrain(d: dict, margin: float = 900.0, hole_m: float = 66.0):
    """Gelände als Gitternetz um die Strecke (mit Loch dort, wo schon der Rasenstreifen liegt)."""
    T = terrain_for(d)
    tr = d["track"]
    c = np.array(tr["centre"])
    lo, hi = c[:, :2].min(axis=0) - margin, c[:, :2].max(axis=0) + margin
    step = max(24.0, float((hi - lo).max()) / 190.0)
    nx, ny = int((hi[0] - lo[0]) / step) + 1, int((hi[1] - lo[1]) / step) + 1
    gx, gy = np.meshgrid(lo[0] + np.arange(nx) * step, lo[1] + np.arange(ny) * step)
    xy = np.column_stack([gx.ravel(), gy.ravel()])
    d_min, _ = T.near(xy)
    z = T.height(xy)
    z = z - 0.35 * (1.0 - _smoothstep(d_min, 60.0, 150.0))          # unter dem Rasenstreifen hindurch
    edge = np.minimum.reduce([xy[:, 0] - lo[0], hi[0] - xy[:, 0], xy[:, 1] - lo[1], hi[1] - xy[:, 1]])
    z = T.base + (z - T.base) * _smoothstep(edge, 0.0, 350.0)       # am Rand auf die Grundebene
    idx = np.arange(nx * ny).reshape(ny, nx)
    cells = np.stack([idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]], axis=-1).reshape(-1, 4)
    centre_d = d_min[cells].mean(axis=1)
    cells = cells[centre_d > hole_m]
    verts = np.column_stack([xy, z])
    mat = hazeify(ground_material(d["env"]["palette"], near=False), *haze_for(d))
    mesh_object("Gelände", verts, cells, mat, smooth=True)
    return T




def haze_for(d: dict):
    """(Dunstfarbe als sRGB, Dichte je Meter) für die Umgebung – aus der Lichtstimmung."""
    p = LIGHT_PRESETS.get(d["meta"]["light"], LIGHT_PRESETS["day"])
    return horizon_color(d["env"]["palette"]), p["fog"] * HAZE_SCALE


def _along(path_xyz: np.ndarray) -> np.ndarray:
    """Weg entlang einer Linie in Metern (geschlossene Schleife: n+1 Werte)."""
    p = np.vstack([path_xyz, path_xyz[:1]])[:, :2]
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]


def build_track(d: dict):
    tr, pal = d["track"], d["env"]["palette"]
    left, right = np.array(tr["left"]), np.array(tr["right"])
    centre = np.array(tr["centre"])
    width = float(tr["width_m"])
    s = _along(centre)
    if len(s) != len(left):
        s = np.linspace(0.0, float(tr["length_m"]), len(left))
    fog = haze_for(d)
    quads = np.stack([left[:-1], left[1:], right[1:], right[:-1]], axis=1)
    uv = np.stack([np.column_stack([np.zeros(len(s) - 1), s[:-1]]), np.column_stack([np.zeros(len(s) - 1), s[1:]]),
                   np.column_stack([np.full(len(s) - 1, width), s[1:]]), np.column_stack([np.full(len(s) - 1, width), s[:-1]])], axis=1)
    quads_object("Strecke", quads, hazeify(asphalt_material(pal, width), *fog), face_up=True, uv=uv)

    T = build_terrain(d)
    gw = T.gw
    mat = hazeify(ground_material(pal, near=True), *fog)
    for name, edge in (("Rand links", left), ("Rand rechts", right)):
        out = edge[:-1, :2] - centre[:, :2]
        out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)
        outer_xy = edge[:-1, :2] + out * gw
        outer = np.column_stack([outer_xy, T.height(outer_xy, hills=False) - 0.30])    # außen: Gelände (ohne Hügel)
        outer = np.vstack([outer, outer[:1]])
        inner = edge.copy()
        inner[:, 2] -= 0.05
        guv = np.stack([np.column_stack([np.zeros(len(s) - 1), s[:-1]]), np.column_stack([np.zeros(len(s) - 1), s[1:]]),
                        np.column_stack([np.full(len(s) - 1, gw), s[1:]]), np.column_stack([np.full(len(s) - 1, gw), s[:-1]])], axis=1)
        quads_object(name, np.stack([inner[:-1], inner[1:], outer[1:], outer[:-1]], axis=1), mat, face_up=True, uv=guv)

    size = 6000.0
    cx, cy = centre[:, 0].mean(), centre[:, 1].mean()
    zb = T.base - 0.5                                          # Grundebene knapp unter dem Gelände-Rand
    plane = [[cx - size, cy - size, zb], [cx + size, cy - size, zb], [cx + size, cy + size, zb], [cx - size, cy + size, zb]]
    quads_object("Horizont", [plane], hazeify(ground_material(pal, near=False), *fog), face_up=True)


GUARD_OFFSET = 7.6      # Meter vom Streckenrand: hinter dem Kiesbett


def build_guardrail(d: dict, offset: float = GUARD_OFFSET):
    """Leitplanke mit Pfosten entlang beider Streckenseiten hinter dem Kiesbett. Gibt im Video etwas, das schnell
    vorbeizieht (Geschwindigkeitsgefühl) und dem Rand eine klare Kante."""
    tr = d["track"]
    centre = np.array(tr["centre"])
    n = len(centre)
    mat = hazeify(solid_material("Leitplanke nah", (0.64, 0.66, 0.68), roughness=0.45, metallic=0.6, specular=0.3), *haze_for(d))
    mat.use_backface_culling = False
    post_mat = hazeify(solid_material("Pfosten", (0.42, 0.44, 0.46), roughness=0.6, metallic=0.4, specular=0.2), *haze_for(d))
    for name, edge in (("Planke links", np.array(tr["left"])), ("Planke rechts", np.array(tr["right"]))):
        out = edge[:-1, :2] - centre[:, :2]
        out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)
        pxy = edge[:-1, :2] + out * offset
        pos = np.column_stack([pxy, terrain_for(d).surface(pxy)])
        pos = np.vstack([pos, pos[:1]])
        lo, hi = pos + [0, 0, 0.32], pos + [0, 0, 0.74]
        quads_object(name, np.stack([lo[:-1], lo[1:], hi[1:], hi[:-1]], axis=1), mat)
        k = np.arange(0, n, 2)
        tang = pos[k + 1, :2] - pos[k, :2]
        yaw = np.arctan2(tang[:, 1], tang[:, 0])
        c, sn = np.cos(yaw), np.sin(yaw)
        hw = 0.055
        corners = np.array([[-hw, -hw], [hw, -hw], [hw, hw], [-hw, hw]])
        xy = pos[k, None, :2] + np.stack([corners[:, 0] * c[:, None] - corners[:, 1] * sn[:, None],
                                          corners[:, 0] * sn[:, None] + corners[:, 1] * c[:, None]], axis=2)
        z0 = pos[k, 2][:, None]
        bot = np.concatenate([xy, np.repeat(z0[:, None, :], 4, axis=1)], axis=2)
        top = np.concatenate([xy, np.repeat(z0[:, None, :] + 0.82, 4, axis=1)], axis=2)
        sides = [np.stack([bot[:, i], bot[:, (i + 1) % 4], top[:, (i + 1) % 4], top[:, i]], axis=1) for i in range(4)]
        quads_object(name + " Pfosten", np.concatenate(sides + [top[:, [0, 1, 2, 3]]]), post_mat)


def build_hills(d: dict):
    """Ferne Hügelkette als Ring um die Strecke (nur ohne Stadt): gibt der Ferne Tiefe, geht im Dunst unter."""
    if d["env"].get("city"):
        return
    tr, pal = d["track"], d["env"]["palette"]
    centre = np.array(tr["centre"])
    zmin = terrain_for(d).base
    cx, cy = centre[:, 0].mean(), centre[:, 1].mean()
    n = 240
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    h = 110 + 80 * np.sin(3 * th + 1.0) + 55 * np.sin(7 * th + 2.0) + 30 * np.sin(13 * th + 0.5)
    h = np.maximum(h, 25.0)
    rings = []
    for r, hh in ((2600.0, 0.0 * h), (3000.0, h), (3500.0, 0.0 * h)):
        rings.append(np.column_stack([cx + r * np.cos(th), cy + r * np.sin(th), zmin + hh]))
    verts = np.vstack(rings)
    faces = []
    for ring in range(2):
        for i in range(n):
            j = (i + 1) % n
            faces.append([ring * n + i, ring * n + j, (ring + 1) * n + j, (ring + 1) * n + i])
    col = 0.55 * to_rgb(pal["far"]) + 0.45 * to_rgb(pal["sky_hor"])
    mat = hazeify(solid_material("Hügel", col, roughness=1.0, specular=0.0), *haze_for(d))
    mat.use_backface_culling = False
    mesh_object("Hügel", verts, faces, mat)


def build_kerbs_and_barriers(d: dict):
    env, pal = d["env"], d["env"]["palette"]
    on, red = np.array(env["kerb_on"], bool), np.array(env["kerb_red"], bool)
    quads, cols = [], []
    for k in env["kerbs"].values():
        a, b = np.array(k["inner"]), np.array(k["outer"])
        idx = np.where(on[:-1] & on[1:])[0]
        quads.append(np.stack([a[idx], a[idx + 1], b[idx + 1], b[idx]], axis=1))
        cols.append(np.where(red[idx, None], [[0.80, 0.08, 0.08]], [[0.92, 0.92, 0.94]]))
    if quads:
        quads_object("Randsteine", np.concatenate(quads), hazeify(vertex_color_material("Randstein", 0.6), *haze_for(d)),
                     rgb=np.concatenate(cols), face_up=True)
    quads = []
    for b in env["barriers"].values():
        lo, hi, ok = np.array(b["low"]), np.array(b["high"]), np.array(b["ok"], bool)
        shift = terrain_for(d).surface(lo[:, :2]) - lo[:, 2]                 # Wand auf das Gelände setzen
        lo, hi = lo + np.column_stack([np.zeros((len(lo), 2)), shift]), hi + np.column_stack([np.zeros((len(hi), 2)), shift])
        idx = np.where(ok[:-1] & ok[1:])[0]
        quads.append(np.stack([lo[idx], lo[idx + 1], hi[idx + 1], hi[idx]], axis=1))
    if quads:
        mat = hazeify(solid_material("Leitplanke", pal["barrier"], roughness=0.5, metallic=0.4), *haze_for(d))
        mat.use_backface_culling = False
        quads_object("Leitplanken", np.concatenate(quads), mat)


def _sphere_template(seg: int = 8, rings: int = 5):
    """Kugel (Einheitsradius) aus Dreiecken: Pol oben, Ringe, Pol unten. → (verts, faces)."""
    v = [(0.0, 0.0, 1.0)]
    for r in range(1, rings):
        phi = np.pi * r / rings
        for k in range(seg):
            th = 2 * np.pi * k / seg
            v.append((np.sin(phi) * np.cos(th), np.sin(phi) * np.sin(th), np.cos(phi)))
    v.append((0.0, 0.0, -1.0))
    f = []
    for k in range(seg):
        f.append((0, 1 + k, 1 + (k + 1) % seg))
    for r in range(rings - 2):
        for k in range(seg):
            a, b = 1 + r * seg + k, 1 + r * seg + (k + 1) % seg
            c, e = a + seg, b + seg
            f += [(a, c, b), (b, c, e)]
    last = len(v) - 1
    for k in range(seg):
        f.append((last, 1 + (rings - 2) * seg + (k + 1) % seg, 1 + (rings - 2) * seg + k))
    return np.array(v), np.array(f)


def _cone_template(seg: int = 8):
    """Kegel (Radius 1, Höhe 1, Spitze oben, offene Unterseite). → (verts, faces)"""
    v = [(np.cos(2 * np.pi * k / seg), np.sin(2 * np.pi * k / seg), 0.0) for k in range(seg)] + [(0.0, 0.0, 1.0)]
    f = [(k, (k + 1) % seg, seg) for k in range(seg)]
    return np.array(v), np.array(f)


def tree_geometry(base: np.ndarray, height: np.ndarray, rgb: np.ndarray, seed: int = 7):
    """Bäume als ein Netz: Laubbäume (3 unregelmäßige Kugeln auf Stamm) und Nadelbäume (3 gestufte Kegel).
    Farbe je Ecke (unten dunkler, oben heller, je Baum leicht anders). → (verts, faces, linear-RGB je Ecke)"""
    rng = np.random.default_rng(seed)
    sv, sf = _sphere_template()
    cv, cf = _cone_template()
    tv = np.array([(np.cos(2 * np.pi * k / 6), np.sin(2 * np.pi * k / 6), z) for z in (0.0, 1.0) for k in range(6)])
    tf = np.array([(k, (k + 1) % 6, 6 + (k + 1) % 6) for k in range(6)] + [(k, 6 + (k + 1) % 6, 6 + k) for k in range(6)])
    trunk_rgb = np.array([0.30, 0.21, 0.14])
    V, F, C = [], [], []
    n = 0

    def add(verts, faces, colors):
        nonlocal n
        V.append(verts)
        F.append(faces + n)
        C.append(colors)
        n += len(verts)

    for b, h, c in zip(base, height, rgb):
        yaw = rng.uniform(0, 2 * np.pi)
        cy_, sy_ = np.cos(yaw), np.sin(yaw)
        rot = np.array([[cy_, -sy_, 0], [sy_, cy_, 0], [0, 0, 1]])
        tone = c * rng.uniform(0.80, 1.20, 3) * np.array([1.0, rng.uniform(0.9, 1.1), 1.0])
        if rng.random() < 0.62:                                           # Laubbaum
            tr_h, tr_r = 0.40 * h, 0.035 * h
            add(b + (tv * [tr_r, tr_r, tr_h]) @ rot.T, tf, np.tile(trunk_rgb * 0.8, (len(tv), 1)))
            for off, rad, zc in (((0, 0, 0), 0.30, 0.62), ((0.17, 0.08, 0), 0.22, 0.52), ((-0.14, -0.1, 0), 0.22, 0.74)):
                lump = rng.uniform(0.80, 1.22, (len(sv), 1))
                centre = np.array([off[0] * h, off[1] * h, zc * h])
                verts = sv * lump * [rad * h, rad * h, rad * h * 0.92]
                shade = 0.62 + 0.55 * (sv[:, 2:3] * 0.5 + 0.5)             # unten dunkel, oben hell
                add(b + (verts + centre) @ rot.T, sf, np.clip(tone * shade, 0, 1))
        else:                                                              # Nadelbaum
            tr_h, tr_r = 0.25 * h, 0.03 * h
            add(b + (tv * [tr_r, tr_r, tr_h]) @ rot.T, tf, np.tile(trunk_rgb * 0.7, (len(tv), 1)))
            dark = tone * np.array([0.62, 0.78, 0.66])
            for z0, r0, hh in ((0.14, 0.30, 0.42), (0.36, 0.24, 0.36), (0.58, 0.17, 0.42)):
                jag = np.r_[rng.uniform(0.85, 1.1, len(cv) - 1), 1.0][:, None]
                verts = cv * jag * [r0 * h, r0 * h, hh * h] + [0, 0, z0 * h]
                shade = 0.55 + 0.6 * cv[:, 2:3]
                add(b + verts @ rot.T, cf, np.clip(dark * shade, 0, 1))
    return np.vstack(V), np.vstack(F), np.vstack(C)


def extra_forest(d: dict, base: np.ndarray, rgb: np.ndarray, n: int = 2600, seed: int = 11):
    """Zusätzliche Bäume dahinter (60–420 m neben der Strecke, nie auf einem anderen Streckenstück), damit
    der Horizont nicht leer ist. Höhe und Farbe aus den vorhandenen Bäumen."""
    rng = np.random.default_rng(seed)
    centre = np.array(d["track"]["centre"])
    left, right = np.array(d["track"]["left"])[:-1], np.array(d["track"]["right"])[:-1]
    idx = rng.integers(0, len(centre), n)
    side = np.where(rng.random(n) < 0.5, 1.0, -1.0)
    edge = np.where(side[:, None] > 0, left[idx], right[idx])[:, :2]
    out = edge - centre[idx, :2]
    out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)
    dist = 28.0 + rng.gamma(2.2, 55.0, n)
    xy = edge + out * dist[:, None]
    sparse = centre[::8, :2]
    keep = np.min(np.linalg.norm(xy[:, None, :] - sparse[None], axis=2), axis=1) > 38.0     # nicht auf Fahrbahn/Rasen anderer Stücke
    xy, idx = xy[keep], idx[keep]
    zc = terrain_for(d).height(xy) - 0.1
    h = rng.uniform(9.0, 20.0, len(xy))
    c = rgb[rng.integers(0, len(rgb), len(xy))]
    return np.column_stack([xy, zc]), h, c


def build_trees(d: dict):
    t = d["env"]["trees"]
    base = np.array(t["base"]).reshape(-1, 3)
    if len(base) == 0:
        return
    height, rgb = np.array(t["height_m"]), np.array(t["rgb"]).reshape(-1, 3)
    T = terrain_for(d)
    base = np.column_stack([base[:, :2], T.height(base[:, :2], hills=True) - 0.1])
    if not d["env"].get("city"):
        eb, eh, ec = extra_forest(d, base, rgb)
        base, height, rgb = np.vstack([base, eb]), np.r_[height, eh], np.vstack([rgb, ec])
    verts, faces, cols = tree_geometry(base, height, rgb)
    lin = srgb_to_linear(cols)
    loop_cols = np.column_stack([lin[faces.ravel()], np.ones(faces.size)])
    mesh_object("Bäume", verts, faces, hazeify(vertex_color_material("Baum", 0.9), *haze_for(d)), loop_cols, smooth=True)


def facade_material(pal, lit: float):
    """Fassade: Vertex-Farbe, darüber ein Fensterraster (UV: u = Meter entlang der Wand, v = Meter Höhe; Dach hat v < 0).
    Fenster spiegeln dunkel-bläulich; nachts leuchtet der Anteil `lit` der Fenster warm."""
    m = new_material("Fassade")
    N = Nodes(m)
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    u, v = N.uv()
    cu, cv = N.math("DIVIDE", u, 3.2), N.math("DIVIDE", v, 3.6)
    fu, fv = N.math("FRACT", cu), N.math("FRACT", cv)
    in_u = N.math("MULTIPLY", N.smooth(fu, 0.16, 0.22), N.math("SUBTRACT", 1.0, N.smooth(fu, 0.78, 0.84)))
    in_v = N.math("MULTIPLY", N.smooth(fv, 0.22, 0.28), N.math("SUBTRACT", 1.0, N.smooth(fv, 0.74, 0.80)))
    above = N.smooth(v, 3.0, 3.4)                              # Erdgeschoss ohne Fenster
    win = N.math("MULTIPLY", N.math("MULTIPLY", in_u, in_v), above)
    glass = N.mix(win, vc.outputs["Color"], rgba((0.07, 0.09, 0.13)))
    N.put(inp(bsdf, "Base Color"), glass)
    N.put(inp(bsdf, "Roughness"), N.math("SUBTRACT", 0.9, N.math("MULTIPLY", win, 0.65)))
    set_specular(bsdf, 0.12)
    if lit > 0:
        cell = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(N.math("FLOOR", cu), cell.inputs["X"])
        nt.links.new(N.math("FLOOR", cv), cell.inputs["Y"])
        wn = nt.nodes.new("ShaderNodeTexWhiteNoise")
        nt.links.new(cell.outputs["Vector"], wn.inputs["Vector"])
        on = N.math("SUBTRACT", 1.0, N.smooth(wn.outputs["Value"], lit - 0.01, lit + 0.01))      # Anteil `lit` der Zellen
        glow = N.math("MULTIPLY", win, on)
        e = inp(bsdf, "Emission Color", "Emission")
        N.put(e, rgba((1.0, 0.78, 0.45)))
        N.put(inp(bsdf, "Emission Strength"), N.math("MULTIPLY", glow, 6.0))
    return m


def build_buildings(d: dict):
    b = d["env"].get("buildings")
    if not b:
        return
    foot, z0, h, rgb = np.array(b["foot"]), np.array(b["z0"]), np.array(b["height_m"]), np.array(b["rgb"])
    quads, cols, uvs = [], [], []
    for fp, zz, hh, cc in zip(foot, z0, h, rgb):
        area = 0.5 * np.sum(fp[:, 0] * np.roll(fp[:, 1], -1) - np.roll(fp[:, 0], -1) * fp[:, 1])
        if area < 0:
            fp = fp[::-1]
        bot = np.column_stack([fp, np.full(4, zz)])
        top = np.column_stack([fp, np.full(4, zz + hh)])
        quads.append(top)                                   # Dach, Normale nach oben (Umlauf gegen den Uhrzeigersinn)
        uvs.append(np.array([[0, -50], [1, -50], [1, -50], [0, -50]], float))
        for i in range(4):
            j = (i + 1) % 4
            quads.append(np.array([bot[i], bot[j], top[j], top[i]]))
            length = float(np.linalg.norm(fp[j] - fp[i]))
            uvs.append(np.array([[0, 0], [length, 0], [length, hh], [0, hh]], float))
        cols.extend([cc] * 5)
    pal = d["env"]["palette"]
    mat = hazeify(facade_material(pal, float(pal.get("window_lit", 0.0))), *haze_for(d))
    quads_object("Häuser", np.array(quads), mat, rgb=np.array(cols), uv=np.array(uvs))


# Straßenlaternen: nachts Flutlicht entlang der Strecke. Leuchtköpfe sind selbstleuchtende Kästchen; echte Lichter
# wären zu teuer. Mastabstand und Höhe grob wie bei Nachtrennen.
LAMP_SPACING_M = 32.0
LAMP_OFFSET_M = 11.0


def build_lamps(d: dict):
    if d["meta"]["light"] != "night":
        return
    tr = d["track"]
    centre = np.array(tr["centre"])
    s = _along(centre)
    n = len(centre)
    pole = hazeify(solid_material("Laternenmast", (0.30, 0.31, 0.33), roughness=0.5, metallic=0.5), *haze_for(d))
    head = solid_material("Laternenkopf", (1.0, 0.86, 0.62), roughness=0.4, emission=120.0)
    quads_p, quads_h = [], []
    for side, edge in ((1.0, np.array(tr["left"])), (-1.0, np.array(tr["right"]))):
        for j, target in enumerate(np.arange(0.0, s[-1], LAMP_SPACING_M * 2)):
            i = int(np.searchsorted(s, target + (LAMP_SPACING_M if side < 0 else 0.0))) % n
            out = edge[i, :2] - centre[i, :2]
            out /= max(np.linalg.norm(out), 1e-9)
            bxy = edge[i, :2] + out * LAMP_OFFSET_M
            base = np.append(bxy, terrain_for(d).surface(bxy[None])[0])
            tang = np.array([-out[1], out[0]])
            hw = 0.14
            for corners, quads, z_lo, z_hi, w, ln in (
                    (None, quads_p, 0.0, 10.0, hw, hw), (None, quads_h, 9.6, 10.2, 0.6, 1.6)):
                a = tang * ln
                b_ = out * w
                c4 = [base[:2] - a - b_, base[:2] + a - b_, base[:2] + a + b_, base[:2] - a + b_]
                if quads is quads_h:                                           # Kopf ragt zur Strecke hin
                    c4 = [p - out * 0.8 for p in c4]
                bot = [np.append(p, base[2] + z_lo) for p in c4]
                top = [np.append(p, base[2] + z_hi) for p in c4]
                for k in range(4):
                    q = (k + 1) % 4
                    quads.append(np.array([bot[k], bot[q], top[q], top[k]]))
                quads.append(np.array(top))
    if quads_p:
        quads_object("Laternenmasten", np.array(quads_p), pole)
    if quads_h:
        quads_object("Laternenköpfe", np.array(quads_h), head)


def build_gantry_and_finish(d: dict):
    env = d["env"]
    quads_object("Portal", env["gantry"], hazeify(solid_material("Portal", (0.12, 0.12, 0.14), roughness=0.6, metallic=0.3), *haze_for(d)))
    fin = env["finish"]
    quads_object("Ziellinie", fin["quads"], hazeify(vertex_color_material("Ziellinie", 0.7), *haze_for(d)),
                 rgb=np.array(fin["rgb"]), face_up=True)


# ── Autos ────────────────────────────────────────────────────────────────────

def _prep(o, name, mat, parent, bevel=0.0):
    o.name = name
    o.data.materials.append(mat)
    o.parent = parent
    if bevel > 0:
        m = o.modifiers.new("Bevel", "BEVEL")
        m.width = bevel
        m.segments = 3
        set_safe(m, "limit_method", "ANGLE")
        wn = o.modifiers.new("Normalen", "WEIGHTED_NORMAL")
        set_safe(wn, "keep_sharp", True)
    if hasattr(o.data, "shade_smooth"):
        o.data.shade_smooth()
    return o


def _box(name, size, loc, mat, parent, bevel=0.03, rot=(0.0, 0.0, 0.0)):
    """Quader: Größe steckt in den Eckpunkten (nicht im Maßstab), damit die Abrundung gleichmäßig ist."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.data.transform(Matrix.Diagonal((size[0], size[1], size[2], 1.0)))
    return _prep(o, name, mat, parent, bevel)


def _wheel(name, x, y, radius, width, mat, parent, bevel=0.03):
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=radius, depth=width, location=(x, y, radius),
                                        rotation=(math.pi / 2, 0, 0))
    return _prep(bpy.context.active_object, name, mat, parent, bevel)


def build_placeholder_car(name: str, color, ghost: bool, parent):
    """F1-Auto aus abgerundeten Formen, ca. 5,5 m lang, Nase nach +x, Boden bei z = 0. Von hinten gesehen
    (die Kamera sitzt dort) tragen Heckflügel, Räder, Halo und Rücklicht das Bild."""
    al = 0.45 if ghost else 1.0
    body = solid_material(f"{name} Lack", color, 0.25, 0.25, alpha=al, specular=0.5)
    carbon = solid_material(f"{name} Carbon", (0.045, 0.045, 0.05), 0.35, 0.15, alpha=al, specular=0.4)
    rubber = solid_material(f"{name} Reifen", (0.02, 0.02, 0.022), 0.85, alpha=al, specular=0.2)
    rim = solid_material(f"{name} Felge", (0.55, 0.55, 0.58), 0.3, 1.0, alpha=al)
    helmet = solid_material(f"{name} Helm", (0.9, 0.9, 0.92), 0.25, alpha=al, specular=0.5)
    taillight = solid_material(f"{name} Rücklicht", (1.0, 0.04, 0.02), 0.4, emission=14.0)

    def B(n, size, loc, mat, bev=0.03, rot=(0.0, 0.0, 0.0)):
        return _box(f"{name} {n}", size, loc, mat, parent, bev, rot)

    B("Boden", (3.9, 1.45, 0.05), (0.0, 0, 0.12), carbon, 0.012)
    B("Monocoque", (2.9, 0.58, 0.46), (0.15, 0, 0.50), body, 0.13)
    B("Cockpit", (0.75, 0.40, 0.14), (0.35, 0, 0.76), carbon, 0.05)
    B("Motorhaube", (1.5, 0.42, 0.40), (-0.85, 0, 0.74), body, 0.15)
    B("Heck", (1.3, 0.26, 0.28), (-1.9, 0, 0.55), body, 0.10)
    bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=0.20, radius2=0.06, depth=1.9, location=(2.05, 0, 0.36),
                                    rotation=(0, math.pi / 2, 0))
    _prep(bpy.context.active_object, f"{name} Nase", body, parent, 0.0)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.14, segments=24, ring_count=12, location=(0.30, 0, 0.84))
    _prep(bpy.context.active_object, f"{name} Helm", helmet, parent, 0.0)
    B("Halo Stütze", (0.05, 0.05, 0.30), (0.85, 0, 0.84), carbon, 0.015, (0, -0.35, 0))
    for s_ in (1, -1):
        B(f"Halo Bogen {s_}", (1.0, 0.04, 0.05), (0.38, 0.23 * s_, 0.98), carbon, 0.015)
        B(f"Seitenkasten {s_}", (1.9, 0.42, 0.36), (-0.2, 0.50 * s_, 0.37), body, 0.14)
        B(f"Einlass {s_}", (0.22, 0.34, 0.26), (0.78, 0.50 * s_, 0.40), carbon, 0.06)
        B(f"Endplatte vorn {s_}", (0.55, 0.04, 0.24), (2.62, 0.90 * s_, 0.20), carbon, 0.012)
        B(f"Endplatte hinten {s_}", (0.62, 0.04, 0.62), (-2.30, 0.50 * s_, 0.82), body, 0.015)
        B(f"Querlenker vorn {s_}", (0.07, 0.55, 0.035), (1.72, 0.55 * s_, 0.34), carbon, 0.01)
        B(f"Querlenker hinten {s_}", (0.07, 0.55, 0.035), (-1.62, 0.55 * s_, 0.40), carbon, 0.01)
    B("Frontflügel", (0.42, 1.84, 0.04), (2.68, 0, 0.12), carbon, 0.012)
    B("Frontflügel oben", (0.26, 1.70, 0.03), (2.56, 0, 0.22), carbon, 0.01, (0, 0.12, 0))
    B("Heckflügel", (0.52, 0.98, 0.045), (-2.28, 0, 0.92), carbon, 0.012)
    B("Heckflügel oben", (0.32, 0.98, 0.035), (-2.34, 0, 1.06), carbon, 0.01, (0, -0.22, 0))
    B("Heckflügel Stütze", (0.12, 0.08, 0.46), (-2.08, 0, 0.72), carbon, 0.02)
    B("Diffusor", (0.75, 1.0, 0.16), (-2.02, 0, 0.30), carbon, 0.02, (0, -0.18, 0))
    B("Rücklicht", (0.03, 0.22, 0.07), (-2.40, 0, 0.36), taillight, 0.0)
    for s_ in (1, -1):
        _wheel(f"{name} Rad vorn {s_}", 1.75, 0.84 * s_, 0.33, 0.38, rubber, parent)
        _wheel(f"{name} Felge vorn {s_}", 1.75, 0.84 * s_, 0.21, 0.41, rim, parent, 0.012)
        _wheel(f"{name} Rad hinten {s_}", -1.65, 0.84 * s_, 0.36, 0.50, rubber, parent)
        _wheel(f"{name} Felge hinten {s_}", -1.65, 0.84 * s_, 0.23, 0.53, rim, parent, 0.012)


def import_car_model(path: Path, parent, yaw_deg: float):
    """Eigenes Modell importieren und an das Auto-Empty hängen (Maßstab steckt im Empty)."""
    before = set(bpy.data.objects)
    ext = path.suffix.lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    else:
        raise ValueError(f"Auto-Modell {ext} nicht unterstützt (glb, gltf, fbx)")
    new = [o for o in bpy.data.objects if o not in before]
    pivot = bpy.data.objects.new(f"{parent.name} Modell", None)
    link(pivot)
    pivot.parent = parent
    pivot.rotation_euler = (0, 0, math.radians(yaw_deg))
    for o in new:
        if o.parent is None or o.parent not in new:
            o.parent = pivot
    return pivot


# ── Aufbereitetes Modell: „F1 2026 concept (polygon model)“ von Qvist_designs (CC BY 4.0) ──────────
# Die Datei ist ein einziges weißes Netz (1,2 Mio. Dreiecke, ein Material, mm, Z-hoch ohne Umrechnung,
# Nase nach −x). Wir drehen/skalieren es, trennen die vier Räder anhand der Geometrie ab (damit sie sich
# drehen und eigene Materialien bekommen), färben die Karosserie in der Teamfarbe und vereinfachen das Netz.
# Das Ergebnis wird einmal als .blend neben dem Modell zwischengespeichert.

CAR_MODEL_MATCH = "f1_2026_concept"
CAR_PREP_VERSION = 1
WHEEL_NAMES = ("VL", "VR", "HL", "HR")       # vorn links/rechts, hinten links/rechts
CAR_WHEELS: dict = {}                        # Fahrer → [(Rad-Objekt, Radius in m)], wird von build_cars gefüllt


def _coords(me) -> np.ndarray:
    a = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", a)
    return a.reshape(-1, 3)


def classify_wheel_parts(boxes: list) -> dict:
    """boxes: je Teil (xmin, xmax, ymin, ymax, zmin, zmax) in Metern, Auto steht auf z = 0, Nase nach +x.
    Liefert {"tyres": [4 Indizes], "members": {Reifen-Index: [Indizes der Teile im Rad]}}.
    Ein Reifen ist rund (Breite ≈ Höhe 0,55–0,9 m), steht auf dem Boden und sitzt seitlich vom Auto. Zum Rad
    gehört, was ganz innerhalb des Radzylinders liegt (Felge, Nabe, Bremse) – Aufhängungsarme ragen heraus."""
    b = np.asarray(boxes, dtype=float)
    dx, dy, dz = b[:, 1] - b[:, 0], b[:, 3] - b[:, 2], b[:, 5] - b[:, 4]
    cy = (b[:, 2] + b[:, 3]) / 2
    ok = (dx > 0.55) & (dx < 0.9) & (dz > 0.55) & (dz < 0.9) & (np.abs(dx - dz) < 0.1) & (dy > 0.2) & (dy < 0.6) \
        & (b[:, 4] > -0.05) & (b[:, 4] < 0.1) & (np.abs(cy) > 0.45)
    tyres = [int(i) for i in np.flatnonzero(ok)]
    if len(tyres) != 4:
        raise ValueError(f"Erwartet 4 Reifen im Modell, gefunden {len(tyres)} – Modell/Profil passen nicht zusammen")
    members: dict = {}
    for t in tyres:
        cx, cz, r = (b[t, 0] + b[t, 1]) / 2, (b[t, 4] + b[t, 5]) / 2, dx[t] / 2
        side = 1.0 if cy[t] > 0 else -1.0                 # Bremse/Nabe reichen zur Fahrzeugmitte hin über den Reifen hinaus
        lo = b[t, 2] - (0.12 if side > 0 else 0.02)
        hi = b[t, 3] + (0.02 if side > 0 else 0.12)
        inner = (b[:, 0] > cx - r - 0.01) & (b[:, 1] < cx + r + 0.01) & (b[:, 4] > cz - r - 0.01) & \
                (b[:, 5] < cz + r + 0.01) & (b[:, 2] > lo) & (b[:, 3] < hi)
        members[t] = [int(i) for i in np.flatnonzero(inner) if i != t]
    return {"tyres": tyres, "members": members}


def carbon_faces(centres: np.ndarray) -> np.ndarray:
    """Flächenmittelpunkte (n×3, Meter, Nase +x) → True, wo Carbon statt Teamfarbe: Unterboden und Diffusor,
    Frontflügel, Heckflügel samt Endplatten."""
    x, z = centres[:, 0], centres[:, 2]
    return (z < 0.15) | (x > 2.30) | (x < -1.92)


def prepare_car_model(path: Path, decimate: float):
    """Modell aufbereiten → (Karosserie-Objekt, {Radname: Objekt mit Ursprung in der Radachse}, Radradius)."""
    import time
    t0 = time.time()
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    helpers = [o.name for o in new if o.type != "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    car = bpy.context.view_layer.objects.active
    car.parent = None
    car.matrix_world = Matrix.Identity(4)
    for name in helpers:                               # leere Hilfsobjekte des Importers
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name])
    me = car.data
    # Rohdaten: Z hoch, Länge in x, mm. Nase zeigt dort nach −x; Radstand-Mitte in den Ursprung, Reifen auf z = 0
    me.transform(Matrix.Rotation(math.radians(-90), 4, "X"))
    me.transform(Matrix.Scale(0.001, 4))
    co = _coords(me)
    me.transform(Matrix.Translation((0.0, 0.0, -float(co[:, 2].min()))))
    me.transform(Matrix.Rotation(math.pi, 4, "Z"))
    # Radstandmitte → Ursprung: erst die Räder suchen
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")
    parts = [o for o in bpy.data.objects if o.type == "MESH" and o not in before]
    boxes = []
    for o in parts:
        c = _coords(o.data)
        boxes.append((c[:, 0].min(), c[:, 0].max(), c[:, 1].min(), c[:, 1].max(), c[:, 2].min(), c[:, 2].max()))
    cls = classify_wheel_parts(boxes)
    tyre_x = [(boxes[t][0] + boxes[t][1]) / 2 for t in cls["tyres"]]
    shift = -(max(tyre_x) + min(tyre_x)) / 2
    print(f"[car] {len(parts)} Teile, 4 Reifen, Radstandmitte bei x={-shift:+.3f} ({time.time() - t0:.1f}s)")

    def tag(o, slot):
        n = len(o.data.polygons)
        o.data.polygons.foreach_set("material_index", np.full(n, slot, dtype=np.int32))

    for name in ("paint", "carbon", "rubber", "rim"):
        if f"slot_{name}" not in bpy.data.materials:
            bpy.data.materials.new(f"slot_{name}")
    mats = {n: bpy.data.materials[f"slot_{n}"] for n in ("paint", "carbon", "rubber", "rim")}
    in_wheel = {i for ms in cls["members"].values() for i in ms} | set(cls["tyres"])
    body_parts = []
    for i, o in enumerate(parts):
        if i in in_wheel:
            continue
        o.data.materials.clear()
        o.data.materials.append(mats["paint"])
        o.data.materials.append(mats["carbon"])
        body_parts.append(o)

    def join(objs):
        bpy.ops.object.select_all(action="DESELECT")
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        if len(objs) > 1:
            bpy.ops.object.join()
        return bpy.context.view_layer.objects.active

    wheels = {}
    radius = 0.0
    order = sorted(cls["tyres"], key=lambda t: (-(boxes[t][0] + boxes[t][1]), -(boxes[t][2] + boxes[t][3])))   # vorn zuerst, links (+y) zuerst
    for name, t in zip(WHEEL_NAMES, order):
        for i in [t] + cls["members"][t]:
            o = parts[i]
            o.data.materials.clear()
            o.data.materials.append(mats["rubber"])
            o.data.materials.append(mats["rim"])
            tag(o, 0 if i == t else 1)
        w = join([parts[i] for i in [t] + cls["members"][t]])
        w.name = f"CAR_RAD_{name}"
        b = boxes[t]
        centre = Vector(((b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2))
        w.data.transform(Matrix.Translation(-centre))
        w.location = centre
        w["radius"] = (b[1] - b[0]) / 2
        radius = (b[1] - b[0]) / 2
        wheels[name] = w
    body = join(body_parts)
    body.name = "CAR_KAROSSERIE"
    body.data.transform(Matrix.Translation((shift, 0, 0)))      # Radstandmitte → Ursprung (vor der Carbon-Einteilung)
    ctr = np.empty(len(body.data.polygons) * 3, dtype=np.float64)
    body.data.polygons.foreach_get("center", ctr)
    body.data.polygons.foreach_set("material_index", carbon_faces(ctr.reshape(-1, 3)).astype(np.int32))
    if 0.0 < decimate < 1.0:
        mod = body.modifiers.new("vereinfachen", "DECIMATE")
        mod.ratio = decimate
        bpy.context.view_layer.objects.active = body
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for w in wheels.values():
        w.location.x += shift
    print(f"[car] aufbereitet: Karosserie {len(body.data.polygons):,} Flächen, Radradius {radius:.3f} m ({time.time() - t0:.1f}s)")
    return body, wheels, radius


def load_car_template(path: Path, decimate: float, rebuild: bool = False):
    """Aufbereitetes Modell aus dem Zwischenspeicher holen (oder erzeugen). → (Karosserie, Räder, Radradius),
    Objekte sind nicht in der Szene verlinkt; nur ihre Netze werden weiterverwendet."""
    cache = path.with_name(f"{path.stem}.prep{CAR_PREP_VERSION}-d{int(round(decimate * 100)):03d}.blend")
    if cache.exists() and not rebuild and cache.stat().st_mtime >= path.stat().st_mtime:
        with bpy.data.libraries.load(str(cache)) as (src, dst):
            dst.objects = list(src.objects)
        objs = {o.name: o for o in dst.objects}
        wheels = {n: objs[f"CAR_RAD_{n}"] for n in WHEEL_NAMES}
        print(f"[car] aus Zwischenspeicher: {cache.name}")
        return objs["CAR_KAROSSERIE"], wheels, float(wheels[WHEEL_NAMES[0]]["radius"])
    body, wheels, radius = prepare_car_model(path, decimate)
    try:
        bpy.data.libraries.write(str(cache), {body, *wheels.values()}, fake_user=True)
        print(f"[car] Zwischenspeicher geschrieben: {cache.name}")
    except Exception as e:                        # nur eine Beschleunigung, kein Muss
        print(f"[car] Zwischenspeicher nicht möglich ({e})")
    return body, wheels, radius


def build_model_cars(d: dict, path: Path, decimate: float, rebuild: bool, yaw: float) -> dict:
    meta = d["meta"]
    body, wheels, radius = load_car_template(path, decimate, rebuild)
    cars = {}
    for drv in (meta["a"], meta["b"]):
        empty = bpy.data.objects.new(f"Auto {drv}", None)
        link(empty)
        empty.rotation_mode = "XYZ"
        pivot = bpy.data.objects.new(f"{drv} Modell", None)
        link(pivot)
        pivot.parent = empty
        pivot.rotation_euler = (0, 0, math.radians(yaw))
        al = 0.45 if meta.get("ghost") == drv else 1.0
        mats = {
            "paint": solid_material(f"{drv} Lack", meta["colors"][drv], 0.25, 0.25, alpha=al, specular=0.5),
            "carbon": solid_material(f"{drv} Carbon", (0.045, 0.045, 0.05), 0.35, 0.15, alpha=al, specular=0.4),
            "rubber": solid_material(f"{drv} Reifen", (0.02, 0.02, 0.022), 0.85, alpha=al, specular=0.2),
            "rim": solid_material(f"{drv} Felge", (0.55, 0.55, 0.58), 0.3, 1.0, alpha=al),
        }
        order = {"body": ("paint", "carbon"), "wheel": ("rubber", "rim")}

        def instance(name, tmpl, kinds):
            o = bpy.data.objects.new(f"{drv} {name}", tmpl.data)
            link(o)
            o.parent = pivot
            o.location = tmpl.location
            o.rotation_mode = "XYZ"
            for slot, kind in zip(o.material_slots, kinds):
                slot.link = "OBJECT"
                slot.material = mats[kind]
            return o

        instance("Karosserie", body, order["body"])
        CAR_WHEELS[drv] = [(instance(f"Rad {n}", w, order["wheel"]), radius) for n, w in wheels.items()]
        cars[drv] = empty
    for o in [body, *wheels.values()]:               # Vorlagen entfernen, Netze bleiben über die Instanzen
        bpy.data.objects.remove(o)
    return cars


def build_cars(d: dict, car_path, scale, yaw, decimate: float = 0.35, rebuild: bool = False):
    meta = d["meta"]
    if scale is None:
        scale = PLACEHOLDER_SCALE
    CAR_WHEELS.clear()
    if car_path:
        car_path = Path(car_path).resolve()           # relative Pfade deutet Blender selbst (Laufwerkswurzel)
    if car_path and CAR_MODEL_MATCH in Path(car_path).name.lower():
        cars = build_model_cars(d, Path(car_path), decimate, rebuild, yaw)
        for empty in cars.values():
            empty.scale = (scale, scale, scale)
        return cars
    if car_path and scale == PLACEHOLDER_SCALE:
        scale = 1.0
    cars = {}
    for drv in (meta["a"], meta["b"]):
        empty = bpy.data.objects.new(f"Auto {drv}", None)
        link(empty)
        empty.rotation_mode = "XYZ"
        empty.scale = (scale, scale, scale)
        ghost = meta.get("ghost") == drv
        if car_path:
            import_car_model(Path(car_path), empty, yaw)
        else:
            build_placeholder_car(drv, meta["colors"][drv], ghost, empty)
        cars[drv] = empty
    return cars


# ── Licht, Himmel ────────────────────────────────────────────────────────────

LIGHT_PRESETS = {
    # sun: (Höhe über Horizont °, Richtung °, Stärke, Farbe); sky = Helligkeit des sichtbaren Himmels
    # (1,0 = Palettenfarbe wie angegeben), amb = Umgebungslicht aus dem Himmel; fog = Dichte;
    # follow = Begleitlicht (W)
    "day": dict(sun=(52, 140, 3.0, (1.0, 0.96, 0.9)), sky=1.0, amb=0.60, fog=0.0006, follow=0),
    "dusk": dict(sun=(12, 140, 2.4, (1.0, 0.62, 0.38)), sky=1.0, amb=6.0, fog=0.0010, follow=1500),
    "night": dict(sun=(64, 140, 1.7, (0.78, 0.86, 1.0)), sky=1.0, amb=5.0, fog=0.0012, follow=3000),   # sun = Flutlicht von oben
    "rain": dict(sun=(40, 140, 0.8, (0.85, 0.9, 1.0)), sky=1.0, amb=1.1, fog=0.0035, follow=0),
}


def _clouds(nt, sep, sky, covered: float, tint) -> "bpy.types.NodeSocket":
    """Wolken in den Himmelsverlauf mischen: Rauschen auf die Himmelskuppel projiziert (x/z, y/z), zum
    Horizont hin ausgeblendet. covered 0…1 = Anteil bedeckter Himmel."""
    N = Nodes(type("W", (), {"node_tree": nt})())
    z = sep.outputs["Z"]
    k = N.math("ADD", z, 0.18)
    cx, cy = N.math("DIVIDE", sep.outputs["X"], k), N.math("DIVIDE", sep.outputs["Y"], k)
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(cx, comb.inputs["X"])
    nt.links.new(cy, comb.inputs["Y"])
    big = N.noise(comb.outputs["Vector"], 1.3, 5.0)
    puff = N.noise(comb.outputs["Vector"], 5.0, 4.0)
    dens = N.math("ADD", big, N.math("MULTIPLY", N.math("SUBTRACT", puff, 0.5), 0.35))
    lo = 1.0 - covered
    cover = N.smooth(dens, lo - 0.02, lo + 0.22)
    fade = N.smooth(z, 0.03, 0.30)
    amount = N.math("MULTIPLY", N.math("MULTIPLY", cover, fade), 0.92)
    under = N.math("SUBTRACT", 1.0, N.math("MULTIPLY", N.smooth(dens, lo + 0.1, lo + 0.45), 0.18))   # Unterseite grauer
    white = N.mix(N.math("SUBTRACT", 1.0, under), rgba(np.array(tint)), rgba(np.array(tint) * 0.80))
    return N.mix(amount, sky, white)


def build_world(d: dict, fog: bool = False):
    meta, pal = d["meta"], d["env"]["palette"]
    p = LIGHT_PRESETS.get(meta["light"], LIGHT_PRESETS["day"])
    world = bpy.data.worlds.new("Welt")
    bpy.context.scene.world = world
    set_safe(world, "use_nodes", True)
    nt = world.node_tree
    bg = nt.nodes["Background"]
    out = nt.nodes["World Output"]
    elev, azim, energy, col = p["sun"]
    # Himmel als Verlauf (Palette aus chase3d): unten die Horizont-Farbe, knapp darüber helles Dunstblau,
    # oben die Himmelsfarbe. Berechnet aus der Blickrichtung – ohne Sonnenscheibe, ohne ausgebrannten Rand.
    try:
        hor, haze, top = horizon_color(pal), to_rgb(pal["sky_hor"]), to_rgb(pal["sky_top"])
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
        nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
        cr = ramp.color_ramp
        cr.elements[0].position, cr.elements[0].color = 0.0, rgba(hor)
        cr.elements[1].position, cr.elements[1].color = 0.40, rgba(top)
        mid = cr.elements.new(0.08)
        mid.color = rgba(haze)
        sky = ramp.outputs["Color"]
        if meta["light"] in ("day", "dusk", "rain"):
            hz = to_rgb(pal["sky_hor"])
            tint = {"day": (1.0, 0.97, 0.94), "rain": (0.62, 0.63, 0.66)}.get(meta["light"])
            if tint is None:                                   # Abend: Wolken nehmen die Himmelsfarbe an, nicht Weiß
                tint = np.clip(0.35 * np.ones(3) + 0.55 * hz, 0, 1) * 0.8
            sky = _clouds(nt, sep, sky, covered=0.78 if meta["light"] == "rain" else 0.55, tint=tint)
        nt.links.new(sky, bg.inputs["Color"])
    except (KeyError, RuntimeError, StopIteration):
        bg.inputs["Color"].default_value = rgba(pal["sky_hor"])
    # sichtbarer Himmel (Kamerastrahlen) hell, Umgebungslicht für alles andere schwächer – sonst
    # wirken Asphalt und Gras vom hellen Himmel überstrahlt
    bg.inputs["Strength"].default_value = p["sky"]
    try:
        lp = nt.nodes.new("ShaderNodeLightPath")
        mix = nt.nodes.new("ShaderNodeMath")
        mix.operation = "MULTIPLY_ADD"                       # is_camera * (sichtbar − ambient) + ambient
        nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
        mix.inputs[1].default_value = p["sky"] - p["amb"]
        mix.inputs[2].default_value = p["amb"]
        nt.links.new(mix.outputs["Value"], bg.inputs["Strength"])
    except (KeyError, RuntimeError):
        bg.inputs["Strength"].default_value = p["amb"]
    # Dunst (Volumen-Streuung in der Welt) – wie der Nebel im alten Bild; Rain deutlich dichter.
    # STANDARD AUS: in Cycles (5.2.2, Test ohne GPU) macht schon ein Welt-Volumen das ganze Bild schwarz,
    # egal wie klein die Dichte. In EEVEE nicht geprüft → nur mit --fog, bei schwarzem Bild weglassen.
    if fog and p["fog"] > 0:
        try:
            vs = nt.nodes.new("ShaderNodeVolumeScatter")
            vs.inputs["Density"].default_value = p["fog"]
            vs.inputs["Color"].default_value = rgba(pal["fog"])
            nt.links.new(vs.outputs["Volume"], out.inputs["Volume"])
        except (KeyError, RuntimeError):
            pass
    sun = bpy.data.lights.new("Sonne", "SUN")
    sun.energy = energy if energy > 0 else 0.05          # Nacht: nur ein Hauch Mondlicht
    sun.color = col[:3]
    set_safe(sun, "angle", math.radians(0.6 if meta["light"] == "day" else 3.0))
    so = link(bpy.data.objects.new("Sonne", sun))
    so.rotation_euler = Euler((math.radians(90 - elev), 0, math.radians(azim)), "XYZ")
    follow = None
    if p["follow"] > 0:
        pl = bpy.data.lights.new("Begleitlicht", "POINT")
        pl.energy = p["follow"]
        pl.color = (1.0, 0.92, 0.82)
        set_safe(pl, "shadow_soft_size", 3.0)
        follow = link(bpy.data.objects.new("Begleitlicht", pl))
    return follow


# ── Kamera und Bewegung ──────────────────────────────────────────────────────

def build_camera(d: dict, scale: float, fov_v: float | None = None):
    meta = d["meta"]
    cam = bpy.data.cameras.new("Verfolger")
    cam.sensor_fit = "VERTICAL"
    cam.sensor_height = 24.0
    cam.lens = cam.sensor_height / (2 * math.tan(math.radians(fov_v or meta["fov_v_deg"]) / 2))
    cam.clip_start, cam.clip_end = 0.5, 6000.0
    obj = link(bpy.data.objects.new("Verfolger", cam))
    obj.rotation_mode = "XYZ"
    sc = bpy.context.scene
    sc.camera = obj
    sc.render.resolution_x = int(round(meta["width_px"] * scale))
    sc.render.resolution_y = int(round(meta["height_px"] * scale))
    sc.render.resolution_percentage = 100
    sc.render.fps = int(meta["fps"])
    return obj


def key_motion(d: dict, cars: dict, cam, follow):
    """Pro Bild ein Schlüsselbild (Position, Drehung). Lineare Zwischenwerte: kein Überschwingen,
    und Bewegungsunschärfe funktioniert nur mit animierten Objekten."""
    set_safe(bpy.context.preferences.edit, "keyframe_new_interpolation_type", "LINEAR")
    fr = d["frames"]
    n = len(fr["t"])
    cam_pos = np.array(fr["camera"]["pos"])
    cam_fwd = np.array(fr["camera"]["forward"])
    car_pos = {k: np.array(v["pos"]) for k, v in fr["cars"].items()}
    car_yaw = {k: np.array(v["yaw_rad"]) for k, v in fr["cars"].items()}
    car_pitch = {k: np.array(v.get("pitch_rad", np.zeros(n))) for k, v in fr["cars"].items()}
    # zurückgelegter Weg je Auto → Raddrehung (Rad rollt ohne Schlupf)
    roll = {k: np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))] for k, p in car_pos.items()}
    prev = Euler((0, 0, 0))
    for i in range(n):
        f = i + 1
        for drv, empty in cars.items():
            empty.location = car_pos[drv][i]
            # Neigung der Strecke: Blender dreht um +y die Nase nach unten, „Nase hoch“ ist also negativ
            empty.rotation_euler = (0, -float(car_pitch[drv][i]), float(car_yaw[drv][i]))
            empty.keyframe_insert("location", frame=f)
            empty.keyframe_insert("rotation_euler", frame=f)
            for wheel, radius in CAR_WHEELS.get(drv, ()):
                wheel.rotation_euler = (0, float(roll[drv][i] / radius), 0)       # +y: Rad rollt nach +x
                wheel.keyframe_insert("rotation_euler", frame=f)
        cam.location = cam_pos[i]
        q = Vector(cam_fwd[i]).to_track_quat("-Z", "Y")
        e = q.to_euler("XYZ", prev)
        prev = e
        cam.rotation_euler = e
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
        if follow is not None:
            follow.location = cam_pos[i] + np.array([0.0, 0.0, 8.0]) + cam_fwd[i] * np.array([12.0, 12.0, 0.0])
            follow.keyframe_insert("location", frame=f)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, n


# ── Rendern ──────────────────────────────────────────────────────────────────

def configure_render(engine: str, samples: int | None, motion_blur: bool):
    sc = bpy.context.scene
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    if engine == "cycles":
        sc.render.engine = "CYCLES"
        sc.cycles.samples = samples or 96
        set_safe(sc.cycles, "use_denoising", True)
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
                try:
                    prefs.compute_device_type = kind
                    prefs.get_devices()
                    if any(dev.type != "CPU" for dev in prefs.devices):
                        for dev in prefs.devices:
                            dev.use = True
                        sc.cycles.device = "GPU"
                        break
                except (TypeError, ValueError):
                    continue
        except (KeyError, AttributeError):
            pass
    else:
        eevee = [e for e in engines if "EEVEE" in e]
        sc.render.engine = eevee[0]                  # 5.x: BLENDER_EEVEE; 4.2–4.5: BLENDER_EEVEE_NEXT
        set_safe(sc.eevee, "taa_render_samples", samples or 48)
        set_safe(sc.eevee, "use_raytracing", True)
        set_safe(sc.eevee, "use_shadows", True)
        set_safe(sc.eevee, "use_volumetric_shadows", True)
    # „Standard“ statt AgX: AgX entsättigt und hellt auf – die Farben der Palette (aus dem
    # matplotlib-Bild übernommen) sollen so aussehen, wie sie angegeben sind.
    set_safe(sc.view_settings, "view_transform", "Standard")
    set_safe(sc.view_settings, "look", "None")
    set_safe(sc.render, "use_motion_blur", motion_blur)
    set_safe(sc.render, "motion_blur_shutter", 0.35)
    sc.render.film_transparent = False


def render_output(out: Path, video: bool, still: int | None):
    sc = bpy.context.scene
    out.parent.mkdir(parents=True, exist_ok=True)
    if still is not None:
        sc.render.image_settings.file_format = "PNG"
        sc.render.filepath = str(out.with_suffix(".png"))
        sc.frame_set(still + 1)
        bpy.ops.render.render(write_still=True)
        return sc.render.filepath
    if video:
        try:
            sc.render.image_settings.file_format = "FFMPEG"
            sc.render.ffmpeg.format = "MPEG4"
            sc.render.ffmpeg.codec = "H264"
            sc.render.ffmpeg.constant_rate_factor = "HIGH"
            sc.render.filepath = str(out.with_suffix(""))        # Blender hängt .mp4 selbst an
            bpy.ops.render.render(animation=True)
            return str(out.with_suffix(".mp4"))
        except (TypeError, ValueError, RuntimeError) as exc:
            print(f"[blender_render] MP4 nicht möglich ({exc}) – schreibe PNG-Folge", file=sys.stderr)
    sc.render.image_settings.file_format = "PNG"
    folder = out.with_suffix("")
    folder.mkdir(parents=True, exist_ok=True)
    sc.render.filepath = str(folder / "frame_")
    bpy.ops.render.render(animation=True)
    return str(folder)


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="blender_render", description=__doc__.split("\n")[0])
    ap.add_argument("scene_json")
    ap.add_argument("out")
    ap.add_argument("--engine", choices=("eevee", "cycles"), default="eevee")
    ap.add_argument("--samples", type=int)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--still", type=int)
    ap.add_argument("--frames")
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--car")
    ap.add_argument("--car-scale", type=float, default=None)
    ap.add_argument("--car-yaw", type=float, default=0.0)
    ap.add_argument("--car-decimate", type=float, default=0.35,
                    help="Anteil der Flächen, die vom Modell bleiben (1 = alles). Nur beim ersten Aufbereiten")
    ap.add_argument("--car-rebuild", action="store_true", help="Zwischenspeicher des aufbereiteten Modells neu erzeugen")
    ap.add_argument("--motion-blur", type=int, choices=(0, 1), default=1)
    ap.add_argument("--fov", type=float, default=FOV_V, help=f"vertikaler Bildwinkel in Grad (Standard {FOV_V}; kleiner = Autos größer)")
    ap.add_argument("--fog", action="store_true", help="Dunst (Welt-Volumen); kann das Bild schwarz machen")
    return ap.parse_args(argv)


def build_scene(d: dict, args: argparse.Namespace):
    if d.get("schema") != 1:
        raise ValueError(f"Unbekanntes Schema {d.get('schema')!r} – blender_export.py und blender_render.py passen nicht zusammen")
    clear_scene()
    build_track(d)
    build_kerbs_and_barriers(d)
    build_guardrail(d)
    build_lamps(d)
    build_hills(d)
    build_trees(d)
    build_buildings(d)
    build_gantry_and_finish(d)
    follow = build_world(d, args.fog)
    cars = build_cars(d, args.car, args.car_scale, args.car_yaw, args.car_decimate, args.car_rebuild)
    cam = build_camera(d, args.scale, args.fov)
    key_motion(d, cars, cam, follow)
    configure_render(args.engine, args.samples, bool(args.motion_blur))
    return cars, cam


def main(argv: list[str]) -> str:
    args = parse_args(argv)
    d = json.loads(Path(args.scene_json).read_text(encoding="utf-8"))
    build_scene(d, args)
    sc = bpy.context.scene
    if args.frames:
        a, b = (int(v) for v in args.frames.split(":"))
        sc.frame_start, sc.frame_end = a + 1, b
    # absolut machen: Blender deutet relative Pfade selbst (bei dir landete das Bild in C:\output)
    result = render_output(Path(args.out).resolve(), args.video, args.still)
    print(f"[blender_render] fertig: {result}")
    return result


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
