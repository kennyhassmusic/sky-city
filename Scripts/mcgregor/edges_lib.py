"""McGregor edge transitions (mcgregor-edges agent, 20 Oct 2026): no high edges where the roads, parking lots and pads
meet the ground. Shared by build_mcgregor_ue.py (`roads` and `pad_edges` stages), site_ue.py (`lots` / `lot_berms`)
and the survey (edges_survey_ue.py). Runs inside the editor (needs `unreal`); nothing here touches a level by itself.

Why the old edges were high: the roads were swept ribbons 0.12-0.14 m above the 2 m DEM at their centreline, with
vertical sides, on a terrain mesh that is the 4 m DEM simplified to 10 cm, so the edge stood 0-1.4 m (median ~0.17 m)
above the ground beside it; the parking lots are sheets 0.18 m over the DEM; the unveil lot is a graded slab 0.3-1.8 m
above the ground at its edges.

How the Skyster car meets a surface (Source/SkyCity/SkysterCar.cpp): a ray under its centre seats it on whatever it
finds (a vertical step under ~0.5 m just pops it up or down); an 80 cm ball 1 m up its body bounces off anything taller
(the "run into" edges); and it leaves the ground when the surface bends away under it by more than 2.5 m/s of its speed
in one 1/120 s step (v * sin(crease) > 2.5 m/s). So a ramp with a sharp lip launches it, and a transition has to bend a
little at a time:
  roads  draped ON the terrain mesh (heights traced from the Terrain_i_j actors themselves): every ~2 m along, 3-5 points
         across, 1 cm over the terrain at the edges and 2-3 cm at the crown; any cell or edge where the terrain would
         poke through is lifted. Edge lips 1-3 cm, no ribbon walls. Optional (build_mcgregor_ue.py `roads_smooth`):
         every ~3 m, 5 points across, then 6 passes of fill-only smoothing inside the outline (never below the drape,
         outline pinned), which rounds the terrain's sharp crests under the road: fewer launches crossing or driving
         along a road (offline simulation in the hand-over note), 1.5x the triangles.
  berms  round raised pads and lots: a strip from the pad's top edge down into the terrain, in the terrain tile's own
         aerial-photo material (the same picture as the ground under it, so the ground seems to rise to the pad). Its
         profile bends 1.5 degrees every 0.8 m (1.5, 3, 4.5, 6 degrees), then runs at 1:8 to 10 cm under the terrain:
         convex creases of 1.5 degrees launch the car only above ~210 mph head-on (the terrain's own facets bend more).
Local metres: x east, y north, z up; Unreal cm: X = y*100, Y = x*100, Z = z*100.
"""
import math
import os
import unreal


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
    import unreal  # running in the editor without __file__
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")


W2, H2, TILE = 4800.0, 3600.0, 2400.0


def tile_of(x, y):
    return min(max(int((x + W2) // TILE), 0), 3), min(max(int((y + H2) // TILE), 0), 2)


class Terrain:
    """Height (m) of the terrain meshes only -- the Terrain_i_j actors -- by line traces that ignore every other actor
    in the level (Python has no per-component trace), so roads, lots and berms never see themselves or anything else
    standing on the ground. ~35 us a query."""

    def __init__(self, actors):
        actors = list(actors)
        self.comp = {}
        for a in actors:
            p = a.get_actor_label().split("_")
            if len(p) == 3 and p[0] == "Terrain" and p[1].isdigit() and p[2].isdigit():
                self.comp[(int(p[1]), int(p[2]))] = a
            elif a.get_actor_label() == "Horizon":          # the farmland skirt past the map edge is ground too
                self.comp["horizon"] = a
        self.ignore = [a for a in actors if a not in self.comp.values()]
        self.world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        self.n = 0
        self.miss = 0

    def h(self, x, y):
        self.n += 1
        r = unreal.SystemLibrary.line_trace_single(self.world, unreal.Vector(y * 100.0, x * 100.0, 9000.0), unreal.Vector(y * 100.0, x * 100.0, -4000.0),
                                                   unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, self.ignore, unreal.DrawDebugTrace.NONE, True)
        if r:
            t = r.to_tuple()
            if t[0]:
                return t[4].z / 100.0
        self.miss += 1
        return None


class DEM:
    """The 4 m height grids the terrain meshes were built from (Saved/McGregor/terrain_i_j.f32), bilinear: the same
    function as build_mcgregor_ue.py's dem_at and site_layout.py's ground (the parking lots and parked cars use it)."""

    def __init__(self, root=None):
        self.root = root or _skycity_root()
        self.g = {}

    def h(self, x, y):
        import array
        N = 601
        i, j = tile_of(x, y)
        if (i, j) not in self.g:
            a = array.array("f")
            with open(f"{self.root}/Saved/McGregor/terrain_{i}_{j}.f32", "rb") as fh:
                a.frombytes(fh.read())
            self.g[(i, j)] = a
        g = self.g[(i, j)]
        c, r = (x - (-W2 + i * TILE)) / 4.0, (y - (-H2 + j * TILE)) / 4.0
        c0, r0 = min(max(int(c), 0), N - 2), min(max(int(r), 0), N - 2)
        fc, fr = min(max(c - c0, 0.0), 1.0), min(max(r - r0, 0.0), 1.0)
        return ((g[r0 * N + c0] * (1 - fc) + g[r0 * N + c0 + 1] * fc) * (1 - fr) +
                (g[(r0 + 1) * N + c0] * (1 - fc) + g[(r0 + 1) * N + c0 + 1] * fc) * fr)


# ------------------------------------------------------------------ mesh assembly
class MeshBuf:
    """Vertices in local metres + triangles grouped by material id, wound counter-clockwise seen from above (local
    right-handed frame); to_dynamic_mesh() converts to Unreal and fixes the winding once for the axis swap."""

    def __init__(self):
        self.v = []
        self.t = {}

    def add(self, x, y, z):
        self.v.append((x, y, z))
        return len(self.v) - 1

    def tri(self, mid, a, b, c):
        if a != b and b != c and a != c:
            self.t.setdefault(mid, []).append((a, b, c))

    def ntris(self):
        return sum(len(v) for v in self.t.values())

    def to_dynamic_mesh(self):
        dm = unreal.DynamicMesh()
        if not self.t:
            return dm
        LU = unreal.GeometryScript_List
        vl = LU.convert_array_to_vector_list([unreal.Vector(y * 100.0, x * 100.0, z * 100.0) for x, y, z in self.v])
        unreal.GeometryScript_MeshEdits.add_vertices_to_mesh(dm, vl[0] if isinstance(vl, tuple) else vl)
        # the local frame is right-handed, Unreal's (X = north, Y = east) is mirrored: swap two indices so the faces
        # still look up/out
        ranges = []
        n0 = 0
        for mid, ts in sorted(self.t.items()):
            tl = LU.convert_array_to_triangle_list([unreal.IntVector(a, c, b) for a, b, c in ts])
            # (the third argument is the triangle GROUP id, not the material: materials are set below)
            unreal.GeometryScript_MeshEdits.add_triangles_to_mesh(dm, tl[0] if isinstance(tl, tuple) else tl, mid)
            ranges.append((mid, n0, n0 + len(ts)))
            n0 += len(ts)
        # material ids: the triangles went in block by block on an empty mesh, so their ids are those ranges
        MF = unreal.GeometryScript_Materials   # (UE 5.8 Python name; was GeometryScript_MeshMaterialFunctions, which doesn't exist: mcgregor-placer, 21 Oct)
        MF.enable_material_i_ds(dm)
        self.mat_set = 0
        for mid, a, b in ranges:
            if mid == 0:
                continue
            for tid in range(a, b):
                MF.set_triangle_material_id(dm, tid, mid, True)
                self.mat_set += 1
        self.mat_check = {mid: MF.get_triangle_material_id(dm, (a + b) // 2) for mid, a, b in ranges}
        # belt and braces: if most faces came out looking down, flip them all (as the other McGregor builders do)
        n = unreal.GeometryScript_MeshQueries.get_num_triangle_i_ds(dm)
        down = 0
        probe = list(range(0, n, max(1, n // 60)))[:60]
        for tid in probe:
            nv = unreal.GeometryScript_MeshQueries.get_triangle_face_normal(dm, tid)
            nv = nv[0] if isinstance(nv, tuple) else nv
            down += 1 if nv.z < 0 else 0
        if probe and down > len(probe) / 2:
            unreal.GeometryScript_Normals.flip_normals(dm)
        self.flipped = bool(probe and down > len(probe) / 2)
        return dm


def write_static_mesh(dm, path, mats, collide=True):
    """Create the static mesh asset at `path`, or write into it in place, so the actors in BOTH McGregor maps (they
    share the mesh assets) pick the new geometry up without being touched. Returns (mesh, how)."""
    EAL = unreal.EditorAssetLibrary
    how = "created"
    if EAL.does_asset_exist(path):
        sm = EAL.load_asset(path)
        o = unreal.GeometryScriptCopyMeshToAssetOptions()
        for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", True), ("replace_materials", True), ("new_materials", mats)):
            try:
                o.set_editor_property(k, v)
            except Exception:
                pass
        unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, o, unreal.GeometryScriptMeshWriteLOD())
        how = "in place"
    else:
        o = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
        for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", True), ("enable_nanite", False), ("enable_collision", collide)):
            try:
                o.set_editor_property(k, v)
            except Exception:
                pass
        res = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, o)
        sm = res[0] if isinstance(res, (tuple, list)) else res
    bs = sm.get_editor_property("body_setup")
    if bs:
        bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if collide else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
    for i, m in enumerate(mats):
        if m:
            sm.set_material(i, m)
    EAL.save_loaded_asset(sm)
    return sm, how


def finish_mesh(dm, uv_scale=100.0):
    unreal.GeometryScript_Normals.set_per_vertex_normals(dm)
    unreal.GeometryScript_UVs.set_mesh_u_vs_from_box_projection(dm, 0, unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(uv_scale, uv_scale, uv_scale)),
                                                                unreal.GeometryScriptMeshSelection())
    return dm


def terrain_materials(tiles):
    """The terrain tiles' own material instances (MI_Terrain_i_j: the aerial photo by world position), in tile order:
    berm triangles take the material of the tile they stand in, so they show the same picture as the ground."""
    EAL = unreal.EditorAssetLibrary
    mats = []
    for t in tiles:
        p = f"/Game/McGregor/Materials/MI_Terrain_{t['i']}_{t['j']}"
        mats.append(EAL.load_asset(p) if EAL.does_asset_exist(p) else None)
    return mats


def tile_index(tiles):
    idx = {(t["i"], t["j"]): k for k, t in enumerate(tiles)}
    return lambda x, y: idx.get(tile_of(x, y), 0)


# ------------------------------------------------------------------ roads draped on the terrain
ROAD_LIFT = {"asphalt": (0.012, 0.030), "caliche": (0.010, 0.025), "dirt": (0.008, 0.020)}   # (edges, crown) m over the terrain
ROAD_STEP = 2.0          # cross-sections every ~2 m along the road
ROAD_CLEAR = 0.006       # the terrain must stay at least this far under any cell centre or edge midpoint
ROAD_SMOOTH = 0          # passes of fill-only smoothing: round the terrain's crests under a road by filling round them
ROAD_RAISE = "crown"     # where the terrain would poke through a cell: lift its crown-side corners ("crown") or all four
ROAD_COLS = None         # points across every road (None: 3 up to 7 m wide, 4 up to 9.5 m, else 5)


def _unit(dx, dy):
    L = math.hypot(dx, dy)
    return (dx / L, dy / L) if L > 1e-9 else (0.0, 0.0)


def road_rows(pts, w, step=None):
    """Cross-sections of one road polyline: rows of (x, y) from the right edge to the left edge. The edges are offset
    along the corner bisector with a mitre (constant width round bends, up to 1.67x at sharp corners); between the
    OSM vertices they are straight, as the old swept ribbon's were."""
    step = step or ROAD_STEP
    q = [tuple(pts[0])]
    for p in pts[1:]:
        if math.dist(p, q[-1]) > 0.05:
            q.append(tuple(p))
    n = len(q)
    if n < 2:
        return []
    hw = w / 2.0
    nrm = []
    for k in range(n):
        if k == 0:
            t, m = _unit(q[1][0] - q[0][0], q[1][1] - q[0][1]), 1.0
        elif k == n - 1:
            t, m = _unit(q[-1][0] - q[-2][0], q[-1][1] - q[-2][1]), 1.0
        else:
            t1 = _unit(q[k][0] - q[k - 1][0], q[k][1] - q[k - 1][1])
            t2 = _unit(q[k + 1][0] - q[k][0], q[k + 1][1] - q[k][1])
            s = (t1[0] + t2[0], t1[1] + t2[1])
            if math.hypot(*s) < 1e-6:
                t, m = t1, 1.0
            else:
                t = _unit(*s)
                m = 1.0 / max(t[0] * t1[0] + t[1] * t1[1], 0.6)
        nrm.append((-t[1] * m, t[0] * m))
    cols = ROAD_COLS or (3 if w <= 7.0 else 4 if w <= 9.5 else 5)
    us = [-1.0 + 2.0 * c / (cols - 1) for c in range(cols)]
    rows = []
    for k in range(n - 1):
        L = math.dist(q[k], q[k + 1])
        m = max(1, int(math.ceil(L / step - 1e-6)))
        for s in range(m + (1 if k == n - 2 else 0)):
            f = s / m
            cx, cy = q[k][0] + (q[k + 1][0] - q[k][0]) * f, q[k][1] + (q[k + 1][1] - q[k][1]) * f
            nx, ny = nrm[k][0] + (nrm[k + 1][0] - nrm[k][0]) * f, nrm[k][1] + (nrm[k + 1][1] - nrm[k][1]) * f
            rows.append([(cx + nx * hw * u, cy + ny * hw * u) for u in us])
    return rows


def road_mesh(roads, H, mids, buf=None, stats=None):
    """All roads as one draped surface (MeshBuf). roads: mcgregor_data.json road dicts; H: terrain height (m) at (x, y);
    mids: surface -> material id. The first and last rows sit at the edge lift (no lip at road ends)."""
    buf = buf or MeshBuf()
    st = stats if stats is not None else {}
    st.setdefault("rows", 0)
    st.setdefault("raised_cells", 0)
    st.setdefault("max_raise_m", 0.0)
    for r in roads:
        if r["kind"] in ("footway", "path"):
            continue
        rows = road_rows(r["pts"], r["w"])
        if len(rows) < 2:
            continue
        e_lift, c_lift = ROAD_LIFT.get(r["surface"], ROAD_LIFT["caliche"])
        cols = len(rows[0])
        nr = len(rows)
        z = []
        for i, row in enumerate(rows):
            zr = []
            for c, (x, y) in enumerate(row):
                g = H(x, y)
                if g is None:
                    g = r["z"][min(len(r["z"]) - 1, int(i * len(r["z"]) / nr))]
                edge = c in (0, cols - 1) or i in (0, nr - 1)
                zr.append(g + (e_lift if edge else c_lift))
            z.append(zr)
        if ROAD_SMOOTH:
            # fill-only smoothing: average with the neighbours along and across, never below the draped height, so
            # a convex crest of the terrain stays put and the road round it is raised a little: the crest is rounded
            # over several cells instead of one sharp bend (the car leaves the ground at sharp convex bends)
            base = [row[:] for row in z]
            for _ in range(ROAD_SMOOTH):
                zs = []
                for i in range(nr):
                    i0, i1 = max(0, i - 1), min(nr - 1, i + 1)
                    zr = []
                    for c in range(cols):
                        c0, c1 = max(0, c - 1), min(cols - 1, c + 1)
                        if c in (0, cols - 1) or i in (0, nr - 1):
                            zr.append(base[i][c])        # the outline stays on the terrain: no lip
                        else:
                            zr.append(max(base[i][c], ((z[i0][c] + 2 * z[i][c] + z[i1][c]) + (z[i][c0] + 2 * z[i][c] + z[i][c1])) / 8.0))
                    zs.append(zr)
                z = zs
        # lift what the terrain would poke through: cell centres and the outline's edge midpoints
        up = [[0.0] * cols for _ in range(nr)]

        def need(pa, pb, za, zb, ia, ib):
            mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
            g = H(mx, my)
            if g is None:
                return
            d = g + ROAD_CLEAR - (za + zb) / 2
            if d > 0:
                for (ii, cc) in (ia, ib):
                    up[ii][cc] = max(up[ii][cc], d)
        for i in range(nr - 1):
            for c in range(cols - 1):
                ctr = [rows[i][c], rows[i][c + 1], rows[i + 1][c + 1], rows[i + 1][c]]
                mx, my = sum(p[0] for p in ctr) / 4, sum(p[1] for p in ctr) / 4
                g = H(mx, my)
                if g is not None:
                    d = g + ROAD_CLEAR - (z[i][c] + z[i][c + 1] + z[i + 1][c + 1] + z[i + 1][c]) / 4
                    if d > 0:
                        # lift the crown side of the cell, not its edge (an edge lifted is a lip to hit)
                        st["raised_cells"] += 1
                        cs = ((i, c), (i, c + 1), (i + 1, c + 1), (i + 1, c))
                        inner = [(ii, cc) for ii, cc in cs if 0 < cc < cols - 1 and 0 < ii < nr - 1] if ROAD_RAISE == "crown" else []
                        for (ii, cc) in (inner or cs):
                            up[ii][cc] = max(up[ii][cc], min(d * 4.0 / len(inner), 0.15) if inner else d)
            for c in (0, cols - 1):
                need(rows[i][c], rows[i + 1][c], z[i][c], z[i + 1][c], (i, c), (i + 1, c))
        for i in (0, nr - 1):
            for c in range(cols - 1):
                need(rows[i][c], rows[i][c + 1], z[i][c], z[i][c + 1], (i, c), (i, c + 1))
        mid = mids.get(r["surface"], 0)
        ids = []
        for i in range(nr):
            ids.append([buf.add(rows[i][c][0], rows[i][c][1], z[i][c] + up[i][c]) for c in range(cols)])
            st["max_raise_m"] = max(st["max_raise_m"], max(up[i]))
        # quads: a back-right, b back-left, c front-left, d front-right; CCW from above = a d c b
        for i in range(nr - 1):
            for c in range(cols - 1):
                a, b, cc, d = ids[i][c], ids[i][c + 1], ids[i + 1][c + 1], ids[i + 1][c]
                buf.tri(mid, a, d, cc)
                buf.tri(mid, a, cc, b)
        st["rows"] += nr
    return buf


# ------------------------------------------------------------------ berms round raised pads and lots
BERM_SEGS = ((0.8, 1.5), (0.8, 3.0), (0.8, 4.5), (0.8, 6.0))   # (length m, slope deg) outward from the pad's top edge
BERM_SLOPE = 1.0 / 8.0     # then straight at 1:8 (7.1 deg) ...
BERM_SINK = 0.10           # ... until this far under the terrain
BERM_MAX = 40.0            # never wider than this
BERM_FAN = 15.0            # convex corners: a fan of profiles every this many degrees (a rounded corner, no hip)


def berm_profile(H, x, y, nx, ny, z0, sink=BERM_SINK):
    """Vertices (x, y, z) of one berm profile from the pad's top edge (x, y, z0) outward along (nx, ny) (unit, or
    stretched by a mitre at concave corners)."""
    out = [(x, y, z0)]
    d, z = 0.0, z0
    for L, a in BERM_SEGS:
        d += L
        z -= L * math.tan(math.radians(a))
        out.append((x + nx * d, y + ny * d, z))
    dt = 0.05
    for _ in range(4):                     # the toe: 1:8 down to `sink` under the terrain there (it moves with dt)
        g = H(x + nx * (d + dt), y + ny * (d + dt))
        if g is None:
            break
        dt = max(0.05, min(BERM_MAX - d, (z - (g - sink)) / BERM_SLOPE))
    out.append((x + nx * (d + dt), y + ny * (d + dt), z - dt * BERM_SLOPE))
    return out


def ccw(loop, tops):
    a = sum(loop[k][0] * loop[(k + 1) % len(loop)][1] - loop[(k + 1) % len(loop)][0] * loop[k][1] for k in range(len(loop)))
    return (loop, tops) if a > 0 else (loop[::-1], tops[::-1])


def berm_mesh(loop, tops, H, mat_of, buf=None, stats=None, sink=BERM_SINK, closed=True):
    """A berm all round the closed outline `loop` [(x, y)] whose top edge heights are `tops` (the pad's surface at
    those points: the berm's top edge IS the pad's edge, no step). mat_of(x, y) -> material id (the terrain tile).
    Returns the MeshBuf; stats get the edge heights over the terrain and the widths."""
    buf = buf or MeshBuf()
    st = stats if stats is not None else {}
    q, qt = [], []
    for p, z in zip(loop, tops):                  # drop near-duplicate points
        if not q or math.dist(p, q[-1]) > 0.02:
            q.append(tuple(p))
            qt.append(z)
    if closed and len(q) > 3 and math.dist(q[0], q[-1]) <= 0.02:
        q.pop()
        qt.pop()
    if closed:
        q, qt = ccw(q, qt)                        # open polylines: the caller gives them with the pad on the left
    n = len(q)
    if n < (3 if closed else 2):
        return buf
    en = []
    for i in range(n if closed else n - 1):
        dx, dy = q[(i + 1) % n][0] - q[i][0], q[(i + 1) % n][1] - q[i][1]
        L = math.hypot(dx, dy) or 1.0
        en.append((dy / L, -dx / L))              # outward = right of the edge for a CCW loop
    profs = []                                    # (top vertex key, [vertex ids])
    heights, widths = [], []
    for i in range(n):
        n0 = en[i - 1] if (closed or i > 0) else en[0]
        n1 = en[i] if (closed or i < n - 1) else en[-1]
        ang = math.atan2(n0[0] * n1[1] - n0[1] * n1[0], n0[0] * n1[0] + n0[1] * n1[1])     # > 0: convex corner
        dirs = []
        if ang > math.radians(BERM_FAN):
            k = int(math.ceil(ang / math.radians(BERM_FAN)))
            for s in range(k + 1):
                a = math.atan2(n0[1], n0[0]) + ang * s / k
                dirs.append((math.cos(a), math.sin(a)))
        else:
            bx, by = n0[0] + n1[0], n0[1] + n1[1]
            L = math.hypot(bx, by) or 1.0
            m = 1.0 / max(math.cos(ang / 2.0), 0.5)
            dirs.append((bx / L * m, by / L * m))
        g = H(*q[i])
        if g is not None:
            heights.append(qt[i] - g)
        top = None
        for d in dirs:
            pv = berm_profile(H, q[i][0], q[i][1], d[0], d[1], qt[i], sink)
            ids = [buf.add(*v) for v in pv]
            if top is None:
                top = ids[0]
            else:
                ids[0] = top                      # a fan shares the corner's top vertex
            profs.append(ids)
            widths.append(math.dist(pv[0][:2], pv[-1][:2]))
    m = len(profs)
    for k in range(m if closed else m - 1):
        A, B = profs[k], profs[(k + 1) % m]
        for s in range(len(A) - 1):
            a0, a1, b0, b1 = A[s], A[s + 1], B[s], B[s + 1]
            cx = (buf.v[a1][0] + buf.v[b1][0]) / 2
            cy = (buf.v[a1][1] + buf.v[b1][1]) / 2
            mid = mat_of(cx, cy)
            # A then B runs along the loop (CCW); s goes outward: a0 b0 b1 a1 is clockwise from above -> reverse it
            buf.tri(mid, a0, a1, b1)
            buf.tri(mid, a0, b1, b0)
    if heights:
        hs = sorted(heights)
        st.setdefault("edge_over_terrain_m", []).append({"min": round(hs[0], 3), "median": round(hs[len(hs) // 2], 3), "max": round(hs[-1], 3)})
    if widths:
        st.setdefault("width_m", []).append({"min": round(min(widths), 2), "max": round(max(widths), 2)})
    return buf


# ------------------------------------------------------------------ polygons
def inside(p, ring):
    c = False
    for k in range(len(ring)):
        (x1, y1), (x2, y2) = ring[k], ring[(k + 1) % len(ring)]
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def clip_to_box(poly, x0, y0, x1, y1):
    """Sutherland-Hodgman: the polygon clipped to an axis-aligned box (a convex window)."""
    def clip(pts, inside_fn, cross_fn):
        out = []
        for k in range(len(pts)):
            a, b = pts[k - 1], pts[k]
            ia, ib = inside_fn(a), inside_fn(b)
            if ib:
                if not ia:
                    out.append(cross_fn(a, b))
                out.append(b)
            elif ia:
                out.append(cross_fn(a, b))
        return out

    def cx(xv):
        return lambda a, b: (xv, a[1] + (b[1] - a[1]) * (xv - a[0]) / (b[0] - a[0]))

    def cy(yv):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (yv - a[1]) / (b[1] - a[1]), yv)
    p = list(poly)
    for fn, cr in ((lambda q: q[0] >= x0, cx(x0)), (lambda q: q[0] <= x1, cx(x1)), (lambda q: q[1] >= y0, cy(y0)), (lambda q: q[1] <= y1, cy(y1))):
        if not p:
            break
        p = clip(p, fn, cr)
    return p


def ears(ring):
    """Ear-clipping triangulation of a simple polygon -> index triples, counter-clockwise."""
    idx = list(range(len(ring)))
    area = sum(ring[k][0] * ring[(k + 1) % len(ring)][1] - ring[(k + 1) % len(ring)][0] * ring[k][1] for k in range(len(ring)))
    if area < 0:
        idx.reverse()
    out, guard = [], 0
    while len(idx) > 3 and guard < 4 * len(ring) + 10:
        guard += 1
        for k in range(len(idx)):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            (ax, ay), (bx, by), (cx_, cy_) = ring[a], ring[b], ring[c]
            if (bx - ax) * (cy_ - ay) - (by - ay) * (cx_ - ax) <= 1e-12:
                continue
            if any(inside(ring[o], [ring[a], ring[b], ring[c]]) for o in idx if o not in (a, b, c)):
                continue
            out.append((a, b, c))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        out.append(tuple(idx))
    return out


def osm_rings(way_ids, meta, osm_path=None):
    """OSM closed ways -> rings in local metres (same projection as site_layout.py's osm_ring)."""
    import json
    osm_path = osm_path or os.path.join(_skycity_root(), "SourceArt", "osm", "mcgregor.json")
    want = set(way_ids)
    res = {}
    for e in json.load(open(osm_path))["elements"]:
        if e.get("type") == "way" and e.get("id") in want and e.get("geometry"):
            g = [((p["lon"] - meta["lon0"]) * meta["kx"], (p["lat"] - meta["lat0"]) * meta["ky"]) for p in e["geometry"] if p]
            if len(g) > 3 and math.dist(g[0], g[-1]) < 0.5:
                g = g[:-1]
            res[e["id"]] = g
    return res


def draped_lot(ring, z_of, step=4.0):
    """A parking lot draped on the ground like site_layout.py's lot_pad (a 4 m grid, z_of(x, y) at every vertex), but
    clipped to the lot's real outline instead of a staircase of whole cells. Returns (MeshBuf with material 0,
    boundary loop [(x, y)] in order, its heights): the loop is the ring plus every point where it crosses a grid line,
    exactly the surface's own boundary vertices, so a berm built on it meets the lot with no step."""
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    gx0, gy0 = min(xs), min(ys)
    nx_, ny_ = int((max(xs) - gx0) / step) + 2, int((max(ys) - gy0) / step) + 2
    buf = MeshBuf()
    vid = {}

    def V(x, y):
        k = (round(x, 3), round(y, 3))
        if k not in vid:
            vid[k] = buf.add(x, y, z_of(x, y))
        return vid[k]
    for i in range(nx_):
        for j in range(ny_):
            x0, y0 = gx0 + i * step, gy0 + j * step
            x1, y1 = x0 + step, y0 + step
            corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            if all(inside(c, ring) for c in corners) and not any(x0 < p[0] < x1 and y0 < p[1] < y1 for p in ring) and \
                    not any(_seg_box(ring[k], ring[(k + 1) % len(ring)], x0, y0, x1, y1) for k in range(len(ring))):
                a, b, c, d = (V(*p) for p in corners)
                buf.tri(0, a, b, c)
                buf.tri(0, a, c, d)
                continue
            piece = clip_to_box(ring, x0, y0, x1, y1)
            if len(piece) < 3:
                continue
            pc = []
            for p in piece:
                if not pc or math.dist(p, pc[-1]) > 1e-4:
                    pc.append(p)
            if len(pc) > 3 and math.dist(pc[0], pc[-1]) <= 1e-4:
                pc.pop()
            if len(pc) < 3 or abs(sum(pc[k][0] * pc[(k + 1) % len(pc)][1] - pc[(k + 1) % len(pc)][0] * pc[k][1] for k in range(len(pc)))) < 1e-4:
                continue
            ids = [V(*p) for p in pc]
            for a, b, c in ears(pc):
                buf.tri(0, ids[a], ids[b], ids[c])
    # the boundary: ring vertices plus its crossings of the grid lines, in ring order
    loop = []
    for k in range(len(ring)):
        a, b = ring[k], ring[(k + 1) % len(ring)]
        pts = [(0.0, a)]
        for axis, g0 in ((0, gx0), (1, gy0)):
            lo, hi = sorted((a[axis], b[axis]))
            m0 = int(math.floor((lo - g0) / step)) + 1
            m = m0
            while g0 + m * step < hi:
                v = g0 + m * step
                t = (v - a[axis]) / (b[axis] - a[axis])
                if 1e-6 < t < 1 - 1e-6:
                    pts.append((t, (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)))
                m += 1
        pts.sort()
        loop += [p for _, p in pts]
    tops = [z_of(*p) for p in loop]
    return buf, loop, tops


def _seg_box(a, b, x0, y0, x1, y1):
    """Does segment ab pass through the open box?"""
    if max(a[0], b[0]) <= x0 or min(a[0], b[0]) >= x1 or max(a[1], b[1]) <= y0 or min(a[1], b[1]) >= y1:
        return False
    p = clip_to_box([a, b, b], x0 + 1e-9, y0 + 1e-9, x1 - 1e-9, y1 - 1e-9)
    return len(p) > 0
