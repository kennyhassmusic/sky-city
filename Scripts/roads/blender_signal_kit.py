"""Sky City road kit: traffic-control props modelled in Blender (headless), one GLB per asset, plus a Cycles preview.

Conventions (same as Scripts/streets/blender_street_kit.py): metres; each asset built at the origin standing on z = 0
unless noted; its FRONT (what a driver / pedestrian looks at) faces Blender -Y, which Unreal's glTF import turns into
+X (Blender -X becomes Unreal +Y). Material slot names are what Unreal maps by name. Faces carry per-face material
indices, UVs (metric for plain materials, 0..1 where a texture/atlas is meant) and normals (round parts smooth).

  RK_SigPole     mast-arm pole 6.6 m, 0.30 -> 0.20 m, footing (top z 0.05), base plate + nuts, arm plate at z 6.0 on -Y
  RK_SigArm      UNIT-length mast arm: tube from the origin along -Y for 1.0 m, axis at z 0, 0.18 -> 0.12 m
                 (place at the pole axis, z 6.0, scale Y by the arm length)
  RK_SigHead3    3-section head, origin = top centre of the housing (hangs z 0 .. -1.05), lenses R/Y/G top->bottom
  RK_SigHeadL    same with left-turn arrows (arrows point Blender -X = the driver's left)
  RK_PedHead     0.45 m pedestrian head, origin = centre of its back face, DONT WALK top / WALK bottom
  RK_PedPost     3.4 m pedestrian pole (0.11 m) with a cast base
  RK_Cabinet     signal controller cabinet 0.9 x 0.6 x 1.5 m on a concrete pad, door on -Y
  RK_SignPost    3.0 m square galvanised post (0.06 m) with an anchor sleeve
  RK_SignPanel   0.9 x 0.9 x 0.04 m panel, origin = bottom centre; front 0..1 UVs, back mirrored (u -> 1-u)
  RK_Barricade   Type III barricade 2.4 m wide (along X), striped rails, ROAD CLOSED panel on top
  RK_Glyph       1 x 1 m road-marking decal quad at z 0 facing +Z; image top -> Blender -Y, image right -> Blender -X

Run:  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/roads/blender_signal_kit.py
      [-- meshes | preview] [out=<png>] [cam=main|heads|side|back|top|props]
      (default: build all meshes, then render SourceArt/RoadKit/preview.png with textures from make_road_textures.py)
"""
import json, math, os, sys
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
KIT = ROOT + "/SourceArt/RoadKit"
OUT = KIT + "/meshes"
TEX = KIT + "/textures"
os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OPTS = dict(a.split("=", 1) for a in ARGS if "=" in a)
JOBS_WANTED = [a for a in ARGS if "=" not in a] or ["meshes", "preview"]


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


def newell(pts):
    n = Vector((0, 0, 0))
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    return n


class Builder:
    """Accumulates geometry into one bmesh with per-face material indices (house style of the street kit),
    plus shared-vertex smooth surfaces and winding fixed against an expected outward normal."""

    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.mats = []

    def mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def face_v(self, vs, m, uvs=None, n=None, smooth=False):
        """Face from existing BMVerts; reversed if its normal disagrees with n."""
        if n is not None and newell([v.co for v in vs]).dot(Vector(n)) < 0:
            vs = vs[::-1]
            uvs = uvs[::-1] if uvs else uvs
        f = self.bm.faces.new(vs)
        f.material_index = self.mi(m)
        f.smooth = smooth
        if uvs:
            for l, uv in zip(f.loops, uvs):
                l[self.uv].uv = uv
        return f

    def face(self, verts, m, uvs=None, n=None, smooth=False):
        verts = [Vector(v) for v in verts]
        if uvs is None:          # metric planar UVs in the face's own plane
            nn = newell(verts)
            ax = max(range(3), key=lambda i: abs(nn[i]))
            a, b = [(1, 2), (0, 2), (0, 1)][ax]
            uvs = [(v[a], v[b]) for v in verts]
        return self.face_v([self.bm.verts.new(v) for v in verts], m, list(uvs), n, smooth)

    def box(self, c, size, m, rot=Matrix.Identity(3), mats=None):
        """Axis box (optionally rotated). mats: {'-y': material, ...} overrides per side."""
        sx, sy, sz = (s / 2 for s in size)
        P = [rot @ Vector((x * sx, y * sy, z * sz)) + Vector(c) for x, y, z in
             ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))]
        for key, idx in (("-z", (0, 3, 2, 1)), ("+z", (4, 5, 6, 7)), ("-y", (0, 1, 5, 4)), ("+x", (1, 2, 6, 5)), ("+y", (2, 3, 7, 6)), ("-x", (3, 0, 4, 7))):
            pts = [P[i] for i in idx]
            e1, e2 = (pts[1] - pts[0]).length, (pts[3] - pts[0]).length
            self.face(pts, (mats or {}).get(key, m), [(0, 0), (e1, 0), (e1, e2), (0, e2)])

    def slab(self, x0, x1, y0, y1, z0, z1, m_front, m_back, m_edge, uv_front=None, uv_back=None):
        """Box whose -Y (front) and +Y (back) faces take UV functions f(x, z) -> (u, v)."""
        F = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
        self.face([(x, y0, z) for x, z in F], m_front, [uv_front(x, z) for x, z in F] if uv_front else None, n=(0, -1, 0))
        self.face([(x, y1, z) for x, z in F], m_back, [uv_back(x, z) for x, z in F] if uv_back else None, n=(0, 1, 0))
        for (xa, za), (xb, zb) in zip(F, F[1:] + F[:1]):
            mid = Vector(((xa + xb) / 2 - (x0 + x1) / 2, 0, (za + zb) / 2 - (z0 + z1) / 2))
            self.face([(xa, y0, za), (xb, y0, zb), (xb, y1, zb), (xa, y1, za)], m_edge, n=mid)

    def tube(self, path, radii, m, sides=16, cap0=False, cap1=True, smooth=True, uv_v_scale=1.0):
        """Tapered tube along a polyline: shared ring vertices (smooth), flat caps."""
        rings, n, acc = [], len(path), 0.0
        for i, p in enumerate(path):
            p = Vector(p)
            a, b = Vector(path[max(0, i - 1)]), Vector(path[min(n - 1, i + 1)])
            t = (b - a).normalized()
            up = Vector((0, 0, 1)) if abs(t.z) < 0.95 else Vector((1, 0, 0))
            x = t.cross(up).normalized()
            y = t.cross(x).normalized()
            if i:
                acc += (p - Vector(path[i - 1])).length
            pts = [p + (x * math.cos(2 * math.pi * k / sides) + y * math.sin(2 * math.pi * k / sides)) * radii[i] for k in range(sides)]
            rings.append(([self.bm.verts.new(q) for q in pts], pts, acc, p, t))
        for (r0, _, v0, c0, _), (r1, _, v1, c1, _) in zip(rings, rings[1:]):
            for k in range(sides):
                k2 = (k + 1) % sides
                mid = (r0[k].co + r0[k2].co + r1[k].co + r1[k2].co) / 4
                axis = (c1 - c0).normalized()
                out = (mid - c0) - axis * (mid - c0).dot(axis)
                self.face_v([r0[k], r0[k2], r1[k2], r1[k]], m,
                            [(k / sides, v0 * uv_v_scale), ((k + 1) / sides, v0 * uv_v_scale), ((k + 1) / sides, v1 * uv_v_scale), (k / sides, v1 * uv_v_scale)],
                            n=out, smooth=smooth)
        for flag, (_, pts, _, c, t), sgn in ((cap0, rings[0], -1), (cap1, rings[-1], 1)):
            if flag:
                r = max((q - c).length for q in pts) or 1
                self.face(pts, m, [(0.5 + (q - c).dot(pts[0] - c) / (2 * r * r), 0.5 + (q - c).dot(t.cross(pts[0] - c)) / (2 * r * r)) for q in pts], n=t * sgn)

    def prism(self, poly, axis, a0, a1, m, m_cap0=None, m_cap1=None, uv_cap=None):
        """Extrude a 2D polygon along an axis. poly coords: axis 'y' -> (x, z), 'x' -> (y, z), 'z' -> (x, y).
        uv_cap(p2d) -> uv for both caps."""
        def P(p, a):
            return {"y": (p[0], a, p[1]), "x": (a, p[0], p[1]), "z": (p[0], p[1], a)}[axis]

        def D(v2):
            return Vector({"y": (v2[0], 0, v2[1]), "x": (0, v2[0], v2[1]), "z": (v2[0], v2[1], 0)}[axis])
        ax = D((0, 0)) + Vector({"y": (0, 1, 0), "x": (1, 0, 0), "z": (0, 0, 1)}[axis])
        area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
        uvs = [uv_cap(p) for p in poly] if uv_cap else None
        self.face([P(p, a0) for p in poly], m_cap0 or m, uvs, n=-ax * (1 if a1 > a0 else -1))
        self.face([P(p, a1) for p in poly], m_cap1 or m, uvs, n=ax * (1 if a1 > a0 else -1))
        for i in range(len(poly)):
            p, q = poly[i], poly[(i + 1) % len(poly)]
            e = (q[0] - p[0], q[1] - p[1])
            out = (e[1], -e[0]) if area > 0 else (-e[1], e[0])
            self.face([P(p, a0), P(q, a0), P(q, a1), P(p, a1)], m, n=D(out))

    def disc_xz(self, cx, cz, y, r, m, n=24, dome=0.0, smooth=True):
        """Disc facing -Y (optionally domed toward -Y), planar 0..1 UVs over its bounding square."""
        c = self.bm.verts.new((cx, y - dome, cz))
        rim = [self.bm.verts.new((cx + r * math.cos(2 * math.pi * k / n), y, cz + r * math.sin(2 * math.pi * k / n))) for k in range(n)]
        uv = lambda v: (0.5 + (v.co.x - cx) / (2 * r), 0.5 + (v.co.z - cz) / (2 * r))
        for k in range(n):
            vs = [c, rim[k], rim[(k + 1) % n]]
            self.face_v(vs, m, [uv(v) for v in vs], n=(0, -1, 0), smooth=smooth and dome > 0)

    def finish(self, name):
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
    o = objs[0]
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = [min(v[i] for v in bb) for i in range(3)]
    hi = [max(v[i] for v in bb) for i in range(3)]
    print(f"exported {name}: {sum(len(x.data.polygons) for x in objs)} faces, slots {[m.name for m in o.data.materials]}, "
          f"bounds x {lo[0]:.3f}..{hi[0]:.3f} y {lo[1]:.3f}..{hi[1]:.3f} z {lo[2]:.3f}..{hi[2]:.3f}")


# ------------------------------------------------------------------ materials (slot names are the contract)
M_HOUSING = lambda: mat("M_SignalHousing", (0.035, 0.037, 0.04), 0.35, 0.5)
M_CONCRETE = lambda: mat("M_Concrete", (0.5, 0.49, 0.46), 0.0, 0.9)
M_BORDER = lambda: mat("M_SignalBorder", (0.95, 0.78, 0.05), 0.0, 0.35)
M_RED = lambda: mat("M_SignalRed", (0.9, 0.05, 0.03), 0.0, 0.15)
M_YEL = lambda: mat("M_SignalYellow", (0.95, 0.6, 0.02), 0.0, 0.15)
M_GRN = lambda: mat("M_SignalGreen", (0.05, 0.9, 0.5), 0.0, 0.15)
M_RED_A = lambda: mat("M_SignalRedArrow", (0.9, 0.05, 0.03), 0.0, 0.15)
M_YEL_A = lambda: mat("M_SignalYellowArrow", (0.95, 0.6, 0.02), 0.0, 0.15)
M_GRN_A = lambda: mat("M_SignalGreenArrow", (0.05, 0.9, 0.5), 0.0, 0.15)
M_DONT = lambda: mat("M_PedDontWalk", (1.0, 0.42, 0.05), 0.0, 0.2)
M_WALK = lambda: mat("M_PedWalk", (0.92, 0.95, 0.95), 0.0, 0.2)
M_CAB = lambda: mat("M_CabinetMetal", (0.68, 0.7, 0.69), 0.55, 0.45)
M_POST = lambda: mat("M_SignPost", (0.62, 0.63, 0.64), 0.9, 0.38)
M_ATLAS = lambda: mat("M_SignAtlas", (0.9, 0.9, 0.9), 0.0, 0.5)
M_SIGNBACK = lambda: mat("M_SignBack", (0.55, 0.56, 0.57), 0.8, 0.5)
M_STRIPE = lambda: mat("M_BarricadeStripe", (1.0, 0.43, 0.0), 0.0, 0.5)
M_PLASTIC = lambda: mat("M_BarricadePlastic", (0.92, 0.92, 0.9), 0.0, 0.5)
M_GLYPH = lambda: mat("M_RoadGlyph", (0.95, 0.95, 0.95), 0.0, 0.6)


# ------------------------------------------------------------------ signals
POLE_H, POLE_R0, POLE_R1, ARM_Z = 6.6, 0.15, 0.10, 6.0
pole_r = lambda z: POLE_R0 + (POLE_R1 - POLE_R0) * z / POLE_H


def sig_pole():
    B = Builder()
    s, c = M_HOUSING(), M_CONCRETE()
    B.tube([(0, 0, -0.15), (0, 0, 0.05)], [0.3, 0.3], c, 28, uv_v_scale=1.0)            # round footing, top 5 cm up
    B.box((0, 0, 0.065), (0.46, 0.46, 0.03), s)                                          # base plate
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = 0.175 * sx, 0.175 * sy
            B.tube([(x, y, 0.08), (x, y, 0.12)], [0.03, 0.03], s, 6, smooth=False)       # hex nut
            B.tube([(x, y, 0.12), (x, y, 0.15)], [0.012, 0.012], s, 8)                   # anchor-bolt end
    B.tube([(0, 0, 0.08 + k * (POLE_H - 0.08) / 4) for k in range(5)],
           [pole_r(0.08 + k * (POLE_H - 0.08) / 4) for k in range(5)], s, 20, cap1=False)
    B.tube([(0, 0, POLE_H), (0, 0, POLE_H + 0.03)], [pole_r(POLE_H) + 0.008] * 2, s, 20, cap0=True, cap1=False)   # pole cap
    B.tube([(0, 0, POLE_H + 0.03), (0, 0, POLE_H + 0.06)], [pole_r(POLE_H) + 0.008, 0.05], s, 20)
    B.box((0, pole_r(0.5) - 0.004, 0.5), (0.11, 0.03, 0.2), s)                          # handhole cover (back)
    r6 = pole_r(ARM_Z)
    B.box((0, -(r6 + 0.005), ARM_Z), (0.34, 0.04, 0.42), s)                             # arm mounting plate (front, -Y)
    for bx in (-0.12, 0.12):
        for bz in (-0.15, 0.15):
            B.tube([(bx, -(r6 + 0.025), ARM_Z + bz), (bx, -(r6 + 0.05), ARM_Z + bz)], [0.018, 0.018], s, 6, smooth=False)
    export("RK_SigPole", [B.finish("RK_SigPole")])


def sig_arm():
    B = Builder()
    B.tube([(0, 0, 0), (0, -0.5, 0), (0, -1.0, 0)], [0.09, 0.075, 0.06], M_HOUSING(), 20, cap0=True, cap1=True)
    export("RK_SigArm", [B.finish("RK_SigArm")])


HEAD_W, HEAD_H, HEAD_D = 0.35, 1.05, 0.25
LENS_R, LENS_Z = 0.15, (-0.175, -0.525, -0.875)          # section centres, top -> bottom


def backplate(B, w, h, zc, y0, t, b):
    """Black backplate with a retroreflective border band on its front face (coplanar split, no overlap)."""
    hs, bd = M_HOUSING(), M_BORDER()
    x0, x1, z0, z1 = -w / 2, w / 2, zc - h / 2, zc + h / 2
    a0, a1, c0, c1 = x0 + b, x1 - b, z0 + b, z1 - b
    B.face([(a0, y0, c0), (a1, y0, c0), (a1, y0, c1), (a0, y0, c1)], hs, n=(0, -1, 0))
    for quad in ([(x0, z0), (x1, z0), (a1, c0), (a0, c0)], [(x1, z0), (x1, z1), (a1, c1), (a1, c0)],
                 [(x1, z1), (x0, z1), (a0, c1), (a1, c1)], [(x0, z1), (x0, z0), (a0, c0), (a0, c1)]):
        B.face([(x, y0, z) for x, z in quad], bd, n=(0, -1, 0))
    F = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
    B.face([(x, y0 + t, z) for x, z in F], hs, n=(0, 1, 0))
    for (xa, za), (xb, zb) in zip(F, F[1:] + F[:1]):
        B.face([(xa, y0, za), (xb, y0, zb), (xb, y0 + t, zb), (xa, y0 + t, za)], hs, n=((xa + xb) / 2, 0, (za + zb) / 2 - zc))


def tunnel_visor(B, cx, cz, y0, length, r_in, thick, m, gap_deg=64, n=20):
    """Tunnel visor: a cylindrical shell around the lens, open in a slot at the bottom, from y0 forward (-Y)."""
    a0, a1 = math.radians(-90 + gap_deg / 2), math.radians(270 - gap_deg / 2)
    ang = [a0 + (a1 - a0) * j / n for j in range(n + 1)]
    ro = r_in + thick
    y1 = y0 - length
    for r, sgn in ((ro, 1), (r_in, -1)):
        back = [B.bm.verts.new((cx + r * math.cos(a), y0, cz + r * math.sin(a))) for a in ang]
        front = [B.bm.verts.new((cx + r * math.cos(a), y1, cz + r * math.sin(a))) for a in ang]
        for j in range(n):
            out = Vector((math.cos((ang[j] + ang[j + 1]) / 2), 0, math.sin((ang[j] + ang[j + 1]) / 2))) * sgn
            B.face_v([back[j], back[j + 1], front[j + 1], front[j]], m,
                     [(j / n, 0), ((j + 1) / n, 0), ((j + 1) / n, length), (j / n, length)], n=out, smooth=True)
    for j in range(n):                                       # front rim
        a, b = ang[j], ang[j + 1]
        B.face([(cx + ro * math.cos(a), y1, cz + ro * math.sin(a)), (cx + ro * math.cos(b), y1, cz + ro * math.sin(b)),
                (cx + r_in * math.cos(b), y1, cz + r_in * math.sin(b)), (cx + r_in * math.cos(a), y1, cz + r_in * math.sin(a))], m, n=(0, -1, 0))
    for a, sgn in ((a0, -1), (a1, 1)):                       # slot edges
        tdir = Vector((-math.sin(a), 0, math.cos(a))) * sgn
        B.face([(cx + ro * math.cos(a), y0, cz + ro * math.sin(a)), (cx + ro * math.cos(a), y1, cz + ro * math.sin(a)),
                (cx + r_in * math.cos(a), y1, cz + r_in * math.sin(a)), (cx + r_in * math.cos(a), y0, cz + r_in * math.sin(a))], m, n=tdir)


def signal_head(name, arrows):
    B = Builder()
    hs = M_HOUSING()
    yf = -HEAD_D / 2                                          # housing front face
    B.box((0, 0, -HEAD_H / 2), (HEAD_W, HEAD_D, HEAD_H), hs)
    B.box((0, HEAD_D / 2 + 0.012, -HEAD_H / 2), (0.12, 0.024, 0.7), hs)          # rear door hinge rib
    backplate(B, 0.55, 1.25, -HEAD_H / 2, 0.0, 0.02, 0.05)
    lens_mats = (M_RED_A(), M_YEL_A(), M_GRN_A()) if arrows else (M_RED(), M_YEL(), M_GRN())
    for zc, lm in zip(LENS_Z, lens_mats):
        if not arrows:
            B.disc_xz(0, zc, yf - 0.002, LENS_R, lm, 28, dome=0.022)
        else:
            B.disc_xz(0, zc, yf - 0.002, LENS_R, hs, 28)                            # dark lens disc
            # raised arrow pointing Blender -X (the driver's left): shaft + head, convex pieces
            uv = lambda p, zc=zc: (0.5 + p[0] / (2 * LENS_R), 0.5 + (p[1] - zc) / (2 * LENS_R))
            shaft = [(-0.02, zc - 0.026), (0.11, zc - 0.026), (0.11, zc + 0.026), (-0.02, zc + 0.026)]
            tip = [(-0.115, zc), (-0.02, zc - 0.068), (-0.02, zc + 0.068)]
            for poly in (shaft, tip):
                B.prism(poly, "y", yf - 0.003, yf - 0.016, lm, uv_cap=uv)
        tunnel_visor(B, 0, zc, yf, 0.25, LENS_R + 0.006, 0.007, hs)
    export(name, [B.finish(name)])


def ped_head():
    B = Builder()
    hs = M_HOUSING()
    W = H = 0.45
    D = 0.25
    B.box((0, -D / 2, 0), (W, D, H), hs)                                          # back face at y = 0 (origin)
    for z0, z1, m in ((0.02, 0.2, M_DONT()), (-0.2, -0.02, M_WALK())):
        B.face([(-0.19, -D - 0.002, z0), (0.19, -D - 0.002, z0), (0.19, -D - 0.002, z1), (-0.19, -D - 0.002, z1)], m,
               [(0, 0), (1, 0), (1, 1), (0, 1)], n=(0, -1, 0))
    L = 0.17                                                                       # hood visor
    B.box((0, -D - L / 2, H / 2 - 0.006), (W, L, 0.012), hs)
    for sx in (-1, 1):
        B.prism([(-D, H / 2 - 0.012), (-D, -H / 2 + 0.03), (-D - 0.05, -H / 2 + 0.03), (-D - L, H / 2 - 0.012)], "x",
                sx * (W / 2 - 0.012), sx * W / 2, hs)
    B.box((0, -D - 0.045, 0.0), (W - 0.024, 0.09, 0.01), hs)                      # divider between the two sections
    B.box((0, 0.012, 0.0), (0.1, 0.024, 0.3), hs)                                 # clamshell mount (behind the origin)
    export("RK_PedHead", [B.finish("RK_PedHead")])


def ped_post():
    B = Builder()
    s = M_HOUSING()
    B.box((0, 0, 0.01), (0.3, 0.3, 0.02), s)
    B.tube([(0, 0, 0.02), (0, 0, 0.3)], [0.12, 0.105], s, 20)                       # cast base
    B.tube([(0, 0, 0.3), (0, 0, 0.42)], [0.095, 0.055], s, 20, cap1=False)
    B.tube([(0, 0, 0.42), (0, 0, 3.37)], [0.055, 0.055], s, 16, cap1=False)
    B.tube([(0, 0, 3.37), (0, 0, 3.4)], [0.062, 0.062], s, 16, cap0=True)          # pole cap, top at 3.4
    export("RK_PedPost", [B.finish("RK_PedPost")])


def cabinet():
    B = Builder()
    m, c = M_CAB(), M_CONCRETE()
    B.box((0, -0.075, 0.025), (1.3, 1.05, 0.15), c)                               # pad z -0.05..0.10, apron in front
    W, D, z0, z1 = 0.9, 0.6, 0.10, 1.60
    B.box((0, 0, (z0 + z1) / 2), (W, D, z1 - z0), m)
    B.box((0, 0, z0 + 0.025), (W + 0.02, D + 0.02, 0.05), m)                     # base flange
    B.box((0, 0, z1 + 0.02), (W + 0.08, D + 0.08, 0.04), m)                      # rain cap
    B.box((0, 0, z1 + 0.05), (W + 0.02, D + 0.02, 0.02), m)
    yf = -D / 2
    B.box((0, yf - 0.005, 0.86), (0.8, 0.01, 1.32), m)                            # door panel (seam shows as a step)
    B.box((0.33, yf - 0.025, 0.92), (0.03, 0.03, 0.18), m)                        # handle
    B.tube([(0.33, yf - 0.01, 1.08), (0.33, yf - 0.03, 1.08)], [0.015, 0.015], m, 10)   # lock
    for hz in (0.38, 0.86, 1.34):
        B.tube([(-0.405, yf - 0.012, hz - 0.05), (-0.405, yf - 0.012, hz + 0.05)], [0.012, 0.012], m, 8)  # hinges
    B.box((0.22, yf - 0.012, 1.3), (0.22, 0.006, 0.26), m)                        # police panel
    for k in range(6):                                                            # louvres, door top-left and bottom
        rot = Matrix.Rotation(math.radians(35), 3, "X")
        B.box((-0.13, yf - 0.018, 1.22 + k * 0.045), (0.4, 0.012, 0.035), m, rot)
        B.box((0.0, yf - 0.018, 0.27 + k * 0.045), (0.6, 0.012, 0.035), m, rot)
    for sx in (-1, 1):                                                            # side louvres
        for k in range(5):
            B.box((sx * (W / 2 + 0.008), 0, 1.3 + k * 0.045), (0.012, 0.36, 0.035), m, Matrix.Rotation(math.radians(-35 * sx), 3, "Y"))
    export("RK_Cabinet", [B.finish("RK_Cabinet")])


def sign_post():
    B = Builder()
    p = M_POST()
    B.box((0, 0, 1.5), (0.06, 0.06, 3.0), p)
    B.box((0, 0, 0.14), (0.076, 0.076, 0.28), p)                                 # anchor sleeve (base)
    B.tube([(0.038, 0, 0.2), (0.058, 0, 0.2)], [0.009, 0.009], p, 6, smooth=False)    # corner bolt
    B.box((0, 0, 3.005), (0.066, 0.066, 0.01), p)                                # cap
    export("RK_SignPost", [B.finish("RK_SignPost")])


def sign_panel():
    B = Builder()
    w, h, t = 0.9, 0.9, 0.04
    uvf = lambda x, z: ((x + w / 2) / w, z / h)          # front: viewer's left (-X) = u 0, bottom = v 0 (Blender v up)
    B.slab(-w / 2, w / 2, -t / 2, t / 2, 0.0, h, M_ATLAS(), M_ATLAS(), M_SIGNBACK(), uvf, uvf)   # back: same u(x) = mirrored
    export("RK_SignPanel", [B.finish("RK_SignPanel")])


def barricade():
    B = Builder()
    st, pl, at = M_STRIPE(), M_PLASTIC(), M_ATLAS()
    W = 2.4
    for x in (-0.95, 0.95):
        B.box((x, 0, 0.7), (0.08, 0.08, 1.4), pl)                                 # uprights z 0..1.4
        B.box((x, 0, 0.04), (0.14, 0.8, 0.08), pl)                                # feet
        B.box((x, 0, 0.12), (0.1, 0.3, 0.08), pl)
    for zc in (0.4, 0.8, 1.2):                                                    # rails: U = metres / 0.8, V = 0..1 per rail
        uv = lambda x, z, zc=zc: ((x + W / 2) / 0.8, (z - (zc - 0.1)) / 0.2)
        B.slab(-W / 2, W / 2, -0.07, -0.04, zc - 0.1, zc + 0.1, st, st, pl, uv, uv)
    for x in (-0.45, 0.45):
        B.box((x, -0.085, 1.5), (0.05, 0.03, 0.8), pl)                            # panel posts z 1.1..1.9
    full = lambda x, z: ((x + 0.6) / 1.2, (z - 1.34) / 0.6)
    B.slab(-0.6, 0.6, -0.12, -0.10, 1.34, 1.94, at, pl, pl, full, None)            # ROAD CLOSED panel 1.2 x 0.6
    export("RK_Barricade", [B.finish("RK_Barricade")])


def glyph():
    B = Builder()
    # +Z facing; image top (Blender v = 1) at -Y = forward, image right (u = 1) at -X = the driver's right
    B.face([(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)], M_GLYPH(),
           [(1, 1), (0, 1), (0, 0), (1, 0)], n=(0, 0, 1))
    export("RK_Glyph", [B.finish("RK_Glyph")])


ASSETS = [sig_pole, sig_arm, lambda: signal_head("RK_SigHead3", False), lambda: signal_head("RK_SigHeadL", True),
          ped_head, ped_post, cabinet, sign_post, sign_panel, barricade, glyph]


# ------------------------------------------------------------------ preview render
def preview(outp, cam_name):
    reset()
    meta = json.load(open(f"{TEX}/textures.json"))
    IMG = {}

    def image(fn):
        if fn not in IMG:
            IMG[fn] = bpy.data.images.load(f"{TEX}/{fn}")
        return IMG[fn]

    def imp(name, loc=(0, 0, 0), rz=0.0, scale=(1, 1, 1)):
        bpy.ops.import_scene.gltf(filepath=f"{OUT}/{name}.glb")
        ob = [o for o in bpy.context.selected_objects if o.type == "MESH"][0]
        ob.location = loc
        ob.rotation_mode = "XYZ"                 # the glTF importer leaves objects in quaternion mode
        ob.rotation_euler = (0, 0, math.radians(rz))
        ob.scale = scale
        return ob

    def tex_mat(name, fn, cell=None, grid=(1, 1), alpha=True, emit=0.0):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        bsdf.inputs["Roughness"].default_value = 0.5
        it = nt.nodes.new("ShaderNodeTexImage")
        it.image = image(fn)
        if cell is not None:
            cols, rows = grid
            col, row = cell % cols, cell // cols
            tc = nt.nodes.new("ShaderNodeTexCoord")
            mp = nt.nodes.new("ShaderNodeMapping")
            mp.inputs["Scale"].default_value = (1 / cols, 1 / rows, 1)
            mp.inputs["Location"].default_value = (col / cols, 1 - (row + 1) / rows, 0)   # Blender v is bottom-up
            nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
            nt.links.new(mp.outputs["Vector"], it.inputs["Vector"])
        nt.links.new(it.outputs["Color"], bsdf.inputs["Base Color"])
        if alpha:
            nt.links.new(it.outputs["Alpha"], bsdf.inputs["Alpha"])
        if emit:
            nt.links.new(it.outputs["Color"], bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = emit
        return m

    def set_slot(ob, base, m):
        for i, sm in enumerate(ob.data.materials):
            if sm and sm.name.split(".")[0] == base:
                ob.data.materials[i] = m

    # mast-arm assembly: pole on the driver's right, arm reaching across the lanes toward Blender -X (the driver's left)
    imp("RK_SigPole", rz=-90)
    imp("RK_SigArm", (0, 0, ARM_Z), rz=-90, scale=(1, 9.0, 1))
    for x in (-2.3, -4.6, -6.6):
        imp("RK_SigHead3", (x, 0, ARM_Z))
    imp("RK_SigHeadL", (-8.4, 0, ARM_Z))
    imp("RK_PedPost", (2.2, -1.2, 0))
    imp("RK_PedHead", (2.2, -1.2 - 0.055, 3.0))
    imp("RK_Cabinet", (4.3, 0.4, 0))
    imp("RK_SignPost", (6.4, -1.2, 0))
    sc_cells = {c["name"]: c for c in meta["signs"]["cells"]}
    for nm, z in (("STOP", 2.08), ("ONE_WAY", 1.72)):
        c = sc_cells[nm]
        w, h = c["panel_m"]
        ob = imp("RK_SignPanel", (6.4, -1.2 - 0.05, z), scale=(w / 0.9, 1, h / 0.9))
        set_slot(ob, "M_SignAtlas", tex_mat("pv_" + nm, "T_SignAtlas2.png", c["index"], (4, 4)))
    bar = imp("RK_Barricade", (9.2, -1.6, 0))
    set_slot(bar, "M_SignAtlas", tex_mat("pv_RC", "T_SignAtlas2.png", sc_cells["ROAD_CLOSED"]["index"], (4, 4)))
    set_slot(bar, "M_BarricadeStripe", tex_mat("pv_stripe", "T_BarricadeStripe.png", alpha=False))
    # glyphs, turned 180 deg so their forward points +Y (away from the camera, like the signals' approach)
    gc = {c["name"]: c for c in meta["glyphs"]["cells"]}
    for nm, x, y in (("L", -8.4, -3.4), ("S", -6.5, -3.4), ("S", -4.55, -3.4), ("SR", -2.3, -3.4),
                     ("ONLY", -8.4, -7.0), ("LR", -6.5, -7.3), ("LS", -4.55, -7.3), ("R", -2.3, -7.3), ("BIKE", -0.25, -5.2)):
        w, l = gc[nm]["decal_m"]
        ob = imp("RK_Glyph", (x, y, 0.004), rz=180, scale=(w, l, 1))
        set_slot(ob, "M_RoadGlyph", tex_mat("pv_g_" + nm, "T_RoadGlyphs.png", gc[nm]["index"], (4, 2)))
    for m in bpy.data.materials:                                      # lit lenses
        base = m.name.split(".")[0]
        if base.startswith("M_Signal") and base not in ("M_SignalHousing", "M_SignalBorder") or base.startswith("M_Ped"):
            b = m.node_tree.nodes.get("Principled BSDF")
            b.inputs["Emission Color"].default_value = b.inputs["Base Color"].default_value
            b.inputs["Emission Strength"].default_value = 5.0
    # lane lines for scale
    for x in (-9.5, -7.45, -5.5, -3.45, -1.15, 0.65):
        bpy.ops.mesh.primitive_plane_add(size=1, location=(x, -5.6, 0.002))
        bpy.context.object.scale = (0.12, 9.0, 1)
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, 0))
    g = bpy.data.materials.new("ground")
    g.use_nodes = True
    g.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.035, 0.035, 0.04, 1)
    g.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.85
    bpy.context.object.data.materials.append(g)
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(55), 0, math.radians(-30)))
    bpy.context.object.data.energy = 3.5
    w = bpy.data.worlds.new("w")
    bpy.context.scene.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.42, 0.5, 0.62, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    cams = {  # name: (location, look-at, lens, ortho_scale)
        "main": ((-0.2, -19.0, 4.0), (-0.1, 0.0, 2.3), 26, None),
        "heads": ((-5.4, -6.5, 5.0), (-5.4, 0.0, 5.45), 32, None),
        "side": ((-15.0, -4.0, 6.2), (-6.0, 0.0, 5.6), 50, None),
        "back": ((-1.0, 22.0, 4.5), (-1.0, 0.0, 3.0), 30, None),
        "top": ((-4.0, -5.5, 40.0), (-4.0, -5.499, 0.0), 50, 13.0),
        "props": ((6.0, -9.0, 2.4), (6.0, 0.0, 1.5), 32, None),
    }
    loc, tgt, lens, ortho = cams[cam_name]
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.object
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = lens
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.engine = "CYCLES"
    sc.cycles.samples = int(OPTS.get("samples", 64))
    sc.cycles.device = "CPU"
    try:
        sc.cycles.use_denoising = True
    except Exception:
        pass
    sc.render.resolution_x, sc.render.resolution_y = (1600, 900) if cam_name != "top" else (1200, 1200)
    sc.render.filepath = outp
    bpy.ops.render.render(write_still=True)
    print("rendered", outp)


if "meshes" in JOBS_WANTED:
    for fn in ASSETS:
        reset()
        MATS.clear()
        fn()
if "preview" in JOBS_WANTED:
    preview(OPTS.get("out", KIT + "/preview.png"), OPTS.get("cam", "main"))
print("ALL DONE")
