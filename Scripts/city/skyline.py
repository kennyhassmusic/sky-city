"""Resolve a district's skyline parameters.

Order, low to high: skyline.yaml defaults, the character preset, the district type
(when the district has one), then the district's own skyline object. A district
with no type is resolved exactly as before, from the character alone. A hero tower
uses hero_height_rank_m and still passes through the silhouette, so a curve can
ease a spire without a hard clip. The Map Designer writes the district object; it
does not need a second code path.
"""
import copy
from pathlib import Path

import yaml_lite


def project_root():
    env = __import__("os").environ.get("SKYCITY_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "SkyCity.uproject").exists():
            return p
    raise RuntimeError("Cannot find the Sky City project folder; set SKYCITY_ROOT")


def load(path=None):
    """Prefer Config/SkyCity/skyline.yaml when a maintainer has placed it there."""
    root = project_root()
    candidates = []
    if path:
        candidates.append(Path(path))
    else:
        candidates.append(root / "Config" / "SkyCity" / "skyline.yaml")
        candidates.append(root / "Scripts" / "city" / "skyline.yaml")
    for candidate in candidates:
        if candidate.is_file():
            data = yaml_lite.loads(candidate.read_text())
            data["_path"] = str(candidate)
            return data
    raise FileNotFoundError("no skyline.yaml in Config/SkyCity or Scripts/city")


def for_district(district, sky):
    """Flat parameter dict the grammar and the hero placer both read.

    A district type supplies height, the building list, roofs, materials, wear and
    furniture. The district's own skyline still wins, so a slider moved in the Map
    Designer is not overwritten by the type. `style_pinned` forces one grammar
    style; otherwise a typed district varies across its building list.
    """
    params = copy.deepcopy(sky.get("defaults") or {})
    character = (sky.get("characters") or {}).get(district.get("character") or "", {})
    params.update(copy.deepcopy(character.get("skyline") or {}))
    type_name = district.get("district_type")
    spec = ((sky.get("district_types") or {}).get(type_name) or None) if type_name else None
    if spec:
        _apply_type(params, spec, type_name)
    for key in ("buildings", "roofs", "materials", "furniture"):
        if district.get(key):
            params[key] = list(district[key])
    if type_name and district.get("wear") is not None:
        params["wear"] = float(district["wear"])
    if type_name and district.get("height_m"):
        _apply_height(params, district["height_m"])
    params.update(copy.deepcopy(district.get("skyline") or {}))
    if district.get("style_pinned") and district.get("style"):
        params["style"] = district["style"]
    elif params.get("buildings"):
        params["style"] = params["buildings"][0]
    else:
        params["style"] = district.get("style") or character.get("style") or "prewar_masonry"
    if district.get("trees"):
        params["trees"] = list(district["trees"])
    elif spec and spec.get("vegetation"):
        params["trees"] = list(spec["vegetation"])
    else:
        params["trees"] = list(character.get("trees") or ["linden", "elm"])
    params["character"] = district.get("character") or "downtown"
    if type_name:
        params["district_type"] = type_name
        params["pack"] = district.get("pack") or (spec.get("pack") if spec else type_name)
    return params


def for_lot(district, lot, sky):
    """Parameters for one lot. A nested type on the lot replaces the district recipe.

    The district skyline still applies, and a pinned style still applies, so a
    sub-mix changes what is built without throwing away an artist override.
    """
    subtype = (lot or {}).get("district_type")
    if not subtype or subtype == (district or {}).get("district_type"):
        return for_district(district or {}, sky)
    shadow = {
        "id": (district or {}).get("id"),
        "character": (district or {}).get("character"),
        "district_type": subtype,
        "skyline": copy.deepcopy((district or {}).get("skyline") or {}),
        "style_pinned": bool((district or {}).get("style_pinned")),
    }
    if shadow["style_pinned"]:
        shadow["style"] = (district or {}).get("style")
    return for_district(shadow, sky)


def _apply_type(params, spec, type_name):
    _apply_height(params, spec.get("height_m") or [0, 0])
    params["buildings"] = list(spec.get("buildings") or [])
    params["roofs"] = list(spec.get("roofs") or [])
    params["materials"] = list(spec.get("materials") or [])
    params["furniture"] = list(spec.get("furniture") or [])
    params["vegetation"] = list(spec.get("vegetation") or [])
    params["wear"] = float(spec.get("wear") or 0)
    params["pack"] = spec.get("pack") or type_name


def _apply_height(params, height):
    low, high = float(height[0]), float(height[1])
    params["base_height_m"] = (low + high) / 2.0
    params["edge_height_m"] = low
    params["noise_amplitude_m"] = (high - low) / 4.0
