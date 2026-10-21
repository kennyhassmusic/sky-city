"""Seam junction audit: find and rank the messy intersections where the mashup stitched Chicago's streets to Austin's.

Why: Kenny (20 Oct night): "in austin, I think near where the pedestrian walk way would be, probably in the place(s) where
some of the streets were supposed to merge (chicago to austin) that there are some major logical street messes at major
intersections. those can be simplified." The mashup plan (Saved/Mashup/plan_v3.json) joined the two cities along a seam
at 46 deg through plan (100, -50) with connector pieces ("stitch" roads from integrate_v2.py, "sketch" roads from Kenny's
19 Oct sketch: Seam Circle, Crosstown Parkway, the expressways and the Ida B. Wells ramp). Where those pieces land next to
the cities' own streets the network can bunch several junction nodes together, meet at odd angles, leave stubs, doubled
pieces and dead ends, trap one-way traffic or make the traffic links loop back. This script measures all of that for every
major intersection near the seam, the stitch/sketch roads and Austin's pedestrian ways (plan "ped" roads, park paths and
the bridges), scores each and ranks them.

A "site" is a cluster of junction nodes joined by streets shorter than 45 m (or closer than 35 m). Per site:
  nodes      junction nodes in the cluster (a real intersection is one node; a divided road crossing makes two)
  legs       streets leaving the cluster; min_angle between neighbouring legs; acute = leg pairs meeting at 12-55 deg
  stubs      pieces < 40 m ending in a dead end or a dangling pass node next to the site; dead ends within 120 m
  overlap    m2 where two street ribbons lie on top of each other outside the junction rings (doubled roads, slivers)
  apron      junction-ring area and its largest dimension
  oneway     junction nodes no car can leave or reach in traffic.json, nodes outside the main strongly connected piece
  traffic    for every way into the site and every way out (not straight back), the route through it: unreachable pairs,
             detours (> 2.2 x the straight distance or > 230 deg of turning)
Score = a weighted sum (see SCORE); the list is sorted by it.
Output: Saved/Roads/seam/audit_<tag>.json, crops Saved/Roads/seam/<tag>_<nn>.jpg (debug_render.render_box) and an index
sheet Saved/Roads/seam/<tag>_overview.jpg. Plan metres, x east, y north; Unreal X = y*100, Y = x*100.
Run: python3 -I Scripts/roads/seam_audit.py [path/to/roadnet.json] [--tag before] [--render N] [--sites file.json]
                                           [--roi-from other/roadnet.json]
  --sites: render the same boxes as an earlier audit (for before/after pairs).
  --roi-from: the region of interest from another network's connector roads (compare before and after on one region).
"""
import collections, heapq, json, math, pathlib, sys
import numpy as np
from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Scripts" / "roads"))
import debug_render as DR  # noqa: E402

args = [a for a in sys.argv[1:]]


def opt(name, default=None):
    if name in args:
        i = args.index(name)
        v = args[i + 1]
        del args[i:i + 2]
        return v
    return default


TAG = opt("--tag", "now")
ROI_FROM = opt("--roi-from")          # take the region of interest (the connector roads) from another roadnet.json
NREN = int(opt("--render", "0"))
SITES_FROM = opt("--sites")
RN_PATH = pathlib.Path(args[0]) if args else ROOT / "Saved/Roads/roadnet.json"
D = json.load(open(RN_PATH))
TR_PATH = RN_PATH.parent / "traffic.json"
TR = json.load(open(TR_PATH))
PLAN = json.load(open(ROOT / "Saved/Mashup/plan_v3.json"))
OUTD = ROOT / "Saved/Roads/seam"
OUTD.mkdir(parents=True, exist_ok=True)
SEAM = PLAN["seam"]


def ue(p):
    return [round(p[1] * 100), round(p[0] * 100)]


def unit(v):
    L = math.hypot(v[0], v[1]) or 1e-12
    return (v[0] / L, v[1] / L)


def cumlen(pts):
    s = [0.0]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + math.dist(a, b))
    return s


def closest_on_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy or 1e-12
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    q = (a[0] + dx * t, a[1] + dy * t)
    return math.dist(p, q)


def dist_poly(p, pts):
    return min(closest_on_seg(p, a, b) for a, b in zip(pts, pts[1:])) if len(pts) >= 2 else math.dist(p, pts[0])


def poly_area(r):
    return abs(sum(r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1] for i in range(len(r)))) / 2


def at_len(pts, s):
    sc = cumlen(pts)
    s = min(s, sc[-1])
    for i in range(len(pts) - 1):
        if sc[i + 1] >= s:
            t = (s - sc[i]) / ((sc[i + 1] - sc[i]) or 1e-9)
            return (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t)
    return pts[-1]


# ---------------------------------------------------------------- the network rebuilt from roadnet.json
key = lambda p: (round(p[0], 2), round(p[1], 2))
nid = {}
npos = []
adj = collections.defaultdict(list)          # node -> [(edge index, other node)]
E = D["edges"]
for i, e in enumerate(E):
    a, b = key(e["geom"][0]), key(e["geom"][-1])
    for k in (a, b):
        if k not in nid:
            nid[k] = len(npos)
            npos.append(k)
    e["_a"], e["_b"] = nid[a], nid[b]
    e["_L"] = cumlen(e["geom"])[-1]
    adj[nid[a]].append((i, nid[b]))
    adj[nid[b]].append((i, nid[a]))
    e["_seam"] = any(t in e.get("pc", "") for t in ("stitch", "sketch", "new"))
# node kinds from the rebuilt graph (roadnet.json's "ends" are in its graph's node order, not the geometry's)
X0_, Y0_, X1_, Y1_ = PLAN["bounds"]
kind = {}
for n in range(len(npos)):
    deg = len(adj[n])
    p = npos[n]
    edge_ = p[0] < X0_ + 60 or p[0] > X1_ - 60 or p[1] < Y0_ + 60 or p[1] > Y1_ - 60
    kind[n] = ("edge" if edge_ else "deadend") if deg == 1 else ("pass" if deg == 2 else "junction")
jnodes = [n for n in range(len(npos)) if kind.get(n) == "junction"]
ring_of = {key(j["c"]): j for j in D["junctions"]}
unit_ctrl = {u["unit"]: u for u in D["units"]}

# region of interest: the seam, the stitch / sketch connectors, Austin's pedestrian ways and bridges
seam_edges = [e for e in E if e["_seam"]]
PED = [r["pts"] for r in PLAN["roads"] if r["cls"] == "ped" and r["city"] == "austin"]
# park paths and plazas from the street pass (OSM footways in parks, the Lady Bird Lake trail) on the Austin side
SDp = json.load(open(ROOT / "Saved/Streets/street_data.json")).get("paths", {})
for kind_ in ("park_path", "plaza"):
    for pth in SDp.get(kind_, []):
        PED.append(pth["pts"])


def seg_grid(polys, cell=50.0):
    g = collections.defaultdict(list)
    for pi, pts in enumerate(polys):
        for a, b in zip(pts, pts[1:]):
            for gx in range(int(min(a[0], b[0]) // cell), int(max(a[0], b[0]) // cell) + 1):
                for gy in range(int(min(a[1], b[1]) // cell), int(max(a[1], b[1]) // cell) + 1):
                    g[(gx, gy)].append((a, b))
    return g, cell


def near_dist(grid, p, r):
    g, cell = grid
    best = r
    for gx in range(int((p[0] - r) // cell), int((p[0] + r) // cell) + 1):
        for gy in range(int((p[1] - r) // cell), int((p[1] + r) // cell) + 1):
            for a, b in g.get((gx, gy), ()):
                best = min(best, closest_on_seg(p, a, b))
    return best


G_SEAM = seg_grid([SEAM])
if ROI_FROM:
    _roi = json.load(open(ROI_FROM))["edges"]
    G_STITCH = seg_grid([e["geom"] for e in _roi if any(t in e.get("pc", "") for t in ("stitch", "sketch", "new"))])
else:
    G_STITCH = seg_grid([e["geom"] for e in seam_edges])
G_PED = seg_grid(PED)
AUSTIN_BRIDGES = [b["pts"] for b in PLAN["bridges"]]
G_BR = seg_grid(AUSTIN_BRIDGES)

# ---------------------------------------------------------------- traffic graph
TN = {key(p): int(k) for k, p in TR["nodes"].items()}
t_out = collections.defaultdict(list)
t_in = collections.defaultdict(list)
for li, l in enumerate(TR["links"]):
    l["_L"] = cumlen(l["p"])[-1]
    t_out[l["a"]].append(li)
    t_in[l["b"]].append(li)
# main strongly connected piece (Tarjan, iterative)
import networkx as nx  # noqa: E402
DG = nx.DiGraph()
for l in TR["links"]:
    DG.add_edge(l["a"], l["b"])
sccs = sorted(nx.strongly_connected_components(DG), key=len, reverse=True)
MAIN = sccs[0] if sccs else set()

# ---------------------------------------------------------------- sites: clusters of junction nodes
par = {n: n for n in jnodes}


def f(x):
    while par[x] != x:
        par[x] = par[par[x]]
        x = par[x]
    return x


jset = set(jnodes)
for i, e in enumerate(E):
    if e["_a"] in jset and e["_b"] in jset and e["_a"] != e["_b"] and e["_L"] < 45.0:
        par[f(e["_a"])] = f(e["_b"])
cg = collections.defaultdict(list)
for n in jnodes:
    cg[(int(npos[n][0] // 35), int(npos[n][1] // 35))].append(n)
for n in jnodes:
    gx, gy = int(npos[n][0] // 35), int(npos[n][1] // 35)
    for u in range(gx - 1, gx + 2):
        for v in range(gy - 1, gy + 2):
            for m in cg.get((u, v), ()):
                if m > n and math.dist(npos[n], npos[m]) < 35.0:
                    par[f(n)] = f(m)
clusters = collections.defaultdict(list)
for n in jnodes:
    clusters[f(n)].append(n)

# pavement raster for overlaps (0.5 m), built lazily per site
RES = 0.5


def site_overlap(box, edges_idx, rings):
    x0, y0, x1, y1 = box
    W, H = int((x1 - x0) / RES) + 1, int((y1 - y0) / RES) + 1
    if W * H > 4e6:
        return 0.0
    cnt = np.zeros((H, W), np.uint8)
    P = lambda p: ((p[0] - x0) / RES, (y1 - p[1]) / RES)
    for i in edges_idx:
        rb = E[i]["ribbon"]
        if not rb or len(rb) < 3:
            continue
        im = Image.new("L", (W, H), 0)
        ImageDraw.Draw(im).polygon([P(p) for p in rb], fill=1)
        cnt += np.array(im, np.uint8)
    im = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(im)
    for r in rings:
        dr.polygon([P(p) for p in r], fill=1)
    for j in D["joints"]:
        if len(j) >= 3 and x0 - 20 <= j[0][0] <= x1 + 20 and y0 - 20 <= j[0][1] <= y1 + 20:
            dr.polygon([P(p) for p in j], fill=1)
    ring = np.array(im, bool)
    return float(((cnt >= 2) & ~ring).sum() * RES * RES)


def leg_dir(e, n):
    g = e["geom"] if e["_a"] == n else e["geom"][::-1]
    q = at_len(g, min(20.0, e["_L"] * 0.5))
    return unit((q[0] - g[0][0], q[1] - g[0][1]))


def route(starts, goal_nodes, inside):
    """Dijkstra over traffic links from a set of (node, heading) starts, staying inside the site; returns
    {node: (length, turning)} for goal nodes."""
    best = {}
    pq = []
    for n, h in starts:
        heapq.heappush(pq, (0.0, 0.0, n, h))
    seen = set()
    res = {}
    while pq:
        L, turn, n, h = heapq.heappop(pq)
        if (n, round(h[0], 2), round(h[1], 2)) in seen:
            continue
        seen.add((n, round(h[0], 2), round(h[1], 2)))
        if n in goal_nodes and n not in res:
            res[n] = (L, turn)
        for li in t_out.get(n, ()):
            l = TR["links"][li]
            if l["b"] not in inside:
                continue
            p = l["p"]
            d0 = unit((p[1][0] - p[0][0], p[1][1] - p[0][1]))
            d1 = unit((p[-1][0] - p[-2][0], p[-1][1] - p[-2][1]))
            a = abs(math.degrees(math.atan2(h[0] * d0[1] - h[1] * d0[0], h[0] * d0[0] + h[1] * d0[1])))
            if a > 150:
                continue                         # no U-turns inside a junction
            heapq.heappush(pq, (L + l["_L"], turn + a, l["b"], d1))
    return res


SCORE = {"extra_nodes": 3.0, "extra_legs": 1.0, "acute": 2.0, "stubs": 3.0, "deadends": 1.0, "overlap_m2": 1 / 40.0,
         "apron_m2": 1 / 1500.0, "traps": 4.0, "unreach": 1.5, "detours": 1.0, "seam_bonus": 2.0}
sites = []
for root, nodes in clusters.items():
    ns = set(nodes)
    c = (sum(npos[n][0] for n in nodes) / len(nodes), sum(npos[n][1] for n in nodes) / len(nodes))
    dseam = near_dist(G_SEAM, c, 400.0)
    dstitch = near_dist(G_STITCH, c, 400.0)
    dped = near_dist(G_PED, c, 200.0)
    dbr = near_dist(G_BR, c, 200.0)
    # legs and internal pieces
    legs, internal = [], []
    for n in nodes:
        for i, m in adj[n]:
            e = E[i]
            if m in ns and m != n:
                if i not in internal:
                    internal.append(i)
                continue
            legs.append((n, i, m))
    cls = [E[i]["cls"] for _, i, _ in legs]
    major = any(k in ("major", "highway") for k in cls)
    austin = sum(1 for _, i, _ in legs if E[i]["city"] == "austin") >= 1
    seamish = any(E[i]["_seam"] for _, i, _ in legs) or any(E[i]["_seam"] for i in internal)
    in_roi = (dseam <= 300 or dstitch <= 300) or (austin and (dped <= 60 or dbr <= 60))
    if not in_roi or len(legs) < 3:
        continue
    # angles between neighbouring legs (directions taken from the site centre)
    dirs = sorted([(math.atan2(*leg_dir(E[i], n)[::-1]), n, i) for n, i, m in legs])
    gaps = [((dirs[(k + 1) % len(dirs)][0] - dirs[k][0]) % (2 * math.pi)) for k in range(len(dirs))]
    min_ang = math.degrees(min(gaps)) if gaps else 180
    acute = []
    for k in range(len(dirs)):
        g = math.degrees(gaps[k])
        a_, b_ = E[dirs[k][2]], E[dirs[(k + 1) % len(dirs)][2]]
        if 12.0 <= g <= 55.0 and not (a_["name"] and a_["name"] == b_["name"]):
            acute.append((a_["name"] or a_["cls"], b_["name"] or b_["cls"], round(g)))
    # stubs and dead ends
    stubs = []
    for n, i, m in legs:
        e = E[i]
        if kind.get(m) == "deadend" and e["_L"] < 60.0:
            stubs.append((e["name"] or e["cls"], round(e["_L"]), "dead-end stub"))
        elif kind.get(m) == "pass" and e["_L"] < 25.0:
            # a pass node right outside the site: what's beyond it?
            nxt = [j for j, o in adj[m] if j != i]
            if nxt and kind.get(E[nxt[0]]["_b"] if E[nxt[0]]["_a"] == m else E[nxt[0]]["_a"]) == "deadend":
                stubs.append((e["name"] or e["cls"], round(e["_L"] + E[nxt[0]]["_L"]), "dead-end stub"))
        elif kind.get(m) == "junction" and m not in ns and e["_L"] < 12.0:
            stubs.append((e["name"] or e["cls"], round(e["_L"]), "sliver link"))
    dead = [n for n in range(len(npos)) if kind.get(n) == "deadend" and math.dist(npos[n], c) < 120.0]
    # overlap and apron
    rings = [ring_of[npos[n]]["ring"] for n in nodes if npos[n] in ring_of]
    apron = sum(poly_area(r) for r in rings)
    allp = [p for r in rings for p in r] or [c]
    span = max(math.dist(p, q) for p in allp for q in allp) if len(allp) > 1 else 0.0
    box = (c[0] - 90, c[1] - 90, c[0] + 90, c[1] + 90)
    eidx = [i for i, e in enumerate(E) if e["ribbon"] and any(box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3] for p in e["geom"][::max(1, len(e["geom"]) // 8)] + [e["geom"][-1]])]
    overlap = site_overlap(box, eidx, [j["ring"] for j in D["junctions"] if math.dist(j["c"], c) < 160])
    # one-way traps and traffic through the site
    tnodes = {TN[npos[n]] for n in nodes if npos[n] in TN}
    traps = [n for n in tnodes if not t_out.get(n) or not t_in.get(n)]
    off_main = [n for n in tnodes if n not in MAIN]
    inside = set(tnodes)
    unreach, detours = 0, []
    entries = []      # (link index arriving at a site node from outside)
    exits = []
    for n in tnodes:
        for li in t_in.get(n, ()):
            if TR["links"][li]["a"] not in inside:
                entries.append(li)
        for li in t_out.get(n, ()):
            if TR["links"][li]["b"] not in inside:
                exits.append(li)
    for li in entries:
        l = TR["links"][li]
        p = l["p"]
        h = unit((p[-1][0] - p[-2][0], p[-1][1] - p[-2][1]))
        goals = {TR["links"][lo]["a"]: lo for lo in exits}
        res = route([(l["b"], h)], set(goals), inside)
        for lo in exits:
            lx = TR["links"][lo]
            if lx["b"] == l["a"]:
                continue                       # straight back where it came from
            q = lx["p"]
            d_out = unit((q[1][0] - q[0][0], q[1][1] - q[0][1]))
            if h[0] * d_out[0] + h[1] * d_out[1] < -0.85:
                continue                       # a U-turn movement
            r = res.get(lx["a"])
            if r is None:
                unreach += 1
                continue
            # the turning of the last step onto the exit link
            a_last = 0.0
            straight = math.dist(p[-1], q[0])
            if r[0] > max(30.0, 2.2 * straight + 15.0) or r[1] > 230.0:
                detours.append((l.get("n") or "?", lx.get("n") or "?", round(r[0]), round(r[1])))
    feats = {"extra_nodes": len(nodes) - 1, "extra_legs": max(0, len(legs) - 4), "acute": len(acute), "stubs": len(stubs),
             "deadends": len(dead), "overlap_m2": overlap, "apron_m2": max(0.0, apron - 900.0), "traps": len(traps) + len(off_main),
             "unreach": min(unreach, 12), "detours": min(len(detours), 12), "seam_bonus": 1.0 if seamish else 0.0}
    score = sum(SCORE[k] * v for k, v in feats.items())
    names = sorted({E[i]["name"] for _, i, _ in legs if E[i]["name"]})
    ctrls = sorted({unit_ctrl[ring_of[npos[n]]["unit"]]["ctrl"] for n in nodes if npos[n] in ring_of and ring_of[npos[n]]["unit"] in unit_ctrl})
    sites.append({"c": [round(c[0], 1), round(c[1], 1)], "ue": ue(c), "score": round(score, 2), "major": major,
                  "nodes": len(nodes), "legs": len(legs), "internal": len(internal),
                  "internal_m": round(sum(E[i]["_L"] for i in internal), 1), "min_angle": round(min_ang),
                  "acute": acute, "stubs": stubs, "deadends_120m": len(dead), "overlap_m2": round(overlap),
                  "apron_m2": round(apron), "apron_span_m": round(span), "traps": len(traps), "off_main_scc": len(off_main),
                  "unreachable_moves": unreach, "detours": detours[:8], "n_detours": len(detours),
                  "d_seam": round(dseam), "d_stitch": round(dstitch), "d_ped": round(dped), "d_bridge": round(dbr),
                  "seam_road": seamish, "austin": austin, "streets": names, "ctrl": ctrls,
                  "stitch_names": sorted({E[i]["name"] or E[i]["cls"] for _, i, _ in legs if E[i]["_seam"]} |
                                         {E[i]["name"] or E[i]["cls"] for i in internal if E[i]["_seam"]})})

sites.sort(key=lambda s: -s["score"])
for r, s in enumerate(sites, 1):
    s["rank"] = r
summary = {"tag": TAG, "roadnet": str(RN_PATH), "sites": len(sites), "major_sites": sum(s["major"] for s in sites),
           "score_total": round(sum(s["score"] for s in sites), 1),
           "multi_node_sites": sum(1 for s in sites if s["nodes"] >= 2), "sites_ge3_nodes": sum(1 for s in sites if s["nodes"] >= 3),
           "acute_pairs": sum(len(s["acute"]) for s in sites), "stubs": sum(len(s["stubs"]) for s in sites),
           "overlap_m2": round(sum(s["overlap_m2"] for s in sites)), "traps": sum(s["traps"] + s["off_main_scc"] for s in sites),
           "unreachable_moves": sum(s["unreachable_moves"] for s in sites), "detours": sum(s["n_detours"] for s in sites),
           "traffic_main_scc": f"{len(MAIN)} of {DG.number_of_nodes()}",
           "dead_ends_network": sum(1 for n in kind if kind[n] == "deadend")}
json.dump({"summary": summary, "score_weights": SCORE, "sites": sites}, open(OUTD / f"audit_{TAG}.json", "w"), indent=1)
print(json.dumps(summary, indent=1))
for s in sites[:40]:
    print(f"#{s['rank']:2d} {s['score']:6.1f} c={s['c']} ue={s['ue']} n={s['nodes']} legs={s['legs']} ang={s['min_angle']} "
          f"acute={len(s['acute'])} stubs={len(s['stubs'])} dead={s['deadends_120m']} ovl={s['overlap_m2']} apron={s['apron_m2']} "
          f"traps={s['traps']}+{s['off_main_scc']} unr={s['unreachable_moves']} det={s['n_detours']} seam={s['d_seam']} "
          f"st={s['d_stitch']} ped={s['d_ped']} {'/'.join(s['streets'])[:90]}")

# ---------------------------------------------------------------- renders
if NREN or SITES_FROM:
    water = PLAN["water"]["outer"]
    BLD = json.load(open(ROOT / "Saved/Mashup/buildings_v3.json"))["buildings"]
    bl = []
    for b in BLD:
        a = math.radians(b["yaw"]); ca, sa = math.cos(a), math.sin(a); hw, hd = b["w"] / 2, b["d"] / 2
        bl.append([(b["x"] + sa * u + ca * v, b["y"] + ca * u - sa * v) for u, v in ((hw, hd), (-hw, hd), (-hw, -hd), (hw, -hd))])
    boxes = []
    if SITES_FROM:
        prev = json.load(open(SITES_FROM))
        for s in prev["sites"][:NREN or 20]:
            boxes.append((s["rank"], s["c"], s.get("box_r", 110)))
    else:
        for s in sites[:NREN]:
            boxes.append((s["rank"], s["c"], 110))
    for rank, c, rr in boxes:
        box = (c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr)
        probs = []
        for s in sites:
            if math.dist(s["c"], c) < rr:
                probs.append({"plan": s["c"], "kind": f"#{s['rank']} {s['score']}"})
        im = DR.render_box(D, box, 3.0, OUTD / "_tmp.png", problems=probs, water=water, buildings=bl)
        # traffic links on top (thin cyan, arrow at the far end) so loops and dead links show
        dr = ImageDraw.Draw(im)
        P = lambda p: ((p[0] - box[0]) * 3.0, (box[3] - p[1]) * 3.0)
        for l in TR["links"]:
            if not any(box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3] for p in l["p"]):
                continue
            o = l["o"][0] if l["o"] else 0.0
            pts = l["p"]
            sh = []
            for k_, p in enumerate(pts):
                a = pts[max(0, k_ - 1)]; b = pts[min(len(pts) - 1, k_ + 1)]
                t = unit((b[0] - a[0], b[1] - a[1]))
                sh.append((p[0] + t[1] * o, p[1] - t[0] * o))
            dr.line([P(p) for p in sh], fill=(0, 220, 230), width=1)
            if len(sh) >= 2:
                x, y = P(sh[-1]); t = unit((sh[-1][0] - sh[-2][0], sh[-1][1] - sh[-2][1]))
                for da in (2.6, -2.6):
                    ang = math.atan2(t[1], t[0]) + da
                    dr.line([(x, y), (x + math.cos(ang) * 7, y - math.sin(ang) * 7)], fill=(0, 220, 230), width=1)
        dr.line([P(p) for p in SEAM], fill=(255, 0, 255), width=1)
        dr.text((6, 6), f"{TAG} #{rank}  plan ({c[0]:.0f}, {c[1]:.0f})  UE ({c[1]*100:.0f}, {c[0]*100:.0f})", fill=(0, 0, 0))
        im.convert("RGB").save(OUTD / f"{TAG}_{rank:02d}.jpg", quality=82)
    (OUTD / "_tmp.png").unlink(missing_ok=True)
