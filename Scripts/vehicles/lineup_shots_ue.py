"""Editor-viewport shots of the McGregor line-up (the placed Lineup_<Car> actors, wherever demo_layout/lineup_ue put
them), for checking the vehicle glass and lamps on the static line-up at night. Read-only: moves only the level
viewport camera (and puts it back), takes HighResShots. Run with McGregor or McGregorNight loaded (not in PIE):
  py Scripts/vehicles/lineup_shots_ue.py tag=lineup_night [res=1280x720]
Writes Saved/VehicleModels/out_<tag>.json; collect with Scripts/vehicles/collect_shots.py <tag>."""
import builtins, json, math, os, sys, time, unreal

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
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
TAG, RES = KV.get("tag", "lineup"), KV.get("res", "1280x720")
OUT = f"{ROOT}/Saved/VehicleModels/out_{TAG}.json"
SHOTS = f"{ROOT}/Saved/Screenshots/MacEditor"
ORDER = ["Model3", "ModelY", "Cybertruck", "Robotaxi", "Semi"]
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
cars = {}
for a in EAS.get_all_level_actors():
    lab = a.get_actor_label()
    if lab.startswith("Lineup_") and lab.count("_") == 1:
        cars[lab[7:]] = a
res = {"tag": TAG, "cars": {k: [round(v, 1) for v in a.get_actor_location().to_tuple()] + [round(a.get_actor_rotation().yaw, 1)] for k, a in cars.items()}, "shots": []}
views = []
if cars:
    ps = [a.get_actor_location() for a in cars.values()]
    c = unreal.Vector(sum(p.x for p in ps) / len(ps), sum(p.y for p in ps) / len(ps), sum(p.z for p in ps) / len(ps))
    yaw = math.radians(list(cars.values())[0].get_actor_rotation().yaw)
    f = unreal.Vector(math.cos(yaw), math.sin(yaw), 0)               # the cars face local +X

    def look(at, frm):
        d = at - frm
        return unreal.Rotator(roll=0, pitch=math.degrees(math.atan2(d.z, math.hypot(d.x, d.y))), yaw=math.degrees(math.atan2(d.y, d.x)))
    def side(v, k):
        return unreal.Vector(-v.y * k, v.x * k, 0)
    views.append(("front_all", c + f * 2400 + unreal.Vector(0, 0, 260), c + unreal.Vector(0, 0, 120)))
    views.append(("front_left", c + f * 1300 + side(f, 900) + unreal.Vector(0, 0, 200), c + unreal.Vector(0, 0, 120)))
    views.append(("front_right", c + f * 1300 - side(f, 900) + unreal.Vector(0, 0, 200), c + unreal.Vector(0, 0, 120)))
    for k in ("Semi", "Model3", "Cybertruck"):
        if k in cars:
            p = cars[k].get_actor_location()
            views.append((f"close_{k}", p + f * 900 + side(f, 350) + unreal.Vector(0, 0, 220), p + unreal.Vector(0, 0, 110)))
st = {"i": 0, "phase": 0, "t": time.time() + 1.0, "cam": ues.get_level_viewport_camera_info()}
_h = None


def tick(dt):
    try:
        if time.time() < st["t"]:
            return
        if st["i"] >= len(views):
            try:
                ues.set_level_viewport_camera_info(st["cam"][0], st["cam"][1])
            except Exception:
                pass
            unreal.unregister_slate_post_tick_callback(_h)
            res["done"] = True
            open(OUT, "w").write(json.dumps(res, indent=1))
            return
        name, frm, at = views[st["i"]]
        if st["phase"] == 0:
            ues.set_level_viewport_camera_info(frm, look(at, frm))
            st["phase"], st["t"] = 1, time.time() + 1.5
            return
        if st["phase"] == 1:
            st["count"] = len(os.listdir(SHOTS))
            unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), f"HighResShot {RES}")
            res["shots"].append({"veh": st["i"] + 1, "view": name, "wall": time.time()})
            st["phase"], st["t0"] = 2, time.time()
            return
        if len(os.listdir(SHOTS)) <= st["count"] and time.time() - st["t0"] < 10:
            return
        st["i"] += 1
        st["phase"], st["t"] = 0, time.time() + 0.2
        open(OUT, "w").write(json.dumps(res, indent=1))
    except Exception as e:
        import traceback
        unreal.unregister_slate_post_tick_callback(_h)
        res["error"] = traceback.format_exc()
        open(OUT, "w").write(json.dumps(res, indent=1))


for _old in getattr(builtins, "_vm_ticks", []):
    try:
        unreal.unregister_slate_post_tick_callback(_old)
    except Exception:
        pass
_h = unreal.register_slate_post_tick_callback(tick)
builtins._vm_ticks = [_h]
