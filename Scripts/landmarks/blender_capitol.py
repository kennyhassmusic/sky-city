"""Sky City: the Texas State Capitol (Austin, 1882-88, Elijah E. Myers, sunset-red granite) and its grounds, modelled
procedurally in headless Blender from the HABS measured drawings (HABS TX-3326, 1986-88) and photographs, exported as GLB.

Why: Kenny asked (20 Oct 2026) for the Austin Capitol "as accurate as possible", with the masonry and concrete around it
and its walkways. build_city.py only had a box + sphere stand-in. References and the dimensions built to are listed in
SourceArt/Reference/TexasCapitol/sources.txt and below.

Conventions (same as Scripts/landmarks/blender_landmarks.py, whose Builder class is copied here unchanged):
  * real-world metres; z = 0 is the grade at the south front; the first floor (FFL) is 1.8 m above it;
  * one shared ORIGIN for every Capitol asset = the centre of the rotunda/dome at grade, so all of them get the same
    actor transform in Unreal (Scripts/roads/place_capitol_ue.py);
  * building frame: Blender +X = building east (toward Brazos St), +Y = building north (toward 15th St); the south front
    (the Great Walk, Congress Avenue) faces Blender -Y, the landmark convention's "front";
  * one bmesh per asset with per-face material indices; stable slot names (M_*), mapped to MI_Cap_* in Unreal;
  * metre-scale UVs (arc-length on grids, box projection elsewhere); smooth shading on curved surfaces only.

Key dimensions (HABS sheets 10 first-floor plan, 43 roof plan, 46 north wing, 54 south elevation, 69 dome section):
  overall length E-W 537'-11" = 163.96 m between the end vestibule faces (u = +-81.95)   [sheet 10 dimension string]
  end pavilions 73'-1 3/4" = 22.3 m E-W x 172'-1 5/8" = 52.46 m N-S; vestibules 13'-11" = 4.24 m deep, 27.1 m wide
  hyphens (E/W wings) 124'-8" = 38.0 m long, 30.2 m deep (v = +-15.1); central block 114'-4" = 34.85 m wide
  north wing 140'-2 1/2" = 42.74 m wide, its face 46.3 m north of the rotunda centre, porch to 54 m
  south wing 34.85 m wide, its face 37.0 m south of the rotunda centre; the great arch 11.6 m wide, crown 25.2 m
  storeys (above grade): first floor 1.8, 2nd 8.1, 3rd 14.5, 4th (attic) 20.5, attic floor 26.6 [sheet 69 + 1.8 m]
  main entablature 19.4-22.4 m; hyphen parapet 24.5 m; wing attic cornice 26.3-27.3 m; pediments to 36.7 / 37.6 m
  dome: lower drum r 14.6 to 39.6 m; peristyle of 20 columns at r 13.8, 41.8-50.0 m; balcony 52.6 m; upper drum r 11.6
  to 60.2 m; dome shell r 10.1 at 64 m to the lantern at 74 m (20 ribs, 20 oval lucarnes); lantern to 87.2 m;
  Goddess of Liberty 4.6 m (15'-7 1/2") to the top of her star at 91.8 m (official height 302.64 ft = 92.24 m)

Assets (SourceArt/Landmarks/capitol/<name>.glb, all at the shared origin unless noted):
  LM_Capitol_Building    wings, porches, the great arch and loggia, pediments, cornices, roofs, vent cupolas, steps
  LM_Capitol_Dome        lower drum, peristyle, balcony, upper drum, ribbed dome, lantern, the Goddess of Liberty
  LM_Capitol_Grounds     lawns, Great Walk (black-and-white diamond paving), oval drive with granite curbs, walks,
                         monuments as simple forms, fountains, the north (extension) court; fitted to the streets
  LM_Capitol_Fence10     10 m module of the 1890 cast-iron fence (star-capped pickets on a granite curb) along -Y
  LM_Capitol_GatePier    granite gate pier with cap (origin at its foot centre)
  LM_Capitol_Lamp        cast-iron lamp post with globe (origin at its foot)
  LM_Capitol_Tree        not built: the grounds keep the city's OpenStreetMap park trees (roadnet props)
Writes SourceArt/Landmarks/capitol/capitol.json: the frame (plan position and rotation of the origin), asset bounds,
fence runs, gate and lamp positions, and keep-out polygons (plan metres) where trees and props must not stand.

Run (repo root):
  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/landmarks/blender_capitol.py [-- jobs...]
    jobs: site building dome grounds kit (default: all; building/dome/grounds need site), then writes capitol.json
  ... -P Scripts/landmarks/blender_capitol.py -- --render [names...]
    renders SourceArt/Landmarks/capitol/preview_<name>.png (south, oblique, aerial, dome, walk; default: all)
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
BASE = ROOT + "/SourceArt/Landmarks/capitol"
OUT = BASE
os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
META = {}          # filled per asset, merged into capitol.json
LAYOUT = {}        # fence runs, gates, lamps, keep-outs, frame


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    MATS.clear()


# ------------------------------------------------------------------ materials
MATDEF = {
    #  name               base colour (linear)     metal rough  extra
    "M_Granite": ((0.50, 0.29, 0.22), 0.0, 0.62, {}),           # sunset-red granite, dressed ashlar
    "M_GraniteRough": ((0.36, 0.20, 0.15), 0.0, 0.88, {}),      # rock-faced base storey
    "M_GranitePolished": ((0.30, 0.15, 0.11), 0.0, 0.30, {}),   # monument dies, polished
    "M_DomeIron": ((0.55, 0.35, 0.27), 0.15, 0.50, {}),         # cast-iron dome, painted to match the granite
    "M_RoofMetal": ((0.33, 0.34, 0.34), 0.55, 0.45, {}),        # standing-seam metal roofs
    "M_Glass": ((0.025, 0.035, 0.045), 0.3, 0.08, {}),
    "M_Door": ((0.09, 0.05, 0.03), 0.2, 0.45, {}),
    "M_Statue": ((0.60, 0.58, 0.53), 0.3, 0.45, {}),            # the Goddess (painted aluminium)
    "M_Bronze": ((0.23, 0.16, 0.09), 0.9, 0.45, {}),
    "M_Lawn": ((0.09, 0.20, 0.05), 0.0, 0.95, {}),
    "M_Planting": ((0.05, 0.11, 0.03), 0.0, 1.00, {}),          # shrub and flower beds
    "M_PavingLight": ((0.58, 0.55, 0.50), 0.0, 0.80, {}),       # Great Walk diamonds
    "M_PavingDark": ((0.20, 0.20, 0.19), 0.0, 0.80, {}),
    "M_Concrete": ((0.48, 0.46, 0.42), 0.0, 0.85, {}),          # walks, aprons
    "M_Asphalt": ((0.055, 0.055, 0.06), 0.0, 0.90, {}),         # the drives
    "M_Curb": ((0.40, 0.26, 0.21), 0.0, 0.70, {}),              # granite curbs and copings
    "M_Iron": ((0.025, 0.025, 0.028), 0.6, 0.50, {}),           # fence, gates, lamp posts
    "M_Gold": ((0.80, 0.55, 0.18), 1.0, 0.30, {}),              # gilded fence stars
    "M_Water": ((0.05, 0.12, 0.14), 0.0, 0.03, {}),
    "M_Light": ((1.00, 0.93, 0.80), 0.0, 0.40, {"emit": 4.0}),  # lamp globes
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
    d = {"file": f"SourceArt/Landmarks/capitol/{name}.glb", "tris": tris,
         "bbox_min_m": [round(c, 3) for c in lo], "bbox_max_m": [round(c, 3) for c in hi],
         "size_m": [round(c, 3) for c in (hi - lo)], "materials": mats}
    d.update(meta or {})
    META[name] = d
    print(f"exported {name}: {tris} tris, size {tuple(round(c, 2) for c in hi - lo)}, mats {mats}")
    if tris > 80000:
        print("WARNING: over the 80k triangle budget:", name)


# ================================================================== site: plan frame, streets, the grounds outline
PLAN = json.load(open(ROOT + "/Saved/Mashup/plan_v3.json"))
RN = json.load(open(ROOT + "/Saved/Roads/roadnet.json"))
# The origin sits on the Congress Avenue axis, as in Austin: a least-squares fit of 1.2 km of roadnet centreline gives a
# bearing 1.92 deg east of plan north and x = -1464.8 at the Capitol (the OpenStreetMap footprint's centre is -1464.75;
# its hyphen block centres on y = -1136.5). The OSM tree rows of the Great Walk then sit symmetric at u = +-7.1 m.
R0 = (-1464.8, -1136.5)
AXIS_DEG = 1.92
PHI = math.radians(180.0 - AXIS_DEG)     # building frame -> plan: building north points to plan -y (Austin turned 164 deg)
CP, SP = math.cos(PHI), math.sin(PHI)
FFL = 1.8                                 # first floor above the south grade


def to_plan(u, v):
    return (R0[0] + CP * u - SP * v, R0[1] + SP * u + CP * v)


def to_local(x, y):
    dx, dy = x - R0[0], y - R0[1]
    return (CP * dx + SP * dy, -SP * dx + CP * dy)


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


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def poly_dist(p, poly):
    return min(seg_dist(p, poly[i - 1], poly[i]) for i in range(len(poly)))


def area(poly):
    return 0.5 * sum(poly[i - 1][0] * poly[i][1] - poly[i][0] * poly[i - 1][1] for i in range(len(poly)))


CORR = []        # street corridors (carriageways, junctions, sidewalks) near the Capitol, local metres, with bboxes


def load_corridors():
    CORR.clear()
    # junction rings carry no sidewalk polygon round their corners: give them their sidewalk width as a margin
    srcs = [(RN["walk"], None), ([e["ribbon"] for e in RN["edges"] if e["ribbon"]], None),
            ([j["ring"] for j in RN["junctions"]], [j.get("sw", 3.8) for j in RN["junctions"]]), (RN["joints"], None)]
    for src, margins in srcs:
        for k, poly in enumerate(src):
            L = [to_local(*p) for p in poly]
            xs = [p[0] for p in L]
            ys = [p[1] for p in L]
            bb = (min(xs), min(ys), max(xs), max(ys))
            if bb[2] < -280 or bb[0] > 280 or bb[3] < -300 or bb[1] > 340:
                continue
            CORR.append((bb, L, margins[k] if margins else 0.0))


def on_street(p, margin=0.0):
    for bb, poly, m0 in CORR:
        mm = margin + m0
        if bb[0] - mm <= p[0] <= bb[2] + mm and bb[1] - mm <= p[1] <= bb[3] + mm:
            if in_poly(p, poly) or (mm > 0 and poly_dist(p, poly) < mm):
                return True
    return False


def _resample_ue(pts, step):          # build_city.resample
    out_ = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(math.dist(a, b) / step))
        for i in range(1, n + 1):
            out_.append((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n))
    return out_


def expressway_piers():
    """The elevated expressways' piers exactly as build_city.stage_elevated places them (every >= 40 m where the deck is
    above 4 m), in local metres. Nothing of ours may stand on them."""
    out = []
    for r in PLAN["roads"]:
        if not r.get("elevated"):
            continue
        pts = _resample_ue([(p[1] * 100.0, p[0] * 100.0) for p in r["pts"]], 1500.0)
        s = [0.0]
        for a, b in zip(pts, pts[1:]):
            s.append(s[-1] + math.dist(a, b))
        L = s[-1]
        rr = min(15000.0, L / 2.5)
        zs = []
        for d in s:
            f = min(1.0, d / rr, (L - d) / rr)
            f = f * f * (3 - 2 * f)
            zs.append(7.0 + (900.0 - 7.0) * f)
        acc = 0.0
        for i in range(1, len(pts)):
            acc += math.dist(pts[i - 1], pts[i])
            if acc >= 4000 and zs[i] > 400:
                acc = 0.0
                q = to_local(pts[i][1] / 100.0, pts[i][0] / 100.0)
                if abs(q[0]) < 300 and -320 < q[1] < 340:
                    out.append(q)
    return out


BLDG = []        # City Sample building footprints near the Capitol (plan buildings_v3), local metres


def load_buildings():
    BLDG.clear()
    for b in json.load(open(ROOT + "/Saved/Mashup/buildings_v3.json"))["buildings"]:
        u, v = to_local(b["x"], b["y"])
        if abs(u) > 300 or not -320 < v < 340:
            continue
        c, s_ = math.cos(math.radians(b["yaw"])), math.sin(math.radians(b["yaw"]))
        pts = [(b["x"] + c * a * b["w"] / 2 - s_ * d * b["d"] / 2, b["y"] + s_ * a * b["w"] / 2 + c * d * b["d"] / 2)
               for a, d in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        BLDG.append([to_local(*p) for p in pts])


def blocked(p):
    return on_street(p, 0.35) or any(in_poly(p, b) or poly_dist(p, b) < 1.5 for b in BLDG if abs(b[0][0] - p[0]) < 60 and abs(b[0][1] - p[1]) < 60)


def grounds_outline():
    """The plan's Capitol grounds park polygon in local metres, fitted to the streets: pulled back wherever it reaches a
    street corridor (carriageway, junction or sidewalk) so nothing of ours covers a roadway, and pushed out (up to 12 m)
    to the back of the sidewalk where the park polygon stops short of it; counter-clockwise."""
    park = None
    for pk in PLAN["parks"]:
        if in_poly(R0, pk):
            park = pk
            break
    L = [to_local(*p) for p in park]
    if L[0] == L[-1]:
        L = L[:-1]
    if area(L) < 0:
        L = L[::-1]
    dense = []
    for i in range(len(L)):
        a, b = Vector((*L[i], 0)), Vector((*L[(i + 1) % len(L)], 0))
        n = max(1, int((b - a).length / 1.5))
        for k in range(n):
            dense.append(a.lerp(b, k / n))
    out = []
    N = len(dense)
    for i in range(N):
        p = dense[i]
        t = (dense[(i + 1) % N] - dense[i - 1])
        t.normalize()
        inward = Vector((-t.y, t.x, 0))
        q = p.copy()
        if blocked((q.x, q.y)):
            for _ in range(80):
                if not blocked((q.x, q.y)):
                    break
                q += inward * 0.25
        else:
            r = q.copy()
            for _ in range(48):
                r2 = r - inward * 0.25
                if blocked((r2.x, r2.y)):
                    q = r
                    break
                r = r2
        out.append((q.x, q.y))
    sm = [((out[i - 1][0] + 2 * out[i][0] + out[(i + 1) % N][0]) / 4, (out[i - 1][1] + 2 * out[i][1] + out[(i + 1) % N][1]) / 4) for i in range(N)]
    sm = [p if not blocked(p) else out[i] for i, p in enumerate(sm)]
    for _ in range(3):   # drop near-collinear points and spikes (turns sharper than 150 deg)
        keep = []
        n = len(sm)
        for i in range(n):
            a, b, c = Vector((*sm[i - 1], 0)), Vector((*sm[i], 0)), Vector((*sm[(i + 1) % n], 0))
            d1, d2 = (b - a), (c - b)
            if d1.length < 0.3 or d2.length < 1e-6:
                continue
            if d1.normalized().dot(d2.normalized()) < -0.87:
                continue
            if seg_dist(sm[i], sm[i - 1], sm[(i + 1) % n]) > 0.12:
                keep.append(sm[i])
        sm = keep
    return sm


def offset_poly(poly, d):
    """Mitred offset of a closed CCW polygon (d > 0 outward)."""
    n = len(poly)
    out = []
    for i in range(n):
        a, b, c = Vector((*poly[i - 1], 0)), Vector((*poly[i], 0)), Vector((*poly[(i + 1) % n], 0))
        t1 = (b - a).normalized()
        t2 = (c - b).normalized()
        n1 = Vector((t1.y, -t1.x, 0))
        n2 = Vector((t2.y, -t2.x, 0))
        m = n1 + n2
        k = 1.0 + n1.dot(n2)
        q = b + m * (d / k) if k > 1e-3 else b + n1 * d
        out.append((q.x, q.y))
    return out


SITE = {}


def site():
    load_corridors()
    load_buildings()
    SITE["outline"] = grounds_outline()
    SITE["piers"] = expressway_piers()
    v11 = None   # 11th Street's north back-of-walk on the axis (local v), measured from the corridors
    v = -150.0
    while v > -260:
        if on_street((0.0, v)):
            v11 = v
            break
        v -= 0.25
    SITE["v11"] = v11
    print("site: outline", len(SITE["outline"]), "pts; piers", len(SITE["piers"]), "; 11th St sidewalk at v =", v11)
    LAYOUT["frame"] = {"origin_plan_m": list(R0), "axis_deg_east_of_plan_north": AXIS_DEG, "phi_deg": round(math.degrees(PHI), 4),
                       "local_to_plan": "x = x0 + cos(phi) u - sin(phi) v,  y = y0 + sin(phi) u + cos(phi) v",
                       "ffl_m": FFL}
    LAYOUT["grounds_outline_local"] = [[round(a, 2), round(b, 2)] for a, b in SITE["outline"]]
    LAYOUT["piers_local"] = [[round(a, 2), round(b, 2)] for a, b in SITE["piers"]]


# ================================================================== 1. the building (1888 Renaissance Revival, granite)
# heights above the south grade (HABS sheet 54 south elevation, 1:240, measured on a metre grid; sheet 69 levels + 1.8 m)
Z = dict(plinth=1.0, belt0=7.8, belt1=8.4, dado1=9.6, band0=13.8, band1=14.3, ent0=19.4, ent1=22.4,
         parapet=24.5, attic1=26.3, cornice1=27.3, parapet_w=28.3)
WIN = dict(w=1.15, gap=0.45, f1=(1.9, 6.3), f2=(10.0, 13.5), f3=(15.0, 18.5), att=(22.9, 25.2))
REV = 0.42           # windows are set back 0.42 m in the granite
UP = Vector((0, 0, 1))


def seg_of(p0, p1):
    a = Vector((p0[0], p0[1], 0))
    b = Vector((p1[0], p1[1], 0))
    t = b - a
    L = t.length
    t /= L
    return (a, t, Vector((t.y, -t.x, 0)), L)


def facade_band(B, seg, z0, z1, holes, m, rev=None):
    """Flat wall from z0 to z1 along seg (front faces only: the inside is never seen), with rectangular openings
    holes = [(x0, x1, h0, h1, fill_material)]; each opening gets jambs, sill, head and a recessed pane."""
    a, t, n, L = seg
    F = lambda x, z: a + t * x + UP * z
    hs = [(max(0.0, h[0]), min(L, h[1]), max(z0, h[2]), min(z1, h[3]), h[4]) for h in holes]
    hs = [h for h in hs if h[1] - h[0] > 0.05 and h[3] - h[2] > 0.05]
    zs = sorted(set([z0, z1] + [h[2] for h in hs] + [h[3] for h in hs]))
    for za, zb in zip(zs, zs[1:]):
        zm = (za + zb) / 2
        cover = sorted((h[0], h[1]) for h in hs if h[2] <= zm <= h[3])
        x = 0.0
        runs = []
        for x0, x1 in cover:
            if x0 > x + 1e-6:
                runs.append((x, x0))
            x = max(x, x1)
        if x < L - 1e-6:
            runs.append((x, L))
        for x0, x1 in runs:
            B.face([F(x0, za), F(x1, za), F(x1, zb), F(x0, zb)], m, [(x0, za), (x1, za), (x1, zb), (x0, zb)])
    d = -n * (REV if rev is None else rev)
    for x0, x1, h0, h1, fill in hs:
        A, Bq, C, D = F(x0, h0), F(x1, h0), F(x1, h1), F(x0, h1)
        B.face([A, A + d, D + d, D], m)                   # left jamb (faces +t)
        B.face([Bq, C, C + d, Bq + d], m)                 # right jamb
        B.face([A, Bq, Bq + d, A + d], m)                 # sill
        B.face([D, D + d, C + d, C], m)                   # head
        if fill:
            B.face([A + d, Bq + d, C + d, D + d], fill, [(x0, h0), (x1, h0), (x1, h1), (x0, h1)])


def obox(B, seg, x, w, z0, z1, proj, m, back=0.0):
    """Box standing proud of the wall line of seg (pilaster, pier, pedestal): front, sides, top, bottom."""
    a, t, n, L = seg
    P = lambda xx, dd, z: a + t * xx + n * dd + UP * z
    x0, x1, d0, d1 = max(0.0, x - w / 2), min(L, x + w / 2), -back, proj      # never overhang the building's corners
    B.face([P(x0, d1, z0), P(x1, d1, z0), P(x1, d1, z1), P(x0, d1, z1)], m)
    B.face([P(x0, d0, z0), P(x0, d1, z0), P(x0, d1, z1), P(x0, d0, z1)], m)
    B.face([P(x1, d0, z0), P(x1, d0, z1), P(x1, d1, z1), P(x1, d1, z0)], m)
    B.face([P(x0, d0, z1), P(x0, d1, z1), P(x1, d1, z1), P(x1, d0, z1)], m)
    B.face([P(x0, d0, z0), P(x1, d0, z0), P(x1, d1, z0), P(x0, d1, z0)], m)


def miter_offsets(P, proj, closed):
    n = len(P)
    nrm = lambda i, j: (lambda t: Vector((t.y, -t.x, 0)))((P[j] - P[i]).normalized())
    offs = []
    for i in range(n):
        if closed or 0 < i < n - 1:
            n1, n2 = nrm(i - 1, i), nrm(i, (i + 1) % n)
            k = 1.0 + n1.dot(n2)
            offs.append(P[i] + (n1 + n2) * (proj / k) if k > 1e-3 else P[i] + n1 * proj)
        elif i == 0:
            offs.append(P[0] + nrm(0, 1) * proj)
        else:
            offs.append(P[-1] + nrm(n - 2, n - 1) * proj)
    return offs


def band(B, pts, z0, z1, proj, m, closed=False, top=True, bottom=True, caps=True):
    """Horizontal moulding along a CCW wall line (pts), standing proj proud of it, mitred at every corner."""
    P = [Vector((p[0], p[1], 0)) for p in pts]
    Q = miter_offsets(P, proj, closed)
    n = len(P)
    fl = (lambda q: q[::-1]) if proj < 0 else (lambda q: q)   # an inward band (parapet backs) faces inward
    for i in (range(n) if closed else range(n - 1)):
        j = (i + 1) % n
        a, b, qa, qb = P[i], P[j], Q[i], Q[j]
        L = (qb - qa).length
        uv = [(0, z0), (L, z0), (L, z1), (0, z1)]
        B.face(fl([qa + UP * z0, qb + UP * z0, qb + UP * z1, qa + UP * z1]), m, fl(uv))
        if top:
            B.face(fl([a + UP * z1, qa + UP * z1, qb + UP * z1, b + UP * z1]), m)
        if bottom:
            B.face(fl([a + UP * z0, b + UP * z0, qb + UP * z0, qa + UP * z0]), m)
    if caps and not closed:
        B.face(fl([P[0] + UP * z0, Q[0] + UP * z0, Q[0] + UP * z1, P[0] + UP * z1]), m)
        B.face(fl([P[-1] + UP * z0, P[-1] + UP * z1, Q[-1] + UP * z1, Q[-1] + UP * z0]), m)


def mirror_pts(pts):
    return [(-u, v) for u, v in reversed(pts)]


# the building's wall line, counter-clockwise, east half from the great arch's east pier round to the north face
OUT_E = [(6.6, -37.0), (17.4, -37.0), (17.4, -15.1), (55.4, -15.1), (55.4, -26.2), (77.7, -26.2), (77.7, -13.55),
         (81.95, -13.55), (81.95, 13.55), (77.7, 13.55), (77.7, 26.2), (55.4, 26.2), (55.4, 15.1), (21.4, 15.1), (21.4, 46.3)]
OUTLINE = OUT_E + mirror_pts(OUT_E)                    # open: the great arch (u +-6.6) interrupts the mouldings
CLOSED = OUTLINE                                       # closed version (plinth) runs across the arch
UPPER = [(-17.4, -37.0), (17.4, -37.0), (17.4, 15.1), (21.4, 15.1), (21.4, 46.3), (-21.4, 46.3), (-21.4, 15.1), (-17.4, 15.1)]
UPPER_RUNS = [[(10.5, -37.0), (17.4, -37.0), (17.4, 15.1), (21.4, 15.1), (21.4, 46.3), (9.2, 46.3)],
              [(-9.2, 46.3), (-21.4, 46.3), (-21.4, 15.1), (-17.4, 15.1), (-17.4, -37.0), (-10.5, -37.0)]]
# facade spec per east-half segment (start point): kind, bays, corner pilasters at start/end, doors
SPEC_E = {
    (6.6, -37.0): ("wing", "front", None, None),
    (17.4, -37.0): ("wing", 4, "pair", "single"),
    (17.4, -15.1): ("low", 8, "single", "single"),
    (55.4, -15.1): ("low", 2, "single", "pair"),
    (55.4, -26.2): ("low", 3, "pair", "pair"),
    (77.7, -26.2): ("low", 2, "pair", "single"),
    (77.7, -13.55): ("low", 1, "none", "none"),
    (81.95, -13.55): ("low", 3, "single", "single"),
    (81.95, 13.55): ("low", 1, "none", "none"),
    (77.7, 13.55): ("low", 2, "single", "pair"),
    (77.7, 26.2): ("low", 3, "pair", "pair"),
    (55.4, 26.2): ("low", 2, "pair", "single"),
    (55.4, 15.1): ("low", 7, "single", "single"),
    (21.4, 15.1): ("wing", 5, "single", "pair"),
    (21.4, 46.3): ("wing", 7, "pair", "pair"),
}
CORNER = {"pair": ([0.55, 1.75], 2.3), "single": ([0.6], 1.2), "none": ([], 0.25)}


def layout(spec, L):
    """-> (pilaster centres, [(window centre, kind)]) along a segment of length L."""
    kind, nb, c0, c1 = spec
    if nb == "front":    # the south wing front beside the great arch (east side; mirrored on the west)
        return [0.35, 1.55, 6.55, 9.65, 10.45], [(4.05, "pair"), (8.1, "single")]
    p0, z0 = CORNER[c0]
    p1, z1 = CORNER[c1]
    pils = list(p0) + [L - x for x in p1]
    bw = (L - z0 - z1) / nb
    pils += [z0 + bw * k for k in range(1, nb)]
    wins = [(z0 + bw * (k + 0.5), "pair" if bw >= 3.9 else "single") for k in range(nb)]
    return sorted(pils), wins


def segments():
    """[(seg, spec, pilasters, windows, key)] for the whole outline (west half mirrored)."""
    out = []
    for i in range(len(OUTLINE) - 1):
        p0, p1 = OUTLINE[i], OUTLINE[i + 1]
        key = (round(p0[0], 2), round(p0[1], 2))
        mirrored = False
        if key not in SPEC_E:
            key = (round(-p1[0], 2), round(p1[1], 2))
            mirrored = True
        spec = SPEC_E.get(key)
        if spec is None:
            if abs(p0[1] - 46.3) < 0.01 and abs(p1[1] - 46.3) < 0.01:
                spec = SPEC_E[(21.4, 46.3)]
            else:
                raise RuntimeError(f"no facade spec for {p0}->{p1}")
        seg = seg_of(p0, p1)
        pils, wins = layout(spec, seg[3])
        if mirrored:
            pils = sorted(seg[3] - x for x in pils)
            wins = sorted((seg[3] - x, k) for x, k in wins)
        out.append((seg, spec, pils, wins, (p0, p1)))
    return out


def window_holes(x, kind, rows, fill="M_Glass"):
    w, g = WIN["w"], WIN["gap"]
    hs = []
    for h0, h1 in rows:
        if kind == "pair":
            hs += [(x - g / 2 - w, x - g / 2, h0, h1, fill), (x + g / 2, x + g / 2 + w, h0, h1, fill)]
        elif kind == "single":
            hs.append((x - 0.62, x + 0.62, h0, h1, fill))
    return hs


def door_hole(x, w=2.3, top=5.9):
    return [(x - w / 2, x + w / 2, FFL, top, "M_Door")]


def steps(B, u0, u1, v_face, direction, n=9, rise=0.2, tread=0.36, m="M_Granite", axis="v"):
    """A flight from grade up to the first floor against a face at v_face (or u_face), going outward along +/-axis."""
    for k in range(n):
        z1 = (k + 1) * rise
        outer = v_face + direction * (n - k) * tread
        a, b = min(outer, v_face), max(outer, v_face)
        if axis == "v":
            B.boxmm((u0, a, z1 - rise), (u1, b, z1), m)
        else:
            B.boxmm((a, u0, z1 - rise), (b, u1, z1), m)


def lamp_cluster(B, x, y, z):
    """Cast-iron lamp standard with five globes (the south steps' pedestals)."""
    B.cyl((x, y, z), 2.2, 0.09, "M_Iron", sides=8)
    B.cyl((x, y, z), 0.5, 0.2, "M_Iron", sides=8)
    for k in range(4):
        a = k * math.pi / 2 + math.pi / 4
        p = (x + 0.45 * math.cos(a), y + 0.45 * math.sin(a), z + 2.0)
        B.beam((x, y, z + 1.85), p, 0.06, 0.06, "M_Iron")
        B.ellipsoid((p[0], p[1], p[2] + 0.2), (0.2, 0.2, 0.2), "M_Light", segs=10, rings=6)
    B.ellipsoid((x, y, z + 2.45), (0.24, 0.24, 0.24), "M_Light", segs=10, rings=6)


def great_arch(B):
    """The south wing's centre: 11.6 m arch (springing 19.4 m, crown 25.2 m) over a recessed loggia with two columns,
    entrance doors and windows behind; archivolt and keystone; flight of steps with lamp pedestals."""
    r = 5.8
    zs = Z["ent0"]
    B.wall((-6.6, -37.0, Z["plinth"]), (1, 0, 0), (0, 0, 1), 13.2, Z["cornice1"] - Z["plinth"], 1.0, "M_Granite",
           holes=[(6.6, 2 * r, FFL - Z["plinth"], zs - Z["plinth"], True)], segs=18, edges=False)
    # archivolt: voussoir ring standing 0.25 m proud
    ri, ro, vf = r, r + 0.95, -37.25
    N = 18
    pts = [(math.cos(math.pi * k / N), math.sin(math.pi * k / N)) for k in range(N + 1)]
    for k in range(N):
        (c0, s0), (c1, s1) = pts[k], pts[k + 1]
        I0, I1 = Vector((ri * c0, vf, zs + ri * s0)), Vector((ri * c1, vf, zs + ri * s1))
        O0, O1 = Vector((ro * c0, vf, zs + ro * s0)), Vector((ro * c1, vf, zs + ro * s1))
        B.face([I0, O0, O1, I1], "M_GraniteRough")                                     # front (faces -v)
        B.face([O0, O0 + Vector((0, 0.25, 0)), O1 + Vector((0, 0.25, 0)), O1], "M_GraniteRough")   # extrados
        B.face([I0, I1, I1 + Vector((0, 0.25, 0)), I0 + Vector((0, 0.25, 0))], "M_GraniteRough")   # intrados
    B.boxmm((-0.55, -37.45, zs + r - 0.3), (0.55, -37.0, zs + r + 1.25), "M_Granite")    # keystone
    for s in (-1, 1):                                                                     # imposts
        B.boxmm((min(s * 5.35, s * 6.95), -37.3, zs - 0.6), (max(s * 5.35, s * 6.95), -37.0, zs), "M_Granite")
    # loggia: floor, side walls, barrel vault, back wall with doors and windows, glazed tympanum
    vb = -31.0
    B.face([(-r, -37.0, FFL), (r, -37.0, FFL), (r, vb, FFL), (-r, vb, FFL)], "M_Granite")
    B.face([(r, -36.0, FFL), (r, -36.0, zs), (r, vb, zs), (r, vb, FFL)], "M_Granite")         # east side, faces -u
    B.face([(-r, -36.0, FFL), (-r, vb, FFL), (-r, vb, zs), (-r, -36.0, zs)], "M_Granite")     # west side, faces +u
    vault = []
    for k in range(N + 1):
        a = math.pi * k / N
        vault.append([Vector((r * math.cos(a), v, zs + r * math.sin(a))) for v in (-36.0, vb)])
    B.grid(vault, "M_Granite", smooth=True)
    back = seg_of((-r, vb), (r, vb))
    holes = door_hole(1.6, 1.7, 5.9) + door_hole(5.8, 1.7, 5.9) + door_hole(10.0, 1.7, 5.9)
    for x in (1.9, 4.5, 7.1, 9.7):
        holes += [(x - 0.55, x + 0.55, 10.0, 13.5, "M_Glass"), (x - 0.55, x + 0.55, 15.0, 18.5, "M_Glass")]
    facade_band(B, back, FFL, zs, holes, "M_Granite")
    fan = [Vector((0, vb + 0.02, zs))] + [Vector((r * math.cos(math.pi * k / N), vb + 0.02, zs + r * math.sin(math.pi * k / N))) for k in range(N + 1)]
    for k in range(1, N + 1):
        B.face([fan[0], fan[k], fan[k + 1]], "M_Glass")
    for k in range(1, 6):                                                                  # tympanum mullions
        a = math.pi * k / 6
        B.beam((0, vb + 0.06, zs), (r * math.cos(a), vb + 0.06, zs + r * math.sin(a)), 0.18, 0.08, "M_Granite", up=(0, 1, 0))
    # screen: two columns carrying a lintel across the arch at the belt course, urns above
    for s in (-1, 1):
        x = 2.3 * s
        B.lathe([(0.55, FFL), (0.55, FFL + 0.35), (0.42, FFL + 0.45), (0.36, 7.0), (0.5, 7.25), (0.5, 7.55), (0.0, 7.55)], "M_Granite",
                segs=14, center=(x, -36.4, 0))
        B.lathe([(0.0, 8.4), (0.32, 8.4), (0.32, 8.55), (0.18, 8.7), (0.38, 9.1), (0.3, 9.45), (0.08, 9.6), (0.0, 9.6)], "M_Granite",
                segs=12, center=(x, -36.4, 0))
    B.boxmm((-r, -36.9, 7.55), (r, -35.9, 8.4), "M_Granite")
    # steps from the grade to the loggia floor, granite cheek walls and lamp pedestals
    steps(B, -6.9, 6.9, -37.0, -1)
    for s in (-1, 1):
        B.boxmm((min(s * 6.9, s * 8.2), -40.3, 0.0), (max(s * 6.9, s * 8.2), -37.0, 1.95), "M_Granite")
        B.boxmm((s * 7.55 - 0.55, -40.15, 1.95), (s * 7.55 + 0.55, -39.05, 2.25), "M_Granite")
        lamp_cluster(B, s * 7.55, -39.6, 2.25)


def frontispiece(B, sgn, half_w, depth, z0, z1, ped_apex, ped_half, medal_xs, round_windows):
    """Attic frontispiece above a wing's centre with its pediment (sgn -1 = south front at v -37, +1 = north at 46.3)."""
    v_face = -37.0 if sgn < 0 else 46.3
    vf, vb = v_face, v_face - sgn * depth
    fr = seg_of((-half_w, vf), (half_w, vf)) if sgn < 0 else seg_of((half_w, vf), (-half_w, vf))
    L = 2 * half_w
    facade_band(B, fr, z0, z1, [], "M_Granite")
    # side and back walls of the block (its roof is the pediment's); east side faces +X, west side -X
    lo_v, hi_v = min(vf, vb), max(vf, vb)
    facade_band(B, seg_of((half_w, lo_v), (half_w, hi_v)), z0, z1, [], "M_Granite")
    facade_band(B, seg_of((-half_w, hi_v), (-half_w, lo_v)), z0, z1, [], "M_Granite")
    bk = seg_of((half_w, vb), (-half_w, vb)) if sgn < 0 else seg_of((-half_w, vb), (half_w, vb))
    facade_band(B, bk, z0, z1, [], "M_Granite")
    for s in (-1, 1):   # corner pedestals
        obox(B, fr, L / 2 + s * (half_w - 1.0), 2.0, z0 + 2.2, z1 + 0.1, 0.3, "M_Granite")
    nrm = fr[2]
    for x in medal_xs:   # medallions (the six-nations seals in the south; round windows in the north)
        c = Vector((x, vf, (z0 + z1) / 2 + 0.2)) + nrm * 0.12
        ring = [c + Vector((0.6 * math.cos(2 * math.pi * k / 12) * (1 if sgn < 0 else -1), 0, 0.6 * math.sin(2 * math.pi * k / 12))) for k in range(12)]
        B.face(ring, "M_Glass" if round_windows else "M_Bronze")
    band(B, [(-half_w, vf), (half_w, vf)] if sgn < 0 else [(half_w, vf), (-half_w, vf)], z1 - 0.5, z1, 0.45, "M_Granite")
    # pediment: tympanum, raking cornices, roof slopes back to the block's rear
    zb, za = z1, ped_apex
    pf = vf
    t0, t1, t2 = Vector((-ped_half, pf, zb)), Vector((ped_half, pf, zb)), Vector((0, pf, za))
    B.face([t0, t1, t2] if sgn < 0 else [t1, t0, t2], "M_Granite")
    rb = vb - sgn * 0.5
    r0, r1, r2 = Vector((-ped_half, rb, zb)), Vector((ped_half, rb, zb)), Vector((0, rb, za))
    B.face([r1, r0, r2] if sgn < 0 else [r0, r1, r2], "M_Granite")
    for s in (-1, 1):
        e = t0 if s < 0 else t1
        er = r0 if s < 0 else r1
        q = [e, t2, r2, er]
        B.face(q if (s * sgn) > 0 else q[::-1], "M_RoofMetal")
    B.face([t0, r0, r1, t1] if sgn < 0 else [t1, r1, r0, t0], "M_Granite")
    # raking cornice bands standing proud of the tympanum
    out = Vector((0, sgn * 0.45, 0))
    for s in (-1, 1):
        e = t0 if s < 0 else t1
        a, b = e + out, t2 + out
        B.beam(a + Vector((0, 0, 0.25)), b + Vector((0, 0, 0.25)), 0.9, 0.55, "M_Granite", up=(0, 0, 1))
    B.beam(t0 + out + Vector((0, 0, 0.2)), t1 + out + Vector((0, 0, 0.2)), 0.9, 0.4, "M_Granite")
    oc = Vector((0, pf + sgn * 0.08, zb + (za - zb) * 0.42))
    disc = [oc + Vector((0.85 * math.cos(2 * math.pi * k / 16), 0, 0.85 * math.sin(2 * math.pi * k / 16))) for k in range(16)]
    B.face(disc if sgn < 0 else disc[::-1], "M_Bronze")


def north_porch(B):
    """The north entrance porch: three arches in front, one each side, a terrace roof with a balustrade; steps."""
    hw, v0, v1, top = 8.5, 46.3, 54.0, Z["belt1"]
    th = 0.8
    arches = [(hw - 3.4, 2.6, FFL, 5.6, True), (hw, 2.6, FFL, 5.6, True), (hw + 3.4, 2.6, FFL, 5.6, True)]
    B.wall((hw, v1, 0.0), (-1, 0, 0), (0, 0, 1), 2 * hw, top, th, "M_GraniteRough", holes=arches, segs=10, edges=True)
    for s in (-1, 1):
        o = (s * hw, v0, 0.0) if s > 0 else (s * hw, v1, 0.0)
        r = (0, 1, 0) if s > 0 else (0, -1, 0)
        B.wall(o, r, (0, 0, 1), v1 - v0, top, th, "M_GraniteRough", holes=[((v1 - v0) / 2, 3.0, FFL, 5.4, True)], segs=10, edges=True)
    B.face([(-hw + th, v0, FFL), (hw - th, v0, FFL), (hw - th, v1 - th, FFL), (-hw + th, v1 - th, FFL)], "M_Granite")
    B.face([(-hw + th, v0, 7.6), (-hw + th, v1 - th, 7.6), (hw - th, v1 - th, 7.6), (hw - th, v0, 7.6)], "M_Granite")
    B.boxmm((-hw - 0.3, v0, top), (hw + 0.3, v1 + 0.3, top + 0.45), "M_Granite")
    rail = [(hw + 0.3, v0), (hw + 0.3, v1 + 0.3), (-hw - 0.3, v1 + 0.3), (-hw - 0.3, v0)]
    band(B, rail, top + 0.45, top + 1.35, 0.0, "M_Granite", top=False, bottom=False, caps=False)
    band(B, rail, top + 0.45, top + 1.45, -0.35, "M_Granite", bottom=False)
    steps(B, -6.5, 6.5, v1, 1)
    for s in (-1, 1):
        B.boxmm((s * 7.4 - 0.5, v1 + 2.6, 0.0), (s * 7.4 + 0.5, v1 + 3.6, 2.2), "M_Granite")
        lamp_cluster(B, s * 7.4, v1 + 3.1, 2.2)


def inset_rings(rect, profile):
    """Rings of a rectangle (x0, y0, x1, y1) inset by d at height z for each (d, z): a hipped / mansard surface."""
    x0, y0, x1, y1 = rect
    P = []
    for corner in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x1, y1, -1, -1), (x0, y1, 1, -1)):
        cx, cy, sx, sy = corner
        P.append([Vector((cx + sx * d, cy + sy * d, z)) for d, z in profile])
    return P


def roofs(B):
    zeave, zridge = Z["parapet"] - 0.15, 27.1
    for s in (-1, 1):
        U = lambda u: s * u
        # long ridge roof over the hyphen, the end pavilion's centre and the vestibule (hip end at the outer face)
        e0, e1, ridge_end, hv = 17.4, 81.6, 68.4, 13.2
        pts_s = [(U(e0), -hv, zeave), (U(e1), -hv, zeave), (U(ridge_end), 0, zridge), (U(e0), 0, zridge)]
        pts_n = [(U(e0), 0, zridge), (U(ridge_end), 0, zridge), (U(e1), hv, zeave), (U(e0), hv, zeave)]
        hip = [(U(e1), -hv, zeave), (U(e1), hv, zeave), (U(ridge_end), 0, zridge)]
        gable = [(U(e0), -hv, zeave), (U(e0), 0, zridge), (U(e0), hv, zeave)]
        for poly in (pts_s, pts_n, hip, gable):
            B.face(poly if s > 0 else poly[::-1], "M_RoofMetal")
        for vv in (-1, 1):   # flat gutters between the hyphen parapet and the slopes
            q = [(U(e0), vv * hv, zeave), (U(55.4), vv * hv, zeave), (U(55.4), vv * 14.8, zeave), (U(e0), vv * 14.8, zeave)]
            B.face(q if (s * vv) < 0 else q[::-1], "M_RoofMetal")
        for vv in (-1, 1):   # the hyphen skylights, on each slope
            a0, a1, b0, b1 = 25.0, 47.0, 2.5, 10.5
            zf = lambda b: zridge - (zridge - zeave) * b / hv + 0.06
            q = [(U(a0), vv * b0, zf(b0)), (U(a1), vv * b0, zf(b0)), (U(a1), vv * b1, zf(b1)), (U(a0), vv * b1, zf(b1))]
            B.face(q if (s * vv) < 0 else q[::-1], "M_Glass")
        # corner blocks of the end pavilions: convex (bell) mansards with a low hipped deck and a finial
        for vv in (-1, 1):
            rect = (min(U(55.65), U(77.45)), min(vv * 13.6, vv * 25.95), max(U(55.65), U(77.45)), max(vv * 13.6, vv * 25.95))
            prof = [(3.3 * (1 - math.cos(math.pi / 2 * k / 6)), zeave + 3.8 * math.sin(math.pi / 2 * k / 6)) for k in range(7)]
            prof += [(4.6, zeave + 4.2), (5.8, zeave + 4.55)]
            B.grid(inset_rings(rect, prof), "M_RoofMetal", smooth=False, close_u=True)
            x0, y0, x1, y1 = rect
            d, zt = prof[-1]
            B.face([(x0 + d, y0 + d, zt), (x1 - d, y0 + d, zt), (x1 - d, y1 - d, zt), (x0 + d, y1 - d, zt)], "M_RoofMetal")
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            B.lathe([(0.0, zt), (0.45, zt), (0.45, zt + 0.6), (0.25, zt + 0.9), (0.35, zt + 1.6), (0.1, zt + 2.6), (0.0, zt + 3.9)], "M_DomeIron",
                    segs=10, center=(cx, cy, 0))
        # roof vent cupola (HABS sheet 76)
        cx, cy = U(70.5), -6.0
        B.boxmm((cx - 1.2, cy - 1.2, 25.6), (cx + 1.2, cy + 1.2, 30.6), "M_Granite")
        B.boxmm((cx - 1.45, cy - 1.45, 30.6), (cx + 1.45, cy + 1.45, 30.95), "M_Granite")
        for k in range(4):
            a = k * math.pi / 2
            B.card((cx + 1.21 * math.cos(a), cy + 1.21 * math.sin(a), 28.4), (math.cos(a), math.sin(a), 0), (0, 0, 1), 1.2, 2.6, "M_Glass")
        B.lathe([(1.35, 30.95), (1.3, 31.6), (1.05, 32.5), (0.6, 33.2), (0.2, 33.5), (0.12, 33.6), (0.04, 36.8), (0.0, 36.8)], "M_DomeIron",
                segs=16, center=(cx, cy, 0))
    # central block deck round the drum, then the north and south wings' hipped roofs with flat decks
    zw = Z["cornice1"] + 0.05
    B.face([(-17.0, -14.7, zw), (17.0, -14.7, zw), (17.0, 14.7, zw), (-17.0, 14.7, zw)], "M_RoofMetal")
    B.grid(inset_rings((-21.0, 14.7, 21.0, 45.9), [(0.0, zw), (9.0, 33.0)]), "M_RoofMetal", smooth=False, close_u=True)
    B.face([(-12.0, 23.7, 33.0), (12.0, 23.7, 33.0), (12.0, 36.9, 33.0), (-12.0, 36.9, 33.0)], "M_RoofMetal")
    B.grid(inset_rings((-17.0, -36.6, 17.0, -14.7), [(0.0, zw), (7.5, 32.0)]), "M_RoofMetal", smooth=False, close_u=True)
    B.face([(-9.5, -29.1, 32.0), (9.5, -29.1, 32.0), (9.5, -22.2, 32.0), (-9.5, -22.2, 32.0)], "M_RoofMetal")


def building():
    """The Capitol building itself (everything below the dome's drum)."""
    B = Builder()
    segs = segments()
    for seg, spec, pils, wins, ends in segs:
        kind = spec[0]
        L = seg[3]
        door_mid = ends[0] in ((81.95, -13.55), (-81.95, 13.55))
        north_face = abs(ends[0][1] - 46.3) < 0.01 and abs(ends[1][1] - 46.3) < 0.01
        h1, h2, ha = [], [], []
        for k, (x, wk) in enumerate(wins):
            ground = window_holes(x, wk, [WIN["f1"]])
            if door_mid and k == len(wins) // 2:
                ground = door_hole(x)
            if north_face and abs(x - L / 2) < 7.0:
                ground = door_hole(x, 2.0, 6.2)
            h1 += ground
            h2 += window_holes(x, wk, [WIN["f2"], WIN["f3"]])
            ha += window_holes(x, "pair" if wk == "pair" else "single", [WIN["att"]])
        facade_band(B, seg, Z["plinth"], Z["belt0"], h1, "M_GraniteRough")
        facade_band(B, seg, Z["dado1"], Z["ent0"], h2, "M_Granite")
        for x in pils:
            obox(B, seg, x, 1.45, Z["plinth"], Z["belt0"], 0.12, "M_GraniteRough")          # rock-faced pier
            obox(B, seg, x, 1.35, Z["belt1"], 9.8, 0.5, "M_Granite")                          # pedestal
            obox(B, seg, x, 1.0, 9.8, 18.8, 0.38, "M_Granite")                                # pilaster shaft
            obox(B, seg, x, 1.3, 18.8, Z["ent0"], 0.46, "M_Granite")                          # capital
        if kind == "wing":
            facade_band(B, seg, Z["ent1"], Z["attic1"], ha, "M_Granite")
            for x in pils:
                obox(B, seg, x, 0.85, Z["ent1"], Z["attic1"], 0.22, "M_Granite")
        else:   # balustraded parapet: sunk panels between the pedestals over the pilasters
            stops = [0.0] + list(pils) + [L]
            panels = [(a + 0.75, b - 0.75, 22.75, 23.95, "M_GraniteRough") for a, b in zip(stops, stops[1:]) if b - a > 2.2]
            facade_band(B, seg, Z["ent1"], Z["parapet"] - 0.2, panels, "M_Granite", rev=0.14)
            for x in pils:
                obox(B, seg, x, 1.0, Z["ent1"], Z["parapet"] - 0.2, 0.16, "M_Granite")
    # central block walls above the hyphen roofs (u = +-17.4) and the north wing's south face over them
    for p0, p1 in (((17.4, -15.1), (17.4, 15.1)), ((17.4, 15.1), (21.4, 15.1)), ((-21.4, 15.1), (-17.4, 15.1)), ((-17.4, 15.1), (-17.4, -15.1))):
        facade_band(B, seg_of(p0, p1), Z["ent1"], Z["attic1"], [], "M_Granite")
    # horizontal mouldings round the whole building
    band(B, CLOSED, 0.0, Z["plinth"], 0.3, "M_GraniteRough", closed=True, bottom=False)
    band(B, OUTLINE, Z["belt0"], 8.1, 0.25, "M_Granite")
    band(B, OUTLINE, 8.1, Z["belt1"], 0.4, "M_Granite")
    band(B, OUTLINE, Z["belt1"], Z["dado1"], 0.12, "M_Granite", bottom=False)
    band(B, OUTLINE, Z["band0"], Z["band1"], 0.1, "M_Granite")
    band(B, OUTLINE, Z["ent0"], 21.0, 0.42, "M_Granite")
    band(B, OUTLINE, 21.0, 21.6, 0.65, "M_Granite")
    band(B, OUTLINE, 21.6, Z["ent1"], 1.0, "M_Granite")
    # parapet caps of the low parts (hyphens and end pavilions): one run per side
    for run in (OUTLINE[2:14], mirror_pts(OUTLINE[2:14])):
        band(B, run, Z["parapet"] - 0.2, Z["parapet"] + 0.05, 0.2, "M_Granite")
        band(B, run, Z["parapet"] - 0.7, Z["parapet"] + 0.05, -0.3, "M_Granite", bottom=False, caps=False)
    # the wings' attic cornice and parapet (closed round the north wing, central block and south wing)
    band(B, UPPER, Z["attic1"], 26.8, 0.35, "M_Granite", closed=True)
    band(B, UPPER, 26.8, Z["cornice1"], 0.8, "M_Granite", closed=True)
    for run in UPPER_RUNS:   # the parapet stops at the two frontispieces
        band(B, run, Z["cornice1"], Z["parapet_w"], 0.0, "M_Granite", top=False, bottom=False, caps=False)
        band(B, run, Z["parapet_w"] - 0.2, Z["parapet_w"] + 0.05, 0.15, "M_Granite", bottom=False)
        band(B, run, Z["cornice1"] - 0.1, Z["parapet_w"] + 0.05, -0.3, "M_Granite", bottom=False)
    great_arch(B)
    frontispiece(B, -1, 10.5, 3.0, Z["cornice1"], 33.5, 37.6, 12.2, [-5.0, -3.0, -1.0, 1.0, 3.0, 5.0], False)
    frontispiece(B, 1, 9.2, 3.0, Z["cornice1"], 33.3, 36.7, 10.6, [-6.0, -4.0, -1.0, 1.0, 4.0, 6.0], True)
    north_porch(B)
    for s in (-1, 1):   # east and west entrance steps
        steps(B, -2.6, 2.6, s * 81.95, s, axis="u")
    roofs(B)
    ob = B.finish("LM_Capitol_Building")
    export("LM_Capitol_Building", [ob], {"origin": "rotunda centre at the south grade; front (south) faces Blender -Y",
                                         "ffl_m": FFL})


# ================================================================== 2. the dome (cast iron on a granite drum) and the Goddess
NB = 20                 # 20 bays all the way up: columns, ribs, windows, lucarnes (HABS sheets 42, 43)


def polar(r, th, z):
    """Angle th from the south (building -Y) toward the east (+X)."""
    return Vector((r * math.sin(th), -r * math.cos(th), z))


def flat_panel(B, r, th, z0, z1, w, m, arch=False, out=0.03, segs=6):
    """A window/panel outline lying on a cylinder of radius r (flat, tangent at th), standing out by `out`."""
    c = polar(r + out, th, 0)
    tx = Vector((math.cos(th), math.sin(th), 0))        # tangent toward increasing th (east of south)
    pts = [(-w / 2, z0), (w / 2, z0)]
    if arch:
        zc = z1 - w / 2
        pts += [(w / 2 * math.cos(math.pi * k / segs), zc + w / 2 * math.sin(math.pi * k / segs)) for k in range(segs + 1)]
    else:
        pts += [(w / 2, z1), (-w / 2, z1)]
    B.face([c + tx * x + UP * z for x, z in pts], m)


def frame_ring(B, r, th, z0, z1, w, m, arch=False, fw=0.18, out=0.12, segs=6):
    """Raised moulded frame round a window on the drum (a thin prism following the outline)."""
    c = polar(r, th, 0)
    n = Vector((-math.sin(th), math.cos(th), 0)) * -1    # outward normal
    tx = Vector((math.cos(th), math.sin(th), 0))
    def outline(w_, z0_, z1_):
        pts = [(-w_ / 2, z0_), (w_ / 2, z0_)]
        if arch:
            zc = z1 - w / 2
            pts += [(w_ / 2 * math.cos(math.pi * k / segs), zc + w_ / 2 * math.sin(math.pi * k / segs)) for k in range(segs + 1)]
        else:
            pts += [(w_ / 2, z1_), (-w_ / 2, z1_)]
        return pts
    inner = outline(w, z0, z1)
    outer = outline(w + 2 * fw, z0 - fw, z1 + fw)
    P = lambda p, d: c + tx * p[0] + UP * p[1] + n * d
    k = len(inner)
    for i in range(k):
        j = (i + 1) % k
        B.face([P(inner[i], out), P(outer[i], out), P(outer[j], out), P(inner[j], out)], m)
        B.face([P(outer[i], 0), P(outer[j], 0), P(outer[j], out), P(outer[i], out)], m)


def goddess(B, z0):
    """The Goddess of Liberty (1888 zinc, 1986 aluminium replica): 4.6 m to the top of the star she holds up in her
    left hand; sword in her right hand, facing south down Congress Avenue. Simplified draped figure."""
    m = "M_Statue"
    # robe: flared skirt to the waist, then torso
    B.lathe([(0.0, z0), (0.62, z0), (0.66, z0 + 0.25), (0.55, z0 + 1.0), (0.42, z0 + 1.7), (0.33, z0 + 2.1), (0.36, z0 + 2.55),
             (0.40, z0 + 2.85), (0.30, z0 + 3.05), (0.12, z0 + 3.15), (0.11, z0 + 3.25), (0.0, z0 + 3.25)], m, segs=14)
    B.ellipsoid((0, 0, z0 + 3.47), (0.2, 0.22, 0.26), m, segs=12, rings=8)                    # head
    B.ellipsoid((0, 0.02, z0 + 3.62), (0.24, 0.24, 0.12), m, segs=12, rings=4, half=True)     # crown / wreath
    B.ellipsoid((0.0, -0.05, z0 + 2.6), (0.42, 0.24, 0.2), m, segs=10, rings=6)               # shoulders, drapery
    # left arm (east) raised with the star; right arm (west) lowered holding the sword
    sh_l = Vector((0.36, 0.0, z0 + 2.75))
    hand_l = Vector((0.95, -0.05, z0 + 4.05))
    B.tube([sh_l, sh_l.lerp(hand_l, 0.5) + Vector((0.05, 0, 0.05)), hand_l], [0.11, 0.09, 0.07], m, sides=8, cap1=True)
    star_c = hand_l + Vector((0.05, 0, 0.32))
    pts = []
    for k in range(10):
        a = math.pi / 2 + k * math.pi / 5
        rr = 0.3 if k % 2 == 0 else 0.12
        pts.append(star_c + Vector((rr * math.cos(a), 0, rr * math.sin(a))))
    for s in (-1, 1):
        tip = star_c + Vector((0, s * 0.06, 0))
        for k in range(10):
            tri = [tip, pts[k], pts[(k + 1) % 10]]
            B.face(tri if s < 0 else tri[::-1], "M_Gold")
    sh_r = Vector((-0.36, 0.0, z0 + 2.75))
    hand_r = Vector((-0.5, -0.12, z0 + 1.75))
    B.tube([sh_r, Vector((-0.48, -0.06, z0 + 2.25)), hand_r], [0.11, 0.09, 0.07], m, sides=8, cap1=True)
    B.beam(hand_r + Vector((0, 0, 0.1)), hand_r + Vector((-0.05, -0.05, -1.25)), 0.08, 0.03, "M_Statue")


def dome():
    B = Builder()
    th = lambda k: 2 * math.pi * k / NB
    # lower drum (granite) from the central roof deck: rusticated wall, small windows, cornice
    B.lathe([(14.9, 27.3), (14.9, 28.2), (14.6, 28.4), (14.6, 38.9), (15.15, 39.0), (15.15, 39.6), (14.9, 39.6)], "M_Granite",
            segs=60, smooth=True)
    for k in range(NB):
        flat_panel(B, 14.6, th(k), 35.2, 37.6, 1.1, "M_Glass")
        flat_panel(B, 14.6, th(k), 30.4, 32.6, 1.1, "M_Glass")
    # peristyle stylobate with column pedestals
    B.lathe([(14.9, 39.6), (14.9, 41.8), (11.3, 41.8)], "M_Granite", segs=60)
    for k in range(NB):
        c = polar(13.8, th(k + 0.5), 0)
        B.box((c.x, c.y, 40.9), (1.25, 1.25, 1.8), "M_DomeIron", rot=Matrix.Rotation(th(k + 0.5), 3, "Z"))
    # inner drum wall with 20 tall arched windows and 20 oculi above, framed; pilasters behind the columns
    B.lathe([(11.3, 41.8), (11.3, 50.0)], "M_DomeIron", segs=60)
    for k in range(NB):
        flat_panel(B, 11.3, th(k), 42.6, 47.2, 1.5, "M_Glass", arch=True)
        frame_ring(B, 11.3, th(k), 42.6, 47.2, 1.5, "M_DomeIron", arch=True)
        oc = polar(11.34, th(k), 48.55)
        tx = Vector((math.cos(th(k)), math.sin(th(k)), 0))
        ring = [oc + tx * (0.62 * math.cos(2 * math.pi * j / 12)) + UP * (0.62 * math.sin(2 * math.pi * j / 12)) for j in range(12)]
        B.face(ring, "M_Glass")
        ring2 = [oc + (oc - polar(0, th(k), oc.z)).normalized() * 0.1 + tx * (0.85 * math.cos(2 * math.pi * j / 12)) + UP * (0.85 * math.sin(2 * math.pi * j / 12)) for j in range(12)]
        for j in range(12):
            B.face([ring[j], ring2[j], ring2[(j + 1) % 12], ring[(j + 1) % 12]], "M_DomeIron")
        c = polar(11.3, th(k + 0.5), 0)
        B.box((c.x, c.y, 45.9), (0.9, 0.5, 8.2), "M_DomeIron", rot=Matrix.Rotation(th(k + 0.5), 3, "Z"))
    # the 20 columns (Corinthian, cast iron)
    for k in range(NB):
        c = polar(13.8, th(k + 0.5), 0)
        B.lathe([(0.55, 41.8), (0.55, 42.05), (0.47, 42.2), (0.43, 42.35), (0.37, 49.2), (0.42, 49.3), (0.5, 49.75), (0.0, 49.75)],
                "M_DomeIron", segs=12, center=(c.x, c.y, 0))
        B.box((c.x, c.y, 49.88), (1.05, 1.05, 0.25), "M_DomeIron", rot=Matrix.Rotation(th(k + 0.5), 3, "Z"))
    # entablature ring and balcony (balustrade with pedestals over the columns)
    B.lathe([(11.3, 50.0), (14.45, 50.0), (14.45, 51.8), (15.2, 51.95), (15.2, 52.6), (14.45, 52.6), (14.45, 53.55), (14.62, 53.6),
             (14.62, 53.8), (14.15, 53.8), (14.15, 52.6), (11.6, 52.6)], "M_DomeIron", segs=60, smooth=False)
    for k in range(NB):
        flat_panel(B, 14.45, th(k), 52.75, 53.45, 3.2, "M_Glass", out=0.01)            # open balustrade, read as dark
        c = polar(14.35, th(k + 0.5), 0)
        B.box((c.x, c.y, 53.25), (0.75, 0.75, 1.3), "M_DomeIron", rot=Matrix.Rotation(th(k + 0.5), 3, "Z"))
    # upper drum (attic) with 20 arched windows between pilasters, cornice
    B.lathe([(11.6, 52.6), (11.6, 59.4), (12.15, 59.5), (12.15, 60.2), (11.95, 60.2)], "M_DomeIron", segs=60, smooth=False)
    for k in range(NB):
        flat_panel(B, 11.6, th(k), 55.0, 58.3, 1.25, "M_Glass", arch=True)
        frame_ring(B, 11.6, th(k), 55.0, 58.3, 1.25, "M_DomeIron", arch=True, fw=0.15, out=0.1)
        c = polar(11.6, th(k + 0.5), 0)
        B.box((c.x, c.y, 56.3), (0.7, 0.4, 5.6), "M_DomeIron", rot=Matrix.Rotation(th(k + 0.5), 3, "Z"))
    # dome base: sloped band with consoles
    B.lathe([(11.95, 60.2), (11.6, 60.8), (11.0, 62.0), (10.4, 63.5), (10.15, 64.0)], "M_DomeIron", segs=60)
    for k in range(NB):
        c = polar(11.0, th(k + 0.5), 0)
        B.box((c.x, c.y, 61.8), (0.45, 0.9, 2.3), "M_DomeIron", rot=Matrix.Rotation(th(k + 0.5), 3, "Z") @ Matrix.Rotation(math.radians(-22), 3, "X"))
    # the dome shell: half-ellipse a 10.1 m, b 10.5 m from z 64 to the lantern ring at 74 m; 20 ribs; 20 oval lucarnes
    prof = []
    for j in range(15):
        a = math.radians(90.0 * j / 14 * (math.asin(min(1.0, 10.0 / 10.5)) / (math.pi / 2)))
        prof.append((10.1 * math.cos(a), 64.0 + 10.5 * math.sin(a)))
    prof.append((0.0, prof[-1][1]))
    B.lathe(prof, "M_DomeIron", segs=80)
    for k in range(NB):
        t_ = th(k + 0.5)
        path, radii = [], []
        for j in range(1, 15):
            r_, z_ = prof[j - 1]
            path.append(polar(r_ + 0.12, t_, z_))
            radii.append(0.2)
        B.tube(path, radii, "M_DomeIron", sides=4, aspect=[(1.0, 0.8)] * len(path))
        # lucarne: oval frame + dark glass, on the shell
        r_l, z_l = 9.55, 67.6
        c = polar(r_l + 0.25, th(k), z_l)
        tx = Vector((math.cos(th(k)), math.sin(th(k)), 0))
        nrm = (c - Vector((0, 0, 64.0))).normalized()
        upv = nrm.cross(tx).normalized()
        if upv.z < 0:
            upv = -upv
        oval = [c + tx * (0.55 * math.cos(2 * math.pi * j / 12)) + upv * (1.0 * math.sin(2 * math.pi * j / 12)) for j in range(12)]
        oval2 = [c - nrm * 0.35 + tx * (0.85 * math.cos(2 * math.pi * j / 12)) + upv * (1.35 * math.sin(2 * math.pi * j / 12)) for j in range(12)]
        B.face(oval[::-1] if nrm.dot((oval[1] - oval[0]).cross(oval[2] - oval[1])) < 0 else oval, "M_Glass")
        for j in range(12):
            q = [oval[j], oval2[j], oval2[(j + 1) % 12], oval[(j + 1) % 12]]
            nq = (q[1] - q[0]).cross(q[2] - q[1])
            B.face(q if nq.dot((q[0] - c)) + nq.dot(nrm) * 0.3 > 0 else q[::-1], "M_DomeIron")
    # lantern: balustrade ring, base, colonnade (8 columns round a glazed core), cornice, upper stage, bell cap
    zl = prof[-1][1]
    B.lathe([(3.5, zl - 0.3), (3.6, zl), (3.6, zl + 1.0), (3.45, zl + 1.0), (3.45, zl + 0.1), (2.6, zl + 0.1)], "M_DomeIron", segs=40, smooth=False)
    B.lathe([(2.6, zl + 0.1), (2.6, 76.8), (2.9, 76.9), (2.9, 77.3), (1.65, 77.3)], "M_DomeIron", segs=32, smooth=False)
    B.lathe([(1.6, 77.3), (1.6, 81.0)], "M_Glass", segs=24)
    for k in range(8):
        a = 2 * math.pi * (k + 0.5) / 8
        c = polar(2.15, a, 0)
        B.lathe([(0.2, 77.3), (0.17, 80.75), (0.24, 81.0), (0.0, 81.0)], "M_DomeIron", segs=8, center=(c.x, c.y, 0))
    B.lathe([(2.0, 81.0), (2.6, 81.2), (2.6, 82.0), (1.85, 82.0), (1.85, 84.0), (1.95, 84.1), (1.7, 84.6), (1.15, 85.4), (0.7, 86.1),
             (0.45, 86.6), (0.5, 86.65), (0.5, 87.2), (0.0, 87.2)], "M_DomeIron", segs=32)
    for k in range(8):
        flat_panel(B, 1.85, 2 * math.pi * k / 8, 82.6, 83.5, 0.55, "M_Glass", out=0.02)
    goddess(B, 87.2)
    ob = B.finish("LM_Capitol_Dome")
    export("LM_Capitol_Dome", [ob], {"origin": "rotunda centre at the south grade (same as LM_Capitol_Building)",
                                     "top_of_star_m": 91.8})


# ================================================================== 3. the grounds (W. M. Johnson's 1888 layout, restored 1995-97)
# Laid out from HABS sheet 2 (site plan, 1:720) and photographs, fitted to Sky City's streets. Heights above the grounds'
# base (the placement script sets the base on the traced city ground): lawn 0.04, drives 0.05 with 0.17 m granite curbs,
# walks 0.06, the Great Walk and plazas 0.07.
ZL, ZD, ZW, ZG, ZC = 0.04, 0.05, 0.06, 0.07, 0.17
FEAT = []            # (kind, polygon) for the site map / keep-outs
KEEP = []            # keep-out polygons (local) for trees and props
LAMPS = []
PIERS = []           # gate piers (u, v, yaw_deg)


def catmull(points, closed=True, step=2.0):
    """Centripetal-free uniform Catmull-Rom through points, sampled about every `step` metres."""
    P = [Vector((p[0], p[1], 0)) for p in points]
    n = len(P)
    out = []
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = P[(i - 1) % n] if closed or i > 0 else P[0]
        p1, p2 = P[i], P[(i + 1) % n]
        p3 = P[(i + 2) % n] if closed or i + 2 < n else P[-1]
        L = (p2 - p1).length
        m = max(2, int(L / step))
        for k in range(m):
            t = k / m
            t2, t3 = t * t, t * t * t
            q = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            out.append((q.x, q.y))
    if not closed:
        out.append((P[-1].x, P[-1].y))
    return out


def offsets(pts, d, closed):
    return [(q.x, q.y) for q in miter_offsets([Vector((p[0], p[1], 0)) for p in pts], d, closed)]


def pl_dist(p, pts):
    return min(seg_dist(p, a, b) for a, b in zip(pts, pts[1:]))


def strip(B, pts, w, z, m, closed=False, z0=None, off=0.0, skip=None):
    """Ribbon of width w centred (offset by `off`) on a polyline, top at z; vertical sides down to z0 if given;
    segments whose midpoint skip(p) rejects are left out (drive mouths)."""
    Lp = offsets(pts, off - w / 2, closed)
    Rp = offsets(pts, off + w / 2, closed)
    n = len(pts)
    for i in (range(n) if closed else range(n - 1)):
        j = (i + 1) % n
        if skip and skip(((Lp[i][0] + Rp[j][0]) / 2, (Lp[i][1] + Rp[j][1]) / 2)):
            continue
        B.face([(*Lp[i], z), (*Rp[i], z), (*Rp[j], z), (*Lp[j], z)], m)
        if z0 is not None:
            B.face([(*Rp[i], z0), (*Rp[j], z0), (*Rp[j], z), (*Rp[i], z)], m)
            B.face([(*Lp[j], z0), (*Lp[i], z0), (*Lp[i], z), (*Lp[j], z)], m)
    return Lp, Rp


def road(B, pts, w, closed=False, kind="drive", skip_surface=None, skip_left=None, skip_right=None):
    """Asphalt drive with granite curbs either side (left/right of the direction of pts)."""
    strip(B, pts, w, ZD, "M_Asphalt", closed, skip=skip_surface)
    strip(B, pts, 0.3, ZC, "M_Curb", closed, z0=ZL - 0.02, off=-(w / 2 + 0.15), skip=skip_left or skip_surface)
    strip(B, pts, 0.3, ZC, "M_Curb", closed, z0=ZL - 0.02, off=w / 2 + 0.15, skip=skip_right or skip_surface)
    Lp = offsets(pts, -(w / 2 + 0.3), closed)
    Rp = offsets(pts, w / 2 + 0.3, closed)
    if closed:
        FEAT.append((kind, Rp)); FEAT.append(("lawn", Lp))
        KEEP.append(("ring", offsets(pts, w / 2 + 2.0, True), offsets(pts, -(w / 2 + 2.0), True)))
    else:
        FEAT.append((kind, Lp + Rp[::-1]))
        KEEP.append(offsets(pts, -(w / 2 + 2.0), False) + offsets(pts, w / 2 + 2.0, False)[::-1])


def walk(B, pts, w=3.0, m="M_Concrete", z=ZW, curbs=False, keep=1.5):
    strip(B, pts, w, z, m, z0=ZL - 0.02)
    if curbs:
        strip(B, pts, 0.25, z + 0.08, "M_Curb", z0=ZL - 0.02, off=-(w / 2 + 0.125))
        strip(B, pts, 0.25, z + 0.08, "M_Curb", z0=ZL - 0.02, off=w / 2 + 0.125)
    FEAT.append(("walk", offsets(pts, -w / 2, False) + offsets(pts, w / 2, False)[::-1]))
    KEEP.append(offsets(pts, -(w / 2 + keep), False) + offsets(pts, w / 2 + keep, False)[::-1])


def disc(B, c, r, z, m, n=28, rim=None, rim_h=0.1, keep=1.5):
    pts = [(c[0] + r * math.cos(2 * math.pi * k / n), c[1] + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    B.face([(*p, z) for p in pts], m)
    if rim:
        strip(B, pts, 0.3, z + rim_h, rim, closed=True, z0=ZL - 0.02, off=0.15)
    FEAT.append(("plaza", pts))
    KEEP.append([(c[0] + (r + keep) * math.cos(2 * math.pi * k / 16), c[1] + (r + keep) * math.sin(2 * math.pi * k / 16)) for k in range(16)])
    return pts


def clip_poly(poly, x0, x1, y0, y1):
    def clip(P, inside, inter):
        out = []
        for i in range(len(P)):
            a, b = P[i - 1], P[i]
            ia, ib = inside(a), inside(b)
            if ib:
                if not ia:
                    out.append(inter(a, b))
                out.append(b)
            elif ia:
                out.append(inter(a, b))
        return out
    P = poly
    for axis, val, keep_lo in ((0, x0, False), (0, x1, True), (1, y0, False), (1, y1, True)):
        if not P:
            return P
        inside = (lambda p, a=axis, v=val, k=keep_lo: p[a] <= v if k else p[a] >= v)
        def inter(a, b, ax=axis, v=val):
            t = (v - a[ax]) / (b[ax] - a[ax])
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        P = clip(P, inside, inter)
    return P


def great_walk(B, v0, v1, hw=4.5, s=1.05):
    """The Great Walk: black-and-white diamond paving between granite curbs, from the south gate to the drive."""
    r2 = math.sqrt(0.5)
    amin = int(math.floor((-hw + v0) * r2 / s)) - 2
    amax = int(math.ceil((hw + v1) * r2 / s)) + 2
    bmin = int(math.floor((v0 - hw) * r2 / s)) - 2
    bmax = int(math.ceil((v1 + hw) * r2 / s)) + 2
    for i in range(amin, amax):
        for j in range(bmin, bmax):
            corners = []
            for a, b in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)):
                A, Bv = a * s, b * s
                corners.append(((A - Bv) * r2, (A + Bv) * r2))
            if max(c[1] for c in corners) < v0 or min(c[1] for c in corners) > v1:
                continue
            if max(c[0] for c in corners) < -hw or min(c[0] for c in corners) > hw:
                continue
            P = clip_poly(corners, -hw, hw, v0, v1)
            if len(P) >= 3:
                B.face([(*p, ZG) for p in P], "M_PavingLight" if (i + j) % 2 == 0 else "M_PavingDark")
    for sgn in (-1, 1):
        strip(B, [(sgn * (hw + 0.15), v0), (sgn * (hw + 0.15), v1)], 0.3, ZG + 0.08, "M_Curb", z0=ZL - 0.02)
    FEAT.append(("great_walk", [(-hw, v0), (hw, v0), (hw, v1), (-hw, v1)]))
    KEEP.append([(-hw - 0.8, v0 - 1), (hw + 0.8, v0 - 1), (hw + 0.8, v1), (-hw - 0.8, v1)])


def monument(B, kind, c, yaw=0.0):
    """Monuments as simple forms: granite pedestals with bronze figures/shafts (no inscriptions)."""
    x, y = c
    rot = Matrix.Rotation(math.radians(yaw), 3, "Z")
    def bx(cx, cy, z0, sx, sy, sz, m):
        p = rot @ Vector((cx, cy, 0))
        B.box((x + p.x, y + p.y, z0 + sz / 2), (sx, sy, sz), m, rot=rot)
    if kind == "shaft":          # tall granite shaft with a figure (e.g. Heroes of the Alamo, 1891)
        bx(0, 0, ZG, 4.4, 4.4, 0.6, "M_Granite"); bx(0, 0, ZG + 0.6, 3.6, 3.6, 0.6, "M_Granite")
        bx(0, 0, ZG + 1.2, 2.5, 2.5, 2.6, "M_GranitePolished"); bx(0, 0, ZG + 3.8, 2.9, 2.9, 0.4, "M_Granite")
        B.lathe([(0.75, ZG + 4.2), (0.62, ZG + 10.2), (0.8, ZG + 10.4), (0.8, ZG + 10.8), (0.0, ZG + 10.8)], "M_Granite", segs=8, smooth=False, center=(x, y, 0))
        figure(B, x, y, ZG + 10.8, 2.2, yaw)
    elif kind == "column":       # granite column with a figure on top
        bx(0, 0, ZG, 5.0, 5.0, 0.7, "M_Granite"); bx(0, 0, ZG + 0.7, 3.4, 3.4, 2.4, "M_GranitePolished")
        bx(0, 0, ZG + 3.1, 2.4, 2.4, 1.2, "M_Granite")
        B.lathe([(0.7, ZG + 4.3), (0.58, ZG + 11.0), (0.85, ZG + 11.4), (0.0, ZG + 11.4)], "M_Granite", segs=12, center=(x, y, 0))
        figure(B, x, y, ZG + 11.4, 2.0, yaw)
    elif kind == "rider":        # equestrian group on a pedestal (Terry's Texas Rangers, 1907; the Texas Cowboy)
        bx(0, 0, ZG, 3.6, 5.6, 0.5, "M_Granite"); bx(0, 0, ZG + 0.5, 2.8, 4.8, 2.6, "M_GranitePolished")
        bx(0, 0, ZG + 3.1, 3.2, 5.2, 0.3, "M_Granite")
        z = ZG + 3.4
        bx(0, 0, z + 1.0, 0.75, 2.1, 0.9, "M_Bronze")                              # horse body
        for dx, dy in ((-0.25, -0.75), (0.25, -0.75), (-0.25, 0.75), (0.25, 0.75)):
            bx(dx, dy, z, 0.16, 0.16, 1.05, "M_Bronze")                            # legs
        B.beam(tuple(Vector((x, y, 0)) + rot @ Vector((0, -1.0, z + 1.7))), tuple(Vector((x, y, 0)) + rot @ Vector((0, -1.55, z + 2.35))), 0.35, 0.45, "M_Bronze")
        figure(B, x, y, z + 1.9, 1.5, yaw)
    elif kind == "figure":       # single figure on a pedestal (Volunteer Firemen, 1896/1905; Spanish-American War)
        bx(0, 0, ZG, 3.0, 3.0, 0.5, "M_Granite"); bx(0, 0, ZG + 0.5, 2.1, 2.1, 2.8, "M_GranitePolished")
        bx(0, 0, ZG + 3.3, 2.4, 2.4, 0.3, "M_Granite")
        figure(B, x, y, ZG + 3.6, 2.2, yaw)
    elif kind == "fountain":     # oval granite basin with a cast-iron spray fountain (1905 type)
        n = 24
        ring = [(x + 4.0 * math.cos(2 * math.pi * k / n), y + 2.6 * math.sin(2 * math.pi * k / n)) for k in range(n)]
        strip(B, ring, 0.45, 0.55, "M_Granite", closed=True, z0=ZL - 0.02, off=0.22)
        B.face([(*p, 0.38) for p in ring], "M_Water")
        B.lathe([(0.0, 0.38), (0.55, 0.38), (0.4, 0.8), (0.18, 1.1), (0.15, 1.6), (1.2, 1.75), (1.25, 1.95), (0.2, 2.0), (0.12, 2.6),
                 (0.6, 2.7), (0.62, 2.85), (0.1, 2.9), (0.06, 3.4), (0.0, 3.5)], "M_Iron", segs=14, center=(x, y, 0))


def figure(B, x, y, z0, h, yaw=0.0):
    """A standing bronze figure, h metres tall (simplified)."""
    s = h / 2.0
    B.lathe([(0.0, z0), (0.32 * s, z0), (0.3 * s, z0 + 0.9 * s), (0.22 * s, z0 + 1.0 * s), (0.27 * s, z0 + 1.45 * s), (0.3 * s, z0 + 1.6 * s),
             (0.12 * s, z0 + 1.68 * s), (0.0, z0 + 1.68 * s)], "M_Bronze", segs=10, center=(x, y, 0))
    B.ellipsoid((x, y, z0 + 1.82 * s), (0.12 * s, 0.13 * s, 0.16 * s), "M_Bronze", segs=8, rings=6)


def boundary_runs(outline, gaps, segs_keep):
    """Split the fence line into runs, leaving gaps (centre (u, v), half width) for gates."""
    pts = []
    for a, b in zip(outline, outline[1:] + outline[:1]):
        L = math.dist(a, b)
        n = max(1, int(L / 1.0))
        for k in range(n):
            pts.append((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
    keep = [segs_keep(p) and all(math.dist(p, g) > hw for g, hw in gaps) for p in pts]
    runs, cur = [], []
    for p, k in zip(pts + pts[:1], keep + keep[:1]):
        if k:
            cur.append(p)
        elif cur:
            if len(cur) > 3:
                runs.append(cur)
            cur = []
    if len(cur) > 3:
        runs.append(cur)
    # merge a run that wraps round the start, then simplify each run to its corners
    out = []
    for r in runs:
        simp = [r[0]]
        for i in range(1, len(r) - 1):
            if seg_dist(r[i], simp[-1], r[i + 1]) > 0.05:
                simp.append(r[i])
        simp.append(r[-1])
        out.append(simp)
    return out


def cross_line(poly, u=None, v=None):
    """Where the vertical line u = const (or horizontal v = const) crosses a polygon: sorted list of the other coordinate."""
    hits = []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        if u is not None and (a[0] - u) * (b[0] - u) <= 0 and a[0] != b[0]:
            hits.append(a[1] + (b[1] - a[1]) * (u - a[0]) / (b[0] - a[0]))
        if v is not None and (a[1] - v) * (b[1] - v) <= 0 and a[1] != b[1]:
            hits.append(a[0] + (b[0] - a[0]) * (v - a[1]) / (b[1] - a[1]))
    return sorted(hits)


def grounds():
    B = Builder()
    FEAT.clear(); KEEP.clear(); LAMPS.clear(); PIERS.clear()
    outline = SITE["outline"]
    # lawn over the whole grounds
    B.face([(*p, ZL) for p in outline], "M_Lawn")
    # granite-curbed apron round the building and the south entrance plaza
    apron = offset_poly(CLOSED, 3.5)
    B.face([(*p, ZW + 0.005) for p in apron], "M_Concrete")
    strip(B, apron, 0.3, ZW + 0.12, "M_Curb", closed=True, z0=ZL - 0.02, off=0.15)
    FEAT.append(("plaza", apron))
    KEEP.append(offset_poly(CLOSED, 5.5))
    plaza = [(-16.0, -47.4), (16.0, -47.4), (16.0, -38.0), (-16.0, -38.0)]
    B.face([(*p, ZG) for p in plaza], "M_PavingLight")
    north_pl = [(-11.0, 53.0), (11.0, 53.0), (11.0, 64.4), (-11.0, 64.4)]
    B.face([(*p, ZG) for p in north_pl], "M_PavingLight")
    FEAT.append(("plaza", plaza)); FEAT.append(("plaza", north_pl))
    # the oval drive round the building (asphalt between granite curbs), counter-clockwise from the south axis
    ctrl_e = [(0, -51.0), (20, -50.0), (40, -45.0), (60, -41.0), (78, -38.5), (92, -31.0), (101, -16.0), (103.5, 0.0), (101, 16.0), (92, 31.0),
              (78, 38.5), (60, 40.5), (42, 42.0), (31.5, 46.5), (28.0, 56.0), (22.0, 64.5), (11.0, 68.0)]
    ctrl = ctrl_e + [(0.0, 69.0)] + [(-u, v) for u, v in reversed(ctrl_e[1:])]
    loop = catmull(ctrl, closed=True, step=2.5)
    LAYOUT["loop_drive_local"] = [[round(a, 2), round(b, 2)] for a, b in loop]
    v_gate = cross_line(outline, u=0.0)[0] + 0.35
    v_n = cross_line(outline, u=0.0)[-1] - 0.4
    court_c, court_r = (0.0, 128.0), 14.5
    sides = {sgn: catmull([(sgn * 38.0, -44.0), (sgn * 33.5, -70.0), (sgn * 29.6, -112.0), (sgn * 25.5, -160.0), (sgn * 21.0, -196.0),
                           (sgn * 20.5, v_gate)], closed=False, step=2.0) for sgn in (-1, 1)}
    norths = {sgn: catmull([(sgn * 11.0, 66.0), (sgn * 11.0, 100.0), (sgn * 19.5, 116.0), (sgn * 21.0, 128.0), (sgn * 19.5, 140.0), (sgn * 11.0, 156.0),
                            (sgn * 11.0, 200.0), (sgn * 11.0, v_n)], closed=False, step=2.0) for sgn in (-1, 1)}
    connectors = list(sides.values()) + list(norths.values())
    on_loop = lambda p: pl_dist(p, loop + loop[:1]) < 3.75
    road(B, loop, 7.0, closed=True, kind="drive", skip_right=lambda p: any(pl_dist(p, c) < 3.9 for c in connectors))
    for c in connectors:
        road(B, c, 6.5, kind="drive", skip_surface=on_loop)
    # the Great Walk from the south gate to the drive; side drives to 11th Street outside the two lawn panels
    v_top = -54.8
    great_walk(B, v_gate, v_top)
    gate_gaps = [((0.0, v_gate), 6.6)]
    for sgn in (-1, 1):
        ue = sides[sgn][-1][0]
        PIERS.extend([(ue - 4.4, v_gate + 0.6, 0.0), (ue + 4.4, v_gate + 0.6, 0.0)])
        gate_gaps.append(((ue, v_gate), 4.3))
        # monument plazas and the fountains on the lawn panels, with spurs to the Great Walk
        for vv, kind in ((-86.0, "shaft" if sgn > 0 else "rider"), (-170.0, "column" if sgn > 0 else "figure")):
            c = (sgn * 14.0, vv)
            disc(B, c, 4.6, ZG, "M_PavingLight", rim="M_Curb")
            walk(B, [(sgn * 4.8, vv), (sgn * 9.6, vv)] if sgn > 0 else [(sgn * 9.6, vv), (sgn * 4.8, vv)], w=2.6, m="M_PavingLight", z=ZG)
            monument(B, kind, c, 0.0 if kind != "rider" else 90.0 * sgn)
        cf = (sgn * 14.0, -128.0)
        disc(B, cf, 5.4, ZW, "M_Concrete")
        monument(B, "fountain", cf)
        walk(B, [(sgn * 4.8, -128.0), (sgn * 8.8, -128.0)] if sgn > 0 else [(sgn * 8.8, -128.0), (sgn * 4.8, -128.0)], w=2.6, m="M_PavingLight", z=ZG)
    PIERS.extend([(-5.6, v_gate + 0.6, 0.0), (5.6, v_gate + 0.6, 0.0), (-7.4, v_gate + 0.6, 0.0), (7.4, v_gate + 0.6, 0.0)])
    # diagonal walks from the corners of 11th Street, east and west walks from Colorado and Brazos
    sw = catmull([(-145.0, v_gate + 2.0), (-128.0, -150.0), (-108.0, -92.0), (-92.0, -42.0)], closed=False, step=3.0)
    se = catmull([(147.0, v_gate + 3.0), (129.0, -150.0), (109.0, -92.0), (93.0, -42.0)], closed=False, step=3.0)
    walk(B, sw); walk(B, se)
    xw = cross_line(outline, v=0.0)[0] + 0.3
    xe = cross_line(outline, v=0.0)[-1] - 0.3
    walk(B, [(xw, 0.0), (-107.5, 0.0)]); walk(B, [(xe, 0.0), (107.5, 0.0)])
    # monuments in the side lawns (simple forms)
    for c, kind, yaw in (((-50.0, -92.0), "rider", 30.0), ((-128.0, -40.0), "figure", 60.0), ((128.0, -48.0), "column", -60.0)):
        disc(B, c, 4.0, ZG, "M_PavingLight", rim="M_Curb")
        monument(B, kind, c, yaw)
    walk(B, catmull([(-50.0, -96.0), (-36.0, -100.0), (-27.5, -104.0)], closed=False), w=2.4)
    walk(B, [(-124.0, -40.0), (-112.0, -40.0)], w=2.4)
    walk(B, [(124.0, -48.0), (113.0, -48.0)], w=2.4)
    # north grounds (the 1993 Capitol Extension above ground): twin drives round the open-air rotunda court, a central
    # walk, skylight strips; kept clear of the elevated expressway's piers
    walk(B, [(0.0, 72.0), (0.0, court_c[1] - court_r)], w=5.0, m="M_PavingLight", z=ZG, curbs=True)
    walk(B, [(0.0, court_c[1] + court_r), (0.0, v_n)], w=4.0, m="M_PavingLight", z=ZG, curbs=True)
    disc(B, court_c, court_r, ZG, "M_PavingLight", n=40)
    ring = [(court_c[0] + (court_r + 0.4) * math.cos(2 * math.pi * k / 40), court_c[1] + (court_r + 0.4) * math.sin(2 * math.pi * k / 40)) for k in range(40)]
    strip(B, ring, 0.8, 1.05, "M_Granite", closed=True, z0=ZL - 0.02)
    star = []
    for k in range(10):
        a = math.pi / 2 + k * math.pi / 5
        rr = 6.0 if k % 2 == 0 else 2.4
        star.append((court_c[0] + rr * math.cos(a), court_c[1] + rr * math.sin(a)))
    B.face([(*p, ZG + 0.01) for p in star], "M_GranitePolished")
    for v0, v1 in ((78.0, 108.0), (150.0, 162.0), (186.0, 230.0)):
        for sgn in (-1, 1):
            r_ = [(sgn * 3.2, v0), (sgn * 6.2, v0), (sgn * 6.2, v1), (sgn * 3.2, v1)]
            if sgn < 0:
                r_ = r_[::-1]
            B.boxmm((min(p[0] for p in r_) - 0.2, v0 - 0.2, ZL - 0.02), (max(p[0] for p in r_) + 0.2, v1 + 0.2, 0.42), "M_Curb")
            B.face([(p[0], p[1], 0.43) for p in r_], "M_Glass")
    # the cast-iron fence on a granite curb along 11th Street, Colorado and Brazos (south of the north grounds)
    fence_line = offset_poly(outline, -0.6)
    corner_gates = [((-145.0, v_gate + 1.0), 2.4), ((147.0, v_gate + 1.0), 2.4)]
    side_gates = [((xw + 0.6, 0.0), 2.2), ((xe - 0.6, 0.0), 2.2)]
    runs = boundary_runs(fence_line, gate_gaps + corner_gates + side_gates, lambda p: p[1] < 52.0)
    LAYOUT["fence_runs_local"] = [[[round(a, 2), round(b, 2)] for a, b in r] for r in runs]
    for r in runs:
        KEEP.append(offsets(r, -0.9, False) + offsets(r, 0.9, False)[::-1])
    for c, w in corner_gates:
        PIERS.extend([(c[0] - w, c[1], 0.0), (c[0] + w, c[1], 0.0)])
    PIERS.extend([(xw + 0.6, 2.4, 90.0), (xw + 0.6, -2.4, 90.0), (xe - 0.6, 2.4, 90.0), (xe - 0.6, -2.4, 90.0)])
    for p in PIERS:
        KEEP.append([(p[0] - 1.2, p[1] - 1.2), (p[0] + 1.2, p[1] - 1.2), (p[0] + 1.2, p[1] + 1.2), (p[0] - 1.2, p[1] + 1.2)])
    # benches along the Great Walk (cast-iron ends, slatted seat) and planting beds along the building's long fronts
    v = v_gate + 18.5
    while v < v_top - 6:
        for sgn in (-1, 1):
            if all(abs(v - vv) > 4.5 for vv in (-86.0, -128.0, -170.0)):
                x = sgn * 5.35
                for dv in (-0.85, 0.85):
                    B.boxmm((x - 0.3, v + dv - 0.04, ZG), (x + 0.3, v + dv + 0.04, ZG + 0.8), "M_Iron")
                B.boxmm((x - 0.25, v - 0.95, ZG + 0.42), (x + 0.25, v + 0.95, ZG + 0.47), "M_Door")
                bx = x + sgn * 0.25
                B.boxmm((bx - 0.03, v - 0.95, ZG + 0.5), (bx + 0.03, v + 0.95, ZG + 0.85), "M_Door")
        v += 21.0
    for sgn in (-1, 1):
        for v0, v1, u0, u1 in ((-20.4, -19.0, 21.3, 51.5), (19.0, 20.4, 25.3, 51.5)):
            B.boxmm((min(sgn * u0, sgn * u1), v0, ZL), (max(sgn * u0, sgn * u1), v1, ZL + 0.75), "M_Planting")
    # lamps: both sides of the Great Walk, round the oval drive, along the north walk
    v = v_gate + 8.0
    while v < v_top - 3:
        LAMPS.extend([(-5.3, v), (5.3, v)])
        v += 21.0
    acc = 0.0
    lo = offsets(loop, 4.6, True)
    for i in range(1, len(lo)):
        acc += math.dist(lo[i - 1], lo[i])
        if acc > 30.0:
            acc = 0.0
            LAMPS.append(lo[i])
    for v in range(80, int(v_n) - 5, 24):
        if abs(v - 171) > 6 and not (court_c[1] - court_r - 2 < v < court_c[1] + court_r + 2):
            LAMPS.extend([(-3.0, float(v)), (3.0, float(v))])
    piers = SITE["piers"]
    LAMPS[:] = [p for p in LAMPS if in_poly(p, outline) and min(math.dist(p, q) for q in piers) > 4.0]
    ob = B.finish("LM_Capitol_Grounds", weld=False)
    export("LM_Capitol_Grounds", [ob], {"origin": "rotunda centre; z = 0 is the grounds' base (the city ground)"})
    # keep-outs where the city's park trees and street props must go: building, drives, walks, plazas, fence, piers
    polys = [k for k in KEEP if isinstance(k, list)]
    rings = [k for k in KEEP if isinstance(k, tuple)]
    R2 = lambda P: [[round(a, 2), round(b, 2)] for a, b in P]
    LAYOUT["keepouts_local"] = [R2(k) for k in polys]
    LAYOUT["keepout_rings_local"] = [[R2(k[1]), R2(k[2])] for k in rings]
    LAYOUT["keepouts_plan"] = [R2([to_plan(a, b) for a, b in k]) for k in polys]
    LAYOUT["keepout_rings_plan"] = [[R2([to_plan(a, b) for a, b in k[1]]), R2([to_plan(a, b) for a, b in k[2]])] for k in rings]
    LAYOUT["grounds_outline_plan"] = R2([to_plan(a, b) for a, b in outline])
    LAYOUT["gate_piers_local"] = [[round(p[0], 2), round(p[1], 2), p[2]] for p in PIERS]
    LAYOUT["lamps_local"] = R2(LAMPS)
    LAYOUT["features_local"] = [{"kind": k, "poly": R2(p)} for k, p in FEAT]
    print("grounds:", len(runs), "fence runs,", len(PIERS), "gate piers,", len(LAMPS), "lamps,", len(LAYOUT["keepouts_local"]), "keep-outs")


# ================================================================== 4. kit: fence module, gate pier, lamp post
def fence10():
    """10 m of the 1890 fence (Mast, Foos & Co.): pickets every 0.2 m capped with gilded five-pointed stars, two rails,
    heavier posts every 2.5 m, on a granite curb. Runs from y = 0 to y = -10 (the landmark kit's linear-module rule)."""
    B = Builder()
    B.boxmm((-0.24, -10.0, 0.0), (0.24, 0.0, 0.36), "M_Curb")
    for z in (0.5, 1.22):
        B.boxmm((-0.025, -10.0, z - 0.025), (0.025, 0.0, z + 0.025), "M_Iron")
    for k in range(50):
        y = -0.1 - 0.2 * k
        B.boxmm((-0.014, y - 0.014, 0.36), (0.014, y + 0.014, 1.36), "M_Iron")
        c = Vector((0.0, y, 1.45))
        pts = []
        for j in range(10):
            a = math.pi / 2 + j * math.pi / 5
            rr = 0.075 if j % 2 == 0 else 0.03
            pts.append(c + Vector((0, rr * math.cos(a), rr * math.sin(a))))
        for s in (-1, 1):
            tip = c + Vector((s * 0.012, 0, 0))
            for j in range(10):
                tri = [tip, pts[j], pts[(j + 1) % 10]]
                B.face(tri if s > 0 else tri[::-1], "M_Gold")
    for k in range(4):
        y = -2.5 * k
        B.boxmm((-0.05, y - 0.05 if k else -0.1, 0.36), (0.05, y + 0.05 if k else 0.0, 1.5), "M_Iron")
        B.ellipsoid((0.0, y if k else -0.05, 1.58), (0.07, 0.07, 0.08), "M_Iron", segs=8, rings=4)
    ob = B.finish("LM_Capitol_Fence10")
    export("LM_Capitol_Fence10", [ob], {"origin": "foot of the run's start; runs 10 m along -Y; scale Y to fit a run"})


def gate_pier():
    B = Builder()
    B.box((0, 0, 0.2), (1.3, 1.3, 0.4), "M_Granite")
    B.box((0, 0, 1.45), (1.0, 1.0, 2.1), "M_GraniteRough")
    B.box((0, 0, 2.65), (1.3, 1.3, 0.3), "M_Granite")
    B.pyramid((0, 0, 2.8), 0.55, 0.55, 0.45, "M_Granite")
    ob = B.finish("LM_Capitol_GatePier")
    export("LM_Capitol_GatePier", [ob], {"origin": "foot centre"})


def lamp():
    B = Builder()
    B.lathe([(0.26, 0.0), (0.26, 0.15), (0.2, 0.3), (0.14, 0.85), (0.1, 0.95), (0.075, 1.05), (0.06, 3.55), (0.11, 3.65), (0.16, 3.8),
             (0.0, 3.8)], "M_Iron", segs=10)
    B.ellipsoid((0, 0, 4.08), (0.27, 0.27, 0.3), "M_Light", segs=12, rings=8)
    B.lathe([(0.0, 4.36), (0.1, 4.36), (0.03, 4.55), (0.0, 4.6)], "M_Iron", segs=8)
    ob = B.finish("LM_Capitol_Lamp")
    export("LM_Capitol_Lamp", [ob], {"origin": "foot"})


def kit():
    fence10(); reset(); gate_pier(); reset(); lamp()


# ================================================================== preview renderer (after blender_landmarks.py's)
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


def _scene_setup(ground=True):
    sc = bpy.context.scene
    if ground:
        bpy.ops.mesh.primitive_plane_add(size=3000, location=(0, 0, -0.03))
        bpy.context.object.data.materials.append(_simple_mat("PV_Ground", (0.30, 0.30, 0.29), 0.85))
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
    ramp.color_ramp.elements[0].color = (0.80, 0.86, 0.93, 1)
    ramp.color_ramp.elements[1].position = 0.6
    ramp.color_ramp.elements[1].color = (0.22, 0.42, 0.78, 1)
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(42), 0, math.radians(-30)))
    sun = bpy.context.object
    sun.data.energy = 3.8
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


def _render(path, samples=40):
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


def _fence_preview():
    """Fence modules, gate piers and lamps from capitol.json placed as in Unreal (preview only)."""
    data = json.load(open(BASE + "/capitol.json"))
    lay = data.get("layout", {})
    objs = []
    for run in lay.get("fence_runs_local", []):
        for a, b in zip(run, run[1:]):
            L = math.dist(a, b)
            n = max(1, round(L / 10.0))
            yaw = math.atan2(b[1] - a[1], b[0] - a[0]) - math.pi / 2 + math.pi   # module runs along its local -Y
            for k in range(n):
                p = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n, 0.0)
                objs += _import("LM_Capitol_Fence10", p, (0, 0, yaw), (1, L / n / 10.0, 1))
    for g in lay.get("gate_piers_local", []):
        objs += _import("LM_Capitol_GatePier", (g[0], g[1], 0.0), (0, 0, math.radians(g[2])))
    for lp in lay.get("lamps_local", []):
        objs += _import("LM_Capitol_Lamp", (lp[0], lp[1], 0.0))
    return objs


PREVIEWS = {
    # name: (camera location, look-at, lens, ortho scale, with fence/lamps)
    "south_ortho": ((0, -400, 46), (0, 0, 46), 35, 190.0, False),
    "south": ((0, -175, 6.0), (0, 0, 38.0), 30, None, True),
    "oblique": ((-150, -150, 55), (0, -5, 25), 32, None, True),
    "aerial": ((60, -330, 240), (0, -60, 0), 28, None, True),
    "dome": ((25, -70, 45), (0, 0, 66), 50, None, False),
    "north": ((60, 160, 30), (0, 20, 25), 32, None, True),
    "walk": ((0, -205, 1.7), (0, -40, 12), 32, None, True),
    "top": ((0, 0, 900), (0, 0.01, 0), 35, 520.0, True),
}


def render_previews(names):
    for name in (names or list(PREVIEWS)):
        loc, look, lens, ortho, extras = PREVIEWS[name]
        reset()
        _scene_setup(ground=not os.path.exists(f"{OUT}/LM_Capitol_Grounds.glb") or name == "south_ortho")
        objs = []
        for a in ("LM_Capitol_Building", "LM_Capitol_Dome") + (() if name == "south_ortho" else ("LM_Capitol_Grounds",)):
            if os.path.exists(f"{OUT}/{a}.glb"):
                objs += _import(a)
        if extras and os.path.exists(BASE + "/capitol.json"):
            objs += _fence_preview()
        if name in ("south", "walk"):
            _person((3.0, -60.0, 0.0))
        res = (1900, 1000) if name == "south_ortho" else ((1200, 1200) if name == "top" else (1600, 1000))
        _cam(loc, look, lens, res, ortho)
        _render(f"{BASE}/preview_{name}.png", samples=24 if name == "top" else 40)



def write_json():
    path = BASE + "/capitol.json"
    data = {}
    if os.path.exists(path):
        try:
            data = json.load(open(path))
        except Exception:
            data = {}
    assets = data.get("assets", {})
    assets.update(META)
    data["assets"] = dict(sorted(assets.items()))
    lay = data.get("layout", {})
    lay.update(LAYOUT)
    data["layout"] = lay
    data["conventions"] = {
        "units": "metres in Blender/GLB; Unreal imports as centimetres",
        "frame": "Blender +X = building east, +Y = building north, origin = rotunda centre at the south grade; "
                 "plan (x east, y north) = origin + R(phi) (u, v); Unreal X = plan y * 100, Y = plan x * 100",
        "fence": "LM_Capitol_Fence10 runs 10 m along its local -Y from its origin; place modules along each run, "
                 "scaling Y to fit; gate piers stand at their origin; lamps at their foot",
        "generator": "Scripts/landmarks/blender_capitol.py",
    }
    json.dump(data, open(path, "w"), indent=1)
    print("wrote", path)
    # the same keep-outs in landmark_zones.json's format, for roadnet.py's prop pass (streets-junctions)
    zones = []
    for k, poly in enumerate(lay.get("keepouts_plan", [])):
        zones.append({"name": f"capitol_keepout_{k}", "clear": ["props"], "poly": poly})
    for k, (outer, inner) in enumerate(lay.get("keepout_rings_plan", [])):     # ring (the oval drive) as quads
        n = len(outer)
        for i in range(n):
            j = (i + 1) % n
            zones.append({"name": f"capitol_ring_{k}_{i}", "clear": ["props"], "poly": [outer[i], outer[j], inner[j], inner[i]]})
    zp = BASE + "/capitol_zones.json"
    json.dump({"frame": "plan metres, x east, y north (Saved/Mashup/plan_v3.json); Unreal X = y*100, Y = x*100",
               "why": "Texas Capitol building, drives, walks, plazas, monuments, fence line: no street props or park trees inside",
               "used_by": "Scripts/roads/place_capitol_ue.py stage trees; Scripts/roads/roadnet.py could read it like landmark_zones.json",
               "generator": "Scripts/landmarks/blender_capitol.py", "zones": zones}, open(zp, "w"))
    print("wrote", zp, len(zones), "zones")


JOBS = {"site": site, "building": building, "dome": dome, "grounds": grounds, "kit": kit}

if __name__ == "__main__":
    if ARGS and ARGS[0] == "--render":
        render_previews(ARGS[1:])
    else:
        for job, fn in JOBS.items():
            if ARGS and job not in ARGS and job != "site":
                continue
            if job != "site":
                reset()
            fn()
        write_json()
    print("ALL DONE")
