"""The HUD mini map's assets: the map images (Scripts/hud/make_minimaps.py) as textures and M_MiniMap, a UI material
that turns and zooms a map image around the car (heading up, the car low in the panel so you see more road ahead,
like a Tesla's navigation map) and rounds the panel's corners. ASkysterHUD drives it from C++ (SkysterHUD.cpp) and
draws the car, the route and the chargers on top. /Game/SkyCity/HUD is always cooked (DefaultGame.ini).
Run in the editor: py Scripts/hud/minimap_ue.py [import] [material]
Writes Saved/MCPScripts/out_minimap.json."""
import glob, json, sys, time, traceback, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_minimap.json"
DIR = "/Game/SkyCity/HUD"
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
STAGES = sys.argv[1:] or ["import", "material"]
out = {"stages": STAGES}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def stage_import():
    tasks = []
    for f in sorted(glob.glob(ROOT + "/SourceArt/HUD/T_MiniMap_*.png")):
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", DIR)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", False)
        tasks.append(t)
    AT.import_asset_tasks(tasks)
    done = []
    for p in EAL.list_assets(DIR, recursive=False):
        a = EAL.load_asset(p.split(".")[0])
        if isinstance(a, unreal.Texture2D) and a.get_name().startswith("T_MiniMap_"):
            a.set_editor_property("never_stream", True)            # sampled at an arbitrary zoom: keep every mip resident
            a.set_editor_property("srgb", True)
            a.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
            a.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
            EAL.save_loaded_asset(a)
            done.append(a.get_name())
    log("import", done)


CODE = """float2 p = float2((UV.x - 0.5) * Aspect, UV.y - CarY);
float rightM = p.x * Meters;
float fwdM = -p.y * Meters;
float s = sin(Heading), c = cos(Heading);
float east = rightM * c + fwdM * s;
float north = -rightM * s + fwdM * c;
float2 uv = float2(CenterU + east / Size, CenterV - north / Size);
float3 col = Texture2DSample(Tex, TexSampler, uv).rgb;
float2 q = abs(float2((UV.x - 0.5) * Aspect, UV.y - 0.5)) - float2(0.5 * Aspect - Corner, 0.5 - Corner);
float d = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - Corner;
float a = saturate(-d * 300.0);
float rim = saturate(1.0 - abs(d + 0.004) * 300.0);
col = lerp(col, float3(0.42, 0.45, 0.5), rim * 0.6);
return float4(col, a * Opacity);"""


def stage_material():
    path = f"{DIR}/M_MiniMap"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
    else:
        m = AT.create_asset("M_MiniMap", DIR, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("material_domain", unreal.MaterialDomain.MD_UI)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)

    def X(cls, x, y, **props):
        e = MEL.create_material_expression(m, cls, x, y)
        for k, v in props.items():
            e.set_editor_property(k, v)
        return e
    tex = EAL.load_asset(f"{DIR}/T_MiniMap_SkyCity")
    cu = X(unreal.MaterialExpressionCustom, -300, 0, code=CODE, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT4)
    names = ["UV", "Tex", "CenterU", "CenterV", "Size", "Meters", "Heading", "Aspect", "CarY", "Corner", "Opacity"]
    ins = []
    for n in names:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    cu.set_editor_property("inputs", ins)
    MEL.connect_material_expressions(X(unreal.MaterialExpressionTextureCoordinate, -700, -200), "", cu, "UV")
    MEL.connect_material_expressions(X(unreal.MaterialExpressionTextureObjectParameter, -700, -120, parameter_name="Map", texture=tex,
                                       sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR), "", cu, "Tex")
    defaults = {"CenterU": 0.5, "CenterV": 0.5, "Size": 4096.0, "Meters": 300.0, "Heading": 0.0, "Aspect": 1.5, "CarY": 0.68,
                "Corner": 0.06, "Opacity": 0.94}
    for k, (n, v) in enumerate(defaults.items()):
        MEL.connect_material_expressions(X(unreal.MaterialExpressionScalarParameter, -700, -40 + k * 70, parameter_name=n, default_value=v), "", cu, n)
    rgb = X(unreal.MaterialExpressionComponentMask, -100, -60, r=True, g=True, b=True, a=False)
    al = X(unreal.MaterialExpressionComponentMask, -100, 60, r=False, g=False, b=False, a=True)
    MEL.connect_material_expressions(cu, "", rgb, "")
    MEL.connect_material_expressions(cu, "", al, "")
    MEL.connect_material_property(rgb, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(al, "", unreal.MaterialProperty.MP_OPACITY)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    log("material", path)


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
