"""Street-level OpenStreetMap detail for Sky City's two downtowns (same areas as Scripts/mashup/fetch_osm.py):
lamps, trees and tree rows, crossings, signals, stop signs, kerbs, alleys and service roads, footways,
benches, bins, bike parking, hydrants, bus stops, parking lots and grass/gravel areas.
Saves raw Overpass JSON to SourceArt/osm/<city>_street.json. Data (c) OpenStreetMap contributors, ODbL.

Run: python3 -I Scripts/streets/fetch_street_osm.py
"""
import json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "SourceArt" / "osm"
CITIES = {"chicago": (41.860, -87.665, 41.910, -87.600), "austin": (30.245, -97.770, 30.290, -97.715)}


def query(b):
    bb = ",".join(str(v) for v in b)
    return f"""[out:json][timeout:240];
(
  node["highway"~"^(street_lamp|traffic_signals|stop|give_way|crossing|bus_stop)$"]({bb});
  node["natural"="tree"]({bb});
  way["natural"="tree_row"]({bb});
  node["amenity"~"^(bicycle_parking|bench|waste_basket|waste_disposal|recycling|post_box|bicycle_rental|parking_entrance|fountain|drinking_water)$"]({bb});
  node["emergency"="fire_hydrant"]({bb});
  node["traffic_sign"]({bb});
  node["kerb"]({bb});
  node["barrier"~"^(bollard|kerb)$"]({bb});
  way["highway"="service"]({bb});
  way["highway"~"^(footway|pedestrian|path|cycleway|steps)$"]({bb});
  way["amenity"="parking"]({bb});
  way["landuse"~"^(grass|construction|brownfield|railway)$"]({bb});
  way["surface"~"^(gravel|fine_gravel|pebblestone|dirt|ground|grass)$"]["area"="yes"]({bb});
  way["leisure"~"^(pitch|playground|garden)$"]({bb});
  way["natural"~"^(scrub|grassland|wood)$"]({bb});
);
out geom({bb});
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, b in CITIES.items():
        t0 = time.time()
        for attempt in range(5):
            raw = subprocess.run(["curl", "-sS", "-m", "300", "-A", "SkyCity-streets/1.0", "--data-urlencode", "data@-",
                                  "https://overpass-api.de/api/interpreter"], input=query(b).encode(), capture_output=True, check=True).stdout
            try:
                n = len(json.loads(raw)["elements"])
                break
            except ValueError:
                time.sleep(20 * (attempt + 1))
        else:
            raise RuntimeError(raw[:300])
        (OUT / f"{name}_street.json").write_bytes(raw)
        print(f"{name}: {n} elements, {len(raw) / 1e6:.1f} MB in {time.time() - t0:.0f}s")
        time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
