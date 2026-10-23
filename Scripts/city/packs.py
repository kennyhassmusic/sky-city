"""Texture-pack loader for the city generator.

The AI packs are not in the repo yet. They are expected under Art/ai_textures/
(or a root passed to the loader) in this shape:

  packs/districts.json
  facades/<id>/manifest.json
  ground/<id>/manifest.json
  storefronts/<id>/manifest.json
  interiors/<id>/manifest.json
  decals/<id>/manifest.json

A set manifest names a role (basic or accent), a suggested use, and the
districts and income tiers it belongs to. Facade and ground sets carry
albedo, normal and roughness. Size, when present, is power-of-two on both
axes. scale_m is the real-world size of one tile. Each facade entry can
carry a glass mask plus window, bay and floor rects in 0..1 texture space.
A decal carries an alpha map.

packs/districts.json is the mix: one basic for the body, an optional accent
for the crown, the ground band or a corner, and neighbors that avoid
repeating that basic. Ground features named in the mix scatter list
(potholes, stains) are decals. They are not tiled.

Missing art, a missing manifest, or a set that fails those checks falls
back to the CC0 slots. This module does not open image files.

Run: python3 -I Scripts/city/test_packs.py
"""
import json
from pathlib import Path

import geom
import skyline

KINDS = ("facade", "ground", "storefront", "interior", "decal")
ROLES = ("basic", "accent")
_KIND_DIRS = {
    "facades": "facade",
    "facade": "facade",
    "ground": "ground",
    "grounds": "ground",
    "storefronts": "storefront",
    "storefront": "storefront",
    "interiors": "interior",
    "interior": "interior",
    "decals": "decal",
    "decal": "decal",
}
SCATTER_FEATURES = ("pothole", "stain")
DEFAULT_MIX = {
    "facade": {
        "body": "basic",
        "accents": ["crown", "ground_band", "corner"],
        "neighbors_avoid_repeat_basic": True,
    },
    "ground": {
        "body": "basic",
        "accents": [],
        "scatter": ["pothole", "stain"],
    },
}


def load_library(root=None):
    """Every valid set under the pack root, plus the mix and the rejects.

    `root` is a directory that contains the kind folders and packs/districts.json.
    With no root, Art/ai_textures is used when that folder exists. An empty
    library is valid: callers then use the CC0 slots.
    """
    base = _root(root)
    sets = []
    skipped = []
    if base is not None:
        for kind, folder in _kind_folders(base):
            for manifest in sorted(folder.glob("*/manifest.json")):
                item, reason = normalize_set(manifest, kind)
                if item is None:
                    skipped.append({"id": manifest.parent.name, "path": str(manifest), "reason": reason})
                else:
                    sets.append(item)
    sets.sort(key=lambda item: item["id"])
    return {
        "root": None if base is None else str(base),
        "mix": _read_mix(base),
        "sets": sets,
        "skipped": skipped,
    }


def for_district(library, district, tier=None):
    """Sets that may dress this district type and, when given, this income tier."""
    found = []
    for item in library.get("sets") or []:
        if _matches(item, district, tier):
            found.append(item)
    return found


def assign(model, library=None, root=None):
    """Choose a body, optional accents and decals for each building.

    The choice is seeded. Neighbors on the same block, or within 20 m, do not
    share a facade basic when another basic is eligible. Locked buildings that
    already carry a pack choice are left alone. Returns the building ids stamped.
    """
    library = library if library is not None else load_library(root)
    mix = library.get("mix") or DEFAULT_MIX
    lots = {lot.get("id"): lot for lot in model.get("lots") or []}
    districts = {item.get("id"): item for item in model.get("districts") or []}
    seed = int(model.get("seed") or 1)
    buildings = [b for b in model.get("buildings") or [] if b.get("role") != "context"]
    buildings.sort(key=lambda item: item.get("id") or "")
    chosen = {}
    touched = []
    for building in buildings:
        if building.get("locked") and building.get("pack"):
            chosen[building["id"]] = building["pack"]
            continue
        lot = lots.get(building.get("lot_id")) or {}
        district = districts.get(building.get("district_id") or lot.get("district_id")) or {}
        kind = lot.get("district_type") or district.get("district_type")
        tier = lot.get("tier") or district.get("tier")
        eligible = for_district(library, kind, tier) if kind else []
        avoid = _neighbor_basics(building, buildings, chosen, mix)
        pack = _bind(building, eligible, mix, avoid, seed)
        building["pack"] = pack
        chosen[building["id"]] = pack
        touched.append(building["id"])
    return touched


def normalize_set(manifest, kind):
    """One set, or (None, reason) when the manifest is not usable.

    Image files are not opened. A path in the manifest is kept as written,
    relative to the set folder.
    """
    data = _read_json(manifest)
    if not isinstance(data, dict):
        return None, "manifest is missing or not an object"
    ident = str(data.get("id") or manifest.parent.name)
    role = data.get("role")
    use = data.get("suggested_use") or data.get("suggestedUse") or data.get("use")
    feature = str(data.get("feature") or use or "")
    scatter = feature in SCATTER_FEATURES or data.get("placement") == "decal" or data.get("tile") is False
    if kind in ("facade", "ground"):
        if role not in ROLES:
            return None, "role must be basic or accent"
    elif role not in ROLES:
        role = "accent" if kind == "decal" or scatter else "basic"
    if kind == "decal":
        scatter = True
    size = data.get("size_px")
    if size is not None:
        if not (isinstance(size, (list, tuple)) and len(size) == 2 and _power_of_two(size[0]) and _power_of_two(size[1])):
            return None, "size_px must be power-of-two on both axes"
        size = [int(size[0]), int(size[1])]
    scale, scale_reason = _scale(data.get("scale_m") if data.get("scale_m") is not None else data.get("real_world_scale_m"))
    if scale_reason:
        return None, scale_reason
    maps = dict(data.get("maps") or {})
    for source_key, dest_key in (("albedo", "albedo"), ("color", "albedo"), ("normal", "normal"), ("roughness", "roughness")):
        if data.get(source_key) and dest_key not in maps:
            maps[dest_key] = data[source_key]
    alpha = data.get("alpha") or data.get("decal_alpha") or maps.get("alpha")
    facades, face_reason = _facades(data)
    if face_reason:
        return None, face_reason
    if scatter:
        tile = False
        placement = "decal"
    else:
        tile = True
        placement = "tile"
    return {
        "id": ident,
        "kind": kind,
        "role": role,
        "suggested_use": str(use or ("body" if role == "basic" else feature or kind)),
        "feature": feature,
        "districts": _name_list(data.get("districts") if data.get("districts") is not None else data.get("district")),
        "tiers": _name_list(data.get("tiers") if data.get("tiers") is not None else data.get("tier")),
        "maps": {key: str(value) for key, value in maps.items() if value},
        "size_px": size,
        "scale_m": scale,
        "glass_mask": data.get("glass_mask"),
        "facades": facades,
        "alpha": None if alpha in (None, "") else str(alpha),
        "tile": tile,
        "placement": placement,
        "path": str(manifest),
    }, None


def grammar_rects(face):
    """Window, bay and floor rects in 0..1 from a grammar facade.

    Used when a pack face has no rects of its own, including the CC0 fallback,
    so every opening still has a rectangle. A blind bay is a bay rect only.
    """
    count = max(1, int(face.get("bays") or 1))
    length = float(face.get("length") or 1.0) or 1.0
    pier = float(face.get("pier_w") or 0.0)
    opening = float(face.get("opening_w") or 0.0)
    kinds = list(face.get("bay_kinds") or [])
    floor = int(face.get("floor") or 0)
    sill = 0.22
    head = 0.78
    windows = []
    bays = []
    cursor = pier
    for index in range(count):
        u0 = max(0.0, min(1.0, cursor / length))
        u1 = max(u0, min(1.0, (cursor + opening) / length))
        if u1 <= u0:
            u1 = min(1.0, u0 + 1.0 / count)
        bays.append({"index": index, "floor": floor, "rect": _round_rect([u0, 0.0, u1, 1.0])})
        kind = kinds[index] if index < len(kinds) else "window"
        if kind != "blind":
            windows.append({
                "bay": index, "floor": floor,
                "rect": _round_rect([u0, sill, u1, head]),
            })
        cursor += opening + pier
    floors = [{"index": floor, "rect": [0.0, 0.0, 1.0, 1.0]}]
    return windows, bays, floors


def _bind(building, eligible, mix, avoid, seed):
    facade_mix = mix.get("facade") or DEFAULT_MIX["facade"]
    ground_mix = mix.get("ground") or DEFAULT_MIX["ground"]
    basics = [item for item in eligible if item["kind"] == "facade" and item["role"] == facade_mix.get("body", "basic")]
    body = _pick(basics, avoid if facade_mix.get("neighbors_avoid_repeat_basic", True) else (), seed, building.get("id"), "facade")
    accents = {}
    for use in facade_mix.get("accents") or []:
        pool = [item for item in eligible if item["kind"] == "facade" and item["role"] == "accent" and item["suggested_use"] == use]
        chosen = _pick(pool, (), seed, building.get("id"), "accent", use)
        if chosen:
            accents[use] = chosen["id"]
    ground_pool = [item for item in eligible if item["kind"] == "ground" and item["role"] == ground_mix.get("body", "basic") and item["tile"]]
    ground = _pick(ground_pool, (), seed, building.get("id"), "ground")
    scatter_names = set(ground_mix.get("scatter") or SCATTER_FEATURES)
    decals = []
    for item in eligible:
        feature = item.get("feature") or item.get("suggested_use")
        if item["kind"] == "decal" or (item["kind"] == "ground" and feature in scatter_names):
            decals.append({
                "id": item["id"],
                "feature": feature,
                "alpha": item.get("alpha"),
                "tile": False,
                "placement": "decal",
                "scale_m": item.get("scale_m"),
                "maps": dict(item.get("maps") or {}),
            })
    decals.sort(key=lambda item: item["id"])
    storefront = _pick([item for item in eligible if item["kind"] == "storefront"], (), seed, building.get("id"), "storefront")
    interior = _pick([item for item in eligible if item["kind"] == "interior"], (), seed, building.get("id"), "interior")
    return {
        "source": "pack" if body or ground or decals or storefront or interior else "cc0",
        "facade": {
            "basic": None if body is None else body["id"],
            "accents": accents,
            "scale_m": None if body is None else body.get("scale_m"),
            "maps": {} if body is None else dict(body.get("maps") or {}),
            "faces": _faces(building, body),
        },
        "ground": {
            "basic": None if ground is None else ground["id"],
            "tile": True,
            "scale_m": None if ground is None else ground.get("scale_m"),
            "maps": {} if ground is None else dict(ground.get("maps") or {}),
            "decals": decals,
        },
        "storefront": None if storefront is None else storefront["id"],
        "interior": None if interior is None else interior["id"],
    }


def _faces(building, body):
    packed = {}
    if body:
        for entry in body.get("facades") or []:
            packed.setdefault(entry.get("role") or "", []).append(entry)
        if body.get("glass_mask") and "" not in packed and not packed:
            packed[""] = [{"role": "", "glass_mask": body["glass_mask"], "windows": [], "bays": [], "floors": []}]
    out = []
    for face in building.get("facades") or []:
        role = face.get("role") or ""
        entry = _face_entry(packed, role)
        windows = _for_floor(entry.get("windows") if entry else None, face.get("floor"))
        bays = _for_floor(entry.get("bays") if entry else None, face.get("floor"))
        floors = _for_floor(entry.get("floors") if entry else None, face.get("floor"))
        if not windows or not bays or not floors:
            grown_w, grown_b, grown_f = grammar_rects(face)
            windows = windows or grown_w
            bays = bays or grown_b
            floors = floors or grown_f
        out.append({
            "floor": face.get("floor"),
            "role": role,
            "glass_mask": None if not entry else entry.get("glass_mask"),
            "windows": windows,
            "bays": bays,
            "floors": floors,
        })
    return out


def _face_entry(packed, role):
    if role in packed and packed[role]:
        return packed[role][0]
    if "" in packed and packed[""]:
        return packed[""][0]
    return None


def _for_floor(items, floor):
    if not items:
        return []
    specific = [item for item in items if item.get("floor") is not None and int(item.get("floor")) == int(floor or 0)]
    if specific:
        return specific
    return [item for item in items if item.get("floor") is None]


def _neighbor_basics(building, buildings, chosen, mix):
    if not (mix.get("facade") or {}).get("neighbors_avoid_repeat_basic", True):
        return set()
    avoid = set()
    block = building.get("block_id")
    centre = _centre(building.get("footprint"))
    for other in buildings:
        if other.get("id") == building.get("id"):
            continue
        pack = chosen.get(other.get("id"))
        if not pack:
            continue
        basic = (pack.get("facade") or {}).get("basic")
        if not basic:
            continue
        same_block = block and other.get("block_id") == block
        near = False
        if centre is not None:
            other_centre = _centre(other.get("footprint"))
            if other_centre is not None:
                near = geom.dist(centre, other_centre) <= 20.0
        if same_block or near:
            avoid.add(basic)
    return avoid


def _pick(pool, avoid, seed, *parts):
    ordered = sorted(pool, key=lambda item: item["id"])
    usable = [item for item in ordered if item["id"] not in set(avoid)] or ordered
    if not usable:
        return None
    index = int(geom.rnd(seed, *parts) * len(usable))
    if index >= len(usable):
        index = len(usable) - 1
    return usable[index]


def _matches(item, district, tier):
    if item.get("districts") and district not in item["districts"]:
        return False
    tiers = item.get("tiers") or []
    if tier is None:
        return not tiers
    return not tiers or tier in tiers


def _facades(data):
    raw = data.get("facades")
    if raw is None:
        mask = data.get("glass_mask")
        if isinstance(mask, dict):
            raw = [{"role": key, "glass_mask": value} for key, value in mask.items()]
        else:
            return [], None
    if not isinstance(raw, list):
        return None, "facades must be a list"
    out = []
    for entry in raw:
        if not isinstance(entry, dict):
            return None, "a facade entry must be an object"
        windows, reason = _rects(entry.get("windows"), "window")
        if reason:
            return None, reason
        bays, reason = _rects(entry.get("bays"), "bay")
        if reason:
            return None, reason
        floors, reason = _rects(entry.get("floors"), "floor")
        if reason:
            return None, reason
        out.append({
            "role": entry.get("role") or entry.get("name") or "",
            "glass_mask": entry.get("glass_mask"),
            "windows": windows,
            "bays": bays,
            "floors": floors,
        })
    return out, None


def _rects(items, kind):
    if items is None:
        return [], None
    if not isinstance(items, list):
        return None, "%s rects must be a list" % kind
    out = []
    for item in items:
        if not isinstance(item, dict):
            return None, "a %s rect must be an object" % kind
        rect = _rect(item.get("rect"))
        if rect is None:
            return None, "a %s rect must be u0,v0,u1,v1 inside 0..1" % kind
        kept = {"rect": rect}
        if kind == "window":
            if item.get("bay") is not None:
                kept["bay"] = int(item["bay"])
            if item.get("floor") is not None:
                kept["floor"] = int(item["floor"])
        elif kind == "bay":
            if item.get("index") is not None:
                kept["index"] = int(item["index"])
            elif item.get("bay") is not None:
                kept["index"] = int(item["bay"])
            if item.get("floor") is not None:
                kept["floor"] = int(item["floor"])
        else:
            if item.get("index") is not None:
                kept["index"] = int(item["index"])
            elif item.get("floor") is not None:
                kept["index"] = int(item["floor"])
                kept["floor"] = int(item["floor"])
            if item.get("floor") is not None and "floor" not in kept:
                kept["floor"] = int(item["floor"])
        out.append(kept)
    return out, None


def _rect(value):
    if isinstance(value, dict):
        value = [value.get("u0"), value.get("v0"), value.get("u1"), value.get("v1")]
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        u0, v0, u1, v1 = (float(part) for part in value)
    except (TypeError, ValueError):
        return None
    if not (0.0 <= u0 < u1 <= 1.0 and 0.0 <= v0 < v1 <= 1.0):
        return None
    return _round_rect([u0, v0, u1, v1])


def _round_rect(rect):
    return [round(float(part), 4) for part in rect]


def _scale(value):
    if value is None:
        return None, None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        value = {"width": value[0], "height": value[1]}
    if not isinstance(value, dict) or "width" not in value or "height" not in value:
        return None, "scale_m needs width and height in metres"
    try:
        width = float(value["width"])
        height = float(value["height"])
    except (TypeError, ValueError):
        return None, "scale_m needs width and height in metres"
    if width <= 0 or height <= 0:
        return None, "scale_m must be positive"
    return {"width": round(width, 3), "height": round(height, 3)}, None


def _read_mix(base):
    if base is None:
        return json.loads(json.dumps(DEFAULT_MIX))
    path = base / "packs" / "districts.json"
    data = _read_json(path)
    if not isinstance(data, dict):
        return json.loads(json.dumps(DEFAULT_MIX))
    facade = data.get("facade") or {}
    ground = data.get("ground") or {}
    accents = facade.get("accents")
    if accents is None:
        accents = facade.get("accent_uses")
    if accents is None:
        accents = list(DEFAULT_MIX["facade"]["accents"])
    scatter = ground.get("scatter")
    if scatter is None:
        scatter = ground.get("scatter_features")
    if scatter is None:
        scatter = list(DEFAULT_MIX["ground"]["scatter"])
    ground_accents = ground.get("accents")
    if ground_accents is None:
        ground_accents = []
    return {
        "facade": {
            "body": facade.get("body") or facade.get("body_role") or "basic",
            "accents": [str(item) for item in accents],
            "neighbors_avoid_repeat_basic": bool(facade.get("neighbors_avoid_repeat_basic", True)),
        },
        "ground": {
            "body": ground.get("body") or ground.get("body_role") or "basic",
            "accents": [str(item) for item in ground_accents],
            "scatter": [str(item) for item in scatter],
        },
    }


def _kind_folders(base):
    found = []
    seen = set()
    for name, kind in _KIND_DIRS.items():
        folder = base / name
        if folder.is_dir() and folder not in seen:
            seen.add(folder)
            found.append((kind, folder))
    sets = base / "packs" / "sets"
    if sets.is_dir():
        for name, kind in _KIND_DIRS.items():
            folder = sets / name
            if folder.is_dir() and folder not in seen:
                seen.add(folder)
                found.append((kind, folder))
    return found


def _root(root):
    if root is not None:
        path = Path(root)
        return path if path.is_dir() else None
    try:
        art = skyline.project_root() / "Art" / "ai_textures"
    except RuntimeError:
        return None
    if art.is_dir():
        return art
    return None


def _read_json(path):
    if path is None or not Path(path).is_file():
        return None
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def _name_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _power_of_two(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return False
    return number >= 1 and (number & (number - 1)) == 0


def _centre(polygon):
    if not polygon or len(polygon) < 3:
        return None
    return geom.centroid([(float(point[0]), float(point[1])) for point in polygon])
