"""Sky City: the elevated L's layout, computed offline and written to Saved/Rail/l_layout.json for build_l_ue.py to place.

Why (20 Oct 2026 playtest, Kenny: the L "seemed to stop randomly at some point"): the old build_l_ue.py paired the plan's
OpenStreetMap tracks on the fly inside the editor and placed whatever came out. The South Side line stopped in mid-air
in the middle of a block south of Harrison (plan (80,-1512)) because the mashup integration dropped track vertices outside
the plan box instead of clipping them; the junction at Wabash/Van Buren became a pile of short single lines; columns and
stair towers stood wherever the tracks put them (in travel lanes, crosswalks and junctions); all of it faded out beyond
900-1200 m (HISM cull distances). This script does the whole layout offline, against the street network, so every column
and stair footprint can be checked before anything is placed.

What it builds (plan frame: metres, x east, y north; Unreal X = y*100, Y = x*100):
  routes    LOOP   the Union Loop as one closed two-track structure: midline of the plan's two Loop tracks (Wabash,
                   Lake, the Seam Line arc where Austin replaced the Loop's NW corner, Wells, Van Buren)
            SOUTH  the South Side line from the Loop's SE corner (Tower 12, Wabash/Van Buren) straight down Wabash Avenue
                   to a terminal between 8th and 9th Street. The plan's own tracks curve off Wabash at Congress into the
                   mid-block alley like the real Green Line, but in Sky City those blocks are built up (6 towers stand on
                   that alignment between Balbo and 9th), so the line keeps to Wabash, over the street
            WYE    the Van Buren <-> Wabash-south connecting curve at Tower 12 (plan tracks 1 and 13)
  deck      span modules along each route's chords: 15.24 m on straights, 5.08 m on curves (scaled to fit); "J"
            (junction) spans without outer walkways/handrails where two routes' decks overlap
  bents     a cross girder on two columns roughly every 15.24 m (9-20 m, up to 30 m over big junctions). Each column is
            placed on its own: never in a travel lane, junction ring, crosswalk, building or water; at the curb line or in
            a parking lane, like the Loop L over Wabash, Lake, Wells and Van Buren. Offsets are kept steady along a street
  stations  at the real Loop stations by their cross streets (State/Lake, Washington/Wabash, Adams/Wabash, Harold
            Washington Library, LaSalle/Van Buren, Quincy) and a terminal on SOUTH; four 30.48 m platform modules a side,
            cantilevered off the deck (no ground columns); stair towers at the platform ends where they land on the
            sidewalk (with a short bridge from the platform when the street is wide); a fare house at one stair head
  ends      bumpers + end fence at the SOUTH terminal; the Loop is closed; the WYE and SOUTH join the Loop's deck
  collision an invisible slab at top of rail along every chord so the car can drive the deck (the rails and ties alone
            are a cattle grid); columns and stairs block
Also lists road props and signals that collide with the structure (trees through the deck, mast arms through girders)
for the streets agent.
Inputs: Saved/Mashup/plan_v3.json, Saved/Roads/roadnet.json (read-only), SourceArt/Rail/kit.json,
        Saved/Rail/obstacles.json (building/water height map from Scripts/rail/l_probe_ue.py, run in the editor).
Run: python3 -I Scripts/rail/l_layout.py     -> Saved/Rail/l_layout.json + Saved/Rail/l_layout*.png (debug maps)
"""
import collections, json, math, pathlib, sys
import numpy as np
from skimage.measure import points_in_poly

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLAN = json.load(open(ROOT / "Saved/Mashup/plan_v3.json"))
RN = json.load(open(ROOT / "Saved/Roads/roadnet.json"))
KIT = json.load(open(ROOT / "SourceArt/Rail/kit.json"))
OBST = json.load(open(ROOT / "Saved/Rail/obstacles.json"))
OUTD = ROOT / "Saved/Rail"
OUTD.mkdir(parents=True, exist_ok=True)
stats = collections.Counter()
issues = []

BENT = 15.24
SPAN_S = BENT / 3
DECK_HALF = 4.45                      # outer walkway edge
COL_DEFAULT = 5.0                     # kit L_Bent columns at +-5.0
COL_MIN, COL_MAX = 3.3, 10.5          # column offset range from the track-pair centreline
FOOT = (1.5, 1.3)                     # column footing across x along (m)
FOOT_MARGIN = 0.3                     # clear space round a footing
PLAT_L = 30.48
PLAT_OUT = 6.95                       # platform outer edge from the centreline
STAIR_W, STAIR_L = 3.0, 16.56         # stair tower footprint (kit L_StationStairs: x 6.95..9.95, y 0..-16.56)
TOR = KIT["track"]["top_of_rail_z"]


# ---------------------------------------------------------------- geometry
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def unit(v):
    L = math.hypot(v[0], v[1]) or 1e-12
    return (v[0] / L, v[1] / L)


def cumlen(pts):
    s = [0.0]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + dist(a, b))
    return s


def at_s(pts, s_c, s):
    s = max(0.0, min(s_c[-1], s))
    i = max(0, min(len(pts) - 2, int(np.searchsorted(s_c, s, side="right")) - 1))
    a, b = pts[i], pts[i + 1]
    seg = (s_c[i + 1] - s_c[i]) or 1e-9
    t = (s - s_c[i]) / seg
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), unit((b[0] - a[0], b[1] - a[1]))


def resample(pts, step):
    s_c = cumlen(pts)
    n = max(1, int(round(s_c[-1] / step)))
    return [at_s(pts, s_c, s_c[-1] * k / n)[0] for k in range(n + 1)]


def left(t):
    return (-t[1], t[0])


def offset_polyline(pts, off):
    """Offset to the left by off (negative = right), mitred (same as roadnet.py so bands match the ribbons)."""
    n = len(pts)
    res = []
    for i in range(n):
        if i == 0:
            t = unit((pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]))
            nrm = (-t[1], t[0])
        elif i == n - 1:
            t = unit((pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]))
            nrm = (-t[1], t[0])
        else:
            t1 = unit((pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
            t2 = unit((pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]))
            n1, n2 = (-t1[1], t1[0]), (-t2[1], t2[0])
            m = unit((n1[0] + n2[0], n1[1] + n2[1]))
            k = max(0.5, m[0] * n1[0] + m[1] * n1[1])
            nrm = (m[0] / k, m[1] / k)
        res.append((pts[i][0] + nrm[0] * off, pts[i][1] + nrm[1] * off))
    return res


def sub_polyline(pts, s_c, s0, s1):
    if s1 - s0 < 0.05:
        return []
    out = [at_s(pts, s_c, s0)[0]]
    for p, s in zip(pts, s_c):
        if s0 + 1e-6 < s < s1 - 1e-6:
            out.append(p)
    out.append(at_s(pts, s_c, s1)[0])
    return out


def closest_on_polyline(pts, p):
    best = (1e18, None, 0.0, None)
    s = 0.0
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy or 1e-12
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
        q = (a[0] + dx * t, a[1] + dy * t)
        d = dist(p, q)
        if d < best[0]:
            best = (d, q, s + math.sqrt(L2) * t, unit((dx, dy)))
        s += math.sqrt(L2)
    return best          # (distance, point, s along, tangent)


def rect(c, t, w_across, l_along, off_along=0.0):
    """Corners of a rectangle centred at c (+ off_along along t), w across t, l along t."""
    n = left(t)
    cx, cy = c[0] + t[0] * off_along, c[1] + t[1] * off_along
    hw, hl = w_across / 2, l_along / 2
    return [(cx + n[0] * sw * hw + t[0] * sl * hl, cy + n[1] * sw * hw + t[1] * sl * hl) for sw, sl in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def rect_samples(corners, n=5):
    a, b, c, d = corners
    out = []
    for i in range(n):
        for j in range(n):
            u, v = i / (n - 1), j / (n - 1)
            p = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
            q = (d[0] + (c[0] - d[0]) * u, d[1] + (c[1] - d[1]) * u)
            out.append((p[0] + (q[0] - p[0]) * v, p[1] + (q[1] - p[1]) * v))
    return out


# ---------------------------------------------------------------- forbidden ground (what a column or stair may not stand on)
# A raster of the ground (0.25 m cells) built from the street network and the editor's obstacle probe:
#   0 free (sidewalk, plaza, lawn)  1 parking lane  2 travel lane  3 crosswalk or stop bar  7 junction ring / joint
#   4 building, landmark, elevated road  5 street furniture (tree, lamp, hydrant, sign, signal pole...)  6 water
from PIL import Image, ImageDraw  # noqa: E402
RES = 0.25
RX0, RY0, RX1, RY1 = -640.0, -2010.0, 300.0, -100.0
RW, RH = int((RX1 - RX0) / RES), int((RY1 - RY0) / RES)
_img = Image.new("L", (RW, RH), 0)
_drw = ImageDraw.Draw(_img)


def _px(ring):
    return [((x - RX0) / RES, (RY1 - y) / RES) for x, y in ring]


TRAVEL_BANDS = []
for e in RN["edges"]:
    if not e["ribbon"]:
        continue
    g = e["geom"]
    s_c = cumlen(g)
    sub = sub_polyline(g, s_c, e["s0"], e["s1"])
    if len(sub) < 2:
        continue
    W = e["width"]
    el = e["elems"]
    lpark = 0.0
    for k, w, d in el:
        if k not in ("parking", "gutter"):
            break
        lpark += w
    rpark = 0.0
    for k, w, d in reversed(el):
        if k not in ("parking", "gutter"):
            break
        rpark += w
    _drw.polygon(_px(e["ribbon"]), fill=1)
    TRAVEL_BANDS.append(offset_polyline(sub, W / 2 - lpark) + offset_polyline(sub, -W / 2 + rpark)[::-1])
for band in TRAVEL_BANDS:
    _drw.polygon(_px(band), fill=2)
for J in RN["junctions"]:
    _drw.polygon(_px(J["ring"]), fill=7)
for j in RN["joints"]:
    _drw.polygon(_px(j), fill=7)
for b in RN["markings"]["bars"]:
    _drw.polygon(_px(b), fill=3)
# obstacle height map from the editor (BuildingCollision, water, elevated expressways, landmarks)
OX0, OY0, OX1, OY1 = OBST["box"]
OST = OBST["step"]
OLAB = OBST["labels"]
BAD_LAB = {i for i, l in enumerate(OLAB) if l == "BuildingCollision" or "Water" in l or l == "ElevatedExpressways" or l.startswith("LM_")}
for j, (zr, ar) in enumerate(zip(OBST["z"], OBST["a"])):
    for i, (z, a) in enumerate(zip(zr, ar)):
        if a in BAD_LAB and (z > 60 or "Water" in OLAB[a]):
            x, y = OX0 + i * OST, OY0 + j * OST
            _drw.rectangle(_px([(x - OST / 2, y + OST / 2), (x + OST / 2, y - OST / 2)]), fill=6 if "Water" in OLAB[a] else 4)
# upright street furniture (a column or a stair must not land on a lamp, tree, hydrant, sign, signal pole...)
PROP_R = {"tree": 1.2, "lamp": 0.5, "lamp_hw": 0.5, "hydrant": 0.5, "namesign": 0.4, "dumpster": 1.3, "bin": 0.5,
          "bikerack": 0.9, "mailbox": 0.5, "busstop": 0.5, "shelter": 2.0, "bench": 1.0}


def _dot(p, r):
    _drw.ellipse(_px([(p[0] - r, p[1] + r), (p[0] + r, p[1] - r)]), fill=5)


for _q in RN["props"]:
    if _q["t"] in PROP_R and RX0 < _q["p"][0] < RX1 and RY0 < _q["p"][1] < RY1:
        _dot(_q["p"], PROP_R[_q["t"]])
for _q in RN["signs"]:
    if RX0 < _q["p"][0] < RX1 and RY0 < _q["p"][1] < RY1:
        _dot(_q["p"], 0.4)
for _k in ("poles", "cabinets"):
    for _q in RN["signals"][_k]:
        if RX0 < _q["p"][0] < RX1 and RY0 < _q["p"][1] < RY1:
            _dot(_q["p"], 0.6)
GROUND = np.array(_img, np.uint8)
del _img, _drw
# crosswalk / stop bars grown by 0.75 m (a column keeps that far off them; the bars are thin, so sampling alone misses them)
_cw = GROUND == 3
CROSS = _cw.copy()
for _dy in range(-3, 4):
    for _dx in range(-3, 4):
        if _dx or _dy:
            CROSS[max(0, _dy):RH + min(0, _dy), max(0, _dx):RW + min(0, _dx)] |= _cw[max(0, -_dy):RH + min(0, -_dy), max(0, -_dx):RW + min(0, -_dx)]
del _cw


def crosswalk_near(pts):
    P = np.asarray(pts, float).reshape(-1, 2)
    ix = np.clip(((P[:, 0] - RX0) / RES).astype(int), 0, RW - 1)
    iy = np.clip(((RY1 - P[:, 1]) / RES).astype(int), 0, RH - 1)
    return CROSS[iy, ix]


def ground(pts):
    """Ground codes under plan points (array)."""
    P = np.asarray(pts, float).reshape(-1, 2)
    ix = np.clip(((P[:, 0] - RX0) / RES).astype(int), 0, RW - 1)
    iy = np.clip(((RY1 - P[:, 1]) / RES).astype(int), 0, RH - 1)
    return GROUND[iy, ix]


CODE_NAME = {0: None, 1: "parking", 2: "travel lane", 3: "crosswalk", 4: "building", 5: "street furniture", 6: "water", 7: "junction"}


def footing_ok(p, t, w=FOOT[0], l=FOOT[1], margin=FOOT_MARGIN, cw=1.6):
    """Why a column footing centred at p (bent direction t) can't stand there, or None."""
    g = ground(rect_samples(rect(p, t, w + 2 * margin, l + 2 * margin), 9))
    bad = g[(g == 2) | (g >= 4)]
    if bad.size:
        return CODE_NAME[int(bad.max())]
    if crosswalk_near(rect_samples(rect(p, t, w + max(0.0, cw - 1.5), l + max(0.0, cw - 1.5)), 9)).any():
        return "crosswalk"
    return None


def stair_ok(corners, foot_corners):
    """A stair tower (corners) may stand only on free ground; its street entrance (foot) must be free too."""
    g = ground(rect_samples(corners, 9))
    if (g > 0).any():
        return CODE_NAME[int(g.max())]
    g = ground(rect_samples(foot_corners, 4))
    if (g > 0).any():
        return "entrance " + CODE_NAME[int(g.max())]
    return None


# ---------------------------------------------------------------- routes
TR = {i: [tuple(p) for p in r["pts"]] for i, r in enumerate(PLAN["rail"]) if r["kind"] == "L"}


def chain(ids):
    pts = []
    for i in ids:
        p = TR[i]
        if pts:
            if dist(pts[-1], p[0]) > 4.0:
                if dist(pts[-1], p[-1]) < 4.0:
                    p = p[::-1]
                else:
                    raise SystemExit(f"track {i} does not join the chain: {pts[-1]} vs {p[0]}/{p[-1]}")
            p = p[1:]
        pts += list(p)
    return pts


def midline(A, B, closed=False, maxsep=10.0):
    """Midline of two roughly parallel tracks: each point of A (1 m) paired with its nearest point on B."""
    Ar = resample(A, 1.0)
    Br = resample(B, 1.0)
    grid = collections.defaultdict(list)
    for k, q in enumerate(Br):
        grid[(int(q[0] // 10), int(q[1] // 10))].append(k)
    out = []
    for p in Ar:
        best = None
        gx, gy = int(p[0] // 10), int(p[1] // 10)
        for u in (gx - 1, gx, gx + 1):
            for v in (gy - 1, gy, gy + 1):
                for k in grid.get((u, v), ()):
                    d = dist(p, Br[k])
                    if best is None or d < best[0]:
                        best = (d, k)
        if best and best[0] < maxsep:
            # refine on the two neighbouring segments of B
            k = best[1]
            seg = Br[max(0, k - 1): k + 2]
            d, q, _, _ = closest_on_polyline(seg, p)
            out.append(((p[0] + q[0]) / 2, (p[1] + q[1]) / 2))
        else:
            out.append(p)
    return smooth(out, 9, closed)


def smooth(pts, half, closed=False, passes=2):
    P = np.array(pts, float)
    n = len(P)
    for _ in range(passes):
        Q = P.copy()
        for i in range(n):
            if closed:
                idx = [(i + k) % n for k in range(-half, half + 1)]
            else:
                lo, hi = max(0, i - half), min(n - 1, i + half)
                h = min(i - lo, hi - i)                    # symmetric window: ends stay put
                idx = list(range(i - h, i + h + 1))
            Q[i] = P[idx].mean(0)
        P = Q
    return [tuple(p) for p in P]


def street_line(name, ymax, ymin):
    """Centreline of a N-S street (roadnet edges by name) between ymax and ymin, north to south."""
    pts = set()
    for e in RN["edges"]:
        if e["name"] == name:
            for p in e["geom"]:
                if ymin <= p[1] <= ymax:
                    pts.add((round(p[0], 2), round(p[1], 2)))
    pts = sorted(pts, key=lambda p: -p[1])
    # one point per ~10 m of y (divided / duplicate edges)
    out = []
    for p in pts:
        if out and abs(out[-1][1] - p[1]) < 8:
            continue
        out.append(p)
    return out


ROUTES = {}
loopA = chain([19, 4, 239, 25, 24, 3, 28, 16])
loopB = chain([20, 12, 27, 21, 22, 5, 18, 238, 23, 2])
lp = midline(loopA, loopB, closed=True)
# start the closed loop mid-Wabash (between Adams and Jackson) so its seam is on a straight
k0 = min(range(len(lp)), key=lambda k: dist(lp[k], (143, -960)))
lp = lp[k0:] + lp[:k0]
lp = resample(lp + [lp[0]], 1.0)
ROUTES["LOOP"] = {"pts": lp, "closed": True}

# SOUTH: the plan's two Wabash tracks from the Loop corner to Ida B. Wells Drive, then Wabash Avenue's centreline
southA = chain([17, 10])
southB = chain([14, 11])
sm = midline(southA, southB)
sm = [p for p in sm if p[1] >= -1290]
wab = street_line("South Wabash Avenue", -1300, -1968)
south = resample(sm + wab, 1.0)
south = smooth(south, 12)
south = resample(south, 1.0)
ROUTES["SOUTH"] = {"pts": south, "closed": False}

wye = midline(chain([1]), chain([13]))
ROUTES["WYE"] = {"pts": resample(wye, 1.0), "closed": False}


def route_s_of(route, p):
    d, q, s, t = closest_on_polyline(ROUTES[route]["pts"], p)
    return s, d


# trim SOUTH: start at the Loop's corner (where its Wabash straight ends), end before 9th Street's junction ring
def ring_near(p, r=40.0):
    for J in RN["junctions"]:
        if dist(J["c"], p) < r:
            yield J


def first_ring_hit(pts, s_c, s_from, s_to, step=0.5):
    s = s_from
    while s <= s_to:
        p, t = at_s(pts, s_c, s)
        for J in ring_near(p):
            if points_in_poly(np.array([p]), np.array(J["ring"]))[0]:
                return s
        s += step
    return None


def street_crossing_s(route, name, s_lo=0.0, s_hi=1e9):
    """s along a route where it crosses the centreline of the named street (first one in [s_lo, s_hi])."""
    pts = ROUTES[route]["pts"]
    s_c = cumlen(pts)
    best = None
    for e in RN["edges"]:
        if e["name"] != name:
            continue
        g = e["geom"]
        for a, b in zip(g, g[1:]):
            for k in range(len(pts) - 1):
                p, q = pts[k], pts[k + 1]
                d1 = (b[0] - a[0], b[1] - a[1])
                d2 = (q[0] - p[0], q[1] - p[1])
                den = d1[0] * d2[1] - d1[1] * d2[0]
                if abs(den) < 1e-9:
                    continue
                w = (p[0] - a[0], p[1] - a[1])
                u = (w[0] * d2[1] - w[1] * d2[0]) / den
                v = (w[0] * d1[1] - w[1] * d1[0]) / den
                if 0 <= u <= 1 and 0 <= v <= 1:
                    s = s_c[k] + v * dist(p, q)
                    if s_lo <= s <= s_hi and (best is None or s < best):
                        best = s
    return best


sp = ROUTES["SOUTH"]["pts"]
s_c = cumlen(sp)
s_9th = street_crossing_s("SOUTH", "East 9th Street")
s_ring = first_ring_hit(sp, s_c, s_9th - 40, s_9th)
SOUTH_END_S = (s_ring - 2.5) if s_ring else s_9th - 18
ROUTES["SOUTH"]["pts"] = sub_polyline(sp, s_c, 0.0, SOUTH_END_S)
for r in ROUTES.values():
    r["s"] = cumlen(r["pts"])
    r["len"] = r["s"][-1]
stats["SOUTH_end_s"] = round(SOUTH_END_S, 1)


def P(route, s):
    r = ROUTES[route]
    s = s % r["len"] if r["closed"] else s
    return at_s(r["pts"], r["s"], s)


# ---------------------------------------------------------------- report: where the old build stopped, and route summary
if __name__ == "__main__" and "--routes" in sys.argv:
    for k, r in ROUTES.items():
        print(k, round(r["len"]), r["pts"][0], r["pts"][-1])


# ---------------------------------------------------------------- the street under the L
EDGE_IDX = collections.defaultdict(list)
for _i, _e in enumerate(RN["edges"]):
    if _e["ribbon"]:
        for _p in _e["geom"]:
            EDGE_IDX[(int(_p[0] // 50), int(_p[1] // 50))].append(_i)


def street_under(p, t):
    """The roadnet edge running along the L at p (parallel, within its ribbon + 3 m): (edge, signed lateral offset of the
    edge centreline from the L centreline (+ = left of t), aligned (+1/-1)) or None."""
    cand = set()
    gx, gy = int(p[0] // 50), int(p[1] // 50)
    for u in (gx - 1, gx, gx + 1):
        for v in (gy - 1, gy, gy + 1):
            cand.update(EDGE_IDX.get((u, v), ()))
    best = None
    for i in cand:
        e = RN["edges"][i]
        g = e["geom"]
        d, q, s, te = closest_on_polyline(g, p)
        if s < e["s0"] - 1 or s > e["s1"] + 1:
            continue
        dot = t[0] * te[0] + t[1] * te[1]
        if abs(dot) < 0.8 or d > e["width"] / 2 + 3:
            continue
        n = left(t)
        lat = (q[0] - p[0]) * n[0] + (q[1] - p[1]) * n[1]
        if best is None or d < best[1]:
            best = (e, d, lat, 1 if dot > 0 else -1)
    if best is None:
        return None
    return best[0], best[2], best[3]


if __name__ == "__main__" and "--streets" in sys.argv:
    for name, r in ROUTES.items():
        print("==", name)
        last = None
        s = 0.0
        while s < r["len"]:
            p, t = P(name, s)
            su = street_under(p, t)
            key = (su[0]["name"], su[0]["width"]) if su else None
            if key != last:
                if su:
                    e, lat, al = su
                    el = e["elems"] if al > 0 else [[k, w, -d] for k, w, d in reversed(e["elems"])]
                    print(f"  s={s:6.0f} ({p[0]:7.1f},{p[1]:7.1f})  {e['name']:28s} W={e['width']:4.1f} sw={e['sidewalk']} L-offset {lat:+5.1f}  {[k for k,w,d in el]}")
                else:
                    print(f"  s={s:6.0f} ({p[0]:7.1f},{p[1]:7.1f})  -- no street under --")
                last = key
            s += 4.0


# ---------------------------------------------------------------- deck chords and the overlap between routes
def deck_chords(name):
    """Chord breakpoints along a route: 15.24 m where straight, 5.08 m where the line bends (sagitta > 0.2 m)."""
    r = ROUTES[name]
    L = r["len"]
    ss = [0.0]
    while ss[-1] < L - 0.5:
        s0 = ss[-1]
        a, _ = P(name, s0)
        b, _ = P(name, min(L, s0 + BENT))
        m, _ = P(name, min(L, s0 + BENT / 2))
        ch = (b[0] - a[0], b[1] - a[1])
        lc = math.hypot(*ch) or 1.0
        sag = abs((m[0] - a[0]) * ch[1] - (m[1] - a[1]) * ch[0]) / lc
        step = BENT if sag < 0.2 else SPAN_S
        nxt = s0 + step
        if L - nxt < 0.4 * step:            # don't leave a sliver: stretch this chord to the end
            nxt = L
        ss.append(min(L, nxt))
    return ss


def deck_overlap(name, p, others_only=True):
    """Other routes whose deck covers point p (within the deck half width)."""
    hit = []
    for k, r in ROUTES.items():
        if k == name:
            continue
        d, q, s, t = closest_on_polyline(r["pts"], p)
        if d < DECK_HALF + 0.3:
            hit.append(k)
    return hit




# ---------------------------------------------------------------- bents: columns placed one by one off the roadway
OFFS = np.round(np.arange(COL_MIN, COL_MAX + 1e-6, 0.1), 2)
WIDE_OFFS = np.round(np.arange(COL_MIN, 14.0 + 1e-6, 0.1), 2)
_FS_IN = np.array(rect_samples(rect((0, 0), (0, 1), FOOT[0] + 2 * FOOT_MARGIN, FOOT[1] + 2 * FOOT_MARGIN), 9))   # x across, y along
_FS_OUT = np.array(rect_samples(rect((0, 0), (0, 1), FOOT[0] + 0.1, FOOT[1] + 0.1), 9))
SKEWS = [0, 8, -8, 16, -16, 24, -24, 32, -32]


def rot(t, deg):
    a = math.radians(deg)
    return (t[0] * math.cos(a) - t[1] * math.sin(a), t[0] * math.sin(a) + t[1] * math.cos(a))


_BE_CACHE = {}


def band_edges(q, t):
    """(left, right) edges of the travel band of the street running along t at q, as signed offsets (+ = left), or None."""
    key = (round(q[0], 1), round(q[1], 1), round(t[0], 2), round(t[1], 2))
    if key in _BE_CACHE:
        return _BE_CACHE[key]
    su = street_under(q, t)
    res = None
    if su:
        e, lat, al = su
        el = e["elems"] if al > 0 else [[k, w, -d] for k, w, d in reversed(e["elems"])]
        W = e["width"]
        lpark = 0.0
        for k, w, d in el:
            if k not in ("parking", "gutter"):
                break
            lpark += w
        rpark = 0.0
        for k, w, d in reversed(el):
            if k not in ("parking", "gutter"):
                break
            rpark += w
        res = (lat + W / 2 - lpark, lat - W / 2 + rpark)
    _BE_CACHE[key] = res
    return res


def column_options(p, t, side, offs=OFFS, t_track=None):
    """Valid column offsets on one side (+1 left / -1 right of t) at p, for a bent whose girder runs along left(t)."""
    n = left(t)
    ok = np.ones(len(offs), bool)
    for S, bad in ((_FS_IN, (2, 4, 5, 6, 7)), (_FS_OUT, ("cw",))):
        lx = S[:, 0][None, :] + (side * offs)[:, None]
        ly = S[:, 1][None, :]
        X = p[0] + n[0] * lx + t[0] * ly
        Y = p[1] + n[1] * lx + t[1] * ly
        pts = np.stack([X.ravel(), Y.ravel()], 1)
        if bad == ("cw",):
            ok &= ~crosswalk_near(pts).reshape(X.shape).any(1)
            continue
        g = ground(pts).reshape(X.shape)
        for b in bad:
            ok &= ~(g == b).any(1)
    # lane shadow: the travel lanes of the street under the L, 4-14 m up and down the street, must stay clear of the column's
    # inner face too (where the street narrows, the outer lane of the wider part would run the car straight into it)
    tt = t_track or t
    nt = left(tt)
    for along in (-14.0, -9.0, -4.0, 4.0, 9.0, 14.0):
        q = (p[0] + tt[0] * along, p[1] + tt[1] * along)
        be = band_edges(q, tt)
        if be is None:
            continue
        lft, rgt = be                      # signed offsets of the travel band edges at q (+ = left)
        # q is on the line through p along tt, so offsets compare directly
        edge = lft if side > 0 else -rgt
        ok &= (offs - FOOT[0] / 2 - FOOT_MARGIN) >= edge - 1e-6
    return offs[ok]


def pick(opts, pref):
    """Column offset: the curb line (COL_DEFAULT or just outside the carriageway) first, then steady along the street."""
    if len(opts) == 0:
        return None
    o = np.asarray(opts)
    cost = np.abs(o - COL_DEFAULT) + np.where(o >= COL_DEFAULT, 0.0, 0.6) + 0.25 * np.minimum(np.abs(o - pref), 1.5)
    return float(o[int(np.argmin(cost))])


def bent_at(name, s, prefL=COL_DEFAULT, prefR=COL_DEFAULT, wide=False):
    """A legal bent at s (square to the track if possible, else skewed up to 32 deg), or None."""
    p, t = P(name, s)
    for sk in SKEWS:
        tt = rot(t, sk)
        offs = WIDE_OFFS if wide else OFFS
        oL = column_options(p, tt, +1, offs, t)
        if len(oL) == 0:
            continue
        oR = column_options(p, tt, -1, offs, t)
        if len(oR) == 0:
            continue
        # the girder must still pass under both deck edges along its own (skewed) line
        cL, cR = pick(oL, prefL), pick(oR, prefR)
        if sk:
            reach = DECK_HALF / max(0.5, math.cos(math.radians(sk)))
            if cL < min(reach, 6.0) - 1.0 or cR < min(reach, 6.0) - 1.0:
                continue
        return {"route": name, "s": round(s, 2), "p": p, "t": t, "tb": tt, "skew": sk, "oL": cL, "oR": cR}
    return None


def bent_cost(b, k, prefL, prefR):
    return (abs(k - BENT) + 0.6 * (abs(b["oL"] - COL_DEFAULT) + abs(b["oR"] - COL_DEFAULT))
            + 0.15 * (abs(b["oL"] - prefL) + abs(b["oR"] - prefR)) + 0.12 * abs(b["skew"]))


def place_bents(name, s_start=0.0, s_end=None):
    """Greedy along the route: next bent 9-20 m on, then up to 30 m (two span modules), then up to 62 m (a truss span)."""
    r = ROUTES[name]
    L = r["len"] if s_end is None else s_end
    bents = []
    pref = [COL_DEFAULT, COL_DEFAULT]

    def add(b, flag=None):
        b["flag"] = flag
        bents.append(b)
        pref[0], pref[1] = b["oL"], b["oR"]

    b0 = None
    for ds in [k * 0.5 for k in range(0, 40)]:
        b0 = bent_at(name, s_start + ds) or bent_at(name, s_start + ds, wide=True)
        if b0:
            add(b0)
            break
    if not b0:
        issues.append(f"{name}: no legal first bent near s={s_start:.0f}")
        return bents
    while True:
        s_prev = bents[-1]["s"]
        if not r["closed"] and L - s_prev <= 20.0:
            if L - s_prev > 3.0:
                for ds in [0.0] + [-k * 0.5 for k in range(1, 16)]:
                    b = bent_at(name, L + ds) or bent_at(name, L + ds, wide=True)
                    if b and L + ds - s_prev > 3.0:
                        add(b, "end")
                        break
                else:
                    issues.append(f"{name}: no legal bent at the end s={L:.0f}")
            else:
                bents[-1]["flag"] = "end"
            break
        if r["closed"] and L - s_prev <= 22.0:
            if L - s_prev < 7.0 and len(bents) > 2:
                bents.pop()
            break
        best = None
        for lo, hi, pen, wide in ((9.0, 20.0, 0.0, False), (5.0, 30.0, 6.0, False), (5.0, 30.0, 9.0, True), (30.5, 62.0, 25.0, True)):
            k = lo
            while k <= hi + 1e-6:
                s = s_prev + k
                if s > (L - 3.0 if r["closed"] else L):
                    break
                b = bent_at(name, s, pref[0], pref[1], wide)
                if b:
                    c = bent_cost(b, k, pref[0], pref[1]) + pen
                    if best is None or c < best[0]:
                        best = (c, b, k)
                k += 0.5
            if best:
                break
        if best is None:
            # nothing legal within 62 m: keep looking further (a longer truss) rather than leave the line unsupported
            k = 62.5
            while k <= 120.0 and best is None:
                s = s_prev + k
                if s > (L - 3.0 if r["closed"] else L):
                    break
                b = bent_at(name, s, pref[0], pref[1], True)
                if b:
                    best = (0.0, b, k)
                k += 0.5
            p, t = P(name, s_prev + BENT)
            issues.append(f"{name}: no legal bent within 62 m after s={s_prev:.0f} ({p[0]:.0f},{p[1]:.0f})" + (f"; next at +{best[2]:.0f} m" if best else "; none within 120 m"))
            if best is None:
                break
        k = best[2]
        add(best[1], "truss" if k > 30.25 else "long" if k > 20.25 else None)
    return bents


def bent_columns(b):
    n = left(b["tb"])
    p = b["p"]
    return (p[0] + n[0] * b["oL"], p[1] + n[1] * b["oL"]), (p[0] - n[0] * b["oR"], p[1] - n[1] * b["oR"])


# ---------------------------------------------------------------- stations
STATIONS = [
    # name, route, approximate centre (plan m) between the real station's cross streets
    ("State/Lake", "LOOP", (25, -200)),                                    # Lake St, State - Wabash
    ("Washington/Wabash", "LOOP", (131, -541)),                            # Wabash, Washington - Madison
    ("Adams/Wabash", "LOOP", (136, -817)),                                 # Wabash, Monroe - Adams
    ("Harold Washington Library-State/Van Buren", "LOOP", (-33, -1177)),   # Van Buren, State - Plymouth
    ("LaSalle/Van Buren", "LOOP", (-326, -1182)),                          # Van Buren, Clark - Financial Pl (LaSalle is on the Austin side)
    ("Quincy", "LOOP", (-494, -973)),                                      # Wells, Adams - Jackson
    ("9th Street (terminal)", "SOUTH", None),                              # end of the South Side line, 8th - 9th St
]
STAIR_D = [round(0.5 * k, 1) for k in range(0, 17)]          # bridge from the platform to the stair: 0..8 m
TERMINAL_GAP = 7.0                                            # platform end to the end of the deck (bumpers in between)


def chord_dev(name, s0, s1):
    a, _ = P(name, s0)
    b, _ = P(name, s1)
    ch = (b[0] - a[0], b[1] - a[1])
    lc = math.hypot(*ch) or 1.0
    dev = 0.0
    s = s0
    while s <= s1:
        m, _ = P(name, s)
        dev = max(dev, abs((m[0] - a[0]) * ch[1] - (m[1] - a[1]) * ch[0]) / lc)
        s += 2.0
    return dev, a, b


def module_frame(A, u, i, side):
    """Platform module i of a station (start A, direction u): (start, end) of the side module's own frame.
    The kit models one platform side as +X of a module running start -> end; +X is the LEFT of start -> end
    (verified in the editor), so the left platform runs A->B and the right one B->A."""
    pa = (A[0] + u[0] * PLAT_L * i, A[1] + u[1] * PLAT_L * i)
    pb = (pa[0] + u[0] * PLAT_L, pa[1] + u[1] * PLAT_L)
    return (pa, pb) if side > 0 else (pb, pa)


def stair_geom(fa, fb, d):
    """Stair tower footprint and entrance zone for a side module frame fa->fb with a d m bridge."""
    u = unit((fb[0] - fa[0], fb[1] - fa[1]))
    n = left(u)
    x0, x1 = PLAT_OUT + d, PLAT_OUT + d + STAIR_W

    def Q(x, y):
        return (fa[0] + n[0] * x + u[0] * y, fa[1] + n[1] * x + u[1] * y)
    tower = [Q(x0, 0.0), Q(x1, 0.0), Q(x1, STAIR_L), Q(x0, STAIR_L)]
    foot = [Q(x0, -1.8), Q(x1, -1.8), Q(x1, 0.2), Q(x0, 0.2)]
    bridge = [Q(PLAT_OUT, 14.04), Q(x0 + 0.01, 14.04), Q(x0 + 0.01, 16.44), Q(PLAT_OUT, 16.44)] if d > 0 else None
    return tower, foot, bridge


COLUMN_RECTS = []          # filled in build(): footings of the placed bents (stairs keep 0.5 m off them)


def clear_of_columns(corners):
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    box = (min(xs) - 2, min(ys) - 2, max(xs) + 2, max(ys) + 2)
    P_ = np.array(rect_samples(corners, 9))
    for c, r in COLUMN_RECTS:
        if box[0] <= c[0] <= box[2] and box[1] <= c[1] <= box[3]:
            if points_in_poly(P_, np.array(r)).any():
                return False
            # also the column inside the stair
            if points_in_poly(np.array(r), np.array(corners)).any():
                return False
    return True


def plan_station(spec, taken):
    name, route, centre = spec
    nmod = 4
    if centre is None:                                          # terminal: platform ends TERMINAL_GAP before the deck end
        L = ROUTES[route]["len"]
        s_hi = L - TERMINAL_GAP
        s_8th = street_crossing_s(route, "East 8th Street")
        if s_8th is not None and s_hi - nmod * PLAT_L < s_8th + 9:      # keep the platform clear of 8th Street's junction
            nmod = max(3, int((s_hi - s_8th - 9) // PLAT_L))
        centres = [s_hi - nmod * PLAT_L / 2]
    else:
        c, d = route_s_of(route, centre)
        if d > 15:
            issues.append(f"station {name}: {route} passes {d:.0f} m from {centre}")
        centres = [c + k for k in sorted(range(-40, 41, 2), key=abs)]
    st2 = centre
    best = None
    for nm in ([nmod, nmod - 1] if st2 else [nmod]):
        half = nm * PLAT_L / 2
        for sc in centres:
            s0, s1 = sc - half, sc + half
            if not ROUTES[route]["closed"] and (s0 < 0 or s1 > ROUTES[route]["len"]):
                continue
            if any(not (s1 < a - 10 or s0 > b + 10) for a, b in taken):
                continue
            dev, A, B = chord_dev(route, s0, s1)
            if dev > 0.6:
                continue
            u = unit((B[0] - A[0], B[1] - A[1]))
            stairs = []
            for i in (0, nm - 1):
                for side in (+1, -1):
                    fa, fb = module_frame(A, u, i, side)
                    for d in STAIR_D:
                        tower, foot, bridge = stair_geom(fa, fb, d)
                        if stair_ok(tower, foot) is None and clear_of_columns(tower):
                            stairs.append({"module": i, "side": side, "d": d, "tower": tower, "foot": foot, "bridge": bridge})
                            break
            sides = {st_["side"] for st_ in stairs}
            score = 10 * len(stairs) + 15 * len(sides) - 0.3 * abs(sc - centres[0]) - 25 * (nmod - nm) - sum(st_["d"] for st_ in stairs)
            if best is None or score > best[0]:
                best = (score, {"name": name, "route": route, "s0": s0, "s1": s1, "A": A, "B": B, "u": u, "nmod": nm, "stairs": stairs, "dev": dev})
        if best and len(best[1]["stairs"]) >= 2:
            break
    if best is None:
        issues.append(f"station {name}: no straight, free stretch found")
        return None
    return best[1]


# ---------------------------------------------------------------- the whole layout
def build():
    # SOUTH ends where a bent can stand (just short of 9th Street's junction)
    lay = {"frame": "plan metres, x east, y north (Unreal X = y*100, Y = x*100)", "kit": "SourceArt/Rail (Scripts/rail/blender_l_kit.py)"}
    bents = {}
    for name in ("LOOP", "SOUTH", "WYE"):
        bents[name] = place_bents(name)
    # the SOUTH deck ends on its last bent (just short of 9th Street's junction ring)
    last = bents["SOUTH"][-1]
    if last["s"] < ROUTES["SOUTH"]["len"] - 0.05:
        r = ROUTES["SOUTH"]
        r["pts"] = sub_polyline(r["pts"], r["s"], 0.0, last["s"])
        r["s"] = cumlen(r["pts"])
        r["len"] = r["s"][-1]
    # SOUTH and WYE join the Loop's deck: drop their bents where the Loop already stands (columns within 3 m)
    keep = list(bents["LOOP"])
    for name in ("SOUTH", "WYE"):
        for b in bents[name]:
            cols = bent_columns(b)
            clash = False
            for k in keep:
                kc = bent_columns(k)
                if min(dist(c1, c2) for c1 in cols for c2 in kc) < 3.0 or (dist(b["p"], k["p"]) < 4.0 and abs(b["t"][0] * k["t"][0] + b["t"][1] * k["t"][1]) > 0.97):
                    clash = True
                    break
            if not clash:
                keep.append(b)
            else:
                stats["bents_merged_at_junctions"] += 1
    all_bents = keep
    COLUMN_RECTS.clear()
    for b in all_bents:
        for c in bent_columns(b):
            COLUMN_RECTS.append((c, rect(c, b["tb"], FOOT[0] + 1.0, FOOT[1] + 1.0)))
    # stations
    stations, taken = [], collections.defaultdict(list)
    for spec in STATIONS:
        stn = plan_station(spec, taken[spec[1]])
        if stn:
            stations.append(stn)
            taken[spec[1]].append((stn["s0"], stn["s1"]))
    # deck chords -> span modules (J where another route's deck overlaps), collision slabs
    spans = []
    for name, r in ROUTES.items():
        ss = deck_chords(name)
        for s0, s1 in zip(ss, ss[1:]):
            a, _ = P(name, s0)
            b, _ = P(name, s1)
            m, _ = P(name, (s0 + s1) / 2)
            ov = set(deck_overlap(name, a)) | set(deck_overlap(name, b)) | set(deck_overlap(name, m))
            for k in ov:
                stats[f"J_{name}_{k}"] += 1
            spans.append({"route": name, "s0": round(s0, 2), "s1": round(s1, 2), "a": a, "b": b, "len": round(dist(a, b), 3),
                          "kind": ("15" if s1 - s0 > BENT * 0.6 else "5") + ("J" if ov else "")})
    # trusses over the long gaps
    trusses = []
    for name in ROUTES:
        bl = sorted([b for b in all_bents if b["route"] == name], key=lambda b: b["s"])
        for b1, b2 in zip(bl, bl[1:]):
            if b2["s"] - b1["s"] > 30.25 and b2.get("flag") == "truss":
                dev, A, B = chord_dev(name, b1["s"], b2["s"])
                trusses.append({"route": name, "a": A, "b": B, "len": round(dist(A, B), 2), "sag": round(dev, 2)})
    # terminal: bumpers + end fence at the end of SOUTH
    L = ROUTES["SOUTH"]["len"]
    pe, te = P("SOUTH", L)
    pb_, tb_ = P("SOUTH", L - 1.2)
    ends = {"bumpers": [{"p": pb_, "t": tb_}], "fences": [{"p": pe, "t": te}]}
    lay.update({"routes": {k: {"len": round(r["len"], 1), "closed": r["closed"], "pts": [[round(x, 2), round(y, 2)] for x, y in r["pts"][::2]]}
                           for k, r in ROUTES.items()},
                "bents": all_bents, "spans": spans, "trusses": trusses, "stations": stations, "ends": ends})
    return lay


def footprint(lay):
    """Deck, column and stair polygons for other agents (roadnet.py can keep furniture out of them)."""
    deck = []
    for sp in lay["spans"]:
        u = unit((sp["b"][0] - sp["a"][0], sp["b"][1] - sp["a"][1]))
        m = ((sp["a"][0] + sp["b"][0]) / 2, (sp["a"][1] + sp["b"][1]) / 2)
        deck.append([[round(x, 2), round(y, 2)] for x, y in rect(m, u, 2 * DECK_HALF + 0.2, sp["len"] + 0.4)])
    cols = []
    for b in lay["bents"]:
        for c in bent_columns(b):
            cols.append([[round(x, 2), round(y, 2)] for x, y in rect(c, b["tb"], FOOT[0], FOOT[1])])
    plats, stairs = [], []
    for stn in lay["stations"]:
        A, u = stn["A"], stn["u"]
        L = stn["nmod"] * PLAT_L
        m = (A[0] + u[0] * L / 2, A[1] + u[1] * L / 2)
        plats.append([[round(x, 2), round(y, 2)] for x, y in rect(m, u, 2 * PLAT_OUT, L)])
        for st_ in stn["stairs"]:
            stairs.append([[round(x, 2), round(y, 2)] for x, y in st_["tower"]])
            stairs.append([[round(x, 2), round(y, 2)] for x, y in st_["foot"]])
    return {"frame": lay["frame"], "why": "the elevated L (Scripts/rail/l_layout.py): keep street furniture out of these",
            "deck": deck, "platforms": plats, "columns": cols, "stairs": stairs}


def under_deck_conflicts(lay):
    """Road props and signal heads under the deck or platforms (they'd poke through the structure)."""
    polys = [np.array(p) for p in footprint(lay)["deck"]] + [np.array(p) for p in footprint(lay)["platforms"]]
    boxes = [(p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()) for p in polys]

    def inside(q):
        for P_, (a, b, c, d) in zip(polys, boxes):
            if a <= q[0] <= c and b <= q[1] <= d and points_in_poly(np.array([q]), P_)[0]:
                return True
        return False
    tall = {"tree", "lamp", "lamp_hw", "shelter", "busstop", "namesign"}
    props = [{"t": q["t"], "p": q["p"]} for q in RN["props"] if q["t"] in tall and RX0 < q["p"][0] < RX1 and RY0 < q["p"][1] < RY1 and inside(q["p"])]
    heads = [{"p": h["p"], "z": h.get("z"), "unit": h.get("unit")} for h in RN["signals"]["heads"]
             if RX0 < h["p"][0] < RX1 and RY0 < h["p"][1] < RY1 and inside(h["p"])]
    poles = [{"p": h["p"], "arm": h.get("arm")} for h in RN["signals"]["poles"] if RX0 < h["p"][0] < RX1 and RY0 < h["p"][1] < RY1 and inside(h["p"])]
    return {"props": props, "signal_heads": heads, "signal_poles": poles}


def jsonable(o):
    if isinstance(o, dict):
        return {k: jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return round(float(o), 3)
    if isinstance(o, np.integer):
        return int(o)
    return o


PAL = np.array([[48, 52, 48], [90, 90, 110], [70, 70, 75], [230, 230, 230], [150, 60, 170], [190, 120, 60], [30, 60, 120], [95, 88, 70]], np.uint8)


def render_layout(lay, box, path, scale=3.0):
    x0, y0, x1, y1 = box
    i0, i1 = int((x0 - RX0) / RES), int((x1 - RX0) / RES)
    j0, j1 = int((RY1 - y1) / RES), int((RY1 - y0) / RES)
    crop = PAL[GROUND[max(0, j0):j1, max(0, i0):i1]]
    im = Image.fromarray(crop).resize((int((x1 - x0) * scale), int((y1 - y0) * scale)), Image.NEAREST)
    d = ImageDraw.Draw(im)

    def T(p):
        return ((p[0] - x0) * scale, (y1 - p[1]) * scale)
    for sp in lay["spans"]:
        u = unit((sp["b"][0] - sp["a"][0], sp["b"][1] - sp["a"][1]))
        m = ((sp["a"][0] + sp["b"][0]) / 2, (sp["a"][1] + sp["b"][1]) / 2)
        d.polygon([T(q) for q in rect(m, u, 2 * DECK_HALF, sp["len"])], outline=(90, 200, 255) if "J" not in sp["kind"] else (255, 120, 255))
    for tr in lay["trusses"]:
        d.line([T(tr["a"]), T(tr["b"])], fill=(255, 255, 0), width=max(1, int(scale)))
    for stn in lay["stations"]:
        A, u = stn["A"], stn["u"]
        L = stn["nmod"] * PLAT_L
        m = (A[0] + u[0] * L / 2, A[1] + u[1] * L / 2)
        d.polygon([T(q) for q in rect(m, u, 2 * PLAT_OUT, L)], outline=(255, 255, 255))
        for st_ in stn["stairs"]:
            d.polygon([T(q) for q in st_["tower"]], fill=(255, 140, 0))
            d.polygon([T(q) for q in st_["foot"]], outline=(255, 220, 120))
            if st_["bridge"]:
                d.polygon([T(q) for q in st_["bridge"]], fill=(255, 200, 80))
        d.text(T(m), stn["name"].split("-")[0], fill=(255, 255, 255))
    for b in lay["bents"]:
        cl, cr = bent_columns(b)
        col = (255, 170, 0) if b.get("flag") in ("long", "truss") else (60, 255, 90)
        d.line([T(cl), T(cr)], fill=col, width=max(1, int(scale * 0.4)))
        for c in (cl, cr):
            d.polygon([T(q) for q in rect(c, b["tb"], FOOT[0], FOOT[1])], fill=col)
    for e in lay["ends"]["fences"]:
        n = left(e["t"])
        d.line([T((e["p"][0] + n[0] * 5, e["p"][1] + n[1] * 5)), T((e["p"][0] - n[0] * 5, e["p"][1] - n[1] * 5))], fill=(255, 0, 0), width=3)
    im.save(path)


def deck_clear(lay):
    """Building / landmark / water cells under the deck (|lateral| <= deck half + 0.5) or under the platforms."""
    hits = []
    for name, r in ROUTES.items():
        s = 0.0
        while s < r["len"]:
            p, t = P(name, s)
            n = left(t)
            for o in np.arange(-DECK_HALF - 0.5, DECK_HALF + 0.51, 0.5):
                q = (p[0] + n[0] * o, p[1] + n[1] * o)
                if ground([q])[0] == 4:
                    hits.append((name, round(s), round(q[0]), round(q[1])))
                    break
            s += 1.0
    for stn in lay["stations"]:
        A, u = stn["A"], stn["u"]
        n = left(u)
        for k in range(int(stn["nmod"] * PLAT_L)):
            for o in (-PLAT_OUT, PLAT_OUT):
                q = (A[0] + u[0] * k + n[0] * o, A[1] + u[1] * k + n[1] * o)
                if ground([q])[0] == 4:
                    hits.append((stn["name"], k, round(q[0]), round(q[1])))
    return hits


# ---------------------------------------------------------------- placements for build_l_ue.py
TIE_TOP = KIT["track"]["tie_top_z"]
GIRDER_UNIT = 10.9
TRUSS_L, TRUSS_X = 45.0, 4.95
Z_J = {"LOOP": 0.0, "SOUTH": 0.012, "WYE": 0.024}       # overlapping junction decks: a hair apart (no z-fighting)


def instances(lay):
    """Every kit piece as [origin x, origin y, forward x, forward y, z, scale x, scale y, scale z] in plan metres.
    Kit frame (all pieces): forward = the module's run direction (Blender -Y), +X = left of forward, z up from the street."""
    I = collections.defaultdict(list)

    def put(mesh, o, f, z=0.0, sx=1.0, sy=1.0, sz=1.0):
        f = unit(f)
        I[mesh].append([round(o[0], 3), round(o[1], 3), round(f[0], 5), round(f[1], 5), round(z, 3), round(sx, 4), round(sy, 4), round(sz, 4)])
    for b in lay["bents"]:
        cl, cr = bent_columns(b)
        tb = b["tb"]
        put("L_BentColumn", cl, (-tb[0], -tb[1]))               # knee brace (+X) toward the track
        put("L_BentColumn", cr, tb)
        n = left(tb)
        c = (b["p"][0] + n[0] * (b["oL"] - b["oR"]) / 2, b["p"][1] + n[1] * (b["oL"] - b["oR"]) / 2)
        put("L_BentGirder", c, tb, sx=(b["oL"] + b["oR"] + 0.9) / GIRDER_UNIT)
    for sp in lay["spans"]:
        f = (sp["b"][0] - sp["a"][0], sp["b"][1] - sp["a"][1])
        base = BENT if sp["kind"].startswith("15") else SPAN_S
        mesh = "L_Span15" if sp["kind"].startswith("15") else "L_Span5"
        J = sp["kind"].endswith("J")
        put(mesh + ("J" if J else ""), sp["a"], f, z=Z_J[sp["route"]] if J else 0.0, sy=sp["len"] / base)
        put("L_DeckSlab", sp["a"], f, z=TIE_TOP + (Z_J[sp["route"]] if J else 0.0), sx=2 * 4.45, sy=sp["len"], sz=TOR - TIE_TOP)
    for tr in lay["trusses"]:
        f = (tr["b"][0] - tr["a"][0], tr["b"][1] - tr["a"][1])
        put("L_Truss", tr["a"], f, sx=max(1.0, (DECK_HALF + 0.3 + tr["sag"]) / TRUSS_X), sy=tr["len"] / TRUSS_L)
    for k, stn in enumerate(lay["stations"]):
        A, u = stn["A"], stn["u"]
        at_ = {(st_["module"], st_["side"]): st_ for st_ in stn["stairs"]}
        house_done = False
        for i in range(stn["nmod"]):
            for side in (+1, -1):
                fa, fb = module_frame(A, u, i, side)
                f = (fb[0] - fa[0], fb[1] - fa[1])
                st_ = at_.get((i, side))
                put("L_PlatSide30_Stair" if st_ else "L_PlatSide30", fa, f)
                if st_:
                    n = left(unit(f))
                    d = st_["d"]
                    put("L_StationStairs", (fa[0] + n[0] * d, fa[1] + n[1] * d), f)
                    if d > 0:
                        put("L_StairBridge", (fa[0] + n[0] * PLAT_OUT, fa[1] + n[1] * PLAT_OUT), f, sx=d)
                    if not house_done:
                        put("L_StationHouse", fa, f)
                        house_done = True
        if k % 2 == 0:                                          # a parked 4-car train on the right-hand track
            n = left(u)
            Ls = stn["nmod"] * PLAT_L
            for c in range(min(4, stn["nmod"] + 1)):
                d_ = 8.0 + 7.3 + c * 14.9
                if d_ + 7.3 > Ls:
                    break
                put("L_TrainCar", (A[0] + u[0] * d_ - n[0] * 1.9, A[1] + u[1] * d_ - n[1] * 1.9), u, z=TOR)
    for e in lay["ends"]["bumpers"]:
        put("L_Bumper", P("SOUTH", ROUTES["SOUTH"]["len"])[0], (-e["t"][0], -e["t"][1]))
    for e in lay["ends"]["fences"]:
        put("L_EndFence", e["p"], (-e["t"][0], -e["t"][1]))
    return dict(I)


def verify(lay):
    """Independent check of the placements: every column footing and stair tower against the ground raster."""
    bad = collections.Counter()
    where = []
    for row in lay["instances"].get("L_BentColumn", []):
        o, fwd = (row[0], row[1]), (row[2], row[3])
        why = footing_ok(o, fwd, margin=0.15, cw=1.5)
        if why:
            bad["column " + why] += 1
            where.append((round(o[0], 1), round(o[1], 1), why))
    for row in lay["instances"].get("L_StationStairs", []):
        o, fwd = (row[0], row[1]), unit((row[2], row[3]))
        n = left(fwd)

        def Q(x, y):
            return (o[0] + n[0] * x + fwd[0] * y, o[1] + n[1] * x + fwd[1] * y)
        tower = [Q(PLAT_OUT, 0.0), Q(PLAT_OUT + STAIR_W, 0.0), Q(PLAT_OUT + STAIR_W, STAIR_L), Q(PLAT_OUT, STAIR_L)]
        g = ground(rect_samples(tower, 9))
        if (g > 0).any():
            bad["stair on " + CODE_NAME[int(g.max())]] += 1
            where.append((round(o[0], 1), round(o[1], 1), "stair"))
    return {"problems": dict(bad), "where": where[:50], "columns": len(lay["instances"].get("L_BentColumn", [])),
            "stairs": len(lay["instances"].get("L_StationStairs", []))}


if __name__ == "__main__" and not any(a.startswith("--") for a in sys.argv[1:]):
    lay = build()
    fp = footprint(lay)
    conf = under_deck_conflicts(lay)
    lay["under_deck"] = conf
    lay["deck_hits"] = deck_clear(lay)
    lay["instances"] = instances(lay)
    lay["verify"] = verify(lay)
    lay["issues"] = issues
    lay["stats"] = dict(stats)
    json.dump(jsonable(lay), open(OUTD / "l_layout.json", "w"))
    json.dump(jsonable(fp), open(OUTD / "l_footprint.json", "w"))
    render_layout(lay, (-620, -1990, 280, -120), OUTD / "l_layout.png", 1.2)
    for nm, box in {"tower12": (60, -1260, 200, -1100), "lake": (-140, -260, 160, -150), "arc_apron": (-400, -320, -220, -200),
                    "south_end": (90, -1890, 220, -1700), "wells_vanburen": (-540, -1220, -420, -1000)}.items():
        render_layout(lay, box, OUTD / f"l_layout_{nm}.png", 5.0)
    print("routes", {k: round(r["len"]) for k, r in ROUTES.items()})
    print("bents", len(lay["bents"]), collections.Counter(b.get("flag") for b in lay["bents"]), "skewed", sum(1 for b in lay["bents"] if b["skew"]))
    print("spans", collections.Counter(sp["kind"] for sp in lay["spans"]), "trusses", [(t_["route"], t_["len"], t_["sag"]) for t_ in lay["trusses"]])
    for stn in lay["stations"]:
        print(f"station {stn['name']:45s} {stn['route']} s {stn['s0']:7.1f}-{stn['s1']:7.1f} modules {stn['nmod']} dev {stn['dev']:.2f} stairs",
              [(st_['module'], st_['side'], st_['d']) for st_ in stn['stairs']])
    print("under deck:", {k: len(v) for k, v in conf.items()}, collections.Counter(q["t"] for q in conf["props"]))
    print("deck/platform over buildings:", len(lay["deck_hits"]), lay["deck_hits"][:10])
    print("instances", {k: len(v) for k, v in lay["instances"].items()})
    print("verify", lay["verify"])
    print("stats", dict(stats))
    print("\n".join(issues))




if __name__ == "__main__" and "--verify-built" in sys.argv:
    # re-check the placements in Saved/Rail/l_layout.json (what build_l_ue.py placed) against the CURRENT roadnet.json
    built = json.load(open(OUTD / "l_layout.json"))
    print("verify-built", verify({"instances": built["instances"]}))
