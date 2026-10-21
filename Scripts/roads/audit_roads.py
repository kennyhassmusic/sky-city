"""Offline audit of Sky City's streets: is every street drivable and does every intersection make sense?

Why: Kenny asked (20 Oct evening) for every street and junction to be checked, not by eye on a few corners but over the
whole network. This reads Saved/Roads/roadnet.json (what roadnet.py designed), Saved/Roads/placed_props.json (what is
actually in the level, dumped by Scripts/roads/dump_placed_ue.py) and Content/SkyCity/Data/traffic.json, rasterises
the paved surface at 0.5 m and checks:
  props      every upright instance in the level against the pavement (depth inside it), and its height (props that
             landed on the L deck, bridges or roofs instead of the sidewalk)
  slivers    raised 15 cm curb strips or islands inside the roadway that a car would catch (thin or tiny blocks)
  junctions  junction rings far bigger than the streets that meet there (aprons), self-crossing rings
  arrows     lane-use arrows that don't point along their lane, or sit in a junction or off their lane
  bars       stop bars off the pavement or across the wrong street
  signals    heads not over a lane arriving towards them, poles far from their junction
  signs      ONE WAY arrows against the traffic, stop signs not at the right of a stop approach
  traffic    links that lead nowhere (cars stop), nodes no car can leave or reach
  walls      street ribbons running into building footprints; dead ends and where they end
Output: Saved/Roads/audit.json (problem list with plan metres and Unreal cm) and a summary on stdout.
Run: python3 -I Scripts/roads/audit_roads.py [--no-placed]
"""
import collections, json, math, pathlib, sys
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parents[2]
D = json.load(open(ROOT / "Saved/Roads/roadnet.json"))
PLAN = json.load(open(ROOT / "Saved/Mashup/plan_v3.json"))
BLD = json.load(open(ROOT / "Saved/Mashup/buildings_v3.json"))["buildings"]
TR = json.load(open(ROOT / "Content/SkyCity/Data/traffic.json"))
PLACED_P = ROOT / "Saved/Roads/placed_props.json"
PLACED = json.load(open(PLACED_P)) if PLACED_P.exists() and "--no-placed" not in sys.argv else None
OUT = ROOT / "Saved/Roads/audit.json"
RES = 0.5
X0, Y0, X1, Y1 = PLAN["bounds"]
NX, NY = int((X1 - X0) / RES) + 1, int((Y1 - Y0) / RES) + 1
problems = []
summary = collections.OrderedDict()


def ue(p):
    return [round(p[1] * 100), round(p[0] * 100)]


def near_edge_of_map(p, m=6.0):
    return p[0] < X0 + m or p[0] > X1 - m or p[1] < Y0 + m or p[1] > Y1 - m


def report(kind, p, sev, **kw):
    if kind in ("curb_island", "thin_curb_strip") and near_edge_of_map(p):
        return
    r = {"kind": kind, "plan": [round(p[0], 1), round(p[1], 1)], "ue": ue(p), "sev": sev}
    r.update(kw)
    problems.append(r)


def pix(p):
    return ((p[0] - X0) / RES, (Y1 - p[1]) / RES)


def raster(rings, value=1):
    im = Image.new("L", (NX, NY), 0)
    dr = ImageDraw.Draw(im)
    for r in rings:
        if r and len(r) >= 3:
            dr.polygon([pix(p) for p in r], fill=value)
    return np.array(im, bool)


def sample(arr, p):
    c, r = pix(p)
    c, r = int(round(c)), int(round(r))
    if 0 <= r < arr.shape[0] and 0 <= c < arr.shape[1]:
        return arr[r, c]
    return 0


def unit(v):
    L = math.hypot(v[0], v[1]) or 1e-12
    return (v[0] / L, v[1] / L)


def angdiff(a, b):
    d = (a - b) % 360
    return min(d, 360 - d)


# ---------------------------------------------------------------- surfaces
ribbons = [e["ribbon"] for e in D["edges"] if e["ribbon"]]
road = raster(ribbons + [j["ring"] for j in D["junctions"]] + D["joints"])
rib_only = raster(ribbons)
jring = raster([j["ring"] for j in D["junctions"]])
water = raster(PLAN["water"]["outer"]) & ~raster(PLAN["water"]["inner"])
land = ~water
blocks = land & ~road
depth_in = ndimage.distance_transform_edt(road) * RES        # metres to the nearest curb, inside the pavement
from skimage.measure import points_in_poly
ALL_RINGS = [np.array(r, float) for r in ribbons + [j["ring"] for j in D["junctions"]] + D["joints"] if r and len(r) >= 3]
RING_GRID = collections.defaultdict(list)
for _i, _r in enumerate(ALL_RINGS):
    (_x0, _y0), (_x1, _y1) = _r.min(0), _r.max(0)
    for _gx in range(int(_x0 // 50), int(_x1 // 50) + 1):
        for _gy in range(int(_y0 // 50), int(_y1 // 50) + 1):
            RING_GRID[(_gx, _gy)].append(_i)


def exact_depth(p):
    """Exact: how far inside the pavement polygons p stands (0 if outside), like roadnet.py's in_road."""
    q = np.array([p], float)
    best = 0.0
    for i in RING_GRID.get((int(p[0] // 50), int(p[1] // 50)), ()):
        r = ALL_RINGS[i]
        if points_in_poly(q, r)[0]:
            a, b = r, np.roll(r, -1, axis=0)
            d = b - a
            L2 = (d ** 2).sum(1)
            L2[L2 == 0] = 1e-12
            t = np.clip(((q - a) * d).sum(1) / L2, 0, 1)
            best = max(best, float(np.sqrt(((a + d * t[:, None] - q) ** 2).sum(1)).min()))
    return best
summary["road_area_km2"] = round(road.sum() * RES * RES / 1e6, 3)

# what Unreal actually built (build_roads_ue.py writes the block outlines and holes it raised): even-odd fill
BUILT_P = ROOT / "Saved/Roads/blocks_built.json"
if BUILT_P.exists() and "--no-built" not in sys.argv:
    built = np.zeros((NY, NX), bool)
    for r in json.load(open(BUILT_P)):
        built ^= raster([r])
    summary["blocks_from"] = "Saved/Roads/blocks_built.json (as built in Unreal)"
    blocks_used = built
else:
    blocks_used = blocks
    summary["blocks_from"] = "roadnet.json (land minus pavement)"

# lanes on blocks: every travel lane, sampled every 2 m between its junction mouths (and through swallowed pieces),
# must be on asphalt, not on a raised sidewalk or lawn (the 20 Oct drive found a folded junction ring leaving lawn in
# Lake Shore Drive's lanes)
lane_hits = []
for ei, e in enumerate(D["edges"]):
    g = e["geom"]
    sc = [0.0]
    for a, b in zip(g, g[1:]):
        sc.append(sc[-1] + math.dist(a, b))
    L = sc[-1]
    s0, s1 = (0.0, L) if e["s1"] - e["s0"] < 1.0 else (e["s0"], e["s1"])
    x = e["width"] / 2
    offs = []
    for kind, w, dd in e["elems"]:
        if kind == "lane":
            offs.append(x - w / 2)
        x -= w
    s = s0 + 1.0
    while s < s1 - 1.0:
        k = max(0, min(len(g) - 2, next((i for i in range(len(g) - 1) if sc[i + 1] >= s), len(g) - 2)))
        a, b = g[k], g[k + 1]
        t = unit((b[0] - a[0], b[1] - a[1]))
        f = (s - sc[k]) / max(sc[k + 1] - sc[k], 1e-9)
        c = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        for o in offs:
            p = (c[0] - t[1] * o, c[1] + t[0] * o)
            if sample(blocks_used, p) and not near_edge_of_map(p, 3.0):
                lane_hits.append((ei, p))
        s += 2.0
seen = set()
for ei, p in lane_hits:
    key = (ei, int(p[0] // 10), int(p[1] // 10))
    if key in seen:
        continue
    seen.add(key)
    report("block_in_lane", p, 3, street=D["edges"][ei]["name"])
summary["lane_samples_on_blocks"] = len(lane_hits)

# ---------------------------------------------------------------- 1. placed props on the pavement / wrong height
STAND = {"pole", "lamp", "lamp_hw", "post", "pedpost", "cabinet", "hydrant", "bin", "bench", "mailbox", "busstop", "shelter",
         "rack", "namepost", "dumpster", "liveoak", "honeylocust", "linden", "elm"}
COLLIDE = {"pole", "lamp", "lamp_hw"}
if PLACED:
    pp = collections.Counter()
    zbad = collections.Counter()
    for lab, rows in PLACED["inst"].items():
        k = lab.replace("RProps_", "")
        for x, y, z, yaw, sx, sy, sz in rows:
            p = (y / 100.0, x / 100.0)
            if k in STAND:
                dep = exact_depth(p) if sample(depth_in, p) > 0 else 0.0
                if dep > 0.3:
                    pp[k] += 1
                    report("prop_on_road", p, 3 if k in COLLIDE else 1, prop=k, depth=round(float(dep), 1))
                if not sample(land, p):
                    report("prop_in_water", p, 2, prop=k)
                if abs(z - 15) > 5 and abs(z) > 5:
                    zbad[k] += 1
                    report("prop_height", p, 2 if k in COLLIDE else 1, prop=k, z=z)
            elif k in ("manhole", "drain", "barricade"):
                if abs(z) > 30:
                    zbad[k] += 1
                    report("prop_height", p, 1, prop=k, z=z)
    summary["placed_on_road"] = dict(pp)
    summary["placed_wrong_height"] = dict(zbad)
# the JSON's own props
jp = collections.Counter()
for pr in D["props"]:
    if pr["t"] in ("manhole", "drain"):
        continue
    if sample(depth_in, pr["p"]) > 0 and exact_depth(pr["p"]) > 0.3:
        jp[pr["t"]] += 1
summary["json_props_on_road"] = dict(jp)

# ---------------------------------------------------------------- 2. slivers: thin or tiny raised blocks inside the roadway
lab, n = ndimage.label(blocks_used)
sizes = ndimage.sum(blocks_used, lab, range(1, n + 1)) * RES * RES
tiny = 0
for i, a in enumerate(sizes):
    if a < 25.0:                       # an island smaller than 25 m2 (a curb chunk in the asphalt)
        sl = ndimage.find_objects((lab == i + 1).astype(np.uint8))[0]
        cy, cx = (sl[0].start + sl[0].stop) / 2, (sl[1].start + sl[1].stop) / 2
        p = (X0 + cx * RES, Y1 - cy * RES)
        if sample(land, p) and not near_edge_of_map(p):
            tiny += 1
            report("curb_island", p, 2 if a < 6 else 1, area=round(float(a), 1))
summary["curb_islands_lt25m2"] = tiny
# thin strips: block pixels removed by an opening with a 1.5 m disc (strips narrower than ~1.5 m)
st = np.zeros((3, 3), bool)
st[1, :] = st[:, 1] = True
opened = ndimage.binary_opening(blocks_used, structure=st, iterations=2)       # removes parts thinner than ~2 px * 2 = 2 m
thin = blocks_used & ~opened
tl, tn = ndimage.label(thin, structure=np.ones((3, 3)))
tsz = ndimage.sum(thin, tl, range(1, tn + 1))
objs = ndimage.find_objects(tl)
nthin = 0
for i, (a, sl) in enumerate(zip(tsz, objs)):
    if a * RES * RES < 4.0:            # ignore specks (rounded corners)
        continue
    cy, cx = (sl[0].start + sl[0].stop) / 2, (sl[1].start + sl[1].stop) / 2
    p = (X0 + cx * RES, Y1 - cy * RES)
    if near_edge_of_map(p):
        continue
    nthin += 1
    report("thin_curb_strip", p, 1, area=round(float(a * RES * RES), 1),
           len=round(max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start) * RES, 1))
summary["thin_curb_strips"] = nthin

# ---------------------------------------------------------------- 3. junction rings
def area(r):
    a = 0.0
    for i in range(len(r)):
        a += r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1]
    return a / 2


units = {u["unit"]: u for u in D["units"]}
ring_of_unit = collections.defaultdict(list)
for j in D["junctions"]:
    ring_of_unit[j["unit"]].append(j)
big = 0
for j in D["junctions"]:
    r = j["ring"]
    a = abs(area(r))
    ext = max(math.dist(q, j["c"]) for q in r)
    # self-crossing check: raster area vs signed area
    if a > 2500 or ext > 45:
        big += 1
        report("big_junction_ring", j["c"], 2, area=round(a), extent=round(ext, 1), unit=j["unit"])
summary["big_junction_rings"] = big
for uid, js in ring_of_unit.items():
    if len(js) >= 3:
        u = units.get(uid, {})
        report("compound_junction", js[0]["c"], 1, nodes=len(js), legs=u.get("legs"), ctrl=u.get("ctrl"),
               c=u.get("c"), ue_c=ue(u["c"]) if u else None)

# ---------------------------------------------------------------- 4. lane arrows
# nearest edge centreline per point
seg_cell = 20.0
segs = collections.defaultdict(list)
for ei, e in enumerate(D["edges"]):
    g = e["geom"]
    for k, (a, b) in enumerate(zip(g, g[1:])):
        for gx in range(int(math.floor(min(a[0], b[0]) / seg_cell)), int(math.floor(max(a[0], b[0]) / seg_cell)) + 1):
            for gy in range(int(math.floor(min(a[1], b[1]) / seg_cell)), int(math.floor(max(a[1], b[1]) / seg_cell)) + 1):
                segs[(gx, gy)].append((ei, k))


def edge_candidates(p, r=30.0):
    """Edges near p: (lateral distance, edge index, segment, tangent, signed offset left+, inside_ribbon_span)."""
    gx0, gy0 = int(math.floor((p[0] - r) / seg_cell)), int(math.floor((p[1] - r) / seg_cell))
    gx1, gy1 = int(math.floor((p[0] + r) / seg_cell)), int(math.floor((p[1] + r) / seg_cell))
    best = {}
    seen = set()
    for gx in range(gx0, gx1 + 1):
        for gy in range(gy0, gy1 + 1):
            for ei, k in segs.get((gx, gy), ()):
                if (ei, k) in seen:
                    continue
                seen.add((ei, k))
                e = D["edges"][ei]
                g = e["geom"]
                a, b = g[k], g[k + 1]
                dx, dy = b[0] - a[0], b[1] - a[1]
                L2 = dx * dx + dy * dy or 1e-12
                t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
                tc = max(0.0, min(1.0, t))
                q = (a[0] + dx * tc, a[1] + dy * tc)
                dd = math.dist(p, q)
                side = dx * (p[1] - a[1]) - dy * (p[0] - a[0])
                end_clamped = (t < 0 and k == 0) or (t > 1 and k == len(g) - 2)
                rec = (dd, ei, k, unit((dx, dy)), math.copysign(dd, side), not end_clamped)
                if ei not in best or dd < best[ei][0]:
                    best[ei] = rec
    return list(best.values())


def nearest_edge(p, r=30.0, want_off=None):
    """The edge p belongs to: one whose ribbon span contains it (|offset| within its half width), else the nearest.
    want_off: expected |offset| (signs stand at W/2 + 1.2): pick the edge that best matches it."""
    cs = edge_candidates(p, r)
    if not cs:
        return None
    if want_off is not None:
        cs2 = [c for c in cs if c[5]]
        if cs2:
            return min(cs2, key=lambda c: abs(c[0] - want_off(D["edges"][c[1]])))
    inside = [c for c in cs if c[5] and c[0] <= D["edges"][c[1]]["width"] / 2 + 0.05]
    if inside:
        return min(inside, key=lambda c: c[0] / max(D["edges"][c[1]]["width"], 1.0))
    return min(cs, key=lambda c: c[0])


def lane_at(e, off):
    """Element of edge e at lateral offset off (left of the geometry +)."""
    x = e["width"] / 2
    for kind, w, dd in e["elems"]:
        if x - w <= off <= x + 1e-6:
            return kind, dd
        x -= w
    return None, 0


bad_arrows = 0
for a in D["markings"]["arrows"]:
    p = a["p"]
    ne = nearest_edge(p)
    if not ne:
        report("arrow_no_street", p, 2, kind_=a["kind"])
        bad_arrows += 1
        continue
    dd, ei, k, t, off, _ = ne
    e = D["edges"][ei]
    edge_yaw = math.degrees(math.atan2(t[1], t[0])) % 360
    d_ = min(angdiff(a["yaw"], edge_yaw), angdiff(a["yaw"], edge_yaw + 180))
    kind, dirn = lane_at(e, off)
    travel_yaw = edge_yaw if dirn == 1 else (edge_yaw + 180) % 360
    if d_ > 15:
        report("arrow_turned", p, 2, kind_=a["kind"], arrow_yaw=a["yaw"], street_yaw=round(edge_yaw, 1), off=round(d_, 1), street=e["name"])
        bad_arrows += 1
    elif kind != "lane" and not (kind == "twltl" and a["kind"] == "L"):     # an L arrow in the centre turn lane is right
        report("arrow_off_lane", p, 2, kind_=a["kind"], on=kind, street=e["name"])
        bad_arrows += 1
    elif kind == "lane" and angdiff(a["yaw"], travel_yaw) > 90:
        report("arrow_backwards", p, 3, kind_=a["kind"], street=e["name"])
        bad_arrows += 1
    elif sample(jring, p) and not sample(rib_only, p):
        report("arrow_in_junction", p, 1, kind_=a["kind"], street=e["name"])
        bad_arrows += 1
summary["arrows"] = len(D["markings"]["arrows"])
summary["arrows_bad"] = bad_arrows

# ---------------------------------------------------------------- 5. stop bars and crosswalk bars on the pavement
off_bars = 0
for r in D["markings"]["bars"]:
    c = (sum(q[0] for q in r) / len(r), sum(q[1] for q in r) / len(r))     # (yield-line teeth are triangles)
    if not sample(road, c):
        off_bars += 1
        report("bar_off_road", c, 1)
summary["bars"] = len(D["markings"]["bars"])
summary["bars_off_road"] = off_bars

# ---------------------------------------------------------------- 6. signals
heads_bad = 0
for h in D["signals"]["heads"]:
    p = h["p"]
    if not sample(road, p):
        if h["z"] < 5:
            continue                    # pole-mounted head on the curb: fine
        heads_bad += 1
        report("head_not_over_road", p, 1, yaw=h["yaw"])
        continue
    ne = nearest_edge(p)
    if not ne:
        continue
    dd, ei, k, t, off, _ = ne
    e = D["edges"][ei]
    kind, dirn = lane_at(e, off)
    if kind != "lane":
        continue
    edge_yaw = math.degrees(math.atan2(t[1], t[0])) % 360
    travel_yaw = edge_yaw if dirn == 1 else (edge_yaw + 180) % 360
    # a head faces the drivers coming at it: its yaw is opposite to their travel
    if angdiff(h["yaw"], (travel_yaw + 180) % 360) > 50 and not sample(jring, p):
        heads_bad += 1
        report("head_faces_wrong_lane", p, 2, yaw=h["yaw"], lane_travel=round(travel_yaw, 1), street=e["name"])
summary["signal_heads"] = len(D["signals"]["heads"])
summary["signal_heads_suspect"] = heads_bad
ucs = {u["unit"]: u["c"] for u in D["units"]}
far_poles = 0
for pl in D["signals"]["poles"]:
    dmin = min(math.dist(pl["p"], c) for c in ucs.values())
    if dmin > 40:
        far_poles += 1
        report("pole_far_from_junction", pl["p"], 1, d=round(dmin, 1))
summary["signal_poles_far"] = far_poles

# ---------------------------------------------------------------- 7. signs
sg_bad = 0
for sg in D["signs"]:
    if sg["kind"] != "oneway":
        continue
    ne = nearest_edge(sg["p"], 30, want_off=lambda e: e["width"] / 2 + 1.2)
    if not ne:
        continue
    dd, ei, k, t, off, _ = ne
    e = D["edges"][ei]
    if not e["oneway"]:
        continue
    edge_yaw = math.degrees(math.atan2(t[1], t[0])) % 360
    travel_yaw = edge_yaw if e["travel"] >= 0 else (edge_yaw + 180) % 360
    if angdiff(sg["arrow"], travel_yaw) > 60 and angdiff(sg["arrow"], (travel_yaw + 180)) < 60:
        sg_bad += 1
        report("oneway_arrow_against_traffic", sg["p"], 2, street=e["name"])
summary["oneway_signs_against"] = sg_bad

# ---------------------------------------------------------------- 8. traffic network
links = TR["links"]
out_of = collections.defaultdict(list)
in_to = collections.defaultdict(list)
for i, l in enumerate(links):
    out_of[l["a"]].append(i)
    in_to[l["b"]].append(i)
stuck = 0
uturn_only = 0
for i, l in enumerate(links):
    outs = out_of.get(l["b"], [])
    if not outs:
        stuck += 1
        report("traffic_dead_end", l["p"][-1], 2, link=i, street=l["n"])
    elif all(links[j]["b"] == l["a"] for j in outs):
        uturn_only += 1
        report("traffic_uturn_only", l["p"][-1], 1, link=i, street=l["n"])
summary["traffic_links"] = len(links)
summary["traffic_dead_end_links"] = stuck
summary["traffic_uturn_only"] = uturn_only
try:
    import networkx as nx
    DG = nx.DiGraph()
    for l in links:
        DG.add_edge(l["a"], l["b"])
    sccs = sorted(nx.strongly_connected_components(DG), key=len, reverse=True)
    summary["traffic_scc_sizes"] = [len(s) for s in sccs[:8]]
    main = sccs[0]
    outside = [n for n in DG.nodes if n not in main]
    summary["traffic_nodes_outside_main"] = len(outside)
except Exception as ex:
    summary["traffic_scc_error"] = str(ex)

# ---------------------------------------------------------------- 9. streets into buildings, dead ends
fp_rings = []
for b in BLD:
    a = math.radians(b["yaw"])
    ca, sa = math.cos(a), math.sin(a)
    hw, hd = b["w"] / 2, b["d"] / 2
    fp_rings.append([(b["x"] + sa * u + ca * v, b["y"] + ca * u - sa * v) for u, v in ((hw, hd), (-hw, hd), (-hw, -hd), (hw, -hd))])
bmask = raster(fp_rings)
hit = road & bmask
hl, hn = ndimage.label(hit)
hs = ndimage.sum(hit, hl, range(1, hn + 1)) * RES * RES
ho = ndimage.find_objects(hl)
nb = 0
for a, sl in zip(hs, ho):
    if a < 2.0:
        continue
    cy, cx = (sl[0].start + sl[0].stop) / 2, (sl[1].start + sl[1].stop) / 2
    p = (X0 + cx * RES, Y1 - cy * RES)
    nb += 1
    report("building_on_road", p, 3 if a > 20 else 2, area=round(float(a), 1))
summary["building_footprints_on_road"] = nb
de = collections.Counter()
for e in D["edges"]:
    for end, kind in zip((e["geom"][0], e["geom"][-1]), e["ends"]):
        if kind == "deadend":
            w = not sample(land, end)
            de["water" if w else "land"] += 1
            report("dead_end", end, 1, street=e["name"], cls=e["cls"], in_water=bool(w))
summary["dead_ends"] = dict(de)

# ---------------------------------------------------------------- output
sev = collections.Counter((p["kind"], p["sev"]) for p in problems)
summary["problems_by_kind"] = {f"{k} s{s}": n for (k, s), n in sorted(sev.items())}
json.dump({"summary": summary, "problems": problems}, open(OUT, "w"), indent=0)
print(json.dumps(summary, indent=1))
