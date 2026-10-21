"""The Chicago L in Sky City: places the layout computed offline by Scripts/rail/l_layout.py (Saved/Rail/l_layout.json)
with the Blender kit (SourceArt/Rail, Scripts/rail/blender_l_kit.py). All the thinking (routes, junctions, where each
column and stair may stand, stations, the terminal) happens offline against the street network; this script only
imports the kit and turns the layout's placements into instanced meshes.

20 Oct 2026 rebuild (Kenny: the L "seemed to stop randomly"): the old version paired OpenStreetMap tracks inside the
editor; the South Side line ended in mid-air south of Harrison (the mashup had dropped its clipped tracks), Tower 12 was a
pile of short lines, columns stood in travel lanes and crosswalks, and every piece faded out 900-1200 m from the camera
(HISM cull distances). Now:
  structure  L_BentColumn x2 + L_BentGirder per bent (each column at the curb or in a parking lane, girder scaled to
             fit), L_Span15/5 deck modules (J variants without outer walkways where two routes' decks overlap), L_Truss
             over the long spans across big junctions; never culled (Macs force LOD 1, so there are no LODs to fall to)
  stations   L_PlatSide30(_Stair) one-sided cantilevered platforms, L_StationStairs (+ L_StairBridge on wide streets),
             L_StationHouse, a parked train at every other station
  ends       L_Bumper + L_EndFence at the South Side line's terminal
  collision  columns, girders, deck modules, stairs and platforms block (complex collision); an invisible L_DeckSlab at
             top of rail along every chord gives the car a smooth floor on the deck
Stages: import (kit GLBs -> /Game/City/Rail), materials (kit slots -> MI_L_*), meshes (Nanite off, complex collision),
        axes (checks the kit frame: forward = +Y, left platform = +X), place, save
Run in the editor: py Scripts/roads/build_l_ue.py [import] [materials] [meshes] [axes] [place] [save]
(no args = all). Rerun python3 -I Scripts/rail/l_layout.py first whenever Saved/Roads/roadnet.json changes.
Writes Saved/MCPScripts/out_l.json.
"""
import glob, json, math, sys, time, traceback, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_l.json"
LAYOUT = ROOT + "/Saved/Rail/l_layout.json"
DIR = "/Game/City/Rail"
TAG = "SC_TheL"
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
STAGES = sys.argv[1:] or ["import", "materials", "meshes", "axes", "place", "save"]
out = {"stages": STAGES}

# per kit piece: (collision, cast shadow, cull start/end cm (0 = never), hidden in game)
PIECES = {
    "L_BentColumn": ("block", True, 0, False),
    "L_BentGirder": ("block", True, 0, False),
    "L_Span15": ("block", True, 0, False),
    "L_Span5": ("block", True, 0, False),
    "L_Span15J": ("block", True, 0, False),
    "L_Span5J": ("block", True, 0, False),
    "L_Truss": ("block", True, 0, False),
    "L_DeckSlab": ("block", False, 0, True),
    "L_PlatSide30": ("block", True, 250000, False),
    "L_PlatSide30_Stair": ("block", True, 250000, False),
    "L_StationStairs": ("block", True, 250000, False),
    "L_StairBridge": ("block", True, 250000, False),
    "L_StationHouse": ("block", True, 200000, False),
    "L_TrainCar": ("block", True, 180000, False),
    "L_Bumper": ("block", True, 150000, False),
    "L_EndFence": ("block", True, 150000, False),
}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def import_files(files, dest):
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", dest)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        tasks.append(t)
    AT.import_asset_tasks(tasks)
    res = []
    for t in tasks:
        res += list(t.get_editor_property("imported_object_paths") or [])
    return res


def stage_import():
    files = sorted(glob.glob(ROOT + "/SourceArt/Rail/meshes/*.glb"))
    log("import", len(import_files(files, DIR)))


_MESH = {}


def mesh(name):
    if name in _MESH:
        return _MESH[name]
    found = None
    for p in EAL.list_assets(DIR, recursive=True):
        if p.split("/")[-1].split(".")[0] == name and EAL.find_asset_data(p).asset_class_path.asset_name == "StaticMesh":
            found = EAL.load_asset(p.split(".")[0])
            break
    _MESH[name] = found
    return found


def flat_mi(name, tint, rough, metal=0.0, glow=0.0):
    path = f"{DIR}/Materials/{name}"
    if EAL.does_asset_exist(path):
        mi = EAL.load_asset(path)
    else:
        mi = AT.create_asset(name, f"{DIR}/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mi.set_editor_property("parent", EAL.load_asset("/Game/City/Street/Materials/M_StreetProp"))
    MEL.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(*tint, 1))
    MEL.set_material_instance_scalar_parameter_value(mi, "Roughness", rough)
    MEL.set_material_instance_scalar_parameter_value(mi, "Metallic", metal)
    if glow:
        MEL.set_material_instance_vector_parameter_value(mi, "EmissiveColor", unreal.LinearColor(*tint, 1))
        MEL.set_material_instance_scalar_parameter_value(mi, "EmissiveStrength", glow)
    MEL.update_material_instance(mi)
    EAL.save_loaded_asset(mi)
    return mi


def stage_materials():
    slots = {
        "M_LSteel": flat_mi("MI_L_Steel", (0.13, 0.16, 0.14), 0.6, 0.4),
        "M_LSteelRust": flat_mi("MI_L_SteelRust", (0.22, 0.13, 0.08), 0.8, 0.2),
        "M_Rail": flat_mi("MI_L_Rail", (0.45, 0.45, 0.46), 0.35, 0.9),
        "M_Tie": flat_mi("MI_L_Tie", (0.09, 0.07, 0.05), 0.9),
        "M_Concrete": flat_mi("MI_L_Concrete", (0.45, 0.44, 0.42), 0.85),
        "M_Grating": flat_mi("MI_L_Grating", (0.2, 0.2, 0.21), 0.7, 0.6),
        "M_Glass": flat_mi("MI_L_Glass", (0.05, 0.07, 0.08), 0.1, 0.3),
        "M_Canopy": flat_mi("MI_L_Canopy", (0.14, 0.17, 0.15), 0.6, 0.3),
        "M_SignPanel": flat_mi("MI_L_SignPanel", (0.02, 0.02, 0.025), 0.4, 0.0, 0.0),
        "M_Light": flat_mi("MI_L_Light", (1.0, 0.95, 0.85), 0.3, 0.0, 6.0),
        "M_Paint_Yellow": flat_mi("MI_L_PaintYellow", (0.85, 0.65, 0.05), 0.5),
        "M_Insulator": flat_mi("MI_L_Insulator", (0.6, 0.55, 0.45), 0.5),
        "M_LineStripe": flat_mi("MI_L_LineStripe", (0.75, 0.05, 0.05), 0.4, 0.0, 2.0),
        "M_Stainless": flat_mi("MI_L_Stainless", (0.6, 0.61, 0.62), 0.3, 1.0),
        "M_DestSign": flat_mi("MI_L_DestSign", (1.0, 0.55, 0.1), 0.4, 0.0, 3.0),
    }
    n = 0
    for p in EAL.list_assets(DIR, recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name != "StaticMesh":
            continue
        sm = EAL.load_asset(p.split(".")[0])
        for i, sml in enumerate(sm.get_editor_property("static_materials")):
            base = str(sml.get_editor_property("material_slot_name")).split(".")[0]
            if base in slots:
                sm.set_material(i, slots[base])
                n += 1
        EAL.save_loaded_asset(sm)
    log("materials", n)


def stage_meshes():
    """Macs run SM5 (no Nanite: a Nanite mesh would draw its coarse fallback) and force LOD 1 (Config/Mac/MacEngine.ini), so:
    Nanite off, no LODs, per-poly collision (the car drives on the slab, hits girders, rails, handrails and stairs)."""
    res = {}
    for name in PIECES:
        sm = mesh(name)
        if sm is None:
            res[name] = "missing"
            continue
        ns = sm.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", False)
        sm.set_editor_property("nanite_settings", ns)
        bs = sm.get_editor_property("body_setup")
        if bs:
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        EAL.save_loaded_asset(sm)
        res[name] = "ok"
    log("meshes", res)


def stage_axes():
    """The kit frame in Unreal: run direction (Blender -Y) = local +Y, Blender +X = local +X (the left platform)."""
    res = {}
    for name in ("L_Span15", "L_StationStairs", "L_BentGirder", "L_BentColumn", "L_PlatSide30", "L_StairBridge", "L_Bumper"):
        sm = mesh(name)
        if sm:
            bb = sm.get_bounding_box()
            res[name] = [round(v) for v in (bb.min.x, bb.max.x, bb.min.y, bb.max.y, bb.min.z, bb.max.z)]
    log("axes", res)
    st = res.get("L_StationStairs")
    sp = res.get("L_Span15")
    ok = bool(st and sp and st[0] > 600 and st[1] < 1050 and sp[3] > 1400 and sp[2] > -10)
    log("axes_ok", ok)
    if not ok:
        raise RuntimeError("kit frame is not forward=+Y / left=+X; fix xf() before placing")


def xf(row):
    """Layout row [ox, oy, fx, fy, z, sx, sy, sz] (plan metres) -> Unreal transform (kit forward = local +Y)."""
    ox, oy, fx, fy, z, sx, sy, sz = row
    yaw = math.degrees(math.atan2(fx, fy)) - 90.0        # plan (x east, y north) -> Unreal yaw of +Y
    return unreal.Transform(unreal.Vector(oy * 100.0, ox * 100.0, z * 100.0), unreal.Rotator(roll=0, pitch=0, yaw=yaw), unreal.Vector(sx, sy, sz))


def add_component(actor, cls):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    BFL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=cls, blueprint_context=None)
    h, fail = sds.add_new_subobject(params)
    return BFL.get_object(BFL.get_data(h))


def instanced(label, sm, xfs, collide, shadows, cull, hidden):
    if not xfs or sm is None:
        return 0
    act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    act.set_actor_label(label)
    act.set_folder_path("City/TheL")
    act.tags = [TAG, "City_Generated"]
    act.set_editor_property("is_spatially_loaded", False)
    c = add_component(act, unreal.HierarchicalInstancedStaticMeshComponent)
    c.set_static_mesh(sm)
    c.set_editor_property("cast_shadow", shadows)
    c.set_collision_profile_name("BlockAll" if collide == "block" else "NoCollision")
    c.set_cull_distances(int(cull * 0.85), int(cull))
    if hidden:
        c.set_editor_property("visible", False)
        c.set_editor_property("hidden_in_game", True)
    c.add_instances(xfs, False, True)
    return len(xfs)


def stage_place():
    lay = json.load(open(LAYOUT))
    removed = 0
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags] or a.get_actor_label() == "TheL":
            EAS.destroy_actor(a)
            removed += 1
    counts = {"removed_old": removed}
    for name, rows in sorted(lay["instances"].items()):
        coll, shadows, cull, hidden = PIECES.get(name, ("block", True, 0, False))
        sm = mesh(name)
        if sm is None:
            counts[name] = "MISSING MESH"
            continue
        counts[name] = instanced(name.replace("L_", "L_") + "s", sm, [xf(r) for r in rows], coll, shadows, cull, hidden)
    counts["routes"] = {k: v["len"] for k, v in lay["routes"].items()}
    counts["stations"] = [s["name"] for s in lay["stations"]]
    log("place", counts)


def stage_save():
    ok = unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    log("save", ok)


QUEUE = [(s, globals()["stage_" + s]) for s in STAGES]
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


_h = unreal.register_slate_post_tick_callback(tick)
