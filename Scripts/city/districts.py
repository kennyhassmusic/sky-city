"""District types, mix ratios, and texture-pack lookup.

A type is a recipe: grammar styles, a height range, roofs, material slots, plants,
wear, and street furniture. skyline.yaml holds one mix for the whole city and
further mixes for named regions. assign paints unlocked districts from a mix with
a seeded weight, and it will not put utilities or industrial next to houses when
another type in the mix can take that spot.

A type, or a district, may carry a nested mix. The blocks inside that district
are painted from the nested mix, so one district can hold a sub-mix. Lots inside
a block use the block's type, or the block's own nested mix when it has one.

Texture packs are not in the repo yet. load_pack reads
Scripts/city/packs/<district>/manifest.json and, when that file is missing or
unreadable, returns the type's CC0 material slots instead.
"""
import json
from pathlib import Path

import geom
import skyline


TYPE_NAMES = (
    "brand_new",
    "historic_old",
    "eclectic_mix",
    "tech",
    "green_renewable",
    "houses",
    "apartments_condos",
    "industrial_commercial",
    "utilities",
)

# Pairs that should not share a boundary. Checked in both directions.
AVOID = (
    ("houses", "utilities"),
    ("houses", "industrial_commercial"),
    ("apartments_condos", "utilities"),
)

# Metres. A local street between two district polygons still counts as adjacent.
NEAR_M = 20.0

REQUIRED = (
    "buildings", "height_m", "roofs", "materials", "pack",
    "vegetation", "wear", "furniture",
)

# Grammar slot -> CC0 texture id already shipped with the city generator.
CC0_TEXTURES = {
    "brick": "brick_wall_001",
    "concrete": "concrete_wall_001",
    "plaster": "grey_plaster",
    "metal": "metal_plate",
    "glass": "glass",
    "asphalt": "asphalt_02",
    "paving": "PavingStones092",
    "grass": "Grass004",
}


def table(sky):
    """The nine types from a loaded skyline. Raises if one is missing or incomplete."""
    raw = sky.get("district_types") or {}
    missing = [name for name in TYPE_NAMES if name not in raw]
    if missing:
        raise ValueError("skyline.yaml is missing district types: %s" % ", ".join(missing))
    for name in TYPE_NAMES:
        spec = raw[name] or {}
        for key in REQUIRED:
            if key not in spec:
                raise ValueError("district type %s needs %s" % (name, key))
        height = spec.get("height_m") or []
        if len(height) != 2:
            raise ValueError("district type %s needs a height range" % name)
        wear = float(spec.get("wear") or 0)
        if wear < 0 or wear > 1:
            raise ValueError("district type %s wear must be from 0 to 1" % name)
        for child in (spec.get("mix") or {}):
            if child not in TYPE_NAMES:
                raise ValueError("district type %s mix names unknown type %s" % (name, child))
    return raw


def resolve_mix(sky, region=None):
    """City mix, or one region. An unknown region is an error so a typo is not silent."""
    mix = sky.get("mix") or {}
    if region is None:
        found = mix.get("city") or {}
        if not found:
            raise ValueError("skyline.yaml has no city mix")
        return dict(found)
    regions = mix.get("regions") or {}
    if region not in regions:
        raise ValueError("no mix for region %s" % region)
    return dict(regions[region])


def conflicts(type_name):
    """Types that should not sit next to this one."""
    banned = set()
    for left, right in AVOID:
        if type_name == left:
            banned.add(right)
        elif type_name == right:
            banned.add(left)
    return banned


def choose(weights, seed, *parts, banned=()):
    """Seeded weighted pick. Names are sorted so the order of the yaml does not matter.

    When every positive weight is banned, the lightest banned weight is used so a
    district still receives a type. Callers that include a neutral type (tech,
    brand_new) never hit that fallback.
    """
    banned = set(banned or ())
    clean = []
    for name, weight in (weights or {}).items():
        if name not in TYPE_NAMES:
            raise ValueError("unknown district type %s" % name)
        amount = float(weight)
        if amount > 0:
            clean.append((name, amount))
    if not clean:
        raise ValueError("mix has no positive weights")
    clean.sort(key=lambda item: item[0])
    allowed = [item for item in clean if item[0] not in banned]
    if not allowed:
        # Every remaining type conflicts. Take the smallest share so a rare
        # utilities pocket is preferred over a large industrial one.
        return sorted(clean, key=lambda item: (item[1], item[0]))[0][0]
    total = sum(amount for _, amount in allowed)
    cursor = geom.rnd(seed, *parts) * total
    acc = 0.0
    for name, amount in allowed:
        acc += amount
        if cursor < acc:
            return name
    return allowed[-1][0]


def near(polygon_a, polygon_b, gap=NEAR_M):
    """True when two rings touch, overlap, or sit within `gap` metres."""
    if not polygon_a or not polygon_b:
        return False
    (ax0, ay0), (ax1, ay1) = geom.bbox(polygon_a)
    (bx0, by0), (bx1, by1) = geom.bbox(polygon_b)
    if ax1 < bx0 - gap or bx1 < ax0 - gap or ay1 < by0 - gap or by1 < ay0 - gap:
        return False
    if geom.point_in_poly(geom.centroid(polygon_a), polygon_b):
        return True
    if geom.point_in_poly(geom.centroid(polygon_b), polygon_a):
        return True
    return _ring_gap(polygon_a, polygon_b) <= gap


def apply_type(district, type_name, types, source="generated", keep_style_pin=True):
    """Copy a type's recipe onto a district. The district skyline is left alone.

    Height, roofs and the building list are stored on the district so the Map
    Designer can read them without opening skyline.yaml. A skyline override the
    caller already set still wins inside for_district. A hand mix is kept; the
    type's own mix fills in only when the district does not already have one.
    """
    if type_name not in TYPE_NAMES or type_name not in (types or {}):
        raise ValueError("unknown district type %s" % type_name)
    spec = types[type_name]
    district["district_type"] = type_name
    district["type_source"] = source
    district["buildings"] = list(spec.get("buildings") or [])
    height = spec.get("height_m") or [0, 0]
    district["height_m"] = [float(height[0]), float(height[1])]
    district["roofs"] = list(spec.get("roofs") or [])
    district["materials"] = list(spec.get("materials") or [])
    district["pack"] = spec.get("pack") or type_name
    plants = list(spec.get("vegetation") or [])
    district["vegetation"] = plants
    district["trees"] = list(plants)
    district["wear"] = float(spec.get("wear") or 0)
    district["furniture"] = list(spec.get("furniture") or [])
    if spec.get("mix") and district.get("mix_source") != "hand":
        district["mix"] = dict(spec["mix"])
        district["mix_source"] = "type"
    elif not spec.get("mix") and district.get("mix_source") != "hand":
        district.pop("mix", None)
        district.pop("mix_source", None)
    if not keep_style_pin:
        district["style_pinned"] = False
    return district


def assign(districts, weights, seed, types, near_m=NEAR_M):
    """Paint districts in id order. Locked districts and hand-set types stay put."""
    ordered = sorted(districts or [], key=lambda item: item.get("id") or "")
    placed = [item for item in ordered if _held(item) and item.get("district_type")]
    touched = []
    for district in ordered:
        if _held(district):
            continue
        banned = _banned_by(district, placed, near_m)
        pick = choose(weights, seed, district.get("id") or "", "district", banned=banned)
        apply_type(district, pick, types, source="generated", keep_style_pin=True)
        placed.append(district)
        touched.append(district["id"])
    return touched


def assign_children(items, weights, seed, parent_id, types, outside=None, near_m=NEAR_M):
    """Paint blocks or lots from a nested mix. `outside` is (polygon, type) pairs."""
    outside = list(outside or [])
    ordered = sorted(items or [], key=lambda item: item.get("id") or "")
    placed = [(item.get("polygon"), item.get("district_type"))
              for item in ordered if _held(item) and item.get("district_type")]
    touched = []
    for item in ordered:
        if _held(item):
            continue
        banned = set()
        for polygon, kind in list(placed) + outside:
            if kind and near(item.get("polygon"), polygon, near_m):
                banned |= conflicts(kind)
        pick = choose(weights, seed, parent_id or "", item.get("id") or "", "submix", banned=banned)
        item["district_type"] = pick
        item["type_source"] = "generated"
        spec = (types or {}).get(pick) or {}
        if spec.get("mix") and item.get("mix_source") != "hand":
            item["mix"] = dict(spec["mix"])
            item["mix_source"] = "type"
        elif not spec.get("mix") and item.get("mix_source") != "hand":
            item.pop("mix", None)
            item.pop("mix_source", None)
        placed.append((item.get("polygon"), pick))
        touched.append(item.get("id"))
    return touched


def stamp_children(model, district, types, seed, include_lots=True):
    """Apply a district's mix to its blocks, then to the lots in those blocks.

    A district with no mix still copies its own type onto children, so a tech
    district and a nested tech block read the same recipe. Hand-set and locked
    children are left as they are.
    """
    if not district:
        return []
    seed = int(seed or 1)
    blocks = [block for block in model.get("blocks") or []
              if block.get("district_id") == district.get("id")]
    lots = [lot for lot in model.get("lots") or []
            if lot.get("district_id") == district.get("id")] if include_lots else []
    touched = []
    mix = district.get("mix")
    outside = outside_context(model, district)
    if mix and blocks:
        touched.extend(assign_children(blocks, mix, seed, district.get("id"), types, outside=outside))
    elif district.get("district_type"):
        touched.extend(_copy_type(blocks, district["district_type"]))
    if not include_lots:
        return touched
    if mix and not blocks and lots:
        touched.extend(assign_children(lots, mix, seed, district.get("id"), types, outside=outside))
        return touched
    for block in blocks:
        block_lots = [lot for lot in lots if lot.get("block_id") == block.get("id")]
        if not block_lots:
            continue
        if block.get("mix"):
            touched.extend(assign_children(
                block_lots, block["mix"], seed, block.get("id"), types, outside=outside))
        elif block.get("district_type"):
            touched.extend(_copy_type(block_lots, block["district_type"]))
    return touched


def outside_context(model, district):
    """Neighboring leaf types. A neighbor's blocks count when it has already been split."""
    if not district:
        return []
    found = []
    for other in model.get("districts") or []:
        if other.get("id") == district.get("id"):
            continue
        children = [block for block in model.get("blocks") or []
                    if block.get("district_id") == other.get("id")
                    and block.get("district_type") and block.get("polygon")]
        if children:
            for child in children:
                found.append((child["polygon"], child["district_type"]))
        elif other.get("district_type") and other.get("polygon"):
            found.append((other["polygon"], other["district_type"]))
    return found


def load_pack(type_name, root=None, sky=None):
    """Read packs/<district>/manifest.json, or the CC0 slots when it is missing.

    `root` is a directory that contains `packs/`. The default is Scripts/city,
    next to this file. A missing file, an empty file, or invalid JSON all use
    the CC0 fallback. An unknown type is an error.
    """
    if type_name not in TYPE_NAMES:
        raise ValueError("unknown district type %s" % type_name)
    sky = sky or skyline.load()
    types = table(sky)
    slots = list((types.get(type_name) or {}).get("materials") or [])
    path = _manifest_path(type_name, root)
    if path.is_file():
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict):
            return {
                "source": "pack",
                "district": type_name,
                "materials": list(data.get("materials") or slots),
                "textures": dict(data.get("textures") or {}),
                "path": str(path),
            }
    return {
        "source": "cc0",
        "district": type_name,
        "materials": slots,
        "textures": {slot: CC0_TEXTURES.get(slot, slot) for slot in slots},
        "path": None,
    }


def _manifest_path(type_name, root):
    base = Path(root) if root else Path(__file__).resolve().parent
    return base / "packs" / type_name / "manifest.json"


def _held(item):
    return bool(item.get("locked")) or item.get("type_source") == "hand"


def _banned_by(district, others, near_m):
    banned = set()
    for other in others:
        if other is district:
            continue
        if near(district.get("polygon"), other.get("polygon"), near_m):
            banned |= conflicts(other.get("district_type"))
    return banned


def _copy_type(items, type_name):
    touched = []
    for item in items:
        if _held(item):
            continue
        item["district_type"] = type_name
        item["type_source"] = "generated"
        if item.get("id"):
            touched.append(item["id"])
    return touched


def _ring_gap(polygon_a, polygon_b):
    best = 1e9
    for ring, other in ((polygon_a, polygon_b), (polygon_b, polygon_a)):
        count = len(other)
        for point in ring:
            point = (float(point[0]), float(point[1]))
            for index in range(count):
                start = other[index]
                end = other[(index + 1) % count]
                best = min(best, _point_seg(point, start, end))
    return best


def _point_seg(point, start, end):
    start = (float(start[0]), float(start[1]))
    end = (float(end[0]), float(end[1]))
    span = geom.sub(end, start)
    length2 = geom.dot(span, span) or 1e-12
    t = max(0.0, min(1.0, geom.dot(geom.sub(point, start), span) / length2))
    return geom.dist(point, geom.lerp(start, end, t))
