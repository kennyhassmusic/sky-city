"""McGregor test-site structures in Unreal, from Saved/McGregor/site_features.json (Scripts/mcgregor/site_layout.py) and
the Blender kit SourceArt/McGregor/site/*.glb (Scripts/mcgregor/blender_site_kit.py). Run it in McGregor, then again in
McGregorNight (a copy of McGregor.umap with its own actors); the imported meshes, materials and the rebuilt OSM buildings
mesh are shared assets, so `import materials osm` only has to run once.

  import     the kit GLBs -> /Game/McGregor/Site (Nanite off for the M1; collision per site_features: complex-as-simple,
             a simple box, or none)
  materials  MI_Site* from the street kit's M_StreetProp (and MI_SiteLot from MI_Asphalt) on the kit's M_Site* slots;
             the OSM sheds' MI_MetalSiding goes whiter (the site's buildings are white in every photo)
  osm        rebuilds SM_MG_Buildings in place without what the kit replaces (osm_filter: superseded footprints, the
             'works' areas and 'water_tower' footprints that had been extruded into 22-38 m slabs, all storage tanks)
  clear      removes this script's actors (tag MG_Site) and the superseded spheroid water towers from WaterTowers
  lots       draped asphalt pads for the parking lots (SM_MG_SiteLots): the same 4 m grid on the DEM + 0.18 m as
             site_layout.py's lot_pad (the parked cars and stall lines stand on it), clipped to each lot's real OSM
             outline instead of a staircase of whole cells (20 Oct 2026 overnight, mcgregor-edges)
  lot_berms  ground-coloured berms all round the lots (SM_MG_SiteLotBerms, actor Site_LotBerms): top edge on the lot's
             own edge, bending down 1.5 degrees every 0.8 m then 1:8 into the terrain, so there's no 8-28 cm lip to hit
             (edges_lib.py; mcgregor-edges). Run it after `lots`; both are in the default lists
  place      one hierarchical instanced actor per kit mesh (labels Site_<mesh>), tags MG_Site + MG_Generated + NoWallRide
  beacons    McGregorNight only: red obstruction lights (emissive, no light cost) on the tall structures' tops
  save       saves the level and dirty packages
(20 Oct 2026, mcgregor-tests: the test stands' new kit pieces and SK_T_* site meshes are ordinary placements here; import
them and their materials with site_tests_ue.py first, which also cuts the trenches into the terrain.)
Rerun safely: `clear` first (it's in the default list). The demo area (unveil lot, ramp, stage, line-up) is not touched.
Run in the editor (PIE off), McGregor or McGregorNight loaded:
  py Scripts/mcgregor/site_ue.py [stage ...]
  default: import materials osm clear lots lot_berms place beacons save
           (McGregorNight: clear lots lot_berms place beacons save)
Writes Saved/MCPScripts/out_site.json.
"""
import glob, importlib, json, math, os, sys, time, traceback, unreal

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
RAS = os.environ.get("SKYCITY_MCGREGOR_RAW", os.path.join(ROOT, "Saved", "McGregorRaw"))   # raw USGS / NAIP rasters (fetch_rasters.py)
sys.path.insert(0, ROOT + "/Scripts/mcgregor")
import edges_lib as EL                  # lot outlines and berms (mcgregor-edges); reloaded so edits take effect
importlib.reload(EL)
OUT = ROOT + "/Saved/MCPScripts/out_site.json"
DIR = "/Game/McGregor"
SITE = DIR + "/Site"
F = json.load(open(ROOT + "/Saved/McGregor/site_features.json"))
D = json.load(open(ROOT + "/Saved/McGregor/mcgregor_data.json"))
TAG, GEN = "MG_Site", "MG_Generated"
KIT_FRONT = -90.0          # kit pieces face local +Y after the glTF import: placement bearings name the front direction
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
PR = unreal.GeometryScript_Primitives
STAGES = sys.argv[1:] or ["import", "materials", "osm", "clear", "lots", "lot_berms", "place", "beacons", "save"]
out = {"stages": STAGES, "map": unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name()}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def U(x, y, z=0.0):
    return unreal.Vector(y * 100.0, x * 100.0, z * 100.0)


def collide_of():
    c = {}
    for p in F["placements"]:
        c.setdefault(p["mesh"], p.get("collide", "complex"))
    return c


def kit_meshes():
    res = {}
    for p in EAL.list_assets(SITE, recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name == "StaticMesh":
            res[p.split("/")[-1].split(".")[0]] = p.split(".")[0]
    return res


# ------------------------------------------------------------------ stages
def stage_import():
    files = sorted(glob.glob(ROOT + "/SourceArt/McGregor/site/*.glb"))
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", SITE)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        tasks.append(t)
    AT.import_asset_tasks(tasks)
    ses = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    col = collide_of()
    done = {}
    for name, path in kit_meshes().items():
        sm = EAL.load_asset(path)
        ns = sm.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", False)
        sm.set_editor_property("nanite_settings", ns)
        mode = col.get(name, "complex")
        bs = sm.get_editor_property("body_setup")
        try:
            ses.remove_collisions(sm)
        except Exception:
            pass
        if mode == "box":
            ses.add_simple_collisions(sm, unreal.ScriptCollisionShapeType.BOX)
            bs = sm.get_editor_property("body_setup")
            if bs:
                bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
        elif bs:
            bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        EAL.save_loaded_asset(sm)
        done[name] = mode
    log("import", {"files": len(files), "meshes": done})


def mi(name, parent, scalars=None, vectors=None):
    path = f"{DIR}/Materials/{name}"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.clear_all_material_instance_parameters(m)
    else:
        m = AT.create_asset(name, f"{DIR}/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    m.set_editor_property("parent", parent)
    for k, v in (scalars or {}).items():
        MEL.set_material_instance_scalar_parameter_value(m, k, v)
    for k, v in (vectors or {}).items():
        MEL.set_material_instance_vector_parameter_value(m, k, unreal.LinearColor(*v, 1))
    MEL.update_material_instance(m)
    EAL.save_loaded_asset(m)
    return m


# slot -> (scalars, vectors) on M_StreetProp
SLOTS = {"M_SiteBlue": ({"Roughness": 0.55, "Metallic": 0.15}, {"Tint": (0.02, 0.09, 0.36)}),
         "M_SiteConcreteTan": ({"Roughness": 0.85}, {"Tint": (0.45, 0.38, 0.30)}),
         "M_SiteWhite": ({"Roughness": 0.45, "Metallic": 0.1}, {"Tint": (0.86, 0.87, 0.87)}),
         "M_SiteRoof": ({"Roughness": 0.5, "Metallic": 0.4}, {"Tint": (0.48, 0.50, 0.52)}),
         "M_SiteConcrete": ({"Roughness": 0.85}, {"Tint": (0.62, 0.59, 0.54)}),
         "M_SiteConcreteDark": ({"Roughness": 0.9}, {"Tint": (0.22, 0.21, 0.2)}),
         "M_SiteSteel": ({"Roughness": 0.5, "Metallic": 0.7}, {"Tint": (0.36, 0.37, 0.39)}),
         "M_SiteRust": ({"Roughness": 0.75, "Metallic": 0.3}, {"Tint": (0.28, 0.13, 0.07)}),
         "M_SiteDark": ({"Roughness": 0.8}, {"Tint": (0.035, 0.035, 0.04)}),
         "M_SiteGlass": ({"Roughness": 0.12, "Metallic": 0.2}, {"Tint": (0.04, 0.06, 0.08)}),
         "M_SiteRed": ({"Roughness": 0.45, "Metallic": 0.3}, {"Tint": (0.55, 0.04, 0.03)}),
         "M_SiteYellow": ({"Roughness": 0.45, "Metallic": 0.3}, {"Tint": (0.8, 0.55, 0.04)}),
         "M_SiteGrate": ({"Roughness": 0.6, "Metallic": 0.6}, {"Tint": (0.22, 0.22, 0.23)}),
         "M_SiteBerm": ({"Roughness": 0.95}, {"Tint": (0.42, 0.38, 0.27)}),
         "M_SiteBlack": ({"Roughness": 0.5, "Metallic": 0.5}, {"Tint": (0.05, 0.05, 0.055)}),
         "M_SiteDoor": ({"Roughness": 0.5, "Metallic": 0.4}, {"Tint": (0.62, 0.63, 0.64)}),
         "M_SiteTyre": ({"Roughness": 0.9}, {"Tint": (0.02, 0.02, 0.02)}),
         "M_SiteLine": ({"Roughness": 0.6}, {"Tint": (0.85, 0.85, 0.82)}),
         "M_SiteWood": ({"Roughness": 0.8}, {"Tint": (0.35, 0.25, 0.15)}),
         "M_SiteGalv": ({"Roughness": 0.38, "Metallic": 0.9}, {"Tint": (0.62, 0.63, 0.64)}),
         "M_SiteInterstage": ({"Roughness": 0.5, "Metallic": 0.4}, {"Tint": (0.32, 0.33, 0.35)}),
         "M_SiteWater": ({"Roughness": 0.08}, {"Tint": (0.02, 0.025, 0.03)}),
         "M_CarPaintWhite": ({"Roughness": 0.32, "Metallic": 0.45}, {"Tint": (0.82, 0.83, 0.83)}),
         "M_CarPaintSilver": ({"Roughness": 0.32, "Metallic": 0.45}, {"Tint": (0.52, 0.53, 0.55)}),
         "M_CarPaintBlack": ({"Roughness": 0.32, "Metallic": 0.45}, {"Tint": (0.025, 0.025, 0.028)}),
         "M_CarPaintGrey": ({"Roughness": 0.32, "Metallic": 0.45}, {"Tint": (0.17, 0.18, 0.19)}),
         "M_CarPaintRed": ({"Roughness": 0.32, "Metallic": 0.45}, {"Tint": (0.42, 0.03, 0.03)}),
         "M_CarPaintBlue": ({"Roughness": 0.32, "Metallic": 0.45}, {"Tint": (0.04, 0.09, 0.26)})}
MATS = {}


def load_site_mats():
    for slot in SLOTS:
        p = f"{DIR}/Materials/MI_{slot[2:]}"
        if EAL.does_asset_exist(p):
            MATS[slot] = EAL.load_asset(p)
    for n in ("MI_SiteLot",):
        p = f"{DIR}/Materials/{n}"
        if EAL.does_asset_exist(p):
            MATS[n] = EAL.load_asset(p)


def stage_materials():
    P = EAL.load_asset("/Game/City/Street/Materials/M_StreetProp")
    for slot, (sc, vec) in SLOTS.items():
        MATS[slot] = mi("MI_" + slot[2:], P, sc, vec)
    MATS["MI_SiteLot"] = mi("MI_SiteLot", EAL.load_asset("/Game/City/Street/Materials/MI_Asphalt"), {"TileSize": 4.5, "MacroVariation": 0.5}, {"Tint": (2.3, 2.3, 2.25)})
    # the OSM sheds: white metal siding like the photos (build_mcgregor_ue.py's materials stage uses the same value)
    ms = f"{DIR}/Materials/MI_MetalSiding"
    if EAL.does_asset_exist(ms):
        m = EAL.load_asset(ms)
        MEL.set_material_instance_vector_parameter_value(m, "Tint", unreal.LinearColor(0.84, 0.85, 0.85, 1))
        MEL.update_material_instance(m)
        EAL.save_loaded_asset(m)
    n = 0
    for name, path in kit_meshes().items():
        sm = EAL.load_asset(path)
        for i, s in enumerate(sm.get_editor_property("static_materials")):
            slot = str(s.get_editor_property("material_slot_name")).split(".")[0]
            if slot in MATS:
                sm.set_material(i, MATS[slot])
                n += 1
        EAL.save_loaded_asset(sm)
    log("materials", n)


def opts(mid):
    o = unreal.GeometryScriptPrimitiveOptions()
    o.set_editor_property("material_id", mid)
    return o


def ccw_xy(ring):
    a = sum(ring[k][0] * ring[(k + 1) % len(ring)][1] - ring[(k + 1) % len(ring)][0] * ring[k][1] for k in range(len(ring)))
    return ring if a > 0 else ring[::-1]


def write_mesh(dm, name, mats, collide):
    """Create /Game/McGregor/Meshes/<name>, or write into it in place (placed actors in both maps keep pointing at it).
    Returns (mesh, how); how = 'created' / 'in place' / 'kept (copy failed: ...)'."""
    path = f"{DIR}/Meshes/{name}"
    how = "created"
    if EAL.does_asset_exist(path):
        sm = EAL.load_asset(path)
        try:
            o = unreal.GeometryScriptCopyMeshToAssetOptions()
            for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", True), ("replace_materials", True), ("new_materials", mats)):
                try:
                    o.set_editor_property(k, v)
                except Exception:
                    pass
            unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, o, unreal.GeometryScriptMeshWriteLOD())
            how = "in place"
        except Exception as ex:
            return sm, f"kept (copy failed: {ex})"
    else:
        o = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
        for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", True), ("enable_nanite", False), ("enable_collision", collide)):
            try:
                o.set_editor_property(k, v)
            except Exception:
                pass
        res = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, o)
        sm = res[0] if isinstance(res, (tuple, list)) else res
    bs = sm.get_editor_property("body_setup")
    if bs:
        bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if collide else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
    for i, m in enumerate(mats):
        sm.set_material(i, m)
    EAL.save_loaded_asset(sm)
    return sm, how


def stage_osm():
    """build_mcgregor_ue.py's buildings stage, minus what the site kit replaces (same filter as that stage now applies)."""
    flt = F["osm_filter"]
    sup = flt.get("buildings", [])
    mat = {n: EAL.load_asset(f"{DIR}/Materials/{n}") for n in ("MI_MetalSiding", "MI_ConcreteBunker", "MI_StandSteel", "MI_HouseSiding", "MI_TankWhite")}
    kinds = {"industrial": "metal", "warehouse": "metal", "yes": "metal", "hangar": "metal", "bunker": "concrete", "tower": "steel",
             "works": "steel", "mast": "steel", "house": "house", "residential": "house", "church": "house", "garage": "metal"}
    slots = ["metal", "concrete", "steel", "house", "tank"]
    dm = unreal.DynamicMesh()
    n = skipped = 0
    for b in D["buildings"]:
        ring = b["ring"]
        if len(ring) < 3:
            continue
        c = (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
        if b["kind"] in flt.get("skip_kinds", []) or any(math.dist(c, q) < 3.0 for q in sup):
            skipped += 1
            continue
        pts = ccw_xy([(p[1] * 100.0, p[0] * 100.0) for p in ring])
        mid = slots.index(kinds.get(b["kind"], "metal"))
        PR.append_simple_extrude_polygon(dm, opts(mid), unreal.Transform(unreal.Vector(0, 0, b["z"] * 100.0), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                         [unreal.Vector2D(x, y) for x, y in pts], (b["h"] + 0.3) * 100.0, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        n += 1
    nt = 0
    for tk in D["tanks"]:
        if tk["kind"] in flt.get("skip_tank_kinds", []):
            continue
        PR.append_cylinder(dm, opts(4), unreal.Transform(U(tk["p"][0], tk["p"][1], tk["z"] - 0.2), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                           tk["r"] * 100.0, (tk["h"] + 0.2) * 100.0, 20, 1, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        if tk["kind"] == "silo":
            PR.append_cone(dm, opts(4), unreal.Transform(U(tk["p"][0], tk["p"][1], tk["z"] + tk["h"]), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                           tk["r"] * 100.0, 10.0, tk["r"] * 60.0, 20, 1, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        nt += 1
    unreal.GeometryScript_Normals.set_per_face_normals(dm)
    unreal.GeometryScript_UVs.set_mesh_u_vs_from_box_projection(dm, 0, unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(400, 400, 400)), unreal.GeometryScriptMeshSelection())
    mats = [mat["MI_MetalSiding"], mat["MI_ConcreteBunker"], mat["MI_StandSteel"], mat["MI_HouseSiding"], mat["MI_TankWhite"]]
    sm, how = write_mesh(dm, "SM_MG_Buildings", mats, True)
    swapped = 0
    if how.startswith("kept"):
        # fallback: a separate asset, swapped onto this map's Buildings actor (run `osm` in each map then)
        sm, how2 = write_mesh(dm, "SM_MG_BuildingsSite", mats, True)
        how += f"; fallback SM_MG_BuildingsSite {how2}"
        for a in EAS.get_all_level_actors():
            if a.get_actor_label() == "Buildings" and GEN in [str(t) for t in a.tags]:
                a.modify()
                a.static_mesh_component.set_static_mesh(sm)
                swapped += 1
    log("osm", {"footprints": n, "skipped": skipped, "tanks_kept": nt, "mesh": how, "swapped": swapped})


def stage_clear():
    gone = 0
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags]:
            EAS.destroy_actor(a)
            gone += 1
    # the spheroid water towers the site kit's plain white ones replace
    wt_removed = 0
    for a in EAS.get_all_level_actors():
        if a.get_actor_label() == "WaterTowers" and GEN in [str(t) for t in a.tags]:
            a.modify()
            for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
                c.modify()
                for i in reversed(range(c.get_instance_count())):
                    t = c.get_instance_transform(i, True)
                    t = t[1] if isinstance(t, (tuple, list)) else t
                    loc = t.translation
                    x, y = loc.y / 100.0, loc.x / 100.0
                    if any(math.dist((x, y), q) < 8.0 for q in F["osm_filter"].get("water_towers", [])):
                        c.remove_instance(i)
                        wt_removed += 1
    log("clear", {"actors": gone, "water_tower_instances": wt_removed})


# the lots' OSM ways (site_layout.py: lot_pad("OfficeLot", osm_ring(925912177)), simple_lot(925912166, ...), ...)
LOT_WAYS = {"OfficeLot": 925912177, "BlockhouseLot": 925912166, "CoreHangarLot": 925912173, "StandsLot": 233581971}


def lot_outlines():
    """Each lot as (name, MeshBuf of its draped surface, boundary loop, boundary heights). Lots with a known OSM ring:
    edges_lib.draped_lot (site_layout's 4 m grid on the DEM + raise_m, clipped to the ring). Others (a lot site_layout
    adds later): its own grid from site_features.json and the staircase boundary of that grid."""
    meta = json.load(open(RAS + "/rasters.json"))
    rings = EL.osm_rings(LOT_WAYS.values(), meta)
    dem = EL.DEM()
    res = []
    for lot in F["lots"]:
        ring = rings.get(LOT_WAYS.get(lot["name"]))
        rz = lot.get("raise_m", 0.18)
        if ring:
            buf, loop, tops = EL.draped_lot(ring, lambda x, y, rz=rz: dem.h(x, y) + rz)
            res.append((lot["name"], buf, [loop], [tops]))
            continue
        buf = EL.MeshBuf()
        for v in lot["verts"]:
            buf.add(*v)
        for t in lot["tris"]:
            buf.tri(0, *t)
        nxt = {}
        dirs = {(t[a], t[(a + 1) % 3]) for t in lot["tris"] for a in range(3)}
        for (a, b) in dirs:
            if (b, a) not in dirs:
                nxt[a] = b
        loops, seen = [], set()
        for s in list(nxt):
            if s in seen:
                continue
            lp, v = [], s
            while v not in seen and v in nxt:
                seen.add(v)
                lp.append(v)
                v = nxt[v]
            if len(lp) > 2:
                loops.append(lp)
        res.append((lot["name"], buf, [[tuple(lot["verts"][v][:2]) for v in lp] for lp in loops], [[lot["verts"][v][2] for v in lp] for lp in loops]))
    return res


def stage_lots():
    """The parking lots (see the header): draped on the DEM + 0.18 m like site_layout's lot_pad, clipped to their OSM
    outlines (edges_lib.draped_lot); their outlines go to Saved/McGregor/edges/outlines.json for the edge survey."""
    load_site_mats()
    buf = EL.MeshBuf()
    ol_lots = {}
    for name, b, loops, _tops in lot_outlines():
        off = len(buf.v)
        buf.v += b.v
        for mid, ts in b.t.items():
            for t in ts:
                buf.tri(0, t[0] + off, t[1] + off, t[2] + off)
        ol_lots[name] = [[round(x, 3), round(y, 3)] for x, y in loops[0]] if loops else []
    dm = buf.to_dynamic_mesh()
    unreal.GeometryScript_Normals.set_per_vertex_normals(dm)
    unreal.GeometryScript_UVs.set_mesh_u_vs_from_box_projection(dm, 0, unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(100, 100, 100)), unreal.GeometryScriptMeshSelection())
    lotmat = MATS.get("MI_SiteLot") or EAL.load_asset("/Game/City/Street/Materials/MI_Asphalt")
    sm, how = write_mesh(dm, "SM_MG_SiteLots", [lotmat], True)
    for old in EAS.get_all_level_actors():               # rerunnable without `clear`
        if old.get_actor_label() == "Site_Lots":
            EAS.destroy_actor(old)
    a = EAS.spawn_actor_from_object(sm, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    a.set_actor_label("Site_Lots")
    a.set_folder_path("McGregor/Site")
    a.tags = [TAG, GEN]
    a.static_mesh_component.set_editor_property("cast_shadow", False)
    a.static_mesh_component.set_collision_profile_name("BlockAll")
    os.makedirs(ROOT + "/Saved/McGregor/edges", exist_ok=True)
    op = ROOT + "/Saved/McGregor/edges/outlines.json"
    ol = json.load(open(op)) if os.path.exists(op) else {}
    ol["lots"] = ol_lots
    json.dump(ol, open(op, "w"))
    log("lots", {"lots": len(F["lots"]), "tris": buf.ntris(), "mesh": how, "outline_points": {k: len(v) for k, v in ol_lots.items()}})


def stage_lot_berms():
    """Berms all round the parking lots (see the header; edges_lib.berm_mesh), actor Site_LotBerms."""
    meta = json.load(open(RAS + "/rasters.json"))
    T = EL.Terrain(EAS.get_all_level_actors())
    if not T.comp:
        raise RuntimeError("no Terrain_i_j actors in this level")
    buf = EL.MeshBuf()
    stats = {}
    for name, _b, loops, tops in lot_outlines():
        for lp, tp in zip(loops, tops):
            s = {}
            EL.berm_mesh(lp, tp, T.h, EL.tile_index(meta["tiles"]), buf=buf, stats=s)
            stats[name] = s
    dm = EL.finish_mesh(buf.to_dynamic_mesh())
    sm, how = write_mesh(dm, "SM_MG_SiteLotBerms", EL.terrain_materials(meta["tiles"]), True)
    for old in EAS.get_all_level_actors():
        if old.get_actor_label() == "Site_LotBerms":
            EAS.destroy_actor(old)
    a = EAS.spawn_actor_from_object(sm, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    a.set_actor_label("Site_LotBerms")
    a.set_folder_path("McGregor/Site")
    a.tags = [TAG, GEN, "NoWallRide", "MG_Edge"]
    a.static_mesh_component.set_editor_property("cast_shadow", False)
    a.static_mesh_component.set_collision_profile_name("BlockAll")
    log("lot_berms", {"tris": buf.ntris(), "mesh": how, "terrain_traces": T.n, "material_ids": str(getattr(buf, "mat_check", None)), "lots": stats})


def stage_lots_staircase():
    """The lots as they were before 20 Oct 2026 overnight: whole 4 m cells from site_features.json (staircase edges)."""
    load_site_mats()
    LU = unreal.GeometryScript_List
    dm = unreal.DynamicMesh()
    for lot in F["lots"]:
        part = unreal.DynamicMesh()
        vl = LU.convert_array_to_vector_list([U(*v) for v in lot["verts"]])
        tl = LU.convert_array_to_triangle_list([unreal.IntVector(*t) for t in lot["tris"]])
        unreal.GeometryScript_MeshEdits.add_vertices_to_mesh(part, vl[0] if isinstance(vl, tuple) else vl)
        unreal.GeometryScript_MeshEdits.add_triangles_to_mesh(part, tl[0] if isinstance(tl, tuple) else tl, 0)
        nrm = unreal.GeometryScript_MeshQueries.get_triangle_face_normal(part, 0)
        nrm = nrm[0] if isinstance(nrm, tuple) else nrm
        if nrm.z < 0:
            unreal.GeometryScript_Normals.flip_normals(part)
        lib = unreal.GeometryScript_MeshEdits if hasattr(unreal.GeometryScript_MeshEdits, "append_mesh") else unreal.GeometryScript_MeshBasicEdits
        lib.append_mesh(dm, part, unreal.Transform())
    unreal.GeometryScript_Normals.set_per_vertex_normals(dm)
    unreal.GeometryScript_UVs.set_mesh_u_vs_from_box_projection(dm, 0, unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(100, 100, 100)), unreal.GeometryScriptMeshSelection())
    lotmat = MATS.get("MI_SiteLot") or EAL.load_asset("/Game/City/Street/Materials/MI_Asphalt")
    sm, how = write_mesh(dm, "SM_MG_SiteLots", [lotmat], True)
    a = EAS.spawn_actor_from_object(sm, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    a.set_actor_label("Site_Lots")
    a.set_folder_path("McGregor/Site")
    a.tags = [TAG, GEN]
    a.static_mesh_component.set_editor_property("cast_shadow", False)
    a.static_mesh_component.set_collision_profile_name("BlockAll")
    log("lots", {"lots": len(F["lots"]), "tris": unreal.GeometryScript_MeshQueries.get_num_triangle_i_ds(dm), "mesh": how})


def add_component(actor, cls):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    BFL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=cls, blueprint_context=None)
    h, fail = sds.add_new_subobject(params)
    return BFL.get_object(BFL.get_data(h))


CULL = {"SK_Car": 45000, "SK_StallLine": 18000, "SK_TankV": 160000, "SK_TankH": 160000, "SK_StageDebris": 80000, "SK_Crane": 250000}


def stage_place():
    meshes = kit_meshes()
    groups = {}
    for p in F["placements"]:
        groups.setdefault(p["mesh"], []).append(p)
    placed, missing = {}, []
    for name, ps in groups.items():
        if name not in meshes:
            missing.append(name)
            continue
        sm = EAL.load_asset(meshes[name])
        xfs = [unreal.Transform(U(p["p"][0], p["p"][1], p["z"]), unreal.Rotator(roll=0, pitch=0, yaw=p["bearing"] + KIT_FRONT), unreal.Vector(*p["scale"])) for p in ps]
        act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        act.set_actor_label(f"Site_{name}")
        act.set_folder_path("McGregor/Site")
        act.tags = [TAG, GEN, "NoWallRide"]
        c = add_component(act, unreal.HierarchicalInstancedStaticMeshComponent)
        c.set_static_mesh(sm)
        mode = ps[0].get("collide", "complex")
        c.set_collision_profile_name("NoCollision" if mode == "none" else "BlockAll")
        c.set_editor_property("cast_shadow", name != "SK_StallLine" and not name.startswith(("SK_T_Scorch", "SK_T_Pad", "SK_T_Apron")))   # (flat skins: mcgregor-tests)
        cull = next((v for k, v in CULL.items() if name.startswith(k)), 0)
        if cull:
            c.set_cull_distances(int(cull * 0.8), int(cull))
        c.add_instances(xfs, False, True)
        placed[name] = len(xfs)
    log("place", {"meshes": placed, "missing": missing, "instances": sum(placed.values())})


def stage_beacons():
    if "Night" not in out["map"] or not F.get("beacons"):
        log("beacons", "day map: none")
        return
    sm = EAL.load_asset("/Engine/BasicShapes/Sphere")
    red = EAL.load_asset(f"{DIR}/Materials/MI_Night_LEDRed") if EAL.does_asset_exist(f"{DIR}/Materials/MI_Night_LEDRed") else None
    act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    act.set_actor_label("Site_Beacons")
    act.set_folder_path("McGregor/Site")
    act.tags = [TAG, GEN, "NoWallRide"]
    c = add_component(act, unreal.HierarchicalInstancedStaticMeshComponent)
    c.set_static_mesh(sm)
    if red:
        c.set_material(0, red)
    c.set_collision_profile_name("NoCollision")
    c.set_editor_property("cast_shadow", False)
    c.add_instances([unreal.Transform(U(*b), unreal.Rotator(0, 0, 0), unreal.Vector(0.8, 0.8, 0.8)) for b in F["beacons"]], False, True)
    log("beacons", len(F["beacons"]))


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
