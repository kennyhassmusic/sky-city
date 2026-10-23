"""Resolve a district's skyline parameters.

Order, low to high: skyline.yaml defaults, the character preset, then the district's
own skyline object. A hero tower uses hero_height_rank_m and still passes through the
silhouette, so a curve can ease a spire without a hard clip. The Map Designer writes
the district object; it does not need a second code path.
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
    """Flat parameter dict the grammar and the hero placer both read."""
    params = copy.deepcopy(sky.get("defaults") or {})
    character = (sky.get("characters") or {}).get(district.get("character") or "", {})
    params.update(copy.deepcopy(character.get("skyline") or {}))
    params.update(copy.deepcopy(district.get("skyline") or {}))
    params["style"] = district.get("style") or character.get("style") or "prewar_masonry"
    params["trees"] = list(district.get("trees") or character.get("trees") or ["linden", "elm"])
    params["character"] = district.get("character") or "downtown"
    return params
