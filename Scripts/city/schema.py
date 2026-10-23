"""Validate a city_model document.

The JSON schema next to this file is the contract for the Map Designer and for a
future web tool. This checker is what the tests and the regenerator actually run,
so a model that gets through here is safe to hash and to mesh. Landmarks are
allowed to be a point with a name; ordinary buildings need a footprint and a height.
"""
import json
from pathlib import Path

SOURCES = ("osm", "generated", "hand")
CHARACTERS = ("downtown", "residential", "industrial", "park", "waterfront", "custom")
LAYERS = ("districts", "roads", "blocks", "lots", "buildings", "streetscape")


def schema_path():
    return Path(__file__).resolve().parent / "city_model.schema.json"


def validate(model):
    if not isinstance(model, dict):
        raise ValueError("city model is not an object")
    if int(model.get("version") or 0) != 1:
        raise ValueError("city model version must be 1")
    if "seed" not in model:
        raise ValueError("city model needs a seed")
    for key in ("districts", "roads", "blocks", "lots", "buildings", "overrides"):
        if key not in model or not isinstance(model[key], list):
            raise ValueError("city model needs a list '%s'" % key)
    ids = set()
    for district in model["districts"]:
        _element(district, ids, "district")
        if len(district.get("polygon") or []) < 3:
            raise ValueError("district %s needs a polygon" % district.get("id"))
        character = district.get("character") or "custom"
        if character not in CHARACTERS:
            raise ValueError("district %s has character %s" % (district["id"], character))
        kind = district.get("district_type")
        if kind:
            import districts as district_types
            if kind not in district_types.TYPE_NAMES:
                raise ValueError("district %s has district type %s" % (district["id"], kind))
    for road in model["roads"]:
        _element(road, ids, "road")
        if len(road.get("polyline") or []) < 2:
            raise ValueError("road %s needs a polyline" % road["id"])
    for block in model["blocks"]:
        _element(block, ids, "block")
        if len(block.get("polygon") or []) < 3:
            raise ValueError("block %s needs a polygon" % block["id"])
    for lot in model["lots"]:
        _element(lot, ids, "lot")
        if len(lot.get("polygon") or []) < 3:
            raise ValueError("lot %s needs a polygon" % lot["id"])
    for building in model["buildings"]:
        _element(building, ids, "building")
        if building.get("role") == "landmark":
            if "position" not in building and "footprint" not in building:
                raise ValueError("landmark %s needs a position" % building["id"])
            continue
        if building.get("height") is None:
            raise ValueError("building %s needs a height" % building["id"])
        if len(building.get("footprint") or []) < 3:
            raise ValueError("building %s needs a footprint" % building["id"])
    for override in model["overrides"]:
        _element(override, ids, "override")
        if "op" not in override:
            raise ValueError("override %s needs an op" % override["id"])
    return model


def _element(item, ids, kind):
    if not isinstance(item, dict) or not item.get("id"):
        raise ValueError("a %s is missing an id" % kind)
    if item["id"] in ids:
        raise ValueError("duplicate id %s" % item["id"])
    ids.add(item["id"])
    if item.get("source") not in SOURCES:
        raise ValueError("%s %s needs source osm, generated or hand" % (kind, item["id"]))
    if not isinstance(item.get("locked"), bool):
        raise ValueError("%s %s needs locked true or false" % (kind, item["id"]))


def write_schema_file():
    """The on-disk schema. Kept beside the checker so a web designer can load it."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/kennyhassmusic/sky-city/Scripts/city/city_model.schema.json",
        "title": "Sky City city model",
        "type": "object",
        "required": ["version", "seed", "districts", "roads", "blocks", "lots", "buildings", "overrides"],
        "additionalProperties": True,
        "properties": {
            "version": {"const": 1},
            "seed": {"type": "integer"},
            "bounds": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
            "districts": {"type": "array", "items": {"$ref": "#/$defs/district"}},
            "roads": {"type": "array", "items": {"$ref": "#/$defs/road"}},
            "blocks": {"type": "array", "items": {"$ref": "#/$defs/block"}},
            "lots": {"type": "array", "items": {"$ref": "#/$defs/lot"}},
            "buildings": {"type": "array", "items": {"$ref": "#/$defs/building"}},
            "overrides": {"type": "array", "items": {"$ref": "#/$defs/element"}},
            "streetscape": {"type": "object"},
        },
        "$defs": {
            "element": {
                "type": "object",
                "required": ["id", "source", "locked"],
                "properties": {
                    "id": {"type": "string"},
                    "source": {"enum": ["osm", "generated", "hand"]},
                    "locked": {"type": "boolean"},
                },
            },
            "district": {
                "allOf": [{"$ref": "#/$defs/element"}],
                "properties": {
                    "polygon": {"$ref": "#/$defs/ring"},
                    "character": {"enum": list(CHARACTERS)},
                    "style": {"type": "string"},
                    "skyline": {"type": "object"},
                    "trees": {"type": "array", "items": {"type": "string"}},
                    "district_type": {"enum": [
                        "brand_new", "historic_old", "eclectic_mix", "tech", "green_renewable",
                        "houses", "apartments_condos", "industrial_commercial", "utilities",
                    ]},
                    "height_m": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                    "buildings": {"type": "array", "items": {"type": "string"}},
                    "roofs": {"type": "array", "items": {"type": "string"}},
                    "materials": {"type": "array", "items": {"type": "string"}},
                    "furniture": {"type": "array", "items": {"type": "string"}},
                    "wear": {"type": "number"},
                    "mix": {"type": "object"},
                },
            },
            "road": {
                "allOf": [{"$ref": "#/$defs/element"}],
                "properties": {
                    "polyline": {"$ref": "#/$defs/ring"},
                    "cls": {"enum": ["highway", "major", "mid", "minor"]},
                    "lanes": {"type": "integer"},
                    "oneway": {"type": "boolean"},
                    "core": {"type": "boolean"},
                    "name": {"type": "string"},
                },
            },
            "block": {
                "allOf": [{"$ref": "#/$defs/element"}],
                "properties": {"polygon": {"$ref": "#/$defs/ring"}, "district_id": {"type": "string"}},
            },
            "lot": {
                "allOf": [{"$ref": "#/$defs/element"}],
                "properties": {"polygon": {"$ref": "#/$defs/ring"}, "block_id": {"type": "string"}},
            },
            "building": {
                "allOf": [{"$ref": "#/$defs/element"}],
                "properties": {
                    "height": {"type": "number"},
                    "style": {"type": "string"},
                    "seed": {"type": "integer"},
                    "footprint": {"$ref": "#/$defs/ring"},
                    "role": {"enum": ["building", "landmark", "context"]},
                },
            },
            "ring": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
        },
    }
    path = schema_path()
    path.write_text(json.dumps(schema, indent=2) + "\n")
    return path
