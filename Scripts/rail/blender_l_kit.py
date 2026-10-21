"""Sky City - Chicago "L" elevated railway kit, modelled in headless Blender and exported as GLB, one file per asset.

Reference: the Loop L over Wabash / Lake / Wells / Van Buren. Two standard-gauge tracks (1.435 m) with centres 3.8 m
apart, top of rail 7.3 m above the street, a ~9 m wide open deck on transverse steel bents every 50 ft (15.24 m):
two latticed columns, a deep cross girder, arched knee braces; longitudinal plate girders under every rail; wooden
ties every 2 ft, running rails, a top-contact third rail on the outer side of each track, steel walkway grating
between and outside the tracks, pipe handrails at the outer edges.

CONVENTIONS (same as Scripts/streets/blender_street_kit.py)
- Real-world metres, Blender Z up, street level = z 0.
- LINEAR modules run along Blender -Y from y = 0 to y = -L and are centred on the track-pair centreline x = 0.
  glTF import turns Blender -Y into Unreal +X and Blender -X into Unreal +Y (so Blender +X = Unreal -Y), metres -> cm.
- Track centres x = +-1.9; rails at track +- 0.7535 (gauge measured between the rail heads' inner faces).
- One mesh per GLB, flat-shaded hard surface (tubes smooth), transforms applied, normals + UVs exported.
  UVs are box-projected in metres for tiling textures; sign faces (M_SignPanel, M_DestSign) are UV'd to the full
  0-1 square and read upright from the front (Blender's v runs bottom-up, glTF/Unreal's top-down: handled by glTF).
- Material slot names are stable; Unreal maps them (M_* -> MI_*).

KEY HEIGHTS: top of rail 7.30 | tie top 7.10 | longitudinal girder top 6.90 (1.5 m deep plate girders, bottom 5.40,
framing 0.5 m into the bent's cross girder) | bent cross girder top 5.90 (1.4 m deep, bottom 4.50 = street clearance
under the girder) | platform deck 8.30 (= top of rail + 1.0) | canopy underside 11.20 | third rail top 7.42.

ASSETS (SourceArt/Rail/meshes/*.glb)
  L_Bent                      transverse bent, centred on y = 0 (sits at a module joint); columns x = +-5.0,
                              footings 1.5 x 1.3 m (bury to z -0.4), cross girder top z 5.9.
  L_Span15 / L_Span5          deck modules 15.24 / 5.08 m long (y 0 .. -L) that sit on bents at their ends.
  L_StationPlatform30         30.48 m of two side platforms (x +-3.35 .. +-6.95), own outrigger columns x = +-6.7 at
                              y -3.81 -11.43 -19.05 -26.67 (between bents), canopies, benches, 2 hanging name signs
                              per side (y -7.62, -22.86), glass railing on the outer edge. Placed together with spans.
  L_StationPlatform30_Stair   same, with 2.4 m railing openings at the module centre (y -14.04 .. -16.44) on both
                              sides, where L_StationStairs / L_StationHouse attach; no centre bench.
  L_StationStairs             enclosed street-to-platform stair for the +X platform, modelled IN THE PLATFORM FRAME:
                              place it with the same transform as an L_StationPlatform30_Stair module. Occupies
                              x 6.95 .. 9.95, y 0 .. -16.56: street entrance (canopy + "L" blade sign) at the +Y end
                              (y -1.0, facing +Y = Unreal -X), rising toward -Y, top landing at platform height in
                              the railing opening. For the -X platform: yaw 180 deg about the module centre (i.e. put
                              it at the module's far end, local y = -30.48, rotated 180) or mirror (Unreal scale Y -1).
  L_StationHouse              small platform-level fare-control house (Quincy/Wells style), standing on the +X platform
                              under the canopy at the stair head: x 5.0 .. 6.75, y -12.24 .. -18.24, doors to the stair
                              landing (outer wall) and to the platform (both ends). Same transform as the _Stair module.
  L_TrainCar                  CTA 5000-series-style car, 14.6 x 2.8 x 3.7 m, pivot at the car centre on the rail
                              plane (wheels on z 0; place at z = top of rail), cab / front toward -Y (Unreal +X), both
                              ends identical. Wheels at x +-0.75, third-rail shoes reach x +-1.6.

  --- added 20 Oct 2026 for the street-fitted layout (Scripts/rail/l_layout.py -> Scripts/roads/build_l_ue.py) ---
  L_BentColumn                one bent column at the origin (footing 1.5 x 1.3, shoe, latticed shaft, cap at z 4.5) with
                              its arched knee brace toward +X: turn +X toward the track. Two per bent, placed one by one
                              so each lands at the curb or in a parking lane (Wabash / Lake / Wells / Van Buren practice)
  L_BentGirder                the deep cross girder alone, x -5.45..5.45 (bearing at +-5.0), z 4.5..5.9; scale X by
                              (column spacing + 0.9) / 10.9 and centre it between the two columns (skew allowed)
  L_Span15J / L_Span5J        deck modules for junctions (decks of two routes overlap): no outer walkways, toe boards,
                              handrails or third rails
  L_PlatSide30(_Stair)        ONE platform side (+X) of a 30.48 m module, cantilevered off the deck (struts to the outer
                              deck girder, no ground columns, so wide streets keep their lanes); other side = same mesh
                              placed from the module's far end back to its start. _Stair: railing opening at the centre
  L_StairBridge               enclosed walkway at platform level, x 0..1 (scale X to the gap), y = the stair opening:
                              joins the platform to a stair tower set back onto the sidewalk on a wide street
  L_Bumper                    buffer stops for both tracks, frame y 0..-2.4 from the deck end (buffers face -Y = the
                              way trains come in); place at the end point, forward pointing back along the line
  L_EndFence                  end plate over the girder ends + fence + red lamps across the deck end (same frame)
  L_Truss                     Pratt through truss beside the deck, y 0..-45 (scale Y to the span, X for curves), for
                              spans of 30-60 m over big junctions; the bents at its ends carry it
  L_DeckSlab                  1 m box (x -0.5..0.5, y 0..-1, z 0..1): invisible collision floor at top of rail

Run:
  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/rail/blender_l_kit.py [-- jobs...]
  jobs: bent span platform stairs house train column girder jspan platside bridge bumper fence truss slab
        (default: all of them; also rewrites SourceArt/Rail/kit.json)
        preview scene=new cam=newmain|newunder|newend|newtruss|newstair  -> the 20 Oct parts assembled
        preview  -> Cycles render of the assembled kit, SourceArt/Rail/preview.png
                    options: cam=main|bent|under|joint|deck|opendeck|station|stairs2|head|headtop|housefront|train|top|end
                             out=<png>  samples=<n>  res=<w>x<h>  notrain=1
                    (sign faces get an orientation test texture: white "L" left, red square top-right)
"""
import json, math, os, sys
import bpy, bmesh
from mathutils import Vector

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
RAIL = ROOT + "/SourceArt/Rail"
OUT = RAIL + "/meshes"
os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OPTS = dict(a.split("=", 1) for a in ARGS if "=" in a)
JOBS_ASKED = [a for a in ARGS if "=" not in a]

# ------------------------------------------------------------------ dimensions (metres)
FT = 0.3048
GAUGE = 1.435
TRACK_X = 1.9                               # track centres at x = +-1.9 (3.8 m apart)
RAIL_X = GAUGE / 2 + 0.036                  # rail centreline from the track centre
TOR = 7.30                                  # top of rail
RAIL_H, PLATE_H = 0.17, 0.03
TIE_H, TIE_W, TIE_L = 0.20, 0.15, 2.6
TIE_PITCH = 2 * FT
TIE_TOP = TOR - RAIL_H - PLATE_H            # 7.10
GIRDER_TOP = TIE_TOP - TIE_H                # 6.90
GIRDER_D = 1.5
GIRDER_X = (TRACK_X - RAIL_X, TRACK_X + RAIL_X)   # one plate girder under each rail
THIRD_X = TRACK_X + 1.5                     # third rail, outer side of each track
THIRD_TOP = TOR + 0.12
LONG_TIE_X = 4.5                            # every 3rd tie runs the full width (walkways, third-rail insulators)
WALK_IN, WALK_OUT = 3.62, 4.45
GRATING_T = 0.035
HANDRAIL_X = 4.42
HANDRAIL_TOP = TIE_TOP + GRATING_T + 0.88   # 8.015: stays under the platform slab (8.10)
SPAN_L = 50 * FT                            # 15.24 bent spacing
SPAN_S = SPAN_L / 3                         # 5.08
COL_X = 5.0
BENT_TOP, BENT_D = 5.9, 1.4
PLAT_L = 100 * FT                           # 30.48
PLAT_Z = TOR + 1.0                          # 8.30
PLAT_T = 0.2
PLAT_EDGE = 3.35                            # car side at 1.9 + 1.4 = 3.30
PLAT_W = 3.6
PLAT_OUT = PLAT_EDGE + PLAT_W               # 6.95
PLAT_COL_X = 6.7
PLAT_BEAM_D = 0.45
FRAMES = [-(k + 0.5) * PLAT_L / 4 for k in range(4)]   # -3.81 -11.43 -19.05 -26.67
CANOPY_Z = 11.2
STAIR_GAP = (-14.04, -16.44)                # railing opening / stair top landing (module centre +- 1.2)
STAIR_X0, STAIR_X1 = PLAT_OUT, PLAT_OUT + 3.0
SIGN_Y = (-7.62, -22.86)

# ------------------------------------------------------------------ materials
MAT_DEFS = {   # name: (base colour, metallic, roughness, emission strength)
    "M_LSteel": ((0.18, 0.22, 0.20), 0.35, 0.6, 0),
    "M_LSteelRust": ((0.19, 0.12, 0.08), 0.25, 0.85, 0),
    "M_Rail": ((0.42, 0.40, 0.38), 0.9, 0.35, 0),
    "M_Tie": ((0.12, 0.09, 0.07), 0.0, 0.85, 0),
    "M_Concrete": ((0.55, 0.54, 0.52), 0.0, 0.9, 0),
    "M_Grating": ((0.22, 0.24, 0.23), 0.7, 0.55, 0),
    "M_Insulator": ((0.55, 0.47, 0.33), 0.0, 0.5, 0),
    "M_Glass": ((0.55, 0.68, 0.72), 0.0, 0.05, 0),
    "M_Canopy": ((0.56, 0.58, 0.59), 0.5, 0.45, 0),
    "M_SignPanel": ((0.04, 0.05, 0.07), 0.0, 0.4, 0),
    "M_Light": ((1.0, 0.94, 0.82), 0.0, 0.3, 5.0),
    "M_Paint_Yellow": ((0.95, 0.74, 0.05), 0.0, 0.5, 0),
    "M_Stainless": ((0.74, 0.75, 0.76), 1.0, 0.28, 0),
    "M_LineStripe": ((0.78, 0.07, 0.09), 0.0, 0.4, 0),
    "M_TrainDark": ((0.035, 0.035, 0.04), 0.3, 0.6, 0),
    "M_TrainInterior": ((0.45, 0.48, 0.52), 0.0, 0.6, 0),
    "M_DestSign": ((0.9, 0.55, 0.1), 0.0, 0.4, 2.0),
}
MATS = {}


def M(name):
    if name in MATS:
        return MATS[name]
    rgb, metal, rough, emit = MAT_DEFS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*rgb, 1)
        b.inputs["Emission Strength"].default_value = emit
    if name == "M_Glass":
        b.inputs["Transmission Weight"].default_value = 0.9
    MATS[name] = m
    return m


# ------------------------------------------------------------------ geometry builder
def newell(pts):
    n = Vector((0.0, 0.0, 0.0))
    for i, p in enumerate(pts):
        q = pts[(i + 1) % len(pts)]
        n.x += (p.y - q.y) * (p.z + q.z)
        n.y += (p.z - q.z) * (p.x + q.x)
        n.z += (p.x - q.x) * (p.y + q.y)
    return n


def rect(cx, cy, sx, sy, z):
    return [(cx - sx / 2, cy - sy / 2, z), (cx + sx / 2, cy - sy / 2, z), (cx + sx / 2, cy + sy / 2, z), (cx - sx / 2, cy + sy / 2, z)]


class Builder:
    """Accumulates geometry into one bmesh with per-face material indices (house style of the street kit)."""
    SIDES = {"-z": (0, 3, 2, 1), "+z": (4, 5, 6, 7), "-y": (0, 1, 5, 4), "+x": (1, 2, 6, 5), "+y": (2, 3, 7, 6), "-x": (3, 0, 4, 7)}

    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.mats = []
        self.fixed = set()          # faces with explicit UVs (everything else is box-projected in finish())

    def mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def face(self, pts, m, uvs=None, n=None):
        """New face from points; with n given, the winding is flipped if needed so the face looks along n."""
        pts = [Vector(p) for p in pts]
        if n is not None and newell(pts).dot(Vector(n)) < 0:
            pts.reverse()
            uvs = list(uvs)[::-1] if uvs else None
        f = self.bm.faces.new([self.bm.verts.new(p) for p in pts])
        f.material_index = self.mi(m)
        if uvs:
            for l, uv in zip(f.loops, uvs):
                l[self.uv].uv = uv
            self.fixed.add(f)
        return f

    def face_v(self, verts, m, smooth=False, uvs=None):
        f = self.bm.faces.new(verts)
        f.material_index = self.mi(m)
        f.smooth = smooth
        if uvs:
            for l, uv in zip(f.loops, uvs):
                l[self.uv].uv = uv
            self.fixed.add(f)
        return f

    def box(self, c, size, m, skip=(), sm=None):
        c = Vector(c)
        hx, hy, hz = (s / 2 for s in size)
        P = [c + Vector((x * hx, y * hy, z * hz)) for x, y, z in
             ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))]
        for side, idx in self.SIDES.items():
            if side not in skip:
                self.face([P[i] for i in idx], (sm or {}).get(side, m))

    def aabb(self, x0, x1, y0, y1, z0, z1, m, skip=(), sm=None):
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        z0, z1 = sorted((z0, z1))
        self.box(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, y1 - y0, z1 - z0), m, skip, sm)

    def prism(self, poly, d, m, caps=(True, True), cap_m=None):
        """Planar polygon extruded by vector d, faces outward."""
        P = [Vector(p) for p in poly]
        d = Vector(d)
        if newell(P).dot(d) < 0:
            P.reverse()
        Q = [p + d for p in P]
        for i in range(len(P)):
            j = (i + 1) % len(P)
            self.face([P[i], P[j], Q[j], Q[i]], m)
        if caps[0]:
            self.face(P[::-1], cap_m or m)
        if caps[1]:
            self.face(Q, cap_m or m)

    def beam(self, p0, p1, w, h, m, up=(0, 0, 1), caps=True, ext=0.0):
        """Rectangular member from p0 to p1: h along `up` (projected), w across."""
        p0, p1 = Vector(p0), Vector(p1)
        t = (p1 - p0).normalized()
        p0, p1 = p0 - t * ext, p1 + t * ext
        u = Vector(up)
        u = u - t * u.dot(t)
        if u.length < 1e-6:
            u = Vector((1, 0, 0)) - t * t.x
        u.normalize()
        v = t.cross(u)
        poly = [p0 + v * (a * w / 2) + u * (b * h / 2) for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        self.prism(poly, p1 - p0, m, caps=(caps, caps))

    def loft(self, r0, r1, m, cap0=True, cap1=True, cap_m=None):
        r0 = [Vector(p) for p in r0]
        r1 = [Vector(p) for p in r1]
        c = sum(r0 + r1, Vector()) / (2 * len(r0))
        for i in range(len(r0)):
            j = (i + 1) % len(r0)
            q = [r0[i], r0[j], r1[j], r1[i]]
            self.face(q, m, n=sum(q, Vector()) / 4 - c)
        c0, c1 = sum(r0, Vector()) / len(r0), sum(r1, Vector()) / len(r1)
        if cap0:
            self.face(r0, cap_m or m, n=c0 - c1)
        if cap1:
            self.face(r1, cap_m or m, n=c1 - c0)

    def tube(self, path, radius, m, sides=8, caps=True, smooth=True):
        """Round tube along a polyline, shared vertices so it shades smooth; flat caps."""
        path = [Vector(p) for p in path]
        n = len(path)
        radii = list(radius) if isinstance(radius, (list, tuple)) else [radius] * n
        rings, acc = [], [0.0]
        for i, p in enumerate(path):
            t = (path[min(n - 1, i + 1)] - path[max(0, i - 1)]).normalized()
            up = Vector((0, 0, 1)) if abs(t.z) < 0.95 else Vector((1, 0, 0))
            x = t.cross(up).normalized()
            y = t.cross(x).normalized()
            rings.append([self.bm.verts.new(p + (x * math.cos(2 * math.pi * k / sides) + y * math.sin(2 * math.pi * k / sides)) * radii[i])
                          for k in range(sides)])
            if i:
                acc.append(acc[-1] + (p - path[i - 1]).length)
        for i in range(n - 1):
            r0, r1 = rings[i], rings[i + 1]
            circ = 2 * math.pi * radii[i]
            for k in range(sides):
                k2 = (k + 1) % sides
                u0, u1 = circ * k / sides, circ * (k + 1) / sides
                self.face_v([r0[k], r0[k2], r1[k2], r1[k]], m, smooth,
                            [(u0, acc[i]), (u1, acc[i]), (u1, acc[i + 1]), (u0, acc[i + 1])])
        if caps:
            self.face([v.co.copy() for v in rings[-1]], m)
            self.face([v.co.copy() for v in rings[0]][::-1], m)

    def cylx(self, xc, y, z, r, w, m, sides=16):
        self.tube([(xc - w / 2, y, z), (xc + w / 2, y, z)], r, m, sides, caps=True)

    def sweep(self, prof, d, m, smooth=True, away=None):
        """Open polyline extruded by vector d; each face is turned to look away from point `away` (ignoring d)."""
        d = Vector(d)
        A = [self.bm.verts.new(Vector(p)) for p in prof]
        Bv = [self.bm.verts.new(Vector(p) + d) for p in prof]
        dn = d.normalized()
        for i in range(len(prof) - 1):
            q = [A[i], A[i + 1], Bv[i + 1], Bv[i]]
            if away is not None:
                pts = [v.co for v in q]
                c = sum(pts, Vector()) / 4
                o = c - Vector(away)
                o -= dn * o.dot(dn)
                if newell(pts).dot(o) < 0:
                    q.reverse()
            self.face_v(q, m, smooth)

    def card(self, center, normal, up, w, h, m, uv=((0, 0), (1, 0), (1, 1), (0, 1))):
        """Sign face: full 0-1 UVs, reads upright when seen from the `normal` side."""
        n = Vector(normal).normalized()
        x = Vector(up).cross(n).normalized()
        y = n.cross(x).normalized()
        c = Vector(center)
        P = [c - x * w / 2 - y * h / 2, c + x * w / 2 - y * h / 2, c + x * w / 2 + y * h / 2, c - x * w / 2 + y * h / 2]
        return self.face(P, m, list(uv))

    def finish(self, name):
        bm = self.bm
        bm.normal_update()
        for f in bm.faces:                        # box-projected UVs in metres, not mirrored when seen from the front
            if f in self.fixed:
                continue
            n = f.normal
            ax = max(range(3), key=lambda i: abs(n[i]))
            for l in f.loops:
                co = l.vert.co
                if ax == 0:
                    uv = (co.y if n.x > 0 else -co.y, co.z)
                elif ax == 1:
                    uv = (-co.x if n.y > 0 else co.x, co.z)
                else:
                    uv = (co.x, co.y if n.z > 0 else -co.y)
                l[self.uv].uv = uv
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for m in self.mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        return ob


STATS = {}


def export(name, ob):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    kw = dict(filepath=f"{OUT}/{name}.glb", export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
              export_materials="EXPORT", export_image_format="NONE", export_normals=True, export_texcoords=True)
    bpy.ops.export_scene.gltf(**kw)
    me = ob.data
    me.calc_loop_triangles()
    xs, ys, zs = zip(*[v.co[:] for v in me.vertices])
    STATS[name] = {"tris": len(me.loop_triangles),
                   "bbox_blender_m": {"x": [round(min(xs), 3), round(max(xs), 3)], "y": [round(min(ys), 3), round(max(ys), 3)],
                                      "z": [round(min(zs), 3), round(max(zs), 3)]},
                   "materials": [m.name for m in me.materials]}
    print(f"exported {name}: {len(me.loop_triangles)} tris, materials {[m.name for m in me.materials]}")


# ------------------------------------------------------------------ shared parts
RAIL_PROF = [(-0.07, 0), (0.07, 0), (0.07, 0.012), (0.012, 0.032), (0.009, 0.125), (0.036, 0.132), (0.036, 0.17),
             (-0.036, 0.17), (-0.036, 0.132), (-0.009, 0.125), (-0.012, 0.032), (-0.07, 0.012)]


def rail(B, x, z0, y0, y1, m):
    B.prism([(x + px, y0, z0 + pz) for px, pz in RAIL_PROF], (0, y1 - y0, 0), m)


def ibeam_y(B, x, y0, y1, ztop, D, fw, tw, ft, m, mb=None):
    """Built-up I girder running along Y, centred on x, top at ztop."""
    B.aabb(x - fw / 2, x + fw / 2, y0, y1, ztop - ft, ztop, m)
    B.aabb(x - tw / 2, x + tw / 2, y0, y1, ztop - D + ft, ztop - ft, m, skip=("+z", "-z"))
    B.aabb(x - fw / 2, x + fw / 2, y0, y1, ztop - D, ztop - D + ft, mb or m)


def ibeam_x(B, x0, x1, y, ztop, D, fw, tw, ft, m, mb=None):
    B.aabb(x0, x1, y - fw / 2, y + fw / 2, ztop - ft, ztop, m)
    B.aabb(x0, x1, y - tw / 2, y + tw / 2, ztop - D + ft, ztop - ft, m, skip=("+z", "-z"))
    B.aabb(x0, x1, y - fw / 2, y + fw / 2, ztop - D, ztop - D + ft, mb or m)


def stiffeners_y(B, x, ys, ztop, D, fw, tw, ft, m):
    """Web stiffener plates on both sides of a Y girder."""
    for y in ys:
        for s in (-1, 1):
            B.aabb(x + s * tw / 2, x + s * (fw / 2 - 0.015), y - 0.008, y + 0.008, ztop - D + ft, ztop - ft, m,
                   skip=("+z", "-z", "-x" if s > 0 else "+x"))


def stiffeners_x(B, xs, y, ztop, D, fw, tw, ft, m):
    for x in xs:
        for s in (-1, 1):
            B.aabb(x - 0.01, x + 0.01, y + s * tw / 2, y + s * (fw / 2 - 0.015), ztop - D + ft, ztop - ft, m,
                   skip=("+z", "-z", "-y" if s > 0 else "+y"))


def footing(B, cx, cy, sx, sy, top, m):
    """Concrete pier, buried to z -0.4, chamfered top."""
    B.aabb(cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, -0.4, top - 0.18, m, skip=("-z", "+z"))
    B.loft(rect(cx, cy, sx, sy, top - 0.18), rect(cx, cy, sx - 0.28, sy - 0.28, top), m, cap0=False)


def lattice_column(B, cx, cy, w, d, z0, z1, m):
    """Built-up riveted column: two channels (webs on the +-x faces) laced with X bars on the +-y faces, batten plates."""
    tw, ft, fl = 0.022, 0.02, 0.1
    H = z1 - z0
    for s in (-1, 1):
        xw = cx + s * (w / 2 - tw / 2)
        B.aabb(xw - tw / 2, xw + tw / 2, cy - d / 2, cy + d / 2, z0, z1, m, skip=("+z", "-z"))
        for sy in (-1, 1):
            B.aabb(cx + s * (w / 2 - fl), cx + s * (w / 2 - tw), cy + sy * (d / 2 - ft), cy + sy * d / 2, z0, z1, m,
                   skip=("+z", "-z"))
    bt = min(0.35, H * 0.12)
    n = max(2, round((H - 2 * bt) / (w * 0.9)))
    pitch = (H - 2 * bt) / n
    xa, xb = cx - w / 2 + 0.05, cx + w / 2 - 0.05
    for sy in (-1, 1):
        yy = cy + sy * (d / 2 + 0.006)
        for za, zb in ((z0, z0 + bt), (z1 - bt, z1)):
            B.aabb(cx - w / 2 + tw, cx + w / 2 - tw, yy - sy * 0.006, yy + sy * 0.009, za, zb, m)
        for k in range(n):
            za = z0 + bt + k * pitch - 0.03
            zb = za + pitch + 0.06
            B.beam((xa, yy, za), (xb, yy, zb), 0.055, 0.012, m, up=(0, 1, 0), caps=False)
            y2 = yy + sy * 0.006                       # second bar of the X sits proud of the first (no z-fight)
            B.beam((xb, y2, za), (xa, y2, zb), 0.055, 0.012, m, up=(0, 1, 0), caps=False)


def shoe(B, cx, cy, base, top, z0, z1, mr, ms=None):
    """Base plate + flared column shoe."""
    B.aabb(cx - base[0] / 2 - 0.06, cx + base[0] / 2 + 0.06, cy - base[1] / 2 - 0.06, cy + base[1] / 2 + 0.06, z0, z0 + 0.04, mr)
    B.loft(rect(cx, cy, base[0], base[1], z0 + 0.04), rect(cx, cy, top[0], top[1], z1), ms or mr, cap0=False)
    for ax in (-1, 1):                                  # anchor-bolt nuts
        for ay in (-1, 1):
            B.aabb(cx + ax * (base[0] / 2 + 0.01) - 0.03, cx + ax * (base[0] / 2 + 0.01) + 0.03,
                   cy + ay * (base[1] / 2 - 0.06) - 0.03, cy + ay * (base[1] / 2 - 0.06) + 0.03, z0 + 0.04, z0 + 0.09, mr, skip=("-z",))


# ------------------------------------------------------------------ L_Bent
def build_bent():
    B = Builder()
    S, R, C = M("M_LSteel"), M("M_LSteelRust"), M("M_Concrete")
    zc0, zg = 1.3, BENT_TOP - BENT_D                     # column shaft from 1.3 to the girder bottom 4.5
    for s in (-1, 1):
        cx = s * COL_X
        footing(B, cx, 0, 1.5, 1.3, 0.5, C)
        shoe(B, cx, 0, (0.92, 0.78), (0.6, 0.45), 0.5, zc0, R, S)
        lattice_column(B, cx, 0, 0.6, 0.45, zc0, zg - 0.03, S)
        B.aabb(cx - 0.36, cx + 0.36, -0.29, 0.29, zg - 0.03, zg, S)                     # cap plate
        for sy in (-1, 1):                                                               # gusset plates column -> girder
            B.aabb(cx - 0.42, cx + 0.42, sy * 0.25, sy * 0.262, zg - 0.55, zg + 0.45, S)
        # arched knee brace: plate between a quarter circle and the column/girder corner, flange on the arc
        r = 1.4
        kc = Vector((s * (COL_X - 0.3 - r), 0, zg - r))
        arc = [kc + Vector((s * r * math.cos(a), 0, r * math.sin(a))) for a in [math.pi / 2 * i / 8 for i in range(9)]]
        corner = Vector((s * (COL_X - 0.3), 0, zg))
        for yy in (-0.01, 0.01):
            off = Vector((0, yy, 0))
            for i in range(8):
                B.face([corner + off, arc[i] + off, arc[i + 1] + off], S, n=(0, yy, 0))
        for i in range(8):
            a, b = arc[i], arc[i + 1]
            rad = ((a + b) / 2 - kc).normalized()
            B.beam(a - rad * 0.012, b - rad * 0.012, 0.3, 0.024, S, up=rad, caps=False, ext=0.02)
    # deep cross girder
    x0, x1 = -(COL_X + 0.45), COL_X + 0.45
    FW, TW, FTk = 0.5, 0.025, 0.035
    ibeam_x(B, x0, x1, 0, BENT_TOP, BENT_D, FW, TW, FTk, S)
    B.aabb(x0 - 0.0, x0 + 0.02, -FW / 2, FW / 2, zg, BENT_TOP, S)                         # end plates
    B.aabb(x1 - 0.02, x1, -FW / 2, FW / 2, zg, BENT_TOP, S)
    for za, zb in ((BENT_TOP - FTk - 0.09, BENT_TOP - FTk), (zg + FTk, zg + FTk + 0.09)):   # flange angles (riveted look)
        for sy in (-1, 1):
            B.aabb(x0, x1, sy * TW / 2, sy * (TW / 2 + 0.012), za, zb, S, skip=("+z", "-z"))
    xs = [s * (COL_X + d) for s in (-1, 1) for d in (-0.25, 0.25)] + [-4.2 + 0.84 * k for k in range(11)]
    stiffeners_x(B, xs, 0, BENT_TOP, BENT_D, FW, TW, FTk, S)
    export("L_Bent", B.finish("L_Bent"))


# ------------------------------------------------------------------ L_Span15 / L_Span5
def build_span(name, L, junction=False):
    """Deck module; junction=True: no outer walkways, toe boards, handrails or third rails (decks overlap at junctions)."""
    B = Builder()
    S, R, RL, T, G, IN = M("M_LSteel"), M("M_LSteelRust"), M("M_Rail"), M("M_Tie"), M("M_Grating"), M("M_Insulator")
    n = round(L / TIE_PITCH)
    p = L / n
    ty = [-(k + 0.5) * p for k in range(n)]
    longk = list(range(1, n, 3))
    zt, zb = GIRDER_TOP, GIRDER_TOP - GIRDER_D
    FW, TW, FTk = 0.4, 0.02, 0.03
    nst = max(2, round(L / 1.524))
    st_y = [-0.15, -(L - 0.15)] + [-k * L / nst for k in range(1, nst)]
    for s in (-1, 1):
        for gx in GIRDER_X:
            ibeam_y(B, s * gx, 0, -L, zt, GIRDER_D, FW, TW, FTk, S)
            stiffeners_y(B, s * gx, st_y, zt, GIRDER_D, FW, TW, FTk, S)
    # cross frames between the two girders of each track, struts between the tracks, bottom lateral bracing
    ncf = max(2, round(L / 3.81))
    cf_y = [-k * L / ncf for k in range(1, ncf)]
    bays = [-0.06] + cf_y + [-L + 0.06]                  # laterals stop short of the module ends (bbox stays y 0..-L)
    for s in (-1, 1):
        xa, xb = s * (GIRDER_X[0] + TW / 2), s * (GIRDER_X[1] - TW / 2)
        for y in cf_y:
            B.beam((xa, y, zt - 0.1), (xb, y, zb + 0.12), 0.08, 0.08, S, up=(0, 1, 0))
            B.beam((xb, y - 0.08, zt - 0.1), (xa, y - 0.08, zb + 0.12), 0.08, 0.08, S, up=(0, 1, 0))
            B.beam((xa, y - 0.04, zb + 0.08), (xb, y - 0.04, zb + 0.08), 0.1, 0.1, S, up=(0, 0, 1))
        for i in range(len(bays) - 1):
            ya, yb = (bays[i], bays[i + 1]) if i % 2 == 0 else (bays[i + 1], bays[i])
            B.beam((xa, ya, zb + FTk + 0.012), (xb, yb, zb + FTk + 0.012), 0.1, 0.024, S, up=(0, 0, 1))
    xi = GIRDER_X[0] - TW / 2
    for y in cf_y:
        B.beam((-xi, y - 0.04, zb + 0.08), (xi, y - 0.04, zb + 0.08), 0.1, 0.1, S, up=(0, 0, 1))
        B.beam((-xi, y - 0.04, zt - 0.2), (xi, y - 0.04, zt - 0.2), 0.1, 0.1, S, up=(0, 0, 1))
    for i in range(len(bays) - 1):
        ya, yb = (bays[i], bays[i + 1]) if i % 2 else (bays[i + 1], bays[i])
        B.beam((-xi, ya, zb + FTk + 0.012), (xi, yb, zb + FTk + 0.012), 0.1, 0.024, S, up=(0, 0, 1))
    # ties (every third one is a long walkway tie) + tie plates
    for k, y in enumerate(ty):
        if k in longk and not junction:
            B.aabb(-LONG_TIE_X, LONG_TIE_X, y - TIE_W / 2, y + TIE_W / 2, zt, TIE_TOP, T)
        else:
            for s in (-1, 1):
                B.aabb(s * (TRACK_X - TIE_L / 2), s * (TRACK_X + TIE_L / 2), y - TIE_W / 2, y + TIE_W / 2, zt, TIE_TOP, T)
        for s in (-1, 1):
            for gx in GIRDER_X:
                B.aabb(s * gx - 0.165, s * gx + 0.165, y - 0.085, y + 0.085, TIE_TOP, TIE_TOP + PLATE_H, R, skip=("-z", "-x", "+x"))
    for s in (-1, 1):
        for gx in GIRDER_X:                                                             # running rails
            rail(B, s * gx, TIE_TOP + PLATE_H, 0, -L, RL)
        if junction:
            B.aabb(s * 0.8 - 0.075, s * 0.8 + 0.075, 0, -L, TIE_TOP, TIE_TOP + 0.15, T)  # inner timber guard only
            continue
        for k in longk:                                                                 # third rail on insulators
            B.aabb(s * THIRD_X - 0.07, s * THIRD_X + 0.07, ty[k] - 0.07, ty[k] + 0.07, TIE_TOP, THIRD_TOP - 0.17, IN)
        rail(B, s * THIRD_X, THIRD_TOP - 0.17, 0, -L, RL)
        for gxg in (0.8, 3.05):                                                         # timber guards
            B.aabb(s * gxg - 0.075, s * gxg + 0.075, 0, -L, TIE_TOP, TIE_TOP + 0.15, T)
        B.aabb(s * WALK_IN, s * WALK_OUT, 0, -L, TIE_TOP, TIE_TOP + GRATING_T, G)      # outer walkway
        B.aabb(s * (WALK_OUT + 0.005), s * (WALK_OUT + 0.035), 0, -L, TIE_TOP, TIE_TOP + 0.14, T)   # toe board
        for k in longk:                                                                 # handrail posts on the long ties
            B.tube([(s * HANDRAIL_X, ty[k], TIE_TOP + GRATING_T), (s * HANDRAIL_X, ty[k], HANDRAIL_TOP)], 0.024, S, 6)
        for z in (HANDRAIL_TOP, TIE_TOP + GRATING_T + 0.46):
            B.tube([(s * HANDRAIL_X, 0, z), (s * HANDRAIL_X, -L, z)], 0.024, S, 6, caps=False)
    B.aabb(-0.62, 0.62, 0, -L, TIE_TOP, TIE_TOP + GRATING_T, G)                         # centre walkway
    export(name, B.finish(name))


# ------------------------------------------------------------------ L_StationPlatform30 (+ _Stair)
def build_platform(name, stair):
    B = Builder()
    S, R, C, Y, G, CAN, LT, SG, T = (M("M_LSteel"), M("M_LSteelRust"), M("M_Concrete"), M("M_Paint_Yellow"), M("M_Glass"),
                                     M("M_Canopy"), M("M_Light"), M("M_SignPanel"), M("M_Tie"))
    Lm = PLAT_L
    z1, z0 = PLAT_Z, PLAT_Z - PLAT_T
    zb = z0 - PLAT_BEAM_D
    for s in (-1, 1):
        def X(v):
            return s * v
        inner_face = "-x" if s > 0 else "+x"
        # deck: steel edge angle, yellow edge strip, concrete slab
        B.aabb(X(PLAT_EDGE), X(PLAT_EDGE + 0.03), 0, -Lm, z1 - 0.35, z1, S)
        B.aabb(X(PLAT_EDGE + 0.03), X(PLAT_EDGE + 0.63), 0, -Lm, z0, z1, C, sm={"+z": Y})
        B.aabb(X(PLAT_EDGE + 0.63), X(PLAT_OUT), 0, -Lm, z0, z1, C)
        # steel framing: two stringers, four cross beams on outrigger columns, knee struts
        for bx in (4.7, PLAT_COL_X):
            ibeam_y(B, X(bx), 0, -Lm, z0, PLAT_BEAM_D - 0.01, 0.22, 0.015, 0.02, S)
        for fy in FRAMES:
            ibeam_x(B, X(4.55), X(PLAT_OUT), fy, z0, PLAT_BEAM_D, 0.22, 0.015, 0.02, S)
            cx = X(PLAT_COL_X)
            footing(B, cx, fy, 1.1, 1.0, 0.45, C)
            shoe(B, cx, fy, (0.66, 0.56), (0.4, 0.32), 0.45, 1.0, R, S)
            lattice_column(B, cx, fy, 0.4, 0.32, 1.0, zb - 0.02, S)
            B.aabb(cx - 0.25, cx + 0.25, fy - 0.2, fy + 0.2, zb - 0.02, zb, S)
            B.beam((X(PLAT_COL_X - 0.2), fy, zb - 1.15), (X(4.85), fy, zb), 0.14, 0.14, S, up=(0, 1, 0), ext=0.03)
        # canopy: posts over the columns, cross beams, brackets, sloped roof, eave beam, lit underside
        for fy in FRAMES:
            B.aabb(X(6.2), X(6.4), fy - 0.1, fy + 0.1, z1, CANOPY_Z - 0.25, S)
            ibeam_x(B, X(3.6), X(7.0), fy, CANOPY_Z, 0.25, 0.15, 0.012, 0.015, S)
            B.beam((X(6.2), fy, CANOPY_Z - 1.05), (X(4.7), fy, CANOPY_Z - 0.25), 0.1, 0.1, S, up=(0, 1, 0), ext=0.03)
            B.aabb(X(6.2), X(6.08), fy - 0.14, fy + 0.14, 10.15, 10.33, S, sm={inner_face: LT})   # post lamp
        B.prism([(X(3.5), 0, CANOPY_Z), (X(7.0), 0, CANOPY_Z), (X(7.0), 0, CANOPY_Z + 0.3), (X(3.5), 0, CANOPY_Z + 0.18)],
                (0, -Lm, 0), CAN)
        ibeam_y(B, X(6.3), 0, -Lm, CANOPY_Z, 0.24, 0.15, 0.012, 0.015, S)
        for lx in (4.3, 5.7):
            B.face([(X(lx), -0.05, CANOPY_Z - 0.004), (X(lx + 0.16), -0.05, CANOPY_Z - 0.004),
                    (X(lx + 0.16), -Lm + 0.05, CANOPY_Z - 0.004), (X(lx), -Lm + 0.05, CANOPY_Z - 0.004)], LT, n=(0, 0, -1))
        # hanging CTA-style name signs (double-sided, track face toward the track)
        for sy in SIGN_Y:
            sx = 4.2
            B.aabb(X(sx - 0.04), X(sx + 0.04), sy - 1.24, sy + 1.24, 10.33, 10.84, S)
            B.card((X(sx - 0.0405), sy, 10.585), (-s, 0, 0), (0, 0, 1), 2.4, 0.45, SG)
            B.card((X(sx + 0.0405), sy, 10.585), (s, 0, 0), (0, 0, 1), 2.4, 0.45, SG)
            for ry in (sy - 1.0, sy + 1.0):
                B.tube([(X(sx), ry, 10.84), (X(sx), ry, CANOPY_Z)], 0.015, S, 6, caps=False)
        # benches (face the track)
        for by in [SIGN_Y[0], SIGN_Y[1]] + ([] if stair else [-PLAT_L / 2]):
            B.aabb(X(5.3), X(5.75), by - 0.9, by + 0.9, z1 + 0.42, z1 + 0.47, T)
            B.aabb(X(5.75), X(5.8), by - 0.9, by + 0.9, z1 + 0.52, z1 + 0.95, T)
            for ly in (by - 0.75, by + 0.75):
                B.aabb(X(5.35), X(5.8), ly - 0.03, ly + 0.03, z1, z1 + 0.42, S)
                B.aabb(X(5.8), X(5.84), ly - 0.03, ly + 0.03, z1, z1 + 0.95, S)
        # outer glass railing (opening for the stairs in the _Stair variant)
        rx = X(6.9)
        posts = [-(k + 0.5) * Lm / 16 for k in range(16)]
        runs = [(0.0, -Lm)]
        if stair:
            g0, g1 = STAIR_GAP
            posts = [py for py in posts if not (g1 - 0.15 < py < g0 + 0.15)] + [g0 + 0.03, g1 - 0.03]
            runs = [(0.0, g0 + 0.03), (g1 - 0.03, -Lm)]
        for py in posts:
            B.aabb(rx - 0.03, rx + 0.03, py - 0.03, py + 0.03, z1, z1 + 1.1, S)
        for ya, yb in runs:
            for z in (z1 + 1.1, z1 + 0.1):
                B.tube([(rx, ya, z), (rx, yb, z)], 0.025, S, 6, caps=stair)
            B.aabb(rx - 0.008, rx + 0.008, ya, yb, z1 + 0.13, z1 + 1.07, G)
    export(name, B.finish(name))


# ------------------------------------------------------------------ L_StationStairs
def poly_eval(pts, y):
    """z of a polyline given as (y, z) points with y decreasing."""
    for (ya, za), (yb, zb) in zip(pts, pts[1:]):
        if yb <= y <= ya:
            return za + (zb - za) * ((ya - y) / (ya - yb) if ya != yb else 0.0)
    return pts[0][1] if y > pts[0][0] else pts[-1][1]


def offset_clamped(pts, dz, zmin=0.0):
    out = []
    for i, (y, z) in enumerate(pts):
        if i:
            (ya, za), (yb, zb) = pts[i - 1], pts[i]
            a, b = za + dz - zmin, zb + dz - zmin
            if a * b < 0:
                t = a / (a - b)
                out.append((ya + (yb - ya) * t, zmin))
        out.append((y, max(zmin, z + dz)))
    return out


def build_stairs():
    B = Builder()
    S, R, C, Y, G, CAN, LT, SG = (M("M_LSteel"), M("M_LSteelRust"), M("M_Concrete"), M("M_Paint_Yellow"), M("M_Glass"),
                                  M("M_Canopy"), M("M_Light"), M("M_SignPanel"))
    NR = 44                                   # 2 flights x 22 risers of 0.1886 m, 0.254 m treads
    r, g, LAND = PLAT_Z / NR, 0.254, 1.2
    ys, y_end, y_ent = STAIR_GAP[0], STAIR_GAP[1], -1.0
    y0 = ys + 42 * g + LAND                   # first riser of the lower flight (-2.172)
    y1 = y0 - 21 * g - LAND                   # first riser of the upper flight
    wt = 0.12
    xi0, xi1 = STAIR_X0 + wt, STAIR_X1 - wt
    # steps: riser, yellow nosing, concrete tread
    for ystart, zstart in ((y0, 0.0), (y1, 22 * r)):
        for j in range(22):
            yr = ystart - j * g
            za, zb = zstart + j * r, zstart + (j + 1) * r
            B.face([(xi0, yr, za), (xi1, yr, za), (xi1, yr, zb), (xi0, yr, zb)], S, n=(0, 1, 0))
            if j < 21:
                B.face([(xi0, yr, zb), (xi1, yr, zb), (xi1, yr - 0.05, zb), (xi0, yr - 0.05, zb)], Y, n=(0, 0, 1))
                B.face([(xi0, yr - 0.05, zb), (xi1, yr - 0.05, zb), (xi1, yr - g, zb), (xi0, yr - g, zb)], C, n=(0, 0, 1))
    B.aabb(xi0, xi1, y_ent, y0, -0.25, 0.0, C)                                           # entrance floor
    for ya, yb, z, x0 in ((y0 - 21 * g, y1, 22 * r, xi0), (ys, y_end - wt, PLAT_Z, STAIR_X0)):   # mid + top landing
        B.aabb(x0, xi1, ya, yb, z - 0.25, z, C, skip=("+z",))
        xa, xb = x0, xi1
        B.face([(xa, ya, z), (xb, ya, z), (xb, ya - 0.05, z), (xa, ya - 0.05, z)], Y, n=(0, 0, 1))
        B.face([(xa, ya - 0.05, z), (xb, ya - 0.05, z), (xb, yb, z), (xa, yb, z)], C, n=(0, 0, 1))
    # floor (nosing) line, wall / roof outlines
    F = [(y_ent, 0.0), (y0 + g, 0.0), (y0 - 21 * g, 22 * r), (y1 + g, 22 * r), (ys, PLAT_Z), (y_end, PLAT_Z)]
    BOT = offset_clamped(F, -0.45)
    HEAD = 2.7

    def wall(xa, xb, pts_f, pts_b):
        top1 = [(y, z + 1.05) for y, z in pts_f]
        top2 = [(y, z + HEAD) for y, z in pts_f]
        B.prism([(xa, y, z) for y, z in pts_b] + [(xa, y, z) for y, z in reversed(top1)], (xb - xa, 0, 0), S)
        xm = (xa + xb) / 2
        B.prism([(xm - 0.015, y, z) for y, z in top1] + [(xm - 0.015, y, z) for y, z in reversed(top2)], (0.03, 0, 0), G)
        yA, yB = pts_f[0][0], pts_f[-1][0]
        nm = max(1, round((yA - yB) / 1.6))
        for k in range(nm + 1):
            ym = min(yA - 0.03, max(yB + 0.03, yA - (yA - yB) * k / nm))
            zf = poly_eval(pts_f, ym)
            B.aabb(xa, xb, ym - 0.03, ym + 0.03, zf + 1.05, zf + HEAD, S, skip=("-z", "+z"))

    Fi = [p for p in F if p[0] >= ys]
    Bi = [p for p in BOT if p[0] >= ys]
    wall(STAIR_X0, STAIR_X0 + wt, Fi, Bi)                                                 # inner wall (open at the landing)
    wall(STAIR_X1 - wt, STAIR_X1, F, BOT)                                                 # outer wall
    zl = PLAT_Z - 0.45                                                                    # end wall
    B.aabb(STAIR_X0, STAIR_X1, y_end - wt, y_end, zl, PLAT_Z + 1.05, S)
    B.aabb(STAIR_X0, STAIR_X1, y_end - wt / 2 - 0.015, y_end - wt / 2 + 0.015, PLAT_Z + 1.05, PLAT_Z + HEAD, G)
    for xm in (STAIR_X0 + 0.03, (STAIR_X0 + STAIR_X1) / 2, STAIR_X1 - 0.03):
        B.aabb(xm - 0.03, xm + 0.03, y_end - wt, y_end, PLAT_Z + 1.05, PLAT_Z + HEAD, S, skip=("-z", "+z"))
    # roof following the stair, lit strip underneath
    RF = F[:-1] + [(y_end - wt, PLAT_Z)]
    B.prism([(STAIR_X0, y, z + HEAD) for y, z in RF] + [(STAIR_X0, y, z + HEAD + 0.12) for y, z in reversed(RF)],
            (STAIR_X1 + 0.05 - STAIR_X0, 0, 0), S)
    for (ya, za), (yb, zb) in zip(RF, RF[1:]):
        B.face([(8.35, ya, za + HEAD - 0.004), (8.55, ya, za + HEAD - 0.004), (8.55, yb, zb + HEAD - 0.004), (8.35, yb, zb + HEAD - 0.004)],
               LT, n=(0, 0, -1))
    # soffit under the flights
    for (ya, za), (yb, zb) in zip(BOT, BOT[1:]):
        if za > 0.001 or zb > 0.001:
            B.face([(xi0, ya, za), (xi1, ya, za), (xi1, yb, zb), (xi0, yb, zb)], S, n=(0, 0, -1))
    B.face([(STAIR_X0, y_end - wt, zl), (xi1, y_end - wt, zl), (xi1, ys, zl), (STAIR_X0, ys, zl)], S, n=(0, 0, -1))
    # handrails
    HR = [(y0 + g, 0.9), (y0 - 21 * g, 22 * r + 0.9), (y1 + g, 22 * r + 0.9), (ys, PLAT_Z + 0.9)]
    for hx in (xi0 + 0.07, xi1 - 0.07):
        B.tube([(hx, y, z) for y, z in HR], 0.022, S, 6)
    # supports: H posts on footings + an X brace under the top landing
    ymid = (y1 + ys) / 2
    for py, ztop in ((y1 + 0.2, 22 * r - 0.45), (ymid, poly_eval(BOT, ymid)), (y_end + 0.25, zl)):
        for px in (STAIR_X0 + 0.25, STAIR_X1 - 0.25):
            B.aabb(px - 0.3, px + 0.3, py - 0.3, py + 0.3, -0.3, 0.12, C, skip=("-z",))
            for sy in (-1, 1):
                B.aabb(px - 0.13, px + 0.13, py + sy * 0.11, py + sy * 0.13, 0.12, ztop, S, skip=("-z", "+z"))
            B.aabb(px - 0.01, px + 0.01, py - 0.11, py + 0.11, 0.12, ztop, S, skip=("-z", "+z"))
            B.aabb(px - 0.18, px + 0.18, py - 0.16, py + 0.16, 0.12, 0.15, R)
    pyb = y_end + 0.25
    B.beam((STAIR_X0 + 0.3, pyb + 0.16, 0.6), (STAIR_X1 - 0.3, pyb + 0.16, zl - 0.3), 0.1, 0.03, S, up=(0, 1, 0))
    B.beam((STAIR_X1 - 0.3, pyb + 0.2, 0.6), (STAIR_X0 + 0.3, pyb + 0.2, zl - 0.3), 0.1, 0.03, S, up=(0, 1, 0))
    # street entrance: canopy with lit underside, "L" blade sign on the street-side corner
    B.aabb(STAIR_X0 - 0.1, STAIR_X1 + 0.1, 0.0, y_ent - 0.3, HEAD + 0.12, HEAD + 0.28, CAN)
    B.face([(STAIR_X0 + 0.4, -0.12, HEAD + 0.116), (STAIR_X1 - 0.4, -0.12, HEAD + 0.116), (STAIR_X1 - 0.4, y_ent + 0.08, HEAD + 0.116),
            (STAIR_X0 + 0.4, y_ent + 0.08, HEAD + 0.116)], LT, n=(0, 0, -1))
    bx0, bx1, by0, by1, bz0, bz1 = STAIR_X0 - 0.63, STAIR_X0, y_ent - 0.1, y_ent - 0.22, 3.2, 5.6
    B.aabb(bx0, bx1, by0, by1, bz0, bz1, S)
    bc = ((bx0 + bx1) / 2, (bz0 + bz1) / 2)
    B.card((bc[0], by0 + 0.001, bc[1]), (0, 1, 0), (0, 0, 1), 0.55, 2.3, SG)
    B.card((bc[0], by1 - 0.001, bc[1]), (0, -1, 0), (0, 0, 1), 0.55, 2.3, SG)
    B.aabb(bx0, bx1, by0 + 0.02, by1 - 0.02, bz1, bz1 + 0.08, LT)
    B.aabb(bx0, bx1, by0 + 0.02, by1 - 0.02, bz0 - 0.08, bz0, LT)
    export("L_StationStairs", B.finish("L_StationStairs"))


# ------------------------------------------------------------------ L_StationHouse
def glazed_wall(B, along, fixed, a, b, z0, z_sill, z_head, z_top, S, G, doors=(), t=0.1, mull=1.2):
    """Wall along 'x' or 'y' from a to b, centred on `fixed`; steel band, glass with mullions, steel band; doors cut through."""
    lo, hi = sorted((a, b))
    segs, cur = [], lo
    for d0, d1 in sorted(tuple(sorted(d)) for d in doors):
        if d0 > cur:
            segs.append((cur, d0))
        cur = max(cur, d1)
    if cur < hi:
        segs.append((cur, hi))

    def box(u0, u1, za, zb, m, th=t, skip=()):
        if along == "y":
            B.aabb(fixed - th / 2, fixed + th / 2, u0, u1, za, zb, m, skip=skip)
        else:
            B.aabb(u0, u1, fixed - th / 2, fixed + th / 2, za, zb, m, skip=skip)
    for u0, u1 in segs:
        box(u0, u1, z0, z_sill, S)
        box(u0, u1, z_sill, z_head, G, th=0.03)
        nm = max(1, round((u1 - u0) / mull))
        for k in range(nm + 1):
            u = min(u1 - 0.03, max(u0 + 0.03, u0 + (u1 - u0) * k / nm))
            box(u - 0.03, u + 0.03, z_sill, z_head, S, skip=("-z", "+z"))
    box(lo, hi, z_head, z_top, S)


def build_house():
    B = Builder()
    S, G, CAN, LT, SG = M("M_LSteel"), M("M_Glass"), M("M_Canopy"), M("M_Light"), M("M_SignPanel")
    x0, x1, y0, y1 = 5.0, 6.75, -12.24, -18.24
    z0, zs, zh, zt = PLAT_Z, PLAT_Z + 0.9, 10.5, 10.85
    glazed_wall(B, "y", x0 + 0.05, y0, y1, z0, zs, zh, zt, S, G)                                  # track side
    glazed_wall(B, "y", x1 - 0.05, y0, y1, z0, zs, zh, zt, S, G, doors=[STAIR_GAP])               # stair side
    for yw in (y0 - 0.05, y1 + 0.05):                                                              # ends: doors to platform
        glazed_wall(B, "x", yw, x0 + 0.1, x1 - 0.1, z0, zs, zh, zt, S, G, doors=[(5.35, 6.35)], mull=0.6)
    B.aabb(x0 - 0.06, x1 + 0.06, y0 + 0.06, y1 - 0.06, zt, zt + 0.12, CAN)                         # roof
    B.face([(5.3, y0 - 0.5, zt - 0.004), (6.45, y0 - 0.5, zt - 0.004), (6.45, y1 + 0.5, zt - 0.004), (5.3, y1 + 0.5, zt - 0.004)],
           LT, n=(0, 0, -1))
    yc = (y0 + y1) / 2
    B.card((x0 - 0.002, yc, (zh + zt) / 2), (-1, 0, 0), (0, 0, 1), 3.2, 0.28, SG)                  # name band toward the track
    for ty in (y0 - 1.1, y1 + 1.1):                                                                # fare gates
        for tx in (5.3, 5.85, 6.4):
            B.aabb(tx - 0.09, tx + 0.09, ty - 0.35, ty + 0.35, z0, z0 + 1.0, S, sm={"+z": LT})
    export("L_StationHouse", B.finish("L_StationHouse"))


# ------------------------------------------------------------------ L_TrainCar
def build_train():
    B = Builder()
    ST, LS, G, D, LT, IN, DS, RL = (M("M_Stainless"), M("M_LineStripe"), M("M_Glass"), M("M_TrainDark"), M("M_Light"),
                                    M("M_TrainInterior"), M("M_DestSign"), M("M_Rail"))
    HL, HW, YE = 7.3, 1.4, 7.22
    Z0, ZF, ZS0, ZS1, ZW0, ZW1, ZE, ZR, ZD = 0.95, 1.12, 1.62, 1.80, 1.95, 2.85, 3.2, 3.52, 3.0
    half = [("p", 0.22), ("w", 0.9), ("p", 0.25), ("w", 1.2), ("p", 0.2), ("d", 1.4), ("p", 0.2), ("w", 1.25), ("p", 0.2), ("w", 1.25)]
    half.append(("p", YE - sum(w for _, w in half)))
    ivs, y = [], -YE
    for kind, w in half:
        ivs.append((kind, y, y + w))
        y += w
    ivs += [(k, -b, -a) for k, a, b in reversed(ivs)]

    def sq(s, ya, yb, za, zb, m, x=None):
        x = s * HW if x is None else x
        B.face([(x, ya, za), (x, yb, za), (x, yb, zb), (x, ya, zb)], m, n=(s, 0, 0))

    def win(s, ya, yb, za, zb, xo=None, inset=0.035):
        xo = s * HW if xo is None else xo
        xi = xo - s * inset
        sq(s, ya, yb, za, zb, G, x=xi)
        B.face([(xo, ya, za), (xo, yb, za), (xi, yb, za), (xi, ya, za)], D, n=(0, 0, 1))
        B.face([(xo, ya, zb), (xo, yb, zb), (xi, yb, zb), (xi, ya, zb)], D, n=(0, 0, -1))
        B.face([(xo, ya, za), (xo, ya, zb), (xi, ya, zb), (xi, ya, za)], D, n=(0, 1, 0))
        B.face([(xo, yb, za), (xo, yb, zb), (xi, yb, zb), (xi, yb, za)], D, n=(0, -1, 0))

    for s in (-1, 1):
        for kind, ya, yb in ivs:
            if kind == "d":
                sq(s, ya, yb, Z0, ZF, ST)
                sq(s, ya, yb, ZD, ZE, ST)
                xo, xl = s * HW, s * (HW - 0.015)                     # leaves recessed 15 mm, dark reveals + centre seam
                B.face([(xo, ya, ZF), (xo, ya, ZD), (xl, ya, ZD), (xl, ya, ZF)], D, n=(0, 1, 0))
                B.face([(xo, yb, ZF), (xo, yb, ZD), (xl, yb, ZD), (xl, yb, ZF)], D, n=(0, -1, 0))
                B.face([(xo, ya, ZD), (xo, yb, ZD), (xl, yb, ZD), (xl, ya, ZD)], D, n=(0, 0, -1))
                ym = (ya + yb) / 2
                sq(s, ym - 0.008, ym + 0.008, ZF, ZD, D, x=s * (HW - 0.03))
                for la, lb in ((ya, ym - 0.008), (ym + 0.008, yb)):
                    sq(s, la, lb, ZF, ZS0, ST, x=xl)
                    sq(s, la, lb, ZS0, ZS1, LS, x=xl)
                    sq(s, la, lb, ZS1, 1.85, ST, x=xl)
                    sq(s, la, la + 0.1, 1.85, 2.75, ST, x=xl)
                    sq(s, lb - 0.1, lb, 1.85, 2.75, ST, x=xl)
                    win(s, la + 0.1, lb - 0.1, 1.85, 2.75, xo=xl, inset=0.025)
                    sq(s, la, lb, 2.75, ZD, ST, x=xl)
            else:
                sq(s, ya, yb, Z0, ZS0, ST)
                sq(s, ya, yb, ZS0, ZS1, LS)
                sq(s, ya, yb, ZS1, ZW0, ST)
                if kind == "w":
                    win(s, ya, yb, ZW0, ZW1)
                else:
                    sq(s, ya, yb, ZW0, ZW1, ST)
                sq(s, ya, yb, ZW1, ZE, ST)
    # roof (smooth elliptical arc) + end caps, AC pods
    N = 12
    arc = [(HW * math.cos(math.pi * i / N), ZE + (ZR - ZE) * math.sin(math.pi * i / N)) for i in range(N + 1)]
    B.sweep([(x, -YE, z) for x, z in arc], (0, 2 * YE, 0), ST, smooth=True, away=(0, 0, 2.0))
    for yc in (-4.3, 4.3):
        B.loft(rect(0, yc, 1.9, 2.9, 3.36), rect(0, yc, 1.66, 2.6, 3.70), ST, cap0=False)
        B.aabb(-0.6, 0.6, yc - 0.9, yc + 0.9, 3.70, 3.71, D, skip=("-z",))                 # grille
    # ends (both identical: windshield, end door window, destination sign, lights, anticlimber, coupler)
    for sy in (-1, 1):
        y = sy * YE
        nrm = (0, sy, 0)

        def q(xa, xb, za, zb, m, yy=y):
            B.face([(xa, yy, za), (xb, yy, za), (xb, yy, zb), (xa, yy, zb)], m, n=nrm)
        q(-HW, HW, Z0, ZS0, ST)
        q(-HW, HW, ZS0, ZS1, LS)
        q(-HW, HW, ZS1, 2.0, ST)
        for xa, xb, k in ((-HW, -1.25, 0), (-1.25, -0.5, 1), (-0.5, -0.42, 0), (-0.42, 0.42, 1), (0.42, 0.5, 0), (0.5, 1.25, 1), (1.25, HW, 0)):
            if not k:
                q(xa, xb, 2.0, ZW1, ST)
                continue
            yi = y - sy * 0.04
            q(xa, xb, 2.0, ZW1, G, yy=yi)
            B.face([(xa, y, 2.0), (xb, y, 2.0), (xb, yi, 2.0), (xa, yi, 2.0)], D, n=(0, 0, 1))
            B.face([(xa, y, ZW1), (xb, y, ZW1), (xb, yi, ZW1), (xa, yi, ZW1)], D, n=(0, 0, -1))
            B.face([(xa, y, 2.0), (xa, y, ZW1), (xa, yi, ZW1), (xa, yi, 2.0)], D, n=(1, 0, 0))
            B.face([(xb, y, 2.0), (xb, y, ZW1), (xb, yi, ZW1), (xb, yi, 2.0)], D, n=(-1, 0, 0))
        q(-HW, -0.6, ZW1, ZE, ST)
        q(0.6, HW, ZW1, ZE, ST)
        q(-0.6, 0.6, ZW1, 2.9, ST)
        q(-0.6, 0.6, 3.12, ZE, ST)
        B.card((0, y + sy * 0.001, 3.01), nrm, (0, 0, 1), 1.2, 0.22, DS)
        B.face([(x, y, z) for x, z in arc], ST, n=nrm)
        front = "+y" if sy > 0 else "-y"
        for hx in (-0.95, 0.95):
            B.aabb(hx - 0.17, hx + 0.17, y, y + sy * 0.05, 1.25, 1.45, ST, sm={front: LT})
        for hx in (-1.22, 1.22):
            B.aabb(hx - 0.07, hx + 0.07, y, y + sy * 0.03, 2.93, 3.07, ST, sm={front: LT})
        B.aabb(-1.3, 1.3, y, sy * HL, 0.97, 1.12, D)
        B.aabb(-0.14, 0.14, sy * 6.9, sy * HL, 0.72, 0.92, D)
        B.aabb(-0.4, 0.4, sy * 6.95, sy * 7.05, 0.75, 0.97, D)
    B.face([(-HW, -YE, Z0), (HW, -YE, Z0), (HW, YE, Z0), (-HW, YE, Z0)], D, n=(0, 0, -1))
    # underframe equipment
    for yc, ln, dp, wx in ((-2.7, 1.5, 0.45, 1.1), (-0.85, 1.4, 0.36, 0.9), (0.95, 1.6, 0.42, 1.15), (2.75, 1.3, 0.34, 1.0)):
        B.aabb(-wx, wx, yc - ln / 2, yc + ln / 2, Z0 - dp, Z0, D, skip=("+z",))
    # trucks: wheels on z 0, gauge 1.435, side frames, bolster, third-rail shoes both sides
    for tc in (-5.15, 5.15):
        for ay in (tc - 1.04, tc + 1.04):
            for sx in (-1, 1):
                B.cylx(sx * 0.75, ay, 0.356, 0.356, 0.13, RL, 16)
                B.aabb(sx * 0.95 - 0.1, sx * 0.95 + 0.1, ay - 0.14, ay + 0.14, 0.24, 0.48, D)
            B.cylx(0, ay, 0.356, 0.07, 1.5, D, 8)
        for sx in (-1, 1):
            B.aabb(sx * 0.95 - 0.07, sx * 0.95 + 0.07, tc - 1.4, tc + 1.4, 0.40, 0.62, D)
            B.aabb(sx * 1.02, sx * 1.46, tc - 0.08, tc + 0.08, 0.22, 0.30, D)
            B.aabb(sx * 1.40, sx * 1.60, tc - 0.18, tc + 0.18, 0.135, 0.17, RL)
            for sy2 in (-1, 1):
                B.cylx(sx * 0.95, tc + sy2 * 0.45, 0.7, 0.13, 0.22, D, 10)    # air springs (horizontal stubs)
        B.aabb(-1.02, 1.02, tc - 0.25, tc + 0.25, 0.55, 0.80, D)
        for tyy in (tc - 0.55, tc + 0.55):
            B.aabb(-0.9, 0.9, tyy - 0.08, tyy + 0.08, 0.42, 0.56, D)
        B.aabb(-0.5, 0.5, tc - 0.4, tc + 0.4, 0.80, Z0, D, skip=("+z",))      # centre pivot / pedestal
    # interior (seen through the glass)
    xi = HW - 0.06
    B.face([(-xi, -7.0, ZF), (xi, -7.0, ZF), (xi, 7.0, ZF), (-xi, 7.0, ZF)], IN, n=(0, 0, 1))
    B.face([(-xi, -7.0, 3.02), (xi, -7.0, 3.02), (xi, 7.0, 3.02), (-xi, 7.0, 3.02)], IN, n=(0, 0, -1))
    B.face([(-0.12, -6.8, 3.015), (0.12, -6.8, 3.015), (0.12, 6.8, 3.015), (-0.12, 6.8, 3.015)], LT, n=(0, 0, -1))
    for s in (-1, 1):
        x = s * xi
        for za, zb in ((ZF, ZW0), (ZW1, 3.02)):
            B.face([(x, -7.0, za), (x, 7.0, za), (x, 7.0, zb), (x, -7.0, zb)], IN, n=(-s, 0, 0))
        for ya, yb in ((-2.95, 2.95), (-6.8, -4.55), (4.55, 6.8)):
            B.aabb(x, s * (xi - 0.45), ya, yb, ZF, ZF + 0.45, IN, skip=("-z",))
            B.aabb(x, s * (xi - 0.08), ya, yb, ZF + 0.45, ZF + 0.95, IN)
    for sy in (-1, 1):
        for za, zb in ((ZF, 2.0), (ZW1, 3.02)):
            B.face([(-xi, sy * 7.0, za), (xi, sy * 7.0, za), (xi, sy * 7.0, zb), (-xi, sy * 7.0, zb)], IN, n=(0, -sy, 0))
    export("L_TrainCar", B.finish("L_TrainCar"))



# ------------------------------------------------------------------ 20 Oct 2026: parts for a layout that fits the streets
# (Scripts/rail/l_layout.py places them): bents as separate columns + a cross girder so each column can stand at the
# curb or in a parking lane on its own; junction spans; one-sided cantilevered platforms; stair bridges for wide
# streets; terminal bumpers and end fence; a through truss for long spans over big junctions; a collision slab.
ZG = BENT_TOP - BENT_D                               # 4.5: street clearance under the cross girder
GIRDER_UNIT = 2 * COL_X + 0.9                        # 10.9: L_BentGirder length (bearing points at +-5.0)


def column_parts(B, cx, inward):
    """One bent column at x = cx (y = 0): footing, shoe, latticed shaft, cap, gussets, arched knee brace toward `inward`."""
    S, R, C = M("M_LSteel"), M("M_LSteelRust"), M("M_Concrete")
    zc0 = 1.3
    footing(B, cx, 0, 1.5, 1.3, 0.5, C)
    shoe(B, cx, 0, (0.92, 0.78), (0.6, 0.45), 0.5, zc0, R, S)
    lattice_column(B, cx, 0, 0.6, 0.45, zc0, ZG - 0.03, S)
    B.aabb(cx - 0.36, cx + 0.36, -0.29, 0.29, ZG - 0.03, ZG, S)
    for sy in (-1, 1):
        B.aabb(cx - 0.42, cx + 0.42, sy * 0.25, sy * 0.262, ZG - 0.55, ZG, S)
    r = 1.4
    kc = Vector((cx + inward * (0.3 + r), 0, ZG - r))
    arc = [kc + Vector((-inward * r * math.cos(a), 0, r * math.sin(a))) for a in [math.pi / 2 * i / 8 for i in range(9)]]
    corner = Vector((cx + inward * 0.3, 0, ZG))
    for yy in (-0.01, 0.01):
        off = Vector((0, yy, 0))
        for i in range(8):
            B.face([corner + off, arc[i] + off, arc[i + 1] + off], S, n=(0, yy, 0))
    for i in range(8):
        a, b = arc[i], arc[i + 1]
        rad = ((a + b) / 2 - kc).normalized()
        B.beam(a - rad * 0.012, b - rad * 0.012, 0.3, 0.024, S, up=rad, caps=False, ext=0.02)


def build_bent_column():
    """L_BentColumn: one column at the origin, knee brace toward +X (turn it so +X points under the deck)."""
    B = Builder()
    column_parts(B, 0.0, +1)
    export("L_BentColumn", B.finish("L_BentColumn"))


def build_bent_girder():
    """L_BentGirder: the deep cross girder, x -5.45..5.45 (bearing on columns at +-5.0), bottom z 4.5, top 5.9; scale X so
    the bearing points land on the two columns: sx = (column spacing + 0.9) / 10.9."""
    B = Builder()
    S = M("M_LSteel")
    x0, x1 = -GIRDER_UNIT / 2, GIRDER_UNIT / 2
    FW, TW, FTk = 0.5, 0.025, 0.035
    ibeam_x(B, x0, x1, 0, BENT_TOP, BENT_D, FW, TW, FTk, S)
    B.aabb(x0, x0 + 0.02, -FW / 2, FW / 2, ZG, BENT_TOP, S)
    B.aabb(x1 - 0.02, x1, -FW / 2, FW / 2, ZG, BENT_TOP, S)
    for za, zb in ((BENT_TOP - FTk - 0.09, BENT_TOP - FTk), (ZG + FTk, ZG + FTk + 0.09)):
        for sy in (-1, 1):
            B.aabb(x0, x1, sy * TW / 2, sy * (TW / 2 + 0.012), za, zb, S, skip=("+z", "-z"))
    xs = [s * (COL_X + d) for s in (-1, 1) for d in (-0.25, 0.25)] + [-4.2 + 0.84 * k for k in range(11)]
    stiffeners_x(B, xs, 0, BENT_TOP, BENT_D, FW, TW, FTk, S)
    export("L_BentGirder", B.finish("L_BentGirder"))


def build_plat_side(name, stair):
    """One side (+X) of a 30.48 m platform module, cantilevered off the deck (no ground columns): the cross beams run in
    over the walkway and a strut drops to the outer deck girder's bottom flange. Same frame as the spans (y 0..-30.48).
    The other side: the same mesh placed from the module's far end back to its start."""
    B = Builder()
    S, C, Y, G, CAN, LT, SG, T = (M("M_LSteel"), M("M_Concrete"), M("M_Paint_Yellow"), M("M_Glass"), M("M_Canopy"),
                                  M("M_Light"), M("M_SignPanel"), M("M_Tie"))
    Lm = PLAT_L
    z1, z0 = PLAT_Z, PLAT_Z - PLAT_T
    zb = z0 - PLAT_BEAM_D
    gx = GIRDER_X[1]                                   # outer deck girder (2.65), bottom flange at z 5.4
    B.aabb(PLAT_EDGE, PLAT_EDGE + 0.03, 0, -Lm, z1 - 0.35, z1, S)
    B.aabb(PLAT_EDGE + 0.03, PLAT_EDGE + 0.63, 0, -Lm, z0, z1, C, sm={"+z": Y})
    B.aabb(PLAT_EDGE + 0.63, PLAT_OUT, 0, -Lm, z0, z1, C)
    for bx in (4.7, PLAT_COL_X):
        ibeam_y(B, bx, 0, -Lm, z0, PLAT_BEAM_D - 0.01, 0.22, 0.015, 0.02, S)
    for fy in FRAMES:
        ibeam_x(B, PLAT_EDGE + 0.1, PLAT_OUT, fy, z0, PLAT_BEAM_D, 0.22, 0.015, 0.02, S)
        B.aabb(PLAT_EDGE + 0.1, PLAT_EDGE + 0.3, fy - 0.11, fy + 0.11, GIRDER_TOP - 0.02, zb, S)        # hanger to the girder top
        B.beam((gx + 0.12, fy, GIRDER_TOP - GIRDER_D + 0.06), (PLAT_COL_X, fy, zb + 0.02), 0.2, 0.2, S, up=(0, 1, 0), ext=0.04)
        B.beam((gx + 0.12, fy, GIRDER_TOP - 0.25), (PLAT_COL_X, fy, zb + 0.02), 0.12, 0.12, S, up=(0, 1, 0), ext=0.02)
        B.aabb(gx + 0.02, gx + 0.22, fy - 0.15, fy + 0.15, GIRDER_TOP - GIRDER_D, GIRDER_TOP - GIRDER_D + 0.3, S)  # gusset
    for fy in FRAMES:
        B.aabb(6.2, 6.4, fy - 0.1, fy + 0.1, z1, CANOPY_Z - 0.25, S)
        ibeam_x(B, 3.6, 7.0, fy, CANOPY_Z, 0.25, 0.15, 0.012, 0.015, S)
        B.beam((6.2, fy, CANOPY_Z - 1.05), (4.7, fy, CANOPY_Z - 0.25), 0.1, 0.1, S, up=(0, 1, 0), ext=0.03)
        B.aabb(6.2, 6.08, fy - 0.14, fy + 0.14, 10.15, 10.33, S, sm={"-x": LT})
    B.prism([(3.5, 0, CANOPY_Z), (7.0, 0, CANOPY_Z), (7.0, 0, CANOPY_Z + 0.3), (3.5, 0, CANOPY_Z + 0.18)], (0, -Lm, 0), CAN)
    ibeam_y(B, 6.3, 0, -Lm, CANOPY_Z, 0.24, 0.15, 0.012, 0.015, S)
    for lx in (4.3, 5.7):
        B.face([(lx, -0.05, CANOPY_Z - 0.004), (lx + 0.16, -0.05, CANOPY_Z - 0.004), (lx + 0.16, -Lm + 0.05, CANOPY_Z - 0.004),
                (lx, -Lm + 0.05, CANOPY_Z - 0.004)], LT, n=(0, 0, -1))
    for sy in SIGN_Y:
        sx = 4.2
        B.aabb(sx - 0.04, sx + 0.04, sy - 1.24, sy + 1.24, 10.33, 10.84, S)
        B.card((sx - 0.0405, sy, 10.585), (-1, 0, 0), (0, 0, 1), 2.4, 0.45, SG)
        B.card((sx + 0.0405, sy, 10.585), (1, 0, 0), (0, 0, 1), 2.4, 0.45, SG)
        for ry in (sy - 1.0, sy + 1.0):
            B.tube([(sx, ry, 10.84), (sx, ry, CANOPY_Z)], 0.015, S, 6, caps=False)
    for by in [SIGN_Y[0], SIGN_Y[1]] + ([] if stair else [-PLAT_L / 2]):
        B.aabb(5.3, 5.75, by - 0.9, by + 0.9, z1 + 0.42, z1 + 0.47, T)
        B.aabb(5.75, 5.8, by - 0.9, by + 0.9, z1 + 0.52, z1 + 0.95, T)
        for ly in (by - 0.75, by + 0.75):
            B.aabb(5.35, 5.8, ly - 0.03, ly + 0.03, z1, z1 + 0.42, S)
            B.aabb(5.8, 5.84, ly - 0.03, ly + 0.03, z1, z1 + 0.95, S)
    rx = 6.9
    posts = [-(k + 0.5) * Lm / 16 for k in range(16)]
    runs = [(0.0, -Lm)]
    if stair:
        g0, g1 = STAIR_GAP
        posts = [py for py in posts if not (g1 - 0.15 < py < g0 + 0.15)] + [g0 + 0.03, g1 - 0.03]
        runs = [(0.0, g0 + 0.03), (g1 - 0.03, -Lm)]
    for py in posts:
        B.aabb(rx - 0.03, rx + 0.03, py - 0.03, py + 0.03, z1, z1 + 1.1, S)
    for ya, yb in runs:
        for z in (z1 + 1.1, z1 + 0.1):
            B.tube([(rx, ya, z), (rx, yb, z)], 0.025, S, 6, caps=stair)
        B.aabb(rx - 0.008, rx + 0.008, ya, yb, z1 + 0.13, z1 + 1.07, G)
    export(name, B.finish(name))


def build_stair_bridge():
    """L_StairBridge: enclosed walkway from the platform's stair opening out to a stair tower set back on a wide street.
    x 0..1 (scale X to the gap; place at the platform's outer edge, x 6.95 of the platform frame), y = the stair
    opening (-14.04..-16.44), floor at platform level."""
    B = Builder()
    S, C, Y, G, CAN, LT = M("M_LSteel"), M("M_Concrete"), M("M_Paint_Yellow"), M("M_Glass"), M("M_Canopy"), M("M_Light")
    ya, yb = STAIR_GAP
    z1 = PLAT_Z
    HEAD = 2.7
    B.aabb(0.0, 1.0, ya, yb, z1 - 0.25, z1, C)
    for yy in (ya + 0.25, yb - 0.25):
        ibeam_x(B, 0.0, 1.0, yy, z1 - 0.25, 0.45, 0.2, 0.015, 0.02, S)
    for y0_, inward in ((ya, -1), (yb, 1)):                       # side walls: steel dado, glass, head rail
        B.aabb(0.0, 1.0, y0_, y0_ + inward * 0.12, z1, z1 + 1.05, S)
        B.aabb(0.0, 1.0, y0_ + inward * 0.045, y0_ + inward * 0.075, z1 + 1.05, z1 + HEAD - 0.08, G)
        B.aabb(0.0, 1.0, y0_, y0_ + inward * 0.12, z1 + HEAD - 0.08, z1 + HEAD, S)
    B.aabb(-0.02, 1.02, ya + 0.05, yb - 0.05, z1 + HEAD, z1 + HEAD + 0.12, CAN)
    B.face([(0.0, ya - 0.5, z1 + HEAD - 0.004), (1.0, ya - 0.5, z1 + HEAD - 0.004), (1.0, yb + 0.5, z1 + HEAD - 0.004),
            (0.0, yb + 0.5, z1 + HEAD - 0.004)], LT, n=(0, 0, -1))
    export("L_StairBridge", B.finish("L_StairBridge"))


def build_bumper():
    """L_Bumper: buffer stops for both tracks at the end of the line. Module frame y 0..-2.4: the deck end at y 0, the
    buffer faces toward -Y (where the trains come from); place from the end point back along the track."""
    B = Builder()
    S, R, Y, LT, RL = M("M_LSteel"), M("M_LSteelRust"), M("M_Paint_Yellow"), M("M_Light"), M("M_Rail")
    zr = TOR
    for tx in (-TRACK_X, TRACK_X):
        for sx in (-1, 1):                                                  # two raked rail-steel struts per rail
            x = tx + sx * (GAUGE / 2 + 0.036)
            B.beam((x, -0.2, TIE_TOP), (x, -1.9, zr + 0.75), 0.17, 0.08, RL, up=(0, -1, 1))
            B.beam((x, -0.25, TIE_TOP), (x, -0.25, zr + 0.95), 0.14, 0.14, S)
        B.aabb(tx - 1.2, tx + 1.2, -1.75, -2.05, zr + 0.55, zr + 1.05, Y)  # buffer beam (yellow)
        for sx in (-0.85, 0.85):                                            # spring buffers + plates
            B.tube([(tx + sx, -2.05, zr + 0.8), (tx + sx, -2.35, zr + 0.8)], 0.11, S, 10)
            B.aabb(tx + sx - 0.22, tx + sx + 0.22, -2.35, -2.42, zr + 0.58, zr + 1.02, R)
        B.aabb(tx - 0.12, tx + 0.12, -1.9, -2.0, zr + 1.05, zr + 1.35, S)
        B.aabb(tx - 0.14, tx + 0.14, -2.0, -2.06, zr + 1.35, zr + 1.63, S)
        mr = M("M_LineStripe")
        B.aabb(tx - 0.1, tx + 0.1, -2.06, -2.08, zr + 1.39, zr + 1.59, mr)  # red end lamp face
    export("L_Bumper", B.finish("L_Bumper"))


def build_end_fence():
    """L_EndFence: closes the end of the deck: steel end plate over the girder ends, a fence on top, red lamps.
    Frame y 0..-0.4 at the deck end (y 0 = end); place from the end point back along the track."""
    B = Builder()
    S, R, LT, MR = M("M_LSteel"), M("M_LSteelRust"), M("M_Light"), M("M_LineStripe")
    W = WALK_OUT + 0.05
    B.aabb(-W, W, 0.0, -0.03, GIRDER_TOP - GIRDER_D - 0.05, TIE_TOP + 0.2, S)
    for x in [-W + 0.05 + k * (2 * W - 0.1) / 8 for k in range(9)]:
        B.aabb(x - 0.04, x + 0.04, -0.05, -0.13, TIE_TOP, TIE_TOP + 1.25, S)
    for z in (TIE_TOP + 0.45, TIE_TOP + 0.85, TIE_TOP + 1.25):
        B.tube([(-W + 0.05, -0.09, z), (W - 0.05, -0.09, z)], 0.03, S, 6)
    for x in (-W + 0.2, W - 0.2):
        B.aabb(x - 0.1, x + 0.1, -0.13, -0.33, TIE_TOP + 1.25, TIE_TOP + 1.45, S)
        B.aabb(x - 0.09, x + 0.09, 0.005, 0.0, TIE_TOP + 1.27, TIE_TOP + 1.43, MR)
    export("L_EndFence", B.finish("L_EndFence"))


TRUSS_L, TRUSS_X, TRUSS_H, TRUSS_PANELS = 45.0, 4.95, 5.6, 6


def build_truss():
    """L_Truss: a Pratt through truss beside the deck for long spans over big junctions (the bents at its ends carry it).
    y 0..-45 (scale Y to the span), trusses at x +-4.95 (scale X for curves), bottom chord at the deck girder top."""
    B = Builder()
    S, R = M("M_LSteel"), M("M_LSteelRust")
    z0 = GIRDER_TOP - 0.6
    z1 = z0 + TRUSS_H
    pl = TRUSS_L / TRUSS_PANELS
    ys = [-k * pl for k in range(TRUSS_PANELS + 1)]
    for sx in (-1, 1):
        x = sx * TRUSS_X
        B.beam((x, 0.0, z0), (x, -TRUSS_L, z0), 0.45, 0.6, S, up=(0, 0, 1))                       # bottom chord
        B.beam((x, ys[1], z1), (x, ys[-2], z1), 0.5, 0.45, S, up=(0, 0, 1), ext=0.2)               # top chord
        B.beam((x, ys[0], z0 + 0.2), (x, ys[1], z1), 0.5, 0.45, S, up=(1, 0, 0), ext=0.1)         # inclined end posts
        B.beam((x, ys[-1], z0 + 0.2), (x, ys[-2], z1), 0.5, 0.45, S, up=(1, 0, 0), ext=0.1)
        for k in range(1, TRUSS_PANELS):                                                            # verticals
            B.beam((x, ys[k], z0 + 0.3), (x, ys[k], z1 - 0.2), 0.3, 0.32, S, up=(1, 0, 0))
        for k in range(1, TRUSS_PANELS - 1):                                                        # Pratt diagonals toward the middle
            if k < TRUSS_PANELS / 2:
                B.beam((x, ys[k], z1 - 0.2), (x, ys[k + 1], z0 + 0.3), 0.22, 0.26, S, up=(1, 0, 0))
            else:
                B.beam((x, ys[k + 1], z1 - 0.2), (x, ys[k], z0 + 0.3), 0.22, 0.26, S, up=(1, 0, 0))
        for k in range(TRUSS_PANELS + 1):                                                           # gusset plates
            B.aabb(x - 0.26, x + 0.26, ys[k] - 0.5 if k else -0.05, ys[k] + 0.5 if k < TRUSS_PANELS else ys[k] + 0.05, z0 - 0.3, z0 + 0.5, R)
    for k in range(1, TRUSS_PANELS):                                                                # top struts + X bracing
        B.beam((-TRUSS_X, ys[k], z1), (TRUSS_X, ys[k], z1), 0.25, 0.35, S, up=(0, 0, 1))
        if k < TRUSS_PANELS - 1:
            B.beam((-TRUSS_X, ys[k], z1 + 0.1), (TRUSS_X, ys[k + 1], z1 + 0.1), 0.12, 0.05, S, up=(0, 0, 1))
            B.beam((TRUSS_X, ys[k], z1 + 0.16), (-TRUSS_X, ys[k + 1], z1 + 0.16), 0.12, 0.05, S, up=(0, 0, 1))
    for yk in (ys[1], ys[-2]):                                                                      # portal frames with knee braces
        B.beam((-TRUSS_X, yk, z1 - 0.9), (TRUSS_X, yk, z1 - 0.9), 0.25, 0.5, S, up=(0, 0, 1))
        for sx in (-1, 1):
            B.beam((sx * TRUSS_X, yk, z1 - 2.0), (sx * (TRUSS_X - 1.4), yk, z1 - 0.9), 0.14, 0.12, S, up=(0, 1, 0))
    export("L_Truss", B.finish("L_Truss"))


def build_deck_slab():
    """L_DeckSlab: a 1 m box (x -0.5..0.5, y 0..-1, z 0..1) for the invisible collision floor the car drives on along the
    deck (scaled to each chord: 8.9 m wide, 0.2 m thick, top at top of rail)."""
    B = Builder()
    B.aabb(-0.5, 0.5, 0.0, -1.0, 0.0, 1.0, M("M_Concrete"))
    export("L_DeckSlab", B.finish("L_DeckSlab"))


# ------------------------------------------------------------------ kit.json
def write_kit_json():
    path = RAIL + "/kit.json"
    old = {}
    if os.path.exists(path):
        try:
            old = json.load(open(path)).get("assets", {})
        except Exception:
            old = {}
    steel = ["M_LSteel", "M_LSteelRust"]
    info = {
        "L_Bent": {"kind": "joint", "length_y": 0.0, "pivot": "centre of the bent at street level; place at every span joint (y = 0 of a span)",
                   "columns_x": [-COL_X, COL_X], "column_size_xy": [0.6, 0.45], "footing_size_xy": [1.5, 1.3],
                   "heights": {"footing_top": 0.5, "footing_bottom_buried": -0.4, "cross_girder_top": BENT_TOP,
                               "cross_girder_bottom_clearance": BENT_TOP - BENT_D, "knee_brace_low_point_at_column": BENT_TOP - BENT_D - 1.4},
                   "cross_girder_x": [-(COL_X + 0.45), COL_X + 0.45]},
        "L_Span15": {"kind": "linear", "length_y": SPAN_L, "pivot": "y = 0 end on the track-pair centreline, z = street level",
                     "ends_meet_bents_at_y": [0.0, -SPAN_L]},
        "L_Span5": {"kind": "linear", "length_y": SPAN_S, "pivot": "as L_Span15; chain 3 per bent bay or use around curves",
                    "ends_meet_bents_at_y": [0.0, -SPAN_S]},
        "L_StationPlatform30": {"kind": "linear", "length_y": PLAT_L, "pivot": "same frame as the spans it sits beside (track centreline, street level)",
                                "platform_x": [[-PLAT_OUT, -PLAT_EDGE], [PLAT_EDGE, PLAT_OUT]], "columns_x": [-PLAT_COL_X, PLAT_COL_X],
                                "columns_y": FRAMES, "canopy_posts_x": [-6.3, 6.3], "name_signs_y": list(SIGN_Y), "name_sign_x": [-4.2, 4.2],
                                "name_sign_size": [2.4, 0.45]},
        "L_StationPlatform30_Stair": {"kind": "linear", "length_y": PLAT_L, "pivot": "as L_StationPlatform30",
                                      "railing_opening_y": list(STAIR_GAP), "note": "openings on both platforms; attach L_StationStairs / L_StationHouse here"},
        "L_StationStairs": {"kind": "attachment", "length_y": 16.56, "pivot": "PLATFORM FRAME: use the transform of the L_StationPlatform30_Stair module",
                            "footprint_x": [STAIR_X0, STAIR_X1], "footprint_y": [0.0, -16.56], "entrance_y": -1.0,
                            "entrance_faces": "+Y blender (= Unreal -X): pedestrians enter at the y=0 end and climb toward -Y",
                            "top_landing_y": list(STAIR_GAP), "risers": 44, "riser_m": round(PLAT_Z / 44, 4), "tread_m": 0.254,
                            "blade_sign": "M_SignPanel, 0.55 x 2.3 m, both faces (+-Y), at x 6.32..6.95, z 3.2..5.6",
                            "other_side": "yaw 180 about the module centre (place at module local y = -30.48 rotated 180) or mirror Unreal Y"},
        "L_StationHouse": {"kind": "attachment", "length_y": 6.0, "pivot": "PLATFORM FRAME: same transform as L_StationPlatform30_Stair / L_StationStairs",
                           "footprint_x": [5.0, 6.75], "footprint_y": [-12.24, -18.24], "floor_z": PLAT_Z, "roof_z": 10.97,
                           "choice": "platform level, on the +X platform under the canopy at the stair head (Quincy/Wells style fare control); doors: stair landing side and both ends"},
        "L_TrainCar": {"kind": "vehicle", "length_y": 14.6, "pivot": "car centre, rail plane (wheel bottoms at z 0); place at z = top of rail on a track centre (x = +-1.9)",
                       "front": "-Y blender (= Unreal +X); ends identical", "width": 2.8, "height": 3.70, "floor_z": 1.12,
                       "truck_centres_y": [-5.15, 5.15], "wheelbase": 2.08, "wheel_radius": 0.356, "gauge": GAUGE,
                       "door_centres_y": [-3.75, 3.75], "third_rail_shoe_x": [-1.5, 1.5]},
    }
    info.update({
        "L_BentColumn": {"kind": "joint", "pivot": "column centre at street level; knee brace toward +X (turn +X toward the track)",
                         "footing_size_xy": [1.5, 1.3], "top_z": ZG},
        "L_BentGirder": {"kind": "joint", "pivot": "girder centre at street level", "length_x": GIRDER_UNIT, "bearing_x": [-COL_X, COL_X],
                         "z": [ZG, BENT_TOP], "scale": "X = (column spacing + 0.9) / 10.9"},
        "L_Span15J": {"kind": "linear", "length_y": SPAN_L, "pivot": "as L_Span15", "note": "junction deck: no outer walkways/handrails/third rail"},
        "L_Span5J": {"kind": "linear", "length_y": SPAN_S, "pivot": "as L_Span5", "note": "junction deck"},
        "L_PlatSide30": {"kind": "linear", "length_y": PLAT_L, "pivot": "track-pair centreline frame; the +X platform only, cantilevered",
                         "platform_x": [PLAT_EDGE, PLAT_OUT]},
        "L_PlatSide30_Stair": {"kind": "linear", "length_y": PLAT_L, "pivot": "as L_PlatSide30", "railing_opening_y": list(STAIR_GAP)},
        "L_StairBridge": {"kind": "attachment", "pivot": "x 0 at the platform's outer edge (x 6.95 of the platform frame); scale X = gap",
                          "y": list(STAIR_GAP), "floor_z": PLAT_Z},
        "L_Bumper": {"kind": "attachment", "length_y": 2.42, "pivot": "deck end on the centreline; buffers toward -Y"},
        "L_EndFence": {"kind": "attachment", "length_y": 0.4, "pivot": "deck end on the centreline; fence toward -Y"},
        "L_Truss": {"kind": "linear", "length_y": TRUSS_L, "truss_x": [-TRUSS_X, TRUSS_X], "height": TRUSS_H, "panels": TRUSS_PANELS,
                    "pivot": "span start on the centreline, street level"},
        "L_DeckSlab": {"kind": "linear", "length_y": 1.0, "pivot": "x -0.5..0.5, y 0..-1, z 0..1 (scale to the chord)"},
    })
    assets = dict(old)
    for name, d in info.items():
        entry = dict(assets.get(name, {}))
        entry.update(d)
        entry.update(STATS.get(name, {}))
        entry["file"] = f"meshes/{name}.glb"
        assets[name] = entry
    kit = {
        "generator": "Scripts/rail/blender_l_kit.py",
        "units": "metres (Unreal import: x100 cm)",
        "axes": "Blender Z up; linear modules run y 0 -> -L on the track-pair centreline x = 0. Unreal (Interchange glTF, measured 20 Oct 2026): local +Y = blender -Y (run direction), local +X = blender +X, Z = z.",
        "track": {"gauge": GAUGE, "track_centres_x": [-TRACK_X, TRACK_X], "rail_centres_x": sorted([s * g for s in (-1, 1) for g in GIRDER_X]),
                  "top_of_rail_z": TOR, "tie_top_z": TIE_TOP, "tie": {"length": TIE_L, "w": TIE_W, "h": TIE_H, "pitch": round(TIE_PITCH, 4), "long_every": 3, "long_length": 2 * LONG_TIE_X},
                  "third_rail_x": [-THIRD_X, THIRD_X], "third_rail_top_z": THIRD_TOP,
                  "longitudinal_girders": {"x": sorted([s * g for s in (-1, 1) for g in GIRDER_X]), "top_z": GIRDER_TOP, "depth": GIRDER_D, "bottom_z": GIRDER_TOP - GIRDER_D},
                  "walkways": {"centre_x": [-0.62, 0.62], "outer_x": [WALK_IN, WALK_OUT], "deck_z": TIE_TOP + GRATING_T, "handrail_x": HANDRAIL_X, "handrail_top_z": HANDRAIL_TOP},
                  "structure_width": 2 * WALK_OUT, "bent_spacing": SPAN_L},
        "station": {"platform_z": PLAT_Z, "platform_edge_x": PLAT_EDGE, "platform_outer_x": PLAT_OUT, "platform_width": PLAT_W,
                    "canopy_underside_z": CANOPY_Z, "module_length": PLAT_L, "stair_opening_y": list(STAIR_GAP)},
        "materials": sorted(MAT_DEFS),
        "assets": assets,
    }
    json.dump(kit, open(path, "w"), indent=1)
    print("wrote", path)


# ------------------------------------------------------------------ preview render
def preview():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    lib = {}

    def get(name):
        if name not in lib:
            before = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=f"{OUT}/{name}.glb")
            ob = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
            for c in list(ob.users_collection):
                c.objects.unlink(ob)
            lib[name] = ob
        return lib[name]

    def place(name, x=0.0, y=0.0, z=0.0, rz=0.0, scale=(1, 1, 1)):
        ob = get(name).copy()
        sc.collection.objects.link(ob)
        ob.location = (x, y, z)
        ob.rotation_mode = "XYZ"                       # glTF import leaves objects in quaternion mode
        ob.rotation_euler = (0, 0, rz)
        ob.scale = scale
        return ob

    if OPTS.get("scene") == "new":                     # the 20 Oct parts: asymmetric bents, station side, stair bridge, truss, end
        xl, xr = -5.0, 6.6
        gx = (xl + xr) / 2
        gs = (xr - xl + 0.9) / GIRDER_UNIT
        bent_ys = [60.0 - SPAN_L * k for k in range(10)] + [-90.0 - 45.0, -150.0]
        for yb in bent_ys:
            place("L_BentColumn", xl, yb)
            place("L_BentColumn", xr, yb, rz=math.pi)
            place("L_BentGirder", gx, yb, scale=(gs, 1, 1))
        y = 60.0
        while y > -150.0 + 0.1:
            L = min(SPAN_L, y + 150.0)
            place("L_Span15", 0, y, scale=(1, L / SPAN_L, 1))
            y -= L
        for i in range(3):
            y0 = -i * PLAT_L
            place("L_PlatSide30_Stair" if i == 0 else "L_PlatSide30", 0, y0)
            place("L_PlatSide30_Stair" if i == 2 else "L_PlatSide30", 0, y0 - PLAT_L, rz=math.pi)
        d = 2.5
        place("L_StationStairs", d, 0.0)
        place("L_StairBridge", PLAT_OUT, 0.0, scale=(d, 1, 1))
        place("L_StationHouse", 0, 0.0)
        place("L_StationStairs", 0, -3 * PLAT_L, rz=math.pi)
        place("L_Truss", 0, -90.0, scale=(1, 45.0 / TRUSS_L, 1))
        place("L_Bumper", 0, -150.0, rz=math.pi)
        place("L_EndFence", 0, -150.0, rz=math.pi)
        for k in range(3):
            place("L_TrainCar", TRACK_X, -20.0 - 14.7 * k, TOR)

    # a straight run of bents and spans (first bay as 3 short spans), a 3-module station with stairs both sides
    bents = [30.48 - SPAN_L * k for k in range(14)] if OPTS.get("scene") != "new" else []
    for k, yb in enumerate(bents):
        place("L_Bent", 0, yb)
        if k == len(bents) - 1:
            break
        if k == 0:
            for j in range(3):
                place("L_Span5", 0, yb - j * SPAN_S)
        else:
            place("L_Span15", 0, yb)
    if OPTS.get("scene") != "new":
        place("L_StationPlatform30", 0, 0.0)
        place("L_StationPlatform30_Stair", 0, -PLAT_L)
        place("L_StationPlatform30", 0, -2 * PLAT_L)
        for nm in ("L_StationStairs", "L_StationHouse"):
            place(nm, 0, -PLAT_L)
            place(nm, 0, -2 * PLAT_L, rz=math.pi)
    if OPTS.get("notrain") != "1" and OPTS.get("scene") != "new":                      # a 4-car train in the station, 2 cars arriving on the far track
        for k in range(2):                             # near track: arriving over the open spans
            place("L_TrainCar", TRACK_X, -3.0 + 14.7 * k, TOR)
        for k in range(4):                             # far track: standing in the station, heading +Y
            place("L_TrainCar", -TRACK_X, -24.0 - 14.7 * k, TOR, rz=math.pi)

    def simple(name, rgb, rough=0.8):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        b.inputs["Base Color"].default_value = (*rgb, 1)
        b.inputs["Roughness"].default_value = rough
        return m

    def slab(name, x0, x1, y0, y1, z0, z1, m):
        bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
        o = bpy.context.object
        o.scale = (x1 - x0, y1 - y0, z1 - z0)
        o.data.materials.append(m)
        o.name = name
        return o
    asph, walk, bld, bld2 = simple("asphalt", (0.07, 0.07, 0.075)), simple("sidewalk", (0.42, 0.41, 0.39)), simple("bld", (0.35, 0.3, 0.26)), simple("bld2", (0.22, 0.25, 0.3), 0.4)
    slab("road", -300, 300, -400, 200, -0.2, 0.0, asph)
    for s in (-1, 1):
        slab("walk", s * 5.6, s * 15.0, -400, 200, 0.0, 0.15, walk)
        for k in range(14):
            h = 18 + (k * 37 % 5) * 9
            y0 = 60 - k * 32
            if s > 0 and y0 > -40:
                continue
            slab("b", s * 15.5, s * 40, y0, y0 - 30, 0, h, bld if k % 2 else bld2)
    for m in bpy.data.materials:
        base = m.name.split(".")[0]
        if not m.node_tree:
            continue
        b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if b is None:
            continue
        if base == "M_Light":
            b.inputs["Emission Color"].default_value = (1.0, 0.93, 0.8, 1)
            b.inputs["Emission Strength"].default_value = 8.0
        if base == "M_DestSign":
            b.inputs["Emission Strength"].default_value = 3.0
        if base == "M_SignPanel":                      # orientation test: white "L" at the left, red square top-right
            import numpy as np
            W, H = 256, 128
            px = np.zeros((H, W, 4), np.float32)
            px[..., :] = (0.02, 0.03, 0.08, 1)
            px[16:112, 24:48] = (1, 1, 1, 1)               # rows run bottom-up in Blender images
            px[16:40, 24:96] = (1, 1, 1, 1)
            px[96:120, 216:244] = (0.9, 0.05, 0.05, 1)
            img = bpy.data.images.new("signtest", W, H)
            img.pixels = px.ravel()
            tex = m.node_tree.nodes.new("ShaderNodeTexImage")
            tex.image = img
            m.node_tree.links.new(tex.outputs["Color"], b.inputs["Base Color"])
            m.node_tree.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
            b.inputs["Emission Strength"].default_value = 1.5
        if base == "M_Glass":
            b.inputs["Transmission Weight"].default_value = 0.85
            b.inputs["Roughness"].default_value = 0.05
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 4.0
    sun.data.angle = math.radians(1.5)
    sun.rotation_euler = (math.radians(52), 0, math.radians(125))
    sc.collection.objects.link(sun)
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.55, 0.68, 0.88, 1)
    bg.inputs["Strength"].default_value = 0.9
    cams = {   # name: (location, look-at, lens)
        "main": ((30.0, 38.0, 1.7), (0.0, -14.0, 10.5), 26),
        "opendeck": ((6.0, 40.0, 10.0), (1.0, 22.0, 7.3), 22),
        "joint": ((3.6, 3.0, 4.2), (1.6, -1.0, 6.2), 18),
        "headtop": ((13.0, -38.0, 15.0), (6.0, -45.7, 8.3), 22),
        "housefront": ((3.7, -39.0, 9.9), (5.6, -46.0, 9.6), 22),
        "deck": ((6.2, -2.0, 9.2), (1.5, -12.0, 7.2), 22),
        "head": ((4.0, -34.5, 9.9), (7.6, -46.0, 9.2), 22),
        "stairs2": ((-15.0, -66.0, 2.0), (-7.0, -50.0, 6.0), 20),
        "bent": ((9.0, 5.0, 1.6), (0.0, -8.0, 6.0), 18),
        "under": ((0.5, 0.0, 1.6), (0.0, -15.0, 6.5), 16),
        "station": ((14.0, -22.0, 2.0), (4.0, -44.0, 8.5), 20),
        "train": ((5.5, -30.0, 9.8), (1.9, -45.0, 8.6), 24),
        "top": ((30.0, 25.0, 30.0), (0.0, -40.0, 6.0), 24),
        "end": ((0.0, 45.0, 7.5), (0.0, 0.0, 7.0), 28),
        "newmain": ((32.0, 40.0, 3.0), (0.0, -10.0, 8.0), 22),
        "newunder": ((0.8, 66.0, 1.6), (0.5, 30.0, 5.0), 18),
        "newend": ((12.0, -175.0, 12.0), (0.0, -145.0, 7.0), 24),
        "newtruss": ((26.0, -70.0, 4.0), (0.0, -115.0, 9.0), 22),
        "newstair": ((22.0, 12.0, 4.0), (8.0, -12.0, 6.0), 20),
    }
    loc, aim, lens = cams[OPTS.get("cam", "main")]
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = lens
    cam.location = loc
    cam.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(cam)
    sc.camera = cam
    sc.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        sc.cycles.device = "GPU"
    except Exception as e:
        print("GPU not available, CPU render:", e)
    sc.cycles.samples = int(OPTS.get("samples", 48))
    sc.cycles.use_denoising = True
    rx, ry = (int(v) for v in OPTS.get("res", "1600x900").split("x"))
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    sc.view_settings.view_transform = "AgX"
    sc.render.filepath = OPTS.get("out", RAIL + "/preview.png")
    bpy.ops.render.render(write_still=True)
    print("rendered", sc.render.filepath)


# ------------------------------------------------------------------ main
JOBS = {
    "bent": build_bent,
    "span": lambda: (build_span("L_Span15", SPAN_L), build_span("L_Span5", SPAN_S)),
    "column": build_bent_column,
    "girder": build_bent_girder,
    "jspan": lambda: (build_span("L_Span15J", SPAN_L, True), build_span("L_Span5J", SPAN_S, True)),
    "platside": lambda: (build_plat_side("L_PlatSide30", False), build_plat_side("L_PlatSide30_Stair", True)),
    "bridge": build_stair_bridge,
    "bumper": build_bumper,
    "fence": build_end_fence,
    "truss": build_truss,
    "slab": build_deck_slab,
    "platform": lambda: (build_platform("L_StationPlatform30", False), build_platform("L_StationPlatform30_Stair", True)),
    "stairs": build_stairs,
    "house": build_house,
    "train": build_train,
}
todo = [j for j in JOBS if not JOBS_ASKED or j in JOBS_ASKED or "all" in JOBS_ASKED]
if JOBS_ASKED and all(j == "preview" for j in JOBS_ASKED):
    todo = []
for job in todo:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    MATS.clear()
    JOBS[job]()
if todo:
    write_kit_json()
if "preview" in JOBS_ASKED:
    preview()
print("ALL DONE")
