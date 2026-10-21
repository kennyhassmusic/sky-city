"""Sky City: Chicago's water side -- the Chicago Harbor Lock, the harbours' docks, the Dime Pier breakwater, navigation
lights and a fleet of boats (sailboats, motor yachts, river tour boats, water taxis, the Navy Pier speedboat, dinner
cruise ships, the four-masted tall ship, the Columbia Yacht Club's ferry clubhouse, tiki boats, kayaks, buoys),
modelled procedurally in headless Blender and exported as GLB, one file per asset, to SourceArt/Landmarks/water/.

Same conventions as Scripts/landmarks/blender_landmarks.py (its Builder / PlanBuilder / preview helpers are imported
and used read-only; nothing in that file is changed):
  * real-world metres; Unreal's glTF import maps Blender (x, y, z) m -> Unreal (x, -y, z) * 100 cm;
  * BOATS: bow toward Blender +X (= Unreal +X), origin on the WATERLINE at mid-length, port side = Blender +Y.
    In Unreal a boat heading along plan direction (dx, dy) gets yaw = atan2(dx, dy) degrees;
  * SITE assets (lock walls, docks, breakwater) are modelled in the PLAN frame (Saved/Mashup/plan_v3.json: x east,
    y north) relative to a site origin and turned -90 deg about Z at export (PlanBuilder): place them in Unreal at the
    site origin, ground level, with NO rotation.  Heights: plan ground z = 0, water surface z = -5.5 m (build_city.py
    WATER_Z), river / lake bed -8 m;
  * gate leaves are plan-frame too (pivot at the origin, closing arm along +x): yaw in Unreal = -(plan angle);
  * material slots: M_CWB_* = boat surfaces (Unreal: MI_CWB_* on the bobbing master M_CW_BoatBob), M_CW_* = static
    structures (MI_CW_*), plain M_* = slots that already exist as MI_LM_* (place_landmarks_ue.py);
  * Nanite OFF, collision = the render mesh (Scripts/roads/place_chicago_water_ue.py sets both).
Positions and shapes come from OpenStreetMap (SourceArt/Landmarks/water/water_features.json, made by
Scripts/landmarks/chicago_water_osm.py), USDA NAIP aerials and Wikimedia Commons photos in
SourceArt/Reference/ChicagoWater/ (sources.txt in each folder), plus published dimensions (see each docstring).

Run (repo root):
  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/landmarks/blender_chicago_water.py [-- jobs...]
     jobs: boats lock docks breakwater lights (default: all) -> SourceArt/Landmarks/water/*.glb + water.json
  ... -P Scripts/landmarks/blender_chicago_water.py -- --render [names...]
     preview renders SourceArt/Landmarks/water/preview_<name>.png (PREVIEWS; default: all)
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
sys.path.insert(0, ROOT + "/Scripts/landmarks")
import blender_landmarks as BL                                   # noqa: E402  (helpers only, read-only)
from blender_landmarks import Builder, PlanBuilder, ccw, offset_poly, circle, rrect, tri_count   # noqa: E402

OUT = ROOT + "/SourceArt/Landmarks/water"
os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
FEAT = json.load(open(OUT + "/water_features.json"))
PLAN = json.load(open(ROOT + "/Saved/Mashup/plan_v3.json"))
META = {}
WATER = -5.5          # water surface, metres relative to plan ground (build_city.py WATER_Z = -550 cm)
BED = -8.0            # river / lake bed

# ------------------------------------------------------------------ materials (added to the landmarks' table)
CW_MATS = {
    # boats: Unreal MI_CWB_* on M_CW_BoatBob (gentle bobbing by world-position offset)
    "M_CWB_HullWhite": ((0.90, 0.91, 0.92), 0.0, 0.25, {}),
    "M_CWB_HullNavy": ((0.04, 0.08, 0.20), 0.0, 0.25, {}),
    "M_CWB_HullYellow": ((0.96, 0.74, 0.05), 0.0, 0.35, {}),
    "M_CWB_HullBlack": ((0.035, 0.035, 0.04), 0.0, 0.35, {}),
    "M_CWB_Bottom": ((0.30, 0.06, 0.05), 0.0, 0.6, {}),        # antifouling red below the boot stripe
    "M_CWB_Boot": ((0.06, 0.08, 0.12), 0.0, 0.4, {}),          # dark boot / rub rail
    "M_CWB_Stripe": ((0.05, 0.12, 0.35), 0.0, 0.3, {}),        # navy cove stripe, window bands of the big ships
    "M_CWB_Maroon": ((0.36, 0.05, 0.06), 0.0, 0.35, {}),       # Windy's sheer stripe
    "M_CWB_Green": ((0.04, 0.20, 0.11), 0.0, 0.4, {}),         # river tour-boat trim
    "M_CWB_Teak": ((0.42, 0.29, 0.16), 0.0, 0.7, {}),
    "M_CWB_DeckGrey": ((0.78, 0.78, 0.75), 0.0, 0.8, {}),
    "M_CWB_Glass": ((0.02, 0.035, 0.05), 0.6, 0.06, {}),
    "M_CWB_GlassBlue": ((0.04, 0.10, 0.20), 0.5, 0.08, {}),
    "M_CWB_Canvas": ((0.04, 0.14, 0.34), 0.0, 0.85, {}),       # sail covers, biminis, jib UV strips
    "M_CWB_Sail": ((0.93, 0.92, 0.88), 0.0, 0.8, {}),
    "M_CWB_Spar": ((0.72, 0.74, 0.76), 0.8, 0.3, {}),          # aluminium masts and booms
    "M_CWB_WoodSpar": ((0.55, 0.38, 0.20), 0.0, 0.55, {}),     # varnished spars (tall ship)
    "M_CWB_Steel": ((0.72, 0.74, 0.76), 0.9, 0.25, {}),        # stainless rails, rigging
    "M_CWB_Seat": ((0.08, 0.24, 0.58), 0.0, 0.6, {}),
    "M_CWB_Rope": ((0.16, 0.13, 0.09), 0.0, 0.9, {}),
    "M_CWB_Orange": ((0.92, 0.36, 0.05), 0.0, 0.6, {}),
    "M_CWB_Thatch": ((0.52, 0.40, 0.20), 0.0, 0.95, {}),
    "M_CWB_Light": ((1.0, 0.95, 0.80), 0.0, 0.4, {"emit": 4.0}),
    # static structures: Unreal MI_CW_* (tinted M_StreetProp)
    "M_CW_LockConcrete": ((0.63, 0.62, 0.59), 0.0, 0.85, {}),
    "M_CW_WallDark": ((0.20, 0.21, 0.20), 0.0, 0.9, {}),
    "M_CW_GateSteel": ((0.33, 0.36, 0.39), 0.6, 0.45, {}),
    "M_CW_SafetyYellow": ((0.95, 0.74, 0.05), 0.0, 0.6, {}),
    "M_CW_Fender": ((0.035, 0.035, 0.035), 0.0, 0.8, {}),
    "M_CW_DockDeck": ((0.50, 0.46, 0.40), 0.0, 0.85, {}),
    "M_CW_Float": ((0.78, 0.78, 0.76), 0.0, 0.7, {}),
    "M_CW_Piling": ((0.24, 0.25, 0.26), 0.5, 0.6, {}),
    "M_CW_Riprap": ((0.36, 0.35, 0.32), 0.0, 0.95, {}),
    "M_CW_Buoy": ((0.93, 0.93, 0.91), 0.0, 0.5, {}),
    "M_CW_WhiteWall": ((0.86, 0.86, 0.84), 0.0, 0.7, {}),
    "M_CW_SignalRed": ((0.90, 0.05, 0.03), 0.0, 0.4, {"emit": 3.0}),
    "M_CW_SignalGreen": ((0.05, 0.85, 0.25), 0.0, 0.4, {"emit": 3.0}),
    "M_CW_ShipBlack": ((0.035, 0.035, 0.04), 0.0, 0.35, {}),   # moored-for-good ship (no bobbing)
    "M_CW_ShipWhite": ((0.88, 0.88, 0.87), 0.0, 0.4, {}),
    "M_CW_ShipRed": ((0.40, 0.06, 0.05), 0.0, 0.5, {}),
}
BL.MATDEF.update(CW_MATS)
mat = BL.mat


def reset():
    BL.reset()


# ------------------------------------------------------------------ export
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
    d = {"file": f"SourceArt/Landmarks/water/{name}.glb", "tris": tris,
         "bbox_min_m": [round(c, 3) for c in lo], "bbox_max_m": [round(c, 3) for c in hi],
         "size_m": [round(c, 3) for c in (hi - lo)], "materials": mats}
    d.update(meta or {})
    META[name] = d
    print(f"exported {name}: {tris} tris, size {tuple(round(c, 2) for c in hi - lo)}")
    if tris > 60000:
        print("WARNING: over the 60k triangle budget:", name)


def site_export(name, ob, meta):
    meta = dict(meta)
    meta["frame"] = "plan-local (x east, y north) turned -90 deg: place in Unreal at the site origin with NO rotation"
    export(name, [ob], meta)


# ------------------------------------------------------------------ boat building blocks
def lerp(a, b, t):
    return a + (b - a) * t


class Hull:
    """Smooth monohull, bow toward +X, waterline z = 0, waterline length L centred on x = 0.
    bands: [(spec, material, extra_rows)] from the sheer down; each band runs from its spec to the next one (the last one
    to the keel). spec ('deck', dz) = dz below the sheer line, ('abs', z) = absolute height (parallel to the waterline).
    Section = superellipse |y/b|^sq + |(zd - z)/(zd - zk)|^sq = 1 (sq 2 round, 4+ boxy, < 2 vee), sq blends from sq_mid
    amidships to sq_bow at the stem; the stem rakes forward above the waterline (rake m per m) and the forefoot cuts away
    below it; transom = stern half-beam / max half-beam."""

    def __init__(self, B, L, beam, fb_bow, fb_stern, draft, bands, deck_mat, transom=0.82, tm=0.42, entry=1.7, rake=0.9,
                 sq_mid=3.2, sq_bow=1.3, nst=22, camber=0.06, stern_rake=0.25, forefoot=0.8, deck=True):
        self.L, self.beam, self.rake = L, beam, rake
        self.fb_bow, self.fb_stern, self.draft = fb_bow, fb_stern, draft
        self.transom, self.tm, self.entry, self.sq_mid, self.sq_bow = transom, tm, entry, sq_mid, sq_bow
        self.stern_rake, self.forefoot = stern_rake, forefoot
        ts = []
        for i in range(nst):
            s = i / (nst - 1)
            ts.append(0.65 * s + 0.35 * (1 - math.cos(math.pi * s)) / 2)
        self.ts = ts
        # rows (z specs) with the material of the band below each row
        rows = []
        for k, (spec, m, extra) in enumerate(bands):
            nxt = bands[k + 1][0] if k + 1 < len(bands) else ("keel", 0.0)
            rows.append((spec, None, m))
            for e in range(extra):
                rows.append((spec, (nxt, (e + 1) / (extra + 1)), m))
        self.rows = rows
        bm = B.bm
        grid = []
        self.st = []
        for t in ts:
            b, zd, zk, sq = self.section(t)
            xw = -L / 2 + L * t
            zs = [self.row_z(r, zd, zk) for r in rows]
            col = []
            pts_port = []
            for z in zs:
                rel = min(1.0, max(0.0, (zd - z) / max(1e-6, zd - zk)))
                y = b * max(0.0, 1 - rel ** sq) ** (1.0 / sq)
                pts_port.append((xw + self.dx(t, z), y, z))
            keel = (xw + self.dx(t, zk), 0.0, zk)
            col = pts_port + [keel] + [(x, -y, z) for (x, y, z) in reversed(pts_port)]
            grid.append([bm.verts.new(p) for p in col])
            self.st.append((xw + self.dx(t, zd), b, zd))
        nrow = len(rows)
        mats_seg = []
        for j in range(2 * nrow):
            if j < nrow:
                mats_seg.append(rows[j][2])
            else:
                mats_seg.append(rows[2 * nrow - 1 - j][2])
        for i in range(nst - 1):
            for j in range(2 * nrow):
                vs = [grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]]
                B._poly(vs, mats_seg[j], None, True)
        # transom (normal -x): the stern section's outline
        stern = [bm.verts.new(v.co) for v in grid[0]]
        B._poly(stern, bands[0][1], None, False)
        if deck:
            dg = []
            for (x, b, zd) in self.st:
                row = []
                for k, f in enumerate((-1.0, -0.5, 0.0, 0.5, 1.0)):
                    row.append(bm.verts.new((x, f * b * 0.999, zd + camber * (1 - f * f))))
                dg.append(row)
            for i in range(nst - 1):
                for k in range(4):
                    B._poly([dg[i][k], dg[i + 1][k], dg[i + 1][k + 1], dg[i][k + 1]], deck_mat, None, True)
            # deck end cap at the transom (closes the camber gap)
            B._poly([dg[0][0], dg[0][1], dg[0][2], dg[0][3], dg[0][4]], deck_mat, None, False)

    def section(self, t):
        L = self.L
        tm = self.tm
        if t <= tm:
            b = self.beam / 2 * (self.transom + (1 - self.transom) * math.sin(math.pi / 2 * t / tm))
        else:
            u = (t - tm) / (1 - tm)
            b = self.beam / 2 * max(0.0, 1 - u ** self.entry) ** 0.6
        zd = self.fb_stern + (self.fb_bow - self.fb_stern) * t ** 1.8
        ub = max(0.0, (t - 0.72) / 0.28)
        zk = -self.draft * (1 - self.forefoot * ub ** 2)
        us = max(0.0, (t - tm) / (1 - tm))
        sq = self.sq_mid + (self.sq_bow - self.sq_mid) * us ** 1.2
        return b, zd, zk, sq

    def row_z(self, r, zd, zk):
        spec, sub, _m = r

        def z_of(sp):
            if sp[0] == "deck":
                return zd - sp[1]
            if sp[0] == "abs":
                return sp[1]
            return zk
        z = z_of(spec)
        if sub:
            z = lerp(z, z_of(sub[0]), sub[1])
        return min(zd, max(zk + 0.02, z))

    def dx(self, t, z):
        ub = max(0.0, (t - 0.7) / 0.3) ** 2
        d = self.rake * max(z, 0.0) * ub + 0.6 * self.rake * min(z, 0.0) * ub
        if t < 0.06:
            d -= self.stern_rake * max(z, 0.0) * (1 - t / 0.06)
        return d

    def at(self, x):
        """(half beam, deck height) of the sheer at x."""
        st = self.st
        if x <= st[0][0]:
            return st[0][1], st[0][2]
        for (x0, b0, z0), (x1, b1, z1) in zip(st, st[1:]):
            if x0 <= x <= x1:
                f = (x - x0) / max(1e-6, x1 - x0)
                return lerp(b0, b1, f), lerp(z0, z1, f)
        return 0.0, st[-1][2]

    def bow_x(self):
        return self.st[-1][0]

    def stern_x(self):
        return self.st[0][0]

    def outline(self, x0, x1, inset, n=14, round_fwd=0.0):
        """Closed CCW plan outline following the sheer between x0 and x1, inset from the deck edge (min half width 0.25);
        round_fwd rounds the forward end (fraction of the half width)."""
        xs = [lerp(x0, x1, k / (n - 1)) for k in range(n)]
        half = [max(0.25, self.at(x)[0] - inset) for x in xs]
        if round_fwd > 0:
            rr = round_fwd * half[-1]
            for k in range(n):
                d = x1 - xs[k]
                if d < rr:
                    half[k] = max(0.2, half[k] * math.sqrt(max(0.0, 1 - ((rr - d) / rr) ** 2)))
        stb = [(x, -h) for x, h in zip(xs, half)]
        prt = [(x, h) for x, h in zip(xs[::-1], half[::-1])]
        return stb + prt


def house(B, rows, roof=None, roof_z=None, roof_over=0.0):
    """Lofted deckhouse: rows = [(z, outline, material_of_band_above)] bottom-up (same vertex count per outline, CCW);
    walls between rows; roof face on the last outline (optionally an overhanging slab roof_over metres wider)."""
    bm = B.bm
    rings = [[bm.verts.new((x, y, z)) for x, y in ol] for z, ol, _m in rows]
    n = len(rows[0][1])
    for k in range(len(rows) - 1):
        m = rows[k][2]
        for i in range(n):
            j = (i + 1) % n
            B._poly([rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]], m, None, False)
    if roof:
        ztop = rows[-1][0]
        ol = rows[-1][1]
        if roof_over > 0:
            big = offset_poly(ol, roof_over)
            B.face([(x, y, ztop) for x, y in big][::-1], roof)        # underside (seen under the overhang)
            B.face([(x, y, ztop + 0.12) for x, y in big], roof)
            for i in range(len(big)):
                a, b = big[i], big[(i + 1) % len(big)]
                B.face([(a[0], a[1], ztop), (b[0], b[1], ztop), (b[0], b[1], ztop + 0.12), (a[0], a[1], ztop + 0.12)], roof)
        else:
            B._poly([bm.verts.new((x, y, ztop)) for x, y in ol], roof, None, False)


def shrink_front(ol, x_front, dx):
    """Pull the forward part of an outline aft by up to dx (raked windscreens): points within 3 m of x_front move."""
    out = []
    for x, y in ol:
        f = max(0.0, 1 - (x_front - x) / 3.0)
        out.append((x - dx * f, y))
    return out


def rail(B, pts, z, h=1.0, step=1.6, m="M_CWB_Steel", r=0.022, mid=True, closed=False, post=0.045):
    """Posts + top rail (+ mid rail) along a polyline at height z (a list of z per point is allowed)."""
    P = [Vector((p[0], p[1], p[2] if len(p) > 2 else z)) for p in pts]
    if closed:
        P = P + [P[0]]
    for a, b in zip(P, P[1:]):
        L = (b - a).length
        if L < 0.1:
            continue
        n = max(1, round(L / step))
        for i in range(n + (1 if b is P[-1] else 0)):
            c = a.lerp(b, i / n)
            B.box((c.x, c.y, c.z + h / 2), (post, post, h), m)
        B.tube([a + Vector((0, 0, h)), b + Vector((0, 0, h))], [r, r], m, 4)
        if mid:
            B.tube([a + Vector((0, 0, h * 0.5)), b + Vector((0, 0, h * 0.5))], [r * 0.7, r * 0.7], m, 4)


def windows_band(B, ol, z0, z1, step, m, w=0.09, out=0.03, skip_x=None):
    """Mullions (thin vertical bars) every `step` metres along an outline's long (fore-and-aft) sides, standing proud of a
    glazed band."""
    n = len(ol)
    acc = step * 0.5
    for i in range(n):
        a, b = Vector(ol[i]), Vector(ol[(i + 1) % n])
        e = b - a
        L = e.length
        if L < 1e-4:
            continue
        t = e.normalized()
        if abs(t.x) < 0.7:
            acc = step * 0.5
            continue
        nrm = Vector((t.y, -t.x))
        d = acc
        while d < L:
            c = a + t * d + nrm * out
            if not (skip_x and skip_x(c.x)):
                B.box((c.x, c.y, (z0 + z1) / 2), (w, 0.06, z1 - z0), m)
            d += step
        acc = d - L


# ================================================================== 1. boats (bow +X, origin on the waterline)
def white_bands(hull="M_CWB_HullWhite", stripe="M_CWB_Stripe", boot_top=0.22):
    return [(("deck", 0.0), hull, 0), (("deck", 0.07), stripe, 0), (("deck", 0.15), hull, 2),
            (("abs", boot_top), "M_CWB_Boot", 0), (("abs", 0.08), "M_CWB_Bottom", 3)]


def sloop(B, hull_mat="M_CWB_HullWhite", sailing=False):
    """A 33 ft cruising sloop (the bulk of DuSable / Monroe Harbor): LOA ~10.2 m, waterline 8.8 m, beam 3.3 m, mast 13.5 m
    above the deck, cabin trunk with ports, cockpit coamings, stern pushpit, bow pulpit and lifelines; sails furled
    (blue main cover on the boom, roller-furled jib) or set (sailing=True)."""
    bands = white_bands(hull_mat, "M_CWB_Stripe" if hull_mat == "M_CWB_HullWhite" else "M_CWB_HullWhite")
    H = Hull(B, 8.8, 3.3, 1.15, 0.86, 0.45, bands, "M_CWB_DeckGrey", transom=0.80, rake=0.85, sq_mid=2.6, sq_bow=1.25,
             nst=20, stern_rake=-0.35)
    zc = max(H.at(x)[1] for x in (-0.5, 0.5, 1.5, 2.3)) - 0.04
    ol = H.outline(-0.8, 2.6, 0.62, n=10, round_fwd=0.9)
    house(B, [(zc, ol, "M_CWB_HullWhite"), (zc + 0.28, ol, "M_CWB_Glass"), (zc + 0.40, ol, "M_CWB_HullWhite"),
              (zc + 0.56, ol, None)], roof="M_CWB_DeckGrey")
    zk = H.at(-2.0)[1]
    for y in (-1.05, 1.05):                                                    # cockpit coamings + seats
        B.box((-2.4, y, zk + 0.18), (3.0, 0.08, 0.36), "M_CWB_HullWhite")
        B.box((-2.4, y * 0.78, zk + 0.10), (2.8, 0.42, 0.20), "M_CWB_Teak")
    B.tube([(-3.55, 0, zk), (-3.55, 0, zk + 0.75)], [0.03, 0.03], "M_CWB_Steel", 4)     # wheel pedestal + wheel
    B.torus((-3.5, 0, zk + 0.95), 0.38, 0.025, "M_CWB_Steel", 16, 4, Matrix.Rotation(math.pi / 2, 3, "Y"))
    xm = 1.15
    zm = H.at(xm)[1] + 0.56
    top = zm + 13.0
    B.tube([(xm, 0, zm - 0.5), (xm, 0, top)], [0.095, 0.06], "M_CWB_Spar", 6, cap1=True)
    for zs_, ws in ((zm + 4.6, 1.15), (zm + 8.6, 0.8)):                          # spreaders
        B.tube([(xm, -ws, zs_), (xm, ws, zs_)], [0.025, 0.025], "M_CWB_Spar", 4)
    bow = Vector((H.bow_x() - 0.05, 0, H.fb_bow + 0.08))
    stern = Vector((H.stern_x() + 0.15, 0, H.fb_stern + 0.05))
    zb = zm + 0.95
    B.tube([(xm, 0, top - 0.6), bow], [0.012, 0.012], "M_CWB_Steel", 3)       # forestay
    B.tube([(xm, 0, top), stern], [0.01, 0.01], "M_CWB_Steel", 3)             # backstay
    for y in (-1.5, 1.5):                                                     # shrouds
        B.tube([(xm, 0, top - 0.9), (xm, y * 0.77, zm + 8.6), (xm, y, H.at(xm)[1])], [0.01, 0.01, 0.01], "M_CWB_Steel", 3)
        B.tube([(xm, 0, zm + 4.6), (xm - 0.6, y * 0.95, H.at(xm - 0.6)[1])], [0.01, 0.01], "M_CWB_Steel", 3)
    if not sailing:
        B.tube([(xm, 0, zb), (-3.4, 0, zb + 0.15)], [0.07, 0.06], "M_CWB_Spar", 6, cap0=True, cap1=True)       # boom
        B.tube([(xm - 0.15, 0, zb + 0.24), (-1.0, 0, zb + 0.28), (-2.9, 0, zb + 0.26)], [0.24, 0.2, 0.12], "M_CWB_Canvas", 7,
               cap0=True, cap1=True, aspect=[(0.8, 1.3)] * 3)                                                   # main cover
        f0 = bow.lerp(Vector((xm, 0, top - 0.6)), 0.05)
        f1 = bow.lerp(Vector((xm, 0, top - 0.6)), 0.88)
        B.tube([f0, f0.lerp(f1, 0.35), f1], [0.045, 0.075, 0.03], "M_CWB_Canvas", 6, cap0=True, cap1=True)   # furled jib
    else:
        a = math.radians(-14)
        bend = Vector((math.cos(a), math.sin(a), 0))
        bend_end = Vector((xm, 0, zb)) - bend * 4.5
        B.tube([(xm, 0, zb), bend_end], [0.07, 0.06], "M_CWB_Spar", 6, cap0=True, cap1=True)
        head = Vector((xm, 0, top - 0.3))
        P = [Vector((xm, 0, zb + 0.1)), bend_end + Vector((0, 0, 0.1)), head.lerp(bend_end, 0.45) + bend * -0.25 + Vector((0, 0, 0.5)), head]
        for f in (P, P[::-1]):
            B.face(f, "M_CWB_Sail")                                           # mainsail (double-sided)
        clew = Vector((xm - 1.6, -1.1, zm + 0.6))
        J = [bow, Vector((xm, 0, top - 0.8)), clew]
        B.face(J, "M_CWB_Sail")
        B.face(J[::-1], "M_CWB_Sail")
    # lifelines: stanchions along the sheer, bow pulpit, stern pushpit
    xs = [lerp(H.stern_x() + 0.4, H.bow_x() - 1.0, k / 6) for k in range(7)]
    for sgn in (-1, 1):
        pts = [(x, sgn * (H.at(x)[0] - 0.12), H.at(x)[1]) for x in xs]
        rail(B, pts, 0, h=0.62, step=1.4, r=0.012, post=0.03)
    by = H.at(H.bow_x() - 1.0)[0] - 0.12
    B.tube([(H.bow_x() - 1.0, -by, H.at(H.bow_x() - 1.0)[1] + 0.62), (H.bow_x() - 0.35, 0, H.fb_bow + 0.65),
            (H.bow_x() - 1.0, by, H.at(H.bow_x() - 1.0)[1] + 0.62)], [0.016] * 3, "M_CWB_Steel", 4)
    sx = H.stern_x() + 0.4
    sb = H.at(sx)[0] - 0.12
    B.tube([(sx, -sb, H.fb_stern + 0.62), (sx - 0.2, 0, H.fb_stern + 0.62), (sx, sb, H.fb_stern + 0.62)], [0.016] * 3, "M_CWB_Steel", 4)
    return H


def motor_yacht(B):
    """A 45 ft flybridge motor yacht (DuSable, Navy Pier Marina, the river charters): LOA ~14.5 m, beam 4.4 m, deep-vee
    bow, swim platform, main saloon with a raked windscreen, flybridge with helm and hardtop, radar arch."""
    bands = [(("deck", 0.0), "M_CWB_HullWhite", 0), (("deck", 0.10), "M_CWB_Boot", 0), (("deck", 0.18), "M_CWB_HullWhite", 2),
             (("abs", 0.40), "M_CWB_Stripe", 0), (("abs", 0.18), "M_CWB_Bottom", 3)]
    H = Hull(B, 13.2, 4.4, 1.95, 1.45, 0.85, bands, "M_CWB_Teak", transom=0.90, rake=1.05, sq_mid=3.8, sq_bow=1.15,
             nst=20, stern_rake=0.0)
    sx = H.stern_x()
    B.box((sx - 0.55, 0, 0.32), (1.1, 3.6, 0.16), "M_CWB_Teak")                # swim platform
    zc = H.at(0)[1] - 0.05
    ol = H.outline(-4.2, 2.6, 0.45, n=12, round_fwd=0.7)
    olt = shrink_front(ol, 2.6, 1.3)
    olm = shrink_front(ol, 2.6, 0.35)
    house(B, [(zc, ol, "M_CWB_HullWhite"), (zc + 0.75, olm, "M_CWB_Glass"), (zc + 1.75, olt, "M_CWB_HullWhite"),
              (zc + 2.0, olt, None)], roof="M_CWB_HullWhite", roof_over=0.15)
    zf = zc + 2.12                                                            # flybridge
    B.box((-1.2, 0, zf + 0.5), (1.0, 1.4, 1.0), "M_CWB_HullWhite")           # helm console
    B.box((-0.65, 0, zf + 1.05), (0.1, 1.3, 0.35), "M_CWB_Glass")
    for x in (-2.4, -3.3):
        B.box((x, 0, zf + 0.25), (0.6, 2.6, 0.5), "M_CWB_HullWhite")
    rail(B, [(-4.3, -1.75), (0.6, -1.75), (1.2, 0), (0.6, 1.75), (-4.3, 1.75)], zf, h=0.75, step=1.3, r=0.02)
    for x, y in ((-3.9, -1.5), (-3.9, 1.5), (-0.6, -1.5), (-0.6, 1.5)):
        B.tube([(x, y, zf), (x, y, zf + 2.0)], [0.03, 0.03], "M_CWB_Steel", 4)
    B.box((-2.25, 0, zf + 2.05), (4.0, 3.4, 0.1), "M_CWB_HullWhite")         # hardtop
    B.tube([(-3.6, -1.6, zf + 2.1), (-3.8, 0, zf + 2.9), (-3.6, 1.6, zf + 2.1)], [0.05] * 3, "M_CWB_HullWhite", 6)
    B.cyl((-3.8, 0, zf + 2.9), 0.1, 0.35, "M_CWB_HullWhite", 10)              # radar dome
    # foredeck rails + sun pad
    xs = [lerp(2.4, H.bow_x() - 0.6, k / 5) for k in range(6)]
    for sgn in (-1, 1):
        rail(B, [(x, sgn * (H.at(x)[0] - 0.1), H.at(x)[1]) for x in xs], 0, h=0.6, step=1.2, r=0.015, post=0.03)
    B.box((3.6, 0, H.at(3.6)[1] + 0.1), (1.6, 2.0, 0.2), "M_CWB_Canvas")
    return H


def tour_boat(B):
    """Chicago River architecture tour boat (Chicago's First Lady class, photos in river_boats/): LOA ~30 m, beam 7.9 m,
    classic white yacht hull with a green rub rail and boot top, enclosed lower saloon with a long row of windows, open
    upper deck with green railings and bench rows, low aft pilothouse; air draft kept under 5.2 m for the river bridges."""
    bands = [(("deck", 0.0), "M_CWB_Green", 0), (("deck", 0.16), "M_CWB_HullWhite", 2), (("abs", 0.38), "M_CWB_Green", 0),
             (("abs", 0.16), "M_CWB_HullBlack", 2)]
    H = Hull(B, 28.6, 7.9, 1.25, 1.05, 1.0, bands, "M_CWB_DeckGrey", transom=0.86, rake=0.55, sq_mid=4.6, sq_bow=1.7,
             nst=22, stern_rake=-0.2)
    zc = H.at(0)[1] - 0.02
    ol = H.outline(-12.6, 9.8, 0.28, n=16, round_fwd=1.0)
    house(B, [(zc, ol, "M_CWB_HullWhite"), (zc + 0.72, ol, "M_CWB_Glass"), (zc + 1.82, ol, "M_CWB_HullWhite"),
              (zc + 2.02, ol, "M_CWB_Green"), (zc + 2.14, ol, None)], roof="M_CWB_DeckGrey", roof_over=0.18)
    windows_band(B, ol, zc + 0.72, zc + 1.82, 1.05, "M_CWB_HullWhite", w=0.12)
    zu = zc + 2.26                                                            # upper deck
    ou = offset_poly(ol, 0.05)
    rail(B, [(x, y) for x, y in ou], zu, h=0.95, step=1.25, m="M_CWB_Green", r=0.035, closed=True, post=0.06)
    for k in range(13):                                                       # bench rows facing forward
        x = -10.4 + 1.25 * k
        if -8.6 < x < -5.4:
            continue
        hb = H.at(x)[0] - 0.9
        B.box((x, 0, zu + 0.22), (0.45, 2 * hb, 0.44), "M_CWB_Teak")
        B.box((x - 0.22, 0, zu + 0.6), (0.06, 2 * hb, 0.4), "M_CWB_Teak")
    po = H.outline(-8.6, -5.6, 2.4, n=6)
    house(B, [(zu, po, "M_CWB_HullWhite"), (zu + 0.85, po, "M_CWB_Glass"), (zu + 1.55, po, "M_CWB_HullWhite"),
              (zu + 1.7, po, None)], roof="M_CWB_HullWhite", roof_over=0.2)
    B.tube([(-7.0, 0, zu + 1.8), (-7.0, 0, zu + 2.6)], [0.03, 0.02], "M_CWB_Steel", 4)         # flag staff
    # bow / stern deck rails on the main deck
    xs = [lerp(9.6, H.bow_x() - 0.5, k / 3) for k in range(4)]
    for sgn in (-1, 1):
        rail(B, [(x, sgn * (H.at(x)[0] - 0.1), H.at(x)[1]) for x in xs], 0, h=0.9, step=1.2, m="M_CWB_Green", r=0.03)
    return H


def water_taxi(B):
    """Yellow river water taxi (photos in river_boats/): LOA ~20 m, beam 5.8 m, yellow hull and cabin with a black
    window band, white roof, raised pilot station forward, open aft deck; under 5 m air draft. No livery or names."""
    bands = [(("deck", 0.0), "M_CWB_HullBlack", 0), (("deck", 0.2), "M_CWB_HullYellow", 2), (("abs", 0.3), "M_CWB_HullBlack", 2)]
    H = Hull(B, 18.8, 5.8, 1.25, 1.05, 0.8, bands, "M_CWB_DeckGrey", transom=0.9, rake=0.5, sq_mid=4.2, sq_bow=1.6, nst=20,
             stern_rake=0.0)
    zc = H.at(0)[1] - 0.02
    ol = H.outline(-6.6, 6.2, 0.3, n=14, round_fwd=1.0)
    olt = shrink_front(ol, 6.2, 0.6)
    house(B, [(zc, ol, "M_CWB_HullYellow"), (zc + 0.62, ol, "M_CWB_Glass"), (zc + 1.85, olt, "M_CWB_HullYellow"),
              (zc + 2.1, olt, None)], roof="M_CWB_HullWhite", roof_over=0.12)
    windows_band(B, ol, zc + 0.62, zc + 1.85, 1.4, "M_CWB_HullYellow", w=0.14)
    zr = zc + 2.22
    po = H.outline(2.6, 5.2, 1.4, n=6, round_fwd=0.6)
    house(B, [(zr, po, "M_CWB_HullYellow"), (zr + 0.35, po, "M_CWB_Glass"), (zr + 1.0, po, "M_CWB_HullYellow"),
              (zr + 1.15, po, None)], roof="M_CWB_HullWhite", roof_over=0.1)
    xs = [lerp(H.stern_x() + 0.3, -6.6, k / 3) for k in range(4)]
    for sgn in (-1, 1):
        rail(B, [(x, sgn * (H.at(x)[0] - 0.1), H.at(x)[1]) for x in xs], 0, h=0.95, step=1.1, m="M_CWB_HullYellow", r=0.03)
    B.box((-8.4, 0, zc + 0.25), (0.5, 4.0, 0.5), "M_CWB_HullYellow")
    return H


def speedboat(B):
    """Navy Pier's open thrill-ride speedboat (Seadog class): LOA ~21 m, beam 5.4 m, deep-vee hull with a long raked bow,
    rows of bench seats on an open deck, a central console under a T-top; white with a blue band."""
    bands = [(("deck", 0.0), "M_CWB_HullWhite", 0), (("deck", 0.18), "M_CWB_Seat", 1), (("deck", 0.72), "M_CWB_HullYellow", 0),
             (("deck", 0.8), "M_CWB_HullWhite", 2), (("abs", 0.18), "M_CWB_Boot", 2)]
    H = Hull(B, 19.0, 5.4, 1.75, 1.15, 0.7, bands, "M_CWB_DeckGrey", transom=0.9, rake=1.5, sq_mid=2.5, sq_bow=1.05, nst=22,
             stern_rake=0.0)
    for k in range(11):
        x = -8.0 + 1.3 * k
        if 2.0 < x < 4.8:
            continue
        hb, zd = H.at(x)
        B.box((x, 0, zd + 0.22), (0.5, 2 * hb - 0.9, 0.44), "M_CWB_Seat")
        B.box((x - 0.26, 0, zd + 0.55), (0.08, 2 * hb - 0.9, 0.5), "M_CWB_Seat")
    zd = H.at(3.4)[1]
    B.box((3.4, 0, zd + 0.6), (1.6, 1.4, 1.2), "M_CWB_HullWhite")
    B.box((4.15, 0, zd + 1.35), (0.1, 1.3, 0.4), "M_CWB_Glass")
    for x, y in ((2.6, -1.0), (2.6, 1.0), (4.4, -1.0), (4.4, 1.0)):
        B.tube([(x, y, zd), (x, y, zd + 2.4)], [0.035, 0.035], "M_CWB_Steel", 4)
    B.box((3.5, 0, zd + 2.45), (2.6, 2.6, 0.1), "M_CWB_Seat")
    xs = [lerp(H.stern_x() + 0.3, H.bow_x() - 0.8, k / 9) for k in range(10)]
    for sgn in (-1, 1):
        rail(B, [(x, sgn * (H.at(x)[0] - 0.08), H.at(x)[1]) for x in xs], 0, h=0.7, step=1.3, r=0.02, mid=False)
    return H


def cruise_ship(B):
    """Lakefront dinner cruise ship (Odyssey / Spirit of Chicago class, navypier_ships/): LOA ~61 m, beam 12.4 m, three
    enclosed decks with dark-blue glazing, raked forward faces, open sun deck aft, bridge forward on deck 3, swept mast."""
    bands = [(("deck", 0.0), "M_CWB_HullWhite", 0), (("deck", 0.55), "M_CWB_Stripe", 0), (("deck", 0.8), "M_CWB_HullWhite", 2),
             (("abs", 0.5), "M_CWB_Stripe", 0), (("abs", 0.25), "M_CWB_HullBlack", 2)]
    H = Hull(B, 56.0, 12.4, 3.1, 2.5, 1.8, bands, "M_CWB_DeckGrey", transom=0.92, rake=1.35, sq_mid=5.5, sq_bow=1.5,
             nst=26, stern_rake=-0.3)
    z1 = H.at(0)[1] - 0.05
    o1 = H.outline(-27.5, 22.0, 0.35, n=18, round_fwd=1.0)
    house(B, [(z1, o1, "M_CWB_HullWhite"), (z1 + 0.55, o1, "M_CWB_GlassBlue"), (z1 + 2.45, shrink_front(o1, 22.0, 0.5), "M_CWB_HullWhite"),
              (z1 + 2.9, shrink_front(o1, 22.0, 0.6), None)], roof="M_CWB_DeckGrey", roof_over=0.3)
    windows_band(B, o1, z1 + 0.55, z1 + 2.45, 2.2, "M_CWB_HullWhite", w=0.16)
    z2 = z1 + 3.02
    o2 = H.outline(-23.5, 15.5, 0.7, n=16, round_fwd=1.0)
    house(B, [(z2, o2, "M_CWB_HullWhite"), (z2 + 0.5, o2, "M_CWB_GlassBlue"), (z2 + 2.3, shrink_front(o2, 15.5, 0.9), "M_CWB_HullWhite"),
              (z2 + 2.75, shrink_front(o2, 15.5, 1.1), None)], roof="M_CWB_DeckGrey", roof_over=0.35)
    windows_band(B, o2, z2 + 0.5, z2 + 2.3, 2.2, "M_CWB_HullWhite", w=0.16)
    z3 = z2 + 2.87
    o3 = H.outline(-13.0, 7.5, 2.0, n=12, round_fwd=0.9)
    house(B, [(z3, o3, "M_CWB_HullWhite"), (z3 + 0.6, o3, "M_CWB_GlassBlue"), (z3 + 2.1, shrink_front(o3, 7.5, 0.9), "M_CWB_HullWhite"),
              (z3 + 2.5, shrink_front(o3, 7.5, 1.0), None)], roof="M_CWB_HullWhite", roof_over=0.4)
    # sun deck rails (deck 3 level, aft) and bow rails (main deck)
    rail(B, [(-13.2, -H.at(-13.2)[0] + 0.9), (-23.5, -H.at(-23.5)[0] + 0.9), (-23.5, H.at(-23.5)[0] - 0.9), (-13.2, H.at(-13.2)[0] - 0.9)],
         z3, h=1.05, step=1.6, r=0.03)
    rail(B, [(x, y) for x, y in offset_poly(o2, 0.25)], z2 - 0.02, h=1.0, step=1.8, r=0.03, closed=True)
    xs = [lerp(22.2, H.bow_x() - 0.8, k / 4) for k in range(5)]
    for sgn in (-1, 1):
        rail(B, [(x, sgn * (H.at(x)[0] - 0.15), H.at(x)[1]) for x in xs], 0, h=1.05, step=1.5, r=0.03)
    zt = z3 + 2.62                                                            # swept mast + radar
    B.tube([(-1.0, 0, zt), (-2.6, 0, zt + 3.6), (-3.4, 0, zt + 5.2)], [0.35, 0.22, 0.1], "M_CWB_HullWhite", 6, cap1=True)
    B.box((-2.3, 0, zt + 3.4), (0.3, 3.0, 0.15), "M_CWB_HullWhite")
    return H


def tall_ship(B, sailing=False):
    """The four-masted gaff topsail schooner at Navy Pier (Windy, 1996; tallship/ photos): 148 ft (45 m) over all with the
    bowsprit, 36 m on the waterline, beam 7.6 m, white hull with a maroon sheer stripe, varnished bulwark cap, four
    raked wooden masts ~26 m above the deck with booms and gaffs; sails furled (docked) or set (sailing=True)."""
    bands = [(("deck", 0.0), "M_CWB_HullWhite", 0), (("deck", 0.15), "M_CWB_Maroon", 0), (("deck", 0.45), "M_CWB_HullWhite", 2),
             (("abs", 0.22), "M_CWB_HullBlack", 2)]
    H = Hull(B, 36.0, 7.6, 2.2, 1.75, 2.0, bands, "M_CWB_Teak", transom=0.55, rake=1.4, sq_mid=2.6, sq_bow=1.3, nst=24,
             stern_rake=-0.9)
    xs = [lerp(H.stern_x() + 0.05, H.bow_x() - 0.05, k / 23) for k in range(24)]
    for sgn in (-1, 1):                                                       # bulwarks 0.9 m, varnished cap rail
        prof = [(x, sgn * H.at(x)[0], H.at(x)[1]) for x in xs]
        inner = [(x, y - sgn * 0.12, z) for x, y, z in prof]
        for (a, b), (ai, bi) in zip(zip(prof, prof[1:]), zip(inner, inner[1:])):
            up = lambda p: (p[0], p[1], p[2] + 0.9)
            if sgn > 0:
                B.face([b, a, up(a), up(b)], "M_CWB_HullWhite")
                B.face([ai, bi, up(bi), up(ai)], "M_CWB_HullWhite")
            else:
                B.face([a, b, up(b), up(a)], "M_CWB_HullWhite")
                B.face([bi, ai, up(ai), up(bi)], "M_CWB_HullWhite")
        cap = [(x, sgn * (H.at(x)[0] - 0.06), H.at(x)[1] + 0.95) for x in xs]
        B.tube(cap, [0.08] * len(cap), "M_CWB_WoodSpar", 4, aspect=[(1.6, 0.6)] * len(cap))
    for x0, x1 in ((-12.0, -7.0), (1.0, 4.5)):                               # deckhouses
        zd = max(H.at(x0)[1], H.at(x1)[1])
        B.boxmm((x0, -1.4, zd - 0.1), (x1, 1.4, zd + 1.0), "M_CWB_Teak")
        B.boxmm((x0 - 0.1, -1.5, zd + 1.0), (x1 + 0.1, 1.5, zd + 1.08), "M_CWB_WoodSpar")
    bow = Vector((H.bow_x(), 0, H.fb_bow + 0.6))
    tip = bow + Vector((7.2, 0, 1.3))
    B.tube([bow - Vector((1.5, 0, 0.1)), tip], [0.22, 0.1], "M_CWB_WoodSpar", 6, cap1=True)    # bowsprit
    masts = [13.0, 5.0, -3.0, -11.0]
    heights = [24.5, 26.0, 26.0, 25.0]
    rake = math.radians(4.0)
    sails = []
    for k, (xm, hm) in enumerate(zip(masts, heights)):
        zd = H.at(xm)[1]
        top = Vector((xm - hm * math.sin(rake), 0, zd + hm))
        mid = Vector((xm - 0.72 * hm * math.sin(rake), 0, zd + 0.72 * hm))
        B.tube([(xm, 0, zd - 0.3), mid], [0.24, 0.19], "M_CWB_WoodSpar", 8)
        B.tube([mid - Vector((0, 0, 1.5)), top], [0.13, 0.07], "M_CWB_WoodSpar", 6, cap1=True)   # topmast
        B.box((mid.x, 0, mid.z), (0.9, 1.6, 0.12), "M_CWB_WoodSpar")               # crosstrees
        boom_len = 7.2 if k < 3 else 9.0
        zb = zd + 2.4
        gaff_z = zd + 0.6 * hm
        b0 = Vector((xm - 0.3, 0, zb))
        b1 = Vector((xm - 0.3 - boom_len, 0, zb + 0.4))
        g0 = Vector((xm - 0.6 * hm * math.sin(rake) - 0.25, 0, gaff_z))
        g1 = g0 + Vector((-boom_len * 0.85, 0, boom_len * 0.45))
        if sailing:
            yaw = math.radians(-18)
            R = Matrix.Rotation(yaw, 3, "Z")
            b1 = b0 + R @ (b1 - b0)
            g1 = g0 + R @ (g1 - g0)
        B.tube([b0, b1], [0.12, 0.09], "M_CWB_WoodSpar", 6, cap1=True)
        B.tube([g0, g1], [0.1, 0.07], "M_CWB_WoodSpar", 6, cap1=True)
        if sailing:
            sails.append([b0 + Vector((0, 0, 0.15)), b1 + Vector((0, 0, 0.15)), g1 - Vector((0, 0, 0.15)), g0 - Vector((0, 0, 0.2))])
            sails.append([g0 + Vector((0, 0, 0.3)), g1 + Vector((0, 0, 0.1)), top - Vector((0, 0, 0.6))])        # gaff topsail
        else:
            B.tube([b0.lerp(b1, 0.02) + Vector((0, 0, 0.3)), b0.lerp(b1, 0.5) + Vector((0, 0, 0.42)), b1 + Vector((0, 0, 0.3))],
                   [0.32, 0.36, 0.22], "M_CWB_Sail", 7, cap0=True, cap1=True)                                   # furled
        for sgn in (-1, 1):                                                   # shrouds to the channels
            for dx in (-0.8, 0.0, 0.8):
                B.tube([mid, (xm + dx, sgn * (H.at(xm + dx)[0] + 0.25), H.at(xm + dx)[1] + 0.9)], [0.018, 0.018], "M_CWB_Rope", 3)
        B.box((top.x, 0, top.z + 0.5), (0.02, 0.9, 0.6), "M_CWB_Seat")           # pennant
    B.tube([tip, Vector((masts[0] - 24.5 * math.sin(rake), 0, H.at(masts[0])[1] + 24.0))], [0.02, 0.02], "M_CWB_Rope", 3)
    for k in range(3):
        a = Vector((masts[k] - 0.72 * heights[k] * math.sin(rake), 0, H.at(masts[k])[1] + 0.72 * heights[k]))
        b = Vector((masts[k + 1] - 0.72 * heights[k + 1] * math.sin(rake), 0, H.at(masts[k + 1])[1] + 0.72 * heights[k + 1]))
        B.tube([a, b], [0.02, 0.02], "M_CWB_Rope", 3)                           # spring stays
    fore_top = Vector((masts[0] - 0.72 * heights[0] * math.sin(rake), 0, H.at(masts[0])[1] + 0.72 * heights[0]))
    for f in (0.0, 0.45, 0.85):                                               # three headsails (set) / stays (furled)
        a = bow.lerp(tip, f)
        b = fore_top.lerp(Vector((masts[0], 0, H.at(masts[0])[1] + 3.0)), f * 0.35)
        B.tube([a, b], [0.018, 0.018], "M_CWB_Rope", 3)
        if sailing:
            clew = Vector((masts[0] - 1.0, -1.6 - f, H.at(masts[0])[1] + 2.0 + f * 1.5))
            sails.append([a, b, clew])
    for S in sails:
        B.face(S, "M_CWB_Sail")
        B.face(S[::-1], "M_CWB_Sail")
    return H


def boats():
    jobs = [
        ("CW_Sloop", lambda B: sloop(B), "33 ft cruising sloop, sails furled (white hull)"),
        ("CW_SloopNavy", lambda B: sloop(B, "M_CWB_HullNavy"), "33 ft sloop, navy hull"),
        ("CW_SloopSailing", lambda B: sloop(B, sailing=True), "33 ft sloop under sail (main + jib set)"),
        ("CW_MotorYacht", motor_yacht, "45 ft flybridge motor yacht"),
        ("CW_TourBoat", tour_boat, "river architecture tour boat, 30 m"),
        ("CW_WaterTaxi", water_taxi, "yellow river water taxi, 20 m"),
        ("CW_Speedboat", speedboat, "Navy Pier thrill-ride speedboat, 21 m"),
        ("CW_CruiseShip", cruise_ship, "lakefront dinner cruise ship, 61 m"),
        ("CW_TallShip", lambda B: tall_ship(B), "four-masted schooner, sails furled, 45 m"),
        ("CW_TallShipSailing", lambda B: tall_ship(B, sailing=True), "four-masted schooner under sail"),
    ]
    for name, fn, desc in jobs:
        if ONLY and name not in ONLY:
            continue
        reset()
        B = Builder()
        H = fn(B)
        ob = B.finish(name, sharp_angle=40)
        if name == "CW_SloopSailing":
            ob.rotation_euler = (math.radians(-12), 0, 0)          # heeled to starboard under sail
        export(name, [ob], {"pivot": "waterline, mid-length; bow toward +X", "desc": desc,
                            "loa_m": round(H.bow_x() - H.stern_x(), 2), "beam_m": H.beam})


ONLY = None


# ================================================================== 2. one-off ship and small craft
def abegweit():
    """The Columbia Yacht Club's clubhouse: the retired icebreaking rail-car ferry Abegweit (1947), moored for good at the
    north end of Monroe Harbor (the plan's island x 1254-1368, y -410..-392 is her hull; columbia_yc/ photo, NAIP).
    LOA 113 m, beam 18.7 m, black hull with a red boot top, two white superstructure decks with rows of windows, bridge
    with wings, mast, lifeboats, portholes. Main deck 5.8 m above the water (= 0.3 m above the plan ground).
    Static materials (M_CW_*): she doesn't bob."""
    reset()
    B = Builder()
    bands = [(("deck", 0.0), "M_CW_ShipWhite", 0), (("deck", 0.25), "M_CW_ShipBlack", 3), (("abs", 0.6), "M_CW_ShipRed", 0),
             (("abs", 0.0), "M_CW_ShipRed", 2)]
    H = Hull(B, 106.5, 18.7, 6.6, 5.6, 2.0, bands, "M_CW_DockDeck", transom=0.72, rake=0.75, sq_mid=6.0, sq_bow=1.9, nst=28,
             stern_rake=0.4, forefoot=0.5)
    for x in [lerp(-44, 42, k / 34) for k in range(35)]:                       # portholes
        hb, zd = H.at(x)
        for sgn in (-1, 1):
            B.box((x, sgn * (hb + 0.02), zd - 1.7), (0.55, 0.06, 0.55), "M_GlassDark")
    zA = H.at(0)[1] - 0.05
    oA = H.outline(-46.0, 38.0, 0.9, n=18, round_fwd=0.8)
    house(B, [(zA, oA, "M_CW_ShipWhite"), (zA + 1.0, oA, "M_GlassDark"), (zA + 2.2, oA, "M_CW_ShipWhite"), (zA + 3.0, oA, None)],
          roof="M_CW_DockDeck", roof_over=0.4)
    windows_band(B, oA, zA + 1.0, zA + 2.2, 1.7, "M_CW_ShipWhite", w=0.3)
    zB = zA + 3.12
    oB = H.outline(-32.0, 24.0, 2.2, n=14, round_fwd=0.8)
    house(B, [(zB, oB, "M_CW_ShipWhite"), (zB + 0.9, oB, "M_GlassDark"), (zB + 2.0, oB, "M_CW_ShipWhite"), (zB + 2.8, oB, None)],
          roof="M_CW_DockDeck", roof_over=0.4)
    windows_band(B, oB, zB + 0.9, zB + 2.0, 1.7, "M_CW_ShipWhite", w=0.3)
    zC = zB + 2.92
    oC = H.outline(12.0, 22.0, 3.4, n=8, round_fwd=0.6)
    house(B, [(zC, oC, "M_CW_ShipWhite"), (zC + 1.0, oC, "M_GlassDark"), (zC + 2.1, oC, "M_CW_ShipWhite"), (zC + 2.7, oC, None)],
          roof="M_CW_ShipWhite", roof_over=0.5)
    B.boxmm((19.0, -9.2, zC + 0.9), (21.6, 9.2, zC + 1.1), "M_CW_ShipWhite")   # bridge wings
    rail(B, [(19.0, -9.2), (21.6, -9.2)], zC + 1.1, h=1.0, step=1.3, m="M_Railing")
    rail(B, [(19.0, 9.2), (21.6, 9.2)], zC + 1.1, h=1.0, step=1.3, m="M_Railing")
    B.tube([(8.0, 0, zC), (8.0, 0, zC + 12.0)], [0.25, 0.12], "M_CW_ShipWhite", 8, cap1=True)   # mast + yard
    B.tube([(8.0, -3.2, zC + 8.5), (8.0, 3.2, zC + 8.5)], [0.08, 0.08], "M_CW_ShipWhite", 6)
    rail(B, [(x, y) for x, y in offset_poly(oB, 0.3)], zB, h=1.05, step=2.0, m="M_Railing", closed=True)
    xs = [lerp(H.stern_x() + 0.6, -46.5, k / 3) for k in range(4)]
    for sgn in (-1, 1):
        rail(B, [(x, sgn * (H.at(x)[0] - 0.2), H.at(x)[1]) for x in xs], 0, h=1.05, step=2.0, m="M_Railing")
        for x in (-26.0, -16.0, 0.0, 10.0):                                    # lifeboats on davits
            y = sgn * (H.at(x)[0] - 1.6)
            B.ellipsoid((x, y, zB + 1.6), (3.6, 1.1, 0.7), "M_CWB_Orange", 12, 6)
            for dx in (-2.4, 2.4):
                B.tube([(x + dx, y - sgn * 1.0, zB), (x + dx, y - sgn * 1.0, zB + 3.0), (x + dx, y, zB + 3.2)], [0.08] * 3, "M_CW_ShipWhite", 4)
    ob = B.finish("CW_Abegweit", sharp_angle=40)
    export("CW_Abegweit", [ob], {"pivot": "waterline, mid-length; bow +X", "loa_m": round(H.bow_x() - H.stern_x(), 1), "beam_m": 18.7,
                                 "main_deck_above_water_m": round(H.at(0)[1], 2)})


def small_craft():
    """Tiki pontoon boat (river), kayak, mooring buoy, dock bollard, navigation light towers."""
    reset()
    B = Builder()                                                             # tiki boat: 5 m round pontoon, thatched roof
    B.lathe([(2.5, -0.3), (2.55, 0.25), (2.5, 0.42), (0.0, 0.42)], "M_CWB_HullWhite", 24)
    B.lathe([(2.42, 0.43), (0.0, 0.43)], "M_CWB_Teak", 24)
    for k in range(10):
        a = 2 * math.pi * k / 10
        B.box((1.15 * math.cos(a), 1.15 * math.sin(a), 0.95), (0.8, 0.25, 1.05), "M_CWB_Teak", Matrix.Rotation(a + math.pi / 2, 3, "Z"))
    B.lathe([(1.45, 1.48), (0.85, 1.48), (0.85, 1.52), (1.45, 1.52)], "M_CWB_Teak", 20)
    B.tube([(0, 0, 0.43), (0, 0, 2.7)], [0.12, 0.1], "M_CWB_Teak", 8)
    B.lathe([(2.9, 2.45), (2.6, 2.6), (1.4, 3.05), (0.0, 3.45)], "M_CWB_Thatch", 20)
    B.lathe([(0.0, 2.43), (2.9, 2.43)], "M_CWB_Thatch", 20)
    rail(B, [(2.25 * math.cos(2 * math.pi * k / 16), 2.25 * math.sin(2 * math.pi * k / 16)) for k in range(16)], 0.43, h=0.8,
         step=1.0, m="M_CWB_Steel", closed=True)
    export("CW_TikiBoat", [B.finish("CW_TikiBoat")], {"pivot": "waterline centre", "desc": "round tiki pontoon boat, 5 m"})
    reset()
    B = Builder()                                                             # kayak 4.2 m
    B.ellipsoid((0, 0, 0.05), (2.1, 0.33, 0.2), "M_CWB_Orange", 14, 6)
    B.ellipsoid((-0.1, 0, 0.2), (0.45, 0.24, 0.06), "M_CWB_HullBlack", 10, 3)
    export("CW_Kayak", [B.finish("CW_Kayak")], {"pivot": "waterline centre", "desc": "sit-in kayak 4.2 m"})
    reset()
    B = Builder()                                                             # mooring buoy
    B.lathe([(0.0, -0.25), (0.42, -0.1), (0.46, 0.15), (0.3, 0.42), (0.0, 0.46)], "M_CWB_HullWhite", 12)
    B.torus((0, 0, 0.52), 0.1, 0.025, "M_CWB_Steel", 8, 4, Matrix.Rotation(math.pi / 2, 3, "X"))
    B.lathe([(0.47, 0.02), (0.47, 0.12)], "M_CWB_Seat", 12)
    export("CW_MooringBuoy", [B.finish("CW_MooringBuoy")], {"pivot": "waterline centre", "desc": "mooring buoy"})
    reset()
    B = Builder()                                                             # dock bollard
    B.lathe([(0.18, 0.0), (0.14, 0.06), (0.12, 0.32), (0.2, 0.38), (0.2, 0.44), (0.0, 0.47)], "M_Railing", 10)
    export("CW_Bollard", [B.finish("CW_Bollard")], {"pivot": "base centre", "desc": "cast-iron mooring bollard 0.47 m"})
    for col, mname in (("Green", "M_CW_SignalGreen"), ("Red", "M_CW_SignalRed")):
        reset()
        B = Builder()                                                         # harbour light tower
        B.box((0, 0, 0.3), (2.4, 2.4, 0.6), "M_CW_LockConcrete")
        B.lathe([(0.62, 0.6), (0.55, 5.4), (0.0, 5.4)], "M_CW_WhiteWall", 16)
        B.lathe([(0.58, 4.0), (0.56, 5.3)], mname.replace("Signal", "Signal"), 16)
        B.lathe([(1.0, 5.4), (1.0, 5.5), (0.0, 5.5)], "M_CW_GateSteel", 16)
        B.torus((0, 0, 6.4), 0.95, 0.025, "M_Railing", 16, 4)
        for k in range(8):
            a = 2 * math.pi * k / 8
            B.tube([(0.95 * math.cos(a), 0.95 * math.sin(a), 5.5), (0.95 * math.cos(a), 0.95 * math.sin(a), 6.4)], [0.02, 0.02], "M_Railing", 4)
        B.lathe([(0.42, 5.5), (0.42, 6.5), (0.0, 6.5)], "M_Glass", 12)
        B.lathe([(0.2, 5.7), (0.2, 6.3), (0.0, 6.3)], mname, 8)
        B.lathe([(0.5, 6.5), (0.0, 7.1)], "M_CW_GateSteel", 12)
        export(f"CW_NavLight{col}", [B.finish(f"CW_NavLight{col}")], {"pivot": "base centre", "desc": f"harbour light, {col.lower()} band, 7 m"})


# ================================================================== 3. the Chicago Harbor Lock (site, plan frame)
LAYOUT = {}                       # positions computed here and used by the Unreal placement (water_layout.json)
LOCK_O = (1768.0, 96.0)           # site origin: middle of the chamber
LOCK_WALLS = {                    # OSM man_made=breakwater outlines of the lock's walls (ids) -> role
    925460353: "south lock wall", 925740530: "north lock wall + north pier", 925740529: "north wall east end",
    1491876770: "north pier head", 925460323: "south approach wall (west)", 925736498: "south guide wall (east)",
}
GATE_R, GATE_SWEEP, GATE_OPEN = 15.6, 55.0, 58.0
TOP = 0.06                        # wall tops 6 cm over the plan ground they overlap inside the map (x < 1723)


def feat_by_id(kind, i):
    return next(f for f in FEAT[kind] if f.get("id") == i)


def seg_dist(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def poly_dist(p, poly, closed=True):
    pts = list(poly) + ([poly[0]] if closed else [])
    return min(seg_dist(p, a, b) for a, b in zip(pts, pts[1:]))


def inside(poly, x, y):
    c = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def clean(poly):
    out = []
    for p in poly:
        if not out or math.dist(p, out[-1]) > 0.05:
            out.append(tuple(p))
    if len(out) > 2 and math.dist(out[0], out[-1]) < 0.05:
        out.pop()
    return out


def banded_slab(B, poly, z0, z1, bands, top):
    """Extrude a plan polygon from z0 to z1: top face + side walls split into horizontal bands [(z_from, z_to, mat)]."""
    poly = ccw(poly)
    n = len(poly)
    B.face([(x, y, z1) for x, y in poly], top, [(x, y) for x, y in poly])
    for i in range(n):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % n]
        L = math.hypot(bx - ax, by - ay)
        if L < 1e-6:
            continue
        for za, zb, m in bands:
            za, zb = max(za, z0), min(zb, z1)
            if zb > za:
                B.face([(ax, ay, za), (bx, by, za), (bx, by, zb), (ax, ay, zb)], m, [(0, za), (L, za), (L, zb), (0, zb)])


WALL_BANDS = [(BED, WATER + 0.7, "M_CW_WallDark"), (WATER + 0.7, 9.0, "M_CW_LockConcrete")]


def along(path, step, start=0.0):
    """Points every `step` metres along a polyline: [(x, y, tx, ty)]."""
    out = []
    d0 = start
    for a, b in zip(path, path[1:]):
        L = math.dist(a, b)
        if L < 1e-6:
            continue
        tx, ty = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        d = d0
        while d <= L:
            out.append((a[0] + tx * d, a[1] + ty * d, tx, ty))
            d += step
        d0 = d - L
    return out


def lock_geometry():
    """Wall outlines of the lock (plan metres, CCW). OSM maps only the walls' OUTER edges / planted strips (breakwater
    ways) and the chamber (water=lock); the walls themselves are the land between, so each outline is assembled from
    the OSM outer edge + the chamber face lines (fitted to the OSM chamber polygon) + the gate bays, which are cut as
    sectors round each gate pivot (radius GATE_R + 0.6) so the leaves can swing open into them."""
    ch = FEAT["lock"]["pts"]
    yS = lambda x: 83.23 + (86.97 - 83.23) * (x - 1685.88) / (1855.97 - 1685.88)     # chamber south face (OSM)
    yN = lambda x: 107.32 + (111.28 - 107.32) * (x - 1685.17) / (1855.26 - 1685.17)  # chamber north face (OSM)
    th_f = math.atan2(86.97 - 83.23, 1855.97 - 1685.88)
    piv = {}
    for g in FEAT["lock_gates"]:
        if "pts" in g:
            a, apex, c = g["pts"]
            for pv in (a, c):
                ang = math.atan2(apex[1] - pv[1], apex[0] - pv[0])
                piv[("in" if pv[0] < 1768 else "out", "N" if ang < 0 else "S")] = (tuple(pv), ang)
    Rb = GATE_R + 0.6
    sw = math.radians(GATE_SWEEP)
    op = math.radians(GATE_OPEN)

    def arc_pts(c, r, a0, a1, n=10):
        return [(c[0] + r * math.cos(a0 + (a1 - a0) * k / n), c[1] + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]

    def bay_S(key):
        (px, py), ang = piv[key]
        a_end = ang - op - sw - math.radians(3)
        pts = arc_pts((px, py), Rb, th_f, a_end)
        pts.append((px + 0.9 * math.cos(a_end), py + 0.9 * math.sin(a_end)))
        pts.append((px, py))
        return pts

    def bay_N(key):
        (px, py), ang = piv[key]
        a_end = ang + op + sw + math.radians(3)
        pts = [(px, py), (px + 0.9 * math.cos(a_end), py + 0.9 * math.sin(a_end))]
        pts += arc_pts((px, py), Rb, a_end, math.atan2(111.28 - 107.32, 1855.26 - 1685.17))
        return pts

    bw = lambda i: [tuple(p) for p in feat_by_id("breakwaters", i)["pts"]]
    s_out = [(1656.4, 65.8), (1675.7, 66.2), (1679.5, 70.5), (1689.4, 70.7), (1854.1, 74.4), (1854.2, 70.1), (1873.9, 70.5),
             (1878.0, 74.9), (1886.7, 75.2)]                                # OSM 925460353, its outer (south) edge
    S = s_out + [(1886.7, yS(1886.7))] + bay_S(("out", "S")) + bay_S(("in", "S")) + [(1656.3, yS(1656.3))]
    rnd = bw(925740529)                                                     # north wall's round east end (OSM)
    rnd = [p for p in rnd if p[0] > 1909.5]
    n_out = bw(925740530)                                                   # north wall outer edge + north pier east face
    quay = [(1654.0, 185.1), (1655.2, 130.5), (1655.7, 106.7), (1663.6, 106.8)]   # OSM quay 1491876771: north pier west face
    N = quay[1:] + bay_N(("in", "N")) + bay_N(("out", "N")) + [(1909.0, yN(1909.0))] + rnd + n_out + \
        [(1667.6, 191.5), (1666.8, 198.5), (1663.5, 203.8), (1659.8, 205.9), (1658.6, 205.9), (1654.0, 197.0), (1654.0, 185.1)]
    G = [(1886.7, 75.2), (2090.5, 79.7), (2093.2, 79.8), (2095.0, 80.3), (2096.3, 81.1), (2097.3, 82.2), (2098.1, 83.4), (2098.6, 84.8),
         (2098.7, 86.3), (2098.3, 87.8), (2097.7, 89.2), (2096.9, 90.2), (2095.9, 91.0), (2094.8, 91.5), (2093.3, 92.0), (2091.3, 92.1),
         (1886.7, yS(1886.7))]                                              # guide wall east (OSM 925736498 + its walkway)
    A = [(1470.5, 47.0), (1480.0, 45.8), (1516.0, 51.0), (1656.4, 65.8), (1656.3, yS(1656.3)), (1475.0, 57.0), (1472.0, 54.0)]
    rails = [s_out, G[:16], n_out[:-1] + [n_out[-1]], quay[::-1][::-1], [(1480.0, 45.8), (1516.0, 51.0), (1656.4, 65.8)],
             [(1656.3, yS(1656.3)), (1475.0, 57.0)], rnd]
    return {"S": S, "N": N, "G": G, "A": A, "yS": yS, "yN": yN, "piv": piv, "rails": rails}


def lock_site():
    """The Chicago Harbor Lock at the river mouth (USACE, 1938; chamber 600 x 80 ft between sector gates), on its OSM
    outlines (which match the NAIP aerial, Reference/ChicagoWater/aerials/aerial_naip_lock.jpg): the south lock wall,
    the north wall with the L-shaped north pier and its head, the approach wall west and the guide wall east (to the
    Southeast Guidewall Light); concrete from the lake bed to 6 cm over the plan ground (which already has these walls
    as land strips inside the map, x < 1723); chamber faces with rubber fenders, ladders, bollards and a yellow edge
    line; railings and lamps on the outer edges; planters on the south walls (the trees are the city's honey locusts,
    placed by the Unreal script); the operations building, the control tower (3 storeys + glazed control room +
    antenna; OSM height 20 m) and a store on the north wall; machinery houses at the four gate pivots; red/green lock
    signals. The four sector-gate leaves are separate meshes (CW_LockGateL/R), placed OPEN in their bays."""
    ox, oy = LOCK_O
    G = lock_geometry()
    B = PlanBuilder()
    for key in ("S", "N", "G", "A"):
        poly = clean(G[key])
        banded_slab(B, [(x - ox, y - oy) for x, y in offset_poly(poly, 0.03)], BED, TOP, WALL_BANDS, "M_CW_LockConcrete")
    yS, yN = G["yS"], G["yN"]
    # chamber faces between the gates: fenders, ladders, bollards, yellow coping line
    for yf, nrm in ((yS, 1.0), (yN, -1.0)):
        x0, x1 = 1688.0, 1856.0
        ang = math.atan2(yf(x1) - yf(x0), x1 - x0)
        rot = Matrix.Rotation(ang, 3, "Z")
        for k in range(int((x1 - x0) / 8.0)):
            x = x0 + 4.0 + 8.0 * k
            y = yf(x)
            zc = (WATER - 0.8 + TOP - 0.5) / 2
            B.box((x - ox, y + nrm * 0.18 - oy, zc), (0.5, 0.36, TOP - 0.5 - (WATER - 0.8)), "M_CW_Fender", rot)
            if k % 4 == 2:
                lx = x + 4.0
                ly = yf(lx)
                for s_ in (-0.25, 0.25):
                    B.box((lx + s_ - ox, ly + nrm * 0.1 - oy, (WATER - 1.0 + TOP) / 2), (0.06, 0.06, TOP - WATER + 1.0), "M_CW_GateSteel")
                zr = WATER - 0.6
                while zr < TOP - 0.1:
                    B.box((lx - ox, ly + nrm * 0.1 - oy, zr), (0.5, 0.04, 0.04), "M_CW_GateSteel")
                    zr += 0.35
            if k % 2 == 0:
                B.lathe([(0.18, TOP), (0.14, TOP + 0.06), (0.12, TOP + 0.32), (0.2, TOP + 0.38), (0.2, TOP + 0.44), (0.0, TOP + 0.47)],
                        "M_Railing", 8, center=(x - ox, y - nrm * 0.9 - oy, 0))
        B.beam((x0 - ox, yf(x0) - nrm * 0.3 - oy, TOP + 0.004), (x1 - ox, yf(x1) - nrm * 0.3 - oy, TOP + 0.004), 0.2, 0.01, "M_CW_SafetyYellow")
    # railings + lamps on the outer edges (each rail path runs with the wall on its left)
    lamps = []
    for path in G["rails"]:
        for a, b in zip(path, path[1:]):
            L = math.dist(a, b)
            if L < 0.5:
                continue
            tx, ty = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            ix, iy = -ty * 0.35, tx * 0.35
            B.railing([(a[0] + ix - ox, a[1] + iy - oy), (b[0] + ix - ox, b[1] + iy - oy)], TOP, h=1.07, step=2.4, m="M_Railing")
        for (x, y, tx, ty) in along(path, 32.0, 10.0):
            lamps.append((x - ty * 1.6, y + tx * 1.6))
    for x, y in lamps:
        B.tube([(x - ox, y - oy, TOP), (x - ox, y - oy, TOP + 6.0)], [0.09, 0.06], "M_Railing", 6, cap1=True)
        B.box((x - ox, y - oy, TOP + 5.95), (0.6, 0.6, 0.18), "M_Railing")
        B.box((x - ox, y - oy, TOP + 5.83), (0.5, 0.5, 0.06), "M_Light")
    LAYOUT["lock_lamps"] = [[round(x, 2), round(y, 2)] for x, y in lamps]
    # planters on the south walls' planted strip (2.4 m in from the outer edge), trees in every other one
    trees = []
    south = [clean(G["A"]), clean(G["S"]), clean(G["G"])]
    for x in range(1490, 2088, 9):
        if 1650 < x < 1700 or 1846 < x < 1892:
            continue
        ys = []
        for poly in south:
            n = len(poly)
            for i in range(n):
                (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
                if (x1 <= x < x2) or (x2 <= x < x1):
                    ys.append(y1 + (y2 - y1) * (x - x1) / (x2 - x1))
        if len(ys) < 2 or max(ys) - min(ys) < 6.0:
            continue
        yc = min(ys) + 2.4
        B.boxmm((x - 2.0 - ox, yc - 0.8 - oy, TOP), (x + 2.0 - ox, yc + 0.8 - oy, TOP + 0.5), "M_CW_LockConcrete")
        B.boxmm((x - 1.85 - ox, yc - 0.65 - oy, TOP + 0.5), (x + 1.85 - ox, yc + 0.65 - oy, TOP + 0.62), "M_Hedge")
        if (x // 9) % 2 == 0:
            trees.append([round(x, 2), round(yc, 2)])
    LAYOUT["lock_trees"] = trees

    def bldg(x0, x1, y0, y1, h, glass_band=(1.1, 2.4), roof="M_RoofFlat"):
        B.boxmm((x0 - ox, y0 - oy, TOP), (x1 - ox, y1 - oy, TOP + glass_band[0]), "M_CW_WhiteWall")
        B.boxmm((x0 + 0.05 - ox, y0 + 0.05 - oy, TOP + glass_band[0]), (x1 - 0.05 - ox, y1 - 0.05 - oy, TOP + glass_band[1]), "M_GlassDark")
        B.boxmm((x0 - ox, y0 - oy, TOP + glass_band[1]), (x1 - ox, y1 - oy, TOP + h), "M_CW_WhiteWall")
        B.boxmm((x0 - 0.3 - ox, y0 - 0.3 - oy, TOP + h), (x1 + 0.3 - ox, y1 + 0.3 - oy, TOP + h + 0.25), roof)
    bldg(1748.0, 1786.0, 111.6, 119.2, 4.4)                                  # operations building
    bldg(1804.0, 1820.0, 112.2, 119.0, 3.6)                                  # store
    tx0, tx1, ty0, ty1 = 1787.0, 1797.0, 111.2, 120.6                        # control tower
    B.boxmm((tx0 - ox, ty0 - oy, TOP), (tx1 - ox, ty1 - oy, TOP + 7.6), "M_CW_WhiteWall")
    for zz in (2.6, 5.4):
        B.boxmm((tx0 - 0.04 - ox, ty0 - 0.04 - oy, TOP + zz), (tx1 + 0.04 - ox, ty1 + 0.04 - oy, TOP + zz + 1.1), "M_GlassDark")
    B.boxmm((tx0 - 0.6 - ox, ty0 - 0.6 - oy, TOP + 7.6), (tx1 + 0.6 - ox, ty1 + 0.6 - oy, TOP + 7.85), "M_CW_WhiteWall")
    B.boxmm((tx0 - 0.3 - ox, ty0 - 0.3 - oy, TOP + 7.85), (tx1 + 0.3 - ox, ty1 + 0.3 - oy, TOP + 10.9), "M_GlassDark")
    for cx, cy in ((tx0 - 0.3, ty0 - 0.3), (tx1 + 0.3, ty0 - 0.3), (tx1 + 0.3, ty1 + 0.3), (tx0 - 0.3, ty1 + 0.3)):
        B.box((cx - ox, cy - oy, TOP + 9.4), (0.18, 0.18, 3.1), "M_CW_WhiteWall")
    B.boxmm((tx0 - 0.8 - ox, ty0 - 0.8 - oy, TOP + 10.9), (tx1 + 0.8 - ox, ty1 + 0.8 - oy, TOP + 11.3), "M_RoofFlat")
    B.railing([(tx0 - 0.6 - ox, ty0 - 0.6 - oy), (tx1 + 0.6 - ox, ty0 - 0.6 - oy), (tx1 + 0.6 - ox, ty1 + 0.6 - oy), (tx0 - 0.6 - ox, ty1 + 0.6 - oy)],
              TOP + 7.85, h=1.0, step=1.5, closed=True)
    cxm, cym = (tx0 + tx1) / 2 - ox, (ty0 + ty1) / 2 - oy
    B.tube([(cxm, cym, TOP + 11.3), (cxm, cym, TOP + 20.0)], [0.12, 0.05], "M_CW_GateSteel", 6, cap1=True)
    B.tube([(cxm - 1.2, cym, TOP + 15.5), (cxm + 1.2, cym, TOP + 15.5)], [0.04, 0.04], "M_CW_GateSteel", 4)
    gates = []
    for (which, side), ((px, py), ang) in sorted(G["piv"].items()):
        angd = math.degrees(ang)
        kind = "L" if side == "N" else "R"
        opened = angd + (GATE_OPEN if kind == "L" else -GATE_OPEN)
        gates.append({"pivot": [round(px, 2), round(py, 2)], "kind": kind, "closed_deg": round(angd, 2), "open_deg": round(opened, 2),
                      "gate": "inner (river)" if which == "in" else "outer (lake)"})
        # machinery house on the wall beside the pivot, away from the bay
        hx = px + (-2.0 if which == "in" else -3.5)
        hy = py + (4.6 if side == "N" else -4.6)
        B.boxmm((hx - 1.6 - ox, hy - 1.6 - oy, TOP), (hx + 1.6 - ox, hy + 1.6 - oy, TOP + 2.7), "M_CW_WhiteWall")
        B.boxmm((hx - 1.8 - ox, hy - 1.8 - oy, TOP + 2.7), (hx + 1.8 - ox, hy + 1.8 - oy, TOP + 2.9), "M_RoofFlat")
        # lock signal facing the approach (river side west of the inner gate, lake side east of the outer gate)
        sgx = px - 9.0 if which == "in" else px + GATE_R + 3.0
        sgy = (yN(sgx) + 2.2) if side == "N" else (yS(sgx) - 2.2)
        face = -1.0 if which == "in" else 1.0
        B.tube([(sgx - ox, sgy - oy, TOP), (sgx - ox, sgy - oy, TOP + 4.2)], [0.08, 0.08], "M_CW_GateSteel", 6)
        B.box((sgx - ox, sgy - oy, TOP + 3.7), (0.5, 0.5, 1.1), "M_CW_GateSteel")
        for zz, mm in ((TOP + 4.0, "M_CW_SignalRed"), (TOP + 3.45, "M_CW_SignalGreen")):
            B.box((sgx + face * 0.27 - ox, sgy - oy, zz), (0.04, 0.3, 0.3), mm)
    LAYOUT["lock_gates"] = gates
    LAYOUT["lock_origin"] = list(LOCK_O)
    LAYOUT["lock_outlines"] = {k: [[round(x, 2), round(y, 2)] for x, y in clean(G[k])] for k in ("S", "N", "G", "A")}
    ob = B.finish("CW_ChicagoLock", sharp_angle=40)
    site_export("CW_ChicagoLock", ob, {"pivot": "plan %s (chamber middle), plan ground" % (LOCK_O,), "osm_ways": LOCK_WALLS,
                                       "chamber": "OSM water=lock polygon w762092241 (x 1664-1871), gates at x 1673 / 1871",
                                       "top_m": TOP, "bed_m": BED})


def lock_gate(kind):
    """One sector-gate leaf (plan frame, PIVOT AT THE ORIGIN, closing arm along +x): a curved skin plate of radius
    GATE_R swept GATE_SWEEP degrees (CCW for 'L' = north leaves, CW for 'R' = south leaves), three horizontal girders,
    radial truss arms to the pivot column, a grated walkway with railings on top. Lake bed to 0.35 m over the ground."""
    reset()
    B = PlanBuilder()
    R, sw = GATE_R, math.radians(GATE_SWEEP)
    a0, a1 = (0.0, sw) if kind == "L" else (-sw, 0.0)
    zt = 0.25
    seg = 14
    B.lathe([(R, BED), (R, zt), (R - 0.35, zt), (R - 0.35, BED), (R, BED)], "M_CW_GateSteel", seg, a0=a0, a1=a1, smooth=False)
    for ang in (a0, a1):                                                      # end plates of the skin
        c, s_ = math.cos(ang), math.sin(ang)
        pts = [(R * c, R * s_, BED), (R * c, R * s_, zt), ((R - 0.35) * c, (R - 0.35) * s_, zt), ((R - 0.35) * c, (R - 0.35) * s_, BED)]
        B.face(pts if ang == a1 else pts[::-1], "M_CW_GateSteel")
        B.face(pts[::-1] if ang == a1 else pts, "M_CW_GateSteel")
    for z in (-0.6, -2.6, -4.6, -6.8):                                       # horizontal girders behind the skin
        B.lathe([(R - 1.2, z), (R - 0.35, z), (R - 0.35, z + 0.25), (R - 1.2, z + 0.25), (R - 1.2, z)], "M_CW_GateSteel", seg, a0=a0, a1=a1, smooth=False)
    B.cyl((0, 0, BED), zt + 0.1 - BED, 0.7, "M_CW_GateSteel", 12)              # pivot column
    arms = [a0, (a0 + a1) / 2, a1]
    for ang in arms:                                                          # radial truss arms (top + bottom chords, diagonals)
        c, s_ = math.cos(ang), math.sin(ang)
        p = lambda r, z: (r * c, r * s_, z)
        B.beam(p(0.6, -0.4), p(R - 1.2, -0.4), 0.35, 0.5, "M_CW_GateSteel")
        B.beam(p(0.6, -4.4), p(R - 1.2, -4.4), 0.35, 0.5, "M_CW_GateSteel")
        for k in range(4):
            r0 = 0.6 + (R - 1.8) * k / 4
            r1 = 0.6 + (R - 1.8) * (k + 1) / 4
            B.beam(p(r0, -4.4), p(r1, -0.4), 0.22, 0.22, "M_CW_GateSteel")
            B.beam(p(r1, -4.4), p(r1, -0.4), 0.22, 0.22, "M_CW_GateSteel")
    for (u, v) in ((arms[0], arms[1]), (arms[1], arms[2])):                    # top bracing between arms
        for f0, f1 in ((0.35, 0.9), (0.9, 0.35)):
            B.beam((R * f0 * math.cos(u), R * f0 * math.sin(u), -0.3), (R * f1 * math.cos(v), R * f1 * math.sin(v), -0.3), 0.18, 0.18, "M_CW_GateSteel")
    # walkway along the skin + along the closing arm, with railings
    B.lathe([(R - 1.5, zt), (R - 0.3, zt), (R - 0.3, zt + 0.1), (R - 1.5, zt + 0.1), (R - 1.5, zt)], "M_CW_GateSteel", seg, a0=a0, a1=a1, smooth=False)
    for rr in (R - 1.45, R - 0.35):
        pts = [(rr * math.cos(a0 + (a1 - a0) * k / seg), rr * math.sin(a0 + (a1 - a0) * k / seg)) for k in range(seg + 1)]
        B.railing(pts, zt + 0.1, h=1.07, step=1.6, m="M_Railing")
    arm = a0 if kind == "L" else a1
    c, s_ = math.cos(arm), math.sin(arm)
    nx, ny = (-s_, c) if kind == "L" else (s_, -c)                            # into the leaf
    B.beam((0.7 * c + nx * 0.6, 0.7 * s_ + ny * 0.6, zt + 0.05), ((R - 1.5) * c + nx * 0.6, (R - 1.5) * s_ + ny * 0.6, zt + 0.05), 1.1, 0.1, "M_CW_GateSteel")
    B.railing([(0.7 * c + nx * 1.15, 0.7 * s_ + ny * 1.15), ((R - 1.5) * c + nx * 1.15, (R - 1.5) * s_ + ny * 1.15)], zt + 0.1, h=1.07, step=1.6)
    name = "CW_LockGate" + kind
    ob = B.finish(name, sharp_angle=40)
    site_export(name, ob, {"pivot": "the leaf's vertical pivot axis, plan ground; closing arm along plan +x",
                           "radius_m": R, "sweep_deg": GATE_SWEEP, "sweep_dir": "CCW (north leaves)" if kind == "L" else "CW (south leaves)",
                           "unreal_yaw": "-(plan angle of the closing arm), see water_layout.json lock_gates"})


def lock():
    lock_site()
    lock_gate("L")
    lock_gate("R")


# ================================================================== 4. harbour docks + boat slots (sites, plan frame)
HARBOURS = {
    # area: (site origin, main-walkway min length, finger width, main width, plan water ring (bbox to find it))
    "dusable": ((1356.0, -212.0), 60.0, 0.9, 2.4, (1246, 1465, -385, -41)),
    "navypier_marina": ((1860.0, 560.0), 150.0, 1.5, 2.6, (1021, 1723, -1968, 1624)),
    "monroe": ((1100.0, -700.0), 60.0, 1.0, 2.4, (935, 1467, -1968, -384)),
    "lock": ((1426.0, 6.0), 999.0, 1.4, 2.0, (16.6, 1673, -33, 340)),
    "river": ((950.0, 190.0), 999.0, 2.4, 2.4, (16.6, 1673, -33, 340)),
}
DECK_Z, FLOAT_Z = WATER + 0.5, WATER - 0.3
MAX_AREA_PERIM = 400.0           # closed "pier" areas bigger than this are breakwaters / land already in the plan


def plan_ring(bb):
    for ring in PLAN["water"]["outer"]:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        if abs(min(xs) - bb[0]) < 1.5 and abs(max(xs) - bb[1]) < 1.5 and abs(min(ys) - bb[2]) < 1.5 and abs(max(ys) - bb[3]) < 1.5:
            return ring
    return None


def plen(pts):
    return sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))


def proj_on(path, p):
    """(distance, arc length s, point, tangent) of the closest point of polyline path to p."""
    best = (1e9, 0.0, None, None)
    acc = 0.0
    for a, b in zip(path, path[1:]):
        L = math.dist(a, b)
        if L < 1e-6:
            continue
        tx, ty = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        t = max(0.0, min(L, (p[0] - a[0]) * tx + (p[1] - a[1]) * ty))
        q = (a[0] + tx * t, a[1] + ty * t)
        d = math.dist(p, q)
        if d < best[0]:
            best = (d, acc + t, q, (tx, ty))
        acc += L
    return best


def at_s(path, s):
    acc = 0.0
    for a, b in zip(path, path[1:]):
        L = math.dist(a, b)
        if L < 1e-6:
            continue
        if acc + L >= s:
            t = (s - acc) / L
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        acc += L
    a, b = path[-2], path[-1]
    L = max(1e-6, math.dist(a, b))
    return tuple(b), ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


def dock_strip(B, path, w, z_top, ox, oy, deck="M_CW_DockDeck", side="M_CW_Float"):
    P = [(x - ox, y - oy) for x, y in path]
    hw = w / 2
    B.sweep_open(P, [(-hw, FLOAT_Z), (-hw, z_top)], side)
    B.sweep_open(P, [(-hw, z_top), (hw, z_top)], deck)
    B.sweep_open(P, [(hw, z_top), (hw, FLOAT_Z)], side)
    for (a, b), sgn in (((P[0], P[1]), -1), ((P[-1], P[-2]), -1)):
        L = math.dist(a, b)
        tx, ty = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = -ty * hw, tx * hw
        B.face([(a[0] - nx, a[1] - ny, FLOAT_Z), (a[0] - nx, a[1] - ny, z_top), (a[0] + nx, a[1] + ny, z_top), (a[0] + nx, a[1] + ny, FLOAT_Z)], side)


def gangway(B, top, bottom, w, ox, oy):
    """Sloped aluminium gangway with railings from a quay point (z 0) to a dock point (deck height)."""
    (x0, y0, z0), (x1, y1, z1) = top, bottom
    L = math.hypot(x1 - x0, y1 - y0)
    tx, ty = (x1 - x0) / L, (y1 - y0) / L
    nx, ny = -ty * w / 2, tx * w / 2
    P = [(x0 - nx - ox, y0 - ny - oy, z0 + 0.04), (x1 - nx - ox, y1 - ny - oy, z1 + 0.04), (x1 + nx - ox, y1 + ny - oy, z1 + 0.04), (x0 + nx - ox, y0 + ny - oy, z0 + 0.04)]
    B.face(P, "M_CW_GateSteel")
    B.face(P[::-1], "M_CW_GateSteel")
    for sg in (-1, 1):
        a = (x0 + sg * nx - ox, y0 + sg * ny - oy, z0 + 0.04)
        b = (x1 + sg * nx - ox, y1 + sg * ny - oy, z1 + 0.04)
        rail(B, [a, b], 0, h=1.0, step=2.0, m="M_Railing", r=0.025, mid=True, post=0.04)


def harbour(area):
    """Floating docks of one harbour from its OSM man_made=pier ways (DuSable Harbor's seven 150-165 m walkways with
    their cross-fingers, the Navy Pier Marina's main walkway and 56 m diagonal fingers, the Chicago / Columbia yacht club
    docks and the tender pier in Monroe Harbor, the police / Coast Guard docks at the river mouth, the kayak launch and the
    Ogden Slip dock): walkways 2.4-2.6 m, fingers 0.9-1.5 m, decks 0.5 m over the water on white floats, guide piles,
    utility pedestals, gangways down from the quay. Also computes the boat slots between the fingers (water_layout.json)."""
    origin, main_min, fw, mw, ring_bb = HARBOURS[area]
    ox, oy = origin
    ring = plan_ring(ring_bb)
    B = PlanBuilder()
    piers = [p for p in FEAT["piers"] if p["area"] == area]
    mains, fingers = [], []
    for p in piers:
        pts = [tuple(q) for q in p["pts"]]
        L = plen(pts)
        if p["is_area"]:
            if L > MAX_AREA_PERIM or len(pts) > 18 and L < 30:          # big = land/breakwater; 20-point circles = dolphins
                if L <= 30:
                    c = (sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts))
                    B.cyl((c[0] - ox, c[1] - oy, BED), 3.2 - BED, 1.2, "M_CW_Piling", 10)     # mooring dolphin
                continue
            poly = clean(pts)
            if len(poly) < 3:
                continue
            fixed = p["floating"] == "no"
            zt = WATER + 1.5 if fixed else DECK_Z
            banded_slab(B, [(x - ox, y - oy) for x, y in poly], FLOAT_Z if not fixed else BED, zt,
                        [(BED, zt, "M_CW_Piling" if fixed else "M_CW_Float")], "M_CW_DockDeck")
            continue
        (mains if L >= main_min else fingers).append(pts)
    for m in mains:
        dock_strip(B, m, mw, DECK_Z, ox, oy)
        for k, (x, y, tx, ty) in enumerate(along(m, 18.0, 6.0)):
            sg = 1 if k % 2 else -1
            px, py = x - ty * sg * (mw / 2 + 0.3), y + tx * sg * (mw / 2 + 0.3)
            B.cyl((px - ox, py - oy, BED), WATER + 2.5 - BED, 0.2, "M_CW_Piling", 8)
            B.cyl((px - ox, py - oy, WATER + 2.5), 0.12, 0.23, "M_CW_Buoy", 8)
        for (x, y, tx, ty) in along(m, 12.0, 3.0):
            B.box((x - ox, y - oy, DECK_Z + 0.45), (0.32, 0.32, 0.9), "M_CW_WhiteWall")
            B.box((x - ox, y - oy, DECK_Z + 0.93), (0.26, 0.26, 0.06), "M_Light")
        if ring:
            for end, nxt in ((m[0], m[1]), (m[-1], m[-2])):
                d, _s, q, _t = proj_on(list(ring) + [ring[0]], end)
                if d < 9.0:
                    L = math.dist(end, nxt)
                    tx, ty = (nxt[0] - end[0]) / L, (nxt[1] - end[1]) / L
                    gangway(B, (q[0] - tx * 0.6, q[1] - ty * 0.6, 0.0), (end[0] + tx * (14.0 - d), end[1] + ty * (14.0 - d), DECK_Z), 1.4, ox, oy)
    for f in fingers:
        dock_strip(B, f, fw, DECK_Z - 0.02, ox, oy)
        tip = f[-1]
        B.cyl((tip[0] - ox, tip[1] - oy, BED), WATER + 1.8 - BED, 0.16, "M_CW_Piling", 8)
    if area == "river":                                                        # boarding pontoons + gangways at the berths
        for b in LAYOUT.get("river_berths", []):
            (wx, wy), (tx, ty), (nx, ny) = b["wall"], b["t"], b["n"]
            c0 = (wx + nx * 1.5 - tx * 6.0, wy + ny * 1.5 - ty * 6.0)
            c1 = (wx + nx * 1.5 + tx * 6.0, wy + ny * 1.5 + ty * 6.0)
            dock_strip(B, [c0, c1], 2.6, DECK_Z, ox, oy)
            gangway(B, (wx - nx * 0.6 - tx * 9.0, wy - ny * 0.6 - ty * 9.0, 0.0), (wx + nx * 0.9 + tx * 3.0, wy + ny * 0.9 + ty * 3.0, DECK_Z), 1.3, ox, oy)
            for f in (-5.0, 5.0):
                B.cyl((wx + nx * 3.0 + tx * f - ox, wy + ny * 3.0 + ty * f - oy, BED), WATER + 2.2 - BED, 0.2, "M_CW_Piling", 8)
    for mo in FEAT["moorings"]:                                                # pile moorings (DuSable)
        if mo["area"] == area and mo["cat"] == "pile":
            B.cyl((mo["x"] - ox, mo["y"] - oy, BED), WATER + 1.6 - BED, 0.15, "M_CW_Piling", 8)
    # boat slots between fingers, each side of each main
    rnd = random.Random(hash(area) & 0xffff)
    slots = []
    for m in mains:
        att = {1: [], -1: []}
        for f in fingers:
            best = min(((proj_on(m, q), q) for q in f), key=lambda t: t[0][0])
            (d, s_, q0, (tx, ty)), qa = best
            if d > 1.8:
                continue
            for e in f:
                v = (e[0] - q0[0], e[1] - q0[1])
                ln = math.hypot(*v)
                if ln < 3.0:
                    continue
                side = 1 if tx * v[1] - ty * v[0] > 0 else -1
                att[side].append((s_, ln, (v[0] / ln, v[1] / ln)))
        for side, lst in att.items():
            lst.sort()
            for (s0, l0, d0), (s1, l1, d1) in zip(lst, lst[1:]):
                g = s1 - s0
                n_b = 1 if 3.2 <= g <= 9.5 else (2 if 9.5 < g <= 17.0 else (int(g / 26.0) + 1 if area == "navypier_marina" and g > 17 else 0))
                if n_b == 0:
                    continue
                dx_, dy_ = (d0[0] + d1[0]) / 2, (d0[1] + d1[1]) / 2
                dn = math.hypot(dx_, dy_)
                dx_, dy_ = dx_ / dn, dy_ / dn
                for k in range(n_b):
                    if rnd.random() < 0.1:
                        continue
                    sm = s0 + g * (k + 0.5) / n_b
                    base, _tan = at_s(m, sm)
                    blen = min(l0, l1) * (0.95 if area != "navypier_marina" else 0.55) + rnd.uniform(-0.8, 0.8)
                    blen = max(7.0, min(blen, 30.0))
                    off = (mw / 2 + 0.5 + blen / 2) if area != "navypier_marina" else (mw / 2 + 2.0 + blen / 2)
                    cx, cy = base[0] + dx_ * off, base[1] + dy_ * off
                    if area == "navypier_marina":                         # slips between diagonal fingers: offset across
                        cx += (dy_ if side < 0 else -dy_) * 0.0
                    h = math.degrees(math.atan2(dy_, dx_)) + (180.0 if rnd.random() < 0.5 else 0.0)
                    if area == "navypier_marina":
                        kind = "CW_MotorYacht"
                    else:
                        r = rnd.random()
                        kind = "CW_Sloop" if r < 0.55 else ("CW_SloopNavy" if r < 0.65 else "CW_MotorYacht")
                    slots.append({"x": round(cx, 2), "y": round(cy, 2), "h": round(h, 1), "len": round(blen, 2), "type": kind})
    LAYOUT["slots_" + area] = slots
    LAYOUT["origin_" + area] = list(origin)
    name = "CW_Docks_" + "".join(w.capitalize() for w in area.split("_"))
    ob = B.finish(name, sharp_angle=40)
    site_export(name, ob, {"pivot": "plan %s, plan ground" % (origin,), "osm_area": area, "mains": len(mains), "fingers": len(fingers),
                           "boat_slots": len(slots), "deck_m": DECK_Z})


def harbour_extras():
    """Boat positions that don't come from finger slips (water_layout.json): Monroe Harbor's mooring field (one boat per
    OSM mooring buoy, all lying to the same breeze), the excursion ships along Navy Pier's south dock (OSM berths, in
    order, kept apart), the river tour-boat / water-taxi berths on the Chicago side (OSM ferry terminals; a boarding
    pontoon + gangway each, built into CW_Docks_River), tiki boats, kayaks, boats in the lock chamber (NAIP), boats
    under way on the river and the lake, the Abegweit on her island, harbour lights."""
    rnd = random.Random(42)
    moor = []
    for mo in FEAT["moorings"]:
        if mo["area"] == "monroe" and mo["cat"] == "buoy":
            h = 78.0 + rnd.uniform(-9, 9)
            r = rnd.random()
            kind = "CW_Sloop" if r < 0.8 else ("CW_SloopNavy" if r < 0.88 else "CW_MotorYacht")
            blen = rnd.uniform(8.5, 12.5) if kind != "CW_MotorYacht" else rnd.uniform(10.0, 14.0)
            hr = math.radians(h)
            cx, cy = mo["x"] - math.cos(hr) * (blen / 2 + 2.0), mo["y"] - math.sin(hr) * (blen / 2 + 2.0)
            moor.append({"buoy": [mo["x"], mo["y"]], "x": round(cx, 2), "y": round(cy, 2), "h": round(h, 1), "len": round(blen, 2), "type": kind,
                         "empty": rnd.random() < 0.08})
    LAYOUT["monroe_moorings"] = moor
    # Navy Pier south dock (deck edge y = 383 in LM_NavyPierDeck): ships in OSM berth order, pushed apart
    want = [("Shoreline I", "CW_TourBoat", 0.85), ("Shoreline II", "CW_TourBoat", 0.85), ("Odyssey", "CW_CruiseShip", 1.0),
            ("Windy", "CW_TallShip", 1.0), ("Chicago Elite", "CW_MotorYacht", 2.4), ("Spirit of Chicago", "CW_CruiseShip", 0.87),
            ("Spirit of Navy Pier", "CW_CruiseShip", 0.75), ("Shoreline", "CW_TourBoat", 0.85)]
    at = {"Odyssey": 1826.0}                                                  # NAIP: the Odyssey lies at x 1795-1855
    lens = {"CW_TourBoat": 29.3, "CW_Speedboat": 21.6, "CW_CruiseShip": 60.2, "CW_TallShip": 48.6, "CW_MotorYacht": 16.35, "CW_WaterTaxi": 19.4}
    beams = {"CW_TourBoat": 7.9, "CW_Speedboat": 5.4, "CW_CruiseShip": 12.4, "CW_TallShip": 8.1, "CW_MotorYacht": 4.4, "CW_WaterTaxi": 5.8}
    ber = {b["name"]: b for b in FEAT["berths"]}
    ships = []
    last_end = 1540.0
    for nm, kind, sc in want:
        b = ber.get(nm)
        if not b:
            continue
        L = lens[kind] * sc
        cx = max(at.get(nm, b["x"]), last_end + 4.0 + L / 2)
        last_end = cx + L / 2
        ships.append({"name": nm, "type": kind, "scale": sc, "x": round(cx, 2), "y": round(383.0 - 1.0 - beams[kind] * sc / 2, 2),
                      "h": 0.0 if len(ships) % 2 else 180.0})
    for nm in ("Seadog I", "Seadog II", "Seadog III", "Seadog IV"):          # moored bow-in, side by side (NAIP)
        b = ber.get(nm)
        if b:
            ships.append({"name": nm, "type": "CW_Speedboat", "scale": 1.0, "x": round(b["x"], 2), "y": round(383.0 - 0.8 - 21.6 / 2, 2), "h": 90.0})
    LAYOUT["navypier_ships"] = ships
    # river berths (Chicago side of the seam)
    seam = PLAN["seam"]

    def chicago_side(x, y):
        for (x1, y1), (x2, y2) in zip(seam, seam[1:]):
            if x1 <= x <= x2:
                return y < y1 + (y2 - y1) * (x - x1) / max(1e-6, x2 - x1)
        return True
    river_ring = plan_ring(HARBOURS["river"][4])
    rr = list(river_ring) + [river_ring[0]]
    berths = []
    for b in FEAT["berths"]:
        if not (220 <= b["x"] <= 1400 and -40 <= b["y"] <= 345) or not chicago_side(b["x"], b["y"]):
            continue
        nm, op = b["name"], b["operator"]
        if "Kayak" in nm or "Kyak" in nm:
            continue
        d, _s, q, (tx, ty) = proj_on(rr, (b["x"], b["y"]))
        nx, ny = -ty, tx
        if not inside(river_ring, q[0] + nx * 3, q[1] + ny * 3):
            nx, ny = -nx, -ny
        if "Tiki" in nm:
            kind, sc = "CW_TikiBoat", 1.0
        elif "Water Taxi" in op or nm in ("Michigan Avenue",) or "Navy Pier (River" in nm:
            kind, sc = "CW_WaterTaxi", 1.0
        elif "Anita Dee" in nm:
            kind, sc = "CW_MotorYacht", 1.9
        elif "Mercury" in nm or "Wendella" in nm:
            kind, sc = "CW_TourBoat", 0.78
        elif "Shoreline" in nm:
            kind, sc = "CW_TourBoat", 0.85
        else:
            kind, sc = "CW_TourBoat", 1.0
        beam = {"CW_TikiBoat": 5.8}.get(kind, beams.get(kind, 6.0) * sc)
        berths.append({"name": nm, "type": kind, "scale": sc, "wall": [round(q[0], 2), round(q[1], 2)], "t": [round(tx, 4), round(ty, 4)],
                       "n": [round(nx, 4), round(ny, 4)], "x": round(q[0] + nx * (2.8 + beam / 2), 2), "y": round(q[1] + ny * (2.8 + beam / 2), 2),
                       "h": round(math.degrees(math.atan2(ty, tx)) + (180.0 if rnd.random() < 0.5 else 0.0), 1)})
    LAYOUT["river_berths"] = berths
    kay = []
    for k in range(9):                                                       # Urban Kayaks launch (OSM 920-961, 44-52)
        kay.append({"x": 924.0 + 4.4 * k, "y": 54.6 + (k % 2) * 0.9, "h": 90.0 + rnd.uniform(-6, 6)})
    LAYOUT["kayaks"] = kay
    LAYOUT["lock_boats"] = [{"type": "CW_TourBoat", "scale": 1.0, "x": 1712.0, "y": 101.5, "h": 0.0},
                            {"type": "CW_WaterTaxi", "scale": 1.0, "x": 1728.0, "y": 89.8, "h": 180.0},
                            {"type": "CW_MotorYacht", "scale": 0.9, "x": 1762.0, "y": 105.0, "h": 0.0},
                            {"type": "CW_MotorYacht", "scale": 0.75, "x": 1781.0, "y": 105.5, "h": 0.0},
                            {"type": "CW_Sloop", "scale": 1.0, "x": 1801.0, "y": 105.8, "h": 0.0},
                            {"type": "CW_MotorYacht", "scale": 0.85, "x": 1820.0, "y": 106.3, "h": 0.0}]
    LAYOUT["underway"] = [{"type": "CW_TourBoat", "scale": 1.0, "x": 560.0, "y": 118.0, "h": 172.0},
                          {"type": "CW_TourBoat", "scale": 0.85, "x": 790.0, "y": 104.0, "h": -6.0},
                          {"type": "CW_WaterTaxi", "scale": 1.0, "x": 1000.0, "y": 108.0, "h": 2.0},
                          {"type": "CW_TourBoat", "scale": 1.0, "x": 1290.0, "y": 130.0, "h": 15.0},
                          {"type": "CW_Speedboat", "scale": 1.0, "x": 1440.0, "y": 150.0, "h": -10.0},
                          {"type": "CW_TallShipSailing", "scale": 1.0, "x": 1640.0, "y": -320.0, "h": 100.0},
                          {"type": "CW_CruiseShip", "scale": 1.0, "x": 2000.0, "y": 315.0, "h": 2.0},
                          {"type": "CW_SloopSailing", "scale": 1.0, "x": 1560.0, "y": -560.0, "h": 60.0},
                          {"type": "CW_SloopSailing", "scale": 1.1, "x": 1620.0, "y": -700.0, "h": 75.0},
                          {"type": "CW_SloopSailing", "scale": 0.9, "x": 1700.0, "y": -150.0, "h": 40.0},
                          {"type": "CW_SloopSailing", "scale": 1.0, "x": 1880.0, "y": 600.0, "h": 200.0},
                          {"type": "CW_SloopSailing", "scale": 1.2, "x": 2150.0, "y": 680.0, "h": 170.0},
                          {"type": "CW_SloopSailing", "scale": 1.0, "x": 1180.0, "y": -1550.0, "h": 120.0},
                          {"type": "CW_MotorYacht", "scale": 1.0, "x": 1600.0, "y": -1000.0, "h": 85.0},
                          {"type": "CW_MotorYacht", "scale": 1.0, "x": 960.0, "y": 324.0, "h": 0.0},
                          {"type": "CW_MotorYacht", "scale": 0.9, "x": 1000.0, "y": 324.5, "h": 180.0},
                          {"type": "CW_MotorYacht", "scale": 1.2, "x": 1050.0, "y": 325.0, "h": 0.0},
                          {"type": "CW_TourBoat", "scale": 1.0, "x": 1411.0, "y": 48.6, "h": 0.0},
                          {"type": "CW_TourBoat", "scale": 1.0, "x": 1450.0, "y": 48.6, "h": 180.0},
                          {"type": "CW_MotorYacht", "scale": 0.6, "x": 1418.0, "y": 10.0, "h": 90.0},
                          {"type": "CW_MotorYacht", "scale": 0.6, "x": 1429.0, "y": 10.0, "h": 90.0},
                          {"type": "CW_MotorYacht", "scale": 0.55, "x": 1436.0, "y": 10.0, "h": -90.0}]
    isl = PLAN["water"]["inner"]
    best = None
    for ring in isl:
        xs = [q[0] for q in ring]; ys = [q[1] for q in ring]
        if 1240 < min(xs) < 1270 and 1350 < max(xs) < 1380 and -415 < min(ys) < -385:
            best = ring
    if best:
        cx = sum(q[0] for q in best) / len(best); cy = sum(q[1] for q in best) / len(best)
        LAYOUT["abegweit"] = {"x": round((min(q[0] for q in best) + max(q[0] for q in best)) / 2, 2),
                              "y": round((min(q[1] for q in best) + max(q[1] for q in best)) / 2, 2), "h": 0.0,
                              "island": [[round(q[0], 2), round(q[1], 2)] for q in best]}
    LAYOUT["nav_lights"] = [{"name": "Southeast Guidewall Light", "type": "CW_NavLightGreen", "x": 2089.6, "y": 87.0, "z": TOP},
                            {"name": "lock north wall east end", "type": "CW_NavLightRed", "x": 1912.4, "y": 118.4, "z": TOP},
                            {"name": "Breakwater South Light", "type": "CW_NavLightRed", "x": 1463.8, "y": -1174.3, "z": 0.0},
                            {"name": "South Breakwater Northend Light 1", "type": "CW_NavLightGreen", "x": 1459.1, "y": -1413.0, "z": 0.0},
                            {"name": "Dime Pier east end", "type": "CW_NavLightRed", "x": 2327.0, "y": 252.4, "z": DIME_TOP}]


def river_docks():
    """Boarding pontoons + gangways at the river berths (computed in harbour_extras), added to CW_Docks_River."""
    pass


DIME_TOP = WATER + 1.3


def dime_pier():
    """The Dime Pier / City Pier No. 1 breakwater between the lock and Navy Pier (OSM w157657596, x 1621-2332, 8 m wide;
    dark rubble mound with scrub in the NAIP aerial): a crest 1.3 m over the water, rock slopes to the bed, boulders
    along both waterlines, a scrubby strip on top."""
    reset()
    poly = clean(feat_by_id("breakwaters", 157657596)["pts"])
    ox, oy = 1977.0, 246.0
    B = PlanBuilder()
    P = [(x - ox, y - oy) for x, y in ccw(poly)]
    B.sweep_closed(P, [(4.0, BED), (0.0, WATER), (-1.6, DIME_TOP)], "M_CW_Riprap")
    crest = offset_poly(P, -1.6)
    B.face([(x, y, DIME_TOP) for x, y in crest], "M_CW_Riprap")
    rnd = random.Random(7)
    per = list(P) + [P[0]]
    for (x, y, tx, ty) in along(per, 4.2, 1.0):
        for dd, zz in ((0.6, WATER + 0.1), (-1.0, DIME_TOP - 0.2)):
            nx, ny = ty, -tx                                                  # outward for a CCW outline
            r = rnd.uniform(0.6, 1.3)
            B.ellipsoid((x + nx * dd + rnd.uniform(-0.6, 0.6), y + ny * dd + rnd.uniform(-0.6, 0.6), zz), (r * 1.2, r, r * 0.7), "M_CW_Riprap",
                        5, 3, Matrix.Rotation(rnd.uniform(0, 3.14), 3, "Z"))
    mid = offset_poly(P, -3.2)
    if len(mid) > 2:
        B.face([(x, y, DIME_TOP + 0.25) for x, y in mid], "M_Hedge")
    ob = B.finish("CW_DimePier", sharp_angle=40)
    LAYOUT["origin_dime"] = [ox, oy]
    site_export("CW_DimePier", ob, {"pivot": "plan (%.1f, %.1f), plan ground" % (ox, oy), "osm": "w157657596", "crest_m": DIME_TOP})


def river_walls():
    """A dressed river wall along the Chicago side of the main stem (the plan's river ring, east of the seam, x > 200,
    up to the lock): a concrete facing 4 cm proud of the city's cut wall (dark, wet band at the waterline), a coping
    lip at street level, ladders every ~40 m and rubber fenders by the tour-boat berths."""
    reset()
    ring = plan_ring(HARBOURS["river"][4])
    seam = PLAN["seam"]

    def chicago_side(x, y):
        for (x1, y1), (x2, y2) in zip(seam, seam[1:]):
            if x1 <= x <= x2:
                return y < y1 + (y2 - y1) * (x - x1) / max(1e-6, x2 - x1)
        return True
    ox, oy = 950.0, 190.0
    B = PlanBuilder()
    pts = list(ring) + [ring[0]]
    acc = 0.0
    nseg = 0
    for a, b in zip(pts, pts[1:]):
        L = math.dist(a, b)
        if L < 0.3 or min(a[0], b[0]) < 200 or max(a[0], b[0]) > 1660:
            continue
        if not (chicago_side(*a) and chicago_side(*b)):
            continue
        tx, ty = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = -ty, tx
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        if not inside(ring, mx + nx * 1.0, my + ny * 1.0):
            nx, ny = -nx, -ny                                                 # n points into the water
        A = (a[0] + nx * 0.04 - ox, a[1] + ny * 0.04 - oy)
        Bp = (b[0] + nx * 0.04 - ox, b[1] + ny * 0.04 - oy)
        for z0, z1, m in ((BED, WATER + 0.6, "M_CW_WallDark"), (WATER + 0.6, -0.14, "M_CW_LockConcrete")):
            q = [(A[0], A[1], z0), (Bp[0], Bp[1], z0), (Bp[0], Bp[1], z1), (A[0], A[1], z1)]
            # orient to face the water
            e = Vector((Bp[0] - A[0], Bp[1] - A[1], 0))
            if e.cross(Vector((0, 0, 1))).dot(Vector((nx, ny, 0))) < 0:
                q = q[::-1]
            B.face(q, m)
        B.beam((a[0] + nx * 0.16 - ox, a[1] + ny * 0.16 - oy, -0.06), (b[0] + nx * 0.16 - ox, b[1] + ny * 0.16 - oy, -0.06), 0.36, 0.18, "M_CW_LockConcrete")
        d = 40.0 - acc
        while d < L:
            x, y = a[0] + tx * d, a[1] + ty * d
            for s_ in (-0.25, 0.25):
                B.box((x + tx * s_ + nx * 0.12 - ox, y + ty * s_ + ny * 0.12 - oy, (WATER - 1.0) / 2), (0.06, 0.06, -WATER + 1.0), "M_CW_GateSteel")
            zr = WATER - 0.6
            while zr < -0.2:
                B.beam((x - tx * 0.25 + nx * 0.12 - ox, y - ty * 0.25 + ny * 0.12 - oy, zr), (x + tx * 0.25 + nx * 0.12 - ox, y + ty * 0.25 + ny * 0.12 - oy, zr), 0.04, 0.04, "M_CW_GateSteel")
                zr += 0.35
            d += 40.0
        acc = (acc + L) % 40.0
        nseg += 1
    for b in LAYOUT.get("river_berths", []):                                    # fenders at the berths
        (wx, wy), (tx, ty), (nx, ny) = b["wall"], b["t"], b["n"]
        for f in (-6.0, -2.0, 2.0, 6.0):
            B.box((wx + tx * f + nx * 0.2 - ox, wy + ty * f + ny * 0.2 - oy, (WATER - 0.8 - 0.6) / 2), (0.4, 0.4, -0.6 - (WATER - 0.8)), "M_CW_Fender",
                  Matrix.Rotation(math.atan2(ty, tx), 3, "Z"))
    ob = B.finish("CW_RiverWalls", sharp_angle=40)
    LAYOUT["origin_riverwalls"] = [ox, oy]
    site_export("CW_RiverWalls", ob, {"pivot": "plan (%.1f, %.1f), plan ground" % (ox, oy), "segments": nseg})


def riverwalk():
    """The Chicago Riverwalk's east reach (Michigan Ave to Lake Shore Drive) on the Chicago side's south bank: the strip
    between the river wall and Wacker Drive's sidewalk (12-30 m wide in roadnet.json) gets granite paving, a guard
    railing on the wall (open at the boat gangways), planters with trees (honey locusts placed in Unreal), benches,
    lamps, and three stepped terraces that go down to a ledge 1.6 m over the water (the real Riverwalk sits a level
    below the street; the plan has one ground level, so the terraces step down into the river instead)."""
    reset()
    rn = json.load(open(ROOT + "/Saved/Roads/roadnet.json"))
    polys = []
    for e in rn["edges"]:
        rb = e.get("ribbon")
        if rb:
            polys.append(json.loads(rb) if isinstance(rb, str) else rb)
    polys += [w for w in rn["walk"]] + [j["ring"] for j in rn["junctions"]] + [w for w in rn["parkway"]]
    idx = []
    for p_ in polys:
        xs = [q[0] for q in p_]; ys = [q[1] for q in p_]
        if max(xs) < 200 or min(xs) > 1200 or max(ys) < -50 or min(ys) > 200:
            continue
        idx.append((min(xs), max(xs), min(ys), max(ys), p_))

    def hit(x, y):
        return any(a <= x <= b and c <= y <= d and inside(p_, x, y) for a, b, c, d, p_ in idx)
    ring = plan_ring(HARBOURS["river"][4])
    # the south bank from Michigan Ave to Lake Shore Drive, walked east -> west along the ring
    bank = [tuple(q) for q in ring if 296 <= q[0] <= 1112 and q[1] < 125]
    bank.sort(key=lambda q: q[0])
    samples = []
    for a, b in zip(bank, bank[1:]):
        L = math.dist(a, b)
        n = max(1, int(L / 4.0))
        for k in range(n):
            samples.append((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
    samples.append(bank[-1])
    berths = [b["wall"] for b in LAYOUT.get("river_berths", [])]
    ox, oy = 700.0, 80.0
    B = PlanBuilder()
    rows = []
    for i, (x, y) in enumerate(samples):
        a = samples[max(0, i - 1)]; b = samples[min(len(samples) - 1, i + 1)]
        L = max(1e-6, math.dist(a, b))
        tx, ty = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = ty, -tx                                                      # to the left of eastward = south = land
        if inside(ring, x + nx * 1.0, y + ny * 1.0):
            nx, ny = -nx, -ny
        d = 0.0
        while d < 30.0 and not hit(x + nx * (d + 1.0), y + ny * (d + 1.0)):
            d += 1.0
        rows.append((x, y, nx, ny, tx, ty, min(14.0, d - 1.0)))
    # runs where the strip is at least 4 m wide
    runs, cur = [], []
    for r in rows:
        if r[6] >= 4.0:
            cur.append(r)
        else:
            if len(cur) > 3:
                runs.append(cur)
            cur = []
    if len(cur) > 3:
        runs.append(cur)
    trees, lamps = [], []
    for run in runs:
        edge = [(x - ox, y - oy) for x, y, nx, ny, tx, ty, w in run]
        inner = [(x + nx * w - ox, y + ny * w - oy) for x, y, nx, ny, tx, ty, w in run]
        poly = edge + inner[::-1]
        banded_slab(B, poly, -0.15, 0.05, [(-0.15, 0.05, "M_CW_LockConcrete")], "M_DeckPaving")
        acc = 0.0
        for i, (x, y, nx, ny, tx, ty, w) in enumerate(run):
            if i:
                acc += math.dist((x, y), run[i - 1][:2])
            near_berth = any(math.dist((x, y), q) < 11.0 for q in berths)
            if i < len(run) - 1 and not near_berth:
                x2, y2 = run[i + 1][0], run[i + 1][1]
                B.railing([(x + nx * 0.3 - ox, y + ny * 0.3 - oy), (x2 + nx * 0.3 - ox, y2 + ny * 0.3 - oy)], 0.05, h=1.07, step=2.0, m="M_Railing")
            k = int(acc // 14.0)
            if abs(acc - k * 14.0) < 2.0 and w >= 7.0 and (k, "p") not in [t[2:] for t in trees] and not near_berth:
                px, py = x + nx * (w * 0.62), y + ny * (w * 0.62)
                rot = Matrix.Rotation(math.atan2(ty, tx), 3, "Z")
                B.box((px - ox, py - oy, 0.28), (3.2, 1.6, 0.46), "M_CW_LockConcrete", rot)
                B.box((px - ox, py - oy, 0.52), (3.0, 1.4, 0.06), "M_Hedge", rot)
                trees.append((round(px, 2), round(py, 2), k, "p"))
                bx, by = x + nx * 2.4 + tx * 7.0, y + ny * 2.4 + ty * 7.0
                B.box((bx - ox, by - oy, 0.27), (1.9, 0.5, 0.06), "M_Timber", rot)
                B.box((bx - ox, by - oy, 0.14), (1.6, 0.4, 0.2), "M_Railing", rot)
            kl = int(acc // 25.0)
            if abs(acc - kl * 25.0) < 2.0 and (kl, "l") not in [t[2:] for t in lamps]:
                lx, ly = x + nx * 1.3, y + ny * 1.3
                B.tube([(lx - ox, ly - oy, 0.05), (lx - ox, ly - oy, 4.6)], [0.07, 0.05], "M_Railing", 6, cap1=True)
                B.ellipsoid((lx - ox, ly - oy, 4.8), (0.24, 0.24, 0.3), "M_Light", 8, 4)
                lamps.append((lx, ly, kl, "l"))
    # stepped terraces down to a ledge over the water
    terr = []
    for target in (520.0, 770.0, 980.0):
        r = min(rows, key=lambda r: abs(r[0] - target))
        x, y, nx, ny, tx, ty, w = r
        if any(math.dist((x, y), q) < 25.0 for q in berths):
            continue
        wx, wy = -nx, -ny                                                     # into the water
        rot = Matrix.Rotation(math.atan2(ty, tx), 3, "Z")
        nst = 9
        for k in range(nst):
            z1 = -(k + 1) * (3.9 / nst) + 3.9 / nst                          # top of step k
            dd = 0.8 * k + 0.4
            B.box((x + wx * dd - ox, y + wy * dd - oy, (z1 + (WATER - 0.4)) / 2), (12.0, 0.8, z1 - (WATER - 0.4)), "M_CW_LockConcrete", rot)
        dd = 0.8 * nst + 1.2
        B.box((x + wx * dd - ox, y + wy * dd - oy, (-3.9 + WATER - 0.4) / 2), (12.0, 2.4, -3.9 - (WATER - 0.4)), "M_CW_LockConcrete", rot)
        ex, ey = x + wx * (0.8 * nst + 2.35), y + wy * (0.8 * nst + 2.35)
        B.railing([(ex - tx * 6 - ox, ey - ty * 6 - oy), (ex + tx * 6 - ox, ey + ty * 6 - oy)], -3.9, h=1.07, step=2.0)
        terr.append([round(x, 1), round(y, 1)])
    ob = B.finish("CW_Riverwalk", sharp_angle=40)
    LAYOUT["origin_riverwalk"] = [ox, oy]
    LAYOUT["riverwalk_trees"] = [[t[0], t[1]] for t in trees]
    LAYOUT["riverwalk_zone"] = [[[round(x, 2), round(y, 2)] for x, y, nx, ny, tx, ty, w in run] +
                                [[round(x + nx * w, 2), round(y + ny * w, 2)] for x, y, nx, ny, tx, ty, w in run][::-1] for run in runs]
    site_export("CW_Riverwalk", ob, {"pivot": "plan (%.1f, %.1f), plan ground" % (ox, oy), "runs": len(runs), "terraces": terr,
                                     "trees": len(trees)})


def clubhouses():
    """Two harbour buildings on their OSM footprints: the Chicago Yacht Club's Monroe Station (2 storeys, on the Monroe
    Harbor shore, w210969079) with its signal mast and yardarm; the Navy Pier Marina boat house (2 storeys, on its
    floating platform north of the pier, w1417040524)."""
    for nm, oid, base, h1, h2, name in (("Chicago Yacht Club - Monroe Station", (972.0, -712.0), 0.0, 3.8, 3.4, "CW_YachtClubMonroe"),
                                         ("Navy Pier Marina Boat House", (1781.3, 533.9), DECK_Z, 3.2, 3.0, "CW_MarinaBoathouse")):
        reset()
        b = next(x for x in FEAT["boathouses"] if x["name"] == nm)
        poly = clean(b["pts"])
        ox, oy = oid
        P = [(x - ox, y - oy) for x, y in ccw(poly)]
        B = PlanBuilder()
        z = base
        for z0, z1, m in ((z, z + 0.9, "M_CW_WhiteWall"), (z + 0.9, z + h1 - 0.5, "M_GlassDark"), (z + h1 - 0.5, z + h1, "M_CW_WhiteWall"),
                          (z + h1, z + h1 + 0.8, "M_CW_WhiteWall"), (z + h1 + 0.8, z + h1 + h2 - 0.4, "M_GlassDark"), (z + h1 + h2 - 0.4, z + h1 + h2, "M_CW_WhiteWall")):
            n = len(P)
            for i in range(n):
                (ax, ay), (bx, by) = P[i], P[(i + 1) % n]
                B.face([(ax, ay, z0), (bx, by, z0), (bx, by, z1), (ax, ay, z1)], m)
        big = offset_poly(P, 0.8)
        zt = z + h1 + h2
        B.face([(x, y, zt) for x, y in big][::-1], "M_RoofFlat")
        B.face([(x, y, zt + 0.3) for x, y in big], "M_RoofFlat")
        for i in range(len(big)):
            (ax, ay), (bx, by) = big[i], big[(i + 1) % len(big)]
            B.face([(ax, ay, zt), (bx, by, zt), (bx, by, zt + 0.3), (ax, ay, zt + 0.3)], "M_CW_WhiteWall")
        mid = offset_poly(P, 0.35)                                            # balcony slab at the upper floor
        B.face([(x, y, z + h1) for x, y in mid][::-1], "M_CW_WhiteWall")
        B.face([(x, y, z + h1 + 0.15) for x, y in mid], "M_CW_DockDeck")
        if name == "CW_YachtClubMonroe":                                      # yacht-club signal mast with yardarm and gaff
            mx, my = 993.0 - ox, -722.0 - oy
            B.tube([(mx, my, 0.0), (mx, my, 16.0)], [0.16, 0.07], "M_CW_WhiteWall", 8, cap1=True)
            B.tube([(mx - 3.0, my, 11.0), (mx + 3.0, my, 11.0)], [0.06, 0.05], "M_CW_WhiteWall", 6)
            B.tube([(mx, my, 9.0), (mx - 0.1, my - 2.8, 11.6)], [0.05, 0.04], "M_CW_WhiteWall", 6)
            for sx in (-3.0, 3.0):
                B.tube([(mx, my, 15.5), (mx + sx, my, 11.0), (mx + sx * 1.6, my, 0.0)], [0.012] * 3, "M_CWB_Steel", 3)
        ob = B.finish(name, sharp_angle=40)
        LAYOUT["origin_" + name] = [ox, oy]
        site_export(name, ob, {"pivot": "plan (%.1f, %.1f), plan ground" % (ox, oy), "osm": nm})


def docks():
    harbour_extras()
    for area in HARBOURS:
        reset()
        harbour(area)
    reset()
    dime_pier()
    river_walls()
    riverwalk()
    clubhouses()


# ================================================================== previews
_CACHE = {}


def _import(name, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0):
    """Import a GLB once, then link duplicates of its mesh (fast for hundreds of boats)."""
    if name in _CACHE and all(o.name in bpy.data.objects for o in _CACHE[name]):
        new = []
        for src in _CACHE[name]:
            o = bpy.data.objects.new(name, src.data)
            bpy.context.scene.collection.objects.link(o)
            new.append(o)
    else:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=f"{OUT}/{name}.glb")
        new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
        _CACHE[name] = new
    for o in new:
        if o.parent is None:
            o.location = Vector(loc)
            o.rotation_mode = "XYZ"
            o.rotation_euler = rot
            o.scale = (scale, scale, scale)
    return new


def _preview_reset():
    _CACHE.clear()
    reset()


def _preview(path, layout, view=(-0.55, -1.0, 0.32), frame=1.0, lens=35, target_z=None, water=None,
             res=(1280, 800), cam=None, ground_z=-0.02, person=None, target=None, extras=()):
    _preview_reset()
    BL._scene_setup(False, ground_z=ground_z, water=water)
    land = BL._simple_mat("PV_Land", (0.33, 0.33, 0.32), 0.85)
    for lo, hi in extras:
        bpy.ops.mesh.primitive_cube_add(size=1, location=((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2))
        o = bpy.context.object
        o.scale = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
        o.data.materials.append(land)
    objs = []
    for item in layout:
        objs += _import(*item)
    if person:
        BL._person(person)
    BL._camera(objs, view, lens, res, frame, target_z, target)
    if cam:
        c = bpy.context.scene.camera
        c.location = Vector(cam[0])
        c.rotation_euler = (Vector(cam[1]) - Vector(cam[0])).to_track_quat("-Z", "Y").to_euler()
    BL._render(path, samples=32)


LAKE = ((0, 0, -0.005), (6000, 6000, 1))
LAKE_SITE = ((0, 0, WATER), (8000, 8000, 1))


def _bl(px, py, z=0.0, o=(0.0, 0.0)):
    """plan point (absolute) -> Blender preview coords relative to the plan point o."""
    return ((py - o[1]), -(px - o[0]), z)


def _harbour_layout(area):
    lay = json.load(open(OUT + "/water_layout.json"))
    o = lay["origin_" + area]
    L = [("CW_Docks_" + "".join(w.capitalize() for w in area.split("_")),)]
    base = {"CW_Sloop": 9.78, "CW_SloopNavy": 9.78, "CW_MotorYacht": 16.35}
    for b in lay["slots_" + area]:
        sc = b["len"] / base.get(b["type"], 10.0)
        L.append((b["type"], _bl(b["x"], b["y"], WATER, o), (0, 0, math.radians(b["h"])), sc))
    return L


def _river_layout():
    lay = json.load(open(OUT + "/water_layout.json"))
    o = (700.0, 80.0)
    L = [("CW_Riverwalk",), ("CW_RiverWalls", _bl(950.0, 190.0, 0, o)), ("CW_Docks_River", _bl(950.0, 190.0, 0, o))]
    for b in lay["river_berths"] + [u for u in lay["underway"] if u["x"] < 1150]:
        L.append((b["type"], _bl(b["x"], b["y"], WATER, o), (0, 0, math.radians(b["h"])), b.get("scale", 1.0)))
    return L


def _lock_layout(open_gates=True):
    lay = json.load(open(OUT + "/water_layout.json"))
    L = [("CW_ChicagoLock",)]
    for g in lay.get("lock_gates", []):
        ang = g["open_deg"] if open_gates else g["closed_deg"]
        L.append(("CW_LockGate" + g["kind"], _bl(g["pivot"][0], g["pivot"][1], 0, LOCK_O), (0, 0, math.radians(ang))))
    # a few boats in the chamber (as in the NAIP aerial)
    for name, px, py, hd in (("CW_TourBoat", 1720, 101, 0), ("CW_WaterTaxi", 1735, 89, 180), ("CW_MotorYacht", 1770, 104, 0),
                             ("CW_Sloop", 1795, 104.5, 0), ("CW_MotorYacht", 1815, 104, 0)):
        L.append((name, _bl(px, py, WATER, LOCK_O), (0, 0, math.radians(hd))))
    return L
PREVIEWS = {
    "Fleet": dict(layout=[("CW_Sloop", (0, 0, 0)), ("CW_SloopNavy", (0, 6, 0)), ("CW_SloopSailing", (14, -14, 0)), ("CW_MotorYacht", (0, 13, 0)),
                          ("CW_TourBoat", (-4, -14, 0)), ("CW_WaterTaxi", (-6, -26, 0)), ("CW_Speedboat", (22, 8, 0)),
                          ("CW_CruiseShip", (-12, 44, 0)), ("CW_TallShip", (-14, -48, 0))],
                  water=LAKE, ground_z=-3.0, view=(-0.9, -1.0, 0.35), frame=0.62, lens=30),
    "Lock": dict(layout=_lock_layout(), water=LAKE_SITE, ground_z=-9.0, cam=(_bl(1640, 30, 40, LOCK_O), _bl(1790, 100, -4, LOCK_O)), lens=30),
    "Lock_gate": dict(layout=_lock_layout(), water=LAKE_SITE, ground_z=-9.0, cam=(_bl(1700, 60, 9, LOCK_O), _bl(1668, 100, -3, LOCK_O)), lens=30),
    "Lock_air": dict(layout=_lock_layout(), water=LAKE_SITE, ground_z=-9.0, cam=(_bl(1770, -120, 260, LOCK_O), _bl(1770, 110, -5, LOCK_O)), lens=35),
    "Abegweit": dict(layout=[("CW_Abegweit",), ("CW_Sloop", (-40, -22, 0), (0, 0, 1.3)), ("CW_Sloop", (-25, -30, 0), (0, 0, 1.4))],
                     water=LAKE, ground_z=-3.0, view=(0.7, -1.0, 0.28), frame=0.65, lens=35, target_z=6.0),
    "DuSable": dict(layout=_harbour_layout("dusable"), water=LAKE_SITE, ground_z=-9.0,
                    cam=(_bl(1230, -420, 70, (1356.0, -212.0)), _bl(1340, -230, -5, (1356.0, -212.0))), lens=32),
    "River": dict(layout=_river_layout(), water=LAKE_SITE, ground_z=-9.0, extras=[((-150, -40, -9), (40, 520, 0.0))],
                  cam=(_bl(300, 60, 25, (700.0, 80.0)), _bl(560, 110, -3, (700.0, 80.0))), lens=30),
    "SmallBoats": dict(layout=[("CW_Sloop", (0, 0, 0)), ("CW_MotorYacht", (0, 7, 0)), ("CW_SloopNavy", (0, -6, 0))],
                       water=LAKE, ground_z=-3.0, view=(1.0, -0.8, 0.25), frame=0.55, lens=40, target_z=1.5),
    "RiverBoats": dict(layout=[("CW_TourBoat", (0, 0, 0)), ("CW_WaterTaxi", (-4, -11, 0)), ("CW_Speedboat", (2, 11, 0))],
                       water=LAKE, ground_z=-3.0, view=(0.5, -1.0, 0.3), frame=0.6, lens=40, target_z=2.0),
}


def render_previews(names):
    for name in (names or list(PREVIEWS)):
        _preview(f"{OUT}/preview_{name}.png", **PREVIEWS[name])


JOBS = {"boats": boats, "ships": lambda: (abegweit(), small_craft()), "lock": lock, "docks": docks}


def write_json():
    path = OUT + "/water.json"
    data = {}
    if os.path.exists(path):
        try:
            data = json.load(open(path))
        except Exception:
            data = {}
    assets = data.get("assets", {})
    assets.update(META)
    data["assets"] = dict(sorted(assets.items()))
    data["conventions"] = {"units": "metres in Blender/GLB; Unreal imports as centimetres",
                           "axes": "Blender (x, y, z) -> Unreal (x, -y, z); boats bow +X, origin on the waterline; site assets plan-frame, placed unrotated",
                           "water_surface_m": WATER, "generator": "Scripts/landmarks/blender_chicago_water.py"}
    json.dump(data, open(path, "w"), indent=1)
    print("wrote", path)
    if LAYOUT:
        lp = OUT + "/water_layout.json"
        lay = json.load(open(lp)) if os.path.exists(lp) else {}
        lay.update(LAYOUT)
        lay["frame"] = "plan metres (x east, y north); headings in degrees CCW from plan east; Unreal yaw = 90 - heading"
        json.dump(lay, open(lp, "w"), indent=0)
        print("wrote", lp)


if __name__ == "__main__":
    if ARGS and ARGS[0] == "--render":
        render_previews(ARGS[1:])
    else:
        sel = [a for a in ARGS if a in JOBS]
        ONLY = [a for a in ARGS if a.startswith("CW_")] or None
        for job, fn in JOBS.items():
            if sel and job not in sel:
                continue
            reset()
            fn()
        write_json()
    print("ALL DONE")
