"""Wind proof on a generated-city drive level (lane 8), in PIE: frame sequences of the waving flags and swaying trees
(wind off, then on), and GPU / frame time with the wind off and on. Run after wind_gencity_ue.py, full editor:
  "$UE" "$PWD/SkyCity.uproject" /Game/Maps/GenCity_Seed7 -nosplash "$THROTTLE_OFF" -abslog=<log> \
    -ExecCmds="py <space-free path>/Scripts/gencity/wind_shots_gencity_ue.py region=seed7_city bt=<bt> tag=w1"
Frames: MPC_Wind TimeScale 0 and TimeOffset stepped by 1/fps per frame, so every frame is exactly 0.1 s of wind
apart however long a HighResShot takes. Cameras: CameraActors placed before PIE (not saved) and made the view
target. Perf: the car parked at the plan's downtown pose, chase camera; for off/on/off/on, the game-thread frame
time over `perf_secs` and ProfileGPU twice (the log, between WIND_AB markers; read with --read <log>).
Writes Saved/GenCity/wind_<tag>.json; the PNGs land in Saved/Screenshots/MacEditor.
"""
import builtins
import json
import math
import os
import re
import sys
import time
import traceback

KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)


def read_log(path):
    """{state: [<root> ms of each ProfileGPU dump that drew the scene]} between the WIND_AB markers."""
    text = open(path, errors="replace").read()
    out = {}
    for m in re.finditer(r"WIND_AB begin state=(\w+)(.*?)WIND_AB end", text, re.S):
        dumps, cur = [], None
        for line in m.group(2).splitlines():
            hit = re.search(r"([\d.]+) ms \S\s+<root>\s", line) or re.search(r"([\d.]+)ms\s+<root>", line)
            if hit:
                cur = {"root": float(hit.group(1)), "scene": False}
                dumps.append(cur)
            if cur is not None and any(k in line for k in ("BasePass", "ShadowDepths", "Lumen")):
                cur["scene"] = True
        out.setdefault(m.group(1), []).extend(d["root"] for d in dumps if d["scene"])
    return out


if "--read" in sys.argv:
    res = read_log(sys.argv[sys.argv.index("--read") + 1])
    for k, v in sorted(res.items()):
        print(k, "GPU <root> ms", [round(x, 2) for x in v], "mean %.2f" % (sum(v) / len(v)) if v else "")
    sys.exit(0)

import unreal  # noqa: E402

ROOT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")
REGION = KV.get("region", "seed7_city")
TAG = KV.get("tag", "wind")
BT = KV["bt"]
SETTLE = float(KV.get("settle", "90"))
FRAMES = int(KV.get("frames", "24"))
OFF_FRAMES = int(KV.get("off_frames", "4"))
FPS = float(KV.get("fps", "10"))
RES = KV.get("res", "1280x720")
PERF_SECS = float(KV.get("perf_secs", "6"))
QUIT = KV.get("quit", "1") == "1"
WIND = json.load(open(os.path.join(BT, "Saved", "CityGen", "wind_%s.json" % REGION)))
PLAN = json.load(open(os.path.join(ROOT, "Saved", "GenCity", "plan_%s.json" % REGION)))
OUT = os.path.join(ROOT, "Saved", "GenCity", "wind_%s.json" % TAG)
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "MacEditor")
MPC = unreal.EditorAssetLibrary.load_asset("/Game/CityGen/Wind/MPC_Wind")
SHOT_CVARS = ("r.MotionBlurQuality 0", "r.DefaultFeature.MotionBlur 0", "r.AntiAliasingMethod 1", "r.ProfileGPU.ShowUI 0")

ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
st = {"t0": time.time(), "phase": "settle", "res": {"tag": TAG, "region": REGION, "done": False, "clips": [], "perf": []}}


def write():
    with open(OUT, "w") as fh:
        json.dump(st["res"], fh, indent=1, sort_keys=True)


def files():
    return set(os.listdir(SHOTS)) if os.path.isdir(SHOTS) else set()


def look(eye, target):
    d = [target[i] - eye[i] for i in range(3)]
    yaw = math.degrees(math.atan2(d[1], d[0]))
    pitch = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
    return unreal.Rotator(roll=0.0, pitch=pitch, yaw=yaw)


def flag_camera(flags, dist_cm, back_cm=0.0, up_cm=-120.0):
    """A camera beside a flag (or the middle of a group of flags), across the wind, looking at the flown flags."""
    wx, wy = WIND["prevailing"]["toward_ue"]
    cx = sum(f["hoist_top_ue"][0] for f in flags) / len(flags)
    cy = sum(f["hoist_top_ue"][1] for f in flags) / len(flags)
    cz = sum(f["hoist_top_ue"][2] for f in flags) / len(flags)
    tgt = [cx + wx * 90.0, cy + wy * 90.0, cz - 60.0]
    side = (-wy, wx)
    eye = [tgt[0] + side[0] * dist_cm - wx * back_cm, tgt[1] + side[1] * dist_cm - wy * back_cm, cz + up_cm]
    return eye, tgt


def subjects():
    F = WIND["flags"]
    out = []
    school = [f for f in F if f["kind"] == "school"]
    if school:
        s = max(school, key=lambda f: f["exposure"])
        eye, tgt = flag_camera([s], 750.0)
        out.append({"name": "school_flag", "eye": eye, "target": tgt, "flags": [s["hoist_top_ue"]]})
    # the flag row: the biggest group of flags within 20 m of each other
    best = []
    for f in F:
        grp = [g for g in F if math.dist(f["hoist_top_ue"][:2], g["hoist_top_ue"][:2]) < 2000.0]
        if len(grp) > len(best):
            best = grp
    if len(best) > 1:
        eye, tgt = flag_camera(best, 1700.0, back_cm=300.0, up_cm=-250.0)
        out.append({"name": "flag_row", "eye": eye, "target": tgt, "flags": [f["hoist_top_ue"] for f in best]})
    # trees: the plan's suburbs pose, from a little above the street
    for s in PLAN.get("shots", []):
        if s.get("zone") in ("suburbs", "residential") or s["name"].startswith("suburb"):
            x, y = s["ue"][0], s["ue"][1]
            yaw = math.radians(s["yaw"])
            eye = [x - math.cos(yaw) * 600.0, y - math.sin(yaw) * 600.0, 450.0]
            tgt = [x + math.cos(yaw) * 2500.0, y + math.sin(yaw) * 2500.0, 350.0]
            out.append({"name": "trees", "eye": eye, "target": tgt})
            break
    return out


def place_cameras(subs):
    for a in eas.get_all_level_actors():
        if a.get_actor_label().startswith("WindCam_"):
            eas.destroy_actor(a)
    for s in subs:
        cam = eas.spawn_actor_from_class(unreal.CameraActor, unreal.Vector(*s["eye"]), look(s["eye"], s["target"]))
        cam.set_actor_label("WindCam_" + s["name"])
        cc = cam.get_component_by_class(unreal.CameraComponent)
        cc.set_editor_property("field_of_view", 50.0)
        cc.set_editor_property("constrain_aspect_ratio", False)


def mpc(gw, name, value):
    unreal.MaterialLibrary.set_scalar_parameter_value(gw, MPC, name, float(value))


def finish():
    unreal.unregister_slate_post_tick_callback(builtins._wind_tick)
    st["res"]["done"] = True
    st["res"]["secs_total"] = round(time.time() - st["t0"], 1)
    write()
    if ues.get_game_world():
        les.editor_request_end_play()
    if QUIT:
        st["quit_at"] = time.time() + 3.0

        def later(_dt):
            if time.time() > st["quit_at"]:
                unreal.SystemLibrary.quit_editor()
        builtins._wind_quit = unreal.register_slate_post_tick_callback(later)


def frame_steps():
    """(clip index, state, frame index) for every frame: OFF_FRAMES with the wind off, FRAMES with it on."""
    out = []
    for ci in range(len(st["subs"])):
        out += [(ci, "off", k) for k in range(OFF_FRAMES)] + [(ci, "on", k) for k in range(FRAMES)]
    return out


def tick(dt):
    try:
        now = time.time()
        res = st["res"]
        if st["phase"] == "settle":
            if now - st["t0"] < SETTLE:
                return
            st["subs"] = subjects()
            res["subjects"] = st["subs"]
            place_cameras(st["subs"])
            les.editor_request_begin_play()
            st["phase"] = "pie"
            st["until"] = now + 60.0
            write()
            return
        gw = ues.get_game_world()
        if st["phase"] == "pie":
            pc = unreal.GameplayStatics.get_player_controller(gw, 0) if gw else None
            p = pc.get_controlled_pawn() if pc else None
            if p is None:
                if now > st["until"]:
                    res["error"] = "no pawn in PIE"
                    finish()
                return
            st["pc"], st["p"] = pc, p
            if hasattr(p, "get_mode"):
                p.set_editor_property("test_input", True)
                p.set_editor_property("test_brake", 1.0)
                p.set_editor_property("test_stop", 1.0)
            for c in SHOT_CVARS:
                unreal.SystemLibrary.execute_console_command(gw, c)
            st["cams"] = {a.get_actor_label(): a for a in unreal.GameplayStatics.get_all_actors_of_class(gw, unreal.CameraActor)}
            res["cams_found"] = sorted(st["cams"])
            # perf first: the car at the plan's downtown pose, its chase camera
            shots = PLAN.get("shots", [])
            down = next((s for s in shots if s.get("zone") == "downtown" or s["name"].startswith("downtown")), shots[0] if shots else None)
            if down and hasattr(p, "test_teleport"):
                p.test_teleport(unreal.Vector(down["ue"][0], down["ue"][1], 100.0), down["yaw"])
                cam = down.get("cam")
                if cam:
                    p.set_editor_property("test_cam_dist", cam["dist_m"])
                    p.set_editor_property("test_cam_yaw", cam["yaw"])
                    p.set_editor_property("test_cam_elev", cam["elev"])
            res["perf_pose"] = down and down["name"]
            st["perf"] = ["off", "on", "off", "on"]
            st["phase"] = "perf_set"
            st["until"] = now + 8.0
            return
        p = st["p"]
        if st["phase"] == "perf_set":
            if now < st["until"]:
                return
            if not st["perf"]:
                st["phase"] = "clip_set"
                st["steps"] = frame_steps()
                st["si"] = 0
                mpc(gw, "TimeScale", 0.0)
                write()
                return
            state = st["perf"][0]
            mpc(gw, "WindOn", 1.0 if state == "on" else 0.0)
            st["dts"] = []
            st["phase"] = "perf_warm"
            st["until"] = now + 3.0
            return
        if st["phase"] == "perf_warm":
            if now < st["until"]:
                return
            st["phase"] = "perf_run"
            st["until"] = now + PERF_SECS
            return
        if st["phase"] == "perf_run":
            st["dts"].append(dt)
            if now < st["until"]:
                return
            state = st["perf"].pop(0)
            d = sorted(st["dts"])
            res["perf"].append({"state": state, "n": len(d), "mean_ms": round(1000 * sum(d) / max(1, len(d)), 2),
                                "p95_ms": round(1000 * d[int(0.95 * (len(d) - 1))], 2) if d else None})
            unreal.log("WIND_AB begin state=%s" % state)
            unreal.SystemLibrary.execute_console_command(gw, "ProfileGPU")
            st["phase"] = "perf_gpu2"
            st["until"] = now + 2.0
            st["state"] = state
            return
        if st["phase"] == "perf_gpu2":
            if now < st["until"]:
                return
            unreal.SystemLibrary.execute_console_command(gw, "ProfileGPU")
            st["phase"] = "perf_gpu_end"
            st["until"] = now + 2.0
            return
        if st["phase"] == "perf_gpu_end":
            if now < st["until"]:
                return
            unreal.log("WIND_AB end")
            st["phase"] = "perf_set"
            st["until"] = now
            write()
            return
        if st["phase"] == "clip_set":
            if st["si"] >= len(st["steps"]):
                mpc(gw, "TimeScale", 1.0)
                mpc(gw, "TimeOffset", 0.0)
                mpc(gw, "WindOn", 1.0)
                finish()
                return
            ci, state, k = st["steps"][st["si"]]
            sub = st["subs"][ci]
            cam = st["cams"].get("WindCam_" + sub["name"])
            if cam is not None and (st.get("cam_for") != ci):
                st["pc"].set_view_target_with_blend(cam, 0.0)
                st["cam_for"] = ci
                st["until"] = now + 4.0       # streaming and shadows at the new view
            else:
                st["until"] = now + 0.25
            mpc(gw, "WindOn", 1.0 if state == "on" else 0.0)
            mpc(gw, "TimeOffset", 100.0 + k / FPS)
            st["phase"] = "clip_wait"
            return
        if st["phase"] == "clip_wait":
            if now < st["until"]:
                return
            st["before"] = files()
            unreal.SystemLibrary.execute_console_command(gw, "HighResShot %s" % RES)
            st["phase"] = "clip_file"
            st["until"] = now + 15.0
            return
        if st["phase"] == "clip_file":
            new = sorted(files() - st["before"])
            if not new and now < st["until"]:
                return
            ci, state, k = st["steps"][st["si"]]
            res["clips"].append({"subject": st["subs"][ci]["name"], "state": state, "k": k,
                                 "file": os.path.join(SHOTS, new[-1]) if new else None})
            st["si"] += 1
            st["phase"] = "clip_set"
            if st["si"] % 8 == 0:
                write()
            return
    except Exception:
        st["res"]["error"] = traceback.format_exc()
        try:
            finish()
        except Exception:
            write()


for _old in getattr(builtins, "_wind_ticks", []):
    try:
        unreal.unregister_slate_post_tick_callback(_old)
    except Exception:
        pass
builtins._wind_tick = unreal.register_slate_post_tick_callback(tick)
builtins._wind_ticks = [builtins._wind_tick]
write()
