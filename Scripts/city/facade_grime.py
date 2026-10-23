"""Facade grime intensity and the masks the two materials share.

District age and income tier already land on a building as ``wear``
(skyline.yaml, then the tier overlay in skyline.for_lot). 0 is a clean wall
and 1 is heavy. brand_new and tech are near zero. historic_old and a
distressed tier are heavy. When a spec has no wear number, the district
type, the tier, then the grammar style fill in, in that order.

The stains themselves are not a photo and not a card:

- Edges and corners come from curvature. The Blender preview compares a
  short bevel's normal to the face normal, because Pointiness stays flat on
  the big facade quads. Unreal uses the screen-space derivative of the
  pixel normal, plus precomputed AO where a lightmap has it.
- Drips are vertical, world-aligned, and broken up by noise. A drip peaks
  just under the sill line of a typical floor and again under the ledge at
  the top of the floor, then fades downward. AC units hang in the sill
  band, so the same streaks fall under them.
- Dirt gathers on the bottom of the wall, from the sidewalk up to about
  1.4 m, and a little noise keeps that band from being a hard line.

Both materials multiply every mask by the wear value. Wear 0 leaves the
scan alone. The Blender preview reads wear from the mesh colour attribute
(red). The Unreal master reads vertex colour red, times the WearScale
parameter. Unreal world positions are centimetres; divide by UE_CM before
using the metre constants below.

Run the checks with python3 -I Scripts/city/test_facade_grime.py.
"""


# Wall slots that take the procedural facade. Roads, grass and paving do not.
WALL_SLOTS = ("brick", "concrete", "plaster", "metal")
FACADE_MATERIALS = ("M_Brick", "M_Concrete", "M_Plaster", "M_Metal")

# Metres. Matches skyline.yaml defaults.floor_height_m and the sidewalk.
FLOOR_H = 3.4
GROUND_Z = 0.15
BASE_Z0 = 0.15
BASE_Z1 = 1.40

# Fraction of a floor. The sill band fades downward. The ledge band fades
# down from the top of the floor. The gap between them is the glass.
SILL_PEAK = 0.42
SILL_FADE = 0.28
LEDGE_PEAK = 0.96
LEDGE_FADE = 0.22

# Bevel-normal distance. A face centre is 0. A corner rises toward 1.
# Pointiness does not: on one quad per wall it sits near 0.7 everywhere.
EDGE_LO = 0.02
EDGE_HI = 0.40
BEVEL_RADIUS = 0.03
BEVEL_SAMPLES = 2

# World-space noise. Column scale is per metre in XY so a streak holds its
# value down the wall. Break scale stretches Z so the streak is interrupted.
# The column window leaves most of a bay clean. Columns that pass it are
# wide enough, and dark enough, to read on a busy brick scan.
COLUMN_SCALE = 1.7
COLUMN_LO = 0.52
COLUMN_HI = 0.68
BREAK_SCALE = (0.55, 0.55, 2.6)
BREAK_LO = 0.55
BREAK_HI = 1.0
BASE_NOISE = 2.2
# The base band is a tide, not a hole pattern. Noise only frays it.
BASE_NOISE_LO = 0.85
BASE_NOISE_HI = 1.0
# A streak core, times wear, reaches full soot. The height band and the
# column noise still decide where that happens.
DRIP_GAIN = 2.4
# Flat bays still streak. Edges pick up a little more.
CLING_FLOOR = 0.85
CLING_EDGE = 0.15
CORNER_WEIGHT = 0.85
CHIP_GAIN = 0.55

# AO sample used by the Blender preview. A few rays, this object only.
AO_DISTANCE = 0.4
AO_SAMPLES = 4

# Unreal curvature is the squared screen derivative of the normal. This gain
# brings a hard edge up into the 0-1 mask. It is view-dependent on purpose:
# there is no curvature bake and no paid node.
CURVE_GAIN = 25.0

# Soot multiplied onto the scan, and the lighter chip on worn edges.
# Dark enough that a distressed base reads against the brick. Wear near
# zero barely mixes it in.
SOOT = (0.08, 0.07, 0.06, 1.0)
CHIP = (0.86, 0.82, 0.74, 1.0)

# Unreal units per metre. glTF import is centimetres.
UE_CM = 100.0

# Fallbacks when a spec has no wear field. District numbers match skyline.yaml.
# Tier numbers match the houses income tiers (distressed heaviest, high near zero).
# Styles cover the block-study previews, which are not typed districts.
TYPE_WEAR = {
    "brand_new": 0.05,
    "historic_old": 0.75,
    "eclectic_mix": 0.45,
    "tech": 0.08,
    "green_renewable": 0.15,
    "houses": 0.35,
    "apartments_condos": 0.20,
    "industrial_commercial": 0.55,
    "utilities": 0.40,
}
TIER_WEAR = {
    "high": 0.05,
    "mid": 0.28,
    "low": 0.62,
    "distressed": 0.90,
}
STYLE_WEAR = {
    "glass_curtain": 0.06,
    "modern_mixed": 0.08,
    "prewar_masonry": 0.75,
    "art_deco": 0.60,
    "brick_walkup": 0.45,
    "texas_lowrise": 0.35,
    "industrial": 0.55,
}


def intensity(spec):
    """0 to 1. An explicit wear wins. Otherwise tier, district type, then style."""
    spec = spec or {}
    if spec.get("wear") is not None:
        return _clamp(spec.get("wear"))
    tier = spec.get("tier") or ""
    if tier in TIER_WEAR:
        return TIER_WEAR[tier]
    dtype = spec.get("district_type") or ""
    if dtype in TYPE_WEAR:
        return TYPE_WEAR[dtype]
    style = spec.get("style") or ""
    if style in STYLE_WEAR:
        return STYLE_WEAR[style]
    return 0.35


def floor_phase(z, floor_h=FLOOR_H, ground=GROUND_Z):
    """0 at the sidewalk (and each floor up), 1 at the next floor."""
    if floor_h <= 0.0:
        return 0.0
    rel = (float(z) - ground) / floor_h
    return rel - _floor(rel)


def drip_weight(z, floor_h=FLOOR_H, ground=GROUND_Z):
    """1 just under a sill or a ledge, fading downward. 0 across the glass."""
    phase = floor_phase(z, floor_h, ground)
    sill = _band(phase, SILL_PEAK, SILL_FADE)
    ledge = _band(phase, LEDGE_PEAK, LEDGE_FADE)
    if sill > ledge:
        return sill
    return ledge


def base_weight(z, z0=BASE_Z0, z1=BASE_Z1):
    """1 at the sidewalk, 0 at z1 and above."""
    span = z1 - z0
    if span <= 0.0:
        return 0.0
    weight = (z1 - float(z)) / span
    return _clamp(weight)


def _band(phase, peak, fade):
    """1 at `peak`, 0 `fade` below it, 0 above it. Linear, matching the shader."""
    raw = peak - phase
    gate = raw + 0.001
    if gate <= 0.0:
        gate = 0.0
    elif gate >= 0.001:
        gate = 1.0
    else:
        gate = gate / 0.001
    if fade <= 0.0:
        fall = 1.0
    else:
        fall = (fade - raw) / fade
        fall = _clamp(fall)
    return gate * fall


def _clamp(value):
    value = float(value)
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _floor(value):
    # math.floor without importing math at the call sites that only need this.
    import math
    return math.floor(value)
