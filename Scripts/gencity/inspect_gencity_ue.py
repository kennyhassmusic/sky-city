"""Inspection drives for the review agents (lane P, 2026-10-28): the Skyster driven headless along the planned routes
(Saved/GenCity/inspect_<region>.json, inspect_plan_gencity.py) at about 35 mph (15 near turns), in PIE, with
captures along the way; then quit. Full editor on the level (it ticks across frames: -ExecCmds):
  "$UE" "$PWD/SkyCity.uproject" /Game/Maps/GenCity_Seed7 -nosplash ... \
    -ExecCmds="py <space-free path>/Scripts/gencity/inspect_gencity_ue.py region=seed7_city tag=v8"
Captures (1280x720, motion blur and TAA history off): the chase camera every 40 m, a driver-eye forward frame every
80 m (a camera 1.2 m up, just ahead of the windscreen so the hood stays out), and at every 3rd intersection a pedestrian-eye set (1.7 m)
looking down each leg from the corner. While a capture runs the game is frozen (global time dilation), so the car
doesn't move between the frames and the physics checks pause.
Physics checks while driving (game time): stuck (< 2 mph for 3 s with throttle on; then the car is put 30 m on),
below ground, sudden stop (-12 mph within 0.4 s), airborne (not DRIVE/SLIDE for > 0.6 s), in the water, off the
route (> 12 m; put back). Each with the car's location, the actors within 8 m and what a trace straight ahead hits.
A put-back (teleport_to) holds the car still in game time: throttle and steer zeroed, full brake and the stop button,
velocity zeroed; pure pursuit steers for STEER_IN_S before the brake comes off (inspect_plan_gencity.teleport_reset /
hold_phase). The chase camera is the car's fixed test camera, kept under the signal heads (<= 4.5 m) and tucked in low
near a signal mast (inspect_plan_gencity.chase_cam, routes[].masts_ue). Pedestrian cameras stand where the plan puts
them (caps[].cams: on the sidewalk corner, each leg's half width + 2 m out).
Writes Saved/GenCity/inspect_<tag>.json (frames: route, kind, png, camera UE location and yaw, car, edge, ...).
inspect_pack.py turns that into AssetBuilds/inspect_v8/<route>/NNNN_<kind>.jpg + manifest.json.
"""
import builtins
import importlib
import json
import math
import os
import sys
import time
import traceback

import unreal

ROOT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")
_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.path.join(ROOT, "Scripts", "gencity")
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import inspect_plan_gencity as IP  # noqa: E402  (plain-Python helpers: hold logic, chase camera)
importlib.reload(IP)               # the editor's interpreter persists between runs
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
REGION = KV.get("region", "seed7_city")
TAG = KV.get("tag", "inspect")
SETTLE = float(KV.get("settle", "60"))
RES = KV.get("res", "1280x720")
MPH = float(KV.get("mph", "35"))
SLOW_MPH = float(KV.get("slow_mph", "15"))
ONLY = [r for r in KV.get("routes", "").split("+") if r]
PLAN = json.load(open(os.path.join(ROOT, "Saved", "GenCity", "inspect_%s.json" % REGION)))
OUT = os.path.join(ROOT, "Saved", "GenCity", "inspect_%s.json" % TAG)
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "MacEditor")
CVARS = ("r.MotionBlurQuality 0", "r.DefaultFeature.MotionBlur 0", "r.AntiAliasingMethod 1")
ZERO = {"test_throttle": 0.0, "test_brake": 0.0, "test_steer": 0.0, "test_pitch": 0.0, "test_roll": 0.0,
        "test_stop": 0.0, "test_jump": False, "test_boost": False, "test_fly": False, "test_slide": False}
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
res = {"tag": TAG, "region": REGION, "done": False, "frames": [], "anomalies": [], "routes": {}, "log": []}
S = {"t0": time.time(), "phase": "settle"}


def write():
    res["secs"] = round(time.time() - S["t0"], 1)
    with open(OUT, "w") as h:
        json.dump(res, h, indent=1, default=str)


def gw():
    return ues.get_game_world()


def cmd(c):
    unreal.SystemLibrary.execute_console_command(gw(), c)


def files():
    return set(os.listdir(SHOTS)) if os.path.isdir(SHOTS) else set()


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def gtime():
    return unreal.GameplayStatics.get_time_seconds(gw())


def label(a):
    if a is None:
        return ""
    try:
        return a.get_actor_label()
    except Exception:
        return a.get_name()


def trace(a, b, ignore):
    r = unreal.SystemLibrary.line_trace_single(gw(), a, b, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, ignore,
                                               unreal.DrawDebugTrace.NONE, True)
    t = r.to_tuple() if r is not None else None
    if not t or not t[0]:
        return None
    comp = t[10] if len(t) > 10 else None
    return {"z": round(t[5].z, 1), "at": [round(t[4].x), round(t[4].y), round(t[4].z)], "actor": label(t[9])[:48],
            "comp": (comp.get_name() if comp else "")[:48], "item": t[11] if len(t) > 11 else None}


def near_actors(loc, radius=800.0):
    try:
        r = unreal.SystemLibrary.sphere_overlap_actors(gw(), loc, radius,
                                                       [unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY1,
                                                        unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY2], None, [S["p"]])
        acts = r[1] if isinstance(r, tuple) else r
        out = sorted({label(a)[:48] for a in (acts or [])})
        return out[:10]
    except Exception as exc:  # noqa: BLE001
        return ["(overlap failed: %s)" % exc]


def anomaly(kind, extra=None):
    p = S["p"]
    loc = p.get_actor_location()
    yaw = p.get_actor_rotation().yaw
    r = math.radians(yaw)
    ahead = trace(unreal.Vector(loc.x, loc.y, loc.z + 80), unreal.Vector(loc.x + math.cos(r) * 700,
                                                                          loc.y + math.sin(r) * 700, loc.z + 80), [p])
    R = S["route"]
    e = R["edges"][R["path"][S["pi"]][3]]
    a = {"route": R["name"], "kind": kind, "t_game": round(gtime() - S["rt0"], 2), "dist_m": R["path"][S["pi"]][2],
         "car_ue": [round(loc.x), round(loc.y), round(loc.z)], "yaw": round(yaw, 1), "mph": round(p.get_speed_mph(), 1),
         "mode": p.get_mode(), "edge": e["id"], "class": e["class"], "ground": trace(
             unreal.Vector(loc.x, loc.y, loc.z + 50), unreal.Vector(loc.x, loc.y, loc.z - 3000), [p]),
         "ahead_hit": ahead, "near_actors": near_actors(loc)}
    a.update(extra or {})
    res["anomalies"].append(a)
    unreal.log("INSPECT anomaly %s" % json.dumps(a, default=str)[:400])


def teleport_to(pi):
    """Put the car on the path at point pi and hold it still (game time): no stale throttle/steer, full brake and stop,
    velocity zeroed; drive() keeps the hold on until S["hold_until"], steers before it lets the brake off."""
    R = S["route"]
    pts = R["path"]
    pi = min(pi, len(pts) - 2)
    a, b = pts[pi], pts[min(pi + 2, len(pts) - 1)]
    yaw = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    p = S["p"]
    IP.hold_controls(p)                    # before the move, so nothing is applied on the way
    p.test_teleport(unreal.Vector(a[0], a[1], 150.0), yaw)
    S["hold_until"] = IP.teleport_reset(p, gtime(), unreal.Vector(0.0, 0.0, 0.0))
    S["quiet_until"] = S["hold_until"] + IP.STEER_IN_S + 1.0
    S["pi"] = pi
    S["slow_t"] = None
    S["air_t"] = None
    S["hist"] = []


def set_chase_cam(loc, yaw):
    """The car's fixed chase camera for where it is now (it eases there at the car's camera rate, so set it every
    tick while driving: the frozen capture frame shows what the camera had settled to)."""
    R = S["route"]
    dist, elev, h, tucked = IP.chase_cam([loc.x, loc.y], yaw, R.get("masts_ue") or [],
                                         float(KV.get("chase_dist", IP.CHASE_DIST_M)),
                                         float(KV.get("chase_elev", IP.CHASE_ELEV_DEG)))
    p = S["p"]
    if S.get("chase") is None or abs(S["chase"]["dist_m"] - dist) > 0.01 or abs(S["chase"]["elev"] - elev) > 0.01:
        p.set_editor_property("test_cam_dist", dist)
        p.set_editor_property("test_cam_yaw", 0.0)
        p.set_editor_property("test_cam_elev", elev)
    S["chase"] = {"dist_m": round(dist, 2), "elev": round(elev, 2), "height_m": round(h, 2), "tucked": tucked}


# --- route driving -------------------------------------------------------------------------------------

def start_route(i):
    R = S["routes"][i]
    S["ri"], S["route"], S["pi"], S["ci"] = i, R, 0, 0
    p = S["p"]
    for k, v in ZERO.items():
        p.set_editor_property(k, v)
    S["chase"] = None
    S["pc"].set_view_target_with_blend(p, 0.0)
    p.test_teleport(unreal.Vector(R["start_ue"][0], R["start_ue"][1], 150.0), R["start_yaw"])
    set_chase_cam(p.get_actor_location(), R["start_yaw"])
    S["rt0"] = None
    S["hold_until"] = IP.teleport_reset(p, gtime(), unreal.Vector(0.0, 0.0, 0.0), 2.5)
    S["hist"] = []
    S["air_t"] = None
    S["slow_t"] = None
    S["last_anom"] = {}
    res["routes"][R["name"]] = {"length_m": R["length_m"], "t_start": round(time.time() - S["t0"], 1)}
    S["phase"] = "drive"
    unreal.log("INSPECT route %s start" % R["name"])


def drive(now):
    p = S["p"]
    R = S["route"]
    pts = R["path"]
    ph = IP.hold_phase(gtime(), S["hold_until"])
    if ph == "hold":
        IP.hold_controls(p)                # every tick: nothing stale gets through while the car is held
        return
    if S["rt0"] is None:
        S["rt0"] = gtime()
    loc = p.get_actor_location()
    rot = p.get_actor_rotation()
    set_chase_cam(loc, rot.yaw)
    # progress: the nearest path point in a window ahead
    best, bi = 1e18, S["pi"]
    for j in range(S["pi"], min(len(pts), S["pi"] + 30)):
        d = (pts[j][0] - loc.x) ** 2 + (pts[j][1] - loc.y) ** 2
        if d < best:
            best, bi = d, j
    S["pi"] = bi
    off_m = math.sqrt(best) / 100.0
    dist = pts[bi][2]
    if bi >= len(pts) - 2:
        finish_route()
        return
    # captures due at this distance: freeze and shoot
    caps = R["caps"]
    if S["ci"] < len(caps) and dist >= caps[S["ci"]]["d"]:
        due = []
        while S["ci"] < len(caps) and dist >= caps[S["ci"]]["d"]:
            due.append(caps[S["ci"]])
            S["ci"] += 1
        begin_capture(due)
        return
    # steering: pure pursuit on a point ~10 m (or 0.8 s) ahead
    mph = p.get_speed_mph()
    look = max(10.0, mph * 0.447 * 0.8)
    tj = bi
    while tj < len(pts) - 1 and pts[tj][2] - dist < look:
        tj += 1
    want = math.degrees(math.atan2(pts[tj][1] - loc.y, pts[tj][0] - loc.x))
    err = wrap(want - rot.yaw)
    p.set_editor_property("test_steer", max(-1.0, min(1.0, err / 25.0)))
    if ph == "steer":                      # pure pursuit is steering; the brake comes off next
        p.set_editor_property("test_throttle", 0.0)
        p.set_editor_property("test_brake", 1.0)
        p.set_editor_property("test_stop", 1.0)
        return
    p.set_editor_property("test_stop", 0.0)
    target = SLOW_MPH if any(a <= dist <= b for a, b in R["slow"]) else MPH
    if abs(err) > 35:
        target = min(target, SLOW_MPH)
    if mph < target - 2:
        p.set_editor_property("test_throttle", max(0.25, min(1.0, (target - mph) / 12.0)))
        p.set_editor_property("test_brake", 0.0)
    elif mph > target + 3:
        p.set_editor_property("test_throttle", 0.0)
        p.set_editor_property("test_brake", min(1.0, (mph - target) / 15.0))
    else:
        p.set_editor_property("test_throttle", 0.3)
        p.set_editor_property("test_brake", 0.0)
    checks(now, loc, mph, off_m)


def rate_ok(kind, gt, gap=3.0):
    last = S["last_anom"].get(kind, -99.0)
    if gt - last < gap:
        return False
    S["last_anom"][kind] = gt
    return True


def checks(now, loc, mph, off_m):
    p = S["p"]
    gt = gtime() - S["rt0"]
    if gt < 1.5 or gtime() < S.get("quiet_until", 0.0):
        S["hist"] = [(gt, mph)]
        return
    S["hist"].append((gt, mph))
    S["hist"] = [h for h in S["hist"] if gt - h[0] <= 0.5]
    old = [h for h in S["hist"] if gt - h[0] >= 0.35]
    if old and old[0][1] - mph > 12.0 and rate_ok("sudden_stop", gt):
        anomaly("sudden_stop", {"mph_before": round(old[0][1], 1)})
    mode = p.get_mode()
    if mode not in ("DRIVE", "SLIDE"):
        S["air_t"] = S["air_t"] if S["air_t"] is not None else gt
        if gt - S["air_t"] > 0.6 and rate_ok("airborne", gt):
            anomaly("airborne", {"for_s": round(gt - S["air_t"], 2)})
    else:
        S["air_t"] = None
    g = trace(unreal.Vector(loc.x, loc.y, loc.z + 50), unreal.Vector(loc.x, loc.y, loc.z - 3000), [p])
    if g is None:
        if rate_ok("no_ground", gt):
            anomaly("no_ground")
    elif loc.z < g["z"] - 15 and rate_ok("below_ground", gt):
        anomaly("below_ground", {"depth_cm": round(g["z"] - loc.z)})
    if p.is_in_water() and rate_ok("in_water", gt, 10.0):
        anomaly("in_water")
    if mph < 2.0 and p.get_editor_property("test_throttle") > 0.2:
        S["slow_t"] = S["slow_t"] if S["slow_t"] is not None else gt
        if gt - S["slow_t"] > 3.0:
            anomaly("stuck", {"for_s": round(gt - S["slow_t"], 1), "recovered": "teleported 30 m on"})
            teleport_to(S["pi"] + 8)       # holds the car (game time) with the controls zeroed and the brake on
            return
    else:
        S["slow_t"] = None
    if off_m > 12.0 and rate_ok("off_route", gt, 5.0):
        anomaly("off_route", {"off_m": round(off_m, 1), "recovered": "put back on the route"})
        teleport_to(S["pi"] + 2)
        return
    if gt > S["route"]["length_m"] / 5.0 + 40.0:
        anomaly("route_timeout")
        finish_route()


def finish_route():
    R = S["route"]
    r = res["routes"][R["name"]]
    r["t_game"] = round(gtime() - (S["rt0"] or gtime()), 1)
    r["dist_reached_m"] = R["path"][S["pi"]][2]
    r["frames"] = sum(1 for f in res["frames"] if f["route"] == R["name"])
    write()
    if S["ri"] + 1 < len(S["routes"]):
        start_route(S["ri"] + 1)
    else:
        finish()


# --- captures ------------------------------------------------------------------------------------------

def begin_capture(due):
    p = S["p"]
    unreal.GameplayStatics.set_global_time_dilation(gw(), 0.0001)
    R = S["route"]
    loc = p.get_actor_location()
    yaw = p.get_actor_rotation().yaw
    items = []
    for c in due:
        if c["kind"] == "chase":
            items.append({"kind": "chase", "view": "car", "chase_cam": dict(S.get("chase") or {})})
        elif c["kind"] == "fwd":
            r = math.radians(yaw)
            at = unreal.Vector(loc.x + math.cos(r) * 140.0, loc.y + math.sin(r) * 140.0, loc.z + 120.0)
            items.append({"kind": "fwd", "view": "cam", "loc": at, "rot": unreal.Rotator(0.0, -2.0, yaw)})
        elif c["kind"] == "ped" and c.get("cams"):
            # the plan's sidewalk corners: each leg's half width + 2 m behind the curb, clear of every leg
            for k, pc in enumerate(c["cams"]):
                x, y = pc["at_ue"]
                g = trace(unreal.Vector(x, y, loc.z + 500), unreal.Vector(x, y, loc.z - 1000), [p])
                gz = g["z"] if g else loc.z
                at = unreal.Vector(x, y, gz + IP.PED_EYE_M * 100.0)
                items.append({"kind": "ped%d" % k, "view": "cam", "loc": at, "rot": unreal.Rotator(0.0, -1.0, pc["yaw"]),
                              "node": c["node"], "leg": pc["leg"]})
        elif c["kind"] == "ped":           # an older plan without caps[].cams
            cx, cy = c["at_ue"]
            g = trace(unreal.Vector(cx, cy, loc.z + 500), unreal.Vector(cx, cy, loc.z - 1000), [p])
            gz = g["z"] if g else loc.z
            legs = c["legs_plan_deg"]
            for k, lp in enumerate(legs):
                # plan heading (x east, y north) -> UE yaw (X north, Y east); stand on the corner to the right
                uyaw = 90.0 - lp
                r = math.radians(uyaw)
                rx, ry = math.cos(r + math.pi / 2), math.sin(r + math.pi / 2)
                at = unreal.Vector(cx - math.cos(r) * 700 + rx * 800, cy - math.sin(r) * 700 + ry * 800, gz + 170.0)
                items.append({"kind": "ped%d" % k, "view": "cam", "loc": at, "rot": unreal.Rotator(0.0, -1.0, uyaw),
                              "node": c["node"]})
    e = R["edges"][R["path"][S["pi"]][3]]
    for it in items:
        it.update({"route": R["name"], "dist_m": R["path"][S["pi"]][2], "edge": e["id"], "class": e["class"],
                   "district": e["district"], "zones": e["zones"], "parcel_types": e["parcel_types"],
                   "bridge": e["bridge"], "car_ue": [round(loc.x), round(loc.y), round(loc.z)], "car_yaw": round(yaw, 1),
                   "mph": round(p.get_speed_mph(), 1)})
    S["cap"] = items
    S["phase"] = "cap_set"


def capture(now):
    if not S["cap"]:
        S["pc"].set_view_target_with_blend(S["p"], 0.0)
        unreal.GameplayStatics.set_global_time_dilation(gw(), 1.0)
        S["phase"] = "drive"
        S["hist"] = []                     # the frozen frames read as a speed drop: start the checks afresh
        S["quiet_until"] = max(S.get("quiet_until", 0.0), gtime() + 0.6)
        write()
        return
    it = S["cap"][0]
    if S["phase"] == "cap_set":
        if it["view"] == "car":
            S["pc"].set_view_target_with_blend(S["p"], 0.0)
            cam = S["pc"].player_camera_manager
            loc, rot = cam.get_camera_location(), cam.get_camera_rotation()
            it["cam_ue"] = [round(loc.x), round(loc.y), round(loc.z)]
            it["cam_yaw"] = round(rot.yaw, 1)
        else:
            S["cam"].set_actor_location_and_rotation(it["loc"], it["rot"], False, True)
            S["pc"].set_view_target_with_blend(S["cam"], 0.0)
            it["cam_ue"] = [round(it["loc"].x), round(it["loc"].y), round(it["loc"].z)]
            it["cam_yaw"] = round(it["rot"].yaw, 1)
        S["phase"] = "cap_wait"
        S["until"] = now + 0.35
        return
    if S["phase"] == "cap_wait":
        if now < S["until"]:
            return
        S["before"] = files()
        cmd("HighResShot %s" % RES)
        S["phase"] = "cap_file"
        S["until"] = now + 12.0
        return
    if S["phase"] == "cap_file":
        new = sorted(files() - S["before"])
        if not new and now < S["until"]:
            return
        for k in ("loc", "rot", "view"):
            it.pop(k, None)
        it["png"] = os.path.join(SHOTS, new[-1]) if new else None
        res["frames"].append(it)
        S["cap"].pop(0)
        S["phase"] = "cap_set"


def finish():
    unreal.unregister_slate_post_tick_callback(builtins._lanep_inspect)
    res["done"] = True
    write()
    if gw():
        unreal.GameplayStatics.set_global_time_dilation(gw(), 1.0)
        les.editor_request_end_play()
    S["quit_at"] = time.time() + 3.0

    def later(_dt):
        if time.time() > S["quit_at"]:
            unreal.SystemLibrary.quit_editor()
    builtins._lanep_quit = unreal.register_slate_post_tick_callback(later)


def tick(dt):
    try:
        now = time.time()
        ph = S["phase"]
        if ph == "settle":
            if now - S["t0"] < SETTLE:
                return
            cam = eas.spawn_actor_from_class(unreal.CameraActor, unreal.Vector(0, 0, 5000), unreal.Rotator(0, 0, 0))
            cam.set_editor_property("tags", [unreal.Name("lanep_inspect_cam")])
            cam.camera_component.set_editor_property("field_of_view", 80.0)
            cam.camera_component.set_editor_property("constrain_aspect_ratio", False)
            les.editor_request_begin_play()
            S["phase"], S["until"] = "pie", now + 90.0
            return
        if ph == "pie":
            w = gw()
            pc = unreal.GameplayStatics.get_player_controller(w, 0) if w else None
            p = pc.get_controlled_pawn() if pc else None
            if p is None:
                if now > S["until"]:
                    res["error"] = "no pawn in PIE"
                    finish()
                return
            cams = list(unreal.GameplayStatics.get_all_actors_with_tag(w, unreal.Name("lanep_inspect_cam")))
            S["pc"], S["p"], S["cam"] = pc, p, cams[0]
            p.set_editor_property("test_input", True)
            p.set_editor_property("test_full_tank", True)
            for c in CVARS:
                cmd(c)
            cmd("DisableAllScreenMessages")
            cmd("ShowHUD")                     # the car's HUD off: the frames are of the city
            S["routes"] = [r for r in PLAN["routes"] if not ONLY or r["name"] in ONLY]
            start_route(0)
            return
        if ph == "drive":
            drive(now)
            return
        if ph.startswith("cap"):
            capture(now)
            return
    except Exception:
        res["error"] = traceback.format_exc()
        unreal.log_error("INSPECT error " + res["error"])
        try:
            finish()
        except Exception:
            write()


for _old in getattr(builtins, "_lanep_inspect_all", []):
    try:
        unreal.unregister_slate_post_tick_callback(_old)
    except Exception:
        pass
builtins._lanep_inspect = unreal.register_slate_post_tick_callback(tick)
builtins._lanep_inspect_all = [builtins._lanep_inspect]
write()
