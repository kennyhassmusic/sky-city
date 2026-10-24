"""Import the generated city beside City Sample. Does not replace it.

Reads chunked GLBs from Scripts/city/blender_city.py. They are the block
builder's facade, roof and storefront meshes, with the same -90 degree turn
baked in, so each mesh is spawned at the world origin (plan north on +X,
plan east on +Y). SkyCityMashup is not opened. CitySamplePCG is not modified
or removed.

Materials: pack_slots.plan_slots() picks an AI texture pack per slot when one
fits the district (windowless walls, asphalt, sidewalk, grass) and the CC0
scans otherwise; city_materials_ue.py builds them, plus real glass so the
room shells behind every pane show through, and emissive lit rooms.

Nanite is turned off on every imported mesh (the Mac build is SM5, where
Nanite would draw the simplified fallback).

Collision: every imported mesh uses its own triangles as collision (complex
as simple) so the Skyster can drive the streets and wall-ride the towers.
A thin ground slab under the region keeps the car up between street meshes.
The level gets a sun, sky light, atmosphere, fog and a PlayerStart on the
longest major street. Re-running replaces what this script spawned.

If the GLB folder is empty, the script falls back to scaled cubes from the
spawn record so a layout pass still has something to see.

Buildings: --buildings baked (default) imports the tower GLBs and boxes
what they leave out. --buildings kit imports only the street tiles and
assembles every tower from the facade kit (kit_city_ue.py, kit_layout.py,
blender_facade_kit.py): about 25 HISM components for the whole region,
simple box collision per setback tier.

Run in the editor, PIE off (paths are relative to the project folder):
  py Scripts/city/import_city_ue.py
  py Scripts/city/import_city_ue.py --glbs SourceArt/CityGen/chicago \
      --level /Game/Maps/SkyCityChicagoGen --spawn Saved/CityGen/sky_city_spawn_chicago_loop.json
  py Scripts/city/import_city_ue.py --glbs SourceArt/CityGen/chicago --buildings kit \
      --level /Game/Maps/SkyCityChicagoGen --spawn Saved/CityGen/sky_city_spawn_chicago_loop.json
Without arguments it is the old behaviour: SourceArt/CityGen/city into
/Game/Maps/SkyCityGenerated. A spawn record's "level" and "folder" are used
when --level / --folder are not given.
"""
import json
import os
import sys


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
_CITY = os.path.join(ROOT, "Scripts", "city")
if _CITY not in sys.path:
    sys.path.insert(0, _CITY)
SPAWN = os.path.join(ROOT, "Saved", "CityGen", "sky_city_spawn.json")
SPAWN_FALLBACK = os.path.join(ROOT, "Scripts", "city", "examples", "sky_city_spawn.json")
MESH_SRC = os.path.join(ROOT, "SourceArt", "CityGen", "city")
ART = os.path.join(ROOT, "SourceArt", "CityGen")
LEVEL = "/Game/Maps/SkyCityGenerated"
FOLDER = "/Game/City/Generated"
GROUND_PAD_M = 40.0
FOG_DENSITY = 0.0025
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
MAT_DIR = FOLDER + "/Materials"
MESH_FOLDER_PREFIX = "/Game/City/Generated"
TEX_DIR = FOLDER + "/Textures"
OUTLINER = "SkyCityGenerated"
PLAN = {}  # the slot plan of this run (pack_slots.plan_slots), for the ground slab


def parse_args(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="import_city_ue.py")
    parser.add_argument("--glbs", default=None, help="folder of city GLBs (default SourceArt/CityGen/city)")
    parser.add_argument("--level", default=None, help="target level, e.g. /Game/Maps/SkyCityChicagoGen")
    parser.add_argument("--folder", default=None, help="content folder for meshes and materials")
    parser.add_argument("--spawn", default=None, help="spawn record (default Saved/CityGen/sky_city_spawn.json)")
    parser.add_argument("--no-collision", action="store_true", help="skip complex collision (layout passes)")
    parser.add_argument("--buildings", choices=("baked", "kit"), default="baked",
                        help="baked: the tower GLBs; kit: towers assembled from the facade kit (HISM)")
    parser.add_argument("--kit", default=None, help="facade kit GLBs (default SourceArt/CityGen/kit)")
    parser.add_argument("--layout", default=None,
                        help="kit layout (default Saved/CityGen/kit_layout_<region>.json; built if missing)")
    parser.add_argument("--ids", default=None, help="comma-separated building ids: only these (a prototype block)")
    parser.add_argument("--no-streets", action="store_true", help="skip the street GLBs")
    return parser.parse_args(sys.argv[1:] if argv is None else argv)


def resolve(args):
    """Paths and names for one run. Pure Python, so the defaults can be tested."""
    def abspath(path):
        return path if os.path.isabs(path) else os.path.join(ROOT, path)
    spawn = abspath(args.spawn) if args.spawn else (SPAWN if os.path.isfile(SPAWN) else SPAWN_FALLBACK)
    document = {}
    if os.path.isfile(spawn):
        with open(spawn) as handle:
            document = json.load(handle)
    level = args.level or document.get("level") or LEVEL
    folder = args.folder or document.get("folder") or FOLDER
    region = document.get("region") or "city"
    return {
        "buildings": args.buildings,
        "kit": abspath(args.kit) if args.kit else os.path.join(ART, "kit"),
        "layout": abspath(args.layout) if args.layout else os.path.join(ROOT, "Saved", "CityGen", "kit_layout_%s.json" % region),
        "ids": set(args.ids.split(",")) if args.ids else None,
        "streets": not args.no_streets,
        "glbs": abspath(args.glbs) if args.glbs else MESH_SRC,
        "level": level,
        "folder": folder,
        "label": level.rsplit("/", 1)[-1],
        "spawn": spawn,
        "document": document,
        "collision": not args.no_collision,
    }


def main(argv=None):
    import unreal
    run = resolve(parse_args(argv))
    global MAT_DIR, TEX_DIR, OUTLINER
    OUTLINER = run["label"]
    MAT_DIR = run["folder"] + "/Materials"
    TEX_DIR = run["folder"] + "/Textures"
    if run["level"].rsplit("/", 1)[-1] == "SkyCityMashup":
        raise SystemExit("import_city_ue.py never writes into SkyCityMashup")
    _open_level(unreal, run["level"])
    _clear_previous(unreal, run["label"])
    glbs = select_glbs(_glbs(run["glbs"]), run)
    document = run["document"]
    if glbs or run["buildings"] == "kit":
        materials = _city_materials(unreal, document)
        count, unbound = _spawn_glbs(unreal, glbs, materials, run)
        print("CITYGEN meshes", count, "from", len(glbs), "glb in", run["glbs"])
        if run["buildings"] == "kit":
            _kit(unreal, run, materials)
        elif document:
            boxes, lanes = _massing(unreal, document, run, materials)
            print("CITYGEN massing", boxes, "buildings past the mesh budget,", lanes, "road pieces outside the meshed streets")
        if unbound:
            print("CITYGEN slots left on the glTF material:", ", ".join(sorted(unbound)))
    else:
        if not document:
            raise SystemExit("no GLB in %s and no spawn record at %s" % (run["glbs"], run["spawn"]))
        cube = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube")
        materials = _cube_materials(unreal)
        _buildings(unreal, document, cube, materials)
        _roads(unreal, document, cube, materials)
        _props(unreal, document, cube, materials)
        print("CITYGEN cubes buildings", len(document.get("buildings") or []))
    _stage(unreal, document, run)
    _save_level(unreal)
    print("CITYGEN level", run["level"])
    print("City Sample was not opened. CitySamplePCG was not changed.")


def _open_level(unreal, level):
    subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if unreal.EditorAssetLibrary.does_asset_exist(level):
        ok = subsystem.load_level(level)
    else:
        ok = subsystem.new_level(level)
    if not ok:
        raise SystemExit("could not open or create %s" % level)


def _save_level(unreal):
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()


def _actors(unreal):
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _clear_previous(unreal, label):
    """Destroy what an earlier run of this script spawned (its outliner folder)."""
    sub = _actors(unreal)
    gone = 0
    for actor in sub.get_all_level_actors():
        path = str(actor.get_folder_path())
        if path == label or path.startswith(label + "/"):
            sub.destroy_actor(actor)
            gone += 1
    if gone:
        print("CITYGEN removed", gone, "actors from the previous run")


def select_glbs(glbs, run):
    """Which GLBs this run imports. Kit runs take only the street tiles (the kit builds the towers)."""
    def street(path):
        return "_street" in os.path.basename(path)
    out = []
    for path in glbs:
        if street(path):
            if run.get("streets", True):
                out.append(path)
        elif run.get("buildings", "baked") == "baked":
            out.append(path)
    return out


def _kit(unreal, run, materials):
    import city_materials_ue
    import kit_city_ue
    import kit_layout
    if os.path.isfile(run["layout"]):
        layout = kit_city_ue.load_layout(run["layout"])
    else:
        import generate_city
        city = generate_city.build_from_disk(ROOT, region=run["document"].get("region"))
        layout = kit_layout.build_layout(city).document(run["document"].get("region"))
    if run["ids"]:
        import generate_city
        city = generate_city.build_from_disk(ROOT, region=run["document"].get("region"))
        layout = kit_layout.build_layout(city, run["ids"]).document(run["document"].get("region"))
    meshes = kit_city_ue.import_kit(unreal, run["kit"], run["folder"] + "/Kit")
    kit_city_ue.prepare(unreal, meshes, materials, _drop_gltf_materials)
    walls = city_materials_ue.kit_walls(unreal, unreal.AssetToolsHelpers.get_asset_tools(), unreal.EditorAssetLibrary,
                                        unreal.MaterialEditingLibrary, MAT_DIR, PLAN)
    stats = kit_city_ue.build(unreal, layout, meshes, walls, materials, run["label"], run["label"] + "/Kit", run["level"])
    print("CITYGEN kit buildings", layout.get("buildings"), "sublevels", stats["sublevels"],
          "components", stats["components"], "instances", stats["instances"])


def _glbs(folder):
    if not os.path.isdir(folder):
        return []
    return [os.path.join(folder, name) for name in sorted(os.listdir(folder)) if name.endswith(".glb")]


def _spawn_glbs(unreal, glbs, materials, run):
    import city_materials_ue
    assets = unreal.AssetToolsHelpers.get_asset_tools()
    library = unreal.EditorAssetLibrary
    dest = run["folder"] + "/Meshes"
    if not library.does_directory_exist(dest):
        library.make_directory(dest)
    _drop_stale_meshes(unreal, dest, glbs)
    spawned = 0
    unbound = set()
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
            unbound.update(city_materials_ue.assign(unreal, asset, materials))
            _no_nanite(unreal, asset)
            if run["collision"]:
                _complex_collision(unreal, asset)
            library.save_loaded_asset(asset)
            _drop_gltf_materials(unreal, path.split(".")[0])
            actor = _actors(unreal).spawn_actor_from_class(
                unreal.StaticMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
            actor.set_actor_label(os.path.splitext(os.path.basename(filename))[0][:80])
            actor.set_folder_path(run["label"] + "/Meshes")
            component = actor.static_mesh_component
            component.set_static_mesh(asset)
            component.set_collision_profile_name("BlockAll")
            spawned += 1
    return spawned, unbound


def _drop_stale_meshes(unreal, dest, glbs):
    """Delete mesh folders of GLBs this run does not import (a chunk that was renamed or dropped)."""
    library = unreal.EditorAssetLibrary
    keep = {os.path.splitext(os.path.basename(path))[0] for path in glbs}
    seen = set()
    for path in library.list_assets(dest, recursive=True):
        rest = path[len(dest) + 1:] if path.startswith(dest + "/") else ""
        name = rest.split("/", 1)[0]
        if name and name not in keep and name not in seen:
            seen.add(name)
            library.delete_directory(dest + "/" + name)
    if seen:
        print("CITYGEN removed stale meshes:", ", ".join(sorted(seen)))


def _drop_gltf_materials(unreal, mesh_path):
    """The glTF import makes a material per slot beside each mesh. Every slot is
    rebound above, so those copies are unused; delete them (about 20 MB a city)."""
    library = unreal.EditorAssetLibrary
    folder = mesh_path.rsplit("/", 2)[0] + "/Materials"
    if not folder.startswith(MESH_FOLDER_PREFIX) or not library.does_directory_exist(folder):
        return
    mesh = library.load_asset(mesh_path)
    used = set()
    for slot in mesh.get_editor_property("static_materials") or []:
        mat = slot.get_editor_property("material_interface")
        if mat:
            used.add(mat.get_path_name().split(".")[0])
    for path in library.list_assets(folder, recursive=True):
        if path.split(".")[0] not in used:
            library.delete_asset(path.split(".")[0])


def meshed_ids(glb_folder):
    """Building ids the GLBs already carry (city_manifest.json beside them)."""
    path = os.path.join(glb_folder, "city_manifest.json")
    if not os.path.isfile(path):
        return set()
    with open(path) as handle:
        manifest = json.load(handle)
    ids = set()
    for entry in manifest.get("files") or []:
        if isinstance(entry, dict):
            ids.update(entry.get("buildings") or [])
    return ids


def massing_plan(document, meshed, pad=28.0):
    """(buildings to box, roads to pave) for what the GLBs do not cover.

    A road is paved when no piece of it crosses the meshed buildings' box
    grown by pad metres: blender_city.py clips its street meshes to that box.
    """
    items = [item for item in document.get("buildings") or [] if item.get("kind") == "building"]
    done = [item for item in items if item.get("id") in meshed]
    todo = [item for item in items if item.get("id") not in meshed]
    if not done:
        return todo, list(document.get("roads") or [])
    x0 = min(float(i["x"]) - float(i.get("w", 0)) for i in done) - pad
    x1 = max(float(i["x"]) + float(i.get("w", 0)) for i in done) + pad
    y0 = min(float(i["y"]) - float(i.get("d", 0)) for i in done) - pad
    y1 = max(float(i["y"]) + float(i.get("d", 0)) for i in done) + pad
    import generate_city
    roads = [road for road in document.get("roads") or []
             if not generate_city.clip_polyline(road.get("pts") or [], [x0, y0, x1, y1])]
    return todo, roads


def _massing(unreal, document, run, materials):
    todo, roads = massing_plan(document, meshed_ids(run["glbs"]))
    if run.get("ids"):
        # A prototype block: box only its own unmeshed buildings, no road strips.
        todo = [item for item in todo if item.get("id") in run["ids"]]
        roads = []
    cube = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube")
    wall = {"brick": "M_Brick", "concrete": "M_Concrete", "plaster": "M_Plaster", "metal": "M_Metal", "glass": "M_MassingGlass"}
    fallback = materials.get("M_Concrete")
    facades = _massing_materials(unreal, document)
    for item in todo:
        # A windowed pack facade laid out in metres (city_materials_ue.massing), else the wall scan.
        mat = facades.get(item.get("district_type")) or facades.get("*") \
            or materials.get(wall.get(item.get("wall") or "concrete", "M_Concrete")) or fallback
        loc = item.get("ue") or [item["y"] * 100.0, item["x"] * 100.0, item["h"] * 50.0]
        actor = _actor(unreal, cube, mat, item["id"], loc, (0, item.get("ue_yaw") or 0, 0),
                       (item["w"], item["d"], item["h"]), folder="Massing")
        component = actor.static_mesh_component
        component.set_collision_profile_name("BlockAll")
        for k, size in enumerate((item["w"], item["d"], item["h"])):
            component.set_default_custom_primitive_data_float(k, float(size))
    asphalt = materials.get("M_Asphalt") or fallback
    pieces = 0
    for road in roads:
        pts = road.get("pts") or []
        width = float(road.get("width") or 8.0)
        for a, b in zip(pts, pts[1:]):
            dx, dy = float(b[0]) - float(a[0]), float(b[1]) - float(a[1])
            length = (dx * dx + dy * dy) ** 0.5
            if length < 0.5:
                continue
            mx, my = (float(a[0]) + float(b[0])) / 2.0, (float(a[1]) + float(b[1])) / 2.0
            actor = _actor(unreal, cube, asphalt, road["id"] + "_asphalt", (my * 100.0, mx * 100.0, -1.0),
                           (0, _ue_yaw_of(dx, dy), 0), (length, width, 0.02), folder="Roads")
            actor.static_mesh_component.set_collision_profile_name("BlockAll")
            pieces += 1
    return len(todo), pieces


def _massing_materials(unreal, document):
    import city_materials_ue
    import pack_slots
    sets = pack_slots.massing_sets(document, region=document.get("region") or "city")
    for kind, entry in sorted(sets.items()):
        print("CITYGEN massing facade", kind, entry["set_id"], "tile", entry["tile_m"])
    return city_materials_ue.massing(unreal, unreal.AssetToolsHelpers.get_asset_tools(), unreal.EditorAssetLibrary,
                                     unreal.MaterialEditingLibrary, MAT_DIR, TEX_DIR, sets)


def _no_nanite(unreal, mesh):
    """The glTF import turns Nanite on. Sky City's Mac build is Metal SM5 (no Nanite), where a
    Nanite mesh draws its simplified fallback: torn facades and bow-tie panes. Use the full mesh."""
    settings = mesh.get_editor_property("nanite_settings")
    if settings.get_editor_property("enabled"):
        settings.set_editor_property("enabled", False)
        mesh.set_editor_property("nanite_settings", settings)


def _complex_collision(unreal, mesh):
    """Per-triangle collision: streets, curbs and facades are all drivable."""
    body = mesh.get_editor_property("body_setup")
    if body is None:
        print("CITYGEN note: %s has no body setup; collision left as imported" % mesh.get_name())
        return
    body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)


def _city_materials(unreal, document):
    import city_materials_ue
    import pack_slots
    import packs
    record = pack_slots.load_record(ART)
    plan = pack_slots.plan_slots(document, packs.load_library(), record, ART,
                                 region=document.get("region") or "city")
    for line in pack_slots.summary(plan):
        print("CITYGEN slot", line)
    materials = city_materials_ue.build(unreal, plan, MAT_DIR, TEX_DIR)
    PLAN.clear()
    PLAN.update(plan)
    return materials


def _stage(unreal, document, run):
    """Sun, sky, fog, a ground slab under the region and a PlayerStart on a street."""
    sub = _actors(unreal)
    folder = run["label"] + "/Stage"

    def spawn(cls, location=(0, 0, 0), rotation=(0, 0, 0), label=None):
        actor = sub.spawn_actor_from_class(cls, unreal.Vector(*location), unreal.Rotator(*rotation))
        actor.set_folder_path(folder)
        if label:
            actor.set_actor_label(label)
        return actor

    sun = spawn(unreal.DirectionalLight, (0, 0, 50000), (0, -38, -35), "Sun")
    try:
        sun.light_component.set_editor_property("atmosphere_sun_light", True)
        sun.light_component.set_editor_property("intensity", 8.0)
    except Exception:
        pass
    sky = spawn(unreal.SkyLight, (0, 0, 40000), label="SkyLight")
    try:
        sky.light_component.set_editor_property("real_time_capture", True)
    except Exception:
        pass
    spawn(unreal.SkyAtmosphere, label="SkyAtmosphere")
    fog = spawn(unreal.ExponentialHeightFog, (0, 0, -100), label="HeightFog")
    try:
        # The default density whites out a 1 km city; keep a light haze for depth.
        fog.component.set_editor_property("fog_density", FOG_DENSITY)
        fog.component.set_editor_property("fog_height_falloff", 0.2)
    except Exception:
        pass
    bounds = document.get("bounds") or _bounds_of(document)
    if bounds:
        _ground(unreal, spawn, bounds)
    start = _start_on_street(document)
    spawn(unreal.PlayerStart, start[0], start[1], "PlayerStart")
    print("CITYGEN player start", [round(v) for v in start[0]], "yaw", round(start[1][2]))


def _ground(unreal, spawn, bounds):
    x0, y0, x1, y1 = (float(v) for v in bounds)
    pad = GROUND_PAD_M
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    cube = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube")
    # UE X is plan north (y), UE Y is plan east (x). The cube is 1 m; top at z = -2 cm.
    slab = spawn(unreal.StaticMeshActor, (cy * 100.0, cx * 100.0, -7.0), label="GroundSlab")
    slab.static_mesh_component.set_static_mesh(cube)
    slab.set_actor_scale3d(unreal.Vector((y1 - y0) + 2 * pad, (x1 - x0) + 2 * pad, 0.1))
    size = ((y1 - y0) + 2 * pad, (x1 - x0) + 2 * pad)
    mat = None
    if PLAN.get("M_Paving", {}).get("textures"):
        # One cube face spans the region: tile the paving every tile_m metres instead of stretching it.
        import city_materials_ue
        mat = city_materials_ue.ground_tiled(
            unreal, unreal.AssetToolsHelpers.get_asset_tools(), unreal.EditorAssetLibrary,
            unreal.MaterialEditingLibrary, MAT_DIR, "M_GroundSlab", PLAN["M_Paving"], size)
    mat = mat or unreal.EditorAssetLibrary.load_asset(MAT_DIR + "/M_Paving") \
        or unreal.EditorAssetLibrary.load_asset(MAT_DIR + "/M_Concrete")
    if mat:
        slab.static_mesh_component.set_material(0, mat)
    slab.static_mesh_component.set_collision_profile_name("BlockAll")


def _bounds_of(document):
    xs, ys = [], []
    for item in document.get("buildings") or []:
        xs.append(float(item.get("x", 0)))
        ys.append(float(item.get("y", 0)))
    if not xs:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def _start_on_street(document):
    """Middle of the longest major (else any) road, facing along it, 1.5 m up."""
    import math
    best, best_len = None, -1.0
    for road in document.get("roads") or []:
        pts = road.get("pts") or []
        if len(pts) < 2:
            continue
        length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
        rank = length * (2.0 if road.get("cls") == "major" else 1.0)
        if rank > best_len:
            best, best_len = pts, rank
    if not best:
        return (0.0, 0.0, 150.0), (0.0, 0.0, 0.0)
    i = max(0, len(best) // 2 - 1)
    a, b = best[i], best[i + 1]
    mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
    yaw = _ue_yaw_of(b[0] - a[0], b[1] - a[1])
    return (my * 100.0, mx * 100.0, 150.0), (0.0, 0.0, yaw)


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
        _actor(unreal, cube, materials.get(slot.get(kind)) or materials["metal"], prop.get("id") or kind,
               loc, (0, float(prop.get("yaw") or 0), 0), scale.get(kind, (1, 1, 1)))


def _ue_yaw_of(dx, dy):
    import math
    return 90.0 - math.degrees(math.atan2(dy, dx))


def _actor(unreal, cube, material, label, location, rotator, scale, folder="Cubes"):
    """rotator is (pitch, yaw, roll). unreal.Rotator's positional order is roll, pitch, yaw."""
    actor = _actors(unreal).spawn_actor_from_class(
        unreal.StaticMeshActor, unreal.Vector(location[0], location[1], location[2]),
        unreal.Rotator(pitch=rotator[0], yaw=rotator[1], roll=rotator[2]))
    actor.set_actor_label(str(label)[:80])
    actor.set_folder_path(OUTLINER + "/" + folder)
    mesh = actor.static_mesh_component
    mesh.set_static_mesh(cube)
    mesh.set_material(0, material)
    actor.set_actor_scale3d(unreal.Vector(scale[0], scale[1], scale[2]))
    return actor


if __name__ == "__main__":
    main()
