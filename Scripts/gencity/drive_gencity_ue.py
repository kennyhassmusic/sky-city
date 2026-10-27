"""Drive test and chase-camera shots on a generated-city drive level (GenCity_<Name>), in PIE, then quit the editor.

Started at editor launch on the level (it ticks across frames, so -ExecCmds, not -ExecutePythonScript):
  "$UE" "$PWD/SkyCity.uproject" /Game/Maps/GenCity_Seed7 -nosplash "$THROTTLE_OFF" -abslog=<log> \
    -ExecCmds="py $PWD/Scripts/gencity/drive_gencity_ue.py region=seed7_city tag=v1"
Steps:
  1. settle (default 75 s) with the level open: shaders and streaming, the clean-load window
  2. PIE: the level's game mode must spawn the Skyster (ASkysterCar) at the PlayerStart
  3. drive: through the car's test hooks (bTestInput), full throttle for secs (default 20) along the plan's route
     (Saved/GenCity/plan_<region>.json, plan_gencity.py), steering for the next waypoint. Every frame it logs the car's
     position, speed, mode and the ground under it (a line trace down). Pass: the car never ends a frame below the
     ground it is over (and the trace always finds ground), never leaves the city's bounds (+ pad), covers > 150 m.
     Frame time: the game-thread delta of every PIE frame while driving (mean, p50, p95, max).
  4. shots: the car teleported to each plan pose (downtown, suburbs, industrial, civic, farmland), the chase camera
     behind it, a HighResShot each; the aerial with the test camera pulled back and up.
Writes Saved/GenCity/drive_<tag>.json (incremental; "done": true at the end). The PNGs land in
Saved/Screenshots/MacEditor; the json maps each shot to its file.
"""
import builtins
import json
import math
import os
import sys
import time
import traceback

import unreal


def _root():
    try:
        d = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        d = None
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "SkyCity.uproject")):
            return d
        d = os.path.dirname(d)
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")


ROOT = _root()
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
REGION = KV.get("region", "seed7_city")
TAG = KV.get("tag", "drive")
SETTLE = float(KV.get("settle", "75"))
SECS = float(KV.get("secs", "20"))
RES = KV.get("res", "1920x1080")
QUIT = KV.get("quit", "1") == "1"
PAD_M = 60.0
PLAN = json.load(open(os.path.join(ROOT, "Saved", "GenCity", "plan_%s.json" % REGION)))
OUT = os.path.join(ROOT, "Saved", "GenCity", "drive_%s.json" % TAG)
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "MacEditor")
RAMP_SECS = float(KV.get("ramp_secs", "18"))
RAMP_THROTTLE = float(KV.get("ramp_throttle", "0.45"))
SHOT_CVARS = ("r.MotionBlurQuality 0", "r.DefaultFeature.MotionBlur 0", "r.AntiAliasingMethod 1")
ZERO = {"test_throttle": 0.0, "test_brake": 0.0, "test_steer": 0.0, "test_pitch": 0.0, "test_roll": 0.0,
        "test_stop": 0.0, "test_jump": False, "test_boost": False, "test_fly": False, "test_slide": False}

ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
st = {"t0": time.time(), "phase": "settle", "res": {"tag": TAG, "region": REGION, "level": PLAN.get("level"),
                                                     "done": False, "shots": []}, "log": [], "dts": []}
_h = None


def write():
    with open(OUT, "w") as handle:
        json.dump(st["res"], handle, indent=1, sort_keys=True)


def wrap(a):
    while a > 180:
        a -= 360
    while a < -180:
        a += 360
    return a


def ground_under(gw, p):
    loc = p.get_actor_location()
    a = unreal.Vector(loc.x, loc.y, loc.z + 50.0)
    b = unreal.Vector(loc.x, loc.y, loc.z - 5000.0)
    r = unreal.SystemLibrary.line_trace_single(gw, a, b, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [p],
                                               unreal.DrawDebugTrace.NONE, True)
    if r is None:
        return None
    t = r.to_tuple()
    if not t[0]:
        return None
    act = t[9]
    label = ""
    if act:
        label = act.get_actor_label() if hasattr(act, "get_actor_label") else act.get_name()
    return {"z": t[5].z, "actor": label}


def inside(loc):
    b = PLAN["bounds"]
    x, y = loc.y / 100.0, loc.x / 100.0          # plan x east = UE Y, plan y north = UE X
    return b[0] - PAD_M <= x <= b[2] + PAD_M and b[1] - PAD_M <= y <= b[3] + PAD_M


def pctl(values, q):
    v = sorted(values)
    return v[min(len(v) - 1, int(q * (len(v) - 1) + 0.5))] if v else None


def files():
    return set(os.listdir(SHOTS)) if os.path.isdir(SHOTS) else set()


def finish():
    unreal.unregister_slate_post_tick_callback(_h)
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
        builtins._gencity_quit = unreal.register_slate_post_tick_callback(later)


def tick(dt):
    try:
        now = time.time()
        res = st["res"]
        if st["phase"] == "settle":
            if now - st["t0"] < SETTLE:
                return
            unreal.log("GENCITY settle done after %.0f s" % (now - st["t0"]))
            res["settle_s"] = round(now - st["t0"], 1)
            les.editor_request_begin_play()
            st["phase"] = "pie"
            st["until"] = now + 60.0
            return
        gw = ues.get_game_world()
        if st["phase"] == "pie":
            p = None
            if gw:
                pc = unreal.GameplayStatics.get_player_controller(gw, 0)
                p = pc.get_controlled_pawn() if pc else None
            if p is None:
                if now > st["until"]:
                    res["error"] = "PIE started but no player pawn after 60 s"
                    finish()
                return
            st["pc"] = pc
            st["p"] = p
            res["pawn_class"] = p.get_class().get_name()
            loc = p.get_actor_location()
            res["spawn_at_ue"] = [round(loc.x), round(loc.y), round(loc.z)]
            gm = unreal.GameplayStatics.get_game_mode(gw)
            res["game_mode"] = gm.get_class().get_name() if gm else None
            if not hasattr(p, "get_mode"):
                res["error"] = "the player pawn is %s, not the Skyster" % res["pawn_class"]
                finish()
                return
            p.set_editor_property("test_input", True)
            p.set_editor_property("test_full_tank", True)
            for k, v in ZERO.items():
                p.set_editor_property(k, v)
            p.set_editor_property("test_brake", 1.0)
            st["phase"] = "wait_drive"
            st["until"] = now + 4.0
            write()
            return
        p = st["p"]
        if st["phase"] == "wait_drive":
            if now < st["until"]:
                return
            loc = p.get_actor_location()
            st["start"] = loc
            st["wi"] = 0
            st["drive_t0"] = now
            st["phase"] = "drive"
            res["drive"] = {"secs": SECS, "start_ue": [round(loc.x), round(loc.y), round(loc.z)], "below_ground": 0,
                            "no_ground": 0, "outside": 0, "frames": 0, "min_clear_cm": None, "max_mph": 0.0,
                            "modes": {}, "surfaces": {}, "track": []}
            p.set_editor_property("test_brake", 0.0)
            p.set_editor_property("test_throttle", 1.0)
            return
        if st["phase"] == "drive":
            d = res["drive"]
            t = now - st["drive_t0"]
            loc = p.get_actor_location()
            rot = p.get_actor_rotation()
            wps = PLAN["route"]["waypoints_ue"]
            while st["wi"] < len(wps) - 1 and math.hypot(wps[st["wi"]][0] - loc.x, wps[st["wi"]][1] - loc.y) < 1500.0:
                st["wi"] += 1
            wp = wps[st["wi"]]
            want = math.degrees(math.atan2(wp[1] - loc.y, wp[0] - loc.x))
            err = wrap(want - rot.yaw)
            p.set_editor_property("test_steer", max(-1.0, min(1.0, err / 20.0)))
            if t > 1.0:
                st["dts"].append(dt)
            g = ground_under(gw, p)
            mph = p.get_speed_mph()
            mode = p.get_mode()
            d["frames"] += 1
            d["max_mph"] = round(max(d["max_mph"], mph), 1)
            d["modes"][mode] = d["modes"].get(mode, 0) + 1
            if g is None:
                d["no_ground"] += 1
            else:
                clear = loc.z - g["z"]
                d["surfaces"][g["actor"][:40]] = d["surfaces"].get(g["actor"][:40], 0) + 1
                if d["min_clear_cm"] is None or clear < d["min_clear_cm"]:
                    d["min_clear_cm"] = round(clear, 1)
                if loc.z < g["z"] - 5.0:
                    d["below_ground"] += 1
            if loc.z < -200.0:
                d["below_ground"] += 1
            if not inside(loc):
                d["outside"] += 1
            if d["frames"] % 15 == 0:
                d["track"].append([round(t, 2), round(loc.x), round(loc.y), round(loc.z), round(mph, 1), mode])
            if t >= SECS:
                end = loc
                d["end_ue"] = [round(end.x), round(end.y), round(end.z)]
                d["dist_m"] = round(math.hypot(end.x - st["start"].x, end.y - st["start"].y) / 100.0, 1)
                d["secs_driven"] = round(t, 2)
                dts = st["dts"]
                res["frame_ms"] = {"n": len(dts), "mean": round(1000 * sum(dts) / max(1, len(dts)), 2),
                                   "p50": round(1000 * pctl(dts, 0.5), 2) if dts else None,
                                   "p95": round(1000 * pctl(dts, 0.95), 2) if dts else None,
                                   "max": round(1000 * max(dts), 2) if dts else None}
                d["pass"] = bool(d["below_ground"] == 0 and d["no_ground"] == 0 and d["outside"] == 0
                                 and d["dist_m"] > 150.0)
                for k, v in ZERO.items():
                    p.set_editor_property(k, v)
                p.set_editor_property("test_brake", 1.0)
                st["phase"] = "ramp_tp" if PLAN.get("ramp") else "shots_go"
                write()
            return
        if st["phase"] == "ramp_tp":
            r = PLAN["ramp"]
            p.test_teleport(unreal.Vector(*r["start_ue"]), r["yaw"])
            st["phase"] = "ramp_wait"
            st["until"] = now + 3.0
            return
        if st["phase"] == "ramp_wait":
            if now < st["until"]:
                return
            loc = p.get_actor_location()
            res["ramp"] = {"start_ue": [round(loc.x), round(loc.y), round(loc.z)], "z0": round(loc.z), "max_z": round(loc.z),
                           "below_ground": 0, "no_ground": 0, "frames": 0, "secs": RAMP_SECS}
            st["ramp_z0"] = loc.z
            p.set_editor_property("test_brake", 0.0)
            p.set_editor_property("test_throttle", RAMP_THROTTLE)
            st["ramp_t0"] = now
            st["phase"] = "ramp"
            return
        if st["phase"] == "ramp":
            r = res["ramp"]
            loc = p.get_actor_location()
            wps = PLAN["ramp"].get("waypoints_ue") or []
            wi = st.setdefault("ramp_wi", 0)
            while wi < len(wps) - 1 and math.hypot(wps[wi][0] - loc.x, wps[wi][1] - loc.y) < 250.0:
                wi += 1
            st["ramp_wi"] = wi
            if wps:
                want = math.degrees(math.atan2(wps[wi][1] - loc.y, wps[wi][0] - loc.x))
                err = wrap(want - p.get_actor_rotation().yaw)
                p.set_editor_property("test_steer", max(-1.0, min(1.0, err / 25.0)))
                # slow on the turn, then climb
                p.set_editor_property("test_throttle", RAMP_THROTTLE * (0.6 if abs(err) > 25.0 else 1.0))
            g = ground_under(gw, p)
            r["frames"] += 1
            r["max_z"] = max(r["max_z"], round(loc.z))
            if g is None:
                r["no_ground"] += 1
            elif loc.z < g["z"] - 5.0:
                r["below_ground"] += 1
            if g is not None and r["frames"] % 10 == 0:
                r.setdefault("track", []).append([round(now - st["ramp_t0"], 2), round(loc.x), round(loc.y),
                                                  round(loc.z), g["actor"][:30], p.get_mode()])
            if now - st["ramp_t0"] >= RAMP_SECS:
                r["climb_cm"] = round(r["max_z"] - st["ramp_z0"])
                r["pass"] = bool(r["climb_cm"] >= 250 and r["below_ground"] == 0 and r["no_ground"] == 0)
                for k, v in ZERO.items():
                    p.set_editor_property(k, v)
                p.set_editor_property("test_brake", 1.0)
                # the ramp shot, from the chase camera, then the zone shots
                st["phase"] = "shots_go"
                write()
            return
        if st["phase"] == "shots_go":
            st["phase"] = "shot_tp"
            st["si"] = 0
            # Shots: no motion blur and no temporal AA history. After a teleport the camera cuts, and TAA/TSR
            # blend the car with the previous view: it read as a ghosted, see-through car in v1.
            for cmd in SHOT_CVARS:
                unreal.SystemLibrary.execute_console_command(gw, cmd)
            write()
            return
        shots = PLAN["shots"]
        if st["si"] >= len(shots):
            p.set_editor_property("test_cam_dist", 0.0)
            p.set_editor_property("test_input", False)
            finish()
            return
        s = shots[st["si"]]
        if st["phase"] == "shot_tp":
            for k, v in ZERO.items():
                p.set_editor_property(k, v)
            p.set_editor_property("test_brake", 1.0)
            p.set_editor_property("test_stop", 1.0)           # parked: the shot is of a standing car
            p.test_teleport(unreal.Vector(s["ue"][0], s["ue"][1], 100.0), s["yaw"])
            cam = s.get("cam")
            if cam:
                p.set_editor_property("test_cam_dist", cam["dist_m"])
                p.set_editor_property("test_cam_yaw", cam["yaw"])
                p.set_editor_property("test_cam_elev", cam["elev"])
            else:
                p.set_editor_property("test_cam_dist", 0.0)
            st["phase"] = "shot_wait"
            st["until"] = now + (6.0 if cam else 4.0)
            return
        if st["phase"] == "shot_wait":
            if now < st["until"]:
                return
            st["before"] = files()
            unreal.SystemLibrary.execute_console_command(gw, "HighResShot %s" % RES)
            loc = p.get_actor_location()
            g = ground_under(gw, p)
            res["shots"].append({"name": s["name"], "zone": s.get("zone"), "mph": round(p.get_speed_mph(), 1), "car_ue": [round(loc.x), round(loc.y), round(loc.z)],
                                 "ground": g, "mode": p.get_mode(), "wall": round(now - st["t0"], 1)})
            st["phase"] = "shot_file"
            st["until"] = now + 15.0
            return
        if st["phase"] == "shot_file":
            new = sorted(files() - st["before"])
            if not new and now < st["until"]:
                return
            res["shots"][-1]["file"] = os.path.join(SHOTS, new[-1]) if new else None
            st["si"] += 1
            st["phase"] = "shot_tp"
            write()
            return
    except Exception:
        st["res"]["error"] = traceback.format_exc()
        try:
            finish()
        except Exception:
            unreal.unregister_slate_post_tick_callback(_h)
            write()


for _old in getattr(builtins, "_gencity_ticks", []):
    try:
        unreal.unregister_slate_post_tick_callback(_old)
    except Exception:
        pass
_h = unreal.register_slate_post_tick_callback(tick)
builtins._gencity_ticks = [_h]
write()
