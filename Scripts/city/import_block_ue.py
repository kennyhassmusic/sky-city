"""Import the city-block study and bind the CC0 maps.

The GLBs under SourceArt/CityGen/blocks keep named slots (M_Brick, M_Concrete,
M_Plaster, M_Metal, M_Asphalt, M_Paving, M_Grass, M_Glass) and do not embed images.
Embedding the scans in every LOD would copy the same JPGs into each file. This
script imports the meshes and the JPGs, builds one material per slot, and assigns
it. Mesh UVs are already in repeats of the scan size recorded in materials.json.

M_Glass is a plain pane. InteriorCubemap on that slot, and Nanite on LOD0, stay
hand steps in the editor.

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
ART = os.path.join(ROOT, "SourceArt", "CityGen")
MESH_DIR = "/Game/City/CityGen/Blocks"
TEX_DIR = "/Game/City/CityGen/Textures"
MAT_DIR = "/Game/City/CityGen/Materials"

# Blender slot (M_<Capitalized>) -> materials.json id.
SLOTS = {
    "M_Brick": "brick_wall_001",
    "M_Concrete": "concrete_wall_001",
    "M_Plaster": "grey_plaster",
    "M_Metal": "metal_plate",
    "M_Asphalt": "asphalt_02",
    "M_Paving": "PavingStones092",
    "M_Grass": "Grass004",
}


def main():
    import unreal
    record = json.load(open(os.path.join(ART, "materials", "materials.json")))
    assets = unreal.AssetToolsHelpers.get_asset_tools()
    library = unreal.EditorAssetLibrary
    editing = unreal.MaterialEditingLibrary
    imported = _import_glb(unreal, assets)
    textures = _import_textures(unreal, assets, library, record)
    materials = _build_materials(unreal, assets, library, editing, record, textures)
    bound = _assign(unreal, library, imported, materials)
    print("CITYGEN import", len(imported), "meshes,", len(bound), "slots bound")


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


def _import_textures(unreal, assets, library, record):
    """Return materials.json id -> {color, normal, rough} asset paths."""
    out = {}
    for ident, info in record.items():
        maps = info.get("maps") or {}
        out[ident] = {}
        for kind, rel in maps.items():
            src = os.path.join(ART, "materials", rel)
            if not os.path.isfile(src):
                continue
            # HDR skies stay in the Blender preview. The editor import binds the JPG scans.
            if not src.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            dest = TEX_DIR + "/" + ident
            task = unreal.AssetImportTask()
            task.set_editor_property("filename", src)
            task.set_editor_property("destination_path", dest)
            task.set_editor_property("automated", True)
            task.set_editor_property("replace_existing", True)
            task.set_editor_property("save", True)
            assets.import_asset_tasks([task])
            paths = list(task.get_editor_property("imported_object_paths") or [])
            if not paths:
                continue
            tex = library.load_asset(paths[0])
            if kind == "color":
                tex.set_editor_property("srgb", True)
            else:
                tex.set_editor_property("srgb", False)
                if kind == "normal":
                    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
                    tex.set_editor_property("flip_green_channel", True)
            library.save_loaded_asset(tex)
            out[ident][kind] = paths[0].split(".")[0]
    return out


def _expr(unreal, editing, mat, cls, x, y):
    return editing.create_material_expression(mat, cls, x, y)


def _build_materials(unreal, assets, library, editing, record, textures):
    made = {}
    for slot, ident in SLOTS.items():
        info = textures.get(ident) or {}
        if "color" not in info:
            continue
        if library.does_asset_exist(MAT_DIR + "/" + slot):
            library.delete_asset(MAT_DIR + "/" + slot)
        mat = assets.create_asset(slot, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
        color = _expr(unreal, editing, mat, unreal.MaterialExpressionTextureSample, -400, -200)
        color.set_editor_property("texture", library.load_asset(info["color"]))
        editing.connect_material_property(color, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
        if "rough" in info:
            rough = _expr(unreal, editing, mat, unreal.MaterialExpressionTextureSample, -400, 80)
            rough.set_editor_property("texture", library.load_asset(info["rough"]))
            rough.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
            editing.connect_material_property(rough, "R", unreal.MaterialProperty.MP_ROUGHNESS)
        if "normal" in info:
            normal = _expr(unreal, editing, mat, unreal.MaterialExpressionTextureSample, -400, 280)
            normal.set_editor_property("texture", library.load_asset(info["normal"]))
            normal.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
            editing.connect_material_property(normal, "RGB", unreal.MaterialProperty.MP_NORMAL)
        editing.recompile_material(mat)
        library.save_loaded_asset(mat)
        made[slot] = mat
    # A readable pane. InteriorCubemap is applied by hand on top of this slot.
    glass_name = "M_Glass"
    if library.does_asset_exist(MAT_DIR + "/" + glass_name):
        library.delete_asset(MAT_DIR + "/" + glass_name)
    glass = assets.create_asset(glass_name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    glass.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    const = _expr(unreal, editing, glass, unreal.MaterialExpressionConstant3Vector, -300, 0)
    const.set_editor_property("constant", unreal.LinearColor(0.55, 0.7, 0.82, 1))
    editing.connect_material_property(const, "", unreal.MaterialProperty.MP_BASE_COLOR)
    opacity = _expr(unreal, editing, glass, unreal.MaterialExpressionConstant, -300, 160)
    opacity.set_editor_property("r", 0.55)
    editing.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY)
    editing.recompile_material(glass)
    library.save_loaded_asset(glass)
    made[glass_name] = glass
    made["M_GlassLit"] = glass
    # Dress slots are flat colours. The Blender preview blends the CC0 grime; these
    # are the fallbacks so a slot is not left empty after import.
    flats = {
        "M_Blind": (0.8, 0.78, 0.72),
        "M_CurtainRed": (0.45, 0.16, 0.14),
        "M_AwningNavy": (0.12, 0.16, 0.28),
        "M_Puddle": (0.04, 0.04, 0.045),
        "M_Manhole": (0.25, 0.25, 0.26),
        "M_SignCafe": (0.36, 0.16, 0.14),
    }
    for name, rgb in flats.items():
        if library.does_asset_exist(MAT_DIR + "/" + name):
            library.delete_asset(MAT_DIR + "/" + name)
        mat = assets.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
        const = _expr(unreal, editing, mat, unreal.MaterialExpressionConstant3Vector, -200, 0)
        const.set_editor_property("constant", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1))
        editing.connect_material_property(const, "", unreal.MaterialProperty.MP_BASE_COLOR)
        editing.recompile_material(mat)
        library.save_loaded_asset(mat)
        made[name] = mat
    return made


def _assign(unreal, library, imported, materials):
    bound = []
    for path in imported:
        asset = library.load_asset(path.split(".")[0])
        if asset is None or not isinstance(asset, unreal.StaticMesh):
            continue
        slots = asset.get_editor_property("static_materials")
        for index, slot in enumerate(slots):
            name = str(slot.get_editor_property("material_slot_name"))
            base = name.split(".")[0]
            mat = materials.get(base)
            if mat is None:
                continue
            asset.set_material(index, mat)
            bound.append(path + ":" + base)
        library.save_loaded_asset(asset)
    return bound


if __name__ == "__main__":
    main()
