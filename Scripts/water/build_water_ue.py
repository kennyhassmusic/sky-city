"""Lane 9: build seed 7's river (Longcut) and a demo pond two ways in this copy of the drive project, then save.

Headless (UnrealEditor-Cmd ... -ExecutePythonScript=<this>), on /Game/Maps/GenCity_Seed7 of THIS project copy
(SkyCity-water, branch gen/water-plugin; lane 7's level in SkyCity-drive is not touched). Saved as
/Game/Maps/GenCity_Seed7_Water.

Shared (tag lane9_shared): the ground slab replaced by the slab minus the river and the pond (our ground cut), the
riverbed and banks (channel), the pond bowl, the park lawn around the pond. Old flat water (Water_*) removed.
A (tag lane9_A): Unreal Water plugin: a WaterZone, a WaterBodyRiver on the centreline spline (width and depth per
  point), a WaterBodyLake on the pond outline. Plugin default materials (Epic content, test copy only).
B (tag lane9_B): our own water: river and lake surface meshes with M_L9_Water (Single Layer Water shading, flow-
  mapped normals from a code-made texture, shore foam, lake waves), bed material M_L9_Bed.
Writes Saved/Water/build_status.json.
"""
import json
import os
import sys
import time
import traceback

import unreal

ROOT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")
HERE = os.path.join(ROOT, "Scripts", "water")
sys.path.insert(0, HERE)
import water_geo as G  # noqa: E402

PLAN = json.load(open(os.path.join(ROOT, "Saved", "Water", "plan.json")))
SRC_LEVEL = "/Game/Maps/GenCity_Seed7"
OUT_LEVEL = "/Game/Maps/GenCity_Seed7_Water"
DEST = "/Game/Water/Lane9"
GLB_DIR = os.path.join(ROOT, "Saved", "Water", "glb")
TEX_DIR = os.path.join(ROOT, "Saved", "Water", "tex")
STATUS = os.path.join(ROOT, "Saved", "Water", "build_status.json")
os.makedirs(GLB_DIR, exist_ok=True)

lib = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
st = {"t0": time.time(), "steps": {}, "probe": {}, "errors": []}


def save_status():
    st["secs"] = round(time.time() - st["t0"], 1)
    keep = {k: v for k, v in st.items() if k not in ("rows", "slab_material", "park_ground")}
    with open(STATUS, "w") as h:
        json.dump(keep, h, indent=1, sort_keys=True, default=str)


def step(name):
    def deco(fn):
        def run(*a, **k):
            t = time.time()
            try:
                out = fn(*a, **k)
                st["steps"][name] = {"ok": True, "secs": round(time.time() - t, 1), "out": out}
                return out
            except Exception:
                st["steps"][name] = {"ok": False, "secs": round(time.time() - t, 1), "error": traceback.format_exc()}
                unreal.log_error("LANE9 step %s failed\n%s" % (name, traceback.format_exc()))
                return None
            finally:
                save_status()
        return run
    return deco


def ue(p, z=None):
    """plan (x, y[, z]) metres → UE Vector cm."""
    zz = p[2] if z is None and len(p) > 2 else (z or 0.0)
    return unreal.Vector(p[1] * 100.0, p[0] * 100.0, zz * 100.0)


def tag(actor, name, label, folder):
    actor.set_actor_label(label)
    actor.set_folder_path("Lane9Water/" + folder)
    actor.set_editor_property("tags", [unreal.Name(name)])


def import_glb(mesh, name):
    src = os.path.join(GLB_DIR, name + ".glb")
    with open(src, "wb") as h:
        h.write(mesh.glb(name))
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", src)
    task.set_editor_property("destination_path", DEST + "/Meshes")
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    tools.import_asset_tasks([task])
    paths = list(task.get_editor_property("imported_object_paths") or [])
    meshes = [lib.load_asset(p.split(".")[0]) for p in paths]
    meshes = [m for m in meshes if isinstance(m, unreal.StaticMesh)]
    if not meshes:
        raise RuntimeError("no static mesh from " + src + " " + str(paths))
    sm = meshes[0]
    try:
        ns = sm.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", False)
        sm.set_editor_property("nanite_settings", ns)
    except Exception:
        pass
    body = sm.get_editor_property("body_setup")
    if body:
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    lib.save_loaded_asset(sm)
    return sm


def place(sm, label, tagname, folder, material, collision="BlockAll", shadow=True):
    a = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    c = a.static_mesh_component
    c.set_static_mesh(sm)
    if material is not None:
        for i in range(max(1, c.get_num_materials())):
            c.set_material(i, material)
    c.set_collision_profile_name(collision)
    c.set_editor_property("cast_shadow", shadow)
    tag(a, tagname, label, folder)
    return a


# --- materials ------------------------------------------------------------------------------------------------

def fresh_material(name):
    path = DEST + "/Materials/" + name
    if lib.does_asset_exist(path):
        lib.delete_asset(path)
    return tools.create_asset(name, DEST + "/Materials", unreal.Material, unreal.MaterialFactoryNew())


def E(mat, cls, x, y, **props):
    node = MEL.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        node.set_editor_property(k, v)
    return node


def C(a, b, pin="", out=""):
    if not MEL.connect_material_expressions(a, out, b, pin):
        raise RuntimeError("connect %s.%s -> %s.%s failed" % (a.get_name(), out, b.get_name(), pin))


def P(node, prop, out=""):
    if not MEL.connect_material_property(node, out, prop):
        raise RuntimeError("connect property %s failed" % prop)


def const(mat, v, x, y):
    if isinstance(v, (int, float)):
        return E(mat, unreal.MaterialExpressionConstant, x, y, r=float(v))
    if len(v) == 2:
        return E(mat, unreal.MaterialExpressionConstant2Vector, x, y, r=float(v[0]), g=float(v[1]))
    return E(mat, unreal.MaterialExpressionConstant3Vector, x, y, constant=unreal.LinearColor(v[0], v[1], v[2], 1))


def op(mat, cls, a, b, x, y):
    n = E(mat, cls, x, y)
    C(a, n, "A")
    C(b, n, "B")
    return n


def mask(mat, src, x, y, r=False, g=False, b=False):
    n = E(mat, unreal.MaterialExpressionComponentMask, x, y, r=r, g=g, b=b, a=False)
    C(src, n)
    return n


def import_texture(name, normal=False):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", os.path.join(TEX_DIR, name + ".png"))
    task.set_editor_property("destination_path", DEST + "/Textures")
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    tools.import_asset_tasks([task])
    tex = lib.load_asset(DEST + "/Textures/" + name)
    if normal:
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        tex.set_editor_property("srgb", False)
    lib.save_loaded_asset(tex)
    return tex


@step("textures")
def textures():
    return {n: import_texture(n, n.endswith("Normal")).get_path_name()
            for n in ("T_L9_WaterNormal", "T_L9_Foam", "T_L9_BedNoise")}


@step("material_bed")
def material_bed():
    mat = fresh_material("M_L9_Bed")
    uv = E(mat, unreal.MaterialExpressionTextureCoordinate, -900, 0, coordinate_index=0)
    tex = E(mat, unreal.MaterialExpressionTextureSample, -650, 0,
            texture=lib.load_asset(DEST + "/Textures/T_L9_BedNoise"))
    C(uv, tex, "UVs")
    r = mask(mat, tex, -420, 0, r=True)
    lerp = E(mat, unreal.MaterialExpressionLinearInterpolate, -200, 0)
    C(const(mat, (0.075, 0.068, 0.05), -420, -150), lerp, "A")
    C(const(mat, (0.21, 0.19, 0.14), -420, 150), lerp, "B")
    C(r, lerp, "Alpha")
    P(lerp, unreal.MaterialProperty.MP_BASE_COLOR)
    P(const(mat, 0.92, -200, 200), unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.recompile_material(mat)
    lib.save_loaded_asset(mat)
    return mat.get_path_name()


@step("material_water_B")
def material_water():
    """M_L9_Water: our own water. Single Layer Water shading (depth-based absorption and scattering against the real
    bed, Lumen/SSR reflections, Fresnel from the specular), two flow-mapped normal layers that move downstream at
    the vertex's speed (UV1.y m/s; V runs downstream in TILE_M units), a slow drift for still water, shore foam
    from the distance to the shore (UV1.x m) broken up by a code-made foam texture, gentle WPO waves where the
    water is still (lakes)."""
    mat = fresh_material("M_L9_Water")
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_SINGLE_LAYER_WATER)
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    ntex = lib.load_asset(DEST + "/Textures/T_L9_WaterNormal")
    ftex = lib.load_asset(DEST + "/Textures/T_L9_Foam")
    uv0 = E(mat, unreal.MaterialExpressionTextureCoordinate, -2200, 0, coordinate_index=0)
    uv1 = E(mat, unreal.MaterialExpressionTextureCoordinate, -2200, 300, coordinate_index=1)
    t = E(mat, unreal.MaterialExpressionTime, -2200, -300)
    shore = mask(mat, uv1, -2000, 260, r=True)
    speed = mask(mat, uv1, -2000, 380, g=True)
    # V offset (tiles) = time * speed / TILE_M; layer A at 1x, layer B at 1.9x scale and 1.3x speed.
    tv = op(mat, unreal.MaterialExpressionMultiply, t, speed, -1800, -200)
    va = op(mat, unreal.MaterialExpressionMultiply, tv, const(mat, -1.0 / G.TILE_M, -1950, -120), -1600, -200)
    vb = op(mat, unreal.MaterialExpressionMultiply, tv, const(mat, -1.3 * 1.9 / G.TILE_M, -1950, -40), -1600, -80)
    ua = op(mat, unreal.MaterialExpressionMultiply, t, const(mat, 0.011, -1950, -300), -1600, -320)
    ub = op(mat, unreal.MaterialExpressionMultiply, t, const(mat, -0.016, -1950, -380), -1600, -420)
    offa = op(mat, unreal.MaterialExpressionAppendVector, ua, va, -1400, -260)
    offb = op(mat, unreal.MaterialExpressionAppendVector, ub, vb, -1400, -120)
    uva = op(mat, unreal.MaterialExpressionAdd, uv0, offa, -1200, -260)
    uv0b = op(mat, unreal.MaterialExpressionMultiply, uv0, const(mat, 1.9, -1400, 20), -1300, 20)
    uvb = op(mat, unreal.MaterialExpressionAdd, uv0b, offb, -1200, -100)
    na = E(mat, unreal.MaterialExpressionTextureSample, -1000, -300, texture=ntex,
           sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    C(uva, na, "UVs")
    nb = E(mat, unreal.MaterialExpressionTextureSample, -1000, -60, texture=ntex,
           sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    C(uvb, nb, "UVs")
    rga = mask(mat, na, -780, -300, r=True, g=True)
    rgb_ = mask(mat, nb, -780, -60, r=True, g=True)
    rg = op(mat, unreal.MaterialExpressionAdd, rga, rgb_, -620, -200)
    rgs = op(mat, unreal.MaterialExpressionMultiply, rg, const(mat, 0.55, -780, 60), -480, -200)
    n3 = op(mat, unreal.MaterialExpressionAppendVector, rgs, const(mat, 1.0, -620, 60), -340, -200)
    nn = E(mat, unreal.MaterialExpressionNormalize, -200, -200)
    C(n3, nn)
    P(nn, unreal.MaterialProperty.MP_NORMAL)
    # Foam: 1 at the waterline, 0 past ~1.6 m, broken up by the foam texture moving with layer A.
    sm = op(mat, unreal.MaterialExpressionDivide, shore, const(mat, 1.6, -1800, 520), -1600, 460)
    sat = E(mat, unreal.MaterialExpressionSaturate, -1450, 460)
    C(sm, sat)
    edge = E(mat, unreal.MaterialExpressionOneMinus, -1300, 460)
    C(sat, edge)
    fuv = op(mat, unreal.MaterialExpressionMultiply, uva, const(mat, 2.3, -1300, 600), -1150, 560)
    ft = E(mat, unreal.MaterialExpressionTextureSample, -1000, 560, texture=ftex)
    C(fuv, ft, "UVs")
    fr = mask(mat, ft, -800, 560, r=True)
    e2 = op(mat, unreal.MaterialExpressionMultiply, edge, edge, -1100, 420)
    fm = op(mat, unreal.MaterialExpressionMultiply, e2, const(mat, 1.8, -1100, 480), -950, 440)
    f1 = op(mat, unreal.MaterialExpressionMultiply, fm, fr, -700, 460)
    foam = E(mat, unreal.MaterialExpressionSaturate, -560, 460)
    C(f1, foam)
    bc = op(mat, unreal.MaterialExpressionMultiply, foam, const(mat, (0.78, 0.8, 0.78), -700, 620), -400, 520)
    P(bc, unreal.MaterialProperty.MP_BASE_COLOR)
    rough = E(mat, unreal.MaterialExpressionLinearInterpolate, -300, 400)
    C(const(mat, 0.035, -450, 360), rough, "A")
    C(const(mat, 0.55, -450, 420), rough, "B")
    C(foam, rough, "Alpha")
    P(rough, unreal.MaterialProperty.MP_ROUGHNESS)
    P(const(mat, 0.0, -300, 300), unreal.MaterialProperty.MP_METALLIC)
    P(const(mat, 1.0, -300, 250), unreal.MaterialProperty.MP_SPECULAR)
    # Lake waves: 4 cm, two crossing swells, only where the water is still (speed 0).
    wp = E(mat, unreal.MaterialExpressionWorldPosition, -2200, 900)
    xy = mask(mat, wp, -2000, 900, r=True, g=True)
    d1 = op(mat, unreal.MaterialExpressionDotProduct, xy, const(mat, (0.0031, 0.0019), -2000, 980), -1800, 900)
    d2 = op(mat, unreal.MaterialExpressionDotProduct, xy, const(mat, (-0.0023, 0.0042), -2000, 1060), -1800, 1000)
    a1 = op(mat, unreal.MaterialExpressionAdd, d1, op(mat, unreal.MaterialExpressionMultiply, t,
                                                       const(mat, 1.1, -1950, 1150), -1800, 1120), -1600, 900)
    a2 = op(mat, unreal.MaterialExpressionAdd, d2, op(mat, unreal.MaterialExpressionMultiply, t,
                                                       const(mat, 1.7, -1950, 1250), -1800, 1220), -1600, 1000)
    s1 = E(mat, unreal.MaterialExpressionSine, -1450, 900, period=6.2831853)
    C(a1, s1)
    s2 = E(mat, unreal.MaterialExpressionSine, -1450, 1000, period=6.2831853)
    C(a2, s2)
    s2s = op(mat, unreal.MaterialExpressionMultiply, s2, const(mat, 0.6, -1450, 1080), -1300, 1000)
    sw = op(mat, unreal.MaterialExpressionAdd, s1, s2s, -1150, 950)
    still = op(mat, unreal.MaterialExpressionMultiply, speed, const(mat, 4.0, -1450, 1180), -1300, 1150)
    still_s = E(mat, unreal.MaterialExpressionSaturate, -1150, 1150)
    C(still, still_s)
    still_1 = E(mat, unreal.MaterialExpressionOneMinus, -1000, 1150)
    C(still_s, still_1)
    amp = op(mat, unreal.MaterialExpressionMultiply, sw, still_1, -900, 1000)
    amp_cm = op(mat, unreal.MaterialExpressionMultiply, amp, const(mat, 4.0, -900, 1100), -750, 1000)
    wpo = op(mat, unreal.MaterialExpressionAppendVector,
             const(mat, (0.0, 0.0), -750, 900), amp_cm, -550, 950)
    P(wpo, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    # Single Layer Water: absorption and scattering per metre (a green-brown lowland river).
    out = E(mat, unreal.MaterialExpressionSingleLayerWaterMaterialOutput, 0, 800)
    wired = []
    for value, names in (((0.012, 0.022, 0.018), ("ScatteringCoefficients", "Scattering Coefficients")),
                         ((0.42, 0.13, 0.09), ("AbsorptionCoefficients", "Absorption Coefficients")),
                         (0.1, ("PhaseG", "Phase G"))):
        node = const(mat, value, -250, 800 + 80 * len(wired))
        for nm in names:
            if MEL.connect_material_expressions(node, "", out, nm):
                wired.append(nm)
                break
    MEL.recompile_material(mat)
    lib.save_loaded_asset(mat)
    return {"path": mat.get_path_name(), "slw_inputs": wired}


# --- the level ------------------------------------------------------------------------------------------------

@step("open_level")
def open_level():
    ok = les.load_level(SRC_LEVEL)
    return {"loaded": bool(ok), "actors": len(eas.get_all_level_actors())}


@step("save_as")
def save_as():
    world = unreal.EditorLevelLibrary.get_editor_world()
    ok = False
    try:
        ok = unreal.EditorLoadingAndSavingUtils.save_map(world, OUT_LEVEL)
    except Exception:
        st["errors"].append("save_map: " + traceback.format_exc()[-300:])
    if not ok:
        # This whole project is lane 9's copy: saving GenCity_Seed7 here does not touch lane 7's level.
        ok2 = les.save_current_level()
        return {"saved_as": False, "saved_in_place": bool(ok2), "level": SRC_LEVEL}
    return {"saved_as": True, "level": OUT_LEVEL}


def bounds2(actor):
    o, e = actor.get_actor_bounds(False)
    return (o.y - e.y) / 100.0, (o.x - e.x) / 100.0, (o.y + e.y) / 100.0, (o.x + e.x) / 100.0, (o.z + e.z) / 100.0


@step("clear")
def clear():
    """The old flat water out; lane 9's own actors from an earlier run out; the ground slab's place and material."""
    out = {"removed": [], "slab": None}
    for a in eas.get_all_level_actors():
        label = a.get_actor_label()
        tags = [str(t) for t in a.get_editor_property("tags")]
        if any(t.startswith("lane9") for t in tags) or (label.startswith("Water_") and isinstance(a, unreal.StaticMeshActor)):
            out["removed"].append(label)
            eas.destroy_actor(a)
    for a in eas.get_all_level_actors():
        if a.get_actor_label() == "GroundSlab":
            b = bounds2(a)
            mat = a.static_mesh_component.get_material(0)
            out["slab"] = {"rect": [round(v, 2) for v in b[:4]], "top": round(b[4], 3),
                           "material": mat.get_path_name() if mat else None}
            st["slab_material"] = mat
            out["removed"].append("GroundSlab")
            eas.destroy_actor(a)
            break
    return out


@step("pond_site")
def pond_site():
    """Clear the demo pond's site in the park: trees and props within its radius, and the park's ground pieces."""
    cx, cy, r = PLAN["pond"]
    reach = r * 1.25 + 5.0
    out = {"instances_removed": 0, "actors_removed": [], "ground": []}
    for a in eas.get_all_level_actors():
        tags = [str(t) for t in a.get_editor_property("tags")]
        if any(t.startswith("lane9") for t in tags):
            continue
        for comp in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            n = comp.get_instance_count()
            kill = []
            for i in range(n):
                tr = comp.get_instance_transform(i, True)
                x, y = tr.translation.y / 100.0, tr.translation.x / 100.0
                if (x - cx) ** 2 + (y - cy) ** 2 < reach ** 2:
                    kill.append(i)
            if kill:
                comp.remove_instances(kill)
                out["instances_removed"] += len(kill)
        if not isinstance(a, unreal.StaticMeshActor):
            continue
        x0, y0, x1, y1, top = bounds2(a)
        nx, ny = min(max(cx, x0), x1), min(max(cy, y0), y1)
        if (nx - cx) ** 2 + (ny - cy) ** 2 > reach ** 2:
            continue
        size = max(x1 - x0, y1 - y0)
        label = a.get_actor_label()
        if size > 260.0:
            out["ground"].append({"kept_large": label, "size_m": round(size), "top": round(top, 3)})
            continue
        mat = a.static_mesh_component.get_material(0)
        if top < 1.0:
            out["ground"].append({"removed": label, "size_m": round(size), "top": round(top, 3),
                                  "material": mat.get_path_name() if mat else None})
            st.setdefault("park_ground", []).append((size, top, mat))
        out["actors_removed"].append(label)
        eas.destroy_actor(a)
    return out


@step("shared_geometry")
def shared_geometry():
    river, lake = PLAN["river"], PLAN["lake"]
    rows = G.extended(river, 260.0, 260.0)
    st["rows"] = rows
    st["rows_n"] = len(rows)
    slab = st["steps"]["clear"]["out"]["slab"]
    rect = slab["rect"] if slab else [-200.0, -200.0, 1700.0, 1700.0]
    ztop = slab["top"] if slab else -0.02
    out = {}
    bed_mat = lib.load_asset(DEST + "/Materials/M_L9_Bed")
    ground_mat = st.get("slab_material")
    for i, m in enumerate(G.ground_cut(rows, rect, ztop, hole=lake["outline"])):
        sm = import_glb(m, "SM_L9_GroundCut_%d" % i)
        place(sm, "L9_GroundCut_%d" % i, "lane9_shared", "Shared", ground_mat)
        out["ground_cut_%d" % i] = len(m.tris)
    ch = G.channel(rows, river["level"], river["bank_slope"])
    place(import_glb(ch, "SM_L9_RiverBed"), "L9_RiverBed", "lane9_shared", "Shared", bed_mat)
    out["channel_tris"] = len(ch.tris)
    bw = G.bowl(lake)
    place(import_glb(bw, "SM_L9_PondBed"), "L9_PondBed", "lane9_shared", "Shared", bed_mat)
    park = PLAN.get("park")
    pg = sorted(st.get("park_ground") or [], key=lambda t: -t[0])
    if park and pg:
        _size, top, mat = pg[0]
        ring = G.with_hole([tuple(p) for p in park["polygon"]], [tuple(p) for p in lake["outline"]])
        pm = G.polygon_mesh(ring, top)
        place(import_glb(pm, "SM_L9_ParkAroundPond"), "L9_ParkAroundPond", "lane9_shared", "Shared", mat)
        out["park"] = {"top": top, "material": mat.get_path_name() if mat else None}
    return out


@step("option_B")
def option_b():
    river, lake = PLAN["river"], PLAN["lake"]
    wmat = lib.load_asset(DEST + "/Materials/M_L9_Water")
    rs = G.river_surface(st["rows"], river["level"], river["surface_m"], river["bank_slope"])
    place(import_glb(rs, "SM_L9_RiverSurface"), "L9B_River_Longcut", "lane9_B", "B_OwnWater", wmat,
          collision="NoCollision", shadow=False)
    ls = G.lake_surface(lake)
    place(import_glb(ls, "SM_L9_PondSurface"), "L9B_Lake_DemoPond", "lane9_B", "B_OwnWater", wmat,
          collision="NoCollision", shadow=False)
    return {"river_tris": len(rs.tris), "lake_tris": len(ls.tris)}


def try_set(obj, names, value):
    for n in names:
        try:
            obj.set_editor_property(n, value)
            return n
        except Exception:
            continue
    return None


def probe(obj, words=("water", "spline", "width", "depth", "veloc", "zone", "collision", "material", "metadata",
                      "update", "extent", "buoy")):
    return sorted(n for n in dir(obj) if not n.startswith("_") and any(w in n.lower() for w in words))


@step("option_A")
def option_a():
    river, lake = PLAN["river"], PLAN["lake"]
    out = {}
    st["probe"]["classes"] = {n: hasattr(unreal, n) for n in ("WaterZone", "WaterBodyRiver", "WaterBodyLake",
                                                               "WaterSplineComponent", "WaterSplineMetadata",
                                                               "BuoyancyComponent", "WaterBodyRiverComponent")}
    rows = st["rows"]
    mid = rows[len(rows) // 2]["at"]
    zone = eas.spawn_actor_from_class(unreal.WaterZone, ue((mid[0], mid[1], 0.0)), unreal.Rotator(0, 0, 0))
    tag(zone, "lane9_A", "L9A_WaterZone", "A_WaterPlugin")
    st["probe"]["zone"] = probe(zone)
    out["zone_extent_prop"] = try_set(zone, ["zone_extent"], unreal.Vector2D(200000.0, 200000.0))
    # The river: every 3rd station, carried 120 m past the city's edges.
    rrows = G.extended(river, 120.0, 120.0)[::3]
    surface = river["surface_m"]
    body = eas.spawn_actor_from_class(unreal.WaterBodyRiver, ue((rrows[0]["at"][0], rrows[0]["at"][1], surface)),
                                      unreal.Rotator(0, 0, 0))
    tag(body, "lane9_A", "L9A_River_Longcut", "A_WaterPlugin")
    st["probe"]["river_actor"] = probe(body)
    spline = body.get_water_spline()
    st["probe"]["spline"] = probe(spline)
    try:
        defaults = spline.get_editor_property("water_spline_defaults")
        st["probe"]["spline_defaults"] = probe(defaults, ("default",))
        mean_w = sum(r["w"] for r in rrows) / len(rrows)
        mean_d = sum(r["d"] for r in rrows) / len(rrows)
        try_set(defaults, ["default_width"], mean_w * 100.0)
        try_set(defaults, ["default_depth"], (mean_d - (river["level"] - surface)) * 100.0)
        try_set(defaults, ["default_velocity"], rrows[0]["v"] * 100.0)
        spline.set_editor_property("water_spline_defaults", defaults)
        out["defaults"] = {"width_cm": round(mean_w * 100), "depth_cm": round((mean_d - 0.5) * 100)}
    except Exception:
        out["defaults_error"] = traceback.format_exc()[-400:]
    pts = [ue((r["at"][0], r["at"][1], surface)) for r in rrows]
    spline.set_spline_points(pts, unreal.SplineCoordinateSpace.WORLD, True)
    out["river_points"] = spline.get_number_of_spline_points()
    # Per-point width, depth and velocity (the spline's metadata), when Python can reach it.
    meta = None
    for getter in ("get_water_spline_metadata", "get_spline_metadata"):
        for o in (body, spline, getattr(body, "get_water_body_component", lambda: None)()):
            if o is not None and hasattr(o, getter):
                try:
                    meta = getattr(o, getter)()
                    if meta:
                        break
                except Exception:
                    pass
        if meta:
            break
    if meta is None:
        for o in (body, spline):
            for prop in ("water_spline_metadata", "spline_metadata"):
                try:
                    meta = o.get_editor_property(prop)
                    if meta:
                        break
                except Exception:
                    pass
            if meta:
                break
    out["metadata"] = meta.get_class().get_name() if meta else None
    if meta:
        st["probe"]["metadata"] = probe(meta, ("width", "depth", "veloc", "audio", "curve"))
        try:
            for prop, key, scale in (("river_width", "w", 100.0), ("depth", "d", 100.0),
                                     ("water_velocity_scalar", "v", 1.0 / 0.6)):
                curve = meta.get_editor_property(prop)
                cpts = list(curve.get_editor_property("points"))
                for i, cp in enumerate(cpts):
                    r = rrows[min(i, len(rrows) - 1)]
                    val = r[key] * scale if key != "d" else (r["d"] - (river["level"] - surface)) * 100.0
                    cp.set_editor_property("out_val", float(val))
                    cpts[i] = cp
                curve.set_editor_property("points", cpts)
                meta.set_editor_property(prop, curve)
            out["per_point"] = True
        except Exception:
            out["per_point_error"] = traceback.format_exc()[-500:]
    # The lake.
    lk = eas.spawn_actor_from_class(unreal.WaterBodyLake, ue((lake["centroid"][0], lake["centroid"][1], lake["surface_m"])),
                                    unreal.Rotator(0, 0, 0))
    tag(lk, "lane9_A", "L9A_Lake_DemoPond", "A_WaterPlugin")
    ls = lk.get_water_spline()
    ring = G.ccw(lake["outline"])[::2]
    ls.set_spline_points([ue((p[0], p[1], lake["surface_m"])) for p in ring], unreal.SplineCoordinateSpace.WORLD, True)
    ls.set_closed_loop(True)
    out["lake_points"] = ls.get_number_of_spline_points()
    # Nudge the editor's change path so the bodies rebuild (the saved level also rebuilds them on load).
    for a in (body, lk, zone):
        for fn in ("post_edit_change", "rerun_construction_scripts", "on_water_body_changed", "update_all"):
            if hasattr(a, fn):
                try:
                    getattr(a, fn)()
                except Exception:
                    pass
    comp = body.get_water_body_component() if hasattr(body, "get_water_body_component") else None
    if comp:
        st["probe"]["river_component"] = probe(comp)
        for prop in ("water_material", "underwater_post_process_material", "water_info_material",
                     "water_static_mesh_material", "water_lod_material", "river_to_lake_transition_material",
                     "river_to_ocean_transition_material"):
            try:
                m = comp.get_editor_property(prop)
                out.setdefault("epic_materials", {})[prop] = m.get_path_name() if m else None
            except Exception:
                pass
        for prop in ("collision_profile_name", "b_generate_collisions", "generate_collisions"):
            try:
                out.setdefault("collision", {})[prop] = str(comp.get_editor_property(prop))
            except Exception:
                pass
    return out


@step("hide_A_in_B_check")
def overlap_report():
    """Actors near the river's middle and low (anything that could cover the channel): a list to look at."""
    rows = st["rows"]
    hits = []
    for a in eas.get_all_level_actors():
        if not isinstance(a, unreal.StaticMeshActor):
            continue
        tags = [str(t) for t in a.get_editor_property("tags")]
        if any(t.startswith("lane9") for t in tags):
            continue
        x0, y0, x1, y1, top = bounds2(a)
        if top > 0.5 or (x1 - x0) > 400:
            continue
        for r in rows[::5]:
            if x0 + 3 < r["at"][0] < x1 - 3 and y0 < r["at"][1] < y1:
                hits.append(a.get_actor_label())
                break
    return hits[:60]


def main():
    open_level()
    textures()
    material_bed()
    material_water()
    clear()
    pond_site()
    shared_geometry()
    option_b()
    option_a()
    overlap_report()
    save_as()
    st["done"] = True
    save_status()


try:
    main()
except Exception:
    st["errors"].append(traceback.format_exc())
    save_status()
