"""Sky City's elevated expressways, laid out offline: Interstate 35 (Austin upper deck) past the Capitol, and the Wacker
Canal Expressway (a Chicago steel viaduct). Writes Saved/Expressway/expressway_layout.json for the Blender kit
(Scripts/roads/blender_expressway_kit.py) and the Unreal placement (Scripts/roads/build_expressway_ue.py), plus
Saved/Expressway/expressway_footprint.json (deck, ramp-fill and column polygons, in l_footprint.json's format) for the
street builder, and debug maps Saved/Expressway/layout_*.png.

Why (20 Oct 2026, Kenny: "there's a weird structure that looks like a highway that runs past the capitol.. what is it? it
needs to be specific.. build it the way it looks in real life"): the two roads came from his 19 Oct sketch
(Scripts/mashup/apply_sketch.py) and build_city.py's "elevated" stage drew them as one generic slab on 2.2 m box pillars
every 40 m: pillars stood in streets, the 150 m ramps crossed Guadalupe, Trinity and three Wacker junctions 2-5 m up
(walls across the lanes), and I-35's west end hung 39 m past the edge of the land. Kenny confirmed: the road past the
Capitol is Austin's I-35 upper deck, accurate to real life; the Wacker one gets the matching Chicago look.

Plan frame: metres, x east, y north; Unreal X = y*100, Y = x*100, z up. s runs along each road from its first end.
What it decides, per road:
  alignment  the plan centreline, resampled at 2 m and smoothed (Gaussian, sigma 12 m: the sketch scribble had 2-4 m
             wiggles no interstate has), within a few metres of the plan line; ends extended or trimmed so they meet the
             street network (I-35: east over the 15th St cluster and Canal St to grade on the Eisenhower's line before
             the South Branch; west to grade at the land edge)
  profile    deck top (road surface) z(s): full height in the middle, ramps of at most STYLE grade with parabolic vertical
             curves (a box filter of a piecewise-linear grade line), never below the clearance over a street it crosses
  structure  "fill" where the deck is low (retained earth between precast panel walls, like TxDOT's MSE approach ramps),
             an abutment where the bridge starts, then spans between bents. Every bent is chosen against the ground:
             a single-column hammerhead (Austin) / multi-column bent (Chicago) when its columns stand clear of pavement,
             sidewalks, water, buildings, landmark keep-outs and street furniture; otherwise a straddle bent with its
             columns outside the pavement and a long cap over it; span lengths by dynamic programming (target ~30 m,
             18-40 m prestressed I-girders, up to 55 m as steel plate girders)
  furniture  light poles (on the median barrier, twin arms), overhead sign bridges with their sign faces, expansion
             joints at every bent (simple spans, as the 1970s decks were built), deck drains
  checks     clearance under the superstructure over every street it crosses, columns vs everything, the deck vs
             buildings, trees and lamps under the deck (listed for the street builder in the footprint file)
Inputs (read-only): Saved/Mashup/plan_v3.json, Saved/Roads/roadnet.json, Saved/Roads/placed_props.json (what is placed in
the level), Saved/Expressway/probe.json (buildings, water, landmark pieces traced in the level by
Scripts/roads/expressway_probe_ue.py), SourceArt/Landmarks/capitol/capitol.json (keep-outs), Saved/Mashup/buildings_v3.json.
Run: python3 -I Scripts/roads/expressway_layout.py [i35] [wacker]       (no argument = both)
(20 Oct 2026, agent highway-capitol)
"""
import collections, json, math, pathlib, sys, time
import numpy as np
from PIL import Image, ImageDraw
from skimage.measure import points_in_poly

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUTD = ROOT / "Saved/Expressway"
OUTD.mkdir(parents=True, exist_ok=True)
PLAN = json.load(open(ROOT / "Saved/Mashup/plan_v3.json"))
RN = json.load(open(ROOT / "Saved/Roads/roadnet.json"))
# seam-junctions' next street network (Saved/Roads/wip/roadnet.json, with this layout's requests in it): columns must
# clear both the live pavement and the coming one, so the structure stays valid across their rebuild
_wip = ROOT / "Saved/Roads/wip/roadnet.json"
RN_WIP = json.load(open(_wip)) if _wip.exists() and "--no-wip" not in sys.argv else None
BLD = json.load(open(ROOT / "Saved/Mashup/buildings_v3.json"))["buildings"]
CAP = json.load(open(ROOT / "SourceArt/Landmarks/capitol/capitol.json"))["layout"]
_pp = ROOT / "Saved/Roads/placed_props.json"
PROPS = json.load(open(_pp))["inst"] if _pp.exists() else {}
_pr = OUTD / "probe.json"
PROBE = json.load(open(_pr)) if _pr.exists() else None
ONLY = [a for a in sys.argv[1:] if not a.startswith("-")]
stats = collections.Counter()
issues = []

# ------------------------------------------------------------------------------------------------ styles
# Dimensions in metres. Sources and what is estimated: Saved/Expressway notes + NOTES/highway-capitol-2026-10-20.md.
STYLES = {
    "austin": {   # I-35 upper decks, central Austin (built 1972-76), as they stood before the Capital Express Central rebuild
        "name": "I-35 upper deck (TxDOT, 1970s)",
        "twin": True, "deck_gap": 1.2,       # one deck per direction (NBI: SB 12.7 m, NB 13.3 m), side by side here
        "lanes_per_dir": 2, "lane_w": 3.66,  # 12 ft lanes (NBI / TTI; KUT: the rebuild narrows them to 11 ft)
        "shoulder_out": 3.05, "shoulder_in": 1.52,   # ~10 ft / ~4-5 ft (estimated from the 41.7 ft deck)
        "rail_w": 0.38, "rail_h": 0.84, "fascia": 0.15,   # open concrete post-and-beam rail (photos), ~33 in
        "deck_top": 8.5,                     # road surface above grade (girders ~7.2 m up; photos: deck 8-9 m up)
        "slab": 0.19, "haunch": 0.05,
        "girders_per_deck": 7,               # ~7 prestressed I-girder lines per deck (photos, NBI: prestressed I)
        "girder_types": [[32.0, "txdot_c", 1.016], [41.5, "txdot_iv", 1.372], [70.0, "steel_plate", 2.0]],
        "girder": "txdot_c", "girder_d": 1.016,
        "cap_d": 1.68, "cap_d_tip": 1.07, "cap_w": 1.52,   # hammerhead cap: deep at the column, tapered tips
        "col": (1.83, 1.22),                 # rectangular column, across x along (photos/estimate ~1.2 x 2 m)
        "straddle_col": (1.37, 1.37),
        "grade": 0.06, "vc": 40.0, "clear_min": 5.03,      # 16.5 ft TxDOT minimum vertical clearance
        "span": (18.0, 28.0, 41.5, 60.0),    # NBI: longest span 41.1 m; typical ~25-35 m
        "fill_below": 5.4,                   # deck top below this: retained-earth (MSE) fill, not spans
        "light_every": 61.0, "light_h": 12.2, "light_arm": 3.66,   # 40 ft davit poles, 12 ft arms
    },
    "chicago": {  # IDOT expressway viaduct (Dan Ryan / Ohio feeder / Stevenson, 1950s-60s steel and concrete)
        "name": "IDOT steel viaduct",
        "twin": False, "deck_gap": 0.0,
        "lanes_per_dir": 2, "lane_w": 3.66, "shoulder_out": 0.6, "shoulder_in": 0.3,   # old viaducts: next to no shoulders
        "rail_w": 0.53, "rail_h": 0.95, "fascia": 0.1, "median_w": 0.61,
        "cols_in_parking": True,             # columns may stand in parking lanes / at the curb (like the L on Wells)
        "piers_in_water": True,              # river piers, as on the Chicago viaducts over the South Branch
        "deck_top": 7.6, "slab": 0.22, "haunch": 0.08,
        "girders_per_deck": 8, "girder_types": [[70.0, "steel_plate", 1.5]], "girder": "steel_plate", "girder_d": 1.5,
        "cap_d": 1.5, "cap_d_tip": 1.5, "cap_w": 1.5, "col": (0.91, 0.91), "straddle_col": (1.07, 1.07),
        "grade": 0.065, "vc": 30.0, "clear_min": 4.42, "span": (16.0, 26.0, 40.0, 60.0),
        "fill_below": 5.0, "light_every": 55.0, "light_h": 12.2, "light_arm": 3.0,
    },
}


def deck_width(st):
    """Out-to-out width of one deck (twin: one direction; single: both directions with a median barrier)."""
    one = st["fascia"] + st["rail_w"] + st["shoulder_out"] + st["lanes_per_dir"] * st["lane_w"] + st["shoulder_in"]
    if st["twin"]:
        return one + st["rail_w"] + st["fascia"]
    return 2 * one + st["median_w"]


for _st in STYLES.values():
    _st["deck_w"] = round(deck_width(_st), 3)
    _st["decks"] = ([round(_st["deck_gap"] / 2 + _st["deck_w"] / 2, 3), -round(_st["deck_gap"] / 2 + _st["deck_w"] / 2, 3)]
                    if _st["twin"] else [0.0])                  # deck centre offsets (+ = left of +s travel)
    _st["total_w"] = round(_st["deck_w"] * len(_st["decks"]) + _st["deck_gap"], 3)
    _st["sup_d"] = round(_st["slab"] + _st["haunch"] + _st["girder_d"], 3)       # top of deck to bottom of beams

# ------------------------------------------------------------------------------------------------ roads
ROADS = {
    "i35": {
        "names": ["Interstate 35", "Ida B. Wells Expressway"], "style": "austin", "label": "Interstate 35",
        # east end: over the 15th St / Eisenhower cluster and Canal St, down to grade on the Eisenhower's line in the
        # empty block west of the South Branch (the street builder continues it east over the river to Wacker Drive)
        "prepend": [(-846.0, -1320.5), (-900.0, -1320.5), (-960.0, -1320.3), (-1005.0, -1319.0)],
        "trim_x_min": -1877.0,              # west end: the land ends at the plan bounds
        "ends": ("grade", "grade"),
        # (plan x, lateral metres, + = left of +s travel = south here): off West/East 14th St's south sidewalk, so the
        # north deck's columns stand behind the sidewalk and the west ramp's fill clears it (plan line +-9 m)
        "offsets": [(-1060.0, 0.0), (-1100.0, 3.0), (-1140.0, 5.5), (-1230.0, 5.5), (-1300.0, 3.0), (-1360.0, 1.0),
                    (-1590.0, 1.0), (-1650.0, 3.5), (-1720.0, 6.0), (-1790.0, 8.5), (-1877.0, 8.5)],
        "signs": "i35", "publish": True,
    },
    "wacker": {
        "names": ["Wacker Canal Expressway"], "style": "chicago", "label": "Wacker Canal Expressway",
        # south end: down to grade between South Wacker Drive's two carriageways (x -758 / -738), from Van Buren south to
        # just short of Jackson, like the real ramps between Upper and Lower Wacker; north end: into the Crosstown Parkway /
        # West 5th St pair at the plan's end, the way the Ohio Street feeder comes down into Ohio Street
        "prepend": [(-748.0, -1033.0), (-748.0, -990.0), (-748.3, -945.0), (-749.5, -912.0), (-752.0, -893.0)],
        # the plan's last 72 m ran inside the Crosstown Parkway: the ramp now touches down ~10 m short of its south edge
        # and meets it at grade (a short connector + T junction, requested from the street builder)
        "trim_end_m": 78.0,
        "trim_x_min": None, "ends": ("grade", "grade"),
        "offsets": [(-600.0, 0.0), (-575.0, 5.0), (-500.0, 5.0)],    # last stretch 5 m west, off the creek bank and the bridge tender house
        "signs": "wacker",
        "publish": True,         # ends agreed with seam-junctions (their note, 01:16)
    },
}


# ------------------------------------------------------------------------------------------------ geometry
def unit(v):
    L = math.hypot(v[0], v[1]) or 1e-12
    return (v[0] / L, v[1] / L)


def left(t):
    return (-t[1], t[0])


def cumlen(pts):
    s = [0.0]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + math.dist(a, b))
    return s


def resample(pts, step):
    s = cumlen(pts)
    n = max(2, int(round(s[-1] / step)) + 1)
    out = []
    j = 0
    for k in range(n):
        d = s[-1] * k / (n - 1)
        while j < len(pts) - 2 and s[j + 1] < d:
            j += 1
        seg = (s[j + 1] - s[j]) or 1e-9
        t = (d - s[j]) / seg
        out.append((pts[j][0] + (pts[j + 1][0] - pts[j][0]) * t, pts[j][1] + (pts[j + 1][1] - pts[j][1]) * t))
    return out


def gauss_smooth(pts, sigma_m, step):
    """Gaussian smoothing of a polyline sampled every `step` m; the ends are pinned by odd reflection (keeps end tangents)."""
    P = np.array(pts, float)
    r = int(3 * sigma_m / step)
    if r < 1 or len(P) < 5:
        return pts
    k = np.exp(-0.5 * (np.arange(-r, r + 1) * step / sigma_m) ** 2)
    k /= k.sum()
    head = 2 * P[0] - P[1:r + 1][::-1]
    tail = 2 * P[-1] - P[-r - 1:-1][::-1]
    Q = np.vstack([head, P, tail])
    out = np.stack([np.convolve(Q[:, i], k, mode="valid") for i in range(2)], 1)
    return [tuple(p) for p in out]


def closest(pts, p):
    best = (1e18, 0, 0.0)
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy or 1e-12
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
        d = math.dist(p, (a[0] + dx * t, a[1] + dy * t))
        if d < best[0]:
            best = (d, i, t)
    return best


def rect(c, t, w_across, l_along):
    n = left(t)
    hw, hl = w_across / 2, l_along / 2
    return [(c[0] + t[0] * sl + n[0] * sw, c[1] + t[1] * sl + n[1] * sw) for sl, sw in ((-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw))]


# ------------------------------------------------------------------------------------------------ ground raster
PAVE, WALK, PARKWAY, BUILD, WATER, KEEP, OBST, PARK = 1, 2, 4, 8, 16, 32, 64, 128   # PARK: a parking lane (on PAVE)
RES = 0.5


class Ground:
    """Bit raster (RES m) of what is on the ground round a road, from roadnet.json, the plan and the level probe."""

    def __init__(self, box):
        self.x0, self.y0, self.x1, self.y1 = box
        self.nx = int((self.x1 - self.x0) / RES) + 1
        self.ny = int((self.y1 - self.y0) / RES) + 1
        self.bits = np.zeros((self.ny, self.nx), np.uint8)
        self.props = []        # (x, y, kind, radius)

    def _px(self, p):
        return ((p[0] - self.x0) / RES, (self.y1 - p[1]) / RES)

    def paint(self, polys, bit):
        im = Image.new("L", (self.nx, self.ny), 0)
        d = ImageDraw.Draw(im)
        n = 0
        for r in polys:
            if r is None or len(r) < 3:
                continue
            xs = [p[0] for p in r]; ys = [p[1] for p in r]
            if max(xs) < self.x0 or min(xs) > self.x1 or max(ys) < self.y0 or min(ys) > self.y1:
                continue
            d.polygon([self._px(p) for p in r], fill=1)
            n += 1
        a = np.array(im, np.uint8)
        self.bits |= (a * bit).astype(np.uint8)
        return n

    def clear_bits(self, polys, bit):
        im = Image.new("L", (self.nx, self.ny), 0)
        d = ImageDraw.Draw(im)
        for r in polys:
            if r and len(r) >= 3:
                d.polygon([self._px(p) for p in r], fill=1)
        a = np.array(im, bool)
        self.bits[a] &= np.uint8(255 - bit)

    def at(self, p):
        i = int(round((p[0] - self.x0) / RES)); j = int(round((self.y1 - p[1]) / RES))
        if 0 <= i < self.nx and 0 <= j < self.ny:
            return int(self.bits[j, i])
        return 0

    def poly_values(self, poly):
        """The raster values under a polygon (numpy array)."""
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        i0 = max(0, int((min(xs) - self.x0) / RES)); i1 = min(self.nx - 1, int((max(xs) - self.x0) / RES) + 1)
        j0 = max(0, int((self.y1 - max(ys)) / RES)); j1 = min(self.ny - 1, int((self.y1 - min(ys)) / RES) + 1)
        if i1 < i0 or j1 < j0:
            return np.zeros(1, np.uint8)
        ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1))
        pts = np.stack([self.x0 + ii.ravel() * RES, self.y1 - jj.ravel() * RES], 1)
        inside = points_in_poly(pts, np.array(poly, float))
        if not inside.any():
            c = (sum(xs) / len(xs), sum(ys) / len(ys))
            return np.array([self.at(c)], np.uint8)
        return self.bits[jj.ravel()[inside], ii.ravel()[inside]]

    def poly_bits(self, poly):
        """OR of all bits under a polygon (sampled at the raster resolution)."""
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        i0 = max(0, int((min(xs) - self.x0) / RES)); i1 = min(self.nx - 1, int((max(xs) - self.x0) / RES) + 1)
        j0 = max(0, int((self.y1 - max(ys)) / RES)); j1 = min(self.ny - 1, int((self.y1 - min(ys)) / RES) + 1)
        if i1 < i0 or j1 < j0:
            return 0
        ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1))
        pts = np.stack([self.x0 + ii.ravel() * RES, self.y1 - jj.ravel() * RES], 1)
        inside = points_in_poly(pts, np.array(poly, float))
        if not inside.any():
            c = (sum(xs) / len(xs), sum(ys) / len(ys))
            return self.at(c)
        v = self.bits[jj.ravel()[inside], ii.ravel()[inside]]
        return int(np.bitwise_or.reduce(v))

    def props_near(self, p, r, kinds=None):
        out = []
        for q in self.props:
            if kinds and q[2] not in kinds:
                continue
            if abs(q[0] - p[0]) < r + q[3] and abs(q[1] - p[1]) < r + q[3] and math.dist(p, q[:2]) < r + q[3]:
                out.append(q)
        return out


TREES = ("RProps_liveoak", "RProps_elm", "RProps_linden", "RProps_honeylocust")
UPRIGHT = ("RProps_lamp", "RProps_lamp_hw", "RProps_pole", "RProps_post", "RProps_ped", "RProps_pedpost", "RProps_cabinet",
           "RProps_namepost", "RProps_hydrant", "RProps_bin", "RProps_busstop", "RProps_shelter", "RProps_mailbox",
           "RProps_dumpster", "RProps_bench", "RProps_rack", "RProps_blade", "RProps_barricade")
TREE_CROWN = {"RProps_liveoak": 7.5, "RProps_elm": 6.0, "RProps_linden": 4.0, "RProps_honeylocust": 5.0}
TREE_H = {"RProps_liveoak": 9.0, "RProps_elm": 14.0, "RProps_linden": 12.5, "RProps_honeylocust": 12.0}


def build_ground(box):
    G = Ground(box)
    for net in [RN] + ([RN_WIP] if RN_WIP else []):
        paint_net(G, net)
    G.paint(RN["parkway"], PARKWAY)
    return finish_ground(G, box)


def paint_net(G, RN):
    ribbons = [e["ribbon"] for e in RN["edges"] if e.get("ribbon")]
    stats["ground_pave_polys"] += G.paint(ribbons + [J["ring"] for J in RN["junctions"]] + list(RN["joints"]), PAVE)
    # parking lanes (columns may stand in them for styles that allow it, as the L does): strips along each ribbon side
    strips = []
    for e in RN["edges"]:
        rb = e.get("ribbon")
        el = e.get("elems") or []
        if not rb or len(rb) % 2 or not el:
            continue
        n = len(rb) // 2
        Lb, Rb = rb[:n], rb[n:][::-1]
        W = e["width"] or 1.0
        lp = 0.0
        for k, w, d in el:
            if k != "parking":
                break
            lp += w
        rp = 0.0
        for k, w, d in reversed(el):
            if k != "parking":
                break
            rp += w
        if lp > 0:
            inner = [(a[0] + (b[0] - a[0]) * lp / W, a[1] + (b[1] - a[1]) * lp / W) for a, b in zip(Lb, Rb)]
            strips.append(list(Lb) + inner[::-1])
        if rp > 0:
            inner = [(b[0] + (a[0] - b[0]) * rp / W, b[1] + (a[1] - b[1]) * rp / W) for a, b in zip(Lb, Rb)]
            strips.append(list(Rb) + inner[::-1])
    G.paint(strips, PARK)
    G.clear_bits([J["ring"] for J in RN["junctions"]] + list(RN["joints"]), PARK)
    G.paint(RN["walk"], WALK)


def finish_ground(G, box):
    G.paint(PLAN["water"]["outer"], WATER)
    G.clear_bits(PLAN["water"]["inner"], WATER)
    rects = []
    for b in BLD:
        a = math.radians(b["yaw"]); c, s = math.cos(a), math.sin(a)
        rects.append([(b["x"] + c * i * b["w"] / 2 - s * j * b["d"] / 2, b["y"] + s * i * b["w"] / 2 + c * j * b["d"] / 2)
                      for i, j in ((1, 1), (1, -1), (-1, -1), (-1, 1))])
    G.paint(rects + [lm.get("outline") for lm in PLAN["landmarks"] if lm.get("outline")], BUILD)
    G.paint(CAP.get("keepouts_plan", []), KEEP)
    for ring in CAP.get("keepout_rings_plan", []):
        G.paint([ring[0]] if ring and isinstance(ring[0][0], list) else [ring], KEEP)
    if PROBE:
        st = PROBE["step"]
        labels = PROBE["labels"]
        for g in PROBE["grids"].values():
            for j, (ra, rz) in enumerate(zip(g["a"], g["z"])):
                y = g["y0"] + j * st
                for i, (a, z) in enumerate(zip(ra, rz)):
                    if a < 0:
                        continue
                    lab = labels[a]
                    x = g["x0"] + i * st
                    sq = [(x - st / 2, y - st / 2), (x + st / 2, y - st / 2), (x + st / 2, y + st / 2), (x - st / 2, y + st / 2)]
                    if lab == "WaterSurfaceCollision" or lab == "Water":
                        G.paint([sq], WATER)
                    elif z > 60 and lab == "BuildingCollision":
                        G.paint([sq], BUILD)
                    elif z > 60 and not lab.startswith(("R2", "Ground", "Roads_", "Parks", "SM_")):
                        G.paint([sq], OBST)
    for k, rows in PROPS.items():
        if k not in TREES and k not in UPRIGHT:
            continue
        for v in rows:
            x, y = v[1] / 100.0, v[0] / 100.0
            if box[0] - 20 < x < box[2] + 20 and box[1] - 20 < y < box[3] + 20:
                if k in TREES:
                    G.props.append((x, y, k, TREE_CROWN[k] * max(v[4], 0.5)))
                else:
                    G.props.append((x, y, k, 0.6))
    return G


# ------------------------------------------------------------------------------------------------ alignment
def plan_road(names):
    for nm in names:
        rs = [r for r in PLAN["roads"] if r.get("name") == nm and r.get("elevated")]
        if rs:
            return rs[0]
    raise SystemExit(f"no elevated plan road named {names}")


def alignment(key, cfg):
    r = plan_road(cfg["names"])
    pts = [tuple(p) for p in r["pts"]]
    raw = list(pts)
    pts = list(cfg["prepend"]) + pts
    if cfg.get("trim_x_min") is not None:
        cut = []
        for a, b in zip(pts, pts[1:]):
            cut.append(a)
            if (a[0] - cfg["trim_x_min"]) * (b[0] - cfg["trim_x_min"]) < 0:
                t = (cfg["trim_x_min"] - a[0]) / (b[0] - a[0])
                cut.append((cfg["trim_x_min"], a[1] + (b[1] - a[1]) * t))
                break
        else:
            cut.append(pts[-1])
        pts = cut
    if cfg.get("trim_end_m"):
        sc = cumlen(pts)
        keep = sc[-1] - cfg["trim_end_m"]
        cut = [p for p, sv in zip(pts, sc) if sv < keep]
        i = len(cut)
        a, b = pts[i - 1], pts[i]
        f = (keep - sc[i - 1]) / ((sc[i] - sc[i - 1]) or 1e-9)
        pts = cut + [(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)]
    pts = resample(pts, 2.0)
    pts = gauss_smooth(pts, 12.0, 2.0)
    pts = gauss_smooth(pts, 12.0, 2.0)
    pts = resample(pts, 2.0)
    # lateral offsets keyed by plan x (I-35 runs east-west), blended linearly
    if cfg["offsets"]:
        ox = sorted(cfg["offsets"])
        out = []
        for i, p in enumerate(pts):
            a = pts[max(0, i - 1)]; b = pts[min(len(pts) - 1, i + 1)]
            n = left(unit((b[0] - a[0], b[1] - a[1])))
            xs = [o[0] for o in ox]; ds = [o[1] for o in ox]
            d = float(np.interp(p[0], xs, ds))
            out.append((p[0] + n[0] * d, p[1] + n[1] * d))
        pts = gauss_smooth(out, 10.0, 2.0)
    devs = []
    for p in pts[::5]:
        d, i, f = closest(raw, p)
        if 0 < i < len(raw) - 2 or (i == 0 and f > 0.0 and d < 30):
            devs.append(d)
    dev = max(devs) if devs else 0.0
    return pts, raw, round(dev, 2), r


# ------------------------------------------------------------------------------------------------ profile
def profile(s_tot, ends, st, z_req):
    """Deck-top heights every 2 m: a piecewise-linear grade line (full height between ramps of the style's grade, 0 at
    'grade' ends) box-filtered over the vertical-curve length, raised where a crossing needs more clearance."""
    H, G, VC = st["deck_top"], st["grade"], st["vc"]
    n = int(round(s_tot / 2.0)) + 1
    s = np.linspace(0, s_tot, n)
    lo = VC / 2 if ends[0] == "grade" else -1e9          # touchdown at the very end after filtering
    hi = s_tot - VC / 2 if ends[1] == "grade" else 1e9
    raw = np.minimum(H, np.minimum(G * (s - lo + VC / 2), G * (hi + VC / 2 - s)))
    raw = np.maximum(raw, 0.0)
    pad = int(VC / 4)
    ext = np.concatenate([np.full(pad, raw[0] if ends[0] != "grade" else 0.0), raw, np.full(pad, raw[-1] if ends[1] != "grade" else 0.0)])
    k = np.ones(2 * pad + 1) / (2 * pad + 1)
    z = np.convolve(ext, k, mode="valid")
    if ends[0] == "grade":
        z[0] = 0.0
    if ends[1] == "grade":
        z[-1] = 0.0
    return s, z


# ------------------------------------------------------------------------------------------------ bents
def street_crossings(G, pts, s, half_w):
    """Station ranges where pavement or sidewalk lies under the deck (for clearance and spans)."""
    under = []
    for i, p in enumerate(pts):
        a = pts[max(0, i - 1)]; b = pts[min(len(pts) - 1, i + 1)]
        n = left(unit((b[0] - a[0], b[1] - a[1])))
        bits = 0
        for k in np.linspace(-half_w, half_w, 13):
            bits |= G.at((p[0] + n[0] * k, p[1] + n[1] * k))
        under.append(bits)
    return under


def col_ok(G, c, t, size, margin=0.75, parking=False, water=False):
    """A column footing is fine if nothing paved, walked, wet, built or kept out lies under it (+margin) and no upright
    prop or tree trunk stands within 1.2 m of it. parking=True: a parking lane is fine (never a travel lane)."""
    poly = rect(c, t, size[0] + 2 * margin, size[1] + 2 * margin)
    v = G.poly_values(poly)
    bits = int(np.bitwise_or.reduce(v))
    if bits & (WALK | BUILD | KEEP | OBST | (0 if water else WATER)):
        return False, bits
    if bits & PAVE:
        if not parking:
            return False, bits
        if np.any((v & PAVE).astype(bool) & ~((v & PARK).astype(bool))):
            return False, bits
    for q in G.props_near(c, max(size) / 2 + 1.2):
        if q[2] in TREES:
            if math.dist(c, q[:2]) < max(size) / 2 + 1.5:
                return False, -1
        else:
            return False, -2
    return True, bits


def bent_options(G, st, p, t):
    """Options for a bent at p (road centre, tangent t). Austin: one single-column hammerhead per deck, the column under
    its deck's centre (up to 1.2 m eccentric). Chicago: a cap beam on three (or two) round columns. Either way, when no
    column spot is clear, a straddle bent: one column each side outside everything paved, a long cap under all decks."""
    n = left(t)
    opts = []
    if st["girder"] == "steel_plate":
        w = st["deck_w"] / 2 - 2.2
        for offs in ((-w, 0.0, w), (-w, w), (-w + 1.5, w - 1.5), (-w - 1.5, w + 1.5)):
            cols = []
            for o in offs:
                got = None
                for e in (0.0, 0.8, -0.8, 1.6, -1.6):
                    c = (p[0] + n[0] * (o + e), p[1] + n[1] * (o + e))
                    if col_ok(G, c, t, st["col"], margin=0.4, parking=st.get("cols_in_parking", False), water=st.get("piers_in_water", False))[0]:
                        got = o + e
                        break
                if got is None:
                    cols = None
                    break
                cols.append(got)
            if cols:
                opts.append({"type": "multi", "offs": cols, "cost": 0.0 if len(cols) == 3 else 0.4})
                break
    else:
        offs = []
        for dc in st["decks"]:
            got = None
            for e in (0.0, 0.6, -0.6, 1.2, -1.2):
                c = (p[0] + n[0] * (dc + e), p[1] + n[1] * (dc + e))
                if col_ok(G, c, t, st["col"])[0]:
                    got = dc + e
                    break
            if got is None:
                offs = None
                break
            offs.append(got)
        if offs:
            opts.append({"type": "hammer", "offs": offs, "cost": 0.4 * sum(abs(o - d) for o, d in zip(offs, st["decks"]))})
    outer = st["total_w"] / 2
    left_c = right_c = None
    pk = st.get("cols_in_parking", False)
    for o in np.arange(outer - 2.0, outer + 26.01, 0.5):
        c = (p[0] + n[0] * o, p[1] + n[1] * o)
        if col_ok(G, c, t, st["straddle_col"], parking=pk)[0]:
            left_c = float(o)
            break
    for o in np.arange(outer - 2.0, outer + 26.01, 0.5):
        c = (p[0] - n[0] * o, p[1] - n[1] * o)
        if col_ok(G, c, t, st["straddle_col"], parking=pk)[0]:
            right_c = -float(o)
            break
    if left_c is not None and right_c is not None and left_c - right_c <= 62.0:
        cap = left_c - right_c
        # caps up to ~45 m in post-tensioned concrete; longer ones are steel box caps (cost more, used only when needed)
        opts.append({"type": "straddle", "offs": [right_c, left_c], "cap": "concrete" if cap <= 45.0 else "steel_box",
                     "cost": 2.0 + 0.05 * max(0.0, cap - 2 * outer) + (4.0 if cap > 45.0 else 0.0)})
    return opts


def place_bents(G, st, pts, s, z, s_from, s_to):
    """Dynamic programming over 1 m stations between two fixed supports (abutments)."""
    smin, starget, smax_pc, smax_st = st["span"]
    S = np.arange(math.ceil(s_from), math.floor(s_to) + 1, 1.0)
    cand = {}
    for sv in S:
        if sv - s_from < smin * 0.6 or s_to - sv < smin * 0.6:
            continue
        p, t = at(pts, s, sv)
        o = bent_options(G, st, p, t)
        if o:
            cand[float(sv)] = min(o, key=lambda q: q["cost"])
    nodes = [float(s_from)] + sorted(cand) + [float(s_to)]
    best = {nodes[0]: (0.0, None)}
    for j, b in enumerate(nodes[1:], 1):
        bc = None
        for a in nodes[:j][::-1]:
            L = b - a
            if L > smax_st:
                break
            if L < smin and not (a == nodes[0] or b == nodes[-1]):
                continue
            if a not in best:
                continue
            c = best[a][0] + ((L - starget) / 10.0) ** 2 + (3.0 if L > smax_pc else 0.0) + (cand[b]["cost"] if b in cand else 0.0)
            if bc is None or c < bc[0]:
                bc = (c, a)
        if bc:
            best[b] = bc
    if nodes[-1] not in best:
        issues.append({"kind": "no_bent_chain", "s_from": s_from, "s_to": s_to})
        return []
    chain, k = [], nodes[-1]
    while best[k][1] is not None:
        k = best[k][1]
        if k != nodes[0]:
            chain.append(k)
    chain = sorted(chain)
    return [dict(s=sv, **cand[sv]) for sv in chain]


def at(pts, s_arr, sv):
    i = int(min(len(pts) - 2, max(0, np.searchsorted(s_arr, sv) - 1)))
    a, b = pts[i], pts[i + 1]
    seg = (s_arr[i + 1] - s_arr[i]) or 1e-9
    f = (sv - s_arr[i]) / seg
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f), unit((b[0] - a[0], b[1] - a[1]))


def z_at(s_arr, z_arr, sv):
    return float(np.interp(sv, s_arr, z_arr))


# Overhead guide signs per road: (direction, 0 = first sign bridge the traffic meets, 1 = second) -> sign face ids
# (drawn by the kit). I-35 here runs plan west (+s, the Austin-side "north" toward the edge of the map) and east (-s,
# into Chicago, where it meets the Eisenhower, I-290). No exits on the upper decks (the real ones had none either).
SIGNS = {
    "i35": {("plus", 0): ["I35N_DALLAS", "UPPER_THRU"], ("plus", 1): ["I35N_GEORGETOWN", "MILEAGE_N"],
            ("minus", 0): ["I35S_SANANTONIO", "TO290E_CHICAGO"], ("minus", 1): ["CAPITOL_CONGRESS", "MILEAGE_S"]},
    "wacker": {("plus", 0): ["WCX_N_CROSSTOWN", "WCX_N_6TH"], ("plus", 1): ["WCX_N_LAKE", "WCX_N_PKWY"],
               ("minus", 0): ["WCX_S_LOOP", "WCX_S_290"], ("minus", 1): ["WCX_S_WILLIS", "WCX_S_ADAMS"]},
}


# ------------------------------------------------------------------------------------------------ build one road
def layout_road(key, cfg):
    st = STYLES[cfg["style"]]
    pts, raw, dev, r = alignment(key, cfg)
    s_c = cumlen(pts)
    s_arr = np.array(s_c)
    L = s_c[-1]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    box = (min(xs) - 45, min(ys) - 45, max(xs) + 45, max(ys) + 45)
    G = build_ground(box)
    half = st["total_w"] / 2
    under = street_crossings(G, pts, s_c, half)
    sp, zp = profile(L, cfg["ends"], st, None)
    z = np.interp(s_arr, sp, zp)
    # clearance check over streets (raise the profile locally would change the ramps; report instead)
    clear = []
    for i, bits in enumerate(under):
        if bits & (PAVE | WALK):
            cl = z[i] - st["sup_d"]
            clear.append((s_c[i], cl, bool(bits & PAVE)))
    # fill sections at each end; the abutments sit where the deck reaches fill_below, but never with fill in water (a
    # creek or the canal under a low ramp gets spans; the abutment moves out past the far bank)
    wet = [bool(b & WATER) and 6.0 < s_c[i] < L - 6.0 for i, b in enumerate(under)]   # the land edge itself doesn't count
    s_abut0 = next((s_c[i] for i in range(len(pts)) if z[i] >= st["fill_below"]), 0.0)
    s_abut1 = next((s_c[i] for i in range(len(pts) - 1, -1, -1) if z[i] >= st["fill_below"]), L)
    w0 = [s_c[i] for i in range(len(pts)) if wet[i] and s_c[i] < s_abut0]
    if w0:
        s_abut0 = max(0.0, min(w0) - 4.0)
    w1 = [s_c[i] for i in range(len(pts)) if wet[i] and s_c[i] > s_abut1]
    if w1:
        s_abut1 = min(L, max(w1) + 4.0)
    bents = place_bents(G, st, pts, s_arr, z, s_abut0, s_abut1)
    for b in bents:
        p, t = at(pts, s_arr, b["s"])
        b["p"] = [round(p[0], 3), round(p[1], 3)]
        b["t"] = [round(t[0], 5), round(t[1], 5)]
        b["z_top"] = round(z_at(s_arr, z, b["s"]), 3)
        n = left(t)
        b["cols"] = [[round(p[0] + n[0] * o, 3), round(p[1] + n[1] * o, 3)] for o in b["offs"]]
    supports = [s_abut0] + [b["s"] for b in bents] + [s_abut1]
    spans = []
    for a, b in zip(supports, supports[1:]):
        Ls = b - a
        gt = next(g for g in st["girder_types"] if Ls <= g[0] + 1e-6) if Ls <= st["girder_types"][-1][0] else st["girder_types"][-1]
        spans.append({"s0": round(a, 2), "s1": round(b, 2), "len": round(Ls, 2), "girder": gt[1], "girder_d": gt[2]})
    # light poles: Austin, single-arm davits on each deck's inside rail, staggered between the two decks; Chicago, davits on
    # the outside parapets, alternating sides. The arm reaches over the lanes.
    lights = []
    rail_in = st["deck_w"] / 2 - st["fascia"] - st["rail_w"] / 2
    for k, dc in enumerate(st["decks"]):
        sv = 20.0 + k * st["light_every"] / 2
        side = 0
        while sv < L - 20.0:
            p, t = at(pts, s_arr, sv)
            n = left(t)
            if st["twin"]:
                lat = dc - math.copysign(rail_in, dc)      # inside rail of this deck
                arm = math.copysign(1.0, dc)               # towards the deck's outer side, over its lanes
            else:
                sgn = 1 if side % 2 == 0 else -1
                lat = sgn * rail_in
                arm = -sgn
                side += 1
            q = (p[0] + n[0] * lat, p[1] + n[1] * lat)
            lights.append({"deck": k, "s": round(sv, 2), "p": [round(q[0], 3), round(q[1], 3)], "t": [round(t[0], 5), round(t[1], 5)],
                           "z": round(z_at(s_arr, z, sv), 3), "arm": arm})
            sv += st["light_every"] * (1.0 if st["twin"] else 0.5)
        if not st["twin"]:
            break
    # sign bridges at bents, one per deck per end, facing that deck's traffic. Right-hand traffic: the deck right of +s
    # (negative offset) carries +s traffic, so its signs face -s; the left deck carries -s traffic.
    gantries = []
    sign_sets = SIGNS.get(cfg.get("signs"), {})
    for k, dc in enumerate(st["decks"] if st["twin"] else [0.0, 0.0]):
        plus = (dc < 0) if st["twin"] else (k == 0)        # this deck/direction carries +s traffic
        face = -1 if plus else +1
        for j, frac in enumerate((0.22, 0.72) if plus else (0.78, 0.28)):
            target = s_abut0 + (s_abut1 - s_abut0) * frac
            sb = min(bents, key=lambda b: abs(b["s"] - target))["s"] if bents else target
            p, t = at(pts, s_arr, sb)
            n = left(t)
            q = (p[0] + n[0] * dc, p[1] + n[1] * dc)
            gantries.append({"deck": k, "s": round(sb, 2), "p": [round(q[0], 3), round(q[1], 3)], "t": [round(t[0], 5), round(t[1], 5)],
                             "z": round(z_at(s_arr, z, sb), 3), "face": face, "dir": "plus" if plus else "minus",
                             "signs": sign_sets.get(("plus" if plus else "minus", j), [])})
    # footprint polygons for the street builder
    def strip(s0, s1, w, step=4.0):
        ss = list(np.arange(s0, s1, step)) + [s1]
        Lp, Rp = [], []
        for sv in ss:
            p, t = at(pts, s_arr, sv)
            n = left(t)
            Lp.append((round(p[0] + n[0] * w / 2, 2), round(p[1] + n[1] * w / 2, 2)))
            Rp.append((round(p[0] - n[0] * w / 2, 2), round(p[1] - n[1] * w / 2, 2)))
        return Lp + Rp[::-1]
    deck_polys = [strip(s_abut0, s_abut1, st["total_w"] + 0.6)]
    fill_polys = []
    if s_abut0 > 0.5:
        fill_polys.append(strip(0.0, s_abut0, st["total_w"] + 0.6))
    if L - s_abut1 > 0.5:
        fill_polys.append(strip(s_abut1, L, st["total_w"] + 0.6))
    col_polys = []
    for b in bents:
        t = tuple(b["t"])
        size = st["col"] if b["type"] != "straddle" else st["straddle_col"]
        for c in b["cols"]:
            col_polys.append([(round(x, 2), round(y, 2)) for x, y in rect(c, t, size[0], size[1])])
    # what stands under the deck now (for the street builder): trees whose crown reaches the beams, lamps, poles
    under_props = []
    for q in G.props:
        d, i, f = closest(pts, q[:2])
        if i >= len(pts) - 1:
            continue
        si = s_c[i] + f * (s_c[i + 1] - s_c[i])
        zz = z_at(s_arr, z, si)
        if q[2] in TREES:
            if d < half + q[3] + 1.0 and TREE_H[q[2]] * 1.1 > zz - st["sup_d"] - 0.5:
                under_props.append({"kind": q[2], "p": [round(q[0], 2), round(q[1], 2)], "d": round(d, 1)})
        elif d < half + 1.0 and q[2] in ("RProps_lamp", "RProps_lamp_hw", "RProps_pole", "RProps_arm"):
            under_props.append({"kind": q[2], "p": [round(q[0], 2), round(q[1], 2)], "d": round(d, 1)})
    lay = {
        "key": key, "label": cfg["label"], "style": cfg["style"], "plan_name": r["name"], "ref": r.get("ref"),
        "len": round(L, 2), "plan_dev_max_m": dev, "ends": cfg["ends"],
        "centre": [[round(p[0], 3), round(p[1], 3), round(float(zz), 3), round(sv, 2)] for p, zz, sv in zip(pts, z, s_c)],
        "abutments": [round(s_abut0, 2), round(s_abut1, 2)],
        "fill": [[0.0, round(s_abut0, 2)], [round(s_abut1, 2), round(L, 2)]],
        "bents": bents, "spans": spans, "lights": lights, "gantries": gantries,
        "clearance_min": [round(min((c[1] for c in clear if c[2]), default=99), 2),
                          round(min((c[1] for c in clear), default=99), 2)],
        "footprint": {"deck": deck_polys, "fill": fill_polys, "columns": col_polys},
        "under_props": under_props,
        "counts": {"bents": len(bents), "hammer": sum(b["type"] == "hammer" for b in bents),
                   "multi": sum(b["type"] == "multi" for b in bents), "straddle": sum(b["type"] == "straddle" for b in bents),
                   "steel_spans": sum(sp_["girder"] == "steel" for sp_ in spans), "spans": len(spans),
                   "under_trees": sum(1 for q in under_props if q["kind"] in TREES)},
    }
    # the deck and fill vs buildings and other structures traced in the level (a building through the deck is a bug)
    hits = []
    for i in range(0, len(pts), 2):
        p = pts[i]
        a = pts[max(0, i - 1)]; b = pts[min(len(pts) - 1, i + 1)]
        n = left(unit((b[0] - a[0], b[1] - a[1])))
        for k in np.linspace(-half - 0.3, half + 0.3, 15):
            q = (p[0] + n[0] * k, p[1] + n[1] * k)
            v = G.at(q)
            if v & (BUILD | OBST):
                hits.append({"s": round(s_c[i], 1), "p": [round(q[0], 1), round(q[1], 1)], "what": "building" if v & BUILD else "structure"})
    lay["deck_hits"] = hits[:200]
    lay["counts"]["deck_hits"] = len(hits)
    # crossings under the bridge, by street name, with the clearance there
    names = []
    for e in RN["edges"]:
        g = e["geom"]
        for a_, b_ in zip(g, g[1:]):
            for i in range(0, len(pts) - 1):
                h = seg_x(pts[i], pts[i + 1], a_, b_)
                if h is not None:
                    sv = s_c[i] + h * (s_c[i + 1] - s_c[i])
                    names.append({"street": e["name"], "cls": e["cls"], "s": round(sv, 1),
                                  "deck_top": round(z_at(s_arr, z, sv), 2), "clearance": round(z_at(s_arr, z, sv) - st["sup_d"], 2)})
    lay["crossings"] = sorted(names, key=lambda q: q["s"])
    render(lay, G, st, OUTD / f"layout_{key}.png")
    return lay


def seg_x(a, b, c, d):
    r = (b[0] - a[0], b[1] - a[1]); q = (d[0] - c[0], d[1] - c[1])
    den = r[0] * q[1] - r[1] * q[0]
    if abs(den) < 1e-9:
        return None
    t = ((c[0] - a[0]) * q[1] - (c[1] - a[1]) * q[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    return t if 0 <= t <= 1 and 0 <= u <= 1 else None


# ------------------------------------------------------------------------------------------------ debug render
def render(lay, G, st, path, scale=2.0):
    x0, y0, x1, y1 = G.x0, G.y0, G.x1, G.y1
    W, H = int((x1 - x0) * scale), int((y1 - y0) * scale)
    col = np.zeros((G.ny, G.nx, 3), np.uint8) + np.array([40, 43, 49], np.uint8)
    for bit, c in ((PARKWAY, (40, 70, 50)), (WALK, (80, 82, 88)), (PAVE, (125, 130, 140)), (WATER, (30, 55, 100)),
                   (KEEP, (110, 60, 110)), (BUILD, (170, 60, 50)), (OBST, (200, 120, 200))):
        col[(G.bits & bit) > 0] = c
    im = Image.fromarray(col).resize((W, H), Image.NEAREST)
    d = ImageDraw.Draw(im)
    px = lambda p: ((p[0] - x0) * scale, (y1 - p[1]) * scale)
    for q in G.props:
        r = 0.7 if q[2] not in TREES else 1.2
        d.ellipse([px((q[0] - r, q[1] + r)), px((q[0] + r, q[1] - r))], fill=(60, 200, 60) if q[2] in TREES else (255, 210, 0))
    fp = lay["footprint"]
    for poly in fp["fill"]:
        d.polygon([px(p) for p in poly], outline=(255, 140, 0))
    for poly in fp["deck"]:
        d.polygon([px(p) for p in poly], outline=(255, 255, 255))
    for poly in fp["columns"]:
        d.polygon([px(p) for p in poly], fill=(255, 40, 40))
    for b in lay["bents"]:
        p = b["p"]; t = b["t"]; n = left(t)
        w = st["total_w"] / 2
        d.line([px((p[0] + n[0] * w, p[1] + n[1] * w)), px((p[0] - n[0] * w, p[1] - n[1] * w))],
               fill=(255, 80, 80) if b["type"] != "straddle" else (0, 220, 255), width=2)
    for g in lay["gantries"]:
        p = g["p"]
        d.ellipse([px((p[0] - 2, p[1] + 2)), px((p[0] + 2, p[1] - 2))], outline=(0, 255, 120), width=2)
    c = lay["centre"]
    d.line([px(p) for p in c], fill=(255, 255, 0), width=1)
    for k in range(0, len(c), 50):
        d.text(px(c[k]), f"s{int(c[k][3])} z{c[k][2]:.1f}", fill=(255, 255, 255))
    for gx in range(int(x0 // 50 * 50), int(x1) + 1, 50):
        d.text(px((gx, y1 - 1)), str(gx), fill=(200, 200, 200))
    im.save(path)


# ------------------------------------------------------------------------------------------------ main
def main():
    t0 = time.time()
    keys = [k for k in ROADS if not ONLY or k in ONLY]
    prev = {}
    lp = OUTD / "expressway_layout.json"
    if lp.exists():
        try:
            prev = json.load(open(lp)).get("roads", {})
        except Exception:
            prev = {}
    roads = dict(prev)
    for k in keys:
        roads[k] = layout_road(k, ROADS[k])
    out = {"frame": "plan metres, x east, y north (Unreal X = y*100, Y = x*100); z metres above the street",
           "made": time.strftime("%Y-%m-%d %H:%M"), "styles": STYLES, "roads": roads, "issues": issues}
    json.dump(out, open(lp, "w"))
    fp = {"frame": "plan metres, x east, y north (Unreal X = y*100, Y = x*100)",
          "why": "elevated expressways (Scripts/roads/expressway_layout.py): no trees within 3.5 m of a deck polygon, no lamps "
                 "or signs within 1 m, nothing at all on a fill polygon (solid ramp embankment) or within 0.5 m of a column",
          "deck": [], "platforms": [], "columns": [], "stairs": [], "fill": []}
    for k, lay in roads.items():
        if not ROADS.get(k, {}).get("publish", True):
            continue
        fp["deck"] += lay["footprint"]["deck"] + lay["footprint"]["fill"]
        fp["fill"] += lay["footprint"]["fill"]
        fp["columns"] += lay["footprint"]["columns"]
    json.dump(fp, open(OUTD / "expressway_footprint.json", "w"))
    summ = {k: {"len": v["len"], "plan_dev_max_m": v["plan_dev_max_m"], "abutments": v["abutments"], "counts": v["counts"],
                "clearance_min_lanes_walks": v["clearance_min"],
                "spans": [s["len"] for s in v["spans"]]} for k, v in roads.items() if k in keys}
    print(json.dumps({"secs": round(time.time() - t0, 1), "roads": summ, "issues": issues}, indent=1))


if __name__ == "__main__":
    main()
