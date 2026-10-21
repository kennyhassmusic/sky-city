"""Make Sky City playable: a flyable Roadster pawn, a game mode that uses it, and a start point.

Stages (run one at a time, each on the next editor tick; poll Saved/MCPScripts/out.json):
    py .../make_pawn.py merge      # load the old map, merge the imported Roadster parts into SM_Roadster_Merged (faces +X)
    py .../make_pawn.py pawn       # BP_RoadsterFlyer (DefaultPawn child: Xbox pad / WASD flying) + BP_SkyCityGameMode
    py .../make_pawn.py setup      # back in the city map: player start on the Congress Ave bridge, game mode, default maps
"""
import json, math, sys, traceback
import unreal

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
OUT = ROOT + "/Saved/MCPScripts/out.json"
CITY_MAP = "/Game/Maps/SkyCityMashup"
OLD_MAP = "/Game/Maps/SkyCity"
VEH = "/Game/Vehicles/Roadster"
BP_DIR = "/Game/SkyCity/Blueprints"
EAL = unreal.EditorAssetLibrary
out = {}


def les():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def eas():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def current_map():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name().split(".")[0]


def load_all_actors():
    """World Partition maps open with their actors unloaded; load every one (these maps are small)."""
    try:
        WPL = unreal.WorldPartitionBlueprintLibrary
        descs = WPL.get_actor_descs()
        guids = [d.get_editor_property("guid") for d in descs]
        if guids:
            WPL.load_actors(guids)
        out["actors_loaded"] = len(guids)
    except Exception as e:
        out["load_all_error"] = str(e)


def stage_merge():
    if current_map() != OLD_MAP:
        les().load_level(OLD_MAP)
    load_all_actors()
    acts = eas().get_all_level_actors()
    root = next(a for a in acts if a.get_name().startswith("roadster_master_scene"))
    keep_loc, keep_rot = root.get_actor_location(), root.get_actor_rotation()
    root.set_actor_location_and_rotation(unreal.Vector(0, 0, 0), unreal.Rotator(roll=0, pitch=0, yaw=-90), False, True)
    parts = [a for a in eas().get_all_level_actors() if isinstance(a, unreal.StaticMeshActor) and a.get_name().startswith("roadster_master_")]
    opts = unreal.MergeStaticMeshActorsOptions()
    opts.set_editor_property("destroy_source_actors", False)
    opts.set_editor_property("spawn_merged_actor", False)
    opts.set_editor_property("base_package_name", f"{VEH}/SM_Roadster_Merged")
    ms = opts.get_editor_property("mesh_merging_settings")
    # 5.8 replaced bPivotPointAtZero with a pivot-type enum: pick its world-origin value
    pivot_enum = next(getattr(unreal, n) for n in dir(unreal) if "MergePivot" in n)
    zero = next((getattr(pivot_enum, m) for m in dir(pivot_enum) if m.isupper() and ("ZERO" in m or "ORIGIN" in m)), None)
    out["pivot_enum"] = [m for m in dir(pivot_enum) if m.isupper()]
    if zero is not None:
        ms.set_editor_property("pivot_type", zero)
    ms.set_editor_property("merge_materials", False)
    opts.set_editor_property("mesh_merging_settings", ms)
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    res = sub.merge_static_mesh_actors(parts, opts)
    root.set_actor_location_and_rotation(keep_loc, keep_rot, False, True)
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    out["parts_merged"] = len(parts)
    out["merge_result"] = str(res)
    found = [str(p) for p in EAL.list_assets(VEH, recursive=False)]
    out["vehicle_assets"] = found


def find_merged():
    for p in EAL.list_assets(VEH, recursive=True):
        if "SM_Roadster_Merged" in str(p):
            return EAL.load_asset(str(p).split(".")[0])
    return None


def make_bp(name, parent):
    path = f"{BP_DIR}/{name}"
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)
    f = unreal.BlueprintFactory()
    f.set_editor_property("parent_class", parent)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, BP_DIR, unreal.Blueprint, f)


def add_component(bp, cls, name, parent_handle=None):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = sds.k2_gather_subobject_data_for_blueprint(bp)
    BFL = unreal.SubobjectDataBlueprintFunctionLibrary
    for h in handles:   # already there?
        o = BFL.get_object(BFL.get_data(h))
        if o and o.get_name().startswith(name):
            return h, o
    parent = parent_handle or handles[0]
    params = unreal.AddNewSubobjectParams(parent_handle=parent, new_class=cls, blueprint_context=bp)
    h, fail = sds.add_new_subobject(params)
    sds.rename_subobject(h, unreal.Text(name))
    return h, BFL.get_object(BFL.get_data(h))


def stage_pawn():
    EAL.make_directory(BP_DIR)
    car = find_merged()
    out["merged_mesh"] = car.get_path_name() if car else None
    bp = make_bp("BP_RoadsterFlyer", unreal.DefaultPawn)
    arm_h, arm = add_component(bp, unreal.SpringArmComponent, "ChaseArm")
    cam_h, cam = add_component(bp, unreal.CameraComponent, "ChaseCamera", arm_h)
    arm.set_editor_property("target_arm_length", 950.0)
    arm.set_editor_property("socket_offset", unreal.Vector(0, 0, 220))
    arm.set_editor_property("use_pawn_control_rotation", True)
    arm.set_editor_property("enable_camera_lag", True)
    arm.set_editor_property("camera_lag_speed", 9.0)
    arm.set_editor_property("do_collision_test", True)
    cam.set_editor_property("field_of_view", 80.0)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    cdo = unreal.get_default_object(bp.generated_class())
    mesh = cdo.get_editor_property("mesh_component")
    if car:
        mesh.set_editor_property("static_mesh", car)
    mesh.set_editor_property("relative_location", unreal.Vector(0, 0, -60))
    mesh.set_editor_property("relative_scale3d", unreal.Vector(1, 1, 1))
    mesh.set_editor_property("hidden_in_game", False)
    mesh.set_collision_profile_name("NoCollision")
    col = cdo.get_editor_property("collision_component")
    col.set_editor_property("sphere_radius", 140.0)
    mv = cdo.get_editor_property("movement_component")
    for k, v in (("max_speed", 9000.0), ("acceleration", 9000.0), ("deceleration", 6000.0), ("turning_boost", 6.0)):
        try:
            mv.set_editor_property(k, v)
        except Exception as e:
            out.setdefault("movement_warnings", []).append(f"{k}: {e}")
    for k, v in (("base_turn_rate", 70.0), ("base_look_up_rate", 55.0)):
        try:
            cdo.set_editor_property(k, v)
        except Exception:
            pass   # read-only on DefaultPawn in 5.8; its defaults are fine
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    EAL.save_loaded_asset(bp)
    gm = make_bp("BP_SkyCityGameMode", unreal.GameModeBase)
    unreal.BlueprintEditorLibrary.compile_blueprint(gm)
    gcdo = unreal.get_default_object(gm.generated_class())
    gcdo.set_editor_property("default_pawn_class", bp.generated_class())
    unreal.BlueprintEditorLibrary.compile_blueprint(gm)
    EAL.save_loaded_asset(gm)
    out["pawn"] = bp.get_path_name()
    out["game_mode"] = gm.get_path_name()


def stage_setup():
    if current_map() != CITY_MAP:
        les().load_level(CITY_MAP)
    load_all_actors()
    plan = json.load(open(ROOT + "/Saved/Mashup/plan_v3.json"))
    # start on the Congress Avenue bridge, looking downstream toward the Loop skyline
    br = next((l["pos"] for l in plan["landmarks"] if l["name"] == "Congress Ave Bridge"), None)
    if br is None:
        br = [-1500, 300]
    loop = next((l["pos"] for l in plan["landmarks"] if l["name"] == "Willis Tower"), [-500, -1000])
    X, Y = br[1] * 100, br[0] * 100
    tx, ty = loop[1] * 100, loop[0] * 100
    yaw = math.degrees(math.atan2(ty - Y, tx - X))
    starts = [a for a in eas().get_all_level_actors() if isinstance(a, unreal.PlayerStart)]
    ps = starts[0] if starts else eas().spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(X, Y, 400), unreal.Rotator(0, 0, 0))
    ps.set_actor_location_and_rotation(unreal.Vector(X, Y, 400), unreal.Rotator(roll=0, pitch=0, yaw=yaw), False, True)
    gm = EAL.load_asset(f"{BP_DIR}/BP_SkyCityGameMode")
    ws = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_world_settings()
    ws.set_editor_property("default_game_mode", gm.generated_class())
    les().save_current_level()
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    out["player_start"] = [round(X), round(Y), round(yaw, 1)]


STAGES = {"merge": stage_merge, "pawn": stage_pawn, "setup": stage_setup}


def run(stage):
    try:
        out["stage"] = stage
        STAGES[stage]()
        out["ok"] = True
    except Exception:
        out["error"] = traceback.format_exc()
    open(OUT, "w").write(json.dumps(out, indent=1))


_stage = sys.argv[1] if len(sys.argv) > 1 else "pawn"
open(OUT, "w").write(json.dumps({"stage": _stage, "running": True}))
_h = None


def _tick(dt):
    unreal.unregister_slate_post_tick_callback(_h)
    run(_stage)


_h = unreal.register_slate_post_tick_callback(_tick)
