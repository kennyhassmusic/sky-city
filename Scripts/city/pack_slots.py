"""Which texture each engine material slot gets: an AI pack set or the CC0 scan.

The city GLBs share one material slot per surface (M_Brick, M_Asphalt, ...)
across every building in a chunk, so a pack is chosen per slot, not per
building. The choice follows the district types of the buildings that use the
slot, most common first, and is seeded so two runs match.

- Wall slots (M_Brick, M_Concrete, M_Plaster, M_Metal) take only a windowless
  basic facade set. The meshes already model windows, glass and rooms; a
  facade tile with painted windows would double them. When no windowless set
  fits the district, the slot keeps its CC0 scan.
- Ground slots take a basic ground set by suggested_use: M_Asphalt asphalt,
  M_Paving sidewalk, M_Grass grass. Curbs stay flat: the pack curbs are
  banded strips (top, face, gutter) that need curb-specific UVs.
- A district type is only considered when it holds at least MIN_SHARE of the
  buildings on that slot (or of the region, for a slot no building names), so
  a handful of distressed lots does not dress every concrete tower.
- A set whose albedo file is missing is skipped. A slot with no usable set
  stays CC0 (materials.json under SourceArt/CityGen/materials).

uv_scale maps the mesher's UVs (metres / the CC0 scan's uv_m) onto the pack
tile (metres / scale_m): uv_scale = uv_m / scale_m on each axis.
Pack normals are DirectX (Unreal's convention, no flip); the Poly Haven scans
are OpenGL (flip green). Roughness is the roughness map, else ORM green.

Pure Python. The editor scripts import_city_ue.py and import_block_ue.py call
plan_slots(); test_packs.py covers it.
"""
import json
from pathlib import Path

import packs

WALL_SLOTS = {"M_Brick": "brick", "M_Concrete": "concrete", "M_Plaster": "plaster", "M_Metal": "metal"}
GROUND_SLOTS = {"M_Asphalt": "asphalt", "M_Paving": "sidewalk", "M_Grass": "grass"}
MIN_SHARE = 0.25
# Slot -> materials.json id. Same scans as the block importer.
CC0 = {
    "M_Brick": "brick_wall_001",
    "M_Concrete": "concrete_wall_001",
    "M_Plaster": "grey_plaster",
    "M_Metal": "metal_plate",
    "M_Asphalt": "asphalt_02",
    "M_Paving": "PavingStones092",
    "M_Grass": "Grass004",
}
# A building's spawn "wall" names its wall slot. Glass towers mesh their
# spandrels and piers in concrete.
WALL_OF = {"brick": "M_Brick", "concrete": "M_Concrete", "plaster": "M_Plaster", "metal": "M_Metal", "glass": "M_Concrete"}
DEFAULT_UV_M = 3.0


def plan_slots(spawn, library=None, record=None, art_root=None, seed=7, region="city"):
    """slot -> {source, set_id, maps{color,rough,normal}, rough_channel, flip_green, uv_scale}.

    spawn is the spawn document (buildings with wall and district_type).
    library is packs.load_library(); record is materials.json; art_root is
    SourceArt/CityGen (for the CC0 files). Paths in maps are absolute.
    """
    library = library if library is not None else packs.load_library()
    record = record or {}
    art_root = Path(art_root) if art_root else None
    weights = _district_weights(spawn)
    out = {}
    for slot in list(WALL_SLOTS) + list(GROUND_SLOTS):
        types = weights.get(slot) or weights.get("*") or []
        chosen = _choose(slot, types, library, seed, region)
        cc0 = _cc0(slot, record, art_root)
        if chosen:
            out[slot] = _pack_entry(chosen, cc0)
        elif cc0:
            out[slot] = cc0
    return out


def _district_weights(spawn):
    per_slot = {}
    overall = {}
    for item in (spawn or {}).get("buildings") or []:
        if item.get("kind") != "building":
            continue
        kind = item.get("district_type")
        if not kind:
            continue
        key = (kind, item.get("tier"))
        slot = WALL_OF.get(item.get("wall") or "concrete", "M_Concrete")
        per_slot.setdefault(slot, {})
        per_slot[slot][key] = per_slot[slot].get(key, 0) + 1
        overall[key] = overall.get(key, 0) + 1
    ranked = {slot: _rank(counts) for slot, counts in per_slot.items()}
    ranked["*"] = _rank(overall)
    return ranked


def _rank(counts):
    total = float(sum(counts.values())) or 1.0
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
    return [key for key, count in ordered if count / total >= MIN_SHARE]


def _choose(slot, types, library, seed, region):
    for kind, tier in types:
        pool = []
        for item in packs.for_district(library, kind, tier) or packs.for_district(library, kind):
            if item.get("role") != "basic" or not _albedo(item):
                continue
            if slot in WALL_SLOTS and item["kind"] == "facade" and item.get("windowless"):
                pool.append(item)
            elif slot in GROUND_SLOTS and item["kind"] == "ground" and item.get("tile") \
                    and item.get("suggested_use") == GROUND_SLOTS[slot]:
                pool.append(item)
        if pool:
            return packs._pick(pool, (), seed, region, slot, kind, tier or "")
    return None


def _albedo(item):
    path = _resolve(item, (item.get("maps") or {}).get("albedo") or (item.get("maps") or {}).get("color"))
    return path if path and path.is_file() else None


def _resolve(item, rel):
    if not rel:
        return None
    base = Path(item.get("path") or ".").parent
    return (base / rel).resolve()


def _pack_entry(item, cc0):
    maps = item.get("maps") or {}
    out_maps = {"color": str(_albedo(item))}
    rough_channel = "R"
    rough = _resolve(item, maps.get("roughness"))
    if rough is None or not rough.is_file():
        rough = _resolve(item, maps.get("orm"))
        rough_channel = "G"
    if rough is not None and rough.is_file():
        out_maps["rough"] = str(rough)
    normal = _resolve(item, maps.get("normal"))
    if normal is not None and normal.is_file():
        out_maps["normal"] = str(normal)
    scale = item.get("scale_m") or {"width": DEFAULT_UV_M, "height": DEFAULT_UV_M}
    scale = [scale["width"], scale["height"]] if isinstance(scale, dict) else list(scale)
    uv_m = (cc0 or {}).get("uv_m") or [DEFAULT_UV_M, DEFAULT_UV_M]
    return {
        "source": "pack",
        "set_id": item["id"],
        "maps": out_maps,
        "rough_channel": rough_channel if "rough" in out_maps else None,
        "flip_green": (item.get("normal_convention") or "DirectX") != "DirectX",
        "uv_scale": [round(float(uv_m[0]) / float(scale[0]), 4), round(float(uv_m[1]) / float(scale[1]), 4)],
        "tile_m": [float(scale[0]), float(scale[1])],
    }


def _cc0(slot, record, art_root):
    ident = CC0.get(slot)
    info = (record or {}).get(ident) or {}
    maps = info.get("maps") or {}
    out = {}
    for kind in ("color", "rough", "normal"):
        rel = maps.get(kind)
        if not rel:
            continue
        path = (art_root / "materials" / rel) if art_root else Path(rel)
        if art_root is None or path.is_file():
            out[kind] = str(path)
    if "color" not in out:
        return None
    uv_m = info.get("uv_m") or [DEFAULT_UV_M, DEFAULT_UV_M]
    return {
        "source": "cc0",
        "set_id": ident,
        "maps": out,
        "rough_channel": "R" if "rough" in out else None,
        "flip_green": True,
        "uv_scale": [1.0, 1.0],
        "uv_m": [float(uv_m[0]), float(uv_m[1])],
    }


def massing_sets(spawn, library=None, seed=7, region="city"):
    """district_type -> windowed facade entry for the importer's massing boxes.

    Buildings past the GLB budget are boxes with no modelled windows, so they
    take a basic facade set that paints them (the opposite of the wall slots).
    Each entry is a pack entry (as plan_slots); its tile_m is the set's
    scale_m, so floors and bays keep their real size.
    "*" is the region's most common type that has a set, for any other type.
    """
    library = library if library is not None else packs.load_library()
    counts = {}
    for item in (spawn or {}).get("buildings") or []:
        if item.get("kind") == "building" and item.get("district_type"):
            counts[item["district_type"]] = counts.get(item["district_type"], 0) + 1
    out = {}
    for kind, _count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        pool = [item for item in packs.for_district(library, kind) or []
                if item.get("kind") == "facade" and item.get("role") == "basic"
                and not item.get("windowless") and _albedo(item)]
        if not pool:
            continue
        chosen = packs._pick(pool, (), seed, region, "massing", kind)
        out[kind] = _pack_entry(chosen, None)
        out.setdefault("*", out[kind])
    return out


def spawn_from_model(model):
    """The spawn fields plan_slots reads, from a city model (lots carry the type)."""
    lots = {lot.get("id"): lot for lot in model.get("lots") or []}
    districts = {item.get("id"): item for item in model.get("districts") or []}
    rows = []
    for spec in model.get("buildings") or []:
        if spec.get("role") in ("landmark", "context"):
            continue
        lot = lots.get(spec.get("lot_id")) or {}
        district = districts.get(spec.get("district_id") or lot.get("district_id")) or {}
        rows.append({
            "kind": "building",
            "wall": (spec.get("materials") or {}).get("wall") or "concrete",
            "district_type": lot.get("district_type") or district.get("district_type"),
            "tier": lot.get("tier") or district.get("tier"),
        })
    return {"buildings": rows}


def summary(plan):
    """One line per slot, for logs and the report."""
    return ["%s: %s %s uv %s" % (slot, entry["source"], entry["set_id"], entry["uv_scale"])
            for slot, entry in sorted(plan.items())]


def load_record(art_root):
    path = Path(art_root) / "materials" / "materials.json"
    return json.loads(path.read_text()) if path.is_file() else {}
