"""Lane 9: the water A/B plan for seed 7 (plain Python): the generator's river, a demo pond (seed 7 has no lake), the
park parcel around the pond, and the camera poses shared by A and B. Writes Saved/Water/plan.json.
python3 -I Scripts/water/prep_water.py <building-types worktree> <zoned_city.json>"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BT, ZONED = sys.argv[1], sys.argv[2]
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(BT, "Scripts", "city"))
import water_geo  # noqa: E402
import city_water  # noqa: E402
import city_waterflow  # noqa: E402

zoned = json.load(open(ZONED))
flow = city_waterflow.document(zoned, "seed7_city")
river = flow["rivers"][0]
POND = (851.0, 1358.0, 24.0)            # inside park p_e9c5e440_a0301 (largest park; inradius ~40 m)
pond_ring = water_geo.pond_outline(*POND)
lake = city_waterflow.lake_record({"id": "demo_pond", "name": "Demo pond (lane 9 test only, not from the generator)"},
                                  city_water._ring(pond_ring), 0.0)
park = None
for p in zoned["parcels"]:
    if p["zone"] == "park" and water_geo._point_in(POND[:2], [tuple(q) for q in p["polygon"]]):
        park = p
st = river["stations"]


def station_near_y(y):
    return min(st, key=lambda s: abs(s["at"][1] - y))


def look(cam, target):
    dx, dy, dz = target[0] - cam[0], target[1] - cam[1], target[2] - cam[2]
    yaw = math.degrees(math.atan2(dx, dy))          # UE yaw: 0 = +X = plan north; +90 = +Y = plan east
    pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
    return {"plan": [round(v, 2) for v in cam], "yaw": round(yaw, 2), "pitch": round(pitch, 2)}


poses = {}
s = station_near_y(697.0)                             # the arterial bridge r_art_034 crosses at (397, 690)
poses["bridge"] = look((s["at"][0] + 4.0, 699.0, 3.2), (s["at"][0] - 3.0, 728.0, -0.5))
s = station_near_y(1000.0)
f = s["flow"]
right = (f[1], -f[0])                                 # downstream-right normal
bank = (s["at"][0] + right[0] * s["width_m"] / 2.0, s["at"][1] + right[1] * s["width_m"] / 2.0)
cam = (bank[0] + right[0] * 3.0, bank[1] + right[1] * 3.0, 1.7)
tgt = (s["at"][0] - f[0] * 38.0 - right[0] * 8.0, s["at"][1] - f[1] * 38.0 - right[1] * 8.0, -0.8)
poses["riverbank"] = look(cam, tgt)
s = station_near_y(760.0)
poses["aerial"] = look((s["at"][0] + 230.0, 520.0, 170.0), (s["at"][0], 800.0, 0.0))
poses["lake"] = look((POND[0] + 30.0, POND[1] - 38.0, 4.0), (POND[0] - 4.0, POND[1] + 6.0, -0.5))
# The car test: on the east bank, facing west across the river, and dropped over the middle.
s = station_near_y(1000.0)
car_bank = (bank[0] + right[0] * 12.0, bank[1] + right[1] * 12.0)
car = {"bank_plan": [round(v, 2) for v in car_bank], "bank_yaw": round(math.degrees(math.atan2(-right[0], -right[1])), 2),
       "drop_plan": [round(v, 2) for v in s["at"]]}
plan = {"river": river, "lake": lake, "pond": list(POND), "park": park and {"id": park["id"], "polygon": park["polygon"]},
        "poses": poses, "car": car, "frame": "plan metres x east y north; UE X = y*100, Y = x*100"}
os.makedirs(os.path.join(ROOT, "Saved", "Water"), exist_ok=True)
json.dump(plan, open(os.path.join(ROOT, "Saved", "Water", "plan.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in poses.items()}), car, park and park["id"])
