"""Open-source repo prep (22 Oct 2026). Two jobs, so the McGregor maps and the blocky stand-in cars work in a clone that has
no licensed car models (the public repo leaves /Game/Vehicles/Tesla out):

  plan  list the materials the stand-ins (/Game/Vehicles/Placeholder) still take from /Game/Vehicles/Tesla, and everything
        those need from that folder in turn
  copy  copy them to /Game/Vehicles/Shared/Materials, point the copies at each other (parents, textures) and the stand-in
        meshes at the copies. The originals stay where they are for the licensed models in Kenny's own builds.
  tag   tag every part of the line-up in McGregor and McGregorNight with its car and part ("LineupCar:Semi",
        "LineupPart:Wheel_A1L", from the actor labels lineup_ue.py gives them), so the game can pick the licensed model or
        the stand-in at play (PickLineupModels in Source/SkyCity/SkysterCar.cpp)
  save  save what changed

Run in the editor: py Scripts/vehicles/shared_materials_ue.py plan copy tag save
Writes Saved/MCPScripts/out_shared_materials.json."""
import json, os, sys, traceback, unreal


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
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")


ROOT = _skycity_root()
OUT = ROOT + "/Saved/MCPScripts/out_shared_materials.json"
STAGES = [a for a in sys.argv[1:]] or ["plan"]
LICENSED = "/Game/Vehicles/Tesla/"
SRC = "/Game/Vehicles/Tesla/Materials/"
DST = "/Game/Vehicles/Shared/Materials"
STANDINS = "/Game/Vehicles/Placeholder"
MAPS = ["/Game/Maps/McGregor", "/Game/Maps/McGregorNight"]
AR = unreal.AssetRegistryHelpers.get_asset_registry()
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
out = {"stages": STAGES}


def save_out():
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)


def pkg(path):
    return str(path).split(".")[0]


def deps(package):
    o = unreal.AssetRegistryDependencyOptions(include_soft_package_references=True, include_hard_package_references=True,
                                              include_searchable_names=False, include_soft_management_references=False,
                                              include_hard_management_references=False)
    return [str(d) for d in (AR.get_dependencies(package, o) or [])]


def assets_of(folder, cls):
    return [pkg(a) for a in EAL.list_assets(folder, recursive=True)
            if str(EAL.find_asset_data(a).asset_class_path.asset_name) == cls]


def standin_meshes():
    return assets_of(STANDINS, "StaticMesh")


def needed():
    todo, need = [], set()
    for m in standin_meshes():
        todo += [d for d in deps(m) if d.startswith(LICENSED)]
    while todo:
        p = todo.pop()
        if p in need:
            continue
        need.add(p)
        todo += [d for d in deps(p) if d.startswith(LICENSED)]
    return sorted(need)


def mapped(path):
    return DST + "/" + path.rsplit("/", 1)[1]


def stage_plan():
    need = needed()
    out["need"] = need
    out["outside_materials_folder"] = [p for p in need if not p.startswith(SRC)]
    out["classes"] = {p: str(EAL.find_asset_data(p).asset_class_path.asset_name) for p in need}


def stage_copy():
    need = needed()
    bad = [p for p in need if not p.startswith(SRC)]
    if bad:
        raise RuntimeError("the stand-ins need licensed-model files outside Tesla/Materials: " + ", ".join(bad))
    remap = {p: mapped(p) for p in need}
    made = []
    for src, dst in remap.items():
        if not EAL.does_asset_exist(dst):
            EAL.duplicate_asset(src, dst)
            made.append(dst)
    out["copied"] = made
    # the copies point at each other, never back into the licensed folder
    fixed = []
    for dst in remap.values():
        a = EAL.load_asset(dst)
        if isinstance(a, unreal.MaterialInstanceConstant):
            parent = a.get_editor_property("parent")
            if parent and pkg(parent.get_path_name()) in remap:
                MEL.set_material_instance_parent(a, EAL.load_asset(remap[pkg(parent.get_path_name())]))
                fixed.append(dst + " parent")
            for name in MEL.get_texture_parameter_names(a) or []:
                t = MEL.get_material_instance_texture_parameter_value(a, name)
                if t and pkg(t.get_path_name()) in remap:
                    MEL.set_material_instance_texture_parameter_value(a, name, EAL.load_asset(remap[pkg(t.get_path_name())]))
                    fixed.append(f"{dst} {name}")
            MEL.update_material_instance(a)
        EAL.save_asset(dst, only_if_is_dirty=False)
    out["copies_repointed"] = fixed
    # the stand-in meshes use the copies
    meshes = []
    for m in standin_meshes():
        sm = EAL.load_asset(m)
        changed = False
        for i, s in enumerate(sm.get_editor_property("static_materials")):
            mi = s.get_editor_property("material_interface")
            if mi and pkg(mi.get_path_name()) in remap:
                sm.set_material(i, EAL.load_asset(remap[pkg(mi.get_path_name())]))   # the engine call: edits the mesh itself
                changed = True
        if changed:
            sm.modify()
            EAL.save_asset(m, only_if_is_dirty=False)
            meshes.append(m)
    out["meshes_repointed"] = meshes
    still = {m: [d for d in deps(m) if d.startswith(LICENSED)] for m in standin_meshes()}
    still.update({d: [x for x in deps(d) if x.startswith(LICENSED)] for d in remap.values()})
    out["still_licensed_refs"] = {k: v for k, v in still.items() if v}


def stage_tag():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    res = {}
    for m in MAPS:
        les.load_level(m)
        n = 0
        for a in eas.get_all_level_actors():
            tags = [str(t) for t in a.tags]
            if "MG_Lineup" not in tags:
                continue
            bits = a.get_actor_label().split("_", 2)          # Lineup_<Car> or Lineup_<Car>_<Part>
            if len(bits) < 2 or bits[0] != "Lineup":
                continue
            car, part = bits[1], (bits[2] if len(bits) == 3 else "Body")
            want = [t for t in tags if not t.startswith("LineupCar:") and not t.startswith("LineupPart:")]
            want += [f"LineupCar:{car}", f"LineupPart:{part}"]
            if want != tags:
                a.modify()
                a.tags = want
                n += 1
        les.save_current_level()
        res[m] = n
    out["tagged"] = res


def stage_save():
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    out["saved"] = True


try:
    for s in STAGES:
        globals()["stage_" + s]()
        out["done"] = out.get("done", []) + [s]
        save_out()
except Exception:
    out["error"] = traceback.format_exc()
save_out()
