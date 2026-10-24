"""Master facade material for the generated city. No paid add-ons.

Builds M_Facade and one instance per wall slot (M_Brick, M_Concrete,
M_Plaster, M_Metal). The scan stays a texture parameter. Grime is procedural:

- Wear is vertex colour red (the mesher writes facade_grime.intensity) times
  the WearScale parameter. Distressed and older buildings are heavier.
  brand_new and tech stay near zero.
- Edges and corners use the screen-space derivative of the pixel normal
  (curvature, no bake) plus precomputed ambient occlusion where a lightmap
  has one.
- Drips are world-aligned and noise-broken. They peak under the sill band
  and under the ledge at the top of each floor, then fade down. AC units
  sit in the sill band.
- Base dirt fades from the sidewalk up to about 1.4 m.

Pack textures (pack_slots.py) reuse the same master: UVScale (default 1, 1)
multiplies the mesher's UVs so a pack tile of scale_m metres lines up, and
RoughFromG (0 or 1) reads roughness from an ORM map's green channel.

World position in Unreal is centimetres. The metre constants live in
facade_grime.py and are divided by UE_CM here. The Blender preview in
realism._facade_grime uses the same constants.

Run in the editor, PIE off, from the city or block importer:
  py Scripts/city/import_city_ue.py
  py Scripts/city/import_block_ue.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import facade_grime  # noqa: E402


MASTER_NAME = "M_Facade"
FLAT_NORMAL = "/Engine/EngineMaterials/FlatNormal"


def apply(unreal, assets, library, editing, folder, slot_textures):
    """Create the master and an instance for each slot that has a colour map.

    slot_textures maps a material name (M_Brick) to asset paths
    {color, rough, normal}. Returns name -> material instance.
    """
    present = {}
    for name, textures in (slot_textures or {}).items():
        if name not in facade_grime.FACADE_MATERIALS:
            continue
        if not textures or "color" not in textures:
            continue
        present[name] = textures
    if not present:
        return {}
    master = _master(unreal, assets, library, editing, folder, _defaults(library, present))
    made = {}
    for name, textures in present.items():
        made[name] = _instance(unreal, assets, library, editing, folder, master, name, textures)
    return made


def _defaults(library, slot_textures):
    """A texture for each parameter of the master: the first slot that has that map.

    A TextureSampleParameter2D with no texture fails to compile, and the whole
    master then draws as the engine's grey checker. The instances override these.
    """
    out = {}
    for kind, parameter in (("color", "BaseColor"), ("rough", "Roughness"), ("normal", "Normal")):
        for _name, textures in sorted(slot_textures.items()):
            if textures.get(kind):
                out[parameter] = library.load_asset(textures[kind])
                break
    if "Normal" not in out:
        out["Normal"] = library.load_asset(FLAT_NORMAL)
    return out


def _master(unreal, assets, library, editing, folder, defaults=None):
    path = folder + "/" + MASTER_NAME
    if library.does_asset_exist(path):
        library.delete_asset(path)
    if not library.does_directory_exist(folder):
        library.make_directory(folder)
    mat = assets.create_asset(MASTER_NAME, folder, unreal.Material, unreal.MaterialFactoryNew())
    g = _Graph(unreal, editing, mat)

    uv = _uv_scaled(g, unreal)
    defaults = defaults or {}
    base = g.tex("BaseColor", -1400, -200, defaults.get("BaseColor"))
    rough = g.tex("Roughness", -1400, 80, defaults.get("Roughness"))
    rough.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    normal = g.tex("Normal", -1400, 360, defaults.get("Normal"))
    normal.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    for sample in (base, rough, normal):
        g.wire(uv, sample, in_hint="UVs", in_index=0)

    wear = _wear(g)
    world = g.node(unreal.MaterialExpressionWorldPosition, -1400, 640)
    normal_ws = g.node(unreal.MaterialExpressionPixelNormalWS, -1400, 860)
    z_m = g.div(g.mask(world, False, False, True, False, -1100, 640), facade_grime.UE_CM, -900, 640)

    edge = _curvature(g, normal_ws)
    corner = _ao(g, unreal)
    base_dirt = _base_dirt(g, unreal, world, z_m)
    drip = _drips(g, unreal, world, z_m, edge)

    # dirt = saturate((corner * CORNER_WEIGHT + base + drip) * wear)
    dirt = g.sat(
        g.mul(g.add(g.add(g.mul(corner, facade_grime.CORNER_WEIGHT, 200, 200), base_dirt, 360, 200), drip, 520, 200), wear, 700, 200),
        860, 200,
    )
    chip = g.sat(g.mul(g.mul(edge, wear, 200, 40), facade_grime.CHIP_GAIN, 400, 40), 560, 40)

    soot = g.const3(facade_grime.SOOT, 700, 400)
    chip_color = g.const3(facade_grime.CHIP, 700, -40)
    darkened_b = g.mul(base, soot, 900, 0)
    darkened = g.lerp(base, darkened_b, dirt, 1100, 0)
    colored = g.lerp(darkened, chip_color, chip, 1300, 0)
    g.to_property(colored, "", unreal.MaterialProperty.MP_BASE_COLOR)

    rough_r = g.mask(rough, True, False, False, False, -1100, 80)
    rough_g = g.mask(rough, False, True, False, False, -1100, 140)
    from_g = g.node(unreal.MaterialExpressionScalarParameter, -1100, 200)
    from_g.set_editor_property("parameter_name", "RoughFromG")
    from_g.set_editor_property("default_value", 0.0)
    from_g.set_editor_property("group", "Facade")
    rough_out = g.lerp(rough_r, rough_g, from_g, -900, 80)
    rougher = g.lerp(rough_out, g.const(1.0, 900, 160), g.mul(dirt, 0.35, 1000, 160), 1200, 160)
    g.to_property(rougher, "", unreal.MaterialProperty.MP_ROUGHNESS)
    g.to_property(normal, "RGB", unreal.MaterialProperty.MP_NORMAL)

    editing.recompile_material(mat)
    library.save_loaded_asset(mat)
    return mat


def _uv_scaled(g, unreal):
    """TexCoord 0 times the UVScale vector parameter (R = U, G = V)."""
    coord = g.node(unreal.MaterialExpressionTextureCoordinate, -1900, 120)
    scale = g.node(unreal.MaterialExpressionVectorParameter, -1900, 220)
    scale.set_editor_property("parameter_name", "UVScale")
    scale.set_editor_property("default_value", unreal.LinearColor(1.0, 1.0, 0.0, 0.0))
    scale.set_editor_property("group", "Facade")
    rg = g.mask(scale, True, True, False, False, -1700, 220)
    return g.mul(coord, rg, -1600, 160)


def _wear(g):
    """Vertex colour red, times WearScale. The mesher writes the intensity."""
    color = g.node(g.unreal.MaterialExpressionVertexColor, -1100, -40)
    red = g.mask(color, True, False, False, False, -900, -40)
    scale = g.node(g.unreal.MaterialExpressionScalarParameter, -1100, 120)
    scale.set_editor_property("parameter_name", "WearScale")
    scale.set_editor_property("default_value", 1.0)
    scale.set_editor_property("slider_min", 0.0)
    scale.set_editor_property("slider_max", 1.0)
    scale.set_editor_property("group", "Grime")
    return g.sat(g.mul(red, scale, -700, 40), -500, 40)


def _curvature(g, normal_ws):
    """Length of the screen derivatives of the normal. High on edges and corners."""
    dx = g.node(g.unreal.MaterialExpressionDDX, -1100, 860)
    dy = g.node(g.unreal.MaterialExpressionDDY, -1100, 1040)
    g.wire(normal_ws, dx)
    g.wire(normal_ws, dy)
    dx2 = g.dot(dx, dx, -900, 860)
    dy2 = g.dot(dy, dy, -900, 1040)
    return g.sat(g.mul(g.add(dx2, dy2, -700, 940), facade_grime.CURVE_GAIN, -500, 940), -300, 940)


def _ao(g, unreal):
    """Concave corners from the lightmap AO. Open faces stay clean."""
    cls = getattr(unreal, "MaterialExpressionPrecomputedAOMask", None)
    if cls is None:
        return g.const(0.0, -500, 1180)
    ao = g.node(cls, -1100, 1220)
    opened = g.one_minus(ao, -900, 1220)
    return g.sat(g.mul(opened, 2.0, -700, 1220), -500, 1220)


def _base_dirt(g, unreal, world, z_m):
    span = facade_grime.BASE_Z1 - facade_grime.BASE_Z0
    band = g.sat(g.div(g.sub(facade_grime.BASE_Z1, z_m, -700, 640), span, -500, 640), -300, 640)
    noise = _noise_metres(g, unreal, world, facade_grime.BASE_NOISE, facade_grime.BASE_NOISE, facade_grime.BASE_NOISE, -700, 480)
    broken = g.lerp_const(facade_grime.BASE_NOISE_LO, facade_grime.BASE_NOISE_HI, noise, -300, 480)
    return g.mul(band, broken, -80, 560)


def _drips(g, unreal, world, z_m, edge):
    rel = g.div(g.sub(z_m, facade_grime.GROUND_Z, -700, 1500), facade_grime.FLOOR_H, -500, 1500)
    phase = g.frac(rel, -300, 1500)
    sill = _height_band(g, phase, facade_grime.SILL_PEAK, facade_grime.SILL_FADE, -80, 1400)
    ledge = _height_band(g, phase, facade_grime.LEDGE_PEAK, facade_grime.LEDGE_FADE, -80, 1680)
    band = g.max(sill, ledge, 160, 1540)
    column = _column_noise(g, unreal, world, 160, 1280)
    streak = g.sat(g.div(g.sub(column, facade_grime.COLUMN_LO, 400, 1280), facade_grime.COLUMN_HI - facade_grime.COLUMN_LO, 560, 1280), 720, 1280)
    brk = _noise_metres(g, unreal, world, facade_grime.BREAK_SCALE[0], facade_grime.BREAK_SCALE[1], facade_grime.BREAK_SCALE[2], 160, 1860)
    broken = g.lerp_const(facade_grime.BREAK_LO, facade_grime.BREAK_HI, brk, 400, 1860)
    # A floor so a streak still reads across a flat bay, plus a lift on the edge.
    cling = g.add(facade_grime.CLING_FLOOR, g.mul(edge, facade_grime.CLING_EDGE, 400, 1540), 560, 1540)
    gained = g.mul(g.mul(g.mul(streak, broken, 860, 1400), band, 1020, 1460), cling, 1180, 1500)
    return g.mul(gained, facade_grime.DRIP_GAIN, 1340, 1500)


def _height_band(g, phase, peak, fade, x, y):
    raw = g.sub(peak, phase, x, y)
    gate = g.sat(g.mul(g.add(raw, 0.001, x + 180, y), 1000.0, x + 360, y), x + 540, y)
    fall = g.sat(g.div(g.sub(fade, raw, x + 180, y + 80), fade, x + 360, y + 80), x + 540, y + 80)
    return g.mul(gate, fall, x + 720, y)


def _column_noise(g, unreal, world, x, y):
    """Noise of world XY only, so one column keeps its value down the wall."""
    scale = facade_grime.COLUMN_SCALE / facade_grime.UE_CM
    xy = g.mask(world, True, True, False, False, x, y)
    # Append a zero Z. Mask RG is a float2; append makes the column constant in Z.
    zero = g.const(0.0, x, y + 80)
    flat = g.append(xy, zero, x + 180, y)
    scaled = g.mul(flat, scale, x + 360, y)
    noise = g.node(unreal.MaterialExpressionNoise, x + 540, y)
    noise.set_editor_property("scale", 1.0)
    noise.set_editor_property("levels", 2)
    noise.set_editor_property("output_min", 0.0)
    noise.set_editor_property("output_max", 1.0)
    g.wire(scaled, noise, in_hint="Position")
    return noise


def _noise_metres(g, unreal, world, sx, sy, sz, x, y):
    scaled = _scale_cm(g, world, sx, sy, sz, x, y)
    noise = g.node(unreal.MaterialExpressionNoise, x + 700, y)
    noise.set_editor_property("scale", 1.0)
    noise.set_editor_property("levels", 2)
    noise.set_editor_property("output_min", 0.0)
    noise.set_editor_property("output_max", 1.0)
    g.wire(scaled, noise, in_hint="Position")
    return noise


def _scale_cm(g, world, sx, sy, sz, x, y):
    """Scale a centimetre world position into the metre noise frequency."""
    cm = facade_grime.UE_CM
    rx = g.mul(g.mask(world, True, False, False, False, x, y), sx / cm, x + 200, y)
    gy = g.mul(g.mask(world, False, True, False, False, x, y + 40), sy / cm, x + 200, y + 40)
    bz = g.mul(g.mask(world, False, False, True, False, x, y + 80), sz / cm, x + 200, y + 80)
    return g.append(g.append(rx, gy, x + 400, y), bz, x + 520, y)


def _instance(unreal, assets, library, editing, folder, master, name, textures):
    path = folder + "/" + name
    if library.does_asset_exist(path):
        library.delete_asset(path)
    inst = assets.create_asset(name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    editing.set_material_instance_parent(inst, master)
    _set_tex(editing, library, inst, "BaseColor", textures.get("color"))
    _set_tex(editing, library, inst, "Roughness", textures.get("rough"))
    _set_tex(editing, library, inst, "Normal", textures.get("normal"))
    scale = textures.get("uv_scale") or (1.0, 1.0)
    editing.set_material_instance_vector_parameter_value(
        inst, "UVScale", unreal.LinearColor(float(scale[0]), float(scale[1]), 0.0, 0.0))
    editing.set_material_instance_scalar_parameter_value(
        inst, "RoughFromG", 1.0 if textures.get("rough_channel") == "G" else 0.0)
    editing.update_material_instance(inst)
    library.save_loaded_asset(inst)
    return inst


def _set_tex(editing, library, inst, parameter, asset_path):
    if not asset_path:
        return
    tex = library.load_asset(asset_path)
    if tex is None:
        return
    editing.set_material_instance_texture_parameter_value(inst, parameter, tex)


class _Graph(object):
    """Material expressions. Empty pin names mean the first pin, which is what
    MaterialEditingLibrary uses when a node has one input or one output.
    Named pins are used when a node has several, and a failed name falls
    back to the pin list the editor reports.
    """

    def __init__(self, unreal, editing, mat):
        self.unreal = unreal
        self.editing = editing
        self.mat = mat

    def node(self, cls, x, y):
        return self.editing.create_material_expression(self.mat, cls, int(x), int(y))

    def tex(self, parameter, x, y, default=None):
        """A texture parameter. Pass a default texture: without one the material does not compile."""
        node = self.node(self.unreal.MaterialExpressionTextureSampleParameter2D, x, y)
        node.set_editor_property("parameter_name", parameter)
        node.set_editor_property("group", "Facade")
        if default is not None:
            node.set_editor_property("texture", default)
        return node

    def const(self, value, x, y):
        node = self.node(self.unreal.MaterialExpressionConstant, x, y)
        node.set_editor_property("r", float(value))
        return node

    def const3(self, rgba, x, y):
        node = self.node(self.unreal.MaterialExpressionConstant3Vector, x, y)
        node.set_editor_property("constant", self.unreal.LinearColor(float(rgba[0]), float(rgba[1]), float(rgba[2]), 1.0))
        return node

    def mask(self, src, r, g, b, a, x, y):
        node = self.node(self.unreal.MaterialExpressionComponentMask, x, y)
        node.set_editor_property("r", bool(r))
        node.set_editor_property("g", bool(g))
        node.set_editor_property("b", bool(b))
        node.set_editor_property("a", bool(a))
        self.wire(src, node)
        return node

    def mul(self, a, b, x, y):
        return self._binop(self.unreal.MaterialExpressionMultiply, a, b, x, y)

    def add(self, a, b, x, y):
        return self._binop(self.unreal.MaterialExpressionAdd, a, b, x, y)

    def sub(self, a, b, x, y):
        return self._binop(self.unreal.MaterialExpressionSubtract, a, b, x, y)

    def div(self, a, b, x, y):
        return self._binop(self.unreal.MaterialExpressionDivide, a, b, x, y)

    def max(self, a, b, x, y):
        return self._binop(self.unreal.MaterialExpressionMax, a, b, x, y)

    def dot(self, a, b, x, y):
        return self._binop(self.unreal.MaterialExpressionDotProduct, a, b, x, y)

    def _binop(self, cls, a, b, x, y):
        node = self.node(cls, x, y)
        if isinstance(a, (int, float)):
            self._const_pin(node, "const_a", a, "A", 0)
        else:
            self.wire(a, node, in_hint="A", in_index=0)
        if isinstance(b, (int, float)):
            self._const_pin(node, "const_b", b, "B", 1)
        else:
            self.wire(b, node, in_hint="B", in_index=1)
        return node

    def _const_pin(self, node, prop, value, hint, index):
        try:
            node.set_editor_property(prop, float(value))
        except Exception:
            const = self.const(value, 0, 0)
            self.wire(const, node, in_hint=hint, in_index=index)

    def lerp(self, a, b, alpha, x, y):
        node = self.node(self.unreal.MaterialExpressionLinearInterpolate, x, y)
        self.wire(a, node, in_hint="A", in_index=0)
        self.wire(b, node, in_hint="B", in_index=1)
        self.wire(alpha, node, in_hint="Alpha", in_index=2)
        return node

    def lerp_const(self, a, b, alpha, x, y):
        """Lerp between two constants. Alpha is a node."""
        node = self.node(self.unreal.MaterialExpressionLinearInterpolate, x, y)
        node.set_editor_property("const_a", float(a))
        node.set_editor_property("const_b", float(b))
        self.wire(alpha, node, in_hint="Alpha", in_index=2)
        return node

    def sat(self, src, x, y):
        cls = getattr(self.unreal, "MaterialExpressionSaturate", None)
        if cls is not None:
            node = self.node(cls, x, y)
            self.wire(src, node)
            return node
        node = self.node(self.unreal.MaterialExpressionClamp, x, y)
        self.wire(src, node, in_hint="Input", in_index=0)
        try:
            node.set_editor_property("min_default", 0.0)
            node.set_editor_property("max_default", 1.0)
        except Exception:
            self.wire(self.const(0.0, x, y + 40), node, in_hint="Min", in_index=1)
            self.wire(self.const(1.0, x, y + 80), node, in_hint="Max", in_index=2)
        return node

    def frac(self, src, x, y):
        node = self.node(self.unreal.MaterialExpressionFrac, x, y)
        self.wire(src, node)
        return node

    def one_minus(self, src, x, y):
        node = self.node(self.unreal.MaterialExpressionOneMinus, x, y)
        self.wire(src, node)
        return node

    def append(self, a, b, x, y):
        node = self.node(self.unreal.MaterialExpressionAppendVector, x, y)
        self.wire(a, node, in_hint="A", in_index=0)
        self.wire(b, node, in_hint="B", in_index=1)
        return node

    def to_property(self, src, out_hint, prop):
        out_name = self._out_name(src, out_hint)
        ok = self.editing.connect_material_property(src, out_name, prop)
        if not ok and out_name:
            ok = self.editing.connect_material_property(src, "", prop)
        if not ok:
            raise RuntimeError("Facade master could not connect to %s" % prop)

    def wire(self, src, dst, out_hint="", in_hint="", in_index=0):
        out_name = self._out_name(src, out_hint)
        ins = [str(name) for name in (self.editing.get_material_expression_input_names(dst) or [])]
        if in_hint and in_hint in ins:
            in_name = in_hint
        elif ins and in_index < len(ins):
            in_name = ins[in_index]
        else:
            in_name = ""
        ok = self.editing.connect_material_expressions(src, out_name, dst, in_name)
        if not ok and in_name:
            ok = self.editing.connect_material_expressions(src, out_name, dst, "")
        if not ok:
            raise RuntimeError(
                "Facade master could not connect %s -> %s (inputs %s)"
                % (out_name or "out", in_name or "in", ", ".join(ins))
            )

    def _out_name(self, src, hint):
        outs = [str(name) for name in (self.editing.get_material_expression_output_names(src) or [])]
        if hint and hint in outs:
            return hint
        if not hint and "RGB" in outs:
            return "RGB"
        if outs:
            return outs[0]
        return hint or ""
