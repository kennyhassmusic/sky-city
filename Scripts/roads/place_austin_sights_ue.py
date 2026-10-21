"""The Austin side's sights from Scripts/landmarks/blender_austin_sights.py (SourceArt/Landmarks/austin) placed in
SkyCityMashup where the plan puts them: the Congress Avenue Bridge's arches, sidewalks and lamps and the Lamar
Boulevard Bridge's arches under the city's decks, the Pfluger pedestrian bridge, docks and boats on Lady Bird Lake, the
Stevie Ray Vaughan, Angelina Eberly and Willie Nelson statues, the Treaty Oak, Austin's two moonlight towers in the map,
6th Street's neon, a theatre blade on Congress Avenue, the bat watchers, and twelve more Texas Capitol monuments.

Why: Kenny's 20 Oct overnight request ("all the structures in the surrounding areas: parks, stadiums, landmarks, boats,
the locks, docks, statues"); notes in side-session-notes/.../austin-sights-2026-10-20.md.

Stages (one console call; they run in order from a slate tick so the editor stays responsive):
  py Scripts/roads/place_austin_sights_ue.py [import] [materials] [place] [clear] [save]
  import     GLBs -> /Game/City/AustinSights (out of /Game/City/Landmarks, whose material pass renames slots), 8 per tick
  materials  MI_ATX_* (flat colours on M_StreetProp, textured ones on M_StreetSurface) or the city's own MIs (the
             Capitol's granite and bronze, the street kit's bark, leaves, lawn, gravel, bridge concrete); Nanite off;
             complex-as-simple collision on everything that collides
  place      removes our earlier actors (tag SC_AustinSights), checks how the glTF import turned the axes, then spawns
             every placement of austin_sights.json (plan metres; z on the traced city surface, on the lake at -5.5 m, or
             absolute); assets used 4+ times go in one instanced actor each
  clear      removes the stand-ins under our footprints: the city's park trees / lamps / benches / bins (SC_RoadProps
             instances) inside layout.clear circles and under the Pfluger walkway; never signals, signs or kerb props
  save       World Partition: saves every dirty actor package
  shots tag=<t> [sites=a,b]   viewport captures of each site to Saved/AustinSights/shots/<t>_<site>.jpg (via a PNG ring in tmp/)
Options: only=<substring,...> limits import/materials to matching assets.
Writes Saved/MCPScripts/out_austin_sights.json. Rerunning is safe (replace_existing imports; place removes our actors
first; clear only removes stand-ins still there).
"""
import json, math, os, subprocess, sys, time, traceback, unreal

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
SRC = ROOT + "/SourceArt/Landmarks/austin"
OUT = ROOT + "/Saved/MCPScripts/out_austin_sights.json"
DATA = json.load(open(SRC + "/austin_sights.json"))
LAY = DATA["layout"]
DIR = "/Game/City/AustinSights"
TAG = "SC_AustinSights"
FOLDER = "City/Landmarks/AustinSights"
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
STAGES = [a for a in sys.argv[1:] if "=" not in a] or ["import", "materials", "place", "clear", "save"]
ONLY = [s for s in KV.get("only", "").split(",") if s]
USED = sorted({p["asset"] for p in LAY["placements"]})
ASSETS = [a for a in sorted(DATA["assets"]) if a in USED and (not ONLY or any(s in a for s in ONLY))]
COLL = {}
for p in LAY["placements"]:
    COLL[p["asset"]] = p.get("collision", "complex")
WATER_Z = -550.0
NO_WALLRIDE = ("Fountain", "Jets", "Gazebo", "Moonlight", "Neon", "Theatre", "Crowd", "Statue", "Cap_", "Kayak", "SUP", "Shell", "Scull", "Boat", "Riverboat", "Dock",
               "Piling", "Stair", "TreatyOak")
out = {"stages": STAGES, "assets": len(ASSETS)}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def mesh(name):
    p = f"{DIR}/{name}/{name}"
    for cand in (p, f"{DIR}/{name}"):
        if EAL.does_asset_exist(cand):
            a = EAL.load_asset(cand)
            if isinstance(a, unreal.StaticMesh):
                return a
    for q in EAL.list_assets(f"{DIR}/{name}" if EAL.does_directory_exist(f"{DIR}/{name}") else DIR, recursive=True):
        if q.split("/")[-1].split(".")[0] == name and EAL.find_asset_data(q).asset_class_path.asset_name == "StaticMesh":
            return EAL.load_asset(q.split(".")[0])
    return None


# ------------------------------------------------------------------ import (8 GLBs per tick)
IMP = {"todo": None}


def stage_import():
    IMP["todo"] = list(ASSETS)
    IMP["done"] = []
    return "async_import"


def import_tick():
    batch, IMP["todo"] = IMP["todo"][:8], IMP["todo"][8:]
    tasks = []
    for name in batch:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f"{SRC}/{name}.glb")
        t.set_editor_property("destination_path", f"{DIR}/{name}")
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        tasks.append(t)
    if tasks:
        AT.import_asset_tasks(tasks)
    IMP["done"] += batch
    log("import", {"done": len(IMP["done"]), "of": len(ASSETS), "missing": [n for n in IMP["done"] if not mesh(n)]})
    return not IMP["todo"]


# ------------------------------------------------------------------ materials
SURF = "/Game/City/Street/Materials/M_StreetSurface"
PROP = "/Game/City/Street/Materials/M_StreetProp"
TEX = "/Game/City/Street/Textures"
SM = "/Game/City/Street/Materials"
CM = "/Game/City/Capitol/Materials"
REUSE = {   # slot -> an existing material instance of the city
    "M_Granite": f"{CM}/MI_Cap_Granite", "M_GranitePolished": f"{CM}/MI_Cap_GranitePolished", "M_GraniteRough": f"{CM}/MI_Cap_GraniteRough",
    "M_Bronze": f"{CM}/MI_Cap_Bronze", "M_Gold": f"{CM}/MI_Cap_Gold", "M_Bark": f"{SM}/MI_Bark", "M_Leaves_liveoak": f"{SM}/MI_Leaves_liveoak",
    "M_Concrete": f"{SM}/MI_BridgeConcrete", "M_Lawn": f"{SM}/MI_Lawn", "M_Gravel": f"{SM}/MI_Gravel", "M_Paving": f"{SM}/MI_Paving",
    "M_DeckConcrete": f"{SM}/MI_Sidewalk", "M_Asphalt": f"{SM}/MI_Asphalt", "M_WaterJet": "/Game/City/Landmarks/Materials/M_LM_WaterJet",
}
TEXMEAN = {"concrete_pavement": (0.21, 0.18, 0.14), "concrete_floor_01": (0.19, 0.15, 0.10)}
TEXTURED = {  # slot -> (texture, tile m, world aligned, normal strength)
    "M_Limestone": ("concrete_floor_01", 1.6, False, 0.8), "M_ConcreteDark": ("concrete_pavement", 3.0, False, 0.8),
    "M_PflugerRed": ("concrete_pavement", 2.5, True, 0.6), "M_Stucco": ("concrete_floor_01", 2.0, False, 0.5),
    "M_GraniteGrey": ("concrete_floor_01", 1.2, False, 0.4), "M_DockDeck": ("concrete_floor_01", 1.5, False, 0.6),
}


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


MATS = {}


def material(slot):
    if slot in MATS:
        return MATS[slot]
    m = None
    if slot in REUSE and EAL.does_asset_exist(REUSE[slot]):
        m = EAL.load_asset(REUSE[slot])
    elif slot in TEXTURED:
        tname, tile, world, nrm = TEXTURED[slot]
        d = DATA["materials"][slot]
        mean = TEXMEAN[tname]
        tint = tuple(max(0.05, d["rgb"][i] / mean[i]) for i in range(3))
        m = mi("MI_ATX_" + slot[2:], SURF, {"RoughnessScale": d["rough"] / 0.8, "TileSize": tile, "NormalStrength": nrm, "MacroVariation": 0.25},
               {"Tint": tint}, {"BaseColorTex": tex(tname, "diff"), "NormalTex": tex(tname, "nor_gl"), "ARMTex": tex(tname, "arm")}, {"WorldAligned": world})
    elif slot in DATA["materials"]:
        d = DATA["materials"][slot]
        v = {"Tint": tuple(d["rgb"])}
        if d["emit"]:
            v["EmissiveColor"] = tuple(d["rgb"])
        m = mi("MI_ATX_" + slot[2:], PROP, {"Roughness": d["rough"], "Metallic": d["metal"], "EmissiveStrength": d["emit"]}, v)
    MATS[slot] = m
    return m


def stage_materials():
    res = {}
    for name in ASSETS:
        sm = mesh(name)
        if not sm:
            res[name] = "missing"
            continue
        n = 0
        for i, sml in enumerate(sm.get_editor_property("static_materials")):
            base = str(sml.get_editor_property("material_slot_name")).split(".")[0]
            m = material(base)
            if m:
                sm.set_material(i, m)
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


def ue_xy(p):
    return (p[1] * 100.0, p[0] * 100.0)


def ground_z(p, default=15.0):
    """City surface height at plan point p (the road-props rule: step under anything that isn't street surface)."""
    x, y = ue_xy(p)
    top = 3000.0
    for _ in range(10):
        hit = unreal.SystemLibrary.line_trace_single(WORLD, unreal.Vector(x, y, top), unreal.Vector(x, y, -1000),
                                                     unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True)
        if not hit:
            return default, None
        t = hit.to_tuple()
        a = t[9]
        tags = [str(g) for g in a.tags] if a else []
        if a and (a.get_actor_label().startswith(SURFACE_LABELS) or "StreetSurface" in tags) and TAG not in tags:
            return t[4].z, a.get_actor_label()
        if t[4].z >= top - 1.0:
            return default, None
        top = t[4].z - 2.0
    return default, None


def import_map():
    """Which axis map the glTF import applied, from the Pfluger bridge's bounds (asymmetric): expected 'x,-y'."""
    cands = {"x,-y": (1, -1), "x,y": (1, 1)}
    sm = mesh("LM_ATX_PflugerBridge") or mesh(ASSETS[0])
    name = sm.get_name()
    a = DATA["assets"][name]
    bb = sm.get_bounding_box()
    best = None
    for k, (sx, sy) in cands.items():
        xs = sorted(c * sx * 100.0 for c in (a["bbox_min_m"][0], a["bbox_max_m"][0]))
        ys = sorted(c * sy * 100.0 for c in (a["bbox_min_m"][1], a["bbox_max_m"][1]))
        err = abs(xs[0] - bb.min.x) + abs(xs[1] - bb.max.x) + abs(ys[0] - bb.min.y) + abs(ys[1] - bb.max.y)
        if best is None or err < best[0]:
            best = (err, k)
    return best[1], round(best[0], 1)


def add_component(actor, cls):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    BFL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=cls, blueprint_context=None)
    h, fail = sds.add_new_subobject(params)
    return BFL.get_object(BFL.get_data(h))


def tagged(a, label, asset):
    a.set_actor_label(label)
    a.set_folder_path(FOLDER)
    tags = [TAG, "City_Generated"]
    if any(k in asset for k in NO_WALLRIDE):
        tags.append("NoWallRide")
    a.tags = tags
    a.set_editor_property("is_spatially_loaded", False)


def stage_place():
    global WORLD
    WORLD = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    gone = 0
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags]:
            EAS.destroy_actor(a)
            gone += 1
    amap, err = import_map()
    groups = {}
    for p in LAY["placements"]:
        groups.setdefault(p["asset"], []).append(p)
    placed, zlog, missing = {}, {}, []
    for asset, ps in sorted(groups.items()):
        sm = mesh(asset)
        if not sm:
            missing.append(asset)
            continue
        xfs = []
        for k, p in enumerate(ps):
            X, Y = ue_xy(p["p"])
            z = p.get("z", "ground")
            if z == "water":
                Z = WATER_Z
            elif z in ("ground", "deck"):
                Z, lab = ground_z(p["p"])
                if k < 3:
                    zlog[f"{asset}#{k}"] = [round(Z, 1), lab]
            else:
                Z = float(z) * 100.0
            Z += float(p.get("dz", 0.0)) * 100.0
            yaw = 90.0 - p["theta"] if amap == "x,-y" else p["theta"] - 90.0
            sc = p.get("scale", [1.0, 1.0, 1.0])
            if amap == "x,-y":
                sc = [sc[0], sc[1], sc[2]]          # Blender X stays the mesh's local X
            xfs.append(unreal.Transform(unreal.Vector(X, Y, Z), unreal.Rotator(roll=0, pitch=0, yaw=yaw), unreal.Vector(*sc)))
        coll = COLL.get(asset, "complex")
        if len(xfs) >= 4:
            act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
            tagged(act, asset.replace("LM_ATX_", "ATX_") + "_set", asset)
            c = add_component(act, unreal.HierarchicalInstancedStaticMeshComponent)
            c.set_static_mesh(sm)
            c.set_collision_profile_name("NoCollision" if coll == "none" else "BlockAll")
            c.set_cull_distances(40000, 60000)
            c.add_instances(xfs, False, True)
        else:
            for k, xf in enumerate(xfs):
                a = EAS.spawn_actor_from_object(sm, xf.translation, xf.rotation.rotator())
                a.set_actor_scale3d(xf.scale3d)
                tagged(a, asset.replace("LM_ATX_", "ATX_") + (f"_{k}" if len(xfs) > 1 else ""), asset)
                a.static_mesh_component.set_collision_profile_name("NoCollision" if coll == "none" else "BlockAll")
        placed[asset] = len(xfs)
    log("place", {"removed_old": gone, "import_map": amap, "map_err_cm": err, "placed": placed, "missing": missing, "z": zlog})


# ------------------------------------------------------------------ clear the stand-ins under our footprints
SOFT = ("RProps_liveoak", "RProps_elm", "RProps_linden", "RProps_honeylocust", "RProps_grate", "RProps_bench", "RProps_bin",
        "RProps_dumpster", "RProps_mailbox", "RProps_lamp")
TREES = ("RProps_liveoak", "RProps_elm", "RProps_linden", "RProps_honeylocust", "RProps_grate")


def stage_clear():
    zones = []
    for c in LAY.get("clear", []):
        x, y, r = c["circle"]
        zones.append((x, y, r, TREES if c["kind"] == "trees" else SOFT, c.get("why", "")))
    pf = LAY.get("sites", {}).get("pfluger")
    if pf:
        for q in pf.get("keepout_plan", []):
            zones.append((q[0], q[1], 5.0, SOFT, "Pfluger walkway"))
    removed, report = {}, {}
    for a in EAS.get_all_level_actors():
        lab = a.get_actor_label()
        tags = [str(t) for t in a.tags]
        is_prop = "SC_RoadProps" in tags or lab.startswith("RProps_")
        is_pickup = lab.startswith(("SC_Pads", "SC_Chargers", "SC_Addons"))
        if not (is_prop or is_pickup):
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            n = c.get_instance_count()
            if n == 0 or n > 120000:
                continue
            kill = []
            for i in range(n):
                t = c.get_instance_transform(i, True).translation
                px, py = t.y / 100.0, t.x / 100.0
                for zx, zy, r, kinds, why in zones:
                    if abs(px - zx) < r and abs(py - zy) < r and (px - zx) ** 2 + (py - zy) ** 2 < r * r:
                        if is_prop and lab.startswith(kinds):
                            kill.append(i)
                        elif is_pickup:
                            report[f"{lab}/{c.get_name()}#{i}"] = [round(px, 1), round(py, 1), why]
                        break
            if kill:
                a.modify()
                c.modify()
                c.remove_instances(sorted(set(kill), reverse=True))
                removed[lab] = removed.get(lab, 0) + len(set(kill))
    log("clear", {"removed": removed, "pickups_in_footprints": report})


def stage_save():
    log("save", unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True))


# ------------------------------------------------------------------ captures
def site_poses():
    """Camera poses per site (plan metres): (name, cam x, cam y, cam z, pitch, compass yaw)."""
    poses = []
    def look(name, tx, ty, tz, dist, height, bearing):
        a = math.radians(bearing)
        cx, cy = tx - math.sin(a) * dist, ty - math.cos(a) * dist
        pitch = -math.degrees(math.atan2(height - tz, dist))
        yaw_ue = math.degrees(math.atan2(tx - cx, ty - cy))       # Unreal yaw: X = plan y, Y = plan x
        poses.append((name, cx, cy, height, pitch, yaw_ue))
    sites = {}
    for p in LAY["placements"]:
        sites.setdefault(p.get("site") or p["asset"], []).append(p["p"])
    br = LAY.get("bridges", {})
    if "congress" in br:
        O, d, L = br["congress"]["origin"], br["congress"]["dir"], br["congress"]["water_len"]
        mid = (O[0] + d[0] * L / 2, O[1] + d[1] * L / 2)
        look("congress_side", mid[0], mid[1], -2.0, 150.0, 6.0, math.degrees(math.atan2(-d[1], d[0])) + 0.0)
        look("congress_low", mid[0] - 60, mid[1] - 40, -3.0, 70.0, -3.5, 60.0)
        look("congress_deck", O[0] + d[0] * 10 - 11.2, O[1] + d[1] * 10, 1.5, 40.0, 3.0, 0.0)
    if "lamar" in br:
        O, d, L = br["lamar"]["origin"], br["lamar"]["dir"], br["lamar"]["water_len"]
        look("lamar_pfluger", O[0] + d[0] * L / 2 - 30, O[1] + d[1] * L / 2, 0.0, 150.0, 20.0, 250.0)
    if "pfluger" in LAY.get("sites", {}):
        c = LAY["sites"]["pfluger"]["origin"]
        look("pfluger_helix", c[0], c[1], 3.0, 45.0, 15.0, 20.0)
        look("pfluger_air", c[0] + 30, c[1] + 90, 0.0, 170.0, 70.0, 200.0)
    for key, (dist, h, brg, tz) in {"srv": (14.0, 3.0, 290.0, 1.8), "eberly": (11.0, 3.0, 120.0, 1.5), "willie": (9.0, 2.5, 200.0, 2.0),
                                    "treaty_oak": (38.0, 8.0, 30.0, 5.0), "9th_guadalupe": (45.0, 12.0, 300.0, 25.0),
                                    "11th_trinity": (45.0, 12.0, 120.0, 25.0), "capitol": (60.0, 25.0, 180.0, 2.0), "sixth": (40.0, 9.0, 270.0, 4.0),
                                    "paramount": (28.0, 6.0, 300.0, 9.0), "hyatt": (45.0, 10.0, 160.0, -4.0), "riverboat": (40.0, 8.0, 200.0, -3.0),
                                    "boathouse": (45.0, 10.0, 200.0, -4.0), "bat_lawn": (30.0, 6.0, 180.0, 0.5)}.items():
        if key in sites:
            pts = sites[key]
            tx = sum(p[0] for p in pts) / len(pts)
            ty = sum(p[1] for p in pts) / len(pts)
            look(key, tx, ty, tz, dist, h, brg)
    return poses


SHOT = {"i": 0, "k": 0, "files": []}


def stage_shots():
    poses = site_poses()
    want = [s for s in KV.get("sites", "").split(",") if s]
    SHOT["poses"] = [p for p in poses if not want or p[0] in want]
    SHOT["tag"] = KV.get("tag", "shot")
    SHOT["res"] = [int(v) for v in KV.get("res", "1600x900").split("x")]
    os.makedirs(ROOT + "/Saved/AustinSights/shots", exist_ok=True)
    os.makedirs(ROOT + "/Saved/AustinSights/tmp", exist_ok=True)
    return "async_shots"


def shots_tick():
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if SHOT["i"] >= len(SHOT["poses"]):
        SHOT["k"] += 1
        return SHOT["k"] > 30
    name, px, py, zm, pitch, yaw = SHOT["poses"][SHOT["i"]]
    if SHOT["k"] == 0:
        ues.set_level_viewport_camera_info(unreal.Vector(py * 100.0, px * 100.0, zm * 100.0), unreal.Rotator(roll=0, pitch=pitch, yaw=yaw))
    tmp = f"{ROOT}/Saved/AustinSights/tmp/s{SHOT['i'] % 6}.png"
    if SHOT["k"] == 45:
        unreal.AutomationLibrary.take_high_res_screenshot(SHOT["res"][0], SHOT["res"][1], tmp)
    if SHOT["k"] == 69:
        fn = f"{ROOT}/Saved/AustinSights/shots/{SHOT['tag']}_{name}.jpg"
        subprocess.Popen(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "70", tmp, "--out", fn], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        SHOT["files"].append(fn)
        log("shots", SHOT["files"])
    SHOT["k"] += 1
    if SHOT["k"] > 70:
        SHOT["k"] = 0
        SHOT["i"] += 1
    return False


ASYNC_FN = {"async_import": import_tick, "async_shots": shots_tick}
QUEUE = [(s, globals()["stage_" + s]) for s in STAGES]
BUSY = [False]
ASYNC = [None]
T0 = time.time()
_h = None
try:
    unreal.unregister_slate_post_tick_callback(__import__("builtins")._austin_sights_h)
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
        if isinstance(r, str) and r in ASYNC_FN:
            ASYNC[0] = ASYNC_FN[r]
        log("stage", name)
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        log("error", traceback.format_exc())
    finally:
        BUSY[0] = False


open(OUT, "w").write(json.dumps({"started": STAGES}))
_h = unreal.register_slate_post_tick_callback(tick)
__import__("builtins")._austin_sights_h = _h
