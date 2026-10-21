"""Drive tests for the elevated expressways (read-only: writes Saved/Expressway/drive/out_<tag>.json and HighResShots).
Runs in PIE through the SkysterCar test hooks (as Saved/Playtest/pt.py and Scripts/rail/l_drive_ue.py): for each run the
car is teleported with test_teleport (it stands on whatever it finds from 2 m above the point downward) and driven through
waypoints at a target speed, steering for them. It logs what a player would notice: speed drops (> 8 mph in 0.2 s = hit
something, with what is ahead), stuck time, the surface under the car (deck, ramp, street), the clearance above the car
and what is above (deck, cap), the chase camera's height and distance, and where the run ended.
Runs (plan metres -> Unreal X = y*100, Y = x*100) are built from Saved/Expressway/expressway_layout.json:
  deck_wb / deck_eb   I-35 end to end on the decks (outer lane of each direction), from one ramp foot to the other
  under_*             the streets under the decks (Guadalupe, Lavaca, Colorado, San Jacinto, Canal, West 14th, the
                      Eisenhower stub under the 15th St cluster), checking nothing blocks the lanes
  trinity             Trinity St across the west ramp: blocked until the street builder cuts it (requested)
Run in the editor (lock held; starts PIE if needed, leaves PIE running: stop it with Saved/Playtest/end_pie_pt.py):
  py Scripts/roads/expressway_drive_ue.py tag=deck runs=deck_wb,deck_eb [shot_every=4]
(20 Oct 2026, agent highway-capitol)
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
os.makedirs(ROOT + "/Saved/Expressway/drive", exist_ok=True)
OUT = f"{ROOT}/Saved/Expressway/drive/out_{TAG}.json"
LAY = json.load(open(ROOT + "/Saved/Expressway/expressway_layout.json"))
SHOT_EVERY = float(KV.get("shot_every", "0"))
VMAX = float(KV.get("v", "24"))


def build_runs():
    runs = []
    r = LAY["roads"].get("i35")
    if r:
        st = LAY["styles"][r["style"]]
        c = r["centre"]
        W = st["deck_w"]; curb = st["rail_w"] + st["fascia"]
        lane_out = W / 2 - curb - st["shoulder_out"] - st["lane_w"] / 2       # outer lane centre from the deck centre
        def pt(s, lat):
            i = min(range(len(c) - 1), key=lambda k: abs(c[k][3] - s))
            a, b = c[i], c[min(i + 1, len(c) - 1)]
            tx, ty = b[0] - a[0], b[1] - a[1]
            L = math.hypot(tx, ty) or 1.0
            nx, ny = -ty / L, tx / L
            return [round(a[0] + nx * lat, 2), round(a[1] + ny * lat, 2), round(a[2], 2)]
        L = r["len"]
        dR, dL = min(st["decks"]), max(st["decks"])          # right deck (north here) carries +s, left deck -s
        wb = [pt(s, dR - lane_out) for s in [6.0] + [x * 20.0 for x in range(1, int((L - 6) / 20))] + [L - 6.0]]
        eb = [pt(s, dL + lane_out) for s in [L - 6.0] + [L - x * 20.0 for x in range(1, int((L - 6) / 20))] + [6.0]]
        runs.append({"name": "deck_wb", "why": "I-35 westbound on the north deck, east ramp foot to the west ramp foot", "wps": wb, "v": VMAX, "secs": 120})
        runs.append({"name": "deck_eb", "why": "I-35 eastbound on the south deck, west ramp foot to the east ramp foot", "wps": eb, "v": VMAX, "secs": 120})
    U = lambda pts: [[x, y, 0.0] for x, y in pts]
    runs += [
        {"name": "under_guadalupe", "why": "Guadalupe St northbound under the decks", "wps": U([(-1119.3, -1385), (-1119, -1330), (-1118, -1300), (-1115.5, -1235)]), "v": 15, "secs": 40},
        {"name": "under_lavaca", "why": "Lavaca St southbound under the decks", "wps": U([(-1223.5, -1215), (-1226.5, -1290), (-1228.5, -1330), (-1229.5, -1385)]), "v": 15, "secs": 40},
        {"name": "under_colorado", "why": "Colorado St under the decks (two-way, northbound lane)", "wps": U([(-1336.5, -1380), (-1335.5, -1320), (-1334.5, -1290), (-1333, -1230)]), "v": 13, "secs": 40},
        {"name": "under_sanjacinto", "why": "San Jacinto Blvd northbound under the decks", "wps": U([(-1716.3, -1392), (-1715.5, -1330), (-1714, -1285), (-1711, -1200)]), "v": 15, "secs": 40},
        {"name": "under_canal", "why": "Canal St northbound under the east end", "wps": U([(-979.5, -1415), (-980.5, -1340), (-980.8, -1300), (-979.5, -1215)]), "v": 15, "secs": 40},
        {"name": "under_14th", "why": "West 14th St westbound beside / under the north deck", "wps": U([(-1100, -1302), (-1160, -1299), (-1226.5, -1297.5), (-1290, -1295), (-1326, -1294)]), "v": 13, "secs": 45},
        {"name": "under_eisenhower", "why": "the Eisenhower stub under the decks at the 15th St cluster", "wps": U([(-984, -1314), (-1030, -1318), (-1058, -1328)]), "v": 13, "secs": 30},
        {"name": "trinity", "why": "Trinity St southbound across the west ramp (blocked until the street builder cuts it)", "wps": U([(-1819, -1215), (-1820.3, -1273), (-1821.5, -1330), (-1822.8, -1380)]), "v": 12, "secs": 30},
    ]
    return runs


ALL = build_runs()
WANT = [r for r in KV.get("runs", "").split(",") if r]
RUNS = [r for r in ALL if not WANT or r["name"] in WANT]
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
if not ues.get_game_world():
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()
ZERO = {"test_throttle": 0.0, "test_brake": 0.0, "test_steer": 0.0, "test_pitch": 0.0, "test_roll": 0.0,
        "test_jump": False, "test_boost": False, "test_fly": False, "test_slide": False}
st = {"wait": 90, "started": False, "ri": 0, "phase": "teleport", "t": 0.0, "res": [], "cur": None, "pk": 0}
_h = None


def wrap(a):
    while a > 180:
        a -= 360
    while a < -180:
        a += 360
    return a


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
    cur["end_at_plan"] = [round(loc.y / 100, 1), round(loc.x / 100, 1), round(loc.z / 100, 2)]
    cur["log"] = cur["log"][-500:]
    st["res"].append(cur)
    st["cur"] = None
    st["ri"] += 1
    st["phase"] = "teleport"
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
                    a.set_ground(False)
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
        if st["phase"] == "teleport":
            for k, v in ZERO.items():
                p.set_editor_property(k, v)
            st["pk"] += 1
            if st["pk"] < 3:
                return
            a, b = run["wps"][0], run["wps"][1]
            yaw = math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))     # plan heading -> Unreal yaw (X north, Y east)
            p.test_teleport(unreal.Vector(a[1] * 100.0, a[0] * 100.0, a[2] * 100.0 + 100.0), yaw)
            st["phase"] = "settle"
            st["pk"] = 0
            return
        if st["phase"] == "settle":
            st["pk"] += 1
            p.set_editor_property("test_brake", 1.0)
            if st["pk"] < 30:
                return
            loc = p.get_actor_location()
            st["phase"] = "drive"
            st["t"] = 0.0
            st["cur"] = {"name": run["name"], "why": run.get("why", ""), "events": [], "log": [], "hits": 0, "stuck": 0.0,
                         "start_at": [round(loc.y / 100, 1), round(loc.x / 100, 1), round(loc.z / 100, 2)],
                         "min_clear": None, "min_cam_dz": None, "wi": 1, "prev": None, "shots": [], "surfaces": {}, "z_max": -1e9}
            return
        cur = st["cur"]
        loc = p.get_actor_location()
        rot = p.get_actor_rotation()
        mph = p.get_speed_mph()
        v = mph / 2.23694
        wps = run["wps"]
        wi = cur["wi"]
        tx, ty = wps[wi][1] * 100.0, wps[wi][0] * 100.0
        d = math.hypot(tx - loc.x, ty - loc.y)
        last = wi == len(wps) - 1
        if d < 700.0 or (last and d < 400.0):
            if last:
                finish_run(p, "arrived")
                write()
                return
            cur["wi"] += 1
        want = math.degrees(math.atan2(ty - loc.y, tx - loc.x))
        err = wrap(want - rot.yaw)
        vt = run.get("v", 18.0) if abs(err) < 20 else min(run.get("v", 18.0), 8.0)
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
            cur["shots"].append({"t": round(t, 2), "wall": time.time(), "plan": [round(loc.y / 100, 1), round(loc.x / 100, 1)]})
        if cur["prev"] is not None:
            pm, pt_ = cur["prev"]
            if pm - mph > 8 and t - pt_ < 0.2:
                cur["hits"] += 1
                g = trace(gw, unreal.Vector(loc.x, loc.y, loc.z + 50), unreal.Vector(loc.x + math.cos(math.radians(rot.yaw)) * 600, loc.y + math.sin(math.radians(rot.yaw)) * 600, loc.z + 50), [p])
                cur["events"].append({"t": round(t, 2), "kind": "hit", "frm": round(pm, 1), "to": round(mph, 1),
                                      "plan": [round(loc.y / 100, 1), round(loc.x / 100, 1), round(loc.z / 100, 2)], "ahead": g["actor"] if g else None})
        cur["prev"] = (mph, t)
        if thr > 0.5 and mph < 2.0 and t > 2.0:
            cur["stuck"] += dtc
            if cur["stuck"] > 3.0:
                g = trace(gw, unreal.Vector(loc.x, loc.y, loc.z + 50), unreal.Vector(loc.x + math.cos(math.radians(rot.yaw)) * 600, loc.y + math.sin(math.radians(rot.yaw)) * 600, loc.z + 50), [p])
                cur["events"].append({"t": round(t, 2), "kind": "stuck", "plan": [round(loc.y / 100, 1), round(loc.x / 100, 1), round(loc.z / 100, 2)],
                                      "ahead": g["actor"] if g else None})
                finish_run(p, "stuck")
                write()
                return
        else:
            cur["stuck"] = 0.0
        if t > run.get("secs", 90.0):
            finish_run(p, "timeout")
            write()
            return
        if int(t / 0.25) != int((t - dtc) / 0.25):
            g = trace(gw, unreal.Vector(loc.x, loc.y, loc.z + 100), unreal.Vector(loc.x, loc.y, loc.z - 3000), [p])
            up = trace(gw, unreal.Vector(loc.x, loc.y, loc.z + 60), unreal.Vector(loc.x, loc.y, loc.z + 2500), [p])
            cm = unreal.GameplayStatics.get_player_camera_manager(gw, 0)
            cl = cm.get_camera_location() if cm else None
            row = {"t": round(t, 2), "plan": [round(loc.y / 100, 1), round(loc.x / 100, 1)], "z": round(loc.z), "mph": round(mph, 1),
                   "mode": p.get_mode(), "surf": g["actor"] if g else None}
            if g:
                cur["surfaces"][g["actor"]] = cur["surfaces"].get(g["actor"], 0) + 1
            cur["z_max"] = max(cur["z_max"], round(loc.z))
            if up:
                clear = (up["z"] - loc.z) / 100.0
                row["above"] = up["actor"]
                row["clear_m"] = round(clear, 2)
                if "XW_" in up["actor"] and (cur["min_clear"] is None or clear < cur["min_clear"]):
                    cur["min_clear"] = round(clear, 2)
            if cl is not None:
                row["cam_z"] = round(cl.z)
                row["cam_d"] = round((cl - loc).length() / 100.0, 2)
                if up and "XW_" in up["actor"]:
                    dz = (up["z"] - cl.z) / 100.0
                    if cur["min_cam_dz"] is None or dz < cur["min_cam_dz"]:
                        cur["min_cam_dz"] = round(dz, 2)
            cur["log"].append(row)
            if len(cur["log"]) % 20 == 0:
                write()
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        json.dump({"error": traceback.format_exc(), "runs": st["res"]}, open(OUT, "w"))


for _old in getattr(builtins, "_xw_drive_ticks", []):
    try:
        unreal.unregister_slate_post_tick_callback(_old)
    except Exception:
        pass
_h = unreal.register_slate_post_tick_callback(tick)
builtins._xw_drive_ticks = [_h]
write()
