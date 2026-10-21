"""Low viewport captures of McGregor's edge transitions (mcgregor-edges, 20 Oct 2026), read-only for the level: the same
method as Saved/MCPScripts/unveil_shots.py (move the level viewport camera to each pose, wait for streaming, take a
high-res screenshot). Poses in PLAN metres: name:px,py,z_m,pitch,yaw_compass; z_m under 40 = above the ground there.
Run:  py Scripts/mcgregor/edges_shots_ue.py tag=before poses="a:x,y,z,p,y;..." [res=1280x720]
Writes Saved/McGregor/shots/edges/<tag>_<n>_<name>.png and out_shots.json there."""
import json, math, os, sys, time, traceback, unreal

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
SHOTS = ROOT + "/Saved/McGregor/shots/edges"
os.makedirs(SHOTS, exist_ok=True)
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
TAG = KV.get("tag", "shot")
RES = [int(v) for v in KV.get("res", "1280x720").split("x")]
WAIT = int(KV.get("wait", "50"))


def pose_sets():
    return {}


POSES = []
if "poses" in KV:
    for p in KV["poses"].split(";"):
        if p:
            name, vals = p.split(":") if ":" in p else (str(len(POSES)), p)
            POSES.append((name, [float(v) for v in vals.split(",")]))
for sname in KV.get("set", "").split(","):
    if sname:
        POSES += [(n, list(v)) for n, *v in pose_sets()[sname]]
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
st = {"i": 0, "k": 0, "files": [], "t0": time.time()}
OUTJ = SHOTS + "/out_shots.json"
try:
    unreal.unregister_slate_post_tick_callback(__import__("builtins")._edges_shots_h)
except Exception:
    pass


def tick(dt):
    try:
        if st["i"] >= len(POSES):
            if st["k"] > 30:
                unreal.unregister_slate_post_tick_callback(_h)
                json.dump({"tag": TAG, "files": st["files"], "done": True, "secs": round(time.time() - st["t0"], 1)}, open(OUTJ, "w"), indent=1)
            st["k"] += 1
            return
        name, (px, py, zm, pitch, yawc) = POSES[st["i"]]
        if st["k"] == 0:
            if zm < 40:
                w = ues.get_editor_world()
                hit = unreal.SystemLibrary.line_trace_single(w, unreal.Vector(py * 100, px * 100, 60000), unreal.Vector(py * 100, px * 100, -60000),
                                                             unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True)
                zm += hit.to_tuple()[4].z / 100.0 if hit else 0.0
            ues.set_level_viewport_camera_info(unreal.Vector(py * 100.0, px * 100.0, zm * 100.0), unreal.Rotator(roll=0, pitch=pitch, yaw=yawc))
        if st["k"] == WAIT:
            fn = f"{SHOTS}/{TAG}_{st['i']:02d}_{name}.png"
            unreal.AutomationLibrary.take_high_res_screenshot(RES[0], RES[1], fn)
            st["files"].append(fn)
        st["k"] += 1
        if st["k"] > WAIT + 25:
            st["k"] = 0
            st["i"] += 1
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        json.dump({"error": traceback.format_exc(), "files": st["files"]}, open(OUTJ, "w"), indent=1)


json.dump({"started": True, "poses": POSES}, open(OUTJ, "w"))
_h = unreal.register_slate_post_tick_callback(tick)
__import__("builtins")._edges_shots_h = _h
