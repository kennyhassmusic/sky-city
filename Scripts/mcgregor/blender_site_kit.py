"""McGregor test-site structures, modelled in Blender (headless) and exported as GLB (one per asset), so the McGregor maps
show the real facility instead of generic OSM extrusions. Same conventions as blender_mcgregor_kit.py (and the street
kit it borrows Builder / mat / export from): metres, standing on z = 0, the "front" toward Blender -Y (site_ue.py turns
it to the placement bearing with KIT_FRONT), material slots M_Site* mapped to MI_Site* in Unreal.

Shapes come from Kenny's reference photos (SourceArt/Reference/McGregor), the research agent's photos
(SourceArt/Reference/McGregor/research), the NAIP aerial on the terrain and the OSM footprints; see
Saved/McGregor/site_features.json and the hand-over note mcgregor-site-2026-10-20.md. No names, logos or signage.

  SK_StructuralStand  blue lattice tower 10 x 10 m, 50 m, platforms, hoist jib, white tank article inside (Kenny's photo)
  SK_Tripod           the old tripod first-stage stand: three banded concrete columns, triangular cap at 30-34 m, cross
                      beams, rusty steel flame deflector exiting -Y, blue lattice access tower on top to 67 m
                      (the 220 ft vertical stand of March 2000), blue stair tower up one leg
  SK_FSStand          current first-stage stand over its trench: concrete piers, grey steel thrust tower to 36 m,
                      deck over the sump, a plain white stage (test article) standing in it, engines down
  SK_FSTrench         concrete liner for the first-stage flame trench (fitted to the USGS DEM pit): 16 m deep sump,
                      ramp floor rising 60 m to the south, vertical walls, apron covering the terrain's slope
  SK_WaterTower(Small) plain white multi-leg elevated tank, 84 m (central) / 44 m (east), 16 m tank (no logo)
  SK_TankV / SK_TankBig / SK_TankOpen / SK_TankH / SK_TubeBank   white vertical cryo tank (3.4 x 12 m unit), big flat-bottom
                      water tank (20 x 10 m unit), horizontal tank on saddles (10 m x 3 m unit, long axis = Blender Y),
                      tube-trailer bundle
  SK_EngineStandV     vertical engine stand: concrete flame bucket, grey steel frame 6 x 6 x 18 m, engine, run tank
  SK_EngineStandH     horizontal engine stand: concrete thrust wall, black steel test cell, engine firing -Y, scorched pad
  SK_Hangar           large white hangar 30 x 60 x 16.5 m (gable roof, big door on the -Y end, blue trim); scaled per site
  SK_Shop             white office/shop building 20 x 40 x 8 m with window bands, roll-up doors, rooftop units
  SK_Blockhouse       hardened concrete control building 12 x 34 m with earth berms on three sides, antenna mast
  SK_Crane            red crawler crane, 48 m lattice boom raised toward -Y
  SK_StageDebris      a scorched white stage section lying on blocks (the boneyard)
  SK_Car_<Body>_<Colour>  generic parked cars (Sedan / SUV / Pickup x White / Silver / Black / Grey / Red / Blue)
  SK_StallLine        5.5 m parking stall stripe
  (mcgregor-tests agent, 20 Oct 2026; jobs `testhw` and `tests`)
  SK_RaptorEngine     generic methalox engine hanging nozzle-down from its gimbal (3.1 m, 1.3 m exit)
  SK_RaptorCell       the 2025 black vertical engine cells over the Raptor North / South trench heads
  SK_VertStand(S2)    steel stand over a trench head (2021 vertical Raptor stand; S2: no run tank, holds the stage)
  SK_UpperStage       generic upper stage with its vacuum nozzle (second-stage stand)
  SK_DisplayBooster   flown-looking first stage on deployed legs on a round plinth (the hangar circle)
  SK_PipeRack / SK_TankTall / SK_RVacTrailer   rack segment, 28 m vertical tank, vacuum engine on a trailer
  SK_T_*              trench liners, blast aprons, caliche pads and scorch skins from Saved/McGregor/tests_meshes.json
                      (Scripts/mcgregor/tests_layout.py, run through site_layout.py): absolute heights, placed bearing 180
Run: /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/mcgregor/blender_site_kit.py [-- structural tripod ...]
Output: SourceArt/McGregor/site/<name>.glb
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
spec_path = os.path.join(ROOT, "Scripts", "streets", "blender_street_kit.py")
src = open(spec_path).read().split("# ------------------------------------------------------------------ props")[0]
K = {"__file__": spec_path}
exec(compile(src, "kit_helpers", "exec"), K)
Builder, mat, export = K["Builder"], K["mat"], K["export"]
K["OUT"] = os.path.join(ROOT, "SourceArt", "McGregor", "site")
os.makedirs(K["OUT"], exist_ok=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    K["MATS"].clear()


BLUE = lambda: mat("M_SiteBlue", (0.03, 0.12, 0.42), 0.55, 0.45)
WHITE = lambda: mat("M_SiteWhite", (0.86, 0.87, 0.87), 0.1, 0.45)
ROOF = lambda: mat("M_SiteRoof", (0.48, 0.50, 0.52), 0.4, 0.5)
CONC = lambda: mat("M_SiteConcrete", (0.62, 0.59, 0.54), 0.0, 0.85)
CONCD = lambda: mat("M_SiteConcreteDark", (0.22, 0.21, 0.2), 0.0, 0.9)
STEEL = lambda: mat("M_SiteSteel", (0.36, 0.37, 0.39), 0.7, 0.5)
RUST = lambda: mat("M_SiteRust", (0.28, 0.13, 0.07), 0.3, 0.75)
DARK = lambda: mat("M_SiteDark", (0.035, 0.035, 0.04), 0.0, 0.8)
GLASS = lambda: mat("M_SiteGlass", (0.04, 0.06, 0.08), 0.2, 0.12)
RED = lambda: mat("M_SiteRed", (0.55, 0.04, 0.03), 0.3, 0.45)
YEL = lambda: mat("M_SiteYellow", (0.8, 0.55, 0.04), 0.3, 0.45)
GRATE = lambda: mat("M_SiteGrate", (0.22, 0.22, 0.23), 0.6, 0.6)
BERM = lambda: mat("M_SiteBerm", (0.42, 0.38, 0.27), 0.0, 0.95)
BLACK = lambda: mat("M_SiteBlack", (0.05, 0.05, 0.055), 0.5, 0.5)
DOOR = lambda: mat("M_SiteDoor", (0.62, 0.63, 0.64), 0.4, 0.5)


# ------------------------------------------------------------------ helpers
def fo(B, pts, m, want, uvs=None):
    """Add a face whose normal points along `want` (flips the winding if needed; Unreal draws one side only)."""
    n = Vector((0.0, 0.0, 0.0))
    for i in range(len(pts)):
        a, b = Vector(pts[i]), Vector(pts[(i + 1) % len(pts)])
        n += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
    if n.dot(Vector(want)) < 0:
        pts = pts[::-1]
        uvs = uvs[::-1] if uvs else None
    return B.face(pts, m, uvs)


def dedupe(prof):
    out = [prof[0]]
    for p in prof[1:]:
        if abs(p[0] - out[-1][0]) > 1e-6 or abs(p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    return out


def lattice(B, x0, y0, x1, y1, z0, z1, panel, m, col=0.3, brace=0.12, faces=(0, 1, 2, 3), girts=True, sides=4):
    """Square / rectangular lattice tower between (x0, y0) and (x1, y1), z0..z1: 4 columns, girts every panel,
    one diagonal per panel per face (alternating = K/X look from afar)."""
    cs = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for x, y in cs:
        B.tube([(x, y, z0), (x, y, z1)], [col, col], m, sides, cap=False)
    n = max(1, int(round((z1 - z0) / panel)))
    for i in range(n + 1):
        z = z0 + (z1 - z0) * i / n
        for f in faces:
            a, b = cs[f], cs[(f + 1) % 4]
            if girts:
                B.tube([(a[0], a[1], z), (b[0], b[1], z)], [brace, brace], m, sides, cap=False)
            if i < n:
                zz = z0 + (z1 - z0) * (i + 1) / n
                p, q = (a, b) if (i + f) % 2 else (b, a)
                B.tube([(p[0], p[1], z), (q[0], q[1], zz)], [brace * 0.8, brace * 0.8], m, sides, cap=False)


def deck(B, x0, y0, x1, y1, z, m, t=0.3):
    B.box(((x0 + x1) / 2, (y0 + y1) / 2, z - t / 2), (abs(x1 - x0), abs(y1 - y0), t), m)


def rail(B, x0, y0, x1, y1, z, m, h=1.1):
    for (ax, ay), (bx, by) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        B.tube([(ax, ay, z + h), (bx, by, z + h)], [0.03, 0.03], m, 4, cap=False)


def revolve(B, prof, m, n=20, c=(0, 0, 0)):
    """Surface of revolution about the z axis from a (r, z) profile (bottom to top)."""
    rings = []
    for r, z in dedupe(prof):
        rings.append([(c[0] + r * math.cos(2 * math.pi * k / n), c[1] + r * math.sin(2 * math.pi * k / n), c[2] + z) for k in range(n + 1)])
    for (ra, _), (rb, _), a, b in zip(dedupe(prof), dedupe(prof)[1:], rings, rings[1:]):
        for k in range(n):
            if ra < 1e-6 and rb < 1e-6:
                continue
            if ra < 1e-6:                                   # fan from a pole: triangles, no zero-area faces
                B.face([a[k], b[k + 1], b[k]], m)
            elif rb < 1e-6:
                B.face([a[k], a[k + 1], b[k]], m)
            else:
                B.face([a[k], a[k + 1], b[k + 1], b[k]], m, [(k / n, a[k][2] * 0.2), ((k + 1) / n, a[k][2] * 0.2), ((k + 1) / n, b[k][2] * 0.2), (k / n, b[k][2] * 0.2)])


def dome_prof(r, z0, h, n=5, up=True):
    """Elliptical head profile from the rim (r, z0) to the pole."""
    pts = []
    for i in range(n + 1):
        t = math.pi / 2 * i / n
        pts.append((max(r * math.cos(t), 0.0), z0 + (h * math.sin(t) if up else -h * math.sin(t))))
    return pts


def htank(B, cx, cy, cz, L, r, m, axis="y", n=14):
    """Horizontal tank with elliptical heads, axis along y (or x)."""
    hd = r * 0.5
    prof = dome_prof(r, 0.0, hd, 4, up=False)[::-1] + [(r, 0.0), (r, L - 2 * hd)] + dome_prof(r, L - 2 * hd, hd, 4, up=True)[1:]
    # build along local z then rotate to the axis
    B2 = []
    for i, (rr, zz) in enumerate(dedupe(prof)):
        B2.append((rr, zz - (L - 2 * hd) / 2))
    rings = []
    for rr, zz in B2:
        ring = []
        for k in range(n + 1):
            a = 2 * math.pi * k / n
            u, w = rr * math.cos(a), rr * math.sin(a)
            if axis == "y":
                ring.append((cx + u, cy + zz, cz + w))
            else:
                ring.append((cx + zz, cy + u, cz + w))
        rings.append(ring)
    radii = [rr for rr, _ in B2]
    for ra, rb, a, b in zip(radii, radii[1:], rings, rings[1:]):
        for k in range(n):
            q = [a[k], b[k + 1], b[k]] if ra < 1e-6 else [a[k], a[k + 1], b[k]] if rb < 1e-6 else [a[k], a[k + 1], b[k + 1], b[k]]
            B.face(q[::-1] if axis == "y" else q, m)


def bell(B, c, r_throat, r_exit, L, m, down=True, axis="z", n=12):
    """Engine nozzle (open cone) from the throat at c, length L, pointing down (or along -y)."""
    prof = [(r_throat * 1.4, 0.0), (r_throat, L * 0.08)] + [(r_throat + (r_exit - r_throat) * (t / 6) ** 0.7, L * (0.08 + 0.92 * t / 6)) for t in range(1, 7)]
    for (ra, za), (rb, zb) in zip(prof, prof[1:]):
        for k in range(n):
            a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
            def P(r, z, a):
                u, w = r * math.cos(a), r * math.sin(a)
                if axis == "z":
                    return (c[0] + u, c[1] + w, c[2] - z if down else c[2] + z)
                return (c[0] + u, c[1] - z, c[2] + w)
            q = [P(ra, za, a0), P(ra, za, a1), P(rb, zb, a1), P(rb, zb, a0)]
            B.face(q, m)
            B.face(q[::-1], m)


# ------------------------------------------------------------------ test stands
def structural():
    """Falcon 9 structural test stand: tall blue lattice tower (Kenny's aerial: the blue tower between the rocket and the
    tripod), base pad, platforms every 12 m, a hoist jib at the top, a white tank article in the lower bay."""
    reset()
    B = Builder()
    b, g = BLUE(), GRATE()
    H, S = 50.0, 5.0
    B.box((0, 0, 0.5), (14.0, 14.0, 1.0), CONC())
    lattice(B, -S, -S, S, S, 1.0, H, 3.5, b, col=0.34, brace=0.14)
    lattice(B, -S, -S, S, S, 1.0, H, 7.0, b, col=0.01, brace=0.1, girts=False, faces=(1, 3))    # second diagonal set: X bracing
    for z in (13.0, 25.0, 37.0, H):
        deck(B, -S - 0.6, -S - 0.6, S + 0.6, S + 0.6, z, g)
        rail(B, -S - 0.6, -S - 0.6, S + 0.6, S + 0.6, z, b)
    B.box((0, 0, H + 1.6), (5.0, 5.0, 3.2), WHITE())                     # top shed
    B.tube([(0, S, H + 3.2), (0, S + 9.0, H + 3.2)], [0.3, 0.3], b, 4, cap=False)        # hoist jib (toward +Y)
    B.tube([(0, S, H + 5.5), (0, S + 9.0, H + 3.4)], [0.08, 0.08], b, 4, cap=False)
    B.tube([(0, S + 8.5, H + 3.0), (0, S + 8.5, H - 8.0)], [0.03, 0.03], STEEL(), 4, cap=False)
    revolve(B, [(0.0, 1.0), (1.85, 1.0), (1.85, 21.0)] + dome_prof(1.85, 21.0, 1.0, 4)[1:], WHITE(), 16)      # tank article
    # stair tower on the -Y face
    lattice(B, -1.5, -S - 3.0, 1.5, -S, 1.0, H, 4.0, b, col=0.12, brace=0.06, faces=(0, 1, 3))
    for i in range(int(H / 3.0)):
        z = 1.0 + 3.0 * i
        x0, x1 = (-1.3, 1.3) if i % 2 else (1.3, -1.3)
        B.tube([(x0, -S - 1.5, z), (x1, -S - 1.5, z + 3.0)], [0.25, 0.25], g, 4, cap=False)
    export("SK_StructuralStand", [B.finish("SK_StructuralStand")])


def tripod():
    """The old tripod first-stage stand (Beal Aerospace, March 2000: '220-foot-tall vertical-fire stand'), from Kenny's
    aerial and NSF's 2019 close-up: three round banded concrete columns, a triangular concrete cap 4 m thick at 30 m,
    two levels of cross beams, a rusty steel flame deflector between the legs opening toward -Y, a blue lattice access
    tower on the cap to 67 m and a blue stair tower up the +X leg."""
    reset()
    B = Builder()
    c, cd, b, g = mat("M_SiteConcreteTan", (0.45, 0.38, 0.30), 0.0, 0.85), CONCD(), BLUE(), GRATE()     # weathered tan concrete (Kenny's aerial)
    R0, R1, ZC, TC = 14.0, 11.0, 30.0, 4.0
    angs = [math.radians(a) for a in (90.0, 210.0, 330.0)]           # one leg at the back (+Y), two at the front
    base = [(R0 * math.cos(a), R0 * math.sin(a)) for a in angs]
    top = [(R1 * math.cos(a), R1 * math.sin(a)) for a in angs]
    for (bx, by), (tx, ty) in zip(base, top):
        B.tube([(bx, by, 0.0), (tx, ty, ZC + 0.5)], [2.1, 2.0], c, 16, cap=False)
        for k in range(1, 10):                                      # the lift bands of the slip-formed columns
            t = k / 10.0
            px, py, pz = bx + (tx - bx) * t, by + (ty - by) * t, (ZC + 0.5) * t
            B.tube([(px, py, pz - 0.18), (px + (tx - bx) * 0.012, py + (ty - by) * 0.012, pz + 0.18)], [2.13, 2.13], cd, 16, cap=False)
        B.box((bx, by, 0.4), (5.5, 5.5, 0.8), c)                     # footings
    for z in (11.0, 21.0):                                           # cross beams
        t = z / (ZC + 0.5)
        pts = [(bx + (tx - bx) * t, by + (ty - by) * t) for (bx, by), (tx, ty) in zip(base, top)]
        for k in range(3):
            if k == 1:                                               # leave the front (-Y) open for the deflector
                continue
            (ax, ay), (qx, qy) = pts[k], pts[(k + 1) % 3]
            B.tube([(ax, ay, z), (qx, qy, z)], [0.8, 0.8], c, 4, cap=False)
        (ax, ay), (qx, qy) = pts[1], pts[2]
        B.tube([(ax, ay, z + 6.0), (qx, qy, z + 6.0)], [0.6, 0.6], c, 4, cap=False)
    # triangular cap with chamfered corners
    tri = []
    for a in angs:
        for d in (-18.0, 18.0):
            r = R1 + 3.2
            tri.append((r * math.cos(a + math.radians(d)), r * math.sin(a + math.radians(d))))
    tri = tri[1:] + tri[:1]
    for z0, z1 in ((ZC, ZC + TC),):
        B.face([(x, y, z1) for x, y in tri], c)
        B.face([(x, y, z0) for x, y in tri][::-1], c)
        for k in range(len(tri)):
            (ax, ay), (qx, qy) = tri[k], tri[(k + 1) % len(tri)]
            B.face([(ax, ay, z0), (qx, qy, z0), (qx, qy, z1), (ax, ay, z1)], c)
    rail(B, -6, -6, 6, 6, ZC + TC, b)
    # flame deflector: a curved rusty chute from under the cap, down and out to the front, with side cheeks
    rs = RUST()
    W = 9.0
    prof = [(1.5 - 13.0 * (1 - math.cos(math.radians(90.0 * i / 8))), 1.0 + 21.0 * (1 - math.sin(math.radians(90.0 * i / 8)))) for i in range(9)]
    for (y0, z0), (y1, z1) in zip(prof, prof[1:]):
        q = [(-W / 2, y0, z0), (W / 2, y0, z0), (W / 2, y1, z1), (-W / 2, y1, z1)]
        B.face(q, rs)
        B.face(q[::-1], rs)
    for x in (-W / 2, W / 2):
        pts = [(x, y, z) for y, z in prof] + [(x, prof[-1][0], 0.0), (x, prof[0][0], 0.0)]
        for k in range(len(prof) - 1):
            q = [(x, prof[k][0], prof[k][1]), (x, prof[k + 1][0], prof[k + 1][1]), (x, prof[k + 1][0], 0.0), (x, prof[k][0], 0.0)]
            B.face(q, rs)
            B.face(q[::-1], rs)
        for k in range(0, len(prof), 2):                              # stiffener ribs
            B.tube([(x * 1.02, prof[k][0], prof[k][1]), (x * 1.02, prof[k][0], 0.0)], [0.15, 0.15], rs, 4, cap=False)
    B.box((0, -6.0, 0.15), (16.0, 22.0, 0.3), cd)                     # scorched apron in front of the chute
    # blue access tower on the cap, and a stair tower up the +X front leg
    lattice(B, -3.5, -3.5, 3.5, 3.5, ZC + TC, 67.0, 3.6, b, col=0.28, brace=0.11)
    for z in (ZC + TC + 11.0, ZC + TC + 22.0, 67.0):
        deck(B, -4.2, -4.2, 4.2, 4.2, z, g)
        rail(B, -4.2, -4.2, 4.2, 4.2, z, b)
    B.box((0, 0, 68.4), (5.0, 5.0, 2.8), WHITE())
    sx, sy = base[2]
    lattice(B, sx + 2.5, sy - 1.5, sx + 5.5, sy + 1.5, 0.0, ZC + TC, 3.4, b, col=0.12, brace=0.06)
    export("SK_Tripod", [B.finish("SK_Tripod")])


def fs_stand():
    """Current first-stage stand at the north end of its trench (Kenny's aerial; NSF 2021: the stage stands on a low
    concrete deck with white service huts and pipework, a thin galvanised lattice mast beside it; StratMap 2020: the
    deck is ~37 x 30 m north of the pit). Origin = the stage axis at rim level; the pit is toward -Y (south)."""
    reset()
    B = Builder()
    c, s, w = CONC(), STEEL(), WHITE()
    gv = mat("M_SiteGalv", (0.62, 0.63, 0.64), 0.9, 0.38)
    B.box((1.0, 13.0, 0.25), (30.0, 26.0, 0.5), c)                       # deck at ground level north of the sump
    for x in (-3.4, 3.4):
        B.box((x, -1.5, 0.6), (2.0, 4.0, 1.2), c)                        # mount piers over the sump
    B.box((0.0, -1.5, 1.35), (8.8, 3.0, 0.3), s)                         # thrust beam
    revolve(B, [(2.4, 1.2), (2.4, 2.0), (0.0, 2.0)], s, 20)              # hold-down ring
    revolve(B, [(1.83, 2.0), (1.83, 42.1)], w, 20)                       # the stage (test article): plain white
    revolve(B, [(1.83, 42.1), (1.86, 46.6), (0.0, 46.6)], mat("M_SiteInterstage", (0.32, 0.33, 0.35), 0.4, 0.5), 20)
    for k in range(9):                                                    # engines down into the sump
        if k == 8:
            x, y = 0.0, 0.0
        else:
            x, y = 1.2 * math.cos(2 * math.pi * k / 8), 1.2 * math.sin(2 * math.pi * k / 8)
        bell(B, (x, y, 1.9), 0.18, 0.46, 2.4, DARK(), n=10)
    for (x, y, sx, sy, h) in ((7.0, 4.0, 4.0, 6.0, 3.2), (11.5, 9.0, 4.0, 6.0, 3.2), (-6.0, 9.0, 3.0, 4.0, 2.8), (5.0, 14.0, 6.0, 3.0, 3.0)):
        B.box((x, y, 0.5 + h / 2), (sx, sy, h), w)                        # service huts
    for k, z in enumerate((1.6, 2.4, 3.2)):                               # pipe rack east
        B.tube([(2.5, 1.0 + 0.7 * k, z), (16.0, 1.0 + 0.7 * k, z), (40.0, 1.0 + 0.7 * k, z)], [0.25, 0.25, 0.25], s, 8, cap=False)
    for x in (18.0, 24.0, 30.0, 36.0):
        B.box((x, 1.7, 0.8), (0.3, 2.6, 1.6), s)
    for x in (16.0, 18.0, 20.0):                                          # vertical bottles
        revolve(B, [(0.0, 0.5), (0.8, 0.5), (0.8, 7.5)] + dome_prof(0.8, 7.5, 0.4, 3)[1:], w, 10, c=(x, 6.0, 0.0))
    lattice(B, -9.5, 1.0, -8.0, 2.5, 0.5, 72.0, 2.0, gv, col=0.07, brace=0.035)     # tall thin mast west of the stage
    rail(B, -14.0, 0.0, 16.0, 26.0, 0.5, YEL())
    export("SK_FSStand", [B.finish("SK_FSStand")])


# the first-stage trench in facility metres (StratMap 2020 rim + USGS DEM floor), relative to the north-wall origin
TRENCH_O = (-136.0, -575.0)
TRENCH_RIM = 23.3


def trench_east(y):          # bottom-of-slope lines from the DEM, facility y
    return -122.0 + max(0.0, (-584.0 - y)) * (10.0 / 68.0)


def trench_west(y):
    return -146.0 - max(0.0, (-584.0 - y)) * 0.5


def trench_floor(y):
    if y >= -590.0:
        return -15.9
    return min(0.0, -15.2 + (-590.0 - y) * 15.2 / 65.0)


def fs_trench():
    """Concrete liner for the first-stage flame trench (StratMap 2020 rim, USGS DEM floor): 16 m deep sump under the
    stage, floor ramping 65 m up to the south exit, the east wall nearly straight, the west wall flaring out (the pit
    is a skewed triangle opening south-south-west), vertical walls, a 7 m apron at ground level hiding the terrain's own
    2 m-DEM slopes. Origin = (-136, -575) in facility metres at rim level; placed with bearing 180 (no rotation)."""
    reset()
    B = Builder()
    c, cd = CONC(), CONCD()
    ox, oy = TRENCH_O
    ys = [-575.0, -580.0, -584.0, -590.0] + [-590.0 - 5.0 * k for k in range(1, 14)] + [-656.0]
    ys = sorted(set(ys), reverse=True)
    L = lambda x, y, z: (x - ox, y - oy, z)
    for y0, y1 in zip(ys, ys[1:]):
        e0, e1, w0, w1 = trench_east(y0), trench_east(y1), trench_west(y0), trench_west(y1)
        f0, f1 = trench_floor(y0), trench_floor(y1)
        m = cd if y0 > -615.0 else c
        fo(B, [L(w0, y0, f0), L(e0, y0, f0), L(e1, y1, f1), L(w1, y1, f1)], m, (0, 0, 1), [(w0 / 4, y0 / 4), (e0 / 4, y0 / 4), (e1 / 4, y1 / 4), (w1 / 4, y1 / 4)])
        for xa, xb, sgn in ((e0, e1, 1), (w0, w1, -1)):
            fo(B, [L(xa, y0, f0), L(xb, y1, f1), L(xb, y1, 0.3), L(xa, y0, 0.3)], m if f0 < -6 else c, (-sgn, 0, 0))
            fo(B, [L(xa, y0, 0.3), L(xb, y1, 0.3), L(xb + sgn * 7.0, y1, 0.3), L(xa + sgn * 7.0, y0, 0.3)], c, (0, 0, 1))
            fo(B, [L(xa + sgn * 7.0, y0, 0.3), L(xb + sgn * 7.0, y1, 0.3), L(xb + sgn * 7.0, y1, -0.8), L(xa + sgn * 7.0, y0, -0.8)], c, (sgn, 0, 0))
    e, w = trench_east(-575.0), trench_west(-575.0)
    fo(B, [L(w, -575.0, trench_floor(-575.0)), L(e, -575.0, trench_floor(-575.0)), L(e, -575.0, 0.3), L(w, -575.0, 0.3)], cd, (0, -1, 0))     # north wall
    fo(B, [L(w - 7.0, -575.0, 0.3), L(e + 7.0, -575.0, 0.3), L(e + 7.0, -566.0, 0.3), L(w - 7.0, -566.0, 0.3)], c, (0, 0, 1))                  # north apron
    for y in ys[::2]:                                                     # rail posts along the rim
        for x, sgn in ((trench_east(y), 1), (trench_west(y), -1)):
            B.tube([L(x + sgn * 0.5, y, 0.3), L(x + sgn * 0.5, y, 1.4)], [0.04, 0.04], YEL(), 4, cap=False)
    export("SK_FSTrench", [B.finish("SK_FSTrench")])


def engine_v():
    """Vertical engine stand (M1D vertical / stage-2 / Raptor vertical, scaled per site): concrete flame bucket with the
    exit toward -Y, grey steel frame 6 x 6 x 18 m with platforms, engine at the bottom, white run tank on top."""
    reset()
    B = Builder()
    c, cd, s, g = CONC(), CONCD(), STEEL(), GRATE()
    B.box((0, 3.5, 2.0), (10.0, 7.0, 4.0), c)                          # back block
    for x in (-4.0, 4.0):
        B.box((x, -1.0, 2.0), (2.0, 4.0, 4.0), c)                       # bucket cheeks
    B.face([(-3.0, 0.0, 4.0), (3.0, 0.0, 4.0), (3.0, -6.0, 0.05), (-3.0, -6.0, 0.05)][::-1], cd)      # deflector slope
    B.box((0, -10.0, 0.06), (10.0, 14.0, 0.12), cd)                    # scorched apron
    lattice(B, -3.0, -3.0, 3.0, 3.0, 4.0, 22.0, 3.0, s, col=0.25, brace=0.1)
    for z in (10.0, 16.0, 22.0):
        deck(B, -3.4, -3.4, 3.4, 3.4, z, g)
        rail(B, -3.4, -3.4, 3.4, 3.4, z, s)
    bell(B, (0.0, 0.0, 6.5), 0.22, 0.75, 2.4, DARK(), n=12)
    revolve(B, [(0.35, 6.5), (0.35, 9.0), (0.8, 9.0), (0.8, 10.0)], s, 10)
    revolve(B, [(0.0, 16.0), (1.6, 16.0), (1.6, 21.0)] + dome_prof(1.6, 21.0, 0.8, 3)[1:], WHITE(), 14)
    B.box((0, 0, 22.8), (6.4, 6.4, 0.2), ROOF())
    export("SK_EngineStandV", [B.finish("SK_EngineStandV")])


def engine_h():
    """Horizontal engine stand (M1D / Raptor horizontal): heavy concrete thrust wall at the back (+Y), black steel test
    cell, engine firing toward -Y over a scorched pad, white run tanks behind the wall."""
    reset()
    B = Builder()
    c, cd, bk = CONC(), CONCD(), BLACK()
    B.box((0, 3.0, 4.0), (12.0, 4.0, 8.0), c)
    for x in (-6.5, 6.5):
        B.box((x, -3.0, 2.5), (1.0, 8.0, 5.0), c)                       # blast side walls
    lattice(B, -3.5, -6.0, 3.5, 1.0, 0.0, 7.0, 3.5, bk, col=0.25, brace=0.12)
    B.box((0, -2.5, 7.1), (7.6, 7.6, 0.25), bk)
    bell(B, (0.0, -3.0, 3.2), 0.3, 0.9, 3.0, DARK(), axis="y", n=12)
    revolve(B, [(0.5, 0.0), (0.5, 2.0)], STEEL(), 10, c=(0.0, -3.0, 2.2))
    B.box((0, -24.0, 0.06), (14.0, 34.0, 0.12), cd)
    for x in (-4.0, 0.0, 4.0):
        revolve(B, [(0.0, 0.0), (1.4, 0.0), (1.4, 10.0)] + dome_prof(1.4, 10.0, 0.7, 3)[1:], WHITE(), 12, c=(x, 8.0, 0.0))
    B.tube([(-6.5, 5.5, 3.0), (6.5, 5.5, 3.0)], [0.2, 0.2], STEEL(), 6, cap=False)
    export("SK_EngineStandH", [B.finish("SK_EngineStandH")])


def crane():
    """Red crawler crane (beside the first-stage stand in Kenny's photo): tracks, house, 48 m lattice boom at 68 deg
    toward -Y, hook."""
    reset()
    B = Builder()
    r, d = RED(), DARK()
    for x in (-2.4, 2.4):
        B.box((x, 0, 0.6), (1.2, 8.0, 1.2), d)
    B.box((0, 0.8, 2.4), (4.4, 6.5, 2.4), r)
    B.box((0, 3.6, 2.6), (4.6, 1.8, 2.8), mat("M_SiteSteel", (0.36, 0.37, 0.39), 0.7, 0.5))   # counterweight
    B.box((-1.6, -2.0, 3.6), (1.2, 1.8, 1.8), GLASS())                  # cab
    ang, L = math.radians(68.0), 48.0
    ux, uz = -math.cos(ang), math.sin(ang)                               # along -Y and up
    p0 = Vector((0, -1.5, 3.4))
    hw = 0.9
    for sx in (-hw, hw):
        for sz in (-hw, hw):
            a = p0 + Vector((sx, 0, sz))
            e = a + Vector((0, ux, uz)) * L
            B.tube([tuple(a), tuple(e)], [0.12, 0.12], r, 4, cap=False)
    n = 16
    for i in range(n):
        t0, t1 = L * i / n, L * (i + 1) / n
        c0 = p0 + Vector((0, ux, uz)) * t0
        c1 = p0 + Vector((0, ux, uz)) * t1
        for (sx0, sz0), (sx1, sz1) in (((-hw, -hw), (hw, -hw)), ((hw, -hw), (hw, hw)), ((hw, hw), (-hw, hw)), ((-hw, hw), (-hw, -hw))):
            a = c0 + Vector((sx0, 0, sz0))
            e = c1 + Vector((sx1, 0, sz1)) if i % 2 else c1 + Vector((sx0, 0, sz0))
            B.tube([tuple(a), tuple(c0 + Vector((sx1, 0, sz1)))], [0.05, 0.05], r, 4, cap=False)
            B.tube([tuple(a), tuple(c1 + Vector((sx1, 0, sz1)))], [0.05, 0.05], r, 4, cap=False)
    tip = p0 + Vector((0, ux, uz)) * L
    B.tube([tuple(tip), (tip.x, tip.y, 8.0)], [0.03, 0.03], d, 4, cap=False)
    B.box((tip.x, tip.y, 7.4), (0.8, 0.5, 1.2), YEL())
    B.tube([(0, 3.0, 5.0), tuple(tip)], [0.04, 0.04], d, 4, cap=False)        # pendant
    export("SK_Crane", [B.finish("SK_Crane")])


# ------------------------------------------------------------------ tanks
def water_tower(name="SK_WaterTower", ZT=70.0, R0=11.0, R1=6.4, step=10.0):
    """Plain white multi-leg elevated water tank (Kenny's aerial; NSF 2021), 16 m tank, no logo. SK_WaterTower: the central
    tower, ~84 m to the finial (research: shadow on StratMap Jan 2020 -> ~83 m, the tallest structure on site);
    SK_WaterTowerSmall: 44 m (the east tower by the stage-2 stand, typical 250,000 gal tank)."""
    reset()
    B = Builder()
    w, s = WHITE(), STEEL()
    n = 6
    legs = []
    for k in range(n):
        a = 2 * math.pi * (k + 0.5) / n
        legs.append(((R0 * math.cos(a), R0 * math.sin(a)), (R1 * math.cos(a), R1 * math.sin(a))))
        B.tube([(R0 * math.cos(a), R0 * math.sin(a), 0.0), (R1 * math.cos(a), R1 * math.sin(a), ZT + 2.0)], [0.5, 0.42], w, 10, cap=False)
        B.box((R0 * math.cos(a), R0 * math.sin(a), 0.3), (2.2, 2.2, 0.6), CONC())
    lv = [step * k for k in range(int(ZT / step) + 1)] + ([ZT] if ZT % step else [])
    for z0, z1 in zip(lv, lv[1:]):
        for k in range(n):
            (b0, t0), (b1, t1) = legs[k], legs[(k + 1) % n]
            f0, f1 = z0 / (ZT + 2.0), z1 / (ZT + 2.0)
            p = (b0[0] + (t0[0] - b0[0]) * f0, b0[1] + (t0[1] - b0[1]) * f0, z0)
            q = (b1[0] + (t1[0] - b1[0]) * f0, b1[1] + (t1[1] - b1[1]) * f0, z0)
            p1 = (b0[0] + (t0[0] - b0[0]) * f1, b0[1] + (t0[1] - b0[1]) * f1, z1)
            q1 = (b1[0] + (t1[0] - b1[0]) * f1, b1[1] + (t1[1] - b1[1]) * f1, z1)
            B.tube([p1, q1], [0.22, 0.22], w, 6, cap=False)
            B.tube([p, q1], [0.05, 0.05], s, 4, cap=False)
            B.tube([q, p1], [0.05, 0.05], s, 4, cap=False)
    B.cyl((0, 0, 0), ZT + 1.0, 0.9, w, 12, top=False)                   # riser
    RT = 8.0
    prof = [(0.0, ZT - 1.0)] + [(RT * math.sin(math.pi / 2 * i / 6), ZT + 3.0 - 4.0 * math.cos(math.pi / 2 * i / 6)) for i in range(1, 7)]
    prof += [(RT, ZT + 10.0), (RT * 0.92, ZT + 10.6), (1.0, ZT + 12.6), (0.0, ZT + 12.8)]
    revolve(B, prof, w, 28)
    B.cyl((0, 0, ZT + 2.9), 0.15, RT + 0.9, GRATE(), 28, top=True)        # balcony
    for k in range(24):
        a = 2 * math.pi * k / 24
        B.tube([((RT + 0.85) * math.cos(a), (RT + 0.85) * math.sin(a), ZT + 3.0), ((RT + 0.85) * math.cos(a), (RT + 0.85) * math.sin(a), ZT + 4.1)], [0.03, 0.03], s, 4, cap=False)
    B.tube([(0, 0, ZT + 12.8), (0, 0, ZT + 13.6)], [0.12, 0.08], w, 6)
    export(name, [B.finish(name)])


def water_towers():
    water_tower()
    water_tower("SK_WaterTowerSmall", 31.0, 8.0, 6.4, 8.0)


def tanks():
    reset()
    B = Builder()
    w, s = WHITE(), STEEL()
    revolve(B, [(0.0, 0.8), (1.7, 0.8), (1.7, 11.2)] + dome_prof(1.7, 11.2, 0.8, 4)[1:], w, 16)
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        B.tube([(1.5 * math.cos(a), 1.5 * math.sin(a), 0.0), (1.5 * math.cos(a), 1.5 * math.sin(a), 1.4)], [0.12, 0.12], s, 4, cap=False)
    B.tube([(1.75, 0, 0.8), (1.75, 0, 11.2)], [0.05, 0.05], s, 4, cap=False)        # ladder / line
    export("SK_TankV", [B.finish("SK_TankV")])
    reset()
    B = Builder()
    w = WHITE()
    revolve(B, [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 11.6)], w, 32)
    B.box((0, 0, 0.15), (21.0, 21.0, 0.3), CONC())
    export("SK_TankBig", [B.finish("SK_TankBig")])
    reset()
    B = Builder()                                                         # open-top water tank, dark water inside
    revolve(B, [(10.0, 0.0), (10.0, 5.0), (9.7, 5.0), (9.7, 0.3)], WHITE(), 32)
    revolve(B, [(0.0, 4.2), (9.7, 4.2)][::-1], mat("M_SiteWater", (0.02, 0.025, 0.03), 0.0, 0.08), 32)
    B.box((0, 0, 0.15), (21.0, 21.0, 0.3), CONC())
    export("SK_TankOpen", [B.finish("SK_TankOpen")])
    reset()
    B = Builder()
    w, c = WHITE(), CONC()
    htank(B, 0.0, 0.0, 2.3, 10.0, 1.5, w, "y")
    for y in (-3.2, 3.2):
        B.box((0, y, 0.5), (2.4, 0.5, 1.0), c)
        B.box((0, y, 1.1), (2.0, 0.3, 0.4), STEEL())
    export("SK_TankH", [B.finish("SK_TankH")])
    reset()
    B = Builder()
    w, s = WHITE(), STEEL()
    for i in range(3):
        for j in range(3):
            htank(B, -0.85 + 0.85 * i, 0.0, 0.9 + 0.85 * j, 11.0, 0.4, w, "y", n=8)
    B.box((0, -5.7, 1.75), (2.6, 0.3, 2.9), s)
    B.box((0, 5.7, 1.75), (2.6, 0.3, 2.9), s)
    B.box((0, 0, 0.25), (2.6, 12.0, 0.5), s)
    export("SK_TubeBank", [B.finish("SK_TubeBank")])


# ------------------------------------------------------------------ buildings
def hangar():
    """Large white hangar, 30 m wide (x) x 60 m long (y) x 13 m eaves / 16.5 m ridge, big door on the -Y gable, blue
    trim at the eaves and corners, personnel doors and a window band on the long walls (NSF 2019: white walls, grey
    roof, blue trim)."""
    reset()
    B = Builder()
    w, r, d, b, gl = WHITE(), ROOF(), DOOR(), BLUE(), GLASS()
    X, Y, E, RZ = 15.0, 30.0, 13.0, 16.5
    for sgn in (-1, 1):
        fo(B, [(sgn * X, -Y, 0), (sgn * X, Y, 0), (sgn * X, Y, E), (sgn * X, -Y, E)], w, (sgn, 0, 0), [(0, 0), (12, 0), (12, 3), (0, 3)])
        fo(B, [(-X, sgn * Y, 0), (X, sgn * Y, 0), (X, sgn * Y, E), (0, sgn * Y, RZ), (-X, sgn * Y, E)], w, (0, sgn, 0))
        fo(B, [(0, -Y - 0.6, RZ), (0, Y + 0.6, RZ), (sgn * (X + 0.6), Y + 0.6, E - 0.25), (sgn * (X + 0.6), -Y - 0.6, E - 0.25)], r, (sgn * 0.2, 0, 1),
           [(0, 0), (12, 0), (12, 3), (0, 3)])
        fo(B, [(0, -Y - 0.6, RZ - 0.2), (0, Y + 0.6, RZ - 0.2), (sgn * (X + 0.6), Y + 0.6, E - 0.45), (sgn * (X + 0.6), -Y - 0.6, E - 0.45)], r, (0, 0, -1))
        for yy in (-Y - 0.6, Y + 0.6):                                    # roof edge fascia
            fo(B, [(0, yy, RZ), (sgn * (X + 0.6), yy, E - 0.25), (sgn * (X + 0.6), yy, E - 0.45), (0, yy, RZ - 0.2)], b, (0, 1 if yy > 0 else -1, 0))
        B.box((sgn * (X + 0.03), 0, E - 0.4), (0.06, 2 * Y, 0.35), b)       # blue eave trim
        for k in range(6):                                                # personnel doors / windows
            yk = -Y + 6 + k * 10
            B.box((sgn * (X + 0.03), yk, 1.1), (0.06, 1.0, 2.2), d)
            B.box((sgn * (X + 0.03), yk + 3.5, 3.0), (0.06, 3.0, 1.0), gl)
    B.box((0, -Y - 0.06, 6.5), (24.0, 0.12, 13.0), d)                     # big door
    for k in range(1, 6):
        B.box((-12.0 + 4.0 * k, -Y - 0.14, 6.5), (0.12, 0.06, 13.0), ROOF())
    B.box((0, -Y - 0.15, 13.3), (25.0, 0.3, 0.6), b)                      # door header
    for x in (-8.0, 0.0, 8.0):                                            # back roll-up doors
        B.box((x, Y + 0.06, 2.5), (4.5, 0.12, 5.0), d)
    for x in (-X, X):
        for yy in (-Y, Y):
            B.box((x, yy, E / 2), (0.3, 0.3, E), b)
    export("SK_Hangar", [B.finish("SK_Hangar")])


def shop():
    """White office / shop building 20 x 40 x 8 m: window bands, three roll-up doors on +X, glass entry on -Y,
    low-slope roof with rooftop units."""
    reset()
    B = Builder()
    w, r, d, gl = WHITE(), ROOF(), DOOR(), GLASS()
    X, Y, E, RZ = 10.0, 20.0, 7.0, 8.2
    B.box((0, 0, E / 2), (2 * X, 2 * Y, E), w)
    for sgn in (-1, 1):
        fo(B, [(0, -Y - 0.4, RZ), (0, Y + 0.4, RZ), (sgn * (X + 0.4), Y + 0.4, E), (sgn * (X + 0.4), -Y - 0.4, E)], r, (sgn * 0.1, 0, 1), [(0, 0), (8, 0), (8, 2), (0, 2)])
        fo(B, [(0, -Y - 0.4, RZ - 0.15), (0, Y + 0.4, RZ - 0.15), (sgn * (X + 0.4), Y + 0.4, E - 0.15), (sgn * (X + 0.4), -Y - 0.4, E - 0.15)], r, (0, 0, -1))
        fo(B, [(-X, sgn * Y, E), (X, sgn * Y, E), (0, sgn * Y, RZ)], w, (0, sgn, 0))
    B.box((-X - 0.03, 0, 2.6), (0.06, 2 * Y - 4, 1.4), gl)               # window bands, -X side (offices)
    B.box((-X - 0.03, 0, 5.2), (0.06, 2 * Y - 4, 1.2), gl)
    for k in range(3):
        B.box((X + 0.04, -12.0 + 12.0 * k, 2.6), (0.08, 4.5, 5.2), d)
    B.box((0, -Y - 0.04, 1.4), (5.0, 0.08, 2.8), gl)
    B.box((0, -Y - 1.8, 3.0), (7.0, 3.6, 0.25), r)                       # entry canopy
    for k in range(4):
        B.box((-4.0 + 2.5 * k, -10.0 + 7.0 * k, RZ - 0.2), (2.0, 3.0, 1.4), STEEL())
    export("SK_Shop", [B.finish("SK_Shop")])


def blockhouse():
    """Hardened control building ('Control Room' in OSM, the labelled aerial's blockhouse): 12 x 34 m concrete box,
    earth berms on the back and both ends, slit windows and doors on the front (-Y), antenna mast."""
    reset()
    B = Builder()
    c, be, d, gl = CONC(), BERM(), DOOR(), GLASS()
    X, Y, H = 17.0, 6.0, 4.6
    B.box((0, 0, H / 2), (2 * X, 2 * Y, H), c)
    B.box((0, 0, H + 0.3), (2 * X + 1.0, 2 * Y + 1.0, 0.6), c)
    for k in range(5):
        B.box((-12.0 + 6.0 * k, -Y - 0.03, 2.6), (2.6, 0.06, 0.5), gl)
    for x in (-15.0, 15.0):
        B.box((x, -Y - 0.04, 1.2), (1.2, 0.08, 2.4), d)
    BW, T = 7.0, H + 0.6                                                   # berms: back (+Y) and the two ends
    fo(B, [(-X, Y + 0.5, T), (X, Y + 0.5, T), (X + BW, Y + BW, -0.3), (-X - BW, Y + BW, -0.3)], be, (0, 1, 1))
    for sgn in (-1, 1):
        fo(B, [(sgn * (X + 0.5), -Y, T), (sgn * (X + 0.5), Y + 0.5, T), (sgn * (X + BW), Y + BW, -0.3), (sgn * (X + BW), -Y, -0.3)], be, (sgn, 0, 1))
        fo(B, [(sgn * (X + 0.5), -Y, T), (sgn * (X + BW), -Y, -0.3), (sgn * (X + 0.5), -Y, -0.3)], be, (0, -1, 0))
        fo(B, [(sgn * (X + 0.5), Y + 0.5, T), (sgn * (X + BW), Y + BW, -0.3), (sgn * (X + BW), Y + 0.5, -0.3)], be, (sgn, 1, 0))
    lattice(B, 10.0, 1.0, 11.0, 2.0, T, H + 14.0, 2.0, STEEL(), col=0.05, brace=0.025)
    B.box((-8.0, 2.0, H + 1.2), (3.0, 2.0, 1.2), STEEL())
    export("SK_Blockhouse", [B.finish("SK_Blockhouse")])


def debris():
    reset()
    B = Builder()
    w, cd, d = WHITE(), CONCD(), DARK()
    htank(B, 0.0, 0.0, 2.25, 14.0, 1.83, w, "y", n=16)
    for y in (-4.0, 4.0):
        B.box((0, y, 0.2), (2.6, 0.6, 0.4), mat("M_SiteWood", (0.35, 0.25, 0.15), 0.0, 0.8))
    B.tube([(0, -7.05, 2.25), (0, -3.0, 2.25)], [1.86, 1.86], cd, 16, cap=False)     # soot at the engine end
    export("SK_StageDebris", [B.finish("SK_StageDebris")])


CARS = {"Sedan": (4.7, 1.85, 1.45, 0.34), "SUV": (4.8, 1.95, 1.72, 0.37), "Pickup": (5.8, 2.05, 1.92, 0.40)}
PAINTS = {"White": (0.82, 0.83, 0.83), "Silver": (0.52, 0.53, 0.55), "Black": (0.025, 0.025, 0.028), "Grey": (0.17, 0.18, 0.19),
          "Red": (0.42, 0.03, 0.03), "Blue": (0.04, 0.09, 0.26)}


def cars():
    """Generic parked cars (no makes or badges), ~200 triangles each, front toward -Y."""
    for body, (L, Wd, H, r) in CARS.items():
        for pn, rgb in PAINTS.items():
            reset()
            B = Builder()
            paint = mat(f"M_CarPaint{pn}", rgb, 0.45, 0.32)
            gl, ty = GLASS(), mat("M_SiteTyre", (0.02, 0.02, 0.02), 0.0, 0.9)
            zb, hb = r * 0.55, H * (0.50 if body != "Pickup" else 0.55)
            B.box((0, 0, zb + hb / 2), (Wd, L, hb), paint)
            z0 = zb + hb
            if body == "Pickup":
                f0, f1, t0, t1 = -L / 2 + 1.2, -0.2, -L / 2 + 1.9, -0.35
                for x in (-Wd / 2 + 0.05, Wd / 2 - 0.05):
                    B.box((x, (f1 + L / 2) / 2, z0 + 0.25), (0.1, L / 2 - f1, 0.5), paint)
                B.box((0, L / 2 - 0.05, z0 + 0.25), (Wd, 0.1, 0.5), paint)
            elif body == "SUV":
                f0, f1, t0, t1 = -L / 2 + 1.3, L / 2 - 0.25, -L / 2 + 2.0, L / 2 - 0.45
            else:
                f0, f1, t0, t1 = -L / 2 + 1.35, L / 2 - 0.65, -L * 0.1, L * 0.2
            cab = [(-Wd / 2 + 0.06, f0, z0), (Wd / 2 - 0.06, f0, z0), (Wd / 2 - 0.06, f1, z0), (-Wd / 2 + 0.06, f1, z0),
                   (-Wd / 2 + 0.2, t0, H), (Wd / 2 - 0.2, t0, H), (Wd / 2 - 0.2, t1, H), (-Wd / 2 + 0.2, t1, H)]
            for q in ((0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
                B.face([cab[i] for i in q][::-1], paint if q == (7, 6, 5, 4) else gl)
            for x in (-Wd / 2 + 0.12, Wd / 2 - 0.12):
                for y in (-L / 2 + 0.85, L / 2 - 0.9):
                    B.tube([(x - 0.12, y, r), (x + 0.12, y, r)], [r, r], ty, 8, cap=True)
            export(f"SK_Car_{body}_{pn}", [B.finish(f"SK_Car_{body}_{pn}")])
    reset()
    B = Builder()
    B.box((0, 0, 0.01), (0.12, 5.5, 0.02), mat("M_SiteLine", (0.85, 0.85, 0.82), 0.0, 0.6))
    export("SK_StallLine", [B.finish("SK_StallLine")])


# ------------------------------------------------------------------ test stands round 2 (mcgregor-tests agent, 20 Oct 2026)
# Hardware on the stands (generic, no names or logos) and the site-specific meshes from Scripts/mcgregor/tests_layout.py.
SOOT = lambda: mat("M_TestSootDark", (0.05, 0.045, 0.04), 0.0, 0.95)
NOZ = lambda: mat("M_TestNozzle", (0.12, 0.11, 0.10), 0.7, 0.45)
PWR = lambda: mat("M_TestPowerhead", (0.55, 0.50, 0.45), 0.8, 0.35)
SOOTW = lambda: mat("M_TestSootWhite", (0.42, 0.41, 0.40), 0.1, 0.6)
SOOTW2 = lambda: mat("M_TestSootWhite2", (0.66, 0.65, 0.63), 0.1, 0.5)
CARBON = lambda: mat("M_TestCarbon", (0.06, 0.06, 0.065), 0.2, 0.5)
TEST_MATS = {"M_TestSootDark": SOOT, "M_TestApron": lambda: mat("M_TestApron", (0.55, 0.53, 0.50), 0.0, 0.9),
             "M_TestCaliche": lambda: mat("M_TestCaliche", (0.78, 0.74, 0.64), 0.0, 0.95),
             "M_TestScorch": lambda: mat("M_TestScorch", (0.04, 0.035, 0.03), 0.0, 1.0),
             "M_TestScorchLight": lambda: mat("M_TestScorchLight", (0.10, 0.09, 0.07), 0.0, 1.0),
             "M_SiteConcrete": CONC, "M_SiteConcreteDark": CONCD, "M_SiteYellow": YEL}


def raptor_engine(name="SK_RaptorEngine"):
    """Generic methalox engine (~Raptor-sized: 3.1 m long, 1.3 m nozzle exit), hanging nozzle-down from its gimbal at the
    origin: thrust puck, powerhead with two turbopumps and manifolds, chamber, regen-cooled bell. No markings."""
    reset()
    B = Builder()
    p, n, s = PWR(), NOZ(), STEEL()
    revolve(B, [(0.0, 0.0), (0.45, 0.0), (0.45, -0.28), (0.55, -0.32), (0.55, -1.05), (0.42, -1.12), (0.0, -1.12)][::-1], p, 16)
    for x in (-0.62, 0.62):                                     # turbopumps
        revolve(B, [(0.0, -0.15), (0.27, -0.15), (0.27, -0.95), (0.0, -0.95)][::-1], p, 10, c=(x, 0.1, 0.0))
        B.tube([(x, 0.1, -0.6), (x * 0.55, 0.0, -1.0)], [0.12, 0.12], s, 8, cap=False)
    B.tube([(0.0, 0.62, -0.2), (0.0, 0.62, -1.15), (0.0, 0.3, -1.35)], [0.1, 0.1, 0.1], s, 8, cap=False)
    revolve(B, [(0.5, -1.12), (0.25, -1.36)], n, 16)
    bell(B, (0.0, 0.0, -1.36), 0.25, 0.65, 1.74, n, n=18)
    revolve(B, [(0.67, -3.08), (0.67, -3.12)], s, 18)          # exit ring
    export(name, [B.finish(name)])


def raptor_cell():
    """The 2025 vertical engine cells (Raptor North / South, NSF Aug 2025): a black steel box ~16 m tall straddling the
    head of the trench, the engine hanging nozzle-down in an open bay (seen from both sides), engine deck at 7 m, clad
    back half, roof with a white run tank, stair tower, silver feed lines. Origin = the engine axis at pad level; the
    trench runs toward -Y (the placement bearing), its head wall under the cell at local y = +3."""
    reset()
    B = Builder()
    bk, g, w, gv, c = BLACK(), GRATE(), WHITE(), mat("M_SiteGalv", (0.62, 0.63, 0.64), 0.9, 0.38), CONC()
    X0, X1, Y0, Y1, H = -8.0, 8.0, -5.0, 11.0, 16.0
    for x in (X0, X1):
        for y in (Y0, 3.0, Y1):
            B.box((x, y, H / 2), (0.7, 0.7, H), bk)
            B.box((x, y, 0.4), (1.6, 1.6, 0.8), c)               # footings beside the trench
    for z in (7.0, 11.0, H):                                     # ring beams
        for (a, b) in (((X0, Y0), (X1, Y0)), ((X1, Y0), (X1, Y1)), ((X1, Y1), (X0, Y1)), ((X0, Y1), (X0, Y0))):
            B.box(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, z - 0.35), (abs(b[0] - a[0]) + 0.7, abs(b[1] - a[1]) + 0.7, 0.7), bk)
    # clad back half (y 3..11): walls on three sides, full height; front half clad only above the bay (z 11..16)
    for x in (X0, X1):
        fo(B, [(x, 3.0, 0.0), (x, Y1, 0.0), (x, Y1, H), (x, 3.0, H)], bk, (1 if x > 0 else -1, 0, 0))
        fo(B, [(x, Y0, 11.0), (x, 3.0, 11.0), (x, 3.0, H), (x, Y0, H)], bk, (1 if x > 0 else -1, 0, 0))
        fo(B, [(x, 3.0, 0.0), (x, Y1, 0.0), (x, Y1, H), (x, 3.0, H)], bk, (-1 if x > 0 else 1, 0, 0))
    fo(B, [(X0, Y1, 0.0), (X1, Y1, 0.0), (X1, Y1, H), (X0, Y1, H)], bk, (0, 1, 0))
    fo(B, [(X0, Y0, 11.0), (X1, Y0, 11.0), (X1, Y0, H), (X0, Y0, H)], bk, (0, -1, 0))
    fo(B, [(X0, 3.0, 0.0), (X1, 3.0, 0.0), (X1, 3.0, 11.0), (X0, 3.0, 11.0)], bk, (0, -1, 0))    # inner wall behind the bay
    B.box((0.0, (Y0 + Y1) / 2, H + 0.15), (X1 - X0 + 0.7, Y1 - Y0 + 0.7, 0.3), bk)              # roof
    # engine deck over the bay with the thrust structure the engine hangs from
    for (x0, x1) in ((X0, -2.2), (2.2, X1)):
        deck(B, x0, Y0, x1, 3.0, 7.3, g)
    deck(B, -2.2, Y0, 2.2, -2.2, 7.3, g)
    deck(B, -2.2, 2.2, 2.2, 3.0, 7.3, g)
    B.box((0.0, 0.0, 7.6), (5.0, 0.6, 0.6), bk)
    B.box((0.0, 0.0, 7.6), (0.6, 5.0, 0.6), bk)
    revolve(B, [(0.0, 6.6), (0.5, 6.6), (0.5, 7.3)], STEEL(), 12)
    rail(B, X0, Y0, X1, 3.0, 7.3, YEL())
    # run tank on the roof, feed lines down the side, stair tower on +X
    revolve(B, [(0.0, H + 0.3), (1.7, H + 0.3), (1.7, H + 7.5)] + dome_prof(1.7, H + 7.5, 0.8, 3)[1:], w, 16, c=(0.0, 7.0, 0.0))
    rail(B, X0, Y0, X1, Y1, H + 0.3, YEL())
    for k, x in enumerate((-1.2, 0.0, 1.2)):
        B.tube([(x, 7.0, H + 0.6), (x, 3.5, H + 0.6), (x, 3.5, 8.2), (x * 0.3, 0.6, 7.9)], [0.16, 0.16, 0.16, 0.16], gv, 8, cap=False)
    for k, z in enumerate((2.0, 3.0)):
        B.tube([(X1 + 0.6, 30.0, z), (X1 + 0.6, 6.0, z), (X1 + 0.6, 6.0, 8.0 + k), (X1 - 0.5, 4.0, 8.0 + k)], [0.22, 0.22, 0.22, 0.22], gv, 8, cap=False)
    lattice(B, X1 + 0.6, 6.5, X1 + 3.6, 10.5, 0.0, H + 0.3, 4.0, bk, col=0.14, brace=0.07)
    for i in range(int(H / 3.0)):
        z = 3.0 * i
        y0, y1 = (6.9, 10.1) if i % 2 else (10.1, 6.9)
        B.tube([(X1 + 2.1, y0, z), (X1 + 2.1, y1, z + 3.0)], [0.3, 0.3], g, 4, cap=False)
    export("SK_RaptorCell", [B.finish("SK_RaptorCell")])


def vert_stand(name="SK_VertStand", tank=True):
    """Vertical stand over a trench head (the 2021 Raptor stand; with tank=False the second-stage stand, scaled per site):
    concrete piers on the rims, a grey steel frame 16 x 8 m, deck at 4 m and platforms at 10 / 16 / 22 m with a 4.6 m
    square opening for the engine or stage, bracing on the sides and back (front open toward the trench, -Y), a hoist
    beam on top, a white run tank above the engine (tank=True), stair tower on +X. Origin = the engine / stage axis
    at rim level; the trench head wall is at local y = +2.5."""
    reset()
    B = Builder()
    s, g, c = STEEL(), GRATE(), CONC()
    X, Yf, Yb, H = 8.0, -2.0, 6.0, 24.0       # the front piers stand on the rims, clear of the trench's flare
    for x in (-X, X):
        for y in (Yf, Yb):
            B.box((x, y, 0.5), (1.6, 1.6, 1.0), c)
            B.box((x, y, H / 2 + 0.5), (0.5, 0.5, H - 1.0), s)
    for z in (4.0, 10.0, 16.0, 22.0):
        hole = 2.3
        for (x0, y0, x1, y1) in ((-X, Yf, -hole, Yb), (hole, Yf, X, Yb), (-hole, Yf, hole, -hole), (-hole, hole, hole, Yb)):
            deck(B, x0, y0, x1, y1, z, g)
        rail(B, -X, Yf, X, Yb, z, YEL())
        for (a, b) in (((-X, Yf), (X, Yf)), ((X, Yf), (X, Yb)), ((X, Yb), (-X, Yb)), ((-X, Yb), (-X, Yf))):
            B.tube([(a[0], a[1], z - 0.3), (b[0], b[1], z - 0.3)], [0.22, 0.22], s, 4, cap=False)
    for x in (-X, X):                                            # side bracing
        for z0, z1 in ((4.0, 10.0), (10.0, 16.0), (16.0, 22.0)):
            B.tube([(x, Yf, z0), (x, Yb, z1)], [0.12, 0.12], s, 4, cap=False)
            B.tube([(x, Yb, z0), (x, Yf, z1)], [0.12, 0.12], s, 4, cap=False)
    for z0, z1 in ((4.0, 10.0), (10.0, 16.0), (16.0, 22.0)):     # back bracing
        B.tube([(-X, Yb, z0), (X, Yb, z1)], [0.12, 0.12], s, 4, cap=False)
    B.box((0.0, (Yf + Yb) / 2, H), (0.6, Yb - Yf + 6.0, 0.8), s)          # hoist beam, overhanging the front
    B.tube([(0.0, Yf - 2.5, H - 0.4), (0.0, Yf - 2.5, H - 6.0)], [0.03, 0.03], s, 4, cap=False)
    if tank:
        B.box((0.0, 0.0, 7.7), (4.6, 0.6, 0.6), s)                          # thrust beam the engine hangs from
        revolve(B, [(0.0, 12.0), (1.6, 12.0), (1.6, 19.5)] + dome_prof(1.6, 19.5, 0.8, 3)[1:], WHITE(), 14)
        B.tube([(0.0, 0.0, 12.0), (0.0, 0.0, 7.9)], [0.2, 0.2], mat("M_SiteGalv", (0.62, 0.63, 0.64), 0.9, 0.38), 8, cap=False)
    lattice(B, X, 1.0, X + 3.0, Yb, 0.0, H - 2.0, 4.0, s, col=0.12, brace=0.06)
    export(name, [B.finish(name)])


def upper_stage():
    """Generic upper stage standing in the second-stage stand: plain white tank body 3.66 m across and 12.6 m tall, dark
    aft skirt, a long dark vacuum nozzle (3.2 m, 2.4 m exit) hanging below. Origin = the base of the body."""
    reset()
    B = Builder()
    revolve(B, [(0.0, 0.0), (1.83, 0.0), (1.83, 1.4)], CARBON(), 24)
    revolve(B, [(1.83, 1.4), (1.83, 12.6)] + dome_prof(1.83, 12.6, 0.9, 4)[1:], WHITE(), 24)
    revolve(B, [(0.0, -0.05), (0.55, -0.05), (0.55, -0.6)][::-1], PWR(), 12)
    bell(B, (0.0, 0.0, -0.6), 0.32, 1.2, 2.6, NOZ(), n=20)
    export("SK_UpperStage", [B.finish("SK_UpperStage")])


def display_booster():
    """Display first stage at the hangar circle (Kenny's photo 06, Apple's shadow): a flown-looking stage standing on four
    deployed legs on a round concrete plinth: white body 3.66 m across to 44.5 m with soot on the lower third, black
    interstage to 51 m with four grid fins, nine sooty engine bells, legs and struts dark. No markings."""
    reset()
    B = Builder()
    B.cyl((0, 0, 0), 0.6, 12.5, CONC(), 40)
    revolve(B, [(0.0, 3.3), (1.86, 3.3), (1.86, 3.6)], CARBON(), 24)                 # octaweb / heat shield
    for k in range(9):
        x, y = (0.0, 0.0) if k == 8 else (1.25 * math.cos(2 * math.pi * k / 8), 1.25 * math.sin(2 * math.pi * k / 8))
        bell(B, (x, y, 3.3), 0.16, 0.45, 1.35, SOOT(), n=10)
    revolve(B, [(1.83, 3.6), (1.83, 14.0)], SOOTW(), 24)
    revolve(B, [(1.83, 14.0), (1.83, 21.0)], SOOTW2(), 24)
    revolve(B, [(1.83, 21.0), (1.83, 44.5)], WHITE(), 24)
    revolve(B, [(1.84, 44.5), (1.84, 51.0), (1.5, 51.0)], CARBON(), 24)
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        ca, sa = math.cos(a), math.sin(a)
        # leg: from the base out and down to the foot on the plinth; telescoping strut from 10 m up to the leg's outer end
        B.tube([(1.9 * ca, 1.9 * sa, 3.8), (8.6 * ca, 8.6 * sa, 0.9)], [0.45, 0.32], CARBON(), 6, cap=False)
        B.box((8.8 * ca, 8.8 * sa, 0.75), (1.5, 1.5, 0.3), CARBON())
        B.tube([(1.86 * ca, 1.86 * sa, 10.5), (7.0 * ca, 7.0 * sa, 1.8)], [0.18, 0.14], STEEL(), 6, cap=False)
        # grid fin, deployed outward at 48.5 m
        fa, fb = Vector((1.9 * ca, 1.9 * sa, 48.5)), Vector((3.5 * ca, 3.5 * sa, 48.5))
        tang = Vector((-sa, ca, 0.0))
        P = [fa - tang * 0.75 + Vector((0, 0, -0.1)), fb - tang * 0.75 + Vector((0, 0, -0.1)), fb + tang * 0.75, fa + tang * 0.75]
        for dz in (0.0, 0.5):
            q = [tuple(v + Vector((0, 0, dz))) for v in P]
            B.face(q, mat("M_SiteGrate", (0.22, 0.22, 0.23), 0.6, 0.6))
            B.face(q[::-1], mat("M_SiteGrate", (0.22, 0.22, 0.23), 0.6, 0.6))
    export("SK_DisplayBooster", [B.finish("SK_DisplayBooster")])


def pipe_rack():
    """10 m of the pipe rack between the 2025 stands (Esri: x ~921, y 262..590): one H bent, four silver lines along Y."""
    reset()
    B = Builder()
    s, gv = STEEL(), mat("M_SiteGalv", (0.62, 0.63, 0.64), 0.9, 0.38)
    for x in (-1.5, 1.5):
        B.box((x, 0.0, 2.1), (0.3, 0.3, 4.2), s)
        B.box((x, 0.0, 0.2), (0.8, 0.8, 0.4), CONC())
    B.box((0.0, 0.0, 3.5), (3.6, 0.3, 0.3), s)
    B.box((0.0, 0.0, 4.3), (3.6, 0.3, 0.3), s)
    for x, z, r in ((-0.9, 3.85, 0.3), (0.0, 3.85, 0.22), (0.9, 3.85, 0.3), (-0.4, 4.6, 0.16)):
        B.tube([(x, -5.0, z), (x, 5.0, z)], [r, r], gv, 8, cap=False)
    export("SK_PipeRack", [B.finish("SK_PipeRack")])


def tank_tall():
    """Tall white vertical tank (the two at Raptor South: ~28 m, leaning tall cylinders in the imagery): skirt, body,
    dome, ladder cage line, top railing."""
    reset()
    B = Builder()
    w, s = WHITE(), STEEL()
    revolve(B, [(2.0, 0.0), (2.0, 1.2)], mat("M_SiteSteel", (0.36, 0.37, 0.39), 0.7, 0.5), 18)
    revolve(B, [(2.0, 1.2), (2.0, 27.0)] + dome_prof(2.0, 27.0, 1.0, 4)[1:], w, 18)
    B.tube([(2.15, 0.0, 1.2), (2.15, 0.0, 27.2)], [0.06, 0.06], s, 4, cap=False)
    B.tube([(2.45, 0.0, 3.0), (2.45, 0.0, 27.2)], [0.4, 0.4], s, 6, cap=False)
    for k in range(12):
        a = 2 * math.pi * k / 12
        B.tube([(1.3 * math.cos(a), 1.3 * math.sin(a), 27.6), (1.3 * math.cos(a), 1.3 * math.sin(a), 28.6)], [0.03, 0.03], YEL(), 4, cap=False)
    export("SK_TankTall", [B.finish("SK_TankTall")])


def rvac_trailer():
    """A vacuum engine lying on its white cradle on a black low trailer (NSF Aug 2025, at Raptor South): big two-part
    nozzle (black regen section, ribbed silver extension) along the trailer, powerhead toward +Y."""
    reset()
    B = Builder()
    bk, ty, w = BLACK(), mat("M_SiteTyre", (0.02, 0.02, 0.02), 0.0, 0.9), WHITE()
    B.box((0.0, 0.0, 1.0), (2.6, 14.0, 0.3), bk)
    B.box((0.0, 6.2, 1.5), (2.4, 2.0, 0.8), bk)
    for y in (-5.0, -3.7, 4.0, 5.3):
        for x in (-1.15, 1.15):
            B.tube([(x - 0.3, y, 0.5), (x + 0.3, y, 0.5)], [0.5, 0.5], ty, 10, cap=True)
    B.box((0.0, 2.6, 1.6), (2.2, 0.6, 1.0), w)
    B.box((0.0, -2.6, 1.9), (2.4, 0.6, 1.6), w)
    for x in (-0.8, 0.8):
        B.tube([(x, 2.4, 1.2), (0.0, 2.6, 2.7)], [0.1, 0.1], w, 6, cap=False)
    zc = 2.6
    # engine axis along Y: powerhead at y ~ +3, nozzle opening toward -Y
    B.tube([(0.0, 3.6, zc), (0.0, 2.6, zc)], [0.55, 0.55], PWR(), 14, cap=True)
    for x in (-0.6, 0.6):
        B.tube([(x, 3.4, zc + 0.3), (x, 2.5, zc + 0.3)], [0.25, 0.25], PWR(), 10, cap=True)
    bell(B, (0.0, 2.6, zc), 0.3, 0.75, 1.2, NOZ(), axis="y", n=18)
    bell(B, (0.0, 1.4, zc), 0.75 / 1.4, 1.15, 3.3, mat("M_SiteGalv", (0.62, 0.63, 0.64), 0.9, 0.38), axis="y", n=24)
    export("SK_RVacTrailer", [B.finish("SK_RVacTrailer")])


def tests_meshes():
    """Trench liners, aprons, pads and scorch skins from Saved/McGregor/tests_meshes.json (tests_layout.py): shared
    vertices, per-vertex UVs, smooth or flat per part, one material slot per part."""
    import json
    M = json.load(open(os.path.join(ROOT, "Saved", "McGregor", "tests_meshes.json")))
    for name, m in M.items():
        reset()
        me = bpy.data.meshes.new(name)
        import bmesh as _bm
        bm = _bm.new()
        uvl = bm.loops.layers.uv.new("UVMap")
        mats = []
        for part in m["parts"]:
            mm = TEST_MATS.get(part["mat"], lambda n=part["mat"]: mat(n))()
            if mm not in mats:
                mats.append(mm)
            mi = mats.index(mm)
            vs = [bm.verts.new(v) for v in part["verts"]]
            for t in part["tris"]:
                try:
                    f = bm.faces.new([vs[i] for i in t])
                except ValueError:
                    continue
                f.material_index = mi
                f.smooth = bool(part["smooth"])
                for l, i in zip(f.loops, t):
                    l[uvl].uv = part["uvs"][i]
        bm.to_mesh(me)
        bm.free()
        for mm in mats:
            me.materials.append(mm)
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        export(name, [ob])


def test_hardware():
    raptor_engine()
    raptor_cell()
    vert_stand()
    vert_stand("SK_VertStandS2", tank=False)
    upper_stage()
    display_booster()
    pipe_rack()
    tank_tall()
    rvac_trailer()


JOBS = {"structural": structural, "tripod": tripod, "fsstand": fs_stand, "trench": fs_trench, "enginev": engine_v,
        "engineh": engine_h, "crane": crane, "watertower": water_towers, "tanks": tanks, "hangar": hangar, "shop": shop,
        "blockhouse": blockhouse, "debris": debris, "cars": cars, "testhw": test_hardware, "tests": tests_meshes}
ONLY = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
for k, fn in JOBS.items():
    if not ONLY or k in ONLY:
        fn()
print("SITE KIT DONE")
