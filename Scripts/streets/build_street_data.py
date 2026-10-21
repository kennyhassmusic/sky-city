"""Street-level data for Sky City, in the plan frame (metres, x east, y north; Unreal X = y*100, Y = x*100).

Inputs: Saved/Mashup/plan_v3.json (the city's roads, water, parks, rail), SourceArt/osm/<city>.json (road tags),
SourceArt/osm/<city>_street.json (lamps, trees, crossings, signals, alleys, ...), Saved/Mashup/buildings_v3.json.
Each OSM feature goes through the same projection and layout transform as the plan (Chicago as-is, Austin rotated
and shifted), and is kept only where its own city survived the mashup.

Output: Saved/Streets/street_data.json
  roads         every plan road with real lanes / one-way / speed from OSM, a curb-to-curb width, and flags
                (skip = a lower level like Lower Wacker, parkway = grass strip between kerb and sidewalk)
  nodes         intersections (clustered), with signal / stop flags
  markings      solid and dashed lane lines (polylines), crosswalk and stop bars (rectangles)
  props         lamps, trees, signals, stop / name / speed signs, hydrants, bins, benches, racks, dumpsters, ...
  areas, paths  grass, gravel, parking lots, plazas, alleys and park paths
Data (c) OpenStreetMap contributors, ODbL.

Run: python3 -I Scripts/streets/build_street_data.py
"""
import collections, json, math, pathlib, sys, zlib
import numpy as np
from skimage.measure import points_in_poly

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Scripts" / "mashup"))
import integrate_v2 as IV  # noqa: E402  (the mashup's layout frame: same transform and seam)

PLAN = json.load(open(ROOT / "Saved/Mashup/plan_v3.json"))
BLD = json.load(open(ROOT / "Saved/Mashup/buildings_v3.json"))["buildings"]
OUT = ROOT / "Saved/Streets/street_data.json"
F = IV.Frame(PLAN["layout"])
ORIGIN = {"chicago": (41.88756, -87.6278), "austin": (30.261444, -97.7451)}
ROAD_CLASS = {"motorway": "highway", "trunk": "highway", "motorway_link": "highway", "trunk_link": "highway",
              "primary": "major", "secondary": "major", "primary_link": "major", "secondary_link": "major",
              "tertiary": "mid", "tertiary_link": "mid", "residential": "minor", "unclassified": "minor",
              "living_street": "minor", "pedestrian": "ped"}
DRIVE = ("highway", "major", "mid", "minor")
stats = collections.Counter()


def h32(*a):
    return zlib.crc32(repr(a).encode()) & 0xffffffff


def rnd(*a):
    return h32(*a) / 4294967296.0


# ---------------------------------------------------------------- projection into the plan frame
class Proj:
    def __init__(self, city):
        self.lat0, self.lon0 = ORIGIN[city]
        self.kx = 111320.0 * math.cos(math.radians(self.lat0))
        self.ky = 110574.0
        self.tf = F.tf(city)

    def __call__(self, lat, lon):
        return self.tf((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)


PROJ = {c: Proj(c) for c in ORIGIN}
x0, y0, x1, y1 = PLAN["bounds"]


def inbox(p, pad=0.0):
    return x0 + pad <= p[0] <= x1 - pad and y0 + pad <= p[1] <= y1 - pad


def side_ok(city, p, need=4.0):
    return F.sgn[city] * F.csd(p) >= need


# land mask: water outer rings minus islands, beaches count as not-street
def make_ring_tester(rings):
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


in_water_outer = make_ring_tester(PLAN["water"]["outer"])
in_island = make_ring_tester(PLAN["water"]["inner"])
in_beach = make_ring_tester(PLAN.get("beaches", []))
in_park = make_ring_tester(PLAN["parks"])


def on_land(pts):
    pts = np.asarray(pts, float).reshape(-1, 2)
    return ~in_water_outer(pts) | in_island(pts)


# ---------------------------------------------------------------- segment grid for nearest-road queries
class SegGrid:
    def __init__(self, cell=30.0):
        self.cell, self.g, self.segs = cell, collections.defaultdict(list), []

    def add(self, a, b, payload):
        i = len(self.segs)
        self.segs.append((a, b, payload))
        c = self.cell
        for gx in range(int(math.floor(min(a[0], b[0]) / c)), int(math.floor(max(a[0], b[0]) / c)) + 1):
            for gy in range(int(math.floor(min(a[1], b[1]) / c)), int(math.floor(max(a[1], b[1]) / c)) + 1):
                self.g[(gx, gy)].append(i)

    def near(self, p, r):
        c = self.cell
        seen = set()
        for gx in range(int(math.floor((p[0] - r) / c)), int(math.floor((p[0] + r) / c)) + 1):
            for gy in range(int(math.floor((p[1] - r) / c)), int(math.floor((p[1] + r) / c)) + 1):
                for i in self.g.get((gx, gy), ()):
                    if i not in seen:
                        seen.add(i)
                        yield self.segs[i]


def closest_on_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy or 1e-12
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    q = (a[0] + dx * t, a[1] + dy * t)
    return q, t, math.dist(p, q)


def cumlen(pts):
    s = [0.0]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + math.dist(a, b))
    return s


def unit(v):
    L = math.hypot(*v) or 1e-12
    return (v[0] / L, v[1] / L)


def at_s(pts, s_cum, s):
    """Point and unit tangent at arc length s."""
    s = max(0.0, min(s_cum[-1], s))
    i = max(0, min(len(pts) - 2, int(np.searchsorted(s_cum, s, side="right")) - 1))
    a, b = pts[i], pts[i + 1]
    seg = (s_cum[i + 1] - s_cum[i]) or 1e-9
    t = (s - s_cum[i]) / seg
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), unit((b[0] - a[0], b[1] - a[1]))


def offset_polyline(pts, off):
    """Offset to the left by off (negative = right), mitred."""
    n = len(pts)
    res = []
    for i in range(n):
        a = pts[max(0, i - 1)]
        b = pts[min(n - 1, i + 1)]
        if i == 0:
            a, b = pts[0], pts[1]
        if i == n - 1:
            a, b = pts[-2], pts[-1]
        t = unit((b[0] - a[0], b[1] - a[1]))
        nrm = (-t[1], t[0])
        if 0 < i < n - 1:
            t1 = unit((pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
            t2 = unit((pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]))
            n1, n2 = (-t1[1], t1[0]), (-t2[1], t2[0])
            m = unit((n1[0] + n2[0], n1[1] + n2[1]))
            k = max(0.5, m[0] * n1[0] + m[1] * n1[1])
            nrm = (m[0] / k, m[1] / k)
        res.append((pts[i][0] + nrm[0] * off, pts[i][1] + nrm[1] * off))
    return res


def sub_polyline(pts, s_cum, s0, s1):
    if s1 - s0 < 0.05:
        return []
    out = [at_s(pts, s_cum, s0)[0]]
    for p, s in zip(pts, s_cum):
        if s0 < s < s1:
            out.append(p)
    out.append(at_s(pts, s_cum, s1)[0])
    return out


# ---------------------------------------------------------------- 1. OSM roads with tags
osm_roads = SegGrid(25.0)
osm_way_tags = []
for city in ORIGIN:
    pr = PROJ[city]
    for el in json.load(open(ROOT / f"SourceArt/osm/{city}.json"))["elements"]:
        t = el.get("tags", {})
        if el["type"] != "way" or t.get("highway") not in ROAD_CLASS:
            continue
        wi = len(osm_way_tags)
        osm_way_tags.append((city, t))
        run = []
        for g in el.get("geometry") or []:
            if g is None:
                run = []
                continue
            p = pr(g["lat"], g["lon"])
            if run:
                osm_roads.add(run[-1], p, wi)
            run.append(p)


def parse_int(v, default=None):
    try:
        return int(str(v).split(";")[0].strip())
    except ValueError:
        return default


def parse_speed(v):
    if not v:
        return None
    v = str(v).lower()
    n = parse_int(v.replace("mph", "").strip())
    if n is None:
        return None
    return n if "mph" in v or n <= 75 else round(n / 1.609)


# ---------------------------------------------------------------- 2. plan roads, matched and measured
district_grid = collections.defaultdict(list)
for b in BLD:
    district_grid[(int(b["x"] // 100), int(b["y"] // 100))].append(b)


def district_at(p, city):
    votes = collections.Counter()
    gx, gy = int(p[0] // 100), int(p[1] // 100)
    for i in range(gx - 1, gx + 2):
        for j in range(gy - 1, gy + 2):
            for b in district_grid.get((i, j), ()):
                if math.dist((b["x"], b["y"]), p) < 140:
                    votes[b["district"]] += 1
    if votes:
        return votes.most_common(1)[0][0]
    return "chicago" if city == "chicago" else "austin_low"


roads = []
for ri, r in enumerate(PLAN["roads"]):
    pts = [tuple(p) for p in r["pts"]]
    if len(pts) < 2 or cumlen(pts)[-1] < 1.0:
        continue
    city = r["city"] if r["city"] in ORIGIN else ("chicago" if side_ok("chicago", pts[len(pts) // 2], 0) else "austin")
    s_cum = cumlen(pts)
    votes = collections.Counter()
    for k in range(int(s_cum[-1] // 10) + 1):
        p, _ = at_s(pts, s_cum, k * 10.0)
        best = None
        for a, b, wi in osm_roads.near(p, 9.0):
            wc, wt = osm_way_tags[wi]
            if wc != city:
                continue
            _, _, d = closest_on_seg(p, a, b)
            same = r["name"] and wt.get("name") == r["name"]
            score = d - (4.0 if same else 0.0) + (3.0 if wt.get("layer", "0").startswith("-") or wt.get("tunnel") in ("yes", "building_passage") else 0.0)
            if d < (9.0 if same else 5.0) and (best is None or score < best[0]):
                best = (score, wi)
        if best:
            votes[best[1]] += 1
    tags = {}
    under = False
    if votes:
        wi = votes.most_common(1)[0][0]
        tags = osm_way_tags[wi][1]
        under = tags.get("layer", "0").startswith("-") or tags.get("tunnel") in ("yes", "building_passage")
    cls = r["cls"]
    oneway = tags.get("oneway") in ("yes", "1", "true", "-1")
    reverse = tags.get("oneway") == "-1"
    if cls == "highway" and not tags.get("oneway") and "Lake Shore" in r["name"]:
        oneway = True
    lanes = parse_int(tags.get("lanes"))
    if not lanes:
        lanes = {"highway": 3 if oneway else 6, "major": 3 if oneway else 4, "mid": 2, "minor": 1 if oneway else 2, "ped": 1}[cls]
    lanes = max(1, min(lanes, 8))
    lane_w = {"highway": 3.6, "major": 3.3, "mid": 3.2, "minor": 3.0, "ped": 3.0}[cls]
    extra = {"highway": 2.4, "major": 2.4, "mid": 4.8, "minor": 4.6, "ped": 0.0}[cls]   # shoulders / parking lanes
    if cls == "minor" and oneway:
        extra = 4.0
    width = parse_int(tags.get("width")) or round(lanes * lane_w + extra, 1)
    mid = at_s(pts, s_cum, s_cum[-1] / 2)[0]
    dist = district_at(mid, city)
    core = dist in ("chicago_core", "austin_dt")
    speed = parse_speed(tags.get("maxspeed")) or (
        (40 if "Lake Shore" in r["name"] else 30) if city == "chicago" else {"highway": 55, "major": 35, "mid": 30, "minor": 25, "ped": 15}[cls])
    skip = under or "Lower " in r["name"]
    roads.append({"i": len(roads), "plan_i": ri, "cls": cls, "name": r["name"], "city": city, "pts": pts, "lanes": lanes, "lane_w": lane_w,
                  "oneway": oneway, "reverse": reverse, "width": width, "speed": speed, "district": dist, "core": core,
                  "skip": skip, "parkway": (not core) and cls in ("minor", "mid") and not skip,
                  "elevated": bool(r.get("elevated")), "matched": bool(votes)})
    stats["roads"] += 1
    stats["roads_matched"] += bool(votes)
    stats["roads_skipped_lower"] += skip

drive = [r for r in roads if r["cls"] in DRIVE and not r["skip"] and not r["elevated"]]
for r in drive:
    r["s"] = cumlen(r["pts"])
road_grid = SegGrid(30.0)
for r in drive:
    for k, (a, b) in enumerate(zip(r["pts"], r["pts"][1:])):
        road_grid.add(a, b, (r["i"], k))
R = {r["i"]: r for r in roads}


def nearest_road(p, maxd=30.0, cls=None, city=None):
    best = None
    for a, b, (ri, k) in road_grid.near(p, maxd):
        r = R[ri]
        if (cls and r["cls"] not in cls) or (city and r["city"] != city and r["city"] in ORIGIN):
            continue
        q, t, d = closest_on_seg(p, a, b)
        if d < maxd and (best is None or d < best[0]):
            s = r["s"][k] + t * math.dist(a, b)
            best = (d, r, s, q, unit((b[0] - a[0], b[1] - a[1])))
    return best


def on_roadway(p, margin=0.3):
    for a, b, (ri, k) in road_grid.near(p, 20.0):
        if closest_on_seg(p, a, b)[2] < R[ri]["width"] / 2 + margin:
            return True
    return False


# ---------------------------------------------------------------- 3. intersections
def seg_x(a, b, c, d):
    r = (b[0] - a[0], b[1] - a[1]); s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-9:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    if -1e-6 <= t <= 1 + 1e-6 and -1e-6 <= u <= 1 + 1e-6:
        return (a[0] + r[0] * t, a[1] + r[1] * t)
    return None


raw = []   # (point, road_i, road_j)
for i, (a, b, (ri, ki)) in enumerate(road_grid.segs):
    for c, d, (rj, kj) in road_grid.near(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), math.dist(a, b) / 2 + 1.0):
        if rj <= ri:
            continue
        p = seg_x(a, b, c, d)
        if p:
            raw.append((p, ri, rj))
# T-junctions and pieces meeting end to end
for r in drive:
    for end in (r["pts"][0], r["pts"][-1]):
        for a, b, (rj, k) in road_grid.near(end, 3.0):
            if rj == r["i"]:
                continue
            q, t, dd = closest_on_seg(end, a, b)
            if dd < 2.5:
                raw.append((q, r["i"], rj))


def same_street_continues(ri, rj, p):
    a, b = R[ri], R[rj]
    if not a["name"] or a["name"] != b["name"]:
        return False
    da = min(math.dist(p, a["pts"][0]), math.dist(p, a["pts"][-1]))
    db = min(math.dist(p, b["pts"][0]), math.dist(p, b["pts"][-1]))
    return da < 3 and db < 3


raw = [x for x in raw if not same_street_continues(x[1], x[2], x[0])]
# cluster within 9 m
parent = list(range(len(raw)))


def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


cg = collections.defaultdict(list)
for i, (p, _, _) in enumerate(raw):
    cg[(int(p[0] // 9), int(p[1] // 9))].append(i)
for i, (p, _, _) in enumerate(raw):
    gx, gy = int(p[0] // 9), int(p[1] // 9)
    for u in range(gx - 1, gx + 2):
        for v in range(gy - 1, gy + 2):
            for j in cg.get((u, v), ()):
                if j > i and math.dist(p, raw[j][0]) < 9.0:
                    parent[find(i)] = find(j)
groups = collections.defaultdict(list)
for i in range(len(raw)):
    groups[find(i)].append(i)
nodes = []
for g in groups.values():
    pts = [raw[i][0] for i in g]
    members = sorted({raw[i][1] for i in g} | {raw[i][2] for i in g})
    c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    nodes.append({"p": c, "roads": members, "w": max(R[m]["width"] for m in members), "signal": False, "stop": False})
node_grid = collections.defaultdict(list)
for ni, n in enumerate(nodes):
    node_grid[(int(n["p"][0] // 40), int(n["p"][1] // 40))].append(ni)


def nodes_near(p, r):
    gx, gy = int(p[0] // 40), int(p[1] // 40)
    for u in range(gx - 1, gx + 2):
        for v in range(gy - 1, gy + 2):
            for ni in node_grid.get((u, v), ()):
                if math.dist(nodes[ni]["p"], p) < r:
                    yield ni


stats["nodes"] = len(nodes)
# per road: node positions along it
for r in drive:
    r["nodes"] = []
for ni, n in enumerate(nodes):
    for ri in n["roads"]:
        r = R[ri]
        best = None
        for k, (a, b) in enumerate(zip(r["pts"], r["pts"][1:])):
            q, t, d = closest_on_seg(n["p"], a, b)
            if best is None or d < best[0]:
                best = (d, r["s"][k] + t * math.dist(a, b))
        other_w = max([R[m]["width"] for m in n["roads"] if m != ri] or [0])
        r["nodes"].append((best[1], ni, other_w))

# ---------------------------------------------------------------- 4. OSM street features
feat = collections.defaultdict(list)    # kind -> [(p, city, tags)]
ways = collections.defaultdict(list)    # kind -> [(pts, city, tags)]
for city in ORIGIN:
    pr = PROJ[city]
    for el in json.load(open(ROOT / f"SourceArt/osm/{city}_street.json"))["elements"]:
        t = el.get("tags", {})
        if el["type"] == "node":
            p = pr(el["lat"], el["lon"])
            if not inbox(p) or not side_ok(city, p):
                continue
            hw, am = t.get("highway"), t.get("amenity")
            kind = (hw if hw in ("street_lamp", "traffic_signals", "stop", "give_way", "crossing", "bus_stop") else
                    "tree" if t.get("natural") == "tree" else
                    am if am in ("bicycle_parking", "bench", "waste_basket", "waste_disposal", "recycling", "post_box",
                                 "bicycle_rental", "fountain", "drinking_water") else
                    "hydrant" if t.get("emergency") == "fire_hydrant" else
                    "bollard" if t.get("barrier") == "bollard" else
                    "traffic_sign" if t.get("traffic_sign") else None)
            if kind:
                feat[kind].append((p, city, t))
        elif el["type"] == "way":
            run, runs = [], []
            for g in el.get("geometry") or []:
                if g is None:
                    if len(run) > 1:
                        runs.append(run)
                    run = []
                else:
                    run.append(pr(g["lat"], g["lon"]))
            if len(run) > 1:
                runs.append(run)
            hw = t.get("highway")
            kind = ("tree_row" if t.get("natural") == "tree_row" else
                    "alley" if hw == "service" and t.get("service") == "alley" else
                    "service" if hw == "service" else
                    "crossing" if t.get("footway") == "crossing" else
                    "sidewalk" if t.get("footway") == "sidewalk" else
                    "footway" if hw in ("footway", "pedestrian", "path", "cycleway", "steps") else
                    "parking" if t.get("amenity") == "parking" and t.get("parking") not in ("multi-storey", "underground", "rooftop") else
                    "gravel" if t.get("landuse") in ("construction", "brownfield", "railway") or t.get("surface") in ("gravel", "fine_gravel", "pebblestone", "dirt", "ground") else
                    "grass" if t.get("landuse") == "grass" or t.get("leisure") == "garden" or t.get("natural") in ("grassland", "scrub") or t.get("surface") == "grass" else
                    "pitch" if t.get("leisure") in ("pitch", "playground") else None)
            if not kind:
                continue
            for run in runs:
                c = run[len(run) // 2]
                if inbox(c) and side_ok(city, c):
                    ways[kind].append((run, city, t))
for k in list(feat):
    stats["osm_" + k] = len(feat[k])
for k in list(ways):
    stats["osmway_" + k] = len(ways[k])

# signals and stops onto nodes
for p, city, t in feat["traffic_signals"]:
    for ni in nodes_near(p, 30.0):
        nodes[ni]["signal"] = True
for p, city, t in feat["stop"]:
    for ni in nodes_near(p, 25.0):
        nodes[ni]["stop"] = True
for n in nodes:
    if not n["signal"] and len(n["roads"]) >= 2 and all(R[m]["cls"] in ("minor", "mid") for m in n["roads"]):
        n["stop"] = True     # Chicago and Austin: unsignalled residential corners are stop-controlled
stats["signal_nodes"] = sum(n["signal"] for n in nodes)
stats["stop_nodes"] = sum(n["stop"] for n in nodes)

# ---------------------------------------------------------------- 5. markings
M = {"solid_white": [], "solid_yellow": [], "dash_white": [], "bars": []}


def allowed_intervals(r, extra=0.0):
    L = r["s"][-1]
    gaps = []
    for s, ni, ow in r["nodes"]:
        T = ow / 2 + 1.0 + (4.5 if nodes[ni]["signal"] or nodes[ni]["stop"] else 0.0) + extra
        gaps.append((s - T, s + T))
    gaps.sort()
    out, cur = [], 0.0
    for a, b in gaps:
        if a > cur:
            out.append((cur, min(a, L)))
        cur = max(cur, b)
    if cur < L:
        out.append((cur, L))
    return [(a, b) for a, b in out if b - a > 2.0]


def add_line(r, off, kind, iv):
    for a, b in iv:
        if kind == "dash_white":
            s = a + (h32(r["i"], off) % 12)
            while s < b:
                seg = sub_polyline(r["pts"], r["s"], s, min(b, s + 3.0))
                if len(seg) >= 2:
                    M[kind].append([[round(x, 2), round(y, 2)] for x, y in offset_polyline(seg, off)])
                s += 12.0
        else:
            seg = sub_polyline(r["pts"], r["s"], a, b)
            if len(seg) >= 2:
                M[kind].append([[round(x, 2), round(y, 2)] for x, y in offset_polyline(seg, off)])


for r in drive:
    iv = allowed_intervals(r)
    L, lw, W = r["lanes"], r["lane_w"], r["width"]
    if r["cls"] == "minor":
        continue
    if r["oneway"]:
        for k in range(1, L):
            add_line(r, -L * lw / 2 + k * lw, "dash_white", iv)
        if r["cls"] == "highway":
            add_line(r, L * lw / 2 + 0.3, "solid_yellow", iv)
            add_line(r, -L * lw / 2 - 0.3, "solid_white", iv)
    else:
        add_line(r, 0.11, "solid_yellow", iv)
        add_line(r, -0.11, "solid_yellow", iv)
        half = max(1, L // 2)
        for k in range(1, half):
            add_line(r, k * lw, "dash_white", iv)
            add_line(r, -k * lw, "dash_white", iv)
        if r["cls"] == "highway":
            add_line(r, half * lw + 0.3, "solid_white", iv)
            add_line(r, -half * lw - 0.3, "solid_white", iv)


def rect(c, t, along, across):
    """Rectangle centred at c, `along` metres in direction t, `across` metres sideways."""
    n = (-t[1], t[0])
    ha, hc = along / 2, across / 2
    return [[round(c[0] + t[0] * sa * ha + n[0] * sc * hc, 2), round(c[1] + t[1] * sa * ha + n[1] * sc * hc, 2)]
            for sa, sc in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


crosswalks = []   # (road, s, node or None)


def add_crosswalk(r, s, ni):
    for rr, ss, _ in crosswalks:
        if rr is r and abs(ss - s) < 8.0:
            return
    crosswalks.append((r, s, ni))
    c, t = at_s(r["pts"], r["s"], s)
    n = (-t[1], t[0])
    W = r["width"]
    k = -W / 2 + 0.6
    while k <= W / 2 - 0.5:      # continental bars: 0.6 m wide, 0.6 m apart, 3 m long
        M["bars"].append(rect((c[0] + n[0] * k, c[1] + n[1] * k), t, 3.0, 0.6))
        k += 1.2
    if ni is None:
        return
    # stop bar on the approach side, across the lanes heading into the intersection
    toward = 1.0 if R[r["i"]]["s"] and s < [x for x in r["nodes"] if x[1] == ni][0][0] else -1.0
    dirv = (t[0] * toward, t[1] * toward)
    right = (dirv[1], -dirv[0])
    sb = s - toward * 3.2
    cb, _ = at_s(r["pts"], r["s"], sb)
    if r["oneway"]:
        travel = -1.0 if r["reverse"] else 1.0
        if travel != toward:
            return
        M["bars"].append(rect(cb, t, 0.6, W - 0.6))
    else:
        mid = (cb[0] + right[0] * W / 4, cb[1] + right[1] * W / 4)
        M["bars"].append(rect(mid, t, 0.6, W / 2 - 0.4))


for p, city, t in feat["crossing"]:
    nr = nearest_road(p, 6.0, DRIVE)
    if nr and nr[1]["cls"] != "highway":
        d, r, s, q, tg = nr
        ni = None
        for s_n, nn, ow in r["nodes"]:
            if abs(s_n - s) < 30:
                ni = nn
        add_crosswalk(r, s, ni)
for ni, n in enumerate(nodes):
    if not (n["signal"] or (n["stop"] and R[n["roads"][0]]["core"])):
        continue
    for ri in n["roads"]:
        r = R[ri]
        if r["cls"] == "highway":
            continue
        for s_n, nn, ow in r["nodes"]:
            if nn != ni:
                continue
            for sgn in (-1, 1):
                s = s_n + sgn * (ow / 2 + 2.5)
                if 0 < s < r["s"][-1]:
                    add_crosswalk(r, s, ni)
stats["crosswalks"] = len(crosswalks)
for k, v in M.items():
    stats["mark_" + k] = len(v)

# ---------------------------------------------------------------- 6. props
props = []


def prop(kind, p, yaw, **kw):
    d = {"t": kind, "p": [round(p[0], 2), round(p[1], 2)], "yaw": round(math.degrees(yaw) % 360, 1)}
    d.update(kw)
    props.append(d)


def kerb_spot(r, s, side, inset):
    """A point `inset` metres behind the kerb on `side` (+1 left, -1 right of the road's direction)."""
    c, t = at_s(r["pts"], r["s"], s)
    n = (-t[1], t[0])
    o = side * (r["width"] / 2 + inset)
    return (c[0] + n[0] * o, c[1] + n[1] * o), t, n


def near_node(r, s, d):
    return any(abs(s - sn) < d + ow / 2 for sn, _, ow in r["nodes"])


def facing_road(p, q):
    return math.atan2(q[1] - p[1], q[0] - p[0])


def ok_spot(p):
    return bool(on_land([p])[0]) and not on_roadway(p, 0.2) and not in_footprint(p)


fp_grid = collections.defaultdict(list)
for b in BLD:
    a = math.radians(90.0 - b["yaw"])
    # footprint axes in the plan frame (buildings_v3 yaw is compass-style; same convention as corners() in Unreal)
    fp_grid[(int(b["x"] // 50), int(b["y"] // 50))].append(b)


def in_footprint(p, margin=0.4):
    gx, gy = int(p[0] // 50), int(p[1] // 50)
    for u in range(gx - 2, gx + 3):
        for v in range(gy - 2, gy + 3):
            for b in fp_grid.get((u, v), ()):
                a = math.radians(b["yaw"])
                dx, dy = p[0] - b["x"], p[1] - b["y"]
                # plan frame: footprint width along (sin a, cos a)?? use both axes symmetric test with rotation
                ca, sa = math.cos(a), math.sin(a)
                u_ = dx * sa + dy * ca
                v_ = dx * ca - dy * sa
                if abs(u_) < b["w"] / 2 + margin and abs(v_) < b["d"] / 2 + margin:
                    return True
    return False


# lamps: OSM first, then fill the gaps along bigger streets
lamp_pts = []
for p, city, t in feat["street_lamp"]:
    nr = nearest_road(p, 25.0, DRIVE)
    if not nr:
        continue
    d, r, s, q, tg = nr
    if d < r["width"] / 2 + 0.4:     # mapped on the carriageway: move it onto the kerb line
        side = 1 if ((p[0] - q[0]) * -tg[1] + (p[1] - q[1]) * tg[0]) >= 0 else -1
        p = kerb_spot(r, s, side, 0.6)[0]
    if not ok_spot(p):
        continue
    lamp_pts.append(p)
    prop("lamp", p, facing_road(p, q), city=city, src="osm")
lamp_grid = collections.defaultdict(list)
for p in lamp_pts:
    lamp_grid[(int(p[0] // 30), int(p[1] // 30))].append(p)


def lamp_near(p, d):
    gx, gy = int(p[0] // 30), int(p[1] // 30)
    return any(math.dist(p, q) < d for u in range(gx - 1, gx + 2) for v in range(gy - 1, gy + 2) for q in lamp_grid.get((u, v), ()))


for r in drive:
    step = {"highway": 45.0, "major": 32.0, "mid": 36.0, "minor": 42.0}[r["cls"]]
    sides = (1, -1) if r["cls"] != "minor" else (1 if h32(r["i"]) & 1 else -1,)
    for side in sides:
        s = (step / 2 if side > 0 else 0.0) + rnd(r["i"], side) * 6
        while s < r["s"][-1]:
            if not near_node(r, s, 6.0):
                p, t, n = kerb_spot(r, s, side, 0.6 if r["cls"] != "highway" else 1.2)
                if not lamp_near(p, 15.0) and ok_spot(p):
                    prop("lamp", p, math.atan2(-n[1] * side, -n[0] * side), city=r["city"], src="rule",
                         style="highway" if r["cls"] == "highway" else "street")
                    lamp_grid[(int(p[0] // 30), int(p[1] // 30))].append(p)
            s += step

# trees
SPECIES = {"chicago": [("honeylocust", 0.4), ("linden", 0.3), ("elm", 0.3)], "austin": [("liveoak", 0.65), ("elm", 0.35)]}


def species(city, p):
    x = rnd(round(p[0], 1), round(p[1], 1))
    acc = 0.0
    for sp, w in SPECIES[city]:
        acc += w
        if x <= acc:
            return sp
    return SPECIES[city][-1][0]


tree_grid = collections.defaultdict(list)


def tree_near(p, d):
    gx, gy = int(p[0] // 20), int(p[1] // 20)
    return any(math.dist(p, q) < d for u in range(gx - 1, gx + 2) for v in range(gy - 1, gy + 2) for q in tree_grid.get((u, v), ()))


def add_tree(p, city, src, pit, gap=3.5):
    if tree_near(p, gap) or not ok_spot(p) or bool(in_beach([p])[0]):
        return
    tree_grid[(int(p[0] // 20), int(p[1] // 20))].append(p)
    prop("tree", p, rnd(p[0], p[1], 7) * 2 * math.pi, city=city, sp=species(city, p), scale=round(0.8 + 0.45 * rnd(p[1], p[0]), 2),
         pit=pit, src=src)


tree_src = list(feat["tree"])
for pts, city, t in ways["tree_row"]:
    s_cum = cumlen(pts)
    k = 0.0
    while k <= s_cum[-1]:
        tree_src.append((at_s(pts, s_cum, k)[0], city, t))
        k += 9.0
for p, city, t in tree_src:
    nr = nearest_road(p, 12.0, DRIVE)
    pit = "grate" if (nr and nr[1]["core"]) else ("park" if bool(in_park([p])[0]) else "grass")
    add_tree(p, city, "osm", pit)
for r in drive:
    if not r["parkway"]:
        continue
    for side in (1, -1):
        s = 6.0 + rnd(r["i"], side, 3) * 5
        while s < r["s"][-1]:
            if not near_node(r, s, 7.0):
                p = kerb_spot(r, s, side, 1.5)[0]
                add_tree(p, r["city"], "rule", "grass")
            s += 10.0 + rnd(r["i"], s) * 3
# park fill
for ring in PLAN["parks"]:
    a = np.array(ring, float)
    area = 0.5 * abs(np.dot(a[:, 0], np.roll(a[:, 1], 1)) - np.dot(a[:, 1], np.roll(a[:, 0], 1)))
    n = int(min(area / 700.0, 400))      # open parkland: fill only where OSM's own trees leave gaps
    if n <= 0:
        continue
    lo, hi = a.min(0), a.max(0)
    rng = np.random.default_rng(h32(round(lo[0]), round(lo[1])))
    cand = rng.uniform(lo, hi, size=(n * 3, 2))
    inside = points_in_poly(cand, a)
    city = "chicago" if side_ok("chicago", tuple(a.mean(0)), 0) else "austin"
    for p in cand[inside][:n]:
        add_tree((float(p[0]), float(p[1])), city, "park", "park", gap=11.0)
stats["trees"] = sum(1 for x in props if x["t"] == "tree")
stats["lamps"] = sum(1 for x in props if x["t"] == "lamp")


# simple OSM point props, nudged off the carriageway
def place_osm(kind, out_kind, min_gap=1.0):
    seen = []
    for p, city, t in feat[kind]:
        nr = nearest_road(p, 20.0, DRIVE)
        if nr:
            d, r, s, q, tg = nr
            if d < r["width"] / 2 + 0.5:
                side = 1 if ((p[0] - q[0]) * -tg[1] + (p[1] - q[1]) * tg[0]) >= 0 else -1
                p = kerb_spot(r, s, side, 1.0)[0]
            yaw = facing_road(p, q) + math.pi / 2
        else:
            yaw = rnd(p[0], p[1]) * 2 * math.pi
        if not ok_spot(p) or any(math.dist(p, x) < min_gap for x in seen[-50:]):
            continue
        seen.append(p)
        prop(out_kind, p, yaw, city=city, src="osm")


place_osm("bicycle_parking", "bikerack")
place_osm("bench", "bench")
place_osm("waste_basket", "bin")
place_osm("hydrant", "hydrant")
place_osm("post_box", "mailbox")
place_osm("bicycle_rental", "bikeshare", 4.0)
place_osm("bus_stop", "busstop", 10.0)

# per-intersection furniture: signals, stop signs, name signs, hydrants, bins, drains, utility boxes
names = collections.Counter()
for ni, n in enumerate(nodes):
    legs = []
    for ri in n["roads"]:
        r = R[ri]
        for s_n, nn, ow in r["nodes"]:
            if nn != ni:
                continue
            for sgn in (-1, 1):       # each direction the road leaves the node
                s = s_n + sgn * (ow / 2 + 1.5)
                if 0.5 < s < r["s"][-1] - 0.5:
                    legs.append((r, s_n, sgn, ow))
    for k, (r, s_n, sgn, ow) in enumerate(legs):
        if r["cls"] == "highway":
            continue
        # traffic approaching the node along this leg travels in direction -sgn
        travel = -sgn
        if r["oneway"] and travel != (-1 if r["reverse"] else 1):
            approach_ok = False
        else:
            approach_ok = True
        s_corner = s_n + sgn * (ow / 2 + 1.2)
        c, t = at_s(r["pts"], r["s"], s_corner)
        dirv = (t[0] * travel, t[1] * travel)
        right = (dirv[1], -dirv[0])
        corner = (c[0] + right[0] * (r["width"] / 2 + 0.8), c[1] + right[1] * (r["width"] / 2 + 0.8))
        face = math.atan2(-dirv[1], -dirv[0])         # sign faces the approaching driver
        if not ok_spot(corner):
            continue
        if approach_ok and n["signal"]:
            arm = min(14.0, (r["lanes"] if r["oneway"] else max(1, r["lanes"] // 2)) * r["lane_w"] + 0.8)
            prop("signal", corner, face, arm=round(arm, 1), city=r["city"])
            if k == 0:
                ub = (corner[0] + dirv[0] * -3.0 + right[0] * 1.2, corner[1] + dirv[1] * -3.0 + right[1] * 1.2)
                if ok_spot(ub):
                    prop("utilitybox", ub, face, city=r["city"])
        elif approach_ok and n["stop"]:
            prop("stopsign", corner, face, city=r["city"])
        if approach_ok and r["cls"] != "highway":
            drain = (c[0] + right[0] * (r["width"] / 2 - 0.25) - dirv[0] * 1.5, c[1] + right[1] * (r["width"] / 2 - 0.25) - dirv[1] * 1.5)
            prop("drain", drain, math.atan2(dirv[1], dirv[0]), city=r["city"])
    named = sorted({R[ri]["name"] for ri in n["roads"] if R[ri]["name"] and R[ri]["cls"] != "highway"})
    if len(named) >= 2 and legs:
        r, s_n, sgn, ow = legs[0]
        c, t = at_s(r["pts"], r["s"], s_n + sgn * (ow / 2 + 1.0))
        nrm = (-t[1], t[0])
        p = (c[0] + nrm[0] * (r["width"] / 2 + 0.7), c[1] + nrm[1] * (r["width"] / 2 + 0.7))
        if ok_spot(p):
            a_name, b_name = named[0], named[1]
            ra = next(R[ri] for ri in n["roads"] if R[ri]["name"] == a_name)
            rb = next(R[ri] for ri in n["roads"] if R[ri]["name"] == b_name)
            ta = nearest_road(n["p"], 40.0)
            ya = math.atan2(*reversed(at_s(ra["pts"], ra["s"], [x for x in ra["nodes"] if x[1] == ni][0][0])[1]))
            yb = math.atan2(*reversed(at_s(rb["pts"], rb["s"], [x for x in rb["nodes"] if x[1] == ni][0][0])[1]))
            prop("namesign", p, ya, a=a_name, b=b_name, yaw_b=round(math.degrees(yb) % 360, 1), city=r["city"])
            names[a_name] += 1
            names[b_name] += 1
    # a hydrant and (downtown) a bin at one corner of most intersections
    if legs and rnd(ni, "hyd") < 0.7:
        r, s_n, sgn, ow = legs[-1]
        p, t, nrm = kerb_spot(r, s_n + sgn * (ow / 2 + 5.5), -1, 0.5)
        if ok_spot(p):
            prop("hydrant", p, math.atan2(t[1], t[0]), city=r["city"], src="rule")
    if legs and legs[0][0]["core"] and rnd(ni, "bin") < 0.6:
        r, s_n, sgn, ow = legs[0]
        p, t, nrm = kerb_spot(r, s_n + sgn * (ow / 2 + 3.0), 1, 0.7)
        if ok_spot(p):
            prop("bin", p, math.atan2(t[1], t[0]), city=r["city"], src="rule")

# speed limit signs: after each big crossing and every ~400 m, facing traffic, on the right
for r in drive:
    if r["cls"] == "minor" or r["s"][-1] < 150:
        continue
    dirs = [(-1 if r["reverse"] else 1)] if r["oneway"] else [1, -1]
    for travel in dirs:
        s = 60.0
        while s < r["s"][-1] - 40:
            sp = s if travel > 0 else r["s"][-1] - s
            if not near_node(r, sp, 15.0):
                c, t = at_s(r["pts"], r["s"], sp)
                dirv = (t[0] * travel, t[1] * travel)
                right = (dirv[1], -dirv[0])
                p = (c[0] + right[0] * (r["width"] / 2 + 0.6), c[1] + right[1] * (r["width"] / 2 + 0.6))
                if ok_spot(p):
                    prop("speedsign", p, math.atan2(-dirv[1], -dirv[0]), mph=int(r["speed"]), city=r["city"])
            s += 400.0
# manholes on the carriageway
for r in drive:
    s = 20.0 + rnd(r["i"], "mh") * 30
    while s < r["s"][-1]:
        if not near_node(r, s, 4.0):
            c, t = at_s(r["pts"], r["s"], s)
            off = (rnd(r["i"], s) - 0.5) * (r["width"] - 3.0)
            prop("manhole", (c[0] - t[1] * off, c[1] + t[0] * off), rnd(s, r["i"]) * 2 * math.pi, city=r["city"])
        s += 55.0 + rnd(s, "mh") * 30

# alleys and dumpsters
paths = {"alley": [], "park_path": [], "plaza": [], "ballast": []}
for pts, city, t in ways["alley"]:
    if len(pts) < 2:
        continue
    keep = [p for p in pts if bool(on_land([p])[0])]
    if len(keep) < 2:
        continue
    paths["alley"].append({"pts": [[round(x, 2), round(y, 2)] for x, y in pts], "w": 5.0})
    s_cum = cumlen(pts)
    s = 12.0 + rnd(pts[0][0], pts[0][1]) * 10
    side = 1
    while s < s_cum[-1] - 6:
        c, tg = at_s(pts, s_cum, s)
        p = (c[0] - tg[1] * side * 1.9, c[1] + tg[0] * side * 1.9)
        if bool(on_land([p])[0]) and not on_roadway(p, 1.0) and rnd(s, c[0]) < 0.75:
            prop("dumpster", p, math.atan2(tg[1], tg[0]) + (math.pi if side < 0 else 0), city=city)
        side = -side
        s += 28.0 + rnd(c[1], s) * 20
for pts, city, t in ways["footway"]:
    mid = pts[len(pts) // 2]
    if bool(in_park([mid])[0]):
        paths["park_path"].append({"pts": [[round(x, 2), round(y, 2)] for x, y in pts], "w": 4.0 if t.get("highway") == "pedestrian" else 2.6})
for r in roads:
    if r["cls"] == "ped" and not r["skip"]:
        paths["plaza"].append({"pts": [[round(x, 2), round(y, 2)] for x, y in r["pts"]], "w": 7.0})
for rl in PLAN["rail"]:
    if rl["kind"] == "rail":
        paths["ballast"].append({"pts": rl["pts"], "w": 5.0})

areas = {"grass": [], "gravel": [], "parking": [], "pitch": []}
for kind in areas:
    for pts, city, t in ways[kind]:
        if len(pts) >= 4 and math.dist(pts[0], pts[-1]) < 1.0:
            areas[kind].append([[round(x, 2), round(y, 2)] for x, y in pts[:-1]])
areas["grass"] += [list(map(list, ring)) for ring in PLAN["parks"]]

for k in ("alley", "park_path", "plaza", "ballast"):
    stats["path_" + k] = len(paths[k])
for k in areas:
    stats["area_" + k] = len(areas[k])
stats.update(collections.Counter("prop_" + p["t"] for p in props))

OUT.parent.mkdir(parents=True, exist_ok=True)
out = {
    "frame": "plan metres, x east, y north; Unreal X = y*100, Y = x*100; yaw degrees CCW from +x",
    "attribution": "(c) OpenStreetMap contributors",
    "roads": [{k: v for k, v in r.items() if k not in ("s",)} | {"nodes": [[round(a, 2), b, c] for a, b, c in r.get("nodes", [])]} for r in roads],
    "nodes": [{"p": [round(n["p"][0], 2), round(n["p"][1], 2)], "roads": n["roads"], "w": n["w"], "signal": n["signal"], "stop": n["stop"]} for n in nodes],
    "markings": M, "props": props, "paths": paths, "areas": areas,
    "names": [n for n, _ in names.most_common()],
    "stats": dict(stats),
}
OUT.write_text(json.dumps(out, separators=(",", ":")))
print(json.dumps(dict(stats), indent=1))
print("wrote", OUT, round(OUT.stat().st_size / 1e6, 1), "MB")
