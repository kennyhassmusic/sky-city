"""Build the McGregor map (/Game/Maps/McGregor) in Unreal from Saved/McGregor/ (build_mcgregor_data.py) and the
public-domain rasters in the raw-raster folder (fetch_rasters.py; $SKYCITY_MCGREGOR_RAW, default Saved/McGregorRaw).

  map        new level from the engine's default template (sun, sky, fog), its floor removed
  textures   NAIP aerial photo tiles (12 x 4096 px over 2400 m, plus a sharper demo-lot tile) and the chain-link mask
  terrain    12 tiles from the USGS 2 m elevation (sampled at 4 m), simplified to 10 cm, aerial photo draped on top
             (M_TerrainNAIP maps world position to each tile's photo, with a close-up grass detail normal)
  roads      OSM roads draped ON the terrain mesh: asphalt, white caliche gravel, dirt tracks (heights traced from the
             Terrain_i_j actors every ~2 m, 1 cm over the terrain at the edges, 2-3 cm at the crown: no high edges;
             edges_lib.py). `roads_smooth`: the same every ~3 m, 5 points across, with the terrain's crests under the road
             rounded by fill-only smoothing (fewer hops crossing / driving along roads; not yet run in the maps). SM_MG_Roads is rewritten in place, so McGregorNight's Roads actor follows. `roads_swept` = the
             old 0.45 m swept ribbon (0.12 m over the DEM at the centreline, vertical sides)
  pad_edges  ground-coloured berms round the demo pads (the unveil lot): top edge on the pad's own top, bending down
             1.5 degrees every 0.8 m then 1:8 into the terrain (edges_lib.berm_mesh); actor Edge_PadBerm_<name>, kept
             when `demo` reruns: rerun `pad_edges` after `demo` whenever the lot's ring, raise or grade change
             (20 Oct 2026 overnight, mcgregor-edges agent: roads / roads_swept / pad_edges / pad_berm())
  buildings  OSM footprints extruded (metal sheds, concrete bunkers, steel test-stand towers), storage tanks and silos
  site       water towers, power pylons, chain-link fences, ponds and flame trenches
  demo       the unveil area from Saved/McGregor/demo_layout.json (Scripts/mcgregor/demo_layout.py): the lot graded as
             one slab (a best-fit plane over the terrain, "grade": "plane", or flat), the ramp, stage, screens, light
             masts, cranes, lines, barricades, hospitality, the white buildings (panel joints, dark base band), and the
             player start in front of the ramp run-up
  kit_unveil import only the unveil kit (SourceArt/McGregor/meshes/UV_*.glb, blender_unveil_kit.py)
  (20 Oct 2026, mcgregor-unveil agent: demo stage reworked for the real unveil layout; `kit_unveil` stage, the new kit's
  material slots in site_materials(), plane grading from the DEM grid, `buildings` list; old flat pads still work)
  (20 Oct 2026 round 2, mcgregor-fixes agent: graded_pad's "level" patches, so the ramp stands level on a flat patch of
  the lot instead of the graded slope; the ramp deck is weathered concrete (MI_RampDeck on M_StreetSurface with the city's
  concrete_floor_01 scans, metre UVs from blender_mcgregor_kit.py) with white MI_RampLine paint; `kit_ramp` stage
  reimports MG_Ramp alone)
  horizon    farmland skirt to 60 km (mirrored whole-map photo from make_overview.py), lighter haze, 10 lux sun
Run in the editor (PIE off): py Scripts/mcgregor/build_mcgregor_ue.py [stage ...]
Writes Saved/MCPScripts/out_mcg.json.
"""
import array, importlib, json, math, os, sys, time, traceback, unreal

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
sys.path.insert(0, ROOT + "/Scripts/mcgregor")
import edges_lib as EL                  # draped roads and pad berms (mcgregor-edges); reloaded so edits take effect
importlib.reload(EL)
RAS = os.environ.get("SKYCITY_MCGREGOR_RAW", os.path.join(ROOT, "Saved", "McGregorRaw"))   # raw USGS / NAIP rasters (fetch_rasters.py)
OUT = ROOT + "/Saved/MCPScripts/out_mcg.json"
MAP = "/Game/Maps/McGregor"
DIR = "/Game/McGregor"
D = json.load(open(ROOT + "/Saved/McGregor/mcgregor_data.json"))
META = json.load(open(RAS + "/rasters.json"))
DEMO = json.load(open(ROOT + "/Saved/McGregor/demo_layout.json")) if os.path.exists(ROOT + "/Saved/McGregor/demo_layout.json") else None
TAG = "MG_Generated"
# what Scripts/mcgregor/site_ue.py's kit models replace (Saved/McGregor/site_features.json, written by site_layout.py):
# the buildings / site stages leave those OSM footprints, 'works' areas, 'water_tower' footprints, storage tanks and
# spheroid water towers out, so a full rebuild followed by site_ue.py gives the same map
_SF = ROOT + "/Saved/McGregor/site_features.json"
SITE_FILTER = json.load(open(_SF)).get("osm_filter", {}) if os.path.exists(_SF) else {}


def superseded(p, key, r):
    return any(math.dist(p, q) < r for q in SITE_FILTER.get(key, []))
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
PR = unreal.GeometryScript_Primitives
STAGES = sys.argv[1:] or ["map", "textures", "materials", "kit", "terrain", "roads", "buildings", "site", "demo", "horizon", "save"]
out = {"stages": STAGES}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def U(x, y, z=0.0):
    """Local metres (x east, y north, z up) -> Unreal cm (X north, Y east)."""
    return unreal.Vector(y * 100.0, x * 100.0, z * 100.0)


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


def save_mesh(dm, name, mats, collide):
    path = f"{DIR}/Meshes/{name}"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
    for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", True), ("enable_nanite", False), ("enable_collision", collide)):
        try:
            opts.set_editor_property(k, v)
        except Exception:
            pass
    res = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, opts)
    sm = res[0] if isinstance(res, (tuple, list)) else res
    bs = sm.get_editor_property("body_setup")
    if bs:
        bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if collide else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
    for i, m in enumerate(mats):
        sm.set_material(i, m)
    EAL.save_loaded_asset(sm)
    return sm


def place(sm, label, folder, collide, shadows=False, tags=()):
    a = EAS.spawn_actor_from_object(sm, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    a.set_actor_label(label)
    a.set_folder_path(f"McGregor/{folder}")
    a.tags = [TAG] + list(tags)
    c = a.static_mesh_component
    c.set_editor_property("cast_shadow", shadows)
    c.set_collision_profile_name("BlockAll" if collide else "NoCollision")
    return a


def opts(mid):
    o = unreal.GeometryScriptPrimitiveOptions()
    o.set_editor_property("material_id", mid)
    return o


def tris(dm):
    return unreal.GeometryScript_MeshQueries.get_num_triangle_i_ds(dm)


def mi(name, parent, scalars=None, vectors=None, textures=None, switches=None):
    path = f"{DIR}/Materials/{name}"
    if EAL.does_asset_exist(path):                    # update in place: placed meshes keep pointing at it
        m = EAL.load_asset(path)
        MEL.clear_all_material_instance_parameters(m)
    else:
        m = AT.create_asset(name, f"{DIR}/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    m.set_editor_property("parent", parent)
    for k, v in (scalars or {}).items():
        MEL.set_material_instance_scalar_parameter_value(m, k, v)
    for k, v in (vectors or {}).items():
        MEL.set_material_instance_vector_parameter_value(m, k, unreal.LinearColor(*v, 1))
    for k, v in (textures or {}).items():
        MEL.set_material_instance_texture_parameter_value(m, k, EAL.load_asset(v) if isinstance(v, str) else v)
    for k, v in (switches or {}).items():
        MEL.set_material_instance_static_switch_parameter_value(m, k, v)
    MEL.update_material_instance(m)
    EAL.save_loaded_asset(m)
    return m


# ------------------------------------------------------------------ stages
def stage_map():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not EAL.does_asset_exist(MAP):
        les.new_level_from_template(MAP, "/Engine/Maps/Templates/Template_Default")
    elif unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name().split(".")[0] != MAP:
        les.load_level(MAP)
    removed = []
    for a in EAS.get_all_level_actors():
        lab = a.get_actor_label()
        if lab.startswith("Floor") or TAG in [str(t) for t in a.tags]:
            removed.append(lab)
            EAS.destroy_actor(a)
    les.save_current_level()
    log("map", {"removed": len(removed)})


def stage_textures():
    files = [f"{RAS}/{t['file']}" for t in META["tiles"]] + ([f"{RAS}/{META['demo']['file']}"] if "demo" in META else [])
    files.append(ROOT + "/SourceArt/McGregor/textures/T_ChainLink.png")
    paths = import_files(files, f"{DIR}/Textures")
    for p in paths:
        t = EAL.load_asset(p)
        if "naip" in p.lower():
            t.set_editor_property("max_texture_size", 4096)
            t.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        EAL.save_loaded_asset(t)
    log("textures", len(paths))


def terrain_master():
    """BaseColor from the tile's aerial photo by world position; a grass detail normal for close range."""
    path = f"{DIR}/Materials/M_TerrainNAIP"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    m = AT.create_asset("M_TerrainNAIP", f"{DIR}/Materials", unreal.Material, unreal.MaterialFactoryNew())

    def X(cls, x, y):
        return MEL.create_material_expression(m, cls, x, y)

    def S(name, v, x, y):
        e = X(unreal.MaterialExpressionScalarParameter, x, y)
        e.set_editor_property("parameter_name", name)
        e.set_editor_property("default_value", v)
        return e
    wp = X(unreal.MaterialExpressionWorldPosition, -1600, 0)

    def mask(rgba, x, y):
        e = X(unreal.MaterialExpressionComponentMask, x, y)
        for ch, on in zip("rgba", rgba):
            e.set_editor_property(ch, on)            # set every channel: don't rely on the defaults
        return e
    mx = mask((True, False, False, False), -1400, -100)
    my = mask((False, True, False, False), -1400, 100)
    MEL.connect_material_expressions(wp, "", mx, "")
    MEL.connect_material_expressions(wp, "", my, "")
    # u = (Y - OriginY) / Size ; v = (OriginX - X) / Size   (photo row 0 = north edge)
    su = X(unreal.MaterialExpressionSubtract, -1200, 100)
    MEL.connect_material_expressions(my, "", su, "A")
    MEL.connect_material_expressions(S("OriginY", 0.0, -1400, 250), "", su, "B")
    sv = X(unreal.MaterialExpressionSubtract, -1200, -100)
    MEL.connect_material_expressions(S("OriginX", 0.0, -1400, -250), "", sv, "A")
    MEL.connect_material_expressions(mx, "", sv, "B")
    size = S("Size", 240000.0, -1200, 300)
    du = X(unreal.MaterialExpressionDivide, -1000, 100)
    MEL.connect_material_expressions(su, "", du, "A")
    MEL.connect_material_expressions(size, "", du, "B")
    dv = X(unreal.MaterialExpressionDivide, -1000, -100)
    MEL.connect_material_expressions(sv, "", dv, "A")
    MEL.connect_material_expressions(size, "", dv, "B")
    uv = X(unreal.MaterialExpressionAppendVector, -850, 0)
    MEL.connect_material_expressions(du, "", uv, "A")
    MEL.connect_material_expressions(dv, "", uv, "B")
    photo = X(unreal.MaterialExpressionTextureSampleParameter2D, -650, -100)
    photo.set_editor_property("parameter_name", "Photo")
    photo.set_editor_property("texture", EAL.load_asset("/Engine/EngineResources/WhiteSquareTexture"))
    photo.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    MEL.connect_material_expressions(uv, "", photo, "UVs")
    tint = X(unreal.MaterialExpressionVectorParameter, -650, 150)
    tint.set_editor_property("parameter_name", "Tint")
    tint.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))
    mul = X(unreal.MaterialExpressionMultiply, -400, 0)
    MEL.connect_material_expressions(photo, "RGB", mul, "A")
    MEL.connect_material_expressions(tint, "", mul, "B")
    MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_BASE_COLOR)
    # detail normal: world-aligned grass normal, faded in strength by a parameter
    dmul = X(unreal.MaterialExpressionMultiply, -1000, 450)
    wm2 = mask((True, True, False, False), -1200, 450)
    MEL.connect_material_expressions(wp, "", wm2, "")
    MEL.connect_material_expressions(wm2, "", dmul, "A")
    MEL.connect_material_expressions(S("DetailScale", 0.004, -1200, 550), "", dmul, "B")
    dn = X(unreal.MaterialExpressionTextureSampleParameter2D, -650, 450)
    dn.set_editor_property("parameter_name", "DetailNormal")
    dn.set_editor_property("texture", EAL.load_asset("/Engine/EngineMaterials/FlatNormal"))
    dn.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    MEL.connect_material_expressions(dmul, "", dn, "UVs")
    flat = X(unreal.MaterialExpressionConstant3Vector, -650, 650)
    flat.set_editor_property("constant", unreal.LinearColor(0, 0, 1, 0))
    nl = X(unreal.MaterialExpressionLinearInterpolate, -400, 500)
    MEL.connect_material_expressions(flat, "", nl, "A")
    MEL.connect_material_expressions(dn, "RGB", nl, "B")
    MEL.connect_material_expressions(S("DetailStrength", 0.6, -650, 750), "", nl, "Alpha")
    MEL.connect_material_property(nl, "", unreal.MaterialProperty.MP_NORMAL)
    MEL.connect_material_property(S("Roughness", 0.92, -400, 300), "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


MATS = {}


def stage_materials():
    T = terrain_master()
    detail = None
    for p in EAL.list_assets("/Game/City/Street/Textures/leafy_grass", recursive=False):
        if "nor_gl" in p.lower():
            detail = EAL.load_asset(p.split(".")[0])
    for t in META["tiles"]:
        tex = EAL.load_asset(f"{DIR}/Textures/{t['file'].split('.')[0]}")
        MATS[f"T_{t['i']}_{t['j']}"] = mi(f"MI_Terrain_{t['i']}_{t['j']}", T,
                                          {"OriginX": (t["y0"] + t["size_m"]) * 100.0, "OriginY": t["x0"] * 100.0, "Size": t["size_m"] * 100.0},
                                          textures={"Photo": tex, **({"DetailNormal": detail} if detail else {})})
    if "demo" in META:
        dm = META["demo"]
        tex = EAL.load_asset(f"{DIR}/Textures/{dm['file'].split('.')[0]}")
        MATS["demo"] = mi("MI_Terrain_Demo", T, {"OriginX": (dm["y0"] + dm["size_m"]) * 100.0, "OriginY": dm["x0"] * 100.0, "Size": dm["size_m"] * 100.0},
                          textures={"Photo": tex, **({"DetailNormal": detail} if detail else {})})
    P = EAL.load_asset("/Game/City/Street/Materials/M_StreetProp")
    S = EAL.load_asset("/Game/City/Street/Materials/M_StreetSurface")
    MATS["caliche"] = mi("MI_Caliche", S, {"TileSize": 2.0, "RoughnessScale": 1.0}, {"Tint": (1.35, 1.3, 1.2)},
                         textures={k: EAL.load_asset(p.split(".")[0]) for k, p in
                                   (("BaseColorTex", next(x for x in EAL.list_assets("/Game/City/Street/Textures/gravel_floor_02") if "diff" in x.lower())),
                                    ("NormalTex", next(x for x in EAL.list_assets("/Game/City/Street/Textures/gravel_floor_02") if "nor_gl" in x.lower())))})
    MATS["dirt"] = mi("MI_Dirt", S, {"TileSize": 2.0, "RoughnessScale": 1.0}, {"Tint": (0.62, 0.52, 0.42)},
                      textures={"BaseColorTex": MATS["caliche"].get_texture_parameter_value("BaseColorTex")})
    MATS["asphalt"] = EAL.load_asset("/Game/City/Street/Materials/MI_Asphalt")
    MATS["metal"] = mi("MI_MetalSiding", P, {"Roughness": 0.62, "Metallic": 0.15}, {"Tint": (0.84, 0.85, 0.85)})   # white like the photos (was 0.70)
    MATS["roof"] = mi("MI_MetalRoof", P, {"Roughness": 0.55, "Metallic": 0.25}, {"Tint": (0.64, 0.64, 0.64)})
    # the graded unveil lot: the city asphalt, tiled larger with more macro variation so it doesn't read as a grid
    MATS["lot"] = mi("MI_LotAsphalt", MATS["asphalt"], {"TileSize": 4.5, "MacroVariation": 0.55}, {"Tint": (0.9, 0.9, 0.9)})
    MATS["concrete"] = mi("MI_ConcreteBunker", P, {"Roughness": 0.85}, {"Tint": (0.55, 0.54, 0.52)})
    MATS["steel"] = mi("MI_StandSteel", P, {"Roughness": 0.5, "Metallic": 0.7}, {"Tint": (0.28, 0.29, 0.30)})
    MATS["tank"] = mi("MI_TankWhite", P, {"Roughness": 0.45, "Metallic": 0.1}, {"Tint": (0.85, 0.86, 0.87)})
    MATS["house"] = mi("MI_HouseSiding", P, {"Roughness": 0.7}, {"Tint": (0.75, 0.70, 0.62)})
    MATS["water"] = EAL.load_asset("/Game/Blockout/Materials/M_BO_Water")
    # masked chain link (from the foliage master: masked, two-sided)
    F = EAL.load_asset("/Game/City/Street/Materials/M_Foliage")
    MATS["chainlink"] = mi("MI_ChainLink", F, {"Translucency": 0.0, "Roughness": 0.4}, {"Tint": (1, 1, 1)},
                           textures={"BaseColorTex": EAL.load_asset(f"{DIR}/Textures/T_ChainLink")})
    log("materials", sorted(MATS))


def load_mats():
    if MATS:
        return
    for p in EAL.list_assets(f"{DIR}/Materials", recursive=False):
        n = p.split("/")[-1].split(".")[0]
        MATS[n] = EAL.load_asset(p.split(".")[0])
    alias = {"caliche": "MI_Caliche", "dirt": "MI_Dirt", "metal": "MI_MetalSiding", "roof": "MI_MetalRoof", "concrete": "MI_ConcreteBunker",
             "steel": "MI_StandSteel", "tank": "MI_TankWhite", "house": "MI_HouseSiding", "chainlink": "MI_ChainLink", "demo": "MI_Terrain_Demo",
             "lot": "MI_LotAsphalt", "horizon": "MI_Horizon"}
    for k, v in alias.items():
        if v in MATS:
            MATS[k] = MATS[v]
    for t in META["tiles"]:
        MATS[f"T_{t['i']}_{t['j']}"] = MATS.get(f"MI_Terrain_{t['i']}_{t['j']}")
    MATS["asphalt"] = EAL.load_asset("/Game/City/Street/Materials/MI_Asphalt")
    MATS["water"] = EAL.load_asset("/Game/Blockout/Materials/M_BO_Water")


def stage_kit():
    import glob
    paths = import_files(sorted(glob.glob(ROOT + "/SourceArt/McGregor/meshes/*.glb")), f"{DIR}/Kit")
    log("kit", len(paths))


def kit_mesh(name):
    for p in EAL.list_assets(f"{DIR}/Kit", recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name == "StaticMesh" and p.split("/")[-1].split(".")[0] == name:
            return EAL.load_asset(p.split(".")[0])
    return None


def stage_terrain():
    load_mats()
    N, STEP = 601, 4.0
    LU = unreal.GeometryScript_List
    made = {}
    for t in META["tiles"]:
        i, j, x0, y0 = t["i"], t["j"], t["x0"], t["y0"]
        hs = array.array("f")
        with open(ROOT + f"/Saved/McGregor/terrain_{i}_{j}.f32", "rb") as fh:
            hs.frombytes(fh.read())
        verts = []
        for r in range(N):
            y = y0 + r * STEP
            for c in range(N):
                verts.append(unreal.Vector(y * 100.0, (x0 + c * STEP) * 100.0, hs[r * N + c] * 100.0))
        tl = []
        for r in range(N - 1):
            for c in range(N - 1):
                a = r * N + c
                tl.append(unreal.IntVector(a, a + 1, a + N + 1))
                tl.append(unreal.IntVector(a, a + N + 1, a + N))
        dm = unreal.DynamicMesh()
        vl = LU.convert_array_to_vector_list(verts)
        tli = LU.convert_array_to_triangle_list(tl)
        unreal.GeometryScript_MeshEdits.add_vertices_to_mesh(dm, vl[0] if isinstance(vl, tuple) else vl)
        unreal.GeometryScript_MeshEdits.add_triangles_to_mesh(dm, tli[0] if isinstance(tli, tuple) else tli, 0)
        before = tris(dm)
        so = unreal.GeometryScriptSimplifyMeshOptions()
        unreal.GeometryScript_MeshSimplification.apply_simplify_to_tolerance(dm, 10.0, so)
        n = unreal.GeometryScript_MeshQueries.get_triangle_face_normal(dm, 0)
        n = n[0] if isinstance(n, tuple) else n
        if n.z < 0:
            unreal.GeometryScript_Normals.flip_normals(dm)
        unreal.GeometryScript_Normals.set_per_vertex_normals(dm)
        unreal.GeometryScript_UVs.set_mesh_u_vs_from_planar_projection(dm, 0, unreal.Transform(), unreal.GeometryScriptMeshSelection())
        sm = save_mesh(dm, f"SM_MG_Terrain_{i}_{j}", [MATS[f"T_{i}_{j}"]], True)
        place(sm, f"Terrain_{i}_{j}", "Terrain", True, shadows=False)
        made[f"{i}_{j}"] = [before, tris(dm)]
        log("terrain_progress", made)
    log("terrain", made)


def sweep_ribbon(dm, pts, zs, width, thick, mid):
    if len(pts) < 2:
        return
    T = []
    n = len(pts)
    for k in range(n):
        a, b = pts[max(0, k - 1)], pts[min(n - 1, k + 1)]
        za, zb = zs[max(0, k - 1)], zs[min(n - 1, k + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ds = math.hypot(dx, dy) or 1.0
        yaw = math.degrees(math.atan2(dx, dy))            # local (east, north) -> Unreal yaw from +X (north) toward +Y (east)
        pitch = math.degrees(math.atan2(zb - za, ds))
        T.append(unreal.Transform(U(pts[k][0], pts[k][1], zs[k]), unreal.Rotator(roll=0, pitch=pitch, yaw=yaw), unreal.Vector(1, 1, 1)))
    w = width * 50.0
    prof = [unreal.Vector2D(-w, -thick * 100), unreal.Vector2D(w, -thick * 100), unreal.Vector2D(w, 0), unreal.Vector2D(-w, 0)]
    PR.append_sweep_polygon(dm, opts(mid), unreal.Transform(), prof, T, False, True, 1.0, 1.0, 0.0, 1.0)


def stage_roads():
    """The OSM roads draped ON the terrain mesh (mcgregor-edges, 20 Oct 2026). The old swept ribbons (`roads_swept`)
    stood 0.12-0.14 m over the 2 m DEM at their centreline with vertical sides, so on the 4 m terrain mesh (simplified to
    10 cm) their edges stood 0-1.4 m (median ~0.17 m) above the ground: the car popped up on them or ran into them.
    Now every ~2 m along and 3-5 points across, the height is traced from the Terrain_i_j actors, plus 1 cm at the edges
    and 2-3 cm at the crown (asphalt over caliche over dirt where roads overlap); any cell centre or edge midpoint where
    the terrain would poke through is lifted (edges_lib.road_mesh). Same outlines as before, mitred at bends.
    SM_MG_Roads is written in place: McGregorNight's Roads actor (same mesh asset) changes with it."""
    load_mats()
    order = ["asphalt", "caliche", "dirt"]
    T = EL.Terrain(EAS.get_all_level_actors())
    if not T.comp:
        raise RuntimeError("no Terrain_i_j actors in this level: run the terrain stage first")
    st = {}
    buf = EL.road_mesh(D["roads"], T.h, {k: i for i, k in enumerate(order)}, stats=st)
    dm = EL.finish_mesh(buf.to_dynamic_mesh())
    sm, how = EL.write_static_mesh(dm, f"{DIR}/Meshes/SM_MG_Roads", [MATS["asphalt"], MATS["caliche"], MATS["dirt"]], True)
    have = [a for a in EAS.get_all_level_actors() if a.get_actor_label() == "Roads" and TAG in [str(t) for t in a.tags]]
    for a in have:
        a.modify()
        a.static_mesh_component.set_static_mesh(sm)
    if not have:
        place(sm, "Roads", "Roads", True)
    log("roads", {"mesh": how, "verts": len(buf.v), "tris": buf.ntris(), "rows": st.get("rows"), "raised_cells": st.get("raised_cells"),
                  "max_raise_m": round(st.get("max_raise_m", 0.0), 3), "terrain_traces": T.n, "terrain_misses": T.miss, "actor": "kept" if have else "placed",
                  "material_ids": str(getattr(buf, "mat_check", None))})


def stage_roads_smooth():
    """`roads` with the terrain's crests under each road rounded (mcgregor-edges): cross-sections every ~3 m, 5 points
    across, 6 passes of fill-only smoothing inside the outline (never below the drape; the outline stays on the terrain).
    Offline (the exported terrain mesh + the car's leave-the-ground rule) it cuts launches crossing a road at 50 mph from
    ~31% to ~22% (bare terrain ~19%) and driving along one at 100 mph from ~18% to ~4% of 60 m runs; ~1.5x the triangles."""
    EL.ROAD_STEP, EL.ROAD_COLS, EL.ROAD_SMOOTH = 3.0, 5, 6
    try:
        stage_roads()
    finally:
        EL.ROAD_STEP, EL.ROAD_COLS, EL.ROAD_SMOOTH = 2.0, None, 0


def stage_roads_swept():
    """The roads as they were before 20 Oct 2026 overnight: 0.45 m ribbons swept 0.12 m (asphalt 0.14 m) over the DEM
    at the centreline, flat across, vertical sides (high edges on any cross-slope). Kept for comparison / rollback;
    destroys this map's Roads actor and recreates the mesh asset (McGregorNight then needs `roads_swept` too)."""
    load_mats()
    clear_labels(["Roads"])
    order = ["asphalt", "caliche", "dirt"]
    dm = unreal.DynamicMesh()
    counts = {k: 0 for k in order}
    for r in D["roads"]:
        if r["kind"] in ("footway", "path"):
            continue
        z = [h + 0.12 + (0.02 if r["surface"] == "asphalt" else 0.0) for h in r["z"]]
        sweep_ribbon(dm, r["pts"], z, r["w"], 0.45, order.index(r["surface"]))
        counts[r["surface"]] += 1
    unreal.GeometryScript_Normals.set_per_face_normals(dm)
    unreal.GeometryScript_UVs.set_mesh_u_vs_from_box_projection(dm, 0, unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(100, 100, 100)), unreal.GeometryScriptMeshSelection())
    sm = save_mesh(dm, "SM_MG_Roads", [MATS["asphalt"], MATS["caliche"], MATS["dirt"]], True)
    place(sm, "Roads", "Roads", True)
    log("roads", counts | {"tris": tris(dm)})


def ccw_xy(ring):
    a = sum(ring[k][0] * ring[(k + 1) % len(ring)][1] - ring[(k + 1) % len(ring)][0] * ring[k][1] for k in range(len(ring)))
    return ring if a > 0 else ring[::-1]


def stage_buildings():
    load_mats()
    kinds = {"industrial": "metal", "warehouse": "metal", "yes": "metal", "hangar": "metal", "bunker": "concrete", "tower": "steel",
             "works": "steel", "mast": "steel", "house": "house", "residential": "house", "church": "house", "garage": "metal"}
    slots = ["metal", "concrete", "steel", "house", "tank"]
    dm = unreal.DynamicMesh()
    n = 0
    for b in D["buildings"]:
        ring = b["ring"]
        if len(ring) < 3:
            continue
        if b["kind"] in SITE_FILTER.get("skip_kinds", []) or superseded((sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)), "buildings", 3.0):
            continue                                       # a site_ue.py kit model stands here
        # Unreal XY of local (x, y) is (y, x): swapping axes mirrors, so wind the ring for Unreal space
        pts = ccw_xy([(p[1] * 100.0, p[0] * 100.0) for p in ring])
        mid = slots.index(kinds.get(b["kind"], "metal"))
        PR.append_simple_extrude_polygon(dm, opts(mid), unreal.Transform(unreal.Vector(0, 0, b["z"] * 100.0), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                         [unreal.Vector2D(x, y) for x, y in pts], (b["h"] + 0.3) * 100.0, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        n += 1
    for tk in D["tanks"]:
        if tk["kind"] in SITE_FILTER.get("skip_tank_kinds", []):
            continue                                       # site_ue.py places kit tanks from the OSM shapes
        PR.append_cylinder(dm, opts(4), unreal.Transform(U(tk["p"][0], tk["p"][1], tk["z"] - 0.2), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                           tk["r"] * 100.0, (tk["h"] + 0.2) * 100.0, 20, 1, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        if tk["kind"] == "silo":
            PR.append_cone(dm, opts(4), unreal.Transform(U(tk["p"][0], tk["p"][1], tk["z"] + tk["h"]), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                           tk["r"] * 100.0, 10.0, tk["r"] * 60.0, 20, 1, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
    unreal.GeometryScript_Normals.set_per_face_normals(dm)
    unreal.GeometryScript_UVs.set_mesh_u_vs_from_box_projection(dm, 0, unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(400, 400, 400)), unreal.GeometryScriptMeshSelection())
    sm = save_mesh(dm, "SM_MG_Buildings", [MATS["metal"], MATS["concrete"], MATS["steel"], MATS["house"], MATS["tank"]], True)
    place(sm, "Buildings", "Buildings", True, shadows=True, tags=["NoWallRide"] if False else [])
    log("buildings", {"footprints": n, "tanks": len(D["tanks"]), "tris": tris(dm)})


def add_component(actor, cls):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    BFL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=cls, blueprint_context=None)
    h, fail = sds.add_new_subobject(params)
    return BFL.get_object(BFL.get_data(h))


def instanced(label, mesh, xfs, cull, shadows=True, folder="Site", collide=False, tags=("NoWallRide",)):
    if not xfs or mesh is None:
        return 0
    act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    act.set_actor_label(label)
    act.set_folder_path(f"McGregor/{folder}")
    act.tags = [TAG] + list(tags)
    c = add_component(act, unreal.HierarchicalInstancedStaticMeshComponent)
    c.set_static_mesh(mesh)
    c.set_editor_property("cast_shadow", shadows)
    c.set_collision_profile_name("BlockAll" if collide else "NoCollision")
    c.set_cull_distances(int(cull * 0.8), int(cull))
    c.add_instances(xfs, False, True)
    return len(xfs)


def apply_slots(sm):
    load_mats()
    street = {p.split("/")[-1].split(".")[0]: p.split(".")[0] for p in EAL.list_assets("/Game/City/Street/Materials", recursive=False)}
    for i, s in enumerate(sm.get_editor_property("static_materials")):
        slot = str(s.get_editor_property("material_slot_name")).split(".")[0]
        cand = "MI_" + slot[2:]
        if cand in MATS:
            sm.set_material(i, MATS[cand])
        elif cand in street:
            sm.set_material(i, EAL.load_asset(street[cand]))
        elif slot == "M_ChainLink":
            sm.set_material(i, MATS["chainlink"])
    EAL.save_loaded_asset(sm)


def site_materials():
    """Material instances for the McGregor kit's own slot names (others reuse the street kit's)."""
    load_mats()
    P = EAL.load_asset("/Game/City/Street/Materials/M_StreetProp")
    defs = {"M_ScaffoldSteel": ({"Roughness": 0.4, "Metallic": 0.85}, {"Tint": (0.55, 0.56, 0.58)}),
            "M_Tarp": ({"Roughness": 0.75}, {"Tint": (0.32, 0.36, 0.42)}),
            "M_TarpLight": ({"Roughness": 0.8}, {"Tint": (0.85, 0.82, 0.78)}),
            "M_TrussAlu": ({"Roughness": 0.35, "Metallic": 0.9}, {"Tint": (0.75, 0.76, 0.78)}),
            "M_LEDWall": ({"Roughness": 0.2, "EmissiveStrength": 2.0}, {"Tint": (0.05, 0.08, 0.12), "EmissiveColor": (0.2, 0.5, 1.0)}),
            "M_StageRoof": ({"Roughness": 0.5, "Metallic": 0.2}, {"Tint": (0.08, 0.08, 0.09)}),
            "M_Windscreen": ({"Roughness": 0.85}, {"Tint": (0.02, 0.02, 0.02)}),
            "M_TrailerYellow": ({"Roughness": 0.5, "Metallic": 0.3}, {"Tint": (0.85, 0.6, 0.05)}),
            "M_GantrySteel": ({"Roughness": 0.45, "Metallic": 0.7}, {"Tint": (0.12, 0.13, 0.14)}),
            "M_StackSteel": ({"Roughness": 0.5, "Metallic": 0.8}, {"Tint": (0.42, 0.40, 0.38)}),
            "M_StackTip": ({"Roughness": 0.6, "Metallic": 0.6}, {"Tint": (0.15, 0.12, 0.1)}),
            "M_Concrete": ({"Roughness": 0.85}, {"Tint": (0.6, 0.6, 0.58)}),
            "M_TowerWhite": ({"Roughness": 0.45, "Metallic": 0.3}, {"Tint": (0.86, 0.87, 0.88)}),
            "M_Insulator": ({"Roughness": 0.3}, {"Tint": (0.35, 0.25, 0.2)}),
            # the unveil kit (blender_unveil_kit.py)
            "M_StageDeck": ({"Roughness": 0.55, "Metallic": 0.1}, {"Tint": (0.16, 0.165, 0.17)}),
            "M_StageSkirt": ({"Roughness": 0.5, "Metallic": 0.2}, {"Tint": (0.07, 0.072, 0.075)}),
            "M_LEDScreen": ({"Roughness": 0.15, "EmissiveStrength": 0.12}, {"Tint": (0.015, 0.017, 0.022), "EmissiveColor": (0.2, 0.25, 0.4)}),
            "M_LEDRed": ({"Roughness": 0.3, "EmissiveStrength": 4.0}, {"Tint": (0.6, 0.02, 0.015), "EmissiveColor": (1.0, 0.05, 0.02)}),
            "M_RedLamp": ({"Roughness": 0.25, "EmissiveStrength": 3.0}, {"Tint": (0.6, 0.05, 0.03), "EmissiveColor": (1.0, 0.08, 0.03)}),
            "M_TrussBlack": ({"Roughness": 0.4, "Metallic": 0.7}, {"Tint": (0.05, 0.05, 0.055)}),
            "M_BarricadeSteel": ({"Roughness": 0.45, "Metallic": 0.6}, {"Tint": (0.035, 0.035, 0.04)}),
            "M_UmbrellaFabric": ({"Roughness": 0.9}, {"Tint": (0.025, 0.025, 0.028)}),
            "M_CraneWhite": ({"Roughness": 0.45, "Metallic": 0.3}, {"Tint": (0.78, 0.78, 0.76)}),
            "M_CraneBoom": ({"Roughness": 0.45, "Metallic": 0.5}, {"Tint": (0.12, 0.12, 0.13)}),
            "M_TrailerWhite": ({"Roughness": 0.45, "Metallic": 0.2}, {"Tint": (0.86, 0.87, 0.87)}),
            "M_BuildingWhite": ({"Roughness": 0.55, "Metallic": 0.15}, {"Tint": (0.88, 0.88, 0.86)}),
            "M_BuildingJoint": ({"Roughness": 0.6, "Metallic": 0.2}, {"Tint": (0.6, 0.6, 0.6)}),
            "M_BuildingBase": ({"Roughness": 0.7}, {"Tint": (0.05, 0.05, 0.055)}),
            "M_LinePaint": ({"Roughness": 0.6}, {"Tint": (0.85, 0.85, 0.82)})}
    for slot, (sc, vec) in defs.items():
        MATS["MI_" + slot[2:]] = mi("MI_" + slot[2:], P, sc, vec)
    # the ramp's riding surface: weathered concrete, not white (Kenny, 20 Oct round 2: "so we can see the line on it"):
    # the city's concrete_floor_01 scan (Poly Haven, CC0) on the street surface master, mesh UVs in metres (the kit
    # writes them along the curve), tinted to a light grey (albedo ~0.37), a slow brightness wobble for weathering
    S = EAL.load_asset("/Game/City/Street/Materials/M_StreetSurface")
    cf = EAL.list_assets("/Game/City/Street/Textures/concrete_floor_01", recursive=False)
    tex = {param: EAL.load_asset(next(x for x in cf if key in x.lower()).split(".")[0]) for param, key in (("BaseColorTex", "diff"), ("NormalTex", "nor_gl"), ("ARMTex", "arm"))}
    MATS["MI_RampDeck"] = mi("MI_RampDeck", S, {"TileSize": 1.5, "RoughnessScale": 1.0, "NormalStrength": 0.6, "MacroVariation": 0.5, "MetallicScale": 0.0},
                             {"Tint": (1.9, 2.3, 3.1)}, textures=tex, switches={"WorldAligned": False})
    # its painted lines (and the stage's tape lines, same slot): plain white road paint
    MATS["MI_RampLine"] = mi("MI_RampLine", P, {"Roughness": 0.5, "Metallic": 0.0}, {"Tint": (0.86, 0.86, 0.84)})


def stage_site():
    load_mats()
    site_materials()
    clear_labels(["WaterTowers", "Pylons", "Fences", "Ponds"])
    meshes = {n: kit_mesh(n) for n in ("MG_WaterTower", "MG_Pylon", "MG_ChainLink")}
    for sm in meshes.values():
        if sm:
            apply_slots(sm)
    # water towers (OSM nodes and closed ways tagged water_tower)
    wt = [unreal.Transform(U(t["p"][0], t["p"][1], t["z"]), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)) for t in D["towers"] if t["kind"] == "water_tower"]
    wt += [unreal.Transform(U(sum(p[0] for p in b["ring"]) / len(b["ring"]), sum(p[1] for p in b["ring"]) / len(b["ring"]), b["z"] + 0.3),
                            unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)) for b in D["buildings"] if b["kind"] == "water_tower"]
    wt = [t for t in wt if not superseded((t.translation.y / 100.0, t.translation.x / 100.0), "water_towers", 8.0)]
    # pylons: face along the line (toward the nearest neighbour)
    py = []
    P = D["pylons"]
    for k, p in enumerate(P):
        best = min((q for q in P if q is not p), key=lambda q: math.dist(p["p"], q["p"]), default=None)
        yaw = math.degrees(math.atan2(best["p"][0] - p["p"][0], best["p"][1] - p["p"][1])) + 90.0 if best else 0.0
        py.append(unreal.Transform(U(p["p"][0], p["p"][1], p["z"]), unreal.Rotator(roll=0, pitch=0, yaw=yaw), unreal.Vector(1, 1, 1)))
    # fences: one 3 m bay per segment
    fe = []
    for f in D["fences"]:
        pts, zs = f["pts"], f["z"]
        for k in range(len(pts) - 1):
            a, b = pts[k], pts[k + 1]
            L = math.dist(a, b)
            if L < 0.5:
                continue
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            yaw = math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))      # the bay's long axis is its local X
            fe.append(unreal.Transform(U(m[0], m[1], (zs[k] + zs[k + 1]) / 2), unreal.Rotator(roll=0, pitch=0, yaw=yaw), unreal.Vector(L / 3.0, 1, 1)))
    counts = {"water_towers": instanced("WaterTowers", meshes["MG_WaterTower"], wt, 300000),
              "pylons": instanced("Pylons", meshes["MG_Pylon"], py, 200000),
              "fence_bays": instanced("Fences", meshes["MG_ChainLink"], fe, 25000, shadows=False)}
    # ponds and flame trenches as water / dark planes
    dm = unreal.DynamicMesh()
    for p in D["ponds"]:
        if p.get("kind") == "trench":
            continue        # (mcgregor-tests, 20 Oct: flame trenches are real pits now: site_tests_ue.py + SK_T_Trench*)
        pts = ccw_xy([(q[1] * 100.0, q[0] * 100.0) for q in p["ring"]])
        PR.append_triangulated_polygon(dm, opts(0), unreal.Transform(unreal.Vector(0, 0, p["level"] * 100.0), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                       [unreal.Vector2D(x, y) for x, y in pts], True)
    if tris(dm):
        n = unreal.GeometryScript_MeshQueries.get_triangle_face_normal(dm, 0)
        n = n[0] if isinstance(n, tuple) else n
        if n.z < 0:
            unreal.GeometryScript_Normals.flip_normals(dm)
        sm = save_mesh(dm, "SM_MG_Ponds", [MATS["water"]], False)
        place(sm, "Ponds", "Site", False)
    counts["ponds"] = len(D["ponds"])
    log("site", counts)


KIT_FRONT = -90.0   # Blender-made kit pieces come out of the glTF import facing local +Y: layout yaws name the front direction


def clear_labels(prefixes):
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags] and any(a.get_actor_label().startswith(p) for p in prefixes):
            EAS.destroy_actor(a)


def stage_kit_ramp():
    """Only MG_Ramp (blender_mcgregor_kit.py -- ramp), after a change to its geometry or UVs (round 2: metre UVs for
    the concrete deck). The slots are re-pointed at the MI_* materials by the demo stage (apply_slots)."""
    paths = import_files([ROOT + "/SourceArt/McGregor/meshes/MG_Ramp.glb"], f"{DIR}/Kit")
    sm = kit_mesh("MG_Ramp")
    if sm:
        ns = sm.get_editor_property("nanite_settings")
        if ns.get_editor_property("enabled"):
            ns.set_editor_property("enabled", False)          # the M1 draws Nanite as coarse fallbacks
            sm.set_editor_property("nanite_settings", ns)
        apply_slots(sm)
    log("kit_ramp", {"paths": paths, "slots": [str(m.get_editor_property("material_slot_name")) for m in sm.get_editor_property("static_materials")] if sm else None})


def stage_kit_unveil():
    """Only the unveil kit (blender_unveil_kit.py): quicker than the full `kit` stage."""
    import glob
    paths = import_files(sorted(glob.glob(ROOT + "/SourceArt/McGregor/meshes/UV_*.glb")), f"{DIR}/Kit")
    log("kit_unveil", len(paths))


_DEM = {}


def dem_at(x, y):
    """Terrain height (local metres) from the same 4 m grids the terrain meshes were built from, bilinear."""
    W2, H2, N = META["w_m"] / 2, META["h_m"] / 2, 601
    i = max(0, min(int((x + W2) // 2400), 3))
    j = max(0, min(int((y + H2) // 2400), 2))
    if (i, j) not in _DEM:
        a = array.array("f")
        with open(ROOT + f"/Saved/McGregor/terrain_{i}_{j}.f32", "rb") as fh:
            a.frombytes(fh.read())
        _DEM[(i, j)] = a
    g = _DEM[(i, j)]
    c, r = (x - (-W2 + i * 2400)) / 4.0, (y - (-H2 + j * 2400)) / 4.0
    c0, r0 = max(0, min(int(c), N - 2)), max(0, min(int(r), N - 2))
    fc, fr = c - c0, r - r0
    return (g[r0 * N + c0] * (1 - fc) * (1 - fr) + g[r0 * N + c0 + 1] * fc * (1 - fr) +
            g[(r0 + 1) * N + c0] * (1 - fc) * fr + g[(r0 + 1) * N + c0 + 1] * fc * fr)


def _inside(p, ring):
    c = False
    for k in range(len(ring)):
        (x1, y1), (x2, y2) = ring[k], ring[(k + 1) % len(ring)]
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def _ears(ring):
    """Triangulate a simple polygon (list of (x, y)) by ear clipping -> index triples (CCW)."""
    idx = list(range(len(ring)))
    area = sum(ring[k][0] * ring[(k + 1) % len(ring)][1] - ring[(k + 1) % len(ring)][0] * ring[k][1] for k in range(len(ring)))
    if area < 0:
        idx.reverse()
    out_, guard = [], 0
    while len(idx) > 3 and guard < 1000:
        guard += 1
        for k in range(len(idx)):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            (ax, ay), (bx, by), (cx, cy) = ring[a], ring[b], ring[c]
            if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) <= 0:
                continue
            if any(_inside(ring[q], [ring[a], ring[b], ring[c]]) for q in idx if q not in (a, b, c)):
                continue
            out_.append((a, b, c))
            idx.pop(k)
            break
    out_.append(tuple(idx))
    return out_


def _lstsq(rows, z):
    """Least squares by the normal equations (no numpy in the editor's Python)."""
    n = len(rows[0])
    A = [[sum(r[i] * r[j] for r in rows) for j in range(n)] for i in range(n)]
    b = [sum(r[i] * zz for r, zz in zip(rows, z)) for i in range(n)]
    for c in range(n):                                    # Gauss-Jordan with partial pivoting
        p = max(range(c, n), key=lambda r: abs(A[r][c]))
        A[c], A[p], b[c], b[p] = A[p], A[c], b[p], b[c]
        for r in range(n):
            if r != c and A[c][c]:
                f = A[r][c] / A[c][c]
                A[r] = [x - f * y for x, y in zip(A[r], A[c])]
                b[r] -= f * b[c]
    return [b[i] / A[i][i] for i in range(n)]


def graded_pad(pad):
    """The lot as one slab graded from the terrain under it (DEM grid every 4 m):
      grade "quad"  a gently curved surface (least-squares quadratic, follows the land's overall fall)
      grade "plane" a best-fit plane;  anything else: flat (the old way)
    lifted so the 99.5th percentile of the ground clears by pad['raise'], plus smooth humps (1:7 cones) over the odd
    spike in the DEM so no ground ever pokes through; the base goes 0.5 m under the lowest ground. The top is
    tessellated (~5 m) so it can follow that surface. pad["level"]: rectangles held dead level (the ramp's footprint),
    eased back into the graded top around them. Returns (DynamicMesh, info, top(x, y))."""
    ring = pad["ring"]
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    S = [(x, y, dem_at(x, y)) for x in range(int(min(xs)), int(max(xs)) + 1, 4) for y in range(int(min(ys)), int(max(ys)) + 1, 4)
         if _inside((x, y), ring)] + [(p[0], p[1], dem_at(*p)) for p in ring]
    rz = pad.get("raise", 0.12)
    mx, my = sum(s[0] for s in S) / len(S), sum(s[1] for s in S) / len(S)
    grade = pad.get("grade", "flat")
    terms = {"quad": lambda X, Y: [1.0, X, Y, X * X, X * Y, Y * Y], "plane": lambda X, Y: [1.0, X, Y]}.get(grade, lambda X, Y: [1.0])
    co = _lstsq([terms((s[0] - mx) / 100.0, (s[1] - my) / 100.0) for s in S], [s[2] for s in S])
    surf = lambda x, y: sum(c * t for c, t in zip(co, terms((x - mx) / 100.0, (y - my) / 100.0)))
    need = sorted(s[2] - surf(s[0], s[1]) + rz for s in S)
    lift = need[int(len(need) * 0.995)] if grade in ("quad", "plane") else need[-1]
    humps = [(s[0], s[1], s[2] - surf(s[0], s[1]) + rz) for s in S if s[2] - surf(s[0], s[1]) + rz > lift]
    def top0(x, y):
        o = lift
        for hx, hy, hn in humps:
            o = max(o, hn - math.hypot(x - hx, y - hy) / 7.0)
        return surf(x, y) + o
    # level patches (round 2, mcgregor-fixes: the ramp's footprint): a rectangle along a heading held dead level at the
    # highest graded top inside it (so it never dips toward the ground the slab clears), easing back into the graded
    # surface outside along a vertical curve of radius ease_r (z = level - d^2 / 2R, d = distance outside the rectangle)
    levels = []
    for lv in pad.get("level") or []:
        hr = math.radians(lv["heading"])
        tv, nv = (math.sin(hr), math.cos(hr)), (math.cos(hr), -math.sin(hr))
        o0 = lv["p"]
        def dout(x, y, lv=lv, tv=tv, nv=nv, o0=o0):
            dx, dy = x - o0[0], y - o0[1]
            a, w = dx * tv[0] + dy * tv[1], dx * nv[0] + dy * nv[1]
            return math.hypot(max(lv["from"] - a, 0.0, a - lv["to"]), max(abs(w) - lv["half"], 0.0))
        grid = [(o0[0] + tv[0] * a + nv[0] * w, o0[1] + tv[1] * a + nv[1] * w)
                for a in [lv["from"] + (lv["to"] - lv["from"]) * k / 26.0 for k in range(27)]
                for w in [-lv["half"] + 2 * lv["half"] * k / 16.0 for k in range(17)]]
        zl = max(top0(*q) for q in grid)
        levels.append({"name": lv.get("name", "level"), "dout": dout, "z": zl, "R": lv.get("ease_r", 900.0),
                       "raised_max_m": round(zl - min(top0(*q) for q in grid), 3),
                       "inside_lot": all(_inside(q, ring) for q in (grid[0], grid[16], grid[-17], grid[-1]))})
    def top(x, y):
        v = top0(x, y)
        for lv in levels:
            d = lv["dout"](x, y)
            v = max(v, lv["z"] - d * d / (2.0 * lv["R"]))
        return v
    base = min(s[2] for s in S) - 0.5
    verts, tl = [], []
    vid = {}
    def V(x, y, z):
        k = (round(x, 3), round(y, 3), round(z, 3))
        if k not in vid:
            vid[k] = len(verts)
            verts.append(unreal.Vector(y * 100.0, x * 100.0, z * 100.0))
        return vid[k]
    tris = _ears(ring)
    for (i, j, k) in tris:                                # each ear triangle subdivided n x n
        A_, B_, C_ = ring[i], ring[j], ring[k]
        n = max(1, int(max(math.dist(A_, B_), math.dist(B_, C_), math.dist(C_, A_)) / 5.0))
        def P(a, b):                                      # barycentric: a along AB, b along AC (in steps)
            x = A_[0] + (B_[0] - A_[0]) * a / n + (C_[0] - A_[0]) * b / n
            y = A_[1] + (B_[1] - A_[1]) * a / n + (C_[1] - A_[1]) * b / n
            return V(x, y, top(x, y))
        for a in range(n):
            for b in range(n - a):
                p0, p1, p2 = P(a, b), P(a + 1, b), P(a, b + 1)
                tl.append(unreal.IntVector(p0, p2, p1))   # mirrored axes: flip the winding
                if a + b < n - 1:
                    p3 = P(a + 1, b + 1)
                    tl.append(unreal.IntVector(p1, p2, p3))
    for (i, j, k) in tris:                                # bottom
        tl.append(unreal.IntVector(V(*ring[i], base), V(*ring[j], base), V(*ring[k], base)))
    m = len(ring)
    cw = sum(ring[q][0] * ring[(q + 1) % m][1] - ring[(q + 1) % m][0] * ring[q][1] for q in range(m)) < 0
    for q in range(m):                                    # side walls, the same steps as the top's edges
        a0, b0 = ring[q], ring[(q + 1) % m]
        n = max(1, int(math.dist(a0, b0) / 5.0))
        for t in range(n):
            pa = (a0[0] + (b0[0] - a0[0]) * t / n, a0[1] + (b0[1] - a0[1]) * t / n)
            pb = (a0[0] + (b0[0] - a0[0]) * (t + 1) / n, a0[1] + (b0[1] - a0[1]) * (t + 1) / n)
            ta, tb, ba, bb = V(*pa, top(*pa)), V(*pb, top(*pb)), V(*pa, base), V(*pb, base)
            if cw:
                tl += [unreal.IntVector(ta, ba, bb), unreal.IntVector(ta, bb, tb)]
            else:
                tl += [unreal.IntVector(tb, bb, ba), unreal.IntVector(tb, ba, ta)]
    dm = unreal.DynamicMesh()
    LU = unreal.GeometryScript_List
    vl = LU.convert_array_to_vector_list(verts)
    tli = LU.convert_array_to_triangle_list(tl)
    unreal.GeometryScript_MeshEdits.add_vertices_to_mesh(dm, vl[0] if isinstance(vl, tuple) else vl)
    unreal.GeometryScript_MeshEdits.add_triangles_to_mesh(dm, tli[0] if isinstance(tli, tuple) else tli, 0)
    nrm = unreal.GeometryScript_MeshQueries.get_triangle_face_normal(dm, 0)
    nrm = nrm[0] if isinstance(nrm, tuple) else nrm
    if nrm.z < 0:
        unreal.GeometryScript_Normals.flip_normals(dm)
    steps = [top(s[0], s[1]) - s[2] for s in S]
    return dm, {"grade": grade, "samples": len(S), "lift_m": round(lift, 2), "humps": len(humps), "tris": len(tl),
                "top_at_corners": [round(top(*p), 2) for p in ring], "step_at_corners_m": [round(top(*p) - dem_at(*p), 2) for p in ring],
                "step_mean_m": round(sum(steps) / len(steps), 2), "step_max_m": round(max(steps), 2), "step_min_m": round(min(steps), 2),
                "base": round(base, 2), "levels": [{k: v for k, v in lv.items() if k not in ("dout",)} for lv in levels]}, top


def white_building(b, mats):
    """A long plain white windowless building: box walls and roof, vertical panel joints every ~4.6 m, a dark base band.
    Stands on the lowest ground under its footprint (DEM), so no wall floats."""
    yaw = b["yaw"]
    L, Wd, h = b["len"], b["wid"], b["h"]
    ca, sa = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    def P(a, w):                                  # along the long axis, across (right): local metres
        return (b["p"][0] + sa * a + ca * w, b["p"][1] + ca * a - sa * w)
    zs = [dem_at(*P(a * L / 2, w * Wd / 2)) for a in (-1, -0.5, 0, 0.5, 1) for w in (-1, 0, 1)]
    z0 = min(zs) - 0.4
    dm = unreal.DynamicMesh()
    rot = unreal.Rotator(roll=0, pitch=0, yaw=yaw)    # box local X = the long axis (compass yaw, Unreal yaw)
    def box(a, w, z, dl, dw, dh, mid):
        x, y = P(a, w)
        PR.append_box(dm, opts(mid), unreal.Transform(U(x, y, z), rot, unreal.Vector(1, 1, 1)), dl * 100.0, dw * 100.0, dh * 100.0, 0, 0, 0,
                      unreal.GeometryScriptPrimitiveOriginMode.BASE)
    top = max(zs) + h
    box(0, 0, z0, L, Wd, top - z0, 0)                                  # walls + roof
    box(0, 0, z0, L + 0.3, Wd + 0.3, (max(zs) + 2.2) - z0, 2)          # dark base band (2.2 m above the highest ground)
    box(0, 0, top, L + 0.25, Wd + 0.25, 0.35, 1)                       # parapet cap
    pitch = 4.6
    for side in (-1, 1):                                               # joints on the long faces
        for k in range(1, int(L / pitch)):
            a = -L / 2 + k * L / int(L / pitch)
            box(a, side * (Wd / 2 + 0.03), z0, 0.12, 0.08, top - z0, 1)
    for side in (-1, 1):                                               # and on the ends
        for k in range(1, int(Wd / pitch)):
            w = -Wd / 2 + k * Wd / int(Wd / pitch)
            box(side * (L / 2 + 0.03), w, z0, 0.08, 0.12, top - z0, 1)
    unreal.GeometryScript_Normals.set_per_face_normals(dm)
    unreal.GeometryScript_UVs.set_mesh_u_vs_from_box_projection(dm, 0, unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(400, 400, 400)), unreal.GeometryScriptMeshSelection())
    sm = save_mesh(dm, f"SM_MG_{b['name']}", mats, True)
    place(sm, b["name"], "Demo", True, shadows=True, tags=["UV_Building"])
    return {"z0": round(z0, 2), "top": round(top, 2), "ground_range": round(max(zs) - min(zs), 2)}


def stage_demo():
    """The unveil area, from Saved/McGregor/demo_layout.json: {name: {"p": [x, y], "yaw": deg (0 = north), ...}}."""
    load_mats()
    site_materials()
    if not DEMO:
        log("demo", "no demo_layout.json yet")
        return
    clear_labels(["Demo_", "Pad_", "WhiteBuilding", "RoadsterBuilding", "UV_"])
    for a in EAS.get_all_level_actors():                 # the buildings carry a UV_Building tag
        if "UV_Building" in [str(t) for t in a.tags]:
            EAS.destroy_actor(a)
    placed = {}
    tops = []
    # the unveil lot itself, graded first so the set pieces stand on it
    for pad in DEMO.get("pads", []):
        dm, info, _top = graded_pad(pad)                # "grade": "quad" / "plane" (follows the land) or flat (the old way)
        unreal.GeometryScript_Normals.set_per_face_normals(dm)
        unreal.GeometryScript_UVs.set_mesh_u_vs_from_box_projection(dm, 0, unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(100, 100, 100)), unreal.GeometryScriptMeshSelection())
        sm = save_mesh(dm, f"SM_MG_Pad_{pad['name']}", [MATS.get(pad.get("mat", "asphalt")) or MATS["asphalt"]], True)
        place(sm, f"Pad_{pad['name']}", "Demo", True)
        placed[f"pad_{pad['name']}"] = info
        tops.append((pad["ring"], _top))
    # painted lines and LED strips as thin ribbons 2 cm over the graded lot (flat kit stripes float or sink on a slope)
    if DEMO.get("paint"):
        dm = unreal.DynamicMesh()
        for pt in DEMO["paint"]:
            pts = []
            for a, b in zip(pt["pts"], pt["pts"][1:]):
                n = max(1, int(math.dist(a, b) / 2.0))
                pts += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
            pts.append(tuple(pt["pts"][-1]))
            zs = []
            for q in pts:
                f = next((t for r, t in tops if _inside(q, r)), None)
                zs.append((f(*q) if f else ground_at(*q)) + 0.025)
            sweep_ribbon(dm, pts, zs, pt["w"], 0.03, 1 if pt.get("mat") == "led" else 0)
        unreal.GeometryScript_Normals.set_per_face_normals(dm)
        sm = save_mesh(dm, "SM_MG_DemoLines", [MATS.get("MI_LinePaint") or MATS["caliche"], MATS.get("MI_LEDRed") or MATS["metal"]], False)
        place(sm, "Demo_Lines", "Demo", False, tags=["NoWallRide"])
        placed["paint"] = len(DEMO["paint"])
    ground = {}
    for item in DEMO["items"]:
        for p in item["at"]:
            k = (p["p"][0], p["p"][1])
            if p.get("z") is None and k not in ground:
                ground[k] = ground_at(*k)
    for item in DEMO["items"]:
        if not item["at"]:
            continue
        sm = kit_mesh(item["mesh"])
        if sm is None:
            placed[item["mesh"]] = "missing mesh"
            continue
        apply_slots(sm)
        if item.get("collide"):
            bs = sm.get_editor_property("body_setup")
            if bs:
                bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
                EAL.save_loaded_asset(sm)
        xfs = []
        for p in item["at"]:
            z = (p["z"] if p.get("z") is not None else ground[(p["p"][0], p["p"][1])]) + p.get("dz", 0.0)
            xfs.append(unreal.Transform(U(p["p"][0], p["p"][1], z), unreal.Rotator(roll=0, pitch=0, yaw=p.get("yaw", 0.0) + KIT_FRONT),
                                        unreal.Vector(*p.get("scale", (1, 1, 1)))))
        # the ramp is driven on (no NoWallRide); flying over the fleet deck is the line-up move (SC_Lineup)
        tags = () if item["mesh"] in ("MG_Ramp", "UV_Stage") else ("NoWallRide", "SC_Lineup") if item["mesh"] == "MG_FleetDeck" else ("NoWallRide",)
        placed[item["mesh"]] = instanced(f"Demo_{item['mesh']}", sm, xfs, 300000, shadows=not item.get("hidden"), folder="Demo", collide=item.get("collide", False), tags=tags)
        if item.get("hidden"):                       # collision only (the ramp's blocker)
            for a in EAS.get_all_level_actors():
                if a.get_actor_label() == f"Demo_{item['mesh']}":
                    for c in a.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent):
                        c.set_editor_property("hidden_in_game", True)
                        c.set_visibility(False)
    # the white buildings Kenny marked (newer than the public aerial photo)
    mats = [MATS.get("MI_BuildingWhite") or MATS["tank"], MATS.get("MI_BuildingJoint") or MATS["metal"], MATS.get("MI_BuildingBase") or MATS["concrete"]]
    blds = DEMO.get("buildings") or ([dict(DEMO["white_building"], name="WhiteBuilding")] if DEMO.get("white_building") else [])
    placed["buildings"] = {b["name"]: white_building(b, mats) for b in blds}
    # player start in front of the ramp run-up
    ps = [a for a in EAS.get_all_level_actors() if isinstance(a, unreal.PlayerStart)]
    st = DEMO["start"]
    loc = U(st["p"][0], st["p"][1], ground_at(st["p"][0], st["p"][1]) + 1.2)
    rot = unreal.Rotator(roll=0, pitch=0, yaw=st["yaw"])
    if ps:
        ps[0].modify()
        ps[0].set_actor_location_and_rotation(loc, rot, False, True)
    else:
        EAS.spawn_actor_from_class(unreal.PlayerStart, loc, rot)
    placed["player_start"] = [round(loc.x), round(loc.y), round(loc.z), round(st["yaw"], 1)]
    log("demo", placed)


def pad_berm(pad, T=None):
    """The edge transition round one demo pad (mcgregor-edges, 20 Oct 2026; the unveil lot stood 0.3-1.8 m over the
    ground at its edges, vertical sides the car ran into): a berm in the terrain tiles' own photo material, its top edge
    exactly on the pad's top surface (graded_pad's top, at the same boundary points the pad's top mesh uses), bending
    down 1.5 degrees every 0.8 m, then 1:8 to 10 cm under the terrain (edges_lib.berm_mesh); rounded at the corners.
    Writes SM_MG_PadBerm_<name> and (re)places the actor Edge_PadBerm_<name> (tags MG_Generated, MG_Edge, NoWallRide;
    `demo` doesn't remove it). Call it after the pad is rebuilt, or run the `pad_edges` stage after `demo`."""
    load_mats()
    T = T or EL.Terrain(EAS.get_all_level_actors())
    # follow the pad that is actually in this level: its slab's bottom vertices lie on its ring (graded_pad's side walls
    # end at one base height), so a demo_layout.json edited since the last `demo` run doesn't put the berm in the wrong place
    lr = level_ring(f"Pad_{pad['name']}")
    if lr and (len(lr) != len(pad["ring"]) or max(min(math.dist(p, q) for q in lr) for p in pad["ring"]) > 0.5):
        pad = dict(pad, ring=lr)
    _dm, info, top = graded_pad(pad)
    ring = pad["ring"]
    nseg = {}                                             # the pad top's boundary vertices: each ring edge is a side
    for (i, j, k) in _ears(ring):                         # of one ear triangle, cut into n = longest side / 5 m parts
        n = max(1, int(max(math.dist(ring[i], ring[j]), math.dist(ring[j], ring[k]), math.dist(ring[k], ring[i])) / 5.0))
        for a, b in ((i, j), (j, k), (k, i)):
            nseg[frozenset((a, b))] = n
    m = len(ring)
    loop = []
    for q in range(m):
        a0, b0 = ring[q], ring[(q + 1) % m]
        n = nseg.get(frozenset((q, (q + 1) % m)), max(1, int(math.dist(a0, b0) / 5.0)))
        loop += [(a0[0] + (b0[0] - a0[0]) * t / n, a0[1] + (b0[1] - a0[1]) * t / n) for t in range(n)]
    tops = [top(*p) for p in loop]
    exact = level_top_edge(f"Pad_{pad['name']}", ring)      # better still: the pad mesh's own top-edge vertices
    if exact:
        loop, tops = exact
    st = {"top_edge_from": "pad mesh" if exact else "graded_pad top()"}
    buf = EL.berm_mesh(loop, tops, T.h, EL.tile_index(META["tiles"]), stats=st)
    dm = EL.finish_mesh(buf.to_dynamic_mesh())
    sm, how = EL.write_static_mesh(dm, f"{DIR}/Meshes/SM_MG_PadBerm_{pad['name']}", EL.terrain_materials(META["tiles"]), True)
    label = f"Edge_PadBerm_{pad['name']}"
    clear_labels([label])
    place(sm, label, "Edges", True, tags=["MG_Edge", "NoWallRide"])
    os.makedirs(ROOT + "/Saved/McGregor/edges", exist_ok=True)
    op = ROOT + "/Saved/McGregor/edges/outlines.json"
    ol = json.load(open(op)) if os.path.exists(op) else {}
    ol.setdefault("pads", {})[pad["name"]] = [[round(x, 3), round(y, 3)] for x, y in loop]
    json.dump(ol, open(op, "w"))
    return {"mesh": how, "profiles_at": len(loop), "tris": buf.ntris(), "terrain_traces": T.n, "material_ids": str(getattr(buf, "mat_check", None)), **{k: v for k, v in st.items()},
            "pad_step_at_corners_m": info.get("step_at_corners_m")}


def level_ring(label):
    """The ring of a graded pad as built in this level (mcgregor-edges): the corners of its slab's bottom outline (the
    vertices at the slab's lowest height, ordered round their centre, collinear ones dropped). None if no such actor."""
    act = next((a for a in EAS.get_all_level_actors() if a.get_actor_label() == label), None)
    if act is None:
        return None
    dm = unreal.DynamicMesh()
    unreal.GeometryScript_AssetUtils.copy_mesh_from_static_mesh(act.static_mesh_component.static_mesh, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(),
                                                                unreal.GeometryScriptMeshReadLOD())
    vl = unreal.GeometryScript_MeshQueries.get_all_vertex_positions(dm, False)
    vl = next(e for e in vl if isinstance(e, unreal.GeometryScriptVectorList)) if isinstance(vl, tuple) else vl
    vs = unreal.GeometryScript_List.convert_vector_list_to_array(vl)
    zmin = min(v.z for v in vs)
    pts = {(round(v.y / 100.0, 3), round(v.x / 100.0, 3)) for v in vs if v.z < zmin + 1.0}
    cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    pts = sorted(pts, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    keep = []
    for k, p in enumerate(pts):
        a, b = pts[k - 1], pts[(k + 1) % len(pts)]
        cr = (p[0] - a[0]) * (b[1] - p[1]) - (p[1] - a[1]) * (b[0] - p[0])
        if abs(cr) > 0.02 * math.dist(a, p) * math.dist(p, b):            # a corner, not a point along a side
            keep.append([p[0], p[1]])
    return keep if len(keep) >= 3 else None


def level_top_edge(label, ring):
    """The top edge of the pad as built in this level (mcgregor-edges): the vertices of its upward faces that lie on the
    ring, in order round the ring, with their heights -- the berm then meets the slab's top exactly, kinks and all."""
    act = next((a for a in EAS.get_all_level_actors() if a.get_actor_label() == label), None)
    if act is None:
        return None
    dm = unreal.DynamicMesh()
    unreal.GeometryScript_AssetUtils.copy_mesh_from_static_mesh(act.static_mesh_component.static_mesh, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(),
                                                                unreal.GeometryScriptMeshReadLOD())
    vl = unreal.GeometryScript_MeshQueries.get_all_vertex_positions(dm, False)
    vl = next(e for e in vl if isinstance(e, unreal.GeometryScriptVectorList)) if isinstance(vl, tuple) else vl
    tl = unreal.GeometryScript_MeshQueries.get_all_triangle_indices(dm, False)
    tl = next(e for e in tl if isinstance(e, unreal.GeometryScriptTriangleList)) if isinstance(tl, tuple) else tl
    vs = [(v.y / 100.0, v.x / 100.0, v.z / 100.0) for v in unreal.GeometryScript_List.convert_vector_list_to_array(vl)]
    base = min(v[2] for v in vs)
    on = {}
    m = len(ring)
    for t in unreal.GeometryScript_List.convert_triangle_list_to_array(tl):
        a, b, c = vs[t.x], vs[t.y], vs[t.z]
        if min(a[2], b[2], c[2]) < base + 0.05:
            continue
        nz = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        L = math.dist(a, b) * math.dist(a, c) or 1.0
        if abs(nz) / L < 0.3:
            continue
        for v in (a, b, c):
            for k in range(m):
                p0, p1 = ring[k], ring[(k + 1) % m]
                ex, ey = p1[0] - p0[0], p1[1] - p0[1]
                L2 = ex * ex + ey * ey
                tt = ((v[0] - p0[0]) * ex + (v[1] - p0[1]) * ey) / L2
                if -1e-3 <= tt <= 1 + 1e-3 and abs((v[0] - p0[0]) * ey - (v[1] - p0[1]) * ex) / math.sqrt(L2) < 0.02:
                    key = (k + min(max(tt, 0.0), 1.0 - 1e-9)) % m
                    on[round(key, 6)] = v
                    break
    if len(on) < 3:
        return None
    pts = [on[k] for k in sorted(on)]
    return [(p[0], p[1]) for p in pts], [p[2] for p in pts]


def stage_pad_edges():
    """Berms round every demo pad (pad_berm). After `demo` (the pads), before `save`."""
    if not DEMO:
        log("pad_edges", "no demo_layout.json")
        return
    T = EL.Terrain(EAS.get_all_level_actors())
    log("pad_edges", {p["name"]: pad_berm(p, T) for p in DEMO.get("pads", [])})


def stage_horizon():
    """Farmland skirt to 60 km past the map edge (no more blue planet band below the horizon), a lighter haze.
    The skirt starts at the terrain's own edge heights, levels out, then bends down with the planet; its photo is the
    whole-map overview (make_overview.py) mirrored outward."""
    load_mats()
    clear_labels(["Horizon"])
    ov = META.get("overview")
    if ov:
        tp = f"{DIR}/Textures/{ov['file'].split('.')[0]}"
        if not EAL.does_asset_exist(tp):
            import_files([f"{RAS}/{ov['file']}"], f"{DIR}/Textures")
        tex = EAL.load_asset(tp)
        tex.set_editor_property("address_x", unreal.TextureAddress.TA_MIRROR)
        tex.set_editor_property("address_y", unreal.TextureAddress.TA_MIRROR)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        tex.set_editor_property("never_stream", True)     # world-position UVs fool the streamer into keeping the 32 px mip
        EAL.save_loaded_asset(tex)
        T = EAL.load_asset(f"{DIR}/Materials/M_TerrainNAIP")
        MATS["horizon"] = mi("MI_Horizon", T, {"OriginX": (ov["y0"] + ov["size_m"]) * 100.0, "OriginY": ov["x0"] * 100.0, "Size": ov["size_m"] * 100.0,
                                                "DetailStrength": 0.0}, textures={"Photo": tex})
    # the map edge, counter-clockwise from the south-west corner, every 4 m, with the terrain grid's heights
    W2, H2, STEP, N = META["w_m"] / 2, META["h_m"] / 2, 4.0, 601
    grids = {}

    def h(x, y):
        i = min(int((x + W2) // 2400), 3)
        j = min(int((y + H2) // 2400), 2)
        if (i, j) not in grids:
            a = array.array("f")
            with open(ROOT + f"/Saved/McGregor/terrain_{i}_{j}.f32", "rb") as fh:
                a.frombytes(fh.read())
            grids[(i, j)] = a
        c = int(round((x - (-W2 + i * 2400)) / STEP))
        r = int(round((y - (-H2 + j * 2400)) / STEP))
        return grids[(i, j)][min(r, N - 1) * N + min(c, N - 1)]
    edge, nrm = [], []
    corners = [(-W2, -H2), (W2, -H2), (W2, H2), (-W2, H2)]
    for k in range(4):
        (ax, ay), (bx, by) = corners[k], corners[(k + 1) % 4]
        n = int(round(math.hypot(bx - ax, by - ay) / STEP))
        en = ((by - ay) / math.hypot(bx - ax, by - ay), -(bx - ax) / math.hypot(bx - ax, by - ay))     # outward normal
        for q in range(n):
            x, y = ax + (bx - ax) * q / n, ay + (by - ay) * q / n
            edge.append((x, y, h(x, y) - 0.15))
            if q == 0:                                    # mitred corner: filled in below from both edges
                nrm.append(None)
            else:
                nrm.append(en)
    for k in range(len(edge)):                            # corners take the sum of the neighbouring edges' normals
        if nrm[k] is None:
            a, b = nrm[k - 1] or nrm[k - 2], nrm[(k + 1) % len(edge)]
            nrm[k] = (a[0] + b[0], a[1] + b[1])
    base = sorted(e[2] for e in edge)[len(edge) // 2]
    rings = [0.0, 60.0, 250.0, 800.0, 2500.0, 8000.0, 25000.0, 60000.0]
    verts = []
    for d in rings:
        s = min(1.0, d / 2500.0)
        s = s * s * (3 - 2 * s)
        drop = d * d / (2 * 6360000.0)                    # follow the planet's curvature
        for (x, y, z), (nx, ny) in zip(edge, nrm):
            verts.append(unreal.Vector((y + ny * d) * 100.0, (x + nx * d) * 100.0, (z + (base - z) * s - drop) * 100.0))
    M = len(edge)
    tl = []
    for r in range(len(rings) - 1):
        for k in range(M):
            a, b = r * M + k, r * M + (k + 1) % M
            tl.append(unreal.IntVector(a, b + M, b))
            tl.append(unreal.IntVector(a, a + M, b + M))
    LU = unreal.GeometryScript_List
    dm = unreal.DynamicMesh()
    vl = LU.convert_array_to_vector_list(verts)
    tli = LU.convert_array_to_triangle_list(tl)
    unreal.GeometryScript_MeshEdits.add_vertices_to_mesh(dm, vl[0] if isinstance(vl, tuple) else vl)
    unreal.GeometryScript_MeshEdits.add_triangles_to_mesh(dm, tli[0] if isinstance(tli, tuple) else tli, 0)
    n = unreal.GeometryScript_MeshQueries.get_triangle_face_normal(dm, 0)
    n = n[0] if isinstance(n, tuple) else n
    if n.z < 0:
        unreal.GeometryScript_Normals.flip_normals(dm)
    unreal.GeometryScript_Normals.set_per_vertex_normals(dm)
    unreal.GeometryScript_UVs.set_mesh_u_vs_from_planar_projection(dm, 0, unreal.Transform(), unreal.GeometryScriptMeshSelection())
    sm = save_mesh(dm, "SM_MG_Horizon", [MATS.get("horizon") or MATS["T_1_1"]], True)
    a = place(sm, "Horizon", "Terrain", True, shadows=False)
    # a 120 km mesh gets a useless, fully "occupied" distance field that shadows it black: keep it out of DF lighting
    a.static_mesh_component.set_editor_property("affect_distance_field_lighting", False)
    # haze: the template's fog (0.044 at z = -68 m) washed the photo out; Central Texas summer haze is much lighter
    for f in EAS.get_all_level_actors():
        if isinstance(f, unreal.ExponentialHeightFog):
            f.set_actor_location(unreal.Vector(0, 0, 0), False, True)
            c = f.get_component_by_class(unreal.ExponentialHeightFogComponent)
            for k, v in (("fog_density", 0.006), ("fog_height_falloff", 0.06), ("start_distance", 60000.0), ("fog_max_opacity", 0.9)):
                c.set_editor_property(k, v)
        elif isinstance(f, unreal.DirectionalLight):      # template sun was 6 lux: shadows came out sky-blue
            f.get_component_by_class(unreal.DirectionalLightComponent).set_editor_property("intensity", 10.0)
        elif isinstance(f, unreal.SkyLight):              # warm bounce from the dry fields instead of a black lower sky
            c = f.get_component_by_class(unreal.SkyLightComponent)
            c.set_editor_property("lower_hemisphere_is_black", True)      # = "lower hemisphere is solid colour"
            c.set_editor_property("lower_hemisphere_color", unreal.LinearColor(0.34, 0.29, 0.22, 1.0))
            c.recapture_sky()
        elif isinstance(f, unreal.SkyAtmosphere):         # less blue aerial perspective on the far fields
            f.get_component_by_class(unreal.SkyAtmosphereComponent).set_editor_property("aerial_pespective_view_distance_scale", 0.5)
    log("horizon", {"edge": M, "verts": len(verts), "tris": tris(dm), "base_m": round(base, 1)})


def ground_at(x, y):
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    v = U(x, y)
    hit = unreal.SystemLibrary.line_trace_single(w, unreal.Vector(v.x, v.y, 50000), unreal.Vector(v.x, v.y, -50000),
                                                 unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True)
    return hit.to_tuple()[4].z / 100.0 if hit else 0.0


def stage_save():
    log("save_level", unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level())
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
        import shutil
        if shutil.disk_usage(os.path.expanduser("~")).free / 1e9 < 6.0:
            unreal.unregister_slate_post_tick_callback(_h)
            log("error", "stopped: under 6 GB free on disk")
            return
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


_h = unreal.register_slate_post_tick_callback(tick)
