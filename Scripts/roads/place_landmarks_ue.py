"""Chicago landmarks from the Blender kit (SourceArt/Landmarks, Scripts/landmarks/blender_landmarks.py) placed at their
REAL positions in the plan (Saved/Mashup/plan_v3.json frame: metres, x east, y north; Unreal X = y*100, Y = x*100):

  Cloud Gate     LM_CloudGate on LM_CloudGatePlaza (Grainger / AT&T Plaza, McCormick Tribune Plaza and the rink outline,
                 Chase Promenade, the Washington / Madison walks), long axis north-south, + a sphere reflection capture
                 so the mirror reflects the plaza instead of the sky light's black lower hemisphere (the old dark band)
  Buckingham     LM_BuckinghamFountain + LM_BuckinghamJets on LM_BuckinghamPlaza (pink paver plaza, lawn ring, fence,
                 pavilions, hedges, the west arm to Columbus Drive toward Congress Plaza)
  Navy Pier      LM_NavyPierDeck (929 m deck at the real place, out past the plan edge into the lake), LM_NavyPierBuildings
                 (headhouse + Family Pavilion, Crystal Gardens, Pier Park rides, Skyline Stage, Shakespeare, garage,
                 Festival Hall + hotel, West Terminal, Lakeview Terrace), LM_NavyPierBallroom, LM_PolkBrosPark(+Jets),
                 the Centennial Wheel (frame, rotor, 42 gondolas) at plan (1684.4, 458.0) with its plane north-south,
                 turning in game at 1.5 deg/s (RotatingMovementComponent; gondolas attached, kept upright),
                 honey locusts along the south promenade past the plan edge
  bridge tender houses at the corners of the Chicago river bridges, each kept off the pavement of Saved/Roads/roadnet.json
                 (pushed outward up to 25 m, else dropped; no two within 12 m)

The site assets are modelled in the plan frame: every one of them is placed at its site origin with NO rotation.
The glTF import maps Blender (x, y, z) to Unreal (x, -y, z) (checked on LM_NavyPierShed / the gondola bounds).

Stages (default: all, in this order):
  import     import the current GLBs from SourceArt/Landmarks/meshes into /Game/City/Landmarks
  nanite     Nanite off on every landmark mesh (the M1 can't draw Nanite; it showed the coarse fallback meshes) and
             complex-as-simple collision (the imported convex hulls stopped the car under the Bean)
  materials  MI_LM_* per material slot (tinted M_StreetProp, the city's textured surfaces), jet material, then assign
  tints      rebuild only some MIs: `tints=M_Brick,M_PinkMarble`
  assign     just assign the existing MIs (after a partial re-import: `import=LM_A,LM_B nanite assign place save`)
  place      remove the old SC_Landmarks actors, place everything (ground height traced at each site)
  clear      remove street props / trees (RProps_*) inside the landmark zones, City Sample building instances on the
             pier, and their boxes in BuildingCollision; zones: SourceArt/Landmarks/landmark_zones.json (plan polygons)
             RE-RUN `clear` after build_road_props_ue.py or a City Sample regeneration
  pickups    lift any pickup instances (pads, Supercharger bays, add-ons) the new plazas cover onto the new surface
  save       save dirty packages (World Partition: one file per actor)
Run in the editor (hold the editor lock):
  py Scripts/roads/place_landmarks_ue.py [import] [nanite] [materials] [place] [clear] [save]
Writes Saved/MCPScripts/out_landmarks.json.
"""
import glob, json, math, random, sys, time, traceback, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_landmarks.json"
PLAN = json.load(open(ROOT + "/Saved/Mashup/plan_v3.json"))
LMJ = json.load(open(ROOT + "/SourceArt/Landmarks/landmarks.json"))
ZONES = json.load(open(ROOT + "/SourceArt/Landmarks/landmark_zones.json"))
DIR = "/Game/City/Landmarks"
TAG = "SC_Landmarks"
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
STAGES = sys.argv[1:] or ["import", "nanite", "materials", "place", "clear", "pickups", "save"]
ONLY = None                     # "import=LM_A,LM_B" limits import / nanite / assign to those meshes
TINTS = []                      # "tints=M_Brick,M_PinkMarble" rebuilds only those MIs
for _a in list(STAGES):
    if _a.startswith("import="):
        ONLY = _a.split("=", 1)[1].split(",")
    if _a.startswith("tints="):
        TINTS = _a.split("=", 1)[1].split(",")
STAGES = [a.split("=")[0] for a in STAGES]
out = {"stages": STAGES}
SITE = {"bean": (369.8, -538.7), "fountain": (731.6, -1300.15), "pier": (1496.0, 451.0)}   # = blender_landmarks.SITES
WHEEL_AT = (1684.4, 458.0)
HUB_M = 30.8                    # = blender_landmarks.WHEEL["HUB"]
R_ATT_M = 26.6                  # gondola pivot radius
BEAN_DECK_M = 0.45
CURRENT = ["LM_CloudGate", "LM_CloudGatePlaza", "LM_BuckinghamFountain", "LM_BuckinghamJets", "LM_BuckinghamPlaza",
           "LM_CentennialWheel_Frame", "LM_CentennialWheel_Rotor", "LM_CentennialWheel_Gondola", "LM_NavyPierDeck",
           "LM_NavyPierBuildings", "LM_NavyPierBallroom", "LM_PolkBrosPark", "LM_PolkBrosJets", "LM_BridgeTenderHouse",
           "LM_CloudGatePlazaSteps"]
NO_COLLISION = ("LM_BuckinghamJets", "LM_PolkBrosJets", "LM_CentennialWheel_Rotor", "LM_CentennialWheel_Gondola", "LM_CloudGatePlazaSteps")


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def stage_import():
    tasks = []
    for name in (ONLY or CURRENT):
        f = f"{ROOT}/SourceArt/Landmarks/meshes/{name}.glb"
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", DIR)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        tasks.append(t)
    AT.import_asset_tasks(tasks)
    log("import", len(tasks))


def stage_nanite():
    """Nanite OFF on every landmark mesh: Kenny's M1 Max (Metal SM5) can't draw Nanite and shows the coarse fallback mesh
    instead (255-5,000 triangles: the faceted Bean with its dark band, broken facades and 'floating slabs')."""
    SMES = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    done = {}
    for p in EAL.list_assets(DIR, recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name != "StaticMesh":
            continue
        sm = EAL.load_asset(p.split(".")[0])
        if ONLY and sm.get_name() not in ONLY:
            continue
        ns = sm.get_editor_property("nanite_settings")
        if ns.get_editor_property("enabled"):
            ns.set_editor_property("enabled", False)
            try:
                SMES.set_nanite_settings(sm, ns, True)
            except Exception:
                sm.modify()
                sm.set_editor_property("nanite_settings", ns)
            EAL.save_loaded_asset(sm)
        # collide with the real surfaces (the import gave convex hulls: the car stopped under the Bean's arch and was
        # launched off the plaza's hull)
        bs = sm.get_editor_property("body_setup")
        if bs and bs.get_editor_property("collision_trace_flag") != unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE:
            sm.modify()
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            try:
                unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).remove_collisions(sm)
            except Exception:
                pass
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            EAL.save_loaded_asset(sm)
        done[sm.get_name()] = [sm.get_num_triangles(0), str(sm.get_editor_property("body_setup").get_editor_property("collision_trace_flag"))]
    log("nanite", done)


def mesh(name):
    for p in EAL.list_assets(DIR, recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name == "StaticMesh" and p.split("/")[-1].split(".")[0] == name:
            return EAL.load_asset(p.split(".")[0])
    return None


def mi(name, tint, rough, metal=0.0, glow=0.0, parent="/Game/City/Street/Materials/M_StreetProp"):
    path = f"{DIR}/Materials/{name}"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
    else:
        m = AT.create_asset(name, f"{DIR}/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    m.set_editor_property("parent", EAL.load_asset(parent))
    MEL.set_material_instance_vector_parameter_value(m, "Tint", unreal.LinearColor(*tint, 1))
    MEL.set_material_instance_scalar_parameter_value(m, "Roughness", rough)
    MEL.set_material_instance_scalar_parameter_value(m, "Metallic", metal)
    MEL.set_material_instance_vector_parameter_value(m, "EmissiveColor", unreal.LinearColor(*tint, 1))
    MEL.set_material_instance_scalar_parameter_value(m, "EmissiveStrength", glow)
    MEL.update_material_instance(m)
    EAL.save_loaded_asset(m)
    return m


def jet_material():
    """Fountain spray: two-sided translucent, mostly see-through in the middle of a jet and soft at its edges (the old
    one read as solid white tubes)."""
    path = f"{DIR}/Materials/M_LM_WaterJet"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
    else:
        m = AT.create_asset("M_LM_WaterJet", f"{DIR}/Materials", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("two_sided", True)
    m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_VOLUMETRIC_NON_DIRECTIONAL)
    c = MEL.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -500, 0)
    c.set_editor_property("constant", unreal.LinearColor(0.78, 0.84, 0.88, 1))
    MEL.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    fr = MEL.create_material_expression(m, unreal.MaterialExpressionFresnel, -600, 150)
    om = MEL.create_material_expression(m, unreal.MaterialExpressionOneMinus, -450, 150)
    pw = MEL.create_material_expression(m, unreal.MaterialExpressionPower, -330, 150)
    e = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, -450, 260)
    e.set_editor_property("r", 2.0)
    k = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, -330, 260)
    k.set_editor_property("r", 0.32)
    mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -200, 150)
    MEL.connect_material_expressions(fr, "", om, "")
    MEL.connect_material_expressions(om, "", pw, "Base")
    MEL.connect_material_expressions(e, "", pw, "Exponent")
    MEL.connect_material_expressions(pw, "", mul, "A")
    MEL.connect_material_expressions(k, "", mul, "B")
    MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_OPACITY)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


# slot -> (tint, roughness, metallic[, glow]) or an existing material path
SLOTS = {
    "M_MirrorSteel": ((0.96, 0.96, 0.97), 0.02, 1.0),
    "M_PinkMarble": ((0.52, 0.34, 0.29), 0.45),     # Georgia pink marble, pinkish tan
    "M_Bronze": ((0.35, 0.25, 0.14), 0.4, 0.9),
    "M_Verdigris": ((0.20, 0.44, 0.37), 0.5, 0.35),
    "M_Water": ((0.05, 0.12, 0.14), 0.05, 0.0),
    "M_Limestone": ((0.74, 0.70, 0.62), 0.75),
    "M_BridgeSteel": ((0.12, 0.13, 0.13), 0.55, 0.5),
    "M_Asphalt": "/Game/City/Street/Materials/MI_Asphalt",
    "M_Railing": ((0.08, 0.08, 0.08), 0.5, 0.6),
    "M_WheelWhite": ((0.86, 0.87, 0.88), 0.4, 0.3),
    "M_Gondola": ((0.20, 0.24, 0.30), 0.15, 0.2),
    "M_Glass": ((0.06, 0.08, 0.10), 0.08, 0.4),
    "M_GlassDark": ((0.03, 0.04, 0.05), 0.06, 0.5),
    "M_Brick": ((0.15, 0.055, 0.03), 0.85),        # tints are LINEAR: 0.15 lin ~ 0.42 sRGB (deep red-brown brick)
    "M_HotelBrick": ((0.24, 0.13, 0.085), 0.85),
    "M_Roof": ((0.24, 0.40, 0.34), 0.55, 0.3),
    "M_RoofRib": ((0.30, 0.47, 0.40), 0.45, 0.35),
    "M_RoofFlat": ((0.30, 0.30, 0.30), 0.8),
    "M_Light": ((1.0, 0.93, 0.8), 0.3, 0.0, 6.0),
    "M_Concrete": ((0.45, 0.44, 0.42), 0.85),
    "M_Steel": ((0.40, 0.41, 0.42), 0.4, 0.8),
    "M_Granite": ((0.60, 0.60, 0.58), 0.55),
    "M_GraniteDark": ((0.28, 0.28, 0.29), 0.5),
    "M_GranitePromenade": ((0.52, 0.50, 0.47), 0.7),
    "M_RinkSurface": ((0.50, 0.52, 0.55), 0.4),
    "M_Lawn": ((0.13, 0.25, 0.08), 0.95),
    "M_Hedge": ((0.06, 0.16, 0.05), 0.9),
    "M_PinkPaver": ((0.62, 0.38, 0.33), 0.8),
    "M_DeckConcrete": ((0.58, 0.57, 0.54), 0.85),
    "M_DockWall": ((0.44, 0.43, 0.41), 0.9),
    "M_DockWallDark": ((0.16, 0.17, 0.16), 0.9),
    "M_Timber": ((0.28, 0.19, 0.11), 0.85),
    "M_SidewalkConcrete": ((0.60, 0.59, 0.56), 0.85),
    "M_DeckPaving": ((0.62, 0.58, 0.53), 0.8),
    "M_Membrane": ((0.94, 0.94, 0.92), 0.6),
    "M_Carousel": ((0.85, 0.52, 0.18), 0.5),
    "M_GarageOpening": ((0.04, 0.04, 0.05), 0.9),
    "M_ParkPaver": ((0.56, 0.53, 0.48), 0.8),
    "M_MosaicBlue": ((0.12, 0.26, 0.56), 0.5),
    "M_MosaicYellow": ((0.82, 0.62, 0.12), 0.5),
}


# paved / planted slots use the city's own textured surface materials (CC0 textures), tinted where the parent allows
TEXTURED = {
    "M_Granite": ("/Game/City/Street/Materials/MI_Sidewalk", (1.08, 1.08, 1.1)),
    "M_GranitePromenade": ("/Game/City/Street/Materials/MI_Sidewalk", (0.95, 0.93, 0.9)),
    "M_GraniteDark": ("/Game/City/Street/Materials/MI_Kerb", None),
    "M_PinkPaver": ("/Game/City/Street/Materials/MI_Sidewalk", (1.0, 0.74, 0.7)),   # pink-grey concrete pavers
    "M_ParkPaver": ("/Game/City/Street/Materials/MI_Paving", (0.95, 1.0, 1.1)),
    "M_DeckPaving": ("/Game/City/Street/Materials/MI_Paving", (1.0, 1.0, 1.05)),
    "M_SidewalkConcrete": ("/Game/City/Street/Materials/MI_Sidewalk", None),
    "M_DeckConcrete": ("/Game/City/Street/Materials/MI_BridgeConcrete", None),
    "M_DockWall": ("/Game/City/Street/Materials/MI_BridgeConcrete", None),
    "M_Lawn": ("/Game/City/Street/Materials/MI_Lawn", None),
}


def textured(slot, parent_path, tint):
    parent = EAL.load_asset(parent_path) if EAL.does_asset_exist(parent_path) else None
    if parent is None:
        return None
    vnames = [str(n) for n in MEL.get_vector_parameter_names(parent)]
    if tint is None or "Tint" not in vnames:
        return parent
    nm = "MI_LM_" + slot[2:]
    path = f"{DIR}/Materials/{nm}"
    m = EAL.load_asset(path) if EAL.does_asset_exist(path) else AT.create_asset(nm, f"{DIR}/Materials", unreal.MaterialInstanceConstant,
                                                                                   unreal.MaterialInstanceConstantFactoryNew())
    m.set_editor_property("parent", parent)
    MEL.set_material_instance_vector_parameter_value(m, "Tint", unreal.LinearColor(*tint, 1))
    MEL.update_material_instance(m)
    EAL.save_loaded_asset(m)
    return m


def stage_tints():
    """Rebuild only the MIs of the slots given as tints=M_A,M_B (each MI save takes the editor ~10 s)."""
    done = {}
    for slot in TINTS:
        if slot in TEXTURED:
            m = textured(slot, *TEXTURED[slot])
        else:
            v = SLOTS[slot]
            m = mi("MI_LM_" + slot[2:], v[0], v[1], v[2] if len(v) > 2 else 0.0, v[3] if len(v) > 3 else 0.0)
        done[slot] = m.get_path_name() if m else None
    log("tints", done)


def stage_assign():
    """Assign the existing MI_LM_* / city materials to the slots of the (re)imported meshes, without rebuilding the MIs
    (saving ~40 MIs takes the editor 5-15 minutes)."""
    S = {}
    for slot, v in SLOTS.items():
        path = None
        if slot in TEXTURED:
            parent, tint = TEXTURED[slot]
            path = f"{DIR}/Materials/MI_LM_{slot[2:]}" if tint is not None else parent
        elif isinstance(v, str):
            path = v
        else:
            path = f"{DIR}/Materials/MI_LM_{slot[2:]}"
        if EAL.does_asset_exist(path):
            S[slot] = EAL.load_asset(path)
    S["M_WaterJet"] = EAL.load_asset(f"{DIR}/Materials/M_LM_WaterJet")
    n = 0
    missing = set()
    for p in EAL.list_assets(DIR, recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name != "StaticMesh":
            continue
        sm = EAL.load_asset(p.split(".")[0])
        if ONLY and sm.get_name() not in ONLY:
            continue
        for i, sml in enumerate(sm.get_editor_property("static_materials")):
            base = str(sml.get_editor_property("material_slot_name")).split(".")[0]
            if base in S and S[base]:
                sm.set_material(i, S[base])
                n += 1
            else:
                missing.add(base)
        EAL.save_loaded_asset(sm)
    log("assign", {"assigned": n, "unmapped_slots": sorted(missing)})


def stage_materials():
    S = {}
    info = {}
    for slot, v in SLOTS.items():
        if slot in TEXTURED:
            t = textured(slot, *TEXTURED[slot])
            if t is not None:
                S[slot] = t
                info[slot] = t.get_path_name()
                continue
        if isinstance(v, str):
            S[slot] = EAL.load_asset(v)
        else:
            nm = "MI_LM_" + slot[2:]
            S[slot] = mi(nm, v[0], v[1], v[2] if len(v) > 2 else 0.0, v[3] if len(v) > 3 else 0.0)
    try:
        out["surface_params"] = {p_: [str(n) for n in MEL.get_vector_parameter_names(EAL.load_asset(p_))] + [str(n) for n in MEL.get_scalar_parameter_names(EAL.load_asset(p_))]
                                 for p_ in ("/Game/City/Street/Materials/MI_Paving", "/Game/City/Street/Materials/M_StreetProp")}
    except Exception as e:
        out["surface_params"] = str(e)
    out["textured"] = info
    S["M_WaterJet"] = jet_material()
    n = 0
    missing = set()
    for p in EAL.list_assets(DIR, recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name != "StaticMesh":
            continue
        sm = EAL.load_asset(p.split(".")[0])
        for i, sml in enumerate(sm.get_editor_property("static_materials")):
            base = str(sml.get_editor_property("material_slot_name")).split(".")[0]
            if base in S and S[base]:
                sm.set_material(i, S[base])
                n += 1
            else:
                missing.add(base)
        EAL.save_loaded_asset(sm)
    log("materials", {"assigned": n, "unmapped_slots": sorted(missing)})


WORLD = None
IGNORE = []


def ground_z(px, py, default=15.0):
    """Ground height (cm) at plan (px, py): the first hit that isn't a landmark, prop, City Sample piece or collision box."""
    x, y = py * 100.0, px * 100.0
    hit = unreal.SystemLibrary.line_trace_single(WORLD, unreal.Vector(x, y, 8000), unreal.Vector(x, y, -2000),
                                                 unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, IGNORE, unreal.DrawDebugTrace.NONE, True)
    if hit:
        t = hit.to_tuple()
        return t[4].z, (t[9].get_actor_label() if t[9] else "")
    return default, ""


def spawn(sm, label, loc, yaw=0.0, collide=True, folder="City/Landmarks"):
    a = EAS.spawn_actor_from_object(sm, loc, unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.set_actor_label(label)
    a.set_folder_path(folder)
    a.tags = [TAG, "City_Generated"]
    a.set_editor_property("is_spatially_loaded", False)
    c = a.static_mesh_component
    c.set_collision_profile_name("BlockAll" if collide else "NoCollision")
    if not collide:
        c.set_editor_property("cast_shadow", True)
    return a


def U(px, py, z):
    return unreal.Vector(py * 100.0, px * 100.0, z)


# ------------------------------------------------------------------ bridge tender houses off the pavement
def inside_poly(poly, x, y):
    c = False; n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c

def pavement_index(rn, cell=50.0):
    polys = []
    for e in rn["edges"]:
        rb = e.get("ribbon")
        if rb:
            polys.append(json.loads(rb) if isinstance(rb, str) else rb)
    polys += [j["ring"] for j in rn["junctions"]] + list(rn["joints"])
    grid = {}
    out = []
    for p in polys:
        xs = [q[0] for q in p]; ys = [q[1] for q in p]
        b = (min(xs), max(xs), min(ys), max(ys))
        k = len(out); out.append((p, b))
        for gx in range(int(b[0] // cell), int(b[1] // cell) + 1):
            for gy in range(int(b[2] // cell), int(b[3] // cell) + 1):
                grid.setdefault((gx, gy), []).append(k)
    def on(x, y):
        for k in grid.get((int(x // cell), int(y // cell)), ()):
            p, b = out[k]
            if b[0] <= x <= b[1] and b[2] <= y <= b[3] and inside_poly(p, x, y):
                return True
        return False
    return on

def _tender_layout(plan, on_pavement):
    """Four houses per Chicago river bridge (15-130 m, not expressways), 6 m back from each end and beside the deck;
    each is pushed outward along the bridge normal (1 m steps, up to 25 m) until its 9 x 9 m footprint is off the
    pavement, dropped if it never is, and dropped if it would stand within 12 m of a house already placed
    (streets-junctions found 54 of 196 in the lanes, 18 stacked at one crossing)."""
    houses, dropped, moved = [], 0, 0
    for b in plan["bridges"]:
        if b["cls"] == "highway":
            continue
        pts = b["pts"]
        L = sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))
        if not 15 <= L <= 130:
            continue
        a, c = pts[0], pts[-1]
        if a[0] < -900 and c[0] < -900:
            continue
        d = ((c[0] - a[0]) / L, (c[1] - a[1]) / L)
        n = (-d[1], d[0])
        half = {"major": 13.0, "mid": 10.0, "minor": 8.0}.get(b["cls"], 10.0) + 4.0
        yaw = math.degrees(math.atan2(d[0], d[1]))
        for end, sgn in ((a, -1), (c, 1)):
            for side in (1, -1):
                ok = None
                for push in range(0, 26):
                    off = half + push
                    q = (end[0] + d[0] * sgn * 6.0 + n[0] * side * off, end[1] + d[1] * sgn * 6.0 + n[1] * side * off)
                    samples = [(q[0] + dx, q[1] + dy) for dx in (-4.5, 0.0, 4.5) for dy in (-4.5, 0.0, 4.5)]
                    if not any(on_pavement(x, y) for x, y in samples):
                        ok = (q, push)
                        break
                if ok is None:
                    dropped += 1
                    continue
                q, push = ok
                if any(math.dist(q, h[0]) < 12.0 for h in houses):
                    dropped += 1
                    continue
                moved += push > 0
                houses.append((q, yaw))
    return houses, dropped, moved

def tender_layout():
    rn = json.load(open(ROOT + "/Saved/Roads/roadnet.json"))
    hs, dropped, moved = _tender_layout(PLAN, pavement_index(rn))
    return hs, {"houses": len(hs), "dropped": dropped, "moved_off_pavement": moved}


def stage_place():
    global WORLD, IGNORE
    WORLD = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    old_labels = ("Landmark_TheBean", "Landmark_BuckinghamFountain", "Landmark_NavyPier")
    gone = 0
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags] or a.get_actor_label() in old_labels:
            EAS.destroy_actor(a)
            gone += 1
    acts = EAS.get_all_level_actors()
    IGNORE = [a for a in acts if a.get_actor_label().startswith(("RProps_", "CS_", "HLOD", "SC_", "LM_")) or
              a.get_actor_label() in ("BuildingCollision", "WorldBounds") or "HLOD" in a.get_class().get_name()]
    placed = {}
    M = {n: mesh(n) for n in CURRENT}
    out["missing_meshes"] = [n for n, m in M.items() if m is None]
    # --- Cloud Gate on its plaza, long axis north-south (the mesh's long axis is Unreal X = north)
    ox, oy = SITE["bean"]
    gz, under = ground_z(ox, oy)
    placed["bean"] = {"ground_cm": gz, "under": under}
    spawn(M["LM_CloudGatePlaza"], "LM_CloudGatePlaza", U(ox, oy, gz))
    if M.get("LM_CloudGatePlazaSteps"):
        spawn(M["LM_CloudGatePlazaSteps"], "LM_CloudGatePlazaSteps", U(ox, oy, gz), collide=False)
    bean = spawn(M["LM_CloudGate"], "LM_CloudGate", U(ox, oy, gz + BEAN_DECK_M * 100.0))
    # the capture sits inside the Bean: hide the Bean from captures so it records the plaza, trees and sky round it
    bean.static_mesh_component.set_editor_property("visible_in_reflection_captures", False)
    cap = EAS.spawn_actor_from_class(unreal.SphereReflectionCapture, U(ox, oy, gz + BEAN_DECK_M * 100.0 + 450.0))
    cap.set_actor_label("LM_CloudGate_ReflectionCapture")
    cap.set_folder_path("City/Landmarks")
    cap.tags = [TAG, "City_Generated"]
    cap.set_editor_property("is_spatially_loaded", False)
    try:
        cap.get_component_by_class(unreal.SphereReflectionCaptureComponent).set_editor_property("influence_radius", 3500.0)
    except Exception as e:
        placed["capture_radius_error"] = str(e)
    # --- Buckingham Fountain, its jets and plaza
    ox, oy = SITE["fountain"]
    gz, under = ground_z(ox + 60.0, oy + 60.0)          # on the lawn ring away from the old fountain mesh
    placed["fountain"] = {"ground_cm": gz, "under": under}
    spawn(M["LM_BuckinghamPlaza"], "LM_BuckinghamPlaza", U(ox, oy, gz))
    spawn(M["LM_BuckinghamFountain"], "LM_BuckinghamFountain", U(ox, oy, gz))
    spawn(M["LM_BuckinghamJets"], "LM_BuckinghamJets", U(ox, oy, gz), collide=False)
    # --- Navy Pier (one origin for all its assets) and Polk Bros Park
    ox, oy = SITE["pier"]
    gz, under = ground_z(1600.0, 451.0)
    placed["pier"] = {"ground_cm": gz, "under": under}
    for n in ("LM_NavyPierDeck", "LM_NavyPierBuildings", "LM_NavyPierBallroom", "LM_PolkBrosPark", "LM_PolkBrosJets"):
        spawn(M[n], n, U(ox, oy, gz), collide=n not in NO_COLLISION)
    # --- the Centennial Wheel: plane north-south (Unreal X-Z), axle east-west
    wx, wy = WHEEL_AT
    base = gz + 6.0
    spawn(M["LM_CentennialWheel_Frame"], "LM_CentennialWheel_Frame", U(wx, wy, base))
    hub = U(wx, wy, base + HUB_M * 100.0)
    rotor = spawn(M["LM_CentennialWheel_Rotor"], "LM_CentennialWheel_Rotor", hub, collide=False)
    gondolas = []
    for k in range(42):
        a_ = 2 * math.pi * k / 42
        gondolas.append(spawn(M["LM_CentennialWheel_Gondola"], f"LM_Gondola_{k}",
                              unreal.Vector(hub.x + R_ATT_M * 100.0 * math.sin(a_), hub.y, hub.z - R_ATT_M * 100.0 * math.cos(a_)), collide=False))
    placed["wheel_turns"] = wheel_motion(rotor, gondolas)
    # --- honey locusts in the south promenade's tree pits east of the plan edge (the city's own tree mesh)
    placed["pier_trees"] = pier_trees(gz)
    # --- bridge tender houses at the Chicago river bridges, kept off the pavement (tender_layout)
    th = M["LM_BridgeTenderHouse"]
    n_th = 0
    if th:
        houses, info = tender_layout()
        placed["tender_layout"] = info
        for q, yaw in houses:
            z, _u = ground_z(q[0], q[1])
            spawn(th, f"LM_TenderHouse_{n_th}", U(q[0], q[1], z), yaw)
            n_th += 1
    placed["tender_houses"] = n_th
    log("place", {"placed": placed, "removed": gone})


def add_component(actor, cls):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    BFL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=cls, blueprint_context=None)
    h, fail = sds.add_new_subobject(params)
    return BFL.get_object(BFL.get_data(h))


def wheel_motion(rotor, gondolas):
    """The Centennial Wheel turns in game: 3 revolutions per 12-minute ride (Wikipedia) = 1.5 deg/s about its east-west
    axle (Unreal Y = pitch), by an engine RotatingMovementComponent on the rotor; the 42 gondolas are attached to it with
    absolute rotation, so they ride round the rim and stay upright."""
    try:
        rotor.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
        rm = add_component(rotor, unreal.RotatingMovementComponent)
        rm.set_editor_property("rotation_rate", unreal.Rotator(roll=0.0, pitch=1.5, yaw=0.0))
        rm.set_editor_property("rotation_in_local_space", True)
        for g in gondolas:
            g.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
            g.attach_to_actor(rotor, "", unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD,
                              unreal.AttachmentRule.KEEP_WORLD, False)
            g.static_mesh_component.set_absolute(False, True, False)
        return "1.5 deg/s"
    except Exception:
        return traceback.format_exc()[-600:]


def pier_trees(gz):
    """Honey locusts in the south promenade's tree pits east of the plan edge, same mesh / custom data / culling /
    collision as the street builder's RProps_honeylocust."""
    srca = next((a for a in EAS.get_all_level_actors() if a.get_actor_label() == "RProps_honeylocust"), None)
    cs = srca.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent) if srca else []
    if not cs:
        return "no RProps_honeylocust"
    src = cs[0]
    act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    act.set_actor_label("LM_PierTrees")
    act.set_folder_path("City/Landmarks")
    act.tags = [TAG, "City_Generated", "NoWallRide"]
    act.set_editor_property("is_spatially_loaded", False)
    c = add_component(act, unreal.HierarchicalInstancedStaticMeshComponent)
    c.set_static_mesh(src.static_mesh)
    c.set_editor_property("cast_shadow", src.get_editor_property("cast_shadow"))
    c.set_collision_profile_name(src.get_collision_profile_name())
    try:
        c.set_cull_distances(src.get_editor_property("instance_start_cull_distance"), src.get_editor_property("instance_end_cull_distance"))
    except Exception:
        pass
    ncd = src.get_editor_property("num_custom_data_floats")
    cd = list(src.get_editor_property("per_instance_sm_custom_data"))[:ncd] if ncd else []
    rnd = random.Random(11)
    T = []
    for k in range(49):
        x = 1732.0 + 10.0 * k
        for y in (394.5, 403.5):
            sc = rnd.uniform(0.85, 1.1)
            T.append(unreal.Transform(U(x, y, gz + 6.0), unreal.Rotator(0, 0, rnd.uniform(0, 360)), unreal.Vector(sc, sc, sc)))
    if ncd:
        c.set_editor_property("num_custom_data_floats", ncd)
    c.add_instances(T, False, True)
    for i in range(len(T)):
        for k, v in enumerate(cd):
            c.set_custom_data_value(i, k, float(v), False)
    return len(T)


# ------------------------------------------------------------------ clear: props, trees and buildings inside the zones
def inside(poly, x, y):
    c = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def zone_hit(zs, X, Y):
    """Unreal X, Y (cm) -> True if inside any of the zones (plan polygons)."""
    px, py = Y / 100.0, X / 100.0
    for z in zs:
        b = z["bbox"]
        if b[0] <= px <= b[1] and b[2] <= py <= b[3] and inside(z["poly"], px, py):
            return True
    return False


def stage_clear():
    for z in ZONES["zones"]:
        xs = [p[0] for p in z["poly"]]
        ys = [p[1] for p in z["poly"]]
        z["bbox"] = [min(xs), max(xs), min(ys), max(ys)]
    props_z = [z for z in ZONES["zones"] if "props" in z["clear"]]
    bldg_z = [z for z in ZONES["zones"] if "buildings" in z["clear"]]
    res = {"props": {}, "buildings": 0, "collision": None}
    for a in EAS.get_all_level_actors():
        lab = a.get_actor_label()
        if lab.startswith("RProps_"):
            zs = props_z
        elif lab.startswith("CS_"):
            zs = bldg_z
        else:
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            n = c.get_instance_count()
            if not n:
                continue
            o, e, _r = unreal.SystemLibrary.get_component_bounds(c)
            if not any(o.x + e.x >= z["bbox"][2] * 100 and o.x - e.x <= z["bbox"][3] * 100 and o.y + e.y >= z["bbox"][0] * 100 and
                       o.y - e.y <= z["bbox"][1] * 100 for z in zs):
                continue
            kill = []
            for i in range(n):
                p = c.get_instance_transform(i, True).translation
                if zone_hit(zs, p.x, p.y):
                    kill.append(i)
            if kill:
                a.modify()
                c.modify()
                c.remove_instances(kill)
                if lab.startswith("RProps_"):
                    res["props"][lab] = res["props"].get(lab, 0) + len(kill)
                else:
                    res["buildings"] += len(kill)
    res["roof_caps"] = carve_roof_caps(bldg_z)
    res["collision"] = carve_collision(bldg_z)
    log("clear", res)


def carve_roof_caps(zs):
    """The City Sample PCG volumes also generate the flat roof caps as one DynamicMeshComponent per volume: delete its
    triangles that lie inside a building zone (else the caps float over the pier once the walls are gone)."""
    done = {}
    for a in EAS.get_all_level_actors():
        lab = a.get_actor_label()
        if not lab.startswith("CS_"):
            continue
        for c in a.get_components_by_class(unreal.DynamicMeshComponent):
            co, ce, _r = unreal.SystemLibrary.get_component_bounds(c)
            hit = [z for z in zs if co.x + ce.x >= z["bbox"][2] * 100 and co.x - ce.x <= z["bbox"][3] * 100 and
                   co.y + ce.y >= z["bbox"][0] * 100 and co.y - ce.y <= z["bbox"][1] * 100]
            if not hit:
                continue
            try:
                xf = c.get_world_transform()
                inv = xf.inverse()
                dm = c.get_dynamic_mesh()
                before = dm.get_triangle_count()
                for z in hit:
                    b = z["bbox"]
                    pts = [inv.transform_location(unreal.Vector(X, Y, Z)) for X in (b[2] * 100, b[3] * 100) for Y in (b[0] * 100, b[1] * 100)
                           for Z in (-5000.0, 100000.0)]
                    lo = unreal.Vector(min(p_.x for p_ in pts), min(p_.y for p_ in pts), min(p_.z for p_ in pts))
                    hi = unreal.Vector(max(p_.x for p_ in pts), max(p_.y for p_ in pts), max(p_.z for p_ in pts))
                    r = unreal.GeometryScript_MeshSelection.select_mesh_elements_in_box(dm, unreal.Box(lo, hi),
                                                                                      unreal.GeometryScriptMeshSelectionType.TRIANGLES, False, 3)
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
                done[lab + "|" + c.get_name()] = [before, after, round(xf.rotation.rotator().yaw, 2)]
            except Exception:
                done[lab + "|" + c.get_name()] = traceback.format_exc()[-400:]
    return done


def carve_collision(zs):
    """Delete the BuildingCollision boxes whose triangles all lie inside a building zone's bounding box."""
    act = next((a for a in EAS.get_all_level_actors() if a.get_actor_label() == "BuildingCollision"), None)
    if not act:
        return "no BuildingCollision"
    sm = act.static_mesh_component.static_mesh
    dm = unreal.DynamicMesh()
    try:
        GS = unreal.GeometryScript_AssetUtils
        opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
        r = GS.copy_mesh_from_static_mesh(sm, dm, opts, unreal.GeometryScriptMeshReadLOD())
        dm = r[0] if isinstance(r, (tuple, list)) else dm
        before = dm.get_triangle_count()
        for z in zs:
            b = z["bbox"]
            box = unreal.Box(unreal.Vector(b[2] * 100, b[0] * 100, -5000), unreal.Vector(b[3] * 100, b[1] * 100, 100000))
            r = unreal.GeometryScript_MeshSelection.select_mesh_elements_in_box(dm, box, unreal.GeometryScriptMeshSelectionType.TRIANGLES, False, 3)
            sel = next((x for x in (r if isinstance(r, (tuple, list)) else [r]) if isinstance(x, unreal.GeometryScriptMeshSelection)), None)
            if sel is None:
                return "no selection from select_mesh_elements_in_box: %r" % (r,)
            r = unreal.GeometryScript_MeshEdits.delete_selected_triangles_from_mesh(dm, sel)
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


def stage_pickups():
    """Pickups (SC_Pads*, SC_Chargers, SC_Addons instances) that the new plazas cover are lifted onto the new surface."""
    global WORLD
    WORLD = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    for z in ZONES["zones"]:
        xs = [p[0] for p in z["poly"]]
        ys = [p[1] for p in z["poly"]]
        z["bbox"] = [min(xs), max(xs), min(ys), max(ys)]
    zs = [z for z in ZONES["zones"] if "props" in z["clear"]]
    acts = EAS.get_all_level_actors()
    pick = [a for a in acts if a.get_actor_label().startswith(("SC_Pads", "SC_Chargers", "SC_Addons"))]
    res = {}
    for a in pick:
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            for i in range(c.get_instance_count()):
                t = c.get_instance_transform(i, True)
                p = t.translation
                if not zone_hit(zs, p.x, p.y):
                    continue
                hit = unreal.SystemLibrary.line_trace_single(WORLD, unreal.Vector(p.x, p.y, p.z + 3000), unreal.Vector(p.x, p.y, p.z - 500),
                                                             unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, pick, unreal.DrawDebugTrace.NONE, True)
                if not hit:
                    continue
                hz = hit.to_tuple()[4].z
                key = a.get_actor_label() + "|" + c.get_name()
                if hz > p.z + 1.0 and hz - p.z < 120.0:
                    a.modify()
                    c.modify()
                    t.translation = unreal.Vector(p.x, p.y, hz)
                    c.update_instance_transform(i, t, True, True, True)
                    res.setdefault(key, []).append([round(p.x), round(p.y), round(hz - p.z, 1)])
                else:
                    res.setdefault(key + "|ok", []).append([round(p.x), round(p.y), round(hz - p.z, 1)])
    log("pickups", res)


def stage_save():
    log("save", unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True))


_MAP = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name()
if "SkyCityMashup" not in _MAP:
    log("error", "the loaded map is %s, not SkyCityMashup: nothing done" % _MAP)
    STAGES = []
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
