"""Render an integrated plan (integrate_v2.py) as one city: shared colours by road class, no city tint.
Usage: python3 -I Scripts/mashup/render_plan_v2.py plan.json out.svg [--debug]
--debug draws new and stitched roads in purple and the seam as a faint dashed line."""
import json, sys

plan = json.load(open(sys.argv[1]))
debug = "--debug" in sys.argv
x0, y0, x1, y1 = plan["bounds"]
W = 1400
k = W / (x1 - x0)
H = round((y1 - y0) * k)
P = lambda p: (round((p[0] - x0) * k, 1), round((y1 - p[1]) * k, 1))
# one palette for the whole city (metres -> px widths roughly to scale)
LAND, WATER, PARK, SAND = "#efece4", "#a9cfe0", "#cfe2bf", "#ecdcb0"
ROAD = {"ped": ("#d9d4c8", .6), "minor": ("#ffffff", 2.2), "mid": ("#fbf3d5", 3.2),
        "major": ("#f6d98a", 4.2), "highway": ("#e8a54b", 6.4)}
CASING = "#b9b2a3"


def d(pts, close=False):
    return "M" + " L".join(f"{x},{y}" for x, y in map(P, pts)) + (" Z" if close else "")


s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"><rect width="100%" height="100%" fill="{LAND}"/>',
     f'<path fill="{PARK}" d="' + " ".join(d(r, True) for r in plan["parks"]) + '"/>',
     f'<path fill="{SAND}" d="' + " ".join(d(r, True) for r in plan.get("beaches", [])) + '"/>',
     f'<path fill="{WATER}" d="' + " ".join(d(r, True) for r in plan["water"]["outer"]) + '"/>',
     f'<path fill="{LAND}" d="' + " ".join(d(r, True) for r in plan["water"]["inner"]) + '"/>']
order = ("ped", "minor", "mid", "major", "highway")
# casings first, then fills, so junctions merge cleanly
for cls in order:
    col, w = ROAD[cls]
    lines = [r["pts"] for r in plan["roads"] if r["cls"] == cls]
    if cls != "ped" and lines:
        s.append(f'<path fill="none" stroke="{CASING}" stroke-width="{w + 1.6}" stroke-linecap="round" stroke-linejoin="round" d="' + " ".join(d(l) for l in lines) + '"/>')
for cls in order:
    col, w = ROAD[cls]
    lines = [r["pts"] for r in plan["roads"] if r["cls"] == cls and not (debug and r.get("new"))]
    if lines:
        s.append(f'<path fill="none" stroke="{col}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round" d="' + " ".join(d(l) for l in lines) + '"/>')
    if debug:
        new = [r["pts"] for r in plan["roads"] if r["cls"] == cls and r.get("new")]
        if new:
            s.append(f'<path fill="none" stroke="#8a4fd0" stroke-width="{w}" stroke-linecap="round" d="' + " ".join(d(l) for l in new) + '"/>')
# bridges: dark casing so you can see them cross water
for b in plan.get("bridges", []):
    col, w = ROAD.get(b["cls"], ROAD["minor"])
    s.append(f'<path fill="none" stroke="#5c5548" stroke-width="{w + 3}" stroke-linecap="butt" d="{d(b["pts"])}"/>')
    s.append(f'<path fill="none" stroke="{col}" stroke-width="{w}" stroke-linecap="butt" d="{d(b["pts"])}"/>')
# the L
for r in plan["rail"]:
    if r["kind"] == "L":
        s.append(f'<path fill="none" stroke="#4a4f57" stroke-width="3.2" stroke-dasharray="{"7 3" if r["city"] == "stitch" else "none"}" d="{d(r["pts"])}"/>')
    elif r["kind"] == "rail":
        s.append(f'<path fill="none" stroke="#8e8a80" stroke-width="1.2" stroke-dasharray="5 3" d="{d(r["pts"])}"/>')
for lm in plan["landmarks"]:
    if lm["outline"]:
        s.append(f'<path fill="#6d6457" d="{d(lm["outline"], True)}"/>')
    x, y = P(lm["pos"])
    s.append(f'<circle cx="{x}" cy="{y}" r="4" fill="#3d3830"/><text x="{x+7}" y="{y+5}" font-family="Helvetica" font-size="14" '
             f'font-weight="bold" fill="#3d3830" stroke="{LAND}" stroke-width="3" paint-order="stroke">{lm["name"].upper()}</text>')
if debug and plan.get("seam"):
    s.append(f'<path fill="none" stroke="#8a4fd0" stroke-opacity=".35" stroke-width="1.5" stroke-dasharray="6 6" d="{d(plan["seam"])}"/>')
px0, py0, px1, py1 = plan["playArea"]
a, b = P((px0, py1)), P((px1, py0))
s.append(f'<rect x="{a[0]}" y="{a[1]}" width="{b[0]-a[0]}" height="{b[1]-a[1]}" fill="none" stroke="#c0581b" stroke-width="2" stroke-dasharray="14 6"/>')
s.append(f'<line x1="30" y1="{H-30}" x2="{30+500*k:.0f}" y2="{H-30}" stroke="#3d3830" stroke-width="3"/><text x="{36+500*k:.0f}" y="{H-25}" font-family="Helvetica" font-size="14" fill="#3d3830">500 m</text>')
s.append("</svg>")
open(sys.argv[2], "w").write("\n".join(s))
print("wrote", sys.argv[2])
