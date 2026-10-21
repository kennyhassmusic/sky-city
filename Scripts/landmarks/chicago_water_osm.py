"""Sky City: the Chicago lakefront / river water structures from OpenStreetMap, in the plan frame.

What: reads the Overpass extract SourceArt/Reference/ChicagoWater/osm/osm_water.json (harbour features of the Chicago
lakefront and the river main stem: lock, gates, breakwaters, quays, floating docks, moorings, ferry / tour-boat
berths, beacons, lighthouses, boathouses, slipways) and writes SourceArt/Landmarks/water/water_features.json in plan
metres (Saved/Mashup/plan_v3.json frame: x east, y north from the State St bridge; Unreal X = y*100, Y = x*100).
Why: one small, data-driven input for Scripts/landmarks/blender_chicago_water.py (meshes) and
Scripts/roads/place_chicago_water_ue.py (placement), so both use exactly the same real positions.
Projection = Scripts/mashup/build_mashup_data.py's Proj for Chicago (origin 41.88756, -87.6278; equirectangular).
Data (c) OpenStreetMap contributors, ODbL.

Run (repo root):  python3 -I Scripts/landmarks/chicago_water_osm.py
"""
import json, math, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "SourceArt/Reference/ChicagoWater/osm/osm_water.json"
DST = ROOT / "SourceArt/Landmarks/water/water_features.json"
LAT0, LON0 = 41.88756, -87.6278
KX, KY = 111320.0 * math.cos(math.radians(LAT0)), 110574.0
BOX = (100.0, 3200.0, -2200.0, 1800.0)          # plan x0, x1, y0, y1 kept (Chicago lakefront + river main stem)
AREAS = {                                          # named harbour areas (plan bbox)
    "dusable": (1240, 1480, -390, -30),
    "navypier_marina": (1480, 2240, 505, 650),
    "monroe": (920, 1480, -2140, -385),
    "river": (150, 1300, -40, 345),
    "lock": (1300, 2120, -60, 260),
    "navypier": (1480, 2440, 370, 520),
}


def P(lat, lon):
    return [round((lon - LON0) * KX, 2), round((lat - LAT0) * KY, 2)]


def area_of(x, y):
    for k, (a, b, c, d) in AREAS.items():
        if a <= x <= b and c <= y <= d:
            return k
    return None


def inbox(pts):
    return any(BOX[0] <= x <= BOX[1] and BOX[2] <= y <= BOX[3] for x, y in pts)


def main():
    els = json.load(open(SRC))["elements"]
    out = {"frame": "plan metres, x east, y north (Saved/Mashup/plan_v3.json); Unreal X = y*100, Y = x*100",
           "source": "OpenStreetMap (c) OpenStreetMap contributors, ODbL; Overpass extract " + str(SRC.relative_to(ROOT)),
           "lock": {}, "lock_gates": [], "breakwaters": [], "quays": [], "piers": [], "moorings": [], "berths": [],
           "beacons": [], "lighthouses": [], "boathouses": [], "slipways": [], "towers": [], "beaches": [], "water": {}}
    for e in els:
        t = e.get("tags", {})
        if e["type"] == "node":
            x, y = P(e["lat"], e["lon"])
            if not (BOX[0] <= x <= BOX[1] and BOX[2] <= y <= BOX[3]):
                continue
            if t.get("seamark:type") == "mooring":
                out["moorings"].append({"x": x, "y": y, "cat": t.get("seamark:mooring:category", ""), "area": area_of(x, y)})
            elif t.get("amenity") in ("ferry_terminal", "boat_rental"):
                out["berths"].append({"name": t.get("name", ""), "operator": t.get("operator", ""), "kind": t["amenity"], "x": x, "y": y})
            elif t.get("leisure") == "slipway":
                out["slipways"].append({"x": x, "y": y})
            elif t.get("waterway") == "lock_gate":
                out["lock_gates"].append({"name": t.get("name", ""), "x": x, "y": y})
            continue
        if e["type"] == "way":
            pts = [P(g["lat"], g["lon"]) for g in e.get("geometry") or [] if g]
            if len(pts) < 2 or not inbox(pts):
                continue
            closed = e["nodes"][0] == e["nodes"][-1]
            rec = {"id": e["id"], "name": t.get("name", ""), "closed": closed, "pts": pts}
            mm = t.get("man_made")
            if mm == "pier":
                cx = sum(p[0] for p in pts) / len(pts)
                cy = sum(p[1] for p in pts) / len(pts)
                rec.update(area=area_of(cx, cy), floating=t.get("floating", ""), mooring=t.get("mooring", ""),
                           is_area=t.get("area") == "yes" or closed)
                out["piers"].append(rec)
            elif mm in ("breakwater", "groyne"):
                out["breakwaters"].append(rec)
            elif mm == "quay":
                out["quays"].append(rec)
            elif mm == "beacon":
                out["beacons"].append(rec)
            elif mm == "lighthouse":
                rec["height"] = t.get("height", "")
                out["lighthouses"].append(rec)
            elif mm == "tower":
                rec["height"] = t.get("height", "")
                out["towers"].append(rec)
            elif t.get("building") == "boathouse":
                rec["levels"] = t.get("building:levels", "")
                out["boathouses"].append(rec)
            elif t.get("waterway") == "lock_gate":
                out["lock_gates"].append(rec)
            elif t.get("natural") == "beach":
                out["beaches"].append(rec)
            elif t.get("natural") == "water" and t.get("water") in ("lock", "harbour"):
                out["water"][t.get("name") or str(e["id"])] = rec
                if t.get("water") == "lock":
                    out["lock"] = rec
        elif e["type"] == "relation" and t.get("man_made") == "breakwater":
            for m in e.get("members", []):
                pts = [P(g["lat"], g["lon"]) for g in m.get("geometry") or [] if g]
                if len(pts) >= 2 and inbox(pts):
                    out["breakwaters"].append({"id": e["id"], "name": t.get("name", ""), "closed": False, "pts": pts, "member": m.get("ref")})
    DST.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(DST, "w"), indent=0)
    print("wrote", DST, {k: len(v) for k, v in out.items() if isinstance(v, (list, dict))})


if __name__ == "__main__":
    main()
