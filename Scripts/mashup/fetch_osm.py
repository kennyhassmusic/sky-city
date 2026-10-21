"""Download downtown street maps of Chicago and Austin from OpenStreetMap (Overpass API).

Saves raw Overpass JSON to SourceArt/osm/<city>.json. Data (c) OpenStreetMap contributors, ODbL:
a released game must credit "(c) OpenStreetMap contributors".

Run: python3 -I Scripts/mashup/fetch_osm.py
"""
import json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "SourceArt" / "osm"

# south, west, north, east
CITIES = {
    # the Loop, River North, Streeterville, Grant Park and the lakefront
    "chicago": (41.860, -87.665, 41.910, -87.600),
    # Lady Bird Lake and the top of South Congress up past the Capitol
    "austin": (30.245, -97.770, 30.290, -97.715),
}

ROADS = ("motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|pedestrian|"
         "motorway_link|trunk_link|primary_link|secondary_link|tertiary_link")


def query(b):
    bb = ",".join(str(v) for v in b)
    return f"""[out:json][timeout:180];
(
  way["highway"~"^({ROADS})$"]({bb});
  way["railway"~"^(subway|light_rail|rail|monorail)$"]({bb});
  way["natural"="water"]({bb});
  relation["natural"="water"]({bb});
  way["waterway"~"^(river|canal|stream)$"]({bb});
  way["natural"="coastline"]({bb});
  way["leisure"="park"]({bb});
  relation["leisure"="park"]({bb});
  way["building"]["name"~"Capitol|Willis|Merchandise Mart|Navy Pier"]({bb});
);
out geom({bb});
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, b in CITIES.items():
        t0 = time.time()
        # system curl: python.org Python on this Mac has no CA bundle installed
        raw = subprocess.run(["curl", "-sS", "-m", "240", "-A", "SkyCity-mashup/1.0", "--data-urlencode", "data@-",
                              "https://overpass-api.de/api/interpreter"],
                             input=query(b).encode(), capture_output=True, check=True).stdout
        (OUT / f"{name}.json").write_bytes(raw)
        n = len(json.loads(raw).get("elements", []))
        print(f"{name}: {n} elements, {len(raw) / 1e6:.1f} MB in {time.time() - t0:.0f}s")
        time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
