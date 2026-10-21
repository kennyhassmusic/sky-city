"""Edge survey of the McGregor maps (mcgregor-edges agent, 20 Oct 2026): how high the edges of the roads, parking lots,
the unveil lot and the test-stand pads stand above the ground beside them. Read-only for the level.

For every sample it traces straight down (Visibility channel, complex collision: what the car's own ray sees) at
offsets across the edge, -0.6 .. +0.6 m (inside .. outside), and wherever two neighbouring samples differ by more than
2.5 cm it bisects down to 1.5 cm spacing: a vertical step keeps its full height at any spacing, a slope shrinks away.
  step  the biggest vertical discontinuity across the edge (cm; + = the road / lot side is higher)
  rise  the road / lot top (0.3 m inside) over the bare terrain 2 m outside (cm): how much the transition has to cover
Kinds:
  roads   both edges at every OSM road vertex (mcgregor_data.json; ~6 m apart). edge=sweep: the old swept ribbon's edge
          (bisector, no mitre); edge=mitre (default once the roads stage has been rerun): the draped roads' edge
  lots    the parking lots' outline: Saved/McGregor/edges/outlines.json (written by site_ue.py lots) if present, else
          the staircase boundary of site_features.json's lot grids; every 2 m
  pads    the unveil lot (demo_layout.json pads) every 2.5 m round its ring
  kit     radial scans round the test-stand / building kit models: low raised platforms (aprons, decks, footings: top
          < 1.2 m over the terrain, horizontal) and the step at their edges
Run in the editor (PIE off), McGregor (or McGregorNight) loaded:
  py Scripts/mcgregor/edges_survey_ue.py tag=before [edge=sweep|mitre]
     [kinds=roads,lots,pads,kit] [every=1]  (every=N: every Nth road vertex)
Writes Saved/McGregor/edges/survey_<tag>.json (summary + compact samples [x, y, step_cm, rise_cm, flag]) and progress
in Saved/MCPScripts/out_edges_survey.json. Map of the bad edges: python3 -I Scripts/mcgregor/edges_map.py <tag>.
"""
import importlib, json, math, os, sys, time, traceback, unreal

import os


def _skycity_root():
    """Project folder: $SKYCITY_ROOT, else the folder above this script that holds SkyCity.uproject."""
    env = os.environ.get("SKYCITY_ROOT")
    if env:
        return env
    try:
        d = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        d = None
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "SkyCity.uproject")):
            return d
        d = os.path.dirname(d)
    import unreal  # running in the editor without __file__
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")


ROOT = _skycity_root()
sys.path.insert(0, ROOT + "/Scripts/mcgregor")
import edges_lib as EL
importlib.reload(EL)

KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
TAG = KV.get("tag", "survey")
EDGE = KV.get("edge", "mitre")
KINDS = KV.get("kinds", "roads,lots,pads,kit").split(",")
EVERY = int(KV.get("every", "1"))
OUTD = ROOT + "/Saved/McGregor/edges"
os.makedirs(OUTD, exist_ok=True)
PROG = ROOT + "/Saved/MCPScripts/out_edges_survey.json"
D = json.load(open(ROOT + "/Saved/McGregor/mcgregor_data.json"))
F = json.load(open(ROOT + "/Saved/McGregor/site_features.json"))
DEMO = json.load(open(ROOT + "/Saved/McGregor/demo_layout.json"))
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
W = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
T = EL.Terrain(EAS.get_all_level_actors())
DEMH = EL.DEM()
O = [-0.6, -0.3, -0.12, -0.04, 0.04, 0.12, 0.3, 0.6]
out = {"tag": TAG, "map": W.get_path_name(), "edge": EDGE, "kinds": KINDS, "t0": time.strftime("%H:%M:%S")}
NTR = [0]


def prog(**k):
    out.update(k)
    open(PROG, "w").write(json.dumps({kk: v for kk, v in out.items() if kk not in ("samples",)}, indent=1))


def zhit(x, y):
    """First blocking hit straight down at (x, y): (z m, normal z, actor label) or None."""
    NTR[0] += 1
    g = DEMH.h(x, y)
    h = unreal.SystemLibrary.line_trace_single(W, unreal.Vector(y * 100.0, x * 100.0, (g + 6.0) * 100.0), unreal.Vector(y * 100.0, x * 100.0, (g - 6.0) * 100.0),
                                               unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [], unreal.DrawDebugTrace.NONE, True)
    if not h:
        return None
    t = h.to_tuple()
    if not t[0]:
        return None
    a = t[9]
    return (t[4].z / 100.0, t[7].z, a.get_actor_label() if a else "")


def refine(px, py, nx, ny, oa, ha, ob, hb):
    """Bisect [oa, ob] toward the biggest jump until the samples are 1.5 cm apart -> (jump inner-outer m, offset)."""
    while ob - oa > 0.015:
        om = (oa + ob) / 2
        hm = zhit(px + nx * om, py + ny * om)
        if hm is None:
            break
        if abs(ha[0] - hm[0]) >= abs(hm[0] - hb[0]):
            ob, hb = om, hm
        else:
            oa, ha = om, hm
    return ha[0] - hb[0], (oa + ob) / 2, ha, hb


def profile(px, py, nx, ny):
    """Across the edge at (px, py), outward unit normal (nx, ny) -> (step m, offset, rise m, inner label, outer label)."""
    hs = [zhit(px + nx * o, py + ny * o) for o in O]
    best = (0.0, 0.0, None, None)
    for k in range(len(O) - 1):
        a, b = hs[k], hs[k + 1]
        if a is None or b is None or abs(a[0] - b[0]) <= 0.025:
            continue
        j, off, ha, hb = refine(px, py, nx, ny, O[k], a, O[k + 1], b)
        if abs(j) > abs(best[0]):
            best = (j, off, ha, hb)
    g = T.h(px + nx * 2.0, py + ny * 2.0)
    top = hs[1][0] if hs[1] else None
    rise = (top - g) if (top is not None and g is not None) else None
    return best[0], best[1], rise, (hs[1][2] if hs[1] else ""), (best[3][2] if best[3] else (hs[-1][2] if hs[-1] else ""))


# ------------------------------------------------------------------ what to sample
def road_jobs():
    jobs = []
    for ri, r in enumerate(D["roads"]):
        if r["kind"] in ("footway", "path"):
            continue
        q = [tuple(r["pts"][0])]
        for p in r["pts"][1:]:
            if math.dist(p, q[-1]) > 0.05:
                q.append(tuple(p))
        n = len(q)
        if n < 2:
            continue
        hw = r["w"] / 2
        for k in range(0, n, EVERY):
            a, b = q[max(0, k - 1)], q[min(n - 1, k + 1)]
            if EDGE == "mitre" and 0 < k < n - 1:
                t1 = EL._unit(q[k][0] - q[k - 1][0], q[k][1] - q[k - 1][1])
                t2 = EL._unit(q[k + 1][0] - q[k][0], q[k + 1][1] - q[k][1])
                s = (t1[0] + t2[0], t1[1] + t2[1])
                t = EL._unit(*s) if math.hypot(*s) > 1e-6 else t1
                m = 1.0 / max(t[0] * t1[0] + t[1] * t1[1], 0.6) if math.hypot(*s) > 1e-6 else 1.0
            else:
                t = EL._unit(b[0] - a[0], b[1] - a[1])
                m = 1.0
            nx, ny = -t[1], t[0]
            for side in (-1, 1):
                jobs.append(("roads", q[k][0] + side * nx * hw * m, q[k][1] + side * ny * hw * m, side * nx, side * ny, ri))
    return jobs


def loop_jobs(kind, loop, spacing, ident):
    jobs = []
    a2 = sum(loop[k][0] * loop[(k + 1) % len(loop)][1] - loop[(k + 1) % len(loop)][0] * loop[k][1] for k in range(len(loop)))
    sgn = 1.0 if a2 > 0 else -1.0                  # CCW: outward is right of the edge
    for k in range(len(loop)):
        a, b = loop[k], loop[(k + 1) % len(loop)]
        L = math.dist(a, b)
        if L < 0.05:
            continue
        nx, ny = (b[1] - a[1]) / L * sgn, -(b[0] - a[0]) / L * sgn
        m = max(1, int(round(L / spacing)))
        for s in range(m):
            f = (s + 0.5) / m
            jobs.append((kind, a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, nx, ny, ident))
    return jobs


def staircase_jobs(lot):
    """Boundary edges of a lot grid (edges used by one triangle), sampled at their midpoints, normal away from the
    triangle."""
    cnt, opp = {}, {}
    V = lot["verts"]
    for t in lot["tris"]:
        for e in ((t[0], t[1], t[2]), (t[1], t[2], t[0]), (t[2], t[0], t[1])):
            key = tuple(sorted(e[:2]))
            cnt[key] = cnt.get(key, 0) + 1
            opp[key] = e[2]
    jobs = []
    for key, c in cnt.items():
        if c != 1:
            continue
        a, b, o = V[key[0]], V[key[1]], V[opp[key]]
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        L = math.dist(a[:2], b[:2]) or 1.0
        nx, ny = (b[1] - a[1]) / L, -(b[0] - a[0]) / L
        if (o[0] - mx) * nx + (o[1] - my) * ny > 0:
            nx, ny = -nx, -ny
        jobs.append(("lots", mx, my, nx, ny, lot["name"]))
    return jobs


def lot_jobs():
    op = OUTD + "/outlines.json"
    ol = json.load(open(op)).get("lots", {}) if os.path.exists(op) else {}
    jobs = []
    for lot in F["lots"]:
        if lot["name"] in ol:
            jobs += loop_jobs("lots", ol[lot["name"]], 2.0, lot["name"])
        else:
            jobs += staircase_jobs(lot)
    out["lots_source"] = "outlines.json" if ol else "site_features staircase"
    return jobs


def pad_jobs():
    """The demo pads' rings: the outline the berm was built on (outlines.json, = the pad actually in the level) if
    there is one, else demo_layout.json's ring."""
    op = OUTD + "/outlines.json"
    ol = json.load(open(op)).get("pads", {}) if os.path.exists(op) else {}
    jobs = []
    for pad in DEMO.get("pads", []):
        jobs += loop_jobs("pads", ol.get(pad["name"]) or pad["ring"], 2.5, pad["name"])
    return jobs


KIT_R = {"SK_Tripod": 26, "SK_FSStand": 30, "SK_FSTrench": 45, "SK_EngineStandV": 16, "SK_EngineStandH": 18, "SK_StructuralStand": 14,
         "SK_Blockhouse": 30, "SK_Hangar": 38, "SK_Shop": 28, "SK_TankBig": 15, "SK_TankOpen": 15, "SK_WaterTower": 16, "SK_WaterTowerSmall": 12}


def kit_jobs():
    jobs = []
    for p in F["placements"]:
        if p["mesh"] in KIT_R:
            R = KIT_R[p["mesh"]] * max(p["scale"][0], p["scale"][1], 1.0 if p["mesh"] != "SK_Hangar" else 0.0)
            jobs.append(("kit", p["p"][0], p["p"][1], R, 0, p["mesh"]))
    return jobs


def kit_scan(cx, cy, R, mesh):
    """48 rays from the model's centre; along each, steps between low horizontal surfaces -> list of samples."""
    res = []
    for ray in range(48):
        a = math.radians(ray * 7.5)
        nx, ny = math.sin(a), math.cos(a)
        prev = None
        r = 1.0
        while r <= R:
            h = zhit(cx + nx * r, cy + ny * r)
            if h is not None and prev is not None and abs(h[0] - prev[1][0]) > 0.03:
                hi, lo = (prev, (r, h)) if prev[1][0] > h[0] else ((r, h), prev)
                g = T.h(cx + nx * hi[0], cy + ny * hi[0])
                if g is not None and hi[1][0] - g < 1.2 and hi[1][1] > 0.9:
                    j, off, ha, hb = refine(cx, cy, nx, ny, prev[0], prev[1], r, h)
                    if abs(j) > 0.03:
                        px, py = cx + nx * off, cy + ny * off
                        gl = T.h(px + nx * 2.0, py + ny * 2.0) if j > 0 else T.h(px - nx * 2.0, py - ny * 2.0)
                        res.append((px, py, abs(j), (hi[1][0] - gl) if gl is not None else None, hi[1][2], mesh))
            if h is not None:
                prev = (r, h)
            r += 0.3
    return res


JOBS = []
for k in KINDS:
    JOBS += {"roads": road_jobs, "lots": lot_jobs, "pads": pad_jobs, "kit": kit_jobs}[k]()
out["jobs"] = len(JOBS)
SAMPLES = {k: [] for k in KINDS}
st = {"i": 0, "t0": time.time()}


def pct(v, p):
    return v[min(len(v) - 1, int(len(v) * p))] if v else None


def summarise():
    summ = {}
    for k, ss in SAMPLES.items():
        steps = sorted(abs(s[2]) for s in ss)
        rises = sorted(s[3] for s in ss if s[3] is not None)
        if not steps:
            summ[k] = {"n": 0}
            continue
        summ[k] = {"n": len(steps), "step_cm": {"p50": pct(steps, 0.5), "p90": pct(steps, 0.9), "p99": pct(steps, 0.99), "max": steps[-1]},
                   "rise_cm": {"p50": pct(rises, 0.5), "p90": pct(rises, 0.9), "max": rises[-1] if rises else None},
                   "share_over_cm": {str(t): round(sum(1 for s in steps if s > t) / len(steps) * 100, 1) for t in (3, 10, 20, 30, 52)}}
        if k == "kit":
            per = {}
            for s in ss:
                per.setdefault(s[5], []).append(abs(s[2]))
            summ[k]["by_mesh_max_cm"] = {m: max(v) for m, v in per.items()}
            summ[k]["by_mesh_n"] = {m: len(v) for m, v in per.items()}
    return summ


def tick(dt):
    try:
        t0 = time.time()
        while st["i"] < len(JOBS) and time.time() - t0 < 0.3:
            kind, x, y, a, b, ident = JOBS[st["i"]]
            st["i"] += 1
            if kind == "kit":
                for px, py, j, rise, lab, mesh in kit_scan(x, y, a, ident):
                    SAMPLES["kit"].append([round(px, 2), round(py, 2), round(j * 100), round(rise * 100) if rise is not None else None, lab, mesh])
                continue
            j, off, rise, lin, lout = profile(x, y, a, b)
            SAMPLES[kind].append([round(x, 2), round(y, 2), round(j * 100, 1), round(rise * 100) if rise is not None else None, lin, lout, ident])
        if st["i"] % 2000 < 50 or st["i"] >= len(JOBS):
            prog(done_jobs=st["i"], traces=NTR[0], terrain_traces=T.n, secs=round(time.time() - st["t0"], 1))
        if st["i"] >= len(JOBS):
            unreal.unregister_slate_post_tick_callback(_h)
            out["summary"] = summarise()
            out["samples"] = SAMPLES
            out["traces"] = NTR[0]
            out["terrain_traces"] = T.n
            out["secs"] = round(time.time() - st["t0"], 1)
            json.dump(out, open(f"{OUTD}/survey_{TAG}.json", "w"), separators=(",", ":"))
            prog(done=True, summary=out["summary"])
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        prog(error=traceback.format_exc())


prog(started=True)
_h = unreal.register_slate_post_tick_callback(tick)
