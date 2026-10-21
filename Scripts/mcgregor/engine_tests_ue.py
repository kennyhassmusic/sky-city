"""Places the timed engine tests (C++ ASkysterEngineTests, Source/SkyCity/SkysterEngineTests.*) in a McGregor map and fills
every property from Saved/McGregor/site_features.json -> tests.engine_tests (site_layout.py / tests_layout.py): the
stands in rotation order (nozzle, plume, exhaust bay, burn time, smoke / fire scale), interval 414 s (6.9 min), the
first test 40 s after load at the stand nearest the player, wind, rumble radius, sound radius, and the assets (plume
cone + MI_Jet, smoke flipbook + fire materials, the roar loop) so they cook with the map. Night map: the flickering
light over the exhaust bay is on. (mcgregor-tests agent, 20 Oct 2026; needs the editor rebuilt with the new class.)

Stages (args, default "place save"):
  map=<path>   load that map first (e.g. map=/Game/Maps/McGregorNight)
  place        removes this script's actor (tag MG_EngineTests) and spawns "Engine_Tests" at the site centre
  save         saves the level / dirty packages
  dry          (alone) prints the site table it would set, no editor changes
Run (editor, PIE off, lock taken):
  py Scripts/mcgregor/engine_tests_ue.py map=/Game/Maps/McGregor place save
  py Scripts/mcgregor/engine_tests_ue.py map=/Game/Maps/McGregorNight place save
Writes Saved/MCPScripts/out_engine_tests.json (props_failed lists any property name that didn't match).
"""
import json, math, sys, time, traceback

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
OUT = ROOT + "/Saved/MCPScripts/out_engine_tests.json"
F = json.load(open(ROOT + "/Saved/McGregor/site_features.json"))
ET = F["tests"]["engine_tests"]
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
STAGES = [a for a in sys.argv[1:] if "=" not in a] or ["place", "save"]
KIND = {"engine": 0, "booster": 1, "stage": 2}
TAG = "MG_EngineTests"
ASSETS = {"PlumeMesh": "/Game/Vehicles/RoadsterRig/SC_JetCone/StaticMeshes/SC_JetCone",
          "QuadMesh": "/Engine/BasicShapes/Plane",
          "JetMaterial": "/Game/SkyCity/Pickups/Materials/MI_Jet",
          "SmokeMaterial": "/Game/SkyCity/FX/M_SkyVapor",
          "FireMaterial": "/Game/SkyCity/FX/M_SkyFire",
          "RoarSound": "/Game/McGregor/Audio/S_MG_EngineRoar"}
out = {"stages": STAGES, "kv": KV}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1, default=str))


def ue_xyz(p):
    """site metres (x east, y north, z) -> Unreal cm (X north, Y east, Z)."""
    return (p[1] * 100.0, p[0] * 100.0, p[2] * 100.0)


def ue_dir(d):
    x, y, z = d[1], d[0], d[2]
    L = math.sqrt(x * x + y * y + z * z) or 1.0
    return (x / L, y / L, z / L)


def wind_ue():
    b = math.radians((ET.get("wind_from_bearing", 170.0) + 180.0) % 360.0)      # blowing toward
    s = ET.get("wind_mps", 5.0) * 100.0
    return (math.cos(b) * s, math.sin(b) * s, 0.0)                              # X = north, Y = east


def site_rows():
    rows = []
    for s in ET["sites"]:
        rows.append({"Id": s["id"], "Name": s["name"], "Kind": KIND.get(s["kind"], 0), "Nozzle": ue_xyz(s["nozzle"]), "NozzleDir": ue_dir(s["dir"]),
                     "Nozzles": int(s.get("nozzles", 1)), "NozzleSpread": s.get("nozzle_spread_m", 0.0) * 100.0,
                     "PlumeLength": s["plume_len_m"] * 100.0, "PlumeRadius": s["plume_radius_m"] * 100.0, "Exit": ue_xyz(s["exit"]),
                     "ExitDir": ue_dir(s["exit_dir"]), "ExitWidth": s["exit_width_m"] * 100.0, "Duration": s["duration_s"],
                     "SmokeScale": s.get("smoke_scale", 1.0), "FireScale": s.get("fire_scale", 1.0)})
    return rows


if STAGES == ["dry"]:
    print(json.dumps({"wind_cms": wind_ue(), "sites": site_rows()}, indent=1))
    raise SystemExit

import unreal  # noqa: E402  (after the dry run, which works outside the editor)

EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EAL = unreal.EditorAssetLibrary


def setp(obj, names, value, failed):
    for n in names:
        try:
            obj.set_editor_property(n, value)
            return n
        except Exception:
            continue
    failed.append(names[0])
    return None


def snake(n):
    s = n[1:] if n.startswith("b") and n[1:2].isupper() else n
    return "".join(("_" + c.lower()) if c.isupper() else c for c in s).lstrip("_")


def stage_map():
    if "map" in KV:
        unreal.EditorLoadingAndSavingUtils.load_map(KV["map"])
    out["map"] = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name()
    log("map", out["map"])


def stage_place():
    cls = getattr(unreal, "SkysterEngineTests", None)
    if cls is None:
        log("place", {"error": "unreal.SkysterEngineTests not found: rebuild the editor target with Source/SkyCity/SkysterEngineTests.* and restart"})
        return
    gone = 0
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags]:
            EAS.destroy_actor(a)
            gone += 1
    rows = site_rows()
    cx = sum(r["Exit"][0] for r in rows) / len(rows)
    cy = sum(r["Exit"][1] for r in rows) / len(rows)
    act = EAS.spawn_actor_from_class(cls, unreal.Vector(cx, cy, 3000.0), unreal.Rotator(0, 0, 0))
    act.set_actor_label("Engine_Tests")
    act.set_folder_path("McGregor/Site")
    act.tags = [TAG, "MG_Generated"]
    failed = []
    sites = []
    for r in rows:
        st = unreal.SkysterTestSite()
        for k, v in r.items():
            if isinstance(v, tuple):
                v = unreal.Vector(*v)
            elif k == "Id":
                v = unreal.Name(v)
            if setp(st, [snake(k), k], v, failed) is None:
                pass
        sites.append(st)
    setp(act, ["sites", "Sites"], sites, failed)
    night = "Night" in out.get("map", unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name())
    props = {"bEnabled": True, "Interval": float(ET["interval_s"]), "FirstDelay": float(ET["first_delay_s"]),
             "bFirstNearest": ET.get("first_site", "nearest") == "nearest", "bRandomOrder": bool(ET.get("random_order", False)),
             "WindVelocity": unreal.Vector(*wind_ue()), "ShakeRadius": ET["shake_radius_m"] * 100.0, "SoundRadius": ET["sound_radius_m"] * 100.0,
             "bNightLights": night}
    for k, v in props.items():
        setp(act, [snake(k), k], v, failed)
    missing = []
    for k, p in ASSETS.items():
        if EAL.does_asset_exist(p):
            setp(act, [snake(k), k], EAL.load_asset(p), failed)
        else:
            missing.append(p)
    log("place", {"actor": act.get_actor_label(), "replaced": gone, "sites": [r["Id"] for r in rows], "night_lights": night,
                  "wind_cms": wind_ue(), "props_failed": sorted(set(failed)), "assets_missing": missing})


def stage_save():
    log("save_level", unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level())
    log("save_dirty", unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True))


QUEUE = [("map", stage_map)] + [(s, globals()["stage_" + s]) for s in STAGES]
BUSY = [False]
T0 = time.time()
_h = None


def tick(dt):
    if BUSY[0]:
        return
    BUSY[0] = True
    try:
        if not QUEUE:
            unreal.unregister_slate_post_tick_callback(_h)
            log("done", round(time.time() - T0, 1))
            return
        name, fn = QUEUE.pop(0)
        fn()
        log("stage", name)
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        log("error", traceback.format_exc())
    finally:
        BUSY[0] = False


log("started", time.strftime("%H:%M:%S"))
_h = unreal.register_slate_post_tick_callback(tick)
