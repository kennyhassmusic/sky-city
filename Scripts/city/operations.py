"""Operations the Map Designer and the AI link both call.

add_district, set_skyline, draw_road, split_block, set_building, lock, unlock,
regenerate, screenshot. Nothing here knows about Unreal or Blender. A later plugin
maps these names onto buttons and onto the local MCP server. Each change returns
(model, touched ids) and leaves the caller's model alone. screenshot returns a
request and does not change the manifest hash.

Regeneration is non-destructive: it rebuilds a layer from the layers above it and
keeps anything locked or drawn by hand.
"""
import copy
import zlib

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
    if "trees" in updates:
        district["trees"] = list(updates.pop("trees"))
    district.setdefault("skyline", {}).update(updates)
    _audit(model, "set_skyline", [district_id], {"fields": sorted(updates.keys())})
    return model, [district_id]


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
