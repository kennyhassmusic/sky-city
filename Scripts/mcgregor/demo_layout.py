"""Unveil ("demo") area layout for the McGregor maps -> Saved/McGregor/demo_layout.json.

Where: the real unveil spot Kenny found (20 Oct 2026), from his marks on an Apple Maps screenshot
(SourceArt/Reference/McGregor/unveil/09_kenny_layout_sketch_applemaps.webp), georeferenced to the site frame (metres,
x east, y north, origin = facility centre): similarity fit to 8 control points shared with the NAIP aerial and the OSM
roads, 0.511 m per screenshot pixel, screen-up = bearing 42.6 deg (the screenshot is NOT north-up: its compass points
up-left), RMS 5.3 m. Overlay proof: SourceArt/Reference/McGregor/unveil/georef_*.jpg. Every number below came out of
that fit (Scripts/mcgregor/georef_sketch.py redoes it).

How it was laid out (Kenny's marks + his photos 01-10 and the night drone shot):
  yellow  the paved lot                 -> LOT (graded as one gently sloped slab by build_mcgregor_ue.py's demo stage)
  black   the stage                     -> STAGE on the long black stroke NE of the filled box, square to it, facing
                                           the audience (away from the red line): low deck with a red LED edge, an LED
                                           screen past each end turned in toward the crowd, truss light masts outboard
                                           of them facing the crowd, a T mast in the crowd; camera risers on the filled
                                           box; back-of-house by the Roadster building (round 2, see STAGE below)
  red     staging / performance limit   -> RED_LINE: barricades along it; the stage side is the staging area, the far side
                                           the performance area (ramp, both lines, line-up, cranes)
  blue    ramp + its run-up line        -> RAMP at the blue scribble, facing along RUNUP; the player spawns at RUNUP[0]
  green   fleet jump + fleet line       -> FLEET (the line-up, side by side along the lane) and FLEET_LINE (kickflip lane);
                                           since round 2 the line-up is at the line's W end, the run from the E end
                                           (Kenny: "the fleet jump is inverted"; FLEET_AT = "east" puts it back)
  white   the two blurred buildings     -> BUILDINGS: long plain white windowless boxes, vertical panel joints, dark base
                                           band; heights estimated from photo 08 (the overhead door ~4.9 m, wall ~2.9 doors)

KENNY'S CORRECTION (he thinks the sketch may be drawn too big / off): change SCALE (about the stage), ROTATE (about the
stage, degrees clockwise) and/or OFFSET (metres east, north) below; or edit any single mark (LOT corners, RUNUP ends,
RAMP, FLEET, ...). The buildings are measured from the imagery, so they don't move with SCALE/ROTATE/OFFSET.
POLES is the telephone line used for the landing check printed at the end (default: the OSM-mapped line; put Kenny's
pole(s) here). Then rerun everything (see the hand-over note mcgregor-unveil-2026-10-20.md):
  python3 -I Scripts/mcgregor/demo_layout.py
  python3 -I Scripts/hud/make_minimaps.py McGregor
  editor, McGregor:      py .../build_mcgregor_ue.py kit_unveil demo save ; py .../lineup_ue.py place save ;
                         py .../pickups_ue.py place save ; py .../hud/minimap_ue.py import
  editor, McGregorNight: py .../build_mcgregor_ue.py demo save ; py .../lineup_ue.py place save ;
                         py .../pickups_ue.py place save ; py .../night_ue.py lights save
Round 2 (20 Oct 2026, mcgregor-fixes agent): stage/screens/masts turned and placed from the photos + BAR1, the line-up
swapped to the other end of the green line, the lot held level under the ramp (pads[].level, RAMP["level"]).
Run: python3 -I Scripts/mcgregor/demo_layout.py"""
import json, math, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]

# ================================================================= KEY NUMBERS (site metres: x east, y north)
SCALE = 1.0                  # Kenny's marks scaled about the stage centre (0.8 = everything 20 % closer to the stage)
ROTATE = 0.0                 # then turned about the stage centre, degrees clockwise
OFFSET = (0.0, 0.0)          # then moved, metres (east, north)

LOT = [(1641.3, 1029.4), (1673.2, 797.5), (1411.5, 749.4), (1388.3, 929.0)]   # yellow: N, E, S, W corners (paved)
# round 2: the slab is paved a little past Kenny's yellow NW edge, by the W corner, so the kickflip over the line-up
# lands and runs out on asphalt (75 m past the row, 40 m either side, + 4 m); inserted after the W corner (~3000 m2).
# "lot" in the JSON stays the four yellow corners (other scripts take its centre); the slab's ring is "lot_paved".
LOT_EXTRA = [(1397.2, 971.9), (1466.9, 964.8)]
# Round 2: the WHOLE EVENT (stage, screens, masts, risers, audience, the red line AND the performance area: ramp + run-up,
# fleet line + line-up, lanes, cranes, light towers, show wall) moved together as one rigid piece, metres (east, north),
# for landing room past the line-up (Kenny). Moving only the performance area would have to slide it along the red
# line: 40 m bought only 17 m of run-out and turned the ramp 9-16 deg off where photos 02/03/05 show it from the
# audience, so the stage goes with it. 15 m toward bearing 150 (away from the NW lot edge the kickflip lands toward):
# run-out past the row 37 -> 68 m to Kenny's yellow edge; the right-hand LED screen / mast end up 7 m off the Roadster
# building; the lot, the buildings and the poles stay where they are. (0, 0) = the event on Kenny's marks.
EVENT_OFFSET = (7.5, -12.99)
# black, measured stroke by stroke (Scripts/mcgregor/georef_sketch.py frame; round 2, 20 Oct 2026):
#   BAR1  the long stroke NE of the filled box: centre (1595.3, 863.8), 49 m along bearing 99.0  -> the stage
#   BOX   the filled box (with the two thin strokes off its corners): centre (1558.9, 840.4)      -> camera risers
#   BAR4  the long stroke to the west: centre (1513.5, 848.9), 50 m along bearing 51.5           (not built)
#   TICK  the little cross on the thin stroke in front of BAR1, (1595.3, 845.0)                   -> the T mast in the crowd
# Round 1 put the stage on the centroid of ALL the black ink, square to the red line (facing 169.6). Kenny's photos say
# otherwise: from the audience the ramp shows LEFT of the stage's centre line (photos 03 ~6 deg left, 05 ~20 deg left of
# the stage normal, the night drone ~13 deg left), and photo 02 (from the front of the left wing) has it ~31 deg right
# of the wing's normal. With the ramp where Kenny drew it, the stage on BAR1 facing square to it (189) reproduces all
# of those (-5, -18, -6, +28); on the old centroid it took facing ~207, 25 deg off any black stroke.
STAGE = {"p": (1595.3, 863.8),        # BAR1's centre
         "len": 34.0, "dep": 12.0,    # deck length along BAR1, depth (the kit deck is 34 x 12 m, 1.2 m high)
         "faces": 189.0,              # bearing the front faces: square to BAR1, toward the audience (None = square to the red line)
         "screen_toe": 25.0,          # the LED screens at the ends turn IN toward the audience by this (photos 03/05: each faces across)
         "screen_w": 15.0,            # their width (the kit's is 12 m at 16:9; the photos' read ~2.2:1)
         "risers": (1558.9, 840.4),   # BOX: camera risers (None = one riser behind the audience)
         "tmast": (1595.3, 845.0),    # TICK: a T-top light/camera mast in the middle of the crowd (drone shot; None = none)
         "hospitality": (44.0, 32.0)} # umbrellas / tables / sofas: centre, metres right of the stage axis and in front of the
                                      # stage (round 1: 30, 58; with the event moved, that fell off the lot's SE edge)
RED_LINE = [(1657.6, 893.7), (1401.8, 846.7)]          # red: staging area (stage side) | performance area
RUNUP = [(1460.8, 884.1), (1567.8, 953.3)]             # blue line: start (player spawn) -> toward the ramp
RAMP = {"p": (1584.4, 959.9),          # blue scribble: centroid less 2 m (the kit ramp's footprint centre is 2 m past its origin)
        "heading": None,               # car's travel up the ramp, bearing (None = from RUNUP[0] straight at RAMP p)
        "level": (-10.0, 16.0, 8.0),   # the lot is LEVEL under the ramp: metres along the travel (from, to) and half-width
        "dz": -0.01}                   # the ramp's apron sits 1 cm proud of that level patch (flush, no z-fighting)
GREEN = [(1456.7, 933.8), (1579.4, 923.0), (1591.2, 920.1)]   # green as drawn: line W end, line E end, the circle
# Kenny, 20 Oct round 2: "the fleet jump is inverted, the fleet has to be on the other side from where they are right
# now, the line is correct though" -> the line stays, the line-up swaps ends with the kickflip run's start: the row is
# centred on the W end of the green line and the run comes from the E end (where the circle is). "east" = as first drawn.
FLEET_AT = "west"
FLEET_LINE = [GREEN[2], GREEN[0]] if FLEET_AT == "west" else [GREEN[0], GREEN[1]]   # kickflip run start -> toward the row
FLEET = {"p": GREEN[0] if FLEET_AT == "west" else GREEN[2],   # centre of the line-up row
         "faces": None}                # bearing the vehicles face (None = square to the lane, toward the stage)
# Kenny, round 2: "I don't think there is enough landing room for the fleet jump. can you move the whole set ... more
# margin on that side of the performance area?" then "I meant the whole performance area, not just the fleet jump" and
# "because the context matters" -> EVENT_OFFSET below moves the event as one rigid piece.
# the two white rectangles Kenny marked (Apple blurs the buildings; sizes = the blurred footprints)
BUILDINGS = [
    {"name": "RoadsterBuilding", "p": (1684.6, 851.5), "len": 72.1, "wid": 51.9, "h": 14.0, "bearing": 36.5},
    {"name": "WhiteBuilding2", "p": (1803.9, 822.8), "len": 157.0, "wid": 52.7, "h": 14.0, "bearing": 43.9},
]
# telephone line for the landing check (OSM way 435741101, power=minor_line, mapped ~2016: poles at its vertices)
POLES = [(1642.2, 535.2), (1634.8, 572.3), (1625.6, 619.1), (1605.1, 689.5), (1588.5, 744.8), (1566.9, 804.5),
         (1546.4, 866.1), (1529.2, 920.6), (1517.9, 980.8), (1511.8, 1001.8), (1474.1, 1047.7), (1433.1, 1093.3),
         (1393.0, 1139.0), (1354.5, 1185.7), (1314.1, 1230.9), (1273.6, 1277.1)]
LANDING_BACK = (25.0, 80.0)  # where the car comes down after the ramp, metres back along the run-up (real stunt)
# =================================================================

GEOREF = {"sketch": "SourceArt/Reference/McGregor/unveil/09_kenny_layout_sketch_applemaps.webp", "m_per_px": 0.5110,
          "up_bearing_deg": 42.61, "origin_px0": [1516.6, 1439.7], "rms_m": 5.26, "max_m": 9.4, "control_points": 8}


def heading(a, b):
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))


def off(p, yaw, d):
    r = math.radians(yaw)
    return [round(p[0] + math.sin(r) * d, 2), round(p[1] + math.cos(r) * d, 2)]


def lerp(a, b, t):
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]


S0 = STAGE["p"]


def T(p):
    """Kenny's correction: scale + rotate about the stage centre, then offset."""
    dx, dy = (p[0] - S0[0]) * SCALE, (p[1] - S0[1]) * SCALE
    r = math.radians(ROTATE)
    x = dx * math.cos(r) + dy * math.sin(r)
    y = -dx * math.sin(r) + dy * math.cos(r)
    return [round(S0[0] + x + OFFSET[0], 2), round(S0[1] + y + OFFSET[1], 2)]


def Ev(p):
    """An event mark: Kenny's correction, then the whole-event move (EVENT_OFFSET). The lot and buildings don't move."""
    q = T(p)
    return [round(q[0] + EVENT_OFFSET[0], 2), round(q[1] + EVENT_OFFSET[1], 2)]


def H(b):
    return None if b is None else b + ROTATE


lot = [T(p) for p in LOT]
lot_paved = lot + [T(p) for p in LOT_EXTRA]
red = [Ev(p) for p in RED_LINE]
run = [Ev(p) for p in RUNUP]
fl = [Ev(p) for p in FLEET_LINE]
stage_p = Ev(S0)
ramp = Ev(RAMP["p"])
start = run[0]
travel = H(RAMP["heading"]) if RAMP["heading"] is not None else heading(start, ramp)
fleet_c = Ev(FLEET["p"])
U2 = heading(fl[0], fleet_c)                     # kickflip lane heading, toward the line-up


def ts(p, o, hd):
    """(along, left) of p in the frame at o heading hd."""
    dx, dy = p[0] - o[0], p[1] - o[1]
    r1, r2 = math.radians(hd), math.radians(hd - 90)
    return (dx * math.sin(r1) + dy * math.cos(r1), dx * math.sin(r2) + dy * math.cos(r2))


def seg_dist(p, a, b):
    ab = (b[0] - a[0], b[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / (ab[0] ** 2 + ab[1] ** 2)))
    return math.dist(p, (a[0] + ab[0] * t, a[1] + ab[1] * t))


def inside(p, poly):
    c = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def ix(a, b, c, d):
    """Intersection of lines a-b and c-d."""
    x1, y1, x2, y2, x3, y3, x4, y4 = *a, *b, *c, *d
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    return [round(x1 + t * (x2 - x1), 2), round(y1 + t * (y2 - y1), 2)]


X_C = ix(start, ramp, fl[0], fleet_c)

# ---- the line-up: five vehicles side by side along the lane, centred on the green circle, fronts flush
PARTS_FILE = ROOT / "SourceArt/Vehicles/parts.json"
if not PARTS_FILE.exists():
    PARTS_FILE = ROOT / "Scripts/vehicles/placeholder_parts.json"   # public repo: the stand-ins' parts
PARTS = json.load(open(PARTS_FILE))
order = ["Robotaxi", "Cybertruck", "Semi", "ModelY", "Model3"]   # from the near (lane) end
row_len = sum(PARTS[n]["size_m"][1] for n in order) + 1.15 * (len(order) - 1)
K = off(fleet_c, U2 + 180, row_len / 2)           # the row's near end
side_stage = 1 if ts(stage_p, fleet_c, U2)[1] < 0 else -1          # stage to the right of the lane -> face right
FACE = H(FLEET["faces"]) if FLEET["faces"] is not None else U2 + 90 * side_stage
# Kenny's render reads Model 3, Model Y, Semi, Cybertruck, Cybercab from left to right seen from the front: keep that
# whichever way the row faces
if math.sin(math.radians(FACE - U2)) > 0:
    order = order[::-1]
lineup, d = [], 0.0
for n in order:
    w = PARTS[n]["size_m"][1]
    d += w / 2
    lineup.append({"name": n, "p": off(K, U2, d), "yaw": round(FACE, 1)})
    d += w / 2 + 1.15
row_end = off(K, U2, row_len)

# ---- corridors kept clear of anything solid: the run-up (+ the fly-back landing zone behind the start), the kickflip
# lane (+ its run-out: the barrel roll carries the car ~35 m sideways, either way: drive tests 20 Oct), the ramp itself
CLEAR = [
    {"name": "runup", "a": off(ramp, travel, -4.0), "b": start, "half": 12.0},
    {"name": "flyback", "a": start, "b": off(start, travel + 180, 220.0), "half": 18.0},
    {"name": "kickflip_lane", "a": fl[0], "b": K, "half": 12.0},
    {"name": "kickflip_runout", "a": K, "b": off(row_end, U2, 75.0), "half": 42.0},
    {"name": "ramp", "a": off(ramp, travel, -10.0), "b": off(ramp, travel, 14.0), "half": 9.0},
]


def clear_of(p, pad=0.0, skip=()):
    return all(seg_dist(p, c["a"], c["b"]) > c["half"] + pad for c in CLEAR if c["name"] not in skip)


def along(a, b, step):
    L = math.dist(a, b)
    hd = heading(a, b)
    return [{"p": off(a, hd, step * (k + 0.5)), "yaw": round(hd, 1)} for k in range(int(L // step))]


# ---- paint and LEDs, drawn by the demo stage as thin ribbons that follow the graded lot: Line 1 (run-up, white) with red
# LED strips either side (the drone shot's red-lit run-up), Line 2 (kickflip lane), red LED strips in front of and
# behind the line-up
line1_from = off(start, travel + 180, 10.0)
paint = [{"pts": [line1_from, off(ramp, travel, -4.0)], "w": 0.3, "mat": "paint"},
         {"pts": [fl[0], off(K, U2 + 180, 1.0)], "w": 0.3, "mat": "paint"}]
for s_ in (-1, 1):
    paint.append({"pts": [off(line1_from, travel - 90 * s_, 4.5), off(off(ramp, travel, -6.0), travel - 90 * s_, 4.5)], "w": 0.12, "mat": "led"})
# (21 Oct, mcgregor-placer, Kenny: "weird lights in the way of the fleet jump": the strips beside the row used to run 3.2 /
# 3.6 m off the row, i.e. under the kickflip itself; they now stand ROW_LED_OFF m off the row, outside the jump corridor,
# which must stay clear of anything lit or solid for CORRIDOR_HALF m either side of the fleet line)
CORRIDOR_HALF = 8.0
ROW_LED_OFF = 9.0
for o in (ROW_LED_OFF, -ROW_LED_OFF):
    q = off(K, FACE if o > 0 else FACE + 180, abs(o))
    paint.append({"pts": [off(q, U2, -14.0), off(q, U2, row_len + 14.0)], "w": 0.12, "mat": "led"})
# lit lane posts flank the START of the kickflip run (Kenny: "where the car spawns, on either side of it"), in pairs
# LANE_POST_OFF m off the lane (21 Oct: was 7.5, inside the jump corridor; now 12.5 = just outside the kickflip_lane
# keep-clear half width), none within 10 m of Line 1 (each post trails a 6 m knee-high truss rail that collides)
LANE_POST_OFF = 12.5
lane = []
L2 = math.dist(fl[0], K)
for k in range(10):
    dd = L2 - 2.0 - k * 10.0
    if dd < 25.0:
        break
    q = off(K, U2 + 180, dd)
    pair = []
    for s_ in (-1, 1):
        p = off(q, U2 + 90 * s_, LANE_POST_OFF)
        rail_end = off(p, U2 + 180, 6.0)
        if min(seg_dist(p, start, ramp), seg_dist(rail_end, start, ramp)) < 10.0 or not inside(p, lot):
            break
        pair.append({"p": p, "yaw": round(U2 + 180, 1)})
    if len(pair) == 2:
        lane += pair

# ---- the stage (staging side of the red line), its screens, light masts, audience, riser, barricades, back-of-house
rl = heading(red[0], red[1])
n1 = rl + 90
face = H(STAGE["faces"]) if STAGE["faces"] is not None else (n1 if ts(ramp, stage_p, n1)[0] < 0 else n1 + 180)
face = (face + 180) % 360 - 180
ax = face - 90                                     # the stage's long axis (screens at either end)
SL, SD = STAGE["len"] * SCALE ** 0, STAGE["dep"]   # the deck is a real-size kit piece: it doesn't scale
items_stage = [{"p": stage_p, "yaw": round(face, 1)}]
# the LED screens past both ends of the deck (a low apron between: photo 05), turned IN toward the audience so each one
# faces across to the far side of the crowd (photo 05 from the right sees the left screen square on and the right one
# edge-on, photo 03 from the left the other way round; the night drone shows both facing the crowd). s_ = +1 is the
# audience's right (the end toward the Roadster building).
TOE = STAGE.get("screen_toe", 0.0)
# the kit screen is 12 x 6.75 m (16:9); the photos' screens read ~2.2:1, so they're stretched to 15 m wide
SW = STAGE.get("screen_w", 12.0)
screens = [{"p": off(off(stage_p, ax, s_ * (SL / 2 + 8.0)), face + 180, 1.0), "yaw": round(face + TOE * s_, 1),
            "scale": [1.0, round(SW / 12.0, 3), 1.0]} for s_ in (-1, 1)]
aud_c = off(stage_p, face, SD / 2 + 18.0)          # audience pen centre
# truss light masts just outboard of the screens, their lamp banks turned to the crowd (photos 03, 05, 08: the lamps and
# the red bottom row face the audience; the drone shot: a mast beside each screen)
masts = []
for s_ in (-1, 1):
    q = off(off(stage_p, ax, s_ * (SL / 2 + 18.0)), face, 3.0)
    masts.append({"p": q, "yaw": round(heading(q, aud_c), 1)})
# two more behind the audience, facing the stage (photos 06, 07), and the T mast in the middle of the crowd (drone shot)
masts += [{"p": off(off(aud_c, ax, s_ * 24.0), face, 14.0), "yaw": round(face + 180 - 25 * s_, 1)} for s_ in (-1, 1)]
if STAGE.get("tmast"):
    q = Ev(STAGE["tmast"])
    masts.append({"p": q, "yaw": round(heading(q, stage_p), 1)})
# camera risers: on Kenny's filled box (two side by side, facing the stage), else one behind the audience
if STAGE.get("risers"):
    rc = Ev(STAGE["risers"])
    ry_ = heading(rc, stage_p)
    riser = [{"p": off(rc, ry_ + 90, s_ * 3.5), "yaw": round(ry_, 1)} for s_ in (-1, 1)]
else:
    riser = [{"p": off(aud_c, face, 10.0), "yaw": round(face + 180, 1)}]
barricades = []
# the red line (back-of-house | performance): 2.5 m bays, kept off every lane and the fly-back
for q in along(red[0], red[1], 2.5):
    if clear_of(q["p"], 2.0) and inside(q["p"], lot):
        barricades.append({"p": q["p"], "yaw": round(q["yaw"] - 90, 1)})
# the audience pen: front rail 6 m off the deck edge, sides
pen_w = SL + 16.0
fr = off(stage_p, face, SD / 2 + 6.0)
for q in along(off(fr, ax, -pen_w / 2), off(fr, ax, pen_w / 2), 2.5):
    barricades.append({"p": q["p"], "yaw": round(face + 180, 1)})
for s_ in (-1, 1):
    a = off(fr, ax, s_ * pen_w / 2)
    for q in along(a, off(a, face, 30.0), 2.5):
        barricades.append({"p": q["p"], "yaw": round(ax + (0 if s_ > 0 else 180), 1)})
# hospitality: black umbrellas, high tables and lounge sofas on the asphalt behind the audience, toward the Roadster
# building (photo 04)
hosp_c = off(off(stage_p, face, STAGE.get("hospitality", (30.0, 58.0))[1]), ax, STAGE.get("hospitality", (30.0, 58.0))[0])
umbrellas, tables, sofas = [], [], []
for i in range(4):
    for j in range(3):
        c = off(off(hosp_c, ax, (i - 1.5) * 9.0), face, (j - 1) * 9.0)
        umbrellas.append({"p": c, "yaw": round(ax, 1)})
        tables.append({"p": off(c, ax, 2.2), "yaw": round(ax, 1)})
        sofas.append({"p": off(c, face, -2.4), "yaw": round(face + 180, 1)})
# back-of-house: the semi by the stage and the Roadster building (nav map 01), two production trailers. Behind the
# stage there are only ~10 m to the red line now, so they park along the Roadster building's side that faces the stage,
# 9 m off its wall, parallel to it
rb = BUILDINGS[0]
_nb = rb["bearing"] - 90 if ts(stage_p, rb["p"], rb["bearing"] - 90)[0] > 0 else rb["bearing"] + 90   # wall normal toward the stage
boh_c = off(off(rb["p"], _nb, rb["wid"] / 2 + 9.0), rb["bearing"], -12.0)    # S of the red line's end
boh = []
trailers = [{"p": off(off(boh_c, rb["bearing"], 8.0), _nb, k * 4.2), "yaw": round(rb["bearing"] + 180, 1)} for k in range(2)]
semi = [{"p": off(boh_c, rb["bearing"], -10.0), "yaw": round(rb["bearing"] + 180, 1)}]

# ---- the performance area: cranes with light rigs (photos 00 / 02), portable light towers, a show wall behind the ramp
left = travel - 90
right_of_ramp = 1 if ts(fleet_c, ramp, travel)[1] < 0 else -1          # the line-up's side of the run-up
cranes = [{"p": off(off(ramp, travel, 6.0), travel - 90 * right_of_ramp, 20.0)}]       # beside the ramp, away from the line-up
cranes[0]["yaw"] = round(heading(cranes[0]["p"], off(ramp, travel, -4.0)), 1)
# the far side of the performance area: along the lot edge opposite the stage. Cranes and light towers are laid out on
# the lot's edges as they were with the event on Kenny's marks, then move with the event (EVENT_OFFSET) like everything
# else in it, so the set keeps its shape; any that would leave the paved slab are dropped below
lot_ev = [[p[0] + EVENT_OFFSET[0], p[1] + EVENT_OFFSET[1]] for p in lot]
edges = [(lot_ev[i], lot_ev[(i + 1) % 4]) for i in range(4)]
far = max(edges, key=lambda e: math.dist(lerp(e[0], e[1], 0.5), stage_p))
cen = [sum(p[0] for p in lot_ev) / 4, sum(p[1] for p in lot_ev) / 4]
for t in (0.3, 0.5, 0.7, 0.9):
    q = lerp(far[0], far[1], t)
    p = off(q, heading(q, cen), 12.0)
    if clear_of(p, 6.0):
        cranes.append({"p": p, "yaw": round(heading(p, lerp(X_C, ramp, 0.5)), 1)})
towers = []
_edges0 = [(lot[i], lot[(i + 1) % 4]) for i in range(4)]
_cen0 = [sum(p[0] for p in lot) / 4, sum(p[1] for p in lot) / 4]
for t in (0.15, 0.5, 0.85):
    for e, e0 in zip(edges, _edges0):
        q = lerp(e[0], e[1], t)
        p = off(q, heading(q, cen), 6.0)
        if not inside(off(p, heading(p, cen), -2.0), lot_paved):     # moved with the event it would leave the slab:
            q = lerp(e0[0], e0[1], t)                                 # it stays at its spot on the lot's real edge
            p = off(q, heading(q, _cen0), 6.0)
        if clear_of(p, 4.0) and all(math.dist(p, c["p"]) > 20 for c in cranes + masts):
            towers.append({"p": p, "yaw": round(heading(p, cen), 1)})
W1 = off(off(ramp, travel, 30.0), left, 22.0)
W2 = off(off(ramp, travel, 30.0), left, -22.0)
walls = [w for w in along(W1, W2, 10.0) if clear_of(w["p"], 3.0) and clear_of(off(w["p"], heading(W1, W2), 5.0), 3.0)]
for w in walls:                                    # the LED face (mesh -X) looks back toward the ramp, seating behind
    w["yaw"] = round(w["yaw"] + 180.0, 1)


def building_ok(p, pad=3.0):
    for b in BUILDINGS:
        a, w = ts(p, b["p"], b["bearing"])
        if abs(a) < b["len"] / 2 + pad and abs(w) < b["wid"] / 2 + pad:
            return False
    return True


def keep(lst, pad=3.0, name=""):
    out_ = [q for q in lst if building_ok(q["p"], pad)]
    if len(out_) != len(lst):
        dropped.append(f"{name}: {len(lst) - len(out_)} inside a building")
    return out_


dropped = []
_n = (len(cranes), len(towers))
cranes = [c for c in cranes if inside(c["p"], lot_paved)]
towers = [q for q in towers if inside(q["p"], lot_paved)]
if (len(cranes), len(towers)) != _n:
    dropped.append(f"off the slab after the event move: {_n[0] - len(cranes)} cranes, {_n[1] - len(towers)} towers")
umbrellas, tables, sofas = keep(umbrellas, 2, "umbrellas"), keep(tables, 2, "tables"), keep(sofas, 2, "sofas")
trailers, semi = keep(trailers, 3, "trailers"), keep(semi, 3, "semi")
towers, cranes, masts = keep(towers, 4, "towers"), keep(cranes, 8, "cranes"), keep(masts, 3, "masts")

# ---- checks: nothing solid in the lanes
solid = {"stage": items_stage, "screens": screens, "masts": masts, "riser": riser, "trailers": trailers, "semi": semi,
         "cranes": cranes, "towers": towers, "walls": walls, "umbrellas": umbrellas, "barricades": barricades}
blocked = {k: [q["p"] for q in v if not clear_of(q["p"], 2.0, skip=("ramp",))] for k, v in solid.items()}
blocked = {k: v for k, v in blocked.items() if v}

# ---- the telephone-line check: where the mapped line crosses the run-up, and whether the landing falls under it
poles_check = {"line": "OSM way 435741101 (power=minor_line)" if POLES and POLES[0] == (1642.2, 535.2) else "POLES (edited)"}
cross = None
for a, b in zip(POLES, POLES[1:]):
    # start + u (ramp - start) = a + t (b - a)
    rx, ry, sx, sy = ramp[0] - start[0], ramp[1] - start[1], b[0] - a[0], b[1] - a[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-9:
        continue
    qx, qy = a[0] - start[0], a[1] - start[1]
    t = (qx * ry - qy * rx) / den
    u = (qx * sy - qy * sx) / den
    if 0 <= t <= 1 and -1.0 <= u <= 1.2:
        q = [a[0] + sx * t, a[1] + sy * t]
        back = ts(ramp, q, travel)[0]
        if back > 0:
            cross = {"at": [round(q[0], 1), round(q[1], 1)], "back_from_ramp_m": round(back, 1),
                     "poles": [list(a), list(b)], "nearest_pole_m": round(min(math.dist(q, a), math.dist(q, b)), 1)}
poles_check["crossing"] = cross
poles_check["landing_under_line"] = bool(cross and LANDING_BACK[0] <= cross["back_from_ramp_m"] <= LANDING_BACK[1])
poles_check["nearest_pole_to_X_m"] = round(min(math.dist(X_C, p) for p in POLES), 1)
# the correction that would put the middle of the landing zone under the wires 6 m beside each nearby pole (the pole on
# the same side as now, so the car never meets it; for Kenny's pinned pole:
# replace POLES with it, rerun, and copy the suggested OFFSET above)
mid_back = sum(LANDING_BACK) / 2
land = off(ramp, travel + 180, mid_back)
sugg = []
for p in sorted(POLES, key=lambda q: math.dist(q, land))[:3]:
    a_, l_ = ts(p, land, travel)
    l_ -= math.copysign(6.0, l_)
    sh = off(off([0.0, 0.0], travel, a_), travel - 90, l_)              # move everything by this (east, north)
    sugg.append({"pole": list(p), "pole_from_landing_m": round(math.dist(p, land), 1),
                 "offset_for_landing_beside_pole": [round(OFFSET[0] + sh[0], 1), round(OFFSET[1] + sh[1], 1)]})
poles_check["landing_mid"] = land
poles_check["suggestions"] = sugg

# ---- landing room past the line-up (round 2): straight along the jump to the slab's edge, and how far inside the slab
# the landing / run-out points are (25-75 m past the row, 35 m either side: the barrel roll carries the car sideways)
def _ray(p, b, poly):
    d = (math.sin(math.radians(b)), math.cos(math.radians(b)))
    best = None
    for i in range(len(poly)):
        a, c = poly[i], poly[(i + 1) % len(poly)]
        ex, ey = c[0] - a[0], c[1] - a[1]
        den = d[0] * ey - d[1] * ex
        if abs(den) < 1e-9:
            continue
        t = ((a[0] - p[0]) * ey - (a[1] - p[1]) * ex) / den
        s2 = ((a[0] - p[0]) * d[1] - (a[1] - p[1]) * d[0]) / den
        if t > 0 and 0 <= s2 <= 1:
            best = t if best is None else min(best, t)
    return best


def _edge(p, poly):
    return min(seg_dist(p, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))) * (1 if inside(p, poly) else -1)


landing = {"straight_runout_m": round(_ray(row_end, U2, lot_paved), 1),
           "straight_runout_yellow_lot_m": round(_ray(row_end, U2, lot), 1),
           "row_to_runup_line_m": round(min(seg_dist(v["p"], start, ramp) for v in lineup), 1),
           "points_inside_slab_m": {f"{a}m_past_{'R' if s_ > 0 else 'L' if s_ < 0 else 'C'}{abs(s_)}": round(_edge(off(off(row_end, U2, a), U2 + 90, s_), lot_paved), 1)
                                    for a in (25, 45, 75) for s_ in (-35, 0, 35)}}
layout = {
    "georef": GEOREF, "correction": {"scale": SCALE, "rotate": ROTATE, "offset": list(OFFSET)}, "event_offset": list(EVENT_OFFSET),
    "lot": lot, "ramp": {"p": ramp, "yaw": round(travel, 1)}, "start": {"p": start, "yaw": round(travel, 1)},
    "x_centre": X_C, "lane_heading": round(U2, 1), "lineup": lineup, "wall": [W1, W2],
    "red_line": red, "lines": {"runup": [start, ramp], "fleet": [fl[0], K]},
    "stage": {"p": stage_p, "yaw": round(face, 1), "len": SL, "dep": SD, "audience": aud_c, "hospitality": hosp_c, "back_of_house": boh_c},
    "keep_clear": CLEAR, "paint": paint,
    # the lot slab; "level": patches where build_mcgregor_ue.py holds the top dead level (the ramp's footprint, so its
    # toe meets the asphalt flush; round 1 sat the level ramp on the graded slope: the asphalt buried its toe on one
    # side by up to 5.6 cm and dropped away under its back), easing back into the graded surface around them
    "lot_paved": lot_paved, "fleet_landing": landing,
    "pads": [{"name": "UnveilLot", "ring": lot_paved, "mat": "lot", "raise": 0.3, "grade": "quad",
              "level": [{"name": "ramp", "p": ramp, "heading": round(travel, 2), "from": RAMP["level"][0], "to": RAMP["level"][1],
                         "half": RAMP["level"][2], "ease_r": 900.0}] if RAMP.get("level") else []}],
    "items": [
        {"mesh": "MG_Ramp", "collide": True, "at": [{"p": ramp, "yaw": round(travel, 1), "dz": RAMP.get("dz", 0.0)}]},
        {"mesh": "MG_RampTruss", "at": [{"p": ramp, "yaw": round(travel, 1), "dz": RAMP.get("dz", 0.0)}]},
        {"mesh": "MG_RampBlock", "collide": True, "hidden": True, "at": [{"p": ramp, "yaw": round(travel, 1), "dz": RAMP.get("dz", 0.0)}]},
        {"mesh": "MG_LanePost", "collide": True, "at": lane},
        {"mesh": "MG_ShowWall", "collide": True, "at": walls},
        {"mesh": "MG_LightTower", "at": towers},
        {"mesh": "UV_Stage", "collide": True, "at": items_stage},
        {"mesh": "UV_LEDScreen", "collide": True, "at": screens},
        {"mesh": "UV_LightMast", "at": masts},
        {"mesh": "UV_Riser", "collide": True, "at": riser},
        {"mesh": "UV_Barricade", "at": barricades},
        {"mesh": "UV_Umbrella", "at": umbrellas},
        {"mesh": "UV_HighTable", "at": tables},
        {"mesh": "UV_Sofa", "at": sofas},
        {"mesh": "UV_Trailer", "collide": True, "at": trailers},
        {"mesh": "MG_Veh_SemiCab", "collide": True, "at": semi},
        {"mesh": "UV_CraneBody", "collide": True, "at": cranes},
        {"mesh": "UV_CraneBoom", "at": cranes},
        # (the old gantry and flare stacks stood at Kenny's earlier overview pins, far from the real unveil: dropped)
    ],
    # the Roadster building (pickups / older scripts read this key) and both buildings
    "white_building": {"p": list(rb["p"]), "len": rb["len"], "wid": rb["wid"], "h": rb["h"], "yaw": rb["bearing"]},
    "buildings": [{"name": b["name"], "p": list(b["p"]), "len": b["len"], "wid": b["wid"], "h": b["h"], "yaw": b["bearing"]} for b in BUILDINGS],
    "poles_check": poles_check,
}
# ---- the fleet-jump corridor check (21 Oct, Kenny: "weird lights in the way of the fleet jump"): nothing placed here stands or
# glows within CORRIDOR_HALF m of the fleet line, from the run's start through the line-up and 135 m past the row (the
# landing and the whole run-out). The run-up's own LED ribbons cross the corridor at the X (Kenny's two lines cross there;
# flat on the ground) and the line-up cars are the row itself: both are listed, not counted.
_cor_a, _cor_b = fl[0], off(row_end, U2, 135.0)
_cor = {}
for _it in layout["items"]:
    _d = [round(seg_dist(a_["p"], _cor_a, _cor_b), 1) for a_ in _it["at"]]
    if _d:
        _cor[_it["mesh"]] = min(_d)
_led = [round(min(seg_dist(q_, _cor_a, _cor_b) for q_ in pt_["pts"]), 1) for pt_ in paint if pt_["mat"] == "led"]
layout["fleet_corridor"] = {"half_m": CORRIDOR_HALF, "from": list(_cor_a), "to": list(_cor_b),
                            "closest_item_m": dict(sorted(_cor.items(), key=lambda kv: kv[1])[:6]),
                            "led_ribbons_end_distance_m": _led, "lane_post_off_m": LANE_POST_OFF, "row_led_off_m": ROW_LED_OFF}
json.dump(layout, open(ROOT / "Saved/McGregor/demo_layout.json", "w"), indent=1)
print("ramp", layout["ramp"], "start", layout["start"], "run-up %.1f m" % math.dist(start, ramp), "X", X_C)
print("line-up row %.1f m along %.1f, facing %.1f; stage faces %.1f; lane posts %d; cranes %d; towers %d; wall %d; barricades %d"
      % (row_len, U2, FACE, face, len(lane), len(cranes), len(towers), len(walls), len(barricades)))
print("dropped:", dropped or "none", "| solid in lanes:", blocked or "none")
print("fleet landing room:", json.dumps(landing))
print("telephone line:", json.dumps(poles_check))
print("fleet corridor:", json.dumps(layout["fleet_corridor"]))
