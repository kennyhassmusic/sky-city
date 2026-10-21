"""Drive plans through the simplified seam junctions, for Scripts/roads/junction_drive_ue.py (seam-junctions agent).

For each site (plan metres) it takes the traffic.json nodes within R of it, every link arriving there from outside and
every link leaving, and builds routes through the junction: from each arriving street the straightest way on and one
turn (U-turns left out), with about 80 m of run-up along the street before it and 60 m after. Each route gets a start
(plan point + heading) for ASkysterCar::TestTeleport.
Run: python3 -I Scripts/roads/seam_drive_plan.py [traffic=Content/SkyCity/Data/traffic.json] [per_site=4]
Out: Saved/Roads/seam/drive_plan.json
"""
import json, math, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
TR = json.load(open(ROOT / KV.get("traffic", "Content/SkyCity/Data/traffic.json")))
PER = int(KV.get("per_site", "4"))
L = TR["links"]
NODES = {int(k): v for k, v in TR["nodes"].items()}
# the junctions this session simplified (plan metres), with a name for the logs
SITES = [
    ("seam_circle", (-270.0, -284.0), 55.0, 6),
    ("crosstown_bowie", (-421.0, -275.0), 25.0, 3),
    ("crosstown_baylor", (-130.0, -318.0), 30.0, 3),
    ("crosstown_state", (-8.0, -336.0), 25.0, 3),
    ("lake_state", (-8.0, -200.0), 25.0, 3),
    ("eisenhower_guadalupe", (-1120.0, -1352.0), 25.0, 3),
    ("15th_guadalupe", (-1112.0, -1429.0), 30.0, 4),
    ("canal_wacker_10th", (-755.0, -805.0), 40.0, 4),
    ("lamar_reynolds", (-250.0, 8.0), 30.0, 4),
    ("riogrande_8th", (-769.0, -608.0), 25.0, 2),
    ("i35_frontage_canal", (-985.0, -1318.0), 30.0, 3),
    ("i35_lower_lavaca", (-1227.0, -1317.0), 20.0, 2),
]


def unit(v):
    n = math.hypot(v[0], v[1]) or 1e-9
    return (v[0] / n, v[1] / n)


def head_in(l):
    p = l["p"]
    return unit((p[-1][0] - p[-2][0], p[-1][1] - p[-2][1]))


def head_out(l):
    p = l["p"]
    return unit((p[1][0] - p[0][0], p[1][1] - p[0][1]))


def length(l):
    return sum(math.dist(a, b) for a, b in zip(l["p"], l["p"][1:]))


out_of = {}
into = {}
for i, l in enumerate(L):
    out_of.setdefault(l["a"], []).append(i)
    into.setdefault(l["b"], []).append(i)


def through(entry, exits, inside):
    """Shortest link chain from the end of `entry` to the start of one of `exits`, inside the site."""
    best = {}
    front = [(0.0, entry, [entry])]
    while front:
        front.sort()
        d, li, path = front.pop(0)
        if li in exits and li != entry:
            return path
        if li in best and best[li] <= d:
            continue
        best[li] = d
        for nx in out_of.get(L[li]["b"], []):
            if L[nx]["b"] == L[li]["a"] and L[nx]["a"] == L[li]["b"]:
                continue                     # straight back
            if nx in exits or L[nx]["b"] in inside:
                front.append((d + length(L[nx]), nx, path + [nx]))
    return None


def extend_back(li, metres):
    chain = [li]
    acc = 0.0
    while acc < metres:
        cands = [k for k in into.get(L[chain[0]]["a"], []) if not (L[k]["a"] == L[chain[0]]["b"])]
        if not cands:
            break
        h = head_out(L[chain[0]])
        k = max(cands, key=lambda k: head_in(L[k])[0] * h[0] + head_in(L[k])[1] * h[1])
        if head_in(L[k])[0] * h[0] + head_in(L[k])[1] * h[1] < 0.5 or k in chain:
            break
        chain.insert(0, k)
        acc += length(L[k])
    return chain


def extend_fwd(li, metres):
    chain = [li]
    acc = 0.0
    while acc < metres:
        cands = [k for k in out_of.get(L[chain[-1]]["b"], []) if not (L[k]["b"] == L[chain[-1]]["a"])]
        if not cands:
            break
        h = head_in(L[chain[-1]])
        k = max(cands, key=lambda k: head_out(L[k])[0] * h[0] + head_out(L[k])[1] * h[1])
        if k in chain:
            break
        chain.append(k)
        acc += length(L[k])
    return chain


plan = {"traffic": KV.get("traffic", "Content/SkyCity/Data/traffic.json"), "sites": []}
for name, c, R, per in SITES:
    inside = {n for n, p in NODES.items() if math.dist(p, c) < R}
    if not inside:
        plan["sites"].append({"name": name, "c": c, "routes": [], "note": "no traffic node near"})
        continue
    entries = [i for i, l in enumerate(L) if l["b"] in inside and l["a"] not in inside]
    exits = {i for i, l in enumerate(L) if l["a"] in inside and l["b"] not in inside}
    routes = []
    for e in sorted(entries, key=lambda i: -length(L[i])):
        hin = head_in(L[e])
        opts = []
        for x in exits:
            if L[x]["b"] == L[e]["a"]:
                continue
            ho = head_out(L[x])
            dot = hin[0] * ho[0] + hin[1] * ho[1]
            if dot < -0.85:
                continue                          # U-turn
            path = through(e, {x}, inside)
            if path:
                cr = hin[0] * ho[1] - hin[1] * ho[0]
                opts.append((dot, "S" if dot > 0.7 else ("L" if cr > 0 else "R"), path))
        opts.sort(key=lambda o: -o[0])
        picked = opts[:1] + [o for o in opts[1:] if o[1] != opts[0][1]][:1] if opts else []
        for dot, mv, path in picked:
            full = extend_back(path[0], 80.0)[:-1] + path + extend_fwd(path[-1], 60.0)[1:]
            p0 = L[full[0]]["p"]
            o = L[full[0]]["o"]
            off = o[len(o) // 2]
            t = unit((p0[1][0] - p0[0][0], p0[1][1] - p0[0][1]))
            start = (p0[0][0] + t[1] * off, p0[0][1] - t[0] * off)
            routes.append({"move": mv, "links": full, "names": [L[k].get("n", "") for k in full],
                           "start": [round(start[0], 2), round(start[1], 2)],
                           "yaw_plan": round(math.degrees(math.atan2(t[0], t[1])), 1),
                           "m": round(sum(length(L[k]) for k in full))})
        if len(routes) >= per:
            break
    plan["sites"].append({"name": name, "c": c, "routes": routes[:per]})
    print(name, len(routes[:per]), [r["move"] for r in routes[:per]])
json.dump(plan, open(ROOT / "Saved/Roads/seam/drive_plan.json", "w"), indent=1)
print("wrote Saved/Roads/seam/drive_plan.json")
