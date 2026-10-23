"""Frontage-first lot subdivision.

A rectangular block (the usual grid face, rotated or not) gets two rows of lots
facing the long sides and an alley between them when the block is deep enough.
Corner lots also front the side street. The cuts are a function of the polygon and
the seed's target frontage only, so regenerating a block rebuilds the same lots.
"""
import geom

MIN_DEPTH = 14.0
ALLEY_MIN = 18.0


def subdivide(polygon, target_frontage=22.0, alley=5.0, seed=1):
    """Return {lots, alley}. Lots are local dicts without ids; the model assigns those."""
    polygon = geom.ensure_ccw([tuple(p) for p in polygon])
    frame = geom.rectangle_frame(polygon)
    if frame is None:
        return {"lots": [_one(polygon, _normals_from_edges(polygon))], "alley": None}
    return _rows(frame, float(target_frontage), float(alley), int(seed))


def _rows(frame, target, alley, seed):
    width, depth = frame["width"], frame["depth"]
    # Stagger the north row by half a bay when the seed is odd, so party walls
    # don't stack across the alley. The stagger is a pure function of the seed.
    stagger = (target * 0.5) if (seed % 2) else 0.0
    if depth >= alley + 2 * MIN_DEPTH:
        row_d = (depth - alley) / 2.0
        south = _split(frame, 0.0, row_d, width, target, 0.0, "s", (0.0, -1.0))
        north = _split(frame, row_d + alley, depth, width, target, stagger, "n", (0.0, 1.0))
        ay0, ay1 = row_d, row_d + alley
        alley_poly = geom.world_poly([(0, ay0), (width, ay0), (width, ay1), (0, ay1)], frame)
        # the two short ends of the alley are where it meets the side streets
        return {"lots": south + north, "alley": [list(p) for p in alley_poly]}
    lots = _split(frame, 0.0, depth, width, target, 0.0, "a", (0.0, -1.0))
    for lot in lots:
        lot["front_normals"].append([round(frame["y"][0], 4), round(frame["y"][1], 4)])
    return {"lots": lots, "alley": None}


def _split(frame, y0, y1, width, target, stagger, tag, local_normal):
    span = width
    n = max(1, int(round(span / target)))
    # A stagger shifts the cuts and keeps the end lots on the property. The shift
    # wraps by using n lots still, with the first and last absorbing it.
    shift = 0.0
    if stagger and n >= 3:
        shift = min(stagger, (span / n) * 0.45)
    cuts = [0.0]
    step = (span - 2 * shift) / n if False else span / n
    # Apply the shift by moving interior cuts only.
    for i in range(1, n):
        cuts.append(i * step + (shift if 0 < i < n else 0.0))
    cuts.append(span)
    # Re-clamp in case the shift pushed a cut past the end.
    cuts = [0.0] + sorted(min(span - 0.5, max(0.5, c)) for c in cuts[1:-1]) + [span]
    # If the shift collapsed two cuts, fall back to even cuts.
    if any(cuts[i + 1] - cuts[i] < target * 0.45 for i in range(len(cuts) - 1)):
        cuts = [i * span / n for i in range(n + 1)]
    lots = []
    normal = [round(local_normal[0] * frame["x"][0] + local_normal[1] * frame["y"][0], 4),
              round(local_normal[0] * frame["x"][1] + local_normal[1] * frame["y"][1], 4)]
    side_out = {
        "w": [-round(frame["x"][0], 4), -round(frame["x"][1], 4)],
        "e": [round(frame["x"][0], 4), round(frame["x"][1], 4)],
    }
    for i in range(len(cuts) - 1):
        a, b = cuts[i], cuts[i + 1]
        local = [(a, y0), (b, y0), (b, y1), (a, y1)]
        if local_normal[1] < 0:
            # south row: local +y is into the lot, polygon above is already CCW
            pass
        else:
            # north row was built with y0 < y1 still CCW
            pass
        poly = geom.world_poly(local, frame)
        fronts = [normal]
        if i == 0:
            fronts.append(side_out["w"])
        if i == len(cuts) - 2:
            fronts.append(side_out["e"])
        lots.append({
            "tag": "%s%d" % (tag, i),
            "polygon": [list(p) for p in poly],
            "front_normals": fronts,
            "role": "lot",
        })
    return lots


def _one(polygon, normals):
    return {"tag": "a0", "polygon": [list(geom.r2(p)) for p in polygon], "front_normals": normals, "role": "lot"}


def _normals_from_edges(polygon):
    # longest edge's outward normal, so a non-rectangular face still has a front
    best = None
    best_l = -1
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        L = geom.dist(a, b)
        if L > best_l:
            d = geom.unit(geom.sub(b, a))
            best = [round(d[1], 4), round(-d[0], 4)]
            best_l = L
    return [best or [0.0, -1.0]]
