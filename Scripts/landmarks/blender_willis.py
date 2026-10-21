"""Sky City: the Willis Tower (Chicago, SOM 1970-74, Sears Tower until 2009) and its base, modelled procedurally in headless
Blender and exported as GLB, plus the small textures its tiling curtain-wall material uses in Unreal.

Why: Kenny (20 Oct 2026): "drive up the willis tower for example (also that still has to be textured by the way)".
Climbing it is one of the game's signature things to do (Design/Places_and_Easter_Eggs.md: wall-ride all 442 m up the
face to the roof, park in one of the Skydeck's glass Ledge boxes on the 103rd floor). build_city.py only had nine
untextured boxes (Landmark_WillisTower).

References (SourceArt/Reference/WillisTower/sources.txt): OpenStreetMap building:part outlines (tubes, Catalog podium,
rooftop drums, masts), Wikipedia, SkyscraperPage (Chicago Building Dept. floor levels), Wikimedia Commons photographs.

Frame and conventions (as Scripts/landmarks/blender_landmarks.py, whose Builder / PlanBuilder this script imports):
  * metres; modelled in the TOWER frame (x east, y north along the tower's own grid, origin = the centre of the
    nine-tube square at street level), then turned by THETA (the tower is turned 1.08 deg counter-clockwise from the
    plan axes, OpenStreetMap edges) and by -90 deg (PlanBuilder) at export: every asset goes into Unreal at
    ORIGIN (plan) with NO rotation (Scripts/roads/place_willis_ue.py);
  * one bmesh per asset with per-face material slots M_WT_*; place_willis_ue.py maps them to MI_WT_*;
  * curtain-wall faces carry UVs in BAYS (u, 15 ft = 4.572 m, integer at every column line) and FLOORS (v, integer at
    every floor line, through the real floor levels): the M_WT_Facade material tiles one bay x one floor, and picks the
    lit windows at night from a small random map by floor(u * 3) / floor(v);
  * the visible meshes have NO collision; the car drives on three hidden colliders with clean flat faces:
      WT_ColWalls  every wall face (tower + podium) and the LIPS: each exposed roof edge is rounded over (a short tight
                   radius R1 for the first 12 deg off the wall, then a long radius R2 to the roof) so the Roadster rolls
                   from the face onto the roof instead of flying off: SkysterCar.cpp launches the car when the surface
                   normal turns more than ~2.5 m/s worth in one 1/120 s substep once N.z > 0.6, so R2 >= v^2 / 300 and the
                   facets are about one substep long. Checked offline with Saved/Willis/lip_sim.py (the support / seat /
                   launch rules copied from the C++): the tower lips take a full-throttle level-6 wall ride (~50 m/s)
                   up to 55 m/s; the podium lips about 35-40 m/s (faster: a hop that lands on the roof or the tower);
      WT_ColRoofs  every flat top (setbacks, the 442 m roof, podium terraces, drum tops, the atrium's skylight): a
                   separate component from the walls, because the car's "drive down a wall onto the ground" code only
                   re-seats on a different component;
      WT_ColLedge  the Ledge boxes' floors and side/front panes (open top, so a car driving down the face drops in).
Assets (SourceArt/Landmarks/willis/<name>.glb, all at the same origin):
  WT_Tower     the nine tubes: curtain wall, louvre bands (floors 29-32, 64-65, 88-89, 106-108), column covers every
               15 ft, copings, the setback roofs (white membrane at 50/66, grey at 90/108) and the four rooftop drums
  WT_Top       the two masts (west 527.3 m, east 521.2 m), six smaller masts, base frames, red beacons
  WT_Ledge     four glass boxes on the 103rd floor, west face of the west tube (bays 1, 2, 4, 5: the middle bay is the
               climbing lane), 3.6 x 5.0 x 3.0 m (real ones stick out about 1.3 m: these are deepened so the car fits)
  WT_Base      the Catalog podium and wings (OSM building:part outlines simplified to rectangles), roof terrace and
               garden, the atrium skylight, the Wacker Drive forecourt and the Jackson Blvd forecourt paving
  WT_ColWalls, WT_ColRoofs, WT_ColLedge   hidden colliders (see above)
Writes SourceArt/Landmarks/willis/willis.json (frame, assets, heights, the clear zone, test points, Ledge boxes) and
SourceArt/Landmarks/willis/textures/T_WT_*.png (small: 256 px and under).

Run (repo root):
  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/landmarks/blender_willis.py [-- jobs...]
    jobs: textures tower top ledge base collision (default: all), then writes willis.json
  ... -P Scripts/landmarks/blender_willis.py -- --render [names...]
    preview renders SourceArt/Landmarks/willis/preview_<name>.png (sw, west, top, ledge, base; default: all)
"""
import json, math, os, random, struct, sys, zlib
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
import blender_landmarks as BL                                    # noqa: E402  (shared Builder / materials)
from blender_landmarks import PlanBuilder, mat, tri_count          # noqa: E402

BASE = ROOT + "/SourceArt/Landmarks/willis"
TEXD = BASE + "/textures"
os.makedirs(TEXD, exist_ok=True)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
META = {}

# ------------------------------------------------------------------ frame and dimensions
ORIGIN = (-671.4473, -959.3803)    # plan metres: centre of the OSM tube square (Scripts: fit of the building:part edges)
THETA_DEG = 1.0771                 # the tower grid is turned this much counter-clockwise from the plan axes (OSM edges)
TH = math.radians(THETA_DEG)
OUT_FACE = 34.9                    # 229 ft square at the outside faces (column covers); 225 ft between column lines
XB = [-OUT_FACE, -11.43, 11.43, OUT_FACE]     # tube boundaries (interior ones are column lines, 75 ft tubes)
BAY = 4.572                        # columns 15 ft on centre
GRID0 = -34.29                     # the west / south column line: bays count from here
GLASS_IN = 0.25                    # glass sits this far behind the column-cover face
# floor levels (m above the Wacker Drive entrance): Chicago Building Dept. via SkyscraperPage (50th 658 ft, 66th 874 ft,
# 90th 1,186 ft, 103rd 1,353 ft); the floor above each setback's last floor is its roof; main roof 1,451 ft
FZ = [(1, 0.0), (50, 200.6), (51, 204.7), (66, 266.4), (67, 270.4), (90, 361.5), (91, 365.4), (103, 412.4), (109, 442.1)]


def zf(F):
    for (f0, z0), (f1, z1) in zip(FZ, FZ[1:]):
        if F <= f1:
            return z0 + (z1 - z0) * (F - f0) / (f1 - f0)
    return FZ[-1][1]


def fz(z):
    for (f0, z0), (f1, z1) in zip(FZ, FZ[1:]):
        if z <= z1 + 1e-9:
            return f0 + (f1 - f0) * (z - z0) / (z1 - z0)
    return FZ[-1][0]


TOP = zf(109)                      # 442.1: the roof (here a flush deck at the parapet top, so it can be driven)
H50, H66, H90 = zf(51), zf(67), zf(91)
# tube heights by (col W->E, row S->N): NW+SE end at the 50th floor, NE+SW at the 66th, N+E+S at the 90th, W+C at 108
HT = {(0, 0): H66, (1, 0): H90, (2, 0): H50,
      (0, 1): TOP, (1, 1): TOP, (2, 1): H90,
      (0, 2): H50, (1, 2): H90, (2, 2): H66}
BANDS = [(29, 33), (64, 66), (88, 90), (106, 109)]     # black louvre bands: floors 29-32, 64-65, 88-89 and the top (106-108 + parapet;
# Wikipedia gives 104-108, but the photographs show glass rows between the Ledge and the dark top band)
LEDGE_FLOOR = zf(103)              # 412.4 m, the Skydeck
LEDGE = dict(w=3.6, d=5.0, h=3.0, bays=(-9.144, -4.572, 4.572, 9.144))   # west face of the west tube, bays 1 2 4 5
DRUMS = [(23.06, -22.32), (-22.62, -22.34), (-22.43, 22.90), (23.41, 22.84)]   # OSM: r 4.36 m, 5 m tall (SE, SW, NW, NE)
DRUM_R, DRUM_H = 4.36, 5.0
MASTS = [(-24.60, 0.19, 527.3), (2.17, 0.05, 521.2)]   # west (extended 2000, 1,730 ft) and east (1,710 ft); OSM r 2.33 m
SMALL_MASTS = [(-17.80, 6.99, 24.0), (-11.49, 7.15, 30.0), (-4.77, 7.20, 20.0), (-4.83, -5.95, 26.0), (-10.26, -6.04, 18.0),
               (-16.65, -6.11, 28.0)]
# the base: OSM building:part outlines (Catalog by Gensler 2019-22, the Wacker and Franklin entrances, the Adams canopy),
# simplified to rectangles in the tower frame (snapped to the tower faces) and split so that every edge sees one
# neighbour height
# (name, x0, x1, y0, y1, height, roof material)
PODIUM = [
    ("AdamsCanopy", -24.8, 20.7, 34.9, 42.8, 5.0, "M_WT_PodiumRoofDark"),
    ("NE_North", 20.7, 40.8, 34.9, 42.8, 10.0, "M_WT_PodiumRoof"),
    ("NE_East", 34.9, 40.8, 11.6, 34.9, 10.0, "M_WT_PodiumRoof"),
    ("FranklinEntrance", 34.9, 40.8, -11.6, 11.6, 10.0, "M_WT_PodiumRoofDark"),
    ("SE_East", 34.9, 40.8, -75.7, -11.6, 10.0, "M_WT_PodiumRoof"),
    ("SE_SouthA", 11.6, 34.9, -75.7, -71.6, 10.0, "M_WT_PodiumRoof"),
    ("SE_SouthB", 11.6, 34.9, -71.6, -66.0, 10.0, "M_WT_PodiumRoof"),
    ("CatalogW1", -51.2, -43.5, -66.0, -10.6, 20.0, "M_WT_PodiumRoof"),
    ("CatalogW2", -43.5, -34.9, -66.0, -10.6, 20.0, "M_WT_PodiumRoof"),
    ("CatalogS1", -34.9, -24.6, -66.0, -34.9, 20.0, "M_WT_PodiumRoof"),
    ("CatalogS2", -24.6, -11.6, -66.0, -34.9, 20.0, "M_WT_PodiumRoof"),
    ("CatalogGarden", 11.6, 34.9, -66.0, -34.9, 20.0, "M_WT_Lawn"),
    ("CatalogSouthA", -11.6, 11.6, -71.6, -66.0, 20.0, "M_WT_PodiumRoof"),
    ("CatalogSouthB", -11.6, 11.6, -66.0, -61.9, 20.0, "M_WT_PodiumRoof"),
    ("CatalogHigh", -40.0, -20.0, -55.6, -38.0, 25.0, "M_WT_PodiumRoofDark"),
    ("JacksonRow", -43.5, -24.6, -75.5, -66.0, 20.0, "M_WT_PodiumRoof"),
    ("JacksonW", -51.2, -43.5, -75.5, -66.0, 10.0, "M_WT_PodiumRoof"),
    ("JacksonE_A", -24.6, -11.6, -75.5, -71.6, 10.0, "M_WT_PodiumRoof"),
    ("JacksonE_B", -24.6, -11.6, -71.6, -66.0, 10.0, "M_WT_PodiumRoof"),
    ("WackerPavilion", -43.5, -34.9, -10.6, 11.1, 20.0, "M_WT_PodiumRoofDark"),
    ("WackerN_A", -51.3, -43.5, 11.1, 34.9, 20.0, "M_WT_PodiumRoof"),
    ("WackerN_B", -43.5, -34.9, 11.1, 34.9, 20.0, "M_WT_PodiumRoof"),
    ("AdamsW", -51.3, -24.8, 34.9, 42.9, 10.0, "M_WT_PodiumRoof"),
]
ATRIUM = (-11.6, 11.6, -61.9, -34.9, 20.0, 21.0)      # glass-roofed atrium (OSM 21 m, roof colour #cddce7): 4 m slopes
FORECOURTS = [(-56.0, -43.5, -10.6, 11.1), (-11.6, 11.6, -76.6, -71.6)]   # Wacker entrance, Jackson visitors' entrance
BLOCK = (-51.3, 40.8, -75.7, 42.9)                     # the city block between the backs of the four sidewalks
# lip profiles (R1, R2, end of R1 in deg, facets on R1, facets on R2): see the module docstring and Saved/Willis/lip_sim.py
PROF = {"big": (0.8, 10.0, 12.0, 3, 30), "pod": (0.6, 6.0, 12.0, 3, 20), "small": (0.5, 3.0, 12.0, 3, 16)}

# ------------------------------------------------------------------ materials (added to blender_landmarks.MATDEF)
BL.MATDEF.update({
    "M_WT_CurtainWall": ((0.05, 0.045, 0.04), 0.5, 0.10, {}),     # bronze-tinted glass + black aluminium (tiled in UE)
    "M_WT_Louvre": ((0.025, 0.025, 0.027), 0.6, 0.50, {}),        # mechanical-floor louvres
    "M_WT_SkydeckGlass": ((0.06, 0.05, 0.04), 0.5, 0.10, {}),     # the 103rd floor: every window lit (the Skydeck at night)
    "M_WT_Alu": ((0.02, 0.02, 0.022), 0.7, 0.40, {}),             # black anodised aluminium: column covers, copings
    "M_WT_RoofWhite": ((0.70, 0.70, 0.68), 0.0, 0.80, {}),        # OSM roof:colour #ffffff (50th / 66th setbacks)
    "M_WT_RoofGrey": ((0.19, 0.18, 0.165), 0.0, 0.85, {}),        # OSM roof:colour #797771 (90th setbacks, main roof)
    "M_WT_DrumMetal": ((0.55, 0.56, 0.57), 0.6, 0.40, {}),
    "M_WT_MastWhite": ((0.82, 0.83, 0.84), 0.3, 0.40, {}),
    "M_WT_Beacon": ((1.00, 0.05, 0.02), 0.0, 0.40, {"emit": 8.0}),
    "M_WT_LedgeGlass": ((0.60, 0.70, 0.75), 0.0, 0.05, {"alpha": 0.25}),
    "M_WT_LedgeFrame": ((0.05, 0.05, 0.055), 0.7, 0.40, {}),
    "M_WT_Podium": ((0.06, 0.07, 0.08), 0.5, 0.15, {}),           # Catalog curtain wall (tiled in UE)
    "M_WT_PodiumRoof": ((0.45, 0.44, 0.42), 0.0, 0.80, {}),       # roof terrace pavers
    "M_WT_PodiumRoofDark": ((0.12, 0.12, 0.13), 0.0, 0.85, {}),
    "M_WT_Lawn": ((0.12, 0.25, 0.07), 0.0, 0.95, {}),             # Catalog roof garden
    "M_WT_Skylight": ((0.10, 0.13, 0.15), 0.8, 0.05, {}),
    "M_WT_Granite": ((0.50, 0.42, 0.40), 0.0, 0.60, {}),          # forecourt paving
    "M_WT_Col": ((0.80, 0.20, 0.80), 0.0, 0.50, {}),              # hidden colliders
})


def reset():
    BL.reset()


class TB(PlanBuilder):
    """Builder in the tower frame: finish() turns it by THETA (tower grid -> plan axes), then PlanBuilder turns it -90 deg."""

    def finish(self, name, sharp_angle=48.0, weld=True):
        bmesh.ops.transform(self.bm, matrix=Matrix.Rotation(TH, 4, "Z"), verts=self.bm.verts)
        return PlanBuilder.finish(self, name, sharp_angle, weld)


def to_plan(x, y):
    c, s = math.cos(TH), math.sin(TH)
    return (ORIGIN[0] + c * x - s * y, ORIGIN[1] + s * x + c * y)


def heading(dx, dy):
    """Compass heading (deg, 0 = plan north, 90 = east) of a tower-frame direction = the Unreal yaw."""
    c, s = math.cos(TH), math.sin(TH)
    px, py = c * dx - s * dy, s * dx + c * dy
    return math.degrees(math.atan2(px, py)) % 360.0


def export(name, objs, meta=None):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=f"{BASE}/{name}.glb", export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_materials="EXPORT", export_image_format="NONE")
    lo = Vector((1e9, 1e9, 1e9))
    hi = -lo
    for o in objs:
        for v in o.data.vertices:
            co = o.matrix_world @ v.co
            lo = Vector(map(min, lo, co))
            hi = Vector(map(max, hi, co))
    mats = []
    for o in objs:
        for m in o.data.materials:
            if m.name not in mats:
                mats.append(m.name)
    d = {"file": f"SourceArt/Landmarks/willis/{name}.glb", "tris": tri_count(objs), "bbox_min_m": [round(c, 3) for c in lo],
         "bbox_max_m": [round(c, 3) for c in hi], "materials": mats}
    d.update(meta or {})
    META[name] = d
    print(f"exported {name}: {d['tris']} tris, size {tuple(round(c, 2) for c in hi - lo)}, mats {mats}")


# ------------------------------------------------------------------ block geometry helpers
def tube_rect(c, r):
    return (XB[c], XB[c + 1], XB[r], XB[r + 1])


def all_blocks():
    """(x0, x1, y0, y1, H) of every tube and podium block (the atrium counts as 20 m at its edges)."""
    out = [tube_rect(c, r) + (h,) for (c, r), h in HT.items()]
    out += [(x0, x1, y0, y1, h) for _n, x0, x1, y0, y1, h, _m in PODIUM]
    out.append(ATRIUM[:4] + (ATRIUM[4],))
    return out


BLOCKS = all_blocks()


def height_at(x, y):
    h = 0.0
    for x0, x1, y0, y1, hh in BLOCKS:
        if x0 + 1e-6 < x < x1 - 1e-6 and y0 + 1e-6 < y < y1 - 1e-6:
            h = max(h, hh)
    return h


def rect_edges(x0, x1, y0, y1):
    """Counter-clockwise edges: (name, A, B, outward normal)."""
    return [("S", (x0, y0), (x1, y0), (0, -1)), ("E", (x1, y0), (x1, y1), (1, 0)),
            ("N", (x1, y1), (x0, y1), (0, 1)), ("W", (x0, y1), (x0, y0), (-1, 0))]


def edge_intervals(A, B, n, H):
    """Split edge A->B at every block boundary; each interval with the height just outside it (0.3 m out)."""
    horiz = abs(A[1] - B[1]) < 1e-6
    a0, a1 = (A[0], B[0]) if horiz else (A[1], B[1])
    lo, hi = min(a0, a1), max(a0, a1)
    cuts = {lo, hi}
    for x0, x1, y0, y1, _h in BLOCKS:
        for v in ((x0, x1) if horiz else (y0, y1)):
            if lo + 1e-3 < v < hi - 1e-3:
                cuts.add(v)
    cuts = sorted(cuts)
    out = []
    for s0, s1 in zip(cuts, cuts[1:]):
        m = (s0 + s1) / 2
        p = (m, A[1]) if horiz else (A[0], m)
        ho = height_at(p[0] + n[0] * 0.3, p[1] + n[1] * 0.3)
        out.append((s0, s1, ho))
    if (a1 < a0):
        out = out[::-1]
    return out, horiz


def profile(R1, R2, p1deg=12.0, n1=3, n2=30):
    """Lip curve (d inward from the wall plane, h below the roof): from (0, -Lz), vertical, to (D, 0), horizontal."""
    p1 = math.radians(p1deg)
    pts = []
    for k in range(n1 + 1):
        ph = p1 * k / n1
        pts.append((R1 * (1 - math.cos(ph)), R1 * math.sin(ph)))
    d1, h1 = pts[-1]
    for k in range(1, n2 + 1):
        ph = p1 + (math.pi / 2 - p1) * k / n2
        pts.append((d1 + R2 * (math.cos(p1) - math.cos(ph)), h1 + R2 * (math.sin(ph) - math.sin(p1))))
    Lz = pts[-1][1]
    return [(d, h - Lz) for d, h in pts], pts[-1][0], Lz


# ------------------------------------------------------------------ textures (tiny PNG writer: no PIL inside Blender)
def write_png(path, w, h, rgba_rows):
    raw = b"".join(b"\x00" + bytes(row) for row in rgba_rows)
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    open(path, "wb").write(png)


def smoothstep(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def band(x, a, b, soft):
    return smoothstep(a - soft, a + soft, x) * (1 - smoothstep(b - soft, b + soft, x))


def textures():
    """T_WT_CurtainWall: one bay (u 0..1 = 4.572 m) x one floor (v 0..1, image top = top of the floor), RGBA masks:
         R glass (three windows between the column covers, glass from 20% to 82% of the floor), G frame relief (mullion
         edge highlight / reveal shadow), B spandrel panel, A 1.
       T_WT_Louvre: same tile, louvre blades (G), no glass.
       T_WT_Podium: one panel (1.5 m) x one storey (5 m) of the Catalog's curtain wall: tall glass, thin frames, a transom.
       T_WT_Lit: 64 x 64 random map, one texel per window (3 per bay) per floor: R = lit (floor-clustered office
         lighting), G = glass tint variation, B = blinds; sampled point-filtered by floor(u*3), floor(v)."""
    N = 256
    rows = []
    for j in range(N):
        v = 1.0 - (j + 0.5) / N
        row = []
        for i in range(N):
            u = (i + 0.5) / N
            # windows: column cover halves at the bay edges (the 3-D covers sit on top), 2 mullions inside
            cover = 0.066
            span = 1 - 2 * cover
            wpos = (u - cover) / span * 3.0
            inbay = cover < u < 1 - cover
            frac = wpos - math.floor(wpos)
            mull = 0.035                                   # mullion half-width (fraction of a window)
            gx = 1.0 if inbay else 0.0
            gx *= smoothstep(mull - 0.01, mull + 0.01, frac) * (1 - smoothstep(1 - mull - 0.01, 1 - mull + 0.01, frac))
            gy = band(v, 0.20, 0.82, 0.006)
            glass = gx * gy
            spandrel = (1 - gy) * (1.0 if inbay else 0.0)
            # relief: a light rim on the frame next to the glass, a reveal shadow inside the pane edge
            rim = band(v, 0.18, 0.20, 0.004) + band(v, 0.82, 0.84, 0.004)
            edge = max(0.0, 1 - min(frac, 1 - frac) / 0.08) * gy
            relief = min(1.0, 0.5 + 0.35 * rim - 0.25 * edge)
            row += [int(255 * glass), int(255 * relief), int(255 * spandrel), 255]
        rows.append(row)
    write_png(f"{TEXD}/T_WT_CurtainWall.png", N, N, rows)
    # louvre: 14 blades per floor, darker gaps, the same bay framing
    rows = []
    for j in range(128):
        v = 1.0 - (j + 0.5) / 128
        row = []
        for i in range(128):
            u = (i + 0.5) / 128
            blade = 0.5 + 0.5 * math.cos(v * 14 * 2 * math.pi)
            inbay = 0.066 < u < 0.934
            g = 0.25 + 0.6 * blade if inbay else 0.4
            row += [0, int(255 * g), 0, 255]
        rows.append(row)
    write_png(f"{TEXD}/T_WT_Louvre.png", 128, 128, rows)
    # podium: 1.5 m panel x 5 m storey: frames 6 cm, transom at 3.6 m, spandrel 4.6-5.0 m
    rows = []
    for j in range(128):
        v = 1.0 - (j + 0.5) / 128
        row = []
        for i in range(128):
            u = (i + 0.5) / 128
            gx = band(u, 0.04, 0.96, 0.01)
            gy = band(v, 0.02, 0.70, 0.005) + band(v, 0.73, 0.90, 0.005)
            glass = gx * min(1.0, gy)
            spandrel = 1.0 - band(v, 0.0, 0.90, 0.005)
            row += [int(255 * glass), int(255 * (0.55 + 0.2 * (1 - gx))), int(255 * spandrel), 255]
        rows.append(row)
    write_png(f"{TEXD}/T_WT_Podium.png", 128, 128, rows)
    # lit windows: floors cluster (whole floors or wings lit), windows vary inside a floor
    rnd = random.Random(1974)
    S = 64
    fl = [rnd.random() for _ in range(S)]
    wing = [[rnd.random() for _ in range(8)] for _ in range(S)]
    rows = []
    for j in range(S):
        row = []
        for i in range(S):
            val = 0.45 * fl[j] + 0.35 * wing[j][i // 8] + 0.20 * rnd.random()
            row += [int(255 * val), int(255 * rnd.random()), int(255 * rnd.random()), 255]
        rows.append(row)
    write_png(f"{TEXD}/T_WT_Lit.png", S, S, rows)
    print("textures written to", TEXD)


# ------------------------------------------------------------------ the tower (visible)
def u_of(p, t):
    """Bay coordinate of a tower-frame point along the face tangent t."""
    return ((p[0] - GRID0) * t[0] + (p[1] - GRID0) * t[1]) / BAY


def z_cuts(z0, z1):
    cuts = {z0, z1}
    for f, _z in FZ:
        z = zf(f)
        if z0 + 1e-3 < z < z1 - 1e-3:
            cuts.add(z)
    for a, b in BANDS + [(103, 104)]:
        for z in (zf(a), zf(b)):
            if z0 + 1e-3 < z < z1 - 1e-3:
                cuts.add(z)
    return sorted(cuts)


def in_band(z0, z1):
    zm = (z0 + z1) / 2
    return any(zf(a) <= zm <= zf(b) for a, b in BANDS)


def in_skydeck(z0, z1):
    zm = (z0 + z1) / 2
    return zf(103) <= zm <= zf(104)


FACE_SEED = [0]


def facade(B, A, Bp, n, z0, z1, corner_a, corner_b):
    """One exposed tube face from A to Bp (tower frame, the cover surface), outward normal n, from z0 to z1.
    corner_a / corner_b: the end is a convex corner (gets an end cover)."""
    t = (-n[1], n[0])
    # orient along t
    if (Bp[0] - A[0]) * t[0] + (Bp[1] - A[1]) * t[1] < 0:
        A, Bp, corner_a, corner_b = Bp, A, corner_b, corner_a
    L = math.hypot(Bp[0] - A[0], Bp[1] - A[1])
    gi = (-n[0] * GLASS_IN, -n[1] * GLASS_IN)
    ga = (A[0] + gi[0], A[1] + gi[1])
    gb = (Bp[0] + gi[0], Bp[1] + gi[1])
    FACE_SEED[0] += 1
    # UVs stay small (Unreal stores mesh UVs as half floats: 1/64 precision below 16): subtract whole bays / floors and
    # add a small whole offset per quad instead, so the lit-window map still differs from quad to quad
    u0 = math.floor(u_of(A, t))
    ua, ub = u_of(A, t) - u0, u_of(Bp, t) - u0
    zs = z_cuts(z0, z1)
    for za, zb in zip(zs, zs[1:]):
        m = "M_WT_Louvre" if in_band(za, zb) else ("M_WT_SkydeckGlass" if in_skydeck(za, zb) else "M_WT_CurtainWall")
        fa, fb = fz(za), fz(zb)
        n_ch = max(1, math.ceil((fb - fa) / 12.0 - 1e-6))
        for c_ in range(n_ch):
            f0 = fa + (fb - fa) * c_ / n_ch
            f1 = fa + (fb - fa) * (c_ + 1) / n_ch
            z_0, z_1 = zf(f0), zf(f1)
            k = (FACE_SEED[0] * 7 + c_ * 3 + int(fa)) % 4
            va, vb = f0 - math.floor(f0) + k, f1 - math.floor(f0) + k
            B.face([(ga[0], ga[1], z_0), (gb[0], gb[1], z_0), (gb[0], gb[1], z_1), (ga[0], ga[1], z_1)], m,
                   [(ua, va), (ub, va), (ub, vb), (ua, vb)])
    # column covers on every column line inside the face, end covers at convex corners
    k0, k1 = math.ceil(u_of(A, t) - 1e-6), math.floor(u_of(Bp, t) + 1e-6)
    pos = []
    for k in range(k0, k1 + 1):
        s = (k - u_of(A, t)) * BAY
        if 0.29 < s < L - 0.29:
            pos.append(s)
    if corner_a:
        pos.append(0.3)
    if corner_b:
        pos.append(L - 0.3)
    for s in pos:
        cx, cy = A[0] + t[0] * s - n[0] * GLASS_IN / 2, A[1] + t[1] * s - n[1] * GLASS_IN / 2
        w = 0.6
        B.box((cx, cy, (z0 + z1) / 2), (abs(t[0]) * w + abs(n[0]) * GLASS_IN, abs(t[1]) * w + abs(n[1]) * GLASS_IN, z1 - z0), "M_WT_Alu")
    # coping band at the top
    cx, cy = (A[0] + Bp[0]) / 2 - n[0] * GLASS_IN / 2, (A[1] + Bp[1]) / 2 - n[1] * GLASS_IN / 2
    B.box((cx, cy, z1 - 0.35), (abs(t[0]) * L + abs(n[0]) * (GLASS_IN + 0.02), abs(t[1]) * L + abs(n[1]) * (GLASS_IN + 0.02), 0.7), "M_WT_Alu")


def roof_groups():
    """Roof rectangles: the W and C tubes share the 442 m roof; every other tube has its own."""
    groups = [((XB[0], XB[2], XB[1], XB[2]), TOP, "top")]
    names = {(0, 0): "SW", (1, 0): "S", (2, 0): "SE", (2, 1): "E", (0, 2): "NW", (1, 2): "N", (2, 2): "NE"}
    for (c, r), nm in names.items():
        groups.append((tube_rect(c, r), HT[(c, r)], nm))
    return groups


def tower():
    B = TB()
    FACE_SEED[0] = 0
    for (x0, x1, y0, y1), H, nm in roof_groups():
        edges = rect_edges(x0, x1, y0, y1)
        expo = []
        for k, (en, A, Bp, n) in enumerate(edges):
            iv, horiz = edge_intervals(A, Bp, n, H)
            expo.append(any(ho < H - 0.5 for _a, _b, ho in iv))
        for k, (en, A, Bp, n) in enumerate(edges):
            iv, horiz = edge_intervals(A, Bp, n, H)
            for s0, s1, ho in iv:
                if ho >= H - 0.5:
                    continue
                pa = (s0, A[1]) if horiz else (A[0], s0)
                pb = (s1, A[1]) if horiz else (A[0], s1)
                # a convex corner at an interval end that is also the rectangle's corner, with the next edge exposed
                ca = cb = False
                for P_, flag in ((pa, "a"), (pb, "b")):
                    if abs(P_[0] - A[0]) < 1e-6 and abs(P_[1] - A[1]) < 1e-6:
                        c_ = expo[k - 1]
                    elif abs(P_[0] - Bp[0]) < 1e-6 and abs(P_[1] - Bp[1]) < 1e-6:
                        c_ = expo[(k + 1) % 4]
                    else:
                        c_ = False
                    if flag == "a":
                        ca = c_
                    else:
                        cb = c_
                facade(B, pa, pb, n, ho, H, ca, cb)
        # roof membrane
        m = "M_WT_RoofWhite" if H < 300 else "M_WT_RoofGrey"
        B.face([(x0, y0, H + 0.02), (x1, y0, H + 0.02), (x1, y1, H + 0.02), (x0, y1, H + 0.02)], m)
        # dark coping border on the roof (0.6 m)
        for en, A, Bp, n in edges:
            if not expo[[e[0] for e in edges].index(en)]:
                continue
            t = (Bp[0] - A[0], Bp[1] - A[1])
            Lr = math.hypot(*t)
            t = (t[0] / Lr, t[1] / Lr)
            inw = (-n[0], -n[1])
            P = [A, Bp, (Bp[0] + inw[0] * 0.6, Bp[1] + inw[1] * 0.6), (A[0] + inw[0] * 0.6, A[1] + inw[1] * 0.6)]
            B.face([(p[0], p[1], H + 0.04) for p in P], "M_WT_Alu")
    # rooftop drums (window-washer garages) on the 50th / 66th-floor roofs
    for (dx, dy) in DRUMS:
        H = height_at(dx, dy)
        B.lathe([(DRUM_R, H), (DRUM_R, H + DRUM_H - 0.6), (DRUM_R + 0.05, H + DRUM_H - 0.6), (DRUM_R + 0.05, H + DRUM_H),
                 (0.0, H + DRUM_H + 0.6)], "M_WT_DrumMetal", 32, center=(dx, dy, 0))
        B.lathe([(DRUM_R + 0.02, H + 1.2), (DRUM_R + 0.02, H + 1.6)], "M_WT_Alu", 32, center=(dx, dy, 0), smooth=True)
    ob = B.finish("WT_Tower")
    export("WT_Tower", [ob], {"what": "nine bundled tubes: curtain wall (UV bays x floors), louvre bands, column covers, copings, "
                                      "setback roofs, rooftop drums; NO collision (WT_Col* carry it)"})


# ------------------------------------------------------------------ the masts (visible)
def top():
    B = TB()
    for k, (mx, my, mz) in enumerate(MASTS):
        z0 = TOP
        # base frame: a white steel platform round the mast foot
        for sx in (-1, 1):
            for sy in (-1, 1):
                B.box((mx + sx * 3.2, my + sy * 3.2, z0 + 5.0), (0.35, 0.35, 10.0), "M_WT_MastWhite")
        for zz in (z0 + 3.5, z0 + 7.0, z0 + 10.0):
            for (ax, ay), (bx, by) in (((-3.2, -3.2), (3.2, -3.2)), ((3.2, -3.2), (3.2, 3.2)), ((3.2, 3.2), (-3.2, 3.2)), ((-3.2, 3.2), (-3.2, -3.2))):
                B.beam((mx + ax, my + ay, zz), (mx + bx, my + by, zz), 0.18, 0.18, "M_WT_MastWhite")
        # the mast: stepped tapering tube (photographs: wide base, three telescoping sections, a thin top)
        if k == 0:
            prof = [(2.33, z0), (2.33, z0 + 12.0), (1.95, z0 + 12.6), (1.95, z0 + 36.0), (1.55, z0 + 36.6), (1.55, z0 + 55.0),
                    (1.15, z0 + 55.6), (1.15, z0 + 67.0), (0.42, z0 + 67.6), (0.42, mz - 4.0), (0.22, mz - 3.5), (0.22, mz), (0.0, mz)]
        else:
            prof = [(2.33, z0), (2.33, z0 + 12.0), (1.95, z0 + 12.6), (1.95, z0 + 33.0), (1.55, z0 + 33.6), (1.55, z0 + 52.0),
                    (1.15, z0 + 52.6), (1.15, z0 + 70.0), (0.45, z0 + 70.6), (0.45, mz - 2.0), (0.0, mz)]
        B.lathe(prof, "M_WT_MastWhite", 16, center=(mx, my, 0))
        for zz in (z0 + 24.0, z0 + 46.0, z0 + 62.0):
            r = 2.0 if zz < z0 + 30 else (1.6 if zz < z0 + 50 else 1.2)
            B.lathe([(r, zz), (r + 0.45, zz + 0.25), (r + 0.45, zz + 0.9), (r, zz + 1.1)], "M_WT_MastWhite", 16, center=(mx, my, 0))
            B.lathe([(0.0, zz + 1.1), (0.3, zz + 1.4), (0.0, zz + 1.7)], "M_WT_Beacon", 8, center=(mx, my, 0))
        for zz in (mz, z0 + 67.0 if k == 0 else z0 + 70.0):
            B.lathe([(0.0, zz - 0.3), (0.38, zz), (0.0, zz + 0.4)], "M_WT_Beacon", 8, center=(mx, my, 0))
    for (sx, sy, h) in SMALL_MASTS:
        B.cyl((sx, sy, TOP), h, 0.28, "M_WT_MastWhite", 8)
        B.lathe([(0.0, TOP + h), (0.22, TOP + h + 0.2), (0.0, TOP + h + 0.45)], "M_WT_Beacon", 6, center=(sx, sy, 0))
    # rooftop equipment between the masts (low boxes on the deck)
    for (ex, ey, sx_, sy_, h) in ((-11.0, 0.0, 6.0, 3.0, 2.2), (-16.0, -2.0, 3.0, 2.0, 1.6)):
        B.boxmm((ex - sx_ / 2, ey - sy_ / 2, TOP), (ex + sx_ / 2, ey + sy_ / 2, TOP + h), "M_WT_DrumMetal")
    ob = B.finish("WT_Top")
    export("WT_Top", [ob], {"what": "the two masts (west 527.3 m, east 521.2 m), six smaller masts, base frames, red beacons; NO collision"})


# ------------------------------------------------------------------ the Ledge (visible)
def ledge_boxes():
    """(x_out, x_in, y0, y1, z0, z1) per box, tower frame: x_in is the west face (cover surface)."""
    out = []
    for yc in LEDGE["bays"]:
        out.append((-OUT_FACE - LEDGE["d"], -OUT_FACE + GLASS_IN, yc - LEDGE["w"] / 2, yc + LEDGE["w"] / 2, LEDGE_FLOOR, LEDGE_FLOOR + LEDGE["h"]))
    return out


def ledge():
    B = TB()
    f = 0.10      # frame size
    for (xo, xi, y0, y1, z0, z1) in ledge_boxes():
        # glass floor (thin slab), walls and roof
        B.boxmm((xo, y0, z0 - 0.08), (xi, y1, z0), "M_WT_LedgeGlass")
        B.face([(xo, y0, z0), (xo, y1, z0), (xo, y1, z1), (xo, y0, z1)], "M_WT_LedgeGlass")
        B.face([(xo, y0, z1), (xo, y1, z1), (xo, y1, z0), (xo, y0, z0)], "M_WT_LedgeGlass")
        for yy, sgn in ((y0, -1), (y1, 1)):
            P = [(xo, yy, z0), (xi, yy, z0), (xi, yy, z1), (xo, yy, z1)]
            B.face(P if sgn < 0 else P[::-1], "M_WT_LedgeGlass")
            B.face(P[::-1] if sgn < 0 else P, "M_WT_LedgeGlass")
        B.face([(xo, y0, z1), (xi, y0, z1), (xi, y1, z1), (xo, y1, z1)], "M_WT_LedgeGlass")
        B.face([(xo, y1, z1), (xi, y1, z1), (xi, y0, z1), (xo, y0, z1)], "M_WT_LedgeGlass")
        # frame: the 8 outer edges and the attachment ring
        for a, b in (((xo, y0, z0), (xo, y1, z0)), ((xo, y0, z1), (xo, y1, z1)), ((xo, y0, z0), (xo, y0, z1)), ((xo, y1, z0), (xo, y1, z1)),
                     ((xo, y0, z0), (xi, y0, z0)), ((xo, y1, z0), (xi, y1, z0)), ((xo, y0, z1), (xi, y0, z1)), ((xo, y1, z1), (xi, y1, z1)),
                     ((xi, y0, z0), (xi, y0, z1)), ((xi, y1, z0), (xi, y1, z1))):
            B.beam(a, b, f, f, "M_WT_LedgeFrame")
        # the retracting-box housing: a dark steel sill under the floor
        B.boxmm((xi - 0.6, y0 - 0.15, z0 - 0.45), (xi, y1 + 0.15, z0 - 0.08), "M_WT_LedgeFrame")
    ob = B.finish("WT_Ledge")
    export("WT_Ledge", [ob], {"what": "four glass Ledge boxes, 103rd floor (412.4 m), west face of the west tube, bays 1 2 4 5; "
                                      "3.6 wide x 5.0 deep x 3.0 m; NO collision (WT_ColLedge)"})


# ------------------------------------------------------------------ the base (visible)
def base():
    B = TB()
    for nm, x0, x1, y0, y1, H, rm in PODIUM:
        edges = rect_edges(x0, x1, y0, y1)
        for en, A, Bp, n in edges:
            iv, horiz = edge_intervals(A, Bp, n, H)
            t = (Bp[0] - A[0], Bp[1] - A[1])
            Lr = math.hypot(*t)
            t = (t[0] / Lr, t[1] / Lr)
            for s0, s1, ho in iv:
                if ho >= H - 0.3:
                    continue
                pa = (s0, A[1]) if horiz else (A[0], s0)
                pb = (s1, A[1]) if horiz else (A[0], s1)
                if (pb[0] - pa[0]) * t[0] + (pb[1] - pa[1]) * t[1] < 0:
                    pa, pb = pb, pa
                zt = H - 0.8
                if zt > ho + 0.1:
                    # 1.5 m panels x 5 m storeys, in chunks of 12 panels so the half-float UVs stay small
                    L0 = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
                    nch = max(1, math.ceil(L0 / 18.0))
                    for c_ in range(nch):
                        q0 = (pa[0] + (pb[0] - pa[0]) * c_ / nch, pa[1] + (pb[1] - pa[1]) * c_ / nch)
                        q1 = (pa[0] + (pb[0] - pa[0]) * (c_ + 1) / nch, pa[1] + (pb[1] - pa[1]) * (c_ + 1) / nch)
                        ua = (q0[0] * t[0] + q0[1] * t[1]) / 1.5
                        ub = (q1[0] * t[0] + q1[1] * t[1]) / 1.5
                        uf = math.floor(ua)
                        B.face([(q0[0], q0[1], ho), (q1[0], q1[1], ho), (q1[0], q1[1], zt), (q0[0], q0[1], zt)], "M_WT_Podium",
                               [(ua - uf, ho / 5.0), (ub - uf, ho / 5.0), (ub - uf, zt / 5.0), (ua - uf, zt / 5.0)])
                B.face([(pa[0], pa[1], max(ho, zt)), (pb[0], pb[1], max(ho, zt)), (pb[0], pb[1], H), (pa[0], pa[1], H)], "M_WT_Alu")
                # vertical fins every 6 m (the Catalog's dark frame rhythm)
                L = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
                for k in range(1, int(L / 6.0) + 1):
                    s = k * L / (int(L / 6.0) + 1)
                    cx, cy = pa[0] + t[0] * s + n[0] * 0.15, pa[1] + t[1] * s + n[1] * 0.15
                    B.box((cx, cy, (ho + H) / 2), (abs(t[0]) * 0.35 + abs(n[0]) * 0.3, abs(t[1]) * 0.35 + abs(n[1]) * 0.3, H - ho), "M_WT_Alu")
        B.face([(x0, y0, H), (x1, y0, H), (x1, y1, H), (x0, y1, H)], rm)
        if rm == "M_WT_Lawn":     # roof-garden paths (a paver ring)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            r0, r1 = min(x1 - x0, y1 - y0) * 0.30, min(x1 - x0, y1 - y0) * 0.30 + 1.6
            for k in range(32):
                a0, a1 = 2 * math.pi * k / 32, 2 * math.pi * (k + 1) / 32
                B.face([(cx + r0 * math.cos(a0), cy + r0 * math.sin(a0), H + 0.03), (cx + r1 * math.cos(a0), cy + r1 * math.sin(a0), H + 0.03),
                        (cx + r1 * math.cos(a1), cy + r1 * math.sin(a1), H + 0.03), (cx + r0 * math.cos(a1), cy + r0 * math.sin(a1), H + 0.03)],
                       "M_WT_PodiumRoof")
    # atrium skylight: flat glass at 21 m with 4 m slopes down to the 20 m terrace on the E, W and S sides
    x0, x1, y0, y1, zl, zh = ATRIUM
    i = 4.0
    P = [(x0, y0, zl), (x1, y0, zl), (x1, y1, zl), (x0, y1, zl)]
    Q = [(x0 + i, y0 + i, zh), (x1 - i, y0 + i, zh), (x1 - i, y1, zh), (x0 + i, y1, zh)]
    B.face(Q, "M_WT_Skylight")
    B.face([P[0], P[1], Q[1], Q[0]], "M_WT_Skylight")
    B.face([P[1], P[2], Q[2], Q[1]], "M_WT_Skylight")
    B.face([P[3], P[0], Q[0], Q[3]], "M_WT_Skylight")
    for k in range(1, 8):            # skylight mullions
        xx = x0 + (x1 - x0) * k / 8
        B.box((xx, (y0 + y1) / 2, zh + 0.04), (0.12, y1 - y0 - 2 * i, 0.08), "M_WT_Alu")
    # forecourt paving (2 cm over the city's sidewalk blocks)
    for (fx0, fx1, fy0, fy1) in FORECOURTS:
        B.face([(fx0, fy0, 0.17), (fx1, fy0, 0.17), (fx1, fy1, 0.17), (fx0, fy1, 0.17)], "M_WT_Granite")
    # entrance canopies: Wacker (west of the pavilion) and Jackson (the visitors' entrance), dark steel and glass
    B.boxmm((-48.5, -8.0, 6.2), (-43.5, 8.0, 6.6), "M_WT_Alu")
    B.boxmm((-9.0, -76.6, 5.2), (9.0, -71.6, 5.6), "M_WT_Alu")
    ob = B.finish("WT_Base")
    export("WT_Base", [ob], {"what": "Catalog podium and wings (OSM building:part, simplified), roof terrace and garden, atrium "
                                     "skylight, forecourts, canopies; NO collision"})


# ------------------------------------------------------------------ colliders (hidden)
def lipped_block(W, R, rect, H, prof_name, wall_floor=None):
    """Walls on exposed edges (from the height outside up to H - Lz) + lips into W; the flat top (inset by D on exposed
    edges) into R. Returns the exposure flags."""
    x0, x1, y0, y1 = rect
    pts, D, Lz = profile(*PROF[prof_name])
    edges = rect_edges(x0, x1, y0, y1)
    info = []
    for en, A, Bp, n in edges:
        iv, horiz = edge_intervals(A, Bp, n, H)
        ex = [ho < H - 0.5 for _a, _b, ho in iv]
        if any(ex) and not all(ex):
            print(f"WARNING mixed exposure on {rect} edge {en}: {iv}")
        info.append((en, A, Bp, n, iv, horiz, sum(ex) * 2 > len(ex)))
    expo = [e[6] for e in info]
    for k, (en, A, Bp, n, iv, horiz, ex) in enumerate(info):
        # walls per interval (the outside height changes along an edge)
        for s0, s1, ho in iv:
            if ho >= H - 0.5:
                continue
            zt = H - Lz if ex else H
            if wall_floor is not None:
                ho = min(ho, wall_floor)
            if zt <= ho + 0.01:
                continue
            pa = (s0, A[1]) if horiz else (A[0], s0)
            pb = (s1, A[1]) if horiz else (A[0], s1)
            t = (Bp[0] - A[0], Bp[1] - A[1])
            if (pb[0] - pa[0]) * t[0] + (pb[1] - pa[1]) * t[1] < 0:
                pa, pb = pb, pa
            W.face([(pa[0], pa[1], ho), (pb[0], pb[1], ho), (pb[0], pb[1], zt), (pa[0], pa[1], zt)], "M_WT_Col")
        if not ex:
            continue
        L = math.hypot(Bp[0] - A[0], Bp[1] - A[1])
        t = ((Bp[0] - A[0]) / L, (Bp[1] - A[1]) / L)
        nin = (-n[0], -n[1])
        miter_a, miter_b = expo[k - 1], expo[(k + 1) % 4]
        rowA, rowB = [], []
        for d, h in pts:
            ta = d if miter_a else 0.0
            tb = d if miter_b else 0.0
            rowA.append(Vector((A[0] + t[0] * ta + nin[0] * d, A[1] + t[1] * ta + nin[1] * d, H + h)))
            rowB.append(Vector((Bp[0] - t[0] * tb + nin[0] * d, Bp[1] - t[1] * tb + nin[1] * d, H + h)))
        W.grid([rowA, rowB], "M_WT_Col", smooth=False)
    # flat top
    fx0 = x0 + (D if expo[3] else 0.0)
    fx1 = x1 - (D if expo[1] else 0.0)
    fy0 = y0 + (D if expo[0] else 0.0)
    fy1 = y1 - (D if expo[2] else 0.0)
    if fx1 - fx0 > 0.05 and fy1 - fy0 > 0.05:
        R.face([(fx0, fy0, H), (fx1, fy0, H), (fx1, fy1, H), (fx0, fy1, H)], "M_WT_Col")
    return {e[0]: e[6] for e in info}, D, Lz


def choose_profile(x0, x1, y0, y1, H, step):
    """The biggest lip that fits: its height under the smallest step, its depth inside the block (half of it when both
    opposite edges are lipped)."""
    ex = {}
    for en, A, Bp, n in rect_edges(x0, x1, y0, y1):
        iv, _h = edge_intervals(A, Bp, n, H)
        ex[en] = any(ho < H - 0.5 for _a, _b, ho in iv)
    room_x = (x1 - x0) / (2 if ex["W"] and ex["E"] else 1)
    room_y = (y1 - y0) / (2 if ex["S"] and ex["N"] else 1)
    for pn in ("big", "pod", "small"):
        _p, D, Lz = profile(*PROF[pn])
        if Lz < step - 0.5 and D <= min(room_x if (ex["W"] or ex["E"]) else 1e9, room_y if (ex["S"] or ex["N"]) else 1e9) + 1e-6:
            return pn
    return "small"


def prism(B, cx, cy, r0, r1, z0, z1, m, sides=8, top=None):
    """Tapered n-gon prism (sides only; the top cap goes to `top` if given)."""
    ring0 = [(cx + r0 * math.cos(2 * math.pi * (k + 0.5) / sides), cy + r0 * math.sin(2 * math.pi * (k + 0.5) / sides)) for k in range(sides)]
    ring1 = [(cx + r1 * math.cos(2 * math.pi * (k + 0.5) / sides), cy + r1 * math.sin(2 * math.pi * (k + 0.5) / sides)) for k in range(sides)]
    for k in range(sides):
        j = (k + 1) % sides
        B.face([(ring0[k][0], ring0[k][1], z0), (ring0[j][0], ring0[j][1], z0), (ring1[j][0], ring1[j][1], z1), (ring1[k][0], ring1[k][1], z1)], m)
    if top is not None:
        top.face([(p[0], p[1], z1) for p in ring1], m)


def collision():
    W, R, LD = TB(), TB(), TB()
    report = {"tower": {}, "podium": {}}
    for rect, H, nm in roof_groups():
        ex, D, Lz = lipped_block(W, R, rect, H, "big")
        report["tower"][nm] = {"H": round(H, 2), "exposed": ex, "lip_D": round(D, 2), "lip_Lz": round(Lz, 2)}
    for nm, x0, x1, y0, y1, H, _m in PODIUM:
        # profile by the smallest exposed step of the block
        steps = []
        for en, A, Bp, n in rect_edges(x0, x1, y0, y1):
            iv, _h = edge_intervals(A, Bp, n, H)
            steps += [H - ho for _a, _b, ho in iv if ho < H - 0.5]
        st = min(steps) if steps else 99
        pn = choose_profile(x0, x1, y0, y1, H, st)
        ex, D, Lz = lipped_block(W, R, (x0, x1, y0, y1), H, pn)
        report["podium"][nm] = {"H": H, "exposed": ex, "profile": pn, "min_step": round(st, 2)}
    # atrium: a low hip roof (20 m at the E, W, S edges, 21 m on top), all in the roofs collider
    x0, x1, y0, y1, zl, zh = ATRIUM
    i = 4.0
    P = [(x0, y0, zl), (x1, y0, zl), (x1, y1, zl), (x0, y1, zl)]
    Q = [(x0 + i, y0 + i, zh), (x1 - i, y0 + i, zh), (x1 - i, y1, zh), (x0 + i, y1, zh)]
    R.face(Q, "M_WT_Col")
    R.face([P[0], P[1], Q[1], Q[0]], "M_WT_Col")
    R.face([P[1], P[2], Q[2], Q[1]], "M_WT_Col")
    R.face([P[3], P[0], Q[0], Q[3]], "M_WT_Col")
    # drums: sides (walls) from below the roof, tops (roofs)
    for (dx, dy) in DRUMS:
        H = height_at(dx, dy)
        prism(W, dx, dy, DRUM_R, DRUM_R, H - 1.0, H + DRUM_H, "M_WT_Col", 16, top=R)
    # masts: tapered 8-gons (yes, the car can try to drive up them)
    for (mx, my, mz) in MASTS:
        prism(W, mx, my, 2.33, 0.6, TOP - 0.5, TOP + 70.0, "M_WT_Col", 8)
        prism(W, mx, my, 0.6, 0.25, TOP + 70.0, mz, "M_WT_Col", 8)
    # Ledge boxes: floor slab (closed) and side / front panes (closed slabs); open top so a car can drop in
    for (xo, xi, y0, y1, z0, z1) in ledge_boxes():
        xi_c = -OUT_FACE
        LD.boxmm((xo, y0, z0 - 0.3), (xi_c, y1, z0), "M_WT_Col")
        LD.boxmm((xo, y0, z0), (xo + 0.12, y1, z1), "M_WT_Col")
        LD.boxmm((xo, y0, z0), (xi_c, y0 + 0.1, z1), "M_WT_Col")
        LD.boxmm((xo, y1 - 0.1, z0), (xi_c, y1, z1), "M_WT_Col")
    for B_, name, what in ((W, "WT_ColWalls", "hidden collider: every wall face of the tower and podium + rounded lips at exposed roof edges + drum sides + masts"),
                           (R, "WT_ColRoofs", "hidden collider: flat tops (setbacks, 442 m roof, podium terraces, drum tops, atrium skylight)"),
                           (LD, "WT_ColLedge", "hidden collider: Ledge box floors and side/front panes (open top)")):
        ob = B_.finish(name, weld=True)
        export(name, [ob], {"what": what})
    META["_collision_report"] = report


# ------------------------------------------------------------------ willis.json
def write_json():
    path = BASE + "/willis.json"
    data = {}
    if os.path.exists(path):
        try:
            data = json.load(open(path))
        except Exception:
            data = {}
    assets = data.get("assets", {})
    rep = META.pop("_collision_report", None)
    assets.update(META)
    data["assets"] = dict(sorted(assets.items()))
    if rep:
        data["collision_report"] = rep
    pts, Dbig, Lbig = profile(*PROF["big"])
    data["frame"] = {
        "origin_plan_m": list(ORIGIN), "theta_deg": THETA_DEG,
        "note": "tower frame (x east, y north along the tower grid) -> plan: rotate by theta CCW, add origin; Unreal X = plan y*100, "
                "Y = plan x*100; the GLBs are already turned: place them at the origin with no rotation",
    }
    data["heights_m"] = {"roof_442": round(TOP, 2), "setback_90": round(H90, 2), "setback_66": round(H66, 2), "setback_50": round(H50, 2),
                         "skydeck_103": round(LEDGE_FLOOR, 2), "mast_west": MASTS[0][2], "mast_east": MASTS[1][2],
                         "floor_levels": FZ, "louvre_bands_floors": BANDS}
    data["lips"] = {k: {"R1": v[0], "R2": v[1], "R1_end_deg": v[2], "D": round(profile(*v)[1], 2), "Lz": round(profile(*v)[2], 2)} for k, v in PROF.items()}
    bx0, bx1, by0, by1 = BLOCK
    data["zone_plan"] = [list(to_plan(x, y)) for x, y in ((bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1))]
    tower_poly = [list(to_plan(x, y)) for x, y in ((-OUT_FACE, -OUT_FACE), (OUT_FACE, -OUT_FACE), (OUT_FACE, OUT_FACE), (-OUT_FACE, OUT_FACE))]
    data["tower_outline_plan"] = tower_poly

    def tp(x, y, dx, dy, z=1.0):
        p = to_plan(x, y)
        return {"local": [x, y], "plan": [round(p[0], 2), round(p[1], 2)], "ue_cm": [round(p[1] * 100), round(p[0] * 100), round(z * 100)],
                "yaw": round(heading(dx, dy), 2)}
    data["test_points"] = {
        "wacker_start": tp(-62.5, 0.0, 1, 0),                     # Wacker Drive northbound lanes (east of the Wacker Canal Expressway fill), facing the west face
        "forecourt": tp(-49.0, 0.0, 1, 0),
        "adams_start": tp(0.0, 62.0, 0, -1),                      # Adams St, facing the north face
        "roof_west_bay2": tp(-21.5, -4.572, -1, 0, TOP + 1.0),     # the roof, facing west over Ledge box 2
        "roof_centre": tp(-11.0, -4.0, 1, 0, TOP + 1.0),
        "ledge_box2": tp(-OUT_FACE - 2.6, -4.572, -1, 0, LEDGE_FLOOR + 1.0),
        "setback_N": tp(0.0, 20.0, 0, -1, H90 + 1.0),
        "setback_NW": tp(-20.0, 26.0, 0, -1, H50 + 1.0),         # NW setback, facing the west tube's north face
        "rocket_addon": tp(-11.0, 4.0, 0, 1, TOP + 1.2),
    }
    data["ledge_boxes"] = [{"centre_plan": list(map(lambda v: round(v, 2), to_plan((b[0] + b[1]) / 2, (b[2] + b[3]) / 2))), "floor_z_m": LEDGE_FLOOR,
                            "w": LEDGE["w"], "d": LEDGE["d"], "h": LEDGE["h"]} for b in ledge_boxes()]
    data["climbing_lane"] = "west face of the west tube, middle bay (tower-frame y = -2.3..2.3): street/Wacker forecourt -> 20 m " \
                            "pavilion -> 442 m roof with no Ledge box in the way; steer 4-5 m sideways near the top to miss the west mast"
    data["conventions"] = {"units": "metres in Blender/GLB; Unreal imports as centimetres", "generator": "Scripts/landmarks/blender_willis.py",
                           "facade_uv": "u = bays (4.572 m, integer at column lines), v = floors (integer at floor lines, real levels)"}
    json.dump(data, open(path, "w"), indent=1)
    print("wrote", path)


# ------------------------------------------------------------------ previews
def _import(name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=f"{BASE}/{name}.glb")
    return [o for o in bpy.data.objects if o not in before]


def _preview_materials(objs):
    """Swap the facade slots for preview materials that use the real tile textures, so the render shows the look."""
    def texmat(name, png, glass_rgb, frame_rgb, emit_lit=False):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(f"{TEXD}/{png}")
        tex.image.colorspace_settings.name = "Non-Color"
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(tex.outputs["Color"], sep.inputs[0])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["A"].default_value = (*frame_rgb, 1)
        mix.inputs["B"].default_value = (*glass_rgb, 1)
        nt.links.new(sep.outputs[0], mix.inputs["Factor"])
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
        rmix = nt.nodes.new("ShaderNodeMapRange")
        nt.links.new(sep.outputs[0], rmix.inputs["Value"])
        rmix.inputs["To Min"].default_value = 0.45
        rmix.inputs["To Max"].default_value = 0.06
        nt.links.new(rmix.outputs["Result"], bsdf.inputs["Roughness"])
        bsdf.inputs["Metallic"].default_value = 0.6
        return m
    cw = texmat("PV_CW", "T_WT_CurtainWall.png", (0.06, 0.05, 0.045), (0.015, 0.015, 0.017))
    lv = texmat("PV_LV", "T_WT_Louvre.png", (0.02, 0.02, 0.02), (0.03, 0.03, 0.032))
    pd = texmat("PV_PD", "T_WT_Podium.png", (0.08, 0.10, 0.12), (0.015, 0.015, 0.017))
    for o in objs:
        if o.type != "MESH":
            continue
        for i, m in enumerate(o.data.materials):
            if m is None:
                continue
            if m.name.startswith("M_WT_CurtainWall"):
                o.data.materials[i] = cw
            elif m.name.startswith("M_WT_SkydeckGlass"):
                o.data.materials[i] = cw
            elif m.name.startswith("M_WT_Louvre"):
                o.data.materials[i] = lv
            elif m.name.startswith("M_WT_Podium") and "Roof" not in m.name:
                o.data.materials[i] = pd


PREVIEWS = {
    # name: (camera location (plan-local metres, tower frame), look-at, lens, resolution, include colliders)
    "sw": ((-420.0, -560.0, 160.0), (0.0, 0.0, 230.0), 50, (1100, 1500), False),
    "west": ((-260.0, 10.0, 60.0), (0.0, 0.0, 250.0), 40, (1100, 1500), False),
    "top": ((-120.0, -90.0, 480.0), (-10.0, 0.0, 430.0), 45, (1500, 1100), False),
    "ledge": ((-70.0, -40.0, 420.0), (-36.0, 0.0, 412.0), 40, (1500, 1100), False),
    "base": ((-150.0, -170.0, 60.0), (-10.0, -20.0, 15.0), 35, (1500, 1000), False),
    "collision": ((-160.0, -120.0, 470.0), (-10.0, 0.0, 425.0), 40, (1500, 1100), True),
}


def render_previews(names):
    for name in (names or list(PREVIEWS)):
        loc, look, lens, res, col = PREVIEWS[name]
        BL.reset()
        BL._scene_setup()
        objs = []
        for a in ("WT_Tower", "WT_Top", "WT_Ledge", "WT_Base") + (("WT_ColWalls", "WT_ColRoofs", "WT_ColLedge") if col else ()):
            if os.path.exists(f"{BASE}/{a}.glb"):
                new = _import(a)
                objs += new
        _preview_materials(objs)
        if col:
            cm = bpy.data.materials.new("PV_Col")
            cm.use_nodes = True
            b = next(n for n in cm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            b.inputs["Base Color"].default_value = (0.9, 0.2, 0.8, 1)
            for o in objs:
                if o.name.startswith("WT_Col") and o.type == "MESH":
                    for i in range(len(o.data.materials)):
                        o.data.materials[i] = cm
                if o.name.startswith(("WT_Tower", "WT_Base")):
                    o.hide_render = True
        # the GLBs are in plan orientation turned -90 (Blender x = plan north): put the camera in the same frame
        def P(p):
            c, s = math.cos(TH), math.sin(TH)
            px, py = c * p[0] - s * p[1], s * p[0] + c * p[1]
            return Vector((py, -px, p[2]))
        bpy.ops.object.camera_add(location=P(loc))
        cam = bpy.context.object
        d = P(look) - P(loc)
        cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = lens
        cam.data.clip_end = 5000
        sc = bpy.context.scene
        sc.camera = cam
        sc.render.resolution_x, sc.render.resolution_y = res
        try:
            sc.render.engine = "BLENDER_EEVEE_NEXT"
        except TypeError:
            sc.render.engine = "BLENDER_EEVEE"
        try:
            sc.eevee.taa_render_samples = 16
        except Exception:
            pass
        sc.render.filepath = f"{BASE}/preview_{name}.png"
        bpy.ops.render.render(write_still=True)
        print("rendered", sc.render.filepath)


JOBS = {"textures": textures, "tower": tower, "top": top, "ledge": ledge, "base": base, "collision": collision}

if __name__ == "__main__":
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
