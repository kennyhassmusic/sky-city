"""Assemble the generated city's towers in Unreal from the facade kit (HISM).

Called by import_city_ue.py --buildings kit. Reads the layout from
kit_layout.py (every module instance, already in Unreal centimetres) and the
seven kit GLBs from blender_facade_kit.py. The city is cut into 400 m tiles;
each tile is an always-loaded sublevel (<level>_Kit/<name>_Kit_<i>_<j>) with
one actor holding one HierarchicalInstancedStaticMeshComponent per module and
material (about 25). Each component draws all of its instances with one draw
per material section. Tiles keep each level file well under pr-guard's 100 MB.

Materials: walls, piers, corners and parapets take M_KitWall (city_materials_ue.kit_walls),
which lays the scan or pack tile out in metres along each instance's own axes,
so a scaled module never stretches its texture. Glass is the city's real glass,
lit rooms are emissive, blinds and curtains are the mesher's flats.

Collision: the facade components have none. One hidden component of KIT_Wall
boxes (simple box collision, one per setback tier) blocks the car, so a wall
ride runs on a flat wall at the facade plane instead of catching every sill.

Run through import_city_ue.py, in the editor, PIE off.
"""
import json
import os

MESH_OF = {
    "KIT_Wall": "KIT_Wall", "KIT_Pier": "KIT_Pier", "KIT_Corner": "KIT_Corner", "KIT_Pane": "KIT_Pane",
    "KIT_PaneCurtain": "KIT_PaneCurtain", "KIT_Leaf": "KIT_Leaf", "KIT_RoofCap": "KIT_RoofCap",
}
# Fixed slot bindings; M_Wall, M_PaneBack and M_Leaf change per component.
FIXED = {"M_Glass": "M_Glass", "M_Frame": "M_TrimDark", "M_Coping": "M_TrimDark"}
BACK = {"lit": "M_InteriorLit", "dark": "M_Interior"}
CHUNK = 20000


def import_kit(unreal, kit_dir, dest):
    """Import the kit GLBs into dest; returns name -> StaticMesh."""
    library = unreal.EditorAssetLibrary
    assets = unreal.AssetToolsHelpers.get_asset_tools()
    if not library.does_directory_exist(dest):
        library.make_directory(dest)
    meshes = {}
    for name in sorted(set(MESH_OF.values())):
        path = os.path.join(kit_dir, name + ".glb")
        if not os.path.isfile(path):
            raise SystemExit("kit module missing: %s (run Scripts/city/blender_facade_kit.py)" % path)
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", path)
        task.set_editor_property("destination_path", dest)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", True)
        assets.import_asset_tasks([task])
        for asset_path in list(task.get_editor_property("imported_object_paths") or []):
            asset = library.load_asset(asset_path.split(".")[0])
            if isinstance(asset, unreal.StaticMesh):
                meshes[name] = asset
    return meshes


def prepare(unreal, meshes, materials, drop_gltf_materials):
    """Nanite off, fixed slots bound, box collision on KIT_Wall only."""
    import city_materials_ue
    subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    for name, mesh in meshes.items():
        settings = mesh.get_editor_property("nanite_settings")
        if settings.get_editor_property("enabled"):
            settings.set_editor_property("enabled", False)
            mesh.set_editor_property("nanite_settings", settings)
        for index, slot in enumerate(mesh.get_editor_property("static_materials")):
            slot_name = city_materials_ue.base_slot(slot.get_editor_property("material_slot_name"))
            fixed = materials.get(FIXED.get(slot_name, ""))
            if fixed is not None:
                mesh.set_material(index, fixed)
        subsystem.remove_collisions(mesh)
        if name == "KIT_Wall":
            subsystem.add_simple_collisions(mesh, unreal.ScriptCollisionShapeType.BOX)
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
        drop_gltf_materials(unreal, mesh.get_path_name().split(".")[0])


def _slot_index(mesh, slot_name):
    import city_materials_ue
    for index, slot in enumerate(mesh.get_editor_property("static_materials")):
        if city_materials_ue.base_slot(slot.get_editor_property("material_slot_name")) == slot_name:
            return index
    return -1


def _material_for(key, walls, materials):
    """(slot name, material) overrides for one layout key."""
    module, _, variant = key.partition("|")
    out = []
    if module in ("KIT_Wall", "KIT_Pier", "KIT_Corner", "KIT_RoofCap"):
        if variant == "roof":
            out.append(("M_Wall", materials.get("M_Roof")))
        elif variant != "collision":
            out.append(("M_Wall", walls.get(variant) or walls.get("concrete")))
    elif module in ("KIT_Pane", "KIT_PaneCurtain"):
        out.append(("M_PaneBack", materials.get(BACK.get(variant, "M_Interior"))))
    elif module == "KIT_Leaf":
        out.append(("M_Leaf", materials.get(variant) or materials.get("M_Blind")))
    return [(slot, mat) for slot, mat in out if mat is not None]


def _subobject(unreal, actor, cls):
    """A new instance component on actor, saved with the level."""
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=cls, blueprint_context=None)
    handle, fail = sds.add_new_subobject(params)
    if not fail.is_empty():
        raise RuntimeError("could not add %s: %s" % (cls.get_name(), fail))
    data = unreal.SubobjectDataBlueprintFunctionLibrary.get_data(handle)
    return unreal.SubobjectDataBlueprintFunctionLibrary.get_object(data)


def _transforms(unreal, items):
    out = []
    for x, y, z, yaw, sx, sy, sz in items:
        out.append(unreal.Transform(location=unreal.Vector(x, y, z), rotation=unreal.Rotator(roll=0.0, pitch=0.0, yaw=yaw),
                                    scale=unreal.Vector(sx, sy, sz)))
    return out


TILE_CM = 40000.0  # 400 m: about 60k instances and an ~8 MB sublevel per tile in the Loop


def tiles_of(layout, tile_cm=TILE_CM):
    """(i, j) -> {key: items}: instances bucketed by origin. HISM data lives in the
    level file (~140 bytes an instance), so one level for the whole city would
    pass pr-guard's 100 MB per-file limit; each tile is its own sublevel."""
    out = {}
    for key, items in layout["groups"].items():
        for item in items:
            cell = (int(item[0] // tile_cm), int(item[1] // tile_cm))
            out.setdefault(cell, {}).setdefault(key, []).append(item)
    return out


def sublevel_path(level, cell):
    base = level.rsplit("/", 1)[-1]
    return "%s_Kit/%s_Kit_%d_%d" % (level, base, cell[0], cell[1])


def drop_sublevels(unreal, level):
    """Remove the kit sublevels an earlier run added to this level."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    prefix = level + "_Kit/"
    gone = []
    for sub in unreal.EditorLevelUtils.get_levels(world):
        name = sub.get_outermost().get_name()
        if name.startswith(prefix):
            unreal.EditorLevelUtils.remove_level_from_world(sub)
            gone.append(name)
    library = unreal.EditorAssetLibrary
    if library.does_directory_exist(level + "_Kit"):
        library.delete_directory(level + "_Kit")
    if gone:
        print("CITYGEN removed kit sublevels:", len(gone))


def build(unreal, layout, meshes, walls, materials, label, folder, level):
    """One always-loaded sublevel per tile, each with a <label>_Kit actor of HISMs. Returns stats."""
    drop_sublevels(unreal, level)
    editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    stats = {"components": 0, "instances": 0, "sublevels": 0}
    for cell, groups in sorted(tiles_of(layout).items()):
        streaming = unreal.EditorLevelUtils.create_new_streaming_level(
            unreal.LevelStreamingAlwaysLoaded, sublevel_path(level, cell), False)
        if streaming is None:
            raise SystemExit("could not create kit sublevel %s" % sublevel_path(level, cell))
        unreal.EditorLevelUtils.make_level_current(streaming)
        _actor_with(unreal, groups, meshes, walls, materials, "%s_Kit_%d_%d" % (label, cell[0], cell[1]), folder, stats)
        stats["sublevels"] += 1
    editor.save_all_dirty_levels()
    # New actors (the stage) go back into the persistent level.
    editor.set_current_level_by_name("PersistentLevel")
    return stats


def _actor_with(unreal, groups, meshes, walls, materials, name, folder, stats):
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor = sub.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    actor.set_actor_label(name)
    actor.set_folder_path(folder)
    _subobject(unreal, actor, unreal.SceneComponent)
    for key, items in sorted(groups.items()):
        module = key.split("|")[0]
        mesh = meshes.get(MESH_OF.get(module))
        if mesh is None or not items:
            continue
        comp = _subobject(unreal, actor, unreal.HierarchicalInstancedStaticMeshComponent)
        comp.set_editor_property("static_mesh", mesh)
        for slot_name, mat in _material_for(key, walls, materials):
            index = _slot_index(mesh, slot_name)
            if index >= 0:
                comp.set_material(index, mat)
        if key.endswith("|collision"):
            comp.set_collision_profile_name("BlockAll")
            comp.set_editor_property("visible", False)
            comp.set_editor_property("cast_shadow", False)
        else:
            comp.set_collision_profile_name("NoCollision")
            comp.set_editor_property("cast_shadow", module not in ("KIT_Leaf",))
        for start in range(0, len(items), CHUNK):
            comp.add_instances(_transforms(unreal, items[start:start + CHUNK]), False, False)
        stats["components"] += 1
        stats["instances"] += len(items)
    print("CITYGEN kit", name, sum(len(items) for items in groups.values()), "instances", flush=True)
    return actor


def load_layout(path):
    with open(path) as handle:
        return json.load(handle)
