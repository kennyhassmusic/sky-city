"""Plane geometry for the city model. Metres, x east, y north. No PyYAML, no Shapely.

Polygons are lists of (x, y) in counter-clockwise order, not closed (the first point is not
repeated at the end). The same helpers feed the grammar, the lot splitter, the street
section and the tests, so a footprint means one thing everywhere.
"""
import math
import zlib


def rnd(*parts):
    """A stable 0..1 number. Arguments should be strings, ints or short floats.

    `repr` is the seed, so call sites pass already-rounded values. The same arguments
    always return the same number, which is what makes a city reproducible.
    """
    return (zlib.crc32(repr(parts).encode()) & 0xffffffff) / 4294967296.0


def r2(p):
    return (round(p[0], 2), round(p[1], 2))


def r3(p):
    return (round(float(p[0]), 3), round(float(p[1]), 3))


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def mul(a, s):
    return (a[0] * s, a[1] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def hypot(a):
    return math.hypot(a[0], a[1])


def unit(a):
    L = hypot(a) or 1e-12
    return (a[0] / L, a[1] / L)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def poly_area(poly):
    a = 0.0
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        a += p[0] * q[1] - q[0] * p[1]
    return a / 2.0


def ensure_ccw(poly):
    if poly_area(poly) < 0:
        return list(reversed(poly))
    return list(poly)


def centroid(poly):
    a = poly_area(poly)
    if abs(a) < 1e-8:
        sx = sum(p[0] for p in poly) / len(poly)
        sy = sum(p[1] for p in poly) / len(poly)
        return (sx, sy)
    x = y = 0.0
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        c = p[0] * q[1] - q[0] * p[1]
        x += (p[0] + q[0]) * c
        y += (p[1] + q[1]) * c
    x /= 6.0 * a
    y /= 6.0 * a
    return (x, y)


def canon_ring(poly):
    """CCW ring starting at the lexicographically lowest vertex, rounded to centimetres.

    The block id is a hash of this, so regenerating the same roads finds the same block.
    """
    poly = [r2(p) for p in ensure_ccw(poly)]
    # drop a repeated closing point, and consecutive duplicates
    cleaned = []
    for p in poly:
        if not cleaned or dist(cleaned[-1], p) > 0.02:
            cleaned.append(p)
    if len(cleaned) >= 2 and dist(cleaned[0], cleaned[-1]) < 0.02:
        cleaned.pop()
    if not cleaned:
        return []
    i = min(range(len(cleaned)), key=lambda k: (cleaned[k][1], cleaned[k][0]))
    return cleaned[i:] + cleaned[:i]


def point_in_poly(p, poly):
    """Even-odd test. Points on the boundary count as inside."""
    x, y = p
    n = len(poly)
    inside = False
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if abs((y1 - y0) * (x - x0) - (x1 - x0) * (y - y0)) < 1e-8:
            if min(x0, x1) - 1e-8 <= x <= max(x0, x1) + 1e-8 and min(y0, y1) - 1e-8 <= y <= max(y0, y1) + 1e-8:
                return True
        if (y0 > y) != (y1 > y):
            xint = (x1 - x0) * (y - y0) / ((y1 - y0) or 1e-12) + x0
            if xint >= x:
                inside = not inside
    return inside


def bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys)), (max(xs), max(ys))


def spans(poly):
    (x0, y0), (x1, y1) = bbox(poly)
    return x1 - x0, y1 - y0


def line_hit(p, d, q, e):
    """Intersection of p + t d and q + u e. Returns (point, t, u) or None."""
    den = cross(d, e)
    if abs(den) < 1e-12:
        return None
    w = sub(q, p)
    t = cross(w, e) / den
    u = cross(w, d) / den
    return (p[0] + d[0] * t, p[1] + d[1] * t), t, u


def seg_hit(a, b, c, d, tol=1e-8):
    """Proper or endpoint intersection of segments ab and cd. Returns (point, t, u) or None."""
    hit = line_hit(a, sub(b, a), c, sub(d, c))
    if hit is None:
        return None
    pt, t, u = hit
    if -tol <= t <= 1 + tol and -tol <= u <= 1 + tol:
        return pt, t, u
    return None


def project_t(p, a, b):
    """Parameter of the closest point of p on segment ab, if the distance is under 0.05 and t is interior."""
    ab = sub(b, a)
    L2 = dot(ab, ab) or 1e-12
    t = dot(sub(p, a), ab) / L2
    if t <= 0.002 or t >= 0.998:
        return None
    q = lerp(a, b, t)
    if dist(p, q) > 0.05:
        return None
    return t


def offset_polygon(poly, dist):
    """Parallel inset (dist > 0) of a convex CCW polygon. Negative dist outsets it.

    Falls back to a scale about the centroid if an edge offset would collapse.
    """
    poly = ensure_ccw(poly)
    if abs(dist) < 1e-8:
        return [tuple(p) for p in poly]
    if not is_convex(poly):
        return scale_about(poly, max(0.15, 1.0 - dist / max(spans(poly)) * 2.0))
    n = len(poly)
    lines = []
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        d = unit(sub(b, a))
        inward = (-d[1], d[0])
        lines.append((add(a, mul(inward, dist)), d))
    out = []
    for i in range(n):
        hit = line_hit(lines[i][0], lines[i][1], lines[(i + 1) % n][0], lines[(i + 1) % n][1])
        if hit is None:
            return scale_about(poly, 0.8)
        out.append(hit[0])
    if poly_area(out) <= 1.0 or not is_convex(out):
        return scale_about(poly, max(0.2, 1.0 - abs(dist) / (max(spans(poly)) or 1)))
    return out


def offset_edges(poly, dists):
    """Offset each edge of a convex CCW polygon by its own distance (positive = inward)."""
    poly = ensure_ccw(poly)
    n = len(poly)
    if len(dists) != n:
        raise ValueError("one distance per edge")
    lines = []
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        d = unit(sub(b, a))
        inward = (-d[1], d[0])
        lines.append((add(a, mul(inward, dists[i])), d))
    out = []
    for i in range(n):
        hit = line_hit(lines[i][0], lines[i][1], lines[(i + 1) % n][0], lines[(i + 1) % n][1])
        if hit is None:
            return offset_polygon(poly, sum(dists) / n)
        out.append(hit[0])
    if poly_area(out) <= 1.0:
        return offset_polygon(poly, sum(dists) / n)
    return out


def is_convex(poly):
    n = len(poly)
    if n < 3:
        return False
    sign = 0
    for i in range(n):
        a, b, c = poly[i], poly[(i + 1) % n], poly[(i + 2) % n]
        z = cross(sub(b, a), sub(c, b))
        if abs(z) < 1e-8:
            continue
        s = 1 if z > 0 else -1
        if sign and s != sign:
            return False
        sign = s
    return True


def scale_about(poly, factor):
    c = centroid(poly)
    return [add(c, mul(sub(p, c), factor)) for p in poly]


def clip_halfplane(poly, origin, normal):
    """Keep the part of poly where dot(p - origin, normal) >= 0. normal points at the kept side."""
    if not poly:
        return []
    out = []
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        da = dot(sub(a, origin), normal)
        db = dot(sub(b, origin), normal)
        if da >= -1e-9:
            out.append(a)
        if (da > 0) != (db > 0) and abs(da - db) > 1e-12:
            t = da / (da - db)
            out.append(lerp(a, b, t))
    return out


def rectangle_frame(poly, tol=0.08):
    """If poly is a rectangle, return origin, x axis (long side), y axis (inward), width, depth.

    origin is the start of the long side. Local (0, 0) is that corner and the polygon
    occupies local x in [0, width], y in [0, depth].
    """
    poly = ensure_ccw(poly)
    if len(poly) != 4:
        return None
    vecs = [sub(poly[(i + 1) % 4], poly[i]) for i in range(4)]
    lens = [hypot(v) for v in vecs]
    for i in range(4):
        if abs(dot(vecs[i], vecs[(i + 1) % 4])) > tol * lens[i] * lens[(i + 1) % 4]:
            return None
    i = max(range(4), key=lambda k: lens[k])
    if lens[i] < 1.0 or lens[(i + 1) % 4] < 1.0:
        return None
    x = unit(vecs[i])
    y = (-x[1], x[0])
    return {"origin": tuple(poly[i]), "x": x, "y": y, "width": lens[i], "depth": lens[(i + 1) % 4]}


def to_local(p, frame):
    d = sub(p, frame["origin"])
    return (dot(d, frame["x"]), dot(d, frame["y"]))


def to_world(lx, ly, frame):
    return add(frame["origin"], add(mul(frame["x"], lx), mul(frame["y"], ly)))


def world_poly(local_pts, frame):
    return [r2(to_world(x, y, frame)) for x, y in local_pts]


def mark_rect(centre, tangent, along, across):
    """A rectangle centred on centre. `along` is its length in the tangent direction."""
    t = unit(tangent)
    n = (-t[1], t[0])
    ha, hc = along / 2.0, across / 2.0
    pts = []
    for sa, sc in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        pts.append(r2(add(centre, add(mul(t, sa * ha), mul(n, sc * hc)))))
    return pts


def fillet_ring(poly, radius, n=5):
    """Round every corner of a CCW ring with the same radius. The arc bulges to the inside,
    which is how a curb return cuts the sharp corner off a block."""
    poly = ensure_ccw(poly)
    m = len(poly)
    if m < 3 or radius <= 0:
        return [tuple(p) for p in poly]
    out = []
    for i in range(m):
        prev, c, nxt = poly[(i - 1) % m], poly[i], poly[(i + 1) % m]
        vin = unit(sub(c, prev))
        vout = unit(sub(nxt, c))
        delta = math.atan2(cross(vin, vout), dot(vin, vout))
        if abs(delta) < 0.2:
            out.append(tuple(c))
            continue
        half = abs(delta) / 2.0
        tan_half = math.tan(half) or 1e-6
        L = min(radius * math.tan(half), 0.45 * dist(prev, c), 0.45 * dist(c, nxt))
        r_eff = L / tan_half
        t1 = sub(c, mul(vin, L))
        t2 = add(c, mul(vout, L))
        left = (-vin[1], vin[0])
        side = 1.0 if delta > 0 else -1.0
        centre = add(t1, mul(left, side * r_eff))
        a0 = math.atan2(t1[1] - centre[1], t1[0] - centre[0])
        a1 = math.atan2(t2[1] - centre[1], t2[0] - centre[0])
        sweep = a1 - a0
        while sweep > math.pi:
            sweep -= 2 * math.pi
        while sweep < -math.pi:
            sweep += 2 * math.pi
        out.append(t1)
        for k in range(1, n):
            a = a0 + sweep * k / n
            out.append((centre[0] + r_eff * math.cos(a), centre[1] + r_eff * math.sin(a)))
        out.append(t2)
    return out


def move_inward(poly, dist):
    """Push every vertex of a CCW ring inward along a smoothed vertex normal."""
    poly = ensure_ccw(poly)
    n = len(poly)
    out = []
    for i in range(n):
        prev, c, nxt = poly[(i - 1) % n], poly[i], poly[(i + 1) % n]
        e0 = unit(sub(c, prev))
        e1 = unit(sub(nxt, c))
        left0 = (-e0[1], e0[0])
        left1 = (-e1[1], e1[0])
        inward = unit(add(left0, left1))
        # mitre so a constant offset doesn't leave gaps on a straight run
        k = max(0.4, dot(inward, left0))
        out.append(add(c, mul(inward, dist / k)))
    return out
