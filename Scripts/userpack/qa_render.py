"""Look at converted pack GLBs before they go near Unreal (Blender headless, `-t 2`).

  Blender -b -t 2 --python Scripts/userpack/qa_render.py -- <glb dir> <out dir> [name,name,...]

Per GLB: a "front" view from +X (the pack frame's front: a car's nose, a forklift's forks, a person's face must show
here), a three-quarter street view at eye height (1.6 m), and a 1.8 m scale post beside the asset (a person's height),
on a grey ground under a sun. Writes <out>/<name>_front.png and <name>_street.png.
"""
import math
import os
import sys

import bpy
import mathutils


def setup_scene():
    sc = bpy.context.scene
    try:
        sc.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 640, 480
    world = bpy.data.worlds.new("w")
    sc.world = world
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.6, 0.68, 0.8, 1.0)
    bg.inputs["Strength"].default_value = 0.9
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 4.0
    sun.rotation_euler = (math.radians(45), 0.0, math.radians(30))
    sc.collection.objects.link(sun)
    bpy.ops.mesh.primitive_plane_add(size=400)
    ground = bpy.context.object
    mat = bpy.data.materials.new("ground")
    mat.use_nodes = True
    next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"].default_value = \
        (0.3, 0.3, 0.29, 1.0)
    ground.data.materials.append(mat)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    return cam


def bounds():
    mn = mathutils.Vector((1e9,) * 3)
    mx = mathutils.Vector((-1e9,) * 3)
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name not in ("Plane", "post"):
            for c in o.bound_box:
                w = o.matrix_world @ mathutils.Vector(c)
                mn = mathutils.Vector(map(min, mn, w))
                mx = mathutils.Vector(map(max, mx, w))
    return mn, mx


def shoot(cam, path, eye, target, lens=40):
    cam.data.lens = lens
    cam.location = eye
    cam.rotation_euler = (mathutils.Vector(target) - mathutils.Vector(eye)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    src, out = argv[0], argv[1]
    names = argv[2].split(",") if len(argv) > 2 else None
    os.makedirs(out, exist_ok=True)
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".glb"):
            continue
        name = fn[:-4]
        if names and name not in names and name.replace("SM_UP_", "") not in names:
            continue
        bpy.ops.wm.read_factory_settings(use_empty=True)
        cam = setup_scene()
        bpy.ops.import_scene.gltf(filepath=os.path.join(src, fn))
        mn, mx = bounds()
        size = max(mx - mn)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=1.8, location=(0.0, mx.y + 0.4, 0.9))
        bpy.context.object.name = "post"
        mid_z = (mn.z + mx.z) / 2.0
        d = max(size * 1.6, 2.5)
        shoot(cam, os.path.join(out, name + "_front.png"), (d + mx.x, 0.0, max(1.6, mid_z)), (0.0, 0.0, mid_z))
        shoot(cam, os.path.join(out, name + "_street.png"), (d * 0.9, -d * 0.9, 1.6), (0.0, 0.0, mid_z * 0.8))


main()
