"""Spawn the generated Sky City beside City Sample. Does not replace it.

Reads Saved/CityGen/sky_city_spawn.json (from Scripts/city/generate_city.py).
Creates /Game/Maps/SkyCityGenerated and actors under /Game/City/Generated.
SkyCityMashup is not opened. CitySamplePCG is not modified or removed.

Buildings are scaled engine cubes in the CC0 slot colour (brick, concrete,
plaster, glass, metal). Roads are asphalt ribbons with a sidewalk strip.
This is the comparison view, not the final mesher.

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
LEVEL = "/Game/Maps/SkyCityGenerated"
FOLDER = "/Game/City/Generated"
MAT_DIR = FOLDER + "/Materials"

# CC0 slot names the generator already uses. Flat colour until the scans are bound.
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
    path = SPAWN if os.path.isfile(SPAWN) else SPAWN_FALLBACK
    document = json.load(open(path))
    level = document.get("level") or LEVEL
    unreal.EditorLevelLibrary.new_level(level)
    cube = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube")
    materials = _materials(unreal)
    _buildings(unreal, document, cube, materials)
    _roads(unreal, document, cube, materials)
    _props(unreal, document, cube, materials)
    unreal.EditorLevelLibrary.save_current_level()
    print("CITYGEN level", level, "buildings", len(document.get("buildings") or []),
          "roads", len(document.get("roads") or []))
    print("City Sample was not opened. CitySamplePCG was not changed.")


def _materials(unreal):
    lib = unreal.EditorAssetLibrary
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    if not lib.does_directory_exist(MAT_DIR):
        lib.make_directory(MAT_DIR)
    made = {}
    for name, rgba in COLOURS.items():
        asset_name = "M_Gen_" + name.capitalize()
        path = MAT_DIR + "/" + asset_name
        if lib.does_asset_exist(path):
            lib.delete_asset(path)
        mat = tools.create_asset(asset_name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
        editing = unreal.MaterialEditingLibrary
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
                   (item["y"] * 100.0, item["x"] * 100.0, 2000.0),
                   (0, 0, 0), (4, 4, 40))
            continue
        loc = item.get("ue") or [item["y"] * 100.0, item["x"] * 100.0, item["h"] * 50.0]
        yaw = item.get("ue_yaw") or 0
        wall = item.get("wall") or "concrete"
        _actor(unreal, cube, materials.get(wall) or materials["concrete"], item["id"],
               loc, (0, yaw, 0), (item["w"], item["d"], item["h"]))


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
        "lamp": (0.3, 0.3, 6.0),
        "signal": (0.4, 0.4, 5.0),
        "stop": (0.2, 0.8, 2.6),
        "yield": (0.2, 0.8, 2.6),
        "street_name": (0.15, 0.9, 2.4),
        "bus_stop": (0.2, 0.5, 2.8),
        "hydrant": (0.4, 0.4, 0.8),
        "bench": (1.6, 0.5, 0.8),
        "bin": (0.6, 0.6, 1.1),
        "parked": (4.4, 1.8, 1.5),
        "tree": (1.2, 1.2, 8.0),
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
    """Plan edge (east, north) to an Unreal yaw whose local X follows that edge."""
    import math
    plan = math.degrees(math.atan2(dy, dx))
    return 90.0 - plan


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
