"""Land cover on a generated-city drive level: the generator's hero scatter (trees, shrubs, logs) and its fields,
with the starter pack's own meshes and ground materials (/Game/LandCover, building-types branch assets/starter-pack,
copied into this project's Content/LandCover by run_gencity.sh; not committed here).

Reads the land-cover stage's output in the building-types worktree (Saved/CityGen/pipeline/seed-<N>/landcover/):
  hero.json        one instance per tree/shrub/log: slot, plan mm, yaw (0.1 degree), scale (1/1000)
  landcover.json   fields: polygon (plan m), crop, slot, stage
and adds to the open level, in the outliner folder GenCity_<Name>/LandCover (replacing an earlier run's):
  - one HISM per hero slot (SM_<slot>); a slot the pack has no mesh for is counted and skipped
  - one flat ground slab per field (its bounding rectangle, 3 cm above the city's ground slab) with the pack's
    ground material for its crop (MI_GND_FieldRows, Pasture, Stubble ...); no crop meshes (a field is ~20,000 m²)
Trees and logs block the car with the pack's own collision (not the chase camera); shrubs don't; field slabs block
(the car drives on them).

  py Scripts/gencity/landcover_gencity_ue.py        (after import_gencity_ue.py, in the same editor or a new one)
Env/args: GEN_BT (building-types worktree), GEN_SEED (7). Writes Saved/GenCity/landcover_status_<region>.json.
"""
import json
import os
import sys
import traceback

import unreal

PACK = "/Game/LandCover"
# field crop -> ground material (/Game/LandCover/Materials/Ground)
FIELD_GROUND = {"corn": "MI_GND_FieldRows", "soy": "MI_GND_FieldRows", "wheat": "MI_GND_Stubble",
                "pasture": "MI_GND_Pasture", "hay": "MI_GND_GrassMeadow", "orchard": "MI_GND_GrassMeadow",
                "fallow": "MI_GND_SoilDry"}
FIELD_DEFAULT = "MI_GND_FieldRows"
# Hero slots the pack has no tree for yet (not built: no whole-tree reference photos), drawn with the nearest
# pack species of the same size and listed in the status as stood_in. Dead snags have no stand-in: skipped.
FALLBACK = {"VEG_SugarMaple_L": "VEG_SilverMaple_L", "VEG_SugarMaple_M": "VEG_SilverMaple_M",
            "VEG_SugarMaple_S": "VEG_SilverMaple_S", "VEG_LondonPlane_M": "VEG_Hackberry_M",
            "VEG_LondonPlane_L": "VEG_Hackberry_L"}
SOFT = ("VEG_Lilac", "VEG_ShrubRound", "VEG_Sumac", "VEG_WillowShrub", "VEG_Boxwood", "VEG_Sage", "VEG_Rabbit")
FIELD_Z_CM = 1.0      # top of the field slab (the city's ground slab top is at -2 cm, roads at 0)


def _root():
    try:
        d = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        d = None
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "SkyCity.uproject")):
            return d
        d = os.path.dirname(d)
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")


def _meshes():
    """mesh name (without SM_) -> path, for every SM_ mesh in the pack."""
    lib = unreal.EditorAssetLibrary
    out = {}
    for path in lib.list_assets(PACK + "/Meshes", recursive=True):
        name = path.split("/")[-1].split(".")[0]
        if name.startswith("SM_"):
            out[name[3:]] = path.split(".")[0]
    return out


def slot_meshes(names, slot):
    """The mesh paths for a slot: SM_<slot> itself, else its variants SM_<slot>_A, _B, ... in order."""
    if slot in names:
        return [names[slot]]
    return [names[n] for n in sorted(names) if n.startswith(slot + "_") and len(n) == len(slot) + 2 and n[-1].isupper()]


def _subobject(actor, cls):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    root = sds.k2_gather_subobject_data_for_instance(actor)[0]
    handle, _fail = sds.add_new_subobject(unreal.AddNewSubobjectParams(parent_handle=root, new_class=cls))
    data = unreal.SubobjectDataBlueprintFunctionLibrary.get_data(handle)
    return unreal.SubobjectDataBlueprintFunctionLibrary.get_object(data)


def main():
    root = _root()
    bt = os.environ.get("GEN_BT") or sys.argv[1]
    seed = int(os.environ.get("GEN_SEED", "7"))
    region, name = "seed%d_city" % seed, "Seed%d" % seed
    label = "GenCity_%s" % name
    status = os.path.join(root, "Saved", "GenCity", "landcover_status_%s.json" % region)
    result = {"region": region}
    try:
        lc = os.path.join(bt, "Saved", "CityGen", "pipeline", "seed-%d" % seed, "landcover")
        hero = json.load(open(os.path.join(lc, "hero.json")))
        cover = json.load(open(os.path.join(lc, "landcover.json")))
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        if not world or world.get_name() != label:
            les.load_level("/Game/Maps/%s" % label)
        sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        folder = label + "/LandCover"
        for actor in sub.get_all_level_actors():
            if str(actor.get_folder_path()).startswith(folder):
                sub.destroy_actor(actor)
        meshes = _meshes()
        fields = hero["head"]["fields"]
        slots = hero["head"]["slots"]
        i_slot, i_x, i_y, i_z = fields.index("slot"), fields.index("x_mm"), fields.index("y_mm"), fields.index("z_mm")
        i_yaw, i_s = fields.index("yaw_ddeg"), fields.index("scale_milli")
        by_slot = {}
        for row in hero["instances"]:
            by_slot.setdefault(slots[row[i_slot]], []).append(row)
        actor = sub.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        actor.set_actor_label("LC_HeroScatter")
        actor.set_folder_path(folder)
        _subobject(actor, unreal.SceneComponent)
        placed, missing, stood_in = {}, {}, {}
        for slot, all_rows in sorted(by_slot.items()):
            paths = slot_meshes(meshes, slot)
            if not paths and slot in FALLBACK:
                paths = slot_meshes(meshes, FALLBACK[slot])
                if paths:
                    stood_in[slot] = FALLBACK[slot]
            if not paths:
                missing[slot] = len(all_rows)
                continue
            for vi, path in enumerate(paths):
              rows = all_rows[vi::len(paths)]          # variants take turns
              if not rows:
                  continue
              mesh = unreal.EditorAssetLibrary.load_asset(path)
              comp = _subobject(actor, unreal.HierarchicalInstancedStaticMeshComponent)
              comp.set_editor_property("static_mesh", mesh)
              if slot.startswith(SOFT):
                  comp.set_collision_profile_name("NoCollision")       # shrubs: the car pushes through
              else:
                  comp.set_collision_profile_name("BlockAll")          # trunks and logs block the car...
                  comp.set_collision_response_to_channel(unreal.CollisionChannel.ECC_CAMERA,
                                                         unreal.CollisionResponseType.ECR_IGNORE)  # ...not the camera
              xforms = []
              for r in rows:
                  s = r[i_s] / 1000.0
                  # plan (x east, y north, yaw ccw from east) -> Unreal (X north, Y east, yaw cw from X)
                  xforms.append(unreal.Transform(unreal.Vector(r[i_y] / 10.0, r[i_x] / 10.0, r[i_z] / 10.0),
                                                 unreal.Rotator(0.0, 0.0, 90.0 - r[i_yaw] / 10.0),
                                                 unreal.Vector(s, s, s)))
              comp.add_instances(xforms, False, False)
            placed[slot] = len(all_rows)
        # fields
        lib = unreal.EditorAssetLibrary
        # the generator's own 1 m cube (owned_basics_ue.py imports it with the city)
        cube = lib.load_asset("/Game/CityGen/Basics/KIT_Cube/StaticMeshes/KIT_Cube") if lib.does_asset_exist("/Game/CityGen/Basics/KIT_Cube/StaticMeshes/KIT_Cube") else None
        nf = 0
        if cube is not None:
            for f in cover.get("fields") or []:
                pts = f["polygon"]
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
                mat = lib.load_asset("%s/Materials/Ground/%s" % (PACK, FIELD_GROUND.get(f.get("crop"), FIELD_DEFAULT)))
                a = sub.spawn_actor_from_class(unreal.StaticMeshActor,
                                               unreal.Vector((y0 + y1) * 50.0, (x0 + x1) * 50.0, FIELD_Z_CM - 2.5),
                                               unreal.Rotator(0, 0, 0))
                a.set_actor_label("LC_Field_%s" % f["id"][-12:])
                a.set_folder_path(folder + "/Fields")
                a.static_mesh_component.set_static_mesh(cube)
                a.set_actor_scale3d(unreal.Vector(y1 - y0, x1 - x0, 0.05))
                if mat:
                    a.static_mesh_component.set_material(0, mat)
                a.static_mesh_component.set_collision_profile_name("BlockAll")
                nf += 1
        result.update({"ok": True, "hero_placed": placed, "hero_total": sum(placed.values()),
                       "hero_missing_slots": missing, "hero_stood_in": stood_in, "fields": nf, "cube": cube.get_path_name() if cube else None})
        les.save_current_level()
    except BaseException:
        result.update({"ok": False, "trace": traceback.format_exc()})
    with open(status, "w") as handle:
        json.dump(result, handle, indent=1, sort_keys=True)
        handle.write("\n")


main()
