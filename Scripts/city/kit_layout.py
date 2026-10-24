"""Facade-kit layout: where every kit module goes, for every building of a city or region.

The baked pipeline meshes each tower in Blender and ships it as a GLB. The kit
pipeline ships a handful of small modules (SourceArt/CityGen/kit, from
blender_facade_kit.py) and this layout; import_city_ue.py --buildings kit
places the modules as instanced static meshes (HISM). The layout follows the
mesher exactly (blender_city._fitted_facade): the same facade records from the
city model, the same face_uv.fit_bays() pane fit, the same sill and head, the
same lit rooms (grammar.room_of / bay_lit) and the same blinds and curtains
(realism.dress_opening). What the kit leaves out: storefront awnings and shop
interiors, doors, air conditioners and roof units.

Modules, all 1 m long (X) and 1 m tall (Z), scaled per instance; Y is depth
into the building, in metres, and is not scaled except for boxes:
  KIT_Wall     box, X 0..1, Y 0..1 (inward), Z 0..1. Wall spans under the
               sills and above the heads, the roof slab, and collision.
  KIT_Pier     box like KIT_Wall, for the piers between panes.
  KIT_Corner   box standing CORNER_PROUD proud of the wall, for end pilasters.
  KIT_Pane     window bay: glass at PANE_GLASS_IN, back panel at PANE_BACK_IN,
               a frame and a sill. KIT_PaneCurtain is the same with no sill
               (curtain wall).
  KIT_Leaf     one plane at LEAF_IN: a blind or a curtain leaf.
  KIT_RoofCap  parapet with a coping lip, on every roof and terrace edge.

Frames: plan metres (x east, y north, z up) in, Unreal centimetres out:
X = y * 100, Y = x * 100, Z = z * 100. Each instance is [x, y, z, yaw, sx, sy, sz]:
its module's local origin (start of the run, on the facade plane, at the
bottom), Unreal yaw in degrees, and scale in metres. Local +Y always points
into the building: a run whose yaw would put +Y outward starts from its other
end instead, so no instance is mirrored (negative scale would flip culling).

Collision is one plain box per setback tier (the footprint is a quad), so the
car meets a flat wall at the facade plane instead of every sill and pier.

Pure Python. Run (writes Saved/CityGen/kit_layout_<region>.json):
  python3 -I Scripts/city/kit_layout.py --region chicago_loop
Tests: python3 -I Scripts/city/test_generate_city.py
"""
import json
import math
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
for _path in (_HERE, os.path.join(os.path.dirname(_HERE), "roads")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import face_uv  # noqa: E402
import geom  # noqa: E402
import grammar  # noqa: E402
import profiles  # noqa: E402

# Depths into the building (metres), the mesher's numbers.
SPAN_DEPTH = 0.28
PIER_DEPTH = 0.34
CORNER_PROUD = 0.05
PANE_GLASS_IN = 0.08
PANE_BACK_IN = 0.42
LEAF_IN = 0.35 * 0.5
ROOF_SLAB = 0.3
CAP_DEPTH = 0.3
DEFAULT_PARAPET = 0.6
BLIND_WIDTH = 0.92
CURTAINS = {"red": "M_CurtainRed", "green": "M_CurtainGreen", "cream": "M_CurtainCream", "blue": "M_CurtainBlue"}
# realism.CURTAINS order, for bays with no room.
CURTAIN_ORDER = ("M_CurtainRed", "M_CurtainGreen", "M_CurtainCream", "M_CurtainBlue")
MODULES = ("KIT_Wall", "KIT_Pier", "KIT_Corner", "KIT_Pane", "KIT_PaneCurtain", "KIT_Leaf", "KIT_RoofCap")
COLLISION = "KIT_Wall|collision"


def to_ue(x, y, z):
    return (y * 100.0, x * 100.0, z * 100.0)


def ue_yaw(dx, dy):
    """Unreal yaw (degrees) of a plan direction."""
    return math.degrees(math.atan2(dx, dy))


def _local_y(yaw_deg):
    """Unreal local +Y of a yaw: (-sin, cos) in Unreal X, Y."""
    r = math.radians(yaw_deg)
    return (-math.sin(r), math.cos(r))


def run(start, tangent, inward, length, z, sx, sy, sz):
    """One instance along a plan run. Local +Y is made to point along inward."""
    tx, ty = tangent
    yaw = ue_yaw(tx, ty)
    ly = _local_y(yaw)
    # inward in Unreal X, Y is (inward_y, inward_x)
    if ly[0] * inward[1] + ly[1] * inward[0] < 0:
        start = (start[0] + tx * length, start[1] + ty * length)
        yaw = ue_yaw(-tx, -ty)
    ux, uy, uz = to_ue(start[0], start[1], z)
    return [round(ux, 1), round(uy, 1), round(uz, 1), round(yaw, 3), round(sx, 4), round(sy, 4), round(sz, 4)]


def target_window_h(building, floor_h, opening):
    """blender_city._target_window_h."""
    floor_h = float(floor_h or 3.0)
    if opening == "curtain":
        return min(floor_h * 0.76, floor_h - 0.48)
    frac = float(building.get("head") or 0.74) - float(building.get("sill") or 0.32)
    return floor_h * max(0.36, min(0.58, frac))


def _materials(building):
    mats = building.get("materials") or {}
    wall = mats.get("wall") or "concrete"
    trim = mats.get("trim") or "concrete"
    metal = mats.get("metal") or "metal"
    # A glass tower's wall slot is its curtain; its solid wall parts are concrete (pack_slots.WALL_OF).
    if wall == "glass":
        wall = "concrete"
    if trim == "glass":
        trim = "concrete"
    return wall, trim, metal


class Layout(object):
    def __init__(self):
        self.groups = {}
        self.buildings = 0

    def add(self, key, item):
        self.groups.setdefault(key, []).append(item)

    def document(self, region=None):
        counts = {key: len(items) for key, items in sorted(self.groups.items())}
        return {
            "region": region,
            "frame": "Unreal cm; [x, y, z, yaw, sx, sy, sz]; module origin at run start, facade plane, bottom",
            "modules": list(MODULES),
            "buildings": self.buildings,
            "instances": sum(counts.values()),
            "counts": counts,
            "groups": {key: items for key, items in sorted(self.groups.items())},
        }


def facade_record(layout, building, facade):
    """blender_city._fitted_facade, as kit instances."""
    ax, ay = float(facade["a"][0]), float(facade["a"][1])
    bx, by = float(facade["b"][0]), float(facade["b"][1])
    length = float(facade.get("length") or 0.0) or math.hypot(bx - ax, by - ay)
    if length < 0.4:
        return
    tangent = ((bx - ax) / length, (by - ay) / length)
    nx, ny = float(facade["normal"][0]), float(facade["normal"][1])
    inward = (-nx, -ny)
    z0 = float(facade["z"]) + profiles.CURB_RISE
    floor_h = float(facade["h"])
    z1 = z0 + floor_h
    opening = facade.get("opening") or "punched"
    wall, trim, metal = _materials(building)
    field = metal if opening == "curtain" else wall
    pier = float(building.get("pier_m") or 0.3)
    lay = face_uv.fit_bays(length, floor_h, pier, face_uv.WINDOW_ASPECT,
                           target_window_h(building, floor_h, opening))
    if lay["wh"] < 0.4 or lay["ww"] < 0.45 or lay["ww"] / lay["wh"] < 0.2:
        layout.add("KIT_Wall|" + field, run((ax, ay), tangent, inward, length, z0, length, SPAN_DEPTH, floor_h))
        return
    sill = z0 + max(0.2, (floor_h - lay["wh"]) * (0.28 if opening == "curtain" else 0.55))
    head = sill + lay["wh"]
    if head > z1 - 0.12:
        head = z1 - 0.12
        sill = head - lay["wh"]
    layout.add("KIT_Wall|" + field, run((ax, ay), tangent, inward, length, z0, length, SPAN_DEPTH, sill - z0))
    layout.add("KIT_Wall|" + field, run((ax, ay), tangent, inward, length, head, length, SPAN_DEPTH, z1 - head))
    pane = "KIT_PaneCurtain" if opening == "curtain" else "KIT_Pane"
    cursor = 0.0
    for index in range(lay["count"]):
        pier_w = lay["end"] if index == 0 else lay["pier"]
        start = (ax + tangent[0] * cursor, ay + tangent[1] * cursor)
        if index == 0:
            layout.add("KIT_Corner|" + trim, run(start, tangent, inward, pier_w, z0, pier_w, 1.0, floor_h))
        else:
            layout.add("KIT_Pier|" + trim, run(start, tangent, inward, pier_w, z0, pier_w, PIER_DEPTH, floor_h))
        cursor += pier_w
        origin = (ax + tangent[0] * cursor, ay + tangent[1] * cursor)
        lit, leaf = dressing(building, facade, index, lay["ww"])
        layout.add("%s|%s" % (pane, "lit" if lit else "dark"),
                   run(origin, tangent, inward, lay["ww"], sill, lay["ww"], 1.0, head - sill))
        if leaf:
            mat, along, width, inset = leaf
            leaf_start = (origin[0] + tangent[0] * along, origin[1] + tangent[1] * along)
            layout.add("KIT_Leaf|" + mat, run(leaf_start, tangent, inward, width, sill + inset, width, 1.0,
                                               max(0.1, head - sill - 2 * inset)))
        cursor += lay["ww"]
    rest = length - cursor
    if rest > 0.02:
        start = (ax + tangent[0] * cursor, ay + tangent[1] * cursor)
        layout.add("KIT_Corner|" + trim, run(start, tangent, inward, rest, z0, rest, 1.0, floor_h))


def dressing(building, facade, bay, width):
    """(lit, leaf) of one pane. leaf is (material, along, width, inset) or None.

    Lit: blender_city._fitted_pane. Leaf: realism.dress_opening / _dress_room.
    """
    seed = int(building.get("seed") or 1)
    bid = building["id"]
    floor = int(facade.get("floor") or 0)
    room = grammar.room_of(building, facade, min(bay, max(0, int(facade.get("bays") or 1) - 1)))
    lit = bool(room.get("lit")) if room is not None else grammar.bay_lit(seed, bid, floor, bay)
    room = grammar.room_of(building, facade, bay)
    if room is not None:
        curtain = room.get("curtain") or "none"
        if curtain == "blind":
            return lit, ("M_BlindWarm" if room.get("blind_warm") else "M_Blind",
                         width * (1 - BLIND_WIDTH) / 2.0, width * BLIND_WIDTH, 0.05)
        name = CURTAINS.get(curtain)
        if not name:
            return lit, None
        frac = max(0.2, min(0.7, float(room.get("curtain_frac") or 0.45)))
        side = room.get("curtain_side") or "left"
        if side == "both":
            # Two leaves: the kit draws one centred pair as a single leaf at each side.
            return lit, (name, 0.0, width * frac * 0.5, 0.04)
        along = width * (1.0 - frac) if side == "right" else 0.0
        return lit, (name, along, width * frac, 0.04)
    roll = geom.rnd(seed, bid, floor, bay, "dress")
    if roll < 0.28:
        mat = "M_BlindWarm" if geom.rnd(seed, bid, floor, bay, "blind") < 0.5 else "M_Blind"
        return lit, (mat, width * (1 - BLIND_WIDTH) / 2.0, width * BLIND_WIDTH, 0.05)
    if roll < 0.62:
        name = CURTAIN_ORDER[int(geom.rnd(seed, bid, floor, bay, "curtain") * len(CURTAIN_ORDER)) % len(CURTAIN_ORDER)]
        frac = 0.34 + 0.28 * geom.rnd(seed, bid, floor, bay, "curtainw")
        along = 0.0 if geom.rnd(seed, bid, floor, bay, "curtainside") < 0.5 else width * (1.0 - frac)
        return lit, (name, along, width * frac, 0.04)
    return lit, None


def tiers(building):
    """[(polygon, z0, z1)] for each run of floors with the same footprint, bottom first."""
    out = []
    for floor in building.get("floors") or []:
        poly = [(round(float(p[0]), 3), round(float(p[1]), 3)) for p in floor.get("polygon") or []]
        z0 = float(floor.get("z") or 0.0)
        z1 = z0 + float(floor.get("h") or 0.0)
        if out and out[-1][0] == poly:
            out[-1] = (poly, out[-1][1], max(out[-1][2], z1))
        else:
            out.append((poly, z0, z1))
    return [tier for tier in out if len(tier[0]) >= 3]


def box_of(poly):
    """(corner, u, v, lu, lv): an oriented box around a quad, u along its first edge."""
    (x0, y0), (x1, y1) = poly[0], poly[1]
    length = math.hypot(x1 - x0, y1 - y0) or 1.0
    u = ((x1 - x0) / length, (y1 - y0) / length)
    v = (-u[1], u[0])
    pu = [px * u[0] + py * u[1] for px, py in poly]
    pv = [px * v[0] + py * v[1] for px, py in poly]
    cu, cv = min(pu), min(pv)
    corner = (u[0] * cu + v[0] * cv, u[1] * cu + v[1] * cv)
    return corner, u, v, max(pu) - cu, max(pv) - cv


def solids(layout, building):
    """Collision box and roof slab per tier, parapet caps on every tier top edge."""
    wall, trim, _metal = _materials(building)
    parapet = float(building.get("parapet_m") or DEFAULT_PARAPET)
    found = tiers(building)
    for index, (poly, z0, z1) in enumerate(found):
        corner, u, v, lu, lv = box_of(poly)
        top = z1 + profiles.CURB_RISE
        bottom = (z0 + profiles.CURB_RISE) if index else 0.0
        layout.add(COLLISION, run(corner, u, v, lu, bottom, lu, lv, top - bottom))
        layout.add("KIT_Wall|roof", run(corner, u, v, lu, top - ROOF_SLAB, lu, lv, ROOF_SLAB))
        centre = geom.centroid(poly)
        for a, b in zip(poly, poly[1:] + poly[:1]):
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            if length < 0.3:
                continue
            t = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
            n = (-t[1], t[0])
            mid = ((a[0] + b[0]) / 2.0 - centre[0], (a[1] + b[1]) / 2.0 - centre[1])
            inward = n if n[0] * mid[0] + n[1] * mid[1] < 0 else (-n[0], -n[1])
            layout.add("KIT_RoofCap|" + trim, run(a, t, inward, length, top, length, CAP_DEPTH, parapet))


def build_layout(city, ids=None):
    """Layout for every building with facades (or only those in ids), sorted by id."""
    layout = Layout()
    specs = [spec for spec in city.get("buildings") or []
             if spec.get("facades") and spec.get("role") != "landmark" and (ids is None or spec.get("id") in ids)]
    for building in sorted(specs, key=lambda spec: spec.get("id") or ""):
        for facade in building.get("facades") or []:
            facade_record(layout, building, facade)
        solids(layout, building)
        layout.buildings += 1
    return layout


def main(argv=None):
    import argparse
    import generate_city
    import skyline
    parser = argparse.ArgumentParser(description="Write the facade-kit layout.")
    parser.add_argument("--region", choices=sorted(generate_city.REGIONS))
    parser.add_argument("--ids", help="comma-separated building ids (a prototype block)")
    parser.add_argument("--out", help="output path (default Saved/CityGen/kit_layout_<region>.json)")
    args = parser.parse_args(argv)
    root = skyline.project_root()
    city = generate_city.build_from_disk(root, region=args.region)
    ids = set(args.ids.split(",")) if args.ids else None
    document = build_layout(city, ids).document(args.region)
    document["hash"] = city.get("hash") or ""
    out = Path(args.out) if args.out else root / "Saved" / "CityGen" / ("kit_layout_%s.json" % (args.region or "city"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, separators=(",", ":")))
    print("buildings", document["buildings"], "instances", document["instances"])
    for key, count in document["counts"].items():
        print("  %-28s %d" % (key, count))
    print("layout", out, round(out.stat().st_size / 1048576.0, 1), "MB")


if __name__ == "__main__":
    main()
