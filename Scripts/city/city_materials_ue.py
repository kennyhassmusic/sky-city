"""Editor materials shared by import_city_ue.py and import_block_ue.py.

- Slot textures come from pack_slots.plan_slots(): an AI pack set when one
  fits, else the CC0 scan. Wall slots are instances of M_Facade (procedural
  grime, UVScale, RoughFromG). Ground slots are a small textured material
  with the same UVScale.
- Glass is real glass, not a flat tint: translucent, lit per pixel, nearly
  clear head-on and reflective at grazing angles (Fresnel), so the room
  shells the mesher builds behind every pane show through. The lit variants
  are the same glass; the light comes from the rooms behind.
- M_InteriorLit is emissive (EmissiveStrength), so lit rooms read at dusk.

Pack normals are DirectX (Unreal's own convention): no green flip. Poly Haven
scans are OpenGL: flipped on import. Import does not open SkyCityMashup.
Run from the importers, in the editor, PIE off.
"""
import os

GLASS_SLOTS = ("M_Glass", "M_GlassLit", "M_CurtainGlass", "M_CurtainGlassLit")
CAR_GLASS_SLOTS = ("M_ParkedGlass",)
# Slots the GLBs carry that used to fall through to the plain glTF colour.
FLATS = {
    "M_Roof": (0.18, 0.19, 0.20, 0.85),
    "M_Curb": (0.78, 0.76, 0.72, 0.80),
    "M_LanePaint": (0.92, 0.92, 0.90, 0.60),
    "M_LanePaintYellow": (0.86, 0.68, 0.12, 0.60),
    "M_Interior": (0.12, 0.10, 0.09, 0.85),
    "M_FenceIron": (0.16, 0.17, 0.18, 0.55),
    "M_FenceWood": (0.36, 0.24, 0.14, 0.80),
    "M_TrimDark": (0.25, 0.22, 0.20, 0.60),
    "M_Paint": (0.85, 0.85, 0.82, 0.60),
    "M_Blind": (0.80, 0.78, 0.72, 0.90),
    "M_BlindWarm": (0.86, 0.78, 0.62, 0.90),
    "M_CurtainRed": (0.45, 0.16, 0.14, 0.95),
    "M_CurtainBlue": (0.18, 0.24, 0.38, 0.95),
    "M_CurtainGreen": (0.16, 0.28, 0.22, 0.95),
    "M_CurtainCream": (0.72, 0.66, 0.52, 0.95),
    "M_AwningNavy": (0.12, 0.16, 0.28, 0.90),
    "M_AwningRed": (0.42, 0.12, 0.12, 0.90),
    "M_AwningGreen": (0.12, 0.28, 0.24, 0.90),
    "M_AwningCream": (0.78, 0.74, 0.64, 0.90),
    "M_Counter": (0.32, 0.28, 0.24, 0.70),
    "M_Wood": (0.28, 0.18, 0.10, 0.70),
    "M_CastIron": (0.05, 0.05, 0.05, 0.50),
    "M_PaintedSteelDark": (0.06, 0.065, 0.07, 0.45),
    "M_BenchSteel": (0.15, 0.15, 0.16, 0.45),
    "M_BenchWood": (0.35, 0.22, 0.12, 0.75),
    "M_ParkedBody": (0.22, 0.28, 0.34, 0.30),
    "M_SignPole": (0.22, 0.22, 0.24, 0.55),
    "M_SignalPole": (0.20, 0.20, 0.22, 0.55),
    "M_SK_BusStop": (0.12, 0.28, 0.48, 0.60),
    "M_SK_Stop": (0.62, 0.08, 0.07, 0.50),
    "M_SK_StreetName": (0.12, 0.32, 0.22, 0.50),
    "M_Puddle": (0.04, 0.04, 0.045, 0.05),
    "M_Manhole": (0.25, 0.25, 0.26, 0.70),
    "M_Hydrant": (0.62, 0.10, 0.08, 0.55),
    # Simple massing for buildings past the mesh budget (import_city_ue.py).
    "M_MassingGlass": (0.10, 0.14, 0.18, 0.15),
}
EMISSIVE = {
    "M_InteriorLit": ((1.0, 0.72, 0.38), 3.0),
    "M_LampLens": ((1.0, 0.92, 0.75), 6.0),
    "M_SignalLamp0": ((0.70, 0.08, 0.06), 4.0),
    "M_SignalLamp1": ((0.75, 0.58, 0.10), 4.0),
    "M_SignalLamp2": ((0.10, 0.45, 0.16), 4.0),
}


def base_slot(name):
    """Blender appends .001 to a reused slot name; the material is the same."""
    name = str(name).split(".")[0]
    return name


def build(unreal, plan, mat_dir, tex_dir):
    """slot name -> material for every slot this module knows."""
    library = unreal.EditorAssetLibrary
    assets = unreal.AssetToolsHelpers.get_asset_tools()
    editing = unreal.MaterialEditingLibrary
    if not library.does_directory_exist(mat_dir):
        library.make_directory(mat_dir)
    import facade_grime
    import facade_material_ue
    made = {}
    facade = {}
    for slot, entry in sorted((plan or {}).items()):
        textures = _textures(unreal, assets, library, entry, tex_dir)
        if "color" not in textures:
            continue
        entry["textures"] = dict(textures)  # asset paths, for ground_tiled()
        textures["uv_scale"] = entry.get("uv_scale") or (1.0, 1.0)
        textures["rough_channel"] = entry.get("rough_channel")
        if slot in facade_grime.FACADE_MATERIALS:
            facade[slot] = textures
        else:
            made[slot] = _textured(unreal, assets, library, editing, mat_dir, slot, textures)
    if facade:
        made.update(facade_material_ue.apply(unreal, assets, library, editing, mat_dir, facade))
    glass = _glass(unreal, assets, library, editing, mat_dir, "M_Glass", (0.02, 0.025, 0.03), 0.06, 0.5)
    for slot in GLASS_SLOTS:
        made[slot] = glass
    car = _glass(unreal, assets, library, editing, mat_dir, "M_CarGlass", (0.01, 0.012, 0.014), 0.45, 0.85)
    for slot in CAR_GLASS_SLOTS:
        made[slot] = car
    for name, (r, g, b, rough) in FLATS.items():
        made[name] = _flat(unreal, assets, library, editing, mat_dir, name, (r, g, b), rough)
    for name, (rgb, strength) in EMISSIVE.items():
        made[name] = _emissive(unreal, assets, library, editing, mat_dir, name, rgb, strength)
    return made


MASSING_MASTER = "M_MassingFacade"
# Custom primitive data on each massing box: its size in metres along local X, Y, Z.
MASSING_SIZE_CPD = 0
MASSING_ROOF = (0.16, 0.17, 0.18)


def massing(unreal, assets, library, editing, mat_dir, tex_dir, sets):
    """district_type -> instance of M_MassingFacade for pack_slots.massing_sets().

    The boxes are the engine cube scaled to the building, so its own UVs would
    stretch one tile over a whole tower. The master lays the tile out in metres
    from the local position instead: U runs along the face (local Y on X faces,
    local X on Y faces), V up from the ground, so floors line up at the base and
    bays keep their width on any box. The box size comes from custom primitive
    data (import_city_ue.py writes it). Roofs are flat dark grey. No normal map:
    the cube's tangents do not follow these UVs.
    """
    if not sets:
        return {}
    import facade_material_ue
    imported = {}
    for kind, entry in sorted(sets.items()):
        if kind == "*":
            continue
        textures = _textures(unreal, assets, library, dict(entry, maps={
            key: entry["maps"][key] for key in ("color", "rough") if key in entry["maps"]}), tex_dir)
        if "color" in textures:
            imported[kind] = textures
    if not imported:
        return {}
    first = imported[sorted(imported)[0]]
    path = mat_dir + "/" + MASSING_MASTER
    if library.does_asset_exist(path):
        library.delete_asset(path)
    mat = assets.create_asset(MASSING_MASTER, mat_dir, unreal.Material, unreal.MaterialFactoryNew())
    g = facade_material_ue._Graph(unreal, editing, mat)
    local = g.node(unreal.MaterialExpressionLocalPosition, -2200, 0)
    unit = g.add(g.div(local, 100.0, -2000, 0), 0.5, -1850, 0)  # 0..1 across the cube
    size = []
    for k, name in enumerate(("SizeX", "SizeY", "SizeZ")):
        node = g.node(unreal.MaterialExpressionScalarParameter, -2000, 200 + 80 * k)
        node.set_editor_property("parameter_name", name)
        node.set_editor_property("default_value", 10.0)
        node.set_editor_property("use_custom_primitive_data", True)
        node.set_editor_property("primitive_data_index", MASSING_SIZE_CPD + k)
        size.append(node)
    metres = g.mul(unit, g.append(g.append(size[0], size[1], -1800, 200), size[2], -1700, 220), -1600, 100)
    normal_ws = g.node(unreal.MaterialExpressionVertexNormalWS, -2200, 500)
    to_local = g.node(unreal.MaterialExpressionTransform, -2000, 500)
    to_local.set_editor_property("transform_source_type", unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD)
    to_local.set_editor_property("transform_type", unreal.MaterialVectorCoordTransform.TRANSFORM_LOCAL)
    g.wire(normal_ws, to_local)
    normalized = g.node(unreal.MaterialExpressionNormalize, -1850, 500)
    g.wire(to_local, normalized)
    facing = g.node(unreal.MaterialExpressionAbs, -1700, 500)
    g.wire(normalized, facing)
    on_x = g.mask(facing, True, False, False, False, -1550, 480)
    on_z = g.mask(facing, False, False, True, False, -1550, 560)
    along = g.lerp(g.mask(metres, True, False, False, False, -1450, 60),
                   g.mask(metres, False, True, False, False, -1450, 120), on_x, -1300, 80)
    tile = []
    for k, name in enumerate(("TileW", "TileH")):
        node = g.node(unreal.MaterialExpressionScalarParameter, -1450, 260 + 80 * k)
        node.set_editor_property("parameter_name", name)
        node.set_editor_property("default_value", 4.0)
        tile.append(node)
    u = g.div(along, tile[0], -1150, 80)
    v = g.div(g.mul(g.mask(metres, False, False, True, False, -1450, 200), -1.0, -1300, 200), tile[1], -1150, 200)
    uv = g.append(u, v, -1000, 140)
    # Defaults so the master compiles (an empty texture parameter does not); instances override them.
    base = g.tex("BaseColor", -850, 0, library.load_asset(first["color"]))
    rough = g.tex("Roughness", -850, 300, library.load_asset(first.get("rough") or first["color"]))
    rough.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    for sample in (base, rough):
        g.wire(uv, sample, in_hint="UVs", in_index=0)
    roof = g.const3(MASSING_ROOF, -700, 160)
    g.to_property(g.lerp(base, roof, on_z, -500, 0), "", unreal.MaterialProperty.MP_BASE_COLOR)
    g.to_property(g.lerp(g.mask(rough, True, False, False, False, -650, 300), g.const(0.85, -650, 380), on_z, -500, 300),
                  "", unreal.MaterialProperty.MP_ROUGHNESS)
    editing.recompile_material(mat)
    library.save_loaded_asset(mat)
    made = {}
    for kind, textures in sorted(imported.items()):
        entry = sets[kind]
        name = "MI_Massing_" + kind
        inst_path = mat_dir + "/" + name
        if library.does_asset_exist(inst_path):
            library.delete_asset(inst_path)
        inst = assets.create_asset(name, mat_dir, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        editing.set_material_instance_parent(inst, mat)
        facade_material_ue._set_tex(editing, library, inst, "BaseColor", textures.get("color"))
        facade_material_ue._set_tex(editing, library, inst, "Roughness", textures.get("rough"))
        editing.set_material_instance_scalar_parameter_value(inst, "TileW", float(entry["tile_m"][0]))
        editing.set_material_instance_scalar_parameter_value(inst, "TileH", float(entry["tile_m"][1]))
        editing.update_material_instance(inst)
        library.save_loaded_asset(inst)
        made[kind] = inst
    if "*" in sets and sets["*"]["set_id"] in {sets[k]["set_id"] for k in made}:
        made["*"] = next(made[k] for k in made if sets[k]["set_id"] == sets["*"]["set_id"])
    return made


def ground_tiled(unreal, assets, library, editing, mat_dir, name, entry, size_m):
    """A copy of a ground slot for one big flat face (the ground slab): its 0..1 UVs tile every tile_m metres."""
    tile = (entry or {}).get("tile_m") or (entry or {}).get("uv_m") or [3.0, 3.0]
    textures = {kind: path for kind, path in (entry or {}).get("textures", {}).items()}
    textures["uv_scale"] = (float(size_m[0]) / tile[0], float(size_m[1]) / tile[1])
    textures["rough_channel"] = (entry or {}).get("rough_channel")
    return _textured(unreal, assets, library, editing, mat_dir, name, textures)


def assign(unreal, mesh, materials):
    """Bind every slot this mesh names; returns the slot names left unbound."""
    missing = []
    slots = mesh.get_editor_property("static_materials")
    for index, slot in enumerate(slots):
        name = base_slot(slot.get_editor_property("material_slot_name"))
        mat = materials.get(name)
        if mat is None and name.startswith("M_Sign"):
            mat = materials.get("M_SignPole")
        if mat is None:
            missing.append(name)
            continue
        mesh.set_material(index, mat)
    return missing


def _textures(unreal, assets, library, entry, tex_dir):
    out = {}
    for kind, src in (entry.get("maps") or {}).items():
        if not src or not os.path.isfile(src) or not src.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        dest = tex_dir + "/" + str(entry.get("set_id") or "set")
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", src)
        task.set_editor_property("destination_path", dest)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", True)
        assets.import_asset_tasks([task])
        paths = list(task.get_editor_property("imported_object_paths") or [])
        if not paths:
            continue
        tex = library.load_asset(paths[0])
        if kind == "color":
            tex.set_editor_property("srgb", True)
        else:
            tex.set_editor_property("srgb", False)
            if kind == "normal":
                tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
                tex.set_editor_property("flip_green_channel", bool(entry.get("flip_green")))
            else:
                tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        library.save_loaded_asset(tex)
        out[kind] = paths[0].split(".")[0]
    return out


def _fresh(unreal, assets, library, mat_dir, name):
    path = mat_dir + "/" + name
    if library.does_asset_exist(path):
        library.delete_asset(path)
    return assets.create_asset(name, mat_dir, unreal.Material, unreal.MaterialFactoryNew())


def _textured(unreal, assets, library, editing, mat_dir, slot, textures):
    mat = _fresh(unreal, assets, library, mat_dir, slot)
    coord = editing.create_material_expression(mat, unreal.MaterialExpressionTextureCoordinate, -900, 0)
    scale = textures.get("uv_scale") or (1.0, 1.0)
    coord.set_editor_property("u_tiling", float(scale[0]))
    coord.set_editor_property("v_tiling", float(scale[1]))
    color = editing.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -400, -200)
    color.set_editor_property("texture", unreal.EditorAssetLibrary.load_asset(textures["color"]))
    editing.connect_material_expressions(coord, "", color, "UVs")
    editing.connect_material_property(color, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    if "rough" in textures:
        rough = editing.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -400, 80)
        rough.set_editor_property("texture", unreal.EditorAssetLibrary.load_asset(textures["rough"]))
        rough.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
        editing.connect_material_expressions(coord, "", rough, "UVs")
        channel = "G" if textures.get("rough_channel") == "G" else "R"
        editing.connect_material_property(rough, channel, unreal.MaterialProperty.MP_ROUGHNESS)
    if "normal" in textures:
        normal = editing.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -400, 280)
        normal.set_editor_property("texture", unreal.EditorAssetLibrary.load_asset(textures["normal"]))
        normal.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        editing.connect_material_expressions(coord, "", normal, "UVs")
        editing.connect_material_property(normal, "RGB", unreal.MaterialProperty.MP_NORMAL)
    editing.recompile_material(mat)
    library.save_loaded_asset(mat)
    return mat


def _glass(unreal, assets, library, editing, mat_dir, name, tint, opacity_head_on, opacity_grazing):
    """Clear pane: translucent, per-pixel lit, Fresnel opacity, smooth and specular."""
    mat = _fresh(unreal, assets, library, mat_dir, name)
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    _try_set(mat, "translucency_lighting_mode", "TranslucencyLightingMode", "TLM_SURFACE_PER_PIXEL_LIGHTING", unreal)
    _try_set(mat, "translucency_pass", "MaterialTranslucencyPass", "MTP_AFTER_DOF", unreal)
    base = editing.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -600, -200)
    base.set_editor_property("constant", unreal.LinearColor(tint[0], tint[1], tint[2], 1))
    editing.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    for prop, value, y in ((unreal.MaterialProperty.MP_METALLIC, 0.0, -60),
                           (unreal.MaterialProperty.MP_SPECULAR, 1.0, 20),
                           (unreal.MaterialProperty.MP_ROUGHNESS, 0.04, 100)):
        const = editing.create_material_expression(mat, unreal.MaterialExpressionConstant, -600, y)
        const.set_editor_property("r", value)
        editing.connect_material_property(const, "", prop)
    fresnel = editing.create_material_expression(mat, unreal.MaterialExpressionFresnel, -800, 240)
    fresnel.set_editor_property("exponent", 4.0)
    fresnel.set_editor_property("base_reflect_fraction", 0.04)
    lerp = editing.create_material_expression(mat, unreal.MaterialExpressionLinearInterpolate, -500, 240)
    lerp.set_editor_property("const_a", float(opacity_head_on))
    lerp.set_editor_property("const_b", float(opacity_grazing))
    editing.connect_material_expressions(fresnel, "", lerp, "Alpha")
    editing.connect_material_property(lerp, "", unreal.MaterialProperty.MP_OPACITY)
    editing.recompile_material(mat)
    library.save_loaded_asset(mat)
    return mat


def _flat(unreal, assets, library, editing, mat_dir, name, rgb, roughness):
    mat = _fresh(unreal, assets, library, mat_dir, name)
    const = editing.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -300, 0)
    const.set_editor_property("constant", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1))
    editing.connect_material_property(const, "", unreal.MaterialProperty.MP_BASE_COLOR)
    rough = editing.create_material_expression(mat, unreal.MaterialExpressionConstant, -300, 160)
    rough.set_editor_property("r", float(roughness))
    editing.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    editing.recompile_material(mat)
    library.save_loaded_asset(mat)
    return mat


def _emissive(unreal, assets, library, editing, mat_dir, name, rgb, strength):
    mat = _fresh(unreal, assets, library, mat_dir, name)
    const = editing.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -500, 0)
    const.set_editor_property("constant", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1))
    editing.connect_material_property(const, "", unreal.MaterialProperty.MP_BASE_COLOR)
    gain = editing.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -500, 160)
    gain.set_editor_property("parameter_name", "EmissiveStrength")
    gain.set_editor_property("default_value", float(strength))
    mul = editing.create_material_expression(mat, unreal.MaterialExpressionMultiply, -250, 100)
    editing.connect_material_expressions(const, "", mul, "A")
    editing.connect_material_expressions(gain, "", mul, "B")
    editing.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    editing.recompile_material(mat)
    library.save_loaded_asset(mat)
    return mat


def _try_set(obj, prop, enum_name, member, unreal):
    enum = getattr(unreal, enum_name, None)
    value = getattr(enum, member, None) if enum is not None else None
    if value is None:
        print("CITYGEN note: %s.%s not in this engine; left at default" % (enum_name, member))
        return False
    try:
        obj.set_editor_property(prop, value)
        return True
    except Exception as err:  # property renamed between engine versions
        print("CITYGEN note: could not set %s (%s)" % (prop, err))
        return False
