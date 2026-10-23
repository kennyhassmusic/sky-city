"""Plan renders of stage-1 street dressing. No Blender and no Pillow.

Builds the loop block through the city generator (import only; this does not
run Scripts/city/block.py, which writes example files) and draws the street
surfaces, paint and props.

Run: python3 -I Scripts/roads/preview_dressing.py
Writes (not committed):
  /opt/cursor/artifacts/previews/street_dressing_plan.png
  /opt/cursor/artifacts/previews/street_dressing_corners.png
"""
import os
import sys
from pathlib import Path

CITY = Path(__file__).resolve().parents[1] / "city"
ROADS = Path(__file__).resolve().parent
sys.path.insert(0, str(CITY))
sys.path.insert(0, str(ROADS))

import block  # noqa: E402
import geom  # noqa: E402
import model as model_mod  # noqa: E402
import pngutil  # noqa: E402

OUT = Path("/opt/cursor/artifacts/previews")

# 5x7 glyphs, five bits per row, high bit on the left.
_FONT = {
    "A": (0b01110, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001),
    "B": (0b11110, 0b10001, 0b10001, 0b11110, 0b10001, 0b10001, 0b11110),
    "C": (0b01110, 0b10001, 0b10000, 0b10000, 0b10000, 0b10001, 0b01110),
    "D": (0b11110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b11110),
    "E": (0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b11111),
    "G": (0b01110, 0b10001, 0b10000, 0b10111, 0b10001, 0b10001, 0b01110),
    "H": (0b10001, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001),
    "I": (0b01110, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110),
    "K": (0b10001, 0b10010, 0b10100, 0b11000, 0b10100, 0b10010, 0b10001),
    "L": (0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b11111),
    "M": (0b10001, 0b11011, 0b10101, 0b10101, 0b10001, 0b10001, 0b10001),
    "N": (0b10001, 0b11001, 0b10101, 0b10011, 0b10001, 0b10001, 0b10001),
    "O": (0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110),
    "P": (0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000, 0b10000),
    "R": (0b11110, 0b10001, 0b10001, 0b11110, 0b10100, 0b10010, 0b10001),
    "S": (0b01111, 0b10000, 0b10000, 0b01110, 0b00001, 0b00001, 0b11110),
    "T": (0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100),
    "U": (0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110),
    "W": (0b10001, 0b10001, 0b10001, 0b10101, 0b10101, 0b10101, 0b01010),
    "Y": (0b10001, 0b10001, 0b01010, 0b00100, 0b00100, 0b00100, 0b00100),
    " ": (0, 0, 0, 0, 0, 0, 0),
    "-": (0, 0, 0, 0b01110, 0, 0, 0),
}

_PROP = {
    "lamp": (232, 196, 92),
    "signal": (196, 48, 42),
    "stop": (176, 32, 36),
    "yield": (214, 176, 48),
    "street_name": (36, 120, 86),
    "bus_stop": (48, 96, 176),
    "parked": (70, 96, 124),
    "hydrant": (196, 92, 42),
    "bench": (132, 92, 58),
    "bin": (58, 92, 72),
    "tree": (46, 112, 58),
    "sign": (150, 86, 140),
    "grate": (90, 92, 94),
    "drain": (70, 78, 86),
    "weed": (72, 104, 52),
    "bollard": (160, 160, 164),
}


def main():
    city = block.build_sample()
    again = block.build_sample()
    digest = model_mod.manifest_hash(city)
    if digest != model_mod.manifest_hash(again):
        raise SystemExit("sample hash changed between two builds")
    sc = city["streetscape"]
    OUT.mkdir(parents=True, exist_ok=True)
    plan = OUT / "street_dressing_plan.png"
    corners = OUT / "street_dressing_corners.png"
    _plan(sc, plan, ppm=14)
    _corners(sc, corners, ppm=22)
    kinds = {}
    for prop in sc["props"]:
        kinds[prop["kind"]] = kinds.get(prop["kind"], 0) + 1
    marks = {}
    for mark in sc["markings"]:
        marks[mark["kind"]] = marks.get(mark["kind"], 0) + 1
    print("hash", digest)
    print("props", " ".join("%s=%d" % (k, kinds[k]) for k in sorted(kinds)))
    print("marks", " ".join("%s=%d" % (k, marks[k]) for k in sorted(marks)))
    print("wear", sc["markings"][0].get("wear") if sc["markings"] else None)
    print("wrote", plan)
    print("wrote", corners)


def _plan(sc, path, ppm):
    bounds = _bounds(sc)
    pad = 6.0
    x0, y0, x1, y1 = bounds[0] - pad, bounds[1] - pad, bounds[2] + pad, bounds[3] + pad
    width = int((x1 - x0) * ppm)
    height = int((y1 - y0) * ppm)
    buf = bytearray([34, 36, 38]) * (width * height)
    _paint_scene(buf, width, height, sc, x0, y1, ppm, props=True)
    pngutil.write_rgb(str(path), width, height, buf)


def _corners(sc, path, ppm):
    # SW signals, SE through-road, NE stop, NW yield. Each window is the corner.
    panels = (
        ((-78, -62, -42, -28), "SW SIGNALS"),
        ((42, -62, 78, -28), "SE NAMES"),
        ((42, 28, 78, 62), "NE STOP"),
        ((-78, 28, -42, 62), "NW YIELD"),
    )
    cell_w = int(36 * ppm)
    cell_h = int(34 * ppm)
    gap = 8
    legend_h = 36
    width = cell_w * 2 + gap * 3
    height = cell_h * 2 + gap * 3 + legend_h
    buf = bytearray([22, 24, 26]) * (width * height)
    for index, (box, title) in enumerate(panels):
        col = index % 2
        row = index // 2
        ox = gap + col * (cell_w + gap)
        oy = gap + row * (cell_h + gap)
        _blit_window(buf, width, height, sc, box, ox, oy, cell_w, cell_h, ppm)
        _text(buf, width, height, ox + 8, oy + 8, title, (236, 232, 220), 2)
    _legend(buf, width, height, gap, height - legend_h + 6)
    pngutil.write_rgb(str(path), width, height, buf)


def _blit_window(buf, width, height, sc, box, ox, oy, cell_w, cell_h, ppm):
    x0, y0, x1, y1 = box
    scratch_w = int((x1 - x0) * ppm)
    scratch_h = int((y1 - y0) * ppm)
    scratch = bytearray([34, 36, 38]) * (scratch_w * scratch_h)
    _paint_scene(scratch, scratch_w, scratch_h, sc, x0, y1, ppm, props=True, clip=box)
    for y in range(min(cell_h, scratch_h, height - oy)):
        for x in range(min(cell_w, scratch_w, width - ox)):
            s = (y * scratch_w + x) * 3
            d = ((oy + y) * width + (ox + x)) * 3
            buf[d:d + 3] = scratch[s:s + 3]


def _paint_scene(buf, width, height, sc, origin_x, origin_y, ppm, props, clip=None):
    surfaces = sc.get("surfaces") or {}
    for kind, colour in (
        ("parkway", (62, 104, 58)),
        ("sidewalk", (156, 152, 144)),
        ("gutter", (58, 60, 62)),
        ("asphalt", (52, 54, 56)),
    ):
        for poly in surfaces.get(kind) or []:
            _fill(buf, width, height, poly.get("polygon") or [], colour, origin_x, origin_y, ppm, clip)
    for curb in sc.get("curb_paths") or []:
        _stroke(buf, width, height, curb.get("polyline") or [], (176, 172, 164), origin_x, origin_y, ppm, 1.6, clip)
    for cross in sc.get("crosswalks") or []:
        for mark in cross.get("marks") or []:
            _fill(buf, width, height, mark.get("polygon") or [], (228, 226, 218), origin_x, origin_y, ppm, clip)
    for mark in sc.get("markings") or []:
        colour = _mark_colour(mark)
        _fill(buf, width, height, mark.get("polygon") or [], colour, origin_x, origin_y, ppm, clip)
    if props:
        for prop in sc.get("props") or []:
            _prop(buf, width, height, prop, origin_x, origin_y, ppm, clip)


def _mark_colour(mark):
    wear = float(mark.get("wear") or 0.0)
    yellow = mark.get("material") == "M_LanePaintYellow" or mark.get("kind") in ("centre", "keep_clear")
    base = (232, 186, 46) if yellow else (236, 234, 226)
    if mark.get("kind") in ("manhole",):
        base = (78, 80, 84)
    if mark.get("kind") == "puddle":
        base = (42, 52, 62)
    asphalt = (52, 54, 56)
    fade = min(0.72, wear * 0.85)
    return tuple(int(base[i] * (1.0 - fade) + asphalt[i] * fade) for i in range(3))


def _prop(buf, width, height, prop, origin_x, origin_y, ppm, clip):
    kind = prop.get("kind")
    colour = _PROP.get(kind, (200, 200, 200))
    x, y = float(prop["x"]), float(prop["y"])
    if clip and not (clip[0] <= x <= clip[2] and clip[1] <= y <= clip[3]):
        return
    if kind == "parked":
        yaw = float(prop.get("yaw") or 0.0) * 3.14159265 / 180.0
        import math
        tangent = (math.cos(yaw), math.sin(yaw))
        _fill(buf, width, height, _rect((x, y), tangent, 4.3, 1.75), colour, origin_x, origin_y, ppm, clip)
        return
    radius = 1.15 if kind in ("signal", "stop", "yield", "bus_stop", "street_name") else 0.7
    if kind == "lamp":
        radius = 0.85
    _disc(buf, width, height, x, y, radius, colour, origin_x, origin_y, ppm)


def _legend(buf, width, height, x, y):
    items = (
        ((232, 186, 46), "YELLOW"),
        ((236, 234, 226), "WHITE"),
        ((196, 48, 42), "SIGNAL"),
        ((176, 32, 36), "STOP"),
        ((214, 176, 48), "YIELD"),
        ((36, 120, 86), "NAME"),
        ((48, 96, 176), "BUS"),
        ((70, 96, 124), "PARKED"),
        ((232, 196, 92), "LAMP"),
    )
    cursor = x
    for colour, label in items:
        if cursor + 90 > width:
            break
        _fill_px(buf, width, height, cursor, y + 2, cursor + 14, y + 16, colour)
        _text(buf, width, height, cursor + 18, y, label, (220, 218, 210), 1)
        cursor += 18 + len(label) * 6 + 14


def _fill(buf, width, height, poly, colour, origin_x, origin_y, ppm, clip):
    pts = [(float(p[0]), float(p[1])) for p in poly]
    if len(pts) < 3:
        return
    if clip and not _overlaps(pts, clip):
        return
    pix = [((p[0] - origin_x) * ppm, (origin_y - p[1]) * ppm) for p in pts]
    ys = [p[1] for p in pix]
    y0 = max(0, int(min(ys)))
    y1 = min(height - 1, int(max(ys)) + 1)
    n = len(pix)
    for y in range(y0, y1 + 1):
        scan = y + 0.5
        xs = []
        for i in range(n):
            ax, ay = pix[i]
            bx, by = pix[(i + 1) % n]
            if (ay > scan) == (by > scan):
                continue
            t = (scan - ay) / ((by - ay) or 1e-9)
            xs.append(ax + (bx - ax) * t)
        xs.sort()
        row = y * width
        for i in range(0, len(xs) - 1, 2):
            x_start = max(0, int(xs[i]))
            x_end = min(width - 1, int(xs[i + 1]))
            for x in range(x_start, x_end + 1):
                i3 = (row + x) * 3
                buf[i3] = colour[0]
                buf[i3 + 1] = colour[1]
                buf[i3 + 2] = colour[2]


def _stroke(buf, width, height, polyline, colour, origin_x, origin_y, ppm, radius_px, clip):
    pts = [(float(p[0]), float(p[1])) for p in polyline]
    if len(pts) < 2:
        return
    step = 0.35
    for a, b in zip(pts, pts[1:]):
        length = geom.dist(a, b)
        n = max(1, int(length / step))
        for i in range(n + 1):
            t = i / n
            x = a[0] + (b[0] - a[0]) * t
            y = a[1] + (b[1] - a[1]) * t
            if clip and not (clip[0] - 1 <= x <= clip[2] + 1 and clip[1] - 1 <= y <= clip[3] + 1):
                continue
            _disc(buf, width, height, x, y, radius_px / ppm, colour, origin_x, origin_y, ppm)


def _disc(buf, width, height, wx, wy, radius_m, colour, origin_x, origin_y, ppm):
    cx = (wx - origin_x) * ppm
    cy = (origin_y - wy) * ppm
    r = max(1.2, radius_m * ppm)
    x0 = max(0, int(cx - r))
    x1 = min(width - 1, int(cx + r) + 1)
    y0 = max(0, int(cy - r))
    y1 = min(height - 1, int(cy + r) + 1)
    r2 = r * r
    for y in range(y0, y1 + 1):
        dy = y + 0.5 - cy
        row = y * width
        for x in range(x0, x1 + 1):
            dx = x + 0.5 - cx
            if dx * dx + dy * dy <= r2:
                i3 = (row + x) * 3
                buf[i3] = colour[0]
                buf[i3 + 1] = colour[1]
                buf[i3 + 2] = colour[2]


def _fill_px(buf, width, height, x0, y0, x1, y1, colour):
    for y in range(max(0, y0), min(height, y1)):
        row = y * width
        for x in range(max(0, x0), min(width, x1)):
            i3 = (row + x) * 3
            buf[i3] = colour[0]
            buf[i3 + 1] = colour[1]
            buf[i3 + 2] = colour[2]


def _text(buf, width, height, x, y, text, colour, scale):
    cursor = x
    for ch in text:
        glyph = _FONT.get(ch, _FONT[" "])
        for row, bits in enumerate(glyph):
            for col in range(5):
                if bits & (1 << (4 - col)):
                    _fill_px(
                        buf, width, height,
                        cursor + col * scale, y + row * scale,
                        cursor + (col + 1) * scale, y + (row + 1) * scale,
                        colour,
                    )
        cursor += 6 * scale


def _rect(centre, tangent, along, across):
    length = geom.hypot(tangent) or 1.0
    tx, ty = tangent[0] / length, tangent[1] / length
    nx, ny = -ty, tx
    ha, hc = along / 2.0, across / 2.0
    pts = []
    for sa, sc in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        pts.append((
            centre[0] + tx * sa * ha + nx * sc * hc,
            centre[1] + ty * sa * ha + ny * sc * hc,
        ))
    return pts


def _bounds(sc):
    xs, ys = [], []
    for kind in ("asphalt", "sidewalk", "parkway", "gutter"):
        for poly in (sc.get("surfaces") or {}).get(kind) or []:
            for p in poly.get("polygon") or []:
                xs.append(float(p[0]))
                ys.append(float(p[1]))
    if not xs:
        return (-80.0, -60.0, 80.0, 60.0)
    return (min(xs), min(ys), max(xs), max(ys))


def _overlaps(pts, clip):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return not (max(xs) < clip[0] or min(xs) > clip[2] or max(ys) < clip[1] or min(ys) > clip[3])


if __name__ == "__main__":
    main()
