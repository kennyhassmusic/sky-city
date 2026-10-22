"""Course track tests (geometry agent): build courses with ASkyCourseTrack in PIE, look at them, and drive them.

Run from the editor's console box:   py /abs/path/Scripts/course/track_test.py <scenario> [k=v ...]
Scenarios (results in Saved/Playtest/course_geo/geo_<tag>.json, shots Saved/Playtest/course_geo/geo_<tag>_<what>.png):
  build   build each course in files= (a comma list of course JSON files) with its own track actor, save the bake summary
          (TestBuildJson: errors, warnings, segments with their centre lines every 2 m, gates, splits, routes, grid) and
          take shots from above and from the side of each
  drive   build file= and drive the player's car round it with the car's test hooks: steering toward the centre line
          ahead, a speed plan (curves by radius, loops fast, jumps at the take-off speed their landing needs), boost
          below the plan; logs mode, position, speed, segment and how far off the centre line every 0.2 s and takes
          shots at the loop's top, mid-jump, the corkscrew and the banked curve
  errors  run Scripts/course/courses/bad_cases.json through TestBuildJson: each case's error must contain its expected
          text (JSON paths and all); a case expecting nothing must be valid
  roundtrip (mode=1) each course in files= into the director (TestSetCourseJson = Parse), back out (TestGetCourseJson =
          Write), parsed again and baked: the same pieces and the same length
Options: map=/Game/Maps/McGregor  mode=0 (1: open the map as the Course Builder, ?mode=build, so the build pad is there)
         level=0 (drive at the car's saved level; level=N switches it, and that is SAVED to the player's progress file)  laps=1  secs=90  lap=1 (which lap's route)  tag=  shots=1  size=1920x1080
         speed=1.0 (scale the speed plan)  stay=0 (1: leave PIE running at the end)
"""
import json, math, os, shutil, sys, time, unreal

ROOT = os.environ.get("SKYCITY_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUTDIR = ROOT + "/Saved/Playtest/course_geo"   # my own folder (other course tests clear theirs)
os.makedirs(OUTDIR, exist_ok=True)
A = sys.argv[1:]
SCEN = A[0] if A and "=" not in A[0] else "build"
KV = dict(a.split("=", 1) for a in A if "=" in a)
MAP = KV.get("map", "/Game/Maps/McGregor")
MODE = KV.get("mode", "0") == "1"
FILES = [f for f in KV.get("files", KV.get("file", ROOT + "/Scripts/course/courses/example.json")).split(",") if f]
TAG = KV.get("tag", SCEN)
LEVEL = int(KV.get("level", "0"))   # 0: leave the car's level alone. Setting one SAVES it to the player's progress file!
SECS = float(KV.get("secs", "90"))
LAP = int(KV.get("lap", "1"))
LAPS = int(KV.get("laps", "1"))
SHOTS = KV.get("shots", "1") == "1"
SIZE = KV.get("size", "1920x1080")
SPEED = float(KV.get("speed", "1.0"))
TWIST_V = float(KV.get("twist_v", "40"))
STAY = KV.get("stay", "0") == "1"
G = 25.4
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
TRACK_CLS = unreal.load_class(None, "/Script/SkyCity.SkyCourseTrack")
CAR_CLS = unreal.load_class(None, "/Script/SkyCity.SkysterCar")
MODE_CLS = unreal.load_class(None, "/Script/SkyCity.SkyCourseMode")
SHOTDIR = unreal.Paths.project_saved_dir() + "Screenshots/MacEditor"

out = {"scenario": SCEN, "files": FILES, "builds": [], "log": [], "events": [], "shots": []}
st = {"n": 0, "h": None, "phase": "start", "n1": 0, "queue": [], "shot": None, "done": False, "tracks": [], "cam": None}


def log(*a):
    out["log"].append(" ".join(str(x) for x in a))


def finish(err=None):
    if err:
        out["error"] = err
    with open(f"{OUTDIR}/geo_{TAG}.json", "w") as f:
        json.dump(out, f, indent=1)
    if st["h"] is not None:
        unreal.unregister_slate_post_tick_callback(st["h"])
        st["h"] = None
    st["done"] = True
    if not STAY and world():
        les.editor_request_end_play()


def world():
    return ues.get_game_world()


def first(cls):
    w = world()
    if not w:
        return None
    xs = unreal.GameplayStatics.get_all_actors_of_class(w, cls)
    return xs[0] if xs else None


def spawn(path, pycls):
    """Spawn an actor in the PIE world with the cheat manager's summon (Python can't spawn into PIE directly)."""
    w = world()
    before = set(unreal.GameplayStatics.get_all_actors_of_class(w, pycls))
    unreal.SystemLibrary.execute_console_command(w, "summon " + path)
    new = [a for a in unreal.GameplayStatics.get_all_actors_of_class(w, pycls) if a not in before]
    return new[0] if new else None


def newest_shot():
    try:
        fs = [os.path.join(SHOTDIR, f) for f in os.listdir(SHOTDIR) if f.endswith(".png")]
        return max(fs, key=os.path.getmtime) if fs else None
    except Exception:
        return None


def sim(v):
    return (v.x / 100.0, -v.y / 100.0, v.z / 100.0)


def ue(p):
    return unreal.Vector(p[0] * 100.0, -p[1] * 100.0, p[2] * 100.0)


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    return mul(a, 1.0 / n) if n > 1e-9 else (0.0, 0.0, 0.0)


# ------------------------------------------------------------------------------------------------ shots
def shot(name):
    st["shot"] = {"name": name, "before": newest_shot(), "n0": st["n"]}
    unreal.SystemLibrary.execute_console_command(world(), f"HighResShot {SIZE}")


def shot_poll():
    s = st["shot"]
    if not s:
        return False
    f = newest_shot()
    if f and f != s["before"] and os.path.getsize(f) > 1000 and time.time() - os.path.getmtime(f) > 0.3:
        dest = f"{OUTDIR}/geo_{TAG}_{s['name']}.png"
        shutil.copyfile(f, dest)
        out["shots"].append(dest)
        st["shot"] = None
        return False
    if st["n"] - s["n0"] > 900:
        out["shots"].append("(missed) " + s["name"])
        st["shot"] = None
        return False
    return True


def look_from(eye, target, fov=70.0):
    """Park a camera at eye looking at target (course metres) and make it the view."""
    w = world()
    cam = st["cam"]
    if cam is None:
        cam = spawn("/Script/Engine.CameraActor", unreal.CameraActor)
        st["cam"] = cam
        if cam is None:
            log("no camera actor (summon failed)")
            return
        try:
            cam.camera_component.set_editor_property("field_of_view", fov)
            cam.camera_component.set_editor_property("constrain_aspect_ratio", False)
        except Exception as e:
            log("cam setup", repr(e))
    e, t = ue(eye), ue(target)
    rot = unreal.MathLibrary.find_look_at_rotation(e, t)
    cam.set_actor_location_and_rotation(e, rot, False, False)
    pc = unreal.GameplayStatics.get_player_controller(w, 0)
    pc.set_view_target_with_blend(cam, 0.0)


def view_car():
    w = world()
    pc = unreal.GameplayStatics.get_player_controller(w, 0)
    car = first(CAR_CLS)
    if car:
        pc.set_view_target_with_blend(car, 0.0)


# ------------------------------------------------------------------------------------------------ building
def build(path, idx):
    txt = open(path).read()
    # with the Course Builder running, its own track takes every course in turn; otherwise one summoned track per course
    have = unreal.GameplayStatics.get_all_actors_of_class(world(), TRACK_CLS)
    director = first(MODE_CLS) is not None
    if director and have:
        tr = have[0]
    else:
        tr = spawn("/Script/SkyCity.SkyCourseTrack", TRACK_CLS)
        if tr is None:
            raise RuntimeError("could not summon a SkyCourseTrack")
    st["tracks"].append(tr)
    t0 = time.time()
    res = tr.call_method("TestBuildJson", (txt,))
    r = json.loads(res)
    r["file"] = path
    r["wall_ms"] = round((time.time() - t0) * 1000, 1)
    out["builds"].append(r)
    short = {k: r.get(k) for k in ("valid", "errors", "warnings", "length", "pieces", "build_ms", "components", "tris", "props")}
    log("build", os.path.basename(path), json.dumps(short))
    return tr, r


def bounds_of(r):
    lo, hi = r.get("bounds_min"), r.get("bounds_max")
    if not lo:
        return (0, 0, 0), (1, 1, 1)
    return tuple(lo), tuple(hi)


def queue_overview_shots(r, name):
    if first(MODE_CLS) is not None:
        lo, hi = bounds_of(r)
        ext = max(hi[0] - lo[0], hi[1] - lo[1])
        st["queue"].append(("pawncam", 0, 85, ext * 1.25))
        st["queue"].append(("wait", 45))
        st["queue"].append(("shot", name + "_top"))
        st["queue"].append(("pawncam", 225, 28, ext * 0.9))
        st["queue"].append(("wait", 45))
        st["queue"].append(("shot", name + "_side"))
        return
    lo, hi = bounds_of(r)
    c = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)
    ext = max(hi[0] - lo[0], hi[1] - lo[1]) * 0.5 + 15
    h = ext / math.tan(math.radians(33))
    # straight down (a hair off vertical so the look-at rotation is well defined), then from the side and low
    st["queue"].append(("look", (c[0] - 0.01 * h, c[1], c[2] + h), c))
    st["queue"].append(("wait", 20))
    st["queue"].append(("shot", name + "_top"))
    st["queue"].append(("look", (c[0] - ext * 1.1, c[1] - ext * 1.3, c[2] + ext * 0.55), c))
    st["queue"].append(("wait", 20))
    st["queue"].append(("shot", name + "_side"))
    st["queue"].append(("look", (c[0] + ext * 1.2, c[1] + ext * 0.6, c[2] + ext * 0.25), c))
    st["queue"].append(("wait", 20))
    st["queue"].append(("shot", name + "_low"))


# ------------------------------------------------------------------------------------------------ driving
D = {"route": [], "idx": 0, "t": 0.0, "next_log": 0.0, "lap_len": 0.0, "fell": 0, "shots_done": set(), "car": None,
     "prev_mode": None, "air_t": 0.0, "max_off": 0.0, "start_wall": 0.0, "dist": 0.0, "lastP": None, "laps_done": 0}


def make_route(r, lap):
    routes = r.get("routes") or []
    segs = r["segs"]
    ids = routes[lap - 1] if routes else list(range(len(segs)))
    pts = []
    for sid in ids:
        s = segs[sid]
        for k, p in enumerate(s["path"]):
            if pts and k == 0:
                continue
            pts.append({"p": (p[0], p[1], p[2]), "u": (p[3], p[4], p[5]), "w": p[6], "deck": p[7] > 0.5, "seg": sid,
                        "kind": s["kind"], "type": s["type"]})
    # distance along, curvature (radius) in the plane of the deck, target speeds
    s = 0.0
    for i, q in enumerate(pts):
        if i:
            s += norm(sub(q["p"], pts[i - 1]["p"]))
        q["s"] = s
    n = len(pts)
    for i, q in enumerate(pts):
        a, b = pts[max(0, i - 3)], pts[min(n - 1, i + 3)]
        d1, d2 = unit(sub(q["p"], a["p"])), unit(sub(b["p"], q["p"]))
        ds = max(1e-3, (b["s"] - a["s"]) * 0.5)
        ang = math.acos(max(-1.0, min(1.0, dot(d1, d2))))
        q["r"] = ds / ang if ang > 1e-4 else 1e4
    vmax = 62.0
    for q in pts:
        v = vmax
        if q["type"] == "curve" or q["kind"] in ("merge_lead", "close_link", "split_lead"):
            v = min(v, math.sqrt(30.0 * q["r"]))
        q["v"] = v
    # loops: fast (the loop needs v^2/r > g at the top and loses speed climbing); corkscrews and wallrides: moderate
    # (a twisting deck is steep away from its middle, so stay central and not too fast)
    for i, q in enumerate(pts):
        if q["type"] == "loop":
            q["v"] = max(q["v"], 44.0)
        if q["type"] in ("corkscrew", "wallride"):
            q["v"] = min(q["v"], TWIST_V)
            q["twist"] = True
    # jumps: the take-off speed that reaches the pad, +8%, held for the run-up
    i = 0
    while i < n:
        if not pts[i]["deck"]:
            j = i
            while j < n and not pts[j]["deck"]:
                j += 1
            lip, land = pts[i - 1], pts[min(j, n - 1)]
            prev = pts[max(0, i - 3)]
            # the lip leaves at 15 degrees (SkyGeom::JumpLipAngle); the 2 m path points round it down
            th = math.radians(15.0) if lip["type"] == "jump" else math.atan2(lip["p"][2] - prev["p"][2], math.hypot(lip["p"][0] - prev["p"][0], lip["p"][1] - prev["p"][1]))
            X = math.hypot(land["p"][0] - lip["p"][0], land["p"][1] - lip["p"][1])
            dz = land["p"][2] - lip["p"][2]
            den = 2 * math.cos(th) ** 2 * (X * math.tan(th) - dz)
            vj = math.sqrt(G * X * X / den) if den > 0 else 50.0
            vj *= 1.08
            out["events"].append({"kind": "jump_plan", "v": round(vj, 1), "X": round(X, 1), "dz": round(dz, 2), "th": round(math.degrees(th), 1)})
            for k in range(max(0, i - 60), j):
                pts[k]["v"] = vj
                pts[k]["jump"] = True
            for k in range(j, min(n, j + 30)):
                pts[k]["after_jump"] = True
            i = j
        else:
            i += 1
    for q in pts:
        q["v"] *= SPEED
    # brake ahead of slow parts
    for i in range(n - 2, -1, -1):
        ds = pts[i + 1]["s"] - pts[i]["s"]
        if not pts[i].get("jump"):
            pts[i]["v"] = min(pts[i]["v"], math.sqrt(pts[i + 1]["v"] ** 2 + 2 * 22.0 * ds))
    return pts


def drive_tick(dt):
    car = D["car"]
    R = D["route"]
    if not car or not R:
        return
    D["t"] += dt
    loc = car.get_actor_location()
    P = sim(loc)
    F = sim(car.get_actor_forward_vector())
    F = (F[0] * 100, F[1] * 100, F[2] * 100)
    U = sim(car.get_actor_up_vector())
    U = (U[0] * 100, U[1] * 100, U[2] * 100)
    v = car.get_speed_mph() / 2.23694
    if D["lastP"]:
        D["dist"] += norm(sub(P, D["lastP"]))
    D["lastP"] = P
    # nearest point ahead of the last one
    i0 = D["idx"]
    best, bj = 1e18, i0
    for j in range(max(0, i0 - 4), min(len(R), i0 + 60)):
        d = norm(sub(P, R[j]["p"]))
        if d < best:
            best, bj = d, j
    D["idx"] = bj
    q = R[bj]
    off = norm(sub(P, q["p"]))
    D["max_off"] = max(D["max_off"], off if q["deck"] else 0)
    # wrap round for more laps
    if bj >= len(R) - 3:
        D["laps_done"] += 1
        out["events"].append({"kind": "lap", "t": round(D["t"], 2), "n": D["laps_done"]})
        if D["laps_done"] >= LAPS:
            return "done"
        D["idx"] = 0
    look = max(7.0, min(28.0, v * 0.42))
    if q.get("twist"):
        look = max(5.0, min(10.0, v * 0.18))   # on a rolling deck a far look-ahead point is on a deck turned the other way
    j, acc = bj, 0.0
    while j + 1 < len(R) and acc < look:
        acc += norm(sub(R[j + 1]["p"], R[j]["p"]))
        j += 1
    T = R[j]["p"]
    Dv = sub(T, P)
    Dp = sub(Dv, mul(U, dot(Dv, U)))
    Fp = sub(F, mul(U, dot(F, U)))
    ang = math.atan2(dot(cross(Fp, Dp), U), dot(Fp, Dp))
    steer = max(-1.0, min(1.0, -ang * 2.2))
    want = q["v"]
    thr, brake, boost = 0.0, 0.0, False
    if v < want - 0.8:
        thr = 1.0
        boost = v < want - 2.5
    elif v > want + 2.0:
        brake = min(1.0, (v - want) / 8.0)
    else:
        thr = 0.5
    mode = car.get_mode()
    if mode != "DRIVE" and mode != "WALL":
        brake = 0.0          # in the air the brake is the air brake: it would spoil a jump
    car.set_editor_property("test_throttle", thr)
    car.set_editor_property("test_brake", brake)
    # per piece: speeds, modes, and AIR over deck that isn't a jump (the car hopping off the surface)
    key = f"{q['seg']}:{q['type']}"
    ps = D.setdefault("per", {}).setdefault(key, {"vmin": 999.0, "vmax": 0.0, "modes": {}, "air_on_deck": 0, "max_off": 0.0})
    ps["vmin"] = min(ps["vmin"], round(v, 1))
    ps["vmax"] = max(ps["vmax"], round(v, 1))
    ps["modes"][mode] = ps["modes"].get(mode, 0) + 1
    ps["max_off"] = max(ps["max_off"], round(off, 2))
    if mode in ("AIR", "AIR BRAKE") and q["deck"] and q["type"] != "jump" and not q.get("after_jump"):
        ps["air_on_deck"] += 1
    car.set_editor_property("test_steer", steer if mode != "AIR" else 0.0)
    car.set_editor_property("test_boost", boost)
    # what happened
    if mode != D["prev_mode"]:
        out["events"].append({"kind": "mode", "t": round(D["t"], 2), "mode": mode, "seg": q["seg"], "type": q["type"],
                              "v": round(v, 1), "p": [round(x, 1) for x in P], "deck": q["deck"]})
        D["prev_mode"] = mode
    if P[2] < q["p"][2] - 6.0 and q["deck"]:
        D["fell"] += 1
        out["events"].append({"kind": "fell", "t": round(D["t"], 2), "seg": q["seg"], "type": q["type"], "p": [round(x, 1) for x in P]})
        return "fell"
    if D["t"] >= D["next_log"]:
        D["next_log"] = D["t"] + 0.2
        out["log"].append([round(D["t"], 2), mode, round(v, 1), [round(x, 2) for x in P], q["seg"], q["type"], round(off, 2),
                           round(want, 1), round(steer, 2), 1 if boost else 0, round(dot(U, q["u"]), 3)])
    # shots at the moments that matter
    if SHOTS and not st["shot"]:
        for key, cond in (("loop_top", q["type"] == "loop" and dot(q["u"], (0, 0, 1)) < -0.9),
                          ("jump_air", not q["deck"] and mode == "AIR"),
                          ("banked_curve", q["type"] == "curve" and abs(q["u"][2]) < 0.97),
                          ("corkscrew", q["type"] == "corkscrew" and q["u"][2] < -0.5),
                          ("wallride", q["type"] == "wallride" and abs(q["u"][2]) < 0.3),
                          ("split", q["kind"] == "split_lead"),
                          ("merge", q["kind"] == "merge_lead")):
            if cond and key not in D["shots_done"]:
                D["shots_done"].add(key)
                shot(f"drive_{key}")
                break
    return None


# ------------------------------------------------------------------------------------------------ the run
if world():
    les.editor_request_end_play()
les.load_level(MAP)
les.editor_request_begin_play()


def tick(dt):
    st["n"] += 1
    if st["done"]:
        return
    w = world()
    if not w:
        if st["n"] > 2400:
            finish("PIE never started")
        return
    try:
        step(w, dt)
    except Exception as e:
        import traceback
        finish("exception: " + traceback.format_exc())


def step(w, dt):
    if st["phase"] == "start":
        if st["n"] < 90:
            return
        if MODE:
            unreal.SystemLibrary.execute_console_command(w, "open " + MAP + "?mode=build")
        st["phase"], st["n1"] = "ready", st["n"]
        return
    if st["phase"] == "ready":
        if st["n"] - st["n1"] < (240 if MODE else 30):
            return
        car = first(CAR_CLS)
        if not car:
            if st["n"] - st["n1"] > 2400:
                finish("no car")
            return
        if SCEN == "build":
            for i, f in enumerate(FILES):
                st["queue"].append(("build", f, i))
                st["queue"].append(("wait", 40))
            st["queue"].append(("end",))
            st["phase"] = "queue"
        elif SCEN == "errors":
            cases = json.load(open(ROOT + "/Scripts/course/courses/bad_cases.json"))
            tr = spawn("/Script/SkyCity.SkyCourseTrack", TRACK_CLS)
            res = []
            for c in cases:
                r = json.loads(tr.call_method("TestBuildJson", (json.dumps(c["course"]),)))
                errs = r.get("errors", [])
                if c["expect"]:
                    ok = all(any(e_ in e for e in errs) for e_ in c["expect"])
                else:
                    ok = bool(r.get("valid"))
                res.append({"why": c["why"], "ok": ok, "errors": errs, "warnings": r.get("warnings", []), "valid": r.get("valid")})
            out["cases"] = res
            out["passed"] = sum(1 for x in res if x["ok"])
            out["total"] = len(res)
            finish()
            return
        elif SCEN == "roundtrip":
            mode = first(MODE_CLS)
            if not mode:
                finish("roundtrip needs mode=1 (the director)")
                return
            res = []
            for f in FILES:
                txt = open(f).read()
                a = mode.call_method("TestSetCourseJson", (txt, ""))
                ok_set = a[0] if isinstance(a, tuple) else a
                errs = a[1] if isinstance(a, tuple) and len(a) > 1 else ""
                back = mode.call_method("TestGetCourseJson", ())
                item = {"file": os.path.basename(f), "set": ok_set, "set_errors": errs, "written": back}
                try:
                    j0, j1 = json.loads(txt), json.loads(back)

                    def flat(ps):
                        o = []
                        for p_ in ps:
                            o.append(p_["type"])
                            for b_ in p_.get("branches", []):
                                o.append("[")
                                o += flat(b_.get("pieces", []))
                                o.append("]")
                        return o
                    item["same_pieces"] = flat(j0["pieces"]) == flat(j1["pieces"])
                    tr = first(TRACK_CLS)
                    r0 = json.loads(tr.call_method("TestBuildJson", (txt,)))
                    r1 = json.loads(tr.call_method("TestBuildJson", (back,)))
                    item["len0"], item["len1"] = r0.get("length"), r1.get("length")
                    item["same_length"] = abs((r0.get("length") or 0) - (r1.get("length") or 0)) < 1e-6
                    item["ok"] = bool(ok_set and item["same_pieces"] and item["same_length"])
                except Exception as e:
                    item["ok"] = False
                    item["exception"] = repr(e)
                res.append(item)
            out["roundtrip"] = res
            finish()
            return
        elif SCEN == "drive":
            tr, r = build(FILES[0], 0)
            st["queue"].append(("wait", 30))
            if not r.get("valid"):
                finish("the course didn't build: " + "; ".join(r.get("errors", [])[:5]))
                return
            D["route"] = make_route(r, LAP)
            D["lap_len"] = D["route"][-1]["s"] if D["route"] else 0
            out["route_points"] = len(D["route"])
            if LEVEL > 0:
                # careful: Progress.SetLevel saves, so this changes the player's saved level (Saved/SaveGames/Skyster.sav)
                car.set_editor_property("test_set_level", LEVEL)
                out["warning"] = f"set the car to level {LEVEL}: this is saved to the player's progress; set it back in the Garage"
            car.set_editor_property("test_full_tank", True)
            car.set_editor_property("test_input", True)
            D["car"] = car
            g = r["grid_ue"][0]
            if SHOTS:
                queue_overview_shots(r, "course")
            st["queue"].append(("view_car",))
            st["queue"].append(("teleport", g))
            st["queue"].append(("wait", 45))
            st["queue"].append(("drive",))
            st["phase"] = "queue"
        return
    if st["phase"] == "queue":
        if shot_poll():
            return
        if st.get("wait", 0) > 0:
            st["wait"] -= 1
            return
        while st["queue"]:
            s = st["queue"].pop(0)
            k = s[0]
            if k == "build":
                tr, r = build(s[1], s[2])
                if SHOTS and r.get("parsed"):
                    # overview shots go in right after this build (front of the queue)
                    keep = st["queue"]
                    st["queue"] = []
                    queue_overview_shots(r, os.path.splitext(os.path.basename(s[1]))[0])
                    st["queue"] += keep
            elif k == "look":
                look_from(s[1], s[2])
            elif k == "pawncam":
                pawn = first(unreal.load_class(None, "/Script/SkyCity.SkyCourseBuilderPawn"))
                if pawn:
                    pawn.call_method("TestCamera", (float(s[1]), float(s[2]), float(s[3]), True))
            elif k == "view_car":
                view_car()
            elif k == "wait":
                st["wait"] = s[1]
                return
            elif k == "shot":
                shot(s[1])
                return
            elif k == "teleport":
                g = s[1]
                D["car"].call_method("TestTeleport", (unreal.Vector(g[0], g[1], g[2] + 60.0), g[3]))
            elif k == "drive":
                st["phase"] = "drive"
                D["start_wall"] = time.time()
                return
            elif k == "end":
                finish()
                return
        return
    if st["phase"] == "drive":
        shot_poll()
        r = drive_tick(dt)
        if r in ("done", "fell") or D["t"] > SECS:
            car = D["car"]
            for k, v in (("test_throttle", 0.0), ("test_brake", 1.0), ("test_steer", 0.0), ("test_boost", False)):
                car.set_editor_property(k, v)
            out["per_piece"] = D.get("per", {})
            out["result"] = {"why": r or "time", "t": round(D["t"], 2), "dist": round(D["dist"], 1), "laps": D["laps_done"],
                             "route_len": round(D["lap_len"], 1), "fell": D["fell"], "max_off": round(D["max_off"], 2),
                             "progress": round(D["route"][D["idx"]]["s"], 1) if D["route"] else 0}
            st["phase"] = "tail"
            st["n1"] = st["n"]
        return
    if st["phase"] == "tail":
        if shot_poll():
            return
        if st["n"] - st["n1"] > 30:
            finish()


st["h"] = unreal.register_slate_post_tick_callback(tick)
