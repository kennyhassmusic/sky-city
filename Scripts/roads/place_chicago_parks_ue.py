"""Chicago parks, museums, statues and landmark buildings (chicago-parks agent, 20-21 Oct 2026) from the Blender kit
(Scripts/landmarks/blender_chicago_parks.py -> SourceArt/Landmarks/parks/meshes/*.glb + parks.json) placed at their REAL
positions in the plan (Saved/Mashup/plan_v3.json frame: metres, x east, y north; Unreal X = y*100, Y = x*100).

Every asset is modelled in the plan frame about its own origin (parks.json "origin_plan_m"), so it is placed at that
origin with NO rotation; Z = the ground traced there. Re-runnable: the place stage first removes every actor tagged
SC_Parks, then spawns them again.

Stages (default: import setup materials place clear standins save):
  import     import the GLBs (all, or `import=PK_A,PK_B`) into /Game/City/Parks
  setup      Nanite OFF (the M1 draws Nanite as coarse fallbacks) and complex-as-simple collision on every PK_ mesh
  materials  MI_PK_* (tinted M_StreetProp) for this kit's own slots, then assign every slot (the landmarks' MI_LM_* and the
             city's textured surfaces are reused for the shared slots); `assign` only assigns
  place      remove the SC_Parks actors, spawn every asset of parks.json (or `only=PK_A,PK_B`) at its origin
             collide: complex -> BlockAll; none -> NoCollision; hidden -> BlockAll, invisible (simple colliders of towers)
  clear      remove street props / trees (RProps_* instances) inside the assets' zones ('props') and City Sample building
             instances, their roof caps and their BuildingCollision boxes inside 'buildings' zones
             RE-RUN `clear save` after build_road_props_ue.py, citysample_buildings.py or building_collision.py
  standins   remove build_city.py's generic stand-ins that these assets replace (none at present: the Willis Tower and its
             stand-in belong to the willis-tower agent)
  save       save dirty packages (World Partition: one file per actor)
Run in the editor (hold the editor lock):
  py Scripts/roads/place_chicago_parks_ue.py [stages...]
Writes Saved/MCPScripts/out_parks.json.
"""
import json, math, sys, time, traceback, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_parks.json"
KIT = json.load(open(ROOT + "/SourceArt/Landmarks/parks/parks.json"))
ASSETS = KIT["assets"]
DIR = "/Game/City/Parks"
LMDIR = "/Game/City/Landmarks/Materials"
TAG = "SC_Parks"
FOLDER = "City/Parks"
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
STAGES = sys.argv[1:] or ["import", "setup", "materials", "place", "clear", "standins", "save"]
ONLY = None
GROW = 3.0                      # m added round each building zone's box when carving BuildingCollision ("grow=5" to change)
for _a in list(STAGES):
    if _a.startswith("grow="):
        GROW = float(_a.split("=", 1)[1])
STAGES = [a for a in STAGES if not a.startswith("grow=")]
for _a in list(STAGES):
    if _a.startswith(("import=", "only=")):
        ONLY = _a.split("=", 1)[1].split(",")
STAGES = [a.split("=")[0] for a in STAGES if not a.startswith("only=")]
out = {"stages": STAGES, "only": ONLY}
STANDINS = ()     # Landmark_WillisTower (build_city.py) belongs to the willis-tower agent since 20 Oct 23:10

# this kit's own slots -> (linear tint, roughness, metallic[, emissive strength]); same values as the Blender MATDEF
OWN = {
    "M_TowerBlack": ((0.025, 0.025, 0.028), 0.35, 0.8),
    "M_TintedGlass": ((0.05, 0.042, 0.035), 0.06, 0.6),
    "M_Louvre": ((0.06, 0.06, 0.065), 0.6, 0.5),
    "M_Stainless": ((0.78, 0.79, 0.81), 0.22, 1.0),
    "M_PipeWhite": ((0.80, 0.81, 0.82), 0.4, 0.3),
    "M_SeatRed": ((0.40, 0.03, 0.025), 0.55),
    "M_WoodLight": ((0.42, 0.25, 0.12), 0.6),
    "M_LEDBright": ((0.95, 0.88, 0.80), 0.3, 0.0, 2.0),
    "M_LEDMid": ((0.55, 0.38, 0.28), 0.3, 0.0, 1.2),
    "M_LEDSkin": ((0.75, 0.52, 0.40), 0.3, 0.0, 1.6),
    "M_LEDDark": ((0.10, 0.06, 0.05), 0.3, 0.0, 0.6),
    "M_GlassBlock": ((0.62, 0.70, 0.74), 0.15, 0.0, 0.25),
    "M_GraniteBlack": ((0.02, 0.02, 0.025), 0.12),
    "M_CorTen": ((0.20, 0.07, 0.03), 0.75, 0.3),
    "M_CalderRed": ((0.70, 0.05, 0.02), 0.5, 0.1),
    "M_LionBronze": ((0.10, 0.13, 0.09), 0.45, 0.8),
    "M_Gravel": ((0.45, 0.42, 0.37), 0.95),
    "M_ClimbGrey": ((0.50, 0.51, 0.52), 0.7, 0.1),
    "M_Ice": ((0.80, 0.86, 0.90), 0.1),
    "M_SignBulb": ((1.0, 0.85, 0.55), 0.4, 0.0, 8.0),
    "M_SignRed": ((0.75, 0.04, 0.03), 0.45, 0.0, 3.0),
    "M_Marble": ((0.78, 0.77, 0.73), 0.45),
    "M_MosaicRed": ((0.50, 0.10, 0.07), 0.5),
    "M_MosaicGreen": ((0.14, 0.32, 0.22), 0.5),
    "M_MosaicWhite": ((0.74, 0.72, 0.66), 0.5),
    "M_Rubber": ((0.08, 0.22, 0.35), 0.9),
    "M_PaintYellow": ((0.80, 0.58, 0.07), 0.5, 0.2),
    "M_TerraCotta": ((0.80, 0.77, 0.69), 0.6),
    "M_GoldLeaf": ((0.75, 0.55, 0.20), 0.3, 1.0),
    "M_GlassTeal": ((0.05, 0.17, 0.21), 0.06, 0.6),
    "M_Salvia": ((0.16, 0.08, 0.30), 0.85),
    "M_Grasses": ((0.42, 0.38, 0.20), 0.9),
}
# shared slots: the city's textured surfaces (same mapping as place_landmarks_ue.TEXTURED) or the landmarks' MI_LM_*
TEXTURED = {
    "M_Granite": "MI_LM_Granite", "M_GranitePromenade": "MI_LM_GranitePromenade",
    "M_GraniteDark": "/Game/City/Street/Materials/MI_Kerb", "M_PinkPaver": "MI_LM_PinkPaver",
    "M_ParkPaver": "MI_LM_ParkPaver", "M_DeckPaving": "MI_LM_DeckPaving",
    "M_SidewalkConcrete": "/Game/City/Street/Materials/MI_Sidewalk", "M_DeckConcrete": "/Game/City/Street/Materials/MI_BridgeConcrete",
    "M_DockWall": "/Game/City/Street/Materials/MI_BridgeConcrete", "M_Lawn": "/Game/City/Street/Materials/MI_Lawn",
    "M_Asphalt": "/Game/City/Street/Materials/MI_Asphalt",
}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def names():
    return [n for n in ASSETS if not ONLY or n in ONLY]


def stage_import():
    tasks = []
    for name in names():
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f"{ROOT}/{ASSETS[name]['file']}")
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


def stage_setup():
    SMES = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    done = {}
    for name in names():
        sm = mesh(name)
        if sm is None:
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
        if bs and bs.get_editor_property("collision_trace_flag") != unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE:
            sm.modify()
            try:
                SMES.remove_collisions(sm)
            except Exception:
                pass
            bs = sm.get_editor_property("body_setup")
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        EAL.save_loaded_asset(sm)
        done[name] = [sm.get_num_triangles(0), str(sm.get_editor_property("body_setup").get_editor_property("collision_trace_flag"))]
    log("setup", done)


def own_mi(slot, v):
    name = "MI_PK_" + slot[2:]
    path = f"{DIR}/Materials/{name}"
    m = EAL.load_asset(path) if EAL.does_asset_exist(path) else AT.create_asset(name, f"{DIR}/Materials", unreal.MaterialInstanceConstant,
                                                                                    unreal.MaterialInstanceConstantFactoryNew())
    m.set_editor_property("parent", EAL.load_asset("/Game/City/Street/Materials/M_StreetProp"))
    tint, rough = v[0], v[1]
    metal = v[2] if len(v) > 2 else 0.0
    glow = v[3] if len(v) > 3 else 0.0
    MEL.set_material_instance_vector_parameter_value(m, "Tint", unreal.LinearColor(*tint, 1))
    MEL.set_material_instance_scalar_parameter_value(m, "Roughness", rough)
    MEL.set_material_instance_scalar_parameter_value(m, "Metallic", metal)
    MEL.set_material_instance_vector_parameter_value(m, "EmissiveColor", unreal.LinearColor(*tint, 1))
    MEL.set_material_instance_scalar_parameter_value(m, "EmissiveStrength", glow)
    MEL.update_material_instance(m)
    EAL.save_loaded_asset(m)
    return m


def resolve(slot):
    """Material for a slot: this kit's MI_PK_*, else the city surface / landmarks MI the landmarks kit uses."""
    if slot in OWN:
        p = f"{DIR}/Materials/MI_PK_{slot[2:]}"
        return EAL.load_asset(p) if EAL.does_asset_exist(p) else None
    if slot in TEXTURED:
        t = TEXTURED[slot]
        p = t if t.startswith("/") else f"{LMDIR}/{t}"
        if EAL.does_asset_exist(p):
            return EAL.load_asset(p)
    if slot == "M_WaterJet":
        p = f"{LMDIR}/M_LM_WaterJet"
        return EAL.load_asset(p) if EAL.does_asset_exist(p) else None
    p = f"{LMDIR}/MI_LM_{slot[2:]}"
    return EAL.load_asset(p) if EAL.does_asset_exist(p) else None


def stage_materials(build=True):
    made = []
    if build:
        for slot, v in OWN.items():
            own_mi(slot, v)
            made.append(slot)
    n, missing = 0, set()
    cache = {}
    for name in names():
        sm = mesh(name)
        if sm is None:
            continue
        for i, sml in enumerate(sm.get_editor_property("static_materials")):
            base = str(sml.get_editor_property("material_slot_name")).split(".")[0]
            if base not in cache:
                cache[base] = resolve(base)
            if cache[base]:
                sm.set_material(i, cache[base])
                n += 1
            else:
                missing.add(base)
        EAL.save_loaded_asset(sm)
    log("materials", {"built": made, "assigned": n, "unmapped_slots": sorted(missing)})


def stage_assign():
    stage_materials(build=False)


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


def U(px, py, z):
    return unreal.Vector(py * 100.0, px * 100.0, z)


def spawn(sm, label, loc, collide="complex"):
    a = EAS.spawn_actor_from_object(sm, loc, unreal.Rotator(roll=0, pitch=0, yaw=0))
    a.set_actor_label(label)
    a.set_folder_path(FOLDER)
    a.tags = [TAG, "City_Generated"] + (["NoWallRide"] if label.endswith(("Trellis",)) else [])
    a.set_editor_property("is_spatially_loaded", False)
    c = a.static_mesh_component
    if collide == "none":
        c.set_collision_profile_name("NoCollision")
    else:
        c.set_collision_profile_name("BlockAll")
    if collide == "hidden":
        c.set_editor_property("visible", False)
        c.set_editor_property("cast_shadow", False)
        a.set_actor_hidden_in_game(True)
    return a


def stage_place():
    global WORLD, IGNORE
    WORLD = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    gone = 0
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags] and (not ONLY or a.get_actor_label() in ONLY):
            EAS.destroy_actor(a)
            gone += 1
    acts = EAS.get_all_level_actors()
    IGNORE = [a for a in acts if a.get_actor_label().startswith(("RProps_", "CS_", "HLOD", "SC_", "LM_", "PK_", "Landmark_")) or
              a.get_actor_label() in ("BuildingCollision", "WorldBounds") or "HLOD" in a.get_class().get_name()]
    placed, missing = {}, []
    ground = {}
    for name in names():
        rec = ASSETS[name]
        sm = mesh(name)
        if sm is None:
            missing.append(name)
            continue
        ox, oy = rec["origin_plan_m"]
        gx, gy = rec.get("ground_probe_plan_m", (ox, oy))       # assets whose origin is on a street probe the park instead
        key = (round(gx, 1), round(gy, 1))
        if key not in ground:
            ground[key] = ground_z(gx, gy)
        gz, under = ground[key]
        gz += rec.get("z_offset_m", 0.0) * 100.0
        IGNORE.append(spawn(sm, name, U(ox, oy, gz), rec.get("collide", "complex")))     # never trace onto our own
        placed[name] = {"ground_cm": round(gz, 1), "under": under}
    log("place", {"placed": placed, "removed": gone, "missing": missing})


# ------------------------------------------------------------------ clear: props, trees and City Sample buildings in zones
def inside(poly, x, y):
    c = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def zones(kind):
    zs = []
    for name, rec in ASSETS.items():
        z = rec.get("zone")
        if not z or kind not in z.get("clear", []):
            continue
        # buildings: the whole footprints of the named City Sample buildings when given (z["buildings"]), else the zone
        polys = z["buildings"] if kind == "buildings" and z.get("buildings") else [z["poly"]] + list(z.get("extra", []))
        for poly in polys:
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            zs.append({"name": name, "poly": poly, "bbox": [min(xs), max(xs), min(ys), max(ys)]})
    for z in KIT.get("zones", []):
        if kind in z.get("clear", []):
            xs = [p[0] for p in z["poly"]]
            ys = [p[1] for p in z["poly"]]
            zs.append({"name": z["name"], "poly": z["poly"], "bbox": [min(xs), max(xs), min(ys), max(ys)]})
    return zs


def zone_hit(zs, X, Y):
    px, py = Y / 100.0, X / 100.0
    for z in zs:
        b = z["bbox"]
        if b[0] <= px <= b[1] and b[2] <= py <= b[3] and inside(z["poly"], px, py):
            return z["name"]
    return None


def stage_clear():
    props_z, bldg_z = zones("props"), zones("buildings")
    res = {"props": {}, "buildings": {}, "zones": [len(props_z), len(bldg_z)]}
    for a in EAS.get_all_level_actors():
        lab = a.get_actor_label()
        if lab.startswith("RProps_"):
            zs = props_z
        elif lab.startswith("CS_"):
            zs = bldg_z
        else:
            continue
        if not zs:
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
                zn = zone_hit(zs, p.x, p.y)
                if zn:
                    kill.append(i)
                    d = res["props"] if lab.startswith("RProps_") else res["buildings"]
                    d[zn] = d.get(zn, 0) + 1
            if kill:
                a.modify()
                c.modify()
                c.remove_instances(kill)
    res["roof_caps"] = carve_roof_caps(bldg_z)
    res["collision"] = carve_collision(bldg_z)
    log("clear", res)


def carve_roof_caps(zs):
    """City Sample roof caps are one DynamicMeshComponent per PCG volume: delete their triangles inside the zones' boxes."""
    done = {}
    if not zs:
        return done
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
                if after != before:
                    done[lab + "|" + c.get_name()] = [before, after]
            except Exception:
                done[lab + "|" + c.get_name()] = traceback.format_exc()[-400:]
    return done


def carve_collision(zs):
    """Delete the BuildingCollision boxes whose triangles lie inside a building zone's bounding box."""
    if not zs:
        return "no building zones"
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
        g = GROW * 100.0              # the collision boxes come from facade extents and can stand a little outside the footprint
        for z in zs:
            b = z["bbox"]
            box = unreal.Box(unreal.Vector(b[2] * 100 - g, b[0] * 100 - g, -5000), unreal.Vector(b[3] * 100 + g, b[1] * 100 + g, 100000))
            r = unreal.GeometryScript_MeshSelection.select_mesh_elements_in_box(dm, box, unreal.GeometryScriptMeshSelectionType.TRIANGLES, False, 3)
            sel = next((x for x in (r if isinstance(r, (tuple, list)) else [r]) if isinstance(x, unreal.GeometryScriptMeshSelection)), None)
            if sel is None:
                return "no selection from select_mesh_elements_in_box: %r" % (r,)
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


def stage_standins():
    gone = []
    for a in EAS.get_all_level_actors():
        if a.get_actor_label() in STANDINS:
            gone.append(a.get_actor_label())
            EAS.destroy_actor(a)
    log("standins", gone)


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
        t0 = time.time()
        fn()
        log("stage_" + name + "_s", round(time.time() - t0, 1))
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        log("error", traceback.format_exc())
    finally:
        BUSY[0] = False


_h = unreal.register_slate_post_tick_callback(tick)
