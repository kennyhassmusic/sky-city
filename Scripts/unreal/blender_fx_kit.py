"""The thruster plume mesh (SC_JetCone) for the car's jets: an open, ogive-shaped plume rather than a straight cone,
so the gas swells past the nozzle and closes softly where the material has faded it out.
Frame: nozzle at the origin, 1 m long toward -X (Blender), base radius 0.09 m; UV U runs round it, V from 0 at the
nozzle to 1 at the tip (the material scrolls its turbulence along V). The C++ scales X for length, Y/Z for width.
Run: /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/unreal/blender_fx_kit.py
Output: SourceArt/RoadsterRig/SC_JetCone.glb"""
import math, os
import bmesh, bpy



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


OUT = os.path.join(_skycity_root(), "SourceArt", "RoadsterRig")
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)

R0, SEG = 0.09, 24
RINGS = [0.0, 0.03, 0.08, 0.15, 0.24, 0.35, 0.48, 0.62, 0.76, 0.88, 0.96, 1.0]


def radius(v):
    """Swells to about one and a half times the nozzle by mid-length, then closes; the tip is a point."""
    return R0 * (1 + 0.6 * v ** 0.75) * max(0.0, 1 - v ** 6) ** 0.5


bm = bmesh.new()
uv = bm.loops.layers.uv.new()
grid = []
for v in RINGS:
    r = radius(v)
    grid.append([bm.verts.new((-v, r * math.cos(2 * math.pi * i / SEG), r * math.sin(2 * math.pi * i / SEG))) for i in range(SEG + 1)])
for j in range(len(RINGS) - 1):
    for i in range(SEG):
        a, b, c, d = grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]
        if j == len(RINGS) - 2:
            f = bm.faces.new((a, b, d))                     # the last ring is a point: triangles
            uvs = ((i / SEG, RINGS[j]), ((i + 1) / SEG, RINGS[j]), ((i + 0.5) / SEG, 1.0))
        else:
            f = bm.faces.new((a, b, c, d))
            uvs = ((i / SEG, RINGS[j]), ((i + 1) / SEG, RINGS[j]), ((i + 1) / SEG, RINGS[j + 1]), (i / SEG, RINGS[j + 1]))
        for loop, t in zip(f.loops, uvs):
            loop[uv].uv = t
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)       # the tip and the UV seam (UVs stay per loop)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
for f in bm.faces:                                          # outward normals (the plume is open at the nozzle)
    c = f.calc_center_median()
    if f.normal.dot((0, c.y, c.z)) < 0:
        f.normal_flip()
me = bpy.data.meshes.new("SC_JetCone")
bm.to_mesh(me)
for p in me.polygons:
    p.use_smooth = True
me.materials.append(bpy.data.materials.new("M_Jet"))
ob = bpy.data.objects.new("SC_JetCone", me)
bpy.context.collection.objects.link(ob)
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.export_scene.gltf(filepath=f"{OUT}/SC_JetCone.glb", export_format="GLB", use_selection=True, export_yup=True,
                          export_normals=True, export_texcoords=True, export_materials="EXPORT")
print("PLUME DONE", len(me.vertices), "verts")
