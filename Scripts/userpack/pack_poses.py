"""Camera poses that look at the game pack's meshes in the imported level (for revisit_gencity_ue.py).

  python3 -I Scripts/userpack/pack_poses.py <building-types worktree> <region> <out json> [per_slot]

Replays user_pack.plan on the same layout, props and lot cars the import used, with the imported meshes' bounds
from the import report (Saved/CityGen/userpack_game_<region>.json), so the instances are exactly where Unreal put
them. For a few instances per slot it writes a pedestrian-height pose (1.7 m) a few metres off, looking at it.
"""
import json
import math
import os
import sys


def main():
    bt, region, out = sys.argv[1], sys.argv[2], sys.argv[3]
    per = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    sys.path.insert(0, os.path.join(bt, "Scripts", "city"))
    import user_pack
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    manifest = user_pack.load(os.path.join(here, "UserPacks", "game", "userpack.json"))
    saved = os.path.join(bt, "Saved", "CityGen")
    report = json.load(open(os.path.join(saved, "userpack_game_%s.json" % region)))
    bounds = {m: (tuple(a), tuple(b)) for m, (a, b) in report["bounds_cm"].items()}
    layout = json.load(open(os.path.join(saved, "kit_layout_%s.json" % region)))
    for name, key in (("props_%s.json", "groups"), ("lotdress_%s.json", "cars")):
        path = os.path.join(saved, name % region)
        if os.path.isfile(path):
            for k, items in json.load(open(path))[key].items():
                layout["groups"].setdefault(k, []).extend(items)
    available, _ = user_pack.resolve(manifest)
    available = {s: [(m, v) for m, v in vs if m in bounds] for s, vs in available.items()}
    available = {s: vs for s, vs in available.items() if vs}
    user_pack.plan(layout, manifest, available, bounds)
    poses = []
    dist = {"dock.forklift": 9.0, "vehicle.parked.suv": 9.0, "vehicle.parked.pickup": 9.0, "person.idle": 5.0,
            "street.bike_parked": 4.5, "dock.pallet_stack": 7.0, "dock.pallet_load": 7.0, "yard.drum": 6.0,
            "dock.pallet_jack": 6.0}
    for key in sorted(layout["groups"]):
        if not key.startswith("UP_") or not key.endswith("|pack"):
            continue
        slot = next((s for s in available for m, _v in available[s] if key == m + "|pack"), None)
        items = layout["groups"][key]
        step = max(1, len(items) // (per + 1))
        for i, it in enumerate(items[step::step][:per]):
            x, y, z, yaw = it[:4]
            d = dist.get(slot, 7.0) * 100.0
            # From the open side, a little off axis: a forklift faces its dock door (look from behind it), a pallet
            # jack stands side-on to the door, everything else faces out of the lot or along the sidewalk.
            view = yaw + {"dock.forklift": 215.0, "dock.pallet_jack": -55.0}.get(slot, 35.0)
            cx, cy = x + d * math.cos(math.radians(view)), y + d * math.sin(math.radians(view))
            look = math.degrees(math.atan2(y - cy, x - cx))
            poses.append({"name": "%s_%d" % (key.split("|")[0][3:], i), "v8_file": slot, "cam_ue": [round(cx), round(cy), round(z + 170)],
                          "yaw": round(look, 1), "pitch": -8.0})
    json.dump({"poses": poses, "spots": []}, open(out, "w"), indent=1)
    print(len(poses), "poses ->", out)


main()
