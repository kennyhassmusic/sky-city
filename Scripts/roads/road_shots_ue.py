"""Editor viewport captures of the streets (before/after pictures for the street audit; adapted from Scripts/rail/l_shots_ue.py): moves the level viewport camera to each pose, waits for it to
render, and takes a high-res screenshot into Saved/Roads/shots/<tag>_<n>_<name>.png. Read-only for the level.
Poses are in PLAN metres (x east, y north; Unreal X = y*100, Y = x*100): name:px,py,z_m,pitch,yaw_compass
(yaw_compass: 0 = looking north, 90 = east; pitch -90 = straight down).
Run in the editor:  py Scripts/roads/road_shots_ue.py tag=before "poses=a:80,-1512,60,-90,0;b:..."
Writes Saved/Roads/shots/out_shots.json (list of files) when done.
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
SHOTS = ROOT + "/Saved/Roads/shots"
os.makedirs(SHOTS, exist_ok=True)
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
TAG = KV.get("tag", "shot")
RES = [int(v) for v in KV.get("res", "1600x900").split("x")]
POSES = []
for p in KV.get("poses", "").split(";"):
    if not p:
        continue
    name, vals = p.split(":") if ":" in p else (str(len(POSES)), p)
    POSES.append((name, [float(v) for v in vals.split(",")]))
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
st = {"i": 0, "k": 0, "files": [], "t0": time.time()}
OUTJ = SHOTS + "/out_shots.json"
WAIT = int(KV.get("wait", "40"))


def tick(dt):
    try:
        if st["i"] >= len(POSES):
            if st["k"] > 30:                       # let the last screenshot be written
                unreal.unregister_slate_post_tick_callback(_h)
                json.dump({"tag": TAG, "files": st["files"], "done": True, "secs": round(time.time() - st["t0"], 1)}, open(OUTJ, "w"), indent=1)
            st["k"] += 1
            return
        name, (px, py, zm, pitch, yawc) = POSES[st["i"]]
        if st["k"] == 0:
            # compass yaw (0 north, 90 east) -> Unreal yaw: Unreal X = north, Y = east, so yaw = compass
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


json.dump({"started": True}, open(OUTJ, "w"))
_h = unreal.register_slate_post_tick_callback(tick)
