"""Chicago's water side in SkyCityMashup: the Chicago Harbor Lock, the harbours' floating docks, the Dime Pier breakwater,
harbour lights and the boats (DuSable Harbor's slips, Monroe Harbor's mooring field, the Navy Pier Marina, the
excursion ships along Navy Pier's south dock, the river tour boats / water taxis / tiki boats / kayaks at their real
berths, the Columbia Yacht Club's ferry Abegweit, boats in the lock and under way), all at their REAL positions
(OpenStreetMap + NAIP aerials; plan frame of Saved/Mashup/plan_v3.json: metres, x east, y north; Unreal X = y*100,
Y = x*100). Meshes: Scripts/landmarks/blender_chicago_water.py -> SourceArt/Landmarks/water/*.glb; positions:
SourceArt/Landmarks/water/water_layout.json (written by the same Blender script).

Heights: plan ground = Unreal z 0, water surface = -550 cm (build_city.py WATER_Z). Boats stand on the water with
their waterline at -550; site meshes (lock, docks, breakwater) are modelled relative to the ground and placed at z 0
with NO rotation; gate leaves get yaw = -(plan angle). Boats bob gently: their materials are instances of
M_CW_BoatBob (world-position offset: heave + small roll / pitch, phase per instance). Rerunnable: every actor this
script places carries the tag SC_ChicagoWater (folder City/Water) and is replaced on the next `place`.

Stages (default: survey import nanite materials place clear save):
  survey     read-only report: ground height and what stands at the key spots (Saved/MCPScripts/out_chicago_water.json)
  import     import the GLBs into /Game/City/Water (`import=CW_A,CW_B` limits it)
  nanite     Nanite off, collision = the render mesh (complex as simple), auto LODs on the boat meshes
  materials  M_CW_BoatBob + MI_CWB_* (boats), MI_CW_* (structures), reuse of the landmarks' MI_LM_*; assign
  assign     only assign existing MIs (after a partial re-import)
  place      remove the old SC_ChicagoWater actors, place everything
  clear      remove street props / trees / City Sample instances that stand inside the lock walls or on the Abegweit
  save       save dirty packages (World Partition: one file per actor)
Run in the editor (hold the editor lock):
  py Scripts/roads/place_chicago_water_ue.py [stages...]
"""
import json, math, random, sys, time, traceback, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_chicago_water.json"
SRC = ROOT + "/SourceArt/Landmarks/water"
LAY = json.load(open(SRC + "/water_layout.json"))
META = json.load(open(SRC + "/water.json"))["assets"]
DIR = "/Game/City/Water"
LMDIR = "/Game/City/Landmarks/Materials"
TAG = "SC_ChicagoWater"
FOLDER = "City/Water"
WATER_CM = -550.0
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
STAGES = sys.argv[1:] or ["survey", "import", "nanite", "materials", "place", "clear", "save"]
ONLY = None
for _a in list(STAGES):
    if _a.startswith("import="):
        ONLY = _a.split("=", 1)[1].split(",")
STAGES = [a.split("=")[0] for a in STAGES]
out = {"stages": STAGES, "t0": time.strftime("%H:%M:%S")}
ALL = sorted(META)
BOATS = [n for n in ALL if n.startswith(("CW_Sloop", "CW_Motor", "CW_Tour", "CW_Water", "CW_Speed", "CW_Cruise", "CW_Tall", "CW_Tiki",
                                         "CW_Kayak", "CW_Mooring"))]
NO_COLLISION = ("CW_MooringBuoy", "CW_Kayak")


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def U(px, py, z):
    return unreal.Vector(py * 100.0, px * 100.0, z)


def yaw_of(h):
    """plan heading (deg CCW from east) -> Unreal yaw (deg from +X=north toward +Y=east)."""
    return 90.0 - h


# ------------------------------------------------------------------ survey
def stage_survey():
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    spots = {"lock_south_wall_in_map": (1700.0, 76.0), "lock_north_wall_in_map": (1700.0, 114.0), "lock_chamber": (1700.0, 96.0),
             "lock_east_beyond_map": (1800.0, 96.0), "abegweit_island": (1311.0, -401.0), "dusable_water": (1350.0, -200.0),
             "monroe_water": (1200.0, -900.0), "river_mid": (700.0, 110.0), "pier_south_water": (1850.0, 370.0),
             "dime_pier": (1977.0, 246.0), "cyc_monroe_station": (973.0, -715.0), "approach_wall": (1600.0, 70.0),
             "easterly_breakwater": (1463.0, -800.0), "riverwalk_south_bank": (700.0, 70.0)}
    res = {}
    for k, (px, py) in spots.items():
        x, y = py * 100.0, px * 100.0
        hits = unreal.SystemLibrary.line_trace_multi(w, unreal.Vector(x, y, 20000), unreal.Vector(x, y, -3000),
                                                    unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True)
        res[k] = [(round(h.to_tuple()[4].z, 1), h.to_tuple()[9].get_actor_label() if h.to_tuple()[9] else "") for h in (hits or [])][:6]
    acts = EAS.get_all_level_actors()
    res["water_actors"] = [(a.get_actor_label(), round(a.get_actor_location().z, 1)) for a in acts
                           if a.get_actor_label() in ("Water", "HorizonLake", "WaterCollision", "Ground") or "Water" in a.get_actor_label()][:20]
    res["existing_cw"] = sum(1 for a in acts if TAG in [str(t) for t in a.tags])
    # instances (props / City Sample) standing on the lock walls or the Abegweit island
    polys = list(LAY["lock_outlines"].values()) + [LAY["abegweit"]["island"]] + LAY.get("riverwalk_zone", [])
    res["intruders"] = intruders(acts, polys, dry=True)
    log("survey", res)


# ------------------------------------------------------------------ import / nanite
def stage_import():
    tasks = []
    for name in (ONLY or ALL):
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f"{SRC}/{name}.glb")
        t.set_editor_property("destination_path", DIR)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        tasks.append(t)
    AT.import_asset_tasks(tasks)
    log("import", len(tasks))


def mesh(name):
    p = f"{DIR}/{name}"
    if EAL.does_asset_exist(p):
        a = EAL.load_asset(p)
        if isinstance(a, unreal.StaticMesh):
            return a
    for q in EAL.list_assets(DIR, recursive=True):
        if q.split("/")[-1].split(".")[0] == name and EAL.find_asset_data(q).asset_class_path.asset_name == "StaticMesh":
            return EAL.load_asset(q.split(".")[0])
    return None


def stage_nanite():
    SMES = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    done = {}
    for name in (ONLY or ALL):
        sm = mesh(name)
        if not sm:
            done[name] = "missing"
            continue
        ns = sm.get_editor_property("nanite_settings")
        if ns.get_editor_property("enabled"):
            ns.set_editor_property("enabled", False)
            try:
                SMES.set_nanite_settings(sm, ns, True)
            except Exception:
                sm.modify()
                sm.set_editor_property("nanite_settings", ns)
        bs = sm.get_editor_property("body_setup")
        if bs:
            sm.modify()
            try:
                SMES.remove_collisions(sm)
            except Exception:
                pass
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        if name in BOATS and sm.get_num_lods() < 2:
            try:
                opts = unreal.EditorScriptingMeshReductionOptions()
                opts.set_editor_property("auto_compute_lod_screen_size", False)
                opts.set_editor_property("reduction_settings", [
                    unreal.EditorScriptingMeshReductionSettings(percent_triangles=1.0, screen_size=1.0),
                    unreal.EditorScriptingMeshReductionSettings(percent_triangles=0.45, screen_size=0.12),
                    unreal.EditorScriptingMeshReductionSettings(percent_triangles=0.15, screen_size=0.035)])
                SMES.set_lods(sm, opts)
            except Exception as e:
                done[name + "_lod"] = str(e)[:200]
        EAL.save_loaded_asset(sm)
        done[name] = [sm.get_num_triangles(0), sm.get_num_lods(), str(bs.get_editor_property("collision_trace_flag")) if bs else None]
    log("nanite", done)


# ------------------------------------------------------------------ materials
BOAT_SLOTS = {   # slot -> (tint LINEAR, roughness, metallic, glow)
    "M_CWB_HullWhite": ((0.80, 0.81, 0.82), 0.3, 0.0), "M_CWB_HullNavy": ((0.012, 0.025, 0.08), 0.3, 0.0),
    "M_CWB_HullYellow": ((0.90, 0.50, 0.01), 0.35, 0.0), "M_CWB_HullBlack": ((0.01, 0.01, 0.012), 0.35, 0.0),
    "M_CWB_Bottom": ((0.12, 0.02, 0.015), 0.6, 0.0), "M_CWB_Boot": ((0.02, 0.025, 0.04), 0.4, 0.0),
    "M_CWB_Stripe": ((0.015, 0.035, 0.12), 0.3, 0.0), "M_CWB_Maroon": ((0.12, 0.012, 0.015), 0.35, 0.0),
    "M_CWB_Green": ((0.01, 0.06, 0.03), 0.4, 0.0), "M_CWB_Teak": ((0.17, 0.08, 0.035), 0.7, 0.0),
    "M_CWB_DeckGrey": ((0.55, 0.55, 0.52), 0.8, 0.0), "M_CWB_Glass": ((0.01, 0.015, 0.02), 0.06, 0.6),
    "M_CWB_GlassBlue": ((0.01, 0.03, 0.08), 0.08, 0.5), "M_CWB_Canvas": ((0.01, 0.04, 0.14), 0.85, 0.0),
    "M_CWB_Sail": ((0.85, 0.83, 0.77), 0.8, 0.0), "M_CWB_Spar": ((0.55, 0.57, 0.6), 0.3, 0.8),
    "M_CWB_WoodSpar": ((0.27, 0.13, 0.04), 0.55, 0.0), "M_CWB_Steel": ((0.6, 0.62, 0.64), 0.25, 0.9),
    "M_CWB_Seat": ((0.01, 0.05, 0.3), 0.6, 0.0), "M_CWB_Rope": ((0.03, 0.02, 0.01), 0.9, 0.0),
    "M_CWB_Orange": ((0.85, 0.12, 0.005), 0.6, 0.0), "M_CWB_Thatch": ((0.24, 0.14, 0.04), 0.95, 0.0),
    "M_CWB_Light": ((1.0, 0.9, 0.65), 0.4, 0.0, 4.0),
}
STATIC_SLOTS = {
    "M_CW_LockConcrete": ((0.42, 0.41, 0.38), 0.85), "M_CW_WallDark": ((0.05, 0.055, 0.05), 0.9),
    "M_CW_GateSteel": ((0.09, 0.11, 0.13), 0.45, 0.6), "M_CW_SafetyYellow": ((0.9, 0.5, 0.01), 0.6),
    "M_CW_Fender": ((0.01, 0.01, 0.01), 0.8), "M_CW_DockDeck": ((0.22, 0.19, 0.15), 0.85),
    "M_CW_Float": ((0.6, 0.6, 0.57), 0.7), "M_CW_Piling": ((0.05, 0.055, 0.06), 0.6, 0.5),
    "M_CW_Riprap": ((0.1, 0.095, 0.085), 0.95), "M_CW_Buoy": ((0.85, 0.85, 0.82), 0.5),
    "M_CW_WhiteWall": ((0.72, 0.72, 0.69), 0.7), "M_CW_SignalRed": ((0.9, 0.01, 0.005), 0.4, 0.0, 6.0),
    "M_CW_SignalGreen": ((0.01, 0.75, 0.06), 0.4, 0.0, 6.0), "M_CW_ShipBlack": ((0.012, 0.012, 0.014), 0.35),
    "M_CW_ShipWhite": ((0.75, 0.75, 0.73), 0.4), "M_CW_ShipRed": ((0.14, 0.015, 0.012), 0.5),
}
# slots that already exist as the landmarks' instances (place_landmarks_ue.py) -> fallback tint if they don't
LM_SLOTS = {"M_Railing": ((0.08, 0.08, 0.08), 0.5, 0.6), "M_Light": ((1.0, 0.93, 0.8), 0.3, 0.0, 6.0),
            "M_Glass": ((0.06, 0.08, 0.10), 0.08, 0.4), "M_GlassDark": ((0.03, 0.04, 0.05), 0.06, 0.5),
            "M_RoofFlat": ((0.30, 0.30, 0.30), 0.8), "M_Hedge": ((0.06, 0.16, 0.05), 0.9), "M_Steel": ((0.40, 0.41, 0.42), 0.4, 0.8),
            "M_DeckPaving": ((0.62, 0.58, 0.53), 0.8), "M_Timber": ((0.28, 0.19, 0.11), 0.85)}
PROP = "/Game/City/Street/Materials/M_StreetProp"


def mi(name, parent, tint, rough, metal=0.0, glow=0.0, extra=None):
    path = f"{DIR}/Materials/{name}"
    m = EAL.load_asset(path) if EAL.does_asset_exist(path) else AT.create_asset(name, f"{DIR}/Materials", unreal.MaterialInstanceConstant,
                                                                                unreal.MaterialInstanceConstantFactoryNew())
    m.set_editor_property("parent", parent)
    MEL.set_material_instance_vector_parameter_value(m, "Tint", unreal.LinearColor(*tint, 1))
    MEL.set_material_instance_scalar_parameter_value(m, "Roughness", rough)
    MEL.set_material_instance_scalar_parameter_value(m, "Metallic", metal)
    MEL.set_material_instance_vector_parameter_value(m, "EmissiveColor", unreal.LinearColor(*tint, 1))
    MEL.set_material_instance_scalar_parameter_value(m, "EmissiveStrength", glow)
    for k, v in (extra or {}).items():
        MEL.set_material_instance_scalar_parameter_value(m, k, v)
    MEL.update_material_instance(m)
    return m


def boat_master():
    """M_CW_BoatBob: opaque, Tint / Roughness / Metallic / EmissiveColor x EmissiveStrength like M_StreetProp, plus a
    world-position offset that rocks the whole boat as a rigid body: heave (HeaveAmp cm) and small roll / pitch
    (RollAmp / PitchAmp radians) about its own axes, periods 3.1 / 4.6 / 3.7 s, phase from PerInstanceRandom and the
    object position so neighbours don't bob in step."""
    path = f"{DIR}/Materials/M_CW_BoatBob"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
    else:
        m = AT.create_asset("M_CW_BoatBob", f"{DIR}/Materials", unreal.Material, unreal.MaterialFactoryNew())
    for flag in ("used_with_instanced_static_meshes",):
        try:
            m.set_editor_property(flag, True)
        except Exception:
            pass
    E = lambda cls, x, y: MEL.create_material_expression(m, cls, x, y)
    C = MEL.connect_material_expressions

    def sp(name, v, x, y):
        e = E(unreal.MaterialExpressionScalarParameter, x, y)
        e.set_editor_property("parameter_name", name)
        e.set_editor_property("default_value", v)
        return e

    def vp(name, v, x, y):
        e = E(unreal.MaterialExpressionVectorParameter, x, y)
        e.set_editor_property("parameter_name", name)
        e.set_editor_property("default_value", unreal.LinearColor(*v, 1))
        return e
    tint = vp("Tint", (0.8, 0.8, 0.8), -800, -400)
    MEL.connect_material_property(tint, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(sp("Roughness", 0.4, -800, -250), "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(sp("Metallic", 0.0, -800, -180), "", unreal.MaterialProperty.MP_METALLIC)
    em = E(unreal.MaterialExpressionMultiply, -600, -100)
    C(vp("EmissiveColor", (1, 1, 1), -800, -120), "", em, "A")
    C(sp("EmissiveStrength", 0.0, -800, -40), "", em, "B")
    MEL.connect_material_property(em, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    wpo = "none"
    try:
        tm = E(unreal.MaterialExpressionTime, -1600, 200)
        pr = E(unreal.MaterialExpressionPerInstanceRandom, -1600, 300)
        op = E(unreal.MaterialExpressionObjectPositionWS, -1600, 400)
        dk = E(unreal.MaterialExpressionConstant3Vector, -1600, 480)
        dk.set_editor_property("constant", unreal.LinearColor(0.00031, 0.00047, 0.0, 1))
        dot = E(unreal.MaterialExpressionDotProduct, -1450, 420)
        C(op, "", dot, "A")
        C(dk, "", dot, "B")
        ph10 = E(unreal.MaterialExpressionMultiply, -1450, 300)
        C(pr, "", ph10, "A")
        k10 = E(unreal.MaterialExpressionConstant, -1600, 340)
        k10.set_editor_property("r", 7.3)
        C(k10, "", ph10, "B")
        ph = E(unreal.MaterialExpressionAdd, -1300, 350)
        C(ph10, "", ph, "A")
        C(dot, "", ph, "B")

        def wave(period, mult, y):
            d = E(unreal.MaterialExpressionDivide, -1300, y)
            C(tm, "", d, "A")
            kp = E(unreal.MaterialExpressionConstant, -1450, y)
            kp.set_editor_property("r", period)
            C(kp, "", d, "B")
            pm = E(unreal.MaterialExpressionMultiply, -1300, y + 60)
            C(ph, "", pm, "A")
            km = E(unreal.MaterialExpressionConstant, -1450, y + 60)
            km.set_editor_property("r", mult)
            C(km, "", pm, "B")
            a = E(unreal.MaterialExpressionAdd, -1150, y)
            C(d, "", a, "A")
            C(pm, "", a, "B")
            s = E(unreal.MaterialExpressionSine, -1000, y)
            s.set_editor_property("period", 1.0)
            C(a, "", s, "")
            return s
        roll = E(unreal.MaterialExpressionMultiply, -850, 600)
        C(wave(4.6, 1.0, 600), "", roll, "A")
        C(sp("RollAmp", 0.018, -1000, 680), "", roll, "B")
        pitch = E(unreal.MaterialExpressionMultiply, -850, 800)
        C(wave(3.7, 1.3, 800), "", pitch, "A")
        C(sp("PitchAmp", 0.008, -1000, 880), "", pitch, "B")
        heave = E(unreal.MaterialExpressionMultiply, -850, 1000)
        C(wave(3.1, 0.7, 1000), "", heave, "A")
        C(sp("HeaveAmp", 6.0, -1000, 1080), "", heave, "B")
        ap = E(unreal.MaterialExpressionAppendVector, -700, 700)
        C(roll, "", ap, "A")
        C(pitch, "", ap, "B")
        z0 = E(unreal.MaterialExpressionConstant, -850, 900)
        z0.set_editor_property("r", 0.0)
        om = E(unreal.MaterialExpressionAppendVector, -560, 750)
        C(ap, "", om, "A")
        C(z0, "", om, "B")
        lp = E(unreal.MaterialExpressionLocalPosition, -700, 850)
        cr = E(unreal.MaterialExpressionCrossProduct, -420, 780)
        C(om, "", cr, "A")
        C(lp, "", cr, "B")
        tr = E(unreal.MaterialExpressionTransform, -280, 780)
        tr.set_editor_property("transform_source_type", unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL)
        tr.set_editor_property("transform_type", unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
        C(cr, "", tr, "")
        hz0 = E(unreal.MaterialExpressionConstant2Vector, -700, 1050)
        hz0.set_editor_property("r", 0.0)
        hz0.set_editor_property("g", 0.0)
        hz = E(unreal.MaterialExpressionAppendVector, -560, 1050)
        C(hz0, "", hz, "A")
        C(heave, "", hz, "B")
        tot = E(unreal.MaterialExpressionAdd, -140, 900)
        C(tr, "", tot, "A")
        C(hz, "", tot, "B")
        MEL.connect_material_property(tot, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
        wpo = "ok"
    except Exception:
        wpo = traceback.format_exc()[-600:]
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m, wpo


def slot_materials():
    S = {}
    prop = EAL.load_asset(PROP)
    try:
        bob, wpo = boat_master()
    except Exception:
        bob, wpo = prop, traceback.format_exc()[-400:]
    out["boat_master_wpo"] = wpo
    for slot, v in BOAT_SLOTS.items():
        extra = {"HeaveAmp": 3.0, "RollAmp": 0.006, "PitchAmp": 0.003} if False else None
        S[slot] = mi("MI_CWB_" + slot[6:], bob, v[0], v[1], v[2], v[3] if len(v) > 3 else 0.0, extra)
    for slot, v in STATIC_SLOTS.items():
        S[slot] = mi("MI_CW_" + slot[5:], prop, v[0], v[1], v[2] if len(v) > 2 else 0.0, v[3] if len(v) > 3 else 0.0)
    for slot, v in LM_SLOTS.items():
        p = f"{LMDIR}/MI_LM_{slot[2:]}"
        S[slot] = EAL.load_asset(p) if EAL.does_asset_exist(p) else mi("MI_CW_" + slot[2:], prop, v[0], v[1], v[2] if len(v) > 2 else 0.0,
                                                                         v[3] if len(v) > 3 else 0.0)
    return S


def existing_materials():
    S = {}
    for slot in BOAT_SLOTS:
        p = f"{DIR}/Materials/MI_CWB_{slot[6:]}"
        if EAL.does_asset_exist(p):
            S[slot] = EAL.load_asset(p)
    for slot in STATIC_SLOTS:
        p = f"{DIR}/Materials/MI_CW_{slot[5:]}"
        if EAL.does_asset_exist(p):
            S[slot] = EAL.load_asset(p)
    for slot in LM_SLOTS:
        for p in (f"{LMDIR}/MI_LM_{slot[2:]}", f"{DIR}/Materials/MI_CW_{slot[2:]}"):
            if EAL.does_asset_exist(p):
                S[slot] = EAL.load_asset(p)
                break
    return S


def assign(S):
    n, missing = 0, set()
    for name in (ONLY or ALL):
        sm = mesh(name)
        if not sm:
            continue
        for i, sml in enumerate(sm.get_editor_property("static_materials")):
            base = str(sml.get_editor_property("material_slot_name")).split(".")[0]
            if base in S:
                sm.set_material(i, S[base])
                n += 1
            else:
                missing.add(base)
    EAL.save_directory(DIR, only_if_is_dirty=True, recursive=True)
    return {"assigned": n, "unmapped": sorted(missing)}


def stage_materials():
    log("materials", assign(slot_materials()))


def stage_assign():
    log("assign", assign(existing_materials()))


# ------------------------------------------------------------------ place
def add_component(actor, cls):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    BFL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=cls, blueprint_context=None)
    h, fail = sds.add_new_subobject(params)
    return BFL.get_object(BFL.get_data(h))


def tag(a, label):
    a.set_actor_label(label)
    a.set_folder_path(FOLDER)
    a.tags = [TAG, "City_Generated"]
    a.set_editor_property("is_spatially_loaded", False)


def spawn(name, label, loc, yaw=0.0, scale=1.0, collide=True):
    sm = mesh(name)
    if not sm:
        out.setdefault("missing", []).append(name)
        return None
    a = EAS.spawn_actor_from_object(sm, loc, unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    tag(a, label)
    if scale != 1.0:
        a.set_actor_scale3d(unreal.Vector(scale, scale, scale))
    a.static_mesh_component.set_collision_profile_name("BlockAll" if collide else "NoCollision")
    return a


def hism(label, name, items, cull=(0.0, 0.0), collide=True):
    """One actor with a HISM of `name`; items = [(plan x, plan y, z cm, heading deg, scale)]."""
    sm = mesh(name)
    if not sm or not items:
        return 0
    act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    tag(act, label)
    c = add_component(act, unreal.HierarchicalInstancedStaticMeshComponent)
    c.set_static_mesh(sm)
    c.set_collision_profile_name("BlockAll" if collide else "NoCollision")
    if cull[1] > 0:
        try:
            c.set_cull_distances(cull[0], cull[1])
        except Exception:
            pass
    T = [unreal.Transform(U(x, y, z), unreal.Rotator(roll=0, pitch=0, yaw=yaw_of(h)), unreal.Vector(s, s, s)) for x, y, z, h, s in items]
    c.add_instances(T, False, True)
    return len(T)


BASE_LEN = {"CW_Sloop": 9.78, "CW_SloopNavy": 9.78, "CW_SloopSailing": 9.78, "CW_MotorYacht": 16.35}


def stage_place():
    gone = 0
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags]:
            EAS.destroy_actor(a)
            gone += 1
    placed = {"removed": gone}
    # --- sites (plan frame, no rotation, ground z 0)
    lo = LAY["lock_origin"]
    spawn("CW_ChicagoLock", "CW_ChicagoLock", U(lo[0], lo[1], 0.0))
    for k, g in enumerate(LAY["lock_gates"]):
        spawn("CW_LockGate" + g["kind"], f"CW_LockGate_{k}_{g['gate'].split()[0]}", U(g["pivot"][0], g["pivot"][1], 0.0), yaw=-g["open_deg"])
    for area in ("dusable", "navypier_marina", "monroe", "lock", "river"):
        o = LAY["origin_" + area]
        spawn("CW_Docks_" + "".join(w.capitalize() for w in area.split("_")), "CW_Docks_" + area, U(o[0], o[1], 0.0))
    o = LAY["origin_dime"]
    spawn("CW_DimePier", "CW_DimePier", U(o[0], o[1], 0.0))
    o = LAY["origin_riverwalls"]
    spawn("CW_RiverWalls", "CW_RiverWalls", U(o[0], o[1], 0.0))
    o = LAY["origin_riverwalk"]
    spawn("CW_Riverwalk", "CW_Riverwalk", U(o[0], o[1], 0.0))
    for nm in ("CW_YachtClubMonroe", "CW_MarinaBoathouse"):
        o = LAY["origin_" + nm]
        spawn(nm, nm, U(o[0], o[1], 0.0))
    ab = LAY["abegweit"]
    spawn("CW_Abegweit", "CW_Abegweit_ColumbiaYachtClub", U(ab["x"], ab["y"], WATER_CM), yaw=yaw_of(ab["h"]))
    for nl in LAY["nav_lights"]:
        spawn(nl["type"], "CW_" + nl["name"].replace(" ", "_"), U(nl["x"], nl["y"], nl["z"] * 100.0))
    # --- boats (instanced per harbour and type)
    groups = {}

    def add(group, kind, x, y, h, s):
        groups.setdefault((group, kind), []).append((x, y, WATER_CM, h, s))
    for area in ("dusable", "navypier_marina", "monroe"):
        for b in LAY.get("slots_" + area, []):
            s = b["len"] / BASE_LEN.get(b["type"], 10.0)
            add(area, b["type"], b["x"], b["y"], b["h"], round(max(0.55, min(s, 2.2)), 3))
    buoys = []
    for b in LAY["monroe_moorings"]:
        buoys.append((b["buoy"][0], b["buoy"][1], WATER_CM, 0.0, 1.0))
        if not b["empty"]:
            add("monroe_field", b["type"], b["x"], b["y"], b["h"], round(b["len"] / BASE_LEN.get(b["type"], 10.0), 3))
    for b in LAY["navypier_ships"] + LAY["lock_boats"] + LAY["underway"] + LAY["river_berths"]:
        add("ships", b["type"], b["x"], b["y"], b["h"], b.get("scale", 1.0))
    for b in LAY["kayaks"]:
        add("kayaks", "CW_Kayak", b["x"], b["y"], b["h"], 1.0)
    for b in LAY["river_berths"]:
        if b["type"] == "CW_TikiBoat":                                         # a second tiki boat at each tiki berth
            add("ships", "CW_TikiBoat", b["x"] + b["t"][0] * 7.0, b["y"] + b["t"][1] * 7.0, b["h"] + 40.0, 1.0)
    counts = {}
    for (group, kind), items in sorted(groups.items()):
        big = kind in ("CW_CruiseShip", "CW_TallShip", "CW_TallShipSailing", "CW_TourBoat")
        cull = (0.0, 0.0) if big else ((0.0, 60000.0) if kind == "CW_Kayak" else (0.0, 250000.0))
        counts[f"{group}/{kind}"] = hism(f"CW_Boats_{group}_{kind[3:]}", kind, items, cull, collide=kind not in NO_COLLISION)
    counts["buoys"] = hism("CW_MooringBuoys_Monroe", "CW_MooringBuoy", buoys, (0.0, 80000.0), collide=False)
    placed["boats"] = counts
    placed["trees"] = city_trees("CW_LockTrees", LAY["lock_trees"], 6.0 + 62.0, 0.8, 1.0)
    placed["riverwalk_trees"] = city_trees("CW_RiverwalkTrees", LAY["riverwalk_trees"], 5.0 + 58.0, 0.85, 1.1)
    log("place", placed)


def city_trees(label, pts, z, s0, s1):
    """Honey locusts in the planters (lock's south walls, Riverwalk): the city's tree mesh and settings, as the
    landmarks' LM_PierTrees."""
    srca = next((a for a in EAS.get_all_level_actors() if a.get_actor_label() == "RProps_honeylocust"), None)
    cs = srca.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent) if srca else []
    if not cs:
        return "no RProps_honeylocust"
    src = cs[0]
    act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    tag(act, label)
    act.tags = [TAG, "City_Generated", "NoWallRide"]
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
    rnd = random.Random(5)
    T = []
    for x, y in pts:
        sc = rnd.uniform(s0, s1)
        T.append(unreal.Transform(U(x, y, z), unreal.Rotator(0, 0, rnd.uniform(0, 360)), unreal.Vector(sc, sc, sc)))
    if ncd:
        c.set_editor_property("num_custom_data_floats", ncd)
    c.add_instances(T, False, True)
    for i in range(len(T)):
        for k, v in enumerate(cd):
            c.set_custom_data_value(i, k, float(v), False)
    return len(T)


# ------------------------------------------------------------------ clear
def inside(poly, x, y):
    c = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def intruders(acts, polys, dry=True):
    """Instances of street props / trees (RProps_*) and City Sample pieces (CS_*) inside the given plan polygons."""
    boxes = []
    for p in polys:
        xs = [q[0] for q in p]
        ys = [q[1] for q in p]
        boxes.append((min(xs), max(xs), min(ys), max(ys), p))
    res = {}
    for a in acts:
        lab = a.get_actor_label()
        if not lab.startswith(("RProps_", "CS_")):
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            n = c.get_instance_count()
            if not n:
                continue
            o, e, _r = unreal.SystemLibrary.get_component_bounds(c)
            if not any(o.x + e.x >= b[2] * 100 and o.x - e.x <= b[3] * 100 and o.y + e.y >= b[0] * 100 and o.y - e.y <= b[1] * 100 for b in boxes):
                continue
            kill = []
            for i in range(n):
                p = c.get_instance_transform(i, True).translation
                px, py = p.y / 100.0, p.x / 100.0
                if any(b[0] <= px <= b[1] and b[2] <= py <= b[3] and inside(b[4], px, py) for b in boxes):
                    kill.append(i)
            if kill:
                res[lab + "|" + c.get_name()] = len(kill)
                if not dry:
                    a.modify()
                    c.modify()
                    c.remove_instances(kill)
    return res


def stage_clear():
    polys = list(LAY["lock_outlines"].values()) + [LAY["abegweit"]["island"]] + LAY.get("riverwalk_zone", [])
    log("clear", intruders(EAS.get_all_level_actors(), polys, dry=False))


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
        t = time.time()
        fn()
        log("stage_" + name, round(time.time() - t, 1))
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        log("error", traceback.format_exc())
    finally:
        BUSY[0] = False


_h = unreal.register_slate_post_tick_callback(tick)
