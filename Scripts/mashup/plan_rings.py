"""Plan a boost-ring course through the mashup (plan metres -> Saved/Mashup/rings_v1.json).

One loop that shows the city off: east along Lady Bird Lake from the Congress Ave bridge, under-the-bridge height
to the Lake Shore Drive crossing, south over the lakefront to Buckingham Fountain, up Michigan Avenue past the Bean,
across the Chicago River, down the South Branch past Willis Tower, west to the Texas Capitol and back up
Congress Avenue. Rings sit on a smooth Catmull-Rom curve through the waypoints, roughly every 170 m, and are
raised wherever a building would clip them.
Usage: python3 plan_rings.py ../../Saved/Mashup/buildings_v3.json ../../Saved/Mashup/rings_v1.json
"""
import json, math, sys

# (x, y, z) plan metres; z is height above ground
WAYPOINTS = [
    (-1300, 340, 20), (-900, 300, 18), (-500, 285, 18), (-150, 330, 24), (150, 470, 30), (500, 680, 32),
    (850, 800, 30), (1150, 790, 26), (1350, 600, 40), (1250, 100, 42), (1100, -400, 36), (950, -1000, 36),
    (738, -1240, 40), (420, -1290, 30), (300, -1100, 30), (300, -800, 30), (300, -450, 30), (300, -120, 34),
    (260, 60, 30), (-300, 200, 36), (-700, 150, 30), (-745, -200, 30), (-745, -600, 30), (-745, -950, 30),
    (-760, -1300, 26), (-1050, -1300, 30), (-1300, -1290, 34), (-1335, -1000, 44), (-1452, -760, 40),
    (-1440, -420, 36), (-1430, -120, 34), (-1421, 100, 28),
]
SPACING = 170.0
RING_R = 10.0        # ring radius (m); clearance needed around its centre
CLEAR = RING_R + 4.0


def catmull(p0, p1, p2, p3, t):
    return tuple(0.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (-a + 3 * b - 3 * c + d) * t ** 3)
                 for a, b, c, d in zip(p0, p1, p2, p3))


def sample_loop(wp, step):
    n = len(wp)
    dense = []
    for i in range(n):
        p0, p1, p2, p3 = wp[i - 1], wp[i], wp[(i + 1) % n], wp[(i + 2) % n]
        for k in range(40):
            dense.append(catmull(p0, p1, p2, p3, k / 40))
    out, acc = [dense[0]], 0.0
    for a, b in zip(dense, dense[1:] + dense[:1]):
        acc += math.dist(a[:2], b[:2])
        if acc >= step:
            out.append(b)
            acc = 0.0
    return out


def rect_dist(b, x, y):
    """Distance from (x, y) to the building's footprint rectangle (0 inside)."""
    a = math.radians(b["yaw"])
    dx, dy = x - b["x"], y - b["y"]
    u = dx * math.cos(a) + dy * math.sin(a)
    v = -dx * math.sin(a) + dy * math.cos(a)
    ou = max(0.0, abs(u) - b["w"] / 2)
    ov = max(0.0, abs(v) - b["d"] / 2)
    return math.hypot(ou, ov)


B = json.load(open(sys.argv[1]))["buildings"]
pts = sample_loop(WAYPOINTS, SPACING)
def blocked_top(x, y):
    near = [b for b in B if abs(b["x"] - x) < 90 and abs(b["y"] - y) < 90 and rect_dist(b, x, y) < CLEAR]
    return max([b["h"] for b in near], default=0.0)


rings, raised, nudged = [], 0, 0
for i, (x, y, z) in enumerate(pts):
    # slide sideways (perpendicular to the course) to the nearest gap between buildings before climbing over them
    nx_, ny_, _ = pts[(i + 1) % len(pts)]
    px_, py_, _ = pts[i - 1]
    hd = math.atan2(ny_ - py_, nx_ - px_)
    sx, sy = -math.sin(hd), math.cos(hd)
    best = None
    for off in [0] + [s * k for k in range(4, 49, 4) for s in (1, -1)]:
        cx, cy = x + sx * off, y + sy * off
        if blocked_top(cx, cy) <= z - CLEAR:
            best = (cx, cy)
            break
    if best is None:
        z = blocked_top(x, y) + CLEAR + 4
        raised += 1
    else:
        if best != (x, y):
            nudged += 1
        x, y = best
    rings.append([round(x, 1), round(y, 1), round(z, 1)])
# ease the height profile so no ring is a sudden jump: limit the climb between rings to ~20 degrees
for _ in range(3):
    for i in range(len(rings)):
        for j in (i - 1, (i + 1) % len(rings)):
            gap = math.dist(rings[i][:2], rings[j][:2])
            if rings[j][2] < rings[i][2] - gap * 0.36:
                rings[j][2] = round(rings[i][2] - gap * 0.36, 1)
# heading of each ring: toward the next one
pos = [tuple(r) for r in rings]
for i, r in enumerate(rings):
    nx, ny, nz = pos[(i + 1) % len(pos)]
    px, py, pz = pos[i - 1]
    r.append(round(math.degrees(math.atan2(ny - py, nx - px)), 1))               # plan heading (deg, CCW from east)
    r.append(round(math.degrees(math.atan2(nz - pz, math.dist((nx, ny), (px, py)))), 1))  # climb angle
json.dump({"rings": rings, "radius_m": RING_R}, open(sys.argv[2], "w"))
print("rings", len(rings), "raised", raised, "nudged", nudged, "max z", max(r[2] for r in rings))
