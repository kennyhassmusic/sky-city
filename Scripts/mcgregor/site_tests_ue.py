"""McGregor test stands round 2 in Unreal (mcgregor-tests agent, 20 Oct 2026): imports the new kit pieces and site meshes
(blender_site_kit.py jobs `testhw` + `tests` -> SourceArt/McGregor/site/SK_T_*, SK_Raptor*, ...), builds their materials,
cuts the flame trenches into the terrain, and drops the old dark "pond" planes the trenches had been drawn as. The kit
placements themselves live in Saved/McGregor/site_features.json (site_layout.py + tests_layout.py) and are put in the maps
by site_ue.py `clear lots place beacons save` (run it after this script, in each map).

  import     the new GLBs only (SK_T_*, SK_RaptorEngine, SK_RaptorCell, SK_VertStand(S2), SK_UpperStage, SK_DisplayBooster,
             SK_PipeRack, SK_TankTall, SK_RVacTrailer) -> /Game/McGregor/Site; Nanite off; collision complex (scorch: none);
             the soot / scorch masks (make_scorch_textures.py) -> /Game/McGregor/Textures
  materials  M_MG_TestApron (concrete with exhaust streaks from T_MG_SootStreaks in the apron's own UVs) and M_MG_TestScorch
             (masked burnt-ground skin, edge broken up by world noise) + their instances, MI_Test* tints on M_StreetProp, MI_Caliche for the pads;
             every slot of the new meshes pointed at its MI (M_Site* slots -> the site kit's MI_Site*)
  audio      the roar loop for the timed tests (make_engine_roar.py) -> /Game/McGregor/Audio/S_MG_EngineRoar (looping)
  backup     copies the terrain tiles the cuts touch (Content/McGregor/Meshes/SM_MG_Terrain_i_j.uasset) to
             Saved/McGregor/terrain_backup/<time>/ before `cut` writes them
  cut        trims the terrain tiles inside each trench rim (site_features.json tests.terrain_cuts): GeometryScript boolean
             TrimInside with a prism, written back into the same assets (shared by McGregor and McGregorNight: once is
             enough); rerun after any rebuild of build_mcgregor_ue.py's terrain stage (cutting twice is harmless)
  ponds      SM_MG_Ponds rewritten in place without the 'trench' rings (build_mcgregor_ue.py's site stage skips them now)
  place      replaces only the Site_<mesh> actors of the new meshes and of the four whose lists changed (SK_EngineStandH/V,
             SK_TankH/V), same labels / tags / folder as site_ue.py `place` (whose full rerun gives the same result)
  save       saves dirty packages (and the level)
Run in the editor (PIE off), McGregor or McGregorNight loaded:
  py Scripts/mcgregor/site_tests_ue.py [stage ...]
  McGregor: default = import materials audio backup cut ponds place save;   McGregorNight: place save
  (the meshes, materials, terrain tiles and SM_MG_Ponds are shared assets: once for both maps)
  probe    (only) lists the GeometryScript functions this needs, writes nothing
Writes Saved/MCPScripts/out_site_tests.json.
"""
import glob, json, math, os, shutil, sys, time, traceback, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_site_tests.json"
DIR = "/Game/McGregor"
SITE = DIR + "/Site"
F = json.load(open(ROOT + "/Saved/McGregor/site_features.json"))
D = json.load(open(ROOT + "/Saved/McGregor/mcgregor_data.json"))
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
PR = unreal.GeometryScript_Primitives
STAGES = sys.argv[1:] or ["import", "materials", "audio", "backup", "cut", "ponds", "place", "save"]
NEW = ("SK_T_", "SK_RaptorEngine", "SK_RaptorCell", "SK_VertStand", "SK_UpperStage", "SK_DisplayBooster", "SK_PipeRack",
       "SK_TankTall", "SK_RVacTrailer")
out = {"stages": STAGES, "map": unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name()}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1, default=str))


def U(x, y, z=0.0):
    return unreal.Vector(y * 100.0, x * 100.0, z * 100.0)


def new_meshes():
    res = {}
    for p in EAL.list_assets(SITE, recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name == "StaticMesh":
            n = p.split("/")[-1].split(".")[0]
            if n.startswith(NEW):
                res[n] = p.split(".")[0]
    return res


def collide_of():
    c = {}
    for p in F["placements"]:
        c.setdefault(p["mesh"], p.get("collide", "complex"))
    return c


# ------------------------------------------------------------------ stages
def stage_probe():
    names = {}
    for cls in ("GeometryScript_AssetUtils", "GeometryScript_MeshBooleans", "GeometryScript_Primitives"):
        c = getattr(unreal, cls, None)
        names[cls] = [n for n in dir(c) if not n.startswith("_")] if c else None
    names["bool_ops"] = [n for n in dir(unreal.GeometryScriptBooleanOperation) if n.isupper()]
    names["bool_opts"] = [n for n in dir(unreal.GeometryScriptMeshBooleanOptions()) if not n.startswith("_")][:40]
    log("probe", names)


def stage_import():
    files = [f for f in sorted(glob.glob(ROOT + "/SourceArt/McGregor/site/*.glb")) if os.path.basename(f).startswith(NEW)]
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", SITE)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        tasks.append(t)
    AT.import_asset_tasks(tasks)
    ses = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    col = collide_of()
    done = {}
    for name, path in new_meshes().items():
        sm = EAL.load_asset(path)
        ns = sm.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", False)
        sm.set_editor_property("nanite_settings", ns)
        try:
            ses.remove_collisions(sm)
        except Exception:
            pass
        mode = col.get(name, "complex")
        bs = sm.get_editor_property("body_setup")
        if bs:
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if mode != "none" else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
        EAL.save_loaded_asset(sm)
        done[name] = mode
    # masks
    tex = []
    tt = []
    for f in ("T_MG_SootStreaks.png", "T_MG_Scorch.png"):
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", ROOT + "/SourceArt/McGregor/textures/" + f)
        t.set_editor_property("destination_path", DIR + "/Textures")
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", False)
        tt.append(t)
    AT.import_asset_tasks(tt)
    for f in ("T_MG_SootStreaks", "T_MG_Scorch"):
        p = f"{DIR}/Textures/{f}"
        if EAL.does_asset_exist(p):
            t = EAL.load_asset(p)
            t.set_editor_property("srgb", False)
            t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_GRAYSCALE)
            t.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
            t.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
            EAL.save_loaded_asset(t)
            tex.append(p)
    log("import", {"files": len(files), "meshes": done, "textures": tex})


def master(name, build):
    path = f"{DIR}/Materials/{name}"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
    else:
        m = AT.create_asset(name, f"{DIR}/Materials", unreal.Material, unreal.MaterialFactoryNew())
    build(m)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def X(m, cls, x, y):
    return MEL.create_material_expression(m, cls, x, y)


def sparam(m, name, v, x, y):
    e = X(m, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", v)
    return e


def vparam(m, name, rgb, x, y):
    e = X(m, unreal.MaterialExpressionVectorParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", unreal.LinearColor(*rgb, 1))
    return e


def tparam(m, name, tex, x, y, sampler=None):
    e = X(m, unreal.MaterialExpressionTextureSampleParameter2D, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("texture", EAL.load_asset(tex))
    # our masks are linear grayscale (TC_GRAYSCALE, sRGB off); T_SkyNoise is linear colour
    e.set_editor_property("sampler_type", sampler or unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
    return e


def build_apron(m):
    """Concrete slab with the exhaust soot mask (R of T_MG_SootStreaks in the mesh UVs) and a world-space mottling so
    the slab isn't flat grey; soot is darker and rougher."""
    soot = tparam(m, "Soot", f"{DIR}/Textures/T_MG_SootStreaks", -900, 0)
    mott = tparam(m, "Mottle", "/Game/SkyCity/FX/T_SkyNoise", -900, 300, unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)   # wraps
    wp = X(m, unreal.MaterialExpressionWorldPosition, -1400, 300)
    mk = X(m, unreal.MaterialExpressionComponentMask, -1250, 300)
    for ch, on in zip("rgba", (True, True, False, False)):
        mk.set_editor_property(ch, on)
    MEL.connect_material_expressions(wp, "", mk, "")
    sc = X(m, unreal.MaterialExpressionMultiply, -1100, 300)
    MEL.connect_material_expressions(mk, "", sc, "A")
    MEL.connect_material_expressions(sparam(m, "MottleScale", 0.00021, -1250, 420), "", sc, "B")
    MEL.connect_material_expressions(sc, "", mott, "UVs")
    st = X(m, unreal.MaterialExpressionMultiply, -650, 0)
    MEL.connect_material_expressions(soot, "R", st, "A")
    MEL.connect_material_expressions(sparam(m, "SootStrength", 1.25, -900, 200), "", st, "B")
    sat = X(m, unreal.MaterialExpressionSaturate, -500, 0)
    MEL.connect_material_expressions(st, "", sat, "")
    conc = vparam(m, "Concrete", (0.56, 0.54, 0.50), -650, -250)
    conc2 = X(m, unreal.MaterialExpressionMultiply, -500, -250)          # mottled concrete: 0.85 .. 1.05
    mm = X(m, unreal.MaterialExpressionLinearInterpolate, -650, 330)
    c1 = X(m, unreal.MaterialExpressionConstant, -800, 450)
    c1.set_editor_property("r", 1.04)
    c2 = X(m, unreal.MaterialExpressionConstant, -800, 520)
    c2.set_editor_property("r", 0.86)
    MEL.connect_material_expressions(c1, "", mm, "A")
    MEL.connect_material_expressions(c2, "", mm, "B")
    MEL.connect_material_expressions(mott, "R", mm, "Alpha")
    MEL.connect_material_expressions(conc, "", conc2, "A")
    MEL.connect_material_expressions(mm, "", conc2, "B")
    lerp = X(m, unreal.MaterialExpressionLinearInterpolate, -300, -100)
    MEL.connect_material_expressions(conc2, "", lerp, "A")
    MEL.connect_material_expressions(vparam(m, "SootColor", (0.03, 0.027, 0.024), -650, -100), "", lerp, "B")
    MEL.connect_material_expressions(sat, "", lerp, "Alpha")
    MEL.connect_material_property(lerp, "", unreal.MaterialProperty.MP_BASE_COLOR)
    rl = X(m, unreal.MaterialExpressionLinearInterpolate, -300, 150)
    r0 = X(m, unreal.MaterialExpressionConstant, -450, 150)
    r0.set_editor_property("r", 0.82)
    r1 = X(m, unreal.MaterialExpressionConstant, -450, 220)
    r1.set_editor_property("r", 0.96)
    MEL.connect_material_expressions(r0, "", rl, "A")
    MEL.connect_material_expressions(r1, "", rl, "B")
    MEL.connect_material_expressions(sat, "", rl, "Alpha")
    MEL.connect_material_property(rl, "", unreal.MaterialProperty.MP_ROUGHNESS)


def build_scorch(m):
    """Masked burnt-ground skin: coverage = T_MG_Scorch.R * Strength, its edge broken up by world-space noise (ragged,
    like burnt grass) instead of a soft fade; charcoal core to dark brown edge."""
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    try:
        m.set_editor_property("opacity_mask_clip_value", 0.5)
    except Exception:
        pass
    tx = tparam(m, "Scorch", f"{DIR}/Textures/T_MG_Scorch", -900, 0)
    mul = X(m, unreal.MaterialExpressionMultiply, -650, 100)
    MEL.connect_material_expressions(tx, "R", mul, "A")
    MEL.connect_material_expressions(sparam(m, "Strength", 1.3, -900, 200), "", mul, "B")
    sat = X(m, unreal.MaterialExpressionSaturate, -500, 100)
    MEL.connect_material_expressions(mul, "", sat, "")
    wp = X(m, unreal.MaterialExpressionWorldPosition, -1400, 400)
    mk = X(m, unreal.MaterialExpressionComponentMask, -1250, 400)
    for ch, on in zip("rgba", (True, True, False, False)):
        mk.set_editor_property(ch, on)
    MEL.connect_material_expressions(wp, "", mk, "")
    sc = X(m, unreal.MaterialExpressionMultiply, -1100, 400)
    MEL.connect_material_expressions(mk, "", sc, "A")
    MEL.connect_material_expressions(sparam(m, "NoiseScale", 0.0011, -1250, 520), "", sc, "B")
    nz = tparam(m, "Noise", "/Game/SkyCity/FX/T_SkyNoise", -900, 400, unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    MEL.connect_material_expressions(sc, "", nz, "UVs")
    off = X(m, unreal.MaterialExpressionConstantBiasScale, -650, 400)
    off.set_editor_property("bias", -0.5)
    off.set_editor_property("scale", 0.45)
    MEL.connect_material_expressions(nz, "R", off, "")
    add = X(m, unreal.MaterialExpressionAdd, -300, 200)
    MEL.connect_material_expressions(sat, "", add, "A")
    MEL.connect_material_expressions(off, "", add, "B")
    MEL.connect_material_property(add, "", unreal.MaterialProperty.MP_OPACITY_MASK)
    lerp = X(m, unreal.MaterialExpressionLinearInterpolate, -300, -100)
    MEL.connect_material_expressions(vparam(m, "Edge", (0.11, 0.085, 0.06), -650, -250), "", lerp, "A")
    MEL.connect_material_expressions(vparam(m, "Core", (0.025, 0.022, 0.02), -650, -100), "", lerp, "B")
    MEL.connect_material_expressions(sat, "", lerp, "Alpha")
    MEL.connect_material_property(lerp, "", unreal.MaterialProperty.MP_BASE_COLOR)
    r = X(m, unreal.MaterialExpressionConstant, -300, 300)
    r.set_editor_property("r", 0.97)
    MEL.connect_material_property(r, "", unreal.MaterialProperty.MP_ROUGHNESS)


def mi(name, parent, scalars=None, vectors=None):
    path = f"{DIR}/Materials/{name}"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.clear_all_material_instance_parameters(m)
    else:
        m = AT.create_asset(name, f"{DIR}/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    m.set_editor_property("parent", parent)
    for k, v in (scalars or {}).items():
        MEL.set_material_instance_scalar_parameter_value(m, k, v)
    for k, v in (vectors or {}).items():
        MEL.set_material_instance_vector_parameter_value(m, k, unreal.LinearColor(*v, 1))
    MEL.update_material_instance(m)
    EAL.save_loaded_asset(m)
    return m


# new slots on M_StreetProp (Tint / Roughness / Metallic), like site_ue.py's SLOTS
TINTS = {"M_TestSootDark": ({"Roughness": 0.95}, {"Tint": (0.05, 0.045, 0.04)}),
         "M_TestNozzle": ({"Roughness": 0.45, "Metallic": 0.7}, {"Tint": (0.12, 0.11, 0.10)}),
         "M_TestPowerhead": ({"Roughness": 0.35, "Metallic": 0.8}, {"Tint": (0.55, 0.50, 0.45)}),
         "M_TestSootWhite": ({"Roughness": 0.6, "Metallic": 0.1}, {"Tint": (0.42, 0.41, 0.40)}),
         "M_TestSootWhite2": ({"Roughness": 0.5, "Metallic": 0.1}, {"Tint": (0.66, 0.65, 0.63)}),
         "M_TestCarbon": ({"Roughness": 0.5, "Metallic": 0.2}, {"Tint": (0.06, 0.06, 0.065)})}


def stage_materials():
    P = EAL.load_asset("/Game/City/Street/Materials/M_StreetProp")
    mats = {s: mi("MI_" + s[2:], P, sc, vec) for s, (sc, vec) in TINTS.items()}
    apron = master("M_MG_TestApron", build_apron)
    scorch = master("M_MG_TestScorch", build_scorch)
    mats["M_TestApron"] = mi("MI_TestApron", apron)
    mats["M_TestScorch"] = mi("MI_TestScorch", scorch, {"Strength": 1.35})
    mats["M_TestScorchLight"] = mi("MI_TestScorchLight", scorch, {"Strength": 0.95}, {"Core": (0.06, 0.05, 0.04), "Edge": (0.13, 0.11, 0.08)})
    mats["M_TestCaliche"] = EAL.load_asset(f"{DIR}/Materials/MI_Caliche")
    n, missing = 0, set()
    for name, path in new_meshes().items():
        sm = EAL.load_asset(path)
        for i, s in enumerate(sm.get_editor_property("static_materials")):
            slot = str(s.get_editor_property("material_slot_name")).split(".")[0]
            m = mats.get(slot)
            if m is None and slot.startswith("M_Site") and EAL.does_asset_exist(f"{DIR}/Materials/MI_{slot[2:]}"):
                m = EAL.load_asset(f"{DIR}/Materials/MI_{slot[2:]}")
            if m is not None:
                sm.set_material(i, m)
                n += 1
            else:
                missing.add(slot)
        EAL.save_loaded_asset(sm)
    log("materials", {"slots_set": n, "missing": sorted(missing)})


def tiles_of(poly):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    res = set()
    for x in (min(xs), max(xs)):
        for y in (min(ys), max(ys)):
            res.add((min(max(int((x + 4800) // 2400), 0), 3), min(max(int((y + 3600) // 2400), 0), 2)))
    return res


def cut_plan():
    plan = {}
    for c in F["tests"]["terrain_cuts"]:
        for t in tiles_of(c["poly"]):
            plan.setdefault(t, []).append(c)
    return plan


def stage_backup():
    dst = ROOT + "/Saved/McGregor/terrain_backup/" + time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(dst, exist_ok=True)
    done = []
    for (i, j) in cut_plan():
        src = f"{ROOT}/Content/McGregor/Meshes/SM_MG_Terrain_{i}_{j}.uasset"
        if os.path.exists(src):
            shutil.copy2(src, dst)
            done.append(os.path.basename(src))
    log("backup", {"dir": dst, "files": done})


def ccw_xy(ring):
    a = sum(ring[k][0] * ring[(k + 1) % len(ring)][1] - ring[(k + 1) % len(ring)][0] * ring[k][1] for k in range(len(ring)))
    return ring if a > 0 else ring[::-1]


def first(res):
    return res[0] if isinstance(res, (tuple, list)) else res


def stage_cut():
    AU = unreal.GeometryScript_AssetUtils
    BO = unreal.GeometryScript_MeshBooleans
    res = {}
    for (i, j), cuts in sorted(cut_plan().items()):
        path = f"{DIR}/Meshes/SM_MG_Terrain_{i}_{j}"
        sm = EAL.load_asset(path)
        dm = unreal.DynamicMesh()
        ro = unreal.GeometryScriptCopyMeshFromAssetOptions()
        lod = unreal.GeometryScriptMeshReadLOD()
        r = AU.copy_mesh_from_static_mesh(sm, dm, ro, lod)
        dm = first(r) if isinstance(first(r), unreal.DynamicMesh) else dm
        before = unreal.GeometryScript_MeshQueries.get_num_triangle_i_ds(dm)
        for c in cuts:
            tool = unreal.DynamicMesh()
            pts = ccw_xy([(p[1] * 100.0, p[0] * 100.0) for p in c["poly"]])
            o = unreal.GeometryScriptPrimitiveOptions()
            # a prism from far below to far above the ground: everything of the terrain inside the rim goes
            PR.append_simple_extrude_polygon(tool, o, unreal.Transform(unreal.Vector(0, 0, -200.0 * 100), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                             [unreal.Vector2D(x, y) for x, y in pts], 600.0 * 100, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
            bo = unreal.GeometryScriptMeshBooleanOptions()
            for k, v in (("fill_holes", False), ("simplify_output", False)):
                try:
                    bo.set_editor_property(k, v)
                except Exception:
                    pass
            BO.apply_mesh_boolean(dm, unreal.Transform(), tool, unreal.Transform(), unreal.GeometryScriptBooleanOperation.TRIM_INSIDE, bo)
        after = unreal.GeometryScript_MeshQueries.get_num_triangle_i_ds(dm)
        wo = unreal.GeometryScriptCopyMeshToAssetOptions()
        for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", True), ("replace_materials", False)):
            try:
                wo.set_editor_property(k, v)
            except Exception:
                pass
        AU.copy_mesh_to_static_mesh(dm, sm, wo, unreal.GeometryScriptMeshWriteLOD())
        bs = sm.get_editor_property("body_setup")
        if bs:
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        EAL.save_loaded_asset(sm)
        res[f"{i}_{j}"] = {"cuts": [c["id"] for c in cuts], "tris_before": before, "tris_after": after}
        log("cut_progress", res)
    log("cut", res)


def stage_ponds():
    dm = unreal.DynamicMesh()
    n = 0
    for p in D["ponds"]:
        if p.get("kind") == "trench":
            continue
        pts = ccw_xy([(q[1] * 100.0, q[0] * 100.0) for q in p["ring"]])
        PR.append_triangulated_polygon(dm, unreal.GeometryScriptPrimitiveOptions(), unreal.Transform(unreal.Vector(0, 0, p["level"] * 100.0), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                       [unreal.Vector2D(x, y) for x, y in pts], True)
        n += 1
    nrm = first(unreal.GeometryScript_MeshQueries.get_triangle_face_normal(dm, 0))
    if nrm.z < 0:
        unreal.GeometryScript_Normals.flip_normals(dm)
    sm = EAL.load_asset(f"{DIR}/Meshes/SM_MG_Ponds")
    wo = unreal.GeometryScriptCopyMeshToAssetOptions()
    for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", True), ("replace_materials", False)):
        try:
            wo.set_editor_property(k, v)
        except Exception:
            pass
    unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, wo, unreal.GeometryScriptMeshWriteLOD())
    sm.set_material(0, EAL.load_asset("/Game/Blockout/Materials/M_BO_Water"))
    EAL.save_loaded_asset(sm)
    log("ponds", {"kept": n, "dropped_trench_rings": sum(1 for p in D["ponds"] if p.get("kind") == "trench")})


CHANGED = ("SK_EngineStandH", "SK_EngineStandV", "SK_TankH", "SK_TankV")   # meshes whose placement lists changed (tests_layout)
KIT_FRONT = -90.0
CULL = {"SK_TankV": 160000, "SK_TankH": 160000, "SK_PipeRack": 120000, "SK_RVacTrailer": 90000}


def add_component(actor, cls):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    BFL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=cls, blueprint_context=None)
    h, fail = sds.add_new_subobject(params)
    return BFL.get_object(BFL.get_data(h))


def stage_place():
    """Like site_ue.py `place`, for the new meshes and the four whose lists changed only: their Site_<mesh> actors are
    replaced, everything else (lots, berms, other kit) is left alone. site_ue.py `clear ... place` gives the same."""
    EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    allm = {}
    for p in EAL.list_assets(SITE, recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name == "StaticMesh":
            allm[p.split("/")[-1].split(".")[0]] = p.split(".")[0]
    groups = {}
    for p in F["placements"]:
        if p["mesh"].startswith(NEW) or p["mesh"] in CHANGED:
            groups.setdefault(p["mesh"], []).append(p)
    gone = 0
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        if "MG_Site" in [str(t) for t in a.tags] and a.get_actor_label() in [f"Site_{n}" for n in groups]:
            EAS.destroy_actor(a)
            gone += 1
    placed, missing = {}, []
    for name, ps in groups.items():
        if name not in allm:
            missing.append(name)
            continue
        sm = EAL.load_asset(allm[name])
        xfs = [unreal.Transform(U(p["p"][0], p["p"][1], p["z"]), unreal.Rotator(roll=0, pitch=0, yaw=p["bearing"] + KIT_FRONT), unreal.Vector(*p["scale"])) for p in ps]
        act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        act.set_actor_label(f"Site_{name}")
        act.set_folder_path("McGregor/Site")
        act.tags = ["MG_Site", "MG_Generated", "NoWallRide"]
        c = add_component(act, unreal.HierarchicalInstancedStaticMeshComponent)
        c.set_static_mesh(sm)
        mode = ps[0].get("collide", "complex")
        c.set_collision_profile_name("NoCollision" if mode == "none" else "BlockAll")
        c.set_editor_property("cast_shadow", not name.startswith(("SK_T_Scorch", "SK_T_Pad", "SK_T_Apron")))
        cull = next((v for k, v in CULL.items() if name.startswith(k)), 0)
        if cull:
            c.set_cull_distances(int(cull * 0.8), int(cull))
        c.add_instances(xfs, False, True)
        placed[name] = len(xfs)
    log("place", {"replaced_actors": gone, "meshes": placed, "missing": missing, "instances": sum(placed.values())})


def stage_audio():
    """The engine roar loop (make_engine_roar.py) -> /Game/McGregor/Audio/S_MG_EngineRoar, looping."""
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", ROOT + "/SourceArt/McGregor/audio/S_MG_EngineRoar.wav")
    t.set_editor_property("destination_path", DIR + "/Audio")
    t.set_editor_property("automated", True)
    t.set_editor_property("replace_existing", True)
    t.set_editor_property("save", False)
    AT.import_asset_tasks([t])
    p = DIR + "/Audio/S_MG_EngineRoar"
    res = {"exists": EAL.does_asset_exist(p)}
    if res["exists"]:
        w = EAL.load_asset(p)
        try:
            w.set_editor_property("looping", True)
            res["looping"] = True
        except Exception as ex:
            res["looping"] = str(ex)
        res["duration"] = w.get_editor_property("duration")
        EAL.save_loaded_asset(w)
    log("audio", res)


def stage_save():
    log("save_dirty", unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True))


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
        t0 = time.time()
        fn()
        out.setdefault("timing", []).append([name, round(time.time() - t0, 1)])
        log("stage", name)
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        log("error", traceback.format_exc())
    finally:
        BUSY[0] = False


log("started", time.strftime("%H:%M:%S"))
_h = unreal.register_slate_post_tick_callback(tick)
