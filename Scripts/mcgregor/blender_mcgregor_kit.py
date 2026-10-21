"""McGregor demo-area set pieces, modelled in Blender (headless) and exported as GLB (one per asset).
Same conventions as Scripts/streets/blender_street_kit.py: metres, standing on z = 0, front toward Blender -Y
(Unreal +X after the glTF import).

  MG_Ramp        the ~75 ft crescent ramp from the reveal photos: up through vertical into a long, nearly flat inverted
                 run (LIP in ramp()), 5.5 m deck with painted lines and red edge trim, lattice tower + top girder
                 (deck UVs in metres along the curve since 20 Oct round 2: Unreal gives it a concrete scan, MI_RampDeck)
                 Approach runs along -Y (Blender), so in Unreal the car drives toward -X into the ramp face.
  MG_RampTarps   the tarp curtains alone (so tarp configurations can be swapped / hidden)
  MG_FleetDeck   the low red-lit deck the five-vehicle line-up stood on; MG_Veh_* unbadged stand-in vehicles (sedan,
                 crossover, semi cab, pickup, coupe) sized and coloured from the reveal photos
  MG_Stage       event stage: 20 x 12 m deck at 1.2 m, truss roof at 10 m, LED wall, light bars
  MG_DragFence   one 10 m bay of black windscreen fencing on posts (instanced along the drag strip)
  MG_LightTower  portable light tower (trailer, mast, 4-lamp head)
  MG_Gantry      16 m steel box gantry with tarps draped inside
  MG_FlareStack  28 m flare stack with ladder platforms
Run: /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/mcgregor/blender_mcgregor_kit.py [-- ramp stage ...]
Output: SourceArt/McGregor/meshes/<name>.glb
"""
import math, os, sys
import bpy
from mathutils import Matrix, Vector

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
sys.path.insert(0, os.path.join(ROOT, "Scripts", "streets"))
import importlib.util
spec = importlib.util.spec_from_file_location("kit", os.path.join(ROOT, "Scripts", "streets", "blender_street_kit.py"))
# reuse the Builder / mat / export helpers without running the street kit's jobs
src = open(spec.origin).read().split("# ------------------------------------------------------------------ props")[0]
K = {"__file__": spec.origin}
exec(compile(src, "kit_helpers", "exec"), K)
Builder, mat, export = K["Builder"], K["mat"], K["export"]
K["OUT"] = os.path.join(ROOT, "SourceArt", "McGregor", "meshes")
os.makedirs(K["OUT"], exist_ok=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    K["MATS"].clear()


STEEL = lambda: mat("M_ScaffoldSteel", (0.55, 0.56, 0.58), 0.85, 0.4)
DECK = lambda: mat("M_RampDeck", (0.92, 0.92, 0.9), 0.1, 0.35)
TARP = lambda: mat("M_Tarp", (0.045, 0.047, 0.05), 0.0, 0.85)     # charcoal scaffold netting
TRUSS = lambda: mat("M_TrussAlu", (0.75, 0.76, 0.78), 0.9, 0.35)
BLACK = lambda: mat("M_BlackPlastic", (0.03, 0.03, 0.03), 0.0, 0.6)
LED = lambda: mat("M_LEDWall", (0.05, 0.08, 0.12), 0.0, 0.2)
LAMP = lambda: mat("M_LampLens", (1.0, 0.92, 0.75), 0.0, 0.2)


def ramp():
    """The unveil ramp, from Kenny's reveal photos: a crescent deck that leaves the ground, climbs through vertical, curls
    back over the approach and ends in a long, nearly flat inverted run (the car crossed it upside down on its suction
    fans, then fired off the lip). Steel lattice tower behind the vertical part, a top girder carrying the cantilever.
    Proportions scaled from the daytime side photo; top of the lip ~23.7 m (78 ft), tower ~25.6 m. LIP = deck angle at
    the lip in degrees (180 = flat upside down)."""
    reset()
    B = Builder()
    W, T = 5.5, 0.6                     # deck width, deck thickness (back skin)
    LEAD, R1, S, R2, LIP, RUN = 4.0, 7.0, 6.0, 9.5, 170.0, 7.5     # fitted to the daytime side photo
    # profile in (f, z): f = distance forward (the car drives toward Blender -Y, so y = -f), integrated segment by segment
    segs = [("line", LEAD), ("arc", R1, 90.0), ("line", S), ("arc", R2, LIP - 90.0), ("line", RUN)]
    pts, ang = [(-LEAD, 0.0)], 0.0
    curve_start = None
    for sg in segs:
        f0, z0 = pts[-1]
        if sg[0] == "line":
            n = max(1, int(sg[1] / 2.0))
            for k in range(1, n + 1):
                pts.append((f0 + math.cos(math.radians(ang)) * sg[1] * k / n, z0 + math.sin(math.radians(ang)) * sg[1] * k / n))
        else:
            if curve_start is None:
                curve_start = len(pts) - 1
            R, d = sg[1], sg[2]
            cf, cz = f0 - R * math.sin(math.radians(ang)), z0 + R * math.cos(math.radians(ang))   # centre, on the rider side
            n = max(2, int(d / 5.0))
            for k in range(1, n + 1):
                t = math.radians(ang + d * k / n)
                pts.append((cf + R * math.sin(t), cz - R * math.cos(t)))
            ang += d
    prof = [(-f, z) for f, z in pts]    # -> Blender (y, z)
    ly, lz = prof[-1]
    TOP = lz + 2.0                      # top of the tower and girder

    def nrm(k):                         # rider-side unit normal of segment k in (y, z)
        k = min(k, len(prof) - 2)
        (y0, z0), (y1, z1) = prof[k], prof[k + 1]
        L = math.hypot(y1 - y0, z1 - z0)
        return (z1 - z0) / L, -(y1 - y0) / L

    def at(k, off):                     # profile point k pushed along the averaged normal (+ rider side, - back side)
        a_, b_ = nrm(max(k - 1, 0)), nrm(k)
        ny, nz = a_[0] + b_[0], a_[1] + b_[1]
        L = math.hypot(ny, nz) or 1.0
        return prof[k][0] + ny / L * off, prof[k][1] + nz / L * off
    deck, line, trim = DECK(), mat("M_RampLine", (0.95, 0.95, 0.93), 0.0, 0.5), mat("M_RampTrim", (0.75, 0.06, 0.04), 0.0, 0.4)
    # UVs in metres (round 2: the deck is textured concrete now, MI_RampDeck): u across the deck, v the distance along
    # the curve, so the texture runs round the crescent without stretching on the vertical part
    sl = [0.0]
    for k in range(len(prof) - 1):
        sl.append(sl[-1] + math.hypot(prof[k + 1][0] - prof[k][0], prof[k + 1][1] - prof[k][1]))
    for k in range(len(prof) - 1):
        (y0, z0), (y1, z1) = at(k, 0.02), at(k + 1, 0.02)
        v0, v1 = sl[k], sl[k + 1]
        B.face([(-W / 2, y0, z0), (W / 2, y0, z0), (W / 2, y1, z1), (-W / 2, y1, z1)][::-1], deck,
               [(-W / 2, v0), (W / 2, v0), (W / 2, v1), (-W / 2, v1)][::-1])
        for xc in (-W / 2 + 0.6, W / 2 - 0.6):          # the two painted lines
            (a0, c0), (a1, c1) = at(k, 0.04), at(k + 1, 0.04)
            B.face([(xc - 0.06, a0, c0), (xc + 0.06, a0, c0), (xc + 0.06, a1, c1), (xc - 0.06, a1, c1)][::-1], line)
        if k < curve_start:             # flat apron: thin, skirts to the ground
            for x in (-W / 2, W / 2):
                q = [(x, y0, 0.0), (x, y1, 0.0), (x, y1, z1), (x, y0, z0)]
                uq = [(v0, 0.0), (v1, 0.0), (v1, z1), (v0, z0)]
                B.face(q, deck, uq)
                B.face(q[::-1], deck, uq[::-1])
            continue
        (b0y, b0z), (b1y, b1z) = at(k, -T), at(k + 1, -T)
        B.face([(-W / 2, b0y, b0z), (W / 2, b0y, b0z), (W / 2, b1y, b1z), (-W / 2, b1y, b1z)], deck,
               [(-W / 2, v0), (W / 2, v0), (W / 2, v1), (-W / 2, v1)])
        for x in (-W / 2, W / 2):       # side faces of the thick plate, a red trim along the riding edge
            q = [(x, y0, z0), (x, y1, z1), (x, b1y, b1z), (x, b0y, b0z)]
            uq = [(v0, 0.0), (v1, 0.0), (v1, T), (v0, T)]
            B.face(q, deck, uq)
            B.face(q[::-1], deck, uq[::-1])
            (t0y, t0z), (t1y, t1z) = at(k, -0.14), at(k + 1, -0.14)
            sx = 0.01 if x > 0 else -0.01
            q = [(x + sx, y0, z0), (x + sx, y1, z1), (x + sx, t1y, t1z), (x + sx, t0y, t0z)]
            B.face(q, trim)
            B.face(q[::-1], trim)
    (by_, bz_) = at(len(prof) - 1, -T)
    q = [(-W / 2, ly, lz), (W / 2, ly, lz), (W / 2, by_, bz_), (-W / 2, by_, bz_)]
    B.face(q, deck)                     # lip edge
    B.face(q[::-1], deck)
    # the steel goes in its own mesh with no collision (thin tubes snag and trap the car); an invisible block
    # fills the tower and the space over the overhang so nothing can get wedged up there
    Bd, B = B, Builder()
    # lattice tower behind the vertical section
    s = mat("M_TrussSteel", (0.62, 0.63, 0.65), 0.8, 0.4)
    vy = -(LEAD * 0 + R1) - T - 0.2     # front face of the tower, just behind the deck's back skin
    D, xw = 4.0, W / 2 + 0.4
    ys2 = (vy, vy - D)
    cols = [(x, y) for x in (-xw, xw) for y in ys2]
    for x, y in cols:
        B.tube([(x, y, 0), (x, y, TOP)], [0.14, 0.14], s, 8, cap=False)
    lv = [2.0 * k for k in range(0, int(TOP / 2.0) + 1)] + [TOP]
    faces = [((-xw, ys2[0]), (xw, ys2[0])), ((-xw, ys2[1]), (xw, ys2[1])), ((-xw, ys2[0]), (-xw, ys2[1])), ((xw, ys2[0]), (xw, ys2[1]))]
    for i, z in enumerate(lv):
        for (ax, ay), (bx, by) in faces:
            B.tube([(ax, ay, z), (bx, by, z)], [0.06, 0.06], s, 6, cap=False)
            if i + 1 < len(lv):
                z1 = lv[i + 1]
                if i % 2:
                    B.tube([(ax, ay, z), (bx, by, z1)], [0.045, 0.045], s, 5, cap=False)
                else:
                    B.tube([(bx, by, z), (ax, ay, z1)], [0.045, 0.045], s, 5, cap=False)
    # top girders over the cantilever, from the back of the tower to the lip, with hangers down to the deck
    gy0, gy1 = ys2[1], ly + 0.3
    zb, zt = lz + T + 0.5, TOP
    gx = (-W / 2 + 0.4, W / 2 - 0.4)
    for x in gx:
        B.tube([(x, gy0, zb), (x, gy1, zb)], [0.1, 0.1], s, 6, cap=False)
        B.tube([(x, gy0, zt), (x, gy1, zt)], [0.1, 0.1], s, 6, cap=False)
        n = int(abs(gy1 - gy0) / 2.0)
        for k in range(n + 1):
            y = gy0 + (gy1 - gy0) * k / n
            B.tube([(x, y, zb), (x, y, zt)], [0.05, 0.05], s, 5, cap=False)
            if k < n:
                y1 = gy0 + (gy1 - gy0) * (k + 1) / n
                B.tube([(x, y, zb if k % 2 else zt), (x, y1, zt if k % 2 else zb)], [0.045, 0.045], s, 5, cap=False)
    for k in range(int(abs(gy1 - gy0) / 4.0) + 1):
        y = gy0 + (gy1 - gy0) * k / int(abs(gy1 - gy0) / 4.0)
        B.tube([(gx[0], y, zt), (gx[1], y, zt)], [0.05, 0.05], s, 5, cap=False)
    for k in range(curve_start, len(prof)):
        by, bz = at(k, -T)
        if k % 2 == 0 and by > vy + 0.5 and bz > lz - 8.0 and bz < zb - 0.3:       # hangers under the girders
            for x in gx:
                B.tube([(x, by, bz), (x, by, zb)], [0.05, 0.05], s, 5, cap=False)
        elif k % 2 == 0 and bz > 1.2 and by > vy and bz < lz - 8.0:                 # struts from the tower to the climb
            for x in gx:
                B.tube([(x, vy, bz), (x, by, bz)], [0.06, 0.06], s, 5, cap=False)
    # (used by the optional tarps below: netting round the tower)
    xs, ys, R, H = [-xw, xw], [vy, vy - D], -vy - 0.2, TOP - 2.0
    export("MG_Ramp", [Bd.finish("MG_Ramp")])
    export("MG_RampTruss", [B.finish("MG_RampTruss")])
    # invisible collision block: the tower's volume, and a prism from the deck's back skin (from the top of the
    # vertical section to the lip) up to the girder top, as wide as the deck
    K = Builder()
    kb = mat("M_RampBlock", (0.5, 0.5, 0.5), 0.0, 1.0)
    K.box((0, vy - D / 2, TOP / 2), (2 * xw, D, TOP), kb)
    k0 = next(k for k, (y, z) in enumerate(prof) if abs(y + R1) < 1e-6 and z >= R1 + S - 1e-6)
    poly = [at(k, -T) for k in range(k0, len(prof))]
    poly += [(poly[-1][0], TOP), (vy, TOP), (vy, poly[0][1])]
    half = W / 2
    n = len(poly)
    K.face([(-half, y, z) for (y, z) in poly], kb)
    K.face([(half, y, z) for (y, z) in poly][::-1], kb)
    for i in range(n):
        (y0, z0), (y1, z1) = poly[i], poly[(i + 1) % n]
        K.face([(-half, y0, z0), (half, y0, z0), (half, y1, z1), (-half, y1, z1)][::-1], kb)
    import bmesh
    bmesh.ops.recalc_face_normals(K.bm, faces=K.bm.faces[:])   # closed volumes, normals out
    export("MG_RampBlock", [K.finish("MG_RampBlock")])
    # tarps: netting wrapped round the scaffold tower (sides and back); the white deck curve stays open to view
    T = Builder()
    tarp = TARP()
    xw = xs[-1] + 0.3
    for x in (-xw, xw):
        for k in range(4):                                # gently billowing panels
            y0 = -R - 0.2 - k * (ys[0] - ys[-1] + 0.6) / 4
            y1 = y0 - (ys[0] - ys[-1] + 0.6) / 4
            bil = 0.15 * math.sin(k * 1.7)
            T.face([(x + bil, y0, 0.2), (x + bil, y1, 0.2), (x - bil * 0.5, y1, H + 2.0), (x - bil * 0.5, y0, H + 2.0)], tarp,
                   [(0, 0), (1, 0), (1, 6), (0, 6)])
            T.face([(x - bil * 0.5, y0, H + 2.0), (x - bil * 0.5, y1, H + 2.0), (x + bil, y1, 0.2), (x + bil, y0, 0.2)], tarp,
                   [(0, 6), (1, 6), (1, 0), (0, 0)])
    yb = ys[-1] - 0.4
    for k in range(6):
        x0 = -xw + k * 2 * xw / 6
        x1 = x0 + 2 * xw / 6
        T.face([(x0, yb, 0.2), (x1, yb, 0.2), (x1, yb, H + 2.0), (x0, yb, H + 2.0)], tarp, [(0, 0), (1, 0), (1, 6), (0, 6)])
        T.face([(x1, yb, 0.2), (x0, yb, 0.2), (x0, yb, H + 2.0), (x1, yb, H + 2.0)], tarp, [(0, 0), (1, 0), (1, 6), (0, 6)])
    export("MG_RampTarps", [T.finish("MG_RampTarps")])


def fleet_deck():
    """The low display deck the five-vehicle fleet sat on (red light strips round the edge). Long axis = Blender X
    (across the vehicles), vehicles face Blender -Y like every kit piece."""
    reset()
    B = Builder()
    L, D, h = 24.0, 9.0, 0.3
    B.box((0, 0, h / 2), (L, D, h), BLACK())
    red = mat("M_RampTrim", (0.75, 0.06, 0.04), 0.0, 0.4)
    for y in (-D / 2 - 0.03, D / 2 + 0.03):
        B.box((0, y, h * 0.55), (L + 0.1, 0.06, 0.07), red)
    for x in (-L / 2 - 0.03, L / 2 + 0.03):
        B.box((x, 0, h * 0.55), (0.06, D + 0.1, 0.07), red)
    export("MG_FleetDeck", [B.finish("MG_FleetDeck")])


def vehicle(name, kind, L, Wd, H, rgb, r):
    """Unbadged stand-in vehicles for the fleet line-up (sizes and colours from the reveal photos, no makes/logos)."""
    reset()
    B = Builder()
    paint = mat(f"M_Paint_{name}", rgb, 0.5, 0.28)
    glass = mat("M_CarGlass", (0.02, 0.025, 0.03), 0.2, 0.08)
    tyre = mat("M_Tyre", (0.025, 0.025, 0.025), 0.0, 0.85)
    lamp = LAMP()
    zb = r * 0.8                                    # body floor: wheels show below it
    if kind == "semi":
        B.box((0, 0.6, zb + 0.35), (Wd - 0.2, L - 1.2, 0.7), BLACK())                 # chassis
        cab = [(-Wd / 2, -L / 2, zb + 0.4), (Wd / 2, -L / 2, zb + 0.4), (Wd / 2, L / 2 - 1.6, zb + 0.4), (-Wd / 2, L / 2 - 1.6, zb + 0.4),
               (-Wd / 2 + 0.1, -L / 2 + 1.3, H), (Wd / 2 - 0.1, -L / 2 + 1.3, H), (Wd / 2 - 0.1, L / 2 - 1.6, H), (-Wd / 2 + 0.1, L / 2 - 1.6, H)]
    else:
        hb = H * (0.52 if kind != "pickup" else 0.58)
        B.box((0, 0, zb + hb / 2), (Wd - 0.12, L, hb), paint)
        if kind == "pickup":
            f0, f1, t0, t1 = -L / 2 + 1.1, 0.35, -L / 2 + 1.9, 0.2
        elif kind == "coupe":
            f0, f1, t0, t1 = -L / 2 + 1.2, L / 2 - 0.6, -L * 0.08, L * 0.12
        else:
            f0, f1, t0, t1 = -L / 2 + 1.25, L / 2 - 0.5, -L * 0.12, L * (0.3 if kind == "crossover" else 0.18)
        z0 = zb + hb
        cab = [(-Wd / 2 + 0.05, f0, z0), (Wd / 2 - 0.05, f0, z0), (Wd / 2 - 0.05, f1, z0), (-Wd / 2 + 0.05, f1, z0),
               (-Wd / 2 + 0.2, t0, H), (Wd / 2 - 0.2, t0, H), (Wd / 2 - 0.2, t1, H), (-Wd / 2 + 0.2, t1, H)]
        if kind == "pickup":                        # bed walls
            for x in (-Wd / 2 + 0.05, Wd / 2 - 0.05):
                B.box((x, (f1 + L / 2) / 2, z0 + 0.25), (0.08, L / 2 - f1, 0.5), paint)
            B.box((0, L / 2 - 0.04, z0 + 0.25), (Wd, 0.08, 0.5), paint)
    m_cab = paint if kind == "semi" else glass
    c = cab
    for q in ((0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
        B.face([c[i] for i in q][::-1], m_cab if q not in ((7, 6, 5, 4),) else paint)
    if kind == "semi":                              # windscreen band on the sloped front
        B.face([(-Wd / 2 + 0.06, -L / 2 + 0.75, H - 0.9), (Wd / 2 - 0.06, -L / 2 + 0.75, H - 0.9), (Wd / 2 - 0.08, -L / 2 + 1.2, H - 0.15),
                (-Wd / 2 + 0.08, -L / 2 + 1.2, H - 0.15)][::-1], glass)
    B.box((0, -L / 2 - 0.01, zb + 0.55 * (H if kind == "semi" else 1.0) * (0.35 if kind == "semi" else 0.8)), (Wd * 0.8, 0.03, 0.05), lamp)  # light bar
    for x in (-Wd / 2 + 0.1, Wd / 2 - 0.1):
        for y in ((-L / 2 + 1.0, L / 2 - 2.2, L / 2 - 0.9) if kind == "semi" else (-L / 2 + 0.85, L / 2 - 0.85)):
            B.tube([(x - 0.13, y, r), (x + 0.13, y, r)], [r, r], tyre, 16, cap=True)
    export(name, [B.finish(name)])


def fleet():
    fleet_deck()
    vehicle("MG_Veh_Sedan", "sedan", 4.72, 1.85, 1.44, (0.03, 0.08, 0.32), 0.34)
    vehicle("MG_Veh_Crossover", "crossover", 4.75, 1.92, 1.62, (0.45, 0.02, 0.02), 0.36)
    vehicle("MG_Veh_SemiCab", "semi", 6.6, 2.55, 3.9, (0.85, 0.86, 0.87), 0.52)
    vehicle("MG_Veh_Pickup", "pickup", 5.7, 2.2, 1.9, (0.55, 0.56, 0.57), 0.42)
    vehicle("MG_Veh_Coupe", "coupe", 4.25, 1.95, 1.3, (0.62, 0.52, 0.3), 0.34)


def stadium_light():
    """Reveal-night light mast: a 22 m galvanised pole with a 4 x 3 bank of LED floods facing Blender -Y (Unreal: the
    placement yaw), on a service platform."""
    reset()
    B = Builder()
    g = mat("M_Galvanized", (0.62, 0.63, 0.64), 0.9, 0.38)
    lamp = LAMP()
    B.box((0, 0, 0.3), (1.6, 1.6, 0.6), mat("M_Concrete", (0.55, 0.55, 0.53), 0.0, 0.9))
    B.tube([(0, 0, 0.6), (0, 0, 21.0)], [0.28, 0.16], g, 12)
    B.box((0, -0.3, 21.0), (4.6, 1.2, 0.12), g)                        # platform
    B.box((0, -0.65, 22.4), (4.4, 0.12, 2.6), BLACK())                 # bank frame
    for i in range(4):
        for j in range(3):
            x, z = -1.65 + i * 1.1, 21.55 + j * 0.85
            B.box((x, -0.78, z), (0.9, 0.18, 0.7), BLACK())
            B.card((x, -0.88, z), (0, -1, 0), (0, 0, 1), 0.8, 0.6, lamp)
    export("MG_StadiumLight", [B.finish("MG_StadiumLight")])


def light_truss():
    """A ground lighting truss like the one in front of the ramp on reveal night: a 12 m box truss on two
    towers with six moving-head fixtures on top and a red LED strip along its base."""
    reset()
    B = Builder()
    t = mat("M_TrussAlu", (0.75, 0.76, 0.78), 0.9, 0.35)
    red = mat("M_RampTrim", (0.75, 0.06, 0.04), 0.0, 0.4)
    for x in (-6.0, 6.0):
        for dx in (-0.25, 0.25):
            for dy in (-0.25, 0.25):
                B.tube([(x + dx, dy, 0), (x + dx, dy, 2.2)], [0.03, 0.03], t, 6, cap=False)
    for z in (2.0, 2.5):
        for dy in (-0.25, 0.25):
            B.tube([(-6.25, dy, z), (6.25, dy, z)], [0.03, 0.03], t, 6, cap=False)
    for k in range(25):
        x = -6.0 + k * 0.5
        B.tube([(x, -0.25, 2.0), (x + 0.5, 0.25, 2.5)], [0.015, 0.015], t, 4, cap=False)
    B.box((0, 0, 0.12), (12.6, 0.8, 0.24), BLACK())
    B.box((0, -0.41, 0.14), (12.6, 0.02, 0.06), red)
    for i in range(6):
        x = -5.0 + i * 2.0
        B.box((x, 0, 2.7), (0.45, 0.45, 0.2), BLACK())                  # base
        B.box((x, 0, 3.05), (0.3, 0.35, 0.45), BLACK())                 # yoke head
        B.card((x, -0.18, 3.1), (0, -1, 0), (0, 0, 1), 0.22, 0.22, LAMP())
    export("MG_LightTruss", [B.finish("MG_LightTruss")])


def beam_cone():
    """A light shaft: apex at the origin, 1 m long along +X (Unreal forward), base radius 0.5; V runs 0 at the apex
    to 1 at the base so the additive plume material fades it out."""
    reset()
    B = Builder()
    m = mat("M_Beam", (1.0, 1.0, 1.0), 0.0, 1.0)
    n = 24
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        B.face([(0.0, 0.0, 0.0), (1.0, 0.5 * math.cos(a0), 0.5 * math.sin(a0)), (1.0, 0.5 * math.cos(a1), 0.5 * math.sin(a1))], m,
               [(i / n, 0.0), (i / n, 1.0), ((i + 1) / n, 1.0)])
    export("MG_BeamCone", [B.finish("MG_BeamCone")])


def night():
    stadium_light()
    light_truss()
    beam_cone()


def stage():
    reset()
    B = Builder()
    W, D, h = 20.0, 12.0, 1.2
    B.box((0, 0, h / 2), (W, D, h), BLACK())
    B.box((0, -D / 2 - 1.0, 0.4), (6.0, 2.0, 0.8), BLACK())          # front steps
    t = TRUSS()
    for x in (-W / 2, W / 2):
        for y in (-D / 2, D / 2):
            B.tube([(x, y, 0), (x, y, 10.5)], [0.25, 0.25], t, 8, cap=False)
    for y in (-D / 2, D / 2):
        B.tube([(-W / 2, y, 10.5), (W / 2, y, 10.5)], [0.25, 0.25], t, 8, cap=False)
    for x in (-W / 2, 0.0, W / 2):
        B.tube([(x, -D / 2, 10.5), (x, D / 2, 10.5)], [0.2, 0.2], t, 8, cap=False)
    B.box((0, 0, 10.9), (W + 1, D + 1, 0.15), mat("M_StageRoof", (0.08, 0.08, 0.09), 0.2, 0.5))
    B.box((0, D / 2 - 0.4, h + 4.0), (14.0, 0.3, 7.0), LED())               # LED wall at the back
    for x in [-W / 2 + 2 + 2.6 * i for i in range(7)]:
        B.box((x, -D / 2 + 0.6, 10.1), (0.5, 0.4, 0.35), BLACK())
        B.card((x, -D / 2 + 0.39, 10.1), (0, -1, 0), (0, 0, 1), 0.35, 0.25, LAMP())
    export("MG_Stage", [B.finish("MG_Stage")])


def drag_fence():
    reset()
    B = Builder()
    s = STEEL()
    for x in (-5.0, 5.0):
        B.tube([(x, 0, 0), (x, 0, 2.4)], [0.035, 0.035], s, 6)
    B.tube([(-5, 0, 2.4), (5, 0, 2.4)], [0.025, 0.025], s, 5, cap=False)
    screen = mat("M_Windscreen", (0.02, 0.02, 0.02), 0.0, 0.85)
    B.face([(-5, -0.02, 0.05), (5, -0.02, 0.05), (5, -0.02, 2.35), (-5, -0.02, 2.35)], screen, [(0, 0), (5, 0), (5, 1.2), (0, 1.2)])
    B.face([(5, 0.02, 0.05), (-5, 0.02, 0.05), (-5, 0.02, 2.35), (5, 0.02, 2.35)], screen, [(0, 0), (5, 0), (5, 1.2), (0, 1.2)])
    export("MG_DragFence", [B.finish("MG_DragFence")])


def light_tower():
    reset()
    B = Builder()
    y = mat("M_TrailerYellow", (0.85, 0.6, 0.05), 0.3, 0.5)
    B.box((0, 0, 0.9), (1.5, 3.2, 1.1), y)
    for dx in (-0.8, 0.8):
        B.cyl((dx, 0.6, 0.0), 0.15, 0.32, BLACK(), 10)
    B.tube([(0, 0.8, 1.4), (0, 0.8, 8.5)], [0.08, 0.06], M_GALV := mat("M_Galvanized", (0.62, 0.63, 0.64), 0.9, 0.38), 8)
    B.box((0, 0.8, 8.6), (1.6, 0.1, 0.1), M_GALV)
    for dx in (-0.6, -0.2, 0.2, 0.6):
        B.box((dx, 0.75, 8.85), (0.32, 0.18, 0.4), BLACK())
        B.card((dx, 0.65, 8.85), (0, -1, 0), (0, 0, 1), 0.26, 0.32, LAMP())
    export("MG_LightTower", [B.finish("MG_LightTower")])


def gantry():
    reset()
    B = Builder()
    s = mat("M_GantrySteel", (0.12, 0.13, 0.14), 0.7, 0.45)
    S, H = 16.0, 16.0
    for x in (-S / 2, S / 2):
        for y in (-S / 2, S / 2):
            B.tube([(x, y, 0), (x, y, H)], [0.3, 0.3], s, 8, cap=False)
    for z in (H, H - 4.0):
        for a, b in (((-S / 2, -S / 2), (S / 2, -S / 2)), ((S / 2, -S / 2), (S / 2, S / 2)), ((S / 2, S / 2), (-S / 2, S / 2)), ((-S / 2, S / 2), (-S / 2, -S / 2))):
            B.tube([(a[0], a[1], z), (b[0], b[1], z)], [0.2, 0.2], s, 8, cap=False)
    for k in range(-3, 4):                      # cable web overhead
        B.tube([(-S / 2, k * 2.0, H), (S / 2, -k * 2.0, H)], [0.02, 0.02], s, 4, cap=False)
    tarp = mat("M_TarpLight", (0.85, 0.82, 0.78), 0.0, 0.8)
    for side in range(4):                       # tarps sagging from the top ring down inside each face
        for k in range(4):
            u0, u1 = -S / 2 + k * S / 4, -S / 2 + (k + 1) * S / 4
            sag = 1.2 + 0.4 * math.sin(k + side)
            def P(u, z, inset):
                v = S / 2 - inset
                return {0: (u, -v, z), 1: (v, u, z), 2: (-u, v, z), 3: (-v, -u, z)}[side]
            B.face([P(u0, 1.0, sag), P(u1, 1.0, sag), P(u1, H - 0.3, 0.3), P(u0, H - 0.3, 0.3)], tarp, [(0, 0), (1, 0), (1, 4), (0, 4)])
            B.face([P(u1, 1.0, sag), P(u0, 1.0, sag), P(u0, H - 0.3, 0.3), P(u1, H - 0.3, 0.3)], tarp, [(0, 0), (1, 0), (1, 4), (0, 4)])
    export("MG_Gantry", [B.finish("MG_Gantry")])


def flare_stack():
    reset()
    B = Builder()
    s = mat("M_StackSteel", (0.42, 0.40, 0.38), 0.8, 0.5)
    B.box((0, 0, 0.4), (3.0, 3.0, 0.8), mat("M_Concrete", (0.6, 0.6, 0.58), 0.0, 0.85))
    B.tube([(0, 0, 0.8), (0, 0, 28.0)], [0.6, 0.4], s, 12)
    for z in (9.0, 18.0, 26.5):
        B.cyl((0, 0, z), 0.08, 1.4, s, 16)
    B.tube([(0.55, -0.3, 0.8), (0.55, -0.3, 27.0)], [0.03, 0.03], s, 4, cap=False)
    B.cyl((0, 0, 28.0), 0.6, 0.45, mat("M_StackTip", (0.15, 0.12, 0.1), 0.6, 0.6), 12)
    export("MG_FlareStack", [B.finish("MG_FlareStack")])


def show():
    """The reveal-night show pieces from Kenny's overhead shot and approach photo:
    MG_LanePost   a 6 m run of low black stage truss with a 4.5 m red LED pole at its start (the kickflip lane)
    MG_ShowWall   a 10 m module of the long barrier wall between the ramp and the line-up: black wall 1.3 m high,
                  red LED strip along its face, three uplight fixtures on top, red-lit tiered seating behind it
    MG_LineStripe a 10 m x 0.3 m white painted stripe (the X lines across the lot)
    MG_LEDStrip   a 10 m x 0.12 m red LED strip flush on the ground (in front of and beside the line-up)"""
    reset()
    B = Builder()
    blk = BLACK()
    red = mat("M_LEDRed", (1.0, 0.03, 0.02), 0.0, 0.3)
    # truss: two chords and diagonals, 6 m along -Y, 0.6 m tall
    for z in (0.15, 0.75):
        for x in (-0.15, 0.15):
            B.tube([(x, 0.0, z), (x, -6.0, z)], [0.025, 0.025], blk, 6, cap=False)
    for k in range(12):
        y0, y1 = -k * 0.5, -(k + 1) * 0.5
        B.tube([(0.0, y0, 0.15), (0.0, y1, 0.75)], [0.015, 0.015], blk, 4, cap=False)
    B.box((0, -0.15, 0.05), (0.5, 0.5, 0.1), blk)
    B.tube([(0.0, -0.15, 0.1), (0.0, -0.15, 4.6)], [0.05, 0.05], red, 8)
    export("MG_LanePost", [B.finish("MG_LanePost")])
    reset()
    B = Builder()
    blk = BLACK()
    red = mat("M_LEDRed", (1.0, 0.03, 0.02), 0.0, 0.3)
    seat = mat("M_SeatRed", (0.35, 0.02, 0.02), 0.0, 0.6)
    B.box((0, -5.0, 0.65), (0.5, 10.0, 1.3), blk)
    B.box((-0.27, -5.0, 1.1), (0.04, 10.0, 0.08), red)               # LED strip on the face (the -X side faces the lot)
    for k in range(3):
        y = -1.7 - k * 3.3
        B.box((0.0, y, 1.42), (0.35, 0.35, 0.24), blk)
        B.cyl((0.0, y, 1.54), 0.11, 0.06, LAMP(), 10)
    for t in range(4):                                                # tiered seating behind (+X)
        B.box((1.2 + t * 0.9, -5.0, 0.35 + t * 0.45), (0.9, 9.8, 0.7 + t * 0.9), seat)
    export("MG_ShowWall", [B.finish("MG_ShowWall")])
    reset()
    B = Builder()
    B.box((0, -5.0, 0.005), (0.3, 10.0, 0.01), mat("M_LinePaint", (0.85, 0.85, 0.82), 0.0, 0.6))
    export("MG_LineStripe", [B.finish("MG_LineStripe")])
    reset()
    B = Builder()
    B.box((0, -5.0, 0.01), (0.12, 10.0, 0.02), mat("M_LEDRed", (1.0, 0.03, 0.02), 0.0, 0.3))
    export("MG_LEDStrip", [B.finish("MG_LEDStrip")])


ONLY = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []      # e.g. -- ramp gantry
for fn in (ramp, stage, drag_fence, light_tower, gantry, flare_stack, fleet, night, show):
    if not ONLY or fn.__name__ in ONLY:
        fn()
print("ALL DONE")


def water_tower():
    """Elevated spheroid tank on four legs, ~40 m to the top (like the one behind the drag strip)."""
    reset()
    B = Builder()
    paint = mat("M_TowerWhite", (0.86, 0.87, 0.88), 0.3, 0.45)
    steel = mat("M_ScaffoldSteel", (0.55, 0.56, 0.58), 0.85, 0.4)
    H, R = 30.0, 7.0
    for k in range(4):
        a = math.radians(45 + 90 * k)
        B.tube([(math.cos(a) * 6.0, math.sin(a) * 6.0, 0), (math.cos(a) * 3.5, math.sin(a) * 3.5, H)], [0.35, 0.3], paint, 8, cap=False)
    for z in (8.0, 16.0, 24.0):
        f = 6.0 - (6.0 - 3.5) * z / H
        ring = [(math.cos(math.radians(45 + 90 * k)) * f, math.sin(math.radians(45 + 90 * k)) * f, z) for k in range(5)]
        B.tube(ring, [0.12] * 5, steel, 6, cap=False)
    B.cyl((0, 0, 0), H + 2.0, 0.9, paint, 12)                     # riser pipe
    # spheroid tank: stacked rings
    rings = 12
    prev = None
    for i in range(rings + 1):
        phi = math.pi * i / rings
        z = H + 4.5 - 4.5 * math.cos(phi)
        r = R * math.sin(phi)
        ring = [(r * math.cos(2 * math.pi * k / 24), r * math.sin(2 * math.pi * k / 24), z) for k in range(25)]
        if prev:
            for k in range(24):
                B.face([prev[k], prev[k + 1], ring[k + 1], ring[k]][::-1], paint)
        prev = ring
    B.cyl((0, 0, H + 4.4), 0.3, R * 1.05, steel, 24, top=False)     # catwalk ring
    export("MG_WaterTower", [B.finish("MG_WaterTower")])


def pylon():
    """Lattice transmission tower ~32 m, crossarms for three conductors each side."""
    reset()
    B = Builder()
    s = mat("M_Galvanized", (0.62, 0.63, 0.64), 0.9, 0.38)
    H = 32.0
    base, top = 4.0, 1.2
    corners = lambda z: [(sx * (base + (top - base) * z / H) / 2, sy * (base + (top - base) * z / H) / 2, z) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    for k in range(4):
        B.tube([corners(0)[k], corners(H)[k]], [0.1, 0.06], s, 4, cap=False)
    for z0 in [2.0 * i for i in range(16)]:
        c0, c1 = corners(z0), corners(z0 + 2.0)
        for k in range(4):
            B.tube([c0[k], c1[(k + 1) % 4]], [0.035, 0.035], s, 4, cap=False)
            B.tube([c0[(k + 1) % 4], c1[k]], [0.035, 0.035], s, 4, cap=False)
    for z, L in ((H - 1.0, 5.0), (H - 6.0, 6.5), (H - 11.0, 5.5)):
        B.tube([(-L, 0, z), (L, 0, z)], [0.08, 0.08], s, 4, cap=False)
        for sx in (-1, 1):
            B.tube([(sx * L, 0, z), (sx * L, 0, z - 1.6)], [0.05, 0.05], mat("M_Insulator", (0.35, 0.25, 0.2), 0.0, 0.3), 6)
    export("MG_Pylon", [B.finish("MG_Pylon")])


def chain_link():
    """One 3 m bay of 2.2 m chain-link fence with barbed-wire arms (masked mesh texture)."""
    reset()
    B = Builder()
    g = mat("M_Galvanized", (0.62, 0.63, 0.64), 0.9, 0.38)
    for x in (-1.5, 1.5):
        B.tube([(x, 0, 0), (x, 0, 2.2)], [0.03, 0.03], g, 6)
        B.tube([(x, 0, 2.2), (x, 0.35, 2.55)], [0.015, 0.015], g, 4, cap=False)
    B.tube([(-1.5, 0, 2.15), (1.5, 0, 2.15)], [0.02, 0.02], g, 5, cap=False)
    for k in range(3):
        B.tube([(-1.5, 0.12 * (k + 1), 2.3 + 0.08 * k), (1.5, 0.12 * (k + 1), 2.3 + 0.08 * k)], [0.006, 0.006], g, 3, cap=False)
    mesh = mat("M_ChainLink", (0.7, 0.7, 0.72), 0.9, 0.4)
    B.face([(-1.5, 0, 0.05), (1.5, 0, 0.05), (1.5, 0, 2.15), (-1.5, 0, 2.15)], mesh, [(0, 0), (6, 0), (6, 4.3), (0, 4.3)])
    export("MG_ChainLink", [B.finish("MG_ChainLink")])


for fn in (water_tower, pylon, chain_link):
    if not ONLY or fn.__name__ in ONLY:
        fn()
print("EXTRA DONE")
