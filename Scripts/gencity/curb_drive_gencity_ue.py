"""Curb and ditch drive checks (lane P, v10): the Skyster driven from a start pose straight at a curb return, a
crosswalk ramp, a dropped curb (driveway) and into a roadside ditch, in PIE, then quit.
  "$UE" "$PWD/SkyCity.uproject" /Game/Maps/GenCity_Seed7 -nosplash ... \
    -ExecCmds="py <space-free path>/Scripts/gencity/curb_drive_gencity_ue.py in=Saved/GenCity/curbtests_seed7_city.json tag=v10"
Input: [{name, start_ue, yaw, secs, throttle, target_plan}] (plan metres; UE X = plan y, Y = plan x). For each: the
car's track every 0.1 s (position, height, speed, mode, the ground under it) and a chase-camera frame halfway. The
verdict is left to the reader of the track: climbed (z rose to the walk and the car kept going), stopped (speed fell
to ~0 at the curb), bounced/airborne, or went into the ditch and out. Writes Saved/GenCity/curb_<tag>.json.
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
TAG = KV.get("tag", "curb")
TESTS = json.load(open(os.path.join(ROOT, KV.get("in", "Saved/GenCity/curbtests_seed7_city.json"))))
SETTLE = float(KV.get("settle", "40"))
OUT = os.path.join(ROOT, "Saved", "GenCity", "curb_%s.json" % TAG)
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "MacEditor")
ZERO = {"test_throttle": 0.0, "test_brake": 0.0, "test_steer": 0.0, "test_pitch": 0.0, "test_roll": 0.0,
        "test_stop": 0.0, "test_jump": False, "test_boost": False, "test_fly": False, "test_slide": False}
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
res = {"tag": TAG, "done": False, "tests": []}
S = {"t0": time.time(), "phase": "settle", "i": 0}


def write():
    with open(OUT, "w") as h:
        json.dump(res, h, indent=1, default=str)


def gw():
    return ues.get_game_world()


def ground(p):
    loc = p.get_actor_location()
    r = unreal.SystemLibrary.line_trace_single(gw(), unreal.Vector(loc.x, loc.y, loc.z + 80),
                                               unreal.Vector(loc.x, loc.y, loc.z - 2000),
                                               unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [p],
                                               unreal.DrawDebugTrace.NONE, True)
    t = r.to_tuple() if r is not None else None
    if not t or not t[0]:
        return None
    a = t[9]
    return [round(t[5].z, 1), (a.get_actor_label() if a else "")[:40]]


def finish():
    unreal.unregister_slate_post_tick_callback(builtins._lanep_curb)
    res["done"] = True
    write()
    les.editor_request_end_play()
    S["quit_at"] = time.time() + 3.0

    def later(_d):
        if time.time() > S["quit_at"]:
            unreal.SystemLibrary.quit_editor()
    builtins._lanep_curb_quit = unreal.register_slate_post_tick_callback(later)


def tick(_dt):
    try:
        now = time.time()
        if S["phase"] == "settle":
            if now - S["t0"] >= SETTLE:
                les.editor_request_begin_play()
                S["phase"], S["until"] = "pie", now + 90
            return
        if S["phase"] == "pie":
            w = gw()
            pc = unreal.GameplayStatics.get_player_controller(w, 0) if w else None
            p = pc.get_controlled_pawn() if pc else None
            if p is None:
                if now > S["until"]:
                    res["error"] = "no pawn"
                    finish()
                return
            S["p"] = p
            p.set_editor_property("test_input", True)
            p.set_editor_property("test_cam_dist", 9.0)
            p.set_editor_property("test_cam_yaw", 35.0)
            p.set_editor_property("test_cam_elev", 14.0)
            for c in ("r.MotionBlurQuality 0", "r.AntiAliasingMethod 1", "ShowHUD", "DisableAllScreenMessages"):
                unreal.SystemLibrary.execute_console_command(gw(), c)
            S["phase"] = "start"
            return
        p = S["p"]
        if S["phase"] == "start":
            if S["i"] >= len(TESTS):
                finish()
                return
            t = TESTS[S["i"]]
            for k, v in ZERO.items():
                p.set_editor_property(k, v)
            p.set_editor_property("test_brake", 1.0)
            p.set_editor_property("test_stop", 1.0)             # X holds the car: start from rest
            p.test_teleport(unreal.Vector(*t["start_ue"]), t["yaw"])
            S["rec"] = {"name": t["name"], "start_ue": t["start_ue"], "yaw": t["yaw"], "track": []}
            S["t1"] = now + 2.5
            S["phase"] = "run"
            return
        if S["phase"] == "run":
            t = TESTS[S["i"]]
            rec = S["rec"]
            el = now - S["t1"]
            if el < 0:
                return
            p.set_editor_property("test_brake", 0.0)
            p.set_editor_property("test_stop", 0.0)
            p.set_editor_property("test_throttle", t["throttle"])
            p.set_editor_property("test_steer", 0.0)
            if int(el * 10) != S.get("last"):
                S["last"] = int(el * 10)
                loc = p.get_actor_location()
                rec["track"].append([round(el, 1), round(loc.x), round(loc.y), round(loc.z), round(p.get_speed_mph(), 1),
                                     p.get_mode(), ground(p)])
            if el > t["secs"] / 2 and "shot" not in rec:
                rec["shot"] = True
                S["before"] = set(os.listdir(SHOTS))
                unreal.SystemLibrary.execute_console_command(gw(), "HighResShot 1280x720")
            if el < t["secs"]:
                return
            new = sorted(set(os.listdir(SHOTS)) - S.get("before", set()))
            rec["shot"] = os.path.join(SHOTS, new[-1]) if new else None
            tr = rec["track"]
            z0 = tr[0][3] if tr else 0
            rec["summary"] = {"z_start": z0, "z_max": max(r[3] for r in tr), "z_min": min(r[3] for r in tr),
                              "z_end": tr[-1][3], "mph_max": max(r[4] for r in tr), "mph_end": tr[-1][4],
                              "moved_m": round(math.hypot(tr[-1][1] - tr[0][1], tr[-1][2] - tr[0][2]) / 100.0, 1),
                              "modes": sorted({r[5] for r in tr}), "ground_end": tr[-1][6]}
            res["tests"].append(rec)
            write()
            S["i"] += 1
            S["phase"] = "start"
    except Exception:
        res["error"] = traceback.format_exc()
        write()
        try:
            finish()
        except Exception:
            unreal.SystemLibrary.quit_editor()


builtins._lanep_curb = unreal.register_slate_post_tick_callback(tick)
write()
