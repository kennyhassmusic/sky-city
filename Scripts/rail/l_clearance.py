"""Offline clearance check for the L (complements the PIE drive test): for every drive-test path in Saved/Rail/drive_runs.json
(outer-lane runs under the L both ways, U-turns, right/left turns through the junctions under the L), the smallest distance
from the car's path to a column footing or stair tower of the placed layout (Saved/Rail/l_layout.json), minus half the car's
width (Roadster ~2.0 m). Also the clearance of every column footing to the nearest travel-lane edge.
Run: python3 -I Scripts/rail/l_clearance.py   -> prints a table, writes Saved/Rail/clearance.json
"""
import json, math, pathlib, sys
sys.argv = [sys.argv[0], "--lib"]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import l_layout as L  # noqa: E402

lay = json.load(open(L.OUTD / "l_layout.json"))
runs = json.load(open(L.OUTD / "drive_runs.json"))["runs"]
HALF_CAR = 1.0
obst = []
for row in lay["instances"]["L_BentColumn"]:
    o, f = (row[0], row[1]), L.unit((row[2], row[3]))
    obst.append(("column", np.array(L.rect(o, f, L.FOOT[0], L.FOOT[1]))))
for row in lay["instances"]["L_StationStairs"]:
    o, f = (row[0], row[1]), L.unit((row[2], row[3]))
    n = L.left(f)

    def Q(x, y):
        return (o[0] + n[0] * x + f[0] * y, o[1] + n[1] * x + f[1] * y)
    obst.append(("stair", np.array([Q(L.PLAT_OUT, 0), Q(L.PLAT_OUT + L.STAIR_W, 0), Q(L.PLAT_OUT + L.STAIR_W, L.STAIR_L), Q(L.PLAT_OUT, L.STAIR_L)])))
cent = np.array([r.mean(0) for k, r in obst])


def seg_dist(P, A, B):
    """Distance from points P (n,2) to segment AB."""
    d = B - A
    L2 = float(d @ d) or 1e-12
    t = np.clip(((P - A) @ d) / L2, 0, 1)
    Q = A + t[:, None] * d
    return np.sqrt(((P - Q) ** 2).sum(1))


def poly_dist(path, poly):
    """Smallest distance between a polyline and a convex polygon (sampled)."""
    edges = [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]
    pts = []
    for a, b in edges:
        for u in np.linspace(0, 1, 6):
            pts.append(a + (b - a) * u)
    pts = np.array(pts)
    best = 1e9
    for a, b in zip(path, path[1:]):
        best = min(best, float(seg_dist(pts, a, b).min()))
        # path point inside polygon -> 0
    for p in path:
        from skimage.measure import points_in_poly
        if points_in_poly(np.array([p]), poly)[0]:
            return 0.0
    return best


res = []
for r in runs:
    if r.get("z"):
        continue
    path = np.array([w[:2] for w in r["wps"]], float)
    # densify
    dense = [path[0]]
    for a, b in zip(path, path[1:]):
        n = max(1, int(np.linalg.norm(b - a) / 2.0))
        for k in range(1, n + 1):
            dense.append(a + (b - a) * k / n)
    dense = np.array(dense)
    lo, hi = dense.min(0) - 30, dense.max(0) + 30
    near = [i for i, c in enumerate(cent) if lo[0] <= c[0] <= hi[0] and lo[1] <= c[1] <= hi[1]]
    best = (1e9, None)
    for i in near:
        dd = np.sqrt(((dense - cent[i]) ** 2).sum(1)).min()
        if dd > 25:
            continue
        d = poly_dist(dense, obst[i][1])
        if d < best[0]:
            best = (d, (obst[i][0], [round(v, 1) for v in cent[i]]))
    res.append({"run": r["name"], "min_gap_m": round(best[0] - HALF_CAR, 2), "nearest": best[1]})
for x in res:
    print(f"{x['run']:18s} gap {x['min_gap_m']:6.2f} m  nearest {x['nearest']}")
json.dump(res, open(L.OUTD / "clearance.json", "w"), indent=0)
