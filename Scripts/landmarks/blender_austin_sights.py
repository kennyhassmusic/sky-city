"""Sky City: the sights of the Austin side (Lady Bird Lake, its bridges, boats and docks, Auditorium Shores, Butler Park,
downtown's moonlight tower and Treaty Oak, 6th Street's neon, Congress Avenue's theatre sign and the Texas Capitol's
remaining monuments), modelled procedurally in headless Blender and exported as GLB, one file per asset.

Why: Kenny asked (20 Oct 2026, overnight round) for "all the structures in the surrounding areas: parks, stadiums,
landmarks, boats, the locks, docks, statues, etc". This script covers the Austin part of SkyCityMashup; the Chicago side
has its own scripts (chicago-water, chicago-parks). The Texas Capitol building and grounds are blender_capitol.py's.
What is inside the map, and what was left out, is in side-session-notes/.../austin-sights-2026-10-20.md.

Conventions (as Scripts/landmarks/blender_landmarks.py and blender_capitol.py, whose Builder class is copied unchanged):
  * real-world metres; one bmesh per asset with per-face material indices; stable slot names (M_*), mapped to MI_ATX_*
    (or to the Capitol's MI_Cap_* and the street kit's MI_Bark / MI_Leaves_liveoak) by Scripts/roads/place_austin_sights_ue.py;
  * Unreal's glTF import maps Blender (x, y, z) m -> Unreal (x, -y, z) cm: a proper rotation of the plan frame, so an asset
    whose Blender +X should point along plan angle theta (degrees CCW from plan east) gets Unreal yaw = 90 - theta;
  * objects: origin at the foot (statues, towers, trees) or at the waterline (boats, floating docks, z = 0 = the water);
    "front" faces Blender -Y for statues and signs (signs: the wall is the plane y = 0, the sign stands out toward -Y);
    boats point their bow along Blender +X;
  * SITE assets (bridge additions, the Pfluger bridge, plazas) are modelled directly in the plan frame (Blender X = plan
    east, Y = plan north) relative to a site origin listed in austin_sights.json, so they go in with theta = 0 (yaw 90);
  * Unreal heights this city uses (build_city.py, build_roads_ue.py): water surface -5.5 m, bed -8 m, street asphalt 0,
    lawn blocks +0.15, bridge decks 0 to -1.2 m with parapets to +1.1 m. Bridge additions are modelled in those heights.
  * smooth shading on curved surfaces, flat on boxes; metre-scale UVs (leaf cards keep 0-1 UVs for the kit's leaf texture).
References: SourceArt/Reference/AustinSights/<thing>/sources.txt; OpenStreetMap positions and outlines (c) OpenStreetMap
contributors, cached in SourceArt/Landmarks/austin/osm/ and turned into the plan frame with the plan's Austin layout
(rotation -164 deg about the Congress Avenue Bridge origin; see AUSTIN below).

Run (repo root):
  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/landmarks/blender_austin_sights.py [-- jobs...]
    jobs (default: all): boats docks signs tree tower bridges pfluger statues capitol shores buildings layout
    writes SourceArt/Landmarks/austin/<asset>.glb and austin_sights.json (assets + layout: every placement in plan metres)
  ... -P Scripts/landmarks/blender_austin_sights.py -- --render [names...]
    renders SourceArt/Landmarks/austin/preview_<name>.png (PREVIEWS; default: all)
"""
import json, math, os, random, sys
import bpy, bmesh
from mathutils import Matrix, Vector

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


ROOT = _skycity_root()
BASE = ROOT + "/SourceArt/Landmarks/austin"
OUT = BASE
os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
META = {}          # filled per asset, merged into austin_sights.json
LAYOUT = {}        # placements and keep-outs, plan metres


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    MATS.clear()


# ------------------------------------------------------------------ materials
MATDEF = {
    #  name                 base colour (linear)      metal rough  extra
    "M_Concrete": ((0.50, 0.48, 0.44), 0.0, 0.85, {}),          # bridge concrete, weathered cream-grey
    "M_ConcreteDark": ((0.26, 0.25, 0.23), 0.0, 0.90, {}),      # piers at the waterline, soffits
    "M_Limestone": ((0.66, 0.60, 0.48), 0.0, 0.75, {}),         # Austin limestone walls, seat walls
    "M_Granite": ((0.50, 0.29, 0.22), 0.0, 0.62, {}),           # = the Capitol's sunset-red granite (MI_Cap_Granite)
    "M_GranitePolished": ((0.30, 0.15, 0.11), 0.0, 0.30, {}),   # = MI_Cap_GranitePolished
    "M_GraniteGrey": ((0.36, 0.36, 0.35), 0.0, 0.45, {}),
    "M_GraniteBlack": ((0.035, 0.035, 0.04), 0.0, 0.22, {}),
    "M_Bronze": ((0.23, 0.16, 0.09), 0.9, 0.45, {}),            # = MI_Cap_Bronze
    "M_BronzeDark": ((0.10, 0.07, 0.045), 0.85, 0.5, {}),
    "M_Verdigris": ((0.26, 0.48, 0.40), 0.35, 0.55, {}),
    "M_Gold": ((0.80, 0.55, 0.18), 1.0, 0.30, {}),              # = MI_Cap_Gold (Liberty's flame)
    "M_GraniteRough": ((0.36, 0.20, 0.15), 0.0, 0.88, {}),      # = MI_Cap_GraniteRough (rock-faced, the Tejano outcrop)        # oxidised copper (Statue of Liberty replica)
    "M_Iron": ((0.025, 0.025, 0.028), 0.6, 0.50, {}),
    "M_TowerIron": ((0.42, 0.43, 0.44), 0.55, 0.45, {}),        # moonlight towers: grey-painted iron
    "M_Steel": ((0.30, 0.32, 0.33), 0.7, 0.40, {}),
    "M_WhiteSteel": ((0.82, 0.83, 0.82), 0.3, 0.35, {}),
    "M_Light": ((1.00, 0.93, 0.80), 0.0, 0.40, {"emit": 6.0}),  # lamp globes / lenses
    "M_Bark": ((0.30, 0.26, 0.22), 0.0, 0.90, {}),              # = street kit MI_Bark
    "M_Leaves_liveoak": ((0.20, 0.35, 0.12), 0.0, 0.60, {}),    # = street kit MI_Leaves_liveoak (leaf-cluster cards)
    "M_Lawn": ((0.09, 0.20, 0.05), 0.0, 0.95, {}),
    "M_Mulch": ((0.11, 0.07, 0.045), 0.0, 1.00, {}),
    "M_Paving": ((0.55, 0.52, 0.47), 0.0, 0.80, {}),
    "M_Gravel": ((0.55, 0.45, 0.32), 0.0, 0.95, {}),            # decomposed-granite trail
    "M_DeckConcrete": ((0.58, 0.56, 0.52), 0.0, 0.85, {}),
    "M_Asphalt": ((0.055, 0.055, 0.06), 0.0, 0.90, {}),
    "M_Water": ((0.05, 0.12, 0.14), 0.0, 0.03, {}),
    "M_WaterJet": ((0.92, 0.96, 1.00), 0.0, 0.25, {}),           # = the landmarks' translucent M_LM_WaterJet
    "M_Glass": ((0.10, 0.14, 0.17), 0.3, 0.06, {}),
    "M_GlassDark": ((0.03, 0.04, 0.05), 0.4, 0.08, {}),
    "M_Stucco": ((0.70, 0.66, 0.58), 0.0, 0.85, {}),
    "M_Metal": ((0.55, 0.56, 0.57), 0.8, 0.35, {}),
    "M_SteelDark": ((0.20, 0.08, 0.04), 0.3, 0.70, {}),          # Pfluger girders: weathering steel, rust brown
    "M_BladeGreen": ((0.03, 0.22, 0.10), 0.2, 0.45, {}),         # the theatre blade's green face
    "M_RoofWhite": ((0.80, 0.80, 0.78), 0.0, 0.55, {}),          # the gazebo's hyperbolic-paraboloid roof
    "M_Copper": ((0.55, 0.27, 0.13), 0.9, 0.35, {}),
    "M_PflugerRed": ((0.42, 0.17, 0.12), 0.0, 0.80, {}),         # red concrete paving bands             # brushed metal panels, railings
    "M_RoofMetal": ((0.33, 0.34, 0.34), 0.55, 0.45, {}),
    # 6th Street storefronts
    "M_Brick": ((0.36, 0.13, 0.08), 0.0, 0.85, {}),
    "M_TrimDark": ((0.05, 0.05, 0.05), 0.2, 0.55, {}),
    "M_PaintTeal": ((0.08, 0.28, 0.26), 0.0, 0.70, {}),
    "M_PaintRust": ((0.40, 0.12, 0.05), 0.0, 0.70, {}),
    "M_PaintCream": ((0.70, 0.62, 0.46), 0.0, 0.70, {}),
    "M_RoofFlat": ((0.16, 0.16, 0.17), 0.0, 0.90, {}),
    "M_AwningRed": ((0.40, 0.04, 0.04), 0.0, 0.80, {}),
    "M_Door": ((0.09, 0.05, 0.03), 0.2, 0.45, {}),
    # boats
    "M_HullWhite": ((0.84, 0.85, 0.85), 0.1, 0.35, {}),
    "M_TrimRed": ((0.42, 0.035, 0.03), 0.1, 0.40, {}),
    "M_TrimBlue": ((0.025, 0.08, 0.30), 0.1, 0.40, {}),
    "M_TrimGreen": ((0.03, 0.18, 0.08), 0.1, 0.40, {}),
    "M_DeckWood": ((0.30, 0.19, 0.11), 0.0, 0.80, {}),
    "M_Canopy": ((0.86, 0.86, 0.84), 0.0, 0.70, {}),
    "M_CanopyBlue": ((0.04, 0.13, 0.36), 0.0, 0.70, {}),
    "M_Seat": ((0.06, 0.06, 0.065), 0.0, 0.60, {}),
    "M_ShellYellow": ((0.80, 0.58, 0.08), 0.1, 0.30, {}),
    "M_Carbon": ((0.03, 0.03, 0.035), 0.2, 0.35, {}),
    "M_OarBlade": ((0.55, 0.04, 0.03), 0.0, 0.40, {}),
    "M_KayakRed": ((0.60, 0.06, 0.03), 0.0, 0.35, {}),
    "M_KayakYellow": ((0.85, 0.62, 0.05), 0.0, 0.35, {}),
    "M_KayakBlue": ((0.03, 0.22, 0.55), 0.0, 0.35, {}),
    "M_KayakGreen": ((0.10, 0.45, 0.12), 0.0, 0.35, {}),
    "M_BoardWhite": ((0.80, 0.82, 0.82), 0.0, 0.35, {}),
    "M_PFD": ((0.90, 0.30, 0.02), 0.0, 0.60, {}),               # life vests
    "M_Skin": ((0.50, 0.32, 0.22), 0.0, 0.60, {}),
    "M_Cloth": ((0.10, 0.15, 0.28), 0.0, 0.85, {}),
    "M_ClothLight": ((0.62, 0.60, 0.55), 0.0, 0.85, {}),
    "M_ClothRed": ((0.45, 0.06, 0.05), 0.0, 0.85, {}),
    "M_Float": ((0.07, 0.07, 0.075), 0.0, 0.70, {}),            # dock floats (black plastic)
    "M_DockDeck": ((0.36, 0.33, 0.29), 0.0, 0.85, {}),          # composite decking
    "M_Piling": ((0.20, 0.17, 0.13), 0.0, 0.90, {}),
    # signs (emissive tubes and bulbs)
    "M_SignBox": ((0.025, 0.025, 0.03), 0.5, 0.50, {}),
    "M_SignFace": ((0.70, 0.64, 0.52), 0.1, 0.45, {}),
    "M_Neon_Red": ((1.00, 0.08, 0.05), 0.0, 0.30, {"emit": 12.0}),
    "M_Neon_Pink": ((1.00, 0.12, 0.55), 0.0, 0.30, {"emit": 12.0}),
    "M_Neon_Blue": ((0.10, 0.35, 1.00), 0.0, 0.30, {"emit": 12.0}),
    "M_Neon_Green": ((0.20, 1.00, 0.25), 0.0, 0.30, {"emit": 12.0}),
    "M_Neon_Yellow": ((1.00, 0.75, 0.10), 0.0, 0.30, {"emit": 12.0}),
    "M_Neon_White": ((1.00, 0.95, 0.88), 0.0, 0.30, {"emit": 10.0}),
    "M_Bulb": ((1.00, 0.82, 0.50), 0.0, 0.30, {"emit": 9.0}),
    "M_MarqueeFace": ((0.92, 0.90, 0.84), 0.0, 0.50, {"emit": 1.5}),
    "M_LetterBlack": ((0.02, 0.02, 0.02), 0.0, 0.50, {}),
}
MATS = {}


def mat(name):
    if name in MATS:
        return MATS[name]
    rgb, metal, rough, extra = MATDEF[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if "emit" in extra:
        b.inputs["Emission Color"].default_value = (*rgb, 1)
        b.inputs["Emission Strength"].default_value = extra["emit"]
    MATS[name] = m
    return m


# ------------------------------------------------------------------ geometry builder (copied from blender_landmarks.py)
def V(*a):
    return Vector(a[0]) if len(a) == 1 else Vector(a)


class Builder:
    """Accumulates geometry into one bmesh with per-face material indices.
    face/box/card make flat, unshared faces; grid/lathe/tube make shared-vertex smooth surfaces."""

    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.hasuv = self.bm.faces.layers.int.new("hasuv")
        self.mats = []

    def mi(self, m):
        if isinstance(m, str):
            m = mat(m)
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def _poly(self, vs, m, uvs=None, smooth=False):
        # drop consecutive duplicates (poles)
        keep = []
        kuv = []
        for k, v in enumerate(vs):
            if keep and keep[-1] is v:
                continue
            keep.append(v)
            kuv.append(uvs[k] if uvs else None)
        if len(keep) > 2 and keep[0] is keep[-1]:
            keep.pop()
            kuv.pop()
        if len(keep) < 3:
            return None
        try:
            f = self.bm.faces.new(keep)
        except ValueError:
            return None
        f.material_index = self.mi(m)
        f.smooth = smooth
        if uvs:
            for l, uv in zip(f.loops, kuv):
                l[self.uv].uv = uv
            f[self.hasuv] = 1
        return f

    def face(self, pts, m, uvs=None, smooth=False):
        return self._poly([self.bm.verts.new(Vector(p)) for p in pts], m, uvs, smooth)

    def box(self, c, size, m, rot=None):
        """Axis-aligned (or rotated) box centred on c."""
        rot = rot or Matrix.Identity(3)
        sx, sy, sz = (s / 2 for s in size)
        c = Vector(c)
        P = [rot @ Vector((x * sx, y * sy, z * sz)) + c for x, y, z in
             ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))]
        for idx in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            pts = [P[i] for i in idx]
            e1, e2 = (pts[1] - pts[0]).length, (pts[3] - pts[0]).length
            self.face(pts, m, [(0, 0), (e1, 0), (e1, e2), (0, e2)])

    def boxmm(self, lo, hi, m):
        """Box from min corner to max corner."""
        lo, hi = Vector(lo), Vector(hi)
        self.box((lo + hi) / 2, hi - lo, m)

    def beam(self, a, b, w, h, m, up=(0, 0, 1)):
        """Rectangular beam from a to b (w across, h along 'up')."""
        a, b = Vector(a), Vector(b)
        t = (b - a)
        L = t.length
        if L < 1e-6:
            return
        t.normalize()
        u = Vector(up)
        if abs(t.dot(u)) > 0.98:
            u = Vector((1, 0, 0)) if abs(t.x) < 0.9 else Vector((0, 1, 0))
        x = t.cross(u).normalized()
        z = x.cross(t).normalized()
        rot = Matrix((x, t, z)).transposed()
        self.box((a + b) / 2, (w, L, h), m, rot)

    def card(self, center, normal, up, w, h, m, double=False):
        n = Vector(normal).normalized()
        u = Vector(up)
        x = u.cross(n).normalized()
        y = n.cross(x).normalized()
        c = Vector(center)
        P = [c - x * w / 2 - y * h / 2, c + x * w / 2 - y * h / 2, c + x * w / 2 + y * h / 2, c - x * w / 2 + y * h / 2]
        uv = [(0, 0), (w, 0), (w, h), (0, h)]
        self.face(P, m, uv)
        if double:
            self.face(P[::-1], m, uv[::-1])

    def poly_local(self, origin, right, up, pts2d, m, back=False):
        """Flat polygon given in a local 2-D frame (right, up); its normal is right x up (or reversed)."""
        o, r, u = Vector(origin), Vector(right).normalized(), Vector(up).normalized()
        P = [o + r * x + u * y for x, y in pts2d]
        uv = list(pts2d)
        if back:
            P, uv = P[::-1], uv[::-1]
        return self.face(P, m, uv)

    def prism(self, origin, right, up, pts2d, depth, m, smooth=False):
        """Extrude a 2-D polygon (counter-clockwise in right/up) along -(right x up) by depth: front face + back + sides."""
        o, r, u = Vector(origin), Vector(right).normalized(), Vector(up).normalized()
        n = r.cross(u).normalized()
        F = [o + r * x + u * y for x, y in pts2d]
        Bk = [p - n * depth for p in F]
        self.face(F, m, list(pts2d))
        self.face(Bk[::-1], m, [(-x, y) for x, y in pts2d][::-1])
        k = len(F)
        for i in range(k):
            j = (i + 1) % k
            e = (F[j] - F[i]).length
            self.face([F[i], Bk[i], Bk[j], F[j]], m, [(0, 0), (depth, 0), (depth, e), (0, e)])

    def grid(self, P, m, smooth=True, close_u=False, uvs=True):
        """Quad grid over P[i][j] (i = u, j = v); face normal = du x dv. close_u wraps i. Rows/columns whose
        points coincide become a single vertex (poles)."""
        nu, nv = len(P), len(P[0])
        VV = [[None] * nv for _ in range(nu)]
        for j in range(nv):
            col = [Vector(P[i][j]) for i in range(nu)]
            pole = all((c - col[0]).length < 1e-7 for c in col)
            shared = self.bm.verts.new(col[0]) if pole else None
            for i in range(nu):
                VV[i][j] = shared if pole else self.bm.verts.new(col[i])
        # arc-length uvs
        U = [[0.0] * nv for _ in range(nu + 1)]
        W = [[0.0] * nv for _ in range(nu + 1)]
        for j in range(nv):
            for i in range(1, nu + (1 if close_u else 0)):
                U[i][j] = U[i - 1][j] + (Vector(P[i % nu][j]) - Vector(P[i - 1][j])).length
        for i in range(nu + (1 if close_u else 0)):
            for j in range(1, nv):
                W[i][j] = W[i][j - 1] + (Vector(P[i % nu][j]) - Vector(P[i % nu][j - 1])).length
        last = nu if close_u else nu - 1
        for i in range(last):
            i2 = (i + 1) % nu
            for j in range(nv - 1):
                vs = [VV[i][j], VV[i2][j], VV[i2][j + 1], VV[i][j + 1]]
                uv = [(U[i][j], W[i][j]), (U[i + 1][j], W[i + 1][j]), (U[i + 1][j + 1], W[i + 1][j + 1]), (U[i][j + 1], W[i][j + 1])] if uvs else None
                self._poly(vs, m, uv, smooth)
        return VV

    def lathe(self, profile, m, segs=64, f=None, smooth=True, a0=0.0, a1=None, center=(0, 0, 0), mtx=None):
        """Surface of revolution about local z. profile rows: (r, z) or (r, z, dr, dz[, k]); dr/dz are scaled by
        f(theta) (or f[k](theta) when f is a list) for scallops and fluting. Traverse the profile counter-clockwise
        around the solid (outer face upward, top inward, inner face downward) so normals point out.
        Partial sweeps with a1; mtx (3x3) re-orients the local axis (e.g. Matrix.Rotation(-pi/2, 3, 'X') -> axis +Y)."""
        c = Vector(center)
        R = mtx or Matrix.Identity(3)
        full = a1 is None
        a1 = a0 + 2 * math.pi if full else a1
        n = segs if full else segs + 1
        fl = f if isinstance(f, (list, tuple)) else [f]
        P = []
        for i in range(n):
            th = a0 + (a1 - a0) * i / segs
            ks = [ff(th) if ff else 0.0 for ff in fl]
            ct, st = math.cos(th), math.sin(th)
            col = []
            for row in profile:
                r, z = row[0], row[1]
                dr = row[2] if len(row) > 2 else 0.0
                dz = row[3] if len(row) > 3 else 0.0
                k = ks[row[4] if len(row) > 4 else 0]
                rr = r + dr * k
                col.append(c + R @ Vector((rr * ct, rr * st, z + dz * k)))
            P.append(col)
        return self.grid(P, m, smooth, close_u=full)

    def torus(self, center, R, r, m, segs=96, sides=8, mtx=None):
        """Closed ring tube (major radius R about local z, minor radius r)."""
        c = Vector(center)
        M3 = mtx or Matrix.Identity(3)
        P = []
        for i in range(segs):
            th = 2 * math.pi * i / segs
            col = []
            for k in range(sides + 1):
                ph = 2 * math.pi * k / sides
                rr = R + r * math.cos(ph)
                col.append(c + M3 @ Vector((rr * math.cos(th), rr * math.sin(th), r * math.sin(ph))))
            P.append(col)
        self.grid(P, m, True, close_u=True)

    def sweep(self, P2, m, rows, smooth=True, close=True):
        """Generalised prism: P2 = closed 2-D outline [(x, y)...] counter-clockwise; rows = [(sx, sy, z, ox, oy)];
        a scale of 0 makes a pole. Normals point out."""
        P = []
        for (x, y) in P2:
            P.append([Vector((ox + x * sx, oy + y * sy, z)) for sx, sy, z, ox, oy in rows])
        return self.grid(P, m, smooth, close_u=close)

    def tube(self, path, radii, m, sides=10, cap0=False, cap1=False, smooth=True, up=(0, 0, 1), aspect=None):
        """Smooth tube along a path; radii per point; aspect per point = (sx, sy) to flatten the section
        (sx along the frame's 'side' axis = path x up)."""
        n = len(path)
        path = [Vector(p) for p in path]
        rings = []
        prev_x = None
        for i, p in enumerate(path):
            a = path[max(0, i - 1)]
            b = path[min(n - 1, i + 1)]
            t = (b - a).normalized()
            u = Vector(up)
            if abs(t.dot(u)) > 0.97:
                u = prev_x.cross(t) if prev_x is not None else Vector((1, 0, 0))
            x = t.cross(u).normalized()
            if prev_x is not None and x.dot(prev_x) < 0:
                x = -x
            prev_x = x
            y = t.cross(x).normalized()
            sx, sy = aspect[i] if aspect else (1.0, 1.0)
            ring = [p + (x * math.cos(2 * math.pi * k / sides) * sx + y * math.sin(2 * math.pi * k / sides) * sy) * radii[i] for k in range(sides)]
            rings.append(ring)
        P = [[rings[j][k] for j in range(n)] for k in range(sides)]
        VV = self.grid(P, m, smooth, close_u=True)
        if cap1:
            self._poly([VV[k][n - 1] for k in range(sides)], m, None, False)
        if cap0:
            self._poly([VV[k][0] for k in range(sides)][::-1], m, None, False)
        return VV

    def rod(self, a, b, r, m, sides=8, caps=True):
        self.tube([a, b], [r, r], m, sides, caps, caps, smooth=True)

    def cyl(self, base, height, radius, m, sides=16, top=True, bottom=False):
        x, y, z = base
        self.lathe([(radius, z), (radius, z + height)] if not top else [(radius, z), (radius, z + height), (0.0, z + height)], m, sides,
                   center=(x, y, 0), smooth=True)
        if bottom:
            self.lathe([(0.0, z), (radius, z)], m, sides, center=(x, y, 0))

    def sphere(self, c, r, m, segs=16, rings=8, scale=(1, 1, 1)):
        prof = []
        for j in range(rings + 1):
            ph = -math.pi / 2 + math.pi * j / rings
            prof.append((r * math.cos(ph), r * math.sin(ph)))
        VV = self.lathe(prof, m, segs)
        return VV

    def ellipsoid(self, c, radii, m, segs=16, rings=10, rot=None, half=False):
        """Ellipsoid (half=True: upper half only, open at the bottom)."""
        rot = rot or Matrix.Identity(3)
        c = Vector(c)
        P = []
        for i in range(segs):
            th = 2 * math.pi * i / segs
            col = []
            for j in range(rings + 1):
                ph = (0.0 if half else -math.pi / 2) + (math.pi / 2 if half else math.pi) * j / rings
                v = Vector((radii[0] * math.cos(ph) * math.cos(th), radii[1] * math.cos(ph) * math.sin(th), radii[2] * math.sin(ph)))
                col.append(c + rot @ v)
            P.append(col)
        self.grid(P, m, True, close_u=True)

    def wall(self, origin, right, up, width, height, thick, m, holes=(), fill=None, fill_inset=0.6, segs=8, edges=True,
             fill_back=False):
        """Wall slab in a local frame: x 0..width along right, y 0..height along up, front normal = right x up, thickness
        extruded behind. holes = [(xc, w, y0, y1, arch)]: opening from y0 to y1, then a semicircular head if arch.
        Reveals (jambs, sill, head/soffit) are modelled; fill = material of a pane set back fill_inset * thick."""
        o, r, u = Vector(origin), Vector(right).normalized(), Vector(up).normalized()
        n = r.cross(u).normalized()
        F = lambda x, y: o + r * x + u * y
        Bk = lambda x, y: F(x, y) - n * thick
        holes = sorted(holes, key=lambda h: h[0])
        polys = []
        xs = 0.0
        for xc, w, y0, y1, arch in holes:
            xl, xr = xc - w / 2, xc + w / 2
            if xl > xs + 1e-6:
                polys.append([(xs, 0), (xl, 0), (xl, height), (xs, height)])
            if y0 > 1e-6:
                polys.append([(xl, 0), (xr, 0), (xr, y0), (xl, y0)])
            if arch:
                rr = w / 2
                pts = [(xc + rr * math.cos(math.pi - math.pi * k / segs), y1 + rr * math.sin(math.pi - math.pi * k / segs)) for k in range(segs + 1)]
                for k in range(segs):
                    (ax, ay), (bx, by) = pts[k], pts[k + 1]
                    polys.append([(ax, ay), (bx, by), (bx, height), (ax, height)])
            elif y1 < height - 1e-6:
                polys.append([(xl, y1), (xr, y1), (xr, height), (xl, height)])
            xs = xr
        if xs < width - 1e-6:
            polys.append([(xs, 0), (width, 0), (width, height), (xs, height)])
        for P2 in polys:
            self.face([F(x, y) for x, y in P2], m, [(x, y) for x, y in P2])
            self.face([Bk(x, y) for x, y in P2][::-1], m, [(-x, y) for x, y in P2][::-1])
        for xc, w, y0, y1, arch in holes:
            xl, xr = xc - w / 2, xc + w / 2
            self.face([F(xl, y0), Bk(xl, y0), Bk(xl, y1), F(xl, y1)], m)
            self.face([F(xr, y0), F(xr, y1), Bk(xr, y1), Bk(xr, y0)], m)
            if y0 > 1e-6:
                self.face([F(xl, y0), F(xr, y0), Bk(xr, y0), Bk(xl, y0)], m)
            outline = [(xl, y0), (xr, y0), (xr, y1)]
            if arch:
                rr = w / 2
                pts = [(xc + rr * math.cos(math.pi - math.pi * k / segs), y1 + rr * math.sin(math.pi - math.pi * k / segs)) for k in range(segs + 1)]
                for k in range(segs):
                    (ax, ay), (bx, by) = pts[k], pts[k + 1]
                    self.face([F(ax, ay), Bk(ax, ay), Bk(bx, by), F(bx, by)], m)
                outline += pts[::-1][1:-1]
            else:
                self.face([F(xl, y1), Bk(xl, y1), Bk(xr, y1), F(xr, y1)], m)
            outline.append((xl, y1))
            if fill is not None:
                d = n * (thick * fill_inset)
                self.face([F(x, y) - d for x, y in outline], fill, [(x, y) for x, y in outline])
                if fill_back:
                    self.face([F(x, y) - d - n * 0.01 for x, y in outline][::-1], fill, [(x, y) for x, y in outline][::-1])
        if edges:
            self.face([F(0, height), F(width, height), Bk(width, height), Bk(0, height)], m)
            self.face([F(0, 0), F(0, height), Bk(0, height), Bk(0, 0)], m)
            self.face([F(width, 0), Bk(width, 0), Bk(width, height), F(width, height)], m)

    def pyramid(self, c, hx, hy, h, m, soffit=True):
        """Hip/pyramid roof: base rectangle centred on c (at c.z), apex h above."""
        c = Vector(c)
        P = [c + Vector((-hx, -hy, 0)), c + Vector((hx, -hy, 0)), c + Vector((hx, hy, 0)), c + Vector((-hx, hy, 0))]
        apex = c + Vector((0, 0, h))
        for i in range(4):
            self.face([P[i], P[(i + 1) % 4], apex], m)
        if soffit:
            self.face([P[0], P[3], P[2], P[1]], m)

    def finish(self, name, sharp_angle=48.0, weld=True):
        if weld:
            bmesh.ops.remove_doubles(self.bm, verts=self.bm.verts, dist=1e-5)
        # sharp edges: between faces meeting at more than sharp_angle, or where a flat face meets a smooth one
        thr = math.radians(sharp_angle)
        for e in self.bm.edges:
            lf = e.link_faces
            if len(lf) != 2:
                continue
            if lf[0].smooth != lf[1].smooth or not lf[0].smooth or lf[0].material_index != lf[1].material_index:
                e.smooth = False
            else:
                try:
                    e.smooth = e.calc_face_angle() <= thr
                except ValueError:
                    e.smooth = False
        # box-projected metre UVs for faces built without explicit UVs
        for f in self.bm.faces:
            if f[self.hasuv]:
                continue
            n = f.normal
            ax = max(range(3), key=lambda k: abs(n[k]))
            for l in f.loops:
                co = l.vert.co
                l[self.uv].uv = (co.y, co.z) if ax == 0 else ((co.x, co.z) if ax == 1 else (co.x, co.y))
        me = bpy.data.meshes.new(name)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(m)
        if "hasuv" in me.attributes:
            me.attributes.remove(me.attributes["hasuv"])
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        return ob


def tri_count(objs):
    return sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs)




def tri_count(objs):
    return sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs)


def join(objs):
    """One mesh object per asset (Unreal's glTF import makes one static mesh per node)."""
    objs = [o for o in objs if o is not None]
    if len(objs) == 1:
        return objs[0]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    return objs[0]


def export(name, objs, meta=None, budget=60000):
    ob = join(objs)
    ob.name = name
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.gltf(filepath=f"{OUT}/{name}.glb", export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_materials="EXPORT", export_image_format="NONE")
    lo = Vector((1e9, 1e9, 1e9))
    hi = -lo
    for v in ob.data.vertices:
        co = ob.matrix_world @ v.co
        lo = Vector(map(min, lo, co))
        hi = Vector(map(max, hi, co))
    tris = tri_count([ob])
    mats = [m.name for m in ob.data.materials]
    d = {"file": f"SourceArt/Landmarks/austin/{name}.glb", "tris": tris,
         "bbox_min_m": [round(c, 3) for c in lo], "bbox_max_m": [round(c, 3) for c in hi],
         "size_m": [round(c, 3) for c in (hi - lo)], "materials": mats}
    d.update(meta or {})
    META[name] = d
    print(f"exported {name}: {tris} tris, size {tuple(round(c, 2) for c in hi - lo)}, mats {mats}")
    if tris > budget:
        print("WARNING: over the triangle budget:", name, tris)
    return ob


def text_obj(txt, size, m, depth=0.0, bevel=0.0, fill="BOTH", align="CENTER", font=None, spacing=1.0):
    """A text curve converted to a mesh object (Blender's built-in font). fill='NONE' + bevel gives neon-tube outlines.
    Text lies in the XY plane, reading along +X, baseline at y = 0."""
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = txt
    cu.size = size
    cu.extrude = depth
    cu.bevel_depth = bevel
    cu.bevel_resolution = 1
    cu.fill_mode = fill
    cu.align_x = align
    cu.space_character = spacing
    cu.resolution_u = 3
    if font:
        cu.font = font
    ob = bpy.data.objects.new("txt", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    me.materials.clear()
    me.materials.append(mat(m) if isinstance(m, str) else m)
    o2 = bpy.data.objects.new("txtm", me)
    bpy.context.scene.collection.objects.link(o2)
    return o2


def place_obj(ob, loc=(0, 0, 0), rot=None, scale=None):
    """Bake a transform into a helper object's mesh (rot = 3x3 Matrix)."""
    M = Matrix.Translation(Vector(loc)) @ (rot.to_4x4() if rot else Matrix.Identity(4))
    if scale:
        M = M @ Matrix.Diagonal((*scale, 1.0))
    ob.data.transform(M)
    return ob


# ================================================================== the plan frame and the Austin layout
PLAN = json.load(open(ROOT + "/Saved/Mashup/plan_v3.json"))
_A = PLAN["layout"]["austin"]
_T = math.radians(_A["rotationDeg"])
AUSTIN = {"rotation_deg": _A["rotationDeg"], "offset_plan_m": [_A["x"], _A["y"]], "origin_latlon": [30.261444, -97.7451],
          "projection": "local metres = ((lon - lon0) * 111320 cos(lat0), (lat - lat0) * 110574); plan = R(rot) local + offset "
                        "(Scripts/mashup/build_mashup_data.py Proj + integrate_v2.py Frame.tf)"}
_KX = 111320.0 * math.cos(math.radians(30.261444))
_KY = 110574.0


def ll_plan(lat, lon):
    x, y = (lon - (-97.7451)) * _KX, (lat - 30.261444) * _KY
    c, s = math.cos(_T), math.sin(_T)
    return (c * x - s * y + _A["x"], s * x + c * y + _A["y"])


def plan_angle(deg_true_bearing):
    """Plan angle (deg CCW from plan east) of a real-world compass bearing (deg clockwise from true north), after the
    Austin rotation."""
    real_ccw_from_east = 90.0 - deg_true_bearing
    return real_ccw_from_east + _A["rotationDeg"]


OSM = {}


def osm():
    """Cached OpenStreetMap extracts (Overpass, 20 Oct 2026): id -> element, positions turned into plan metres."""
    if OSM:
        return OSM
    for f in ("features.json", "towers.json", "geom.json"):
        p = f"{BASE}/osm/{f}"
        if not os.path.exists(p):
            continue
        for e in json.load(open(p))["elements"]:
            k = f"{e['type'][0]}{e['id']}"
            if e["type"] == "node":
                e["plan"] = ll_plan(e["lat"], e["lon"])
            elif "geometry" in e:
                e["plan_pts"] = [ll_plan(q["lat"], q["lon"]) for q in e["geometry"] if q]
            elif "center" in e:
                e["plan"] = ll_plan(e["center"]["lat"], e["center"]["lon"])
            if k not in OSM or "plan_pts" in e:
                OSM[k] = e
    return OSM


def opos(key):
    e = osm()[key]
    if "plan" in e:
        return e["plan"]
    pts = e["plan_pts"]
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def place(asset, p, theta=0.0, z="ground", **kw):
    """Record one placement: asset at plan point p, its Blender +X along plan angle theta (deg); z = 'ground' (trace the
    city surface), 'water' (the lake surface), a number (absolute metres in Unreal's frame) or 'deck' (trace, any surface)."""
    d = {"asset": asset, "p": [round(p[0], 2), round(p[1], 2)], "theta": round(theta % 360.0, 2), "z": z}
    d.update(kw)
    LAYOUT.setdefault("placements", []).append(d)
    return d


# ================================================================== people (low-poly figures for crews, crowds and statues)
def person(B, x, y, z, yaw=0.0, pose="stand", h=1.75, cloth="M_Cloth", skin="M_Skin", legs=None, vest=None):
    """A simple figure facing +X rotated by yaw (deg) about z. pose: stand | sit (legs forward, e.g. a rower) | kneel."""
    R = Matrix.Rotation(math.radians(yaw), 3, "Z")
    o = Vector((x, y, z))
    s = h / 1.75
    T = lambda vx, vy, vz: tuple(o + R @ Vector((vx * s, vy * s, vz * s)))
    legs = legs or "M_Cloth"
    if pose == "stand":
        hip = 0.92
        for side in (-1, 1):
            B.tube([T(0, side * 0.1, 0.0), T(0, side * 0.1, 0.48), T(0, side * 0.1, hip)], [0.075 * s, 0.085 * s, 0.1 * s], legs, 6, cap1=True)
    elif pose == "sit":
        hip = 0.30
        for side in (-1, 1):
            B.tube([T(0, side * 0.1, hip), T(0.38, side * 0.12, 0.52), T(0.62, side * 0.1, 0.10)], [0.1 * s, 0.085 * s, 0.07 * s], legs, 6, cap1=True)
    else:   # kneel
        hip = 0.55
        for side in (-1, 1):
            B.tube([T(0, side * 0.1, hip), T(0.05, side * 0.1, 0.1), T(-0.4, side * 0.1, 0.05)], [0.1 * s, 0.08 * s, 0.07 * s], legs, 6, cap1=True)
    top = hip + 0.58
    B.tube([T(0, 0, hip - 0.02), T(0, 0, hip + 0.3), T(0, 0, top)], [0.17 * s, 0.16 * s, 0.19 * s], vest or cloth, 8, cap0=True, cap1=True,
           aspect=[(1.0, 0.65), (1.0, 0.6), (1.0, 0.62)])
    B.tube([T(0, 0, top), T(0, 0, top + 0.07)], [0.05 * s, 0.05 * s], skin, 6)
    B.ellipsoid(T(0.01, 0, top + 0.17), (0.095 * s, 0.085 * s, 0.115 * s), skin, segs=8, rings=5)
    return T, top


def arms(B, T, top, hands, cloth="M_Cloth", skin="M_Skin", s=1.0):
    """Arms from the shoulders to the given hand points (figure-local coordinates, metres)."""
    for side, hp in zip((-1, 1), hands):
        sh = (0.0, side * 0.2, top - 0.05)
        el = ((sh[0] + hp[0]) / 2 + 0.02, (sh[1] + hp[1]) / 2 + side * 0.06, (sh[2] + hp[2]) / 2 - 0.12)
        B.tube([T(*sh), T(*el), T(*hp)], [0.055 * s, 0.05 * s, 0.045 * s], cloth, 6, cap1=True)


# ================================================================== boats (bow along +X, z = 0 = the water surface)
def hull_rows(L, W, bow=0.25, stern_w=0.85, n=24):
    """Plan outline of a hull (closed, counter-clockwise): a parallel middle body, a fine curved bow and a transom stern."""
    pts = []
    for i in range(n + 1):
        t = i / n
        x = -L / 2 + L * t
        xb = L / 2 - L * bow
        if x <= xb:
            w = W / 2 * (stern_w + (1 - stern_w) * min(1.0, (x + L / 2) / (L * 0.15)))
        else:
            u = (x - xb) / (L * bow)
            w = W / 2 * math.sqrt(max(0.0, 1 - u * u))
        pts.append((x, w))
    right = [(x, -w) for x, w in pts]
    left = [(x, w) for x, w in reversed(pts)]
    return right + left[1:-1]


def hull(B, L, W, z0, z1, m_side, m_deck=None, bow=0.25, stern_w=0.85, deadrise=0.6, n=24, trim=None):
    """A displacement hull: bottom at z0 (narrowed by deadrise), sheer at z1, flat deck on top (m_deck)."""
    out = hull_rows(L, W, bow, stern_w, n)
    k = deadrise
    P = []
    for (x, y) in out:
        P.append([Vector((x * (1 - 0.04), y * k, z0)), Vector((x * 0.995, y * 0.97, (z0 + z1) * 0.5)), Vector((x, y, z1))])
    B.grid(P, m_side, smooth=True, close_u=True)
    B.face([tuple(c[0]) for c in P][::-1], m_side)
    if m_deck:
        B.face([tuple(c[2]) for c in P], m_deck)
    if trim:
        ring = [Vector((x * 1.003, y * 1.02, z1 - 0.12)) for x, y in out]
        P2 = [[r, r + Vector((0, 0, 0.12))] for r in ring]
        B.grid(P2, trim, smooth=True, close_u=True)
    return out


def rail(B, pts, z0, h, m, post=1.6, closed=False, r=0.025):
    """A simple railing along a polyline: posts + top rail + mid rail."""
    pts = [Vector((p[0], p[1], z0)) for p in pts]
    if closed:
        pts = pts + [pts[0]]
    for a, b in zip(pts, pts[1:]):
        L = (b - a).length
        n = max(1, round(L / post))
        for i in range(n):
            q = a.lerp(b, i / n)
            B.rod(tuple(q), tuple(q + Vector((0, 0, h))), r, m, sides=5, caps=False)
        B.rod(tuple(a + Vector((0, 0, h))), tuple(b + Vector((0, 0, h))), r, m, sides=5, caps=False)
        B.rod(tuple(a + Vector((0, 0, h * 0.5))), tuple(b + Vector((0, 0, h * 0.5))), r * 0.7, m, sides=4, caps=False)
    if not closed:
        q = pts[-1]
        B.rod(tuple(q), tuple(q + Vector((0, 0, h))), r, m, sides=5, caps=False)


def riverboat():
    """Double-deck stern-wheel excursion boat (the Lone Star Riverboat type on Lady Bird Lake): white hull and cabins
    with red trim, enclosed lower salon, open upper deck under a canopy, pilot house, twin stacks, red stern wheel."""
    B = Builder()
    L, W = 21.5, 5.0        # 75 ft overall with the wheel, 16 ft beam (references)
    out = hull(B, L, W, -0.7, 0.85, "M_HullWhite", "M_DeckWood", bow=0.22, stern_w=0.92, deadrise=0.75, trim="M_TrimRed")
    B.boxmm((-L / 2 + 0.5, -W / 2 - 0.03, 0.42), (L / 2 - 2.5, W / 2 + 0.03, 0.55), "M_TrimBlue")
    # main-deck salon (enclosed): windows band, doors fore and aft
    x0, x1, hw, zt = -7.6, 5.4, 2.2, 3.05
    B.boxmm((x0, -hw, 0.85), (x1, hw, 1.55), "M_HullWhite")
    B.boxmm((x0, -hw + 0.04, 1.55), (x1, hw - 0.04, 2.55), "M_GlassDark")
    for k in range(9):
        x = x0 + (x1 - x0) * k / 8
        B.boxmm((x - 0.08, -hw - 0.02, 1.55), (x + 0.08, hw + 0.02, 2.55), "M_HullWhite")
    B.boxmm((x0, -hw, 2.55), (x1, hw, zt - 0.15), "M_HullWhite")
    B.boxmm((x0 - 0.05, -hw - 0.05, zt - 0.3), (x1 + 0.05, hw + 0.05, zt - 0.15), "M_TrimRed")
    # upper deck: overhanging floor, railing, canopy on posts, pilot house forward, stacks
    ux0, ux1, uw = -8.8, 6.6, 2.5
    B.boxmm((ux0, -uw, zt - 0.15), (ux1, uw, zt + 0.05), "M_HullWhite")
    B.face([(ux0, -uw, zt + 0.06), (ux1, -uw, zt + 0.06), (ux1, uw, zt + 0.06), (ux0, uw, zt + 0.06)], "M_DeckWood")
    rail(B, [(ux0, -uw), (ux1, -uw), (ux1, uw), (ux0, uw)], zt + 0.06, 1.0, "M_HullWhite", post=1.2, closed=True, r=0.03)
    B.boxmm((ux0 - 0.02, -uw - 0.03, zt + 0.95), (ux1 + 0.02, -uw + 0.03, zt + 1.08), "M_TrimRed")
    B.boxmm((ux0 - 0.02, uw - 0.03, zt + 0.95), (ux1 + 0.02, uw + 0.03, zt + 1.08), "M_TrimRed")
    zc = zt + 2.45
    for x in (ux0 + 0.2, -4.5, -1.2):
        for y in (-uw + 0.12, uw - 0.12):
            B.rod((x, y, zt + 0.06), (x, y, zc), 0.06, "M_HullWhite", sides=8)
    B.boxmm((ux0 - 0.2, -uw - 0.25, zc), (-1.0, uw + 0.25, zc + 0.12), "M_Canopy")         # shade over the aft half only
    B.boxmm((ux0 - 0.25, -uw - 0.3, zc - 0.25), (-0.95, uw + 0.3, zc), "M_TrimRed")
    # pilot house (front of the upper deck) with a hip roof
    B.boxmm((4.4, -1.5, zt + 0.06), (6.4, 1.5, zt + 1.0), "M_HullWhite")
    B.boxmm((4.45, -1.45, zt + 1.0), (6.35, 1.45, zt + 1.85), "M_GlassDark")
    for y in (-1.5, -0.5, 0.5, 1.5):
        B.boxmm((6.32, y - 0.06, zt + 1.0), (6.44, y + 0.06, zt + 1.85), "M_HullWhite")
    B.boxmm((4.3, -1.6, zt + 1.85), (6.55, 1.6, zt + 2.0), "M_TrimRed")
    B.pyramid((5.42, 0.0, zt + 2.0), 1.15, 1.62, 0.7, "M_Canopy")
    # twin stacks ahead of the pilot house, with crowns
    for x in (-6.5, -5.0, -3.5, 0.5, 2.0, 3.5):                                                   # white deck chairs
        for y in (-1.2, 1.2):
            B.boxmm((x - 0.25, y - 0.25, zt + 0.06), (x + 0.25, y + 0.25, zt + 0.5), "M_HullWhite")
            B.boxmm((x - 0.27, y - 0.25, zt + 0.5), (x - 0.2, y + 0.25, zt + 0.95), "M_HullWhite")
    # bow: railing, flag staff; stern: the wheel frame and the wheel
    rail(B, [(x1 + 0.3, -2.6), (8.6, -1.6), (9.95, 0.0), (8.6, 1.6), (x1 + 0.3, 2.6)], 0.85, 1.0, "M_HullWhite", post=1.0)
    B.rod((9.6, 0, 0.85), (9.6, 0, 4.6), 0.04, "M_Iron", sides=6)
    wx, wz, wr, ww = -11.3, 1.05, 1.85, 4.2
    for y in (-ww / 2 - 0.25, ww / 2 + 0.25):
        B.beam((-9.6, y, 0.85), (wx - 0.3, y, wz + 0.2), 0.2, 0.32, "M_HullWhite")
        B.beam((-9.0, y, zt), (wx, y, wz + 0.1), 0.16, 0.2, "M_HullWhite")
    B.rod((wx, -ww / 2 - 0.4, wz), (wx, ww / 2 + 0.4, wz), 0.14, "M_Iron", sides=10)
    rx = Matrix.Rotation(-math.pi / 2, 3, "X")      # lathe axis -> +Y
    for y in (-ww / 2, ww / 2):
        B.torus((wx, y, wz), wr, 0.07, "M_TrimRed", segs=40, sides=6, mtx=rx)
        B.torus((wx, y, wz), wr * 0.45, 0.05, "M_TrimRed", segs=24, sides=6, mtx=rx)
    for k in range(14):
        a = 2 * math.pi * k / 14
        c, s = math.cos(a), math.sin(a)
        for y in (-ww / 2, ww / 2):
            B.beam((wx + c * 0.15, y, wz + s * 0.15), (wx + c * wr, y, wz + s * wr), 0.07, 0.07, "M_TrimRed")
        cx, cz = wx + c * (wr - 0.25), wz + s * (wr - 0.25)
        B.box((cx, 0.0, cz), (0.08, ww, 0.55), "M_TrimRed", rot=Matrix.Rotation(-a, 3, "Y"))
    B.boxmm((wx - wr - 0.1, -ww / 2 - 0.3, wz + wr - 0.05), (wx + 0.6, ww / 2 + 0.3, wz + wr + 0.08), "M_HullWhite")   # splash guard
    # a few passengers on the upper deck
    rnd = random.Random(7)
    for k in range(14):
        x = rnd.uniform(ux0 + 0.6, 3.8)
        y = rnd.choice((-1, 1)) * rnd.uniform(1.6, 2.5)
        person(B, x, y, zt + 0.06, yaw=90 if y < 0 else -90, h=rnd.uniform(1.6, 1.85),
               cloth=rnd.choice(("M_Cloth", "M_ClothLight", "M_ClothRed")))
    export("LM_ATX_Riverboat", [B.finish("LM_ATX_Riverboat")], {"origin": "waterline, hull centre; bow +X", "length_m": L})


def cruise_boat():
    """Covered pontoon tour boat (the bat-cruise boats at the Hyatt dock): twin pontoons, deck, white canopy, blue trim."""
    B = Builder()
    L, W = 13.5, 4.4
    for y in (-1.45, 1.45):
        B.tube([(-L / 2, y, 0.05), (-L / 2 + 0.3, y, 0.05), (L / 2 - 1.3, y, 0.05), (L / 2 - 0.2, y, 0.25), (L / 2, y, 0.45)],
               [0.42, 0.45, 0.45, 0.32, 0.12], "M_Metal", sides=12, cap0=True, cap1=True, up=(0, 0, 1))
    B.boxmm((-L / 2, -W / 2, 0.45), (L / 2 - 0.3, W / 2, 0.62), "M_TrimBlue")
    B.face([(-L / 2, -W / 2, 0.63), (L / 2 - 0.3, -W / 2, 0.63), (L / 2 - 0.3, W / 2, 0.63), (-L / 2, W / 2, 0.63)], "M_DeckWood")
    # side fences: white panels with a blue stripe, open at the gate amidships
    for y in (-W / 2, W / 2):
        for xa, xb in ((-L / 2, -0.6), (0.6, L / 2 - 0.4)):
            B.boxmm((xa, y - 0.03, 0.63), (xb, y + 0.03, 1.55), "M_TrimBlue")
            B.boxmm((xa, y - 0.04, 1.2), (xb, y + 0.04, 1.36), "M_HullWhite")
    B.boxmm((L / 2 - 0.45, -W / 2, 0.63), (L / 2 - 0.35, W / 2, 1.55), "M_HullWhite")
    # bench rows, helm console aft
    for x in (-4.6, -3.4, -2.2, -1.0, 0.8, 2.0, 3.2, 4.4):
        for y in (-1.15, 1.15):
            B.boxmm((x - 0.25, y - 0.8, 0.63), (x + 0.25, y + 0.8, 1.08), "M_Seat")
            B.boxmm((x - 0.32, y - 0.8, 1.08), (x - 0.22, y + 0.8, 1.5), "M_Seat")
    B.boxmm((-6.3, -0.5, 0.63), (-5.6, 0.5, 1.6), "M_HullWhite")
    # canopy on eight posts
    zc = 2.85
    for x in (-L / 2 + 0.2, -2.2, 2.2, L / 2 - 0.6):
        for y in (-W / 2 + 0.1, W / 2 - 0.1):
            B.rod((x, y, 0.63), (x, y, zc), 0.045, "M_Metal", sides=8)
    B.boxmm((-L / 2 - 0.15, -W / 2 - 0.15, zc), (L / 2 - 0.3, W / 2 + 0.15, zc + 0.1), "M_CanopyBlue")
    B.boxmm((-L / 2 - 0.2, -W / 2 - 0.2, zc - 0.22), (L / 2 - 0.25, W / 2 + 0.2, zc), "M_TrimBlue")
    rnd = random.Random(3)
    for k in range(10):
        x = rnd.choice((-4.6, -3.4, -2.2, -1.0, 0.8, 2.0, 3.2, 4.4)) + 0.05
        y = rnd.choice((-1, 1)) * rnd.uniform(0.6, 1.7)
        person(B, x, y, 0.63 + 0.12, yaw=0, pose="sit", h=1.7, cloth=rnd.choice(("M_Cloth", "M_ClothLight", "M_ClothRed")))
    export("LM_ATX_CruiseBoat", [B.finish("LM_ATX_CruiseBoat")], {"origin": "waterline, centre; bow +X", "length_m": L})


def shell(name, L, W, seats, oar_len, hull_m="M_ShellYellow", sweep=True, cox=True):
    """Racing shell with riggers, oars resting on the water and its crew (an eight with cox, or a single scull)."""
    B = Builder()
    n = 28
    P = []
    for i in range(n + 1):
        t = i / n
        x = -L / 2 + L * t
        w = W / 2 * math.sin(math.pi * t) ** 0.6
        d = 0.22 * math.sin(math.pi * t) ** 0.5
        P.append([Vector((x, 0, -d)), Vector((x, -w, -d * 0.4)), Vector((x, -w * 0.98, 0.1)), Vector((x, 0, 0.12)),
                  Vector((x, w * 0.98, 0.1)), Vector((x, w, -d * 0.4)), Vector((x, 0, -d))])
    B.grid([[P[i][j] for i in range(n + 1)] for j in range(7)], hull_m, smooth=True)
    B.boxmm((-L / 2 * 0.62, -W * 0.32, 0.1), (L / 2 * 0.55, W * 0.32, 0.14), "M_Carbon")       # cockpit strip
    sp = (L * 0.62) / max(1, seats)
    xs = [-L * 0.25 + sp * (k + 0.5) - sp * seats / 2 + L * 0.2 for k in range(seats)]
    for k, x in enumerate(xs):
        sides = [(-1 if k % 2 == 0 else 1)] if sweep else [-1, 1]
        for sd in sides:
            pin = Vector((x + 0.35, sd * (0.82 if sweep else 0.8), 0.32))
            B.rod((x + 0.1, sd * W * 0.45, 0.12), tuple(pin), 0.018, "M_Metal", sides=4, caps=False)
            B.rod((x + 0.6, sd * W * 0.45, 0.12), tuple(pin), 0.018, "M_Metal", sides=4, caps=False)
            # oar: handle inboard, loom out over the water, blade flat on the surface (oars at rest)
            hand = Vector((x - 0.15, -sd * (0.25 if sweep else 0.05), 0.55))
            tipx = pin + (pin - hand).normalized() * (oar_len - (pin - hand).length)
            tip = Vector((tipx.x, tipx.y, 0.02))
            B.rod(tuple(hand), tuple(tip), 0.022, "M_Carbon", sides=5, caps=True)
            d = (tip - pin).normalized()
            B.box(tuple(tip + d * 0.22), (0.5, 0.2, 0.012), "M_OarBlade", rot=Matrix.Rotation(math.atan2(d.y, d.x), 3, "Z"))
        T, top = person(B, x - 0.25, 0, 0.1, yaw=180, pose="sit", h=1.8, cloth=random.choice(("M_Cloth", "M_ClothRed")))
        arms(B, T, top, [(0.45, -0.22, top - 0.25), (0.45, 0.22, top - 0.25)])
    if cox:
        person(B, xs[0] - 1.4, 0, 0.05, yaw=0, pose="sit", h=1.5, cloth="M_ClothLight")
    export(name, [B.finish(name)], {"origin": "waterline, centre; bow +X", "length_m": L})


def kayak(name, m_hull, paddler=True, cloth="M_Cloth"):
    """Sit-on-top rental kayak (3.8 m), optionally with a paddler in a life vest and a double paddle."""
    B = Builder()
    L, W = 3.8, 0.78
    n = 20
    P = []
    for i in range(n + 1):
        t = i / n
        x = -L / 2 + L * t
        w = W / 2 * math.sin(math.pi * t) ** 0.45
        P.append([Vector((x, 0, -0.12)), Vector((x, -w, -0.04)), Vector((x, -w * 0.9, 0.2)), Vector((x, 0, 0.26 if abs(x) > 0.8 else 0.2)),
                  Vector((x, w * 0.9, 0.2)), Vector((x, w, -0.04)), Vector((x, 0, -0.12))])
    B.grid([[P[i][j] for i in range(n + 1)] for j in range(7)], m_hull, smooth=True)
    if paddler:
        T, top = person(B, -0.15, 0, 0.12, yaw=0, pose="sit", h=1.72, cloth=cloth, vest="M_PFD")
        hands = [(0.3, -0.3, top - 0.2), (0.3, 0.3, top - 0.2)]
        arms(B, T, top, hands, cloth=cloth)
        a = Vector(T(0.3, -1.15, top - 0.45))
        b = Vector(T(0.3, 1.15, top + 0.05))
        B.rod(tuple(a), tuple(b), 0.016, "M_Carbon", sides=5)
        for e, sgn in ((a, -1), (b, 1)):
            B.box(tuple(e), (0.18, 0.45, 0.01), "M_OarBlade", rot=Matrix.Rotation(math.radians(80), 3, "X"))
    export(name, [B.finish(name)], {"origin": "waterline, centre; bow +X", "length_m": L})


def sup():
    """Stand-up paddle board (3.3 m) with a standing paddler."""
    B = Builder()
    L, W = 3.3, 0.8
    n = 16
    out = []
    for i in range(n + 1):
        t = i / n
        x = -L / 2 + L * t
        w = W / 2 * (math.sin(math.pi * min(1.0, t * 1.15)) ** 0.5 if t < 0.85 else math.sin(math.pi * t) ** 0.5)
        out.append((x, max(0.05, w)))
    ring = [(x, -w) for x, w in out] + [(x, w) for x, w in reversed(out)][1:-1]
    B.sweep(ring, "M_BoardWhite", [(1, 1, -0.04, 0, 0), (1.0, 1.0, 0.08, 0, 0), (0.0, 0.0, 0.08, 0, 0)], smooth=True)
    T, top = person(B, 0.0, 0, 0.08, yaw=0, pose="stand", h=1.75, cloth="M_ClothLight", vest="M_PFD")
    arms(B, T, top, [(0.25, 0.25, top + 0.2), (0.35, 0.2, top - 0.35)], cloth="M_ClothLight")
    B.rod(T(0.22, 0.27, top + 0.32), T(0.55, 0.32, -0.02), 0.016, "M_Carbon", sides=5)
    B.box(T(0.57, 0.32, -0.05), (0.08, 0.2, 0.42), "M_OarBlade")
    export("LM_ATX_SUP", [B.finish("LM_ATX_SUP")], {"origin": "waterline, centre; nose +X", "length_m": L})


def boats():
    riverboat(); reset()
    cruise_boat(); reset()
    random.seed(11)
    shell("LM_ATX_Shell8", 17.6, 0.6, 8, 3.75, "M_ShellYellow", sweep=True, cox=True); reset()
    random.seed(12)
    shell("LM_ATX_Scull1", 8.2, 0.3, 1, 2.9, "M_HullWhite", sweep=False, cox=False); reset()
    kayak("LM_ATX_Kayak_Red", "M_KayakRed", True, "M_Cloth"); reset()
    kayak("LM_ATX_Kayak_Yellow", "M_KayakYellow", True, "M_ClothRed"); reset()
    kayak("LM_ATX_Kayak_Blue", "M_KayakBlue", False); reset()
    kayak("LM_ATX_Kayak_Green", "M_KayakGreen", False); reset()
    sup()


# ================================================================== docks (floating, z = 0 = water) and quay stairs
def dock_module():
    """Floating dock module 10 x 3 m: composite decking 0.45 m above the water on black floats, timber rub rails, cleats.
    Origin: deck centre at the waterline; the long side runs along Blender X."""
    B = Builder()
    Lx, Wy, zd = 10.0, 3.0, 0.45
    B.boxmm((-Lx / 2, -Wy / 2, zd - 0.06), (Lx / 2, Wy / 2, zd), "M_DockDeck")
    for k in range(int(Lx / 0.6)):
        x = -Lx / 2 + 0.3 + k * 0.6
        B.boxmm((x - 0.008, -Wy / 2, zd), (x + 0.008, Wy / 2, zd + 0.004), "M_Float")
    for x in (-3.4, 0.0, 3.4):
        for y in (-0.8, 0.8):
            B.boxmm((x - 1.5, y - 0.6, -0.28), (x + 1.5, y + 0.6, zd - 0.06), "M_Float")
    for y in (-Wy / 2 - 0.06, Wy / 2):
        B.boxmm((-Lx / 2, y, zd - 0.3), (Lx / 2, y + 0.06, zd - 0.02), "M_Piling")
    for x in (-Lx / 2 - 0.06, Lx / 2):
        B.boxmm((x, -Wy / 2, zd - 0.3), (x + 0.06, Wy / 2, zd - 0.02), "M_Piling")
    for x in (-4.0, 0.0, 4.0):
        for y in (-Wy / 2 + 0.15, Wy / 2 - 0.15):
            B.boxmm((x - 0.15, y - 0.04, zd), (x + 0.15, y + 0.04, zd + 0.06), "M_Iron")
            B.boxmm((x - 0.04, y - 0.04, zd), (x + 0.04, y + 0.04, zd + 0.1), "M_Iron")
    export("LM_ATX_DockModule", [B.finish("LM_ATX_DockModule")], {"origin": "deck centre at the waterline; 10 m along X, 3 m along Y"})


def piling():
    """Steel guide piling for a floating dock: 0.36 m pipe from the lake bed (-2.6 m) to 2.2 m above the water, cap."""
    B = Builder()
    B.lathe([(0.18, -2.6), (0.18, 2.1), (0.2, 2.15), (0.2, 2.25), (0.0, 2.25)], "M_Piling", segs=12)
    export("LM_ATX_Piling", [B.finish("LM_ATX_Piling")], {"origin": "waterline"})


def quay_stair(rise=5.65):
    """Steel stair down the city's quay wall to a floating dock: two flights and a landing, parallel to the wall.
    The wall face is the plane y = 0 (land at y > 0); origin at the top of the wall; the stair runs along +X and hangs
    off the wall toward -Y; it lands on the water side at z = -rise + 0.45 (dock deck level)."""
    B = Builder()
    w = 1.4
    z_top, z_bot = 0.0, -rise + 0.45
    zl = (z_top + z_bot) / 2
    run = (z_top - zl) / 0.18 * 0.28
    n = int(round((z_top - zl) / 0.18))
    yo, yi = -w - 0.1, -0.1
    def flight(xa, za, xb, zb):
        for k in range(n):
            t = k / n
            x = xa + (xb - xa) * t
            z = za + (zb - za) * t
            B.boxmm((min(x, x + (xb - xa) / n), yo, z - 0.04 - (za - zb) / n), (max(x, x + (xb - xa) / n), yi, z - (za - zb) / n), "M_Steel")
        for y in (yo, yi):
            B.beam((xa, y, za - 0.1), (xb, y, zb - 0.1), 0.08, 0.25, "M_Steel")
    flight(0.0, z_top, run, zl)
    B.boxmm((run, yo, zl - 0.06), (run + 1.6, yi, zl), "M_Steel")
    yo2, yi2 = yo - w - 0.1, yo - 0.1
    for k in range(n):
        x = run - run * k / n
        z = zl - (zl - z_bot) * (k + 1) / n
        B.boxmm((x - run / n, yo2, z - 0.04), (x, yi2, z), "M_Steel")
    B.boxmm((run, yo2, zl - 0.06), (run + 1.6, yo, zl), "M_Steel")
    for y in (yo2, yi2):
        B.beam((run, y, zl - 0.1), (0.0, y, z_bot - 0.1), 0.08, 0.25, "M_Steel")
    rail(B, [(0.0, yo + 0.02), (run, yo + 0.02)], 0.0, 1.0, "M_Metal", post=1.4)
    for q in [(0.0, yo + 0.02, z_top), (run, yo + 0.02, zl)]:
        pass
    # handrails following the slopes
    B.rod((0.0, yo - 0.02, z_top + 1.0), (run, yo - 0.02, zl + 1.0), 0.025, "M_Metal", sides=5)
    B.rod((run + 1.6, yo2 - 0.02, zl + 1.0), (0.0, yo2 - 0.02, z_bot + 1.0), 0.025, "M_Metal", sides=5)
    B.rod((run + 1.6, yo2 - 0.02, zl + 1.0), (run + 1.6, yo - 0.02, zl + 1.0), 0.025, "M_Metal", sides=5)
    for x, z in ((0.0, z_top), (run * 0.5, (z_top + zl) / 2), (run, zl), (run + 1.6, zl)):
        B.rod((x, yo - 0.02, z), (x, yo - 0.02, z + 1.0), 0.025, "M_Metal", sides=5)
    for x, z in ((run * 0.5, (zl + z_bot) / 2), (0.0, z_bot), (run + 1.6, zl)):
        B.rod((x, yo2 - 0.02, z), (x, yo2 - 0.02, z + 1.0), 0.025, "M_Metal", sides=5)
    export("LM_ATX_QuayStair", [B.finish("LM_ATX_QuayStair")], {"origin": "top of the quay wall; wall = plane y=0, water at -Y", "rise_m": rise})


def docks():
    dock_module(); reset(); piling(); reset(); quay_stair()


# ================================================================== signs: 6th Street neon (generic words) and a theatre blade
NEON_BLADES = [
    # name suffix, word (vertical), tube colour, box height
    ("LiveMusic", "LIVE", "M_Neon_Red", 3.6), ("Blues", "BLUES", "M_Neon_Blue", 4.2), ("Bar", "BAR", "M_Neon_Pink", 3.0),
    ("Tacos", "TACOS", "M_Neon_Yellow", 4.2), ("Dance", "DANCE", "M_Neon_Green", 4.2), ("Jazz", "JAZZ", "M_Neon_Blue", 3.6),
    ("Saloon", "SALOON", "M_Neon_Red", 4.8), ("Pizza", "PIZZA", "M_Neon_Green", 4.2), ("Rock", "ROCK", "M_Neon_Pink", 3.6),
    ("Club", "CLUB", "M_Neon_White", 3.6), ("Open", "OPEN", "M_Neon_Red", 3.6), ("Hotel", "HOTEL", "M_Neon_White", 4.2),
]
NEON_FLAT = [
    # name suffix, words (one line each), tube colour, width
    ("HonkyTonk", ["HONKY", "TONK"], "M_Neon_Yellow", 4.4), ("LiveTonight", ["LIVE", "TONIGHT"], "M_Neon_Red", 4.4),
    ("Cocktails", ["COCKTAILS"], "M_Neon_Pink", 4.6), ("Karaoke", ["KARAOKE"], "M_Neon_Blue", 4.0),
    ("Burgers", ["BURGERS"], "M_Neon_Green", 4.0), ("Music", ["MUSIC"], "M_Neon_White", 3.2),
]


def neon_word(txt, size, m, depth_x=None):
    """Neon tube lettering: the glyph outlines of the built-in font swept as round tubes (bevel, no fill)."""
    return text_obj(txt, size, m, depth=0.0, bevel=size * 0.035, fill="NONE")


def neon_blade(suffix, word, colour, H):
    """Projecting blade sign: a dark steel box (0.95 m out from the wall, 0.35 m thick) with the word in neon on both
    faces, letters stacked top to bottom, a neon border, and two wall brackets. Wall = plane y = 0, sign toward -Y,
    origin at the wall at the bottom of the box (the placer sets the mounting height)."""
    B = Builder()
    D, T = 0.95, 0.35          # projection from the wall, thickness
    y0, y1 = -0.25, -0.25 - D
    B.boxmm((-T / 2, y1, 0.0), (T / 2, y0, H), "M_SignBox")
    for z in (0.35, H - 0.35):
        B.boxmm((-0.06, y0, z - 0.05), (0.06, 0.0, z + 0.05), "M_Iron")
        B.boxmm((-0.15, -0.02, z - 0.15), (0.15, 0.0, z + 0.15), "M_Iron")
    objs = []
    n = len(word)
    pitch = (H - 0.5) / n
    size = min(pitch * 0.92, D * 0.95)
    for side in (-1, 1):
        # border tube
        r = 0.022
        P = [(y1 + 0.07, 0.07), (y0 - 0.07, 0.07), (y0 - 0.07, H - 0.07), (y1 + 0.07, H - 0.07)]
        for (ya, za), (yb, zb) in zip(P, P[1:] + P[:1]):
            B.rod((side * (T / 2 + 0.03), ya, za), (side * (T / 2 + 0.03), yb, zb), r, colour, sides=6, caps=False)
        for k, ch in enumerate(word):
            o = neon_word(ch, size, colour)
            zc = H - 0.25 - pitch * (k + 0.78)
            # text plane XY -> sign face (normal +-X): text +X runs along -Y (outward) on the +X face, +Y up
            if side > 0:
                rot = Matrix(((0, 0, 1), (1, 0, 0), (0, 1, 0)))      # seen from +X: text x -> +Y, y -> +Z, normal -> +X
            else:
                rot = Matrix(((0, 0, -1), (-1, 0, 0), (0, 1, 0)))    # seen from -X: text x -> -Y, y -> +Z, normal -> -X
            place_obj(o, (side * (T / 2 + 0.035), (y0 + y1) / 2 if side > 0 else (y0 + y1) / 2, zc), rot)
            objs.append(o)
    name = f"LM_ATX_Neon_{suffix}"
    export(name, [B.finish(name)] + objs, {"origin": "wall (plane y=0) at the bottom of the sign; sign projects toward -Y",
                                           "height_m": H, "word": word})


def neon_flat(suffix, lines, colour, W):
    """Flat neon sign on a wall above a door: a slim dark backing panel with neon words, facing -Y."""
    B = Builder()
    n = len(lines)
    lh = 0.62
    H = 0.25 + n * lh
    B.boxmm((-W / 2, -0.12, 0.0), (W / 2, 0.0, H), "M_SignBox")
    objs = []
    for k, line in enumerate(lines):
        size = min(lh * 0.85, (W - 0.3) / max(1, len(line)) * 1.45)
        o = neon_word(line, size, colour)
        rot = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))        # text x -> +X, text y -> +Z, text z -> -Y (out of the wall)
        place_obj(o, (0.0, -0.16, H - 0.15 - lh * (k + 0.8)), rot)
        objs.append(o)
    for (xa, za), (xb, zb) in (((-W / 2 + 0.05, 0.05), (W / 2 - 0.05, 0.05)), ((-W / 2 + 0.05, H - 0.05), (W / 2 - 0.05, H - 0.05))):
        B.rod((xa, -0.15, za), (xb, -0.15, zb), 0.018, colour, sides=6, caps=False)
    name = f"LM_ATX_NeonFlat_{suffix}"
    export(name, [B.finish(name)] + objs, {"origin": "wall (plane y=0) at the bottom centre; faces -Y", "width_m": W, "words": lines})


def theatre_sign():
    """A generic 1915-style theatre blade sign and marquee (the type on Congress Avenue; no name, no trademark): a tall
    vertical blade reading THEATRE in red neon framed by chaser bulbs, with a crown on top, over a marquee box with bulb
    rows and blank white letter boards. Wall = plane y = 0, everything toward -Y; origin at the wall at sidewalk level
    (the marquee's underside is 3.6 m up, the blade from 6.6 m to 17.6 m)."""
    B = Builder()
    # marquee: 9 m wide, 2.4 m tall, 3.2 m deep, chamfered front corners
    zm0, zm1, W, D = 3.6, 6.0, 9.0, 3.2
    P2 = [(-W / 2, 0.0), (-W / 2, -D + 0.8), (-W / 2 + 0.8, -D), (W / 2 - 0.8, -D), (W / 2, -D + 0.8), (W / 2, 0.0)]
    B.prism((0, 0, zm0), (1, 0, 0), (0, 1, 0), [(x, y) for x, y in P2][::-1], -(zm1 - zm0), "M_SignFace")
    # letter boards on the front faces
    for (xa, ya), (xb, yb) in zip(P2[:-1], P2[1:]):
        a, b = Vector((xa, ya, 0)), Vector((xb, yb, 0))
        L = (b - a).length
        if L < 2.0:
            continue
        d = (b - a).normalized()
        nrm = Vector((d.y, -d.x, 0))
        c = (a + b) / 2 + nrm * 0.02
        B.card(tuple(c + Vector((0, 0, (zm0 + zm1) / 2))), tuple(nrm), (0, 0, 1), L - 0.5, 1.3, "M_MarqueeFace")
    # bulbs (separate pass, centred correctly)
    B2 = Builder()
    for (xa, ya), (xb, yb) in zip(P2[:-1], P2[1:]):
        a, b = Vector((xa, ya, 0)), Vector((xb, yb, 0))
        L = (b - a).length
        d = (b - a).normalized()
        nrm = Vector((d.y, -d.x, 0))
        nb = max(2, int(L / 0.3))
        for k in range(nb):
            q = a + d * (L * (k + 0.5) / nb) + nrm * 0.06
            for z in (zm0 + 0.2, zm1 - 0.2):
                B2.lathe([(0.0, z - 0.06), (0.05, z - 0.04), (0.06, z), (0.05, z + 0.04), (0.0, z + 0.06)], "M_Bulb", segs=6, center=(q.x, q.y, 0))
    # underside soffit with downlights
    B.face([(x, y, zm0 - 0.001) for x, y in P2], "M_SignBox")
    # the blade: a green face with a bulb border, 2.4 m out from the wall, 0.7 m thick, 7.5..22.5 m (the 1930s blade
    # was 50 ft long, its top over 75 ft above the sidewalk), with a crest
    zb0, zb1, BD, BT = 7.5, 22.5, 2.4, 0.7
    yb0, yb1 = -0.3, -0.3 - BD
    B.boxmm((-BT / 2, yb1, zb0), (BT / 2, yb0, zb1), "M_BladeGreen")
    B.boxmm((-BT / 2 - 0.05, yb1 - 0.05, zb0 - 0.2), (BT / 2 + 0.05, yb0 + 0.05, zb0), "M_TrimRed")
    B.boxmm((-BT / 2 - 0.05, yb1 - 0.05, zb1), (BT / 2 + 0.05, yb0 + 0.05, zb1 + 0.25), "M_TrimRed")
    B.lathe([(0.0, zb1 + 0.25), (0.75, zb1 + 0.25), (0.9, zb1 + 0.6), (0.6, zb1 + 1.0), (0.3, zb1 + 1.6), (0.12, zb1 + 2.2), (0.0, zb1 + 2.3)],
            "M_TrimRed", segs=10, center=(0.0, (yb0 + yb1) / 2, 0))
    for z in (zb0 + 1.5, zb0 + 4.5, zb0 + 7.5):
        B.boxmm((-0.06, yb0, z - 0.06), (0.06, 0.0, z + 0.06), "M_Iron")
    objs = []
    word = "THEATRE"
    pitch = (zb1 - zb0 - 0.6) / len(word)
    for side in (-1, 1):
        for k, ch in enumerate(word):
            o = neon_word(ch, min(pitch * 0.9, BD * 0.8), "M_Neon_Yellow")
            zc = zb1 - 0.3 - pitch * (k + 0.8)
            rot = Matrix(((0, 0, 1), (1, 0, 0), (0, 1, 0))) if side > 0 else Matrix(((0, 0, -1), (-1, 0, 0), (0, 1, 0)))
            place_obj(o, (side * (BT / 2 + 0.03), (yb0 + yb1) / 2, zc), rot)
            objs.append(o)
        nb = int((zb1 - zb0) / 0.32)
        for k in range(nb):
            z = zb0 + 0.16 + k * 0.32
            for y in (yb0 - 0.12, yb1 + 0.12):
                B2.lathe([(0.0, -0.06), (0.05, -0.04), (0.06, 0), (0.05, 0.04), (0.0, 0.06)], "M_Bulb", segs=6,
                         center=(side * (BT / 2 + 0.06), y, z), mtx=Matrix.Rotation(math.pi / 2 * side, 3, "Y"))
    export("LM_ATX_TheatreSign", [B.finish("LM_ATX_TheatreSign"), B2.finish("LM_ATX_TheatreSign_bulbs")] + objs,
           {"origin": "wall (plane y=0) at sidewalk level; marquee 3.6-6.0 m, blade 6.6-17.6 m, projects toward -Y"})


def signs():
    for s in NEON_BLADES:
        neon_blade(*s); reset()
    for s in NEON_FLAT:
        neon_flat(*s); reset()
    theatre_sign()


# ================================================================== the Treaty Oak (live oak, ~500 years old)
def live_oak(name, H=13.0, spread=30.0, trunk_r=0.95, clear=2.4, nlimbs=7, ncards=1500, card=2.6, seed=1836, gap=None, fence=0.0):
    """A big live oak after the street kit's tree() method (crown volume -> limbs grown toward it -> leaf-cluster cards),
    scaled to a monumental tree: a short massive trunk with root flare, heavy limbs that run out nearly level and droop,
    a broad low dome of foliage. gap = (bearing_deg, width_deg): a sector of the crown left thin (the Treaty Oak lost
    much of its crown to the 1989 poisoning)."""
    rnd = random.Random(seed)
    B = Builder()          # crown: leaf cards and the smaller branches (no collision in Unreal)
    BT = Builder()         # trunk and main limbs (complex collision)
    bark, leaf = "M_Bark", "M_Leaves_liveoak"
    ch = H - clear - 1.0
    base_z = clear + 0.6
    # root flare + trunk
    flare = [(trunk_r * 1.9, 0.0), (trunk_r * 1.45, 0.25), (trunk_r * 1.15, 0.7), (trunk_r, 1.4), (trunk_r * 0.95, clear)]
    BT.lathe([(r, z) for r, z in flare] + [(trunk_r * 0.9, clear + 0.25)], bark, segs=14,
             f=lambda th: 0.12 * math.sin(5 * th) + 0.06 * math.sin(11 * th + 1.0))
    BT.lathe([(0.0, -0.05), (trunk_r * 4.0, -0.05), (trunk_r * 4.0, 0.03), (0.0, 0.06)], "M_Mulch", segs=24, smooth=False)
    if fence:      # the low chain on green steel posts round the tree, a granite marker on two steps
        npost = int(2 * math.pi * fence / 2.4)
        for k in range(npost):
            a0, a1 = 2 * math.pi * k / npost, 2 * math.pi * (k + 1) / npost
            p0 = (fence * math.cos(a0), fence * math.sin(a0))
            p1 = (fence * math.cos(a1), fence * math.sin(a1))
            BT.rod((*p0, 0.0), (*p0, 0.7), 0.035, "M_TrimGreen", sides=6)
            mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, 0.5)
            BT.tube([(*p0, 0.62), mid, (*p1, 0.62)], [0.012] * 3, "M_Iron", sides=3)
        BT.boxmm((-1.2, -fence - 2.6, 0.0), (1.2, -fence - 1.4, 0.15), "M_GraniteGrey")
        BT.boxmm((-0.9, -fence - 2.3, 0.15), (0.9, -fence - 1.6, 0.3), "M_GraniteGrey")
        BT.boxmm((-0.55, -fence - 2.05, 0.3), (0.55, -fence - 1.85, 1.2), "M_GranitePolished")

    def in_crown():
        while True:
            x, y, z = rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(0, 1)
            r = math.hypot(x, y)
            if r * r + ((z - 0.3) / 0.8) ** 2 <= 1 and z > 0.05:
                if gap:
                    b = (90 - math.degrees(math.atan2(y, x))) % 360
                    if abs((b - gap[0] + 180) % 360 - 180) < gap[1] / 2 and rnd.random() < 0.75:
                        continue
                return Vector((x * spread / 2, y * spread / 2, base_z + z * ch))
    leaves = [in_crown() for _ in range(ncards)]
    anchors = []

    def grow(start, target, r0, depth, droop=0.0, segs=6):
        pts = [Vector(start)]
        L = (Vector(target) - Vector(start)).length
        for i in range(1, segs + 1):
            t = i / segs
            p = Vector(start).lerp(Vector(target), t)
            p += Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-0.5, 0.8))) * (L * 0.05)
            p.z -= droop * math.sin(math.pi * t) * L * 0.12
            pts.append(p)
        (BT if depth == 0 else B).tube([tuple(p) for p in pts], [r0 * (1 - 0.7 * i / segs) for i in range(segs + 1)], bark,
                                       8 if depth == 0 else (6 if depth == 1 else 4), cap1=True)
        anchors.extend(pts[2:])
        return pts

    for k in range(nlimbs):
        ang = 2 * math.pi * (k + rnd.uniform(-0.3, 0.3)) / nlimbs
        if gap:
            b = (90 - math.degrees(ang)) % 360
            if abs((b - gap[0] + 180) % 360 - 180) < gap[1] / 2:
                ang += math.radians(gap[1] * 0.6)
        reach = spread * 0.5 * rnd.uniform(0.75, 0.95)
        start = Vector((math.cos(ang) * trunk_r * 0.5, math.sin(ang) * trunk_r * 0.5, clear * rnd.uniform(0.75, 1.05)))
        tgt = Vector((math.cos(ang) * reach, math.sin(ang) * reach, base_z + ch * rnd.uniform(0.05, 0.3)))
        pts = grow(start, tgt, trunk_r * rnd.uniform(0.42, 0.55), 0, droop=rnd.uniform(0.4, 1.0), segs=7)
        for j in range(5):
            a = pts[rnd.randint(2, len(pts) - 1)]
            out = Vector((a.x, a.y, 0)).normalized()
            side = Vector((-out.y, out.x, 0)) * rnd.choice((-1, 1))
            t2 = a + out * rnd.uniform(2.0, 5.0) + side * rnd.uniform(1.0, 4.0) + Vector((0, 0, rnd.uniform(0.8, 3.5)))
            sub = grow(a, t2, trunk_r * 0.16, 1, droop=0.3, segs=4)
            for j2 in range(3):
                b = sub[rnd.randint(1, len(sub) - 1)]
                t3 = b + Vector((rnd.uniform(-2.2, 2.2), rnd.uniform(-2.2, 2.2), rnd.uniform(0.3, 2.0)))
                grow(b, t3, trunk_r * 0.06, 2, segs=3)
    centre = Vector((0, 0, base_z + ch * 0.4))
    for p in leaves:
        a = min(anchors, key=lambda q: (q - p).length_squared)
        p = a.lerp(p, 0.6)
        out = p - centre
        out.z *= 0.5
        n = (out.normalized() * 0.7 + Vector((rnd.uniform(-0.5, 0.5), rnd.uniform(-0.5, 0.5), rnd.uniform(0.2, 1.0)))).normalized()
        s = card * rnd.uniform(0.8, 1.3)
        up = (Vector((0, 0, 1)) + Vector((rnd.uniform(-0.6, 0.6), rnd.uniform(-0.6, 0.6), 0))).normalized()
        if abs(n.dot(up)) > 0.95:
            up = Vector((1, 0, 0))
        nn = Vector(n).normalized()
        x = Vector(up).cross(nn).normalized()
        y = nn.cross(x).normalized()
        P = [p - x * s / 2 - y * s / 2, p + x * s / 2 - y * s / 2, p + x * s / 2 + y * s / 2, p - x * s / 2 + y * s / 2]
        uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
        B.face([tuple(q) for q in P], leaf, uv)
        B.face([tuple(q) for q in P[::-1]], leaf, [uv[1], uv[0], uv[3], uv[2]])
    export(name, [B.finish(name, sharp_angle=60.0)], {"origin": "trunk centre at grade", "height_m": H, "spread_m": spread, "part": "crown"})
    export(name + "_Trunk", [BT.finish(name + "_Trunk", sharp_angle=60.0)], {"origin": "trunk centre at grade", "part": "trunk and main limbs"})


def tree():
    # Treaty Oak: about 13 m tall, crown about 30 m across today, trunk girth about 6 m (references); a thin sector where
    # the poisoned limbs were removed.
    live_oak("LM_ATX_TreatyOak", H=13.0, spread=30.0, trunk_r=0.8, gap=(20.0, 70.0), fence=9.5)


# ================================================================== Austin's moonlight tower (1894-95; 165 ft)
ML = dict(H=50.3, POLE=4.6, S0=1.5, S1=1.25, TOP=45.4, PANEL=3.05, GUYS=(19.5, 30.5, 41.0))


def moonlight_tower():
    """One of Austin's 1890s moonlight towers (Fort Wayne Jenney Electric Co.), 165 ft = 50.3 m, as in the reference
    photos (SourceArt/Reference/AustinSights/MoonlightTower): a single cast-iron mast from the ground to 4.6 m carrying a
    tripod of struts, a hexagonal caged catwalk where the lattice starts, the triangular lattice shaft (tube chords,
    horizontal struts every ~3 m, crossed tie rods, a ladder up one corner) tapering slightly to the top cage, and the
    crown of six lamps on radiating arms with a finial. White-grey paint. Origin: the foot of the mast.
    The guy wires are a separate asset (LM_ATX_MoonlightGuys, no collision)."""
    B = Builder()
    m = "M_TowerIron"
    H, z0, zt = ML["H"], ML["POLE"], ML["TOP"]
    corner = lambda z: [Vector((r * math.cos(a), r * math.sin(a), z)) for a in (math.radians(90), math.radians(210), math.radians(330))
                        for r in [((ML["S0"] + (ML["S1"] - ML["S0"]) * (z - z0) / (zt - z0)) / math.sqrt(3))]]
    # the mast, its collars and the tripod struts
    B.lathe([(0.26, 0.0), (0.22, 0.4), (0.17, 0.5), (0.17, z0 - 0.3), (0.21, z0 - 0.2), (0.21, z0 + 0.1), (0.0, z0 + 0.1)], m, segs=12)
    for zc in (1.6, 3.1):
        B.lathe([(0.2, zc - 0.12), (0.22, zc), (0.2, zc + 0.12)], m, segs=12, smooth=True)
    for c in corner(z0):
        B.rod((0, 0, 1.6), tuple(c), 0.06, m, sides=6)
        B.rod((0, 0, 3.1), tuple(c), 0.045, m, sides=6)
    # the hexagonal caged catwalk at the foot of the lattice
    hexr = 1.75
    hx = [Vector((hexr * math.cos(math.radians(30 + 60 * k)), hexr * math.sin(math.radians(30 + 60 * k)), z0)) for k in range(6)]
    B.face([tuple(p) for p in hx], m)
    for k in range(6):
        a, b = hx[k], hx[(k + 1) % 6]
        for dz in (0.0, 1.0, 2.0):
            B.rod(tuple(a + Vector((0, 0, dz))), tuple(b + Vector((0, 0, dz))), 0.03, m, sides=4, caps=False)
        B.rod(tuple(a), tuple(a + Vector((0, 0, 2.0))), 0.035, m, sides=4, caps=False)
        for t in (0.2, 0.4, 0.6, 0.8):
            q = a.lerp(b, t)
            B.rod(tuple(q), tuple(q + Vector((0, 0, 2.0))), 0.012, m, sides=3, caps=False)
    # the lattice shaft
    n = int((zt - z0) / ML["PANEL"])
    zs = [z0 + (zt - z0) * i / n for i in range(n + 1)]
    for k in range(3):
        B.tube([tuple(corner(z)[k]) for z in zs], [0.055] * len(zs), m, sides=6, smooth=True)
    for i, z in enumerate(zs):
        C = corner(z)
        for k in range(3):
            B.rod(tuple(C[k]), tuple(C[(k + 1) % 3]), 0.035, m, sides=4, caps=False)
        if i < n:
            D = corner(zs[i + 1])
            for k in range(3):
                j = (k + 1) % 3
                B.rod(tuple(C[k]), tuple(D[j]), 0.014, m, sides=3, caps=False)
                B.rod(tuple(C[j]), tuple(D[k]), 0.014, m, sides=3, caps=False)
    # ladder up corner 0 (rungs outside the chord)
    c0 = lambda z: corner(z)[0] + Vector((0, 0.18, 0))
    for zz in [z0 + 0.35 * i for i in range(int((zt - z0) / 0.35))]:
        p = c0(zz)
        B.rod(tuple(p + Vector((-0.2, 0, 0))), tuple(p + Vector((0.2, 0, 0))), 0.012, m, sides=3, caps=False)
    B.rod(tuple(c0(z0) + Vector((-0.2, 0, 0))), tuple(c0(zt) + Vector((-0.2, 0, 0))), 0.015, m, sides=3, caps=False)
    B.rod(tuple(c0(z0) + Vector((0.2, 0, 0))), tuple(c0(zt) + Vector((0.2, 0, 0))), 0.015, m, sides=3, caps=False)
    # the top cage (a ring platform and a frame round the lamp gear) and the crown
    top = corner(zt)
    zc = zt + 2.3
    ring = [Vector((1.2 * math.cos(math.radians(30 + 60 * k)), 1.2 * math.sin(math.radians(30 + 60 * k)), zt)) for k in range(6)]
    for dz in (0.0, 1.0, 2.3):
        for k in range(6):
            B.rod(tuple(ring[k] + Vector((0, 0, dz))), tuple(ring[(k + 1) % 6] + Vector((0, 0, dz))), 0.03, m, sides=4, caps=False)
    for k in range(6):
        B.rod(tuple(ring[k]), tuple(ring[k] + Vector((0, 0, 2.3))), 0.035, m, sides=4, caps=False)
    for c in top:
        B.rod(tuple(c), (0, 0, zt + 0.2), 0.04, m, sides=4)
    B.rod((0, 0, zt), (0, 0, H - 0.4), 0.09, m, sides=8)
    B.lathe([(0.0, zc), (0.35, zc), (0.35, zc + 0.5), (0.0, zc + 0.5)], m, segs=8, smooth=False)      # gear box
    za = zt + 3.35
    for k in range(6):
        a = math.radians(60 * k)
        tip = Vector((1.25 * math.cos(a), 1.25 * math.sin(a), za + 0.25))
        B.rod((0, 0, za), tuple(tip), 0.035, m, sides=4)
        B.rod((0, 0, za - 0.7), tuple(tip - Vector((0, 0, 0.05))), 0.02, m, sides=3)
        # lamp: reflector bowl (open downward) with a glowing globe under it
        B.lathe([(0.0, tip.z + 0.05), (0.12, tip.z + 0.04), (0.32, tip.z - 0.12), (0.36, tip.z - 0.22), (0.3, tip.z - 0.2), (0.0, tip.z - 0.04)],
                m, segs=12, center=(tip.x, tip.y, 0))
        B.lathe([(0.0, tip.z - 0.12), (0.16, tip.z - 0.22), (0.17, tip.z - 0.36), (0.1, tip.z - 0.46), (0.0, tip.z - 0.48)], "M_Light", segs=10,
                center=(tip.x, tip.y, 0))
    B.lathe([(0.0, H - 0.4), (0.08, H - 0.4), (0.05, H - 0.05), (0.0, H)], m, segs=8)
    export("LM_ATX_MoonlightTower", [B.finish("LM_ATX_MoonlightTower")],
           {"origin": "foot of the mast", "height_m": H, "guy_levels_m": list(ML["GUYS"])})


def moonlight_guys(R=(16.0, 22.0, 28.0)):
    """The tower's guy wires: three levels x three directions (between the lattice corners), down to anchors at radius R
    (m). Thin steel cables, no collision; same origin as the tower; they end at z = 0 (no anchor blocks: in town the
    anchors would land on sidewalks and streets)."""
    B = Builder()
    for lev, z in enumerate(ML["GUYS"]):
        rr = (ML["S0"] + (ML["S1"] - ML["S0"]) * (z - ML["POLE"]) / (ML["TOP"] - ML["POLE"])) / math.sqrt(3)
        for k in range(3):
            a = math.radians(90 + 120 * k + 60)
            att = Vector((rr * 0.5 * math.cos(a), rr * 0.5 * math.sin(a), z))
            anc = Vector((R[lev] * math.cos(a), R[lev] * math.sin(a), 0.0))
            B.rod(tuple(att), tuple(anc), 0.012, "M_Steel", sides=3, caps=False)
    export("LM_ATX_MoonlightGuys", [B.finish("LM_ATX_MoonlightGuys")], {"origin": "foot of the tower mast", "anchor_radius_m": list(R)})


def tower():
    moonlight_tower(); reset(); moonlight_guys()


# ================================================================== geometry helpers on the plan (water, roadnet)
RN = json.load(open(ROOT + "/Saved/Roads/roadnet.json"))
Z_WATER, Z_BED, Z_DECK_SOFFIT, Z_LAWN = -5.5, -8.0, -1.2, 0.15


def in_poly(p, poly):
    x, y = p
    c = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def wet(p):
    return any(in_poly(p, r) for r in PLAN["water"]["outer"]) and not any(in_poly(p, r) for r in PLAN["water"]["inner"])


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def poly_dist(p, poly):
    return min(seg_dist(p, poly[i - 1], poly[i]) for i in range(len(poly)))


_PAVE = []


def pavement(margin_box=None):
    """roadnet.json pavement polygons (carriageway ribbons, junction rings, joints, sidewalks) with bounding boxes."""
    if not _PAVE:
        for kind, src in (("ribbon", [e["ribbon"] for e in RN["edges"] if e["ribbon"]]), ("ring", [j["ring"] for j in RN["junctions"]]),
                          ("joint", RN["joints"]), ("walk", RN["walk"])):
            for poly in src:
                xs = [q[0] for q in poly]
                ys = [q[1] for q in poly]
                _PAVE.append((kind, (min(xs), min(ys), max(xs), max(ys)), poly))
    return _PAVE


def on_pavement(p, margin=0.0, kinds=("ribbon", "ring", "joint", "walk")):
    for kind, bb, poly in pavement():
        if kind not in kinds:
            continue
        if bb[0] - margin <= p[0] <= bb[2] + margin and bb[1] - margin <= p[1] <= bb[3] + margin:
            if in_poly(p, poly) or (margin > 0 and poly_dist(p, poly) < margin):
                return True
    return False


def street_axis(names, box):
    """Least-squares centreline (point, unit direction) of the roadnet edges with these names inside box (x0,y0,x1,y1)."""
    pts = []
    for e in RN["edges"]:
        if e["name"] in names:
            pts += [p for p in e["geom"] if box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    sxx = sum((p[0] - cx) ** 2 for p in pts)
    syy = sum((p[1] - cy) ** 2 for p in pts)
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in pts)
    a = 0.5 * math.atan2(2 * sxy, sxx - syy)
    d = (math.cos(a), math.sin(a))
    if d[1] < 0:
        d = (-d[0], -d[1])
    return (cx, cy), d


def water_run(c, d, half=300.0, step=0.5):
    """Along the line c + s d, the longest wet run (s0, s1) near c."""
    best, cur = None, None
    n = int(2 * half / step)
    for i in range(n + 1):
        s = -half + i * step
        w = wet((c[0] + d[0] * s, c[1] + d[1] * s))
        if w and cur is None:
            cur = s
        if (not w or i == n) and cur is not None:
            run = (cur, s)
            if best is None or run[1] - run[0] > best[1] - best[0]:
                best = run
            cur = None
    return best


# ================================================================== arch bridges under the city's decks (Congress Ave, Lamar Blvd)
def segmental(c0, c1, z_spring, z_crown, n=16):
    """Points (s, z) of a segmental arch intrados from s=c0 to s=c1."""
    c = c1 - c0
    r = z_crown - z_spring
    R = (c * c / 4 + r * r) / (2 * r)
    sm = (c0 + c1) / 2
    zc = z_crown - R
    a = math.asin((c / 2) / R)
    return [(sm + R * math.sin(-a + 2 * a * i / n), zc + R * math.cos(-a + 2 * a * i / n)) for i in range(n + 1)], (sm, zc, R)


def arch_bridge(name, O, d, Lw, spans, half_w, z_spring=-4.6, z_crown=-1.45, ring=0.75, pier_len=3.2, open_spandrel=True,
                post_step=2.6, sidewalks=0.0, lamps=0.0, rail="post", style="congress"):
    """Arch spans, piers and spandrels below a deck the city already has (slab 0 to -1.2 m, parapets to +1.1 m), in the
    plan frame relative to O; the bridge runs along d from s=0 (one quay wall) to s=Lw (the other) and is 2 half_w wide.
    sidewalks > 0 adds cantilevered sidewalks of that width outside the parapets with an outer railing; lamps > 0 sets
    the spacing of lamp poles on the parapets."""
    B = Builder()
    n = (-d[1], d[0])
    P = lambda s, t, z: (d[0] * s + n[0] * t, d[1] * s + n[1] * t, z)
    W = half_w + 0.45            # outer face of the city's parapet
    piers = [Lw * k / spans for k in range(spans + 1)]
    conc, dark = "M_Concrete", "M_ConcreteDark"
    for k, s in enumerate(piers):
        a0 = s - pier_len / 2 if 0 < k < spans else (s - 0.2 if k else s - 0.5)
        a1 = s + pier_len / 2 if 0 < k < spans else (s + 0.5 if not k else s + 0.2)
        if 0 < k < spans:
            # pier shaft with pointed cutwaters, waterline band, cap
            tw = W + 1.2
            rr = (a1 - a0) / 2
            outline = [(s + rr * math.cos(math.pi + math.pi * k / 6), -tw + rr * math.sin(math.pi + math.pi * k / 6)) for k in range(7)] + \
                      [(s + rr * math.cos(math.pi * k / 6), tw + rr * math.sin(math.pi * k / 6)) for k in range(7)]
            def ring_at(z, grow=0.0):
                return [P(s + (u - s) * (1 + grow / rr), t + (grow if t > 0 else -grow), z) for u, t in outline]
            rows = [(Z_BED, 0.0, dark), (Z_WATER + 0.6, 0.0, conc), (z_spring - 0.45, 0.0, conc), (z_spring - 0.45, 0.25, conc), (z_spring, 0.25, conc)]
            for (za, ga, ma), (zb, gb, mb) in zip(rows, rows[1:]):
                A, Bq = ring_at(za, ga), ring_at(zb, gb)
                for i in range(len(outline)):
                    j = (i + 1) % len(outline)
                    B.face([A[i], A[j], Bq[j], Bq[i]], ma)
            B.face(ring_at(z_spring, 0.25), conc)
    # arches
    for k in range(spans):
        c0 = piers[k] + (pier_len / 2 if k > 0 else 0.0)
        c1 = piers[k + 1] - (pier_len / 2 if k + 1 < spans else 0.0)
        intra, (sm, zc, R) = segmental(c0, c1, z_spring, z_crown, 18)
        extra = [(sm + (s - sm) * (R + ring) / R, zc + (z - zc) * (R + ring) / R) for s, z in intra]
        # soffit (barrel) across the full width, face rings on both faces, extrados top
        Pt = [[Vector(P(s, t, z)) for t in (-W + 0.05, W - 0.05)] for s, z in intra]
        B.grid([[Pt[i][j] for i in range(len(intra))] for j in range(2)][::-1], conc, smooth=True)
        for sgn in (-1, 1):
            t0, t1 = sgn * (W - 0.05), sgn * (W + 0.12)
            for i in range(len(intra) - 1):
                q = [P(intra[i][0], t1, intra[i][1]), P(intra[i + 1][0], t1, intra[i + 1][1]), P(extra[i + 1][0], t1, extra[i + 1][1]),
                     P(extra[i][0], t1, extra[i][1])]
                B.face(q if sgn > 0 else q[::-1], conc)
                q2 = [P(intra[i][0], t0, intra[i][1]), P(intra[i + 1][0], t0, intra[i + 1][1]), P(intra[i + 1][0], t1, intra[i + 1][1]), P(intra[i][0], t1, intra[i][1])]
                B.face(q2 if sgn < 0 else q2[::-1], conc)
            # spandrel: open (posts) or closed (wall)
            if open_spandrel:
                m_ = int((c1 - c0) / post_step)
                for i in range(1, m_):
                    s = c0 + (c1 - c0) * i / m_
                    # extrados height at s
                    zs = zc + math.sqrt(max(0.0, (R + ring) ** 2 - (s - sm) ** 2))
                    if Z_DECK_SOFFIT - 0.35 - zs > 0.25:
                        for tt in (sgn * (W - 0.3),):
                            B.box(P(s, tt, (zs + Z_DECK_SOFFIT - 0.35) / 2), (0.45, 0.6, Z_DECK_SOFFIT - 0.35 - zs), conc,
                                  rot=Matrix.Rotation(math.atan2(d[1], d[0]), 3, "Z"))
            else:
                poly = [(c0, z_spring)] + [(s, z) for s, z in extra] + [(c1, z_spring), (c1, Z_DECK_SOFFIT), (c0, Z_DECK_SOFFIT)]
                B.face([P(s, sgn * (W + 0.02), z) for s, z in poly][:: (1 if sgn > 0 else -1)], conc)
        # transverse spandrel walls (seen from below) at the open posts
        if open_spandrel:
            m_ = int((c1 - c0) / (post_step * 2))
            for i in range(1, m_):
                s = c0 + (c1 - c0) * i / m_
                zs = zc + math.sqrt(max(0.0, (R + ring) ** 2 - (s - sm) ** 2))
                if Z_DECK_SOFFIT - 0.35 - zs > 0.25:
                    B.box(P(s, 0, (zs + Z_DECK_SOFFIT - 0.35) / 2), (0.35, 2 * W - 1.2, Z_DECK_SOFFIT - 0.35 - zs), conc,
                          rot=Matrix.Rotation(math.atan2(d[1], d[0]), 3, "Z"))
    # spandrel cap beams (fascia) under the city's parapets, full length
    for sgn in (-1, 1):
        q = [P(0.0, sgn * (W + 0.15), Z_DECK_SOFFIT - 0.55), P(Lw, sgn * (W + 0.15), Z_DECK_SOFFIT - 0.55), P(Lw, sgn * (W + 0.15), Z_DECK_SOFFIT + 0.05),
             P(0.0, sgn * (W + 0.15), Z_DECK_SOFFIT + 0.05)]
        B.face(q if sgn > 0 else q[::-1], conc)
        qb = [P(0.0, sgn * (W - 0.5), Z_DECK_SOFFIT - 0.55), P(Lw, sgn * (W - 0.5), Z_DECK_SOFFIT - 0.55), P(Lw, sgn * (W + 0.15), Z_DECK_SOFFIT - 0.55),
              P(0.0, sgn * (W + 0.15), Z_DECK_SOFFIT - 0.55)]
        B.face(qb if sgn < 0 else qb[::-1], conc)
    # cantilevered sidewalks with an outer railing (Congress), lamp poles on the parapets
    if sidewalks > 0:
        for sgn in (-1, 1):
            ti, to = sgn * W, sgn * (W + sidewalks)
            lo = [P(0.0, ti, -0.35), P(Lw, ti, -0.35), P(Lw, to, -0.35), P(0.0, to, -0.35)]
            B.face([P(0.0, ti, 0.12), P(Lw, ti, 0.12), P(Lw, to, 0.12), P(0.0, to, 0.12)][:: (1 if sgn > 0 else -1)], "M_DeckConcrete")
            B.face(lo[:: (-1 if sgn > 0 else 1)], conc)
            edge = [P(0.0, to, -0.35), P(Lw, to, -0.35), P(Lw, to, 0.12), P(0.0, to, 0.12)]
            B.face(edge if sgn > 0 else edge[::-1], conc)
            nb = int(Lw / 6.0)
            for i in range(nb + 1):
                s = Lw * i / nb
                B.beam(P(s, ti, -0.4), P(s, to - sgn * 0.2, -0.4), 0.35, 0.5, conc)
            npost = int(Lw / 2.5)
            for i in range(npost + 1):
                s = Lw * i / npost
                B.box(P(s, to - sgn * 0.15, 0.12 + 0.55), (0.22, 0.22, 1.1), "M_Metal", rot=Matrix.Rotation(math.atan2(d[1], d[0]), 3, "Z"))
            for zr in (0.62, 1.12):
                B.beam(P(0.0, to - sgn * 0.22, zr), P(Lw, to - sgn * 0.22, zr), 0.08, 0.14, "M_Metal")
    if lamps > 0:
        nl = max(1, int(Lw / lamps))
        for i in range(nl + 1):
            s = Lw * i / nl
            for sgn in (-1, 1):
                if (i + (sgn > 0)) % 2:
                    continue
                base = Vector(P(s, sgn * (half_w + 0.22), 1.1))
                top = base + Vector((0, 0, 9.6))
                B.tube([tuple(base), tuple(top)], [0.13, 0.08], "M_Metal", sides=8, cap1=True)
                arm_end = Vector(P(s, sgn * (half_w + 0.22 - 2.4), 1.1 + 10.2))
                B.tube([tuple(top), tuple(top + Vector((0, 0, 0.5)) + (arm_end - top) * 0.35), tuple(arm_end)], [0.06, 0.055, 0.05], "M_Metal", sides=6)
                B.box(tuple(arm_end + Vector((0, 0, -0.12))), (0.7, 0.35, 0.18), "M_Metal", rot=Matrix.Rotation(math.atan2(n[1], n[0]), 3, "Z"))
                B.box(tuple(arm_end + Vector((0, 0, -0.23))), (0.55, 0.26, 0.04), "M_Light", rot=Matrix.Rotation(math.atan2(n[1], n[0]), 3, "Z"))
    export(name, [B.finish(name)], {"origin": "plan frame (Blender X = plan east), origin at the quay wall on the bridge axis; z = Unreal metres",
                                    "spans": spans, "length_m": round(Lw, 2), "style": style})


def lamar_bridge(name, O, d, Lw, spans, half_w, z_spring=-6.4, z_crown=-1.9, rib=(2.6, 0.7), cols=8, walk=2.1):
    """Lamar Boulevard Bridge (1942, Art Deco): per span two parallel segmental arch ribs (2.6 m x 0.7 m) springing just
    under the lake surface, eight slender columns on each rib carrying floor beams under the city's deck, fluted piers
    with caps, sidewalks cantilevered 2.1 m on brackets with concrete-post-and-tube railings, lamp standards over the
    piers. Plan frame relative to O (s along d from quay wall to quay wall)."""
    B = Builder()
    n = (-d[1], d[0])
    P = lambda s, t, z: (d[0] * s + n[0] * t, d[1] * s + n[1] * t, z)
    rot = Matrix.Rotation(math.atan2(d[1], d[0]), 3, "Z")
    W = half_w + 0.45
    conc = "M_Concrete"
    piers = [Lw * k / spans for k in range(spans + 1)]
    pl = 3.4
    tw = W + walk
    for k, s in enumerate(piers[1:-1], 1):
        rr = pl / 2
        outline = [(s + rr * math.cos(math.pi + math.pi * j / 6), -tw + rr * math.sin(math.pi + math.pi * j / 6)) for j in range(7)] + \
                  [(s + rr * math.cos(math.pi * j / 6), tw + rr * math.sin(math.pi * j / 6)) for j in range(7)]
        for za, zb, g in ((Z_BED, -4.4, 0.0), (-4.4, -4.0, 0.25)):
            A = [P(s + (u - s) * (1 + g / rr), t + (g if t > 0 else -g), za) for u, t in outline]
            Bq = [P(s + (u - s) * (1 + g / rr), t + (g if t > 0 else -g), zb) for u, t in outline]
            for i in range(len(outline)):
                j = (i + 1) % len(outline)
                B.face([A[i], A[j], Bq[j], Bq[i]], conc)
            B.face(Bq, conc)
        for sgn in (-1, 1):                       # vertical fluting on the pier faces
            for f in range(-3, 4):
                B.box(P(s + sgn * (rr + 0.04), f * 1.8, (Z_WATER - 0.5 - 4.4) / 2), (0.1, 0.35, -4.4 - Z_WATER + 1.0), conc, rot=rot)
    for k in range(spans):
        c0, c1 = piers[k] + (pl / 2 if k > 0 else 0.0), piers[k + 1] - (pl / 2 if k + 1 < spans else 0.0)
        intra, (sm, zc, R) = segmental(c0, c1, z_spring, z_crown, 20)
        extra = [(sm + (s_ - sm) * (R + rib[1]) / R, zc + (z - zc) * (R + rib[1]) / R) for s_, z in intra]
        for sgn in (-1, 1):
            tc = sgn * (W - 2.0)
            ta, tb = tc - rib[0] / 2, tc + rib[0] / 2
            for i in range(len(intra) - 1):
                (s0, z0), (s1, z1) = intra[i], intra[i + 1]
                (e0, y0), (e1, y1) = extra[i], extra[i + 1]
                B.face([P(s0, ta, z0), P(s1, ta, z1), P(s1, tb, z1), P(s0, tb, z0)], conc)              # soffit
                B.face([P(e0, tb, y0), P(e1, tb, y1), P(e1, ta, y1), P(e0, ta, y0)], conc)              # extrados
                B.face([P(s0, tb, z0), P(s1, tb, z1), P(e1, tb, y1), P(e0, tb, y0)], conc)
                B.face([P(e0, ta, y0), P(e1, ta, y1), P(s1, ta, z1), P(s0, ta, z0)], conc)
            for j in range(1, cols + 1):
                s_ = c0 + (c1 - c0) * j / (cols + 1)
                ze = zc + math.sqrt(max(0.0, (R + rib[1]) ** 2 - (s_ - sm) ** 2))
                h = Z_DECK_SOFFIT - 0.5 - ze
                if h > 0.25:
                    B.box(P(s_, tc, ze + h / 2), (0.32, 0.4, h), conc, rot=rot)
        for j in range(0, cols + 2):
            s_ = c0 + (c1 - c0) * j / (cols + 1)
            B.box(P(s_, 0.0, Z_DECK_SOFFIT - 0.3), (0.4, 2 * tw, 0.6), conc, rot=rot)                     # floor beams + brackets
    # sidewalks on the cantilevered beams, railings, lamp standards over the piers
    for sgn in (-1, 1):
        ti, to = sgn * W, sgn * tw
        B.face([P(0.0, ti, 0.12), P(Lw, ti, 0.12), P(Lw, to, 0.12), P(0.0, to, 0.12)][:: (1 if sgn > 0 else -1)], "M_DeckConcrete")
        B.face([P(0.0, ti, -0.3), P(Lw, ti, -0.3), P(Lw, to, -0.3), P(0.0, to, -0.3)][:: (-1 if sgn > 0 else 1)], conc)
        B.face([P(0.0, to, -0.3), P(Lw, to, -0.3), P(Lw, to, 0.12), P(0.0, to, 0.12)][:: (1 if sgn > 0 else -1)], conc)
        npost = int(Lw / 3.0)
        for i in range(npost + 1):
            s_ = Lw * i / npost
            B.box(P(s_, to - sgn * 0.2, 0.12 + 0.55), (0.32, 0.32, 1.1), conc, rot=rot)
            if i < npost:
                for b_ in range(1, 6):
                    sb = s_ + Lw / npost * b_ / 6
                    B.rod(P(sb, to - sgn * 0.2, 0.3), P(sb, to - sgn * 0.2, 1.0), 0.015, "M_Metal", sides=4, caps=False)
        for zr in (0.3, 1.0):
            B.rod(P(0.0, to - sgn * 0.2, zr), P(Lw, to - sgn * 0.2, zr), 0.04, "M_Metal", sides=6, caps=False)
        for k_, s_ in enumerate(piers):
            base = Vector(P(s_, to - sgn * 0.2, 0.12))
            B.box(tuple(base + Vector((0, 0, 0.9))), (0.6, 0.6, 1.8), conc, rot=rot)
            B.tube([tuple(base + Vector((0, 0, 1.8))), tuple(base + Vector((0, 0, 8.5)))], [0.11, 0.07], "M_Metal", sides=8, cap1=True)
            arm = Vector(P(s_, to - sgn * 2.4, 8.9))
            B.tube([tuple(base + Vector((0, 0, 8.5))), tuple(arm)], [0.06, 0.05], "M_Metal", sides=6)
            B.box(tuple(arm + Vector((0, 0, -0.15))), (0.6, 0.3, 0.16), "M_Light", rot=rot)
    export(name, [B.finish(name)], {"origin": "plan frame (Blender X = plan east), origin at the quay wall on the bridge axis; z = Unreal metres",
                                    "spans": spans, "length_m": round(Lw, 2), "style": "lamar twin ribs"})


def crowd(name, n, length, depth, seed=5, sit=0.0, facing=90.0):
    """Static spectators (no collision): n figures scattered over a length x depth strip along +X, facing +Y by default
    (the bat watchers on the bridge sidewalk and on the lawn), sit = share of seated figures. Origin: strip centre."""
    rnd = random.Random(seed)
    B = Builder()
    cloths = ("M_Cloth", "M_ClothLight", "M_ClothRed", "M_ClothLight", "M_Cloth")
    for i in range(n):
        x = rnd.uniform(-length / 2, length / 2)
        y = rnd.uniform(-depth / 2, depth / 2)
        pose = "sit" if rnd.random() < sit else "stand"
        T, top = person(B, x, y, 0.0, yaw=facing + rnd.uniform(-35, 35), pose=pose, h=rnd.uniform(1.15, 1.9) if pose == "stand" else 1.7,
                        cloth=rnd.choice(cloths), legs=rnd.choice(("M_Cloth", "M_ClothLight", "M_Seat")))
        if pose == "stand" and rnd.random() < 0.4:
            arms(B, T, top, [(0.25, -0.2, top - 0.1), (0.2, 0.25, top - 0.45)], cloth=rnd.choice(cloths))
    export(name, [B.finish(name)], {"origin": "centre of the strip; figures face +Y", "figures": n})


def bridges():
    # Congress Avenue: the city's deck follows roadnet's Congress Avenue; arches over the water only
    c, d = street_axis({"South Congress Avenue", "Congress Avenue"}, (-1440, 230, -1395, 500))
    run = water_run(c, d)
    O = (c[0] + d[0] * run[0], c[1] + d[1] * run[0])
    Lw = run[1] - run[0]
    LAYOUT.setdefault("bridges", {})["congress"] = {"origin": [round(O[0], 2), round(O[1], 2)], "dir": [round(d[0], 5), round(d[1], 5)], "water_len": round(Lw, 2)}
    arch_bridge("LM_ATX_CongressBridge", O, d, Lw, BRIDGE["congress"]["spans"], 9.15, sidewalks=3.2, lamps=36.0, style="congress")
    place("LM_ATX_CongressBridge", O, 0.0, z=0.0, collision="complex", note="arches, piers, sidewalks and lamps under/along the city's deck")
    reset()
    c, d = street_axis({"South Lamar Boulevard", "North Lamar Boulevard"}, (-260, 120, -205, 400))
    run = water_run(c, d)
    O = (c[0] + d[0] * run[0], c[1] + d[1] * run[0])
    Lw = run[1] - run[0]
    LAYOUT["bridges"]["lamar"] = {"origin": [round(O[0], 2), round(O[1], 2)], "dir": [round(d[0], 5), round(d[1], 5)], "water_len": round(Lw, 2)}
    lamar_bridge("LM_ATX_LamarBridge", O, d, Lw, BRIDGE["lamar"]["spans"], 9.15)
    place("LM_ATX_LamarBridge", O, 0.0, z=0.0, collision="complex", note="open-spandrel arches under the city's deck")
    reset()
    crowd("LM_ATX_CrowdSidewalk", 70, 60.0, 2.0, seed=21, sit=0.0)
    reset()
    crowd("LM_ATX_CrowdLawn", 60, 34.0, 14.0, seed=22, sit=0.65)


# Congress: 8 main spans of up to 36 m over 288 m in reality; the plan's lake here is 210 m wide, so 6 spans of ~35 m.
# Lamar: 6 spans of 34 m over 201 m in reality; the plan's lake is 152 m, so 5 spans of ~30 m.
BRIDGE = {"congress": {"spans": 6}, "lamar": {"spans": 5}}


# ================================================================== the James D. Pfluger Pedestrian Bridge (2001)
def smooth_path(pts, step=1.0):
    """Catmull-Rom through pts, resampled every ~step metres."""
    P = [Vector((p[0], p[1], 0)) for p in pts]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        n = max(2, int((p2 - p1).length / step))
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            q = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            out.append((q.x, q.y))
    out.append((pts[-1][0], pts[-1][1]))
    return out


def path_len(pts):
    s = [0.0]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + math.dist(a, b))
    return s


def deck_strip(B, path, zs, w, m_top, m_side, m_bot, girder=None, z_off=0.0, bands=None):
    """A walkway deck along path (plan points) with heights zs: top surface (optionally striped: bands = [(t0, t1, mat)]),
    side fascias, soffit; girder = (depth, width) adds a box girder under it."""
    n = len(path)
    T = []
    for i in range(n):
        a = path[max(0, i - 1)]
        b = path[min(n - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        T.append((-dy / L, dx / L))
    def pt(i, t, z):
        return Vector((path[i][0] + T[i][0] * t, path[i][1] + T[i][1] * t, z))
    bands = bands or [(-w / 2, w / 2, m_top)]
    for t0, t1, m in bands:
        B.grid([[pt(i, t1, zs[i]) for i in range(n)], [pt(i, t0, zs[i]) for i in range(n)]], m, smooth=False)
    th = 0.35
    B.grid([[pt(i, w / 2, zs[i] - th) for i in range(n)], [pt(i, w / 2, zs[i]) for i in range(n)]], m_side, smooth=False)
    B.grid([[pt(i, -w / 2, zs[i]) for i in range(n)], [pt(i, -w / 2, zs[i] - th) for i in range(n)]], m_side, smooth=False)
    if girder:
        gd, gw = girder
        B.grid([[pt(i, -w / 2, zs[i] - th) for i in range(n)], [pt(i, w / 2, zs[i] - th) for i in range(n)]], m_bot, smooth=False)
        B.grid([[pt(i, gw / 2, zs[i] - th - gd) for i in range(n)], [pt(i, gw / 2, zs[i] - th) for i in range(n)]], m_bot, smooth=False)
        B.grid([[pt(i, -gw / 2, zs[i] - th) for i in range(n)], [pt(i, -gw / 2, zs[i] - th - gd) for i in range(n)]], m_bot, smooth=False)
        B.grid([[pt(i, -gw / 2, zs[i] - th - gd) for i in range(n)], [pt(i, gw / 2, zs[i] - th - gd) for i in range(n)]], m_bot, smooth=False)
    else:
        B.grid([[pt(i, -w / 2, zs[i] - th) for i in range(n)], [pt(i, w / 2, zs[i] - th) for i in range(n)]], m_bot, smooth=False)
    # end caps
    for i in (0, n - 1):
        q = [pt(i, -w / 2, zs[i] - th), pt(i, w / 2, zs[i] - th), pt(i, w / 2, zs[i]), pt(i, -w / 2, zs[i])]
        B.face(q if i == n - 1 else q[::-1], m_side)
    return pt, T


def picket_rail(B, pt, n, zs, t, step_i=2, h=1.25, m="M_Metal", skip=None):
    """Galvanised picket railing along a deck edge (posts every step_i path samples, top and bottom rails, pickets);
    skip(point) -> True leaves a gap (where another deck joins)."""
    for i in range(0, n - 1):
        a, b = pt(i, t, zs[i]), pt(i + 1, t, zs[i + 1])
        if skip and (skip(a) or skip(b)):
            continue
        B.rod(tuple(a + Vector((0, 0, h))), tuple(b + Vector((0, 0, h))), 0.035, m, sides=5, caps=False)
        B.rod(tuple(a + Vector((0, 0, 0.12))), tuple(b + Vector((0, 0, 0.12))), 0.02, m, sides=4, caps=False)
        if i % step_i == 0:
            B.rod(tuple(a), tuple(a + Vector((0, 0, h))), 0.045, m, sides=6, caps=False)
        L = (b - a).length
        for k in range(int(L / 0.25)):
            q = a.lerp(b, (k + 0.5) / int(L / 0.25))
            B.rod(tuple(q + Vector((0, 0, 0.12))), tuple(q + Vector((0, 0, h))), 0.009, m, sides=3, caps=False)


def lamp_cone(B, base):
    """Pfluger lamp post: a white tapered concrete base, slim pole, lantern."""
    x, y, z = base
    B.lathe([(0.0, z), (0.42, z), (0.36, z + 0.25), (0.2, z + 1.4), (0.12, z + 1.5), (0.0, z + 1.5)], "M_Stucco", segs=10, center=(x, y, 0))
    B.lathe([(0.07, z + 1.5), (0.05, z + 4.8), (0.0, z + 4.8)], "M_Steel", segs=8, center=(x, y, 0))
    B.lathe([(0.0, z + 4.75), (0.16, z + 4.8), (0.2, z + 5.2), (0.14, z + 5.45), (0.25, z + 5.5), (0.0, z + 5.62)], "M_Steel", segs=8, center=(x, y, 0))
    B.lathe([(0.0, z + 4.85), (0.15, z + 4.85), (0.17, z + 5.18), (0.0, z + 5.18)], "M_Light", segs=8, center=(x, y, 0))


def pfluger():
    """The Pfluger bridge across the lake beside Lamar, on its OpenStreetMap alignment turned into the plan: a curving
    steel box-girder walkway (7 m, red and buff concrete paving, picket railings, lamp posts on white conical bases) on
    concrete Y bents, the helix at its north end and the branch to the south bank's Lamar side. In this city the banks
    stand 5.5 m above the water, so the walkway runs at +5 m (10.5 m above the water, as the real one) from the helix
    top across the lake and ramps down to the lawn at both south ends; the helix winds up one full turn from the lawn.
    Drivable (complex collision). Site asset, plan frame, origin = the helix centre."""
    o = osm()
    main = o["w238575801"]["plan_pts"]
    leg = o["w27401202"]["plan_pts"]
    hel_a = o["w922194707"]["plan_pts"] + o["w131234491"]["plan_pts"][1:] + o["w1274242597"]["plan_pts"][1:]
    # helix centre: mean of the loop's points (one full turn)
    loop = o["w131234491"]["plan_pts"] + o["w1274242597"]["plan_pts"][1:-2]
    C = (sum(p[0] for p in loop) / len(loop), sum(p[1] for p in loop) / len(loop))
    R = sum(math.dist(p, C) for p in loop) / len(loop)
    HD, WD = 5.0, 7.0
    # keep the helix (deck edge) off the street corridor south of it: push the centre north if needed
    hw = 2.4
    for push in range(0, 12):
        Cp = (C[0], C[1] + push * 0.5)
        if not any(on_pavement((Cp[0] + (R + hw + 0.5) * math.cos(a), Cp[1] + (R + hw + 0.5) * math.sin(a))) for a in [k * math.pi / 18 for k in range(36)]):
            break
    C = Cp
    # helix: start on the lawn at the west-south-west, clockwise, one full turn plus a lead-out to the north joining the main span
    a0 = math.atan2(o["w922194707"]["plan_pts"][0][1] - C[1], o["w922194707"]["plan_pts"][0][0] - C[0])
    a_exit = math.atan2(main[0][1] - C[1], main[0][0] - C[0])
    turn = (a0 - a_exit) % (2 * math.pi) + 2 * math.pi      # clockwise from the lawn entry, round once, out to the north
    hel = []
    N = 120
    for i in range(N + 1):
        a = a0 - turn * i / N
        hel.append((C[0] + R * math.cos(a), C[1] + R * math.sin(a)))
    # main span: from the helix exit (nearest helix-end point) through the OSM alignment to the south bank
    m0 = min(range(len(main)), key=lambda i: math.dist(main[i], hel[-1]))
    span = smooth_path([hel[-1]] + main[max(1, m0 + 1):], step=2.0)
    s_span = path_len(span)
    Ls = s_span[-1]
    # profile: helix 0.2 -> HD over the turn; main level, then down to the lawn over the last 72 m
    z_end = Z_LAWN + 0.05
    zs_span = [HD if s < Ls - 72 else z_end + (HD - z_end) * 0.5 * (1 + math.cos(math.pi * (s - (Ls - 72)) / 72)) for s in s_span]
    s_hel = path_len(hel)
    zs_hel = [z_end + (HD - z_end) * (s / s_hel[-1]) for s in s_hel]
    # branch: leaves the main where the OSM leg starts, ramps to the lawn at its end
    b0 = min(range(len(span)), key=lambda i: math.dist(span[i], leg[0]))
    legp = smooth_path([span[b0]] + leg[1:], step=2.0)
    s_leg = path_len(legp)
    zb = zs_span[b0]
    zs_leg = [zb + (z_end - zb) * (0.5 - 0.5 * math.cos(math.pi * s / s_leg[-1])) for s in s_leg]
    B = Builder()
    bands = [(-WD / 2, -WD / 2 + 2.2, "M_PflugerRed"), (-WD / 2 + 2.2, WD / 2 - 2.2, "M_DeckConcrete"), (WD / 2 - 2.2, WD / 2, "M_PflugerRed")]
    rel = lambda pts: [(p[0] - C[0], p[1] - C[1]) for p in pts]
    parts = {}
    for key, path, zs, w, girder in (("span", rel(span), zs_span, WD, (1.7, 4.2)), ("helix", rel(hel), zs_hel, 2 * hw, (0.9, 2.6)),
                                      ("leg", rel(legp), zs_leg, 5.0, (1.2, 3.0))):
        bb = bands if key == "span" else [(-w / 2, w / 2, "M_PflugerRed")]
        pt, T = deck_strip(B, path, zs, w, "M_DeckConcrete", "M_Steel", "M_SteelDark", girder=girder, bands=bb)
        parts[key] = (path, zs, pt, len(path), w, T)
    # railings (the leg/span junction keeps an opening), lamp posts every ~24 m alternating sides
    def near(path, half):
        def f(q):
            return min(seg_dist((q.x, q.y), a, b) for a, b in zip(path, path[1:])) < half
        return f
    in_leg = near(parts["leg"][0], parts["leg"][4] / 2 + 0.15)
    in_span = near(parts["span"][0], WD / 2 + 0.15)
    # the mid-river plaza where the two curved "avenues" meet (the deck widens to ~13 m): a lens 36 m long on the span
    path_s, zs_s, pt_s, n_s, w_s, T_s = parts["span"]
    ss = path_len(path_s)
    wet_i = [i for i in range(n_s) if wet((path_s[i][0] + C[0], path_s[i][1] + C[1])) and zs_s[i] >= HD - 0.01]
    plaza = None
    if wet_i:
        s_mid = ss[wet_i[len(wet_i) // 2]]
        PL = 36.0
        idx = [i for i in range(n_s) if abs(ss[i] - s_mid) <= PL / 2]
        if len(idx) > 3:
            hwid = lambda i: WD / 2 + 3.0 * math.cos(math.pi * (ss[i] - s_mid) / PL) ** 2
            top_l = [pt_s(i, hwid(i), zs_s[i] + 0.01) for i in idx]
            top_r = [pt_s(i, -hwid(i), zs_s[i] + 0.01) for i in idx]
            B.grid([top_l, top_r], "M_DeckConcrete", smooth=False)
            for side, top in ((1, top_l), (-1, top_r)):
                bot = [q - Vector((0, 0, 0.6)) for q in top]
                B.grid([bot, top] if side > 0 else [top, bot], "M_SteelDark", smooth=False)
                B.grid([[pt_s(i, 0, zs_s[i] - 0.6) for i in idx], bot] if side > 0 else [bot, [pt_s(i, 0, zs_s[i] - 0.6) for i in idx]], "M_SteelDark", smooth=False)
                for a, b in zip(top, top[1:]):
                    B.rod(tuple(a + Vector((0, 0, 1.25))), tuple(b + Vector((0, 0, 1.25))), 0.035, "M_Metal", sides=5, caps=False)
                    B.rod(tuple(a + Vector((0, 0, 0.12))), tuple(b + Vector((0, 0, 0.12))), 0.02, "M_Metal", sides=4, caps=False)
                    B.rod(tuple(a), tuple(a + Vector((0, 0, 1.25))), 0.045, "M_Metal", sides=6, caps=False)
                    L = (b - a).length
                    for k in range(int(L / 0.25)):
                        q = a.lerp(b, (k + 0.5) / int(L / 0.25))
                        B.rod(tuple(q + Vector((0, 0, 0.12))), tuple(q + Vector((0, 0, 1.25))), 0.009, "M_Metal", sides=3, caps=False)
            for k in (-1, 1):                                    # benches and planters on the plaza
                i = idx[len(idx) // 2 + k * 2]
                for side in (-1, 1):
                    c_ = pt_s(i, side * (WD / 2 + 1.6), zs_s[i])
                    B.box(tuple(c_ + Vector((0, 0, 0.25))), (2.0, 0.5, 0.5), "M_Limestone")
                c_ = pt_s(idx[len(idx) // 2], 0.0, zs_s[idx[len(idx) // 2]])
            for side in (-1, 1):
                c_ = pt_s(idx[len(idx) // 2], side * (WD / 2 + 1.8), zs_s[idx[len(idx) // 2]])
                B.lathe([(0.0, c_.z), (1.0, c_.z), (1.0, c_.z + 0.6), (0.85, c_.z + 0.6), (0.0, c_.z + 0.55)], "M_Limestone", segs=12, center=(c_.x, c_.y, 0))
            plaza = (ss[idx[0]] + 0.5, ss[idx[-1]] - 0.5)
    for key, (path, zs, pt, n, w, T) in parts.items():
        sk = in_leg if key == "span" else (in_span if key == "leg" else None)
        if key == "span" and plaza:
            def sk(q, _base=in_leg, _pl=plaza, _path=path, _ss=ss):
                if _base(q):
                    return True
                i = min(range(len(_path)), key=lambda j: (_path[j][0] - q.x) ** 2 + (_path[j][1] - q.y) ** 2)
                return _pl[0] <= _ss[i] <= _pl[1]
        picket_rail(B, pt, n, zs, w / 2 - 0.05, skip=sk)
        picket_rail(B, pt, n, zs, -(w / 2 - 0.05), skip=sk)
        s = path_len(path)
        nxt = 10.0
        side = 1
        for i in range(n):
            if s[i] >= nxt and i < n - 2:
                lamp_cone(B, tuple(pt(i, side * (w / 2 - 0.55), zs[i])))
                side = -side
                nxt += 24.0
    # Y bents: twin raking concrete columns from the lake bed (or the lawn) to a cap under the girder, every ~30 m
    for key, (path, zs, pt, n, w, T) in parts.items():
        s = path_len(path)
        step = 30.0 if key != "helix" else 12.0
        nxt = step * 0.5
        for i in range(1, n - 1):
            if s[i] < nxt or zs[i] < 1.6:
                continue
            nxt += step
            p = (path[i][0] + C[0], path[i][1] + C[1])
            zb = Z_BED if wet(p) else 0.0
            top = zs[i] - 0.35 - (1.7 if key == "span" else 1.0)
            cap = pt(i, 0, top)
            for sgn in (-1, 1):
                foot = pt(i, sgn * 0.6, zb)
                head = pt(i, sgn * 1.6, top - 0.6)
                B.tube([tuple(foot), tuple(head)], [0.55, 0.45], "M_Concrete", sides=8, cap0=False, cap1=True)
            B.box(tuple(cap - Vector((0, 0, 0.35))), (1.4, 4.2, 0.7), "M_Concrete", rot=Matrix.Rotation(math.atan2(-T[i][0], T[i][1]), 3, "Z"))
    export("LM_ATX_PflugerBridge", [B.finish("LM_ATX_PflugerBridge")],
           {"origin": "helix centre, plan frame (Blender X = plan east); z = Unreal metres", "deck_m": WD, "deck_height_m": HD,
            "helix_radius_m": round(R, 2), "span_len_m": round(Ls, 1)})
    place("LM_ATX_PflugerBridge", C, 0.0, z=0.0, collision="complex", note="drivable walkway with helix")
    LAYOUT.setdefault("sites", {})["pfluger"] = {"origin": [round(C[0], 2), round(C[1], 2)], "helix_r": round(R, 2),
                                                 "keepout_plan": [[round(p[0], 1), round(p[1], 1)] for p in span[::4] + legp[::4]],
                                                 "drive_path": [[round(p[0], 1), round(p[1], 1), round(z, 2)] for p, z in list(zip(hel, zs_hel))[::4] + list(zip(span, zs_span))[1::3]]}


# ================================================================== statues: stylised bronze figures (see the credits notes)
def loft(B, secs, m, segs=12, cap0=True, cap1=True):
    """Lofted solid through elliptical sections secs = [(cx, cy, z, rx, ry[, yaw_deg])] (bottom to top)."""
    P = []
    for k in range(segs):
        a = 2 * math.pi * k / segs
        col = []
        for sec in secs:
            cx, cy, z, rx, ry = sec[:5]
            yw = math.radians(sec[5]) if len(sec) > 5 else 0.0
            x, y = rx * math.cos(a), ry * math.sin(a)
            col.append(Vector((cx + x * math.cos(yw) - y * math.sin(yw), cy + x * math.sin(yw) + y * math.cos(yw), z)))
        P.append(col)
    VV = B.grid(P, m, smooth=True, close_u=True)
    if cap0:
        B._poly([VV[k][0] for k in range(segs)][::-1], m, None, True)
    if cap1:
        B._poly([VV[k][len(secs) - 1] for k in range(segs)], m, None, True)


def limb(B, pts, radii, m, sides=8):
    B.tube([tuple(p) for p in pts], list(radii), m, sides=sides, cap0=True, cap1=True)


def boot(B, x, y, z, yaw, m, s=1.0):
    R = Matrix.Rotation(math.radians(yaw), 3, "Z")
    T = lambda v: tuple(Vector((x, y, z)) + R @ (Vector(v) * s))
    loft(B, [(*T((0.03, 0, 0))[:2], z, 0.15 * s, 0.065 * s), (*T((0.04, 0, 0))[:2], z + 0.09 * s, 0.15 * s, 0.065 * s),
             (*T((-0.02, 0, 0))[:2], z + 0.16 * s, 0.075 * s, 0.065 * s), (*T((-0.02, 0, 0))[:2], z + 0.45 * s, 0.075 * s, 0.07 * s)],
         m, segs=10)


def hand(B, p, m, s=1.0):
    B.ellipsoid(tuple(p), (0.055 * s, 0.045 * s, 0.085 * s), m, segs=8, rings=5)


def guitar(B, base, axis, up, m, scale=1.0, acoustic=True):
    """A guitar: body (two lobes) extruded 0.1 m, neck and headstock. base = bottom of the body; axis = body->head
    direction; up = the face normal."""
    a = Vector(axis).normalized()
    u = Vector(up).normalized()
    side = a.cross(u).normalized()
    o = Vector(base)
    pts = []
    for k in range(28):
        t = 2 * math.pi * k / 28
        # waisted outline: lower bout r 0.2, upper 0.15
        y = 0.24 + 0.24 * math.cos(t) * 1.0
        r = (0.2 if math.cos(t) < 0.2 else 0.15) * (1.0 - 0.18 * math.exp(-((y - 0.3) / 0.06) ** 2))
        pts.append((r * math.sin(t) * scale, (0.25 - 0.25 * math.cos(t)) * scale))
    B.prism(tuple(o + u * 0.05 * scale), tuple(side), tuple(a), pts[::-1], 0.1 * scale, m)
    B.beam(tuple(o + a * 0.45 * scale), tuple(o + a * 1.0 * scale), 0.05 * scale, 0.04 * scale, m, up=tuple(u))
    B.box(tuple(o + a * 1.08 * scale), (0.09 * scale, 0.16 * scale, 0.03 * scale), m,
          rot=Matrix((side, a, u)).transposed())


def srv_statue():
    """Stevie Ray Vaughan (Ralph Helmick, 1993, Auditorium Shores): the bronze bluesman in his flat-brimmed hat and
    poncho, guitar held by the neck with its body at his boots, on a low limestone plinth with his bronze "shadow" laid
    on top; the decomposed-granite plaza and the curved limestone seat wall on the lake side. The figure faces -Y, the
    lake is behind (+Y). Origin: plinth centre at grade. Proportions from the reference photos (~2.6 m figure)."""
    B = Builder()
    br = "M_BronzeDark"
    # plaza and seat wall
    B.lathe([(0.0, 0.02), (8.0, 0.02), (8.0, 0.04), (0.0, 0.05)], "M_Gravel", segs=40, smooth=False)
    for k in range(17):
        a0 = math.radians(-10 + 200 * k / 17)
        a1 = math.radians(-10 + 200 * (k + 1) / 17)
        for r0, r1, z in ((7.6, 8.1, 0.5),):
            q = [(r0 * math.cos(a0), r0 * math.sin(a0)), (r1 * math.cos(a0), r1 * math.sin(a0)), (r1 * math.cos(a1), r1 * math.sin(a1)), (r0 * math.cos(a1), r0 * math.sin(a1))]
            B.prism((0, 0, 0), (1, 0, 0), (0, 1, 0), q[::-1], -z, "M_Limestone")
    # plinth with the shadow plate
    B.boxmm((-2.0, -1.0, 0.0), (2.0, 1.0, 0.5), "M_Limestone")
    shadow = [(-1.45, 0.25), (-0.6, 0.18), (-0.45, 0.45), (-0.2, 0.42), (-0.15, 0.2), (0.2, 0.15), (0.35, 0.3), (0.7, 0.32), (0.75, 0.12),
              (1.05, 0.1), (1.2, -0.05), (0.75, -0.12), (0.7, -0.3), (0.35, -0.28), (0.15, -0.15), (-0.2, -0.2), (-0.6, -0.12), (-1.45, -0.1)]
    B.prism((0, 0, 0.55), (1, 0, 0), (0, 1, 0), [(x - 0.3, y - 0.45) for x, y in shadow], -0.02, br)
    z0 = 0.55
    # boots apart, legs hidden by the poncho down to the knees
    boot(B, -0.16, -0.05, z0, -100, br, 1.15)
    boot(B, 0.16, 0.02, z0, -80, br, 1.15)
    for sx in (-0.15, 0.15):
        limb(B, [(sx, 0.0, z0 + 0.45), (sx * 0.9, 0.0, z0 + 0.9)], (0.09, 0.1), br)
    # poncho: draped from broad shoulders, hem lower at the back and on the guitar side, arms under it; the forearms come
    # out at the front (right hand with a flower) and at the left side (hand on the guitar neck)
    P = []
    nseg = 20
    rows = ((0.78, 0.50, 0.40), (0.95, 0.47, 0.38), (1.25, 0.43, 0.33), (1.55, 0.40, 0.29), (1.78, 0.38, 0.25), (1.92, 0.33, 0.2),
            (1.99, 0.2, 0.13), (2.02, 0.11, 0.09))
    for k in range(nseg):
        a_ = 2 * math.pi * k / nseg
        ca, sa = math.cos(a_), math.sin(a_)
        col = []
        for j, (z, rx, ry) in enumerate(rows):
            zz = z
            if j == 0:      # uneven hem: higher at the front (-Y), lower at the back and on the left (+X)
                zz = z - 0.12 * sa - 0.08 * max(0.0, ca)
            fold = 1.0 + 0.05 * math.sin(5 * a_ + j) * (1.0 if j < 4 else 0.3)
            col.append(Vector((rx * ca * fold, 0.02 + ry * sa * fold, z0 + zz)))
        P.append(col)
    VV = B.grid(P, br, smooth=True, close_u=True)
    B._poly([VV[k][0] for k in range(nseg)][::-1], br, None, True)
    limb(B, [(0.36, 0.02, z0 + 1.45), (0.44, -0.02, z0 + 1.28), (0.4, -0.06, z0 + 1.16)], (0.075, 0.07, 0.065), br)     # left forearm
    hand(B, (0.4, -0.08, z0 + 1.1), br, 1.1)
    limb(B, [(-0.2, -0.28, z0 + 1.38), (-0.26, -0.42, z0 + 1.3), (-0.3, -0.5, z0 + 1.26)], (0.075, 0.07, 0.065), br)    # right forearm
    hand(B, (-0.31, -0.55, z0 + 1.25), br, 1.1)
    B.ellipsoid((-0.31, -0.6, z0 + 1.32), (0.05, 0.05, 0.06), "M_ClothRed", segs=6, rings=4)                         # the fans' flower
    # neck, head, long hair, the flat-brimmed hat
    limb(B, [(0, 0, z0 + 2.0), (0, -0.01, z0 + 2.1)], (0.075, 0.07), br)
    B.ellipsoid((0.0, -0.02, z0 + 2.22), (0.1, 0.11, 0.13), br, segs=10, rings=6)
    loft(B, [(0.0, 0.04, z0 + 2.04, 0.12, 0.08), (0.0, 0.04, z0 + 2.2, 0.12, 0.09)], br, segs=10)
    B.lathe([(0.0, z0 + 2.3), (0.36, z0 + 2.29), (0.37, z0 + 2.31), (0.13, z0 + 2.33), (0.12, z0 + 2.46), (0.0, z0 + 2.47)], br, segs=20,
            center=(0.0, -0.02, 0))
    # the guitar: held by the neck in the left hand, body resting by the boots behind the left leg
    guitar(B, (0.46, 0.18, z0 + 0.02), (-0.04, -0.2, 1.0), (1.0, 0.25, 0.0), br, scale=1.05)
    export("LM_ATX_SRVStatue", [B.finish("LM_ATX_SRVStatue")], {"origin": "plinth centre at grade; the figure faces -Y", "figure_m": 2.47})


def eberly_statue():
    """Angelina Eberly (Pat Oliphant, 2004, Congress Ave at 6th St): the innkeeper of the 1842 Archive War in a wide
    stance, reaching with a slow match to the touch hole of a cannon on its spoked carriage, on a low round red-granite
    base. Faces -Y (the cannon's muzzle points -Y too). Origin: base centre at the sidewalk."""
    B = Builder()
    br = "M_BronzeDark"
    B.lathe([(0.0, 0.0), (2.5, 0.0), (2.5, 0.32), (2.42, 0.4), (0.0, 0.4)], "M_GranitePolished", segs=36, smooth=False)
    z0 = 0.4
    # cannon: barrel along -Y on a trail carriage, two wheels
    cx, cy = -0.75, -0.4
    for sx in (-0.55, 0.55):
        B.torus((cx + sx, cy - 0.3, z0 + 0.66), 0.64, 0.045, br, segs=32, sides=6, mtx=Matrix.Rotation(math.pi / 2, 3, "Y"))
        B.lathe([(0.0, -0.12), (0.12, -0.1), (0.12, 0.1), (0.0, 0.12)], br, segs=10, center=(cx + sx, cy - 0.3, z0 + 0.66),
                mtx=Matrix.Rotation(math.pi / 2, 3, "Y"))
        for k in range(12):
            a = 2 * math.pi * k / 12
            B.rod((cx + sx, cy - 0.3, z0 + 0.66), (cx + sx, cy - 0.3 + 0.62 * math.cos(a), z0 + 0.66 + 0.62 * math.sin(a)), 0.022, br, sides=4)
    B.rod((cx - 0.6, cy - 0.3, z0 + 0.66), (cx + 0.6, cy - 0.3, z0 + 0.66), 0.05, br, sides=6)
    B.beam((cx, cy - 0.15, z0 + 0.66), (cx, cy + 1.6, z0 + 0.05), 0.3, 0.2, br)
    B.lathe([(0.15, 0.0), (0.13, 1.1), (0.1, 1.55), (0.14, 1.6), (0.14, 1.65), (0.0, 1.65)], br, segs=14,
            center=(cx, cy - 0.3 + 0.55, z0 + 0.85), mtx=Matrix.Rotation(math.pi / 2, 3, "X"))
    B.ellipsoid((cx, cy + 0.4, z0 + 0.85), (0.16, 0.16, 0.16), br, segs=10, rings=6)
    # the figure: stout, leaning toward the cannon (-X), skirt flaring back (+X)
    fx, fy = 0.75, 0.15
    for sx, lean in ((-0.35, -0.2), (0.35, 0.15)):
        limb(B, [(fx + sx * 1.2, fy, z0), (fx + sx * 0.8, fy, z0 + 0.45), (fx + sx * 0.4, fy, z0 + 0.85)], (0.07, 0.08, 0.1), br)
    loft(B, [(fx + 0.1, fy, z0 + 0.35, 0.55, 0.3, 0), (fx + 0.05, fy, z0 + 0.7, 0.42, 0.28, 0), (fx - 0.05, fy, z0 + 1.05, 0.28, 0.2, 0),
             (fx - 0.15, fy, z0 + 1.45, 0.25, 0.19, 0), (fx - 0.25, fy, z0 + 1.7, 0.21, 0.16, 0)], br, segs=14)
    B.ellipsoid((fx - 0.15, fy - 0.12, z0 + 1.42), (0.17, 0.12, 0.11), br, segs=10, rings=6)
    B.ellipsoid((fx - 0.32, fy, z0 + 1.9), (0.11, 0.1, 0.13), br, segs=10, rings=6)
    B.ellipsoid((fx - 0.28, fy + 0.03, z0 + 1.98), (0.12, 0.12, 0.09), br, segs=10, rings=6)     # hair bun
    limb(B, [(fx - 0.35, fy - 0.15, z0 + 1.68), (fx - 0.75, fy - 0.2, z0 + 1.62), (fx - 1.1, fy - 0.25, z0 + 1.52)], (0.07, 0.06, 0.05), br)
    hand(B, (fx - 1.16, fy - 0.25, z0 + 1.5), br)
    B.rod((fx - 1.16, fy - 0.25, z0 + 1.5), (cx + 0.05, cy + 0.38, z0 + 1.05), 0.012, br, sides=4)
    limb(B, [(fx - 0.15, fy + 0.15, z0 + 1.68), (fx + 0.2, fy + 0.3, z0 + 1.5), (fx + 0.5, fy + 0.35, z0 + 1.4)], (0.07, 0.06, 0.05), br)
    hand(B, (fx + 0.56, fy + 0.35, z0 + 1.38), br)
    export("LM_ATX_EberlyStatue", [B.finish("LM_ATX_EberlyStatue")], {"origin": "base centre at the sidewalk; faces -Y"})


def statues():
    srv_statue(); reset(); eberly_statue(); reset(); willie_statue()


# ================================================================== the Texas Capitol's other monuments (TSPB Capitol Monument Guide)
BR = "M_Bronze"


def bfig(B, x, y, z, yaw=0.0, h=1.9, pose="stand", dress=False, hat=None, m=BR):
    """A bronze figure facing -Y rotated by yaw (deg): person() in bronze, optionally with a long skirt and a hat."""
    T, top = person(B, x, y, z, yaw=yaw - 90.0, pose=pose, h=h, cloth=m, skin=m, legs=m)
    s = h / 1.75
    if dress:
        loft(B, [(*T(0.0, 0.0, 0.02)[:2], z + 0.02, 0.36 * s, 0.34 * s), (*T(0.0, 0.0, 0.5)[:2], z + 0.5 * s, 0.27 * s, 0.25 * s),
                 (*T(0.0, 0.0, 0.95)[:2], z + 0.95 * s, 0.17 * s, 0.14 * s)], m, segs=12)
    if hat == "brim":
        hp = T(0.01, 0, top + 0.27)
        B.lathe([(0.0, hp[2]), (0.24 * s, hp[2]), (0.1 * s, hp[2] + 0.02), (0.1 * s, hp[2] + 0.12 * s), (0.0, hp[2] + 0.12 * s)], m, segs=12, center=(hp[0], hp[1], 0))
    elif hat == "bonnet":
        B.ellipsoid(T(-0.02, 0, top + 0.2), (0.14 * s, 0.13 * s, 0.13 * s), m, segs=8, rings=5)
    return T, top


def ped(B, w, d, h, m="M_Granite", x=0.0, y=0.0, z=0.0, taper=0.0, cap=True):
    """Pedestal block w x d x h (optionally tapering by `taper` per side) with a thin cap."""
    if taper:
        B.sweep([(-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)], m,
                [(1, 1, z, x, y), (1 - 2 * taper / w, 1 - 2 * taper / d, z + h, x, y), (0, 0, z + h, x, y)], smooth=False)
    else:
        B.boxmm((x - w / 2, y - d / 2, z), (x + w / 2, y + d / 2, z + h), m)
    if cap:
        B.boxmm((x - w / 2 - 0.06, y - d / 2 - 0.06, z + h), (x + w / 2 + 0.06, y + d / 2 + 0.06, z + h + 0.12), m)
    return z + h + (0.12 if cap else 0.0)


def plaque(B, x, y, z, w=0.6, h=0.4, yaw=0.0):
    B.box((x, y, z), (w, 0.03, h), "M_BronzeDark", rot=Matrix.Rotation(math.radians(yaw), 3, "Z"))


def longhorn(B, x, y, z, yaw, s=1.0, m=BR):
    """A longhorn (body, legs, head and its wide horns), facing local +X rotated by yaw."""
    R = Matrix.Rotation(math.radians(yaw), 3, "Z")
    T = lambda v: tuple(Vector((x, y, z)) + R @ (Vector(v) * s))
    B.ellipsoid(T((0, 0, 1.15)), (0.95 * s, 0.38 * s, 0.42 * s), m, segs=10, rings=6, rot=R)
    for dx in (-0.6, 0.6):
        for dy in (-0.2, 0.2):
            limb(B, [T((dx, dy, 0.0)), T((dx, dy, 0.85))], (0.07 * s, 0.09 * s), m, sides=6)
    B.ellipsoid(T((1.1, 0, 1.2)), (0.32 * s, 0.17 * s, 0.2 * s), m, segs=8, rings=5, rot=R)
    B.tube([T((1.05, -0.95, 1.55)), T((1.05, -0.45, 1.36)), T((1.05, 0, 1.38)), T((1.05, 0.45, 1.36)), T((1.05, 0.95, 1.55))],
           [0.02 * s, 0.05 * s, 0.06 * s, 0.05 * s, 0.02 * s], m, sides=6)


def horse_rider(B, x, y, z, yaw, m=BR, s=1.0, rider=True):
    R = Matrix.Rotation(math.radians(yaw), 3, "Z")
    T = lambda v: tuple(Vector((x, y, z)) + R @ (Vector(v) * s))
    B.ellipsoid(T((0, 0, 1.35)), (0.85 * s, 0.32 * s, 0.38 * s), m, segs=10, rings=6, rot=R)
    for dx in (-0.55, 0.6):
        for dy in (-0.16, 0.16):
            limb(B, [T((dx, dy, 0.0)), T((dx + 0.05, dy, 0.6)), T((dx, dy, 1.1))], (0.06 * s, 0.07 * s, 0.1 * s), m, sides=6)
    limb(B, [T((0.7, 0, 1.5)), T((1.0, 0, 1.95))], (0.2 * s, 0.14 * s), m)
    B.ellipsoid(T((1.12, 0, 1.95)), (0.3 * s, 0.11 * s, 0.13 * s), m, segs=8, rings=5, rot=Matrix.Rotation(math.radians(yaw), 3, "Z") @ Matrix.Rotation(-0.6, 3, "Y"))
    limb(B, [T((-0.85, 0, 1.45)), T((-1.05, 0, 0.9))], (0.08 * s, 0.04 * s), m, sides=5)
    if rider:
        bfig(B, *T((-0.05, 0, 1.55)), yaw=yaw + 90, h=1.75 * s, pose="sit", hat="brim", m=m)


def cap_tejano():
    """Tejano Monument (2012): a rough pink-granite outcrop 12 m long with a tall rock pylon, a vaquero on horseback,
    a longhorn cow and calf, a Spanish explorer on the pylon, a ranching family, and bronze plaques. Faces -Y."""
    B = Builder()
    rnd = random.Random(12)
    rocks = [(-4.5, 0.4, 3.0, 2.6, 0.9), (-1.5, 0.2, 3.4, 3.2, 1.2), (1.8, 0.3, 3.0, 2.8, 1.1), (4.6, 0.6, 2.8, 2.6, 3.6), (0.2, 1.4, 6.0, 1.6, 0.8)]
    for cx, cy, w, d, h in rocks:
        B.sweep([(-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)], "M_GraniteRough",
                [(1.0, 1.0, 0.0, cx, cy), (0.96, 0.94, h * 0.7, cx + rnd.uniform(-0.1, 0.1), cy), (0.85, 0.8, h, cx, cy), (0.0, 0.0, h + 0.15, cx, cy)], smooth=False)
    horse_rider(B, -1.4, 0.3, 1.2, 15.0)
    longhorn(B, 1.6, 0.0, 1.1, -170.0, 1.0)
    longhorn(B, 2.6, -0.6, 1.1, 160.0, 0.6)
    bfig(B, 4.6, 0.6, 3.6, yaw=0, h=2.1, hat="brim")
    for k, (fx, fy, h, dr) in enumerate(((-5.3, -1.7, 1.85, False), (-4.6, -1.8, 1.7, True), (-3.9, -1.6, 1.15, False))):
        bfig(B, fx, fy, 0.0, yaw=10, h=h, dress=dr)
    for k in range(5):
        plaque(B, -2.4 + k * 1.2, -1.42, 0.55, 0.9, 0.7)
    export("LM_ATX_Cap_Tejano", [B.finish("LM_ATX_Cap_Tejano")], {"origin": "centre at grade; faces -Y"})


def cap_african_american():
    """Texas African American History Memorial (2016): a curved bronze relief wall on a granite base and, at its centre,
    a tall drum pedestal (relief band, EMANCIPATION ribbon) carrying a man raising a document and a woman. Faces -Y."""
    B = Builder()
    R0, a0, a1 = 9.0, math.radians(235), math.radians(305)
    n = 14
    for k in range(n):
        aa, ab = a0 + (a1 - a0) * k / n, a0 + (a1 - a0) * (k + 1) / n
        for r0, r1, z0, z1, m in ((R0 - 0.5, R0 + 0.5, 0.0, 0.6, "M_Granite"), (R0 - 0.25, R0 + 0.25, 0.6, 3.0, "M_BronzeDark")):
            q = [(r0 * math.cos(aa), r0 * math.sin(aa) + R0), (r1 * math.cos(aa), r1 * math.sin(aa) + R0), (r1 * math.cos(ab), r1 * math.sin(ab) + R0),
                 (r0 * math.cos(ab), r0 * math.sin(ab) + R0)]
            B.prism((0, 0, z0), (1, 0, 0), (0, 1, 0), q[::-1], -(z1 - z0), m)
        # relief figures standing out of the wall's face
        am = (aa + ab) / 2
        for j in range(2):
            px, py = (R0 - 0.3) * math.cos(am + (j - 0.5) * 0.03), (R0 - 0.3) * math.sin(am + (j - 0.5) * 0.03) + R0
            B.box((px, py, 1.55 + 0.3 * j), (0.35, 0.22, 1.1), BR, rot=Matrix.Rotation(am, 3, "Z"))
    B.lathe([(0.0, 0.0), (2.0, 0.0), (2.0, 0.6), (1.7, 0.75), (1.6, 4.2), (1.75, 4.35), (1.75, 4.6), (0.0, 4.6)], "M_BronzeDark", segs=28, center=(0, -0.6, 0))
    B.lathe([(1.62, 3.3), (1.85, 3.35), (1.85, 3.75), (1.62, 3.8)], BR, segs=28, center=(0, -0.6, 0))
    T, top = bfig(B, -0.35, -0.6, 4.6, yaw=0, h=2.4)
    arms(B, T, top, [(0.15, -0.3, top + 0.55), (0.1, 0.25, top - 0.5)], cloth=BR, skin=BR, s=1.3)
    B.box(T(0.15, -0.3, top + 0.85), (0.04, 0.4, 0.5), BR)
    bfig(B, 0.45, -0.55, 4.6, yaw=-10, h=2.25, dress=True)
    export("LM_ATX_Cap_AfricanAmerican", [B.finish("LM_ATX_Cap_AfricanAmerican")], {"origin": "drum centre + 0.6 m back, at grade; faces -Y"})


def cap_peace_officers():
    """Texas Peace Officers' Memorial (1999): a round dark plaza, a curved black granite wall of names and the twin
    black granite shafts at its centre. Faces -Y (the wall is behind, +Y)."""
    B = Builder()
    B.lathe([(0.0, 0.0), (7.2, 0.0), (7.2, 0.06), (0.0, 0.08)], "M_GraniteGrey", segs=40, smooth=False)
    B.lathe([(0.0, 0.08), (2.4, 0.08), (2.4, 0.35), (2.2, 0.35), (2.2, 0.2), (0.0, 0.2)], "M_GraniteBlack", segs=32, smooth=False)
    n = 18
    for k in range(n):
        aa, ab = math.radians(10 + 160 * k / n), math.radians(10 + 160 * (k + 1) / n)
        q = [(6.3 * math.cos(aa), 6.3 * math.sin(aa)), (6.8 * math.cos(aa), 6.8 * math.sin(aa)), (6.8 * math.cos(ab), 6.8 * math.sin(ab)), (6.3 * math.cos(ab), 6.3 * math.sin(ab))]
        B.prism((0, 0, 0), (1, 0, 0), (0, 1, 0), q[::-1], -2.0, "M_GraniteBlack")
    for dx in (-0.35, 0.35):
        B.sweep([(-0.18, -0.45), (0.18, -0.45), (0.18, 0.45), (-0.18, 0.45)], "M_GraniteBlack",
                [(1, 1, 0.35, dx, 2.4), (0.75, 0.8, 6.0, dx, 2.4), (0.0, 0.0, 6.4, dx, 2.4)], smooth=False)
    export("LM_ATX_Cap_PeaceOfficers", [B.finish("LM_ATX_Cap_PeaceOfficers")], {"origin": "plaza centre at grade; faces -Y"})


def cap_vietnam():
    """Texas Vietnam Veterans Monument (2014): five bronze soldiers on an octagonal bronze-relief plinth on granite. Faces -Y."""
    B = Builder()
    B.lathe([(0.0, 0.0), (2.6, 0.0), (2.6, 0.9), (0.0, 0.9)], "M_Granite", segs=8, smooth=False)
    B.lathe([(0.0, 0.9), (2.2, 0.9), (2.2, 1.95), (2.0, 2.1), (0.0, 2.1)], "M_BronzeDark", segs=8, smooth=False)
    z = 2.1
    for (x, y, yaw, pose, h) in ((0.0, 0.3, 0, "stand", 2.0), (-0.9, -0.2, 20, "kneel", 2.0), (0.9, -0.3, -25, "sit", 1.95),
                                 (-0.5, 0.9, 160, "stand", 1.95), (0.7, 0.8, -150, "kneel", 2.0)):
        T, top = bfig(B, x, y, z, yaw=yaw, h=h * 1.1, pose=pose, hat="bonnet")
        B.rod(T(0.3, -0.2, top - 0.4), T(0.3, 0.6, top - 0.55), 0.03, BR, sides=5)
    B.box((0, 0.2, z + 0.25), (1.2, 0.8, 0.5), "M_BronzeDark")
    export("LM_ATX_Cap_Vietnam", [B.finish("LM_ATX_Cap_Vietnam")], {"origin": "centre at grade; faces -Y"})


def cap_disabled_vets():
    """Disabled Veterans monument: a granite stele with a rounded centre tablet and two lower side tablets. Faces -Y."""
    B = Builder()
    B.boxmm((-2.3, -0.6, 0.0), (2.3, 0.6, 0.3), "M_GraniteGrey")
    B.boxmm((-0.8, -0.22, 0.3), (0.8, 0.22, 2.1), "M_Granite")
    B.ellipsoid((0, 0, 2.1), (0.8, 0.22, 0.35), "M_Granite", segs=16, rings=6, half=True)
    for sx in (-1.45, 1.45):
        B.boxmm((sx - 0.65, -0.2, 0.3), (sx + 0.65, 0.2, 1.3), "M_Granite")
    plaque(B, 0.0, -0.24, 1.4, 0.9, 0.9)
    export("LM_ATX_Cap_DisabledVets", [B.finish("LM_ATX_Cap_DisabledVets")], {"origin": "centre at grade; faces -Y"})


def lady_liberty(B, x, y, z, h=2.6, m="M_Verdigris"):
    s = h / 2.6
    loft(B, [(x, y, z, 0.42 * s, 0.36 * s), (x, y, z + 0.6 * s, 0.34 * s, 0.3 * s), (x, y, z + 1.4 * s, 0.27 * s, 0.22 * s),
             (x, y, z + 1.85 * s, 0.25 * s, 0.18 * s), (x, y, z + 2.0 * s, 0.12 * s, 0.1 * s)], m, segs=12)
    B.ellipsoid((x, y, z + 2.14 * s), (0.1 * s, 0.11 * s, 0.13 * s), m, segs=8, rings=5)
    for k in range(7):
        a = math.radians(-60 + 120 * k / 6) - math.pi / 2
        B.rod((x, y, z + 2.22 * s), (x + 0.28 * s * math.cos(a), y + 0.28 * s * math.sin(a) * 0.4, z + 2.34 * s + 0.12 * s * math.cos(math.radians(-60 + 120 * k / 6))), 0.015 * s, m, sides=3)
    limb(B, [(x + 0.2 * s, y, z + 1.85 * s), (x + 0.3 * s, y - 0.05 * s, z + 2.3 * s), (x + 0.32 * s, y - 0.05 * s, z + 2.75 * s)], (0.06 * s, 0.05 * s, 0.045 * s), m)
    B.lathe([(0.0, z + 2.75 * s), (0.06 * s, z + 2.78 * s), (0.08 * s, z + 2.95 * s), (0.0, z + 2.95 * s)], m, segs=8, center=(x + 0.32 * s, y - 0.05 * s, 0))
    B.ellipsoid((x + 0.32 * s, y - 0.05 * s, z + 3.02 * s), (0.06 * s, 0.06 * s, 0.1 * s), "M_Gold", segs=8, rings=4)
    limb(B, [(x - 0.2 * s, y, z + 1.8 * s), (x - 0.28 * s, y - 0.15 * s, z + 1.45 * s), (x - 0.18 * s, y - 0.22 * s, z + 1.35 * s)], (0.055 * s, 0.05 * s, 0.045 * s), m)
    B.box((x - 0.22 * s, y - 0.2 * s, z + 1.45 * s), (0.08 * s, 0.25 * s, 0.38 * s), m, rot=Matrix.Rotation(0.3, 3, "X"))


def cap_liberty():
    """Statue of Liberty replica (Boy Scouts of America, 1951): a 2.6 m verdigris copper statue on a limestone-block
    pedestal on a pink-granite base. Faces -Y."""
    B = Builder()
    z = ped(B, 2.8, 2.8, 0.9, "M_Granite", taper=0.4)
    for k in range(6):
        B.boxmm((-0.7 + 0.02 * k, -0.7 + 0.02 * k, z + 0.38 * k), (0.7 - 0.02 * k, 0.7 - 0.02 * k, z + 0.38 * k + 0.36), "M_Limestone")
    z += 2.28
    B.boxmm((-0.62, -0.62, z), (0.62, 0.62, z + 0.15), "M_Granite")
    lady_liberty(B, 0.0, 0.0, z + 0.15)
    plaque(B, 0.0, -1.18, 0.55, 0.6, 0.4)
    export("LM_ATX_Cap_Liberty", [B.finish("LM_ATX_Cap_Liberty")], {"origin": "centre at grade; faces -Y"})


def cap_ten_commandments():
    """The Ten Commandments monolith (Fraternal Order of Eagles, 1961): a red granite tablet with a double-arched top on
    a base. Faces -Y."""
    B = Builder()
    B.boxmm((-0.85, -0.4, 0.0), (0.85, 0.4, 0.32), "M_GranitePolished")
    pts = [(-0.55, 0.32), (0.55, 0.32), (0.55, 1.62)]
    for k in range(9):
        a = math.pi * k / 8
        pts.append((0.275 + 0.275 * math.cos(a), 1.62 + 0.2 * math.sin(a)))
    for k in range(1, 9):
        a = math.pi * k / 8
        pts.append((-0.275 + 0.275 * math.cos(a), 1.62 + 0.2 * math.sin(a)))
    B.prism((0, 0.15, 0), (1, 0, 0), (0, 0, 1), pts, 0.3, "M_GranitePolished")
    export("LM_ATX_Cap_TenCommandments", [B.finish("LM_ATX_Cap_TenCommandments")], {"origin": "centre at grade; faces -Y"})


def cap_wwii():
    """Texas World War II Memorial: a grey granite pylon with an opening holding a bronze wreath, on a pink granite die
    with a plaque. Faces -Y."""
    B = Builder()
    B.boxmm((-0.9, -0.75, 0.0), (0.9, 0.75, 0.3), "M_Granite")
    B.boxmm((-0.6, -0.45, 0.3), (0.6, 0.45, 1.7), "M_Granite")
    plaque(B, 0.0, -0.47, 1.25, 0.55, 0.45)
    B.boxmm((-0.55, -0.3, 1.7), (0.55, 0.3, 2.3), "M_GraniteGrey")
    for x0, x1 in ((-0.55, -0.32), (0.32, 0.55)):
        B.boxmm((x0, -0.3, 2.3), (x1, 0.3, 4.6), "M_GraniteGrey")
    B.boxmm((-0.55, -0.3, 4.6), (0.55, 0.3, 5.0), "M_GraniteGrey")
    B.torus((0, -0.32, 3.4), 0.36, 0.07, BR, segs=24, sides=6, mtx=Matrix.Rotation(math.pi / 2, 3, "X"))
    B.rod((0, -0.05, 2.3), (0, -0.05, 4.6), 0.04, BR, sides=5)
    export("LM_ATX_Cap_WWII", [B.finish("LM_ATX_Cap_WWII")], {"origin": "centre at grade; faces -Y"})


def cap_pioneer_woman():
    """Tribute to Texas Pioneer Woman (1998): a woman in a bonnet and long dress, a child at her side, on a granite
    pedestal. Faces -Y."""
    B = Builder()
    z = ped(B, 1.3, 1.3, 1.6, "M_Granite", taper=0.12)
    plaque(B, 0.0, -0.64, 1.0, 0.6, 0.45)
    T, top = bfig(B, 0.0, 0.0, z, yaw=0, h=2.15, dress=True, hat="bonnet")
    bfig(B, 0.35, -0.15, z, yaw=-20, h=1.05)
    export("LM_ATX_Cap_PioneerWoman", [B.finish("LM_ATX_Cap_PioneerWoman")], {"origin": "centre at grade; faces -Y"})


def cap_children():
    """Tribute to Texas Children (1999): bronze children at play on the lawn, a low plaque. Faces -Y."""
    B = Builder()
    rnd = random.Random(31)
    for k, (x, y, yaw, h) in enumerate(((-2.2, 0.4, 15, 1.25), (-0.9, -0.3, -10, 1.15), (0.4, 0.2, 30, 1.35), (1.6, -0.4, -25, 1.05), (2.6, 0.5, 5, 1.2))):
        T, top = bfig(B, x, y, 0.0, yaw=yaw, h=h, dress=(k % 2 == 1))
        arms(B, T, top, [(0.1, -0.35, top + rnd.uniform(-0.3, 0.3)), (0.1, 0.35, top + rnd.uniform(-0.3, 0.3))], cloth=BR, skin=BR, s=0.7)
    B.boxmm((-0.5, -1.4, 0.0), (0.5, -1.0, 0.35), "M_GraniteGrey")
    export("LM_ATX_Cap_Children", [B.finish("LM_ATX_Cap_Children")], {"origin": "group centre at grade; faces -Y"})


def cap_soldier(name, h=2.1, ped_h=2.2, doc=""):
    """A bronze soldier with a rifle on a granite pedestal (the Texas National Guard monument, generic form)."""
    B = Builder()
    z = ped(B, 1.5, 1.5, ped_h, "M_Granite", taper=0.1)
    B.boxmm((-0.95, -0.95, 0.0), (0.95, 0.95, 0.35), "M_Granite")
    plaque(B, 0.0, -0.74, ped_h * 0.6, 0.6, 0.5)
    T, top = bfig(B, 0.0, 0.0, z, yaw=0, h=h, hat="brim")
    arms(B, T, top, [(0.25, -0.2, top - 0.45), (0.2, 0.25, top - 0.2)], cloth=BR, skin=BR, s=1.2)
    B.rod(T(0.28, -0.35, top - 0.8), T(0.25, 0.4, top + 0.1), 0.035, BR, sides=5)
    export(name, [B.finish(name)], {"origin": "centre at grade; faces -Y", "note": doc})


def cap_pearl_harbor():
    """Pearl Harbor memorial: a grey granite marker beside a bronze anchor. Faces -Y."""
    B = Builder()
    B.boxmm((-1.2, -0.5, 0.0), (1.2, 0.5, 0.25), "M_GraniteGrey")
    B.boxmm((-0.75, -0.18, 0.25), (0.75, 0.18, 1.45), "M_GraniteGrey")
    plaque(B, 0.0, -0.2, 0.9, 1.0, 0.7)
    ax = 1.0
    B.rod((ax, 0, 0.25), (ax, 0, 1.9), 0.06, "M_Iron", sides=6)
    B.rod((ax - 0.45, 0, 1.6), (ax + 0.45, 0, 1.6), 0.05, "M_Iron", sides=6)
    B.torus((ax, 0, 2.0), 0.12, 0.03, "M_Iron", segs=12, sides=4, mtx=Matrix.Rotation(math.pi / 2, 3, "X"))
    B.tube([(ax - 0.55, 0, 0.75), (ax - 0.35, 0, 0.4), (ax, 0, 0.3), (ax + 0.35, 0, 0.4), (ax + 0.55, 0, 0.75)], [0.05] * 5, "M_Iron", sides=6)
    export("LM_ATX_Cap_PearlHarbor", [B.finish("LM_ATX_Cap_PearlHarbor")], {"origin": "centre at grade; faces -Y"})


def capitol():
    for fn in (cap_tejano, cap_african_american, cap_peace_officers, cap_vietnam, cap_disabled_vets, cap_liberty, cap_ten_commandments,
               cap_wwii, cap_pioneer_woman, cap_children, cap_pearl_harbor):
        fn(); reset()
    cap_soldier("LM_ATX_Cap_NationalGuard", doc="Texas National Guard monument (generic soldier form)")


def willie_statue():
    """Willie Nelson (Clete Shields, 2012, at the Moody Theater on W 2nd St): the 8-ft bronze of Willie perched on a
    stump, bandana and braids, leaning over his guitar Trigger on his knee, on a dark polished stone plinth with a
    board-formed concrete wall and plaques behind. Faces -Y. Origin: plinth centre at grade."""
    B = Builder()
    br = "M_BronzeDark"
    B.boxmm((-1.3, -1.1, 0.0), (1.3, 1.1, 0.9), "M_GraniteBlack")
    B.boxmm((-1.8, 1.4, 0.0), (1.8, 1.9, 4.2), "M_ConcreteDark")
    for x, z, w, h in ((0.75, 2.8, 0.75, 0.5), (0.75, 1.7, 0.75, 1.1)):
        plaque(B, x, 1.38, z, w, h)
    z0 = 0.9
    B.lathe([(0.0, z0), (0.5, z0), (0.42, z0 + 0.15), (0.34, z0 + 0.9), (0.36, z0 + 1.0), (0.0, z0 + 1.02)], br, segs=12, center=(0.0, 0.15, 0),
            f=lambda th: 0.05 * math.sin(7 * th))                                                              # the stump
    s = 2.4 / 1.75
    zh = z0 + 1.0                                                                                              # seat
    for sx, lift in ((-0.17, 0.0), (0.17, 0.45)):
        knee = (sx * 1.3, -0.5, zh + 0.15 + lift)
        foot = (sx * 1.5, -0.55 + lift * 0.3, z0 + 0.05 + lift * 1.2)
        limb(B, [(sx, 0.1, zh + 0.05), knee, foot], (0.14, 0.12, 0.1), br)
        boot(B, foot[0], foot[1] - 0.05, foot[2] - 0.02, -90, br, 1.25)
    loft(B, [(0.0, 0.05, zh, 0.27, 0.2), (0.0, -0.02, zh + 0.45, 0.25, 0.17), (0.0, -0.1, zh + 0.8, 0.3, 0.19), (0.0, -0.12, zh + 0.95, 0.12, 0.1)], br, segs=12)
    limb(B, [(0.0, -0.13, zh + 0.95), (0.0, -0.18, zh + 1.05)], (0.08, 0.075), br)
    B.ellipsoid((0.0, -0.22, zh + 1.2), (0.12, 0.13, 0.15), br, segs=10, rings=6)
    B.ellipsoid((0.0, -0.2, zh + 1.3), (0.135, 0.14, 0.07), br, segs=10, rings=4)                                   # bandana
    for sx in (-0.11, 0.11):
        B.tube([(sx, -0.15, zh + 1.15), (sx * 1.2, -0.2, zh + 0.85), (sx * 1.1, -0.25, zh + 0.6)], [0.035, 0.03, 0.02], br, sides=5)   # braids
    g0 = Vector((-0.1, -0.62, zh + 0.25))
    guitar(B, tuple(g0), (0.85, 0.15, 0.5), (0.0, -1.0, 0.25), br, scale=1.15)
    limb(B, [(0.3, -0.12, zh + 0.85), (0.45, -0.45, zh + 0.6), (0.35, -0.7, zh + 0.65)], (0.08, 0.07, 0.06), br)
    hand(B, (0.33, -0.74, zh + 0.66), br, 1.3)
    limb(B, [(-0.3, -0.12, zh + 0.85), (-0.35, -0.45, zh + 0.6), (-0.05, -0.68, zh + 0.5)], (0.08, 0.07, 0.06), br)
    hand(B, (0.0, -0.72, zh + 0.5), br, 1.3)
    export("LM_ATX_WillieStatue", [B.finish("LM_ATX_WillieStatue")], {"origin": "plinth centre at grade; faces -Y"})


# ================================================================== layout: every placement, in plan metres
BLD = json.load(open(ROOT + "/Saved/Mashup/buildings_v3.json"))["buildings"]
CAPJ = json.load(open(ROOT + "/SourceArt/Landmarks/capitol/capitol.json"))["layout"]


def bld_rect(b, grow=0.0):
    a = math.radians(b["yaw"])
    c, s = math.cos(a), math.sin(a)
    hw, hd = b["w"] / 2 + grow, b["d"] / 2 + grow
    return [(b["x"] + c * u - s * v, b["y"] + s * u + c * v) for u, v in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd))]


def in_building(p, grow=0.0):
    for b in BLD:
        if abs(b["x"] - p[0]) < 60 and abs(b["y"] - p[1]) < 60 and in_poly(p, bld_rect(b, grow)):
            return True
    return False


def clear_spot(p, r, pave_margin=0.5, kinds=("ribbon", "ring", "joint", "walk"), bld=True, water_ok=False, step=1.0, rmax=25.0):
    """Nearest point to p where a disc of radius r is off the pavement (kinds), out of buildings and on land."""
    def ok(q):
        pts = [q] + [(q[0] + r * math.cos(a), q[1] + r * math.sin(a)) for a in [k * math.pi / 6 for k in range(12)]]
        for t in pts:
            if on_pavement(t, pave_margin, kinds):
                return False
            if bld and in_building(t, 0.5):
                return False
            if not water_ok and wet(t):
                return False
        return True
    if ok(p):
        return p, 0.0
    for ring in range(1, int(rmax / step) + 1):
        rr = ring * step
        cands = [(p[0] + rr * math.cos(a), p[1] + rr * math.sin(a)) for a in [k * 2 * math.pi / (8 * ring) for k in range(8 * ring)]]
        for q in cands:
            if ok(q):
                return q, rr
    return None, None


def facing_theta(front_plan_deg):
    """theta for an asset whose front faces Blender -Y, so that the front faces plan angle front_plan_deg."""
    return front_plan_deg + 90.0


def cap_to_plan(u, v):
    x0, y0 = CAPJ["frame"]["origin_plan_m"]
    ph = math.radians(CAPJ["frame"]["phi_deg"])
    return (x0 + math.cos(ph) * u - math.sin(ph) * v, y0 + math.sin(ph) * u + math.cos(ph) * v)


def cap_dir(du, dv):
    ph = math.radians(CAPJ["frame"]["phi_deg"])
    return math.degrees(math.atan2(math.sin(ph) * du + math.cos(ph) * dv, math.cos(ph) * du - math.sin(ph) * dv))


def cap_blocked(u, v, r):
    """On a Capitol drive, walk, plaza or keep-out (capitol.json, local metres), or near an expressway pier?"""
    pts = [(u, v)] + [(u + r * math.cos(a), v + r * math.sin(a)) for a in [k * math.pi / 4 for k in range(8)]]
    for q in pts:
        for poly in CAPJ.get("keepouts_local", []):
            if in_poly(q, poly):
                return True
        for outer, inner in CAPJ.get("keepout_rings_local", []):
            if in_poly(q, outer) and not in_poly(q, inner):
                return True
        if not in_poly(q, CAPJ["grounds_outline_local"]):
            return True
    for pu, pv in CAPJ.get("piers_local", []):
        if math.hypot(pu - u, pv - v) < r + 8.0:
            return True
    return False


EXPR = json.load(open(ROOT + "/Saved/Expressway/expressway_footprint.json")) if os.path.exists(ROOT + "/Saved/Expressway/expressway_footprint.json") else {}


def near_expressway(p, margin=4.0):
    """Within margin of an I-35 / Wacker deck, fill or column polygon (highway-capitol's footprint file)?"""
    for key in ("deck", "fill", "columns"):
        for poly in EXPR.get(key, []):
            xs = [q[0] for q in poly]
            ys = [q[1] for q in poly]
            if min(xs) - margin <= p[0] <= max(xs) + margin and min(ys) - margin <= p[1] <= max(ys) + margin:
                if in_poly(p, poly) or poly_dist(p, poly) < margin:
                    return True
    return False


CLEAR = []        # stand-ins to remove in Unreal: {"kind": "props"|"trees", "circle": [x, y, r]} or {"poly": [...]}


def layout():
    """All placements that are not made by the asset jobs themselves (bridges, Pfluger), plus the clear zones."""
    LAYOUT["_redo_assets"] = []
    redo = LAYOUT["_redo_assets"]
    P = LAYOUT.setdefault("placements", [])
    def put(asset, p, theta, z="ground", **kw):
        redo.append(asset)
        return place(asset, p, theta, z, **kw)
    o = osm()
    report = {}
    # --- moonlight towers in the map: W 9th & Guadalupe (SE corner, at the city's plaque) and E 11th & Trinity (SE corner)
    for key, src in (("9th_guadalupe", "n13971422752"), ("11th_trinity", "n3913816610")):
        p0 = opos(src)
        q, moved = clear_spot(p0, 1.9, pave_margin=0.3, kinds=("ribbon", "ring", "joint"))
        if q is None:
            report[key] = "no clear spot"
            continue
        # guys: turn the set so as few anchors as possible land in buildings
        best = None
        for k in range(12):
            th = k * 10.0
            bad = 0
            for lev, R in enumerate((16.0, 22.0, 28.0)):
                for j in range(3):
                    a = math.radians(th + 90 + 120 * j + 60)
                    t = (q[0] + R * math.cos(a), q[1] + R * math.sin(a))
                    bad += in_building(t) * 2 + on_pavement(t, 0.0, ("ribbon", "ring", "joint"))
            if best is None or bad < best[0]:
                best = (bad, th)
        put("LM_ATX_MoonlightTower", q, best[1], collision="complex", site=key)
        put("LM_ATX_MoonlightGuys", q, best[1], collision="none", site=key)
        CLEAR.append({"kind": "props", "circle": [q[0], q[1], 2.6], "why": f"moonlight tower {key}"})
        report[key] = {"p": [round(q[0], 1), round(q[1], 1)], "moved_m": moved, "guys_bad_anchors": best[0]}
    # --- the Treaty Oak, in the middle of its little park (Caldwell Treaty Oak Park)
    park = o["w210646847"]["plan_pts"]
    pc = (sum(p[0] for p in park[:-1]) / (len(park) - 1), sum(p[1] for p in park[:-1]) / (len(park) - 1))
    put("LM_ATX_TreatyOak", pc, 0.0, collision="none", site="treaty_oak")
    put("LM_ATX_TreatyOak_Trunk", pc, 0.0, collision="complex", site="treaty_oak")
    CLEAR.append({"kind": "trees", "circle": [pc[0], pc[1], 15.0], "why": "Treaty Oak canopy"})
    CLEAR.append({"kind": "props", "circle": [pc[0], pc[1], 3.5], "why": "Treaty Oak trunk"})
    report["treaty_oak"] = [round(pc[0], 1), round(pc[1], 1)]
    # --- Stevie Ray Vaughan at Auditorium Shores, facing south (real) with the lake behind him
    p0 = opos("n281230952")
    p, moved = clear_spot(p0, 8.4, pave_margin=0.3, kinds=("ribbon", "ring", "joint", "walk"), step=0.5)   # the plaza stays on land
    put("LM_ATX_SRVStatue", p, facing_theta(plan_angle(180.0)), collision="complex", site="srv")
    CLEAR.append({"kind": "props", "circle": [p[0], p[1], 8.6], "why": "SRV plaza"})
    report["srv"] = {"p": [round(p[0], 1), round(p[1], 1)], "moved_m": moved}
    # --- Angelina Eberly at Congress & 6th, cannon pointing up Congress (north)
    p = opos("n10289996520")
    q, moved = clear_spot(p, 2.6, pave_margin=0.2, kinds=("ribbon", "ring", "joint"))
    put("LM_ATX_EberlyStatue", q, facing_theta(plan_angle(0.0)), collision="complex", site="eberly")
    CLEAR.append({"kind": "props", "circle": [q[0], q[1], 2.8], "why": "Eberly base"})
    report["eberly"] = {"p": [round(q[0], 1), round(q[1], 1)], "moved_m": moved}
    # --- Willie Nelson on 2nd Street, facing the street (real south)
    p = opos("n8454950386")
    q, moved = clear_spot(p, 1.2, pave_margin=0.2, kinds=("ribbon", "ring", "joint"))
    put("LM_ATX_WillieStatue", q, facing_theta(plan_angle(180.0)), collision="complex", site="willie")
    CLEAR.append({"kind": "props", "circle": [q[0], q[1], 1.6], "why": "Willie plinth"})
    report["willie"] = {"p": [round(q[0], 1), round(q[1], 1)], "moved_m": moved}
    # --- Capitol monuments: OpenStreetMap positions where mapped, else the TSPB guide (capitol local u east, v north)
    caps = [("LM_ATX_Cap_Tejano", "n14134110658", None, 7.0), ("LM_ATX_Cap_AfricanAmerican", "n4979610121", None, 6.0),
            ("LM_ATX_Cap_PeaceOfficers", "w1406446799", None, 7.5), ("LM_ATX_Cap_Vietnam", "n6990944960", None, 3.0),
            ("LM_ATX_Cap_DisabledVets", "n14134107471", None, 2.6), ("LM_ATX_Cap_Liberty", "n9293789970", None, 1.8),
            ("LM_ATX_Cap_TenCommandments", "n5058269727", None, 1.2), ("LM_ATX_Cap_WWII", "n9293789971", None, 1.2),
            ("LM_ATX_Cap_Children", "n2743506690", None, 3.0), ("LM_ATX_Cap_PioneerWoman", "ll30.27561,-97.74059", None, 1.2),
            ("LM_ATX_Cap_PearlHarbor", None, (-52.0, 128.0), 1.6), ("LM_ATX_Cap_NationalGuard", None, (-129.0, 0.0), 1.2)]
    x0, y0 = CAPJ["frame"]["origin_plan_m"]
    ph = math.radians(CAPJ["frame"]["phi_deg"])
    def to_local(x, y):
        dx, dy = x - x0, y - y0
        return (math.cos(ph) * dx + math.sin(ph) * dy, -math.sin(ph) * dx + math.cos(ph) * dy)
    used = []
    for asset, key, uv, r in caps:
        if key and key.startswith("ll"):
            la, lo = (float(t) for t in key[2:].split(","))
            u, v = to_local(*ll_plan(la, lo))
        else:
            u, v = to_local(*opos(key)) if key else uv
        best = None
        for ring in range(0, 13):
            for k in range(max(1, 8 * ring)):
                a = 2 * math.pi * k / max(1, 8 * ring)
                uu, vv = u + ring * math.cos(a), v + ring * math.sin(a)
                if cap_blocked(uu, vv, r) or near_expressway(cap_to_plan(uu, vv), r + 4.0) or any(math.hypot(uu - a_, vv - b_) < r + r_ + 1.0 for a_, b_, r_ in used):
                    continue
                best = (uu, vv, ring)
                break
            if best:
                break
        if not best:
            report[asset] = "no clear spot on the grounds"
            continue
        uu, vv, moved = best
        used.append((uu, vv, r))
        front = cap_dir(-1.0 if uu > 0 else 1.0, 0.0)      # face the Great Walk / north drive axis
        put(asset, cap_to_plan(uu, vv), facing_theta(front), collision="complex", site="capitol")
        CLEAR.append({"kind": "props", "circle": [*cap_to_plan(uu, vv), r + 0.5], "why": asset})
        report[asset] = {"local": [round(uu, 1), round(vv, 1)], "moved_m": moved, "src": key or "TSPB guide"}
    # --- the bat watchers: on the Congress bridge's east sidewalk and on the south-bank lawn west of the bridge
    br = LAYOUT.get("bridges", {}).get("congress") or json.load(open(BASE + "/austin_sights.json"))["layout"]["bridges"]["congress"]
    O, d = br["origin"], br["dir"]
    n = (-d[1], d[0])
    th = math.degrees(math.atan2(d[1], d[0]))
    for s in (55.0, 125.0):
        put("LM_ATX_CrowdSidewalk", (O[0] + d[0] * s + n[0] * 11.2, O[1] + d[1] * s + n[1] * 11.2), th, z=0.12, collision="none", site="congress")
    # lawn: the green strip on the south bank, plan east of the bridge (the Statesman lawn's side is built over in the plan)
    q, moved = clear_spot((O[0] + d[0] * (br["water_len"] + 14.0) - n[0] * 30.0, O[1] + d[1] * (br["water_len"] + 14.0) - n[1] * 30.0), 8.0,
                          pave_margin=0.5, kinds=("ribbon", "ring", "joint", "walk"))
    if q:
        put("LM_ATX_CrowdLawn", q, th + 180.0, collision="none", site="bat_lawn")
        CLEAR.append({"kind": "trees", "circle": [q[0], q[1], 9.0], "why": "bat lawn"})
        report["bat_lawn"] = {"p": [round(q[0], 1), round(q[1], 1)], "moved_m": moved}
    # --- docks, moorings and boats
    dock_layout(o, put, report)
    shores_layout(put, report)
    # --- 6th Street neon and the theatre blade on Congress Avenue
    neon_layout(put, report)
    sixth_frontage(put, report)
    LAYOUT["clear"] = CLEAR
    LAYOUT["report"] = report


def pier_axis(pts):
    """Principal axis of a pier outline: centre, unit direction, length, width."""
    pts = pts[:-1] if pts[0] == pts[-1] else pts
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    sxx = sum((p[0] - cx) ** 2 for p in pts)
    syy = sum((p[1] - cy) ** 2 for p in pts)
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in pts)
    a = 0.5 * math.atan2(2 * sxy, sxx - syy)
    d = (math.cos(a), math.sin(a))
    proj = [(p[0] - cx) * d[0] + (p[1] - cy) * d[1] for p in pts]
    w = [-(p[0] - cx) * d[1] + (p[1] - cy) * d[0] for p in pts]
    return (cx, cy), d, max(proj) - min(proj), max(w) - min(w)


def boat_ok(p, theta, L, W):
    a = math.radians(theta)
    d, n = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
    for u in (-L / 2 - 1, 0.0, L / 2 + 1):
        for v in (-W / 2 - 1, W / 2 + 1):
            if not wet((p[0] + d[0] * u + n[0] * v, p[1] + d[1] * u + n[1] * v)):
                return False
    return True


def dock_layout(o, put, report):
    """Floating docks along the mapped floating piers (Hyatt / bat-cruise docks, the riverboat dock, the Waller Creek
    boathouse of the Austin Rowing Club), a quay stair down the 5.5 m wall at each, boats moored and out on the lake."""
    groups = {"hyatt": ["w969902081", "w969902082", "w969902083"], "riverboat": ["w969902073"],
              "boathouse": ["w849962544", "w849962545", "w849962546"]}
    rep = {}
    taken = []
    for g, keys in groups.items():
        for key in keys:
            if key not in o:
                continue
            c, d, L, Wd = pier_axis(o[key]["plan_pts"])
            # point the dock away from the shore: the end nearer the land is the root
            e0 = (c[0] - d[0] * L / 2, c[1] - d[1] * L / 2)
            e1 = (c[0] + d[0] * L / 2, c[1] + d[1] * L / 2)
            if not wet(e0) and wet(e1):
                pass
            elif wet(e0) and not wet(e1):
                d = (-d[0], -d[1])
            Lm = max(10.0, round(L / 10.0) * 10.0)
            root = (c[0] - d[0] * Lm / 2, c[1] - d[1] * Lm / 2)
            # walk the root out until it is on the water, then lay modules
            s = 0.0
            while not wet((root[0] + d[0] * s, root[1] + d[1] * s)) and s < 30:
                s += 0.5
            th = math.degrees(math.atan2(d[1], d[0]))
            mods = []
            for k in range(int(Lm / 10)):
                m = (root[0] + d[0] * (s + 5.0 + 10.0 * k), root[1] + d[1] * (s + 5.0 + 10.0 * k))
                if not wet(m):
                    continue
                put("LM_ATX_DockModule", m, th, z="water", collision="complex", site=g)
                mods.append(m)
                for sv in (-1.0, 1.0):
                    put("LM_ATX_Piling", (m[0] - d[1] * sv * 1.75 + d[0] * 4.0, m[1] + d[0] * sv * 1.75 + d[1] * 4.0), 0.0, z="water", collision="complex", site=g)
            if not mods:
                continue
            # quay stair: from the wall top at the dock root, running along the wall
            q = (root[0] + d[0] * (s - 0.3), root[1] + d[1] * (s - 0.3))
            put("LM_ATX_QuayStair", q, th + 90.0, z=0.0, collision="complex", site=g)
            taken += mods
            rep.setdefault(g, 0)
            rep[g] += len(mods)
            # moorings beside the dock
            side = (-d[1], d[0])
            if g == "hyatt":
                bp = (mods[-1][0] + side[0] * 4.0, mods[-1][1] + side[1] * 4.0)
                if boat_ok(bp, th, 13.5, 4.4):
                    put("LM_ATX_CruiseBoat", bp, th, z="water", collision="complex", site=g)
            elif g == "riverboat":
                bp = (mods[0][0] + side[0] * 5.2 + d[0] * 4.0, mods[0][1] + side[1] * 5.2 + d[1] * 4.0)
                if boat_ok(bp, th, 23.0, 6.5):
                    put("LM_ATX_Riverboat", bp, th, z="water", collision="complex", site=g)
            else:
                for k_, mm in enumerate(mods[:2]):
                    for sv in (-1.0, 1.0):
                        bp = (mm[0] + side[0] * sv * 2.2, mm[1] + side[1] * sv * 2.2)
                        asset = "LM_ATX_Kayak_Blue" if (k_ + (sv > 0)) % 2 else "LM_ATX_Kayak_Green"
                        if boat_ok(bp, th, 3.8, 0.8):
                            put(asset, bp, th, z="water", collision="none", site=g)
    # boats out on the lake: positions given as (plan point, heading deg), kept only if the hull is on open water
    lake = [("LM_ATX_Shell8", (-1650.0, 405.0), 4.0), ("LM_ATX_Scull1", (-1540.0, 380.0), 186.0), ("LM_ATX_Shell8", (-980.0, 335.0), 178.0),
            ("LM_ATX_CruiseBoat", (-1470.0, 360.0), 95.0), ("LM_ATX_Riverboat", (-1290.0, 420.0), 182.0),
            ("LM_ATX_Kayak_Red", (-930.0, 300.0), 20.0), ("LM_ATX_Kayak_Yellow", (-905.0, 292.0), 35.0), ("LM_ATX_SUP", (-860.0, 310.0), 190.0),
            ("LM_ATX_Kayak_Red", (-700.0, 280.0), 200.0), ("LM_ATX_SUP", (-640.0, 300.0), 12.0), ("LM_ATX_Kayak_Yellow", (-520.0, 300.0), 170.0),
            ("LM_ATX_Scull1", (-380.0, 280.0), 10.0), ("LM_ATX_Kayak_Red", (-150.0, 300.0), 15.0), ("LM_ATX_SUP", (-1180.0, 360.0), 0.0),
            ("LM_ATX_Kayak_Yellow", (-1600.0, 380.0), 190.0)]
    sizes = {"LM_ATX_Shell8": (18.0, 1.0), "LM_ATX_Scull1": (8.5, 1.0), "LM_ATX_CruiseBoat": (14.0, 4.8), "LM_ATX_Riverboat": (23.5, 6.5),
             "LM_ATX_Kayak_Red": (3.8, 2.4), "LM_ATX_Kayak_Yellow": (3.8, 2.4), "LM_ATX_SUP": (3.3, 1.0)}
    kept = 0
    for asset, p, hd in lake:
        L, W = sizes[asset]
        if boat_ok(p, hd, L, W) and all(math.dist(p, t) > 15 for t in taken):
            put(asset, p, hd, z="water", collision="complex" if L > 10 else "none", site="lake")
            kept += 1
    rep["lake_boats"] = kept
    report["docks"] = rep


def street_edges(names):
    return [e for e in RN["edges"] if e["name"] in names and e["ribbon"]]


def neon_layout(put, report):
    """6th Street between Congress Avenue and the map edge: blade signs and flat signs on the street faces of the
    buildings (buildings_v3 footprints, which the City Sample facades follow), every ~14 m, both sides."""
    edges = street_edges({"East 6th Street"})
    blades = [s[0] for s in NEON_BLADES]
    flats = [s[0] for s in NEON_FLAT]
    rnd = random.Random(606)
    placed = 0
    used = []
    for b in BLD:
        if b["district"] not in ("austin_dt", "austin_low"):
            continue
        R = bld_rect(b)
        for i in range(4):
            a, c = R[i], R[(i + 1) % 4]
            L = math.dist(a, c)
            if L < 8:
                continue
            mid = ((a[0] + c[0]) / 2, (a[1] + c[1]) / 2)
            dvec = ((c[0] - a[0]) / L, (c[1] - a[1]) / L)
            nout = (dvec[1], -dvec[0])         # outward normal for a counter-clockwise rect
            ctr = (b["x"], b["y"])
            if (mid[0] - ctr[0]) * nout[0] + (mid[1] - ctr[1]) * nout[1] < 0:
                nout = (-nout[0], -nout[1])
            # this face must look onto 6th Street within 14 m
            near = None
            for e in edges:
                g = e["geom"]
                dd = min(seg_dist(mid, p, q) for p, q in zip(g, g[1:]))
                if dd < 22.0:
                    near = (e, dd)
                    break
            if not near:
                continue
            probe = (mid[0] + nout[0] * 8.0, mid[1] + nout[1] * 8.0)
            if not on_pavement(probe, 1.0, ("ribbon", "ring", "joint", "walk")):
                continue
            nk = max(1, int(L / 14.0))
            for k in range(nk):
                t = (k + 0.5) / nk
                p = (a[0] + (c[0] - a[0]) * t, a[1] + (c[1] - a[1]) * t)
                if any(math.dist(p, u) < 9.0 for u in used):
                    continue
                used.append(p)
                front = math.degrees(math.atan2(nout[1], nout[0]))
                if (placed % 3) != 2:
                    nm = rnd.choice(blades)
                    put(f"LM_ATX_Neon_{nm}", p, facing_theta(front), z="ground", dz=4.2, collision="complex", site="sixth", wall=True)
                else:
                    nm = rnd.choice(flats)
                    put(f"LM_ATX_NeonFlat_{nm}", p, facing_theta(front), z="ground", dz=3.4, collision="none", site="sixth", wall=True)
                placed += 1
    # the Paramount's blade and marquee: on the Congress Avenue face of the building behind the theatre's footprint
    th_c = opos("w328526454")
    best = None
    for b in BLD:
        if abs(b["x"] - th_c[0]) > 50 or abs(b["y"] - th_c[1]) > 50:
            continue
        R = bld_rect(b)
        for i in range(4):
            a, c = R[i], R[(i + 1) % 4]
            mid = ((a[0] + c[0]) / 2, (a[1] + c[1]) / 2)
            L = math.dist(a, c)
            dvec = ((c[0] - a[0]) / L, (c[1] - a[1]) / L)
            nout = (dvec[1], -dvec[0])
            if (mid[0] - b["x"]) * nout[0] + (mid[1] - b["y"]) * nout[1] < 0:
                nout = (-nout[0], -nout[1])
            if nout[0] < 0.8:            # faces plan east, onto Congress Avenue
                continue
            # the point of this face nearest the theatre's real frontage (its footprint's east side)
            tgt = (max(p[0] for p in osm()["w328526454"]["plan_pts"]), th_c[1])
            u = max(0.0, min(L, (tgt[0] - a[0]) * dvec[0] + (tgt[1] - a[1]) * dvec[1]))
            p = (a[0] + dvec[0] * u, a[1] + dvec[1] * u)
            dd = math.dist(p, tgt)
            if best is None or dd < best[0]:
                best = (dd, p, nout)
    if best:
        dd, p, nout = best
        put("LM_ATX_TheatreSign", p, facing_theta(math.degrees(math.atan2(nout[1], nout[0]))), z="ground", dz=0.0, collision="complex",
            site="paramount", wall=True)
        report["theatre_sign"] = {"p": [round(p[0], 1), round(p[1], 1)], "off_footprint_m": round(dd, 1)}
    report["sixth_street_signs"] = placed


# ================================================================== 6th Street storefronts (generic 1870s-1900s two-storey commercial fronts)
STOREFRONTS = {
    # name: (width, height, storeys, wall material, trim, upper windows, extras)
    "A": (8.0, 8.2, 2, "M_Brick", "M_Limestone", 3, ("awning",)),
    "B": (10.0, 9.6, 2, "M_Limestone", "M_TrimDark", 3, ("balcony",)),
    "C": (12.0, 8.6, 2, "M_PaintTeal", "M_Limestone", 4, ("awning", "arched")),
    "D": (14.0, 11.2, 3, "M_Brick", "M_Limestone", 5, ("arched",)),
    "E": (9.0, 8.6, 2, "M_PaintRust", "M_TrimDark", 2, ("balcony", "awning")),
    "F": (11.0, 9.0, 2, "M_PaintCream", "M_TrimDark", 3, ()),
}


def storefront(key):
    """A generic commercial front of the kind that lines E 6th Street (brick, limestone or painted, a glazed shopfront
    with a recessed door and transom, tall upper windows with hoods or arches, a corbelled cornice and parapet with a
    blank name panel; some with an iron balcony or a canvas awning). 8 m deep. Origin: the front wall's bottom centre on
    the back of the sidewalk; the front faces -Y; the building extends toward +Y."""
    W, H, n_st, wall, trim, nwin, extras = STOREFRONTS[key]
    D = 8.0
    B = Builder()
    gf = 4.2                       # ground-floor height (shopfront)
    # shell: side and back walls, roof
    B.boxmm((-W / 2, 0.3, 0.0), (-W / 2 + 0.3, D, H), wall)
    B.boxmm((W / 2 - 0.3, 0.3, 0.0), (W / 2, D, H), wall)
    B.boxmm((-W / 2 + 0.3, D - 0.3, 0.0), (W / 2 - 0.3, D, H), wall)
    B.boxmm((-W / 2 + 0.3, 0.3, H - 0.9), (W / 2 - 0.3, D - 0.3, H - 0.7), "M_RoofFlat")
    B.boxmm((-W / 2 + 0.3, 0.3, 0.0), (W / 2 - 0.3, D - 0.3, 0.1), "M_TrimDark")
    # shopfront: pilasters, a dark glazed front with mullions, recessed door, transom band, sign band
    B.boxmm((-W / 2, 0.0, 0.0), (-W / 2 + 0.55, 0.35, gf), trim)
    B.boxmm((W / 2 - 0.55, 0.0, 0.0), (W / 2, 0.35, gf), trim)
    B.boxmm((-W / 2 + 0.55, 0.15, 0.0), (W / 2 - 0.55, 0.3, 0.5), trim)                      # bulkhead
    B.boxmm((-W / 2 + 0.55, 0.22, 0.5), (W / 2 - 0.55, 0.28, 3.0), "M_GlassDark")
    for k in range(1, 4):
        x = -W / 2 + 0.55 + (W - 1.1) * k / 4
        B.boxmm((x - 0.05, 0.12, 0.5), (x + 0.05, 0.25, 3.0), "M_TrimDark")
    B.boxmm((-0.8, 0.2, 0.0), (0.8, 1.4, 2.6), "M_GlassDark")                                   # recessed door bay
    B.boxmm((-0.8, 1.38, 0.0), (0.8, 1.45, 2.4), "M_Door")
    B.boxmm((-W / 2 + 0.55, 0.1, 3.0), (W / 2 - 0.55, 0.3, 3.15), "M_TrimDark")
    B.boxmm((-W / 2 + 0.55, 0.24, 3.15), (W / 2 - 0.55, 0.3, 3.6), "M_GlassDark")                # transom
    B.boxmm((-W / 2, 0.0, 3.6), (W / 2, 0.35, gf), trim)                                       # sign band / storefront cornice
    B.boxmm((-W / 2 - 0.05, -0.12, gf - 0.15), (W / 2 + 0.05, 0.35, gf), trim)
    # upper facade with windows
    holes = []
    for j in range(nwin):
        xc = -W / 2 + W * (j + 0.5) / nwin
        holes.append((xc + W / 2, min(1.1, W / nwin * 0.5), 0.0, 0.0, False))
    st_h = (H - gf - 1.3) / (n_st - 1)
    for s_ in range(n_st - 1):
        z0 = gf + s_ * st_h
        hl = []
        for j in range(nwin):
            xc = W * (j + 0.5) / nwin
            ww = min(1.15, W / nwin * 0.5)
            top = st_h - 0.75 - (ww / 2 if "arched" in extras else 0.0)
            hl.append((xc, ww, 0.75, top, "arched" in extras))
        B.wall((-W / 2, 0.0, z0), (1, 0, 0), (0, 0, 1), W, st_h, 0.35, wall, holes=hl, fill="M_GlassDark", fill_inset=0.7)
        for xc, ww, y0, y1, arch in hl:
            x = -W / 2 + xc
            B.boxmm((x - ww / 2 - 0.1, -0.08, z0 + y0 - 0.12), (x + ww / 2 + 0.1, 0.02, z0 + y0), trim)          # sill
            if not arch:
                B.boxmm((x - ww / 2 - 0.15, -0.1, z0 + y1), (x + ww / 2 + 0.15, 0.02, z0 + y1 + 0.22), trim)      # hood
    # cornice and parapet with a blank name panel
    zc = gf + (n_st - 1) * st_h
    B.boxmm((-W / 2, 0.0, zc), (W / 2, 0.35, H), wall)
    B.boxmm((-W / 2 - 0.1, -0.3, zc + 0.1), (W / 2 + 0.1, 0.35, zc + 0.35), trim)
    for k in range(int(W / 0.6)):
        x = -W / 2 + 0.3 + k * 0.6
        B.boxmm((x - 0.1, -0.22, zc - 0.05), (x + 0.1, 0.0, zc + 0.1), trim)                                     # corbels
    B.boxmm((-W / 2 - 0.05, -0.1, H - 0.15), (W / 2 + 0.05, 0.35, H), trim)
    B.boxmm((-W * 0.2, -0.05, zc + 0.35), (W * 0.2, 0.02, H - 0.2), trim)
    B.pyramid((0.0, -0.01, H), W * 0.2, 0.18, 0.6, trim)
    if "balcony" in extras:
        zb = gf
        B.boxmm((-W / 2 + 0.4, -1.4, zb - 0.1), (W / 2 - 0.4, 0.0, zb + 0.05), "M_Iron")
        rail(B, [(-W / 2 + 0.4, 0.0), (-W / 2 + 0.4, -1.4), (W / 2 - 0.4, -1.4), (W / 2 - 0.4, 0.0)], zb + 0.05, 1.0, "M_Iron", post=0.9, r=0.02)
        for x in (-W / 2 + 0.5, W / 2 - 0.5):
            B.rod((x, -1.3, 0.0), (x, -1.3, zb - 0.1), 0.06, "M_Iron", sides=6)
    if "awning" in extras:
        P0, P1 = (-W / 2 + 0.6, 0.1, 3.5), (W / 2 - 0.6, 0.1, 3.5)
        B.face([P0, P1, (W / 2 - 0.6, -1.6, 2.8), (-W / 2 + 0.6, -1.6, 2.8)][::-1], "M_AwningRed")
        B.face([P0, P1, (W / 2 - 0.6, -1.6, 2.8), (-W / 2 + 0.6, -1.6, 2.8)], "M_AwningRed")
        B.face([(-W / 2 + 0.6, -1.6, 2.8), (W / 2 - 0.6, -1.6, 2.8), (W / 2 - 0.6, -1.6, 2.5), (-W / 2 + 0.6, -1.6, 2.5)], "M_AwningRed")
    name = f"LM_ATX_Storefront{key}"
    export(name, [B.finish(name)], {"origin": "front wall bottom centre; faces -Y; 8 m deep toward +Y", "width_m": W, "height_m": H})


def storefronts():
    for k in STOREFRONTS:
        storefront(k); reset()
    string_lights()


def string_lights(span=24.0, sag=1.4):
    """A catenary of warm bulbs strung across a street (as on E 6th), span metres along +X, hung from wall brackets at
    z = 0 (the placer sets the height); no collision. Origin: the span's midpoint at the brackets' height."""
    B = Builder()
    n = 24
    pts = []
    for k in range(n + 1):
        x = -span / 2 + span * k / n
        z = -sag * (1 - (2 * x / span) ** 2)
        pts.append((x, 0.0, z))
    B.tube(pts, [0.012] * len(pts), "M_Iron", sides=3)
    for k in range(1, n * 2):
        t = k / (n * 2)
        x = -span / 2 + span * t
        z = -sag * (1 - (2 * x / span) ** 2) - 0.08
        B.lathe([(0.0, z - 0.06), (0.05, z - 0.03), (0.05, z + 0.03), (0.0, z + 0.06)], "M_Bulb", segs=6, center=(x, 0.0, 0))
    for sx in (-1, 1):
        B.rod((sx * span / 2, 0.0, 0.0), (sx * (span / 2 + 0.6), 0.0, 0.0), 0.03, "M_Iron", sides=4)
    export("LM_ATX_StringLights", [B.finish("LM_ATX_StringLights")], {"origin": "span midpoint at bracket height; spans along X", "span_m": span})


def sixth_frontage(put, report):
    """Fill the empty frontage along E 6th Street (Congress Avenue to the map edge) with storefronts at the back of the
    sidewalk, where an 8 m deep footprint is clear of the City Sample buildings (buildings_v3 + 1 m), the pavement and
    the water; neon on them (a blade on most, a flat sign over some doors)."""
    edges = street_edges({"East 6th Street"})
    rnd = random.Random(1906)
    keys = list(STOREFRONTS)
    placed = []
    signs = 0
    for e in edges:
        g = e["geom"]
        off0 = e["width"] / 2 + e.get("sidewalk", 3.8) + 0.25
        for side in (-1, 1):
            # sample the back-of-sidewalk line every 0.5 m
            line = []
            for a, b in zip(g, g[1:]):
                L = math.dist(a, b)
                d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
                n = (-d[1] * side, d[0] * side)
                for k in range(int(L / 0.5)):
                    t = k * 0.5
                    line.append(((a[0] + d[0] * t + n[0] * off0, a[1] + d[1] * t + n[1] * off0), d, n))
            i = 0
            while i < len(line):
                key = rnd.choice(keys)
                W = STOREFRONTS[key][0]
                nW = int(W / 0.5)
                if i + nW >= len(line):
                    break
                p0, d, n = line[i]
                p1 = line[i + nW][0]
                c = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
                ok = True
                for u in [-W / 2 + (W) * k / 6 for k in range(7)]:
                    for v in (-1.8, 0.2, 2.5, 5.0, 7.8, 8.3):
                        q = (c[0] + d[0] * u + n[0] * v, c[1] + d[1] * u + n[1] * v)
                        if v < 0:      # awnings and balconies may overhang the sidewalk, never the carriageway or a corner
                            if on_pavement(q, 0.3, ("ribbon", "ring", "joint")):
                                ok = False
                                break
                            continue
                        if on_pavement(q, 0.15) or in_building(q, 1.0) or wet(q) or near_expressway(q, 1.0):
                            ok = False
                            break
                    if not ok:
                        break
                if not ok or any(math.dist(c, pc) < W / 2 + 4.0 for pc, _ in placed):
                    i += 2
                    continue
                front = math.degrees(math.atan2(-n[1], -n[0]))         # faces the street
                put(f"LM_ATX_Storefront{key}", c, facing_theta(front), z="ground", collision="complex", site="sixth")
                placed.append((c, W))
                # neon: a blade near one end of the upper facade, or a flat sign over the door
                if rnd.random() < 0.7:
                    nm = rnd.choice([s[0] for s in NEON_BLADES])
                    u = rnd.choice((-1, 1)) * (W / 2 - 0.9)
                    put(f"LM_ATX_Neon_{nm}", (c[0] + d[0] * u, c[1] + d[1] * u), facing_theta(front), z="ground", dz=4.4, collision="complex", site="sixth")
                else:
                    nm = rnd.choice([s[0] for s in NEON_FLAT])
                    put(f"LM_ATX_NeonFlat_{nm}", (c[0] - n[0] * 0.36, c[1] - n[1] * 0.36), facing_theta(front), z="ground", dz=4.25, collision="none",
                        site="sixth")
                signs += 1
                i += nW + 1
    # string lights across the street where storefronts face each other
    lights = 0
    for (c1, w1) in placed:
        best = None
        for (c2, w2) in placed:
            dd = math.dist(c1, c2)
            if 14.0 < dd < 30.0 and (best is None or dd < best[0]):
                best = (dd, c2)
        if best and c1[0] < best[1][0] and lights < 14:
            dd, c2 = best
            mid = ((c1[0] + c2[0]) / 2, (c1[1] + c2[1]) / 2)
            th = math.degrees(math.atan2(c2[1] - c1[1], c2[0] - c1[0]))
            if abs(dd - 24.0) < 7.0:
                put("LM_ATX_StringLights", mid, th, z="ground", dz=7.2, collision="none", site="sixth", scale=[round(dd / 24.0, 3), 1.0, 1.0])
                lights += 1
    report["sixth_string_lights"] = lights
    report["sixth_storefronts"] = len(placed)
    report["sixth_storefront_signs"] = signs


# ================================================================== Auditorium Shores lakeside: the Fannie Davis gazebo, Brent Grulke Plaza
def gazebo():
    """The Fannie Davis Town Lake Gazebo (by the S 1st Street bridge): an octagonal open pavilion on a limestone
    platform, eight posts, a timber ring beam and a steep octagonal roof with a finial. ~12 m across (OSM outline).
    Origin: centre at grade."""
    B = Builder()
    R = 5.6
    oct_ = lambda r, z: [(r * math.cos(math.radians(22.5 + 45 * k)), r * math.sin(math.radians(22.5 + 45 * k)), z) for k in range(8)]
    B.sweep([(p[0], p[1]) for p in oct_(R + 0.4, 0)], "M_Limestone", [(1, 1, 0.0, 0, 0), (1, 1, 0.55, 0, 0), (0, 0, 0.55, 0, 0)], smooth=False)
    for k in range(3):
        z = 0.55 - 0.18 * (k + 1)
        ang = math.radians(270)
        B.boxmm((-1.0, -(R + 0.4) - 0.35 * (k + 1), z - 0.18), (1.0, -(R + 0.4) - 0.35 * k, z), "M_Limestone")
    for x, y, z in oct_(R - 0.3, 0.55):
        B.box((x, y, 0.55 + 1.5), (0.3, 0.3, 3.0), "M_DeckWood")
        B.box((x, y, 0.55 + 0.25), (0.45, 0.45, 0.5), "M_Limestone")
    ring = oct_(R - 0.3, 3.55)
    for i in range(8):
        B.beam(ring[i], ring[(i + 1) % 8], 0.25, 0.35, "M_DeckWood")
    # white hyperbolic-paraboloid roof: eave points alternate high and low round the octagon, warped panels to the apex
    eave = [(x, y, 3.4 if i % 2 == 0 else 4.6) for i, (x, y, z) in enumerate(oct_(R + 0.9, 0))]
    apex = Vector((0, 0, 6.2))
    nn = 6
    for i in range(8):
        a, b = Vector(eave[i]), Vector(eave[(i + 1) % 8])
        rows = []
        for u in range(nn + 1):
            e = a.lerp(b, u / nn)
            rows.append([e.lerp(apex, v / nn) + Vector((0, 0, 0.35 * math.sin(math.pi * v / nn) * (1 - abs(2 * u / nn - 1)))) for v in range(nn + 1)])
        B.grid(rows, "M_RoofWhite", smooth=True)
        B.grid([list(reversed(r)) for r in rows], "M_RoofWhite", smooth=True)
    B.lathe([(0.0, 6.1), (0.2, 6.1), (0.08, 9.6), (0.0, 9.8)], "M_Copper", segs=8)
    for k in range(4):
        a = math.pi / 2 * k
        B.prism((0, 0, 0), (math.cos(a), math.sin(a), 0), (0, 0, 1), [(0.1, 6.3), (1.0, 6.4), (0.15, 9.2)], 0.05, "M_Copper")
    for i in range(8):
        if i == 6:
            continue
        a, b = oct_(R - 0.3, 0.55)[i], oct_(R - 0.3, 0.55)[(i + 1) % 8]
        B.beam((a[0], a[1], 1.4), (b[0], b[1], 1.4), 0.12, 0.12, "M_DeckWood")
    export("LM_ATX_Gazebo", [B.finish("LM_ATX_Gazebo")], {"origin": "centre at grade", "diameter_m": 2 * (R + 0.6)})


def grulke_plaza():
    """Brent Grulke Plaza: the concrete overlook that reaches over the lake at Auditorium Shores (OSM pier outline),
    a slab at the lawn level with a steel railing on its water edges. Site asset in the plan frame, origin at its
    centroid; z = Unreal metres."""
    o = osm()
    pts = o["w856483794"]["plan_pts"]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    rel = [(p[0] - c[0], p[1] - c[1]) for p in pts]
    if area_signed(rel) < 0:
        rel = rel[::-1]
    B = Builder()
    B.prism((0, 0, Z_LAWN), (1, 0, 0), (0, 1, 0), rel, 0.75, "M_DeckConcrete")
    n = len(rel)
    for i in range(n):
        a, b = rel[i], rel[(i + 1) % n]
        mid = ((a[0] + b[0]) / 2 + c[0], (a[1] + b[1]) / 2 + c[1])
        if wet(mid):
            rail(B, [a, b], Z_LAWN, 1.1, "M_Metal", post=1.8, r=0.03)
    # the slab's edge beams down to the water on the lake side
    for i in range(n):
        a, b = rel[i], rel[(i + 1) % n]
        mid = ((a[0] + b[0]) / 2 + c[0], (a[1] + b[1]) / 2 + c[1])
        if wet(mid):
            B.face([(a[0], a[1], Z_LAWN - 0.75), (b[0], b[1], Z_LAWN - 0.75), (b[0], b[1], Z_WATER - 0.3), (a[0], a[1], Z_WATER - 0.3)], "M_ConcreteDark")
    export("LM_ATX_GrulkePlaza", [B.finish("LM_ATX_GrulkePlaza")], {"origin": "plaza centroid, plan frame; z = Unreal metres"})
    return c


def liz_carpenter_fountain():
    """The Liz Carpenter Fountain in Butler Park: a round splash plaza (~25 m) paved in a spiral of light and dark bands,
    ground jets in rings (static sprays), and dark stone seat walls round part of it. Origin: centre at grade.
    The jets are a separate asset (LM_ATX_LizCarpenterJets, no collision)."""
    B = Builder()
    R = 12.5
    nseg, nr = 48, 10
    for i in range(nseg):
        for j in range(nr):
            a0, a1 = 2 * math.pi * i / nseg, 2 * math.pi * (i + 1) / nseg
            r0, r1 = R * j / nr, R * (j + 1) / nr
            band = int((i / nseg * 6 + j * 0.5)) % 2           # a six-armed spiral
            q = [(r0 * math.cos(a0), r0 * math.sin(a0), 0.06), (r1 * math.cos(a0), r1 * math.sin(a0), 0.06), (r1 * math.cos(a1), r1 * math.sin(a1), 0.06),
                 (r0 * math.cos(a1), r0 * math.sin(a1), 0.06)]
            B.face(q, "M_GraniteGrey" if band else "M_Paving")
    B.lathe([(R, 0.06), (R, -0.1), (0.0, -0.1)], "M_Paving", segs=48, smooth=False)
    for k in range(10):
        a0, a1 = math.radians(200 + 14 * k), math.radians(200 + 14 * (k + 1) - 2)
        q = [((R + 0.3) * math.cos(a0), (R + 0.3) * math.sin(a0)), ((R + 0.8) * math.cos(a0), (R + 0.8) * math.sin(a0)),
             ((R + 0.8) * math.cos(a1), (R + 0.8) * math.sin(a1)), ((R + 0.3) * math.cos(a1), (R + 0.3) * math.sin(a1))]
        B.prism((0, 0, 0), (1, 0, 0), (0, 1, 0), q[::-1], -0.45, "M_GraniteBlack")
    export("LM_ATX_LizCarpenterFountain", [B.finish("LM_ATX_LizCarpenterFountain")], {"origin": "centre at grade", "diameter_m": 2 * R})
    reset()
    J = Builder()
    for ring_r, n, h in ((3.0, 8, 2.6), (6.0, 14, 1.8), (9.0, 20, 1.2)):
        for k in range(n):
            a = 2 * math.pi * (k + 0.5 * (ring_r == 6.0)) / n
            x, y = ring_r * math.cos(a), ring_r * math.sin(a)
            J.lathe([(0.0, 0.06), (0.06, 0.1), (0.1, h * 0.6), (0.06, h), (0.0, h + 0.1)], "M_WaterJet", segs=6, center=(x, y, 0))
    export("LM_ATX_LizCarpenterJets", [J.finish("LM_ATX_LizCarpenterJets")], {"origin": "fountain centre at grade"})


def area_signed(poly):
    return 0.5 * sum(poly[i - 1][0] * poly[i][1] - poly[i][0] * poly[i - 1][1] for i in range(len(poly)))


def shores():
    liz_carpenter_fountain(); reset()
    gazebo(); reset()
    c = grulke_plaza()
    LAYOUT.setdefault("sites", {})["grulke"] = {"origin": [round(c[0], 2), round(c[1], 2)]}
    place("LM_ATX_GrulkePlaza", c, 0.0, z=0.0, collision="complex", site="shores")
    LAYOUT["_redo_assets"] = LAYOUT.get("_redo_assets", []) + ["LM_ATX_GrulkePlaza"]


def shores_layout(put, report):
    """The gazebo on its peninsula, a small dock with kayaks at the Zilker Park boat rental."""
    p = opos("w383346797")
    put("LM_ATX_Gazebo", p, 0.0, collision="complex", site="gazebo")
    CLEAR.append({"kind": "props", "circle": [p[0], p[1], 7.0], "why": "gazebo"})
    # the Liz Carpenter Fountain in Butler Park (kept on land and off the paths)
    q, moved = clear_spot(opos("w37692951"), 13.3, pave_margin=0.3, kinds=("ribbon", "ring", "joint", "walk"), step=0.5)
    if q:
        put("LM_ATX_LizCarpenterFountain", q, 0.0, collision="complex", site="butler")
        put("LM_ATX_LizCarpenterJets", q, 0.0, collision="none", site="butler")
        CLEAR.append({"kind": "props", "circle": [q[0], q[1], 13.5], "why": "Liz Carpenter Fountain"})
        report["liz_carpenter"] = {"p": [round(q[0], 1), round(q[1], 1)], "moved_m": moved}
    # Zilker Park Boat Rental: a dock module out from the bank at the mapped point, kayaks beside it
    z = opos("n3194262978")
    best = None
    for k in range(36):
        a = math.radians(10 * k)
        d = (math.cos(a), math.sin(a))
        if not wet(z) and wet((z[0] + d[0] * 8, z[1] + d[1] * 8)) and wet((z[0] + d[0] * 12, z[1] + d[1] * 12)):
            best = d
            break
        if wet(z):
            # the point is on the water: find the bank behind it
            if not wet((z[0] - d[0] * 6, z[1] - d[1] * 6)) and wet((z[0] + d[0] * 8, z[1] + d[1] * 8)):
                best = d
                break
    if best:
        d = best
        s = 0.0
        while not wet((z[0] + d[0] * s, z[1] + d[1] * s)) and s < 20:
            s += 0.5
        th = math.degrees(math.atan2(d[1], d[0]))
        m = (z[0] + d[0] * (s + 5.0), z[1] + d[1] * (s + 5.0))
        put("LM_ATX_DockModule", m, th, z="water", collision="complex", site="zilker")
        put("LM_ATX_QuayStair", (z[0] + d[0] * (s - 0.3), z[1] + d[1] * (s - 0.3)), th + 90.0, z=0.0, collision="complex", site="zilker")
        side = (-d[1], d[0])
        for k, sv in enumerate((-2.2, 2.2, -3.4, 3.4)):
            bp = (m[0] + side[0] * sv + d[0] * (k - 1.5) * 2.0, m[1] + side[1] * sv + d[1] * (k - 1.5) * 2.0)
            asset = ("LM_ATX_Kayak_Blue", "LM_ATX_Kayak_Green", "LM_ATX_Kayak_Red", "LM_ATX_SUP")[k]
            if boat_ok(bp, th, 3.8, 0.8):
                put(asset, bp, th, z="water", collision="none", site="zilker")
        report["zilker_dock"] = [round(m[0], 1), round(m[1], 1)]
    else:
        report["zilker_dock"] = "no bank found"


# ================================================================== preview renderer (after blender_capitol.py's)
def _import(name, loc=(0, 0, 0), rot=(0, 0, 0), scale=None):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=f"{OUT}/{name}.glb")
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        if o.parent is None:
            o.location = Vector(loc)
            o.rotation_mode = "XYZ"
            o.rotation_euler = rot
            if scale:
                o.scale = scale
    return new


def _simple_mat(name, rgb, rough=0.6, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def _scene_setup(ground=True, water=False, night=False, gz=-0.03):
    sc = bpy.context.scene
    if ground:
        bpy.ops.mesh.primitive_plane_add(size=3000, location=(0, 0, gz))
        bpy.context.object.data.materials.append(_simple_mat("PV_Ground", (0.30, 0.30, 0.29), 0.85))
    if water:
        bpy.ops.mesh.primitive_plane_add(size=3000, location=(0, 0, 0.0 if water is True else water))
        bpy.context.object.data.materials.append(_simple_mat("PV_Water", (0.04, 0.10, 0.12), 0.05))
    wd = bpy.data.worlds.new("PV_Sky")
    sc.world = wd
    wd.use_nodes = True
    nt = wd.node_tree
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    if night:
        ramp.color_ramp.elements[0].color = (0.02, 0.02, 0.04, 1)
        ramp.color_ramp.elements[1].color = (0.005, 0.008, 0.02, 1)
    else:
        ramp.color_ramp.elements[0].color = (0.80, 0.86, 0.93, 1)
        ramp.color_ramp.elements[1].color = (0.22, 0.42, 0.78, 1)
    ramp.color_ramp.elements[1].position = 0.6
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(42), 0, math.radians(-30)))
    sun = bpy.context.object
    sun.data.energy = 0.05 if night else 3.8
    sun.data.angle = math.radians(1.5)


def _person(loc):
    pm = _simple_mat("PV_Person", (0.75, 0.12, 0.08), 0.6)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=1.5, location=(loc[0], loc[1], loc[2] + 0.75))
    bpy.context.object.data.materials.append(pm)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.13, location=(loc[0], loc[1], loc[2] + 1.66))
    bpy.context.object.data.materials.append(pm)


def _cam(loc, look, lens=35, res=(1600, 1000), ortho=None):
    sc = bpy.context.scene
    bpy.ops.object.camera_add(location=Vector(loc))
    cam = bpy.context.object
    cam.data.lens = lens
    cam.data.clip_end = 20000
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    cam.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100


def _render(path, samples=32):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        sc.cycles.device = "GPU"
    except Exception as e:
        print("GPU unavailable, CPU render:", e)
        sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in sc.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
    sc.render.filepath = path
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 72
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


def _row(names, gap=2.0, axis=1):
    """Import assets side by side along Y (spacing by their sizes from META/json)."""
    objs = []
    off = 0.0
    sizes = {}
    if os.path.exists(BASE + "/austin_sights.json"):
        sizes = {k: v.get("size_m") for k, v in json.load(open(BASE + "/austin_sights.json")).get("assets", {}).items()}
    for n in names:
        sz = sizes.get(n) or META.get(n, {}).get("size_m") or [10, 10, 10]
        off += sz[axis] / 2
        loc = (0, off, 0) if axis == 1 else (off, 0, 0)
        objs += _import(n, loc)
        off += sz[axis] / 2 + gap
    return objs, off


PREVIEWS = {
    # name: (assets, camera location, look-at, lens, water, night, row axis/gap)
    "boats": (["LM_ATX_Riverboat", "LM_ATX_CruiseBoat", "LM_ATX_Shell8", "LM_ATX_Scull1", "LM_ATX_Kayak_Red", "LM_ATX_Kayak_Yellow",
               "LM_ATX_Kayak_Blue", "LM_ATX_SUP"], (34, -16, 12), (0, 16, 0), 30, True, False),
    "riverboat": (["LM_ATX_Riverboat"], (16, -18, 6), (0, 0, 2.5), 35, True, False),
    "docks": (["LM_ATX_DockModule", "LM_ATX_Piling", "LM_ATX_QuayStair"], (14, -14, 4), (0, 4, -1), 30, True, False),
    "neon": (["LM_ATX_Neon_LiveMusic", "LM_ATX_Neon_Blues", "LM_ATX_Neon_Tacos", "LM_ATX_NeonFlat_HonkyTonk", "LM_ATX_Neon_Saloon",
              "LM_ATX_NeonFlat_Cocktails"], (9, -9, 3.5), (0, 6, 2.0), 30, False, True),
    "theatre": (["LM_ATX_TheatreSign"], (14, -16, 6), (0, -1.5, 9), 35, False, True),
    "treaty": (["LM_ATX_TreatyOak"], (30, -26, 9), (0, 0, 5), 35, False, False),
    "tower": (["LM_ATX_MoonlightTower", "LM_ATX_MoonlightGuys"], (40, -40, 20), (0, 0, 22), 30, False, False, "stack"),
    "tower_top": (["LM_ATX_MoonlightTower"], (6, -6, 50), (0, 0, 46.5), 40, False, False),
    "tower_base": (["LM_ATX_MoonlightTower"], (6, -6, 2.5), (0, 0, 4), 30, False, False),
    "congress": (["LM_ATX_CongressBridge"], (-120, 60, 6), (5, 100, -2), 30, -5.5, False, {"site": "congress"}),
    "congress_under": (["LM_ATX_CongressBridge"], (-35, 75, -4.6), (0, 110, -2.5), 24, -5.5, False, {"site": "congress"}),
    "lamar": (["LM_ATX_LamarBridge"], (-90, 40, 4), (0, 70, -2.5), 30, -5.5, False, {"site": "lamar"}),
    "srv": (["LM_ATX_SRVStatue"], (2.6, -4.2, 2.2), (0, 0, 1.7), 40, False, False, "stack"),
    "srv_wide": (["LM_ATX_SRVStatue"], (6, -12, 4), (0, 1, 1), 30, False, False, "stack"),
    "eberly": (["LM_ATX_EberlyStatue"], (4.5, -4.5, 2.2), (0, 0, 1.2), 35, False, False, "stack"),
    "capitol_a": (["LM_ATX_Cap_Tejano", "LM_ATX_Cap_AfricanAmerican", "LM_ATX_Cap_PeaceOfficers", "LM_ATX_Cap_Vietnam"], (14, -40, 9), (0, 24, 2.5), 32, False, False),
    "capitol_b": (["LM_ATX_Cap_DisabledVets", "LM_ATX_Cap_Liberty", "LM_ATX_Cap_TenCommandments", "LM_ATX_Cap_WWII", "LM_ATX_Cap_PioneerWoman",
                   "LM_ATX_Cap_Children", "LM_ATX_Cap_PearlHarbor", "LM_ATX_Cap_NationalGuard"], (16, -30, 6), (0, 22, 2.0), 32, False, False),
    "storefronts": (["LM_ATX_StorefrontA", "LM_ATX_StorefrontB", "LM_ATX_StorefrontC", "LM_ATX_StorefrontD", "LM_ATX_StorefrontE",
                     "LM_ATX_StorefrontF"], (22, -26, 4), (36, 0, 5), 32, False, False, (0, 0.2)),
    "willie": (["LM_ATX_WillieStatue"], (2.5, -4.5, 2.5), (0, 0, 2.2), 40, False, False, "stack"),
    "theatre_day": (["LM_ATX_TheatreSign"], (16, -18, 8), (0, -1.5, 12), 35, False, False, "stack"),
    "gazebo": (["LM_ATX_Gazebo"], (12, -12, 4), (0, 0, 3), 32, False, False, "stack"),
    "pfluger": (["LM_ATX_PflugerBridge"], (-110, -40, 55), (30, 90, 0), 30, -5.5, False, "stack"),
    "pfluger_helix": (["LM_ATX_PflugerBridge"], (-38, -30, 9), (0, 2, 2), 28, -5.5, False, "stack"),
    "pfluger_deck": (["LM_ATX_PflugerBridge"], (4, 30, 6.9), (30, 110, 4), 30, -5.5, False, "stack"),
}


def render_previews(names):
    """Previews are rendered as JPG (smaller) next to the GLBs."""
    for name in (names or list(PREVIEWS)):
        spec = PREVIEWS[name]
        assets, loc, look, lens, water, night = spec[:6]
        reset()
        _scene_setup(ground=not water, water=water, night=night)
        if len(spec) > 6 and isinstance(spec[6], dict):
            site = json.load(open(BASE + "/austin_sights.json"))["layout"]["bridges"][spec[6]["site"]]
            O, dd = site["origin"], site["dir"]
            objs = sum((_import(a) for a in assets), [])
            # the city's deck as built by build_roads_ue.py: slab 0..-1.2 m, 18.3 m wide, 0.45 m parapets to +1.1 m
            L = site["water_len"]
            ang = math.atan2(dd[1], dd[0])
            for w, z0, z1, off in ((18.3, -1.2, 0.0, 0.0), (0.45, -1.2, 1.1, 9.375), (0.45, -1.2, 1.1, -9.375)):
                bpy.ops.mesh.primitive_cube_add(size=1)
                ob = bpy.context.object
                ob.scale = (L + 40, w, z1 - z0)
                c = Vector((dd[0] * L / 2 - dd[1] * off, dd[1] * L / 2 + dd[0] * off, (z0 + z1) / 2))
                ob.location = c
                ob.rotation_euler = (0, 0, ang)
                ob.data.materials.append(_simple_mat("PV_Deck", (0.35, 0.35, 0.34), 0.8))
        elif len(spec) > 6 and spec[6] == "stack":
            objs = sum((_import(a) for a in assets), [])
        elif len(spec) > 6 and isinstance(spec[6], tuple):
            objs, span = _row(assets, gap=spec[6][1], axis=spec[6][0])
        else:
            objs, span = _row(assets)
        _person((0, -3, 0.45 if water is True else 0))
        _cam(loc, look, lens)
        _render(f"{BASE}/preview_{name}.jpg")


def write_json():
    path = BASE + "/austin_sights.json"
    data = {}
    if os.path.exists(path):
        try:
            data = json.load(open(path))
        except Exception:
            data = {}
    assets = data.get("assets", {})
    assets.update(META)
    data["assets"] = dict(sorted(assets.items()))
    if LAYOUT:
        # merge: placements of the assets (re)built in this run replace their old ones; everything else is kept
        lay = data.get("layout", {})
        redone = {q["asset"] for q in LAYOUT.get("placements", [])} | set(LAYOUT.get("_redo_assets", []))
        old = [q for q in lay.get("placements", []) if q["asset"] not in redone]
        for k, v in LAYOUT.items():
            if k in ("placements", "_redo_assets"):
                continue
            if isinstance(v, dict) and isinstance(lay.get(k), dict):
                lay[k].update(v)
            else:
                lay[k] = v
        lay["placements"] = old + LAYOUT.get("placements", [])
        data["layout"] = lay
    data["materials"] = {k: {"rgb": list(v[0]), "metal": v[1], "rough": v[2], "emit": v[3].get("emit", 0.0)} for k, v in MATDEF.items()}
    data["conventions"] = {
        "units": "metres in Blender/GLB; Unreal imports as centimetres",
        "placements": "p = plan metres (x east, y north; Unreal X = y*100, Y = x*100); theta = plan angle (deg CCW from east) "
                      "of the asset's Blender +X; Unreal yaw = 90 - theta; z = 'ground' | 'water' | 'deck' | metres",
        "austin": AUSTIN,
        "osm": "(c) OpenStreetMap contributors (ODbL); cached Overpass extracts in SourceArt/Landmarks/austin/osm/",
        "generator": "Scripts/landmarks/blender_austin_sights.py",
    }
    json.dump(data, open(path, "w"), indent=1)
    print("wrote", path)


JOBS = {"boats": boats, "docks": docks, "signs": signs, "tree": tree, "tower": tower, "bridges": bridges, "pfluger": pfluger, "statues": statues, "capitol": capitol, "storefronts": storefronts, "shores": shores, "layout": layout}

if __name__ == "__main__":
    if ARGS and ARGS[0] == "--render":
        render_previews(ARGS[1:])
    else:
        for job, fn in JOBS.items():
            if ARGS and job not in ARGS:
                continue
            reset()
            fn()
        write_json()
    print("ALL DONE")
