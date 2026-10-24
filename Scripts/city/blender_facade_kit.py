"""Build the facade kit: the small modules import_city_ue.py --buildings kit instances.

Seven GLBs in SourceArt/CityGen/kit (KIT_Wall, KIT_Pier, KIT_Corner, KIT_Pane,
KIT_PaneCurtain, KIT_Leaf, KIT_RoofCap). Sizes and depths are the mesher's
(kit_layout.py holds them, and kit_layout places the modules exactly where
blender_city._fitted_facade puts its spans, piers and panes). Every module is
1 m long and 1 m tall and is scaled per instance in Unreal.

Frame: Unreal gets local X = Blender X, local Y = -Blender Y, Z = Z (the same
mapping the city GLBs go through). Local +Y in Unreal is "into the building",
so here the depth runs along Blender -Y. Faces are wound so their normals
face the way given, not left to a recalculation.

Material slots (names are what Unreal binds): M_Wall (walls, piers, corners,
roof slab and parapets take the wall or trim material per HISM), M_Glass,
M_PaneBack (lit or dark room), M_Frame (frames, sills, reveals), M_Leaf
(blind or curtain), M_Coping.

Run (Blender 5.2.x, headless):
  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup \\
    --python-exit-code 1 -P Scripts/city/blender_facade_kit.py
"""
import math
import os
import sys

import bmesh
import bpy

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import kit_layout as kit  # noqa: E402


def _root():
    env = os.environ.get("SKYCITY_ROOT")
    if env:
        return env
    d = _HERE
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "SkyCity.uproject")):
            return d
        d = os.path.dirname(d)
    raise SystemExit("SkyCity.uproject not found")


OUT = os.environ.get("SKYCITY_KIT_OUT") or os.path.join(_root(), "SourceArt", "CityGen", "kit")
FRAME_W = 0.035      # frame strip, in the pane's unit square
SILL_H = 0.035
SILL_OUT = 0.05      # sill stands this far proud of the wall plane (metres)
COPING_H = 0.08
COPING_OUT = 0.04


class Kit(object):
    """One module. Points are given as (along, depth, up): depth > 0 is into the building."""

    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.slots = []

    def quad(self, pts, normal, slot):
        """pts in (along, depth, up). normal in the same frame. UV: the face's own two axes, 0..1."""
        verts = [(p[0], -p[1], p[2]) for p in pts]
        n = (normal[0], -normal[1], normal[2])
        a, b, c = verts[0], verts[1], verts[2]
        e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        cross = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        if cross[0] * n[0] + cross[1] * n[1] + cross[2] * n[2] < 0:
            verts.reverse()
            pts = list(reversed(pts))
        face = self.bm.faces.new([self.bm.verts.new(v) for v in verts])
        if slot not in self.slots:
            self.slots.append(slot)
        face.material_index = self.slots.index(slot)
        for loop, p in zip(face.loops, pts):
            # Planar UV from the two axes the face spans.
            if abs(normal[0]) > 0.5:
                loop[self.uv].uv = (p[1], p[2])
            elif abs(normal[2]) > 0.5:
                loop[self.uv].uv = (p[0], p[1])
            else:
                loop[self.uv].uv = (p[0], p[2])

    def box(self, a0, a1, d0, d1, z0, z1, slot, skip=()):
        """Axis box; faces named front (depth d0), back, left, right, bottom, top."""
        faces = {
            "front": ([(a0, d0, z0), (a1, d0, z0), (a1, d0, z1), (a0, d0, z1)], (0, -1, 0)),
            "back": ([(a0, d1, z0), (a1, d1, z0), (a1, d1, z1), (a0, d1, z1)], (0, 1, 0)),
            "left": ([(a0, d0, z0), (a0, d1, z0), (a0, d1, z1), (a0, d0, z1)], (-1, 0, 0)),
            "right": ([(a1, d0, z0), (a1, d1, z0), (a1, d1, z1), (a1, d0, z1)], (1, 0, 0)),
            "bottom": ([(a0, d0, z0), (a1, d0, z0), (a1, d1, z0), (a0, d1, z0)], (0, 0, -1)),
            "top": ([(a0, d0, z1), (a1, d0, z1), (a1, d1, z1), (a0, d1, z1)], (0, 0, 1)),
        }
        for name, (pts, normal) in faces.items():
            if name not in skip:
                self.quad(pts, normal, slot)

    def finish(self):
        mesh = bpy.data.meshes.new(self.name)
        bmesh.ops.remove_doubles(self.bm, verts=list(self.bm.verts), dist=1e-5)
        self.bm.to_mesh(mesh)
        self.bm.free()
        for slot in self.slots:
            mat = bpy.data.materials.get(slot) or bpy.data.materials.new(slot)
            mesh.materials.append(mat)
        ob = bpy.data.objects.new(self.name, mesh)
        bpy.context.scene.collection.objects.link(ob)
        return ob


def wall():
    k = Kit("KIT_Wall")
    # Spans, the roof slab and collision: the back is never seen.
    k.box(0, 1, 0, 1, 0, 1, "M_Wall", skip=("back",))
    return k.finish()


def pier():
    k = Kit("KIT_Pier")
    # Between two panes: the front and the two reveals. Floors stack, so no top or bottom.
    k.box(0, 1, 0, kit.PIER_DEPTH, 0, 1, "M_Wall", skip=("back", "top", "bottom"))
    return k.finish()


def corner():
    k = Kit("KIT_Corner")
    # End pilaster, a little proud of the wall so the corner reads.
    k.box(0, 1, -kit.CORNER_PROUD, kit.PIER_DEPTH, 0, 1, "M_Wall", skip=("back",))
    return k.finish()


def pane(name, sill):
    k = Kit(name)
    g, back = kit.PANE_GLASS_IN, kit.PANE_BACK_IN
    k.quad([(0, g, 0), (1, g, 0), (1, g, 1), (0, g, 1)], (0, -1, 0), "M_Glass")
    k.quad([(0, back, 0), (1, back, 0), (1, back, 1), (0, back, 1)], (0, -1, 0), "M_PaneBack")
    # Reveals: seal the opening between the wall plane and the back panel.
    k.quad([(0, 0, 0), (0, back, 0), (0, back, 1), (0, 0, 1)], (1, 0, 0), "M_Frame")
    k.quad([(1, 0, 0), (1, back, 0), (1, back, 1), (1, 0, 1)], (-1, 0, 0), "M_Frame")
    k.quad([(0, 0, 1), (1, 0, 1), (1, back, 1), (0, back, 1)], (0, 0, -1), "M_Frame")
    k.quad([(0, 0, 0), (1, 0, 0), (1, back, 0), (0, back, 0)], (0, 0, 1), "M_Frame")
    # Frame: four flat strips just in front of the glass (8 triangles; boxes cost 40).
    f = g - 0.01
    for a0, a1, z0, z1 in ((0, FRAME_W, 0, 1), (1 - FRAME_W, 1, 0, 1), (FRAME_W, 1 - FRAME_W, 1 - FRAME_W, 1),
                           (FRAME_W, 1 - FRAME_W, 0, FRAME_W)):
        k.quad([(a0, f, z0), (a1, f, z0), (a1, f, z1), (a0, f, z1)], (0, -1, 0), "M_Frame")
    if sill:
        # Only the faces seen from the street: the front and the top.
        k.box(-0.02, 1.02, -SILL_OUT, 0.1, -SILL_H, 0, "M_Frame", skip=("back", "bottom", "left", "right"))
    return k.finish()


def leaf():
    k = Kit("KIT_Leaf")
    d = kit.LEAF_IN
    k.quad([(0, d, 0), (1, d, 0), (1, d, 1), (0, d, 1)], (0, -1, 0), "M_Leaf")
    return k.finish()


def roof_cap():
    k = Kit("KIT_RoofCap")
    # Parapet wall (scaled to the parapet height and depth) and a proud coping on top.
    k.box(0, 1, 0, 1, 0, 1 - COPING_H, "M_Wall", skip=("bottom", "top"))
    k.box(0, 1, -COPING_OUT, 1 + COPING_OUT, 1 - COPING_H, 1, "M_Coping", skip=())
    return k.finish()


def _export(ob, path):
    for other in bpy.context.scene.objects:
        other.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=False,
                              export_yup=True, export_materials="EXPORT", export_image_format="NONE")


def main():
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    os.makedirs(OUT, exist_ok=True)
    made = [wall(), pier(), corner(), pane("KIT_Pane", True), pane("KIT_PaneCurtain", False), leaf(), roof_cap()]
    names = {ob.name for ob in made}
    if names != set(kit.MODULES):
        raise SystemExit("kit modules %s do not match kit_layout.MODULES %s" % (sorted(names), sorted(kit.MODULES)))
    for ob in made:
        path = os.path.join(OUT, ob.name + ".glb")
        _export(ob, path)
        print("KIT", ob.name, "tris", sum(len(p.vertices) - 2 for p in ob.data.polygons),
              "slots", [m.name for m in ob.data.materials], os.path.getsize(path), "bytes", flush=True)


if __name__ == "__main__":
    main()
