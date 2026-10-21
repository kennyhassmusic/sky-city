"""Boost rings for Sky City: a glowing ring course (Saved/Mashup/rings_v1.json) that fires the Roadster's RingBoost.

Stages (each on the next editor tick; poll Saved/MCPScripts/out_rings.json):
    py .../boost_rings.py assets   # SM_BoostRing (torus), M_BoostRing (emissive), BP_BoostRing (mesh + trigger sphere)
    py .../boost_rings.py place    # one BP_BoostRing per ring in the course (replaces earlier ones)
The ring's overlap logic (cast to BP_RoadsterFlyer -> RingBoost) is written with the MCP BlueprintTools DSL.
"""
import json, sys, traceback
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
OUT = ROOT + "/Saved/MCPScripts/out_rings.json"
MESH_DIR = "/Game/City/Meshes"
BP_DIR = "/Game/SkyCity/Blueprints"
EAL = unreal.EditorAssetLibrary
TAG = "SC_BoostRing"
out = {}


def emissive_material(name, color, strength):
    path = f"{MESH_DIR}/{name}"
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, MESH_DIR, unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    MEL = unreal.MaterialEditingLibrary
    c = MEL.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -500, 0)
    c.set_editor_property("constant", unreal.LinearColor(color[0] * strength, color[1] * strength, color[2] * strength, 1))
    MEL.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(mat)
    EAL.save_loaded_asset(mat)
    return mat


def ring_mesh(mat):
    path = f"{MESH_DIR}/SM_BoostRing"
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)
    dm = unreal.DynamicMesh()
    opts = unreal.GeometryScriptPrimitiveOptions()
    # torus axis along +X, so the ring faces the direction the actor points
    xf = unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(roll=0, pitch=90, yaw=0), unreal.Vector(1, 1, 1))
    unreal.GeometryScript_Primitives.append_torus(dm, opts, xf, unreal.GeometryScriptRevolveOptions(),
                                                  major_radius=1000.0, minor_radius=110.0, major_steps=48, minor_steps=12)
    o = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
    o.set_editor_property("enable_collision", False)
    sm, _ = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, o)
    sm.set_material(0, mat)
    EAL.save_loaded_asset(sm)
    return sm


def add_component(bp, cls, name, parent=None):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    BFL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_blueprint(bp)
    for h in handles:
        o = BFL.get_object(BFL.get_data(h))
        if o and o.get_name().startswith(name):
            return h, o
    h, _ = sds.add_new_subobject(unreal.AddNewSubobjectParams(parent_handle=parent or handles[0], new_class=cls, blueprint_context=bp))
    sds.rename_subobject(h, unreal.Text(name))
    return h, BFL.get_object(BFL.get_data(h))


def stage_assets():
    mat = emissive_material("M_BoostRing", (1.0, 0.42, 0.06), 9.0)
    sm = ring_mesh(mat)
    path = f"{BP_DIR}/BP_BoostRing"
    if EAL.does_asset_exist(path):
        bp = EAL.load_asset(path)
    else:
        f = unreal.BlueprintFactory()
        f.set_editor_property("parent_class", unreal.Actor)
        bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset("BP_BoostRing", BP_DIR, unreal.Blueprint, f)
    trig_h, trig = add_component(bp, unreal.SphereComponent, "Trigger")
    trig.set_editor_property("sphere_radius", 950.0)
    trig.set_collision_profile_name("OverlapAllDynamic")
    trig.set_editor_property("generate_overlap_events", True)
    trig.set_editor_property("hidden_in_game", True)
    ring_h, ring = add_component(bp, unreal.StaticMeshComponent, "Ring", trig_h)
    ring.set_editor_property("static_mesh", sm)
    ring.set_collision_profile_name("NoCollision")
    ring.set_editor_property("cast_shadow", False)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    EAL.save_loaded_asset(bp)
    out["bp"] = bp.get_path_name()
    out["mesh"] = sm.get_path_name()


def stage_place():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    old = [a for a in eas.get_all_level_actors() if TAG in [str(t) for t in a.tags]]
    eas.destroy_actors(old)
    cls = EAL.load_blueprint_class(f"{BP_DIR}/BP_BoostRing")
    rings = json.load(open(ROOT + "/Saved/Mashup/rings_v1.json"))["rings"]
    for i, (x, y, z, heading, climb) in enumerate(rings):
        loc = unreal.Vector(y * 100.0, x * 100.0, z * 100.0)
        rot = unreal.Rotator(roll=0, pitch=climb, yaw=90.0 - heading)
        a = eas.spawn_actor_from_class(cls, loc, rot)
        a.set_actor_label(f"BoostRing_{i:02d}")
        a.tags = [TAG, "City_Generated"]
        a.set_folder_path("City/BoostRings")
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    out["removed"] = len(old)
    out["placed"] = len(rings)


STAGES = {"assets": stage_assets, "place": stage_place}


def run(stage):
    try:
        out["stage"] = stage
        STAGES[stage]()
        out["ok"] = True
    except Exception:
        out["error"] = traceback.format_exc()
    open(OUT, "w").write(json.dumps(out, indent=1))


_stage = sys.argv[1] if len(sys.argv) > 1 else "assets"
open(OUT, "w").write(json.dumps({"stage": _stage, "running": True}))
_h = None


def _tick(dt):
    unreal.unregister_slate_post_tick_callback(_h)
    run(_stage)


_h = unreal.register_slate_post_tick_callback(_tick)
