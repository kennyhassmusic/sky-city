"""Public-domain rasters for the McGregor map (US Government works, no restrictions):
  elevation   USGS 3DEP (elevation.nationalmap.gov ImageServer), 2 m float32 grid, one GeoTIFF
  imagery     USDA NAIP via The National Map (imagery.nationalmap.gov USGSNAIPPlus), 4 x 3 tiles at 0.6 m,
              plus a 0.3 m tile around the demo lot (pass --demo lat lon)
Both are requested in plain lat/lon (EPSG:4326) over the same box, so a pixel maps linearly to the map's local
metres (x = (lon - LON0) * KX, y = (lat - LAT0) * KY), the same projection the city maps use.
Saved to $SKYCITY_MCGREGOR_RAW, default Saved/McGregorRaw/ (large; git-ignored; may be a symlink to an external drive).
Run: python3 -I Scripts/mcgregor/fetch_rasters.py [--demo LAT LON]
"""
import json, math, os, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(os.environ.get("SKYCITY_MCGREGOR_RAW", ROOT / "Saved" / "McGregorRaw"))
OUT.mkdir(parents=True, exist_ok=True)
LAT0, LON0 = 31.40375, -97.4621                       # centre of the SpaceX facility (OSM relation 13609042)
KX, KY = 111320.0 * math.cos(math.radians(LAT0)), 110574.0
W_M, H_M = 9600.0, 7200.0                             # map extent in metres (4 x 3 tiles of 2400 m)
LON_W, LON_E = LON0 - W_M / 2 / KX, LON0 + W_M / 2 / KX
LAT_S, LAT_N = LAT0 - H_M / 2 / KY, LAT0 + H_M / 2 / KY
DEP = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
NAIP = "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer/exportImage"


def get(url, params, dest, magic, tries=6):
    """Fetch with retries; keep the file only if it starts like the format we asked for (the servers answer
    errors and gateway timeouts with HTML)."""
    import time
    q = "&".join(f"{k}={v}" for k, v in params.items())
    for t in range(tries):
        subprocess.run(["curl", "-sS", "-m", "300", "-A", "SkyCity-mcgregor/1.0", "-o", str(dest), f"{url}?{q}"])
        if dest.exists() and dest.stat().st_size > 2000 and dest.read_bytes()[:4] in magic:
            return dest.stat().st_size
        time.sleep(5 * (t + 1))
    raise RuntimeError(f"failed: {dest.name}: {dest.read_bytes()[:200] if dest.exists() else b''}")


TIFF = (b"II*\x00", b"MM\x00*")
JPEG = (b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\xff\xd8\xff\xdb", b"\xff\xd8\xff\xee")
PARTS = OUT / "parts"
PARTS.mkdir(exist_ok=True)


def true_band(img_h, w_m, h_m):
    """Rows [top, bottom) of a returned chunk that hold the requested area: the server keeps the requested longitude
    span and widens latitude (centred) so pixels are square in degrees."""
    dlon, dlat = w_m / KX, h_m / KY
    used = img_h * dlat / dlon
    top = (img_h - used) / 2.0
    return top, top + used


def bbox_of(x0, y0, w, h):
    return [LON0 + x0 / KX, LAT0 + y0 / KY, LON0 + (x0 + w) / KX, LAT0 + (y0 + h) / KY]


meta = {"lat0": LAT0, "lon0": LON0, "kx": KX, "ky": KY, "w_m": W_M, "h_m": H_M,
        "bbox": [LON_W, LAT_S, LON_E, LAT_N], "tiles": []}
total = 0
import numpy as np, tifffile
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
# elevation: 4 x 3 chunks of 2400 m at 2 m (1200 px), stitched into one 4800 x 3600 grid (row 0 = north)
dem = np.zeros((int(H_M / 2), int(W_M / 2)), np.float32)
for j in range(3):
    for i in range(4):
        x0, y0 = -W_M / 2 + i * 2400.0, -H_M / 2 + j * 2400.0
        f = PARTS / f"dem_{i}_{j}.tif"
        if not (f.exists() and f.read_bytes()[:4] in TIFF):
            total += get(DEP, {"bbox": ",".join(map(str, bbox_of(x0, y0, 2400, 2400))), "bboxSR": 4326, "imageSR": 4326, "size": "1200,1200",
                               "format": "tiff", "pixelType": "F32", "interpolation": "RSP_BilinearInterpolation", "f": "image"}, f, TIFF)
        a = tifffile.imread(f).astype(np.float32)
        t0, t1 = true_band(a.shape[0], 2400.0, 2400.0)
        from scipy.ndimage import map_coordinates
        rr = t0 + (np.arange(1200) + 0.5) * (t1 - t0) / 1200 - 0.5
        cc = np.arange(1200, dtype=np.float64)
        R_, C_ = np.meshgrid(rr, cc, indexing="ij")
        a = map_coordinates(a, [R_.ravel(), C_.ravel()], order=1, mode="nearest").reshape(1200, 1200)
        r0 = int(H_M / 2) - (j + 1) * 1200
        dem[r0:r0 + 1200, i * 1200:(i + 1) * 1200] = a
tifffile.imwrite(OUT / "elevation_2m.tif", dem)
meta["elevation"] = {"file": "elevation_2m.tif", "size": [int(W_M / 2), int(H_M / 2)], "metres_per_px": 2.0, "row0": "north",
                     "min": float(dem.min()), "max": float(dem.max())}
# imagery: each 2400 m tile = 2 x 2 chunks of 1200 m at 0.6 m (2000 px), stitched to 4000 px, saved as 4096 jpg.
# The server takes a minute or two per chunk, so fetch six at a time first.
from concurrent.futures import ThreadPoolExecutor
jobs = []
for j in range(3):
    for i in range(4):
        x0, y0 = -W_M / 2 + i * 2400.0, -H_M / 2 + j * 2400.0
        for b in range(2):
            for a in range(2):
                f = PARTS / f"naip_{i}_{j}_{a}{b}.jpg"
                if not (f.exists() and f.read_bytes()[:4] in JPEG):
                    jobs.append((f, bbox_of(x0 + a * 1200, y0 + b * 1200, 1200, 1200)))


def fetch(job):
    f, bb = job
    return get(NAIP, {"bbox": ",".join(map(str, bb)), "bboxSR": 4326, "imageSR": 4326, "size": "2000,2000", "format": "jpg",
                      "compressionQuality": 90, "bandIds": "0,1,2", "f": "image"}, f, JPEG)


with ThreadPoolExecutor(max_workers=6) as ex:
    total += sum(ex.map(fetch, jobs))
for j in range(3):
    for i in range(4):
        x0, y0 = -W_M / 2 + i * 2400.0, -H_M / 2 + j * 2400.0
        tile = Image.new("RGB", (4000, 4000))
        for b in range(2):
            for a in range(2):
                f = PARTS / f"naip_{i}_{j}_{a}{b}.jpg"
                if not (f.exists() and f.read_bytes()[:4] in JPEG):
                    total += get(NAIP, {"bbox": ",".join(map(str, bbox_of(x0 + a * 1200, y0 + b * 1200, 1200, 1200))), "bboxSR": 4326, "imageSR": 4326,
                                        "size": "2000,2000", "format": "jpg", "compressionQuality": 90, "bandIds": "0,1,2", "f": "image"}, f, JPEG)
                im = Image.open(f).convert("RGB")
                t0, t1 = true_band(im.height, 1200.0, 1200.0)
                tile.paste(im.crop((0, int(round(t0)), im.width, int(round(t1)))).resize((2000, 2000), Image.LANCZOS), (a * 2000, (1 - b) * 2000))
        out = OUT / f"naip_{i}_{j}.jpg"
        tile.resize((4096, 4096), Image.LANCZOS).save(out, quality=92)
        meta["tiles"].append({"file": out.name, "i": i, "j": j, "x0": x0, "y0": y0, "size_m": 2400.0})
# a sharper 0.3 m tile of the demo lot (1200 m square, 4 chunks of 600 m at 2000 px)
if "--demo" in sys.argv:
    k = sys.argv.index("--demo")
    la, lo = float(sys.argv[k + 1]), float(sys.argv[k + 2])
    cx, cy = (lo - LON0) * KX, (la - LAT0) * KY
    tile = Image.new("RGB", (4000, 4000))
    for b in range(2):
        for a in range(2):
            f = PARTS / f"demo_{a}{b}.jpg"
            total += get(NAIP, {"bbox": ",".join(map(str, bbox_of(cx - 600 + a * 600, cy - 600 + b * 600, 600, 600))), "bboxSR": 4326, "imageSR": 4326,
                                "size": "2000,2000", "format": "jpg", "compressionQuality": 92, "bandIds": "0,1,2", "f": "image"}, f, JPEG)
            im = Image.open(f).convert("RGB")
            t0, t1 = true_band(im.height, 600.0, 600.0)
            tile.paste(im.crop((0, int(round(t0)), im.width, int(round(t1)))).resize((2000, 2000), Image.LANCZOS), (a * 2000, (1 - b) * 2000))
    tile.resize((4096, 4096), Image.LANCZOS).save(OUT / "naip_demo.jpg", quality=93)
    meta["demo"] = {"file": "naip_demo.jpg", "x0": cx - 600, "y0": cy - 600, "size_m": 1200.0}
old = OUT / "rasters.json"
if old.exists() and "--demo" not in sys.argv:
    prev = json.load(open(old))
    if "demo" in prev:
        meta["demo"] = prev["demo"]
json.dump(meta, open(OUT / "rasters.json", "w"), indent=1)
print(f"downloaded {total / 1e6:.1f} MB to {OUT}")
