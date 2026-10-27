"""Plan the drive test and the chase-camera shots for a generated city imported into this project (plain Python).

The city comes from the building-types generator (kennyhassmusic/building-types, branch integration/drive-preview):
  python3 -I Scripts/city/pipeline.py --seed 7          (in the building-types worktree)
then import_gencity_ue.py imports it into /Game/Maps/GenCity_Seed7 here and writes the drive route
(building-types Saved/CityGen/drive_<region>.json: the longest straight major street, where the PlayerStart is).
This script reads that route, the spawn record (roads) and the zoned document (parcel zones) and writes
Saved/GenCity/plan_<region>.json for drive_gencity_ue.py:
  route    waypoints along the main street, Unreal cm, from the PlayerStart
  shots    one car pose per zone (downtown, suburbs, industrial, civic, farmland) on the road whose sides carry the
           most parcels of that zone, plus an aerial (the chase camera pulled far back and up)
  bounds   the city's plan bounds (the drive test checks the car stays inside them)

  python3 -I Scripts/gencity/plan_gencity.py --bt "/Volumes/Sound Libraries/SkyCity Work/BuildingTypes-drive" \
      --seed 7
"""
import argparse
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# zone -> shot name; the order is the shot order.
ZONES = (("downtown_core", "downtown"), ("residential", "suburbs"), ("industrial", "industrial"),
         ("civic", "civic"), ("rural", "farmland"))


def _poly(parcel):
    pts = parcel["polygon"]
    return json.loads(pts) if isinstance(pts, str) else pts


def _centroid(pts):
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def ue(x, y, z=1.0):
    """Plan metres (x east, y north) -> Unreal cm (X north, Y east)."""
    return [round(y * 100.0, 1), round(x * 100.0, 1), round(z * 100.0, 1)]


def ue_yaw(dx, dy):
    """Unreal yaw of a plan direction (X north, Y east)."""
    return round(math.degrees(math.atan2(dx, dy)), 2)


def _edges(zoned):
    nodes = {n["id"]: (float(n["at"][0]), float(n["at"][1])) for n in zoned["roads"]["nodes"]}
    return {e["id"]: (nodes[e["a"]], nodes[e["b"]], e.get("class")) for e in zoned["roads"]["edges"]
            if e["a"] in nodes and e["b"] in nodes}


def _pose(name, zone, a, b, t, extra=None):
    x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
    out = {"name": name, "zone": zone, "plan": [round(x, 2), round(y, 2)], "ue": ue(x, y),
           "yaw": ue_yaw(b[0] - a[0], b[1] - a[1])}
    out.update(extra or {})
    return out


def zone_poses(zoned, fields=()):
    """One car pose per zone: on the road edge (>= 40 m) that the most parcels of that zone front (frontage_edge),
    less the parcels of other zones fronting it, a third of the way along (the chase camera then looks down the
    block). Farmland: beside the largest crop field, on the road nearest its middle (land cover fields), else the
    rural zone the same way as the others."""
    edges = _edges(zoned)
    fronts = {}
    for p in zoned.get("parcels") or []:
        fronts.setdefault(p.get("frontage_edge"), []).append(p.get("zone"))
    out = []
    for zone, name in ZONES:
        if zone == "rural" and fields:
            f = max(fields, key=lambda f: (f.get("area_m2") or 0, f["id"]))
            cx, cy = _centroid(f["polygon"])
            best = None
            for eid, (a, b, _cls) in sorted(edges.items()):
                dx, dy = b[0] - a[0], b[1] - a[1]
                length2 = dx * dx + dy * dy
                if length2 < 40.0 ** 2:
                    continue
                t = max(0.1, min(0.9, ((cx - a[0]) * dx + (cy - a[1]) * dy) / length2))
                d = math.hypot(a[0] + dx * t - cx, a[1] + dy * t - cy)
                if best is None or d < best[0]:
                    best = (d, a, b, t)
            if best:
                d, a, b, t = best
                out.append(_pose(name, zone, a, b, max(0.1, t - 0.15),
                                 {"field": f["id"], "crop": f.get("crop"), "field_dist_m": round(d, 1)}))
                continue
        best = None
        for eid, (a, b, _cls) in sorted(edges.items()):
            if math.hypot(b[0] - a[0], b[1] - a[1]) < 40.0:
                continue
            zs = fronts.get(eid) or []
            n = sum(1 for z in zs if z == zone)
            score = n - sum(1 for z in zs if z != zone)
            if n and (best is None or score > best[0]):
                best = (score, n, a, b, eid)
        if best is None:
            continue
        _score, n, a, b, eid = best
        out.append(_pose(name, zone, a, b, 0.3, {"edge": eid, "parcels_fronting": n}))
    return out


def garage_ramp(layout, back_m=12.0):
    """A garage's drive ramp (office type, lane 5: "KIT_Awning|collision" plates, Unreal cm [x, y, z, yaw, sx, sy,
    sz]): the lowest plate and the next one up the ramp give the way in. Returns the car's start (back_m before the
    first plate, on the street), its yaw and the ramp's rise per plate, or None when the city has no garage."""
    plates = (layout.get("groups") or {}).get("KIT_Awning|collision") or []
    if len(plates) < 2:
        return None
    low = min(plates, key=lambda i: (i[2], i[0], i[1]))
    up = [i for i in plates if 20.0 < i[2] - low[2] < 120.0]
    if not up:
        return None
    nxt = min(up, key=lambda i: math.hypot(i[0] - low[0], i[1] - low[1]))
    dx, dy = nxt[0] - low[0], nxt[1] - low[1]
    d = math.hypot(dx, dy) or 1.0
    ux, uy = dx / d, dy / d
    start = [round(low[0] - ux * back_m * 100.0, 1), round(low[1] - uy * back_m * 100.0, 1), 100.0]
    return {"start_ue": start, "yaw": round(math.degrees(math.atan2(uy, ux)), 2), "first_plate_ue": low[:3],
            "rise_cm_per_plate": round(nxt[2] - low[2], 1), "run_cm_per_plate": round(d, 1),
            "plates": len(plates)}


def plan(bt_root, region, waypoint_m=60.0):
    saved = os.path.join(bt_root, "Saved", "CityGen")
    spawn = json.load(open(os.path.join(saved, "spawn_%s.json" % region)))
    route = json.load(open(os.path.join(saved, "drive_%s.json" % region)))
    seed = spawn.get("seed")
    zoned_path = os.path.join(saved, "pipeline", "seed-%s" % seed, "zoned_city.json")
    zoned = json.load(open(zoned_path))
    pts = route["pts"]
    sx, sy = route["start_plan"]
    wps = []
    # Waypoints every waypoint_m along the route, from the start point on.
    dist_from_start = 0.0
    prev = (sx, sy)
    started = False
    for a, b in zip(pts, pts[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        steps = max(1, int(seg // waypoint_m))
        for i in range(1, steps + 1):
            q = (a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps)
            if not started:
                # skip points behind the start
                if (q[0] - sx) * (b[0] - a[0]) + (q[1] - sy) * (b[1] - a[1]) <= 1.0:
                    continue
                started = True
            dist_from_start += math.hypot(q[0] - prev[0], q[1] - prev[1])
            prev = q
            wps.append(ue(q[0], q[1], 0.0))
    fields = []
    lc_path = os.path.join(saved, "pipeline", "seed-%s" % seed, "landcover", "landcover.json")
    if os.path.isfile(lc_path):
        fields = json.load(open(lc_path)).get("fields") or []
    shots = zone_poses(zoned, fields)
    bounds = route.get("bounds") or spawn.get("bounds")
    # The aerial: the car on the main street a third of the way along, the test camera 450 m back and 40 degrees
    # up, looking over the city along the street.
    a, b = route["pts"][0], route["pts"][-1]
    shots.append(_pose("aerial", None, a, b, 0.25, {"cam": {"dist_m": 450.0, "yaw": 0.0, "elev": 40.0}}))
    layout_path = os.path.join(saved, "kit_layout_%s.json" % region)
    ramp = garage_ramp(json.load(open(layout_path))) if os.path.isfile(layout_path) else None
    if ramp:
        shots.append({"name": "garage_ramp", "zone": None, "ue": ramp["start_ue"], "yaw": ramp["yaw"],
                      "plan": [round(ramp["start_ue"][1] / 100.0, 2), round(ramp["start_ue"][0] / 100.0, 2)]})
    return {"region": region, "seed": seed, "ramp": ramp, "level": route.get("level"), "bounds": bounds,
            "route": {"start_ue": route["start_ue"], "yaw": route["yaw"], "length_m": route["length_m"],
                      "waypoints_ue": wps, "major": route.get("major")},
            "shots": shots, "bt_root": bt_root}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--bt", required=True, help="building-types worktree that generated the city")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--region", default=None, help="default seed<N>_city")
    args = parser.parse_args(argv)
    region = args.region or "seed%d_city" % args.seed
    doc = plan(os.path.abspath(args.bt), region)
    os.makedirs(os.path.join(ROOT, "Saved", "GenCity"), exist_ok=True)
    out = os.path.join(ROOT, "Saved", "GenCity", "plan_%s.json" % region)
    with open(out, "w") as handle:
        json.dump(doc, handle, indent=1, sort_keys=True)
        handle.write("\n")
    print("plan", out, "route", doc["route"]["length_m"], "m,", len(doc["route"]["waypoints_ue"]), "waypoints;",
          "shots", ", ".join(s["name"] for s in doc["shots"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
