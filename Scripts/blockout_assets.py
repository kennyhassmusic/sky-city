# Sky City blockout assets: flat-colour materials and the custom ramp meshes.
# Run in the editor: py Scripts/blockout_assets.py
# Safe to re-run: existing assets are rebuilt in place.
import json, math, traceback
import unreal

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


OUT = os.path.join(_skycity_root(), "Saved", "MCPScripts", "out.json")
MAT_DIR = "/Game/Blockout/Materials"
MESH_DIR = "/Game/Blockout/Meshes"
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
out = {"materials": {}, "meshes": {}}


def const3(m, rgb, x, y):
    e = MEL.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, x, y)
    e.set_editor_property("constant", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))
    return e


def const1(m, v, x, y):
    e = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, x, y)
    e.set_editor_property("r", v)
    return e


def make_material(name, rgb, rough=0.8, metal=0.0, emissive=0.0, rgb2=None, spec=0.5):
    """rgb2: per-instance random tint between rgb and rgb2 (for PCG towers)."""
    path = f"{MAT_DIR}/{name}"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
    else:
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("used_with_instanced_static_meshes", True)
    if rgb2:
        a, b = const3(m, rgb, -600, -100), const3(m, rgb2, -600, 0)
        pir = MEL.create_material_expression(m, unreal.MaterialExpressionPerInstanceRandom, -600, 100)
        lerp = MEL.create_material_expression(m, unreal.MaterialExpressionLinearInterpolate, -300, 0)
        MEL.connect_material_expressions(a, "", lerp, "A")
        MEL.connect_material_expressions(b, "", lerp, "B")
        MEL.connect_material_expressions(pir, "", lerp, "Alpha")
        base = lerp
    else:
        base = const3(m, rgb, -300, 0)
    MEL.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(const1(m, rough, -300, 150), "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(const1(m, metal, -300, 220), "", unreal.MaterialProperty.MP_METALLIC)
    MEL.connect_material_property(const1(m, spec, -300, 290), "", unreal.MaterialProperty.MP_SPECULAR)
    if emissive > 0:
        k = const1(m, emissive, -500, 400)
        mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -300, 400)
        MEL.connect_material_expressions(base, "", mul, "A")
        MEL.connect_material_expressions(k, "", mul, "B")
        MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    out["materials"][name] = path
    return m


def vec2(pts):
    return [unreal.Vector2D(x, y) for x, y in pts]


def bounds(dm):
    b = unreal.GeometryScript_MeshQueries.get_mesh_bounding_box(dm)
    return [round(b.min.x), round(b.min.y), round(b.min.z), round(b.max.x), round(b.max.y), round(b.max.z)]


def save_mesh(dm, name, mat):
    path = f"{MESH_DIR}/{name}"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
    for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", True),
                 ("enable_nanite", False), ("enable_collision", True)):
        try:
            opts.set_editor_property(k, v)
        except Exception:
            pass
    res = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, opts)
    sm = res[0] if isinstance(res, (tuple, list)) else res
    # drive and wall-ride on the real surface, not a box approximation
    bs = sm.get_editor_property("body_setup")
    if bs:
        bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    sm.set_material(0, mat)
    EAL.save_loaded_asset(sm)
    out["meshes"][name] = {"path": path, "bounds_cm": bounds(dm)}
    return sm


def extrude_profile(dm, profile, width):
    """Extrude a side profile drawn in (x, height) across `width` along Y, centred on Y=0."""
    P = unreal.GeometryScript_Primitives
    # roll -90 maps the polygon's y onto world +Z and the extrusion onto world -Y
    xf = unreal.Transform(unreal.Vector(0, width / 2.0, 0), unreal.Rotator(roll=-90, pitch=0, yaw=0), unreal.Vector(1, 1, 1))
    P.append_simple_extrude_polygon(dm, unreal.GeometryScriptPrimitiveOptions(), xf, vec2(profile), width, 0, True,
                                    unreal.GeometryScriptPrimitiveOriginMode.BASE)
    return dm


try:
    EAL.make_directory(MAT_DIR)
    EAL.make_directory(MESH_DIR)
    mats = {
        "asphalt": make_material("M_BO_Asphalt", (0.045, 0.047, 0.052), rough=0.9),
        "sidewalk": make_material("M_BO_Sidewalk", (0.42, 0.42, 0.40), rough=0.85),
        "water": make_material("M_BO_Water", (0.015, 0.09, 0.16), rough=0.04, spec=0.8),
        "park": make_material("M_BO_Park", (0.09, 0.22, 0.05), rough=0.95),
        "tower": make_material("M_BO_Tower", (0.30, 0.32, 0.35), rough=0.45, metal=0.2, rgb2=(0.72, 0.74, 0.78)),
        "lowrise": make_material("M_BO_LowRise", (0.55, 0.38, 0.28), rough=0.8, rgb2=(0.80, 0.74, 0.62)),
        "glass": make_material("M_BO_Glass", (0.10, 0.22, 0.30), rough=0.12, metal=0.7),
        "steel": make_material("M_BO_LSteel", (0.11, 0.09, 0.20), rough=0.5, metal=0.5),
        "accent": make_material("M_BO_Accent", (0.85, 0.33, 0.17), rough=0.6),
        "granite": make_material("M_BO_Granite", (0.62, 0.36, 0.30), rough=0.7),
        "dome": make_material("M_BO_Dome", (0.92, 0.90, 0.85), rough=0.5),
        "boost": make_material("M_BO_Boost", (1.0, 0.45, 0.05), rough=0.3, emissive=25.0),
        "wallride": make_material("M_BO_WallRide", (0.12, 0.62, 0.66), rough=0.35, emissive=0.6),
    }

    P = unreal.GeometryScript_Primitives
    opt = unreal.GeometryScriptPrimitiveOptions()

    # 1 m cube with its pivot on the bottom face: PCG scales it to any building height
    dm = unreal.DynamicMesh()
    P.append_box(dm, opt, unreal.Transform(), 100, 100, 100, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
    save_mesh(dm, "SM_BlockBox", mats["sidewalk"])

    # wedge ramp, 1 m long (X -50..50), 1 m wide, rising to 1 m at +X. Scale to fit.
    dm = extrude_profile(unreal.DynamicMesh(), [(-50, 0), (50, 0), (50, 100)], 100)
    save_mesh(dm, "SM_Ramp", mats["accent"])

    # quarter-pipe, 1 m radius: flat lip at X=0 curving up to vertical at X=100
    arc = [(100 * math.cos(math.radians(a)), 100 + 100 * math.sin(math.radians(a))) for a in range(-90, 1, 6)]
    qp = list(reversed(arc + [(100, 0)]))
    dm = extrude_profile(unreal.DynamicMesh(), qp, 100)
    save_mesh(dm, "SM_QuarterPipe", mats["accent"])

    # wall-ride tower: 20 m radius, 180 m tall cylinder with a 10 m quarter-pipe skirt around its foot
    RT, RS, H = 2000.0, 1000.0, 18000.0
    dm = unreal.DynamicMesh()
    P.append_cylinder(dm, opt, unreal.Transform(), RT, H, 48, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
    skirt = [(RT, 0.0)] + [(RT + RS - RS * math.sin(math.radians(a)), RS - RS * math.cos(math.radians(a))) for a in range(0, 91, 6)]
    skirt = [(RT, 0.0), (RT + RS, 0.0)] + skirt[2:]
    rev = unreal.GeometryScriptRevolveOptions()
    P.append_revolve_polygon(dm, opt, unreal.Transform(), vec2(skirt), rev, 0.0, 48)
    save_mesh(dm, "SM_WallRideTower", mats["wallride"])

    out["ok"] = True
except Exception:
    out["error"] = traceback.format_exc()

open(OUT, "w").write(json.dumps(out, indent=1))
