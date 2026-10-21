"""Render an integrated city plan (from integrate_layout.py) to SVG for review.
Usage: python3 -I Scripts/mashup/render_plan.py plan.json out.svg"""
import json, sys

plan = json.load(open(sys.argv[1]))
x0, y0, x1, y1 = plan["bounds"]
W = 1400
k = W / (x1 - x0)
H = round((y1 - y0) * k)
P = lambda p: (round((p[0] - x0) * k, 1), round((y1 - p[1]) * k, 1))
COL = {"chicago": "#2c5d8f", "austin": "#bf5700", "new": "#6b3fa0"}
WID = {"ped": .4, "minor": .9, "mid": 1.3, "major": 1.9, "highway": 3.4, "boulevard": 7}


def d(pts, close=False):
    return "M" + " L".join(f"{x},{y}" for x, y in map(P, pts)) + (" Z" if close else "")


s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"><rect width="100%" height="100%" fill="#f4f3ef"/>',
     '<path fill="#bcd8e6" d="' + " ".join(d(r, True) for r in plan["water"]["outer"]) + '"/>',
     '<path fill="#f4f3ef" d="' + " ".join(d(r, True) for r in plan["water"]["inner"]) + '"/>',
     '<path fill="#d2e5c6" d="' + " ".join(d(r, True) for r in plan["parks"]) + '"/>']
for cls in ("ped", "minor", "mid", "major", "highway", "boulevard"):
    for city in ("chicago", "austin", "new"):
        lines = [r["pts"] for r in plan["roads"] if r["cls"] == cls and r["city"] == city]
        if lines:
            s.append(f'<path fill="none" stroke="{COL[city]}" stroke-width="{WID[cls]}" stroke-linecap="round" stroke-linejoin="round" '
                     f'stroke-opacity="{0.9 if cls != "boulevard" else 0.55}" d="' + " ".join(d(l) for l in lines) + '"/>')
for r in plan["rail"]:
    if r["kind"] == "L":
        c = COL[r["city"]]
        s.append(f'<path fill="none" stroke="{c}" stroke-width="{5 if r["city"] == "new" else 3.4}" stroke-dasharray="{"8 4" if r["city"] == "new" else "none"}" d="{d(r["pts"])}"/>')
for lm in plan["landmarks"]:
    if lm["outline"]:
        s.append(f'<path fill="{COL[lm["city"]]}" d="{d(lm["outline"], True)}"/>')
    x, y = P(lm["pos"])
    s.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{COL[lm["city"]]}"/><text x="{x+7}" y="{y+5}" font-family="Helvetica" font-size="15" '
             f'font-weight="bold" fill="{COL[lm["city"]]}" stroke="#f4f3ef" stroke-width="3" paint-order="stroke">{lm["name"].upper()}</text>')
px0, py0, px1, py1 = plan["playArea"]
a, b = P((px0, py1)), P((px1, py0))
s.append(f'<rect x="{a[0]}" y="{a[1]}" width="{b[0]-a[0]}" height="{b[1]-a[1]}" fill="none" stroke="#bf5700" stroke-width="2.5" stroke-dasharray="14 6"/>')
s.append(f'<line x1="30" y1="{H-30}" x2="{30+500*k:.0f}" y2="{H-30}" stroke="#1d2227" stroke-width="3"/><text x="{36+500*k:.0f}" y="{H-25}" font-family="Helvetica" font-size="15">500 m</text>')
s.append("</svg>")
open(sys.argv[2], "w").write("\n".join(s))
print("wrote", sys.argv[2])
