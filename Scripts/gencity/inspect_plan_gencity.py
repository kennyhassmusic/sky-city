"""Plan the inspection drives on a generated city (plain Python): five routes along the road graph, each through one
part of the city, with the capture points that inspect_gencity_ue.py drives and shoots for the review agents.
  python3 -I Scripts/gencity/inspect_plan_gencity.py --bt <building-types worktree> --seed 7
Reads <bt>/Saved/CityGen/pipeline/seed-<N>/placed_city.json (roads, parcels with building types, districts) and
<bt>/Saved/CityGen/bridges_<region>.json; writes Saved/GenCity/inspect_<region>.json:
  routes[]: name, path (points every 4 m, 1.7 m right of the centre line: the inner travel lane, clear of parked cars),
            each point [ue_x, ue_y, dist_m, edge_index]; edges[] (id, class, district, zones, parcel types);
            caps[]: capture points by distance (chase every 40 m, forward every 80 m, a 4-way pedestrian set at every
            3rd intersection), target speeds (35 mph, 15 near a turn)
Routes: downtown grid, suburbs/houses, industrial, civic + the river with one bridge crossing, county farmland.
A route walks from the edge its zone fronts most, at each node taking the unvisited edge that fronts most of its zone
(straight ahead preferred), to about 1.1 km; civic then takes the shortest way to a bridge and crosses it.
A route never U-turns (no edge straight back, no turn over MAX_TURN_DEG at a node; a dead end ends the route) and never
drives an edge twice. Corners get fillet points (FILLET_RIGHT_M / FILLET_LEFT_M on the lane line) so pure pursuit
doesn't cut toward the centre line. Pedestrian cameras stand on the sidewalk corner: each leg's half width (curb to
curb / 2, street_section's rule) + PED_CURB_M from the curb, checked against every leg at the node. Signal masts from
<bt>/Saved/CityGen/props_<region>.json near the route go in routes[].masts_ue for the chase-camera nudge.
Tests: python3 -I Scripts/gencity/test_inspect_plan_gencity.py
"""
import argparse
import heapq
import json
import math
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# route, zones it follows, district kinds it keeps to (edge midpoints inside them score extra)
ROUTES = (("downtown", ("downtown_core",), ("downtown",)), ("suburbs", ("residential",), ("residential",)),
          ("industrial", ("industrial",), ("residential", "downtown")), ("civic_river", ("civic", "park"), ("residential",)),
          ("farmland", ("rural",), ("mixed",)))
BOX = {}
LANE_M = 1.7
STEP_M = 4.0
TARGET_M = 1400.0
LOOKAHEAD = 4                   # walk(): prefer edges that go on legally this many more edges
MAX_TURN_DEG = 150.0            # a sharper turn at a node is a U-turn: never taken
FILLET_RIGHT_M = 6.0            # lane-line radius of a right turn (inside of the corner) ...
FILLET_LEFT_M = 9.0             # ... and of a left turn (across the intersection)
FILLET_MIN_DEG = 4.0            # straighter than this: no fillet
ARC_STEP_DEG = 15.0             # one fillet point per this much turn
PED_CURB_M = 2.0                # pedestrian camera: this far behind the curb
PED_EYE_M = 1.7
# Camera clearance (v9 review: ped and STOP-corner cameras inside signal poles, bollards and walls). The UE scripts
# sweep a CAM_PROBE_M sphere from an open-air point (the junction's centre at eye height; the sign's face side) to
# the camera; on a hit the camera comes forward to CAM_CLEAR_M short of it (clear_camera), and a view left closer
# than CAM_MIN_M to that point is skipped rather than shot from inside something.
CAM_PROBE_M = 0.25
CAM_CLEAR_M = 0.4
CAM_MIN_M = 2.0
MAST_NEAR_M = 40.0              # signal masts within this of the route go to the UE script
# chase camera (inspect_gencity_ue.py drives the car's fixed test camera with these)
CHASE_DIST_M = 9.0
CHASE_ELEV_DEG = 13.0
CHASE_MAX_Z_M = 4.5             # signal heads hang at 5-6 m: the camera stays under them
CHASE_PIVOT_M = 1.8             # the test camera's height at elev 0 (SkysterCar: Up * 1.0 + 0.5), + 0.3 m CamLift margin
MAST_REACH_M = 10.0             # a mast arm reaches about this far from its pole, in any direction we don't know
MAST_CLEAR_M = 3.0              # ... and the camera keeps this clear of that reach, or tucks in low and close
TUCK_DIST_M = 6.5
TUCK_MAX_Z_M = 3.2
# street_section.py (BuildingTypes Scripts/city): curb-to-curb width by class and context
SS_LANE_M = 3.5
SS_ROAD_EXTRA = 2.0
SS_DEFAULT_LANES = {"highway": 4, "arterial": 4, "collector": 2, "local": 2}
SS_PARK_LANE = 2.4
SS_PARK_CLASSES = ("local", "collector")
SS_PARK_CONTEXTS = ("downtown", "commercial", "residential", "civic", "industrial")
SS_TRAVEL = {"local": 3.1, "collector": 3.6}


def ue(x, y):
    return [round(y * 100.0, 1), round(x * 100.0, 1)]


def load(bt, seed):
    saved = os.path.join(bt, "Saved", "CityGen")
    placed = json.load(open(os.path.join(saved, "pipeline", "seed-%d" % seed, "placed_city.json")))
    region = "seed%d_city" % seed
    bpath = os.path.join(saved, "bridges_%s.json" % region)
    bridges = json.load(open(bpath)).get("bridges", []) if os.path.isfile(bpath) else []
    return placed, bridges, region


def graph(placed):
    nodes = {n["id"]: (float(n["at"][0]), float(n["at"][1])) for n in placed["roads"]["nodes"]}
    edges = {}
    adj = {}
    for e in placed["roads"]["edges"]:
        if e.get("class") == "alley" or e["a"] not in nodes or e["b"] not in nodes:
            continue
        a, b = nodes[e["a"]], nodes[e["b"]]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1.0:
            continue
        edges[e["id"]] = {"id": e["id"], "a": e["a"], "b": e["b"], "class": e.get("class"), "len": L,
                          "lanes": e.get("lanes")}
        adj.setdefault(e["a"], []).append(e["id"])
        adj.setdefault(e["b"], []).append(e["id"])
    return nodes, edges, adj


def fronting(placed):
    dist = {d["id"]: "%s (%s)" % (d.get("name"), d.get("kind")) for d in placed.get("districts") or []}
    out = {}
    for p in placed.get("parcels") or []:
        f = out.setdefault(p.get("frontage_edge"), {"zones": Counter(), "types": Counter(), "districts": Counter()})
        f["zones"][p.get("zone")] += 1
        if p.get("building_type"):
            f["types"][p["building_type"]] += 1
        f["districts"][dist.get(p.get("district_id"), p.get("district_id"))] += 1
    return out


def contexts(placed):
    """edge id -> context, as street_section.contexts: the zone most of its frontage parcels have."""
    tally = {}
    for p in placed.get("parcels") or []:
        z = {"downtown_core": "downtown"}.get(p.get("zone"), p.get("zone") or "rural")
        t = tally.setdefault(p.get("frontage_edge"), {})
        t[z] = t.get(z, 0) + 1
    return {e: max(sorted(t), key=lambda k: t[k]) for e, t in tally.items()}


def road_width(e, ctx=None):
    """Curb to curb (m), street_section.width: parked town locals/collectors are lanes x travel + 2 parking lanes,
    everything else lanes x 3.5 + 2."""
    cls = e.get("class")
    lanes = int(e.get("lanes") or SS_DEFAULT_LANES.get(cls, 2))
    c = (ctx or {}).get(e["id"], "rural" if cls in ("collector", "local") else "park")
    if ctx is not None and cls in SS_PARK_CLASSES and c in SS_PARK_CONTEXTS:
        return lanes * SS_TRAVEL[cls] + 2 * SS_PARK_LANE
    return lanes * SS_LANE_M + SS_ROAD_EXTRA


def set_widths(edges, ctx):
    for e in edges.values():
        e["hw"] = road_width(e, ctx) / 2.0


def heading(nodes, e, start):
    a, b = (nodes[e["a"]], nodes[e["b"]]) if start == e["a"] else (nodes[e["b"]], nodes[e["a"]])
    return math.atan2(b[1] - a[1], b[0] - a[0])


def other(e, n):
    return e["b"] if n == e["a"] else e["a"]


def inside_kind(nodes, e, kinds):
    a, b = nodes[e["a"]], nodes[e["b"]]
    x, y = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    return any(k in kinds and x0 <= x <= x1 and y0 <= y <= y1 for k, (x0, y0, x1, y1) in BOX.get("d", []))


def onward(nodes, edges, adj, node, came, h, banned):
    """The edges a car arriving at node along edge `came` with heading h may take: not the same edge back, not one in
    banned (already driven), no turn over MAX_TURN_DEG. Yields (edge id, new heading, turn rad)."""
    for nid in adj.get(node, []):
        if nid == came or nid in banned:
            continue
        nh = heading(nodes, edges[nid], node)
        turn = abs(math.remainder(nh - h, 2 * math.pi))
        if turn > math.radians(MAX_TURN_DEG):
            continue
        yield nid, nh, turn


def goes_on_from(nodes, edges, adj, node, came, h, banned, depth):
    """True when a car at node (arrived along `came`, heading h) can drive `depth` more edges legally (no U-turn, no
    edge in banned, none twice)."""
    if depth <= 0:
        return True
    for nid, nh, _turn in onward(nodes, edges, adj, node, came, h, banned):
        if goes_on_from(nodes, edges, adj, other(edges[nid], node), nid, nh, banned | {nid}, depth - 1):
            return True
    return False


def path_heading(nodes, edges, path):
    eid, frm = path[-1]
    return heading(nodes, edges[eid], frm)


def end_node(edges, path):
    eid, frm = path[-1]
    return other(edges[eid], frm)


def route_problems(path, nodes, edges):
    """What breaks the no-U-turn / no-repeat rules on a route, as strings (empty when it is clean)."""
    out = []
    seen = set()
    for k, (eid, frm) in enumerate(path):
        if eid in seen:
            out.append("edge %s driven twice (step %d)" % (eid, k))
        seen.add(eid)
        if k == 0:
            continue
        peid, pfrm = path[k - 1]
        if frm != other(edges[peid], pfrm):
            out.append("step %d does not start where step %d ends" % (k, k - 1))
        if eid == peid:
            out.append("U-turn on %s (step %d)" % (eid, k))
            continue
        turn = abs(math.remainder(heading(nodes, edges[eid], frm) - heading(nodes, edges[peid], pfrm), 2 * math.pi))
        if turn > math.radians(MAX_TURN_DEG):
            out.append("turn of %.0f deg at %s (step %d)" % (math.degrees(turn), frm, k))
    return out


def walk(nodes, edges, adj, front, zones, used, start_eid=None, target=TARGET_M, kinds=()):
    def score(eid):
        f = front.get(eid)
        return (sum(f["zones"][z] for z in zones) if f else 0) + (6 if inside_kind(nodes, edges[eid], kinds) else -4)
    if start_eid is None:
        cands = [e for e in edges if e not in used and edges[e]["len"] >= 40]
        start_eid = max(cands, key=lambda e: (score(e) - 0.3 * sum((front.get(e) or {"zones": Counter()})["zones"].values())
                                              - (8.0 if min(len(adj.get(edges[e]["a"], [])), len(adj.get(edges[e]["b"], []))) <= 1 else 0.0), e))
    e = edges[start_eid]
    path = [(start_eid, e["a"])]
    seen = {start_eid}
    total = e["len"]
    node = e["b"]
    h = heading(nodes, e, e["a"])
    steps = 0
    while total < target and steps < 60:
        steps += 1
        best = None
        cands = list(onward(nodes, edges, adj, node, path[-1][0], h, seen))
        # look a few edges on: an edge with a legal way on past it beats one into a dead end or a pocket of them
        # (which would end the route there)
        goes_on = [c for c in cands if goes_on_from(nodes, edges, adj, other(edges[c[0]], node), c[0], c[1],
                                                    seen | {c[0]}, LOOKAHEAD)]
        for nid, nh, turn in goes_on or cands:
            far = other(edges[nid], node)
            # stay in the zone, go straight, don't drive into dead ends; repeats and U-turns are never candidates
            s = (score(nid) * 2.0 - turn * 1.5 + (0.5 if nid not in used else -2.0)
                 - (8.0 if len(adj.get(far, [])) <= 1 else 0.0)
                 - (3.0 if edges[nid]["class"] == "highway" else 0.0))
            if best is None or s > best[0]:
                best = (s, nid, nh)
        if best is None:                   # a dead end (or every way on is driven): the route ends here
            break
        _s, nid, h = best
        path.append((nid, node))
        seen.add(nid)
        total += edges[nid]["len"]
        node = other(edges[nid], node)
    return path, node, total


def shortest(nodes, edges, adj, src, goals, came=None, h=None, banned=(), goal_edges=()):
    """Dijkstra from node src (arrived along edge `came` with heading h, if any) to any node in goals, over (node,
    incoming edge) states so no step U-turns or turns over MAX_TURN_DEG, never using an edge in banned and never the
    same edge twice; or, with goal_edges, until it has driven one of those edges; returns ([(edge id, from node)], length) or (None, None)."""
    start = (src, came)
    dist = {start: 0.0}
    prev = {}
    q = [(0.0, 0, src, came)]
    tie = 1
    while q:
        d, _t, n, ce = heapq.heappop(q)
        if d > dist.get((n, ce), 1e18):
            continue
        if (n in goals or ce in goal_edges) and (n, ce) != start:
            out = []
            st = (n, ce)
            while st != start:
                pst, eid = prev[st]
                out.append((eid, pst[0]))
                st = pst
            out.reverse()
            if len({e for e, _ in out}) == len(out):
                return out, d
            continue
        pst = prev.get((n, ce))
        hh = heading(nodes, edges[ce], pst[0][0]) if pst else h
        # edges already on the way here are banned too (no repeat within the leg)
        on_way = set()
        st = (n, ce)
        while st in prev:
            st, e0 = prev[st]
            on_way.add(e0)
        for eid in adj.get(n, []):
            if eid in banned or eid in on_way or eid == ce:
                continue
            if hh is not None:
                turn = abs(math.remainder(heading(nodes, edges[eid], n) - hh, 2 * math.pi))
                if turn > math.radians(MAX_TURN_DEG):
                    continue
            m = other(edges[eid], n)
            nd = d + edges[eid]["len"]
            if nd < dist.get((m, eid), 1e18):
                dist[(m, eid)] = nd
                prev[(m, eid)] = ((n, ce), eid)
                heapq.heappush(q, (nd, tie, m, eid))
                tie += 1
    return None, None


def _norm(x, y):
    L = math.hypot(x, y)
    return (x / L, y / L) if L > 1e-9 else (0.0, 0.0)


def lane_path(path, nodes, edges, lane=LANE_M, step=STEP_M):
    """The driven line: the centre line offset `lane` m to the right of travel (mitred at nodes, so the offset stays
    the same through a corner), each corner replaced by a fillet arc (FILLET_RIGHT_M / FILLET_LEFT_M, cut down so
    the tangent lengths fit in the segments), straights split every `step` m.
    Returns [[x, y, dist, k]] in plan metres; dist runs along the centre line (nodes at their centre-line distance),
    k is the index of the path step (edge) the point belongs to."""
    vs = [nodes[path[0][1]]]
    cum = [0.0]
    for eid, frm in path:
        vs.append(nodes[other(edges[eid], frm)])
        cum.append(cum[-1] + edges[eid]["len"])
    n = len(path)
    ds = [_norm(vs[i + 1][0] - vs[i][0], vs[i + 1][1] - vs[i][1]) for i in range(n)]
    rs = [(d[1], -d[0]) for d in ds]                    # right of travel (plan x east, y north)
    off = [(vs[0][0] + rs[0][0] * lane, vs[0][1] + rs[0][1] * lane)]
    for i in range(1, n):
        d0, d1, r0, r1 = ds[i - 1], ds[i], rs[i - 1], rs[i]
        # the two offset lines meet at v + m, with m along the bisector of the right normals
        bx, by = _norm(r0[0] + r1[0], r0[1] + r1[1])
        c = bx * r0[0] + by * r0[1]
        m = lane / c if c > 0.2 else lane
        off.append((vs[i][0] + bx * m, vs[i][1] + by * m))
    off.append((vs[n][0] + rs[n - 1][0] * lane, vs[n][1] + rs[n - 1][1] * lane))
    seg = [math.hypot(off[i + 1][0] - off[i][0], off[i + 1][1] - off[i][1]) for i in range(n)]
    # corners: (tangent in, arc points, tangent out) per interior vertex
    corners = {}
    for i in range(1, n):
        d0, d1 = ds[i - 1], ds[i]
        cross = d0[0] * d1[1] - d0[1] * d1[0]
        th = abs(math.atan2(cross, d0[0] * d1[0] + d0[1] * d1[1]))
        if th < math.radians(FILLET_MIN_DEG):
            continue
        R = FILLET_LEFT_M if cross > 0 else FILLET_RIGHT_M
        t = min(R * math.tan(th / 2), 0.45 * seg[i - 1], 0.45 * seg[i])
        if t < 0.05:
            continue
        R = t / math.tan(th / 2)
        P = off[i]
        t1 = (P[0] - d0[0] * t, P[1] - d0[1] * t)
        side = 1.0 if cross > 0 else -1.0                # centre to the left of travel on a left turn
        cx, cy = t1[0] - d0[1] * R * side, t1[1] + d0[0] * R * side
        a0 = math.atan2(t1[1] - cy, t1[0] - cx)
        m = max(2, int(math.ceil(math.degrees(th) / ARC_STEP_DEG)))
        pts = []
        for j in range(m + 1):
            a = a0 + side * th * j / m
            dd = cum[i] - t + 2 * t * j / m
            pts.append([cx + math.cos(a) * R, cy + math.sin(a) * R, dd, i - 1 if dd < cum[i] else i])
        corners[i] = (t, pts)
    out = []

    def add(x, y, dd, k):
        if out and math.hypot(x - out[-1][0], y - out[-1][1]) < 0.05:
            return
        out.append([x, y, dd, k])
    for k in range(n):
        t_in = corners[k][0] if k in corners else 0.0
        t_out = corners[k + 1][0] if k + 1 in corners else 0.0
        if k in corners:
            for q in corners[k][1]:
                add(*q)
        d = ds[k]
        a = (off[k][0] + d[0] * t_in, off[k][1] + d[1] * t_in)
        L = seg[k] - t_in - t_out
        da, db = cum[k] + t_in, cum[k + 1] - t_out
        cnt = max(1, int(math.ceil(L / step))) if L > 0 else 0
        for j in range(cnt):
            f = j / cnt
            add(a[0] + d[0] * L * f, a[1] + d[1] * L * f, da + (db - da) * f, k)
    add(off[n][0], off[n][1], cum[n], n - 1)
    return out


def _seg_dist(p, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
    return math.hypot(p[0] - a[0] - vx * t, p[1] - a[1] - vy * t), t


def in_strip(p, nodes, e, margin=0.0):
    """True when plan point p is on edge e's road (within its half width + margin of the centre-line segment)."""
    d, _t = _seg_dist(p, nodes[e["a"]], nodes[e["b"]])
    return d < e["hw"] + margin


def ped_cams(node, nodes, edges, adj, max_legs=4):
    """Pedestrian-eye cameras at an intersection, one per leg (up to max_legs): on the corner behind and to the right
    of the leg, back by the right-hand street's half width + PED_CURB_M and out by the street-behind's half width +
    PED_CURB_M (the leg's own when nothing is behind), then pushed out of every leg's road strip. Each looks down its
    leg (at a point 40 m out). Returns [{"leg", "plan_deg", "at_plan", "at_ue", "yaw"}]."""
    c = nodes[node]
    legs = [(lid, heading(nodes, edges[lid], node)) for lid in adj.get(node, [])]

    def nearest(h):
        best = None
        for lid, lh in legs:
            diff = abs(math.remainder(lh - h, 2 * math.pi))
            if diff < math.radians(50) and (best is None or diff < best[0]):
                best = (diff, lid)
        return best[1] if best else None
    out = []
    for lid, lh in legs[:max_legs]:
        d = (math.cos(lh), math.sin(lh))
        r = (d[1], -d[0])
        behind = nearest(lh + math.pi)
        right = nearest(lh - math.pi / 2)
        side = edges[behind if behind is not None else lid]["hw"] + PED_CURB_M
        back = (edges[right]["hw"] if right is not None else 0.0) + PED_CURB_M
        p = [c[0] - d[0] * back + r[0] * side, c[1] - d[1] * back + r[1] * side]
        for _ in range(12):
            moved = False
            for oid, _oh in legs:
                e = edges[oid]
                a, b = nodes[e["a"]], nodes[e["b"]]
                dist, t = _seg_dist(p, a, b)
                need = e["hw"] + PED_CURB_M
                if dist >= need - 1e-6:
                    continue
                foot = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                ux, uy = _norm(p[0] - foot[0], p[1] - foot[1])
                if ux == 0.0 and uy == 0.0:
                    ux, uy = r
                p = [foot[0] + ux * need, foot[1] + uy * need]
                moved = True
            if not moved:
                break
        aim = (c[0] + d[0] * 40.0, c[1] + d[1] * 40.0)
        yaw = math.degrees(math.atan2(aim[0] - p[0], aim[1] - p[1]))   # UE yaw: X = plan north, Y = plan east
        out.append({"leg": lid, "plan_deg": round(math.degrees(math.remainder(lh, 2 * math.pi)), 1),
                    "at_plan": [round(p[0], 2), round(p[1], 2)], "at_ue": ue(p[0], p[1]), "yaw": round(yaw, 2)})
    return out


def clear_camera(origin, cam, hit_m, clear_m=CAM_CLEAR_M, min_m=CAM_MIN_M):
    """Where a camera may stand on the line from an open-air origin to its planned spot cam ((x, y, z) UE cm each),
    given hit_m, the distance (m) along that line to the first blocking hit (None: clear). -> (spot, moved_m), or
    (None, moved_m) when the clear part of the line is shorter than min_m (skip the view)."""
    d = [cam[k] - origin[k] for k in range(3)]
    length = math.sqrt(sum(c * c for c in d)) / 100.0
    if hit_m is None or hit_m >= length or length <= 0.0:
        return tuple(cam), 0.0
    keep = hit_m - clear_m
    if keep < min_m:
        return None, round(length - max(keep, 0.0), 2)
    f = keep / length
    return tuple(origin[k] + d[k] * f for k in range(3)), round(length - keep, 2)


def chase_cam(car_ue, yaw_deg, masts_ue, dist=CHASE_DIST_M, elev=CHASE_ELEV_DEG):
    """The car's fixed chase camera (TestCamDist / TestCamElev) for this spot: at most CHASE_MAX_Z_M up, under the
    signal heads (5-6 m); with a signal mast pole within MAST_REACH_M + MAST_CLEAR_M of the camera or the car, tucked
    in (TUCK_DIST_M) and lower still (TUCK_MAX_Z_M), so the boom passes under the mast arm. UE cm in, -> (dist m,
    elev deg, height m, tucked)."""
    r = math.radians(yaw_deg)
    near = (MAST_REACH_M + MAST_CLEAR_M) * 100.0
    cam = (car_ue[0] - math.cos(r) * dist * 100.0, car_ue[1] - math.sin(r) * dist * 100.0)
    tucked = any(math.hypot(m[0] - cam[0], m[1] - cam[1]) < near or math.hypot(m[0] - car_ue[0], m[1] - car_ue[1]) < near
                 for m in masts_ue)
    top = CHASE_MAX_Z_M
    if tucked:
        dist, top = min(dist, TUCK_DIST_M), TUCK_MAX_Z_M
    s = max(-1.0, min(1.0, (top - CHASE_PIVOT_M) / dist))
    elev = min(elev, math.degrees(math.asin(s)))
    return dist, elev, CHASE_PIVOT_M + dist * math.sin(math.radians(elev)), tucked


def masts_near(masts_ue, pts_ue, radius_m=MAST_NEAR_M):
    """The masts (UE cm [x, y]) within radius_m of any path point."""
    cell = radius_m * 100.0
    grid = {}
    for p in pts_ue:
        grid.setdefault((int(p[0] // cell), int(p[1] // cell)), []).append(p)
    out = []
    for m in masts_ue:
        gx, gy = int(m[0] // cell), int(m[1] // cell)
        if any(math.hypot(p[0] - m[0], p[1] - m[1]) <= cell
               for i in (-1, 0, 1) for j in (-1, 0, 1) for p in grid.get((gx + i, gy + j), [])):
            out.append([round(m[0], 1), round(m[1], 1)])
    return out


def build(name, path, nodes, edges, adj, front, bridge_edges, masts_ue=()):
    eds, caps = [], []
    dist = 0.0
    ix_count = 0
    for k, (eid, frm) in enumerate(path):
        e = edges[eid]
        f = front.get(eid) or {"zones": Counter(), "types": Counter(), "districts": Counter()}
        eds.append({"id": eid, "class": e["class"], "bridge": eid in bridge_edges, "hw": round(e.get("hw", 0.0), 2),
                    "district": f["districts"].most_common(1)[0][0] if f["districts"] else None,
                    "zones": dict(f["zones"].most_common()), "parcel_types": [t for t, _ in f["types"].most_common(6)]})
        # the node at this edge's start: an intersection when 3+ roads meet there
        deg = len(adj.get(frm, []))
        if k > 0 and deg >= 3:
            ix_count += 1
            if ix_count % 3 == 0:
                cams = ped_cams(frm, nodes, edges, adj)
                cx, cy = nodes[frm]
                caps.append({"d": round(dist, 1), "kind": "ped", "node": frm, "at_ue": ue(cx, cy),
                             "legs_plan_deg": [c["plan_deg"] for c in cams], "cams": cams, "edge_index": k})
        dist += e["len"]
    pts = [ue(x, y) + [round(dd, 1), k] for x, y, dd, k in lane_path(path, nodes, edges)]
    d = 40.0
    while d < dist - 10:
        caps.append({"d": d, "kind": "chase"})
        if int(round(d)) % 80 == 0:
            caps.append({"d": d + 0.1, "kind": "fwd"})
        d += 40.0
    caps.sort(key=lambda c: c["d"])
    # slow points: 15 mph from 25 m before a turn of more than 30 degrees
    slow = []
    for k in range(1, len(path)):
        e0, f0 = edges[path[k - 1][0]], path[k - 1][1]
        e1, f1 = edges[path[k][0]], path[k][1]
        turn = abs(math.remainder(heading(nodes, e1, f1) - heading(nodes, e0, f0), 2 * math.pi))
        if turn > math.radians(30):
            at = sum(edges[p[0]]["len"] for p in path[:k])
            slow.append([round(at - 25.0, 1), round(at + 8.0, 1)])
    p0, p1 = pts[0], pts[min(3, len(pts) - 1)]
    yaw = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
    return {"name": name, "length_m": round(dist, 1), "start_ue": p0[:2], "start_yaw": round(yaw, 2),
            "path": pts, "edges": eds, "caps": caps, "slow": slow, "intersections": ix_count,
            "bridges_crossed": [x["id"] for x in eds if x["bridge"]], "problems": route_problems(path, nodes, edges),
            "masts_ue": masts_near(masts_ue, pts)}


# --- drive-time helpers for inspect_gencity_ue.py (plain Python, so they're tested here) ----------------------------

HOLD_S = 1.5                    # after a teleport: game seconds held still on the brake ...
STEER_IN_S = 0.3                # ... then this long steering (pure pursuit) with the brake still on, then drive
HOLD_CONTROLS = (("test_throttle", 0.0), ("test_steer", 0.0), ("test_brake", 1.0), ("test_stop", 1.0),
                 ("test_boost", False), ("test_jump", False), ("test_slide", False))


def hold_controls(pawn):
    """Zero throttle and steer, full brake and the stop button (the Skyster's handbrake), nothing else pressed."""
    for k, v in HOLD_CONTROLS:
        pawn.set_editor_property(k, v)


def zero_velocity(pawn, zero_vec):
    """Zero the pawn's physics linear and angular velocity when its root simulates physics (the Skyster's own sim
    already zeroes Vel and W in SpawnAt / TestTeleport). Returns True when a physics body was zeroed."""
    root = getattr(pawn, "root_component", None)
    if root is None and hasattr(pawn, "get_root_component"):
        root = pawn.get_root_component()
    try:
        if root is None or not root.is_simulating_physics():
            return False
        root.set_physics_linear_velocity(zero_vec, False)
        root.set_physics_angular_velocity_in_degrees(zero_vec, False)
        return True
    except AttributeError:
        return False


def teleport_reset(pawn, now_game, zero_vec, hold_s=HOLD_S):
    """Around a teleport: controls to hold (no throttle/steer, full brake + stop), velocity zeroed; returns the game
    time the hold ends (drive() keeps holding until then: hold_phase)."""
    hold_controls(pawn)
    zero_velocity(pawn, zero_vec)
    return now_game + hold_s


def hold_phase(now_game, hold_until, steer_in_s=STEER_IN_S):
    """'hold' (keep the hold controls on), 'steer' (pure pursuit steers, brake still on, no throttle) or 'drive'."""
    if hold_until is None:
        return "drive"
    if now_game < hold_until:
        return "hold"
    if now_game < hold_until + steer_in_s:
        return "steer"
    return "drive"


def load_masts(bt, region):
    """Signal mast poles (UE cm [x, y]) from <bt>/Saved/CityGen/props_<region>.json, or [] without it."""
    path = os.path.join(bt, "Saved", "CityGen", "props_%s.json" % region)
    if not os.path.isfile(path):
        return []
    groups = json.load(open(path)).get("groups") or {}
    return [[r[0], r[1]] for k, rows in groups.items() if k.startswith("KIT_SS_SignalMast") for r in rows]


def to_bridge(nodes, edges, adj, path, bridge_edges):
    """Carry a route on from its end the shortest legal way (no U-turn, no repeat) onto a bridge edge, across it, and
    one edge past it (the straightest legal one). Returns the longer path (or the same one when no way exists)."""
    if any(e in bridge_edges for e, _ in path):
        return path
    driven = {e for e, _ in path}
    more, _d = shortest(nodes, edges, adj, end_node(edges, path), set(), came=path[-1][0],
                        h=path_heading(nodes, edges, path), banned=driven, goal_edges=set(bridge_edges))
    best = path + more if more else None
    if best is None:
        return path
    node = end_node(edges, best)
    nxt = sorted(onward(nodes, edges, adj, node, best[-1][0], path_heading(nodes, edges, best), {e for e, _ in best}),
                 key=lambda t: t[2])
    if nxt:
        best.append((nxt[0][0], node))
    return best


def plan(bt, seed):
    placed, bridges, region = load(bt, seed)
    BOX["d"] = [(d["kind"], (min(p[0] for p in d["polygon"]), min(p[1] for p in d["polygon"]),
                             max(p[0] for p in d["polygon"]), max(p[1] for p in d["polygon"]))) for d in placed["districts"]]
    nodes, edges, adj = graph(placed)
    set_widths(edges, contexts(placed))
    front = fronting(placed)
    masts = load_masts(bt, region)
    bridge_edges = set()
    for b in bridges:
        if b.get("kind") == "girder":
            bridge_edges.update(r for r in b.get("roads") or [] if r in edges)
    used = set()
    routes = []
    for name, zones, kinds in ROUTES:
        target = 900.0 if name == "civic_river" else TARGET_M
        path, end, total = walk(nodes, edges, adj, front, zones, used, target=target, kinds=kinds)
        if name == "civic_river" and bridge_edges:
            path = to_bridge(nodes, edges, adj, path, bridge_edges)
        used.update(e for e, _ in path)
        routes.append(build(name, path, nodes, edges, adj, front, bridge_edges, masts))
    return {"region": region, "seed": seed, "lane_offset_m": LANE_M, "routes": routes}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bt", required=True)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    out = plan(a.bt, a.seed)
    path = os.path.join(ROOT, "Saved", "GenCity", "inspect_%s.json" % out["region"])
    with open(path, "w") as h:
        json.dump(out, h, indent=1)
    for r in out["routes"]:
        n = Counter(c["kind"] for c in r["caps"])
        print("%-12s %6.0f m  edges %2d  intersections %2d  caps %s  frames %d  bridges %s" % (
            r["name"], r["length_m"], len(r["edges"]), r["intersections"], dict(n),
            n["chase"] + n["fwd"] + 4 * n["ped"], r["bridges_crossed"]))
    print(path)


if __name__ == "__main__":
    main()
