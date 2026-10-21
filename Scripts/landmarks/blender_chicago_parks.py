"""Sky City: Chicago parks, museums, statues and landmark buildings on the Chicago side of the map (chicago-parks agent,
night of 20-21 Oct 2026), modelled procedurally in headless Blender and exported as GLB (one file per asset).

Why: Kenny asked for "all the structures in the surrounding areas: parks, stadiums, land marks, boats, the locks, docks,
statues, etc". This script does the Chicago side's parks, monuments, statues and landmark buildings on land; the lock,
harbours, docks, boats and lighthouse are chicago-water's (other scripts). Navy Pier, Cloud Gate and Buckingham Fountain
are Scripts/landmarks/blender_landmarks.py (finished, not touched here).

Conventions (same as blender_landmarks.py, whose Builder / PlanBuilder / material helpers this script imports):
  * real-world metres; Blender (x, y, z) m -> Unreal (x, -y, z) * 100 cm (glTF import), Blender +X = Unreal +X = plan north;
  * EVERY asset here is a site asset: modelled in the PLAN frame of Saved/Mashup/plan_v3.json (x east, y north, metres)
    relative to its own origin (ASSETS[name]["origin"], a real position from OpenStreetMap / NAIP), turned -90 deg about Z
    at export by PlanBuilder.finish, so Unreal places it at that origin with NO rotation
    (Scripts/roads/place_chicago_parks_ue.py reads SourceArt/Landmarks/parks/parks.json written here);
  * z = 0 is the local ground (the placement traces the ground at the origin);
  * one bmesh per asset with per-face material slots (M_*); Unreal maps each slot to MI_PK_* / MI_LM_* / city surfaces;
  * <name>_Col assets are invisible simple colliders (boxes) for tall buildings whose facade relief would make the
    Roadster's wall ride bumpy: the visual mesh then has no collision.
  * stylised stand-ins for the artists' sculptures that are still in copyright (Calder, Miro, Chagall, Plensa, Gehry, as
    Cloud Gate was done): recognisable silhouettes and colours, no copied surface detail.
References (photos, NAIP aerials, OSM extracts, sources.txt): SourceArt/Reference/ChicagoParks/<site>/.

Assets (SourceArt/Landmarks/parks/meshes/<name>.glb; placement data in parks.json):
  Millennium Park   PK_PritzkerPavilion (stage house, stylised Gehry headdress, 4,000 seats, lawn, promenade),
                    PK_PritzkerTrellis (pipe arches + pylons), PK_BPBridge (285 m snaking deck, drivable), PK_CrownFountain
                    (stylised towers + pool), PK_Peristyle (Millennium Monument), PK_LurieGarden, PK_MillenniumPavilions
  Maggie Daley      PK_MaggieDaley (climbing wall, skating ribbon, fieldhouse, play garden features)
  Art Institute     PK_ArtInstitute (+Steps), PK_ArtInstituteLions (Kemeys 1894), Modern Wing, Nichols Bridgeway
  Grant Park        PK_CongressPlaza (Bowman / Spearman, pylons), PK_LincolnHeadOfState (+Steps), PK_LoganMonument,
                    PK_SpiritOfMusic, PK_PetrilloShell, PK_GreatLakesFountain, PK_StockExchangeArch, PK_GrantParkRail
                    (Metra tracks at grade), PK_PathsMillennium / PK_PathsGrantNorth / PK_PathsGrantSouth (OSM footpaths)
  Loop plazas       PK_ChicagoPicasso (+Daley Plaza), PK_Flamingo (+Federal Plaza), PK_FourSeasons (+Chase Plaza),
                    PK_MiroChicago, PK_ChicagoTheatre, PK_HealdSquare
  Buildings that replace City Sample towers on their real sites (zone "buildings": whole City Sample footprints removed):
                    PK_CulturalCenter, PK_AuditoriumBuilding, PK_HaroldWashingtonLibrary, PK_BoardOfTrade, PK_AonCenter(+_Col),
                    PK_TwoPrudential(+_Col), PK_LakePointTower(+_Col), PK_VistaTower(+_Col), PK_CarbideCarbon
  Streeterville     PK_OlivePark (+Jets)
  (reference only, handed to the willis-tower agent: willis_tower() -> PK_WillisTower(+_Col), job "willis_ref")

Run (repo root):
  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/landmarks/blender_chicago_parks.py [-- jobs...]
    jobs: see JOBS at the bottom (default: all); writes SourceArt/Landmarks/parks/meshes/*.glb + parks.json
  ... -P Scripts/landmarks/blender_chicago_parks.py -- --render [names...]
    renders SourceArt/Landmarks/parks/preview_<name>.png
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
sys.path.insert(0, ROOT + "/Scripts/landmarks")
import blender_landmarks as BL                                    # noqa: E402  (shared Builder / materials / export)
from blender_landmarks import Builder, PlanBuilder, mat, ccw, offset_poly, arc, rrect, circle, tri_count   # noqa: E402

BASE = ROOT + "/SourceArt/Landmarks/parks"
OUT = BASE + "/meshes"
os.makedirs(OUT, exist_ok=True)
BL.OUT = OUT                                                       # BL.export writes here
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

# ------------------------------------------------------------------ materials (added to blender_landmarks.MATDEF)
BL.MATDEF.update({
    #  name               base colour             metal rough  extra
    "M_TowerBlack": ((0.025, 0.025, 0.028), 0.8, 0.35, {}),       # Willis: black anodised aluminium skin
    "M_TintedGlass": ((0.05, 0.042, 0.035), 0.6, 0.06, {}),       # bronze-tinted glass
    "M_Louvre": ((0.06, 0.06, 0.065), 0.5, 0.6, {}),              # mechanical-floor louvres
    "M_Stainless": ((0.78, 0.79, 0.81), 1.0, 0.22, {}),           # brushed stainless (Pritzker ribbons, BP Bridge)
    "M_PipeWhite": ((0.86, 0.87, 0.88), 0.3, 0.40, {}),           # trellis pipes
    "M_SeatRed": ((0.50, 0.05, 0.04), 0.0, 0.55, {}),
    "M_WoodLight": ((0.55, 0.37, 0.21), 0.0, 0.60, {}),           # stage shell, bridge decks
    "M_LEDBright": ((0.95, 0.88, 0.80), 0.0, 0.30, {"emit": 1.6}),  # Crown Fountain screens (a face, stylised)
    "M_LEDMid": ((0.62, 0.45, 0.36), 0.0, 0.30, {"emit": 1.0}),
    "M_LEDDark": ((0.16, 0.10, 0.08), 0.0, 0.30, {"emit": 0.5}),
    "M_LEDSkin": ((0.80, 0.60, 0.48), 0.0, 0.30, {"emit": 1.3}),
    "M_GlassBlock": ((0.80, 0.86, 0.88), 0.0, 0.15, {}),          # glass-brick skin
    "M_GraniteBlack": ((0.025, 0.025, 0.03), 0.0, 0.12, {}),      # polished black granite (wet pool)
    "M_CorTen": ((0.27, 0.11, 0.05), 0.3, 0.75, {}),              # weathering steel (Picasso, Daley Center)
    "M_CalderRed": ((0.78, 0.10, 0.04), 0.1, 0.50, {}),           # 'Calder red' vermilion
    "M_LionBronze": ((0.14, 0.18, 0.14), 0.8, 0.45, {}),          # dark bronze with green patina (Art Institute lions)
    "M_Gravel": ((0.55, 0.52, 0.47), 0.0, 0.95, {}),
    "M_ClimbGrey": ((0.58, 0.59, 0.60), 0.1, 0.70, {}),           # Maggie Daley climbing wall
    "M_Ice": ((0.86, 0.91, 0.95), 0.0, 0.10, {}),                 # skating ribbon (winter ice; reads as a pale path)
    "M_SignBulb": ((1.00, 0.88, 0.62), 0.0, 0.40, {"emit": 8.0}), # theatre sign bulbs
    "M_SignRed": ((0.80, 0.06, 0.04), 0.0, 0.45, {"emit": 3.0}),
    "M_Marble": ((0.85, 0.84, 0.80), 0.0, 0.45, {}),
    "M_MosaicRed": ((0.60, 0.15, 0.10), 0.0, 0.50, {}),
    "M_MosaicGreen": ((0.20, 0.42, 0.30), 0.0, 0.50, {}),
    "M_MosaicWhite": ((0.82, 0.80, 0.74), 0.0, 0.50, {}),
    "M_Rubber": ((0.12, 0.30, 0.45), 0.0, 0.90, {}),              # playground safety surface
    "M_PaintYellow": ((0.85, 0.65, 0.10), 0.2, 0.50, {}),
    "M_TerraCotta": ((0.86, 0.83, 0.76), 0.0, 0.60, {}),          # white glazed terra cotta (Wrigley-style)
    "M_GoldLeaf": ((0.80, 0.62, 0.25), 1.0, 0.30, {}),
    "M_GlassTeal": ((0.06, 0.20, 0.24), 0.6, 0.06, {}),           # St. Regis blue-green glass
    "M_Salvia": ((0.22, 0.12, 0.38), 0.0, 0.85, {}),              # Lurie Garden's purple 'river' of salvia
    "M_Grasses": ((0.55, 0.50, 0.30), 0.0, 0.90, {}),             # prairie grasses
})

META = {}          # asset -> placement info, written to parks.json
PREVIEW_LAYOUT = {}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    BL.MATS.clear()


def P2(pts, o):
    """World plan points -> site-local (relative to origin o)."""
    return [(x - o[0], y - o[1]) for x, y in pts]


def rotate_verts(B, deg, about=(0.0, 0.0)):
    """Rotate every vertex built so far counter-clockwise (plan frame, before finish) about a plan-local point."""
    R = Matrix.Rotation(math.radians(deg), 4, "Z")
    T = Matrix.Translation((about[0], about[1], 0.0))
    bmesh.ops.transform(B.bm, matrix=T @ R @ T.inverted(), verts=B.bm.verts)


PROBES = {     # where to trace the ground for assets whose origin lies on a street (the parks / plazas stand 15 cm higher)
    "PK_BPBridge": (538.0, -613.0), "PK_CongressPlaza": (338.0, -1268.0), "PK_PathsGrantSouth": (700.0, -1450.0),
    "PK_PathsGrantNorth": (660.0, -1060.0), "PK_GrantParkRail": (482.0, -1400.0),
    # the plan cut these fountains' pools out of the ground as water: probe the park beside them
    "PK_CrownFountain": (318.0, -671.0), "PK_CrownFountainWater": (318.0, -671.0), "PK_GreatLakesFountain": (352.0, -985.0),
    "PK_Peristyle": (330.0, -418.0), "PK_PathsMillennium": (420.0, -600.0),
}


def export_site(name, B, origin, meta=None, collide="complex", zone=None, layer="parks", record=True):
    """Finish a PlanBuilder and export it; record placement info for place_chicago_parks_ue.py.
    collide: 'complex' (complex-as-simple), 'none' (visual only), 'hidden' (an invisible collider)."""
    ob = B.finish(name)
    m = dict(meta or {})
    m["frame"] = "plan-local (x east, y north) turned -90 deg: place in Unreal at the origin with NO rotation"
    BL.export(name, [ob], m)
    rec = dict(BL.META[name])
    rec["file"] = f"SourceArt/Landmarks/parks/meshes/{name}.glb"
    rec.update({"origin_plan_m": [round(origin[0], 2), round(origin[1], 2)], "collide": collide})
    if zone:
        rec["zone"] = zone
    if name in PROBES:
        rec["ground_probe_plan_m"] = list(PROBES[name])
    if record:                        # record=False: GLB only, not placed by place_chicago_parks_ue.py
        META[name] = rec
    return ob


# ------------------------------------------------------------------ shared small parts
def tube_poly(B, pts, r, m, sides=8, smooth=True):
    B.tube([Vector(p) for p in pts], [r] * len(pts), m, sides, smooth=smooth)


def limb(B, pts, radii, m, sides=8):
    """Capped smooth tube (statue limbs, necks, tails)."""
    B.tube([Vector(p) for p in pts], list(radii), m, sides, cap0=True, cap1=True)


def lamp_post(B, x, y, h=4.2, m="M_Railing"):
    B.cyl((x, y, 0.0), h, 0.07, m, 8)
    B.lathe([(0.0, h), (0.26, h + 0.1), (0.3, h + 0.35), (0.0, h + 0.62)], "M_Light", 8, center=(x, y, 0))


def bench(B, x, y, yaw_deg, L=1.8):
    a = math.radians(yaw_deg)
    R = Matrix.Rotation(a, 3, "Z")
    B.box((x, y, 0.42), (L, 0.45, 0.06), "M_Timber", R)
    B.box((x - math.sin(a) * 0.2, y + math.cos(a) * 0.2, 0.68), (L, 0.06, 0.4), "M_Timber", R)


def tree_ball(B, x, y, h=7.0, r=2.6, m="M_Hedge", z=0.0):
    B.cyl((x, y, z), h * 0.45, 0.18, "M_Timber", 6)
    B.ellipsoid((x, y, z + h * 0.62), (r, r, r * 0.85), m, 10, 6)


# ================================================================== 1. Willis Tower (REFERENCE ONLY: handed to the "willis-tower" agent)
# The coordinator gave the Willis Tower its own agent at 23:10 on 20 Oct. This builder is kept for that agent to use; it is
# not in the default jobs and its GLBs are not recorded in parks.json (record=False), so place_chicago_parks_ue.py never
# places it. Export the reference GLBs with:  ... -P Scripts/landmarks/blender_chicago_parks.py -- willis_ref
# OSM building:part data (heights) + the published 75 ft (22.86 m) tubes; technical floors 29-32, 64-65, 88-89, 104-108
# (Willis Tower scheme, Commons), Skydeck Ledge at 413 m on the west face; antennas to 527 m (OSM).
WILLIS = dict(
    origin=(-671.5, -959.4),          # tower centre (OSM tube outlines)
    yaw=1.1,                          # the tower (and the Chicago grid here) is turned 1.1 deg CCW from plan axes (OSM edges)
    tube=22.86, storey=3.92,
    # tube heights (m) by (col, row): col 0 = west, row 0 = south (OSM)
    H={(0, 0): 260.0, (1, 0): 355.0, (2, 0): 200.0,
       (0, 1): 442.0, (1, 1): 442.0, (2, 1): 355.0,
       (0, 2): 200.0, (1, 2): 355.0, (2, 2): 260.0},
    mech=[(29, 32), (64, 65), (88, 89), (104, 108)],
)
# Catalog podium (2019-22) and the low wings: OSM building:part polygons (world plan m) and heights
WILLIS_PODIUM = [
    (20.0, [(-722.4, -971.0), (-706.1, -970.7), (-705.6, -995.0), (-681.7, -994.5), (-681.8, -1021.4), (-658.3, -1021.0),
            (-658.8, -994.0), (-636.0, -993.8), (-635.4, -1024.8), (-658.6, -1025.2), (-658.5, -1030.7), (-681.2, -1031.1),
            (-681.3, -1025.4), (-721.4, -1026.1)]),
    (25.0, [(-710.8, -998.1), (-710.4, -1015.6), (-690.4, -1015.3), (-690.8, -997.9)]),
    (18.0, [(-713.5, -1026.0), (-713.5, -1035.7), (-694.7, -1035.4), (-694.8, -1025.7)]),
    (10.0, [(-721.4, -1026.1), (-721.2, -1035.8), (-713.5, -1035.7), (-713.5, -1026.0)]),
    (10.0, [(-694.8, -1025.7), (-681.3, -1025.4), (-681.1, -1035.1), (-694.7, -1035.4)]),
    (10.0, [(-636.4, -970.2), (-630.5, -970.6), (-629.3, -1034.3), (-658.4, -1034.8), (-658.6, -1025.2), (-635.4, -1024.8),
            (-636.0, -993.8)]),
    (18.0, [(-715.1, -949.1), (-706.5, -948.9), (-706.1, -970.7), (-714.7, -970.8)]),
    (20.0, [(-723.3, -926.2), (-722.8, -949.2), (-706.5, -948.9), (-707.0, -925.9)]),
    (10.0, [(-707.0, -925.9), (-723.3, -926.2), (-723.5, -917.5), (-696.9, -917.0), (-696.9, -924.8), (-707.0, -925.0)]),
    (10.0, [(-636.8, -946.9), (-630.9, -947.0), (-631.5, -915.9), (-651.6, -916.3), (-651.4, -924.0), (-637.4, -923.7)]),
    (5.0, [(-696.9, -917.0), (-696.9, -924.8), (-651.4, -924.0), (-651.6, -916.3)]),
]


def facade_face(B, p0, p1, z0, z1, out, storey, mech_z, col_step=4.572, mull=2):
    """One exposed tube face from p0 to p1 (plan-local, counter-clockwise seen from outside), z0..z1: glass plane, black
    spandrel strip at every floor, louvre bands on the mechanical floors, column covers every 15 ft with mullions between."""
    p0, p1 = Vector((p0[0], p0[1], 0)), Vector((p1[0], p1[1], 0))
    t = (p1 - p0)
    W = t.length
    t.normalize()
    n = Vector((out[0], out[1], 0))
    if z1 - z0 < 0.5:
        return
    # glass
    B.face([p0 + Vector((0, 0, z0)), p1 + Vector((0, 0, z0)), p1 + Vector((0, 0, z1)), p0 + Vector((0, 0, z1))], "M_TintedGlass",
           [(0, z0), (W, z0), (W, z1), (0, z1)])
    # spandrels (one quad per floor, 5 cm proud) and louvre bands
    k0 = int(math.ceil(z0 / storey - 1e-6))
    k1 = int(math.floor(z1 / storey + 1e-6))
    for k in range(k0, k1 + 1):
        z = k * storey
        a, b = max(z0, z - 0.55), min(z1, z + 0.55)
        if b - a < 0.05:
            continue
        o = n * 0.05
        B.face([p0 + o + Vector((0, 0, a)), p1 + o + Vector((0, 0, a)), p1 + o + Vector((0, 0, b)), p0 + o + Vector((0, 0, b))], "M_TowerBlack")
    for a, b in mech_z:
        a, b = max(a, z0), min(b, z1)
        if b - a > 0.1:
            o = n * 0.03
            B.face([p0 + o + Vector((0, 0, a)), p1 + o + Vector((0, 0, a)), p1 + o + Vector((0, 0, b)), p0 + o + Vector((0, 0, b))], "M_Louvre")
    # column covers (0.6 m wide, 0.22 m proud) every 15 ft incl. the corners, mullions (0.12 m, 0.12 proud) between
    nc = int(round(W / col_step))
    for i in range(nc + 1):
        s = W * i / nc
        c = p0 + t * s + n * 0.11
        B.beam((c.x, c.y, z0), (c.x, c.y, z1), 0.6, 0.22, "M_TowerBlack", up=(n.x, n.y, 0))
        if i < nc:
            for j in range(1, mull + 1):
                s2 = s + (W / nc) * j / (mull + 1)
                c2 = p0 + t * s2 + n * 0.06
                B.beam((c2.x, c2.y, z0), (c2.x, c2.y, z1), 0.12, 0.12, "M_TowerBlack", up=(n.x, n.y, 0))


def willis_tower():
    W = WILLIS
    o = W["origin"]
    T, st = W["tube"], W["storey"]
    H = W["H"]
    mech_z = [((a - 1) * st, b * st) for a, b in W["mech"]]
    B = PlanBuilder()
    C = PlanBuilder()                      # invisible collider: one box per tube + the podium blocks
    x0 = -1.5 * T
    y0 = -1.5 * T
    hgt = lambda c, r: H.get((c, r), 0.0)
    for (c, r), h in H.items():
        xa, ya = x0 + c * T, y0 + r * T
        xb, yb = xa + T, ya + T
        # faces: (p0, p1, outward normal, neighbour)
        for p0, p1, nrm, nb in (((xa, ya), (xb, ya), (0, -1), (c, r - 1)), ((xb, ya), (xb, yb), (1, 0), (c + 1, r)),
                                ((xb, yb), (xa, yb), (0, 1), (c, r + 1)), ((xa, yb), (xa, ya), (-1, 0), (c - 1, r))):
            zb = hgt(*nb)
            if h > zb + 0.5:
                facade_face(B, p0, p1, zb, h, nrm, st, mech_z)
        # roof: membrane (white on the 50 / 66-storey tubes, OSM roof:colour), parapet
        B.face([(xa, ya, h), (xb, ya, h), (xb, yb, h), (xa, yb, h)], "M_Concrete" if h < 300 else "M_RoofFlat")
        for p0, p1 in (((xa, ya), (xb, ya)), ((xb, ya), (xb, yb)), ((xb, yb), (xa, yb)), ((xa, yb), (xa, ya))):
            B.beam((p0[0], p0[1], h + 0.6), (p1[0], p1[1], h + 0.6), 0.5, 1.2, "M_TowerBlack")
        C.boxmm((xa - 0.22, ya - 0.22, 0.0), (xb + 0.22, yb + 0.22, h + 1.2), "M_Concrete")
    # round rooftop drums on the 50- and 66-storey tubes (OSM 'metal' parts r 4.4 m, 5 m tall)
    for (c, r) in ((0, 0), (2, 0), (0, 2), (2, 2)):
        h = hgt(c, r)
        cx, cy = x0 + (c + 0.5) * T, y0 + (r + 0.5) * T
        cx += -4.0 if c == 0 else 4.0
        cy += -4.0 if r == 0 else 4.0
        B.cyl((cx, cy, h), 5.0, 4.4, "M_WheelWhite", 20)
    # top penthouse block and the two antennas (OSM: 527 m, at plan (-669.3, -959.2) and (-696.0, -959.5))
    top = 442.0
    B.boxmm((x0 + 0.25 * T, y0 + 1.15 * T, top), (x0 + 1.75 * T, y0 + 1.85 * T, top + 3.0), "M_TowerBlack")
    for ax in (-669.3 - o[0], -696.0 - o[0]):
        ay = -959.3 - o[1]
        z_a, z_b = top + 3.0, 527.0
        prof = [(1.9, z_a), (1.6, z_a + 25.0), (1.0, z_a + 50.0), (0.55, z_a + 70.0), (0.25, z_b - 6.0), (0.1, z_b), (0.0, z_b + 0.01)]
        B.lathe(prof, "M_WheelWhite", 4, a0=math.pi / 4, smooth=False, center=(ax, ay, 0))
        for zz in (z_a + 18.0, z_a + 38.0, z_a + 58.0):
            B.lathe([(1.6 - (zz - z_a) * 0.02, zz), (1.95 - (zz - z_a) * 0.02, zz + 0.3), (1.6 - (zz - z_a) * 0.02, zz + 1.2)], "M_Railing", 4,
                    a0=math.pi / 4, smooth=False, center=(ax, ay, 0))
        B.lathe([(0.0, z_b - 0.3), (0.35, z_b), (0.0, z_b + 0.35)], "M_SignRed", 6, center=(ax, ay, 0))      # beacon
    # smaller masts on the top roof
    for dx, dy, hh in ((-12.0, 4.0, 30.0), (-8.0, -5.0, 22.0), (6.0, 6.0, 18.0), (14.0, -3.0, 26.0)):
        B.cyl((x0 + 1.0 * T + dx, y0 + 1.5 * T + dy, top + 3.0), hh, 0.35, "M_WheelWhite", 6)
    # the Ledge: four glass boxes on the west face at the 103rd floor (413 m)
    zl = 413.0 - 1.0
    xw = x0 - 0.22
    for k in range(4):
        yc = y0 + 1.5 * T + (k - 1.5) * 3.6
        xo = xw - 1.3
        B.boxmm((xo, yc - 1.5, zl - 0.12), (xw, yc + 1.5, zl), "M_TowerBlack")
        for (ya_, yb_) in ((yc - 1.5, yc + 1.5),):
            B.face([(xo, ya_, zl), (xo, yb_, zl), (xo, yb_, zl + 3.1), (xo, ya_, zl + 3.1)], "M_Glass")
            B.face([(xo, ya_, zl), (xo, ya_, zl + 3.1), (xw, ya_, zl + 3.1), (xw, ya_, zl)], "M_Glass")
            B.face([(xo, yb_, zl), (xw, yb_, zl), (xw, yb_, zl + 3.1), (xo, yb_, zl + 3.1)], "M_Glass")
            B.face([(xo, ya_, zl + 3.1), (xo, yb_, zl + 3.1), (xw, yb_, zl + 3.1), (xw, ya_, zl + 3.1)], "M_Glass")
    rotate_verts(B, W["yaw"])
    rotate_verts(C, W["yaw"])
    # podium and low wings (already in the world frame)
    for h, poly in WILLIS_PODIUM:
        loc = P2(poly, o)
        B.slab(loc, 0.0, h - 0.6, "M_RoofFlat", "M_TintedGlass")
        # black fascia band and mullions around the top
        B.sweep_closed(loc, [(0.05, h - 1.6), (0.15, h - 1.6), (0.15, h), (0.0, h)], "M_TowerBlack")
        B.face([(x, y, h - 0.02) for x, y in ccw(loc)], "M_RoofFlat")
        for (ax, ay), (bx, by) in zip(ccw(loc), ccw(loc)[1:] + ccw(loc)[:1]):
            L = math.hypot(bx - ax, by - ay)
            nm = int(L / 1.6)
            for i in range(1, nm):
                tq = i / nm
                B.beam((ax + (bx - ax) * tq, ay + (by - ay) * tq, 0.0), (ax + (bx - ax) * tq, ay + (by - ay) * tq, h - 1.6), 0.08, 0.1, "M_TowerBlack")
        C.slab(loc, 0.0, h, "M_Concrete")
    # Willis Terrace roof garden on the 20 m podium (south) and the Wacker Drive entrance canopy (west, glass vault)
    B.slab(P2([(-704.0, -998.0), (-660.0, -997.0), (-660.0, -1019.0), (-704.0, -1019.5)], o), 20.0, 20.25, "M_Lawn")
    cx = -722.4 - o[0]
    for k in range(9):
        yy = (-930.0 - o[1]) - k * 4.5
        B.tube([Vector((cx, yy, 7.5)), Vector((cx - 5.0, yy, 6.8)), Vector((cx - 9.0, yy, 5.6))], [0.12] * 3, "M_TowerBlack", 6)
    B.face([(cx, -930.0 - o[1], 7.5), (cx, -966.0 - o[1], 7.5), (cx - 9.0, -966.0 - o[1], 5.6), (cx - 9.0, -930.0 - o[1], 5.6)], "M_Glass")
    B.face([(cx - 9.0, -930.0 - o[1], 5.6), (cx - 9.0, -966.0 - o[1], 5.6), (cx, -966.0 - o[1], 7.5), (cx, -930.0 - o[1], 7.5)], "M_Glass")
    zone = {"poly": [(-724.0, -1037.0), (-628.0, -1036.0), (-629.0, -914.0), (-725.0, -915.0)], "clear": ["props", "buildings"]}
    export_site("PK_WillisTower", B, o, {"what": "Willis Tower: 9 bundled tubes 22.86 m (OSM heights 200/260/355/442 m), antennas to 527 m, "
                                                 "technical-floor louvre bands, the Ledge at 413 m, Catalog podium"}, collide="none", zone=zone,
                record=False)
    export_site("PK_WillisTower_Col", C, o, {"what": "invisible collider for PK_WillisTower (one box per tube + podium blocks)"}, collide="hidden",
                record=False)


# ================================================================== 2. Millennium Park
def catmull(pts, n):
    """Catmull-Rom spline through 3-D control points, n samples (inclusive ends)."""
    P = [Vector(p) for p in pts]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    segs = len(P) - 3
    out = []
    for k in range(n):
        t = k / (n - 1) * segs
        i = min(int(t), segs - 1)
        u = t - i
        p0, p1, p2, p3 = P[i], P[i + 1], P[i + 2], P[i + 3]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3))
    return out


def ribbon(B, bottom, top, m, bulge=(0, 0, 0), nu=14, nv=8, thick=0.35):
    """A curved stainless 'ribbon' sheet lofted from a bottom edge curve to a top edge curve (control points), bowed by
    `bulge` at mid-height; closed slab of thickness `thick` (front, back and the four edges)."""
    A = catmull(bottom, nu)
    Bc = catmull(top, nu)
    bv = Vector(bulge)
    F = [[A[i].lerp(Bc[i], j / (nv - 1)) + bv * math.sin(math.pi * j / (nv - 1)) * math.sin(math.pi * (0.15 + 0.7 * i / (nu - 1)))
          for j in range(nv)] for i in range(nu)]
    # normals by finite differences
    N = []
    for i in range(nu):
        row = []
        for j in range(nv):
            du = F[min(i + 1, nu - 1)][j] - F[max(i - 1, 0)][j]
            dv = F[i][min(j + 1, nv - 1)] - F[i][max(j - 1, 0)]
            n_ = du.cross(dv)
            row.append(n_.normalized() if n_.length > 1e-9 else Vector((0, 0, 1)))
        N.append(row)
    Bk = [[F[i][j] - N[i][j] * thick for j in range(nv)] for i in range(nu)]
    B.grid(F, m, smooth=True)
    B.grid([list(reversed(r)) for r in Bk], m, smooth=True)
    # edges
    for i in range(nu - 1):
        for j in (0, nv - 1):
            a, b, c, d = F[i][j], F[i + 1][j], Bk[i + 1][j], Bk[i][j]
            B.face([a, b, c, d] if j == 0 else [d, c, b, a], m)
    for j in range(nv - 1):
        for i in (0, nu - 1):
            a, b, c, d = F[i][j], F[i][j + 1], Bk[i][j + 1], Bk[i][j]
            B.face([a, b, c, d] if i == nu - 1 else [d, c, b, a], m)


PRITZKER = dict(stage=(492.5, -458.0))     # centre of the proscenium front line (OSM pavilion footprint 443..536.5 x -458.7..-437.3)


def trellis_outline(n=80, north=-462.0):
    """Plan outline of the trellis / Great Lawn (NAIP): 95 m wide from the stage (y -462) to y -545, then an elliptical
    end to the tip at y -641 (published 600 x 300 ft = 183 x 91 m). Clockwise from the north-west corner."""
    cx, w = 493.5, 47.5
    return [(cx - w, north), (cx + w, north)] + [(cx + w * math.cos(math.pi * k / n), -545.0 - 96.0 * math.sin(math.pi * k / n))
                                                   for k in range(n + 1)]


def clip_line_poly(p, d, poly):
    """Intersections of the infinite line p + t d with a closed polygon -> (t_min, t_max) or None."""
    ts = []
    n = len(poly)
    for i in range(n):
        a, b = Vector(poly[i]), Vector(poly[(i + 1) % n])
        e = b - a
        den = d.x * e.y - d.y * e.x
        if abs(den) < 1e-9:
            continue
        w = a - p
        t = (w.x * e.y - w.y * e.x) / den
        u = (w.x * d.y - w.y * d.x) / den
        if 0 <= u <= 1:
            ts.append(t)
    if len(ts) < 2:
        return None
    return min(ts), max(ts)


def pritzker_pavilion():
    o = PRITZKER["stage"]
    B = PlanBuilder()
    # --- stage house (concrete, 30 m wide x 15 m tall orchestra shell inside), proscenium glass doors folded open
    B.boxmm((-21.0, 0.0, 0.0), (21.0, 24.0, 21.0), "M_Concrete")
    B.boxmm((-15.0, -0.2, 1.2), (15.0, 18.0, 1.35), "M_WoodLight")                         # stage floor
    B.boxmm((-15.0, -3.5, 0.0), (15.0, 0.0, 1.2), "M_Concrete")                             # stage apron
    # wood-lined shell: back wall, side walls, folded ceiling panels (cut into the concrete house as an inner liner)
    B.face([(-15.0, 17.9, 1.35), (15.0, 17.9, 1.35), (15.0, 17.9, 15.0), (-15.0, 17.9, 15.0)], "M_SeatRed")      # curtain
    B.face([(-15.0, -0.25, 1.35), (-15.0, 17.9, 1.35), (-15.0, 17.9, 15.0), (-15.0, -0.25, 15.0)][::-1], "M_WoodLight")
    B.face([(15.0, -0.25, 1.35), (15.0, 17.9, 1.35), (15.0, 17.9, 15.0), (15.0, -0.25, 15.0)], "M_WoodLight")
    for k in range(5):
        y0, y1 = -0.25 + k * 3.65, -0.25 + (k + 1) * 3.65
        z0, z1 = 15.0 - (k % 2) * 1.2, 15.0 - ((k + 1) % 2) * 1.2
        B.face([(-15.0, y0, z0), (15.0, y0, z0), (15.0, y1, z1), (-15.0, y1, z1)][::-1], "M_WoodLight")
    # cut the opening: the front wall of the house around a 30 x 15 m opening
    B.face([(-21.0, -0.3, 0.0), (-15.0, -0.3, 0.0), (-15.0, -0.3, 21.0), (-21.0, -0.3, 21.0)], "M_Concrete")
    B.face([(15.0, -0.3, 0.0), (21.0, -0.3, 0.0), (21.0, -0.3, 21.0), (15.0, -0.3, 21.0)], "M_Concrete")
    B.face([(-15.0, -0.3, 15.0), (15.0, -0.3, 15.0), (15.0, -0.3, 21.0), (-15.0, -0.3, 21.0)], "M_Concrete")
    # loudspeaker towers either side of the stage (photo)
    for sx in (-1, 1):
        B.cyl((sx * 19.0, -4.0, 0.0), 9.0, 0.3, "M_Steel", 8)
        B.boxmm((sx * 19.0 - 1.4, -5.4, 9.0), (sx * 19.0 + 1.4, -2.6, 13.5), "M_Railing")
    # --- the stainless steel headdress (Gehry): ribbons framing the proscenium, 37-42 m tall (stylised)
    S = "M_Stainless"
    ribbon(B, [(-13, -1, 17), (-28, -6, 15), (-44, -1, 19)], [(-11, -11, 30), (-27, -17, 35), (-43, -10, 38)], S, (0, 4.0, -2.0))     # west scroll
    ribbon(B, [(12, -1, 13), (26, -4, 9), (38, 2, 12)], [(14, -9, 30), (29, -15, 41), (40, -6, 35)], S, (2.0, 5.0, 0.0))              # east cup
    ribbon(B, [(34, 4, 14), (42, 10, 19), (45, 17, 27)], [(30, 0, 37), (36, 6, 42), (39, 13, 40)], S, (3.0, 2.0, 0.0), 10, 7)          # east roll
    ribbon(B, [(-15, -3, 22), (0, -8, 25), (16, -3, 22)], [(-13, -13, 28), (2, -16, 33), (18, -12, 30)], S, (0, 0, 3.0), 12, 6)        # top crossing
    ribbon(B, [(-17, 0, 0.5), (-22, -3, 2), (-30, 2, 4)], [(-16, -2, 15), (-24, -6, 14), (-34, -1, 13)], S, (-1.5, -2.0, 0), 10, 6)    # west wing
    ribbon(B, [(17, 0, 0.5), (22, -3, 2), (28, 3, 4)], [(16, -2, 12.5), (24, -6, 10.5), (30, 0, 10)], S, (1.5, -2.0, 0), 10, 6)        # east wing
    ribbon(B, [(-16, -1, 16.5), (0, -2, 17.5), (16, -1, 16.5)], [(-15, -9, 18.5), (0, -11, 21.0), (15, -9, 19.0)], S, (0, 0, -1.5), 12, 5)  # canopy
    ribbon(B, [(-30, 6, 10), (-40, 12, 14), (-44, 21, 20)], [(-34, 2, 30), (-44, 8, 34), (-46, 17, 32)], S, (-3.0, 1.0, 0), 10, 7)     # back west
    ribbon(B, [(-6, 2, 30), (6, 4, 33), (18, 2, 31)], [(-4, -4, 39), (8, -6, 42), (20, -3, 38)], S, (0, 2.0, 1.0), 10, 6)              # crown
    ribbon(B, [(-26, 2, 24), (-12, 3, 27), (2, 2, 29)], [(-30, -3, 33), (-15, -5, 37), (0, -4, 38)], S, (0, 2.5, 1.5), 12, 6)          # west brow
    ribbon(B, [(18, 3, 22), (28, 6, 26), (36, 10, 30)], [(16, -1, 32), (25, 1, 37), (33, 5, 39)], S, (2.0, 1.5, 0), 10, 6)             # east brow
    ribbon(B, [(-40, 0, 2), (-44, 4, 6), (-46, 10, 12)], [(-36, -4, 16), (-42, -2, 19), (-45, 4, 22)], S, (-2.0, -1.0, 0), 8, 6)       # west skirt
    # steel struts behind the ribbons
    for a, b in (((-30, 2, 0), (-36, 2, 30)), ((32, 4, 0), (36, 6, 36)), ((-10, 20, 21), (-20, 4, 34)), ((10, 20, 21), (22, 4, 34)),
                 ((0, 22, 21), (4, 2, 38)), ((-40, 14, 0), (-42, 14, 26)), ((40, 12, 0), (42, 12, 30))):
        B.rod(a, b, 0.45, "M_Steel", 8)
    # --- fixed seating: 4,000 red seats in raked rows (y -462 .. -506), three aisles, the sound-desk box at the back
    y_front, y_back = -4.5, -48.0
    nrow = 46
    for r in range(nrow):
        y = y_front + (y_back - y_front) * r / (nrow - 1)
        hw = 37.0 + 10.0 * r / (nrow - 1)
        z = 0.014 * r
        for xa, xb in ((-hw, -14.5), (-12.5, -1.0), (1.0, 12.5), (14.5, hw)):
            B.boxmm((xa, y - 0.25, z), (xb, y + 0.25, z + 0.45), "M_SeatRed")
            B.boxmm((xa, y + 0.2, z + 0.45), (xb, y + 0.3, z + 0.85), "M_SeatRed")
        if r:
            B.boxmm((-hw - 1.0, y - 0.5, 0.0), (hw + 1.0, y + 0.45, z), "M_Concrete")
    B.boxmm((-6.0, -51.0, 0.0), (6.0, -46.0, 3.8), "M_Concrete")                            # sound desk
    # paving under the seats and the promenade ring round the lawn
    seat_poly = [(-38.0, -3.0), (38.0, -3.0), (48.0, -50.0), (-48.0, -50.0)]
    B.slab(seat_poly, -0.1, 0.04, "M_GranitePromenade")
    outline = P2(trellis_outline(), o)
    B.sweep_closed(outline, [(0.0, 0.05), (3.5, 0.05), (3.5, -0.1), (0.0, -0.1)], "M_ParkPaver")
    lawn = P2(trellis_outline(80, -508.0), o)
    B.slab(lawn, -0.1, 0.05, "M_Lawn")
    B.sweep_open([(-47.5, -50.2), (47.5, -50.2)], [(0.4, 0.0), (0.4, 0.75), (-0.4, 0.75), (-0.4, 0.0)], "M_Concrete")   # low wall behind the seats
    zone = {"poly": [(440.0, -462.0), (548.0, -462.0), (548.0, -648.0), (440.0, -648.0)], "clear": ["props"]}
    zone2 = [(440.0, -437.0), (548.0, -437.0), (548.0, -462.0), (440.0, -462.0)]
    export_site("PK_PritzkerPavilion", B, o, {"what": "Jay Pritzker Pavilion: stage house, 30 x 15 m orchestra shell, stainless headdress "
                                                       "(stylised Gehry ribbons, 42 m), 4,000 raked seats, sound desk, lawn + promenade"},
                collide="complex", zone={"poly": zone["poly"][:2] + zone["poly"][2:] , "clear": ["props"], "extra": [zone2]})


def pritzker_trellis():
    """The trellis over the Great Lawn: two families of straight-in-plan steel pipe arches at +/-35 deg (NAIP: 14.5 m apart
    along the lawn), springing from concrete pylons round the outline, parabolic in elevation, speakers every ~21 m."""
    o = PRITZKER["stage"]
    B = PlanBuilder()
    outline = P2(trellis_outline(120), o)
    th = math.radians(35.0)
    pylons = []
    for fam in (1, -1):
        d = Vector((math.cos(th), -math.sin(th)))          # east-south; the other family runs west-south
        for k in range(-2, 16):
            p = Vector((-47.5, -6.0 - 14.5 * k)) if fam == 1 else Vector((47.5, -6.0 - 14.5 * k))
            r = clip_line_poly(p, d if fam == 1 else Vector((-d.x, d.y)), outline)
            if not r:
                continue
            dd = d if fam == 1 else Vector((-d.x, d.y))
            a = p + dd * r[0]
            b = p + dd * r[1]
            L = (b - a).length
            if L < 18.0:
                continue
            h0 = 7.5
            hm = h0 + min(15.0, 0.13 * L)
            pts = []
            n = max(8, int(L / 4.0))
            for i in range(n + 1):
                s_ = i / n
                q = a.lerp(b, s_)
                pts.append((q.x, q.y, h0 + (hm - h0) * 4 * s_ * (1 - s_)))
            tube_poly(B, pts, 0.32, "M_PipeWhite", 8)
            for e in (a, b):
                if e.y > -6.0:                       # these land on the pavilion's structure
                    continue
                if not any((e - q).length < 3.0 for q in pylons):
                    pylons.append(e.copy())
            # loudspeaker clusters hanging under the arch every ~21 m
            ns = int(L / 21.0)
            for i in range(1, ns + 1):
                s_ = i / (ns + 1)
                q = a.lerp(b, s_)
                z = h0 + (hm - h0) * 4 * s_ * (1 - s_)
                B.rod((q.x, q.y, z - 0.3), (q.x, q.y, z - 1.6), 0.03, "M_Railing", 4)
                B.boxmm((q.x - 0.45, q.y - 0.45, z - 2.6), (q.x + 0.45, q.y + 0.45, z - 1.6), "M_Railing")
    for q in pylons:
        B.lathe([(0.75, 0.0), (0.75, 6.6), (0.95, 6.9), (0.95, 7.6), (0.0, 7.6)], "M_Concrete", 12, center=(q.x, q.y, 0))
    export_site("PK_PritzkerTrellis", B, o, {"what": "Pritzker Pavilion trellis: pipe arches over the Great Lawn, %d pylons" % len(pylons)},
                collide="complex")


def bp_bridge():
    """BP Pedestrian Bridge (Gehry, 2004): 285 m snaking deck (OSM centreline), 5 % ramps, 6.1 m wide, timber deck between
    stainless steel 'snake' sides, rising from the Pritzker lawn over Columbus Drive (>= 4.1 m clearance) into Maggie Daley
    Park. Drivable (complex collision)."""
    line = [(541.4, -613.4), (547.6, -609.7), (552.2, -605.6), (555.0, -601.2), (555.0, -597.3), (553.7, -593.5), (550.2, -587.9),
            (549.0, -584.3), (548.8, -580.5), (549.8, -577.4), (552.6, -574.2), (555.7, -571.5), (558.1, -568.3), (559.2, -564.7),
            (559.0, -561.3), (558.3, -559.2), (557.2, -555.6), (556.9, -551.7), (557.3, -547.3), (558.6, -543.1), (560.6, -539.3),
            (564.1, -534.0), (568.1, -530.7), (573.0, -527.4), (577.6, -525.2), (582.8, -523.9), (588.6, -523.1), (595.3, -523.0),
            (603.0, -524.2), (609.2, -526.7), (615.2, -530.2), (621.1, -535.3), (623.7, -539.1), (627.9, -546.4), (630.2, -548.5),
            (632.5, -549.6), (635.5, -550.3), (639.1, -549.9), (641.6, -548.5), (643.9, -546.2), (645.1, -543.4), (645.9, -539.5),
            (645.6, -530.4), (646.0, -526.9), (647.0, -523.8), (649.4, -521.0), (653.4, -519.3), (657.1, -519.3), (660.5, -520.3),
            (663.8, -522.8), (665.2, -526.0), (665.4, -529.2), (664.4, -532.7), (660.5, -540.1), (659.0, -544.0), (658.8, -546.9),
            (659.4, -550.9), (660.5, -553.8), (662.6, -555.7), (665.5, -556.3), (669.5, -555.7), (673.9, -555.1), (678.2, -556.0),
            (680.4, -557.4)]
    o = (595.3, -523.0)
    pts2 = catmull([(x - o[0], y - o[1], 0.0) for x, y in line], 260)
    # arc length and height profile: 5 % up from both ends to a 6.2 m crest held over Columbus Drive (x 585..640)
    s = [0.0]
    for a, b in zip(pts2, pts2[1:]):
        s.append(s[-1] + (b - a).length)
    L = s[-1]
    ZC = 6.2
    z = [min(ZC, 0.05 * si, 0.05 * (L - si)) for si in s]
    # smooth the kinks
    for _ in range(25):
        z = [z[0]] + [(z[i - 1] + 2 * z[i] + z[i + 1]) / 4 for i in range(1, len(z) - 1)] + [z[-1]]
    B = PlanBuilder()
    W = 3.05
    rows_F, rows_L, rows_R = [], [], []
    for i, p in enumerate(pts2):
        a = pts2[max(0, i - 1)]
        b = pts2[min(len(pts2) - 1, i + 1)]
        t = (b - a)
        t.z = 0
        t.normalize()
        nl = Vector((-t.y, t.x, 0))
        zz = z[i]
        c = Vector((p.x, p.y, zz))
        # snake side profile (outward from the deck edge): sill, rounded stainless skin 1.1 m above the deck to 1.4 m below
        rows_L.append([c + nl * (W + dx) + Vector((0, 0, dz)) for dx, dz in ((0.0, 0.0), (0.0, 1.05), (0.25, 1.25), (0.55, 1.0), (0.75, 0.2),
                                                                              (0.6, -0.6), (0.2, -0.95), (0.0, -1.0))])
        rows_R.append([c - nl * (W + dx) + Vector((0, 0, dz)) for dx, dz in ((0.0, -1.0), (0.2, -0.95), (0.6, -0.6), (0.75, 0.2), (0.55, 1.0),
                                                                              (0.25, 1.25), (0.0, 1.05), (0.0, 0.0))])
        rows_F.append([c - nl * W, c + nl * W])
    B.grid(rows_F, "M_WoodLight", smooth=False)                    # deck (normal up: rows along the path, columns right -> left)
    B.grid(rows_L, "M_Stainless", smooth=True)
    B.grid(rows_R, "M_Stainless", smooth=True)
    # soffit under the deck
    B.grid([[r[1] + Vector((0, 0, -1.0)), r[0] + Vector((0, 0, -1.0))] for r in rows_F], "M_Steel", smooth=False)
    # piers where the deck is high enough (every ~22 m), never on the plan's carriageways or sidewalks (Columbus Drive)
    rn = json.load(open(ROOT + "/Saved/Roads/roadnet.json"))
    pave = [json.loads(e["ribbon"]) if isinstance(e["ribbon"], str) else e["ribbon"] for e in rn["edges"] if e.get("ribbon")]
    pave += [j["ring"] for j in rn["junctions"]] + list(rn["joints"]) + list(rn["walk"])
    on_pave = _poly_index(pave)
    k = 0
    acc = 0.0
    for i in range(1, len(pts2)):
        acc += (pts2[i] - pts2[i - 1]).length
        if acc >= 22.0 and z[i] > 2.0:
            wx, wy = pts2[i].x + o[0], pts2[i].y + o[1]
            if any(on_pave(wx + dx, wy + dy) for dx in (-2.0, 0.0, 2.0) for dy in (-2.0, 0.0, 2.0)):
                continue
            acc = 0.0
            B.boxmm((pts2[i].x - 0.6, pts2[i].y - 0.6, 0.0), (pts2[i].x + 0.6, pts2[i].y + 0.6, z[i] - 0.95), "M_Concrete")
            k += 1
    export_site("PK_BPBridge", B, o, {"what": "BP Pedestrian Bridge: %.0f m deck, crest %.1f m over Columbus Drive, %d piers" % (L, ZC, k)},
                collide="complex")


def face_pattern(u, v):
    """A stylised, generic close-up face for the Crown Fountain screens on a unit square (u across, v up), filling the
    screen like the real videos: 0 hair/background, 1 shadow, 2 skin, 3 highlight, 4 features (eyes, brows, open mouth)."""
    du, dv = (u - 0.5) / 0.47, (v - 0.47) / 0.50
    r2 = du * du + dv * dv
    if v > 0.86 or r2 > 1.0:
        return 0
    for ex in (0.31, 0.69):
        if ((u - ex) / 0.085) ** 2 + ((v - 0.60) / 0.035) ** 2 < 1.0:
            return 4                              # eyes
        if abs(u - ex) < 0.11 and 0.665 < v < 0.69:
            return 4                              # brows
    if ((u - 0.5) / 0.075) ** 2 + ((v - 0.26) / 0.045) ** 2 < 1.0:
        return 4                                  # open mouth (the spout)
    if abs(u - 0.5) < 0.05 and 0.36 < v < 0.40:
        return 1                                  # under the nose
    if 0.44 < u < 0.48 and 0.40 < v < 0.56:
        return 1                                  # nose side shadow
    if r2 > 0.78:
        return 1                                  # cheek / jaw shading
    if 0.52 < u < 0.56 and 0.42 < v < 0.56:
        return 3                                  # nose highlight
    return 2


def crown_fountain():
    """Crown Fountain (Plensa, 2004; stylised stand-in): two 15.24 m glass-brick towers (7.0 x 4.9 m, OSM footprints at
    (334.8, -646.2) and (336.3, -696.4)) at the ends of a 71 x 15 m black granite reflecting pool; the inner faces show a
    (generic, stylised) face on the LED screen; a sheet of water down every face."""
    o = (335.5, -671.3)
    B = PlanBuilder()
    yaw = math.degrees(math.atan2(336.3 - 334.8, -646.2 - -696.4)) * -1.0           # the pool axis leans ~1.7 deg (OSM)
    # reflecting pool: 15 x 71 m, black granite, a few mm of water (drivable, flat)
    B.slab([(-7.5, -35.5), (7.5, -35.5), (7.5, 35.5), (-7.5, 35.5)], -0.1, 0.06, "M_GraniteBlack")
    B.face([(-7.3, -35.3, 0.065), (7.3, -35.3, 0.065), (7.3, 35.3, 0.065), (-7.3, 35.3, 0.065)], "M_Water")
    for yc, inner in ((25.1, -1), (-25.1, 1)):
        xa, xb, ya, yb = -3.5, 3.5, yc - 2.45, yc + 2.45
        H = 15.24
        # glass-brick skin on the outer three faces, banded every 1.5 m (the LED support bands)
        for p0, p1, n_ in (((xa, ya), (xb, ya), (0, -1)), ((xb, ya), (xb, yb), (1, 0)), ((xb, yb), (xa, yb), (0, 1)), ((xa, yb), (xa, ya), (-1, 0))):
            facing_pool = (n_[1] == inner)
            if facing_pool:
                # the screen: a 16 x 34 grid of LED 'pixels' showing the face
                nu, nv = 16, 34
                for i in range(nu):
                    for j in range(nv):
                        u0, u1 = i / nu, (i + 1) / nu
                        v0, v1 = j / nv, (j + 1) / nv
                        lvl = face_pattern((u0 + u1) / 2, (v0 + v1) / 2)
                        m_ = ("M_LEDDark", "M_LEDMid", "M_LEDSkin", "M_LEDBright", "M_LEDDark")[lvl]
                        q0 = Vector(p0).lerp(Vector(p1), u0)
                        q1 = Vector(p0).lerp(Vector(p1), u1)
                        z0, z1 = 0.25 + (H - 0.5) * v0, 0.25 + (H - 0.5) * v1
                        B.face([(q0.x, q0.y, z0), (q1.x, q1.y, z0), (q1.x, q1.y, z1), (q0.x, q0.y, z1)], m_)
                # the spout (mouth) nozzle 3.7 m up
                cx = (p0[0] + p1[0]) / 2
                ym = p0[1]
                B.rod((cx, ym, 0.25 + (H - 0.5) * 0.26), (cx, ym + n_[1] * 0.4, 0.25 + (H - 0.5) * 0.26), 0.12, "M_Steel", 6)
            else:
                B.face([(p0[0], p0[1], 0.0), (p1[0], p1[1], 0.0), (p1[0], p1[1], H), (p0[0], p0[1], H)], "M_GlassBlock")
            for zb in [1.524 * k for k in range(1, 10)]:
                o_ = Vector((n_[0], n_[1], 0)) * 0.04
                B.face([(p0[0] + o_.x, p0[1] + o_.y, zb - 0.05), (p1[0] + o_.x, p1[1] + o_.y, zb - 0.05),
                        (p1[0] + o_.x, p1[1] + o_.y, zb + 0.05), (p0[0] + o_.x, p0[1] + o_.y, zb + 0.05)], "M_Steel")
        # stainless T-frame edges and the cap
        for cx_, cy_ in ((xa, ya), (xb, ya), (xb, yb), (xa, yb)):
            B.boxmm((cx_ - 0.12, cy_ - 0.12, 0.0), (cx_ + 0.12, cy_ + 0.12, H + 0.1), "M_Steel")
        B.boxmm((xa - 0.1, ya - 0.1, H), (xb + 0.1, yb + 0.1, H + 0.25), "M_Steel")
        # water sheet down the faces (thin, slightly proud) and the splash at the foot
        B.boxmm((xa - 0.35, ya - 0.35, 0.0), (xb + 0.35, yb + 0.35, 0.12), "M_GraniteBlack")
    rotate_verts(B, yaw)
    # water: a thin sheet down every face of both towers and the arcing spout from each face's mouth (no collision)
    J = PlanBuilder()
    for yc, inner in ((25.1, -1), (-25.1, 1)):
        xa, xb, ya, yb = -3.62, 3.62, yc - 2.57, yc + 2.57
        for p0, p1 in (((xa, ya), (xb, ya)), ((xb, ya), (xb, yb)), ((xb, yb), (xa, yb)), ((xa, yb), (xa, ya))):
            J.face([(p0[0], p0[1], 0.1), (p1[0], p1[1], 0.1), (p1[0], p1[1], 15.2), (p0[0], p0[1], 15.2)], "M_WaterJet")
        zm = 0.25 + (15.24 - 0.5) * 0.26
        y0 = yc + inner * 2.6
        pts = [(0.0, y0 + inner * d, zm + 1.2 * d - 0.16 * d * d) for d in [k * 0.8 for k in range(13)]]
        J.tube([Vector(q) for q in pts], [0.12 + 0.02 * k for k in range(13)], "M_WaterJet", 8)
    rotate_verts(J, yaw)
    export_site("PK_CrownFountainWater", J, o, {"what": "Crown Fountain water sheets and spouts (no collision)"}, collide="none")
    zone = {"poly": [(326.0, -709.0), (346.0, -709.0), (346.0, -633.0), (326.0, -633.0)], "clear": ["props"]}
    export_site("PK_CrownFountain", B, o, {"what": "Crown Fountain (stylised): 2 glass-brick towers 15.24 x 7.0 x 4.9 m, 71 x 15 m black "
                                                    "granite pool, generic stylised face on the inner LED screens"},
                collide="complex", zone=zone)


def peristyle():
    """Millennium Monument (Wrigley Square): semicircular peristyle of paired Roman Doric columns (replica of the 1917
    original), OSM outline r 9.5-12.4 m about (329.9, -397.0), opening south over the round fountain pool (r 6.5 m)."""
    o = (329.9, -397.0)
    B = PlanBuilder()
    R_in, R_out = 9.6, 12.3
    Hc, base_h = 9.2, 1.2
    # stepped stylobate (half ring) and entablature
    def half_ring(r0, r1, z0, z1, m, n=40):
        P = [(r1 * math.cos(math.pi * k / n), r1 * math.sin(math.pi * k / n)) for k in range(n + 1)]
        P += [(r0 * math.cos(math.pi * k / n), r0 * math.sin(math.pi * k / n)) for k in range(n, -1, -1)]
        B.slab(P, z0, z1, m)
    half_ring(R_in - 0.9, R_out + 0.9, 0.0, 0.4, "M_Limestone")
    half_ring(R_in - 0.5, R_out + 0.5, 0.4, 0.8, "M_Limestone")
    half_ring(R_in - 0.2, R_out + 0.2, 0.8, base_h, "M_Limestone")
    zt = base_h + Hc
    half_ring(R_in - 0.3, R_out + 0.3, zt, zt + 0.9, "M_Limestone")         # architrave + frieze
    half_ring(R_in - 0.55, R_out + 0.55, zt + 0.9, zt + 1.15, "M_Limestone")  # cornice
    half_ring(R_in - 0.4, R_out + 0.4, zt + 1.15, zt + 1.7, "M_Limestone")    # attic
    # 40 columns: 20 pairs (inner + outer) round the half circle; Doric: fluted-looking 16-gon shaft with entasis, echinus, abacus
    for k in range(20):
        a = math.pi * (k + 0.5) / 20
        for R in (R_in + 0.55, R_out - 0.55):
            cx, cy = R * math.cos(a), R * math.sin(a)
            prof = [(0.48, base_h), (0.46, base_h + Hc * 0.4), (0.40, base_h + Hc - 0.55), (0.52, base_h + Hc - 0.3), (0.0, base_h + Hc - 0.3)]
            B.lathe(prof, "M_Limestone", 16, center=(cx, cy, 0))
            B.box((cx, cy, base_h + Hc - 0.15), (1.15, 1.15, 0.3), "M_Limestone", Matrix.Rotation(a, 3, "Z"))
    # the fountain pool in front (OSM r 6.5 m) with a low coping, and the square's paving
    B.slab(circle(0.3, -0.7, 6.8, 40), -0.1, 0.45, "M_Limestone")
    B.slab(circle(0.3, -0.7, 6.4, 40), 0.1, 0.32, "M_Water")
    B.slab([(-17.0, -30.0), (17.0, -30.0), (17.0, 14.0), (-17.0, 14.0)], -0.1, 0.03, "M_Granite")
    zone = {"poly": [(310.0, -428.0), (350.0, -428.0), (350.0, -381.0), (310.0, -381.0)], "clear": ["props"]}
    export_site("PK_Peristyle", B, o, {"what": "Millennium Monument peristyle: 20 pairs of Doric columns on a half ring r 9.6-12.3 m, "
                                                "entablature 10.4 m, fountain pool r 6.4 m, Wrigley Square paving"}, collide="complex", zone=zone)


def lurie_garden():
    """Lurie Garden (Gustafson Guthrie Nichol / Oudolf): the 4.6 m 'shoulder hedge' on its steel armature along the north
    and west sides, the dark plate and light plate planting beds, the diagonal 'seam' boardwalk with its water channel
    (OSM gardens at x 451..559, y -632..-724)."""
    o = (505.0, -675.0)
    B = PlanBuilder()
    # shoulder hedge: north side (along the lawn's south edge) and west side, 4.6 m tall, 3 m thick, on a steel armature
    hedge_n = [(452.0, -632.0), (470.0, -637.0), (490.0, -641.5), (510.0, -642.5), (530.0, -640.0), (548.0, -634.0), (559.0, -630.0)]
    hedge_w = [(452.0, -632.0), (451.0, -660.0), (451.0, -700.0), (452.0, -724.0)]
    for line in (hedge_n, hedge_w):
        loc = P2(line, o)
        B.sweep_open(loc, [(1.5, 0.0), (1.6, 3.2), (1.2, 4.6), (-1.2, 4.6), (-1.6, 3.2), (-1.5, 0.0)], "M_Hedge", smooth=True)
        for (ax, ay), (bx, by) in zip(loc, loc[1:]):
            L = math.hypot(bx - ax, by - ay)
            for i in range(int(L / 6.0) + 1):
                t = i * 6.0 / L if L else 0
                B.cyl((ax + (bx - ax) * t, ay + (by - ay) * t, 0.0), 4.9, 0.06, "M_Steel", 6)
    # plates: dark plate (west, deep purple-green perennials) and light plate (east), low mounded beds with gravel walks
    dark = [(455.0, -646.0), (497.0, -652.0), (480.0, -722.0), (455.0, -722.0)]
    light = [(503.0, -652.0), (556.0, -644.0), (556.0, -722.0), (486.0, -722.0)]
    for poly, m in ((dark, "M_Hedge"), (light, "M_Lawn")):
        loc = P2(poly, o)
        B.slab(loc, -0.1, 0.05, m)                     # planted ground (dark plate / light plate)
        # planting drifts: rows of low mounds
        xs = [p[0] for p in loc]; ys = [p[1] for p in loc]
        import random
        rnd = random.Random(len(loc) * 13 + int(xs[0]))
        tries = 0
        placed = []
        while len(placed) < 150 and tries < 3000:
            tries += 1
            gx, gy = rnd.uniform(min(xs), max(xs)), rnd.uniform(min(ys), max(ys))
            if not BL_inside(loc, gx, gy) or any(math.hypot(gx - a, gy - b) < 2.4 for a, b in placed):
                continue
            placed.append((gx, gy))
            pal = ("M_Grasses", "M_Lawn", "M_Verdigris", "M_Salvia", "M_Hedge") if m == "M_Lawn" else ("M_Hedge", "M_Salvia", "M_Salvia", "M_Grasses", "M_Verdigris")
            B.ellipsoid((gx, gy, 0.05), (rnd.uniform(1.8, 3.4), rnd.uniform(1.4, 2.4), rnd.uniform(0.4, 0.9)), rnd.choice(pal), 8, 3, half=True,
                        rot=Matrix.Rotation(rnd.uniform(0, math.pi), 3, "Z"))
    # the seam: diagonal boardwalk (timber) over a shallow water channel, from NE to SW (NAIP)
    seam = P2([(497.0, -652.0), (486.0, -722.0)], o)
    a, b = Vector((*seam[0], 0)), Vector((*seam[1], 0))
    t = (b - a).normalized()
    n_ = Vector((-t.y, t.x, 0))
    for w0, w1, z, m in ((-1.6, 1.6, 0.06, "M_Water"), (1.6, 4.4, 0.32, "M_WoodLight"), (-4.4, -1.6, 0.32, "M_WoodLight")):
        q = [a + n_ * w0, b + n_ * w0, b + n_ * w1, a + n_ * w1]
        B.slab([(p.x, p.y) for p in q], -0.1, z, m)
    zone = {"poly": [(449.0, -628.0), (561.0, -628.0), (561.0, -726.0), (449.0, -726.0)], "clear": ["props"]}
    export_site("PK_LurieGarden", B, o, {"what": "Lurie Garden: 4.6 m shoulder hedge (north + west), dark and light plates, seam boardwalk"},
                collide="complex", zone=zone)


def BL_inside(poly, x, y):
    c = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c



def millennium_pavilions():
    """Millennium Park's small buildings (OSM outlines): the four black photovoltaic-glass Exelon Pavilions (Renzo Piano;
    the two on Monroe pulled in off the plan's sidewalk), the Harris Theater's glass entrance pavilion on Randolph and its
    stage house, and the McDonald's Cycle Center's glass roof."""
    o = (490.0, -550.0)
    B = PlanBuilder()
    for (x0, y0, x1, y1) in ((443.2, -390.7, 454.5, -375.6), (521.6, -389.4, 532.6, -374.1), (454.5, -723.0, 462.1, -713.8), (524.7, -723.0, 535.6, -712.3)):
        q = [(x0 - o[0], y0 - o[1]), (x1 - o[0], y0 - o[1]), (x1 - o[0], y1 - o[1]), (x0 - o[0], y1 - o[1])]
        B.slab(q, 0.0, 6.2, "M_GlassDark", "M_TowerBlack")
        B.sweep_closed(q, [(0.0, 5.8), (0.25, 5.8), (0.25, 6.4), (0.0, 6.4)], "M_Steel")
    hx0, hx1 = 472.4 - o[0], 504.8 - o[0]
    B.slab([(hx0, -386.2 - o[1]), (hx1, -386.2 - o[1]), (hx1, -373.4 - o[1]), (hx0, -373.4 - o[1])], 0.0, 7.0, "M_RoofFlat", "M_Glass")
    B.slab([(472.8 - o[0], -437.5 - o[1]), (505.6 - o[0], -437.5 - o[1]), (505.4 - o[0], -390.0 - o[1]), (472.3 - o[0], -390.0 - o[1])], 0.0, 13.5,
           "M_RoofFlat", "M_Steel")
    B.slab([(548.4 - o[0], -404.0 - o[1]), (559.5 - o[0], -404.0 - o[1]), (559.4 - o[0], -395.4 - o[1]), (548.3 - o[0], -395.4 - o[1])], 0.0, 0.4, "M_Concrete")
    B.lathe([(6.0, 0.4), (5.6, 2.5), (4.0, 3.8), (0.0, 4.2)], "M_Glass", 16, center=(553.9 - o[0], -399.7 - o[1], 0))
    export_site("PK_MillenniumPavilions", B, o, {"what": "Exelon Pavilions x4, Harris Theater entrance + stage house, Cycle Center roof"},
                collide="complex")


# ================================================================== 3. The Art Institute of Chicago
AIC_ALLERTON = [(314.0, -835.4), (368.5, -834.5), (368.6, -850.0), (373.7, -850.0), (374.9, -915.6), (369.6, -915.6), (370.0, -932.0),
                (315.4, -933.1), (314.9, -898.9), (310.6, -899.0), (310.4, -870.5), (314.7, -870.4)]
AIC_WINGS = [   # (height m, OSM-derived polygon) the later wings round the 1893 building (massing, limestone / modern)
    (13.0, "M_Limestone", [(366.9, -771.1), (383.1, -770.9), (383.5, -840.5), (384.3, -873.7), (374.0, -873.7), (373.7, -850.0), (368.6, -850.0),
                           (368.5, -834.5), (367.1, -775.4)]),
    (13.0, "M_Limestone", [(374.9, -891.7), (384.6, -891.7), (386.3, -947.4), (386.7, -994.7), (369.4, -995.0), (368.7, -942.2), (370.1, -941.1),
                           (370.0, -932.0), (369.6, -915.6), (374.9, -915.6)]),
    (15.0, "M_Concrete", [(443.6, -872.8), (463.3, -872.4), (463.0, -859.3), (486.0, -858.8), (485.4, -821.8), (532.0, -821.2), (532.1, -827.8),
                          (549.4, -844.2), (549.6, -851.1), (549.4, -856.3), (545.3, -856.4), (556.3, -867.7), (556.7, -891.9), (546.1, -902.9),
                          (488.1, -903.7), (489.8, -998.1), (490.0, -1007.2), (449.0, -1004.6), (447.9, -904.6), (446.8, -904.7), (446.3, -890.5)]),
]
AIC_MODERN = [(537.1, -770.2), (531.4, -770.3), (531.4, -762.1), (483.0, -763.3), (483.0, -766.3), (469.6, -766.5), (469.1, -767.2),
              (460.5, -767.3), (460.4, -762.6), (445.6, -762.9), (445.8, -770.5), (437.5, -772.4), (437.8, -792.8), (441.5, -792.6),
              (441.9, -803.9), (446.3, -803.7), (447.0, -843.1), (439.7, -843.3), (439.8, -853.1), (443.2, -853.1), (443.6, -872.8),
              (463.3, -872.4), (463.0, -859.3), (486.0, -858.8), (485.4, -821.8), (474.1, -822.0), (473.8, -803.6), (531.8, -802.7),
              (531.6, -796.8), (537.6, -796.7)]


def facade(B, a, b, z0, z1, bays, m="M_Limestone", glass="M_GlassDark", kind="window", thick=0.9, aw=3.4):
    """A wall from plan-local a to b (outside on the right-hand side when walking a -> b... normal = (b-a) x up), with `bays`
    openings: kind 'arch' (tall round-headed), 'window' (rectangular), 'basement' (low arched), 'blind' (none)."""
    a, b = Vector((a[0], a[1], 0)), Vector((b[0], b[1], 0))
    W = (b - a).length
    r = (b - a).normalized()
    holes = []
    H = z1 - z0
    if kind != "blind" and bays > 0:
        bw = W / bays
        for i in range(bays):
            xc = bw * (i + 0.5)
            if kind == "arch":
                w = min(bw * 0.5, aw)
                holes.append((xc, w, H * 0.12, H * 0.78 - w / 2, True))
            elif kind == "basement":
                w = min(bw * 0.38, 2.2)
                holes.append((xc, w, H * 0.25, H * 0.8 - w / 2, True))
            else:
                w = min(bw * 0.45, 2.0)
                holes.append((xc, w, H * 0.2, H * 0.8, False))
    # no end caps: on a closed outline the neighbouring walls meet at the corners, and caps would be coplanar with them
    B.wall(Vector((a.x, a.y, z0)), r, Vector((0, 0, 1)), W, H, thick, m, holes=holes, fill=glass, fill_inset=0.7, edges=False)


def art_institute():
    """The Art Institute of Chicago: the 1893 Allerton Building (Shepley, Rutan & Coolidge; Beaux-Arts limestone, raised
    basement, arched piano nobile, the central pavilion with its three great arches and pediment, the grand stair and the two
    bronze lions on the Michigan Avenue side), the later wings as massing (OSM footprints), Gunsaulus Hall over the Metra
    tracks, the Modern Wing (Renzo Piano, 2009) with its 'flying carpet' roof and the Nichols Bridgeway (190 m) to
    Millennium Park."""
    o = (342.0, -884.0)
    B = PlanBuilder(vis=True)
    L = P2(AIC_ALLERTON, o)
    pts = ccw(L)
    # --- Allerton: raised basement (rusticated) 0-5.4, piano nobile 5.4-15.6, attic 15.6-19.2, cornice, parapet
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        W = math.hypot(b[0] - a[0], b[1] - a[1])
        if W < 3.0:
            B.wall(Vector((a[0], a[1], 0)), Vector((b[0] - a[0], b[1] - a[1], 0)).normalized(), Vector((0, 0, 1)), W, 21.0, 0.9, "M_Limestone")
            continue
        n = max(1, int(round(W / 6.4)))
        central = abs(a[0] - (310.4 - o[0])) < 0.5 and abs(b[0] - (310.6 - o[0])) < 0.5
        if central:
            continue
        facade(B, a, b, 0.0, 5.4, n, kind="basement")
        facade(B, a, b, 5.4, 15.6, n, kind="arch")
        facade(B, a, b, 15.6, 19.2, n, kind="window")
    # cornice + parapet round the whole block
    B.sweep_closed(pts, [(0.0, 15.4), (0.35, 15.6), (0.35, 15.9), (0.0, 16.1)], "M_Limestone")
    B.sweep_closed(pts, [(0.0, 18.6), (0.9, 18.9), (1.2, 19.3), (1.2, 19.6), (0.0, 19.7)], "M_Limestone")
    B.sweep_closed(pts, [(0.0, 19.6), (0.05, 19.6), (0.05, 21.0), (0.0, 21.0)], "M_Limestone")
    B.sweep_closed(pts, [(0.0, 5.2), (0.25, 5.3), (0.25, 5.6), (0.0, 5.7)], "M_Limestone")
    B.slab(pts, 0.0, 20.6, "M_RoofFlat") if False else B.face([(x, y, 20.6) for x, y in pts], "M_RoofFlat")
    # skylights over the galleries and the grand staircase hall
    for (x0_, y0_, x1_, y1_) in ((322, -845, 362, -858), (322, -910, 362, -923), (330, -870, 366, -898)):
        a_, b_ = (x0_ - o[0], y1_ - o[1]), (x1_ - o[0], y0_ - o[1])
        cx_, cy_ = (a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2
        B.pyramid((cx_, cy_, 20.6), abs(b_[0] - a_[0]) / 2, abs(b_[1] - a_[1]) / 2, 2.4, "M_Glass")
    # --- the central pavilion (west front, x 310.4, y -870.5 .. -899): three great arches in a loggia, paired columns,
    # entablature, attic with the relief panels and the pediment
    xf = 310.4 - o[0]
    ya, yb = -870.5 - o[1], -899.0 - o[1]
    Wc = ya - yb
    holes = [(Wc * (i + 0.5) / 3, 5.4, 0.6, 7.4, True) for i in range(3)]
    B.wall(Vector((xf, ya, 5.4)), Vector((0, -1, 0)), Vector((0, 0, 1)), Wc, 10.5, 1.6, "M_Limestone", holes=holes, fill="M_GlassDark", fill_inset=1.4)
    facade(B, (xf, ya), (xf, yb), 0.0, 5.4, 5, kind="basement", thick=1.6)
    for i in range(4):
        yy = ya - Wc * i / 3
        for dy in (-0.9, 0.9) if 0 < i < 3 else ((-0.9,) if i == 0 else (0.9,)):
            yc = yy + dy * (1 if i == 0 else 1)
            B.lathe([(0.55, 5.6), (0.5, 12.0), (0.44, 15.6), (0.62, 16.0), (0.0, 16.0)], "M_Limestone", 12, center=(xf - 0.6, max(min(yc, ya - 0.6), yb + 0.6), 0))
    B.boxmm((xf - 1.4, yb - 0.4, 15.9), (xf + 0.5, ya + 0.4, 18.2), "M_Limestone")             # entablature
    B.boxmm((xf - 1.0, yb, 18.2), (xf + 0.5, ya, 19.7), "M_Limestone")                          # attic band
    for k in range(2):
        yc = yb + Wc * (0.25 + 0.5 * k)
        B.boxmm((xf - 1.5, yc - 3.5, 16.3), (xf - 1.35, yc + 3.5, 17.8), "M_Limestone")         # frieze relief panels
    B.prism(Vector((xf - 1.3, yb - 0.4, 19.7)), Vector((0, 1, 0)), Vector((0, 0, 1)),
            [(0.0, 0.0), (Wc + 0.8, 0.0), ((Wc + 0.8) / 2, 3.8)], -9.0, "M_Limestone")             # low pediment
    # --- the grand stair down to Michigan Avenue between the lion pedestals, and the forecourt terrace
    B.steps(305.0 - o[0], -899.5 - o[1] + 0.0, xf, -869.5 - o[1], 2.2, 0.0, 9, "M_Granite", axis="x", up_positive=True)
    B.boxmm((xf - 0.01, yb - 6.0, 0.0), (xf + 4.0, ya + 6.0, 2.2), "M_Granite")
    for yl in (-866.0, -903.0):
        B.boxmm((305.2 - o[0], yl - o[1] - 1.3, 0.0), (309.8 - o[0], yl - o[1] + 1.3, 2.3), "M_Granite")         # lion pedestals
        B.boxmm((305.0 - o[0], yl - o[1] - 1.45, 2.3), (310.0 - o[0], yl - o[1] + 1.45, 2.5), "M_Granite")
    # balustrades along the forecourt
    for y0_, y1_ in ((-835.4, -866.0), (-903.0, -933.1)):
        B.balustrade([(305.6 - o[0], y0_ - o[1] - 1.5), (305.6 - o[0], y1_ - o[1] + 1.5)], 0.0, "M_Limestone", h=1.0, step=0.4) if False else \
            B.beam((305.6 - o[0], y0_ - o[1] - 1.5, 0.5), (305.6 - o[0], y1_ - o[1] + 1.5, 0.5), 0.5, 1.0, "M_Limestone")
    # --- the later wings (massing with window bands) and Gunsaulus Hall bridging the tracks
    for h, m_, poly in AIC_WINGS:
        loc = ccw(P2(poly, o))
        B.slab(loc, 0.0, h, "M_RoofFlat", m_)
        for i in range(len(loc)):
            a, b = loc[i], loc[(i + 1) % len(loc)]
            W = math.hypot(b[0] - a[0], b[1] - a[1])
            if W > 6.0:
                n_ = Vector((b[1] - a[1], -(b[0] - a[0]), 0)).normalized() * 0.04
                for zb in (3.2, 7.8):
                    B.face([(a[0] + n_.x, a[1] + n_.y, zb), (b[0] + n_.x, b[1] + n_.y, zb), (b[0] + n_.x, b[1] + n_.y, zb + 2.2),
                            (a[0] + n_.x, a[1] + n_.y, zb + 2.2)], "M_GlassDark")
        B.sweep_closed(loc, [(0.0, h - 0.6), (0.3, h - 0.6), (0.3, h + 0.6), (0.0, h + 0.6)], m_)
    gp = P2([(384.0, -873.7), (446.3, -872.8), (446.3, -890.5), (384.6, -891.7)], o)
    B.slab(gp, 7.2, 17.0, "M_RoofFlat", "M_Limestone")
    for x_ in (395.0, 408.0, 421.0, 434.0):
        B.boxmm((x_ - o[0] - 0.7, -890.0 - o[1], 0.0), (x_ - o[0] + 0.7, -874.5 - o[1], 7.2), "M_Concrete")
    for k in range(12):
        x_ = 386.0 + k * 5.0 - o[0]
        for yy in (-873.6 - o[1] + 0.05, -891.6 - o[1] - 0.05):
            B.face([(x_, yy, 9.0), (x_ + 3.2, yy, 9.0), (x_ + 3.2, yy, 15.0), (x_, yy, 15.0)][:: (1 if yy > -880 - o[1] else -1)], "M_GlassDark")
    # --- the Modern Wing (glass, 3 storeys) with the 'flying carpet' blade roof over its east pavilion
    mw = ccw(P2(AIC_MODERN, o))
    B.slab(mw, 0.0, 17.0, "M_RoofFlat", "M_Glass")          # 17 m: the Nichols Bridgeway lands on its roof terrace
    for zb in (6.4, 12.8):
        B.sweep_closed(mw, [(0.0, zb - 0.3), (0.15, zb - 0.3), (0.15, zb + 0.3), (0.0, zb + 0.3)], "M_WheelWhite")
    B.sweep_closed(mw, [(0.0, 16.4), (0.3, 16.4), (0.3, 17.6), (0.0, 17.6)], "M_WheelWhite")
    fx0, fx1, fy0, fy1 = 472.9 - o[0], 538.8 - o[0], -819.8 - o[1], -753.9 - o[1]
    nb = 36
    for k in range(nb + 1):
        y_ = fy0 + (fy1 - fy0) * k / nb
        B.boxmm((fx0, y_ - 0.06, 20.6), (fx1, y_ + 0.06, 21.7), "M_WheelWhite")
    for x_ in (fx0, fx1):
        B.boxmm((x_ - 0.15, fy0, 21.5), (x_ + 0.15, fy1, 21.7), "M_WheelWhite")
    for x_ in (fx0 + 2.0, (fx0 + fx1) / 2, fx1 - 2.0):
        for y_ in (fy0 + 2.0, (fy0 + fy1) / 2, fy1 - 2.0):
            B.cyl((x_, y_, 17.0), 3.6, 0.18, "M_WheelWhite", 8)
    # --- Nichols Bridgeway: 190 m blade bridge from the Modern Wing's west terrace (z 17 m) north over Monroe St to the park
    bw = [(447.0, -800.0), (437.0, -799.0), (433.4, -760.0), (432.0, -700.0), (430.9, -650.0), (430.2, -620.0)]   # lands on the roof
    rn = json.load(open(ROOT + "/Saved/Roads/roadnet.json"))
    pave = [json.loads(e["ribbon"]) if isinstance(e["ribbon"], str) else e["ribbon"] for e in rn["edges"] if e.get("ribbon")]
    pave += [j["ring"] for j in rn["junctions"]] + list(rn["joints"]) + list(rn["walk"])
    on_pave = _poly_index(pave)
    pts3 = catmull([(x - o[0], y - o[1], 0.0) for x, y in bw], 60)
    s_ = [0.0]
    for p_, q_ in zip(pts3, pts3[1:]):
        s_.append(s_[-1] + (q_ - p_).length)
    Lb = s_[-1]
    rows_d, rows_e1, rows_e2 = [], [], []
    for i, p_ in enumerate(pts3):
        a_ = pts3[max(0, i - 1)]; b_ = pts3[min(len(pts3) - 1, i + 1)]
        t_ = (b_ - a_); t_.z = 0; t_.normalize()
        nl = Vector((-t_.y, t_.x, 0))
        z_ = 17.05 if s_[i] < 10.0 else 17.05 * (1 - (s_[i] - 10.0) / (Lb - 10.0)) ** 1.15 + 0.05
        c_ = Vector((p_.x, p_.y, z_))
        rows_d.append([c_ - nl * 2.3, c_ + nl * 2.3])
        rows_e1.append([c_ + nl * 2.3 + Vector((0, 0, dz)) for dz in (0.0, 1.1)])
        rows_e2.append([c_ - nl * 2.3 + Vector((0, 0, dz)) for dz in (1.1, 0.0)])
        if i % 12 == 6 and z_ > 3.0 and not any(on_pave(p_.x + o[0] + dx, p_.y + o[1] + dy) for dx in (-1.5, 0, 1.5) for dy in (-1.5, 0, 1.5)):
            B.cyl((p_.x, p_.y, 0.0), z_ - 0.6, 0.35, "M_WheelWhite", 8)
    B.grid(rows_d, "M_WheelWhite", smooth=False)
    B.grid([[r[1] + Vector((0, 0, -0.6)), r[0] + Vector((0, 0, -0.6))] for r in rows_d], "M_WheelWhite", smooth=False)
    B.grid(rows_e1, "M_Glass", smooth=False)
    B.grid(rows_e2, "M_Glass", smooth=False)
    zone = {"poly": [(304.8, -1008.0), (558.0, -1008.0), (558.0, -752.0), (304.8, -752.0)], "clear": ["props", "buildings"],
            "buildings": bv3_rects([(417.2, -764.0), (412.4, -791.0), (418.8, -838.9), (417.6, -877.7), (427.1, -944.0), (421.6, -986.4)])}
    export_site("PK_ArtInstitute", B, o, {"what": "Art Institute of Chicago: Allerton Building (1893) with central pavilion, grand stair, "
                                                   "lion pedestals; later wings; Gunsaulus Hall; Modern Wing + flying carpet; Nichols Bridgeway"},
                collide="complex", zone=zone)
    export_site("PK_ArtInstituteSteps", B.vis, o, {"what": "visible stair treads of PK_ArtInstitute (no collision; hidden ramps in the main mesh)"},
                collide="none")


def lion(B, c, yaw_deg, pose="prowl", s=1.0):
    """Kemeys' Art Institute lion (1894, public domain), stylised from simple solids: ~3.6 m long, 2.4 m tall, facing
    yaw (deg, plan: 0 = east, 180 = west). pose 'prowl' (north lion: head low, striding) or 'defiance' (south: head up)."""
    R = Matrix.Rotation(math.radians(yaw_deg), 3, "Z")
    C = Vector(c)
    def P(x, y, z):
        return C + R @ (Vector((x, y, z)) * s)
    def RY(a):
        return R @ Matrix.Rotation(a, 3, "Y")
    m = "M_LionBronze"
    up = pose == "defiance"
    # torso: chest, belly, haunches
    B.ellipsoid(P(-0.1, 0, 1.08), (1.0 * s, 0.46 * s, 0.46 * s), m, 16, 9, rot=RY(0.06 if up else -0.03))
    B.ellipsoid(P(-0.85, 0, 1.08), (0.5 * s, 0.44 * s, 0.5 * s), m, 12, 8, rot=R)
    B.ellipsoid(P(0.62, 0, 1.2), (0.55 * s, 0.5 * s, 0.6 * s), m, 14, 8, rot=R)
    # the mane: a big shaggy collar round neck and shoulders, tufts
    mx, mz = (0.95, 1.62) if up else (1.0, 1.42)
    B.ellipsoid(P(mx, 0, mz), (0.55 * s, 0.6 * s, 0.68 * s), m, 16, 10, rot=RY(-0.5 if up else -0.2))
    for k in range(10):
        a = 2 * math.pi * k / 10
        B.ellipsoid(P(mx - 0.1 + 0.08 * math.cos(a), 0.52 * math.sin(a), mz + 0.55 * math.cos(a)), (0.22 * s, 0.16 * s, 0.2 * s), m, 6, 4, rot=R)
    # head: broad skull, flat face, muzzle, nose, brow, ears
    hx, hz = (1.32, 1.95) if up else (1.42, 1.58)
    B.ellipsoid(P(hx, 0, hz), (0.34 * s, 0.32 * s, 0.33 * s), m, 12, 8, rot=R)
    B.ellipsoid(P(hx + 0.3, 0, hz - 0.12), (0.2 * s, 0.2 * s, 0.17 * s), m, 10, 6, rot=R)
    B.ellipsoid(P(hx + 0.45, 0, hz - 0.06), (0.06 * s, 0.09 * s, 0.06 * s), m, 6, 4, rot=R)
    B.ellipsoid(P(hx + 0.18, 0, hz + 0.16), (0.14 * s, 0.26 * s, 0.07 * s), m, 8, 4, rot=R)
    for side in (-1, 1):
        B.ellipsoid(P(hx - 0.12, side * 0.24, hz + 0.27), (0.07 * s, 0.06 * s, 0.09 * s), m, 6, 4, rot=R)
    # legs: front pair straight and heavy, hind pair with hock; big paws
    st = 0.3 if pose == "prowl" else 0.08
    for side in (-1, 1):
        fx = 0.75 + (st if side > 0 else -st * 0.4)
        limb(B, [P(0.7, side * 0.27, 1.05), P(fx - 0.02, side * 0.28, 0.55), P(fx, side * 0.28, 0.1)], [0.2 * s, 0.15 * s, 0.13 * s], m, 10)
        B.ellipsoid(P(fx + 0.12, side * 0.28, 0.08), (0.2 * s, 0.13 * s, 0.08 * s), m, 8, 4, rot=R)
        hx_ = -1.0 - (st if side < 0 else -st * 0.4)
        B.ellipsoid(P(-0.95, side * 0.28, 0.9), (0.45 * s, 0.2 * s, 0.42 * s), m, 10, 6, rot=R)
        limb(B, [P(-0.95, side * 0.28, 0.75), P(hx_ - 0.22, side * 0.28, 0.42), P(hx_, side * 0.28, 0.1)], [0.17 * s, 0.11 * s, 0.12 * s], m, 8)
        B.ellipsoid(P(hx_ + 0.12, side * 0.28, 0.08), (0.19 * s, 0.12 * s, 0.08 * s), m, 8, 4, rot=R)
    # tail with its tuft, hanging in an S
    limb(B, [P(-1.3, 0, 1.2), P(-1.6, 0.05, 0.95), P(-1.68, 0.15, 0.5), P(-1.58, 0.28, 0.15)], [0.08 * s, 0.07 * s, 0.06 * s, 0.06 * s], m, 6)
    B.ellipsoid(P(-1.55, 0.3, 0.13), (0.12 * s, 0.1 * s, 0.09 * s), m, 6, 4, rot=R)
    B.box(P(0.0, 0.0, 0.03), (3.7 * s, 1.1 * s, 0.06 * s), m, R)


def aic_lions():
    """The two bronze lions (Edward Kemeys, 1894) on their pedestals at the Michigan Avenue stair (OSM (302, -866) north
    'on the prowl', (303, -903) south 'in an attitude of defiance'), facing west; set 3.5 m east so they stay off the
    sidewalk of the plan (walk edge x 304.7)."""
    o = (342.0, -884.0)
    B = PlanBuilder()
    lion(B, (307.5 - o[0], -866.0 - o[1], 2.5), 180.0, "prowl", 1.0)
    lion(B, (307.5 - o[0], -903.0 - o[1], 2.5), 180.0, "defiance", 1.0)
    export_site("PK_ArtInstituteLions", B, o, {"what": "Art Institute lions (Kemeys 1894, public domain), stylised, on the pedestals"},
                collide="complex")


# ================================================================== 4. Grant Park: monuments and the band shell
def horse_rider(B, c, yaw_deg, s=1.0, pose="rear", rider="spear", m="M_LionBronze"):
    """A stylised bronze equestrian group about 5.2 m tall (s=1) standing on its base plate at c, facing yaw (plan deg).
    pose 'rear' (front legs up, Mestrovic's Bowman / Spearman) or 'walk' (Logan); rider 'spear' (arm thrust forward),
    'bow' (arms drawing an invisible bow), 'flag' (holding a staff with a flag)."""
    R = Matrix.Rotation(math.radians(yaw_deg), 3, "Z")
    C = Vector(c)
    rear = pose == "rear"
    tilt = 0.42 if rear else 0.0                    # body pitch (nose up) when rearing
    T = R @ Matrix.Rotation(-tilt, 3, "Y")
    hip = Vector((-0.9, 0.0, 1.55 if rear else 1.45)) * s
    def P(x, y, z):                                # body frame: rotate about the hind hip when rearing
        v = Vector((x, y, z)) * s
        return C + R @ (Matrix.Rotation(-tilt, 3, "Y") @ (v - hip) + hip)
    # barrel, chest, hindquarters, neck, head
    B.ellipsoid(P(0.0, 0, 1.75), (1.05 * s, 0.42 * s, 0.48 * s), m, 16, 9, rot=T)
    B.ellipsoid(P(0.75, 0, 1.85), (0.5 * s, 0.4 * s, 0.55 * s), m, 12, 8, rot=T)
    B.ellipsoid(P(-0.8, 0, 1.8), (0.55 * s, 0.44 * s, 0.55 * s), m, 12, 8, rot=T)
    limb(B, [P(0.9, 0, 2.05), P(1.25, 0, 2.55), P(1.4, 0, 2.95)], [0.32 * s, 0.26 * s, 0.2 * s], m, 10)
    limb(B, [P(1.38, 0, 3.0), P(1.75, 0, 2.75), P(1.95, 0, 2.55)], [0.2 * s, 0.17 * s, 0.13 * s], m, 10)
    for sd in (-1, 1):
        B.ellipsoid(P(1.4, sd * 0.09, 3.18), (0.05 * s, 0.04 * s, 0.11 * s), m, 6, 4, rot=T)
    limb(B, [P(1.0, 0, 2.6), P(1.3, 0, 2.95)], [0.06 * s, 0.05 * s], m, 6)            # mane crest
    # legs: hind legs planted; front legs tucked up (rear) or striding (walk)
    for sd in (-1, 1):
        y = sd * 0.25
        if rear:
            hp = C + R @ Vector((-0.95 * s, y * s, 1.4 * s))
            B.tube([hp, C + R @ Vector((-0.75 * s, y * s, 0.75 * s)), C + R @ Vector((-1.05 * s, y * s, 0.42 * s)), C + R @ Vector((-0.9 * s, y * s, 0.06 * s))],
                   [0.2 * s, 0.11 * s, 0.09 * s, 0.09 * s], m, 8)
            fk = 0.0 if sd < 0 else 0.25
            B.tube([P(0.8, y, 1.45), P(1.1 + fk, y, 1.0 + fk), P(0.85 + fk, y, 0.65 + fk * 1.6), P(0.95 + fk, y, 0.45 + fk * 1.6)],
                   [0.14 * s, 0.09 * s, 0.08 * s, 0.08 * s], m, 8)
        else:
            st = 0.3 * sd
            limb(B, [P(-0.85, y, 1.45), P(-0.75 - st, y, 0.8), P(-0.95 - st, y, 0.45), P(-0.85 - st, y, 0.06)], [0.2 * s, 0.11 * s, 0.09 * s, 0.09 * s], m, 8)
            limb(B, [P(0.8, y, 1.45), P(0.85 + st, y, 0.8), P(0.85 + st * 1.6, y, 0.4), P(0.9 + st * 1.8, y, 0.06)], [0.14 * s, 0.09 * s, 0.08 * s, 0.08 * s], m, 8)
    limb(B, [P(-1.3, 0, 2.0), P(-1.6, 0, 1.6), P(-1.7, 0.05, 1.0)], [0.12 * s, 0.1 * s, 0.07 * s], m, 8)           # tail
    # rider: thighs over the barrel, torso, head (feathered headdress), arms
    limb(B, [P(0.15, -0.38, 1.85), P(0.25, -0.42, 1.4)], [0.11 * s, 0.08 * s], m, 8)
    limb(B, [P(0.15, 0.38, 1.85), P(0.25, 0.42, 1.4)], [0.11 * s, 0.08 * s], m, 8)
    B.ellipsoid(P(0.05, 0, 2.7), (0.27 * s, 0.33 * s, 0.58 * s), m, 10, 6, rot=T)
    B.ellipsoid(P(0.12, 0, 3.45), (0.16 * s, 0.15 * s, 0.19 * s), m, 8, 6, rot=T)
    B.ellipsoid(P(0.06, 0, 3.62), (0.2 * s, 0.17 * s, 0.1 * s), m, 8, 4, rot=T)
    if rider == "spear":
        limb(B, [P(0.05, -0.25, 2.85), P(0.45, -0.35, 3.0), P(0.95, -0.35, 3.15)], [0.07 * s, 0.06 * s, 0.05 * s], m, 6)
        limb(B, [P(0.05, 0.25, 2.85), P(-0.3, 0.35, 2.55), P(-0.45, 0.3, 2.25)], [0.07 * s, 0.06 * s, 0.05 * s], m, 6)
    elif rider == "bow":
        limb(B, [P(0.05, 0.25, 2.85), P(0.55, 0.45, 3.0), P(0.95, 0.5, 3.1)], [0.07 * s, 0.06 * s, 0.05 * s], m, 6)
        limb(B, [P(0.05, -0.25, 2.85), P(-0.2, -0.3, 2.95), P(-0.25, -0.15, 3.0)], [0.07 * s, 0.06 * s, 0.05 * s], m, 6)
    else:
        limb(B, [P(0.05, 0.25, 2.85), P(0.3, 0.35, 2.6)], [0.07 * s, 0.06 * s], m, 6)
        B.rod(P(0.32, 0.36, 2.0), P(0.25, 0.36, 4.4), 0.03 * s, m, 6)
        B.face([P(0.25, 0.36, 4.35), P(-0.6, 0.36, 4.2), P(-0.65, 0.36, 3.65), P(0.28, 0.36, 3.75)], m)
        B.face([P(0.28, 0.36, 3.75), P(-0.65, 0.36, 3.65), P(-0.6, 0.36, 4.2), P(0.25, 0.36, 4.35)], m)
    B.box(C + R @ Vector((0, 0, 0.04 * s)), (2.6 * s, 0.9 * s, 0.08 * s), m, R)


def congress_plaza():
    """Congress Plaza: Mestrovic's 'The Bowman' and 'The Spearman' (1928, public domain), bronze, ~5.2 m, rearing horses on
    granite pedestals (OSM (355.9, -1281.1) and (357.2, -1334.5); the Spearman nudged 1.5 m off the plan's sidewalk), facing
    each other across Congress; the two 15 m limestone pylons with their reliefs (OSM (387.6, -1260.0), (389.2, -1352.2))."""
    o = (372.0, -1307.0)
    B = PlanBuilder()
    for (px, py, yaw, rider) in ((355.9, -1281.1, -90.0, "bow"), (357.8, -1333.1, 90.0, "spear")):
        x, y = px - o[0], py - o[1]
        B.boxmm((x - 2.6, y - 3.8, 0.0), (x + 2.6, y + 3.8, 0.5), "M_Granite")
        B.boxmm((x - 2.2, y - 3.4, 0.5), (x + 2.2, y + 3.4, 0.9), "M_Granite")
        B.boxmm((x - 1.6, y - 2.9, 0.9), (x + 1.6, y + 2.9, 4.3), "M_Granite")
        B.boxmm((x - 1.8, y - 3.1, 4.3), (x + 1.8, y + 3.1, 4.6), "M_Granite")
        horse_rider(B, (x, y, 4.6), yaw, 1.35, "rear", rider)
    for (px, py) in ((387.6, -1260.0), (389.2, -1352.2)):
        x, y = px - o[0], py - o[1]
        B.boxmm((x - 4.4, y - 3.6, 0.0), (x + 4.4, y + 3.6, 1.2), "M_Limestone")
        B.boxmm((x - 3.6, y - 2.9, 1.2), (x + 3.6, y + 2.9, 12.5), "M_Limestone")
        B.boxmm((x - 4.0, y - 3.3, 12.5), (x + 4.0, y + 3.3, 13.3), "M_Limestone")
        B.boxmm((x - 3.4, y - 2.7, 13.3), (x + 3.4, y + 2.7, 15.2), "M_Limestone")
        B.boxmm((x - 3.8, y - 3.1, 15.2), (x + 3.8, y + 3.1, 15.6), "M_Limestone")
        for sd in (-1, 1):                             # relief panels on the faces
            B.boxmm((x - 2.6, y + sd * 2.9 - 0.08, 5.0), (x + 2.6, y + sd * 2.9 + 0.08, 10.5), "M_Limestone")
            B.boxmm((x + sd * 3.6 - 0.08, y - 1.9, 5.0), (x + sd * 3.6 + 0.08, y + 1.9, 10.5), "M_Limestone")
    zone = {"poly": [(350.0, -1290.0), (362.0, -1290.0), (362.0, -1272.0), (350.0, -1272.0)], "clear": ["props"],
            "extra": [[(351.0, -1342.0), (364.0, -1342.0), (364.0, -1325.0), (351.0, -1325.0)],
                      [(382.0, -1265.0), (394.0, -1265.0), (394.0, -1254.0), (382.0, -1254.0)],
                      [(383.0, -1358.0), (395.0, -1358.0), (395.0, -1346.0), (383.0, -1346.0)]]}
    export_site("PK_CongressPlaza", B, o, {"what": "Congress Plaza: The Bowman and The Spearman (stylised) on granite pedestals, two 15.6 m pylons"},
                collide="complex", zone=zone)


def seated_figure(B, c, yaw_deg, s=1.0, m="M_LionBronze"):
    """A seated bronze figure in a chair (Saint-Gaudens' Lincoln, 1926, public domain), ~3.6 m tall seated (s=1)."""
    R = Matrix.Rotation(math.radians(yaw_deg), 3, "Z")
    C = Vector(c)
    P = lambda x, y, z: C + R @ (Vector((x, y, z)) * s)
    B.box(P(-0.1, 0, 0.75), (1.5 * s, 1.9 * s, 1.5 * s), m, R)                 # chair seat block
    B.box(P(-0.75, 0, 1.9), (0.25 * s, 1.9 * s, 2.3 * s), m, R)                # chair back
    B.ellipsoid(P(-0.15, 0, 2.25), (0.4 * s, 0.55 * s, 0.75 * s), m, 12, 8, rot=R)      # torso (coat)
    B.ellipsoid(P(0.0, 0, 3.2), (0.2 * s, 0.18 * s, 0.25 * s), m, 10, 6, rot=R)         # head
    for sd in (-1, 1):
        limb(B, [P(-0.2, sd * 0.3, 1.55), P(0.55, sd * 0.32, 1.55), P(0.65, sd * 0.32, 0.1)], [0.2 * s, 0.17 * s, 0.13 * s], m, 8)   # legs
        limb(B, [P(-0.1, sd * 0.55, 2.7), P(0.1, sd * 0.62, 2.0), P(0.45, sd * 0.5, 1.75)], [0.13 * s, 0.11 * s, 0.09 * s], m, 8)    # arms
    B.ellipsoid(P(-0.3, 0, 1.6), (0.6 * s, 0.75 * s, 0.25 * s), m, 10, 6, rot=R)        # coat tails over the seat


def lincoln_head_of_state():
    """Abraham Lincoln: The Head of State (Saint-Gaudens, 1926) in the Court of Presidents: the seated bronze on its
    pedestal (OSM (518.1, -1134.8)) on a raised granite exedra platform with steps along the south front and the two tall
    columns with lamps (OSM (498.5, -1147.3), (537.7, -1146.6))."""
    o = (518.0, -1140.0)
    B = PlanBuilder(vis=True)
    # platform 48 x 16 m, 1.6 m up, steps along the south edge (hidden ramp under them in the main mesh), back wall / bench
    B.boxmm((-24.0, -2.0, 0.0), (24.0, 13.0, 1.6), "M_Granite")
    B.steps(-24.0, -10.0, 24.0, -2.0, 1.6, 0.0, 8, "M_Granite", axis="y", up_positive=False) if False else \
        B.steps(-24.0, -10.0, 24.0, -2.0, 1.6, 0.0, 8, "M_Granite", axis="y", up_positive=True)
    B.boxmm((-24.0, 11.0, 1.6), (24.0, 13.0, 2.6), "M_Granite")
    B.boxmm((-24.0, 11.6, 2.6), (24.0, 13.0, 3.2), "M_Granite")
    # pedestal and statue (faces south)
    sx, sy = 518.1 - o[0], -1134.8 - o[1]
    B.boxmm((sx - 2.2, sy - 2.0, 1.6), (sx + 2.2, sy + 2.0, 2.2), "M_Granite")
    B.boxmm((sx - 1.7, sy - 1.6, 2.2), (sx + 1.7, sy + 1.6, 4.3), "M_Granite")
    seated_figure(B, (sx, sy, 4.3), -90.0, 1.0)
    # the two columns with lamp lanterns
    for px, py in ((498.5, -1147.3), (537.7, -1146.6)):
        x, y = px - o[0], py - o[1]
        B.boxmm((x - 1.2, y - 1.2, 0.0), (x + 1.2, y + 1.2, 1.4), "M_Granite")
        B.lathe([(0.62, 1.4), (0.58, 6.0), (0.5, 11.5), (0.75, 11.8), (0.75, 12.3), (0.0, 12.3)], "M_Marble", 16, center=(x, y, 0))
        B.lathe([(0.35, 12.3), (0.45, 12.9), (0.25, 13.6), (0.0, 13.9)], "M_Railing", 8, center=(x, y, 0))
    zone = {"poly": [(492.0, -1152.0), (544.0, -1152.0), (544.0, -1125.0), (492.0, -1125.0)], "clear": ["props"]}
    export_site("PK_LincolnHeadOfState", B, o, {"what": "Seated Lincoln (stylised) on its exedra platform, steps, two lamp columns"},
                collide="complex", zone=zone)
    export_site("PK_LincolnHeadOfStateSteps", B.vis, o, {"what": "visible steps of PK_LincolnHeadOfState"}, collide="none")


def logan_monument():
    """General John Logan Memorial (Saint-Gaudens, 1897, public domain): equestrian bronze holding a flag on a tall granite
    pedestal on a grassy mound (OSM (359.3, -1873.0), at Michigan and 9th)."""
    o = (359.3, -1873.0)
    B = PlanBuilder()
    B.lathe([(16.0, 0.0), (13.0, 1.3), (8.0, 3.2), (5.0, 3.8), (0.0, 3.9)], "M_Lawn", 32)           # the mound
    B.boxmm((-3.0, -2.0, 3.6), (3.0, 2.0, 4.4), "M_Granite")
    B.boxmm((-2.5, -1.6, 4.4), (2.5, 1.6, 8.6), "M_Granite")
    B.boxmm((-2.8, -1.8, 8.6), (2.8, 1.8, 9.0), "M_Granite")
    horse_rider(B, (0.0, 0.0, 9.0), 180.0, 1.1, "walk", "flag")
    zone = {"poly": [(342.0, -1890.0), (376.0, -1890.0), (376.0, -1856.0), (342.0, -1856.0)], "clear": ["props"]}
    export_site("PK_LoganMonument", B, o, {"what": "Logan Monument: mound, granite pedestal, equestrian with flag (stylised), ~15 m"},
                collide="complex", zone=zone)


def spirit_of_music():
    """Spirit of Music (Polasek, 1923, public domain; Theodore Thomas memorial): a bronze woman with a lyre on a granite
    pedestal before a curved granite exedra (OSM (354.0, -1564.8), 13 x 8 m)."""
    o = (354.0, -1564.8)
    B = PlanBuilder()
    pts = [(6.5 * math.cos(math.pi * k / 16), -1.0 + 4.5 * math.sin(math.pi * k / 16) * -1.0) for k in range(17)]
    B.sweep_open([(x, -y) for x, y in pts], [(0.4, 0.0), (0.4, 1.1), (-0.4, 1.1), (-0.4, 0.0)], "M_Granite")
    B.boxmm((-1.4, -1.4, 0.0), (1.4, 1.4, 0.5), "M_Granite")
    B.boxmm((-1.0, -1.0, 0.5), (1.0, 1.0, 3.2), "M_Granite")
    m = "M_LionBronze"
    B.lathe([(0.5, 3.2), (0.42, 4.0), (0.3, 5.0), (0.22, 5.4), (0.0, 5.45)], m, 10)                 # robed figure
    B.ellipsoid((0.0, 0.0, 5.7), (0.13, 0.13, 0.17), m, 8, 6)
    limb(B, [(-0.25, 0.1, 4.6), (-0.6, 0.15, 4.4), (-0.75, 0.0, 4.2)], [0.06, 0.05, 0.05], m, 6)
    B.prism(Vector((-0.95, 0.12, 3.9)), Vector((0, 1, 0)), Vector((0, 0, 1)), [(-0.3, 0.0), (0.3, 0.0), (0.4, 0.9), (0.0, 1.1), (-0.4, 0.9)], 0.08, m)   # lyre
    zone = {"poly": [(345.0, -1572.0), (363.0, -1572.0), (363.0, -1558.0), (345.0, -1558.0)], "clear": ["props"]}
    export_site("PK_SpiritOfMusic", B, o, {"what": "Spirit of Music (stylised): figure with lyre on a pedestal, curved exedra"},
                collide="complex", zone=zone)


def petrillo_shell():
    """James C. Petrillo Music Shell (1978): a 30 x 30 m stage house facing east over the Butler Field lawn, steel truss
    frame with a canopy roof over the stage front, cream panel side walls (OSM footprint x 625-656, y -977.6..-947.5)."""
    o = (640.0, -962.5)
    B = PlanBuilder()
    B.boxmm((-15.0, -15.0, 0.0), (-1.0, 15.0, 13.0), "M_Concrete")                          # back stage house
    for sd in (-1, 1):
        B.boxmm((-1.0, sd * 15.0 - (0.6 if sd > 0 else 0.0), 0.0), (15.0, sd * 15.0 + (0.0 if sd > 0 else 0.6), 11.0), "M_Marble")   # side walls
    B.boxmm((-1.0, -14.4, 0.0), (14.0, 14.4, 1.4), "M_Concrete")                             # stage deck
    B.face([(-0.99, -14.4, 1.4), (-0.99, 14.4, 1.4), (-0.99, 14.4, 11.0), (-0.99, -14.4, 11.0)], "M_GraniteBlack")
    # canopy: sloping roof from the back (13.5 m) to the front (10.5 m), on a truss frame
    B.face([(-15.0, -15.6, 13.6), (15.5, -15.6, 11.0), (15.5, 15.6, 11.0), (-15.0, 15.6, 13.6)], "M_Steel")
    B.face([(-15.0, 15.6, 13.4), (15.5, 15.6, 10.8), (15.5, -15.6, 10.8), (-15.0, -15.6, 13.4)], "M_Marble")
    for y_ in (-15.6, 15.6):
        B.beam((15.5, y_, 0.0), (15.5, y_, 11.0), 0.6, 0.6, "M_Steel")
        B.beam((15.5, y_, 11.0), (-15.0, y_, 13.6), 0.5, 0.9, "M_Steel")
    B.beam((15.5, -15.6, 11.4), (15.5, 15.6, 11.4), 0.7, 1.2, "M_Steel")
    for k in range(7):
        y_ = -12.0 + k * 4.0
        B.boxmm((13.0, y_ - 0.4, 9.0), (13.8, y_ + 0.4, 10.6), "M_Railing")                   # lighting rig
    zone = {"poly": [(622.0, -980.0), (660.0, -980.0), (660.0, -945.0), (622.0, -945.0)], "clear": ["props"]}
    export_site("PK_PetrilloShell", B, o, {"what": "Petrillo Music Shell: stage house, side walls, sloping canopy on a truss frame, faces east"},
                collide="complex", zone=zone)


def great_lakes_fountain():
    """Fountain of the Great Lakes (Lorado Taft, 1913, public domain) in the Art Institute's South Garden: five bronze women
    (the lakes) passing water down from shell to shell, in a pool against the museum wall, facing west (OSM (365.0, -968.6))."""
    o = (365.0, -968.6)
    B = PlanBuilder()
    B.slab(rrect(-6.0, -6.5, 3.2, 6.5, 1.5), 0.0, 0.55, "M_Granite")
    B.slab(rrect(-5.6, -6.1, 2.8, 6.1, 1.2), 0.3, 0.5, "M_Water")
    B.boxmm((0.0, -2.2, 0.3), (2.6, 2.2, 1.4), "M_Granite")
    m = "M_LionBronze"
    for (x, y, z, h) in ((1.3, 0.0, 1.4, 2.4), (0.2, -1.6, 0.5, 1.9), (0.2, 1.6, 0.5, 1.9), (-0.9, -0.8, 0.5, 1.7), (-0.9, 0.8, 0.5, 1.7)):
        B.lathe([(0.45, z), (0.38, z + h * 0.5), (0.25, z + h * 0.85), (0.0, z + h * 0.9)], m, 10, center=(x, y, 0))
        B.ellipsoid((x, y, z + h * 0.97), (0.13, 0.13, 0.16), m, 8, 6)
        B.ellipsoid((x - 0.35, y, z + h * 0.7), (0.3, 0.22, 0.1), m, 8, 4, half=True)          # shell
    zone = {"poly": [(358.0, -976.0), (369.0, -976.0), (369.0, -961.0), (358.0, -961.0)], "clear": ["props"]}
    export_site("PK_GreatLakesFountain", B, o, {"what": "Fountain of the Great Lakes (stylised): five figures with shells in a pool"},
                collide="complex", zone=zone)


def stock_exchange_arch():
    """Chicago Stock Exchange Arch (Adler & Sullivan, 1894; re-erected 1977 east of the Art Institute, OSM (549, -761)):
    the big round-headed entrance arch, ~9 m wide and ~11 m tall, with its ornamented terra cotta frame."""
    o = (549.0, -761.0)
    B = PlanBuilder()
    W, H, T = 9.0, 11.0, 1.4
    B.wall(Vector((-W / 2, 0.7, 0.0)), Vector((1, 0, 0)), Vector((0, 0, 1)), W, H, T, "M_TerraCotta", holes=[(W / 2, 5.2, 0.0, 5.0, True)])
    B.boxmm((-W / 2 - 0.2, -0.9, H), (W / 2 + 0.2, 0.9, H + 0.6), "M_TerraCotta")
    # the ornamented archivolt: a half ring standing proud of the front face round the opening
    ring_pts = [(3.1 * math.cos(math.pi * k / 16), -0.75, 5.0 + 3.1 * math.sin(math.pi * k / 16)) for k in range(17)]
    B.tube([Vector(q) for q in ring_pts], [0.35] * 17, "M_TerraCotta", 8)
    zone = {"poly": [(542.0, -766.0), (556.0, -766.0), (556.0, -756.0), (542.0, -756.0)], "clear": ["props"]}
    export_site("PK_StockExchangeArch", B, o, {"what": "Chicago Stock Exchange Arch (Sullivan, 1894)"}, collide="complex", zone=zone)


# ================================================================== 5. The Loop's plazas and their sculptures
BV3 = None


def bv3_rects(centers, grow=1.5):
    """Footprint rectangles (plan polygons, grown by `grow` m) of the City Sample buildings (Saved/Mashup/buildings_v3.json)
    whose centres are within 3 m of the given points: the clear stage removes those buildings whole."""
    global BV3
    if BV3 is None:
        BV3 = json.load(open(ROOT + "/Saved/Mashup/buildings_v3.json"))["buildings"]
    out = []
    for cx, cy in centers:
        b = min(BV3, key=lambda q: math.hypot(q["x"] - cx, q["y"] - cy))
        if math.hypot(b["x"] - cx, b["y"] - cy) > 3.0:
            print("WARNING: no City Sample building at", cx, cy)
            continue
        a = math.radians(b["yaw"])
        c_, s_ = math.cos(a), math.sin(a)
        w, d = b["w"] / 2 + grow, b["d"] / 2 + grow
        out.append([(round(b["x"] + c_ * dx - s_ * dy, 2), round(b["y"] + s_ * dx + c_ * dy, 2)) for dx, dy in ((-w, -d), (w, -d), (w, d), (-w, d))])
    return out


def plate(B, pts2, origin, right, up, thick, m):
    """A flat plate (2-D outline in a local right/up frame at origin) extruded by thick: sculpture sheet steel."""
    B.prism(Vector(origin), Vector(right), Vector(up), list(pts2), thick, m)


def ellipse_pts(a, b, n=28, cx=0.0, cy=0.0):
    return [(cx + a * math.cos(2 * math.pi * k / n), cy + b * math.sin(2 * math.pi * k / n)) for k in range(n)]


def chicago_picasso():
    """The Chicago Picasso (1967; a court ruled it public domain in 1970), stylised: 15.2 m Cor-Ten steel on its sloped
    base (OSM footprint (-185.8..-175.4, -438.5..-432.2)), facing south over Daley Plaza: two tall 'wing' plates, the T-shaped
    face with its long nose, the fan of rods, the beaded neck and spike, the two rounded shoulders. Plus the plaza paving
    (granite) where the plan had City Sample towers, and the Eternal Flame (OSM (-158.6, -437.4))."""
    o = (-180.6, -435.3)
    B = PlanBuilder()
    m = "M_CorTen"
    # plaza: granite paving over the cleared lot
    B.slab(P2([(-190.0, -462.0), (-152.0, -462.0), (-152.0, -408.0), (-190.0, -408.0)], o), -0.1, 0.06, "M_Granite")
    # base: sloped plinth (frustum) 10.4 x 6.3 m at the ground
    B.sweep([(-1, -1), (1, -1), (1, 1), (-1, 1)], "M_TowerBlack", [(5.2, 3.15, 0.06, 0, 0), (4.0, 2.4, 0.9, 0, 0), (0, 0, 0.9, 0, 0)], smooth=False)
    # shoulders: two rounded humps either side (quarter cylinders), x across, facing south (-y)
    for sd in (-1, 1):
        prof = [(sd * 4.3, 0.0)] + [(sd * (1.6 + 2.7 * math.cos(math.pi / 2 * k / 8)), 2.9 * math.sin(math.pi / 2 * k / 8)) for k in range(9)]
        prof = [(x, z + 0.9) for x, z in prof] + [(sd * 1.6, 0.9)]
        if sd < 0:
            prof = prof[::-1]
        plate(B, prof, (0, 1.2, 0), (1, 0, 0), (0, 0, 1), 2.4, m)
    # spike/neck: a tapering blade from the base up to the face, with stacked 'beads'
    plate(B, [(-1.6, 0.9), (1.6, 0.9), (0.25, 7.0), (-0.25, 7.0)], (0, 0.15, 0), (1, 0, 0), (0, 0, 1), 0.3, m)
    for k, z in enumerate((7.2, 7.9, 8.6)):
        plate(B, [(-0.45, z), (0.0, z - 0.35), (0.45, z), (0.0, z + 0.35)], (0, 0.15, 0), (1, 0, 0), (0, 0, 1), 0.3, m)
    # wings: two tall ellipses (about 3.4 x 12 m) leaning out, behind the face, meeting at the top
    for sd in (-1, 1):
        pts = ellipse_pts(1.75, 5.9, 32, sd * 1.6, 9.0)
        pts = [(x + sd * 0.22 * (z - 9.0) / 5.9 * 0.0, z) for x, z in pts]
        plate(B, pts, (0, 0.9, 0), (1, 0, 0), (0, 0, 1), 0.22, m)
    # the fan of rods between the wings (behind the face)
    for k in range(13):
        a = math.radians(-60 + 120 * k / 12)
        top = Vector((2.6 * math.sin(a), 0.6, 9.2 + 3.2 * math.cos(a)))
        B.rod((0.0, 0.6, 7.6), top, 0.035, "M_Steel", 4, caps=False)
    # the face: wide forehead and long nose (the T), eyes slit
    face = [(-2.0, 12.9), (2.0, 12.9), (2.1, 12.4), (0.45, 11.9), (0.38, 9.6), (0.0, 9.25), (-0.38, 9.6), (-0.45, 11.9), (-2.1, 12.4)]
    plate(B, face, (0, -0.05, 0), (1, 0, 0), (0, 0, 1), 0.25, m)
    plate(B, ellipse_pts(0.55, 0.12, 12, 0.0, 12.35), (0, -0.07, 0), (1, 0, 0), (0, 0, 1), 0.03, "M_TowerBlack")
    # the Eternal Flame (veterans' memorial) on the plaza
    fx, fy = -158.6 - o[0], -437.4 - o[1]
    B.lathe([(1.2, 0.06), (1.2, 0.7), (0.9, 0.9), (0.0, 0.9)], "M_Granite", 16, center=(fx, fy, 0))
    B.lathe([(0.35, 0.9), (0.25, 1.4), (0.0, 1.7)], "M_SignBulb", 8, center=(fx, fy, 0))
    rects = bv3_rects([(-186.4, -448.8), (-171.1, -418.9)])
    zone = {"poly": [(-191.0, -463.0), (-151.0, -463.0), (-151.0, -407.0), (-191.0, -407.0)], "clear": ["props", "buildings"],
            "buildings": rects}
    export_site("PK_ChicagoPicasso", B, o, {"what": "Chicago Picasso (stylised), 15.2 m Cor-Ten on its plinth; Daley Plaza paving; Eternal Flame",
                                            "removes": "City Sample 215 m tower (-186.4, -448.8) and 16 m lowrise (-171.1, -418.9) on the plaza"},
                collide="complex", zone=zone)


def blade(B, foot, hub, w0, w1, fin, m, up=(0, 0, 1)):
    """A Calder-style tapering plate leg from foot to hub (widths w0 -> w1) with a stiffening fin along its centreline."""
    a, b = Vector(foot), Vector(hub)
    t = (b - a).normalized()
    side = t.cross(Vector(up))
    if side.length < 1e-6:
        side = Vector((1, 0, 0))
    side.normalize()
    n_ = side.cross(t).normalized()
    th = 0.12
    P = [a - side * w0 / 2, a + side * w0 / 2, b + side * w1 / 2, b - side * w1 / 2]
    B.face(P, m)
    B.face([p - n_ * th for p in P][::-1], m)
    for i in range(4):
        q0, q1 = P[i], P[(i + 1) % 4]
        B.face([q0, q0 - n_ * th, q1 - n_ * th, q1][::-1], m)
    F = [a, b, b + n_ * fin, a + n_ * fin * 0.25]
    B.face(F, m)
    B.face(F[::-1], m)


def calder_flamingo():
    """Flamingo (Alexander Calder, 1974), stylised stand-in: a 16 m vermilion steel stabile of tapering plate legs with
    fins, two arches and a tall 'neck' loop, in Federal Plaza (OSM (-155.9, -967.9)); granite paving over the cleared lot."""
    o = (-155.9, -967.9)
    B = PlanBuilder()
    m = "M_CalderRed"
    B.slab(P2([(-180.0, -985.0), (-147.0, -985.0), (-147.0, -945.0), (-180.0, -945.0)], o), -0.1, 0.06, "M_Granite")
    H1 = Vector((-1.5, 0.3, 9.5))                  # main hub
    H2 = Vector((3.2, -0.6, 12.0))                 # neck hub
    A = Vector((1.0, 0.5, 16.0))                   # top of the neck loop
    for f in ((-8.5, -3.2, 0.0), (-7.0, 3.6, 0.0), (1.5, 3.8, 0.0)):
        blade(B, f, H1, 1.0, 4.4, 1.6, m)
    for f in ((8.0, -2.8, 0.0), (6.5, 3.0, 0.0)):
        blade(B, f, H2, 1.0, 4.0, 1.5, m)
    blade(B, H1, H2, 3.6, 3.2, 1.2, m)
    blade(B, H1, A, 3.2, 1.4, 1.1, m)
    blade(B, A, H2, 1.4, 2.6, 1.0, m)
    blade(B, (-1.0, -3.0, 0.0), (0.2, -0.8, 6.5), 0.8, 2.6, 0.8, m)
    for f in ((-8.5, -3.2), (-7.0, 3.6), (1.5, 3.8), (8.0, -2.8), (6.5, 3.0), (-1.0, -3.0)):
        B.boxmm((f[0] - 0.5, f[1] - 0.5, 0.06), (f[0] + 0.5, f[1] + 0.5, 0.25), "M_Steel")
    rects = bv3_rects([(-166.3, -961.9)])
    zone = {"poly": [(-181.0, -986.0), (-146.0, -986.0), (-146.0, -944.0), (-181.0, -944.0)], "clear": ["props", "buildings"], "buildings": rects}
    export_site("PK_Flamingo", B, o, {"what": "Flamingo (Calder, stylised stand-in) 16 m; Federal Plaza paving",
                                      "removes": "City Sample 211 m tower (-166.3, -961.9) on the plaza"}, collide="complex", zone=zone)


def chagall_four_seasons():
    """The Four Seasons (Marc Chagall, 1974), stylised stand-in: a 21.3 x 3.05 x 4.27 m box clad in mosaic on all four
    sides (blues, with seasonal patches), on a low granite base, under its 1994 glass canopy, in Chase Tower Plaza
    (OSM (-166.9..-162.8, -726.2..-703.8)); plaza paving and the square fountain pool where the plan had a 292 m tower."""
    o = (-164.9, -715.0)
    B = PlanBuilder()
    B.slab(P2([(-186.0, -744.0), (-150.0, -744.0), (-150.0, -700.0), (-186.0, -700.0)], o), -0.1, 0.06, "M_Granite")
    # fountain pool (OSM w127107046 at (-193, -708) lies on the plan's next lot; the pool sits at the plaza's west side)
    B.slab(P2([(-185.0, -718.0), (-176.0, -718.0), (-176.0, -706.0), (-185.0, -706.0)], o), 0.0, 0.5, "M_Granite")
    B.slab(P2([(-184.4, -717.4), (-176.6, -717.4), (-176.6, -706.6), (-184.4, -706.6)], o), 0.2, 0.42, "M_Water")
    yaw = math.degrees(math.atan2(-726.2 - -703.9, -162.8 - -166.9)) + 90.0       # the box leans ~1.5 deg (OSM)
    L, W, H = 21.3, 3.05, 4.27
    B.boxmm((-W / 2 - 0.4, -L / 2 - 0.4, 0.0), (W / 2 + 0.4, L / 2 + 0.4, 0.45), "M_Granite")
    import random
    rnd = random.Random(1974)
    pal = ["M_MosaicBlue"] * 6 + ["M_MosaicYellow", "M_MosaicRed", "M_MosaicGreen", "M_MosaicWhite", "M_MosaicWhite"]
    z0 = 0.45
    for (p0, p1, n_) in (((-W / 2, -L / 2), (W / 2, -L / 2), (0, -1)), ((W / 2, -L / 2), (W / 2, L / 2), (1, 0)),
                         ((W / 2, L / 2), (-W / 2, L / 2), (0, 1)), ((-W / 2, L / 2), (-W / 2, -L / 2), (-1, 0))):
        a, b = Vector((*p0, 0)), Vector((*p1, 0))
        Wf = (b - a).length
        nu = max(2, int(Wf / 0.9))
        nv = 5
        for i in range(nu):
            for j in range(nv):
                q0, q1 = a.lerp(b, i / nu), a.lerp(b, (i + 1) / nu)
                za, zb = z0 + H * j / nv, z0 + H * (j + 1) / nv
                B.face([(q0.x, q0.y, za), (q1.x, q1.y, za), (q1.x, q1.y, zb), (q0.x, q0.y, zb)], rnd.choice(pal))
    B.face([(-W / 2, -L / 2, z0 + H), (W / 2, -L / 2, z0 + H), (W / 2, L / 2, z0 + H), (-W / 2, L / 2, z0 + H)], "M_MosaicBlue")
    # the glass canopy on slim posts
    for sx in (-1, 1):
        for sy in (-1, 0, 1):
            B.cyl((sx * (W / 2 + 1.2), sy * (L / 2 + 0.5), 0.45), H + 1.4, 0.08, "M_Steel", 8)
    B.boxmm((-W / 2 - 1.5, -L / 2 - 0.9, z0 + H + 1.4), (W / 2 + 1.5, L / 2 + 0.9, z0 + H + 1.55), "M_Glass")
    rotate_verts(B, yaw, (0.0, 0.0)) if False else None
    rects = bv3_rects([(-171.1, -728.7)])
    zone = {"poly": [(-187.0, -745.0), (-149.0, -745.0), (-149.0, -701.0), (-187.0, -701.0)], "clear": ["props", "buildings"], "buildings": rects}
    export_site("PK_FourSeasons", B, o, {"what": "Four Seasons (Chagall, stylised mosaic box) + glass canopy; Chase Tower Plaza paving and pool",
                                         "removes": "City Sample 292 m tower (-171.1, -728.7) on the plaza"}, collide="complex", zone=zone)


def miro_chicago():
    """Miro's Chicago ('The Sun, the Moon and One Star', Joan Miro, 1981), stylised stand-in: a 12 m figure of concrete with
    ceramic-tile patches: bulbous lower body, a flat disc collar at the waist, a narrow neck, the round flat head and the
    fork (trident) crown, on its small plaza on Washington Street (OSM (-215.8..-211.4, -498.8..-494.5))."""
    o = (-213.6, -496.6)
    B = PlanBuilder()
    B.boxmm((-3.5, -3.0, 0.0), (3.5, 3.0, 0.3), "M_Granite")
    prof = [(1.6, 0.3), (2.3, 1.4), (2.4, 2.6), (1.9, 4.0), (1.0, 5.2), (0.55, 6.2), (0.5, 6.8), (0.0, 6.9)]
    B.lathe(prof, "M_Concrete", 20)
    B.lathe([(0.5, 6.6), (2.3, 6.8), (2.4, 7.05), (0.5, 7.25), (0.0, 7.3)], "M_Concrete", 24)                  # collar disc
    B.cyl((0.0, 0.0, 7.2), 1.2, 0.35, "M_Concrete", 10)                                                       # neck
    B.ellipsoid((0.0, 0.0, 9.0), (1.25, 0.45, 1.05), "M_Concrete", 18, 10)                                     # flat round head
    B.cyl((0.0, 0.0, 10.0), 0.6, 0.18, "M_Concrete", 8)
    B.boxmm((-0.95, -0.12, 10.55), (0.95, 0.12, 10.8), "M_Concrete")                                           # fork crossbar
    for dx in (-0.85, -0.28, 0.28, 0.85):
        B.boxmm((dx - 0.09, -0.09, 10.8), (dx + 0.09, 0.09, 12.1), "M_Concrete")                               # tines
    B.ellipsoid((0.0, -0.46, 9.1), (0.32, 0.06, 0.32), "M_PaintYellow", 10, 4)                                  # the 'sun' tile
    import random
    rnd = random.Random(1981)
    for k in range(22):
        a = rnd.uniform(0, 2 * math.pi)
        z = rnd.uniform(0.8, 5.0)
        r = 0.0
        for (r0, z0_), (r1, z1_) in zip(prof, prof[1:]):
            if z0_ <= z <= z1_:
                r = r0 + (r1 - r0) * (z - z0_) / (z1_ - z0_)
        c = Vector((r * math.cos(a), r * math.sin(a), z))
        n_ = Vector((math.cos(a), math.sin(a), 0))
        B.card(c + n_ * 0.03, n_, (0, 0, 1), rnd.uniform(0.3, 0.7), rnd.uniform(0.3, 0.7), rnd.choice(("M_MosaicRed", "M_MosaicYellow", "M_MosaicBlue", "M_MosaicGreen")))
    zone = {"poly": [(-218.5, -500.0), (-208.5, -500.0), (-208.5, -490.0), (-218.5, -490.0)], "clear": ["props"]}
    export_site("PK_MiroChicago", B, o, {"what": "Miro's Chicago (stylised stand-in), 12 m"}, collide="complex", zone=zone)


# block letters on a 3 x 5 grid (strokes as rectangles in letter units, x 0..3, y 0..5)
GLYPHS = {
    "C": [(0, 0, 3, 1), (0, 0, 1, 5), (0, 4, 3, 5)],
    "H": [(0, 0, 1, 5), (2, 0, 3, 5), (0, 2, 3, 3)],
    "I": [(1, 0, 2, 5), (0.5, 0, 2.5, 0.8), (0.5, 4.2, 2.5, 5)],
    "A": [(0, 0, 1, 5), (2, 0, 3, 5), (0, 4, 3, 5), (0, 2, 3, 3)],
    "G": [(0, 0, 3, 1), (0, 0, 1, 5), (0, 4, 3, 5), (2, 0, 3, 2.6), (1.5, 1.8, 3, 2.6)],
    "O": [(0, 0, 3, 1), (0, 0, 1, 5), (2, 0, 3, 5), (0, 4, 3, 5)],
}


def letter(B, ch, origin, right, up, size, depth, m):
    """Extruded block letter `ch` with its bottom-left at origin, height = size (5 units)."""
    u = size / 5.0
    o, r, up_ = Vector(origin), Vector(right).normalized(), Vector(up).normalized()
    n_ = r.cross(up_).normalized()
    for x0, y0, x1, y1 in GLYPHS[ch]:
        c = o + r * ((x0 + x1) / 2 * u) + up_ * ((y0 + y1) / 2 * u) + n_ * (depth / 2)
        R = Matrix((r, up_, n_)).transposed()
        B.box(c, ((x1 - x0) * u, (y1 - y0) * u, depth), m, R)


def chicago_theatre():
    """The Chicago Theatre (Rapp & Rapp, 1921) on State Street (OSM building, cropped to x <= 56 where the plan keeps a City
    Sample tower behind): six storeys of cream terra cotta, the State Street front with its great arch and round window,
    the 18 m vertical C-H-I-C-A-G-O sign in bulbs and the marquee, and the five-storey Page Brothers Building at the corner.
    Replaces the City Sample towers the plan put on the site (146 m at (12.4, -237.6), 120 m at (42.5, -231.5))."""
    o = (6.8, -253.6)                  # the State Street facade line, at the arch
    B = PlanBuilder()
    th = [(56.0, -211.6), (56.0, -262.8), (6.8, -262.5), (6.8, -244.6), (26.9, -244.6), (26.3, -211.7)]
    pb = [(26.3, -211.7), (26.9, -244.6), (6.8, -244.6), (6.6, -211.9)]
    B.slab(P2(th, o), 0.0, 24.0, "M_RoofFlat", "M_TerraCotta")
    B.slab(P2(pb, o), 0.0, 21.0, "M_RoofFlat", "M_Brick")
    for zb in range(1, 5):                                          # Page Brothers windows (cast-iron front)
        for k in range(9):
            y0 = -244.0 + k * 3.6
            B.face([(6.55 - o[0], y0 - o[1], zb * 4.2 - 2.8), (6.55 - o[0], y0 + 2.4 - o[1], zb * 4.2 - 2.8),
                    (6.55 - o[0], y0 + 2.4 - o[1], zb * 4.2 - 0.6), (6.55 - o[0], y0 - o[1], zb * 4.2 - 0.6)][::-1], "M_GlassDark")
    # theatre front: the triumphal arch (8 m wide) with the round window, cornice, side piers with windows
    xf = -0.02
    yA, yB = -244.6 - o[1], -262.5 - o[1]
    B.wall(Vector((xf, yA, 4.5)), Vector((0, -1, 0)), Vector((0, 0, 1)), yA - yB, 17.0, 0.8, "M_TerraCotta",
           holes=[((yA - yB) / 2, 8.0, 0.0, 11.0, True)], fill="M_GlassDark", fill_inset=0.6)
    yc = (yA + yB) / 2
    B.torus((xf - 0.1, yc, 11.0), 3.0, 0.25, "M_TerraCotta", 32, 6, mtx=Matrix.Rotation(math.pi / 2, 3, "Y"))     # round window ring
    B.boxmm((xf - 1.0, yB - 0.3, 21.5), (xf + 0.3, yA + 0.3, 22.6), "M_TerraCotta")                                # cornice
    B.boxmm((xf - 0.5, yB, 22.6), (xf + 0.3, yA, 24.6), "M_TerraCotta")
    # ground floor: lobby glass and the marquee (projects 4 m over the sidewalk, 4.6 m up)
    B.face([(xf - 0.05, yA, 0.0), (xf - 0.05, yA, 4.5), (xf - 0.05, yB, 4.5), (xf - 0.05, yB, 0.0)], "M_GlassDark")
    B.boxmm((xf - 4.2, yB + 1.0, 4.6), (xf, yA - 1.0, 5.2), "M_TerraCotta")
    B.boxmm((xf - 4.2, yB + 1.0, 5.2), (xf - 3.9, yA - 1.0, 7.4), "M_SignRed")
    for sd in (-1, 1):
        B.boxmm((xf - 4.2, (yB + 1.0) if sd < 0 else (yA - 1.3), 5.2), (xf, (yB + 1.3) if sd < 0 else (yA - 1.0), 7.4), "M_SignRed")
    B.face([(xf - 4.25, yB + 1.0, 5.4), (xf - 4.25, yA - 1.0, 5.4), (xf - 4.25, yA - 1.0, 7.2), (xf - 4.25, yB + 1.0, 7.2)][::-1], "M_SignBulb")
    B.face([(xf - 4.2, yB + 1.0, 4.58), (xf, yB + 1.0, 4.58), (xf, yA - 1.0, 4.58), (xf - 4.2, yA - 1.0, 4.58)][::-1], "M_SignBulb")   # soffit lights
    # the small CHICAGO crest on the marquee
    letter_h, gap = 0.9, 0.25
    word = "CHICAGO"
    wtot = len(word) * (letter_h * 0.6 + gap)
    for i, ch in enumerate(word):
        y = yc + wtot / 2 - i * (letter_h * 0.6 + gap)
        letter(B, ch, (xf - 4.35, y, 7.55), (0, -1, 0), (0, 0, 1), letter_h, 0.1, "M_SignBulb")
    B.boxmm((xf - 4.3, yc - wtot / 2 - 0.3, 7.4), (xf - 4.1, yc + wtot / 2 + 0.3, 8.7), "M_SignRed")
    # the vertical sign: a red blade 2.6 m wide, 18 m tall, projecting west from the facade at the north pier, letters both faces
    ys = yA - 1.4
    x0s, x1s = xf - 3.4, xf - 0.4
    z0s, z1s = 8.0, 26.5
    B.boxmm((x0s, ys - 0.35, z0s), (x1s, ys + 0.35, z1s), "M_SignRed")
    B.boxmm((x0s - 0.4, ys - 0.5, z1s), (x1s + 0.2, ys + 0.5, z1s + 1.3), "M_SignRed")         # crown
    for k, ch in enumerate(word):
        zc = z1s - 1.6 - k * 2.45
        for sd in (-1, 1):
            letter(B, ch, (x0s + 0.6 if sd < 0 else x1s - 0.6, ys + sd * 0.36, zc - 1.0), (sd * 1.0, 0, 0) if False else ((1, 0, 0) if sd < 0 else (-1, 0, 0)),
                   (0, 0, 1), 1.8, 0.08, "M_SignBulb")
    for zb in (z0s, z1s):                                          # bulb borders
        B.boxmm((x0s - 0.05, ys - 0.4, zb - 0.1), (x1s + 0.05, ys + 0.4, zb + 0.1), "M_SignBulb")
    for xb in (x0s, x1s):
        B.boxmm((xb - 0.08, ys - 0.4, z0s), (xb + 0.08, ys + 0.4, z1s), "M_SignBulb")
    B.beam((x1s, ys, 12.0), (xf + 0.3, ys, 12.0), 0.2, 0.2, "M_Steel")
    B.beam((x1s, ys, 22.0), (xf + 0.3, ys, 22.0), 0.2, 0.2, "M_Steel")
    rects = bv3_rects([(12.4, -237.6), (42.5, -231.5)])
    zone = {"poly": [(6.0, -263.5), (56.5, -263.5), (56.5, -211.0), (6.0, -211.0)], "clear": ["props", "buildings"], "buildings": rects}
    export_site("PK_ChicagoTheatre", B, o, {"what": "Chicago Theatre: 6-storey terra cotta front with the great arch, 18 m CHICAGO vertical sign, "
                                                    "marquee; Page Brothers Building",
                                            "removes": "City Sample towers 146 m (12.4, -237.6) and 120 m (42.5, -231.5) on the site"},
                collide="complex", zone=zone)


# ================================================================== 6. Maggie Daley Park
MD_RIBBON = [(748.6, -421.2), (750.1, -418.6), (750.6, -415.5), (750.0, -412.5), (748.4, -409.9), (746.0, -408.0), (743.1, -406.9),
             (740.0, -406.9), (737.1, -408.0), (732.2, -411.5), (726.8, -414.0), (720.9, -414.6), (715.0, -413.3), (710.9, -411.6),
             (706.5, -411.2), (702.1, -412.0), (698.1, -414.0), (694.9, -417.0), (692.4, -422.5), (691.2, -427.2), (690.7, -436.4),
             (688.5, -442.2), (684.6, -447.1), (679.4, -450.6), (673.1, -453.3), (666.0, -453.3), (657.0, -450.4), (652.4, -450.4),
             (648.0, -451.9), (644.3, -454.7), (641.7, -458.6), (640.6, -463.1), (640.7, -467.7), (642.3, -472.0), (645.1, -475.6),
             (649.0, -478.2), (653.5, -479.4), (658.1, -479.1), (668.8, -475.5), (678.2, -469.5), (684.3, -466.5), (691.0, -465.2),
             (697.8, -465.6), (702.7, -467.3), (706.9, -470.2), (709.3, -473.1), (714.1, -480.3), (721.3, -483.9), (729.2, -485.4),
             (737.3, -484.6), (744.5, -480.7), (750.2, -474.7), (753.6, -467.3), (754.3, -463.4), (754.0, -459.5), (752.7, -455.9),
             (750.4, -452.7), (744.4, -444.2), (741.9, -440.0), (740.9, -435.3), (741.5, -430.5), (743.5, -426.1)]
MD_CLIMB = [
    [(698.1, -444.8), (697.0, -447.5), (698.1, -451.3), (699.8, -454.7), (705.9, -456.1), (709.8, -454.9), (713.1, -458.1), (713.0, -460.2),
     (711.5, -463.1), (712.5, -466.3), (718.9, -471.4), (721.0, -470.5), (724.1, -471.2), (726.3, -469.7), (730.6, -471.4), (733.5, -470.6),
     (734.9, -469.1), (736.7, -465.0), (736.8, -463.2), (735.3, -460.9), (730.4, -459.1), (726.1, -455.2), (725.3, -453.4), (718.7, -452.7),
     (716.3, -449.7), (718.4, -446.3), (722.1, -445.1), (726.4, -441.7), (727.7, -439.5), (727.3, -434.9), (727.6, -432.2), (726.0, -430.7),
     (726.4, -427.5), (725.1, -426.9), (722.0, -427.7), (720.1, -429.8), (717.1, -430.2), (715.4, -431.5), (714.4, -433.9), (713.5, -433.7),
     (712.7, -430.8), (710.0, -429.9), (708.4, -428.9), (707.2, -429.8), (702.4, -430.8), (699.5, -434.4), (697.4, -435.6), (696.9, -438.2),
     (697.6, -440.4)],
    [(648.9, -456.5), (651.7, -456.0), (652.6, -457.2), (654.5, -457.1), (663.5, -463.1), (665.5, -463.9), (665.7, -466.6), (661.7, -468.4),
     (659.0, -469.2), (657.5, -467.7), (653.3, -466.6), (648.0, -466.3), (648.1, -462.2), (647.4, -460.5), (647.9, -459.6), (647.8, -458.0)],
]


def craggy(B, poly, h0, h1, m, seed=1, tiers=3):
    """A sculpted 'ice-climbing' massif: the outline extruded in tiers that step in and rise to a ragged crown."""
    import random
    rnd = random.Random(seed)
    pts = ccw(poly)
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    rings = []
    for t in range(tiers + 1):
        k = 1.0 - 0.18 * t
        z = h0 + (h1 - h0) * t / tiers
        rings.append([Vector((cx + (x - cx) * k, cy + (y - cy) * k, z * rnd.uniform(0.86, 1.08) if t else 0.0)) for x, y in pts])
    P = [[rings[t][i] for t in range(tiers + 1)] for i in range(len(pts))]
    B.grid(P, m, smooth=False, close_u=True)
    top = rings[-1]
    c = Vector((cx, cy, max(v.z for v in top) * 0.97))
    for i in range(len(top)):
        B.face([top[i], top[(i + 1) % len(top)], c], m)


def maggie_daley():
    """Maggie Daley Park (2015): the 12 m sculpted climbing wall (OSM Climbing Park), the quarter-mile skating ribbon looping
    round it (OSM centreline, ~6.5 m wide), the fieldhouse along Randolph, and the play garden's features (blue 'Sea' surface,
    the ship in the Harbor, Slide Crater's mound and slides, the Cradle Nest climbing net, swings)."""
    o = (700.0, -500.0)
    B = PlanBuilder()
    # skating ribbon (pale ice / concrete track) with a low kerb either side
    rib = P2(MD_RIBBON, o)
    B.sweep_closed(rib, [(-3.6, -0.05), (-3.6, 0.25), (-3.3, 0.25), (-3.3, 0.08), (3.3, 0.08), (3.3, 0.25), (3.6, 0.25), (3.6, -0.05)],
                   "M_Ice", smooth=False)
    # climbing wall massifs
    for k, poly in enumerate(MD_CLIMB):
        craggy(B, P2(poly, o), 4.0, 12.2 if k == 0 else 8.5, "M_ClimbGrey", seed=40 + k)
    # fieldhouse: long low pavilion with a green roof on Randolph (OSM strip x 682..766, y -400..-394.7)
    B.boxmm((682.4 - o[0], -401.0 - o[1], 0.0), (765.8 - o[0], -393.0 - o[1], 4.6), "M_Concrete")
    B.boxmm((682.0 - o[0], -401.4 - o[1], 4.6), (766.2 - o[0], -392.6 - o[1], 5.0), "M_Lawn")
    for k in range(16):
        x0 = 686.0 + k * 5.0 - o[0]
        B.face([(x0, -401.05 - o[1], 0.4), (x0 + 3.6, -401.05 - o[1], 0.4), (x0 + 3.6, -401.05 - o[1], 3.8), (x0, -401.05 - o[1], 3.8)], "M_Glass")
    # play garden: rubber surfaces (OSM playground outlines, simplified), features
    for poly_c, r, m in (((758.0, -590.0), 20.0, "M_Rubber"), ((806.0, -583.0), 16.0, "M_Lawn"), ((802.0, -641.0), 18.0, "M_Rubber"),
                         ((718.0, -632.0), 11.0, "M_Rubber"), ((739.0, -632.0), 8.0, "M_Rubber"), ((761.0, -622.0), 6.5, "M_Rubber")):
        B.slab(circle(poly_c[0] - o[0], poly_c[1] - o[1], r, 28), -0.1, 0.07, m)
    # the ship in the Harbor (a big white hull with a mast), the lighthouse-like tower
    hx, hy = 739.0 - o[0], -632.0 - o[1]
    hull = [(-6.0, 0.0), (-4.5, -2.2), (4.5, -2.2), (7.5, 0.0), (4.5, 2.2), (-4.5, 2.2)]
    B.slab([(hx + x, hy + y) for x, y in hull], 0.07, 2.6, "M_WheelWhite")
    B.cyl((hx, hy, 2.6), 7.0, 0.18, "M_Timber", 8)
    B.face([(hx + 0.2, hy, 3.4), (hx + 3.5, hy, 3.6), (hx + 3.2, hy, 8.6), (hx + 0.2, hy, 9.0)], "M_Membrane")
    B.face([(hx + 0.2, hy, 9.0), (hx + 3.2, hy, 8.6), (hx + 3.5, hy, 3.6), (hx + 0.2, hy, 3.4)], "M_Membrane")
    # Slide Crater: a grassy mound with slides down its flanks
    sx, sy = 802.0 - o[0], -641.0 - o[1]
    B.lathe([(15.0, 0.0), (11.0, 2.5), (6.0, 5.0), (3.0, 5.6), (0.0, 5.6)], "M_Lawn", 28, center=(sx, sy, 0))
    for a in (0.3, 1.9, 3.6, 5.0):
        p0 = Vector((sx + 3.0 * math.cos(a), sy + 3.0 * math.sin(a), 5.7))
        p1 = Vector((sx + 14.0 * math.cos(a), sy + 14.0 * math.sin(a), 0.6))
        B.beam(p0, p1, 1.1, 0.25, "M_Stainless")
    B.cyl((sx, sy, 5.6), 3.0, 1.6, "M_PaintYellow", 12)
    # the Cradle Nest: a climbing-net dome
    nx, ny = 718.0 - o[0], -632.0 - o[1]
    for k in range(10):
        a = math.pi * k / 10
        pts = [(nx + 8.0 * math.cos(math.pi * t / 12) * math.cos(a), ny + 8.0 * math.cos(math.pi * t / 12) * math.sin(a), 6.0 * math.sin(math.pi * t / 12))
               for t in range(-12, 13)]
        B.tube([Vector(p) for p in pts], [0.08] * len(pts), "M_Railing", 5)
    # swings frame
    wx, wy = 761.0 - o[0], -622.0 - o[1]
    for dx in (-4.0, 4.0):
        B.beam((wx + dx, wy - 1.5, 0.0), (wx + dx, wy, 3.2), 0.15, 0.15, "M_PaintYellow")
        B.beam((wx + dx, wy + 1.5, 0.0), (wx + dx, wy, 3.2), 0.15, 0.15, "M_PaintYellow")
    B.beam((wx - 4.0, wy, 3.2), (wx + 4.0, wy, 3.2), 0.15, 0.15, "M_PaintYellow")
    # the two re-erected columns of the old Federal Building (OSM 'Federal Building Columns', NE corner of the park)
    for cx in (851.2, 860.2):
        x, y = cx - o[0], -372.5 - o[1]
        B.boxmm((x - 1.1, y - 1.1, 0.0), (x + 1.1, y + 1.1, 1.2), "M_Granite")
        B.lathe([(0.65, 1.2), (0.6, 6.0), (0.52, 10.2), (0.8, 10.6), (0.8, 11.2), (0.0, 11.2)], "M_Granite", 16, center=(x, y, 0))
    zone = {"poly": [(634.0, -492.0), (758.0, -492.0), (758.0, -400.0), (634.0, -400.0)], "clear": ["props"],
            "extra": [[(680.0, -403.0), (768.0, -403.0), (768.0, -391.0), (680.0, -391.0)], [(848.0, -376.0), (864.0, -376.0), (864.0, -369.0), (848.0, -369.0)]]}
    export_site("PK_MaggieDaley", B, o, {"what": "Maggie Daley Park: climbing wall (12 m), skating ribbon, fieldhouse, play-garden features"},
                collide="complex", zone=zone)


# ================================================================== 7. Grant Park / Millennium Park / Maggie Daley path network
def _poly_index(polys, cell=40.0):
    grid, out = {}, []
    for poly in polys:
        xs = [q[0] for q in poly]; ys = [q[1] for q in poly]
        b = (min(xs), max(xs), min(ys), max(ys)); k = len(out); out.append((poly, b))
        for gx in range(int(b[0] // cell), int(b[1] // cell) + 1):
            for gy in range(int(b[2] // cell), int(b[3] // cell) + 1):
                grid.setdefault((gx, gy), []).append(k)
    def hit(x, y):
        for k in grid.get((int(x // cell), int(y // cell)), ()):
            poly, b = out[k]
            if b[0] <= x <= b[1] and b[2] <= y <= b[3] and BL_inside(poly, x, y):
                return True
        return False
    return hit


PATH_REGIONS = {      # name: (origin, y range) — the path network is split in three so no single mesh gets huge
    "PK_PathsMillennium": ((560.0, -540.0), (-760.0, -300.0)),
    "PK_PathsGrantNorth": ((600.0, -1000.0), (-1240.0, -760.0)),
    "PK_PathsGrantSouth": ((600.0, -1600.0), (-1990.0, -1240.0)),
}


def park_paths():
    """The parks' footpaths from OpenStreetMap (SourceArt/Reference/ChicagoParks/GrantPark/osm_paths.json): every footway /
    path / pedestrian way / cycleway at ground level inside the plan's Grant Park complex, as a 5 cm paved strip (3.5 m
    footways, 5 m promenades, 2.5 m paths), cut where it would lie on the plan's roads or sidewalks or inside a landmark's
    own plaza (landmark_zones.json + this kit's zones), so it never covers a street or another asset."""
    W = json.load(open(ROOT + "/SourceArt/Reference/ChicagoParks/GrantPark/osm_paths.json"))["ways"]
    plan = json.load(open(ROOT + "/Saved/Mashup/plan_v3.json"))
    parks = [pk for pk in plan["parks"] if 250 < sum(p[0] for p in pk) / len(pk) < 1100 and -2000 < sum(p[1] for p in pk) / len(pk) < -280]
    in_park = _poly_index(parks)
    rn = json.load(open(ROOT + "/Saved/Roads/roadnet.json"))
    pave = [json.loads(e["ribbon"]) if isinstance(e["ribbon"], str) else e["ribbon"] for e in rn["edges"] if e.get("ribbon")]
    pave += [j["ring"] for j in rn["junctions"]] + list(rn["joints"]) + list(rn["walk"])
    on_pave = _poly_index(pave)
    excl = [z["poly"] for z in json.load(open(ROOT + "/SourceArt/Landmarks/landmark_zones.json"))["zones"]]
    try:
        A = json.load(open(BASE + "/parks.json"))["assets"]
    except Exception:
        A = {}
    for n, rec in A.items():
        z = rec.get("zone")
        if z and not n.startswith("PK_Paths"):
            excl += [z["poly"]] + list(z.get("extra", []))
    in_excl = _poly_index(excl)
    widths = {"footway": 3.5, "pedestrian": 5.0, "path": 2.5, "cycleway": 3.0}
    builders = {n: PlanBuilder() for n in PATH_REGIONS}
    counts = {n: 0 for n in PATH_REGIONS}
    for k, w in enumerate(W):
        if w["hw"] not in widths or w.get("bridge") or w.get("area") == "yes" or (w.get("layer") not in (None, "0")):
            continue
        pts = [Vector((p[0], p[1], 0.0)) for p in w["pts"]]
        # resample every 2 m
        dense = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            n_ = max(1, int((b - a).length / 2.0))
            dense += [a.lerp(b, i / n_) for i in range(1, n_ + 1)]
        hw = widths[w["hw"]] / 2
        ok = [in_park(p.x, p.y) and not on_pave(p.x, p.y) and not in_excl(p.x, p.y) for p in dense]
        runs, cur = [], []
        for p, good in zip(dense, ok):
            if good:
                cur.append(p)
            else:
                if len(cur) > 2:
                    runs.append(cur)
                cur = []
        if len(cur) > 2:
            runs.append(cur)
        for run in runs:
            yc = sum(p.y for p in run) / len(run)
            reg = next((n for n, (o_, (y0, y1)) in PATH_REGIONS.items() if y0 <= yc < y1), None)
            if not reg:
                continue
            o_ = PATH_REGIONS[reg][0]
            zt = 0.045 + (k % 7) * 0.003
            loc = [(p.x - o_[0], p.y - o_[1]) for p in run]
            builders[reg].sweep_open(loc, [(hw, -0.08), (hw, zt), (-hw, zt), (-hw, -0.08)], "M_ParkPaver")
            counts[reg] += 1
    for n, B in builders.items():
        if counts[n]:
            export_site(n, B, PATH_REGIONS[n][0], {"what": "park footpaths from OSM, %d runs" % counts[n]}, collide="none")   # 5 cm strips: visual only, the ground collides


# ================================================================== 8. Landmark buildings that replace City Sample towers
LPT_TOWER = [(1268.5, 438.7), (1270.7, 442.0), (1272.8, 446.3), (1273.4, 451.6), (1273.3, 464.1), (1273.5, 465.9), (1274.9, 468.1),
             (1276.4, 469.7), (1279.2, 470.6), (1286.1, 470.9), (1288.3, 470.1), (1290.4, 468.8), (1291.6, 466.8), (1292.1, 464.2),
             (1292.5, 451.6), (1293.6, 446.4), (1295.7, 442.3), (1298.6, 439.0), (1302.1, 435.8), (1313.1, 429.7), (1314.6, 428.7),
             (1315.8, 426.5), (1316.5, 424.3), (1315.9, 421.5), (1312.8, 415.4), (1311.0, 413.8), (1308.8, 412.7), (1306.5, 412.7),
             (1304.0, 413.5), (1292.7, 419.3), (1288.0, 420.8), (1283.2, 421.2), (1278.1, 420.2), (1274.2, 418.6), (1263.2, 412.4),
             (1261.5, 411.7), (1259.0, 411.8), (1256.8, 412.3), (1254.6, 414.2), (1251.0, 420.0), (1250.6, 422.3), (1250.7, 424.8),
             (1251.9, 426.8), (1253.9, 428.5), (1264.7, 435.2)]
LPT_PODIUM = [(1161.9, 470.3), (1326.4, 473.7), (1327.6, 408.8), (1163.5, 404.5)]


def smooth_ring(poly, n=3):
    """Chaikin-smoothed closed outline (rounder wing ends)."""
    P = list(poly)
    for _ in range(n):
        Q = []
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]
            Q.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            Q.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        P = Q
    return P


def lake_point_tower():
    """Lake Point Tower (Schipporeit & Heinrich, 1968): 197 m, three curving wings at 120 deg (OSM building:part outline,
    smoothed), bronze-tinted glass with dark floor bands (70 storeys), the round core crown, on its 12 m podium garage with
    the rooftop park (OSM r19385699). Replaces the five City Sample towers (100-119 m) the plan put on the site."""
    o = (1283.5, 441.0)
    B = PlanBuilder()
    C = PlanBuilder()
    pod = offset_poly(P2(LPT_PODIUM, o), -1.0)
    B.slab(pod, 0.0, 12.0, "M_Lawn", "M_Concrete")
    for zb in (3.2, 7.4):
        B.sweep_closed(pod, [(0.02, zb), (0.02, zb + 2.2), (0.0, zb + 2.2), (0.0, zb)], "M_GarageOpening")
    B.sweep_closed(pod, [(0.0, 11.0), (0.25, 11.0), (0.25, 13.1), (0.0, 13.1)], "M_Concrete")
    import random
    rnd = random.Random(1968)
    for k in range(40):                                              # rooftop park trees
        x, y = rnd.uniform(1170, 1245) - o[0], rnd.uniform(410, 466) - o[1]
        tree_ball(B, x, y, rnd.uniform(5.0, 7.0), rnd.uniform(1.8, 2.6), z=12.0)
    B.slab([(1185 - o[0], 425 - o[1]), (1215 - o[0], 425 - o[1]), (1215 - o[0], 445 - o[1]), (1185 - o[0], 445 - o[1])], 12.0, 12.15, "M_Water")
    T = smooth_ring(P2(LPT_TOWER, o), 1)
    H = 191.0
    B.slab(T, 12.0, H, "M_RoofFlat", "M_TintedGlass")
    nf = 33                                                          # a dark band every second floor
    for k in range(nf + 1):
        z = 13.0 + (H - 13.0) * k / nf
        B.sweep_closed(T, [(0.0, z - 0.45), (0.08, z - 0.45), (0.08, z + 0.45), (0.0, z + 0.45)], "M_TowerBlack")
    for i in range(0, len(T), 3):                                   # mullions
        x, y = T[i]
        B.boxmm((x - 0.09, y - 0.09, 12.0), (x + 0.09, y + 0.09, H), "M_TowerBlack")
    B.sweep_closed(T, [(0.0, H - 2.0), (0.2, H - 2.0), (0.2, H + 1.2), (0.0, H + 1.2)], "M_TowerBlack")
    B.cyl((1283.5 - o[0], 435.8 - o[1], H), 6.5, 12.6, "M_TowerBlack", 28)
    C.slab(offset_poly(T, 0.1), 0.0, H + 1.2, "M_Concrete")
    C.slab(pod, 0.0, 12.0, "M_Concrete")
    rects = bv3_rects([(1200.4, 456.5), (1269.7, 425.3), (1225.9, 451.5), (1255.0, 455.8), (1231.2, 420.7)])
    zone = {"poly": [(1161.0, 403.5), (1328.5, 403.5), (1328.5, 474.5), (1161.0, 474.5)], "clear": ["props", "buildings"], "buildings": rects}
    export_site("PK_LakePointTower", B, o, {"what": "Lake Point Tower: 3-wing curved glass tower 197 m on its 12 m podium with the rooftop park",
                                            "removes": "five City Sample towers on the podium"}, collide="none", zone=zone)
    export_site("PK_LakePointTower_Col", C, o, {"what": "invisible collider for PK_LakePointTower"}, collide="hidden")


CCC = [(255.3, -374.5), (257.2, -462.2), (239.3, -462.3), (239.2, -460.7), (228.8, -460.7), (228.9, -462.4), (210.9, -462.8),
       (210.4, -427.9), (212.4, -427.8), (211.9, -388.3), (209.9, -388.3), (209.3, -354.1), (225.3, -354.0), (225.2, -351.4),
       (239.9, -351.1), (240.1, -353.4), (255.6, -353.5)]


def cultural_center():
    """Chicago Cultural Center (Shepley, Rutan & Coolidge, 1897; the old public library) facing Millennium Park across
    Michigan Avenue: a 5-storey limestone block (OSM footprint) with raised basement, round-arched second floor, a
    two-storey colonnade, deep cornice and attic, the columned Washington Street loggia and the Randolph Street portico.
    Replaces the three City Sample towers (136-144 m) the plan put on the block."""
    o = (233.0, -407.0)
    B = PlanBuilder()
    pts = ccw(offset_poly(P2(CCC, o), -0.5))
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        W = math.hypot(b[0] - a[0], b[1] - a[1])
        if W < 4.0:
            B.wall(Vector((a[0], a[1], 0)), Vector((b[0] - a[0], b[1] - a[1], 0)).normalized(), Vector((0, 0, 1)), W, 30.0, 0.9, "M_Limestone")
            continue
        n = max(1, int(round(W / 5.2)))
        facade(B, a, b, 0.0, 6.0, n, kind="window")
        facade(B, a, b, 6.0, 13.0, n, kind="arch")
        facade(B, a, b, 13.0, 25.0, n, kind="window")
        facade(B, a, b, 25.0, 30.0, n, kind="blind")
        # engaged columns of the colonnade
        d = Vector((b[0] - a[0], b[1] - a[1], 0)).normalized()
        nrm = Vector((d.y, -d.x, 0))
        for k in range(n + 1):
            c = Vector((a[0], a[1], 0)) + d * (W * k / n) + nrm * 0.45
            B.lathe([(0.55, 13.3), (0.5, 20.0), (0.45, 24.3), (0.65, 24.6), (0.0, 24.6)], "M_Limestone", 10, center=(c.x, c.y, 0))
    for prof in ([(0.0, 5.8), (0.3, 6.0), (0.3, 6.3), (0.0, 6.5)], [(0.0, 12.8), (0.35, 13.0), (0.35, 13.3), (0.0, 13.5)],
                 [(0.0, 24.6), (0.6, 24.9), (1.4, 26.6), (1.4, 27.2), (0.0, 27.4)], [(0.0, 29.6), (0.4, 29.8), (0.4, 30.4), (0.0, 30.6)]):
        B.sweep_closed(pts, prof, "M_Limestone")
    B.face([(x, y, 30.0) for x, y in pts], "M_RoofFlat")
    # the two interior glass domes show as skylight lanterns on the roof
    for (dx, dy, r) in ((233.0, -440.0, 8.0), (233.0, -372.0, 6.5)):
        B.lathe([(r, 30.0), (r, 31.5), (r * 0.7, 33.5), (0.0, 34.6)], "M_Glass", 20, center=(dx - o[0], dy - o[1], 0))
    # Randolph portico (north) and the Washington loggia (south): projecting columned porches
    for (y0, sgn) in ((-353.0, 1), (-463.0, -1)):
        yb = y0 - o[1]
        for k in range(6):
            x = 218.0 + k * 6.0 - o[0]
            B.lathe([(0.6, 0.0), (0.55, 8.0), (0.5, 12.5), (0.7, 12.8), (0.0, 12.8)], "M_Limestone", 12, center=(x, yb + sgn * 2.2, 0))
        B.boxmm((216.0 - o[0], min(yb, yb + sgn * 3.4), 12.8), (250.0 - o[0], max(yb, yb + sgn * 3.4), 14.6), "M_Limestone")
    rects = bv3_rects([(222.3, -441.2), (230.7, -384.8), (251.6, -446.0)])
    zone = {"poly": [(208.5, -463.5), (258.0, -463.5), (258.0, -350.5), (208.5, -350.5)], "clear": ["props", "buildings"], "buildings": rects}
    export_site("PK_CulturalCenter", B, o, {"what": "Chicago Cultural Center: 5-storey limestone block, arches, colonnade, cornice, porticos",
                                            "removes": "three City Sample towers on the block"}, collide="complex", zone=zone)


# ================================================================== 9. The Metra cut through Grant Park
GP_STRIP_BUILDINGS = [(417.2, -764.0), (412.4, -791.0), (418.8, -838.9), (417.6, -877.7), (427.1, -944.0), (421.6, -986.4), (432.3, -1055.5),
                      (429.8, -1106.5), (426.7, -1159.2), (432.0, -1188.7), (432.7, -1226.4), (426.9, -1260.6), (440.1, -1352.8),
                      (430.3, -1393.7), (444.5, -1506.6), (445.1, -1532.2), (447.7, -1629.6), (447.1, -1651.7), (449.4, -1693.5),
                      (448.6, -1720.9), (413.3, -1853.9), (418.6, -1888.0)]


def grant_park_rail():
    """The Metra Electric / South Shore tracks along the west side of Grant Park (plan rail lines, x ~385-470) from Monroe to
    the map's south edge, kept at grade as the plan has one ground level: ballast beds, rails, the overhead catenary on
    poles every ~60 m, fences either side. Cut wherever a plan street or sidewalk crosses (the real streets bridge the cut).
    The plan had 22 City Sample towers (24-130 m) standing on this strip inside Grant Park; this asset's zone removes them."""
    o = (430.0, -1300.0)
    plan = json.load(open(ROOT + "/Saved/Mashup/plan_v3.json"))
    rn = json.load(open(ROOT + "/Saved/Roads/roadnet.json"))
    pave = [json.loads(e["ribbon"]) if isinstance(e["ribbon"], str) else e["ribbon"] for e in rn["edges"] if e.get("ribbon")]
    pave += [j["ring"] for j in rn["junctions"]] + list(rn["joints"]) + list(rn["walk"])
    on_pave = _poly_index(pave)
    lines = []
    for r in plan["rail"]:
        if r.get("city") != "chicago" or r.get("kind") == "L":
            continue
        xs = [q[0] for q in r["pts"]]; ys = [q[1] for q in r["pts"]]
        if min(xs) > 375 and max(xs) < 480 and max(ys) <= -750 and min(ys) >= -1975:
            lines.append(r["pts"])
    B = PlanBuilder()
    nseg = 0
    pole_acc = {}
    for li, pts in enumerate(lines):
        P = [Vector((x, y, 0)) for x, y in pts]
        dense = [P[0]]
        for a, b in zip(P, P[1:]):
            n_ = max(1, int((b - a).length / 4.0))
            dense += [a.lerp(b, i / n_) for i in range(1, n_ + 1)]
        good = [not on_pave(p.x, p.y) and not on_pave(p.x + 2.5, p.y) and not on_pave(p.x - 2.5, p.y) for p in dense]
        run = []
        for p, g in list(zip(dense, good)) + [(None, False)]:
            if g:
                run.append(p)
                continue
            if len(run) >= 3:
                loc = [(q.x - o[0], q.y - o[1]) for q in run]
                B.sweep_open(loc, [(2.4, -0.05), (1.9, 0.32), (-1.9, 0.32), (-2.4, -0.05)], "M_Gravel")
                B.sweep_open(loc, [(1.3, 0.33), (1.3, 0.34), (-1.3, 0.34), (-1.3, 0.33)], "M_Timber")
                for off in (0.72, -0.72):
                    B.sweep_open(loc, [(off + 0.04, 0.34), (off + 0.04, 0.5), (off - 0.04, 0.5), (off - 0.04, 0.34)], "M_Steel")
                B.sweep_open(loc, [(0.03, 6.3), (0.03, 6.36), (-0.03, 6.36), (-0.03, 6.3)], "M_Railing")      # contact wire
                # catenary poles every ~60 m (one side per track, alternating), with the arm over the track
                acc = 0.0
                for a, b in zip(run, run[1:]):
                    acc += (b - a).length
                    if acc >= 60.0:
                        acc = 0.0
                        t = (b - a).normalized()
                        nl = Vector((-t.y, t.x, 0)) * (1 if li % 2 else -1)
                        base = Vector((b.x - o[0], b.y - o[1], 0)) + nl * 3.0
                        B.boxmm((base.x - 0.15, base.y - 0.15, 0.0), (base.x + 0.15, base.y + 0.15, 7.4), "M_Steel")
                        top = Vector((b.x - o[0], b.y - o[1], 7.0))
                        B.beam(base + Vector((0, 0, 7.0)), top - nl * 0.2, 0.12, 0.12, "M_Steel")
                        B.rod(top + Vector((0, 0, -0.1)), top + Vector((0, 0, -0.66)), 0.02, "M_Railing", 4)
                nseg += 1
            run = []
    # fences along the outer tracks (west at x ~ 380-388, east at x ~ 445-470) as simple chain-link panels
    for li, pts in enumerate(lines):
        pass
    # the Metra Jackson substation (OSM, 3 storeys of brick) and the Hector Guimard Paris Metro entrance at Van Buren
    sub = [(421.0, -1003.4), (435.1, -1003.4), (435.1, -964.7), (421.0, -964.7)]
    B.slab(P2(sub, o), 0.0, 12.0, "M_RoofFlat", "M_Brick")
    zone = {"poly": [(383.0, -1975.0), (475.0, -1975.0), (475.0, -1006.0), (383.0, -1006.0)], "clear": ["buildings"],      # not props: streets cross
            "buildings": bv3_rects(GP_STRIP_BUILDINGS)}
    export_site("PK_GrantParkRail", B, o, {"what": "Metra Electric / South Shore tracks through Grant Park at grade: ballast, rails, catenary; %d runs" % nseg,
                                           "removes": "22 City Sample towers that stood on the rail strip inside Grant Park"},
                collide="complex", zone=zone)


BOT_BASE = [(-363.5, -1087.6), (-364.0, -1051.8), (-345.5, -1051.5), (-344.7, -1097.7), (-344.9, -1108.2), (-338.8, -1108.3), (-338.7, -1161.9),
            (-342.2, -1162.0), (-342.1, -1165.8), (-349.2, -1165.9), (-349.1, -1171.3), (-389.9, -1172.0), (-390.0, -1168.5), (-398.0, -1168.6),
            (-398.1, -1163.4), (-401.7, -1163.5), (-402.3, -1109.3), (-397.3, -1109.2), (-398.0, -1052.3), (-379.8, -1051.9), (-378.9, -1087.9),
            (-391.3, -1088.1), (-390.9, -1106.8), (-350.7, -1106.0), (-351.0, -1087.3)]
BOT_LOBBY = [(-378.9, -1087.9), (-379.8, -1051.9), (-364.0, -1051.8), (-363.5, -1087.6)]
BOT_TOWER = [(-378.9, -1087.9), (-391.3, -1088.1), (-390.9, -1106.8), (-350.7, -1106.0), (-351.0, -1087.3), (-363.5, -1087.6)]
BOT_TOP = [(-387.7, -1092.5), (-386.6, -1091.3), (-354.9, -1090.6), (-353.6, -1092.0), (-353.2, -1102.1), (-354.7, -1103.5), (-386.5, -1103.7),
           (-387.7, -1102.7)]
BOT_ANNEX = [(-390.0, -1168.5), (-390.8, -1119.8), (-350.0, -1119.1), (-349.2, -1165.9), (-349.1, -1171.3), (-389.9, -1172.0)]
BOT_EAST = [(-258.0, -1096.3), (-323.4, -1096.9), (-344.7, -1097.7), (-344.9, -1108.2), (-338.8, -1108.3), (-338.7, -1161.9), (-322.5, -1161.6),
            (-322.3, -1171.2), (-257.9, -1170.0)]
TRANSUNION = [(-258.1, -1091.7), (-323.5, -1092.5), (-323.9, -1056.9), (-323.5, -1055.9), (-259.0, -1054.9), (-258.1, -1089.6)]


def deco_walls(B, poly, z0, z1, pier=2.6, m="M_Limestone", glass="M_GlassDark", depth=0.35):
    """Art Deco walls: a recessed dark window plane with continuous limestone piers every `pier` m and solid corners."""
    pts = ccw(poly)
    B.slab(pts, z0, z1, "M_RoofFlat", glass)
    for i in range(len(pts)):
        a, b = Vector((*pts[i], 0)), Vector((*pts[(i + 1) % len(pts)], 0))
        L = (b - a).length
        if L < 0.5:
            continue
        t = (b - a) / L
        n_ = Vector((t.y, -t.x, 0))
        k = max(1, int(round(L / pier)))
        for j in range(k + 1):
            c = a + t * (L * j / k) + n_ * (depth / 2)
            w = 1.6 if j in (0, k) else 0.7
            B.beam((c.x, c.y, z0), (c.x, c.y, z1), w, depth, m, up=(n_.x, n_.y, 0))
    B.sweep_closed(pts, [(0.0, z1 - 1.2), (0.45, z1 - 1.0), (0.45, z1 + 0.6), (0.0, z1 + 0.8)], m)


def board_of_trade():
    """Chicago Board of Trade Building (Holabird & Root, 1930) closing the LaSalle Street canyon, from the OSM building parts:
    the 21-storey wings round the 4-storey Jackson Boulevard lobby, the tower (44 storeys) with its 45th-storey top and the
    hipped pyramid roof to 184 m, the stylised aluminium Ceres (9.4 m) on top; the 1980 annex with its own hipped roof, the
    7-storey east block and the TransUnion building (24 storeys) complete the block. Replaces the seven City Sample towers
    (157-204 m) the plan put here."""
    o = (-370.5, -1097.9)
    B = PlanBuilder()
    st = 4.1
    deco_walls(B, P2(BOT_BASE, o), 0.0, 21 * st)
    deco_walls(B, P2(BOT_LOBBY, o), 0.0, 4 * st)
    deco_walls(B, P2(BOT_TOWER, o), 0.0, 44 * st, pier=2.2)
    deco_walls(B, P2(BOT_TOP, o), 44 * st, 45 * st, pier=2.2)
    top = P2(BOT_TOP, o)
    xs = [p[0] for p in top]; ys = [p[1] for p in top]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    hx, hy = (max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2
    B.pyramid((cx, cy, 45 * st + 0.8), hx, hy, 184.0 - (45 * st + 0.8), "M_Roof")
    # Ceres: robed figure holding a sheaf and a sack (stylised), on a small plinth at the apex
    zc = 184.0 - 1.0
    B.lathe([(0.9, zc), (0.8, zc + 3.0), (0.55, zc + 6.5), (0.35, zc + 7.8), (0.0, zc + 8.0)], "M_Steel", 12, center=(cx, cy, 0))
    B.ellipsoid((cx, cy, zc + 8.5), (0.38, 0.38, 0.5), "M_Steel", 10, 6)
    limb(B, [(cx + 0.4, cy, zc + 6.2), (cx + 1.0, cy, zc + 5.0), (cx + 1.1, cy, zc + 7.2)], [0.16, 0.13, 0.22], "M_Steel", 8)
    # annex with its hipped roof, east block, TransUnion
    deco_walls(B, P2(BOT_ANNEX, o), 21 * st - 0.01, 23 * st, pier=3.0, m="M_Concrete", glass="M_Glass")
    an = P2(BOT_ANNEX, o)
    xs = [p[0] for p in an]; ys = [p[1] for p in an]
    B.pyramid(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 23 * st + 0.8), (max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2, 14.0, "M_Glass")
    deco_walls(B, P2(BOT_EAST, o), 0.0, 7 * st, pier=4.0, m="M_Concrete")
    tu = P2(TRANSUNION, o)
    B.slab(tu, 0.0, 102.0, "M_RoofFlat", "M_Glass")
    for k in range(1, 25):
        B.sweep_closed(tu, [(0.0, k * 4.2 - 0.5), (0.06, k * 4.2 - 0.5), (0.06, k * 4.2 + 0.5), (0.0, k * 4.2 + 0.5)], "M_Concrete")
    rects = bv3_rects([(-324.5, -1087.5), (-366.1, -1160.1), (-322.0, -1128.5), (-362.8, -1077.1), (-381.8, -1105.6), (-338.5, -1154.0), (-348.6, -1129.0)])
    zone = {"poly": [(-403.0, -1173.0), (-257.0, -1173.0), (-257.0, -1050.5), (-403.0, -1050.5)], "clear": ["props", "buildings"], "buildings": rects}
    export_site("PK_BoardOfTrade", B, o, {"what": "Chicago Board of Trade Building (184 m + Ceres), annex, east block, TransUnion building",
                                          "removes": "seven City Sample towers on the block"}, collide="complex", zone=zone)


def notched_square(cx, cy, half, notch):
    """Square with its four corners notched in (Aon Center / Two Prudential plan)."""
    h, n = half, notch
    return [(cx - h + n, cy - h), (cx + h - n, cy - h), (cx + h - n, cy - h + n), (cx + h, cy - h + n), (cx + h, cy + h - n), (cx + h - n, cy + h - n),
            (cx + h - n, cy + h), (cx - h + n, cy + h), (cx - h + n, cy + h - n), (cx - h, cy + h - n), (cx - h, cy - h + n), (cx - h + n, cy - h + n)]


def chevron_piers(B, poly, z0, z1, step, depth, w, m):
    """Triangular (chevron) piers standing proud of each wall every `step` m (the Aon Center's white fins)."""
    pts = ccw(poly)
    for i in range(len(pts)):
        a, b = Vector((*pts[i], 0)), Vector((*pts[(i + 1) % len(pts)], 0))
        L = (b - a).length
        if L < step:
            continue
        t = (b - a) / L
        n_ = Vector((t.y, -t.x, 0))
        k = int(L / step)
        for j in range(k + 1):
            c = a + t * (L * j / k)
            B.prism(Vector((c.x, c.y, z0)), t, Vector((0, 0, 1)), [(-w / 2, 0.0), (w / 2, 0.0), (0.0, 0.001)], 0.001, m) if False else None
            p0, p1, p2 = c - t * (w / 2), c + t * (w / 2), c + n_ * depth
            for (q0, q1) in ((p0, p2), (p2, p1)):
                B.face([(q0.x, q0.y, z0), (q1.x, q1.y, z0), (q1.x, q1.y, z1), (q0.x, q0.y, z1)], m)


def aon_center():
    """Aon Center (Edward Durell Stone, 1973): a 57 m square white shaft (notched corners), 83 storeys, 346 m (OSM), clad
    in close-set chevron piers with dark glass between; the plan's City Sample buildings there were 41-59 m."""
    o = (518.2, -251.9)
    B = PlanBuilder()
    C = PlanBuilder()
    sq = notched_square(0.0, 0.0, 28.5, 2.2)
    B.slab(sq, 0.0, 340.0, "M_RoofFlat", "M_GlassDark")
    chevron_piers(B, sq, 0.0, 340.0, 1.55, 0.75, 1.05, "M_Marble")
    B.sweep_closed(sq, [(0.0, 337.0), (0.8, 337.0), (0.8, 341.0), (0.0, 341.0)], "M_Marble")
    B.slab(notched_square(-4.5, 0.0, 15.8, 1.5), 340.0, 346.0, "M_RoofFlat", "M_Marble")
    B.slab(notched_square(0.0, 0.0, 40.0, 3.0), -0.1, 0.4, "M_Granite")                  # plaza
    C.slab(offset_poly(sq, 0.8), 0.0, 341.0, "M_Concrete")
    rects = bv3_rects([(510.5, -236.6), (516.7, -274.4)])
    zone = {"poly": [(478.0, -292.0), (558.0, -292.0), (558.0, -212.0), (478.0, -212.0)], "clear": ["props", "buildings"], "buildings": rects}
    export_site("PK_AonCenter", B, o, {"what": "Aon Center: 346 m white shaft with chevron piers", "removes": "two City Sample buildings (41, 59 m)"},
                collide="none", zone=zone)
    export_site("PK_AonCenter_Col", C, o, {"what": "invisible collider for PK_AonCenter"}, collide="hidden")


def two_prudential():
    """Two Prudential Plaza (Loebl Schlossman & Hackl, 1990): a 40 m square granite shaft with notched corners, 64 storeys,
    the stepped chevron-gabled crown and the spire to 303 m (OSM); the plan had a 39 m City Sample building there."""
    o = (421.0, -243.0)
    B = PlanBuilder()
    C = PlanBuilder()
    B.slab(P2([(400.2, -264.9), (441.9, -264.0), (440.8, -208.8), (400.2, -209.1)], o), 0.0, 12.0, "M_RoofFlat", "M_Granite")
    z = 12.0
    for half, notch, h in ((20.0, 3.2, 228.0), (17.5, 3.0, 12.0), (15.0, 2.6, 10.0), (12.5, 2.2, 8.0)):
        sq = notched_square(0.0, 0.0, half, notch)
        B.slab(sq, z, z + h, "M_RoofFlat", "M_GlassDark")
        chevron_piers(B, sq, z, z + h, 2.4, 0.4, 1.0, "M_Granite")
        B.sweep_closed(sq, [(0.0, z + h - 1.2), (0.5, z + h - 1.2), (0.5, z + h + 0.4), (0.0, z + h + 0.4)], "M_Granite")
        if half == 20.0:
            C.slab(offset_poly(sq, 0.5), 0.0, z + h, "M_Concrete")
        z += h
    # chevron gables on each face of the crown and the pyramid + spire
    for k in range(4):
        R = Matrix.Rotation(math.pi / 2 * k, 3, "Z")
        a, b, c = R @ Vector((-12.5, -12.6, z)), R @ Vector((12.5, -12.6, z)), R @ Vector((0.0, -12.6, z + 9.0))
        B.face([a, b, c], "M_Granite")
    B.pyramid((0.0, 0.0, z), 12.5, 12.5, 14.0, "M_Granite")
    B.lathe([(0.9, z + 14.0), (0.5, z + 25.0), (0.2, 300.0), (0.0, 303.0)], "M_Steel", 8)
    rects = bv3_rects([(431.0, -231.5)])
    zone = {"poly": [(399.0, -266.0), (443.0, -266.0), (443.0, -207.5), (399.0, -207.5)], "clear": ["props", "buildings"], "buildings": rects}
    export_site("PK_TwoPrudential", B, o, {"what": "Two Prudential Plaza: 40 m square shaft, chevron crown, spire to 303 m", "removes": "a 39 m City Sample building"},
                collide="none", zone=zone)
    export_site("PK_TwoPrudential_Col", C, o, {"what": "invisible collider for PK_TwoPrudential"}, collide="hidden")


HWL = [(-63.9, -1297.0), (-65.7, -1189.4), (-3.8, -1188.5), (-3.2, -1296.0)]


def harold_washington_library():
    """Harold Washington Library Center (Hammond Beeby & Babka, 1991): ten storeys of red brick over a rusticated granite base,
    five-storey round-arched windows, a heavy cornice, and the glass-and-steel roof with big pediments and the green
    acroterion ornaments ('owls') at the corners; OSM footprint at State and Van Buren. Replaces five City Sample towers."""
    o = (-34.4, -1242.7)
    B = PlanBuilder()
    pts = ccw(P2(HWL, o))
    B.slab(pts, 0.0, 5.0, "M_RoofFlat", "M_Granite")
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        W = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(3, int(round(W / 9.0)))
        facade(B, a, b, 5.0, 33.0, n, m="M_Brick", kind="arch", thick=1.6, aw=5.5)
        facade(B, a, b, 33.0, 40.0, n, m="M_Brick", kind="blind", thick=1.0)
    B.sweep_closed(pts, [(0.0, 39.5), (1.0, 40.0), (2.6, 42.0), (2.6, 43.0), (0.0, 43.2)], "M_Verdigris")
    B.face([(x, y, 43.0) for x, y in pts], "M_RoofFlat")
    # glass roof: a hipped glass mansard with the pediments on the long faces
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    cx, cy = sum(xs) / 4, sum(ys) / 4
    hx, hy = (max(xs) - min(xs)) / 2 - 2.0, (max(ys) - min(ys)) / 2 - 2.0
    B.pyramid((cx, cy, 43.0), hx, hy, 9.0, "M_Glass")
    for side in (-1, 1):
        for k in range(3):
            y0 = cy - hy + (k + 0.5) * (2 * hy / 3)
            a = (cx + side * hx, y0 - 9.0, 43.0)
            b = (cx + side * hx, y0 + 9.0, 43.0)
            c = (cx + side * hx, y0, 54.0)
            B.face([a, b, c] if side > 0 else [b, a, c], "M_Verdigris")
            B.face([b, a, c] if side > 0 else [a, b, c], "M_Verdigris")
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = cx + sx * (hx + 1.0), cy + sy * (hy + 1.0)
            B.lathe([(1.6, 43.0), (1.2, 46.0), (2.0, 48.5), (0.8, 51.5), (0.0, 52.5)], "M_Verdigris", 8, center=(x, y, 0))
    rects = bv3_rects([(-13.4, -1279.3), (-7.5, -1245.3), (-49.7, -1223.7), (-19.6, -1212.0), (-41.8, -1272.1)])
    zone = {"poly": [(-67.0, -1298.0), (-2.0, -1298.0), (-2.0, -1187.5), (-67.0, -1187.5)], "clear": ["props", "buildings"], "buildings": rects}
    export_site("PK_HaroldWashingtonLibrary", B, o, {"what": "Harold Washington Library: red brick, great arches, glass roof, green ornaments",
                                                     "removes": "five City Sample towers on the block"}, collide="complex", zone=zone)


AUD = [(161.0, -1293.5), (268.0, -1293.5), (268.0, -1246.3), (262.4, -1246.5), (262.4, -1241.5), (217.5, -1242.9), (217.7, -1251.3), (159.8, -1252.5)]


def auditorium_building():
    """The Auditorium Building (Adler & Sullivan, 1889; Roosevelt University), facing Congress Plaza across Michigan Avenue:
    ten storeys of rough-faced granite and limestone with arcaded window bays, and the 17-storey tower on the Congress side
    (OSM footprint, pulled in off the plan's sidewalks). Replaces three City Sample towers."""
    o = (214.0, -1268.0)
    B = PlanBuilder()
    pts = ccw(P2(AUD, o))
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        W = math.hypot(b[0] - a[0], b[1] - a[1])
        if W < 4.0:
            B.wall(Vector((a[0], a[1], 0)), Vector((b[0] - a[0], b[1] - a[1], 0)).normalized(), Vector((0, 0, 1)), W, 44.0, 1.0, "M_Granite")
            continue
        n = max(1, int(round(W / 6.0)))
        facade(B, a, b, 0.0, 12.0, n, m="M_Granite", kind="basement", thick=1.2)
        facade(B, a, b, 12.0, 32.0, n, m="M_Limestone", kind="arch", thick=1.0)
        facade(B, a, b, 32.0, 44.0, n * 2, m="M_Limestone", kind="arch", thick=0.9)
    B.sweep_closed(pts, [(0.0, 43.4), (0.8, 43.8), (0.8, 44.6), (0.0, 44.8)], "M_Limestone")
    B.face([(x, y, 44.0) for x, y in pts], "M_RoofFlat")
    tw = [(190.0 - o[0], -1293.4 - o[1]), (213.0 - o[0], -1293.4 - o[1]), (213.0 - o[0], -1276.0 - o[1]), (190.0 - o[0], -1276.0 - o[1])]
    for i in range(4):
        a, b = ccw(tw)[i], ccw(tw)[(i + 1) % 4]
        facade(B, a, b, 44.0, 70.0, 4, m="M_Limestone", kind="window", thick=0.8)
    B.sweep_closed(ccw(tw), [(0.0, 69.0), (1.0, 69.5), (1.0, 71.0), (0.0, 71.2)], "M_Limestone")
    B.face([(x, y, 71.0) for x, y in ccw(tw)], "M_RoofFlat")
    rects = bv3_rects([(190.1, -1253.8), (251.7, -1259.5), (197.8, -1282.0)])
    zone = {"poly": [(159.0, -1294.5), (269.0, -1294.5), (269.0, -1240.5), (159.0, -1240.5)], "clear": ["props", "buildings"], "buildings": rects}
    export_site("PK_AuditoriumBuilding", B, o, {"what": "Auditorium Building (Sullivan): 10 storeys, arcades, 17-storey tower",
                                                "removes": "three City Sample towers on the block"}, collide="complex", zone=zone)


def frustum_stack(B, cx, cy, hx, hy, z0, z1, n, flare, m_glass, m_band):
    """A stack of n glass frustums alternately flaring out and tucking in (St. Regis Chicago), on a rectangle hx x hy."""
    for k in range(n):
        za, zb = z0 + (z1 - z0) * k / n, z0 + (z1 - z0) * (k + 1) / n
        fa, fb = (1.0, 1.0 + flare) if k % 2 == 0 else (1.0 + flare, 1.0)
        rect = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        B.sweep(rect, m_glass, [(hx * fa, hy * fa, za, cx, cy), (hx * fb, hy * fb, zb, cx, cy)], smooth=False)
        B.sweep(rect, m_band, [(hx * fb + 0.12, hy * fb + 0.12, zb - 0.5, cx, cy), (hx * fb + 0.12, hy * fb + 0.12, zb + 0.5, cx, cy)], smooth=False)
    B.face([(cx - hx, cy - hy, z1), (cx + hx, cy - hy, z1), (cx + hx, cy + hy, z1), (cx - hx, cy + hy, z1)], "M_RoofFlat")


def st_regis():
    """Vista Tower / St. Regis Chicago (Studio Gang, 2020): three interlocking towers of stacked glass frustums, 349 / 259 / 179 m (OSM
    parts) with an 11-storey east block, blue-green glass; replaces three City Sample towers (93-112 m)."""
    o = (873.6, -35.6)
    B = PlanBuilder()
    C = PlanBuilder()
    for (x0, x1, y0, y1, h, n) in ((820.6, 847.3, -45.8, -17.8, 349.0, 10), (847.0, 874.0, -48.6, -21.3, 259.0, 8), (873.6, 900.4, -52.5, -24.6, 179.0, 6)):
        cx, cy = (x0 + x1) / 2 - o[0], (y0 + y1) / 2 - o[1]
        hx, hy = (x1 - x0) / 2 * 0.94, (y1 - y0) / 2 * 0.94
        frustum_stack(B, cx, cy, hx, hy, 0.0, h, n, 0.06, "M_GlassTeal", "M_Stainless")
        C.boxmm((cx - hx * 1.07, cy - hy * 1.07, 0.0), (cx + hx * 1.07, cy + hy * 1.07, h), "M_Concrete")
    B.boxmm((899.9 - o[0], -59.2 - o[1], 0.0), (926.6 - o[0], -26.3 - o[1], 59.0), "M_GlassTeal")
    C.boxmm((899.9 - o[0], -59.2 - o[1], 0.0), (926.6 - o[0], -26.3 - o[1], 59.0), "M_Concrete")
    rects = bv3_rects([(893.4, -34.9), (837.1, -23.9), (935.7, -41.3)])
    zone = {"poly": [(819.0, -61.0), (928.5, -61.0), (928.5, -10.5), (819.0, -10.5)], "clear": ["props", "buildings"], "buildings": rects}
    export_site("PK_VistaTower", B, o, {"what": "St. Regis Chicago: three stacked-frustum glass towers 349/259/179 m",
                                     "removes": "three City Sample towers"}, collide="none", zone=zone)
    export_site("PK_VistaTower_Col", C, o, {"what": "invisible collider for PK_VistaTower"}, collide="hidden")


CARBIDE = [(212.3, -93.8), (250.0, -93.3), (250.2, -116.6), (212.7, -117.1)]


def carbide_carbon():
    """Carbide & Carbon Building (Burnham Brothers, 1929): black polished granite base, dark green terra cotta shaft with
    gold-leaf trim, setback tower and the gold crown to ~153 m (OSM footprint, pulled 1 m in off the sidewalk); replaces a
    103 m City Sample tower."""
    o = (231.3, -105.3)
    B = PlanBuilder()
    base = P2(CARBIDE, o)
    B.slab(base, 0.0, 8.0, "M_RoofFlat", "M_GraniteBlack")
    deco_walls(B, base, 8.0, 92.0, pier=2.2, m="M_MosaicGreen", glass="M_GlassDark", depth=0.3)
    tw = [(-12.0, -8.0), (12.0, -8.0), (12.0, 8.0), (-12.0, 8.0)]
    deco_walls(B, tw, 92.0, 128.0, pier=2.0, m="M_MosaicGreen", glass="M_GlassDark", depth=0.3)
    for z, w in ((92.0, 0.6), (128.0, 0.8)):
        B.sweep_closed(ccw(base if z < 100 else tw), [(0.0, z - 0.6), (0.5, z - 0.6), (0.5, z + 0.5), (0.0, z + 0.5)], "M_GoldLeaf")
    B.slab([(-8.0, -5.0), (8.0, -5.0), (8.0, 5.0), (-8.0, 5.0)], 128.0, 136.0, "M_GoldLeaf", "M_MosaicGreen")
    B.slab([(-5.0, -3.2), (5.0, -3.2), (5.0, 3.2), (-5.0, 3.2)], 136.0, 142.0, "M_GoldLeaf", "M_GoldLeaf")
    B.pyramid((0.0, 0.0, 142.0), 3.5, 2.4, 6.0, "M_GoldLeaf")
    B.lathe([(0.35, 148.0), (0.15, 152.0), (0.0, 153.0)], "M_GoldLeaf", 8)
    rects = bv3_rects([(239.0, -103.8)])
    zone = {"poly": [(211.5, -118.0), (251.0, -118.0), (251.0, -92.5), (211.5, -92.5)], "clear": ["props", "buildings"], "buildings": rects}
    export_site("PK_CarbideCarbon", B, o, {"what": "Carbide & Carbon Building: black granite, green terra cotta, gold crown ~153 m",
                                           "removes": "a 103 m City Sample tower"}, collide="complex", zone=zone)


# ================================================================== 10. Smaller parks and monuments
OLIVE_POOLS = [((1401.5, 680.7), 21.9), ((1486.9, 722.4), 17.3), ((1407.4, 747.9), 11.5), ((1502.5, 835.9), 11.3), ((1480.8, 882.3), 17.3)]


def olive_park():
    """Milton Lee Olive Park (by the Jardine water plant, north of Navy Pier): coping rings and the central fountain jets of
    its five round pools (OSM 'Pool 1-5'; the plan already has their water), the radiating walks between them, and the
    PFC Milton Lee Olive III memorial stone (OSM (1478.8, 788.0))."""
    o = (1450.0, 780.0)
    B = PlanBuilder()
    J = PlanBuilder()
    pts = []
    for (cx, cy), r in OLIVE_POOLS:
        x, y = cx - o[0], cy - o[1]
        B.lathe([(r + 3.2, -0.05), (r + 3.2, 0.06), (r + 0.4, 0.06), (r + 0.4, 0.45), (r, 0.45), (r, -0.3)], "M_Concrete", 48, center=(x, y, 0))
        B.lathe([(1.2, -0.3), (1.2, 0.5), (0.0, 0.5)], "M_Concrete", 12, center=(x, y, 0))
        J.lathe([(0.25, 0.5), (0.6, 2.5), (0.4, 5.5), (0.0, 7.5)], "M_WaterJet", 10, center=(x, y, 0))
        pts.append((x, y, r))
    # walks: ring to ring (OSM pattern) and the two long diagonals
    links = [(0, 2), (2, 1), (0, 1), (1, 3), (3, 4), (2, 3)]
    for a, b in links:
        (xa, ya, ra), (xb, yb, rb) = pts[a], pts[b]
        d = Vector((xb - xa, yb - ya, 0))
        L = d.length
        t = d / L
        p0 = (xa + t.x * (ra + 3.0), ya + t.y * (ra + 3.0))
        p1 = (xb - t.x * (rb + 3.0), yb - t.y * (rb + 3.0))
        B.sweep_open([p0, p1], [(1.8, -0.05), (1.8, 0.05), (-1.8, 0.05), (-1.8, -0.05)], "M_ParkPaver")
    mx, my = 1478.8 - o[0], 788.0 - o[1]
    B.boxmm((mx - 1.0, my - 0.4, 0.0), (mx + 1.0, my + 0.4, 1.6), "M_GraniteDark")
    zone = {"poly": [(1376.0, 655.0), (1520.0, 655.0), (1520.0, 905.0), (1376.0, 905.0)], "clear": []}
    export_site("PK_OlivePark", B, o, {"what": "Milton Lee Olive Park: 5 pool copings, walks, memorial"}, collide="complex", zone=zone)
    export_site("PK_OliveParkJets", J, o, {"what": "Olive Park fountain jets (no collision)"}, collide="none")


def heald_square():
    """Heald Square Monument (Lorado Taft / Leonard Crunelle, 1941) on Wacker Drive at Wabash: George Washington standing
    between Robert Morris and Haym Salomon, bronze on a granite base (OSM (79.8, -39.3)), facing north to the river."""
    o = (79.8, -39.3)
    B = PlanBuilder()
    B.boxmm((-4.0, -2.0, 0.0), (4.0, 2.0, 0.5), "M_Granite")
    B.boxmm((-3.4, -1.5, 0.5), (3.4, 1.5, 1.9), "M_Granite")
    m = "M_LionBronze"
    for x, h in ((-1.6, 2.6), (0.0, 3.0), (1.6, 2.6)):
        B.lathe([(0.42, 1.9), (0.36, 1.9 + h * 0.5), (0.24, 1.9 + h * 0.86), (0.0, 1.9 + h * 0.88)], m, 10, center=(x, 0.0, 0))
        B.ellipsoid((x, 0.0, 1.9 + h * 0.95), (0.14, 0.14, 0.18), m, 8, 6)
    zone = {"poly": [(74.0, -43.0), (86.0, -43.0), (86.0, -35.5), (74.0, -35.5)], "clear": ["props"]}
    export_site("PK_HealdSquare", B, o, {"what": "Heald Square Monument (stylised): three standing bronzes on a granite base"},
                collide="complex", zone=zone)


JOBS = {
    "pritzker": lambda: (pritzker_pavilion(), reset(), pritzker_trellis()),
    "bpbridge": lambda: bp_bridge(),
    "crown": lambda: crown_fountain(),
    "peristyle": lambda: peristyle(),
    "lurie": lambda: lurie_garden(),
    "mpav": lambda: millennium_pavilions(),
    "aic": lambda: (art_institute(), reset(), aic_lions()),
    "congress": lambda: congress_plaza(),
    "lincoln": lambda: lincoln_head_of_state(),
    "logan": lambda: logan_monument(),
    "spirit": lambda: spirit_of_music(),
    "petrillo": lambda: petrillo_shell(),
    "greatlakes": lambda: great_lakes_fountain(),
    "arch": lambda: stock_exchange_arch(),
    "picasso": lambda: chicago_picasso(),
    "flamingo": lambda: calder_flamingo(),
    "fourseasons": lambda: chagall_four_seasons(),
    "miro": lambda: miro_chicago(),
    "theatre": lambda: chicago_theatre(),
    "maggie": lambda: maggie_daley(),
    "lpt": lambda: lake_point_tower(),
    "cultural": lambda: cultural_center(),
    "bot": lambda: board_of_trade(),
    "aon": lambda: aon_center(),
    "pru": lambda: two_prudential(),
    "hwl": lambda: harold_washington_library(),
    "auditorium": lambda: auditorium_building(),
    "stregis": lambda: st_regis(),
    "carbide": lambda: carbide_carbon(),
    "olive": lambda: olive_park(),          # (two assets: the park and its jets)
    "heald": lambda: heald_square(),
    "rail": lambda: grant_park_rail(),
    "paths": lambda: park_paths(),            # run last: it reads the other assets' zones from parks.json
}


# ------------------------------------------------------------------ previews
def render_previews(names):
    sys.path.insert(0, ROOT + "/Scripts/landmarks")
    for name in names:
        lay = PREVIEWS.get(name)
        if not lay:
            print("no preview layout for", name)
            continue
        reset()
        lay = dict(lay)
        if callable(lay["layout"]):
            lay["layout"] = lay["layout"]()
        BL._preview(f"{BASE}/preview_{name}.png", **lay)


_bl = BL._bl


def site(names, center):
    """Preview layout: the named assets at their plan origins relative to `center` (plan m), from parks.json."""
    try:
        A = json.load(open(BASE + "/parks.json"))["assets"]
    except Exception:
        A = {}
    out = []
    for n in names:
        o = A.get(n, {}).get("origin_plan_m", center)
        out.append((n, _bl(o[0] - center[0], o[1] - center[1], 0.0)))
    return out


MP = (470.0, -545.0)                  # Millennium Park preview centre
MP_ALL = ["PK_PritzkerPavilion", "PK_PritzkerTrellis", "PK_BPBridge", "PK_CrownFountain", "PK_Peristyle", "PK_LurieGarden"]
PREVIEWS = {
    "MP_air": dict(layout=lambda: site(MP_ALL, MP), cam=(_bl(-260.0, -330.0, 260.0), _bl(10.0, 0.0, 0.0)), lens=32),
    "MP_pritzker": dict(layout=lambda: site(["PK_PritzkerPavilion", "PK_PritzkerTrellis"], MP), person=_bl(20.0, 30.0, 0.0),
                        cam=(_bl(10.0, -20.0, 2.0), _bl(22.0, 85.0, 18.0)), lens=24),
    "MP_pritzker_sw": dict(layout=lambda: site(["PK_PritzkerPavilion", "PK_PritzkerTrellis"], MP),
                           cam=(_bl(-50.0, 60.0, 3.0), _bl(22.0, 88.0, 20.0)), lens=24),
    "MP_bridge": dict(layout=lambda: site(["PK_BPBridge", "PK_PritzkerTrellis"], MP), cam=(_bl(170.0, -40.0, 12.0), _bl(130.0, 10.0, 3.0)), lens=28),
    "MP_crown": dict(layout=lambda: site(["PK_CrownFountain"], MP), person=_bl(-130.0, -120.0, 0.0),
                     cam=(_bl(-150.0, -160.0, 3.0), _bl(-134.0, -120.0, 7.0)), lens=28),
    "MP_peristyle": dict(layout=lambda: site(["PK_Peristyle"], MP), person=_bl(-140.0, 135.0, 0.0),
                         cam=(_bl(-140.0, 110.0, 2.0), _bl(-140.0, 148.0, 6.0)), lens=28),
    "AIC_front": dict(layout=lambda: site(["PK_ArtInstitute", "PK_ArtInstituteSteps", "PK_ArtInstituteLions"], (342.0, -884.0)),
                      person=_bl(-36.0, 8.0, 0.0), cam=(_bl(-75.0, -40.0, 3.0), _bl(-20.0, 0.0, 10.0)), lens=28),
    "AIC_lion": dict(layout=lambda: site(["PK_ArtInstitute", "PK_ArtInstituteSteps", "PK_ArtInstituteLions"], (342.0, -884.0)),
                     person=_bl(-38.0, 13.0, 0.0), cam=(_bl(-46.0, 10.0, 2.2), _bl(-34.5, 18.0, 3.6)), lens=35),
    "AIC_air": dict(layout=lambda: site(["PK_ArtInstitute", "PK_ArtInstituteSteps", "PK_ArtInstituteLions"], (342.0, -884.0)),
                    cam=(_bl(-120.0, -200.0, 160.0), _bl(80.0, 30.0, 0.0)), lens=32),
    "GP_congress": dict(layout=lambda: site(["PK_CongressPlaza"], (372.0, -1307.0)), person=_bl(-14.0, 22.0, 0.0),
                        cam=(_bl(-95.0, 0.0, 6.0), _bl(0.0, 0.0, 6.0)), lens=30),
    "GP_spearman": dict(layout=lambda: site(["PK_CongressPlaza"], (372.0, -1307.0)), cam=(_bl(-24.0, -20.0, 3.0), _bl(-14.0, -26.0, 7.0)), lens=35),
    "GP_lincoln": dict(layout=lambda: site(["PK_LincolnHeadOfState", "PK_LincolnHeadOfStateSteps"], (518.0, -1140.0)), person=_bl(6.0, -14.0, 0.0),
                       cam=(_bl(0.0, -42.0, 3.0), _bl(0.0, 0.0, 4.0)), lens=30),
    "GP_logan": dict(layout=lambda: site(["PK_LoganMonument"], (359.3, -1873.0)), person=_bl(-14.0, -10.0, 0.0),
                     cam=(_bl(-28.0, -18.0, 3.0), _bl(0.0, 0.0, 9.0)), lens=30),
    "GP_petrillo": dict(layout=lambda: site(["PK_PetrilloShell"], (640.0, -962.5)), person=_bl(25.0, -5.0, 0.0),
                        cam=(_bl(60.0, -30.0, 4.0), _bl(0.0, 0.0, 7.0)), lens=30),
    "GP_small": dict(layout=lambda: [("PK_SpiritOfMusic", _bl(0, 0, 0)), ("PK_GreatLakesFountain", _bl(20, 0, 0)), ("PK_StockExchangeArch", _bl(40, 0, 0))],
                     cam=(_bl(10.0, -32.0, 4.0), _bl(22.0, 0.0, 4.0)), lens=32),
    "L_picasso": dict(layout=lambda: [("PK_ChicagoPicasso", _bl(0, 0, 0))], person=_bl(4.0, -8.0, 0.0), cam=(_bl(2.0, -24.0, 2.0), _bl(0.0, 0.0, 7.5)), lens=32),
    "L_flamingo": dict(layout=lambda: [("PK_Flamingo", _bl(0, 0, 0))], person=_bl(3.0, -10.0, 0.0), cam=(_bl(-6.0, -30.0, 2.0), _bl(0.0, 0.0, 7.0)), lens=32),
    "L_fourseasons": dict(layout=lambda: [("PK_FourSeasons", _bl(0, 0, 0))], person=_bl(-4.0, -3.0, 0.0), cam=(_bl(-16.0, -16.0, 2.0), _bl(0.0, 0.0, 2.5)), lens=28),
    "L_miro": dict(layout=lambda: [("PK_MiroChicago", _bl(0, 0, 0))], person=_bl(3.0, -4.0, 0.0), cam=(_bl(4.0, -18.0, 2.0), _bl(0.0, 0.0, 6.0)), lens=32),
    "L_theatre": dict(layout=lambda: [("PK_ChicagoTheatre", _bl(0, 0, 0))], person=_bl(-3.0, -6.0, 0.0), cam=(_bl(-28.0, -26.0, 2.0), _bl(0.0, 2.0, 12.0)), lens=28),
    "MD_air": dict(layout=lambda: site(["PK_MaggieDaley", "PK_BPBridge"], (700.0, -500.0)), cam=(_bl(-120.0, -260.0, 150.0), _bl(10.0, 40.0, 0.0)), lens=32),
    "MD_wall": dict(layout=lambda: site(["PK_MaggieDaley"], (700.0, -500.0)), person=_bl(5.0, 17.0, 0.0), cam=(_bl(-25.0, -10.0, 3.0), _bl(16.0, 48.0, 6.0)), lens=28),
    "Paths_air": dict(layout=lambda: site(["PK_PathsMillennium", "PK_PathsGrantNorth", "PK_PathsGrantSouth", "PK_PritzkerPavilion", "PK_ArtInstitute"],
                                         (600.0, -1000.0)), cam=(_bl(-500.0, -1300.0, 700.0), _bl(0.0, -200.0, 0.0)), lens=40),
    "B_lpt": dict(layout=lambda: [("PK_LakePointTower", _bl(0, 0, 0))], cam=(_bl(-260.0, -330.0, 60.0), _bl(0.0, 0.0, 90.0)), lens=35, res=(900, 1100)),
    "B_cc": dict(layout=lambda: [("PK_CulturalCenter", _bl(0, 0, 0))], person=_bl(26.0, -60.0, 0.0), cam=(_bl(70.0, -95.0, 2.0), _bl(10.0, -10.0, 14.0)), lens=28),
    "B_bot": dict(layout=lambda: [("PK_BoardOfTrade", _bl(0, 0, 0))], cam=(_bl(-10.0, 230.0, 30.0), _bl(0.0, 0.0, 90.0)), lens=35, res=(900, 1100)),
    "B_skyline": dict(layout=lambda: site(["PK_AonCenter", "PK_TwoPrudential", "PK_CulturalCenter", "PK_PritzkerPavilion", "PK_PritzkerTrellis"], (470.0, -300.0)),
                      cam=(_bl(-20.0, -650.0, 60.0), _bl(10.0, 0.0, 120.0)), lens=30),
    "B_hwl": dict(layout=lambda: [("PK_HaroldWashingtonLibrary", _bl(0, 0, 0))], cam=(_bl(60.0, 90.0, 4.0), _bl(0.0, 0.0, 22.0)), lens=28),
    "B_aud": dict(layout=lambda: [("PK_AuditoriumBuilding", _bl(0, 0, 0))], cam=(_bl(110.0, -70.0, 4.0), _bl(0.0, 0.0, 25.0)), lens=28),
    "B_stregis": dict(layout=lambda: [("PK_VistaTower", _bl(0, 0, 0)), ("PK_CarbideCarbon", _bl(231.3 - 873.6, -105.3 + 35.6, 0))],
                      cam=(_bl(-300.0, -560.0, 60.0), _bl(-320.0, 0.0, 120.0)), lens=28),
    "MP_lurie": dict(layout=lambda: site(["PK_LurieGarden", "PK_PritzkerTrellis"], MP), cam=(_bl(90.0, -190.0, 25.0), _bl(35.0, -130.0, 0.0)), lens=30),
    # plan-local cameras (x east, y north, z up) via _bl; layout items are (glb name, blender loc)
    "Willis_SW": dict(layout=[("PK_WillisTower",)], cam=(_bl(-420.0, -560.0, 40.0), _bl(0.0, 0.0, 230.0)), lens=35, res=(800, 1100)),
    "Willis_base": dict(layout=[("PK_WillisTower",)], person=_bl(-60.0, -40.0, 0.0), cam=(_bl(-95.0, -75.0, 1.8), _bl(-20.0, -10.0, 60.0)), lens=24,
                        res=(1000, 1000)),
    "Willis_top": dict(layout=[("PK_WillisTower",)], cam=(_bl(-120.0, -70.0, 470.0), _bl(-10.0, 0.0, 430.0)), lens=40),
}


def write_json():
    path = BASE + "/parks.json"
    data = {}
    if os.path.exists(path):
        try:
            data = json.load(open(path))
        except Exception:
            data = {}
    assets = data.get("assets", {})
    assets.update(META)
    data["assets"] = dict(sorted(assets.items()))
    data["conventions"] = {
        "frame": "every asset is plan-local (Saved/Mashup/plan_v3.json: x east, y north, metres) about origin_plan_m, already turned "
                 "for Unreal: place at Unreal (X = y*100, Y = x*100) with NO rotation, Z = traced ground",
        "collide": "complex = complex-as-simple collision; none = visual only; hidden = invisible collider (hidden in game)",
        "zone": "plan polygon to clear of street props/trees ('props') and City Sample building instances ('buildings')",
        "generator": "Scripts/landmarks/blender_chicago_parks.py",
    }
    json.dump(data, open(path, "w"), indent=1)
    print("wrote", path)


if __name__ == "__main__":
    if ARGS and ARGS[0] == "willis_ref":          # reference GLBs for the willis-tower agent only (not recorded / placed)
        reset()
        willis_tower()
        print("ALL DONE")
        sys.exit(0)
    if ARGS and ARGS[0] == "--render":
        render_previews(ARGS[1:])
    else:
        for job, fn in JOBS.items():
            if ARGS and job not in ARGS:
                continue
            reset()
            fn()
        write_json()
    print("ALL DONE")
