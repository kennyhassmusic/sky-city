"""Pickup meshes for the Skyster systems in Sky City and McGregor (shapes from Skyster's js/world.js and js/addons.js).
Same conventions as Scripts/streets/blender_street_kit.py: metres, standing on z = 0, Blender X stays Unreal X.

  SC_PadRingSmall / SC_PadCoreSmall   small pressure point: a gold hex coin (ring r 0.42 + hub) round a glowing hex core
  SC_PadRingBig / SC_PadCoreBig       big pressure point: two crossed gold rings (r 1.05) round a glowing 0.55 m sphere
  SC_PadPoolSmall / SC_PadPoolBig     the soft glow pool under each (4 m / 7 m, UVs 0..1 for a radial gradient)
  SC_ChargerBay                       one wireless Supercharger bay: 6 m along (X) x 3 m across, 4 cm glass slab
  SC_ChargerCross                     the floating green cross over a Supercharger site
  SC_Addon_nitrogen / _combustion / _rocket   fuel add-on pickups with a glowing ring round the base
Run: /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/unreal/blender_pickups_kit.py
Output: SourceArt/Pickups/<name>.glb
"""
import math, os
import bmesh, bpy
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
_KIT = os.path.join(ROOT, "Scripts", "streets", "blender_street_kit.py")
src = open(_KIT).read().split("# ------------------------------------------------------------------ props")[0]
K = {"__file__": _KIT}
exec(compile(src, "kit_helpers", "exec"), K)
Builder, mat, export = K["Builder"], K["mat"], K["export"]
K["OUT"] = os.path.join(ROOT, "SourceArt", "Pickups")
os.makedirs(K["OUT"], exist_ok=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    K["MATS"].clear()


def closed(B, name):
    """Finish a closed shape with its normals made consistent and pointing out (the upright rings are built
    with two axes swapped, which flips their winding)."""
    bmesh.ops.remove_doubles(B.bm, verts=B.bm.verts[:], dist=1e-5)
    bmesh.ops.recalc_face_normals(B.bm, faces=B.bm.faces[:])
    return B.finish(name)


def torus(B, m, R, r, seg, sides, plane="xz", z0=0.0):
    """A torus as quads; plane 'xz' stands upright facing Y, 'xy' lies flat."""
    for i in range(seg):
        for j in range(sides):
            q = []
            for di, dj in ((0, 0), (1, 0), (1, 1), (0, 1)):
                a = 2 * math.pi * (i + di) / seg
                b = 2 * math.pi * (j + dj) / sides
                rr = R + r * math.cos(b)
                u, v, w = rr * math.cos(a), rr * math.sin(a), r * math.sin(b)
                q.append((u, w, v + z0) if plane == "xz" else (u, v, w + z0))
            B.face(q, m)


def prism(B, m, R, depth, n, axis="y", z0=0.0, cap=True):
    """An n-sided prism (hex disc / cylinder) along an axis, centred at height z0."""
    def P(a, t):
        x, y = R * math.cos(a), R * math.sin(a)
        return (x, t, y + z0) if axis == "y" else (x, y, t + z0)
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        B.face([P(a0, -depth / 2), P(a1, -depth / 2), P(a1, depth / 2), P(a0, depth / 2)], m)
    if cap:
        for t, rev in ((-depth / 2, False), (depth / 2, True)):
            ring = [P(2 * math.pi * i / n, t) for i in range(n)]
            B.face(ring[::-1] if rev else ring, m)


def sphere(B, m, R, z0, seg=20, rings=12):
    for i in range(rings):
        for j in range(seg):
            q = []
            for di, dj in ((0, 0), (0, 1), (1, 1), (1, 0)):
                th = math.pi * (i + di) / rings
                ph = 2 * math.pi * (j + dj) / seg
                q.append((R * math.sin(th) * math.cos(ph), R * math.sin(th) * math.sin(ph), z0 + R * math.cos(th)))
            B.face(q, m)


def plane(B, m, s):
    B.face([(-s / 2, -s / 2, 0.02), (s / 2, -s / 2, 0.02), (s / 2, s / 2, 0.02), (-s / 2, s / 2, 0.02)], m, [(0, 0), (1, 0), (1, 1), (0, 1)])


GOLD = lambda: mat("M_PadGold", (0.79, 0.64, 0.40), 1.0, 0.25)
CORE = lambda: mat("M_PadCore", (0.4, 0.7, 1.0), 0.0, 0.3)
POOL = lambda: mat("M_PadPool", (0.6, 1.1, 1.6), 0.0, 1.0)

jobs = []

# small pressure point: hex coin standing up (it spins about the vertical in the game)
reset(); B = Builder(); g = GOLD()
torus(B, g, 0.42, 0.07, 6, 8, "xz")
prism(B, g, 0.12, 0.08, 6, "y")
export("SC_PadRingSmall", [closed(B, "SC_PadRingSmall")])
reset(); B = Builder()
prism(B, CORE(), 0.3, 0.05, 6, "y")
export("SC_PadCoreSmall", [closed(B, "SC_PadCoreSmall")])
# big pressure point: crossed rings round a sphere
reset(); B = Builder(); g = GOLD()
torus(B, g, 1.05, 0.08, 36, 10, "xz")
torus(B, g, 1.05, 0.08, 36, 10, "xy")
export("SC_PadRingBig", [closed(B, "SC_PadRingBig")])
reset(); B = Builder()
sphere(B, CORE(), 0.55, 0.0)
export("SC_PadCoreBig", [closed(B, "SC_PadCoreBig")])
for name, s in (("SC_PadPoolSmall", 4.0), ("SC_PadPoolBig", 7.0)):
    reset(); B = Builder()
    plane(B, POOL(), s)
    export(name, [B.finish(name)])

# Supercharger bay: a 4 cm dark glass slab, 6 m along X, 3 m across; the top carries the marking UVs
reset(); B = Builder()
bay = mat("M_ChargerBay", (0.02, 0.022, 0.026), 0.5, 0.22)
L, Wd, h = 6.0, 3.0, 0.04
B.face([(-L / 2, -Wd / 2, h), (L / 2, -Wd / 2, h), (L / 2, Wd / 2, h), (-L / 2, Wd / 2, h)], bay, [(0, 0), (1, 0), (1, 1), (0, 1)])
for (a, b) in (((-L / 2, -Wd / 2), (L / 2, -Wd / 2)), ((L / 2, -Wd / 2), (L / 2, Wd / 2)), ((L / 2, Wd / 2), (-L / 2, Wd / 2)), ((-L / 2, Wd / 2), (-L / 2, -Wd / 2))):
    B.face([(a[0], a[1], 0), (b[0], b[1], 0), (b[0], b[1], h), (a[0], a[1], h)], bay, [(0.5, 0.5)] * 4)
export("SC_ChargerBay", [B.finish("SC_ChargerBay")])
reset(); B = Builder()
gr = mat("M_ChargerCross", (0.3, 1.0, 0.45), 0.0, 0.4)
B.box((0, 0, 0), (0.5, 0.14, 0.14), gr)
B.box((0, 0, 0), (0.14, 0.14, 0.5), gr)
export("SC_ChargerCross", [closed(B, "SC_ChargerCross")])

# fuel add-ons, ~2 m tall, each on a glowing base ring so they read from a distance
def addon(name, body, band, glow, kind):
    reset(); B = Builder()
    mb, mband, mg = mat(f"M_{name}_Body", body, 0.6, 0.3), mat(f"M_{name}_Band", band, 0.3, 0.35), mat(f"M_{name}_Glow", glow, 0.0, 0.4)
    torus(B, mg, 1.25, 0.06, 32, 6, "xy", 0.08)
    if kind == "nitrogen":           # cryo canister: frosted blue bands and a valve on top
        prism(B, mb, 0.42, 1.5, 24, "z", 1.0)
        for zb in (0.55, 1.0, 1.45):
            prism(B, mband, 0.44, 0.12, 24, "z", zb)
        prism(B, mb, 0.12, 0.25, 12, "z", 1.85)
        B.box((0, 0, 2.0), (0.4, 0.06, 0.06), mband)
    elif kind == "combustion":       # an engine: bell nozzle under a turbopump block
        for k in range(10):
            z0, z1 = 0.2 + 0.1 * k, 0.3 + 0.1 * k
            r0, r1 = 0.55 - 0.035 * k, 0.55 - 0.035 * (k + 1)
            for i in range(24):
                a0, a1 = 2 * math.pi * i / 24, 2 * math.pi * (i + 1) / 24
                B.face([(r0 * math.cos(a0), r0 * math.sin(a0), z0), (r0 * math.cos(a1), r0 * math.sin(a1), z0),
                        (r1 * math.cos(a1), r1 * math.sin(a1), z1), (r1 * math.cos(a0), r1 * math.sin(a0), z1)], mb)
        prism(B, mband, 0.3, 0.5, 16, "z", 1.45)
        B.box((0.25, 0, 1.55), (0.35, 0.3, 0.45), mb)
        prism(B, mband, 0.12, 0.3, 12, "z", 1.85)
    else:                            # rocket fuel: white tank, red bands, nose cone, fins
        prism(B, mb, 0.38, 1.5, 24, "z", 1.0)
        for zb in (0.45, 1.5):
            prism(B, mband, 0.40, 0.14, 24, "z", zb)
        for k in range(8):
            z0, z1 = 1.75 + 0.07 * k, 1.75 + 0.07 * (k + 1)
            r0, r1 = 0.38 * (1 - k / 8) ** 0.7, 0.38 * (1 - (k + 1) / 8) ** 0.7
            for i in range(24):
                a0, a1 = 2 * math.pi * i / 24, 2 * math.pi * (i + 1) / 24
                B.face([(r0 * math.cos(a0), r0 * math.sin(a0), z0), (r0 * math.cos(a1), r0 * math.sin(a1), z0),
                        (r1 * math.cos(a1), r1 * math.sin(a1), z1), (r1 * math.cos(a0), r1 * math.sin(a0), z1)], mb)
        for i in range(4):
            a = math.pi / 2 * i
            c, s = math.cos(a), math.sin(a)
            fin = [(0.38 * c, 0.38 * s, 0.25), (0.75 * c, 0.75 * s, 0.25), (0.38 * c, 0.38 * s, 0.85)]
            B.face(fin, mband)
            B.face(fin[::-1], mband)
    export(name, [closed(B, name)])


addon("SC_Addon_nitrogen", (0.85, 0.9, 0.95), (0.25, 0.65, 1.0), (0.45, 1.0, 1.0), "nitrogen")
addon("SC_Addon_combustion", (0.18, 0.18, 0.2), (0.95, 0.45, 0.12), (1.0, 0.45, 0.1), "combustion")
addon("SC_Addon_rocket", (0.95, 0.95, 0.95), (0.8, 0.08, 0.06), (1.0, 0.8, 0.45), "rocket")
print("PICKUPS DONE")
