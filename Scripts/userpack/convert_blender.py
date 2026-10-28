"""Convert one pack asset (USD or GLB) into a game-ready GLB, in Blender headless (5.2, `-t 2`).

  Blender -b -t 2 --python Scripts/userpack/convert_blender.py -- <recipe.json> <asset id> <out dir>

What it does, in order (the recipe row is UserPacks/game/recipes.json "assets"[id]):
  1. Import: USD through Blender's USD importer, GLB through the glTF importer. USD materials come in empty (NVIDIA's
     props use OmniPBR MDL), so their textures are wired from the USD shader inputs or from the .mdl file's OmniPBR
     arguments (diffuse / ORM / normal / opacity, tint, texture_scale). UDIM tile sets are packed into one atlas
     (a grid of tiles, the UVs moved into their cell), so every material ends with plain 0..1 textures glTF can carry.
  2. One mesh: every mesh object is joined into one, transforms applied. Hidden prims and collision proxies are dropped.
  3. Real metres, +Z up, the pack convention (the generator's prop frame): the front faces +X, the pivot is the middle
     of the footprint at ground level. `yaw_deg` turns the asset about Z first; `size` scales it uniformly so one
     dimension (x = length along the front, y = across, z = height) reads its real value.
  4. Budget: the collapse decimator brings LOD0 down to `tris`; every texture is resized to at most `tex` pixels on its
     long side. Materials that share one texture set are merged, so a pack mesh carries few slots.
  5. Export GLB (+Y up in the file, as glTF requires; Unreal's importer turns it back to +Z up) with the credit in
     asset.copyright and {"bt_userpack": {...}} in the scene extras, so a pack file is recognisable wherever it lands
     (building-types' guard test refuses any file that carries the stamp). Stats go to <out>/<id>.json.

No pack file is written anywhere but <out dir> (the external drive's AssetBuilds/game_pack/).
"""
import glob
import json
import math
import os
import re
import sys

import bpy
import bmesh
import mathutils

try:
    import numpy as np
except ImportError:  # Blender always ships NumPy; the guard keeps a clear message if it does not
    np = None


def log(*a):
    print("USERPACK", *a, flush=True)


# ---------------------------------------------------------------------------------------------------------------
# USD materials (NVIDIA OmniPBR)

MDL_ARG = re.compile(r"(\w+)\s*:\s*(texture_2d\(\s*\"([^\"]*)\"[^)]*\)|color\(([^)]*)\)|float2\(([^)]*)\)|"
                     r"(true|false)|(-?[0-9.]+))")


def _mdl_args(path):
    """OmniPBR(...) arguments of a wrapper .mdl file: {name: value} (textures as paths relative to the .mdl)."""
    out = {}
    try:
        text = open(path).read()
    except OSError:
        return out
    for m in MDL_ARG.finditer(text):
        name = m.group(1)
        if m.group(3) is not None:
            out[name] = os.path.normpath(os.path.join(os.path.dirname(path), m.group(3))) if m.group(3) else None
        elif m.group(4) is not None:
            out[name] = tuple(float(v) for v in m.group(4).split(","))
        elif m.group(5) is not None:
            out[name] = tuple(float(v) for v in m.group(5).split(","))
        elif m.group(6) is not None:
            out[name] = m.group(6) == "true"
        elif m.group(7) is not None:
            out[name] = float(m.group(7))
    return out


def usd_material_specs(usd_path):
    """{material name: spec} from the USD stage, through every reference (pxr ships with Blender)."""
    from pxr import Usd, UsdShade, Sdf
    stage = Usd.Stage.Open(usd_path)
    specs = {}
    for prim in stage.Traverse():
        if not prim.IsA(UsdShade.Material):
            continue
        name = prim.GetName()
        spec = {}
        for child in prim.GetChildren():
            if not child.IsA(UsdShade.Shader):
                continue
            shader = UsdShade.Shader(child)
            source = shader.GetSourceAsset("mdl") if shader.GetImplementationSource() == "sourceAsset" else None
            src_path = source.resolvedPath or source.path if source else ""
            base = os.path.basename(str(source.path)) if source else ""
            layer_dir = os.path.dirname(child.GetPrimStack()[0].layer.realPath) if child.GetPrimStack() else ""
            if base not in ("OmniPBR.mdl", "OmniGlass.mdl", "OmniSurface.mdl") and src_path:
                spec.update(_mdl_args(src_path if os.path.isabs(src_path) else os.path.join(layer_dir, src_path)))
            if base == "OmniGlass.mdl":
                spec["glass"] = True
            for inp in shader.GetInputs():
                value = inp.Get()
                if value is None:
                    continue
                key = inp.GetBaseName()
                if isinstance(value, Sdf.AssetPath):
                    path = value.resolvedPath or value.path
                    if path and not os.path.isabs(path):
                        path = os.path.normpath(os.path.join(layer_dir, path))
                    spec[key] = path or None
                elif hasattr(value, "__len__") and not isinstance(value, str):
                    spec[key] = tuple(float(v) for v in value)
                else:
                    spec[key] = value
        specs[name] = spec
    return specs


def _tiles(path):
    """[(udim, file)] for a <UDIM> path, or [(1001, path)] for a plain one; [] when nothing is on disk."""
    if not path:
        return []
    if "<UDIM>" in path:
        out = []
        for f in sorted(glob.glob(path.replace("<UDIM>", "[0-9][0-9][0-9][0-9]"))):
            out.append((int(re.search(r"\.(\d{4})\.", os.path.basename(f)).group(1)), f))
        return out
    return [(1001, path)] if os.path.isfile(path) else []


def _load_pixels(path, size):
    img = bpy.data.images.load(path, check_existing=True)
    if tuple(img.size) != (size, size):
        img.scale(size, size)
    px = np.empty(size * size * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(size, size, 4)


def atlas_image(name, tiles, grid, cell, colorspace):
    """One image of grid tiles (cols x rows) of cell px each; tile k at column k % cols, row k // cols (from the bottom)."""
    cols, rows = grid
    buf = np.zeros((rows * cell, cols * cell, 4), dtype=np.float32)
    buf[..., 3] = 1.0
    for k, (_udim, path) in enumerate(tiles):
        c, r = k % cols, k // cols
        buf[r * cell:(r + 1) * cell, c * cell:(c + 1) * cell] = _load_pixels(path, cell)
    img = bpy.data.images.new(name, cols * cell, rows * cell, alpha=True)
    img.colorspace_settings.name = colorspace
    img.pixels.foreach_set(buf.ravel())
    img.pack()
    return img


def grid_for(n):
    rows = max(1, int(math.floor(math.sqrt(n))))
    cols = int(math.ceil(n / float(rows)))
    while cols & (cols - 1):  # power-of-two cell counts keep the atlas a power of two
        cols += 1
    while rows & (rows - 1):
        rows += 1
    return cols, rows


def remap_udim_uvs(objects, material_names, udims, grid, scale=(1.0, 1.0)):
    """Move each face's UVs (faces with one of material_names) from its UDIM tile into its atlas cell."""
    cols, rows = grid
    index = {u: k for k, u in enumerate(udims)}
    for obj in objects:
        me = obj.data
        if not me.uv_layers:
            continue
        slots = {i for i, s in enumerate(obj.material_slots) if s.material and s.material.name in material_names}
        if not slots:
            continue
        uv = me.uv_layers.active.data
        for poly in me.polygons:
            if poly.material_index not in slots:
                continue
            us = [uv[li].uv[0] * scale[0] for li in poly.loop_indices]
            vs = [uv[li].uv[1] * scale[1] for li in poly.loop_indices]
            if any(x != x for x in us + vs):   # NaN UVs (seen on the forklift): park the face in cell 0
                us = [0.5] * len(us)
                vs = [0.5] * len(vs)
            tu, tv = math.floor(sum(us) / len(us)), math.floor(sum(vs) / len(vs))
            k = index.get(1001 + tu + 10 * tv, 0)
            c, r = k % cols, k // cols
            for li, u, v in zip(poly.loop_indices, us, vs):
                uv[li].uv = ((u - tu + c) / cols, (v - tv + r) / rows)


def scale_uvs(objects, material_names, scale):
    for obj in objects:
        me = obj.data
        if not me.uv_layers:
            continue
        slots = {i for i, s in enumerate(obj.material_slots) if s.material and s.material.name in material_names}
        uv = me.uv_layers.active.data
        for poly in me.polygons:
            if poly.material_index in slots:
                for li in poly.loop_indices:
                    uv[li].uv = (uv[li].uv[0] * scale[0], uv[li].uv[1] * scale[1])


def build_material(name, spec, tex_max, atlas_cache, objects):
    """A Principled material from an OmniPBR spec; UDIM sets become one atlas per texture kind."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    tint = spec.get("diffuse_tint") or (1.0, 1.0, 1.0)
    const = spec.get("diffuse_color_constant") or (0.5, 0.5, 0.5)
    if spec.get("glass"):
        bsdf.inputs["Base Color"].default_value = (0.04, 0.05, 0.055, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.05
        bsdf.inputs["Metallic"].default_value = 0.0
        return mat, []
    diffuse = _tiles(spec.get("diffuse_texture"))
    udims = [u for u, _p in diffuse] or [1001]
    multi = len(udims) > 1
    grid = grid_for(len(udims)) if multi else (1, 1)
    cell = int(tex_max / max(grid)) if multi else tex_max
    used = []

    def tex(kind, colorspace):
        tiles = _tiles(spec.get(kind))
        if not tiles:
            return None
        key = (spec.get(kind), grid, cell)
        if key not in atlas_cache:
            by = dict(tiles)
            ordered = [(u, by.get(u, tiles[0][1])) for u in udims]
            if multi:
                atlas_cache[key] = atlas_image("T_%s_%s" % (name, kind), ordered, grid, cell, colorspace)
            else:
                img = bpy.data.images.load(ordered[0][1], check_existing=True)
                img.colorspace_settings.name = colorspace
                atlas_cache[key] = img
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = atlas_cache[key]
        used.append(node.image)
        return node

    d = tex("diffuse_texture", "sRGB")
    if d is not None:
        if tuple(tint) != (1.0, 1.0, 1.0):
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            nt.links.new(d.outputs["Color"], mix.inputs[6])
            mix.inputs[7].default_value = (tint[0], tint[1], tint[2], 1.0)
            nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        else:
            nt.links.new(d.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (const[0] * tint[0], const[1] * tint[1], const[2] * tint[2], 1.0)
    orm = tex("ORM_texture", "Non-Color")
    if orm is not None:
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(orm.outputs["Color"], sep.inputs[0])
        nt.links.new(sep.outputs[1], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs[2], bsdf.inputs["Metallic"])
    else:
        bsdf.inputs["Roughness"].default_value = float(spec.get("reflection_roughness_constant", 0.6))
        bsdf.inputs["Metallic"].default_value = float(spec.get("metallic_constant", 0.0))
    nrm = tex("normalmap_texture", "Non-Color")
    if nrm is not None:
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(nrm.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if spec.get("enable_opacity") and spec.get("enable_opacity_texture"):
        op = tex("opacity_texture", "Non-Color")
        if op is not None:
            nt.links.new(op.outputs["Color"], bsdf.inputs["Alpha"])
            try:
                mat.surface_render_method = "DITHERED"
            except (AttributeError, TypeError):
                pass
            mat["bt_alpha_mask"] = True
    # UV work for this material's faces: tiling first, then the UDIM atlas cells.
    names = {name}
    scale = spec.get("texture_scale") or (1.0, 1.0)
    if multi:
        remap_udim_uvs(objects, names, udims, grid, scale)
    elif tuple(scale) != (1.0, 1.0):
        scale_uvs(objects, names, scale)
    return mat, used


# ---------------------------------------------------------------------------------------------------------------
# Geometry

def mesh_objects():
    return [o for o in bpy.data.objects if o.type == "MESH"]


def drop_proxies(keep=()):
    """Collision and proxy prims, hidden prims and empty meshes are not part of the visible asset."""
    for o in list(bpy.data.objects):
        if o in keep:
            continue
        low = o.name.lower()
        if o.type == "MESH" and (o.hide_render or o.hide_get() or len(o.data.polygons) == 0
                                 or any(k in low for k in ("collision", "collider", "proxy", "_phys"))):
            bpy.data.objects.remove(o, do_unlink=True)


def join_all():
    objs = mesh_objects()
    if not objs:
        raise SystemExit("no mesh in the asset")
    for o in bpy.data.objects:
        o.select_set(False)
    # Clear parents, keeping the world transform, then apply transforms and join.
    for o in objs:
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    bpy.context.view_layer.objects.active = objs[0]
    for o in objs:
        o.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(objs) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    for o in list(bpy.data.objects):
        if o is not obj:
            bpy.data.objects.remove(o, do_unlink=True)
    obj.name = "Asset"
    return obj


def bounds(obj):
    vs = np.empty(len(obj.data.vertices) * 3, dtype=np.float64)
    obj.data.vertices.foreach_get("co", vs)
    vs = vs.reshape(-1, 3)
    return vs.min(axis=0), vs.max(axis=0)


def tri_count(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def place(obj, yaw_deg, size, dims=None):
    """Yaw about Z, scale to the real size, pivot at the footprint middle on the ground.

    size: {"axis", "m"}, a uniform scale; dims: [x, y, z] metres, a per-axis scale (an AI mesh made from one picture
    often has the depth wrong: a car 2.5 m wide; dims puts its length, width and height to the real ones)."""
    if yaw_deg:
        obj.data.transform(mathutils.Matrix.Rotation(math.radians(yaw_deg), 4, "Z"))
    mn, mx = bounds(obj)
    if dims:
        m = mathutils.Matrix.Diagonal([dims[i] / float(mx[i] - mn[i]) for i in range(3)] + [1.0])
        obj.data.transform(m)
        mn, mx = bounds(obj)
        size = None
    if size:
        axis = "xyz".index(size["axis"])
        k = size["m"] / float(mx[axis] - mn[axis])
        obj.data.transform(mathutils.Matrix.Scale(k, 4))
        mn, mx = bounds(obj)
    obj.data.transform(mathutils.Matrix.Translation((-(mn[0] + mx[0]) / 2.0, -(mn[1] + mx[1]) / 2.0, -mn[2])))
    obj.data.update()


def decimate(obj, target):
    tris = tri_count(obj)
    if not target or tris <= target:
        return tris
    mod = obj.modifiers.new("dec", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = max(0.001, target / float(tris))
    mod.use_collapse_triangulate = True
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return tri_count(obj)


def shrink_images(tex_max):
    for img in bpy.data.images:
        if img.size[0] == 0:
            continue
        w, h = img.size
        if max(w, h) > tex_max:
            k = tex_max / float(max(w, h))
            img.scale(max(1, int(w * k)), max(1, int(h * k)))
            img.pack()


def merge_materials(obj):
    """Slots whose materials use the same images and constants collapse into one slot."""
    def key(mat):
        if mat is None or not mat.use_nodes:
            return ("none",)
        imgs = tuple(sorted(n.image.name for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image))
        consts = []
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                for nm in ("Base Color", "Roughness", "Metallic"):
                    s = n.inputs[nm]
                    if not s.is_linked:
                        v = s.default_value
                        consts.append(tuple(round(x, 3) for x in v) if hasattr(v, "__len__") else round(v, 3))
            if n.type == "MIX":
                consts.append(tuple(round(x, 3) for x in n.inputs[7].default_value))
        return imgs + tuple(consts)
    first = {}
    remap = {}
    for i, slot in enumerate(obj.material_slots):
        k = key(slot.material)
        remap[i] = first.setdefault(k, i)
    if all(remap[i] == i for i in remap):
        return len(obj.material_slots)
    mi = np.empty(len(obj.data.polygons), dtype=np.int32)
    obj.data.polygons.foreach_get("material_index", mi)
    keep = sorted(set(remap.values()))
    newidx = {old: keep.index(remap[old]) for old in remap}
    mi = np.vectorize(newidx.get)(mi).astype(np.int32)
    mats = [obj.material_slots[i].material for i in keep]
    obj.data.materials.clear()
    for m in mats:
        obj.data.materials.append(m)
    obj.data.polygons.foreach_set("material_index", mi)
    obj.data.update()
    return len(keep)


# ---------------------------------------------------------------------------------------------------------------

def load_part(path, tex):
    """Import one source file into the open scene; its materials wired, its meshes joined into one new object."""
    before = set(bpy.data.objects)
    if path.endswith((".usd", ".usda", ".usdc")):
        bpy.ops.wm.usd_import(filepath=path, import_materials=True)
        specs = usd_material_specs(path)
    else:
        bpy.ops.import_scene.gltf(filepath=path)
        specs = {}
    drop_proxies(before)
    new = [o for o in bpy.data.objects if o not in before]
    objects = [o for o in new if o.type == "MESH"]
    src_tris = sum(tri_count(o) for o in objects)
    cache = {}
    if specs:
        names = {sl.material.name for o in objects for sl in o.material_slots if sl.material}
        for name in sorted(names):
            spec = specs.get(name) or specs.get(re.sub(r"\.\d{3}$", "", name))
            if spec is not None:
                build_material(name, spec, tex, cache, objects)
    obj = join_objects(new)
    return obj, src_tris


def join_objects(objs):
    names = [o.name for o in objs]
    meshes = [o for o in objs if o.type == "MESH"]
    if not meshes:
        raise SystemExit("no mesh in the part")
    for o in bpy.data.objects:
        o.select_set(False)
    for o in meshes:
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    bpy.context.view_layer.objects.active = meshes[0]
    for o in meshes:
        o.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    for name in names:
        o = bpy.data.objects.get(name)
        if o is not None and o is not obj:
            bpy.data.objects.remove(o, do_unlink=True)
    return obj


def convert(recipe, asset_id, out_dir):
    row = recipe["assets"][asset_id]
    source = recipe["sources"][row["source"]]
    root = os.path.expandvars(source["root"])
    tex = row.get("tex", recipe["defaults"]["tex"])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if row.get("compose"):
        # Built from parts (a stack of pallets, boxes on a pallet): each part file once, normalised to its own pivot
        # (footprint middle, ground), then copies at the recipe's offsets (metres) and yaws.
        parts, src_tris, placed = {}, 0, []
        for spec in row["compose"]:
            if spec["path"] not in parts:
                part, tris = load_part(os.path.join(root, spec["path"]), tex)
                place(part, 0.0, spec.get("size"))
                part.hide_set(True)
                parts[spec["path"]] = part
                src_tris += tris
            copy = parts[spec["path"]].copy()
            copy.data = parts[spec["path"]].data.copy()
            bpy.context.scene.collection.objects.link(copy)
            copy.hide_set(False)
            copy.rotation_euler = (0.0, 0.0, math.radians(spec.get("yaw", 0.0)))
            copy.location = spec.get("at", (0.0, 0.0, 0.0))
            placed.append(copy)
        for part in parts.values():
            bpy.data.objects.remove(part, do_unlink=True)
        bpy.context.view_layer.update()
        obj = join_objects(placed)
    else:
        obj, src_tris = load_part(os.path.join(root, row["path"]), tex)
    for o in list(bpy.data.objects):
        if o is not obj:
            bpy.data.objects.remove(o, do_unlink=True)
    obj.name = "Asset"
    place(obj, row.get("yaw_deg", 0.0), row.get("size"), row.get("dims"))
    tris = decimate(obj, row.get("tris", recipe["defaults"]["tris"]))
    shrink_images(row.get("tex", recipe["defaults"]["tex"]))
    for img in list(bpy.data.images):
        if img.users == 0:
            bpy.data.images.remove(img)
    slots = merge_materials(obj)
    mn, mx = bounds(obj)
    licence = recipe["licences"][source["licence"]]
    stamp = {"pack": recipe["pack"], "third_party": True, "asset": asset_id, "source": source["name"],
             "source_path": row["path"], "licence": licence["id"], "credit": licence["credit"]}
    bpy.context.scene["bt_userpack"] = json.dumps(stamp, sort_keys=True)
    os.makedirs(out_dir, exist_ok=True)
    glb = os.path.join(out_dir, "SM_UP_%s.glb" % asset_id)
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=False, export_extras=True,
                              export_copyright=licence["credit"], export_yup=True, export_apply=True,
                              export_image_format="AUTO", export_texcoords=True, export_normals=True,
                              export_materials="EXPORT", export_animations=False, export_skins=False,
                              export_morph=False, export_cameras=False, export_lights=False)
    textures = sorted({(i.name, tuple(i.size)) for i in bpy.data.images if i.size[0] and i.users})
    stats = {"asset": asset_id, "slot": row["slot"], "glb": glb, "source": source["name"], "source_path": row["path"],
             "licence": licence["id"], "credit": licence["credit"], "source_tris": src_tris, "tris": tris,
             "materials": slots, "textures": [[n, list(s)] for n, s in textures],
             "tex_max_px": max([max(s) for _n, s in textures] or [0]),
             "size_m": [round(float(b - a), 3) for a, b in zip(mn, mx)], "bytes": os.path.getsize(glb)}
    with open(os.path.join(out_dir, "SM_UP_%s.json" % asset_id), "w") as fh:
        json.dump(stats, fh, indent=1, sort_keys=True)
    log("done", asset_id, "tris", src_tris, "->", tris, "size", stats["size_m"], "tex", stats["tex_max_px"],
        "mats", slots)
    return stats


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:]
    recipe = json.load(open(argv[0]))
    ids = argv[1].split(",") if argv[1] != "all" else sorted(recipe["assets"])
    failed = []
    for aid in ids:
        try:
            convert(recipe, aid, argv[2])
        except Exception as exc:  # noqa: BLE001  one bad asset must not stop the rebuild; the slot falls back
            import traceback
            traceback.print_exc()
            log("FAILED", aid, exc)
            failed.append(aid)
    log("finished", len(ids) - len(failed), "ok", "failed:", ",".join(failed) or "none")
