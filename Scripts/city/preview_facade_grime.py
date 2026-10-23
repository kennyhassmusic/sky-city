"""Cheap preview of the procedural facade grime. Not part of the city build.

Two walls share one brick material. The left wear is brand-new (near zero).
The right wear is distressed. A sill lip and a small AC box sit in the drip
band. Cycles, a few samples. The grimy wall has to come out darker, and the
joined mesh has to keep both wear values.

Run:
  blender --background --factory-startup --python-exit-code 1 -P Scripts/city/preview_facade_grime.py
"""
import math
import os
import sys

import bpy
from mathutils import Matrix

CITY = os.path.dirname(os.path.abspath(__file__))
if CITY not in sys.path:
    sys.path.insert(0, CITY)

import blender_city as city  # noqa: E402  (installs the 5.2 fail-hard checks)
import blender_block as bb  # noqa: E402
import facade_grime  # noqa: E402


def main():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    record = bb.load_material_record()
    lib = bb.make_library(record)
    brick = lib["brick"]
    city._assert_tree(brick.node_tree, "M_Brick")
    _assert_shader(brick)
    if bpy.data.materials.get("M_Streak") is not None:
        city._die("M_Streak leak card is still in the library")

    clean_wear = facade_grime.intensity({"district_type": "brand_new"})
    heavy_wear = facade_grime.intensity({"tier": "distressed"})
    col = bb.collection("GrimePreview")
    clean = _wall("Clean", -4.2, clean_wear, brick, col)
    heavy = _wall("Heavy", 1.0, heavy_wear, brick, col)
    _expect_wear(clean, clean_wear)
    _expect_wear(heavy, heavy_wear)

    joined = city._join_evaluated([clean, heavy], Matrix.Identity(4))
    colors = _wear_values(joined.data)
    if not any(abs(value - clean_wear) < 0.02 for value in colors):
        city._die("joined mesh lost the clean wear: %s" % colors[:8])
    if not any(abs(value - heavy_wear) < 0.02 for value in colors):
        city._die("joined mesh lost the distressed wear: %s" % colors[:8])
    print("JOIN WEAR", round(min(colors), 3), round(max(colors), 3), flush=True)
    joined.hide_render = True

    scene = bpy.context.scene
    _camera(scene)
    _sun()
    _world(scene)
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = False
    scene.cycles.device = "CPU"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 360
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "Standard"
    except TypeError:
        pass
    root = os.environ.get("SKYCITY_ROOT") or os.path.dirname(os.path.dirname(CITY))
    dest_dir = os.path.join(root, "artifacts", "previews")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, "facade_grime.png")
    scene.render.filepath = dest
    bpy.ops.render.render(write_still=True)
    clean_base, clean_glass, heavy_base, heavy_glass = _bands(dest)
    print(
        "GRIME LUMA base", round(clean_base, 4), round(heavy_base, 4),
        "glass", round(clean_glass, 4), round(heavy_glass, 4),
        flush=True,
    )
    if heavy_base > clean_base - 0.06:
        city._die(
            "distressed base is not darker than brand-new (%s vs %s)"
            % (round(heavy_base, 4), round(clean_base, 4))
        )
    if heavy_base > heavy_glass - 0.04:
        city._die(
            "distressed dirt is not gathering at the base (%s vs glass %s)"
            % (round(heavy_base, 4), round(heavy_glass, 4))
        )
    if abs(heavy_glass - clean_glass) > 0.05:
        city._die(
            "the glass band should stay near the scan on both walls (%s vs %s)"
            % (round(heavy_glass, 4), round(clean_glass, 4))
        )
    extra = os.environ.get("SKYCITY_GRIME_COPY")
    if extra:
        import shutil
        os.makedirs(extra, exist_ok=True)
        shutil.copy2(dest, os.path.join(extra, "facade_grime.png"))
    print("GRIME PREVIEW", dest, flush=True)


def _assert_shader(mat):
    nodes = mat.node_tree.nodes
    if not any(node.bl_idname == "ShaderNodeVertexColor" for node in nodes):
        city._die("facade shader does not read vertex colour")
    if not any(node.bl_idname == "ShaderNodeAmbientOcclusion" for node in nodes):
        city._die("facade shader has no ambient-occlusion mask")
    if not any(node.bl_idname == "ShaderNodeBevel" for node in nodes):
        city._die("facade shader has no curvature bevel")
    images = []
    for node in nodes:
        if node.bl_idname == "ShaderNodeTexImage" and getattr(node, "image", None) is not None:
            images.append(node.image.name.lower())
    if any("leak" in name or "cracked_concrete" in name for name in images):
        city._die("facade shader still samples a stain photo: %s" % images)


def _wall(name, x, wear, mat, col):
    """The sill, the AC unit and the pier face the camera, so drips and corner dirt have something to catch."""
    mesh = bb.Mesh(name)
    mesh.grime = wear
    face = -0.14
    depth = 0.28
    mesh.prism(
        [(x, face), (x + 3.2, face), (x + 3.2, face + depth), (x, face + depth)],
        0.15, 0.15 + facade_grime.FLOOR_H, mat,
    )
    sill = 0.15 + facade_grime.SILL_PEAK * facade_grime.FLOOR_H
    lip = 0.16
    mesh.prism(
        [(x + 0.4, face - lip), (x + 2.8, face - lip), (x + 2.8, face), (x + 0.4, face)],
        sill, sill + 0.08, mat,
    )
    mesh.box(
        (x + 2.15, face - lip * 0.55, sill - 0.22),
        (1, 0, 0), (0, 1, 0), (0, 0, 1),
        (0.64, lip + 0.06, 0.28),
        mat,
    )
    mesh.box(
        (x + 0.12, face - 0.02, 0.15 + facade_grime.FLOOR_H * 0.5),
        (1, 0, 0), (0, 1, 0), (0, 0, 1),
        (0.22, 0.22, facade_grime.FLOOR_H),
        mat,
    )
    return mesh.finish(col)


def _expect_wear(ob, wear):
    values = _wear_values(ob.data)
    if not values or any(abs(value - wear) > 0.02 for value in values):
        city._die("%s wear painted %s, expected %s" % (ob.name, values[:4], wear))


def _wear_values(mesh):
    attr = mesh.color_attributes.get("Col")
    if attr is None:
        return []
    return [float(item.color[0]) for item in attr.data]


def _camera(scene):
    data = bpy.data.cameras.new("GrimeCam")
    data.type = "ORTHO"
    data.ortho_scale = 9.2
    cam = bpy.data.objects.new("GrimeCam", data)
    scene.collection.objects.link(cam)
    cam.location = (0.0, -8.0, 1.9)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.camera = cam


def _sun():
    data = bpy.data.lights.new("Sun", "SUN")
    data.energy = 3.5
    data.angle = math.radians(8)
    ob = bpy.data.objects.new("Sun", data)
    bpy.context.scene.collection.objects.link(ob)
    ob.rotation_euler = (math.radians(50), 0.0, math.radians(15))


def _world(scene):
    world = bpy.data.worlds.new("GrimeWorld")
    scene.world = world
    tree = world.node_tree
    if tree is None:
        world.color = (0.62, 0.66, 0.70)
        return
    bg = tree.nodes.get("Background")
    if bg is not None and "Color" in bg.inputs:
        bg.inputs["Color"].default_value = (0.62, 0.66, 0.70, 1.0)
        bg.inputs["Strength"].default_value = 0.55


def _bands(path):
    """Base and glass luminance for each wall. The backdrop is the corner pixel.

    Blender stores the render bottom-up, so the low rows are the sidewalk.
    The glass band is the open middle of the floor, between the sill drip
    and the ledge drip.
    """
    image = bpy.data.images.load(path)
    width, height = image.size
    pixels = list(image.pixels)
    bpy.data.images.remove(image)
    backdrop = (pixels[0], pixels[1], pixels[2])

    def wall(i):
        return (
            abs(pixels[i] - backdrop[0])
            + abs(pixels[i + 1] - backdrop[1])
            + abs(pixels[i + 2] - backdrop[2])
        ) > 0.08

    def span(x0, x1):
        rows = []
        for y in range(height):
            for x in range(x0, x1):
                if wall((y * width + x) * 4):
                    rows.append(y)
                    break
        if len(rows) < 8:
            city._die("preview is missing a wall")
        return min(rows), max(rows)

    def mean(x0, x1, y0, y1):
        acc = []
        for y in range(y0, y1):
            for x in range(x0, x1):
                i = (y * width + x) * 4
                if not wall(i):
                    continue
                acc.append(0.2126 * pixels[i] + 0.7152 * pixels[i + 1] + 0.0722 * pixels[i + 2])
        if len(acc) < 30:
            city._die("preview band has no wall pixels")
        return sum(acc) / len(acc)

    def sample(x0, x1):
        y0, y1 = span(x0, x1)
        height_px = max(1, y1 - y0)
        base = mean(x0, x1, y0, y0 + int(height_px * 0.28))
        glass = mean(x0, x1, y0 + int(height_px * 0.48), y0 + int(height_px * 0.68))
        return base, glass

    mid = width // 2
    clean_base, clean_glass = sample(0, mid)
    heavy_base, heavy_glass = sample(mid, width)
    return clean_base, clean_glass, heavy_base, heavy_glass


if __name__ == "__main__":
    main()
