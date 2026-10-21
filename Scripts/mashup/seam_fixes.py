"""Plan fixes at the Chicago-Austin seam: the connector roads the mashup added, corrected by rules, as a layer on top of
the plan (Saved/Mashup/seam_fixes.json) that Scripts/roads/roadnet.py applies when it reads the streets.

Why: Kenny (20 Oct night) found "major logical street messes at major intersections" in Austin "where some of the
streets were supposed to merge (chicago to austin)". The audit (Scripts/roads/seam_audit.py) traced most of them to the
connector roads in plan_v3.json: the 66 "stitch" pieces of integrate_v2.py and the 6 "sketch" roads of apply_sketch.py
(Kenny's 19 Oct sketch). Two things go wrong with them:
  1. Attributes. The street pass (Scripts/streets/build_street_data.py) gives every plan road the lanes and one-way of
     the OpenStreetMap way it lies on. A connector lies on nothing of its own, so it took whatever was nearest: the
     Crosstown Parkway became a 6-lane ONE-WAY road beside West 5th Street (also one-way, the other way), the Seam Circle
     a 3-lane one-way loop, Lake Shore Drive's continuation two one-ways in the SAME direction, short stitches one-way
     against the streets they join.
  2. Geometry. Kenny's strokes were smoothed into centrelines, but where a stroke ran along an existing street the road
     was drawn ON it, wiggling across it (the Crosstown Parkway crosses West 5th Street 14 times between Nueces and
     the Seam Circle: one junction node per crossing); the Ida B. Wells ramp is a scribble that doubles back three times
     along West 15th Street; streets run straight through the Seam Circle's island.
This script leaves plan_v3.json alone (other tools read it) and writes the corrections as data, each with its rule:
  R1 connector attributes   a stitch road continues the city streets it joins: it takes their lanes and one-way
                            (a one-way continues in the same direction; if the two ends disagree, two-way). Unnamed
                            expressway stitches take the expressway's. Kenny's sketch roads get a design (DESIGN).
  R2 sketch roads on streets where a sketch road runs along an existing street (parallel, within the two half-widths
                            + 3 m, for 30 m or more, small detours between such stretches included) that stretch IS
                            the street: the sketch road is cut there, and the street takes the sketch road's design and
                            name (Austin streets and stitches at least half under it; others only if 80 % under it).
  R3 scribbles              what is left of a sketch road is split where it folds back on itself (> 150 deg within
                            60 m); a part that mostly runs along another road (> 50 %) or is shorter than 30 m goes.
  R4 roundabout             a closed sketch loop is a roundabout: one-way counter-clockwise (right-hand traffic),
                            2 circulating lanes; every other road is cut back to the ring (nothing crosses the island).
  R5 frontage roads         in the seam zone, a one-way "... Service Road" (or a one-way piece of the same street) that
                            runs within 35 m alongside its main street for most of its length is dropped, if the
                            network stays connected (the cross streets reach the main street anyway).
  R6 street gaps            two pieces of the same street whose free ends face each other across <= 25 m of land,
                            beside a connector, are joined.
  R7 I-35 at grade          (highway-capitol's requests) frontage roads at the I-35's east foot and lower lanes under
                            its decks, built from Saved/Expressway/expressway_layout.json.
  R8 Wacker expressway ends (highway-capitol's request 8) South Wacker Drive's carriageways narrowed to two lanes each
                            beside the south ramp's fill strip; a T junction link from the north touchdown to the
                            Crosstown Parkway.
Output: Saved/Mashup/seam_fixes.json {attrs: {plan_i: {...}}, drop: {plan_i: why}, parts: {plan_i: [polylines]},
        add: [new roads], rules, log}. Run: python3 -I Scripts/mashup/seam_fixes.py   (then python3 -I Scripts/roads/roadnet.py)
"""
import collections, json, math, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLAN = json.load(open(ROOT / "Saved/Mashup/plan_v3.json"))
SD = json.load(open(ROOT / "Saved/Streets/street_data.json"))
OUT = ROOT / "Saved/Mashup/seam_fixes.json"
R = PLAN["roads"]
SR = {r["plan_i"]: r for r in SD["roads"]}
DRIVE = ("highway", "major", "mid", "minor")
CONNECTOR = ("stitch", "sketch", "new")
RANK = {"minor": 0, "mid": 1, "major": 2, "highway": 3}
SEAM = PLAN["seam"]
log = []

# Kenny's sketch roads (his names): what each was meant to be, from his sketch notes (sky-city-session1.md, apply_sketch.py)
DESIGN = {
    # "cross-town road with a roundabout where it meets the north-south main road": a two-way crosstown arterial
    "Crosstown Parkway": {"cls": "major", "lanes": 6, "oneway": False, "speed": 35, "rename_hosts": True, "takes_over": True},
    # the roundabout: two circulating lanes, counter-clockwise
    "Seam Circle": {"cls": "major", "lanes": 2, "oneway": True, "speed": 25, "roundabout": True},
    # "a ramp to the parallel street" (West 15th) from the Ida B. Wells Expressway: two-way where it survives R2/R3
    "Ida B. Wells ramp": {"cls": "mid", "lanes": 2, "oneway": False, "speed": 30},
}
# highway-capitol renamed the sketch's expressway past the Capitol to Interstate 35 (Scripts/roads/expressway_names.py,
# 20 Oct 22:36): its ramp is now "Interstate 35 Frontage Road"; same design under either name
DESIGN["Interstate 35 Frontage Road"] = DESIGN["Ida B. Wells ramp"]


# ---------------------------------------------------------------- helpers
def unit(v):
    L = math.hypot(v[0], v[1]) or 1e-12
    return (v[0] / L, v[1] / L)


def cumlen(pts):
    s = [0.0]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + math.dist(a, b))
    return s


def at_s(pts, sc, s):
    s = max(0.0, min(sc[-1], s))
    for i in range(len(pts) - 1):
        if sc[i + 1] >= s:
            seg = (sc[i + 1] - sc[i]) or 1e-9
            t = (s - sc[i]) / seg
            a, b = pts[i], pts[i + 1]
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), unit((b[0] - a[0], b[1] - a[1]))
    return tuple(pts[-1]), unit((pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]))


def sub(pts, sc, s0, s1):
    if s1 - s0 < 0.5:
        return []
    out = [at_s(pts, sc, s0)[0]]
    out += [tuple(p) for p, s in zip(pts, sc) if s0 + 1e-6 < s < s1 - 1e-6]
    out.append(at_s(pts, sc, s1)[0])
    return out


def closest(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy or 1e-12
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    q = (a[0] + dx * t, a[1] + dy * t)
    return math.dist(p, q), q, t


def width(i):
    s = SR.get(i)
    return s["width"] if s else 10.0


def live(i):
    s = SR.get(i)
    return (s is not None and R[i]["cls"] in DRIVE and not s["skip"] and not s["elevated"] and not R[i].get("elevated")
            and len(R[i]["pts"]) >= 2)


def dist_seam(p):
    return min(closest(p, a, b)[0] for a, b in zip(SEAM, SEAM[1:]))


class Grid:
    def __init__(self, cell=25.0):
        self.c, self.g = cell, collections.defaultdict(list)

    def add_poly(self, pts, payload):
        for a, b in zip(pts, pts[1:]):
            for gx in range(int(min(a[0], b[0]) // self.c), int(max(a[0], b[0]) // self.c) + 1):
                for gy in range(int(min(a[1], b[1]) // self.c), int(max(a[1], b[1]) // self.c) + 1):
                    self.g[(gx, gy)].append((tuple(a), tuple(b), payload))

    def near(self, p, r):
        seen = set()
        for gx in range(int((p[0] - r) // self.c), int((p[0] + r) // self.c) + 1):
            for gy in range(int((p[1] - r) // self.c), int((p[1] + r) // self.c) + 1):
                for it in self.g.get((gx, gy), ()):
                    if id(it) not in seen:
                        seen.add(id(it))
                        yield it


attrs, drop, parts = {}, {}, {}
base = [i for i in range(len(R)) if live(i) and R[i]["city"] not in CONNECTOR]
conn = [i for i in range(len(R)) if live(i) and R[i]["city"] in CONNECTOR]
G_BASE = Grid()
for i in base:
    G_BASE.add_poly(R[i]["pts"], i)


def travel_of(i):
    s = SR[i]
    return (-1 if s["reverse"] else 1) if s["oneway"] else 0


def flow_at_end(i, end_pt):
    """For a one-way road i: +1 if its traffic flows toward end_pt (the end of i nearest end_pt), -1 away, 0 two-way."""
    t = travel_of(i)
    if not t:
        return 0
    p = R[i]["pts"]
    at_last = math.dist(p[-1], end_pt) <= math.dist(p[0], end_pt)
    return t if at_last else -t


# ---------------------------------------------------------------- R2 + R3: sketch roads on streets, scribbles
def ride_runs(pts, w, grid, exclude=(), min_run=30.0, step=3.0):
    """Samples along pts that lie on another road (parallel, within the half-widths + 3 m): returns per-sample host
    ids (or None) and the sample spacing."""
    sc = cumlen(pts)
    L = sc[-1]
    n = max(2, int(L / step))
    hosts = []
    for k in range(n + 1):
        p, t = at_s(pts, sc, L * k / n)
        best = None
        for a, b, j in grid.near(p, 20.0):
            if j in exclude:
                continue
            d, q, _ = closest(p, a, b)
            tt = unit((b[0] - a[0], b[1] - a[1]))
            if abs(t[0] * tt[0] + t[1] * tt[1]) < 0.9:
                continue
            if d < (w + width(j)) / 2 + 3.0 and (best is None or d < best[0]):
                best = (d, j)
        hosts.append(best[1] if best else None)
    return hosts, L / n, sc


def runs_of(hosts, ds, same=lambda a, b: a == b):
    """[(k0, k1, host)] maximal runs of samples on the same host (by `same`)."""
    out, k = [], 0
    while k < len(hosts):
        if hosts[k] is None:
            k += 1
            continue
        j = k
        while j + 1 < len(hosts) and hosts[j + 1] is not None and same(hosts[j + 1], hosts[k]):
            j += 1
        out.append([k, j, hosts[k]])
        k = j + 1
    return out


def hairpin_cuts(pts, sc, span=60.0, ang=150.0):
    """Arc lengths where the polyline folds back: heading over the next `span` m turns more than `ang` degrees
    against the heading over the last `span` m; one cut per fold (at its apex)."""
    L = sc[-1]
    cuts, s = [], span
    while s < L - span:
        p0, _ = at_s(pts, sc, s - span)
        p1, _ = at_s(pts, sc, s)
        p2, _ = at_s(pts, sc, s + span)
        a, b = unit((p1[0] - p0[0], p1[1] - p0[1])), unit((p2[0] - p1[0], p2[1] - p1[1]))
        if math.degrees(math.acos(max(-1, min(1, a[0] * b[0] + a[1] * b[1])))) > ang:
            # apex: the point farthest from the chord p0-p2 within the window
            best = max((closest(at_s(pts, sc, x)[0], p0, p2)[0], x) for x in [s - span + i for i in range(0, int(2 * span) + 1, 2)])
            cuts.append(best[1])
            s = best[1] + span
            continue
        s += 3.0
    return cuts


host_upgrade = collections.defaultdict(dict)        # host plan_i -> design attrs (from the sketch road riding it)
for i in conn:
    r = R[i]
    if r["city"] != "sketch":
        continue
    des = DESIGN.get(r["name"], {})
    if des.get("roundabout"):
        continue
    pts = [tuple(p) for p in r["pts"]]
    w = 3.3 * des.get("lanes", SR[i]["lanes"])
    hosts, ds, sc = ride_runs(pts, w, G_BASE)
    name_of = lambda j: R[j]["name"] or f"#{j}"
    rr = runs_of(hosts, ds, lambda a, b: name_of(a) == name_of(b))
    # detours between two stretches on the same street (shorter than 160 m) are part of it
    merged = []
    for run in rr:
        if merged and name_of(merged[-1][2]) == name_of(run[2]) and (run[0] - merged[-1][1]) * ds < 160.0:
            merged[-1][1] = run[1]
        else:
            merged.append(run)
    riding = [(k0 * ds, k1 * ds, h) for k0, k1, h in merged if (k1 - k0) * ds >= 30.0]
    if not riding:
        continue
    # hosts: every base road sampled inside a riding stretch
    hcount = collections.Counter()
    for k0, k1, h in merged:
        if (k1 - k0) * ds >= 30.0:
            for k in range(k0, k1 + 1):
                if hosts[k] is not None:
                    hcount[hosts[k]] += ds
    keep, s_prev = [], 0.0
    for s0, s1, h in riding:
        keep.append((s_prev, s0))
        s_prev = s1
    keep.append((s_prev, sc[-1]))
    pieces = []
    for s0, s1 in keep:
        if s1 - s0 < 1.0:
            continue
        # R3: split at folds
        cuts = [c for c in hairpin_cuts(pts, sc) if s0 < c < s1]
        edges = [s0] + cuts + [s1]
        for a_, b_ in zip(edges, edges[1:]):
            pc = sub(pts, sc, a_, b_)
            if len(pc) >= 2:
                pieces.append(pc)
    kept = []
    G_KEPT = Grid()
    for pc in sorted(pieces, key=lambda p: -cumlen(p)[-1]):
        L = cumlen(pc)[-1]
        if L < 30.0:
            log.append(f"R3 {r['name']}: a {L:.0f} m piece left between stretches on other streets dropped")
            continue
        h1, ds1, _ = ride_runs(pc, w, G_BASE)
        h2, _, _ = ride_runs(pc, w, G_KEPT)
        on = sum(1 for a_, b_ in zip(h1, h2) if a_ is not None or b_ is not None) / len(h1)
        if on > 0.5:
            log.append(f"R3 {r['name']}: a {L:.0f} m piece that runs {on:.0%} along other roads dropped")
            continue
        kept.append([[round(x, 2), round(y, 2)] for x, y in pc])
        G_KEPT.add_poly(pc, -1)
    parts[i] = kept
    tot = sum(s1 - s0 for s0, s1, _ in riding)
    log.append(f"R2 {r['name']} (plan {i}): {tot:.0f} of {sc[-1]:.0f} m run on existing streets "
               f"({', '.join(sorted({name_of(h) for _, _, h in riding}))}); {len(kept)} piece(s) kept")
    if not kept:
        drop[i] = f"R2/R3: all of {r['name']} runs along existing streets or doubles back on itself"
    # stitch pieces inside the riding stretches are part of the street too (West Randolph's stitch between West 5th
    # Street and Randolph): count how much of each lies under the sketch road
    G_ST = Grid()
    for j in conn:
        if R[j]["city"] == "stitch":
            G_ST.add_poly(R[j]["pts"], j)
    hs, ds2, _ = ride_runs(pts, w, G_ST)
    for k_, hh in enumerate(hs):
        if hh is not None and any(s0 <= k_ * ds2 <= s1 for s0, s1, _ in riding):
            hcount[hh] += ds2
    for h, m in hcount.items():
        Lh = cumlen(R[h]["pts"])[-1]
        cover = m / max(Lh, 1.0)
        # (a street only partly under the sketch road keeps its own design: the sketch road starts at a junction on it)
        # (only a sketch road that is a street of its own takes over the street under it: the Crosstown Parkway; a ramp
        # drawn along a street leaves the street as it is). Chicago streets only where they touch a stitch (the seam).
        touches_stitch = any(min(math.dist(q, e_) for q in (R[h]["pts"][0], R[h]["pts"][-1])) < 8.0
                             for j in conn if R[j]["city"] == "stitch" for e_ in (R[j]["pts"][0], R[j]["pts"][-1]))
        if des.get("takes_over") and ((R[h]["city"] in ("austin", "stitch") and cover >= 0.5) or (cover >= 0.8 and touches_stitch)):
            host_upgrade[h] = {"design": r["name"], "cover": round(cover, 2)}

# ---------------------------------------------------------------- R1: connector attributes
end_index = collections.defaultdict(list)            # rounded endpoint -> [plan_i]
for i in base + conn:
    for p in (R[i]["pts"][0], R[i]["pts"][-1]):
        end_index[(round(p[0] / 5), round(p[1] / 5))].append(i)


def partners_at(p, i, r=25.0):
    """Base roads that end within r of p or pass within 6 m of it."""
    out = {}
    for a, b, j in G_BASE.near(p, r):
        if j == i:
            continue
        d, q, t = closest(p, a, b)
        pj = R[j]["pts"]
        de = min(math.dist(p, pj[0]), math.dist(p, pj[-1]))
        if de < r or d < 6.0:
            out[j] = min(out.get(j, 1e9), de)
    return out


def set_attrs(i, a, why):
    cur = attrs.setdefault(str(i), {})
    cur.update(a)
    cur["why"] = (cur.get("why", "") + "; " if cur.get("why") else "") + why


for i in conn:
    r, s = R[i], SR[i]
    if i in drop:
        continue
    if r["city"] == "sketch":
        des = DESIGN.get(r["name"])
        if des:
            a = {k: des[k] for k in ("cls", "lanes", "oneway", "speed") if k in des}
            if des.get("roundabout"):
                # counter-clockwise: the signed area of the loop as drawn tells which way round it runs
                p = r["pts"]
                area = sum(p[k][0] * p[(k + 1) % len(p)][1] - p[(k + 1) % len(p)][0] * p[k][1] for k in range(len(p))) / 2
                a.update({"reverse": area < 0, "roundabout": True})
            else:
                a["reverse"] = False
            set_attrs(i, a, f"R1 Kenny's sketch: {r['name']} as designed")
        continue
    ends = [tuple(r["pts"][0]), tuple(r["pts"][-1])]
    named = bool(r["name"])
    votes = []
    for e_i, p in enumerate(ends):
        cand = partners_at(p, i)
        if named:
            cand = {j: d for j, d in cand.items() if R[j]["name"] == r["name"]} or \
                   ({j: d for j, d in cand.items() if R[j]["cls"] == "highway"} if r["cls"] == "highway" else {})
        elif r["cls"] == "highway":
            cand = {j: d for j, d in cand.items() if R[j]["cls"] == "highway"}
        else:
            cand = {}
        if not cand:
            continue
        j = min(cand, key=lambda j: (-RANK[R[j]["cls"]], cand[j]))
        fl = flow_at_end(j, p)            # +1: partner flows toward the shared point (so we flow away from this end)
        # our travel along our geometry (first -> last): away from end 0 = +1, away from end 1 = -1
        tr = 0 if fl == 0 else (fl if e_i == 0 else -fl)
        votes.append((j, tr, SR[j]["lanes"]))
    if not votes:
        a = {"oneway": False, "reverse": False,
             "lanes": {"highway": 4, "major": 4, "mid": 2, "minor": 2}[r["cls"]]}
        set_attrs(i, a, "R1 connector with no partner street: two-way, lanes by class")
        continue
    trs = {tr for _, tr, _ in votes}
    if len(trs) == 1 and 0 not in trs:
        tr = trs.pop()
        lanes = min(l for _, _, l in votes)
        set_attrs(i, {"oneway": True, "reverse": tr < 0, "lanes": lanes},
                  "R1 continues one-way " + " / ".join(sorted({R[j]["name"] or R[j]["cls"] for j, _, _ in votes})) + " in its direction")
    else:
        two = [l for j, tr, l in votes if tr == 0]
        lanes = max(two) if two else max(2, min(l for _, _, l in votes))
        lanes = max(2, lanes + (lanes % 2 if r["cls"] != "major" else 0))
        set_attrs(i, {"oneway": False, "reverse": False, "lanes": lanes},
                  "R1 joins " + " / ".join(sorted({R[j]["name"] or R[j]["cls"] for j, _, _ in votes})) +
                  (" (two-way)" if two else " (one-ways that disagree)") + ": two-way")

# R1 (cont.): a connector that carries an expressway's traffic (it touches an expressway or an expressway stitch at an
# end) is the expressway's surface continuation (as Congress Parkway is at the end of the Eisenhower in Chicago): a
# two-way arterial with two lanes each way, not a one-lane one-way side street
HW = [j for j in base if R[j]["cls"] == "highway"] + [j for j in conn if R[j]["cls"] == "highway"]
G_HW = Grid()
for j in HW:
    G_HW.add_poly(R[j]["pts"], j)
def end_kind(i, p):
    """What end point p of road i touches: 'hw' (the end of an expressway piece), 'street' (a city street), or None."""
    hw = street = False
    for a, b, j in G_BASE.near(p, 8.0):
        if j == i or closest(p, a, b)[0] >= 6.0:
            continue
        if R[j]["cls"] == "highway":
            pj = R[j]["pts"]
            hw = hw or min(math.dist(p, pj[0]), math.dist(p, pj[-1])) < 8.0
        else:
            street = True
    for a, b, j in G_HW.near(p, 8.0):
        if j != i and R[j]["city"] in CONNECTOR and closest(p, a, b)[0] < 6.0:
            pj = R[j]["pts"]
            hw = hw or min(math.dist(p, pj[0]), math.dist(p, pj[-1])) < 8.0
    return "street" if street and not hw else ("hw" if hw else None)


for i in conn:
    if i in drop or R[i]["city"] == "sketch":
        continue
    k0, k1 = end_kind(i, R[i]["pts"][0]), end_kind(i, R[i]["pts"][-1])
    if {k0, k1} == {"hw", "street"}:
        set_attrs(i, {"cls": "major", "lanes": 4, "oneway": False, "reverse": False},
                  "R1 links an expressway end to a city street: the expressway's surface continuation, two-way, 2 lanes each way")
        attrs[str(i)]["hw_cont"] = True
# ... and a connector that carries such a continuation on to the next street does too (West Congress Parkway after the
# Eisenhower's end)
G_CONT = Grid()
for k_, a_ in attrs.items():
    if a_.get("hw_cont"):
        G_CONT.add_poly(R[int(k_)]["pts"], int(k_))
for i in conn:
    if i in drop or R[i]["city"] == "sketch" or attrs.get(str(i), {}).get("hw_cont"):
        continue
    e0, e1 = R[i]["pts"][0], R[i]["pts"][-1]
    t0 = any(closest(e0, a, b)[0] < 6.0 for a, b, j in G_CONT.near(e0, 8.0) if j != i)
    t1 = any(closest(e1, a, b)[0] < 6.0 for a, b, j in G_CONT.near(e1, 8.0) if j != i)
    if (t0 and end_kind(i, e1) == "street") or (t1 and end_kind(i, e0) == "street"):
        set_attrs(i, {"cls": "major", "lanes": 4, "oneway": False, "reverse": False},
                  "R1 carries an expressway's surface continuation on to the next street: two-way, 2 lanes each way")

# hosts of a sketch road take its design (and, in Austin, its name)
for h, info in host_upgrade.items():
    des = DESIGN[info["design"]]
    a = {k: des[k] for k in ("cls", "lanes", "oneway", "speed") if k in des}
    a["reverse"] = False
    if des.get("rename_hosts") and R[h]["city"] in ("austin", "stitch"):
        a["name"] = info["design"]
    set_attrs(h, a, f"R2 carries {info['design']} ({info['cover']:.0%} of it under the sketch road)")
# stitches that carry a sketch road keep its design (a host stitch got R1 first; R2 wins)

# ---------------------------------------------------------------- R4: roundabouts
for i in conn:
    r = R[i]
    if not DESIGN.get(r["name"], {}).get("roundabout"):
        continue
    p = r["pts"]
    c = (sum(q[0] for q in p) / len(p), sum(q[1] for q in p) / len(p))
    rad = sum(math.dist(q, c) for q in p) / len(p)
    attrs[str(i)]["centre"] = [round(c[0], 2), round(c[1], 2)]
    attrs[str(i)]["radius"] = round(rad, 2)
    for j in base + conn:
        if j == i or j in drop:
            continue
        pj = [tuple(q) for q in (parts[j][0] if j in parts and len(parts[j]) == 1 else R[j]["pts"])]
        if j in parts and len(parts[j]) != 1:
            continue
        if min(math.dist(q, c) for q in pj) > rad + 15:
            continue
        # cut the polyline where it enters the circle: keep the pieces outside, ending exactly on the ring
        sc = cumlen(pj)
        n = max(2, int(sc[-1] / 0.5))
        inside = [math.dist(at_s(pj, sc, sc[-1] * k / n)[0], c) < rad for k in range(n + 1)]
        if not any(inside):
            continue
        segs, k = [], 0
        while k <= n:
            if inside[k]:
                k += 1
                continue
            k1 = k
            while k1 + 1 <= n and not inside[k1 + 1]:
                k1 += 1
            segs.append((sc[-1] * k / n, sc[-1] * k1 / n))
            k = k1 + 1
        newp = [sub(pj, sc, a_, b_) for a_, b_ in segs if b_ - a_ >= 8.0]
        newp = [[[round(x, 2), round(y, 2)] for x, y in q] for q in newp if len(q) >= 2]
        if newp:
            parts[j] = newp
        else:
            drop[j] = f"R4 lies inside {r['name']}"
        log.append(f"R4 {R[j]['name'] or R[j]['cls']} (plan {j}) cut back to the ring of {r['name']}: {len(newp)} piece(s)")

# ---------------------------------------------------------------- R6: gaps in a street (seam zone)
# Two pieces of the same street whose free ends face each other across a gap of up to 25 m (the plan lost the piece
# between, usually where a crossing street was removed at the seam) are joined, so the street doesn't end in two dead
# ends in a row (North Lamar Boulevard south of the Seam Circle).
def free_end(i, e, grid=None):
    for a, b, j in (grid or G_BASE).near(e, 8.0):
        if j == i or j in drop:
            continue
        if closest(e, a, b)[0] < 6.0:
            return False
    return True


ends = []
for i in base:
    if i in drop or (i in parts and len(parts[i]) != 1):
        continue
    pc = parts[i][0] if i in parts else [list(q) for q in R[i]["pts"]]
    for end in (0, -1):
        ends.append((i, end, pc))
joined = set()
CONN_GRID = Grid()
for i in conn:
    if i not in drop:
        for pc in (parts.get(i) or [R[i]["pts"]]):
            CONN_GRID.add_poly(pc, i)


def near_conn(p, r):
    return any(closest(p, a, b)[0] < r for a, b, _ in CONN_GRID.near(p, r))


def on_land_plan(p):
    # plan water outer rings minus islands (ray casting; the rings are big, so only the ones whose box holds p)
    def inside(ring):
        c = False
        for k in range(len(ring)):
            a, b = ring[k], ring[k - 1]
            if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0] - a[0]) * (p[1] - a[1]) / ((b[1] - a[1]) or 1e-12) + a[0]:
                c = not c
        return c
    wet = any(inside(r) for r in PLAN["water"]["outer"] if min(q[0] for q in r) <= p[0] <= max(q[0] for q in r)
              and min(q[1] for q in r) <= p[1] <= max(q[1] for q in r))
    isl = any(inside(r) for r in PLAN["water"]["inner"] if min(q[0] for q in r) <= p[0] <= max(q[0] for q in r)
              and min(q[1] for q in r) <= p[1] <= max(q[1] for q in r))
    return (not wet) or isl
for i, ei, pi_ in ends:
    if i in joined or not R[i]["name"]:
        continue
    e = pi_[ei]
    if not near_conn(e, 120.0):
        continue                        # only beside the connectors (the gaps the stitching left)
    nb = pi_[1] if ei == 0 else pi_[-2]
    out = unit((e[0] - nb[0], e[1] - nb[1]))
    for j, ej, pj in ends:
        if j == i or j in joined or R[j]["name"] != R[i]["name"]:
            continue
        f = pj[ej]
        gap = math.dist(e, f)
        if not (1.0 < gap <= 25.0):
            continue
        nb2 = pj[1] if ej == 0 else pj[-2]
        out2 = unit((f[0] - nb2[0], f[1] - nb2[1]))
        g = unit((f[0] - e[0], f[1] - e[1]))
        if out[0] * g[0] + out[1] * g[1] < 0.85 or -(out2[0] * g[0] + out2[1] * g[1]) < 0.85:
            continue
        if not (free_end(i, e) and free_end(j, f)) or not on_land_plan(((e[0] + f[0]) / 2, (e[1] + f[1]) / 2)):
            continue                    # (gaps over water are bridges: roadnet joins those)
        if ei == 0:
            pi_.insert(0, [round(f[0], 2), round(f[1], 2)])
        else:
            pi_.append([round(f[0], 2), round(f[1], 2)])
        parts[i] = [pi_]
        joined.update((i, j))
        log.append(f"R6 {R[i]['name']} (plan {i}) joined across a {gap:.0f} m gap to plan {j}")
        break

# the streets as they stand now (after the cuts and joins above), for the free-end test below
G_NOW = Grid()
for j in base + conn:
    if j not in drop:
        for pc in (parts.get(j) or [R[j]["pts"]]):
            G_NOW.add_poly(pc, j)
# R4 (cont.): a street that stops just short of the ring, heading for it, is carried on to it (the leg the roundabout is
# for: North Lamar Boulevard south of the circle stopped 3 m short, and 16 m short of its next piece)
for i in conn:
    r = R[i]
    if not DESIGN.get(r["name"], {}).get("roundabout"):
        continue
    c, rad = attrs[str(i)]["centre"], attrs[str(i)]["radius"]
    for j in base + conn:
        if j == i or j in drop:
            continue
        plist = parts.get(j) or [[list(q) for q in R[j]["pts"]]]
        changed = False
        for pc in plist:
            for end in (0, -1):
                e = pc[end]
                nb = pc[1] if end == 0 else pc[-2]
                dc = math.dist(e, c)
                if not (rad + 0.5 < dc < rad + 50.0) or not free_end(j, e, G_NOW):
                    continue
                out = unit((e[0] - nb[0], e[1] - nb[1]))
                toc = unit((c[0] - e[0], c[1] - e[1]))
                if out[0] * toc[0] + out[1] * toc[1] < 0.85:
                    continue
                q = [c[0] - toc[0] * rad, c[1] - toc[1] * rad]
                q = [round(q[0], 2), round(q[1], 2)]
                if end == 0:
                    pc.insert(0, q)
                else:
                    pc.append(q)
                changed = True
                log.append(f"R4 {R[j]['name'] or R[j]['cls']} (plan {j}) carried {dc - rad:.0f} m on to the ring of {r['name']}")
        if changed:
            parts[j] = plist

# ---------------------------------------------------------------- R5: frontage roads in the seam zone
sketch_pts = [tuple(q) for i in conn if R[i]["city"] == "sketch" for q in R[i]["pts"]]
for i in base:
    r, s = R[i], SR[i]
    if not s["oneway"] or i in drop:
        continue
    nm = r["name"]
    basename = nm.replace(" Service Road", "").replace(" Frontage Road", "")
    if basename == nm and "Service" not in nm:
        continue
    pts = [tuple(q) for q in r["pts"]]
    mid = pts[len(pts) // 2]
    if dist_seam(mid) > 300.0 and min((math.dist(mid, q) for q in sketch_pts), default=1e9) > 150.0:
        continue
    sc = cumlen(pts)
    n = max(2, int(sc[-1] / 4))
    along = 0
    for k in range(n + 1):
        p, t = at_s(pts, sc, sc[-1] * k / n)
        for a, b, j in G_BASE.near(p, 35.0):
            if j == i or R[j]["name"] != basename:
                continue
            d, q, _ = closest(p, a, b)
            tt = unit((b[0] - a[0], b[1] - a[1]))
            if d < 35.0 and abs(t[0] * tt[0] + t[1] * tt[1]) > 0.85:
                along += 1
                break
    if along / (n + 1) >= 0.7:
        drop[i] = f"R5 frontage road beside {basename} ({along / (n + 1):.0%} of it within 35 m) in the seam zone"
        log.append(f"R5 {nm} (plan {i}) dropped: frontage road beside {basename}")

# ---------------------------------------------------------------- R7: at-grade roads for the elevated I-35
# highway-capitol's requests (NOTES/highway-capitol-2026-10-20.md, 23:10), built from its layout
# (Saved/Expressway/expressway_layout.json) so they follow it if it moves:
#   - frontage roads at the I-35's east foot: one-way, two lanes, from South Canal Street east along the outside of the
#     ramp's walls (north side westbound, south side eastbound) to the Eisenhower's main lanes beyond the foot (the main
#     lanes there are the plan's own Eisenhower pieces; roadnet.py keeps them, the foot counts as a road going on)
#   - lower lanes under the decks from Guadalupe Street to Colorado Street: one lane each way + shoulders, centred on the
#     I-35 centreline between the two column lines (West 14th Street beside it is the westbound frontage)
# (Trinity Street's cut under the west ramp, and keeping every street off the ramp fills, are done in roadnet.py.)
added = []
LAY_P = ROOT / "Saved/Expressway/expressway_layout.json"
if LAY_P.exists():
    LAY = json.load(open(LAY_P))
    i35 = LAY.get("roads", {}).get("i35")
    if i35 and i35.get("centre"):
        cen = [(q[0], q[1], q[2]) for q in i35["centre"]]
        fills = i35.get("footprint", {}).get("fill", [])

        def street_x_at(name, y):
            """x where the plan street `name` crosses the line y (nearest crossing to the I-35's x range)."""
            best = None
            for j in base:
                if R[j]["name"] != name:
                    continue
                p = R[j]["pts"]
                for a, b in zip(p, p[1:]):
                    if (a[1] - y) * (b[1] - y) <= 0 and a[1] != b[1]:
                        x = a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1])
                        if best is None or abs(x + 1000) < abs(best + 1000):
                            best = x
            return best

        def poly_box(r):
            return min(q[0] for q in r), min(q[1] for q in r), max(q[0] for q in r), max(q[1] for q in r)

        foot = cen[0] if cen[0][2] <= 0.1 and cen[0][0] > cen[-1][0] else None
        east_fill = None
        if foot:
            east_fill = min(fills, key=lambda r: math.dist(foot[:2], ((poly_box(r)[0] + poly_box(r)[2]) / 2, (poly_box(r)[1] + poly_box(r)[3]) / 2)), default=None)
        if foot and east_fill:
            fx0, fy0, fx1, fy1 = poly_box(east_fill)
            half = 3.3                                    # two 3.3 m lanes
            yn, ys = fy1 + 1.0 + half, fy0 - 1.0 - half   # frontage centrelines outside the walls
            # the main lanes beyond the foot: the plan's Eisenhower pieces just east of it
            def main_y(east_x, side):
                cands = []
                for j in base:
                    if R[j]["cls"] != "highway" or "Eisenhower" not in R[j]["name"]:
                        continue
                    for a, b in zip(R[j]["pts"], R[j]["pts"][1:]):
                        if min(a[0], b[0]) <= east_x <= max(a[0], b[0]):
                            y = a[1] + (b[1] - a[1]) * (east_x - a[0]) / ((b[0] - a[0]) or 1e-9)
                            cands.append(y)
                cands = [y for y in cands if (y > foot[1]) == (side > 0)]
                return (max(cands) if side > 0 else min(cands)) if cands else None
            x_join = fx1 + 36.0                          # where the frontage lanes meet the main lanes
            x_canal_n, x_canal_s = street_x_at("South Canal Street", yn), street_x_at("South Canal Street", ys)
            for side, yf, xc, travel, label in ((1, yn, x_canal_n, -1, "westbound"), (-1, ys, x_canal_s, 1, "eastbound")):
                ym = main_y(x_join, side)
                if xc is None or ym is None:
                    log.append(f"R7 {label} frontage road: no Canal St / main lanes found, skipped")
                    continue
                # Canal St -> along the wall -> an S-curve onto the main lanes past the foot
                n_st = max(1, int(abs(fx1 + 4.0 - xc - 1.5) / 10.0))
                pts = [[round(xc + 1.5 + (fx1 + 4.0 - xc - 1.5) * k / n_st, 2), round(yf, 2)] for k in range(n_st + 1)]
                # (it stops 0.6 m short of the main lanes' centreline: roadnet snaps that end onto them as a junction;
                # an end exactly on a nearly parallel line falls between its crossing and snapping tests)
                ym2 = ym + 0.6 * side
                for k in range(1, 9):
                    t = k / 8.0
                    w = t * t * (3 - 2 * t)
                    pts.append([round(fx1 + 4.0 + (x_join - fx1 - 4.0) * t, 2), round(yf + (ym2 - yf) * w, 2)])
                added.append({"name": "Interstate 35 Frontage Road", "ref": "I-35", "cls": "mid", "lanes": 2, "oneway": True,
                              "reverse": travel < 0, "speed": 35, "city": "chicago", "pts": pts,
                              "why": f"R7 {label} frontage road at the I-35's east foot (highway-capitol request 3)"})
                log.append(f"R7 {label} frontage road from South Canal Street (x {xc:.0f}) along the ramp wall (y {yf:.1f}) to the main lanes at x {x_join:.0f}")
        # lower lanes under the decks, Guadalupe -> Colorado
        yc = sum(q[1] for q in cen if -1340 < q[0] < -1120) / max(1, sum(1 for q in cen if -1340 < q[0] < -1120))
        xg, xcol = street_x_at("Guadalupe Street", yc), street_x_at("Colorado Street", yc)
        if xg is not None and xcol is not None:
            lo, hi = sorted((xg, xcol))
            seg = [q for q in cen if lo + 1.0 < q[0] < hi - 1.0]
            if len(seg) >= 2:
                def y_at(x):
                    for a, b in zip(cen, cen[1:]):
                        if min(a[0], b[0]) <= x <= max(a[0], b[0]):
                            return a[1] + (b[1] - a[1]) * (x - a[0]) / ((b[0] - a[0]) or 1e-9)
                    return yc
                pts = [[round(hi, 2), round(y_at(hi), 2)]] + [[round(q[0], 2), round(q[1], 2)] for q in sorted(seg, key=lambda q: -q[0])][::3] + \
                      [[round(lo, 2), round(y_at(lo), 2)]]
                # an end lands on the junction already there (another street's end on the same cross street within 20 m:
                # at Guadalupe, the Eisenhower's surface continuation, West Congress Parkway): the lower lanes carry it on
                # across the cross street instead of making a second junction 12 m from it
                for end in (0, -1):
                    e = pts[end]
                    best = None
                    for j in base + conn:
                        if j in drop:
                            continue
                        for q in (R[j]["pts"][0], R[j]["pts"][-1]):
                            d_ = math.dist(e, q)
                            if 1.0 < d_ < 20.0 and (best is None or d_ < best[0]):
                                best = (d_, q, j)
                    if best:
                        dx, dy = best[1][0] - e[0], best[1][1] - e[1]
                        sc_ = cumlen(pts if end == 0 else pts[::-1])
                        seq = pts if end == 0 else pts[::-1]
                        for k_, (q, s_) in enumerate(zip(list(seq), sc_)):
                            w = max(0.0, 1.0 - s_ / 45.0)
                            w = w * w * (3 - 2 * w)
                            seq[k_] = [round(q[0] + dx * w, 2), round(q[1] + dy * w, 2)]
                        pts = seq if end == 0 else seq[::-1]
                        log.append(f"R7 lower lanes' end moved {best[0]:.0f} m onto the end of {R[best[2]]['name'] or R[best[2]]['cls']} (one junction)")
                added.append({"name": "Interstate 35 Lower Level", "ref": "I-35", "cls": "mid", "lanes": 2, "oneway": False,
                              "reverse": False, "speed": 30, "city": "austin", "under": True, "pts": pts,
                              "why": "R7 lower lanes under the I-35 decks, Guadalupe St to Colorado St (highway-capitol request 4)"})
                log.append(f"R7 lower lanes under the I-35 decks from Guadalupe St (x {hi:.0f}) to Colorado St (x {lo:.0f}) at y ~{yc:.0f}")

# ---------------------------------------------------------------- R8: at-grade ends of the Wacker Canal Expressway
# highway-capitol's request 8 (00:05), from its layout (roads.wacker): the south ramp comes down in the middle of South
# Wacker Drive (like the real ramps between Upper and Lower Wacker), on a solid fill strip between the carriageways, so
# along the strip each carriageway keeps its outer two lanes (no parking), its inner edge 0.2 m outside the fill wall,
# easing back to its own line over 25 m beyond the strip; the north end touches down beside the Crosstown Parkway and
# gets a short two-way link (2 + 2 lanes) onto it: a T junction.
if LAY_P.exists():
    wk = LAY.get("roads", {}).get("wacker")
    if wk and wk.get("centre") and wk.get("footprint", {}).get("fill"):
        cen = [(q[0], q[1], q[2]) for q in wk["centre"]]
        fills = wk["footprint"]["fill"]
        boxes = [(min(q[0] for q in f), min(q[1] for q in f), max(q[0] for q in f), max(q[1] for q in f)) for f in fills]
        # the south strip: the fill nearest the grade end at the south
        south = min(range(len(boxes)), key=lambda i: boxes[i][1])
        fx0, fy0, fx1, fy1 = boxes[south]
        half = 3.3                                          # two 3.3 m lanes
        for side, wall in ((-1, fx0), (1, fx1)):
            xc = wall + side * (0.2 + half)                 # the narrowed carriageway's centre line
            for j in base:
                if R[j]["cls"] == "highway" or "Wacker" not in R[j]["name"] or j in drop or j in parts:
                    continue
                pj = [tuple(q) for q in R[j]["pts"]]
                # a carriageway alongside the strip on this side: its line within 14 m outside the wall, overlapping it
                ys = [q[1] for q in pj]
                xs = [q[0] for q in pj]
                if max(ys) < fy0 - 2 or min(ys) > fy1 + 2:
                    continue
                xm = sum(xs) / len(xs)
                if not (0.0 <= (xm - wall) * side <= 14.0) and not (abs(xm - wall) < 3.0):
                    continue
                y_lo, y_hi = fy0 - 16.0, fy1 + 1.0          # down to the junction at the strip's foot, up to its end
                y_t = fy1 + 25.0                            # easing back by here
                sc_ = cumlen(pj)
                n_ = max(2, int(sc_[-1] / 2.0))
                samples = [at_s(pj, sc_, sc_[-1] * k / n_)[0] for k in range(n_ + 1)]
                inside, outside = [], [[]]
                for q in samples:
                    if q[1] <= y_t:
                        if q[1] <= y_hi:
                            w = 1.0
                        else:
                            w = 1.0 - (q[1] - y_hi) / (y_t - y_hi)
                            w = w * w * (3 - 2 * w)
                        inside.append([round(q[0] + (xc - q[0]) * w, 2), round(q[1], 2)] if q[1] >= y_lo - 30 else [round(q[0], 2), round(q[1], 2)])
                        if outside[-1]:
                            outside.append([])
                    else:
                        outside[-1].append([round(q[0], 2), round(q[1], 2)])
                keep = [o for o in outside if len(o) >= 2]
                if len(inside) < 2:
                    continue
                if R[j]["pts"][0][1] > R[j]["pts"][-1][1]:
                    pass                                    # samples follow the plan direction; one-way stays valid
                parts[j] = keep if keep else []
                if not keep:
                    drop[j] = "R8 replaced by its narrowed piece beside the Wacker expressway's ramp"
                s_ = SR[j]
                added.append({"name": R[j]["name"], "cls": R[j]["cls"], "lanes": 2, "oneway": s_["oneway"], "reverse": s_["reverse"],
                              "speed": s_["speed"], "city": R[j]["city"] if R[j]["city"] in ("chicago", "austin") else "chicago",
                              "narrow": True, "pts": inside,
                              "why": f"R8 {R[j]['name']} narrowed to two lanes beside the Wacker Canal Expressway's south ramp (highway-capitol request 8)"})
                log.append(f"R8 {R[j]['name']} (plan {j}) beside the Wacker ramp strip: 2 lanes centred at x {xc:.1f} from y {min(q[1] for q in inside):.0f} to {max(q[1] for q in inside):.0f}")
        # the north end: a link from the touchdown (past any fill there) to the nearest street ahead
        tx, ty = cen[-1][0], cen[-1][1]
        hx, hy = unit((cen[-1][0] - cen[-3][0], cen[-1][1] - cen[-3][1]))
        if cen[0][1] > cen[-1][1]:
            tx, ty = cen[0][0], cen[0][1]
            hx, hy = unit((cen[0][0] - cen[2][0], cen[0][1] - cen[2][1]))
        s0 = 0.0
        for k_, f in enumerate(fills):
            if k_ == south:
                continue
            bx0, by0, bx1, by1 = boxes[k_]
            while bx0 - 0.5 <= tx + hx * s0 <= bx1 + 0.5 and by0 - 0.5 <= ty + hy * s0 <= by1 + 0.5 and s0 < 40:
                s0 += 0.5
        start = (tx + hx * s0, ty + hy * s0)
        best = None
        for a, b, j in G_BASE.near(start, 60.0):
            if R[j]["cls"] == "highway":
                continue
            # ray-segment crossing
            ex, ey = b[0] - a[0], b[1] - a[1]
            den = hx * ey - hy * ex
            if abs(den) < 1e-6:
                continue
            wx, wy = a[0] - start[0], a[1] - start[1]
            t = (wx * ey - wy * ex) / den
            u = (wx * hy - wy * hx) / den
            if 0 < t < 60 and 0 <= u <= 1 and (best is None or t < best[0]):
                best = (t, j)
        if best:
            t, j = best
            t -= 0.6                                       # 0.6 m short of the street's line: roadnet snaps it on as a T
            end = (start[0] + hx * t, start[1] + hy * t)
            n_ = max(2, int(t / 8))
            pts = [[round(start[0] + (end[0] - start[0]) * k / n_, 2), round(start[1] + (end[1] - start[1]) * k / n_, 2)] for k in range(n_ + 1)]
            added.append({"name": "Wacker Canal Expressway", "cls": "major", "lanes": 4, "oneway": False, "reverse": False,
                          "speed": 35, "city": "austin", "pts": pts,
                          "why": "R8 the Wacker Canal Expressway's north end: a T junction with the street it lands beside (highway-capitol request 8)"})
            nm = attrs.get(str(j), {}).get("name", R[j]["name"])
            log.append(f"R8 Wacker Canal Expressway's north end: {t:.0f} m link from the touchdown to {nm} at plan ({end[0]:.0f}, {end[1]:.0f})")

out = {"what": "corrections to plan_v3.json's connector roads at the seam, applied by Scripts/roads/roadnet.py",
       "made_by": "Scripts/mashup/seam_fixes.py", "rules": __doc__.split("This script")[1].split("Output:")[0].strip(),
       "attrs": attrs, "drop": {str(k): v for k, v in drop.items()}, "parts": {str(k): v for k, v in parts.items()},
       "add": added, "log": log}
json.dump(out, open(OUT, "w"), indent=1)
print("wrote", OUT, "|", len(attrs), "attribute fixes,", len(drop), "drops,", len(parts), "re-cut roads")
for line in log:
    print(" ", line)
for k, v in sorted(attrs.items(), key=lambda kv: int(kv[0])):
    print(f"  {k:>5} {R[int(k)]['city']:7} {(R[int(k)]['name'] or R[int(k)]['cls'])[:30]:30} {({kk: vv for kk, vv in v.items() if kk != 'why'})} | {v['why'][:110]}")
for k, v in drop.items():
    print("  drop", k, R[int(k)]["name"], "|", v)
