"""Operations the Map Designer and the AI link both call.

add_district, set_skyline, set_district_type, set_mix, assign_districts, set_tier,
set_tier_mix, assign_tiers, draw_road, split_block, set_building, lock, unlock,
regenerate, screenshot, texture_pack.
Nothing here knows about Unreal or Blender. A later plugin maps these names onto
buttons and onto the local MCP server. Each change returns (model, touched ids)
and leaves the caller's model alone. screenshot returns a request and does not
change the manifest hash. texture_pack is a lookup: it returns the pack record
and does not change the model.

Regeneration is non-destructive: it rebuilds a layer from the layers above it and
keeps anything locked or drawn by hand.
"""
import copy
import zlib

import districts as district_types
import geom
import grammar
import model as model_mod
import skyline


def add_district(model, polygon, character="downtown", name=None, style=None,
                 skyline_overrides=None, trees=None, district_id=None):
    """Paint a district. Character copies style, trees and the skyline preset."""
    model = copy.deepcopy(model)
    sky = skyline.load()
    preset = (sky.get("characters") or {}).get(character) or {}
    if character not in ("downtown", "residential", "industrial", "park", "waterfront", "custom"):
        raise ValueError("unknown character %s" % character)
    poly = [[round(float(p[0]), 2), round(float(p[1]), 2)] for p in polygon]
    ident = district_id or _hid("d", name or character, poly)
    district = {
        "id": ident,
        "name": name or character,
        "source": "hand",
        "locked": False,
        "polygon": poly,
        "character": character,
        "style": style or preset.get("style") or "prewar_masonry",
        "trees": list(trees or preset.get("trees") or ["linden", "elm"]),
        "skyline": dict(skyline_overrides or {}),
    }
    model["districts"].append(district)
    _audit(model, "add_district", [ident], {"character": character, "name": district["name"]})
    return model, [ident]


def set_skyline(model, district_id, updates):
    """Merge skyline fields onto one district. `style` sets the district style itself.

    This does not rebuild buildings. Call regenerate afterwards so locked buildings
    stay put and the rest pick up the new heights.
    """
    model = copy.deepcopy(model)
    district = _must(model, district_id, "districts")
    updates = dict(updates or {})
    if "style" in updates:
        district["style"] = updates.pop("style")
        district["style_pinned"] = True
    if "trees" in updates:
        district["trees"] = list(updates.pop("trees"))
    district.setdefault("skyline", {}).update(updates)
    _audit(model, "set_skyline", [district_id], {"fields": sorted(updates.keys())})
    return model, [district_id]


def set_district_type(model, district_id, type_name):
    """Give one district a type. Hand-set, so a later assign_districts leaves it.

    The type's building list, heights, roofs, materials, plants, wear and
    furniture are copied onto the district. A style pin is cleared: the type's
    buildings are allowed to vary until set_skyline pins a style again. Blocks
    and lots already inside the district pick up the type, or its nested mix.
    """
    model = copy.deepcopy(model)
    district = _must(model, district_id, "districts")
    sky = skyline.load()
    types = district_types.table(sky)
    district_types.apply_type(district, type_name, types, source="hand", keep_style_pin=False)
    children = district_types.stamp_children(model, district, types, model.get("seed") or 1)
    ids = [district_id] + [item for item in children if item and item != district_id]
    _audit(model, "set_district_type", ids, {"district_type": type_name})
    return model, ids


def set_mix(model, district_id, weights):
    """Store a nested mix on one district and paint the blocks and lots inside it.

    Weights are shares, the same way skyline.yaml writes them. This mix is
    hand-set, so assigning a type later does not replace it.
    """
    model = copy.deepcopy(model)
    district = _must(model, district_id, "districts")
    clean = _mix_weights(weights)
    district["mix"] = clean
    district["mix_source"] = "hand"
    sky = skyline.load()
    types = district_types.table(sky)
    children = district_types.stamp_children(model, district, types, model.get("seed") or 1)
    ids = [district_id] + [item for item in children if item and item != district_id]
    _audit(model, "set_mix", ids, {"types": sorted(clean)})
    return model, ids


def assign_districts(model, region=None, mix=None):
    """Paint unlocked districts from a region mix, the city mix, or an explicit one.

    Placement is weighted and seeded. Utilities and industrial stay off the
    boundary of houses when the mix contains another type that can go there.
    A type that carries a nested mix (eclectic_mix, or a hand mix already on
    the district) is then painted onto that district's blocks and lots.
    """
    model = copy.deepcopy(model)
    sky = skyline.load()
    types = district_types.table(sky)
    weights = _mix_weights(mix) if mix is not None else district_types.resolve_mix(sky, region)
    district_types.assign(model.get("districts") or [], weights, int(model.get("seed") or 1), types)
    touched = []
    for district in model.get("districts") or []:
        touched.append(district["id"])
        if district.get("mix") or district.get("district_type"):
            touched.extend(district_types.stamp_children(
                model, district, types, int(model.get("seed") or 1)))
    _audit(model, "assign_districts", touched, {"region": region or "city"})
    return model, touched


def set_tier(model, element_id, tier):
    """Pin one lot, block or district to an income tier. Hand-set, so assign_tiers leaves it.

    The element has to sit in a houses or apartments district. Distressed adds
    boarded windows or a vacant lot, and an encampment zone with no people.
    """
    if tier not in district_types.TIER_NAMES:
        raise ValueError("unknown income tier %s" % tier)
    model = copy.deepcopy(model)
    key, item = model_mod.find(model, element_id)
    if item is None or key not in ("lots", "blocks", "districts"):
        raise KeyError("no lot, block or district %s" % element_id)
    kind = _tier_kind(model, item)
    if kind not in district_types.TIERED_TYPES:
        raise ValueError("%s is not in a houses or apartments district" % element_id)
    sky = skyline.load()
    types = district_types.table(sky)
    item["tier_source"] = "hand"
    district_types._apply_tier_fields(item, types, kind, tier)
    if tier == "distressed":
        district_types._mark_distress([item], types, kind)
    else:
        district_types._clear_distress(item)
    _audit(model, "set_tier", [element_id], {"tier": tier})
    return model, [element_id]


def set_tier_mix(model, district_id, weights):
    """Store an income mix on one houses or apartments district and band its lots.

    The keys are high, mid, low and distressed. Shares must be positive. This
    mix is hand-set, so a later type assignment does not replace it.
    """
    model = copy.deepcopy(model)
    district = _must(model, district_id, "districts")
    kind = district.get("district_type")
    if kind not in district_types.TIERED_TYPES:
        raise ValueError("%s is not a houses or apartments district" % district_id)
    clean = _tier_weights(weights)
    district["tier_mix"] = clean
    district["tier_mix_source"] = "hand"
    sky = skyline.load()
    types = district_types.table(sky)
    targets = _tier_targets(model, district, kind)
    touched = district_types.assign_tiers(
        targets, clean, int(model.get("seed") or 1), district, types, kind)
    ids = [district_id] + [item for item in touched if item and item != district_id]
    _audit(model, "set_tier_mix", ids, {"tiers": list(district_types.TIER_NAMES)})
    return model, ids


def assign_tiers(model, district_id=None):
    """Band houses and apartments lots from their tier mix. Hand tiers stay put."""
    model = copy.deepcopy(model)
    sky = skyline.load()
    types = district_types.table(sky)
    touched = []
    seed = int(model.get("seed") or 1)
    for district in model.get("districts") or []:
        if district_id and district.get("id") != district_id:
            continue
        groups = {}
        for lot in model.get("lots") or []:
            if lot.get("district_id") != district.get("id"):
                continue
            kind = lot.get("district_type") or district.get("district_type")
            if kind in district_types.TIERED_TYPES:
                groups.setdefault(kind, []).append(lot)
        if not groups and district.get("district_type") in district_types.TIERED_TYPES:
            groups[district["district_type"]] = _tier_targets(model, district, district["district_type"])
        for kind, group in groups.items():
            if not group:
                continue
            weights = district_types._tier_weights(district, types, kind)
            touched.extend(district_types.assign_tiers(group, weights, seed, district, types, kind))
    _audit(model, "assign_tiers", touched, {"district": district_id or "all"})
    return model, touched


def texture_pack(type_name, root=None, tier=None):
    """The texture pack for a district type, or the CC0 slots when the pack is absent.

    This does not change a city model. `root` is the folder that contains
    `packs/<district>/manifest.json`. Pass `tier` to read
    `packs/<district>/<tier>/manifest.json` first. The default root is Scripts/city.
    """
    return district_types.load_pack(type_name, root=root, tier=tier)


def draw_road(model, polyline, cls="minor", lanes=2, oneway=False, core=False,
              name="", district_id=None, road_id=None):
    """A centreline. Crossings become block corners on the next regenerate."""
    model = copy.deepcopy(model)
    pts = [[round(float(p[0]), 2), round(float(p[1]), 2)] for p in polyline]
    if len(pts) < 2:
        raise ValueError("a road needs two points")
    ident = road_id or _hid("road", pts, cls, name)
    model["roads"].append({
        "id": ident,
        "source": "hand",
        "locked": False,
        "polyline": pts,
        "cls": cls,
        "lanes": int(lanes),
        "oneway": bool(oneway),
        "core": bool(core),
        "name": name or "",
        "district_id": district_id,
    })
    _audit(model, "draw_road", [ident], {"cls": cls, "name": name})
    return model, [ident]


def split_block(model, block_id, t):
    """Cut a rectangular block along its long side. `t` is a fraction from 0 to 1.

    The two halves are source hand and locked, so regenerating blocks keeps them
    and does not recreate the parent face. The parent is removed.
    """
    model = copy.deepcopy(model)
    if not 0.15 < float(t) < 0.85:
        raise ValueError("split t must sit between 0.15 and 0.85, got %s" % t)
    block = _must(model, block_id, "blocks")
    frame = geom.rectangle_frame(block["polygon"])
    if frame is None:
        raise ValueError("split_block needs a rectangular block, and %s is not one" % block_id)
    cut = frame["width"] * float(t)
    west = _half(frame, 0.0, cut)
    east = _half(frame, cut, frame["width"])
    children = []
    for tag, poly in (("w", west), ("e", east)):
        child = {
            "id": "%s_%s" % (block_id, tag),
            "source": "hand",
            "locked": True,
            "district_id": block.get("district_id"),
            "polygon": poly,
            # The half sits inside the parent face, which is what tells regenerate
            # not to invent that face again.
            "centreline_polygon": poly,
            "edges": [],
            "alley": None,
            "area": round(abs(geom.poly_area(poly)), 2),
            "split_from": block_id,
        }
        children.append(child)
    model["blocks"] = [b for b in model["blocks"] if b["id"] != block_id] + children
    model["lots"] = [lot for lot in model["lots"] if lot.get("block_id") != block_id]
    model["buildings"] = [b for b in model["buildings"] if b.get("block_id") != block_id]
    ids = [c["id"] for c in children]
    _audit(model, "split_block", ids, {"parent": block_id, "t": float(t)})
    return model, ids


def set_building(model, lot_id, style=None, height=None, sky=None):
    """Run the grammar once on a lot, then freeze the result as a hand edit.

    A later change to the district style does not rebuild it. Pass height to pin
    the metres; otherwise the skyline decides, and an OSM height tag on the lot wins.
    """
    model = copy.deepcopy(model)
    lot = _must(model, lot_id, "lots")
    sky = sky or skyline.load()
    district = next((d for d in model["districts"] if d["id"] == lot.get("district_id")), None)
    params = skyline.for_district(district or {"character": "downtown"}, sky)
    if height is not None:
        lot = copy.deepcopy(lot)
        lot.setdefault("tags", {})["height"] = float(height)
    spec = grammar.evaluate(lot, style or params["style"], params, model.get("seed") or 1)
    spec["source"] = "hand"
    spec["locked"] = True
    spec["district_id"] = lot.get("district_id")
    spec["block_id"] = lot.get("block_id")
    model["buildings"] = [b for b in model["buildings"] if b.get("lot_id") != lot_id and b["id"] != spec["id"]]
    model["buildings"].append(spec)
    _audit(model, "set_building", [spec["id"]], {"lot": lot_id, "style": spec["style"]})
    return model, [spec["id"]]


def lock(model, element_id):
    """Keep this element the next time its layer regenerates."""
    return _set_lock(model, element_id, True)


def unlock(model, element_id):
    return _set_lock(model, element_id, False)


def regenerate(model, layer, district_id=None, sky=None):
    """Rebuild `layer` and everything under it. Locked and hand elements stay."""
    model = model_mod.regenerate(model, layer, district_id=district_id, sky=sky)
    _audit(model, "regenerate", [district_id or layer], {"layer": layer})
    return model, [layer]


def screenshot(model, camera=None):
    """A request for the renderer. The city model is not modified, so the hash holds."""
    return {
        "op": "screenshot",
        "seed": model.get("seed"),
        "camera": camera or {},
        "hash": model_mod.manifest_hash(model),
    }


def _set_lock(model, element_id, locked):
    model = copy.deepcopy(model)
    _key, item = model_mod.find(model, element_id)
    if item is None:
        raise KeyError("no element %s" % element_id)
    item["locked"] = bool(locked)
    _audit(model, "lock" if locked else "unlock", [element_id], {})
    return model, [element_id]


def _must(model, element_id, layer):
    for item in model.get(layer) or []:
        if item.get("id") == element_id:
            return item
    raise KeyError("no %s %s" % (layer[:-1], element_id))


def _half(frame, x0, x1):
    depth = frame["depth"]
    return [list(p) for p in geom.world_poly([(x0, 0), (x1, 0), (x1, depth), (x0, depth)], frame)]


def _audit(model, op, ids, detail):
    ident = "ov_%08x" % (zlib.crc32(repr((op, list(ids), len(model.get("overrides") or []))).encode()) & 0xffffffff)
    model.setdefault("overrides", []).append({
        "id": ident,
        "source": "hand",
        "locked": True,
        "op": op,
        "targets": list(ids),
        "detail": detail,
    })


def _hid(prefix, *parts):
    return "%s_%08x" % (prefix, zlib.crc32(repr(parts).encode()) & 0xffffffff)


def _tier_kind(model, item):
    kind = item.get("district_type")
    if kind in district_types.TIERED_TYPES:
        return kind
    district_id = item.get("district_id")
    if not district_id:
        return kind
    for district in model.get("districts") or []:
        if district.get("id") == district_id:
            return district.get("district_type")
    return kind


def _tier_targets(model, district, kind):
    lots = [lot for lot in model.get("lots") or []
            if lot.get("district_id") == district.get("id")
            and (lot.get("district_type") in (None, kind))]
    if lots:
        return lots
    return [block for block in model.get("blocks") or []
            if block.get("district_id") == district.get("id")
            and (block.get("district_type") in (None, kind))]


def _tier_weights(weights):
    clean = {}
    for name, weight in (weights or {}).items():
        if name not in district_types.TIER_NAMES:
            raise ValueError("unknown income tier %s" % name)
        amount = float(weight)
        if amount <= 0:
            raise ValueError("tier %s needs a positive share" % name)
        clean[name] = amount
    missing = [name for name in district_types.TIER_NAMES if name not in clean]
    if missing:
        raise ValueError("tier mix needs %s" % ", ".join(missing))
    return clean


def _mix_weights(weights):
    clean = {}
    for name, weight in (weights or {}).items():
        if name not in district_types.TYPE_NAMES:
            raise ValueError("unknown district type %s" % name)
        amount = float(weight)
        if amount > 0:
            clean[name] = amount
    if not clean:
        raise ValueError("a mix needs at least one district type")
    return clean
