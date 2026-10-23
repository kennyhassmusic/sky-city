"""Import the generated city beside City Sample. Does not replace it.

Reads the chunked GLBs in SourceArt/CityGen/city (from
Scripts/city/blender_city.py). They are the block builder's facade, roof and
storefront meshes, with the same -90 degree turn baked in, so each mesh is
spawned at the world origin. Textures are the CC0 scans already in
SourceArt/CityGen/materials. SkyCityMashup is not opened. CitySamplePCG is
not modified or removed.

If that folder has no GLB, the script falls back to scaled cubes from
Saved/CityGen/sky_city_spawn.json so a layout pass still has something to see.

Run in the editor, PIE off:
  py Scripts/city/import_city_ue.py
"""
import json
import os


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
    import unreal
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")


ROOT = _root()
SPAWN = os.path.join(ROOT, "Saved", "CityGen", "sky_city_spawn.json")
SPAWN_FALLBACK = os.path.join(ROOT, "Scripts", "city", "examples", "sky_city_spawn.json")
MESH_SRC = os.path.join(ROOT, "SourceArt", "CityGen", "city")
ART = os.path.join(ROOT, "SourceArt", "CityGen")
LEVEL = "/Game/Maps/SkyCityGenerated"
FOLDER = "/Game/City/Generated"
MAT_DIR = FOLDER + "/Materials"
TEX_DIR = FOLDER + "/Textures"

# Blender slot -> materials.json id. Same scans as the block importer.
SLOTS = {
    "M_Brick": "brick_wall_001",
    "M_Concrete": "concrete_wall_001",
    "M_Plaster": "grey_plaster",
    "M_Metal": "metal_plate",
    "M_Asphalt": "asphalt_02",
    "M_Paving": "PavingStones092",
    "M_Grass": "Grass004",
}
FLATS = {
    "M_Roof": (0.18, 0.19, 0.20),
    "M_Curb": (0.78, 0.76, 0.72),
    "M_LanePaint": (0.92, 0.92, 0.90),
    "M_LanePaintYellow": (0.86, 0.68, 0.12),
    "M_Interior": (0.12, 0.10, 0.09),
    "M_InteriorLit": (1.0, 0.72, 0.38),
    "M_FenceIron": (0.16, 0.17, 0.18),
    "M_FenceWood": (0.36, 0.24, 0.14),
    "M_TrimDark": (0.25, 0.22, 0.20),
    "M_Paint": (0.85, 0.85, 0.82),
    "M_Blind": (0.80, 0.78, 0.72),
    "M_CurtainRed": (0.45, 0.16, 0.14),
    "M_AwningNavy": (0.12, 0.16, 0.28),
    "M_Puddle": (0.04, 0.04, 0.045),
    "M_Manhole": (0.25, 0.25, 0.26),
}
# Cube fallback colours, used only when no city GLB is present.
COLOURS = {
    "brick": (0.45, 0.22, 0.16, 1),
    "concrete": (0.55, 0.54, 0.50, 1),
    "plaster": (0.72, 0.68, 0.60, 1),
    "glass": (0.35, 0.50, 0.55, 1),
    "metal": (0.40, 0.42, 0.44, 1),
    "asphalt": (0.12, 0.12, 0.13, 1),
    "paving": (0.55, 0.54, 0.50, 1),
    "grass": (0.25, 0.38, 0.18, 1),
}


def main():
    import unreal
    unreal.EditorLevelLibrary.new_level(LEVEL)
    glbs = _glbs()
    if glbs:
        materials = _city_materials(unreal)
        count = _spawn_glbs(unreal, glbs, materials)
        unreal.EditorLevelLibrary.save_current_level()
        print("CITYGEN meshes", count, "from", len(glbs), "glb")
    else:
        path = SPAWN if os.path.isfile(SPAWN) else SPAWN_FALLBACK
        document = json.load(open(path))
        cube = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube")
        materials = _cube_materials(unreal)
        _buildings(unreal, document, cube, materials)
        _roads(unreal, document, cube, materials)
        _props(unreal, document, cube, materials)
        unreal.EditorLevelLibrary.save_current_level()
        print("CITYGEN cubes buildings", len(document.get("buildings") or []))
    print("City Sample was not opened. CitySamplePCG was not changed.")


def _glbs():
    if not os.path.isdir(MESH_SRC):
        return []
    return [os.path.join(MESH_SRC, name) for name in sorted(os.listdir(MESH_SRC)) if name.endswith(".glb")]


def _spawn_glbs(unreal, glbs, materials):
    assets = unreal.AssetToolsHelpers.get_asset_tools()
    library = unreal.EditorAssetLibrary
    dest = FOLDER + "/Meshes"
    if not library.does_directory_exist(dest):
        library.make_directory(dest)
    spawned = 0
    for filename in glbs:
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", filename)
        task.set_editor_property("destination_path", dest)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", True)
        assets.import_asset_tasks([task])
        for path in list(task.get_editor_property("imported_object_paths") or []):
            asset = library.load_asset(path.split(".")[0])
            if not isinstance(asset, unreal.StaticMesh):
                continue
            _assign_slots(unreal, library, asset, materials)
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
                unreal.StaticMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
            actor.set_actor_label(os.path.splitext(os.path.basename(filename))[0][:80])
            actor.set_folder_path("SkyCityGenerated")
            actor.static_mesh_component.set_static_mesh(asset)
            actor.set_actor_scale3d(unreal.Vector(1, 1, 1))
            spawned += 1
    return spawned


def _assign_slots(unreal, library, asset, materials):
    slots = asset.get_editor_property("static_materials")
    for index, slot in enumerate(slots):
        name = str(slot.get_editor_property("material_slot_name")).split(".")[0]
        mat = materials.get(name)
        if mat is not None:
            asset.set_material(index, mat)
    library.save_loaded_asset(asset)


def _city_materials(unreal):
    library = unreal.EditorAssetLibrary
    assets = unreal.AssetToolsHelpers.get_asset_tools()
    editing = unreal.MaterialEditingLibrary
    record = {}
    path = os.path.join(ART, "materials", "materials.json")
    if os.path.isfile(path):
        record = json.load(open(path))
    if not library.does_directory_exist(MAT_DIR):
        library.make_directory(MAT_DIR)
    made = {}
    for slot, ident in SLOTS.items():
        info = (record.get(ident) or {}).get("maps") or {}
        textures = _textures(unreal, assets, library, ident, info)
        if "color" not in textures:
            continue
        made[slot] = _textured(unreal, assets, library, editing, slot, textures)
    made["M_Glass"] = _glass(unreal, assets, library, editing, "M_Glass")
    made["M_GlassLit"] = made["M_Glass"]
    for name, rgb in FLATS.items():
        made[name] = _flat(unreal, assets, library, editing, name, rgb)
    return made


def _textures(unreal, assets, library, ident, maps):
    out = {}
    for kind, rel in maps.items():
        src = os.path.join(ART, "materials", rel)
        if not os.path.isfile(src):
            continue
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
        out[kind] = paths[0].split(".")[0]
    return out


def _textured(unreal, assets, library, editing, slot, textures):
    if library.does_asset_exist(MAT_DIR + "/" + slot):
        library.delete_asset(MAT_DIR + "/" + slot)
    mat = assets.create_asset(slot, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    color = editing.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -400, -200)
    color.set_editor_property("texture", library.load_asset(textures["color"]))
    editing.connect_material_property(color, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    if "rough" in textures:
        rough = editing.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -400, 80)
        rough.set_editor_property("texture", library.load_asset(textures["rough"]))
        rough.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        editing.connect_material_property(rough, "R", unreal.MaterialProperty.MP_ROUGHNESS)
    if "normal" in textures:
        normal = editing.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -400, 280)
        normal.set_editor_property("texture", library.load_asset(textures["normal"]))
        normal.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        editing.connect_material_property(normal, "RGB", unreal.MaterialProperty.MP_NORMAL)
    editing.recompile_material(mat)
    library.save_loaded_asset(mat)
    return mat


def _glass(unreal, assets, library, editing, name):
    if library.does_asset_exist(MAT_DIR + "/" + name):
        library.delete_asset(MAT_DIR + "/" + name)
    mat = assets.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    const = editing.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -300, 0)
    const.set_editor_property("constant", unreal.LinearColor(0.55, 0.70, 0.82, 1))
    editing.connect_material_property(const, "", unreal.MaterialProperty.MP_BASE_COLOR)
    opacity = editing.create_material_expression(mat, unreal.MaterialExpressionConstant, -300, 160)
    opacity.set_editor_property("r", 0.55)
    editing.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY)
    editing.recompile_material(mat)
    library.save_loaded_asset(mat)
    return mat


def _flat(unreal, assets, library, editing, name, rgb):
    if library.does_asset_exist(MAT_DIR + "/" + name):
        library.delete_asset(MAT_DIR + "/" + name)
    mat = assets.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    const = editing.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -200, 0)
    const.set_editor_property("constant", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1))
    editing.connect_material_property(const, "", unreal.MaterialProperty.MP_BASE_COLOR)
    editing.recompile_material(mat)
    library.save_loaded_asset(mat)
    return mat


def _cube_materials(unreal):
    lib = unreal.EditorAssetLibrary
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    editing = unreal.MaterialEditingLibrary
    if not lib.does_directory_exist(MAT_DIR):
        lib.make_directory(MAT_DIR)
    made = {}
    for name, rgba in COLOURS.items():
        asset_name = "M_Gen_" + name.capitalize()
        if lib.does_asset_exist(MAT_DIR + "/" + asset_name):
            lib.delete_asset(MAT_DIR + "/" + asset_name)
        mat = tools.create_asset(asset_name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
        const = editing.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -300, 0)
        const.set_editor_property("constant", unreal.LinearColor(rgba[0], rgba[1], rgba[2], rgba[3]))
        editing.connect_material_property(const, "", unreal.MaterialProperty.MP_BASE_COLOR)
        editing.recompile_material(mat)
        lib.save_loaded_asset(mat)
        made[name] = mat
    return made


def _buildings(unreal, document, cube, materials):
    for item in document.get("buildings") or []:
        if item.get("kind") == "landmark":
            _actor(unreal, cube, materials["metal"], item["id"],
                   (item["y"] * 100.0, item["x"] * 100.0, 2000.0), (0, 0, 0), (4, 4, 40))
            continue
        loc = item.get("ue") or [item["y"] * 100.0, item["x"] * 100.0, item["h"] * 50.0]
        wall = item.get("wall") or "concrete"
        _actor(unreal, cube, materials.get(wall) or materials["concrete"], item["id"],
               loc, (0, item.get("ue_yaw") or 0, 0), (item["w"], item["d"], item["h"]))


def _roads(unreal, document, cube, materials):
    for road in document.get("roads") or []:
        pts = road.get("pts") or []
        width = float(road.get("width") or 8.0)
        for a, b in zip(pts, pts[1:]):
            ax, ay = float(a[0]), float(a[1])
            bx, by = float(b[0]), float(b[1])
            dx, dy = bx - ax, by - ay
            length = (dx * dx + dy * dy) ** 0.5
            if length < 0.5:
                continue
            mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
            yaw = _ue_yaw_of(dx, dy)
            _actor(unreal, cube, materials["asphalt"], road["id"] + "_asphalt",
                   (my * 100.0, mx * 100.0, 6.0), (0, yaw, 0), (length, width, 0.12))
            walk = 3.8
            for side in (-1.0, 1.0):
                ox = -dy / length * side * (width / 2.0 + walk / 2.0)
                oy = dx / length * side * (width / 2.0 + walk / 2.0)
                slot = "grass" if road.get("parkway") else "paving"
                _actor(unreal, cube, materials[slot], road["id"] + "_walk",
                       ((my + oy) * 100.0, (mx + ox) * 100.0, 10.0),
                       (0, yaw, 0), (length, walk, 0.08))


def _props(unreal, document, cube, materials):
    scale = {
        "lamp": (0.3, 0.3, 6.0), "signal": (0.4, 0.4, 5.0), "stop": (0.2, 0.8, 2.6),
        "yield": (0.2, 0.8, 2.6), "street_name": (0.15, 0.9, 2.4), "bus_stop": (0.2, 0.5, 2.8),
        "hydrant": (0.4, 0.4, 0.8), "bench": (1.6, 0.5, 0.8), "bin": (0.6, 0.6, 1.1),
        "parked": (4.4, 1.8, 1.5), "tree": (1.2, 1.2, 8.0),
    }
    slot = {
        "lamp": "metal", "signal": "metal", "stop": "brick", "yield": "metal",
        "street_name": "plaster", "bus_stop": "glass", "hydrant": "brick",
        "bench": "plaster", "bin": "metal", "parked": "glass", "tree": "grass",
    }
    for prop in document.get("props") or []:
        kind = prop.get("kind") or "lamp"
        loc = (float(prop["y"]) * 100.0, float(prop["x"]) * 100.0, scale.get(kind, (1, 1, 1))[2] * 50.0)
        _actor(unreal, cube, materials.get(slot.get(kind), "metal"), prop.get("id") or kind,
               loc, (0, float(prop.get("yaw") or 0), 0), scale.get(kind, (1, 1, 1)))


def _ue_yaw_of(dx, dy):
    import math
    return 90.0 - math.degrees(math.atan2(dy, dx))


def _actor(unreal, cube, material, label, location, rotator, scale):
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.StaticMeshActor, unreal.Vector(location[0], location[1], location[2]),
        unreal.Rotator(rotator[0], rotator[1], rotator[2]))
    actor.set_actor_label(str(label)[:80])
    actor.set_folder_path("SkyCityGenerated")
    mesh = actor.static_mesh_component
    mesh.set_static_mesh(cube)
    mesh.set_material(0, material)
    actor.set_actor_scale3d(unreal.Vector(scale[0], scale[1], scale[2]))
    return actor


if __name__ == "__main__":
    main()
