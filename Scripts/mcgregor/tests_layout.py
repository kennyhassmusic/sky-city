"""McGregor test stands, round 2 (mcgregor-tests agent, 20 Oct 2026): the flame trenches / exhaust bays that were missing,
the concrete blast aprons and the dark exhaust scorch on them, caliche pads under the 2025 stands, the test hardware on
the stands (engines, an upper stage, the display booster at the hangar circle) and the sites of the timed engine tests
(SkysterEngineTests C++ actor, placed by engine_tests_ue.py).

Called by site_layout.py (build(ground, put, feat) -> site_features.json["tests"]; kit placements go into its normal
"placements" list, so site_ue.py `place` puts them in the maps as Site_<mesh>). The site-specific meshes (trench liners,
aprons, pads, scorch skins) are written as explicit triangle lists to Saved/McGregor/tests_meshes.json; blender_site_kit.py
(job `tests`) exports them as SourceArt/McGregor/site/SK_T_*.glb, Blender frame = (east, north, up) metres relative to each
mesh's origin with absolute heights, placed with bearing 180 and z = 0 (the same convention as SK_FSTrench).

Measured on (all in SourceArt/Reference/McGregor/tests, listed in sources.txt there):
  Esri World Imagery = Vantor WorldView-3 2025-04-13, 0.31 m (stands, trenches, tanks, pads; crops with a site-metre grid)
  Apple Maps / Google satellite, winter 2025-26 (the concrete blast aprons west of the 2025 stands and south of the
  first-stage trench, the soot streaks on the Raptor South apron, the display booster's shadow at the hangar circle)
  NSF / Gary Blair flyover Aug 2025 (both 2025 stands: black vertical test cells over west-running trenches, tall tanks)
  USDA NAIP 2022 (the in-game ground photo: the 2021 vertical stand's trench sits where Esri shows it, ~20 m west of OSM)
Depths from shadow lengths (Apple winter sun ~38 deg: ~11 m at the head of the Raptor South trench; Esri morning sun:
~6-7 m at the head of the 2021 vertical stand's trench); the floors ramp up to the apron at the mouth.
Frame: metres, x east, y north (site_research.json / mcgregor_data.json); bearings 0 = north, 90 = east.
Run: python3 -I Scripts/mcgregor/site_layout.py   (this module is imported from there)
"""
import json, math, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
MESH_OUT = ROOT / "Saved/McGregor/tests_meshes.json"

# ------------------------------------------------------------------ trenches (rim polygon: head left/right, mouth left/right)
# "left" = on the left looking from the head (under the engine) toward the mouth.
TRENCHES = {
    # Raptor North (2025): vertical single-engine cell at the east end, triangular trench opening WEST onto a concrete
    # apron; Esri 2025-04-13: mouth x 822 (y 625..651), narrow head under the cell at x ~899
    "RN": {"name": "Raptor North trench", "head": [(899.0, 633.0), (899.0, 640.0)], "mouth": [(822.0, 625.0), (822.0, 651.0)],
           "depth": 10.0, "feature": "raptor_north_stand"},
    # Raptor South (2025): its twin, 425 m south; mouth x 800 (y 201..228), head x ~878
    "RS": {"name": "Raptor South trench", "head": [(878.0, 208.0), (878.0, 216.0)], "mouth": [(800.0, 201.0), (800.0, 228.0)],
           "depth": 10.0, "feature": "raptor_south_stand"},
    # vertical Raptor stand (2021): east wall straight N-S at x -107, west wall flaring; opens SOUTH (NAIP 2022 + Esri)
    "RV": {"name": "Vertical engine stand trench (2021)", "head": [(-107.0, 332.0), (-117.0, 332.0)], "mouth": [(-107.0, 248.0), (-152.0, 248.0)],
           "depth": 7.0, "feature": "raptor_vertical_2021"},
    # second-stage stand: trench opening SOUTH (Esri 2025; the 2018-20 DEM only holds a 3.5 m dip here)
    "S2": {"name": "Second-stage stand trench", "head": [(1000.0, -710.0), (988.0, -710.0)], "mouth": [(1020.0, -760.0), (984.0, -760.0)],
           "depth": 8.0, "feature": "stage2_stand"},
}
RIM_UP = 0.25          # rim / apron top above the terrain (the pads sit at +0.15)
FLANGE = 3.0           # concrete lip outside the rim, hides the cut terrain's edge

# ------------------------------------------------------------------ concrete blast aprons (Apple / Google 2025-26)
APRONS = {
    "RN": {"ring": [(714.0, 608.0), (822.0, 608.0), (822.0, 683.0), (714.0, 683.0)], "mouth": (822.0, 638.0), "bearing": 270.0, "mouth_w": 26.0},
    "RS": {"ring": [(691.0, 188.0), (800.0, 188.0), (800.0, 253.0), (691.0, 253.0)], "mouth": (800.0, 214.5), "bearing": 270.0, "mouth_w": 27.0},
    # first-stage stand: the new apron south of the trench mouth (y -656), NW corner cut off
    "FS": {"ring": [(-182.0, -657.0), (-112.0, -657.0), (-112.0, -781.0), (-222.0, -781.0), (-222.0, -713.0), (-186.0, -664.0)],
           "mouth": (-147.0, -657.0), "bearing": 180.0, "mouth_w": 70.0},
}
# ------------------------------------------------------------------ caliche pads under the 2025 stands (Esri 2025)
PADS = {
    "RN": [(803.0, 588.0), (985.0, 588.0), (985.0, 713.0), (803.0, 713.0)],
    "RS": [(790.0, 165.0), (975.0, 165.0), (975.0, 265.0), (790.0, 265.0)],
}
# ------------------------------------------------------------------ burnt ground beyond the aprons / at the other trench mouths
# (centre, bearing of the exhaust, length along it, width, how strong 0-1)
SCORCH = [
    ("RN_far", (700.0, 640.0), 270.0, 34.0, 60.0, 0.75),
    ("RS_far", (677.0, 217.0), 270.0, 34.0, 56.0, 0.85),
    ("RV_mouth", (-128.0, 232.0), 180.0, 40.0, 56.0, 0.9),
    ("S2_mouth", (1002.0, -778.0), 180.0, 38.0, 46.0, 0.9),
    ("FS_far", (-165.0, -800.0), 180.0, 34.0, 100.0, 0.6),
    ("Merlin_fan", (600.0, -1318.0), 100.0, 100.0, 62.0, 0.8),     # the big dark fan east of the Merlin stands (Esri)
    ("RH_fan_w", (-112.0, 520.0), 350.0, 70.0, 26.0, 0.55),        # horizontal Raptor bays' exhaust fans (north)
    ("RH_fan_e", (-40.0, 515.0), 35.0, 70.0, 26.0, 0.55),
    ("Tripod", (-30.0, -563.0), 225.0, 26.0, 22.0, 0.8),
]


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def unit(v):
    L = math.hypot(*v) or 1.0
    return (v[0] / L, v[1] / L)


def fwd(b):
    r = math.radians(b)
    return math.sin(r), math.cos(r)


def inside(p, ring):
    x, y, c = p[0], p[1], False
    for i in range(len(ring)):
        (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % len(ring)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def dseg(p, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    L2 = (bx - ax) ** 2 + (by - ay) ** 2 or 1e-9
    t = max(0, min(1, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / L2))
    return math.dist(p, (ax + t * (bx - ax), ay + t * (by - ay)))


def ccw(ring):
    a = sum(ring[k][0] * ring[(k + 1) % len(ring)][1] - ring[(k + 1) % len(ring)][0] * ring[k][1] for k in range(len(ring)))
    return list(ring) if a > 0 else list(ring)[::-1]


def clip(subject, clipper):
    """Sutherland-Hodgman: subject polygon clipped by a convex counter-clockwise clipper."""
    out = list(subject)
    for i in range(len(clipper)):
        a, b = clipper[i], clipper[(i + 1) % len(clipper)]
        inp, out = out, []
        if not inp:
            break

        def side(p):
            return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        for j in range(len(inp)):
            p, q = inp[j], inp[(j + 1) % len(inp)]
            sp, sq = side(p), side(q)
            if sp >= 0:
                out.append(p)
            if (sp >= 0) != (sq >= 0):
                t = sp / (sp - sq)
                out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out


class Part:
    """One material's triangles: shared vertices (east, north, up relative to the mesh origin), per-vertex UVs."""

    def __init__(self, mat, smooth=False):
        self.mat, self.smooth, self.v, self.uv, self.t, self.idx = mat, smooth, [], [], [], {}

    def vert(self, p, uv, share=True):
        key = (round(p[0], 3), round(p[1], 3), round(p[2], 3)) if share else None
        if key is not None and key in self.idx:
            return self.idx[key]
        self.v.append([round(p[0], 3), round(p[1], 3), round(p[2], 3)])
        self.uv.append([round(uv[0], 4), round(uv[1], 4)])
        if key is not None:
            self.idx[key] = len(self.v) - 1
        return len(self.v) - 1

    def poly(self, pts, uvs, want=(0, 0, 1), share=True):
        """A planar convex polygon fanned into triangles, wound so its normal points along `want`."""
        n = [0.0, 0.0, 0.0]
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            n[0] += (a[1] - b[1]) * (a[2] + b[2])
            n[1] += (a[2] - b[2]) * (a[0] + b[0])
            n[2] += (a[0] - b[0]) * (a[1] + b[1])
        if n[0] * want[0] + n[1] * want[1] + n[2] * want[2] < 0:
            pts, uvs = pts[::-1], uvs[::-1]
        ids = [self.vert(p, u, share) for p, u in zip(pts, uvs)]
        for k in range(1, len(ids) - 1):
            if len({ids[0], ids[k], ids[k + 1]}) == 3:
                self.t.append([ids[0], ids[k], ids[k + 1]])

    def dump(self):
        return {"mat": self.mat, "smooth": self.smooth, "verts": self.v, "uvs": self.uv, "tris": self.t}


# ------------------------------------------------------------------ mesh builders
def trench_mesh(T, ground, origin):
    """Concrete-lined trench: vertical walls from the rim down to a floor that holds the full depth under the engine
    (a curved deflector fillet against the head wall), then ramps up to the apron at the mouth; a concrete lip outside
    the rim on both sides and behind the head. Returns parts and the rim polygon (the terrain cut)."""
    (L0, R0), (L1, R1) = T["head"], T["mouth"]
    D = T["depth"]
    m0, m1 = lerp(L0, R0, 0.5), lerp(L1, R1, 0.5)
    A = math.dist(m0, m1)
    ax = unit((m1[0] - m0[0], m1[1] - m0[1]))
    r = min(0.45 * D, 0.2 * A)
    sump = max(r + 4.0, 0.14 * A)
    ox, oy = origin

    def P(xy, z):
        return (xy[0] - ox, xy[1] - oy, z)
    # stations along the axis (distance s from the head): fine across the fillet, then every ~3.5 m
    ss = [r * (1 - math.cos(math.pi / 2 * k / 6)) for k in range(7)] + [sump]
    n = max(4, int((A - sump) / 3.5))
    ss += [sump + (A - sump) * k / n for k in range(1, n + 1)]
    ss = sorted(set(round(s, 3) for s in ss))
    rim = lambda xy: ground(*xy) + RIM_UP
    zrim0 = (rim(L0) + rim(R0)) / 2
    zf = zrim0 - D
    st = []
    for s in ss:
        t = s / A
        L, R = lerp(L0, L1, t), lerp(R0, R1, t)
        zr = (rim(L) + rim(R)) / 2
        if s <= r:
            z = zf + r - math.sqrt(max(0.0, r * r - (r - s) ** 2))
        elif s <= sump:
            z = zf
        else:
            k = (s - sump) / (A - sump)
            z = zf + (zr - zf) * (k ** 1.15)          # floor ramps up to the rim / apron level at the mouth
        st.append((s, L, R, z, rim(L), rim(R)))
    soot, wall, lip = Part("M_TestSootDark"), Part("M_SiteConcreteDark"), Part("M_SiteConcrete")
    W = lambda a, b: math.dist(a, b)
    # floor (flat across), walls (vertical), soot below 1.6 m under the rim
    for (s0, La, Ra, za, la, ra), (s1, Lb, Rb, zb, lb, rb) in zip(st, st[1:]):
        wa, wb = W(La, Ra), W(Lb, Rb)
        soot.poly([P(La, za), P(Ra, za), P(Rb, zb), P(Lb, zb)], [(0, s0 / 4), (wa / 4, s0 / 4), (wb / 4, s1 / 4), (0, s1 / 4)], (0, 0, 1))
        for (Pa, Pb, ztop_a, ztop_b, side) in ((La, Lb, la, lb, "L"), (Ra, Rb, ra, rb, "R")):
            # inward normal: from the wall toward the axis
            mid = lerp(lerp(La, Ra, 0.5), lerp(Lb, Rb, 0.5), 0.5)
            wm = lerp(Pa, Pb, 0.5)
            inn = unit((mid[0] - wm[0], mid[1] - wm[1]))
            want = (inn[0], inn[1], 0.0)
            cut_a, cut_b = max(za, ztop_a - 1.6), max(zb, ztop_b - 1.6)
            soot.poly([P(Pa, za), P(Pb, zb), P(Pb, cut_b), P(Pa, cut_a)], [(s0 / 4, za / 4), (s1 / 4, zb / 4), (s1 / 4, cut_b / 4), (s0 / 4, cut_a / 4)], want, share=False)
            if ztop_a - cut_a > 0.01 or ztop_b - cut_b > 0.01:
                wall.poly([P(Pa, cut_a), P(Pb, cut_b), P(Pb, ztop_b), P(Pa, ztop_a)], [(s0 / 4, cut_a / 4), (s1 / 4, cut_b / 4), (s1 / 4, ztop_b / 4), (s0 / 4, ztop_a / 4)], want, share=False)
    # head wall down to the top of the fillet
    s0, La, Ra, za, la, ra = st[0]
    soot.poly([P(La, za), P(Ra, za), P(Ra, ra), P(La, la)], [(0, za / 4), (W(La, Ra) / 4, za / 4), (W(La, Ra) / 4, ra / 4), (0, la / 4)], (ax[0], ax[1], 0.0), share=False)
    # lip: outside both walls and behind the head, its outer edge dipping into the ground
    def lip_strip(pts_in, out_dir_fn):
        for a, b in zip(pts_in, pts_in[1:]):
            (pa, za_), (pb, zb_) = a, b
            oa, ob = out_dir_fn(pa), out_dir_fn(pb)
            qa = (pa[0] + oa[0] * FLANGE, pa[1] + oa[1] * FLANGE)
            qb = (pb[0] + ob[0] * FLANGE, pb[1] + ob[1] * FLANGE)
            lip.poly([P(pa, za_), P(pb, zb_), P(qb, ground(*qb) + 0.04), P(qa, ground(*qa) + 0.04)],
                     [(pa[0] / 4, pa[1] / 4), (pb[0] / 4, pb[1] / 4), (qb[0] / 4, qb[1] / 4), (qa[0] / 4, qa[1] / 4)], (0, 0, 1))
    # outward directions perpendicular to each side wall line
    def outward(P0, P1, other):
        d = unit((P1[0] - P0[0], P1[1] - P0[1]))
        nrm = (-d[1], d[0])
        o = lerp(other[0], other[1], 0.5)
        mp = lerp(P0, P1, 0.5)
        if nrm[0] * (o[0] - mp[0]) + nrm[1] * (o[1] - mp[1]) > 0:
            nrm = (-nrm[0], -nrm[1])
        return nrm
    oL = outward(L0, L1, (R0, R1))
    oR = outward(R0, R1, (L0, L1))
    back = (-ax[0], -ax[1])
    lip_strip([(L, la) for (_, L, _, _, la, _) in st], lambda p: oL)
    lip_strip([(R, ra) for (_, _, R, _, _, ra) in st], lambda p: oR)
    lip_strip([(L0, st[0][4]), (R0, st[0][5])], lambda p: back)
    for C, o in ((L0, oL), (R0, oR)):          # corner wedges between the side lips and the back lip
        zc = rim(C)
        q1 = (C[0] + o[0] * FLANGE, C[1] + o[1] * FLANGE)
        q2 = (C[0] + back[0] * FLANGE, C[1] + back[1] * FLANGE)
        q3 = (C[0] + (o[0] + back[0]) * FLANGE * 0.707, C[1] + (o[1] + back[1]) * FLANGE * 0.707)
        for a, b in ((q1, q3), (q3, q2)):
            lip.poly([P(C, zc), P(a, ground(*a) + 0.04), P(b, ground(*b) + 0.04)], [(C[0] / 4, C[1] / 4), (a[0] / 4, a[1] / 4), (b[0] / 4, b[1] / 4)], (0, 0, 1))
    # yellow rail posts along both rims every ~6 m (cheap boxes)
    rail = Part("M_SiteYellow")
    for (s, L, R, z, la, ra) in st[::2]:
        for Q, o, zt in ((L, oL, la), (R, oR, ra)):
            c = (Q[0] + o[0] * 0.5, Q[1] + o[1] * 0.5)
            box(rail, P(c, zt), 0.12, 0.12, 1.1, ax)
    parts = [soot, wall, lip, rail]
    return parts, [L0, R0, R1, L1], {"floor_z_head": round(zf, 2), "rim_z_head": round(zrim0, 2), "fillet_r": round(r, 2), "length": round(A, 1)}


def box(part, c, sx, sy, h, ax=(0.0, 1.0)):
    """Upright box standing on c = (x, y, z), sides sx across / sy along the axis ax."""
    ux, uy = ax
    vx, vy = uy, -ux
    pts = []
    for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        pts.append((c[0] + vx * a * sx / 2 + ux * b * sy / 2, c[1] + vy * a * sx / 2 + uy * b * sy / 2))
    z0, z1 = c[2], c[2] + h
    part.poly([(x, y, z1) for x, y in pts], [(0, 0), (1, 0), (1, 1), (0, 1)], (0, 0, 1), share=False)
    for i in range(4):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % 4]
        mx, my = (x0 + x1) / 2 - c[0], (y0 + y1) / 2 - c[1]
        part.poly([(x0, y0, z0), (x1, y1, z0), (x1, y1, z1), (x0, y0, z1)], [(0, 0), (1, 0), (1, 1), (0, 1)], (mx, my, 0.0), share=False)


def drape(part, ring, ground, origin, zoff, step=2.0, uvf=None, holes=(), hole_pad=1.0):
    """Terrain-following surface over a convex ring: grid cells clipped to the ring (exact edges), skipping cells whose
    centre lies in a hole (expanded by hole_pad), each vertex at ground + zoff."""
    ring = ccw(ring)
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    ox, oy = origin
    uvf = uvf or (lambda x, y: (x / 4.0, y / 4.0))
    x = math.floor(min(xs) / step) * step
    while x < max(xs):
        y = math.floor(min(ys) / step) * step
        while y < max(ys):
            cell = clip([(x, y), (x + step, y), (x + step, y + step), (x, y + step)], ring)
            if len(cell) >= 3:
                cx, cy = sum(p[0] for p in cell) / len(cell), sum(p[1] for p in cell) / len(cell)
                if not any(inside((cx, cy), h) or min(dseg((cx, cy), h[k], h[(k + 1) % len(h)]) for k in range(len(h))) < hole_pad for h in holes):
                    part.poly([(p[0] - ox, p[1] - oy, ground(*p) + zoff) for p in cell], [uvf(*p) for p in cell], (0, 0, 1))
            y += step
        x += step


def skirt(part, ring, ground, origin, zoff, width=1.4, drop=0.45, step=2.0):
    """A bevel all round a draped slab: from its edge (ground + zoff) out and down into the ground, so no hard edge."""
    ring = ccw(ring)
    ox, oy = origin
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        d = unit((b[0] - a[0], b[1] - a[1]))
        o = (d[1], -d[0])                                  # outward for a counter-clockwise ring
        n = max(1, int(math.dist(a, b) / step))
        for k in range(n):
            p, q = lerp(a, b, k / n), lerp(a, b, (k + 1) / n)
            po, qo = (p[0] + o[0] * width, p[1] + o[1] * width), (q[0] + o[0] * width, q[1] + o[1] * width)
            part.poly([(p[0] - ox, p[1] - oy, ground(*p) + zoff), (q[0] - ox, q[1] - oy, ground(*q) + zoff),
                       (qo[0] - ox, qo[1] - oy, ground(*qo) + zoff - drop), (po[0] - ox, po[1] - oy, ground(*po) + zoff - drop)],
                      [(p[0] / 4, p[1] / 4), (q[0] / 4, q[1] / 4), (qo[0] / 4, qo[1] / 4), (po[0] / 4, po[1] / 4)], (0, 0, 1))


def axis_uv(mouth, bearing, mouth_w, length):
    """Apron UVs for the soot texture: U across the exhaust (0.5 = the trench axis, 1 unit = 2.5 trench widths), V along
    it (0 at the trench mouth, 1 at `length` metres)."""
    fx, fy = fwd(bearing)
    rx, ry = fy, -fx

    def f(x, y):
        dx, dy = x - mouth[0], y - mouth[1]
        return (0.5 + (dx * rx + dy * ry) / (mouth_w * 2.5), (dx * fx + dy * fy) / length)
    return f


# ------------------------------------------------------------------ build
def build(ground, put, feat):
    meshes, cuts, out = {}, [], {}
    # trenches
    tinfo = {}
    for tid, T in TRENCHES.items():
        origin = tuple(round(c, 1) for c in lerp(*T["head"], 0.5))
        parts, rim, info = trench_mesh(T, ground, origin)
        name = f"SK_T_Trench{tid}"
        meshes[name] = {"origin": list(origin), "parts": [p.dump() for p in parts if p.t]}
        put(name, origin, 180.0, z=0.0, collide="complex", feature=T["feature"])
        cuts.append({"id": tid, "poly": [[round(p[0], 2), round(p[1], 2)] for p in rim]})
        tinfo[tid] = dict(info, rim=[[round(p[0], 2), round(p[1], 2)] for p in rim], depth=T["depth"])
        feat(f"trench_{tid}", T["name"], ["tests: Esri 2025-04-13", "tests: Apple / Google 2025-26", "tests: NSF Aug 2025 flyover"], origin,
             [round(info["length"]), round(max(math.dist(*T["mouth"]), math.dist(*T["head"]))), T["depth"]],
             "concrete-lined pit cut into the terrain: full depth under the engine with a curved deflector, floor ramping up to the mouth, sooty floor and lower walls",
             name, "none (newer than OSM) / OSM flame_trench ring (offset ~20 m in the 2021 stand's case)", "medium (rim from imagery, depth from shadows)")
    # aprons: concrete with soot streaks fanning out from the trench mouth
    for aid, Ap in APRONS.items():
        ring = Ap["ring"]
        origin = tuple(round(c, 1) for c in Ap["mouth"])
        length = max(math.dist(Ap["mouth"], p) for p in ring)
        top = Part("M_TestApron", smooth=True)
        drape(top, ring, ground, origin, RIM_UP, 2.0, axis_uv(Ap["mouth"], Ap["bearing"], Ap["mouth_w"], length))
        edge = Part("M_SiteConcrete", smooth=True)
        skirt(edge, ring, ground, origin, RIM_UP)
        name = f"SK_T_Apron{aid}"
        meshes[name] = {"origin": list(origin), "parts": [top.dump(), edge.dump()]}
        put(name, origin, 180.0, z=0.0, collide="complex", feature=f"apron_{aid}")
        feat(f"apron_{aid}", f"Blast apron ({aid})", ["tests: Apple / Google 2025-26"], origin, [round(length), 0, 0],
             "flat concrete slab where the trench opens, dark exhaust streaks fanning out from the mouth", name, "none", "medium (newer than Esri 2025-04)")
    # caliche pads (holes where the trenches are)
    for pid, ring in PADS.items():
        holes = [tinfo[pid]["rim"]] if pid in tinfo else []
        origin = tuple(round(sum(c) / len(ring), 1) for c in zip(*ring))
        top = Part("M_TestCaliche", smooth=True)
        drape(top, ring, ground, origin, 0.15, 2.0, None, holes, 0.6)
        edge = Part("M_TestCaliche", smooth=True)
        skirt(edge, ring, ground, origin, 0.15, 1.2, 0.35)
        name = f"SK_T_Pad{pid}"
        meshes[name] = {"origin": list(origin), "parts": [top.dump(), edge.dump()]}
        put(name, origin, 180.0, z=0.0, collide="complex", feature=f"pad_{pid}")
    # scorch skins (masked, no collision)
    for sid, c, brg, L, Wd, k in SCORCH:
        fx, fy = fwd(brg)
        rx, ry = fy, -fx
        ring = [(c[0] - fx * L / 2 - rx * Wd / 2, c[1] - fy * L / 2 - ry * Wd / 2), (c[0] + fx * L / 2 - rx * Wd / 2, c[1] + fy * L / 2 - ry * Wd / 2),
                (c[0] + fx * L / 2 + rx * Wd / 2, c[1] + fy * L / 2 + ry * Wd / 2), (c[0] - fx * L / 2 + rx * Wd / 2, c[1] - fy * L / 2 + ry * Wd / 2)]

        def uvf(x, y, c=c, fx=fx, fy=fy, rx=rx, ry=ry, L=L, Wd=Wd):
            dx, dy = x - c[0], y - c[1]
            return (0.5 + (dx * rx + dy * ry) / Wd, 0.5 + (dx * fx + dy * fy) / L)
        on_pad = any(inside(c, r) for r in PADS.values())
        sk = Part("M_TestScorch" if k >= 0.7 else "M_TestScorchLight", smooth=True)
        holes = [t["rim"] for t in tinfo.values()] + [a["ring"] for a in APRONS.values()]
        drape(sk, ring, ground, c, 0.22 if on_pad else 0.07, 2.0, uvf, holes, 0.5)
        name = f"SK_T_Scorch_{sid}"
        if sk.t:
            meshes[name] = {"origin": [round(c[0], 1), round(c[1], 1)], "parts": [sk.dump()]}
            put(name, c, 180.0, z=0.0, collide="none", feature="scorch")
    # ---------------------------------------------------------------- hardware on the stands
    g = lambda x, y: round(ground(x, y), 2)
    zr = lambda x, y: round(ground(x, y) + RIM_UP, 2)
    # 2025 stands: black vertical single-engine cells over the trench heads, engine hanging nozzle-down (NSF Aug 2025)
    cells = {"RN": (896.0, 636.5), "RS": (875.0, 212.0)}
    for sid, p in cells.items():
        z0 = g(*p) + 0.15
        put("SK_RaptorCell", p, 270.0, z=z0, collide="complex", feature=TRENCHES[sid]["feature"])
        put("SK_RaptorEngine", p, 270.0, z=z0 + 6.6, collide="none", feature=TRENCHES[sid]["feature"])
    # tanks: three ~40 m horizontal tanks east-west and vertical tanks (Esri 2025; Apple: RS has two tall ones)
    for y in (648.0, 642.0, 636.0):
        put("SK_TankH", (969.0, y), 90.0, (4.0 / 3.0, 4.0, 4.0 / 3.0), feature="raptor_north_stand", L=40, W=4, sink=0.0)
    for x in (932.0, 938.0):
        put("SK_TankV", (x, 666.0), 0.0, feature="raptor_north_stand", sink=0.0)
    for y in (224.0, 218.5, 213.0):
        put("SK_TankH", (947.0, y), 90.0, (4.0 / 3.0, 4.0, 4.0 / 3.0), feature="raptor_south_stand", L=40, W=4, sink=0.0)
    for p in ((913.0, 238.0), (930.0, 240.0)):
        put("SK_TankTall", p, 0.0, feature="raptor_south_stand", sink=0.0)
    put("SK_RVacTrailer", (935.0, 183.0), 90.0, feature="raptor_south_stand", sink=0.05)    # a vacuum engine on its trailer (NSF Aug 2025)
    # the pipe rack between the two stands (Esri: x ~921, y 262..590)
    y = 266.0
    while y < 590.0:
        put("SK_PipeRack", (921.0, y), 0.0, collide="complex", feature="raptor_pipe_rack", sink=0.0)
        y += 10.0
    # 2021 vertical stand (moved onto its trench head, where NAIP / Esri show it) and the second-stage stand
    # (stand origin = the engine / stage axis, 2.5 m into the trench from its head wall)
    put("SK_VertStand", (-112.0, 329.5), 180.0, (1.0, 1.0, 1.0), z=zr(-112.0, 329.5), collide="complex", feature="raptor_vertical_2021")
    put("SK_RaptorEngine", (-112.0, 329.5), 180.0, z=zr(-112.0, 329.5) + 7.2, collide="none", feature="raptor_vertical_2021")
    put("SK_VertStandS2", (994.0, -712.5), 180.0, (1.15, 1.0, 0.75), z=zr(994.0, -712.5), collide="complex", feature="stage2_stand")
    put("SK_UpperStage", (994.0, -712.5), 180.0, z=zr(994.0, -712.5) + 7.3, collide="complex", feature="stage2_stand")
    # tripod (vertical Raptor stand since 2020): an engine under the cap over the deflector
    put("SK_RaptorEngine", (-15.0, -548.0), 225.0, z=g(-15.0, -548.0) + 29.6, collide="none", feature="tripod")
    # (the horizontal Raptor bays' SK_EngineStandH already carry an engine bell)
    # the display booster on the circle in front of the Rocket Development Hangar (Apple: its long shadow; Kenny's photo
    # 06: the upright white stage behind the stage-left light tower; Esri 2025-04: the circle being built, empty)
    put("SK_DisplayBooster", (1757.0, 651.0), 200.0, z=g(1757.0, 651.0) - 0.1, collide="complex", feature="display_booster")
    feat("display_booster", "Display booster at the hangar circle", ["unveil/06_building_light_tower_booster.webp (upright stage in the distance)", "tests: apple_rdh_display_booster_shadow.jpg"],
         (1757.0, 651.0), [26, 26, 48], "a flown-looking first stage standing on its legs on a round concrete plinth, soot on the lower third, black interstage and grid fins",
         "SK_DisplayBooster", "none", "medium (position from imagery; legs / fins as on display boosters)")
    for fid, nm, p, look in (("raptor_cells", "2025 vertical engine cells (Raptor North / South)", (885.0, 420.0),
                              "black steel cells ~16 m tall straddling the trench heads, an engine hanging nozzle-down in an open bay, run tank on the roof; white tanks east; pipe rack between"),):
        feat(fid, nm, ["tests: nsf_2025-08_raptor_north_south_flyover.jpg", "research: nsf_2025-08_raptor_north_bay_r3.jpg"], p, [16, 14, 16], look,
             "SK_RaptorCell + SK_RaptorEngine", "none", "medium")
    # ---------------------------------------------------------------- timed engine tests (SkysterEngineTests)
    def site(sid, name, kind, nozzle, dirn, plume_len, plume_r, exit_p, exit_dir, exit_w, dur, smoke=1.0, fire=1.0, nozzles=1, spread=0.0):
        return {"id": sid, "name": name, "kind": kind, "nozzle": [round(v, 2) for v in nozzle], "dir": dirn, "nozzles": nozzles, "nozzle_spread_m": spread,
                "plume_len_m": plume_len, "plume_radius_m": plume_r, "exit": [round(v, 2) for v in exit_p], "exit_dir": exit_dir, "exit_width_m": exit_w,
                "duration_s": dur, "smoke_scale": smoke, "fire_scale": fire}
    rn_z, rs_z = g(*cells["RN"]) + 0.15, g(*cells["RS"]) + 0.15
    tests = [
        site("RN", "Raptor North", "engine", (896.0, 636.5, rn_z + 3.4), [0, 0, -1], 11.0, 1.0, (824.0, 638.0, zr(824.0, 638.0) + 1.0), [-1, 0, 0.18], 24.0, 14.0, 1.1, 1.1),
        site("FS", "First-stage stand (booster)", "booster", (-134.0, -577.0, 22.8), [0, 0, -1], 15.0, 2.2, (-147.0, -652.0, 23.6), [0, -1, 0.2], 60.0, 12.0, 2.2, 1.8, 9, 1.2),
        site("RS", "Raptor South", "engine", (875.0, 212.0, rs_z + 3.4), [0, 0, -1], 11.0, 1.0, (802.0, 214.5, zr(802.0, 214.5) + 1.0), [-1, 0, 0.18], 25.0, 18.0, 1.1, 1.1),
        site("TRIPOD", "Tripod (vertical Raptor)", "engine", (-15.0, -548.0, g(-15.0, -548.0) + 26.5), [0, 0, -1], 6.0, 0.9,
             (-23.1, -556.1, g(-23.1, -556.1) + 1.2), [-0.69, -0.69, 0.22], 10.0, 10.0, 0.9, 1.0),
        site("S2", "Second-stage stand", "stage", (994.0, -712.5, zr(994.0, -712.5) + 4.1), [0, 0, -1], 7.0, 1.3, (1002.0, -758.0, zr(1002.0, -758.0) + 1.0), [0, -1, 0.2], 30.0, 12.0, 1.0, 0.9),
        site("RV", "Vertical engine stand (2021)", "engine", (-112.0, 329.5, zr(-112.0, 329.5) + 4.0), [0, 0, -1], 7.0, 1.0, (-128.0, 250.0, zr(-128.0, 250.0) + 1.0), [0, -1, 0.2], 38.0, 10.0, 1.0, 1.0),
        site("MERLIN", "Merlin vertical stands", "engine", (547.0, -1284.0, g(547.0, -1284.0) + 5.1), [0, 0, -1], 3.0, 0.55, (556.0, -1284.0, g(556.0, -1284.0) + 0.8), [1, 0, 0.2], 12.0, 12.0, 0.8, 1.0),
        site("RH", "Horizontal Raptor bays", "engine", (-97.5, 453.0, g(-97.0, 447.0) + 3.2), [-0.087, 0.996, 0], 16.0, 1.0, (-99.0, 470.0, g(-99.0, 470.0) + 2.0), [-0.087, 0.996, 0.1], 14.0, 15.0, 0.9, 1.0),
    ]
    out = {"frame": "metres, x east, y north, z above the map datum (Unreal = (y*100, x*100, z*100))",
           "trenches": tinfo, "terrain_cuts": cuts, "aprons": {k: {"ring": v["ring"], "mouth": v["mouth"]} for k, v in APRONS.items()},
           "pads": PADS, "scorch": [s[0] for s in SCORCH],
           "engine_tests": {"interval_s": 414.0, "first_delay_s": 40.0, "first_site": "nearest", "random_order": False,
                            "wind_from_bearing": 170.0, "wind_mps": 5.0, "shake_radius_m": 900.0, "sound_radius_m": 3000.0,
                            "order": [t["id"] for t in tests], "sites": tests},
           "meshes_file": str(MESH_OUT.relative_to(ROOT))}
    MESH_OUT.write_text(json.dumps(meshes))
    return out


if __name__ == "__main__":
    print("run site_layout.py: it calls tests_layout.build()")
