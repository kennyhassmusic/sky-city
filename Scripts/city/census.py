"""Per-building census for the city meshes.

Counts non-manifold edges, loose vertices, degenerate faces and
self-intersections (BVHTree.overlap, skipping faces that share a vertex).
The plan check is separate: the footprint and the height have to match the
spec, and the lowest vertex has to sit on the ground the wall was built for.
That ground is the sidewalk, not the lane. A base above it is a floating
building.

The dimension check runs without Blender:

  python3 -I Scripts/city/test_census.py

The topology counts run inside Blender, next to the UV test in blender_city.py.
"""
BASE_TOL_M = 0.05
FOOT_TOL_M = 0.45
# Bottom of the walls, not the cornice or the first balcony.
GROUND_BAND_M = 0.5
# Below this, a face is a sliver rather than a pane.
DEGEN_AREA_M2 = 1e-8
# Roof clutter above the deck: a parapet, plus an antenna about 8 m tall.
CLUTTER_M = 9.0


def footprint_bounds(spec):
    pts = [(float(p[0]), float(p[1])) for p in (spec.get("footprint") or [])]
    if len(pts) < 3:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def expected_deck(spec, ground_z):
    """Lane-relative height, lifted onto the sidewalk. Roof height sits above this deck."""
    height = float(spec.get("height") or 0.0)
    roof_h = float((spec.get("roof") or {}).get("h") or 0.0)
    return float(ground_z) + height - roof_h, roof_h


def check_dimensions(verts, spec, ground_z):
    """verts are (x, y, z) in plan metres. reasons is empty when the mass matches."""
    reasons = []
    if not verts:
        return _empty(ground_z, ["empty"])
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    base = min(zs)
    top = max(zs)
    if abs(base - float(ground_z)) > BASE_TOL_M:
        reasons.append("base %.3f ground %.3f" % (base, float(ground_z)))
    band = [v for v in verts if v[2] <= base + GROUND_BAND_M]
    if len(band) < 3:
        band = verts
    bxs = [v[0] for v in band]
    bys = [v[1] for v in band]
    foot = footprint_bounds(spec)
    if foot is None:
        reasons.append("footprint missing")
    else:
        mesh_box = (min(bxs), min(bys), max(bxs), max(bys))
        for mesh_v, foot_v, label in zip(mesh_box, foot, ("minx", "miny", "maxx", "maxy")):
            if abs(mesh_v - foot_v) > FOOT_TOL_M:
                reasons.append("footprint %s mesh %.2f plan %.2f" % (label, mesh_v, foot_v))
    deck, roof_h = expected_deck(spec, ground_z)
    parapet = float(spec.get("parapet_m") or 1.1)
    if top < deck - 0.5:
        reasons.append("height short top %.2f deck %.2f" % (top, deck))
    allow = max(parapet, roof_h) + CLUTTER_M
    if top > deck + allow:
        reasons.append("height tall top %.2f deck %.2f" % (top, deck))
    return {
        "reasons": reasons,
        "base": base,
        "top": top,
        "deck": deck,
        "ground": float(ground_z),
        "minx": min(bxs),
        "miny": min(bys),
        "maxx": max(bxs),
        "maxy": max(bys),
    }


def _empty(ground_z, reasons):
    return {
        "reasons": reasons,
        "base": 0.0,
        "top": 0.0,
        "deck": float(ground_z),
        "ground": float(ground_z),
        "minx": 0.0,
        "miny": 0.0,
        "maxx": 0.0,
        "maxy": 0.0,
    }


def format_line(name, report):
    state = "PASS" if not report.get("reasons") else "FAIL " + "; ".join(report["reasons"])
    return (
        "CENSUS %s faces %d nonmanifold %d loose %d degenerate %d intersect %d "
        "base %.3f ground %.3f top %.2f deck %.2f %s"
        % (
            name,
            int(report.get("faces") or 0),
            int(report.get("nonmanifold") or 0),
            int(report.get("loose") or 0),
            int(report.get("degenerate") or 0),
            int(report.get("intersect") or 0),
            float(report.get("base") or 0),
            float(report.get("ground") or 0),
            float(report.get("top") or 0),
            float(report.get("deck") or 0),
            state,
        )
    )


def survey_object(ob, spec, ground_z):
    """Topology plus the plan check. Modifiers are applied through the depsgraph first."""
    import bmesh
    from mathutils.bvhtree import BVHTree

    mesh, clear = _evaluated_mesh(ob)
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        loose = sum(1 for vert in bm.verts if not vert.link_edges)
        degenerate = sum(1 for face in bm.faces if face.calc_area() < DEGEN_AREA_M2)
        # One face is a boundary (the shell is open). Three or more, or a wire, is not.
        nonmanifold = sum(1 for edge in bm.edges if not edge.is_manifold and not edge.is_boundary)
        verts = [(vert.co.x, vert.co.y, vert.co.z) for vert in bm.verts]
        report = check_dimensions(verts, spec, ground_z)
        report["faces"] = len(bm.faces)
        report["loose"] = loose
        report["degenerate"] = degenerate
        report["nonmanifold"] = nonmanifold
        report["intersect"] = _self_intersections(bm, BVHTree)
        # Stacked boxes share welded vertices, so a non-manifold edge or a
        # BVH overlap is counted and printed. The build stops on an empty mesh,
        # a floating or sunk base, a footprint or height that misses the plan,
        # a loose vertex, or a degenerate face.
        if loose:
            report["reasons"].append("loose %d" % loose)
        if degenerate:
            report["reasons"].append("degenerate %d" % degenerate)
        return report
    finally:
        bm.free()
        if clear is not None:
            clear()


def _evaluated_mesh(ob):
    """Object data, or the modifier result from evaluated_get().to_mesh()."""
    if not ob.modifiers:
        return ob.data, None
    import bpy
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_ob = ob.evaluated_get(depsgraph)
    mesh = eval_ob.to_mesh()

    def clear():
        eval_ob.to_mesh_clear()

    return mesh, clear


def _self_intersections(bm, BVHTree):
    if not bm.faces:
        return 0
    tree = BVHTree.FromBMesh(bm, epsilon=1e-6)
    pairs = tree.overlap(tree)
    if not pairs:
        return 0
    bm.faces.ensure_lookup_table()
    owners = [frozenset(vert.index for vert in face.verts) for face in bm.faces]
    count = 0
    for i, j in pairs:
        if i >= j:
            continue
        if owners[i].isdisjoint(owners[j]):
            count += 1
    return count
