"""Close-up captures of the drivable line-up vehicles in PIE (vehicle-models check, 20 Oct 2026): drives the PIE SkysterCar
through its test hooks (TestVehicle 1-5, the fixed test camera TestCamDist/Yaw/Elev, then the normal chase camera) and
takes a HighResShot per view, so the glass, lamps and paint can be compared before/after a materials change.
Read-only: nothing in the level changes; PIE is started if it isn't running and stopped at the end (stop=0 keeps it).
Run in the editor (any map; McGregorNight shows the lamps at night):
  py Scripts/vehicles/vehicle_shots_ue.py tag=before_day [vehs=1,2,3,4,5]
     [views=front,side,rear,chase,frontclose,rearclose,glass,top] [res=1280x720] [tp=x,y,z,yaw] [stop=1] [lights=0|1]
Writes Saved/VehicleModels/out_<tag>.json (shot list with wall times); collect the PNGs from
Saved/Screenshots/MacEditor with Scripts/vehicles/collect_shots.py <tag>."""
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
TAG = KV.get("tag", "shots")
VEHS = [int(v) for v in KV.get("vehs", "1,2,3,4,5").split(",")]
VIEWS = KV.get("views", "front,side,rear,chase,frontclose,rearclose,glass,top").split(",")
RES = KV.get("res", "1280x720")
TP = [float(v) for v in KV["tp"].split(",")] if "tp" in KV else None
STOP = KV.get("stop", "1") == "1"
# emulate=1: after each switch, redo the car's lamp overrides the way the pending C++ fix does (drop every override on the
# body, then the car's lamp materials on the exact Headlight/AuxLight/Taillight slots), to check the fix before a rebuild
EMULATE = KV.get("emulate", "0") == "1"
os.makedirs(f"{ROOT}/Saved/VehicleModels", exist_ok=True)
OUT = f"{ROOT}/Saved/VehicleModels/out_{TAG}.json"
SHOTS = f"{ROOT}/Saved/Screenshots/MacEditor"
LEN = {1: 4.72, 2: 4.79, 3: 5.98, 4: 4.34, 5: 7.34}
# yaw 0 = behind the car (the camera's back vector), 180 = in front; elevation in degrees
CAM = {"front": (155.0, 1.55, 9.0), "side": (90.0, 1.55, 6.0), "rear": (25.0, 1.55, 9.0),
       "frontclose": (172.0, 0.95, 4.0), "rearclose": (8.0, 0.95, 6.0), "chase": None,
       "glass": (125.0, 0.55, 12.0), "top": (60.0, 0.6, 38.0)}
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
if not ues.get_game_world():
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()
plan = []
for v in VEHS:
    plan.append(("veh", v))
    for w in VIEWS:
        plan.append(("view", v, w))
st = {"wait": 90, "i": 0, "phase": 0, "shots": [], "started": False, "t0": time.time()}
_h = None


def log(extra=None):
    d = {"tag": TAG, "kv": KV, "map": st.get("map"), "shots": st["shots"], "step": st["i"], "of": len(plan), "emulated": st.get("emulated")}
    d.update(extra or {})
    open(OUT, "w").write(json.dumps(d, indent=1))


def emulate_fix(p):
    body = next((c for c in p.get_components_by_class(unreal.StaticMeshComponent) if c.get_name() == "AltBody"), None)
    if body is None:
        return "no AltBody"
    names = [str(n) for n in body.get_material_slot_names()]
    head = next((body.get_material(i) for i, n in enumerate(names) if n == "Headlight"), None)
    tail = next((body.get_material(i) for i, n in enumerate(names) if n == "Taillight"), None)
    try:
        body.empty_override_materials()
    except Exception:
        for i in range(len(names)):
            body.set_material(i, None)
    for i, n in enumerate(names):
        if n in ("Headlight", "AuxLight") and head:
            body.set_material(i, head)
        elif n == "Taillight" and tail:
            body.set_material(i, tail)
    return {"slots": len(names), "head": head.get_name() if head else None, "tail": tail.get_name() if tail else None}


def tick(dt):
    try:
        gw = ues.get_game_world()
        if not gw:
            return
        pc = unreal.GameplayStatics.get_player_controller(gw, 0)
        p = pc.get_controlled_pawn() if pc else None
        if p is None or not hasattr(p, "get_mode"):
            return
        now = unreal.GameplayStatics.get_time_seconds(gw)       # wait in game time: slate ticks outrun a busy PIE
        if st["wait"] > 0:
            st["until"] = now + st["wait"] / 30.0
            st["wait"] = 0
        if now < st.get("until", 0.0):
            return
        if not st["started"]:
            st["started"] = True
            st["map"] = gw.get_name()
            log({"map": st["map"]})
            p.set_editor_property("test_input", True)
            for k in ("test_throttle", "test_brake", "test_steer"):
                p.set_editor_property(k, 0.0)
            if TP:
                p.test_teleport(unreal.Vector(TP[0], TP[1], TP[2]), TP[3])
            st["wait"] = 40
            return
        if st["i"] >= len(plan):
            p.set_editor_property("test_cam_dist", 0.0)
            p.set_editor_property("test_input", False)
            unreal.unregister_slate_post_tick_callback(_h)
            log({"done": True, "secs": round(time.time() - st["t0"], 1)})
            if STOP:
                unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_end_play()
            return
        step = plan[st["i"]]
        if step[0] == "veh":
            if st.get("veh_set") != st["i"]:
                p.set_editor_property("test_vehicle", step[1])
                st["veh_set"] = st["i"]
                st["wait"] = 45
                return
            if EMULATE:
                st.setdefault("emulated", []).append(emulate_fix(p))
            st["i"] += 1
            return
        v, w = step[1], step[2]
        if st["phase"] == 0:                 # set the camera and let it settle
            c = CAM.get(w)
            if c is None:
                p.set_editor_property("test_cam_dist", 0.0)
            else:
                p.set_editor_property("test_cam_dist", LEN[v] * c[1] + 1.5)
                p.set_editor_property("test_cam_yaw", c[0])
                p.set_editor_property("test_cam_elev", c[2])
            st["phase"] = 1
            st["wait"] = 30
            return
        if st["phase"] == 1:                 # shoot, then wait for the PNG to be written before moving the camera
            st["count"] = len(os.listdir(SHOTS)) if os.path.isdir(SHOTS) else 0
            unreal.SystemLibrary.execute_console_command(gw, f"HighResShot {RES}")
            cm = pc.player_camera_manager
            cl, car = cm.get_camera_location(), p.get_actor_location()
            fw, rt = p.get_actor_forward_vector(), p.get_actor_right_vector()
            d = cl - car
            ang = math.degrees(math.atan2(d.dot(rt) if hasattr(d, "dot") else (d.x * rt.x + d.y * rt.y), d.x * fw.x + d.y * fw.y))
            st["shots"].append({"veh": v, "view": w, "wall": time.time(), "cam_angle_from_nose": round(ang, 1),
                                "cam_dist_m": round(d.length() / 100.0, 1), "cam_h_m": round(d.z / 100.0, 1)})
            st["phase"] = 2
            st["shot_t"] = time.time()
            return
        n = len(os.listdir(SHOTS)) if os.path.isdir(SHOTS) else 0
        if n <= st["count"] and time.time() - st["shot_t"] < 8.0:
            return
        st["shots"][-1]["written"] = n > st["count"]
        st["phase"] = 0
        st["i"] += 1
        st["wait"] = 5
        log()
    except Exception as e:
        import traceback
        unreal.unregister_slate_post_tick_callback(_h)
        log({"error": str(e), "tb": traceback.format_exc()})


for _old in getattr(builtins, "_vm_ticks", []):
    try:
        unreal.unregister_slate_post_tick_callback(_old)
    except Exception:
        pass
_h = unreal.register_slate_post_tick_callback(tick)
builtins._vm_ticks = [_h]
