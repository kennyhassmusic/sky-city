"""Kenny's Tesla line-up in McGregor (and the vehicle assets the car can drive as): imports the split bodies and wheels
(Scripts/vehicles/blender_split_lineup.py -> SourceArt/Vehicles), gives the paint a clear coat (it doesn't survive
FBX/glTF) and the light lenses emissive materials (headlights, tail lights, markers on: reveal night), then places the
five side by side where Saved/McGregor/demo_layout.json puts them (Kenny's render: fronts flush, ~1.15 m gaps,
Model 3, Model Y, Semi, Cybertruck, Cybercab from left to right seen from the front).
Licences: see CREDITS_AND_LICENCES.txt in the lineup source folder ($SKYCITY_LINEUP_SRC, default Saved/McGregorLineup) (Semi = editorial placeholder).
Heights: each car stands on the highest ground under its four tyres (the lot is graded by build_mcgregor_ue.py's demo
stage from the terrain under it, so re-running that stage can move the lot surface: re-run `place save` after it,
in McGregor and in McGregorNight, which is a copy of McGregor.umap with its own line-up).
Run in the editor with McGregor (or McGregorNight) loaded: py Scripts/vehicles/lineup_ue.py [import] [materials] [place] [save]
Placeholders (public build, 21 Oct 2026): the place stage puts the blocky stand-ins from /Game/Vehicles/Placeholder
(Scripts/vehicles/PLACEHOLDERS.md) in the line-up instead of the real meshes of the cars in the [SkyFleet] PlaceholderCars list of
Config/DefaultGame.ini, which is what the game's SkyFleet::MeshPath reads (Scripts/build/set_vehicle_flavor.py public|personal
writes it; personal = an empty list = the real meshes, as before). Same part names and pivots, so the placement is identical.
`place placeholders=Semi,Model3` names the cars yourself, `placeholders=none` forces the real ones whatever the ini says. Because
the list is read by default, the chains that rerun `lineup_ue.py place save` (mcgfix_chain.py, unveil_chain.py) keep the flavour.
The place stage replaces the whole line-up. Only `place` looks at this.
(`import meshes materials` needs no particular map: it only touches /Game/Vehicles/Tesla. `import` and `meshes` can take
car names and `parts=` part names, e.g. `import=Semi,ModelY meshes=Semi,ModelY parts=Body materials` re-imports just
those bodies after a re-split; `glass=thin` builds the glass on the Thin Translucent shading model instead.)
Materials stage (vehicle-models, 20 Oct 2026): slots are matched on their name without Blender's .001 suffix (glTF
import turns it into _001, which used to leave the Model 3's second paint slot and all of the Model Y's paint on the
imported materials); the windows of every vehicle get one car-glass material (M_CarGlass: translucent, lit per pixel
so it picks up sky and sun reflections, single-sided, glancing angles more opaque; the imported glass was black at
0.35 opacity with no specular (Cybertruck: looked missing) or opaque grey (Model 3)); the Cybertruck's textured
lamp emitters (*_Inner, a white/amber/red atlas) keep their atlas instead of glowing one flat colour; imported
materials whose glTF specular was 0 (the Model Y's trims) get the default back.
Writes Saved/MCPScripts/out_lineup.json."""
import glob, json, math, re, sys, time, traceback, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_lineup.json"
PARTS_FILE = ROOT + "/SourceArt/Vehicles/parts.json"   # the licensed models' parts (not in the public repo)
if not os.path.exists(PARTS_FILE):
    PARTS_FILE = ROOT + "/Scripts/vehicles/placeholder_parts.json"   # the stand-ins: same names, sizes and pivots
PARTS = json.load(open(PARTS_FILE))
LAYOUT = json.load(open(ROOT + "/Saved/McGregor/demo_layout.json"))
DIR = "/Game/Vehicles/Tesla"
PLACE_DIR = "/Game/Vehicles/Placeholder"           # the blocky stand-ins (placeholders_ue.py); same names under <Car>/
TAG = "MG_Lineup"
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
MEL = unreal.MaterialEditingLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
ARGS = sys.argv[1:] or ["import", "meshes", "materials", "place", "save"]
STAGES = [a.split("=")[0] for a in ARGS if a.split("=")[0] in ("import", "meshes", "materials", "place", "save")]
ONLY = {a.split("=")[0]: a.split("=", 1)[1].split(",") for a in ARGS if "=" in a}
out = {"stages": ARGS}
PAINT = {"Paint_Gold": ((0.72, 0.58, 0.36), 0.6, 0.28), "Paint_BlueGloss": ((0.015, 0.04, 0.2), 0.3, 0.2),
         "Paint_RedGloss": ((0.42, 0.006, 0.008), 0.35, 0.2), "Paint_Silver": ((0.62, 0.63, 0.65), 0.85, 0.25)}
LIGHT = {"Headlight": ((1.0, 0.97, 0.92), 12.0), "Taillight": ((1.0, 0.03, 0.02), 6.0),
         "MarkerLight": ((1.0, 0.45, 0.02), 5.0), "AuxLight": ((1.0, 0.97, 0.92), 8.0)}
# textured lamp emitters: keep the imported glTF material's atlas (base colour = emissive), at this emissive strength
LAMP_ATLAS = {"Headlight_Inner": 2.0, "Taillight_Inner": 2.0}
# window slots per vehicle (exact imported slot names; the Model 3's windows are an outer and an inner shell)
GLASS = {"Model3": ("EXT_Window", "INT_Window"), "ModelY": ("glass_base", "glass_roof_panorama"),
         "Cybertruck": ("glass_windows_mat",), "Robotaxi": ("Material_007",), "Semi": ("glass",)}
# black ceramic frit / smoked trim on the glass (the Model 3's roof-glass edges and tail-lamp surrounds were matte
# near-black, which read as slate next to the grey windows): glossy black
FRIT = {"Model3": ("Black_Glass",)}
# car glass: tint (base colour), opacity face-on and at glancing angles, roughness, specular
GLASS_LOOK = {"Tint": (0.004, 0.005, 0.006), "Opacity": 0.6, "EdgeOpacity": 0.97, "Roughness": 0.02, "Specular": 1.0,
              "Transmittance": (0.30, 0.34, 0.36)}
# Thin Translucent: Opacity is only the coverage of the (black) coat, the specular sits on top at full strength and the
# background is filtered by Transmittance (the tint)
GLASS_LOOK_THIN = {"Tint": (0.0, 0.0, 0.0), "Opacity": 0.04, "EdgeOpacity": 0.3, "Roughness": 0.02, "Specular": 1.0,
                   "Transmittance": (0.20, 0.23, 0.25)}
GLASS_THIN = "glass=thin" in sys.argv[1:]          # try the Thin Translucent shading model instead of Default Lit
if GLASS_THIN:
    GLASS_LOOK = GLASS_LOOK_THIN


def slot_base(s):
    """Blender's duplicate suffix (.001, or _001 after the glTF import) off a slot name."""
    return re.sub(r"[._]\d{3}$", "", s)


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1))


def stage_import():
    n = 0
    for name in PARTS:
        if "import" in ONLY and name not in ONLY["import"]:
            continue
        tasks = []
        for f in sorted(glob.glob(f"{ROOT}/SourceArt/Vehicles/{name}/*.glb")):
            if "parts" in ONLY and f.split("/")[-1][:-4].split("_", 2)[-1] not in ONLY["parts"]:
                continue                                    # e.g. parts=Body: re-import the body only
            t = unreal.AssetImportTask()
            t.set_editor_property("filename", f)
            t.set_editor_property("destination_path", f"{DIR}/{name}")
            t.set_editor_property("automated", True)
            t.set_editor_property("replace_existing", True)
            t.set_editor_property("save", True)
            tasks.append(t)
        AT.import_asset_tasks(tasks)
        n += len(tasks)
    log("import", n)


def paint_master():
    path = f"{DIR}/Materials/M_CarPaint"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
    else:
        m = AT.create_asset("M_CarPaint", f"{DIR}/Materials", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_CLEAR_COAT)

    def sp(name, v, x, y):
        e = MEL.create_material_expression(m, unreal.MaterialExpressionScalarParameter, x, y)
        e.set_editor_property("parameter_name", name)
        e.set_editor_property("default_value", v)
        return e
    c = MEL.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -400, -100)
    c.set_editor_property("parameter_name", "Tint")
    c.set_editor_property("default_value", unreal.LinearColor(0.5, 0.5, 0.5, 1))
    MEL.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(sp("Metallic", 0.4, -400, 50), "", unreal.MaterialProperty.MP_METALLIC)
    MEL.connect_material_property(sp("Roughness", 0.3, -400, 130), "", unreal.MaterialProperty.MP_ROUGHNESS)
    # ClearCoat / ClearCoatRoughness (CustomData0/1) aren't reachable from Python; unconnected they default to a full
    # coat at 0.1 roughness, which is the showroom gloss we want
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def glass_master():
    """M_CarGlass: one window material for every vehicle (line-up, traffic, the drivable cars). Translucent and lit per
    pixel ("Surface ForwardShading"), so the sun's highlight and the sky/reflection captures show on it with no ray
    tracing; single-sided (the models' windows are closed shells or outer+inner shells, so one layer per window draws
    and the far side isn't doubled); opacity rises toward glancing angles (Fresnel) like real glass."""
    path = f"{DIR}/Materials/M_CarGlass"
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
    else:
        m = AT.create_asset("M_CarGlass", f"{DIR}/Materials", unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    m.set_editor_property("two_sided", False)
    for k, v in (("used_with_static_lighting", False),):
        try:
            m.set_editor_property(k, v)
        except Exception:
            pass

    def sp(name, v, x, y):
        e = MEL.create_material_expression(m, unreal.MaterialExpressionScalarParameter, x, y)
        e.set_editor_property("parameter_name", name)
        e.set_editor_property("default_value", v)
        return e
    c = MEL.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -500, -200)
    c.set_editor_property("parameter_name", "Tint")
    c.set_editor_property("default_value", unreal.LinearColor(*GLASS_LOOK["Tint"], 1))
    MEL.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(sp("Specular", GLASS_LOOK["Specular"], -500, -40), "", unreal.MaterialProperty.MP_SPECULAR)
    MEL.connect_material_property(sp("Roughness", GLASS_LOOK["Roughness"], -500, 40), "", unreal.MaterialProperty.MP_ROUGHNESS)
    fr = MEL.create_material_expression(m, unreal.MaterialExpressionFresnel, -700, 260)
    fr.set_editor_property("exponent", 4.0)
    fr.set_editor_property("base_reflect_fraction", 0.04)
    lp = MEL.create_material_expression(m, unreal.MaterialExpressionLinearInterpolate, -300, 200)
    MEL.connect_material_expressions(sp("Opacity", GLASS_LOOK["Opacity"], -700, 120), "", lp, "A")
    MEL.connect_material_expressions(sp("EdgeOpacity", GLASS_LOOK["EdgeOpacity"], -700, 190), "", lp, "B")
    MEL.connect_material_expressions(fr, "", lp, "Alpha")
    MEL.connect_material_property(lp, "", unreal.MaterialProperty.MP_OPACITY)
    if GLASS_THIN:
        # Thin Translucent: the background is multiplied by Transmittance (tinted, not greyed) and the specular isn't
        # scaled down by the opacity, so the reflections stay at full strength on see-through glass
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_THIN_TRANSLUCENT)
        tr = MEL.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -500, 360)
        tr.set_editor_property("parameter_name", "Transmittance")
        tr.set_editor_property("default_value", unreal.LinearColor(*GLASS_LOOK["Transmittance"], 1))
        to = MEL.create_material_expression(m, unreal.MaterialExpressionThinTranslucentMaterialOutput, -100, 360)
        if not any(MEL.connect_material_expressions(tr, "", to, pin) for pin in ("TransmittanceColor", "Transmittance Color")):
            log("glass_thin_pin", "could not connect the transmittance pin")
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def lamp_atlas(path, strength):
    """A child of the imported glTF lamp material (it keeps the atlas texture as base colour and emissive), with the
    emissive strength set; None if the imported material isn't there."""
    if not EAL.does_asset_exist(path):
        return None
    src = EAL.load_asset(path)
    if isinstance(src, unreal.MaterialInstanceConstant) and src.get_editor_property("parent") and "/Game/Vehicles/Tesla/Materials/" in src.get_editor_property("parent").get_path_name():
        src = src.get_editor_property("parent")             # already one of ours: rebuild from its imported parent
    name = "MI_Car_Atlas_" + path.split("/")[-1]
    x = mi(name, src, {"EmissiveStrength": strength})
    return x


def mi(name, parent, scalars=None, vectors=None):
    path = f"{DIR}/Materials/{name}"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    x = AT.create_asset(name, f"{DIR}/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    x.set_editor_property("parent", parent)
    for k, v in (scalars or {}).items():
        MEL.set_material_instance_scalar_parameter_value(x, k, v)
    for k, v in (vectors or {}).items():
        MEL.set_material_instance_vector_parameter_value(x, k, unreal.LinearColor(*v, 1))
    MEL.update_material_instance(x)
    EAL.save_loaded_asset(x)
    return x


def stage_materials():
    pm = paint_master()
    prop = EAL.load_asset("/Game/City/Street/Materials/M_StreetProp")
    S = {}
    for n, (col, metal, rough) in PAINT.items():
        S[n] = mi(f"MI_{n}", pm, {"Metallic": metal, "Roughness": rough}, {"Tint": col})
    for n, (col, k) in LIGHT.items():
        S[n] = mi(f"MI_Car_{n}", prop, {"EmissiveStrength": k, "Roughness": 0.2}, {"Tint": col, "EmissiveColor": col})
    S["Stainless"] = mi("MI_Car_Stainless", prop, {"Metallic": 1.0, "Roughness": 0.32}, {"Tint": (0.62, 0.62, 0.63)})
    S["Frit"] = mi("MI_Car_GlassFrit", prop, {"Metallic": 0.0, "Roughness": 0.06}, {"Tint": (0.008, 0.008, 0.009)})
    gm = glass_master()
    S["Glass"] = mi("MI_Car_Glass", gm, {k: v for k, v in GLASS_LOOK.items() if not isinstance(v, tuple)},
                    {k: v for k, v in GLASS_LOOK.items() if isinstance(v, tuple) and (GLASS_THIN or k != "Transmittance")})
    n, table, spec = 0, {}, []
    for p in EAL.list_assets(DIR, recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name != "StaticMesh":
            continue
        car = p.split("/")[4] if p.startswith(DIR + "/") else ""
        sm = EAL.load_asset(p.split(".")[0])
        rows = []
        for i, sml in enumerate(sm.get_editor_property("static_materials")):
            slot = str(sml.get_editor_property("material_slot_name"))
            base = slot_base(slot)
            cur = sml.get_editor_property("material_interface")
            hit = None
            if slot in GLASS.get(car, ()):
                hit = S["Glass"]
            elif slot in FRIT.get(car, ()):
                hit = S["Frit"]
            elif base in LAMP_ATLAS:
                hit = lamp_atlas(f"{DIR}/{car}/{p.split('/')[5]}/Materials/{slot}", LAMP_ATLAS[base])
                if hit is None:
                    log("lamp_atlas_missing", f"{car} {slot}: re-import the body (import={car} parts=Body)")
            else:
                hit = S.get(slot) or S.get(base)
            if hit is not None:
                sm.set_material(i, hit)
                n += 1
            elif isinstance(cur, unreal.MaterialInstanceConstant) and "/Materials/" in cur.get_path_name() and DIR in cur.get_path_name():
                # imported glTF material: a glTF specular of 0 (KHR_materials_specular) makes trims dead flat; default it
                for sv in cur.get_editor_property("scalar_parameter_values"):
                    if str(sv.parameter_info.name) == "SpecularFactor" and sv.parameter_value < 0.01:
                        MEL.set_material_instance_scalar_parameter_value(cur, "SpecularFactor", 1.0)
                        MEL.update_material_instance(cur)
                        EAL.save_loaded_asset(cur)
                        spec.append(cur.get_name())
            got = hit or cur
            rows.append([slot, got.get_name() if got else None])
        table[p.split(".")[-1]] = rows
        EAL.save_loaded_asset(sm)
    log("materials", n)
    log("specular_restored", sorted(set(spec)))
    log("slots", {k: v for k, v in table.items() if "Body" in k})


def stage_meshes():
    """Kenny's M1 runs SM5, so Nanite meshes would draw their coarse fallback: turn Nanite off and give each part
    real LODs instead (the handoff asks for LODs; Config/Mac/MacEngine.ini forces LOD 1, so LOD 1 keeps 60%)."""
    ses = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    opts = unreal.EditorScriptingMeshReductionOptions()
    opts.set_editor_property("auto_compute_lod_screen_size", True)
    opts.set_editor_property("reduction_settings", [unreal.EditorScriptingMeshReductionSettings(p, s) for p, s in ((1.0, 1.0), (0.6, 0.5), (0.3, 0.25), (0.12, 0.1))])
    n = 0
    for p in EAL.list_assets(DIR, recursive=True):
        if EAL.find_asset_data(p).asset_class_path.asset_name != "StaticMesh":
            continue
        if "meshes" in ONLY and p.split("/")[4] not in ONLY["meshes"]:
            continue
        if "parts" in ONLY and not any(p.split("/")[5] == f"TV_{p.split('/')[4]}_{q}" for q in ONLY["parts"]):
            continue
        sm = EAL.load_asset(p.split(".")[0])
        ns = sm.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", False)
        sm.set_editor_property("nanite_settings", ns)
        ses.set_lods(sm, opts)
        EAL.save_loaded_asset(sm)
        n += 1
    log("meshes", n)


def placeholder_cars():
    """Cars whose place stage uses the placeholder meshes: placeholders=Semi,Model3 / none, else the DefaultGame.ini [SkyFleet] list."""
    v = ONLY.get("placeholders")
    if v and v != ["ini"]:
        return set() if v == ["none"] else set(v)
    cars, sec = set(), ""
    for ln in open(ROOT + "/Config/DefaultGame.ini"):
        ln = ln.strip()
        if ln.startswith("["):
            sec = ln
        elif sec == "[SkyFleet]" and ln.startswith("+PlaceholderCars="):
            cars.add(ln.split("=", 1)[1].strip())
    return cars


PLACEHOLDERS = placeholder_cars()


def mesh(name, part):
    path = f"{PLACE_DIR if name in PLACEHOLDERS else DIR}/{name}"
    want = f"TV_{name}_{part}".lower()
    for p in EAL.list_assets(path, recursive=True):         # glTF import: <dest>/<file stem>/StaticMeshes/<object name>
        bits = [b.lower() for b in p.split(".")[0].split("/")]
        if want in bits and EAL.find_asset_data(p).asset_class_path.asset_name == "StaticMesh":
            return EAL.load_asset(p.split(".")[0])
    return None


def ground_z(world, x, y, default=0.0, ignore=()):
    hit = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, 50000), unreal.Vector(x, y, -50000),
                                                 unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, list(ignore), unreal.DrawDebugTrace.NONE, True)
    return hit.to_tuple()[4].z if hit else default


def stage_place():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    was = {}
    for a in EAS.get_all_level_actors():
        if TAG in [str(t) for t in a.tags] or a.get_actor_label().startswith("Demo_MG_Veh") or a.get_actor_label() == "Demo_MG_FleetDeck":
            if a.get_actor_label().startswith("Lineup_") and a.get_actor_label().count("_") == 1:
                was[a.get_actor_label()[7:]] = round(a.get_actor_location().z, 1)
            EAS.destroy_actor(a)
    placed = []
    heights = {}
    for v in LAYOUT.get("lineup", []):
        name = v["name"]
        info = PARTS[name]
        x, y = v["p"][1] * 100.0, v["p"][0] * 100.0
        yaw = v["yaw"]                       # compass heading = Unreal yaw for a mesh facing local +X
        cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        # stand on the highest ground under the four tyres (and the centre), so no wheel sinks into the lot
        feet = [(0.0, 0.0)] + [(pi["pivot_m"][0] * 100.0, -pi["pivot_m"][1] * 100.0) for part, pi in info["parts"].items() if part != "Body"]
        z = max(ground_z(world, x + lx * cy - ly * sy, y + lx * sy + ly * cy) for lx, ly in feet)
        heights[name] = {"was": was.get(name), "now": round(z, 1)}
        body = mesh(name, "Body")
        if body is None:
            continue
        a = EAS.spawn_actor_from_object(body, unreal.Vector(x, y, z), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
        a.set_actor_label(f"Lineup_{name}")
        a.set_folder_path("Demo/Lineup")
        a.tags = [TAG, "SC_Lineup", "NoWallRide", f"LineupCar:{name}", "LineupPart:Body"]   # the game re-picks the model at play
        a.static_mesh_component.set_collision_profile_name("BlockAll")
        for part, pi in info["parts"].items():
            if part == "Body":
                continue
            wm = mesh(name, part)
            if wm is None:
                continue
            lx, ly, lz = pi["pivot_m"][0] * 100.0, -pi["pivot_m"][1] * 100.0, pi["pivot_m"][2] * 100.0
            wx, wy = x + lx * cy - ly * sy, y + lx * sy + ly * cy
            w = EAS.spawn_actor_from_object(wm, unreal.Vector(wx, wy, z + lz), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
            w.set_actor_label(f"Lineup_{name}_{part}")
            w.set_folder_path("Demo/Lineup")
            w.tags = [TAG, "NoWallRide", f"LineupCar:{name}", f"LineupPart:{part}"]
            w.static_mesh_component.set_collision_profile_name("NoCollision")
        placed.append(name)
    log("place", placed)
    log("placeholders", sorted(PLACEHOLDERS))
    log("heights_cm", heights)


def stage_save():
    log("save", unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level())


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
