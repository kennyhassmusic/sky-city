"""Lighting before/after and street-prop close-ups on a generated-city drive level, in the editor world (no PIE),
then quit. Lane P, 2026-10-27.
  "$UE" "$PWD/SkyCity.uproject" /Game/Maps/GenCity_Seed7 -nosplash "$THROTTLE_OFF" -abslog=<log> \
    -ExecCmds="py <space-free path>/Scripts/gencity/look_gencity_ue.py region=seed7_city tag=p1 bt=<bt> relight=1"
Steps: settle; a HighResShot from fixed cameras at the plan's downtown and industrial poses (looking east down the
street: the north-facing fronts on the right, the south-facing on the left, west-facing ends ahead); with relight=1
the importer's drive_light() (DRIVE_LIGHT, saves the level) and the same shots again; then close-ups of the street
props nearest the downtown pose (hydrant, signal masts, stop sign, parked cars). Writes Saved/GenCity/look_<tag>.json.
"""
import builtins
import json
import math
import os
import runpy
import sys
import time
import traceback

import unreal

ROOT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
REGION = KV.get("region", "seed7_city")
TAG = KV.get("tag", "look")
BT = KV.get("bt", "/Volumes/Sound Libraries/SkyCity Work/BuildingTypes-drive").replace("%20", " ")
SETTLE = float(KV.get("settle", "60"))
RELIGHT = KV.get("relight", "0") == "1"
PROPS = KV.get("props", "1") == "1"
RES = KV.get("res", "1920x1080")
PLAN = json.load(open(os.path.join(ROOT, "Saved", "GenCity", "plan_%s.json" % REGION)))
OUT = os.path.join(ROOT, "Saved", "GenCity", "look_%s.json" % TAG)
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "MacEditor")
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
res = {"tag": TAG, "done": False, "shots": [], "log": []}
S = {"t0": time.time(), "q": [], "busy": 0.0}


def write():
    res["secs"] = round(time.time() - S["t0"], 1)
    with open(OUT, "w") as h:
        json.dump(res, h, indent=1, sort_keys=True, default=str)


def files():
    return set(os.listdir(SHOTS)) if os.path.isdir(SHOTS) else set()


def cmd(c):
    unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), c)


def street_cams():
    out = []
    for s in PLAN["shots"]:
        if s["name"] not in ("downtown", "industrial"):
            continue
        x, y, _ = s["ue"]
        yaw = math.radians(s["yaw"])
        loc = unreal.Vector(x - math.cos(yaw) * 2500.0, y - math.sin(yaw) * 2500.0, 450.0)
        out.append((s["name"], loc, unreal.Rotator(0.0, -6.0, s["yaw"])))
    return out


def prop_cams():
    d = json.load(open(os.path.join(BT, "Saved", "CityGen", "props_%s.json" % REGION)))
    dt = next(s for s in PLAN["shots"] if s["name"] == "downtown")["ue"]
    out = []
    for key, look_z, back in (("KIT_SS_Hydrant|prop", 50.0, 320.0), ("KIT_SS_SignalMastL|prop", 520.0, 1100.0),
                              ("KIT_SS_SignalMastLR|prop", 520.0, 1100.0), ("KIT_SS_StopSign|prop", 200.0, 450.0),
                              ("KIT_SS_CarSedan|prop", 80.0, 650.0), ("KIT_SS_CarSUV|prop", 80.0, 650.0)):
        rows = d["groups"].get(key) or []
        if not rows:
            continue
        r = min(rows, key=lambda r: (r[0] - dt[0]) ** 2 + (r[1] - dt[1]) ** 2)
        yaw = math.radians(r[3] + 35.0)
        target = unreal.Vector(r[0], r[1], r[2] + look_z)
        loc = unreal.Vector(r[0] + math.cos(yaw) * back, r[1] + math.sin(yaw) * back, r[2] + look_z + back * 0.18)
        rot = unreal.MathLibrary.find_look_at_rotation(loc, target)
        out.append((key.split("|")[0].replace("KIT_SS_", "prop_"), loc, rot, r))
    return out


def plan_queue():
    q = []
    for name, loc, rot in street_cams():
        q += [("cam", (loc, rot)), ("wait", 5.0), ("shot", "before_" + name if RELIGHT else name)]
    if RELIGHT:
        q += [("relight", None), ("wait", 6.0)]
        for name, loc, rot in street_cams():
            q += [("cam", (loc, rot)), ("wait", 5.0), ("shot", "after_" + name)]
    if PROPS:
        for name, loc, rot, row in prop_cams():
            q += [("cam", (loc, rot)), ("wait", 4.0), ("shot", name)]
    q.append(("finish", None))
    return q


def do(item, now):
    kind, arg = item
    if kind == "cam":
        ues.set_level_viewport_camera_info(arg[0], arg[1])
        S["cam"] = [arg[0].x, arg[0].y, arg[0].z, arg[1].pitch, arg[1].yaw]
        return True
    if kind == "wait":
        if "until" not in S:
            S["until"] = now + arg
        if now < S["until"]:
            return False
        del S["until"]
        return True
    if kind == "shot":
        if "before" not in S:
            S["before"] = files()
            S["shot_t"] = now
            cmd("HighResShot " + RES)
            return False
        new = sorted(files() - S["before"])
        if not new and now - S["shot_t"] < 30:
            return False
        res["shots"].append({"name": arg, "file": os.path.join(SHOTS, new[-1]) if new else None, "cam": S.get("cam")})
        del S["before"]
        write()
        return True
    if kind == "relight":
        os.environ["GEN_LIGHT_ONLY"] = "1"
        runpy.run_path(os.path.join(ROOT, "Scripts", "gencity", "import_gencity_ue.py"))
        res["relight"] = json.load(open(os.path.join(ROOT, "Saved", "GenCity", "light_status.json")))
        return True
    if kind == "finish":
        unreal.unregister_slate_post_tick_callback(builtins._lanep_look)
        res["done"] = True
        write()
        S["quit_at"] = time.time() + 2.0

        def later(_dt):
            if time.time() > S["quit_at"]:
                unreal.SystemLibrary.quit_editor()
        builtins._lanep_quit = unreal.register_slate_post_tick_callback(later)
        return True
    return True


def tick(_dt):
    try:
        now = time.time()
        if not S["q"]:
            if now - S["t0"] < SETTLE:
                return
            try:
                les.editor_set_game_view(True)
            except Exception as exc:  # noqa: BLE001
                res["log"].append("game view: %s" % exc)
            for c in ("r.MotionBlurQuality 0", "r.AntiAliasingMethod 1"):
                cmd(c)
            S["q"] = plan_queue()
            write()
            return
        if do(S["q"][0], now):
            S["q"].pop(0)
    except Exception:
        res["error"] = traceback.format_exc()
        write()
        unreal.SystemLibrary.quit_editor()


builtins._lanep_look = unreal.register_slate_post_tick_callback(tick)
write()
