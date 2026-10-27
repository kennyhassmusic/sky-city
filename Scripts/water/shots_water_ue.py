"""Lane 9: water A/B pictures, flow frames, frame times and a Skyster water test, in PIE; then quit the editor.

Full editor on the water level (it ticks across frames: -ExecCmds, not -ExecutePythonScript):
  "$UE" "$PWD/SkyCity.uproject" /Game/Maps/GenCity_Seed7_Water -nosplash ... -ExecCmds="py <this> tag=v1"
A camera actor (tag lane9_cam) is placed in the editor world before PIE and used as the view target. Modes:
  A = Water plugin bodies (tag lane9_A) shown, our water (lane9_B) hidden; B = the other way; none = both hidden.
For each mode: the four poses (Saved/Water/plan.json) as 1920x1080 HighResShots; two short frame sequences
(bridge, riverbank) at 960x540; frame time over 4 s at the aerial and bridge poses (game-thread delta, mean and
p95) and one ProfileGPU dump each (parsed from the log afterwards); the car test: the Skyster driven off the east
bank across the river, and dropped over the middle (its height and what a line trace finds under it).
Writes Saved/Water/shots_<tag>.json.
"""
import builtins
import json
import math
import os
import sys
import time
import traceback

import unreal

ROOT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
TAG = KV.get("tag", "v1")
SETTLE = float(KV.get("settle", "90"))
MODES = KV.get("modes", "A,B").split(",")
FRAMES = int(KV.get("frames", "24"))
QUIT = KV.get("quit", "1") == "1"
PLAN = json.load(open(os.path.join(ROOT, "Saved", "Water", "plan.json")))
OUT = os.path.join(ROOT, "Saved", "Water", "shots_%s.json" % TAG)
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "MacEditor")
CVARS = ("r.MotionBlurQuality 0", "r.DefaultFeature.MotionBlur 0", "r.AntiAliasingMethod 1")
ZERO = {"test_throttle": 0.0, "test_brake": 0.0, "test_steer": 0.0, "test_pitch": 0.0, "test_roll": 0.0,
        "test_stop": 0.0, "test_jump": False, "test_boost": False, "test_fly": False, "test_slide": False}
POSES = ["bridge", "riverbank", "aerial", "lake"]
SEQS = ["bridge", "riverbank"]
PARK = (1350.0, 150.0)          # where the car waits during the pictures (plan m), away from the river

ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
res = {"tag": TAG, "done": False, "shots": [], "frames": {}, "timing": {}, "car": {}, "log": []}
S = {"t0": time.time(), "q": [], "busy_until": 0.0, "wait_file": None}


def write():
    res["secs"] = round(time.time() - S["t0"], 1)
    with open(OUT, "w") as h:
        json.dump(res, h, indent=1, sort_keys=True, default=str)


def ue_vec(p, z):
    return unreal.Vector(p[1] * 100.0, p[0] * 100.0, z * 100.0)


def files():
    return set(os.listdir(SHOTS)) if os.path.isdir(SHOTS) else set()


def gw():
    return ues.get_game_world()


def cmd(c):
    unreal.SystemLibrary.execute_console_command(gw(), c)


def tagged(t):
    return list(unreal.GameplayStatics.get_all_actors_with_tag(gw(), unreal.Name(t)))


def set_mode(mode):
    for a in tagged("lane9_A"):
        a.set_actor_hidden_in_game(mode != "A")
    for a in tagged("lane9_B"):
        a.set_actor_hidden_in_game(mode != "B")
    S["mode"] = mode


def set_cam(name):
    p = PLAN["poses"][name]
    cam = S["cam"]
    cam.set_actor_location_and_rotation(ue_vec(p["plan"], p["plan"][2]), unreal.Rotator(0.0, p["pitch"], p["yaw"]),
                                        False, True)
    S["pc"].set_view_target_with_blend(cam, 0.0)


def ground_under(actor, z_up=300.0):
    loc = actor.get_actor_location()
    a = unreal.Vector(loc.x, loc.y, loc.z + z_up)
    b = unreal.Vector(loc.x, loc.y, loc.z - 5000.0)
    r = unreal.SystemLibrary.line_trace_single(gw(), a, b, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [actor],
                                               unreal.DrawDebugTrace.NONE, True)
    t = r.to_tuple() if r is not None else None
    if not t or not t[0]:
        return None
    act = t[9]
    return {"z_cm": round(t[5].z), "actor": (act.get_actor_label() if act else "")[:40]}


def park_car():
    p = S["p"]
    for k, v in ZERO.items():
        p.set_editor_property(k, v)
    p.set_editor_property("test_brake", 1.0)
    p.set_editor_property("test_stop", 1.0)
    p.test_teleport(ue_vec(PARK, 1.0), 0.0)


# --- the work queue: (kind, args) items run one per tick, each may hold the queue for a while ---------------

def plan_queue():
    q = []
    for mode in ["none"] + MODES:
        q.append(("mode", mode))
        q.append(("wait", 4.0))
        poses = ["aerial"] if mode == "none" else POSES
        for name in poses:
            q.append(("cam", name))
            q.append(("wait", 3.0 if name != "lake" else 3.5))
            q.append(("shot", (mode, name, "1920x1080")))
        for name in (["aerial", "bridge"]):
            q.append(("cam", name))
            q.append(("wait", 1.5))
            q.append(("time", (mode, name, 4.0)))
            q.append(("profile", (mode, name)))
            q.append(("wait", 2.0))
        if mode != "none":
            for name in SEQS:
                q.append(("cam", name))
                q.append(("wait", 2.0))
                for i in range(FRAMES):
                    q.append(("frame", (mode, name, i)))
            q.append(("car_bank", mode))
            q.append(("car_drop", mode))
            q.append(("park", None))
    q.append(("finish", None))
    return q


def do(item, now, dt):
    kind, arg = item
    if kind == "mode":
        set_mode(arg)
        res["log"].append("mode %s at %.0f s" % (arg, now - S["t0"]))
        return True
    if kind == "wait":
        if "until" not in S:
            S["until"] = now + arg
        if now < S["until"]:
            return False
        del S["until"]
        return True
    if kind == "cam":
        set_cam(arg)
        return True
    if kind in ("shot", "frame"):
        if S.get("wait_file") is None:
            S["before"] = files()
            if kind == "shot":
                mode, name, rez = arg
            else:
                mode, name, i = arg
                rez = "960x540"
            cmd("HighResShot %s" % rez)
            S["wait_file"] = now + 20.0
            S["issued"] = now
            return False
        new = sorted(files() - S["before"])
        if not new and now < S["wait_file"]:
            return False
        S["wait_file"] = None
        f = os.path.join(SHOTS, new[-1]) if new else None
        if kind == "shot":
            res["shots"].append({"mode": arg[0], "pose": arg[1], "file": f, "t": round(now - S["t0"], 2)})
        else:
            res["frames"].setdefault("%s_%s" % (arg[0], arg[1]), []).append({"file": f, "t": round(S["issued"] - S["t0"], 3)})
        write()
        return True
    if kind == "time":
        mode, name, secs = arg
        if "tt0" not in S:
            S["tt0"] = now
            S["dts"] = []
            return False
        S["dts"].append(dt)
        if now - S["tt0"] < secs:
            return False
        d = sorted(S["dts"])
        res["timing"]["%s_%s" % (mode, name)] = {"n": len(d), "mean_ms": round(1000 * sum(d) / len(d), 2),
                                                 "p50_ms": round(1000 * d[len(d) // 2], 2),
                                                 "p95_ms": round(1000 * d[int(0.95 * (len(d) - 1))], 2)}
        del S["tt0"]
        write()
        return True
    if kind == "profile":
        unreal.log("LANE9 PROFILEGPU %s %s" % arg)
        cmd("ProfileGPU")
        return True
    if kind == "car_bank":
        p = S["p"]
        if "cb" not in S:
            S["cb"] = {"t0": now, "track": []}
            for k, v in ZERO.items():
                p.set_editor_property(k, v)
            p.test_teleport(ue_vec(PLAN["car"]["bank_plan"], 1.0), PLAN["car"]["bank_yaw"])
            S["cam_follow"] = True
            p.set_editor_property("test_cam_dist", 9.0)
            p.set_editor_property("test_cam_yaw", 0.0)
            p.set_editor_property("test_cam_elev", 12.0)
            S["pc"].set_view_target_with_blend(p, 0.0)
            return False
        t = now - S["cb"]["t0"]
        if t > 1.5:
            p.set_editor_property("test_throttle", 0.55)
        if t > 1.5 and len(S["cb"]["track"]) % 1 == 0 and int(t * 4) != S["cb"].get("last"):
            S["cb"]["last"] = int(t * 4)
            loc = p.get_actor_location()
            S["cb"]["track"].append([round(t, 2), round(loc.y / 100.0, 1), round(loc.x / 100.0, 1), round(loc.z),
                                     ground_under(p), p.get_mode(), round(p.get_speed_mph(), 1)])
        if t > 3.5 and "mid_shot" not in S["cb"]:
            S["cb"]["mid_shot"] = True
            S["before_cb"] = files()
            cmd("HighResShot 1280x720")
        if t < 7.5:
            return False
        new = sorted(files() - S.get("before_cb", set()))
        res["car"]["%s_bank" % arg] = {"track": S["cb"]["track"], "shot": os.path.join(SHOTS, new[-1]) if new else None}
        for k, v in ZERO.items():
            p.set_editor_property(k, v)
        p.set_editor_property("test_brake", 1.0)
        del S["cb"]
        write()
        return True
    if kind == "car_drop":
        p = S["p"]
        if "cd" not in S:
            S["cd"] = {"t0": now, "track": []}
            p.test_teleport(ue_vec(PLAN["car"]["drop_plan"], 3.0), PLAN["car"]["bank_yaw"] + 90.0)
            return False
        t = now - S["cd"]["t0"]
        if int(t * 4) != S["cd"].get("last"):
            S["cd"]["last"] = int(t * 4)
            loc = p.get_actor_location()
            S["cd"]["track"].append([round(t, 2), round(loc.z), ground_under(p), p.get_mode()])
        if t < 5.0:
            return False
        res["car"]["%s_drop" % arg] = {"track": S["cd"]["track"]}
        del S["cd"]
        write()
        return True
    if kind == "park":
        park_car()
        p = S["p"]
        p.set_editor_property("test_cam_dist", 0.0)
        S["pc"].set_view_target_with_blend(S["cam"], 0.0)
        return True
    if kind == "finish":
        finish()
        return True
    return True


def finish():
    unreal.unregister_slate_post_tick_callback(builtins._lane9_tick)
    res["done"] = True
    write()
    if gw():
        les.editor_request_end_play()
    if QUIT:
        S["quit_at"] = time.time() + 3.0

        def later(_dt):
            if time.time() > S["quit_at"]:
                unreal.SystemLibrary.quit_editor()
        builtins._lane9_quit = unreal.register_slate_post_tick_callback(later)


def tick(dt):
    try:
        now = time.time()
        phase = S.get("phase", "settle")
        if phase == "settle":
            if now - S["t0"] < SETTLE:
                return
            res["settle_s"] = round(now - S["t0"], 1)
            cam = eas.spawn_actor_from_class(unreal.CameraActor, unreal.Vector(0, 0, 5000), unreal.Rotator(0, 0, 0))
            cam.set_editor_property("tags", [unreal.Name("lane9_cam")])
            cam.camera_component.set_editor_property("field_of_view", 70.0)
            cam.camera_component.set_editor_property("constrain_aspect_ratio", False)
            les.editor_request_begin_play()
            S["phase"] = "pie"
            S["until"] = now + 90.0
            return
        if phase == "pie":
            w = gw()
            p = None
            if w:
                pc = unreal.GameplayStatics.get_player_controller(w, 0)
                p = pc.get_controlled_pawn() if pc else None
            if p is None:
                if now > S["until"]:
                    res["error"] = "no pawn in PIE after 90 s"
                    finish()
                return
            del S["until"]
            S["pc"], S["p"] = pc, p
            res["pawn"] = p.get_class().get_name()
            cams = tagged("lane9_cam")
            if not cams:
                res["error"] = "no lane9_cam in the PIE world"
                finish()
                return
            S["cam"] = cams[0]
            p.set_editor_property("test_input", True)
            p.set_editor_property("test_full_tank", True)
            park_car()
            for c in CVARS:
                cmd(c)
            res["counts"] = {"A": len(tagged("lane9_A")), "B": len(tagged("lane9_B"))}
            # The car's HUD off for the pictures.
            cmd("ShowHUD")
            cmd("DisableAllScreenMessages")
            S["q"] = plan_queue()
            S["phase"] = "run"
            write()
            return
        if phase == "run":
            if not S["q"]:
                return
            if do(S["q"][0], now, dt):
                S["q"].pop(0)
    except Exception:
        res["error"] = traceback.format_exc()
        try:
            finish()
        except Exception:
            write()


for _old in getattr(builtins, "_lane9_ticks", []):
    try:
        unreal.unregister_slate_post_tick_callback(_old)
    except Exception:
        pass
builtins._lane9_tick = unreal.register_slate_post_tick_callback(tick)
builtins._lane9_ticks = [builtins._lane9_tick]
write()
