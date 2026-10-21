"""McGregor reveal night (/Game/Maps/McGregorNight): the McGregor map after dark, staged like the Oct 15 2026 Roadster
reveal from Kenny's photos: a black sky and low haze, tall stadium light banks blazing on the lot and the ramp, light
shafts through the haze, the ramp's edges and the fleet deck glowing red, blue light on the ramp's truss, a moving-head
truss sweeping beams in front of the ramp and searchlights turning over the site.

  map     open /Game/Maps/McGregorNight (made once by copying McGregor.umap with the editor closed; duplicating
          and loading in one go trips the editor's world-leak check)
  kit     import MG_StadiumLight, MG_LightTruss, MG_BeamCone (blender_mcgregor_kit.py -- night)
  sky     sun down, a cool moon, dim sky light, haze, fixed night exposure, bloom
  lights  stadium masts + spotlights + beams, the light towers' floods, ramp LEDs and uplights, fleet LEDs and
          vehicle lamps, the moving-head truss and the searchlights (rotating in game)
  save
Everything it adds is tagged SC_Night, so re-running replaces it.
(20 Oct 2026, mcgregor-unveil agent: lights follow the real unveil layout: masts kept out of demo_layout.json's
keep_clear lanes and the buildings, the moving-head truss on the side of the run-up away from the line-up, both white
buildings' facades washed red, the stage's light masts / screens / LED edge and the cranes' light rigs lit, beam fans
behind the stage like the drone shot.)
(20 Oct 2026 round 2, mcgregor-fixes agent: four small floods at the ramp's foot light it from underneath, cold white
like its top, Night_RampUnder_*; the stage lights follow the stage's new place on Kenny's long black stroke.)
Run in the editor: py Scripts/mcgregor/night_ue.py [stage ...]
"""
import json, math, sys, time, traceback, types, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_night.json"
NIGHT = "/Game/Maps/McGregorNight"
src = open(ROOT + "/Scripts/mcgregor/build_mcgregor_ue.py").read().split("QUEUE = [")[0]
B = types.ModuleType("mcg_defs")
B.__file__ = ROOT + "/Scripts/mcgregor/build_mcgregor_ue.py"
exec(compile(src.replace("STAGES = sys.argv[1:] or", "STAGES = [] or"), "mcg_defs", "exec"), B.__dict__)
EAL, EAS, MEL = B.EAL, B.EAS, B.MEL
L = json.load(open(ROOT + "/Saved/McGregor/demo_layout.json"))
STAGES = sys.argv[1:] or ["map", "kit", "sky", "lights", "save"]
TAG = "SC_Night"
# this level's daylight is a 10 lux sun (the template's scale), so the lights are scaled to it: the floods put
# ~15 lux on the lot, the moon ~0.35
K_LIGHT = 0.14
out = {"stages": STAGES}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def U(x, y, z=0.0):
    return unreal.Vector(y * 100.0, x * 100.0, z * 100.0)


def yaw_to(a, b):
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))


def look_rot(a, b):
    """Rotator turning +X from plan point a (x, y, z) toward b."""
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    return unreal.Rotator(roll=0, pitch=math.degrees(math.atan2(dz, math.hypot(dx, dy))), yaw=math.degrees(math.atan2(dx, dy)))


def seg_dist(p, a, b):
    ab = (b[0] - a[0], b[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / ((ab[0] ** 2 + ab[1] ** 2) or 1.0)))
    return math.dist(p, (a[0] + ab[0] * t, a[1] + ab[1] * t))


# the fleet-jump corridor (21 Oct 2026, mcgregor-placer; Kenny: "weird lights in the way of the fleet jump"): the fleet line
# from the kickflip run's start, past the line-up and 135 m beyond its centre (the landing and the whole run-out). Nothing
# that stands or shines is placed within COR_CLEAR m of it (the 8 m asked for + margin for the lamp banks / beam radii).
_fa, _fk = L["lines"]["fleet"][0], L["lines"]["fleet"][1]
_fd = (_fk[0] - _fa[0], _fk[1] - _fa[1])
_fu = (_fd[0] / math.hypot(*_fd), _fd[1] / math.hypot(*_fd))
_lr = L["lineup"]
_rc0 = (sum(v["p"][0] for v in _lr) / len(_lr), sum(v["p"][1] for v in _lr) / len(_lr))
COR_A, COR_B, COR_CLEAR = _fa, (_rc0[0] + _fu[0] * 135.0, _rc0[1] + _fu[1] * 135.0), 14.0


def cor_dist(p):
    return seg_dist(p, COR_A, COR_B)


def cut_to_corridor(base, aim, full):
    """Longest length (<= full m) of a beam from `base` toward `aim` (3D) whose plan path stays COR_CLEAR m off the corridor."""
    d3 = math.dist(base, aim) or 1.0
    for i in range(0, int(full) + 1):
        t_ = i / d3
        if cor_dist((base[0] + (aim[0] - base[0]) * t_, base[1] + (aim[1] - base[1]) * t_)) < COR_CLEAR:
            return float(max(0, i - 1))
    return float(full)


def lanes_clear(p, pad=4.0):
    """Outside every keep_clear corridor of the layout (run-up, fly-back landing, kickflip lane and run-out, ramp) and the
    fleet-jump corridor (COR_CLEAR + pad off the fleet line, out to 135 m past the line-up)."""
    return cor_dist(p) > COR_CLEAR + pad and all(seg_dist(p, c["a"], c["b"]) > c["half"] + pad for c in L.get("keep_clear", []))


def in_building(p, pad=4.0):
    for b in L.get("buildings") or ([L["white_building"]] if L.get("white_building") else []):
        r = math.radians(b["yaw"])
        dx, dy = p[0] - b["p"][0], p[1] - b["p"][1]
        a, w = dx * math.sin(r) + dy * math.cos(r), dx * math.cos(r) - dy * math.sin(r)
        if abs(a) < b["len"] / 2 + pad and abs(w) < b["wid"] / 2 + pad:
            return True
    return False


def stage_map():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    les.load_level(NIGHT)
    log("map", B.unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name())


def stage_kit():
    files = [ROOT + f"/SourceArt/McGregor/meshes/{n}.glb" for n in ("MG_StadiumLight", "MG_LightTruss", "MG_BeamCone")]
    log("kit", B.import_files(files, f"{B.DIR}/Kit"))


def mi(name, parent, scalars, vectors):
    return B.mi(name, parent, scalars, vectors)


def beam_master():
    """Light shaft: additive, unlit, two-sided; fades along its length (V) and toward its silhouette (facing ratio),
    which is how a shaft of light through haze looks: brightest where you look through the most of it."""
    path = "/Game/SkyCity/Pickups/Materials/M_SkyBeam"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
    else:
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_SkyBeam", "/Game/SkyCity/Pickups/Materials", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("two_sided", True)
    X = lambda cls, x, y: MEL.create_material_expression(m, cls, x, y)
    tc = X(unreal.MaterialExpressionTextureCoordinate, -1100, 0)
    v = X(unreal.MaterialExpressionComponentMask, -950, 0)
    for ch, on in zip("rgba", (False, True, False, False)):
        v.set_editor_property(ch, on)
    MEL.connect_material_expressions(tc, "", v, "")
    om = X(unreal.MaterialExpressionOneMinus, -800, 0)
    MEL.connect_material_expressions(v, "", om, "")
    pw = X(unreal.MaterialExpressionPower, -650, 0)
    MEL.connect_material_expressions(om, "", pw, "Base")
    e1 = X(unreal.MaterialExpressionConstant, -800, 120)
    e1.set_editor_property("r", 1.6)
    MEL.connect_material_expressions(e1, "", pw, "Exp")
    fr = X(unreal.MaterialExpressionFresnel, -800, 260)
    fr.set_editor_property("exponent", 1.2)
    fr.set_editor_property("base_reflect_fraction", 0.0)
    soft = X(unreal.MaterialExpressionOneMinus, -650, 260)
    MEL.connect_material_expressions(fr, "", soft, "")
    sp = X(unreal.MaterialExpressionPower, -500, 260)
    MEL.connect_material_expressions(soft, "", sp, "Base")
    e2 = X(unreal.MaterialExpressionConstant, -650, 380)
    e2.set_editor_property("r", 2.0)
    MEL.connect_material_expressions(e2, "", sp, "Exp")
    col = X(unreal.MaterialExpressionVectorParameter, -500, -200)
    col.set_editor_property("parameter_name", "Color")
    col.set_editor_property("default_value", unreal.LinearColor(0.8, 0.88, 1.0, 1))
    st = X(unreal.MaterialExpressionScalarParameter, -500, 420)
    st.set_editor_property("parameter_name", "Strength")
    st.set_editor_property("default_value", 0.03)
    m1 = X(unreal.MaterialExpressionMultiply, -350, 0)
    MEL.connect_material_expressions(pw, "", m1, "A")
    MEL.connect_material_expressions(sp, "", m1, "B")
    m2 = X(unreal.MaterialExpressionMultiply, -220, -100)
    MEL.connect_material_expressions(col, "", m2, "A")
    MEL.connect_material_expressions(m1, "", m2, "B")
    m3 = X(unreal.MaterialExpressionMultiply, -100, 0)
    MEL.connect_material_expressions(m2, "", m3, "A")
    MEL.connect_material_expressions(st, "", m3, "B")
    MEL.connect_material_property(m3, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def mats():
    em = EAL.load_asset("/Game/SkyCity/Pickups/Materials/M_SkyEmissive")
    jet = beam_master()
    return {
        "led_red": mi("MI_Night_LEDRed", em, {"Strength": 14.0}, {"Color": (1.0, 0.12, 0.03)}),
        "lamp": mi("MI_Night_Lamp", em, {"Strength": 40.0}, {"Color": (1.0, 0.97, 0.9)}),
        "screen": mi("MI_Night_Screen", em, {"Strength": 0.9}, {"Color": (0.42, 0.48, 0.75)}),
        "lamp_warm": mi("MI_Night_LampWarm", em, {"Strength": 18.0}, {"Color": (1.0, 0.85, 0.65)}),
        "beam": mi("MI_Night_Beam", jet, {"Strength": 0.018}, {"Color": (0.8, 0.88, 1.0)}),
        "beam_head": mi("MI_Night_BeamHead", jet, {"Strength": 0.08}, {"Color": (0.85, 0.9, 1.0)}),
        "beam_blue": mi("MI_Night_BeamBlue", jet, {"Strength": 0.05}, {"Color": (0.35, 0.55, 1.0)}),
        "search": mi("MI_Night_Search", jet, {"Strength": 0.25}, {"Color": (0.85, 0.9, 1.0)}),
        "laser": mi("MI_Night_Laser", jet, {"Strength": 3.0}, {"Color": (1.0, 0.05, 0.03)}),
    }


def stage_sky():
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags]:
            EAS.destroy_actor(a)
    for a in EAS.get_all_level_actors():
        if isinstance(a, unreal.DirectionalLight):
            c = a.get_component_by_class(unreal.DirectionalLightComponent)
            c.set_editor_property("intensity", 0.0)                      # the sun is down
            a.set_actor_rotation(unreal.Rotator(roll=0, pitch=12, yaw=-10), False)
        elif isinstance(a, unreal.SkyLight):
            c = a.get_component_by_class(unreal.SkyLightComponent)
            c.set_editor_property("intensity", 0.25)
            c.set_editor_property("lower_hemisphere_is_black", True)
            c.set_editor_property("lower_hemisphere_color", unreal.LinearColor(0.01, 0.012, 0.016, 1))
            c.recapture_sky()
        elif isinstance(a, unreal.ExponentialHeightFog):
            c = a.get_component_by_class(unreal.ExponentialHeightFogComponent)
            for k, v in (("fog_density", 0.045), ("fog_height_falloff", 0.14), ("start_distance", 0.0), ("fog_max_opacity", 1.0)):
                c.set_editor_property(k, v)
            c.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(0.004, 0.0065, 0.013, 1))
    # a cool moon, low in the east
    moon = EAS.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 5000), unreal.Rotator(roll=0, pitch=-32, yaw=115))
    moon.set_actor_label("Night_Moon")
    moon.tags = [TAG]
    mc = moon.get_component_by_class(unreal.DirectionalLightComponent)
    mc.set_editor_property("intensity", 0.25)
    mc.set_editor_property("light_color", unreal.Color(r=135, g=160, b=255, a=255))
    mc.set_editor_property("atmosphere_sun_light", False)
    # night exposure kept in a narrow range (the eye adapts to the lit lot, never brightens the dark fields), bloom, vignette
    pp = EAS.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    pp.set_actor_label("Night_PostProcess")
    pp.tags = [TAG]
    pp.set_editor_property("unbound", True)
    s = pp.get_editor_property("settings")
    # cool and ominous (Kenny): a touch darker, blue in the shadows, heavy vignette
    for k, v in (("auto_exposure_min_brightness", 1.0), ("auto_exposure_max_brightness", 2.4), ("auto_exposure_bias", -0.8),
                 ("bloom_intensity", 1.8), ("vignette_intensity", 0.65)):
        s.set_editor_property("override_" + k, True)
        s.set_editor_property(k, v)
    s.set_editor_property("override_scene_color_tint", True)
    s.set_editor_property("scene_color_tint", unreal.LinearColor(0.9, 0.95, 1.06, 1))
    pp.set_editor_property("settings", s)
    log("sky", "ok")


def spot(label, at, target, lumens, radius, outer, inner, color, shadows=False):
    a = EAS.spawn_actor_from_class(unreal.SpotLight, U(*at), look_rot(at, target))
    a.set_actor_label(label)
    a.tags = [TAG]
    a.set_folder_path("McGregorNight/Lights")
    c = a.get_component_by_class(unreal.SpotLightComponent)
    c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
    c.set_editor_property("intensity", lumens * K_LIGHT)
    c.set_editor_property("attenuation_radius", radius * 100.0)
    c.set_editor_property("outer_cone_angle", outer)
    c.set_editor_property("inner_cone_angle", inner)
    c.set_editor_property("cast_shadows", shadows)
    c.set_editor_property("light_color", unreal.Color(r=int(color[0] * 255), g=int(color[1] * 255), b=int(color[2] * 255), a=255))
    return a


def beam(label, mesh, mat, at, target, length, spread, spin=0.0):
    """A light shaft from `at` toward `target`, `length` m long, `spread` = base diameter per metre; `spin` deg/s
    turns it about the vertical in game (a moving head or a searchlight)."""
    a = EAS.spawn_actor_from_object(mesh, U(*at), look_rot(at, target))
    a.set_actor_label(label)
    a.tags = [TAG]
    a.set_folder_path("McGregorNight/Beams")
    c = a.static_mesh_component
    c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_collision_profile_name("NoCollision")
    c.set_editor_property("cast_shadow", False)
    c.set_material(0, mat)
    a.set_actor_scale3d(unreal.Vector(length, length * spread, length * spread))
    if spin:
        r = B.add_component(a, unreal.RotatingMovementComponent)
        r.set_editor_property("rotation_rate", unreal.Rotator(roll=0, pitch=0, yaw=spin))
        r.set_editor_property("rotation_in_local_space", False)
    return a


def override_slot(actor_label, slot_word, mat):
    n = 0
    for a in EAS.get_all_level_actors():
        if a.get_actor_label() != actor_label:
            continue
        for c in a.get_components_by_class(unreal.StaticMeshComponent):
            sm = c.static_mesh
            if not sm:
                continue
            for i, s in enumerate(sm.get_editor_property("static_materials")):
                if slot_word in str(s.get_editor_property("material_slot_name")):
                    c.set_material(i, mat)
                    n += 1
    return n


PARTS = json.load(open(ROOT + "/SourceArt/Vehicles/parts.json"))


def stage_lights():
    """Kenny: "get lighting right so it feels cool and ominous". Reveal night from his photos and the two videos: a black
    lot under a few cold white stadium banks (pools of light with dark between them), haze, the red LED show wall with its
    uplights and seating behind the ramp and the line-up, red uplights washing the long white building's facade, the
    line-up's headlights on, moving heads and lasers cutting the haze, searchlights over the site."""
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags] and not isinstance(a, (unreal.DirectionalLight, unreal.PostProcessVolume)):
            EAS.destroy_actor(a)
    M = mats()
    cone = B.kit_mesh("MG_BeamCone")
    mast = B.kit_mesh("MG_StadiumLight")
    truss = B.kit_mesh("MG_LightTruss")
    COOL = (0.78, 0.87, 1.0)
    lot = L["lot"]
    C = (sum(p[0] for p in lot) / 4, sum(p[1] for p in lot) / 4)
    ramp = L["ramp"]["p"]
    X = L["x_centre"]
    ry = math.radians(L["ramp"]["yaw"])
    t = (math.sin(ry), math.cos(ry))                              # the car's travel up the ramp (plan)
    side = (-t[1], t[0])                                          # left of the travel
    g = lambda x, y: B.ground_at(x, y)
    zr = g(*ramp)
    focus = ((X[0] + ramp[0]) / 2, (X[1] + ramp[1]) / 2)
    # stadium masts: the lot's corners and two mid-sides, 8 m out, aimed between the X and the ramp. Cold white, and
    # not too many: pools of light with the dark lot between them is what makes it ominous
    spots = []
    for i, p in enumerate(lot):
        q = lot[(i + 1) % 4]
        spots.append(p)
        if i in (0, 2):
            spots.append(((p[0] + q[0]) / 2, (p[1] + q[1]) / 2))
    masts = []
    for k, p in enumerate(spots):
        d = math.hypot(p[0] - C[0], p[1] - C[1])
        x, y = p[0] + (p[0] - C[0]) / d * 8, p[1] + (p[1] - C[1]) / d * 8
        if not lanes_clear((x, y), 6.0) or in_building((x, y)):
            continue                                              # never in a lane, the landing zone or a building
        masts.append((x, y, g(x, y), yaw_to((x, y), focus)))
    xfs = [unreal.Transform(U(x, y, z), unreal.Rotator(roll=0, pitch=0, yaw=yw + B.KIT_FRONT), unreal.Vector(1, 1, 1)) for x, y, z, yw in masts]
    B.instanced("Night_StadiumMasts", mast, xfs, 400000, shadows=True, folder="Night", collide=True, tags=("NoWallRide", TAG))
    for k, (x, y, z, yw) in enumerate(masts):
        f = (math.sin(math.radians(yw)), math.cos(math.radians(yw)))
        head = (x + f[0] * 1.0, y + f[1] * 1.0, z + 22.4)
        tgt = (focus[0] + (k % 3 - 1) * 14.0, focus[1] + (k % 2) * 12.0, g(*focus) + 2.0)
        spot(f"Night_Flood_{k}", head, tgt, 130000.0, 260.0, 34.0, 12.0, COOL, shadows=k < 2)
        # (no flood shafts: at this size the fake cones read as grey domes; the haze and the narrow beams carry it)
    override_slot("Night_StadiumMasts", "LampLens", M["lamp"])
    # the two banks nearest the line-up also throw a beam on it, so the five read against the dark from the lot
    row = L["lineup"]
    rc = (sum(v["p"][0] for v in row) / len(row), sum(v["p"][1] for v in row) / len(row))
    for k, (x, y, z, yw) in enumerate(sorted(masts, key=lambda m: math.dist(m[:2], rc))[:2]):
        spot(f"Night_LineupFlood_{k}", (x, y, z + 22.0), (rc[0], rc[1], g(*rc) + 1.0), 70000.0, 220.0, 12.0, 5.0, COOL, shadows=k == 0)
    for it in L["items"]:
        if it["mesh"] != "MG_LightTower":
            continue
        for k, p in enumerate(it["at"]):
            yw = math.radians(p["yaw"])
            f = (math.sin(yw), math.cos(yw))
            z = g(p["p"][0], p["p"][1])
            head = (p["p"][0] + f[0] * 0.9, p["p"][1] + f[1] * 0.9, z + 8.9)
            spot(f"Night_Tower_{k}", head, (head[0] + f[0] * 18, head[1] + f[1] * 18, z), 30000.0, 70.0, 55.0, 30.0, COOL)
    override_slot("Demo_MG_LightTower", "LampLens", M["lamp"])
    # the ramp: red LED edges, blue uplights on its truss, two cold floods on the deck face
    override_slot("Demo_MG_Ramp", "RampTrim", M["led_red"])
    tower = (ramp[0] + t[0] * 9.8, ramp[1] + t[1] * 9.8)          # behind the vertical section
    for s_ in (-1, 1):
        base = (tower[0] + side[0] * 5.0 * s_ - t[0] * 4.0, tower[1] + side[1] * 5.0 * s_ - t[1] * 4.0, zr + 0.5)
        spot(f"Night_TrussBlue_{s_}", base, (tower[0], tower[1], zr + 24.0), 60000.0, 60.0, 30.0, 12.0, (0.25, 0.45, 1.0))
        beam(f"Night_TrussBlueBeam_{s_}", cone, M["beam_blue"], base, (tower[0], tower[1], zr + 26.0), 28.0, 0.35)
        deck = (ramp[0] - t[0] * 30 + side[0] * 12 * s_, ramp[1] - t[1] * 30 + side[1] * 12 * s_, zr + 1.0)
        spot(f"Night_DeckFlood_{s_}", deck, (ramp[0] + t[0] * 4, ramp[1] + t[1] * 4, zr + 12.0), 80000.0, 90.0, 28.0, 12.0, COOL)
    # (zr above is a trace at the ramp's origin, which lands on the overhang/its collision block ~26 m up, so those
    # lights sit high, which is how the top of the ramp got lit; the lot under the ramp is zg)
    # the ramp from underneath (Kenny, 20 Oct round 2: "maybe more like floodlights just at the base"): four small floods
    # on the ground beside its foot, two a side, aimed up so they wash the climb, the vertical and the inverted run over
    # the approach in the same cold white as the floods on its top; tiny black housings with a glowing lens, no
    # collision, no shadows (cheap on the M1)
    zg = g(ramp[0] - t[0] * 10.0, ramp[1] - t[1] * 10.0)          # the level patch the ramp stands on (build_mcgregor_ue.py)
    under = []
    for s_ in (-1, 1):
        for fa, tf, tz in ((-3.0, 1.5, 14.0), (4.5, -3.5, 21.0)):
            base = (ramp[0] + t[0] * fa + side[0] * 4.4 * s_, ramp[1] + t[1] * fa + side[1] * 4.4 * s_, zg + 0.22)
            tgt = (ramp[0] + t[0] * tf + side[0] * 1.0 * s_, ramp[1] + t[1] * tf + side[1] * 1.0 * s_, zg + tz)
            spot(f"Night_RampUnder_{'L' if s_ < 0 else 'R'}{'f' if fa < 0 else 'b'}", base, tgt, 42000.0, 45.0, 34.0, 20.0, COOL)
            under.append((base, tgt))
    cube = EAL.load_asset("/Engine/BasicShapes/Cube")
    housing, lens = [], []
    for base, tgt in under:
        r = look_rot(base, tgt)
        fwd = r.get_forward_vector()
        housing.append(unreal.Transform(U(*base), r, unreal.Vector(0.42, 0.34, 0.26)))
        lens.append(unreal.Transform(U(*base) + fwd * 21.5, r, unreal.Vector(0.012, 0.28, 0.2)))
    B.instanced("Night_RampUnderFixtures", cube, housing, 200000, shadows=False, folder="Night", collide=False, tags=("NoWallRide", TAG))
    B.instanced("Night_RampUnderLenses", cube, lens, 200000, shadows=False, folder="Night", collide=False, tags=("NoWallRide", TAG))
    blk = EAL.load_asset("/Game/City/Street/Materials/MI_BlackPlastic")
    for a in EAS.get_all_level_actors():
        if a.get_actor_label() in ("Night_RampUnderFixtures", "Night_RampUnderLenses"):
            for c in a.get_components_by_class(unreal.StaticMeshComponent):
                c.set_material(0, blk if a.get_actor_label().endswith("Fixtures") else M["lamp"])
    out["ramp_ground"] = {"zr_origin_trace": round(zr, 2), "zg_level_patch": round(zg, 2)}
    # the show wall: red LED face, its uplight fixtures lit, red light washing the seating, white beams up into the haze
    for lab in ("Demo_MG_ShowWall", "Demo_MG_LEDStrip", "Demo_MG_LanePost"):
        override_slot(lab, "LEDRed", M["led_red"])
    for a in EAS.get_all_level_actors():                          # the LED ribbons (slot 1 of the demo stage's line mesh)
        if a.get_actor_label() == "Demo_Lines":
            for c in a.get_components_by_class(unreal.StaticMeshComponent):
                c.set_material(1, M["led_red"])
    override_slot("Demo_MG_ShowWall", "LampLens", M["lamp"])
    walls = next((it["at"] for it in L["items"] if it["mesh"] == "MG_ShowWall"), [])
    for k, w in enumerate(walls):
        yw = math.radians(w["yaw"])
        run = (math.sin(yw), math.cos(yw))                        # the wall's run (mesh local +Y after KIT_FRONT)
        face = (math.sin(yw + math.pi / 2), math.cos(yw + math.pi / 2))   # the LED face looks this way (toward the X)
        z = g(w["p"][0], w["p"][1])
        for j in range(3):
            o = 1.7 + j * 3.3
            fx = (w["p"][0] + run[0] * o, w["p"][1] + run[1] * o, z + 1.6)
            aim = (fx[0] - face[0] * 6.0 + run[0] * (j - 1) * 4.0, fx[1] - face[1] * 6.0 + run[1] * (j - 1) * 4.0, fx[2] + 60.0)
            beam(f"Night_WallBeam_{k}_{j}", cone, M["beam_head"], fx, aim, 70.0, 0.05, spin=(6.0 if (k + j) % 2 else -6.0) if j == 1 else 0.0)
        mid = (w["p"][0] + run[0] * 5.0 + face[0] * 3.0, w["p"][1] + run[1] * 5.0 + face[1] * 3.0, z + 0.3)
        spot(f"Night_WallWash_{k}", mid, (mid[0] - face[0] * 6.0, mid[1] - face[1] * 6.0, z + 4.0), 22000.0, 30.0, 60.0, 40.0, (1.0, 0.05, 0.03))
    # the long white buildings: red uplights along the facade that faces the stage and the lot (drone shot)
    sp = L.get("stage", {}).get("p", X)
    for bi, wb in enumerate(L.get("buildings") or [L["white_building"]]):
        byw = math.radians(wb["yaw"])
        ax = (math.sin(byw), math.cos(byw))                       # its long axis
        ny = (math.sin(byw + math.pi / 2), math.cos(byw + math.pi / 2))
        if (sp[0] - wb["p"][0]) * ny[0] + (sp[1] - wb["p"][1]) * ny[1] < 0:
            ny = (-ny[0], -ny[1])
        n = max(6, int(wb["len"] / 6.0))
        for k in range(n):
            o = (k + 0.5) / n * wb["len"] - wb["len"] / 2
            bx, by = wb["p"][0] + ax[0] * o + ny[0] * (wb["wid"] / 2 + 1.2), wb["p"][1] + ax[1] * o + ny[1] * (wb["wid"] / 2 + 1.2)
            zb = g(bx, by)                                        # the ground just outside (a trace at the centre hits the roof)
            base = (bx, by, zb + 0.3)
            tgt = (base[0] - ny[0] * 1.6, base[1] - ny[1] * 1.6, zb + wb["h"])
            spot(f"Night_FacadeRed_{bi}_{k}", base, tgt, 26000.0, 35.0, 38.0, 20.0, (1.0, 0.04, 0.03))
        # the end facing the stage too (the drone shot's lit corner)
        ends = sorted((1, -1), key=lambda e: math.dist(sp, (wb["p"][0] + ax[0] * e * wb["len"] / 2, wb["p"][1] + ax[1] * e * wb["len"] / 2)))
        e = ends[0]
        for k in range(max(3, int(wb["wid"] / 8.0))):
            o = (k + 0.5) / max(3, int(wb["wid"] / 8.0)) * wb["wid"] - wb["wid"] / 2
            bx = wb["p"][0] + ax[0] * e * (wb["len"] / 2 + 1.2) + ny[0] * o
            by = wb["p"][1] + ax[1] * e * (wb["len"] / 2 + 1.2) + ny[1] * o
            zb = g(bx, by)
            spot(f"Night_FacadeEnd_{bi}_{k}", (bx, by, zb + 0.3), (bx - ax[0] * e * 1.6, by - ax[1] * e * 1.6, zb + wb["h"]), 26000.0, 35.0, 38.0, 20.0, (1.0, 0.04, 0.03))
    # the line-up: headlights on (spots from the lamp sockets), tail lights glowing
    for v in L["lineup"]:
        info = PARTS.get(v["name"], {})
        sk = info.get("lights", {}).get("sockets", {})
        yw = math.radians(v["yaw"])
        f = (math.sin(yw), math.cos(yw))
        lf = (-math.cos(yw), math.sin(yw))                        # the vehicle's left, in plan
        z = g(v["p"][0] + f[0] * 8.0, v["p"][1] + f[1] * 8.0)     # the lot in front (a trace at the car hits its roof)
        for nm, (sx, sy, sz) in sk.items():
            at = (v["p"][0] + f[0] * sx + lf[0] * sy, v["p"][1] + f[1] * sx + lf[1] * sy, z + sz)
            if nm.startswith("Headlight"):
                spot(f"Night_Head_{v['name']}_{nm[-1]}", at, (at[0] + f[0] * 20, at[1] + f[1] * 20, z), 9000.0, 60.0, 30.0, 14.0, (1.0, 0.97, 0.92))
            else:
                a = EAS.spawn_actor_from_class(unreal.PointLight, U(*at), unreal.Rotator(0, 0, 0))
                a.set_actor_label(f"Night_Tail_{v['name']}_{nm[-1]}")
                a.tags = [TAG]
                a.set_folder_path("McGregorNight/Lights")
                c = a.get_component_by_class(unreal.PointLightComponent)
                c.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
                c.set_editor_property("intensity", 600.0 * K_LIGHT)
                c.set_editor_property("attenuation_radius", 400.0)
                c.set_editor_property("cast_shadows", False)
                c.set_editor_property("light_color", unreal.Color(r=255, g=12, b=8, a=255))
    # moving-head truss to the right of the run-up (the kickflip lane and the line-up are on its left), square to the
    # ramp: its heads light the deck from the side and sweep beams up past the ramp; red lasers fan off it
    # (on the side of the run-up away from the line-up and its kickflip lane)
    rcx = sum(v["p"][0] for v in L["lineup"]) / len(L["lineup"]) - ramp[0]
    rcy = sum(v["p"][1] for v in L["lineup"]) / len(L["lineup"]) - ramp[1]
    away = -1.0 if (rcx * side[0] + rcy * side[1]) > 0 else 1.0     # -1: the line-up is on the left, so go right

    # 21 Oct 2026 (mcgregor-placer; Kenny: "weird lights in the way of the fleet jump"): "away from the line-up" put the truss
    # beside the START of the kickflip run (the fleet line begins on the same side of the run-up as the truss: the lane
    # crosses the run-up at the X), 6.5 m off the line with its floods, moving heads and lasers. The side is now chosen by
    # the fleet-jump corridor (the fleet line from its start, past the row and 135 m beyond: the landing and run-out):
    # whichever side puts the truss farthest from it, and it must stay >= 14 m clear of it.
    _fa, _fk = L["lines"]["fleet"][0], L["lines"]["fleet"][1]
    _fd = (_fk[0] - _fa[0], _fk[1] - _fa[1])
    _fn = math.hypot(*_fd)
    _fu = (_fd[0] / _fn, _fd[1] / _fn)
    _lr = L["lineup"]
    _rc = (sum(v["p"][0] for v in _lr) / len(_lr), sum(v["p"][1] for v in _lr) / len(_lr))
    _far = (_rc[0] + _fu[0] * 135.0, _rc[1] + _fu[1] * 135.0)

    def truss_at(a_):
        return (ramp[0] - t[0] * 22.0 + a_ * side[0] * 24.0, ramp[1] - t[1] * 22.0 + a_ * side[1] * 24.0)
    _d0, _d1 = seg_dist(truss_at(away), _fa, _far), seg_dist(truss_at(-away), _fa, _far)
    if _d1 > _d0:
        away = -away
    tp = truss_at(away)
    out["truss_to_fleet_corridor_m"] = {"chosen": round(seg_dist(tp, _fa, _far), 1), "other_side": round(min(_d0, _d1), 1)}
    B.instanced("Night_LightTruss", truss, [unreal.Transform(U(tp[0], tp[1], g(*tp)), unreal.Rotator(roll=0, pitch=0, yaw=math.degrees(math.atan2(t[0], t[1])) + 180 + B.KIT_FRONT), unreal.Vector(1, 1, 1))],
                400000, shadows=True, folder="Night", collide=False, tags=("NoWallRide", TAG))
    override_slot("Night_LightTruss", "LampLens", M["lamp"])
    override_slot("Night_LightTruss", "RampTrim", M["led_red"])
    for s_, o in ((0, -4.0), (1, 4.0)):
        hx, hy = tp[0] + side[0] * o, tp[1] + side[1] * o
        spot(f"Night_TrussFlood_{s_}", (hx, hy, g(hx, hy) + 3.2), (ramp[0] + t[0] * 5, ramp[1] + t[1] * 5, zr + 11.0), 100000.0, 90.0, 24.0, 9.0, COOL)
    for i in range(6):
        o = -5.0 + i * 2.0
        hx, hy = tp[0] + side[0] * o, tp[1] + side[1] * o
        head = (hx, hy, g(hx, hy) + 3.1)
        aim = (hx + t[0] * 40 + side[0] * (o * 3), hy + t[1] * 40 + side[1] * (o * 3), head[2] + 70.0)
        beam(f"Night_MovingHead_{i}", cone, M["beam_head"], head, aim, 110.0, 0.055, spin=(14.0 if i % 2 else -14.0))
    for i in range(8):
        o = -4.2 + i * 1.2
        hx, hy = tp[0] + side[0] * o, tp[1] + side[1] * o
        head = (hx, hy, g(hx, hy) + 2.6)
        aim = (hx + t[0] * 120 + side[0] * o * 14, hy + t[1] * 120 + side[1] * o * 14, head[2] + 160.0)
        beam(f"Night_Laser_{i}", cone, M["laser"], head, aim, 400.0, 0.0015, spin=(4.0 if i % 2 else -4.0))
    # the stage: LED edge, screens glowing, the truss masts' banks on the deck, blue-white beam fans behind it (drone shot)
    st = L.get("stage")
    if st:
        override_slot("Demo_UV_Stage", "LEDRed", M["led_red"])
        override_slot("Demo_UV_LEDScreen", "LEDScreen", M["screen"])
        override_slot("Demo_UV_LightMast", "LampLens", M["lamp"])
        override_slot("Demo_UV_LightMast", "RedLamp", M["led_red"])
        zs = g(*st["p"])
        sy = math.radians(st["yaw"])
        fwd = (math.sin(sy), math.cos(sy))                        # the stage front faces the audience
        axs = (math.sin(sy - math.pi / 2), math.cos(sy - math.pi / 2))
        for it in L["items"]:
            if it["mesh"] != "UV_LightMast":
                continue
            for k, p in enumerate(it["at"]):
                yw = math.radians(p["yaw"])
                f = (math.sin(yw), math.cos(yw))
                z = g(p["p"][0], p["p"][1])
                head = (p["p"][0] + f[0] * 0.6, p["p"][1] + f[1] * 0.6, z + 15.5)
                spot(f"Night_Mast_{k}", head, (st["p"][0], st["p"][1], zs + 1.5), 60000.0, 120.0, 26.0, 10.0, COOL, shadows=k == 0)
        for s_ in (-1, 1):                                        # beam fans from the back corners of the stage
            for i in range(7):
                base = (st["p"][0] + axs[0] * s_ * (st["len"] / 2 - 2.0 - i * 1.1) - fwd[0] * (st["dep"] / 2 - 0.5),
                        st["p"][1] + axs[1] * s_ * (st["len"] / 2 - 2.0 - i * 1.1) - fwd[1] * (st["dep"] / 2 - 0.5), zs + 1.4)
                spread = (i - 3) * 9.0
                a = math.radians(st["yaw"] + 180 + s_ * (35 + spread))
                aim = (base[0] + math.sin(a) * 40.0, base[1] + math.cos(a) * 40.0, base[2] + 38.0)
                fl_ = cut_to_corridor(base, aim, 90.0)                    # never across the fleet-jump corridor
                if fl_ >= 8.0:
                    beam(f"Night_StageFan_{s_}_{i}", cone, M["beam_blue"] if i % 2 else M["beam_head"], base, aim, fl_, 0.04 * 90.0 / fl_)
        # the crowd in front of the stage: a soft warm wash so people (and the car) read on the dark asphalt
        aud = st.get("audience", st["p"])
        spot("Night_AudienceWash", (st["p"][0] + fwd[0] * 2, st["p"][1] + fwd[1] * 2, zs + 14.0), (aud[0], aud[1], g(*aud)), 40000.0, 90.0, 50.0, 30.0, (1.0, 0.25, 0.18))
    # the cranes' light rigs: cold white onto the lot and the ramp
    override_slot("Demo_UV_CraneBoom", "LampLens", M["lamp"])
    for it in L["items"]:
        if it["mesh"] != "UV_CraneBoom":
            continue
        for k, p in enumerate(it["at"]):
            yw = math.radians(p["yaw"])
            f = (math.sin(yw), math.cos(yw))
            z = g(p["p"][0], p["p"][1])
            rig = (p["p"][0] + f[0] * 7.5, p["p"][1] + f[1] * 7.5, z + 29.0)     # the rig hangs ~7.4 m out, ~29 m up
            tgt = (rig[0] + f[0] * 45.0, rig[1] + f[1] * 45.0, z)
            spot(f"Night_Crane_{k}", rig, tgt, 110000.0, 160.0, 30.0, 12.0, COOL, shadows=False)
    # searchlights at the lot's corners, turning slowly
    for k, p in enumerate(lot):
        d = math.hypot(p[0] - C[0], p[1] - C[1])
        x, y = p[0] + (p[0] - C[0]) / d * 14, p[1] + (p[1] - C[1]) / d * 14
        dc = cor_dist((x, y))
        if dc < COR_CLEAR + 4.0:                                  # this corner is the landing / run-out: slide the light off the line
            nl = math.hypot(COR_B[0] - COR_A[0], COR_B[1] - COR_A[1]) or 1.0
            sgn = 1.0 if ((x - COR_A[0]) * (COR_B[1] - COR_A[1]) - (y - COR_A[1]) * (COR_B[0] - COR_A[0])) > 0 else -1.0   # side of the line the light is on
            nx, ny = (COR_B[1] - COR_A[1]) / nl, -(COR_B[0] - COR_A[0]) / nl
            x, y = x + sgn * nx * (COR_CLEAR + 4.0 - dc + 6.0), y + sgn * ny * (COR_CLEAR + 4.0 - dc + 6.0)
            out.setdefault("searchlights_moved", []).append({"k": k, "from_corridor_m": round(dc, 1), "to_corridor_m": round(cor_dist((x, y)), 1)})
        z = g(x, y) + 1.0
        aim = (x + (p[0] - C[0]) / d * 150, y + (p[1] - C[1]) / d * 150, z + 420.0)
        beam(f"Night_Search_{k}", cone, M["search"], (x, y, z), aim, 600.0, 0.012, spin=(7.0 if k % 2 else -9.0))
    log("lights", {"masts": len(masts), "spots": len([a for a in EAS.get_all_level_actors() if isinstance(a, unreal.SpotLight) and TAG in [str(x) for x in a.tags]])})


def stage_save():
    B.stage_save()
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
