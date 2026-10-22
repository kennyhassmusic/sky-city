"""Course Builder UI tests (editor Python). Opens McGregor as the Course Builder (as the Garage does: McGregor?mode=build),
presses the builder's buttons through its test hooks (ASkyCourseBuilderPawn::TestPress / TestType / TestCamera: the pad is
ignored while bTestInput is on), reads its state back as JSON and takes HighResShots.

Run it from the editor's console box:   py /abs/path/Scripts/course/builder_test.py <scenario> [k=v ...]
Scenarios (each writes Saved/Playtest/course/out_<scenario>.json and shots Saved/Playtest/course/<scenario>_NN_<what>.png):
  view      the build view: area outline, palette, camera moves, the course menu, name box, map list
  build     place pieces one after another (straight, curve, ramp, jump, loop, booster, lanes, checkpoint ...) and look
  split     a split: two branches, View cycles them, build on a branch, remove the split with B
  files     rename, save with the name box, new course, load it back through the list
  drive     test drive (Y), then Y back to building; the camera returns over the cursor
  limits    pieces that must not fit: the fit banner's reason, a refused A, a toast
  all       view, build, split, files, drive, limits one after the other
Options: map=/Game/Maps/McGregor  size=1920x1080  spawn=1 (spawn the director in a plain PIE world instead of ?mode=build)
         fresh=1 (default: start from a new starter course, ignoring the autosave)  steps=/abs/steps.json (your own steps)
Steps (a list of lists): ["wait", frames] ["press", "a"] ["pieces", ["right", "up"]] ["piece", "curve"] ["shot", "name"]
  ["state", "label"] ["cam", yaw, pitch, dist, snap] ["type", "text"] ["course", "/abs/course.json"] ["drive"] ["stop"]
  ["camera_axes", panx, pany, orbx, orby, zoom] ["expect", "label", "state.path", value] ["new"] (menu > New course) ["py", "code"] (run Python in the PIE world)
"""
import glob, json, os, shutil, sys, time, unreal

ROOT = os.environ.get("SKYCITY_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUTDIR = ROOT + "/Saved/Playtest/course"
os.makedirs(OUTDIR, exist_ok=True)
A = sys.argv[1:]
SCEN = A[0] if A and "=" not in A[0] else "view"
KV = dict(a.split("=", 1) for a in A if "=" in a)
MAP = KV.get("map", "/Game/Maps/McGregor")
SIZE = KV.get("size", "1920x1080")
SPAWN = KV.get("spawn", "0") == "1"
FRESH = KV.get("fresh", "1") == "1"
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
MODE_CLS = unreal.load_class(None, "/Script/SkyCity.SkyCourseMode")
PAWN_CLS = unreal.load_class(None, "/Script/SkyCity.SkyCourseBuilderPawn")
CAR_CLS = unreal.load_class(None, "/Script/SkyCity.SkysterCar")
PALETTE = ["straight", "curve", "ramp", "jump", "loop", "corkscrew", "wallride", "booster", "lanes", "split", "checkpoint", "finish", "close"]
SHOTDIR = unreal.Paths.project_saved_dir() + "Screenshots/MacEditor"

out = {"scenario": SCEN, "states": {}, "shots": [], "expect": [], "log": []}
st = {"n": 0, "h": None, "phase": "start", "wait": 0, "queue": [], "shot": None, "n1": 0, "failed": 0, "done": False}


def finish(err=None):
    if err:
        out["error"] = err
    out["passed"] = not err and st["failed"] == 0
    with open(f"{OUTDIR}/out_{SCEN}.json", "w") as f:
        json.dump(out, f, indent=1)
    if st["h"] is not None:
        unreal.unregister_slate_post_tick_callback(st["h"])
        st["h"] = None
    st["done"] = True


def log(*a):
    out["log"].append(" ".join(str(x) for x in a))


def world():
    return ues.get_game_world()


def first(cls):
    w = world()
    if not w:
        return None
    xs = unreal.GameplayStatics.get_all_actors_of_class(w, cls)
    return xs[0] if xs else None


def snake(n):
    r = ""
    for i, c in enumerate(n):
        if c.isupper() and i:
            r += "_"
        r += c.lower()
    return r


def call(obj, name, *args):
    """Call a UFUNCTION by its C++ name (snake_case wrapper if the editor made one, else call_method)."""
    try:
        return getattr(obj, snake(name))(*args)
    except AttributeError:
        return obj.call_method(name, args)


def pawn_state():
    p = first(PAWN_CLS)
    if not p:
        return {}
    try:
        return json.loads(call(p, "TestStateJson"))
    except Exception as e:
        return {"error": repr(e)}


def mode_state():
    m = first(MODE_CLS)
    if not m:
        return {}
    try:
        return json.loads(call(m, "TestStateJson"))
    except Exception as e:
        return {"error": repr(e)}


def pick(d, path):
    for k in path.split("."):
        if isinstance(d, str):
            try:
                d = json.loads(d)
            except Exception:
                return None
        if isinstance(d, list):
            d = d[int(k)] if k.isdigit() and int(k) < len(d) else None
        elif isinstance(d, dict):
            d = d.get(k)
        else:
            return None
        if d is None:
            return None
    return d


def newest_shot():
    fs = glob.glob(SHOTDIR + "/HighresScreenshot*.png")
    return max(fs, key=os.path.getmtime) if fs else None


# ------------------------------------------------------------------------------------------------ steps
def expand_piece(name):
    """Presses (one per frame) to bring the palette to a piece."""
    s = pawn_state()
    cur = int(s.get("paletteIndex", 0))
    want = PALETTE.index(name)
    n = len(PALETTE)
    right = (want - cur) % n
    if right <= n // 2:
        return [["press", "right"], ["wait", 2]] * right
    return [["press", "left"], ["wait", 2]] * (n - right)


def run_step(step):
    kind = step[0]
    p = first(PAWN_CLS)
    m = first(MODE_CLS)
    if kind == "wait":
        st["wait"] = int(step[1])
    elif kind == "press":
        if p:
            call(p, "TestPress", step[1])
        st["wait"] = 2
    elif kind == "pieces":
        st["queue"][0:0] = [x for b in step[1] for x in (["press", b], ["wait", 2])]
    elif kind == "piece":
        st["queue"][0:0] = expand_piece(step[1])
    elif kind == "new":
        # menu > New course: the same fresh starter course, whatever came before
        st["queue"][0:0] = [["press", "x"], ["wait", 5], ["press", "down"], ["wait", 3], ["press", "a"], ["wait", 40]]
    elif kind == "state":
        out["states"][step[1]] = {"pawn": pawn_state(), "mode": mode_state()}
    elif kind == "cam":
        if p:
            call(p, "TestCamera", float(step[1]), float(step[2]), float(step[3]), bool(step[4]) if len(step) > 4 else False)
    elif kind == "camera_axes":
        if p:
            p.set_editor_property("test_pan_x", float(step[1])); p.set_editor_property("test_pan_y", float(step[2]))
            p.set_editor_property("test_orbit_x", float(step[3])); p.set_editor_property("test_orbit_y", float(step[4]))
            p.set_editor_property("test_zoom", float(step[5]))
    elif kind == "type":
        if p:
            call(p, "TestType", step[1])
        st["wait"] = 2
    elif kind == "course":
        if m:
            txt = open(step[1]).read() if os.path.exists(step[1]) else step[1]
            res = call(m, "TestSetCourseJson", txt, "")
            log("course:", res)
        st["wait"] = 5
    elif kind == "drive":
        if m:
            call(m, "TestStartDrive", int(step[1]) if len(step) > 1 else 0)
    elif kind == "stop":
        if m:
            call(m, "TestStopDrive")
    elif kind == "shot":
        before = newest_shot()
        unreal.SystemLibrary.execute_console_command(world(), f"HighResShot {SIZE}")
        st["shot"] = {"name": step[1], "before": before, "n0": st["n"]}
    elif kind == "py":
        # ["py", "code"]: run a bit of Python in the PIE world (names: unreal, first, MODE_CLS, PAWN_CLS, world, out, log)
        exec(step[1], {"unreal": unreal, "first": first, "MODE_CLS": MODE_CLS, "PAWN_CLS": PAWN_CLS, "world": world, "out": out, "log": log, "json": json})
    elif kind == "expect":
        label, path, want = step[1], step[2], step[3]
        got = pick({"pawn": out["states"].get(label, {}).get("pawn", {}), "mode": out["states"].get(label, {}).get("mode", {}), "state": out["states"].get(label, {})}, path)
        ok = (want(got) if callable(want) else got == want)
        out["expect"].append({"label": label, "path": path, "want": want if not callable(want) else "fn", "got": got, "ok": bool(ok)})
        if not ok:
            st["failed"] += 1
    else:
        log("unknown step", step)


# ------------------------------------------------------------------------------------------------ scenarios
def S_view():
    return [
        ["wait", 150], ["state", "start"], ["shot", "start_view"],
        ["cam", 0, 89, 440, False], ["wait", 140], ["shot", "area_topdown"],
        ["cam", 40, 35, 140, False], ["wait", 120], ["shot", "low_wide"],
        ["cam", 0, 52, 70, False], ["wait", 100],
        ["piece", "curve"], ["wait", 20], ["shot", "palette_curve"],
        ["piece", "split"], ["wait", 20], ["shot", "palette_split"],
        ["press", "r3"], ["wait", 5], ["state", "split_r3"],
        ["piece", "straight"],
        ["press", "x"], ["wait", 30], ["shot", "menu"], ["state", "menu"],
        ["pieces", ["down", "down", "down", "down", "down", "down", "down", "down", "down", "down", "down"]], ["wait", 20], ["shot", "menu_llm"],
        ["pieces", ["up", "up", "up", "up", "up", "up", "up", "up", "up"]],
        ["press", "a"], ["wait", 20], ["shot", "name_box"], ["state", "name"],
        ["pieces", ["b"]], ["wait", 10],
        ["press", "x"], ["wait", 20], ["state", "closed"],
        ["press", "menu"], ["wait", 30], ["shot", "garage"], ["state", "garage"],
        ["press", "b"], ["wait", 10], ["state", "end"],
    ]


def S_build():
    s = [["wait", 150], ["new"], ["state", "start"]]
    s += [["piece", "straight"], ["pieces", ["up"] * 6], ["wait", 20], ["state", "straight60"], ["shot", "straight_preview"]]
    s += [["press", "a"], ["wait", 100], ["state", "placed1"], ["shot", "after_straight"]]
    s += [["piece", "curve"], ["wait", 20], ["shot", "curve_preview"], ["press", "a"], ["wait", 100], ["state", "placed2"], ["shot", "after_curve"]]
    s += [["piece", "ramp"], ["press", "a"], ["wait", 60], ["piece", "jump"], ["wait", 20], ["state", "jump"], ["shot", "jump_preview"], ["press", "a"], ["wait", 100], ["state", "placed4"], ["shot", "after_jump"]]
    s += [["piece", "booster"], ["press", "a"], ["wait", 40], ["piece", "loop"], ["wait", 20], ["state", "loop"], ["shot", "loop_preview"], ["press", "a"], ["wait", 100], ["state", "placed6"], ["shot", "after_loop"]]
    s += [["piece", "lanes"], ["wait", 20], ["state", "lanes"], ["press", "a"], ["wait", 60], ["piece", "checkpoint"], ["press", "a"], ["wait", 60], ["state", "placed8"], ["shot", "after_lanes"]]
    s += [["cam", 20, 70, 220, False], ["wait", 140], ["shot", "overview"]]
    s += [["press", "b"], ["wait", 30], ["press", "b"], ["wait", 30], ["state", "removed2"], ["shot", "after_removes"]]
    s += [["press", "undo"], ["wait", 30], ["state", "undone"]]
    s += [["expect", "placed1", "mode.pieces", 3], ["expect", "placed8", "mode.pieces", lambda v: v is not None and v >= 8]]
    return s


def S_split():
    s = [["wait", 150], ["new"], ["state", "start"]]
    s += [["piece", "straight"], ["press", "a"], ["wait", 40], ["piece", "split"], ["wait", 20], ["state", "split_pending"], ["shot", "split_preview"]]
    s += [["press", "a"], ["wait", 120], ["state", "split_placed"], ["shot", "split_two_branches"]]
    s += [["piece", "straight"], ["press", "a"], ["wait", 60], ["state", "branch0_piece"]]
    s += [["press", "view"], ["wait", 100], ["state", "branch1"], ["shot", "branch1"]]
    s += [["piece", "curve"], ["press", "a"], ["wait", 100], ["state", "branch1_curve"], ["shot", "branch1_curve"]]
    s += [["press", "view"], ["wait", 100], ["state", "main_after_merge"], ["shot", "main_after_merge"]]
    s += [["piece", "straight"], ["press", "a"], ["wait", 100], ["state", "main_continued"], ["shot", "main_continued"]]
    s += [["press", "x"], ["wait", 20], ["pieces", ["down"] * 9], ["wait", 10], ["state", "menu_main"]]
    s += [["press", "b"], ["wait", 10], ["press", "view"], ["wait", 60], ["press", "x"], ["wait", 20], ["shot", "menu_branch"], ["state", "menu_branch"]]
    s += [["press", "b"], ["wait", 10]]
    s += [["expect", "split_placed", "mode.seqs", 3], ["expect", "split_placed", "pawn.editSeq", 1], ["expect", "branch1", "pawn.editSeq", 2]]
    return s


def S_files():
    s = [["wait", 150], ["new"], ["piece", "straight"], ["press", "a"], ["wait", 40]]
    s += [["press", "x"], ["wait", 10], ["pieces", ["down", "down", "down", "down"]], ["press", "a"], ["wait", 10], ["state", "rename_box"]]
    s += [["pieces", ["left"] * 12], ["type", "Test Loop 1"], ["wait", 5], ["shot", "rename_typed"], ["press", "a"], ["wait", 20], ["state", "renamed"]]
    s += [["press", "x"], ["wait", 10], ["pieces", ["down", "down"]], ["press", "a"], ["wait", 10], ["state", "save_box"], ["press", "a"], ["wait", 30], ["state", "saved"]]
    s += [["press", "x"], ["wait", 10], ["pieces", ["down"]], ["press", "a"], ["wait", 20], ["state", "new"], ["press", "x"], ["wait", 10], ["pieces", ["down", "down", "down"]], ["press", "a"], ["wait", 20], ["shot", "load_list"], ["state", "load_list"]]
    s += [["press", "a"], ["wait", 60], ["state", "loaded"], ["shot", "loaded"]]
    s += [["expect", "renamed", "mode.name", "Test Loop 1"], ["expect", "saved", "pawn.toasts", lambda v: v is not None and any("Saved" in t for t in v)]]
    return s


def S_drive():
    s = [["wait", 150], ["new"], ["piece", "straight"], ["press", "a"], ["wait", 40], ["state", "before"], ["shot", "before_drive"]]
    s += [["press", "y"], ["wait", 90], ["state", "driving"], ["shot", "driving"]]
    s += [["stop"], ["wait", 150], ["state", "back"], ["shot", "back_to_building"]]
    s += [["expect", "driving", "mode.driving", True], ["expect", "back", "mode.driving", False], ["expect", "back", "mode.carPossessed", False]]
    return s


def S_limits():
    s = [["wait", 150], ["new"], ["piece", "curve"], ["pieces", ["up"] * 12], ["wait", 20], ["state", "wide_curve"], ["shot", "curve_270"]]
    s += [["pieces", ["rb"] * 70], ["wait", 20], ["state", "big_radius"], ["shot", "big_radius"], ["press", "a"], ["wait", 20], ["state", "refused"], ["shot", "refused"]]
    s += [["piece", "finish"], ["press", "a"], ["wait", 60], ["piece", "straight"], ["wait", 20], ["state", "closed"], ["shot", "after_finish"], ["press", "a"], ["wait", 20], ["state", "refused_closed"]]
    s += [["press", "b"], ["wait", 40], ["state", "reopened"]]
    return s


SCENARIOS = {"view": S_view, "build": S_build, "split": S_split, "files": S_files, "drive": S_drive, "limits": S_limits}
if "steps" in KV:
    STEPS = json.load(open(KV["steps"]))
elif SCEN == "all":
    STEPS = []
    for k in ("view", "build", "split", "files", "drive", "limits"):
        STEPS += [["marker", k]] + SCENARIOS[k]()
else:
    STEPS = SCENARIOS[SCEN]()
st["queue"] = list(STEPS)

# ------------------------------------------------------------------------------------------------ the loop
if FRESH:
    # start every run from a new starter course, not last run's autosave
    af = ROOT + "/Saved/Courses/_autosave.json"
    if os.path.exists(af):
        os.remove(af)
if world():
    les.editor_request_end_play()
les.load_level(MAP)
les.editor_request_begin_play()


def ready():
    p = first(PAWN_CLS)
    return p is not None


def tick(dt):
    st["n"] += 1
    w = world()
    if st["done"]:
        return
    if not w:
        if st["n"] > 2400:
            finish("PIE never started")
        return
    if st["phase"] == "start":
        if st["n"] < 90:
            return
        if SPAWN:
            cls = MODE_CLS
            if not first(MODE_CLS):
                t = unreal.Transform()
                a = unreal.GameplayStatics.begin_deferred_actor_spawn_from_class(w, cls, t)
                unreal.GameplayStatics.finish_spawning_actor(a, t)
            st["phase"], st["n1"] = "wait_mode", st["n"]
        else:
            unreal.SystemLibrary.execute_console_command(w, "open " + MAP + "?mode=build")
            st["phase"], st["n1"] = "wait_mode", st["n"]
        return
    if st["phase"] == "wait_mode":
        if st["n"] - st["n1"] < 60:
            return
        if not ready():
            if st["n"] - st["n1"] > 2400:
                finish("no Course Builder director/pawn appeared")
            return
        p = first(PAWN_CLS)
        p.set_editor_property("test_input", True)    # the real pad is ignored from here on
        st["phase"], st["n1"] = "run", st["n"]
        return
    if st["phase"] != "run":
        return
    # screenshot in flight: wait for the new file
    if st["shot"]:
        s = st["shot"]
        f = newest_shot()
        if f and f != s["before"] and os.path.getsize(f) > 1000:
            idx = len(out["shots"]) + 1
            dest = f"{OUTDIR}/{SCEN}_{idx:02d}_{s['name']}.png"
            shutil.copyfile(f, dest)
            out["shots"].append(dest)
            st["shot"] = None
        elif st["n"] - s["n0"] > 600:
            out["shots"].append("(missed) " + s["name"])
            st["shot"] = None
        return
    if st["wait"] > 0:
        st["wait"] -= 1
        return
    while st["queue"]:
        step = st["queue"].pop(0)
        if step[0] == "marker":
            out["log"].append("== " + step[1])
            continue
        try:
            run_step(step)
        except Exception as e:
            log("step failed", step, repr(e))
            st["failed"] += 1
        if st["wait"] > 0 or st["shot"]:
            return
    # the end
    w2 = world()
    if w2:
        les.editor_request_end_play()
    finish()


st["h"] = unreal.register_slate_post_tick_callback(tick)
