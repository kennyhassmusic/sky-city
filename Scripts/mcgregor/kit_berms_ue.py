"""Berms round the test stands' low concrete pads in the McGregor maps (mcgregor-edges, 20 Oct 2026). The site kit
(blender_site_kit.py, placed by site_ue.py from site_features.json) stands each stand on the DEM height at its centre,
so its aprons and decks are boxes 0.12-1.2 m tall whose downhill sides stand up like kerbs. This adds a ground-coloured
berm all round each one (edges_lib.berm_mesh: top edge on the pad's top, bending 1.5 degrees every 0.8 m, then 1:8 to
10 cm under the terrain), without touching the kit meshes or their placements:
  SK_Tripod           the scorched apron in front of the chute (16 x 22 x 0.3 m)
  SK_FSStand          the deck north of the sump (30 x 26 x 0.5 m), open on the pit side
  SK_FSTrench         the 7 m aprons along the trench rims (0.3 m), open on the pit side
  SK_EngineStandV     the scorched apron (10 x 14 x 0.12 m, scaled per stand)
  SK_EngineStandH     the scorched pad (14 x 34 x 0.12 m)
  SK_StructuralStand  the base pad (14 x 14 x 1.0 m, scaled)
Pads in the kit's Blender frame (x, y metres, front = -Y); placement -> site: x = px - bx*sX*cos(b) - by*sY*sin(b),
y = py + bx*sX*sin(b) - by*sY*cos(b), z = pz + top*sZ (b = the placement bearing).
Run in the editor (PIE off), in McGregor and in McGregorNight (the mesh asset is shared, the actor is per map):
  py Scripts/mcgregor/kit_berms_ue.py [build] [save]
Actor Edge_KitPadBerms (folder McGregor/Edges, tags MG_Generated, MG_Edge, NoWallRide), mesh SM_MG_KitPadBerms.
Rerun after site_layout.py moves a stand. Writes Saved/MCPScripts/out_kit_berms.json.
"""
import importlib, json, math, sys, time, traceback, unreal

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
import edges_lib as EL
importlib.reload(EL)

OUT = ROOT + "/Saved/MCPScripts/out_kit_berms.json"
F = json.load(open(ROOT + "/Saved/McGregor/site_features.json"))
META = json.load(open(RAS + "/rasters.json"))
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
STAGES = sys.argv[1:] or ["build", "save"]
out = {"stages": STAGES}
# mesh -> pads: (centre x, centre y, size x, size y, top z, open side or None) in the kit's Blender frame
PADS = {"SK_Tripod": [(0.0, -6.0, 16.0, 22.0, 0.3, None)],
        "SK_FSStand": [(1.0, 13.0, 30.0, 26.0, 0.5, "S")],
        "SK_EngineStandV": [(0.0, -10.0, 10.0, 14.0, 0.12, None)],
        "SK_EngineStandH": [(0.0, -24.0, 14.0, 34.0, 0.12, None)],
        "SK_StructuralStand": [(0.0, 0.0, 14.0, 14.0, 1.0, None)]}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def trench_east(y):          # blender_site_kit.py's trench lines (facility metres)
    return -122.0 + max(0.0, (-584.0 - y)) * (10.0 / 68.0)


def trench_west(y):
    return -146.0 - max(0.0, (-584.0 - y)) * 0.5


def subdiv(chain, step=2.0):
    res = []
    for a, b in zip(chain, chain[1:]):
        n = max(1, int(math.ceil(math.dist(a, b) / step)))
        res += [(a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n) for t in range(n)]
    return res + [chain[-1]]


def outlines():
    """[(name, points, top z, closed)] in site metres, open chains with the pad on their left."""
    res = []
    for p in F["placements"]:
        for (cx, cy, sx, sy, top, open_side) in PADS.get(p["mesh"], []):
            b = math.radians(p["bearing"])
            sX, sY, sZ = p["scale"]
            px, py = p["p"]

            def S(bx, by):
                return (px - bx * sX * math.cos(b) - by * sY * math.sin(b), py + bx * sX * math.sin(b) - by * sY * math.cos(b))
            sw, se, ne, nw = (cx - sx / 2, cy - sy / 2), (cx + sx / 2, cy - sy / 2), (cx + sx / 2, cy + sy / 2), (cx - sx / 2, cy + sy / 2)
            z = p["z"] + top * sZ
            if open_side == "S":
                chain = [S(*q) for q in (se, ne, nw, sw)]
                res.append((f"{p['mesh']}@{px:.0f},{py:.0f}", subdiv(chain), z, False))
            else:
                loop = subdiv([S(*q) for q in (sw, se, ne, nw, sw)])[:-1]
                res.append((f"{p['mesh']}@{px:.0f},{py:.0f}", loop, z, True))
        if p["mesh"] == "SK_FSTrench":
            # the rim aprons' outer edge (facility frame = site frame, origin at rim level; top 0.3 m): up the east side,
            # west along the north apron, down the west side (the pit on the right, the apron on the left)
            ys = [-656.0 + 5.0 * k for k in range(18)] + [-566.0]
            east = [(trench_east(y) + 7.0, y) for y in ys if y <= -575.0] + [(trench_east(-575.0) + 7.0, -566.0)]
            west = [(trench_west(-575.0) - 7.0, -566.0)] + [(trench_west(y) - 7.0, y) for y in reversed(ys) if y <= -575.0]
            res.append(("SK_FSTrench", subdiv(east + west), p["z"] + 0.3, False))
    return res


def stage_build():
    T = EL.Terrain(EAS.get_all_level_actors())
    if not T.comp:
        raise RuntimeError("no Terrain_i_j actors in this level")
    buf = EL.MeshBuf()
    stats = {}
    for name, pts, z, closed in outlines():
        s = {}
        EL.berm_mesh(pts, [z] * len(pts), T.h, EL.tile_index(META["tiles"]), buf=buf, stats=s, closed=closed)
        stats[name] = s
    dm = EL.finish_mesh(buf.to_dynamic_mesh())
    sm, how = EL.write_static_mesh(dm, "/Game/McGregor/Meshes/SM_MG_KitPadBerms", EL.terrain_materials(META["tiles"]), True)
    for a in EAS.get_all_level_actors():
        if a.get_actor_label() == "Edge_KitPadBerms":
            EAS.destroy_actor(a)
    a = EAS.spawn_actor_from_object(sm, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    a.set_actor_label("Edge_KitPadBerms")
    a.set_folder_path("McGregor/Edges")
    a.tags = ["MG_Generated", "MG_Edge", "NoWallRide"]
    a.static_mesh_component.set_editor_property("cast_shadow", False)
    a.static_mesh_component.set_collision_profile_name("BlockAll")
    log("build", {"mesh": how, "tris": buf.ntris(), "terrain_traces": T.n, "material_ids": str(getattr(buf, "mat_check", None)), "pads": stats})


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
