"""Building variety for the facade kit: each Loop style gets its own look.

A style maps to texture-pack families (SourceArt/ai_textures), its own kit
parameters (bay width, window aspect and height, pier, sill, crown, belt
course, corner pilaster, frame and glass colour, trim) and a share of street
dressing (storefronts and decals). look_for() picks, per building, a family,
a wall set from it, a storefront and decals, plus a small wall tint and a
jitter on the window proportions. Neighbours (same block or within
NEIGHBOR_M) avoid the same wall set and tint, so adjacent buildings don't repeat.

  art_deco, prewar_masonry -> historic_old
  brick_walkup             -> apartments_condos
  glass_curtain            -> tech, brand_new
  modern_mixed             -> eclectic_mix, industrial_commercial

Wall sets are the families' basic facade bodies; kit_swatches.py turns the
windowed ones into wall-only swatches (the kit models its windows). Pure
Python; kit_layout.py uses it, and test_generate_city.py covers it.
"""
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import geom  # noqa: E402
import packs  # noqa: E402

# Per style: families, then the kit's numbers (metres unless noted).
# aspect: window width / height. window_frac: window height / floor height (the cap).
# crown: bands stacked up from the roof line, each (height, projection).
STYLES = {
    "art_deco": {
        "families": ("historic_old",), "bay_m": 3.7, "pier_m": 0.62, "aspect": 0.55, "window_frac": 0.62,
        "sill": (0.10, 0.10), "crown": ((1.4, 0.45), (0.7, 0.25)), "belt": (0.45, 0.15), "corner_proud": 0.16,
        "frame": "bronze", "glass": "clear", "trim": "limestone", "curtain": False,
    },
    "prewar_masonry": {
        "families": ("historic_old",), "bay_m": 3.35, "pier_m": 0.46, "aspect": 0.70, "window_frac": 0.56,
        "sill": (0.08, 0.09), "crown": ((0.9, 0.6),), "belt": (0.3, 0.12), "corner_proud": 0.08,
        "frame": "green", "glass": "clear", "trim": "limestone", "curtain": False,
    },
    "brick_walkup": {
        "families": ("apartments_condos",), "bay_m": 3.4, "pier_m": 0.40, "aspect": 0.78, "window_frac": 0.50,
        "sill": (0.06, 0.06), "crown": ((0.5, 0.35),), "belt": None, "corner_proud": 0.04,
        "frame": "white", "glass": "clear", "trim": "painted", "curtain": False,
    },
    "glass_curtain": {
        "families": ("tech", "brand_new"), "bay_m": 3.0, "pier_m": 0.14, "aspect": 1.60, "window_frac": 0.76,
        "sill": None, "crown": ((0.35, 0.06),), "belt": None, "corner_proud": 0.0,
        "frame": "silver", "glass": "blue", "trim": "metal", "curtain": True,
    },
    "modern_mixed": {
        "families": ("eclectic_mix", "industrial_commercial"), "bay_m": 3.25, "pier_m": 0.32, "aspect": 1.25,
        "window_frac": 0.60, "sill": (0.03, 0.04), "crown": ((0.7, 0.12),), "belt": None, "corner_proud": 0.0,
        "frame": "black", "glass": "grey", "trim": "concrete", "curtain": False,
    },
}
DEFAULT_STYLE = "modern_mixed"
# Flat colours (RGB, roughness, metallic) the UE side builds for frames, trims and glass tints.
FRAMES = {"bronze": (0.30, 0.19, 0.10, 0.45, 0.8), "green": (0.06, 0.13, 0.09, 0.55, 0.0),
          "white": (0.82, 0.81, 0.77, 0.6, 0.0), "silver": (0.58, 0.60, 0.62, 0.35, 0.9),
          "black": (0.035, 0.035, 0.04, 0.5, 0.2)}
TRIMS = {"limestone": (0.70, 0.66, 0.58, 0.8, 0.0), "painted": (0.80, 0.78, 0.72, 0.7, 0.0),
         "metal": (0.48, 0.50, 0.52, 0.4, 0.8), "concrete": (0.54, 0.53, 0.50, 0.85, 0.0)}
GLASS = {"clear": ((0.02, 0.025, 0.03), 0.06, 0.5), "blue": ((0.04, 0.08, 0.11), 0.22, 0.75),
         "grey": ((0.03, 0.035, 0.035), 0.14, 0.65)}
# Wall tints: multiplied into the wall swatch per building (per-instance custom data in UE).
TINTS = ((1.0, 1.0, 1.0), (0.88, 0.88, 0.9), (1.08, 1.02, 0.94), (0.94, 0.98, 1.05), (1.14, 1.1, 1.04))
WALL_SETS_PER_FAMILY = 3
# Families whose seeded pick would land on the wrong material: brick walkups take the
# apartments packs' brick bodies, not their render, glass or boarded-up ones (checked by eye
# on the kit_swatches.py output).
WALL_OVERRIDES = {
    "apartments_condos": ("fac_apartments_distressed_v05", "fac_apartments_low_v03", "fac_apartments_low_v05",
                          "fac_apartments_mid_v03"),
}
DECALS_PER_FAMILY = 3
WALL_DECALS = {"stain", "rust_streak", "crack", "patch", "plaster_patch", "poster", "graffiti", "paint_drip",
               "moss", "paint", "dirt"}
GROUND_DECALS = {"litter", "leaves", "manhole", "paint_marking", "tire_marks", "pothole", "debris", "gravel",
                 "grate", "hatch", "drain_channel", "tactile_paving", "puddle", "weeds"}
NEIGHBOR_M = 30.0


def style_of(building):
    style = building.get("style")
    return style if style in STYLES else DEFAULT_STYLE


def params(building, jitter=True):
    """The style's kit numbers for one building, with its own small jitter."""
    p = dict(STYLES[style_of(building)])
    if jitter:
        seed, bid = int(building.get("seed") or 1), building.get("id") or ""
        p["aspect"] = p["aspect"] * (0.9 + 0.2 * geom.rnd(seed, bid, "kit", "aspect"))
        p["pier_m"] = p["pier_m"] * (0.85 + 0.35 * geom.rnd(seed, bid, "kit", "pier"))
        p["window_frac"] = max(0.3, min(0.85, p["window_frac"] + 0.08 * (geom.rnd(seed, bid, "kit", "frac") - 0.5)))
    return p


def window_height(p, floor_h):
    """The pane height the fitter aims for: the style's share of the floor, or what the bay allows."""
    by_bay = max(0.4, (p["bay_m"] - p["pier_m"]) / max(0.2, p["aspect"]))
    return max(0.3, min(p["window_frac"] * floor_h, by_bay, floor_h - 0.4))


def _family_sets(library, family, kind, feature=None):
    out = []
    # Any income tier: a style's look does not follow the lot's tier.
    for item in library.get("sets") or []:
        if family not in (item.get("districts") or []):
            continue
        if item.get("kind") != kind:
            continue
        if kind == "facade" and (item.get("role") != "basic" or item.get("suggested_use") != "body"):
            continue
        if feature is not None and (item.get("feature") or item.get("suggested_use")) not in feature:
            continue
        out.append(item)
    return sorted(out, key=lambda item: item["id"])


def _pick_n(items, count, *parts):
    """count items in a stable order chosen by the seed. "Windowless" facade sets are left out:
    in these packs they are boarded-up fronts whose masks call the boards wall."""
    usable = [item for item in items if not (item.get("kind") == "facade" and item.get("windowless"))] or items
    ranked = sorted(usable, key=lambda item: geom.rnd(7, item["id"], *parts))
    return ranked[:count]


def _walls(library, family):
    known = {item["id"] for item in _family_sets(library, family, "facade")}
    override = [set_id for set_id in WALL_OVERRIDES.get(family, ()) if set_id in known]
    if override:
        return override
    return [item["id"] for item in _pick_n(_family_sets(library, family, "facade"), WALL_SETS_PER_FAMILY, family, "wall")]


def wall_sets(library=None):
    """Every wall set the styles can use, by id (kit_swatches.py makes their swatches)."""
    library = library if library is not None else packs.load_library()
    out = []
    for family in sorted({fam for style in STYLES.values() for fam in style["families"]}):
        out.extend(_walls(library, family))
    return sorted(set(out))


def family_dressing(library, family):
    """{'walls': [ids], 'storefront': id, 'wall_decals': [...], 'ground_decals': [...]} for one family."""
    walls = _walls(library, family)
    fronts = _family_sets(library, family, "storefront")
    decals = _family_sets(library, family, "decal")
    wall_d = [item for item in decals if (item.get("feature") or "") in WALL_DECALS]
    ground_d = [item for item in decals if (item.get("feature") or "") in GROUND_DECALS]

    def as_decal(item):
        scale = item.get("scale_m") or {"width": 1.0, "height": 1.0}
        return {"id": item["id"], "feature": item.get("feature"), "size": [float(scale["width"]), float(scale["height"])]}
    front_scale = (fronts[0].get("scale_m") if fronts else None) or {"width": 4.5, "height": 4.5}
    return {
        "walls": sorted(walls),
        "storefront": fronts[0]["id"] if fronts else None,
        "storefront_size": [float(front_scale["width"]), float(front_scale["height"])],
        "wall_decals": [as_decal(item) for item in _pick_n(wall_d, DECALS_PER_FAMILY, family, "walldecal")],
        "ground_decals": [as_decal(item) for item in _pick_n(ground_d, DECALS_PER_FAMILY, family, "grounddecal")],
    }


def _centre(building):
    poly = building.get("footprint") or []
    if not poly:
        return None
    return (sum(float(p[0]) for p in poly) / len(poly), sum(float(p[1]) for p in poly) / len(poly))


def look_for(city, library=None):
    """building id -> look: {style, family, wall, tint, storefront, wall_decals, ground_decals}.

    Buildings go in id order. Each one avoids the wall sets and tints of the
    neighbours already chosen (same block, or centres within NEIGHBOR_M), then
    takes its family and wall set from the seed among what is left.
    """
    library = library if library is not None else packs.load_library()
    dressing = {}
    specs = sorted((spec for spec in city.get("buildings") or [] if spec.get("facades") and spec.get("role") != "landmark"),
                   key=lambda spec: spec.get("id") or "")
    centres = {spec["id"]: _centre(spec) for spec in specs}
    looks = {}
    for spec in specs:
        style = style_of(spec)
        seed, bid = int(spec.get("seed") or 1), spec["id"]
        options = []
        for family in STYLES[style]["families"]:
            if family not in dressing:
                dressing[family] = family_dressing(library, family)
            options.extend((family, wall) for wall in dressing[family]["walls"])
        near_walls, near_tints = set(), set()
        for other_id, other in looks.items():
            same_block = spec.get("block_id") and spec.get("block_id") == other.get("block")
            a, b = centres.get(bid), centres.get(other_id)
            if same_block or (a and b and math.hypot(a[0] - b[0], a[1] - b[1]) <= NEIGHBOR_M):
                near_walls.add(other["wall"])
                near_tints.add(other["tint"])
        usable = [option for option in options if option[1] not in near_walls] or options
        if usable:
            family, wall = usable[min(len(usable) - 1, int(geom.rnd(seed, bid, "look", "wall") * len(usable)))]
        else:
            family, wall = STYLES[style]["families"][0], None
        tints = [index for index in range(len(TINTS)) if index not in near_tints] or list(range(len(TINTS)))
        tint = tints[min(len(tints) - 1, int(geom.rnd(seed, bid, "look", "tint") * len(tints)))]
        dress = dressing.get(family) or {"storefront": None, "wall_decals": [], "ground_decals": []}
        looks[bid] = {
            "style": style, "family": family, "wall": wall, "tint": tint, "block": spec.get("block_id"),
            "storefront": dress["storefront"], "storefront_size": dress.get("storefront_size") or [4.5, 4.5],
            "wall_decals": dress["wall_decals"],
            "ground_decals": dress["ground_decals"],
        }
    return looks
