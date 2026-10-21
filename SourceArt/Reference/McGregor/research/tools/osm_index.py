"""Map OSM element ids to their index in Saved/McGregor/mcgregor_data.json (roads/buildings/tanks/towers/fences/
ponds/pylons), by replaying the classification order of Scripts/mcgregor/build_mcgregor_data.py on the same
SourceArt/osm/mcgregor.json. Used by build_site_research.py. Run alone to print the table:
  python3 -I SourceArt/Reference/McGregor/research/tools/osm_index.py"""
import json, math, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[5]
LAT0, LON0, KX, KY = 31.40375, -97.4621, 95013.4785371064, 110574.0
W, H = 9600.0, 7200.0
ROAD = {"motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "service", "track", "footway", "path"}


def xy(lat, lon):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


def inside(p):
    return -W / 2 <= p[0] <= W / 2 and -H / 2 <= p[1] <= H / 2


def build():
    osm = json.load(open(ROOT / "SourceArt/osm/mcgregor.json"))["elements"]
    n = {k: 0 for k in ("roads", "buildings", "tanks", "towers", "fences", "ponds", "pylons")}
    table = {}
    for e in osm:
        t = e.get("tags", {})
        if e["type"] == "node":
            p = xy(e["lat"], e["lon"])
            if not inside(p):
                continue
            if t.get("power") == "tower":
                table[("node", e["id"])] = ("pylons", n["pylons"]); n["pylons"] += 1
            elif t.get("man_made") in ("water_tower", "tower", "mast", "chimney"):
                table[("node", e["id"])] = ("towers", n["towers"]); n["towers"] += 1
            continue
        if e["type"] != "way":
            continue
        g = [xy(q["lat"], q["lon"]) for q in (e.get("geometry") or []) if q]
        if len(g) < 2 or not any(inside(p) for p in g):
            continue
        closed = math.dist(g[0], g[-1]) < 0.5 and len(g) >= 4
        cat = None
        if "highway" in t and t["highway"] in ROAD:
            cat = "roads"
        elif closed and t.get("man_made") in ("storage_tank", "silo"):
            cat = "tanks"
        elif closed and t.get("man_made") in ("water_tower", "tower", "works", "mast") or (closed and t.get("aeroway") == "flame_trench"):
            cat = "ponds" if (t.get("aeroway") == "flame_trench" and not t.get("man_made")) else "buildings"
        elif closed and "building" in t:
            cat = "buildings"
        elif t.get("barrier") in ("fence", "wall"):
            cat = "fences"
        elif closed and (t.get("natural") == "water" or t.get("water") or t.get("landuse") in ("reservoir", "basin")):
            cat = "ponds"
        if cat:
            table[("way", e["id"])] = (cat, n[cat]); n[cat] += 1
    return table, n


if __name__ == "__main__":
    table, n = build()
    D = json.load(open(ROOT / "Saved/McGregor/mcgregor_data.json"))
    print({k: (n[k], len(D[k])) for k in n})
