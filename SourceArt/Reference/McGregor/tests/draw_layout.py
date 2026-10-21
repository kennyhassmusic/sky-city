"""Draws the test-stand layout (Saved/McGregor/site_features.json -> tests) over imagery crops in the site frame, to check
the trenches, aprons, pads, cells and test sites against the photos. Reference only (mcgregor-tests agent, 20 Oct 2026).
Run: python3 -I SourceArt/Reference/McGregor/tests/draw_layout.py  (fetches the crops with make_crops.py, needs network)"""
import json, pathlib, subprocess, sys
from PIL import Image, ImageDraw
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
F = json.load(open(ROOT / "Saved/McGregor/site_features.json"))
T = F["tests"]
VIEWS = {"RN": (690, 1000, 570, 730), "RS": (670, 990, 150, 300), "RV": (-175, -20, 215, 360), "S2": (940, 1060, -800, -660), "FS": (-240, -90, -800, -540)}
MPP = 0.3
for vid, (x0, x1, y0, y1) in VIEWS.items():
    img = HERE / f"_esri_{vid}.jpg"
    if not img.exists():
        subprocess.run([sys.executable, "-I", str(HERE / "make_crops.py"), "esri", str(x0), str(x1), str(y0), str(y1), str(MPP), str(img), "10"], check=True)
    im = Image.open(img).convert("RGB")
    d = ImageDraw.Draw(im)
    P = lambda p: ((p[0] - x0) / MPP, (y1 - p[1]) / MPP)
    for tid, tr in T["trenches"].items():
        d.polygon([P(p) for p in tr["rim"]], outline=(255, 40, 40), width=3)
    for aid, a in T["aprons"].items():
        d.polygon([P(p) for p in a["ring"]], outline=(40, 160, 255), width=3)
    for pid, ring in T["pads"].items():
        d.polygon([P(p) for p in ring], outline=(255, 220, 60), width=2)
    for s in T["engine_tests"]["sites"]:
        n, e = P(s["nozzle"]), P(s["exit"])
        d.ellipse([n[0] - 6, n[1] - 6, n[0] + 6, n[1] + 6], outline=(255, 255, 255), width=3)
        d.line([n, e], fill=(255, 140, 0), width=2)
        d.ellipse([e[0] - 5, e[1] - 5, e[0] + 5, e[1] + 5], fill=(255, 140, 0))
    for p in F["placements"]:
        if p["mesh"] in ("SK_RaptorCell", "SK_VertStand", "SK_VertStandS2", "SK_TankH", "SK_TankTall", "SK_DisplayBooster") and x0 < p["p"][0] < x1 and y0 < p["p"][1] < y1:
            c = P(p["p"])
            d.rectangle([c[0] - 8, c[1] - 8, c[0] + 8, c[1] + 8], outline=(0, 255, 120), width=2)
    d.text((8, im.height - 40), "red: trench rims (terrain cut)  blue: aprons  yellow: pads  white->orange: nozzle -> exhaust bay  green: stands / tanks", fill=(255, 255, 255))
    d.text((8, im.height - 24), "imagery: Esri World Imagery (Vantor WV3 2025-04-13), reference only", fill=(255, 255, 255))
    im.save(HERE / f"layout_over_esri_{vid}.jpg", quality=85)
    img.unlink()
    print("->", HERE / f"layout_over_esri_{vid}.jpg")
