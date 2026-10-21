"""Blocky stand-ins for Kenny's five third-party vehicles (Model 3, Model Y, Cybertruck, Robotaxi, Semi), for the public
itch.io build and the open-source repo: the real models are not licensed for redistribution, so the game ships these
instead (Source/SkyCity/SkysterFleet.h picks /Game/Vehicles/Placeholder/... when a car is listed under [SkyFleet]
PlaceholderCars in Config/DefaultGame.ini, or when the real model's package is missing).
They are meant to say "a car of this size and kind goes here", so anyone can model their own and drop it in
(Scripts/vehicles/PLACEHOLDERS.md): true size, true wheel positions / radii / widths, the same part names, glass panels
(windscreen, side windows, rear glass, roof glass where the real car has it), headlight and taillight strips at the
light sockets of SourceArt/Vehicles/parts.json, black trim and bumpers, wheel arches cut as notches, simple tyres
and 5-spoke rims. Everything is built from boxes, hexahedra and prisms (no bevels yet: it is meant to be upgraded to
rounder shapes later). Written from the published dimensions and plain photos of the vehicle classes: no mesh of the real
models is used (the real GLBs are only read, if present, to render the side-by-side preview sheet).
Frame and conventions are those of Scripts/vehicles/blender_split_lineup.py: metres, +X = front, +Y = the car's left,
+Z up, body origin on the ground under the centre, each wheel mesh centred on its own pivot (pivot_m from parts.json,
wheel axle along Y), exported with the same glTF settings, so the Unreal import lands at
<dest>/TV_<Car>_<Part>/StaticMeshes/TV_<Car>_<Part> like the real ones.
Material slots (the C++ lamp code matches Headlight / Taillight / AuxLight by exact name): Paint, Glass, Headlight,
Taillight, Trim, Tyre, Rim (+ AuxLight on the Cybertruck's roof bar, MarkerLight on the Semi's roof lamps).
Run: Blender -b --factory-startup -P Scripts/vehicles/blender_placeholder_cars.py [-- Model3 ModelY ... ] [nopreview]
  (PLACEHOLDER_OUT=/some/dir writes there instead of SourceArt/Vehicles/Placeholder, for a dry run)
Output: <out>/<Car>/TV_<Car>_Body.glb and TV_<Car>_<Wheel>.glb, plus Saved/VehicleModels/placeholders_sheet.jpg (the
real car next to its placeholder, side / three-quarter / front / top; only when the real GLBs are around) and
Saved/VehicleModels/placeholders_only.jpg (placeholders alone)."""
import json, math, os, sys
import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.path.join(os.environ.get("SKYCITY_ROOT") or os.path.expanduser("~/UnrealProjects/SkyCity"), "Scripts", "vehicles")
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.environ.get("PLACEHOLDER_OUT", f"{ROOT}/SourceArt/Vehicles/Placeholder")
REAL = f"{ROOT}/SourceArt/Vehicles"                       # the real models (never in the public repo): preview only
SHEETS = f"{ROOT}/Saved/VehicleModels"
PARTS = json.load(open(f"{REAL}/parts.json")) if os.path.exists(f"{REAL}/parts.json") else json.load(open(f"{HERE}/placeholder_parts.json"))   # (the latter: a public checkout)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
CARS = [a for a in ARGS if a in PARTS] or list(PARTS)
PREVIEW = "nopreview" not in ARGS
E = 0.012                                                  # how far lamps and trim strips stand proud of the body

SLOTS = ["Paint", "Glass", "Headlight", "Taillight", "Trim", "Tyre", "Rim", "AuxLight", "MarkerLight"]
SI = {s: i for i, s in enumerate(SLOTS)}
PAINT = {"Paint_Gold": ((0.72, 0.58, 0.36), 0.6, 0.28), "Paint_BlueGloss": ((0.015, 0.04, 0.2), 0.3, 0.2),
         "Paint_RedGloss": ((0.42, 0.006, 0.008), 0.35, 0.2), "Paint_Silver": ((0.62, 0.63, 0.65), 0.85, 0.25),
         None: ((0.55, 0.56, 0.57), 1.0, 0.38)}           # null = bare stainless steel (the Cybertruck)


def make_materials(paint):
    """One material per slot, named exactly like the slot (the glTF -> Unreal import turns the names into slot names).
    Fresh Blender state per car, so 'Paint' can be a different colour for each."""
    col, metal, rough = PAINT[paint]
    spec = {"Paint": (col, metal, rough, None, 1.0), "Glass": ((0.008, 0.012, 0.016), 0.0, 0.03, None, 0.35),
            "Headlight": ((1, 1, 1), 0.0, 0.2, (1.0, 0.97, 0.92), 1.0), "Taillight": ((0.3, 0, 0), 0.0, 0.2, (1.0, 0.03, 0.02), 1.0),
            "Trim": ((0.018, 0.018, 0.02), 0.0, 0.6, None, 1.0), "Tyre": ((0.012, 0.012, 0.013), 0.0, 0.9, None, 1.0),
            "Rim": ((0.62, 0.63, 0.66), 1.0, 0.28, None, 1.0), "AuxLight": ((1, 1, 1), 0.0, 0.2, (1.0, 0.97, 0.92), 1.0),
            "MarkerLight": ((1.0, 0.4, 0.02), 0.0, 0.3, (1.0, 0.45, 0.02), 1.0)}
    out = {}
    for n in SLOTS:
        c, me, ro, em, al = spec[n]
        m = bpy.data.materials.new(n)
        m.use_nodes = True
        b = next(x for x in m.node_tree.nodes if x.type == "BSDF_PRINCIPLED")
        b.inputs["Base Color"].default_value = (*c, 1.0)
        b.inputs["Metallic"].default_value = me
        b.inputs["Roughness"].default_value = ro
        if em:
            b.inputs["Emission Color"].default_value = (*em, 1.0)
            b.inputs["Emission Strength"].default_value = 3.0
        if al < 1.0:
            b.inputs["Alpha"].default_value = al
            try:
                m.surface_render_method = "BLENDED"
            except Exception:
                pass
        m.diffuse_color = (*(em or c), al if n == "Glass" else 1.0)
        m.use_backface_culling = True
        out[n] = m
    return out


# ------------------------------------------------------------------------------------------------ geometry kit
FACES = {"bottom": (0, 1, 2, 3), "top": (4, 5, 6, 7), "front": (0, 1, 5, 4), "rear": (2, 3, 7, 6), "left": (3, 0, 4, 7), "right": (1, 2, 6, 5)}
# a hexahedron's corner order: b0 front-left, b1 front-right, b2 rear-right, b3 rear-left, then t0..t3 above them
# (so cabins can have a raked windscreen, tumblehome and so on). Face parameter frames for panels (u, v) from corner 00:
PANEL = {"front": (1, 0, 4, 5), "rear": (2, 3, 7, 6), "left": (3, 0, 4, 7), "right": (2, 1, 5, 6), "top": (6, 5, 4, 7)}   # 00, 10, 11, 01


class Mesher:
    def __init__(self):
        self.bm = bmesh.new()

    def solid(self, pts, quads, mats):
        """A closed solid from corner points and face index lists; normals are made outward afterwards."""
        vs = [self.bm.verts.new(p) for p in pts]
        fs = []
        for q, m in zip(quads, mats):
            f = self.bm.faces.new([vs[i] for i in q])
            f.material_index = SI[m]
            fs.append(f)
        bmesh.ops.recalc_face_normals(self.bm, faces=fs)
        return vs

    def hexa(self, c, mats="Paint"):
        """c: 8 corner points (see FACES); mats: one slot name or a dict face-name -> slot name."""
        order = ("bottom", "top", "front", "rear", "left", "right")
        m = [mats.get(k, mats.get("*", "Paint")) if isinstance(mats, dict) else mats for k in order]
        self.solid([Vector(p) for p in c], [FACES[k] for k in order], m)
        return [Vector(p) for p in c]

    def box(self, x0, x1, y0, y1, z0, z1, mats="Paint"):
        return self.hexa([(x1, y1, z0), (x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z1), (x1, y0, z1), (x0, y0, z1), (x0, y1, z1)], mats)

    def sbox(self, x0, x1, ya, yb, z0, z1, mats="Paint"):
        """The same box on both sides of the car (|y| from ya to yb)."""
        self.box(x0, x1, ya, yb, z0, z1, mats)
        self.box(x0, x1, -yb, -ya, z0, z1, mats)

    def prism(self, ring0, ring1, mats, cap0="Paint", cap1="Paint"):
        """A prism between two equal point rings (an extruded polygon)."""
        n = len(ring0)
        pts = list(ring0) + list(ring1)
        quads = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)] + [tuple(range(n)), tuple(range(n, 2 * n))]
        ms = (mats if isinstance(mats, list) else [mats] * n) + [cap0, cap1]
        self.solid([Vector(p) for p in pts], quads, ms)

    def side_prism(self, prof, y0, y1, mats="Paint", cap="Paint"):
        """prof: (x, z) points around the side view, extruded across the width from y0 to y1."""
        self.prism([(x, y0, z) for x, z in prof], [(x, y1, z) for x, z in prof], mats, cap, cap)

    def plan_prism(self, poly, z0, z1, mat="Paint"):
        """poly: (x, y) points seen from above, extruded from z0 to z1."""
        self.prism([(x, y, z0) for x, y in poly], [(x, y, z1) for x, y in poly], mat, mat, mat)

    def arch(self, cx, cz, r, y0, y1, n=12, mat="Trim"):
        """A wheel-arch cutter: an n-gon prism along Y, flat on top."""
        prof = [(cx + r * math.cos(math.pi / n + 2 * math.pi * k / n), cz + r * math.sin(math.pi / n + 2 * math.pi * k / n)) for k in range(n)]
        self.side_prism(prof, y0, y1, mat, mat)

    def corner_cut(self, xa, xf, yf, hw, mat="Paint"):
        """Chamfer a plan-view corner (cutter): from (xa, hw) on the side to (xf, yf) on the end face, both sides."""
        for s in (1, -1):
            p0, p1 = Vector((xa, hw)), Vector((xf, yf))
            d = (p1 - p0).normalized()
            a, b = p0 - d * 0.4, p1 + d * 0.4
            q = Vector((xf + (0.5 if xf > xa else -0.5), hw + 0.5))
            poly = [(a.x, s * a.y), (b.x, s * b.y), (q.x, s * q.y)]
            self.plan_prism(poly, -1.0, 6.0, mat)

    def quad(self, pts, hint, mat, off=0.008):
        """A single glass/trim panel (not closed), facing along `hint`, lifted `off` off its surface. Glass gets a dark
        backing sheet just under it (there is no interior behind the windows: over bare paint the glass would read as a
        pale film)."""
        p = [Vector(x) for x in pts]
        n = (p[1] - p[0]).cross(p[-1] - p[0]) if len(p) == 4 else Newell(p)
        n.normalize()
        if n.dot(Vector(hint)) < 0:
            p.reverse()
            n = -n
        if mat == "Glass":
            g = self.bm.faces.new([self.bm.verts.new(v + n * off * 0.4) for v in p])
            g.material_index = SI["Trim"]
        f = self.bm.faces.new([self.bm.verts.new(v + n * off) for v in p])
        f.material_index = SI[mat]
        return f

    def panel(self, c, face, u0, u1, v0, v1, mat="Glass", off=0.008):
        """A panel inset into one face of a hexahedron (corners c): u, v in 0..1 across the face (PANEL gives the frame).
        Both sides of the car at once for the side faces ('side')."""
        if face == "side":
            self.panel(c, "left", u0, u1, v0, v1, mat, off)
            return self.panel(c, "right", u0, u1, v0, v1, mat, off)
        i00, i10, i11, i01 = (Vector(c[i]) for i in PANEL[face])
        centre = sum((Vector(p) for p in c), Vector()) / 8.0
        mid = (i00 + i10 + i11 + i01) / 4.0

        def at(u, v):
            return i00 + (i10 - i00) * u + (i01 - i00) * v + (i00 - i10 + i11 - i01) * u * v
        self.quad([at(u0, v0), at(u1, v0), at(u1, v1), at(u0, v1)], mid - centre, mat, off)

    def strip(self, pa, pb, t0, t1, z0, z1, mat, out=E, depth=0.035):
        """A lamp / trim strip lying on a plan-view edge pa -> pb (both (x, y), y > 0), from t0 to t1 along it, on both sides."""
        pa, pb = Vector(pa), Vector(pb)
        d = pb - pa
        n = Vector((-d.y, d.x)).normalized()
        if n.dot((pa + pb) / 2.0) < 0:
            n = -n
        for s in (1, -1):
            def P(t, o):
                q = pa + d * t + n * o
                return (q.x, s * q.y)
            ring = lambda z: [(*P(t0, out), z), (*P(t1, out), z), (*P(t1, -depth), z), (*P(t0, -depth), z)]
            self.solid([Vector(p) for p in ring(z0) + ring(z1)], [FACES[k] for k in ("bottom", "top", "front", "rear", "left", "right")], [mat] * 6)

    def uv_and_finish(self, me):
        """Plain box-projected UVs (so the import never trips over a missing UV set) and write into mesh `me`."""
        uv = self.bm.loops.layers.uv.new("UVMap")
        self.bm.normal_update()
        for f in self.bm.faces:
            n = f.normal
            ax = max(range(3), key=lambda i: abs(n[i]))
            for lp in f.loops:
                c = lp.vert.co
                lp[uv].uv = {0: (c.y, c.z), 1: (c.x, c.z), 2: (c.x, c.y)}[ax]
        self.bm.normal_update()
        self.bm.to_mesh(me)
        self.bm.free()


def Newell(p):
    n = Vector()
    for i in range(len(p)):
        a, b = p[i], p[(i + 1) % len(p)]
        n += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
    return n


def new_object(name, mats, bm=None):
    me = bpy.data.meshes.new(name)
    for s in SLOTS:
        me.materials.append(mats[s])
    if bm is not None:
        bm.to_mesh(me)
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def boolean_difference(mats, tub, cut):
    """tub minus cut (both Mesher); cutter faces keep the slot they were built with (Trim wells, Paint chamfers)."""
    a, b = new_object("tub", mats, tub.bm), new_object("cut", mats, cut.bm)
    mod = a.modifiers.new("cut", "BOOLEAN")
    mod.operation, mod.operand_type, mod.object, mod.solver = "DIFFERENCE", "OBJECT", b, "EXACT"
    mod.material_mode = "INDEX"
    bpy.context.view_layer.objects.active = a
    a.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(b)
    r = Mesher()
    r.bm.from_mesh(a.data)
    bpy.data.objects.remove(a)
    return r


# ------------------------------------------------------------------------------------------------ wheels
def build_wheel(mats, name, R, W, side, spokes=5, solid_cover=False):
    """Tyre (a lathe with rounded shoulders) plus a rim: a disc on the outer face, a hub, and raised spokes (a solid
    cover for the Robotaxi). Centred on its pivot, axle along Y, outer face toward `side` (+1 left, -1 right)."""
    M = Mesher()
    N = 20
    hole = 0.80 if solid_cover else 0.60                                                       # radius of the rim opening / R
    ring = [(hole, -0.5), (0.93, -0.5), (1.0, -0.38), (1.0, 0.38), (0.93, 0.5), (hole, 0.5)]    # (radius / R, y / W)
    pts = [Vector((R * r * math.cos(2 * math.pi * k / N), W * yy, R * r * math.sin(2 * math.pi * k / N))) for k in range(N) for r, yy in ring]
    quads, ms = [], []
    nr = len(ring)
    for k in range(N):
        for j in range(nr):
            a, b = k * nr + j, k * nr + (j + 1) % nr
            c, d = ((k + 1) % N) * nr + (j + 1) % nr, ((k + 1) % N) * nr + j
            quads.append((a, b, c, d))
            ms.append("Tyre")
    M.solid(pts, quads, ms)
    yo = side * W * 0.5
    n = 10

    def disc(r, y0, y1, mat):
        M.prism([(R * r * math.cos(2 * math.pi * k / n), y0, R * r * math.sin(2 * math.pi * k / n)) for k in range(n)],
                [(R * r * math.cos(2 * math.pi * k / n), y1, R * r * math.sin(2 * math.pi * k / n)) for k in range(n)], mat, mat, mat)
    # nothing stands proud of the tyre's outer face, so the wheel is exactly as wide as parts.json says
    if solid_cover:
        disc(0.81, yo - side * W * 0.12, yo - side * 0.004, "Rim")
    else:
        disc(0.62, yo - side * W * 0.10, yo - side * 0.012, "Tyre")                    # the dark dish behind the spokes
        for k in range(spokes):
            a = 2 * math.pi * k / spokes + math.pi / 2
            ca, sa = math.cos(a), math.sin(a)
            r0, r1, hw_ = R * 0.10, R * 0.57, R * 0.055
            P = lambda r, w: (r * ca - w * sa, r * sa + w * ca)
            ring4 = lambda y: [(P(r0, -hw_)[0], y, P(r0, -hw_)[1]), (P(r1, -hw_)[0], y, P(r1, -hw_)[1]), (P(r1, hw_)[0], y, P(r1, hw_)[1]), (P(r0, hw_)[0], y, P(r0, hw_)[1])]
            M.prism(ring4(yo - side * W * 0.05), ring4(yo - side * 0.003), "Rim", "Rim", "Rim")
        disc(0.17, yo - side * W * 0.05, yo - side * 0.003, "Rim")
    return M


# ------------------------------------------------------------------------------------------------ the five cars
def wheels_of(info):
    return {k: v for k, v in info["parts"].items() if k != "Body"}


def arches(cut, info, extra, yin, which=None, n=12):
    for k, w in wheels_of(info).items():
        if which and k not in which:
            continue
        px, py, pz = w["pivot_m"]
        s = 1 if py > 0 else -1
        y0, y1 = (yin, abs(py) + 1.0) if s > 0 else (-abs(py) - 1.0, -yin)
        cut.arch(px, pz, w["radius"] + extra, y0, y1, n)


def cab_corners(xbf, xbr, xtf, xtr, zbf, zbr, zt, hbf, hbr, htf):
    """The 8 corners of a cabin (see FACES): bottom front/rear x and z, top front/rear x, top z, half widths at the
    bottom front / bottom rear / top front. The top-rear half width follows from keeping each side face planar, so
    the glass panels (which are flat) sit on the surface."""
    b = (hbf - hbr) / (xbf - xbr)
    c = (htf - hbf - b * (xtf - xbf)) / (zt - zbf)
    htr = hbr + b * (xtr - xbr) + c * (zt - zbr)
    return [(xbf, hbf, zbf), (xbf, -hbf, zbf), (xbr, -hbr, zbr), (xbr, hbr, zbr),
            (xtf, htf, zt), (xtf, -htf, zt), (xtr, -htr, zt), (xtr, htr, zt)]


def model3(info):
    """Sedan with a fastback glass roof: low nose, long sloping rear glass, black pillars, glass roof."""
    L, W, H0, H1 = info["size_m"][0] / 2 - E, info["size_m"][1] / 2, 0.1283, 0.1283 + info["size_m"][2]
    hw, X = 0.92, L
    tub = Mesher()
    prof = [(-2.30, H0), (2.28, H0), (X, 0.30), (X, 0.62), (2.12, 0.72), (1.00, 1.00), (-1.90, 1.02), (-X, 1.10), (-X, 0.30)]
    tub.side_prism(prof, -hw, hw, ["Trim"] + ["Paint"] * 8)
    cut = Mesher()
    cut.corner_cut(2.00, X, 0.55, hw)
    cut.corner_cut(-2.00, -X, 0.70, hw)
    arches(cut, info, 0.07, 0.625)
    body = boolean_difference(MATS, tub, cut)
    cab = cab_corners(1.00, -1.95, .08, -1.00, .99, .99, H1 - .008, .885, .85, .665)
    body.hexa(cab, "Trim")
    body.panel(cab, "front", .07, .93, .05, .93)                    # windscreen
    body.panel(cab, "rear", .09, .91, .10, .93)                     # rear glass (fastback)
    body.panel(cab, "side", .53, .93, .12, .90)                     # front door glass
    body.panel(cab, "side", .07, .49, .12, .90)                     # rear door glass
    body.panel(cab, "top", .06, .94, .08, .92)                      # glass roof
    body.sbox(.45, .62, .90, 1.0438, .99, 1.07, "Trim")             # mirrors
    body.strip((2.00, hw), (X, 0.55), 0.05, 0.80, 0.60, 0.67, "Headlight")
    body.strip((-2.00, hw), (-X, 0.70), 0.0, 1.0, 0.86, 0.94, "Taillight")
    body.sbox(-X - E, -X + 0.03, 0.22, 0.70, 0.86, 0.94, "Taillight")
    body.sbox(X - 0.03, X + E, 0.0, 0.50, 0.30, 0.46, "Trim")       # lower grille
    body.sbox(-X - E, -X + 0.03, 0.0, 0.66, 0.14, 0.34, "Trim")     # rear diffuser
    body.sbox(-0.95, 0.95, hw - 0.02, hw + E, 0.17, 0.30, "Trim")   # side skirts
    return body


def modely(info):
    """Taller crossover: higher belt, upright greenhouse, sloped liftback, panorama roof, light bar across the tail."""
    L, H0, H1 = info["size_m"][0] / 2 - E, 0.162, 0.162 + info["size_m"][2]
    hw, X = 0.945, L
    tub = Mesher()
    prof = [(-2.30, H0), (2.28, H0), (X, 0.30), (X, 0.58), (2.15, 0.88), (1.60, 1.03), (1.10, 1.12), (-1.90, 1.14), (-X, 1.28), (-X, 0.30)]
    tub.side_prism(prof, -hw, hw, ["Trim"] + ["Paint"] * 9)
    cut = Mesher()
    cut.corner_cut(2.02, X, 0.55, hw)
    cut.corner_cut(-2.05, -X, 0.72, hw)
    arches(cut, info, 0.07, 0.64)
    body = boolean_difference(MATS, tub, cut)
    cab = cab_corners(1.10, -2.10, .10, -1.15, 1.115, 1.22, H1 - .008, .92, .89, .70)
    body.hexa(cab, "Trim")
    body.panel(cab, "front", .06, .94, .05, .93)
    body.panel(cab, "rear", .08, .92, .10, .93)
    body.panel(cab, "side", .56, .94, .13, .90)
    body.panel(cab, "side", .22, .52, .13, .90)
    body.panel(cab, "side", .06, .18, .20, .83)                     # rear quarter window
    body.panel(cab, "top", .05, .95, .08, .92)                      # panorama roof
    body.sbox(.55, .72, .92, 1.0621, 1.12, 1.22, "Trim")
    body.strip((2.02, hw), (X, 0.55), 0.05, 0.80, 0.64, 0.71, "Headlight")
    body.box(-X - E, -X + 0.03, -0.72, 0.72, 1.06, 1.14, "Taillight")   # the light bar across the tail, round the corners
    body.strip((-2.05, hw), (-X, 0.72), 0.0, 1.0, 1.06, 1.14, "Taillight")
    body.sbox(X - 0.03, X + E, 0.0, 0.55, 0.16, 0.44, "Trim")       # black lower bumpers, wrapping the corners
    body.strip((2.02, hw), (X, 0.55), 0.0, 1.0, 0.16, 0.44, "Trim")
    body.sbox(-X - E, -X + 0.03, 0.0, 0.72, 0.16, 0.44, "Trim")
    body.strip((-2.05, hw), (-X, 0.72), 0.0, 1.0, 0.16, 0.44, "Trim")
    body.sbox(-0.95, 0.95, hw - 0.02, hw + E, 0.20, 0.34, "Trim")
    return body


def cybertruck(info):
    """The angular wedge: one long raked plane from nose to roof ridge, flat glass roof, tonneau-covered bed behind the
    cab between the sail panels, a light bar across the nose and tail, a roof light bar."""
    X, hw = info["size_m"][0] / 2 - E, 1.10
    TOP = info["size_m"][2]
    tub = Mesher()
    prof = [(-2.80, 0.265), (2.70, 0.265), (X, 0.50), (X, 1.15), (0.30, TOP), (-1.10, 1.71), (-X, 1.41), (-X, 0.40)]
    tub.side_prism(prof, -hw, hw, ["Trim"] + ["Paint"] * 7)
    cut = Mesher()
    cut.corner_cut(2.76, X, 0.90, hw)
    cut.corner_cut(-2.76, -X, 0.95, hw)
    arches(cut, info, 0.09, 0.76)
    body = boolean_difference(MATS, tub, cut)
    k = (TOP - 1.15) / (X - 0.30)                                   # slope of the nose/windscreen plane
    zr = lambda x: 1.15 + (X - x) * k
    k2 = (TOP - 1.71) / (0.30 + 1.10)                               # first stretch of the rear roof
    zroof = lambda x: TOP - (0.30 - x) * k2
    k3 = (1.71 - 1.41) / (X - 1.10)
    ztail = lambda x: 1.71 - (-1.10 - x) * k3
    body.quad([(2.15, .95, zr(2.15)), (2.15, -.95, zr(2.15)), (.55, -.88, zr(.55)), (.55, .88, zr(.55))], (0, 0, 1), "Glass")      # windscreen
    body.quad([(.20, .74, zroof(.20)), (.20, -.74, zroof(.20)), (-.95, -.74, zroof(-.95)), (-.95, .74, zroof(-.95))], (0, 0, 1), "Glass")   # roof glass
    body.quad([(-1.14, .76, ztail(-1.14)), (-1.14, -.76, ztail(-1.14)), (-2.80, -.76, ztail(-2.80)), (-2.80, .76, ztail(-2.80))], (0, 0, 1), "Trim")   # tonneau
    for s in (1, -1):
        y = s * hw
        body.quad([(x, y, z) for x, z in [(2.00, 1.25), (0.60, 1.25), (0.60, zr(.60) - .07), (2.00, zr(2.00) - .07)]], (0, s, 0), "Glass")   # front door glass
        body.quad([(x, y, z) for x, z in [(0.42, 1.25), (-0.92, 1.25), (-0.92, zroof(-.92) - .07), (0.42, zr(.42) - .07)]], (0, s, 0), "Glass")   # rear door glass
    body.box(0.40, 0.54, -0.65, 0.65, zr(.47) - .01, zr(.47) + .035, "AuxLight")                     # roof light bar
    body.box(X - 0.03, X + E, -0.86, 0.86, 0.97, 1.03, "Headlight")
    body.strip((2.76, hw), (X, 0.90), 0.0, 1.0, 0.97, 1.03, "Headlight")
    body.box(-X - E, -X + 0.03, -0.88, 0.88, 1.14, 1.22, "Taillight")
    body.strip((-2.76, hw), (-X, 0.95), 0.0, 1.0, 1.14, 1.22, "Taillight")
    body.sbox(-1.25, 1.55, hw - 0.02, hw + E, 0.30, 0.58, "Trim")   # lower cladding
    body.box(X - 0.04, X + E, -0.88, 0.88, 0.52, 0.85, "Trim")
    body.box(-X - E, -X + 0.04, -0.88, 0.88, 0.42, 0.80, "Trim")
    body.sbox(1.05, 1.25, 1.0, 1.14, 1.28, 1.40, "Trim")             # mirrors
    return body


def robotaxi(info):
    """Compact two-door teardrop: low nose, one big glass greenhouse sloping into a long tail, slim light bars, covered wheels."""
    L, hw, H0, H1 = info["size_m"][0] / 2 - E, info["size_m"][1] / 2 - E, 0.1586, 0.1586 + info["size_m"][2]
    X = L
    tub = Mesher()
    prof = [(-2.0, H0), (2.0, H0), (X, 0.30), (X, 0.62), (1.85, 0.75), (1.50, 0.88), (1.00, 0.93), (-X, 0.93), (-X, 0.30)]
    tub.side_prism(prof, -hw, hw, ["Trim"] + ["Paint"] * 8)
    cut = Mesher()
    cut.corner_cut(1.90, X, 0.60, hw)
    cut.corner_cut(-1.95, -X, 0.62, hw)
    arches(cut, info, 0.05, 0.57)
    body = boolean_difference(MATS, tub, cut)
    cab = cab_corners(1.00, -2.10, .05, -.55, .92, .92, H1, .85, .80, .66)
    body.hexa(cab, "Paint")
    body.panel(cab, "front", .07, .93, .05, .93)                    # windscreen (the real car has no rear glass or roof glass)
    body.panel(cab, "side", .42, .93, .12, .90)                     # one window per side: two doors, no B pillar
    body.box(X - 0.03, X + E, -0.57, 0.57, 0.54, 0.61, "Headlight")
    body.strip((1.90, hw), (X, 0.60), 0.0, 1.0, 0.54, 0.61, "Headlight")
    body.box(-X - E, -X + 0.03, -0.58, 0.58, 0.78, 0.84, "Taillight")
    body.strip((-1.95, hw), (-X, 0.62), 0.0, 1.0, 0.78, 0.84, "Taillight")
    body.sbox(-0.88, 0.94, hw - 0.02, hw + E, 0.17, 0.32, "Trim")
    body.sbox(X - 0.03, X + E, 0.0, 0.60, 0.17, 0.38, "Trim")
    body.strip((1.90, hw), (X, 0.60), 0.0, 1.0, 0.17, 0.38, "Trim")
    body.sbox(-X - E, -X + 0.03, 0.0, 0.62, 0.17, 0.38, "Trim")
    body.strip((-1.95, hw), (-X, 0.62), 0.0, 1.0, 0.17, 0.38, "Trim")
    return body


def semi(info):
    """Tall day-cab tractor, no trailer: raked windscreen, tall slab sides with a big side window, chamfered nose with
    teardrop lamps at the corners, a black chassis behind the cab with rear fenders over the drive tandem and a fifth wheel."""
    X, hw, TOP = info["size_m"][0] / 2 - E, 1.27, 0.1294 + info["size_m"][2]
    tub = Mesher()
    prof = [(-0.25, 0.55), (3.55, 0.55), (X, 0.65), (X, 0.95), (3.30, 1.55), (2.58, 2.49), (1.60, 3.38), (0.80, 3.78), (0.20, TOP), (-0.25, TOP)]
    tub.side_prism(prof, -hw, hw, ["Trim"] + ["Paint"] * 9)
    cut = Mesher()
    cut.corner_cut(3.00, X, 0.70, hw)
    arches(cut, info, 0.10, 0.90, which=("Wheel_A1L", "Wheel_A1R"))
    body = boolean_difference(MATS, tub, cut)
    zr = lambda x: 1.55 + (3.30 - x) * (0.94 / 0.72)               # the windscreen plane
    body.quad([(3.22, 1.02, zr(3.22)), (3.22, -1.02, zr(3.22)), (2.60, -1.10, zr(2.60)), (2.60, 1.10, zr(2.60))], (1, 0, 1), "Glass")   # windscreen
    for s in (1, -1):
        y = s * hw
        body.quad([(x, y, z) for x, z in [(0.95, 1.55), (2.90, 1.55), (2.90, 1.85), (2.42, 2.60), (0.95, 2.60)]], (0, s, 0), "Glass")
    body.strip((3.00, hw), (X, 0.70), 0.30, 0.95, 0.80, 1.05, "Headlight")
    for y in (-0.40, 0.0, 0.40):
        body.box(2.52, 2.60, y - 0.07, y + 0.07, 2.50, 2.56, "MarkerLight")
    body.sbox(2.20, 2.40, hw - 0.02, 1.3876, 1.85, 2.55, "Trim")     # mirrors
    body.box(3.45, X + E, -0.95, 0.95, 0.30, 0.58, "Trim")           # bumper bar
    body.box(0.0, 3.30, -0.90, 0.90, 0.25, 0.56, "Trim")             # under the cab
    body.box(-X, -0.25, -0.85, 0.85, 0.25, 1.05, "Trim")             # chassis behind the cab
    body.box(-X - E, -X + 0.15, -1.00, 1.00, 0.129, 0.36, "Trim")        # rear underride guard
    body.box(-2.20, -0.90, -0.65, 0.65, 1.05, 1.15, "Trim")          # fifth wheel
    body.sbox(-2.50, -0.25, 0.82, 1.25, 1.07, 1.17, "Paint")         # rear fenders over the tandem
    body.box(-2.64, -2.54, -1.10, 1.10, 0.68, 0.76, "Taillight")
    return body


BUILD = {"Model3": model3, "ModelY": modely, "Cybertruck": cybertruck, "Robotaxi": robotaxi, "Semi": semi}


# ------------------------------------------------------------------------------------------------ export + preview
def tris(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def export(ob, path):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO")


def build_car(name):
    global MATS
    info = PARTS[name]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    MATS = make_materials(info.get("paint"))
    od = f"{OUT}/{name}"
    os.makedirs(od, exist_ok=True)
    stats = {}
    body = BUILD[name](info)
    ob = new_object(f"TV_{name}_Body", MATS)
    body.uv_and_finish(ob.data)
    export(ob, f"{od}/TV_{name}_Body.glb")
    stats["Body"] = tris(ob)
    keep = [ob]
    for part, w in wheels_of(info).items():
        side = 1 if w["pivot_m"][1] > 0 else -1
        m = build_wheel(MATS, part, w["radius"], w["width"], side, solid_cover=(name == "Robotaxi"))
        wo = new_object(f"TV_{name}_{part}", MATS)
        m.uv_and_finish(wo.data)
        export(wo, f"{od}/TV_{name}_{part}.glb")
        stats[part] = tris(wo)
        keep.append(wo)
        wo.location = w["pivot_m"]                  # (after the export: it only positions them for the preview renders)
    lo = [min(v.co[i] for v in ob.data.vertices) for i in range(3)]
    hi = [max(v.co[i] for v in ob.data.vertices) for i in range(3)]
    if PREVIEW:
        preview_car(name, info, keep)
    print(f"PLACEHOLDER {name}: body bbox x[{lo[0]:.3f},{hi[0]:.3f}] y[{lo[1]:.3f},{hi[1]:.3f}] z[{lo[2]:.3f},{hi[2]:.3f}] "
          f"(real size {info['size_m']}); tris {stats}")
    return stats



# ------------------------------------------------------------------------------------------------ preview renders
VIEWS = ("q34", "side", "front", "top")
TMP = bpy.app.tempdir or "/tmp"                 # the single view renders (Blender cleans its temp dir on exit)


def scene_setup():
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    try:
        sc.eevee.taa_render_samples = 24
    except Exception:
        pass
    sc.render.resolution_x, sc.render.resolution_y = 480, 270
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 82
    w = bpy.data.worlds.new("sky")
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.55, 0.66, 0.85, 1)
    bg.inputs["Strength"].default_value = 1.1
    sc.world = w
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 4.0
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    bpy.context.collection.objects.link(sun)
    gm = bpy.data.materials.new("ground")
    gm.use_nodes = True
    next(n for n in gm.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"].default_value = (0.32, 0.33, 0.35, 1)
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, -0.005))
    bpy.context.object.data.materials.append(gm)
    bpy.context.object.name = "ground"
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    bpy.context.collection.objects.link(cam)
    sc.camera = cam
    return cam


def shoot(cam, view, info, path):
    c = cam.data
    L, Wd, Hh = info["size_m"][0], info["size_m"][1], info["size_m"][2] + 0.2
    zc = Hh / 2.0
    aspect = 480.0 / 270.0
    if view == "q34":
        az, el, D = math.radians(36), math.radians(15), 1.45 * L + 0.8 * Hh
        c.type, c.lens = "PERSP", 40
        cam.location = (D * math.cos(el) * math.cos(az), -D * math.cos(el) * math.sin(az), zc + D * math.sin(el))
        cam.rotation_euler = (Vector((0.0, 0.0, zc)) - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
    else:
        c.type = "ORTHO"
        if view == "side":
            c.ortho_scale = max(L * 1.1, Hh * 1.25 * aspect)
            cam.location, cam.rotation_euler = (0, -40, zc), (math.radians(90), 0, 0)
        elif view == "front":
            c.ortho_scale = max(Wd * 1.25, Hh * 1.2 * aspect)
            cam.location, cam.rotation_euler = (40, 0, zc), (math.radians(90), 0, math.radians(90))
        else:                                   # top: front to the right, like the side view
            c.ortho_scale = max(L * 1.1, Wd * 1.25 * aspect)
            cam.location, cam.rotation_euler = (0, 0, 40), (0, 0, 0)
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def import_real(name):
    """The real car (body + wheels at their pivots) for the comparison; None when its GLBs aren't here (public checkout)."""
    objs = []
    for part, pi in PARTS[name]["parts"].items():
        f = f"{REAL}/{name}/{pi['file']}"
        if not os.path.exists(f):
            return None
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=f)
        for o in [o for o in bpy.data.objects if o not in before]:
            objs.append(o)
            if o.parent is None:
                o.location = Vector(o.location) + Vector(pi["pivot_m"])
    return objs


def preview_car(name, info, mine):
    """Render the placeholder (and, if the real GLBs are around, the real car) from the same four views into TMP."""
    os.makedirs(TMP, exist_ok=True)
    cam = scene_setup()
    for kind in ("placeholder", "real"):
        objs = mine if kind == "placeholder" else import_real(name)
        if objs is None:
            continue
        for o in mine:
            o.hide_render = kind != "placeholder"
        for v in VIEWS:
            shoot(cam, v, info, f"{TMP}/{name}_{kind}_{v}.jpg")
        if kind == "real":
            for o in objs:
                bpy.data.objects.remove(o)


COMPOSE = r"""
import sys, os, glob
from PIL import Image, ImageDraw
tmp, out_pair, out_only, cars = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].split(",")
views = ["q34", "side", "front", "top"]
W, H = 480, 270
def sheet(path, with_real):
    cols = [(v, k) for v in views for k in (("real", "placeholder") if with_real else ("placeholder",))]
    im = Image.new("RGB", (W * len(cols), H * len(cars)), (20, 20, 22))
    d = ImageDraw.Draw(im)
    for r, c in enumerate(cars):
        for i, (v, k) in enumerate(cols):
            f = f"{tmp}/{c}_{k}_{v}.jpg"
            if os.path.exists(f):
                im.paste(Image.open(f), (i * W, r * H))
            d.text((i * W + 6, r * H + 4), f"{c} {k} {v}", fill=(255, 255, 255))
    im.save(path, quality=84)
    print("sheet", path, im.size)
sheet(out_pair, True)
sheet(out_only, False)
"""


def make_sheets(cars):
    import subprocess
    try:
        subprocess.run(["python3", "-I", "-c", COMPOSE, TMP, f"{SHEETS}/placeholders_sheet.jpg", f"{SHEETS}/placeholders_only.jpg", ",".join(cars)], check=True)
    except Exception as e:
        print("preview sheets skipped (needs python3 with Pillow):", e, "- the single views are in", TMP)


def write_parts_json():
    """The sizes, wheel pivots / radii / widths and light sockets this script (and placeholders_ue.py) build from, as a
    small file that lives next to them: SourceArt/Vehicles/parts.json, where they come from, stays out of public repos."""
    keep = {}
    for n, v in PARTS.items():
        keep[n] = {"size_m": v["size_m"], "paint": v.get("paint"),
                   "parts": {k: {kk: vv for kk, vv in pi.items() if kk != "file"} | {"file": f"TV_{n}_{k}.glb"} for k, pi in v["parts"].items()},
                   "lights": {"sockets": v["lights"]["sockets"]}}
    json.dump(keep, open(f"{HERE}/placeholder_parts.json", "w"), indent=1)


allstats = {}
if os.path.exists(f"{REAL}/parts.json"):
    write_parts_json()
for c in CARS:
    allstats[c] = build_car(c)
if PREVIEW:
    make_sheets(CARS)
print("PLACEHOLDERS DONE", {c: sum(s.values()) for c, s in allstats.items()})
