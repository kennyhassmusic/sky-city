"""Sky City's elevated expressways in Unreal: Interstate 35 (Austin upper decks) and the Wacker Canal Expressway (Chicago
viaduct). Places what Scripts/roads/expressway_layout.py laid out offline and Scripts/roads/blender_expressway_kit.py
modelled (SourceArt/Expressway/meshes + kit.json), and removes build_city.py's generic elevated pieces.

Why (20 Oct 2026, Kenny: "there's a weird structure that looks like a highway that runs past the capitol.. build it the
way it looks in real life"): build_city.py's "elevated" stage drew both sketch roads as one slab (actor
"ElevatedExpressways", mesh /Game/City/Meshes/SM_ElevatedExpressways, tag City_Generated) on box pillars. That actor is
removed here; build_city.py's stage now skips roads this kit builds (see its stage_elevated), so a rerun of it does not
bring the slab back.
Each kit mesh is unique geometry at its real place (decks and bents in chunks of four spans, the ramps on fill), built
round its own plan origin, so each actor stands at (oy*100, ox*100, 0) with no rotation. Collision is per-polygon
(complex as simple): the car drives the decks and ramps end to end, and hits columns, rails and sign towers.
Roads the kit hasn't built yet (style not done) keep a stand-in like the old one (XW_<ROAD>_Legacy), so the level never
loses a road between runs.
Stages: import (GLBs -> /Game/City/Expressway/Meshes, textures -> .../Textures), materials (kit slots -> materials:
        the city's asphalt, paint and galvanized instances, plus M_XW_Concrete: Poly Haven concrete tinted to the pale
        limestone grey of the Austin decks, multiplied by T_Expwy_Grime on the kit's second UV set), meshes (Nanite off,
        complex collision, no LODs), axes (checks the glTF frame against kit.json before placing), place, save
Run in the editor (lock held, PIE off): py Scripts/roads/build_expressway_ue.py [stages]
(no args = all). Writes Saved/MCPScripts/out_expressway.json. Rerunnable: place removes everything tagged SC_Expressway first.
(20 Oct 2026, agent highway-capitol)
"""
import json, math, sys, time, traceback, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_expressway.json"
LAYOUT = ROOT + "/Saved/Expressway/expressway_layout.json"
KITJ = ROOT + "/SourceArt/Expressway/kit.json"
DIR = "/Game/City/Expressway"
TAG = "SC_Expressway"
OLD = ("ElevatedExpressways", "Piers")
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
STAGES = sys.argv[1:] or ["map", "import", "materials", "meshes", "axes", "place", "save"]
MAP = "/Game/Maps/SkyCityMashup"
out = {"stages": STAGES}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def import_files(files, dest):
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", dest)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        tasks.append(t)
    AT.import_asset_tasks(tasks)
    res = []
    for t in tasks:
        res += list(t.get_editor_property("imported_object_paths") or [])
    return res


def kit():
    return json.load(open(KITJ))


def stage_map():
    """Another agent may have left a different map open (McGregor): place only into SkyCityMashup."""
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if ues.get_game_world():
        raise RuntimeError("PIE is running; stop it first")
    if ues.get_editor_world().get_path_name().split(".")[0] != MAP:
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(MAP)
    log("map", ues.get_editor_world().get_path_name())


def stage_import():
    K = kit()
    force = "reimport" in STAGES
    # catalogue pieces stay in SourceArt; meshes already imported are skipped unless their GLB is newer (or "reimport")
    files = []
    for name, m in K["meshes"].items():
        if m.get("kind") == "catalog":
            continue
        sm = mesh(name)
        glb = ROOT + "/" + m["file"]
        if sm is not None and not force:
            try:
                src = sm.get_editor_property("asset_import_data")
                stamp = src.get_first_filename() if src else ""
            except Exception:
                stamp = ""
            import os
            pkg = ROOT + "/Content" + sm.get_path_name().split(".")[0][len("/Game"):] + ".uasset"
            if os.path.exists(pkg) and os.path.getmtime(pkg) > os.path.getmtime(glb):
                continue
        files.append(glb)
    _MESH.clear()
    n = len(import_files(files, DIR + "/Meshes")) if files else 0
    tex = import_files([ROOT + "/SourceArt/Expressway/textures/" + f for f in ("T_Expwy_SignAtlas.png", "T_Expwy_Grime.png", "T_Expwy_MSE_C.png")
                        if force or not EAL.does_asset_exist(DIR + "/Textures/" + f[:-4])], DIR + "/Textures")
    for p in tex:
        a = EAL.load_asset(p.split(".")[0])
        if a:
            a.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
            if "SignAtlas" in p:
                a.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_SHARPEN4)
            EAL.save_loaded_asset(a)
    log("import", {"meshes": n, "files": [f.split("/")[-1] for f in files], "textures": len(tex)})


_MESH = {}


def mesh(name):
    if name in _MESH:
        return _MESH[name]
    found = None
    for p in EAL.list_assets(DIR + "/Meshes", recursive=True):
        if p.split("/")[-1].split(".")[0] == name and EAL.find_asset_data(p).asset_class_path.asset_name == "StaticMesh":
            found = EAL.load_asset(p.split(".")[0])
            break
    _MESH[name] = found
    return found


# ------------------------------------------------------------------------------------------------ materials
def X(m, cls, x, y):
    return MEL.create_material_expression(m, cls, x, y)


def sparam(m, name, v, x, y):
    e = X(m, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", v)
    return e


def vparam(m, name, c, x, y):
    e = X(m, unreal.MaterialExpressionVectorParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", unreal.LinearColor(*c))
    return e


def tparam(m, name, path, sampler, x, y, uv=None):
    e = X(m, unreal.MaterialExpressionTextureSampleParameter2D, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("texture", EAL.load_asset(path))
    e.set_editor_property("sampler_type", sampler)
    if uv is not None:
        MEL.connect_material_expressions(uv, "", e, "UVs")
    return e


def concrete_master():
    """Weathered concrete: BaseColorTex (UV0 in metres / TileSize) x Tint x lerp(1, GrimeTex (UV1), GrimeAmount);
    roughness from the ARM texture's G x RoughnessScale; normal map."""
    path = DIR + "/Materials/M_XW_ConcreteMaster"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
    else:
        m = AT.create_asset("M_XW_ConcreteMaster", DIR + "/Materials", unreal.Material, unreal.MaterialFactoryNew())
    tc0 = X(m, unreal.MaterialExpressionTextureCoordinate, -1500, -200)
    tile = sparam(m, "TileSize", 2.0, -1500, -80)
    uv = X(m, unreal.MaterialExpressionDivide, -1300, -150)
    MEL.connect_material_expressions(tc0, "", uv, "A")
    MEL.connect_material_expressions(tile, "", uv, "B")
    bc = tparam(m, "BaseColorTex", "/Engine/EngineResources/WhiteSquareTexture", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR, -1050, -450, uv)
    nt = tparam(m, "NormalTex", "/Engine/EngineMaterials/FlatNormal", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL, -1050, 150, uv)
    arm = tparam(m, "ARMTex", "/Engine/EngineResources/WhiteSquareTexture", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR, -1050, 450, uv)
    tc1 = X(m, unreal.MaterialExpressionTextureCoordinate, -1500, -700)
    tc1.set_editor_property("coordinate_index", 1)
    gr = tparam(m, "GrimeTex", "/Engine/EngineResources/WhiteSquareTexture", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR, -1050, -800, tc1)
    one = X(m, unreal.MaterialExpressionConstant3Vector, -800, -950)
    one.set_editor_property("constant", unreal.LinearColor(1, 1, 1, 1))
    ga = sparam(m, "GrimeAmount", 1.0, -800, -650)
    lg = X(m, unreal.MaterialExpressionLinearInterpolate, -600, -800)
    MEL.connect_material_expressions(one, "", lg, "A")
    MEL.connect_material_expressions(gr, "RGB", lg, "B")
    MEL.connect_material_expressions(ga, "", lg, "Alpha")
    tint = vparam(m, "Tint", (1, 1, 1, 1), -800, -300)
    m1 = X(m, unreal.MaterialExpressionMultiply, -600, -450)
    MEL.connect_material_expressions(bc, "RGB", m1, "A")
    MEL.connect_material_expressions(tint, "", m1, "B")
    m2 = X(m, unreal.MaterialExpressionMultiply, -400, -600)
    MEL.connect_material_expressions(m1, "", m2, "A")
    MEL.connect_material_expressions(lg, "", m2, "B")
    MEL.connect_material_property(m2, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(nt, "RGB", unreal.MaterialProperty.MP_NORMAL)
    rs = sparam(m, "RoughnessScale", 1.0, -800, 600)
    rm = X(m, unreal.MaterialExpressionMultiply, -500, 500)
    MEL.connect_material_expressions(arm, "G", rm, "A")
    MEL.connect_material_expressions(rs, "", rm, "B")
    MEL.connect_material_property(rm, "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def mi(name, parent, scalars=None, vectors=None, textures=None):
    path = f"{DIR}/Materials/{name}"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
    else:
        m = AT.create_asset(name, f"{DIR}/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    m.set_editor_property("parent", parent if not isinstance(parent, str) else EAL.load_asset(parent))
    for k, v in (scalars or {}).items():
        MEL.set_material_instance_scalar_parameter_value(m, k, v)
    for k, v in (vectors or {}).items():
        MEL.set_material_instance_vector_parameter_value(m, k, unreal.LinearColor(*v, 1))
    for k, v in (textures or {}).items():
        MEL.set_material_instance_texture_parameter_value(m, k, EAL.load_asset(v))
    MEL.update_material_instance(m)
    EAL.save_loaded_asset(m)
    return m


PROP = "/Game/City/Street/Materials/M_StreetProp"
ST = "/Game/City/Street/Materials"
TX = "/Game/City/Street/Textures"


def flat(name, tint, rough, metal=0.0, glow=0.0, tex=None):
    v = {"Tint": tint}
    if glow:
        v["EmissiveColor"] = tint
    return mi(name, PROP, {"Roughness": rough, "Metallic": metal, "EmissiveStrength": glow}, v, {"BaseColorTex": tex} if tex else None)


def stage_materials():
    cm = concrete_master()
    cf = f"{TX}/concrete_floor_01/concrete_floor_01"
    grime = f"{DIR}/Textures/T_Expwy_Grime"
    # concrete_floor_01's mean albedo ~0.19/0.15/0.10 (see place_capitol_ue.py): a tint of ~2.4/2.6/3.2 gives the pale
    # warm limestone grey of the Austin decks (~0.46/0.40/0.32 before grime)
    slots = {
        "M_XW_Concrete": mi("MI_XW_Concrete", cm, {"TileSize": 2.2, "GrimeAmount": 1.0, "RoughnessScale": 1.0},
                            {"Tint": (2.45, 2.6, 3.1)}, {"BaseColorTex": cf + "_diff_2k", "NormalTex": cf + "_nor_gl_2k",
                                                          "ARMTex": cf + "_arm_2k", "GrimeTex": grime}),
        "M_XW_MSE": mi("MI_XW_MSE", cm, {"TileSize": 3.05, "GrimeAmount": 0.8, "RoughnessScale": 1.0},
                       {"Tint": (1.05, 1.08, 1.12)}, {"BaseColorTex": f"{DIR}/Textures/T_Expwy_MSE_C", "NormalTex": cf + "_nor_gl_2k",
                                                      "ARMTex": cf + "_arm_2k", "GrimeTex": grime}),
        "M_XW_Asphalt": EAL.load_asset(f"{ST}/MI_AsphaltWorn") or EAL.load_asset(f"{ST}/MI_Asphalt"),
        "M_XW_PaintWhite": EAL.load_asset(f"{ST}/MI_PaintWhite"),
        "M_XW_PaintYellow": EAL.load_asset(f"{ST}/MI_PaintYellow"),
        "M_XW_Galv": EAL.load_asset(f"{ST}/MI_Galvanized"),
        "M_XW_SignBack": EAL.load_asset(f"{ST}/MI_SignBack"),
        "M_XW_Pipe": flat("MI_XW_Pipe", (0.025, 0.025, 0.027), 0.55),
        "M_XW_Bearing": flat("MI_XW_Bearing", (0.03, 0.03, 0.03), 0.8),
        "M_XW_JointSteel": flat("MI_XW_JointSteel", (0.07, 0.07, 0.075), 0.45, 0.8),
        "M_XW_WeatheringSteel": flat("MI_XW_WeatheringSteel", (0.16, 0.07, 0.035), 0.75, 0.25),
        "M_XW_PaintedSteel": flat("MI_XW_PaintedSteel", (0.2, 0.08, 0.05), 0.6, 0.3),
        "M_XW_Grating": flat("MI_XW_Grating", (0.25, 0.25, 0.26), 0.6, 0.7),
        "M_XW_Lens": flat("MI_XW_Lens", (1.0, 0.78, 0.5), 0.3, 0.0, 4.0),
        "M_XW_SignFace": flat("MI_XW_SignFace", (1.0, 1.0, 1.0), 0.45, 0.0, 0.0, f"{DIR}/Textures/T_Expwy_SignAtlas"),
    }
    n = 0
    miss = set()
    for p in EAL.list_assets(DIR + "/Meshes", recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name != "StaticMesh":
            continue
        sm = EAL.load_asset(p.split(".")[0])
        for i, sml in enumerate(sm.get_editor_property("static_materials")):
            base = str(sml.get_editor_property("material_slot_name")).split(".")[0]
            if base in slots and slots[base]:
                sm.set_material(i, slots[base])
                n += 1
            else:
                miss.add(base)
        EAL.save_loaded_asset(sm)
    log("materials", {"set": n, "unmapped": sorted(miss)})


def stage_meshes():
    """Macs run SM5 (no Nanite) and force LOD 1: Nanite off, per-polygon collision."""
    res = {}
    for name, m in kit()["meshes"].items():
        if m.get("kind") == "catalog":
            continue
        sm = mesh(name)
        if sm is None:
            res[name] = "missing"
            continue
        ns = sm.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", False)
        sm.set_editor_property("nanite_settings", ns)
        bs = sm.get_editor_property("body_setup")
        if bs:
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        EAL.save_loaded_asset(sm)
        res[name] = "ok"
    log("meshes", res)


def stage_axes():
    """The ramp fill at the east end runs from its origin westward (plan -x): in Unreal that must be -Y (Unreal Y = plan x)
    and its X extent must match plan y. A mirrored import would show +Y."""
    res = {}
    K = kit()["meshes"]
    ok = True
    for name in [n for n in K if n.endswith("_FillE")]:
        sm = mesh(name)
        if not sm:
            continue
        bb = sm.get_bounding_box()
        res[name] = [round(v) for v in (bb.min.x, bb.max.x, bb.min.y, bb.max.y, bb.min.z, bb.max.z)]
        ok = ok and abs(bb.min.y) > abs(bb.max.y) * 3
    log("axes", res)
    log("axes_ok", ok)
    if not ok:
        raise RuntimeError("kit frame not as expected (Unreal Y = plan x - ox); fix Builder.local before placing")


# ------------------------------------------------------------------------------------------------ legacy stand-in
def legacy(road_key, lay_road):
    """A stand-in like build_city's (deck slab on box pillars) for a road whose kit style isn't built yet."""
    P = unreal.GeometryScript_Primitives
    OPT = unreal.GeometryScriptPrimitiveOptions()
    plan = json.load(open(ROOT + "/Saved/Mashup/plan_v3.json"))
    r = next((x for x in plan["roads"] if x.get("name") == lay_road["plan_name"]), None)
    if not r:
        return None
    pts = [(p[1] * 100.0, p[0] * 100.0) for p in r["pts"]]
    rs = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        k = max(1, int(math.dist(a, b) / 1500.0))
        for i in range(1, k + 1):
            rs.append((a[0] + (b[0] - a[0]) * i / k, a[1] + (b[1] - a[1]) * i / k))
    s = [0.0]
    for a, b in zip(rs, rs[1:]):
        s.append(s[-1] + math.dist(a, b))
    L = s[-1]
    ramp = min(15000.0, L / 2.5)
    zs = []
    for d in s:
        f = min(1.0, d / ramp, (L - d) / ramp)
        f = f * f * (3 - 2 * f)
        zs.append(7 + (900 - 7) * f)
    T = []
    for i, (p, z) in enumerate(zip(rs, zs)):
        a = rs[max(0, i - 1)]; b = rs[min(len(rs) - 1, i + 1)]
        yaw = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        pitch = math.degrees(math.atan2(zs[min(len(zs) - 1, i + 1)] - zs[max(0, i - 1)], math.dist(a, b) or 1))
        T.append(unreal.Transform(unreal.Vector(p[0], p[1], z), unreal.Rotator(roll=0, pitch=pitch, yaw=yaw), unreal.Vector(1, 1, 1)))
    dm = unreal.DynamicMesh()
    prof = [unreal.Vector2D(-1200, -150), unreal.Vector2D(1200, -150), unreal.Vector2D(1200, 0), unreal.Vector2D(-1200, 0)]
    P.append_sweep_polygon(dm, OPT, unreal.Transform(), prof, T, False, True, 1.0, 1.0, 0.0, 1.0)
    acc = 0.0
    for i in range(1, len(rs)):
        acc += math.dist(rs[i - 1], rs[i])
        if acc >= 4000 and zs[i] > 400:
            acc = 0.0
            P.append_box(dm, OPT, unreal.Transform(unreal.Vector(rs[i][0], rs[i][1], 0), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                         220, 220, zs[i] - 150, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
    path = f"{DIR}/Meshes/SM_XW_{road_key.upper()}_Legacy"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
    for k, v in (("enable_recompute_normals", True), ("enable_nanite", False), ("enable_collision", True)):
        try:
            opts.set_editor_property(k, v)
        except Exception:
            pass
    res = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, opts)
    sm = res[0] if isinstance(res, (tuple, list)) else res
    bs = sm.get_editor_property("body_setup")
    if bs:
        bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    sm.set_material(0, EAL.load_asset(f"{DIR}/Materials/MI_XW_Concrete") or EAL.load_asset("/Game/Blockout/Materials/M_BO_Asphalt"))
    EAL.save_loaded_asset(sm)
    return sm


# ------------------------------------------------------------------------------------------------ place
def spawn(sm, label, loc, folder):
    a = EAS.spawn_actor_from_object(sm, loc, unreal.Rotator(0, 0, 0))
    a.set_actor_label(label)
    a.set_folder_path(folder)
    a.tags = [TAG, "City_Generated"]
    a.set_editor_property("is_spatially_loaded", False)
    c = a.static_mesh_component
    c.set_collision_profile_name("BlockAll")
    c.set_editor_property("mobility", unreal.ComponentMobility.STATIC)
    return a


def stage_place():
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if ues.get_editor_world().get_path_name().split(".")[0] != MAP:
        raise RuntimeError("not on SkyCityMashup; run the map stage first")
    lay = json.load(open(LAYOUT))
    K = kit()["meshes"]
    removed = []
    for a in EAS.get_all_level_actors():
        tags = [str(t) for t in a.tags]
        lab = a.get_actor_label()
        if TAG in tags or (lab in OLD and "City_Generated" in tags):
            removed.append(lab)
            EAS.destroy_actor(a)
    counts = {"removed": removed, "placed": {}}
    for key, road in lay["roads"].items():
        names = sorted(n for n in K if n.startswith(f"XW_{key.upper()}_"))
        folder = f"City/Expressway/{road['label']}"
        placed = []
        if not names:
            sm = legacy(key, road)
            if sm:
                spawn(sm, f"XW_{key.upper()}_Legacy", unreal.Vector(0, 0, 0), folder)
                placed.append("legacy")
        for n in names:
            sm = mesh(n)
            if sm is None:
                placed.append(n + ":MISSING")
                continue
            ox, oy = K[n]["origin_plan"]
            spawn(sm, n, unreal.Vector(oy * 100.0, ox * 100.0, 0.0), folder)
            placed.append(n)
        counts["placed"][key] = placed
    log("place", counts)


def stage_save():
    log("save", unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True))


QUEUE = [(s, globals()["stage_" + s]) for s in STAGES if s != "reimport"]
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


open(OUT, "w").write(json.dumps({"started": time.strftime("%H:%M:%S"), "stages": STAGES}))
_h = unreal.register_slate_post_tick_callback(tick)
