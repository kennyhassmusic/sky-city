"""Build Sky City's street surfaces in Unreal from Saved/Streets/street_data.json (see build_street_data.py).

  roads    every drivable street as a ribbon at its real curb-to-curb width (lanes from OpenStreetMap), unioned
  blocks   land minus roads, convex corners rounded into kerb returns (3 m), raised 15 cm with kerb faces
  ground   the existing Ground mesh becomes the asphalt road surface (z = 0)
  overlays grass (parks, parkway strips), gravel (lots, rail ballast), parking lots, alleys, plazas, park paths
  markings lane lines (solid / dashed, white / yellow), continental crosswalks and stop bars, 2 cm above asphalt
  bridges  decks over water with concrete parapets
All of it is cut into 600 m tiles (one actor per tile per layer) so the renderer can cull it; none of it casts
shadows. The old ribbon roads (Roads_*) and the flat park overlay are hidden, not deleted.
Materials: one master (M_StreetSurface) with instances per surface; textures plug into the instances later.

Run in the editor (PIE off):  py Scripts/streets/build_streets_ue.py
Writes Saved/MCPScripts/out_streets.json as it goes.
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
OUT = ROOT + "/Saved/MCPScripts/out_streets.json"
D = json.load(open(ROOT + "/Saved/Streets/street_data.json"))
PLAN = json.load(open(ROOT + "/Saved/Mashup/plan_v3.json"))
MESH_DIR = "/Game/City/Street/Meshes"
MAT_DIR = "/Game/City/Street/Materials"
TAG = "SC_Streets"
TILE = 60000.0           # cm
KERB_H = 15.0            # cm
KERB_R = 300.0           # cm, kerb return radius at corners
Z_OVER = {"grass": 16.0, "gravel": 16.3, "parking": 16.6, "alley": 16.9, "plaza": 16.9, "path": 17.2}
Z_PAINT = 2.0

PL = unreal.GeometryScript_PolygonList
PP = unreal.GeometryScript_PolyPath
SP = unreal.GeometryScript_SimplePolygon
PR = unreal.GeometryScript_Primitives
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
V2 = unreal.Vector2D
out = {"stage": None, "log": []}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def ue(p):
    return V2(p[1] * 100.0, p[0] * 100.0)


def poly(points_ue):
    return SP.conv_array_of_vector2d_to_geometry_script_simple_polygon(points_ue)


def plist(polys):
    return PL.create_polygon_list_from_simple_polygons(polys)


def ccw(pts):
    a = 0.0
    for i in range(len(pts)):
        p, q = pts[i], pts[(i + 1) % len(pts)]
        a += p.x * q.y - q.x * p.y
    return pts if a > 0 else pts[::-1]


def path_offset(paths, half_width, end="butt", join="round"):
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


def morph_open(pl, d):
    po = unreal.GeometryScriptPolygonOffsetOptions()
    po.set_editor_property("join_type", unreal.GeometryScriptPolyOffsetJoinType.ROUND)
    r = PL.polygons_morphology_open(pl, po, d)
    return r[0] if isinstance(r, tuple) else r


def union_all(lists):
    lists = [l for l in lists if l is not None and PL.get_polygon_count(l) > 0]
    if not lists:
        return None
    acc = lists[0]
    for l in lists[1:]:
        r = PL.append_polygon_list(acc, l)   # Python hands ref params back instead of editing them
        acc = r[0] if isinstance(r, tuple) else (r if r is not None else acc)
    return PL.polygons_union(acc, True)


def count(pl):
    return 0 if pl is None else PL.get_polygon_count(pl)


def rings_of(pl):
    """All rings (outer and holes) as lists of Vector2D."""
    res = []
    for i in range(count(pl)):
        v = PL.get_polygon_vertices(pl, i, -1)
        res.append(list(v[0] if isinstance(v, tuple) else v))
        h = PL.get_polygon_hole_count(pl, i)
        for j in range(h[0] if isinstance(h, tuple) else h):
            v = PL.get_polygon_vertices(pl, i, j)
            res.append(list(v[0] if isinstance(v, tuple) else v))
    return res


# ---------------------------------------------------------------- materials
def tex(path):
    return EAL.load_asset(path)


WHITE_LINEAR = "/Game/City/Street/Textures/Kit/T_WhiteLinear"


def white_linear():
    """A 4x4 white texture stored linear (not sRGB): the default for packed AO/roughness/metal inputs."""
    if not EAL.does_asset_exist(WHITE_LINEAR):
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", ROOT + "/SourceArt/StreetKit/textures/T_WhiteLinear.png")
        t.set_editor_property("destination_path", "/Game/City/Street/Textures/Kit")
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    tx = EAL.load_asset(WHITE_LINEAR)
    tx.set_editor_property("srgb", False)
    tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
    EAL.save_loaded_asset(tx)
    return tx


def master_material(rebuild=False):
    path = f"{MAT_DIR}/M_StreetSurface"
    MEL = unreal.MaterialEditingLibrary
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        if not rebuild:
            return m
        MEL.delete_all_material_expressions(m)     # rebuilt in place, so the instances keep their parent
    else:
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_StreetSurface", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    white_linear()

    def X(cls, x, y):
        return MEL.create_material_expression(m, cls, x, y)

    def scalar(name, v, x, y):
        e = X(unreal.MaterialExpressionScalarParameter, x, y)
        e.set_editor_property("parameter_name", name)
        e.set_editor_property("default_value", v)
        return e

    # UVs: world-aligned (top surfaces) or mesh UVs in metres (kerb faces, props)
    wp = X(unreal.MaterialExpressionWorldPosition, -1800, -200)
    wmask = X(unreal.MaterialExpressionComponentMask, -1600, -200)
    wmask.set_editor_property("r", True)
    wmask.set_editor_property("g", True)
    MEL.connect_material_expressions(wp, "", wmask, "")
    cm = X(unreal.MaterialExpressionConstant, -1600, -100)
    cm.set_editor_property("r", 0.01)
    wm = X(unreal.MaterialExpressionMultiply, -1400, -200)
    MEL.connect_material_expressions(wmask, "", wm, "A")
    MEL.connect_material_expressions(cm, "", wm, "B")
    tc = X(unreal.MaterialExpressionTextureCoordinate, -1600, 0)
    sw = X(unreal.MaterialExpressionStaticSwitchParameter, -1200, -100)
    sw.set_editor_property("parameter_name", "WorldAligned")
    sw.set_editor_property("default_value", True)
    MEL.connect_material_expressions(wm, "", sw, "True")
    MEL.connect_material_expressions(tc, "", sw, "False")
    tile = scalar("TileSize", 2.0, -1200, 50)
    uv = X(unreal.MaterialExpressionDivide, -1000, -100)
    MEL.connect_material_expressions(sw, "", uv, "A")
    MEL.connect_material_expressions(tile, "", uv, "B")
    # textures
    def tparam(name, default, sampler, x, y):
        e = X(unreal.MaterialExpressionTextureSampleParameter2D, x, y)
        e.set_editor_property("parameter_name", name)
        e.set_editor_property("texture", tex(default))
        e.set_editor_property("sampler_type", sampler)
        MEL.connect_material_expressions(uv, "", e, "UVs")
        return e
    bc = tparam("BaseColorTex", "/Engine/EngineResources/WhiteSquareTexture", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR, -700, -400)
    nt = tparam("NormalTex", "/Engine/EngineMaterials/FlatNormal", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL, -700, 100)
    arm = tparam("ARMTex", WHITE_LINEAR, unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR, -700, 400)
    # macro variation: the same base colour sampled 7x larger, as a brightness wobble that hides tiling
    uvm = X(unreal.MaterialExpressionMultiply, -900, -650)
    cmv = X(unreal.MaterialExpressionConstant, -1000, -600)
    cmv.set_editor_property("r", 0.137)
    MEL.connect_material_expressions(uv, "", uvm, "A")
    MEL.connect_material_expressions(cmv, "", uvm, "B")
    bc2 = X(unreal.MaterialExpressionTextureSampleParameter2D, -700, -700)
    bc2.set_editor_property("parameter_name", "BaseColorTex")
    bc2.set_editor_property("texture", tex("/Engine/EngineResources/WhiteSquareTexture"))
    MEL.connect_material_expressions(uvm, "", bc2, "UVs")
    lum = X(unreal.MaterialExpressionDotProduct, -450, -700)
    lw = X(unreal.MaterialExpressionConstant3Vector, -600, -800)
    lw.set_editor_property("constant", unreal.LinearColor(0.6, 0.6, 0.6, 0))
    MEL.connect_material_expressions(bc2, "RGB", lum, "A")
    MEL.connect_material_expressions(lw, "", lum, "B")
    macro_amt = scalar("MacroVariation", 0.35, -450, -850)
    one = X(unreal.MaterialExpressionConstant, -450, -600)
    one.set_editor_property("r", 1.0)
    macro = X(unreal.MaterialExpressionLinearInterpolate, -250, -700)
    MEL.connect_material_expressions(one, "", macro, "A")
    MEL.connect_material_expressions(lum, "", macro, "B")
    MEL.connect_material_expressions(macro_amt, "", macro, "Alpha")
    tint = X(unreal.MaterialExpressionVectorParameter, -450, -300)
    tint.set_editor_property("parameter_name", "Tint")
    tint.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))
    m1 = X(unreal.MaterialExpressionMultiply, -250, -400)
    MEL.connect_material_expressions(bc, "RGB", m1, "A")
    MEL.connect_material_expressions(tint, "", m1, "B")
    m2 = X(unreal.MaterialExpressionMultiply, -50, -450)
    MEL.connect_material_expressions(m1, "", m2, "A")
    MEL.connect_material_expressions(macro, "", m2, "B")
    MEL.connect_material_property(m2, "", unreal.MaterialProperty.MP_BASE_COLOR)
    # roughness / metallic / AO from ARM
    rs = scalar("RoughnessScale", 0.85, -450, 350)
    rmul = X(unreal.MaterialExpressionMultiply, -250, 400)
    MEL.connect_material_expressions(arm, "G", rmul, "A")
    MEL.connect_material_expressions(rs, "", rmul, "B")
    MEL.connect_material_property(rmul, "", unreal.MaterialProperty.MP_ROUGHNESS)
    ms = scalar("MetallicScale", 0.0, -450, 550)
    mmul = X(unreal.MaterialExpressionMultiply, -250, 550)
    MEL.connect_material_expressions(arm, "B", mmul, "A")
    MEL.connect_material_expressions(ms, "", mmul, "B")
    MEL.connect_material_property(mmul, "", unreal.MaterialProperty.MP_METALLIC)
    MEL.connect_material_property(arm, "R", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    # normal strength
    flat = X(unreal.MaterialExpressionConstant3Vector, -450, 100)
    flat.set_editor_property("constant", unreal.LinearColor(0, 0, 1, 0))
    ns = scalar("NormalStrength", 1.0, -450, 250)
    nl = X(unreal.MaterialExpressionLinearInterpolate, -250, 150)
    MEL.connect_material_expressions(flat, "", nl, "A")
    MEL.connect_material_expressions(nt, "RGB", nl, "B")
    MEL.connect_material_expressions(ns, "", nl, "Alpha")
    MEL.connect_material_property(nl, "", unreal.MaterialProperty.MP_NORMAL)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


SURFACES = {   # name: (tint, roughness, tile metres, world aligned)
    "Asphalt": ((0.11, 0.11, 0.115), 0.9, 4.0, True),
    "AsphaltWorn": ((0.16, 0.155, 0.15), 0.92, 4.0, True),
    "Sidewalk": ((0.52, 0.51, 0.49), 0.85, 3.0, True),
    "Kerb": ((0.58, 0.57, 0.55), 0.8, 1.5, False),
    "Grass": ((0.13, 0.25, 0.07), 0.95, 3.0, True),
    "Gravel": ((0.35, 0.33, 0.30), 0.95, 2.5, True),
    "Paving": ((0.47, 0.42, 0.38), 0.85, 2.5, True),
    "Path": ((0.45, 0.44, 0.42), 0.85, 2.5, True),
    "PaintWhite": ((0.80, 0.80, 0.78), 0.6, 1.5, True),
    "PaintYellow": ((0.80, 0.58, 0.08), 0.6, 1.5, True),
    "BridgeConcrete": ((0.45, 0.44, 0.42), 0.85, 2.0, False),
}


def material_instances():
    master = master_material()
    MEL = unreal.MaterialEditingLibrary
    mis = {}
    for name, (tint, rough, tile, world) in SURFACES.items():
        path = f"{MAT_DIR}/MI_{name}"
        if EAL.does_asset_exist(path):
            mi = EAL.load_asset(path)
        else:
            mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(f"MI_{name}", MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
            mi.set_editor_property("parent", master)
            MEL.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(*tint, 1))
            MEL.set_material_instance_scalar_parameter_value(mi, "RoughnessScale", rough)
            MEL.set_material_instance_scalar_parameter_value(mi, "TileSize", tile)
            MEL.set_material_instance_static_switch_parameter_value(mi, "WorldAligned", world)
            MEL.update_material_instance(mi)
            EAL.save_loaded_asset(mi)
        mis[name] = mi
    return mis


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
    for i, m in enumerate(mats):
        sm.set_material(i, m)
    EAL.save_loaded_asset(sm)
    return sm


def place(sm, label, folder, collide):
    a = EAS.spawn_actor_from_object(sm, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    a.set_actor_label(label)
    a.set_folder_path(f"City/Streets/{folder}")
    a.tags = [TAG, "City_Generated"]
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
    """Vertical quads for a list of ((x0,y0),(x1,y1)) segments; outward = right of the direction."""
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


def finish(dm, world_uv=True):
    unreal.GeometryScript_Normals.set_per_face_normals(dm)
    unreal.GeometryScript_UVs.set_mesh_u_vs_from_box_projection(dm, 0, unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(100, 100, 100)), unreal.GeometryScriptMeshSelection())


def up_facing(dm):
    """Triangulation winding check: flip if the first triangle points down."""
    if tris(dm) == 0:
        return
    n = unreal.GeometryScript_MeshQueries.get_triangle_face_normal(dm, 0)
    n = n[0] if isinstance(n, tuple) else n
    if n.z < 0:
        unreal.GeometryScript_Normals.flip_normals(dm)


# ---------------------------------------------------------------- build stages
S = {}
x0, y0, x1, y1 = PLAN["bounds"]
UX0, UX1, UY0, UY1 = y0 * 100, y1 * 100, x0 * 100, x1 * 100
TILES = [(i, j) for i in range(int(math.ceil((UX1 - UX0) / TILE))) for j in range(int(math.ceil((UY1 - UY0) / TILE)))]


def tile_rect(i, j):
    a, b = UX0 + i * TILE, UY0 + j * TILE
    return plist([poly([V2(a, b), V2(a + TILE, b), V2(a + TILE, b + TILE), V2(a, b + TILE)])])


def stage_setup():
    S["mis"] = material_instances()
    old = 0
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags]:
            EAS.destroy_actor(a)
            old += 1
    log("removed_old", old)
    # hide the old ribbon roads and flat park overlay (kept, just switched off)
    hidden = []
    for a in EAS.get_all_level_actors():
        if a.get_actor_label() in ("Roads_minor", "Roads_mid", "Roads_major", "Roads_highway", "Parks"):
            a.modify()
            a.set_actor_hidden_in_game(True)
            a.set_is_temporarily_hidden_in_editor(True)
            a.set_actor_enable_collision(False)
            smc = a.get_component_by_class(unreal.StaticMeshComponent)
            if smc:
                smc.modify()
                smc.set_editor_property("visible", False)
                smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            hidden.append(a.get_actor_label())
        if a.get_actor_label() == "Ground":
            a.static_mesh_component.set_material(0, S["mis"]["Asphalt"])
            a.static_mesh_component.set_editor_property("cast_shadow", False)
    log("hidden_old", hidden)


def stage_polygons():
    t0 = time.time()
    by_w = {}
    for r in D["roads"]:
        if r["cls"] not in ("highway", "major", "mid", "minor") or r["skip"] or r["elevated"]:
            continue
        by_w.setdefault(round(r["width"] * 2) / 2, []).append([ue(p) for p in r["pts"]])
    parts = [path_offset(paths, w * 50.0, end="round") for w, paths in by_w.items()]
    S["roads"] = union_all(parts)
    water = plist([poly(ccw([ue(p) for p in ring])) for ring in PLAN["water"]["outer"] if len(ring) >= 3])
    S["water"] = PL.polygons_union(water, True)
    islands = [poly(ccw([ue(p) for p in ring])) for ring in PLAN["water"]["inner"] if len(ring) >= 3]
    box = plist([poly([V2(UX0, UY0), V2(UX1, UY0), V2(UX1, UY1), V2(UX0, UY1)])])
    land = PL.polygons_difference(box, S["water"])
    if islands:
        land = union_all([land, plist(islands)])
    S["land"] = land
    blocks = PL.polygons_difference(land, S["roads"])
    S["blocks"] = morph_open(blocks, KERB_R)
    S["water_land"] = PL.polygons_difference(S["water"], plist(islands)) if islands else S["water"]
    log("polygons", {"roads": count(S["roads"]), "blocks": count(S["blocks"]), "land": count(land), "water": count(S["water"]), "s": round(time.time() - t0, 1)})


def stage_overlay_polys():
    t0 = time.time()
    B = S["blocks"]

    def areas(key):
        ps = [poly(ccw([ue(p) for p in ring])) for ring in D["areas"].get(key, []) if len(ring) >= 3]
        return PL.polygons_union(plist(ps), True) if ps else None

    def paths(key):
        groups = {}
        for p in D["paths"][key]:
            groups.setdefault(p["w"], []).append([ue(q) for q in p["pts"]])
        return union_all([path_offset(v, w * 50.0, end="round") for w, v in groups.items()])

    # parkway strips: between 0.5 m and 2.3 m behind the kerb on residential streets
    pk = {}
    for r in D["roads"]:
        if r.get("parkway"):
            pk.setdefault(round(r["width"] * 2) / 2, []).append([ue(p) for p in r["pts"]])
    inner = union_all([path_offset(v, w * 50 + 50, end="butt") for w, v in pk.items()])
    outer = union_all([path_offset(v, w * 50 + 230, end="butt") for w, v in pk.items()])
    parkway = PL.polygons_difference(outer, inner) if inner and outer else None
    grass = union_all([areas("grass"), areas("pitch"), parkway])
    gravel = union_all([areas("gravel"), paths("ballast")])
    parking = areas("parking")
    alley = paths("alley")
    plaza = paths("plaza")
    path = paths("park_path")
    clip = lambda pl: PL.polygons_intersection(pl, B) if pl is not None and count(pl) else None
    S["over"] = {"grass": clip(grass), "gravel": clip(gravel), "parking": clip(parking), "alley": clip(alley), "plaza": clip(plaza), "path": clip(path)}
    # each layer owns its footprint: later layers punch holes in earlier ones, so nothing z-fights
    order = ["grass", "gravel", "parking", "alley", "plaza", "path"]
    for i, k in enumerate(order):
        for k2 in order[i + 1:]:
            if S["over"][k] is not None and S["over"][k2] is not None:
                S["over"][k] = PL.polygons_difference(S["over"][k], S["over"][k2])
    log("overlays", {k: count(v) for k, v in S["over"].items()} | {"s": round(time.time() - t0, 1)})


def stage_kerb_segments():
    t0 = time.time()
    segs = {}
    for ring in rings_of(S["blocks"]):
        n = len(ring)
        for k in range(n):
            a, b = ring[k], ring[(k + 1) % n]
            mx, my = (a.x + b.x) / 2, (a.y + b.y) / 2
            key = (int((mx - UX0) // TILE), int((my - UY0) // TILE))
            segs.setdefault(key, []).append(((a.x, a.y), (b.x, b.y)))
    S["kerbs"] = segs
    log("kerb_segments", {"n": sum(len(v) for v in segs.values()), "s": round(time.time() - t0, 1)})


def marking_polys():
    """Per tile: white and yellow paint polygon lists."""
    t0 = time.time()
    M = D["markings"]
    white, yellow = [], []
    for kind, half, dest in (("solid_white", 6.0, white), ("dash_white", 6.0, white), ("solid_yellow", 5.5, yellow)):
        lines = [[ue(p) for p in l] for l in M[kind]]
        for i in range(0, len(lines), 2000):
            pl = path_offset(lines[i:i + 2000], half, end="butt", join="miter")
            if pl is not None:
                dest.append(pl)
    bars = [poly(ccw([ue(p) for p in r])) for r in M["bars"]]
    for i in range(0, len(bars), 3000):
        white.append(plist(bars[i:i + 3000]))
    S["paint"] = {"white": union_all(white), "yellow": union_all(yellow)}
    log("paint", {"white": count(S["paint"]["white"]), "yellow": count(S["paint"]["yellow"]), "s": round(time.time() - t0, 1)})


def build_tile(i, j):
    mis = S["mis"]
    rect = tile_rect(i, j)
    made = {}
    # blocks: sidewalk top + kerb faces
    dm = unreal.DynamicMesh()
    bt = PL.polygons_intersection(S["blocks"], rect)
    triangulate_into(dm, bt, KERB_H, 0)
    up_facing(dm)
    walls_into(dm, S["kerbs"].get((i, j), []), -10.0, KERB_H + 10.0, 1)
    if tris(dm):
        finish(dm)
        sm = save_mesh(dm, f"SM_Blocks_{i}_{j}", [mis["Sidewalk"], mis["Kerb"]], True)
        place(sm, f"Blocks_{i}_{j}", "Blocks", True)
        made["blocks"] = tris(dm)
    # overlays
    dm = unreal.DynamicMesh()
    names = ["grass", "gravel", "parking", "alley", "plaza", "path"]
    for k, name in enumerate(names):
        pl = S["over"][name]
        if pl is not None and count(pl):
            triangulate_into(dm, PL.polygons_intersection(pl, rect), Z_OVER[name], k)
    up_facing(dm)
    if tris(dm):
        finish(dm)
        sm = save_mesh(dm, f"SM_Overlay_{i}_{j}", [mis["Grass"], mis["Gravel"], mis["AsphaltWorn"], mis["AsphaltWorn"], mis["Paving"], mis["Path"]], False)
        place(sm, f"Overlay_{i}_{j}", "Overlays", False)
        made["overlay"] = tris(dm)
    # paint
    dm = unreal.DynamicMesh()
    for k, name in enumerate(("white", "yellow")):
        pl = S["paint"][name]
        if pl is not None and count(pl):
            triangulate_into(dm, PL.polygons_intersection(pl, rect), Z_PAINT, k)
    up_facing(dm)
    if tris(dm):
        finish(dm)
        sm = save_mesh(dm, f"SM_Paint_{i}_{j}", [mis["PaintWhite"], mis["PaintYellow"]], False)
        place(sm, f"Paint_{i}_{j}", "Markings", False)
        made["paint"] = tris(dm)
    return made


def stage_bridges():
    mis = S["mis"]
    decks = PL.polygons_intersection(S["roads"], S["water_land"])
    dm = unreal.DynamicMesh()
    n = 0
    for ring in rings_of(decks):
        if len(ring) < 3:
            continue
        PR.append_simple_extrude_polygon(dm, tri_opts(0), unreal.Transform(unreal.Vector(0, 0, -120), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                         ccw(ring), 120.0, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        n += 1
    rail = PL.polygons_intersection(PL.polygons_difference(offset(S["roads"], 45.0), S["roads"]), S["water_land"])
    for ring in rings_of(rail):
        if len(ring) < 3:
            continue
        PR.append_simple_extrude_polygon(dm, tri_opts(1), unreal.Transform(unreal.Vector(0, 0, -120), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                         ccw(ring), 230.0, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
    if tris(dm):
        finish(dm)
        sm = save_mesh(dm, "SM_BridgeDecks", [mis["Asphalt"], mis["BridgeConcrete"]], True)
        a = place(sm, "BridgeDecks", "Bridges", True)
        a.tags = [TAG, "City_Generated", "NoWallRide"]
    log("bridges", {"decks": n, "tris": tris(dm)})


def stage_save():
    log("save_level", unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level())
    log("save_dirty", unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True))


QUEUE = [("setup", stage_setup), ("polygons", stage_polygons), ("overlay_polys", stage_overlay_polys),
         ("kerbs", stage_kerb_segments), ("paint", marking_polys)]
QUEUE += [(f"tile_{i}_{j}", (lambda i=i, j=j: out.setdefault("tiles", {}).update({f"{i}_{j}": build_tile(i, j)}))) for i, j in TILES]
QUEUE += [("bridges", stage_bridges), ("save", stage_save)]
_h = None
T0 = time.time()


BUSY = [False]


def tick(dt):
    # saving assets and compiling materials pump Slate, which would re-enter this callback mid-stage
    if BUSY[0]:
        return
    BUSY[0] = True
    try:
        if not QUEUE:
            unreal.unregister_slate_post_tick_callback(_h)
            log("done", round(time.time() - T0, 1))
            return
        import shutil, resource
        free_gb = shutil.disk_usage(os.path.expanduser("~")).free / 1e9
        if free_gb < 6.0:
            unreal.unregister_slate_post_tick_callback(_h)
            log("error", f"stopped: only {free_gb:.1f} GB free on disk")
            return
        name, fn = QUEUE.pop(0)
        out["stage"] = name
        t0 = time.time()
        fn()
        out.setdefault("timing", []).append([name, round(time.time() - t0, 1), round(free_gb, 1),
                                             round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 1)])
        log("stage", name)
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        log("error", traceback.format_exc())
    finally:
        BUSY[0] = False


_h = unreal.register_slate_post_tick_callback(tick)
