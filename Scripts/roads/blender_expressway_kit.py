"""Sky City expressway kit, modelled in Blender (headless) from the offline layout, exported as GLB.

Reads Saved/Expressway/expressway_layout.json (Scripts/roads/expressway_layout.py) and builds every piece at its real
place, so curved decks, ramps and odd bents come out exact instead of bent modules:
  Austin, Interstate 35 upper decks (TxDOT, 1970s; references SourceArt/Reference/Expressways):
    decks       two decks, one per direction, 12.95 m out to out: 2 x 3.66 m lanes, 3.05 m outside / 1.52 m inside
                shoulders, a 0.19 m slab on 7 prestressed I-girders (TxDOT Type C, 40 in, up to 32 m spans; Type IV,
                54 in, up to 41.5 m; steel plate girders beyond), concrete end and mid-span diaphragms, an expansion joint
                at every bent (simple spans, the leaking joints that stained the old decks)
    rails       the open concrete post-and-beam rail seen on the decks: 0.30 m curb, posts every 3.05 m, a 0.30 x 0.22 m
                top beam (0.84 m), its outside face flush with the slab edge as one pale fascia band
    bents       one rectangular column (1.83 x 1.22 m) per deck under a hammerhead cap as wide as the deck (1.68 m deep at
                the column, 1.07 m at the tips, 1.52 m thick), neoprene bearing pads, a black drain pipe down the column;
                straddle bents (two square columns, one long cap) where no column spot is clear below
    ramps       retained-earth fill between precast-panel walls (1.52 m panels) with a coping, a safety-shape barrier on
                top, a concrete median barrier, the abutment and its bridge seat where the spans begin
    lights      40 ft (12.2 m) galvanized davit poles on each deck's inside rail with a 12 ft arm and a cobra-head
    signs       galvanized four-chord box-truss sign bridges at bents, lattice end towers, catwalk and sign lights,
                two green guide signs each (SourceArt/Expressway/textures/T_Expwy_SignAtlas.png)
  Chicago, Wacker Canal Expressway (IDOT viaduct): one deck, steel plate girders, multi-column bents, solid parapets
    with a drip groove, davit poles on the parapets, brown steel frame sign bridges.
Weathering: every concrete face gets a second UV set ("Grime": u along the element, v = 0 at its bottom, 1 at its top)
for T_Expwy_Grime.png - streaks from the top, a dirt band at the bottom - multiplied over the concrete in Unreal.

Frames: plan metres (x east, y north, z up). Each exported mesh is built round its own origin (ox, oy) in the plan, written
as Blender (y - oy, -(x - ox), z): Unreal's glTF import keeps Blender X and turns -Y into +Y (centimetres), so the mesh
lands in Unreal axes (X = plan y, Y = plan x) when its actor stands at (oy*100, ox*100, 0) with no rotation.
Output: SourceArt/Expressway/meshes/XW_<ROAD>_<piece>.glb (one mesh per file) + SourceArt/Expressway/kit.json (origins,
triangle counts). Material slot names (M_XW_*) are mapped to Unreal materials by Scripts/roads/build_expressway_ue.py.
Run: /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/roads/blender_expressway_kit.py -- [i35] [wacker]
(20 Oct 2026, agent highway-capitol)
"""
import json, math, os, sys, time
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
LAY = json.load(open(ROOT + "/Saved/Expressway/expressway_layout.json"))
ATLAS = json.load(open(ROOT + "/SourceArt/Expressway/textures/sign_atlas.json"))
OUT = ROOT + "/SourceArt/Expressway/meshes"
os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROADS = [a for a in ARGS if a in LAY["roads"]] or list(LAY["roads"])
KITJ = ROOT + "/SourceArt/Expressway/kit.json"
KIT = json.load(open(KITJ)) if os.path.exists(KITJ) else {"meshes": {}}
UP = Vector((0, 0, 1))


# ------------------------------------------------------------------------------------------------ materials
MATS = {}
MAT_COLORS = {  # viewport/preview colours only; Unreal maps the slot names to its own materials
    "M_XW_Asphalt": (0.06, 0.06, 0.065), "M_XW_Concrete": (0.55, 0.53, 0.49), "M_XW_ConcreteDeck": (0.5, 0.49, 0.46),
    "M_XW_MSE": (0.58, 0.56, 0.52), "M_XW_PaintWhite": (0.9, 0.9, 0.88), "M_XW_PaintYellow": (0.85, 0.62, 0.05),
    "M_XW_JointSteel": (0.12, 0.12, 0.12), "M_XW_Galv": (0.6, 0.61, 0.62), "M_XW_WeatheringSteel": (0.25, 0.12, 0.06),
    "M_XW_PaintedSteel": (0.3, 0.12, 0.08), "M_XW_Lens": (1.0, 0.8, 0.5), "M_XW_SignFace": (0.0, 0.4, 0.25),
    "M_XW_SignBack": (0.55, 0.56, 0.57), "M_XW_Pipe": (0.03, 0.03, 0.03), "M_XW_Bearing": (0.05, 0.05, 0.05),
    "M_XW_Grating": (0.35, 0.35, 0.36),
}


def mat(name):
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*MAT_COLORS.get(name, (0.5, 0.5, 0.5)), 1)
    MATS[name] = m
    return m


# ------------------------------------------------------------------------------------------------ builder
class Builder:
    """One mesh: faces in plan coordinates (converted to the mesh's local Blender frame), material slots, two UV sets."""

    def __init__(self, name, origin):
        self.name = name
        self.ox, self.oy = origin
        self.bm = bmesh.new()
        self.uv0 = self.bm.loops.layers.uv.new("UVMap")
        self.uv1 = self.bm.loops.layers.uv.new("Grime")
        self.mats = []

    def mi(self, name):
        if name not in self.mats:
            self.mats.append(name)
        return self.mats.index(name)

    def local(self, p):
        return Vector((p[1] - self.oy, -(p[0] - self.ox), p[2]))

    def face(self, pts, m, grime=None, uvs=None, smooth=False):
        """pts: plan (x, y, z). grime: (zmin, zmax) for the Grime UVs (None: mid-grey v 0.5). uvs: explicit UV0."""
        if len(pts) < 3:
            return None
        P = [self.local(p) for p in pts]
        n = (P[1] - P[0]).cross(P[2] - P[0])
        if len(pts) > 3:
            n = Vector((0, 0, 0))
            for i in range(len(P)):
                a, b = P[i], P[(i + 1) % len(P)]
                n += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
        if n.length < 1e-9:
            return None
        n.normalize()
        try:
            f = self.bm.faces.new([self.bm.verts.new(v) for v in P])
        except ValueError:
            return None
        f.material_index = self.mi(m)
        f.smooth = smooth
        # UV0: box projection in metres (plan axes); UV1: along / height for the grime texture
        hx = UP.cross(n)
        if hx.length < 1e-6:
            hx = Vector((1, 0, 0))
        hx.normalize()
        for k, (l, v) in enumerate(zip(f.loops, P)):
            if uvs:
                l[self.uv0].uv = uvs[k]
            elif abs(n.z) > 0.7:
                l[self.uv0].uv = (v.x, v.y)
            elif abs(n.x) > abs(n.y):
                l[self.uv0].uv = (v.y, v.z)
            else:
                l[self.uv0].uv = (v.x, v.z)
            if grime:
                z0, z1 = grime
                gv = max(0.0, min(1.0, (v.z - z0) / max(0.05, z1 - z0)))
            else:
                gv = 0.5
            gu = (v.dot(hx) if abs(n.z) <= 0.7 else v.x) / 6.0
            l[self.uv1].uv = (gu, gv)
        return f

    def quad_strip(self, A, B, m, grime=None, smooth=False):
        """Faces between two rows of points (each row along the length)."""
        for i in range(len(A) - 1):
            self.face([A[i], B[i], B[i + 1], A[i + 1]], m, grime, smooth=smooth)

    def sweep(self, frames, profile, mats, closed=True, caps=(True, True), grime=None, smooth=False):
        """frames: [(c(x,y), t, n, z)], profile(k) -> [(u, v)] CCW (u along n, v up) or a fixed list. mats: one name or
        one per edge. grime: (zmin, zmax) fixed, 'local' (per profile: its own v range at each station) or None."""
        rows = []
        for k, (c, t, n, z) in enumerate(frames):
            prof = profile(k) if callable(profile) else profile
            rows.append([(c[0] + n[0] * u, c[1] + n[1] * u, z + v) for u, v in prof])
        npts = len(rows[0])
        edges = range(npts if closed else npts - 1)
        for e in edges:
            m = mats if isinstance(mats, str) else mats[e]
            if m is None:
                continue
            i, j = e, (e + 1) % npts
            for k in range(len(rows) - 1):
                g = grime
                if grime == "local":
                    zs = [p[2] for p in rows[k]]
                    g = (min(zs), max(zs))
                self.face([rows[k][i], rows[k][j], rows[k + 1][j], rows[k + 1][i]], m, g, smooth=smooth)
        if closed:
            m0 = mats if isinstance(mats, str) else next(x for x in mats if x)
            g = grime if grime != "local" else None
            if caps[1]:
                self.face(rows[-1], m0, g if g else (min(p[2] for p in rows[-1]), max(p[2] for p in rows[-1])))
            if caps[0]:
                self.face(rows[0][::-1], m0, g if g else (min(p[2] for p in rows[0]), max(p[2] for p in rows[0])))

    def prism(self, outline, O, A, B, e0, e1, m, grime="auto"):
        """Outline (a, b) CCW in the plane spanned by A (unit) and B (unit), extruded along E = A x B from e0 to e1."""
        A = Vector(A); B = Vector(B); E = A.cross(B)
        O = Vector(O)
        P0 = [O + A * a + B * b + E * e0 for a, b in outline]
        P1 = [O + A * a + B * b + E * e1 for a, b in outline]
        zs = [p.z for p in P0 + P1]
        g = (min(zs), max(zs)) if grime == "auto" else grime
        self.face([tuple(p) for p in P1], m, g)
        self.face([tuple(p) for p in P0[::-1]], m, g)
        n = len(outline)
        for i in range(n):
            j = (i + 1) % n
            self.face([tuple(P0[i]), tuple(P0[j]), tuple(P1[j]), tuple(P1[i])], m, g)

    def vbox(self, c, t, n, along, across, z0, z1, m, grime="auto", chamfer=0.0):
        """Upright box: centre c (x, y), long axis t, from z0 to z1 (an optional corner chamfer)."""
        if t[0] * n[1] - t[1] * n[0] < 0:          # keep (t, n, up) right-handed so faces point out
            n = (-n[0], -n[1])
        a, b = along / 2, across / 2
        if chamfer > 0:
            ch = min(chamfer, a * 0.4, b * 0.4)
            pts2 = [(a, -b + ch), (a, b - ch), (a - ch, b), (-a + ch, b), (-a, b - ch), (-a, -b + ch), (-a + ch, -b), (a - ch, -b)]
        else:
            pts2 = [(a, -b), (a, b), (-a, b), (-a, -b)]
        # (along t, across n) is CCW when t x n = up, which holds for n = left(t)
        self.prism(pts2, (c[0], c[1], 0.0), (t[0], t[1], 0.0), (n[0], n[1], 0.0), z0, z1, m, grime)

    def tube(self, path, radii, m, sides=8, cap=True, smooth=True):
        rings = []
        for i, p in enumerate(path):
            p = Vector(p)
            a = Vector(path[max(0, i - 1)]); b = Vector(path[min(len(path) - 1, i + 1)])
            tt = (b - a).normalized()
            up = UP if abs(tt.z) < 0.95 else Vector((1, 0, 0))
            x = tt.cross(up).normalized()
            y = tt.cross(x).normalized()
            rings.append([tuple(p + (x * math.cos(2 * math.pi * k / sides) + y * math.sin(2 * math.pi * k / sides)) * radii[i]) for k in range(sides)])
        zs = [q[2] for r in rings for q in r]
        g = (min(zs), max(zs))
        for r0, r1 in zip(rings, rings[1:]):
            for k in range(sides):
                kk = (k + 1) % sides
                self.face([r0[k], r0[kk], r1[kk], r1[k]], m, g, smooth=smooth)   # outward (ring order x -> y is +t)
        if cap:
            self.face(rings[-1], m, g)
            self.face(rings[0][::-1], m, g)

    def tris(self):
        return sum(len(f.verts) - 2 for f in self.bm.faces)

    def finish(self):
        me = bpy.data.meshes.new(self.name)
        bmesh.ops.triangulate(self.bm, faces=self.bm.faces[:], quad_method="BEAUTY", ngon_method="EAR_CLIP")
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(mat(m))
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(ob)
        return ob


def export(B, kind, extra=None):
    tris = B.tris()
    name = B.name
    ob = B.finish()
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.gltf(filepath=f"{OUT}/{name}.glb", export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_materials="EXPORT", export_image_format="NONE")
    KIT["meshes"][name] = dict({"file": f"SourceArt/Expressway/meshes/{name}.glb", "origin_plan": [B.ox, B.oy],
                                "tris": tris, "kind": kind}, **(extra or {}))
    bpy.data.objects.remove(ob)
    print("exported", name, tris, "tris")


# ------------------------------------------------------------------------------------------------ road frames
class Road:
    def __init__(self, lay):
        self.lay = lay
        self.st = LAY["styles"][lay["style"]]
        c = lay["centre"]
        self.X = [p[0] for p in c]; self.Y = [p[1] for p in c]; self.Z = [p[2] for p in c]; self.S = [p[3] for p in c]
        self.L = self.S[-1]

    def idx(self, s):
        lo, hi = 0, len(self.S) - 2
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.S[mid] <= s:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def frame(self, s):
        s = max(0.0, min(self.L, s))
        i = self.idx(s)
        seg = (self.S[i + 1] - self.S[i]) or 1e-9
        f = (s - self.S[i]) / seg
        x = self.X[i] + (self.X[i + 1] - self.X[i]) * f
        y = self.Y[i] + (self.Y[i + 1] - self.Y[i]) * f
        z = self.Z[i] + (self.Z[i + 1] - self.Z[i]) * f
        # tangent from a +-2 m window for smoothness
        i0 = self.idx(max(0.0, s - 2.0)); i1 = min(len(self.S) - 1, self.idx(min(self.L, s + 2.0)) + 1)
        tx, ty = self.X[i1] - self.X[i0], self.Y[i1] - self.Y[i0]
        L = math.hypot(tx, ty) or 1.0
        t = (tx / L, ty / L)
        n = (-t[1], t[0])
        return (x, y), t, n, z

    def frames(self, s0, s1, step, off=0.0):
        k = max(1, int(math.ceil((s1 - s0) / step)))
        out = []
        for i in range(k + 1):
            c, t, n, z = self.frame(s0 + (s1 - s0) * i / k)
            out.append(((c[0] + n[0] * off, c[1] + n[1] * off), t, n, z))
        return out

    def point(self, s, u, v):
        c, t, n, z = self.frame(s)
        return (c[0] + n[0] * u, c[1] + n[1] * u, z + v)


# ------------------------------------------------------------------------------------------------ profiles
def i_profile(kind, d, haunch):
    """TxDOT prestressed I-beam outlines (v from the beam bottom), CCW; steel plate girder as a thin I."""
    if kind == "txdot_iv":
        bf, tb, tb2, wh, tt1, tt2, tf = 0.330, 0.203, 0.432, 0.1015, 1.016, 1.168, 0.254
        H = 1.372
    elif kind == "txdot_c":
        bf, tb, tb2, wh, tt1, tt2, tf = 0.2795, 0.178, 0.343, 0.089, 0.812, 0.876, 0.203
        H = 1.016
    else:   # steel plate girder
        H = d
        bf, tb, tb2, wh, tt1, tt2, tf = 0.25, 0.05, 0.05, 0.008, H - 0.04, H - 0.04, 0.225
    H2 = H + haunch
    tt1 += 0; tt2 += 0
    return [(-bf, 0), (bf, 0), (bf, tb), (wh, tb2), (wh, tt1), (tf, tt2), (tf, H2), (-tf, H2), (-tf, tt2), (-wh, tt1), (-wh, tb2), (-bf, tb)], H


def nj_barrier(toe_u, side, base_v=0.0, back_u=None):
    """New Jersey safety shape (TxDOT T501-like, 0.81 m), traffic face at toe_u facing away from `side` (+1: barrier
    on the +u side of the road). Returns a CCW outline."""
    s = side
    pts = [(0.0, 0.0), (0.0, 0.076), (0.152, 0.254), (0.229, 0.813), (0.381, 0.813), (0.381 if back_u is None else back_u, 0.0)]
    out = [(toe_u + s * a, base_v + b) for a, b in pts]
    if s < 0:
        out = out[::-1]
    # make CCW: for s = +1 the order toe-bottom -> up the face -> top -> down the back is clockwise; reverse it
    return out[::-1] if s > 0 else out


def ccw(poly):
    a = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
    return poly if a > 0 else poly[::-1]


# ------------------------------------------------------------------------------------------------ Austin pieces
JOINT = 0.05


def tx_deck_span(B, R, k, sp, dir_plus):
    """One simple span of one deck: slab with curbs (fascia), road surface, open rail, markings, I-girders, diaphragms,
    the joint plate at its far end."""
    st = R.st
    dc = st["decks"][k]
    W = st["deck_w"]
    hw = W / 2
    slab = st["slab"]
    curb_w, curb_h = st["rail_w"] + st["fascia"], 0.30
    s0, s1 = sp["s0"] + JOINT / 2, sp["s1"] - JOINT / 2
    fr = R.frames(s0, s1, 2.5, dc)
    # slab + curbs: outer faces, curb tops, curb inner faces, soffit (concrete); road surface (asphalt)
    prof = [(hw, -slab), (hw, curb_h), (hw - curb_w, curb_h), (hw - curb_w, 0.0), (-hw + curb_w, 0.0),
            (-hw + curb_w, curb_h), (-hw, curb_h), (-hw, -slab)]
    mats = ["M_XW_Concrete", "M_XW_Concrete", "M_XW_Concrete", "M_XW_Asphalt", "M_XW_Concrete", "M_XW_Concrete",
            "M_XW_Concrete", "M_XW_Concrete"]
    B.sweep(fr, prof, mats, closed=True, caps=(True, True), grime="local")
    # open rail: posts every 3.05 m on each curb, continuous top beam
    for side in (+1, -1):
        uc = side * (hw - curb_w / 2 - 0.02)
        beam = ccw([(uc - 0.15, 0.62), (uc + 0.15, 0.62), (uc + 0.15, 0.80), (uc + 0.11, 0.84), (uc - 0.11, 0.84), (uc - 0.15, 0.80)])
        B.sweep(fr, beam, "M_XW_Concrete", closed=True, caps=(True, True), grime=None)
        sv = s0 + 0.4
        while sv < s1 - 0.3:
            c, t, n, z = R.frame(sv)
            cc = (c[0] + n[0] * (dc + uc), c[1] + n[1] * (dc + uc))
            B.vbox(cc, t, n, 0.25, 0.28, z + curb_h - 0.01, z + 0.63, "M_XW_Concrete", grime=(z - slab, z + 0.84))
            sv += 3.05
    # markings (thin strips 8 mm up): inside edge yellow, lane line white dashed (10 ft / 30 ft), outside edge white
    inner = -1 if dir_plus else +1          # + traffic drives on the deck right of +s: its inside edge is on +u...
    inner = +1 if dc < 0 else -1            # the inside (median) edge of this deck faces the road centre
    e_in = inner * (hw - curb_w - st["shoulder_in"])
    e_out = -inner * (hw - curb_w - st["shoulder_out"])
    lane_mid = (e_in + e_out) / 2
    for u, mname, dash in ((e_in - inner * 0.1, "M_XW_PaintYellow", None), (e_out + inner * 0.1, "M_XW_PaintWhite", None),
                           (lane_mid, "M_XW_PaintWhite", (3.05, 9.14))):
        segs = [(s0, s1)] if not dash else []
        if dash:
            sv = math.floor(s0 / 12.19) * 12.19
            while sv < s1:
                a, b = max(s0, sv), min(s1, sv + dash[0])
                if b - a > 0.3:
                    segs.append((a, b))
                sv += 12.19
        for a, b in segs:
            f2 = R.frames(a, b, 2.5, dc)
            B.sweep(f2, [(u + 0.075, 0.008), (u - 0.075, 0.008)], mname, closed=False, caps=(False, False))
    # girders: straight chords per 5 m (they follow the profile), on bearings 0.2 m in from the bent lines
    prof_i, H = i_profile(sp["girder"], sp.get("girder_d", st["girder_d"]), st["haunch"])
    n_g = st["girders_per_deck"]
    over = 0.95 if W > 10 else 0.8
    spacing = (W - 2 * over) / (n_g - 1)
    g0, g1 = sp["s0"] + 0.2, sp["s1"] - 0.2
    frg = R.frames(g0, g1, 5.0, dc)
    v_bot = -slab - st["haunch"] - H
    gm = "M_XW_Concrete" if sp["girder"].startswith("txdot") else "M_XW_WeatheringSteel"
    for j in range(n_g):
        ug = -hw + over + j * spacing
        pr = [(ug + a, v_bot + b) for a, b in prof_i]
        B.sweep(frg, pr, gm, closed=True, caps=(True, True), grime=(None if not gm.endswith("Concrete") else "local"))
    # diaphragms between girders: at both ends and mid-span (concrete), cross-frames on steel
    for sv in (g0 + 0.3, (g0 + g1) / 2, g1 - 0.3):
        c, t, n, z = R.frame(sv)
        for j in range(n_g - 1):
            ua = -hw + over + j * spacing + 0.12
            ub = -hw + over + (j + 1) * spacing - 0.12
            um = (ua + ub) / 2
            cc = (c[0] + n[0] * (dc + um), c[1] + n[1] * (dc + um))
            zt = z - slab - 0.05
            B.vbox(cc, t, n, 0.2, ub - ua, zt - H * 0.75, zt, gm if gm.endswith("Concrete") else "M_XW_WeatheringSteel")
    # joint plate across the far end (steel), at road level
    c, t, n, z = R.frame(sp["s1"])
    a = [(c[0] + n[0] * (dc + u) - t[0] * 0.09, c[1] + n[1] * (dc + u) - t[1] * 0.09, z + 0.004) for u in (hw - curb_w, -hw + curb_w)]
    b = [(c[0] + n[0] * (dc + u) + t[0] * 0.09, c[1] + n[1] * (dc + u) + t[1] * 0.09, z + 0.004) for u in (hw - curb_w, -hw + curb_w)]
    B.face([a[0], a[1], b[1], b[0]] if True else None, "M_XW_JointSteel")
    return H


def seat_z(R, s, H):
    return R.frame(s)[3] - R.st["slab"] - R.st["haunch"] - H - 0.05


def span_H(sp, st):
    return i_profile(sp["girder"], sp.get("girder_d", st["girder_d"]), 0)[1]


def tx_bent(B, R, b, Hmax, Hs):
    """A bent: one hammerhead (cap + column + drain) per deck, or a straddle bent under both."""
    st = R.st
    s = b["s"]
    c, t, n, z = R.frame(s)
    cap_top = z - st["slab"] - st["haunch"] - Hmax - 0.05
    W = st["deck_w"]
    if b["type"] == "hammer":
        for k, dc in enumerate(st["decks"]):
            off = b["offs"][k]
            Lc = W - 0.1
            ac = off - dc                      # column position within the cap
            cw = st["col"][0] / 2 + 0.45
            d, dt = st["cap_d"], st["cap_d_tip"]
            outline = ccw([(-Lc / 2, -dt), (ac - cw, -d), (ac + cw, -d), (Lc / 2, -dt), (Lc / 2, 0.0), (-Lc / 2, 0.0)])
            O = (c[0] + n[0] * dc, c[1] + n[1] * dc, cap_top)
            B.prism(outline, O, (n[0], n[1], 0), (0, 0, 1), -st["cap_w"] / 2, st["cap_w"] / 2, "M_XW_Concrete")
            # column
            cc = (c[0] + n[0] * off, c[1] + n[1] * off)
            B.vbox(cc, t, n, st["col"][1], st["col"][0], -0.5, cap_top - d + 0.02, "M_XW_Concrete", grime=(0.0, cap_top - d), chamfer=0.06)
            # drain pipe down the column face (the +t side), with a short kick-out at the bottom
            pc = (cc[0] + t[0] * (st["col"][1] / 2 + 0.12) + n[0] * 0.5, cc[1] + t[1] * (st["col"][1] / 2 + 0.12) + n[1] * 0.5)
            B.tube([(pc[0], pc[1], cap_top - 0.1), (pc[0], pc[1], 0.5), (pc[0] + t[0] * 0.4, pc[1] + t[1] * 0.4, 0.25)], [0.1, 0.1, 0.1], "M_XW_Pipe", sides=8)
            # bearing pads (+ pedestals under the shallower girders) on both sides of the bent
            n_g = st["girders_per_deck"]
            over = 0.95
            spacing = (W - 2 * over) / (n_g - 1)
            for side, Hside in ((-1, Hs[0]), (+1, Hs[1])):
                if Hside is None:
                    continue
                for j in range(n_g):
                    ug = dc - W / 2 + over + j * spacing
                    q = (c[0] + n[0] * ug + t[0] * side * 0.45, c[1] + n[1] * ug + t[1] * side * 0.45)
                    top = z - st["slab"] - st["haunch"] - Hside
                    B.vbox(q, t, n, 0.36, 0.6, cap_top, top, "M_XW_Bearing" if top - cap_top < 0.12 else "M_XW_Concrete")
    else:
        o0, o1 = min(b["offs"]), max(b["offs"])
        steel = b.get("cap") == "steel_box"
        depth = 1.8                          # keeps 5.4 m over the at-grade lanes below (TxDOT min 5.03 m)
        width = 1.6 if steel else 1.83
        outline = ccw([(o0 - 0.8, -depth), (o1 + 0.8, -depth), (o1 + 0.8, 0.0), (o0 - 0.8, 0.0)])
        O = (c[0], c[1], cap_top)
        B.prism(outline, O, (n[0], n[1], 0), (0, 0, 1), -width / 2, width / 2, "M_XW_WeatheringSteel" if steel else "M_XW_Concrete")
        for o in b["offs"]:
            cc = (c[0] + n[0] * o, c[1] + n[1] * o)
            B.vbox(cc, t, n, st["straddle_col"][1], st["straddle_col"][0], -0.5, cap_top - depth + 0.02, "M_XW_Concrete",
                   grime=(0.0, cap_top - depth), chamfer=0.06)
        n_g = st["girders_per_deck"]
        over = 0.95
        spacing = (W - 2 * over) / (n_g - 1)
        for dc in st["decks"]:
            for side, Hside in ((-1, Hs[0]), (+1, Hs[1])):
                if Hside is None:
                    continue
                for j in range(n_g):
                    ug = dc - W / 2 + over + j * spacing
                    q = (c[0] + n[0] * ug + t[0] * side * 0.45, c[1] + n[1] * ug + t[1] * side * 0.45)
                    top = z - st["slab"] - st["haunch"] - Hside
                    B.vbox(q, t, n, 0.36, 0.6, cap_top, top, "M_XW_Bearing" if top - cap_top < 0.12 else "M_XW_Concrete")


def tx_light(B, R, L):
    """40 ft davit pole on the inside rail: base plate on the top beam, tapered octagonal shaft, curved arm, cobra head."""
    st = R.st
    c, t, n, z = R.frame(L["s"])
    p = L["p"]
    zb = z + st["rail_h"]
    top = z + st["light_h"]
    arm = L["arm"]
    B.vbox((p[0], p[1]), t, n, 0.42, 0.42, zb - 0.02, zb + 0.03, "M_XW_Galv")
    B.tube([(p[0], p[1], zb), (p[0], p[1], top - 0.8)], [0.13, 0.085], "M_XW_Galv", sides=8)
    ax, ay = n[0] * arm, n[1] * arm
    reach = st["light_arm"]
    path = [(p[0], p[1], top - 0.9), (p[0] + ax * 0.3, p[1] + ay * 0.3, top - 0.2), (p[0] + ax * 1.0, p[1] + ay * 1.0, top + 0.05),
            (p[0] + ax * reach, p[1] + ay * reach, top + 0.12)]
    B.tube(path, [0.075, 0.06, 0.055, 0.05], "M_XW_Galv", sides=8, cap=False)
    hx = (p[0] + ax * (reach + 0.35), p[1] + ay * (reach + 0.35))
    nn = (ay, -ax)
    B.vbox(hx, (ax, ay), nn, 0.85, 0.42, top - 0.05, top + 0.22, "M_XW_Galv", chamfer=0.1)
    B.vbox(hx, (ax, ay), nn, 0.6, 0.32, top - 0.16, top - 0.04, "M_XW_Lens")


def sign_uv(sid):
    cell = ATLAS["cells"].get(sid)
    if not cell:
        return [(0, 0), (0.01, 0), (0.01, 0.01), (0, 0.01)]
    c, r = cell["col"], cell["row"]
    u0, u1 = c * 0.5, c * 0.5 + 0.5
    v1 = 1.0 - r / 8.0
    v0 = 1.0 - (r + 1) / 8.0
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def sign_bridge(B, R, g, style="tx"):
    """Overhead sign structure across one deck at a bent: box truss (four chords + lacing) on lattice end towers standing
    on brackets off the fascia, a catwalk, sign lights, two guide signs hung on the traffic side."""
    st = R.st
    c, t, n, z = R.frame(g["s"] + 1.6 * (1 if g["face"] < 0 else -1))
    dc = st["decks"][g["deck"]] if st["twin"] else 0.0
    W = st["deck_w"]
    face = g["face"]
    fv = (t[0] * face, t[1] * face)        # direction the sign faces (towards the traffic)
    mat_s = "M_XW_Galv" if style == "tx" else "M_XW_PaintedSteel"
    zb = z + 6.0                            # bottom chord (sign bottom clears 5.2 m)
    hgt, dep = 1.5, 1.2
    ends = (dc - W / 2 - 0.55, dc + W / 2 + 0.55)
    def P(u, a, h):                         # u lateral, a along the facing direction, h above the deck
        return (c[0] + n[0] * u + fv[0] * a, c[1] + n[1] * u + fv[1] * a, z + h)
    # chords
    for a in (-dep / 2, dep / 2):
        for h in (6.0, 6.0 + hgt):
            B.tube([P(ends[0], a, h), P(ends[1], a, h)], [0.06, 0.06], mat_s, sides=6)
    # lacing: zig-zag on the 4 faces
    nseg = int((ends[1] - ends[0]) / 1.4)
    for i in range(nseg):
        u0 = ends[0] + (ends[1] - ends[0]) * i / nseg
        u1 = ends[0] + (ends[1] - ends[0]) * (i + 1) / nseg
        for a in (-dep / 2, dep / 2):
            B.tube([P(u0, a, 6.0), P(u1, a, 6.0 + hgt)] if i % 2 == 0 else [P(u0, a, 6.0 + hgt), P(u1, a, 6.0)], [0.03, 0.03], mat_s, sides=4, cap=False)
        for h in (6.0, 6.0 + hgt):
            B.tube([P(u0, -dep / 2, h), P(u1, dep / 2, h)] if i % 2 == 0 else [P(u0, dep / 2, h), P(u1, -dep / 2, h)], [0.03, 0.03], mat_s, sides=4, cap=False)
    # end towers: 4-chord lattice columns from the bracket below deck level to the truss top
    for ue in ends:
        for a in (-dep / 2, dep / 2):
            for du in (-0.3, 0.3):
                B.tube([P(ue + du, a, -0.6), P(ue + du, a, 6.0 + hgt + 0.1)], [0.055, 0.055], mat_s, sides=6)
        for h in [x * 0.9 for x in range(0, 9)]:
            B.tube([P(ue - 0.3, -dep / 2, h - 0.6), P(ue + 0.3, dep / 2, h + 0.3)], [0.025, 0.025], mat_s, sides=4, cap=False)
        side = 1 if ue > dc else -1
        cc = P(ue - side * 0.3, 0, 0)
        B.vbox((cc[0], cc[1]), (n[0], n[1]), (-fv[0], -fv[1]), 1.1, dep + 0.3, z - 0.75, z - 0.45, "M_XW_Concrete")
    # signs: 5.4 x 2.7 m on the traffic side, sign 0 on the driver's left
    sw, sh = 5.4, 2.7
    drv_left = 1 if face < 0 else -1        # traffic moves along -face*t; its left is n*(+1) when moving +t
    slots = [dc + drv_left * 3.0, dc - drv_left * 3.0]
    if not st["twin"]:                       # one two-way deck: the signs hang over this direction's half only
        sw, sh = 4.2, 2.1
        half = -drv_left * W / 4             # the driver's right-hand half of the deck
        slots = [half + drv_left * 2.25, half - drv_left * 2.25]
    a_face = dep / 2 + 0.45
    for sid, us in zip(g.get("signs", [])[:2], slots):
        hm = 6.0 + hgt / 2
        # front: texture left on the driver's left, facing the traffic
        q = [P(us + drv_left * sw / 2, a_face, hm - sh / 2), P(us - drv_left * sw / 2, a_face, hm - sh / 2),
             P(us - drv_left * sw / 2, a_face, hm + sh / 2), P(us + drv_left * sw / 2, a_face, hm + sh / 2)]
        uv = sign_uv(sid)
        B.face(q, "M_XW_SignFace", uvs=uv)
        # back and edges: a thin aluminium box behind the face
        cc = P(us, a_face - 0.05, 0)
        B.vbox((cc[0], cc[1]), (fv[0], fv[1]), (n[0], n[1]), 0.09, sw, z + hm - sh / 2, z + hm + sh / 2 - 0.0, "M_XW_SignBack", grime=None)
        for k in (-1.6, 1.6):                # hangers to the chords
            B.tube([P(us + k, a_face - 0.1, hm + sh / 2 + 0.15), P(us + k, dep / 2, 6.0 + hgt), ], [0.035, 0.035], mat_s, sides=4, cap=False)
            B.tube([P(us + k, a_face - 0.1, hm - sh / 2 + 0.1), P(us + k, dep / 2, 6.0)], [0.035, 0.035], mat_s, sides=4, cap=False)
        if style == "tx":                    # catwalk + two sign lights below each sign (period TxDOT detail)
            cw = [P(us - 3.0, a_face + 0.1, hm - sh / 2 - 0.25), P(us + 3.0, a_face + 0.1, hm - sh / 2 - 0.25),
                  P(us + 3.0, a_face - 0.75, hm - sh / 2 - 0.25), P(us - 3.0, a_face - 0.75, hm - sh / 2 - 0.25)]
            B.face(ccw_face(cw), "M_XW_Grating")
            B.face(ccw_face(cw)[::-1], "M_XW_Grating")
            for k in (-1.4, 1.4):
                lp = P(us + k, a_face + 0.55, hm - sh / 2 - 0.35)
                B.vbox((lp[0], lp[1]), (fv[0], fv[1]), (n[0], n[1]), 0.35, 0.5, lp[2], lp[2] + 0.18, "M_XW_Galv")


def ccw_face(q):
    """Order a horizontal quad so its normal points up."""
    a = sum(q[i][0] * q[(i + 1) % 4][1] - q[(i + 1) % 4][0] * q[i][1] for i in range(4))
    return q if a > 0 else q[::-1]


def fill_end(B, R, s_a, s_b, abut_s, abut_dir, Hab):
    """Ramp on retained fill from s_a to s_b: precast panel walls with coping, safety-shape barriers, both roadways with a
    concrete median barrier, markings; the abutment and bridge seat at abut_s, facing abut_dir (+1: the bridge is at s > abut_s)."""
    st = R.st
    TW = st["total_w"]
    hw = TW / 2
    fr = R.frames(s_a, s_b, 2.0)
    zmax = max(f[3] for f in fr)
    # walls: from below grade to the coping, each side; coping band proud by 8 cm
    for side in (+1, -1):
        def wall(k, side=side):
            z = fr[k][3]
            u = side * hw
            pts = [(u, -z - 0.6), (u, -0.55), (u + side * 0.08, -0.55), (u + side * 0.08, 0.05), (u - side * 0.53, 0.05)]
            return pts if side < 0 else pts
        # outer wall face (MSE panels) and coping (concrete) as separate strips
        A = [(f[0][0] + f[2][0] * side * hw, f[0][1] + f[2][1] * side * hw, -0.6) for f in fr]
        Bt = [(f[0][0] + f[2][0] * side * hw, f[0][1] + f[2][1] * side * hw, f[3] - 0.55) for f in fr]
        if side > 0:
            B.quad_strip(A, Bt, "M_XW_MSE", grime=(0.0, zmax))
        else:
            B.quad_strip(Bt, A, "M_XW_MSE", grime=(0.0, zmax))
        cop = [(side * (hw + 0.08), -0.55), (side * (hw + 0.08), 0.0), (side * hw, 0.0), (side * hw, -0.55)]
        B.sweep(fr, ccw(cop), "M_XW_Concrete", closed=True, caps=(True, True), grime="local")
        bar = nj_barrier(side * (hw - 0.53), side, 0.0, back_u=0.53)
        B.sweep(fr, ccw(bar), "M_XW_Concrete", closed=True, caps=(True, True), grime="local")
    # road surface between the barriers, the median barrier, markings
    B.sweep(fr, [(hw - 0.53, 0.0), (-hw + 0.53, 0.0)], "M_XW_Asphalt", closed=False, caps=(False, False))
    med = ccw([(-0.305, 0.0), (0.305, 0.0), (0.229 - 0.152, 0.254), (0.076, 0.813), (-0.076, 0.813), (-0.077, 0.254)])
    med = ccw([(-0.305, 0.0), (0.305, 0.0), (0.153, 0.254), (0.076, 0.813), (-0.076, 0.813), (-0.153, 0.254)])
    B.sweep(fr, med, "M_XW_Concrete", closed=True, caps=(True, True), grime="local")
    if st["twin"]:
        W = st["deck_w"]; curb_w = st["rail_w"] + st["fascia"]
        for dc in st["decks"]:
            inner = +1 if dc < 0 else -1
            e_in = dc + inner * (W / 2 - curb_w - st["shoulder_in"])
            e_out = dc - inner * (W / 2 - curb_w - st["shoulder_out"])
            for u, mname, dash in ((e_in - inner * 0.1, "M_XW_PaintYellow", False), (e_out + inner * 0.1, "M_XW_PaintWhite", False),
                                   ((e_in + e_out) / 2, "M_XW_PaintWhite", True)):
                segs = [(s_a, s_b)]
                if dash:
                    segs = []
                    sv = math.floor(s_a / 12.19) * 12.19
                    while sv < s_b:
                        a, b = max(s_a, sv), min(s_b, sv + 3.05)
                        if b - a > 0.3:
                            segs.append((a, b))
                        sv += 12.19
                for a, b in segs:
                    B.sweep(R.frames(a, b, 2.0), [(u + 0.075, 0.008), (u - 0.075, 0.008)], mname, closed=False, caps=(False, False))
    # the abutment where the bridge starts: front wall to the seat, seat, backwall up to the road
    c, t, n, z = R.frame(abut_s)
    seat = z - st["slab"] - st["haunch"] - Hab - 0.05
    O = (c[0], c[1], 0.0)
    d = abut_dir
    # front wall (faces the bridge): from -0.5 up to the seat, 0.9 m in front of the backwall
    outline = ccw([(-hw, -0.5), (hw, -0.5), (hw, seat), (-hw, seat)])
    e0, e1 = (0.0, 0.9) if d > 0 else (-0.9, 0.0)
    B.prism(outline, O, (n[0], n[1], 0), (0, 0, 1), e0 * 1, e1 * 1, "M_XW_Concrete")
    # backwall: from the seat to the road surface, at the joint line
    outline = ccw([(-hw + 0.53, seat), (hw - 0.53, seat), (hw - 0.53, z - 0.02), (-hw + 0.53, z - 0.02)])
    e0, e1 = (-0.35, 0.0) if d > 0 else (0.0, 0.35)
    B.prism(outline, O, (n[0], n[1], 0), (0, 0, 1), e0, e1, "M_XW_Concrete")
    # end face of the fill under the barriers/walls (closing the walls at the abutment line)


def build_austin(key, lay):
    R = Road(lay)
    st = R.st
    spans = lay["spans"]
    bents = lay["bents"]
    s_ab0, s_ab1 = lay["abutments"]
    Hs = [span_H(sp, st) for sp in spans]
    # chunk boundaries every 4 spans
    groups = []
    cur = []
    for i, sp in enumerate(spans):
        cur.append(i)
        if len(cur) == 4:
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)
    names = []
    for gi, grp in enumerate(groups):
        s0 = spans[grp[0]]["s0"]
        c0 = R.frame(s0)[0]
        B = Builder(f"XW_{key.upper()}_Span{gi:02d}", (round(c0[0], 2), round(c0[1], 2)))
        for i in grp:
            sp = spans[i]
            for k in range(len(st["decks"])):
                plus = st["decks"][k] < 0
                tx_deck_span(B, R, k, sp, plus)
        # bents at the start of each span in this group (bent i sits between span i-1 and span i)
        for i in grp:
            if i == 0:
                continue
            b = bents[i - 1]
            Hmax = max(Hs[i - 1], Hs[i])
            tx_bent(B, R, b, Hmax, (Hs[i - 1], Hs[i]))
        s1 = spans[grp[-1]]["s1"]
        for L in lay["lights"]:
            if s0 <= L["s"] < s1:
                tx_light(B, R, L)
        for g in lay["gantries"]:
            if s0 <= g["s"] < s1 or (gi == len(groups) - 1 and g["s"] >= s1):
                sign_bridge(B, R, g, "tx")
        names.append(B.name)
        export(B, "deck", {"s": [s0, s1]})
    # ramps on fill + abutments
    for tag, (a, b), abut_s, d, Hab in (("FillE", (0.0, s_ab0), s_ab0, +1, Hs[0]), ("FillW", (s_ab1, R.L), s_ab1, -1, Hs[-1])):
        if b - a < 1.0:
            continue
        c0 = R.frame(a)[0]
        B = Builder(f"XW_{key.upper()}_{tag}", (round(c0[0], 2), round(c0[1], 2)))
        fa, fb = (a, b - JOINT / 2) if d > 0 else (a + JOINT / 2, b)
        fill_end(B, R, fa, fb, abut_s, d, Hab)
        for L in lay["lights"]:
            if a <= L["s"] < b and R.frame(L["s"])[3] > 1.0:
                tx_light(B, R, L)
        export(B, "fill", {"s": [a, b]})
    return names


# ------------------------------------------------------------------------------------------------ Chicago pieces
def chi_parapet(side, hw, base_v=0.0):
    """IDOT-style concrete parapet: safety-shape traffic face, thick flat top, plain outside face that runs on down over the
    slab edge as one pale fascia, a drip groove near its foot (cut into the fascia profile). CCW outline (u, v)."""
    s = side
    toe = s * (hw - 0.63)
    pts = [(toe, 0.0), (toe, 0.08), (toe + s * 0.17, 0.27), (toe + s * 0.24, 0.95), (s * hw, 0.95), (s * hw, -0.12),
           (s * (hw - 0.04), -0.15), (s * hw, -0.18), (s * hw, -0.30), (s * (hw - 0.63), -0.30)]
    return ccw(pts)


def chi_markings(B, R, s0, s1):
    """Each direction 2 lanes; + traffic on the right half (u < 0): yellow inside edge, dashed lane line, white edge."""
    st = R.st
    hw = st["deck_w"] / 2
    for sgn in (-1, +1):
        e_in = sgn * (0.305 + st["shoulder_in"])
        e_out = sgn * (hw - 0.63 - st["shoulder_out"])
        for u, mname, dash in ((e_in + sgn * 0.1, "M_XW_PaintYellow", False), (e_out - sgn * 0.1, "M_XW_PaintWhite", False),
                               ((e_in + e_out) / 2, "M_XW_PaintWhite", True)):
            segs = [(s0, s1)]
            if dash:
                segs = []
                sv = math.floor(s0 / 12.19) * 12.19
                while sv < s1:
                    a, b = max(s0, sv), min(s1, sv + 3.05)
                    if b - a > 0.3:
                        segs.append((a, b))
                    sv += 12.19
            for a, b in segs:
                B.sweep(R.frames(a, b, 2.5), [(u + 0.075, 0.008), (u - 0.075, 0.008)], mname, closed=False, caps=(False, False))


def chi_deck_span(B, R, i, sp, joint_end):
    st = R.st
    W = st["deck_w"]
    hw = W / 2
    slab = st["slab"]
    s0, s1 = sp["s0"] + JOINT / 2, sp["s1"] - JOINT / 2
    fr = R.frames(s0, s1, 2.5)
    # slab (between the parapets) + road surface
    prof = [(hw - 0.63, -slab), (hw - 0.63, 0.0), (-hw + 0.63, 0.0), (-hw + 0.63, -slab)]
    B.sweep(fr, prof, ["M_XW_Concrete", "M_XW_Asphalt", "M_XW_Concrete", "M_XW_Concrete"], closed=True, caps=(True, True), grime="local")
    for side in (+1, -1):
        B.sweep(fr, chi_parapet(side, hw), "M_XW_Concrete", closed=True, caps=(True, True), grime="local")
    med = ccw([(-0.305, 0.0), (0.305, 0.0), (0.153, 0.254), (0.076, 0.813), (-0.076, 0.813), (-0.153, 0.254)])
    B.sweep(fr, med, "M_XW_Concrete", closed=True, caps=(True, True), grime="local")
    chi_markings(B, R, s0, s1)
    for sgn in ():
        e_in = sgn * (0.305 + st["shoulder_in"])
        e_out = sgn * (hw - 0.63 - st["shoulder_out"])
        for u, mname, dash in ((e_in + sgn * 0.1, "M_XW_PaintYellow", False), (e_out - sgn * 0.1, "M_XW_PaintWhite", False),
                               ((e_in + e_out) / 2, "M_XW_PaintWhite", True)):
            segs = [(s0, s1)]
            if dash:
                segs = []
                sv = math.floor(s0 / 12.19) * 12.19
                while sv < s1:
                    a, b = max(s0, sv), min(s1, sv + 3.05)
                    if b - a > 0.3:
                        segs.append((a, b))
                    sv += 12.19
            for a, b in segs:
                B.sweep(R.frames(a, b, 2.5), [(u + 0.075, 0.008), (u - 0.075, 0.008)], mname, closed=False, caps=(False, False))
    # steel plate girders, cross-frames, stiffeners on the fascia girders
    prof_i, H = i_profile("steel_plate", st["girder_d"], st["haunch"])
    n_g = st["girders_per_deck"]
    over = 1.0
    spacing = (W - 2 * over) / (n_g - 1)
    g0, g1 = sp["s0"] + 0.1, sp["s1"] - 0.1
    frg = R.frames(g0, g1, 4.0)
    v_bot = -slab - st["haunch"] - H
    for j in range(n_g):
        ug = -hw + over + j * spacing
        B.sweep(frg, [(ug + a, v_bot + b) for a, b in prof_i], "M_XW_PaintedSteel", closed=True, caps=(True, True), grime=None)
    sv = g0 + 1.25
    while sv < g1 - 0.5:
        c, t, n, z = R.frame(sv)
        for ug in (-hw + over, hw - over):
            for side in (-1, 1):
                q = (c[0] + n[0] * (ug + side * 0.07), c[1] + n[1] * (ug + side * 0.07))
                B.vbox(q, t, n, 0.016, 0.12, z + v_bot + 0.05, z - slab - st["haunch"] - 0.04, "M_XW_PaintedSteel", grime=None)
        sv += 2.5
    sv = g0 + 3.0
    while sv < g1 - 1.0:
        c, t, n, z = R.frame(sv)
        for j in range(n_g - 1):
            ua = -hw + over + j * spacing; ub = ua + spacing
            pa = (c[0] + n[0] * ua, c[1] + n[1] * ua); pb = (c[0] + n[0] * ub, c[1] + n[1] * ub)
            zt, zb = z - slab - 0.15, z + v_bot + 0.15
            B.tube([(pa[0], pa[1], zt), (pb[0], pb[1], zb)], [0.05, 0.05], "M_XW_PaintedSteel", sides=4, cap=False)
            B.tube([(pa[0], pa[1], zb), (pb[0], pb[1], zt)], [0.05, 0.05], "M_XW_PaintedSteel", sides=4, cap=False)
            B.tube([(pa[0], pa[1], zb), (pb[0], pb[1], zb)], [0.04, 0.04], "M_XW_PaintedSteel", sides=4, cap=False)
        sv += 7.5
    if joint_end:
        c, t, n, z = R.frame(sp["s1"])
        a = [(c[0] + n[0] * u - t[0] * 0.12, c[1] + n[1] * u - t[1] * 0.12, z + 0.004) for u in (hw - 0.63, -hw + 0.63)]
        b = [(c[0] + n[0] * u + t[0] * 0.12, c[1] + n[1] * u + t[1] * 0.12, z + 0.004) for u in (hw - 0.63, -hw + 0.63)]
        B.face([a[0], a[1], b[1], b[0]], "M_XW_JointSteel")
    return H


def chi_bent(B, R, b, H):
    """Cap beam on round columns (the Dan Ryan's forest of columns), or a straddle bent; black drain pipes."""
    st = R.st
    c, t, n, z = R.frame(b["s"])
    cap_top = z - st["slab"] - st["haunch"] - H - 0.06
    o0, o1 = min(b["offs"]), max(b["offs"])
    hw = st["deck_w"] / 2
    a0, a1 = min(o0 - 0.9, -hw + 0.8), max(o1 + 0.9, hw - 0.8)
    d = st["cap_d"] if b["type"] != "straddle" else 1.7
    outline = ccw([(a0, -d), (a1, -d), (a1, 0.0), (a0, 0.0)])
    B.prism(outline, (c[0], c[1], cap_top), (n[0], n[1], 0), (0, 0, 1), -st["cap_w"] / 2, st["cap_w"] / 2, "M_XW_Concrete")
    r = st["col"][0] / 2 if b["type"] != "straddle" else st["straddle_col"][0] / 2
    for k, o in enumerate(b["offs"]):
        cc = (c[0] + n[0] * o, c[1] + n[1] * o)
        B.tube([(cc[0], cc[1], -0.5), (cc[0], cc[1], cap_top - d + 0.02)], [r, r], "M_XW_Concrete", sides=12)
        if k == 0:
            pc = (cc[0] + t[0] * (r + 0.12), cc[1] + t[1] * (r + 0.12))
            B.tube([(pc[0], pc[1], cap_top - 0.2), (pc[0], pc[1], 0.4), (pc[0] + t[0] * 0.4, pc[1] + t[1] * 0.4, 0.2)], [0.1, 0.1, 0.1], "M_XW_Pipe", sides=8)
    n_g = st["girders_per_deck"]
    spacing = (st["deck_w"] - 2.0) / (n_g - 1)
    for j in range(n_g):
        ug = -hw + 1.0 + j * spacing
        q = (c[0] + n[0] * ug, c[1] + n[1] * ug)
        B.vbox(q, t, n, 0.5, 0.55, cap_top, cap_top + 0.06, "M_XW_Bearing")


def chi_light(B, R, L):
    """IDOT davit pole on the parapet top, single arm over the lanes."""
    st = R.st
    c, t, n, z = R.frame(L["s"])
    p = L["p"]
    zb = z + st["rail_h"]
    top = z + st["light_h"]
    B.vbox((p[0], p[1]), t, n, 0.45, 0.45, zb - 0.02, zb + 0.04, "M_XW_Galv")
    B.tube([(p[0], p[1], zb), (p[0], p[1], top - 0.6)], [0.12, 0.08], "M_XW_Galv", sides=8)
    ax, ay = n[0] * L["arm"], n[1] * L["arm"]
    reach = st["light_arm"]
    B.tube([(p[0], p[1], top - 0.7), (p[0] + ax * 0.5, p[1] + ay * 0.5, top - 0.05), (p[0] + ax * reach, p[1] + ay * reach, top + 0.1)],
           [0.07, 0.06, 0.05], "M_XW_Galv", sides=8, cap=False)
    hx = (p[0] + ax * (reach + 0.35), p[1] + ay * (reach + 0.35))
    B.vbox(hx, (ax, ay), (ay, -ax), 0.8, 0.38, top - 0.02, top + 0.2, "M_XW_Galv", chamfer=0.08)
    B.vbox(hx, (ax, ay), (ay, -ax), 0.55, 0.3, top - 0.12, top - 0.01, "M_XW_Lens")


def chi_fill(B, R, s_a, s_b, abut_s, abut_dir, Hab):
    """Approach on fill between plain cast-in-place retaining walls, parapets on top, median barrier, abutment."""
    st = R.st
    hw = st["deck_w"] / 2
    fr = R.frames(s_a, s_b, 2.0)
    zmax = max(f[3] for f in fr)
    for side in (+1, -1):
        A = [(f[0][0] + f[2][0] * side * hw, f[0][1] + f[2][1] * side * hw, -0.6) for f in fr]
        Bt = [(f[0][0] + f[2][0] * side * hw, f[0][1] + f[2][1] * side * hw, f[3] - 0.3) for f in fr]
        B.quad_strip(A, Bt, "M_XW_Concrete", grime=(0.0, zmax)) if side > 0 else B.quad_strip(Bt, A, "M_XW_Concrete", grime=(0.0, zmax))
        B.sweep(fr, chi_parapet(side, hw), "M_XW_Concrete", closed=True, caps=(True, True), grime="local")
    B.sweep(fr, [(hw - 0.63, 0.0), (-hw + 0.63, 0.0)], "M_XW_Asphalt", closed=False, caps=(False, False))
    med = ccw([(-0.305, 0.0), (0.305, 0.0), (0.153, 0.254), (0.076, 0.813), (-0.076, 0.813), (-0.153, 0.254)])
    B.sweep(fr, med, "M_XW_Concrete", closed=True, caps=(True, True), grime="local")
    chi_markings(B, R, s_a, s_b)
    c, t, n, z = R.frame(abut_s)
    seat = z - st["slab"] - st["haunch"] - Hab - 0.06
    if seat > 0.2:
        O = (c[0], c[1], 0.0)
        outline = ccw([(-hw, -0.5), (hw, -0.5), (hw, seat), (-hw, seat)])
        e0, e1 = (0.0, 0.9) if abut_dir > 0 else (-0.9, 0.0)
        B.prism(outline, O, (n[0], n[1], 0), (0, 0, 1), e0, e1, "M_XW_Concrete")
        outline = ccw([(-hw + 0.63, seat), (hw - 0.63, seat), (hw - 0.63, z - 0.02), (-hw + 0.63, z - 0.02)])
        e0, e1 = (-0.35, 0.0) if abut_dir > 0 else (0.0, 0.35)
        B.prism(outline, O, (n[0], n[1], 0), (0, 0, 1), e0, e1, "M_XW_Concrete")


def build_chicago(key, lay):
    R = Road(lay)
    st = R.st
    spans = lay["spans"]
    bents = lay["bents"]
    s_ab0, s_ab1 = lay["abutments"]
    H = st["girder_d"]
    groups, cur = [], []
    for i, sp in enumerate(spans):
        cur.append(i)
        if len(cur) == 4:
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)
    for gi, grp in enumerate(groups):
        s0 = spans[grp[0]]["s0"]
        c0 = R.frame(s0)[0]
        B = Builder(f"XW_{key.upper()}_Span{gi:02d}", (round(c0[0], 2), round(c0[1], 2)))
        for i in grp:
            chi_deck_span(B, R, i, spans[i], joint_end=(i % 3 == 2 or i == len(spans) - 1))
            if i > 0:
                chi_bent(B, R, bents[i - 1], H)
        s1 = spans[grp[-1]]["s1"]
        for L in lay["lights"]:
            if s0 <= L["s"] < s1:
                chi_light(B, R, L)
        for g in lay["gantries"]:
            if s0 <= g["s"] < s1:
                sign_bridge(B, R, g, "chi")
        export(B, "deck", {"s": [s0, s1]})
    for tag, (a, b), abut_s, d in (("FillS", (0.0, s_ab0), s_ab0, +1), ("FillN", (s_ab1, R.L), s_ab1, -1)):
        if b - a < 1.0:
            continue
        c0 = R.frame(a)[0]
        B = Builder(f"XW_{key.upper()}_{tag}", (round(c0[0], 2), round(c0[1], 2)))
        fa, fb = (a, b - JOINT / 2) if d > 0 else (a + JOINT / 2, b)
        chi_fill(B, R, fa, fb, abut_s, d, H)
        for L in lay["lights"]:
            if a <= L["s"] < b and R.frame(L["s"])[3] > 1.0:
                chi_light(B, R, L)
        export(B, "fill", {"s": [a, b]})


# ------------------------------------------------------------------------------------------------ catalogue
def catalog():
    """Stand-alone kit pieces at the origin (not placed by build_expressway_ue.py; for reuse and reference): a straight
    span of each style, one bent, a rail/parapet module, a light pole, a sign bridge, a ramp module on fill with its
    abutment. Built by the same functions as the placed pieces, on a straight test road along plan +x."""
    for style in ("austin", "chicago"):
        st = LAY["styles"][style]
        top = st["deck_top"]
        def road(z_of_s, L=80.0):
            c = [[sv, 0.0, z_of_s(sv), sv] for sv in [i * 2.0 for i in range(int(L / 2) + 1)]]
            return Road({"style": style, "centre": c})
        R = road(lambda sv: top)
        tag = "TX" if style == "austin" else "CHI"
        sp = {"s0": 10.0, "s1": 40.0, "len": 30.0, "girder": st["girder_types"][0][1], "girder_d": st["girder_types"][0][2]}
        B = Builder(f"XWK_{tag}_Span30", (25.0, 0.0))
        if style == "austin":
            for k in range(len(st["decks"])):
                tx_deck_span(B, R, k, sp, st["decks"][k] < 0)
        else:
            chi_deck_span(B, R, 0, sp, True)
        export(B, "catalog")
        b = {"s": 10.0, "type": "hammer" if style == "austin" else "multi", "offs": list(st["decks"]) if style == "austin" else [-st["deck_w"] / 2 + 2.2, 0.0, st["deck_w"] / 2 - 2.2]}
        B = Builder(f"XWK_{tag}_Bent", (10.0, 0.0))
        H = span_H(sp, st)
        if style == "austin":
            tx_bent(B, R, b, H, (H, H))
        else:
            chi_bent(B, R, b, H)
        export(B, "catalog")
        L = {"s": 10.0, "p": [10.0, st["deck_w"] / 2 - 0.4], "arm": -1}
        B = Builder(f"XWK_{tag}_LightPole", (10.0, st["deck_w"] / 2 - 0.4))
        (tx_light if style == "austin" else chi_light)(B, R, L)
        export(B, "catalog")
        g = {"deck": 0, "s": 20.0, "face": -1, "signs": ["I35N_DALLAS", "UPPER_THRU"] if style == "austin" else ["WCX_S_LOOP", "WCX_S_290"]}
        B = Builder(f"XWK_{tag}_SignBridge", (21.6, st["decks"][0] if st["twin"] else 0.0))
        sign_bridge(B, R, g, "tx" if style == "austin" else "chi")
        export(B, "catalog")
        Rr = road(lambda sv: min(top, max(0.0, (sv - 2.0) * st["grade"])), 200.0)
        ab = (top / st["grade"]) * 0.95
        B = Builder(f"XWK_{tag}_RampOnFill", (0.0, 0.0))
        if style == "austin":
            fill_end(B, Rr, 0.0, ab, ab, +1, H)
        else:
            chi_fill(B, Rr, 0.0, ab, ab, +1, H)
        export(B, "catalog")


# ------------------------------------------------------------------------------------------------ main
def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    t0 = time.time()
    if "catalog" in ARGS:
        catalog()
    for key in (ROADS if any(a in LAY["roads"] for a in ARGS) or "catalog" not in ARGS else []):
        lay = LAY["roads"][key]
        # drop this road's old meshes from kit.json (chunk counts change with the layout)
        for nm in [n for n in KIT["meshes"] if n.startswith(f"XW_{key.upper()}_")]:
            del KIT["meshes"][nm]
        if lay["style"] == "austin":
            build_austin(key, lay)
        elif lay["style"] == "chicago":
            build_chicago(key, lay)
    KIT["made"] = time.strftime("%Y-%m-%d %H:%M")
    json.dump(KIT, open(KITJ, "w"), indent=1)
    print("ALL DONE", round(time.time() - t0, 1), "s")


main()
