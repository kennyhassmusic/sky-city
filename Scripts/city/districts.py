"""District types, mix ratios, income tiers, and texture-pack lookup.

A type is a recipe: grammar styles, a height range, roofs, material slots, plants,
wear, and street furniture. skyline.yaml holds one mix for the whole city and
further mixes for named regions. assign paints unlocked districts from a mix with
a seeded weight, and it will not put utilities or industrial next to houses when
another type in the mix can take that spot.

A type, or a district, may carry a nested mix. The blocks inside that district
are painted from the nested mix, so one district can hold a sub-mix. Lots inside
a block use the block's type, or the block's own nested mix when it has one.

Houses and apartments carry four income tiers (high, mid, low, distressed). A
tier_mix such as {high: 20, mid: 50, low: 25, distressed: 5} is a share, not a
district-type mix. assign_tiers lays those shares out along a seeded axis so a
neighbourhood changes one step at a time. The same seed rebuilds the same bands.

Texture packs are not in the repo yet. load_pack reads
Scripts/city/packs/<district>/<tier>/manifest.json when a tier is named, then
packs/<district>/manifest.json, and, when those files are missing or unreadable,
returns the CC0 material slots instead.
"""
import json
import math
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

# Houses and apartments are painted in income bands. Order is rich to poor,
# one step at a time, so a gradient never jumps from high to distressed.
TIER_NAMES = ("high", "mid", "low", "distressed")
TIERED_TYPES = ("houses", "apartments_condos")
TIER_KEYS = (
    "lot_width_m", "lot_depth_m", "front_setback_m", "side_setback_m",
    "coverage", "height_m", "materials", "wear", "upkeep", "landscaping",
    "tree_density", "fence", "gate", "parked_per_100m", "furniture",
    "lighting", "sidewalk",
)
DISTRESS_KEYS = ("boarded", "vacant_share", "informal", "encampment")

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
        if name in TIERED_TYPES:
            _check_tiers(name, spec)
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
    if type_name in TIERED_TYPES and spec.get("tier_mix") and district.get("tier_mix_source") != "hand":
        district["tier_mix"] = {name: float(spec["tier_mix"][name]) for name in TIER_NAMES}
        district["tier_mix_source"] = "type"
    elif type_name not in TIERED_TYPES and district.get("tier_mix_source") != "hand":
        district.pop("tier_mix", None)
        district.pop("tier_mix_source", None)
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
    else:
        for block in blocks:
            block_lots = [lot for lot in lots if lot.get("block_id") == block.get("id")]
            if not block_lots:
                continue
            if block.get("mix"):
                touched.extend(assign_children(
                    block_lots, block["mix"], seed, block.get("id"), types, outside=outside))
            elif block.get("district_type"):
                touched.extend(_copy_type(block_lots, block["district_type"]))
    if district.get("district_type") in TIERED_TYPES or any(
            (lot.get("district_type") in TIERED_TYPES) or lot.get("tier") for lot in lots):
        touched.extend(finish_tiers(lots, district, types, seed))
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


def load_pack(type_name, root=None, sky=None, tier=None):
    """Read a texture pack, or the CC0 slots when the pack is missing.

    `root` is a directory that contains `packs/`. The default is Scripts/city,
    next to this file. With a tier, the lookup is packs/<district>/<tier>/manifest.json,
    then packs/<district>/manifest.json, then CC0. A missing file, an empty file,
    or invalid JSON falls through to the next step. An unknown type or tier is
    an error. CC0 materials follow the tier recipe when a tier is named.
    """
    if type_name not in TYPE_NAMES:
        raise ValueError("unknown district type %s" % type_name)
    if tier is not None and tier not in TIER_NAMES:
        raise ValueError("unknown income tier %s" % tier)
    if tier is not None and type_name not in TIERED_TYPES:
        raise ValueError("%s has no income tiers" % type_name)
    sky = sky or skyline.load()
    types = table(sky)
    spec = types.get(type_name) or {}
    if tier:
        slots = list((_recipe(types, type_name, tier).get("materials")) or spec.get("materials") or [])
    else:
        slots = list(spec.get("materials") or [])
    for path in _manifest_candidates(type_name, root, tier):
        data = _read_manifest(path)
        if data is None:
            continue
        return {
            "source": "pack",
            "district": type_name,
            "tier": tier,
            "materials": list(data.get("materials") or slots),
            "textures": dict(data.get("textures") or {}),
            "path": str(path),
        }
    return {
        "source": "cc0",
        "district": type_name,
        "tier": tier,
        "materials": slots,
        "textures": {slot: CC0_TEXTURES.get(slot, slot) for slot in slots},
        "path": None,
    }


def _manifest_path(type_name, root, tier=None):
    base = Path(root) if root else Path(__file__).resolve().parent
    folder = base / "packs" / type_name
    if tier:
        folder = folder / tier
    return folder / "manifest.json"


def _manifest_candidates(type_name, root, tier):
    paths = []
    if tier:
        paths.append(_manifest_path(type_name, root, tier))
    paths.append(_manifest_path(type_name, root, None))
    return paths


def _read_manifest(path):
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if isinstance(data, dict):
        return data
    return None


def _check_tiers(name, spec):
    mix = spec.get("tier_mix") or {}
    if set(mix) != set(TIER_NAMES):
        raise ValueError("district type %s tier_mix needs high, mid, low and distressed" % name)
    for tier, weight in mix.items():
        if float(weight) <= 0:
            raise ValueError("district type %s tier %s needs a positive share" % (name, tier))
    tiers = spec.get("income_tiers") or {}
    for tier in TIER_NAMES:
        recipe = tiers.get(tier) or {}
        for key in TIER_KEYS:
            if key not in recipe:
                raise ValueError("district type %s tier %s needs %s" % (name, tier, key))
        wear = float(recipe.get("wear") or 0)
        if wear < 0 or wear > 1:
            raise ValueError("district type %s tier %s wear must be from 0 to 1" % (name, tier))
        if recipe.get("fence") in (None, ""):
            raise ValueError("district type %s tier %s needs a fence" % (name, tier))
    distress = tiers.get("distressed") or {}
    for key in DISTRESS_KEYS:
        if key not in distress:
            raise ValueError("district type %s distressed tier needs %s" % (name, key))


def _recipe(types, type_name, tier):
    spec = (types or {}).get(type_name) or {}
    recipe = ((spec.get("income_tiers") or {}).get(tier) or {})
    if not recipe:
        raise ValueError("district type %s has no %s tier" % (type_name, tier))
    return recipe


def _tier_weights(district, types, kind):
    """A hand or type mix on this district, otherwise the recipe in skyline.yaml."""
    if district and district.get("district_type") == kind and district.get("tier_mix"):
        return {name: float(district["tier_mix"].get(name) or 0) for name in TIER_NAMES}
    spec = (types or {}).get(kind) or {}
    mix = spec.get("tier_mix") or {}
    return {name: float(mix.get(name) or 0) for name in TIER_NAMES}


def _axis(district, seed):
    raw = (district or {}).get("tier_axis")
    if raw and len(raw) >= 2:
        vector = (float(raw[0]), float(raw[1]))
        if geom.hypot(vector) > 1e-8:
            return geom.unit(vector)
    angle = geom.rnd(seed, (district or {}).get("id") or "", "tier_axis") * 2.0 * math.pi
    return (math.cos(angle), math.sin(angle))


def _gradient(district, items, seed):
    """Unit axis plus the low and high projection of the district, else the items."""
    axis = _axis(district, seed)
    points = []
    ring = (district or {}).get("polygon") or []
    if len(ring) >= 3:
        points = [(float(point[0]), float(point[1])) for point in ring]
    else:
        for item in items or []:
            polygon = item.get("polygon") or []
            if len(polygon) >= 3:
                points.append(geom.centroid(polygon))
    if not points:
        return axis, 0.0, 1.0
    projections = [geom.dot(point, axis) for point in points]
    low, high = min(projections), max(projections)
    if high - low < 1e-6:
        high = low + 1.0
    return axis, low, high


def _project_t(point, axis, low, high):
    return max(0.0, min(1.0, (geom.dot(point, axis) - low) / (high - low or 1.0)))


def _tier_from_t(t, weights):
    """t = 0 is the rich end. Shares run high, mid, low, distressed."""
    total = sum(float(weights.get(name) or 0) for name in TIER_NAMES) or 1.0
    cursor = max(0.0, min(0.999999, float(t)))
    acc = 0.0
    for name in TIER_NAMES:
        acc += float(weights.get(name) or 0) / total
        if cursor < acc:
            return name
    return TIER_NAMES[-1]


def _tier_counts(weights, count):
    """Largest remainder. The counts sum to `count` and follow TIER_NAMES."""
    count = int(count)
    shares = {name: 0 for name in TIER_NAMES}
    if count <= 0:
        return shares
    total = sum(float(weights.get(name) or 0) for name in TIER_NAMES)
    if total <= 0:
        raise ValueError("tier mix has no positive weights")
    raw = []
    for index, name in enumerate(TIER_NAMES):
        exact = count * float(weights.get(name) or 0) / total
        whole = int(math.floor(exact))
        raw.append([name, whole, exact - whole, index])
    used = sum(item[1] for item in raw)
    raw.sort(key=lambda item: (-item[2], item[3]))
    for item in raw:
        if used >= count:
            break
        item[1] += 1
        used += 1
    for item in raw:
        shares[item[0]] = item[1]
    return shares


def _item_point(item):
    polygon = item.get("polygon") or []
    if len(polygon) >= 3:
        return geom.centroid(polygon)
    return (0.0, 0.0)


def assign_tiers(items, weights, seed, district, types, type_name):
    """Lay income tiers along the district axis. Hand and locked tiers stay put.

    Open items are ordered by projection plus a small seeded nudge, then sliced
    so the counts match the mix. Low score is the rich end. A later call with
    the same seed rebuilds the same bands.
    """
    seed = int(seed or 1)
    if type_name not in TIERED_TYPES:
        return []
    weights = _tier_weights({"district_type": type_name, "tier_mix": weights}, types, type_name)
    open_items = [item for item in (items or []) if not _tier_held(item)]
    if not open_items:
        return []
    axis, low, high = _gradient(district, open_items, seed)
    span = high - low
    scored = []
    for item in open_items:
        centre = _item_point(item)
        projection = geom.dot(centre, axis)
        nudge = (geom.rnd(seed, item.get("id") or "", "tier_noise") - 0.5) * 2.0 * span * 0.03
        score = projection + nudge
        scored.append((score, item.get("id") or "", item))
    scored.sort(key=lambda row: (row[0], row[1]))
    counts = _tier_counts(weights, len(scored))
    touched = []
    cursor = 0
    for name in TIER_NAMES:
        band = scored[cursor:cursor + counts[name]]
        cursor += counts[name]
        for score, _ident, item in band:
            item["tier_score"] = round(float(score), 4)
            item["tier_source"] = "generated"
            _apply_tier_fields(item, types, type_name, name)
            touched.append(item.get("id"))
    distressed = [item for _score, _ident, item in scored if item.get("tier") == "distressed"]
    _mark_distress(distressed, types, type_name)
    return touched


def finish_tiers(items, district, types, seed):
    """Fill tier fields on lots a frontage plan already labelled, and tier the rest.

    Planned lots keep their tier, so a second pass does not reshuffle a street
    whose lot widths already follow the gradient. Hand tiers are left alone.
    """
    if not items:
        return []
    parent_kind = (district or {}).get("district_type")
    groups = {}
    for item in items:
        kind = item.get("district_type") or parent_kind
        if kind not in TIERED_TYPES:
            continue
        groups.setdefault(kind, []).append(item)
    touched = []
    for kind, group in groups.items():
        holder = district if (district or {}).get("district_type") == kind else {
            "id": (district or {}).get("id"),
            "polygon": (district or {}).get("polygon"),
            "tier_axis": (district or {}).get("tier_axis"),
            "district_type": kind,
        }
        weights = _tier_weights(holder, types, kind)
        pending = [item for item in group if not item.get("tier") and not _tier_held(item)]
        if pending:
            touched.extend(assign_tiers(pending, weights, seed, holder, types, kind))
        for item in group:
            if item.get("tier") and item.get("front_setback_m") is None and not _tier_held(item):
                _apply_tier_fields(item, types, kind, item["tier"])
                if not item.get("tier_source"):
                    item["tier_source"] = "generated"
                if item.get("id"):
                    touched.append(item["id"])
        distressed = [item for item in group
                      if item.get("tier") == "distressed" and not _tier_held(item)]
        _mark_distress(distressed, types, kind)
    return touched


def plan_block(polygon, district, seed, types=None):
    """Frontage widths for one rectangular block, or None when the block is not tiered.

    The walk follows the long side. Each piece takes the mean lot width of the
    tier under its centre, with no extra jitter, so a street aligned with the
    income axis changes width in contiguous bands. Both lot rows share the cuts.
    """
    if not district or district.get("district_type") not in TIERED_TYPES:
        return None
    frame = geom.rectangle_frame(polygon)
    if frame is None:
        return None
    if types is None:
        types = table(skyline.load())
    kind = district["district_type"]
    weights = _tier_weights(district, types, kind)
    axis, low, high = _gradient(district, [], int(seed or 1))
    width = float(frame["width"])
    depth = float(frame["depth"])
    pieces = []
    cursor = 0.0
    guard = 0
    while cursor < width - 0.5 and guard < 500:
        guard += 1
        probe = min(width - 0.01, cursor + 0.5)
        world = geom.to_world(probe, depth / 2.0, frame)
        tier = _tier_from_t(_project_t(world, axis, low, high), weights)
        recipe = _recipe(types, kind, tier)
        lot_width = recipe.get("lot_width_m") or [12.0, 12.0]
        piece = max(4.0, (float(lot_width[0]) + float(lot_width[1])) / 2.0)
        if width - (cursor + piece) < 4.0:
            piece = width - cursor
        elif cursor + piece > width:
            piece = width - cursor
        centre = geom.to_world(min(width - 0.01, cursor + piece * 0.5), depth / 2.0, frame)
        pieces.append({
            "width": piece,
            "tier": tier,
            "tier_score": round(geom.dot(centre, axis), 4),
        })
        cursor += piece
    if not pieces:
        return None
    total = sum(piece["width"] for piece in pieces)
    if abs(total - width) > 1e-6 and total > 0:
        scale = width / total
        for piece in pieces:
            piece["width"] *= scale
        pieces[-1]["width"] += width - sum(piece["width"] for piece in pieces)
    return pieces


def _apply_tier_fields(item, types, type_name, tier):
    recipe = _recipe(types, type_name, tier)
    item["tier"] = tier
    width = recipe.get("lot_width_m") or [0, 0]
    depth = recipe.get("lot_depth_m") or [0, 0]
    height = recipe.get("height_m") or [0, 0]
    item["lot_width_m"] = [float(width[0]), float(width[1])]
    item["lot_depth_m"] = [float(depth[0]), float(depth[1])]
    item["height_m"] = [float(height[0]), float(height[1])]
    item["target_frontage_m"] = (float(width[0]) + float(width[1])) / 2.0
    item["front_setback_m"] = float(recipe.get("front_setback_m") or 0)
    item["side_setback_m"] = float(recipe.get("side_setback_m") or 0)
    item["coverage"] = float(recipe.get("coverage") or 0)
    item["wear"] = float(recipe.get("wear") or 0)
    item["upkeep"] = float(recipe.get("upkeep") or 0)
    item["landscaping"] = recipe.get("landscaping")
    item["tree_density"] = float(recipe.get("tree_density") or 0)
    item["fence"] = recipe.get("fence") or "open"
    item["gate"] = bool(recipe.get("gate"))
    item["parked_per_100m"] = float(recipe.get("parked_per_100m") or 0)
    item["lighting"] = recipe.get("lighting")
    item["sidewalk"] = recipe.get("sidewalk")
    item["materials"] = list(recipe.get("materials") or [])
    item["furniture"] = list(recipe.get("furniture") or [])
    if tier != "distressed":
        _clear_distress(item)
    return item


def _clear_distress(item):
    item["vacant"] = False
    item["boarded"] = False
    item["informal"] = False
    item["encampment"] = False
    item.pop("encampment_zone", None)


def _mark_distress(items, types, type_name):
    """Boarded houses, vacant lots, a shack, and an encampment zone. No people.

    The poorest lots (highest tier score) are vacated first. A vacant lot can
    hold an informal shack; an occupied distressed lot keeps its boarded house.
    """
    chosen = [item for item in (items or []) if item.get("tier") == "distressed"]
    if not chosen:
        return
    recipe = _recipe(types, type_name, "distressed")
    chosen.sort(key=lambda item: (-float(item.get("tier_score") or 0), item.get("id") or ""))
    count = len(chosen)
    vacant_count = int(round(count * float(recipe.get("vacant_share") or 0)))
    camp_count = int(round(count * 0.5)) if recipe.get("encampment") else 0
    if recipe.get("encampment") and camp_count < 1:
        camp_count = 1
    for index, item in enumerate(chosen):
        vacant = index < vacant_count
        item["vacant"] = vacant
        item["informal"] = bool(vacant and recipe.get("informal"))
        item["boarded"] = bool(recipe.get("boarded") and not vacant)
        if index < camp_count:
            item["encampment"] = True
            item["encampment_zone"] = {
                "kind": "encampment",
                "people": 0,
                "polygon": _encampment_polygon(item.get("polygon") or []),
            }
        else:
            item["encampment"] = False
            item.pop("encampment_zone", None)


def _encampment_polygon(polygon):
    if len(polygon) < 3:
        return []
    inset = geom.offset_polygon(polygon, 2.0)
    if abs(geom.poly_area(inset)) < 8.0:
        inset = geom.scale_about(polygon, 0.55)
    return [list(geom.r2(point)) for point in inset]


def _tier_held(item):
    return bool(item.get("locked")) or item.get("tier_source") == "hand"


def _strip_tier(item):
    if _tier_held(item):
        return
    for key in (
        "tier", "tier_source", "tier_score", "target_frontage_m",
        "lot_width_m", "lot_depth_m", "height_m", "front_setback_m", "side_setback_m",
        "coverage", "wear", "upkeep", "landscaping", "tree_density", "fence", "gate",
        "parked_per_100m", "lighting", "sidewalk", "materials", "furniture",
        "boarded", "vacant", "informal", "encampment", "encampment_zone",
    ):
        item.pop(key, None)


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
        if item.get("tier_source") != "hand":
            _strip_tier(item)
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
