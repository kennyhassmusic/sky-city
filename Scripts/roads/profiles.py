"""Curb, gutter and crosswalk profiles shared by the road network and the street kit.

The streets built so far are a flat asphalt ribbon with a vertical 15 cm step up to the
sidewalk (Scripts/roads/build_roads_ue.py). A real street has a gutter pan in the roadway,
sloped to the curb, and a curb face that leans back instead of standing as a wall. Those
two sections live here so roadnet.design_section, the street-kit meshes and the block
preview all use the same numbers.

Units are metres. In a section, x (or y, for a mesh) increases from the lane edge outward
toward the sidewalk, and z is up. The travel lane's edge is z = 0. The sidewalk stays
0.15 m above that edge, which is the rise the rest of the city already uses. The pan sags
a few centimetres so water reaches the inlet, and the curb face, measured from the flow
line, is that sag plus the 0.15 m rise. The face is battered: the top is set back from
the flow line, so the mesh is a bevel rather than a vertical wall.

Run: imported. python3 -I Scripts/roads/test_profiles.py
"""

# Lane and parking widths copied from the rules in roadnet.design_section (AASHTO / NACTO).
LANE_W = {"highway": 3.6, "major": 3.3, "mid": 3.3, "minor": 3.0}
PARKING_W = {"highway": 0.0, "major": 2.4, "mid": 2.4, "minor": 2.1}
# Whole zone from the back of the curb to the property line. Downtown is paved. Elsewhere
# the zone is a grass parkway plus a walk, and the two add up to this width.
SIDEWALK_CORE = 4.6
SIDEWALK_OTHER = 3.8
PARKWAY_W = 2.0
WALK_OTHER = 1.8
FURNITURE_W = 1.5
CURB_RISE = 0.15          # sidewalk above the travel-lane edge
GUTTER_DROP = 0.03        # flow line below the travel-lane edge
CURB_BATTER = 0.04        # how far the top of the face sits back from the flow line
CURB_TOP_W = 0.15
# Curb-return radius by street class. roadnet.RADIUS reads this so the two cannot drift.
CURB_RETURN_RADIUS = {"minor": 6.0, "mid": 7.5, "major": 9.0, "highway": 15.0}
# Kinds that sit outside the travel lanes. The L and the expressway clearance treat them
# the same way they already treat a parking lane.
SIDE_STRIPS = ("parking", "gutter")

# Paint. Continental matches the bars roadnet already draws (0.6 m every 1.2 m, 3.0 m deep).
# Ladder is the second downtown variant: two longitudinal rails and thinner rungs.
CONTINENTAL = {"kind": "continental", "width_m": 3.0, "bar_m": 0.6, "pitch_m": 1.2,
               "stop_bar_m": 0.6, "stop_gap_m": 1.2}
LADDER = {"kind": "ladder", "width_m": 3.0, "bar_m": 0.4, "pitch_m": 0.8, "rail_m": 0.15}
CROSSWALKS = {"continental": CONTINENTAL, "ladder": LADDER}

# Spacing the block preview and, later, the full furniture pass both follow.
SPACING = {
    "lamp_arterial_m": 30.0,
    "lamp_collector_m": 35.0,
    "lamp_local_m": 40.0,
    "tree_grate_m": 9.0,
    "tree_parkway_m": 10.0,
    "corner_clear_m": 8.0,     # no tree or lamp in the ramp / crosswalk at a corner
}


def is_side_strip(kind):
    """True for a gutter pan or a parking lane: outside the travelled way."""
    return kind in SIDE_STRIPS


def gutter_spec(cls, under=False):
    """The pan, or None where a street has a shoulder instead (expressway, or lanes under a deck)."""
    if cls == "highway" or under:
        return None
    return {
        "width_m": 0.30 if cls == "minor" else 0.45,
        "drop_m": GUTTER_DROP,
        "slope": "to_curb",
    }


def curb_spec(cls, core=False):
    """Beveled curb. `rise_m` is the sidewalk height above the lane edge, kept at 15 cm."""
    if cls == "highway":
        return {"profile": "none", "rise_m": 0.0, "return_radius_m": CURB_RETURN_RADIUS["highway"]}
    drop = GUTTER_DROP
    return {
        "profile": "bevel",
        "rise_m": CURB_RISE,
        "face_m": round(CURB_RISE + drop, 3),
        "batter_m": CURB_BATTER,
        "top_width_m": CURB_TOP_W,
        "return_radius_m": CURB_RETURN_RADIUS[cls],
        "core": bool(core),
    }


def curb_ramp_spec():
    """A curb ramp at a crosswalk. Slope 1:12, so the run is twelve times the 15 cm rise.
    The ramp sits in the sidewalk, not in the lane. Flares pick up the curb on either side."""
    rise = CURB_RISE
    slope = 1.0 / 12.0
    return {
        "width_m": 1.2,
        "rise_m": rise,
        "slope": slope,
        "run_m": round(rise / slope, 3),
        "flare_m": 0.9,
    }


def street_profile(cls="major", under=False):
    """Open polyline (x, z) from the lane edge to the back of the curb.

    x = 0, z = 0 is the lane edge. x increases toward the sidewalk. The last point is the
    back of the curb at the sidewalk height. Empty of a gutter (an expressway) it is just
    the lane edge.
    """
    g = gutter_spec(cls, under)
    c = curb_spec(cls)
    if g is None:
        return [(0.0, 0.0)]
    x1 = g["width_m"]
    z1 = -g["drop_m"]
    x2 = x1 + c["batter_m"]
    z2 = c["rise_m"]
    x3 = x2 + c["top_width_m"]
    return [(0.0, 0.0), (round(x1, 3), round(z1, 3)), (round(x2, 3), round(z2, 3)), (round(x3, 3), round(z2, 3))]


def curb_solid_section(cls="major"):
    """Closed (x, z) ring for a curb-and-gutter mesh, buried slightly so it meets the asphalt."""
    surf = street_profile(cls)
    if len(surf) < 2:
        return surf
    bury = -0.08
    return surf + [(surf[-1][0], bury), (surf[0][0], bury)]


def carve_gutters(elems, cls, under=False):
    """Split a gutter pan off the outermost element on each side.

    The pan is part of the carriageway, so the total width does not change and the ribbons
    the city already built keep their edges. What changes, once roadnet is re-run, is that
    the outer strip is labelled `gutter` instead of being the edge of a lane or a parking
    stall. Returns (elems, gutter_spec or None). The input is not mutated.
    """
    original = [list(e) for e in elems]
    spec = gutter_spec(cls, under)
    if spec is None or len(original) < 1:
        return original, None
    w = spec["width_m"]
    elems = [list(e) for e in original]
    for index in (0, -1):
        # Leave a real lane or stall behind the pan. A very narrow outer piece (a barrier,
        # a short shoulder) is not a place to steal a gutter from.
        if elems[index][0] in ("barrier", "shoulder") or elems[index][1] <= w + 0.8:
            return original, None
        elems[index][1] = round(elems[index][1] - w, 2)
    gutter = ["gutter", w, 0]
    return [gutter] + elems + [gutter], spec


def preview_section(cls, lanes, oneway, core):
    """Cross-section for one block, using the same widths as design_section's common cases.

    This is the downtown / neighbourhood case (no expressway deck, no roundabout, no
    "does it fit between the buildings" shrink). The full city still goes through
    roadnet.design_section, which calls carve_gutters on the way out.
    """
    lanes = max(1, int(lanes))
    lw = LANE_W[cls]
    # A one-way local with a single lane is wider, so a fire truck clears parked cars
    # (the same exception as roadnet.design_section).
    if cls == "minor" and oneway and lanes == 1:
        lw = 3.6
    pw = PARKING_W[cls]
    if cls == "highway":
        park = (False, False)
    elif cls == "major" and core and not oneway:
        park = (False, False)
    elif cls == "major" and core and oneway:
        park = (False, True)     # one loading lane on the right
    else:
        park = (True, True)
    if oneway:
        elems = (([["parking", pw, 0]] if park[0] else [])
                 + [["lane", lw, 1]] * lanes
                 + ([["parking", pw, 0]] if park[1] else []))
    else:
        n = max(2, lanes)
        n_b = n // 2
        n_f = n - n_b
        elems = (([["parking", pw, 0]] if park[0] else [])
                 + [["lane", lw, -1]] * n_b)
        if cls in ("major", "mid"):
            elems.append(["dy", 0.3, 0])
        elems += [["lane", lw, 1]] * n_f + ([["parking", pw, 0]] if park[1] else [])
    elems, gutter = carve_gutters(elems, cls, False)
    if cls == "highway":
        sw, parkway = 0.0, False
    elif core:
        sw, parkway = SIDEWALK_CORE, False
    else:
        sw, parkway = SIDEWALK_OTHER, True
    return {
        "elems": elems,
        "width": round(sum(e[1] for e in elems), 2),
        "sidewalk": sw,
        "walk_w": sw if not parkway else WALK_OTHER,
        "parkway": parkway,
        "parkway_w": PARKWAY_W if parkway else 0.0,
        "furniture_w": FURNITURE_W if core else 0.0,
        "curb": curb_spec(cls, core),
        "gutter": gutter,
        "core": bool(core),
        "class": {"highway": "expressway", "major": "arterial", "mid": "collector", "minor": "local"}[cls],
    }


def continental_offsets(span_m):
    """Bar centres across a carriageway, measured from its centreline.

    This is the loop in roadnet's marking pass: a 0.6 m bar every 1.2 m, each bar
    3.0 m long in the direction of traffic. `span_m` is the curb-to-curb width.
    """
    k = -span_m / 2.0 + CONTINENTAL["bar_m"]
    out = []
    while k <= span_m / 2.0 - 0.5:
        out.append(round(k, 3))
        k += CONTINENTAL["pitch_m"]
    return out


def ladder_rails(span_m):
    """The two edge rails of a ladder crosswalk, as (along-traffic offset, rail width).

    The rungs are the continental bars. The rails run curb to curb, 1.5 m either
    side of the crosswalk centre, so the crossing reads as a ladder rather than a zebra.
    """
    half = CONTINENTAL["width_m"] / 2.0
    w = LADDER["rail_m"]
    return ((-half, w), (half, w))


def curb_back_from_flow(cls="major"):
    """How far the back of the curb sits toward the sidewalk from the flow line."""
    p = street_profile(cls)
    if len(p) < 3:
        return 0.0
    return round(p[-1][0] - p[1][0], 3)


def face_is_bevel(profile):
    """The curb face (the segment that climbs to the sidewalk) must move outward as it rises."""
    climb = [(a, b) for a, b in zip(profile, profile[1:]) if b[1] > a[1] + 1e-6]
    return bool(climb) and all(b[0] > a[0] + 1e-6 for a, b in climb)
