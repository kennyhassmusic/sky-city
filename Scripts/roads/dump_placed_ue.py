"""Dump what the road builders actually placed in SkyCityMashup, so the offline audit (Scripts/roads/audit_roads.py) can
check the editor's instances, not only roadnet.json.

Why: the 20 Oct playtest found poles and furniture standing in the lanes; roadnet.py now filters them, but only what
is in the level counts. This writes every SC_RoadProps instance (kind, world x/y/z, yaw, scale) and the list of
SC_Roads2 / SC_RoadProps actors with their collision profile to Saved/Roads/placed_props.json.

Run in the editor (PIE off): py Scripts/roads/dump_placed_ue.py
Writes Saved/MCPScripts/out_dump_placed.json (status) and Saved/Roads/placed_props.json (data). Read-only.
"""
import json, time, traceback, unreal

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
STATUS = ROOT + "/Saved/MCPScripts/out_dump_placed.json"
DATA = ROOT + "/Saved/Roads/placed_props.json"
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
t0 = time.time()
try:
    res = {"actors": [], "inst": {}}
    for a in EAS.get_all_level_actors():
        tags = [str(t) for t in a.tags]
        if not ("SC_RoadProps" in tags or "SC_Roads2" in tags):
            continue
        lab = a.get_actor_label()
        rec = {"label": lab, "tags": tags}
        comps = a.get_components_by_class(unreal.StaticMeshComponent)
        rec["comps"] = []
        for c in comps:
            rec["comps"].append({"name": c.get_name(), "mesh": c.static_mesh.get_name() if c.static_mesh else None,
                                 "coll": str(c.get_collision_profile_name()), "cls": c.get_class().get_name()})
            if isinstance(c, unreal.InstancedStaticMeshComponent):
                n = c.get_instance_count()
                rows = []
                for i in range(n):
                    r = c.get_instance_transform(i, True)
                    xf = r[1] if isinstance(r, tuple) else r
                    l = xf.translation
                    ro = xf.rotation.rotator()
                    s = xf.scale3d
                    rows.append([round(l.x, 1), round(l.y, 1), round(l.z, 1), round(ro.yaw, 1), round(s.x, 2), round(s.y, 2), round(s.z, 2)])
                res["inst"][lab] = rows
        res["actors"].append(rec)
    res["s"] = round(time.time() - t0, 1)
    json.dump(res, open(DATA, "w"))
    open(STATUS, "w").write(json.dumps({"done": True, "actors": len(res["actors"]), "kinds": {k: len(v) for k, v in res["inst"].items()}, "s": res["s"]}, indent=1))
except Exception:
    open(STATUS, "w").write(json.dumps({"error": traceback.format_exc()}))
