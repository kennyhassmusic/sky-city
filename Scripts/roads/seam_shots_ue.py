"""Top-down / oblique editor viewport captures of the seam junctions, for before/after pictures (seam-junctions agent,
20 Oct night; adapted from Scripts/roads/road_shots_ue.py). Read-only for the level.

Moves the level viewport camera to each pose, waits for it to render, takes a high-res screenshot into a 10-slot PNG ring
(Saved/Roads/seam/tmp/, overwritten, nothing piles up) and turns it into a JPG with sips:
Saved/Roads/seam/shots/<tag>_<nn>_<name>.jpg.
Poses: PLAN metres (x east, y north; Unreal X = y*100, Y = x*100): name:px,py,z_m,pitch,yaw_compass (0 = looking north,
90 = east; pitch -90 = straight down). Or sites=Saved/Roads/seam/audit_before.json n=12 [z=220] for the audit's top sites.
Run in the editor (lock held, PIE off):
  py Scripts/roads/seam_shots_ue.py tag=before sites=<json> n=12
  py .../seam_shots_ue.py tag=x "poses=a:80,-1512,60,-90,0;b:..."
Writes Saved/Roads/seam/shots/out_shots.json (files, done) as it goes.
"""
import json, os, subprocess, sys, time, traceback, unreal

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
SHOTS = ROOT + "/Saved/Roads/seam/shots"
TMP = ROOT + "/Saved/Roads/seam/tmp"
os.makedirs(SHOTS, exist_ok=True)
os.makedirs(TMP, exist_ok=True)
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
TAG = KV.get("tag", "shot")
RES = [int(v) for v in KV.get("res", "1400x1000").split("x")]
WAIT = int(KV.get("wait", "45"))
POSES = []
for p in KV.get("poses", "").split(";"):
    if p:
        name, vals = p.split(":") if ":" in p else (str(len(POSES)), p)
        POSES.append((name, [float(v) for v in vals.split(",")]))
if KV.get("sites"):
    S = json.load(open(KV["sites"]))["sites"][: int(KV.get("n", "12"))]
    z = float(KV.get("z", "220"))
    for s in S:
        POSES.append((f"site{s['rank']:02d}", [s["c"][0], s["c"][1], z, -90.0, 0.0]))
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
st = {"i": 0, "k": 0, "files": [], "pending": [], "t0": time.time()}
OUTJ = SHOTS + "/out_shots.json"


def pump(final=False):
    keep = []
    for pd in st["pending"]:
        f = pd["tmp"]
        ok = os.path.exists(f) and os.path.getmtime(f) > pd["t"] - 0.05 and time.time() - os.path.getmtime(f) > 0.8
        if ok:
            subprocess.Popen(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "70", f, "--out", pd["out"]],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            st["files"].append(pd["out"])
        elif time.time() - pd["t"] < 15 and not final:
            keep.append(pd)
    st["pending"] = keep


def tick(dt):
    try:
        pump()
        if st["i"] >= len(POSES):
            st["k"] += 1
            if not st["pending"] or st["k"] > 400:
                unreal.unregister_slate_post_tick_callback(_h)
                json.dump({"tag": TAG, "files": st["files"], "done": True, "secs": round(time.time() - st["t0"], 1)},
                          open(OUTJ, "w"), indent=1)
            return
        name, (px, py, zm, pitch, yawc) = POSES[st["i"]]
        if st["k"] == 0:
            ues.set_level_viewport_camera_info(unreal.Vector(py * 100.0, px * 100.0, zm * 100.0),
                                               unreal.Rotator(roll=0, pitch=pitch, yaw=yawc))
        if st["k"] == WAIT:
            tmp = f"{TMP}/s{st['i'] % 10}.png"
            unreal.AutomationLibrary.take_high_res_screenshot(RES[0], RES[1], tmp)
            st["pending"].append({"tmp": tmp, "out": f"{SHOTS}/{TAG}_{st['i']:02d}_{name}.jpg", "t": time.time()})
        st["k"] += 1
        if st["k"] > WAIT + 30:
            st["k"] = 0
            st["i"] += 1
            json.dump({"tag": TAG, "files": st["files"], "done": False, "at": st["i"]}, open(OUTJ, "w"), indent=1)
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        json.dump({"error": traceback.format_exc(), "files": st["files"]}, open(OUTJ, "w"), indent=1)


json.dump({"started": True, "poses": len(POSES)}, open(OUTJ, "w"))
_h = unreal.register_slate_post_tick_callback(tick)
