"""Wall swatches for the facade kit: the wall of a windowed pack facade, without its windows.

Kit towers model their windows as geometry, so their walls need a wall-only
texture. Most pack families only ship windowed facade tiles. This cuts the
widest band of rows that is all wall (the mask's B channel, R is glass) out
of each tile, the spandrel between window rows, and stacks it with its mirror so
it tiles vertically (the facade tile already tiles horizontally). A tile with
no such band gives its widest all-wall column run instead (a pier), mirrored
sideways. A set with no mask (or a windowless set with no wall band) is
used whole.

Writes SourceArt/CityGen/kit/swatches/<set>_color.png and _rough.png (512 px
on the long side) and swatches.json: {set id: {color, rough, tile_m [w, h],
source: band | pier | whole}}. Paths in the json are relative to it.

Run (plain Python 3 with Pillow and NumPy):
  python3 -I Scripts/city/kit_swatches.py
Safe to rerun: the same packs give the same files.
"""
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import pack_slots  # noqa: E402
import packs  # noqa: E402
import skyline  # noqa: E402
import style_kit  # noqa: E402

WALL_MIN = 0.99      # share of wall pixels a row or column needs to count as all wall
EDGE_TRIM = 0.06     # trimmed off each end of a run: sills and frames bleed into its first rows
BAND_MIN = 0.06      # a band thinner than this share of the tile is not worth using
LONG_SIDE = 512


def wall_runs(wall, axis):
    """(start, length) of the longest run of rows (axis 1) or columns (axis 0) that are all wall."""
    share = wall.mean(axis=axis)
    best, start = (0, 0), None
    for index, ok in enumerate(list(share >= WALL_MIN) + [False]):
        if ok and start is None:
            start = index
        elif not ok and start is not None:
            if index - start > best[1]:
                best = (start, index - start)
            start = None
    trim = int(round(best[1] * EDGE_TRIM))
    return (best[0] + trim, max(0, best[1] - 2 * trim))


def cut(item):
    """{'color': array, 'rough': array or None, 'tile_m': [w, h], 'source': ...} or None."""
    maps = item.get("maps") or {}
    color_path = pack_slots._albedo(item)
    rough_path = pack_slots._resolve(item, maps.get("roughness"))
    mask_path = pack_slots._resolve(item, maps.get("mask") or item.get("glass_mask"))
    scale = item.get("scale_m") or {"width": 3.0, "height": 3.0}
    width_m, height_m = float(scale["width"]), float(scale["height"])
    color = np.asarray(Image.open(color_path).convert("RGB"))
    rough = np.asarray(Image.open(rough_path).convert("L")) if rough_path and rough_path.is_file() else None
    # "Windowless" sets can still paint boarded-up windows, so they are cut like the rest when they have a mask.
    if mask_path is None or not mask_path.is_file():
        return {"color": color, "rough": rough, "tile_m": [width_m, height_m], "source": "whole"}
    mask = np.asarray(Image.open(mask_path).convert("RGB")).astype(np.float32) / 255.0
    if mask.shape[:2] != color.shape[:2]:
        mask = np.asarray(Image.open(mask_path).convert("RGB").resize(color.shape[1::-1])).astype(np.float32) / 255.0
    # Wall, and neither glass nor frame (boarded openings are frame).
    wall = (mask[..., 2] > 0.5) & (mask[..., 0] < 0.5) & (mask[..., 1] < 0.5)
    rows, cols = color.shape[0], color.shape[1]
    start, length = wall_runs(wall, axis=1)
    if length >= BAND_MIN * rows:
        band = color[start:start + length]
        rband = rough[start:start + length] if rough is not None else None
        return {"color": np.concatenate([band, band[::-1]], axis=0),
                "rough": None if rband is None else np.concatenate([rband, rband[::-1]], axis=0),
                "tile_m": [width_m, 2.0 * length / rows * height_m], "source": "band"}
    start, length = wall_runs(wall, axis=0)
    if length >= BAND_MIN * cols:
        strip = color[:, start:start + length]
        rstrip = rough[:, start:start + length] if rough is not None else None
        return {"color": np.concatenate([strip, strip[:, ::-1]], axis=1),
                "rough": None if rstrip is None else np.concatenate([rstrip, rstrip[:, ::-1]], axis=1),
                "tile_m": [2.0 * length / cols * width_m, height_m], "source": "pier"}
    if item.get("windowless"):
        return {"color": color, "rough": rough, "tile_m": [width_m, height_m], "source": "whole"}
    return None


def _save(array, path):
    image = Image.fromarray(array)
    scale = LONG_SIDE / float(max(image.size))
    if scale < 1.0:
        image = image.resize((max(1, int(round(image.size[0] * scale))), max(1, int(round(image.size[1] * scale)))),
                             Image.LANCZOS)
    image.save(path, optimize=True)


def build(out_dir, library=None):
    library = library if library is not None else packs.load_library()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    record_path = out / "swatches.json"
    # Keep brick_swatches.py's own entries (source "generated"): the two scripts can run in
    # either order and neither drops the other's rows.
    record = {}
    if record_path.is_file():
        with open(record_path) as handle:
            record = {set_id: entry for set_id, entry in json.load(handle).items()
                      if entry.get("source") == "generated"}
    for set_id in style_kit.wall_sets(library):
        item = next(entry for entry in library["sets"] if entry["id"] == set_id)
        swatch = cut(item)
        if swatch is None:
            print("swatch", set_id, "no all-wall band or pier; skipped")
            continue
        entry = {"tile_m": [round(v, 4) for v in swatch["tile_m"]], "source": swatch["source"]}
        _save(swatch["color"], out / (set_id + "_color.png"))
        entry["color"] = set_id + "_color.png"
        if swatch["rough"] is not None:
            _save(swatch["rough"], out / (set_id + "_rough.png"))
            entry["rough"] = set_id + "_rough.png"
        record[set_id] = entry
        print("swatch", set_id, entry["source"], "tile", entry["tile_m"])
    (out / "swatches.json").write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
    return record


def main():
    root = skyline.project_root()
    build(root / "SourceArt" / "CityGen" / "kit" / "swatches")


if __name__ == "__main__":
    main()
