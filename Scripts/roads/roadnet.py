"""Sky City road network v2: one connected street graph where every road has a designed cross-section and every
intersection a designed junction, then the markings, signals, signs and street furniture that follow from them.

Why: the first street pass drew each OpenStreetMap piece on its own (round end caps, markings that ignored the
roads they met, signals by guesswork). Here each thing has a rule and a reason, written next to it in the code and
carried into the output ("why" fields), so it can be checked against real-world practice.

Pipeline (all offline, plan frame: metres, x east, y north):
  1. graph      plan roads (with OSM lanes / one-way / speed from street_data.json) noded at every crossing and
                T-junction, endpoints snapped, pieces of the same street merged, dangling stubs removed, dead ends
                either joined to the street they stop short of or given a proper dead-end treatment
  2. sections   every edge gets a cross-section: travel lanes by direction, centre treatment (double yellow, or a
                two-way left-turn lane when OSM gives an odd lane count), parking lanes, a gutter pan taken from the
                outer lane or stall (the carriageway width does not change), a beveled curb, shoulders on expressways,
                sidewalk and parkway widths, all from the rules in SECTION_RULES and Scripts/roads/profiles.py;
                widths are what the parts add up to
  3. junctions  curb-return geometry per intersection (corner radius by street class), compound junctions where
                divided roads make two nodes, crosswalk and stop-line positions, the roads trimmed to the junction
  4. control    signal / all-way stop / two-way stop from OSM plus warrant-style rules; movements that are legal
                (no turning into a one-way the wrong way); signal heads one per inbound lane on a far-side mast arm,
                in phase groups by approach axis; pedestrian heads; ONE WAY, DO NOT ENTER, STOP, DEAD END signs
  5. markings   lane lines, centre lines, parking lines, edge lines, turn pockets, lane-use arrows with ONLY,
                continental crosswalks, stop bars
  6. furniture  lamps, trees, hydrants, bins, benches, bus stops, racks, cabinets placed by rules (corners, spacing,
                sidewalk zones), never in the roadway, never in front of a crosswalk
Output: Saved/Roads/roadnet.json (+ debug renders Saved/Roads/*.png). Data (c) OpenStreetMap contributors, ODbL.
Run: python3 -I Scripts/roads/roadnet.py [--wip] [--debug]
  --wip   write roadnet.json and traffic.json to Saved/Roads/wip/ only (not the live Saved/Roads/roadnet.json, nor the
          game's Content/SkyCity/Data/traffic.json): for trying rule changes while other agents read the live files
"""
import collections, json, math, pathlib, sys, zlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import profiles as road_profiles
import networkx as nx
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
SD = json.load(open(ROOT / "Saved/Streets/street_data.json"))
PLAN = json.load(open(ROOT / "Saved/Mashup/plan_v3.json"))
BLD = json.load(open(ROOT / "Saved/Mashup/buildings_v3.json"))["buildings"]
WIP = "--wip" in sys.argv
OUTP = ROOT / ("Saved/Roads/wip/roadnet.json" if WIP else "Saved/Roads/roadnet.json")
DRIVE = ("highway", "major", "mid", "minor")
BX0, BY0, BX1, BY1 = PLAN["bounds"]
stats = collections.Counter()


def h32(*a):
    return zlib.crc32(repr(a).encode()) & 0xffffffff


def rnd(*a):
    return h32(*a) / 4294967296.0


# ---------------------------------------------------------------- geometry helpers
def unit(v):
    L = math.hypot(v[0], v[1]) or 1e-12
    return (v[0] / L, v[1] / L)


def cumlen(pts):
    s = [0.0]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + math.dist(a, b))
    return s


def at_s(pts, s_cum, s):
    s = max(0.0, min(s_cum[-1], s))
    i = max(0, min(len(pts) - 2, int(np.searchsorted(s_cum, s, side="right")) - 1))
    a, b = pts[i], pts[i + 1]
    seg = (s_cum[i + 1] - s_cum[i]) or 1e-9
    t = (s - s_cum[i]) / seg
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), unit((b[0] - a[0], b[1] - a[1]))


def sub_polyline(pts, s_cum, s0, s1):
    if s1 - s0 < 0.05:
        return []
    out = [at_s(pts, s_cum, s0)[0]]
    for p, s in zip(pts, s_cum):
        if s0 + 1e-6 < s < s1 - 1e-6:
            out.append(p)
    out.append(at_s(pts, s_cum, s1)[0])
    return out


def offset_polyline(pts, off):
    """Offset to the left by off (negative = right), mitred (mitre limited)."""
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


def closest_on_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy or 1e-12
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    q = (a[0] + dx * t, a[1] + dy * t)
    return q, t, math.dist(p, q)


def seg_x(a, b, c, d):
    r = (b[0] - a[0], b[1] - a[1]); s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-9:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return (a[0] + r[0] * t, a[1] + r[1] * t), t, u
    return None


def line_x(p, d, q, e):
    """Intersection of lines p + t d and q + u e: (point, t, u) or None if parallel."""
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-6:
        return None
    w = (q[0] - p[0], q[1] - p[1])
    t = (w[0] * e[1] - w[1] * e[0]) / den
    u = (w[0] * d[1] - w[1] * d[0]) / den
    return (p[0] + d[0] * t, p[1] + d[1] * t), t, u


def poly_area(ring):
    a = 0.0
    for i in range(len(ring)):
        p, q = ring[i], ring[(i + 1) % len(ring)]
        a += p[0] * q[1] - q[0] * p[1]
    return a / 2


def convex_hull(pts):
    pts = sorted(set((round(p[0], 3), round(p[1], 3)) for p in pts))
    if len(pts) < 3:
        return pts
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


class SegGrid:
    def __init__(self, cell=25.0):
        self.cell, self.g, self.segs = cell, collections.defaultdict(list), []

    def add(self, a, b, payload):
        i = len(self.segs)
        self.segs.append((a, b, payload))
        c = self.cell
        for gx in range(int(math.floor(min(a[0], b[0]) / c)), int(math.floor(max(a[0], b[0]) / c)) + 1):
            for gy in range(int(math.floor(min(a[1], b[1]) / c)), int(math.floor(max(a[1], b[1]) / c)) + 1):
                self.g[(gx, gy)].append(i)
        return i

    def near(self, p, r):
        c = self.cell
        seen = set()
        for gx in range(int(math.floor((p[0] - r) / c)), int(math.floor((p[0] + r) / c)) + 1):
            for gy in range(int(math.floor((p[1] - r) / c)), int(math.floor((p[1] + r) / c)) + 1):
                for i in self.g.get((gx, gy), ()):
                    if i not in seen:
                        seen.add(i)
                        yield i, self.segs[i]


# land mask (water outer rings minus islands)
from skimage.measure import points_in_poly  # noqa: E402


def ring_tester(rings):
    rings = [np.array(r, float) for r in rings if len(r) >= 3]
    boxes = [(r[:, 0].min(), r[:, 1].min(), r[:, 0].max(), r[:, 1].max()) for r in rings]

    def test(pts):
        pts = np.asarray(pts, float).reshape(-1, 2)
        hit = np.zeros(len(pts), bool)
        for r, (a, b, c, d) in zip(rings, boxes):
            m = (pts[:, 0] >= a) & (pts[:, 0] <= c) & (pts[:, 1] >= b) & (pts[:, 1] <= d) & ~hit
            if m.any():
                hit[m] = points_in_poly(pts[m], r)
        return hit
    return test


in_water = ring_tester(PLAN["water"]["outer"])
in_island = ring_tester(PLAN["water"]["inner"])


def on_land(p):
    # beyond the plan's bounds there is only the lake (build_city's horizon water): never land
    if not (BX0 <= p[0] <= BX1 and BY0 <= p[1] <= BY1):
        return False
    return bool((~in_water([p]) | in_island([p]))[0])


# The elevated expressways (agent highway-capitol, Scripts/roads/expressway_layout.py) publish their footprint in the
# L's format (Saved/Expressway/expressway_footprint.json): decks (no trees within 3.5 m, no lamps or signs within 1 m),
# columns (nothing within 0.5 m) and ramp fills (solid embankments: nothing on them, no pavement either). Where a ramp
# comes down to grade (the layout's "grade" ends) the road goes on up the ramp: the street piece that ends there is not
# a dead end (no DEAD END sign, no barricade, not removed as a leftover).
X_FP = {"deck": [], "posts": [], "fill": [], "fill_cut": []}
X_FEET = []
_xfp = ROOT / "Saved/Expressway/expressway_footprint.json"
_xlay = ROOT / "Saved/Expressway/expressway_layout.json"
if _xfp.exists():
    _j = json.load(open(_xfp))
    X_FP["deck"] = [np.array(r, float) for r in _j.get("deck", []) + _j.get("platforms", []) if len(r) >= 3]
    X_FP["posts"] = [np.array(r, float) for r in _j.get("columns", []) + _j.get("stairs", []) if len(r) >= 3]
    X_FP["fill"] = [np.array(r, float) for r in _j.get("fill", []) if len(r) >= 3]
if _xlay.exists():
    _jl = json.load(open(_xlay))
    for _key, _rd in _jl.get("roads", {}).items():
        _c = _rd.get("centre") or []
        for _end, _q in zip(_rd.get("ends", []), (_c[:1] + _c[-1:]) if _c else []):
            if _end == "grade" and len(_q) >= 3 and _q[2] <= 0.2:
                X_FEET.append((float(_q[0]), float(_q[1])))
        # streets are cut where the I-35's ramp fills cover them (highway-capitol request 2: Trinity Street under the west
        # ramp); the Wacker Canal Expressway's fills sit on South Wacker Drive and the Crosstown Parkway, which stay (reported
        # back to highway-capitol in NOTES/seam-junctions-2026-10-20.md)
        if _key == "i35":
            X_FP["fill_cut"] += [np.array(r, float) for r in _rd.get("footprint", {}).get("fill", []) if len(r) >= 3]
stats["expressway_footprint"] = {k: len(v) for k, v in X_FP.items()} | {"feet": len(X_FEET)}


def at_foot(p, r=18.0):
    return any(math.dist(p, f) < r for f in X_FEET)


def in_polys(p, polys, margin=0.0):
    q = np.array([p[:2]], float)
    for r in polys:
        if r[:, 0].min() - margin <= p[0] <= r[:, 0].max() + margin and r[:, 1].min() - margin <= p[1] <= r[:, 1].max() + margin:
            if points_in_poly(q, r)[0]:
                return True
            if margin > 0:
                a, b = r, np.roll(r, -1, axis=0)
                dd = b - a
                L2 = (dd ** 2).sum(1)
                L2[L2 == 0] = 1e-12
                t = np.clip(((q - a) * dd).sum(1) / L2, 0, 1)
                if np.sqrt(((a + dd * t[:, None] - q) ** 2).sum(1)).min() < margin:
                    return True
    return False


def near_bounds(p, d=60.0):
    # the map's edge (the city goes on beyond it) or an expressway ramp's foot (the road goes on up the ramp)
    return p[0] < BX0 + d or p[0] > BX1 - d or p[1] < BY0 + d or p[1] > BY1 - d or at_foot(p)


# ================================================================ 1. GRAPH
# Corrections to the mashup's connector roads at the Chicago-Austin seam (Scripts/mashup/seam_fixes.py, rules R1-R5 in
# its docstring): attributes for the stitch and sketch roads (they had inherited the lanes and one-way of whatever OSM
# way lay nearest), sketch roads cut where they run on top of existing streets (the street takes the sketch road's
# design), scribbles dropped, the Seam Circle as a real roundabout (nothing crossing its island), frontage roads beside
# their main street dropped in the seam zone. Applied here by plan index; plan_v3.json itself is left as it is.
FIX_P = ROOT / "Saved/Mashup/seam_fixes.json"
FIX = json.load(open(FIX_P)) if FIX_P.exists() else {"attrs": {}, "drop": {}, "parts": {}}
_roads_in = []
for r in SD["roads"]:
    key_ = str(r.get("plan_i", -1))
    if key_ in FIX["drop"]:
        stats["seam_fix_dropped"] += 1
        continue
    r = dict(r)
    r["rb"] = False
    a_ = FIX["attrs"].get(key_)
    if a_:
        for k_ in ("cls", "lanes", "oneway", "reverse", "speed", "name"):
            if k_ in a_:
                r[k_] = a_[k_]
        r["rb"] = bool(a_.get("roundabout"))
        stats["seam_fix_attrs"] += 1
    if key_ in FIX["parts"]:
        for part in FIX["parts"][key_]:
            _roads_in.append(dict(r, pts=[tuple(q) for q in part]))
        stats["seam_fix_recut"] += 1
    else:
        _roads_in.append(r)
# new roads the fixes add (R7: the I-35's frontage roads and lower lanes, highway-capitol's requests)
for _k, a_ in enumerate(FIX.get("add", [])):
    _roads_in.append({"i": -1 - _k, "plan_i": -1 - _k, "cls": a_["cls"], "name": a_["name"], "city": a_.get("city", "austin"),
                      "frontage": "Frontage" in a_["name"] or bool(a_.get("narrow")),
                      "pts": [tuple(q) for q in a_["pts"]], "lanes": a_["lanes"], "lane_w": 3.6 if a_.get("under") else 3.3,
                      "oneway": a_["oneway"], "reverse": a_.get("reverse", False), "width": 0.0, "speed": a_.get("speed", 30),
                      "district": a_.get("city", "austin"), "core": False, "skip": False, "parkway": False, "elevated": False,
                      "matched": False, "rb": False, "under": bool(a_.get("under")), "pc": "fix"})
    stats["seam_fix_added"] += 1
roads = [r for r in _roads_in if r["cls"] in DRIVE and not r["skip"] and not r["elevated"] and len(r["pts"]) >= 2]
for r in roads:
    r["pts"] = [tuple(p) for p in r["pts"]]
    r["s"] = cumlen(r["pts"])
    # where the piece came from in the mashup plan: chicago / austin, or "stitch" / "sketch" / "new" for the connectors
    # the plan added at the seam (integrate_v2.py, apply_sketch.py); carried to the output so seam junctions can be found
    if "pc" not in r:
        r["pc"] = PLAN["roads"][r["plan_i"]]["city"] if 0 <= r.get("plan_i", -1) < len(PLAN["roads"]) else r["city"]
    r.setdefault("under", False)
    r.setdefault("frontage", False)
roads = [r for r in roads if r["s"][-1] > 1.0]
stats["roads_in"] = len(roads)

grid = SegGrid(20.0)
for ri, r in enumerate(roads):
    for k, (a, b) in enumerate(zip(r["pts"], r["pts"][1:])):
        grid.add(a, b, (ri, k))

splits = collections.defaultdict(list)          # ri -> [(s, point)]
for ri, r in enumerate(roads):
    splits[ri].append((0.0, r["pts"][0]))
    splits[ri].append((r["s"][-1], r["pts"][-1]))

# crossings: every pair of segments from different roads that cross
for i, (a, b, (ri, ki)) in enumerate(grid.segs):
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    for j, (c, d, (rj, kj)) in grid.near(mid, math.dist(a, b) / 2 + 1.0):
        if j <= i or rj == ri:
            continue
        x = seg_x(a, b, c, d)
        if not x:
            continue
        p, t, u = x
        splits[ri].append((roads[ri]["s"][ki] + t * math.dist(a, b), p))
        splits[rj].append((roads[rj]["s"][kj] + u * math.dist(c, d), p))
        stats["crossings"] += 1

# T-junctions: an endpoint that stops within SNAP of another road joins it there (OSM ways often stop a metre short)
SNAP = 6.0
for ri, r in enumerate(roads):
    for end_s, p in ((0.0, r["pts"][0]), (r["s"][-1], r["pts"][-1])):
        best = None
        for j, (c, d, (rj, kj)) in grid.near(p, SNAP):
            if rj == ri:
                continue
            q, u, dd = closest_on_seg(p, c, d)
            if dd < SNAP and (best is None or dd < best[0]):
                best = (dd, rj, roads[rj]["s"][kj] + u * math.dist(c, d), q)
        if best and best[0] > 0.01:
            dd, rj, s_on, q = best
            splits[rj].append((s_on, q))
            splits[ri].append((end_s, q))       # the endpoint moves onto the other road
            stats["t_snaps"] += 1

# cluster split points into nodes (4 m)
allpts = []
for ri, lst in splits.items():
    for s, p in lst:
        allpts.append((ri, s, p))
parent = list(range(len(allpts)))


def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


cg = collections.defaultdict(list)
for i, (_, _, p) in enumerate(allpts):
    cg[(int(p[0] // 4), int(p[1] // 4))].append(i)
for i, (_, _, p) in enumerate(allpts):
    gx, gy = int(p[0] // 4), int(p[1] // 4)
    for u in range(gx - 1, gx + 2):
        for v in range(gy - 1, gy + 2):
            for j in cg.get((u, v), ()):
                if j > i and math.dist(p, allpts[j][2]) < 4.0:
                    parent[find(i)] = find(j)
groups = collections.defaultdict(list)
for i in range(len(allpts)):
    groups[find(i)].append(i)
node_of = {}
node_pos = {}
for nid, (g, idx) in enumerate(groups.items()):
    ps = [allpts[i][2] for i in idx]
    node_pos[nid] = (sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps))
    for i in idx:
        node_of[i] = nid

G = nx.MultiGraph()
for nid, p in node_pos.items():
    G.add_node(nid, p=p)
ROAD_KEYS = ("cls", "name", "city", "lanes", "lane_w", "oneway", "reverse", "speed", "district", "core", "parkway", "pc", "rb", "under",
             "frontage")
idx_by_road = collections.defaultdict(list)
for i, (ri, s, p) in enumerate(allpts):
    idx_by_road[ri].append(i)
for ri, idxs in idx_by_road.items():
    r = roads[ri]
    lst = sorted(((allpts[i][1], node_of[i]) for i in idxs))
    # collapse consecutive splits in the same node
    seq = []
    for s, nid in lst:
        if seq and seq[-1][1] == nid:
            continue
        seq.append((s, nid))
    for (s0, n0), (s1, n1) in zip(seq, seq[1:]):
        if n0 == n1 or s1 - s0 < 0.5:
            continue
        geom = sub_polyline(r["pts"], r["s"], s0, s1)
        if len(geom) < 2:
            continue
        geom[0], geom[-1] = node_pos[n0], node_pos[n1]
        # travel direction relative to the geometry (u -> v): +1 forward, -1 backward, 0 both ways
        travel = (-1 if r["reverse"] else 1) if r["oneway"] else 0
        G.add_edge(n0, n1, geom=geom, travel=travel, src=ri, **{k: r[k] for k in ROAD_KEYS})
stats["nodes_raw"] = G.number_of_nodes()
stats["edges_raw"] = G.number_of_edges()


def elen(d):
    return cumlen(d["geom"])[-1]


def geom_from(d, u):
    """Edge geometry oriented to start at node u."""
    g = d["geom"]
    p = G.nodes[u]["p"]
    return g if math.dist(g[0], p) <= math.dist(g[-1], p) else g[::-1]


def travel_from(d, u):
    """+1 if traffic flows away from u, -1 toward u, 0 two-way."""
    if not d["travel"]:
        return 0
    forward = math.dist(d["geom"][0], G.nodes[u]["p"]) <= math.dist(d["geom"][-1], G.nodes[u]["p"])
    return d["travel"] if forward else -d["travel"]


# drop self-loops and zero-length edges
for u, v, k, d in list(G.edges(keys=True, data=True)):
    if u == v and elen(d) < 15.0:
        G.remove_edge(u, v, k)


# ---------------------------------------------------------------- 1b. clean up
def compatible(a, b):
    return (a["cls"] == b["cls"] and a["lanes"] == b["lanes"] and a["oneway"] == b["oneway"] and a["rb"] == b["rb"]
            and (a["name"] == b["name"] or not a["name"] or not b["name"]))


def merge_pass_nodes():
    """A node where exactly two compatible pieces of the same street meet is not an intersection: join them."""
    merged = 0
    for n in list(G.nodes):
        if n not in G or G.degree(n) != 2:
            continue
        es = list(G.edges(n, keys=True, data=True))
        if len(es) != 2:
            continue
        (_, a, ka, da), (_, b, kb, db) = es
        if a == n or b == n or not compatible(da, db):
            continue
        ga, gb = geom_from(da, n), geom_from(db, n)      # both start at n
        ta, tb = travel_from(da, n), travel_from(db, n)
        if da["oneway"] and ta == tb:                     # head-to-head one-ways are not one street
            continue
        geom = ga[::-1] + gb[1:]                           # a ... n ... b
        travel = 0
        if da["oneway"]:
            travel = 1 if tb == 1 else -1                 # along a -> b
        attrs = {k: da[k] for k in ROAD_KEYS}
        attrs["pc"] = "+".join(sorted(set(da["pc"].split("+")) | set(db["pc"].split("+"))))
        G.remove_edge(n, a, ka)
        G.remove_edge(n, b, kb)
        G.remove_node(n)
        G.add_edge(a, b, geom=geom, travel=travel, src=da["src"], **attrs)
        merged += 1
    return merged


stats["merged_pass"] = merge_pass_nodes()

# streets under an expressway ramp's fill: the piece across it goes, and what is left dangling from it back to the next
# junction goes too (Trinity Street then ends at East 14th from the north and East 15th from the south)
if X_FP["fill_cut"]:
    _cut = 0
    for u, v, k, d in list(G.edges(keys=True, data=True)):
        g = d["geom"]
        sc = cumlen(g)
        if d["cls"] == "highway" and (at_foot(g[0]) or at_foot(g[-1])):
            continue                       # the main lanes going on up the ramp
        n_ = max(2, int(sc[-1] / 1.0))
        if sum(in_polys(at_s(g, sc, sc[-1] * i / n_)[0], X_FP["fill_cut"]) for i in range(n_ + 1)) * sc[-1] / n_ > 3.0:
            G.remove_edge(u, v, k)
            _cut += 1
            for end in (u, v):
                cur = end
                while cur in G and G.degree(cur) == 1 and not near_bounds(G.nodes[cur]["p"], 0.0):
                    (_, m_, k_, _d), = list(G.edges(cur, keys=True, data=True))
                    G.remove_edge(cur, m_, k_)
                    G.remove_node(cur)
                    cur = m_
                    if G.degree(cur) != 1:
                        break
                    # stop at a pass node that becomes a dead end only if it is a real junction-less run
    for n in [n for n in G.nodes if G.degree(n) == 0]:
        G.remove_node(n)
    stats["streets_cut_by_ramp_fill"] = _cut

# dangling stubs: a piece that sticks out less than 30 m past the last junction is OSM noise or a seam leftover
for _ in range(4):
    cut = 0
    for n in list(G.nodes):
        if n in G and G.degree(n) == 1 and not near_bounds(G.nodes[n]["p"]):
            (_, m, k, d), = list(G.edges(n, keys=True, data=True))
            if elen(d) < 30.0 and G.degree(m) >= 2:
                G.remove_edge(n, m, k)
                G.remove_node(n)
                cut += 1
    stats["stubs_removed"] += cut
    stats["merged_pass"] += merge_pass_nodes()
    if not cut:
        break
for n in [n for n in G.nodes if G.degree(n) == 0]:
    G.remove_node(n)

# dead ends that stop short of another street get joined to it (a T), if the gap is short, on land and roughly
# straight ahead; expressways only join expressways
egrid = SegGrid(25.0)


def rebuild_egrid():
    global egrid
    egrid = SegGrid(25.0)
    for u, v, k, d in G.edges(keys=True, data=True):
        for a, b in zip(d["geom"], d["geom"][1:]):
            egrid.add(a, b, (u, v, k))


rebuild_egrid()


def split_edge(u, v, k, p):
    """Split edge (u, v, k) at the point nearest p; returns the new node id."""
    d = G.edges[u, v, k]
    g = d["geom"]
    s_cum = cumlen(g)
    best = None
    for i, (a, b) in enumerate(zip(g, g[1:])):
        q, t, dd = closest_on_seg(p, a, b)
        if best is None or dd < best[0]:
            best = (dd, s_cum[i] + t * math.dist(a, b), q)
    _, s, q = best
    if s < 1.0 or s > s_cum[-1] - 1.0:
        return u if s < 1.0 else v
    nid = max(G.nodes) + 1
    G.add_node(nid, p=q)
    g1 = sub_polyline(g, s_cum, 0, s); g2 = sub_polyline(g, s_cum, s, s_cum[-1])
    g1[-1] = q; g2[0] = q
    attrs = {kk: d[kk] for kk in ROAD_KEYS}
    a0 = g[0]
    first = u if math.dist(a0, G.nodes[u]["p"]) <= math.dist(a0, G.nodes[v]["p"]) else v
    last = v if first == u else u
    G.remove_edge(u, v, k)
    G.add_edge(first, nid, geom=g1, travel=d["travel"], src=d["src"], **attrs)
    G.add_edge(nid, last, geom=g2, travel=d["travel"], src=d["src"], **attrs)
    return nid


joined = 0
for n in list(G.nodes):
    if n not in G or G.degree(n) != 1 or near_bounds(G.nodes[n]["p"]):
        continue
    (_, m, k, d), = list(G.edges(n, keys=True, data=True))
    g = geom_from(d, n)
    p = g[0]
    out = unit((p[0] - g[min(3, len(g) - 1)][0], p[1] - g[min(3, len(g) - 1)][1]))   # pointing past the end
    best = None
    for _, (a, b, (u2, v2, k2)) in egrid.near(p, 45.0):
        if (u2, v2, k2) == (n, m, k) or (v2, u2, k2) == (n, m, k) or n in (u2, v2):
            continue
        d2 = G.edges[u2, v2, k2]
        if (d2["cls"] == "highway") != (d["cls"] == "highway"):
            continue
        q, t, dd = closest_on_seg(p, a, b)
        # the same street carried on (a piece of bridge the plan lost: West Van Buren over the South Branch stopped 28 m
        # short of the bank, playtest-austin 21 Oct) may close a gap up to 45 m; anything else 25 m
        same = bool(d["name"]) and d2["name"] == d["name"]
        if dd > (45.0 if same else 25.0) or dd < 0.5:
            continue
        ahead = ((q[0] - p[0]) * out[0] + (q[1] - p[1]) * out[1]) / dd
        if ahead < math.cos(math.radians(40)):
            continue
        if not on_land(((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)) and not (d["name"] and d2["name"] == d["name"]):
            continue          # over water only to carry the same street on (a bridge the plan lost: Riverside Drive)
        if best is None or dd < best[0]:
            best = (dd, u2, v2, k2, q)
    if best:
        dd, u2, v2, k2, q = best
        t_node = split_edge(u2, v2, k2, q)
        geom = [G.nodes[n]["p"], G.nodes[t_node]["p"]]
        attrs = {kk: d[kk] for kk in ROAD_KEYS}
        G.add_edge(n, t_node, geom=geom, travel=travel_from(d, m) * -1 if d["oneway"] else 0, src=d["src"], **attrs)
        joined += 1
        rebuild_egrid()
stats["dead_ends_joined"] = joined
stats["merged_pass"] += merge_pass_nodes()

# what is left with one end loose is a real dead end (or leaves the map)
for n in G.nodes:
    G.nodes[n]["kind"] = ("edge" if near_bounds(G.nodes[n]["p"]) else "deadend") if G.degree(n) == 1 else (
        "pass" if G.degree(n) == 2 else "junction")
stats["nodes"] = G.number_of_nodes()
stats["edges"] = G.number_of_edges()

# expressway leftovers: ramp pieces whose elevated parts aren't built end in mid-air on the ground; an expressway
# never just stops, so dead-end expressway pieces (and what they leave dangling) are removed
for _ in range(6):
    cut = 0
    for n in list(G.nodes):
        if n in G and G.degree(n) == 1 and not near_bounds(G.nodes[n]["p"]):
            (_, m, k, d), = list(G.edges(n, keys=True, data=True))
            if d["cls"] == "highway" and elen(d) < 400.0:
                G.remove_edge(n, m, k)
                G.remove_node(n)
                cut += 1
            elif elen(d) < 30.0 and G.degree(m) >= 2:
                G.remove_edge(n, m, k)
                G.remove_node(n)
                cut += 1
    stats["ramp_leftovers_removed"] += cut
    stats["merged_pass"] += merge_pass_nodes()
    if not cut:
        break
for n in [n for n in G.nodes if G.degree(n) == 0]:
    G.remove_node(n)
for n in G.nodes:
    G.nodes[n]["kind"] = ("edge" if near_bounds(G.nodes[n]["p"]) else "deadend") if G.degree(n) == 1 else (
        "pass" if G.degree(n) == 2 else "junction")
stats["nodes"] = G.number_of_nodes()
stats["edges"] = G.number_of_edges()

# two junction nodes a few metres apart (a crossing and a T-snap of the same corner) are one intersection
def contract_short(limit=10.0):
    done = 0
    for u, v, k, d in list(G.edges(keys=True, data=True)):
        if u == v or u not in G or v not in G or not G.has_edge(u, v, k):
            continue
        if G.degree(u) < 3 or G.degree(v) < 3 or elen(d) >= limit:
            continue
        pu, pv = G.nodes[u]["p"], G.nodes[v]["p"]
        c = ((pu[0] + pv[0]) / 2, (pu[1] + pv[1]) / 2)
        G.remove_edge(u, v, k)
        moved = []
        for node, pn in ((u, pu), (v, pv)):
            for _, m, kk, dd in list(G.edges(node, keys=True, data=True)):
                g = list(dd["geom"])
                if math.dist(g[0], pn) < 1e-3:
                    g[0] = c
                if math.dist(g[-1], pn) < 1e-3:
                    g[-1] = c
                attrs = {kk2: dd[kk2] for kk2 in ROAD_KEYS}
                other = m if m not in (u, v) else u
                moved.append((other, g, dd["travel"], dd["src"], attrs))
                G.remove_edge(node, m, kk)
        G.remove_node(v)
        G.nodes[u]["p"] = c
        for other, g, travel, src, attrs in moved:
            G.add_edge(u, other, geom=g, travel=travel, src=src, **attrs)
        done += 1
    return done


stats["short_contracted"] = contract_short()
for n in G.nodes:
    G.nodes[n]["kind"] = ("edge" if near_bounds(G.nodes[n]["p"]) else "deadend") if G.degree(n) == 1 else (
        "pass" if G.degree(n) == 2 else "junction")
stats["kinds"] = dict(collections.Counter(G.nodes[n]["kind"] for n in G.nodes))


# building footprints, for the fit check
fp = []
for b in BLD:
    a = math.radians(b["yaw"])
    ca, sa = math.cos(a), math.sin(a)
    hw, hd = b["w"] / 2, b["d"] / 2
    # same footprint axes as build_street_data.in_footprint: u along (sa, ca), v along (ca, -sa)
    corners = [(b["x"] + sa * u + ca * v, b["y"] + ca * u - sa * v) for u, v in ((hw, hd), (-hw, hd), (-hw, -hd), (hw, -hd))]
    fp.append(corners)
fp_grid = SegGrid(30.0)
for bi, c in enumerate(fp):
    for k in range(4):
        fp_grid.add(c[k], c[(k + 1) % 4], bi)


def clearance(p, nrm, maxd=40.0):
    """Distance from p along +nrm to the nearest building wall (or maxd)."""
    best = maxd
    q = (p[0] + nrm[0] * maxd, p[1] + nrm[1] * maxd)
    for _, (a, b, bi) in fp_grid.near(((p[0] + q[0]) / 2, (p[1] + q[1]) / 2), maxd / 2 + 1):
        x = seg_x(p, q, a, b)
        if x:
            best = min(best, x[1] * maxd)
    return best



# ---------------------------------------------------------------- 1c. doubled streets
# Two pieces of street between the same two nodes that lie on top of each other (OSM's parallel carriageways squeezed
# together by the plan, or the same street drawn twice) are one street. The 20 Oct audit found 52 overlapping pairs
# (Lake Shore Drive drawn twice for 1.2 km, lane arrows pointing both ways in the same lane, traffic driving through
# itself). Same direction: keep the one with more lanes. Opposite one-ways: one two-way street as wide as the wider one.
def mean_gap(ga, gb, step=5.0):
    sa = cumlen(ga)
    n = max(2, int(sa[-1] / step))
    tot = 0.0
    for i in range(n + 1):
        p, _ = at_s(ga, sa, sa[-1] * i / n)
        tot += min(closest_on_seg(p, a, b)[2] for a, b in zip(gb, gb[1:]))
    return tot / (n + 1)


def merge_doubled():
    done = 0
    for u, v in {(min(a, b), max(a, b)) for a, b in G.edges() if a != b}:
        while True:
            ks = list(G[u][v].keys()) if G.has_edge(u, v) else []
            pair = None
            for i in range(len(ks)):
                for j in range(i + 1, len(ks)):
                    da, db = G.edges[u, v, ks[i]], G.edges[u, v, ks[j]]
                    # on top of each other: a quarter of their mean width apart at most (pairs further apart but still
                    # overlapping are pushed apart below, not merged: merging those made 8- and 12-lane streets)
                    if da.get("fix") or db.get("fix"):
                        continue
                    near = max(2.5, 0.25 * 3.3 * (max(1, da["lanes"]) + max(1, db["lanes"])) / 2)
                    ga, gb = geom_from(da, u), geom_from(db, u)
                    if max(mean_gap(ga, gb), mean_gap(gb, ga)) < near:
                        pair = (ks[i], ks[j], da, db)
                        break
                if pair:
                    break
            if not pair:
                break
            ka, kb, da, db = pair
            ta, tb = travel_from(da, u), travel_from(db, u)
            if da["oneway"] and db["oneway"] and ta == -tb:
                keep, drop = (ka, kb) if da["lanes"] >= db["lanes"] else (kb, ka)
                d = G.edges[u, v, keep]
                d["lanes"] = max(2, da["lanes"], db["lanes"])       # the footprint of the wider one, split both ways
                d["oneway"], d["travel"], d["reverse"] = False, 0, False
                d["name"] = d["name"] or (db["name"] if keep == ka else da["name"])
                d["fix"] = "two opposite one-ways drawn on top of each other: one two-way street"
                stats["doubled_merged_two_way"] += 1
            else:
                score = lambda dd, kk: (dd["lanes"], RANK_C[dd["cls"]], elen(dd))
                drop = kb if score(da, ka) >= score(db, kb) else ka
                stats["doubled_dropped"] += 1
            G.remove_edge(u, v, drop)
            done += 1
    return done


RANK_C = {"minor": 0, "mid": 1, "major": 2, "highway": 3}


# ---------------------------------------------------------------- 1c'. interchange ramps at grade
# Lake Shore Drive, the Eisenhower and the Dan Ryan cross the grid on bridges and in trenches in the real city; here
# everything is on the ground, so where an expressway meets a street the OpenStreetMap ramps (unnamed expressway
# links) land in the same intersection as the expressway itself: up to 8 nodes and 14 legs in one paved apron
# (Randolph at Lake Shore Drive, UE -35815, 114960). At grade the turns are made at the signal, so short ramps that
# end in such a cluster are dropped when the network stays connected without them.
def prune_at_grade_ramps():
    par = {}

    def f(x):
        while par.setdefault(x, x) != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for u, v, k, d in G.edges(keys=True, data=True):
        if u != v and G.degree(u) >= 3 and G.degree(v) >= 3 and elen(d) < 30.0:
            par[f(u)] = f(v)
    clusters = collections.defaultdict(set)
    for n in list(par):
        clusters[f(n)].add(n)
    cut = 0
    for nodes in clusters.values():
        if len(nodes) < 3:
            continue
        if not any(dd["cls"] == "highway" and dd["name"] for n in nodes for _, _, dd in G.edges(n, data=True)):
            continue
        cands = {(min(a, b), max(a, b), k) for n in nodes for a, b, k, dd in G.edges(n, keys=True, data=True)
                 if dd["cls"] == "highway" and not dd["name"] and elen(dd) < 160.0}
        for a, b, k in sorted(cands, key=lambda t: elen(G.edges[t]) if G.has_edge(*t) else 0):
            if not G.has_edge(a, b, k):
                continue
            d = G.edges[a, b, k]
            G.remove_edge(a, b, k)
            if a != b and not nx.has_path(G, a, b):
                G.add_edge(a, b, k, **d)
                continue
            cut += 1
    # what the ramps leave hanging (the rest of a ramp, a stub) goes the way the expressway leftovers went
    for _ in range(6):
        gone = 0
        for n in list(G.nodes):
            if n in G and G.degree(n) == 1 and not near_bounds(G.nodes[n]["p"]):
                (_, m, k, d), = list(G.edges(n, keys=True, data=True))
                if (d["cls"] == "highway" and elen(d) < 400.0) or (elen(d) < 30.0 and G.degree(m) >= 2):
                    G.remove_edge(n, m, k)
                    G.remove_node(n)
                    gone += 1
        if not gone:
            break
    for n in [n for n in G.nodes if G.degree(n) == 0]:
        G.remove_node(n)
    return cut


stats["at_grade_ramps_dropped"] = prune_at_grade_ramps()


# ---------------------------------------------------------------- 1c''. a street whose end runs along another street
# Some plan polylines carry on along a neighbouring street for a block or more (West Polk Street turning north on top
# of Dearborn for 220 m, West 5th and the Crosstown Parkway sharing a carriageway): two ribbons on top of each other,
# their lane arrows pointing opposite ways in the same lane. Where the END of a street lies on another street for
# 40 m or more, the street stops where it meets the other one (a T there) and the doubled tail goes.
def est_w(d):
    return 3.3 * (max(1, d["lanes"]) if d["oneway"] else max(2, d["lanes"]))


def find_tails():
    rebuild_egrid()
    res = []
    for u, v, k, d in G.edges(keys=True, data=True):
        if u == v:
            continue
        g = d["geom"]
        sc = cumlen(g)
        L = sc[-1]
        if L < 40.0:
            continue
        n = int(L / 2.0) + 1
        onb = []
        for i in range(n + 1):
            s = L * i / n
            p, _ = at_s(g, sc, s)
            best = None
            for _, (a, b, (u2, v2, k2)) in egrid.near(p, 12.0):
                if (u2, v2, k2) in ((u, v, k), (v, u, k)) or not G.has_edge(u2, v2, k2):
                    continue
                d2 = G.edges[u2, v2, k2]
                q, t, dd = closest_on_seg(p, a, b)
                if dd < 0.4 * (est_w(d) + est_w(d2)) and (best is None or dd < best[0]):
                    best = (dd, (u2, v2, k2))
            onb.append((s, best[1] if best else None))
        # a run of samples on the same other street that reaches one of this street's ends
        for end in (0, 1):
            seq = onb if end == 0 else onb[::-1]
            other = seq[0][1]
            if other is None:
                continue
            j = 0
            while j < len(seq) and seq[j][1] == other:
                j += 1
            run = abs(seq[j - 1][0] - seq[0][0])
            if run < 40.0:
                continue
            if RANK_C[G.edges[other]["cls"]] < RANK_C[d["cls"]] and run < L - 5.0:
                continue                   # keep the bigger street whole; the smaller one gets cut instead
            res.append(((u, v, k), end, seq[j - 1][0] if j < len(seq) else None, other))
            break
    return res


def cut_tail(found):
    (u, v, k), end, s_cut, other = found
    if not G.has_edge(u, v, k) or not G.has_edge(*other):
        return False
    d = G.edges[u, v, k]
    g = d["geom"]
    sc = cumlen(g)
    # the end of the geometry that lies on the other street, and the node at that end
    geo_end_node = (u if math.dist(g[0], G.nodes[u]["p"]) <= math.dist(g[0], G.nodes[v]["p"]) else v) if end == 0 else \
                   (v if math.dist(g[-1], G.nodes[v]["p"]) <= math.dist(g[-1], G.nodes[u]["p"]) else u)
    keep_node = v if geo_end_node == u else u
    attrs = {kk: d[kk] for kk in ROAD_KEYS}
    travel, src = d["travel"], d["src"]
    G.remove_edge(u, v, k)
    if s_cut is None or (end == 0 and sc[-1] - s_cut < 10.0) or (end == 1 and s_cut < 10.0):
        return True                            # all of it lies on the other street
    keep = sub_polyline(g, sc, s_cut, sc[-1]) if end == 0 else sub_polyline(g, sc, 0.0, s_cut)
    q = keep[0] if end == 0 else keep[-1]
    t_node = split_edge(*other, q)
    if t_node == keep_node:
        return True
    if end == 0:
        keep[0] = G.nodes[t_node]["p"]
    else:
        keep[-1] = G.nodes[t_node]["p"]
    G.add_edge(t_node, keep_node, geom=keep, travel=travel, src=src, **attrs)
    return True


def resolve_tails():
    cut = 0
    for _ in range(6):
        fs = find_tails()
        done = sum(1 for f in fs if cut_tail(f))
        cut += done
        if not done:
            break
    for n in [n for n in G.nodes if G.degree(n) == 0]:
        G.remove_node(n)
    return cut


stats["doubled_tails_cut"] = resolve_tails()


# ---------------------------------------------------------------- 1c'''. opposite one-ways squeezed onto each other
# A one-way pair whose two carriageways the plan draws closer than their widths (West 5th Street and the Crosstown
# Parkway, Randolph Street and the Crosstown Parkway): each carriageway moves half the overlap away from the other,
# tapering to nothing over 15 m at its nodes, so they run side by side like a divided road (right-hand traffic: each
# keeps to its own side) instead of on top of each other with arrows pointing both ways in one lane.
def separate_opposite_one_ways():
    rebuild_egrid()
    moves = {}
    for u, v, k, d in G.edges(keys=True, data=True):
        if not d["oneway"] or u == v:
            continue
        g = d["geom"]
        sc = cumlen(g)
        L = sc[-1]
        if L < 30.0:
            continue
        tr = d["travel"] if d["travel"] else 1
        n = max(2, int(L / 4.0))
        pts, shifts, hits = [], [], 0
        for i in range(n + 1):
            s = L * i / n
            p, t = at_s(g, sc, s)
            tdir = (t[0] * tr, t[1] * tr)
            best = None
            for _, (a, b, (u2, v2, k2)) in egrid.near(p, 14.0):
                if (u2, v2, k2) in ((u, v, k), (v, u, k)) or not G.has_edge(u2, v2, k2):
                    continue
                d2 = G.edges[u2, v2, k2]
                if not d2["oneway"]:
                    continue
                q, tt, dd = closest_on_seg(p, a, b)
                need = 0.5 * (est_w(d) + est_w(d2)) + 0.3
                # egrid segments run in geometry order, so the other carriageway travels along a -> b times its travel
                sgn = d2["travel"] if d2["travel"] else 1
                t2 = unit((b[0] - a[0], b[1] - a[1]))
                if tdir[0] * t2[0] * sgn + tdir[1] * t2[1] * sgn > -0.8:
                    continue                       # not running the opposite way alongside
                if dd < need and (best is None or dd < best[0]):
                    # right-hand traffic: the opposite carriageway belongs on my left; I move to my right by half of
                    # what is missing (it does the same), which also swaps a pair drawn on the wrong sides
                    left_off = (q[0] - p[0]) * -tdir[1] + (q[1] - p[1]) * tdir[0]
                    best = (dd, need, left_off)
            if best:
                hits += 1
                dd, need, left_off = best
                taper = min(1.0, s / 15.0, (L - s) / 15.0)
                mag = max(0.0, (need - left_off) / 2.0) * taper
                # never into a building: the carriageway's outer edge keeps a metre of sidewalk to the nearest wall
                room = clearance(p, (tdir[1], -tdir[0])) - est_w(d) / 2 - 2.4 - 1.0      # lanes + a parking lane + 1 m
                mag = min(mag, max(0.0, room))
                shifts.append((tdir[1] * mag, -tdir[0] * mag))
            else:
                shifts.append((0.0, 0.0))
            pts.append(p)
        if hits * (L / n) >= 30.0:
            moves[(u, v, k)] = [(p[0] + sx, p[1] + sy) for p, (sx, sy) in zip(pts, shifts)]
    for (u, v, k), newg in moves.items():
        d = G.edges[u, v, k]
        g = d["geom"]
        newg[0], newg[-1] = g[0], g[-1]            # the nodes stay where they are
        d["geom"] = newg
        stats["separated_streets"] = sorted(set(stats.get("separated_streets", [])) | {d["name"] or "(unnamed " + d["cls"] + ")"})
    return len(moves)


stats["opposite_one_ways_separated"] = separate_opposite_one_ways()
stats["merged_pass"] += merge_pass_nodes()
for n in G.nodes:
    G.nodes[n]["kind"] = ("edge" if near_bounds(G.nodes[n]["p"]) else "deadend") if G.degree(n) == 1 else (
        "pass" if G.degree(n) == 2 else "junction")
if merge_doubled():
    stats["merged_pass"] += merge_pass_nodes()
    for n in G.nodes:
        G.nodes[n]["kind"] = ("edge" if near_bounds(G.nodes[n]["p"]) else "deadend") if G.degree(n) == 1 else (
            "pass" if G.degree(n) == 2 else "junction")


# ---------------------------------------------------------------- 1c-seam. seam junctions
# Where the mashup stitched Chicago to Austin (the seam, plan_v3 "seam", and the stitch / sketch connector roads) the
# 20 Oct night audit (Scripts/roads/seam_audit.py) found intersections no city would build: connectors that arrive at a
# junction at 10-35 deg beside a street going the same way (a diagonal shortcut next to the grid: two junctions where one
# would do, a sliver of island between them), and clusters of junction nodes 10-30 m apart that are one intersection
# drawn several times. Rules, in the seam zone only (300 m of the seam, or 60 m of a connector road):
#   redundant connector  a connector road (stitch / sketch) that meets another street at under 40 deg at either end,
#                        where the network has another way between its two ends no longer than twice its length
#                        (+150 m), is removed: the grid already makes that connection (FHWA / NACTO: avoid skewed and
#                        multi-leg intersections; a real city would not build the diagonal)
#   one intersection     junction nodes joined by a street shorter than 30 m, one of them on a connector, become one
#                        node; the streets' last 25 m bend smoothly to meet there head-on (instead of two junctions a car
#                        length apart with a sliver of curb between)
SEAM_PTS = [tuple(p) for p in PLAN.get("seam", [])]
_seam_grid = SegGrid(50.0)
for _a, _b in zip(SEAM_PTS, SEAM_PTS[1:]):
    _seam_grid.add(_a, _b, None)


def d_seam(p, cap=400.0):
    best = cap
    for _, (a, b, _) in _seam_grid.near(p, cap):
        best = min(best, closest_on_seg(p, a, b)[2])
    return best


def is_conn(d):
    return any(t in d.get("pc", "") for t in ("stitch", "sketch", "new"))


def in_seam_zone(p):
    if d_seam(p, 300.0) < 300.0:
        return True
    for _, (a, b, (u2, v2, k2)) in egrid.near(p, 60.0):
        if G.has_edge(u2, v2, k2) and is_conn(G.edges[u2, v2, k2]) and closest_on_seg(p, a, b)[2] < 60.0:
            return True
    return False


def end_dir(d, n, s=15.0):
    g = geom_from(d, n)
    sc = cumlen(g)
    q, _ = at_s(g, sc, min(s, sc[-1] * 0.5))
    return unit((q[0] - g[0][0], q[1] - g[0][1]))


def min_angle_at(n, key):
    """Smallest angle (deg) between edge `key`'s end at node n and the other streets there."""
    u, v, k = key
    mine = end_dir(G.edges[key], n)
    best = 180.0
    for _, m, kk, dd in G.edges(n, keys=True, data=True):
        if {(n, m, kk), (m, n, kk)} & {(u, v, k), (v, u, k)}:
            continue
        o = end_dir(dd, n)
        best = min(best, math.degrees(math.acos(max(-1.0, min(1.0, mine[0] * o[0] + mine[1] * o[1])))))
    return best


def drop_redundant_connectors():
    rebuild_egrid()
    cands = []
    for u, v, k, d in G.edges(keys=True, data=True):
        if u == v or not is_conn(d) or d.get("rb") or G.degree(u) < 2 or G.degree(v) < 2:
            continue
        mid = at_s(d["geom"], cumlen(d["geom"]), elen(d) / 2)[0]
        if not in_seam_zone(mid):
            continue
        acute = min(min_angle_at(u, (u, v, k)), min_angle_at(v, (u, v, k)))
        # two connectors joining the same two junctions (a lens: South Clinton and West Harrison both curving from
        # Harrison up to 15th / Guadalupe) are one connection drawn twice: the longer one is a candidate too
        twin = any(kk != k and is_conn(dd) and elen(dd) <= elen(d) for kk, dd in G[u][v].items())
        if acute < 40.0 or twin:
            cands.append((acute if not twin else -1.0, (u, v, k)))
    cut = 0
    wfun = lambda a, b, dd: min(elen(e) for e in dd.values())
    for acute, (u, v, k) in sorted(cands):
        if not G.has_edge(u, v, k):
            continue
        d = G.edges[u, v, k]
        L = elen(d)
        G.remove_edge(u, v, k)
        try:
            alt = nx.shortest_path_length(G, u, v, weight=wfun)
        except nx.NetworkXNoPath:
            alt = None
        if alt is None or alt > max(2.0 * L, L + 150.0):
            G.add_edge(u, v, k, **d)
            continue
        cut += 1
        stats.setdefault("seam_connectors_dropped", []).append(
            f"{d['name'] or d['cls']} {L:.0f} m at plan ({G.nodes[u]['p'][0]:.0f}, {G.nodes[u]['p'][1]:.0f}): meets at {acute:.0f} deg, "
            f"other way {alt:.0f} m")
    return cut


def reend(g, old, new, blend=25.0):
    """Move a polyline's end at `old` to `new`, carrying the last `blend` metres along smoothly."""
    g = list(g)
    flip = math.dist(g[-1], old) < math.dist(g[0], old)
    if flip:
        g = g[::-1]
    sc = cumlen(g)
    L = sc[-1]
    dx, dy = new[0] - old[0], new[1] - old[1]
    b = min(blend, L * 0.6)
    out = []
    for p, s in zip(g, sc):
        w = max(0.0, 1.0 - s / b) if b > 0 else (1.0 if s == 0 else 0.0)
        w = w * w * (3 - 2 * w)
        out.append((p[0] + dx * w, p[1] + dy * w))
    out[0] = new
    return out[::-1] if flip else out


def contract_seam(limit=30.0):
    done = 0
    rebuild_egrid()
    for _ in range(60):
        best = None
        for u, v, k, d in G.edges(keys=True, data=True):
            if u == v or G.degree(u) < 3 or G.degree(v) < 3 or elen(d) >= limit:
                continue
            if any(dd.get("rb") for n in (u, v) for _, _, dd in G.edges(n, data=True)):
                continue
            if not (is_conn(d) or any(is_conn(dd) for n in (u, v) for _, _, dd in G.edges(n, data=True))):
                continue
            pu, pv = G.nodes[u]["p"], G.nodes[v]["p"]
            if not is_conn(d):
                # a divided road's median link (each end has a one-way carriageway of a city street crossing it) is a
                # real two-node intersection: keep it
                t_ = unit((pv[0] - pu[0], pv[1] - pu[1]))
                med = all(any(dd["oneway"] and not is_conn(dd) and abs(end_dir(dd, n)[0] * t_[0] + end_dir(dd, n)[1] * t_[1]) < 0.5
                              for _, m_, dd in G.edges(n, data=True) if m_ not in (u, v)) for n in (u, v))
                if med:
                    continue
            if not in_seam_zone(((pu[0] + pv[0]) / 2, (pu[1] + pv[1]) / 2)):
                continue
            if best is None or elen(d) < best[0]:
                best = (elen(d), u, v, k)
        if not best:
            break
        _, u, v, k = best
        pu, pv = G.nodes[u]["p"], G.nodes[v]["p"]
        # the new node: weighted towards the busier end (more and bigger streets)
        wu = sum(RANK_C[dd["cls"]] + 1 for _, _, dd in G.edges(u, data=True))
        wv = sum(RANK_C[dd["cls"]] + 1 for _, _, dd in G.edges(v, data=True))
        c = ((pu[0] * wu + pv[0] * wv) / (wu + wv), (pu[1] * wu + pv[1] * wv) / (wu + wv))
        G.remove_edge(u, v, k)
        moved = []
        seen = set()
        for node, pn in ((u, pu), (v, pv)):
            for _, m, kk, dd in list(G.edges(node, keys=True, data=True)):
                if (min(node, m), max(node, m), kk) in seen:
                    continue
                seen.add((min(node, m), max(node, m), kk))
                g = list(dd["geom"])
                if m in (u, v):
                    # another link between the two nodes (or a loop): both its ends move to c
                    other_p = pv if node == u else pu
                    g2 = reend(reend(g, pn, c), other_p if m != node else pn, c)
                    other = u
                else:
                    g2 = reend(g, pn, c)
                    other = m
                attrs = {kk2: dd[kk2] for kk2 in ROAD_KEYS}
                moved.append((other, g2, dd["travel"], dd["src"], attrs))
        for a_, b_, kk in list(G.edges([u, v], keys=True)):
            if G.has_edge(a_, b_, kk):
                G.remove_edge(a_, b_, kk)
        G.remove_node(v)
        G.nodes[u]["p"] = c
        for other, g2, travel, src, attrs in moved:
            if other == u and cumlen(g2)[-1] < 15.0:
                continue
            G.add_edge(u, other, geom=g2, travel=travel, src=src, **attrs)
        done += 1
        stats.setdefault("seam_nodes_merged", []).append(f"plan ({c[0]:.0f}, {c[1]:.0f}): {best[0]:.0f} m apart")
        rebuild_egrid()
    return done


def tidy_after_cuts():
    for _ in range(6):
        gone = 0
        for n in list(G.nodes):
            if n in G and G.degree(n) == 1 and not near_bounds(G.nodes[n]["p"]):
                (_, m, k, d), = list(G.edges(n, keys=True, data=True))
                if elen(d) < 30.0 and G.degree(m) >= 2:
                    G.remove_edge(n, m, k)
                    G.remove_node(n)
                    gone += 1
        if not gone:
            break
    for n in [n for n in G.nodes if G.degree(n) == 0]:
        G.remove_node(n)
    stats["merged_pass"] += merge_pass_nodes()


stats["seam_connectors_dropped_n"] = drop_redundant_connectors()
tidy_after_cuts()
stats["seam_nodes_merged_n"] = contract_seam()
tidy_after_cuts()
for n in G.nodes:
    G.nodes[n]["kind"] = ("edge" if near_bounds(G.nodes[n]["p"]) else "deadend") if G.degree(n) == 1 else (
        "pass" if G.degree(n) == 2 else "junction")


# Untangling (Austin side of the seam zone, and Austin junctions beside its pedestrian ways and bridgeheads): OpenStreetMap
# draws some Austin junctions as tangles of one-lane slip links, a small turnaround loop and a boulevard's two
# carriageways a few metres apart (Lamar Boulevard at Cesar Chavez, B R Reynolds Drive and Sandra Muraida Way, where
# the Lady Bird Lake trail and the pedestrian bridge come in). Simplified the way a city would rebuild them:
#   one street, not two      opposite one-ways of the same street running within 14 m of each other between two
#                            junctions become one two-way street (lanes added), their end nodes merged
#   no slip links            one-lane one-way links (two lanes if unnamed) under 90 m between junctions go, as long as
#                            their two ends stay connected some other way (the one-way rules below then keep every
#                            street usable)
#   no turnaround loops      a closed loop shorter than 160 m made only of unnamed drive pieces or connector curves
#                            becomes one intersection at its centre (the box of four named carriageways where two
#                            divided roads cross stays)
AUSTIN_PED = [[tuple(q) for q in r["pts"]] for r in PLAN["roads"] if r["cls"] == "ped" and r["city"] == "austin"]
_ped_grid = SegGrid(50.0)
for _pts in AUSTIN_PED:
    for _a, _b in zip(_pts, _pts[1:]):
        _ped_grid.add(_a, _b, None)


# ... and the bridgeheads (the plan's bridges: Congress Avenue, Lamar, First Street... over Lady Bird Lake)
for _br in PLAN.get("bridges", []):
    for _a, _b in zip(_br["pts"], _br["pts"][1:]):
        _ped_grid.add(tuple(_a), tuple(_b), None)


def near_ped(p, r=150.0):
    return any(closest_on_seg(p, a, b)[2] < r for _, (a, b, _) in _ped_grid.near(p, r))


# the Texas State Capitol's grounds were fitted to the streets round them (austin-capitol, 20 Oct): leave those alone
_CAP = next((l["pos"] for l in PLAN.get("landmarks", []) if l["name"] == "Texas State Capitol"), None)


def austin_zone(n):
    p = G.nodes[n]["p"]
    if not any(dd["city"] == "austin" for _, _, dd in G.edges(n, data=True)):
        return False
    if _CAP and math.dist(p, _CAP) < 420.0:
        return False
    return d_seam(p, 350.0) < 350.0 or near_ped(p)


def contract_pair(u, v, why):
    """Merge node v into u (both kept junctions), every street end bending smoothly to the new spot."""
    pu, pv = G.nodes[u]["p"], G.nodes[v]["p"]
    c = ((pu[0] + pv[0]) / 2, (pu[1] + pv[1]) / 2)
    moved, seen = [], set()
    for node, pn in ((u, pu), (v, pv)):
        for _, m, kk, dd in list(G.edges(node, keys=True, data=True)):
            key_ = (min(node, m), max(node, m), kk)
            if key_ in seen:
                continue
            seen.add(key_)
            g = list(dd["geom"])
            if m in (u, v):
                if m == node or cumlen(g)[-1] < 40.0:
                    continue                      # the short link between them (or a loop) goes
                g2 = reend(reend(g, pn, c), pv if node == u else pu, c)
                other = u
            else:
                g2 = reend(g, pn, c)
                other = m
            moved.append((other, g2, dd["travel"], dd["src"], {k2: dd[k2] for k2 in ROAD_KEYS}))
    for a_, b_, kk in list(G.edges([u, v], keys=True)):
        if G.has_edge(a_, b_, kk):
            G.remove_edge(a_, b_, kk)
    G.remove_node(v)
    G.nodes[u]["p"] = c
    for other, g2, travel, src, attrs in moved:
        G.add_edge(u, other, geom=g2, travel=travel, src=src, **attrs)
    stats.setdefault("untangle", []).append(f"plan ({c[0]:.0f}, {c[1]:.0f}): {why}")


def untangle():
    done = 0
    # one street, not two
    for _ in range(20):
        found = None
        for u, v, k, d in G.edges(keys=True, data=True):
            if not d["oneway"] or d["rb"] or d["city"] != "austin" or u == v or not d["name"]:
                continue
            if not (austin_zone(u) or austin_zone(v)):
                continue
            g = d["geom"]
            for u2, v2, k2, d2 in G.edges(keys=True, data=True):
                if (u2, v2, k2) == (u, v, k) or not d2["oneway"] or d2["name"] != d["name"] or d2["rb"] or u2 == v2:
                    continue
                # ends pair up: u near one end of d2, v near the other
                ends2 = (G.nodes[u2]["p"], G.nodes[v2]["p"])
                pu, pv = G.nodes[u]["p"], G.nodes[v]["p"]
                if math.dist(pu, ends2[0]) + math.dist(pv, ends2[1]) <= math.dist(pu, ends2[1]) + math.dist(pv, ends2[0]):
                    a2, b2 = u2, v2
                else:
                    a2, b2 = v2, u2
                if math.dist(pu, G.nodes[a2]["p"]) > 30.0 or math.dist(pv, G.nodes[b2]["p"]) > 30.0:
                    continue
                if travel_from(d, u) != -travel_from(d2, a2):
                    continue                          # not opposite directions
                ga, gb = geom_from(d, u), geom_from(d2, a2)
                if max(mean_gap(ga, gb), mean_gap(gb, ga)) > 14.0:
                    continue
                found = (u, v, k, a2, b2, (u2, v2, k2))
                break
            if found:
                break
        if not found:
            break
        u, v, k, a2, b2, key2 = found
        d, d2 = G.edges[u, v, k], G.edges[key2]
        ga, gb = geom_from(d, u), geom_from(d2, a2)
        # lanes: both directions' lanes, but a pair drawn on top of each other (< 8 m apart) is one ordinary street
        lanes = max(1, d["lanes"]) + max(1, d2["lanes"])
        if max(mean_gap(ga, gb), mean_gap(gb, ga)) < 8.0:
            lanes = min(lanes, 4)
        sa, sb = cumlen(ga), cumlen(gb)
        n_ = max(2, int(max(sa[-1], sb[-1]) / 4.0))
        mid = [((at_s(ga, sa, sa[-1] * i / n_)[0][0] + at_s(gb, sb, sb[-1] * i / n_)[0][0]) / 2,
                (at_s(ga, sa, sa[-1] * i / n_)[0][1] + at_s(gb, sb, sb[-1] * i / n_)[0][1]) / 2) for i in range(n_ + 1)]
        attrs = {k2: d[k2] for k2 in ROAD_KEYS}
        attrs.update({"oneway": False, "reverse": False, "lanes": lanes})
        G.remove_edge(u, v, k)
        G.remove_edge(*key2)
        if a2 != u and a2 in G and u in G:
            contract_pair(u, a2, f"{d['name']}: the two carriageways' ends are one intersection")
        if b2 != v and b2 in G and v in G:
            contract_pair(v, b2, f"{d['name']}: the two carriageways' ends are one intersection")
        mid[0], mid[-1] = G.nodes[u]["p"], G.nodes[v]["p"]
        G.add_edge(u, v, geom=mid, travel=0, src=d["src"], **attrs)
        stats.setdefault("untangle", []).append(f"{d['name']}: opposite one-ways {mean_gap(ga, gb):.0f} m apart made one two-way street ({lanes} lanes)")
        done += 1
    # no slip links
    wfun = lambda a, b, dd: min(elen(e) for e in dd.values())
    cands = []
    for u, v, k, d in G.edges(keys=True, data=True):
        if u == v or not d["oneway"] or d["lanes"] > (2 if not d["name"] else 1) or d["rb"] or d["cls"] == "highway" or elen(d) >= 90.0:
            continue                      # (an unnamed one-way piece is a slip lane even with two lanes)
        if G.degree(u) < 3 or G.degree(v) < 3 or not (austin_zone(u) or austin_zone(v)):
            continue
        cands.append((elen(d), (u, v, k)))
    # a slip link whose end is a pass node onto a piece of street drawn twice (West Cesar Chavez at Congress Avenue: the
    # slip and a second copy of Cesar Chavez form one chain from the junction) goes with that doubled piece
    for u, v, k, d in list(G.edges(keys=True, data=True)):
        if u == v or not d["oneway"] or d["lanes"] > 1 or d["rb"] or d["cls"] == "highway" or elen(d) >= 90.0:
            continue
        if not (austin_zone(u) or austin_zone(v)):
            continue
        for a_, b_ in ((u, v), (v, u)):
            if G.degree(a_) != 2 or G.degree(b_) < 3:
                continue
            (nk,) = [(m, kk) for _, m, kk in G.edges(a_, keys=True) if not (m == b_ and kk == k)] or [(None, None)]
            if nk[0] is None:
                continue
            m, kk = nk
            dn = G.edges[a_, m, kk]
            gn = geom_from(dn, m)
            twin = [dd for _, m2, k2, dd in G.edges(m, keys=True, data=True) if not (m2 == a_ and k2 == kk) and
                    dd["name"] == dn["name"] and mean_gap(gn, geom_from(dd, m)[:len(gn) * 4]) < 4.0]
            if twin and G.degree(m) >= 3:
                cands.append((0.0, (u, v, k)))
                G.edges[u, v, k]["_chain"] = (a_, m, kk)
    for L, (u, v, k) in sorted(cands):
        if not G.has_edge(u, v, k):
            continue
        d = G.edges[u, v, k]
        chain = d.pop("_chain", None)
        if chain and G.has_edge(*chain):
            dn = G.edges[chain]
            G.remove_edge(u, v, k)
            G.remove_edge(*chain)
            if chain[0] in G and G.degree(chain[0]) == 0:
                G.remove_node(chain[0])
            stats.setdefault("untangle", []).append(f"{d['name'] or d['cls']}: slip link {L:.0f} m and the doubled piece of "
                                                    f"{dn['name']} it hangs on removed")
            done += 1
            continue
        if G.degree(u) < 3 or G.degree(v) < 3:
            continue
        G.remove_edge(u, v, k)
        try:
            alt = nx.shortest_path_length(G, u, v, weight=wfun)
        except nx.NetworkXNoPath:
            alt = None
        if alt is None or alt > 400.0:
            G.add_edge(u, v, k, **d)
            continue
        stats.setdefault("untangle", []).append(f"{d['name'] or d['cls']}: one-lane slip link {L:.0f} m at plan "
                                                f"({G.nodes[u]['p'][0]:.0f}, {G.nodes[u]['p'][1]:.0f}) removed (other way {alt:.0f} m)")
        done += 1
    # no turnaround loops
    for _ in range(10):
        H = nx.Graph()
        for u, v, k, d in G.edges(keys=True, data=True):
            if u != v and not d["rb"] and elen(d) < 90.0:
                w = elen(d)
                if not H.has_edge(u, v) or H[u][v]["w"] > w:
                    H.add_edge(u, v, w=w)
        loop = None
        for cyc in nx.cycle_basis(H):
            if len(cyc) < 3:
                continue
            per = sum(H[cyc[i]][cyc[(i + 1) % len(cyc)]]["w"] for i in range(len(cyc)))
            # a turnaround is unnamed drive pieces (or a connector's doubled curve): the box of four named one-way
            # carriageways where two divided roads cross is a real intersection and stays
            ring_e = [dd for i in range(len(cyc)) for dd in G[cyc[i]][cyc[(i + 1) % len(cyc)]].values()
                      if elen(dd) < 90.0]
            if not ring_e or not all((not dd["name"]) or is_conn(dd) for dd in ring_e):
                continue
            if per < 160.0 and any(austin_zone(n) for n in cyc):
                loop = (per, cyc)
                break
        if not loop:
            break
        per, cyc = loop
        c = (sum(G.nodes[n]["p"][0] for n in cyc) / len(cyc), sum(G.nodes[n]["p"][1] for n in cyc) / len(cyc))
        keep = cyc[0]
        for n in cyc:
            for _, m, kk in list(G.edges(n, keys=True)):
                if m in cyc and G.has_edge(n, m, kk):
                    G.remove_edge(n, m, kk)
        G.nodes[keep]["p"] = G.nodes[keep]["p"]
        for n in cyc[1:]:
            if n in G and keep in G:
                for _, m, kk, dd in list(G.edges(n, keys=True, data=True)):
                    g2 = reend(dd["geom"], G.nodes[n]["p"], G.nodes[keep]["p"])
                    G.add_edge(keep, m, geom=g2, travel=dd["travel"], src=dd["src"], **{k2: dd[k2] for k2 in ROAD_KEYS})
                    G.remove_edge(n, m, kk)
                G.remove_node(n)
        old = G.nodes[keep]["p"]
        for _, m, kk, dd in list(G.edges(keep, keys=True, data=True)):
            dd["geom"] = reend(dd["geom"], old, c)
        G.nodes[keep]["p"] = c
        stats.setdefault("untangle", []).append(f"plan ({c[0]:.0f}, {c[1]:.0f}): a {per:.0f} m turnaround loop made one intersection")
        done += 1
    return done


stats["untangle_n"] = untangle()
tidy_after_cuts()
stats["short_contracted"] += contract_short()
for n in G.nodes:
    G.nodes[n]["kind"] = ("edge" if near_bounds(G.nodes[n]["p"]) else "deadend") if G.degree(n) == 1 else (
        "pass" if G.degree(n) == 2 else "junction")


# ---------------------------------------------------------------- 1d. one-way streets that go nowhere
# A one-way street must be enterable and leavable: the mashup's seams and the dropped ramps left one-ways that run
# into a dead end or into other one-ways pointing back at them (traffic.json had only 311 of 1228 nodes in one
# strongly connected piece; cars reaching a trap were teleported, self-driving could not route out). Where a node
# can't be left (or entered) the cheapest one-way there (lowest class, then shortest) becomes two-way, and then any
# piece of the network that can't reach the rest (or be reached) gets one two-way link to it. Map-edge nodes count as
# connected to each other (the city continues off the map).
def travel_dir_edges(with_out=True):
    DG = nx.MultiDiGraph()
    DG.add_nodes_from(G.nodes)
    for u, v, k, d in G.edges(keys=True, data=True):
        t = travel_from(d, u)
        if t >= 0:
            DG.add_edge(u, v, key=(u, v, k))
        if t <= 0:
            DG.add_edge(v, u, key=(u, v, k))
    edge_nodes = [n for n in G.nodes if G.nodes[n]["kind"] == "edge"] if with_out else []
    for n in edge_nodes:
        DG.add_edge(n, "OUT", key=None)
        DG.add_edge("OUT", n, key=None)
    return DG


def make_two_way(key, why):
    u, v, k = key
    d = G.edges[u, v, k]
    if not d["oneway"]:
        return False
    d["oneway"], d["travel"], d["reverse"] = False, 0, False
    d["fix"] = why
    stats["oneway_made_two_way"] += 1
    return True


def cost_key(key):
    d = G.edges[key]
    return (d["cls"] == "highway", RANK_C[d["cls"]], elen(d))


for _ in range(12):
    DG = travel_dir_edges()
    changed = 0
    for n in list(G.nodes):
        if G.nodes[n]["kind"] == "edge":
            continue
        if DG.out_degree(n) == 0:
            ins = [kk for _, _, kk in DG.in_edges(n, keys=True) if kk]
            if ins and make_two_way(min(ins, key=cost_key), "one-way into a node no one can leave: two-way"):
                changed += 1
        elif DG.in_degree(n) == 0:
            outs = [kk for _, _, kk in DG.out_edges(n, keys=True) if kk]
            if outs and make_two_way(min(outs, key=cost_key), "one-way out of a node no one can reach: two-way"):
                changed += 1
    if not changed:
        break
for _ in range(250):
    DG = travel_dir_edges(False)
    # a lone map-edge node (a one-way leaving or entering the map) is fine on its own: the city goes on off the map
    comps = [c for c in sorted(nx.strongly_connected_components(DG), key=len, reverse=True)
             if not (len(c) == 1 and G.nodes[next(iter(c))]["kind"] == "edge")]
    if len(comps) <= 1:
        break
    main = comps[0]
    cid = collections.defaultdict(lambda: -1)
    cid.update({n: i for i, c in enumerate(comps) for n in c})
    changed = 0
    reach_main = set(nx.ancestors(DG, next(iter(main)))) | main          # nodes that can get to the main piece
    from_main = set(nx.descendants(DG, next(iter(main)))) | main         # nodes the main piece can get to
    for i, c in enumerate(comps[1:], 1):
        n0 = next(iter(c))
        if n0 not in reach_main:          # trapped: give it a way out (flip one link that leads into it)
            cand = [kk for a, b, kk in DG.in_edges(c, keys=True) if kk and cid[a] != i]
            if not cand:
                cand = [kk for a, b, kk in DG.out_edges(c, keys=True) if kk and cid[b] != i]
            if cand and make_two_way(min(cand, key=cost_key), "only way out of a one-way trap: two-way"):
                changed += 1
                break
        if n0 not in from_main:           # unreachable: give it a way in
            cand = [kk for a, b, kk in DG.out_edges(c, keys=True) if kk and cid[b] != i]
            if not cand:
                cand = [kk for a, b, kk in DG.in_edges(c, keys=True) if kk and cid[a] != i]
            if cand and make_two_way(min(cand, key=cost_key), "only way into a one-way pocket: two-way"):
                changed += 1
                break
    if not changed:
        break
_DG = travel_dir_edges(False)
_comps = sorted(nx.strongly_connected_components(_DG), key=len, reverse=True)
stats["directed_components"] = [len(c) for c in _comps[:6]]
# the clean-ups above can leave two junctions a few metres apart (a ramp gone, a doubled street merged): one junction
stats["short_contracted"] += contract_short()
stats["merged_pass"] += merge_pass_nodes()
for n in G.nodes:
    G.nodes[n]["kind"] = ("edge" if near_bounds(G.nodes[n]["p"]) else "deadend") if G.degree(n) == 1 else (
        "pass" if G.degree(n) == 2 else "junction")
stats["kinds"] = dict(collections.Counter(G.nodes[n]["kind"] for n in G.nodes))

# ================================================================ 2. CROSS-SECTIONS
# Rules (urban US practice: AASHTO Green Book / NACTO Urban Street Design Guide / MUTCD), in metres:
#   lane width    expressway 3.6 (12 ft) · arterial and collector 3.3 (11 ft) · local 3.0 (10 ft) ·
#                 a one-way local with a single lane 3.6 so a fire truck clears parked cars
#   parking lane  2.4 (8 ft) on arterials and collectors, 2.1 (7 ft) on locals; none on expressways; downtown
#                 two-way arterials keep their curb lanes for traffic and buses (no parking); downtown one-way
#                 arterials keep one loading/parking lane on the right
#   centre        two-way arterial with an odd OSM lane count: a 3.3 m two-way left-turn lane (it becomes a left
#                 turn pocket on the approach to a signal) · other two-way arterials and collectors: double yellow
#                 (0.3 m) · two-way locals: unmarked (residential practice) · one-way: none
#   expressway    1.2 m inside shoulder, 3.0 m outside shoulder per carriageway, 1.0 m median barrier if one
#                 polyline carries both directions
#   sidewalk      downtown 4.6 m paved (1.5 m furniture zone with tree grates + 3.1 m walk) · elsewhere a 2.0 m
#                 grass parkway with trees and a 1.8 m walk · expressways: none (a 2.0 m verge)
#   fit           the section has to fit between the buildings on either side; if it doesn't, parking goes first
#                 (one side, then both), then lanes narrow to 3.0 m, then the sidewalk to 2.4 m — each recorded
CLASS_NAME = {"highway": "expressway", "major": "arterial", "mid": "collector", "minor": "local"}

def design_section(d, half_room):
    """Cross-section of edge d: elements from the LEFT curb to the RIGHT curb, looking along the geometry
    (u -> v). Each element: [kind, width, dir] with dir +1 = traffic u -> v, -1 = v -> u, 0 = none.
    half_room = (left, right) clearance from the centreline to the buildings."""
    cls, lanes, oneway, core = d["cls"], max(1, d["lanes"]), d["oneway"], d["core"]
    why = []
    lw = road_profiles.LANE_W[cls]
    if cls == "minor" and oneway and lanes == 1:
        lw = 3.6
        why.append("single-lane one-way local: 3.6 m lane so emergency vehicles clear parked cars")
    pw = road_profiles.PARKING_W[cls]
    # parking by rule
    if cls == "highway":
        park = (False, False)
    elif cls == "major" and core and not oneway:
        park = (False, False)
        why.append("downtown two-way arterial: curb lanes kept for traffic and buses, no parking")
    elif cls == "major" and core and oneway:
        park = (False, True)
        why.append("downtown one-way arterial: one loading/parking lane on the right")
    else:
        park = (True, True)
    if d.get("frontage"):
        park = (False, False)
        why.append("frontage lanes along an expressway ramp's wall: no parking")
    if d.get("under"):
        # lower lanes under an elevated expressway (between its column lines): 3.6 m lanes, 1.5 m shoulders, no parking,
        # no sidewalk (highway-capitol request 4: ~11 m)
        lw = 3.6
        park = (False, False)
        why.append("lower lanes under the expressway decks: 3.6 m lanes, shoulders, no parking or sidewalk")
    if d.get("rb"):
        # roundabout (FHWA Roundabouts: An Informational Guide): the circulating lanes are wider than street lanes so a bus
        # or truck can swing round, there is no parking, and the island side has no sidewalk
        lw = 4.2
        park = (False, False)
        why.append("roundabout: 4.2 m circulating lanes, no parking")
    # centre treatment and lanes per direction
    centre = None
    if oneway:
        n_f = lanes
        n_b = 0
    else:
        if lanes == 1:
            lanes = 2
        if cls == "major" and lanes % 2 == 1 and lanes >= 3:
            centre = ("twltl", 3.3)
            n_f = n_b = (lanes - 1) // 2
            why.append(f"{lanes} lanes (odd): centre two-way left-turn lane")
        else:
            n_f = n_b = lanes // 2
            if cls in ("major", "mid"):
                centre = ("dy", 0.3)
            elif cls == "highway":
                centre = ("barrier", 1.0)
    sw = 0.0 if (cls == "highway" or d.get("under")) else (road_profiles.SIDEWALK_CORE if core else road_profiles.SIDEWALK_OTHER)

    def build(lw_, park_, sw_):
        travel = d["travel"] if oneway else 0
        elems = []
        if cls == "highway":
            if oneway:
                # in the travel frame: left shoulder, lanes, right shoulder
                tr = [["shoulder", 1.2, 0]] + [["lane", lw_, 1]] * n_f + [["shoulder", 3.0, 0]]
                elems = tr if travel >= 0 else [[k, w, -dd] for k, w, dd in reversed(tr)]
            else:
                elems = [["shoulder", 3.0, 0]] + [["lane", lw_, -1]] * n_b + [["barrier", 1.0, 0]] + [["lane", lw_, 1]] * n_f + [["shoulder", 3.0, 0]]
        elif oneway:
            tr = ([["parking", pw, 0]] if park_[0] else []) + [["lane", lw_, 1]] * n_f + ([["parking", pw, 0]] if park_[1] else [])
            elems = tr if travel >= 0 else [[k, w, -dd] for k, w, dd in reversed(tr)]
        else:
            elems = ([["parking", pw, 0]] if park_[0] else []) + [["lane", lw_, -1]] * n_b
            if centre:
                elems.append([centre[0], centre[1], 0])
            elems += [["lane", lw_, 1]] * n_f + ([["parking", pw, 0]] if park_[1] else [])
            if d.get("under"):
                elems = [["shoulder", 1.5, 0]] + elems + [["shoulder", 1.5, 0]]
        W = sum(e[1] for e in elems)
        return elems, W, sw_

    room = min(half_room)
    elems, W, sw2 = build(lw, park, sw)
    if cls != "highway" and W / 2 + sw > room:
        for step, (lw_, park_, sw_, note) in enumerate((
                (lw, (park[0], False) if park[1] and not park[0] else (False, park[1]), sw, "no room between the buildings: parking on one side only"),
                (lw, (False, False), sw, "no room between the buildings: no parking"),
                (3.0, (False, False), sw, "no room: lanes narrowed to 3.0 m"),
                (3.0, (False, False), 2.4, "no room: sidewalk narrowed to 2.4 m"))):
            elems, W, sw2 = build(lw_, park_, sw_)
            if W / 2 + sw_ <= room or step == 3:
                why.append(note)
                break
    # The pan is stolen from the outermost lane or stall, so W is unchanged and the ribbons
    # already in the city keep their edges. The curb face itself is a bevel (profiles.py).
    elems, gutter = road_profiles.carve_gutters(elems, cls, bool(d.get("under")))
    W = sum(e[1] for e in elems)
    if gutter:
        why.append("gutter pan carved off the outer lane or stall; carriageway width unchanged, curb face is a bevel")
    return {"elems": elems, "width": round(W, 2), "sidewalk": sw2, "parkway": (not core) and cls != "highway",
            "class": CLASS_NAME[cls], "why": why,
            "curb": road_profiles.curb_spec(cls, core), "gutter": gutter}


for u, v, k, d in G.edges(keys=True, data=True):
    g = d["geom"]
    s_cum = cumlen(g)
    L = s_cum[-1]
    rooms_l, rooms_r = [], []
    for f in (0.25, 0.5, 0.75):
        p, t = at_s(g, s_cum, L * f)
        nrm = (-t[1], t[0])
        rooms_l.append(clearance(p, nrm))
        rooms_r.append(clearance(p, (-nrm[0], -nrm[1])))
    d["section"] = design_section(d, (min(rooms_l), min(rooms_r)))
    d["width"] = d["section"]["width"]
    stats["section_" + d["section"]["class"]] += 1
    for w in d["section"]["why"]:
        if w.startswith("no room"):
            stats["fit_" + w[:30]] += 1

# ================================================================ 3. JUNCTIONS
# Curb-return radius by the larger street class (design vehicle: a city bus on arterials, a delivery truck on
# collectors, a car on locals): local 6 m, collector 7.5 m, arterial 9 m, expressway 15 m.
RADIUS = road_profiles.CURB_RETURN_RADIUS
RANK = {"minor": 0, "mid": 1, "major": 2, "highway": 3}
GORE_R = 1.0          # nose radius where two roads part at a shallow angle (fork, ramp, merge)


def leg_list(nodes_set):
    """Legs leaving a set of nodes (one node, or the members of a compound junction): every incident edge end
    whose other end is outside the set."""
    legs = []
    for n in nodes_set:
        for _, m, k, d in G.edges(n, keys=True, data=True):
            if m in nodes_set and m != n:
                continue              # internal edge of a compound junction
            ends = [n] if m != n else [n, "loop"]
            for e in ends:
                g = geom_from(d, n) if e != "loop" else geom_from(d, n)[::-1]
                s_cum = cumlen(g)
                L = s_cum[-1]
                p0 = g[0]
                q, _ = at_s(g, s_cum, min(8.0, L * 0.4))
                legs.append({"n": n, "m": m, "k": k, "d": d, "g": g, "p0": p0, "dir": unit((q[0] - p0[0], q[1] - p0[1])),
                             "W": d["width"], "L": L, "rev": e == "loop"})
    return legs


def corner_geometry(legs):
    """Sort legs counter-clockwise and work out, for each pair of neighbours, where their curbs meet and how far
    back each leg's mouth (the curb-return tangent point) is."""
    c = (sum(l["p0"][0] for l in legs) / len(legs), sum(l["p0"][1] for l in legs) / len(legs))
    legs.sort(key=lambda l: math.atan2(l["dir"][1], l["dir"][0]))
    for l in legs:
        l["mouth"] = 0.0
    corners = []
    nL = len(legs)
    for i in range(nL):
        A, B = legs[i], legs[(i + 1) % nL]
        la = (-A["dir"][1], A["dir"][0])            # left of A (counter-clockwise side)
        rb = (B["dir"][1], -B["dir"][0])            # right of B
        pa = (A["p0"][0] + la[0] * A["W"] / 2, A["p0"][1] + la[1] * A["W"] / 2)
        pb = (B["p0"][0] + rb[0] * B["W"] / 2, B["p0"][1] + rb[1] * B["W"] / 2)
        ang = (math.atan2(B["dir"][1], B["dir"][0]) - math.atan2(A["dir"][1], A["dir"][0])) % (2 * math.pi)
        R = RADIUS[max(A["d"]["cls"], B["d"]["cls"], key=lambda x: RANK[x])]
        x = line_x(pa, A["dir"], pb, B["dir"])
        # nearly parallel neighbours (a lane split, a ramp joining alongside) have no real corner: their curb lines
        # meet far down the road and the old rule swept the junction to its 30-40 m clamp, folding the ring
        if x is None or ang > math.radians(165) or ang < math.radians(8) or nL == 1:
            corners.append({"a": i, "b": (i + 1) % nL, "pt": None, "ta": 0.0, "tb": 0.0})
            continue
        pt, ta, tb = x
        # A curb return of radius R sits tan(ang/2) away from where the curb lines meet, which explodes at shallow
        # angles: a fork or a ramp at 20 deg with an expressway's 15 m radius swept the junction 40 m down both roads
        # and paved the wedge between them (the 20 Oct playtest's "huge unmarked apron"). Real forks and ramps end in
        # a gore with a small nose, so below 35 deg the radius is GORE_R; between 35 and 75 deg it grows back to R;
        # and the return never reaches more than R past the curb-line intersection.
        Re = R if ang >= math.radians(75) else (GORE_R if ang <= math.radians(35) else
                                                 GORE_R + (R - GORE_R) * (ang - math.radians(35)) / math.radians(40))
        tang = min(Re / math.tan(min(ang, math.radians(160)) / 2), R)
        ta2, tb2 = max(0.0, ta + tang), max(0.0, tb + tang)
        A["mouth"] = max(A["mouth"], ta2)
        B["mouth"] = max(B["mouth"], tb2)
        corners.append({"a": i, "b": (i + 1) % nL, "pt": pt, "ta": ta2, "tb": tb2, "R": R})
    for l in legs:
        # a junction never reaches far down a street: shallow forks get a straight join instead of a long taper
        l["mouth"] = min(max(l["mouth"], 3.0), 30.0 if l["d"]["cls"] == "highway" else 20.0)
    return c, corners


def mouth_points(l):
    p, t = at_s(l["g"], cumlen(l["g"]), l["mouth"])
    nrm = (-t[1], t[0])
    return ((p[0] + nrm[0] * l["W"] / 2, p[1] + nrm[1] * l["W"] / 2), (p[0] - nrm[0] * l["W"] / 2, p[1] - nrm[1] * l["W"] / 2), p, t)


def self_crossing(ring):
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            c, d = ring[j], ring[(j + 1) % n]
            x = seg_x(a, b, c, d)
            if x and 1e-6 < x[1] < 1 - 1e-6 and 1e-6 < x[2] < 1 - 1e-6:
                return True
    return False


def quad_bezier(a, c, b, n=6):
    return [((1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t * t * b[0], (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t * t * b[1])
            for t in (i / n for i in range(1, n))]


# every junction node gets its own curb-return polygon (legs include short links to a neighbouring junction, so a
# divided road's two crossings are drawn as two junctions joined by the median link, unioned in Unreal)
jnodes = [n for n in G.nodes if G.nodes[n]["kind"] == "junction"]
junctions = []
jid_of = {}
for n in jnodes:
    legs = leg_list({n})
    if len(legs) < 2:
        continue
    c, corners = corner_geometry(legs)
    ring = []
    plain = []
    for i, l in enumerate(legs):
        lp, rp, _, _ = mouth_points(l)
        ring += [rp, lp]
        plain += [rp, lp]
        cn = corners[i]
        if cn["pt"] is not None:
            nlp, nrp, _, _ = mouth_points(legs[cn["b"]])
            # a curb return only where the corner is a real corner (very shallow corners would fling the curve
            # far away): otherwise the two curbs are joined straight
            if math.dist(cn["pt"], lp) < 30.0 and math.dist(cn["pt"], nrp) < 30.0:
                ring += quad_bezier(lp, cn["pt"], nrp)
    if self_crossing(ring):
        # a folded ring leaves unpaved bow-tie holes in the lanes (found on Lake Shore Drive at Monroe, plan 1144, 220):
        # first try the mouths joined straight (a curb return thrown across a neighbour is the usual cause), else the
        # hull of the mouths and curb returns, which is never folded
        if not self_crossing(plain):
            ring = plain
            stats["junction_rings_straightened"] += 1
        else:
            ring = convex_hull(ring)
            stats["junction_rings_unfolded"] += 1
    if poly_area(ring) < 0:
        ring = ring[::-1]
    jid_of[n] = len(junctions)
    junctions.append({"id": len(junctions), "node": n, "c": G.nodes[n]["p"], "legs": legs, "corners": corners, "ring": ring})
stats["junctions"] = len(junctions)

# control units: junctions linked by a short street (a divided road's median crossing, an offset T) are run by one
# controller (one signal plan, one set of crosswalks), like real paired intersections
cu_parent = {j["id"]: j["id"] for j in junctions}


def cufind(i):
    while cu_parent[i] != i:
        cu_parent[i] = cu_parent[cu_parent[i]]
        i = cu_parent[i]
    return i


for u, v, k, d in G.edges(keys=True, data=True):
    if u in jid_of and v in jid_of and u != v and elen(d) < 30.0:
        cu_parent[cufind(jid_of[u])] = cufind(jid_of[v])
for J in junctions:
    J["unit"] = cufind(J["id"])
stats["control_units"] = len({J["unit"] for J in junctions})

# trim each edge to its junction mouths; a link inside a control unit is a median crossing
for u, v, k, d in G.edges(keys=True, data=True):
    d["s0"], d["s1"] = 0.0, elen(d)
    d["internal"] = u in jid_of and v in jid_of and u != v and junctions[jid_of[u]]["unit"] == junctions[jid_of[v]]["unit"]
for J in junctions:
    for l in J["legs"]:
        d = l["d"]
        forward = math.dist(d["geom"][0], l["p0"]) <= math.dist(d["geom"][-1], l["p0"]) and not l["rev"]
        if forward:
            d["s0"] = max(d["s0"], l["mouth"])
        else:
            d["s1"] = min(d["s1"], elen(d) - l["mouth"])
        l["forward"] = forward
for u, v, k, d in G.edges(keys=True, data=True):
    d["swallowed"] = d["s1"] - d["s0"] < 1.0
    stats["edges_swallowed"] += d["swallowed"]

# joints at pass nodes (same street changing lanes, or two streets meeting end to end): the convex hull of the two
# cross-sections fills the bend and tapers any width change
joints = []
for n in G.nodes:
    if G.nodes[n]["kind"] != "pass":
        continue
    pts = []
    for _, m, k, d in G.edges(n, keys=True, data=True):
        g = geom_from(d, n)
        t = unit((g[1][0] - g[0][0], g[1][1] - g[0][1]))
        nrm = (-t[1], t[0])
        p = g[0]
        W = d["width"]
        for s_ in (0.0, 2.0):
            q = (p[0] + t[0] * s_, p[1] + t[1] * s_)
            pts += [(q[0] + nrm[0] * W / 2, q[1] + nrm[1] * W / 2), (q[0] - nrm[0] * W / 2, q[1] - nrm[1] * W / 2)]
    joints.append(convex_hull(pts))
stats["joints"] = len(joints)


# ================================================================ 4. CONTROL
def leg_elems(l):
    """The leg's cross-section in its own frame (looking out of the junction): (kind, width, offset left+, dir)
    with dir +1 = leaving the junction, -1 = arriving."""
    d = l["d"]
    W = d["width"]
    x = W / 2
    res = []
    for kind, w, dd in d["section"]["elems"]:
        c = x - w / 2
        res.append((kind, w, c, dd) if l["forward"] else (kind, w, -c, -dd))
        x -= w
    return res if l["forward"] else res[::-1]


def leg_point(l, s, off):
    p, t = at_s(l["g"], cumlen(l["g"]), s)
    return (p[0] - t[1] * off, p[1] + t[0] * off), t


def turn_of(t_in, d_out):
    """Movement from arriving direction t_in to leaving direction d_out: L, S, R or U."""
    cr = t_in[0] * d_out[1] - t_in[1] * d_out[0]
    dt = t_in[0] * d_out[0] + t_in[1] * d_out[1]
    a = math.degrees(math.atan2(cr, dt))
    return "U" if abs(a) > 150 else ("L" if a > 32 else ("R" if a < -32 else "S"))


sig_pts = [tuple(n["p"]) for n in SD["nodes"] if n["signal"]]
sig_grid = collections.defaultdict(list)
for p in sig_pts:
    sig_grid[(int(p[0] // 50), int(p[1] // 50))].append(p)


def osm_signal_near(p, r=25.0):
    gx, gy = int(p[0] // 50), int(p[1] // 50)
    return any(math.dist(p, q) < r for u in range(gx - 1, gx + 2) for v in range(gy - 1, gy + 2) for q in sig_grid.get((u, v), ()))


units = collections.defaultdict(list)
for J in junctions:
    units[J["unit"]].append(J)
CONTROL = []        # one record per control unit
for uid, Js in units.items():
    c = (sum(J["c"][0] for J in Js) / len(Js), sum(J["c"][1] for J in Js) / len(Js))
    legs = [l for J in Js for l in J["legs"] if not l["d"]["internal"]]
    if len(legs) < 2:
        continue
    for l in legs:
        l["elems"] = leg_elems(l)
        l["in_lanes"] = [e for e in l["elems"] if e[0] == "lane" and e[3] == -1]
        l["out_lanes"] = [e for e in l["elems"] if e[0] == "lane" and e[3] == 1]
        l["twltl"] = any(e[0] == "twltl" for e in l["elems"])
        l["cls"] = l["d"]["cls"]
    # the streets meeting here: legs in line with each other (or sharing a name) are one street
    streets = []
    for l in legs:
        for st in streets:
            m = st[0]
            same_axis = abs(m["dir"][0] * l["dir"][0] + m["dir"][1] * l["dir"][1]) > 0.8
            if same_axis and (m["d"]["name"] == l["d"]["name"] or not m["d"]["name"] or not l["d"]["name"] or m["cls"] == l["cls"]):
                st.append(l)
                break
        else:
            streets.append([l])
    top = sorted((max(RANK[l["cls"]] for l in st) for st in streets), reverse=True)
    osm_sig = any(osm_signal_near(J["c"]) for J in Js)
    core = any(l["d"]["core"] for l in legs)
    why = []
    if len(streets) < 2:
        ctrl = "none"
        why.append("one street only (a fork or merge): yield, no control")
    elif osm_sig:
        ctrl = "signal"
        why.append("signalised in the real city (OpenStreetMap)")
    elif len(top) >= 2 and top[1] >= RANK["major"]:
        ctrl = "signal"
        why.append("two arterials cross: signal")
    elif core and len(top) >= 2 and top[0] >= RANK["major"] and top[1] >= RANK["mid"]:
        ctrl = "signal"
        why.append("downtown arterial meets a collector: signal")
    elif top[0] >= RANK["major"]:
        ctrl = "twostop"
        why.append("arterial meets a minor street: the minor street stops")
    elif len(top) >= 2 and top[0] == top[1]:
        ctrl = "allstop"
        why.append("equal minor streets: all-way stop")
    else:
        ctrl = "twostop"
        why.append("collector meets a local: the local stops")
    if any(l["cls"] == "highway" for l in legs) and ctrl in ("twostop", "allstop"):
        ctrl = "signal"
        why.append("at-grade expressway crossing: signal")
    rb_unit = any(l["d"]["rb"] for l in legs)
    if rb_unit:
        # a roundabout entry: traffic already circulating has the right of way, entering traffic yields (a yield line and
        # ONE WAY signs on the island, no signals, no stop signs, no lane-use arrows)
        ctrl = "yield"
        why = ["roundabout: entering traffic yields to circulating traffic"]
    # approaches and legal movements
    approaches = []
    for l in legs:
        if not l["in_lanes"]:
            continue
        t_in = (-l["dir"][0], -l["dir"][1])
        moves = {}
        for o in legs:
            if o is l:
                continue
            mv = turn_of(t_in, o["dir"])
            if mv == "U":
                continue
            if o["out_lanes"]:            # traffic may leave this way (two-way, or one-way leaving the junction)
                moves.setdefault(mv, []).append(o)
        stops = ctrl == "allstop" or (ctrl == "twostop" and RANK[l["cls"]] < top[0])
        approaches.append({"leg": l, "t": t_in, "moves": moves, "stop": stops, "yield": ctrl == "yield" and not l["d"]["rb"]})
    # phase groups for signals: approaches on one street axis move together
    groups = []
    for a in approaches:
        for gi, g in enumerate(groups):
            if abs(g[0]["t"][0] * a["t"][0] + g[0]["t"][1] * a["t"][1]) > 0.75:
                g.append(a)
                a["group"] = gi
                break
        else:
            a["group"] = len(groups)
            groups.append([a])
    if ctrl == "signal" and len(groups) < 2:
        ctrl = "none"
        why.append("only one direction ever arrives: no signal needed")
    CONTROL.append({"unit": uid, "c": c, "Js": Js, "legs": legs, "streets": len(streets), "ctrl": ctrl, "why": why,
                    "approaches": approaches, "ngroups": max(1, len(groups)), "core": core,
                    "phase": round(rnd(uid, "phase"), 3)})
    stats["ctrl_" + ctrl] += 1


# lane use per approach: which movements each arriving lane may make (only legal ones)
def lane_use(a):
    l = a["leg"]
    mv = set(a["moves"])
    lanes = sorted(l["in_lanes"], key=lambda e: e[2])          # inner (next to the centre) first
    n = len(lanes)
    use = {}
    ltl = None
    if l["twltl"] and "L" in mv:
        ltl = next(e for e in l["elems"] if e[0] == "twltl")
        use["ltl"] = {"L"}
        mv_t = mv - {"L"}
    else:
        mv_t = set(mv)
    for i, e in enumerate(lanes):
        u = set()
        if "S" in mv_t:
            u.add("S")
            if i == 0 and "L" in mv_t:
                u.add("L")
            if i == n - 1 and "R" in mv_t:
                u.add("R")
        else:
            if n == 1:
                u = set(mv_t)
            elif i < n - 1 or "R" not in mv_t:
                u = {"L"} if "L" in mv_t else set(mv_t)
            else:
                u = {"R"}
        use[i] = u
    return lanes, ltl, use


ARROW = {frozenset("L"): "L", frozenset("S"): "S", frozenset("R"): "R", frozenset("LS"): "LS", frozenset("SR"): "SR",
         frozenset("LR"): "LR", frozenset("LSR"): "LSR"}

# ================================================================ 5. MARKINGS, SIGNALS, SIGNS
# Crosswalks: every leg of a signalised or all-way-stop intersection (except expressway legs); at a two-way stop only
# across the street that stops (marking a crosswalk across uncontrolled arterial traffic would invite people into it).
# A crosswalk is 3.0 m wide at the junction mouth, continental bars 0.6 m wide every 1.2 m; the stop bar (0.6 m) sits
# 1.2 m behind it across the arriving lanes. Lane lines: 0.15 m; dashes 3 m with 9 m gaps (10 ft / 30 ft); solid
# white for the last 30 m before a stop bar (no lane changes into the junction); double yellow 2 x 0.12 m.
XW, SETBACK, BAR = (road_profiles.CONTINENTAL["width_m"], road_profiles.CONTINENTAL["stop_gap_m"],
                   road_profiles.CONTINENTAL["bar_m"])
MK = {"solid_white": [], "solid_white_thin": [], "dash_white": [], "solid_yellow": [], "dash_yellow": [], "bars": [],
      "arrows": [], "words": []}
SIG = {"poles": [], "heads": [], "peds": [], "cabinets": []}
SIGNS = []          # {kind, p, yaw (front normal), extra}
BARRICADES = []


def ribbon(d):
    """Road surface of an edge between its trimmed ends (butt ends: the junction polygons meet them). A street swallowed
    by its junctions keeps its whole ribbon, node to node: the rings are drawn from mouth to mouth and cut across a
    curved or long swallowed piece, which left lawn in the lanes (audit 20 Oct: 24 places, incl. Lake Shore Drive)."""
    g = d["geom"]
    s_cum = cumlen(g)
    sub = list(g) if d["swallowed"] else sub_polyline(g, s_cum, d["s0"], d["s1"])
    if len(sub) < 2:
        return None
    W = d["width"]
    return offset_polyline(sub, W / 2) + offset_polyline(sub, -W / 2)[::-1]


# A ribbon that folds over itself (a loop street that comes back to its own node, a hairpin tighter than half its width)
# can come out of a polygon union with its overlap as a hole: a curb island in the lanes (audit: 22 ribbons, e.g. the
# loop at plan -555, -720). Each segment of such a street also goes in as its own quad (a joint), so the union is solid.
for u, v, k, d in G.edges(keys=True, data=True):
    rb = ribbon(d)
    if rb is None or len(rb) > 600 or not self_crossing(rb):
        continue
    g = d["geom"]
    sub = list(g) if d["swallowed"] else sub_polyline(g, cumlen(g), d["s0"], d["s1"])
    for a, b in zip(sub, sub[1:]):
        t = unit((b[0] - a[0], b[1] - a[1]))
        if math.dist(a, b) < 0.05:
            continue
        a2, b2 = (a[0] - t[0] * 0.5, a[1] - t[1] * 0.5), (b[0] + t[0] * 0.5, b[1] + t[1] * 0.5)
        n_ = (-t[1] * d["width"] / 2, t[0] * d["width"] / 2)
        joints.append([(a2[0] + n_[0], a2[1] + n_[1]), (b2[0] + n_[0], b2[1] + n_[1]), (b2[0] - n_[0], b2[1] - n_[1]), (a2[0] - n_[0], a2[1] - n_[1])])
    stats["folded_ribbons_quadded"] += 1

# The paved surface, exactly what the Unreal builder lays as asphalt (edge ribbons, junction rings, joints). Nothing
# upright may stand on it: the 20 Oct playtest found signal poles, trees, lamps and signs in the lanes (props of one
# street landing on an overlapping street or inside a big junction), and a signal pole out in the lake.
ROAD_RINGS = [np.array(r, float) for r in ([ribbon(d) for u, v, k, d in G.edges(keys=True, data=True)]
                                           + [J["ring"] for J in junctions] + list(joints)) if r is not None and len(r) >= 3]
ROAD_CELL = 50.0
ROAD_GRID = collections.defaultdict(list)
for _i, _r in enumerate(ROAD_RINGS):
    (_x0, _y0), (_x1, _y1) = _r.min(0), _r.max(0)
    for _gx in range(int(_x0 // ROAD_CELL), int(_x1 // ROAD_CELL) + 1):
        for _gy in range(int(_y0 // ROAD_CELL), int(_y1 // ROAD_CELL) + 1):
            ROAD_GRID[(_gx, _gy)].append(_i)


def in_road(p):
    pt = np.array([p[:2]], float)
    for i in ROAD_GRID.get((int(p[0] // ROAD_CELL), int(p[1] // ROAD_CELL)), ()):
        if points_in_poly(pt, ROAD_RINGS[i])[0]:
            return True
    return False


def off_road(p, away, max_d=15.0, step=1.0, setback=0.0):
    """p if it stands off the pavement and on land (and off the L's columns and stairs), else the first such point
    stepping along `away`; None if none. setback: also at least this far from any pavement (tried first; if no such
    point within max_d, the plain rule)."""
    def ok(q):
        return (not in_road(q) and on_land(q) and not near_l(q, "posts", 0.6) and not in_polys(q, X_FP["posts"], 0.6)
                and not in_polys(q, X_FP["fill"]))
    if setback > 0:
        ring = [(math.cos(a * math.pi / 4) * setback, math.sin(a * math.pi / 4) * setback) for a in range(8)]
        for k in range(int(max_d / step) + 1):
            q = (p[0] + away[0] * step * k, p[1] + away[1] * step * k)
            if ok(q) and not any(in_road((q[0] + dx, q[1] + dy)) for dx, dy in ring):
                return q
    for k in range(int(max_d / step) + 1):
        q = (p[0] + away[0] * step * k, p[1] + away[1] * step * k)
        if ok(q):
            return q
    return None


# The elevated L (agent "the-l", Scripts/rail/l_layout.py) publishes its footprint: deck and platform polygons, column
# and stair footprints (Saved/Rail/l_footprint.json). Its request, 20 Oct: no trees or lamps under the deck (they grew
# up through the girders on Wabash, Van Buren, Wells and Lake), nothing on a column or stair, and signal heads under
# the deck on low posts (z <= 4.2 m) instead of 5.6 m mast arms that run into the girders.
L_FP = {"deck": [], "posts": []}
_lfp = ROOT / "Saved/Rail/l_footprint.json"
if _lfp.exists():
    _j = json.load(open(_lfp))
    L_FP["deck"] = [np.array(r, float) for r in _j.get("deck", []) + _j.get("platforms", []) if len(r) >= 3]
    L_FP["posts"] = [np.array(r, float) for r in _j.get("columns", []) + _j.get("stairs", []) if len(r) >= 3]
L_GRID = {k: collections.defaultdict(list) for k in L_FP}
for _k, _rs in L_FP.items():
    for _i, _r in enumerate(_rs):
        (_x0, _y0), (_x1, _y1) = _r.min(0) - 4, _r.max(0) + 4
        for _gx in range(int(_x0 // 25), int(_x1 // 25) + 1):
            for _gy in range(int(_y0 // 25), int(_y1 // 25) + 1):
                L_GRID[_k][(_gx, _gy)].append(_i)
stats["l_footprint_polys"] = {k: len(v) for k, v in L_FP.items()}


def near_l(p, kind, margin):
    """True if p is inside one of the L's `kind` polygons ("deck" or "posts") or within `margin` metres of one."""
    if not L_FP[kind]:
        return False
    q = np.array([p[:2]], float)
    for i in L_GRID[kind].get((int(p[0] // 25), int(p[1] // 25)), ()):
        r = L_FP[kind][i]
        if points_in_poly(q, r)[0]:
            return True
        a, b = r, np.roll(r, -1, axis=0)
        dd = b - a
        L2 = (dd ** 2).sum(1)
        L2[L2 == 0] = 1e-12
        t = np.clip(((q - a) * dd).sum(1) / L2, 0, 1)
        if np.sqrt(((a + dd * t[:, None] - q) ** 2).sum(1)).min() < margin:
            return True
    return False




def rect(c, t, along, across):
    n = (-t[1], t[0])
    ha, hc = along / 2, across / 2
    return [[round(c[0] + t[0] * sa * ha + n[0] * sc * hc, 2), round(c[1] + t[1] * sa * ha + n[1] * sc * hc, 2)]
            for sa, sc in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def yaw_of(v):
    return round(math.degrees(math.atan2(v[1], v[0])) % 360, 1)


def turn_samples(C):
    """Turn paths through a control unit as the traffic and self-driving code draw them (ASkysterTraffic: a quadratic
    Bezier from an arriving lane's end at the junction mouth to a leaving lane's start, the control point where the two
    lane lines meet, else halfway), for every left and right movement and every lane pair: an array of sample points."""
    pts = []
    for a in C["approaches"]:
        l = a["leg"]
        for mv, outs in a["moves"].items():
            if mv not in ("L", "R"):
                continue
            for o in outs:
                for e in l["in_lanes"]:
                    p0, t0 = leg_point(l, l["mouth"], e[2])
                    d0 = (-t0[0], -t0[1])
                    for e2 in o["out_lanes"]:
                        p2, t2 = leg_point(o, o["mouth"], e2[2])
                        x = line_x(p0, d0, p2, (-t2[0], -t2[1]))
                        c1 = x[0] if (x and 0 < x[1] < 60 and 0 < x[2] < 60) else ((p0[0] + p2[0]) / 2, (p0[1] + p2[1]) / 2)
                        for k in range(1, 12):
                            tt = k / 12.0
                            pts.append(((1 - tt) ** 2 * p0[0] + 2 * (1 - tt) * tt * c1[0] + tt * tt * p2[0],
                                        (1 - tt) ** 2 * p0[1] + 2 * (1 - tt) * tt * c1[1] + tt * tt * p2[1]))
    return np.array(pts, float) if pts else np.zeros((0, 2))


TURN_CLEAR = 1.5            # poles and cabinets keep this far from every turn path (playtest-chicago, 21 Oct: 216 of 2,611
                            # turn movements passed within 1.3 m of a pole, cabinet or column, and the car stopped dead)


def clear_of_turns(q, out, turns, step=0.5, max_d=8.0):
    """q, or the first point stepping along `out` that is TURN_CLEAR from every turn path and still a good place to
    stand (off the pavement by 1.2 m, on land, off columns); q unchanged if none."""
    if len(turns) == 0:
        return q
    ring = [(math.cos(a_ * math.pi / 4) * 1.2, math.sin(a_ * math.pi / 4) * 1.2) for a_ in range(8)]
    for k in range(int(max_d / step) + 1):
        r = (q[0] + out[0] * step * k, q[1] + out[1] * step * k)
        if np.sqrt(((turns - np.array(r)) ** 2).sum(1)).min() < TURN_CLEAR:
            continue
        if k == 0:
            return r
        if (not in_road(r) and on_land(r) and not near_l(r, "posts", 0.6) and not in_polys(r, X_FP["posts"], 0.6)
                and not in_polys(r, X_FP["fill"]) and not any(in_road((r[0] + dx, r[1] + dy)) for dx, dy in ring)):
            stats["signal_props_moved_off_turn_paths"] += 1
            return r
    stats["signal_props_still_near_turn_paths"] += 1
    return q


for C in CONTROL:
    ctrl = C["ctrl"]
    for l in C["legs"]:
        stops_here = any(a["leg"] is l and a["stop"] for a in C["approaches"])
        l["xw"] = l["cls"] != "highway" and (ctrl in ("signal", "allstop") or (ctrl == "twostop" and stops_here)
                                              or (ctrl == "yield" and not l["d"]["rb"]))
        # at a roundabout the crosswalk sits one car length back from the yield line (a driver who has yielded is past
        # the people crossing), and nothing is marked across the circulating lanes
        l["xw0"] = l["mouth"] + (6.5 if ctrl == "yield" else 0.0)
        l["stop_s"] = (l["mouth"] + 0.9) if ctrl == "yield" else (l["mouth"] + ((XW + SETBACK) if l["xw"] else 1.0) + BAR / 2)
        l["mark_back"] = (l["xw0"] + XW + 0.3) if (ctrl == "yield" and l["xw"]) else (
            l["stop_s"] + BAR / 2 + 0.3 if (l["xw"] or ctrl != "none") else l["mouth"] + 0.3)
        l["unit_ctrl"] = ctrl
        l["unit"] = C
        d = l["d"]
        d.setdefault("end_legs", {})["u" if l["forward"] else "v"] = l
        # crosswalk bars
        if l["xw"]:
            p, t = at_s(l["g"], cumlen(l["g"]), l["xw0"] + XW / 2)
            nrm = (-t[1], t[0])
            k = -l["W"] / 2 + 0.6
            while k <= l["W"] / 2 - 0.5:
                MK["bars"].append(rect((p[0] + nrm[0] * k, p[1] + nrm[1] * k), t, XW, 0.6))
                k += 1.2
    for a in C["approaches"]:
        l = a["leg"]
        lanes, ltl, use = lane_use(a)
        a["lanes"], a["ltl"], a["use"] = lanes, ltl, use
        stopping = ctrl == "signal" or a["stop"]
        if a.get("yield"):
            # yield line: a row of white triangles ("shark teeth", MUTCD 3B.16) pointing at the arriving driver
            for e in lanes:
                k_ = e[2] - e[1] / 2 + 0.35
                while k_ + 0.6 <= e[2] + e[1] / 2 - 0.1:
                    pa, t = leg_point(l, l["stop_s"] - 0.45, k_)
                    pb, _ = leg_point(l, l["stop_s"] - 0.45, k_ + 0.6)
                    tip, _ = leg_point(l, l["stop_s"] + 0.45, k_ + 0.3)
                    MK["bars"].append([[round(pa[0], 2), round(pa[1], 2)], [round(pb[0], 2), round(pb[1], 2)], [round(tip[0], 2), round(tip[1], 2)]])
                    k_ += 0.9
            stats["yield_lines"] += 1
        if stopping:
            arriving = lanes + ([ltl] if ltl else [])
            lo = min(e[2] - e[1] / 2 for e in arriving)
            hi = max(e[2] + e[1] / 2 for e in arriving)
            p, t = leg_point(l, l["stop_s"], (lo + hi) / 2)
            MK["bars"].append(rect(p, t, BAR, hi - lo - 0.2))
        # lane-use arrows (and ONLY where a lane may only turn) at real junctions with a choice of lanes
        if len(C["legs"]) >= 3 and (len(lanes) >= 2 or ltl) and ctrl != "yield":
            items = [(e, use[i]) for i, e in enumerate(lanes)] + ([(ltl, use["ltl"])] if ltl else [])
            # arrows stay on this street's own pavement: clear of the junction at its far end too (the audit found
            # 111 arrows inside the next junction's ring on short blocks)
            far_trim = (elen(l["d"]) - l["d"]["s1"]) if l["forward"] else l["d"]["s0"]
            room = l["L"] - far_trim - l["stop_s"] - 10.0
            for e, u in items:
                kind = ARROW.get(frozenset(u))
                if not kind or (kind == "LSR"):
                    continue
                for s_ in (l["stop_s"] + 7.0, l["stop_s"] + 37.0):
                    if s_ - l["stop_s"] > room:
                        break
                    p, t = leg_point(l, s_, e[2])
                    MK["arrows"].append({"p": [round(p[0], 2), round(p[1], 2)], "yaw": yaw_of((-t[0], -t[1])), "kind": kind})
                    if kind in ("L", "R"):
                        q, _ = leg_point(l, s_ - 5.0, e[2])
                        MK["words"].append({"p": [round(q[0], 2), round(q[1], 2)], "yaw": yaw_of((-t[0], -t[1])), "word": "ONLY"})
                stats["arrows_" + kind] += 1
        # roundabout: a ONE WAY sign on the island straight ahead of each entry, its arrow to the right (counter-clockwise)
        if a.get("yield"):
            ring_w = max((o["W"] for o in C["legs"] if o["d"]["rb"]), default=8.4)
            c_ = l["p0"]
            ti = a["t"]
            ps = (c_[0] + ti[0] * (ring_w / 2 + 3.0), c_[1] + ti[1] * (ring_w / 2 + 3.0))
            SIGNS.append({"kind": "oneway", "p": ps, "yaw": yaw_of((-ti[0], -ti[1])), "arrow": yaw_of((ti[1], -ti[0]))})
        # stop signs at the near right, facing the arriving driver
        if a["stop"]:
            p, t = leg_point(l, l["stop_s"] + 0.5, l["W"] / 2 + 0.8)
            SIGNS.append({"kind": "stop", "p": p, "yaw": yaw_of(t), "allway": ctrl == "allstop"})
    # signals: a mast arm on the far-right corner for each approach, one head over each arriving lane (a left-arrow
    # head over a left-turn-only lane), a second pole-mounted head where an approach has a single lane;
    # pedestrian heads at both ends of every crosswalk, walking with the street they run alongside
    if ctrl == "signal":
        c = C["c"]
        corners = [cn["pt"] for J in C["Js"] for cn in J["corners"] if cn["pt"] is not None]
        turns = turn_samples(C)
        for a in C["approaches"]:
            l, t = a["leg"], a["t"]
            left = (-t[1], t[0])
            best = None
            for q in corners:
                v = (q[0] - c[0], q[1] - c[1])
                along = v[0] * t[0] + v[1] * t[1]
                right = -(v[0] * left[0] + v[1] * left[1])
                if along > 1.0 and right > 1.0 and (best is None or along + right < best[0]):
                    best = (along + right, q)
            arriving = a["lanes"] + ([a["ltl"]] if a["ltl"] else [])
            # in the driver's frame (left +), lane centres are at -offset (offsets are measured looking outward)
            lats = [-e[2] for e in arriving]
            if best:
                q = best[1]
                out = unit((q[0] - c[0], q[1] - c[1]))
                pole = (q[0] + out[0] * 2.0, q[1] + out[1] * 2.0)
            else:          # the stem of a T: pole on the far curb, in line with the right edge of the arriving lanes
                far = max(o["W"] for o in C["legs"] if o is not l) / 2 + 2.0
                lat_r = min(lats) - 2.0
                pole = (c[0] + t[0] * far + left[0] * lat_r, c[1] + t[1] * far + left[1] * lat_r)
            # 1.2 m behind the kerb (playtest-austin, 21 Oct: 177 of 454 Austin poles stood within 0.5 m of the carriageway
            # and a car cutting a corner by a metre mounted the kerb and pinned against them)
            moved = off_road(pole, unit((pole[0] - c[0], pole[1] - c[1])), max_d=25.0, setback=1.2)
            if moved is None:
                stats["signal_approach_dropped_no_curb"] += 1      # no sidewalk or land within 25 m: no pole in the lanes
                continue
            if moved != pole:
                stats["signal_pole_moved_off_road"] += 1
                pole = moved
            pole = clear_of_turns(pole, unit((pole[0] - c[0], pole[1] - c[1])), turns)
            lat_pole = (pole[0] - c[0]) * left[0] + (pole[1] - c[1]) * left[1]
            under_l = near_l(pole, "deck", 1.0) or any(
                near_l((pole[0] + left[0] * (lat - lat_pole), pole[1] + left[1] * (lat - lat_pole)), "deck", 0.5)
                for lat in lats if 0.5 <= lat - lat_pole <= 15.0)
            if under_l:
                # under the L: a 4.2 m post with the heads on it (Chicago mounts them low or on the structure)
                stats["signal_low_under_l"] += 1
                ltl_only = any((e is a["ltl"]) or (a["use"].get(a["lanes"].index(e) if e in a["lanes"] else "ltl") == {"L"}) for e in arriving)
                for j, typ in enumerate(("3", "L") if ltl_only else ("3",)):
                    hp = (pole[0] + left[0] * (0.45 + 0.5 * j), pole[1] + left[1] * (0.45 + 0.5 * j))
                    SIG["heads"].append({"p": [round(hp[0], 2), round(hp[1], 2)], "yaw": yaw_of((-t[0], -t[1])), "z": 4.2, "low": True,
                                         "type": typ, "unit": C["unit"], "group": a["group"], "ngroups": C["ngroups"], "phase": C["phase"]})
                SIG["poles"].append({"p": [round(pole[0], 2), round(pole[1], 2)], "yaw": yaw_of(left), "arm": 0.0, "low": True})
                continue
            arm = 0.0
            for e, lat in zip(arriving, lats):
                dist = lat - lat_pole
                if dist < 0.5 or dist > 15.0:
                    continue
                hp = (pole[0] + left[0] * dist, pole[1] + left[1] * dist)
                if not in_road(hp):
                    # the pole had to step far off the corner: a head out over the sidewalk or lawn helps no one (the
                    # audit found 171); the approach keeps a head on the pole instead
                    stats["signal_heads_off_road_skipped"] += 1
                    continue
                only_left = (e is a["ltl"]) or (a["use"].get(a["lanes"].index(e) if e in a["lanes"] else "ltl") == {"L"})
                SIG["heads"].append({"p": [round(hp[0], 2), round(hp[1], 2)], "yaw": yaw_of((-t[0], -t[1])), "z": 5.6,
                                     "type": "L" if only_left else "3", "unit": C["unit"], "group": a["group"],
                                     "ngroups": C["ngroups"], "phase": C["phase"]})
                arm = max(arm, dist)
            if len(arriving) == 1 or arm == 0.0:
                SIG["heads"].append({"p": [round(pole[0], 2), round(pole[1], 2)], "yaw": yaw_of((-t[0], -t[1])), "z": 3.4,
                                     "type": "3", "unit": C["unit"], "group": a["group"], "ngroups": C["ngroups"], "phase": C["phase"]})
            SIG["poles"].append({"p": [round(pole[0], 2), round(pole[1], 2)], "yaw": yaw_of(left), "arm": round(max(arm + 0.8, 1.5), 2)})
        for l in C["legs"]:
            if not l["xw"]:
                continue
            own = next((a["group"] for a in C["approaches"] if abs(a["t"][0] * l["dir"][0] + a["t"][1] * l["dir"][1]) > 0.75), None)
            others = sorted({a["group"] for a in C["approaches"]} - {own})
            if not others:
                continue
            ends = [leg_point(l, l["mouth"] + XW / 2, side * (l["W"] / 2 + 0.7)) for side in (1, -1)]
            for (pa, t), (pb, _) in (ends, ends[::-1]):
                SIG["peds"].append({"p": [round(pa[0], 2), round(pa[1], 2)], "yaw": yaw_of((pb[0] - pa[0], pb[1] - pa[1])),
                                    "unit": C["unit"], "group": others[0], "ngroups": C["ngroups"], "phase": C["phase"]})
        if corners:
            q = corners[0]
            out = unit((q[0] - c[0], q[1] - c[1]))
            cb = off_road((q[0] + out[0] * 4.0, q[1] + out[1] * 4.0), out, setback=1.2)
            if cb:
                cb = clear_of_turns(cb, out, turns)
                SIG["cabinets"].append({"p": [round(cb[0], 2), round(cb[1], 2)], "yaw": yaw_of(out)})
    # one-way streets: ONE WAY signs on both corners of the leg (arrow along the traffic), DO NOT ENTER facing the
    # junction where traffic only comes out of a street
    if ctrl != "none" or len(C["legs"]) >= 3:
        for l in C["legs"]:
            if l["cls"] == "highway" or not l["d"]["oneway"] or l["d"]["rb"]:
                continue                     # (roundabout arcs: the ONE WAY signs on the island say it)
            arrow = l["dir"] if l["out_lanes"] else (-l["dir"][0], -l["dir"][1])
            for side in (1, -1):
                p, t = leg_point(l, l["mouth"] + 0.5, side * (l["W"] / 2 + 1.2))
                SIGNS.append({"kind": "oneway", "p": p, "yaw": yaw_of((-t[1] * side, t[0] * side)), "arrow": yaw_of(arrow)})
                if not l["out_lanes"]:
                    q, _ = leg_point(l, l["mouth"] + XW + 1.5, side * (l["W"] / 2 + 0.8))
                    SIGNS.append({"kind": "noentry", "p": q, "yaw": yaw_of((-t[0], -t[1]))})
            stats["oneway_legs_signed"] += 1

# lane lines along each edge, between the stop bars at its two ends
DASH, GAP, APPROACH = 3.0, 9.0, 30.0


def edge_line(g, s_cum, a, b, off):
    seg = sub_polyline(g, s_cum, a, b)
    if len(seg) < 2:
        return None
    return [[round(x, 2), round(y, 2)] for x, y in offset_polyline(seg, off)]


def put(kind, g, s_cum, a, b, off):
    if b - a < 0.5:
        return
    if kind in ("dash_white", "dash_yellow"):
        s = a + (h32(round(off, 1), round(a)) % 12)
        while s < b:
            ln = edge_line(g, s_cum, s, min(b, s + DASH), off)
            if ln:
                MK[kind].append(ln)
            s += DASH + GAP
    else:
        ln = edge_line(g, s_cum, a, b, off)
        if ln:
            MK[kind].append(ln)


for u, v, k, d in G.edges(keys=True, data=True):
    if d["swallowed"] or d["internal"]:
        continue
    g = d["geom"]
    s_cum = cumlen(g)
    el = d.get("end_legs", {})
    ua, va = el.get("u"), el.get("v")
    sa = d["s0"] + ((ua["mark_back"] - ua["mouth"]) if ua else 0.3)
    sb = d["s1"] - ((va["mark_back"] - va["mouth"]) if va else 0.3)
    if sb - sa < 2.0:
        continue
    elems = d["section"]["elems"]
    W = d["width"]
    # approach zones: +1 traffic arrives at v, -1 traffic at u (only where a real junction is)
    zone_v = (max(sa, sb - APPROACH), sb) if va and len(va["unit"]["legs"]) >= 3 else None
    zone_u = (sa, min(sb, sa + APPROACH)) if ua and len(ua["unit"]["legs"]) >= 3 else None
    pocket_v = (max(sa, sb - 45.0), sb) if va and va["unit_ctrl"] == "signal" else None
    pocket_u = (sa, min(sb, sa + 45.0)) if ua and ua["unit_ctrl"] == "signal" else None
    if pocket_u and pocket_v and pocket_u[1] > pocket_v[0]:
        mid = (sa + sb) / 2
        pocket_u, pocket_v = (sa, mid), (mid, sb)
    x = W / 2
    for i in range(len(elems) - 1):
        A, B = elems[i], elems[i + 1]
        x -= A[1]
        off = x                                   # boundary between A (left) and B (right)
        ka, kb = A[0], B[0]
        if ka == "lane" and kb == "lane" and A[2] == B[2]:
            zone = zone_v if A[2] == 1 else zone_u
            if zone:
                lo, hi = zone
                put("solid_white", g, s_cum, lo, hi, off)
                if A[2] == 1:
                    put("dash_white", g, s_cum, sa, lo, off)
                else:
                    put("dash_white", g, s_cum, hi, sb, off)
            else:
                put("dash_white", g, s_cum, sa, sb, off)
        elif {ka, kb} == {"lane", "parking"} or {ka, kb} == {"lane", "gutter"}:
            put("solid_white_thin", g, s_cum, sa, sb, off)
        elif {ka, kb} == {"lane", "shoulder"}:
            lane = A if ka == "lane" else B
            shoulder_right_of_travel = (kb == "shoulder") == (lane[2] == 1)
            put("solid_white" if shoulder_right_of_travel else "solid_yellow", g, s_cum, sa, sb, off)
        elif "barrier" in (ka, kb):
            put("solid_yellow", g, s_cum, sa, sb, off + (0.15 if kb == "barrier" else -0.15))
    # centre treatments
    x = W / 2
    for kind, w, dd in elems:
        c = x - w / 2
        x -= w
        if kind == "dy":
            put("solid_yellow", g, s_cum, sa, sb, c + 0.11)
            put("solid_yellow", g, s_cum, sa, sb, c - 0.11)
        elif kind == "twltl":
            lt, rt = c + w / 2, c - w / 2          # left edge (towards -1 lanes), right edge (towards +1 lanes)
            plain = [(sa, sb)]
            if pocket_u:
                plain = [(max(a_, pocket_u[1]), b_) for a_, b_ in plain if b_ > pocket_u[1]]
                # -1 traffic turns left into the pocket from its side: white line there, double yellow opposite
                put("solid_white", g, s_cum, pocket_u[0], pocket_u[1], lt - 0.1)
                put("solid_yellow", g, s_cum, pocket_u[0], pocket_u[1], rt + 0.1)
                put("solid_yellow", g, s_cum, pocket_u[0], pocket_u[1], rt + 0.32)
            if pocket_v:
                plain = [(a_, min(b_, pocket_v[0])) for a_, b_ in plain if a_ < pocket_v[0]]
                put("solid_white", g, s_cum, pocket_v[0], pocket_v[1], rt + 0.1)
                put("solid_yellow", g, s_cum, pocket_v[0], pocket_v[1], lt - 0.1)
                put("solid_yellow", g, s_cum, pocket_v[0], pocket_v[1], lt - 0.32)
            for a_, b_ in plain:
                # two-way left-turn lane: solid yellow outside, broken yellow inside, on both edges (MUTCD 3B-7)
                put("solid_yellow", g, s_cum, a_, b_, lt - 0.1)
                put("dash_yellow", g, s_cum, a_, b_, lt - 0.32)
                put("solid_yellow", g, s_cum, a_, b_, rt + 0.1)
                put("dash_yellow", g, s_cum, a_, b_, rt + 0.32)
for k_, v_ in MK.items():
    stats["mk_" + k_] = len(v_)
stats["signal_heads"] = len(SIG["heads"])
stats["signal_poles"] = len(SIG["poles"])
stats["ped_heads"] = len(SIG["peds"])
stats["signs"] = len(SIGNS)


# ================================================================ 6. FURNITURE
# Each item has a reason (kept in its "why"):
#   lamps     along the curb in the 0.6 m furniture zone: arterials every 30 m both sides (staggered), collectors 35 m,
#             locals 40 m on one side, expressways 50 m on the verge; none inside a junction or over a crosswalk
#   trees     downtown: tree grates every 9 m, 1.1 m behind the curb; elsewhere: in the grass parkway every 10 m;
#             none within 12 m of a junction (drivers must see across the corner) or within 3 m of a lamp
#   hydrants  one at a corner of every intersection, and every 120 m along longer blocks (fire code spacing)
#   bins      downtown, two corners of every signalised intersection, and at bus stops
#   bus stops arterials only: on the far side of a signalised intersection (the bus clears the junction before it
#             stops), at least 350 m apart along the same street; sign + bench + bin (+ shelter downtown)
#   racks     downtown, mid-block every ~90 m on one side
#   mailboxes downtown, at a corner of every third signalised intersection
#   drains    in the gutter just upstream of every crosswalk (water runs to the low corner)
#   manholes  in the traffic lanes every 60-90 m
#   speed     arterials and collectors longer than 150 m: one per direction 25 m after the intersection
#   names     street-name blades on a corner of every intersection of two named streets
#   dumpsters only behind buildings, on the side away from the street, where there is room (service side) — never
#             on a sidewalk or a plaza
PROPS = []


def prop(kind, p, yaw, why, **kw):
    d_ = {"t": kind, "p": [round(p[0], 2), round(p[1], 2)], "yaw": round(yaw % 360, 1), "why": why}
    d_.update(kw)
    PROPS.append(d_)


def edge_point(d, s, off):
    g = d["geom"]
    p, t = at_s(g, cumlen(g), s)
    return (p[0] - t[1] * off, p[1] + t[0] * off), t


lamp_pts = []
lamp_grid = collections.defaultdict(list)


def near_pts(gridd, p, r, cell=30.0):
    gx, gy = int(p[0] // cell), int(p[1] // cell)
    return any(math.dist(p, q) < r for u in range(gx - 1, gx + 2) for v in range(gy - 1, gy + 2) for q in gridd.get((u, v), ()))


def add_grid(gridd, p, cell=30.0):
    gridd[(int(p[0] // cell), int(p[1] // cell))].append(p)


busstop_by_street = collections.defaultdict(list)
tree_grid = collections.defaultdict(list)
for u, v, k, d in G.edges(keys=True, data=True):
    if d["swallowed"] or d["internal"]:
        continue
    cls, sec = d["cls"], d["section"]
    W = d["width"]
    el = d.get("end_legs", {})
    ua, va = el.get("u"), el.get("v")
    sa = d["s0"] + ((ua["mark_back"] - ua["mouth"]) if ua else 0.0) + 4.0
    sb = d["s1"] - ((va["mark_back"] - va["mouth"]) if va else 0.0) - 4.0
    if sb - sa < 4.0:
        continue
    # lamps
    step = {"highway": 50.0, "major": 30.0, "mid": 35.0, "minor": 40.0}[cls]
    sides = (1, -1) if cls != "minor" else ((1,) if h32(u, v, k) & 1 else (-1,))
    for side in sides:
        s = sa + (step / 2 if side < 0 and cls != "minor" else 0.0)
        while s <= sb:
            off = side * (W / 2 + (1.5 if cls == "highway" else 0.6))
            p, t = edge_point(d, s, off)
            if on_land(p) and not near_pts(lamp_grid, p, 12.0):
                prop("lamp_hw" if cls == "highway" else "lamp", p, math.degrees(math.atan2(-t[0] * side, t[1] * side)) + 180,
                     f"{CLASS_NAME[cls]} street lighting every {int(step)} m")
                add_grid(lamp_grid, p)
            s += step
    if cls == "highway":
        continue
    # trees
    core = d["core"]
    if sec["sidewalk"] >= 3.0 or sec["parkway"]:
        tstep = 9.0 if core else 10.0
        for side in (1, -1):
            s = sa + 8.0 + rnd(u, v, side) * 3
            while s <= sb - 8.0:
                p, t = edge_point(d, s, side * (W / 2 + (1.1 if core else 1.0)))
                if on_land(p) and not near_pts(lamp_grid, p, 3.0) and not near_pts(tree_grid, p, 6.0, 20.0):
                    prop("tree", p, rnd(p[0], p[1]) * 360, "street tree in a grate" if core else "street tree in the parkway",
                         pit="grate" if core else "grass", city=d["city"], sp=("liveoak" if d["city"] == "austin" else ["honeylocust", "linden", "elm"][h32(round(s)) % 3]),
                         scale=round(0.85 + 0.35 * rnd(p[1], p[0]), 2))
                    add_grid(tree_grid, p, 20.0)
                s += tstep
    # hydrants along long blocks
    if sb - sa > 140:
        s = sa + 120.0
        while s < sb - 20:
            p, t = edge_point(d, s, (W / 2 + 0.5) * (1 if h32(u, k) & 1 else -1))
            if on_land(p):
                prop("hydrant", p, math.degrees(math.atan2(t[1], t[0])), "hydrant spacing along a long block (120 m)")
            s += 120.0
    # racks downtown
    if core and sb - sa > 60:
        s = (sa + sb) / 2
        while s < sb - 10:
            p, t = edge_point(d, s, (W / 2 + 0.9) * (1 if h32(v, k) & 1 else -1))
            if on_land(p):
                prop("bikerack", p, math.degrees(math.atan2(t[1], t[0])), "bike parking in the downtown furniture zone")
            s += 90.0
    # manholes in the lanes
    lanes = [(c_, w_) for c_, w_ in (((W / 2 - sum(e[1] for e in sec["elems"][:i]) - e[1] / 2), e[1]) for i, e in enumerate(sec["elems"]))
             if True]
    lane_c = [W / 2 - sum(e[1] for e in sec["elems"][:i]) - e[1] / 2 for i, e in enumerate(sec["elems"]) if e[0] == "lane"]
    if lane_c:
        s = sa + 20 + rnd(u, v, "mh") * 30
        while s < sb:
            p, t = edge_point(d, s, lane_c[h32(round(s)) % len(lane_c)])
            prop("manhole", p, rnd(s) * 360, "utility access in the traffic lane")
            s += 60 + rnd(s, "mh") * 30
    # speed limit signs, per direction, after the intersection
    if cls in ("major", "mid") and d["s1"] - d["s0"] > 150:
        for dirn in ((1, -1) if not d["oneway"] else ((d["travel"],))):
            s_ = sa + 25.0 if dirn == 1 else sb - 25.0
            p, t = edge_point(d, s_, -(W / 2 + 0.6) * dirn)
            SIGNS.append({"kind": "speed", "p": p, "yaw": yaw_of((-t[0] * dirn, -t[1] * dirn)), "mph": int(d["speed"])})
    # dead ends: DEAD END at the entrance, a barricade at the end
    for end, node in (("u", u), ("v", v)):
        if G.nodes[node]["kind"] != "deadend":
            continue
        other = el.get("v" if end == "u" else "u")
        if other:
            s_in = d["s0"] + 8.0 if end == "v" else d["s1"] - 8.0
            dirn = 1 if end == "v" else -1
            p, t = edge_point(d, s_in, -(W / 2 + 0.8) * dirn)
            SIGNS.append({"kind": "deadend", "p": p, "yaw": yaw_of((-t[0] * dirn, -t[1] * dirn))})
        s_end = 0.8 if end == "u" else elen(d) - 0.8
        p, t = edge_point(d, s_end, 0.0)
        BARRICADES.append({"p": [round(p[0], 2), round(p[1], 2)], "yaw": yaw_of(t), "w": round(W - 0.6, 2)})

# per intersection: hydrant, bins, mailbox, drains, name blades, bus stops
for C in CONTROL:
    if not C["approaches"]:
        continue
    a0 = C["approaches"][0]
    l0 = a0["leg"]
    p, t = leg_point(l0, l0["stop_s"] + 3.0, l0["W"] / 2 + 0.5)
    if on_land(p):
        prop("hydrant", p, yaw_of(t), "hydrant at the intersection corner")
    if C["core"] and C["ctrl"] == "signal":
        for a in C["approaches"][:2]:
            l = a["leg"]
            p, t = leg_point(l, l["stop_s"] + 2.0, l["W"] / 2 + 1.0)
            if on_land(p):
                prop("bin", p, yaw_of(t), "litter bin at a downtown corner")
        if C["unit"] % 3 == 0:
            p, t = leg_point(l0, l0["stop_s"] + 6.0, l0["W"] / 2 + 1.2)
            if on_land(p):
                prop("mailbox", p, yaw_of(t), "mailbox at a downtown corner")
    for l in C["legs"]:
        if l["xw"] and l["in_lanes"]:
            off = max(e[2] + e[1] / 2 for e in l["in_lanes"]) - 0.3
            p, t = leg_point(l, l.get("xw0", l["mouth"]) + XW + 2.0, off)
            prop("drain", p, yaw_of(t), "gutter inlet upstream of the crosswalk")
    named = []
    for l in C["legs"]:
        nm = l["d"]["name"]
        if nm and l["cls"] != "highway" and nm not in [x[0] for x in named]:
            named.append((nm, l))
    if len(named) >= 2:
        (na, la), (nb, lb) = named[0], named[1]
        p, t = leg_point(la, la["mouth"] - 0.5, la["W"] / 2 + 1.4)
        prop("namesign", p, yaw_of(la["dir"]), "street names at the corner", a=na, b=nb, yaw_b=yaw_of(lb["dir"]))
    # bus stop on the far side of a signalised arterial intersection
    if C["ctrl"] == "signal":
        for l in C["legs"]:
            if l["cls"] != "major" or l["d"]["oneway"] or not l["out_lanes"] or l["L"] - l["mouth"] < 60:
                continue
            nm = l["d"]["name"] or f"edge{id(l['d'])}"
            p, t = leg_point(l, l["mouth"] + XW + 14.0, -(l["W"] / 2 + 1.2))
            if any(math.dist(p, q) < 350 for q in busstop_by_street[nm]) or not on_land(p):
                continue
            busstop_by_street[nm].append(p)
            face = yaw_of((t[1], -t[0]))           # faces the road
            prop("busstop", p, face, "far-side bus stop on an arterial")
            q, _ = leg_point(l, l["mouth"] + XW + 18.0, -(l["W"] / 2 + 2.6))
            prop("shelter" if C["core"] else "bench", q, face, "waiting at the bus stop")
            q2, _ = leg_point(l, l["mouth"] + XW + 22.0, -(l["W"] / 2 + 1.0))
            prop("bin", q2, face, "litter bin at the bus stop")

# dumpsters behind buildings, on the side away from the nearest street, if nothing is in the way
road_seg = SegGrid(30.0)
for u, v, k, d in G.edges(keys=True, data=True):
    for a_, b_ in zip(d["geom"], d["geom"][1:]):
        road_seg.add(a_, b_, d["width"])


def dist_to_road(p, r=60.0):
    best = (r, None)
    for _, (a_, b_, w_) in road_seg.near(p, r):
        q, _, dd = closest_on_seg(p, a_, b_)
        dd -= w_ / 2
        if dd < best[0]:
            best = (dd, q)
    return best


def in_any_footprint(p, margin=0.5):
    for _, (a_, b_, bi) in fp_grid.near(p, 40.0):
        pass
    gx, gy = int(p[0] // 30), int(p[1] // 30)
    for bi in {fp_grid.segs[i][2] for u in range(gx - 2, gx + 3) for v in range(gy - 2, gy + 3) for i in fp_grid.g.get((u, v), ())}:
        if points_in_poly(np.array([p]), np.array(fp[bi]))[0]:
            return True
    return False


for bi, b in enumerate(BLD):
    if rnd(bi, "dump") > 0.35 or b.get("district") not in ("chicago_core", "chicago", "austin_dt", "austin_mid"):
        continue
    c = (b["x"], b["y"])
    dd, q = dist_to_road(c)
    if q is None:
        continue
    away = unit((c[0] - q[0], c[1] - q[1]))
    depth = max(b["w"], b["d"]) / 2 + 2.0
    p = (c[0] + away[0] * depth, c[1] + away[1] * depth)
    dp, _ = dist_to_road(p, 30.0)
    if dp < 8.0 or not on_land(p) or in_any_footprint(p):
        continue
    prop("dumpster", p, yaw_of((away[1], -away[0])), "service side of the building, away from the street")

stats.update({"prop_" + k_: v_ for k_, v_ in collections.Counter(x["t"] for x in PROPS).items()})
stats["barricades"] = len(BARRICADES)
stats["signs_total"] = len(SIGNS)


# ================================================================ 7. OUTPUT
def R2(ring):
    return [[round(p[0], 2), round(p[1], 2)] for p in ring]


edges_out = []
for u, v, k, d in G.edges(keys=True, data=True):
    rb = ribbon(d)
    edges_out.append({"cls": d["cls"], "class": d["section"]["class"], "name": d["name"], "city": d["city"], "pc": d["pc"], "rb": d["rb"], "core": d["core"],
                      "oneway": d["oneway"], "travel": d["travel"], "speed": d["speed"], "width": d["width"],
                      "elems": d["section"]["elems"], "sidewalk": d["section"]["sidewalk"], "parkway": d["section"]["parkway"],
                      "curb": d["section"].get("curb"), "gutter": d["section"].get("gutter"),
                      "why": d["section"]["why"], "geom": R2(d["geom"]), "s0": round(d["s0"], 2), "s1": round(d["s1"], 2),
                      "ribbon": R2(rb) if rb else None, "internal": d["internal"],
                      "ends": [G.nodes[u]["kind"], G.nodes[v]["kind"]]})
# sidewalk zone per edge (curb to back of walk) and the grass parkway strip inside it on non-downtown streets
walk_out, parkway_out = [], []
for u, v, k, d in G.edges(keys=True, data=True):
    sw = d["section"]["sidewalk"]
    if d["swallowed"] or sw <= 0:
        continue
    g = d["geom"]
    s_cum = cumlen(g)
    sub = sub_polyline(g, s_cum, max(0.0, d["s0"] - 0.5), min(s_cum[-1], d["s1"] + 0.5))
    if len(sub) < 2:
        continue
    W = d["width"]
    walk_out.append(R2(offset_polyline(sub, W / 2 + sw) + offset_polyline(sub, -W / 2 - sw)[::-1]))
    if d["section"]["parkway"] and d["s1"] - d["s0"] > 12:
        sub2 = sub_polyline(g, s_cum, d["s0"] + 4.0, d["s1"] - 4.0)
        if len(sub2) >= 2:
            for side in (1, -1):
                a_ = offset_polyline(sub2, side * (W / 2 + 0.15))
                b_ = offset_polyline(sub2, side * (W / 2 + 2.0))
                parkway_out.append(R2(a_ + b_[::-1]))
j_sw = []
for J in junctions:
    j_sw.append(max([l["d"]["section"]["sidewalk"] for l in J["legs"]] + [0.0]))
# park trees from the first street pass (OpenStreetMap park trees and the park fill) stay, except in the plazas round
# the landmarks: Cloud Gate stands in an open paved plaza, Buckingham Fountain in its open forecourt
_LM = {l["name"]: l["pos"] for l in PLAN.get("landmarks", [])}
CLEAR = [(_LM[n], r) for n, r in (("The Bean", 35.0), ("Buckingham Fountain", 60.0)) if n in _LM]
# the landmark agents publish the plazas and walks to keep clear (SourceArt/Landmarks/landmark_zones.json, zones whose
# "clear" lists "props"); when the file is there it replaces the two circles above, for street props and park trees alike
LM_ZONES = []
for _lz in (ROOT / "SourceArt/Landmarks/landmark_zones.json", ROOT / "SourceArt/Landmarks/capitol/capitol_zones.json"):
    LM_ZONES += [np.array(z["poly"], float) for z in (json.load(open(_lz)).get("zones", []) if _lz.exists() else [])
                 if "props" in z.get("clear", []) and len(z.get("poly", [])) >= 3]
# chicago-parks (20 Oct night, its request): every asset zone in SourceArt/Landmarks/parks/parks.json whose "clear" lists
# "props" (its "poly" and any "extra" polygons); austin-sights may publish the same format in SourceArt/Landmarks/austin/
for _pz in (ROOT / "SourceArt/Landmarks/parks/parks.json", ROOT / "SourceArt/Landmarks/austin/austin_sights.json"):
    if not _pz.exists():
        continue
    _assets = json.load(open(_pz)).get("assets", {})
    for _a in (_assets.values() if isinstance(_assets, dict) else _assets):
        _z = _a.get("zone") if isinstance(_a, dict) else None
        if not _z or "props" not in _z.get("clear", []):
            continue
        for _poly in [_z.get("poly", [])] + list(_z.get("extra", [])):
            if len(_poly) >= 3:
                LM_ZONES.append(np.array(_poly, float))
# willis-tower (20 Oct night): no street props inside its block (SourceArt/Landmarks/willis/willis.json zone_plan)
_wz = ROOT / "SourceArt/Landmarks/willis/willis.json"
if _wz.exists():
    _zp = json.load(open(_wz)).get("zone_plan") or []
    if len(_zp) >= 3:
        LM_ZONES.append(np.array(_zp, float))
if LM_ZONES:
    CLEAR = []


def in_lm_zone(p):
    q = np.array([p[:2]], float)
    return any(points_in_poly(q, z)[0] for z in LM_ZONES if z[:, 0].min() <= p[0] <= z[:, 0].max() and z[:, 1].min() <= p[1] <= z[:, 1].max())


for pr in SD["props"]:
    if pr["t"] == "tree" and pr.get("pit") == "park" and not any(math.dist(pr["p"], c) < r for c, r in CLEAR):
        PROPS.append({"t": "tree", "p": pr["p"], "yaw": pr["yaw"], "why": "park tree (OpenStreetMap / park planting)",
                      "pit": "park", "city": pr.get("city", "chicago"), "sp": pr.get("sp", "elm"), "scale": pr.get("scale", 1.0)})
# last check, for everything that stands up (manholes and storm drains belong in the road): off the pavement, on land
FLAT = {"manhole", "drain"}


def standing_ok(p):
    return (not in_road(p) and on_land(p) and not near_l(p, "posts", 0.5) and not in_polys(p, X_FP["posts"], 0.5)
            and not in_polys(p, X_FP["fill"]))


_n = len(PROPS)
PROPS[:] = [pr for pr in PROPS if not in_lm_zone(pr["p"])]
_m = len(SIGNS)
SIGNS[:] = [sg for sg in SIGNS if not in_lm_zone(sg["p"])]
stats["props_dropped_in_landmark_zones"] = (_n - len(PROPS)) + (_m - len(SIGNS))


TALL = {"tree": 3.5, "lamp": 1.0, "lamp_hw": 1.0, "shelter": 1.0, "namesign": 1.0}   # reach the L's girders (5.4 m): metres
_n = len(PROPS)                                                                     # kept clear of the deck (trees: canopy)
PROPS[:] = [pr for pr in PROPS if not (pr["t"] in TALL and (near_l(pr["p"], "deck", TALL[pr["t"]]) or in_polys(pr["p"], X_FP["deck"], TALL[pr["t"]])))]
stats["props_dropped_under_l"] = _n - len(PROPS)


_n = len(PROPS)
PROPS[:] = [pr for pr in PROPS if pr["t"] in FLAT or standing_ok(pr["p"])]
stats["props_dropped_on_road_or_water"] = _n - len(PROPS)
_n = len(SIGNS)
SIGNS[:] = [sg for sg in SIGNS if standing_ok(sg["p"])]
stats["signs_dropped_on_road_or_water"] = _n - len(SIGNS)
_n = len(SIG["peds"])
SIG["peds"] = [pd for pd in SIG["peds"] if standing_ok(pd["p"])]
stats["ped_heads_dropped_on_road_or_water"] = _n - len(SIG["peds"])
units_out = []
for C in CONTROL:
    units_out.append({"unit": C["unit"], "c": R2([C["c"]])[0], "ctrl": C["ctrl"], "why": C["why"], "legs": len(C["legs"]),
                      "streets": C["streets"], "ngroups": C["ngroups"], "phase": C["phase"], "core": C["core"],
                      "approaches": [{"group": a.get("group", 0), "stop": a["stop"], "moves": sorted(a["moves"]),
                                      "lanes": len(a.get("lanes", [])), "ltl": bool(a.get("ltl"))} for a in C["approaches"]]})
for sg in SIGNS:
    sg["p"] = [round(sg["p"][0], 2), round(sg["p"][1], 2)]
data = {
    "frame": "plan metres, x east, y north (Unreal X = y*100, Y = x*100)",
    "attribution": "(c) OpenStreetMap contributors (ODbL)",
    "edges": edges_out,
    "junctions": [{"ring": R2(J["ring"]), "c": R2([J["c"]])[0], "unit": J["unit"], "sw": j_sw[i]} for i, J in enumerate(junctions)],
    "walk": walk_out,
    "parkway": parkway_out,
    "joints": [R2(j) for j in joints if len(j) >= 3],
    "units": units_out,
    "markings": MK,
    "signals": SIG,
    "signs": SIGNS,
    "barricades": BARRICADES,
    "props": PROPS,
    "stats": dict(stats),
}
OUTP.parent.mkdir(parents=True, exist_ok=True)
json.dump(data, open(OUTP, "w"), separators=(",", ":"))
print("wrote", OUTP, round(OUTP.stat().st_size / 1e6, 1), "MB")

# ================================================================ 8. TRAFFIC
# The same network for the C++ traffic (Source/SkyCity/SkysterTraffic): cars on the streets and Cybercabs in the
# sky lanes above them follow it. One link per edge and travel direction, trimmed to the junction mouths, with its
# lanes' offsets to the right of the centreline (inner lane first), the speed for its class and how it arrives at
# the far end: through a signal (its unit's phase and this approach's group, the same numbers the signal heads'
# lenses run on, so cars and lights agree), a stop sign, or free.
SPEED = {"highway": 24.6, "major": 15.6, "mid": 13.4, "minor": 11.2}          # 55 / 35 / 30 / 25 mph
appr_at = {}
for C in CONTROL:
    for a in C["approaches"]:
        l = a["leg"]
        appr_at[(l["n"], l["m"], l["k"])] = (C, a)
links, used = [], set()
for u, v, k, d in G.edges(keys=True, data=True):
    g = d["geom"]
    s_cum = cumlen(g)
    # a street swallowed by its junctions (both mouths overlap: the links inside a compound junction, short pieces
    # next to a pass node) still carries traffic: its link runs node to node, or the network falls apart there
    sub = list(g) if d.get("swallowed") else sub_polyline(g, s_cum, d["s0"], d["s1"])
    if len(sub) < 2 or cumlen(sub)[-1] < 1.0:
        continue
    a_ = u if math.dist(g[0], G.nodes[u]["p"]) <= math.dist(g[-1], G.nodes[u]["p"]) else v
    b_ = v if a_ == u else u
    W = d["width"]
    x = W / 2
    lanes = {1: [], -1: []}
    for kind, w, dd in d["section"]["elems"]:
        c_left = x - w / 2
        x -= w
        if kind == "lane" and dd in (1, -1):
            lanes[dd].append(round(-c_left if dd == 1 else c_left, 2))
    for dd, (p_, q_) in ((1, (a_, b_)), (-1, (b_, a_))):
        if not lanes[dd]:
            continue
        pts = sub if dd == 1 else sub[::-1]
        simp = [pts[0]]
        for p in pts[1:-1]:
            if math.dist(p, simp[-1]) > 3.0:
                simp.append(p)
        simp.append(pts[-1])
        ca = appr_at.get((q_, p_, k))
        ctrl, unit_id, group = 0, -1, 0
        if ca:
            C, a = ca
            if C["ctrl"] == "signal":
                ctrl, unit_id, group = 1, C["unit"], a["group"]
            elif a["stop"]:
                ctrl = 2
        links.append({"a": p_, "b": q_, "p": R2(simp), "o": sorted(lanes[dd]), "v": 9.0 if d["rb"] else SPEED[d["cls"]], "c": ctrl, "u": unit_id,
                      "g": group, "hw": d["cls"] == "highway", "n": d["name"]})
        used.update((p_, q_))
traffic = {"frame": data["frame"], "attribution": data["attribution"], "group_time": 22.0,
           "nodes": {str(n): R2([G.nodes[n]["p"]])[0] for n in used},
           "units": {str(C["unit"]): [C["ngroups"], C["phase"]] for C in CONTROL if C["ctrl"] == "signal"},
           "links": links}
for out in ((ROOT / "Saved/Roads/wip/traffic.json",) if WIP else (ROOT / "Saved/Roads/traffic.json", ROOT / "Content/SkyCity/Data/traffic.json")):
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(traffic, open(out, "w"), separators=(",", ":"))
print("traffic:", len(links), "links,", sum(len(l["o"]) for l in links), "lanes,", sum(1 for l in links if l["c"] == 1), "signalised arrivals")

if "--debug" in sys.argv:
    sys.path.insert(0, str(ROOT / "Scripts" / "roads"))
    import debug_render as DR
    DR.render_all(data, OUTP.parent)
    print(json.dumps(stats, indent=0))
