"""The Willis Tower from Scripts/landmarks/blender_willis.py (SourceArt/Landmarks/willis) placed where the plan puts it in
SkyCityMashup (the Wacker / Adams / Franklin / Jackson block), replacing build_city.py's nine-box stand-in.

Stages (run in the editor console, one call; they run in order from a slate tick so the editor stays responsive):
  py Scripts/roads/place_willis_ue.py [import] [materials] [place] [clear] [pickups] [save]
  import     GLBs -> /Game/City/Willis (kept out of /Game/City/Landmarks: that folder's material pass re-slots by name),
             textures/T_WT_*.png -> /Game/City/Willis/Textures (masks linear, the lit-window map point-sampled, no mips)
  materials  M_WT_Facade (tiling curtain wall: UV bays x floors, mullion grid, spandrels, glass reflection, per-window
             tint, lit windows from the random map) + MI_WT_CurtainWall / Louvre / Podium; M_WT_Glass (translucent Ledge);
             flat MIs on the city's M_StreetProp, surfaces on M_StreetSurface; Nanite off on every mesh; the hidden
             colliders get complex-as-simple collision
  place      removes build_city.py's stand-in (Landmark_WillisTower, tag City_Generated) and our earlier actors (tag
             SC_Willis), finds the street level on Wacker Drive, spawns the visible meshes (no collision) and the three
             hidden colliders (WT_ColWalls / WT_ColRoofs / WT_ColLedge: invisible, BlockAll) at the plan origin, no rotation
  clear      removes City Sample building instances (CS_* ISMs), their roof-cap triangles and BuildingCollision boxes, and
             street props / trees (RProps_* / SC_RoadProps) inside the block (willis.json zone_plan)
  pickups    the rocket-fuel add-on that sat on the stand-in's roof goes onto the new 442 m roof; pads / chargers inside
             the block are dropped onto the new surfaces
  save       World Partition: saves every dirty actor package
  probe      traces the colliders at the test points (writes the hit heights)
  shots tag=<t> "poses=name:px,py,z,pitch,yaw;..." [night=1]   viewport captures to Saved/Willis/shots (plan metres,
             compass yaw); night=1 dims the sun and sky for the duration of the captures and puts them back exactly
Writes Saved/MCPScripts/out_willis.json. Rerunning build_city.py's `landmarks` stage brings the stand-in back: run
`place save` here afterwards.
"""
import json, math, os, sys, time, traceback, unreal

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
SRC = ROOT + "/SourceArt/Landmarks/willis"
OUT = ROOT + "/Saved/MCPScripts/out_willis.json"
WJ = json.load(open(SRC + "/willis.json"))
DIR = "/Game/City/Willis"
TAG = "SC_Willis"
STANDIN = "Landmark_WillisTower"
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
STAGES = [a for a in sys.argv[1:] if "=" not in a] or ["import", "materials", "place", "clear", "pickups", "save"]
VISIBLE = ["WT_Tower", "WT_Top", "WT_Ledge", "WT_Base"]
COLLIDERS = ["WT_ColWalls", "WT_ColRoofs", "WT_ColLedge"]
ASSETS = VISIBLE + COLLIDERS
TEXTURES = ["T_WT_CurtainWall", "T_WT_Louvre", "T_WT_Podium", "T_WT_Lit"]
out = {"stages": STAGES}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def ue_xy(p):
    return (p[1] * 100.0, p[0] * 100.0)


ORIGIN = WJ["frame"]["origin_plan_m"]


# ------------------------------------------------------------------ import
def mesh(name):
    for p in EAL.list_assets(DIR, recursive=True):
        if p.split("/")[-1].split(".")[0] == name and EAL.find_asset_data(p).asset_class_path.asset_name == "StaticMesh":
            return EAL.load_asset(p.split(".")[0])
    return None


def texture(name):
    path = f"{DIR}/Textures/{name}"
    return EAL.load_asset(path) if EAL.does_asset_exist(path) else None


def stage_import():
    tasks = []
    for name in ASSETS:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f"{SRC}/{name}.glb")
        t.set_editor_property("destination_path", DIR)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        tasks.append(t)
    for name in TEXTURES:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f"{SRC}/textures/{name}.png")
        t.set_editor_property("destination_path", f"{DIR}/Textures")
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        tasks.append(t)
    AT.import_asset_tasks(tasks)
    res = {}
    for name in TEXTURES:
        tx = texture(name)
        if not tx:
            res[name] = "missing"
            continue
        tx.set_editor_property("srgb", False)
        if name == "T_WT_Lit":
            tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
            tx.set_editor_property("filter", unreal.TextureFilter.TF_NEAREST)
            tx.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        else:
            tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        EAL.save_loaded_asset(tx)
        res[name] = True
    log("import", {"meshes": {n: bool(mesh(n)) for n in ASSETS}, "textures": res})


# ------------------------------------------------------------------ materials
SURF = "/Game/City/Street/Materials/M_StreetSurface"     # textured, tile size in metres, world-aligned or mesh UVs
PROP = "/Game/City/Street/Materials/M_StreetProp"        # flat colour, roughness, metallic, emissive
TEX = "/Game/City/Street/Textures"


def stex(name, kind):
    return EAL.load_asset(f"{TEX}/{name}/{name}_{kind}_2k")


def mi(name, parent, scalars=None, vectors=None, textures=None, switches=None):
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
        MEL.set_material_instance_texture_parameter_value(m, k, v)
    for k, v in (switches or {}).items():
        MEL.set_material_instance_static_switch_parameter_value(m, k, v)
    MEL.update_material_instance(m)
    EAL.save_loaded_asset(m)
    return m


def surf(name, texname, tint, rough, tile, world=False, normal=1.0, macro=0.3):
    return mi(name, SURF, {"RoughnessScale": rough, "TileSize": tile, "NormalStrength": normal, "MacroVariation": macro}, {"Tint": tint},
              {"BaseColorTex": stex(texname, "diff"), "NormalTex": stex(texname, "nor_gl"), "ARMTex": stex(texname, "arm")}, {"WorldAligned": world})


def flat(name, tint, rough, metal=0.0, glow=0.0):
    v = {"Tint": tint}
    if glow:
        v["EmissiveColor"] = tint
    return mi(name, PROP, {"Roughness": rough, "Metallic": metal, "EmissiveStrength": glow}, v)


def facade_master():
    """M_WT_Facade: the tiling curtain wall. Mesh UV0 = (bays, floors). MaskTex (R glass, G frame relief, B spandrel)
    tiles one bay x one floor; LitTex is sampled once per window (floor(u * WindowsPerBay), floor(v)) for the lit
    offices at night (emissive above LitThreshold), a per-window glass tint and blinds (roughness)."""
    path = f"{DIR}/Materials/M_WT_Facade"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
    else:
        m = AT.create_asset("M_WT_Facade", f"{DIR}/Materials", unreal.Material, unreal.MaterialFactoryNew())

    def X(cls, x, y):
        return MEL.create_material_expression(m, cls, x, y)

    def C(e, pin_out, e2, pin_in):
        MEL.connect_material_expressions(e, pin_out, e2, pin_in)

    def sp(name, v, x, y):
        e = X(unreal.MaterialExpressionScalarParameter, x, y)
        e.set_editor_property("parameter_name", name)
        e.set_editor_property("default_value", v)
        return e

    def vp(name, v, x, y):
        e = X(unreal.MaterialExpressionVectorParameter, x, y)
        e.set_editor_property("parameter_name", name)
        e.set_editor_property("default_value", unreal.LinearColor(*v, 1))
        return e

    def op(cls, a, b, x, y, pa="", pb=""):
        e = X(cls, x, y)
        C(a, pa, e, "A")
        C(b, pb, e, "B")
        return e

    def lerp(a, b, t, x, y, pa="", pb="", pt=""):
        e = X(unreal.MaterialExpressionLinearInterpolate, x, y)
        C(a, pa, e, "A")
        C(b, pb, e, "B")
        C(t, pt, e, "Alpha")
        return e

    def const(v, x, y):
        e = X(unreal.MaterialExpressionConstant, x, y)
        e.set_editor_property("r", v)
        return e

    uv = X(unreal.MaterialExpressionTextureCoordinate, -2200, 0)
    mask = X(unreal.MaterialExpressionTextureSampleParameter2D, -1900, -200)
    mask.set_editor_property("parameter_name", "MaskTex")
    mask.set_editor_property("texture", texture("T_WT_CurtainWall"))
    mask.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    C(uv, "", mask, "UVs")
    # per-window lookup: (floor(uv * (WPB, 1)) + 0.5) / 64
    wpb = sp("WindowsPerBay", 3.0, -2200, 250)
    one = const(1.0, -2200, 330)
    app = op(unreal.MaterialExpressionAppendVector, wpb, one, -2000, 280)
    uvw = op(unreal.MaterialExpressionMultiply, uv, app, -1850, 200)
    fl = X(unreal.MaterialExpressionFloor, -1700, 200)
    C(uvw, "", fl, "")
    half = const(0.5, -1700, 300)
    fl2 = op(unreal.MaterialExpressionAdd, fl, half, -1550, 220)
    inv = const(1.0 / 64.0, -1550, 320)
    luv = op(unreal.MaterialExpressionMultiply, fl2, inv, -1400, 240)
    lit = X(unreal.MaterialExpressionTextureSampleParameter2D, -1200, 240)
    lit.set_editor_property("parameter_name", "LitTex")
    lit.set_editor_property("texture", texture("T_WT_Lit"))
    lit.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    C(luv, "", lit, "UVs")
    # colours
    glass_c = vp("GlassColor", (0.030, 0.026, 0.022), -1200, -600)
    frame_c = vp("FrameColor", (0.012, 0.012, 0.013), -1200, -450)
    span_c = vp("SpandrelColor", (0.016, 0.015, 0.016), -1200, -330)
    tintvar = sp("TintVar", 0.35, -1200, -150)
    one2 = const(1.0, -1050, -100)
    lo = op(unreal.MaterialExpressionSubtract, one2, tintvar, -900, -140)
    hi = op(unreal.MaterialExpressionAdd, one2, tintvar, -900, -60)
    tint = lerp(lo, hi, lit, -750, -100, pt="G")
    glass = op(unreal.MaterialExpressionMultiply, glass_c, tint, -600, -560)
    framecol = lerp(frame_c, span_c, mask, -900, -400, pt="B")
    relief = op(unreal.MaterialExpressionAdd, mask, half, -900, -250, pa="G")
    framelit = op(unreal.MaterialExpressionMultiply, framecol, relief, -700, -380)
    base = lerp(framelit, glass, mask, -400, -450, pt="R")
    MEL.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    # metal / roughness / specular
    gm, fm = sp("GlassMetal", 0.55, -700, 0), sp("FrameMetal", 0.6, -700, 80)
    metal = lerp(fm, gm, mask, -400, 40, pt="R")
    MEL.connect_material_property(metal, "", unreal.MaterialProperty.MP_METALLIC)
    gr, fr = sp("GlassRough", 0.05, -900, 140), sp("FrameRough", 0.45, -700, 220)
    blinds = op(unreal.MaterialExpressionMultiply, lit, sp("BlindRough", 0.12, -1000, 260), -800, 200, pa="B")
    grb = op(unreal.MaterialExpressionAdd, gr, blinds, -650, 160)
    rough = lerp(fr, grb, mask, -400, 180, pt="R")
    MEL.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(sp("Specular", 0.6, -400, 300), "", unreal.MaterialProperty.MP_SPECULAR)
    # lit windows
    thr = sp("LitThreshold", 0.62, -1000, 420)
    d = op(unreal.MaterialExpressionSubtract, lit, thr, -850, 400, pa="R")
    k = op(unreal.MaterialExpressionMultiply, d, const(25.0, -850, 500), -700, 420)
    sat = X(unreal.MaterialExpressionSaturate, -560, 420)
    C(k, "", sat, "")
    g2 = op(unreal.MaterialExpressionMultiply, sat, mask, -420, 420, pb="R")
    lc = vp("LitColor", (1.0, 0.80, 0.55), -560, 540)
    ls = sp("LitStrength", 4.0, -560, 640)
    e1 = op(unreal.MaterialExpressionMultiply, g2, lc, -280, 460)
    e2 = op(unreal.MaterialExpressionMultiply, e1, ls, -140, 500)
    MEL.connect_material_property(e2, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def glass_master():
    """M_WT_Glass: the Ledge boxes. Translucent, lit per pixel, more opaque at glancing angles (Fresnel)."""
    path = f"{DIR}/Materials/M_WT_Glass"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
    else:
        m = AT.create_asset("M_WT_Glass", f"{DIR}/Materials", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    m.set_editor_property("two_sided", False)

    def sp(name, v, x, y):
        e = MEL.create_material_expression(m, unreal.MaterialExpressionScalarParameter, x, y)
        e.set_editor_property("parameter_name", name)
        e.set_editor_property("default_value", v)
        return e
    c = MEL.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -500, -200)
    c.set_editor_property("parameter_name", "Tint")
    c.set_editor_property("default_value", unreal.LinearColor(0.55, 0.62, 0.66, 1))
    MEL.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(sp("Specular", 0.8, -500, -40), "", unreal.MaterialProperty.MP_SPECULAR)
    MEL.connect_material_property(sp("Roughness", 0.04, -500, 40), "", unreal.MaterialProperty.MP_ROUGHNESS)
    fr = MEL.create_material_expression(m, unreal.MaterialExpressionFresnel, -700, 260)
    fr.set_editor_property("exponent", 4.0)
    fr.set_editor_property("base_reflect_fraction", 0.04)
    lp = MEL.create_material_expression(m, unreal.MaterialExpressionLinearInterpolate, -300, 200)
    MEL.connect_material_expressions(sp("Opacity", 0.16, -700, 120), "", lp, "A")
    MEL.connect_material_expressions(sp("EdgeOpacity", 0.6, -700, 190), "", lp, "B")
    MEL.connect_material_expressions(fr, "", lp, "Alpha")
    MEL.connect_material_property(lp, "", unreal.MaterialProperty.MP_OPACITY)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def stage_materials():
    fac = facade_master()
    glass = glass_master()
    lit = texture("T_WT_Lit")
    S = {
        # curtain wall: bronze-tinted glass that reflects the sky (silver-grey in sun, as in the photographs), black frames
        "M_WT_CurtainWall": mi("MI_WT_CurtainWall", fac, {"WindowsPerBay": 3.0, "LitThreshold": 0.62, "LitStrength": 4.0},
                               {"GlassColor": (0.030, 0.026, 0.022), "FrameColor": (0.012, 0.012, 0.013), "SpandrelColor": (0.018, 0.017, 0.018)},
                               {"MaskTex": texture("T_WT_CurtainWall"), "LitTex": lit}),
        # the 103rd floor (Skydeck): every window lit, a bright band at night as in the photographs
        "M_WT_SkydeckGlass": mi("MI_WT_Skydeck", fac, {"WindowsPerBay": 3.0, "LitThreshold": -1.0, "LitStrength": 5.0},
                                {"GlassColor": (0.030, 0.026, 0.022), "FrameColor": (0.012, 0.012, 0.013), "SpandrelColor": (0.018, 0.017, 0.018),
                                 "LitColor": (0.95, 0.92, 0.85)},
                                {"MaskTex": texture("T_WT_CurtainWall"), "LitTex": lit}),
        # louvres: no glass in the mask, so no reflection and no lit windows: the dark bands
        "M_WT_Louvre": mi("MI_WT_Louvre", fac, {"LitStrength": 0.0, "FrameRough": 0.55, "FrameMetal": 0.5},
                          {"FrameColor": (0.008, 0.008, 0.009), "SpandrelColor": (0.008, 0.008, 0.009)},
                          {"MaskTex": texture("T_WT_Louvre"), "LitTex": lit}),
        # the Catalog: clearer glass in black frames, shops lit more often
        "M_WT_Podium": mi("MI_WT_Podium", fac, {"WindowsPerBay": 1.0, "LitThreshold": 0.42, "LitStrength": 3.0, "GlassMetal": 0.45, "TintVar": 0.2},
                          {"GlassColor": (0.045, 0.055, 0.062), "FrameColor": (0.010, 0.010, 0.011), "SpandrelColor": (0.012, 0.012, 0.013)},
                          {"MaskTex": texture("T_WT_Podium"), "LitTex": lit}),
        "M_WT_Alu": flat("MI_WT_Alu", (0.014, 0.014, 0.015), 0.38, 0.75),
        "M_WT_RoofWhite": surf("MI_WT_RoofWhite", "concrete_floor_01", (3.4, 3.6, 4.2), 0.9, 3.0, world=True, macro=0.2),
        "M_WT_RoofGrey": surf("MI_WT_RoofGrey", "concrete_floor_01", (1.05, 1.15, 1.5), 0.9, 3.0, world=True, macro=0.2),
        "M_WT_DrumMetal": flat("MI_WT_DrumMetal", (0.45, 0.46, 0.47), 0.4, 0.6),
        "M_WT_MastWhite": flat("MI_WT_MastWhite", (0.72, 0.73, 0.74), 0.4, 0.3),
        "M_WT_Beacon": flat("MI_WT_Beacon", (1.0, 0.04, 0.02), 0.4, 0.0, 40.0),
        "M_WT_LedgeGlass": glass,
        "M_WT_LedgeFrame": flat("MI_WT_LedgeFrame", (0.03, 0.03, 0.033), 0.35, 0.8),
        "M_WT_PodiumRoof": surf("MI_WT_PodiumRoof", "concrete_pavement", (2.2, 2.4, 2.7), 0.85, 3.0, world=True),
        "M_WT_PodiumRoofDark": surf("MI_WT_PodiumRoofDark", "concrete_floor_01", (0.7, 0.75, 0.85), 0.85, 3.0, world=True),
        "M_WT_Lawn": surf("MI_WT_Lawn", "leafy_grass", (0.19, 0.52, 0.24), 0.95, 3.0, world=True),
        "M_WT_Skylight": flat("MI_WT_Skylight", (0.06, 0.08, 0.09), 0.05, 0.85),
        "M_WT_Granite": surf("MI_WT_Granite", "concrete_pavement", (2.6, 2.3, 2.3), 0.8, 2.5, world=True),
        "M_WT_Col": flat("MI_WT_Collider", (0.8, 0.2, 0.8), 0.5, 0.0),
    }
    res = {}
    for name in ASSETS:
        sm = mesh(name)
        if not sm:
            res[name] = "missing"
            continue
        n = 0
        for i, sml in enumerate(sm.get_editor_property("static_materials")):
            base = str(sml.get_editor_property("material_slot_name")).split(".")[0]
            if base in S:
                sm.set_material(i, S[base])
                n += 1
        ns = sm.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", False)
        sm.set_editor_property("nanite_settings", ns)
        bs = sm.get_editor_property("body_setup")
        if bs:
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        EAL.save_loaded_asset(sm)
        b = sm.get_bounding_box()
        res[name] = {"slots": n, "bounds_cm": [round(v) for v in (b.min.x, b.min.y, b.min.z, b.max.x, b.max.y, b.max.z)]}
    log("materials", res)


# ------------------------------------------------------------------ place
WORLD = None


def world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def trace(x, y, top=60000.0, bottom=-2000.0, ignore=()):
    hit = unreal.SystemLibrary.line_trace_single(world(), unreal.Vector(x, y, top), unreal.Vector(x, y, bottom), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                                                 False, list(ignore), unreal.DrawDebugTrace.NONE, True)
    if not hit:
        return None
    t = hit.to_tuple()
    if not t[0]:
        return None
    a = t[9]
    return {"z": round(t[4].z, 1), "actor": a.get_actor_label() if a else None, "nz": round(t[7].z, 3), "comp": t[10].get_name() if t[10] else None}


def tagged(a, label, extra=()):
    a.set_actor_label(label)
    a.set_folder_path("City/Landmarks/Willis")
    a.tags = [TAG, "City_Generated"] + list(extra)
    a.set_editor_property("is_spatially_loaded", False)


def stage_place():
    gone = []
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags] or a.get_actor_label() == STANDIN:
            gone.append(a.get_actor_label())
            EAS.destroy_actor(a)
    # street level: Wacker Drive in front of the tower and Adams St (the asset origin z = 0 is the street)
    samples = {}
    for nm in ("wacker_start", "adams_start"):
        tp = WJ["test_points"][nm]["ue_cm"]
        samples[nm] = trace(tp[0], tp[1], 3000.0, -1000.0)
    zs = [s["z"] for s in samples.values() if s]
    z0 = sorted(zs)[len(zs) // 2] if zs else 0.0
    if abs(z0) > 80:
        z0 = 0.0
    X, Y = ue_xy(ORIGIN)
    loc = unreal.Vector(X, Y, z0)
    placed = {}
    for nm in VISIBLE + COLLIDERS:
        sm = mesh(nm)
        if not sm:
            placed[nm] = "missing mesh"
            continue
        a = EAS.spawn_actor_from_object(sm, loc, unreal.Rotator(0, 0, 0))
        c = a.static_mesh_component
        if nm in COLLIDERS:
            tagged(a, nm, ["WT_Collider"])
            c.set_collision_profile_name("BlockAll")
            c.set_editor_property("cast_shadow", False)
            c.set_visibility(False, True)
            a.set_actor_hidden_in_game(True)
        else:
            tagged(a, nm, ["NoWallRide"] if nm in ("WT_Top", "WT_Ledge") else [])
            c.set_collision_profile_name("NoCollision")
            c.set_editor_property("cast_shadow", nm != "WT_Ledge")
        b = a.get_actor_bounds(False)
        placed[nm] = {"loc": [round(loc.x), round(loc.y), round(loc.z)], "bounds_origin": [round(v) for v in b[0].to_tuple()],
                      "bounds_extent": [round(v) for v in b[1].to_tuple()]}
    log("place", {"removed": gone, "street_samples": samples, "z0": z0, "placed": placed})


# ------------------------------------------------------------------ clear the block
def inside(poly, x, y):
    c = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


ZONE = WJ["zone_plan"]
ZB = [min(p[0] for p in ZONE), max(p[0] for p in ZONE), min(p[1] for p in ZONE), max(p[1] for p in ZONE)]


def zone_hit(X, Y, pad=0.0):
    px, py = Y / 100.0, X / 100.0
    return ZB[0] - pad <= px <= ZB[1] + pad and ZB[2] - pad <= py <= ZB[3] + pad and inside(ZONE, px, py)


def comp_overlaps_zone(c):
    o, e, _r = unreal.SystemLibrary.get_component_bounds(c)
    return o.x + e.x >= ZB[2] * 100 and o.x - e.x <= ZB[3] * 100 and o.y + e.y >= ZB[0] * 100 and o.y - e.y <= ZB[1] * 100


def stage_clear():
    res = {"citysample_instances": 0, "props": {}, "roof_caps": None, "collision": None, "by_actor": {}}
    for a in EAS.get_all_level_actors():
        lab = a.get_actor_label()
        tags = [str(t) for t in a.tags]
        is_cs = lab.startswith("CS_")
        is_prop = lab.startswith("RProps_") or "SC_RoadProps" in tags
        if not (is_cs or is_prop):
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            n = c.get_instance_count()
            if not n or not comp_overlaps_zone(c):
                continue
            kill = []
            for i in range(n):
                p = c.get_instance_transform(i, True).translation
                if zone_hit(p.x, p.y):
                    kill.append(i)
            if kill:
                a.modify()
                c.modify()
                c.remove_instances(sorted(kill, reverse=True))
                if is_cs:
                    res["citysample_instances"] += len(kill)
                else:
                    res["props"][lab] = res["props"].get(lab, 0) + len(kill)
                res["by_actor"][lab] = res["by_actor"].get(lab, 0) + len(kill)
    res["roof_caps"] = carve_roof_caps()
    res["collision"] = carve_collision()
    log("clear", res)


def zone_box_ue(z0=-5000.0, z1=100000.0):
    return unreal.Box(unreal.Vector(ZB[2] * 100, ZB[0] * 100, z0), unreal.Vector(ZB[3] * 100, ZB[1] * 100, z1))


def carve_roof_caps():
    """City Sample PCG volumes also make the flat roof caps as one DynamicMeshComponent per volume: delete their
    triangles inside the block (same method as place_landmarks_ue.py)."""
    done = {}
    for a in EAS.get_all_level_actors():
        lab = a.get_actor_label()
        if not lab.startswith("CS_"):
            continue
        for c in a.get_components_by_class(unreal.DynamicMeshComponent):
            if not comp_overlaps_zone(c):
                continue
            try:
                xf = c.get_world_transform()
                inv = xf.inverse()
                dm = c.get_dynamic_mesh()
                before = dm.get_triangle_count()
                pts = [inv.transform_location(unreal.Vector(X, Y, Z)) for X in (ZB[2] * 100, ZB[3] * 100) for Y in (ZB[0] * 100, ZB[1] * 100)
                       for Z in (-5000.0, 100000.0)]
                lo = unreal.Vector(min(p_.x for p_ in pts), min(p_.y for p_ in pts), min(p_.z for p_ in pts))
                hi = unreal.Vector(max(p_.x for p_ in pts), max(p_.y for p_ in pts), max(p_.z for p_ in pts))
                r = unreal.GeometryScript_MeshSelection.select_mesh_elements_in_box(dm, unreal.Box(lo, hi), unreal.GeometryScriptMeshSelectionType.TRIANGLES, False, 3)
                sel = next((x for x in (r if isinstance(r, (tuple, list)) else [r]) if isinstance(x, unreal.GeometryScriptMeshSelection)), None)
                if sel is not None:
                    a.modify()
                    c.modify()
                    unreal.GeometryScript_MeshEdits.delete_selected_triangles_from_mesh(dm, sel)
                after = dm.get_triangle_count()
                try:
                    c.notify_mesh_updated()
                except Exception:
                    pass
                if after != before:
                    done[lab + "|" + c.get_name()] = [before, after]
            except Exception:
                done[lab + "|" + c.get_name()] = traceback.format_exc()[-400:]
    return done


def carve_collision():
    """Delete the BuildingCollision boxes whose triangles lie inside the block's bounding box."""
    act = next((a for a in EAS.get_all_level_actors() if a.get_actor_label() == "BuildingCollision"), None)
    if not act:
        return "no BuildingCollision"
    sm = act.static_mesh_component.static_mesh
    dm = unreal.DynamicMesh()
    try:
        GS = unreal.GeometryScript_AssetUtils
        r = GS.copy_mesh_from_static_mesh(sm, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(), unreal.GeometryScriptMeshReadLOD())
        dm = r[0] if isinstance(r, (tuple, list)) else dm
        before = dm.get_triangle_count()
        r = unreal.GeometryScript_MeshSelection.select_mesh_elements_in_box(dm, zone_box_ue(), unreal.GeometryScriptMeshSelectionType.TRIANGLES, False, 3)
        sel = next((x for x in (r if isinstance(r, (tuple, list)) else [r]) if isinstance(x, unreal.GeometryScriptMeshSelection)), None)
        if sel is None:
            return "no selection: %r" % (r,)
        unreal.GeometryScript_MeshEdits.delete_selected_triangles_from_mesh(dm, sel)
        after = dm.get_triangle_count()
        if after != before:
            wopts = unreal.GeometryScriptCopyMeshToAssetOptions()
            wopts.set_editor_property("enable_recompute_normals", False)
            wopts.set_editor_property("enable_recompute_tangents", False)
            GS.copy_mesh_to_static_mesh(dm, sm, wopts, unreal.GeometryScriptMeshWriteLOD())
            bs = sm.get_editor_property("body_setup")
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            EAL.save_loaded_asset(sm)
        return {"triangles_before": before, "after": after}
    except Exception:
        return traceback.format_exc()[-800:]


# ------------------------------------------------------------------ pickups
def stage_pickups():
    res = {"addons": [], "dropped": {}}
    rk = WJ["test_points"]["rocket_addon"]
    tower_poly = WJ["tower_outline_plan"]
    for a in EAS.get_all_level_actors():
        lab = a.get_actor_label()
        tags = [str(t) for t in a.tags]
        if "SC_Addon" in tags:
            for c in a.get_components_by_class(unreal.StaticMeshComponent):
                p = c.get_world_location()
                if zone_hit(p.x, p.y, pad=15.0):
                    old = [round(p.x), round(p.y), round(p.z)]
                    a.modify()
                    c.modify()
                    hit = trace(rk["ue_cm"][0], rk["ue_cm"][1], 60000.0, 30000.0)
                    z = (hit["z"] if hit else WJ["heights_m"]["roof_442"] * 100) + 5.0
                    c.set_world_location(unreal.Vector(rk["ue_cm"][0], rk["ue_cm"][1], z), False, True)
                    res["addons"].append({"actor": lab, "comp": c.get_name(), "tags": [str(t) for t in c.component_tags], "from": old,
                                          "to": [rk["ue_cm"][0], rk["ue_cm"][1], round(z)], "hit": hit})
        elif lab.startswith(("SC_Pads", "SC_Chargers")):
            for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
                for i in range(c.get_instance_count()):
                    t = c.get_instance_transform(i, True)
                    p = t.translation
                    if not zone_hit(p.x, p.y):
                        continue
                    hit = trace(p.x, p.y, p.z + 60000.0, p.z - 3000.0, ignore=[a])
                    if hit:
                        a.modify()
                        c.modify()
                        t.translation = unreal.Vector(p.x, p.y, hit["z"] + 2.0)
                        c.update_instance_transform(i, t, True, True, True)
                        res["dropped"][f"{lab}/{c.get_name()}/{i}"] = [round(p.z), hit["z"]]
    log("pickups", res)


def stage_save():
    log("save", unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True))


def stage_probe():
    res = {}
    for nm, tp in WJ["test_points"].items():
        res[nm] = trace(tp["ue_cm"][0], tp["ue_cm"][1], 60000.0, -1000.0)
    # down the west face in the climbing lane: horizontal traces into the wall every 20 m
    lane = WJ["test_points"]["forecourt"]
    hx = []
    for z in range(2500, 44500, 2000):
        x, y = lane["ue_cm"][0], lane["ue_cm"][1]
        h = unreal.SystemLibrary.line_trace_single(world(), unreal.Vector(x, y, z), unreal.Vector(x, y + 3000.0, z), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                                                   False, [], unreal.DrawDebugTrace.NONE, True)
        t = h.to_tuple() if h else None
        hx.append([z, round(t[4].y) if t and t[0] else None, t[9].get_actor_label() if t and t[0] and t[9] else None])
    res["west_face_lane"] = hx
    log("probe", res)


# ------------------------------------------------------------------ captures
SHOT = {"i": 0, "k": 0, "files": [], "saved": None}


def night_on():
    """Dim the sun and sky for the captures (restored exactly afterwards; nothing is saved)."""
    saved = []
    for a in EAS.get_all_level_actors():
        cls = a.get_class().get_name()
        if cls == "DirectionalLight":
            c = a.get_component_by_class(unreal.DirectionalLightComponent)
            saved.append(("sun", a, c.intensity, a.get_actor_rotation()))
            c.set_intensity(c.intensity * 0.0005)
        elif cls == "SkyLight":
            c = a.get_component_by_class(unreal.SkyLightComponent)
            saved.append(("sky", a, c.intensity, None))
            c.set_intensity(c.intensity * 0.02)
        elif cls == "ExponentialHeightFog":
            c = a.get_component_by_class(unreal.ExponentialHeightFogComponent)
            saved.append(("fog", a, c.get_editor_property("fog_inscattering_luminance"), None))
            c.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(0.002, 0.003, 0.006, 1))
    return saved


def night_off(saved):
    for kind, a, v, rot in saved or []:
        if kind == "sun":
            a.get_component_by_class(unreal.DirectionalLightComponent).set_intensity(v)
        elif kind == "sky":
            a.get_component_by_class(unreal.SkyLightComponent).set_intensity(v)
        elif kind == "fog":
            a.get_component_by_class(unreal.ExponentialHeightFogComponent).set_editor_property("fog_inscattering_luminance", v)


def stage_shots():
    poses = []
    for p in KV.get("poses", "").split(";"):
        if p:
            name, vals = p.split(":")
            poses.append((name, [float(v) for v in vals.split(",")]))
    SHOT["poses"] = poses
    SHOT["tag"] = KV.get("tag", "shot")
    SHOT["res"] = [int(v) for v in KV.get("res", "1600x900").split("x")]
    os.makedirs(ROOT + "/Saved/Willis/shots", exist_ok=True)
    if KV.get("night") == "1":
        SHOT["saved"] = night_on()
    return "async"


def shots_tick():
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if SHOT["i"] >= len(SHOT["poses"]):
        SHOT["k"] += 1
        if SHOT["k"] > 40:
            night_off(SHOT["saved"])
            SHOT["saved"] = None
            log("night_restored", True)
            return True
        return False
    name, (px, py, zm, pitch, yawc) = SHOT["poses"][SHOT["i"]]
    if SHOT["k"] == 0:
        ues.set_level_viewport_camera_info(unreal.Vector(py * 100.0, px * 100.0, zm * 100.0), unreal.Rotator(roll=0, pitch=pitch, yaw=yawc))
    if SHOT["k"] == 50:
        fn = f"{ROOT}/Saved/Willis/shots/{SHOT['tag']}_{SHOT['i']:02d}_{name}.png"
        unreal.AutomationLibrary.take_high_res_screenshot(SHOT["res"][0], SHOT["res"][1], fn)
        SHOT["files"].append(fn)
        log("shots", SHOT["files"])
    SHOT["k"] += 1
    if SHOT["k"] > 80:
        SHOT["k"] = 0
        SHOT["i"] += 1
    return False


QUEUE = [(s, globals()["stage_" + s]) for s in STAGES]
BUSY = [False]
ASYNC = [None]
T0 = time.time()
_h = None
try:
    unreal.unregister_slate_post_tick_callback(__import__("builtins")._willis_place_h)
except Exception:
    pass


def tick(dt):
    if BUSY[0]:
        return
    BUSY[0] = True
    try:
        if ASYNC[0]:
            if ASYNC[0]():
                ASYNC[0] = None
            return
        if not QUEUE:
            unreal.unregister_slate_post_tick_callback(_h)
            log("done", round(time.time() - T0, 1))
            return
        name, fn = QUEUE.pop(0)
        log("stage", name)
        r = fn()
        if r == "async":
            ASYNC[0] = shots_tick
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        try:
            night_off(SHOT.get("saved"))
        except Exception:
            pass
        log("error", traceback.format_exc())
    finally:
        BUSY[0] = False


open(OUT, "w").write(json.dumps({"started": STAGES}))
_h = unreal.register_slate_post_tick_callback(tick)
__import__("builtins")._willis_place_h = _h
