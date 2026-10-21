"""Set pieces for the real Roadster unveil layout (Kenny's photos 02-08 and the night drone shot 10 in
SourceArt/Reference/McGregor/unveil/), modelled in Blender (headless) and exported as GLB, one per asset, next to the
older demo kit (blender_mcgregor_kit.py: MG_Ramp, MG_LightTower, ...). Same conventions: metres, standing on z = 0,
front toward Blender -Y (Unreal +X after the glTF import, so a layout yaw names the direction the front faces).
No names, logos or lettering anywhere (the LED screens are plain emissive panels).

  UV_Stage       the show stage: 34 x 12 m low deck (1.2 m) with rounded front corners, dark skirt, red LED edge,
                 white deck lines, stairs at the back
  UV_LEDScreen   a 12 x 6.75 m LED screen on a black truss frame (one at each end of the stage)
  UV_LightMast   an 18 m box-truss light mast with a T top and two hanging banks of 3 x 4 fixtures (lower row red), a
                 line-array speaker hung off one side (photos 03, 05, 07, 08)
  UV_CraneBody   a telescopic crane truck (outriggers down) ...
  UV_CraneBoom   ... and its 32 m boom at 70 deg with a hanging 2 x 6 light rig over the front (photos 00, 02)
  UV_Barricade   a 2.5 m black steel crowd barricade bay
  UV_Umbrella    a black 3.5 m square market umbrella; UV_HighTable, UV_Sofa (hospitality, photo 04)
  UV_Riser       a 6 x 4 m camera riser with rails and two cameras on tripods (photo 07)
  UV_Trailer     a plain white 16 m production trailer (back-of-house)
Run: /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/mcgregor/blender_unveil_kit.py [-- stage mast ...]
Output: SourceArt/McGregor/meshes/UV_*.glb (build_mcgregor_ue.py kit_unveil imports them)
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
_KIT = os.path.join(ROOT, "Scripts", "streets", "blender_street_kit.py")
src = open(_KIT).read().split("# ------------------------------------------------------------------ props")[0]
K = {"__file__": _KIT}
exec(compile(src, "kit_helpers", "exec"), K)
Builder, mat, export = K["Builder"], K["mat"], K["export"]
K["OUT"] = os.path.join(ROOT, "SourceArt", "McGregor", "meshes")
os.makedirs(K["OUT"], exist_ok=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    K["MATS"].clear()


BLACK = lambda: mat("M_BlackPlastic", (0.03, 0.03, 0.03), 0.0, 0.6)
STEELB = lambda: mat("M_BarricadeSteel", (0.035, 0.035, 0.04), 0.6, 0.45)
LAMP = lambda: mat("M_LampLens", (1.0, 0.92, 0.75), 0.0, 0.2)
REDLAMP = lambda: mat("M_RedLamp", (0.9, 0.08, 0.04), 0.0, 0.25)
LEDRED = lambda: mat("M_LEDRed", (1.0, 0.03, 0.02), 0.0, 0.3)


def prism(B, outline, z0, z1, top, side):
    """Vertical prism over a convex outline (counter-clockwise, Blender XY): top face + side walls."""
    n = len(outline)
    B.face([(x, y, z1) for x, y in outline], top, [(x, y) for x, y in outline])
    for i in range(n):
        (xa, ya), (xb, yb) = outline[i], outline[(i + 1) % n]
        L = math.hypot(xb - xa, yb - ya)
        B.face([(xa, ya, z0), (xb, yb, z0), (xb, yb, z1), (xa, ya, z1)], side, [(0, z0), (L, z0), (L, z1), (0, z1)])


def rounded_rect(W, D, rf, rb=0.4, seg=6):
    """Outline (CCW) of a W x D rectangle centred on the origin, front (-Y) corners rounded by rf, back by rb."""
    pts = []
    for cx, cy, r, a0 in ((W / 2 - rf, -D / 2 + rf, rf, -90), (W / 2 - rb, D / 2 - rb, rb, 0), (-W / 2 + rb, D / 2 - rb, rb, 90), (-W / 2 + rf, -D / 2 + rf, rf, 180)):
        for k in range(seg + 1):
            a = math.radians(a0 + 90 * k / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def stage():
    reset()
    B = Builder()
    W, D, h = 34.0, 12.0, 1.2
    deck = mat("M_StageDeck", (0.16, 0.165, 0.17), 0.1, 0.55)
    skirt = mat("M_StageSkirt", (0.07, 0.072, 0.075), 0.2, 0.5)
    prism(B, rounded_rect(W, D, 3.0), 0.0, h, deck, skirt)
    # the red LED edge just under the deck lip, all round
    prism(B, rounded_rect(W + 0.06, D + 0.06, 3.03), h - 0.16, h - 0.08, LEDRED(), LEDRED())
    line = mat("M_RampLine", (0.95, 0.95, 0.93), 0.0, 0.5)
    for x in (-W / 6, W / 6):                                   # white tape lines across the deck (photo 02)
        B.box((x, 0, h + 0.004), (0.1, D - 1.0, 0.008), line)
    B.box((0, -D / 2 + 2.0, h + 0.004), (W - 6.0, 0.1, 0.008), line)
    for x in (-W / 2 + 3.0, W / 2 - 3.0):                       # stairs at the back
        for k in range(5):
            B.box((x, D / 2 + 0.35 + k * 0.3, (k + 1) * 0.2 / 2), (2.4, 0.3, (k + 1) * 0.2), skirt)
        for dx in (-1.25, 1.25):
            B.tube([(x + dx, D / 2 + 1.9, 1.0), (x + dx, D / 2 + 0.2, h + 1.0)], [0.03, 0.03], STEELB(), 6, cap=False)
    export("UV_Stage", [B.finish("UV_Stage")])


def led_screen():
    reset()
    B = Builder()
    W, Hs, z0, t = 12.0, 6.75, 2.2, 0.4
    scr = mat("M_LEDScreen", (0.02, 0.025, 0.035), 0.0, 0.15)
    blk = BLACK()
    B.box((0, 0, z0 + Hs / 2), (W + 0.3, t, Hs + 0.3), blk)              # cabinet + frame
    B.card((0, -t / 2 - 0.01, z0 + Hs / 2), (0, -1, 0), (0, 0, 1), W, Hs, scr)
    for x in (-W / 2 + 1.0, 0.0, W / 2 - 1.0):                          # truss legs, raked braces, ballast
        B.box((x, 0.6, z0 / 2), (0.4, 0.4, z0), blk)
        B.tube([(x, 3.0, 0.2), (x, 0.4, z0 + Hs * 0.7)], [0.08, 0.08], blk, 6, cap=False)
        B.box((x, 2.6, 0.25), (1.2, 2.4, 0.5), blk)
    B.box((0, 0.6, 0.15), (W, 0.6, 0.3), blk)
    export("UV_LEDScreen", [B.finish("UV_LEDScreen")])


def light_mast():
    reset()
    B = Builder()
    blk = mat("M_TrussBlack", (0.05, 0.05, 0.055), 0.7, 0.4)
    Hm, s = 18.0, 0.22
    B.box((0, 0, 0.15), (2.4, 2.4, 0.3), BLACK())
    for a in (45, 135, 225, 315):                                       # outriggers with pads
        r = math.radians(a)
        B.tube([(0, 0, 0.25), (3.0 * math.cos(r), 3.0 * math.sin(r), 0.25)], [0.07, 0.07], blk, 6, cap=False)
        B.box((3.0 * math.cos(r), 3.0 * math.sin(r), 0.05), (0.5, 0.5, 0.1), BLACK())
    cs = [(-s, -s), (s, -s), (s, s), (-s, s)]
    for x, y in cs:
        B.tube([(x, y, 0.3), (x, y, Hm)], [0.03, 0.03], blk, 6, cap=False)
    z = 0.3
    while z < Hm - 0.5:                                                 # zig-zag lacing on all four faces
        for i in range(4):
            (xa, ya), (xb, yb) = cs[i], cs[(i + 1) % 4]
            B.tube([(xa, ya, z), (xb, yb, z + 0.45)], [0.012, 0.012], blk, 4, cap=False)
        z += 0.9
    B.box((0, 0, Hm + 0.2), (6.6, 0.4, 0.4), blk)                       # the T top
    for side in (-1, 1):
        cx = side * 2.3
        B.tube([(cx - 0.7, -0.1, Hm), (cx - 0.7, -0.1, Hm - 0.6)], [0.015, 0.015], blk, 4, cap=False)
        B.tube([(cx + 0.7, -0.1, Hm), (cx + 0.7, -0.1, Hm - 0.6)], [0.015, 0.015], blk, 4, cap=False)
        for row in range(4):
            zr = Hm - 1.0 - row * 1.05
            B.box((cx, -0.1, zr + 0.42), (1.9, 0.08, 0.08), blk)          # pipe bar
            for k in range(3):
                x = cx - 0.6 + k * 0.6
                B.box((x, -0.2, zr), (0.38, 0.36, 0.42), BLACK())
                B.card((x, -0.39, zr), (0, -1, 0), (0, 0, 1), 0.3, 0.3, REDLAMP() if row == 3 else LAMP())
        B.box((cx - 1.0, -0.1, Hm - 2.6), (0.06, 0.06, 4.4), blk)
        B.box((cx + 1.0, -0.1, Hm - 2.6), (0.06, 0.06, 4.4), blk)
    # line-array speaker hung off one side
    B.tube([(-0.3, -0.5, Hm - 2.0), (-0.3, -0.7, Hm - 5.0)], [0.01, 0.01], blk, 4, cap=False)
    tilt = Matrix.Rotation(math.radians(-8), 3, "X")
    B.box((-0.3, -0.8, Hm - 6.7), (0.75, 0.6, 3.4), BLACK(), tilt)
    export("UV_LightMast", [B.finish("UV_LightMast")])


def crane():
    reset()
    B = Builder()
    white = mat("M_CraneWhite", (0.78, 0.78, 0.76), 0.3, 0.45)
    grey = mat("M_CraneBoom", (0.12, 0.12, 0.13), 0.5, 0.45)
    tyre = mat("M_Tyre", (0.025, 0.025, 0.025), 0.0, 0.85)
    glass = mat("M_CarGlass", (0.02, 0.025, 0.03), 0.2, 0.08)
    B.box((0, 0.8, 1.25), (2.55, 10.4, 1.3), white)                     # carrier deck
    B.box((0, -5.3, 1.6), (2.55, 2.0, 2.4), white)                      # cab
    B.card((0, -6.31, 2.2), (0, -1, 0), (0, 0, 1), 2.2, 0.9, glass)
    for y in (-4.2, -2.6, 1.6, 3.2, 4.8):
        for x in (-1.15, 1.15):
            B.tube([(x - 0.25, y, 0.6), (x + 0.25, y, 0.6)], [0.6, 0.6], tyre, 14, cap=True)
    for y in (-3.4, 4.2):                                               # outriggers down
        for x in (-1, 1):
            B.box((x * 2.3, y, 1.0), (2.2, 0.45, 0.45), white)
            B.box((x * 3.3, y, 0.5), (0.25, 0.25, 1.0), grey)
            B.box((x * 3.3, y, 0.04), (0.8, 0.8, 0.08), grey)
    B.box((0, 3.2, 2.4), (2.4, 3.2, 1.0), grey)                         # turret
    export("UV_CraneBody", [B.finish("UV_CraneBody")])
    reset()
    B = Builder()
    grey = mat("M_CraneBoom", (0.12, 0.12, 0.13), 0.5, 0.45)
    blk = BLACK()
    piv = Vector((0, 3.6, 3.1))
    el, L = math.radians(70), 32.0
    tip = piv + Vector((0, -math.cos(el) * L, math.sin(el) * L))
    secs = 4
    for k in range(secs):                                               # telescoping sections, each a bit thinner
        a = piv + (tip - piv) * (k / secs)
        b = piv + (tip - piv) * ((k + 1) / secs + 0.02)
        r = 0.55 - k * 0.09
        B.tube([tuple(a), tuple(b)], [r, r], grey, 4, cap=True)
    lift = piv + (tip - piv) * 0.22
    B.tube([(0, 1.6, 2.9), tuple(lift)], [0.18, 0.18], grey, 8, cap=False)
    # hanging light rig: a 2 x 6 stack of fixtures facing -Y (the crane's front)
    top = tip + Vector((0, 0, -0.4))
    B.tube([tuple(tip), tuple(top + Vector((0, 0, -1.6)))], [0.02, 0.02], blk, 4, cap=False)
    fz = top.z - 1.6
    B.box((top.x, top.y, fz - 2.0), (1.4, 0.3, 4.2), blk)
    for row in range(6):
        for col in (-0.35, 0.35):
            c = (top.x + col, top.y - 0.25, fz - 0.4 - row * 0.65)
            B.box(c, (0.5, 0.35, 0.5), blk)
            B.card((c[0], c[1] - 0.18, c[2]), (0, -1, 0), (0, 0, 1), 0.38, 0.38, LAMP())
    export("UV_CraneBoom", [B.finish("UV_CraneBoom")])


def barricade():
    reset()
    B = Builder()
    s = STEELB()
    W, Hb = 2.5, 1.1
    for x in (-W / 2 + 0.05, W / 2 - 0.05):
        B.tube([(x, 0, 0.12), (x, 0, Hb)], [0.022, 0.022], s, 6, cap=False)
    for z in (0.18, Hb):
        B.tube([(-W / 2 + 0.05, 0, z), (W / 2 - 0.05, 0, z)], [0.02, 0.02], s, 6, cap=False)
    n = 18
    for k in range(1, n):
        x = -W / 2 + 0.05 + k * (W - 0.1) / n
        B.tube([(x, 0, 0.18), (x, 0, Hb)], [0.009, 0.009], s, 4, cap=False)
    for x in (-W / 2 + 0.2, W / 2 - 0.2):                               # flat feet
        B.box((x, 0, 0.02), (0.06, 0.7, 0.04), s)
        B.tube([(x, 0, 0.04), (x, 0, 0.18)], [0.015, 0.015], s, 4, cap=False)
    export("UV_Barricade", [B.finish("UV_Barricade")])


def hospitality():
    reset()
    B = Builder()
    fab = mat("M_UmbrellaFabric", (0.025, 0.025, 0.028), 0.0, 0.9)
    s = STEELB()
    A, z0, z1 = 1.75, 2.45, 2.85
    rim = [(-A, -A), (A, -A), (A, A), (-A, A)]
    for i in range(4):
        (xa, ya), (xb, yb) = rim[i], rim[(i + 1) % 4]
        B.face([(xa, ya, z0), (xb, yb, z0), (0, 0, z1)], fab)
        B.face([(0, 0, z1), (xb, yb, z0), (xa, ya, z0)], fab)
        B.box(((xa + xb) / 2, (ya + yb) / 2, z0 - 0.1), (abs(xb - xa) + 0.04, abs(yb - ya) + 0.04, 0.2), fab)   # valance
    B.tube([(0, 0, 0.1), (0, 0, z1)], [0.035, 0.035], s, 8, cap=False)
    B.box((0, 0, 0.06), (0.8, 0.8, 0.12), s)
    export("UV_Umbrella", [B.finish("UV_Umbrella")])
    reset()
    B = Builder()
    s = STEELB()
    B.box((0, 0, 1.06), (0.75, 0.75, 0.04), mat("M_TableTop", (0.06, 0.06, 0.065), 0.0, 0.5))
    for x in (-0.33, 0.33):
        for y in (-0.33, 0.33):
            B.tube([(x, y, 0), (x, y, 1.04)], [0.015, 0.015], s, 4, cap=False)
    for z in (0.3,):
        for (a, b) in (((-0.33, -0.33), (0.33, -0.33)), ((0.33, -0.33), (0.33, 0.33)), ((0.33, 0.33), (-0.33, 0.33)), ((-0.33, 0.33), (-0.33, -0.33))):
            B.tube([(a[0], a[1], z), (b[0], b[1], z)], [0.01, 0.01], s, 4, cap=False)
    export("UV_HighTable", [B.finish("UV_HighTable")])
    reset()
    B = Builder()
    up = mat("M_SofaFabric", (0.04, 0.042, 0.045), 0.0, 0.85)
    B.box((0, 0, 0.21), (2.0, 0.85, 0.42), up)
    B.box((0, 0.33, 0.6), (2.0, 0.2, 0.45), up)
    for x in (-0.92, 0.92):
        B.box((x, 0, 0.5), (0.16, 0.85, 0.2), up)
    export("UV_Sofa", [B.finish("UV_Sofa")])


def riser():
    reset()
    B = Builder()
    blk = BLACK()
    s = STEELB()
    W, D, h = 6.0, 4.0, 1.6
    B.box((0, 0, h / 2), (W, D, h), blk)
    for (a, b) in (((-W / 2, -D / 2), (W / 2, -D / 2)), ((-W / 2, -D / 2), (-W / 2, D / 2)), ((W / 2, -D / 2), (W / 2, D / 2))):
        for z in (h + 0.5, h + 1.0):
            B.tube([(a[0], a[1], z), (b[0], b[1], z)], [0.02, 0.02], s, 4, cap=False)
        for t in (0.0, 0.5, 1.0):
            x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            B.tube([(x, y, h), (x, y, h + 1.0)], [0.02, 0.02], s, 4, cap=False)
    for k in range(6):                                                  # stairs at the back
        B.box((W / 2 - 0.8, D / 2 + 0.15 + k * 0.28, (k + 1) * h / 7 / 2), (1.2, 0.28, (k + 1) * h / 7), blk)
    for x in (-1.5, 1.5):                                               # cameras on tripods
        for a in (90, 210, 330):
            r = math.radians(a)
            B.tube([(x + 0.45 * math.cos(r), 0.45 * math.sin(r), h), (x, 0, h + 1.35)], [0.015, 0.015], s, 4, cap=False)
        B.box((x, -0.1, h + 1.55), (0.3, 0.7, 0.35), blk)
        B.tube([(x, -0.45, h + 1.6), (x, -0.85, h + 1.6)], [0.09, 0.08], blk, 10, cap=True)
    export("UV_Riser", [B.finish("UV_Riser")])


def trailer():
    reset()
    B = Builder()
    w = mat("M_TrailerWhite", (0.86, 0.87, 0.87), 0.2, 0.45)
    tyre = mat("M_Tyre", (0.025, 0.025, 0.025), 0.0, 0.85)
    blk = BLACK()
    L, Wd = 16.0, 2.6
    B.box((0, 0, 2.7), (Wd, L, 3.0), w)
    B.box((0, 0, 1.12), (Wd - 0.3, L - 0.4, 0.25), blk)
    for y in (L / 2 - 2.2, L / 2 - 3.5):
        for x in (-1.0, 1.0):
            B.tube([(x - 0.25, y, 0.52), (x + 0.25, y, 0.52)], [0.52, 0.52], tyre, 14, cap=True)
    for x in (-0.9, 0.9):                                               # landing legs at the front
        B.box((x, -L / 2 + 3.0, 0.6), (0.15, 0.15, 1.1), blk)
    for k in range(3):                                                  # steps up to the doors
        B.box((Wd / 2 + 0.4, -2.0 + k * 4.5, 0.5), (0.8, 1.0, 1.0), blk)
    export("UV_Trailer", [B.finish("UV_Trailer")])


JOBS = {"stage": stage, "screen": led_screen, "mast": light_mast, "crane": crane, "barricade": barricade,
        "hospitality": hospitality, "riser": riser, "trailer": trailer}
ONLY = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
for name, fn in JOBS.items():
    if not ONLY or name in ONLY:
        fn()
print("ALL DONE")
