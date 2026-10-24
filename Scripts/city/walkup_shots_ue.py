"""Review shots of the Chicago walk-ups (walkup.py) for the screenshot checklist in Design/WALKUP_RULES.md.

Two steps:
  1. Plain Python plans the cameras from the city (front, close-up, corner, roofs, rear for a few rows):
       python3 -I Scripts/city/walkup_shots_ue.py --plan [--ids b_lot_osm_83,b_lot_osm_22]
     writes Saved/CityGen/walkup_shots.json (Unreal cm and degrees).
  2. In the editor, with the Chicago level open (Output Log, Python):
       py Scripts/city/walkup_shots_ue.py tag=after [res=1600x900] [only=name1,name2]
     moves the level viewport camera to each pose, waits for streaming, and writes
     Saved/CityGen/shots/<tag>_<name>.png and <tag>_shots.json. Read-only for the level.
"""
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else None


def _root():
    env = os.environ.get("SKYCITY_ROOT")
    if env:
        return env
    d = _HERE
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "SkyCity.uproject")):
            return d
        d = os.path.dirname(d)
    import unreal
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")


ROOT = _root()
PLAN = os.path.join(ROOT, "Saved", "CityGen", "walkup_shots.json")
SHOTS = os.path.join(ROOT, "Saved", "CityGen", "shots")
DEFAULT_IDS = ("b_lot_osm_83", "b_lot_osm_58", "b_lot_osm_22")


def _pose(name, eye, target):
    """[name, x, y, z (cm), pitch, yaw] looking from eye to target, both plan (x, y, z) metres."""
    dx, dy, dz = target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]
    yaw = math.degrees(math.atan2(dx, dy))
    pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
    return [name, round(eye[1] * 100.0, 1), round(eye[0] * 100.0, 1), round(eye[2] * 100.0, 1), round(pitch, 2), round(yaw, 2)]


def plan(ids):
    sys.path.insert(0, os.path.join(ROOT, "Scripts", "city"))
    import generate_city
    import skyline
    import walkup
    city = generate_city.build_from_disk(skyline.project_root(), region="chicago_loop")
    lots = walkup.plan_city(city["buildings"])
    poses = []
    for bid in ids:
        row = [lot for lot in lots if lot["building"] == bid]
        if not row:
            print("no walkup", bid)
            continue
        a, t, inn, depth = row[0]["a"], row[0]["t"], row[0]["inn"], row[0]["depth"]
        length = row[-1]["s1"]
        out = (-inn[0], -inn[1])

        def at(s, d, z):
            return (a[0] + t[0] * s + inn[0] * d, a[1] + t[1] * s + inn[1] * d, z)
        mid = length / 2.0
        tall = max(lot["top"] for lot in row)
        # The row from across the street, eye height.
        # From the near sidewalk, back far enough for the whole row (the street can hold the L or a tower).
        poses.append(_pose(bid + "_street", at(mid, -11.0, 1.7), at(mid, 0.0, tall * 0.55)))
        # Close-up of the lot with an oriel, or the middle lot: storefront and windows.
        close = next((lot for lot in row if lot["oriel"] and not lot["vacant"]), row[len(row) // 2])
        cs = (close["s0"] + close["s1"]) / 2.0
        poses.append(_pose(bid + "_close", at(cs + 2.0, -8.0, 1.6), at(cs, 0.0, close["ground_h"] + 1.5)))
        # The end of the row at 45 degrees: cornice return, blind side wall, parapet steps.
        poses.append(_pose(bid + "_corner", at(-9.0, -11.0, 2.5), at(4.0, depth * 0.35, row[0]["top"] * 0.6)))
        # Roofs from the air, from the front: parapets above the deck, clutter toward the rear.
        poses.append(_pose(bid + "_roofs", at(mid - 6.0, -16.0, tall + 22.0), at(mid, depth * 0.55, tall)))
        # The rear from the alley: porches and stairs, common brick.
        poses.append(_pose(bid + "_rear", at(mid + 4.0, depth + 16.0, 7.0), at(mid, depth, 5.0)))
        print(bid, "lots", len(row), "front", round(length, 1), "depth", round(depth, 1))
    os.makedirs(os.path.dirname(PLAN), exist_ok=True)
    with open(PLAN, "w") as handle:
        json.dump({"poses": poses}, handle, indent=1)
    print("poses", len(poses), PLAN)


def shoot(argv):
    import time
    import traceback
    import unreal
    kv = dict(arg.split("=", 1) for arg in argv if "=" in arg)
    tag = kv.get("tag", "shot")
    res = [int(v) for v in kv.get("res", "1600x900").split("x")]
    wait = int(kv.get("wait", "60"))
    with open(PLAN) as handle:
        poses = json.load(handle)["poses"]
    only = set(filter(None, kv.get("only", "").split(",")))
    if only:
        poses = [pose for pose in poses if pose[0] in only]
    os.makedirs(SHOTS, exist_ok=True)
    out_json = os.path.join(SHOTS, tag + "_shots.json")
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    state = {"i": 0, "k": 0, "files": [], "t0": time.time()}

    def tick(_dt):
        try:
            if state["i"] >= len(poses):
                if state["k"] > 30:
                    unreal.unregister_slate_post_tick_callback(handle)
                    with open(out_json, "w") as fh:
                        json.dump({"tag": tag, "files": state["files"], "done": True,
                                   "secs": round(time.time() - state["t0"], 1)}, fh, indent=1)
                state["k"] += 1
                return
            name, x, y, z, pitch, yaw = poses[state["i"]]
            if state["k"] == 0:
                ues.set_level_viewport_camera_info(unreal.Vector(x, y, z), unreal.Rotator(roll=0, pitch=pitch, yaw=yaw))
            if state["k"] == wait:
                path = os.path.join(SHOTS, "%s_%s.png" % (tag, name))
                unreal.AutomationLibrary.take_high_res_screenshot(res[0], res[1], path)
                state["files"].append(path)
            state["k"] += 1
            if state["k"] > wait + 25:
                state["k"] = 0
                state["i"] += 1
        except Exception:  # noqa: BLE001 - report into the json and stop ticking
            unreal.unregister_slate_post_tick_callback(handle)
            with open(out_json, "w") as fh:
                json.dump({"error": traceback.format_exc(), "files": state["files"]}, fh, indent=1)

    with open(out_json, "w") as fh:
        json.dump({"started": True, "poses": poses}, fh)
    handle = unreal.register_slate_post_tick_callback(tick)
    __import__("builtins")._walkup_shots_handle = handle


if __name__ == "__main__":
    if "--plan" in sys.argv:
        ids = DEFAULT_IDS
        if "--ids" in sys.argv:
            ids = tuple(sys.argv[sys.argv.index("--ids") + 1].split(","))
        plan(ids)
    else:
        shoot(sys.argv[1:])
