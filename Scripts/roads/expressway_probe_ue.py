"""Expressway probe (read-only): what stands under and around the two elevated expressways, so the offline layout
(Scripts/roads/expressway_layout.py) can keep piers, decks and ramps off buildings, trees, lamps and landmark pieces.

Why: the plan's buildings (buildings_v3.json) are not the whole story - City Sample buildings, road props (trees, lamps,
signals), the Capitol's fence, lamps and monuments and other agents' landmarks are only known to the level.
What: a grid of downward traces (Visibility channel) every STEP m over each corridor box (plan metres, x east, y north;
Unreal X = y*100, Y = x*100) from z 80 m down to -10 m, ignoring the old generic elevated actors (build_city.py's
"ElevatedExpressways" + "Piers") and this kit's own actors (tag SC_Expressway). Per cell: top hit z (cm), actor label
index, component name index and instance index (HISM item). Before tracing it loads the World Partition actors that
intersect the boxes (loading does not dirty anything) and lists the old elevated actors.
Chunked over slate post-ticks so the editor stays responsive. Writes Saved/Expressway/probe.json.
Run (editor lock held): py Scripts/roads/expressway_probe_ue.py [step=2]
(20 Oct 2026, agent highway-capitol)
"""
import json, os, sys, time, traceback, unreal

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
OUT = ROOT + "/Saved/Expressway/probe.json"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
STEP = float(KV.get("step", 2))
BOXES = {  # plan metres x0, y0, x1, y1
    "i35": (-1935.0, -1365.0, -830.0, -1245.0),
    "wacker": (-805.0, -1060.0, -435.0, -250.0),
}
OLD_LABELS = ("ElevatedExpressways", "Piers")
TAG = "SC_Expressway"
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world = ues.get_editor_world()
out = {"step": STEP, "boxes": BOXES, "labels": [], "comps": [], "grids": {}, "old_actors": [], "wp": {}}
lab_idx, comp_idx = {}, {}


def idx(table, key, s):
    if s not in table:
        table[s] = len(out[key])
        out[key].append(s)
    return table[s]


def load_wp():
    WPL = getattr(unreal, "WorldPartitionBlueprintLibrary", None)
    if WPL is None:
        out["wp"]["note"] = "no WorldPartitionBlueprintLibrary"
        return
    for name, (x0, y0, x1, y1) in BOXES.items():
        try:
            box = unreal.Box(unreal.Vector(y0 * 100 - 2000, x0 * 100 - 2000, -2000), unreal.Vector(y1 * 100 + 2000, x1 * 100 + 2000, 20000))
            descs = WPL.get_intersecting_actor_descs(box)
            guids = [d.guid for d in descs]
            spatial = [d.guid for d in descs if d.get_editor_property("is_spatially_loaded")]
            if spatial:
                WPL.load_actors(spatial)      # most city actors are not spatially loaded (always in); load the rest
            out["wp"][name] = {"descs": len(descs), "spatially_loaded": len(spatial)}
        except Exception as e:
            out["wp"][name] = {"error": str(e)}


ign = []
for a in EAS.get_all_level_actors():
    tags = [str(t) for t in a.tags]
    lab = a.get_actor_label()
    if TAG in tags or (lab in OLD_LABELS and "City_Generated" in tags):
        ign.append(a)
        if lab in OLD_LABELS:
            info = {"label": lab, "tags": tags, "folder": str(a.get_folder_path()), "class": a.get_class().get_name()}
            try:
                info["mesh"] = a.static_mesh_component.static_mesh.get_path_name()
            except Exception:
                pass
            out["old_actors"].append(info)
load_wp()
jobs = []
for name, (x0, y0, x1, y1) in BOXES.items():
    nx, ny = int((x1 - x0) / STEP) + 1, int((y1 - y0) / STEP) + 1
    out["grids"][name] = {"x0": x0, "y0": y0, "nx": nx, "ny": ny, "z": [], "a": [], "c": [], "i": []}
    for j in range(ny):
        jobs.append((name, j))
st = {"k": 0, "t0": time.time()}


def tick(dt):
    try:
        t_end = time.time() + 0.25
        while st["k"] < len(jobs) and time.time() < t_end:
            name, j = jobs[st["k"]]
            g = out["grids"][name]
            py = g["y0"] + j * STEP
            zs, aa, cc, ii = [], [], [], []
            for i in range(g["nx"]):
                px = g["x0"] + i * STEP
                h = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(py * 100, px * 100, 8000), unreal.Vector(py * 100, px * 100, -1000),
                                                           unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, ign, unreal.DrawDebugTrace.NONE, True)
                t = h.to_tuple() if h else None
                if t and t[0]:
                    zs.append(round(t[5].z))
                    act = t[9]
                    aa.append(idx(lab_idx, "labels", act.get_actor_label() if act else ""))
                    comp = t[10]
                    cc.append(idx(comp_idx, "comps", comp.get_name() if comp else ""))
                    ii.append(int(t[13]) if t[13] is not None else -1)
                else:
                    zs.append(-99999); aa.append(-1); cc.append(-1); ii.append(-1)
            g["z"].append(zs); g["a"].append(aa); g["c"].append(cc); g["i"].append(ii)
            st["k"] += 1
        if st["k"] >= len(jobs):
            unreal.unregister_slate_post_tick_callback(_h)
            out["secs"] = round(time.time() - st["t0"], 1)
            out["done"] = True
            open(OUT, "w").write(json.dumps(out))
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        out["error"] = traceback.format_exc()
        open(OUT, "w").write(json.dumps(out))


open(OUT, "w").write(json.dumps({"started": True, "old_actors": out["old_actors"], "wp": out["wp"]}))
_h = unreal.register_slate_post_tick_callback(tick)
