"""Skyster pickups for the loaded map (Sky City or McGregor): pressure points, Supercharger sites and the fuel add-ons,
as tagged instanced meshes the C++ car finds at BeginPlay (Source/SkyCity/SkysterPickups.h). Also removes the old
boost-ring course (Kenny: "remove the rings in the air, we don't need those yet").

  import     SourceArt/Pickups/*.glb (blender_pickups_kit.py) and the two textures -> /Game/SkyCity/Pickups
  materials  M_SkyEmissive (unlit glow), M_SkyGlow (additive glow pool), M_SkyChargerBay (glass + markings that turn
             from red to green per instance while a car charges), and the instances on the kit's slots
  place      Skyster's spacing: small pressure points every 90 m along the main roads (>= 40 m apart), 12 big ones far
             apart, Supercharger rows (3 bays, 6.5 m pitch) about every 450 m just past the kerb where it's clear, and the
             add-ons (nitrogen at street level, Raptor tech on a mid-height roof, rocket fuel on the tallest / hardest spot)
  rings      delete the BP_BoostRing actors
  rig        Kenny's rigged Roadster parts (SourceArt/RoadsterRig, blender_roadster_rig.py) -> /Game/Vehicles/RoadsterRig,
             the plume material M_SkyJet / MI_Jet (additive, fading toward the tip) and the lamp glow MI_CarLight
  save
Run in the editor with the map loaded: py Scripts/unreal/pickups_ue.py [stage ...]
Writes Saved/MCPScripts/out_pickups.json.
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
OUT = ROOT + "/Saved/MCPScripts/out_pickups.json"
DIR = "/Game/SkyCity/Pickups"
TAG = "SC_Pickups"
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
STAGES = sys.argv[1:] or ["import", "materials", "place", "rings", "save"]
out = {"stages": STAGES}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def map_name():
    return world().get_path_name().split(".")[0].split("/")[-1]


def U(x, y, z=0.0):
    """Plan metres (x east, y north) -> Unreal cm (X north, Y east)."""
    return unreal.Vector(y * 100.0, x * 100.0, z * 100.0)


def yaw_of(dx, dy):
    """Unreal yaw (deg) of a plan direction."""
    return math.degrees(math.atan2(dx, dy))


# ------------------------------------------------------------------ assets
def import_files(files, dest):
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", dest)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", False)
        tasks.append(t)
    AT.import_asset_tasks(tasks)
    res = []
    for t in tasks:
        res += list(t.get_editor_property("imported_object_paths") or [])
    return res


def stage_import():
    meshes = import_files(sorted(glob.glob(ROOT + "/SourceArt/Pickups/*.glb")), f"{DIR}/Kit")
    tex = import_files(sorted(glob.glob(ROOT + "/SourceArt/Pickups/textures/*.png")), f"{DIR}/Textures")
    for p in tex:
        t = EAL.load_asset(p)
        t.set_editor_property("srgb", False)
        t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
    log("import", {"meshes": len(meshes), "textures": len(tex)})


def kit(name):
    for p in EAL.list_assets(f"{DIR}/Kit", recursive=True):
        if p.split("/")[-1].split(".")[0] == name and EAL.find_asset_data(p).asset_class_path.asset_name == "StaticMesh":
            return EAL.load_asset(p.split(".")[0])
    return None


def new_material(name):
    path = f"{DIR}/Materials/{name}"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
        return m
    return AT.create_asset(name, f"{DIR}/Materials", unreal.Material, unreal.MaterialFactoryNew())


def mi(name, parent, scalars=None, vectors=None, textures=None):
    path = f"{DIR}/Materials/{name}"
    m = EAL.load_asset(path) if EAL.does_asset_exist(path) else AT.create_asset(name, f"{DIR}/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.clear_all_material_instance_parameters(m)
    m.set_editor_property("parent", parent)
    for k, v in (scalars or {}).items():
        MEL.set_material_instance_scalar_parameter_value(m, k, v)
    for k, v in (vectors or {}).items():
        MEL.set_material_instance_vector_parameter_value(m, k, unreal.LinearColor(*v, 1))
    for k, v in (textures or {}).items():
        MEL.set_material_instance_texture_parameter_value(m, k, v)
    MEL.update_material_instance(m)
    return m


def stage_materials():
    def X(m, cls, x, y):
        return MEL.create_material_expression(m, cls, x, y)

    def param(m, cls, name, x, y, v):
        e = X(m, cls, x, y)
        e.set_editor_property("parameter_name", name)
        e.set_editor_property("default_value", v)
        return e
    tex_glow = EAL.load_asset(f"{DIR}/Textures/T_GlowSpot")
    tex_marks = EAL.load_asset(f"{DIR}/Textures/T_ChargerMarks")
    # unlit glow: Color x Strength
    em = new_material("M_SkyEmissive")
    em.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mul = X(em, unreal.MaterialExpressionMultiply, -300, 0)
    MEL.connect_material_expressions(param(em, unreal.MaterialExpressionVectorParameter, "Color", -600, -100, unreal.LinearColor(1, 1, 1, 1)), "", mul, "A")
    MEL.connect_material_expressions(param(em, unreal.MaterialExpressionScalarParameter, "Strength", -600, 100, 4.0), "", mul, "B")
    MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(em)
    # additive glow pool: the radial spot texture x Color x Strength
    gl = new_material("M_SkyGlow")
    gl.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    gl.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    gl.set_editor_property("two_sided", True)
    t = X(gl, unreal.MaterialExpressionTextureSampleParameter2D, -700, 0)
    t.set_editor_property("parameter_name", "Spot")
    t.set_editor_property("texture", tex_glow)
    t.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    m1 = X(gl, unreal.MaterialExpressionMultiply, -400, 0)
    MEL.connect_material_expressions(t, "R", m1, "A")
    MEL.connect_material_expressions(param(gl, unreal.MaterialExpressionVectorParameter, "Color", -700, 250, unreal.LinearColor(0.6, 1.1, 1.6, 1)), "", m1, "B")
    m2 = X(gl, unreal.MaterialExpressionMultiply, -200, 0)
    MEL.connect_material_expressions(m1, "", m2, "A")
    MEL.connect_material_expressions(param(gl, unreal.MaterialExpressionScalarParameter, "Strength", -400, 250, 0.6), "", m2, "B")
    MEL.connect_material_property(m2, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(gl)
    # Supercharger bay: dark glass; the markings glow red, or pulse green while a car charges (per-instance data 0)
    bay = new_material("M_SkyChargerBay")
    MEL.connect_material_property(param(bay, unreal.MaterialExpressionVectorParameter, "Base", -500, -300, unreal.LinearColor(0.015, 0.017, 0.02, 1)), "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(param(bay, unreal.MaterialExpressionScalarParameter, "Metallic", -500, -200, 0.5), "", unreal.MaterialProperty.MP_METALLIC)
    MEL.connect_material_property(param(bay, unreal.MaterialExpressionScalarParameter, "Roughness", -500, -120, 0.22), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mk = X(bay, unreal.MaterialExpressionTextureSampleParameter2D, -900, 100)
    mk.set_editor_property("parameter_name", "Marks")
    mk.set_editor_property("texture", tex_marks)
    mk.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    busy = X(bay, unreal.MaterialExpressionPerInstanceCustomData, -900, 400)
    busy.set_editor_property("data_index", 0)
    lp = X(bay, unreal.MaterialExpressionLinearInterpolate, -600, 300)
    MEL.connect_material_expressions(param(bay, unreal.MaterialExpressionVectorParameter, "Free", -900, 250, unreal.LinearColor(2.2, 0.22, 0.18, 1)), "", lp, "A")
    MEL.connect_material_expressions(param(bay, unreal.MaterialExpressionVectorParameter, "Charging", -900, 330, unreal.LinearColor(0.4, 2.6, 0.8, 1)), "", lp, "B")
    MEL.connect_material_expressions(busy, "", lp, "Alpha")
    e1 = X(bay, unreal.MaterialExpressionMultiply, -400, 150)
    MEL.connect_material_expressions(mk, "R", e1, "A")
    MEL.connect_material_expressions(lp, "", e1, "B")
    e2 = X(bay, unreal.MaterialExpressionMultiply, -250, 150)
    MEL.connect_material_expressions(e1, "", e2, "A")
    MEL.connect_material_expressions(param(bay, unreal.MaterialExpressionScalarParameter, "Strength", -400, 300, 2.0), "", e2, "B")
    MEL.connect_material_property(e2, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(bay)
    prop = EAL.load_asset("/Game/City/Street/Materials/M_StreetProp")
    mats = {
        "M_PadGold": mi("MI_PadGold", prop, {"Metallic": 1.0, "Roughness": 0.25}, {"Tint": (0.79, 0.64, 0.40)}),
        "M_PadCore": mi("MI_PadCore", em, {"Strength": 5.0}, {"Color": (0.42, 0.72, 1.0)}),
        "M_PadPool": mi("MI_PadPool", gl, {"Strength": 0.6}, {"Color": (0.6, 1.1, 1.6)}),
        "M_ChargerBay": mi("MI_ChargerBay", bay),
        "M_ChargerCross": mi("MI_ChargerCross", em, {"Strength": 6.0}, {"Color": (0.2, 1.0, 0.35)}),
        "M_SC_Addon_nitrogen_Glow": mi("MI_AddonGlow_N2", em, {"Strength": 6.0}, {"Color": (0.45, 1.0, 1.0)}),
        "M_SC_Addon_combustion_Glow": mi("MI_AddonGlow_Raptor", em, {"Strength": 6.0}, {"Color": (1.0, 0.4, 0.08)}),
        "M_SC_Addon_rocket_Glow": mi("MI_AddonGlow_Rocket", em, {"Strength": 6.0}, {"Color": (1.0, 0.75, 0.4)}),
    }
    done = []
    for p in EAL.list_assets(f"{DIR}/Kit", recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name != "StaticMesh":
            continue
        sm = EAL.load_asset(p.split(".")[0])
        for i, s in enumerate(sm.get_editor_property("static_materials")):
            slot = str(s.get_editor_property("material_slot_name"))
            if slot in mats:
                sm.set_material(i, mats[slot])
                done.append(f"{sm.get_name()}:{slot}")
        EAL.save_loaded_asset(sm)
    for m in [em, gl, bay] + list(mats.values()):
        EAL.save_loaded_asset(m)
    log("materials", done)


# ------------------------------------------------------------------ world queries
def hits_at(x, y, top=300.0, bottom=-30.0):
    """All hits straight down at plan (x, y), top first: [(z_m, label)]."""
    # a multi-trace stops at the first blocking hit, so step down past each hit instead
    out_, z = [], top
    for _ in range(8):
        h = unreal.SystemLibrary.line_trace_single(world(), U(x, y, z), U(x, y, bottom), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [],
                                                   unreal.DrawDebugTrace.NONE, True)
        if not h:
            break
        t = h.to_tuple()
        if not t[0]:
            break
        loc, actor = t[4], t[9]
        out_.append((loc.z / 100.0, actor.get_actor_label() if actor else ""))
        z = loc.z / 100.0 - 0.05
        if z <= bottom:
            break
    return out_


ROADISH = ("Ground", "Blocks_", "BridgeDeck", "Overlay_", "Paint_", "Roads", "Pad_", "Elevated", "Expressway", "Deck", "Terrain_", "Street")
UNDER = ("WaterSurface", "Riverbed", "Lake", "Water")


def road_z(x, y, elevated=False):
    """Height of the road surface at (x, y): the top hit on a road-ish actor (so an L track or a sign overhead
    doesn't count); else the lowest hit."""
    hs = [h for h in hits_at(x, y) if not h[1].startswith("SC_") and not h[1].startswith(UNDER)]
    if not hs:
        return None
    road = [h for h in hs if h[1].startswith(ROADISH)]
    if road:
        return road[0][0] if not elevated else max(h[0] for h in road)
    return hs[-1][0]


def clear_spot(x, y, z, r=1.2):
    """Nothing standing at (x, y) above a surface near z (no building, pole or sign)."""
    hs = [h for h in hits_at(x, y, z + 25, z - 3) if not h[1].startswith("SC_")]
    return bool(hs) and abs(hs[0][0] - z) < 0.6


# ------------------------------------------------------------------ layouts
def resample(pts, step, offset):
    """Points every `step` m along a polyline (starting `offset` in), with their headings."""
    outp, carry = [], offset
    for a, b in zip(pts, pts[1:]):
        seg = math.dist(a, b)
        if seg < 1e-6:
            continue
        d = carry
        while d <= seg:
            t = d / seg
            outp.append(((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), (b[0] - a[0]) / seg, (b[1] - a[1]) / seg))
            d += step
        carry = d - seg
    return outp


def roads_for_map():
    """[(pts, width, elevated)] of the roads that get pressure points, plus add-on and big-pad hints."""
    name = map_name()
    if name.startswith("McGregor"):                           # the day map and McGregorNight
        D = json.load(open(ROOT + "/Saved/McGregor/mcgregor_data.json"))
        # pressure points on every drivable road; Superchargers only along the paved ones (it's farmland)
        roads = [(r["pts"], r["w"], False, r["surface"] == "asphalt") for r in D["roads"] if r["kind"] not in ("track", "footway", "path") and r["surface"] != "dirt"]
        L = json.load(open(ROOT + "/Saved/McGregor/demo_layout.json"))
        lot = L["lot"]
        cx, cy = sum(p[0] for p in lot) / 4, sum(p[1] for p in lot) / 4
        ramp = L["ramp"]["p"]
        ry = math.radians(L["ramp"]["yaw"])
        tx, ty = math.sin(ry), math.cos(ry)                       # travel direction (plan)
        lip = (ramp[0] - tx * 8.2, ramp[1] - ty * 8.2)            # the lip overhangs ~8 m back over the approach
        wb = L.get("white_building", {}).get("p")
        st = L["start"]["p"]
        hints = {
            "big": [(cx, cy), (0.0, 0.0), (st[0], st[1])],
            "addons": [("nitrogen", (cx + 25, cy - 10), "street"),
                       ("combustion", tuple(wb) if wb else (cx - 120, cy - 120), "roof"),
                       ("rocket", lip, "air36")],
            "chargers": [((st[0] - ty * 22, st[1] + tx * 22), (tx, ty))],      # in the lot, beside the start
        }
        return roads, hints
    D = json.load(open(ROOT + "/Saved/Streets/street_data.json"))
    roads = [(r["pts"], r.get("width", 8.0), bool(r.get("elevated")), not r.get("elevated")) for r in D["roads"] if r["cls"] in ("major", "mid", "highway") and not r.get("skip")]
    P = json.load(open(ROOT + "/Saved/Mashup/plan_v3.json"))
    lm = {l["name"]: l["pos"] for l in P["landmarks"]}
    hints = {
        "big": [],
        "addons": [("nitrogen", tuple(lm.get("The Bean", (373, -537))), "street"),
                   ("nitrogen", tuple(lm.get("Auditorium Shores", (-771.6, 438.9))), "street"),
                   ("combustion", tuple(lm.get("Wrigley Building", (257, 181))), "roof"),
                   ("combustion", tuple(lm.get("Texas State Capitol", (-1465.3, -1143.6))), "roof"),
                   ("rocket", tuple(lm.get("Willis Tower", (-679, -979))), "roof"),
                   ("rocket", None, "tallest_austin")],
        "chargers": [],
        "play": P["playArea"],
    }
    return roads, hints


def stage_place():
    t0 = time.time()
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags]:
            EAS.destroy_actor(a)
    roads, hints = roads_for_map()
    # --- pressure points: every 90 m along the roads, >= 40 m apart
    cand = []
    grid = {}

    def near(p, r):
        gx, gy = int(p[0] // 50), int(p[1] // 50)
        for i in range(gx - 1, gx + 2):
            for j in range(gy - 1, gy + 2):
                for q in grid.get((i, j), []):
                    if math.dist(p, q) < r:
                        return True
        return False
    for pts, w, elev, _ in roads:
        for p, dx, dy in resample(pts, 90.0, 45.0):
            if near(p, 40.0):
                continue
            grid.setdefault((int(p[0] // 50), int(p[1] // 50)), []).append(p)
            cand.append((p, dx, dy, w, elev))
    # big ones: the hinted spots, then far-apart picks across the map (farthest-point sampling) up to 12
    bigs = [h for h in hints["big"]]
    pool = [c[0] for c in cand]
    while len(bigs) < 12 and pool:
        best, bd = None, -1
        for p in pool[::7]:
            d = min((math.dist(p, b) for b in bigs), default=1e9)
            if d > bd:
                best, bd = p, d
        if best is None or bd < 100:
            break
        bigs.append(best)
    small = [c for c in cand if all(math.dist(c[0], b) > 25 for b in bigs)]

    def place_set(label, tag, items, ring, core, poolm, ring_shadow):
        act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        act.set_actor_label(label)
        act.set_folder_path("Skyster/Pickups")
        act.tags = [TAG, tag, "NoWallRide"]
        comps = {}
        for ctag, mesh in (("Pool", poolm), ("Ring", ring), ("Core", core)):
            c = add_component(act, unreal.InstancedStaticMeshComponent)
            c.set_static_mesh(mesh)
            c.set_mobility(unreal.ComponentMobility.MOVABLE)
            c.set_collision_profile_name("NoCollision")
            c.set_editor_property("cast_shadow", ctag == "Ring" and ring_shadow)
            c.component_tags = [ctag]
            c.set_cull_distances(30000, 40000)
            comps[ctag] = c
        xp, xr = [], []
        for (x, y, z, yaw) in items:
            xp.append(unreal.Transform(U(x, y, z), unreal.Rotator(roll=0, pitch=0, yaw=yaw), unreal.Vector(1, 1, 1)))
            xr.append(unreal.Transform(U(x, y, z + 0.75), unreal.Rotator(roll=0, pitch=0, yaw=yaw), unreal.Vector(1, 1, 1)))
        comps["Pool"].add_instances(xp, False, True)
        comps["Ring"].add_instances(xr, False, True)
        comps["Core"].add_instances(xr, False, True)
        return len(items)
    small_items, miss = [], 0
    for (p, dx, dy, w, elev) in small:
        z = road_z(p[0], p[1], elev)
        if z is None:
            miss += 1
            continue
        small_items.append((p[0], p[1], z, yaw_of(dx, dy)))
    big_items = []
    for b in bigs:
        z = road_z(b[0], b[1])
        if z is not None:
            big_items.append((b[0], b[1], z, 0.0))
    n_small = place_set("SC_PadsSmall", "SC_PadSmall", small_items, kit("SC_PadRingSmall"), kit("SC_PadCoreSmall"), kit("SC_PadPoolSmall"), True)
    n_big = place_set("SC_PadsBig", "SC_PadBig", big_items, kit("SC_PadRingBig"), kit("SC_PadCoreBig"), kit("SC_PadPoolBig"), True)
    # --- Superchargers: rows of 3 bays just past the kerb, about every 450 m, >= 350 m apart, where it's clear
    sites = []
    for (c, d) in hints["chargers"]:
        sites.append((c, d))
    for pts, w, elev, chargeable in roads:
        if elev or not chargeable:
            continue
        for p, dx, dy in resample(pts, 450.0, 120.0):
            if any(math.dist(p, s[0]) < 350 for s in sites):
                continue
            z0 = road_z(p[0], p[1])
            if z0 is None:
                continue
            nx, ny = dy, -dx                                        # right of travel
            for side in (1, -1):
                off = w / 2 + 3.2
                cx, cy = p[0] + nx * side * off, p[1] + ny * side * off
                samples = [(cx + dx * a + nx * b, cy + dy * a + ny * b) for a in (-9.5, -3.0, 3.0, 9.5) for b in (-1.3, 1.3)]
                zs = []
                ok = True
                for (sx, sy) in samples:
                    hs = [h for h in hits_at(sx, sy, z0 + 25, z0 - 3) if not h[1].startswith("SC_")]
                    if not hs or abs(hs[0][0] - z0) > 0.6:
                        ok = False
                        break
                    zs.append(hs[0][0])
                if ok and max(zs) - min(zs) < 0.35:
                    sites.append(((cx, cy), (dx, dy)))
                    break
    bays, crosses = [], []
    for (c, d) in sites:
        z = road_z(c[0], c[1]) or 0.0
        yaw = yaw_of(d[0], d[1])
        for k in (-1, 0, 1):
            bays.append(unreal.Transform(U(c[0] + d[0] * 6.5 * k, c[1] + d[1] * 6.5 * k, z + 0.01), unreal.Rotator(roll=0, pitch=0, yaw=yaw), unreal.Vector(1, 1, 1)))
        crosses.append(unreal.Transform(U(c[0], c[1], z + 3.1), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)))
    act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    act.set_actor_label("SC_Chargers")
    act.set_folder_path("Skyster/Pickups")
    act.tags = [TAG, "SC_Chargers", "NoWallRide"]
    cb = add_component(act, unreal.InstancedStaticMeshComponent)
    cb.set_static_mesh(kit("SC_ChargerBay"))
    cb.set_mobility(unreal.ComponentMobility.MOVABLE)
    cb.set_collision_profile_name("NoCollision")
    cb.set_editor_property("num_custom_data_floats", 1)
    cb.component_tags = ["Bay"]
    cb.add_instances(bays, False, True)
    cc = add_component(act, unreal.InstancedStaticMeshComponent)
    cc.set_static_mesh(kit("SC_ChargerCross"))
    cc.set_mobility(unreal.ComponentMobility.MOVABLE)
    cc.set_collision_profile_name("NoCollision")
    cc.component_tags = ["Cross"]
    cc.add_instances(crosses, False, True)
    # --- fuel add-ons
    act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    act.set_actor_label("SC_Addons")
    act.set_folder_path("Skyster/Pickups")
    act.tags = [TAG, "SC_Addon", "NoWallRide"]
    placed_addons = []
    for (aid, p, how) in hints["addons"]:
        if how == "tallest_austin":
            play = hints.get("play", [-1577, -1668, 1423, 1332])
            best = None
            for gx in range(int(play[0]), -700, 40):
                for gy in range(int(play[1]), int(play[3]), 40):
                    hs = hits_at(gx, gy, 700, -10)
                    if hs and (best is None or hs[0][0] > best[2]):
                        best = (gx, gy, hs[0][0])
            if not best:
                continue
            p, z = (best[0], best[1]), best[2]
        elif how == "roof":
            hs = [h for h in hits_at(p[0], p[1], 700, -10) if not h[1].startswith("SC_")]
            if not hs:
                continue
            z = hs[0][0]
            if z < 8:                                               # no building right there: the nearest mid-height roof
                best = None
                for gx in range(-150, 151, 15):
                    for gy in range(-150, 151, 15):
                        hh = [h for h in hits_at(p[0] + gx, p[1] + gy, 700, -10) if not h[1].startswith("SC_")]
                        if hh and 25 < hh[0][0] < 150:
                            score = abs(hh[0][0] - 60) + 0.2 * math.hypot(gx, gy)
                            if best is None or score < best[0]:
                                best = (score, p[0] + gx, p[1] + gy, hh[0][0])
                if best:
                    p, z = (best[1], best[2]), best[3]
        elif how == "air36":
            z = (road_z(p[0], p[1]) or 0.0) + 36.0
        else:                                                       # street level: snap to the nearest pressure point's road
            if small_items:
                q = min(small_items, key=lambda s: math.dist((s[0], s[1]), p))
                p, z = (q[0] + 6.0, q[1] + 6.0), q[2]
                z = road_z(p[0], p[1]) or z
            else:
                z = road_z(p[0], p[1]) or 0.0
        c = add_component(act, unreal.StaticMeshComponent)
        c.set_static_mesh(kit(f"SC_Addon_{aid}"))
        c.set_collision_profile_name("NoCollision")
        c.component_tags = [aid]
        c.set_world_location(U(p[0], p[1], z + 0.05), False, True)
        c.set_world_scale3d(unreal.Vector(1.4, 1.4, 1.4))
        placed_addons.append([aid, how, round(p[0], 1), round(p[1], 1), round(z, 1)])
    log("place", {"map": map_name(), "small": n_small, "big": n_big, "miss": miss, "charger_sites": len(sites), "bays": len(bays),
                  "addons": placed_addons, "secs": round(time.time() - t0, 1)})


def stage_rig():
    paths = import_files(sorted(glob.glob(ROOT + "/SourceArt/RoadsterRig/*.glb")), "/Game/Vehicles/RoadsterRig")
    # thruster plume: additive, unlit, two-sided; bright at the nozzle, fading to nothing at the tip (V = 1)
    jm = new_material("M_SkyJet")
    jm.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    jm.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    jm.set_editor_property("two_sided", True)
    X = lambda cls, x, y: MEL.create_material_expression(jm, cls, x, y)
    tc = X(unreal.MaterialExpressionTextureCoordinate, -900, 0)
    v = X(unreal.MaterialExpressionComponentMask, -750, 0)
    for ch, on in zip("rgba", (False, True, False, False)):
        v.set_editor_property(ch, on)
    MEL.connect_material_expressions(tc, "", v, "")
    om = X(unreal.MaterialExpressionOneMinus, -600, 0)
    MEL.connect_material_expressions(v, "", om, "")
    pw = X(unreal.MaterialExpressionPower, -450, 0)
    MEL.connect_material_expressions(om, "", pw, "Base")
    ex = X(unreal.MaterialExpressionConstant, -600, 120)
    ex.set_editor_property("r", 1.4)
    MEL.connect_material_expressions(ex, "", pw, "Exp")
    col = X(unreal.MaterialExpressionVectorParameter, -450, -200)
    col.set_editor_property("parameter_name", "Color")
    col.set_editor_property("default_value", unreal.LinearColor(0.9, 1.3, 1.9, 1))
    st = X(unreal.MaterialExpressionScalarParameter, -450, 200)
    st.set_editor_property("parameter_name", "Strength")
    st.set_editor_property("default_value", 2.0)
    m1 = X(unreal.MaterialExpressionMultiply, -250, -50)
    MEL.connect_material_expressions(col, "", m1, "A")
    MEL.connect_material_expressions(pw, "", m1, "B")
    m2 = X(unreal.MaterialExpressionMultiply, -100, 0)
    MEL.connect_material_expressions(m1, "", m2, "A")
    MEL.connect_material_expressions(st, "", m2, "B")
    MEL.connect_material_property(m2, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(jm)
    EAL.save_loaded_asset(jm)
    jmi = mi("MI_Jet", jm)
    em = EAL.load_asset(f"{DIR}/Materials/M_SkyEmissive")
    lmi = mi("MI_CarLight", em, {"Strength": 5.0}, {"Color": (1.0, 0.97, 0.92)})
    for m in (jmi, lmi):
        EAL.save_loaded_asset(m)
    for p in paths:
        a = EAL.load_asset(p)
        if a:
            EAL.save_loaded_asset(a)
    log("rig", {"imported": len(paths)})


def stage_rings():
    gone = 0
    for a in EAS.get_all_level_actors():
        if "BoostRing" in a.get_class().get_name() or a.get_actor_label().startswith("BP_BoostRing"):
            EAS.destroy_actor(a)
            gone += 1
    log("rings_removed", gone)


def add_component(actor, cls):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    BFL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=cls, blueprint_context=None)
    h, fail = sds.add_new_subobject(params)
    return BFL.get_object(BFL.get_data(h))


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
