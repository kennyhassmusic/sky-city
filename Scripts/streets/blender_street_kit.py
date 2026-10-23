"""Sky City street kit, modelled in Blender (headless) and exported as GLB, one file per asset.

Real-world sizes (metres). Every prop is built at the origin, standing on z = 0, with its "front" (the side a
driver sees: sign faces, lamp arms, signal heads) facing Blender -Y, which Unreal's glTF import turns into +X.
A signal's mast arm reaches toward Blender -X (Unreal +Y), i.e. across the lanes to the driver's left.
Material slot names are what Unreal maps to its own materials (M_* -> MI_*).

Trees are procedural (trunk, limbs, branches as tapered tubes; leaf-cluster cards from make_leaf_textures.py):
  liveoak (broad, low, spreading - Austin), honeylocust (open vase, airy), linden (dense oval), elm (vase).

Run: /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/streets/blender_street_kit.py
     add `-- curbs` to export only SK_Curb_Bevel, SK_Gutter_Pan and SK_Curb_Ramp.
Importing this file does not build anything. The block preview calls the prop functions with do_export=False.
Output: SourceArt/StreetKit/meshes/<name>.glb
"""
import math, os, random, sys
import bpy, bmesh
from mathutils import Matrix, Vector

import os


def _skycity_root():
    """Project folder: $SKYCITY_ROOT, else the folder above this script that holds SkyCity.uproject."""
    env = os.environ.get("SKYCITY_ROOT")
    if env:
        return env
    try:
        d = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        d = None
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "SkyCity.uproject")):
            return d
        d = os.path.dirname(d)
    raise RuntimeError("Cannot find the SkyCity project folder (SkyCity.uproject): set SKYCITY_ROOT")


ROOT = _skycity_root()
OUT = ROOT + "/SourceArt/StreetKit/meshes"
os.makedirs(OUT, exist_ok=True)
ONLY = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


MATS = {}


def mat(name, rgb=(0.5, 0.5, 0.5), metal=0.0, rough=0.6):
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    MATS[name] = m
    return m


# Leaf clusters and bark from Scripts/streets/make_leaf_textures.py (CC0 ambientCG scans).
# The flat green on M_Leaves_* is only the fallback when those PNGs are not on disk.
CLUSTER = {
    "M_Leaves_liveoak": "T_Leaves_liveoak",
    "M_Leaves_honeylocust": "T_Leaves_honeylocust",
    "M_Leaves_linden": "T_Leaves_linden",
    "M_Leaves_elm": "T_Leaves_elm",
    "M_Bark": "T_Bark",
}


def bind_cluster(material):
    """Put the species' CC0 cluster on the material and clip the card to the leaves."""
    stem = CLUSTER.get(material.name)
    if not stem or material.get("cluster"):
        return
    folder = os.path.join(ROOT, "SourceArt", "StreetKit", "textures")
    color = os.path.join(folder, stem + "_C.png")
    if not os.path.isfile(color):
        return
    nt = material.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    img = bpy.data.images.load(color, check_existing=True)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if stem.startswith("T_Leaves"):
        nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
        material.use_backface_culling = False
        for attr, value in (("blend_method", "CLIP"), ("shadow_method", "CLIP")):
            if hasattr(material, attr):
                try:
                    setattr(material, attr, value)
                except TypeError:
                    pass
        if hasattr(material, "alpha_threshold"):
            material.alpha_threshold = 0.45
    normal = os.path.join(folder, stem + "_N.png")
    if os.path.isfile(normal):
        nimg = bpy.data.images.load(normal, check_existing=True)
        try:
            nimg.colorspace_settings.name = "Non-Color"
        except TypeError:
            pass
        ntex = nt.nodes.new("ShaderNodeTexImage")
        ntex.image = nimg
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    material["cluster"] = stem


class Builder:
    """Accumulates geometry into one bmesh with per-face material indices."""

    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.mats = []

    def mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def face(self, verts, m, uvs=None):
        vs = [self.bm.verts.new(v) for v in verts]
        f = self.bm.faces.new(vs)
        f.material_index = self.mi(m)
        if uvs:
            for l, uv in zip(f.loops, uvs):
                l[self.uv].uv = uv
        return f

    def box(self, c, size, m, rot=Matrix.Identity(3)):
        cx, cy, cz = c
        sx, sy, sz = (s / 2 for s in size)
        P = [rot @ Vector((x * sx, y * sy, z * sz)) + Vector(c) for x, y, z in
             ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))]
        for idx in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            pts = [P[i] for i in idx]
            e1, e2 = (pts[1] - pts[0]).length, (pts[3] - pts[0]).length
            self.face(pts, m, [(0, 0), (e1, 0), (e1, e2), (0, e2)])

    def tube(self, path, radii, m, sides=8, cap=True, uv_v_scale=1.0):
        """A tapered tube along a list of points."""
        rings = []
        n = len(path)
        acc = 0.0
        for i, p in enumerate(path):
            p = Vector(p)
            a = Vector(path[max(0, i - 1)])
            b = Vector(path[min(n - 1, i + 1)])
            t = (b - a).normalized()
            up = Vector((0, 0, 1)) if abs(t.z) < 0.95 else Vector((1, 0, 0))
            x = t.cross(up).normalized()
            y = t.cross(x).normalized()
            if i:
                acc += (p - Vector(path[i - 1])).length
            ring = []
            for k in range(sides + 1):
                ang = 2 * math.pi * k / sides
                ring.append((p + (x * math.cos(ang) + y * math.sin(ang)) * radii[i], k / sides, acc * uv_v_scale))
            rings.append(ring)
        for r0, r1 in zip(rings, rings[1:]):
            for k in range(sides):
                a, b, c, d = r0[k], r0[k + 1], r1[k + 1], r1[k]
                self.face([a[0], b[0], c[0], d[0]], m, [(a[1], a[2]), (b[1], b[2]), (c[1], c[2]), (d[1], d[2])])
        if cap:
            r = rings[-1]
            self.face([r[k][0] for k in range(sides)][::-1] if False else [r[k][0] for k in range(sides)], m)

    def cyl(self, base, height, radius, m, sides=12, top=True):
        self.tube([base, (base[0], base[1], base[2] + height)], [radius, radius], m, sides, cap=top)

    def card(self, center, normal, up, w, h, m, uv=((0, 0), (1, 0), (1, 1), (0, 1)), double=False):
        n = Vector(normal).normalized()
        u = Vector(up)
        x = u.cross(n).normalized()
        y = n.cross(x).normalized()
        c = Vector(center)
        P = [c - x * w / 2 - y * h / 2, c + x * w / 2 - y * h / 2, c + x * w / 2 + y * h / 2, c - x * w / 2 + y * h / 2]
        self.face(P, m, list(uv))
        if double:
            self.face(P[::-1], m, [uv[1], uv[0], uv[3], uv[2]])

    def finish(self, name):
        bmesh.ops.recalc_face_normals(self.bm, faces=[f for f in self.bm.faces if f.material_index >= 0 and len(f.verts) > 2 and not f.hide]) if False else None
        me = bpy.data.meshes.new(name)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        return ob


def export(name, objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=f"{OUT}/{name}.glb", export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_materials="EXPORT", export_image_format="NONE")
    print("exported", name, sum(len(o.data.polygons) for o in objs), "faces")


# ------------------------------------------------------------------ props
M_STEEL = lambda: mat("M_PaintedSteelDark", (0.06, 0.065, 0.07), 0.6, 0.45)
M_GALV = lambda: mat("M_Galvanized", (0.62, 0.63, 0.64), 0.9, 0.38)
M_LENS = lambda: mat("M_LampLens", (1.0, 0.92, 0.75), 0.0, 0.2)
M_SIGHEAD = lambda: mat("M_SignalHousing", (0.04, 0.04, 0.04), 0.1, 0.5)
M_RED = lambda: mat("M_SignalRed", (0.9, 0.05, 0.03), 0.0, 0.2)
M_YEL = lambda: mat("M_SignalYellow", (0.95, 0.6, 0.02), 0.0, 0.2)
M_GRN = lambda: mat("M_SignalGreen", (0.05, 0.9, 0.5), 0.0, 0.2)
M_SIGNBACK = lambda: mat("M_SignBack", (0.55, 0.56, 0.57), 0.8, 0.5)


def street_lamp(name="SK_Lamp_Street", h=9.0, arm=2.6, double=False, do_export=True):
    B = Builder()
    s = M_STEEL()
    B.cyl((0, 0, 0), 0.6, 0.17, s, 10)                                  # base collar
    B.tube([(0, 0, 0), (0, 0, h)], [0.11, 0.07], s, 10)                 # tapered pole
    for d in ((1,) if not double else (1, -1)):
        pts = [(0, 0, h - 0.6), (0, -d * arm * 0.35, h - 0.05), (0, -d * arm * 0.75, h + 0.15), (0, -d * arm, h + 0.18)]
        B.tube(pts, [0.05, 0.045, 0.04, 0.04], s, 8, cap=False)
        # LED cobra head: tapered housing with the lens on its underside
        hx = Vector((0, -d * (arm + 0.35), h + 0.15))
        B.box(hx, (0.38, 0.8, 0.14), s)
        B.card(hx + Vector((0, 0, -0.072)), (0, 0, -1), (0, -d, 0), 0.3, 0.62, M_LENS())
    ob = B.finish(name)
    if do_export:
        export(name, [ob])
    return ob


def signal_pole(arm_len):
    name = f"SK_Signal_{int(arm_len)}m"
    B = Builder()
    s = M_STEEL()
    B.cyl((0, 0, 0), 0.7, 0.22, s, 10)
    B.tube([(0, 0, 0), (0, 0, 6.8)], [0.15, 0.11], s, 10)
    B.tube([(0, 0, 5.9), (-arm_len, 0, 6.25)], [0.1, 0.06], s, 8)        # mast arm across the lanes
    B.tube([(0, 0, 6.6), (-arm_len * 0.45, 0, 6.3)], [0.03, 0.03], s, 6)  # tie rod

    def head(x, z):
        B.box((x, 0.0, z), (0.36, 0.26, 1.08), M_SIGHEAD())
        B.box((x, 0.14, z), (0.6, 0.03, 1.3), M_SIGHEAD())               # backplate
        for k, mm in enumerate((M_RED(), M_YEL(), M_GRN())):
            zc = z + 0.33 - k * 0.33
            ring = [(x + 0.13 * math.cos(2 * math.pi * j / 12), -0.132, zc + 0.13 * math.sin(2 * math.pi * j / 12)) for j in range(12)]
            B.face(ring, mm)
            B.box((x, -0.2, zc + 0.12), (0.3, 0.14, 0.03), M_SIGHEAD())   # visor
    n = max(1, int(round(arm_len / 3.4)))
    for k in range(n):
        head(-arm_len * (k + 0.8) / (n + 0.3), 5.3)
    head(0.0, 3.0)                                                       # near-side head on the pole
    export(name, [B.finish(name)])


def sign_post(name, face_w, face_h, z_top, face_mat, uv, shape="rect"):
    B = Builder()
    B.box((0, 0.03, z_top / 2), (0.05, 0.05, z_top), M_GALV())
    zc = z_top - face_h / 2
    if shape == "oct":
        r = face_w / 2 / math.cos(math.radians(22.5))
        ring = [(r * math.cos(math.radians(22.5 + 45 * k)), -0.0, zc + r * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)]
        uvs = [(0.5 + 0.5 * math.cos(math.radians(22.5 + 45 * k)) / math.cos(math.radians(22.5)),
                0.5 + 0.5 * math.sin(math.radians(22.5 + 45 * k)) / math.cos(math.radians(22.5))) for k in range(8)]
        B.face(ring, face_mat, uvs)
        B.face([(p[0], 0.008, p[2]) for p in ring][::-1], M_SIGNBACK())
    else:
        u0, v0, u1, v1 = uv          # top-down (glTF / Unreal) texture coordinates; Blender's v runs bottom-up
        B.face([(-face_w / 2, 0, zc - face_h / 2), (face_w / 2, 0, zc - face_h / 2), (face_w / 2, 0, zc + face_h / 2), (-face_w / 2, 0, zc + face_h / 2)],
               face_mat, [(u0, 1 - v1), (u1, 1 - v1), (u1, 1 - v0), (u0, 1 - v0)])
        B.face([(-face_w / 2, 0.008, zc + face_h / 2), (face_w / 2, 0.008, zc + face_h / 2), (face_w / 2, 0.008, zc - face_h / 2), (-face_w / 2, 0.008, zc - face_h / 2)], M_SIGNBACK())
    export(name, [B.finish(name)])


def name_blade():
    """One street-name blade, readable from both sides; 0.9 x 0.18 m, centred on its post, 2.9 m up.
    UVs cover atlas cell 0 (u 0..1/8, v 0..102/4096); the material shifts them per instance."""
    B = Builder()
    m = mat("M_SignName", (0.0, 0.4, 0.28), 0.0, 0.5)
    u1, v1 = 1 / 8, 102 / 4096
    w, h, z = 0.9, 0.18, 2.9
    front = [(-w / 2, -0.006, z - h / 2), (w / 2, -0.006, z - h / 2), (w / 2, -0.006, z + h / 2), (-w / 2, -0.006, z + h / 2)]
    B.face(front, m, [(0, 1 - v1), (u1, 1 - v1), (u1, 1), (0, 1)])
    back = [(w / 2, 0.006, z - h / 2), (-w / 2, 0.006, z - h / 2), (-w / 2, 0.006, z + h / 2), (w / 2, 0.006, z + h / 2)]
    B.face(back, m, [(0, 1 - v1), (u1, 1 - v1), (u1, 1), (0, 1)])
    B.box((0, 0, z), (w + 0.02, 0.01, h + 0.02), M_GALV())
    export("SK_NameBlade", [B.finish("SK_NameBlade")])
    P = Builder()
    P.box((0, 0, 1.4), (0.06, 0.06, 2.8), M_GALV())          # ends just under the blades (bracketed on top)
    export("SK_NamePost", [P.finish("SK_NamePost")])


def bike_rack():
    B = Builder()
    g = M_GALV()
    for x in (-0.45, 0.45):
        pts = [(x, -0.3, 0.0), (x, -0.3, 0.62)]
        for k in range(1, 8):
            a = math.pi * k / 8
            pts.append((x, -0.3 * math.cos(a), 0.62 + 0.3 * math.sin(a)))
        pts += [(x, 0.3, 0.62), (x, 0.3, 0.0)]
        B.tube(pts, [0.025] * len(pts), g, 8, cap=False)
    export("SK_BikeRack", [B.finish("SK_BikeRack")])


def dumpster():
    B = Builder()
    body = mat("M_DumpsterGreen", (0.05, 0.22, 0.12), 0.4, 0.55)
    lid = mat("M_BlackPlastic", (0.03, 0.03, 0.03), 0.0, 0.6)
    # slanted-front 3-yard bin: profile extruded along X
    prof = [(0.6, 0.12), (-0.6, 0.12), (-0.6, 1.25), (0.35, 1.25), (0.6, 0.55)]
    W = 1.85
    for i in range(len(prof)):
        a, b = prof[i], prof[(i + 1) % len(prof)]
        B.face([(-W / 2, a[0], a[1]), (W / 2, a[0], a[1]), (W / 2, b[0], b[1]), (-W / 2, b[0], b[1])], body)
    B.face([(-W / 2, y, z) for y, z in prof], body)
    B.face([(W / 2, y, z) for y, z in prof][::-1], body)
    for x in (-0.47, 0.47):
        B.box((x, -0.12, 1.29), (0.9, 0.98, 0.06), lid, Matrix.Rotation(math.radians(-8), 3, "X"))
    for x in (-0.8, 0.8):
        for y in (-0.45, 0.45):
            B.cyl((x, y, 0.0), 0.12, 0.06, lid, 8)
    B.box((-W / 2 - 0.08, 0, 0.9), (0.16, 0.6, 0.12), body)          # fork pockets
    B.box((W / 2 + 0.08, 0, 0.9), (0.16, 0.6, 0.12), body)
    export("SK_Dumpster", [B.finish("SK_Dumpster")])


def bus_shelter():
    B = Builder()
    al = mat("M_Aluminium", (0.7, 0.71, 0.72), 0.9, 0.35)
    gl = mat("M_Glass", (0.6, 0.7, 0.75), 0.0, 0.05)
    L, D, H = 4.0, 1.5, 2.5
    for x in (-L / 2, L / 2):
        for y in (-D / 2, D / 2):
            B.box((x, y, H / 2), (0.08, 0.08, H), al)
    B.box((0, 0, H + 0.06), (L + 0.3, D + 0.3, 0.12), al)
    B.card((0, D / 2, 1.3), (0, -1, 0), (0, 0, 1), L, 2.1, gl, double=True)
    for x in (-L / 2, L / 2):
        B.card((x, 0, 1.3), (1, 0, 0), (0, 0, 1), D, 2.1, gl, double=True)
    B.box((0, D / 2 - 0.3, 0.45), (2.4, 0.4, 0.06), al)
    for x in (-1.0, 1.0):
        B.box((x, D / 2 - 0.3, 0.22), (0.06, 0.35, 0.44), al)
    export("SK_BusShelter", [B.finish("SK_BusShelter")])
    sign_post("SK_BusStopSign", 0.45, 0.6, 2.8, mat("M_SignBus", (0.1, 0.3, 0.75), 0.0, 0.5), (0, 0, 1, 1))


def storm_drain(do_export=True):
    B = Builder()
    iron = mat("M_CastIron", (0.05, 0.05, 0.05), 0.7, 0.55)
    B.box((0, 0, -0.01), (0.95, 0.5, 0.03), iron)
    for k in range(8):
        B.box((-0.38 + k * 0.108, 0, 0.012), (0.05, 0.42, 0.02), iron)
    ob = B.finish("SK_StormDrain")
    if do_export:
        export("SK_StormDrain", [ob])
    return ob


def mailbox():
    B = Builder()
    blue = mat("M_USPSBlue", (0.04, 0.12, 0.42), 0.3, 0.45)
    B.box((0, 0, 0.75), (0.5, 0.48, 0.95), blue)
    top = [(0, 0.24 * math.cos(math.pi * k / 8), 1.22 + 0.24 * math.sin(math.pi * k / 8) * 0.6) for k in range(9)]
    for k in range(8):
        a, b = top[k], top[k + 1]
        B.face([(-0.25, a[1], a[2]), (0.25, a[1], a[2]), (0.25, b[1], b[2]), (-0.25, b[1], b[2])][::-1], blue)
    for x in (-0.2, 0.2):
        for y in (-0.18, 0.18):
            B.box((x, y, 0.14), (0.05, 0.05, 0.28), blue)
    export("SK_Mailbox", [B.finish("SK_Mailbox")])


def bollard(do_export=True):
    B = Builder()
    s = M_STEEL()
    B.cyl((0, 0, 0), 0.95, 0.1, s, 12)
    B.cyl((0, 0, 0.95), 0.06, 0.11, s, 12)
    B.cyl((0, 0, 0.8), 0.05, 0.102, mat("M_ReflectiveWhite", (0.9, 0.9, 0.9), 0.0, 0.3), 12, top=False)
    ob = B.finish("SK_Bollard")
    if do_export:
        export("SK_Bollard", [ob])
    return ob


def tree_grate():
    B = Builder()
    iron = mat("M_CastIron", (0.05, 0.05, 0.05), 0.7, 0.55)
    s = 1.5
    B.face([(-s / 2, -s / 2, 0.005), (s / 2, -s / 2, 0.005), (s / 2, s / 2, 0.005), (-s / 2, s / 2, 0.005)], mat("M_TreeGrate", (0.08, 0.07, 0.06), 0.6, 0.6),
           [(0, 0), (1, 0), (1, 1), (0, 1)])
    export("SK_TreeGrate", [B.finish("SK_TreeGrate")])


# ------------------------------------------------------------------ trees
SPECIES = {
    #             height  clear  crown_w  crown_h  limbs  limb_up  card  cards  leaf_mat               crown shape
    "liveoak":     (9.0,   2.2,   15.0,    5.5,     6,     0.30,   2.0,  420,  "M_Leaves_liveoak",     "dome"),
    "honeylocust": (12.0,  3.0,   10.0,    7.5,     5,     0.85,   1.8,  320,  "M_Leaves_honeylocust", "vase"),
    "linden":      (12.5,  2.4,   8.0,     9.0,     7,     0.95,   1.9,  440,  "M_Leaves_linden",      "oval"),
    "elm":         (14.0,  3.2,   12.0,    9.0,     5,     1.15,   2.0,  400,  "M_Leaves_elm",         "vase"),
}


def crown_point(rnd, shape, cw, ch, base_z):
    """A random point inside the species' crown volume."""
    while True:
        x, y, z = rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(0, 1)
        r = math.hypot(x, y)
        if shape == "dome":        # broad and flattish, fuller at the top
            ok = r * r + ((z - 0.35) / 0.75) ** 2 <= 1 and z > 0.08
        elif shape == "oval":
            ok = r * r + ((z - 0.5) / 0.5) ** 2 <= 1
        else:                       # vase: narrow at the bottom, wide and rounded on top
            ok = r <= 0.25 + 0.75 * min(1.0, z / 0.7) and ((z - 0.55) / 0.5) ** 2 + r * r * 0.6 <= 1 and z > 0.12
        if ok:
            return Vector((x * cw / 2, y * cw / 2, base_z + z * ch))


def tree(sp, cards=None, do_export=True):
    H, clear, cw, ch, nlimbs, limb_up, card, ncards, leaf_m, shape = SPECIES[sp]
    if cards is not None:
        ncards = int(cards)
    rnd = random.Random(sum(map(ord, sp)))
    B = Builder()
    bark = mat("M_Bark", (0.3, 0.26, 0.22), 0.0, 0.9)
    leaf = mat(leaf_m, (0.2, 0.35, 0.12), 0.0, 0.6)
    bind_cluster(bark)
    bind_cluster(leaf)
    trunk_r = 0.24 if sp != "liveoak" else 0.32
    base_z = H - ch
    lean = Vector((rnd.uniform(-0.12, 0.12), rnd.uniform(-0.12, 0.12), 0))
    top = Vector((0, 0, clear)) + lean
    B.tube([(0, 0, 0), (lean.x * 0.4, lean.y * 0.4, clear * 0.5), tuple(top)], [trunk_r * 1.3, trunk_r, trunk_r * 0.9], bark, 8, cap=False, uv_v_scale=0.5)
    # crown volume first: leaf positions, then limbs grown toward clusters of them
    leaves = [crown_point(rnd, shape, cw, ch, base_z) for _ in range(ncards)]
    anchors = []

    def grow(start, target, radius, depth):
        pts = [Vector(start)]
        d = (Vector(target) - Vector(start))
        L = d.length
        segs = 4
        for i in range(1, segs + 1):
            t = i / segs
            p = Vector(start).lerp(Vector(target), t) + Vector((rnd.uniform(-0.3, 0.3), rnd.uniform(-0.3, 0.3), rnd.uniform(-0.2, 0.3))) * (L * 0.08)
            pts.append(p)
        B.tube([tuple(p) for p in pts], [radius * (1 - 0.65 * i / segs) for i in range(segs + 1)], bark, 6 if depth == 0 else 4, cap=False, uv_v_scale=0.5)
        anchors.extend(pts[1:])
        return pts

    centre = Vector((0, 0, base_z + ch * 0.5))
    for k in range(nlimbs):
        ang = 2 * math.pi * (k + rnd.uniform(-0.25, 0.25)) / nlimbs
        reach = cw * 0.5 * rnd.uniform(0.55, 0.8)
        tgt = Vector((math.cos(ang) * reach, math.sin(ang) * reach, base_z + ch * rnd.uniform(0.3, 0.6) * (0.6 + limb_up * 0.5)))
        start = Vector((0, 0, clear * rnd.uniform(0.85, 1.0))) + lean
        pts = grow(start, tgt, trunk_r * 0.6, 0)
        for j in range(3):
            a = pts[rnd.randint(2, len(pts) - 1)]
            out = (a - Vector((0, 0, a.z))).normalized() if a.xy.length > 0.1 else Vector((1, 0, 0))
            t2 = a + (out * rnd.uniform(1.5, 3.5) + Vector((rnd.uniform(-1.5, 1.5), rnd.uniform(-1.5, 1.5), rnd.uniform(0.8, 2.5))))
            sub = grow(a, t2, trunk_r * 0.28, 1)
            for j2 in range(2):
                b = sub[rnd.randint(2, len(sub) - 1)]
                t3 = b + Vector((rnd.uniform(-1.6, 1.6), rnd.uniform(-1.6, 1.6), rnd.uniform(0.2, 1.6)))
                grow(b, t3, trunk_r * 0.12, 2)
    # leaf cards: each crown point hangs off its nearest branch anchor, facing outward and up
    for p in leaves:
        a = min(anchors, key=lambda q: (q - p).length_squared)
        p = a.lerp(p, 0.55)
        out = p - centre
        out.z *= 0.6
        n = (out.normalized() * 0.8 + Vector((rnd.uniform(-0.5, 0.5), rnd.uniform(-0.5, 0.5), rnd.uniform(0.0, 0.9)))).normalized()
        s = card * rnd.uniform(0.8, 1.25)
        up = (Vector((0, 0, 1)) + Vector((rnd.uniform(-0.6, 0.6), rnd.uniform(-0.6, 0.6), 0))).normalized()
        if abs(n.dot(up)) > 0.95:
            up = Vector((1, 0, 0))
        B.card(tuple(p), tuple(n), tuple(up), s, s, leaf, double=True)
    ob = B.finish(f"SK_Tree_{sp}")
    if do_export:
        export(f"SK_Tree_{sp}", [ob])
    return ob


def _sweep_xz(name, ring, length, material):
    """Extrude a closed (x, z) ring along +Y for `length` metres. x grows toward the sidewalk."""
    B = Builder()
    n = len(ring)
    for i in range(n):
        x0, z0 = ring[i]
        x1, z1 = ring[(i + 1) % n]
        # Outward is to the right of the ring as it is walked in XZ, looking along +Y.
        B.face([(x0, 0, z0), (x0, length, z0), (x1, length, z1), (x1, 0, z1)], material)
    B.face([(x, 0, z) for x, z in ring], material)
    B.face([(x, length, z) for x, z in reversed(ring)], material)
    ob = B.finish(name)
    export(name, [ob])
    return ob


def curb_modules():
    """SK_Curb_Bevel, SK_Gutter_Pan and SK_Curb_Ramp: the profiles.py section as kit meshes.

    Two metres long, so a street can repeat them. The block preview sweeps the same
    section itself; these are the pieces an editor can drop by hand.
    """
    import sys as _sys
    roads = os.path.join(ROOT, "Scripts", "roads")
    if roads not in _sys.path:
        _sys.path.insert(0, roads)
    import profiles
    concrete = mat("M_Concrete", (0.55, 0.54, 0.52), 0.0, 0.7)
    _sweep_xz("SK_Curb_Bevel", profiles.curb_solid_section("major"), 2.0, concrete)
    pan = profiles.street_profile("major")[:2]
    # A thin pan: the slope, then a floor so the mesh is closed.
    pan_ring = pan + [(pan[-1][0], -0.08), (pan[0][0], -0.08)]
    _sweep_xz("SK_Gutter_Pan", pan_ring, 2.0, concrete)
    ramp = profiles.curb_ramp_spec()
    B = Builder()
    w, run, rise = ramp["width_m"], ramp["run_m"], ramp["rise_m"]
    flare = ramp["flare_m"]
    # The ramp runs along +Y, dropping from the sidewalk (y=0, z=rise) to the gutter (y=run, z=0).
    hw = w / 2.0
    B.face([(-hw, 0, rise), (hw, 0, rise), (hw, run, 0), (-hw, run, 0)], concrete)
    B.face([(-hw - flare, 0, rise), (-hw, 0, rise), (-hw, run, 0), (-hw - flare, 0, 0)], concrete)
    B.face([(hw, 0, rise), (hw + flare, 0, rise), (hw + flare, 0, 0), (hw, run, 0)], concrete)
    export("SK_Curb_Ramp", [B.finish("SK_Curb_Ramp")])


JOBS = {
    "lamps": lambda: (street_lamp(), street_lamp("SK_Lamp_Highway", 12.0, 3.2, True)),
    "signals": lambda: [signal_pole(a) for a in (4.0, 7.0, 10.0, 13.0)],
    "signs": lambda: (sign_post("SK_StopSign", 0.76, 0.76, 2.3, mat("M_SignStop", (0.7, 0.1, 0.1), 0.0, 0.5), None, "oct"),
                      sign_post("SK_SpeedSign", 0.61, 0.76, 2.4, mat("M_SignSpeed", (0.95, 0.95, 0.95), 0.0, 0.5), (0, 0, 0.25, 0.3125)),
                      name_blade()),
    "street": lambda: (bike_rack(), dumpster(), bus_shelter(), storm_drain(), mailbox(), bollard(), tree_grate()),
    "trees": lambda: [tree(s) for s in SPECIES],
    "curbs": curb_modules,
}


def main():
    for job, fn in JOBS.items():
        if ONLY and job not in ONLY:
            continue
        reset()
        MATS.clear()
        fn()
    print("ALL DONE")


if __name__ == "__main__":
    main()
