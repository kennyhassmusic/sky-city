"""Chicago storefront walk-ups for the facade kit: one OSM building becomes a row of 25 ft lots.

The generator gives every brick_walkup the same four 3.05 m floors over a
3.5 m ground floor, on one wide footprint. Real late-1800s to 1920s Chicago
mixed-use walk-ups are 20-25 ft lots, each its own building. This module
lays out brick_walkup buildings for kit_layout.py instead of its generic
facade fit, following the walk-up rule set (Design/WALKUP_RULES.md):

- Proportions: a front cut into lots of 6.1-7.6 m (an end lot can be a double
  lot), a 4.0-4.6 m storefront floor (25-40% taller than the 3.05-3.35 m
  upper floors), tall 1:2 double-hung windows with the sill 0.76-0.9 m above
  the floor, recessed 15 cm, stacked over each other, with stone sills and
  lintels that run past the jambs.
- Storefront, bottom up: bulkhead, display glass, transom, sign band and a
  thin storefront cornice; a recessed shop entry with a step, and a separate
  narrow door to the stair at one side.
- Cornice (bracketed pressed metal, corbelled brick or a stone cornice) that
  projects 0.45-0.9 m and returns 0.3-0.9 m around the side, then stops;
  a front parapet 0.6-1.2 m above the roof, sometimes with a raised name plaque.
- Sides and rear in common brick, blind except a few small rear windows;
  side parapets stepping down to the rear; party walls only drawn where a
  taller lot stands over a lower neighbour, often with a ghost sign.
- Wooden back porches with stairs on every floor; a flat membrane roof with
  3-5 pieces of clutter toward the rear (chimneys on the party walls, vents,
  hatch, skylight, condensers, a dish, an old antenna). No water tanks.
- Variety per lot: floors (1-4, sometimes a vacant lot), heights, parapet,
  brick tone, cornice, lintel, window type, oriel bay (about 40%), storefront
  condition, paint, sign, awning and gate. No two lots within four lots of
  each other share brick, cornice, floor count and storefront; neighbours'
  rooflines differ by at least 30 cm.
- Wear: streaks under sills, soot under the cornice, patched brick.

Every number is in RULES. Frames as in kit_layout.py (plan metres in,
Unreal centimetres out, instances [x, y, z, yaw, sx, sy, sz] (+ tint)).
Within a building, positions are (s, d, z): s along the front from its
first corner, d into the building from the front wall plane, z up from the
sidewalk.

Pure Python. kit_layout.build_layout() calls layout_buildings(); the tests
are in test_walkup.py:
  python3 -I Scripts/city/test_walkup.py
"""
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _path in (_HERE, os.path.join(os.path.dirname(_HERE), "roads")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import geom  # noqa: E402
import profiles  # noqa: E402

STYLE = "brick_walkup"

# The rule set, in metres (Design/WALKUP_RULES.md has the reasons).
RULES = {
    "lot_w": (6.1, 7.6),            # a 25 ft lot, facade 20-25 ft
    "double_lot_max": 15.2,         # an end lot may take two lots
    "double_lot_chance": 0.35,
    "floors": ((1, 0.10), (2, 0.30), (3, 0.40), (4, 0.20)),
    "vacant_chance": 0.06,
    "ground_h": (4.0, 4.6),
    "upper_h": (3.05, 3.35),
    "ground_ratio": (1.25, 1.4),    # ground floor over an upper floor
    "top_shorter": 0.15,            # the top floor, half the time
    "window_w": (0.82, 1.0),
    "window_aspect": (0.46, 0.54),  # width / height
    "sill_above_floor": (0.76, 0.9),
    "head_below_ceiling": (0.3, 0.46),
    "recess": 0.15,                 # glass behind the wall face (4-8 in)
    "sill": {"h": (0.08, 0.11), "proud": (0.03, 0.05), "past": (0.1, 0.15)},
    "lintel": {"h": (0.2, 0.3), "proud": (0.025, 0.045), "past": (0.1, 0.15)},
    "pilaster": (0.32, 0.45),
    "bulkhead": (0.45, 0.75),
    "display": (2.13, 2.44),        # 7-8 ft
    "transom": (0.45, 0.9),
    "sign_band": (0.6, 0.9),
    "sf_cornice": {"h": 0.2, "proud": (0.15, 0.3)},
    "entry_w": (1.05, 1.3),
    "entry_depth": (0.9, 1.5),
    "entry_step": 0.12,
    "stair_door_w": (0.9, 1.0),
    "cornice_h": (0.6, 1.2),
    "cornice_proud": (0.45, 0.9),
    "cornice_return": (0.3, 0.9),
    "parapet": (0.6, 1.2),
    "plaque_chance": 0.45,
    "plaque": {"w": (1.6, 2.6), "h": (0.3, 0.6)},
    "rear_parapet": (0.35, 0.55),
    "side_steps": (2, 4),
    "roofline_step": 0.3,           # neighbours' tops differ by at least this
    "oriel_chance": 0.4,
    "oriel_proud": (0.6, 0.9),
    "porch_depth": 1.7,
    "porch_stair": 0.95,
    "roof_items": (3, 5),
    # Clutter at real size (m): chimney (side, height), vent (side, height), hatch 3 x 3 ft
    # (side, curb), skylight (w, l), condenser (side, height), dish diameter.
    "roof_size": {"chimney": (0.6, 1.2), "vent": (0.15, 0.6), "hatch": (0.91, 0.45), "skylight": (0.9, 1.2),
                  "condenser": (1.0, 0.9), "dish": (0.9)},
    "repeat_window": 4,             # no repeated look within this many lots
    "streak_chance": 0.55,
    "streak_drop": (0.9, 1.6),
    "coping_streak_chance": 0.6,
    "soot_chance": 0.75,
    "soot_h": 1.4,
    "patch_chance": 0.45,
    "repair_w": (0.8, 1.6),
    "repair_tint": (1.3, 1.12, 1.02),  # newer, redder brick than the wall around it
    "repair_h": (0.6, 1.2),
    "ghost_chance": 0.55,
    "ac_chance": 0.1,
    "lit_chance": 0.3,
    "shop_depth": (2.2, 3.4),       # window to the shop's back wall
    "parapet_step_min": 0.3,        # each side-parapet step drops at least this
    "parapet_step_zone": 0.4,       # share of the depth the steps take, from the front
}
TONES = ("red", "brown", "buff", "cream", "clinker")
COMMON = "brk_common"
ROOF = "roof_membrane"
CORNICES = ("bracketed", "corbelled", "stone")
LINTELS = ("flat", "segmental", "keystone")
WINDOWS = ("1/1", "2/2", "vinyl")
CONDITIONS = (("original", 0.5), ("remuddled", 0.35), ("boarded", 0.15))
FRAMES = ("wu_white", "wu_green", "wu_brown", "wu_black")
STONES = ("limestone", "brownstone")
METALS = ("pm_cream", "pm_green", "pm_grey", "pm_brown")
PAINTS = ("sf_green", "sf_red", "sf_black", "sf_blue", "sf_cream", "sf_teal")
AWNINGS = ("awn_red", "awn_green", "awn_blue", "awn_black")
SIGNS = tuple("sign_%02d" % k for k in range(1, 11))
GHOSTS = tuple("ghost_%02d" % k for k in range(1, 7))
STREAKS = ("streak_01", "streak_02", "streak_03")
SOOTS = ("soot_01", "soot_02")
SHOP_INTERIORS = ("grocery", "bar", "laundry", "clothes", "empty")
SHOP_LIGHTS = (("on", 0.35), ("dim", 0.4), ("off", 0.25))
ROOF_KINDS = ("chimney", "vent", "hatch", "skylight", "condenser", "dish", "antenna")
CURTAINS = ("M_CurtainRed", "M_CurtainGreen", "M_CurtainCream", "M_CurtainBlue")
WALL = 0.28                         # wall thickness behind the face (kit_layout.SPAN_DEPTH)
PANE_GLASS_IN = 0.08                # KIT_Pane's glass at unit depth (kit_layout.PANE_GLASS_IN)
CURB = profiles.CURB_RISE


def is_walkup(building):
    return building.get("style") == STYLE and building.get("role") != "landmark"


class Rand(object):
    """Seeded draws for one lot: every call names what it draws, so adding a draw moves nothing else."""

    def __init__(self, *parts):
        self.parts = parts

    def u(self, *name):
        return geom.rnd(*(self.parts + name))

    def between(self, lo_hi, *name):
        lo, hi = lo_hi
        return lo + (hi - lo) * self.u(*name)

    def pick(self, items, *name):
        return items[min(len(items) - 1, int(self.u(*name) * len(items)))]

    def weighted(self, pairs, *name):
        roll, acc = self.u(*name), 0.0
        for value, weight in pairs:
            acc += weight
            if roll < acc:
                return value
        return pairs[-1][0]


# ---------------------------------------------------------------------------
# Plan: one building's frame and its lots.

def frame_of(building):
    """(a, t, inn, length, depth) of a walkup: its front edge, tangent, inward normal, front length, depth."""
    fronts = [f for f in building.get("facades") or [] if f.get("role") == "front" and int(f.get("floor") or 0) == 0]
    if not fronts:
        return None
    face = max(fronts, key=lambda f: float(f.get("length") or 0.0))
    a = (float(face["a"][0]), float(face["a"][1]))
    b = (float(face["b"][0]), float(face["b"][1]))
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length < 3.0:
        return None
    t = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
    inn = (-float(face["normal"][0]), -float(face["normal"][1]))
    poly = building.get("footprint") or []
    depth = max([(p[0] - a[0]) * inn[0] + (p[1] - a[1]) * inn[1] for p in poly] or [0.0])
    if depth < 4.0:
        return None
    return a, t, inn, length, depth


def split_lots(length, rand):
    """Lot widths along a front: 6.1-7.6 m each; an end lot may be a double lot; a short front is one lot."""
    lo, hi = RULES["lot_w"]
    if length <= hi * 1.6:
        return [length]
    count = max(1, int(round(length / ((lo + hi) / 2.0))))
    weights = [0.85 + 0.3 * rand.u("lotw", k) for k in range(count)]
    # A double lot at one end (corner stores and wider buildings), when the front has room.
    double = None
    if count >= 3 and rand.u("double") < RULES["double_lot_chance"]:
        double = 0 if rand.u("double_end") < 0.5 else count - 1
        weights[double] *= 2.0
    total = sum(weights)
    widths = [length * w / total for w in weights]
    for k, w in enumerate(widths):
        cap = RULES["double_lot_max"] if k == double else hi * 1.08
        if w < lo * 0.92 or w > cap:
            return [length / count] * count
    return widths


def _floors(rand):
    return rand.weighted(RULES["floors"], "floors")


def _draw_look(rand, attempt):
    """One candidate look for a lot (the parts that make its 'combination')."""
    r = lambda *name: rand.u(attempt, *name)  # noqa: E731
    pick = lambda items, *name: items[min(len(items) - 1, int(r(*name) * len(items)))]  # noqa: E731
    floors = rand.weighted(RULES["floors"], "floors", attempt)
    cond_roll, acc, cond = r("cond"), 0.0, CONDITIONS[-1][0]
    for value, weight in CONDITIONS:
        acc += weight
        if cond_roll < acc:
            cond = value
            break
    upper = RULES["upper_h"][0] + (RULES["upper_h"][1] - RULES["upper_h"][0]) * r("upper")
    ground = RULES["ground_h"][0] + (RULES["ground_h"][1] - RULES["ground_h"][0]) * r("ground")
    # The storefront floor is 25-40% taller than the floors above.
    lo, hi = RULES["ground_ratio"]
    ground = max(max(RULES["ground_h"][0], upper * lo), min(min(RULES["ground_h"][1], upper * hi), ground))
    return {
        "floors": floors,
        "tone": pick(TONES, "tone"),
        "cornice": pick(CORNICES, "cornice"),
        "condition": cond,
        "paint": pick(PAINTS, "paint"),
        "parapet": RULES["parapet"][0] + (RULES["parapet"][1] - RULES["parapet"][0]) * r("parapet"),
        "ground_h": ground,
        "upper_h": upper,
        "top_shorter": r("topshort") < 0.5,
    }


def combo(look):
    """What two nearby lots may not share: brick, cornice, floors and storefront."""
    return (look["tone"], look["cornice"], look["floors"], look["condition"], look["paint"])


def lot_height(look):
    """(roof deck, top of the front) above the sidewalk."""
    floors = look["floors"]
    upper = look["upper_h"]
    h = look["ground_h"] + upper * max(0, floors - 1)
    if floors >= 2 and look["top_shorter"]:
        h -= RULES["top_shorter"]
    return h, h + look["parapet"]


def plan_city(buildings):
    """[lot] for every walkup, in building id order; looks chosen so nearby lots differ.

    A lot is a dict (see _lot); its 'look' never repeats a combination of any
    lot within RULES['repeat_window'] lots (by distance along any street),
    and adjacent lots differ in brick tone and roofline.
    """
    lots = []
    placed = []  # (centre, half width, look, top)
    window_m = RULES["repeat_window"] * RULES["lot_w"][1]
    for building in sorted((b for b in buildings if is_walkup(b)), key=lambda b: b.get("id") or ""):
        frame = frame_of(building)
        if frame is None:
            continue
        a, t, inn, length, depth = frame
        seed, bid = int(building.get("seed") or 1), building["id"]
        widths = split_lots(length, Rand(seed, bid, "walkup"))
        s = 0.0
        for index, width in enumerate(widths):
            rand = Rand(seed, bid, "lot", index)
            mid = (a[0] + t[0] * (s + width / 2.0), a[1] + t[1] * (s + width / 2.0))
            near = [(c, hw, lk, top) for c, hw, lk, top in placed if math.hypot(c[0] - mid[0], c[1] - mid[1]) <= window_m]
            adjacent = [(lk, top) for c, hw, lk, top in near
                        if math.hypot(c[0] - mid[0], c[1] - mid[1]) <= hw + width / 2.0 + 1.5]
            look = None
            for attempt in range(40):
                cand = _draw_look(rand, attempt)
                _deck, top = lot_height(cand)
                if any(combo(lk) == combo(cand) for _c, _hw, lk, _t in near):
                    continue
                if any(lk["tone"] == cand["tone"] or abs(tp - top) < RULES["roofline_step"] for lk, tp in adjacent):
                    continue
                look = cand
                break
            if look is None:
                look = _draw_look(rand, 0)
            vacant = (len(widths) >= 3 and 0 < index < len(widths) - 1
                      and rand.u("vacant") < RULES["vacant_chance"])
            lot = _lot(building, frame, index, s, s + width, look, rand, vacant)
            lots.append(lot)
            placed.append((mid, width / 2.0, look, lot["top"] if not vacant else 0.0))
            s += width
    _neighbours(lots)
    return lots


def _lot(building, frame, index, s0, s1, look, rand, vacant):
    a, t, inn, length, depth = frame
    width = s1 - s0
    floors = look["floors"]
    deck, top = lot_height(look)
    stone = rand.pick(STONES, "stone")
    # Window type: one per lot, and a replacement floor now and then (one type per floor).
    base_window = rand.weighted((("1/1", 0.45), ("2/2", 0.3), ("vinyl", 0.25)), "window")
    windows = []
    for floor in range(1, floors):
        windows.append("vinyl" if base_window != "vinyl" and rand.u("replaced", floor) < 0.18 else base_window)
    bays = 3 if width >= 6.4 else 2
    if width > RULES["lot_w"][1] * 1.3:
        bays = max(4, int(round(width / 2.3)))
    ww = rand.between(RULES["window_w"], "ww")
    aspect = rand.between(RULES["window_aspect"], "aspect")
    sill_above = rand.between(RULES["sill_above_floor"], "sillz")
    head_gap = rand.between(RULES["head_below_ceiling"], "headgap")
    upper = look["upper_h"] - (RULES["top_shorter"] if look["top_shorter"] else 0.0)
    wh = min(ww / aspect, upper - sill_above - head_gap)
    ww = min(ww, wh * RULES["window_aspect"][1])
    oriel = None
    if floors >= 2 and width >= 5.8 and rand.u("oriel") < RULES["oriel_chance"]:
        ow = min(width * rand.between((0.5, 0.6), "oriel_w"), 4.4)
        if bays >= 4:
            centre = width / 2.0
        elif bays == 3:
            centre = width / 2.0
        else:
            centre = width * (0.32 if rand.u("oriel_side") < 0.5 else 0.68)
        oriel = {"s0": centre - ow / 2.0, "s1": centre + ow / 2.0, "proud": rand.between(RULES["oriel_proud"], "oriel_p")}
    cornice_h = rand.between(RULES["cornice_h"], "corn_h")
    cornice = {
        "kind": look["cornice"], "h": cornice_h, "proud": rand.between(RULES["cornice_proud"], "corn_p"),
        "colour": rand.pick(METALS, "corn_c"), "ret": rand.between(RULES["cornice_return"], "corn_r"),
        "brackets": rand.between((0.85, 1.25), "corn_b"),
    }
    storefront = {
        "condition": look["condition"], "paint": look["paint"],
        "bulkhead": rand.between(RULES["bulkhead"], "bulk"), "display": rand.between(RULES["display"], "disp"),
        "transom": rand.between(RULES["transom"], "trans"), "sign_h": rand.between(RULES["sign_band"], "signh"),
        "sf_proud": rand.between(RULES["sf_cornice"]["proud"], "sfp"),
        "door_side": "left" if rand.u("door_side") < 0.5 else "right",
        "door_w": rand.between(RULES["stair_door_w"], "doorw"),
        "entry_w": rand.between(RULES["entry_w"], "entryw"), "entry_d": rand.between(RULES["entry_depth"], "entryd"),
        "entry_at": rand.pick(("centre", "far"), "entry_at"),
        "sign": rand.pick(SIGNS, "sign"),
        "awning": rand.pick(AWNINGS, "awn") if look["condition"] != "boarded" and rand.u("awning") < 0.45 else None,
        "gate": rand.weighted(((None, 0.6), ("rolldown", 0.25), ("accordion", 0.15)), "gate"),
        "gate_closed": rand.u("gate_closed") < 0.4,
        "pilaster": rand.between(RULES["pilaster"], "pil"),
        "interior": rand.pick(SHOP_INTERIORS, "interior"),
        "lights": rand.weighted(SHOP_LIGHTS, "lights"),
        "interior_d": rand.between(RULES["shop_depth"], "interior_d"),
    }
    # The storefront's parts set the ground floor's height (4.0-4.6 m).
    # Too tall for the floor: shrink the transom first, then the sign band, the glass and the bulkhead.
    for part, rule in (("transom", "transom"), ("sign_h", "sign_band"), ("display", "display"), ("bulkhead", "bulkhead")):
        parts = sum(storefront[k] for k in ("bulkhead", "display", "transom", "sign_h")) + RULES["sf_cornice"]["h"]
        over = parts - (look["ground_h"] - 0.1)
        if over > 0:
            storefront[part] = max(RULES[rule][0], storefront[part] - over)
    plaque = None
    if rand.u("plaque") < RULES["plaque_chance"] and floors >= 2:
        plaque = {"w": min(width * 0.45, rand.between(RULES["plaque"]["w"], "plq_w")),
                  "h": rand.between(RULES["plaque"]["h"], "plq_h")}
    count = int(round(rand.between(RULES["roof_items"], "roof_n")))
    kinds = sorted(ROOF_KINDS, key=lambda kind: rand.u("roof_kind", kind))[:count]
    return {
        "id": "%s_lot%d" % (building["id"], index), "building": building["id"], "index": index,
        "seed": int(building.get("seed") or 1), "a": a, "t": t, "inn": inn, "depth": depth,
        "s0": s0, "s1": s1, "vacant": vacant, "look": look, "floors": floors,
        "ground_h": look["ground_h"], "upper_h": look["upper_h"], "top_shorter": look["top_shorter"],
        "deck": deck, "top": top, "parapet": look["parapet"], "plaque": plaque,
        "tone": look["tone"], "wall": "brk_" + look["tone"],
        "tint": tuple(round(0.94 + 0.1 * rand.u("tint", k), 3) for k in range(3)),
        "common_tint": tuple(round(0.92 + 0.12 * rand.u("ctint", k), 3) for k in range(3)),
        "stone": stone, "lintel": rand.pick(LINTELS, "lintel"),
        "lintel_h": rand.between(RULES["lintel"]["h"], "lin_h"),
        "sill_h": rand.between(RULES["sill"]["h"], "sill_h"), "sill_proud": rand.between(RULES["sill"]["proud"], "sill_p"),
        "past": rand.between(RULES["sill"]["past"], "past"),
        "windows": windows, "frame": "wu_vinyl" if base_window == "vinyl" else rand.pick(FRAMES, "frame"),
        "bays": bays, "ww": ww, "wh": wh, "sill_above": sill_above, "oriel": oriel,
        "cornice": cornice, "storefront": storefront,
        "steps": int(round(rand.between(RULES["side_steps"], "steps"))),
        "rear_parapet": rand.between(RULES["rear_parapet"], "rear_p"),
        "roof_items": kinds, "porch": floors >= 2 and depth >= 6.0,
        "left": None, "right": None,
    }


def _neighbours(lots):
    """Each lot's neighbour heights on its two sides (None at a building's end or a vacant lot)."""
    by_building = {}
    for lot in lots:
        by_building.setdefault(lot["building"], []).append(lot)
    for row in by_building.values():
        row.sort(key=lambda lot: lot["index"])
        for k, lot in enumerate(row):
            lot["left"] = row[k - 1] if k > 0 and not row[k - 1]["vacant"] else None
            lot["right"] = row[k + 1] if k + 1 < len(row) and not row[k + 1]["vacant"] else None
            lot["end_left"] = k == 0
            lot["end_right"] = k == len(row) - 1


def floor_z(lot, floor):
    """(bottom, height) of a floor above the sidewalk."""
    if floor == 0:
        return 0.0, lot["ground_h"]
    z = lot["ground_h"] + lot["upper_h"] * (floor - 1)
    h = lot["upper_h"]
    if floor == lot["floors"] - 1 and lot["top_shorter"]:
        h -= RULES["top_shorter"]
    return z, h


def cornice_bottom(lot):
    """Where the cornice starts: its drawn height, kept above the top-floor lintels."""
    top = lot["top"]
    if lot["floors"] >= 2:
        z_floor, _h = floor_z(lot, lot["floors"] - 1)
        clear = z_floor + lot["sill_above"] + lot["wh"] + lot["lintel_h"] * 1.5 + 0.12
    else:
        sf = lot["storefront"]
        clear = sf["bulkhead"] + sf["display"] + sf["transom"] + sf["sign_h"] + RULES["sf_cornice"]["h"] + 0.1
    return top - max(0.35, min(lot["cornice"]["h"], top - clear))


def window_columns(lot):
    """[(s0, s1)] of the upper-floor windows, relative to the lot, the same on every floor (they stack).

    With an oriel, the oriel's own windows are separate (oriel_windows)."""
    width = lot["s1"] - lot["s0"]
    ww = lot["ww"]
    oriel = lot["oriel"]
    spans = [(0.0, width)]
    if oriel:
        spans = [(0.0, oriel["s0"]), (oriel["s1"], width)]
    out = []
    pil = 0.35
    total_bays = lot["bays"]
    for lo, hi in spans:
        span = hi - lo
        if oriel:
            n = 1 if span >= ww + 0.6 else 0
            if total_bays >= 4 and span >= 2 * ww + 1.4:
                n = 2
        else:
            n = total_bays
        if n == 0:
            continue
        # Bays evenly over the span, the end piers a little wider than the ones between.
        inner_lo = lo + (pil if lo == 0.0 else 0.25)
        inner_hi = hi - (pil if hi == width else 0.25)
        bay = (inner_hi - inner_lo) / n
        for k in range(n):
            c = inner_lo + bay * (k + 0.5)
            out.append((c - ww / 2.0, c + ww / 2.0))
    return out


def oriel_windows(lot):
    """Front windows of the oriel (two), relative to the lot; the sides get one narrow window each."""
    oriel = lot["oriel"]
    if not oriel:
        return []
    ww = lot["ww"]
    w = oriel["s1"] - oriel["s0"]
    if w < 2 * ww + 0.9:
        c = (oriel["s0"] + oriel["s1"]) / 2.0
        return [(c - ww / 2.0, c + ww / 2.0)]
    gap = (w - 2 * ww) / 3.0
    return [(oriel["s0"] + gap, oriel["s0"] + gap + ww), (oriel["s1"] - gap - ww, oriel["s1"] - gap)]


# ---------------------------------------------------------------------------
# Emit: kit instances for one lot.

class Emit(object):
    """Boxes and faces in a lot's (s, d, z) frame, written as kit_layout instances."""

    def __init__(self, layout, lot):
        import kit_layout
        self.kit = kit_layout
        self.layout = layout
        self.lot = lot
        self.a, self.t, self.inn = lot["a"], lot["t"], lot["inn"]

    def p(self, s, d):
        s += self.lot["s0"]
        return (self.a[0] + self.t[0] * s + self.inn[0] * d, self.a[1] + self.t[1] * s + self.inn[1] * d)

    def put(self, key, face, s0, s1, d0, d1, z0, z1, tint=None):
        """An instance spanning s0..s1, d0..d1, z0..z1 (z above the sidewalk), its local +Y into the lot.

        face: front (seen from the street), back (from the alley), left (from -s) or right (from +s).
        Modules authored proud of their plane (Y < 0) stick out of the plane: pass the plane as d0
        (front), d1 (back), s0 (left) or s1 (right).
        """
        if s1 - s0 < 0.005 or d1 - d0 < 0.005 or z1 - z0 < 0.005:
            return
        z = z0 + CURB
        inn = self.inn
        out = (-inn[0], -inn[1])
        if face == "front":
            item = self.kit.run(self.p(s0, d0), self.t, inn, s1 - s0, z, s1 - s0, d1 - d0, z1 - z0, tint)
        elif face == "back":
            item = self.kit.run(self.p(s0, d1), self.t, out, s1 - s0, z, s1 - s0, d1 - d0, z1 - z0, tint)
        elif face == "left":
            item = self.kit.run(self.p(s0, d0), inn, self.t, d1 - d0, z, d1 - d0, s1 - s0, z1 - z0, tint)
        elif face == "right":
            item = self.kit.run(self.p(s1, d0), inn, (-self.t[0], -self.t[1]), d1 - d0, z, d1 - d0, s1 - s0, z1 - z0, tint)
        else:
            raise ValueError(face)
        self.layout.add(key, item)

    # Wall helpers -----------------------------------------------------------

    def front_wall(self, s0, s1, z0, z1, holes=(), key=None, tint=None, plane=0.0, module="KIT_Wall"):
        """Front wall s0..s1, z0..z1 at depth plane, with rectangular holes [(s0, s1, z0, z1)] in one band.

        KIT_Wall has no back face (it is inside the building); parapets seen from the roof use KIT_Box."""
        key = key or (module + "|set:" + self.lot["wall"])
        tint = tint if tint is not None else self.lot["tint"]
        holes = sorted(h for h in holes if h[1] > s0 and h[0] < s1)
        if not holes:
            self.put(key, "front", s0, s1, plane, plane + WALL, z0, z1, tint)
            return
        hz0 = min(h[2] for h in holes)
        hz1 = max(h[3] for h in holes)
        self.put(key, "front", s0, s1, plane, plane + WALL, z0, hz0, tint)
        self.put(key, "front", s0, s1, plane, plane + WALL, hz1, z1, tint)
        cursor = s0
        for h0, h1, _z0, _z1 in holes:
            self.put(key, "front", cursor, h0, plane, plane + WALL, hz0, hz1, tint)
            cursor = h1
        self.put(key, "front", cursor, s1, plane, plane + WALL, hz0, hz1, tint)

    def common(self, face, s0, s1, d0, d1, z0, z1, module="KIT_Wall"):
        self.put(module + "|set:" + COMMON, face, s0, s1, d0, d1, z0, z1, self.lot["common_tint"])

    def trim(self, name, face, s0, s1, d0, d1, z0, z1, module="KIT_Box"):
        self.put(module + "|trim:" + name, face, s0, s1, d0, d1, z0, z1)

    def decal(self, name, face, s0, s1, d0, d1, z0, z1):
        self.put("KIT_Decal|gdecal:" + name, face, s0, s1, d0, d1, z0, z1)

    def pane(self, face, s0, s1, plane, z0, z1, lit, look=None, depth=None, module="KIT_Pane"):
        """A window bay: glass RULES['recess'] behind the wall face (front: plane is the wall face)."""
        look = look or self.lot["frame"]
        sy = (depth or RULES["recess"]) / PANE_GLASS_IN
        key = "%s|%s:%s" % (module, "lit" if lit else "dark", look)
        if face == "front":
            self.put(key, "front", s0, s1, plane, plane + sy, z0, z1)
        elif face == "back":
            self.put(key, "back", s0, s1, plane - sy, plane, z0, z1)
        elif face == "left":
            self.put(key, "left", plane, plane + sy, s0, s1, z0, z1)
        elif face == "right":
            self.put(key, "right", plane - sy, plane, s0, s1, z0, z1)


def layout_lot(layout, lot):
    """Every kit instance of one lot."""
    e = Emit(layout, lot)
    width = lot["s1"] - lot["s0"]
    depth = lot["depth"]
    if lot["vacant"]:
        _vacant(e, lot, width, depth)
        return
    _collision(e, lot, width, depth)
    _storefront(e, lot, width)
    for floor in range(1, lot["floors"]):
        _upper_floor(e, lot, width, floor)
    _oriel(e, lot)
    _cornice_and_parapet(e, lot, width)
    _sides(e, lot, width, depth)
    _rear(e, lot, width, depth)
    _roof(e, lot, width, depth)
    _wear(e, lot, width)


def _collision(e, lot, width, depth):
    # One plain box per lot: the car meets a flat wall at the facade plane.
    e.put("KIT_Wall|collision", "front", 0.0, width, 0.0, depth, -CURB, lot["deck"])
    # Shadow-only box behind the panes (kit_layout.SHADOW); inset only at the row's ends, so no
    # sun leaks between lots.
    inset = e.kit.SHADOW_INSET
    s0 = inset if lot.get("end_left") else 0.0
    s1 = width - (inset if lot.get("end_right") else 0.0)
    if depth > 2 * inset + 0.5:
        e.put(e.kit.SHADOW, "front", s0, s1, inset, depth - inset, 0.0, lot["deck"] - 0.3)


def _rnd(lot, *parts):
    return geom.rnd(lot["seed"], lot["id"], *parts)


def _interior(e, lot, face, s0, s1, plane, z0, z1, *key):
    """Lit or dark, and a blind or curtain leaf behind the glass, or a window air conditioner."""
    lit = _rnd(lot, "lit", *key) < RULES["lit_chance"]
    roll = _rnd(lot, "leaf", *key)
    w = s1 - s0
    recess = RULES["recess"]
    leaf_d = plane + recess + 0.06
    if face == "front":
        if roll < 0.28:
            mat = "M_BlindWarm" if _rnd(lot, "blind", *key) < 0.5 else "M_Blind"
            drop = (z1 - z0) * (0.3 + 0.6 * _rnd(lot, "blind_drop", *key))
            e.put("KIT_Leaf|" + mat, "front", s0 + w * 0.04, s1 - w * 0.04, leaf_d - 0.175, leaf_d + 0.825, z1 - drop, z1 - 0.04)
        elif roll < 0.62:
            mat = CURTAINS[int(_rnd(lot, "curtain", *key) * len(CURTAINS)) % len(CURTAINS)]
            frac = 0.34 + 0.28 * _rnd(lot, "curtain_w", *key)
            if _rnd(lot, "curtain_side", *key) < 0.5:
                e.put("KIT_Leaf|" + mat, "front", s0, s0 + w * frac, leaf_d - 0.175, leaf_d + 0.825, z0 + 0.04, z1 - 0.04)
            else:
                e.put("KIT_Leaf|" + mat, "front", s1 - w * frac, s1, leaf_d - 0.175, leaf_d + 0.825, z0 + 0.04, z1 - 0.04)
        if _rnd(lot, "ac", *key) < RULES["ac_chance"]:
            c = (s0 + s1) / 2.0
            e.trim("condenser", "front", c - 0.32, c + 0.32, plane - 0.22, plane + recess - 0.01, z0 + 0.01, z0 + 0.42)
    return lit


def _window(e, lot, s0, s1, z0, z1, kind, *key):
    """One upper-floor window: recessed sash, stone sill, lintel, muntins by type, interior."""
    recess = RULES["recess"]
    lit = _interior(e, lot, "front", s0, s1, 0.0, z0, z1, *key)
    e.pane("front", s0, s1, 0.0, z0, z1, lit, look="wu_vinyl" if kind == "vinyl" else lot["frame"])
    frame = "vinyl" if kind == "vinyl" else (lot["frame"].replace("wu_", ""))
    glass_d = recess - 0.02
    if kind == "vinyl":
        # Replacement sash: the old arched or tall transom filled in with a panel.
        infill = (z1 - z0) * 0.22
        e.trim("vinyl", "front", s0, s1, glass_d - 0.05, glass_d, z1 - infill, z1)
        mid = z0 + (z1 - infill - z0) * 0.5
    else:
        mid = z0 + (z1 - z0) * 0.52
    e.put("KIT_Box|frame:" + frame, "front", s0, s1, glass_d - 0.04, glass_d, mid - 0.025, mid + 0.025)
    if kind == "2/2":
        c = (s0 + s1) / 2.0
        e.put("KIT_Box|frame:" + frame, "front", c - 0.015, c + 0.015, glass_d - 0.03, glass_d, z0, z1)
    # Sill and lintel run past the jambs.
    past = lot["past"]
    e.trim(lot["stone"], "front", s0 - past, s1 + past, -lot["sill_proud"], recess + 0.01, z0 - lot["sill_h"], z0 + 0.01)
    lh = lot["lintel_h"]
    lin_past = past * 0.9
    proud = 0.035
    if lot["lintel"] == "segmental":
        e.put("KIT_ArchLintel|trim:" + lot["stone"], "front", s0 - lin_past, s1 + lin_past, 0.0, proud, z1 - 0.005,
              z1 + lh * 1.5)
    else:
        e.trim(lot["stone"], "front", s0 - lin_past, s1 + lin_past, -proud, 0.02, z1 - 0.005, z1 + lh)
        if lot["lintel"] == "keystone":
            c = (s0 + s1) / 2.0
            e.put("KIT_Keystone|trim:" + lot["stone"], "front", c - 0.16, c + 0.16, -proud, -proud + 0.03,
                  z1 - 0.04, z1 + lh + 0.08)
    return lit


def _upper_floor(e, lot, width, floor):
    z0, h = floor_z(lot, floor)
    sill = z0 + lot["sill_above"]
    head = sill + lot["wh"]
    kind = lot["windows"][floor - 1]
    cols = window_columns(lot)
    holes = [(c0, c1, sill, head) for c0, c1 in cols]
    oriel = lot["oriel"]
    if oriel:
        # The oriel stands proud of the wall; behind it the wall is solid.
        e.front_wall(0.0, oriel["s0"], z0, z0 + h, [hl for hl in holes if hl[1] <= oriel["s0"]])
        e.front_wall(oriel["s1"], width, z0, z0 + h, [hl for hl in holes if hl[0] >= oriel["s1"]])
    else:
        e.front_wall(0.0, width, z0, z0 + h, holes)
    for k, (c0, c1) in enumerate(cols):
        _window(e, lot, c0, c1, sill, head, kind, floor, k)


def _oriel(e, lot):
    """A projecting bay up the upper floors: front windows, narrow side windows, brackets under, a cap."""
    oriel = lot["oriel"]
    if not oriel:
        return
    o0, o1, proud = oriel["s0"], oriel["s1"], oriel["proud"]
    z_bottom = lot["ground_h"]
    # The oriel tucks under the cornice.
    z_top = min(lot["deck"], cornice_bottom(lot)) - 0.05
    wall = "KIT_Wall|set:" + lot["wall"]
    tint = lot["tint"]
    fronts = oriel_windows(lot)
    side_w = proud - 0.3
    for floor in range(1, lot["floors"]):
        z0, h = floor_z(lot, floor)
        z1 = min(z0 + h, z_top)
        sill = z0 + lot["sill_above"]
        head = min(sill + lot["wh"], z1 - 0.25)
        kind = lot["windows"][floor - 1]
        e.front_wall(o0, o1, z0, z1, [(c0, c1, sill, head) for c0, c1 in fronts], plane=-proud)
        for k, (c0, c1) in enumerate(fronts):
            # The oriel's own windows sit in its face (the plane is the oriel front).
            lit = _rnd(lot, "lit", "oriel", floor, k) < RULES["lit_chance"]
            e.pane("front", c0, c1, -proud, sill, head, lit, look="wu_vinyl" if kind == "vinyl" else lot["frame"])
            e.trim(lot["stone"], "front", c0 - 0.06, c1 + 0.06, -proud - lot["sill_proud"], -proud + 0.16,
                   sill - lot["sill_h"], sill + 0.01)
        # Side faces, each with one narrow window when the bay is deep enough.
        for face, s_plane in (("left", o0), ("right", o1)):
            s_a, s_b = (o0, o0 + WALL) if face == "left" else (o1 - WALL, o1)
            if side_w >= 0.3:
                e.put(wall, face, s_a, s_b, -proud, -proud + 0.12, z0, z1, tint)
                e.put(wall, face, s_a, s_b, -proud + 0.12 + side_w, 0.0, z0, z1, tint)
                e.put(wall, face, s_a, s_b, -proud + 0.12, -proud + 0.12 + side_w, z0, sill, tint)
                e.put(wall, face, s_a, s_b, -proud + 0.12, -proud + 0.12 + side_w, head, z1, tint)
                lit = _rnd(lot, "lit", "oriel_side", face, floor) < RULES["lit_chance"]
                e.pane(face, -proud + 0.12, -proud + 0.12 + side_w, s_plane, sill, head, lit,
                       look="wu_vinyl" if kind == "vinyl" else lot["frame"])
            else:
                e.put(wall, face, s_a, s_b, -proud, 0.0, z0, z1, tint)
    # Underside: a soffit on brackets over the storefront cornice; a cap at the top.
    e.trim(lot["stone"], "front", o0, o1, -proud - 0.04, 0.0, z_bottom - 0.12, z_bottom)
    for s in (o0 + 0.1, (o0 + o1) / 2.0 - 0.1, o1 - 0.3):
        e.put("KIT_Bracket|trim:" + lot["stone"], "front", s, s + 0.2, 0.0, proud, z_bottom - 0.6, z_bottom - 0.12)
    e.trim(lot["cornice"]["colour"], "front", o0 - 0.05, o1 + 0.05, -proud - 0.08, 0.0, z_top, z_top + 0.05)


def _storefront(e, lot, width):
    """Ground floor: pilasters, the stair door at one side, the shop with bulkhead, glass, transom, sign band."""
    sf = lot["storefront"]
    g = lot["ground_h"]
    pil = sf["pilaster"]
    wall = "KIT_Wall|set:" + lot["wall"]
    tint = lot["tint"]
    # Pilasters stand a little proud of the wall.
    e.put(wall, "front", 0.0, pil, -0.06, WALL, 0.0, g, tint)
    e.put(wall, "front", width - pil, width, -0.06, WALL, 0.0, g, tint)
    door_w = sf["door_w"]
    door_zone = door_w + 0.3
    if sf["door_side"] == "left":
        d0, shop0, shop1 = pil, pil + door_zone, width - pil
    else:
        d0, shop0, shop1 = width - pil - door_zone, pil, width - pil - door_zone
    if shop1 - shop0 < 2.4:
        # Too narrow for both: the stair door goes, the shop keeps the front.
        shop0, shop1, d0 = pil, width - pil, None
    b, disp, tr, sh = sf["bulkhead"], sf["display"], sf["transom"], sf["sign_h"]
    z_glass, z_tr, z_sign = b, b + disp, b + disp + tr
    z_cornice = z_sign + sh
    z_top = z_cornice + RULES["sf_cornice"]["h"]
    paint = sf["paint"]
    cond = sf["condition"]
    # The stair door: narrow, recessed, with a transom light, brick around it.
    if d0 is not None:
        dd0, dd1 = d0 + 0.15, d0 + 0.15 + door_w
        door_top = 2.25
        e.front_wall(d0, d0 + door_zone, 0.0, z_cornice, [(dd0, dd1, 0.0, door_top + 0.45)])
        e.trim(paint, "front", dd0, dd1, 0.22, 0.27, 0.0, door_top)
        e.pane("front", dd0 + 0.18, dd1 - 0.18, 0.0, 1.1, door_top - 0.2, False, look="wu_black", depth=0.2)
        e.pane("front", dd0, dd1, 0.0, door_top + 0.05, door_top + 0.4, _rnd(lot, "lit", "stair") < 0.4, look="wu_black",
               depth=0.2)
        e.trim(lot["stone"], "front", dd0 - 0.08, dd1 + 0.08, -0.03, 0.03, door_top + 0.45, door_top + 0.6)
        e.trim("coping", "front", dd0, dd1, -0.1, 0.27, 0.0, 0.08)
    # Entry: recessed with a step; centred in the shop, or at its far end.
    ew, ed = sf["entry_w"], sf["entry_d"]
    if sf["entry_at"] == "centre":
        e0 = (shop0 + shop1) / 2.0 - ew / 2.0
    elif sf["door_side"] == "left":
        e0 = shop1 - ew - 0.1
    else:
        e0 = shop0 + 0.1
    e1 = e0 + ew
    shop_look = "wu_alum" if cond == "remuddled" else ("wu_black" if paint in ("sf_black", "sf_cream") else "wu_brown")
    bulk = "sf_tile" if cond == "remuddled" else paint
    _shop_interior(e, lot, shop0, shop1, e0, e1, ed, z_sign)
    glass_top = z_tr if cond != "remuddled" else z_tr - 0.3
    for g0, g1 in ((shop0, e0), (e1, shop1)):
        if g1 - g0 < 0.2:
            continue
        e.trim(bulk, "front", g0, g1, -0.02, 0.3, 0.0, z_glass)
        e.put("KIT_Glass|shopglass:" + shop_look, "front", g0, g1, 0.0, 0.2, z_glass, glass_top)
        e.trim(paint, "front", g0, g1, -0.05, 0.08, z_glass - 0.04, z_glass + 0.03)
        if cond == "remuddled":
            e.trim("sf_alum", "front", g0, g1, -0.01, 0.2, glass_top, z_tr)
        if cond == "boarded":
            e.decal("plywood", "front", g0, g1, -0.02, 1.0, 0.0, z_tr)
        elif sf["gate"] == "accordion" and sf["gate_closed"]:
            e.decal("gate_accordion", "front", g0, g1, -0.04, 1.0, z_glass, z_tr)
    # The recess: step, side panels, ceiling, the shop door at the back.
    e.trim("sf_tile", "front", e0, e1, 0.0, ed, 0.0, RULES["entry_step"])
    e.trim(bulk, "left", e0 - 0.08, e0, 0.0, ed, 0.0, z_tr)
    e.trim(bulk, "right", e1, e1 + 0.08, 0.0, ed, 0.0, z_tr)
    e.trim(paint, "front", e0, e1, 0.0, ed, z_tr - 0.06, z_tr)
    e.put("KIT_Glass|shopglass:" + shop_look, "front", e0 + 0.08, e1 - 0.08, ed, ed + 0.12, RULES["entry_step"],
          z_tr - 0.08)
    if cond == "boarded":
        e.decal("plywood", "front", e0, e1, ed - 0.02, ed + 1.0, RULES["entry_step"], z_tr)
    # Transom across the shop: lights divided by mullions; infilled on a remuddled front.
    if cond == "remuddled":
        e.trim(paint, "front", shop0, shop1, -0.02, 0.2, z_tr, z_sign)
    else:
        e.put("KIT_Glass|shopglass:" + shop_look, "front", shop0, shop1, 0.0, 0.2, z_tr, z_sign)
        lights = max(3, int(round((shop1 - shop0) / 0.9)))
        for k in range(1, lights):
            s = shop0 + (shop1 - shop0) * k / lights
            e.trim(paint, "front", s - 0.025, s + 0.025, 0.0, 0.1, z_tr, z_sign)
        e.trim(paint, "front", shop0, shop1, -0.04, 0.1, z_tr - 0.04, z_tr + 0.04)
        if cond == "boarded":
            e.decal("plywood", "front", shop0, shop1, -0.02, 1.0, z_tr, z_sign)
    # Gate housing (roll-down) under the sign band, the gate pulled down when closed.
    if sf["gate"] == "rolldown" and cond != "boarded":
        e.trim("galv", "front", shop0, shop1, -0.28, 0.0, z_sign - 0.3, z_sign)
        if sf["gate_closed"]:
            e.decal("gate_rolldown", "front", shop0, shop1, -0.26, 1.0, 0.0, z_sign - 0.3)
    # Sign band, sign, the thin storefront cornice; a box sign on a remuddled front.
    sign_proud = 0.25 if cond == "remuddled" else 0.04
    e.trim(paint if cond != "remuddled" else "sf_cream", "front", shop0, shop1, -sign_proud, 0.2, z_sign, z_cornice)
    if cond != "boarded":
        w = min((shop1 - shop0) * 0.85, 4.0)
        c = (shop0 + shop1) / 2.0
        e.decal(sf["sign"], "front", c - w / 2.0, c + w / 2.0, -sign_proud, 1.0, z_sign + sh * 0.12, z_sign + sh * 0.88)
    e.put("KIT_Cornice|trim:" + paint, "front", pil, width - pil, 0.0, sf["sf_proud"], z_cornice, z_top)
    # Awning over the display glass, below the sign band.
    if sf["awning"]:
        e.put("KIT_Awning|trim:" + sf["awning"], "front", shop0, shop1, 0.0, 1.0 + 0.2 * _rnd(lot, "awn_p"),
              z_tr - 0.55, z_sign - 0.05)
    # Brick between the storefront cornice and the first floor (or the parapet on a one-storey lot).
    if g - z_top > 0.01:
        e.front_wall(pil, width - pil, z_top, g, [])


def _shop_interior(e, lot, shop0, shop1, e0, e1, ed, z_top):
    """The shop behind the glass: a back wall (a generated interior, lit, dimmed or dark), floor,
    ceiling, side walls and a few fittings by kind, so the window reads as a shop, not a light box."""
    sf = lot["storefront"]
    kind = sf["interior"]
    state = "off" if sf["condition"] == "boarded" else sf["lights"]
    back = min(lot["depth"] - 1.0, sf["interior_d"])
    inner = "metal_dark" if state == "off" else "sf_cream"
    e.put("KIT_Panel|shopback:%s.%s" % (kind, state), "front", shop0, shop1, back, back + 1.0, 0.0, z_top)
    e.trim("wood_grey" if kind in ("bar", "clothes") else "sf_tile", "front", shop0, shop1, 0.2, back, 0.0, 0.03)
    e.trim(inner, "front", shop0, shop1, 0.2, back, z_top - 0.04, z_top)
    e.trim(inner, "left", shop0 - 0.08, shop0, 0.2, back, 0.0, z_top)
    e.trim(inner, "right", shop1, shop1 + 0.08, 0.2, back, 0.0, z_top)
    # Fittings stand clear of the entry recess.
    d0 = max(0.6, ed + 0.3)
    span = (shop0 + 0.3, shop1 - 0.3)
    if span[1] - span[0] < 1.2 or back - d0 < 0.8:
        return
    r = lambda *k: _rnd(lot, "shop", *k)  # noqa: E731
    if kind == "grocery":
        for k in range(2):
            s = span[0] + (span[1] - span[0]) * (0.25 + 0.5 * k) - 0.2
            e.trim("metal_dark", "front", s, s + 0.4, d0 + 0.2, back - 0.3, 0.0, 1.6 + 0.2 * r("shelf", k))
            for j in range(4):
                e.trim(PAINTS[int(r("goods", k, j) * len(PAINTS)) % len(PAINTS)], "front", s - 0.02, s + 0.42,
                       d0 + 0.25, back - 0.35, 0.3 + 0.35 * j, 0.5 + 0.35 * j)
        e.trim("wood", "front", span[0], span[0] + 1.3, d0, d0 + 0.55, 0.0, 0.95)
    elif kind == "bar":
        e.trim("wood", "front", span[0], span[1], back - 1.2, back - 0.65, 0.0, 1.05)
        e.trim("brownstone", "front", span[0] - 0.05, span[1] + 0.05, back - 1.25, back - 0.6, 1.05, 1.1)
    elif kind == "laundry":
        e.trim("vinyl", "front", span[0], span[1], back - 0.75, back - 0.05, 0.0, 0.9)
        e.trim("wood_grey", "front", span[0] + 0.4, span[0] + 1.6, d0 + 0.3, d0 + 1.0, 0.0, 0.85)
    elif kind == "clothes":
        for k in range(2):
            s = span[0] + (span[1] - span[0]) * (0.2 + 0.6 * k)
            e.trim("galv", "front", s - 0.6, s + 0.6, d0 + 0.4, d0 + 0.45, 1.45, 1.5)
            e.trim(PAINTS[int(r("cloth", k) * len(PAINTS)) % len(PAINTS)], "front", s - 0.55, s + 0.55,
                   d0 + 0.3, d0 + 0.55, 0.6, 1.45)
        e.trim("wood", "front", (span[0] + span[1]) / 2.0 - 0.6, (span[0] + span[1]) / 2.0 + 0.6,
               back - 1.2, back - 0.5, 0.0, 0.8)


def _cornice_and_parapet(e, lot, width):
    """Front parapet to the top, the cornice at its head, coping, a raised name plaque; returns at exposed sides."""
    deck, top = lot["deck"], lot["top"]
    c = lot["cornice"]
    # The top floor's wall ends at the deck; the front parapet carries on to the top.
    e.front_wall(0.0, width, deck, top, [], module="KIT_Box")
    z0 = cornice_bottom(lot)
    ch = top - z0
    proud = c["proud"]
    sides = []
    if lot["left"] is None or lot["left"]["top"] < top - 0.2:
        sides.append("left")
    if lot["right"] is None or lot["right"]["top"] < top - 0.2:
        sides.append("right")
    if c["kind"] == "bracketed":
        metal = c["colour"]
        crown = 0.3
        e.trim(metal, "front", 0.0, width, -0.12, 0.05, z0, top - crown)
        e.put("KIT_Cornice|trim:" + metal, "front", -0.05, width + 0.05, 0.0, proud, top - crown, top)
        n = max(2, int(round(width / c["brackets"])))
        for k in range(n + 1):
            s = 0.1 + (width - 0.3) * k / n
            e.put("KIT_Bracket|trim:" + metal, "front", s, s + 0.16, -0.12, proud - 0.32, z0 + 0.05, top - crown)
        for k in range(int(width / 0.22)):
            s = 0.06 + k * 0.22
            e.trim(metal, "front", s, s + 0.1, -0.2, -0.12, top - crown - 0.12, top - crown)
        e.trim("coping", "front", 0.05, width - 0.05, 0.05, 0.32, top, top + 0.05)
        _returns(e, lot, sides, metal, z0, top, proud, c["ret"], "metal")
    elif c["kind"] == "corbelled":
        courses = 4
        step_h = (ch - 0.08) / courses
        wall = "KIT_Box|set:" + lot["wall"]
        for k in range(courses):
            out = proud * (k + 1) / courses * 0.85
            z = z0 + step_h * k
            if k == 0:
                # Dentil course: every other brick header stands out.
                for j in range(int(width / 0.24)):
                    s = 0.02 + j * 0.24
                    e.put(wall, "front", s, s + 0.12, -out, 0.0, z, z + step_h, lot["tint"])
            else:
                e.put(wall, "front", 0.0, width, -out, 0.0, z, z + step_h, lot["tint"])
        e.trim("coping", "front", -0.03, width + 0.03, -proud, 0.32, top - 0.08, top)
        _returns(e, lot, sides, "coping", top - 0.08, top, proud, c["ret"], "brick")
    else:
        stone = lot["stone"]
        band = ch * 0.45
        e.trim(stone, "front", 0.0, width, -0.08, 0.05, z0, z0 + band)
        e.put("KIT_Cornice|trim:" + stone, "front", -0.03, width + 0.03, 0.0, proud, z0 + band, top)
        e.trim("coping", "front", 0.05, width - 0.05, 0.05, 0.32, top, top + 0.05)
        _returns(e, lot, sides, stone, z0 + band, top, proud, c["ret"], "stone")
    if lot["plaque"]:
        pw, ph = lot["plaque"]["w"], lot["plaque"]["h"]
        s0 = width / 2.0 - pw / 2.0
        e.front_wall(s0, s0 + pw, top, top + ph, [], module="KIT_Box")
        e.trim(lot["stone"], "front", s0 + 0.2, s0 + pw - 0.2, -0.04, 0.02, top + 0.05, top + ph - 0.1)
        e.trim("coping", "front", s0 - 0.04, s0 + pw + 0.04, -0.06, 0.34, top + ph, top + ph + 0.08)


def _returns(e, lot, sides, trim, z0, z1, proud, ret, kind):
    """The cornice turns the corner and stops 0.3-0.9 m back: the ornament is a false front."""
    width = lot["s1"] - lot["s0"]
    module = "KIT_Box"
    for side in sides:
        if side == "left":
            e.put(module + "|trim:" + trim, "left", -proud, 0.0, -proud, ret, z0, z1)
        else:
            e.put(module + "|trim:" + trim, "right", width, width + proud, -proud, ret, z0, z1)


def _sides(e, lot, width, depth):
    """Side walls in common brick where they show: the building's ends and above a lower neighbour.

    Blind, except a few small windows at the rear. The side parapets step down toward the rear."""
    deck, top, rear = lot["deck"], lot["top"], lot["deck"] + lot["rear_parapet"]
    for side in ("left", "right"):
        nb = lot[side]
        end = lot["end_" + side]
        low = 0.0 if nb is None else nb["deck"]
        s_a, s_b = (0.0, WALL) if side == "left" else (width - WALL, width)
        if deck - low > 0.05:
            e.common(side, s_a, s_b, 0.0, depth, low, deck)
            if end or nb is None:
                # A few small windows at the rear of the upper floors.
                for floor in range(1, lot["floors"]):
                    if _rnd(lot, "sidewin", side, floor) < 0.5:
                        z0, h = floor_z(lot, floor)
                        if z0 < low:
                            continue
                        d1 = depth - 1.2
                        d0 = d1 - 0.75
                        plane = 0.0 if side == "left" else width
                        e.pane(side, d0, d1, plane, z0 + 1.0, z0 + 2.2, _rnd(lot, "lit", side, floor) < 0.25,
                               look="wu_white")
                        e.trim("coping", side, s_a - 0.03 if side == "left" else s_a, s_b + 0.03 if side == "right" else s_b,
                               d0 - 0.05, d1 + 0.05, z0 + 0.92, z0 + 1.0)
        # Parapet steps from the front top down to the rear parapet.
        steps = lot["steps"]
        # The steps bunch up behind the false front (the front 40% of the depth); the rest runs low.
        span = depth * RULES["parapet_step_zone"] / steps
        # Each step drops enough to read from the street, but never below the deck's flashing.
        drop = max(top - rear, RULES["parapet_step_min"] * steps)
        for k in range(steps + 1):
            d0 = span * k
            d1 = depth if k == steps else span * (k + 1)
            h = max(deck + 0.3, top - drop * k / steps)
            if k == steps:
                h = deck + lot["rear_parapet"]
            if nb is not None and nb["top"] >= h - 0.02 and nb["deck"] >= deck - 0.02:
                continue
            e.common(side, s_a, s_b, d0, d1, deck, h, module="KIT_Box")
            e.trim("coping", "front", s_a - 0.03, s_b + 0.03, d0, d1, h, h + 0.07)


def _rear(e, lot, width, depth):
    """Back wall in common brick with plain windows and doors, and the wooden porches and stairs."""
    floors = lot["floors"]
    pd, stair = RULES["porch_depth"], RULES["porch_stair"]
    porch = lot["porch"]
    pw0, pw1 = 0.4, width - 0.4
    for floor in range(floors):
        z0, h = floor_z(lot, floor)
        z1 = z0 + h
        door = (width * 0.62, width * 0.62 + 0.9)
        win = (width * 0.18, width * 0.18 + 0.85)
        holes = [(door[0], door[1], z0 + 0.02, z0 + 2.15)]
        holes_w = [(win[0], win[1], z0 + 0.9, z0 + 2.3)]
        # Door band, then window band: two calls so each has one band of holes.
        e.put("KIT_Wall|set:" + COMMON, "back", 0.0, width, depth - WALL, depth, z0, z0 + 0.02, lot["common_tint"])
        cursor = 0.0
        for h0, h1, hz0, hz1 in sorted(holes + holes_w):
            e.common("back", cursor, h0, depth - WALL, depth, z0 + 0.02, z1)
            e.common("back", h0, h1, depth - WALL, depth, hz1, z1)
            if hz0 > z0 + 0.03:
                e.common("back", h0, h1, depth - WALL, depth, z0 + 0.02, hz0)
            cursor = h1
        e.common("back", cursor, width, depth - WALL, depth, z0 + 0.02, z1)
        e.trim("wood", "back", door[0], door[1], depth - 0.25, depth - 0.2, z0 + 0.02, z0 + 2.15)
        e.pane("back", win[0], win[1], depth, z0 + 0.9, z0 + 2.3, _rnd(lot, "lit", "rear", floor) < 0.3, look="wu_white")
        e.trim("concrete", "back", win[0] - 0.05, win[1] + 0.05, depth - 0.12, depth + 0.04, z0 + 0.84, z0 + 0.9)
    deck, rear = lot["deck"], lot["deck"] + lot["rear_parapet"]
    e.common("back", 0.0, width, depth - WALL, depth, deck, rear, module="KIT_Box")
    e.trim("coping", "back", -0.03, width + 0.03, depth - WALL - 0.03, depth + 0.03, rear, rear + 0.07)
    if not porch:
        return
    wood = "wood" if _rnd(lot, "porch_wood") < 0.6 else "wood_grey"
    d_out = depth + pd + stair
    # Posts at the corners and the middle, up to the porch roof.
    roof_z = floor_z(lot, floors - 1)[0] + 2.7
    for s in (pw0, (pw0 + pw1) / 2.0, pw1 - 0.14):
        for d in (depth + pd - 0.14, d_out - 0.14):
            e.trim(wood, "back", s, s + 0.14, d, d + 0.14, 0.0, roof_z)
    e.trim(wood, "back", pw0 - 0.1, pw1 + 0.1, depth, d_out + 0.1, roof_z, roof_z + 0.12)
    for floor in range(1, floors):
        z, _h = floor_z(lot, floor)
        e.trim(wood, "back", pw0, pw1, depth, depth + pd, z - 0.18, z)
        # Railing: top and bottom rails, balusters.
        e.trim(wood, "back", pw0, pw1, depth + pd - 0.08, depth + pd, z + 0.95, z + 1.03)
        e.trim(wood, "back", pw0, pw1, depth + pd - 0.08, depth + pd, z + 0.08, z + 0.14)
        for k in range(int((pw1 - pw0) / 0.3)):
            s = pw0 + 0.15 + k * 0.3
            e.trim(wood, "back", s, s + 0.04, depth + pd - 0.06, depth + pd - 0.02, z + 0.14, z + 0.95)
        # Stair flight up from the floor below, along the porch, alternating direction.
        zb, hb = floor_z(lot, floor - 1)
        steps = max(8, int(round(hb / 0.19)))
        run = (pw1 - pw0 - 0.3) / steps
        rise = hb / steps
        flip = floor % 2 == 0
        for k in range(steps):
            s = pw0 + 0.15 + run * (steps - 1 - k if flip else k)
            e.trim(wood, "back", s, s + run + 0.02, depth + pd, d_out - 0.1, zb + rise * (k + 1) - 0.05, zb + rise * (k + 1))


def _roof(e, lot, width, depth):
    """Membrane deck, and 3-5 pieces of clutter at real size, off-centre and mostly toward the rear.

    Light-coloured metal and brick on the dark membrane, so they read from the air."""
    deck = lot["deck"]
    # Under the parapets too, so no gap shows at a party wall from the air.
    e.put("KIT_Wall|set:" + ROOF, "front", 0.0, width, 0.0, depth, deck - 0.3, deck, (1.0, 1.0, 1.0))
    side = 1 if lot["storefront"]["door_side"] == "right" else 0
    size = RULES["roof_size"]
    for k, kind in enumerate(lot["roof_items"]):
        u = _rnd(lot, "roof_u", kind)
        v = _rnd(lot, "roof_v", kind)
        # Mostly toward the rear (45-85% of the depth), off the centre line.
        d = depth * (0.45 + 0.4 * v)
        s = width * (0.12 + 0.25 * u) if (k + side) % 2 == 0 else width * (0.55 + 0.25 * u)
        if kind == "chimney":
            # On a party wall, in common brick, with a stone cap and clay flue pots.
            cw, ch = size["chimney"][0], size["chimney"][1] + 0.4 * _rnd(lot, "chim_h")
            s0 = WALL if u < 0.5 else width - WALL - cw
            dd = depth * (0.25 + 0.5 * v)
            e.common("front", s0, s0 + cw, dd, dd + cw, deck, deck + ch, module="KIT_Box")
            e.trim("coping", "front", s0 - 0.05, s0 + cw + 0.05, dd - 0.05, dd + cw + 0.05, deck + ch, deck + ch + 0.08)
            for j in range(1 + int(_rnd(lot, "flues") * 2)):
                fs = s0 + 0.1 + j * 0.24
                e.trim("terracotta", "front", fs, fs + 0.18, dd + 0.21, dd + 0.39, deck + ch + 0.08, deck + ch + 0.45)
        elif kind == "vent":
            for j in range(1 + int(v * 2)):
                vs = s + j * 0.8
                hv = size["vent"][1] + 0.3 * u
                e.trim("galv", "front", vs, vs + size["vent"][0], d, d + size["vent"][0], deck, deck + hv)
                e.trim("galv", "front", vs - 0.06, vs + size["vent"][0] + 0.06, d - 0.06, d + size["vent"][0] + 0.06,
                       deck + hv, deck + hv + 0.08)
        elif kind == "hatch":
            # Near the stair, over the upstairs door's side: a 3 x 3 ft curb and lid.
            hw = size["hatch"][0]
            hs = (0.6 if side == 0 else width - 0.6 - hw)
            hd = depth * 0.35
            e.trim("hatch", "front", hs, hs + hw, hd, hd + hw, deck, deck + size["hatch"][1])
            e.trim("galv", "front", hs - 0.05, hs + hw + 0.05, hd - 0.05, hd + hw + 0.05, deck + size["hatch"][1],
                   deck + size["hatch"][1] + 0.06)
        elif kind == "skylight":
            sw, sl = size["skylight"]
            e.trim("galv", "front", s, s + sw, d - sl / 2.0, d + sl / 2.0, deck, deck + 0.3)
            e.trim("skylight", "front", s + 0.05, s + sw - 0.05, d - sl / 2.0 + 0.05, d + sl / 2.0 - 0.05,
                   deck + 0.3, deck + 0.42)
        elif kind == "condenser":
            cw, chh = size["condenser"]
            for j in range(1 + int(u * 2)):
                cs = min(width - WALL - cw - 0.05, s + j * (cw + 0.3))
                e.trim("metal_dark", "front", cs - 0.05, cs + cw + 0.05, d - 0.05, d + cw + 0.05, deck, deck + 0.1)
                e.trim("condenser", "front", cs, cs + cw, d, d + cw, deck + 0.1, deck + 0.1 + chh)
                e.trim("metal_dark", "front", cs + 0.12, cs + cw - 0.12, d + 0.12, d + cw - 0.12, deck + 0.1 + chh,
                       deck + 0.13 + chh)
        elif kind == "dish":
            dw = size["dish"]
            e.put("KIT_Dish|trim:condenser", "back", s, s + dw, d, d + dw, deck, deck + dw)
        elif kind == "antenna":
            e.trim("galv", "front", s, s + 0.06, d, d + 0.06, deck, deck + 2.4)
            e.trim("galv", "front", s - 0.7, s + 0.76, d, d + 0.04, deck + 2.1, deck + 2.14)
            e.trim("galv", "front", s - 0.45, s + 0.51, d, d + 0.04, deck + 1.75, deck + 1.79)


def _piers(lot):
    """Wall gaps between the upper windows (and the ends), relative to the lot: where streaks can run."""
    width = lot["s1"] - lot["s0"]
    edges = [0.0]
    for c0, c1 in sorted(window_columns(lot) + oriel_windows(lot)):
        edges.extend([c0, c1])
    edges.append(width)
    out = []
    for k in range(0, len(edges) - 1, 2):
        a, b = edges[k] + 0.15, edges[k + 1] - 0.15
        if b - a >= 0.5:
            out.append((a, b))
    return out


def _wear(e, lot, width):
    """Rain streaks under sills and the cornice, soot under the cornice, soft brick repairs."""
    cols = window_columns(lot)
    for floor in range(1, lot["floors"]):
        z0, _h = floor_z(lot, floor)
        sill = z0 + lot["sill_above"]
        for k, (c0, c1) in enumerate(cols):
            if _rnd(lot, "streak", floor, k) < RULES["streak_chance"]:
                name = STREAKS[int(_rnd(lot, "streak_kind", floor, k) * len(STREAKS)) % len(STREAKS)]
                drop = RULES["streak_drop"][0] + (RULES["streak_drop"][1] - RULES["streak_drop"][0]) * _rnd(
                    lot, "streak_h", floor, k)
                bottom = max(sill - lot["sill_h"] - drop, z0 - 0.4 if floor > 1 else lot["ground_h"])
                e.decal(name, "front", c0 - 0.12, c1 + 0.12, 0.0, 1.0, bottom, sill - lot["sill_h"])
    top = cornice_bottom(lot)
    if lot["floors"] >= 2:
        z_floor, _h = floor_z(lot, lot["floors"] - 1)
        head = z_floor + lot["sill_above"] + lot["wh"] + lot["lintel_h"] * 1.5
        if _rnd(lot, "soot") < RULES["soot_chance"]:
            name = SOOTS[int(_rnd(lot, "soot_kind") * len(SOOTS)) % len(SOOTS)]
            e.decal(name, "front", 0.0, width, 0.0, 1.0, max(head - 0.6, top - RULES["soot_h"]), top)
        # Runs from the cornice and coping down the piers between the top-floor windows.
        for k, (a, b) in enumerate(_piers(lot)):
            if _rnd(lot, "coping_streak", k) < RULES["coping_streak_chance"]:
                name = STREAKS[int(_rnd(lot, "coping_kind", k) * len(STREAKS)) % len(STREAKS)]
                drop = 1.2 + 1.0 * _rnd(lot, "coping_h", k)
                e.decal(name, "front", a, b, 0.0, 1.0, max(lot["ground_h"] + 0.3, top - drop), top)
    if _rnd(lot, "patch") < RULES["patch_chance"] and lot["floors"] >= 2:
        sf = lot["storefront"]
        z_top = sf["bulkhead"] + sf["display"] + sf["transom"] + sf["sign_h"] + RULES["sf_cornice"]["h"]
        piers = _piers(lot) or [(0.2, width - 0.2)]
        a, b = piers[int(_rnd(lot, "patch_pier") * len(piers)) % len(piers)]
        floor = 1 + int(_rnd(lot, "patch_floor") * max(1, lot["floors"] - 1)) % max(1, lot["floors"] - 1)
        z0, h = floor_z(lot, floor)
        _repair(e, lot, a, b, max(z_top + 0.05, z0 + 0.3), z0 + h - 0.15, "front")


def _repair(e, lot, a, b, z0, z1, face, key="walls"):
    """A brick repair: newer brick of the same kind, 5 mm proud, in courses with a toothed outline.

    Real geometry in the wall's own swatch, so its bricks line up with the wall's (M_KitWall projects
    in world metres) and it takes the wall's light; only its tint (newer, a little redder) differs."""
    course = 0.0667
    w = min(RULES["repair_w"][1], b - a)
    if w < 0.5 or z1 - z0 < 0.5:
        return
    s0 = a + (b - a - w) * _rnd(lot, "repair_s", face, key)
    rows = int(min(RULES["repair_h"][1], z1 - z0) / course / 3)  # bands of three courses
    tint = tuple(min(1.35, c * f) for c, f in zip(lot["tint"] if face == "front" else lot["common_tint"],
                                                RULES["repair_tint"]))
    wall = "KIT_Box|set:" + (lot["wall"] if face == "front" else COMMON)
    zb = z0 + (z1 - z0 - rows * 3 * course) * _rnd(lot, "repair_z", face, key)
    zb = round(zb / course) * course
    for k in range(rows):
        # Each band steps in or out by half a brick, so the edge is toothed like a real repair.
        mid = abs(k - (rows - 1) / 2.0) / max(1.0, (rows - 1) / 2.0)
        inset = 0.11 * int(1 + 3 * mid * _rnd(lot, "repair_tooth", face, key, k))
        lo, hi = s0 + inset, s0 + w - inset * (0.5 + _rnd(lot, "repair_tooth_r", face, key, k))
        if hi - lo < 0.25:
            continue
        zk = zb + 3 * course * k
        if face == "front":
            e.put(wall, "front", lo, hi, -0.005, 0.02, zk, zk + 3 * course, tint)
        elif face == "left":
            e.put(wall, "left", -0.005, 0.02, lo, hi, zk, zk + 3 * course, tint)
        else:
            width = lot["s1"] - lot["s0"]
            e.put(wall, "right", width - 0.02, width + 0.005, lo, hi, zk, zk + 3 * course, tint)


def _ghosts(layout, lots):
    """Painted ghost signs on exposed side walls: building ends, and above a lower neighbour."""
    for lot in lots:
        if lot["vacant"]:
            continue
        e = Emit(layout, lot)
        width = lot["s1"] - lot["s0"]
        for side in ("left", "right"):
            nb = lot[side]
            low = 0.0 if nb is None else nb["deck"]
            exposed = lot["deck"] - max(low, 3.0)
            if exposed < 2.5 or _rnd(lot, "ghost", side) >= RULES["ghost_chance"]:
                continue
            name = GHOSTS[int(_rnd(lot, "ghost_kind", side) * len(GHOSTS)) % len(GHOSTS)]
            w = min(6.0, lot["depth"] * 0.6)
            h = min(4.0, exposed - 0.3, w * 0.66)
            d0 = lot["depth"] * 0.08
            z1 = lot["deck"] - 0.3
            if side == "left":
                e.put("KIT_Decal|gdecal:" + name, "left", -0.001, 1.0, d0, d0 + w, z1 - h, z1)
            else:
                e.put("KIT_Decal|gdecal:" + name, "right", width - 1.0, width + 0.001, d0, d0 + w, z1 - h, z1)
            if _rnd(lot, "patch_side", side) < RULES["patch_chance"]:
                pz = max(low + 0.5, 1.0)
                pd = lot["depth"] * (0.5 + 0.3 * _rnd(lot, "patch_side_d", side))
                _repair(e, lot, pd, pd + 2.0, pz, pz + 1.6, side, "side")


def _vacant(e, lot, width, depth):
    """A vacant lot: a cracked slab and a low fence; the neighbours' party walls show."""
    e.trim("concrete", "front", 0.0, width, 0.0, depth, -0.05, 0.02)
    for k in range(int(width / 2.4) + 1):
        s = min(width - 0.06, k * 2.4)
        e.trim("galv", "front", s, s + 0.05, 0.1, 0.15, 0.0, 1.2)
    e.trim("galv", "front", 0.0, width, 0.1, 0.13, 1.12, 1.16)


def layout_buildings(layout, buildings):
    """Lay out every walkup in buildings; returns the lots (for the report and the tests)."""
    lots = plan_city(buildings)
    for lot in lots:
        layout_lot(layout, lot)
    _ghosts(layout, lots)
    return lots
