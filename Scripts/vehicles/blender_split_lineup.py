"""Kenny's McGregor lineup vehicles ($SKYCITY_LINEUP_SRC, default Saved/McGregorLineup; see its README and lineup_manifest.json) split
into a static body plus one mesh per wheel, each wheel's pivot at its centre, for the McGregor showcase and for
driving them with the Skyster physics (Source/SkyCity/SkysterCar: the car swaps its body and wheels).
Metres, front = +X, origin on the ground under the centre (as delivered). The glTF import keeps Blender X as
Unreal X and flips Y, so the cars arrive facing Unreal +X at true size.
Licences (README / CREDITS_AND_LICENCES.txt): never commit SourceArt/Vehicles to a public repo; Semi = editorial
placeholder; Model 3 licence uncertain; Model Y CC BY-NC (credit BloxBloger).
Body fixes (vehicle-models, 20 Oct 2026), applied to the body after the join, in the car frame (metres, x forward,
y left, z up): LAMPS turns modelled-but-unlit lamps into lamp faces (the Semi's main headlamps are recesses in its
silver paint; the delivered "Headlight" is only the thin light bar), BADGES deletes badge lettering the delivery missed
(Model Y: the chrome letters in the rear light bar and the trim badge on the tailgate), REMAT gives faces a plain
material (the Cybertruck's name plate), SOCKETS overrides lamp
sockets (night_ue.py aims the line-up's headlight spots from them). Wheels are untouched, so pivots stay identical.
Run: Blender -b --factory-startup -P Scripts/vehicles/blender_split_lineup.py [-- names]
  (SPLIT_OUT=/some/dir writes there instead, for a dry run)
Output: SourceArt/Vehicles/<Name>/TV_<Name>_Body.glb, TV_<Name>_<Wheel>.glb, parts.json"""
import json, math, os, sys
import bmesh
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
SRC = os.environ.get("SKYCITY_LINEUP_SRC", os.path.join(ROOT, "Saved", "McGregorLineup"))   # the licensed source files
OUT = os.environ.get("SPLIT_OUT", os.path.join(ROOT, "SourceArt", "Vehicles"))
MAN = json.load(open(f"{SRC}/lineup_manifest.json"))
ONLY = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
info = {}
KIND = {"Diffuse": "BaseColor", "Normal": "Normal", "Emissive": "Emissive"}
# (material to give, seed point, max bend in degrees): the faces reached from the face nearest the seed, over edges
# that bend less than the angle and within the seed face's material, get the lamp material (found with a ray pick
# and checked in renders: each Semi lamp is ~1120 faces, x 2.89-3.41 m, |y| 0.93-1.19 m, z 0.70-1.14 m)
LAMPS = {"Semi": [("Headlight", (3.1415, -1.047, 0.9156), 25.0), ("Headlight", (3.1415, 1.047, 0.9156), 25.0)]}
# (material, x0, x1, |y|0, |y|1, z0, z1): faces of that material with their centre in the box are deleted
BADGES = {"ModelY": [("chrome", -2.20, -2.14, 0.0, 0.30, 1.03, 1.08),       # lettering inside the rear light bar
                     ("chrome", -2.30, -2.24, 0.38, 0.56, 0.76, 0.82)]}     # trim badge, tailgate lower right
# (material, x0, x1, |y|0, |y|1, z0, z1, new material, colour): faces in the box get a plain new material
REMAT = {"Cybertruck": [("body_mat", -2.86, -2.80, 0.0, 0.25, 0.55, 0.71, "Plate", (0.92, 0.92, 0.9))]}   # a name plate
SOCKETS = {"Semi": {"Headlight_L": [3.38, 1.05, 0.93], "Headlight_R": [3.38, -1.05, 0.93]}}   # the main lamps, not the bar


def fix_body(name, o):
    """LAMPS, BADGES and REMAT for one vehicle's joined body object (transforms already applied)."""
    if name not in LAMPS and name not in BADGES and name not in REMAT:
        return
    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    mats = [m.name if m else "" for m in me.materials]

    def mat_index(nm):
        for i, m in enumerate(mats):
            if m == nm or m.split(".")[0] == nm:
                return i
        me.materials.append(bpy.data.materials.get(nm) or bpy.data.materials.new(nm))
        mats.append(nm)
        return len(mats) - 1
    for mat, seed, ang in LAMPS.get(name, []):
        s = Vector(seed)
        f0 = min(bm.faces, key=lambda f: (f.calc_center_median() - s).length_squared)
        src, dst = f0.material_index, mat_index(mat)
        seen, stack = {f0.index}, [f0]
        while stack:
            f = stack.pop()
            for e in f.edges:
                for g in e.link_faces:
                    if g.index not in seen and g.material_index == src and f.normal.angle(g.normal, 0) <= math.radians(ang):
                        seen.add(g.index)
                        stack.append(g)
        for i in seen:
            bm.faces[i].material_index = dst
        print(f"LAMP {name} {mat} from {mats[src]}: {len(seen)} faces at {tuple(round(c, 3) for c in s)}")
    for mat, x0, x1, y0, y1, z0, z1 in BADGES.get(name, []):
        mi = [i for i, m in enumerate(mats) if m == mat or m.split(".")[0] == mat]
        gone = [f for f in bm.faces if f.material_index in mi and x0 <= (c := f.calc_center_median()).x <= x1
                and y0 <= abs(c.y) <= y1 and z0 <= c.z <= z1]
        bmesh.ops.delete(bm, geom=gone, context="FACES")
        bm.faces.ensure_lookup_table()
        print(f"BADGE {name} {mat}: deleted {len(gone)} faces")
    for mat, x0, x1, y0, y1, z0, z1, new, col in REMAT.get(name, []):
        if new not in bpy.data.materials:
            nm = bpy.data.materials.new(new)
            nm.use_nodes = True
            b = next(n for n in nm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            b.inputs["Base Color"].default_value = (*col, 1.0)
            b.inputs["Roughness"].default_value = 0.4
        mi = [i for i, m in enumerate(mats) if m == mat or m.split(".")[0] == mat]
        dst = mat_index(new)
        hit = [f for f in bm.faces if f.material_index in mi and x0 <= (c := f.calc_center_median()).x <= x1
               and y0 <= abs(c.y) <= y1 and z0 <= c.z <= z1]
        for f in hit:
            f.material_index = dst
        print(f"REMAT {name} {mat} -> {new}: {len(hit)} faces")
    bm.to_mesh(me)
    bm.free()
    me.update()


def relink(name):
    """The Cybertruck .blend points at textures on the machine that made it; its Textures folder has the same maps as
    BaseColor / Normal / Emissive / OcclusionRoughnessMetallic PNGs. Point the nodes there (metal = B, rough = G of the
    ORM map, which the glTF exporter packs back into one metallicRoughness texture) so they embed in the GLB."""
    tex = f"{SRC}/{name}/Textures"
    if not os.path.isdir(tex):
        return
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        nt = m.node_tree
        for n in list(nt.nodes):
            if n.type != "TEX_IMAGE" or not n.image or os.path.exists(bpy.path.abspath(n.image.filepath)):
                continue
            stem, kind = os.path.splitext(os.path.basename(n.image.filepath))[0].rsplit("_", 1)
            if kind in KIND:
                f = f"{tex}/{stem}_{KIND[kind]}.png"
                if os.path.exists(f):
                    n.image = bpy.data.images.load(f, check_existing=True)
                    if kind == "Normal":
                        n.image.colorspace_settings.name = "Non-Color"
            elif kind in ("Metallic", "Roughness"):
                f = f"{tex}/{stem}_OcclusionRoughnessMetallic.png"
                if not os.path.exists(f):
                    continue
                n.image = bpy.data.images.load(f, check_existing=True)
                n.image.colorspace_settings.name = "Non-Color"
                sep = nt.nodes.new("ShaderNodeSeparateColor")
                for sock in [l.to_socket for l in n.outputs["Color"].links]:
                    nt.links.new(sep.outputs["Blue" if kind == "Metallic" else "Green"], sock)   # replaces the old link
                nt.links.new(n.outputs["Color"], sep.inputs["Color"])


for v in MAN["vehicles"]:
    name = v["name"]
    if name == "SemiTrailer" or (ONLY and name not in ONLY):
        continue
    bpy.ops.wm.open_mainfile(filepath=f"{SRC}/{name}/{name}_game.blend")
    od = f"{OUT}/{name}"
    relink(name)
    os.makedirs(od, exist_ok=True)
    wheels = {w["bone"]: w for w in v["wheels"]}
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    parts = {}
    for o in meshes:
        for m in list(o.modifiers):
            if m.type == "ARMATURE":
                o.modifiers.remove(m)
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    body = [o for o in meshes if o.name not in wheels]
    if len(body) > 1:                                      # the Cybertruck comes in pieces (body, paint, glass, lights...)
        bpy.ops.object.select_all(action="DESELECT")
        for o in body:
            o.select_set(True)
        bpy.context.view_layer.objects.active = body[0]
        bpy.ops.object.join()
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    for o in meshes:
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        if o.name not in wheels:
            fix_body(name, o)
        piv = Vector((0, 0, 0))
        if o.name in wheels:
            c = wheels[o.name]["centre"]
            piv = Vector(c)
            o.data.transform(Matrix.Translation(-piv))
        label = "Body" if o.name not in wheels else o.name
        fn = f"{od}/TV_{name}_{label}.glb"
        bpy.ops.export_scene.gltf(filepath=fn, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
                                  export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO")
        parts[label] = {"file": os.path.basename(fn), "pivot_m": [round(x, 4) for x in piv]}
        if o.name in wheels:
            parts[label].update({"radius": wheels[o.name]["radius"], "width": wheels[o.name]["width"], "steer": wheels[o.name]["steer"]})
        print("exported", fn)
    lights = json.loads(json.dumps(v.get("lights", {})))
    lights.setdefault("sockets", {}).update(SOCKETS.get(name, {}))
    info[name] = {"size_m": v["size_m"], "parts": parts, "paint": v.get("paint_material"), "lights": lights}
if ONLY and os.path.exists(f"{OUT}/parts.json"):                # a partial run keeps the other vehicles
    info = {**json.load(open(f"{OUT}/parts.json")), **info}
json.dump(info, open(f"{OUT}/parts.json", "w"), indent=1)
print("SPLIT DONE", list(info))
