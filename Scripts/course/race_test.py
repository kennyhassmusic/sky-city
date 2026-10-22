"""Course Builder race test (the race agent's proof). Run in the editor's Python console:
    py Scripts/course/race_test.py [secs=170] [skills=0.5,0.8,1.1] [autopilot=0.9] [laps=3] [opponents=3]
                                   [drop=1] [drop_at=24] [shots=1] [map=/Game/Maps/McGregor] [tag=race]
                                   [file=Scripts/course/courses/<course>.json]
Loads McGregor, starts PIE, and races SkyCourse::Example (a loop, a 36 m jump, a lights split routed by lap: one branch
on laps 1 and 3, the other on lap 2) in the Course Builder's build area with SkyCourse.RaceTest: the player's car driven
by the race's test autopilot, plus AI opponents of mixed skill (SkyCourse.RaceSkills). Mid-race one opponent is dropped
off the side of the track (drop=1) to prove the recovery. Every second the race's results JSON is sampled; at the end
the whole log (events: gates, laps, branches, respawns, finishes) and the player's best-times file are saved.
Writes Saved/Course/race_<tag>.json and HighResShots (Saved/Screenshots); a HUD shot (Shot showui) at the results.
file=: race that course file instead of the example (a path relative to the project, or absolute).
The output's "respawn_summary" lists each car's respawns with where they happened (segment, piece) and why.
Without the editor's MCP: the console command SkyCourse.RaceTest does the same by hand."""
import json, math, os, sys, time, unreal


def _root():
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
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())


ROOT = _root()
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
SECS = float(KV.get("secs", 240))
SKILLS = KV.get("skills", "0.5,0.8,1.1")
AUTOPILOT = float(KV.get("autopilot", 0.9))
LAPS = int(KV.get("laps", 3))
OPP = int(KV.get("opponents", 3))
DROP = KV.get("drop", "1") == "1"
DROP_AT = float(KV.get("drop_at", 24))
SHOTS = KV.get("shots", "1") == "1"
MAP = KV.get("map", "/Game/Maps/McGregor")
TAG = KV.get("tag", "race")
FILE = KV.get("file", "")
if FILE and not os.path.isabs(FILE):
    FILE = os.path.join(ROOT, FILE)
OUT = os.path.join(ROOT, "Saved", "Course", f"race_{TAG}.json")
# the Course Builder's build area on McGregor (Content/SkyCity/Data/course_area.json): start and heading
AREA = json.load(open(os.path.join(ROOT, "Content", "SkyCity", "Data", "course_area.json")))
START = AREA.get("start", [1640.0, -3340.0, 11.25])
YAW = AREA.get("yaw", 0)

ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
CAR = unreal.load_class(None, "/Script/SkyCity.SkysterCar")
RACE = unreal.load_class(None, "/Script/SkyCity.SkyCourseRace")
out = {"map": MAP, "args": KV, "start": START, "samples": [], "shots": [], "notes": []}
st = {"n": 0, "h": None, "phase": "load", "t0": None, "next_sample": 0.0, "dropped": None, "shot_times": [2.5, 9.0, 18.0, 33.0, 52.0],
      "done_t": None, "last": None}


def save():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)


def cmd(w, c):
    unreal.SystemLibrary.execute_console_command(w, c)
    out["notes"].append(f"cmd: {c}")


def race_of(w):
    for a in unreal.GameplayStatics.get_all_actors_of_class(w, RACE):
        return a
    return None


def results(w):
    r = race_of(w)
    if not r:
        return None
    try:
        return json.loads(r.call_method("TestResultsJson"))
    except Exception as e:
        out["notes"].append(f"results: {e!r}")
        return None


def shot(w, what, ui=False):
    if not SHOTS:
        return
    cmd(w, "Shot showui" if ui else "HighResShot 1920x1080")
    out["shots"].append({"what": what, "ui": ui, "wall": round(time.time() - st["t0"], 1)})


def ai_cars(w):
    return [a for a in unreal.GameplayStatics.get_all_actors_of_class(w, CAR) if a.get_editor_property("ai_driver")]


def finish(why):
    out["why_stopped"] = why
    w = ues.get_game_world()
    if w:
        out["final"] = results(w)
    # the player's best times, saved next to the course file
    name = "Sky Loop"
    if FILE:
        try:
            name = json.load(open(FILE)).get("name", name)
        except Exception:
            pass
    times = os.path.join(ROOT, "Saved", "Courses", f"{name}.times.json")
    out["times_file"] = times
    out["times"] = json.load(open(times)) if os.path.exists(times) else None
    out["respawn_summary"] = summarize(out.get("final") or st.get("last"))
    save()
    if ues.get_game_world():
        les.editor_request_end_play()
    if st["h"] is not None:
        unreal.unregister_slate_post_tick_callback(st["h"])
        st["h"] = None


def summarize(r):
    """Per car: skill, finished, time, lap times, and each respawn with its place (seg, piece) and reason."""
    if not r:
        return None
    import re
    cars = {c["name"]: {"skill": round(c["skill"], 2), "finished": c["finished"], "time": round(c["time"], 2), "laps": [round(x, 2) for x in c["lap_times"]],
                        "respawns": c["respawns"], "where": []} for c in r.get("cars", [])}
    for e in r.get("events", []):
        m = re.match(r"\s*([-\d.]+)\s+(\S+) back on the track at (.*?) \((.*)\)$", e)
        if not m or m.group(2) not in cars:
            continue
        why = m.group(4)
        w = re.search(r"left at seg (\d+) \((\w+)\) frame (\d+)", why)
        cars[m.group(2)]["where"].append({"t": float(m.group(1)), "seg": int(w.group(1)) if w else None, "piece": w.group(2) if w else None,
                                          "frame": int(w.group(3)) if w else None, "why": why.split(";")[0]})
    return cars


def tick(dt):
    st["n"] += 1
    st["ticks"] = st.get("ticks", 0) + 1
    w = ues.get_game_world()
    try:
        if st["phase"] == "load":
            if not w:
                if st["n"] > 1200:
                    finish("PIE never started")
                return
            pawn = unreal.GameplayStatics.get_player_pawn(w, 0)
            if pawn and st["n"] > 90:
                st["t0"] = time.time()
                cmd(w, f"SkyCourse.RaceSkills {SKILLS}")
                cmd(w, f"SkyCourse.RaceAutopilot {AUTOPILOT}")
                if FILE:
                    cmd(w, f"SkyCourse.RaceTest file={FILE} opponents={OPP} laps={LAPS}")
                else:
                    cmd(w, f"SkyCourse.RaceTest at={START[0]},{START[1]},{START[2]} yaw={YAW} opponents={OPP} laps={LAPS}")
                st["phase"] = "race"
            return
        if not w:
            finish("PIE ended")
            return
        wall = time.time() - st["t0"]
        if wall > SECS:
            finish("timeout")
            return
        if wall < st["next_sample"]:
            return
        st["next_sample"] = wall + 1.0
        r = results(w)
        if not r:
            if wall > 10:
                finish("no race (see the log: LogSkyRace)")
            return
        st["last"] = r
        clock = r.get("time", 0)
        fps = st.get("ticks", 0) / max(1e-3, wall - st.get("last_wall", 0.0))
        st["ticks"], st["last_wall"] = 0, wall
        out["samples"].append({"wall": round(wall, 1), "clock": round(clock, 2), "fps": round(fps, 1), "phase": r.get("phase"), "gates_lap": r.get("gates_lap"),
                               "tick_ms": round(r.get("tick_ms_avg", 0), 3), "tick_ms_max": round(r.get("tick_ms_max", 0), 3), "contacts": r.get("contacts"),
                               "cars": [{"n": c["name"], "p": c["place"], "lap": c["lap"], "fin": c["finished"], "mph": round(c["speed_mph"]),
                                         "prog": round(c["progress"], 3), "seg": c["seg"], "resp": c["respawns"]} for c in r.get("cars", [])]})
        # shots along the way (the chase camera on the player's car)
        while st["shot_times"] and clock >= st["shot_times"][0]:
            shot(w, f"race clock {st['shot_times'].pop(0)} s")
        # drop one opponent off the side of the track: it must find its way back (respawn at its last checkpoint)
        if DROP and st["dropped"] is None and clock >= DROP_AT:
            cars = ai_cars(w)
            if len(cars) >= 2:
                c = cars[1]
                loc = c.get_actor_location()
                right = c.get_actor_right_vector()
                to = unreal.Vector(loc.x + right.x * 1600, loc.y + right.y * 1600, loc.z + 400)
                c.call_method("TestTeleport", (to, c.get_actor_rotation().yaw))
                who = next((x["name"] for x in r.get("cars", []) if x.get("actor") == c.get_name()), c.get_name())
                st["dropped"] = {"clock": clock, "car": who, "actor": c.get_name(), "from": [round(loc.x), round(loc.y), round(loc.z)], "to": [round(to.x), round(to.y), round(to.z)]}
                out["dropped"] = st["dropped"]
                out["notes"].append(f"dropped {who} 16 m off the side at race clock {clock:.1f}")
        cars = r.get("cars", [])
        player = next((c for c in cars if c.get("player")), None)
        if player and player.get("finished") and st["done_t"] is None:
            st["done_t"] = wall
            shot(w, "results (HUD)", ui=True)
        if st["phase"] == "race" and (r.get("phase") == "done" or (st["done_t"] is not None and all(c.get("finished") for c in cars))):
            if st["done_t"] is None:
                st["done_t"] = wall
            if wall - st["done_t"] > 3.0:
                shot(w, "results at the end (HUD)", ui=True)
                st["phase"] = "ending"
                st["end_wall"] = wall
        if st["phase"] == "ending" and wall - st.get("end_wall", wall) > 2.0:
            finish("race over")
        save()
    except Exception as e:
        out["notes"].append(f"error: {e!r}")
        finish("error")


# a run still going from an earlier call (its callback would end this run's PIE): stop it first
_old = getattr(unreal, "_skycity_race_test_handle", None)
if _old is not None:
    try:
        unreal.unregister_slate_post_tick_callback(_old)
    except Exception:
        pass
if ues.get_game_world():
    les.editor_request_end_play()
les.load_level(MAP)
les.editor_request_begin_play()
st["h"] = unreal.register_slate_post_tick_callback(tick)
unreal._skycity_race_test_handle = st["h"]
