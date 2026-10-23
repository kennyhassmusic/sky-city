"""The city model: layers, locks, and non-destructive regeneration.

Layers, top to bottom: districts, roads, blocks, lots, buildings, streetscape.
Regenerating a layer rebuilds it from the layers above and then rebuilds everything
below it. An element with locked set, or with source "hand", is kept and treated as
a constraint: a generated face that would cover a locked block is not created, and
a locked building is copied through unchanged. An OSM lot that this rebuild drops
still lends its surveyed tags (height, levels, roof) to the new lot that contains
it, which is how a plan keeps a measured height.

The same seed and the same model produce the same manifest hash. Screenshot requests
and other bookkeeping stay out of that hash.
"""
import copy
import hashlib
import json

import geom
import grammar
import lots as lots_mod
import network
import schema
import skyline
import streets


def new_model(bounds, seed):
    return {
        "version": 1,
        "seed": int(seed),
        "bounds": [float(v) for v in bounds],
        "districts": [],
        "roads": [],
        "blocks": [],
        "lots": [],
        "buildings": [],
        "overrides": [],
    }


def regenerate(model, layer, district_id=None, sky=None):
    """Rebuild `layer` and every layer under it. Returns the new model; input is not mutated."""
    if layer not in ("blocks", "lots", "buildings", "streetscape"):
        raise ValueError("regenerate blocks, lots, buildings or streetscape, not %s" % layer)
    model = copy.deepcopy(model)
    sky = sky or skyline.load()
    order = ["blocks", "lots", "buildings", "streetscape"]
    for name in order[order.index(layer):]:
        if name == "blocks":
            _rebuild_blocks(model, district_id)
        elif name == "lots":
            _rebuild_lots(model, district_id)
        elif name == "buildings":
            _rebuild_buildings(model, district_id, sky)
        else:
            _rebuild_streetscape(model, district_id)
    schema.validate(model)
    return model


def manifest(model):
    """The comparable part of the city: one row per real building, in id order."""
    rows = []
    for b in model.get("buildings") or []:
        if b.get("role") == "context":
            continue
        rows.append({
            "id": b["id"],
            "style": b.get("style"),
            "seed": b.get("seed"),
            "height": b.get("height"),
            "footprint": b.get("footprint"),
            "locked": b.get("locked"),
            "source": b.get("source"),
            "district_id": b.get("district_id"),
            "role": b.get("role") or "building",
        })
    rows.sort(key=lambda r: r["id"])
    return rows


def manifest_hash(model):
    blob = json.dumps(manifest(model), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def district_at(model, point):
    for district in model.get("districts") or []:
        if geom.point_in_poly(point, district["polygon"]):
            return district
    return None


def find(model, element_id):
    for key in ("districts", "roads", "blocks", "lots", "buildings", "overrides"):
        for item in model.get(key) or []:
            if item.get("id") == element_id:
                return key, item
    for prop in (model.get("streetscape") or {}).get("props") or []:
        if prop.get("id") == element_id:
            return "props", prop
    return None, None


def _rebuild_blocks(model, district_id):
    faces = network.faces(network.node_roads(model.get("roads") or []))
    kept = []
    for block in model.get("blocks") or []:
        outside = district_id and block.get("district_id") not in (None, district_id)
        if outside or block.get("locked") or block.get("source") == "hand":
            kept.append(block)
    fresh = []
    for face in faces:
        centre = geom.centroid(face["polygon"])
        district = district_at(model, centre)
        if district is None:
            continue
        if district_id and district["id"] != district_id:
            continue
        if _covered_by_hand(centre, face["polygon"], kept):
            continue
        fresh.append(_face_block(model, face, district))
    # a regenerated id that a lock already holds is the lock's copy
    held = {b["id"] for b in kept}
    model["blocks"] = kept + [b for b in fresh if b["id"] not in held]


def _covered_by_hand(centre, face, blocks):
    for block in blocks:
        if not (block.get("locked") or block.get("source") == "hand"):
            continue
        poly = block.get("centreline_polygon") or block.get("polygon")
        if geom.point_in_poly(centre, poly) or geom.point_in_poly(geom.centroid(poly), face):
            return True
    return False


def _face_block(model, face, district):
    import sys
    from pathlib import Path
    roads = Path(__file__).resolve().parents[1] / "roads"
    if str(roads) not in sys.path:
        sys.path.insert(0, str(roads))
    import profiles
    edges = face["edges"]
    dists = []
    for edge in edges:
        sec = profiles.preview_section(edge["cls"], edge["lanes"], edge["oneway"], edge["core"])
        dists.append(sec["width"] / 2.0 + profiles.curb_back_from_flow(edge["cls"]) + sec["sidewalk"])
    if len(dists) == len(face["polygon"]):
        property_poly = geom.offset_edges(face["polygon"], dists)
    else:
        property_poly = geom.offset_polygon(face["polygon"], sum(dists) / max(1, len(dists)))
    property_poly = [list(geom.r2(p)) for p in geom.ensure_ccw(property_poly)]
    centreline = [list(p) for p in face["polygon"]]
    # The face key is the identity. crc32 of it stays the same for the same streets.
    import zlib
    block_id = "block_%08x" % (zlib.crc32(repr(tuple(face["key"])).encode()) & 0xffffffff)
    sub = lots_mod.subdivide(property_poly, seed=model.get("seed") or 1)
    return {
        "id": block_id,
        "source": "generated",
        "locked": False,
        "district_id": district["id"],
        "polygon": property_poly,
        "centreline_polygon": centreline,
        "edges": edges,
        "alley": sub["alley"],
        "area": face["area"],
    }


def _rebuild_lots(model, district_id):
    kept_other = []
    new_lots = []
    donors = _survey_donors(model, district_id)
    for lot in model.get("lots") or []:
        if district_id and lot.get("district_id") != district_id:
            kept_other.append(lot)
    for block in model.get("blocks") or []:
        if district_id and block.get("district_id") != district_id:
            continue
        existing = [lot for lot in model.get("lots") or []
                    if lot.get("block_id") == block["id"] and (lot.get("locked") or lot.get("source") == "hand")]
        made = lots_mod.subdivide(block["polygon"], seed=model.get("seed") or 1)
        # alley lives on the block so the streetscape can pave it; refresh it when
        # the block itself is generated. A hand block keeps the alley it was given.
        if not (block.get("locked") or block.get("source") == "hand"):
            block["alley"] = made["alley"]
        elif block.get("alley") is None:
            block["alley"] = made["alley"]
        fresh = []
        for piece in made["lots"]:
            lot_id = "lot_%s_%s" % (block["id"], piece["tag"])
            if any(lot["id"] == lot_id or _overlaps(piece["polygon"], lot["polygon"]) for lot in existing):
                continue
            fresh.append({
                "id": lot_id,
                "source": "generated",
                "locked": False,
                "block_id": block["id"],
                "district_id": block.get("district_id"),
                "polygon": piece["polygon"],
                "front_normals": piece["front_normals"],
                "role": "lot",
                "tags": _tags_from_donors(piece["polygon"], donors),
            })
        new_lots.extend(existing)
        new_lots.extend(fresh)
    model["lots"] = kept_other + new_lots


def _rebuild_buildings(model, district_id, sky):
    seed = int(model.get("seed") or 1)
    by_lot = {}
    kept = []
    for building in model.get("buildings") or []:
        outside = district_id and building.get("district_id") not in (None, district_id)
        if building.get("role") == "landmark" or outside:
            kept.append(building)
            continue
        if building.get("locked") or building.get("source") == "hand":
            kept.append(building)
            if building.get("lot_id"):
                by_lot[building["lot_id"]] = building
    fresh = []
    for district in model.get("districts") or []:
        if district_id and district["id"] != district_id:
            continue
        params = skyline.for_district(district, sky)
        district_lots = [lot for lot in model.get("lots") or [] if lot.get("district_id") == district["id"]]
        _assign_heroes(district_lots, params, seed)
        for lot in district_lots:
            if lot["id"] in by_lot:
                continue
            spec = grammar.evaluate(lot, params["style"], params, seed)
            spec["district_id"] = district["id"]
            fresh.append(spec)
    model["buildings"] = kept + fresh


def _assign_heroes(district_lots, params, seed):
    for lot in district_lots:
        lot.pop("hero", None)
        lot.pop("hero_rank", None)
    count = int(params.get("hero_count") or 0)
    if count <= 0:
        return
    spacing = float(params.get("hero_min_spacing_m") or 80)
    anchor = params.get("hero_anchor") or params.get("centre") or [0, 0]
    ordered = sorted(district_lots, key=lambda lot: (
        _anchor_dist(lot, anchor),
        geom.rnd(seed, lot["id"], "hero"),
        lot["id"],
    ))
    chosen = []
    for lot in ordered:
        c = geom.centroid(lot["polygon"])
        if any(geom.dist(c, prev) < spacing for prev in chosen):
            continue
        lot["hero"] = True
        lot["hero_rank"] = len(chosen)
        chosen.append(c)
        if len(chosen) >= count:
            break


def _anchor_dist(lot, anchor):
    c = geom.centroid(lot["polygon"])
    return geom.dist(c, (float(anchor[0]), float(anchor[1])))


def _rebuild_streetscape(model, district_id):
    previous = (model.get("streetscape") or {}).get("props") or []
    locked = [p for p in previous if p.get("locked") or p.get("source") == "hand"]
    built = streets.build(model)
    if district_id:
        old = model.get("streetscape") or {}
        built = _merge_district_streetscape(old, built, district_id)
    generated = []
    for prop in built.get("props") or []:
        if any(prop["id"] == old["id"] or geom.dist((prop["x"], prop["y"]), (old["x"], old["y"])) < 1.5
               for old in locked):
            continue
        generated.append(prop)
    built["props"] = locked + generated
    model["streetscape"] = built


def _merge_district_streetscape(old, built, district_id):
    """Replace only the pieces stamped with this district. Other districts stay."""
    def belongs(item):
        return item.get("district_id") == district_id

    merged = {"version": 1}
    for key in ("surfaces",):
        out = {}
        old_s = (old.get(key) or {})
        new_s = built.get(key) or {}
        names = set(old_s) | set(new_s)
        for name in names:
            kept = [p for p in old_s.get(name) or [] if not belongs(p)]
            made = [p for p in new_s.get(name) or [] if belongs(p)]
            out[name] = kept + made
        merged[key] = out
    for key in ("curb_paths", "crosswalks", "ramps", "props", "blocks"):
        kept = [p for p in old.get(key) or [] if not belongs(p)]
        made = [p for p in built.get(key) or [] if belongs(p)]
        merged[key] = kept + made
    merged["sections"] = dict(old.get("sections") or {})
    merged["sections"].update(built.get("sections") or {})
    return merged


def _survey_donors(model, district_id):
    """Centroids and tags of OSM lots this rebuild is about to drop.

    seed_from_plan writes one lot per surveyed footprint and says a later
    regenerate keeps that height. The lot grid replaces those lots, so the
    tags have to move onto whichever new lot contains the old centroid.
    """
    donors = []
    for lot in model.get("lots") or []:
        if district_id and lot.get("district_id") != district_id:
            continue
        if lot.get("locked") or lot.get("source") == "hand":
            continue
        if lot.get("source") != "osm":
            continue
        tags = {k: v for k, v in (lot.get("tags") or {}).items() if v not in (None, "")}
        polygon = lot.get("polygon") or []
        if not tags or len(polygon) < 3:
            continue
        donors.append((geom.centroid(polygon), tags))
    return donors


def _tags_from_donors(polygon, donors):
    """Tags of the tallest surveyed building whose centre sits in this lot."""
    hits = []
    for centre, tags in donors:
        if geom.point_in_poly(centre, polygon):
            hits.append(tags)
    if not hits:
        return {}

    def _height(tags):
        try:
            return float(tags.get("height") or 0)
        except (TypeError, ValueError):
            return 0.0

    return dict(max(hits, key=_height))


def _overlaps(a, b):
    # conservative: a vertex of one inside the other, or bounding boxes nest tightly
    if any(geom.point_in_poly(p, b) for p in a[::max(1, len(a) // 4)]):
        return True
    if any(geom.point_in_poly(p, a) for p in b[::max(1, len(b) // 4)]):
        return True
    return False
