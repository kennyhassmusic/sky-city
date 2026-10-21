"""Plan building footprints for the integrated city (plan_v3.json -> buildings_v3.json).

Every free spot between streets, water, parks, the L and the landmarks gets buildings: rectangles turned to
face the nearest street, packed with alley gaps, sized and styled by district:
  - Chicago Loop and River North: dense towers, tallest near Willis Tower and the river
  - Austin downtown: glass towers near Lady Bird Lake, mid-rise further out
  - the far Austin side (South Congress country): low-rise
Usage: python3 Scripts/mashup/plan_buildings.py <plan.json> <layout.json> <out.json>
"""
import json, math, sys
import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import integrate_v2 as V   # for the seam frame (which side of the mashup a point is on)

plan = json.load(open(sys.argv[1]))
L = json.load(open(sys.argv[2])); L = L.get("data", L)
F = V.Frame(L)
rng = np.random.default_rng(7)

CELL = 3.0
x0, y0, x1, y1 = plan["bounds"]
NX, NY = int((x1 - x0) / CELL) + 1, int((y1 - y0) / CELL) + 1
blocked = np.zeros((NY, NX), dtype=bool)
gx = x0 + (np.arange(NX) + 0.5) * CELL
gy = y0 + (np.arange(NY) + 0.5) * CELL


def mark_poly(ring, pad=0.0):
    pts = np.array(ring, dtype=float)
    if len(pts) < 3:
        return
    ys = pts[:, 1]
    r0 = max(0, int((ys.min() - y0) / CELL)); r1 = min(NY - 1, int((ys.max() - y0) / CELL) + 1)
    xa, ya = pts[:, 0], pts[:, 1]
    xb, yb = np.roll(xa, -1), np.roll(ya, -1)
    for r in range(r0, r1 + 1):
        y = gy[r]
        cross = ((ya <= y) & (yb > y)) | ((yb <= y) & (ya > y))
        if not cross.any():
            continue
        xs = np.sort(xa[cross] + (y - ya[cross]) * (xb[cross] - xa[cross]) / (yb[cross] - ya[cross]))
        for a, b in zip(xs[0::2], xs[1::2]):
            c0 = max(0, int((a - pad - x0) / CELL)); c1 = min(NX - 1, int((b + pad - x0) / CELL))
            if c1 >= c0:
                blocked[r, c0:c1 + 1] = True


def mark_line(pts, half):
    pts = np.array(pts, dtype=float)
    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
        c0 = max(0, int((min(ax, bx) - half - x0) / CELL)); c1 = min(NX - 1, int((max(ax, bx) + half - x0) / CELL) + 1)
        r0 = max(0, int((min(ay, by) - half - y0) / CELL)); r1 = min(NY - 1, int((max(ay, by) + half - y0) / CELL) + 1)
        if c1 < c0 or r1 < r0:
            continue
        X, Y = np.meshgrid(gx[c0:c1 + 1], gy[r0:r1 + 1])
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy or 1e-9
        u = np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0, 1)
        d = np.hypot(X - (ax + u * dx), Y - (ay + u * dy))
        blocked[r0:r1 + 1, c0:c1 + 1] |= d <= half


HALF = {"ped": 3.0, "minor": 4.5 + 4, "mid": 6 + 4, "major": 8 + 4.5, "highway": 12 + 5}
for r in plan["roads"]:
    mark_line(r["pts"], HALF[r["cls"]] + (6 if r.get("elevated") else 0))
for r in plan["rail"]:
    mark_line(r["pts"], 7.0 if r["kind"] == "L" else 6.0)
for ring in plan["water"]["outer"]:
    mark_poly(ring, 4.0)
for ring in plan["parks"] + plan.get("beaches", []):
    mark_poly(ring)
for lm in plan["landmarks"]:
    x, y = lm["pos"]
    mark_line([[x - 1, y], [x + 1, y]], 90.0 if lm["name"] in ("Willis Tower", "Texas State Capitol") else 45.0)
# keep a margin inside the bounds
m = int(40 / CELL)
blocked[:m, :] = blocked[-m:, :] = True
blocked[:, :m] = blocked[:, -m:] = True
# islands are land again
used = blocked.copy()

# nearest-street direction field: sample road segments
segs = []
for r in plan["roads"]:
    if r["cls"] == "ped":
        continue
    for a, b in zip(r["pts"], r["pts"][1:]):
        segs.append((a[0], a[1], b[0], b[1]))
segs = np.array(segs)
mid = np.c_[(segs[:, 0] + segs[:, 2]) / 2, (segs[:, 1] + segs[:, 3]) / 2]
ang = np.arctan2(segs[:, 3] - segs[:, 1], segs[:, 2] - segs[:, 0])


def street_angle(p):
    d = np.hypot(mid[:, 0] - p[0], mid[:, 1] - p[1])
    i = int(np.argmin(d))
    return float(ang[i]), float(d[i])


# districts
lm = {l["name"]: l["pos"] for l in plan["landmarks"]}
willis = lm.get("Willis Tower", [-500, -1000])
cap = lm.get("Texas State Capitol", [-1400, -1100])
CENTRES = {  # (x, y, reach m) — buildings get taller toward these
    "loop": (willis[0] + 450, willis[1] + 250, 1100),
    "rivernorth": (800, 450, 700),
    "austin_dt": (cap[0] + 500, cap[1] + 550, 900),
}


def district(p):
    side = "chicago" if F.sgn["chicago"] * F.csd(p) >= 0 else "austin"
    if side == "chicago":
        k = max(max(0.0, 1 - math.dist(p, CENTRES["loop"][:2]) / CENTRES["loop"][2]),
                max(0.0, 1 - math.dist(p, CENTRES["rivernorth"][:2]) / CENTRES["rivernorth"][2]))
        return side, ("chicago_core" if k > 0.25 else "chicago"), k
    k = max(0.0, 1 - math.dist(p, CENTRES["austin_dt"][:2]) / CENTRES["austin_dt"][2])
    return side, ("austin_dt" if k > 0.2 else "austin_low"), k


def rect_cells_free(c, a, w, d, grid):
    """Sample the rectangle (centre c, angle a, width w along street, depth d) on the grid."""
    ca, sa = math.cos(a), math.sin(a)
    us = np.arange(-w / 2, w / 2 + 0.1, CELL)
    vs = np.arange(-d / 2, d / 2 + 0.1, CELL)
    U, Vv = np.meshgrid(us, vs)
    X = c[0] + U * ca - Vv * sa
    Y = c[1] + U * sa + Vv * ca
    ci = ((X - x0) / CELL).astype(int); ri = ((Y - y0) / CELL).astype(int)
    if ci.min() < 0 or ri.min() < 0 or ci.max() >= NX or ri.max() >= NY:
        return False, None
    return not grid[ri, ci].any(), (ri, ci)


buildings = []
SIZES = [(46, 40), (40, 34), (34, 30), (28, 26), (22, 22), (18, 16)]
cands = [(x, y) for y in np.arange(y0 + 40, y1 - 40, 14.0) for x in np.arange(x0 + 40, x1 - 40, 14.0)]
rng.shuffle(cands)
for (x, y) in cands:
    c = (float(x + rng.uniform(-5, 5)), float(y + rng.uniform(-5, 5)))
    ci, ri = int((c[0] - x0) / CELL), int((c[1] - y0) / CELL)
    if used[ri, ci]:
        continue
    a, dist = street_angle(c)
    if dist > 140:
        continue
    side, dname, k = district(c)
    for w, d in SIZES:
        if dname == "austin_low" and w > 30:
            continue
        ok, cells = rect_cells_free(c, a, w, d, used)
        if not ok:
            continue
        # claim it plus a small gap all round
        ok2, cells2 = rect_cells_free(c, a, w + 6, d + 6, np.zeros_like(used))
        used[cells2] = True
        if dname == "chicago_core":
            h = 60 + 260 * k ** 1.4 * rng.uniform(0.55, 1.0)
        elif dname == "chicago":
            h = rng.uniform(18, 70)
        elif dname == "austin_dt":
            h = 40 + 200 * k ** 1.3 * rng.uniform(0.5, 1.0)
        else:
            h = rng.uniform(7, 24)
        style = {"chicago_core": "tower", "chicago": "tower", "austin_dt": "glass", "austin_low": "lowrise"}[dname]
        buildings.append({"x": round(c[0], 1), "y": round(c[1], 1), "yaw": round(math.degrees(a), 1), "w": w, "d": d,
                          "h": round(float(h), 1), "district": dname, "style": style})
        break

json.dump({"buildings": buildings, "cell": CELL}, open(sys.argv[3], "w"), separators=(",", ":"))
from collections import Counter
print("buildings", len(buildings), Counter(b["district"] for b in buildings))
print("tallest", max(b["h"] for b in buildings), "m")
