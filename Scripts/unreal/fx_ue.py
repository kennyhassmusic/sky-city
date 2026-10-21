"""The car's thrust and smoke looks, for SkysterCar's plumes and particle pools (Source/SkyCity/SkysterFX.*).
Stages (args, default all):
  import     SourceArt/FX/*.png (make_fx_textures.py) -> /Game/SkyCity/FX, and the plume mesh SourceArt/RoadsterRig/SC_JetCone.glb
             (blender_fx_kit.py) over the old cone
  (T_SkySmoke is the Blender smoke flipbook: blender_smoke_flipbook.py, then make_fx_textures.py --smoke)
  materials  M_SkyJet (rebuilt in place: scrolling turbulence, soft edges, hot core, optional shock diamonds; params Color,
             Strength, Gain, Exp, EdgeExp, Hot, Diamonds, Freq; MI_Jet sets Gain), M_SkyVapor (lit translucent puffs), M_SkyFire and M_SkySpark (additive)
  save
Run in the editor: py Scripts/unreal/fx_ue.py [stages]
Writes Saved/MCPScripts/out_fx.json."""
import json, sys, time, traceback, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_fx.json"
DIR = "/Game/SkyCity/FX"
JET = "/Game/SkyCity/Pickups/Materials/M_SkyJet"
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
STAGES = sys.argv[1:] or ["import", "materials", "save"]
GAIN = 0.35   # overall plume brightness (four plumes and their cores overlap additively)
out = {"stages": STAGES}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def import_files(files, dest):
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", dest)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", False)
        tasks.append(t)
    AT.import_asset_tasks(tasks)
    res = []
    for t in tasks:
        res += list(t.get_editor_property("imported_object_paths") or [])
    return res


def stage_import():
    tex = import_files([ROOT + "/SourceArt/FX/T_SkyNoise.png", ROOT + "/SourceArt/FX/T_SkyPuff.png", ROOT + "/SourceArt/FX/T_SkySmoke.png"], DIR)
    for p in tex:
        t = EAL.load_asset(p)
        t.set_editor_property("srgb", False)
        t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
        if "Puff" in p or "Smoke" in p:
            t.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
            t.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
        EAL.save_loaded_asset(t)
    mesh = import_files([ROOT + "/SourceArt/RoadsterRig/SC_JetCone.glb"], "/Game/Vehicles/RoadsterRig")
    log("import", {"textures": tex, "mesh": mesh})


def material(path, blend, unlit, two_sided=False):
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
    else:
        d, n = path.rsplit("/", 1)
        m = AT.create_asset(n, d, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("blend_mode", blend)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT if unlit else unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    m.set_editor_property("two_sided", two_sided)
    m.set_editor_property("used_with_instanced_static_meshes", True)
    return m


def X(m, cls, x, y, **props):
    e = MEL.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def scalar(m, name, v, x, y):
    return X(m, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=v)


def tex_sample(m, tex, x, y):
    return X(m, unreal.MaterialExpressionTextureSample, x, y, texture=tex, sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)


def custom(m, x, y, code, inputs, otype=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
    c = X(m, unreal.MaterialExpressionCustom, x, y, code=code, output_type=otype)
    ins = []
    for n in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    c.set_editor_property("inputs", ins)
    return c


def link(a, b, pin=""):
    MEL.connect_material_expressions(a, "", b, pin)


def plume(noise):
    """Additive, unlit, two-sided gas: two layers of turbulence scroll from the nozzle to the tip (V 0 -> 1), the silhouette
    goes soft (view-facing parts bright, grazing edges faint), a hot core right at the nozzle, optional shock diamonds."""
    m = material(JET, unreal.BlendMode.BLEND_ADDITIVE, True, True)
    tc = X(m, unreal.MaterialExpressionTextureCoordinate, -1400, 0)
    layers = []
    for k, (sc, off, sp) in enumerate((((1.0, 0.45), (0.0, 0.0), -1.8), ((2.0, 0.9), (0.37, 0.0), -3.1))):
        mul = X(m, unreal.MaterialExpressionMultiply, -1250, -300 + k * 160)
        c2 = X(m, unreal.MaterialExpressionConstant2Vector, -1400, -360 + k * 160, r=sc[0], g=sc[1])
        link(tc, mul, "A")
        link(c2, mul, "B")
        add = X(m, unreal.MaterialExpressionAdd, -1120, -300 + k * 160)
        o2 = X(m, unreal.MaterialExpressionConstant2Vector, -1250, -230 + k * 160, r=off[0], g=off[1])
        link(mul, add, "A")
        link(o2, add, "B")
        pan = X(m, unreal.MaterialExpressionPanner, -980, -300 + k * 160, speed_x=0.0, speed_y=sp)
        link(add, pan, "Coordinate")
        ts = tex_sample(m, noise, -820, -300 + k * 200)
        link(pan, ts, "UVs")
        layers.append(ts)
    nrm = X(m, unreal.MaterialExpressionVertexNormalWS, -820, 140)
    cam = X(m, unreal.MaterialExpressionCameraVectorWS, -820, 220)
    col = X(m, unreal.MaterialExpressionVectorParameter, -820, 300, parameter_name="Color", default_value=unreal.LinearColor(0.9, 1.3, 1.9, 1))
    params = [("Strength", 2.0), ("Gain", 1.0), ("Exp", 1.4), ("EdgeExp", 1.5), ("Hot", 0.8), ("Diamonds", 0.0), ("Freq", 5.0)]
    ps = [scalar(m, n, v, -820, 420 + i * 70) for i, (n, v) in enumerate(params)]
    code = """float v = saturate(UV.y);
float turb = saturate(N1 * N2 * 2.6);
float streak = lerp(0.15, 1.3, turb);
float fade = pow(1.0 - v, Exp);
float edge = pow(abs(dot(normalize(Nrm), normalize(Cam))), EdgeExp);
float hot = pow(1.0 - v, 10.0) * Hot;
float d = 0.5 + 0.5 * cos(v * Freq * 6.2831853);
float diam = 1.0 + Diamonds * pow(d, 6.0) * (1.0 - v);
return Color * Strength * Gain * edge * (fade * streak * diam + hot);"""
    cu = custom(m, -450, 0, code, ["UV", "N1", "N2", "Nrm", "Cam", "Color", "Strength", "Gain", "Exp", "EdgeExp", "Hot", "Diamonds", "Freq"])
    link(tc, cu, "UV")
    link(layers[0], cu, "N1")
    link(layers[1], cu, "N2")
    link(nrm, cu, "Nrm")
    link(cam, cu, "Cam")
    link(col, cu, "Color")
    for (n, _), p in zip(params, ps):
        link(p, cu, n)
    MEL.connect_material_property(cu, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    mi = EAL.load_asset("/Game/SkyCity/Pickups/Materials/MI_Jet")
    MEL.set_material_instance_scalar_parameter_value(mi, "Gain", GAIN)
    MEL.update_material_instance(mi)
    EAL.save_loaded_asset(mi)
    return m


FLIP = """float f = saturate(Age) * 63.0;
float f0 = floor(f);
float f1 = min(f0 + 1.0, 63.0);
float2 uv = UV * 0.992 + 0.004;
float2 a0 = (uv + float2(fmod(f0, 8.0), floor(f0 / 8.0))) / 8.0;
float2 a1 = (uv + float2(fmod(f1, 8.0), floor(f1 / 8.0))) / 8.0;
return lerp(Texture2DSample(Tex, TexSampler, a0), Texture2DSample(Tex, TexSampler, a1), f - f0);"""


def flipbook(m, smoke, x, y):
    """The smoke flipbook frame for this particle's age (custom data 4), blended with the next: rgb light and shade, a density."""
    tc = X(m, unreal.MaterialExpressionTextureCoordinate, x - 200, y)
    age = X(m, unreal.MaterialExpressionPerInstanceCustomData, x - 200, y + 70, data_index=4)
    to = X(m, unreal.MaterialExpressionTextureObject, x - 200, y + 140, texture=smoke, sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    fb = custom(m, x, y, FLIP, ["UV", "Age", "Tex"], unreal.CustomMaterialOutputType.CMOT_FLOAT4)
    link(tc, fb, "UV")
    link(age, fb, "Age")
    link(to, fb, "Tex")
    return fb


def vapor(smoke):
    """Lit translucent smoke: the flipbook's billows tinted by the instance colour (custom data 0-2), alpha (3) x density,
    soft where it meets geometry."""
    m = material(f"{DIR}/M_SkyVapor", unreal.BlendMode.BLEND_TRANSLUCENT, False)
    m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_VOLUMETRIC_NON_DIRECTIONAL)
    rgb = X(m, unreal.MaterialExpressionPerInstanceCustomData3Vector, -600, -200, data_index=0)
    a = X(m, unreal.MaterialExpressionPerInstanceCustomData, -600, 0, data_index=3)
    fb = flipbook(m, smoke, -600, 120)
    fbrgb = X(m, unreal.MaterialExpressionComponentMask, -450, -60, r=True, g=True, b=True, a=False)
    link(fb, fbrgb)
    mask = X(m, unreal.MaterialExpressionMultiply, -380, -160)
    link(rgb, mask, "A")
    link(fbrgb, mask, "B")
    am = X(m, unreal.MaterialExpressionComponentMask, -500, 120, r=False, g=False, b=False, a=True)
    link(fb, am)
    mul = X(m, unreal.MaterialExpressionMultiply, -380, 40)
    link(a, mul, "A")
    link(am, mul, "B")
    df = X(m, unreal.MaterialExpressionDepthFade, -220, 40, fade_distance_default=60.0)
    link(mul, df, "Opacity")
    MEL.connect_material_property(mask, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(df, "", unreal.MaterialProperty.MP_OPACITY)
    sp = X(m, unreal.MaterialExpressionConstant, -380, 260, r=0.0)
    ro = X(m, unreal.MaterialExpressionConstant, -380, 330, r=1.0)
    MEL.connect_material_property(sp, "", unreal.MaterialProperty.MP_SPECULAR)
    MEL.connect_material_property(ro, "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def glow(name, puff):
    """Additive sprite: HDR colour x alpha per instance, through the smoke flipbook's density (fire) or a soft round dot (sparks)."""
    m = material(f"{DIR}/{name}", unreal.BlendMode.BLEND_ADDITIVE, True)
    rgb = X(m, unreal.MaterialExpressionPerInstanceCustomData3Vector, -700, -200, data_index=0)
    a = X(m, unreal.MaterialExpressionPerInstanceCustomData, -700, 0, data_index=3)
    g = scalar(m, "Glow", 6.0, -700, 300)
    if puff:
        fb = flipbook(m, puff, -900, 120)
        shape = custom(m, -700, 120, "return pow(saturate(C.a), 1.3) * (0.55 + 0.6 * C.r);", ["C"], unreal.CustomMaterialOutputType.CMOT_FLOAT1)
        link(fb, shape, "C")
        pin = ""
    else:
        tc = X(m, unreal.MaterialExpressionTextureCoordinate, -900, 120)
        shape = custom(m, -700, 120, "return pow(saturate(1.0 - length(UV * 2.0 - 1.0)), 1.5);", ["UV"], unreal.CustomMaterialOutputType.CMOT_FLOAT1)
        link(tc, shape, "UV")
        pin = ""
    df = X(m, unreal.MaterialExpressionDepthFade, -500, 120, fade_distance_default=30.0)
    MEL.connect_material_expressions(shape, pin, df, "Opacity")
    code = "return RGB * A * S * G;"
    cu = custom(m, -250, 0, code, ["RGB", "A", "S", "G"])
    link(rgb, cu, "RGB")
    link(a, cu, "A")
    link(df, cu, "S")
    link(g, cu, "G")
    MEL.connect_material_property(cu, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def stage_materials():
    noise = EAL.load_asset(f"{DIR}/T_SkyNoise")
    smoke = EAL.load_asset(f"{DIR}/T_SkySmoke")
    made = [plume(noise).get_path_name(), vapor(smoke).get_path_name(), glow("M_SkyFire", smoke).get_path_name(), glow("M_SkySpark", None).get_path_name()]
    log("materials", made)


def stage_save():
    EAL.save_directory(DIR, only_if_is_dirty=True, recursive=True)
    EAL.save_directory("/Game/Vehicles/RoadsterRig/SC_JetCone", only_if_is_dirty=True, recursive=True)
    EAL.save_loaded_asset(EAL.load_asset(JET))
    log("saved", True)


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
