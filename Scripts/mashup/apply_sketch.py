"""Apply Kenny's sketch (saved on the mashup page) to an integrated plan.

Each feature below is read from his strokes: scribbles are turned into smooth centrelines by binning
the stroke points along the feature's main axis, then smoothed into organic curves.
  - canal: the South Branch carried north beside Willis Tower into Lady Bird Lake (+ a branch to the creek)
  - expressway: the stub at Willis Tower carried north along the canal, curving into a cross-town road
  - cross-town road with a roundabout where it meets the north-south main road
  - Ida B. Wells Expressway carried west past the Capitol, with a ramp to the parallel street
  - Lady Bird's eastern channel carried into Lake Michigan under Lake Shore Drive
New expressways through the Austin grid are elevated, so cross streets pass underneath.
Roads that would run lengthwise inside new water are removed; roads crossing it become bridges.

Usage: python3 -I Scripts/mashup/apply_sketch.py <plan_in.json> <sketch.json> <plan_out.json>
"""
import json, math, sys

plan = json.load(open(sys.argv[1]))
sk = json.load(open(sys.argv[2]))
sk = sk.get("data", sk)
S = sk["strokes"]
stats = {}


def unit(v):
    L = math.hypot(*v) or 1.0
    return (v[0] / L, v[1] / L)


def length(p):
    return sum(math.dist(a, b) for a, b in zip(p, p[1:]))


def pts_of(*idx, where=lambda p: True):
    return [tuple(p) for i in idx for p in S[i]["pts"] if where(p)]


def centreline(points, axis, step=25.0, lo=None, hi=None):
    """Average the cross coordinate of a scribble in bins along one axis (0 = x, 1 = y)."""
    a = [p[axis] for p in points]
    lo = min(a) if lo is None else lo
    hi = max(a) if hi is None else hi
    out, v = [], lo
    while v <= hi + 1e-6:
        near = [p[1 - axis] for p in points if abs(p[axis] - v) <= step * 0.75]
        if near:
            c = sum(near) / len(near)
            out.append((v, c) if axis == 0 else (c, v))
        v += step
    return smooth(out, 2)


def smooth(p, passes=2):
    """Chaikin corner cutting keeps the ends fixed and rounds everything between."""
    for _ in range(passes):
        if len(p) < 3:
            return p
        q = [p[0]]
        for a, b in zip(p, p[1:]):
            q += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]), (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        q.append(p[-1])
        p = q
    return p


def resample(p, step=12.0):
    out = [p[0]]
    for a, b in zip(p, p[1:]):
        n = max(1, int(math.dist(a, b) / step))
        for i in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n))
    return out


def buffer(p, width):
    """Polygon of a polyline widened to `width` (a canal)."""
    p = resample(p, 10.0)
    L, R = [], []
    for i, c in enumerate(p):
        a = p[max(0, i - 1)]; b = p[min(len(p) - 1, i + 1)]
        tx, ty = unit((b[0] - a[0], b[1] - a[1]))
        nx, ny = -ty, tx
        L.append((c[0] + nx * width / 2, c[1] + ny * width / 2))
        R.append((c[0] - nx * width / 2, c[1] - ny * width / 2))
    return L + R[::-1]


def curve(a, ha, b, hb, n=16):
    D = math.dist(a, b); k = 0.42 * D
    p1 = (a[0] + ha[0] * k, a[1] + ha[1] * k); p2 = (b[0] + hb[0] * k, b[1] + hb[1] * k)
    out = []
    for i in range(n + 1):
        t = i / n
        c0, c1, c2, c3 = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        out.append((c0 * a[0] + c1 * p1[0] + c2 * p2[0] + c3 * b[0], c0 * a[1] + c1 * p1[1] + c2 * p2[1] + c3 * b[1]))
    return out


def nearest_road_point(p, classes, maxd=300, exclude=()):
    best = None
    for k, r in enumerate(plan["roads"]):
        if r["cls"] not in classes or k in exclude:
            continue
        pts = r["pts"]
        for a, b in zip(pts, pts[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy or 1e-9
            u = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
            q = (a[0] + dx * u, a[1] + dy * u)
            d = math.dist(p, q)
            if d <= maxd and (best is None or d < best[0]):
                best = (d, q, unit((dx, dy)), k)
    return best


def add_road(pts, cls, name, elevated=False):
    plan["roads"].append({"cls": cls, "city": "sketch", "name": name, "new": True, "elevated": elevated,
                          "pts": [[round(x, 1), round(y, 1)] for x, y in pts]})


new_water = []


def add_water(poly):
    ring = [[round(x, 1), round(y, 1)] for x, y in poly]
    plan["water"]["outer"].append(ring)
    new_water.append([tuple(p) for p in ring])


# 1. canal: South Branch north to Lady Bird Lake, plus a branch east to the creek
canal = centreline(pts_of(15), axis=1, step=30.0, lo=-1040, hi=262)
add_water(buffer(canal, 48.0))
creek = centreline(pts_of(16), axis=0, step=20.0)
if len(creek) >= 2:
    creek = [canal[min(range(len(canal)), key=lambda i: math.dist(canal[i], creek[0]))]] + creek
    add_water(buffer(creek, 22.0))
stats["canal_length_m"] = round(length(canal))

# 2. expressway north from Willis Tower along the canal, curving east into the cross-town road
ns = centreline(pts_of(2, where=lambda p: p[1] < -380), axis=1, step=30.0)
ns = sorted(ns, key=lambda p: p[1])                    # south to north

# 3. cross-town road (west end deep in Austin, east end at the Loop) with a roundabout
ew_pts = pts_of(2, 5, 6, 7, 8, 9, 10, 19, where=lambda p: -390 <= p[1] <= -230)
ew = centreline(ew_pts, axis=0, step=30.0)
ring_pts = pts_of(3, 4)
rc = (sum(p[0] for p in ring_pts) / len(ring_pts), sum(p[1] for p in ring_pts) / len(ring_pts))
R = 42.0
# the cross-town road stops at the circle on both sides
west = [p for p in ew if p[0] < rc[0] and math.dist(p, rc) > R + 6]
east = [p for p in ew if p[0] > rc[0] and math.dist(p, rc) > R + 6]
circle = [(rc[0] + R * math.cos(2 * math.pi * i / 36), rc[1] + R * math.sin(2 * math.pi * i / 36)) for i in range(37)]
add_road(circle, "major", "Seam Circle")
for side, part in (("west", west), ("east", east)):
    if len(part) < 2:
        continue
    end = part[-1] if side == "west" else part[0]
    v = unit((rc[0] - end[0], rc[1] - end[1]))
    on_ring = (rc[0] - v[0] * R, rc[1] - v[1] * R)
    seg = part + [on_ring] if side == "west" else [on_ring] + part
    add_road(seg, "major", "Crosstown Parkway")
# the north-south main road through the circle's spot also meets the ring
hit = nearest_road_point(rc, ("major", "mid"), maxd=80)
stats["roundabout_on_main_road"] = bool(hit)
# expressway: from the Willis stub north, then a smooth merge into the parkway west of the circle
stub = nearest_road_point(ns[0], ("highway",), maxd=250)
if stub:
    _, q, _, _ = stub
    ns = [q] + [p for p in ns if math.dist(p, q) > 25]
merge_at = min(west, key=lambda p: abs(p[0] - (ns[-1][0] + 140))) if west else None
expressway = ns[:-2] + (curve(ns[-3], unit((ns[-1][0] - ns[-3][0], ns[-1][1] - ns[-3][1])), merge_at, (-1.0, 0.0)) if merge_at else ns[-2:])
add_road(smooth(expressway, 1), "highway", "Wacker Canal Expressway", elevated=True)
stats["expressway_north_m"] = round(length(expressway))
# east end of the parkway joins the Loop's main streets
if east:
    j = nearest_road_point(east[-1], ("major", "highway"), maxd=260)
    if j and j[0] > 3:
        add_road(curve(east[-1], unit((east[-1][0] - east[-2][0], east[-1][1] - east[-2][1])), j[1], unit((east[-1][0] - j[1][0], east[-1][1] - j[1][1]))), "major", "Crosstown Parkway")

# 4. Ida B. Wells Expressway west past the Capitol, with a ramp south
ib = centreline(pts_of(0, 1, 11), axis=0, step=30.0)
ib = sorted(ib, key=lambda p: -p[0])                  # east to west
stub = nearest_road_point(ib[0], ("highway",), maxd=250)
if stub:
    ib = [stub[1]] + [p for p in ib if math.dist(p, stub[1]) > 25]
x0 = plan["bounds"][0]
if ib[-1][0] > x0 + 5:
    ib.append((x0, ib[-1][1]))                       # carry it on to the edge of the city
add_road(smooth(ib, 1), "highway", "Ida B. Wells Expressway", elevated=True)
ramp = smooth([tuple(p) for p in S[12]["pts"]], 2)
if len(ramp) >= 2:
    a = nearest_road_point(ramp[0], ("highway",), maxd=150)
    b = nearest_road_point(ramp[-1], ("major", "mid", "minor"), maxd=150)
    pts = ([a[1]] if a else []) + ramp + ([b[1]] if b else [])
    add_road(smooth(pts, 1), "mid", "Ida B. Wells ramp")
stats["ida_b_wells_west_m"] = round(length(ib))

# 5. Lady Bird's eastern channel carried into the lake under Lake Shore Drive
ne = centreline(pts_of(13), axis=0, step=20.0)
add_water(buffer(ne, 40.0))
stats["lakeward_channel_m"] = round(length(ne))


# ---- roads vs the new water: lengthwise runs are removed, crossings become bridges ----------------------
def point_in(p, ring):
    x, y, inside = p[0], p[1], False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            inside = not inside
    return inside


boxes = [(r, min(p[0] for p in r), min(p[1] for p in r), max(p[0] for p in r), max(p[1] for p in r)) for r in new_water]


def in_new_water(p):
    return any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 and point_in(p, r) for r, x0, y0, x1, y1 in boxes)


kept, removed = [], 0
for r in plan["roads"]:
    if r.get("city") == "sketch" or r["cls"] == "highway":
        kept.append(r); continue
    pts = resample([tuple(p) for p in r["pts"]], 8.0)
    wet = [in_new_water(p) for p in pts]
    # find wet runs; long ones (the street runs along the canal) are cut out
    pieces, cur, run = [], [], []
    for p, w in zip(pts, wet):
        if w:
            run.append(p)
            continue
        if run:
            if length(run) > 70:          # lengthwise: drop it, split the street here
                if len(cur) > 1:
                    pieces.append(cur)
                cur = []
                removed += 1
            else:
                cur += run
            run = []
        cur.append(p)
    if run and length(run) <= 70:
        cur += run
    if len(cur) > 1:
        pieces.append(cur)
    for pc in pieces:
        if length(pc) > 20:
            kept.append({**r, "pts": [[round(x, 1), round(y, 1)] for x, y in pc]})
plan["roads"] = kept
stats["street_runs_removed_from_canals"] = removed

# recompute bridges over all water
water = [(r, min(p[0] for p in r), min(p[1] for p in r), max(p[0] for p in r), max(p[1] for p in r)) for r in [[tuple(p) for p in w] for w in plan["water"]["outer"]]]
islands = [[tuple(p) for p in w] for w in plan["water"]["inner"]]


def wet_any(p):
    for r, x0, y0, x1, y1 in water:
        if x0 <= p[0] <= x1 and y0 <= p[1] <= y1 and point_in(p, r):
            return not any(point_in(p, i) for i in islands)
    return False


plan["bridges"] = []
for r in plan["roads"]:
    if r["cls"] == "ped":
        continue
    pts = resample([tuple(p) for p in r["pts"]], 10.0)
    run = []
    for a, b in zip(pts, pts[1:]):
        if wet_any(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)):
            run = run or [a]
            run.append(b)
        elif run:
            if length(run) > 8:
                plan["bridges"].append({"cls": r["cls"], "name": r["name"], "pts": [[round(x, 1), round(y, 1)] for x, y in run]})
            run = []
    if run and length(run) > 8:
        plan["bridges"].append({"cls": r["cls"], "name": r["name"], "pts": [[round(x, 1), round(y, 1)] for x, y in run]})
stats["bridges"] = len(plan["bridges"])

plan.setdefault("stats", {})["sketch"] = stats
plan["sketch_applied"] = sk.get("savedAt")
json.dump(plan, open(sys.argv[3], "w"), separators=(",", ":"))
print(json.dumps(stats, indent=1))
