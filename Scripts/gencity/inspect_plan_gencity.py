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


def heading(nodes, e, start):
    a, b = (nodes[e["a"]], nodes[e["b"]]) if start == e["a"] else (nodes[e["b"]], nodes[e["a"]])
    return math.atan2(b[1] - a[1], b[0] - a[0])


def other(e, n):
    return e["b"] if n == e["a"] else e["a"]


def inside_kind(nodes, e, kinds):
    a, b = nodes[e["a"]], nodes[e["b"]]
    x, y = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    return any(k in kinds and x0 <= x <= x1 and y0 <= y <= y1 for k, (x0, y0, x1, y1) in BOX.get("d", []))


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
        for nid in adj.get(node, []):
            if nid == path[-1][0]:
                continue
            ne = edges[nid]
            nh = heading(nodes, ne, node)
            turn = abs(math.remainder(nh - h, 2 * math.pi))
            if turn > math.radians(150):
                continue
            far = other(ne, node)
            # stay in the zone, go straight, don't drive into dead ends, don't repeat a street
            s = (score(nid) * 2.0 - turn * 1.5 + (0.5 if nid not in used else -2.0)
                 - (8.0 if len(adj.get(far, [])) <= 1 else 0.0) - (6.0 if nid in seen else 0.0)
                 - (3.0 if edges[nid]["class"] == "highway" else 0.0))
            if best is None or s > best[0]:
                best = (s, nid, nh)
        if best is None:
            break
        _s, nid, h = best
        path.append((nid, node))
        seen.add(nid)
        total += edges[nid]["len"]
        node = other(edges[nid], node)
    return path, node, total


def shortest(nodes, edges, adj, src, goals):
    """Dijkstra from node src to any node in goals; returns [(edge id, from node)]."""
    dist = {src: 0.0}
    prev = {}
    q = [(0.0, src)]
    while q:
        d, n = heapq.heappop(q)
        if n in goals:
            out = []
            while n != src:
                eid, m = prev[n]
                out.append((eid, m))
                n = m
            return list(reversed(out)), d
        if d > dist.get(n, 1e18):
            continue
        for eid in adj.get(n, []):
            m = other(edges[eid], n)
            nd = d + edges[eid]["len"]
            if nd < dist.get(m, 1e18):
                dist[m] = nd
                prev[m] = (eid, n)
                heapq.heappush(q, (nd, m))
    return None, None


def build(name, path, nodes, edges, adj, front, bridge_edges):
    pts, eds, caps = [], [], []
    dist = 0.0
    ix_count = 0
    for k, (eid, frm) in enumerate(path):
        e = edges[eid]
        to = other(e, frm)
        a, b = nodes[frm], nodes[to]
        dx, dy = (b[0] - a[0]) / e["len"], (b[1] - a[1]) / e["len"]
        rx, ry = dy, -dx                       # right of travel (plan x east, y north)
        f = front.get(eid) or {"zones": Counter(), "types": Counter(), "districts": Counter()}
        eds.append({"id": eid, "class": e["class"], "bridge": eid in bridge_edges,
                    "district": f["districts"].most_common(1)[0][0] if f["districts"] else None,
                    "zones": dict(f["zones"].most_common()), "parcel_types": [t for t, _ in f["types"].most_common(6)]})
        # the node at this edge's start: an intersection when 3+ roads meet there
        deg = len(adj.get(frm, []))
        if k > 0 and deg >= 3:
            ix_count += 1
            if ix_count % 3 == 0:
                legs = []
                for lid in adj[frm]:
                    le = edges[lid]
                    lh = heading(nodes, le, frm)
                    legs.append(round(math.degrees(math.atan2(math.sin(lh), math.cos(lh))), 1))
                cx, cy = a
                caps.append({"d": round(dist, 1), "kind": "ped", "node": frm, "at_ue": ue(cx, cy),
                             "legs_plan_deg": legs[:4], "edge_index": k})
        n = max(1, int(e["len"] // STEP_M))
        for i in range(n):
            t = i / n
            x, y = a[0] + (b[0] - a[0]) * t + rx * LANE_M, a[1] + (b[1] - a[1]) * t + ry * LANE_M
            pts.append(ue(x, y) + [round(dist + e["len"] * t, 1), k])
        dist += e["len"]
    last = path[-1]
    e = edges[last[0]]
    to = other(e, last[1])
    pts.append(ue(*nodes[to]) + [round(dist, 1), len(path) - 1])
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
            "bridges_crossed": [x["id"] for x in eds if x["bridge"]]}


def plan(bt, seed):
    placed, bridges, region = load(bt, seed)
    BOX["d"] = [(d["kind"], (min(p[0] for p in d["polygon"]), min(p[1] for p in d["polygon"]),
                             max(p[0] for p in d["polygon"]), max(p[1] for p in d["polygon"]))) for d in placed["districts"]]
    nodes, edges, adj = graph(placed)
    front = fronting(placed)
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
            goals = {edges[e]["a"] for e in bridge_edges} | {edges[e]["b"] for e in bridge_edges}
            more, _d = shortest(nodes, edges, adj, end, goals)
            if more is not None:
                path += more
                node = end
                for eid, frm in more:
                    node = other(edges[eid], frm)
                bid = next(e for e in sorted(bridge_edges) if node in (edges[e]["a"], edges[e]["b"]))
                path.append((bid, node))
                node = other(edges[bid], node)
                # and on past the bridge a little
                tail, _end, _t = walk(nodes, edges, adj, front, zones, used | {e for e, _ in path},
                                      start_eid=None, target=0.0) if False else ([], None, 0)
                for nid in adj.get(node, []):
                    if nid not in {e for e, _ in path}:
                        path.append((nid, node))
                        break
        used.update(e for e, _ in path)
        routes.append(build(name, path, nodes, edges, adj, front, bridge_edges))
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
