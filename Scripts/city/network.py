"""Road centrelines to city blocks.

draw_road stores a polyline. Roads that cross, or that end on another road, are split
here so the faces are the blocks. A face is the walk that keeps the block on the left,
which is the counter-clockwise ring. The outer, clockwise face is thrown away.

This is the engine-agnostic piece a later editor mode and the MCP link both call.
It is meant for a district at a time. The full-city graph still belongs to roadnet.py.
"""
import geom


def node_roads(roads, tol=0.04):
    """Split every road into graph edges at crossings and T junctions.

    Each edge carries the parent road's class, lanes, oneway and core flags, because
    the street section is chosen from those and not from the geometry.
    """
    segs = []
    for road in roads:
        pts = road.get("polyline") or []
        for a, b in zip(pts, pts[1:]):
            if geom.dist(a, b) < tol:
                continue
            segs.append({"a": (float(a[0]), float(a[1])), "b": (float(b[0]), float(b[1])), "road": road})
    splits = [[0.0, 1.0] for _ in segs]
    for i, s in enumerate(segs):
        for j, o in enumerate(segs):
            if i >= j:
                continue
            hit = geom.seg_hit(s["a"], s["b"], o["a"], o["b"])
            if hit is not None:
                _, t, u = hit
                if 0.002 < t < 0.998:
                    splits[i].append(t)
                if 0.002 < u < 0.998:
                    splits[j].append(u)
            for host, other, idx in ((s, o, i), (o, s, j)):
                for p in (other["a"], other["b"]):
                    t = geom.project_t(p, host["a"], host["b"])
                    if t is not None:
                        splits[idx].append(t)
    edges = []
    for s, ts in zip(segs, splits):
        clean = []
        for t in sorted(ts):
            if not clean or t - clean[-1] > 0.002:
                clean.append(t)
        pts = [geom.lerp(s["a"], s["b"], t) for t in clean]
        road = s["road"]
        for a, b in zip(pts, pts[1:]):
            if geom.dist(a, b) < tol:
                continue
            edges.append({
                "a": geom.r2(a), "b": geom.r2(b),
                "road_id": road["id"],
                "cls": road.get("cls") or "minor",
                "lanes": int(road.get("lanes") or 2),
                "oneway": bool(road.get("oneway")),
                "core": bool(road.get("core")),
                "name": road.get("name") or "",
                "district_id": road.get("district_id"),
            })
    return edges


def faces(edges, min_area=40.0, max_area=400000.0):
    """Counter-clockwise block faces. Each face is {polygon, edges}."""
    outgoing = {}
    for e in edges:
        outgoing.setdefault(e["a"], []).append(e)
        rev = {
            "a": e["b"], "b": e["a"], "road_id": e["road_id"], "cls": e["cls"],
            "lanes": e["lanes"], "oneway": e["oneway"], "core": e["core"],
            "name": e["name"], "district_id": e["district_id"], "_rev": True,
        }
        outgoing.setdefault(e["b"], []).append(rev)
    for node, outs in outgoing.items():
        outs.sort(key=lambda e: _angle(node, e["b"]))
    unused = set()
    index = {}
    for node, outs in outgoing.items():
        for i, e in enumerate(outs):
            key = (e["a"], e["b"], e["road_id"])
            # parallel duplicates: include the slot
            key = (e["a"], e["b"], e["road_id"], i)
            e["_key"] = key
            index[key] = (node, i)
            unused.add(key)

    found = []
    seen_rings = set()
    while unused:
        start = min(unused)
        key = start
        ring_pts = []
        ring_edges = []
        guard = 0
        while key in unused and guard < 10000:
            guard += 1
            unused.discard(key)
            node, i = index[key]
            e = outgoing[node][i]
            ring_pts.append(e["a"])
            ring_edges.append(e)
            # arrive at e["b"] along e. Leave by the clockwise-next outgoing,
            # which is the previous edge in the CCW-sorted star. Interior stays left.
            nxt_node = e["b"]
            outs = outgoing[nxt_node]
            rev_i = None
            for k, cand in enumerate(outs):
                if cand["b"] == e["a"] and cand["road_id"] == e["road_id"]:
                    rev_i = k
                    break
            if rev_i is None:
                break
            nxt = outs[(rev_i - 1) % len(outs)]
            key = nxt["_key"]
            if key == start:
                break
        else:
            continue
        if len(ring_pts) < 3 or len(ring_pts) != len(ring_edges):
            continue
        # Keep the walk order. canon_ring is only the identity of the face; rotating
        # the polygon here would assign a side street's width to the avenue.
        raw = [geom.r2(p) for p in ring_pts]
        area = geom.poly_area(raw)
        if area < min_area or area > max_area:
            continue
        sig = tuple(geom.canon_ring(raw))
        if sig in seen_rings:
            continue
        seen_rings.add(sig)
        found.append({
            "polygon": raw,
            "edges": _unique_sides(ring_edges),
            "area": round(area, 2),
            "key": sig,
        })
    return found


def _unique_sides(ring_edges):
    """One record per side of the face, walking order, forward along the face."""
    out = []
    for e in ring_edges:
        out.append({
            "road_id": e["road_id"], "a": list(e["a"]), "b": list(e["b"]),
            "cls": e["cls"], "lanes": e["lanes"], "oneway": e["oneway"],
            "core": e["core"], "name": e["name"], "district_id": e["district_id"],
        })
    return out


def _angle(a, b):
    return __import__("math").atan2(b[1] - a[1], b[0] - a[0])
