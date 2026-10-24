"""Brick and roof swatches for the facade kit: walkup.py's own wall and roof looks.

kit_swatches.py cuts wall-only tiles out of the AI texture packs; the walkup
kit (walkup.py) also wants plain Chicago brick and a flat membrane roof that
no pack ships, so this makes them procedurally (NumPy + Pillow, no network,
no AI). Running bond, 36 courses and 11 bricks per row across a 2.4 x 2.4 m
tile (brick + joint 0.218 x 0.0667 m), seeded so reruns match:

  brk_red, brk_brown, brk_buff, brk_cream  face brick: tight light mortar,
                                           per-brick tint noise, a few darker
                                           or lighter bricks, subtle
                                           low-frequency patchiness.
  brk_clinker                             dark, rougher, flashed face brick.
  brk_common                              Chicago common brick: salmon, tan
                                           and grey mixed, rougher, darker
                                           recessed mortar.
  roof_membrane                           dark grey roll roofing, seams every
                                           0.8 m (seamless at 2.4 m), a few
                                           patches and stains.

Writes SourceArt/CityGen/kit/swatches/<id>_color.png and <id>_rough.png
(1024 x 1024, tile_m [2.4, 2.4]) and merges {color, rough, source: "generated",
tile_m} into swatches.json there, without dropping kit_swatches.py's own
entries (it keeps anything already in the file whose source is not
"generated"; kit_swatches.py itself keeps entries whose source IS
"generated", so the two scripts can run in either order).

Run (plain Python 3 with Pillow and NumPy):
  python3 -I Scripts/city/brick_swatches.py
Safe to rerun: same seeds, same files. SKYCITY_ROOT overrides the project folder.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

SIZE = 1024
TILE_M = (2.4, 2.4)
BRICKS_PER_ROW = 11
COURSES = 36


def _root():
    env = os.environ.get("SKYCITY_ROOT")
    if env:
        return env
    d = _HERE
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "SkyCity.uproject")):
            return d
        d = os.path.dirname(d)
    raise SystemExit("SkyCity.uproject not found")


def _hash(seed, *vals):
    """0..1, deterministic from integer coordinates and a seed (vectorized, no RNG state)."""
    x = np.zeros_like(vals[0], dtype=np.float64) + float(seed) * 37.719
    for k, v in enumerate(vals):
        x = x + v.astype(np.float64) * (12.9898 + 17.233 * k) + 78.233 * k
    frac = np.sin(x) * 43758.5453
    return frac - np.floor(frac)


def _periodic_noise(width, height, seed, terms=4, amp=1.0):
    """Smooth noise that tiles exactly: a sum of sine waves at integer tile frequencies."""
    yy, xx = np.meshgrid(np.arange(height), np.arange(width), indexing="ij")
    out = np.zeros((height, width), dtype=np.float64)
    rng_seed = seed
    for k in range(terms):
        fx = (int(_hash(rng_seed, np.array([k]), np.array([0]))[0] * 3) + 1)
        fy = (int(_hash(rng_seed, np.array([k]), np.array([1]))[0] * 3) + 1)
        phase = _hash(rng_seed, np.array([k]), np.array([2]))[0] * 2 * np.pi
        out += np.sin(2 * np.pi * fx * xx / width + 2 * np.pi * fy * yy / height + phase)
    out /= terms
    return out * amp


def _brick_grid(width, height, bricks_per_row=BRICKS_PER_ROW, courses=COURSES):
    """row, col (int grids), and the fractional position within each brick cell (u, v)."""
    yy, xx = np.meshgrid(np.arange(height), np.arange(width), indexing="ij")
    course_h = height / float(courses)
    brick_w = width / float(bricks_per_row)
    row = np.floor(yy / course_h).astype(np.int64)
    shift = (row % 2) * (brick_w / 2.0)
    xs = (xx + shift) % width
    col = np.floor(xs / brick_w).astype(np.int64)
    u = (xs % brick_w) / brick_w
    v = (yy % course_h) / course_h
    return row, col, u, v


def _face_brick(seed, base_rgb, mortar_rgb, rough_brick, rough_mortar, h_joint=0.05, v_joint=0.15,
                 variant_strength=0.10, outlier_share=0.06):
    """A face-brick tile: tight mortar, per-brick tint, a few outlier bricks, soft patchiness."""
    row, col, u, v = _brick_grid(SIZE, SIZE)
    is_mortar = (u < h_joint) | (v < v_joint)
    tint = (_hash(seed, row, col) - 0.5) * 2.0 * variant_strength
    lo = _hash(seed + 1, row, col) < outlier_share * 0.5
    hi = _hash(seed + 2, row, col) < outlier_share * 0.5
    tint = np.where(lo, tint - 0.28, tint)
    tint = np.where(hi, tint + 0.22, tint)
    patch = _periodic_noise(SIZE, SIZE, seed + 3, terms=3, amp=0.05)
    brick_fleck = (_hash(seed + 4, row, col) - 0.5) * 0.04
    factor = 1.0 + tint + patch + brick_fleck
    color = np.empty((SIZE, SIZE, 3), dtype=np.float64)
    for c in range(3):
        color[..., c] = np.clip(base_rgb[c] * factor, 0, 255)
    mortar_noise = 1.0 + (_hash(seed + 5, row, col) - 0.5) * 0.08
    for c in range(3):
        color[..., c] = np.where(is_mortar, np.clip(mortar_rgb[c] * mortar_noise, 0, 255), color[..., c])
    rough = np.where(is_mortar, rough_mortar, rough_brick)
    rough = rough + (_hash(seed + 6, row, col) - 0.5) * 0.06
    rough = np.clip(rough, 0.0, 1.0) * 255.0
    return color.astype(np.uint8), rough.astype(np.uint8)


def _common_brick(seed):
    """Chicago common: salmon, tan and grey bricks mixed, rougher, darker recessed mortar."""
    row, col, u, v = _brick_grid(SIZE, SIZE)
    h_joint, v_joint = 0.07, 0.18
    is_mortar = (u < h_joint) | (v < v_joint)
    palette = np.array([(196, 140, 112), (186, 150, 108), (150, 142, 132)], dtype=np.float64)
    pick = (_hash(seed, row, col) * len(palette)).astype(np.int64) % len(palette)
    base = palette[pick]
    tint = 1.0 + (_hash(seed + 1, row, col) - 0.5) * 0.16
    patch = _periodic_noise(SIZE, SIZE, seed + 2, terms=3, amp=0.07)
    surface = (_hash(seed + 7, (col * 997 + row) % 4001, row) - 0.5) * 18.0  # rougher surface fleck
    color = np.clip(base * (tint[..., None] + patch[..., None]) + surface[..., None], 0, 255)
    mortar_rgb = np.array([58.0, 54.0, 50.0])  # darker, recessed
    mortar_noise = 1.0 + (_hash(seed + 3, row, col) - 0.5) * 0.10
    color = np.where(is_mortar[..., None], np.clip(mortar_rgb * mortar_noise[..., None], 0, 255), color)
    rough = np.where(is_mortar, 0.92, 0.78) + (_hash(seed + 4, row, col) - 0.5) * 0.08
    rough = np.clip(rough, 0.0, 1.0) * 255.0
    return color.astype(np.uint8), rough.astype(np.uint8)


def _roof_membrane(seed):
    """Dark grey roll roofing: seams every 0.8 m (ties the 2.4 m tile seamlessly), patches, stains."""
    yy, xx = np.meshgrid(np.arange(SIZE), np.arange(SIZE), indexing="ij")
    base = np.array([42.0, 41.0, 40.0])
    seam_period = SIZE / 3.0  # 0.8 m at a 2.4 m tile
    seam_phase = yy % seam_period
    seam = (seam_phase < 2.0) | (seam_phase > seam_period - 2.0)
    noise = _periodic_noise(SIZE, SIZE, seed, terms=5, amp=0.08)
    fine = (_hash(seed + 1, xx // 3, yy // 3) - 0.5) * 0.05
    factor = 1.0 + noise + fine
    color = np.empty((SIZE, SIZE, 3), dtype=np.float64)
    for c in range(3):
        color[..., c] = np.clip(base[c] * factor, 0, 255)
    color = np.where(seam[..., None], color * 0.55, color)
    # A handful of toroidal patches and stains so it reads as a real roof, not a swatch.
    rng_count = 5
    for k in range(rng_count):
        cx = _hash(seed + 10 + k, np.array([k]), np.array([1]))[0] * SIZE
        cy = _hash(seed + 10 + k, np.array([k]), np.array([2]))[0] * SIZE
        radius = 40 + 70 * _hash(seed + 10 + k, np.array([k]), np.array([3]))[0]
        dx = np.minimum(np.abs(xx - cx), SIZE - np.abs(xx - cx))
        dy = np.minimum(np.abs(yy - cy), SIZE - np.abs(yy - cy))
        dist = np.sqrt(dx * dx + dy * dy)
        mask = np.clip(1.0 - dist / radius, 0.0, 1.0) ** 2
        darker = _hash(seed + 20 + k, np.array([k]), np.array([4]))[0] < 0.6
        shade = 0.72 if darker else 1.18
        color = color * (1.0 - mask[..., None] * 0.5) + color * shade * (mask[..., None] * 0.5)
    rough = np.full((SIZE, SIZE), 0.82) + (_hash(seed + 30, xx // 2, yy // 2) - 0.5) * 0.10
    rough = np.where(seam, np.clip(rough + 0.08, 0, 1), rough)
    rough = np.clip(rough, 0.0, 1.0) * 255.0
    return np.clip(color, 0, 255).astype(np.uint8), rough.astype(np.uint8)


# id -> builder. mortar_rgb is light / tight for face brick per the brief.
FACE_BRICKS = {
    "brk_red": lambda seed: _face_brick(seed, (150, 58, 46), (196, 190, 178), 0.62, 0.88),
    "brk_brown": lambda seed: _face_brick(seed, (120, 78, 58), (188, 182, 170), 0.64, 0.88),
    "brk_buff": lambda seed: _face_brick(seed, (196, 168, 128), (206, 200, 188), 0.58, 0.85),
    "brk_cream": lambda seed: _face_brick(seed, (218, 204, 176), (214, 208, 196), 0.55, 0.85),
    "brk_clinker": lambda seed: _face_brick(seed, (72, 46, 42), (150, 144, 136), 0.72, 0.9,
                                            variant_strength=0.16, outlier_share=0.12),
}


def build(out_dir, seed=401):
    out_dir = str(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    record_path = os.path.join(out_dir, "swatches.json")
    record = {}
    if os.path.isfile(record_path):
        with open(record_path) as handle:
            record = json.load(handle)
    made = {}
    for index, (set_id, builder) in enumerate(sorted(FACE_BRICKS.items())):
        color, rough = builder(seed + index * 17)
        made[set_id] = (color, rough)
    made["brk_common"] = _common_brick(seed + 900)
    made["roof_membrane"] = _roof_membrane(seed + 950)
    for set_id, (color, rough) in sorted(made.items()):
        Image.fromarray(color, "RGB").save(os.path.join(out_dir, set_id + "_color.png"), optimize=True)
        Image.fromarray(rough, "L").save(os.path.join(out_dir, set_id + "_rough.png"), optimize=True)
        record[set_id] = {"color": set_id + "_color.png", "rough": set_id + "_rough.png",
                          "source": "generated", "tile_m": list(TILE_M)}
        print("brick swatch", set_id, "tile", list(TILE_M))
    with open(record_path, "w") as handle:
        json.dump(record, handle, indent=1, sort_keys=True)
        handle.write("\n")
    return record


def main():
    build(os.path.join(_root(), "SourceArt", "CityGen", "kit", "swatches"))


if __name__ == "__main__":
    main()
