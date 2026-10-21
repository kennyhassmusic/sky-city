"""Render a preview line-up of the street kit (headless Blender, Cycles), with leaf and sign textures.
Run: Blender -b --factory-startup -P Scripts/streets/blender_preview_kit.py -- <out.png>"""
import math, sys
import bpy
from mathutils import Vector

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
    raise RuntimeError("Cannot find the SkyCity project folder (SkyCity.uproject): set SKYCITY_ROOT")


ROOT = os.path.join(_skycity_root(), "SourceArt", "StreetKit")
OUTP = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
row = ["SK_Tree_liveoak", "SK_Tree_honeylocust", "SK_Tree_linden", "SK_Tree_elm", "SK_Lamp_Street", "SK_Signal_10m",
       "SK_StopSign", "SK_SpeedSign", "SK_NamePost", "SK_NameBlade", "SK_Dumpster", "SK_BikeRack", "SK_Mailbox", "SK_BusShelter"]
x = 0.0
gap = {"SK_Tree_liveoak": 16, "SK_Tree_honeylocust": 12, "SK_Tree_linden": 10, "SK_Tree_elm": 13, "SK_Lamp_Street": 5, "SK_Signal_10m": 4,
       "SK_StopSign": 2, "SK_SpeedSign": 2, "SK_NamePost": 0, "SK_NameBlade": 3, "SK_Dumpster": 3, "SK_BikeRack": 2.5, "SK_Mailbox": 2.5, "SK_BusShelter": 5}
TEX = {"M_Leaves_liveoak": "T_Leaves_liveoak_C.png", "M_Leaves_honeylocust": "T_Leaves_honeylocust_C.png", "M_Leaves_linden": "T_Leaves_linden_C.png",
       "M_Leaves_elm": "T_Leaves_elm_C.png", "M_Bark": "T_Bark_C.png", "M_SignStop": "T_Sign_Stop.png", "M_SignSpeed": "T_Sign_Speed.png", "M_SignName": "T_Sign_Names.png"}
for name in row:
    bpy.ops.import_scene.gltf(filepath=f"{ROOT}/meshes/{name}.glb")
    for ob in bpy.context.selected_objects:
        ob.location.x += x
    x += gap[name]
for m in bpy.data.materials:
    base = m.name.split(".")[0]
    if base in TEX and m.use_nodes:
        nt = m.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        img = nt.nodes.new("ShaderNodeTexImage")
        img.image = bpy.data.images.load(f"{ROOT}/textures/{TEX[base]}")
        nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
        if base.startswith("M_Leaves"):
            nt.links.new(img.outputs["Alpha"], bsdf.inputs["Alpha"])
            m.blend_method = "CLIP" if hasattr(m, "blend_method") else None
    if base.startswith("M_Signal") or base == "M_LampLens":
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Emission Color"].default_value = bsdf.inputs["Base Color"].default_value
        bsdf.inputs["Emission Strength"].default_value = 4.0
# ground, sun, sky, camera
bpy.ops.mesh.primitive_plane_add(size=400, location=(x / 2, 0, 0))
g = bpy.data.materials.new("ground"); g.use_nodes = True
g.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.25, 0.25, 0.26, 1)
bpy.context.object.data.materials.append(g)
bpy.ops.object.light_add(type="SUN", rotation=(math.radians(50), 0, math.radians(30)))
bpy.context.object.data.energy = 4
w = bpy.data.worlds.new("w"); bpy.context.scene.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.68, 0.85, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
bpy.ops.object.camera_add(location=(x / 2 - 6, -55, 9), rotation=(math.radians(85), 0, 0))
cam = bpy.context.object
cam.data.lens = 28
bpy.context.scene.camera = cam
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = 24
sc.cycles.device = "CPU"
sc.render.resolution_x, sc.render.resolution_y = 1800, 560
sc.render.filepath = OUTP
bpy.ops.render.render(write_still=True)
print("rendered", OUTP)
