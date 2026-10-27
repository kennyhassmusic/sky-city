"""Lane 9: parse the ProfileGPU dumps in a shots log: per (mode, pose) the frame's GPU total and the water passes.
python3 -I Scripts/water/gpu_water.py <log>"""
import json
import re
import sys

lines = open(sys.argv[1], errors="replace").read().splitlines()
out, cur = {}, None
KEYS = ("water", "translucen", "lumen reflections", "reflections", "basepass", "singlelayer", "info")
for ln in lines:
    m = re.search(r"LANE9 PROFILEGPU (\S+) (\S+)", ln)
    if m:
        cur = "%s_%s" % m.groups()
        out[cur] = {"frame_ms": None, "passes": {}}
        continue
    if cur is None or "┃" not in ln:
        continue
    cols = ln.split("┃")
    if len(cols) < 4:
        continue
    name = cols[-2].strip()
    t = re.findall(r"([\d.]+) ms", cols[-3])
    if not name or not t:
        continue
    incl = float(t[-1])
    if name.startswith("Frame ") and out[cur]["frame_ms"] is None:
        out[cur]["frame_ms"] = incl
    low = name.lower()
    if any(k in low for k in KEYS) and incl >= 0.05:
        key = name[:60]
        if key not in out[cur]["passes"]:
            out[cur]["passes"][key] = incl
print(json.dumps(out, indent=1))
