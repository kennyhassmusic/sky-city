"""Streetscape from a city model's roads and blocks.

Every road gets the cross-section in Scripts/roads/profiles.py: carriageway, gutter
pan, beveled curb, sidewalk, and a grass parkway where the section calls for one.
Junctions get a curb return, a crosswalk (continental, or ladder on a local street)
and a curb ramp. The crossing sits past the return so the paint is on asphalt.
Lane lines, edge lines and stop bars are part of the same data. Furniture is placed
by spacing, not by hand: lamps, trees of the district's species, drains on the gutter
line, hydrants and benches. Nothing is placed in the roadway or in the crosswalk.

The output is data. Blender and, later, the editor sweep meshes along it.
"""
import math
import sys
from pathlib import Path

import geom

_ROADS = Path(__file__).resolve().parents[1] / "roads"
if str(_ROADS) not in sys.path:
    sys.path.insert(0, str(_ROADS))
import profiles  # noqa: E402


def build(model):
    """Full streetscape for every road. District id is stamped on each piece."""
    roads = model.get("roads") or []
    sections = {r["id"]: profiles.preview_section(r.get("cls") or "minor", r.get("lanes") or 2,
                                                   bool(r.get("oneway")), bool(r.get("core")))
                for r in roads}
    junctions = _junctions(roads)
    surfaces = {"asphalt": [], "gutter": [], "sidewalk": [], "parkway": [], "alley": []}
    curb_paths = []
    crosswalks = []
    ramps = []
    markings = []
    props = []
    blocks_out = []

    for road in roads:
        sec = sections[road["id"]]
        _lay_road(model, road, sec, junctions, surfaces, curb_paths, crosswalks, ramps, props, markings)

    for block in model.get("blocks") or []:
        loop = _block_curb(block, sections)
        if loop:
            curb_paths.append(loop)
            blocks_out.append({"block_id": block["id"], "district_id": block.get("district_id"),
                               "flow": [list(geom.r2(p)) for p in loop["polyline"]]})
        alley = block.get("alley")
        if alley:
            surfaces["alley"].append({"polygon": alley, "district_id": block.get("district_id"),
                                      "block_id": block["id"]})
            _alley_bollards(model, block, props)

    return {
        "version": 1,
        "sections": {k: _public_section(v) for k, v in sections.items()},
        "surfaces": surfaces,
        "curb_paths": curb_paths,
        "crosswalks": crosswalks,
        "ramps": ramps,
        "markings": markings,
        "props": props,
        "blocks": blocks_out,
    }


def point_on_road(road, s, lateral):
    """A point `s` metres along the centreline, `lateral` metres to the left."""
    pts = [(float(p[0]), float(p[1])) for p in road["polyline"]]
    total = sum(geom.dist(a, b) for a, b in zip(pts, pts[1:])) or 1e-6
    s = max(0.0, min(total, s))
    walked = 0.0
    for a, b in zip(pts, pts[1:]):
        L = geom.dist(a, b)
        if walked + L >= s - 1e-8:
            t = (s - walked) / (L or 1)
            p = geom.lerp(a, b, t)
            d = geom.unit(geom.sub(b, a))
            left = (-d[1], d[0])
            return geom.add(p, geom.mul(left, lateral)), d
        walked += L
    d = geom.unit(geom.sub(pts[-1], pts[-2]))
    return geom.add(pts[-1], geom.mul((-d[1], d[0]), lateral)), d


def inner_sign(road, toward):
    """+1 if the block lies to the left of the centreline."""
    pts = road["polyline"]
    a, b = (float(pts[0][0]), float(pts[0][1])), (float(pts[-1][0]), float(pts[-1][1]))
    mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    d = geom.unit(geom.sub(b, a))
    left = (-d[1], d[0])
    v = (float(toward[0]) - mid[0], float(toward[1]) - mid[1])
    return 1.0 if geom.dot(v, left) >= 0 else -1.0


def _lay_road(model, road, sec, junctions, surfaces, curb_paths, crosswalks, ramps, props, markings):
    pts = [(float(p[0]), float(p[1])) for p in road["polyline"]]
    if len(pts) < 2:
        return
    length = sum(geom.dist(a, b) for a, b in zip(pts, pts[1:]))
    W = sec["width"]
    district = road.get("district_id") or _district_of(model, pts[len(pts) // 2])
    # asphalt is the carriageway, curb face to curb face
    surfaces["asphalt"].append({
        "polygon": _ribbon(pts, W / 2.0, W / 2.0),
        "road_id": road["id"], "district_id": district,
    })
    gutter_w = (sec.get("gutter") or {}).get("width_m") or 0.0
    for side in (1.0, -1.0):
        if gutter_w > 0:
            outer = side * (W / 2.0)
            inner = side * (W / 2.0 - gutter_w)
            surfaces["gutter"].append({
                "polygon": _ribbon_sides(pts, outer, inner),
                "road_id": road["id"], "district_id": district, "side": side,
            })
        back = profiles.curb_back_from_flow(road.get("cls") or "minor")
        walk = sec["sidewalk"]
        # sidewalk starts at the back of the curb and runs away from the carriageway
        near = side * (W / 2.0 + back)
        far = side * (W / 2.0 + back + walk)
        if sec["parkway"]:
            grass_far = side * (W / 2.0 + back + sec["parkway_w"])
            surfaces["parkway"].append({
                "polygon": _ribbon_sides(pts, near, grass_far),
                "road_id": road["id"], "district_id": district, "side": side,
            })
            surfaces["sidewalk"].append({
                "polygon": _ribbon_sides(pts, grass_far, far),
                "road_id": road["id"], "district_id": district, "side": side,
            })
        elif walk > 0:
            surfaces["sidewalk"].append({
                "polygon": _ribbon_sides(pts, near, far),
                "road_id": road["id"], "district_id": district, "side": side,
            })
        # straight curb, trimmed before a junction so the return arc can take the corner
        trim = _end_trim(pts, junctions, sec)
        curb_paths.append({
            "kind": "straight", "road_id": road["id"], "district_id": district, "side": side,
            "polyline": _trimmed(pts, trim[0], length - trim[1]),
            "outward": side,  # +1 means the sidewalk is to the left of the centreline direction
            "cls": road.get("cls") or "minor",
        })
        _furniture(model, road, sec, side, length, trim, district, props)
    _crossings(model, road, sec, length, junctions, district, crosswalks, ramps, props, markings)
    _lane_lines(road, sec, length, junctions, district, markings)


def _block_curb(block, sections):
    """Filleted flow line of a block: the curb return at each corner."""
    ring = block.get("centreline_polygon")
    edges = block.get("edges") or []
    if not ring or len(ring) < 3 or not edges:
        return None
    # Per-edge inset from the centreline to the flow line is half the carriageway.
    dists = []
    radii = []
    for e in edges:
        sec = sections.get(e["road_id"])
        if sec is None:
            dists.append(4.0)
            radii.append(6.0)
        else:
            dists.append(sec["width"] / 2.0)
            radii.append(sec["curb"]["return_radius_m"])
    if len(dists) != len(ring):
        # a filleted or noded face can have more vertices than parent edges; use the mean
        mean = sum(dists) / len(dists)
        flow = geom.offset_polygon(ring, mean)
        radius = min(radii) if radii else 6.0
    else:
        flow = geom.offset_edges(ring, dists)
        radius = min(radii) if radii else 6.0
    rounded = geom.fillet_ring(flow, radius, n=4)
    return {
        "kind": "return", "block_id": block["id"], "district_id": block.get("district_id"),
        "polyline": [list(geom.r2(p)) for p in rounded],
        "sidewalk": "inward", "cls": "major", "radius": radius,
    }


def _furniture(model, road, sec, side, length, trim, district, props):
    trees = _trees(model, district)
    start = trim[0] + profiles.SPACING["corner_clear_m"]
    end = length - trim[1] - profiles.SPACING["corner_clear_m"]
    if end - start < 6:
        return
    cls = sec["class"]
    if cls == "expressway":
        lamp_step = 50.0
    elif cls == "arterial":
        lamp_step = profiles.SPACING["lamp_arterial_m"]
    elif cls == "collector":
        lamp_step = profiles.SPACING["lamp_collector_m"]
    else:
        lamp_step = profiles.SPACING["lamp_local_m"]
    tree_step = profiles.SPACING["tree_grate_m"] if sec["furniture_w"] else profiles.SPACING["tree_parkway_m"]
    back = profiles.curb_back_from_flow(road.get("cls") or "minor")
    # furniture sits just behind the curb, in the grate zone or the grass
    lateral = side * (sec["width"] / 2.0 + back + (sec["furniture_w"] * 0.7 if sec["furniture_w"] else sec["parkway_w"] * 0.5))
    bench_lateral = side * (sec["width"] / 2.0 + back + min(sec["sidewalk"] * 0.55, 2.2))
    seed = int(model.get("seed") or 1)
    _scatter(props, road, "lamp", start, end, lamp_step, lateral, district, seed, side)
    if trees and sec["sidewalk"] > 0:
        _scatter(props, road, "tree", start + tree_step * 0.5, end, tree_step, lateral, district, seed, side, trees=trees)
    if sec["core"]:
        _scatter(props, road, "bench", start + 12.0, end, 48.0, bench_lateral, district, seed, side)


def _scatter(props, road, kind, start, end, step, lateral, district, seed, side, trees=None):
    if step <= 0 or end <= start:
        return
    i = 0
    s = start
    # lamps on opposite sides are staggered by half a bay
    if kind == "lamp" and side < 0:
        s += step * 0.5
    while s <= end + 0.1:
        p, d = point_on_road(road, s, lateral)
        # yaw faces the carriageway, so a lamp arm reaches over the lane
        toward_road = -side
        yaw = math.degrees(math.atan2(d[1], d[0]))
        # the kit's lamp arm points to the mesh's local -Y; the placer stores the
        # centreline bearing and the side, and the mesher turns it to face the road
        item = {
            "id": "prop_%s_%s_%d_%d" % (road["id"], kind, 0 if side > 0 else 1, i),
            "kind": kind, "x": round(p[0], 2), "y": round(p[1], 2),
            "yaw": round(yaw, 1), "side": side, "toward_road": toward_road,
            "road_id": road["id"], "district_id": district,
            "source": "generated", "locked": False,
        }
        if kind == "tree" and trees:
            item["species"] = trees[int(geom.rnd(seed, item["id"]) * len(trees)) % len(trees)]
        props.append(item)
        i += 1
        s += step


def _crossings(model, road, sec, length, junctions, district, crosswalks, ramps, props, markings):
    pts = [(float(p[0]), float(p[1])) for p in road["polyline"]]
    radius = sec["curb"]["return_radius_m"]
    # The whole zebra sits on the straight asphalt, past the curb-return trim.
    inset = radius + profiles.CONTINENTAL["width_m"] / 2.0 + 0.8
    if length < inset * 2 + 6:
        return
    kind = "ladder" if (road.get("cls") or "minor") == "minor" else "continental"
    ends = []
    if _is_junction(pts[0], junctions):
        ends.append(inset)
    if _is_junction(pts[-1], junctions):
        ends.append(length - inset)
    W = sec["width"]
    back = profiles.curb_back_from_flow(road.get("cls") or "minor")
    for s in ends:
        p, d = point_on_road(road, s, 0.0)
        marks = []
        for off in profiles.continental_offsets(W):
            c = geom.add(p, geom.mul((-d[1], d[0]), off))
            marks.append({"polygon": geom.mark_rect(c, d, profiles.CONTINENTAL["width_m"], profiles.CONTINENTAL["bar_m"])})
        if kind == "ladder":
            for along, rw in profiles.ladder_rails(W):
                c = geom.add(p, geom.mul(d, along))
                marks.append({"polygon": geom.mark_rect(c, (-d[1], d[0]), W - 0.4, rw), "rail": True})
        crosswalks.append({
            "road_id": road["id"], "district_id": district, "kind": kind,
            "s": round(s, 2), "marks": marks,
        })
        # Stop bar on the mid-block side of the zebra, so it sits on asphalt with the bars.
        gap = profiles.CONTINENTAL["width_m"] / 2.0 + profiles.CONTINENTAL["stop_gap_m"]
        gap += profiles.CONTINENTAL["stop_bar_m"] / 2.0
        bar_s = s + gap if s < length / 2.0 else s - gap
        bp, bd = point_on_road(road, bar_s, 0.0)
        gutter_w = (sec.get("gutter") or {}).get("width_m") or 0.0
        markings.append({
            "kind": "stop", "road_id": road["id"], "district_id": district,
            "material": "M_LanePaint",
            "polygon": geom.mark_rect(bp, bd, profiles.CONTINENTAL["stop_bar_m"], max(1.2, W - 2.0 * gutter_w)),
        })
        # ramps on both curbs, and a drain on the gutter just upstream of the crossing
        for side in (1.0, -1.0):
            lateral = side * (W / 2.0 + back * 0.5)
            rp, _ = point_on_road(road, s, lateral)
            ramps.append({
                "x": round(rp[0], 2), "y": round(rp[1], 2),
                "yaw": round(math.degrees(math.atan2(d[1], d[0])), 1),
                "side": side, "road_id": road["id"], "district_id": district,
                "spec": profiles.curb_ramp_spec(),
            })
            upstream = s - 2.2 if s < length / 2 else s + 2.2
            gp, gd = point_on_road(road, upstream, side * (W / 2.0 - 0.25))
            props.append({
                "id": "prop_%s_drain_%d_%d" % (road["id"], 0 if side > 0 else 1, int(s)),
                "kind": "drain", "x": round(gp[0], 2), "y": round(gp[1], 2),
                "yaw": round(math.degrees(math.atan2(gd[1], gd[0])), 1),
                "side": side, "road_id": road["id"], "district_id": district,
                "source": "generated", "locked": False,
            })
        # one hydrant on the left sidewalk, just past the crossing, toward midblock
        hyd_s = s + 3.5 if s < length / 2 else s - 3.5
        hp, hd = point_on_road(road, hyd_s, (W / 2.0 + back + 1.1))
        props.append({
            "id": "prop_%s_hydrant_%d" % (road["id"], int(s)),
            "kind": "hydrant", "x": round(hp[0], 2), "y": round(hp[1], 2),
            "yaw": round(math.degrees(math.atan2(hd[1], hd[0])), 1),
            "side": 1, "road_id": road["id"], "district_id": district,
            "source": "generated", "locked": False,
        })


def _lane_lines(road, sec, length, junctions, district, markings):
    """Edge lines, a broken line between lanes, and a double centre line. White, M_LanePaint."""
    pts = [(float(p[0]), float(p[1])) for p in road["polyline"]]
    if len(pts) < 2 or length < 8:
        return
    trim = _end_trim(pts, junctions, sec)
    # Keep paint off the zebra. The crossing occupies the return plus the bar depth.
    pad = profiles.CONTINENTAL["width_m"] / 2.0 + 1.4
    s0 = trim[0] + (pad if trim[0] > 0 else 0.4)
    s1 = length - trim[1] - (pad if trim[1] > 0 else 0.4)
    if s1 - s0 < 4:
        return
    cursor = -sec["width"] / 2.0
    elems = sec["elems"]
    for index, elem in enumerate(elems):
        kind = elem[0]
        width = float(elem[1])
        if kind in ("dy", "twltl"):
            for side in (-1.0, 1.0):
                poly = _strip(pts, s0, s1, cursor + width / 2.0 + side * 0.16, 0.1)
                if poly:
                    markings.append({
                        "kind": "centre", "road_id": road["id"], "district_id": district,
                        "material": "M_LanePaint", "polygon": poly,
                    })
        if index < len(elems) - 1:
            nxt = elems[index + 1][0]
            boundary = cursor + width
            if kind in ("dy", "twltl", "barrier") or nxt in ("dy", "twltl", "barrier"):
                cursor += width
                continue
            if "gutter" in (kind, nxt) or "parking" in (kind, nxt) or "shoulder" in (kind, nxt):
                poly = _strip(pts, s0, s1, boundary, 0.12)
                if poly:
                    markings.append({
                        "kind": "edge", "road_id": road["id"], "district_id": district,
                        "material": "M_LanePaint", "polygon": poly,
                    })
            elif kind == "lane" and nxt == "lane":
                dash = 3.0
                gap = 6.0
                s = s0
                n = 0
                while s + dash <= s1 + 0.05:
                    poly = _strip(pts, s, min(s1, s + dash), boundary, 0.12)
                    if poly:
                        markings.append({
                            "kind": "dash", "road_id": road["id"], "district_id": district,
                            "material": "M_LanePaint", "polygon": poly,
                        })
                    n += 1
                    s += dash + gap
                    if n > 80:
                        break
        cursor += width


def _strip(pts, s0, s1, lateral, width):
    sub = _trimmed(pts, s0, s1)
    if len(sub) < 2:
        return None
    half = width / 2.0
    return _ribbon_sides(sub, lateral + half, lateral - half)


def _alley_bollards(model, block, props):
    alley = block.get("alley") or []
    if len(alley) < 4:
        return
    # the two shortest edges are the mouths
    n = len(alley)
    edges = []
    for i in range(n):
        a, b = alley[i], alley[(i + 1) % n]
        edges.append((geom.dist(a, b), a, b))
    edges.sort(key=lambda e: e[0])
    for k, (L, a, b) in enumerate(edges[:2]):
        mid = ((float(a[0]) + float(b[0])) / 2.0, (float(a[1]) + float(b[1])) / 2.0)
        yaw = math.degrees(math.atan2(float(b[1]) - float(a[1]), float(b[0]) - float(a[0])))
        props.append({
            "id": "prop_%s_bollard_%d" % (block["id"], k),
            "kind": "bollard", "x": round(mid[0], 2), "y": round(mid[1], 2),
            "yaw": round(yaw, 1), "district_id": block.get("district_id"),
            "block_id": block["id"], "source": "generated", "locked": False,
        })


def _trees(model, district_id):
    for d in model.get("districts") or []:
        if d["id"] == district_id:
            return list(d.get("trees") or ["linden", "elm"])
    return ["linden", "elm"]


def _district_of(model, p):
    for d in model.get("districts") or []:
        if geom.point_in_poly(p, d["polygon"]):
            return d["id"]
    return None


def _junctions(roads):
    counts = {}
    for road in roads:
        seen = set()
        for p in road.get("polyline") or []:
            key = geom.r2(p)
            if key in seen:
                continue
            seen.add(key)
            counts[key] = counts.get(key, 0) + 1
    return {p for p, n in counts.items() if n >= 2}


def _is_junction(p, junctions):
    q = geom.r2(p)
    return q in junctions or any(geom.dist(q, j) < 0.2 for j in junctions)


def _end_trim(pts, junctions, sec):
    radius = sec["curb"]["return_radius_m"]
    trim = [0.0, 0.0]
    if _is_junction(pts[0], junctions):
        trim[0] = radius
    if _is_junction(pts[-1], junctions):
        trim[1] = radius
    return trim


def _trimmed(pts, s0, s1):
    length = sum(geom.dist(a, b) for a, b in zip(pts, pts[1:]))
    s0 = max(0.0, min(length, s0))
    s1 = max(s0, min(length, s1))
    if s1 - s0 < 0.5:
        return [list(geom.r2(pts[0])), list(geom.r2(pts[-1]))]
    out = []
    walked = 0.0
    for a, b in zip(pts, pts[1:]):
        L = geom.dist(a, b) or 1e-6
        seg0, seg1 = walked, walked + L
        if seg1 >= s0 and seg0 <= s1:
            if not out:
                out.append(geom.lerp(a, b, (s0 - seg0) / L))
            if seg1 >= s1:
                out.append(geom.lerp(a, b, (s1 - seg0) / L))
                break
            out.append(b)
        walked += L
    return [list(geom.r2(p)) for p in out]


def _ribbon(pts, left, right):
    return _ribbon_sides(pts, left, -right)


def _ribbon_sides(pts, lateral_a, lateral_b):
    """A ribbon between two lateral offsets. Offsets are signed, left-positive, in metres."""
    left, right = [], []
    for i in range(len(pts)):
        d = _tangent(pts, i)
        n = (-d[1], d[0])
        left.append(geom.r2(geom.add(pts[i], geom.mul(n, lateral_a))))
        right.append(geom.r2(geom.add(pts[i], geom.mul(n, lateral_b))))
    return [list(p) for p in left + right[::-1]]


def _tangent(pts, i):
    if i == 0:
        return geom.unit(geom.sub(pts[1], pts[0]))
    if i == len(pts) - 1:
        return geom.unit(geom.sub(pts[-1], pts[-2]))
    return geom.unit(geom.sub(pts[i + 1], pts[i - 1]))


def _public_section(sec):
    return {
        "width": sec["width"], "sidewalk": sec["sidewalk"], "parkway": sec["parkway"],
        "parkway_w": sec["parkway_w"], "walk_w": sec["walk_w"],
        "elems": sec["elems"], "curb": sec["curb"], "gutter": sec["gutter"],
        "class": sec["class"],
    }
