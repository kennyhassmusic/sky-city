"""CGA-style building grammar.

Lot, then mass, then facade, then roof. Rules live in grammar.yaml. OSM tags, when a
lot has them, win over the district skyline for height and roof, which is how a real
outline keeps its surveyed height inside a generated district.

The mass is a stack of floor polygons so a setback is a smaller plate, not a texture.
Window recess, pier width and sill line are on the spec because the mesher should not
invent a second set of proportions.
"""
import math

import geom
import yaml_lite
from skyline import project_root

SHAPES = ("flat", "gabled", "hipped", "pyramidal", "dome", "mansard", "setback", "parapet")
_STYLES = None


def load_styles(path=None):
    global _STYLES
    if path is None and _STYLES is not None:
        return _STYLES
    src = path or (project_root() / "Scripts" / "city" / "grammar.yaml")
    data = yaml_lite.loads(Path_read(src))
    styles = data["styles"]
    if path is None:
        _STYLES = styles
    return styles


def Path_read(src):
    from pathlib import Path
    return Path(src).read_text()


def evaluate(lot, style_name, sky, seed, styles=None):
    """One building spec. `sky` is skyline.for_district output. Deterministic in seed + lot id."""
    styles = styles or load_styles()
    if style_name not in styles:
        raise KeyError("unknown style %s" % style_name)
    style = styles[style_name]
    tags = dict(lot.get("tags") or {})
    target = target_height(lot, sky, seed, style, tags)
    footprint = _coverage_footprint(lot.get("polygon") or [], float(sky.get("coverage") or 1), lot.get("hero"))
    floors, z_top, roof_h = stack_floors(footprint, target, style, tags, sky, lot.get("hero"))
    roof = roof_for(floors[-1]["polygon"] if floors else footprint, z_top, roof_h, style, tags, seed, lot["id"],
                    sky.get("roofs") if sky.get("roofs") else None)
    fronts = _fronts(lot)
    facades = facade_plan(floors, fronts, style, seed, lot["id"])
    built = round(z_top + roof["h"], 2)
    spec = {
        "id": lot.get("building_id") or ("b_" + lot["id"]),
        "lot_id": lot["id"],
        "district_id": lot.get("district_id"),
        "block_id": lot.get("block_id"),
        "style": style_name,
        "seed": int(seed),
        "source": "generated",
        "locked": False,
        "role": lot.get("role") or "building",
        "height": built,
        "target_height": target,
        "front_normals": fronts,
        "opening": style["opening"],
        "bay_m": style["bay_m"],
        "pier_m": style["pier_m"],
        "recess_m": style["recess_m"],
        "sill": style["sill"],
        "head": style["head"],
        "tint": list(style.get("tint") or [1, 1, 1]),
        "parapet_m": style.get("parapet_m") or 0.4,
        "materials": _materials(style, sky),
        "footprint": [list(p) for p in (floors[0]["polygon"] if floors else footprint)],
        "floors": floors,
        "roof": roof,
        "facades": facades,
        "balconies": balconies(facades, style),
        "lod": {"lod0": "modules", "lod1": "floor_bands", "lod2": "shell", "far": "box", "nanite": True},
    }
    # Wear is recorded only for a typed district, so untyped specs stay byte-identical.
    if sky.get("district_type") and "wear" in sky:
        spec["wear"] = round(float(sky["wear"]), 3)
    return spec


def _materials(style, sky):
    slots = {
        "wall": style["wall"], "trim": style["trim"],
        "metal": style.get("metal") or "metal", "glass": "glass",
    }
    palette = list(sky.get("materials") or [])
    if palette and sky.get("district_type"):
        slots["palette"] = palette
        slots["wall"] = palette[0]
    return slots


def target_height(lot, sky, seed, style, tags=None):
    tags = tags if tags is not None else dict(lot.get("tags") or {})
    if tags.get("height") not in (None, ""):
        h = float(tags["height"])
    elif tags.get("building:levels") not in (None, ""):
        h = float(tags["building:levels"]) * float(style["floor_h"])
        if tags.get("roof:levels") not in (None, ""):
            h += float(tags["roof:levels"]) * float(style["floor_h"]) * 0.5
        if tags.get("min_height") not in (None, ""):
            h = max(h, float(tags["min_height"]))
    else:
        h = _field_height(lot, sky, seed)
        if lot.get("hero") and not tags.get("height"):
            ranks = list(sky.get("hero_height_rank_m") or [h])
            rank = int(lot.get("hero_rank") or 0)
            h = float(ranks[min(rank, len(ranks) - 1)])
            h = _envelope(h, lot, sky)
    if tags.get("min_height") not in (None, "") and tags.get("height") in (None, ""):
        h = max(h, float(tags["min_height"]))
    cap = style.get("max_floors")
    if cap and not lot.get("hero"):
        limit = float(style["ground_h"]) + float(style["floor_h"]) * (int(cap) - 1) + float(style["roof_h"])
        h = min(h, limit)
    return round(float(h), 2)


def _field_height(lot, sky, seed):
    base = float(sky.get("base_height_m") or 12)
    amp = float(sky.get("noise_amplitude_m") or 0)
    h = base + (geom.rnd(seed, lot["id"], "h") - 0.5) * 2.0 * amp
    centre = sky.get("centre")
    reach = float(sky.get("reach_m") or 0)
    if centre and reach > 1 and lot.get("polygon"):
        c = geom.centroid(lot["polygon"])
        d = math.hypot(c[0] - float(centre[0]), c[1] - float(centre[1]))
        k = max(0.0, 1.0 - d / reach)
        if sky.get("falloff") == "smoothstep":
            k = k * k * (3.0 - 2.0 * k)
        elif sky.get("falloff") == "peak":
            k = k * k
        edge = float(sky.get("edge_height_m") if sky.get("edge_height_m") is not None else base * 0.5)
        h = edge * (1.0 - k) + h * k
    return _envelope(h, lot, sky)


def _envelope(h, lot, sky):
    """Soft max or soft min against the 1D silhouette. 15% of the excess remains,
    so a tower still reads as the peak instead of being sliced flat."""
    sil = sky.get("silhouette") or {}
    samples = list(sil.get("samples") or [])
    if len(samples) < 1 or not lot.get("polygon"):
        return h
    origin = sil.get("origin") or [0, 0]
    axis = sil.get("axis") or [1, 0]
    length = float(sil.get("length") or 1) or 1.0
    c = geom.centroid(lot["polygon"])
    t = ((c[0] - float(origin[0])) * float(axis[0]) + (c[1] - float(origin[1])) * float(axis[1])) / length
    t = max(0.0, min(1.0, t))
    cap = _sample(samples, t)
    mode = sil.get("mode") or "soft_max"
    if mode == "soft_min":
        if h >= cap:
            return h
        return cap + (h - cap) * 0.15
    if h <= cap:
        return h
    return cap + (h - cap) * 0.15


def _sample(samples, t):
    if len(samples) == 1:
        return float(samples[0])
    x = t * (len(samples) - 1)
    i = int(x)
    if i >= len(samples) - 1:
        return float(samples[-1])
    f = x - i
    return float(samples[i]) * (1 - f) + float(samples[i + 1]) * f


def _coverage_footprint(polygon, coverage, hero):
    polygon = [tuple(p) for p in polygon]
    if len(polygon) < 3:
        return polygon
    coverage = max(0.05, min(1.0, float(coverage or 1)))
    if hero:
        coverage = max(coverage, 0.7)
    if coverage >= 0.98:
        return polygon
    # Binary search a parallel inset whose area matches the coverage ratio.
    lot_a = abs(geom.poly_area(polygon)) or 1.0
    target = lot_a * coverage
    lo, hi = 0.0, min(geom.spans(polygon)) * 0.45
    best = polygon
    for _ in range(16):
        mid = (lo + hi) / 2.0
        trial = geom.offset_polygon(polygon, mid)
        if abs(geom.poly_area(trial)) > target:
            best = trial
            lo = mid
        else:
            hi = mid
    return best


def stack_floors(footprint, height, style, tags, sky, hero):
    ground_h = float(style["ground_h"])
    floor_h = float(style["floor_h"])
    roof_h = float(tags["roof:height"]) if tags.get("roof:height") not in (None, "") else float(style["roof_h"])
    usable = max(ground_h, float(height) - roof_h)
    n_upper = max(0, int(round((usable - ground_h) / floor_h)))
    if style.get("max_floors") and not hero:
        n_upper = min(n_upper, int(style["max_floors"]) - 1)
    total = 1 + n_upper
    floors = []
    z = 0.0
    lot_area = abs(geom.poly_area(footprint)) or 1.0
    far_cap = float(sky.get("far") or 0)
    area_sum = 0.0
    # A surveyed height or level count already won over the skyline. FAR is a
    # district envelope for generated masses, not a second clip on a measured building.
    surveyed = tags.get("height") not in (None, "") or tags.get("building:levels") not in (None, "")
    for i in range(total):
        inset = _inset_for(i, total, style)
        poly = geom.offset_polygon(footprint, inset) if inset > 0.05 else [tuple(p) for p in footprint]
        area = abs(geom.poly_area(poly))
        if area < 12.0:
            break
        if far_cap > 0 and not hero and not surveyed and (area_sum + area) / lot_area > far_cap + 0.05 and floors:
            break
        h = ground_h if i == 0 else floor_h
        use = "ground" if i == 0 else "typical"
        rec = {
            "z": round(z, 3), "h": round(h, 3), "use": use,
            "inset": round(inset, 3), "polygon": [list(geom.r3(p)) for p in poly],
        }
        floors.append(rec)
        area_sum += area
        z += h
    if not floors:
        poly = [tuple(p) for p in footprint]
        floors = [{"z": 0.0, "h": round(ground_h, 3), "use": "ground", "inset": 0.0,
                   "polygon": [list(geom.r3(p)) for p in poly]}]
        z = ground_h
    _mark_cornices(floors, style)
    return floors, round(z, 3), round(roof_h, 3)


def _inset_for(i, total, style):
    inset = 0.0
    podium = int(style.get("podium_floors") or 0)
    if podium and i >= podium:
        inset = max(inset, float(style.get("tower_inset_m") or 0))
    every = int(style.get("setback_every") or 0)
    if every:
        inset = max(inset, (i // every) * float(style.get("setback_m") or 0))
    top_n = int(style.get("top_setback_floors") or 0)
    if top_n and total > top_n + 4 and i >= total - top_n:
        inset = max(inset, float(style.get("top_setback_m") or 0))
    return inset


def _mark_cornices(floors, style):
    podium = int(style.get("podium_floors") or 0)
    if floors:
        floors[-1]["cornice"] = float(style.get("cornice_m") or 0)
    if podium and len(floors) > podium:
        floors[podium - 1]["cornice"] = float(style.get("cornice_m") or 0) * 0.65


def roof_for(footprint, z, roof_h, style, tags, seed, lot_id, roofs=None):
    # An OSM roof:shape tag still wins. A district type's roof list is next.
    # The style's own roof is the fallback, which is what untyped districts use.
    shape = tags.get("roof:shape")
    choices = [name for name in (roofs or []) if name in SHAPES]
    if not shape and choices:
        shape = choices[int(geom.rnd(seed, lot_id, "roof_shape") * len(choices)) % len(choices)]
    if not shape:
        shape = style.get("roof") or "flat"
    if shape not in SHAPES:
        shape = "flat"
    units = []
    # Units sit on a flat deck. A hip or a gable has no deck to put them on.
    kinds = list(style.get("roof_units") or []) if shape in ("flat", "parapet", "setback", "mansard") else []
    c = geom.centroid(footprint) if footprint else (0.0, 0.0)
    sx, sy = geom.spans(footprint) if footprint else (10.0, 10.0)
    for kind in kinds:
        jx = (geom.rnd(seed, lot_id, kind, "x") - 0.5) * sx * 0.45
        jy = (geom.rnd(seed, lot_id, kind, "y") - 0.5) * sy * 0.45
        units.append({"kind": kind, "x": round(c[0] + jx, 2), "y": round(c[1] + jy, 2), "z": round(z, 2)})
    return {"shape": shape, "z": round(z, 3), "h": round(roof_h, 3), "units": units,
            "colour": tags.get("roof:colour") or ""}


def _fronts(lot):
    if lot.get("front_normals"):
        return [list(n) for n in lot["front_normals"]]
    names = {"south": (0.0, -1.0), "north": (0.0, 1.0), "east": (1.0, 0.0), "west": (-1.0, 0.0)}
    fronts = lot.get("frontages") or ["south"]
    return [list(names[f]) for f in fronts if f in names] or [[0.0, -1.0]]


def facade_plan(floors, fronts, style, seed=1, lot_id="lot"):
    out = []
    bay = float(style["bay_m"])
    pier = float(style["pier_m"])
    for fi, fl in enumerate(floors):
        poly = fl["polygon"]
        n = len(poly)
        for i in range(n):
            a = tuple(poly[i])
            b = tuple(poly[(i + 1) % n])
            edge = (b[0] - a[0], b[1] - a[1])
            length = math.hypot(edge[0], edge[1]) or 1e-6
            # outward normal of a CCW edge is to the right
            nx, ny = edge[1] / length, -edge[0] / length
            role = _role((nx, ny), fronts)
            count = max(1, int(round(length / bay)))
            opening = style["opening"]
            if fl["use"] == "ground" and role == "front":
                opening = "storefront"
            elif role == "back":
                opening = "alley"
                count = max(1, count // 2)
            elif opening == "mixed" and fl.get("inset", 0) > 0.2:
                opening = "curtain"
            # piers between bays, plus one at each end, have to fit on the edge
            pier_w = pier
            opening_w = (length - (count + 1) * pier_w) / count
            if opening_w < 0.55:
                pier_w = max(0.08, pier * 0.5)
                opening_w = (length - (count + 1) * pier_w) / count
            if opening_w < 0.4:
                count = max(1, int(length / (0.4 + pier_w)))
                opening_w = (length - (count + 1) * pier_w) / max(1, count)
            kinds = []
            for bay_i in range(int(count)):
                roll = geom.rnd(int(seed), lot_id, fi, bay_i, "bay")
                if opening == "storefront":
                    kinds.append("door" if bay_i == int(count) // 2 else ("transom" if roll < 0.35 else "storefront"))
                elif opening == "curtain":
                    kinds.append("mullion" if roll < 0.45 else "curtain")
                elif opening == "alley":
                    kinds.append("blind" if roll < 0.4 else "window")
                elif roll < 0.14:
                    kinds.append("blind")
                elif roll < 0.34:
                    kinds.append("narrow")
                else:
                    kinds.append("window")
            sill_shift = round((geom.rnd(int(seed), lot_id, fi, "sill") - 0.5) * 0.1, 3)
            out.append({
                "floor": fi, "z": fl["z"], "h": fl["h"],
                "a": [round(a[0], 3), round(a[1], 3)],
                "b": [round(b[0], 3), round(b[1], 3)],
                "length": round(length, 3),
                "normal": [round(nx, 4), round(ny, 4)],
                "role": role, "bays": int(count), "opening": opening,
                "opening_w": round(max(0.3, opening_w), 3),
                "pier_w": round(pier_w, 3),
                "cornice": fl.get("cornice") or 0,
                "door": bool(fl["use"] == "ground" and role == "front"),
                "bay_kinds": kinds,
                "sill_shift": sill_shift,
            })
    return out


def _role(normal, fronts):
    dots = [normal[0] * f[0] + normal[1] * f[1] for f in fronts] or [-1]
    if max(dots) > 0.6:
        return "front"
    if fronts and normal[0] * fronts[0][0] + normal[1] * fronts[0][1] < -0.6:
        return "back"
    return "side"


def balconies(facades, style):
    if not style.get("balcony"):
        return []
    every = int(style.get("balcony_every") or 2)
    depth = float(style.get("balcony_depth_m") or 1.2)
    out = []
    for face in facades:
        if face["role"] != "front" or face["floor"] == 0 or face["floor"] % every != 0:
            continue
        ax, ay = face["a"]
        bx, by = face["b"]
        out.append({
            "x": round((ax + bx) / 2.0, 2), "y": round((ay + by) / 2.0, 2),
            "z": face["z"], "w": round(min(face["length"] * 0.45, face["opening_w"] * 1.4), 2),
            "d": depth, "normal": face["normal"],
        })
    return out


def bay_lit(seed, building_id, floor, bay):
    """Whether a window is emitting. The dusk render and a future night material share this."""
    return geom.rnd(int(seed), building_id, int(floor), int(bay), "lit") < 0.42
