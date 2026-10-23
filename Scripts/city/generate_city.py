"""Regenerate Sky City from the mashup layout with this project's generator.

Reads the existing footprints and roads (Saved/Mashup/buildings_v3.json and
plan_v3.json). Does not run roadnet or rebuild the plan. Pedestrian paths are
left out of the driveable streetscape. Every lot gets a district mix and, where
the type has income tiers, a tier. Buildings keep the planned height. Streets
get sidewalks, curbs, grass where the section asks for it, and stage-1 dressing.

City Sample is not touched. The editor script Scripts/city/import_city_ue.py
spawns the compact file into its own level.

Run: python3 -I Scripts/city/generate_city.py
Writes (gitignored): Saved/CityGen/sky_city_spawn.json
Previews: /opt/cursor/artifacts/previews/sky_city_aerial.png and sky_city_street.png
Seed is 7, the same seed plan_buildings used. Two builds of one plan match.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import districts as district_types
import geom
import model as model_mod
import pngutil
import seeder
import skyline

SEED = 7
DRIVE = ("highway", "major", "mid", "minor")
# Representative street kit for the district box. Lots still roll the mix below.
BOX_TYPE = {
    "chicago_core": "tech",
    "chicago": "historic_old",
    "austin_dt": "brand_new",
    "austin_low": "houses",
}
# chicago_core uses the skyline downtown mix. The others stay off utilities.
LOCAL_MIX = {
    "chicago": {"historic_old": 40, "eclectic_mix": 25, "apartments_condos": 25, "tech": 10},
    "austin_dt": {"brand_new": 45, "tech": 35, "green_renewable": 20},
    "austin_low": {"houses": 75, "apartments_condos": 15, "eclectic_mix": 10},
}
PROP_KINDS = (
    "lamp", "tree", "bench", "bin", "hydrant", "signal", "stop", "yield",
    "street_name", "bus_stop", "parked",
)
DISTRICT_RGB = {
    "chicago_core": (176, 148, 116),
    "chicago": (132, 96, 78),
    "austin_dt": (150, 176, 188),
    "austin_low": (120, 140, 104),
}
SPAWN_NAME = "sky_city_spawn.json"
LEVEL = "/Game/Maps/SkyCityGenerated"
FOLDER = "/Game/City/Generated"


def build_city(plan, buildings, landmarks=None, seed=SEED):
    """One deterministic city. The caller's dicts are not modified."""
    city = seeder.seed_from_plan(plan, buildings, landmarks or [], seed=seed)
    _prepare(city)
    return model_mod.regenerate(city, "buildings")


def build_from_disk(root=None):
    root = Path(root) if root else skyline.project_root()
    plan = seeder.read_json(root / "Saved" / "Mashup" / "plan_v3.json")
    buildings = seeder.read_json(root / "Saved" / "Mashup" / "buildings_v3.json")
    return build_city(plan, buildings, plan.get("landmarks") or [], seed=SEED)


def spawn_document(city):
    """What the editor imports. Ribbons and blocks, not every paint polygon."""
    sections = (city.get("streetscape") or {}).get("sections") or {}
    districts = {item["id"]: item for item in city.get("districts") or []}
    lots = {lot["id"]: lot for lot in city.get("lots") or []}
    buildings = []
    for spec in city.get("buildings") or []:
        if spec.get("role") == "landmark":
            pos = spec.get("position") or [0, 0]
            buildings.append({
                "id": spec["id"], "kind": "landmark", "name": spec.get("name") or "",
                "x": round(float(pos[0]), 2), "y": round(float(pos[1]), 2),
                "h": round(float(spec.get("height") or 40), 2),
            })
            continue
        footprint = spec.get("footprint") or []
        if len(footprint) < 3:
            continue
        lot = lots.get(spec.get("lot_id")) or {}
        district = districts.get(spec.get("district_id")) or {}
        centre, width, depth, yaw = _rect_frame(footprint)
        wall = (spec.get("materials") or {}).get("wall") or "concrete"
        ue = _ue(centre[0], centre[1], float(spec.get("height") or 12) / 2.0)
        buildings.append({
            "id": spec["id"], "kind": "building",
            "x": round(centre[0], 2), "y": round(centre[1], 2),
            "w": round(width, 2), "d": round(depth, 2),
            "h": round(float(spec.get("height") or 12), 2),
            "yaw": round(yaw, 2),
            "ue": [round(v, 1) for v in ue],
            "ue_yaw": round(_ue_yaw(yaw), 2),
            "style": spec.get("style"),
            "wall": wall,
            "district": district.get("name"),
            "district_type": lot.get("district_type") or district.get("district_type"),
            "tier": lot.get("tier"),
        })
    roads = []
    for road in city.get("roads") or []:
        sec = sections.get(road["id"]) or {}
        roads.append({
            "id": road["id"], "cls": road.get("cls"),
            "core": bool(road.get("core")),
            "name": road.get("name") or "",
            "width": sec.get("width"),
            "parkway": bool(sec.get("parkway")),
            "pts": road.get("polyline") or [],
        })
    props = []
    for prop in (city.get("streetscape") or {}).get("props") or []:
        if prop.get("kind") not in PROP_KINDS:
            continue
        props.append({
            "id": prop.get("id"), "kind": prop.get("kind"),
            "x": prop.get("x"), "y": prop.get("y"), "yaw": prop.get("yaw") or 0,
            "label": prop.get("label") or "",
        })
    return {
        "seed": int(city.get("seed") or SEED),
        "hash": model_mod.manifest_hash(city),
        "level": LEVEL,
        "folder": FOLDER,
        "frame": "plan metres, x east, y north. UE centimetres: X = y*100, Y = x*100, Z up.",
        "note": "Spawn beside City Sample. Do not open SkyCityMashup and do not remove CitySamplePCG.",
        "buildings": buildings,
        "roads": roads,
        "props": props,
    }


def write_spawn(city, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    document = spawn_document(city)
    dest.write_text(json.dumps(document))
    return document


def render_aerial(city, path, ppm=0.4):
    bounds = city.get("bounds") or [0, 0, 1, 1]
    x0, y0, x1, y1 = (float(v) for v in bounds)
    width = max(1, int((x1 - x0) * ppm))
    height = max(1, int((y1 - y0) * ppm))
    buf = bytearray([186, 196, 186]) * (width * height)
    districts = {item["id"]: item for item in city.get("districts") or []}
    for road in city.get("roads") or []:
        _stroke(buf, width, height, road.get("polyline") or [], (70, 74, 78), x0, y1, ppm, 1.2)
    for spec in city.get("buildings") or []:
        footprint = spec.get("footprint")
        if not footprint or spec.get("role") == "landmark":
            continue
        name = (districts.get(spec.get("district_id")) or {}).get("name") or ""
        colour = DISTRICT_RGB.get(name, (140, 140, 140))
        tall = min(1.0, float(spec.get("height") or 12) / 160.0)
        shade = tuple(min(255, int(channel * (0.55 + 0.45 * tall))) for channel in colour)
        _fill(buf, width, height, footprint, shade, x0, y1, ppm)
    pngutil.write_rgb(str(path), width, height, buf)


def render_street(city, path, width=960, height=540):
    """Eye height, looking at a downtown facade from across the street."""
    spec = _hero_building(city)
    pts = [(float(p[0]), float(p[1])) for p in spec.get("footprint") or [(0, 0), (1, 0), (1, 1)]]
    a, b = pts[0], pts[1]
    edge = (b[0] - a[0], b[1] - a[1])
    span = geom.hypot(edge) or 1.0
    outward = (edge[1] / span, -edge[0] / span)
    mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    eye = (mid[0] + outward[0] * 22.0, mid[1] + outward[1] * 22.0, 1.7)
    forward = (-outward[0], -outward[1])
    right = (forward[1], -forward[0])
    buf = bytearray([168, 188, 204]) * (width * height)
    _horizon(buf, width, height)
    near = _nearby(city, eye, 160.0)
    faces = []
    for spec in near:
        faces.extend(_extrude(spec))
    faces.sort(key=lambda face: -_depth(face, eye, forward))
    for face in faces:
        _paint_face(buf, width, height, face, eye, forward, right)
    pngutil.write_rgb(str(path), width, height, buf)


def _prepare(city):
    city["roads"] = [road for road in city.get("roads") or [] if road.get("cls") in DRIVE]
    seen = {}
    for road in city["roads"]:
        count = seen.get(road["id"], 0)
        seen[road["id"]] = count + 1
        if count:
            road["id"] = "%s_%d" % (road["id"], count)
    sky = skyline.load()
    types = district_types.table(sky)
    downtown = district_types.resolve_mix(sky, "downtown")
    mixes = dict(LOCAL_MIX)
    mixes["chicago_core"] = downtown
    by_name = {district.get("name"): district for district in city.get("districts") or []}
    for name, district in by_name.items():
        kind = BOX_TYPE.get(name)
        if kind:
            district_types.apply_type(district, kind, types, source="generated")
    areas = sorted(city["districts"], key=lambda item: abs(geom.poly_area(item.get("polygon") or [])))
    for road in city["roads"]:
        pts = road.get("polyline") or []
        if len(pts) < 2:
            continue
        mid = pts[len(pts) // 2]
        for district in areas:
            if geom.point_in_poly((float(mid[0]), float(mid[1])), district.get("polygon") or []):
                road["district_id"] = district["id"]
                if district.get("name") in ("chicago_core", "austin_dt"):
                    road["core"] = True
                break
    seed = int(city.get("seed") or SEED)
    buckets = {}
    for lot in city.get("lots") or []:
        name = (by_name and _name_of(lot, city)) or ""
        buckets.setdefault(name, []).append(lot)
    for name, lots in buckets.items():
        weights = mixes.get(name)
        if not weights:
            continue
        district_types.assign_children(lots, weights, seed, name, types, near_m=12.0)
        district = by_name.get(name)
        if not district:
            continue
        for type_name in district_types.TIERED_TYPES:
            group = [lot for lot in lots if lot.get("district_type") == type_name]
            if group:
                district_types.assign_tiers(group, None, seed, district, types, type_name)


def _name_of(lot, city):
    for district in city.get("districts") or []:
        if district.get("id") == lot.get("district_id"):
            return district.get("name")
    return ""


def _rect_frame(footprint):
    pts = [(float(p[0]), float(p[1])) for p in footprint]
    centre = geom.centroid(pts)
    edge = geom.sub(pts[1], pts[0])
    width = geom.hypot(edge) or 1.0
    depth = geom.dist(pts[1], pts[2]) if len(pts) > 2 else width
    yaw = math.degrees(math.atan2(edge[1], edge[0]))
    return centre, width, depth, yaw


def _ue(x, y, z):
    """Plan metres to Unreal centimetres. X is north, Y is east."""
    return (y * 100.0, x * 100.0, z * 100.0)


def _ue_yaw(plan_yaw_deg):
    """Plan yaw 0 is east. Unreal yaw 0 is north (+X)."""
    return 90.0 - float(plan_yaw_deg)


def _hero_building(city):
    """A tall downtown mass, so the street view has a facade in front of the camera."""
    best = None
    best_h = -1.0
    for spec in city.get("buildings") or []:
        if spec.get("role") == "landmark" or not spec.get("footprint"):
            continue
        name = spec.get("district_id") or ""
        if name not in ("chicago_core", "chicago", "austin_dt"):
            continue
        height = float(spec.get("height") or 0)
        if height > best_h:
            best = spec
            best_h = height
    if best:
        return best
    for spec in city.get("buildings") or []:
        if spec.get("footprint") and spec.get("role") != "landmark":
            return spec
    return {"footprint": [[0, 0], [12, 0], [12, 10], [0, 10]], "height": 18, "materials": {"wall": "brick"}}


def _nearby(city, eye, radius):
    found = []
    for spec in city.get("buildings") or []:
        footprint = spec.get("footprint")
        if not footprint or spec.get("role") == "landmark":
            continue
        centre = geom.centroid([(float(p[0]), float(p[1])) for p in footprint])
        if geom.dist(centre, (eye[0], eye[1])) <= radius:
            found.append(spec)
    return found


def _extrude(spec):
    pts = [(float(p[0]), float(p[1])) for p in spec["footprint"]]
    height = max(3.0, float(spec.get("height") or 12))
    wall = (spec.get("materials") or {}).get("wall") or "concrete"
    colour = {
        "brick": (150, 84, 64),
        "plaster": (196, 186, 170),
        "glass": (120, 156, 170),
        "metal": (120, 124, 128),
        "concrete": (168, 164, 156),
    }.get(wall, (160, 154, 146))
    ground = tuple(max(0, c - 28) for c in colour)
    faces = []
    for a, b in zip(pts, pts[1:] + pts[:1]):
        faces.append((
            [(a[0], a[1], 0.0), (b[0], b[1], 0.0), (b[0], b[1], height), (a[0], a[1], height)],
            colour, ground, 4.0,
        ))
    return faces


def _depth(face, eye, forward):
    pts = face[0]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return (cx - eye[0]) * forward[0] + (cy - eye[1]) * forward[1]


def _paint_face(buf, width, height, face, eye, forward, right):
    pts, colour, ground, band = face
    projected = []
    for point in pts:
        rel = (point[0] - eye[0], point[1] - eye[1], point[2] - eye[2])
        depth = rel[0] * forward[0] + rel[1] * forward[1]
        if depth < 0.4:
            return
        across = rel[0] * right[0] + rel[1] * right[1]
        focal = (width * 0.5) / math.tan(math.radians(32))
        sx = width * 0.5 + focal * across / depth
        sy = height * 0.62 - focal * rel[2] / depth
        projected.append((sx, sy, point[2]))
    _fill_screen(buf, width, height, projected, colour, ground, band)


def _horizon(buf, width, height):
    for y in range(int(height * 0.62), height):
        shade = 150 - int(40 * (y - height * 0.62) / (height * 0.38))
        row = y * width
        for x in range(width):
            i = (row + x) * 3
            buf[i] = 90
            buf[i + 1] = shade
            buf[i + 2] = 78


def _fill_screen(buf, width, height, pts, colour, ground, band):
    ys = [p[1] for p in pts]
    y0 = max(0, int(min(ys)))
    y1 = min(height - 1, int(max(ys)) + 1)
    n = len(pts)
    for y in range(y0, y1 + 1):
        scan = y + 0.5
        hits = []
        for i in range(n):
            ax, ay, az = pts[i]
            bx, by, bz = pts[(i + 1) % n]
            if (ay > scan) == (by > scan):
                continue
            t = (scan - ay) / ((by - ay) or 1e-9)
            hits.append((ax + (bx - ax) * t, az + (bz - az) * t))
        hits.sort()
        row = y * width
        for i in range(0, len(hits) - 1, 2):
            x0 = max(0, int(hits[i][0]))
            x1 = min(width - 1, int(hits[i + 1][0]))
            z = (hits[i][1] + hits[i + 1][1]) * 0.5
            rgb = ground if z < band else colour
            for x in range(x0, x1 + 1):
                k = (row + x) * 3
                buf[k] = rgb[0]
                buf[k + 1] = rgb[1]
                buf[k + 2] = rgb[2]


def _fill(buf, width, height, poly, colour, origin_x, origin_y, ppm):
    pix = [((float(p[0]) - origin_x) * ppm, (origin_y - float(p[1])) * ppm) for p in poly]
    if len(pix) < 3:
        return
    ys = [p[1] for p in pix]
    y0 = max(0, int(min(ys)))
    y1 = min(height - 1, int(max(ys)) + 1)
    n = len(pix)
    for y in range(y0, y1 + 1):
        scan = y + 0.5
        xs = []
        for i in range(n):
            ax, ay = pix[i]
            bx, by = pix[(i + 1) % n]
            if (ay > scan) == (by > scan):
                continue
            t = (scan - ay) / ((by - ay) or 1e-9)
            xs.append(ax + (bx - ax) * t)
        xs.sort()
        row = y * width
        for i in range(0, len(xs) - 1, 2):
            x0 = max(0, int(xs[i]))
            x1 = min(width - 1, int(xs[i + 1]))
            for x in range(x0, x1 + 1):
                k = (row + x) * 3
                buf[k] = colour[0]
                buf[k + 1] = colour[1]
                buf[k + 2] = colour[2]


def _stroke(buf, width, height, polyline, colour, origin_x, origin_y, ppm, radius):
    pts = [(float(p[0]), float(p[1])) for p in polyline]
    for a, b in zip(pts, pts[1:]):
        length = geom.dist(a, b)
        steps = max(1, int(length / 6.0))
        for i in range(steps + 1):
            t = i / steps
            x = a[0] + (b[0] - a[0]) * t
            y = a[1] + (b[1] - a[1]) * t
            cx = (x - origin_x) * ppm
            cy = (origin_y - y) * ppm
            _disc(buf, width, height, cx, cy, radius, colour)


def _disc(buf, width, height, cx, cy, radius, colour):
    x0 = max(0, int(cx - radius))
    x1 = min(width - 1, int(cx + radius) + 1)
    y0 = max(0, int(cy - radius))
    y1 = min(height - 1, int(cy + radius) + 1)
    r2 = radius * radius
    for y in range(y0, y1 + 1):
        dy = y + 0.5 - cy
        row = y * width
        for x in range(x0, x1 + 1):
            dx = x + 0.5 - cx
            if dx * dx + dy * dy <= r2:
                k = (row + x) * 3
                buf[k] = colour[0]
                buf[k + 1] = colour[1]
                buf[k + 2] = colour[2]


def main():
    root = skyline.project_root()
    out = root / "Saved" / "CityGen"
    preview = Path("/opt/cursor/artifacts/previews")
    preview.mkdir(parents=True, exist_ok=True)
    city = build_from_disk(root)
    document = write_spawn(city, out / SPAWN_NAME)
    example = Path(__file__).resolve().parent / "examples" / SPAWN_NAME
    example.parent.mkdir(parents=True, exist_ok=True)
    example.write_text(json.dumps(document))
    render_aerial(city, preview / "sky_city_aerial.png")
    render_street(city, preview / "sky_city_street.png")
    kinds = {}
    for prop in document["props"]:
        kinds[prop["kind"]] = kinds.get(prop["kind"], 0) + 1
    print("seed", document["seed"])
    print("hash", document["hash"])
    print("buildings", sum(1 for item in document["buildings"] if item["kind"] == "building"))
    print("roads", len(document["roads"]))
    print("props", " ".join("%s=%d" % (key, kinds[key]) for key in sorted(kinds)))
    print("spawn", out / SPAWN_NAME)


if __name__ == "__main__":
    main()
