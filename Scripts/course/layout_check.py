"""Offline course layout check (plain python3): where every piece of a course JSON ends, the jumps' take-off speeds, and
whether the generated merge and close connectors can be made (radius >= 15 m, slope <= 35 deg), using the same piece
geometry as SkyCourseModel.cpp's bake (main-line and branch piece ends, not the 0.5 m frames, no clearance check).
For designing test and example courses without the editor; the bake in the game is the authority.
    python3 Scripts/course/layout_check.py Scripts/course/courses/example.json [--verbose]"""
import json, math, sys

LANE, G = 5.5, 25.4   # LANE (m per lane) is set per course in main(): lane_width, or 5.5 for a version 1 file without it, else 8


def course_lane_width(c):
    """The course's lane width as the game reads it: lane_width if given; else 5.5 for version 1 (built for it), 8 for version 2."""
    if "lane_width" in c:
        return float(c["lane_width"])
    return 5.5 if c.get("version", 2) < 2 else 8.0


def frame(yaw):
    return (math.cos(yaw), math.sin(yaw)), (-math.sin(yaw), math.cos(yaw))


def advance(st, fx, ly, z):
    (Fx, Fy), (Lx, Ly) = frame(st["yaw"])
    st["p"] = (st["p"][0] + Fx * fx + Lx * ly, st["p"][1] + Fy * fx + Ly * ly, st["p"][2] + z)


def jump_speed(gap, drop):
    la = math.radians(15)
    rl = 30.0
    zl = rl * (1 - math.cos(la))
    xl = rl * math.sin(la)
    tn, cs = math.tan(la), math.cos(la)
    pad = 16.0
    for _ in range(20):
        k = (zl + tn * (gap + pad * 0.5) - drop) / (gap * (gap + pad))
        m = 2 * k * gap - tn
        if k <= 0 or m <= 0.9:
            break
        pad += 4
    if k <= 1e-6:
        return None, xl, pad
    return math.sqrt(G / (2 * k * cs * cs)), xl, pad


def hermite_check(a, ya, b, yb):
    """min radius and max slope of the bake's best Hermite from (a, heading ya) to (b, heading yb), both level."""
    d = math.dist(a, b)
    best = (-1, 90)
    for k in (0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 1.0, 1.15, 1.3, 1.5):
        ta = (math.cos(ya) * d * k, math.sin(ya) * d * k, 0)
        tb = (math.cos(yb) * d * k, math.sin(yb) * d * k, 0)
        minr, maxs = 1e9, 0
        prev = None
        for i in range(65):
            t = i / 64
            t2 = t * t
            v = [a[j] * (6 * t2 - 6 * t) + ta[j] * (3 * t2 - 4 * t + 1) + b[j] * (-6 * t2 + 6 * t) + tb[j] * (3 * t2 - 2 * t) for j in range(3)]
            acc = [a[j] * (12 * t - 6) + ta[j] * (6 * t - 4) + b[j] * (-12 * t + 6) + tb[j] * (6 * t - 2) for j in range(3)]
            sp = math.sqrt(sum(x * x for x in v))
            if sp < 1e-6:
                minr = 0
                continue
            u = [x / sp for x in v]
            if prev and sum(a * b for a, b in zip(prev, u)) < 0.8:
                minr = 0
            prev = u
            cr = (v[1] * acc[2] - v[2] * acc[1], v[2] * acc[0] - v[0] * acc[2], v[0] * acc[1] - v[1] * acc[0])
            kk = math.sqrt(sum(x * x for x in cr)) / sp ** 3
            if kk > 1e-9:
                minr = min(minr, 1 / kk)
            maxs = max(maxs, math.degrees(math.atan2(abs(v[2]), math.hypot(v[0], v[1]))))
        if minr > best[0] + 1e-6 or (abs(minr - best[0]) < 1e-6 and maxs < best[1]):
            best = (minr, maxs)
    return best


def lay(pieces, st, path, out, verbose):
    for i, p in enumerate(pieces):
        t = p["type"]
        lab = f"{path}[{i}] ({t})"
        w = st["lanes"] * LANE
        if t == "start":
            advance(st, 30, 0, 0)
        elif t in ("finish", "checkpoint"):
            advance(st, 6, 0, 0)
        elif t in ("straight", "booster"):
            advance(st, p.get("length", 30 if t == "straight" else 10), 0, 0)
        elif t == "curve":
            a = math.radians(p.get("angle", 90))
            r = p.get("radius", 40)
            s = 1 if a > 0 else -1
            advance(st, r * math.sin(abs(a)), s * r * (1 - math.cos(abs(a))), 0)
            st["yaw"] += a
            if r < w / 2 + 2:
                out["errors"].append(f"{lab}: radius {r} too tight for {st['lanes']} lanes")
        elif t == "ramp":
            L, h = p.get("length", 30), p.get("rise", 8)
            advance(st, L, 0, h)
            if 1.5 * abs(h) > L:
                out["errors"].append(f"{lab}: steeper than 45 deg")
        elif t == "jump":
            gap, drop = p.get("gap", 20), p.get("drop", 0)
            v, xl, pad = jump_speed(gap, drop)
            out["jumps"].append((lab, None if v is None else round(v, 1), None if v is None else round(v * 2.23694)))
            advance(st, xl + gap + pad, 0, drop)
        elif t == "loop":
            off = p.get("offset", w + 1)
            advance(st, 0, off, 0)
        elif t == "corkscrew":
            L, n = p.get("length", 60), p.get("turns", 1)
            pitch = L / (2 * math.pi * n)
            rh = max(0.6, min(4.0, 0.35 * pitch))
            tot = 2 * math.pi * n
            advance(st, L, rh * math.sin(tot), rh * (1 - math.cos(tot)))
            if L / n < 20:
                out["errors"].append(f"{lab}: twists too fast")
        elif t == "wallride":
            L = p.get("length", 40)
            advance(st, L, 0, 0)
            if L < 4 * w + 6:
                out["errors"].append(f"{lab}: needs {4 * w + 6} m")
        elif t == "lanes":
            n = p["lanes"]
            L = p.get("length", 25)
            al = {"left": 1, "right": -1}.get(p.get("align", "center"), 0)
            advance(st, L, al * (w - n * LANE) * 0.5, 0)
            st["lanes"] = n
        elif t == "split":
            lay_split(p, st, lab, path + f"[{i}]", out, verbose)
        elif t == "close":
            a = st["p"]
            b = out["start"]
            r, s = hermite_check(a, st["yaw"], b, out["start_yaw"])
            out["close"] = {"from": [round(x, 1) for x in a], "yaw": round(math.degrees(st["yaw"]), 1), "dist": round(math.dist(a, b), 1),
                            "min_radius": round(r, 1), "max_slope": round(s, 1), "ok": r >= 15 and s <= 35}
            if not (r >= 15 and s <= 35):
                out["errors"].append(f"{lab}: close connector radius {r:.1f} slope {s:.1f}")
            continue
        out["ends"].append((lab, [round(x, 1) for x in st["p"]], round(math.degrees(st["yaw"]), 1), st["lanes"]))
        for k in range(2):
            out["xs"].append(st["p"][k])


def lay_split(p, st, lab, path, out, verbose):
    w = st["lanes"] * LANE
    L = p.get("length", 30)
    brs = p.get("branches", [])
    lanes = [b.get("lanes", st["lanes"]) for b in brs]
    angs = [b.get("angle", 0) for b in brs]
    order = sorted(range(len(brs)), key=lambda b: (-angs[b], b))
    tot = sum(lanes)
    off = [0] * len(brs)
    edge = w / 2
    for b in order:
        wb = w * lanes[b] / tot
        off[b] = edge - wb / 2
        edge -= wb
    ends = []
    (Fx, Fy), (Lx, Ly) = frame(st["yaw"])
    for b, br in enumerate(brs):
        bs = {"p": (st["p"][0] + Lx * off[b], st["p"][1] + Ly * off[b], st["p"][2]), "yaw": st["yaw"], "lanes": lanes[b]}
        a = math.radians(angs[b])
        if abs(a) > 1e-6:
            r = L / abs(a)
            s = 1 if a > 0 else -1
            advance(bs, r * math.sin(abs(a)), s * r * (1 - math.cos(abs(a))), 0)
        else:
            advance(bs, L, 0, 0)
        bs["yaw"] += a
        lay(br.get("pieces", []), bs, f"{path}.branches[{b}].pieces", out, verbose)
        ends.append(bs)
    # merge (as the bake): ahead of the farthest end along the mean heading
    dx = sum(math.cos(e["yaw"]) for e in ends)
    dy = sum(math.sin(e["yaw"]) for e in ends)
    n = math.hypot(dx, dy)
    D = (dx / n, dy / n)
    Lf = (-D[1], D[0])
    lat = sum((e["p"][0] * Lf[0] + e["p"][1] * Lf[1]) * lanes[b] for b, e in enumerate(ends)) / tot
    z = sum(e["p"][2] * lanes[b] for b, e in enumerate(ends)) / tot
    tmax = max(e["p"][0] * D[0] + e["p"][1] * D[1] for e in ends)
    endlat = [e["p"][0] * Lf[0] + e["p"][1] * Lf[1] for e in ends]
    order = sorted(range(len(brs)), key=lambda b: (-endlat[b], b))
    moff = [0] * len(brs)
    edge = w / 2
    for b in order:
        wb = w * lanes[b] / tot
        moff[b] = edge - wb / 2
        edge -= wb
    my = math.atan2(D[1], D[0])
    found = None
    for extra in (12, 18, 25, 35, 50, 70, 95, 125, 160, 200, 250, 300):
        M = (D[0] * (tmax + extra) + Lf[0] * lat, D[1] * (tmax + extra) + Lf[1] * lat, z)
        bad = []
        for b, e in enumerate(ends):
            sl = (M[0] + Lf[0] * moff[b], M[1] + Lf[1] * moff[b], M[2])
            r, s = hermite_check(e["p"], e["yaw"], sl, my)
            if r < 15 or s > 35:
                bad.append((b, round(r, 1), round(s, 1)))
        if not bad:
            found = (extra, M)
            break
    if not found:
        out["errors"].append(f"{lab}: merge infeasible {bad}")
        M = (D[0] * (tmax + 300) + Lf[0] * lat, D[1] * (tmax + 300) + Lf[1] * lat, z)
        found = (300, M)
    out["merges"].append((lab, found[0], [round(x, 1) for x in found[1]], round(math.degrees(my), 1)))
    st["p"] = found[1]
    st["yaw"] = my
    nout = p.get("merge_lanes", st["lanes"]) or st["lanes"]
    advance(st, p.get("merge_length", 30), 0, 0)
    st["lanes"] = nout


def main():
    path = sys.argv[1]
    verbose = "--verbose" in sys.argv
    global LANE
    c = json.load(open(path))
    LANE = course_lane_width(c)
    print(f"lane width {LANE} m (version {c.get('version')})")
    s = c["start"]
    out = {"errors": [], "ends": [], "jumps": [], "merges": [], "xs": [], "start": (s["x"], s["y"], s["z"]), "start_yaw": math.radians(s.get("yaw", 0))}
    st = {"p": (s["x"], s["y"], s["z"]), "yaw": math.radians(s.get("yaw", 0)), "lanes": c.get("lanes", 2)}
    lay(c["pieces"], st, "pieces", out, verbose)
    for e in out["ends"]:
        print("end", *e)
    for j in out["jumps"]:
        print("jump", *j)
    for m in out["merges"]:
        print("merge", *m)
    if "close" in out:
        print("close", out["close"])
    print("errors:", out["errors"] or "none")


if __name__ == "__main__":
    main()
