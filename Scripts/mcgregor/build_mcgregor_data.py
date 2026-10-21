"""McGregor map data, in local metres (x east, y north from the SpaceX facility centre; Unreal X = y*100,
Y = x*100, the same convention as the city map), with heights sampled from the USGS 2 m elevation grid.

Inputs: SourceArt/osm/mcgregor.json (fetch_osm.py), $SKYCITY_MCGREGOR_RAW/rasters.json (default Saved/McGregorRaw) +
elevation_2m.tif (fetch_rasters.py). Output: Saved/McGregor/mcgregor_data.json
  roads      polylines with per-vertex ground height, width and surface (asphalt / caliche gravel / dirt track)
  buildings  footprints with base height (lowest ground under the walls) and height
  tanks      storage tanks and silos as cylinders; towers (test stands, water towers, masts) as points + kind
  fences     fence / wall polylines; ponds as polygons with their water level; pylons (power towers) as points
Data (c) OpenStreetMap contributors, ODbL; elevation USGS 3DEP (public domain).
Run: python3 -I Scripts/mcgregor/build_mcgregor_data.py
"""
import json, math, os, pathlib
import numpy as np, tifffile

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAS = pathlib.Path(os.environ.get("SKYCITY_MCGREGOR_RAW", ROOT / "Saved" / "McGregorRaw"))
META = json.load(open(RAS / "rasters.json"))
DEM = tifffile.imread(RAS / META["elevation"]["file"]).astype(np.float32)   # row 0 = north, 2 m pixels
LAT0, LON0, KX, KY, W, H = META["lat0"], META["lon0"], META["kx"], META["ky"], META["w_m"], META["h_m"]
OSM = json.load(open(ROOT / "SourceArt/osm/mcgregor.json"))["elements"]
OUT = ROOT / "Saved/McGregor/mcgregor_data.json"
Z0 = float(np.percentile(DEM, 5))          # map datum: heights are stored relative to this, so Unreal z stays small


def xy(lat, lon):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


def ground(x, y):
    """Bilinear ground height (m above Z0) at local x, y."""
    c = (x + W / 2) / 2.0 - 0.5
    r = (H / 2 - y) / 2.0 - 0.5
    c = min(max(c, 0), DEM.shape[1] - 1.001)
    r = min(max(r, 0), DEM.shape[0] - 1.001)
    c0, r0 = int(c), int(r)
    fc, fr = c - c0, r - r0
    a = DEM[r0, c0] * (1 - fc) + DEM[r0, c0 + 1] * fc
    b = DEM[r0 + 1, c0] * (1 - fc) + DEM[r0 + 1, c0 + 1] * fc
    return float(a * (1 - fr) + b * fr) - Z0


def inside(p, pad=0.0):
    return -W / 2 + pad <= p[0] <= W / 2 - pad and -H / 2 + pad <= p[1] <= H / 2 - pad


def resample(pts, step):
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(math.dist(a, b) / step))
        for k in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
    return out


ROAD_W = {"motorway": 14, "trunk": 12, "primary": 11, "secondary": 9, "tertiary": 8, "residential": 7, "unclassified": 6.5,
          "service": 5.0, "track": 3.5, "footway": 2.0, "path": 2.0}


def surface_of(t):
    s = t.get("surface", "")
    if s in ("asphalt", "paved", "concrete"):
        return "asphalt"
    if t.get("highway") == "track" or s in ("dirt", "ground", "grass"):
        return "dirt"
    if s in ("gravel", "unpaved", "fine_gravel", "compacted"):
        return "caliche"
    return "asphalt" if t.get("highway") in ("primary", "secondary", "tertiary", "residential", "motorway", "trunk") else "caliche"


roads, buildings, tanks, towers, fences, ponds, pylons = [], [], [], [], [], [], []
for e in OSM:
    t = e.get("tags", {})
    if e["type"] == "node":
        p = xy(e["lat"], e["lon"])
        if not inside(p):
            continue
        if t.get("power") == "tower":
            pylons.append({"p": [round(p[0], 2), round(p[1], 2)], "z": round(ground(*p), 2)})
        elif t.get("man_made") in ("water_tower", "tower", "mast", "chimney"):
            towers.append({"p": [round(p[0], 2), round(p[1], 2)], "z": round(ground(*p), 2), "kind": t.get("man_made"), "name": t.get("name", ""),
                           "height": float(t.get("height", "0").split()[0] or 0)})
        continue
    if e["type"] != "way":
        continue
    g = [xy(q["lat"], q["lon"]) for q in (e.get("geometry") or []) if q]
    if len(g) < 2 or not any(inside(p) for p in g):
        continue
    closed = math.dist(g[0], g[-1]) < 0.5 and len(g) >= 4
    if "highway" in t and t["highway"] in ROAD_W:
        pts = resample(g, 6.0)
        roads.append({"pts": [[round(x, 2), round(y, 2)] for x, y in pts], "z": [round(ground(x, y), 2) for x, y in pts],
                      "w": ROAD_W[t["highway"]], "surface": surface_of(t), "kind": t["highway"], "name": t.get("name", "")})
    elif closed and t.get("man_made") in ("storage_tank", "silo"):
        cx = sum(p[0] for p in g[:-1]) / (len(g) - 1)
        cy = sum(p[1] for p in g[:-1]) / (len(g) - 1)
        r = sum(math.dist((cx, cy), p) for p in g[:-1]) / (len(g) - 1)
        h = float(t.get("height", "0").split()[0] or 0) or (24.0 if t["man_made"] == "silo" else min(max(r * 2.2, 3.0), 14.0))
        tanks.append({"p": [round(cx, 2), round(cy, 2)], "r": round(r, 2), "h": round(h, 1), "z": round(ground(cx, cy), 2), "kind": t["man_made"]})
    elif closed and t.get("man_made") in ("water_tower", "tower", "works", "mast") or (closed and t.get("aeroway") == "flame_trench"):
        cx = sum(p[0] for p in g[:-1]) / (len(g) - 1)
        cy = sum(p[1] for p in g[:-1]) / (len(g) - 1)
        kind = t.get("man_made") or t.get("aeroway")
        dflt = {"water_tower": 38.0, "tower": 45.0, "works": 22.0, "mast": 30.0, "flame_trench": 0.0}[kind]
        h = float(t.get("height", "0").split()[0] or 0) or dflt
        zs = [ground(*p) for p in g[:-1]]
        if kind == "flame_trench":
            ponds.append({"ring": [[round(x, 2), round(y, 2)] for x, y in g[:-1]], "level": round(min(zs) - 0.5, 2), "kind": "trench"})
        else:
            buildings.append({"ring": [[round(x, 2), round(y, 2)] for x, y in g[:-1]], "z": round(min(zs) - 0.3, 2), "h": round(h, 1),
                              "kind": kind, "name": t.get("name", "")})
    elif closed and "building" in t:
        lv = t.get("building:levels")
        h = float(t.get("height", "0").split()[0] or 0) or (float(lv) * 3.5 if lv else
             {"industrial": 9.0, "warehouse": 10.0, "bunker": 3.5, "house": 6.0, "residential": 7.0, "church": 10.0, "garage": 4.0,
              "shed": 3.5, "roof": 5.0}.get(t["building"], 6.0))
        zs = [ground(*p) for p in g[:-1]]
        buildings.append({"ring": [[round(x, 2), round(y, 2)] for x, y in g[:-1]], "z": round(min(zs) - 0.3, 2), "h": round(h, 1),
                          "kind": t["building"], "name": t.get("name", "")})
    elif t.get("barrier") in ("fence", "wall"):
        pts = resample(g, 3.0)
        fences.append({"pts": [[round(x, 2), round(y, 2)] for x, y in pts], "z": [round(ground(x, y), 2) for x, y in pts], "kind": t["barrier"]})
    elif closed and (t.get("natural") == "water" or t.get("water") or t.get("landuse") in ("reservoir", "basin")):
        zs = [ground(*p) for p in g[:-1]]
        ponds.append({"ring": [[round(x, 2), round(y, 2)] for x, y in g[:-1]], "level": round(min(zs) - 0.2, 2), "kind": "pond"})

out = {"frame": "metres, x east, y north, origin = facility centre; z above datum", "datum_m": round(Z0, 2),
       "extent": [W, H], "roads": roads, "buildings": buildings, "tanks": tanks, "towers": towers, "fences": fences,
       "ponds": ponds, "pylons": pylons, "attribution": "(c) OpenStreetMap contributors; USGS 3DEP"}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, separators=(",", ":")))
# terrain height grids for Unreal (its Python has no numpy): one raw float32 file per 2400 m tile,
# 601 x 601 samples at 4 m, row 0 = south edge, column 0 = west edge, metres above the datum
from scipy.ndimage import map_coordinates
N, STEP = 601, 4.0
for t in META["tiles"]:
    x0, y0 = t["x0"], t["y0"]
    xs = x0 + np.arange(N) * STEP
    ys = y0 + np.arange(N) * STEP
    X, Y = np.meshgrid(xs, ys)                    # rows = y (south -> north)
    cols = (X + W / 2) / 2.0 - 0.5
    rows = (H / 2 - Y) / 2.0 - 0.5
    hgt = map_coordinates(DEM, [rows.ravel(), cols.ravel()], order=1, mode="nearest").reshape(N, N) - Z0
    hgt.astype("<f4").tofile(OUT.parent / f"terrain_{t['i']}_{t['j']}.f32")
print("terrain grids written")
print({k: len(v) for k, v in out.items() if isinstance(v, list)}, "datum", round(Z0, 1), "relief", round(float(DEM.max() - DEM.min()), 1), "m")
