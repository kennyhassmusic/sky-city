"""Assemble the generated city's towers in Unreal from the facade kit (HISM).

Called by import_city_ue.py --buildings kit. Reads the layout from
kit_layout.py (every module instance, already in Unreal centimetres) and the
kit GLBs from blender_facade_kit.py. Each module-and-material group is one
HierarchicalInstancedStaticMeshComponent for the whole city (it culls its own
instances), except groups too big for one, which are cut into 300 m squares.
The components are packed into always-loaded sublevels
(<level>_Kit/<name>_Kit_NN) of at most SUBLEVEL_CAP instances, which keeps
each level file well under pr-guard's 25 MB warning (partition()).

Materials: walls, piers, corners and parapets take M_KitWall (city_materials_ue.kit_walls),
which lays the scan or pack tile out in metres along each instance's own axes,
so a scaled module never stretches its texture. Glass is the city's real glass,
lit rooms are emissive, blinds and curtains are the mesher's flats.

Shadows: glass casts none, so a hidden KIT_Wall component (kit_layout.SHADOW,
one box per tier inset behind the panes) casts each building's shadow.

Collision: the facade components have none. One hidden component of KIT_Wall
boxes (simple box collision, one per setback tier) blocks the car, so a wall
ride runs on a flat wall at the facade plane instead of catching every sill.

Run through import_city_ue.py, in the editor, PIE off.
"""
import json
import os

MESH_OF = {name: name for name in (
    "KIT_Wall", "KIT_Pier", "KIT_Corner", "KIT_Pane", "KIT_PaneCurtain", "KIT_Leaf", "KIT_RoofCap",
    "KIT_Sill", "KIT_Cornice", "KIT_Panel", "KIT_Decal", "KIT_DecalFloor",
    # Walkup kit (walkup.py).
    "KIT_Box", "KIT_Bracket", "KIT_ArchLintel", "KIT_Keystone", "KIT_Awning", "KIT_Dish")}
# Default slot bindings; each component overrides its own (see _material_for).
FIXED = {"M_Glass": "M_Glass", "M_Frame": "M_TrimDark", "M_Trim": "M_TrimDark", "M_Coping": "M_TrimDark"}
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


def _material_for(key, walls, materials, styled=None):
    """(slot name, material) overrides for one layout key ("<module>|<material>", see kit_layout)."""
    import style_kit
    styled = styled or {}
    module, _, variant = key.partition("|")
    kind, _, name = variant.partition(":")
    out = []
    if variant in ("collision", "shadow"):
        return out
    if variant == "roof":
        out.append(("M_Wall", materials.get("M_Roof")))
    elif kind in ("set", "frame", "trim"):
        mat = styled.get(variant)
        if mat is None and kind == "set":
            mat = walls.get("concrete")
        out.extend([("M_Wall", mat), ("M_Trim", mat)])
    elif kind == "cc0":
        out.append(("M_Wall", walls.get(name) or walls.get("concrete")))
    elif kind in ("lit", "dark") and module in ("KIT_Pane", "KIT_PaneCurtain"):
        frame, glass = style_kit.pane_look(name)
        out.append(("M_PaneBack", materials.get(BACK[kind])))
        out.append(("M_Frame", styled.get("frame:" + frame)))
        out.append(("M_Glass", styled.get("glass:" + glass) or materials.get("M_Glass")))
    elif module in ("KIT_Pane", "KIT_PaneCurtain"):
        out.append(("M_PaneBack", materials.get(BACK.get(variant, "M_Interior"))))
    elif kind == "sf":
        out.append(("M_Panel", styled.get(variant)))
    elif kind in ("decal", "gdecal"):
        out.append(("M_Decal", styled.get(variant)))
    elif module == "KIT_Leaf":
        out.append(("M_Leaf", materials.get(variant) or materials.get("M_Blind")))
    if module == "KIT_RoofCap" and kind == "trim":
        out.append(("M_Trim", styled.get(variant)))
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
    for item in items:
        x, y, z, yaw, sx, sy, sz = item[:7]
        out.append(unreal.Transform(location=unreal.Vector(x, y, z), rotation=unreal.Rotator(roll=0.0, pitch=0.0, yaw=yaw),
                                    scale=unreal.Vector(sx, sy, sz)))
    return out


TILE_CM = 30000.0     # a group too big for one component is cut into 300 m squares
SPLIT_OVER = 60000    # instances: groups above this are cut spatially
SUBLEVEL_CAP = 100000  # instances per sublevel (~140 bytes each in the level file, so ~14 MB)


def tiles_of(layout, tile_cm=TILE_CM):
    """(i, j) -> {key: items}: instances bucketed by origin."""
    out = {}
    for key, items in layout["groups"].items():
        for item in items:
            cell = (int(item[0] // tile_cm), int(item[1] // tile_cm))
            out.setdefault(cell, {}).setdefault(key, []).append(item)
    return out


def partition(layout, split_over=SPLIT_OVER, cap=SUBLEVEL_CAP, tile_cm=TILE_CM):
    """[ {key: items} ] per sublevel. Pure Python.

    One HISM per group culls its own instances (per cluster), so most groups
    stay whole: one component, one draw per section for the whole city. A
    group over split_over instances is cut into tile_cm squares. The pieces
    are then packed into sublevels of at most cap instances (largest first,
    first fit), because HISM keeps its instances in the level file and one
    file for the whole city would pass pr-guard's 100 MB limit.
    """
    pieces = []
    for key, items in sorted(layout["groups"].items()):
        if len(items) <= split_over:
            pieces.append((key, items))
            continue
        cells = {}
        for item in items:
            cells.setdefault((int(item[0] // tile_cm), int(item[1] // tile_cm)), []).append(item)
        pieces.extend((key, part) for _cell, part in sorted(cells.items()))
    pieces.sort(key=lambda piece: (-len(piece[1]), piece[0]))
    bins = []
    for key, items in pieces:
        for bin_ in bins:
            if bin_["count"] + len(items) <= cap:
                break
        else:
            bin_ = {"count": 0, "groups": {}}
            bins.append(bin_)
        bin_["groups"].setdefault(key, []).extend(items)
        bin_["count"] += len(items)
    return [bin_["groups"] for bin_ in bins]


def sublevel_path(level, index):
    base = level.rsplit("/", 1)[-1]
    return "%s_Kit/%s_Kit_%02d" % (level, base, index)


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


def build(unreal, layout, meshes, walls, materials, label, folder, level, styled=None):
    """One always-loaded sublevel per tile, each with a <label>_Kit actor of HISMs. Returns stats."""
    drop_sublevels(unreal, level)
    editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    stats = {"components": 0, "instances": 0, "sublevels": 0}
    for index, groups in enumerate(partition(layout)):
        streaming = unreal.EditorLevelUtils.create_new_streaming_level(
            unreal.LevelStreamingAlwaysLoaded, sublevel_path(level, index), False)
        if streaming is None:
            raise SystemExit("could not create kit sublevel %s" % sublevel_path(level, index))
        unreal.EditorLevelUtils.make_level_current(streaming)
        _actor_with(unreal, groups, meshes, walls, materials, "%s_Kit_%02d" % (label, index), folder, stats, styled)
        stats["sublevels"] += 1
    editor.save_all_dirty_levels()
    # New actors (the stage) go back into the persistent level.
    editor.set_current_level_by_name("PersistentLevel")
    _drop_unused_sublevels(unreal, level, {sublevel_path(level, index) for index in range(stats["sublevels"])})
    return stats


def _drop_unused_sublevels(unreal, level, keep):
    """Delete kit sublevel files a different layout left behind (none of the new ones)."""
    library = unreal.EditorAssetLibrary
    folder = level + "_Kit"
    left = []
    for path in library.list_assets(folder, recursive=False) if library.does_directory_exist(folder) else []:
        package = path.split(".")[0]
        if package not in keep and not library.delete_asset(package):
            left.append(package)
    if left:
        print("CITYGEN note: could not delete old kit sublevels:", ", ".join(left))


def _actor_with(unreal, groups, meshes, walls, materials, name, folder, stats, styled=None):
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
        for slot_name, mat in _material_for(key, walls, materials, styled):
            index = _slot_index(mesh, slot_name)
            if index >= 0:
                comp.set_material(index, mat)
        if key.endswith("|collision"):
            comp.set_collision_profile_name("BlockAll")
            comp.set_editor_property("visible", False)
            comp.set_editor_property("cast_shadow", False)
        elif key.endswith("|shadow"):
            # Shadow-only proxy (kit_layout.SHADOW): never drawn, never collides, only casts.
            comp.set_collision_profile_name("NoCollision")
            comp.set_editor_property("visible", False)
            comp.set_editor_property("hidden_in_game", True)
            comp.set_editor_property("cast_shadow", True)
            comp.set_editor_property("cast_hidden_shadow", True)
            comp.set_editor_property("component_tags", [unreal.Name("kit_shadow")])
        else:
            comp.set_collision_profile_name("NoCollision")
            comp.set_editor_property("cast_shadow", module not in ("KIT_Leaf", "KIT_Decal", "KIT_DecalFloor", "KIT_Panel"))
        tinted = len(items[0]) >= 10
        if tinted:
            comp.set_editor_property("num_custom_data_floats", 3)
        for start in range(0, len(items), CHUNK):
            comp.add_instances(_transforms(unreal, items[start:start + CHUNK]), False, False)
        if tinted:
            # The building's wall tint: M_KitWall multiplies its colour by custom data 0..2.
            last = len(items) - 1
            for index, item in enumerate(items):
                for k in range(3):
                    comp.set_custom_data_value(index, k, float(item[7 + k]), index == last and k == 2)
        stats["components"] += 1
        stats["instances"] += len(items)
    print("CITYGEN kit", name, sum(len(items) for items in groups.values()), "instances", flush=True)
    return actor


def load_layout(path):
    with open(path) as handle:
        return json.load(handle)
