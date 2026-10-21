"""PIE drive tests across McGregor's road / lot / pad edges (mcgregor-edges, 20 Oct 2026). Read-only for the level:
it only drives the Skyster car through its test hooks (SkysterCar.h: test_teleport, test_input, test_throttle...).

Each case puts the car `run` metres before a crossing point on a straight line along `hdg`, drives it there at `mph`
(throttle, plus boost when far below the target) and on 40 m past it, logging every frame. Around the crossing (from
8 m before to 25 m after) it reports what a player would feel:
  air    the car left the ground (mode AIR / FLIP / TUMBLE): a hop or a launch -- with the air time and peak height
  hit    the speed fell by more than 8 mph within 0.3 s, or the health dropped: it ran into something
  pop    the biggest frame-to-frame jump of the car's height while on the ground (a step it was lifted over)
Cases: cases="name:x,y,hdg,mph,run[,after];..." in PLAN metres (x east, y north), hdg = compass heading of travel;
after (default 25 m) stretches the verdict window past the point (e.g. 300 for a run along a road).
Run in the editor (McGregor or McGregorNight loaded, nobody else in PIE):
  py Scripts/mcgregor/edges_drive_ue.py tag=before cases="..." [end=1] [shots=1]
Writes Saved/McGregor/edges/drive_<tag>.json (per case: verdict, crossing speed, events, the frame log near the edge);
shots=1 takes a HighResShot (chase camera) as each car crosses its edge.
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
END = KV.get("end", "1") == "1"
SHOTS = KV.get("shots", "0") == "1"
OUT = ROOT + f"/Saved/McGregor/edges/drive_{TAG}.json"
os.makedirs(ROOT + "/Saved/McGregor/edges", exist_ok=True)
CASES = []
for c in KV.get("cases", "").split(";"):
    if ":" in c:
        name, v = c.split(":", 1)
        vals = [float(t) for t in v.split(",")]
        x, y, hdg, mph, run = vals[:5]
        CASES.append({"name": name, "x": x, "y": y, "hdg": hdg, "mph": mph, "run": run, "after": vals[5] if len(vals) > 5 else 25.0})
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not ues.get_game_world():
    les.editor_request_begin_play()
st = {"ci": -1, "phase": "wait", "k": 0, "t": 0.0, "res": [], "log": [], "wall0": time.time()}
ZERO = {"test_throttle": 0.0, "test_brake": 0.0, "test_steer": 0.0, "test_pitch": 0.0, "test_roll": 0.0, "test_jump": False, "test_boost": False,
        "test_fly": False, "test_slide": False}


def save(done=False):
    json.dump({"tag": TAG, "done": done, "cases": CASES, "results": st["res"], "secs": round(time.time() - st["wall0"], 1)}, open(OUT, "w"), indent=1)


def ground(gw, x, y, zc, p):
    h = unreal.SystemLibrary.line_trace_single(gw, unreal.Vector(y * 100, x * 100, zc + 3000), unreal.Vector(y * 100, x * 100, zc - 6000),
                                               unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [p] if p else [], unreal.DrawDebugTrace.NONE, True)
    if not h:
        return None
    t = h.to_tuple()
    return (t[4].z, t[9].get_actor_label() if t[9] else "") if t[0] else None


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def verdict(c, rows):
    win = [r for r in rows if -8.0 <= r["s"] <= c.get("after", 25.0)]
    if not win:
        return {"verdict": "never reached the edge", "max_s": max((r["s"] for r in rows), default=None)}
    air = [r for r in win if r["mode"] in ("AIR", "FLIP", "TUMBLE", "LANDING")]
    hit = False
    for i, r in enumerate(win):
        for q in win[i + 1:]:
            if q["t"] - r["t"] > 0.3:
                break
            if r["mph"] - q["mph"] > 8.0:
                hit = True
    hp = win[0]["hp"] - min(r["hp"] for r in win)
    pops = [abs(b["z"] - a["z"]) for a, b in zip(win, win[1:]) if a["mode"] in ("DRIVE", "SLIDE") and b["mode"] in ("DRIVE", "SLIDE")]
    at = min(win, key=lambda r: abs(r["s"]))
    v = {"cross_mph": at["mph"], "air_frames": len(air), "air_s": round(sum(r["dt"] for r in air), 2),
         "air_peak_cm": round(max((r["z"] - r["gz"] for r in air if r["gz"] is not None), default=0.0)), "hit": hit or hp > 0.5,
         "health_drop": round(hp, 1), "max_pop_cm": round(max(pops, default=0.0), 1),
         "surfaces": sorted({r["gact"] for r in win if r["gact"]})}
    v["verdict"] = "HIT" if v["hit"] else "HOP" if air else "clean"
    return v


def tick(dt):
    try:
        gw = ues.get_game_world()
        if not gw:
            return
        pc = unreal.GameplayStatics.get_player_controller(gw, 0)
        p = pc.get_controlled_pawn() if pc else None
        if p is None or not hasattr(p, "test_teleport"):
            return
        if st["phase"] == "wait":
            st["k"] += 1
            if st["k"] < 60:
                return
            p.set_editor_property("test_input", True)
            p.set_editor_property("test_set_level", 6)
            p.set_editor_property("test_full_tank", True)
            st["phase"] = "next"
            return
        if st["phase"] == "next":
            st["ci"] += 1
            if st["ci"] >= len(CASES):
                for k, v in ZERO.items():
                    p.set_editor_property(k, v)
                p.set_editor_property("test_input", False)
                unreal.unregister_slate_post_tick_callback(_h)
                save(True)
                if END:
                    les.editor_request_end_play()
                return
            c = CASES[st["ci"]]
            hr = math.radians(c["hdg"])
            c["dir"] = (math.sin(hr), math.cos(hr))
            sx, sy = c["x"] - c["dir"][0] * c["run"], c["y"] - c["dir"][1] * c["run"]
            g = ground(gw, sx, sy, 2000.0, p)
            z = (g[0] if g else 0.0) + 100.0
            # Unreal yaw: from +X (north) toward +Y (east) = the compass heading
            p.test_teleport(unreal.Vector(sy * 100.0, sx * 100.0, z), c["hdg"])
            for k, v in ZERO.items():
                p.set_editor_property(k, v)
            st.update(phase="settle", k=0, t=0.0, log=[], shot=False)
            return
        c = CASES[st["ci"]]
        if st["phase"] == "settle":
            st["k"] += 1
            if st["k"] > 20:
                st["phase"] = "drive"
            return
        st["t"] += dt
        loc = p.get_actor_location()
        x, y = loc.y / 100.0, loc.x / 100.0
        s = (x - c["x"]) * c["dir"][0] + (y - c["y"]) * c["dir"][1]
        lat = -(x - c["x"]) * c["dir"][1] + (y - c["y"]) * c["dir"][0]
        mph = p.get_speed_mph()
        yaw = p.get_actor_rotation().yaw
        # aim at a point 60 m further down the line (pulls the car back onto it)
        tx, ty = c["x"] + c["dir"][0] * (s + 60.0), c["y"] + c["dir"][1] * (s + 60.0)
        want = math.degrees(math.atan2(tx - x, ty - y))
        err = wrap(want - yaw)
        ctl = dict(ZERO)
        ctl["test_steer"] = max(-1.0, min(1.0, err / 15.0))
        ctl["test_throttle"] = 1.0 if mph < c["mph"] else 0.0
        ctl["test_boost"] = mph < c["mph"] - 12.0 and c["mph"] > 70.0
        ctl["test_brake"] = 0.3 if mph > c["mph"] + 6.0 else 0.0
        for k, v in ctl.items():
            p.set_editor_property(k, v)
        mode = p.get_mode()
        g = ground(gw, x, y, loc.z, p) if -12.0 <= s <= c["after"] + 5.0 else None
        st["log"].append({"t": round(st["t"], 3), "dt": round(dt, 4), "s": round(s, 2), "lat": round(lat, 2), "z": round(loc.z, 1),
                          "gz": round(g[0], 1) if g else None, "gact": g[1] if g else "", "mph": round(mph, 1), "mode": mode,
                          "pitch": round(p.get_actor_rotation().pitch, 1), "hp": round(p.get_health(), 1)})
        if SHOTS and not st["shot"] and s >= -1.0:
            unreal.SystemLibrary.execute_console_command(gw, "HighResShot 1")
            st["shot"] = True
        if s > c["after"] + 15.0 or st["t"] > 40.0 or (st["t"] > 6.0 and mph < 1.0):
            rows = st["log"]
            v = verdict(c, rows)
            v.update(name=c["name"], target_mph=c["mph"], hdg=c["hdg"], lateral_at_edge=min(rows, key=lambda r: abs(r["s"]))["lat"] if rows else None)
            v["near"] = [r for r in rows if -10.0 <= r["s"] <= c["after"] + 3.0]
            st["res"].append(v)
            save(False)
            st["phase"] = "next"
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        st["res"].append({"error": traceback.format_exc()})
        save(True)


for _old in getattr(builtins, "_edges_drive_h", []):
    try:
        unreal.unregister_slate_post_tick_callback(_old)
    except Exception:
        pass
save(False)
_h = unreal.register_slate_post_tick_callback(tick)
builtins._edges_drive_h = [_h]
