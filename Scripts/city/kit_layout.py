"""Facade-kit layout: where every kit module goes, for every building of a city or region.

The baked pipeline meshes each tower in Blender and ships it as a GLB. The kit
pipeline ships a handful of small modules (SourceArt/CityGen/kit, from
blender_facade_kit.py) and this layout; import_city_ue.py --buildings kit
places the modules as instanced static meshes (HISM). The layout walks the
same facade records as the mesher (blender_city._fitted_facade), with the same
face_uv.fit_bays() pane fit, lit rooms (grammar.room_of / bay_lit) and blinds
and curtains (realism.dress_opening). Each building's style sets its own kit
numbers and look (style_kit.py): bay, pier, window aspect and height, sills,
belt course, stepped crowns, corner pilasters, frame and glass colour, its
family's wall swatch with a per-building tint, a storefront on the street
faces of the ground floor, and wall and sidewalk decals at street level.
What the kit leaves out: awnings and shop interiors, doors, air conditioners,
roof units and facade grime. Brick walkups are the exception: walkup.py lays
them out as rows of 25 ft storefront lots with all of that.

Modules, all 1 m long (X) and 1 m tall (Z), scaled per instance; Y is depth
into the building (negative is proud of the wall):
  KIT_Wall        box, Y 0..1. Wall spans, the roof slab, collision.
  KIT_Pier        pier between panes (front and reveals).
  KIT_Corner      end pilaster, Y -1..1 scaled to the style's proud.
  KIT_Pane        window bay: glass at PANE_GLASS_IN, room back at PANE_BACK_IN,
                  frame and reveals. KIT_PaneCurtain: the curtain-wall bay.
  KIT_Sill        sill, Y -1..0.15 scaled to the style's projection.
  KIT_Cornice     crown or belt band with a drip, Y -1..0.1 scaled to its projection.
  KIT_Leaf        a blind or curtain leaf at LEAF_IN.
  KIT_RoofCap     parapet with coping on every roof and terrace edge.
  KIT_Panel       a storefront panel 2 cm proud of the wall.
  KIT_Decal       a wall decal 3 cm proud; KIT_DecalFloor, the same lying on the sidewalk.
  Walkup kit (walkup.py lays these out for brick_walkup buildings):
  KIT_Box         closed box, X, Y, Z 0..1: chimneys, condensers, posts, decks, doors.
  KIT_Bracket     cornice console, Y -1..0, deepest at the top.
  KIT_ArchLintel  segmental arch lintel, Y -1..0.1, arched lower edge.
  KIT_Keystone    keystone, wider at the top, Y -1..0.1.
  KIT_Awning      shed awning: high at the wall (Z 1), low and proud at Y -1, with a valance.
  KIT_Dish        roof satellite dish on a stub mast, facing -Y.

Frames: plan metres (x east, y north, z up) in, Unreal centimetres out:
X = y * 100, Y = x * 100, Z = z * 100. Each instance is [x, y, z, yaw, sx, sy, sz]
(plus [r, g, b], the wall tint, on tinted groups): its module's local origin
(start of the run, on the facade plane, at the bottom), Unreal yaw in degrees,
and scale in metres. Local +Y always points into the building: a run whose
yaw would put +Y outward starts from its other end instead, so no instance is
mirrored (negative scale would flip culling).

Group keys are "<module>|<material>": set:<wall set> (tinted), cc0:<wall>,
trim:<name>, frame:<name>, lit:<style>, dark:<style>, sf:<storefront>,
decal:<id>, M_<leaf material>, roof, collision.

Collision is one plain box per setback tier (the footprint is a quad), so the
car meets a flat wall at the facade plane instead of every sill and pier.
Shadows: one hidden box per tier (SHADOW), inset SHADOW_INSET behind the
panes, casts the building's shadow, because glass casts none.

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
import style_kit  # noqa: E402

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
MODULES = ("KIT_Wall", "KIT_Pier", "KIT_Corner", "KIT_Pane", "KIT_PaneCurtain", "KIT_Leaf", "KIT_RoofCap",
           "KIT_Sill", "KIT_Cornice", "KIT_Panel", "KIT_Decal", "KIT_DecalFloor",
           # The walkup kit (walkup.py).
           "KIT_Box", "KIT_Bracket", "KIT_ArchLintel", "KIT_Keystone", "KIT_Awning", "KIT_Dish")
TINTED = ("KIT_Wall", "KIT_Pier", "KIT_Corner")
# Street dressing: chance per slot, metres per slot.
WALL_DECAL_CHANCE, WALL_DECAL_EVERY = 0.3, 8.0
GROUND_DECAL_CHANCE, GROUND_DECAL_EVERY = 0.35, 10.0
STREET_ROLES = ("front", "side")
COLLISION = "KIT_Wall|collision"
# Shadow-only proxy: glass casts no shadow, so a tower's window bands let sun through in stripes.
# A hidden box per tier, inset behind the panes' room backs, casts the building's shadow instead.
SHADOW = "KIT_Wall|shadow"
SHADOW_INSET = 0.85


def to_ue(x, y, z):
    return (y * 100.0, x * 100.0, z * 100.0)


def ue_yaw(dx, dy):
    """Unreal yaw (degrees) of a plan direction."""
    return math.degrees(math.atan2(dx, dy))


def _local_y(yaw_deg):
    """Unreal local +Y of a yaw: (-sin, cos) in Unreal X, Y."""
    r = math.radians(yaw_deg)
    return (-math.sin(r), math.cos(r))


def run(start, tangent, inward, length, z, sx, sy, sz, tint=None):
    """One instance along a plan run. Local +Y is made to point along inward."""
    tx, ty = tangent
    yaw = ue_yaw(tx, ty)
    ly = _local_y(yaw)
    # inward in Unreal X, Y is (inward_y, inward_x)
    if ly[0] * inward[1] + ly[1] * inward[0] < 0:
        start = (start[0] + tx * length, start[1] + ty * length)
        yaw = ue_yaw(-tx, -ty)
    ux, uy, uz = to_ue(start[0], start[1], z)
    item = [round(ux, 1), round(uy, 1), round(uz, 1), round(yaw, 3), round(sx, 4), round(sy, 4), round(sz, 4)]
    if tint is not None:
        item.extend(round(float(c), 3) for c in tint)
    return item


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
            "looks": {bid: {"style": look["style"], "family": look["family"], "wall": look["wall"], "tint": look["tint"]}
                      for bid, look in sorted(getattr(self, "looks", {}).items())},
            "lots": [{"id": lot["id"], "floors": lot["floors"], "top": round(lot["top"], 2), "tone": lot["tone"],
                      "cornice": lot["cornice"]["kind"], "storefront": lot["storefront"]["condition"],
                      "vacant": lot["vacant"]} for lot in getattr(self, "lots", [])],
        }


class Look(object):
    """One building's kit look: wall group, tint, style numbers and its street dressing."""

    def __init__(self, building, look=None, jitter=True):
        look = look or {}
        self.building = building
        self.style = style_kit.style_of(building)
        self.p = style_kit.params(building, jitter=jitter)
        wall, trim, _metal = _materials(building)
        self.wall = ("set:" + look["wall"]) if look.get("wall") else ("cc0:" + wall)
        self.tint = style_kit.TINTS[int(look.get("tint") or 0) % len(style_kit.TINTS)] if look.get("wall") else None
        self.trim = "trim:" + self.p["trim"]
        self.frame = "frame:" + self.p["frame"]
        self.storefront = look.get("storefront")
        self.storefront_size = look.get("storefront_size") or [4.5, 4.5]
        self.wall_decals = look.get("wall_decals") or []
        self.ground_decals = look.get("ground_decals") or []

    def wall_key(self, module):
        return module + "|" + self.wall

    def pier_key(self, module):
        # A curtain wall's piers are its mullions: the frame metal, not the spandrel.
        return module + "|" + (self.frame if self.p["curtain"] else self.wall)


def _face_seed(facade):
    a = facade.get("a") or (0, 0)
    return "%d:%.1f:%.1f" % (int(facade.get("floor") or 0), float(a[0]), float(a[1]))


def facade_record(layout, building, facade, look=None):
    """One facade record (an edge of one floor) as kit instances."""
    look = look or Look(building, jitter=False)
    p = look.p
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
    floor = int(facade.get("floor") or 0)
    opening = facade.get("opening") or "punched"
    curtain = p["curtain"] or opening == "curtain"
    tint = look.tint
    field = look.wall_key("KIT_Wall")
    _street_decals(layout, building, facade, look, (ax, ay), tangent, inward, length, z0, floor_h)
    if floor == 0 and look.storefront and facade.get("role") in STREET_ROLES and floor_h >= 3.0 and length >= 3.0:
        _storefront(layout, look, (ax, ay), tangent, inward, length, z0, floor_h)
        _belt(layout, look, (ax, ay), tangent, inward, length, z1)
        return
    lay = face_uv.fit_bays(length, floor_h, p["pier_m"], p["aspect"], style_kit.window_height(p, floor_h))
    if lay["wh"] < 0.4 or lay["ww"] < 0.3 or lay["ww"] / lay["wh"] < 0.15:
        layout.add(field, run((ax, ay), tangent, inward, length, z0, length, SPAN_DEPTH, floor_h, tint))
        return
    sill = z0 + max(0.2, (floor_h - lay["wh"]) * (0.28 if curtain else 0.55))
    head = sill + lay["wh"]
    if head > z1 - 0.12:
        head = z1 - 0.12
        sill = head - lay["wh"]
    layout.add(field, run((ax, ay), tangent, inward, length, z0, length, SPAN_DEPTH, sill - z0, tint))
    layout.add(field, run((ax, ay), tangent, inward, length, head, length, SPAN_DEPTH, z1 - head, tint))
    pane = "KIT_PaneCurtain" if curtain else "KIT_Pane"
    proud = max(0.02, p["corner_proud"])
    cursor = 0.0
    for index in range(lay["count"]):
        pier_w = lay["end"] if index == 0 else lay["pier"]
        start = (ax + tangent[0] * cursor, ay + tangent[1] * cursor)
        if index == 0:
            layout.add(look.pier_key("KIT_Corner"), run(start, tangent, inward, pier_w, z0, pier_w, proud, floor_h, tint))
        else:
            layout.add(look.pier_key("KIT_Pier"), run(start, tangent, inward, pier_w, z0, pier_w, PIER_DEPTH, floor_h, tint))
        cursor += pier_w
        origin = (ax + tangent[0] * cursor, ay + tangent[1] * cursor)
        lit, leaf = dressing(building, facade, index, lay["ww"])
        layout.add("%s|%s:%s" % (pane, "lit" if lit else "dark", look.style),
                   run(origin, tangent, inward, lay["ww"], sill, lay["ww"], 1.0, head - sill))
        if p["sill"] and not curtain:
            sill_h, sill_out = p["sill"]
            sill_start = (origin[0] - tangent[0] * 0.03, origin[1] - tangent[1] * 0.03)
            layout.add("KIT_Sill|" + look.trim, run(sill_start, tangent, inward, lay["ww"] + 0.06, sill - sill_h,
                                                    lay["ww"] + 0.06, sill_out, sill_h))
        if leaf:
            mat, along, width, inset = leaf
            leaf_start = (origin[0] + tangent[0] * along, origin[1] + tangent[1] * along)
            layout.add("KIT_Leaf|" + mat, run(leaf_start, tangent, inward, width, sill + inset, width, 1.0,
                                               max(0.1, head - sill - 2 * inset)))
        cursor += lay["ww"]
    rest = length - cursor
    if rest > 0.02:
        start = (ax + tangent[0] * cursor, ay + tangent[1] * cursor)
        layout.add(look.pier_key("KIT_Corner"), run(start, tangent, inward, rest, z0, rest, proud, floor_h, tint))
    if floor == 0:
        _belt(layout, look, (ax, ay), tangent, inward, length, z1)


def _storefront(layout, look, a, tangent, inward, length, z0, floor_h):
    """Ground floor on a street face: a pilaster at each end, the family's storefront between, wall above."""
    p = look.p
    end = min(0.45, length * 0.1)
    proud = max(0.02, p["corner_proud"])
    panel_h = min(floor_h - 0.25, float(look.storefront_size[1]))
    layout.add(look.pier_key("KIT_Corner"), run(a, tangent, inward, end, z0, end, proud, floor_h, look.tint))
    far = (a[0] + tangent[0] * (length - end), a[1] + tangent[1] * (length - end))
    layout.add(look.pier_key("KIT_Corner"), run(far, tangent, inward, end, z0, end, proud, floor_h, look.tint))
    start = (a[0] + tangent[0] * end, a[1] + tangent[1] * end)
    width = length - 2 * end
    layout.add("KIT_Panel|sf:" + look.storefront, run(start, tangent, inward, width, z0, width, 1.0, panel_h))
    if floor_h - panel_h > 0.05:
        layout.add(look.wall_key("KIT_Wall"), run(start, tangent, inward, width, z0 + panel_h, width, SPAN_DEPTH,
                                                   floor_h - panel_h, look.tint))


def _belt(layout, look, a, tangent, inward, length, z):
    """A belt course along the top of the ground floor, for styles that have one."""
    if look.p.get("belt"):
        height, out = look.p["belt"]
        layout.add("KIT_Cornice|" + look.trim, run(a, tangent, inward, length, z - height, length, out, height))


def _street_decals(layout, building, facade, look, a, tangent, inward, length, z0, floor_h):
    """Stains, cracks and posters on the first two floors; litter, manholes and markings on the sidewalk."""
    seed, bid = int(building.get("seed") or 1), building["id"]
    floor = int(facade.get("floor") or 0)
    key = _face_seed(facade)
    if floor <= 1 and look.wall_decals:
        for slot in range(int(length // WALL_DECAL_EVERY) + 1):
            if geom.rnd(seed, bid, key, slot, "wdecal") >= WALL_DECAL_CHANCE:
                continue
            decal = look.wall_decals[int(geom.rnd(seed, bid, key, slot, "wdecal_kind") * len(look.wall_decals))
                                     % len(look.wall_decals)]
            w = min(float(decal["size"][0]), length * 0.8, 3.0)
            h = min(float(decal["size"][1]), floor_h * 0.8, 3.0)
            along = geom.rnd(seed, bid, key, slot, "wdecal_x") * max(0.0, length - w)
            z = z0 + 0.1 + geom.rnd(seed, bid, key, slot, "wdecal_z") * max(0.0, floor_h - h - 0.2)
            start = (a[0] + tangent[0] * along, a[1] + tangent[1] * along)
            layout.add("KIT_Decal|decal:" + decal["id"], run(start, tangent, inward, w, z, w, 1.0, h))
    if floor == 0 and facade.get("role") == "front" and look.ground_decals:
        outward = (-inward[0], -inward[1])
        for slot in range(int(length // GROUND_DECAL_EVERY) + 1):
            if geom.rnd(seed, bid, key, slot, "gdecal") >= GROUND_DECAL_CHANCE:
                continue
            decal = look.ground_decals[int(geom.rnd(seed, bid, key, slot, "gdecal_kind") * len(look.ground_decals))
                                       % len(look.ground_decals)]
            w = min(float(decal["size"][0]), length * 0.8, 3.0)
            d = min(float(decal["size"][1]), 2.0)
            along = geom.rnd(seed, bid, key, slot, "gdecal_x") * max(0.0, length - w)
            off = 0.6 + 1.4 * geom.rnd(seed, bid, key, slot, "gdecal_o")
            start = (a[0] + tangent[0] * along + outward[0] * (off + d), a[1] + tangent[1] * along + outward[1] * (off + d))
            layout.add("KIT_DecalFloor|decal:" + decal["id"],
                       run(start, tangent, inward, w, profiles.CURB_RISE + 0.008, w, d, 1.0))


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


def solids(layout, building, look=None):
    """Collision box and roof slab per tier; crown bands and a parapet on every tier top edge."""
    look = look or Look(building, jitter=False)
    parapet = float(building.get("parapet_m") or DEFAULT_PARAPET)
    found = tiers(building)
    for index, (poly, z0, z1) in enumerate(found):
        corner, u, v, lu, lv = box_of(poly)
        top = z1 + profiles.CURB_RISE
        bottom = (z0 + profiles.CURB_RISE) if index else 0.0
        layout.add(COLLISION, run(corner, u, v, lu, bottom, lu, lv, top - bottom))
        if lu > 2 * SHADOW_INSET + 0.5 and lv > 2 * SHADOW_INSET + 0.5:
            inner = (corner[0] + (u[0] + v[0]) * SHADOW_INSET, corner[1] + (u[1] + v[1]) * SHADOW_INSET)
            layout.add(SHADOW, run(inner, u, v, lu - 2 * SHADOW_INSET, bottom, lu - 2 * SHADOW_INSET,
                                   lv - 2 * SHADOW_INSET, top - ROOF_SLAB - bottom))
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
            z = top
            # Crown bands stack up from the roof line, each a little less proud (art deco steps).
            for height, out in look.p.get("crown") or ():
                layout.add("KIT_Cornice|" + look.trim, run(a, t, inward, length, z, length, out, height))
                z += height
            layout.add("KIT_RoofCap|" + look.trim, run(a, t, inward, length, z, length, CAP_DEPTH, parapet))


def build_layout(city, ids=None, library=None, styled=True):
    """Layout for every building with facades (or only those in ids), sorted by id.

    styled: each building takes its style's look (style_kit.look_for, which
    needs the texture-pack library). Off, every building gets the plain kit
    (CC0 walls by material, no storefronts or decals, no jitter).
    """
    import walkup
    layout = Layout()
    looks = style_kit.look_for(city, library) if styled else {}
    specs = [spec for spec in city.get("buildings") or []
             if spec.get("facades") and spec.get("role") != "landmark" and (ids is None or spec.get("id") in ids)]
    # Styled brick walkups are rows of 25 ft lots with their own kit (walkup.py).
    rows = [spec for spec in specs if styled and walkup.is_walkup(spec) and walkup.frame_of(spec)]
    row_ids = {spec["id"] for spec in rows}
    for building in sorted(specs, key=lambda spec: spec.get("id") or ""):
        layout.buildings += 1
        if building["id"] in row_ids:
            continue
        look = Look(building, looks.get(building["id"]), jitter=styled)
        for facade in building.get("facades") or []:
            facade_record(layout, building, facade, look)
        solids(layout, building, look)
    layout.lots = walkup.layout_buildings(layout, rows) if rows else []
    layout.looks = {bid: looks[bid] for bid in sorted(looks) if (ids is None or bid in ids) and bid not in row_ids}
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
