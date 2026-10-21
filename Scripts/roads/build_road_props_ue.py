"""Place everything that stands on Sky City's streets from the road network v2 (Saved/Roads/roadnet.json).

  materials  M_SignalLens2 (each lens knows its intersection's phase, its approach's phase group and how many groups
             the intersection has: green, yellow, red rotate through the groups; walk / don't walk follow the street a
             crosswalk runs alongside), M_RoadGlyph (lane-use arrows and ONLY from an atlas, per-instance cell),
             M_SignAtlas2 (sign faces from an atlas, per-instance cell), barricade stripes
  meshes     SourceArt/RoadKit/meshes (Scripts/roads/blender_signal_kit.py) -> /Game/City/Roads/Kit
  props      signals (poles, arms scaled to the lanes they cover, one head per arriving lane, pedestrian posts and
             heads, controller cabinets), signs (stop + ALL WAY, ONE WAY with the arrow along the traffic, DO NOT
             ENTER, DEAD END, speed limits, street names), barricades, glyph decals, and the street furniture (lamps,
             trees, hydrants, bins, benches, shelters, bus stops, racks, mailboxes, drains, manholes, dumpsters) using
             the first pass's kit meshes. Each kind is one actor with a hierarchical instanced mesh (tag SC_RoadProps);
             the first pass's props (tag SC_StreetProps) are removed.

Run in the editor (PIE off): py Scripts/roads/build_road_props_ue.py [stage ...]
Stages: import materials props save. Writes Saved/MCPScripts/out_roadprops.json.
"""
import glob, json, math, sys, time, traceback, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_roadprops.json"
D = json.load(open(ROOT + "/Saved/Roads/roadnet.json"))
ATLAS1 = json.load(open(ROOT + "/SourceArt/StreetKit/textures/sign_atlas.json"))
KIT_DIR = "/Game/City/Roads/Kit"
OLD_KIT = "/Game/City/Street/Kit"
PH_DIR = "/Game/City/Street/PolyHaven"
MAT_DIR = "/Game/City/Roads/Materials"
STREET_MAT = "/Game/City/Street/Materials"
TAG = "SC_RoadProps"
OLD_TAG = "SC_StreetProps"
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
STAGES = sys.argv[1:] or ["import", "materials", "props", "save"]
out = {"stages": STAGES}
# sign atlas 2 cells (Scripts/roads/make_road_textures.py)
CELL = {"oneway": 0, "noentry": 1, "stop": 2, "allway": 3, "deadend": 4, "roadclosed": 5, 25: 6, 30: 7, 35: 8, 40: 9, 45: 10, 55: 11}
PANEL = {"oneway": (0.9, 0.3), "noentry": (0.75, 0.75), "stop": (0.75, 0.75), "allway": (0.45, 0.15), "deadend": (0.75, 0.75), "speed": (0.6, 0.75)}
GLYPH = {"S": 0, "L": 1, "R": 2, "LS": 3, "SR": 4, "LR": 5, "ONLY": 6}


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


def stage_import():
    meshes = import_files(sorted(glob.glob(ROOT + "/SourceArt/RoadKit/meshes/*.glb")), KIT_DIR)
    tex = import_files(sorted(glob.glob(ROOT + "/SourceArt/RoadKit/textures/*.png")), KIT_DIR + "/Textures")
    for p in tex:
        t = EAL.load_asset(p)
        t.set_editor_property("srgb", True)
        t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
        if "Glyph" in p:
            t.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
            t.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
        EAL.save_loaded_asset(t)
    log("import", {"meshes": len(meshes), "textures": tex})


# ---------------------------------------------------------------- materials
def new_material(name):
    path = f"{MAT_DIR}/{name}"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
        return m
    return AT.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())


def X(m, cls, x, y, **props):
    e = MEL.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def sp(m, name, v, x, y):
    return X(m, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=v)


def vp(m, name, c, x, y):
    return X(m, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name, default_value=unreal.LinearColor(*c))


def custom(m, x, y, code, inputs, otype=unreal.CustomMaterialOutputType.CMOT_FLOAT1):
    c = X(m, unreal.MaterialExpressionCustom, x, y, code=code, output_type=otype)
    ins = []
    for n in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    c.set_editor_property("inputs", ins)
    return c


def link(a, b, pin=""):
    MEL.connect_material_expressions(a, "", b, pin)


def lens_master():
    """Lit by phase: t = frac(time / (GroupTime * N) + phase); the slot of this lens's group is s = t*N - group
    wrapped into [0, N). Green s < 0.8, yellow 0.8..1, red otherwise; walk s < 0.55, flashing don't walk
    0.55..0.8, solid don't walk after. Mode picks which (0 green, 1 yellow, 2 red, 3 walk, 4 don't walk)."""
    m = new_material("M_SignalLens2")
    m.set_editor_property("used_with_instanced_static_meshes", True)
    tm = X(m, unreal.MaterialExpressionTime, -900, 0)
    p = X(m, unreal.MaterialExpressionPerInstanceCustomData, -900, 80, data_index=0)
    g = X(m, unreal.MaterialExpressionPerInstanceCustomData, -900, 160, data_index=1)
    n = X(m, unreal.MaterialExpressionPerInstanceCustomData, -900, 240, data_index=2)
    gt = sp(m, "GroupTime", 22.0, -900, 320)
    mode = sp(m, "Mode", 0.0, -900, 400)
    code = """float NN = max(N, 1.0);
float t = frac(T / (GT * NN) + P);
float s = t * NN - G;
s = s - NN * floor(s / NN);
float lit = 0.0;
if (Mode < 0.5) lit = s < 0.8 ? 1.0 : 0.0;
else if (Mode < 1.5) lit = (s >= 0.8 && s < 1.0) ? 1.0 : 0.0;
else if (Mode < 2.5) lit = s >= 1.0 ? 1.0 : 0.0;
else if (Mode < 3.5) lit = s < 0.55 ? 1.0 : 0.0;
else lit = s >= 0.8 ? 1.0 : ((s >= 0.55) ? step(0.5, frac(T * 1.2)) : 0.0);
return lit;"""
    cu = custom(m, -600, 150, code, ["T", "P", "G", "N", "GT", "Mode"])
    for src, pin in ((tm, "T"), (p, "P"), (g, "G"), (n, "N"), (gt, "GT"), (mode, "Mode")):
        link(src, cu, pin)
    col = vp(m, "LensColor", (1, 0.1, 0.05, 1), -600, -100)
    em = custom(m, -350, 50, "return C * (0.03 + L * B);", ["C", "L", "B"], unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    link(col, em, "C")
    link(cu, em, "L")
    link(sp(m, "Brightness", 40.0, -600, 300), em, "B")
    MEL.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(em, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(sp(m, "Roughness", 0.15, -350, 250), "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def atlas_master(name, tex_path, cols, rows, masked, glow):
    """Texture atlas cell picked by PerInstanceCustomData[0] (cells numbered row-major from the top left)."""
    m = new_material(name)
    m.set_editor_property("used_with_instanced_static_meshes", True)
    if masked:
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    idx = X(m, unreal.MaterialExpressionPerInstanceCustomData, -900, 0, data_index=0)
    tc = X(m, unreal.MaterialExpressionTextureCoordinate, -900, -100)
    uv = custom(m, -650, 0, f"float c = fmod(I, {cols}.0); float r = floor(I / {cols}.0); return (UV + float2(c, r)) / float2({cols}.0, {rows}.0);",
                ["UV", "I"], unreal.CustomMaterialOutputType.CMOT_FLOAT2)
    link(tc, uv, "UV")
    link(idx, uv, "I")
    ts = X(m, unreal.MaterialExpressionTextureSampleParameter2D, -400, 0, parameter_name="Atlas", texture=EAL.load_asset(tex_path),
           sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    link(uv, ts, "UVs")
    if masked:
        # road paint: the same worn white as the lane lines
        MEL.connect_material_property(vp(m, "Paint", (0.8, 0.8, 0.78, 1), -400, 250), "", unreal.MaterialProperty.MP_BASE_COLOR)
        MEL.connect_material_property(ts, "A", unreal.MaterialProperty.MP_OPACITY_MASK)
    else:
        MEL.connect_material_property(ts, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
        em = X(m, unreal.MaterialExpressionMultiply, -150, 150)
        MEL.connect_material_expressions(ts, "RGB", em, "A")
        link(sp(m, "Glow", glow, -400, 300), em, "B")
        MEL.connect_material_property(em, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(sp(m, "Roughness", 0.55, -400, 380), "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def flat_mi(name, parent_path, tint, rough=0.5, metal=0.0):
    path = f"{MAT_DIR}/{name}"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    mi = AT.create_asset(name, MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mi.set_editor_property("parent", EAL.load_asset(parent_path))
    MEL.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(*tint, 1))
    MEL.set_material_instance_scalar_parameter_value(mi, "Roughness", rough)
    MEL.set_material_instance_scalar_parameter_value(mi, "Metallic", metal)
    MEL.update_material_instance(mi)
    EAL.save_loaded_asset(mi)
    return mi


SLOTS = {}


def stage_materials():
    L = lens_master()

    def lens(name, mode, col):
        path = f"{MAT_DIR}/{name}"
        if EAL.does_asset_exist(path):
            EAL.delete_asset(path)
        mi = AT.create_asset(name, MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mi.set_editor_property("parent", L)
        MEL.set_material_instance_scalar_parameter_value(mi, "Mode", mode)
        MEL.set_material_instance_vector_parameter_value(mi, "LensColor", unreal.LinearColor(*col, 1))
        MEL.update_material_instance(mi)
        EAL.save_loaded_asset(mi)
        return mi
    red, yel, grn = (1.0, 0.06, 0.03), (1.0, 0.62, 0.02), (0.1, 1.0, 0.55)
    SLOTS.update({"M_SignalRed": lens("MI_Lens_Red", 2, red), "M_SignalYellow": lens("MI_Lens_Yellow", 1, yel), "M_SignalGreen": lens("MI_Lens_Green", 0, grn),
                  "M_SignalRedArrow": lens("MI_Lens_RedArrow", 2, red), "M_SignalYellowArrow": lens("MI_Lens_YellowArrow", 1, yel),
                  "M_SignalGreenArrow": lens("MI_Lens_GreenArrow", 0, grn),
                  "M_PedWalk": lens("MI_Lens_Walk", 3, (0.9, 0.95, 1.0)), "M_PedDontWalk": lens("MI_Lens_DontWalk", 4, (1.0, 0.45, 0.05))})
    prop_master = "/Game/City/Street/Materials/M_StreetProp"
    SLOTS["M_SignalHousing"] = flat_mi("MI_R_Housing", prop_master, (0.03, 0.03, 0.03), 0.5, 0.2)
    SLOTS["M_SignalBorder"] = flat_mi("MI_R_Border", prop_master, (0.8, 0.65, 0.05), 0.35)
    SLOTS["M_Concrete"] = flat_mi("MI_R_Concrete", prop_master, (0.45, 0.44, 0.42), 0.85)
    SLOTS["M_CabinetMetal"] = flat_mi("MI_R_Cabinet", prop_master, (0.55, 0.57, 0.55), 0.45, 0.5)
    SLOTS["M_SignPost"] = flat_mi("MI_R_SignPost", prop_master, (0.55, 0.56, 0.57), 0.4, 0.8)
    SLOTS["M_SignBack"] = flat_mi("MI_R_SignBack", prop_master, (0.5, 0.51, 0.52), 0.4, 0.8)
    SLOTS["M_BarricadePlastic"] = flat_mi("MI_R_BarricadePlastic", prop_master, (0.85, 0.85, 0.83), 0.5)
    tex = f"{KIT_DIR}/Textures"
    SLOTS["M_SignAtlas"] = atlas_master("M_SignAtlas2", f"{tex}/T_SignAtlas2", 4, 4, False, 0.15)
    SLOTS["M_RoadGlyph"] = atlas_master("M_RoadGlyph", f"{tex}/T_RoadGlyphs", 4, 2, True, 0.0)
    stripe = new_material("M_BarricadeStripe")
    ts = X(stripe, unreal.MaterialExpressionTextureSample, -400, 0, texture=EAL.load_asset(f"{tex}/T_BarricadeStripe"))
    MEL.connect_material_property(ts, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    em = X(stripe, unreal.MaterialExpressionMultiply, -150, 120)
    MEL.connect_material_expressions(ts, "RGB", em, "A")
    link(sp(stripe, "Glow", 0.2, -400, 200), em, "B")
    MEL.connect_material_property(em, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(stripe)
    EAL.save_loaded_asset(stripe)
    SLOTS["M_BarricadeStripe"] = stripe
    for p in EAL.list_assets(KIT_DIR, recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name != "StaticMesh":
            continue
        sm = EAL.load_asset(p.split(".")[0])
        for i, sml in enumerate(sm.get_editor_property("static_materials")):
            base = str(sml.get_editor_property("material_slot_name")).split(".")[0]
            if base in SLOTS:
                sm.set_material(i, SLOTS[base])
        EAL.save_loaded_asset(sm)
    log("materials", sorted(SLOTS))


# ---------------------------------------------------------------- placement
KIT_FRONT = -90.0     # glTF import leaves the Blender kit's front facing local +Y; yaws name the front
WORLD = None


def ue_xf(p, yaw_plan, z, scale=(1.0, 1.0, 1.0), front=True):
    return unreal.Transform(unreal.Vector(p[1] * 100.0, p[0] * 100.0, z),
                            unreal.Rotator(roll=0, pitch=0, yaw=90.0 - yaw_plan + (KIT_FRONT if front else 0.0)),
                            unreal.Vector(*scale))


# Only the street surface counts as ground: the sidewalk/lawn blocks, the bridge decks, the asphalt Ground plane, and
# anything another builder tags "StreetSurface" (a landmark plaza, say). The 20 Oct audit found ~500 lamps, trees,
# posts and manholes standing on top of the L's deck (z 8-11.5 m) and on roofs, because the trace took the first hit.
SURFACE_LABELS = ("R2Blocks_", "R2BridgeDecks", "Ground")


def _is_surface(a):
    if a is None:
        return False
    if a.get_actor_label().startswith(SURFACE_LABELS):
        return True
    return "StreetSurface" in [str(t) for t in a.tags]


def ground_z(p, default=15.0):
    """Height of the street surface at plan point p: trace down, stepping under anything that isn't street surface
    (the L, bridges' trusses, roofs, landmarks); default (15 = sidewalk top, 0 = asphalt) when nothing is found."""
    x, y = p[1] * 100.0, p[0] * 100.0
    top = 3000.0
    for _ in range(6):
        hit = unreal.SystemLibrary.line_trace_single(WORLD, unreal.Vector(x, y, top), unreal.Vector(x, y, -1000),
                                                     unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True)
        if not hit:
            return default
        t = hit.to_tuple()
        z = t[4].z
        if _is_surface(t[9]):
            return z if z < 300.0 else default
        if z >= top - 1.0:          # started inside something solid: give up on tracing here
            return default
        top = z - 2.0
    return default


def add_component(actor, cls):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    BFL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=cls, blueprint_context=None)
    h, fail = sds.add_new_subobject(params)
    return BFL.get_object(BFL.get_data(h))


def instanced(label, mesh, xfs, cull, shadows=False, custom=None, collide=False):
    if not xfs or mesh is None:
        return 0
    act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    act.set_actor_label(label)
    act.set_folder_path("City/Roads/Props")
    act.tags = [TAG, "City_Generated", "NoWallRide"]
    act.set_editor_property("is_spatially_loaded", False)
    c = add_component(act, unreal.HierarchicalInstancedStaticMeshComponent)
    c.set_static_mesh(mesh)
    c.set_editor_property("cast_shadow", shadows)
    c.set_collision_profile_name("BlockAll" if collide else "NoCollision")
    c.set_cull_distances(int(cull * 0.8), int(cull))
    if custom:
        c.set_editor_property("num_custom_data_floats", len(custom[0]))
    c.add_instances(xfs, False, True)
    if custom:
        for i, vals in enumerate(custom):
            for k, v in enumerate(vals):
                c.set_custom_data_value(i, k, float(v), False)
    return len(xfs)


def find_mesh(folder, contains):
    for p in EAL.list_assets(folder, recursive=True):
        a = EAL.find_asset_data(p)
        if a.asset_class_path.asset_name == "StaticMesh" and p.split("/")[-1].split(".")[0].lower() == contains.lower():
            return EAL.load_asset(p.split(".")[0])
    for p in EAL.list_assets(folder, recursive=True):
        a = EAL.find_asset_data(p)
        if a.asset_class_path.asset_name == "StaticMesh" and contains.lower() in p.lower():
            return EAL.load_asset(p.split(".")[0])
    return None


def stage_props():
    global WORLD
    WORLD = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    gone = 0
    for a in EAS.get_all_level_actors():
        tags = [str(t) for t in a.tags]
        if TAG in tags or OLD_TAG in tags:
            EAS.destroy_actor(a)
            gone += 1
    K = lambda n: find_mesh(KIT_DIR, n)
    O = lambda n: find_mesh(OLD_KIT, n)
    PH = lambda n: find_mesh(f"{PH_DIR}/{n}", "")
    M = {"pole": K("RK_SigPole"), "arm": K("RK_SigArm"), "head3": K("RK_SigHead3"), "headL": K("RK_SigHeadL"), "ped": K("RK_PedHead"),
         "pedpost": K("RK_PedPost"), "cabinet": K("RK_Cabinet"), "post": K("RK_SignPost"), "panel": K("RK_SignPanel"),
         "barricade": K("RK_Barricade"), "glyph": K("RK_Glyph"),
         "lamp": O("SK_Lamp_Street"), "lamp_hw": O("SK_Lamp_Highway"), "namepost": O("SK_NamePost"), "blade": O("SK_NameBlade"),
         "rack": O("SK_BikeRack"), "dumpster": O("SK_Dumpster"), "shelter": O("SK_BusShelter"), "busstop": O("SK_BusStopSign"),
         "drain": O("SK_StormDrain"), "mailbox": O("SK_Mailbox"), "grate": O("SK_TreeGrate"),
         "liveoak": O("SK_Tree_liveoak"), "honeylocust": O("SK_Tree_honeylocust"), "linden": O("SK_Tree_linden"), "elm": O("SK_Tree_elm"),
         "hydrant": PH("fire_hydrant"), "bin": PH("metal_trash_can"), "manhole": PH("water_manhole_cover"), "bench": PH("modular_street_seating")}
    missing = [k for k, v in M.items() if v is None]
    G = {k: [] for k in M}
    C = {k: [] for k in M}
    # signals
    for pl in D["signals"]["poles"]:
        z = ground_z(pl["p"])
        if pl.get("low"):
            # under the L: the 6.6 m pole cut to 4.2 m, no mast arm (the heads sit on the post)
            G["pole"].append(ue_xf(pl["p"], pl["yaw"], z, scale=(1.0, 1.0, 4.2 / 6.6)))
            continue
        G["pole"].append(ue_xf(pl["p"], pl["yaw"], z))
        G["arm"].append(ue_xf(pl["p"], pl["yaw"], z + 600.0, scale=(1.0, pl["arm"], 1.0)))
    for hd in D["signals"]["heads"]:
        z = ground_z(hd["p"], 0.0) if hd["z"] < 5 else 0.0
        base = ground_z(hd["p"], 0.0)
        hang = 420.0 if hd.get("low") else (590.0 if hd["z"] >= 5 else 445.0)
        k = "headL" if hd["type"] == "L" else "head3"
        G[k].append(ue_xf(hd["p"], hd["yaw"], base + hang))
        C[k].append([hd["phase"], hd["group"], hd["ngroups"]])
    for pd in D["signals"]["peds"]:
        z = ground_z(pd["p"])
        G["pedpost"].append(ue_xf(pd["p"], pd["yaw"], z))
        G["ped"].append(ue_xf(pd["p"], pd["yaw"], z + 280.0))
        C["ped"].append([pd["phase"], pd["group"], pd["ngroups"]])
    for cb in D["signals"]["cabinets"]:
        G["cabinet"].append(ue_xf(cb["p"], cb["yaw"], ground_z(cb["p"])))
    # signs: one post, one or two panels
    for sg in D["signs"]:
        kind = sg["kind"]
        z = ground_z(sg["p"])
        if kind == "oneway":
            yaw = sg["arrow"] - 90.0            # front normal: the arrow (printed pointing right) runs along the traffic
            w, h = PANEL["oneway"]
            G["post"].append(ue_xf(sg["p"], yaw, z))
            G["panel"].append(ue_xf(sg["p"], yaw, z + 230.0, scale=(w / 0.9, 1.0, h / 0.9)))
            C["panel"].append([CELL["oneway"]])
            continue
        if kind == "speed":
            mph = min((25, 30, 35, 40, 45, 55), key=lambda m: abs(m - sg.get("mph", 30)))
            cell, (w, h) = CELL[mph], PANEL["speed"]
        else:
            cell, (w, h) = CELL[kind], PANEL[kind]
        G["post"].append(ue_xf(sg["p"], sg["yaw"], z))
        G["panel"].append(ue_xf(sg["p"], sg["yaw"], z + 210.0, scale=(w / 0.9, 1.0, h / 0.9)))
        C["panel"].append([cell])
        if kind == "stop" and sg.get("allway"):
            G["panel"].append(ue_xf(sg["p"], sg["yaw"], z + 185.0, scale=(0.45 / 0.9, 1.0, 0.15 / 0.9)))
            C["panel"].append([CELL["allway"]])
    for b in D["barricades"]:
        G["barricade"].append(ue_xf(b["p"], b["yaw"], ground_z(b["p"], 0.0), scale=(max(0.6, b["w"] / 2.4), 1.0, 1.0)))
    # road glyphs: lane-use arrows and ONLY, 2.5 cm above the asphalt
    for a in D["markings"]["arrows"]:
        G["glyph"].append(ue_xf(a["p"], a["yaw"], 2.5, scale=(1.2, 3.0, 1.0)))
        C["glyph"].append([GLYPH[a["kind"]]])
    for w_ in D["markings"]["words"]:
        G["glyph"].append(ue_xf(w_["p"], w_["yaw"], 2.6, scale=(1.6, 2.4, 1.0)))
        C["glyph"].append([GLYPH["ONLY"]])
    # furniture
    names = ATLAS1["names"]
    for pr in D["props"]:
        t, p, yaw = pr["t"], pr["p"], pr["yaw"]
        if t in ("lamp", "lamp_hw"):
            G[t].append(ue_xf(p, yaw, ground_z(p)))
        elif t == "tree":
            z = ground_z(p)
            sp_ = pr.get("sp", "elm")
            if sp_ in G:
                s = pr.get("scale", 1.0)
                G[sp_].append(ue_xf(p, yaw, z, scale=(s, s, s)))
            if pr.get("pit") == "grate":
                G["grate"].append(ue_xf(p, yaw, z + 0.5))
        elif t == "namesign":
            z = ground_z(p)
            G["namepost"].append(ue_xf(p, yaw, z))
            for k, (nm, yy) in enumerate(((pr["a"], yaw), (pr["b"], pr["yaw_b"]))):
                if nm in names:
                    G["blade"].append(ue_xf(p, yy, z + k * 20.0, front=False))
                    C["blade"].append([names[nm]])
        elif t == "bikerack":
            G["rack"].append(ue_xf(p, yaw, ground_z(p)))
        elif t == "dumpster":
            G["dumpster"].append(ue_xf(p, yaw, ground_z(p), front=False))
        elif t == "drain":
            G["drain"].append(ue_xf(p, yaw, ground_z(p, 0.0) + 0.3, front=False))
        elif t == "manhole":
            G["manhole"].append(ue_xf(p, yaw, ground_z(p, 0.0) + 0.2))
        elif t in ("hydrant", "bin", "bench", "mailbox", "busstop", "shelter"):
            G[t].append(ue_xf(p, yaw, ground_z(p)))
    counts = {}
    cull = {"lamp": 35000, "lamp_hw": 50000, "liveoak": 45000, "honeylocust": 45000, "linden": 45000, "elm": 45000,
            "pole": 30000, "arm": 30000, "head3": 30000, "headL": 30000, "ped": 15000, "pedpost": 15000, "glyph": 12000, "panel": 20000, "post": 20000}
    for k, xfs in G.items():
        if not xfs or M.get(k) is None:
            continue
        counts[k] = instanced(f"RProps_{k}", M[k], xfs, cull.get(k, 18000),
                              shadows=k in ("liveoak", "honeylocust", "linden", "elm", "shelter"),
                              custom=C[k] or None, collide=k in ("pole", "lamp", "lamp_hw"))
    log("props", {"counts": counts, "missing": missing, "removed_old": gone})


def stage_save():
    log("save_level", unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level())
    # World Partition, one file per actor: the new and removed prop actors are their own packages
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
        fn()
        log("stage", name)
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        log("error", traceback.format_exc())
    finally:
        BUSY[0] = False


_h = unreal.register_slate_post_tick_callback(tick)
