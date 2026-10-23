"""Mesh and render the one-block study.

Reads SourceArt/CityGen/loop_variations.json (from Scripts/city/block.py). Builds the
street section from profiles.py, the buildings from the grammar, and writes GLBs plus
day and dusk previews. The GLBs are in plan metres, turned -90 degrees about Z on the
way out, the same turn the landmark exporter uses, so Unreal's glTF import puts plan
north on +X and plan east on +Y.

Windows are a real recess with a glass pane, a sill and a lintel. Shopfronts open
into a small room. CC0 grime, leak decals and a sky HDRI are applied in realism.py.
Transmission is a transparent mix rather than a refractive shader so a CPU render
stays practical.
LOD0 is that module build. LOD1 is one band per floor. LOD2 is the same mass without
the bands. The far LOD is a box with the original facade grid.

Run:
  python3 -I Scripts/city/block.py
  blender -b --factory-startup -P Scripts/city/blender_block.py
Output:
  SourceArt/CityGen/blocks/CG_Block_<style>_LOD0.glb  (and LOD1, LOD2, FAR, _web)
  SourceArt/CityGen/previews/CG_<style>_<shot>.png
  SourceArt/CityGen/block_report.json
"""
import json
import math
import os
import sys
import time

import bpy
import bmesh

CITY = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("SKYCITY_ROOT") or os.path.dirname(os.path.dirname(CITY))
sys.path.insert(0, CITY)
sys.path.insert(0, os.path.join(ROOT, "Scripts", "streets"))
sys.path.insert(0, os.path.join(ROOT, "Scripts", "roads"))

import geom  # noqa: E402
import grammar  # noqa: E402
import profiles  # noqa: E402
import realism  # noqa: E402

ART = os.path.join(ROOT, "SourceArt", "CityGen")
VARIATIONS = os.path.join(ART, "loop_variations.json")
BLOCKS = os.path.join(ART, "blocks")
PREVIEWS = os.path.join(ART, "previews")

# Wall slot in the grammar -> folder under SourceArt/CityGen/materials.
SLOT = {
    "brick": "brick_wall_001",
    "concrete": "concrete_wall_001",
    "plaster": "grey_plaster",
    "metal": "metal_plate",
    "asphalt": "asphalt_02",
    "paving": "PavingStones092",
    "grass": "Grass004",
}


def main():
    os.makedirs(BLOCKS, exist_ok=True)
    os.makedirs(PREVIEWS, exist_ok=True)
    data = json.load(open(VARIATIONS))
    mats = load_material_record()
    reset()
    lib = make_library(mats)
    street_objects = build_street(data, lib)
    prototypes = make_prototypes(data, lib)
    place_props(data, prototypes, street_objects, lib)
    report = {"seed": data["seed"], "hash": data["manifest_hash"], "styles": {}, "renders": []}
    only_styles = [s for s in os.environ.get("SKYCITY_STYLES", "").split(",") if s]
    only_shots = [s for s in os.environ.get("SKYCITY_SHOTS", "").split(",") if s]
    if only_shots:
        # render_style reads this off the function default via the cameras dict copy
        data["cameras"] = {k: v for k, v in data["cameras"].items() if k in only_shots}
        # keep the three keys render_style iterates, filling gaps from street
        for key in ("street", "aerial", "dusk"):
            data["cameras"].setdefault(key, data["cameras"].get("street") or next(iter(data["cameras"].values())))
        data["_shots"] = only_shots
    for style, buildings in data["styles"].items():
        if only_styles and style not in only_styles:
            continue
        print("STYLE", style, len(buildings), flush=True)
        groups = build_style(style, buildings, data.get("context") or [], lib)
        shots = render_style(style, data["cameras"], groups["lod0"] + street_objects)
        report["renders"].extend(shots)
        report["styles"][style] = export_style(style, groups, street_objects)
        clear_groups(groups)
    path = os.path.join(ART, "block_report.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print("REPORT", path, flush=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def load_material_record():
    path = os.path.join(ART, "materials", "materials.json")
    if not os.path.isfile(path):
        return {}
    return json.load(open(path))


def make_library(record):
    """Shared Blender materials. GLBs keep the slot names and do not embed the scans.

    Scripts/city/import_block_ue.py binds these JPGs in the editor. Embedding them in
    every LOD would copy the same maps into each file and blow the pull-request cap.
    """
    lib = {}
    for slot, ident in SLOT.items():
        info = record.get(ident) or {}
        uv = info.get("uv_m") or [2.0, 2.0]
        lib[slot] = textured(slot, info.get("maps") or {}, float(uv[0] or 2.0))
    lib["glass"] = glass_material("M_Glass", emit=0.0)
    lib["glass_lit"] = glass_material("M_GlassLit", emit=1.0)
    lib["paint"] = flat("M_Paint", (0.85, 0.85, 0.82), 0.45)
    lib["trim_dark"] = flat("M_TrimDark", (0.25, 0.22, 0.2), 0.55)
    lib["interior"] = flat("M_Interior", (0.12, 0.1, 0.09), 0.85)
    lib["curb"] = flat("M_Curb", (0.78, 0.76, 0.72), 0.55)
    lib["interior_lit"] = emissive("M_InteriorLit", (1.0, 0.72, 0.38), 0.4)
    lib["roof"] = flat("M_Roof", (0.18, 0.19, 0.2), 0.7)
    lib["lane"] = flat("M_LanePaint", (0.98, 0.98, 0.97), 0.28)
    set_emission(lib["lane"], 0.55)
    realism.extend_library(lib, record, ART)
    return lib


def textured(slot, maps, uv_m):
    mat = bpy.data.materials.new("M_" + slot.capitalize())
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.7
    color_path = _map_path(maps.get("color"))
    if color_path:
        img = bpy.data.images.load(color_path)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        mapping = nt.nodes.new("ShaderNodeMapping")
        coord = nt.nodes.new("ShaderNodeTexCoord")
        # Mesh UVs are already in repeats of uv_m, so the mapping scale stays 1.
        mapping.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
        nt.links.new(coord.outputs["UV"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        rough_path = _map_path(maps.get("rough"))
        if rough_path:
            rimg = bpy.data.images.load(rough_path)
            rimg.colorspace_settings.name = "Non-Color"
            rtex = nt.nodes.new("ShaderNodeTexImage")
            rtex.image = rimg
            nt.links.new(mapping.outputs["Vector"], rtex.inputs["Vector"])
            nt.links.new(rtex.outputs["Color"], bsdf.inputs["Roughness"])
        normal_path = _map_path(maps.get("normal"))
        if normal_path:
            nimg = bpy.data.images.load(normal_path)
            nimg.colorspace_settings.name = "Non-Color"
            ntex = nt.nodes.new("ShaderNodeTexImage")
            ntex.image = nimg
            nmap = nt.nodes.new("ShaderNodeNormalMap")
            nt.links.new(mapping.outputs["Vector"], ntex.inputs["Vector"])
            nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
            nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    mat["uv_m"] = uv_m
    return mat


def _map_path(rel):
    if not rel:
        return None
    path = os.path.join(ART, "materials", rel)
    return path if os.path.isfile(path) else None


def flat(name, rgb, rough):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Roughness"].default_value = rough
    return mat


def emissive(name, rgb, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    _set(bsdf, ("Emission Color", "Emission"), (*rgb, 1))
    _set(bsdf, ("Emission Strength",), strength)
    mat["emit"] = strength
    return mat


def glass_material(name, emit):
    """A pane you can see through, with an optional glow. The recess behind it does the depth."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.55, 0.7, 0.8, 1)
    bsdf.inputs["Roughness"].default_value = 0.05
    _set(bsdf, ("Metallic",), 0.0)
    _set(bsdf, ("Emission Color", "Emission"), (1.0, 0.78, 0.45, 1))
    _set(bsdf, ("Emission Strength",), emit)
    transp = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = 0.42
    out = nt.nodes.get("Material Output")
    nt.links.new(bsdf.outputs["BSDF"], mix.inputs[1])
    nt.links.new(transp.outputs["BSDF"], mix.inputs[2])
    # Material Output already links to the principled; replace it.
    for link in list(nt.links):
        if link.to_node == out:
            nt.links.remove(link)
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    mat["emit"] = emit
    return mat


def _set(bsdf, names, value):
    for name in names:
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = value
            return


def set_emission(mat, strength):
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    _set(bsdf, ("Emission Strength",), strength)


class Mesh(object):
    def __init__(self, name):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.mats = []
        self.name = name

    def slot(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def face(self, verts, mat, uvs):
        try:
            vs = [self.bm.verts.new(v) for v in verts]
            f = self.bm.faces.new(vs)
        except ValueError:
            return
        f.material_index = self.slot(mat)
        if uvs:
            for loop, uv in zip(f.loops, uvs):
                loop[self.uv].uv = uv
        f.normal_update()

    def _tile(self, mat):
        """Metres per texture repeat. UVs are stored in those repeats, not 0-1 per face."""
        try:
            scale = float(mat.get("uv_m") or 1.0)
        except (TypeError, ValueError):
            scale = 1.0
        return scale if scale > 1e-4 else 1.0

    def _uv(self, u_len, v_len, mat):
        s = self._tile(mat)
        return [(0.0, 0.0), (u_len / s, 0.0), (u_len / s, v_len / s), (0.0, v_len / s)]

    def box(self, origin, axis_u, axis_v, axis_w, size, mat):
        """A box. size is (u, v, w) full extents. origin is the centre.

        Each face is UV'd in metres divided by the material's scan size, so a 3 m
        brick repeat tiles across a pier instead of stretching once over it.
        """
        u, v, w = size
        cu, cv, cw = u / 2.0, v / 2.0, w / 2.0

        def at(su, sv, sw):
            return (origin[0] + axis_u[0] * su * cu + axis_v[0] * sv * cv + axis_w[0] * sw * cw,
                    origin[1] + axis_u[1] * su * cu + axis_v[1] * sv * cv + axis_w[1] * sw * cw,
                    origin[2] + axis_u[2] * su * cu + axis_v[2] * sv * cv + axis_w[2] * sw * cw)
        # (corners, length along the face's first edge, length along the second)
        quads = [
            (((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)), abs(u), abs(v)),
            (((-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1)), abs(u), abs(v)),
            (((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)), abs(u), abs(w)),
            (((1, 1, -1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1)), abs(u), abs(w)),
            (((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)), abs(v), abs(w)),
            (((-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1)), abs(v), abs(w)),
        ]
        for quad, lu, lv in quads:
            self.face([at(*c) for c in quad], mat, self._uv(lu, lv, mat))

    def prism(self, poly, z0, z1, mat):
        """Extrude a CCW polygon in plan between two heights."""
        n = len(poly)
        if n < 3 or z1 <= z0:
            return
        s = self._tile(mat)
        top = [(p[0], p[1], z1) for p in poly]
        bot = [(p[0], p[1], z0) for p in poly]
        self.face(top, mat, [(p[0] / s, p[1] / s) for p in poly])
        self.face(list(reversed(bot)), mat, [(p[0] / s, p[1] / s) for p in poly])
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            self.face(
                [(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)],
                mat, self._uv(length, z1 - z0, mat),
            )

    def finish(self, collection):
        me = bpy.data.meshes.new(self.name)
        if self.bm.verts:
            bmesh.ops.remove_doubles(self.bm, verts=list(self.bm.verts), dist=0.004)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(self.name, me)
        collection.objects.link(ob)
        return ob


def collection(name):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def build_street(data, lib):
    col = collection("Street")
    made = []
    sc = data["streetscape"]
    sections = sc["sections"]
    # Courtyard and a base plane so corners are not holes.
    ground = Mesh("Ground")
    for block in data.get("blocks") or []:
        ground.prism(block["polygon"], -0.2, profiles.CURB_RISE, lib["paving"])
    ground.prism([[-120, -110], [120, -110], [120, 110], [-120, 110]], -0.45, -0.2, lib["grass"])
    made.append(ground.finish(col))
    walk_z = profiles.CURB_RISE
    for kind, z, mat_name in (("asphalt", 0.0, "asphalt"), ("sidewalk", walk_z, "paving"),
                              ("parkway", walk_z, "grass"), ("alley", walk_z, "asphalt")):
        mesh = Mesh(kind)
        for poly in sc["surfaces"].get(kind) or []:
            ring = poly["polygon"]
            if kind == "asphalt":
                continue
            mesh.prism(ring, z - 0.04, z, lib[mat_name])
        if mesh.bm.faces:
            made.append(mesh.finish(col))
        else:
            mesh.bm.free()
    # Full carriageway ribbons, including the square where two roads meet. The old
    # mesh stopped at the curb-return trim, so the corner in front of the camera was a hole.
    # Later roads sit a millimetre higher so the overlap does not flicker.
    lanes = Mesh("Lanes")
    for index, poly in enumerate(sc["surfaces"].get("asphalt") or []):
        top = 0.012 + 0.0015 * index
        lanes.prism(poly["polygon"], top - 0.03, top, lib["asphalt"])
    if lanes.bm.faces:
        made.append(lanes.finish(col))
    else:
        lanes.bm.free()
    curbs = Mesh("Curbs")
    for curb in sc["curb_paths"]:
        _sweep_curb(curbs, curb, sections, lib["curb"])
    if curbs.bm.faces:
        made.append(curbs.finish(col))
    else:
        curbs.bm.free()
    paint = Mesh("Paint")
    # Above the tallest asphalt ribbon. M_LanePaint is near-white so the bars read.
    for cross in sc.get("crosswalks") or []:
        for mark in cross.get("marks") or []:
            paint.prism(mark["polygon"], 0.03, 0.055, lib["lane"])
    for mark in sc.get("markings") or []:
        name = mark.get("material")
        if name == "M_Puddle":
            realism.uv_cover(paint, mark["polygon"], 0.022, 0.032, lib["puddle"])
        elif name == "M_Manhole":
            realism.uv_cover(paint, mark["polygon"], 0.02, 0.04, lib["manhole"])
        else:
            paint.prism(mark["polygon"], 0.028, 0.048, lib["lane"])
    wear = Mesh("Wear")
    realism.scatter_decals(wear, data, lib)
    if wear.bm.faces:
        made.append(wear.finish(col))
    else:
        wear.bm.free()
    if paint.bm.faces:
        made.append(paint.finish(col))
    else:
        paint.bm.free()
    ramps = Mesh("Ramps")
    for ramp in sc.get("ramps") or []:
        _ramp(ramps, ramp, lib["concrete"])
    if ramps.bm.faces:
        made.append(ramps.finish(col))
    else:
        ramps.bm.free()
    return made


def _offset_ribbon(pts, half):
    """A quad-ish ribbon. Returns a ring: left side then reversed right side, inset by `half`."""
    left, right = [], []
    for i, p in enumerate(pts):
        d = _tangent(pts, i)
        n = (-d[1], d[0])
        left.append((p[0] + n[0] * half, p[1] + n[1] * half))
        right.append((p[0] - n[0] * half, p[1] - n[1] * half))
    return left + right[::-1]


def _tangent(pts, i):
    if i == 0:
        a, b = pts[0], pts[1]
    elif i == len(pts) - 1:
        a, b = pts[-2], pts[-1]
    else:
        a, b = pts[i - 1], pts[i + 1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1e-6
    return (dx / L, dy / L)


def _sweep_curb(mesh, curb, sections, mat):
    pts = curb.get("polyline") or []
    if len(pts) < 2:
        return
    cls = curb.get("cls") or "major"
    section = profiles.curb_solid_section(cls if cls in profiles.LANE_W else "major")
    gutter_w = 0.45 if cls != "minor" else 0.30
    if curb.get("kind") == "straight":
        sec = sections.get(curb.get("road_id")) or {}
        gutter_w = (sec.get("gutter") or {}).get("width_m") or gutter_w
        width = float(sec.get("width") or 0.0)
        side = float(curb.get("side") or 1.0)
    else:
        width = None
        side = 1.0
    rings = []
    for i, p in enumerate(pts):
        d = _tangent(pts, i)
        left = (-d[1], d[0])
        if width is None:
            outward = left  # CCW return: sidewalk is to the left
            flow = (p[0], p[1])
        else:
            outward = (left[0] * side, left[1] * side)
            flow = (p[0] + outward[0] * width / 2.0, p[1] + outward[1] * width / 2.0)
        ring = []
        for x, z in section:
            shift = x - gutter_w
            ring.append((flow[0] + outward[0] * shift, flow[1] + outward[1] * shift, z))
        rings.append(ring)
    n = len(section)
    for i in range(len(rings) - 1):
        a, b = rings[i], rings[i + 1]
        for k in range(n):
            k2 = (k + 1) % n
            mesh.face([a[k], b[k], b[k2], a[k2]], mat, [(0, 0), (1, 0), (1, 1), (0, 1)])


def _ramp(mesh, ramp, mat):
    spec = ramp.get("spec") or {}
    run = float(spec.get("run_m") or 1.8)
    rise = float(spec.get("rise_m") or 0.15)
    w = float(spec.get("width_m") or 1.2)
    yaw = math.radians(float(ramp.get("yaw") or 0))
    side = float(ramp.get("side") or 1)
    # The ramp climbs away from the carriageway. side +1 is left of the bearing.
    forward = (math.cos(yaw), math.sin(yaw))
    left = (-forward[1], forward[0])
    outward = (left[0] * side, left[1] * side)
    origin = (float(ramp["x"]), float(ramp["y"]))
    hw = w / 2.0
    across = (-outward[1], outward[0])
    def p(along, acc, z):
        return (origin[0] + outward[0] * along + across[0] * acc,
                origin[1] + outward[1] * along + across[1] * acc, z)
    mesh.face([p(0, -hw, 0.02), p(0, hw, 0.02), p(run, hw, rise), p(run, -hw, rise)], mat,
              [(0, 0), (1, 0), (1, 1), (0, 1)])


def make_prototypes(data, lib):
    import blender_street_kit as kit
    protos = {}
    lamp = kit.street_lamp(do_export=False)
    lamp.hide_render = True
    lamp.hide_set(True)
    protos["lamp"] = lamp
    drain = kit.storm_drain(do_export=False)
    drain.hide_render = True
    drain.hide_set(True)
    protos["drain"] = drain
    boll = kit.bollard(do_export=False)
    boll.hide_render = True
    boll.hide_set(True)
    protos["bollard"] = boll
    species = sorted({
        (p.get("species") or "linden")
        for p in (data.get("streetscape") or {}).get("props") or []
        if p.get("kind") == "tree"
    }) or ["linden"]
    for name in species:
        # Species card counts (320-440), with the CC0 cluster on M_Leaves_*.
        ob = kit.tree(name, do_export=False)
        ob.hide_render = True
        ob.hide_set(True)
        protos["tree_" + name] = ob
    protos["bench"] = _bench()
    protos["hydrant"] = _hydrant()
    protos.update(realism.prototypes(lib, Mesh))
    return protos


def _bench():
    B = Mesh("SK_Bench")
    wood = flat("M_BenchWood", (0.35, 0.22, 0.12), 0.6)
    steel = flat("M_BenchSteel", (0.15, 0.15, 0.16), 0.4)
    B.box((0, 0, 0.45), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1.6, 0.45, 0.06), wood)
    B.box((0, -0.16, 0.78), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1.6, 0.06, 0.42), wood)
    for x in (-0.65, 0.65):
        B.box((x, 0, 0.22), (1, 0, 0), (0, 1, 0), (0, 0, 1), (0.06, 0.4, 0.44), steel)
    col = collection("Prototypes")
    ob = B.finish(col)
    ob.hide_render = True
    ob.hide_set(True)
    return ob


def _hydrant():
    B = Mesh("SK_Hydrant")
    body = flat("M_Hydrant", (0.55, 0.12, 0.1), 0.45)
    B.box((0, 0, 0.35), (1, 0, 0), (0, 1, 0), (0, 0, 1), (0.28, 0.28, 0.7), body)
    B.box((0, 0, 0.78), (1, 0, 0), (0, 1, 0), (0, 0, 1), (0.22, 0.22, 0.16), body)
    B.box((0.2, 0, 0.48), (1, 0, 0), (0, 1, 0), (0, 0, 1), (0.16, 0.1, 0.1), body)
    col = bpy.data.collections["Prototypes"]
    ob = B.finish(col)
    ob.hide_render = True
    ob.hide_set(True)
    return ob


def place_props(data, protos, into, lib):
    col = bpy.data.collections["Street"]
    props = data["streetscape"].get("props") or []
    for prop in props:
        kind = prop["kind"]
        if kind == "tree":
            src = protos.get("tree_" + (prop.get("species") or "linden")) or protos.get("tree_linden")
        elif kind == "sign":
            src = protos.get("sign_" + (prop.get("label") or "CAFE"))
        else:
            src = protos.get(kind)
        if src is None:
            continue
        z = 0.02 if kind == "drain" else profiles.CURB_RISE
        ob = bpy.data.objects.new(prop["id"], src.data)
        ob.location = (prop["x"], prop["y"], z)
        ob.rotation_euler = (0, 0, _yaw_to_road(prop))
        col.objects.link(ob)
        into.append(ob)
    wires = Mesh("Wires")
    realism.wires(wires, props, lib["metal"])
    if wires.bm.faces:
        into.append(wires.finish(col))
    else:
        wires.bm.free()


def _yaw_to_road(prop):
    """Kit props face -Y. Turn that toward the carriageway."""
    bearing = math.radians(float(prop.get("yaw") or 0))
    d = (math.cos(bearing), math.sin(bearing))
    left = (-d[1], d[0])
    side = float(prop.get("side") or 1)
    toward = (-left[0] * side, -left[1] * side)
    # local -Y maps to (sin theta, -cos theta)
    return math.atan2(toward[0], -toward[1])


def build_style(style, buildings, context, lib):
    groups = {
        "lod0": [],
        "lod1": [],
        "lod2": [],
        "far": [],
    }
    cols = {name: collection("%s_%s" % (style, name)) for name in groups}
    for building in list(buildings) + list(context):
        groups["lod0"].append(build_lod0(building, lib, cols["lod0"]))
        groups["lod1"].append(build_bands(building, lib, cols["lod1"], banded=True))
        groups["lod2"].append(build_bands(building, lib, cols["lod2"], banded=False))
        groups["far"].append(build_far(building, style, lib, cols["far"]))
    for name in ("lod1", "lod2", "far"):
        for ob in groups[name]:
            ob.hide_render = True
    return groups


def build_lod0(building, lib, col):
    mesh = Mesh(building["id"] + "_LOD0")
    wall = lib.get(building.get("materials", {}).get("wall") or "brick", lib["brick"])
    trim = lib.get(building.get("materials", {}).get("trim") or "plaster", lib["plaster"])
    metal = lib["metal"]
    lift = profiles.CURB_RISE
    for fl in building.get("floors") or []:
        poly = fl["polygon"]
        z1 = fl["z"] + lift + fl["h"]
        # Terrace plate. A setback reads because the plate below is wider.
        mesh.prism(poly, z1 - 0.22, z1, trim if fl.get("cornice") else wall)
    for facade in building.get("facades") or []:
        _facade(mesh, building, facade, wall, trim, metal, lib)
    _roof(mesh, building, wall, trim, metal, lib["roof"])
    for balcony in building.get("balconies") or []:
        _balcony(mesh, balcony, trim, metal)
    return mesh.finish(col)


def _facade(mesh, building, facade, wall, trim, metal, lib):
    ax, ay = facade["a"]
    bx, by = facade["b"]
    length = facade["length"] or 1.0
    tx, ty = (bx - ax) / length, (by - ay) / length
    nx, ny = facade["normal"]
    ix, iy = -nx, -ny
    # Ground floor meets the sidewalk. The model stores z from the lane edge.
    z0 = float(facade["z"]) + profiles.CURB_RISE
    h = float(facade["h"])
    recess = float(building.get("recess_m") or 0.15)
    pier_w = float(facade["pier_w"])
    open_w = float(facade["opening_w"])
    bays = int(facade["bays"])
    sill_r, head_r = float(building.get("sill") or 0.3), float(building.get("head") or 0.75)
    sill_r += float(facade.get("sill_shift") or 0)
    opening = facade["opening"]
    if opening == "storefront":
        sill_r, head_r = 0.02, 0.9
    elif opening == "curtain":
        sill_r, head_r = 0.06, 0.94
    elif opening == "alley":
        sill_r, head_r = 0.42, 0.72
    sill = z0 + h * max(0.0, min(0.85, sill_r))
    head = z0 + h * max(sill_r + 0.2, min(0.98, head_r))
    thick = recess + 0.2
    tangent = (tx, ty, 0)
    inward = (ix, iy, 0)
    up = (0, 0, 1)
    # Top spandrel, full width, so the floors stack as bands.
    _span(mesh, (ax, ay), tangent, inward, up, length, thick, head, z0 + h, wall)
    kinds = facade.get("bay_kinds") or []
    cursor = 0.0
    for i in range(bays):
        kind = kinds[i] if i < len(kinds) else "window"
        _span(mesh, (ax + tx * cursor, ay + ty * cursor), tangent, inward, up, pier_w, thick, z0, z0 + h, trim)
        cursor += pier_w
        origin = (ax + tx * cursor, ay + ty * cursor)
        if kind == "blind":
            _span(mesh, origin, tangent, inward, up, open_w, thick, z0, z0 + h, wall)
            cursor += open_w
            continue
        bay_w = open_w * (0.58 if kind == "narrow" else 1.0)
        inset = (open_w - bay_w) / 2.0
        if inset > 0.02:
            _span(mesh, origin, tangent, inward, up, inset, thick, z0, z0 + h, wall)
        bay_sill, bay_head = sill, head
        if kind == "door":
            realism.pedestrian_door(mesh, building, facade, i, origin, tangent, inward, bay_w, z0, head, lib)
            cursor += open_w
            continue
        elif kind == "transom":
            bay_sill = z0 + h * 0.46
        elif kind == "storefront":
            # A shopfront, not a bay of glass the full storey tall.
            bay_sill = z0 + profiles.STORE_SILL
            bay_head = min(head, z0 + profiles.STORE_HEAD)
        if bay_sill > z0 + 0.05:
            _span(mesh, (origin[0] + tx * inset, origin[1] + ty * inset), tangent, inward, up,
                  bay_w, thick, z0, bay_sill, wall)
        win_o = (origin[0] + tx * inset, origin[1] + ty * inset)
        _window(mesh, building, facade, i, win_o,
                tangent, inward, bay_w, bay_sill, bay_head, recess, lib, kind)
        if kind == "storefront":
            if bay_head < head - 0.05:
                _span(mesh, win_o, tangent, inward, up, bay_w, thick, bay_head, head, wall)
            realism.shop_band(mesh, building, facade, i, win_o, tangent, inward, bay_w, z0, bay_head, lib)
        if kind in ("mullion", "curtain") and bay_w > 1.4:
            bar = min(0.08, bay_w * 0.04)
            _span(mesh, (origin[0] + tx * (inset + bay_w / 2.0 - bar / 2.0),
                         origin[1] + ty * (inset + bay_w / 2.0 - bar / 2.0)),
                  tangent, inward, up, bar, thick * 0.35, bay_sill, bay_head, trim)
        if inset > 0.02:
            _span(mesh, (origin[0] + tx * (inset + bay_w), origin[1] + ty * (inset + bay_w)),
                  tangent, inward, up, inset, thick, z0, z0 + h, wall)
        cursor += open_w
    _span(mesh, (ax + tx * cursor, ay + ty * cursor), tangent, inward, up, max(0.05, length - cursor), thick, z0, z0 + h, trim)
    cornice = float(facade.get("cornice") or 0)
    if int(facade.get("floor") or 0) > 0:
        mid = (ax + tx * length / 2.0 + nx * 0.06, ay + ty * length / 2.0 + ny * 0.06, z0 + 0.04)
        mesh.box(mid, tangent, (nx, ny, 0), up, (length, 0.14, 0.07), trim)
    if cornice > 0.05:
        # A ledge proud of the wall. The seed changes how heavy it is from building to building.
        scale = 0.65 + 0.7 * geom.rnd(int(building.get("seed") or 1), building["id"], int(facade.get("floor") or 0), "cornice")
        depth = min(0.75, cornice * 0.42 * scale)
        centre = (ax + tx * length / 2.0 - nx * depth / 2.0,
                  ay + ty * length / 2.0 - ny * depth / 2.0,
                  z0 + h - 0.08)
        mesh.box(centre, tangent, (nx, ny, 0), up, (length, depth, 0.16 + 0.14 * scale), trim)


def _span(mesh, origin_xy, tangent, inward, up, length, thick, z0, z1, mat):
    if length <= 0.02 or z1 <= z0 + 0.01:
        return
    centre = (origin_xy[0] + tangent[0] * length / 2.0 + inward[0] * thick / 2.0,
              origin_xy[1] + tangent[1] * length / 2.0 + inward[1] * thick / 2.0,
              (z0 + z1) / 2.0)
    mesh.box(centre, tangent, inward, up, (length, thick, z1 - z0), mat)


def _window(mesh, building, facade, bay, origin_xy, tangent, inward, width, z0, z1, recess, lib, kind="window"):
    if z1 <= z0 + 0.15 or width < 0.2:
        return
    # Punched openings are deep enough to read from the street. Curtain bays stay shallower
    # but still step back behind the mullion, so the glass is not a decal on the pier.
    jitter = 0.82 + 0.36 * geom.rnd(int(building.get("seed") or 1), building["id"], int(facade.get("floor") or 0), bay, "depth")
    if facade.get("opening") == "curtain" or kind in ("curtain", "mullion"):
        depth = max(0.55, recess * 3.0) * jitter
    else:
        depth = max(1.05, recess * 3.2) * jitter
    jamb = min(0.16, width * 0.14)
    frame = lib["plaster"]
    # Reveal: the frame steps back from the wall face, which is what makes the opening a hole.
    for side, along in ((0.0, jamb), (width - jamb, jamb)):
        _span(mesh, (origin_xy[0] + tangent[0] * side - inward[0] * 0.04,
                     origin_xy[1] + tangent[1] * side - inward[1] * 0.04),
              tangent, inward, (0, 0, 1), along, depth + 0.08, z0, z1, frame)
    _span(mesh, (origin_xy[0] - inward[0] * 0.04, origin_xy[1] - inward[1] * 0.04),
          tangent, inward, (0, 0, 1), width, depth + 0.08, z1 - jamb, z1, frame)
    _span(mesh, (origin_xy[0] - inward[0] * 0.04, origin_xy[1] - inward[1] * 0.04),
          tangent, inward, (0, 0, 1), width, depth + 0.08, z0, z0 + jamb * 0.65, frame)
    # A stone sill proud of the wall, so the recess catches a shadow line.
    sill_c = (origin_xy[0] + tangent[0] * width / 2.0 - inward[0] * 0.12,
              origin_xy[1] + tangent[1] * width / 2.0 - inward[1] * 0.12,
              z0 + 0.04)
    mesh.box(sill_c, tangent, inward, (0, 0, 1), (width + 0.14, 0.28, 0.11), frame)
    lintel_c = (origin_xy[0] + tangent[0] * width / 2.0 - inward[0] * 0.08,
                origin_xy[1] + tangent[1] * width / 2.0 - inward[1] * 0.08,
                z1 - 0.04)
    mesh.box(lintel_c, tangent, inward, (0, 0, 1), (width + 0.08, 0.2, 0.1), frame)
    if kind not in ("curtain", "mullion", "storefront") and (z1 - z0) > 0.8:
        bar = 0.045
        _span(mesh, origin_xy, tangent, inward, (0, 0, 1), width, 0.08, (z0 + z1) / 2.0 - bar / 2.0, (z0 + z1) / 2.0 + bar / 2.0, frame)
    pane_z = (z0 + z1) / 2.0
    lit = grammar.bay_lit(building.get("seed") or 1, building["id"], facade["floor"], bay)
    # Shopfronts look into the room built in realism._shop. Other bays keep a back wall.
    if kind != "storefront":
        room = (origin_xy[0] + tangent[0] * width / 2.0 + inward[0] * (depth + 0.06),
                origin_xy[1] + tangent[1] * width / 2.0 + inward[1] * (depth + 0.06),
                pane_z)
        mesh.box(room, tangent, inward, (0, 0, 1), (width * 0.98, 0.06, (z1 - z0) * 0.98),
                 lib["interior_lit"] if lit else lib["interior"])
    centre = (origin_xy[0] + tangent[0] * width / 2.0 + inward[0] * (depth * 0.72),
              origin_xy[1] + tangent[1] * width / 2.0 + inward[1] * (depth * 0.72),
              pane_z)
    glass = lib["glass"] if kind == "storefront" else (lib["glass_lit"] if lit else lib["glass"])
    mesh.box(centre, tangent, inward, (0, 0, 1), (max(0.2, width - jamb * 2), 0.015, max(0.3, z1 - z0 - jamb * 2)), glass)
    realism.dress_opening(mesh, building, facade, bay, origin_xy, tangent, inward, width, z0, z1, depth, lib, kind)


def _roof(mesh, building, wall, trim, metal, roof_mat):
    roof = building.get("roof") or {}
    floors = building.get("floors") or []
    if not floors:
        return
    poly = floors[-1]["polygon"]
    z = float(roof.get("z") or (floors[-1]["z"] + floors[-1]["h"])) + profiles.CURB_RISE
    h = float(roof.get("h") or 1.0)
    shape = roof.get("shape") or "flat"
    deck = z
    if shape in ("flat", "parapet"):
        mesh.prism(poly, z, z + 0.16, roof_mat)
        _parapet(mesh, poly, z, float(building.get("parapet_m") or 1.1), trim)
        deck = z
    elif shape == "gabled":
        _gable(mesh, poly, z, h, roof_mat)
        deck = z + h
    elif shape == "hipped":
        _hip(mesh, poly, z, h, roof_mat)
        deck = z + h
    elif shape == "mansard":
        deck = _mansard(mesh, poly, z, h, roof_mat, trim)
    elif shape == "setback":
        deck = _setback_roof(mesh, poly, z, h, roof_mat, trim)
    elif shape == "pyramidal":
        _pyramid(mesh, poly, z, h, roof_mat)
        deck = z + h
    elif shape == "dome":
        _dome(mesh, poly, z, h, roof_mat)
        deck = z + h
    if shape in ("flat", "parapet", "setback", "mansard"):
        for unit in roof.get("units") or []:
            placed = dict(unit)
            placed["z"] = deck
            _unit(mesh, placed, metal, roof_mat)


def _parapet(mesh, poly, z, height, mat):
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1
        tx, ty = dx / L, dy / L
        # outward is to the right of a CCW edge
        ox, oy = dy / L, -dx / L
        centre = ((a[0] + b[0]) / 2.0 - ox * 0.12, (a[1] + b[1]) / 2.0 - oy * 0.12, z + height / 2.0)
        mesh.box(centre, (tx, ty, 0), (ox, oy, 0), (0, 0, 1), (L, 0.22, height), mat)


def _face_up(mesh, pts, mat):
    """A roof face whose normal points up. Three or four points."""
    if len(pts) < 3:
        return
    ax = pts[1][0] - pts[0][0]
    ay = pts[1][1] - pts[0][1]
    bx = pts[2][0] - pts[0][0]
    by = pts[2][1] - pts[0][1]
    if ax * by - ay * bx < 0:
        pts = list(reversed(pts))
    if len(pts) == 3:
        uvs = [(0, 0), (1, 0), (0.5, 1)]
    else:
        uvs = [(0, 0), (1, 0), (1, 1), (0, 1)]
    mesh.face(pts, mat, uvs)


def _hip(mesh, poly, z, h, mat):
    """A hip: ridge along the long axis, triangular ends. Not a gable with the ridge to the eave."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    sx, sy = x1 - x0, y1 - y0
    if sx >= sy:
        inset = sy / 2.0
        mid = (y0 + y1) / 2.0
        r0 = (x0 + inset, mid, z + h)
        r1 = (x1 - inset, mid, z + h)
        if r1[0] - r0[0] < 0.2:
            c = ((x0 + x1) / 2.0, mid, z + h)
            _face_up(mesh, [(x0, y0, z), (x1, y0, z), c], mat)
            _face_up(mesh, [(x1, y1, z), (x0, y1, z), c], mat)
            _face_up(mesh, [(x0, y1, z), (x0, y0, z), c], mat)
            _face_up(mesh, [(x1, y0, z), (x1, y1, z), c], mat)
            return
        _face_up(mesh, [(x0, y0, z), (x1, y0, z), r1, r0], mat)
        _face_up(mesh, [(x1, y1, z), (x0, y1, z), r0, r1], mat)
        _face_up(mesh, [(x0, y0, z), r0, (x0, y1, z)], mat)
        _face_up(mesh, [(x1, y0, z), (x1, y1, z), r1], mat)
    else:
        inset = sx / 2.0
        mid = (x0 + x1) / 2.0
        r0 = (mid, y0 + inset, z + h)
        r1 = (mid, y1 - inset, z + h)
        if r1[1] - r0[1] < 0.2:
            c = (mid, (y0 + y1) / 2.0, z + h)
            _face_up(mesh, [(x0, y0, z), (x1, y0, z), c], mat)
            _face_up(mesh, [(x1, y1, z), (x0, y1, z), c], mat)
            _face_up(mesh, [(x0, y1, z), (x0, y0, z), c], mat)
            _face_up(mesh, [(x1, y0, z), (x1, y1, z), c], mat)
            return
        _face_up(mesh, [(x0, y0, z), (x1, y0, z), r0], mat)
        _face_up(mesh, [(x1, y1, z), (x0, y1, z), r1], mat)
        _face_up(mesh, [(x0, y0, z), r0, r1, (x0, y1, z)], mat)
        _face_up(mesh, [(x1, y0, z), (x1, y1, z), r1, r0], mat)


def _mansard(mesh, poly, z, h, mat, trim):
    """Steep lower slope, then a flat cap with a low parapet. Returns the deck height for roof units."""
    ring = [tuple(p) for p in poly]
    span = min(geom.spans(ring))
    run = min(2.6, max(1.2, span * 0.22))
    inner = geom.offset_polygon(ring, run)
    if not inner or len(inner) != len(ring):
        _hip(mesh, poly, z, h * 0.55, mat)
        return z + h * 0.55
    z1 = z + max(2.2, h * 0.72)
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        c, d = inner[i], inner[(i + 1) % len(inner)]
        _face_up(mesh, [(a[0], a[1], z), (b[0], b[1], z), (d[0], d[1], z1), (c[0], c[1], z1)], mat)
    mesh.prism(inner, z1, z1 + 0.16, mat)
    _parapet(mesh, inner, z1 + 0.16, 0.65, trim)
    return z1 + 0.16


def _setback_roof(mesh, poly, z, h, mat, trim):
    """A flat roof, a parapet, and a penthouse stepped in from the plate."""
    mesh.prism(poly, z, z + 0.14, mat)
    _parapet(mesh, poly, z, 0.8, trim)
    ring = [tuple(p) for p in poly]
    span = min(geom.spans(ring))
    run = min(3.4, max(1.6, span * 0.16))
    inner = geom.offset_polygon(ring, run)
    pent = max(3.0, h)
    if not inner or len(inner) < 3:
        return z
    mesh.prism(inner, z, z + pent, trim)
    cap = geom.offset_polygon(inner, min(1.2, run * 0.4))
    if cap and len(cap) >= 3 and geom.poly_area(cap) > 4.0:
        mesh.prism(cap, z + pent, z + pent + 1.6, mat)
    return z + pent


def _gable(mesh, poly, z, h, mat):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if (x1 - x0) >= (y1 - y0):
        ridge = [((x0 + x1) / 2.0, y0, z + h), ((x0 + x1) / 2.0, y1, z + h)]
        mesh.face([(x0, y0, z), (x1, y0, z), ridge[0]], mat, [(0, 0), (1, 0), (0.5, 1)])
        mesh.face([(x1, y1, z), (x0, y1, z), ridge[1]], mat, [(0, 0), (1, 0), (0.5, 1)])
        mesh.face([(x0, y0, z), ridge[0], ridge[1], (x0, y1, z)], mat, [(0, 0), (1, 0), (1, 1), (0, 1)])
        mesh.face([(x1, y0, z), (x1, y1, z), ridge[1], ridge[0]], mat, [(0, 0), (1, 0), (1, 1), (0, 1)])
    else:
        ridge = [(x0, (y0 + y1) / 2.0, z + h), (x1, (y0 + y1) / 2.0, z + h)]
        mesh.face([(x0, y0, z), (x0, y1, z), ridge[0]], mat, [(0, 0), (1, 0), (0.5, 1)])
        mesh.face([(x1, y1, z), (x1, y0, z), ridge[1]], mat, [(0, 0), (1, 0), (0.5, 1)])
        mesh.face([(x0, y0, z), ridge[0], ridge[1], (x1, y0, z)], mat, [(0, 0), (1, 0), (1, 1), (0, 1)])
        mesh.face([(x0, y1, z), (x1, y1, z), ridge[1], ridge[0]], mat, [(0, 0), (1, 0), (1, 1), (0, 1)])


def _pyramid(mesh, poly, z, h, mat):
    c = (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly), z + h)
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        mesh.face([(a[0], a[1], z), (b[0], b[1], z), c], mat, [(0, 0), (1, 0), (0.5, 1)])


def _dome(mesh, poly, z, h, mat):
    c = (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))
    r = min(max(p[0] for p in poly) - min(p[0] for p in poly),
            max(p[1] for p in poly) - min(p[1] for p in poly)) * 0.45
    rings = 4
    segs = 8
    prev = None
    for i in range(rings + 1):
        t = i / rings
        ang = t * math.pi / 2.0
        rad = r * math.cos(ang)
        zz = z + h * math.sin(ang)
        ring = [(c[0] + rad * math.cos(2 * math.pi * k / segs),
                 c[1] + rad * math.sin(2 * math.pi * k / segs), zz) for k in range(segs)]
        if prev:
            for k in range(segs):
                mesh.face([prev[k], prev[(k + 1) % segs], ring[(k + 1) % segs], ring[k]], mat,
                          [(0, 0), (1, 0), (1, 1), (0, 1)])
        prev = ring


def _unit(mesh, unit, metal, roof_mat):
    x, y, z = float(unit["x"]), float(unit["y"]), float(unit["z"])
    kind = unit.get("kind")
    if kind == "water_tank":
        mesh.box((x, y, z + 2.2), (1, 0, 0), (0, 1, 0), (0, 0, 1), (3.2, 3.2, 3.4), metal)
        mesh.box((x, y, z + 4.1), (1, 0, 0), (0, 1, 0), (0, 0, 1), (3.6, 3.6, 0.25), metal)
    elif kind == "antenna":
        mesh.box((x, y, z + 4.0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (0.15, 0.15, 8.0), metal)
    elif kind == "stair":
        mesh.box((x, y, z + 1.6), (1, 0, 0), (0, 1, 0), (0, 0, 1), (3.0, 4.0, 3.2), roof_mat)
    else:
        mesh.box((x, y, z + 0.8), (1, 0, 0), (0, 1, 0), (0, 0, 1), (3.4, 2.2, 1.5), metal)


def _balcony(mesh, balcony, trim, metal):
    nx, ny = balcony["normal"]
    w, d = float(balcony["w"]), float(balcony["d"])
    centre = (balcony["x"] + nx * d / 2.0, balcony["y"] + ny * d / 2.0, balcony["z"] + profiles.CURB_RISE + 0.08)
    tangent = (-ny, nx, 0)
    mesh.box(centre, tangent, (nx, ny, 0), (0, 0, 1), (w, d, 0.12), trim)
    rail_c = (centre[0] + nx * d / 2.0, centre[1] + ny * d / 2.0, balcony["z"] + profiles.CURB_RISE + 0.55)
    mesh.box(rail_c, tangent, (nx, ny, 0), (0, 0, 1), (w, 0.04, 0.08), metal)


def build_bands(building, lib, col, banded):
    mesh = Mesh(building["id"] + ("_LOD1" if banded else "_LOD2"))
    wall = lib.get(building.get("materials", {}).get("wall") or "brick", lib["brick"])
    trim = lib["trim_dark"]
    floors = building.get("floors") or []
    for fl in floors:
        z0, z1 = fl["z"] + profiles.CURB_RISE, fl["z"] + profiles.CURB_RISE + fl["h"]
        if banded and fl["h"] > 0.6:
            mesh.prism(fl["polygon"], z0, z1 - 0.18, wall)
            mesh.prism(fl["polygon"], z1 - 0.18, z1, trim)
        else:
            mesh.prism(fl["polygon"], z0, z1, wall)
    if floors:
        _roof(mesh, building, wall, trim, lib["metal"], lib["roof"])
    return mesh.finish(col)


def build_far(building, style, lib, col):
    floors = building.get("floors") or []
    mesh = Mesh(building["id"] + "_FAR")
    if not floors:
        return mesh.finish(col)
    # One shell: the ground plate up to the roof, plus the baked grid on the walls.
    poly = floors[0]["polygon"]
    z1 = floors[-1]["z"] + profiles.CURB_RISE + floors[-1]["h"]
    mat = facade_material(style)
    mesh.prism(poly, profiles.CURB_RISE, z1, mat)
    return mesh.finish(col)


def facade_material(style):
    name = "M_Facade_" + style
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    path = os.path.join(ART, "facades", "T_CG_Facade_%s.png" % style)
    if os.path.isfile(path):
        img = bpy.data.images.load(path)
        tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = img
        mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def render_style(style, cameras, visible):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 6
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 2
    scene.cycles.transparent_max_bounces = 8
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    realism.grade(scene)
    world = bpy.data.worlds.new("Sky_" + style)
    scene.world = world
    world.use_nodes = True
    shots = []
    if os.environ.get("SKYCITY_SHOTS") == "none":
        return shots
    wanted = [s for s in os.environ.get("SKYCITY_SHOTS", "").split(",") if s] or ["street", "aerial", "dusk"]
    for shot in wanted:
        cam_spec = cameras[shot]
        _look(cam_spec)
        realism.sky(world, cam_spec["sun"], shot == "dusk", load_material_record(), ART)
        # Dusk turns the occupied windows up. Day keeps a faint glow so a few read as lit offices.
        set_emission(bpy.data.materials["M_GlassLit"], 4.0 if shot == "dusk" else 0.6)
        set_emission(bpy.data.materials["M_InteriorLit"], 14.0 if shot == "dusk" else 1.2)
        name = "CG_%s_%s.png" % (style, "street_dusk" if shot == "dusk" else shot + "_day")
        scene.render.filepath = os.path.join(PREVIEWS, name)
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        shots.append({"file": name, "seconds": round(time.time() - t0, 1)})
        print("RENDER", name, shots[-1]["seconds"], flush=True)
    return shots


def _look(spec):
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.get("BlockCam") or bpy.data.cameras.new("BlockCam")
    cam = bpy.data.objects.get("BlockCam")
    if cam is None:
        cam = bpy.data.objects.new("BlockCam", cam_data)
        scene.collection.objects.link(cam)
    loc = spec["location"]
    tgt = spec["target"]
    cam.location = (loc[0], loc[1], loc[2])
    direction = (tgt[0] - loc[0], tgt[1] - loc[1], tgt[2] - loc[2])
    from mathutils import Vector
    quat = Vector(direction).to_track_quat("-Z", "Y")
    cam.rotation_euler = quat.to_euler()
    cam.data.lens = float(spec.get("lens") or 32)
    cam.data.clip_start = 0.05
    cam.data.clip_end = 2000
    try:
        cam.data.sensor_width = 36.0
    except (AttributeError, TypeError):
        pass
    realism.focus(cam, spec)
    scene.camera = cam


def _sun(world, sun_spec, dusk):
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(float(sun_spec["elevation"]))
    sky.sun_rotation = math.radians(float(sun_spec["rotation"]))
    sky.sun_intensity = 0.15 if dusk else 0.4
    sky.sun_disc = True
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.35 if dusk else 1.0
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    light_data = bpy.data.lights.get("Key") or bpy.data.lights.new("Key", "SUN")
    light = bpy.data.objects.get("Key")
    if light is None:
        light = bpy.data.objects.new("Key", light_data)
        bpy.context.scene.collection.objects.link(light)
    light.data.energy = 2.2 if dusk else 4.5
    light.data.angle = math.radians(1.5 if not dusk else 2.5)
    light.data.color = (1.0, 0.55, 0.32) if dusk else (1.0, 0.97, 0.92)
    elev = math.radians(float(sun_spec["elevation"]))
    rot = math.radians(float(sun_spec["rotation"]))
    light.rotation_euler = (math.pi / 2.0 - elev, 0.0, rot)


def export_style(style, groups, street_objects):
    sizes = {}
    pivot = bpy.data.objects.new("Pivot_" + style, None)
    bpy.context.scene.collection.objects.link(pivot)
    # Plan frame, then -90 Z, matching Scripts/landmarks/blender_landmarks.py.
    pivot.rotation_euler = (0.0, 0.0, -math.pi / 2.0)
    mapping = {
        "LOD0": groups["lod0"],
        "LOD1": groups["lod1"],
        "LOD2": groups["lod2"],
        "FAR": groups["far"],
    }
    for label, objs in mapping.items():
        for ob in objs:
            ob.parent = pivot
            ob.hide_render = False
        path = os.path.join(BLOCKS, "CG_Block_%s_%s.glb" % (style, label))
        _export(path, [pivot] + objs)
        for ob in objs:
            ob.parent = None
        sizes[label] = os.path.getsize(path)
    for ob in groups["lod1"]:
        ob.parent = pivot
    for ob in street_objects:
        if ob.name.startswith("SK_") or ob.hide_render:
            continue
        ob.parent = pivot
    web_objs = [pivot] + groups["lod1"] + [ob for ob in street_objects if not ob.hide_render]
    path = os.path.join(BLOCKS, "CG_Block_%s_web.glb" % style)
    _export(path, web_objs)
    sizes["web"] = os.path.getsize(path)
    for ob in groups["lod1"] + street_objects:
        ob.parent = None
    bpy.data.objects.remove(pivot, do_unlink=True)
    tris = {}
    for label, objs in mapping.items():
        tris[label] = sum(len(ob.data.polygons) for ob in objs if ob.data)
    print("EXPORT", style, sizes, tris, flush=True)
    return {"bytes": sizes, "tris": tris}


def _export(path, objs):
    bpy.ops.object.select_all(action="DESELECT")
    for ob in objs:
        ob.hide_set(False)
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(
        filepath=path, export_format="GLB", use_selection=True, export_apply=False,
        export_yup=True, export_materials="EXPORT", export_image_format="NONE",
    )


def clear_groups(groups):
    for objs in groups.values():
        for ob in objs:
            mesh = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)


if __name__ == "__main__":
    main()
