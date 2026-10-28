"""Pack an inspection run (inspect_gencity_ue.py) for the review agents (plain Python + Pillow):
  python3 -I Scripts/gencity/inspect_pack.py Saved/GenCity/inspect_<tag>.json <out dir> [extra.json ...]
Writes <out>/<route>/NNNN_<kind>.jpg (from the HighResShot PNGs) and <out>/manifest.json (every frame with its
route, kind, file, camera UE location and yaw, car, road edge id and class, district, zones and parcel types, plus
the physics anomalies of the drive)."""
import json
import os
import sys

from PIL import Image


def main(src, out, extras):
    runs = [json.load(open(src))] + [json.load(open(e)) for e in extras]
    manifest = {"source": [src] + extras, "frames": [], "anomalies": [], "routes": {}}
    counters = {}
    plan = {}
    pp = os.path.join(os.path.dirname(src), "inspect_%s.json" % runs[0].get("region", "seed7_city"))
    if os.path.isfile(pp):
        plan = {r["name"]: r for r in json.load(open(pp)).get("routes", [])}
    for run in runs:
        for a in run.get("anomalies", []):
            # the driver brakes hard from 35 to 15 mph where a turn starts (the plan's slow zones): a speed drop that
            # starts there is the driver, not a hit
            slow = (plan.get(a.get("route")) or {}).get("slow") or []
            if a.get("kind") == "sudden_stop" and any(s0 - 5 <= a.get("dist_m", -1) <= s1 + 5 for s0, s1 in slow):
                a["cause"] = "driver braking into a planned turn (slow zone), not a collision"
                a["real"] = False
            else:
                a["real"] = True
            manifest["anomalies"].append(a)
        manifest["routes"].update(run.get("routes", {}))
        for f in run.get("frames", []):
            if not f.get("png") or not os.path.isfile(f["png"]):
                continue
            route = f["route"]
            n = counters.get(route, 0)
            counters[route] = n + 1
            d = os.path.join(out, route)
            os.makedirs(d, exist_ok=True)
            name = "%04d_%s.jpg" % (n, f["kind"])
            Image.open(f["png"]).convert("RGB").save(os.path.join(d, name), quality=88)
            g = dict(f)
            g["file"] = os.path.join(route, name)
            g.pop("png", None)
            manifest["frames"].append(g)
    manifest["counts"] = counters
    manifest["total_frames"] = sum(counters.values())
    with open(os.path.join(out, "manifest.json"), "w") as h:
        json.dump(manifest, h, indent=1)
    print("frames", manifest["total_frames"], counters, "anomalies", len(manifest["anomalies"]),
          "real", sum(1 for a in manifest["anomalies"] if a.get("real")))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
