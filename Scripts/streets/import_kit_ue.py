"""Bring the street kit into Unreal: CC0 textures onto the street materials, the Blender-made props and trees,
the Poly Haven props, prop/foliage/sign materials, then every prop from street_data.json as instanced meshes.

  textures   Poly Haven surfaces (BaseColor / GL normal, green flipped / ARM) -> MI_Asphalt, MI_Sidewalk, ...
             at their real scanned size; leaf clusters, bark and sign atlases from SourceArt/StreetKit/textures
  meshes     SourceArt/StreetKit/meshes/*.glb (glTF), SourceArt/CC0/polyhaven/<asset>/*.gltf
  materials  M_StreetProp (opaque, tint/texture, emissive), M_Foliage (masked two-sided foliage),
             M_SignAtlas (picks its atlas cell from per-instance custom data), M_SignalLens (cycles red/green/yellow
             per intersection and per direction from per-instance custom data)
  props      one actor per kind (tagged SC_StreetProps) with a hierarchical instanced mesh per model;
             heights come from a trace onto whatever is below (sidewalk, grass, road, bridge)

Run in the editor (PIE off): py Scripts/streets/import_kit_ue.py [stage ...]
Stages: textures meshes materials props save  (default: all, in order). Writes Saved/MCPScripts/out_kit.json.
"""
import glob, json, math, os, sys, time, traceback, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_kit.json"
KIT = ROOT + "/SourceArt/StreetKit"
CC0 = ROOT + "/SourceArt/CC0"
D = json.load(open(ROOT + "/Saved/Streets/street_data.json"))
ATLAS = json.load(open(KIT + "/textures/sign_atlas.json"))
TEX_DIR = "/Game/City/Street/Textures"
KIT_DIR = "/Game/City/Street/Kit"
PH_DIR = "/Game/City/Street/PolyHaven"
MAT_DIR = "/Game/City/Street/Materials"
TAG = "SC_StreetProps"
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
STAGES = [a for a in sys.argv[1:]] or ["textures", "meshes", "materials", "props", "save"]
out = {"stages": STAGES}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def import_files(files, dest, extra=None):
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


# ------------------------------------------------------------------ textures
SURF = {  # MI name: (polyhaven id, tile metres, tint)
    "Asphalt": ("asphalt_02", 3.0, (0.85, 0.85, 0.85)),
    "AsphaltWorn": ("worn_asphalt", 2.0, (1.0, 1.0, 1.0)),
    "Sidewalk": ("concrete_pavement", 1.8, (1.0, 1.0, 1.0)),
    "Kerb": ("concrete_floor_01", 2.0, (1.05, 1.05, 1.05)),
    "Grass": ("leafy_grass", 2.0, (0.9, 1.0, 0.85)),
    "Gravel": ("gravel_floor_02", 2.0, (1.0, 1.0, 1.0)),
    "Paving": ("pavement_02", 2.12, (1.0, 1.0, 1.0)),
    "Path": ("concrete_floor_01", 2.0, (1.0, 1.0, 1.0)),
    "BridgeConcrete": ("concrete_floor_01", 2.0, (0.95, 0.95, 0.95)),
}


def tex_settings(t, kind):
    if kind == "normal":
        t.set_editor_property("srgb", False)
        t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        t.set_editor_property("flip_green_channel", True)       # Poly Haven GL normals -> Unreal's DirectX convention
    elif kind == "arm":
        t.set_editor_property("srgb", False)        # linear data, read by a Linear Color sampler
        t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
    EAL.save_loaded_asset(t)


def stage_textures():
    done = {}
    for ph in sorted({v[0] for v in SURF.values()}):
        files = glob.glob(f"{CC0}/polyhaven/{ph}/*.jpg")
        paths = import_files(files, f"{TEX_DIR}/{ph}")
        for p in paths:
            a = EAL.load_asset(p)
            n = p.lower()
            tex_settings(a, "normal" if "nor_gl" in n else "arm" if "_arm_" in n else "color")
        done[ph] = len(paths)
    for name, (ph, tile, tint) in SURF.items():
        mi = EAL.load_asset(f"{MAT_DIR}/MI_{name}")
        assets = {p.split("/")[-1].split(".")[0].lower(): EAL.load_asset(p.split(".")[0]) for p in EAL.list_assets(f"{TEX_DIR}/{ph}", recursive=False)}
        for key, param in (("diff", "BaseColorTex"), ("nor_gl", "NormalTex"), ("arm", "ARMTex")):
            hit = [v for k, v in assets.items() if key in k]
            if hit:
                MEL.set_material_instance_texture_parameter_value(mi, param, hit[0])
        MEL.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(*tint, 1))
        MEL.set_material_instance_scalar_parameter_value(mi, "TileSize", tile)
        MEL.set_material_instance_scalar_parameter_value(mi, "RoughnessScale", 1.0)
        MEL.update_material_instance(mi)
        EAL.save_loaded_asset(mi)
    # kit textures: leaves, bark, signs
    kit = import_files(sorted(glob.glob(f"{KIT}/textures/*.png")), f"{TEX_DIR}/Kit")
    for p in kit:
        a = EAL.load_asset(p)
        if p.endswith("_N"):
            tex_settings(a, "normal")
        else:
            a.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
            EAL.save_loaded_asset(a)
    log("textures", {"surfaces": done, "kit": len(kit)})


# ------------------------------------------------------------------ materials
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


def new_material(name):
    path = f"{MAT_DIR}/{name}"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    return AT.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())


def prop_master():
    """Opaque prop material: texture x tint, roughness, metallic, emissive colour x strength."""
    m = new_material("M_StreetProp")
    bc = tparam(m, "BaseColorTex", "/Engine/EngineResources/WhiteSquareTexture", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR, -800, -300)
    tint = vparam(m, "Tint", (1, 1, 1, 1), -800, -100)
    mul = X(m, unreal.MaterialExpressionMultiply, -500, -200)
    MEL.connect_material_expressions(bc, "RGB", mul, "A")
    MEL.connect_material_expressions(tint, "", mul, "B")
    MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_BASE_COLOR)
    nt = tparam(m, "NormalTex", "/Engine/EngineMaterials/FlatNormal", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL, -800, 100)
    MEL.connect_material_property(nt, "RGB", unreal.MaterialProperty.MP_NORMAL)
    MEL.connect_material_property(sparam(m, "Roughness", 0.5, -500, 200), "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(sparam(m, "Metallic", 0.0, -500, 300), "", unreal.MaterialProperty.MP_METALLIC)
    em = vparam(m, "EmissiveColor", (0, 0, 0, 1), -800, 450)
    es = sparam(m, "EmissiveStrength", 0.0, -800, 550)
    emm = X(m, unreal.MaterialExpressionMultiply, -500, 450)
    MEL.connect_material_expressions(em, "", emm, "A")
    MEL.connect_material_expressions(es, "", emm, "B")
    MEL.connect_material_property(emm, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def foliage_master():
    m = new_material("M_Foliage")
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    bc = tparam(m, "BaseColorTex", "/Engine/EngineResources/WhiteSquareTexture", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR, -800, -300)
    tint = vparam(m, "Tint", (1, 1, 1, 1), -800, -100)
    mul = X(m, unreal.MaterialExpressionMultiply, -500, -200)
    MEL.connect_material_expressions(bc, "RGB", mul, "A")
    MEL.connect_material_expressions(tint, "", mul, "B")
    MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(bc, "A", unreal.MaterialProperty.MP_OPACITY_MASK)
    nt = tparam(m, "NormalTex", "/Engine/EngineMaterials/FlatNormal", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL, -800, 100)
    MEL.connect_material_property(nt, "RGB", unreal.MaterialProperty.MP_NORMAL)
    MEL.connect_material_property(sparam(m, "Roughness", 0.65, -500, 200), "", unreal.MaterialProperty.MP_ROUGHNESS)
    # light through the leaves
    sss = X(m, unreal.MaterialExpressionMultiply, -500, 350)
    MEL.connect_material_expressions(mul, "", sss, "A")
    MEL.connect_material_expressions(sparam(m, "Translucency", 0.6, -800, 400), "", sss, "B")
    MEL.connect_material_property(sss, "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    m.set_editor_property("opacity_mask_clip_value", 0.4)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def sign_atlas_master():
    """UVs shifted to atlas cell = PerInstanceCustomData[0]: col = idx mod Cols, row = floor(idx / Cols)."""
    m = new_material("M_SignAtlas")
    idx = X(m, unreal.MaterialExpressionPerInstanceCustomData, -1400, 0)
    idx.set_editor_property("data_index", 0)
    cols = sparam(m, "Cols", 8.0, -1400, 150)
    fm = X(m, unreal.MaterialExpressionFmod, -1200, 0)
    MEL.connect_material_expressions(idx, "", fm, "A")
    MEL.connect_material_expressions(cols, "", fm, "B")
    dv = X(m, unreal.MaterialExpressionDivide, -1200, 150)
    MEL.connect_material_expressions(idx, "", dv, "A")
    MEL.connect_material_expressions(cols, "", dv, "B")
    fl = X(m, unreal.MaterialExpressionFloor, -1050, 150)
    MEL.connect_material_expressions(dv, "", fl, "")
    du = X(m, unreal.MaterialExpressionMultiply, -900, 0)
    MEL.connect_material_expressions(fm, "", du, "A")
    MEL.connect_material_expressions(sparam(m, "CellU", 0.125, -1200, -150), "", du, "B")
    dvv = X(m, unreal.MaterialExpressionMultiply, -900, 150)
    MEL.connect_material_expressions(fl, "", dvv, "A")
    MEL.connect_material_expressions(sparam(m, "CellV", 102 / 4096, -1050, 300), "", dvv, "B")
    ap = X(m, unreal.MaterialExpressionAppendVector, -750, 50)
    MEL.connect_material_expressions(du, "", ap, "A")
    MEL.connect_material_expressions(dvv, "", ap, "B")
    tc = X(m, unreal.MaterialExpressionTextureCoordinate, -750, -100)
    add = X(m, unreal.MaterialExpressionAdd, -600, 0)
    MEL.connect_material_expressions(tc, "", add, "A")
    MEL.connect_material_expressions(ap, "", add, "B")
    t = tparam(m, "AtlasTex", "/Engine/EngineResources/WhiteSquareTexture", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR, -400, 0, add)
    MEL.connect_material_property(t, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(sparam(m, "Roughness", 0.45, -400, 250), "", unreal.MaterialProperty.MP_ROUGHNESS)
    # retroreflective sheeting: a touch of self-light so signs read in shade
    em = X(m, unreal.MaterialExpressionMultiply, -200, 150)
    MEL.connect_material_expressions(t, "RGB", em, "A")
    MEL.connect_material_expressions(sparam(m, "Glow", 0.15, -400, 350), "", em, "B")
    MEL.connect_material_property(em, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def signal_lens_master():
    """Lit when frac(time/Cycle + data0 + data1*0.5) is inside [On, Off): data0 = intersection phase,
    data1 = 0 for north-south heads, 1 for east-west, so crossing directions alternate."""
    m = new_material("M_SignalLens")
    t = X(m, unreal.MaterialExpressionTime, -1400, 0)
    cyc = sparam(m, "Cycle", 50.0, -1400, 100)
    d = X(m, unreal.MaterialExpressionDivide, -1250, 0)
    MEL.connect_material_expressions(t, "", d, "A")
    MEL.connect_material_expressions(cyc, "", d, "B")
    c0 = X(m, unreal.MaterialExpressionPerInstanceCustomData, -1400, 200)
    c0.set_editor_property("data_index", 0)
    c1 = X(m, unreal.MaterialExpressionPerInstanceCustomData, -1400, 300)
    c1.set_editor_property("data_index", 1)
    half = X(m, unreal.MaterialExpressionMultiply, -1250, 300)
    MEL.connect_material_expressions(c1, "", half, "A")
    hc = X(m, unreal.MaterialExpressionConstant, -1400, 400)
    hc.set_editor_property("r", 0.5)
    MEL.connect_material_expressions(hc, "", half, "B")
    a1 = X(m, unreal.MaterialExpressionAdd, -1100, 100)
    MEL.connect_material_expressions(d, "", a1, "A")
    MEL.connect_material_expressions(c0, "", a1, "B")
    a2 = X(m, unreal.MaterialExpressionAdd, -950, 150)
    MEL.connect_material_expressions(a1, "", a2, "A")
    MEL.connect_material_expressions(half, "", a2, "B")
    fr = X(m, unreal.MaterialExpressionFrac, -800, 150)
    MEL.connect_material_expressions(a2, "", fr, "")
    on = sparam(m, "On", 0.0, -800, 300)
    off = sparam(m, "Off", 0.45, -800, 400)
    s1 = X(m, unreal.MaterialExpressionStep, -600, 200)     # fr >= On
    MEL.connect_material_expressions(on, "", s1, "Y")
    MEL.connect_material_expressions(fr, "", s1, "X")
    s2 = X(m, unreal.MaterialExpressionStep, -600, 350)     # fr < Off
    MEL.connect_material_expressions(fr, "", s2, "Y")
    MEL.connect_material_expressions(off, "", s2, "X")
    lit = X(m, unreal.MaterialExpressionMultiply, -450, 250)
    MEL.connect_material_expressions(s1, "", lit, "A")
    MEL.connect_material_expressions(s2, "", lit, "B")
    col = vparam(m, "LensColor", (1, 0.1, 0.05, 1), -600, -100)
    MEL.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    em = X(m, unreal.MaterialExpressionMultiply, -300, 100)
    MEL.connect_material_expressions(col, "", em, "A")
    MEL.connect_material_expressions(lit, "", em, "B")
    em2 = X(m, unreal.MaterialExpressionMultiply, -150, 100)
    MEL.connect_material_expressions(em, "", em2, "A")
    MEL.connect_material_expressions(sparam(m, "Brightness", 40.0, -300, 250), "", em2, "B")
    MEL.connect_material_property(em2, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(sparam(m, "Roughness", 0.15, -300, 350), "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def mi(name, parent, scalars=None, vectors=None, textures=None):
    path = f"{MAT_DIR}/{name}"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    m = AT.create_asset(name, MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    m.set_editor_property("parent", parent)
    for k, v in (scalars or {}).items():
        MEL.set_material_instance_scalar_parameter_value(m, k, v)
    for k, v in (vectors or {}).items():
        MEL.set_material_instance_vector_parameter_value(m, k, unreal.LinearColor(*v, 1))
    for k, v in (textures or {}).items():
        MEL.set_material_instance_texture_parameter_value(m, k, EAL.load_asset(v))
    MEL.update_material_instance(m)
    EAL.save_loaded_asset(m)
    return m


KT = TEX_DIR + "/Kit"
SLOT_MI = {}


def stage_materials():
    P = prop_master()
    F = foliage_master()
    S = sign_atlas_master()
    L = signal_lens_master()
    defs = {
        "M_PaintedSteelDark": (P, {"Roughness": 0.45, "Metallic": 0.6}, {"Tint": (0.05, 0.055, 0.06)}, {}),
        "M_Galvanized": (P, {"Roughness": 0.38, "Metallic": 0.9}, {"Tint": (0.62, 0.63, 0.64)}, {}),
        "M_LampLens": (P, {"Roughness": 0.2, "EmissiveStrength": 0.0}, {"Tint": (0.85, 0.85, 0.8), "EmissiveColor": (1, 0.85, 0.6)}, {}),
        "M_SignalHousing": (P, {"Roughness": 0.5, "Metallic": 0.1}, {"Tint": (0.035, 0.035, 0.035)}, {}),
        "M_SignBack": (P, {"Roughness": 0.5, "Metallic": 0.8}, {"Tint": (0.55, 0.56, 0.57)}, {}),
        "M_SignStop": (P, {"Roughness": 0.45, "EmissiveStrength": 0.15}, {"Tint": (1, 1, 1), "EmissiveColor": (1, 1, 1)}, {"BaseColorTex": f"{KT}/T_Sign_Stop"}),
        "M_SignBus": (P, {"Roughness": 0.45}, {"Tint": (0.1, 0.3, 0.75)}, {}),
        "M_DumpsterGreen": (P, {"Roughness": 0.55, "Metallic": 0.4}, {"Tint": (0.05, 0.2, 0.11)}, {}),
        "M_BlackPlastic": (P, {"Roughness": 0.6}, {"Tint": (0.03, 0.03, 0.03)}, {}),
        "M_Aluminium": (P, {"Roughness": 0.35, "Metallic": 0.9}, {"Tint": (0.7, 0.71, 0.72)}, {}),
        "M_Glass": (P, {"Roughness": 0.05, "Metallic": 0.6}, {"Tint": (0.25, 0.3, 0.33)}, {}),
        "M_CastIron": (P, {"Roughness": 0.55, "Metallic": 0.7}, {"Tint": (0.05, 0.05, 0.05)}, {}),
        "M_USPSBlue": (P, {"Roughness": 0.45, "Metallic": 0.3}, {"Tint": (0.04, 0.12, 0.42)}, {}),
        "M_ReflectiveWhite": (P, {"Roughness": 0.3, "EmissiveStrength": 0.2}, {"Tint": (0.9, 0.9, 0.9), "EmissiveColor": (1, 1, 1)}, {}),
        "M_TreeGrate": (P, {"Roughness": 0.6, "Metallic": 0.6}, {"Tint": (1, 1, 1)}, {}),
        "M_Bark": (P, {"Roughness": 0.9}, {"Tint": (1, 1, 1)}, {"BaseColorTex": f"{KT}/T_Bark_C", "NormalTex": f"{KT}/T_Bark_N"}),
        "M_SignSpeed": (S, {"Cols": 4.0, "CellU": 0.25, "CellV": 640 / 2048}, {}, {"AtlasTex": f"{KT}/T_Sign_Speed"}),
        "M_SignName": (S, {"Cols": 8.0, "CellU": 0.125, "CellV": 102 / 4096}, {}, {"AtlasTex": f"{KT}/T_Sign_Names"}),
        "M_SignalRed": (L, {"On": 0.0, "Off": 0.45}, {"LensColor": (1.0, 0.06, 0.03)}, {}),
        "M_SignalGreen": (L, {"On": 0.5, "Off": 0.9}, {"LensColor": (0.1, 1.0, 0.55)}, {}),
        "M_SignalYellow": (L, {"On": 0.9, "Off": 1.0}, {"LensColor": (1.0, 0.65, 0.02)}, {}),
    }
    for sp in ("liveoak", "honeylocust", "linden", "elm"):
        defs[f"M_Leaves_{sp}"] = (F, {"Roughness": 0.6}, {"Tint": (1, 1, 1)}, {"BaseColorTex": f"{KT}/T_Leaves_{sp}_C", "NormalTex": f"{KT}/T_Leaves_{sp}_N"})
    for slot, (parent, sc, vec, tx) in defs.items():
        SLOT_MI[slot] = mi("MI_" + slot[2:], parent, sc, vec, tx)
    log("materials", sorted(SLOT_MI))


# ------------------------------------------------------------------ meshes
def stage_meshes():
    kit = import_files(sorted(glob.glob(f"{KIT}/meshes/*.glb")), KIT_DIR)
    ph = []
    for d in sorted(glob.glob(f"{CC0}/polyhaven/*/")):
        g = glob.glob(d + "*.gltf")
        if g:
            ph += import_files(g, f"{PH_DIR}/{os.path.basename(d.rstrip('/'))}")
    log("meshes", {"kit": len(kit), "polyhaven": len(ph), "sample": (kit + ph)[:8]})


def find_mesh(folder, contains):
    for p in EAL.list_assets(folder, recursive=True):
        a = EAL.find_asset_data(p)
        if a.asset_class_path.asset_name == "StaticMesh" and contains.lower() in p.lower():
            return EAL.load_asset(p.split(".")[0])
    return None


def apply_slot_materials(sm):
    if not SLOT_MI:
        for p in EAL.list_assets(MAT_DIR, recursive=False):
            n = p.split("/")[-1].split(".")[0]
            if n.startswith("MI_"):
                SLOT_MI["M_" + n[3:]] = EAL.load_asset(p.split(".")[0])
    mats = sm.get_editor_property("static_materials")
    for i, sml in enumerate(mats):
        slot = str(sml.get_editor_property("material_slot_name"))
        base = slot.split(".")[0]
        if base in SLOT_MI:
            sm.set_material(i, SLOT_MI[base])


def auto_lods(sm, n=3):
    try:
        opts = unreal.EditorScriptingMeshReductionOptions()
        opts.set_editor_property("reduction_settings", [
            unreal.EditorScriptingMeshReductionSettings(percent_triangles=1.0, screen_size=1.0),
            unreal.EditorScriptingMeshReductionSettings(percent_triangles=0.35, screen_size=0.25),
            unreal.EditorScriptingMeshReductionSettings(percent_triangles=0.12, screen_size=0.08)][:n])
        unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).set_lods(sm, opts)
    except Exception as e:
        out.setdefault("lod_errors", []).append(str(e)[:200])


# ------------------------------------------------------------------ props
KIT_FRONT = -90.0   # the Blender kit comes out of the glTF import facing local +Y (Blender X stays X); yaws below name the front


def ue_xf(p, yaw_plan, z, extra_yaw=0.0, scale=1.0, front=True):
    return unreal.Transform(unreal.Vector(p[1] * 100.0, p[0] * 100.0, z),
                            unreal.Rotator(roll=0, pitch=0, yaw=90.0 - yaw_plan + extra_yaw + (KIT_FRONT if front else 0.0)),
                            unreal.Vector(scale, scale, scale))


WORLD = None


def ground_z(p, default=15.0):
    x, y = p[1] * 100.0, p[0] * 100.0
    hit = unreal.SystemLibrary.line_trace_single(WORLD, unreal.Vector(x, y, 3000), unreal.Vector(x, y, -1000),
                                                 unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True)
    if hit:
        t = hit.to_tuple()
        a = t[9]
        if a and ("Collision" in a.get_actor_label() or a.get_actor_label().startswith("CS_")):
            return default     # invisible building boxes: keep the default sidewalk height
        return t[4].z
    return default


def add_component(actor, cls):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    BFL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=cls, blueprint_context=None)
    h, fail = sds.add_new_subobject(params)
    return BFL.get_object(BFL.get_data(h))


def instanced(label, mesh, xfs, cull, shadows=True, custom=None):
    if not xfs or mesh is None:
        return 0
    act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    act.set_actor_label(label)
    act.set_folder_path("City/Streets/Props")
    act.tags = [TAG, "City_Generated", "NoWallRide"]
    act.set_editor_property("is_spatially_loaded", False)
    c = add_component(act, unreal.HierarchicalInstancedStaticMeshComponent)
    c.set_static_mesh(mesh)
    c.set_editor_property("cast_shadow", shadows)
    c.set_collision_profile_name("NoCollision")
    c.set_cull_distances(int(cull * 0.8), int(cull))
    if custom:
        c.set_editor_property("num_custom_data_floats", len(custom[0]))
    c.add_instances(xfs, False, True)
    if custom:
        for i, vals in enumerate(custom):
            for k, v in enumerate(vals):
                c.set_custom_data_value(i, k, float(v), False)
    return len(xfs)


def stage_props():
    global WORLD
    WORLD = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags]:
            EAS.destroy_actor(a)
    M = lambda n: find_mesh(KIT_DIR, n)
    PHM = lambda n: find_mesh(f"{PH_DIR}/{n}", "")
    meshes = {k: M(v) for k, v in {
        "lamp": "SK_Lamp_Street", "lamp_hw": "SK_Lamp_Highway", "sig4": "SK_Signal_4m", "sig7": "SK_Signal_7m", "sig10": "SK_Signal_10m",
        "sig13": "SK_Signal_13m", "stop": "SK_StopSign", "speed": "SK_SpeedSign", "post": "SK_NamePost", "blade": "SK_NameBlade",
        "rack": "SK_BikeRack", "dumpster": "SK_Dumpster", "shelter": "SK_BusShelter", "busstop": "SK_BusStopSign", "drain": "SK_StormDrain",
        "mailbox": "SK_Mailbox", "grate": "SK_TreeGrate", "liveoak": "SK_Tree_liveoak", "honeylocust": "SK_Tree_honeylocust",
        "linden": "SK_Tree_linden", "elm": "SK_Tree_elm"}.items()}
    for k, n in {"hydrant": "fire_hydrant", "bin": "metal_trash_can", "manhole": "water_manhole_cover", "ubox": "utility_box_02",
                 "bench": "modular_street_seating", "planter": "planter_box_01"}.items():
        meshes[k] = PHM(n)
    missing = [k for k, v in meshes.items() if v is None]
    for k, sm in meshes.items():
        if sm is not None:
            apply_slot_materials(sm)
            if k in ("hydrant", "bin", "bench", "planter", "ubox", "liveoak", "honeylocust", "linden", "elm"):
                auto_lods(sm)
            EAL.save_loaded_asset(sm)
    G = {k: [] for k in meshes}
    CUST = {"speed": [], "blade": [], "sig4": [], "sig7": [], "sig10": [], "sig13": []}
    speed_cell = {int(k): v for k, v in ATLAS["speed"].items()}
    names = ATLAS["names"]
    node_phase = {}
    for pr in D["props"]:
        t, p, yaw = pr["t"], pr["p"], pr["yaw"]
        if t == "lamp":
            G["lamp_hw" if pr.get("style") == "highway" else "lamp"].append(ue_xf(p, yaw, ground_z(p)))
        elif t == "tree":
            z = ground_z(p)
            G[pr["sp"]].append(ue_xf(p, yaw, z, scale=pr.get("scale", 1.0)))
            if pr.get("pit") == "grate":
                G["grate"].append(ue_xf(p, yaw, z + 0.5))
        elif t == "signal":
            arm = pr.get("arm", 7.0)
            key = min(("sig4", 4), ("sig7", 7), ("sig10", 10), ("sig13", 13), key=lambda kv: abs(kv[1] - arm))[0]
            G[key].append(ue_xf(p, yaw, ground_z(p)))
            ph = node_phase.setdefault((round(p[0] / 60), round(p[1] / 60)), (hash((round(p[0] / 60), round(p[1] / 60))) % 1000) / 1000.0)
            axis = 0 if abs(math.cos(math.radians(yaw))) > abs(math.sin(math.radians(yaw))) else 1
            CUST[key].append([ph, axis])
        elif t == "stopsign":
            G["stop"].append(ue_xf(p, yaw, ground_z(p)))
        elif t == "speedsign":
            mph = min(speed_cell, key=lambda s: abs(s - pr["mph"]))
            G["speed"].append(ue_xf(p, yaw, ground_z(p)))
            CUST["speed"].append([speed_cell[mph]])
        elif t == "namesign":
            z = ground_z(p)
            G["post"].append(ue_xf(p, yaw, z))
            for k, (nm, yy) in enumerate(((pr["a"], yaw), (pr["b"], pr["yaw_b"]))):
                if nm in names:
                    G["blade"].append(ue_xf(p, yy, z + k * 20.0, front=False))     # long axis = local X, along the road
                    CUST["blade"].append([names[nm]])
        elif t == "bikerack":
            G["rack"].append(ue_xf(p, yaw, ground_z(p)))
        elif t == "dumpster":
            G["dumpster"].append(ue_xf(p, yaw, ground_z(p), front=False))
        elif t == "busstop":
            G["busstop"].append(ue_xf(p, yaw, ground_z(p)))
        elif t == "drain":
            G["drain"].append(ue_xf(p, yaw, ground_z(p, 0.0) + 0.3, front=False))
        elif t == "manhole":
            G["manhole"].append(ue_xf(p, yaw, ground_z(p, 0.0) + 0.2))
        elif t in ("hydrant", "bin", "bench", "mailbox"):
            G[t].append(ue_xf(p, yaw, ground_z(p)))
        elif t == "utilitybox":
            G["ubox"].append(ue_xf(p, yaw, ground_z(p)))
    counts = {}
    cull = {"lamp": 35000, "lamp_hw": 50000, "liveoak": 45000, "honeylocust": 45000, "linden": 45000, "elm": 45000,
            "sig4": 30000, "sig7": 30000, "sig10": 30000, "sig13": 30000}
    for k, xfs in G.items():
        if not xfs or meshes.get(k) is None:
            continue
        counts[k] = instanced(f"Props_{k}", meshes[k], xfs, cull.get(k, 18000),
                              shadows=k in ("liveoak", "honeylocust", "linden", "elm", "shelter"),
                              custom=CUST.get(k))
    log("props", {"counts": counts, "missing": missing})


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
