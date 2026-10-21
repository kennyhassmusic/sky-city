"""The Texas State Capitol and its grounds from Scripts/landmarks/blender_capitol.py (SourceArt/Landmarks/capitol) placed
where the plan puts it in SkyCityMashup, on the Congress Avenue axis, replacing build_city.py's box-and-sphere stand-in.

Stages (run in the editor console, one call, they run in order from a slate tick so the editor stays responsive):
  py Scripts/roads/place_capitol_ue.py [import] [materials] [place] [trees] [save]
  import     GLBs -> /Game/City/Capitol (kept out of /Game/City/Landmarks: that folder's material pass renames slots)
  materials  MI_Cap_* instances (granite = the city's concrete-pavement ashlar texture tinted sunset red, lawn, asphalt,
             diamond paving...), slot by slot; Nanite off; complex-as-simple collision so the car drives the drives,
             climbs the steps and wall-rides the granite
  place      removes the stand-in (Landmark_TexasStateCapitol) and our earlier actors (tag SC_Capitol), traces the city
             ground at the rotunda, finds how the glTF import turned the axes, then spawns the building, dome and
             grounds at one shared transform and the fence modules / gate piers / lamps as instanced meshes
  trees      removes the city's park trees and street props (SC_RoadProps instances) that stand on the building,
             drives, walks, plazas or the fence line (keep-out polygons in capitol.json); OpenStreetMap trees on the
             lawns stay, so the Great Walk keeps its two tree rows
  save       World Partition: saves every dirty actor package
  shots tag=<t> "poses=name:px,py,z,pitch,yaw;..."   viewport captures to Saved/Capitol/shots (plan metres, compass yaw)
Writes Saved/MCPScripts/out_capitol.json. Rerunning build_city.py's `landmarks` stage brings the stand-in back.
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
SRC = ROOT + "/SourceArt/Landmarks/capitol"
OUT = ROOT + "/Saved/MCPScripts/out_capitol.json"
CAP = json.load(open(SRC + "/capitol.json"))
LAY = CAP["layout"]
DIR = "/Game/City/Capitol"
TAG = "SC_Capitol"
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
STAGES = [a for a in sys.argv[1:] if "=" not in a] or ["import", "materials", "place", "trees", "save"]
ASSETS = ["LM_Capitol_Building", "LM_Capitol_Dome", "LM_Capitol_Grounds", "LM_Capitol_Fence10", "LM_Capitol_GatePier", "LM_Capitol_Lamp"]
out = {"stages": STAGES}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


# ------------------------------------------------------------------ frame: building (u east, v north) -> plan -> Unreal
R0 = LAY["frame"]["origin_plan_m"]
PHI = math.radians(LAY["frame"]["phi_deg"])
CP, SP = math.cos(PHI), math.sin(PHI)


def to_plan(u, v):
    return (R0[0] + CP * u - SP * v, R0[1] + SP * u + CP * v)


def ue_xy(p):
    return (p[1] * 100.0, p[0] * 100.0)


def matmul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(2)) for j in range(2)] for i in range(2)]


SWAP = [[0, 1], [1, 0]]                     # plan (x, y) -> Unreal (X, Y)
ROT = [[CP, -SP], [SP, CP]]                 # building -> plan
CANDIDATES = {"x,-y": [[1, 0], [0, -1]], "-x,y": [[-1, 0], [0, 1]], "y,x": [[0, 1], [1, 0]], "-y,-x": [[0, -1], [-1, 0]]}


def import_map():
    """Which of the four handedness-flipping axis maps the glTF import applied: compare LM_Capitol_Building's Unreal
    bounds with its Blender bounds (the building is long east-west and deeper to the north, so the answer is unique)."""
    sm = mesh("LM_Capitol_Building")
    bb = sm.get_bounding_box()
    a = CAP["assets"]["LM_Capitol_Building"]
    bmin, bmax = a["bbox_min_m"], a["bbox_max_m"]
    best = None
    for name, M in CANDIDATES.items():
        xs, ys = [], []
        for bx in (bmin[0], bmax[0]):
            for by in (bmin[1], bmax[1]):
                xs.append((M[0][0] * bx + M[0][1] * by) * 100.0)
                ys.append((M[1][0] * bx + M[1][1] * by) * 100.0)
        err = abs(min(xs) - bb.min.x) + abs(max(xs) - bb.max.x) + abs(min(ys) - bb.min.y) + abs(max(ys) - bb.max.y)
        if best is None or err < best[0]:
            best = (err, name, M)
    return best[1], best[2], round(best[0], 1)


def ue_rot(M, psi_deg=0.0):
    """Unreal yaw (deg) for something whose Blender-frame yaw in the building frame is psi."""
    c, s = math.cos(math.radians(psi_deg)), math.sin(math.radians(psi_deg))
    R = matmul(matmul(matmul(SWAP, ROT), [[c, -s], [s, c]]), M)     # M is its own inverse
    return math.degrees(math.atan2(R[1][0], R[0][0]))


# ------------------------------------------------------------------ import
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
    AT.import_asset_tasks(tasks)
    log("import", {n: bool(mesh(n)) for n in ASSETS})


def mesh(name):
    for p in EAL.list_assets(DIR, recursive=True):
        if p.split("/")[-1].split(".")[0] == name and EAL.find_asset_data(p).asset_class_path.asset_name == "StaticMesh":
            return EAL.load_asset(p.split(".")[0])
    return None


# ------------------------------------------------------------------ materials
SURF = "/Game/City/Street/Materials/M_StreetSurface"     # textured, tile size in metres, world-aligned or mesh UVs
PROP = "/Game/City/Street/Materials/M_StreetProp"        # flat colour, roughness, metallic, emissive
TEX = "/Game/City/Street/Textures"


def tex(name, kind):
    return EAL.load_asset(f"{TEX}/{name}/{name}_{kind}_2k")


def mi(name, parent, scalars=None, vectors=None, textures=None, switches=None):
    path = f"{DIR}/Materials/{name}"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
    else:
        m = AT.create_asset(name, f"{DIR}/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    m.set_editor_property("parent", EAL.load_asset(parent))
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
              {"BaseColorTex": tex(texname, "diff"), "NormalTex": tex(texname, "nor_gl"), "ARMTex": tex(texname, "arm")}, {"WorldAligned": world})


def flat(name, tint, rough, metal=0.0, glow=0.0):
    v = {"Tint": tint}
    if glow:
        v["EmissiveColor"] = tint
    return mi(name, PROP, {"Roughness": rough, "Metallic": metal, "EmissiveStrength": glow}, v)


def stage_materials():
    S = {
        # tints are target albedo / the texture's mean albedo (concrete_pavement 0.21/0.18/0.14, concrete_floor_01
        # 0.19/0.15/0.10, leafy_grass 0.32/0.23/0.10, asphalt_02 0.10 linear); sunset-red granite ~0.42/0.25/0.16 (warm tan-pink in sun, as in the photos),
        # the concrete-pavement slabs reading as ashlar courses (~0.67 m) at a 4 m tile
        "M_Granite": surf("MI_Cap_Granite", "concrete_pavement", (1.96, 1.42, 1.19), 0.9, 4.0, normal=0.8, macro=0.25),
        "M_GraniteRough": surf("MI_Cap_GraniteRough", "concrete_floor_01", (1.75, 1.23, 1.25), 1.0, 2.2, normal=1.0),
        "M_GranitePolished": surf("MI_Cap_GranitePolished", "concrete_floor_01", (1.32, 0.78, 0.87), 0.35, 1.2),
        "M_Curb": surf("MI_Cap_Curb", "concrete_floor_01", (1.9, 1.56, 1.73), 0.85, 1.5),
        "M_DomeIron": flat("MI_Cap_DomeIron", (0.46, 0.29, 0.20), 0.5, 0.15),
        "M_RoofMetal": flat("MI_Cap_RoofMetal", (0.30, 0.31, 0.31), 0.45, 0.55),
        "M_Glass": flat("MI_Cap_Glass", (0.03, 0.04, 0.05), 0.08, 0.5),
        "M_Door": flat("MI_Cap_Door", (0.09, 0.05, 0.03), 0.45, 0.2),
        "M_Statue": flat("MI_Cap_Statue", (0.62, 0.60, 0.55), 0.45, 0.3),
        "M_Bronze": flat("MI_Cap_Bronze", (0.23, 0.16, 0.09), 0.45, 0.9),
        "M_Lawn": surf("MI_Cap_Lawn", "leafy_grass", (0.19, 0.52, 0.24), 0.95, 3.0, world=True),
        "M_Planting": surf("MI_Cap_Planting", "leafy_grass", (0.1, 0.3, 0.15), 1.0, 2.0, world=True),
        "M_PavingLight": surf("MI_Cap_PavingLight", "concrete_floor_01", (2.6, 3.0, 3.9), 0.8, 2.0, world=True),
        "M_PavingDark": surf("MI_Cap_PavingDark", "concrete_floor_01", (0.63, 0.78, 1.06), 0.8, 2.0, world=True),
        "M_Concrete": surf("MI_Cap_Concrete", "concrete_pavement", (1.96, 2.27, 2.67), 0.85, 3.0, world=True),
        "M_Asphalt": surf("MI_Cap_Asphalt", "asphalt_02", (0.3, 0.3, 0.32), 0.9, 4.0, world=True),
        "M_Iron": flat("MI_Cap_Iron", (0.025, 0.025, 0.028), 0.5, 0.6),
        "M_Gold": flat("MI_Cap_Gold", (0.80, 0.55, 0.18), 0.3, 1.0),
        "M_Water": flat("MI_Cap_Water", (0.04, 0.10, 0.12), 0.04, 0.0),
        "M_Light": flat("MI_Cap_Light", (1.0, 0.93, 0.8), 0.4, 0.0, 6.0),
    }
    res = {}
    ses = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
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
        res[name] = n
    log("materials", res)


# ------------------------------------------------------------------ place
WORLD = None
SURFACE_LABELS = ("R2Blocks_", "R2BridgeDecks", "Ground", "Parks")


def ground_z(p, default=15.0):
    """City surface height at plan point p (the road-props builder's rule: step under anything that isn't ground)."""
    x, y = ue_xy(p)
    top = 3000.0
    for _ in range(8):
        hit = unreal.SystemLibrary.line_trace_single(WORLD, unreal.Vector(x, y, top), unreal.Vector(x, y, -1000),
                                                     unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True)
        if not hit:
            return default, None
        t = hit.to_tuple()
        a = t[9]
        if a and (a.get_actor_label().startswith(SURFACE_LABELS) or "StreetSurface" in [str(g) for g in a.tags]) and TAG not in [str(g) for g in a.tags]:
            return t[4].z, a.get_actor_label()
        if t[4].z >= top - 1.0:
            return default, None
        top = t[4].z - 2.0
    return default, None


def add_component(actor, cls):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    BFL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=cls, blueprint_context=None)
    h, fail = sds.add_new_subobject(params)
    return BFL.get_object(BFL.get_data(h))


def tagged(a, label, extra=()):
    a.set_actor_label(label)
    a.set_folder_path("City/Landmarks/Capitol")
    a.tags = [TAG, "City_Generated"] + list(extra)
    a.set_editor_property("is_spatially_loaded", False)


def instanced(label, sm, xfs, cull, collide=True, shadows=True):
    act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    tagged(act, label, ["NoWallRide"])
    c = add_component(act, unreal.HierarchicalInstancedStaticMeshComponent)
    c.set_static_mesh(sm)
    c.set_editor_property("cast_shadow", shadows)
    c.set_collision_profile_name("BlockAll" if collide else "NoCollision")
    c.set_cull_distances(int(cull * 0.8), int(cull))
    c.add_instances(xfs, False, True)
    return len(xfs)


def stage_place():
    global WORLD
    WORLD = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    gone = []
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags] or a.get_actor_label() == "Landmark_TexasStateCapitol":
            gone.append(a.get_actor_label())
            EAS.destroy_actor(a)
    # the grounds' base: the city surface round the rotunda (median of a few samples on the lawns)
    samples = []
    for u, v in ((0, -120), (-60, -120), (60, -120), (-120, 0), (120, 0), (0, 100), (-60, 180), (60, 180), (-130, -180), (130, -180)):
        z, lab = ground_z(to_plan(u, v))
        samples.append((round(z, 1), lab))
    zs = sorted(s[0] for s in samples)
    z0 = zs[len(zs) // 2]
    name, M, err = import_map()
    yaw = ue_rot(M, 0.0)
    X, Y = ue_xy(R0)
    loc = unreal.Vector(X, Y, z0)
    placed = {}
    for nm, extra in (("LM_Capitol_Building", []), ("LM_Capitol_Dome", []), ("LM_Capitol_Grounds", ["StreetSurface", "NoWallRide"])):
        sm = mesh(nm)
        a = EAS.spawn_actor_from_object(sm, loc, unreal.Rotator(roll=0, pitch=0, yaw=yaw))
        tagged(a, nm, extra)
        c = a.static_mesh_component
        c.set_collision_profile_name("BlockAll")
        placed[nm] = [round(loc.x), round(loc.y), round(loc.z), round(yaw, 3)]
    # fence modules along each run (10 m modules scaled to fit), gate piers, lamps: instanced
    ymap_x = abs(M[0][1]) == 1                 # does Blender Y land on the mesh's local X?
    fx = []
    for run in LAY.get("fence_runs_local", []):
        for a_, b_ in zip(run, run[1:]):
            L = math.dist(a_, b_)
            n = max(1, round(L / 10.0))
            psi = math.degrees(math.atan2(b_[0] - a_[0], -(b_[1] - a_[1])))     # module's -Y along the run
            sc = L / n / 10.0
            for k in range(n):
                q = to_plan(a_[0] + (b_[0] - a_[0]) * k / n, a_[1] + (b_[1] - a_[1]) * k / n)
                x, y = ue_xy(q)
                fx.append(unreal.Transform(unreal.Vector(x, y, z0 + 4.0), unreal.Rotator(roll=0, pitch=0, yaw=ue_rot(M, psi)),
                                           unreal.Vector(sc, 1, 1) if ymap_x else unreal.Vector(1, sc, 1)))
    px = [unreal.Transform(unreal.Vector(*ue_xy(to_plan(g[0], g[1])), z0 + 4.0), unreal.Rotator(roll=0, pitch=0, yaw=ue_rot(M, g[2])), unreal.Vector(1, 1, 1))
          for g in LAY.get("gate_piers_local", [])]
    lx = [unreal.Transform(unreal.Vector(*ue_xy(to_plan(p[0], p[1])), z0 + 5.0), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1))
          for p in LAY.get("lamps_local", [])]
    counts = {
        "fence": instanced("LM_Capitol_Fence", mesh("LM_Capitol_Fence10"), fx, 30000),
        "gate_piers": instanced("LM_Capitol_GatePiers", mesh("LM_Capitol_GatePier"), px, 40000),
        "lamps": instanced("LM_Capitol_Lamps", mesh("LM_Capitol_Lamp"), lx, 35000),
    }
    log("place", {"removed": gone, "ground_samples": samples, "z0": z0, "import_map": name, "map_err_cm": err, "yaw": round(yaw, 3),
                  "placed": placed, "instances": counts})


# ------------------------------------------------------------------ trees and props off the paving
def in_poly(p, poly):
    x, y = p
    c = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def stage_trees():
    outline = LAY["grounds_outline_plan"]
    ob = bbox(outline)
    keeps = [(bbox(k), k) for k in LAY["keepouts_plan"]]
    rings = [(bbox(r[0]), r[0], r[1]) for r in LAY.get("keepout_rings_plan", [])]

    def blocked(p):
        if not (ob[0] <= p[0] <= ob[2] and ob[1] <= p[1] <= ob[3]) or not in_poly(p, outline):
            return False
        for b, k in keeps:
            if b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3] and in_poly(p, k):
                return True
        for b, o, i in rings:
            if b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3] and in_poly(p, o) and not in_poly(p, i):
                return True
        return False

    removed, kept_on_lawn = {}, {}
    for a in EAS.get_all_level_actors():
        if "SC_RoadProps" not in [str(t) for t in a.tags]:
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            n = c.get_instance_count()
            kill, lawn = [], 0
            for i in range(n):
                t = c.get_instance_transform(i, True).translation
                p = (t.y / 100.0, t.x / 100.0)
                if ob[0] <= p[0] <= ob[2] and ob[1] <= p[1] <= ob[3]:
                    if blocked(p):
                        kill.append(i)
                    elif in_poly(p, outline):
                        lawn += 1
            if kill:
                a.modify()
                c.modify()
                c.remove_instances(sorted(kill, reverse=True))
                removed[f"{a.get_actor_label()}"] = removed.get(a.get_actor_label(), 0) + len(kill)
            if lawn:
                kept_on_lawn[a.get_actor_label()] = kept_on_lawn.get(a.get_actor_label(), 0) + lawn
    # report (don't touch) Skyster pickups and City Sample pieces standing on the Capitol's footprint or paving
    report = {}
    for a in EAS.get_all_level_actors():
        tags = [str(t) for t in a.tags]
        lab = a.get_actor_label()
        if not (lab.startswith("SC_Pads") or lab.startswith("SC_Chargers") or lab.startswith("SC_Addons") or lab.startswith("CS_")):
            continue
        o, e = a.get_actor_bounds(False)
        if o.x + e.x < ob[1] * 100 or o.x - e.x > ob[3] * 100 or o.y + e.y < ob[0] * 100 or o.y - e.y > ob[2] * 100:
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            n = c.get_instance_count()
            if n > 60000:
                continue
            hits = 0
            for i in range(n):
                t = c.get_instance_transform(i, True).translation
                p = (t.y / 100.0, t.x / 100.0)
                if blocked(p):
                    hits += 1
            if hits:
                report[f"{lab}/{c.get_name()}"] = hits
    log("trees", {"removed": removed, "kept_on_lawns": kept_on_lawn, "pickups_or_citysample_on_paving": report})


def stage_save():
    log("save", unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True))


# ------------------------------------------------------------------ captures
SHOT = {"i": 0, "k": 0, "files": []}


def stage_shots():
    """Queued: handled by the tick (one pose every ~70 frames)."""
    poses = []
    for p in KV.get("poses", "").split(";"):
        if p:
            name, vals = p.split(":")
            poses.append((name, [float(v) for v in vals.split(",")]))
    SHOT["poses"] = poses
    SHOT["tag"] = KV.get("tag", "shot")
    SHOT["res"] = [int(v) for v in KV.get("res", "1600x900").split("x")]
    os.makedirs(ROOT + "/Saved/Capitol/shots", exist_ok=True)
    return "async"


def shots_tick():
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if SHOT["i"] >= len(SHOT["poses"]):
        SHOT["k"] += 1
        return SHOT["k"] > 30
    name, (px, py, zm, pitch, yawc) = SHOT["poses"][SHOT["i"]]
    if SHOT["k"] == 0:
        ues.set_level_viewport_camera_info(unreal.Vector(py * 100.0, px * 100.0, zm * 100.0), unreal.Rotator(roll=0, pitch=pitch, yaw=yawc))
    if SHOT["k"] == 45:
        fn = f"{ROOT}/Saved/Capitol/shots/{SHOT['tag']}_{SHOT['i']:02d}_{name}.png"
        unreal.AutomationLibrary.take_high_res_screenshot(SHOT["res"][0], SHOT["res"][1], fn)
        SHOT["files"].append(fn)
        log("shots", SHOT["files"])
    SHOT["k"] += 1
    if SHOT["k"] > 70:
        SHOT["k"] = 0
        SHOT["i"] += 1
    return False


QUEUE = [(s, globals()["stage_" + s]) for s in STAGES]
BUSY = [False]
ASYNC = [None]
T0 = time.time()
_h = None
try:
    unreal.unregister_slate_post_tick_callback(__import__("builtins")._capitol_place_h)
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
        r = fn()
        if r == "async":
            ASYNC[0] = shots_tick
        log("stage", name)
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        log("error", traceback.format_exc())
    finally:
        BUSY[0] = False


open(OUT, "w").write(json.dumps({"started": STAGES}))
_h = unreal.register_slate_post_tick_callback(tick)
__import__("builtins")._capitol_place_h = _h
