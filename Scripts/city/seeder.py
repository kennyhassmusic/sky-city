"""Turn a plan, a blank canvas, or a sketch into a city model.

OpenStreetMap is one seeder, not the generator. plan_v3.json and buildings_v3.json can
fill the districts, roads and a first guess at lots. A blank canvas and the one-block
study in skyline.yaml are the other seeders. seed_from_city_shape reads a City Shape
v1 document from building-types into the same city model. A later AI link calls the
same functions.

Those OSM files are Git LFS. A fresh clone often has the pointer text instead of the
JSON. read_json refuses that, with a message that says to pull LFS or to build from
skyline.yaml, which does not need them.
"""
import json
import math
import zlib
from pathlib import Path

import model as model_mod
import skyline


# District names written by Scripts/mashup/plan_buildings.py, and the character
# and grammar style they become. The old names (tower, glass, lowrise) were
# buckets for City Sample kits. These are our own.
DISTRICT_STYLE = {
    "chicago_core": ("downtown", "prewar_masonry"),
    "chicago": ("downtown", "prewar_masonry"),
    "austin_dt": ("waterfront", "glass_curtain"),
    "austin_low": ("residential", "texas_lowrise"),
}


def read_json(path):
    """Load a JSON file. Raise if it is still a Git LFS pointer."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    head = text[:180]
    if head.startswith("version https://git-lfs") or "git-lfs.github.com/spec" in head:
        raise RuntimeError(
            "%s is a Git LFS pointer, not city data. Run git lfs pull on that file, "
            "or build the block from Scripts/city/skyline.yaml, which does not need the OSM extracts."
            % path)
    return json.loads(text)


def seed_blank(bounds, seed):
    """An empty city: bounds and a seed, no districts yet. draw_road and add_district fill it."""
    return model_mod.new_model(bounds, seed)


def seed_from_city_shape(doc, seed=None):
    """A city model from a City Shape v1 document written by building-types.

    The roads are drive centrelines for network.py. Districts and water are
    copied only when the document already has them. The command line is
    Scripts/city/cityshape.py.
    """
    import cityshape
    return cityshape.to_city_model(doc, seed=seed)


def seed_from_files(root=None):
    """Read the tracked OSM-derived JSON. Fails clearly when the files are LFS pointers."""
    root = Path(root) if root else skyline.project_root()
    plan = read_json(root / "Saved" / "Mashup" / "plan_v3.json")
    buildings = read_json(root / "Saved" / "Mashup" / "buildings_v3.json")
    landmarks = plan.get("landmarks") or []
    return seed_from_plan(plan, buildings, landmarks, seed=plan.get("seed") or 7)


def seed_from_plan(plan, buildings, landmarks=None, seed=1):
    """A city model from a plan dict, a buildings dict, and landmark records.

    Roads keep their OSM ids and source 'osm'. Rectangle buildings become lots
    tagged with the surveyed height, so a later regenerate honours that height.
    Landmarks are source 'hand' and locked: regeneration copies them through.
    """
    bounds = [float(v) for v in (plan.get("bounds") or [0, 0, 1, 1])]
    city = model_mod.new_model(bounds, seed)
    by_name = {}
    for raw in plan.get("districts") or []:
        district = _district_from_plan(raw)
        city["districts"].append(district)
        by_name[raw.get("name") or raw.get("id")] = district["id"]
        by_name[district["id"]] = district["id"]

    rows = buildings.get("buildings") if isinstance(buildings, dict) else buildings
    rows = list(rows or [])
    if not city["districts"]:
        for district in _districts_from_buildings(rows, landmarks or [], bounds):
            city["districts"].append(district)
            by_name[district.get("name")] = district["id"]
            by_name[district["id"]] = district["id"]

    default_district = city["districts"][0]["id"] if city["districts"] else None
    for raw in plan.get("roads") or []:
        city["roads"].append(_road_from_plan(raw, default_district))

    for i, raw in enumerate(rows):
        district_id = by_name.get(raw.get("district")) or default_district
        _add_rectangle_building(city, raw, i, district_id)

    for raw in landmarks or []:
        city["buildings"].append(_landmark(raw, by_name, default_district))
    return city


def _district_from_plan(raw):
    name = raw.get("name") or raw.get("id") or "district"
    character, style = DISTRICT_STYLE.get(name, (raw.get("character") or "custom", raw.get("style")))
    if character not in ("downtown", "residential", "industrial", "park", "waterfront", "custom"):
        character = "custom"
    sky = skyline.load()
    preset = (sky.get("characters") or {}).get(character) or {}
    return {
        "id": raw.get("id") or _hid("d", name),
        "name": name,
        "source": "osm",
        "locked": False,
        "polygon": [[float(p[0]), float(p[1])] for p in raw["polygon"]],
        "character": character,
        "style": style or preset.get("style") or "prewar_masonry",
        "trees": list(raw.get("trees") or preset.get("trees") or ["linden", "elm"]),
        "skyline": dict(raw.get("skyline") or {}),
    }


def _districts_from_buildings(rows, landmarks, bounds):
    """One district per building-district name, padded around the points that use it."""
    groups = {}
    for raw in rows:
        groups.setdefault(raw.get("district") or "custom", []).append((float(raw["x"]), float(raw["y"])))
    for raw in landmarks:
        pos = raw.get("pos") or raw.get("position") or [0, 0]
        groups.setdefault(raw.get("district") or "custom", []).append((float(pos[0]), float(pos[1])))
    if not groups:
        groups["custom"] = [((bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0)]
    out = []
    for name, pts in groups.items():
        character, style = DISTRICT_STYLE.get(name, ("custom", "prewar_masonry"))
        sky = skyline.load()
        preset = (sky.get("characters") or {}).get(character) or {}
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        pad = 80.0
        poly = [[min(xs) - pad, min(ys) - pad], [max(xs) + pad, min(ys) - pad],
                [max(xs) + pad, max(ys) + pad], [min(xs) - pad, max(ys) + pad]]
        out.append({
            "id": _hid("d", name),
            "name": name,
            "source": "osm",
            "locked": False,
            "polygon": poly,
            "character": character,
            "style": style or preset.get("style") or "prewar_masonry",
            "trees": list(preset.get("trees") or ["linden", "elm"]),
            "skyline": {},
        })
    return out


def _road_from_plan(raw, district_id):
    pts = raw.get("polyline") or raw.get("pts") or []
    return {
        "id": raw.get("id") or _hid("road", pts),
        "source": "osm",
        "locked": False,
        "polyline": [[round(float(p[0]), 2), round(float(p[1]), 2)] for p in pts],
        "cls": raw.get("cls") or "minor",
        "lanes": int(raw.get("lanes") or 2),
        "oneway": bool(raw.get("oneway")),
        "core": bool(raw.get("core")),
        "name": raw.get("name") or "",
        "district_id": raw.get("district_id") or district_id,
    }


def _add_rectangle_building(city, raw, index, district_id):
    """A planned rectangle (centre, yaw, width along the street, depth) becomes a lot."""
    footprint = rectangle_footprint(raw["x"], raw["y"], raw.get("yaw") or 0, raw["w"], raw["d"])
    lot_id = "lot_osm_%d" % index
    yaw = math.radians(float(raw.get("yaw") or 0))
    # yaw is the street direction. The front faces across the street, to the right of yaw
    # in plan space (x east, y north), which is the side the packer left open.
    front = [round(math.sin(yaw), 4), round(-math.cos(yaw), 4)]
    city["lots"].append({
        "id": lot_id,
        "source": "osm",
        "locked": False,
        "block_id": None,
        "district_id": district_id,
        "polygon": footprint,
        "front_normals": [front],
        "role": "lot",
        "tags": {"height": raw.get("h")},
    })
    city["buildings"].append({
        "id": "b_" + lot_id,
        "lot_id": lot_id,
        "district_id": district_id,
        "source": "osm",
        "locked": False,
        "role": "building",
        "style": DISTRICT_STYLE.get(raw.get("district"), (None, raw.get("style")))[1],
        "seed": int(city["seed"]),
        "height": float(raw.get("h") or 12),
        "footprint": footprint,
        "tags": {"height": raw.get("h")},
    })


def rectangle_footprint(x, y, yaw_deg, width, depth):
    """Rectangle centred on (x, y). `width` runs along yaw, `depth` across it. CCW."""
    a = math.radians(float(yaw_deg))
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -math.sin(a), math.cos(a)
    pts = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        pts.append([
            round(float(x) + sx * float(width) / 2.0 * ux + sy * float(depth) / 2.0 * vx, 2),
            round(float(y) + sx * float(width) / 2.0 * uy + sy * float(depth) / 2.0 * vy, 2),
        ])
    return pts


def _landmark(raw, by_name, default_district):
    pos = raw.get("position") or raw.get("pos") or [0, 0]
    name = raw.get("name") or "landmark"
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_") or "landmark"
    return {
        "id": raw.get("id") or ("lm_%s" % slug),
        "name": name,
        "source": "hand",
        "locked": True,
        "role": "landmark",
        "position": [float(pos[0]), float(pos[1])],
        "height": float(raw.get("h") or raw.get("height") or 40),
        "district_id": by_name.get(raw.get("district")) or default_district,
        "style": "landmark",
        "seed": 0,
    }


def _hid(prefix, *parts):
    return "%s_%08x" % (prefix, zlib.crc32(repr(parts).encode()) & 0xffffffff)
