"""Mesh the generated city with the same facade, roof and storefront builder as the CG_* blocks.

Downtown (Chicago core) is meshed first, then one Austin low-rise street whose
lots carry different income tiers. Buildings are written in small GLBs so a
pull request stays under the LFS cap. Street surfaces in each shot are clipped
to that block, and dressing props are simple meshes (no trees).

The GLB vertices are the block exporter's -90 degree Z turn, baked in, so
Unreal imports them at the world origin: plan north on +X, plan east on +Y.

Run:
  blender -b --factory-startup -P Scripts/city/blender_city.py
Output:
  SourceArt/CityGen/city/CG_<district>_<index>.glb
  SourceArt/CityGen/city/CG_<district>_street_<index>.glb
  SourceArt/CityGen/city/city_manifest.json
  /opt/cursor/artifacts/previews/sky_city_downtown_aerial.png
  /opt/cursor/artifacts/previews/sky_city_downtown_street.png
  /opt/cursor/artifacts/previews/sky_city_residential_street.png

SKYCITY_BUDGET_MB (default 220) stops the export. SKYCITY_CORE_MAX and
SKYCITY_RES_MAX cap how many buildings are even considered.
"""
import json
import math
import os
import sys
import time

import bpy

CITY = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("SKYCITY_ROOT") or os.path.dirname(os.path.dirname(CITY))
sys.path.insert(0, CITY)
sys.path.insert(0, os.path.join(ROOT, "Scripts", "streets"))
sys.path.insert(0, os.path.join(ROOT, "Scripts", "roads"))

import blender_block as bb  # noqa: E402
import generate_city  # noqa: E402
import geom  # noqa: E402
import model as model_mod  # noqa: E402
import profiles  # noqa: E402
import realism  # noqa: E402

OUT = os.path.join(ROOT, "SourceArt", "CityGen", "city")
PREVIEWS = os.environ.get("SKYCITY_PREVIEWS") or "/opt/cursor/artifacts/previews"
BUDGET = int(os.environ.get("SKYCITY_BUDGET_MB", "220")) * 1024 * 1024
FILE_CAP = 22 * 1024 * 1024
CORE_MAX = int(os.environ.get("SKYCITY_CORE_MAX", "22"))
RES_MAX = int(os.environ.get("SKYCITY_RES_MAX", "12"))
CORE_RADIUS = 170.0
RES_RADIUS = 70.0

DRESS = {
    "lamp", "bench", "bin", "hydrant", "signal", "stop", "yield",
    "street_name", "bus_stop", "parked", "drain", "bollard", "grate",
    "sign", "fence",
}


def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PREVIEWS, exist_ok=True)
    print("CITY build", flush=True)
    city = generate_city.build_from_disk()
    digest = model_mod.manifest_hash(city)
    print("CITY hash", digest, "seconds", round(time.time() - t0, 1), flush=True)
    lots = {lot["id"]: lot for lot in city.get("lots") or []}
    tier_counts = {}
    for spec in city.get("buildings") or []:
        if _district(city, spec) != "austin_low":
            continue
        tier_counts[_tier(spec, lots) or "none"] = tier_counts.get(_tier(spec, lots) or "none", 0) + 1
    print("AUSTIN TIERS", tier_counts, flush=True)
    anchor, core = _select_core(city)
    pair, residential = _select_residential(city, lots)
    core = core[:CORE_MAX]
    residential = residential[:RES_MAX]
    tier_names = [_tier(spec, lots) for spec in residential]
    print("CITY core", len(core), "of", _count(city, "chicago_core"),
          "residential", len(residential), "tiers", tier_names, flush=True)
    bb.reset()
    lib = bb.make_library(bb.load_material_record())
    protos = _prototypes(lib)
    core_col = bb.collection("CoreBuildings")
    res_col = bb.collection("ResBuildings")
    core_obs = _mesh_list(core, lib, core_col, keep_tall_rooms=False)
    res_obs = _mesh_list(residential, lib, res_col, keep_tall_rooms=True)
    core_bounds = _bounds(core, 28.0)
    res_bounds = _bounds(residential, 22.0)
    core_street = _street(city, core_bounds, lib, protos, "CoreStreet")
    res_street = _street(city, res_bounds, lib, protos, "ResStreet")
    cams = _cameras(anchor, pair, core, residential)
    _render(cams, core_obs, core_street, res_obs, res_street)
    files, spent = _export_all(core, core_obs, core_street, residential, res_obs, res_street)
    manifest = {
        "seed": int(city.get("seed") or generate_city.SEED),
        "hash": digest,
        "frame": "Baked -90 Z, same turn as the CG block GLBs. Plan metres. Actor at the origin.",
        "budget_bytes": BUDGET,
        "bytes": spent,
        "chicago_core_total": _count(city, "chicago_core"),
        "chicago_core_meshed": len(core_obs),
        "austin_low_meshed": len(res_obs),
        "tiers": [_tier(spec, lots) for spec in residential],
        "cameras": cams,
        "files": files,
        "note": "Chicago core around one downtown street, then one residential street. The rest of the city is the spawn record until a larger budget is set.",
    }
    path = os.path.join(OUT, "city_manifest.json")
    with open(path, "w") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    print("CITY done", len(files), "files", round(spent / (1024 * 1024), 1), "MB",
          round(time.time() - t0, 1), "s", flush=True)


def _count(city, name):
    return sum(1 for spec in city.get("buildings") or [] if _district(city, spec) == name)


def _district(city, spec):
    wanted = spec.get("district_id")
    for district in city.get("districts") or []:
        if district.get("id") == wanted:
            return district.get("name") or ""
    return ""


def _tier(spec, lots):
    return (lots.get(spec.get("lot_id")) or {}).get("tier") or ""


def _centre(spec):
    pts = [(float(p[0]), float(p[1])) for p in spec.get("footprint") or []]
    if not pts:
        return (0.0, 0.0)
    return geom.centroid(pts)


def _select_core(city):
    named = []
    for spec in city.get("buildings") or []:
        if spec.get("role") == "landmark" or not spec.get("floors") or not spec.get("facades"):
            continue
        if _district(city, spec) == "chicago_core":
            named.append(spec)
    best = None
    for spec in named:
        height = float(spec.get("height") or 0)
        if height < 16 or height > 64:
            continue
        centre = _centre(spec)
        near = sum(1 for other in named if other is not spec and geom.dist(centre, _centre(other)) < 48)
        rank = (near, -abs(height - 30))
        if best is None or rank > best[0]:
            best = (rank, spec)
    anchor = best[1] if best else max(named, key=lambda spec: float(spec.get("height") or 0))
    origin = _centre(anchor)
    cluster = [spec for spec in named if geom.dist(_centre(spec), origin) <= CORE_RADIUS]
    cluster.sort(key=lambda spec: geom.dist(_centre(spec), origin))
    if anchor not in cluster:
        cluster.insert(0, anchor)
    return anchor, cluster


def _select_residential(city, lots):
    named = []
    for spec in city.get("buildings") or []:
        if not spec.get("floors") or not spec.get("facades"):
            continue
        if _district(city, spec) != "austin_low":
            continue
        if _tier(spec, lots):
            named.append(spec)
    best = None
    for left in named:
        left_tier = _tier(left, lots)
        if left_tier not in ("high", "low", "distressed", "mid"):
            continue
        for right in named:
            right_tier = _tier(right, lots)
            if right is left or right_tier == left_tier:
                continue
            if right_tier not in ("high", "low", "distressed", "mid"):
                continue
            span = geom.dist(_centre(left), _centre(right))
            if span < 8 or span > 45:
                continue
            kinds = {left_tier, right_tier}
            # Neighbours along the income axis. High beside mid reads in one frame.
            rank = 0 if "high" in kinds else 1 if "distressed" in kinds else 2
            key = (rank, span)
            if best is None or key < best[0]:
                best = (key, left, right)
    if best is None:
        origin = _centre(named[0]) if named else (0.0, 0.0)
        cluster = sorted(named, key=lambda spec: geom.dist(_centre(spec), origin))[:RES_MAX]
        return (cluster[0] if cluster else None, None), cluster
    _rank, left, right = best
    mid = geom.lerp(_centre(left), _centre(right), 0.5)
    cluster = [spec for spec in named if geom.dist(_centre(spec), mid) <= RES_RADIUS]
    cluster.sort(key=lambda spec: geom.dist(_centre(spec), mid))
    for spec in (left, right):
        if spec not in cluster:
            cluster.insert(0, spec)
    return (left, right), cluster


def _prototypes(lib):
    import blender_street_kit as kit
    made = {}
    for key, build in (("lamp", kit.street_lamp), ("drain", kit.storm_drain), ("bollard", kit.bollard)):
        ob = build(do_export=False)
        ob.hide_render = True
        ob.hide_set(True)
        made[key] = ob
    made["bench"] = bb._bench()
    made["hydrant"] = bb._hydrant()
    made["signal"] = bb._signal()
    made["stop"] = bb._blade_sign((0.62, 0.08, 0.07), "SK_Stop")
    made["yield"] = bb._blade_sign((0.86, 0.68, 0.12), "SK_Yield")
    made["street_name"] = bb._blade_sign((0.12, 0.32, 0.22), "SK_StreetName")
    made["bus_stop"] = bb._blade_sign((0.12, 0.28, 0.48), "SK_BusStop")
    made["parked"] = bb._parked_car()
    made.update(realism.prototypes(lib, bb.Mesh))
    made["fence_iron"] = _fence("SK_FenceIron", "iron")
    made["fence_wood"] = _fence("SK_FenceWood", "wood")
    return made


def _fence(name, style):
    mesh = bb.Mesh(name)
    metal = bb.flat("M_FenceIron", (0.16, 0.17, 0.18), 0.4)
    wood = bb.flat("M_FenceWood", (0.36, 0.24, 0.14), 0.65)
    mat = metal if style == "iron" else wood
    for x in (-3.5, -1.15, 1.15, 3.5):
        mesh.box((x, 0, 0.55), (1, 0, 0), (0, 1, 0), (0, 0, 1), (0.08, 0.08, 1.1), mat)
    if style == "iron":
        for z in (0.38, 0.92):
            mesh.box((0, 0, z), (1, 0, 0), (0, 1, 0), (0, 0, 1), (7.6, 0.025, 0.025), mat)
    else:
        mesh.box((0, 0, 0.55), (1, 0, 0), (0, 1, 0), (0, 0, 1), (7.4, 0.04, 0.85), mat)
    ob = mesh.finish(bpy.data.collections["Prototypes"])
    ob.hide_render = True
    ob.hide_set(True)
    return ob


def _shell(spec, keep_tall_rooms):
    """Upper floors of a tower keep the window card. The ground floor keeps its rooms."""
    if keep_tall_rooms or float(spec.get("height") or 0) < 22:
        return spec
    copy = dict(spec)
    copy["rooms"] = [room for room in spec.get("rooms") or [] if int(room.get("floor") or 0) == 0]
    return copy


def _mesh_list(specs, lib, col, keep_tall_rooms):
    made = []
    for index, spec in enumerate(specs):
        t0 = time.time()
        ob = bb.build_lod0(_shell(spec, keep_tall_rooms), lib, col)
        made.append(ob)
        print("MESH", spec.get("id"), "h", spec.get("height"), "tris", len(ob.data.polygons),
              "s", round(time.time() - t0, 1), flush=True)
        if index + 1 >= (CORE_MAX if not keep_tall_rooms else RES_MAX):
            break
    return made


def _bounds(specs, pad):
    xs, ys = [], []
    for spec in specs:
        for point in spec.get("footprint") or []:
            xs.append(float(point[0]))
            ys.append(float(point[1]))
    if not xs:
        return (0, 0, 1, 1)
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def _inside(point, bounds):
    return bounds[0] <= point[0] <= bounds[2] and bounds[1] <= point[1] <= bounds[3]


def _hit_x(a, b, x):
    dx = b[0] - a[0]
    t = 0.0 if abs(dx) < 1e-9 else (x - a[0]) / dx
    t = max(0.0, min(1.0, t))
    return (x, a[1] + (b[1] - a[1]) * t)


def _hit_y(a, b, y):
    dy = b[1] - a[1]
    t = 0.0 if abs(dy) < 1e-9 else (y - a[1]) / dy
    t = max(0.0, min(1.0, t))
    return (a[0] + (b[0] - a[0]) * t, y)


def _clip_polygon(poly, bounds):
    """Sutherland-Hodgman clip against an axis-aligned rectangle."""
    x0, y0, x1, y1 = bounds
    pts = [(float(p[0]), float(p[1])) for p in poly]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]

    def cut(pts, inside, hit):
        if not pts:
            return []
        out = []
        prev = pts[-1]
        prev_in = inside(prev)
        for cur in pts:
            cur_in = inside(cur)
            if cur_in:
                if not prev_in:
                    out.append(hit(prev, cur))
                out.append(cur)
            elif prev_in:
                out.append(hit(prev, cur))
            prev = cur
            prev_in = cur_in
        return out

    pts = cut(pts, lambda p: p[0] >= x0 - 1e-6, lambda a, b: _hit_x(a, b, x0))
    pts = cut(pts, lambda p: p[0] <= x1 + 1e-6, lambda a, b: _hit_x(a, b, x1))
    pts = cut(pts, lambda p: p[1] >= y0 - 1e-6, lambda a, b: _hit_y(a, b, y0))
    pts = cut(pts, lambda p: p[1] <= y1 + 1e-6, lambda a, b: _hit_y(a, b, y1))
    return pts


def _clip_chain(pts, bounds):
    """Open polyline clipped to the rectangle, as one chain per visit inside the box."""
    chains = []
    current = []
    points = [(float(p[0]), float(p[1])) for p in pts]
    for index, point in enumerate(points):
        inside = _inside(point, bounds)
        if index:
            prev = points[index - 1]
            if inside != _inside(prev, bounds):
                hit = _segment_enter(prev, point, bounds)
                if hit is not None:
                    current.append(hit)
            if not inside:
                if len(current) >= 2:
                    chains.append(current)
                current = []
        if inside:
            current.append(point)
    if len(current) >= 2:
        chains.append(current)
    return chains


def _segment_enter(a, b, bounds):
    x0, y0, x1, y1 = bounds
    dx, dy = b[0] - a[0], b[1] - a[1]
    hits = []
    if abs(dx) > 1e-9:
        for x in (x0, x1):
            t = (x - a[0]) / dx
            y = a[1] + dy * t
            if 0.0 <= t <= 1.0 and y0 - 1e-6 <= y <= y1 + 1e-6:
                hits.append((t, (x, y)))
    if abs(dy) > 1e-9:
        for y in (y0, y1):
            t = (y - a[1]) / dy
            x = a[0] + dx * t
            if 0.0 <= t <= 1.0 and x0 - 1e-6 <= x <= x1 + 1e-6:
                hits.append((t, (x, y)))
    if not hits:
        return None
    hits.sort(key=lambda item: item[0])
    return hits[0][1]


def _street(city, bounds, lib, protos, name):
    col = bb.collection(name)
    made = []
    ground = bb.Mesh(name + "_Ground")
    # Wider than the block so an oblique camera sees ground, not an empty cutout.
    x0, y0, x1, y1 = bounds[0] - 600, bounds[1] - 600, bounds[2] + 600, bounds[3] + 600
    ground.prism([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], -0.55, -0.2, lib["grass"])
    made.append(ground.finish(col))
    sc = city.get("streetscape") or {}
    surfaces = sc.get("surfaces") or {}
    for kind, z0, z1, slot in (
        ("asphalt", -0.02, 0.012, "asphalt"),
        ("sidewalk", profiles.CURB_RISE - 0.04, profiles.CURB_RISE, "paving"),
        ("parkway", profiles.CURB_RISE - 0.04, profiles.CURB_RISE, "grass"),
        ("alley", profiles.CURB_RISE - 0.04, profiles.CURB_RISE, "asphalt"),
    ):
        mesh = bb.Mesh(name + "_" + kind)
        for index, poly in enumerate(surfaces.get(kind) or []):
            ring = _clip_polygon(poly.get("polygon") or [], bounds)
            if len(ring) >= 3:
                lift = 0.0012 * (index % 5) if kind == "asphalt" else 0.0
                mesh.prism(ring, z0 + lift, z1 + lift, lib[slot])
        if mesh.bm.faces:
            made.append(mesh.finish(col))
        else:
            mesh.bm.free()
    curbs = bb.Mesh(name + "_Curbs")
    for curb in sc.get("curb_paths") or []:
        for clipped in _clip_chain(curb.get("polyline") or [], bounds):
            piece = dict(curb)
            piece["polyline"] = clipped
            bb._sweep_curb(curbs, piece, sc.get("sections") or {}, lib["curb"])
    if curbs.bm.faces:
        made.append(curbs.finish(col))
    else:
        curbs.bm.free()
    paint = bb.Mesh(name + "_Paint")
    for cross in sc.get("crosswalks") or []:
        for mark in cross.get("marks") or []:
            ring = _clip_polygon(mark.get("polygon") or [], bounds)
            if len(ring) >= 3:
                paint.prism(ring, 0.03, 0.055, lib["lane"])
    for mark in sc.get("markings") or []:
        centre = geom.centroid([(float(p[0]), float(p[1])) for p in mark.get("polygon") or [(0, 0)]])
        if not _inside(centre, bounds):
            continue
        ring = mark.get("polygon") or []
        material = mark.get("material")
        if material == "M_Puddle":
            realism.uv_cover(paint, ring, 0.022, 0.032, lib["puddle"])
        elif material == "M_Manhole":
            realism.uv_cover(paint, ring, 0.02, 0.04, lib["manhole"])
        else:
            slot = lib["lane_yellow"] if material == "M_LanePaintYellow" else lib["lane"]
            paint.prism(ring, 0.028, 0.048, slot)
    if paint.bm.faces:
        made.append(paint.finish(col))
    else:
        paint.bm.free()
    ramps = bb.Mesh(name + "_Ramps")
    for ramp in sc.get("ramps") or []:
        if _inside((float(ramp.get("x") or 0), float(ramp.get("y") or 0)), bounds):
            bb._ramp(ramps, ramp, lib["concrete"])
    if ramps.bm.faces:
        made.append(ramps.finish(col))
    else:
        ramps.bm.free()
    props = []
    for prop in sc.get("props") or []:
        if prop.get("kind") not in DRESS:
            continue
        if _inside((float(prop.get("x") or 0), float(prop.get("y") or 0)), bounds):
            props.append(prop)
    made.extend(_place(props, protos, col, lib))
    print("STREET", name, "props", len(props), "meshes", len(made), flush=True)
    return made


def _place(props, protos, col, lib):
    made = []
    for prop in props:
        kind = prop.get("kind")
        if kind == "fence":
            style = prop.get("style") or "wood"
            src = protos.get("fence_iron" if style == "iron" else "fence_wood")
            yaw = math.radians(float(prop.get("yaw") or 0))
            z = profiles.CURB_RISE
        elif kind == "sign":
            src = protos.get("sign_" + (prop.get("label") or "CAFE"))
            yaw = bb._yaw_to_road(prop)
            z = profiles.CURB_RISE
        else:
            src = protos.get(kind)
            yaw = bb._yaw_to_road(prop)
            if kind == "drain":
                z = 0.02
            elif kind == "parked":
                z = 0.28
            else:
                z = profiles.CURB_RISE
        if src is None:
            continue
        ob = bpy.data.objects.new(str(prop.get("id") or kind)[:60], src.data)
        ob.location = (float(prop["x"]), float(prop["y"]), z)
        ob.rotation_euler = (0.0, 0.0, yaw)
        col.objects.link(ob)
        made.append(ob)
    wires = bb.Mesh("Wires")
    realism.wires(wires, props, lib["metal"])
    if wires.bm.faces:
        made.append(wires.finish(col))
    else:
        wires.bm.free()
    return made


def _longest_facade(spec):
    faces = spec.get("facades") or []
    return max(faces, key=lambda face: float(face.get("length") or 0))


def _inside_any(specs, x, y):
    for spec in specs:
        poly = [(float(p[0]), float(p[1])) for p in spec.get("footprint") or []]
        if len(poly) >= 3 and geom.point_in_poly((x, y), poly):
            return True
    return False


def _eye_outside(specs, origin, normal, other, dist):
    """A sidewalk eye: outside every footprint, looking toward the neighbour."""
    best = None
    for sign in (1.0, -1.0):
        n = (normal[0] * sign, normal[1] * sign)
        x, y = origin[0] + n[0] * dist, origin[1] + n[1] * dist
        for _ in range(14):
            if not _inside_any(specs, x, y):
                break
            x += n[0] * 8.0
            y += n[1] * 8.0
        if _inside_any(specs, x, y):
            continue
        view = (other[0] - x, other[1] - y)
        score = view[0] * n[0] + view[1] * n[1]
        if best is None or score > best[0]:
            best = (score, x, y, n[0], n[1])
    if best is None:
        return origin[0] + normal[0] * dist, origin[1] + normal[1] * dist, normal[0], normal[1]
    return best[1], best[2], best[3], best[4]


def _clear_of(specs, point, normal, start):
    """Step out along the facade normal until the eye is not inside a footprint."""
    x, y = point[0] + normal[0] * start, point[1] + normal[1] * start
    for _ in range(8):
        if not any(geom.point_in_poly((x, y), spec.get("footprint") or []) for spec in specs):
            return x, y
        x += normal[0] * 6.0
        y += normal[1] * 6.0
    return x, y


def _sun_for(eye, target, elevation):
    """Key light from the camera side, so the facade in frame is the lit one."""
    dx, dy = target[0] - eye[0], target[1] - eye[1]
    # Sun direction in plan is (sin rot, cos rot). Match the view bearing.
    return {"elevation": elevation, "rotation": round(math.degrees(math.atan2(dx, dy)), 1), "strength": 1.0}


def _cameras(anchor, pair, core, residential):
    face = _longest_facade(anchor)
    ax, ay = float(face["a"][0]), float(face["a"][1])
    bx, by = float(face["b"][0]), float(face["b"][1])
    length = float(face.get("length") or 1.0) or 1.0
    tx, ty = (bx - ax) / length, (by - ay) / length
    nx, ny = float(face["normal"][0]), float(face["normal"][1])
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    ex, ey = _clear_of(core, (mx - tx * 8, my - ty * 8), (nx, ny), 14.0)
    street_eye = [round(ex, 2), round(ey, 2), 1.6]
    street_tgt = [round(mx + tx * 22, 2), round(my + ty * 22, 2), 4.2]
    street = {
        "location": street_eye,
        "target": street_tgt,
        "lens": 32,
        "fstop": 8.0,
        "sun": _sun_for(street_eye, street_tgt, 28),
    }
    centres = [_centre(spec) for spec in core]
    cx = sum(p[0] for p in centres) / len(centres)
    cy = sum(p[1] for p in centres) / len(centres)
    span = max(geom.dist((cx, cy), point) for point in centres) if centres else 80.0
    tall = max(float(spec.get("height") or 12) for spec in core) if core else 40.0
    back = max(110.0, span * 1.25)
    air_eye = [round(cx - back * 0.72, 2), round(cy - back * 0.58, 2), round(max(80.0, span * 0.55 + 28), 2)]
    air_tgt = [round(cx, 2), round(cy, 2), round(min(28.0, tall * 0.15), 2)]
    aerial = {
        "location": air_eye,
        "target": air_tgt,
        "lens": 35,
        "fstop": 0,
        "sun": _sun_for(air_eye, air_tgt, 32),
    }
    left, right = pair if pair else (None, None)
    if left is None:
        res = dict(street)
    else:
        ca, cb = _centre(left), _centre(right or left)
        mid = ((ca[0] + cb[0]) / 2.0, (ca[1] + cb[1]) / 2.0)
        dx, dy = cb[0] - ca[0], cb[1] - ca[1]
        span = math.hypot(dx, dy) or 1.0
        px, py = -dy / span, dx / span
        ex, ey = mid
        for sign in (1.0, -1.0):
            tx, ty = mid[0] + px * sign * 22.0, mid[1] + py * sign * 22.0
            if not _inside_any(residential, tx, ty):
                ex, ey = tx, ty
                break
        res_eye = [round(ex, 2), round(ey, 2), 1.7]
        res_tgt = [round(mid[0], 2), round(mid[1], 2), 4.0]
        print("RES CAM", res_eye, res_tgt, "tiers",
              left.get("lot_id"), right.get("lot_id") if right else None, flush=True)
        res = {
            "location": res_eye,
            "target": res_tgt,
            "lens": 24,
            "fstop": 8.0,
            "sun": _sun_for(res_eye, res_tgt, 34),
        }
    return {"downtown_street": street, "aerial": aerial, "residential_street": res}


def _render(cams, core_obs, core_street, res_obs, res_street):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 6
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 2
    scene.cycles.transparent_max_bounces = 8
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    realism.grade(scene)
    world = bpy.data.worlds.new("Sky_City")
    scene.world = world
    world.use_nodes = True
    record = bb.load_material_record()
    groups = {
        "aerial": core_obs + core_street,
        "downtown_street": core_obs + core_street,
        "residential_street": res_obs + res_street,
    }
    names = {
        "aerial": "sky_city_downtown_aerial.png",
        "downtown_street": "sky_city_downtown_street.png",
        "residential_street": "sky_city_residential_street.png",
    }
    everything = core_obs + core_street + res_obs + res_street
    wanted = [s for s in os.environ.get("SKYCITY_SHOTS", "").split(",") if s]
    order = wanted or ["aerial", "downtown_street", "residential_street"]
    for shot in order:
        show = set(groups[shot])
        for ob in everything:
            ob.hide_render = ob not in show
        bb._look(cams[shot])
        # The block haze is tuned for a 100 m lot. At city clip range it blacks out the sky.
        scene.camera.data.clip_end = 700.0
        realism.sky(world, cams[shot]["sun"], False, record, bb.ART)
        for node in world.node_tree.nodes:
            if node.bl_idname == "ShaderNodeVolumePrincipled":
                node.inputs["Density"].default_value = 0.00035
        if "M_GlassLit" in bpy.data.materials:
            bb.set_emission(bpy.data.materials["M_GlassLit"], 0.6)
        if "M_InteriorLit" in bpy.data.materials:
            bb.set_emission(bpy.data.materials["M_InteriorLit"], 1.2)
        scene.render.filepath = os.path.join(PREVIEWS, names[shot])
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print("RENDER", names[shot], round(time.time() - t0, 1), flush=True)


def _export_baked(path, objects):
    copies = []
    for ob in objects:
        copy = ob.copy()
        copy.data = ob.data.copy()
        bpy.context.scene.collection.objects.link(copy)
        copies.append(copy)
    pivot = bpy.data.objects.new("PivotBake", None)
    bpy.context.scene.collection.objects.link(pivot)
    pivot.rotation_euler = (0.0, 0.0, -math.pi / 2.0)
    for copy in copies:
        copy.parent = pivot
    bpy.context.view_layer.update()
    for copy in copies:
        world = copy.matrix_world.copy()
        copy.parent = None
        copy.matrix_world = world
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action="DESELECT")
    for copy in copies:
        copy.select_set(True)
    bpy.context.view_layer.objects.active = copies[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(copies) > 1:
        bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    bb._export(path, [joined])
    mesh = joined.data
    bpy.data.objects.remove(joined, do_unlink=True)
    if mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)
    bpy.data.objects.remove(pivot, do_unlink=True)
    return os.path.getsize(path)


def _pack(prefix, objects, labels, budget, ratio):
    """Group meshes into GLBs under FILE_CAP, stopping at the remaining budget."""
    files = []
    batch = []
    batch_labels = []
    batch_tris = 0
    spent = 0

    def flush():
        nonlocal batch, batch_labels, batch_tris, spent
        if not batch:
            return True
        path = os.path.join(OUT, "%s_%02d.glb" % (prefix, len(files)))
        size = _export_baked(path, batch)
        files.append({
            "file": os.path.basename(path),
            "bytes": size,
            "buildings": batch_labels,
        })
        spent += size
        print("EXPORT", os.path.basename(path), round(size / (1024 * 1024), 2), "MB", flush=True)
        batch = []
        batch_labels = []
        batch_tris = 0
        return spent < budget

    for ob, label in zip(objects, labels):
        tris = len(ob.data.polygons) if ob.data else 1
        estimate = tris * ratio
        if batch and (batch_tris * ratio + estimate > FILE_CAP):
            if not flush():
                return files, spent
        if spent >= budget:
            break
        if spent + estimate > budget and batch:
            if not flush():
                return files, spent
        if spent >= budget:
            break
        batch.append(ob)
        batch_labels.append(label)
        batch_tris += tris
    flush()
    return files, spent


def _export_all(core, core_obs, core_street, residential, res_obs, res_street):
    for name in os.listdir(OUT):
        if name.endswith(".glb"):
            os.remove(os.path.join(OUT, name))
    sample = core_obs[0] if core_obs else res_obs[0]
    probe = os.path.join(OUT, "_probe.glb")
    probe_size = _export_baked(probe, [sample])
    os.remove(probe)
    tris = max(1, len(sample.data.polygons))
    ratio = probe_size / float(tris)
    print("CITY bytes/tri", round(ratio, 2), flush=True)
    # Streets are small next to towers. Give buildings most of the budget.
    files, spent = _pack("CG_chicago_core", core_obs, [spec.get("id") for spec in core[:len(core_obs)]],
                         int(BUDGET * 0.72), ratio)
    more, more_spent = _pack("CG_austin_low", res_obs, [spec.get("id") for spec in residential[:len(res_obs)]],
                             int(BUDGET * 0.18), ratio)
    files.extend(more)
    spent += more_spent
    left = max(0, BUDGET - spent)
    street_files, street_spent = _pack("CG_chicago_core_street", core_street, ["street"] * len(core_street), left, ratio)
    files.extend(street_files)
    spent += street_spent
    left = max(0, BUDGET - spent)
    street_files, street_spent = _pack("CG_austin_low_street", res_street, ["street"] * len(res_street), left, ratio)
    files.extend(street_files)
    spent += street_spent
    return files, spent


if __name__ == "__main__":
    main()
