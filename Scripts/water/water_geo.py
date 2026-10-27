"""Lane 9 (water A/B): meshes for the river and lake test, built from the generator's waterflow_<region>.json.

Pure Python (runs in Unreal's Python and in plain Python 3). Everything is our own geometry, made by code:
  ground_cut      the ground slab's replacement: the slab rectangle minus the river (and minus a lake), so the
                  channel can sink below the ground plane
  channel         the riverbed and banks: a cross-section per station, BANK_SLOPE banks down to the bed
  river_surface   option B's river: a strip from bank to bank at the surface level. UV0 in metres / TILE_M
                  (U across, V downstream), UV1 = (distance to the shore in m, flow speed in m/s)
  bowl            a lake's bed (outline at the level, down to the max depth)
  lake_surface    option B's lake: concentric rings in from the shore, UV1 = (distance to shore, 0)
  polygon_mesh    a flat polygon, with an optional hole (used for the park around the demo pond)
GLBs: plan (x east, y north, z up, metres) → glTF (y, z, x), which Unreal's glTF import lands at UE (X = y, Y = x,
Z = z) in metres → cm, the city frame (as city_water.water_glb).
"""
import json
import math
import struct

TILE_M = 6.0          # normal-map tile (m) of the B water
BED_UV_M = 4.0        # world-planar UV tile of the bed and ground


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _crs(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


class Mesh:
    def __init__(self):
        self.p, self.uv0, self.uv1, self.tris = [], [], [], []

    def add(self, p, uv0=(0.0, 0.0), uv1=(0.0, 0.0)):
        self.p.append(tuple(float(v) for v in p))
        self.uv0.append(tuple(uv0))
        self.uv1.append(tuple(uv1))
        return len(self.p) - 1

    def tri(self, a, b, c):
        """Plan counter-clockwise seen from above (+z) = facing up."""
        self.tris.append((a, b, c))

    def grid(self, rows):
        """rows: list of lists of vertex indices, each row left → right across, rows in order downstream.
        Faces up when the rows run so that left is +90 degrees from the row direction (plan CCW)."""
        for r0, r1 in zip(rows, rows[1:]):
            for k in range(len(r0) - 1):
                a, b, c, d = r0[k], r0[k + 1], r1[k + 1], r1[k]
                self.tri(a, b, c)
                self.tri(a, c, d)

    def normals(self):
        acc = [[0.0, 0.0, 0.0] for _ in self.p]
        for a, b, c in self.tris:
            n = _crs(_sub(self.p[b], self.p[a]), _sub(self.p[c], self.p[a]))
            for i in (a, b, c):
                acc[i][0] += n[0]
                acc[i][1] += n[1]
                acc[i][2] += n[2]
        return [_norm(v) if any(v) else (0.0, 0.0, 1.0) for v in acc]

    def fix_up(self):
        """Flip any triangle that faces down (all our meshes face up)."""
        out = []
        for a, b, c in self.tris:
            n = _crs(_sub(self.p[b], self.p[a]), _sub(self.p[c], self.p[a]))
            out.append((a, b, c) if n[2] >= 0 else (a, c, b))
        self.tris = out
        return self

    def glb(self, name, material="M_Default"):
        self.fix_up()
        nrm = self.normals()
        positions = [(p[1], p[2], p[0]) for p in self.p]
        normals = [(n[1], n[2], n[0]) for n in nrm]
        indices = [i for a, b, c in self.tris for i in (a, c, b)]   # the swizzle mirrors: reverse the winding
        big = len(positions) > 65535
        blobs = [b"".join(struct.pack("<3f", *v) for v in positions),
                 b"".join(struct.pack("<3f", *v) for v in normals),
                 b"".join(struct.pack("<2f", *v) for v in self.uv0),
                 b"".join(struct.pack("<2f", *v) for v in self.uv1),
                 b"".join(struct.pack("<I" if big else "<H", i) for i in indices)]
        views, offset, binary = [], 0, b""
        for k, blob in enumerate(blobs):
            views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(blob),
                          "target": 34963 if k == 4 else 34962})
            pad = (4 - len(blob) % 4) % 4
            binary += blob + b"\0" * pad
            offset += len(blob) + pad
        lo = [min(p[k] for p in positions) for k in range(3)]
        hi = [max(p[k] for p in positions) for k in range(3)]
        gltf = {"asset": {"version": "2.0", "generator": "SkyCity lane9 water_geo.py"}, "scene": 0,
                "scenes": [{"nodes": [0]}], "nodes": [{"name": name, "mesh": 0}],
                "meshes": [{"name": name, "primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2,
                                                                         "TEXCOORD_1": 3},
                                                          "indices": 4, "mode": 4, "material": 0}]}],
                "materials": [{"name": material, "pbrMetallicRoughness": {"baseColorFactor": [0.5, 0.5, 0.5, 1.0]}}],
                "accessors": [
                    {"bufferView": 0, "componentType": 5126, "count": len(positions), "type": "VEC3", "min": lo, "max": hi},
                    {"bufferView": 1, "componentType": 5126, "count": len(normals), "type": "VEC3"},
                    {"bufferView": 2, "componentType": 5126, "count": len(self.uv0), "type": "VEC2"},
                    {"bufferView": 3, "componentType": 5126, "count": len(self.uv1), "type": "VEC2"},
                    {"bufferView": 4, "componentType": 5125 if big else 5123, "count": len(indices), "type": "SCALAR"}],
                "bufferViews": views, "buffers": [{"byteLength": len(binary)}]}
        text = json.dumps(gltf, separators=(",", ":"), sort_keys=True).encode()
        text += b" " * ((4 - len(text) % 4) % 4)
        chunks = struct.pack("<I4s", len(text), b"JSON") + text + struct.pack("<I4s", len(binary), b"BIN\0") + binary
        return struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks


# --- the river ------------------------------------------------------------------------------------------------

def extended(river, before_m, after_m, step=10.0):
    """The river's stations (dicts with at, width, depth, speed, flow, along) and banks, carried straight past both
    ends by before_m / after_m, so the channel reaches past the ground slab's edge."""
    st = river["stations"]
    rows = [{"at": tuple(s["at"]), "w": s["width_m"], "d": s["depth_m"], "v": s["speed_mps"], "f": tuple(s["flow"]),
             "s": s["along_m"]} for s in st]
    head, tail = rows[0], rows[-1]
    pre = []
    n = int(before_m // step)
    for k in range(n, 0, -1):
        r = dict(head)
        r["at"] = (head["at"][0] - head["f"][0] * step * k, head["at"][1] - head["f"][1] * step * k)
        r["s"] = head["s"] - step * k
        pre.append(r)
    post = []
    for k in range(1, int(after_m // step) + 1):
        r = dict(tail)
        r["at"] = (tail["at"][0] + tail["f"][0] * step * k, tail["at"][1] + tail["f"][1] * step * k)
        r["s"] = tail["s"] + step * k
        post.append(r)
    return pre + rows + post


def left_normal(f):
    return (-f[1], f[0])


def profile_z(e, d, slope):
    """Bed height (m below the level) at distance e (m) in from the nearest bank."""
    return -d * smooth(e / max(d * slope, 0.1))


def shore_offset(level_drop, d, slope):
    """Distance in from the bank where the bed is level_drop below the level (the waterline)."""
    lo, hi = 0.0, d * slope
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if -profile_z(mid, d, slope) < level_drop:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def channel(rows, level, slope, across=17):
    m = Mesh()
    grid = []
    for r in rows:
        n = left_normal(r["f"])
        half = r["w"] / 2.0
        row = []
        for k in range(across):
            u = k / (across - 1.0)               # 0 = left bank, 1 = right bank
            o = half - u * r["w"]                # offset along the left normal
            e = min(u, 1.0 - u) * r["w"]
            z = level + profile_z(e, r["d"], slope)
            x, y = r["at"][0] + n[0] * o, r["at"][1] + n[1] * o
            row.append(m.add((x, y, z), (x / BED_UV_M, y / BED_UV_M), (e, r["v"])))
        grid.append(row)
    # left → right across is the -normal direction; downstream is +f: (right, forward) is plan CCW, so reverse rows.
    m.grid([list(reversed(row)) for row in grid])
    return m


def river_surface(rows, level, surface, slope, across=11, into_bank=0.4):
    m = Mesh()
    grid = []
    for r in rows:
        n = left_normal(r["f"])
        half = r["w"] / 2.0
        e0 = max(0.0, shore_offset(level - surface, r["d"], slope) - into_bank)
        inner = r["w"] - 2.0 * e0
        row = []
        for k in range(across):
            u = k / (across - 1.0)
            o = half - e0 - u * inner
            shore = min(u, 1.0 - u) * inner          # distance in from the waterline (≈)
            x, y = r["at"][0] + n[0] * o, r["at"][1] + n[1] * o
            across_m = (half - o)                     # 0 at the left bank
            row.append(m.add((x, y, surface), (across_m / TILE_M, r["s"] / TILE_M), (max(0.0, shore - into_bank), r["v"])))
        grid.append(row)
    m.grid([list(reversed(row)) for row in grid])
    return m


def bank_line(rows, side):
    """The bank line (left = +normal side of the flow) of the rows."""
    pts = []
    for r in rows:
        n = left_normal(r["f"])
        s = r["w"] / 2.0 * (1 if side == "left" else -1)
        pts.append((r["at"][0] + n[0] * s, r["at"][1] + n[1] * s))
    return pts


def _clip_y(pts, y0, y1):
    """The polyline's part between y0 and y1 (it must run with increasing y), with exact end points."""
    out = []
    for a, b in zip(pts, pts[1:]):
        for yy in (y0, y1):
            if (a[1] - yy) * (b[1] - yy) < 0:
                t = (yy - a[1]) / (b[1] - a[1])
                out.append((a[0] + (b[0] - a[0]) * t, yy))
        if y0 < b[1] < y1:
            out.append(b)
    out.sort(key=lambda p: p[1])
    return out


# --- flat polygons --------------------------------------------------------------------------------------------

def signed_area(ring):
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:] + ring[:1]))


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _in_tri(p, a, b, c):
    return _cross(a, b, p) > 1e-9 and _cross(b, c, p) > 1e-9 and _cross(c, a, p) > 1e-9


def triangulate(ring):
    n = len(ring)
    idx = list(range(n))
    tris = []
    guard = 0
    while len(idx) > 3 and guard < 4 * n * n:
        guard += 1
        m = len(idx)
        for k in range(m):
            i0, i1, i2 = idx[(k - 1) % m], idx[k], idx[(k + 1) % m]
            a, b, c = ring[i0], ring[i1], ring[i2]
            if _cross(a, b, c) <= 1e-12:
                continue
            if any(_in_tri(ring[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            for k in range(1, len(idx) - 1):
                tris.append((idx[0], idx[k], idx[k + 1]))
            return tris
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


def ccw(ring):
    ring = [tuple(p) for p in ring]
    return ring if signed_area(ring) > 0 else list(reversed(ring))


def with_hole(outer, hole):
    """One simple ring: outer (CCW) with a hole (made CW) joined by a slit from the hole's east-most point
    straight east to the outer ring."""
    outer, hole = ccw(outer), list(reversed(ccw(hole)))
    h = max(range(len(hole)), key=lambda k: (hole[k][0], hole[k][1]))
    hp = hole[h]
    best = None
    for k in range(len(outer)):
        a, b = outer[k], outer[(k + 1) % len(outer)]
        if (a[1] - hp[1]) * (b[1] - hp[1]) <= 0 and a[1] != b[1]:
            t = (hp[1] - a[1]) / (b[1] - a[1])
            x = a[0] + (b[0] - a[0]) * t
            if x > hp[0] and (best is None or x < best[0]):
                best = (x, k)
    x, k = best
    bp = (x, hp[1])
    hole_loop = hole[h:] + hole[:h] + [hp]
    return outer[:k + 1] + [bp] + hole_loop + [bp] + outer[k + 1:]


def polygon_mesh(ring, z, uv_m=BED_UV_M):
    ring = ccw(ring) if signed_area(ring) < 0 else [tuple(p) for p in ring]
    m = Mesh()
    ids = [m.add((p[0], p[1], z), (p[0] / uv_m, p[1] / uv_m)) for p in ring]
    for a, b, c in triangulate(ring):
        m.tri(ids[a], ids[b], ids[c])
    return m


def ground_cut(rows, rect, z, hole=None):
    """[west mesh, east mesh]: the slab rectangle (x0, y0, x1, y1) minus the river (crossing it south to north);
    hole (a ring) is cut from whichever side holds it."""
    x0, y0, x1, y1 = rect
    left = _clip_y(bank_line(rows, "left"), y0, y1)
    right = _clip_y(bank_line(rows, "right"), y0, y1)
    west = [(x0, y1), (x0, y0)] + left           # CCW: down the west edge, then north along the left bank
    east = [(x1, y0), (x1, y1)] + list(reversed(right))
    out = []
    for ring in (west, east):
        ring = ccw(ring)
        if hole is not None and _point_in(_centroid(hole), ring):
            ring = with_hole(ring, hole)
        out.append(polygon_mesh(ring, z))
    return out


def _centroid(ring):
    return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))


def _point_in(p, ring):
    x, y, hit = p[0], p[1], False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        if (a[1] > y) != (b[1] > y) and x < a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]):
            hit = not hit
    return hit


# --- lakes ----------------------------------------------------------------------------------------------------

def _inset_rings(outline, offsets):
    """Rings at the given distances in from the outline, pulled toward the centroid (fine for a convex-ish pond)."""
    c = _centroid(outline)
    out = []
    for o in offsets:
        ring = []
        for p in outline:
            dx, dy = p[0] - c[0], p[1] - c[1]
            r = math.hypot(dx, dy) or 1.0
            k = max(0.0, (r - o) / r)
            ring.append((c[0] + dx * k, c[1] + dy * k))
        out.append(ring)
    return c, out


def _radial(m, c, rings, zs, uv1s, uv_m):
    n = len(rings[0])
    ids = [[m.add((p[0], p[1], z), (p[0] / uv_m, p[1] / uv_m), u) for p in ring] for ring, z, u in zip(rings, zs, uv1s)]
    centre = m.add((c[0], c[1], zs[-1]), (c[0] / uv_m, c[1] / uv_m), uv1s[-1])
    for r0, r1 in zip(ids, ids[1:]):
        for k in range(n):
            a, b, cc, d = r0[k], r0[(k + 1) % n], r1[(k + 1) % n], r1[k]
            m.tri(a, b, cc)
            m.tri(a, cc, d)
    last = ids[-1]
    for k in range(n):
        m.tri(last[k], last[(k + 1) % n], centre)
    return m


def bowl(lake, rings=10):
    outline = ccw(lake["outline"])
    d, slope, level = lake["max_depth_m"], lake["bank_slope"], lake["level"]
    c = _centroid(outline)
    rmin = min(math.hypot(p[0] - c[0], p[1] - c[1]) for p in outline)
    offs = [rmin * 0.95 * k / rings for k in range(rings)]
    c, rs = _inset_rings(outline, offs)
    zs = [level + profile_z(o, d, slope) for o in offs]
    return _radial(Mesh(), c, rs, zs, [(o, 0.0) for o in offs], BED_UV_M)


def lake_surface(lake, into_bank=0.4, rings=10):
    outline = ccw(lake["outline"])
    d, slope, level, surface = lake["max_depth_m"], lake["bank_slope"], lake["level"], lake["surface_m"]
    e0 = max(0.0, shore_offset(level - surface, d, slope) - into_bank)
    c = _centroid(outline)
    rmin = min(math.hypot(p[0] - c[0], p[1] - c[1]) for p in outline)
    offs = [e0 + (rmin * 0.95 - e0) * (k / float(rings)) ** 1.5 for k in range(rings)]
    c, rs = _inset_rings(outline, offs)
    return _radial(Mesh(), c, rs, [surface] * len(rs), [(max(0.0, o - e0 - into_bank), 0.0) for o in offs], TILE_M)


def pond_outline(cx, cy, r, n=28, wobble=0.12, seed=7):
    """A demo pond for the lake shots (seed 7 has no lake): a wobbly ellipse, deterministic."""
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        rr = r * (1.0 + wobble * math.sin(3 * a + seed) + 0.5 * wobble * math.sin(5 * a + 2 * seed))
        pts.append((round(cx + rr * 1.15 * math.cos(a), 3), round(cy + rr * 0.9 * math.sin(a), 3)))
    return pts
