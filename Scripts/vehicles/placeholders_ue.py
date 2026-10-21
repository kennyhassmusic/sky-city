"""Imports the blocky placeholder vehicles (Scripts/vehicles/blender_placeholder_cars.py -> SourceArt/Vehicles/Placeholder)
as /Game/Vehicles/Placeholder/<Car>/TV_<Car>_<Part>/StaticMeshes/TV_<Car>_<Part>: exactly the paths and part names of the
real third-party models under /Game/Vehicles/Tesla, because Source/SkyCity/SkysterFleet.h (SkyFleet::MeshPath) loads
whichever of the two folders applies (a car listed under [SkyFleet] PlaceholderCars in Config/DefaultGame.ini, or one
whose real model isn't in the project: the public build and the open-source repo). Modelled on lineup_ue.py's import and
materials stages. Never touches /Game/Vehicles/Tesla (the real assets are only read: their material instances are shared).
Stages (default: all four):
  import      the GLBs of every car in placeholder_parts.json (or `cars=Semi,Model3`), replacing what is there
  materials   slots by exact name -> Paint: the real car's clear-coat paint instance (MI_Paint_*, Cybertruck: bare steel
              MI_Car_Stainless), Glass: MI_Car_Glass, Headlight / Taillight / AuxLight / MarkerLight: the real lamp emissive
              instances (the car's lamp code finds them by these exact names), Trim / Tyre / Rim: three small instances of
              the street-prop material made here in /Game/Vehicles/Placeholder/Materials
  meshes      Nanite off (the M1 draws Nanite as coarse fallbacks); body: simple box collision (the Semi: two boxes, cab and
              chassis, so the low chassis isn't a wall); wheels: none (the car spawns them as non-colliding components)
  verify      every mesh path the C++ will ask for exists, with its slots, size against the real size, Nanite, collision
Run in the editor (any map; it only touches /Game/Vehicles/Placeholder):
  py Scripts/vehicles/placeholders_ue.py [import] [materials] [meshes] [verify] [cars=Semi,Model3]
Writes Saved/MCPScripts/out_placeholders.json.
The shared materials live in /Game/Vehicles/Tesla/Materials (only our own masters and parameter instances: no third-party
art, apart from the MI_Car_Atlas_* ones the placeholders don't use). If your public repo drops /Game/Vehicles/Tesla, keep that
Materials folder, or repoint SHARED below."""
import glob, json, os, re, sys, time, traceback, unreal

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
HERE = ROOT + "/Scripts/vehicles"
OUT = ROOT + "/Saved/MCPScripts/out_placeholders.json"
PF = HERE + "/placeholder_parts.json"
PARTS = json.load(open(PF if os.path.exists(PF) else ROOT + "/SourceArt/Vehicles/parts.json"))
SRC = ROOT + "/SourceArt/Vehicles/Placeholder"
DIR = "/Game/Vehicles/Placeholder"
SHARED = "/Game/Vehicles/Tesla/Materials"
LOCAL = DIR + "/Materials"
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
SML = unreal.EditorStaticMeshLibrary
ARGS = sys.argv[1:] or ["import", "materials", "meshes", "verify"]
STAGES = [a for a in ARGS if a in ("import", "materials", "meshes", "verify")]
CARS = next((a.split("=", 1)[1].split(",") for a in ARGS if a.startswith("cars=")), list(PARTS))
out = {"stages": ARGS}
# the real cars' own instances, by what the slot is
SHARED_MI = {"Glass": "MI_Car_Glass", "Headlight": "MI_Car_Headlight", "Taillight": "MI_Car_Taillight", "AuxLight": "MI_Car_AuxLight",
             "MarkerLight": "MI_Car_MarkerLight"}
PAINT_MI = {"Paint_Gold": "MI_Paint_Gold", "Paint_BlueGloss": "MI_Paint_BlueGloss", "Paint_RedGloss": "MI_Paint_RedGloss",
            "Paint_Silver": "MI_Paint_Silver", None: "MI_Car_Stainless"}
# made here (M_StreetProp: Tint, Metallic, Roughness)
LOCAL_MI = {"Trim": ((0.018, 0.018, 0.020), 0.0, 0.60), "Tyre": ((0.012, 0.012, 0.013), 0.0, 0.90), "Rim": ((0.62, 0.63, 0.66), 1.0, 0.28)}
# the Semi's two collision boxes in the car frame, cm (x0, x1, half y, z0, z1): the cab and the low chassis behind it
SEMI_BOXES = [(-25.0, 367.0, 139.0, 25.0, 386.0), (-367.0, -25.0, 110.0, 13.0, 117.0)]


def slot_base(s):
    return re.sub(r"[._]\d{3}$", "", s)


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1, default=str))


def meshes_of(cars):
    """(car, part, path) for every static mesh under /Game/Vehicles/Placeholder of those cars."""
    r = []
    for p in EAL.list_assets(DIR, recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name != "StaticMesh":
            continue
        bits = p.split(".")[0].split("/")
        if len(bits) > 5 and bits[4] in cars:
            r.append((bits[4], bits[5][len("TV_" + bits[4] + "_"):], p.split(".")[0]))
    return r


def stage_import():
    n, got = 0, {}
    for car in CARS:
        tasks = []
        for f in sorted(glob.glob(f"{SRC}/{car}/*.glb")):
            t = unreal.AssetImportTask()
            t.set_editor_property("filename", f)
            t.set_editor_property("destination_path", f"{DIR}/{car}")
            t.set_editor_property("automated", True)
            t.set_editor_property("replace_existing", True)
            t.set_editor_property("save", True)
            tasks.append(t)
        AT.import_asset_tasks(tasks)
        n += len(tasks)
        got[car] = len(tasks)
    log("import", got)


def local_mi(name, parent, col, metal, rough):
    path = f"{LOCAL}/{name}"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    x = AT.create_asset(name, LOCAL, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    x.set_editor_property("parent", parent)
    MEL.set_material_instance_scalar_parameter_value(x, "Metallic", metal)
    MEL.set_material_instance_scalar_parameter_value(x, "Roughness", rough)
    MEL.set_material_instance_vector_parameter_value(x, "Tint", unreal.LinearColor(*col, 1))
    MEL.update_material_instance(x)
    EAL.save_loaded_asset(x)
    return x


def stage_materials():
    prop = EAL.load_asset("/Game/City/Street/Materials/M_StreetProp")
    loc = {k: local_mi(f"MI_Placeholder_{k}", prop, *v) for k, v in LOCAL_MI.items()}
    missing, table, n = set(), {}, 0
    for car, part, path in meshes_of(CARS):
        sm = EAL.load_asset(path)
        rows = []
        for i, sml in enumerate(sm.get_editor_property("static_materials")):
            slot = str(sml.get_editor_property("material_slot_name"))
            base = slot_base(slot)
            hit = None
            if base == "Paint":
                name = PAINT_MI.get(PARTS[car].get("paint"), "MI_Car_Stainless")
                hit = EAL.load_asset(f"{SHARED}/{name}") if EAL.does_asset_exist(f"{SHARED}/{name}") else None
                if hit is None:
                    missing.add(name)
            elif base in SHARED_MI:
                hit = EAL.load_asset(f"{SHARED}/{SHARED_MI[base]}") if EAL.does_asset_exist(f"{SHARED}/{SHARED_MI[base]}") else None
                if hit is None:
                    missing.add(SHARED_MI[base])
            elif base in loc:
                hit = loc[base]
            if hit is not None:
                sm.set_material(i, hit)
                n += 1
            rows.append([slot, hit.get_name() if hit else None])
        table[f"{car}/{part}"] = rows
        EAL.save_loaded_asset(sm)
    log("materials", n)
    log("materials_missing", sorted(missing))
    log("slots", table)


def set_boxes(sm, boxes):
    """Replace the mesh's simple collision with these boxes ((x0, x1, half y, z0, z1) in cm)."""
    bs = sm.get_editor_property("body_setup")
    agg = bs.get_editor_property("agg_geom")
    elems = []
    for x0, x1, hy, z0, z1 in boxes:
        b = unreal.KBoxElem()
        b.set_editor_property("center", unreal.Vector((x0 + x1) / 2.0, 0.0, (z0 + z1) / 2.0))
        b.set_editor_property("x", x1 - x0)
        b.set_editor_property("y", 2 * hy)
        b.set_editor_property("z", z1 - z0)
        elems.append(b)
    agg.set_editor_property("box_elems", elems)
    bs.set_editor_property("agg_geom", agg)
    sm.modify()
    for fn in ("invalidate_physics_data", "create_physics_meshes"):             # not exposed to Python in every engine version
        if hasattr(bs, fn):
            getattr(bs, fn)()


def stage_meshes():
    n, col = 0, {}
    for car, part, path in meshes_of(CARS):
        sm = EAL.load_asset(path)
        ns = sm.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", False)
        sm.set_editor_property("nanite_settings", ns)
        SML.remove_collisions(sm)
        if part == "Body":
            if car == "Semi":
                try:
                    set_boxes(sm, SEMI_BOXES)
                except Exception:
                    col[f"{car}_semi_boxes_error"] = traceback.format_exc()
                    SML.remove_collisions(sm)
                    SML.add_simple_collisions(sm, unreal.ScriptingCollisionShapeType.BOX)
            else:
                SML.add_simple_collisions(sm, unreal.ScriptingCollisionShapeType.BOX)
            col[f"{car}/{part}"] = SML.get_simple_collision_count(sm)
        EAL.save_loaded_asset(sm)
        n += 1
    log("meshes", n)
    log("collision_boxes", col)


def stage_verify():
    """Every path SkyFleet::MeshPath will build: /Game/Vehicles/Placeholder/<Car>/TV_<Car>_<Part>/StaticMeshes/TV_<Car>_<Part>."""
    rep, bad = {}, []
    for car in CARS:
        info = PARTS[car]
        for part in info["parts"]:
            stem = f"TV_{car}_{part}"
            path = f"{DIR}/{car}/{stem}/StaticMeshes/{stem}"
            ok = EAL.does_asset_exist(path)
            row = {"path": path, "exists": ok}
            if ok:
                sm = EAL.load_asset(path)
                ext = sm.get_bounds().box_extent
                row["slots"] = [str(s.get_editor_property("material_slot_name")) for s in sm.get_editor_property("static_materials")]
                row["materials"] = [s.get_editor_property("material_interface").get_name() if s.get_editor_property("material_interface") else None
                                    for s in sm.get_editor_property("static_materials")]
                row["extent_cm"] = [round(ext.x, 1), round(ext.y, 1), round(ext.z, 1)]
                row["nanite"] = bool(sm.get_editor_property("nanite_settings").get_editor_property("enabled"))
                row["collision"] = SML.get_simple_collision_count(sm)
                row["verts"] = SML.get_number_verts(sm, 0)
                if part == "Body":
                    want = [info["size_m"][0] * 50, info["size_m"][1] * 50]
                    row["size_ok"] = abs(ext.x - want[0]) < 6 and abs(ext.y - want[1]) < 6
                else:
                    row["size_ok"] = abs(ext.x - info["parts"][part]["radius"] * 100) < 2 and abs(ext.y - info["parts"][part]["width"] * 50) < 2
                if row["nanite"] or not row["size_ok"] or (part == "Body" and not row["collision"]):
                    bad.append(path)
            else:
                bad.append(path)
            rep[f"{car}/{part}"] = row
    log("verify", rep)
    log("verify_bad", bad)
    log("verify_count", [sum(1 for r in rep.values() if r["exists"]), len(rep)])


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
