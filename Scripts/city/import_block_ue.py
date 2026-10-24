"""Import the city-block study and bind the CC0 maps.

The GLBs under SourceArt/CityGen/blocks keep named slots (M_Brick, M_Concrete,
M_Plaster, M_Metal, M_Asphalt, M_Paving, M_Grass, M_Glass) and do not embed images.
Embedding the scans in every LOD would copy the same JPGs into each file. This
script imports the meshes and the JPGs, builds one material per slot, and assigns
it. Mesh UVs are already in repeats of the scan size recorded in materials.json.

Slot textures go through pack_slots.py (an AI pack when one fits the block's
district types, else the CC0 scan) and city_materials_ue.py, the same path as
the city importer. Glass is real glass (Fresnel, per-pixel lit translucency)
so the room shells behind the panes show through. Nanite on LOD0 stays a hand
step in the editor. Wall slots are instances of M_Facade: procedural
edge wear, sill drips and base dirt, scaled by the mesh vertex colour.

Run in the editor, PIE off:
  py Scripts/city/import_block_ue.py
"""
import json
import os
import sys


def _skycity_root():
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
    import unreal
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")


ROOT = _skycity_root()
_HERE = os.path.join(ROOT, "Scripts", "city")
ART = os.path.join(ROOT, "SourceArt", "CityGen")
MESH_DIR = "/Game/City/CityGen/Blocks"
TEX_DIR = "/Game/City/CityGen/Textures"
MAT_DIR = "/Game/City/CityGen/Materials"

# Slot -> CC0 scan ids live in pack_slots.CC0.


def main():
    import unreal
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import city_materials_ue
    import pack_slots
    import packs
    assets = unreal.AssetToolsHelpers.get_asset_tools()
    library = unreal.EditorAssetLibrary
    imported = _import_glb(unreal, assets)
    record = pack_slots.load_record(ART)
    plan = pack_slots.plan_slots(_block_spawn(), packs.load_library(), record, ART, region="loop_block")
    for line in pack_slots.summary(plan):
        print("CITYGEN slot", line)
    materials = city_materials_ue.build(unreal, plan, MAT_DIR, TEX_DIR)
    bound = _assign(unreal, library, imported, materials)
    print("CITYGEN import", len(imported), "meshes,", len(bound), "slots bound")


def _block_spawn():
    """District types of the block study, for the pack choice (none: CC0)."""
    import pack_slots
    path = os.path.join(ROOT, "Scripts", "city", "examples", "loop_block.city_model.json")
    if not os.path.isfile(path):
        return {}
    with open(path) as handle:
        return pack_slots.spawn_from_model(json.load(handle))


def _import_glb(unreal, assets):
    folder = os.path.join(ART, "blocks")
    tasks = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".glb"):
            continue
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", os.path.join(folder, name))
        task.set_editor_property("destination_path", MESH_DIR)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", True)
        tasks.append(task)
    assets.import_asset_tasks(tasks)
    paths = []
    for task in tasks:
        paths += list(task.get_editor_property("imported_object_paths") or [])
    return paths


def _assign(unreal, library, imported, materials):
    import city_materials_ue
    bound = []
    for path in imported:
        asset = library.load_asset(path.split(".")[0])
        if asset is None or not isinstance(asset, unreal.StaticMesh):
            continue
        missing = city_materials_ue.assign(unreal, asset, materials)
        bound.append(path)
        if missing:
            print("CITYGEN", path, "left on glTF material:", ", ".join(sorted(set(missing))))
        library.save_loaded_asset(asset)
    return bound


if __name__ == "__main__":
    main()
