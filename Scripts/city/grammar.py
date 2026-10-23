"""CGA-style building grammar.

Lot, then mass, then facade, then roof. Rules live in grammar.yaml. OSM tags, when a
lot has them, win over the district skyline for height and roof, which is how a real
outline keeps its surveyed height inside a generated district.

The mass is a stack of floor polygons so a setback is a smaller plate, not a texture.
Window recess, pier width and sill line are on the spec because the mesher should not
invent a second set of proportions.

Interiors are per room, not per window. layout_rooms stamps a room id on every
exterior opening of a volume (corner unit, wide room, open office, storefront,
lobby) so a parallax shader can share one interior, one light and one curtain.
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
    polygon = [tuple(point) for point in (lot.get("polygon") or [])]
    # A tier's yard is an inset of the lot. Untyped lots skip this, so their
    # footprint stays the coverage inset alone.
    if sky.get("tier") and len(polygon) >= 3:
        yard = max(float(sky.get("side_setback_m") or 0), float(sky.get("front_setback_m") or 0) * 0.5)
        if yard > 0.05:
            shrunk = geom.offset_polygon(polygon, yard)
            if abs(geom.poly_area(shrunk)) > 18.0:
                polygon = shrunk
    footprint = _coverage_footprint(polygon, float(sky.get("coverage") or 1), lot.get("hero"))
    floors, z_top, roof_h = stack_floors(footprint, target, style, tags, sky, lot.get("hero"))
    roof = roof_for(floors[-1]["polygon"] if floors else footprint, z_top, roof_h, style, tags, seed, lot["id"],
                    sky.get("roofs") if sky.get("roofs") else None)
    fronts = _fronts(lot)
    facades = facade_plan(floors, fronts, style, seed, lot["id"])
    rooms = layout_rooms(floors, facades, style, seed, lot["id"])
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
        "rooms": rooms,
        "balconies": balconies(facades, style),
        "lod": {"lod0": "modules", "lod1": "floor_bands", "lod2": "shell", "far": "box", "nanite": True},
    }
    # Wear is recorded only for a typed district, so untyped specs stay byte-identical.
    if sky.get("district_type") and "wear" in sky:
        spec["wear"] = round(float(sky["wear"]), 3)
    if sky.get("boarded"):
        spec["boarded"] = True
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


# Exterior openings that look into a room. A blind bay is solid wall.
_OPENINGS = ("window", "narrow", "curtain", "mullion", "storefront", "transom", "door")
_CURTAIN_COLOURS = ("red", "green", "cream", "blue")


def layout_rooms(floors, facades, style, seed, lot_id):
    """Assign room volumes and stamp bay_rooms on each facade.

    Upper curtain-wall floors are one open office. Other upper floors get corner
    units, then wide rooms along the remaining bays. The ground floor is a lobby
    plus storefronts, and a curtain-wall building keeps one office for the side
    bays the shops did not claim. Alley openings stay small rooms.
    """
    by_floor = {}
    for index, face in enumerate(facades):
        by_floor.setdefault(int(face["floor"]), []).append(index)
        face["bay_rooms"] = [None] * len(face.get("bay_kinds") or [])
    rooms = []
    opening = style.get("opening") or "punched"
    for fi, fl in enumerate(floors):
        idxs = by_floor.get(fi, [])
        if not idxs:
            continue
        if fi > 0 and opening == "curtain":
            _office_floor(rooms, fl, facades, idxs, fi, seed, lot_id)
        elif fi == 0:
            _ground_floor(rooms, fl, facades, idxs, fi, seed, lot_id, opening)
        else:
            _upper_floor(rooms, fl, facades, idxs, fi, seed, lot_id)
    return rooms


def room_of(building, facade, bay):
    """The room record shared by this opening, or None when the bay is solid."""
    ids = (facade or {}).get("bay_rooms") or []
    if bay < 0 or bay >= len(ids) or not ids[bay]:
        return None
    rid = ids[bay]
    for room in building.get("rooms") or []:
        if room.get("id") == rid:
            return room
    return None


def _office_floor(rooms, fl, facades, idxs, floor, seed, lot_id):
    windows = []
    for face_i in idxs:
        face = facades[face_i]
        for bay, kind in enumerate(face.get("bay_kinds") or []):
            if kind in _OPENINGS:
                windows.append((face_i, bay))
    if not windows:
        return
    _add_room(rooms, fl, facades, windows, floor, seed, lot_id, "office",
              [list(p) for p in fl["polygon"]], whole=True)


def _upper_floor(rooms, fl, facades, idxs, floor, seed, lot_id):
    poly = [tuple(p) for p in fl["polygon"]]
    taken = set()
    if len(idxs) == len(poly) and len(poly) >= 3:
        for i in range(len(idxs)):
            prev_i = idxs[(i - 1) % len(idxs)]
            next_i = idxs[i]
            prev, nxt = facades[prev_i], facades[next_i]
            if not _convex_corner(prev, nxt):
                continue
            prev_bays = [b for b in _end_bays(prev, False) if (prev_i, b) not in taken]
            next_bays = [b for b in _end_bays(nxt, True) if (next_i, b) not in taken]
            windows = [(prev_i, b) for b in prev_bays] + [(next_i, b) for b in next_bays]
            if not windows:
                continue
            span_prev = _edge_span(prev, prev_bays, False) if prev_bays else min(2.5, float(prev["length"]) * 0.35)
            span_next = _edge_span(nxt, next_bays, True) if next_bays else min(2.5, float(nxt["length"]) * 0.35)
            quad = _corner_quad(prev, nxt, span_prev, span_next, poly)
            if quad is None:
                continue
            kind = "corner" if prev_bays and next_bays else "room"
            _add_room(rooms, fl, facades, windows, floor, seed, lot_id, kind, quad)
            taken.update(windows)
    for face_i in idxs:
        face = facades[face_i]
        free = [b for b, kind in enumerate(face.get("bay_kinds") or [])
                if kind in _OPENINGS and (face_i, b) not in taken]
        for run in _runs(free):
            for chunk in _chunk_run(run):
                band = _band_quad(face, chunk[0], chunk[-1], poly)
                if band is None:
                    continue
                _add_room(rooms, fl, facades, [(face_i, b) for b in chunk], floor, seed, lot_id, "room", band)
                taken.update((face_i, b) for b in chunk)


def _ground_floor(rooms, fl, facades, idxs, floor, seed, lot_id, opening):
    poly = [tuple(p) for p in fl["polygon"]]
    taken = set()
    count = len(idxs)
    for k, face_i in enumerate(idxs):
        face = facades[face_i]
        if face.get("role") != "front":
            continue
        lobby_bays = _lobby_bays(face)
        windows = [(face_i, b) for b in lobby_bays if (face_i, b) not in taken]
        kinds = face.get("bay_kinds") or []
        opens = [i for i, kind in enumerate(kinds) if kind in _OPENINGS]
        doors = [i for i, kind in enumerate(kinds) if kind == "door"]
        anchor = doors[0] if doors else (opens[len(opens) // 2] if opens else None)
        extra = []
        if anchor is not None and opens and count >= 3:
            if anchor == opens[0]:
                prev_i = idxs[(k - 1) % count]
                ends = _end_bays(facades[prev_i], False)
                if ends and (prev_i, ends[0]) not in taken:
                    extra.append((prev_i, ends[0]))
            if anchor == opens[-1]:
                next_i = idxs[(k + 1) % count]
                ends = _end_bays(facades[next_i], True)
                if ends and (next_i, ends[0]) not in taken:
                    extra.append((next_i, ends[0]))
        windows = windows + extra
        if not windows:
            continue
        on_face = [b for fi, b in windows if fi == face_i]
        polygon = None
        if extra and on_face:
            other_i = extra[0][0]
            if other_i == idxs[(k - 1) % count]:
                polygon = _corner_quad(
                    facades[other_i], face,
                    _edge_span(facades[other_i], [extra[0][1]], False),
                    _edge_span(face, on_face, True), poly)
            else:
                polygon = _corner_quad(
                    face, facades[other_i],
                    _edge_span(face, on_face, False),
                    _edge_span(facades[other_i], [extra[0][1]], True), poly)
        if polygon is None and on_face:
            polygon = _band_quad(face, min(on_face), max(on_face), poly)
        if polygon is None:
            continue
        _add_room(rooms, fl, facades, windows, floor, seed, lot_id, "lobby", polygon)
        taken.update(windows)
    for face_i in idxs:
        face = facades[face_i]
        if face.get("role") != "front":
            continue
        free = [b for b, kind in enumerate(face.get("bay_kinds") or [])
                if kind in ("storefront", "transom", "window", "narrow", "curtain", "mullion")
                and (face_i, b) not in taken]
        for run in _runs(free):
            for chunk in _chunks(run, 3):
                band = _band_quad(face, chunk[0], chunk[-1], poly)
                if band is None:
                    continue
                _add_room(rooms, fl, facades, [(face_i, b) for b in chunk], floor, seed, lot_id, "storefront", band)
                taken.update((face_i, b) for b in chunk)
    if opening == "curtain":
        office = []
        for face_i in idxs:
            face = facades[face_i]
            if face.get("role") == "back":
                continue
            for bay, kind in enumerate(face.get("bay_kinds") or []):
                if kind in ("curtain", "mullion") and (face_i, bay) not in taken:
                    office.append((face_i, bay))
        if office:
            _add_room(rooms, fl, facades, office, floor, seed, lot_id, "office",
                      [list(p) for p in fl["polygon"]], whole=True)
            taken.update(office)
    for face_i in idxs:
        face = facades[face_i]
        for bay, kind in enumerate(face.get("bay_kinds") or []):
            if kind in _OPENINGS and (face_i, bay) not in taken:
                band = _band_quad(face, bay, bay, poly)
                if band is None:
                    continue
                _add_room(rooms, fl, facades, [(face_i, bay)], floor, seed, lot_id, "room", band)
                taken.add((face_i, bay))


def _add_room(rooms, fl, facades, windows, floor, seed, lot_id, kind, polygon, whole=False):
    if not windows or len(polygon) < 3:
        return None
    ring = geom.ensure_ccw([(float(p[0]), float(p[1])) for p in polygon])
    ring = [[round(p[0], 3), round(p[1], 3)] for p in ring]
    number = sum(1 for room in rooms if room["floor"] == floor)
    rid = "%s_f%d_r%d" % (lot_id, floor, number)
    lit, curtain, side, warm, frac = _room_dress(seed, lot_id, rid, kind)
    wins = []
    openings = []
    for face_i, bay in windows:
        facades[face_i]["bay_rooms"][bay] = rid
        wins.append({"facade": face_i, "bay": int(bay)})
        openings.append(_opening_at(facades[face_i], bay))
    rooms.append({
        "id": rid,
        "floor": int(floor),
        "kind": kind,
        "polygon": ring,
        "z": fl["z"],
        "h": fl["h"],
        "lit": bool(lit),
        "curtain": curtain,
        "curtain_side": side,
        "curtain_frac": frac,
        "blind_warm": bool(warm),
        "windows": wins,
        "openings": openings,
        "interior": "parallax",
        "see_through": bool(whole) or _two_normals(wins, facades),
    })
    return rid


def _room_dress(seed, lot_id, room_id, kind):
    """One light and one curtain for the whole room. The bay index is not in the seed."""
    seed = int(seed)
    if kind in ("storefront", "lobby"):
        bias = 0.82 if kind == "lobby" else 0.78
        lit = geom.rnd(seed, lot_id, room_id, "room_lit") < bias
        return lit, "none", "both", False, 0.0
    lit = geom.rnd(seed, lot_id, room_id, "room_lit") < 0.42
    roll = geom.rnd(seed, lot_id, room_id, "room_curtain")
    if roll < 0.28:
        curtain = "blind"
    elif roll < 0.62:
        curtain = _CURTAIN_COLOURS[int(geom.rnd(seed, lot_id, room_id, "room_colour") * 4) % 4]
    else:
        curtain = "none"
    side_r = geom.rnd(seed, lot_id, room_id, "room_side")
    if side_r < 0.34:
        side = "left"
    elif side_r < 0.68:
        side = "right"
    else:
        side = "both"
    warm = geom.rnd(seed, lot_id, room_id, "room_blind") < 0.5
    frac = round(0.34 + 0.28 * geom.rnd(seed, lot_id, room_id, "room_frac"), 3)
    return lit, curtain, side, warm, frac


def _opening_at(face, bay):
    pitch = float(face["pier_w"]) + float(face["opening_w"])
    kind = (face.get("bay_kinds") or [None])[bay]
    width = float(face["opening_w"]) * (0.58 if kind == "narrow" else 1.0)
    t = bay * pitch + float(face["pier_w"]) + width * 0.5
    ax, ay = float(face["a"][0]), float(face["a"][1])
    bx, by = float(face["b"][0]), float(face["b"][1])
    length = float(face["length"] or 1.0)
    tx, ty = (bx - ax) / length, (by - ay) / length
    return {
        "center": [round(ax + tx * t, 3), round(ay + ty * t, 3)],
        "normal": [round(float(face["normal"][0]), 4), round(float(face["normal"][1]), 4)],
        "width": round(width, 3),
    }


def _two_normals(windows, facades):
    normals = []
    for window in windows:
        normal = facades[window["facade"]]["normal"]
        if not any(abs(normal[0] * other[0] + normal[1] * other[1]) > 0.98 for other in normals):
            normals.append(normal)
    for i in range(len(normals)):
        for j in range(i + 1, len(normals)):
            dot = normals[i][0] * normals[j][0] + normals[i][1] * normals[j][1]
            if dot < 0.5:
                return True
    return False


def _end_bays(face, from_start):
    """Openings at one end of an edge. A second bay joins when the edge is wide."""
    kinds = face.get("bay_kinds") or []
    opens = [i for i, kind in enumerate(kinds) if kind in _OPENINGS]
    if not opens:
        return []
    if from_start:
        chosen = [opens[0]]
        if len(opens) >= 5 and opens[1] == opens[0] + 1:
            chosen.append(opens[1])
        return chosen
    chosen = [opens[-1]]
    if len(opens) >= 5 and opens[-2] + 1 == opens[-1]:
        chosen.append(opens[-2])
    return chosen


def _lobby_bays(face):
    kinds = face.get("bay_kinds") or []
    opens = [i for i, kind in enumerate(kinds) if kind in _OPENINGS]
    if not opens:
        return []
    doors = [i for i, kind in enumerate(kinds) if kind == "door"]
    anchor = doors[0] if doors else opens[len(opens) // 2]
    pos = opens.index(anchor) if anchor in opens else len(opens) // 2
    chosen = [opens[pos]]
    if pos > 0:
        chosen.append(opens[pos - 1])
    if pos + 1 < len(opens):
        chosen.append(opens[pos + 1])
    return chosen


def _convex_corner(prev, nxt):
    d0 = _dir(prev["a"], prev["b"])
    d1 = _dir(nxt["a"], nxt["b"])
    return d0[0] * d1[1] - d0[1] * d1[0] > 1e-4


def _dir(a, b):
    dx = float(b[0]) - float(a[0])
    dy = float(b[1]) - float(a[1])
    length = math.hypot(dx, dy) or 1.0
    return (dx / length, dy / length)


def _edge_span(face, bays, from_start):
    """How far a corner room runs along an edge: the claimed bays, up to about 4 m."""
    length = float(face["length"] or 0.0)
    pitch = float(face["pier_w"]) + float(face["opening_w"])
    if not bays or pitch <= 0 or length <= 0:
        return min(4.0, max(length, 0.0) * 0.45)
    if from_start:
        need = min(length, (max(bays) + 1) * pitch)
    else:
        need = max(0.0, length - min(bays) * pitch)
    target = max(need, min(4.0, length * 0.45))
    return min(length * 0.98, target)


def _corner_quad(prev, nxt, span_prev, span_next, floor_poly):
    """CCW quad inside a convex corner. p0 is the footprint corner."""
    corner = (float(nxt["a"][0]), float(nxt["a"][1]))
    d_prev = _dir(prev["a"], prev["b"])
    d_next = _dir(nxt["a"], nxt["b"])
    span_prev = max(0.4, float(span_prev))
    span_next = max(0.4, float(span_next))
    for _ in range(10):
        p0 = corner
        p1 = (corner[0] + d_next[0] * span_next, corner[1] + d_next[1] * span_next)
        p2 = (p1[0] - d_prev[0] * span_prev, p1[1] - d_prev[1] * span_prev)
        p3 = (corner[0] - d_prev[0] * span_prev, corner[1] - d_prev[1] * span_prev)
        quad = [p0, p1, p2, p3]
        if all(geom.point_in_poly(p, floor_poly) for p in quad) and abs(geom.poly_area(quad)) > 0.8:
            return quad
        span_prev *= 0.72
        span_next *= 0.72
        if span_prev < 0.35 and span_next < 0.35:
            break
    return None


def _band_quad(face, first, last, floor_poly):
    """A room along one facade. The outer edge sits on the footprint."""
    length = float(face["length"] or 1.0)
    pitch = float(face["pier_w"]) + float(face["opening_w"])
    t0 = max(0.0, first * pitch)
    t1 = min(length, (last + 1) * pitch)
    if t1 - t0 < 0.35:
        t1 = min(length, t0 + 0.35)
    ax, ay = float(face["a"][0]), float(face["a"][1])
    dx, dy = _dir(face["a"], face["b"])
    ix, iy = -float(face["normal"][0]), -float(face["normal"][1])
    sx, sy = geom.spans(floor_poly) if floor_poly else (length, length)
    depth = min(4.2, 0.35 * max(1.0, min(sx, sy)))
    depth = max(1.5, depth)
    for _ in range(10):
        p0 = (ax + dx * t0, ay + dy * t0)
        p1 = (ax + dx * t1, ay + dy * t1)
        p2 = (p1[0] + ix * depth, p1[1] + iy * depth)
        p3 = (p0[0] + ix * depth, p0[1] + iy * depth)
        quad = [p0, p1, p2, p3]
        if geom.point_in_poly(p2, floor_poly) and geom.point_in_poly(p3, floor_poly) and abs(geom.poly_area(quad)) > 0.5:
            return quad
        depth *= 0.7
        if depth < 0.55:
            break
    return None


def _runs(indices):
    if not indices:
        return []
    indices = sorted(indices)
    runs = [[indices[0]]]
    for index in indices[1:]:
        if index == runs[-1][-1] + 1:
            runs[-1].append(index)
        else:
            runs.append([index])
    return runs


def _chunk_run(run):
    if len(run) >= 6:
        size = 3
    elif len(run) >= 3:
        size = 2
    else:
        size = 1
    return _chunks(run, size)


def _chunks(run, size):
    return [run[i:i + size] for i in range(0, len(run), size)]


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
