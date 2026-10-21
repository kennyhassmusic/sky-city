"""Sky City: Chicago landmarks, modelled procedurally in headless Blender and exported as GLB (one file per asset).

Conventions (verified in Unreal on the imported bounds):
  * real-world metres; Unreal's glTF import maps Blender (x, y, z) m -> Unreal (x, -y, z) * 100 cm, so Blender +X is
    Unreal +X (= plan north in Sky City) and Blender -Y is Unreal +Y (= plan east);
  * single objects (the Bean, the fountain, the wheel parts, bridge parts) are centred on the origin on z = 0 unless
    their docstring says otherwise (rotors, gondolas and bridge leaves keep their pivot where they rotate);
  * SITE assets (plazas, the whole of Navy Pier) are modelled in the PLAN frame of Saved/Mashup/plan_v3.json (x east,
    y north) relative to a site origin (SITES) and turned -90 deg about Z at export, so they go into Unreal at the site
    origin with NO rotation (Scripts/roads/place_landmarks_ue.py);
  * one bmesh per asset with per-face material indices; material slot names are stable (M_*), Unreal maps them to MI_*
    (see MATDEF and place_landmarks_ue.SLOTS / TEXTURED);
  * smooth shading on curved surfaces, flat on boxes; metre-scale UVs.
References for the rebuild of 20 Oct 2026 (positions, outlines, sizes): SourceArt/Reference/{CloudGate,Buckingham,NavyPier}/
(OpenStreetMap extracts, USGS NAIP aerials, Wikimedia Commons photos; sources.txt in each).

Assets (SourceArt/Landmarks/meshes/<name>.glb):
  LM_CloudGate                     the Bean: 20 x 12.8 x 10 m, 3.6 m arch, omphalos apex 8.2 m; long axis = Blender X (north)
  LM_CloudGatePlaza                site: Grainger (AT&T) Plaza 3 steps up with balustrades, steps, ramps and planters;
                                   McCormick Tribune Plaza with the rink; Chase Promenade; the Washington / Madison walks
  LM_BuckinghamFountain            three-tier pink marble body, quatrefoil pool with bastions, coping, 8 verdigris sea horses,
                                   4 bronze jet baskets
  LM_BuckinghamJets                centre 46 m jet, ring jets, sea-horse and basket jets, cascades (M_WaterJet), same origin
  LM_BuckinghamPlaza               site: pink paver plaza, lawn ring + hoop fence, 4 pavilions, hedges, lamps, Congress approach
  LM_CentennialWheel_Frame         legs, axle, base, boarding decks (static), 59.7 m overall
  LM_CentennialWheel_Rotor         hub, spokes, twin rim trusses: ORIGIN = HUB CENTRE (30.8 m up), spins about Blender Y
  LM_CentennialWheel_Gondola       one cabin: ORIGIN = its hanger pivot (radius 26.6 m), hangs down -Z
  LM_NavyPierDeck                  site (pier origin): the 929 m deck, dock walls, north drive, south promenade, railings,
                                   lamps, East End Plaza flagpoles
  LM_NavyPierBuildings             site: headhouse + towers + NAVY PIER arch, Family Pavilion, Crystal Gardens, Pier Park
                                   rides, Skyline Stage, Shakespeare Theater, garage, Festival Hall vaults, Sable hotel,
                                   West Terminal, Lakeview Terrace
  LM_NavyPierBallroom              site: Grand Ballroom drum + copper dome + the two lantern towers
  LM_PolkBrosPark / LM_PolkBrosJets site: Polk Bros Plaza with its round fountain, the pier forecourt / the fountain's jets
  LM_BridgeTenderHouse, LM_BridgeLeaf, LM_BridgeRailing10   Chicago River bascule bridge parts
  (legacy, no longer exported: LM_NavyPierHeadhouse, LM_NavyPierShed -> SourceArt/Landmarks/legacy/)

Run (repo root):
  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/landmarks/blender_landmarks.py [-- jobs...]
    jobs: bean fountain wheel pier bridge (default: all), then writes SourceArt/Landmarks/landmarks.json
  ... -P Scripts/landmarks/blender_landmarks.py -- --render [names...]
    renders SourceArt/Landmarks/preview_<name>.png for the given GLB names / composites (PREVIEWS; default: all)
"""
import json, math, os, sys
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
BASE = ROOT + "/SourceArt/Landmarks"
OUT = BASE + "/meshes"
os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
META = {}          # filled per asset, merged into landmarks.json
WHEEL = dict(HUB=30.8, R_ATT=26.6, N=42)   # 59.7 m tall (OSM height tag), wheel plane N-S (OSM footprint 4.4 x 58.4 m)   # Centennial Wheel: hub height, gondola pivot radius, gondola count


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    MATS.clear()


# ------------------------------------------------------------------ materials
MATDEF = {
    #  name             base colour              metal rough  extra
    "M_MirrorSteel": ((0.92, 0.92, 0.94), 1.0, 0.03, {}),
    "M_PinkMarble": ((0.78, 0.62, 0.58), 0.0, 0.45, {}),
    "M_Bronze": ((0.33, 0.28, 0.17), 0.9, 0.42, {}),
    "M_Water": ((0.08, 0.20, 0.24), 0.0, 0.03, {}),
    "M_WaterJet": ((0.92, 0.96, 1.00), 0.0, 0.25, {"alpha": 0.55}),
    "M_Limestone": ((0.80, 0.76, 0.67), 0.0, 0.70, {}),
    "M_BridgeSteel": ((0.24, 0.28, 0.27), 0.6, 0.50, {}),
    "M_Asphalt": ((0.07, 0.07, 0.075), 0.0, 0.90, {}),
    "M_Railing": ((0.09, 0.10, 0.09), 0.7, 0.45, {}),
    "M_WheelWhite": ((0.90, 0.91, 0.92), 0.2, 0.35, {}),
    "M_Gondola": ((0.82, 0.84, 0.86), 0.6, 0.30, {}),
    "M_Glass": ((0.22, 0.30, 0.34), 0.2, 0.05, {}),
    "M_Brick": ((0.45, 0.20, 0.13), 0.0, 0.85, {}),
    "M_Roof": ((0.27, 0.42, 0.37), 0.4, 0.50, {}),          # copper (pitched roofs, domes)
    "M_RoofFlat": ((0.16, 0.16, 0.17), 0.0, 0.90, {}),      # flat membrane roofs
    "M_Light": ((1.00, 0.92, 0.75), 0.0, 0.40, {"emit": 6.0}),
    "M_Concrete": ((0.55, 0.54, 0.52), 0.0, 0.85, {}),
    "M_Steel": ((0.20, 0.22, 0.24), 0.7, 0.40, {}),
    # site materials (plazas, pier); Unreal maps each slot to an MI_LM_* (Scripts/roads/place_landmarks_ue.py)
    "M_Granite": ((0.62, 0.62, 0.60), 0.0, 0.60, {}),
    "M_GraniteDark": ((0.32, 0.32, 0.33), 0.0, 0.55, {}),
    "M_GranitePromenade": ((0.55, 0.53, 0.50), 0.0, 0.70, {}),
    "M_RinkSurface": ((0.78, 0.80, 0.82), 0.0, 0.30, {}),
    "M_Lawn": ((0.16, 0.30, 0.10), 0.0, 0.95, {}),
    "M_Hedge": ((0.08, 0.20, 0.07), 0.0, 0.90, {}),
    "M_PinkPaver": ((0.66, 0.42, 0.37), 0.0, 0.80, {}),
    "M_Verdigris": ((0.24, 0.47, 0.40), 0.4, 0.50, {}),
    "M_DeckConcrete": ((0.60, 0.59, 0.56), 0.0, 0.85, {}),
    "M_DockWall": ((0.47, 0.46, 0.44), 0.0, 0.90, {}),
    "M_DockWallDark": ((0.20, 0.21, 0.20), 0.0, 0.90, {}),
    "M_Timber": ((0.30, 0.20, 0.12), 0.0, 0.85, {}),
    "M_SidewalkConcrete": ((0.62, 0.61, 0.58), 0.0, 0.85, {}),
    "M_DeckPaving": ((0.64, 0.60, 0.55), 0.0, 0.80, {}),
    "M_Membrane": ((0.95, 0.95, 0.93), 0.0, 0.60, {}),
    "M_Carousel": ((0.85, 0.55, 0.20), 0.0, 0.50, {}),
    "M_GarageOpening": ((0.05, 0.05, 0.06), 0.0, 0.90, {}),
    "M_HotelBrick": ((0.55, 0.38, 0.30), 0.0, 0.85, {}),
    "M_RoofRib": ((0.32, 0.50, 0.43), 0.4, 0.45, {}),
    "M_GlassDark": ((0.05, 0.07, 0.09), 0.5, 0.10, {}),
    "M_ParkPaver": ((0.58, 0.55, 0.50), 0.0, 0.80, {}),
    "M_MosaicBlue": ((0.15, 0.30, 0.60), 0.0, 0.50, {}),
    "M_MosaicYellow": ((0.85, 0.65, 0.15), 0.0, 0.50, {}),
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
    if "alpha" in extra:
        b.inputs["Alpha"].default_value = extra["alpha"]
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    if "emit" in extra:
        b.inputs["Emission Color"].default_value = (*rgb, 1)
        b.inputs["Emission Strength"].default_value = extra["emit"]
    MATS[name] = m
    return m


# ------------------------------------------------------------------ geometry builder
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


def export(name, objs, meta=None):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=f"{OUT}/{name}.glb", export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_materials="EXPORT", export_image_format="NONE")
    lo = Vector((1e9, 1e9, 1e9))
    hi = -lo
    for o in objs:
        for v in o.data.vertices:
            co = o.matrix_world @ v.co
            lo = Vector(map(min, lo, co))
            hi = Vector(map(max, hi, co))
    tris = tri_count(objs)
    mats = []
    for o in objs:
        for m in o.data.materials:
            if m.name not in mats:
                mats.append(m.name)
    d = {"file": f"SourceArt/Landmarks/meshes/{name}.glb", "tris": tris,
         "bbox_min_m": [round(c, 3) for c in lo], "bbox_max_m": [round(c, 3) for c in hi],
         "size_m": [round(c, 3) for c in (hi - lo)], "materials": mats}
    d.update(meta or {})
    META[name] = d
    print(f"exported {name}: {tris} tris, size {tuple(round(c, 2) for c in hi - lo)}, mats {mats}")
    if tris > 80000:
        print("WARNING: over the 80k triangle budget:", name)


# ================================================================== 1. Cloud Gate
BEAN = dict(A=10.0, B=6.4, r0=3.6, r1=2.2, rs=0.58, rp=3.0, h0=6.0, h1=2.17, hs=0.58, hp=3.0, Q=0.56, B0=2.74, C0=2.93, cx=7.0, cy=5.3, e=4)


def cloud_gate():
    """The Bean: 20 m long (Blender X), 12.8 m wide (Y), 10 m tall; 3.6-3.7 m arch on the long sides; omphalos apex 8.2 m.
    Analytic closed surface z = M(x,y) + H(x,y)*dz over a cube-sphere direction d (x = A dx, y = B dy):
      M = rim(u) + Q (1 - rho^2) + B0 phi,  H = hc(u) - C0 phi,  phi = (1 - t^4)^3 a compact bump for the omphalos.
    M and H are smooth, so the surface is smooth everywhere (no poles: cube-sphere mesh), then z is normalised to 0..10."""
    P = BEAN
    A, Bw = P["A"], P["B"]

    def surf(d):
        dx, dy, dz = d
        x, y = A * dx, Bw * dy
        u = x / A
        rim = P["r0"] + P["r1"] * math.exp(-abs(u / P["rs"]) ** P["rp"])
        hc = P["h0"] - P["h1"] * math.exp(-abs(u / P["hs"]) ** P["hp"])
        t = math.sqrt((x / P["cx"]) ** 2 + (y / P["cy"]) ** 2)
        ph = (1 - t ** P["e"]) ** 3 if t < 1 else 0.0
        M = rim + P["Q"] * (dz * dz) + P["B0"] * ph
        H = hc - P["C0"] * ph
        return Vector((x, y, M + H * dz))

    NX, NY, NZ = 92, 60, 48            # cube lattice -> 2(NX NY + NY NZ + NX NZ) quads = 25,296 quads (50.6k tris)
    def warp(c):                       # equal-angle cube-sphere
        return math.tan(c * math.pi / 4)
    verts = {}
    pts = {}

    def key_pt(i, j, k):
        if (i, j, k) not in pts:
            c = Vector((warp(2 * i / NX - 1), warp(2 * j / NY - 1), warp(2 * k / NZ - 1))).normalized()
            pts[(i, j, k)] = surf(c)
        return pts[(i, j, k)]
    # faces of the lattice cube: (fixed axis, value, axis_u, axis_v) chosen so u x v = outward normal
    faces = [
        (0, NX, 1, 2), (0, 0, 2, 1),          # +X: y,z ; -X: z,y
        (1, NY, 2, 0), (1, 0, 0, 2),          # +Y: z,x ; -Y: x,z
        (2, NZ, 0, 1), (2, 0, 1, 0),          # +Z: x,y ; -Z: y,x
    ]
    N = (NX, NY, NZ)
    zs = []
    quads = []
    for ax, val, au, av in faces:
        for a in range(N[au]):
            for b in range(N[av]):
                ids = []
                for da, db in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    ijk = [0, 0, 0]
                    ijk[ax] = val
                    ijk[au] = a + da
                    ijk[av] = b + db
                    ids.append(tuple(ijk))
                quads.append(ids)
    for q in quads:
        for k in q:
            key_pt(*k)
    zmin = min(p.z for p in pts.values())
    zmax = max(p.z for p in pts.values())
    s = 10.0 / (zmax - zmin)
    Bd = Builder()
    for k, p in pts.items():
        verts[k] = Bd.bm.verts.new((p.x, p.y, (p.z - zmin) * s))
    m = mat("M_MirrorSteel")
    for q in quads:
        Bd._poly([verts[k] for k in q], m, None, True)
    ob = Bd.finish("LM_CloudGate", sharp_angle=89.0)
    # measure the arch (lowest underside point on the x = 0 section) for the metadata
    me = ob.data
    arch = min((v.co.z for v in me.vertices if abs(v.co.x) < 0.25 and v.co.z > 1.0 and abs(v.co.y) > 3.5), default=None)
    omph = min((v.co.z for v in me.vertices if abs(v.co.x) < 0.3 and abs(v.co.y) < 0.3), default=None)
    export("LM_CloudGate", [ob], {
        "pivot": "base centre (0,0,0); stands on its two feet at x = +/-7 m",
        "long_axis": "Blender X (Unreal Y); the long sides face -Y/+Y (Unreal +X/-X)",
        "key_heights_m": {"top": 10.0, "arch_on_long_sides": round(arch or 0, 2), "omphalos_apex": round(omph or 0, 2)},
        "notes": "analytic smooth surface, smooth normals; M_MirrorSteel metallic 1 roughness 0.03"})


# ================================================================== 2. Buckingham Fountain
# Real: pool 280 ft (85 m), basins 103 / 60 / 24 ft (31.4 / 18.3 / 7.3 m), upper lip ~7.6 m, centre jet 150 ft (46 m),
# Georgia pink marble, four pairs of bronze sea horses (Marcel Loyau) in the pool, one pair per Lake Michigan state.
FOUNT = dict(pool_r=42.7, pool_water=0.32, low_R=15.7, low_water=1.72, low_lip=1.95, mid_R=9.15, mid_water=5.45,
             mid_lip=5.55, up_R=3.65, up_water=9.17, up_lip=9.4, finial=11.3, horse_r=29.4, basket_r=29.0)
# the body was first modelled with a 7.6 m upper lip from the ground; FOUNT_Z maps those heights to the real ones
FOUNT_Z = [(0.0, 0.0), (1.05, 1.25), (1.64, 1.95), (3.25, 3.9), (4.76, 5.55), (6.62, 7.9), (7.62, 9.4), (9.27, 11.3)]


def fount_z(z):
    for (a0, b0), (a1, b1) in zip(FOUNT_Z, FOUNT_Z[1:]):
        if z <= a1:
            return b0 + (b1 - b0) * (z - a0) / (a1 - a0)
    return z + FOUNT_Z[-1][1] - FOUNT_Z[-1][0]


def scallop(n, sharp=0.5):
    """Rococo lobes: n lobes round the circle, cusps between them (0 at cusps, 1 at lobe centres)."""
    return lambda th: abs(math.cos(n * th / 2)) ** sharp


def flute(n):
    return lambda th: math.cos(n * th)


def seahorse(B, origin, yaw, sc=0.72):
    """Stylised Art-Deco hippocamp (verdigris bronze), rearing out of the water; local front = -Y, origin at water level.
    sc scales the figure (0.72 -> about 2.8 m tall, as in the photos next to the 1.8 m lower-basin wall)."""
    Rz = Matrix.Rotation(yaw, 3, "Z") @ Matrix.Diagonal((sc, sc, sc))
    o = Vector(origin)
    T = lambda pts: [o + Rz @ Vector(p) for p in pts]
    _tube = B.tube
    B_tube = lambda path, radii, *a, **k: _tube(path, [r * sc for r in radii], *a, **k)
    _ell = B.ellipsoid
    B_ell = lambda c, radii, *a, **k: _ell(c, tuple(r * (1.0 if "rot" in k else sc) for r in radii), *a, **k)   # rot already scales
    br = mat("M_Verdigris")
    side = (1, 0, 0)          # tube 'up' hint: keeps the frame's second axis on world X for paths in the YZ plane
    # neck / chest
    B_tube(T([(0, 0.3, 0.1), (0, 0.05, 0.5), (0, -0.25, 1.4), (0, -0.4, 2.2), (0, -0.3, 2.85), (0, -0.05, 3.25)]),
           [0.85, 0.8, 0.68, 0.52, 0.42, 0.36], br, 14, up=Rz @ Vector(side), aspect=[(1, 0.85)] * 6)
    # head, muzzle forward-down
    B_tube(T([(0, 0.08, 3.15), (0, -0.25, 3.45), (0, -0.7, 3.46), (0, -1.1, 3.26), (0, -1.38, 3.04)]),
           [0.36, 0.4, 0.34, 0.26, 0.19], br, 14, up=Rz @ Vector(side), aspect=[(1, 0.78)] * 5)
    B_ell(o + Rz @ Vector((0, -1.4, 3.03)), (0.16, 0.13, 0.19), br, 12, 6, rot=Rz @ Matrix.Rotation(-0.6, 3, "X"))   # muzzle
    for s in (-1, 1):
        B_tube(T([(s * 0.17, -0.12, 3.62), (s * 0.24, 0.12, 4.0)]), [0.09, 0.012], br, 8, up=Rz @ Vector(side))          # ears
        B_ell(o + Rz @ Vector((s * 0.27, -0.55, 3.55)), (0.06, 0.1, 0.07), br, 8, 5)                             # eyes
        # forelegs, bent, ending in webbed fins
        B_tube(T([(s * 0.4, -0.45, 1.55), (s * 0.46, -1.0, 1.78), (s * 0.46, -1.45, 1.45), (s * 0.43, -1.58, 0.95), (s * 0.41, -1.86, 0.74)]),
               [0.36, 0.3, 0.26, 0.22, 0.2], br, 10, up=Rz @ Vector(side))
        B_ell(o + Rz @ Vector((s * 0.41, -2.05, 0.7)), (0.2, 0.34, 0.07), br, 10, 5, rot=Rz @ Matrix.Rotation(0.35, 3, "X"))
    # mane fin along the back of the neck (thin in X)
    B_tube(T([(0, 0.78, 0.6), (0, 0.47, 1.4), (0, 0.22, 2.2), (0, 0.2, 2.85), (0, 0.33, 3.35), (0, 0.27, 3.78)]),
           [0.25, 0.34, 0.34, 0.31, 0.24, 0.08], br, 10, up=Rz @ Vector(side), aspect=[(1, 0.14)] * 6)
    # fish tail curling up behind
    tail = [(0, 0.35, 0.25), (0, 1.2, 0.3), (0, 2.0, 0.45), (0, 2.7, 0.85), (0, 3.02, 1.4), (0, 2.87, 2.0), (0, 2.42, 2.27),
            (0, 2.06, 2.02), (0, 2.0, 1.62)]
    B_tube(T(tail), [0.55, 0.5, 0.45, 0.38, 0.31, 0.23, 0.17, 0.13, 0.1], br, 12, up=Rz @ Vector(side), aspect=[(1, 0.85)] * 9)
    for a in (-0.5, 0.5):     # forked tail fin
        B_ell(o + Rz @ Vector((0, 1.92 + 0.12 * a, 1.32)), (0.06, 0.22, 0.42), br, 10, 6, rot=Rz @ Matrix.Rotation(0.6 * a + 0.3, 3, "X"))
    for z0, y0 in ((0.9, 2.35), (1.6, 2.95)):   # dorsal fin tufts on the tail
        B_ell(o + Rz @ Vector((0, y0 + 0.25, z0 + 0.15)), (0.05, 0.35, 0.18), br, 8, 5, rot=Rz @ Matrix.Rotation(-0.7, 3, "X"))


def buckingham_fountain():
    """Georgia pink marble fountain (Bennett, Loyau, Lambert, 1927): the three-tier body (lower 103 ft / middle 60 ft /
    upper 24 ft basins, upper lip 25 ft above the lower basin's water), the quatrefoil pool with diagonal bastions
    (pool_outline, 85.4 m across), its rounded coping, four pairs of verdigris sea horses on the diagonals and four
    bronze jet baskets on the axes. Built about local Z; the four-fold symmetry fits the plan frame unrotated."""
    F = FOUNT
    B = Builder()
    pm = mat("M_PinkMarble")
    wat = mat("M_Water")
    # --- lower basin (24 rococo lobes on the lip, gadroons on the belly)
    lowf = [scallop(24), flute(48)]
    B.lathe([(15.0, 0.0), (15.0, 0.22), (14.75, 0.28), (14.75, 0.45), (14.9, 0.55), (15.15, 0.8, 0.03, 0, 1), (15.4, 1.05, 0.04, 0, 1),
             (15.6, 1.3, 0.1, 0.0), (15.72, 1.45, 0.18, 0.04), (15.72, 1.56, 0.2, 0.1), (15.6, 1.64, 0.18, 0.12), (15.4, 1.62, 0.12, 0.08),
             (15.3, 1.52, 0.06, 0.03), (15.28, 1.40), (15.25, 1.05), (5.2, 1.05)], pm, 192, lowf)
    # central platform + middle pedestal (fluted shaft)
    B.lathe([(5.2, 1.05), (5.2, 1.78), (5.05, 1.85), (3.6, 1.85)], pm, 96)
    B.lathe([(3.6, 1.85), (3.6, 2.05), (3.3, 2.15), (3.0, 2.3), (2.5, 2.4), (2.25, 2.5, 0.07, 0, 0), (2.15, 2.9, 0.07, 0, 0), (2.2, 3.0),
             (2.6, 3.12), (2.75, 3.22), (2.3, 3.25)], pm, 120, [flute(20)])
    # --- middle basin (16 lobes, shell ribs under the bowl)
    midf = scallop(16)
    B.lathe([(2.2, 3.15), (3.5, 3.2), (5.2, 3.38), (6.8, 3.65, 0.0, -0.07), (7.9, 3.95, 0.05, -0.08), (8.6, 4.25, 0.12, 0.03),
             (9.0, 4.5, 0.18, 0.06), (9.2, 4.66, 0.22, 0.1), (9.12, 4.76, 0.2, 0.13), (8.95, 4.74, 0.14, 0.09), (8.85, 4.62, 0.07, 0.04),
             (8.83, 4.5), (8.8, 4.25), (1.75, 4.25)], pm, 160, midf)
    # upper pedestal
    B.lathe([(1.75, 4.25), (1.75, 4.72), (1.55, 4.8), (1.35, 4.95), (1.05, 5.05, 0.04, 0), (0.95, 6.2, 0.04, 0), (1.0, 6.3), (1.3, 6.45),
             (1.35, 6.55), (0.95, 6.62)], pm, 80, flute(14))
    # --- upper basin (10 lobes) and finial
    B.lathe([(0.9, 6.58), (1.6, 6.62), (2.4, 6.75), (3.0, 6.95, 0.04, -0.05), (3.4, 7.2, 0.1, 0.0), (3.62, 7.42, 0.14, 0.06),
             (3.7, 7.55, 0.15, 0.09), (3.6, 7.62, 0.13, 0.1), (3.45, 7.6, 0.09, 0.06), (3.38, 7.5, 0.04, 0.02), (3.36, 7.42), (3.34, 7.25),
             (0.95, 7.25)], pm, 100, scallop(10))
    B.lathe([(0.95, 7.25), (0.95, 7.7), (0.75, 7.82), (0.55, 7.95), (0.7, 8.15), (0.82, 8.4), (0.7, 8.62), (0.45, 8.78), (0.28, 8.92),
             (0.34, 9.05), (0.26, 9.18), (0.12, 9.25), (0.0, 9.27)], pm, 32)
    # console brackets under the middle and upper basins
    for k in range(8):
        a = 2 * math.pi * (k + 0.5) / 8
        r_, n_ = Vector((math.cos(a), math.sin(a), 0)), Vector((math.sin(a), -math.cos(a), 0))
        B.prism(n_ * 0.22, r_, (0, 0, 1), [(2.1, 2.45), (2.45, 2.45), (3.4, 2.85), (4.6, 3.2), (5.1, 3.36), (5.1, 3.46), (2.1, 3.3)], 0.44, pm)
    for k in range(6):
        a = 2 * math.pi * (k + 0.5) / 6
        r_, n_ = Vector((math.cos(a), math.sin(a), 0)), Vector((math.sin(a), -math.cos(a), 0))
        B.prism(n_ * 0.12, r_, (0, 0, 1), [(0.9, 5.7), (1.1, 5.7), (1.7, 6.3), (2.3, 6.68), (2.3, 6.76), (0.9, 6.62)], 0.24, pm)
    # map the body's heights to the real ones (upper lip 25 ft above the lower basin's water)
    for v in B.bm.verts:
        v.co.z = fount_z(v.co.z)
    B.lathe([(15.29, F["low_water"]), (5.15, F["low_water"])], wat, 192)
    B.lathe([(8.84, F["mid_water"]), (1.7, F["mid_water"])], wat, 128)
    B.lathe([(3.37, F["up_water"]), (0.9, F["up_water"])], wat, 64)
    # --- the pool: rounded pink granite coping on the quatrefoil-with-bastions outline, floor and water
    edge = pool_outline(0.0, 28)
    prof = [(0.0, 0.0), (0.0, 0.42), (-0.12, 0.56), (-0.45, 0.62), (-0.78, 0.56), (-0.9, 0.42), (-0.9, F["pool_water"] - 0.05)]
    P = []
    N = vertex_normals(edge)
    for (x, y), (nx, ny, k) in zip(edge, N):
        P.append([Vector((x + nx * o * k, y + ny * o * k, z)) for o, z in prof])
    B.grid(P, pm, True, close_u=True)
    inner = offset_poly(edge, -0.9)
    B.face([(x, y, 0.02) for x, y in inner], mat("M_Concrete"))
    B.face([(x, y, F["pool_water"]) for x, y in inner], wat)
    # --- four pairs of sea horses (verdigris) on rock-and-reed plinths at the diagonal bastions, heads turned outward
    #     along the rim (Loyau's pairs are back to back); bronze jet baskets on the four axes
    for k in range(4):
        a = math.radians(45 + 90 * k)
        rad = Vector((math.cos(a), math.sin(a), 0))
        tng = Vector((-math.sin(a), math.cos(a), 0))
        c = rad * F["horse_r"]
        B.ellipsoid(c + Vector((0, 0, 0.0)), (3.4, 2.6, 0.8), mat("M_Verdigris"), 24, 6, rot=Matrix.Rotation(a, 3, "Z"), half=True)
        for s in (-1, 1):
            seahorse(B, c + tng * (1.35 * s) + Vector((0, 0, F["pool_water"] + 0.35)), a + math.pi / 2 + s * math.radians(62))
        ab = math.radians(90 * k)
        cb = Vector((math.cos(ab), math.sin(ab), 0)) * F["basket_r"]
        B.lathe([(0.95, 0.0), (0.95, 0.5), (0.78, 0.7, 0.06, 0, 0), (0.72, 1.6, 0.06, 0, 0), (0.95, 1.85), (1.0, 2.0), (0.4, 2.05), (0.0, 2.1)],
                mat("M_Verdigris"), 40, f=[flute(16)], center=(cb.x, cb.y, 0))
    ob = B.finish("LM_BuckinghamFountain", sharp_angle=40)
    export("LM_BuckinghamFountain", [ob], {
        "pivot": "fountain centre on the ground (0,0,0); place at the plan point %s with no rotation" % (str((731.6, -1300.15)),),
        "key_heights_m": {"pool_coping_top": 0.62, "pool_water": F["pool_water"], "lower_basin_lip": F["low_lip"], "lower_water": F["low_water"],
                          "middle_basin_lip": F["mid_lip"], "middle_water": F["mid_water"], "upper_basin_lip": F["up_lip"],
                          "upper_water": F["up_water"], "finial_top": F["finial"]},
        "diameters_m": {"pool_across_lobes": 85.4, "lower_basin": 31.4, "middle_basin": 18.3, "upper_basin": 7.3},
        "sea_horses": "4 pairs (8) on the diagonal bastions at radius %.1f m (OSM artwork nodes), verdigris" % F["horse_r"],
        "notes": "pool = four lobes r 25.8 m centred 16.9 m out + square bastions at (+/-30.5, +/-30.5) (OSM); jets: LM_BuckinghamJets"})


def _arc(B, p0, p1, apex, m, r0, r1, n=14, sides=6):
    """Parabolic water arc from p0 to p1 peaking at height apex (absolute z)."""
    p0, p1 = Vector(p0), Vector(p1)
    za, zb = p0.z, p1.z
    # z(t) = (1-t) za + t zb + 4 h t (1-t), choose h so the max reaches apex
    h = max(0.1, apex - max(za, zb))
    pts, rad = [], []
    for i in range(n + 1):
        t = i / n
        q = p0.lerp(p1, t)
        q.z = (1 - t) * za + t * zb + 4 * h * t * (1 - t) + (max(za, zb) - (1 - t) * za - t * zb) * 4 * t * (1 - t)
        pts.append(q)
        rad.append(r0 + (r1 - r0) * t)
    B.tube(pts, rad, m, sides, cap0=True, cap1=True)


def buckingham_jets():
    F = FOUNT
    B = Builder()
    j = mat("M_WaterJet")
    # central column (nozzle at 9.2 m, top at 46 m): a dense core inside a spray sheath that swells into a plume near the top
    nz = F["finial"] - 0.1
    B.lathe([(0.0, nz), (0.2, nz + 0.05), (0.26, 16), (0.36, 25), (0.5, 34), (0.66, 40), (0.8, 43.5), (0.6, 45.3), (0.25, 45.85), (0.0, 45.9)], j, 32)
    B.lathe([(0.0, nz + 0.15), (0.45, nz + 0.35), (0.6, 16), (0.85, 23), (1.15, 30), (1.5, 37), (1.85, 41.5), (2.0, 43.8), (1.7, 45.3), (1.0, 45.9),
             (0.0, 46.0)], j, 48)
    # basin cascades: water sheets falling off each lip
    for top, bot, segs in (((16.0, F["low_water"] + 0.05), (16.65, F["pool_water"]), 160), ((9.55, F["mid_water"] + 0.05), (10.05, F["low_water"]), 128),
                           ((3.95, F["up_water"] + 0.05), (4.35, F["mid_water"]), 64)):
        mid = ((top[0] * 0.35 + bot[0] * 0.65), (top[1] + bot[1]) / 2)
        sheet = [bot, mid, top]
        B.lathe(sheet, j, segs)
        B.lathe([(r - 0.05, z) for r, z in sheet[::-1]], j, segs)
    # lower basin ring: 20 jets arcing inward toward the middle basin
    for k in range(20):
        a = 2 * math.pi * (k + 0.5) / 20
        d = Vector((math.cos(a), math.sin(a), 0))
        _arc(B, d * 13.6 + Vector((0, 0, F["low_water"])), d * 10.0 + Vector((0, 0, F["low_water"])), 6.6, j, 0.06, 0.2)
    # middle basin ring: 16 jets arcing inward
    for k in range(16):
        a = 2 * math.pi * k / 16
        d = Vector((math.cos(a), math.sin(a), 0))
        _arc(B, d * 8.3 + Vector((0, 0, F["mid_water"])), d * 4.3 + Vector((0, 0, F["mid_water"])), 11.2, j, 0.05, 0.18)
    # upper ring: 8 tall jets round the finial, leaning out and falling back into the upper basin
    for k in range(8):
        a = 2 * math.pi * (k + 0.5) / 8
        d = Vector((math.cos(a), math.sin(a), 0))
        _arc(B, d * 1.6 + Vector((0, 0, F["up_water"])), d * 3.0 + Vector((0, 0, F["up_water"])), 17.5, j, 0.05, 0.16, n=16)
    # sea-horse spouts: from each mouth, arcing outward into the great pool
    for k in range(4):
        a = math.radians(45 + 90 * k)
        rad = Vector((math.cos(a), math.sin(a), 0))
        tng = Vector((-math.sin(a), math.cos(a), 0))
        for s in (-1, 1):
            # Loyau's sea horses spout high arcs in toward the fountain (photos)
            base = rad * F["horse_r"] + tng * (1.35 * s) + Vector((0, 0, F["pool_water"] + 0.35))
            mouth = base + tng * (1.6 * s) + Vector((0, 0, 2.5))
            land = rad * (F["horse_r"] - 11.0) + tng * (2.5 * s) + Vector((0, 0, F["pool_water"]))
            _arc(B, mouth, land, mouth.z + 6.0, j, 0.07, 0.3, n=18)
        ab = math.radians(90 * k)
        cb = Vector((math.cos(ab), math.sin(ab), 0)) * F["basket_r"]
        B.lathe([(0.0, 2.0), (0.3, 2.1), (0.45, 6.0), (0.7, 11.5), (0.35, 13.0), (0.0, 13.2)], j, 20, center=(cb.x, cb.y, 0))
    ob = B.finish("LM_BuckinghamJets", sharp_angle=60)
    export("LM_BuckinghamJets", [ob], {
        "pivot": "same origin as LM_BuckinghamFountain: place both at the same transform and toggle this one",
        "key_heights_m": {"centre_jet_top": 46.0, "centre_nozzle": round(F["finial"] - 0.1, 2)},
        "notes": "translucent spray shapes on M_WaterJet (use a two-sided translucent/additive material): centre core + spray sheath, "
                 "20 lower-ring + 16 middle-ring + 8 upper jets, 8 sea-horse spouts, cascades off all three lips"})


# ================================================================== 3. Centennial Wheel
# Real: 196 ft (60 m) tall (Kenny's brief: 61 m), 42 gondolas (8 riders), 21 spokes of 95 ft, six legs: two A-frame legs
# each side of the wheel plus two raked legs to the east for lateral load, 120 ft spread; boards at Pier Park level.
def _wheel_angles():
    return [2 * math.pi * k / WHEEL["N"] for k in range(WHEEL["N"])]


AXIS_Y = Matrix.Rotation(-math.pi / 2, 3, "X")       # local z -> +Y


def wheel_rotor():
    """Rotating part, ORIGIN = HUB CENTRE, axle along Blender Y. Gondola pivot k sits at
    (R_ATT sin(2 pi k/42), 0, -R_ATT cos(2 pi k/42)) relative to the hub (k = 0 at the bottom)."""
    B = Builder()
    w = mat("M_WheelWhite")
    st = mat("M_Steel")
    lt = mat("M_Light")
    RO, RI, YR = 27.6, 26.0, 1.75          # rim outer/inner chord radii, ring plane offset
    # hub drum with flanges (bore left open for the frame's axle)
    B.lathe([(0.95, -3.7), (2.7, -3.7), (2.7, -3.3), (2.0, -3.2), (2.0, 3.2), (2.7, 3.3), (2.7, 3.7), (0.95, 3.7)], w, 32, mtx=AXIS_Y)
    for s in (-1, 1):
        y = s * YR
        B.torus((0, y, 0), RO, 0.24, w, 126, 8, mtx=AXIS_Y)
        B.torus((0, y, 0), RI, 0.2, w, 126, 8, mtx=AXIS_Y)
        # zig-zag web between the chords
        n = 84
        for i in range(n):
            a0 = 2 * math.pi * i / n
            a1 = 2 * math.pi * (i + 0.5) / n
            a2 = 2 * math.pi * (i + 1) / n
            pi0 = Vector((RI * math.sin(a0), y, -RI * math.cos(a0)))
            po = Vector((RO * math.sin(a1), y, -RO * math.cos(a1)))
            pi2 = Vector((RI * math.sin(a2), y, -RI * math.cos(a2)))
            B.tube([pi0, po], [0.09, 0.09], w, 6)
            B.tube([po, pi2], [0.09, 0.09], w, 6)
    for k, th in enumerate(_wheel_angles()):
        dirv = Vector((math.sin(th), 0, -math.cos(th)))
        # gondola axle spanning the two rings + radial posts in each ring
        B.tube([dirv * WHEEL["R_ATT"] + Vector((0, -YR - 0.15, 0)), dirv * WHEEL["R_ATT"] + Vector((0, YR + 0.15, 0))], [0.13, 0.13], st, 8, True, True)
        for s in (-1, 1):
            B.tube([dirv * RI + Vector((0, s * YR, 0)), dirv * RO + Vector((0, s * YR, 0))], [0.12, 0.12], w, 6)
        if k % 2 == 0:
            # main spoke pair (21 spokes): hub flange -> inner chord, tapered, with an LED strip on the outer face
            for s in (-1, 1):
                a = dirv * 2.55 + Vector((0, s * 3.45, 0))
                b = dirv * RI + Vector((0, s * YR, 0))
                B.tube([a, a.lerp(b, 0.5), b], [0.34, 0.28, 0.22], w, 10)
                off = Vector((0, s * 1, 0)) * 0.26
                B.beam(a.lerp(b, 0.06) + off * 1.25, b + off, 0.07, 0.07, lt, up=(0, 1, 0))
                # tension rods crossing to the neighbouring gondola nodes
                for dk in (-1, 1):
                    th2 = th + dk * 2 * math.pi / WHEEL["N"]
                    d2 = Vector((math.sin(th2), 0, -math.cos(th2)))
                    B.tube([dirv * 2.3 + Vector((0, s * 3.3, 0)), d2 * RI + Vector((0, s * YR, 0))], [0.06, 0.06], w, 4)
    ob = B.finish("LM_CentennialWheel_Rotor", sharp_angle=60)
    export("LM_CentennialWheel_Rotor", [ob], {
        "pivot": "HUB CENTRE (0,0,0). Place at frame origin + (0,0,%.1f) m (Unreal Z +%d cm). Spins about Blender Y = Unreal X (roll)."
                 % (WHEEL["HUB"], WHEEL["HUB"] * 100),
        "gondola_attachment": {"count": WHEEL["N"], "radius_m": WHEEL["R_ATT"],
                               "blender_offset_from_hub_m": "(R sin(2 pi k/42), 0, -R cos(2 pi k/42)), k = 0 at the bottom",
                               "unreal_offset_from_hub_cm": "(0, -R sin(2 pi k/42), -R cos(2 pi k/42)) * 100"},
        "rim": {"outer_chord_radius_m": RO, "inner_chord_radius_m": RI, "ring_planes_y_m": [-YR, YR]},
        "notes": "21 main spoke pairs (LED strips on M_Light) + crossing tension rods; gondola axles on M_Steel"})


def wheel_frame():
    """Static part: axle at (0, 0, HUB) along Y, two A-frames (y = +/-5.8), two raked back legs to +Y, base platform with
    boarding decks on both sides of the gondola path. Origin = ground point under the hub."""
    B = Builder()
    w = mat("M_WheelWhite")
    st = mat("M_Steel")
    con = mat("M_Concrete")
    H = WHEEL["HUB"]
    PZ = 0.6                                             # platform top
    B.boxmm((-18, -9, 0), (18, 26, PZ), con)            # base platform
    B.tube([(0, -6.7, H), (0, 6.7, H)], [0.9, 0.9], st, 20, True, True)     # axle
    for s in (-1, 1):
        B.box((0, s * 5.8, H), (2.6, 1.3, 2.6), w)                          # bearing housings
        B.box((0, s * 5.8, H - 1.6), (3.4, 1.6, 1.2), w)
    # A-frames
    top_z = H - 1.8
    legs = []
    for s in (-1, 1):
        y = s * 5.8
        for sx in (-1, 1):
            a = Vector((sx * 1.2, y, top_z))
            b = Vector((sx * 17.0, s * 6.3, PZ + 0.8))
            B.tube([b, b.lerp(a, 0.5), a], [0.9, 0.78, 0.66], w, 14, cap1=True)
            legs.append((a, b))
            B.box((b.x, b.y, PZ + 0.4), (3.0, 3.0, 0.8), con)                # footing
        # cross tie in each A
        zt = 14.0
        t = (zt - (PZ + 0.8)) / (top_z - (PZ + 0.8))
        xl = 17.0 + (1.2 - 17.0) * t
        yl = s * (6.3 + (5.8 - 6.3) * t)
        B.tube([(-xl, yl, zt), (xl, yl, zt)], [0.45, 0.45], w, 10)
        B.tube([(0, yl, zt), (0, y, top_z - 1.0)], [0.4, 0.4], w, 10)            # king post up to the bearing
    # raked back legs (east / +Y) for lateral load
    for sx in (-1, 1):
        a = Vector((sx * 0.8, 6.6, H - 0.6))
        b = Vector((sx * 8.0, 24.0, PZ + 0.8))
        B.tube([b, b.lerp(a, 0.5), a], [0.75, 0.66, 0.56], w, 12, cap1=True)
        B.box((b.x, b.y, PZ + 0.4), (2.6, 2.6, 0.8), con)
    # boarding station: decks either side of the gondola path, steps, canopies
    deck = 1.0
    for s in (-1, 1):
        y0, y1 = sorted((s * 1.35, s * 6.5))
        B.boxmm((-8, y0, PZ), (8, y1, deck), con)
        for k in range(2):                                                    # two 0.2 m steps at both ends
            for sx in (-1, 1):
                x0 = sx * (8 + 0.35 * (k + 1))
                B.boxmm((min(x0, sx * 8), y0, PZ), (max(x0, sx * 8), y1, deck - 0.2 * (k + 1)), con)
        # gate rail along the platform edge
        ye = s * 1.45
        for x in [-7.5 + 1.5 * i for i in range(11)]:
            B.box((x, ye, deck + 0.55), (0.06, 0.06, 1.1), mat("M_Railing"))
        B.box((0, ye, deck + 1.1), (15.2, 0.06, 0.06), mat("M_Railing"))
        # canopy (clear of the rim: |y| >= 2.4)
        ya, yb = sorted((s * 2.4, s * 7.0))
        B.boxmm((-9, ya, 6.0), (9, yb, 6.35), w)
        for x in (-8.3, 0.0, 8.3):
            B.box((x, s * 6.4, (deck + 6.0) / 2), (0.3, 0.3, 6.0 - deck), st)
        B.boxmm((-8.8, min(ya, yb) + 0.1, 5.95), (8.8, max(ya, yb) - 0.1, 6.0), mat("M_Light"))
    ob = B.finish("LM_CentennialWheel_Frame", sharp_angle=50)
    export("LM_CentennialWheel_Frame", [ob], {
        "pivot": "ground point under the hub (0,0,0); hub centre at (0,0,%.1f) m" % H,
        "key_heights_m": {"hub": H, "platform_top": PZ, "boarding_deck": deck, "overall_top_of_rim": round(H + 27.6 + 0.24, 2)},
        "notes": "wheel plane = Blender XZ (Unreal YZ); back legs rake toward Blender +Y (Unreal -X); platform 46 x 40 m"})


def wheel_gondola():
    """One enclosed 8-seat cabin, ORIGIN = hanger pivot on the rotor axle; hangs down to z = -3.2 (floor bottom).
    Keep it upright (world rotation fixed) while its pivot follows the rotor."""
    B = Builder()
    g = mat("M_Gondola")
    gl = mat("M_Glass")
    st = mat("M_Steel")
    a, b = 1.3, 1.0                                      # half length (x, along travel at the bottom) / half width (y)
    n = 4.0
    outline = []
    for i in range(40):
        t = 2 * math.pi * i / 40
        c, s_ = math.cos(t), math.sin(t)
        outline.append((a * math.copysign(abs(c) ** (2 / n), c), b * math.copysign(abs(s_) ** (2 / n), s_)))
    rows = lambda zs: [(sc, sc, z, 0, 0) for sc, z in zs]
    B.sweep(outline, g, rows([(0.0, -3.2), (0.82, -3.2), (0.95, -3.14), (1.0, -3.02), (1.0, -2.62)]))
    B.sweep(outline, gl, rows([(1.0, -2.62), (1.0, -1.42)]))
    B.sweep(outline, g, rows([(1.0, -1.42), (1.0, -1.18), (0.95, -1.06), (0.8, -0.98), (0.0, -0.96)]))
    # window mullions + door frames
    for t in [2 * math.pi * (i + 0.5) / 8 for i in range(8)]:
        c, s_ = math.cos(t), math.sin(t)
        x, y = a * math.copysign(abs(c) ** (2 / n), c), b * math.copysign(abs(s_) ** (2 / n), s_)
        B.box((x * 1.01, y * 1.01, -2.02), (0.09, 0.09, 1.2), g)
    # hanger: sleeve on the axle, two arms, cross beam on the roof
    B.tube([(0, -1.15, 0), (0, 1.15, 0)], [0.2, 0.2], st, 10, True, True)
    for s in (-1, 1):
        B.box((0, s * 1.08, -0.5), (0.22, 0.1, 1.05), st)
    B.box((0, 0, -0.98), (0.4, 2.26, 0.12), st)
    # interior: floor and two benches so translucent glass doesn't look empty
    B.boxmm((-1.15, -0.85, -3.0), (1.15, 0.85, -2.98), st)
    for s in (-1, 1):
        B.boxmm((min(s * 0.75, s * 1.15), -0.8, -3.0), (max(s * 0.75, s * 1.15), 0.8, -2.55), g)
    ob = B.finish("LM_CentennialWheel_Gondola", sharp_angle=50)
    export("LM_CentennialWheel_Gondola", [ob], {
        "pivot": "HANGER PIVOT (0,0,0) = the rotor's gondola axle; cabin hangs to z = -3.2 m",
        "size_note": "cabin 2.6 m (Blender X) x 2.0 m (Y) x 2.25 m, glass band 1.2 m",
        "placement": "for each k: position = hub + R_rotor(angle) * attachment_k, rotation = world upright (do not inherit rotor roll)"})


def centennial_wheel():
    wheel_frame()
    reset()
    wheel_rotor()
    reset()
    wheel_gondola()


# ================================================================== 4. Navy Pier (1916, Charles S. Frost; brick + terra cotta)
# Pier 3,300 ft long, ~292 ft (89 m) wide: modules are 90 m wide. Headhouse with twin belvedere towers at the west (shore)
# end, two-storey halls along the pier, the Grand Ballroom (100 ft dome, 80 ft ceiling) and two more towers at the east end.
def bays(width, n, w, y0, y1, arch=False, margin=0.0):
    """n evenly spaced openings across a wall of the given width (band-local y0..y1)."""
    step = (width - 2 * margin) / n
    return [(margin + step * (i + 0.5), w, y0, y1, arch) for i in range(n)]


def side_frame(side, x0, x1, y0, y1):
    """(origin, right, width) of the outward-facing wall on one side of a rectangle; up is +Z."""
    return {"-Y": ((x0, y0, 0), (1, 0, 0), x1 - x0), "+Y": ((x1, y1, 0), (-1, 0, 0), x1 - x0),
            "+X": ((x1, y0, 0), (0, 1, 0), y1 - y0), "-X": ((x0, y1, 0), (0, -1, 0), y1 - y0)}[side]


def block_walls(B, rect, bands, m, thick=0.45, sides=("-Y", "+Y", "-X", "+X"), fill=None, fill_inset=0.65):
    """Walls round a rectangle (x0, x1, y0, y1); bands = [(z0, z1, holes_fn(width) -> holes)] stacked bottom-up."""
    for sd in sides:
        o, r, w = side_frame(sd, *rect)
        for z0, z1, hf in bands:
            B.wall(Vector(o) + Vector((0, 0, z0)), r, (0, 0, 1), w, z1 - z0, thick, m, hf(w) if hf else (), fill, fill_inset,
                   edges=False)


def frame_ring(B, rect, z0, z1, proj, depth, m):
    """A non-overlapping ring of 4 boxes round a rectangle (cornices, string courses, base courses)."""
    x0, x1, y0, y1 = rect
    p, d = proj, depth
    B.boxmm((x0 - p, y0 - p, z0), (x1 + p, y0 + d, z1), m)
    B.boxmm((x0 - p, y1 - d, z0), (x1 + p, y1 + p, z1), m)
    B.boxmm((x0 - p, y0 + d, z0), (x0 + d, y1 - d, z1), m)
    B.boxmm((x1 - d, y0 + d, z0), (x1 + p, y1 - d, z1), m)


def belvedere_tower(B, cx, cy, size, shaft_top, bel_h, roof_h):
    """Square brick tower: windowed shaft, limestone quoins, open arcaded belvedere, cornice and pyramid roof."""
    br, ls, gl, rf = mat("M_Brick"), mat("M_Limestone"), mat("M_Glass"), mat("M_Roof")
    s2 = size / 2
    rect = (cx - s2, cx + s2, cy - s2, cy + s2)
    bands = [(0.0, 4.5, None)]
    z = 4.5
    while z + 4.0 <= shaft_top - 0.1:
        bands.append((z, z + 4.0, lambda w: [(w / 2, 1.1, 1.0, 2.9, True)]))
        z += 4.0
    bands.append((z, shaft_top, None))
    block_walls(B, rect, bands, br, 0.5, fill=gl)
    for sx in (-1, 1):                                                     # quoins
        for sy in (-1, 1):
            B.boxmm((cx + sx * s2 - (0.55 if sx > 0 else 0.03), cy + sy * s2 - (0.55 if sy > 0 else 0.03), 0.0),
                    (cx + sx * s2 + (0.03 if sx > 0 else 0.55), cy + sy * s2 + (0.03 if sy > 0 else 0.55), shaft_top), ls)
    frame_ring(B, rect, 0.0, 1.2, 0.12, 0.3, ls)                            # base course
    frame_ring(B, rect, shaft_top, shaft_top + 0.4, 0.3, 0.6, ls)           # string course
    zb = shaft_top + 0.4
    B.boxmm((cx - s2 + 0.3, cy - s2 + 0.3, shaft_top - 0.2), (cx + s2 - 0.3, cy + s2 - 0.3, zb), ls)   # belvedere floor
    for sd in ("-Y", "+Y", "-X", "+X"):                                     # open arcade, one big arch per face
        o, r, w = side_frame(sd, *rect)
        B.wall(Vector(o) + Vector((0, 0, zb)), r, (0, 0, 1), w, bel_h, 0.7, br, [(w / 2, size * 0.46, 0.0, bel_h * 0.5, True)],
               None, edges=False)
    zt = zb + bel_h
    frame_ring(B, rect, zt, zt + 0.55, 0.45, 0.8, ls)
    B.boxmm((cx - s2 + 0.3, cy - s2 + 0.3, zt - 0.3), (cx + s2 - 0.3, cy + s2 - 0.3, zt + 0.5), ls)   # belvedere ceiling
    B.pyramid((cx, cy, zt + 0.55), s2 + 0.45, s2 + 0.45, roof_h, rf)
    B.tube([(cx, cy, zt + 0.55 + roof_h - 0.3), (cx, cy, zt + 0.55 + roof_h + 1.2)], [0.12, 0.05], rf, 8, cap1=True)
    B.ellipsoid((cx, cy, zt + 0.55 + roof_h + 0.6), (0.28, 0.28, 0.28), rf, 12, 6)
    return zt + 0.55 + roof_h + 1.2


def navy_pier_headhouse():
    """West-end headhouse: 84 m wide (X) x 24 m deep, 17 m main block, central pavilion with a 9 m arched entrance,
    twin belvedere towers (to ~39 m). Front (entrance, facing the city) = -Y; the pier sheds attach to the back (+Y)."""
    B = Builder()
    br, ls, gl, rf = mat("M_Brick"), mat("M_Limestone"), mat("M_Glass"), mat("M_Roof")
    X, Y0, Y1 = 42.0, -12.0, 12.0
    ZC = 15.6
    wing_bands = [(0.0, 5.0, lambda w: bays(w, max(1, round(w / 4.2)), 2.4, 0.7, 3.4, True)),
                  (5.0, 9.0, lambda w: bays(w, max(1, round(w / 4.2)), 1.6, 0.9, 3.3)),
                  (9.0, 13.0, lambda w: bays(w, max(1, round(w / 4.2)), 1.6, 0.9, 3.3)),
                  (13.0, ZC, lambda w: bays(w, max(1, round(w / 4.2)), 1.2, 0.5, 1.9))]
    # front wings (outside the towers), back and sides
    for xa, xb in ((-X, -20.0), (20.0, X)):
        o, r, w = side_frame("-Y", xa, xb, Y0, Y1)
        for z0, z1, hf in wing_bands:
            B.wall(Vector(o) + Vector((0, 0, z0)), r, (0, 0, 1), w, z1 - z0, 0.5, br, hf(w), gl, 0.65, edges=False)
    block_walls(B, (-X, X, Y0, Y1), wing_bands, br, 0.5, sides=("+Y", "-X", "+X"), fill=gl)
    B.boxmm((-20.0, Y0, 0), (20.0, Y0 + 0.5, ZC), br)                      # wall behind pavilion/towers
    frame_ring(B, (-X, X, Y0, Y1), 0.0, 1.0, 0.12, 0.4, ls)                # base course
    frame_ring(B, (-X, X, Y0, Y1), 4.8, 5.15, 0.1, 0.4, ls)                # string course
    frame_ring(B, (-X, X, Y0, Y1), ZC, ZC + 0.6, 0.5, 0.7, ls)             # cornice
    B.boxmm((-X + 0.4, Y0 + 0.4, ZC - 0.2), (X - 0.4, Y1 - 0.4, ZC + 0.3), mat("M_RoofFlat"))   # flat roof
    block_walls(B, (-X + 0.2, X - 0.2, Y0 + 0.2, Y1 - 0.2), [(ZC + 0.6, ZC + 1.6, None)], br, 0.35)   # parapet
    frame_ring(B, (-X + 0.2, X - 0.2, Y0 + 0.2, Y1 - 0.2), ZC + 1.6, ZC + 1.8, 0.08, 0.5, ls)     # coping
    # central pavilion with the great arched entrance
    PX, PY0, PZ = 11.0, -14.5, 20.0
    o = Vector((-PX, PY0, 0))
    B.wall(o, (1, 0, 0), (0, 0, 1), 2 * PX, 14.0, 1.4, br, [(PX, 9.0, 0.0, 8.0, True)], gl, 0.85, segs=12, edges=False)
    B.wall(o + Vector((0, 0, 14.0)), (1, 0, 0), (0, 0, 1), 2 * PX, PZ - 14.0, 0.6, br, bays(2 * PX, 3, 1.8, 0.8, 3.6, True), gl, edges=False)
    B.boxmm((-PX, PY0, 0), (PX, Y0 + 0.5, 0.01), ls)
    B.boxmm((-PX, PY0 + 0.5, PZ - 0.2), (PX, Y0 + 0.6, PZ + 0.25), mat("M_RoofFlat"))    # pavilion roof
    for z0, z1, p in ((0.0, 1.0, 0.12), (13.6, 14.1, 0.15), (PZ, PZ + 0.6, 0.45)):
        B.boxmm((-PX - p, PY0 - p, z0), (PX + p, Y0, z1), ls)
    # arch surround (voussoir band) and the sign panel above it
    rr = 4.5
    for k in range(13):
        a = math.pi * k / 12
        c = Vector((-rr * math.cos(a) * 1.08, PY0 - 0.08, 8.0 + rr * math.sin(a) * 1.08))
        B.box(c, (1.1, 0.25, 0.75), ls, Matrix.Rotation(-(math.pi / 2 - a), 3, "Y"))
    B.boxmm((-5.0, PY0 - 0.14, 12.95), (5.0, PY0, 13.55), ls)
    block_walls(B, (-PX + 0.2, PX - 0.2, PY0 + 0.2, Y0 + 2.0), [(PZ + 0.6, PZ + 1.8, None)], br, 0.35, sides=("-Y",))
    B.boxmm((-PX + 0.1, PY0 + 0.1, PZ + 1.8), (PX - 0.1, PY0 + 0.65, PZ + 1.95), ls)           # parapet coping
    B.boxmm((-PX, Y0 - 0.1, ZC), (PX, Y0 + 0.6, PZ), br)                                     # pavilion back wall above the roof
    B.boxmm((-4.0, PY0 + 0.05, PZ + 1.8), (4.0, PY0 + 0.75, PZ + 3.2), ls)   # raised centre block
    # twin towers
    top = 0.0
    for sx in (-1, 1):
        top = belvedere_tower(B, sx * 15.5, -10.0, 9.0, 26.5, 5.0, 5.5)
    ob = B.finish("LM_NavyPierHeadhouse", sharp_angle=40)
    export("LM_NavyPierHeadhouse", [ob], {
        "pivot": "ground centre (0,0,0); entrance facade at y = -14.5 (Unreal +X)",
        "key_heights_m": {"main_cornice": ZC, "pavilion": PZ, "tower_belvedere": [26.9, 31.9], "tower_top": round(top, 2)},
        "connect": "back wall at y = +12: place LM_NavyPierShed rotated 180 deg about Z with its origin at y = +12 to run the pier toward +Y"})


def pier_railing(B, x, y0, y1, z=0.0, step=2.5):
    rl = mat("M_Railing")
    n = max(1, round(abs(y1 - y0) / step))
    for i in range(n + 1):
        y = y0 + (y1 - y0) * i / n
        y = min(max(y, min(y0, y1) + 0.04), max(y0, y1) - 0.04)          # end posts stay inside the module
        B.box((x, y, z + 0.55), (0.08, 0.08, 1.1), rl)
    for zz, h in ((1.08, 0.06), (0.62, 0.04), (0.18, 0.04)):
        B.boxmm((x - 0.04, min(y0, y1), z + zz - h / 2), (x + 0.04, max(y0, y1), z + zz + h / 2), rl)


def street_lamp(B, x, y, h=4.6):
    st, lt = mat("M_Railing"), mat("M_Light")
    B.tube([(x, y, 0), (x, y, 0.5), (x, y, h)], [0.16, 0.1, 0.07], st, 8, cap1=True)
    B.ellipsoid((x, y, h + 0.3), (0.3, 0.3, 0.36), lt, 12, 6)
    B.tube([(x, y, h + 0.62), (x, y, h + 0.8)], [0.12, 0.02], st, 8, cap1=True)


def navy_pier_shed():
    """60 m repeatable pier module, running from y = 0 to y = -60; 90 m wide (x +/-45); deck top z = 0 (solid dock
    down to z = -4). South (x < 0) promenade 15 m, south hall 24 m, glazed concourse 12 m, north hall 24 m,
    north drive 15 m (10 m road + 4 m walk). Railings along both pier edges. Ends closed so one module stands alone."""
    B = Builder()
    br, ls, gl, rf, con, asp, st = (mat(n) for n in ("M_Brick", "M_Limestone", "M_Glass", "M_Roof", "M_Concrete", "M_Asphalt", "M_Steel"))
    L = 60.0
    W2 = 45.0
    B.boxmm((-W2, -L, -4.0), (W2, 0.0, 0.0), con)                                 # deck / dock wall
    for sx in (-1, 1):
        x0, x1 = (W2, W2 + 0.25) if sx > 0 else (-W2 - 0.25, -W2)
        B.boxmm((x0, -L, -0.9), (x1, 0.0, -0.5), st)                               # rubbing strip
        pier_railing(B, sx * (W2 - 0.25), 0.0, -L)
    # north drive: road + curb + walk
    B.boxmm((31.0, -L, 0.0), (41.0, 0.0, 0.02), asp)
    B.boxmm((41.0, -L, 0.0), (41.25, 0.0, 0.15), ls)
    B.boxmm((41.25, -L, 0.0), (W2 - 0.3, 0.0, 0.15), con)
    for k in range(4):
        y = -7.5 - 15 * k
        street_lamp(B, -43.6, y)
        street_lamp(B, 43.5, y)
    # halls
    H_WALL, H_EAVE, H_RIDGE = 11.5, 13.0, 16.5
    outer_bands = [(0.0, 6.5, lambda w: bays(w, 8, 4.4, 0.0, 4.0, True)),
                   (6.5, H_WALL, lambda w: [(c + d, 1.9, 1.0, 3.8, False) for c, *_ in bays(w, 8, 1, 0, 1) for d in (-1.3, 1.3)]),
                   (H_WALL, H_EAVE, None)]
    inner_bands = [(0.0, 6.5, lambda w: bays(w, 8, 5.8, 0.4, 5.6, False)),
                   (6.5, H_WALL, lambda w: bays(w, 8, 4.6, 1.0, 4.0, False)),
                   (H_WALL, H_EAVE, None)]
    for sx in (-1, 1):
        xo, xi = sx * 30.0, sx * 6.0
        x0, x1 = min(xo, xi), max(xo, xi)
        rect = (x0, x1, -L, 0.0)
        out_side, in_side = ("-X", "+X") if sx < 0 else ("+X", "-X")
        block_walls(B, rect, outer_bands, br, 0.5, sides=(out_side,), fill=gl)
        block_walls(B, rect, inner_bands, br, 0.5, sides=(in_side,), fill=gl)
        block_walls(B, rect, [(0.0, H_EAVE, None)], br, 0.5, sides=("-Y", "+Y"))     # closed ends (hidden when tiled)
        # pilasters between bays on the outer wall, string course, cornice
        for i in range(9):
            y = -L * i / 8
            B.boxmm((xo - (0.35 if sx < 0 else 0.0), max(-L, y - 0.45), 0.0), (xo + (0.35 if sx > 0 else 0.0), min(0.0, y + 0.45), H_WALL), br)
        xa, xb = (xo - 0.45, xo + 0.2) if sx < 0 else (xo - 0.2, xo + 0.45)
        B.boxmm((xa, -L, 6.3), (xb, 0.0, 6.7), ls)
        B.boxmm((xa - (0.2 if sx < 0 else 0), -L, H_WALL), (xb + (0.2 if sx > 0 else 0), 0.0, H_WALL + 0.45), ls)
        B.boxmm((xa, -L, H_EAVE - 0.15), (xb, 0.0, H_EAVE + 0.1), ls)
        # gabled roof (ridge along Y) with brick gable ends
        xm = (x0 + x1) / 2
        e = H_EAVE
        B.face([(x0, 0.0, e), (x0, -L, e), (xm, -L, H_RIDGE), (xm, 0.0, H_RIDGE)], rf)
        B.face([(xm, 0.0, H_RIDGE), (xm, -L, H_RIDGE), (x1, -L, e), (x1, 0.0, e)], rf)
        B.face([(x0, 0.0, e), (xm, 0.0, H_RIDGE), (x1, 0.0, e)], br)
        B.face([(x1, -L, e), (xm, -L, H_RIDGE), (x0, -L, e)], br)
        # roof monitor (skylight strip) along the ridge
        B.boxmm((xm - 1.6, -L + 3.0, H_RIDGE - 0.6), (xm + 1.6, -3.0, H_RIDGE + 0.9), gl)
    # glazed barrel-vault concourse between the halls (spring 13 m, crown 19 m)
    R, ZS = 6.0, H_EAVE
    nphi = 16
    ys = [-L + L * i / 8 for i in range(9)]
    P = [[Vector((R * math.cos(math.pi * j / nphi), y, ZS + R * math.sin(math.pi * j / nphi))) for j in range(nphi + 1)] for y in ys]
    B.grid(P, gl, smooth=True)
    for y in ys:                                                                   # steel ribs (end ribs kept inside the module)
        y = min(-0.12, max(-L + 0.12, y))
        B.tube([(R * 1.02 * math.cos(math.pi * j / nphi), y, ZS + R * 1.02 * math.sin(math.pi * j / nphi)) for j in range(nphi + 1)],
               [0.12] * (nphi + 1), st, 6)
    B.tube([(0, 0.0, ZS + R * 1.03), (0, -L, ZS + R * 1.03)], [0.14, 0.14], st, 6)
    for yv, flip in ((0.0, False), (-L, True)):                                    # glazed ends
        pts = [(R * math.cos(math.pi * j / nphi), yv, ZS + R * math.sin(math.pi * j / nphi)) for j in range(nphi + 1)]
        pts = pts[::-1] if not flip else pts
        B.face(pts, gl)
        # end wall under the vault, facing out of the module, thickness inward
        B.wall((R, yv, 0.0) if not flip else (-R, yv, 0.0), (-1, 0, 0) if not flip else (1, 0, 0), (0, 0, 1), 2 * R, ZS, 0.3, br,
               [(R, 6.0, 0.0, 6.0, True)], gl, 0.5, edges=False)
    ob = B.finish("LM_NavyPierShed", sharp_angle=40)
    export("LM_NavyPierShed", [ob], {
        "pivot": "deck top at the module's start edge, pier centreline (0,0,0); module runs to y = -60 (Unreal +X 6000 cm)",
        "tiling": "repeat every 60 m along -Y (Unreal +X); end walls are closed and coincide back-to-back when tiled",
        "cross_section_x_m": {"edge_railings": [-44.75, 44.75], "promenade": [-45, -30], "south_hall": [-30, -6], "concourse": [-6, 6],
                               "north_hall": [6, 30], "road": [31, 41], "walk": [41.25, 44.7]},
        "key_heights_m": {"deck_top": 0.0, "dock_bottom": -4.0, "hall_cornice": H_WALL, "eaves": H_EAVE, "ridge": H_RIDGE,
                          "vault_crown": ZS + R},
        "notes": "set the lake surface ~1.5-2.5 m below the deck; lamps on M_Light"})


def navy_pier_ballroom():
    """East-end Grand Ballroom: 64 x 52 m brick base (13 m), drum and 100 ft (30.5 m) dome (crown ~30 m, lantern to ~36 m),
    two belvedere towers flanking the entrance pavilion. Front (toward the pier, west) = -Y."""
    B = Builder()
    br, ls, gl, rf = mat("M_Brick"), mat("M_Limestone"), mat("M_Glass"), mat("M_Roof")
    X, Y0, Y1 = 32.0, -26.0, 26.0
    ZC = 12.5
    bands = [(0.0, 7.0, lambda w: bays(w, max(1, round(w / 6.5)), 3.0, 0.8, 4.6, True)),
             (7.0, ZC, lambda w: bays(w, max(1, round(w / 6.5)), 2.2, 1.0, 4.2))]
    block_walls(B, (-X, X, Y0, Y1), bands, br, 0.5, fill=gl)
    frame_ring(B, (-X, X, Y0, Y1), 0.0, 1.0, 0.12, 0.4, ls)
    frame_ring(B, (-X, X, Y0, Y1), 6.8, 7.15, 0.1, 0.4, ls)
    frame_ring(B, (-X, X, Y0, Y1), ZC, ZC + 0.6, 0.5, 0.7, ls)
    B.boxmm((-X + 0.4, Y0 + 0.4, ZC - 0.2), (X - 0.4, Y1 - 0.4, ZC + 0.3), mat("M_RoofFlat"))
    block_walls(B, (-X + 0.2, X - 0.2, Y0 + 0.2, Y1 - 0.2), [(ZC + 0.6, ZC + 1.6, None)], br, 0.35)
    frame_ring(B, (-X + 0.2, X - 0.2, Y0 + 0.2, Y1 - 0.2), ZC + 1.6, ZC + 1.8, 0.08, 0.5, ls)
    # drum + dome + lantern, centred a little east of the middle
    cy = 4.0
    c = (0, cy, 0)
    B.lathe([(16.6, ZC + 0.3), (16.6, 18.0), (16.0, 18.0), (16.0, ZC + 0.3)], br, 96, center=c)
    B.lathe([(16.0, ZC + 0.3), (16.0, ZC + 0.31)], br, 96, center=c)
    B.lathe([(16.9, 17.6), (16.9, 18.3), (16.5, 18.5), (15.7, 18.5)], ls, 96, center=c)   # dome base cornice
    prof = [(15.6 * math.cos(t), 18.5 + 11.4 * math.sin(t)) for t in [math.pi / 2 * k / 14 for k in range(15)]]
    prof = [p for p in prof if p[0] >= 2.4] + [(2.4, 18.5 + 11.4 * math.sqrt(max(0.0, 1 - (2.4 / 15.6) ** 2)))]
    B.lathe(prof, rf, 96, center=c)
    zl = prof[-1][1]
    for k in range(16):                                                              # ribs
        a = 2 * math.pi * k / 16
        d = Vector((math.cos(a), math.sin(a), 0))
        pts = [Vector(c) + d * (r + 0.12) + Vector((0, 0, z + 0.05)) for r, z in prof]
        B.tube(pts, [0.22] * len(pts), ls, 6)
    B.lathe([(2.4, zl), (2.4, zl + 3.2)], gl, 24, center=c)                           # lantern
    for k in range(8):
        a = 2 * math.pi * k / 8
        B.box((2.45 * math.cos(a), cy + 2.45 * math.sin(a), zl + 1.6), (0.3, 0.3, 3.2), ls, Matrix.Rotation(a, 3, "Z"))
    B.lathe([(2.85, zl + 3.2), (2.85, zl + 3.6), (2.4, zl + 3.6), (1.6, zl + 4.6), (0.6, zl + 5.2), (0.0, zl + 5.3)], rf, 24, center=c)
    B.tube([(0, cy, zl + 5.2), (0, cy, zl + 6.8)], [0.1, 0.03], rf, 8, cap1=True)
    # clerestory windows round the drum
    for k in range(16):
        a = 2 * math.pi * (k + 0.5) / 16
        d = Vector((math.cos(a), math.sin(a), 0))
        t = Vector((-math.sin(a), math.cos(a), 0))
        base = Vector(c) + d * 16.68 + Vector((0, 0, ZC + 1.6))
        pts = [(-1.3, 0.0), (1.3, 0.0), (1.3, 2.3)] + [(1.3 * math.cos(math.pi * j / 8), 2.3 + 1.3 * math.sin(math.pi * j / 8)) for j in range(1, 8)] + [(-1.3, 2.3)]
        B.poly_local(base, t, (0, 0, 1), pts, gl)
        frame = [(-1.6, -0.25), (1.6, -0.25), (1.6, 2.3)] + [(1.6 * math.cos(math.pi * j / 8), 2.3 + 1.6 * math.sin(math.pi * j / 8)) for j in range(1, 8)] + [(-1.6, 2.3)]
        B.poly_local(base - d * 0.04, t, (0, 0, 1), frame, ls)
    # entrance pavilion between the towers
    PX, PY0, PZ = 8.0, -27.5, 16.0
    o = Vector((-PX, PY0, 0))
    B.wall(o, (1, 0, 0), (0, 0, 1), 2 * PX, 11.0, 1.4, br, [(PX, 7.0, 0.0, 6.0, True)], gl, 0.85, segs=12, edges=False)
    B.wall(o + Vector((0, 0, 11.0)), (1, 0, 0), (0, 0, 1), 2 * PX, PZ - 11.0, 0.6, br, bays(2 * PX, 3, 1.6, 0.9, 3.4, True), gl, edges=False)
    B.boxmm((-PX, PY0 + 0.5, PZ - 0.2), (PX, Y0 + 0.6, PZ + 0.25), mat("M_RoofFlat"))
    for z0, z1, p in ((0.0, 1.0, 0.12), (10.6, 11.0, 0.15), (PZ, PZ + 0.6, 0.45)):
        B.boxmm((-PX - p, PY0 - p, z0), (PX + p, Y0, z1), ls)
    for sx in (-1, 1):                                                                # pavilion side walls
        B.boxmm((PX - 0.01, PY0, 0.0) if sx > 0 else (-PX, PY0, 0.0), (PX, Y0, PZ) if sx > 0 else (-PX + 0.01, Y0, PZ), br)
    B.boxmm((-PX, Y0 + 0.1, ZC), (PX, Y0 + 0.7, PZ), br)                                     # pavilion back wall above the roof
    B.boxmm((-3.5, PY0 + 0.05, PZ + 0.6), (3.5, PY0 + 0.8, PZ + 2.0), ls)
    top = 0.0
    for sx in (-1, 1):
        top = belvedere_tower(B, sx * 27.0, -22.6, 8.0, 23.0, 4.5, 4.5)
    ob = B.finish("LM_NavyPierBallroom", sharp_angle=40)
    export("LM_NavyPierBallroom", [ob], {
        "pivot": "ground centre (0,0,0); entrance pavilion at y = -27.5 faces -Y (Unreal +X), i.e. back along the pier",
        "key_heights_m": {"cornice": ZC, "drum_top": 18.5, "dome_crown": round(zl, 2), "lantern_top": round(zl + 6.8, 2),
                          "towers_top": round(top, 2)},
        "dome": "30.5 m (100 ft) diameter, centred at (0, %.1f)" % cy,
        "connect": "the pier deck is not included: put it on the end of the last LM_NavyPierShed (deck 90 m wide)"})


def navy_pier():
    navy_pier_headhouse()
    reset()
    navy_pier_shed()
    reset()
    navy_pier_ballroom()


# ================================================================== 5. Chicago River bascule bridge parts
# DuSable (Michigan Avenue) Bridge, 1920: double-leaf trunnion bascule, 4 Beaux-Arts limestone bridge houses with relief
# sculptures (The Pioneers, The Discoverers, Defense, Regeneration), ornamental railings and lamp standards.
LEAF = dict(L=30.0, W=28.0, road=9.5, curb=10.0, walk_top=0.2, d_heel=5.0, d_tip=1.4)


def bridge_railing(B, x, y0, length=10.0, z0=0.0, end_posts=True):
    """Ornamental cast-iron railing running from y0 toward -Y: posts every 5 m with ball finials, rails,
    balusters below, a band of rings above. Height 1.15 m (finials 1.35 m)."""
    rl = mat("M_Railing")
    y1 = y0 - length
    n_posts = int(round(length / 5.0))
    for i in range(n_posts + 1):
        if not end_posts and i in (0, n_posts):
            continue
        y = y0 - 5.0 * i
        B.box((x, y, z0 + 0.075), (0.36, 0.36, 0.15), rl)
        B.box((x, y, z0 + 0.6), (0.26, 0.26, 0.9), rl)
        B.box((x, y, z0 + 1.09), (0.34, 0.34, 0.08), rl)
        B.ellipsoid((x, y, z0 + 1.25), (0.1, 0.1, 0.1), rl, 10, 5)
    ya, yb = y0, y1
    B.boxmm((x - 0.06, yb, z0 + 0.12), (x + 0.06, ya, z0 + 0.24), rl)          # bottom rail
    B.boxmm((x - 0.04, yb, z0 + 0.76), (x + 0.04, ya, z0 + 0.82), rl)          # mid rail
    B.boxmm((x - 0.07, yb, z0 + 1.0), (x + 0.07, ya, z0 + 1.08), rl)           # top rail
    B.tube([(x, ya, z0 + 1.12), (x, yb, z0 + 1.12)], [0.05, 0.05], rl, 6)      # handrail
    nb = int(round(length / 0.125))
    for i in range(nb):
        y = ya - (i + 0.5) * length / nb
        B.tube([(x, y, z0 + 0.24), (x, y, z0 + 0.76)], [0.018, 0.018], rl, 4)
    nr = int(round(length / 0.25))
    for i in range(nr):
        y = ya - (i + 0.5) * length / nr
        ring = [(x, y + 0.08 * math.cos(2 * math.pi * k / 8), z0 + 0.91 + 0.08 * math.sin(2 * math.pi * k / 8)) for k in range(9)]
        B.tube(ring, [0.014] * 9, rl, 4)


def bridge_railing10():
    B = Builder()
    bridge_railing(B, 0.0, 0.0, 10.0)
    ob = B.finish("LM_BridgeRailing10", sharp_angle=50)
    export("LM_BridgeRailing10", [ob], {
        "pivot": "railing start, base centreline (0,0,0); runs to y = -10 (Unreal +X 1000 cm); posts at 0, 5, 10 m",
        "key_heights_m": {"top_rail": 1.12, "finials": 1.35},
        "tiling": "repeat every 10 m; end posts coincide when tiled"})


def bridge_lamp(B, x, y, z0):
    """Twin-globe bridge lamp standard (5.8 m)."""
    rl, lt = mat("M_Railing"), mat("M_Light")
    B.box((x, y, z0 + 0.35), (0.6, 0.6, 0.7), rl)
    B.lathe([(0.24, z0 + 0.7), (0.17, z0 + 1.1), (0.12, z0 + 4.8), (0.16, z0 + 5.0), (0.0, z0 + 5.1)], rl, 12, center=(x, y, 0),
            f=flute(8))
    for s in (-1, 1):
        B.tube([(x, y, z0 + 4.95), (x, y + s * 0.45, z0 + 5.15), (x, y + s * 0.62, z0 + 5.35)], [0.05, 0.045, 0.04], rl, 6)
        B.ellipsoid((x, y + s * 0.62, z0 + 5.62), (0.24, 0.24, 0.3), lt, 12, 6)
    B.ellipsoid((x, y, z0 + 5.55), (0.27, 0.27, 0.33), lt, 12, 6)


def bridge_leaf():
    """One bascule leaf. ORIGIN = PIVOT: heel end of the deck at y = 0, deck top z = 0, pivot axis = Blender X
    (Unreal Y). The deck runs 30 m toward -Y (Unreal +X); 28 m wide. Opening: rotate about the origin so the tip rises
    (Blender rotation X negative = Unreal pitch positive). Counterweight hangs behind the pivot (y 0.4..6, z -1.4..-7),
    meant to sit in the abutment pit / below the approach road."""
    B = Builder()
    P = LEAF
    L, W2 = P["L"], P["W"] / 2
    asp, con, ls, stl = mat("M_Asphalt"), mat("M_Concrete"), mat("M_Limestone"), mat("M_BridgeSteel")
    # deck: roadway, curbs, sidewalks
    B.boxmm((-P["road"], -L, -0.1), (P["road"], 0.0, 0.0), asp)
    B.boxmm((-P["road"], -L, -0.4), (P["road"], 0.0, -0.1), stl)
    for s in (-1, 1):
        xa, xb = sorted((s * P["road"], s * P["curb"]))
        B.boxmm((xa, -L, -0.4), (xb, 0.0, P["walk_top"]), ls)
        xa, xb = sorted((s * P["curb"], s * W2))
        B.boxmm((xa, -L, -0.4), (xb, 0.0, P["walk_top"]), con)
        for k in range(3):
            bridge_railing(B, s * (W2 - 0.3), -10.0 * k, 10.0, P["walk_top"])
        for y in (-7.5, -22.5):
            bridge_lamp(B, s * (W2 - 0.95), y, P["walk_top"])
    depth = lambda y: P["d_tip"] + (P["d_heel"] - P["d_tip"]) * ((y + L) / L) ** 1.3
    # outer plate girders (fascia) with stiffeners and flanges
    for s in (-1, 1):
        x = s * (W2 - 0.1)
        n = 15
        top, bot = [], []
        for i in range(n + 1):
            y = -L * i / n
            top.append(Vector((x, y, -0.4)))
            bot.append(Vector((x, y, -0.4 - depth(y))))
        for i in range(n):
            q = [top[i], bot[i], bot[i + 1], top[i + 1]]          # normal -X
            if s > 0:
                q = q[::-1]                                         # outer web face must point away from the deck
            B.face([v + Vector((s * 0.06, 0, 0)) for v in q], stl)
            B.face([v - Vector((s * 0.06, 0, 0)) for v in q][::-1], stl)
            B.face([bot[i] + Vector((-0.06, 0, 0)), bot[i] + Vector((0.06, 0, 0)), bot[i + 1] + Vector((0.06, 0, 0)), bot[i + 1] + Vector((-0.06, 0, 0))], stl)
        for i in range(n + 1):
            y = -L * i / n
            B.box((x + s * 0.12, y, -0.4 - depth(y) / 2), (0.14, 0.3, depth(y)), stl)
        B.beam((x, 0, -0.4 - depth(0) - 0.1), (x, -L, -0.4 - depth(-L) - 0.1), 0.7, 0.2, stl)
        B.boxmm((x - 0.35, -L, -0.6), (x + 0.35, 0.0, -0.4), stl)
        # ornamental panel band on the fascia (limestone-coloured trim line)
        B.boxmm((x + s * 0.07 - 0.04, -L, -0.85), (x + s * 0.07 + 0.04, 0.0, -0.7), ls)
    # inner trusses
    for xg in (-4.5, 4.5, -11.0, 11.0):
        n = 10
        prev = None
        for i in range(n + 1):
            y = -L * i / n
            t = Vector((xg, y, -0.65))
            b = Vector((xg, y, -0.4 - depth(y) + 0.25))
            B.beam(t, b, 0.35, 0.35, stl, up=(1, 0, 0))
            if prev:
                pt, pb = prev
                B.beam(pt, t, 0.55, 0.5, stl, up=(0, 0, 1))
                B.beam(pb, b, 0.55, 0.5, stl, up=(0, 0, 1))
                B.beam(pt if i % 2 else pb, b if i % 2 else t, 0.3, 0.3, stl, up=(1, 0, 0))
            prev = (t, b)
    # floor beams + bottom lateral bracing
    for i in range(11):
        y = -L * i / 10
        B.boxmm((-W2 + 0.2, y - 0.2, -1.3), (W2 - 0.2, y + 0.2, -0.4), stl)
    for i in range(5):
        ya, yb = -L * i / 5, -L * (i + 1) / 5
        za, zb = -0.4 - depth(ya) + 0.25, -0.4 - depth(yb) + 0.25
        B.beam((-4.5, ya, za), (4.5, yb, zb), 0.25, 0.25, stl)
        B.beam((4.5, ya, za), (-4.5, yb, zb), 0.25, 0.25, stl)
    # tip nose plate and heel: trunnion bearings + counterweight
    B.boxmm((-W2, -L, -0.4 - P["d_tip"] - 0.2), (W2, -L + 0.25, -0.4), stl)
    for s in (-1, 1):
        B.tube([(s * (W2 - 0.4), 0, -1.1), (s * (W2 + 0.5), 0, -1.1)], [0.55, 0.55], stl, 16, True, True)
        B.boxmm((min(s * 4.5, s * 11.0) - 0.3, 0.0, -6.5), (max(s * 4.5, s * 11.0) + 0.3, 1.2, -0.5), stl)
    B.boxmm((-12.0, 0.4, -7.0), (12.0, 6.0, -1.4), con)
    B.boxmm((-W2 + 0.2, 0.0, -1.4), (W2 - 0.2, 0.4, -0.4), stl)
    ob = B.finish("LM_BridgeLeaf", sharp_angle=50)
    export("LM_BridgeLeaf", [ob], {
        "pivot": "ORIGIN = PIVOT (trunnion line at the heel, deck top level). Axis = Blender X = Unreal Y. Open by pitching the tip up "
                 "(Unreal +pitch; Blender rotation_euler.x negative). Real DuSable leaves open to ~80 deg.",
        "deck": {"length_m": L, "width_m": P["W"], "roadway_x_m": [-P["road"], P["road"]], "sidewalks_x_m": [[-W2, -P["curb"]], [P["curb"], W2]],
                 "deck_top_z": 0.0, "sidewalk_top_z": P["walk_top"]},
        "pair": "second leaf: same pivot height, rotated 180 deg about Z with its origin 60 m from the first along the leaf axis; tips meet at 30 m",
        "underside_depth_m": {"heel": P["d_heel"], "tip": P["d_tip"]},
        "counterweight": "y 0.4..6.0 m behind the pivot, z -1.4..-7.0 (keep it inside the abutment pit)"})


def tender_house():
    """Beaux-Arts limestone bridge house, 6 m (X, front width) x 8 m (Y), 12 m tall; relief sculpture panels on the
    front (-Y) and back (+Y) faces, arched windows and a bronze door on the sides, cornice and attic parapet."""
    B = Builder()
    ls, gl, br, rf = mat("M_Limestone"), mat("M_Glass"), mat("M_Bronze"), mat("M_Roof")
    HX, HY = 3.0, 4.0
    B.boxmm((-HX - 0.3, -HY - 0.3, 0.0), (HX + 0.3, HY + 0.3, 1.0), ls)                  # plinth
    B.boxmm((-HX - 0.15, -HY - 0.15, 1.0), (HX + 0.15, HY + 0.15, 1.2), ls)
    for k in range(3):                                                                   # rusticated plinth joints
        z = 0.25 + 0.25 * k
        B.boxmm((-HX - 0.33, -HY - 0.33, z), (HX + 0.33, HY + 0.33, z + 0.04), ls)
    Z0, Z1 = 1.2, 9.4
    # front / back with deep relief recesses
    for sd in ("-Y", "+Y"):
        o, r, w = side_frame(sd, -HX, HX, -HY, HY)
        B.wall(Vector(o) + Vector((0, 0, Z0)), r, (0, 0, 1), w, Z1 - Z0, 0.45, ls, [(w / 2, 4.2, 1.0, 7.4, False)], ls, 0.95, edges=False)
    # sides with arched windows (+X side also has the bronze door)
    for sd in ("-X", "+X"):
        o, r, w = side_frame(sd, -HX, HX, -HY, HY)
        holes = [(2.0, 1.3, 2.0, 5.2, True), (6.0, 1.3, 2.0, 5.2, True)] if sd == "-X" else [(1.7, 1.2, 2.0, 5.2, True), (4.0, 1.5, 0.0, 2.6, True),
                                                                                                  (6.3, 1.2, 2.0, 5.2, True)]
        B.wall(Vector(o) + Vector((0, 0, Z0)), r, (0, 0, 1), w, Z1 - Z0, 0.45, ls, holes, gl, 0.6, edges=False)
        for xc, ww, y0, y1, _ in holes:
            if y0 > 0:
                n = Vector(r).cross(Vector((0, 0, 1)))
                base = Vector(o) + Vector(r) * xc + Vector((0, 0, Z0 + y0 - 0.12)) + n * 0.12
                B.box(base, (ww + 0.4 if abs(r[0]) > 0.5 else 0.3, ww + 0.4 if abs(r[1]) > 0.5 else 0.3, 0.15), ls)  # sill
        if sd == "+X":                                                                    # bronze door leaf
            o2 = Vector(o) + Vector(r) * 4.0 + Vector((0, 0, Z0))
            B.box(o2 + Vector((-0.27, 0, 1.3)), (0.06, 1.5, 2.6), br)
    # small square windows high on the sides
    for sx in (-1, 1):
        for yy in (-2.0, 2.0):
            B.box((sx * (HX + 0.01), yy, 8.4), (0.04, 0.8, 0.7), gl)
            B.box((sx * (HX + 0.03), yy, 8.0), (0.08, 1.1, 0.12), ls)
    # corner pilasters
    for sx in (-1, 1):
        for sy in (-1, 1):
            B.boxmm((sx * HX - (0.55 if sx > 0 else 0.12), sy * HY - (0.55 if sy > 0 else 0.12), Z0),
                    (sx * HX + (0.12 if sx > 0 else 0.55), sy * HY + (0.12 if sy > 0 else 0.55), Z1), ls)
    # relief sculpture groups on the front and back panels (stylised figures)
    for sy in (-1, 1):
        yp = sy * (HY - 0.45 * 0.95) + (-sy) * 0.0
        face_y = yp + sy * 0.02
        out = sy
        figs = [(-1.45, 3.4, 0.0), (-0.55, 3.9, 0.25), (0.45, 3.6, -0.2), (1.35, 3.2, 0.1)]
        zb = Z0 + 1.15
        B.boxmm((-2.05, face_y if sy > 0 else face_y - 0.3, zb - 0.2), (2.05, face_y + 0.3 if sy > 0 else face_y, zb), ls)   # ground ledge
        for i, (fx, fh, lean) in enumerate(figs):
            y_out = face_y + out * 0.16
            body = [(fx, y_out, zb), (fx + lean * 0.4, y_out + out * 0.04, zb + fh * 0.5), (fx + lean, y_out, zb + fh * 0.82)]
            B.tube(body, [0.28, 0.24, 0.17], ls, 8, cap1=True, up=(0, 1, 0), aspect=[(1, 0.55)] * 3)
            B.ellipsoid((fx + lean * 1.05, y_out, zb + fh * 0.82 + 0.24), (0.15, 0.1, 0.19), ls, 10, 6)
            arm_up = i % 2 == 0
            ax0 = Vector((fx + lean * 0.9, y_out + out * 0.05, zb + fh * 0.74))
            ax1 = ax0 + Vector(((0.35 if i < 2 else -0.35), out * 0.05, 0.6 if arm_up else -0.5))
            B.tube([ax0, ax1], [0.08, 0.06], ls, 6, cap0=True, cap1=True)
        B.ellipsoid((0.0, face_y + out * 0.1, Z0 + 6.6), (1.7, 0.14, 0.55), ls, 16, 6)      # drapery / banner over the group
        B.boxmm((-2.1, min(face_y, face_y + out * 0.2), Z0 + 7.25), (2.1, max(face_y, face_y + out * 0.2), Z0 + 7.45), ls)
    # entablature, cornice, attic
    B.boxmm((-HX - 0.12, -HY - 0.12, Z1), (HX + 0.12, HY + 0.12, Z1 + 0.7), ls)
    B.boxmm((-HX - 0.45, -HY - 0.45, Z1 + 0.7), (HX + 0.45, HY + 0.45, Z1 + 1.05), ls)
    B.boxmm((-HX - 0.32, -HY - 0.32, Z1 + 1.05), (HX + 0.32, HY + 0.32, Z1 + 1.2), ls)
    block_walls(B, (-HX, HX, -HY, HY), [(Z1 + 1.2, 12.0, lambda w: bays(w, 2 if w < 7 else 3, w / (2 if w < 7 else 3) - 0.9, 0.2, 0.6))],
                ls, 0.35, fill=ls, fill_inset=0.4)
    B.boxmm((-HX - 0.08, -HY - 0.08, 11.85), (HX + 0.08, HY + 0.08, 12.0), ls)
    B.boxmm((-HX + 0.35, -HY + 0.35, Z1 + 1.0), (HX - 0.35, HY - 0.35, Z1 + 1.3), mat("M_RoofFlat"))
    ob = B.finish("LM_BridgeTenderHouse", sharp_angle=40)
    export("LM_BridgeTenderHouse", [ob], {
        "pivot": "ground centre (0,0,0); relief faces at y = -4 / +4 (Unreal +X / -X): face them along the roadway",
        "footprint_m": [6.6, 8.6], "key_heights_m": {"plinth": 1.2, "cornice": 10.6, "top": 12.0},
        "placement": "one at each corner of the bridge, beside the leaf heel (outside the 28 m deck), e.g. x = +/-18 m from the road axis"})


def bridge():
    tender_house()
    reset()
    bridge_leaf()
    reset()
    bridge_railing10()


# ================================================================== preview renderer
# ================================================================== 6. Landmark sites (plazas, walks, the whole of Navy Pier)
# Site assets are modelled in the PLAN frame (x east, y north, metres; Saved/Mashup/plan_v3.json) relative to a site
# origin, and turned -90 deg about Z just before export so that, after Unreal's glTF import (Blender (x, y, z) ->
# Unreal (x, -y, z)), plan north = Unreal +X and plan east = Unreal +Y: place them at Unreal (oy*100, ox*100, ground)
# with NO rotation. Positions, outlines and sizes come from SourceArt/Reference/<site>/ (OpenStreetMap + USGS NAIP
# aerials + published dimensions); see SourceArt/Reference/*/sources.txt and the SITES table below.
SITES = {
    # site origin in plan metres (real position of the landmark)
    "bean": (369.8, -538.7),          # Cloud Gate centre (OSM artwork polygon / NAIP aerial)
    "fountain": (731.6, -1300.15),    # Buckingham Fountain centre (OSM pool polygon centroid)
    "pier": (1496.0, 451.0),          # Navy Pier: headhouse west facade on the pier centreline
}
PIER_MAP_EDGE = 1723.0                # plan bounds: east of this the plan has no land or roads (the horizon lake)


class PlanBuilder(Builder):
    """Builder whose coordinates are plan-local (x east, y north); finish() turns the mesh to the export frame.
    vis=True adds self.vis, a second builder for geometry that is seen but doesn't collide (exported as <name>Steps):
    steps() then draws the treads there and puts a hidden ramp under them here, so the car can drive up a flight."""

    def __init__(self, vis=False):
        Builder.__init__(self)
        self.vis = PlanBuilder() if vis else None

    def finish(self, name, sharp_angle=48.0, weld=True):
        bmesh.ops.transform(self.bm, matrix=Matrix.Rotation(-math.pi / 2, 4, "Z"), verts=self.bm.verts)
        return Builder.finish(self, name, sharp_angle, weld)

    # ---------------------------------------------------------------- 2-D helpers
    def slab(self, poly, z0, z1, top, side=None, bottom=False):
        """Extrude a simple polygon (any winding) from z0 to z1: top face (+ optional bottom) and side walls."""
        poly = ccw(poly)
        side = side or top
        n = len(poly)
        self.face([(x, y, z1) for x, y in poly], top, [(x, y) for x, y in poly])
        if bottom:
            self.face([(x, y, z0) for x, y in poly[::-1]], side)
        for i in range(n):
            (ax, ay), (bx, by) = poly[i], poly[(i + 1) % n]
            L = math.hypot(bx - ax, by - ay)
            if L < 1e-6:
                continue
            self.face([(ax, ay, z0), (bx, by, z0), (bx, by, z1), (ax, ay, z1)], side, [(0, z0), (L, z0), (L, z1), (0, z1)])

    def sweep_closed(self, poly, prof, m, smooth=False):
        """Sweep a profile [(offset_out, z)...] along a closed polygon (miter offsets)."""
        poly = ccw(poly)
        N = vertex_normals(poly)
        P = []
        for (x, y), (nx, ny, k) in zip(poly, N):
            P.append([Vector((x + nx * o * k, y + ny * o * k, z)) for o, z in prof])
        self.grid(P, m, smooth, close_u=True)

    def sweep_open(self, path, prof, m, smooth=False):
        """Sweep a profile [(offset_left, z)] along an open polyline."""
        P = []
        n = len(path)
        for i in range(n):
            a = Vector(path[max(0, i - 1)]); b = Vector(path[min(n - 1, i + 1)])
            t = (b - a).normalized()
            nl = Vector((-t.y, t.x))
            P.append([Vector((path[i][0] + nl.x * o, path[i][1] + nl.y * o, z)) for o, z in prof])
        self.grid(P, m, smooth)

    def steps(self, x0, y0, x1, y1, z_top, z_bot, n, m, axis="x", up_positive=False):
        """A flight of n steps filling the box (x0..x1, y0..y1), stepping down from z_top to z_bot along +axis
        (or toward -axis when up_positive)."""
        rise = (z_top - z_bot) / n
        tgt = self.vis if self.vis is not None else self
        for k in range(n):
            z = z_top - rise * k                      # step k from the top; its box runs from the top edge outward
            if axis == "x":
                L = (x1 - x0) / n
                a = (x0, x0 + L * (k + 1)) if not up_positive else (x1 - L * (k + 1), x1)
                tgt.boxmm((a[0], y0, z_bot - 0.3), (a[1], y1, z), m)
            else:
                L = (y1 - y0) / n
                a = (y0, y0 + L * (k + 1)) if not up_positive else (y1 - L * (k + 1), y1)
                tgt.boxmm((x0, a[0], z_bot - 0.3), (x1, a[1], z), m)
        if self.vis is not None:
            # hidden collision ramp from the toe of the flight to its top edge (inside the staircase profile)
            zt, zb = z_top - 0.01, z_bot
            if axis == "x":
                self.ramp(x0, y0, x1, y1, zt, zb, m, "x") if not up_positive else self.ramp(x0, y0, x1, y1, zb, zt, m, "x")
            else:
                self.ramp(x0, y0, x1, y1, zt, zb, m, "y") if not up_positive else self.ramp(x0, y0, x1, y1, zb, zt, m, "y")

    def ramp(self, x0, y0, x1, y1, z0, z1, m, axis="x"):
        """A sloped slab: top rises from z0 at (x0|y0) to z1 at (x1|y1)."""
        if axis == "x":
            P = [(x0, y0, z0), (x1, y0, z1), (x1, y1, z1), (x0, y1, z0)]
        else:
            P = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z1), (x0, y1, z1)]
        self.face(P, m)
        lo = min(z0, z1) - 0.3
        for (a, b) in zip(P, P[1:] + P[:1]):
            self.face([(a[0], a[1], lo), (b[0], b[1], lo), b, a], m)

    def balustrade(self, path, z, m, h=1.0, step=0.36, closed=False):
        """Classical stone balustrade along a polyline: plinth, turned balusters, handrail, piers every ~3 m."""
        pts = list(path) + ([path[0]] if closed else [])
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L = math.hypot(bx - ax, by - ay)
            if L < 0.2:
                continue
            ux, uy = (bx - ax) / L, (by - ay) / L
            self.beam((ax, ay, z), (bx, by, z), 0.42, 0.18, m)                       # plinth
            self.beam((ax, ay, z + h - 0.14), (bx, by, z + h - 0.14), 0.4, 0.14, m)  # handrail cap
            nb = int(L / step)
            for i in range(nb):
                t = (i + 0.5) / nb * L
                cx, cy = ax + ux * t, ay + uy * t
                self.lathe([(0.08, z + 0.18), (0.11, z + 0.34), (0.065, z + 0.62), (0.08, z + h - 0.22), (0.0, z + h - 0.21)], m, 6,
                           center=(cx, cy, 0), smooth=True)
            npier = max(1, int(L / 3.0))
            for i in range(npier + 1):
                t = L * i / npier
                self.box((ax + ux * t, ay + uy * t, z + h / 2), (0.42, 0.42, h + 0.04), m)

    def railing(self, path, z, h=1.07, step=2.0, m="M_Railing", closed=False):
        """Steel pipe railing: posts every `step`, top rail and two lower rails."""
        pts = list(path) + ([path[0]] if closed else [])
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L = math.hypot(bx - ax, by - ay)
            if L < 0.2:
                continue
            n = max(1, round(L / step))
            for i in range(n + 1):
                t = i / n
                self.box((ax + (bx - ax) * t, ay + (by - ay) * t, z + h / 2), (0.07, 0.07, h), m)
            for zz, r in ((h, 0.035), (h * 0.62, 0.02), (h * 0.25, 0.02)):
                self.tube([(ax, ay, z + zz), (bx, by, z + zz)], [r, r], m, 6)


def ccw(poly):
    a = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
    return list(poly) if a > 0 else list(poly)[::-1]


def vertex_normals(poly):
    """Outward miter normals of a CCW polygon: (nx, ny, miter_scale)."""
    n = len(poly)
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(poly[i - 1]), Vector(poly[i]), Vector(poly[(i + 1) % n])
        e0 = (p1 - p0).normalized(); e1 = (p2 - p1).normalized()
        n0 = Vector((e0.y, -e0.x)); n1 = Vector((e1.y, -e1.x))
        m = (n0 + n1)
        if m.length < 1e-6:
            m = n0
        m.normalize()
        k = 1.0 / max(0.3, m.dot(n1))
        out.append((m.x, m.y, k))
    return out


def offset_poly(poly, d):
    poly = ccw(poly)
    return [(x + nx * d * k, y + ny * d * k) for (x, y), (nx, ny, k) in zip(poly, vertex_normals(poly))]


def arc(cx, cy, r, a0, a1, n):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def rrect(x0, y0, x1, y1, r, n=6):
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    P = []
    for cx, cy, a in ((x1 - r, y0 + r, -math.pi / 2), (x1 - r, y1 - r, 0.0), (x0 + r, y1 - r, math.pi / 2), (x0 + r, y0 + r, math.pi)):
        P += arc(cx, cy, r, a, a + math.pi / 2, n)
    return P


def circle(cx, cy, r, n=48):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


SITE_META = {}


def site_export(name, ob, meta):
    meta = dict(meta)
    meta["frame"] = "plan-local (x east, y north) turned -90 deg: place in Unreal at the site origin with NO rotation"
    export(name, [ob], meta)


# ------------------------------------------------------------------ 6a. Cloud Gate: Grainger (AT&T) Plaza
# Real layout (OSM + NAIP, plan metres): plaza on the roof of Millennium Hall (old Park Grill) x 349..391,
# y -579..-498; 3-step flights down to Chase Promenade at x 388-391 (y -511, -538, -565) and two ramps NE/SE;
# McCormick Tribune Plaza & Ice Rink at street level west of it (rink 61 x 24 m: x 321..344.5, y -569..-510);
# Michigan Ave east sidewalk ends at x 308.8 in the plan. The plan has a single ground level, so the street-level
# rink terrace and the upper park level are flattened: the plaza sits 3 steps (0.45 m) above both.
BEAN_DECK = 0.45


def cloud_gate_plaza():
    ox, oy = SITES["bean"]
    L = lambda x, y: (x - ox, y - oy)
    B = PlanBuilder(vis=True)
    gr, grd, lawn, hedge, rl = "M_Granite", "M_GraniteDark", "M_Lawn", "M_Hedge", "M_Railing"
    PAVE = 0.06                                   # walks / terraces sit 6 cm above the plan ground
    xw = 308.8 - ox                               # Michigan Ave sidewalk edge
    x_grill, x_deck_e, x_prom_e = 349.0 - ox, 388.0 - ox, 413.0 - ox
    y_s, y_n = -579.1 - oy, -498.4 - oy
    # --- McCormick Tribune Plaza (street-level terrace) and the rink (summer: Park Grill Plaza)
    B.slab([(xw, y_s), (x_grill, y_s), (x_grill, y_n), (xw, y_n)], -0.3, PAVE, gr)
    rink = rrect(321.0 - ox, -569.0 - oy, 344.5 - ox, -510.0 - oy, 6.0)
    B.sweep_closed(rink, [(0.3, PAVE), (0.3, PAVE + 0.18), (0.0, PAVE + 0.18), (0.0, PAVE)], grd)
    B.slab(offset_poly(rink, -0.01), PAVE - 0.02, PAVE + 0.01, "M_RinkSurface")
    B.railing(offset_poly(rink, 0.15), PAVE + 0.18, h=1.0, step=2.5, closed=True)
    # terrace planters with trees along Michigan Ave (the honey locusts are the city's own tree props)
    for y0, y1 in ((-575.0, -545.0), (-532.0, -503.0)):
        a, b = L(311.0, y0), L(317.0, y1)
        B.slab([(a[0], a[1]), (b[0], a[1]), (b[0], b[1]), (a[0], b[1])], PAVE, PAVE + 0.45, grd)
        B.slab([(a[0] + 0.3, a[1] + 0.3), (b[0] - 0.3, a[1] + 0.3), (b[0] - 0.3, b[1] - 0.3), (a[0] + 0.3, b[1] - 0.3)], PAVE, PAVE + 0.5, hedge)
    # --- the plaza deck (granite) on Millennium Hall's roof, with its east edge stepping down to the promenade
    deck = [(x_grill, y_s), (x_deck_e, y_s), (x_deck_e, y_n), (x_grill, y_n)]
    B.slab(deck, -0.3, BEAN_DECK, gr, grd)
    # pale granite joint bands every 6 m (the plaza's paving grid)
    for k in range(-6, 7):
        y = k * 6.0
        if y_s + 4 < y < y_n - 4:
            B.boxmm((x_grill + 3.2, y - 0.08, BEAN_DECK), (x_deck_e - 0.2, y + 0.08, BEAN_DECK + 0.006), grd)
    for k in range(-3, 4):
        x = k * 6.0
        if x_grill + 4 < x < x_deck_e - 1:
            B.boxmm((x - 0.08, y_s + 3.2, BEAN_DECK), (x + 0.08, y_n - 3.2, BEAN_DECK + 0.006), grd)
    # 3-step flights (east) at the real positions, 9 m wide; the rest of the east edge is a granite retaining edge
    for yc in (-511.0, -538.1, -565.2):
        y0, y1 = yc - oy - 4.5, yc - oy + 4.5
        B.steps(x_deck_e, y0, x_deck_e + 1.2, y1, BEAN_DECK, PAVE, 3, gr, "x")
    # NE / SE ramps (2023-24 renovation), 3 m wide, running east-southeast/east-northeast down to the promenade
    B.ramp(x_deck_e, -510.9 - oy + 4.4, x_deck_e + 9.0, -510.9 - oy + 7.4, BEAN_DECK, PAVE, gr, "x")
    B.ramp(x_deck_e, -565.2 - oy - 7.4, x_deck_e + 9.0, -565.2 - oy - 4.4, BEAN_DECK, PAVE, gr, "x")
    # west edge: balustrade over the rink terrace, broken by a central flight of 3 steps (to the rink)
    yc0, yc1 = -6.0, 6.0
    B.balustrade([(x_grill + 0.25, y_s + 0.3), (x_grill + 0.25, yc0)], BEAN_DECK, "M_Limestone")
    B.balustrade([(x_grill + 0.25, yc1), (x_grill + 0.25, y_n - 0.3)], BEAN_DECK, "M_Limestone")
    B.steps(x_grill - 1.2, yc0, x_grill, yc1, BEAN_DECK, PAVE, 3, gr, "x", up_positive=True)
    # north and south edges: balustrades too (the deck drops to the park walks)
    B.balustrade([(x_grill + 0.3, y_n - 0.25), (x_deck_e - 0.3, y_n - 0.25)], BEAN_DECK, "M_Limestone")
    B.balustrade([(x_grill + 0.3, y_s + 0.25), (x_deck_e - 0.3, y_s + 0.25)], BEAN_DECK, "M_Limestone")
    # perimeter planting beds inside the balustrades (granite kerbs, low shrubs) along N, S and the west wings
    for (a, b) in (((x_grill + 0.8, y_n - 4.2), (x_deck_e - 1.0, y_n - 0.8)), ((x_grill + 0.8, y_s + 0.8), (x_deck_e - 1.0, y_s + 4.2)),
                   ((x_grill + 0.8, yc1 + 2.0), (x_grill + 4.0, y_n - 4.2)), ((x_grill + 0.8, y_s + 4.2), (x_grill + 4.0, yc0 - 2.0))):
        P = [a, (b[0], a[1]), b, (a[0], b[1])]
        B.slab(P, BEAN_DECK, BEAN_DECK + 0.45, grd)
        B.slab(offset_poly(P, -0.25), BEAN_DECK, BEAN_DECK + 0.55, hedge)
    # --- Chase Promenade (granite) east of the plaza, and the walks along Washington and Madison
    yps, ypn = -610.0 - oy, -474.0 - oy
    B.slab([(x_deck_e, yps), (x_prom_e, yps), (x_prom_e, ypn), (x_deck_e, ypn)], -0.3, PAVE, "M_GranitePromenade")
    for y0, y1 in ((-486.0, -474.0), (-610.0, -598.0)):
        B.slab([(xw, y0 - oy), (x_deck_e, y0 - oy), (x_deck_e, y1 - oy), (xw, y1 - oy)], -0.3, PAVE, "M_GranitePromenade")
    # kerb-line benches along the promenade
    for k in range(10):
        y = ypn - 8 - k * ((ypn - yps - 16) / 9)
        if abs(y) < 45:
            continue
        B.box((x_prom_e - 1.5, y, PAVE + 0.23), (0.6, 2.4, 0.46), "M_Limestone")
    obv = B.vis.finish("LM_CloudGatePlazaSteps", sharp_angle=50)
    site_export("LM_CloudGatePlazaSteps", obv, {"pivot": "same as LM_CloudGatePlaza", "collision": "NONE: the treads are visual; "
                "LM_CloudGatePlaza holds a hidden ramp under each flight so the car can drive up them"})
    ob = B.finish("LM_CloudGatePlaza", sharp_angle=50)
    site_export("LM_CloudGatePlaza", ob, {
        "pivot": "plan %s = Cloud Gate's centre, on the ground; LM_CloudGate stands at (0, 0, %.2f) m on the deck" % (str(SITES["bean"]), BEAN_DECK),
        "deck_top_m": BEAN_DECK, "paving_top_m": PAVE,
        "extent_plan_m": {"x": [308.8, 413.0], "y": [-610.0, -474.0]},
        "notes": "granite plaza (3 steps up) with balustrades, real step flights and ramps, perimeter planters; street-level "
                 "McCormick Tribune Plaza with the rink outline; Chase Promenade and the Washington / Madison walks"})


# ------------------------------------------------------------------ 6b. Buckingham Fountain plaza
# OSM / NAIP: pool = four lobes (radius 25.8 m, centred 16.9 m out on the axes) with square corner bastions at the
# diagonals (corner at 30.5 m), 85.4 m across; a lawn band to a low fence 7.5 m outside it; the plaza of pink
# concrete pavers is an octagon with N and S necks (comfort stations + cafe pavilions), a west arm to Columbus Drive
# (toward Congress Plaza) and an east arm toward Lake Shore Drive; hedged garden beds fill the diagonals.
def pool_outline(d=0.0, n=24):
    """Buckingham's pool edge offset outward by d metres (CCW): four lobes (radius 25.8, centres 16.9 m out on the
    axes) clipped by the lines |x| or |y| = 30.5, with square bastion corners at (+/-30.5, +/-30.5) on the diagonals."""
    rho, c, k = 25.8 + d, 16.9, 30.5 + d
    T = math.acos(max(-1.0, min(1.0, (k - c) / rho)))
    P = []
    for q in range(4):
        R = Matrix.Rotation(q * math.pi / 2, 2)
        for i in range(n + 1):
            t = -T + 2 * T * i / n
            v = R @ Vector((c + rho * math.cos(t), rho * math.sin(t)))
            P.append((v.x, v.y))
        v = R @ Vector((k, k))
        P.append((v.x, v.y))
    Q = []
    for p in P:
        if not Q or math.dist(p, Q[-1]) > 0.05:
            Q.append(p)
    if math.dist(Q[0], Q[-1]) < 0.05:
        Q.pop()
    return ccw(Q)


def buckingham_plaza():
    ox, oy = SITES["fountain"]
    B = PlanBuilder()
    PAVE = 0.06
    W = 613.0 - ox            # Columbus Drive east sidewalk edge
    E = 840.0 - ox            # east arm end (lawn strip before Lake Shore Drive's carriageway at x 872)
    plaza = [(-31.6, 128), (33.4, 128), (33.4, 86), (73.4, 46), (73.4, 17), (E, 17), (E, -17), (73.4, -17), (73.4, -46),
             (33.4, -86), (33.4, -128), (-31.6, -128), (-31.6, -86), (-69.6, -48), (-95, -48), (-95, -15), (W, -15), (W, 13),
             (-95, 13), (-95, 48), (-69.6, 48), (-31.6, 86)]
    # the paved plaza, minus the lawn ring inside the fence: build it as a slab with the fence outline as a hole by
    # splitting into a ring band (fence outline -> plaza) made of quads from a radial sampling
    fence = pool_outline(7.5, 24)
    # outer plaza slab (full), then the lawn ring and pool sit on top of it (lawn slab 1 cm higher)
    B.slab(plaza, -0.3, PAVE, "M_PinkPaver")
    B.sweep_closed(plaza, [(0.12, PAVE - 0.01), (0.12, PAVE + 0.03), (0.0, PAVE + 0.03), (0.0, PAVE - 0.01)], "M_GraniteDark")
    B.slab(fence, PAVE, PAVE + 0.012, "M_Lawn")
    # low hoop fence (black iron) along the lawn band
    fp = offset_poly(fence, -0.15)
    B.railing(fp, PAVE, h=0.6, step=2.4, closed=True)
    # four pavilions (comfort stations / cafe): pink stone, copper hip roofs (OSM footprints)
    for x0, x1, y0, y1 in ((699.2, 710.7, -1202.1, -1182.3), (749.0, 760.4, -1201.3, -1181.5), (703.1, 714.8, -1418.7, -1398.9),
                           (752.9, 764.6, -1417.6, -1397.9)):
        a, b = (x0 - ox, y0 - oy), (x1 - ox, y1 - oy)
        P = [a, (b[0], a[1]), b, (a[0], b[1])]
        B.slab(P, PAVE, 4.2, "M_PinkMarble")
        B.slab(offset_poly(P, 0.35), 4.2, 4.6, "M_PinkMarble")
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        B.pyramid((cx, cy, 4.6), (b[0] - a[0]) / 2 + 0.35, (b[1] - a[1]) / 2 + 0.35, 3.2, "M_Roof")
        for sx in (-1, 1):                     # doors and windows on the long sides
            for k in range(3):
                yy = cy + (k - 1) * 5.5
                B.box((cx + sx * ((b[0] - a[0]) / 2 + 0.01), yy, 1.6), (0.04, 1.6, 2.4), "M_Glass")
    # formal planting: boxwood hedges along the diagonal edges and around the corner garden beds
    for (p, q) in (((33.4, 86), (73.4, 46)), ((73.4, -46), (33.4, -86)), ((-31.6, -86), (-69.6, -48)), ((-69.6, 48), (-31.6, 86))):
        d = Vector(q) - Vector(p)
        nrm = Vector((d.y, -d.x)).normalized()     # outward for the CCW plaza
        a = Vector(p) + nrm * 1.2; b = Vector(q) + nrm * 1.2
        B.sweep_open([tuple(a), tuple(b)], [(-0.45, PAVE), (-0.45, 0.95), (0.45, 0.95), (0.45, PAVE)], "M_Hedge")
    # west arm planting beds (the hedged parterres flanking the approach from Congress Plaza, OSM)
    for x0, x1, y0, y1 in ((620.2, 634.6, -1319.9, -1314.9), (619.7, 634.0, -1287.9, -1283.2)):
        a, b = (x0 - ox, y0 - oy), (x1 - ox, y1 - oy)
        P = [a, (b[0], a[1]), b, (a[0], b[1])]
        B.slab(P, PAVE, 0.32, "M_GraniteDark")
        B.slab(offset_poly(P, -0.25), PAVE, 0.75, "M_Hedge")
    # lamp standards round the plaza (pairs at the arms)
    for x, y in ((-95.5, 16), (-95.5, -18), (74, 20), (74, -20), (-34, 89), (36, 89), (-34, -89), (36, -89)):
        B.tube([(x, y, PAVE), (x, y, PAVE + 0.6), (x, y, 4.4)], [0.16, 0.11, 0.07], "M_Railing", 8, cap1=True)
        B.ellipsoid((x, y, 4.7), (0.28, 0.28, 0.36), "M_Light", 12, 6)
    ob = B.finish("LM_BuckinghamPlaza", sharp_angle=50)
    site_export("LM_BuckinghamPlaza", ob, {
        "pivot": "plan %s = the fountain's centre, on the ground (LM_BuckinghamFountain / Jets go at the same point)" % (str(SITES["fountain"]),),
        "paving_top_m": PAVE, "extent_plan_m": {"x": [613.0, 840.0], "y": [-1428.15, -1172.15]},
        "notes": "pink paver plaza (octagon + N/S necks + arms to Columbus Dr and toward Lake Shore Dr), lawn ring and hoop "
                 "fence round the pool, 4 pavilions with copper roofs, boxwood hedges, lamp standards"})


# ------------------------------------------------------------------ 6c. Navy Pier: deck, buildings, Polk Bros Park
# Real positions (OSM building footprints + NAIP), plan metres; all pier assets share the origin SITES["pier"].
# Inside the plan (x < 1723) Grand Avenue (north edge, y 496.4..519.8 incl. sidewalks) and Dock Street (south edge,
# y 384.1..406.4) are the street builder's: buildings and paving keep to y 406.4..496.4 there, and the deck under
# those roads sits 8 cm below them (its dock walls show, its top doesn't). East of the plan edge the deck carries
# its own north drive (same lanes as Grand Avenue, ending at the real turning circle) and the south promenade.
PIER = dict(y_s=383.0, y_n=521.5, x_w=1496.0, x_e=2423.0, walk_s=406.4, walk_n=496.4, deck_bottom=-7.0)


def pier_deck():
    ox, oy = SITES["pier"]
    T = lambda pts: [(x - ox, y - oy) for x, y in pts]
    B = PlanBuilder()
    D = PIER
    zb = D["deck_bottom"]
    E = PIER_MAP_EDGE
    # deck outline (the real pier east of the plan edge; under-road strips and the central zone inside it)
    east = [(E, D["y_s"]), (2232.0, D["y_s"]), (2232.0, 392.0), (2256.0, 392.0), (2256.0, 428.0), (D["x_e"], 428.0), (D["x_e"], 519.5),
            (2256.0, 519.5), (2256.0, 541.0), (2232.0, 541.0), (2232.0, D["y_n"]), (E, D["y_n"])]
    B.slab(T(east), zb, 0.0, "M_DeckConcrete", "M_DockWall")
    # under-road strips and the central zone inside the plan (deck top hidden 8 cm under the roads)
    for y0, y1 in ((D["y_s"], D["walk_s"]), (D["walk_n"], D["y_n"])):
        B.slab(T([(1466.0, y0), (E, y0), (E, y1), (1466.0, y1)]), zb, -0.08, "M_DockWall")
    # the plan draws Grand Ave's and Dock St's sidewalks here but no carriageway (and its Ground stops at the water):
    # asphalt on the deck where the lanes are, 8 cm under where the street builder's road surface would sit
    for y0, y1 in ((505.8, 516.0), (392.4, 402.6)):
        B.boxmm((1474.0 - ox, y0 - oy, -0.1), (E - ox, y1 - oy, -0.06), "M_Asphalt")
    # dock wall details all round the real pier edge: waterline band, timber fender, top coping
    edge = T([(1466.0, D["y_s"]), (2232.0, D["y_s"]), (2232.0, 392.0), (2256.0, 392.0), (2256.0, 428.0), (D["x_e"], 428.0), (D["x_e"], 519.5),
              (2256.0, 519.5), (2256.0, 541.0), (2232.0, 541.0), (2232.0, D["y_n"]), (1466.0, D["y_n"])])
    B.sweep_closed(edge, [(0.08, -6.2), (0.08, -5.2), (0.0, -5.2), (0.0, -6.2)], "M_DockWallDark")
    B.sweep_closed(edge, [(0.32, -3.0), (0.32, -2.6), (0.0, -2.6), (0.0, -3.0)], "M_Timber")
    # --- east of the plan edge: north drive, south promenade, central paving, east end plaza
    asp = "M_Asphalt"
    B.boxmm((E - ox, 505.8 - oy, 0.0), (2236.0 - ox, 516.0 - oy, 0.02), asp)
    B.slab(T(circle(2236.0, 511.0, 9.5, 32)), 0.0, 0.02, asp)                      # turning circle (real: 2239, 522)
    for y0, y1 in ((496.4, 505.6), (516.2, 520.6)):                               # sidewalks with kerbs
        B.boxmm((E - ox, y0 - oy, 0.0), (2226.0 - ox, y1 - oy, 0.15), "M_SidewalkConcrete")
    B.boxmm((E - ox, D["y_s"] + 0.6 - oy, 0.0), (2232.0 - ox, D["walk_s"] - oy, 0.06), "M_DeckPaving")   # south promenade
    B.boxmm((E - ox, D["walk_s"] - oy, 0.0), (2232.0 - ox, D["walk_n"] - oy, 0.06), "M_DeckPaving")     # central zone
    B.slab(T([(2226.0, 496.4), (D["x_e"] - 0.6, 496.4), (D["x_e"] - 0.6, 518.9), (2256.0, 518.9), (2256.0, 540.4), (2232.6, 540.4),
              (2232.6, 520.9), (2246.0, 520.9), (2246.0, 505.6), (2226.0, 505.6)]), 0.0, 0.06, "M_DeckPaving")
    B.slab(T([(2232.0, 392.6), (2255.4, 392.6), (2255.4, 428.6), (D["x_e"] - 0.6, 428.6), (D["x_e"] - 0.6, 496.4), (2232.0, 496.4)]), 0.0, 0.06, "M_DeckPaving")
    # --- inside the plan: the central zone (headhouse forecourt to the plan edge) paved over the plan ground
    B.boxmm((1482.8 - ox, D["walk_s"] - oy, -0.3), (E - ox, D["walk_n"] - oy, 0.06), "M_DeckPaving")
    # promenade tree pits + benches east of the plan edge (trees themselves are the city's honey locusts)
    for k in range(int((2220 - 1730) / 10)):
        x = 1732.0 + 10.0 * k
        for y in (394.5, 403.5):
            B.sweep_closed(T(rrect(x - 1.0, y - 1.0, x + 1.0, y + 1.0, 0.1, 1)), [(0.15, 0.0), (0.15, 0.14), (0.0, 0.14), (0.0, 0.0)], "M_GraniteDark")
        if k % 3 == 1:
            B.box((x + 5.0 - ox, 399.0 - oy, 0.29), (2.2, 0.6, 0.46), "M_Timber")
    # --- railings along the dock edges (on a 0.25 m concrete kerb) and round the east end
    kerb = [(0.0, -0.1), (0.0, 0.25), (0.35, 0.25), (0.35, -0.1)]
    rails_s = T([(1500.0, D["y_s"] + 0.2), (2232.0 - 0.2, D["y_s"] + 0.2), (2232.0 - 0.2, 392.2), (2256.0 - 0.2, 392.2), (2256.0 - 0.2, 428.2),
                 (D["x_e"] - 0.2, 428.2), (D["x_e"] - 0.2, 519.3), (2256.2, 519.3), (2256.2, 540.8), (2231.8, 540.8), (2231.8, D["y_n"] - 0.2),
                 (1500.0, D["y_n"] - 0.2)])
    B.sweep_open(rails_s, kerb, "M_DockWall")
    B.railing(rails_s, 0.25, h=1.07, step=2.5)
    # --- east end plaza: 13 flagpoles in an arc (OSM), lamps, the anchor memorial plinth
    for x, y in ((2403.1, 437.1), (2406.5, 441.9), (2410.7, 449.1), (2413.2, 455.6), (2415.3, 462.3), (2416.4, 469.7), (2416.5, 476.0),
                 (2416.0, 482.6), (2414.4, 490.0), (2412.0, 496.7), (2409.6, 502.1), (2404.8, 509.4), (2400.4, 515.3)):
        B.tube([(x - ox, y - oy, 0.06), (x - ox, y - oy, 12.5)], [0.11, 0.06], "M_Steel", 8, cap1=True)
        B.box((x - ox, y - oy, 0.2), (0.6, 0.6, 0.3), "M_GraniteDark")
    for x in range(1740, 2400, 25):
        for y in (384.4, 519.8) if x < 2230 else ((429.4, 518.4) if x > 2260 else ()):
            B.tube([(x - ox, y - oy, 0.25), (x - ox, y - oy, 4.8)], [0.09, 0.06], "M_Railing", 8, cap1=True)
            B.ellipsoid((x - ox, y - oy, 5.05), (0.22, 0.22, 0.3), "M_Light", 10, 5)
    ob = B.finish("LM_NavyPierDeck", sharp_angle=50)
    site_export("LM_NavyPierDeck", ob, {
        "pivot": "plan %s (headhouse west facade, pier centreline) on the ground; z 0 = plan ground" % (str(SITES["pier"]),),
        "deck": "real outline x 1496..2423 (929 m), y 383..521.5 (138.5 m) at the west, 91 m at the east end; dock walls to z %.1f" % zb,
        "map_edge_plan_x": E,
        "notes": "east of the plan edge: north drive (Grand Ave lanes) to the turning circle, south promenade with tree pits, "
                 "railings, lamps, East End Plaza flagpoles; inside the plan only dock walls under the roads + central paving"})


def brick_block(B, x0, x1, y0, y1, h, bay=6.0, storey=4.2, glass="M_Glass", wall="M_Brick", trim="M_Limestone", cornice=True, base=0.06):
    """A brick building block with storeys of punched windows on all sides, string courses and a cornice (plan-local)."""
    rect = (x0, x1, y0, y1)
    nst = max(1, int((h - 1.0) // storey))
    bands = []
    z = base
    for s in range(nst):
        z1 = min(h, z + storey)
        bands.append((z, z1, lambda w, s=s, hgt=z1 - z: bays(w, max(1, round(w / bay)), bay * 0.45, 0.9 if s else 0.3,
                                                             (hgt - 0.6 - bay * 0.225) if s == 0 else hgt - 0.9, s == 0)))
        z = z1
    if z < h:
        bands.append((z, h, None))
    for sd in ("-Y", "+Y", "-X", "+X"):
        o, r, w = side_frame(sd, *rect)
        for za, zz, hf in bands:
            holes = hf(w) if hf else ()
            holes = [hh for hh in holes if hh[3] < zz - za - 0.2]
            B.wall(Vector(o) + Vector((0, 0, za)), r, (0, 0, 1), w, zz - za, 0.45, wall, holes, glass, 0.6, edges=False)
    B.boxmm((x0 + 0.3, y0 + 0.3, h - 0.3), (x1 - 0.3, y1 - 0.3, h - 0.05), "M_RoofFlat")
    for k in range(1, nst):
        frame_ring(B, rect, base + k * storey - 0.15, base + k * storey + 0.15, 0.06, 0.3, trim)
    if cornice:
        frame_ring(B, rect, h - 0.1, h + 0.5, 0.4, 0.6, trim)
    frame_ring(B, rect, base, base + 0.9, 0.1, 0.3, trim)


def chamfer_square(cx, cy, s, ch):
    h = s / 2
    return [(cx + h, cy - h + ch), (cx + h, cy + h - ch), (cx + h - ch, cy + h), (cx - h + ch, cy + h), (cx - h, cy + h - ch),
            (cx - h, cy - h + ch), (cx - h + ch, cy - h), (cx + h - ch, cy - h)]


def pier_tower(B, cx, cy, s, h, ch=1.6, dome="M_Roof", lantern="M_Limestone", spire=False):
    """Navy Pier tower (photos): brick shaft with chamfered corners, limestone bands, tall arched window slots on the four
    faces, a heavy stone cornice, then an octagonal lantern with a dome (green copper at the headhouse, white stone and a
    spire at the Grand Ballroom). Returns the top height."""
    base = chamfer_square(cx, cy, s, ch)
    B.slab(base, 0.06, h, "M_Brick")
    B.sweep_closed(base, [(0.18, 0.06), (0.18, 1.4), (0.0, 1.4), (0.0, 0.06)], "M_Limestone")
    z = 6.0
    while z < h - 3.0:
        B.sweep_closed(base, [(0.1, z), (0.1, z + 0.35), (0.0, z + 0.35), (0.0, z)], "M_Limestone")
        z += 5.5
    for k in range(4):                                     # two arched slots per face
        a = k * math.pi / 2
        nx, ny = math.cos(a), math.sin(a)
        tx, ty = -ny, nx
        for off in (-1.3, 1.3):
            px, py = cx + nx * (s / 2 + 0.03) + tx * off, cy + ny * (s / 2 + 0.03) + ty * off
            z0, z1 = 7.0, h - 4.5
            pts = [(-0.55, z0), (0.55, z0), (0.55, z1)] + [(0.55 * math.cos(math.pi * j / 6), z1 + 0.55 * math.sin(math.pi * j / 6)) for j in range(1, 6)] + [(-0.55, z1)]
            B.poly_local((px, py, 0.0), (tx, ty, 0.0), (0, 0, 1), pts, "M_GlassDark")
    top = offset_poly(base, 0.55)
    B.slab(top, h, h + 0.9, "M_Limestone")
    B.slab(offset_poly(base, 0.1), h + 0.9, h + 1.8, "M_Brick")
    B.slab(offset_poly(base, 0.25), h + 1.8, h + 2.1, "M_Limestone")
    r = s * 0.27
    oct_ = [(cx + r * math.cos(math.pi / 8 + k * math.pi / 4), cy + r * math.sin(math.pi / 8 + k * math.pi / 4)) for k in range(8)]
    B.slab(oct_, h + 2.1, h + 5.0, lantern)
    for k in range(8):
        a = k * math.pi / 4
        B.poly_local((cx + r * 0.93 * math.cos(a) + 0.02 * math.cos(a), cy + r * 0.93 * math.sin(a) + 0.02 * math.sin(a), h + 2.6),
                     (-math.sin(a), math.cos(a), 0), (0, 0, 1), [(-0.35, 0), (0.35, 0), (0.35, 1.6), (0, 2.0), (-0.35, 1.6)], "M_GlassDark")
    B.slab(offset_poly(oct_, 0.25), h + 5.0, h + 5.4, lantern)
    prof = [(r * math.cos(t), h + 5.4 + r * 0.95 * math.sin(t)) for t in [math.pi / 2 * j / 8 for j in range(9)]]
    B.lathe(prof, dome, 16, center=(cx, cy, 0))
    ztop = h + 5.4 + r * 0.95
    if spire:
        B.tube([(cx, cy, ztop - 0.2), (cx, cy, ztop + 3.0)], [0.18, 0.03], lantern, 8, cap1=True)
        ztop += 3.0
    else:
        B.ellipsoid((cx, cy, ztop + 0.3), (0.25, 0.25, 0.3), dome, 10, 5)
        ztop += 0.6
    return ztop


def navy_pier_buildings():
    """Headhouse + Family Pavilion, Crystal Gardens, Shakespeare Theater, east garage, Festival Hall + Sable hotel,
    West Terminal + Lakeview Terrace, Skyline Stage tent, Pier Park rides. One mesh (LM_NavyPierBuildings)."""
    ox, oy = SITES["pier"]
    B = PlanBuilder()
    X = lambda x: x - ox
    Y = lambda y: y - oy
    ys, yn = PIER["walk_s"] + 3.0, PIER["walk_n"] - 0.4
    # --- Headhouse (1916): 3-storey brick front block across the pier, twin towers, the glazed NAVY PIER arch
    brick_block(B, X(1496.0), X(1512.0), Y(410.0), Y(yn), 16.0, bay=5.2)
    for yc in (427.7, 482.6):
        pier_tower(B, X(1500.0), Y(yc), 12.0, 29.0, ch=2.2, dome="M_Roof", lantern="M_Limestone")
    # segmental glazed arch canopy between the towers (the NAVY PIER sign arch over the Family Pavilion entrance)
    a0, a1 = Y(436.0), Y(474.0)
    span, rise = a1 - a0, 6.5
    Rr = (span * span / 4 + rise * rise) / (2 * rise)
    yc_ = (a0 + a1) / 2
    zc = 16.0 + rise - Rr
    P = []
    for i in range(17):
        yy = a0 + span * i / 16
        zz = zc + math.sqrt(max(0.0, Rr * Rr - (yy - yc_) ** 2))
        P.append([Vector((X(1495.4), yy, 16.0)), Vector((X(1495.4), yy, zz))])
    B.grid(P[::-1], "M_Glass", smooth=False)
    for i in range(0, 17, 2):
        yy = a0 + span * i / 16
        zz = zc + math.sqrt(max(0.0, Rr * Rr - (yy - yc_) ** 2))
        B.box((X(1495.3), yy, (16.0 + zz) / 2), (0.25, 0.25, zz - 16.0), "M_Steel")
    B.tube([(X(1495.2), a0 + span * i / 16, zc + math.sqrt(max(0.0, Rr * Rr - (a0 + span * i / 16 - yc_) ** 2))) for i in range(17)], [0.22] * 17, "M_Steel", 6)
    B.boxmm((X(1493.6), Y(440.0), 3.6), (X(1496.0), Y(470.0), 4.0), "M_Steel")          # entrance canopy
    # --- Family Pavilion behind the headhouse
    brick_block(B, X(1512.0), X(1572.0), Y(413.0), Y(yn), 18.0, bay=6.0, storey=4.5)
    # --- Crystal Gardens: glass atrium with a barrel-vaulted roof (axis along the pier)
    x0, x1, y0, y1 = X(1572.0), X(1625.0), Y(425.0), Y(491.0)
    B.boxmm((x0, y0, 0.06), (x1, y0 + 0.3, 14.0), "M_Glass"); B.boxmm((x0, y1 - 0.3, 0.06), (x1, y1, 14.0), "M_Glass")
    B.boxmm((x1 - 0.3, y0, 0.06), (x1, y1, 14.0), "M_Glass")
    for k in range(9):
        x = x0 + (x1 - x0) * k / 8
        for yy in (y0, y1):
            B.box((x, yy, 7.0), (0.4, 0.5, 14.0), "M_Steel")
    span = y1 - y0
    P = [[Vector((x0 + (x1 - x0) * i / 12, y0 + span * j / 16, 14.0 + 7.0 * math.sin(math.pi * j / 16))) for j in range(17)] for i in range(13)]
    B.grid(P, "M_Glass", smooth=True)
    for i in range(13):
        x = x0 + (x1 - x0) * i / 12
        B.tube([(x, y0 + span * j / 16, 14.1 + 7.0 * math.sin(math.pi * j / 16)) for j in range(17)], [0.14] * 17, "M_Steel", 6)
    # --- Pier Park: rides, toilets, Skyline Stage
    B.lathe([(6.6, 0.06), (6.6, 0.9), (6.2, 0.9), (6.2, 4.2), (6.9, 4.4), (3.0, 6.6), (0.6, 7.6), (0.0, 7.8)], "M_Carousel", 32, center=(X(1650.3), Y(426.7), 0))
    B.lathe([(5.4, 0.06), (5.4, 0.5), (0.8, 0.5), (0.8, 8.0), (5.8, 9.5), (1.0, 12.0), (0.0, 12.4)], "M_Carousel", 32, center=(X(1650.0), Y(457.4), 0))
    B.cyl((X(1651.6), Y(476.0), 0.06), 38.0, 1.1, "M_WheelWhite", 16)                      # drop tower
    B.cyl((X(1652.9), Y(488.6), 0.06), 22.0, 0.6, "M_WheelWhite", 12)                      # light tower
    B.boxmm((X(1656.7), Y(488.8), 0.06), (X(1673.9), Y(494.6), 4.0), "M_Brick")             # toilets
    B.boxmm((X(1626.6), Y(429.0), 0.06), (X(1641.8), Y(483.0), 0.16), "M_Lawn")             # mini golf
    # Skyline Stage: white membrane roof on masts over a raked seating bowl (OSM 1708.7..1784.2 x 435.1..486.2)
    sx0, sx1, sy0, sy1 = X(1708.7), X(1784.2), Y(435.1), Y(486.2)
    cx, cy = (sx0 + sx1) / 2, (sy0 + sy1) / 2
    rx, ry = (sx1 - sx0) / 2, (sy1 - sy0) / 2
    P = []
    for i in range(33):
        t = 2 * math.pi * i / 32
        col = []
        for j in range(9):
            s = j / 8
            r = 1 - s
            ripple = 0.5 + 0.5 * math.cos(6 * t)
            col.append(Vector((cx + rx * r * math.cos(t), cy + ry * r * math.sin(t), 9.0 + 9.0 * s ** 0.7 - 2.5 * ripple * (1 - s))))
        P.append(col)
    B.grid([c for c in P[:-1]], "M_Membrane", smooth=True, close_u=True)
    B.grid([[v - Vector((0, 0, 0.03)) for v in c] for c in P[:-1][::-1]], "M_Membrane", smooth=True, close_u=True)   # underside
    for i in range(6):
        t = 2 * math.pi * i / 6
        B.tube([(cx + rx * 0.98 * math.cos(t), cy + ry * 0.98 * math.sin(t), 0.06), (cx + rx * 0.98 * math.cos(t), cy + ry * 0.98 * math.sin(t), 11.0)], [0.25, 0.2], "M_Steel", 8, cap1=True)
    B.tube([(cx, cy, 0.06), (cx, cy, 21.0)], [0.45, 0.35], "M_Steel", 10, cap1=True)
    B.slab([(cx - rx * 0.8, cy - ry * 0.5), (cx + rx * 0.2, cy - ry * 0.5), (cx + rx * 0.2, cy + ry * 0.5), (cx - rx * 0.8, cy + ry * 0.5)], 0.06, 1.2, "M_DeckConcrete")
    # --- Chicago Shakespeare Theater (south side) and the east parking garage
    brick_block(B, X(1786.0), X(1870.0), Y(408.5), Y(429.0), 19.0, bay=7.0, storey=4.6)
    brick_block(B, X(1799.5), X(1863.0), Y(429.5), Y(yn), 15.0, bay=6.5, storey=3.0, glass="M_GarageOpening")
    # --- Festival Hall: brick halls with the white fabric vaults; the Sable hotel along its south side
    brick_block(B, X(1863.0), X(1955.0), Y(430.0), Y(yn), 16.0, bay=7.5, storey=5.0)
    fx0, fx1, fy0, fy1 = X(1955.0), X(2220.0), Y(430.0), Y(yn)
    brick_block(B, fx0, fx1, fy0, fy1, 11.0, bay=8.0, storey=5.4)        # two storeys of bays under the fabric vaults
    nb = 4
    bw = (fx1 - fx0) / nb
    for b in range(nb):
        bx0 = fx0 + bw * b
        bcx, bcy = bx0 + bw / 2, (fy0 + fy1) / 2
        hx, hy = bw / 2, (fy1 - fy0) / 2
        # groin vault: z = 11 + 11 * min(cos-shaped in x, in y)
        P = []
        for i in range(17):
            u = -1 + 2 * i / 16
            col = []
            for j in range(17):
                v = -1 + 2 * j / 16
                z = 11.2 + 11.0 * min(math.cos(u * math.pi / 2), math.cos(v * math.pi / 2)) ** 0.8
                col.append(Vector((bcx + hx * u, bcy + hy * v, z)))
            P.append(col)
        B.grid(P, "M_Membrane", smooth=False)
        for diag in (1, -1):
            B.tube([(bcx + hx * t, bcy + hy * t * diag, 11.2 + 11.0 * math.cos(abs(t) * math.pi / 2) ** 0.8 + 0.15) for t in [-1 + 2 * k / 16 for k in range(17)]],
                   [0.25] * 17, "M_Steel", 6)
    brick_block(B, X(1951.1), X(2186.4), Y(408.5), Y(430.0), 26.0, bay=4.5, storey=3.6, wall="M_HotelBrick")
    # --- West Terminal and Lakeview Terrace (east of the plan edge, real footprints)
    brick_block(B, X(2220.0), X(2241.0), Y(433.3), Y(509.0), 10.0, bay=6.0, storey=4.8)
    brick_block(B, X(2241.0), X(2318.0), Y(440.0), Y(506.0), 9.5, bay=6.0, storey=4.6)
    P = [[Vector((X(2245.0) + 55.0 * i / 10, Y(462.0) + 23.0 * j / 8, 9.6 + 4.0 * math.sin(math.pi * j / 8))) for j in range(9)] for i in range(11)]
    B.grid(P, "M_Glass", smooth=True)
    ob = B.finish("LM_NavyPierBuildings", sharp_angle=40)
    site_export("LM_NavyPierBuildings", ob, {
        "pivot": "plan %s on the ground (same as LM_NavyPierDeck)" % (str(SITES["pier"]),),
        "buildings_plan_m": {"headhouse_front": [1496, 1512], "twin_towers_y": [427.7, 482.6], "family_pavilion": [1512, 1572],
                             "crystal_gardens": [1572, 1625], "pier_park": [1625, 1800], "skyline_stage": [1708.7, 1784.2],
                             "shakespeare": [1786, 1870], "garage": [1799.5, 1863], "festival_hall": [1863, 2220], "sable_hotel": [1951.1, 2186.4],
                             "west_terminal": [2220, 2241], "lakeview_terrace": [2241, 2318]},
        "y_band_m": [PIER["walk_s"], PIER["walk_n"]],
        "notes": "buildings keep between the plan's pier roads (y 406.4..496.4); Festival Hall's real north wing (to y 514) is "
                 "cut back so the north drive stays continuous"})


def navy_pier_ballroom_v2():
    """Grand Ballroom (Aon), east end: a two-storey brick drum (r 29.75 m, centre plan (2354, 474)) with a shallow ribbed
    copper dome and an E-W skylight, a west block between two square towers (plan (2329, 449.3) / (2329, 498.7), 10.4 m)."""
    ox, oy = SITES["pier"]
    B = PlanBuilder()
    cx, cy = 2354.0 - ox, 474.0 - oy
    R = 29.75
    br, ls, gl = "M_Brick", "M_Limestone", "M_Glass"
    # drum: lower arcade of tall arched windows, attic band, cornice + balustrade
    n = 28
    for k in range(n):
        a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
        if math.cos((a0 + a1) / 2) < -0.55:            # the west part is the entrance block
            continue
        p0 = Vector((cx + R * math.cos(a0), cy + R * math.sin(a0), 0.06))
        p1 = Vector((cx + R * math.cos(a1), cy + R * math.sin(a1), 0.06))
        r = (p1 - p0)
        w = r.length
        B.wall(p0, r, (0, 0, 1), w, 9.0, 0.6, br, [(w / 2, w * 0.5, 0.6, 6.4, True)], gl, 0.7, segs=8, edges=False)
        B.wall(p0 + Vector((0, 0, 9.0)), r, (0, 0, 1), w, 5.0, 0.6, br, [(w / 2, w * 0.35, 1.2, 3.6, False)], gl, 0.6, edges=False)
    B.lathe([(R + 0.3, 8.7), (R + 0.3, 9.2), (R, 9.2)], ls, 64, center=(cx, cy, 0))
    B.lathe([(R + 0.1, 0.06), (R + 0.1, 0.9), (R, 0.9)], ls, 64, center=(cx, cy, 0))
    B.lathe([(R + 0.6, 14.0), (R + 0.6, 14.6), (R - 0.2, 14.6), (R - 0.2, 14.0)], ls, 64, center=(cx, cy, 0))
    B.lathe([(R - 0.2, 14.6), (R - 0.2, 15.6), (R - 0.6, 15.6), (R - 0.6, 14.6)], ls, 64, center=(cx, cy, 0))   # parapet
    # dome: shallow (springs at 15 m from r 26, crown 25 m), 24 ribs, skylight band on top running E-W
    prof = [(26.0 * math.cos(t), 15.0 + 10.0 * math.sin(t)) for t in [math.pi / 2 * k / 16 for k in range(17)]]
    B.lathe([(R - 0.6, 14.6), (26.3, 14.9)] + prof, "M_Roof", 64, center=(cx, cy, 0))
    for k in range(24):
        a = 2 * math.pi * k / 24
        d = Vector((math.cos(a), math.sin(a), 0))
        B.tube([Vector((cx, cy, 0)) + d * (r + 0.1) + Vector((0, 0, z + 0.08)) for r, z in prof[:-1]], [0.16] * (len(prof) - 1), "M_RoofRib", 5)
    B.boxmm((cx - 10.0, cy - 2.2, 24.2), (cx + 10.0, cy + 2.2, 25.6), "M_GlassDark")
    # west entrance block between the towers
    wx0, wx1 = 2322.0 - ox, cx - 0.5 * R
    B.slab([(wx0, 446.0 - oy), (wx1 + 6, 446.0 - oy), (wx1 + 6, 502.0 - oy), (wx0, 502.0 - oy)], 0.06, 14.6, br)
    frame_ring(B, (wx0, wx1 + 6, 446.0 - oy, 502.0 - oy), 14.0, 14.7, 0.5, 0.7, ls)
    B.wall(Vector((wx0 - 0.02, 502.0 - oy, 0.06)), (0, -1, 0), (0, 0, 1), 56.0, 9.0, 0.5, br, bays(56.0, 6, 3.4, 0.6, 6.0, True), gl, 0.7, edges=False)
    top = 0.0
    for ty in (449.3, 498.7):
        top = pier_tower(B, 2329.4 - ox, ty - oy, 10.4, 26.0, ch=1.0, dome="M_Limestone", lantern="M_Limestone", spire=True)
    ob = B.finish("LM_NavyPierBallroom", sharp_angle=40)
    site_export("LM_NavyPierBallroom", ob, {
        "pivot": "plan %s on the ground (same as LM_NavyPierDeck)" % (str(SITES["pier"]),),
        "drum": {"centre_plan_m": [2354.0, 474.0], "radius_m": R, "cornice_m": 14.6}, "dome_crown_m": 25.0, "towers_top_m": round(top, 1)})


def polk_bros_park():
    """Polk Bros Park and the pier's entrance plaza (plan-local to the pier origin). Polk Bros Plaza (OSM x 1398..1470,
    y 434..475) with the 22.6 m round fountain (centre (1427.1, 454.25)); clipped to the sidewalks of the Streeter Drive
    loop (x 1391.5..1464.1) and Grand Avenue's south sidewalk; the entrance forecourt x 1482.8..1496."""
    ox, oy = SITES["pier"]
    B = PlanBuilder()
    T = lambda pts: [(x - ox, y - oy) for x, y in pts]
    PAVE = 0.06
    gl = lambda x: 492.1 + (x - 1380.0) * 0.1415 - 11.9            # Grand Ave south sidewalk edge
    plaza = [(1392.0, 434.0), (1464.0, 434.0), (1464.0, min(475.0, gl(1464.0) - 0.4)), (1392.0, min(475.0, gl(1392.0) - 0.4))]
    B.slab(T(plaza), -0.3, PAVE, "M_ParkPaver")
    # decorative paving rings and radial mosaic bands round the fountain
    fc = (1427.1 - ox, 454.25 - oy)
    for r in (13.5, 16.0):
        B.sweep_closed(circle(fc[0], fc[1], r, 64), [(0.6, PAVE), (0.6, PAVE + 0.008), (0.0, PAVE + 0.008), (0.0, PAVE)], "M_MosaicBlue")
    for k in range(12):
        a = 2 * math.pi * k / 12
        p0 = (fc[0] + 12.0 * math.cos(a), fc[1] + 12.0 * math.sin(a)); p1 = (fc[0] + 18.5 * math.cos(a), fc[1] + 18.5 * math.sin(a))
        B.sweep_open([p0, p1], [(-0.35, PAVE), (-0.35, PAVE + 0.008), (0.35, PAVE + 0.008), (0.35, PAVE)], "M_MosaicYellow")
    # the fountain: flush granite ring and wet dark basin (an ice rink in winter)
    B.sweep_closed(circle(fc[0], fc[1], 11.3, 64), [(0.8, PAVE), (0.8, PAVE + 0.12), (0.0, PAVE + 0.12), (0.0, PAVE)], "M_GraniteDark")
    B.slab(circle(fc[0], fc[1], 11.31, 64), PAVE - 0.05, PAVE + 0.02, "M_Water")
    # entrance forecourt in front of the headhouse
    B.slab(T([(1482.8, PIER["walk_s"]), (1496.0, PIER["walk_s"]), (1496.0, PIER["walk_n"]), (1482.8, PIER["walk_n"])]), -0.3, PAVE, "M_DeckPaving")
    for y in (420.0, 445.0, 465.0, 488.0):
        B.box((1487.5 - ox, y - oy, PAVE + 0.45), (1.2, 1.2, 0.9), "M_GraniteDark")
        B.ellipsoid((1487.5 - ox, y - oy, PAVE + 1.25), (0.75, 0.75, 0.55), "M_Hedge", 10, 5)
    # welcome pavilion canopy at the plaza's west side (Peoples Energy Welcome Pavilion stand-in: a light steel canopy)
    B.boxmm((1394.0 - ox, 437.0 - oy, 5.0), (1404.0 - ox, 471.0 - oy, 5.4), "M_WheelWhite")
    for y in (438.5, 454.0, 469.5):
        for x in (1395.5, 1402.5):
            B.cyl((x - ox, y - oy, PAVE), 5.0 - PAVE, 0.18, "M_Steel", 8)
    ob = B.finish("LM_PolkBrosPark", sharp_angle=50)
    site_export("LM_PolkBrosPark", ob, {"pivot": "plan %s on the ground (same as LM_NavyPierDeck)" % (str(SITES["pier"]),),
                                        "fountain_centre_plan_m": [1427.1, 454.25], "fountain_radius_m": 11.3})


def polk_bros_jets():
    """Water jets for Polk Bros Park's fountain (no collision), same origin as the pier assets."""
    ox, oy = SITES["pier"]
    B = PlanBuilder()
    fc = Vector((1427.1 - ox, 454.25 - oy, 0.08))
    j = mat("M_WaterJet")
    for k in range(24):
        a = 2 * math.pi * k / 24
        d = Vector((math.cos(a), math.sin(a), 0))
        _arc(B, fc + d * 9.5, fc + d * 4.0, 3.6, j, 0.05, 0.16, n=10)
    B.lathe([(0.0, 0.1), (0.35, 0.2), (0.5, 2.0), (0.8, 4.6), (0.4, 5.6), (0.0, 5.8)], j, 24, center=(fc.x, fc.y, 0))
    ob = B.finish("LM_PolkBrosJets", sharp_angle=60)
    site_export("LM_PolkBrosJets", ob, {"pivot": "plan %s (same as LM_NavyPierDeck)" % (str(SITES["pier"]),)})


def navy_pier_v2():
    pier_deck(); reset()
    navy_pier_buildings(); reset()
    navy_pier_ballroom_v2(); reset()
    polk_bros_park(); reset()
    polk_bros_jets()



def _import(name, loc=(0, 0, 0), rot=(0, 0, 0)):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=f"{OUT}/{name}.glb")
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        if o.parent is None:
            o.location = Vector(loc)
            o.rotation_mode = "XYZ"
            o.rotation_euler = rot
    return new


def _simple_mat(name, rgb, rough=0.6, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def _scene_setup(skyline=False, ground_z=0.0, water=None):
    sc = bpy.context.scene
    # ground: two-tone 2 m checker so scale and reflections read
    bpy.ops.mesh.primitive_plane_add(size=4000, location=(0, 0, ground_z - 0.01))
    g = bpy.context.object
    gm = bpy.data.materials.new("PV_Ground")
    gm.use_nodes = True
    nt = gm.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    chk = nt.nodes.new("ShaderNodeTexChecker")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.25, 0.25, 0.25)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], chk.inputs["Vector"])
    chk.inputs["Color1"].default_value = (0.30, 0.30, 0.29, 1)
    chk.inputs["Color2"].default_value = (0.36, 0.36, 0.35, 1)
    chk.inputs["Scale"].default_value = 1.0
    nt.links.new(chk.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.8
    g.data.materials.append(gm)
    if water:   # a lake/river plane for bridges & piers
        bpy.ops.mesh.primitive_plane_add(size=1, location=water[0])
        w = bpy.context.object
        w.scale = water[1]
        w.data.materials.append(_simple_mat("PV_Lake", (0.05, 0.14, 0.17), 0.08))
    # sky: horizon-to-zenith gradient
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
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.80, 0.86, 0.93, 1)
    ramp.color_ramp.elements[1].position = 0.6
    ramp.color_ramp.elements[1].color = (0.22, 0.42, 0.78, 1)
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(48), 0, math.radians(-35)))
    sun = bpy.context.object
    sun.data.energy = 3.5
    sun.data.angle = math.radians(1.5)
    if skyline:   # a ring of plain towers so the mirror has something to reflect
        tm = _simple_mat("PV_Tower", (0.55, 0.57, 0.6), 0.5)
        tg = _simple_mat("PV_TowerDark", (0.18, 0.2, 0.23), 0.3)
        import random
        rnd = random.Random(7)
        for k in range(36):
            a = 2 * math.pi * k / 36 + rnd.uniform(-0.05, 0.05)
            d = rnd.uniform(70, 140)
            h = rnd.uniform(25, 120)
            bpy.ops.mesh.primitive_cube_add(size=1, location=(d * math.cos(a), d * math.sin(a), h / 2))
            o = bpy.context.object
            o.scale = (rnd.uniform(12, 26), rnd.uniform(12, 26), h)
            o.rotation_euler.z = a
            o.data.materials.append(tm if k % 3 else tg)


def _person(loc):
    pm = _simple_mat("PV_Person", (0.75, 0.12, 0.08), 0.6)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=1.5, location=(loc[0], loc[1], loc[2] + 0.75))
    bpy.context.object.data.materials.append(pm)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.13, location=(loc[0], loc[1], loc[2] + 1.66))
    bpy.context.object.data.materials.append(pm)


def _camera(objs, view=(-0.55, -1.0, 0.42), lens=35, res=(1280, 800), frame=1.0, target_z=None, target=None):
    sc = bpy.context.scene
    bpy.context.view_layer.update()          # moved imports: refresh matrix_world before measuring
    lo = Vector((1e9, 1e9, 1e9))
    hi = -lo
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    ctr = (lo + hi) / 2 if target is None else Vector(target)
    if target_z is not None:
        ctr.z = target_z
    rad = (hi - lo).length / 2 * frame
    d = Vector(view).normalized()
    sensor = 36.0
    hfov = 2 * math.atan(sensor / 2 / lens)
    vfov = 2 * math.atan(math.tan(hfov / 2) * res[1] / res[0])
    dist = rad / math.sin(vfov / 2)
    bpy.ops.object.camera_add(location=ctr + d * dist)
    cam = bpy.context.object
    cam.data.lens = lens
    cam.data.clip_end = 20000
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100


def _render(path, samples=48):
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
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


def _tweak_imported_materials():
    """Make water read as water in the preview (the GLB keeps simple PBR values; Unreal assigns its own MIs)."""
    for m in bpy.data.materials:
        base = m.name.split(".")[0]
        if not m.use_nodes:
            continue
        b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if b is None:
            continue
        if base == "M_WaterJet":
            b.inputs["Base Color"].default_value = (0.95, 0.97, 1.0, 1)
            b.inputs["Alpha"].default_value = 0.35
            b.inputs["Roughness"].default_value = 0.3
        if base == "M_Water":
            b.inputs["Roughness"].default_value = 0.02
        if base == "M_Glass":
            b.inputs["Roughness"].default_value = 0.05
            b.inputs["Metallic"].default_value = 0.6


def _preview(path, layout, skyline=False, view=(-0.55, -1.0, 0.42), person=None, frame=1.0, lens=35, target_z=None,
             water=None, target=None, res=(1280, 800), cam=None, ground_z=0.0, extras=()):
    reset()
    _scene_setup(skyline, ground_z=ground_z, water=water)
    land = _simple_mat("PV_Land", (0.33, 0.33, 0.32), 0.85)
    for lo, hi in extras:   # preview-only context blocks (embankments, approach decks)
        bpy.ops.mesh.primitive_cube_add(size=1, location=((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2))
        o = bpy.context.object
        o.scale = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
        o.data.materials.append(land)
    objs = []
    for item in layout:
        objs += _import(*item)
    _tweak_imported_materials()
    if person:
        _person(person)
    _camera(objs, view, lens, res, frame, target_z, target)
    if cam:   # explicit (location, look-at)
        c = bpy.context.scene.camera
        c.location = Vector(cam[0])
        c.rotation_euler = (Vector(cam[1]) - Vector(cam[0])).to_track_quat("-Z", "Y").to_euler()
    _render(path)




def _wheel_layout(rotor_deg=0.0):
    L = [("LM_CentennialWheel_Frame",), ("LM_CentennialWheel_Rotor", (0, 0, WHEEL["HUB"]), (0, math.radians(rotor_deg), 0))]
    for k in range(WHEEL["N"]):
        th = 2 * math.pi * k / WHEEL["N"] + math.radians(rotor_deg)
        L.append(("LM_CentennialWheel_Gondola", (WHEEL["R_ATT"] * math.sin(th), 0, WHEEL["HUB"] - WHEEL["R_ATT"] * math.cos(th))))
    return L


def _pier_layout():
    L = [("LM_NavyPierHeadhouse",)]
    y0 = 13.0
    for k in range(3):
        L.append(("LM_NavyPierShed", (0, y0 + 60 * k, 0), (0, 0, math.pi)))
    L.append(("LM_NavyPierBallroom", (0, y0 + 180 + 27.0, 0)))
    return L


def _bridge_layout():
    return [("LM_BridgeLeaf",), ("LM_BridgeLeaf", (0, -60, 0), (math.radians(-55), 0, math.pi)),
            ("LM_BridgeTenderHouse", (-18.0, 4.5, 0)), ("LM_BridgeTenderHouse", (18.0, 4.5, 0)),
            ("LM_BridgeTenderHouse", (-18.0, -64.5, 0), (0, 0, math.pi)), ("LM_BridgeTenderHouse", (18.0, -64.5, 0), (0, 0, math.pi))]


def _site_wheel_layout(origin_plan, rotor_deg=4.3):
    """The Centennial Wheel at its real place (plan (1684.4, 458.0)) in a pier-origin site preview (Blender coords)."""
    px, py = 1684.4 - origin_plan[0], 458.0 - origin_plan[1]
    bx, by = py, -px
    L = [("LM_CentennialWheel_Frame", (bx, by, 0.06)), ("LM_CentennialWheel_Rotor", (bx, by, WHEEL["HUB"] + 0.06), (0, math.radians(rotor_deg), 0))]
    for k in range(WHEEL["N"]):
        th = 2 * math.pi * k / WHEEL["N"] + math.radians(rotor_deg)
        L.append(("LM_CentennialWheel_Gondola", (bx + WHEEL["R_ATT"] * math.sin(th), by, WHEEL["HUB"] + 0.06 - WHEEL["R_ATT"] * math.cos(th))))
    return L


def _pier_site_layout():
    return ([("LM_NavyPierDeck",), ("LM_NavyPierBuildings",), ("LM_NavyPierBallroom",), ("LM_PolkBrosPark",), ("LM_PolkBrosJets",)]
            + _site_wheel_layout(SITES["pier"]))


def _bl(px, py, z):
    """plan-local (x east, y north, z) -> Blender preview coordinates."""
    return (py, -px, z)


PIER_EXTRAS = [((-45.0, -227.0, -6.0), (45.0, 150.0, 0.0)), ((-120.0, 13.0, -6.0), (35.0, 120.0, 0.0))]
PREVIEWS = {
    # site previews (plan-frame assets at their site origin; cameras given in plan-local metres via _bl)
    "Site_CloudGate": dict(layout=[("LM_CloudGatePlaza",), ("LM_CloudGate", (0, 0, BEAN_DECK))], skyline=True, person=_bl(-6.0, -9.0, BEAN_DECK),
                           cam=(_bl(-34.0, -20.0, 2.2), _bl(0.0, 0.0, 4.2)), lens=28),
    "Site_CloudGate_air": dict(layout=[("LM_CloudGatePlaza",), ("LM_CloudGate", (0, 0, BEAN_DECK))], skyline=False,
                               cam=(_bl(55.0, -95.0, 75.0), _bl(-8.0, 0.0, 0.0)), lens=35),
    "Site_Buckingham": dict(layout=[("LM_BuckinghamPlaza",), ("LM_BuckinghamFountain",), ("LM_BuckinghamJets",)], person=_bl(4.0, -60.0, 0.06),
                            cam=(_bl(0.0, -104.0, 1.8), _bl(0.0, 0.0, 8.0)), lens=30),
    "Site_Buckingham_close": dict(layout=[("LM_BuckinghamPlaza",), ("LM_BuckinghamFountain",), ("LM_BuckinghamJets",)],
                                  person=_bl(30.0, -36.0, 0.06), cam=(_bl(31.0, -40.0, 1.6), _bl(0.0, 0.0, 4.5)), lens=32),
    "Site_Buckingham_air": dict(layout=[("LM_BuckinghamPlaza",), ("LM_BuckinghamFountain",), ("LM_BuckinghamJets",)],
                                cam=(_bl(-110.0, -170.0, 120.0), _bl(0.0, -10.0, 0.0)), lens=35),
    "Site_NavyPier_SE": dict(layout=_pier_site_layout(), water=((0, -500, -5.66), (5000, 5000, 1)), ground_z=-12, extras=PIER_EXTRAS,
                             cam=(_bl(1060.0, -260.0, 190.0), _bl(820.0, 60.0, 0.0)), lens=35),
    "Site_NavyPier_W": dict(layout=_pier_site_layout(), water=((0, -500, -5.66), (5000, 5000, 1)), ground_z=-12, extras=PIER_EXTRAS,
                            cam=(_bl(-95.0, -40.0, 22.0), _bl(60.0, 5.0, 14.0)), lens=30),
    "Site_NavyPier_entrance": dict(layout=_pier_site_layout(), water=((0, -500, -5.66), (5000, 5000, 1)), ground_z=-12, extras=PIER_EXTRAS,
                                   cam=(_bl(-52.0, 0.0, 1.8), _bl(10.0, 0.0, 15.0)), lens=24),
    "Site_NavyPier_air": dict(layout=_pier_site_layout(), water=((0, -500, -5.66), (5000, 5000, 1)), ground_z=-12, extras=PIER_EXTRAS,
                              cam=(_bl(-260.0, -380.0, 420.0), _bl(420.0, 0.0, 0.0)), lens=35),
    # name: kwargs for _preview
    "LM_CloudGate": dict(layout=[("LM_CloudGate",)], skyline=True, person=(3.0, -8.0, 0), view=(-0.35, -1.0, 0.18), frame=0.9),
    "LM_CloudGate_under": dict(layout=[("LM_CloudGate",)], skyline=True, person=(0.6, -3.0, 0), view=(-0.05, -1.0, 0.02), frame=0.62,
                               target_z=4.5),
    "LM_BuckinghamFountain": dict(layout=[("LM_BuckinghamFountain",)], person=(-10, -43.5, 0), view=(-0.5, -1.0, 0.3), frame=0.5,
                                  target_z=1.0),
    "LM_BuckinghamJets": dict(layout=[("LM_BuckinghamJets",)], view=(-0.5, -1.0, 0.25), frame=0.9),
    "LM_BuckinghamFountain_withJets": dict(layout=[("LM_BuckinghamFountain",), ("LM_BuckinghamJets",)], person=(-10, -43.5, 0),
                                           view=(-0.5, -1.0, 0.16), frame=0.62, target_z=14.0),
    "LM_CentennialWheel": dict(layout=_wheel_layout(4.3), person=(6, -14, 0), view=(-0.55, -1.0, 0.2), frame=0.85),
    "LM_CentennialWheel_Frame": dict(layout=[("LM_CentennialWheel_Frame",)], person=(6, -14, 0)),
    "LM_CentennialWheel_Rotor": dict(layout=[("LM_CentennialWheel_Rotor", (0, 0, WHEEL["HUB"]))], view=(-0.4, -1.0, 0.1)),
    "LM_CentennialWheel_Gondola": dict(layout=[("LM_CentennialWheel_Gondola", (0, 0, 3.4))], person=(2.2, -1.0, 0), view=(-0.7, -1.0, 0.3),
                                       frame=1.2),
    "LM_NavyPierHeadhouse": dict(layout=[("LM_NavyPierHeadhouse",)], person=(0, -18, 0), view=(-0.5, -1.0, 0.25), frame=0.9),
    "LM_NavyPierShed": dict(layout=[("LM_NavyPierShed",)], person=(-40, -62, 0), view=(-0.8, -1.0, 0.45), frame=0.85,
                            water=((0, 0, -2.0), (2000, 2000, 1)), ground_z=-12),
    "LM_NavyPierBallroom": dict(layout=[("LM_NavyPierBallroom",)], person=(0, -30, 0), view=(-0.5, -1.0, 0.3), frame=0.9),
    "LM_NavyPier": dict(layout=_pier_layout(), view=(-1.0, -0.55, 0.35), frame=0.75, water=((0, 100, -2.0), (4000, 4000, 1)), ground_z=-12,
                        extras=[((-45, -60, -4), (45, 12, 0)), ((-300, -400, -4), (300, -60, 0)), ((-32, 233, -4), (32, 260, 0))]),
    "LM_BridgeTenderHouse": dict(layout=[("LM_BridgeTenderHouse",)], person=(2.5, -6.0, 0), view=(-0.6, -1.0, 0.25), frame=1.0),
    "LM_BridgeLeaf": dict(layout=[("LM_BridgeLeaf",)], person=(-12, -2, 0.2), view=(-1.0, -0.75, 0.12), frame=0.8,
                          target_z=-1.0, ground_z=-12, water=((0, 0, -6.0), (2000, 2000, 1))),
    "LM_BridgeRailing10": dict(layout=[("LM_BridgeRailing10",)], person=(1.0, -5.0, 0), view=(-1.0, -0.35, 0.2), frame=1.1),
    "LM_BasculeBridge": dict(layout=_bridge_layout(), view=(-1.0, -0.55, 0.28), frame=0.7, water=((0, -30, -6.0), (4000, 4000, 1)),
                             ground_z=-12, extras=[((-200, 0.0, -9), (200, 150, 0)), ((-200, -210, -9), (200, -60.0, 0))]),
}


def render_previews(names):
    for name in (names or list(PREVIEWS)):
        kw = dict(PREVIEWS[name])
        _preview(f"{BASE}/preview_{name}.png", **kw)


JOBS = {
    "bean": lambda: (cloud_gate(), reset(), cloud_gate_plaza()),
    "fountain": lambda: (buckingham_fountain(), reset(), buckingham_jets(), reset(), buckingham_plaza()),
    "wheel": centennial_wheel,
    "pier": navy_pier_v2,
    "bridge": bridge,
}


def write_json():
    path = BASE + "/landmarks.json"
    data = {}
    if os.path.exists(path):
        try:
            data = json.load(open(path))
        except Exception:
            data = {}
    assets = data.get("assets", {})
    assets.update(META)
    data["assets"] = dict(sorted(assets.items()))
    data["assembly"] = {
        "sites": {k: {"origin_plan_m": list(v), "unreal_cm": [v[1] * 100, v[0] * 100]} for k, v in SITES.items()},
        "cloud_gate": "LM_CloudGatePlaza at the bean site origin (ground); LM_CloudGate at +%.2f m on its deck, no rotation (long axis north-south)" % BEAN_DECK,
        "buckingham": "LM_BuckinghamPlaza, LM_BuckinghamFountain, LM_BuckinghamJets all at the fountain site origin, no rotation",
        "centennial_wheel": {
            "where": "plan (1684.4, 458.0) on Pier Park (OSM), wheel plane north-south (Unreal X-Z), axle east-west",
            "frame": "LM_CentennialWheel_Frame at P (deck surface under the hub)",
            "rotor": "LM_CentennialWheel_Rotor at P + (0, 0, %.1f) m = Unreal Z +%d cm; animate about the Unreal Y axis (axle)" % (WHEEL["HUB"], WHEEL["HUB"] * 100),
            "gondolas": "42 x LM_CentennialWheel_Gondola, k = 0..41: world pos = hub + (%d sin(2 pi k/42), 0, -%d cos(2 pi k/42)) cm (Unreal), "
                        "kept upright; k = 0 hangs over the boarding deck (z 1.0 m)" % (WHEEL["R_ATT"] * 100, WHEEL["R_ATT"] * 100),
        },
        "navy_pier": "LM_NavyPierDeck, LM_NavyPierBuildings, LM_NavyPierBallroom, LM_PolkBrosPark, LM_PolkBrosJets all at the pier site origin "
                     "(plan %s, headhouse west facade on the pier centreline), no rotation" % (str(SITES["pier"]),),
        "bascule_bridge": {
            "leaf_a": "LM_BridgeLeaf at pivot A (deck top height), spanning +X in Unreal",
            "leaf_b": "LM_BridgeLeaf rotated 180 deg yaw, pivot 60 m from A along the bridge axis; tips meet mid-river",
            "open": "pitch each leaf up about its own origin (0..80 deg)",
            "tender_houses": "4 x LM_BridgeTenderHouse, about 18 m either side of the road axis, 4.5 m behind each pivot (on the abutments), "
                             "relief faces along the roadway",
            "railings": "LM_BridgeRailing10 continues the leaf railings along the approaches (x = +/-13.7 m from the axis, base on the 0.2 m sidewalk)",
        },
    }
    data["previews"] = sorted(os.path.basename(f) for f in os.listdir(BASE) if f.startswith("preview_") and f.endswith(".png"))
    data["conventions"] = {
        "units": "metres in Blender/GLB; Unreal imports as centimetres",
        "axes": "Blender (x, y, z) -> Unreal (x, -y, z) (glTF import, verified): Blender +X = Unreal +X = plan north; site assets are plan-frame, placed unrotated",
        "origin": "centred on the origin, standing on z = 0, except where 'pivot' says otherwise",
        "generator": "Scripts/landmarks/blender_landmarks.py",
    }
    json.dump(data, open(path, "w"), indent=2)
    print("wrote", path)


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
