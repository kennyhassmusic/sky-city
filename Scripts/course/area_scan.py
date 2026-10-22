"""Where can the Course Builder's build area go on the McGregor map? (How Content/SkyCity/Data/course_area.json was chosen.)
Plain python3 (numpy, scipy, Pillow), no editor:  python3 -I Scripts/course/area_scan.py [size=600] [margin=70] [top=8] [png=out.png]

Reads Saved/McGregor/ (mcgregor_data.json, site_features.json, demo_layout.json, terrain_*.f32: the 4 m USGS height grids), marks every
road, building, tank, tower, fence, pond, pylon, kit placement, test stand, the unveil lot and its show set on a 10 m grid
(grown by the margin), then slides a size x size window over the map and lists the clear ones with the least height range.

Frames: the site frame (metres, x east, y north, origin = the facility centre). The course frame of SkyCourse.h is
x = site y, y = -site x (Unreal cm = site y * 100 in X, site x * 100 in Y), so a window x0..x1, y0..y1 in site metres is the course
box min [y0, -x1], max [y1, -x0]. The terrain rolls by 4-5 m over any 600 m, so the director lays a flat pad at ground_z (the
window's highest ground) over the area and eases it down to the terrain over pad_margin metres.
"""
import array, json, os, pathlib, sys
import numpy as np
from scipy import ndimage as ndi

ROOT = pathlib.Path(os.environ.get("SKYCITY_ROOT") or pathlib.Path(__file__).resolve().parents[2])
SAVED = ROOT / "Saved" / "McGregor"
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
SIZE = float(KV.get("size", 600))
MARGIN = float(KV.get("margin", 70))
TOP = int(KV.get("top", 8))
CELL = 10.0
X0, X1, Y0, Y1 = -4800.0, 4800.0, -3600.0, 3600.0
NX, NY = int((X1 - X0) / CELL), int((Y1 - Y0) / CELL)

D = json.load(open(SAVED / "mcgregor_data.json"))
S = json.load(open(SAVED / "site_features.json"))
L = json.load(open(SAVED / "demo_layout.json"))

# the height grids: 12 tiles of 601 x 601 samples, 4 m apart (row 0 = south), stitched into one 2400 x 1800 grid
dem = np.zeros((1800, 2400), dtype=np.float32)
for i in range(4):
    for j in range(3):
        a = array.array("f")
        a.frombytes((SAVED / f"terrain_{i}_{j}.f32").read_bytes())
        dem[j * 600:(j + 1) * 600, i * 600:(i + 1) * 600] = np.frombuffer(a, dtype=np.float32).reshape(601, 601)[:600, :600]

from PIL import Image, ImageDraw
img = Image.new("L", (NX, NY), 0)
dr = ImageDraw.Draw(img)
px = lambda x, y: ((x - X0) / CELL, (y - Y0) / CELL)
poly = lambda ring: dr.polygon([px(*p[:2]) for p in ring], fill=255)
line = lambda pts, w: dr.line([px(*p) for p in pts], fill=255, width=max(1, int(w / CELL)))
def disc(p, r):
    cx, cy = px(*p); rr = r / CELL
    dr.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=255)
for r in D["roads"]: line(r["pts"], r["w"] + 4)
for b in D["buildings"]: poly(b["ring"])
for t in D["tanks"]: disc(t["p"], t["r"] + 4)
for t in D["towers"]: disc(t["p"], 15)
for f in D["fences"]: line(f["pts"], 4)
for p in D["ponds"]: poly(p["ring"])
for p in D["pylons"]: disc(p["p"], 12)
for pl in S["placements"]: disc(pl["p"], 14)
for ft in S["features"]:
    if ft.get("p"):
        sz = ft.get("size_m") or [20, 20, 0]
        disc(ft["p"], max(sz[0], sz[1]) * 0.7 + 8)
for lot in S["lots"]:
    xs = [v[0] for v in lot["verts"]]; ys = [v[1] for v in lot["verts"]]
    dr.rectangle([px(min(xs) - 10, min(ys) - 10), px(max(xs) + 10, max(ys) + 10)], fill=255)
poly(L["lot_paved"])
for k in L["keep_clear"]: line([k["a"], k["b"]], 2 * k["half"])
for b in L["buildings"]: disc(b["p"], b["len"] * 0.7)
disc(L["stage"]["p"], 60)
for it in L["items"]:
    for a in it["at"]: disc(a["p"], 12)
for v in L["lines"].values(): line(v, 30)
for ln in L["lineup"]: disc(ln["p"], 20)
for v in S["tests"].values():
    if isinstance(v, dict):
        for e in v.values():
            if isinstance(e, dict) and "rim" in e: poly(e["rim"])
occ = ndi.binary_dilation(np.array(img) > 0, iterations=max(1, int(round(MARGIN / CELL)))).astype(np.float32)

dem10 = ndi.zoom(dem, (NY / 1800, NX / 2400), order=1)
W = int(SIZE / CELL)
busy = ndi.uniform_filter(occ, size=W, mode="constant", cval=1.0) * W * W
rng = ndi.maximum_filter(dem10, size=W) - ndi.minimum_filter(dem10, size=W)
rr, cc = np.mgrid[0:NY, 0:NX]
ok = (busy < 0.5) & (cc > W // 2 + 15) & (cc < NX - W // 2 - 15) & (rr > W // 2 + 15) & (rr < NY - W // 2 - 15)   # 150 m off the map's edge
found = sorted((float(rng[r, c]), int(r), int(c)) for r, c in np.argwhere(ok))
print(f"{SIZE:.0f} m windows clear of everything by {MARGIN:.0f} m: {len(found)} positions; the flattest, one per 400 m:")
seen = []
for dz, r, c in found:
    cx, cy = X0 + (c + .5) * CELL, Y0 + (r + .5) * CELL
    if any(abs(cx - a) < 400 and abs(cy - b) < 400 for a, b in seen): continue
    seen.append((cx, cy))
    h = SIZE / 2
    z = dem[int((cy - h - Y0) / 4):int((cy + h - Y0) / 4) + 1, int((cx - h - X0) / 4):int((cx + h - X0) / 4) + 1]
    print(f"  site x {cx - h:.0f}..{cx + h:.0f}  y {cy - h:.0f}..{cy + h:.0f}   ground {z.min():.1f}..{z.max():.1f} m (range {z.max() - z.min():.1f})"
          f"   course min [{cy - h:.0f}, {-(cx + h):.0f}] max [{cy + h:.0f}, {-(cx - h):.0f}]")
    if len(seen) >= TOP: break
if "png" in KV:
    Image.fromarray((occ * 255).astype("uint8")).transpose(Image.FLIP_TOP_BOTTOM).save(KV["png"])
    print("occupancy picture:", KV["png"])
