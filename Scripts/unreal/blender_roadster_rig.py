"""Split Kenny's rigged Roadster (roadster_rig.glb, a node rig, no skin) into one GLB per moving part for Unreal,
each with its pivot at the origin and the car facing +X (Blender), so Unreal's glTF import gives X forward, Y right
(the car's left = -Y), Z up, centimetres. The C++ (SkysterCar) puts each part back at its pivot and animates it
the way Skyster's js/car.js does.

GLB frame: +Y up, +Z forward, +X = the car's left, metres. Here (after Blender's import, then +90 deg about Z):
(x, y, z) = (gz, gx, gy); Unreal cm = (gz, -gx, gy) * 100.

Parts: RR_Body (everything static, lamp lenses included: the C++ drives their glow), RR_FrontWing, RR_SpoilerPush
(actuator rods), RR_Spoiler, RR_HeadlightPanel_L/R, RR_Baffle_L/R, RR_Wheel_FL/FR/RL/RR. (The thruster plume mesh,
SC_JetCone, is made by Scripts/unreal/blender_fx_kit.py.)
Run: /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/unreal/blender_roadster_rig.py
Output: SourceArt/RoadsterRig/<part>.glb and pivots.json
"""
import json, math, os
import bpy
from mathutils import Matrix, Vector

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


ROOT = _skycity_root()
# the rigged GLB (from Skyster's rig export) and Skyster's assets/rig_meta.json: set SKYCITY_ROADSTER_RIG / SKYSTER_ROOT
SRC = os.environ.get("SKYCITY_ROADSTER_RIG", os.path.expanduser("~/Downloads/roadster_rig.glb"))
OUT = os.path.join(ROOT, "SourceArt", "RoadsterRig")
os.makedirs(OUT, exist_ok=True)
META = json.load(open(os.path.join(os.environ.get("SKYSTER_ROOT", os.path.expanduser("~/skyster")), "assets", "rig_meta.json")))
ROT = Matrix.Rotation(math.radians(90), 4, "Z")


def g2b(p):
    """glTF point -> this script's Blender frame."""
    return Vector((p[2], p[0], p[1]))


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
meshes = [o for o in bpy.data.objects if o.type == "MESH"]


def under(name):
    """Mesh objects at or below the node called `name`."""
    root = bpy.data.objects.get(name)
    out = []
    for o in meshes:
        p = o
        while p is not None:
            if p == root:
                out.append(o)
                break
            p = p.parent
    return out


wheel_c = {w: META[f"Wheel_{w}"]["centre"] for w in ("FL", "FR", "RL", "RR")}
PARTS = {
    "RR_FrontWing": (under("Front_wing"), META["Front_wing"]["pivot"]),
    "RR_Spoiler": (under("Tail_spoiler"), META["Tail_spoiler"]["pivot"]),
    "RR_SpoilerPush": ([o for o in meshes if o.name.endswith("__rod")], [0, 0, 0]),
    "RR_HeadlightPanel_L": (under("Headlight_panel_L"), META["Headlight_panel_L"]["pivot"]),
    "RR_HeadlightPanel_R": (under("Headlight_panel_R"), META["Headlight_panel_R"]["pivot"]),
    "RR_Baffle_L": (under("Baffle_L"), [0, 0, 0]),
    "RR_Baffle_R": (under("Baffle_R"), [0, 0, 0]),
}
for w in ("FL", "FR", "RL", "RR"):
    PARTS[f"RR_Wheel_{w}"] = (under(f"Wheel_{w}_spin"), wheel_c[w])
taken = {o for objs, _ in PARTS.values() for o in objs}
PARTS["RR_Body"] = ([o for o in meshes if o not in taken], [0, 0, 0])


def export_part(name, objs, pivot_g):
    """Bake world transforms (plus the +90 deg turn), move the pivot to the origin, join and export."""
    piv = g2b(pivot_g)
    bpy.ops.object.select_all(action="DESELECT")
    dups = []
    for o in objs:
        d = o.copy()
        d.data = o.data.copy()
        bpy.context.collection.objects.link(d)
        d.parent = None
        d.data.transform(ROT @ o.matrix_world)
        d.matrix_world = Matrix.Identity(4)
        d.data.transform(Matrix.Translation(-piv))
        dups.append(d)
    for d in dups:
        d.select_set(True)
    bpy.context.view_layer.objects.active = dups[0]
    if len(dups) > 1:
        bpy.ops.object.join()
    j = bpy.context.view_layer.objects.active
    j.name = name
    j.data.name = name
    bpy.ops.export_scene.gltf(filepath=f"{OUT}/{name}.glb", export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_texcoords=True, export_normals=True, export_materials="EXPORT")
    bpy.ops.object.delete()
    print("exported", name, len(objs), "pieces")


pivots = {}
for name, (objs, pivot_g) in PARTS.items():
    if not objs:
        print("MISSING", name)
        continue
    export_part(name, objs, pivot_g)
    b = g2b(pivot_g)
    pivots[name] = [round(b.x * 100, 3), round(-b.y * 100, 3), round(b.z * 100, 3)]   # Unreal cm, car frame

# the thruster plume mesh SC_JetCone comes from Scripts/unreal/blender_fx_kit.py
json.dump(pivots, open(f"{OUT}/pivots.json", "w"), indent=1)
print("RIG DONE", json.dumps(pivots))
