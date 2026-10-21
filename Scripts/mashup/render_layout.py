"""Render a saved mashup layout (same rules as the page) to SVG for review.
Usage: python3 -I Scripts/mashup/render_layout.py layout.json out.svg [view_size_m]"""
import json, math, sys, pathlib
here = pathlib.Path(__file__).resolve().parent
D = json.load(open(here / "mashup_data.json"))["cities"]
L = json.load(open(sys.argv[1]))
out = sys.argv[2]
view = float(sys.argv[3]) if len(sys.argv) > 3 else 4200.0
pa = L["playArea"]; cx, cy = pa["x"], pa["y"]
W = H = 1400; k = W / view
P = lambda x, y: (W / 2 + (x - cx) * k, H / 2 - (y - cy) * k)
th = math.radians(L["austin"]["rotationDeg"]); ca, sa = math.cos(th), math.sin(th)
A = lambda x, y: (ca * x - sa * y + L["austin"]["x"], sa * x + ca * y + L["austin"]["y"])
def path(flat, tf, close=False):
    pts = [P(*tf(flat[i], flat[i + 1])) for i in range(0, len(flat), 2)]
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + (" Z" if close else "")
def city(c, color, tf):
    I = lambda x, y: (x, y)
    tf = tf or I
    s = ['<path fill="#bcd8e6" d="' + " ".join(path(r, tf, True) for r in c["water"]["outer"]) + '"/>',
         '<path fill="#f4f3ef" d="' + " ".join(path(r, tf, True) for r in c["water"]["inner"]) + '"/>',
         '<path fill="#d2e5c6" d="' + " ".join(path(r, tf, True) for r in c["parks"]) + '"/>']
    for cls, w in (("ped", .4), ("minor", .8), ("mid", 1.2), ("major", 1.8), ("highway", 3.2)):
        s.append(f'<path fill="none" stroke="{color}" stroke-width="{w}" stroke-linecap="round" d="' + " ".join(path(l[1], tf) for l in c["roads"].get(cls, [])) + '"/>')
    s.append(f'<path fill="none" stroke="{color}" stroke-width="3.4" d="' + " ".join(path(l, tf) for l in c["rail"]["L"]) + '"/>')
    for name, x, y, _ in c["landmarks"]:
        sx, sy = P(*tf(x, y))
        s.append(f'<circle cx="{sx:.0f}" cy="{sy:.0f}" r="4" fill="{color}"/><text x="{sx+7:.0f}" y="{sy+4:.0f}" font-family="Helvetica" font-size="15" font-weight="bold" fill="{color}" stroke="#f4f3ef" stroke-width="3" paint-order="stroke">{name.upper()}</text>')
    return "\n".join(s)
sm = L["seam"]; a = math.radians(sm["angleDeg"]); dx, dy = math.cos(a), math.sin(a); nx, ny = -dy, dx; BIG = 60000
def half(sgn):
    pts = [(sm["x"] - dx * BIG, sm["y"] - dy * BIG), (sm["x"] + dx * BIG, sm["y"] + dy * BIG),
           (sm["x"] + dx * BIG + nx * BIG * sgn, sm["y"] + dy * BIG + ny * BIG * sgn), (sm["x"] - dx * BIG + nx * BIG * sgn, sm["y"] - dy * BIG + ny * BIG * sgn)]
    return "M" + " L".join(f"{P(*p)[0]:.0f},{P(*p)[1]:.0f}" for p in pts) + " Z"
chi_sgn = -1 if sm["chicagoSide"] == "south" else 1
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"><rect width="100%" height="100%" fill="#f4f3ef"/>',
       f'<defs><clipPath id="chi"><path d="{half(chi_sgn)}"/></clipPath><clipPath id="aus"><path d="{half(-chi_sgn)}"/></clipPath></defs>']
if L["mode"] == "stitch":
    svg += ['<g clip-path="url(#chi)">' + city(D["chicago"], "#2c5d8f", None) + "</g>",
            '<g clip-path="url(#aus)">' + city(D["austin"], "#bf5700", A) + "</g>"]
    p1, p2 = P(sm["x"] - dx * BIG, sm["y"] - dy * BIG), P(sm["x"] + dx * BIG, sm["y"] + dy * BIG)
    svg.append(f'<line x1="{p1[0]:.0f}" y1="{p1[1]:.0f}" x2="{p2[0]:.0f}" y2="{p2[1]:.0f}" stroke="#1d2227" stroke-width="1.5" stroke-dasharray="10 6"/>')
else:
    svg += [city(D["chicago"], "#2c5d8f", None), f'<g opacity="{L.get("austinOpacity", .85)}">' + city(D["austin"], "#bf5700", A) + "</g>"]
h = pa["sizeM"] / 2; x0, y0 = P(cx - h, cy + h)
svg.append(f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{pa["sizeM"]*k:.0f}" height="{pa["sizeM"]*k:.0f}" fill="none" stroke="#bf5700" stroke-width="2.5"/>')
# 500 m grid ticks + scale bar
svg.append(f'<line x1="30" y1="{H-30}" x2="{30+500*k:.0f}" y2="{H-30}" stroke="#1d2227" stroke-width="3"/><text x="{36+500*k:.0f}" y="{H-25}" font-family="Helvetica" font-size="15">500 m</text>')
svg.append("</svg>")
open(out, "w").write("\n".join(svg))
print("wrote", out)
