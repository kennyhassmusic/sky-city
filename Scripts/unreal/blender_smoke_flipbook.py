"""A billowing smoke puff for the car's particles, simulated with Blender's own gas solver (Mantaflow) and rendered as an
8 x 8 flipbook: frame 0 is a tight, dense burst, frame 63 a wide, wispy cloud breaking up. The camera follows the cloud
so it fills about the same share of every frame (the C++ grows the sprite itself). Lit by a soft key from above and a
dim ambient, so the billows carry their own light and shade; Unreal's lighting tints it on top.
Run: /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/unreal/blender_smoke_flipbook.py
Output: frames in $TMPDIR/skysmoke/f_##.png (Scripts/unreal/make_fx_textures.py --smoke packs them into SourceArt/FX/T_SkySmoke.png)"""
import math, os, sys
import bpy
from mathutils import Vector

TMP = os.path.join(os.environ.get("TMPDIR", "/tmp"), "skysmoke")
os.makedirs(TMP, exist_ok=True)
FIRST, COUNT, RES = 4, 64, 256           # sim frames FIRST .. FIRST+COUNT-1, rendered at RES px
PREVIEW = "--preview" in sys.argv       # four frames, few samples, to judge the look
STEP = 1                                 # sim frames per flipbook frame
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.frame_start, sc.frame_end = 1, FIRST + COUNT * STEP

# domain: a 6 m cube, no buoyancy (the C++ moves the puffs), swirling and slowly dissolving
bpy.ops.mesh.primitive_cube_add(size=6, location=(0, 0, 0))
dom = bpy.context.object
dom.name = "Domain"
dm = dom.modifiers.new("Fluid", "FLUID")
dm.fluid_type = "DOMAIN"
ds = dm.domain_settings
ds.domain_type = "GAS"
ds.resolution_max = 96
ds.use_noise = True
ds.noise_scale = 2
ds.noise_strength = 2.0
ds.alpha = 0.0
ds.beta = 0.0
ds.vorticity = 0.6
ds.use_dissolve_smoke = True
ds.dissolve_speed = 110
ds.use_dissolve_smoke_log = True
ds.cache_type = "ALL"
ds.cache_directory = os.path.join(TMP, "cache")
ds.cache_frame_start = 1
ds.cache_frame_end = FIRST + COUNT * STEP
ds.use_adaptive_domain = False

# emitters: a cluster of lumpy blobs that burst outward for a few frames, at different strengths
import random
random.seed(5)
tex = bpy.data.textures.new("lumps", "CLOUDS")
tex.noise_scale = 0.2
for k, (pos, rad, vel) in enumerate((((0, 0, 0), 0.42, 1.2), ((0.35, 0.1, 0.25), 0.28, 1.7), ((-0.3, -0.1, 0.2), 0.3, 1.5),
                                      ((0.1, 0.2, -0.32), 0.26, 1.9), ((-0.15, 0.0, -0.25), 0.24, 1.0))):
    bpy.ops.mesh.primitive_ico_sphere_add(radius=rad, subdivisions=3, location=pos)
    em = bpy.context.object
    em.name = f"Burst{k}"
    disp = em.modifiers.new("Lumps", "DISPLACE")
    disp.texture = tex
    disp.strength = rad * 0.7
    fm = em.modifiers.new("Fluid", "FLUID")
    fm.fluid_type = "FLOW"
    fs = fm.flow_settings
    fs.flow_type = "SMOKE"
    fs.flow_behavior = "INFLOW"
    fs.flow_source = "MESH"
    fs.use_initial_velocity = True
    fs.velocity_random = 0.6
    fs.surface_distance = 0.5
    fs.volume_density = 1.0
    for f, d in ((1, 1.0), (3 + k % 2, 1.0), (4 + k % 2, 0.0)):
        fs.density = d
        fs.keyframe_insert("density", frame=f)
        fs.velocity_normal = vel if d else 0.0
        fs.keyframe_insert("velocity_normal", frame=f)
    em.hide_render = True

with bpy.context.temp_override(object=dom, active_object=dom, selected_objects=[dom]):
    bpy.ops.fluid.bake_all()
print("BAKED")

# smoke shader: white, mildly forward-scattering
mat = bpy.data.materials.new("Smoke")
mat.use_nodes = True
nt = mat.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
out = nt.nodes.new("ShaderNodeOutputMaterial")
pv = nt.nodes.new("ShaderNodeVolumePrincipled")
pv.inputs["Color"].default_value = (1, 1, 1, 1)
pv.inputs["Density"].default_value = 9.0
pv.inputs["Anisotropy"].default_value = 0.25
nt.links.new(pv.outputs["Volume"], out.inputs["Volume"])
dom.data.materials.append(mat)

# light: soft key from above and in front, dim grey ambient
bpy.ops.object.light_add(type="SUN", location=(0, -5, 5))
sun = bpy.context.object
sun.data.energy = 9.0
sun.data.angle = math.radians(12)
sun.rotation_euler = (math.radians(40), 0, math.radians(-20))
world = bpy.data.worlds.new("W")
sc.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.52, 0.55, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.1

# camera: orthographic, looking along +Y at the cloud
bpy.ops.object.camera_add(location=(0, -10, 0), rotation=(math.radians(90), 0, 0))
cam = bpy.context.object
cam.data.type = "ORTHO"
sc.camera = cam

r = sc.render
r.engine = "CYCLES"
r.resolution_x = r.resolution_y = RES
r.film_transparent = True
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGBA"
sc.view_settings.view_transform = "Standard"
sc.cycles.samples = 64
sc.cycles.use_denoising = True
sc.cycles.volume_step_rate = 1.0
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    sc.cycles.device = "GPU"
except Exception as e:
    print("GPU unavailable, CPU render:", e)


def bounds():
    """The cloud's extent in the camera plane (x, z), from the density grid."""
    import numpy as np
    ev = dom.evaluated_get(bpy.context.evaluated_depsgraph_get()).modifiers["Fluid"].domain_settings
    g = np.array(ev.density_grid[:], dtype=np.float32)
    res = round(len(g) ** (1 / 3))
    if res ** 3 != len(g):
        return None
    d = g.reshape(res, res, res) > 0.02          # [z][y][x]
    xs, zs = np.where(d.any(axis=1).T)[0], np.where(d.any(axis=(1, 2)))[0]
    if not len(xs) or not len(zs):
        return None
    to_m = lambda i: (i + 0.5) / res * 6.0 - 3.0
    return to_m(xs.min()), to_m(xs.max()), to_m(zs.min()), to_m(zs.max())


scale, centre = None, Vector((0, 0))
frames = [0, 16, 40, 63] if PREVIEW else list(range(COUNT))
if PREVIEW:
    sc.cycles.samples = 16
for i in frames:
    f = FIRST + i * STEP
    sc.frame_set(f)
    b = bounds()
    if i == frames[0]:
        print("BOUNDS", b)
    if b:
        want = max(b[1] - b[0], b[3] - b[2]) / 0.86
        c = Vector(((b[0] + b[1]) / 2, (b[2] + b[3]) / 2))
        scale = want if scale is None else max(scale * 0.97, 0.7 * scale + 0.3 * want)   # never shrink fast
        centre = c if i == 0 else centre.lerp(c, 0.3)
    cam.data.ortho_scale = max(scale or 2.0, 1.0)
    cam.location = (centre.x, -10, centre.y)
    r.filepath = os.path.join(TMP, f"f_{i:02d}.png")
    bpy.ops.render.render(write_still=True)
    print("FRAME", i, round(cam.data.ortho_scale, 2), flush=True)
print("FLIPBOOK DONE", TMP)
