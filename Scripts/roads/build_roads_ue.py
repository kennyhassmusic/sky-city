"""Build Sky City's street surfaces in Unreal from the road network v2 (Saved/Roads/roadnet.json, Scripts/roads/roadnet.py).

The ground (z = 0) is the asphalt; everything that isn't roadway is a raised block (15 cm curb) whose top is split by
purpose, not left as one big paved platform. The 15 cm step is still a vertical face in this builder. The gutter pan
and the beveled curb live in Scripts/roads/profiles.py and in the SK_Curb_* kit meshes; this script keeps the step
until those meshes are imported and swapped in:
  sidewalk   the paved walk along every curb, at the width its street's rules give (downtown 4.6 m, else 3.8 m)
  parkway    the grass strip between curb and walk on non-downtown streets (street trees stand in it)
  grounds    everything behind the sidewalk (building setbacks, courtyards, medians): landscaped lawn, never paving
  park       the city's parks
plus the paint (lane lines, centre lines, parking lines, crosswalk and stop bars) and bridge decks over water.
The roadway is the union of the street ribbons (butt ends, no round caps), the curb-return junction polygons and the
joints where a street changes width. All of it is cut into 600 m tiles; nothing casts shadows. Old street surfaces
(tag SC_Streets) are removed.

Run in the editor (PIE off): py Scripts/roads/build_roads_ue.py
Writes Saved/MCPScripts/out_roads.json as it goes.
"""
import json, math, time, traceback, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_roads.json"
D = json.load(open(ROOT + "/Saved/Roads/roadnet.json"))
PLAN = json.load(open(ROOT + "/Saved/Mashup/plan_v3.json"))
MESH_DIR = "/Game/City/Roads/Meshes"
MAT_DIR = "/Game/City/Street/Materials"
TAG = "SC_Roads2"
OLD_TAG = "SC_Streets"
TILE = 60000.0
KERB_H = 15.0
Z_PAINT = 2.0
LINE_W = {"solid_white": 15.0, "dash_white": 15.0, "solid_white_thin": 10.0, "solid_yellow": 12.0, "dash_yellow": 12.0}

PL = unreal.GeometryScript_PolygonList
PP = unreal.GeometryScript_PolyPath
SP = unreal.GeometryScript_SimplePolygon
PR = unreal.GeometryScript_Primitives
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
V2 = unreal.Vector2D
out = {"stage": None}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def ue(p):
    return V2(p[1] * 100.0, p[0] * 100.0)


def ccw(pts):
    a = 0.0
    for i in range(len(pts)):
        p, q = pts[i], pts[(i + 1) % len(pts)]
        a += p.x * q.y - q.x * p.y
    return pts if a > 0 else pts[::-1]


def poly(points_ue):
    return SP.conv_array_of_vector2d_to_geometry_script_simple_polygon(points_ue)


def plist(polys):
    return PL.create_polygon_list_from_simple_polygons(polys)


def rings_to_pl(rings):
    ps = [poly(ccw([ue(p) for p in r])) for r in rings if r and len(r) >= 3]
    return plist(ps) if ps else None


def path_offset(paths, half_width, end="butt", join="miter"):
    oo = unreal.GeometryScriptOpenPathOffsetOptions()
    oo.set_editor_property("join_type", {"round": unreal.GeometryScriptPolyOffsetJoinType.ROUND, "miter": unreal.GeometryScriptPolyOffsetJoinType.MITER}[join])
    oo.set_editor_property("end_type", {"butt": unreal.GeometryScriptPathOffsetEndType.BUTT, "round": unreal.GeometryScriptPathOffsetEndType.ROUND}[end])
    pps = [PP.conv_array_of_vector2d_to_geometry_script_poly_path(p) for p in paths if len(p) >= 2]
    if not pps:
        return None
    r = PL.create_polygons_from_open_poly_paths_offset(pps, oo, half_width)
    return r[0] if isinstance(r, tuple) else r


def offset(pl, d):
    po = unreal.GeometryScriptPolygonOffsetOptions()
    po.set_editor_property("join_type", unreal.GeometryScriptPolyOffsetJoinType.ROUND)
    r = PL.polygons_offset(pl, po, d)
    return r[0] if isinstance(r, tuple) else r


def count(pl):
    return 0 if pl is None else PL.get_polygon_count(pl)


def union_all(lists):
    lists = [l for l in lists if l is not None and count(l) > 0]
    if not lists:
        return None
    acc = lists[0]
    for l in lists[1:]:
        r = PL.append_polygon_list(acc, l)
        acc = r[0] if isinstance(r, tuple) else (r if r is not None else acc)
    return PL.polygons_union(acc, True)


def chunked_union(rings, n=1500):
    parts = []
    for i in range(0, len(rings), n):
        pl = rings_to_pl(rings[i:i + n])
        if pl is not None:
            parts.append(PL.polygons_union(pl, True))
    return union_all(parts)


def diff(a, b):
    if a is None:
        return None
    if b is None or count(b) == 0:
        return a
    return PL.polygons_difference(a, b)


def inter(a, b):
    if a is None or b is None:
        return None
    return PL.polygons_intersection(a, b)


def rings_of(pl):
    res = []
    for i in range(count(pl)):
        v = PL.get_polygon_vertices(pl, i, -1)
        res.append(list(v[0] if isinstance(v, tuple) else v))
        h = PL.get_polygon_hole_count(pl, i)
        for j in range(h[0] if isinstance(h, tuple) else h):
            v = PL.get_polygon_vertices(pl, i, j)
            res.append(list(v[0] if isinstance(v, tuple) else v))
    return res


# ---------------------------------------------------------------- materials (the street MIs from the first pass)
def mis():
    m = {}
    for n in ("Asphalt", "Sidewalk", "Kerb", "Grass", "Paving", "Path", "PaintWhite", "PaintYellow", "BridgeConcrete", "Gravel"):
        m[n] = EAL.load_asset(f"{MAT_DIR}/MI_{n}")
    # building grounds and medians: the park grass (textured) with a lighter, fresher tint
    lawn = f"{MAT_DIR}/MI_Lawn"
    if EAL.does_asset_exist(lawn):
        EAL.delete_asset(lawn)
    mi = EAL.duplicate_asset(f"{MAT_DIR}/MI_Grass", lawn)
    unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(0.15, 0.27, 0.08, 1))
    unreal.MaterialEditingLibrary.update_material_instance(mi)
    EAL.save_loaded_asset(mi)
    m["Lawn"] = EAL.load_asset(lawn)
    return m


# ---------------------------------------------------------------- mesh helpers
def save_mesh(dm, name, mats, collide):
    path = f"{MESH_DIR}/{name}"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
    for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", True), ("enable_nanite", False), ("enable_collision", collide)):
        try:
            opts.set_editor_property(k, v)
        except Exception:
            pass
    res = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, opts)
    sm = res[0] if isinstance(res, (tuple, list)) else res
    bs = sm.get_editor_property("body_setup")
    if bs:
        bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if collide else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
    for i, mm in enumerate(mats):
        sm.set_material(i, mm)
    EAL.save_loaded_asset(sm)
    return sm


def place(sm, label, folder, collide, extra_tags=()):
    a = EAS.spawn_actor_from_object(sm, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    a.set_actor_label(label)
    a.set_folder_path(f"City/Roads/{folder}")
    a.tags = [TAG, "City_Generated"] + list(extra_tags)
    a.set_editor_property("is_spatially_loaded", False)
    c = a.static_mesh_component
    c.set_editor_property("cast_shadow", False)
    c.set_collision_profile_name("BlockAll" if collide else "NoCollision")
    return a


def tris(dm):
    return unreal.GeometryScript_MeshQueries.get_num_triangle_i_ds(dm)


def tri_opts(mat_id):
    o = unreal.GeometryScriptPrimitiveOptions()
    o.set_editor_property("material_id", mat_id)
    return o


def triangulate_into(dm, pl, z, mat_id):
    if pl is None or count(pl) == 0:
        return
    PR.append_polygon_list_triangulation(dm, tri_opts(mat_id), unreal.Transform(unreal.Vector(0, 0, z), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                         pl, unreal.GeometryScriptPolygonsTriangulationOptions())


def walls_into(dm, segs, z0, h, mat_id):
    if not segs:
        return
    LU = unreal.GeometryScript_List
    verts, trisl = [], []
    for (a, b) in segs:
        k = len(verts)
        verts += [unreal.Vector(a[0], a[1], z0), unreal.Vector(b[0], b[1], z0), unreal.Vector(b[0], b[1], z0 + h), unreal.Vector(a[0], a[1], z0 + h)]
        trisl += [unreal.IntVector(k, k + 2, k + 1), unreal.IntVector(k, k + 3, k + 2)]
    tmp = unreal.DynamicMesh()
    vl = LU.convert_array_to_vector_list(verts)
    tl = LU.convert_array_to_triangle_list(trisl)
    unreal.GeometryScript_MeshEdits.add_vertices_to_mesh(tmp, vl[0] if isinstance(vl, tuple) else vl)
    unreal.GeometryScript_MeshEdits.add_triangles_to_mesh(tmp, tl[0] if isinstance(tl, tuple) else tl, 0)
    unreal.GeometryScript_Materials.enable_material_i_ds(tmp)
    unreal.GeometryScript_Materials.remap_material_i_ds(tmp, 0, mat_id)
    unreal.GeometryScript_MeshEdits.append_mesh(dm, tmp, unreal.Transform())


def finish(dm):
    unreal.GeometryScript_Normals.set_per_face_normals(dm)
    unreal.GeometryScript_UVs.set_mesh_u_vs_from_box_projection(dm, 0, unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(100, 100, 100)), unreal.GeometryScriptMeshSelection())


def up_facing(dm):
    if tris(dm) == 0:
        return
    n = unreal.GeometryScript_MeshQueries.get_triangle_face_normal(dm, 0)
    n = n[0] if isinstance(n, tuple) else n
    if n.z < 0:
        unreal.GeometryScript_Normals.flip_normals(dm)


# ---------------------------------------------------------------- stages
S = {}
x0, y0, x1, y1 = PLAN["bounds"]
UX0, UX1, UY0, UY1 = y0 * 100, y1 * 100, x0 * 100, x1 * 100
TILES = [(i, j) for i in range(int(math.ceil((UX1 - UX0) / TILE))) for j in range(int(math.ceil((UY1 - UY0) / TILE)))]


def tile_rect(i, j):
    a, b = UX0 + i * TILE, UY0 + j * TILE
    return plist([poly([V2(a, b), V2(a + TILE, b), V2(a + TILE, b + TILE), V2(a, b + TILE)])])


def stage_setup():
    S["mis"] = mis()
    gone = 0
    for a in EAS.get_all_level_actors():
        tags = [str(t) for t in a.tags]
        if TAG in tags or OLD_TAG in tags:
            EAS.destroy_actor(a)
            gone += 1
    for a in EAS.get_all_level_actors():
        if a.get_actor_label() == "Ground":
            a.static_mesh_component.set_material(0, S["mis"]["Asphalt"])
            a.static_mesh_component.set_editor_property("cast_shadow", False)
    log("removed_old", gone)


def stage_polygons():
    t0 = time.time()
    rings = [e["ribbon"] for e in D["edges"] if e["ribbon"]] + [j["ring"] for j in D["junctions"]] + D["joints"]
    S["roads"] = chunked_union(rings)
    water = rings_to_pl(PLAN["water"]["outer"])
    S["water"] = PL.polygons_union(water, True)
    islands = rings_to_pl(PLAN["water"]["inner"])
    box = plist([poly([V2(UX0, UY0), V2(UX1, UY0), V2(UX1, UY1), V2(UX0, UY1)])])
    land = PL.polygons_difference(box, S["water"])
    if islands is not None:
        land = union_all([land, islands])
    S["land"] = land
    raw = diff(land, S["roads"])
    S["blocks"], dropped = clean_blocks(raw)
    S["water_land"] = diff(S["water"], islands)
    log("polygons", {"roads": count(S["roads"]), "blocks_raw": count(raw), "blocks": count(S["blocks"]), "islands_dropped": dropped,
                     "s": round(time.time() - t0, 1)})


# Curb slivers: where a junction ring, a street ribbon and a joint almost meet, or two carriageways run a hand's width
# apart, "land minus roads" leaves raised 15 cm chips and strips in the asphalt (the 20 Oct audit counted ~300 islands
# under 25 m2 and ~130 strips under 2 m wide). A car catches on them. An opening (shrink then grow by OPEN_CM, round
# joins) removes every part of a block narrower than 2 x OPEN_CM, and islands left smaller than MIN_ISLAND_M2 go too;
# both become asphalt. Real traffic islands and medians (wider than 1.4 m, bigger than 12 m2) stay.
OPEN_CM = 70.0
MIN_ISLAND_M2 = 12.0


def ring_area_cm2(vs):
    a = 0.0
    for i in range(len(vs)):
        p, q = vs[i], vs[(i + 1) % len(vs)]
        a += p.x * q.y - q.x * p.y
    return abs(a) / 2


def clean_blocks(B):
    if B is None or count(B) == 0:
        return B, 0
    opened = offset(offset(B, -OPEN_CM), OPEN_CM)
    small = []
    for i in range(count(opened)):
        v = PL.get_polygon_vertices(opened, i, -1)
        vs = list(v[0] if isinstance(v, tuple) else v)
        if len(vs) >= 3 and ring_area_cm2(vs) < MIN_ISLAND_M2 * 1e4:
            small.append(poly(ccw(vs)))
    if small:
        opened = diff(opened, plist(small))
    return opened, len(small)


def stage_zones():
    """Split the blocks by purpose: sidewalk, parkway grass, park, and the grounds behind the sidewalk."""
    t0 = time.time()
    walk_e = chunked_union(D["walk"])
    by_sw = {}
    for j in D["junctions"]:
        if j["sw"] > 0:
            by_sw.setdefault(j["sw"], []).append(j["ring"])
    walk_j = union_all([offset(chunked_union(rs), sw * 100.0) for sw, rs in by_sw.items()])
    zone = union_all([walk_e, walk_j])
    B = S["blocks"]
    side = inter(B, zone)
    park = inter(B, PL.polygons_union(rings_to_pl(PLAN["parks"]), True)) if PLAN["parks"] else None
    parkway = inter(side, chunked_union(D["parkway"])) if D["parkway"] else None
    parkway = diff(parkway, park)
    S["z"] = {
        "sidewalk": diff(side, parkway),
        "parkway": parkway,
        "park": diff(park, side),
        "grounds": diff(diff(B, zone), park),
    }
    log("zones", {k: count(v) for k, v in S["z"].items()} | {"s": round(time.time() - t0, 1)})


def stage_kerbs():
    t0 = time.time()
    segs = {}
    # what was actually built, for the audit (Scripts/roads/audit_roads.py checks it for curb slivers): every block
    # outline and hole, plan metres
    json.dump([[[round(v.y / 100.0, 2), round(v.x / 100.0, 2)] for v in ring] for ring in rings_of(S["blocks"])],
              open(ROOT + "/Saved/Roads/blocks_built.json", "w"), separators=(",", ":"))
    for ring in rings_of(S["blocks"]):
        n = len(ring)
        for k in range(n):
            a, b = ring[k], ring[(k + 1) % n]
            key = (int(((a.x + b.x) / 2 - UX0) // TILE), int(((a.y + b.y) / 2 - UY0) // TILE))
            segs.setdefault(key, []).append(((a.x, a.y), (b.x, b.y)))
    S["kerbs"] = segs
    log("kerbs", {"n": sum(len(v) for v in segs.values()), "s": round(time.time() - t0, 1)})


def stage_paint():
    t0 = time.time()
    M = D["markings"]
    white, yellow = [], []
    for kind, dest in (("solid_white", white), ("dash_white", white), ("solid_white_thin", white), ("solid_yellow", yellow), ("dash_yellow", yellow)):
        lines = [[ue(p) for p in l] for l in M[kind]]
        for i in range(0, len(lines), 2000):
            pl = path_offset(lines[i:i + 2000], LINE_W[kind] / 2)
            if pl is not None:
                dest.append(pl)
    bars = [poly(ccw([ue(p) for p in r])) for r in M["bars"]]
    for i in range(0, len(bars), 3000):
        white.append(plist(bars[i:i + 3000]))
    S["paint"] = {"white": union_all(white), "yellow": union_all(yellow)}
    log("paint", {"white": count(S["paint"]["white"]), "yellow": count(S["paint"]["yellow"]), "s": round(time.time() - t0, 1)})


ZONE_ORDER = ["sidewalk", "parkway", "grounds", "park"]


def build_tile(i, j):
    m = S["mis"]
    rect = tile_rect(i, j)
    made = {}
    dm = unreal.DynamicMesh()
    for k, name in enumerate(ZONE_ORDER):
        triangulate_into(dm, inter(S["z"][name], rect), KERB_H, k)
    up_facing(dm)
    walls_into(dm, S["kerbs"].get((i, j), []), -10.0, KERB_H + 10.0, 4)
    if tris(dm):
        finish(dm)
        sm = save_mesh(dm, f"SM_R2Blocks_{i}_{j}", [m["Sidewalk"], m["Grass"], m["Lawn"], m["Grass"], m["Kerb"]], True)
        place(sm, f"R2Blocks_{i}_{j}", "Blocks", True)
        made["blocks"] = tris(dm)
    dm = unreal.DynamicMesh()
    for k, name in enumerate(("white", "yellow")):
        pl = S["paint"][name]
        if pl is not None and count(pl):
            triangulate_into(dm, inter(pl, rect), Z_PAINT, k)
    up_facing(dm)
    if tris(dm):
        finish(dm)
        sm = save_mesh(dm, f"SM_R2Paint_{i}_{j}", [m["PaintWhite"], m["PaintYellow"]], False)
        place(sm, f"R2Paint_{i}_{j}", "Markings", False)
        made["paint"] = tris(dm)
    return made


def stage_bridges():
    m = S["mis"]
    decks = inter(S["roads"], S["water_land"])
    # twin bridges a few metres apart become one deck (Columbus Drive's two decks left 5 m of open water between them and
    # the car dropped into it at a bridgehead, playtest-chicago 21 Oct): a closing (grow 3 m, shrink 3 m) fills gaps under
    # 6 m; the railings along each carriageway's inner edge then stand on the deck as a median
    if decks is not None and count(decks):
        closed = offset(offset(decks, 300.0), -300.0)
        if closed is not None and count(closed):
            decks = inter(closed, S["water_land"])
    dm = unreal.DynamicMesh()
    n = 0
    for ring in rings_of(decks):
        if len(ring) < 3:
            continue
        PR.append_simple_extrude_polygon(dm, tri_opts(0), unreal.Transform(unreal.Vector(0, 0, -120), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                         ccw(ring), 120.0, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        n += 1
    rail = inter(diff(offset(S["roads"], 45.0), S["roads"]), S["water_land"])
    for ring in rings_of(rail):
        if len(ring) < 3:
            continue
        PR.append_simple_extrude_polygon(dm, tri_opts(1), unreal.Transform(unreal.Vector(0, 0, -120), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                         ccw(ring), 230.0, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
    if tris(dm):
        finish(dm)
        sm = save_mesh(dm, "SM_R2BridgeDecks", [m["Asphalt"], m["BridgeConcrete"]], True)
        place(sm, "R2BridgeDecks", "Bridges", True, ("NoWallRide",))
    log("bridges", {"decks": n, "tris": tris(dm)})


def stage_save():
    log("save_level", unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level())
    log("save_dirty", unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True))


QUEUE = [("setup", stage_setup), ("polygons", stage_polygons), ("zones", stage_zones), ("kerbs", stage_kerbs), ("paint", stage_paint)]
QUEUE += [(f"tile_{i}_{j}", (lambda i=i, j=j: out.setdefault("tiles", {}).update({f"{i}_{j}": build_tile(i, j)}))) for i, j in TILES]
QUEUE += [("bridges", stage_bridges), ("save", stage_save)]
_h = None
T0 = time.time()
BUSY = [False]


def tick(dt):
    if BUSY[0]:
        return
    BUSY[0] = True
    try:
        if not QUEUE:
            unreal.unregister_slate_post_tick_callback(_h)
            log("done", round(time.time() - T0, 1))
            return
        import shutil
        free_gb = shutil.disk_usage(os.path.expanduser("~")).free / 1e9
        if free_gb < 6.0:
            unreal.unregister_slate_post_tick_callback(_h)
            log("error", f"stopped: only {free_gb:.1f} GB free on disk")
            return
        name, fn = QUEUE.pop(0)
        out["stage"] = name
        t0 = time.time()
        fn()
        out.setdefault("timing", []).append([name, round(time.time() - t0, 1), round(free_gb, 1)])
        log("stage", name)
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        log("error", traceback.format_exc())
    finally:
        BUSY[0] = False


_h = unreal.register_slate_post_tick_callback(tick)
