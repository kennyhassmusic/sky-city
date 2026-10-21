"""OpenStreetMap for the McGregor map: the SpaceX Rocket Development and Test Facility (OSM relation 13609042)
and its surroundings. Saves SourceArt/osm/mcgregor.json. Data (c) OpenStreetMap contributors, ODbL.
Run: python3 -I Scripts/mcgregor/fetch_osm.py"""
import json, pathlib, subprocess, time
ROOT = pathlib.Path(__file__).resolve().parents[2]
BBOX = (31.368, -97.505, 31.438, -97.418)     # south, west, north, east: the facility plus ~1 km around it
bb = ",".join(map(str, BBOX))
Q = f"""[out:json][timeout:240];
(
  way["highway"]({bb});
  way["building"]({bb});
  way["man_made"]({bb});
  node["man_made"]({bb});
  way["landuse"]({bb});
  way["natural"]({bb});
  way["waterway"]({bb});
  way["water"]({bb});
  way["amenity"]({bb});
  way["barrier"]({bb});
  way["power"]({bb});
  node["power"="tower"]({bb});
  way["railway"]({bb});
  way["leisure"]({bb});
  way["aeroway"]({bb});
  relation(13609042);
  way(r);
);
out geom;
"""
for attempt in range(4):
    raw = subprocess.run(["curl", "-sS", "-m", "300", "-A", "SkyCity-mcgregor/1.0", "--data-urlencode", "data@-",
                          "https://overpass-api.de/api/interpreter"], input=Q.encode(), capture_output=True, check=True).stdout
    try:
        n = len(json.loads(raw)["elements"])
        break
    except ValueError:
        time.sleep(20 * (attempt + 1))
out = ROOT / "SourceArt/osm/mcgregor.json"
out.write_bytes(raw)
print(n, "elements,", round(len(raw) / 1e6, 1), "MB ->", out)
