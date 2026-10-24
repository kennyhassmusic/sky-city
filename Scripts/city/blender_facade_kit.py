"""Build the facade kit: the small modules import_city_ue.py --buildings kit instances.

Eighteen GLBs in SourceArt/CityGen/kit (KIT_Wall, KIT_Pier, KIT_Corner, KIT_Pane,
KIT_PaneCurtain, KIT_Leaf, KIT_RoofCap, KIT_Sill, KIT_Cornice, KIT_Panel,
KIT_Decal, KIT_DecalFloor, plus the walkup kit KIT_Box, KIT_Bracket,
KIT_ArchLintel, KIT_Keystone, KIT_Awning, KIT_Dish; kit_layout.py describes
each). Sizes and depths are the mesher's (kit_layout.py holds them, and
kit_layout places the modules exactly where blender_city._fitted_facade puts
its spans, piers and panes). Every module is 1 m long and 1 m tall and is
scaled per instance in Unreal.

Frame: Unreal gets local X = Blender X, local Y = -Blender Y, Z = Z (the same
mapping the city GLBs go through). Local +Y in Unreal is "into the building",
so here the depth runs along Blender -Y. Faces are wound so their normals
face the way given, not left to a recalculation.

Material slots (names are what Unreal binds, per HISM): M_Wall (walls, piers,
corners, roof slab, parapet), M_Trim (sills, crowns, belts, coping), M_Glass,
M_PaneBack (lit or dark room), M_Frame (frames and reveals), M_Leaf (blind or
curtain), M_Panel (storefront), M_Decal.

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
    # Between two panes: the front and the two reveals, 1 m deep (scaled to PIER_DEPTH).
    # Floors stack, so no top or bottom.
    k.box(0, 1, 0, 1, 0, 1, "M_Wall", skip=("back", "top", "bottom"))
    return k.finish()


def corner():
    k = Kit("KIT_Corner")
    # End pilaster: Y -1..1, scaled to the style's proud, so it stands out of the wall by that much.
    k.box(0, 1, -1, 1, 0, 1, "M_Wall", skip=("back",))
    return k.finish()


def sill():
    k = Kit("KIT_Sill")
    # Proud by its Y scale; tucks 0.15 of that under the pane. Seen from the street: front, top, ends, underside.
    k.box(0, 1, -1, 0.15, 0, 1, "M_Trim", skip=("back",))
    return k.finish()


def cornice():
    k = Kit("KIT_Cornice")
    # A crown or belt band, proud by its Y scale, with a drip moulding along its top edge.
    k.box(0, 1, -1, 0.1, 0, 0.8, "M_Trim", skip=("back",))
    k.box(0, 1, -1.15, 0.1, 0.8, 1, "M_Trim", skip=("back",))
    return k.finish()


def panel():
    k = Kit("KIT_Panel")
    k.quad([(0, -0.02, 0), (1, -0.02, 0), (1, -0.02, 1), (0, -0.02, 1)], (0, -1, 0), "M_Panel")
    return k.finish()


def decal():
    k = Kit("KIT_Decal")
    k.quad([(0, -0.03, 0), (1, -0.03, 0), (1, -0.03, 1), (0, -0.03, 1)], (0, -1, 0), "M_Decal")
    return k.finish()


def decal_floor():
    k = Kit("KIT_DecalFloor")
    # Lying on the sidewalk: X along the facade, Y towards it, facing up.
    k.quad([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], (0, 0, 1), "M_Decal")
    return k.finish()


def pane(name):
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
    # Sills are their own module (KIT_Sill): each style sets its own.
    return k.finish()


def glass():
    k = Kit("KIT_Glass")
    # A shop window: the glass at half its depth scale, a frame just in front; no room back
    # (walkup.py models the shop behind it).
    k.quad([(0, 0.5, 0), (1, 0.5, 0), (1, 0.5, 1), (0, 0.5, 1)], (0, -1, 0), "M_Glass")
    f = 0.49
    for a0, a1, z0, z1 in ((0, FRAME_W, 0, 1), (1 - FRAME_W, 1, 0, 1), (FRAME_W, 1 - FRAME_W, 1 - FRAME_W, 1),
                           (FRAME_W, 1 - FRAME_W, 0, FRAME_W)):
        k.quad([(a0, f, z0), (a1, f, z0), (a1, f, z1), (a0, f, z1)], (0, -1, 0), "M_Frame")
    # Reveals from the wall plane back to the glass, so the frame reads as set into the opening.
    k.quad([(0, 0, 0), (0, 0.5, 0), (0, 0.5, 1), (0, 0, 1)], (1, 0, 0), "M_Frame")
    k.quad([(1, 0, 0), (1, 0.5, 0), (1, 0.5, 1), (1, 0, 1)], (-1, 0, 0), "M_Frame")
    k.quad([(0, 0, 1), (1, 0, 1), (1, 0.5, 1), (0, 0.5, 1)], (0, 0, -1), "M_Frame")
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
    k.box(0, 1, -COPING_OUT, 1 + COPING_OUT, 1 - COPING_H, 1, "M_Trim", skip=())
    return k.finish()


def box():
    k = Kit("KIT_Box")
    # Walkup kit: a closed box (chimneys, condensers, posts, decks, doors), all six faces.
    k.box(0, 1, 0, 1, 0, 1, "M_Wall")
    return k.finish()


def bracket():
    k = Kit("KIT_Bracket")
    # Walkup kit: a cornice console, deepest (most proud) at the top, tapering to the wall
    # going down, in steps; front, both sides and the stepped underside, no back.
    steps = 6
    top_z = 0.85
    for i in range(steps):
        z0 = top_z * i / float(steps)
        z1 = top_z * (i + 1) / float(steps)
        t = (i + 1) / float(steps)
        proud = -(0.3 + 0.7 * t ** 1.6)  # curves faster near the top
        k.box(0, 1, proud, 0, z0, z1, "M_Trim", skip=("back", "top"))
    k.box(0, 1, -1.0, 0, top_z, 1.0, "M_Trim", skip=("back", "bottom"))
    return k.finish()


def arch_lintel():
    k = Kit("KIT_ArchLintel")
    # Walkup kit: a segmental arch band over a punched window, 8 segments; front, soffit, ends.
    segs = 8
    y0, y1 = -1.0, 0.1

    def lo(x):
        return 0.4 * (1.0 - (2.0 * x - 1.0) ** 2)

    def hi(x):
        return 0.6 + 0.4 * (1.0 - (2.0 * x - 1.0) ** 2)

    for i in range(segs):
        x0 = i / float(segs)
        x1 = (i + 1) / float(segs)
        zl0, zl1, zh0, zh1 = lo(x0), lo(x1), hi(x0), hi(x1)
        k.quad([(x0, y0, zl0), (x1, y0, zl1), (x1, y0, zh1), (x0, y0, zh0)], (0, -1, 0), "M_Trim")
        k.quad([(x0, y0, zl0), (x1, y0, zl1), (x1, y1, zl1), (x0, y1, zl0)], (0, 0, -1), "M_Trim")
    k.quad([(0, y0, lo(0.0)), (0, y1, lo(0.0)), (0, y1, hi(0.0)), (0, y0, hi(0.0))], (-1, 0, 0), "M_Trim")
    k.quad([(1, y1, lo(1.0)), (1, y0, lo(1.0)), (1, y0, hi(1.0)), (1, y1, hi(1.0))], (1, 0, 0), "M_Trim")
    return k.finish()


def keystone():
    k = Kit("KIT_Keystone")
    # Walkup kit: a trapezoid block over an arch, wider at the top; front, sides, top.
    y0, y1 = -1.0, 0.1
    k.quad([(0.25, y0, 0), (0.75, y0, 0), (1, y0, 1), (0, y0, 1)], (0, -1, 0), "M_Trim")
    k.quad([(0.25, y0, 0), (0.25, y1, 0), (0, y1, 1), (0, y0, 1)], (-1, 0, 0), "M_Trim")
    k.quad([(0.75, y0, 0), (1, y0, 1), (1, y1, 1), (0.75, y1, 0)], (1, 0, 0), "M_Trim")
    k.quad([(0, y0, 1), (1, y0, 1), (1, y1, 1), (0, y1, 1)], (0, 0, 1), "M_Trim")
    return k.finish()


def awning():
    k = Kit("KIT_Awning")
    # Walkup kit: a shed awning, high at the wall, low and proud at the front, with a valance
    # and closed end panels; the slope is seen from above and below.
    top = [(0, 0, 1), (1, 0, 1), (1, -1, 0.3), (0, -1, 0.3)]
    eps = 0.004  # nudge the underside copy off the top face so remove_doubles keeps both
    under = [(p[0], p[1] + eps, p[2] - eps) for p in reversed(top)]
    k.quad(top, (0, -1, 1), "M_Trim")
    k.quad(under, (0, 1, -1), "M_Trim")
    k.quad([(0, -1, 0.3), (1, -1, 0.3), (1, -1, 0), (0, -1, 0)], (0, -1, 0), "M_Trim")
    k.quad([(0, 0, 1), (0, -1, 0.3), (0, -1, 0)], (-1, 0, 0), "M_Trim")
    k.quad([(1, 0, 1), (1, -1, 0.3), (1, -1, 0)], (1, 0, 0), "M_Trim")
    return k.finish()


def dish():
    k = Kit("KIT_Dish")
    # Walkup kit: a roof satellite dish on a stub mast, facing -Y and tilted up ~30 degrees.
    k.box(0.46, 0.54, 0.46, 0.54, 0.0, 0.55, "M_Trim", skip=("bottom",))
    radius = 0.4
    segs = 30
    tilt = math.radians(30.0)
    n = (0.0, -math.cos(tilt), math.sin(tilt))
    e1 = (1.0, 0.0, 0.0)
    e2 = (0.0, n[2], -n[1])
    c = (0.5, 0.32, 0.72)
    hub = (c[0] - 0.09 * n[0], c[1] - 0.09 * n[1], c[2] - 0.09 * n[2])
    rim = []
    for i in range(segs):
        a = 2.0 * math.pi * i / segs
        rim.append((c[0] + radius * (math.cos(a) * e1[0] + math.sin(a) * e2[0]),
                    c[1] + radius * (math.cos(a) * e1[1] + math.sin(a) * e2[1]),
                    c[2] + radius * (math.cos(a) * e1[2] + math.sin(a) * e2[2])))
    for i in range(segs):
        p0, p1 = rim[i], rim[(i + 1) % segs]
        k.quad([hub, p0, p1], n, "M_Trim")
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
    made = [wall(), pier(), corner(), pane("KIT_Pane"), pane("KIT_PaneCurtain"), leaf(), roof_cap(),
            sill(), cornice(), panel(), decal(), decal_floor(),
            box(), bracket(), arch_lintel(), keystone(), awning(), dish(), glass()]
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
