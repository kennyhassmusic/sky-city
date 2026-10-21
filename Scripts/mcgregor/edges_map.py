"""Map of the McGregor edge survey (mcgregor-edges, 20 Oct 2026): every sampled road / lot / pad / kit edge as a dot on
the aerial photo, coloured by its step (the vertical discontinuity across the edge the car meets).
  grey < 3 cm (fine)   yellow 3-10   orange 10-20   red 20-52   magenta > 52 cm (the car's body hits it)
Reads Saved/McGregor/edges/survey_<tag>.json (edges_survey_ue.py). Writes Saved/McGregor/edges/map_<tag>_<view>.jpg
for the views: whole (the 9.6 x 7.2 km map), site (the test stands, offices and lots), unveil (the unveil lot).
Run: python3 -I Scripts/mcgregor/edges_map.py <tag> [view ...]
"""
import json, os, pathlib, sys
from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAS = pathlib.Path(os.environ.get("SKYCITY_MCGREGOR_RAW", ROOT / "Saved" / "McGregorRaw"))
META = json.load(open(RAS / "rasters.json"))
TAG = sys.argv[1] if len(sys.argv) > 1 else "before"
VIEWS = sys.argv[2:] or ["whole", "site", "unveil"]
S = json.load(open(ROOT / f"Saved/McGregor/edges/survey_{TAG}.json"))
BOX = {"whole": (-4800, -3600, 4800, 3600, 2400), "site": (-820, -1960, 1120, 0, 2000), "unveil": (1330, 690, 1740, 1090, 1600)}


def colour(cm):
    a = abs(cm)
    return (150, 150, 150) if a < 3 else (255, 230, 0) if a < 10 else (255, 140, 0) if a < 20 else (230, 20, 20) if a < 52 else (255, 0, 255)


def background(x0, y0, x1, y1, wpx):
    hpx = int(wpx * (y1 - y0) / (x1 - x0))
    if x1 - x0 > 3000:
        ov = META["overview"]
        im = Image.open(RAS / ov["file"]).convert("RGB")
        s = im.width / ov["size_m"]
        box = ((x0 - ov["x0"]) * s, (ov["y0"] + ov["size_m"] - y1) * s, (x1 - ov["x0"]) * s, (ov["y0"] + ov["size_m"] - y0) * s)
        return im.crop(tuple(int(v) for v in box)).resize((wpx, hpx), Image.LANCZOS)
    out = Image.new("RGB", (wpx, hpx), (60, 60, 60))
    k = wpx / (x1 - x0)
    for t in META["tiles"]:
        tx0, ty0, sz = t["x0"], t["y0"], t["size_m"]
        if tx0 > x1 or tx0 + sz < x0 or ty0 > y1 or ty0 + sz < y0:
            continue
        im = Image.open(RAS / t["file"]).convert("RGB")
        s = im.width / sz
        cx0, cy0, cx1, cy1 = max(x0, tx0), max(y0, ty0), min(x1, tx0 + sz), min(y1, ty0 + sz)
        crop = im.crop((int((cx0 - tx0) * s), int((ty0 + sz - cy1) * s), int((cx1 - tx0) * s), int((ty0 + sz - cy0) * s)))
        crop = crop.resize((max(1, int((cx1 - cx0) * k)), max(1, int((cy1 - cy0) * k))), Image.LANCZOS)
        out.paste(crop, (int((cx0 - x0) * k), int((y1 - cy1) * k)))
    return out


for view in VIEWS:
    x0, y0, x1, y1, wpx = BOX[view]
    im = background(x0, y0, x1, y1, wpx)
    im = Image.blend(im, Image.new("RGB", im.size, (0, 0, 0)), 0.35)
    d = ImageDraw.Draw(im)
    k = wpx / (x1 - x0)
    r0 = 1.4 if view == "whole" else 2.2
    pts = []
    for kind, ss in S["samples"].items():
        for s in ss:
            x, y, step = s[0], s[1], s[2]
            if x0 <= x <= x1 and y0 <= y <= y1:
                pts.append((abs(step), x, y))
    pts.sort()                                             # worst drawn last (on top)
    for a, x, y in pts:
        px, py = (x - x0) * k, (y1 - y) * k
        r = r0 * (1.0 if a < 3 else 1.5 if a < 20 else 2.2)
        d.ellipse((px - r, py - r, px + r, py + r), fill=colour(a))
    n = len(pts)
    bad = sum(1 for a, _, _ in pts if a >= 3)
    d.rectangle((0, 0, wpx, 44), fill=(0, 0, 0))
    d.text((10, 6), f"McGregor edge survey '{TAG}' ({S.get('map', '').split('/')[-1].split('.')[0]}), view {view}: {n} samples, {bad} over 3 cm "
                    f"({100.0 * bad / max(n, 1):.1f}%)", fill=(255, 255, 255))
    d.text((10, 24), "step:  grey <3 cm   yellow 3-10   orange 10-20   red 20-52   magenta >52 (body hits)", fill=(255, 255, 255))
    p = ROOT / f"Saved/McGregor/edges/map_{TAG}_{view}.jpg"
    im.save(p, quality=84)
    print(p, n, bad)
