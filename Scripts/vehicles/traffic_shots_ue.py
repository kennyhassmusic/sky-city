"""Close shots of Sky City street traffic (ASkysterTraffic bodies use the line-up assets' own materials, so they show the
vehicle-models glass/lamp fixes without any C++ change). Read-only: starts PIE in the loaded map (SkyCityMashup) if it
isn't running, borrows the GameNetworkManager actor as a camera (Python can't spawn into the PIE world; same trick as
Saved/MCPScripts/cab_cam.py), frames the nearest ground car of each model in turn, takes a HighResShot, stops PIE.
Run: py Scripts/vehicles/traffic_shots_ue.py tag=traffic_after [dist=7] [up=2.2] [res=960x540]
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
TAG = KV.get("tag", "traffic")
DIST, UP, RES = float(KV.get("dist", 7.0)), float(KV.get("up", 2.2)), KV.get("res", "960x540")
OUT = f"{ROOT}/Saved/VehicleModels/out_{TAG}.json"
SHOTS = f"{ROOT}/Saved/Screenshots/MacEditor"
MODELS = ["Model3", "ModelY", "Cybertruck", "Robotaxi", "Semi"]
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
if not ues.get_game_world():
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()
st = {"phase": "warm", "until": None, "shots": [], "queue": None, "cam": None, "t0": time.time()}
_h = None


def log(extra=None):
    d = {"tag": TAG, "kv": KV, "shots": st["shots"]}
    d.update(extra or {})
    open(OUT, "w").write(json.dumps(d, indent=1))


def bodies(gw):
    out = {}
    for tr in unreal.GameplayStatics.get_all_actors_of_class(gw, unreal.SkysterTraffic):
        for c in tr.get_components_by_class(unreal.StaticMeshComponent):
            m = c.static_mesh
            if m and m.get_name().endswith("_Body") and c.is_visible() and c.get_world_location().z < 1000:
                out.setdefault(m.get_name().split("_")[1], []).append(c)
    return out


def frame(c):
    loc, rot = c.get_world_location(), c.get_world_rotation()
    yaw = math.radians(rot.yaw + 140.0)
    cp = unreal.Vector(loc.x + math.cos(yaw) * DIST * 100, loc.y + math.sin(yaw) * DIST * 100, loc.z + UP * 100)
    d = loc - cp
    look = unreal.Rotator(roll=0, pitch=math.degrees(math.atan2(d.z + 60, math.hypot(d.x, d.y))), yaw=math.degrees(math.atan2(d.y, d.x)))
    st["cam"].set_actor_location_and_rotation(cp, look, False, True)


def tick(dt):
    try:
        gw = ues.get_game_world()
        if not gw:
            return
        pc = unreal.GameplayStatics.get_player_controller(gw, 0)
        if pc is None or pc.get_controlled_pawn() is None:
            return
        now = unreal.GameplayStatics.get_time_seconds(gw)
        if st["until"] is None:
            st["until"] = now + 4.0
        if now < st["until"]:
            if st["phase"] == "settle" and st["queue"]:
                frame(st["queue"][0][1])             # keep framing a moving car
            return
        if st["phase"] == "warm":
            me = pc.get_controlled_pawn().get_actor_location()
            bs = bodies(gw)
            st["queue"] = [(k, min(v, key=lambda c: (c.get_world_location() - me).length())) for k, v in bs.items()]
            st["queue"].sort(key=lambda kv: MODELS.index(kv[0]) if kv[0] in MODELS else 9)
            cam = next((a for a in unreal.GameplayStatics.get_all_actors_of_class(gw, unreal.Actor) if "GameNetworkManager" in a.get_name()), None)
            st["cam"], st["cam_xf"] = cam, (cam.get_actor_location(), cam.get_actor_rotation())
            cam.set_actor_hidden_in_game(True)
            log({"models": [k for k, _ in st["queue"]]})
            st["phase"] = "next"
        if st["phase"] == "next":
            if not st["queue"]:
                pc.set_view_target_with_blend(pc.get_controlled_pawn(), 0.0)
                st["cam"].set_actor_location_and_rotation(st["cam_xf"][0], st["cam_xf"][1], False, True)
                st["cam"].set_actor_hidden_in_game(False)
                unreal.unregister_slate_post_tick_callback(_h)
                log({"done": True, "secs": round(time.time() - st["t0"], 1)})
                unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_end_play()
                return
            frame(st["queue"][0][1])
            pc.set_view_target_with_blend(st["cam"], 0.0)
            st["phase"], st["until"] = "settle", now + 0.8
            return
        if st["phase"] == "settle":
            st["count"] = len(os.listdir(SHOTS))
            unreal.SystemLibrary.execute_console_command(gw, f"HighResShot {RES}")
            k = st["queue"][0][0]
            st["shots"].append({"veh": MODELS.index(k) + 1 if k in MODELS else 0, "view": "traffic", "model": k, "wall": time.time()})
            st["phase"], st["shot_t"] = "wait", time.time()
            return
        if st["phase"] == "wait":
            if len(os.listdir(SHOTS)) <= st["count"] and time.time() - st["shot_t"] < 8:
                return
            st["queue"].pop(0)
            st["phase"] = "next"
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
