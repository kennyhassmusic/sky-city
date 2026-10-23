"""Stage 1 road layer: dress existing centreline roads.

The city generator owns blocks, lots and buildings. This module owns the
regulatory street: signals, stop and yield signs, street-name blades, lane
arrows, the keep-clear box, parking stalls and parked cars, and bus stops.
Lamps, benches, bins and hydrants still come from the city streetscape; this
layer does not replace them. Wear is stamped from the district (or from the
lots, when they carry a tier wear) so paint and props fade together.

The input is the roads the city already drew. Stage 2 can hand the same list
over from a richer graph. See ROADMAP.md. Nothing here builds a highway,
a median, a tunnel or a rail line.

Run the checks with: python3 -I Scripts/roads/test_dressing.py
"""
import math
import zlib

import profiles

_RANK = {"minor": 1, "mid": 2, "major": 3, "highway": 4}
_STALL_M = 6.7


def rnd(*parts):
    """Same 0..1 recipe as the city geometry module, so a seed stays a seed."""
    return (zlib.crc32(repr(parts).encode()) & 0xffffffff) / 4294967296.0


def dress(model, sections):
    """Props and markings to merge into a streetscape. Deterministic in the seed."""
    roads = list(model.get("roads") or [])
    seed = int(model.get("seed") or 1)
    junctions = _junctions(roads)
    props = []
    markings = []
    for point, approaches in _groups(roads, junctions):
        _control(props, markings, point, approaches, sections, seed)
    for road in roads:
        sec = sections.get(road["id"])
        if not sec:
            continue
        _stalls_and_cars(props, markings, model, road, sec, seed)
        _bus_stops(props, road, sec, seed)
    return props, markings


def finish(markings, props, model):
    """District wear on every marking and prop, and yellow paint on the centre line.

    Centre lines are the double-yellow (or the two-way left-turn edges). Dashes,
    edges and stop bars stay white. A keep-clear box is yellow too.
    """
    wear_of = _wear_lookup(model)
    for mark in markings:
        mark["wear"] = wear_of(mark.get("district_id"))
        if mark.get("kind") in ("centre", "keep_clear"):
            mark["material"] = "M_LanePaintYellow"
    for prop in props:
        if prop.get("wear") is None:
            prop["wear"] = wear_of(prop.get("district_id"))


def _wear_lookup(model):
    by_district = {}
    for district in model.get("districts") or []:
        if district.get("wear") is not None:
            by_district[district.get("id")] = float(district["wear"])
    lots = {}
    for lot in model.get("lots") or []:
        if lot.get("wear") is None or not lot.get("district_id"):
            continue
        lots.setdefault(lot["district_id"], []).append(float(lot["wear"]))

    def wear(district_id):
        samples = lots.get(district_id)
        if samples:
            return round(sum(samples) / len(samples), 3)
        if district_id in by_district:
            return round(by_district[district_id], 3)
        return 0.15

    return wear


def _control(props, markings, point, approaches, sections, seed):
    if len(approaches) < 2:
        return
    ranks = [_rank(road) for road, _end in approaches]
    top = max(ranks)
    majors = sum(1 for rank in ranks if rank >= _RANK["major"])
    signalized = majors >= 2
    widths = []
    controlled = signalized
    for road, end in approaches:
        sec = sections.get(road["id"])
        if sec:
            widths.append(float(sec["width"]))
        if signalized:
            _place_end(props, road, end, sec, "signal", "")
        elif _arriving(road, end) and _rank(road) < top:
            kind = "yield" if _rank(road) >= _RANK["mid"] and top >= _RANK["major"] else "stop"
            _place_end(props, road, end, sec, kind, kind.upper())
            controlled = True
        elif _arriving(road, end) and _rank(road) == top and top <= _RANK["mid"] and len(set(ranks)) == 1:
            kind = "yield" if top >= _RANK["mid"] else "stop"
            _place_end(props, road, end, sec, kind, kind.upper())
            controlled = True
        _place_end(props, road, end, sec, "street_name", _cross_name(road, approaches))
        if sec and _arriving(road, end):
            _arrows(markings, road, end, sec)
    if widths and controlled:
        _keep_clear(markings, point, approaches, min(widths))


def _place_end(props, road, end, sec, kind, label):
    if not sec:
        return
    length = _length(road)
    radius = float((sec.get("curb") or {}).get("return_radius_m") or 6.0)
    # Corner clearance keeps lamps and trees 8 m back from the return. Signs sit
    # in that gap so a locked lamp is not within the 1.5 m merge radius of a sign.
    extra = 1.8 if kind == "street_name" else 0.0
    outset = 2.4 if kind == "street_name" else 1.25
    inset = radius + 2.6 + extra
    if length < inset + 6:
        return
    s = inset if end == 0 else length - inset
    side = _side_of_approach(end)
    back = profiles.curb_back_from_flow(road.get("cls") or "minor")
    lateral = side * (float(sec["width"]) / 2.0 + back + outset)
    point, tangent = _point_on(road, s, lateral)
    travel = tangent if end == 1 else (-tangent[0], -tangent[1])
    props.append(_prop(
        road, kind, point, travel, side,
        "prop_%s_%s_%d" % (road["id"], kind, end),
        label,
    ))


def _arrows(markings, road, end, sec):
    lanes = _approach_lanes(sec, end)
    turns = [(lat, legend) for lat, legend in lanes if legend in ("left", "right")]
    if not turns:
        return
    length = _length(road)
    radius = float((sec.get("curb") or {}).get("return_radius_m") or 6.0)
    inset = radius + 11.0
    if length < inset + 8:
        return
    s = inset if end == 0 else length - inset
    _travel_point, tangent = _point_on(road, s, 0.0)
    travel = tangent if end == 1 else (-tangent[0], -tangent[1])
    for lat, legend in turns:
        centre, _along = _point_on(road, s, lat)
        aim = travel
        if legend == "left":
            aim = _rot(travel, 0.55)
        elif legend == "right":
            aim = _rot(travel, -0.55)
        markings.append({
            "kind": "arrow", "legend": legend, "road_id": road["id"],
            "district_id": road.get("district_id"), "material": "M_LanePaint",
            "polygon": _triangle(centre, aim, 2.4, 1.05),
        })


def _keep_clear(markings, point, approaches, width):
    if width < 4.0:
        return
    road = approaches[0][0]
    span = min(8.0, width * 0.55)
    direction = (0.7071, 0.7071)
    normal = (-direction[1], direction[0])
    for index in range(-2, 3):
        centre = (point[0] + normal[0] * index * 1.15, point[1] + normal[1] * index * 1.15)
        markings.append({
            "kind": "keep_clear", "road_id": road["id"],
            "district_id": road.get("district_id"), "material": "M_LanePaintYellow",
            "polygon": _rect(centre, direction, span, 0.28),
        })


def _stalls_and_cars(props, markings, model, road, sec, seed):
    bands = _parking_bands(sec)
    if not bands:
        return
    length = _length(road)
    if length < 24:
        return
    pts = _pts(road)
    trim = _end_trim(pts, sec)
    start = trim[0] + 3.0
    end = length - trim[1] - 3.0
    if end - start < _STALL_M:
        return
    rate = _parking_rate(model, road)
    for band_i, (lateral, width) in enumerate(bands):
        s = start
        stall = 0
        while s + _STALL_M <= end + 0.05:
            tick, tangent = _point_on(road, s, lateral)
            markings.append({
                "kind": "stall", "road_id": road["id"],
                "district_id": road.get("district_id"), "material": "M_LanePaint",
                "polygon": _rect(tick, tangent, 0.12, max(1.6, width * 0.88)),
            })
            if rate > 0:
                occupy = min(0.82, rate / 16.0)
                if rnd(seed, road["id"], "park", band_i, stall) < occupy:
                    centre, along = _point_on(road, s + _STALL_M * 0.5, lateral)
                    props.append(_prop(
                        road, "parked", centre, along, 1.0 if lateral >= 0 else -1.0,
                        "prop_%s_parked_%d_%d" % (road["id"], band_i, stall),
                        "",
                    ))
            stall += 1
            s += _STALL_M
            if stall > 80:
                break


def _bus_stops(props, road, sec, seed):
    rank = _rank(road)
    if rank < _RANK["mid"] or rank >= _RANK["highway"]:
        return
    length = _length(road)
    if length < 50:
        return
    back = profiles.curb_back_from_flow(road.get("cls") or "minor")
    sides = (-1.0,) if road.get("oneway") else (1.0, -1.0)
    for side in sides:
        # Right-hand side of travel. A one-way following the polyline keeps
        # the stop on the right, which is negative-left.
        if road.get("oneway") and side > 0:
            continue
        s = length * (0.58 if side < 0 else 0.42)
        lateral = side * (float(sec["width"]) / 2.0 + back + 1.7)
        point, tangent = _point_on(road, s, lateral)
        props.append(_prop(
            road, "bus_stop", point, tangent, side,
            "prop_%s_bus_%d" % (road["id"], 0 if side > 0 else 1),
            "BUS",
        ))


def _parking_rate(model, road):
    """Cars per 100 m. A nearby lot tier wins; an untyped street defaults to a mid block."""
    district_id = road.get("district_id")
    best = None
    best_d = 45.0 * 45.0
    anchor = _pts(road)[0]
    for lot in model.get("lots") or []:
        if "parked_per_100m" not in lot:
            continue
        if district_id and lot.get("district_id") not in (None, district_id):
            continue
        polygon = lot.get("polygon") or []
        if len(polygon) < 3:
            continue
        centre = _centroid(polygon)
        dist = (centre[0] - anchor[0]) ** 2 + (centre[1] - anchor[1]) ** 2
        if dist < best_d:
            best_d = dist
            best = lot
    if best is None:
        return 8.0
    return float(best.get("parked_per_100m") or 0)


def _approach_lanes(sec, end):
    cursor = -float(sec["width"]) / 2.0
    found = []
    for elem in sec.get("elems") or []:
        kind = elem[0]
        width = float(elem[1])
        direc = int(elem[2]) if len(elem) > 2 else 0
        centre = cursor + width / 2.0
        cursor += width
        if kind == "twltl":
            found.append((centre, "left"))
        elif kind == "lane":
            if end == 1 and direc >= 0:
                found.append((centre, None))
            elif end == 0 and direc <= 0:
                found.append((centre, None))
    ordered = found if end == 1 else list(reversed(found))
    count = len(ordered)
    out = []
    for index, (lateral, forced) in enumerate(ordered):
        if forced:
            legend = forced
        elif count < 2:
            legend = "through"
        elif index == 0:
            legend = "left"
        elif index == count - 1:
            legend = "right"
        else:
            legend = "through"
        out.append((lateral, legend))
    return out


def _parking_bands(sec):
    cursor = -float(sec["width"]) / 2.0
    bands = []
    for elem in sec.get("elems") or []:
        width = float(elem[1])
        if elem[0] == "parking":
            bands.append((cursor + width / 2.0, width))
        cursor += width
    return bands


def _groups(roads, junctions):
    groups = {}
    for road in roads:
        pts = _pts(road)
        if len(pts) < 2:
            continue
        for end, point in ((0, pts[0]), (1, pts[-1])):
            hit = _match(point, junctions)
            if hit is None:
                continue
            groups.setdefault(hit, []).append((road, end))
    return list(groups.items())


def _junctions(roads):
    counts = {}
    for road in roads:
        seen = set()
        for point in road.get("polyline") or []:
            key = (round(float(point[0]), 2), round(float(point[1]), 2))
            if key in seen:
                continue
            seen.add(key)
            counts[key] = counts.get(key, 0) + 1
    return {point for point, count in counts.items() if count >= 2}


def _match(point, junctions):
    for junction in junctions:
        if _dist(point, junction) < 0.25:
            return junction
    return None


def _cross_name(road, approaches):
    for other, _end in approaches:
        if other.get("id") != road.get("id") and other.get("name"):
            return str(other["name"])[:24]
    return "Cross Street"


def _arriving(road, end):
    if end == 1:
        return True
    return not bool(road.get("oneway"))


def _side_of_approach(end):
    """Sidewalk on the right of arriving traffic. +1 is left of the polyline."""
    return -1.0 if end == 1 else 1.0


def _rank(road):
    return _RANK.get(road.get("cls") or "minor", 1)


def _prop(road, kind, point, tangent, side, ident, label):
    yaw = math.degrees(math.atan2(tangent[1], tangent[0]))
    item = {
        "id": ident,
        "kind": kind,
        "x": round(point[0], 2),
        "y": round(point[1], 2),
        "yaw": round(yaw, 1),
        "side": side,
        "road_id": road["id"],
        "district_id": road.get("district_id"),
        "source": "generated",
        "locked": False,
    }
    if label:
        item["label"] = label
    return item


def _end_trim(pts, sec):
    # Local trim so stall paint stops before a corner. Junction radius is enough;
    # the city already trimmed the curb. A missing radius still keeps a gap.
    radius = float((sec.get("curb") or {}).get("return_radius_m") or 4.0)
    return [radius, radius]


def _length(road):
    pts = _pts(road)
    return sum(_dist(a, b) for a, b in zip(pts, pts[1:]))


def _pts(road):
    return [(float(p[0]), float(p[1])) for p in road.get("polyline") or []]


def _point_on(road, s, lateral):
    pts = _pts(road)
    total = sum(_dist(a, b) for a, b in zip(pts, pts[1:])) or 1e-6
    s = max(0.0, min(total, s))
    walked = 0.0
    for a, b in zip(pts, pts[1:]):
        length = _dist(a, b)
        if walked + length >= s - 1e-8:
            t = (s - walked) / (length or 1.0)
            point = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            tangent = _unit((b[0] - a[0], b[1] - a[1]))
            left = (-tangent[1], tangent[0])
            return (point[0] + left[0] * lateral, point[1] + left[1] * lateral), tangent
        walked += length
    tangent = _unit((pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]))
    left = (-tangent[1], tangent[0])
    return (pts[-1][0] + left[0] * lateral, pts[-1][1] + left[1] * lateral), tangent


def _triangle(centre, direction, length, width):
    direction = _unit(direction)
    normal = (-direction[1], direction[0])
    tip = (centre[0] + direction[0] * length * 0.55, centre[1] + direction[1] * length * 0.55)
    base = (centre[0] - direction[0] * length * 0.45, centre[1] - direction[1] * length * 0.45)
    left = (base[0] + normal[0] * width * 0.5, base[1] + normal[1] * width * 0.5)
    right = (base[0] - normal[0] * width * 0.5, base[1] - normal[1] * width * 0.5)
    return [_r2(tip), _r2(left), _r2(right)]


def _rect(centre, tangent, along, across):
    tangent = _unit(tangent)
    normal = (-tangent[1], tangent[0])
    ha, hc = along / 2.0, across / 2.0
    pts = []
    for sa, sc in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        pts.append(_r2((
            centre[0] + tangent[0] * sa * ha + normal[0] * sc * hc,
            centre[1] + tangent[1] * sa * ha + normal[1] * sc * hc,
        )))
    return pts


def _centroid(polygon):
    sx = sum(float(p[0]) for p in polygon)
    sy = sum(float(p[1]) for p in polygon)
    n = len(polygon) or 1
    return (sx / n, sy / n)


def _rot(vector, radians):
    c, s = math.cos(radians), math.sin(radians)
    return (vector[0] * c - vector[1] * s, vector[0] * s + vector[1] * c)


def _unit(vector):
    length = math.hypot(vector[0], vector[1]) or 1e-6
    return (vector[0] / length, vector[1] / length)


def _dist(a, b):
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _r2(point):
    return (round(point[0], 2), round(point[1], 2))
