"""Georeference Kenny's unveil sketch (an Apple Maps screenshot with his marks) into the McGregor site frame and convert
his marks to site metres. Offline; writes Saved/McGregor/unveil_georef.json and the overlay proofs in
SourceArt/Reference/McGregor/unveil/ (georef_overlay.jpg, georef_marks.jpg, georef_side_by_side.jpg).

  1. control points: features visible in both the screenshot and the NAIP aerial / OSM roads (junctions, loop-road
     corners, the pond, a lone tree, a cattle guard), picked by eye on side-by-side zooms (CP list below)
  2. least-squares similarity (scale, rotation, shift; the screenshot is a plain rotated map view) + residuals,
     leave-one-out, and the affine fit for comparison. A brute-force FFT match of the screenshot's road pixels against
     the OSM road raster found the same solution independently (0.51 m/px, 42.5 deg).
  3. Kenny's marks by colour (yellow lot, red line, blue ramp + run-up, green fleet + line, black stage, the two blurred
     white buildings) -> site coordinates (the numbers at the top of demo_layout.py came from here)
Site frame: metres, x east, y north, origin = facility centre (lat 31.40375, lon -97.4621); Unreal X = y*100, Y = x*100.
Run: python3 -I Scripts/mcgregor/georef_sketch.py   (needs numpy, scipy, Pillow; the NAIP tiles on the SkyCity Work drive)"""
import json, math, os, pathlib
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAS = os.environ.get("SKYCITY_MCGREGOR_RAW", str(ROOT / "Saved" / "McGregorRaw"))
REF = ROOT / "SourceArt/Reference/McGregor/unveil"
SKETCH = REF / "09_kenny_layout_sketch_applemaps.webp"
Image.MAX_IMAGE_PIXELS = None
# (name, screenshot px u, v, site E, N)
CP = [
    ("Naval Industrial Reserve x hangar road", 1165, 180, 1901.0, 973.0),
    ("pond basin centre", 1413, 306, 1945.0, 831.0),
    ("west loop road NW corner", 1095, 1113, 1542.0, 639.0),
    ("west loop road SW corner", 1404, 1348, 1577.0, 447.0),
    ("cattle guard on the south road", 1861, 1221, 1790.4, 341.2),
    ("lone tree by the road", 605.4, 178.8, 1680.3, 1161.3),
    ("loop road x parking aisle", 1207, 1003, 1626.0, 648.0),
    ("farm track x Naval Industrial Reserve", 407, 202, 1594.5, 1221.5),
]


def fit(cp):
    u = np.array([c[1] for c in cp], float); v = np.array([c[2] for c in cp], float)
    E = np.array([c[3] for c in cp]); N = np.array([c[4] for c in cp])
    A = np.zeros((2 * len(u), 4)); y = np.zeros(2 * len(u))
    A[0::2, 0], A[0::2, 1], A[0::2, 2], y[0::2] = u, v, 1, E          # E = a u + b v + tx
    A[1::2, 0], A[1::2, 1], A[1::2, 3], y[1::2] = -v, u, 1, N         # N = b u - a v + ty
    a, b, tx, ty = np.linalg.lstsq(A, y, rcond=None)[0]
    return a, b, tx, ty


a, b, tx, ty = fit(CP)
s, th = math.hypot(a, b), math.degrees(math.atan2(-b, a))
to_site = lambda u, v: (a * u + b * v + tx, b * u - a * v + ty)
res = []
for c in CP:
    e, n = to_site(c[1], c[2])
    loo = fit([q for q in CP if q is not c])
    le, ln = loo[0] * c[1] + loo[1] * c[2] + loo[2], loo[1] * c[1] - loo[0] * c[2] + loo[3]
    res.append({"name": c[0], "px": [c[1], c[2]], "site": [c[3], c[4]], "dE": round(e - c[3], 1), "dN": round(n - c[4], 1),
                "r_m": round(math.hypot(e - c[3], n - c[4]), 1), "leave_one_out_m": round(math.hypot(le - c[3], ln - c[4]), 1)})
rms = math.sqrt(sum(r["r_m"] ** 2 for r in res) / len(res))
u_ = np.array([c[1] for c in CP], float); v_ = np.array([c[2] for c in CP], float)
Aa = np.c_[u_, v_, np.ones_like(u_)]
cE = np.linalg.lstsq(Aa, np.array([c[3] for c in CP]), rcond=None)[0]; cN = np.linalg.lstsq(Aa, np.array([c[4] for c in CP]), rcond=None)[0]
aff_rms = float(np.sqrt(np.mean((Aa @ cE - [c[3] for c in CP]) ** 2 + (Aa @ cN - [c[4] for c in CP]) ** 2)))
print("similarity: %.4f m/px, screen-up bearing %.2f deg, px (0,0) at (%.1f, %.1f); RMS %.2f m (affine %.2f m)" % (s, th, tx, ty, rms, aff_rms))
for r in res:
    print("  %-40s dE %+5.1f dN %+5.1f |r| %4.1f  leave-one-out %4.1f" % (r["name"], r["dE"], r["dN"], r["r_m"], r["leave_one_out_m"]))

# ------------------------------------------------------------------ the marks
im = np.asarray(Image.open(SKETCH).convert("RGB")).astype(int)
R, G, B = im[..., 0], im[..., 1], im[..., 2]
H_, W_ = R.shape
yy, xx = np.mgrid[:H_, :W_]
M = {"yellow": (R > 190) & (G > 140) & (B < 90) & (R - B > 120) & (xx < 1300),
     "red": (R > 180) & (G < 90) & (B < 110) & (xx > 580) & (xx < 960) & (yy > 590) & (yy < 1030) & ~((xx < 640) & (yy < 700)),
     "blue": (B > 170) & (R < 90) & (G < 170) & (B - R > 100),
     "green": (G > 170) & (R < 120) & (B < 150) & (G - R > 80) & (xx < 900),
     "black": (im.max(-1) < 38) & (xx > 740) & (xx < 960) & (yy > 680) & (yy < 920),
     "white": (im.min(-1) > 226) & (xx > 930) & (xx < 1320) & (yy > 320) & (yy < 730)}


def line_fit(P):
    c = P.mean(0); d = np.linalg.svd(P - c)[2][0]; t = (P - c) @ d
    return c + d * t.min(), c + d * t.max(), d, c


def ix(l1, l2):
    t = np.linalg.solve(np.array([l1[2], -l2[2]]).T, l2[3] - l1[3])
    return l1[3] + l1[2] * t[0]


S = lambda p: [round(float(q), 1) for q in to_site(*p)]
marks = {}
P = np.c_[np.nonzero(M["yellow"])[::-1]].astype(float)
C0 = {"N": (726, 423), "E": (1077, 719), "S": (766, 1133), "W": (493, 905)}
edges = {"NE": ("N", "E"), "SE": ("E", "S"), "SW": ("S", "W"), "NW": ("W", "N")}


def segd(p, a_, b_):
    a_, b_ = np.array(a_, float), np.array(b_, float); ab = b_ - a_
    t = np.clip(((p - a_) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(p - (a_ + np.outer(t, ab)), axis=1)


Dd = np.stack([segd(P, C0[e[0]], C0[e[1]]) for e in edges.values()], 1)
Ls = {k: line_fit(P[(Dd.argmin(1) == i) & (Dd.min(1) < 8)]) for i, k in enumerate(edges)}
lot_px = {"N": ix(Ls["NW"], Ls["NE"]), "E": ix(Ls["NE"], Ls["SE"]), "S": ix(Ls["SE"], Ls["SW"]), "W": ix(Ls["SW"], Ls["NW"])}
marks["lot"] = {k: S(v) for k, v in lot_px.items()}
l = line_fit(np.c_[np.nonzero(M["red"])[::-1]].astype(float)); marks["red_line"] = [S(l[0]), S(l[1])]
P = np.c_[np.nonzero(M["blue"])[::-1]].astype(float)
l = line_fit(P[P[:, 1] > 632]); marks["runup_line"] = [S(l[1]), S(l[0])]          # start, ramp end
poly = P[P[:, 1] <= 632]; marks["ramp_scribble_centroid"] = S(poly.mean(0))
P = np.c_[np.nonzero(M["green"])[::-1]].astype(float)
circ = (P[:, 0] > 775) & (P[:, 1] < 675)
l = line_fit(P[~circ]); marks["fleet_line"] = [S(l[1]), S(l[0])]
marks["fleet_circle"] = S(P[circ].mean(0))
P = np.c_[np.nonzero(M["black"])[::-1]].astype(float); marks["stage_centroid"] = S(P.mean(0))
lb, n = ndimage.label(M["white"])
sizes = ndimage.sum(M["white"], lb, range(1, n + 1))
blds = []
for i in np.argsort(sizes)[::-1][:2]:
    Pp = np.c_[np.nonzero(lb == i + 1)[::-1]].astype(float); c = Pp.mean(0)
    vt = np.linalg.svd(Pp - c, full_matrices=False)[2]
    t1, t2 = (Pp - c) @ vt[0], (Pp - c) @ vt[1]
    lo1, hi1 = np.percentile(t1, [1, 99]); lo2, hi2 = np.percentile(t2, [1, 99])
    cen = c + vt[0] * (lo1 + hi1) / 2 + vt[1] * (lo2 + hi2) / 2
    blds.append({"centre": S(cen), "len_m": round(float(hi1 - lo1) * s, 1), "wid_m": round(float(hi2 - lo2) * s, 1),
                 "long_axis_bearing": round((math.degrees(math.atan2(vt[0][0], -vt[0][1])) + th) % 180, 1)})
marks["buildings"] = {"Roadster building (small)": blds[1], "other building (large)": blds[0]}
out = {"similarity": {"m_per_px": round(s, 4), "up_bearing_deg": round(th, 2), "px0_site": [round(tx, 1), round(ty, 1)],
                      "rms_m": round(rms, 2), "affine_rms_m": round(aff_rms, 2)}, "control_points": res, "marks": marks}
json.dump(out, open(ROOT / "Saved/McGregor/unveil_georef.json", "w"), indent=1)
print(json.dumps(marks, indent=1))

# ------------------------------------------------------------------ overlay proofs
M_ = json.load(open(RAS + "/rasters.json"))
D = json.load(open(ROOT / "Saved/McGregor/mcgregor_data.json"))
L = json.load(open(ROOT / "Saved/McGregor/demo_layout.json"))


def naip(x0, y0, x1, y1, mpp):
    can = Image.new("RGB", (int((x1 - x0) / mpp), int((y1 - y0) / mpp)))
    for t in [dict(t) for t in M_["tiles"]] + [dict(M_["demo"])]:
        X0, Y0, sz = t["x0"], t["y0"], t["size_m"]
        if X0 > x1 or X0 + sz < x0 or Y0 > y1 or Y0 + sz < y0:
            continue
        ti = Image.open(RAS + "/" + t["file"]); tm = sz / ti.size[0]
        ax0, ax1, ay0, ay1 = max(x0, X0), min(x1, X0 + sz), max(y0, Y0), min(y1, Y0 + sz)
        c = ti.crop((int((ax0 - X0) / tm), int((Y0 + sz - ay1) / tm), int((ax1 - X0) / tm), int((Y0 + sz - ay0) / tm)))
        can.paste(c.resize((max(1, int((ax1 - ax0) / mpp)), max(1, int((ay1 - ay0) / mpp))), Image.LANCZOS), (int((ax0 - x0) / mpp), int((y1 - ay1) / mpp)))
    return can


def warped(x0, y0, x1, y1, mpp):
    # inverse similarity: u = (a (E - tx) + b (N - ty)) / s^2 ; v = (b (E - tx) - a (N - ty)) / s^2
    s2 = a * a + b * b
    A0, A1, A2 = a * mpp / s2, -b * mpp / s2, (a * (x0 - tx) + b * (y1 - ty)) / s2
    B0, B1, B2 = b * mpp / s2, a * mpp / s2, (b * (x0 - tx) - a * (y1 - ty)) / s2
    sk = Image.open(SKETCH).convert("RGBA")
    return sk.transform((int((x1 - x0) / mpp), int((y1 - y0) / mpp)), Image.AFFINE, (A0, A1, A2, B0, B1, B2), resample=Image.BICUBIC)


X0, Y0, X1, Y1, MPP = 1250.0, 300.0, 2450.0, 1400.0, 0.6
base = naip(X0, Y0, X1, Y1, MPP).convert("RGBA")
w = np.asarray(warped(X0, Y0, X1, Y1, MPP)).copy(); w[..., 3] = (w[..., 3] * 0.55).astype(np.uint8)
ov = Image.alpha_composite(base, Image.fromarray(w))
d = ImageDraw.Draw(ov)
Pp = lambda p: ((p[0] - X0) / MPP, (Y1 - p[1]) / MPP)
for r in D["roads"]:
    d.line([Pp(q) for q in r["pts"]], fill=(255, 0, 255, 255), width=2)
for c, r in zip(CP, res):
    q = Pp((c[3], c[4])); e = Pp(to_site(c[1], c[2]))
    d.ellipse([q[0] - 7, q[1] - 7, q[0] + 7, q[1] + 7], outline=(0, 255, 255, 255), width=3)
    d.line([q, (q[0] + (e[0] - q[0]) * 5, q[1] + (e[1] - q[1]) * 5)], fill=(255, 255, 0, 255), width=3)
    d.text((q[0] + 9, q[1] - 6), f"{r['name']} {r['r_m']} m", fill=(255, 255, 255, 255))
d.rectangle([0, 0, 1180, 46], fill=(0, 0, 0, 200))
d.text((8, 6), f"Kenny's sketch warped onto the NAIP 2022 aerial (site frame, north up). Magenta: OSM roads. Cyan: control points, "
               f"yellow: residual x5.", fill=(255, 255, 255, 255))
d.text((8, 24), f"Similarity fit: {s:.3f} m/px, screenshot up = bearing {th:.1f} deg, RMS {rms:.1f} m over {len(CP)} points (affine {aff_rms:.1f} m).", fill=(255, 255, 255, 255))
ov.convert("RGB").save(REF / "georef_overlay.jpg", quality=88)


def draw_marks(img, X0, Y1, mpp, layout=True):
    d = ImageDraw.Draw(img)
    Pq = lambda p: ((p[0] - X0) / mpp, (Y1 - p[1]) / mpp)
    lot = [marks["lot"][k] for k in "NESW"]
    d.polygon([Pq(p) for p in lot], outline=(255, 210, 0), width=4)
    d.line([Pq(p) for p in marks["red_line"]], fill=(255, 40, 40), width=4)
    d.line([Pq(p) for p in marks["runup_line"]], fill=(60, 140, 255), width=4)
    d.line([Pq(p) for p in marks["fleet_line"]], fill=(0, 230, 90), width=4)
    q = Pq(marks["fleet_circle"]); d.ellipse([q[0] - 12 / mpp, q[1] - 12 / mpp, q[0] + 12 / mpp, q[1] + 12 / mpp], outline=(0, 230, 90), width=3)
    q = Pq(marks["ramp_scribble_centroid"]); d.rectangle([q[0] - 10, q[1] - 10, q[0] + 10, q[1] + 10], outline=(60, 140, 255), width=4)
    for bnm, bb in marks["buildings"].items():
        r_ = math.radians(bb["long_axis_bearing"]); axv, nyv = (math.sin(r_), math.cos(r_)), (math.cos(r_), -math.sin(r_))
        cs = [(bb["centre"][0] + axv[0] * i * bb["len_m"] / 2 + nyv[0] * j * bb["wid_m"] / 2, bb["centre"][1] + axv[1] * i * bb["len_m"] / 2 + nyv[1] * j * bb["wid_m"] / 2)
              for i, j in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
        d.polygon([Pq(p) for p in cs], outline=(255, 255, 255), width=3)
        d.text(Pq(bb["centre"]), bnm, fill=(255, 255, 255))
    if layout:
        st = L["stage"]; r_ = math.radians(st["yaw"]); f = (math.sin(r_), math.cos(r_)); axv = (math.sin(r_ - math.pi / 2), math.cos(r_ - math.pi / 2))
        cs = [(st["p"][0] + axv[0] * i * st["len"] / 2 + f[0] * j * st["dep"] / 2, st["p"][1] + axv[1] * i * st["len"] / 2 + f[1] * j * st["dep"] / 2) for i, j in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
        d.polygon([Pq(p) for p in cs], fill=(15, 15, 15), outline=(255, 60, 40))
    return d


mk = naip(X0, Y0, X1, Y1, MPP)
d = draw_marks(mk, X0, Y1, MPP)
Pp = lambda p: ((p[0] - X0) / MPP, (Y1 - p[1]) / MPP)
POLES = [(1642.2, 535.2), (1634.8, 572.3), (1625.6, 619.1), (1605.1, 689.5), (1588.5, 744.8), (1566.9, 804.5), (1546.4, 866.1), (1529.2, 920.6),
         (1517.9, 980.8), (1511.8, 1001.8), (1474.1, 1047.7), (1433.1, 1093.3), (1393.0, 1139.0), (1354.5, 1185.7), (1314.1, 1230.9), (1273.6, 1277.1)]
d.line([Pp(p) for p in POLES], fill=(255, 140, 0), width=2)
for p in POLES:
    q = Pp(p); d.ellipse([q[0] - 5, q[1] - 5, q[0] + 5, q[1] + 5], fill=(255, 140, 0))
ramp, tr = L["ramp"]["p"], math.radians(L["ramp"]["yaw"])
for b0, b1 in ((25, 80),):
    a0 = (ramp[0] - math.sin(tr) * b0, ramp[1] - math.cos(tr) * b0); a1 = (ramp[0] - math.sin(tr) * b1, ramp[1] - math.cos(tr) * b1)
    d.line([Pp(a0), Pp(a1)], fill=(255, 255, 255), width=9)
cx = L["poles_check"]["crossing"]
if cx:
    q = Pp(cx["at"]); d.ellipse([q[0] - 9, q[1] - 9, q[0] + 9, q[1] + 9], outline=(255, 255, 255), width=3)
d.rectangle([0, 0, 1300, 64], fill=(0, 0, 0))
d.text((8, 6), "Kenny's marks in the site frame (north up, NAIP 2022): yellow lot, red staging|performance line, blue run-up (+ ramp square), green fleet line + circle,", fill=(255, 255, 255))
d.text((8, 24), "white buildings (Apple's blurred footprints), black: the stage as built. Orange: the OSM-mapped telephone line (poles = dots, mapped ~2016).", fill=(255, 255, 255))
d.text((8, 42), f"Thick white: where the car comes back down after the ramp (25-80 m back along the run-up). The line crosses the run-up {cx['back_from_ramp_m'] if cx else '-'} m before the ramp; nearest pole to the X: {L['poles_check']['nearest_pole_to_X_m']} m.", fill=(255, 255, 255))
mk.save(REF / "georef_marks.jpg", quality=88)
# side by side: the screenshot as Kenny drew it | the same area rotated north-up over the aerial
sk = Image.open(SKETCH).convert("RGB").resize((1000, 696))
right = Image.alpha_composite(base, Image.fromarray(w)).convert("RGB").resize((1000, int(1000 * (Y1 - Y0) / (X1 - X0))))
sbs = Image.new("RGB", (2010, max(696, right.size[1])), (20, 20, 20))
sbs.paste(sk, (0, 0)); sbs.paste(right, (1010, 0))
ImageDraw.Draw(sbs).text((8, 670), "Kenny's screenshot (its up = bearing %.0f deg: the compass's red tick points up-left)" % th, fill=(255, 255, 0))
ImageDraw.Draw(sbs).text((1018, 6), "the same, warped north-up onto the NAIP aerial", fill=(255, 255, 0))
sbs.save(REF / "georef_side_by_side.jpg", quality=85)
print("wrote", REF / "georef_overlay.jpg", REF / "georef_marks.jpg", REF / "georef_side_by_side.jpg")
