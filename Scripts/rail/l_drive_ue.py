"""Drive test for the L (read-only: writes Saved/Rail/drive/out_<tag>.json and HighResShots). Runs in PIE through the
SkysterCar test hooks (same hooks as Saved/Playtest/pt.py): for each run the car is reset, teleported to a start pose and
driven through waypoints at a target speed, steering for the waypoints; it logs what a player would hit.
Per run: speed drops (> 8 mph in 0.15 s = hit something), stuck time (full throttle, < 2 mph), the surface under the car,
the clearance above the car (trace up to the L structure), and the chase camera's height and distance to the car (does a
girder squeeze the camera?). Optional HighResShots at given waypoints.
Runs come from Saved/Rail/drive_runs.json (written by Scripts/rail/l_drive_runs.py): plan metres (x east, y north),
waypoints [x, y(, target m/s)].
SkysterCar keeps its own physics position, so Python can't teleport it: start PIE with the tour's start transform
(EditorAppToolset StartPIE, startTransform = the run's "start"), then run with spawned=1 (no reset, no teleport).
Run in the editor:  py Scripts/rail/l_drive_ue.py tag=wabash runs=tour_wabash spawned=1 [shots=1]
"""
import builtins, json, math, os, sys, time, traceback, unreal

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
TAG = KV.get("tag", "drive")
os.makedirs(ROOT + "/Saved/Rail/drive", exist_ok=True)
OUT = f"{ROOT}/Saved/Rail/drive/out_{TAG}.json"
ALL = json.load(open(ROOT + "/Saved/Rail/drive_runs.json"))["runs"]
WANT = [r for r in KV.get("runs", "").split(",") if r]
RUNS = [r for r in ALL if not WANT or r["name"] in WANT]
SHOTS = KV.get("shots", "0") == "1"
SPAWNED = KV.get("spawned", "0") == "1"
SHOT_EVERY = float(KV.get("shot_every", "0"))
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
if not ues.get_game_world():
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()
ZERO = {"test_throttle": 0.0, "test_brake": 0.0, "test_steer": 0.0, "test_pitch": 0.0, "test_roll": 0.0,
        "test_jump": False, "test_boost": False, "test_fly": False, "test_slide": False}
st = {"wait": 60, "started": False, "ri": 0, "phase": "settle" if SPAWNED else "reset", "t": 0.0, "res": [], "cur": None, "pk": 0}
_h = None


def wrap(a):
    while a > 180:
        a -= 360
    while a < -180:
        a += 360
    return a


def ue(p, z=0.0):
    return unreal.Vector(p[1] * 100.0, p[0] * 100.0, z)


def trace(gw, a, b, ign):
    r = unreal.SystemLibrary.line_trace_single(gw, a, b, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, ign, unreal.DrawDebugTrace.NONE, True)
    if r is None:
        return None
    t = r.to_tuple()
    if not t[0]:
        return None
    act = t[9]
    return {"z": t[5].z, "actor": act.get_actor_label() if act and hasattr(act, "get_actor_label") else (act.get_name() if act else "")}


def finish_run(p, why):
    cur = st["cur"]
    cur["end"] = why
    cur["secs"] = round(st["t"], 2)
    loc = p.get_actor_location()
    cur["end_at_plan"] = [round(loc.y / 100, 1), round(loc.x / 100, 1)]
    cur["log"] = cur["log"][-400:]
    st["res"].append(cur)
    st["cur"] = None
    st["ri"] += 1
    st["phase"] = "reset"
    st["pk"] = 0


def write(done=False):
    json.dump({"tag": TAG, "done": done, "runs": st["res"], "cur": st["cur"]["name"] if st["cur"] else None}, open(OUT, "w"))


def tick(dt):
    try:
        gw = ues.get_game_world()
        if not gw:
            return
        pc = unreal.GameplayStatics.get_player_controller(gw, 0)
        p = pc.get_controlled_pawn() if pc else None
        if p is None or not hasattr(p, "get_mode"):
            return
        if st["wait"] > 0:
            st["wait"] -= 1
            return
        if not st["started"]:
            p.set_editor_property("test_input", True)
            p.set_editor_property("test_set_level", 6)
            p.set_editor_property("test_full_tank", True)
            if hasattr(unreal, "SkysterTraffic"):
                for a in unreal.GameplayStatics.get_all_actors_of_class(gw, unreal.SkysterTraffic):
                    a.set_ground(False)          # traffic has no collision with the player; keep the test about the L
                    a.set_sky(False)
            st["started"] = True
            return
        if st["ri"] >= len(RUNS):
            for k, v in ZERO.items():
                p.set_editor_property(k, v)
            p.set_editor_property("test_input", False)
            unreal.unregister_slate_post_tick_callback(_h)
            write(True)
            return
        run = RUNS[st["ri"]]
        dtc = min(dt, 0.05)
        if st["phase"] == "reset":
            for k, v in ZERO.items():
                p.set_editor_property(k, v)
            p.reset_to_start()
            st["phase"] = "teleport"
            st["pk"] = 0
            return
        if st["phase"] == "teleport":
            st["pk"] += 1
            if st["pk"] < 3:
                return
            a, b = run["wps"][0], run["wps"][1]
            yaw = math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))     # plan heading -> Unreal yaw (X north, Y east)
            z0 = run.get("z", 0.0) * 100.0 + 120.0
            p.set_actor_location_and_rotation(ue(a, z0), unreal.Rotator(roll=0, pitch=0, yaw=yaw), False, True)
            st["phase"] = "settle"
            st["pk"] = 0
            return
        if st["phase"] == "settle":
            st["pk"] += 1
            p.set_editor_property("test_brake", 1.0)
            if st["pk"] < 25:
                return
            st["phase"] = "drive"
            st["t"] = 0.0
            st["cur"] = {"name": run["name"], "why": run.get("why", ""), "events": [], "log": [], "hits": 0, "stuck": 0.0,
                         "min_clear": None, "min_cam_dz": None, "cam_min_dist": None, "wi": 1, "prev": None, "shots": []}
            return
        cur = st["cur"]
        loc = p.get_actor_location()
        rot = p.get_actor_rotation()
        mph = p.get_speed_mph()
        v = mph / 2.23694
        wps = run["wps"]
        wi = cur["wi"]
        tx, ty = wps[wi][1] * 100.0, wps[wi][0] * 100.0
        wv = wps[wi][2] if len(wps[wi]) > 2 else run.get("v", 18.0)
        d = math.hypot(tx - loc.x, ty - loc.y)
        last = wi == len(wps) - 1
        if d < (4.0 if wv < 10 else run.get("reach", 8.0)) * 100.0:
            if SHOTS and wi in run.get("shot_at", []):
                unreal.SystemLibrary.execute_console_command(gw, "HighResShot 1")
                cur["shots"].append({"wi": wi, "wall": time.time()})
            if last:
                finish_run(p, "arrived")
                write()
                return
            cur["wi"] += 1
        want = math.degrees(math.atan2(ty - loc.y, tx - loc.x))
        err = wrap(want - rot.yaw)
        nxt_slow = wi + 1 < len(wps) and len(wps[wi + 1]) > 2 and wps[wi + 1][2] < 10 and d < 3500
        vt = (wv if not nxt_slow else min(wv, 8.0)) if abs(err) < 20 else min(wv, 7.0)
        thr = max(0.0, min(1.0, (vt - v) * 0.35 + 0.25)) if vt > v else 0.0
        brk = max(0.0, min(1.0, (v - vt) * 0.3)) if v > vt + 2.0 else 0.0
        c = dict(ZERO)
        c.update({"test_throttle": thr, "test_brake": brk, "test_steer": max(-1.0, min(1.0, err / 18.0))})
        for k, val in c.items():
            p.set_editor_property(k, val)
        st["t"] += dtc
        t = st["t"]
        if SHOT_EVERY > 0 and int(t / SHOT_EVERY) != int((t - dtc) / SHOT_EVERY):
            unreal.SystemLibrary.execute_console_command(gw, "HighResShot 1")
            cur["shots"].append({"t": round(t, 2), "wall": time.time(), "plan": [round(p.get_actor_location().y / 100, 1), round(p.get_actor_location().x / 100, 1)]})
        # hits and stuck
        if cur["prev"] is not None:
            pm, pt_ = cur["prev"]
            if pm - mph > 8 and t - pt_ < 0.2:
                cur["hits"] += 1
                g = trace(gw, unreal.Vector(loc.x, loc.y, loc.z + 50), unreal.Vector(loc.x + math.cos(math.radians(rot.yaw)) * 600, loc.y + math.sin(math.radians(rot.yaw)) * 600, loc.z + 50), [p])
                cur["events"].append({"t": round(t, 2), "kind": "hit", "frm": round(pm, 1), "to": round(mph, 1),
                                      "plan": [round(loc.y / 100, 1), round(loc.x / 100, 1)], "ahead": g["actor"] if g else None})
        cur["prev"] = (mph, t)
        if thr > 0.5 and mph < 2.0 and t > 2.0:
            cur["stuck"] += dtc
            if cur["stuck"] > 3.0:
                cur["events"].append({"t": round(t, 2), "kind": "stuck", "plan": [round(loc.y / 100, 1), round(loc.x / 100, 1)]})
                finish_run(p, "stuck")
                write()
                return
        else:
            cur["stuck"] = 0.0
        if t > run.get("secs", 90.0):
            finish_run(p, "timeout")
            write()
            return
        # every 0.25 s: surface, clearance above, camera
        if int(t / 0.25) != int((t - dtc) / 0.25):
            g = trace(gw, unreal.Vector(loc.x, loc.y, loc.z + 100), unreal.Vector(loc.x, loc.y, loc.z - 3000), [p])
            up = trace(gw, unreal.Vector(loc.x, loc.y, loc.z + 60), unreal.Vector(loc.x, loc.y, loc.z + 2000), [p])
            cm = unreal.GameplayStatics.get_player_camera_manager(gw, 0)
            cl = cm.get_camera_location() if cm else None
            row = {"t": round(t, 2), "plan": [round(loc.y / 100, 1), round(loc.x / 100, 1)], "z": round(loc.z), "mph": round(mph, 1),
                   "mode": p.get_mode(), "surf": g["actor"] if g else None}
            if up:
                clear = (up["z"] - loc.z) / 100.0
                row["above"] = up["actor"]
                row["clear_m"] = round(clear, 2)
                if "L_" in up["actor"] and (cur["min_clear"] is None or clear < cur["min_clear"]):
                    cur["min_clear"] = round(clear, 2)
            if cl is not None:
                row["cam_z"] = round(cl.z)
                cd = (cl - loc).length() / 100.0
                row["cam_d"] = round(cd, 2)
                if up and "L_" in up["actor"]:
                    dz = (up["z"] - cl.z) / 100.0
                    if cur["min_cam_dz"] is None or dz < cur["min_cam_dz"]:
                        cur["min_cam_dz"] = round(dz, 2)
                    if cur["cam_min_dist"] is None or cd < cur["cam_min_dist"]:
                        cur["cam_min_dist"] = round(cd, 2)
            cur["log"].append(row)
            if len(cur["log"]) % 20 == 0:
                write()
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        json.dump({"error": traceback.format_exc(), "runs": st["res"]}, open(OUT, "w"))


for _old in getattr(builtins, "_l_drive_ticks", []):
    try:
        unreal.unregister_slate_post_tick_callback(_old)
    except Exception:
        pass
_h = unreal.register_slate_post_tick_callback(tick)
builtins._l_drive_ticks = [_h]
write()
