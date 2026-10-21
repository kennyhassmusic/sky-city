"""Side-by-side comparisons for the mcgregor-tests note: satellite reference | before | after, from the viewport
captures in Saved/McGregor/shots/site/tests_before_*.png / tests_after_*.png (Saved/MCPScripts/tests_chain.py).
Top-down captures are 1600 x 900 at 90 deg HFOV from (x, y, z): ground width = 2 (z - ground); the satellite crop is
fetched for the same box (make_crops.py, Esri 2025-04-13), so the three panels line up.
Run: python3 -I SourceArt/Reference/McGregor/tests/make_compare.py  -> Saved/McGregor/shots/tests/compare_*.jpg"""
import glob, json, pathlib, subprocess, sys
from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SH = ROOT / "Saved/McGregor/shots/site"
OUT = ROOT / "Saved/McGregor/shots/tests"
OUT.mkdir(parents=True, exist_ok=True)
TOPS = {"rn_top": (845, 640, 230, 17.7), "rs_top": (840, 215, 220, 20.3), "fs_top": (-160, -690, 260, 23.8), "merlin_top": (595, -1310, 200, 25.3)}


def find(tag, name):
    f = sorted(glob.glob(str(SH / f"{tag}_*_{name}.png")))
    return Image.open(f[-1]).convert("RGB") if f else None


def label(im, text):
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 10 + 7 * len(text), 22], fill=(0, 0, 0))
    d.text((5, 5), text, fill=(255, 255, 255))
    return im


W = 800
for name in ["rn_top", "rs_top", "fs_top", "merlin_top", "rn_obl", "rs_obl", "unveil_view", "rv_obl", "s2_obl", "booster"]:
    b, a = find("tests_before", name), find("tests_after", name)
    if not a:
        continue
    panels = []
    if name in TOPS:
        x, y, z, g = TOPS[name]
        half = (z - g)                      # 90 deg HFOV: half-width = height above ground
        hh = half * 720 / 1280
        img = OUT / f"_sat_{name}.jpg"
        if not img.exists():
            subprocess.run([sys.executable, "-I", str(HERE / "make_crops.py"), "esri", str(x - half), str(x + half), str(y - hh), str(y + hh),
                            str(2 * half / 1280), str(img)], check=True)
        panels.append(label(Image.open(img).convert("RGB").resize((W, int(W * 720 / 1280))), "satellite: Esri / Vantor 2025-04-13 (reference)"))
    if b:
        panels.append(label(b.resize((W, int(W * b.height / b.width))), "before (20 Oct, 23:xx)"))
    panels.append(label(a.resize((W, int(W * a.height / a.width))), "after"))
    H = max(p.height for p in panels)
    c = Image.new("RGB", (W * len(panels) + 10 * (len(panels) - 1), H), "white")
    for i, p in enumerate(panels):
        c.paste(p, (i * (W + 10), 0))
    c.save(OUT / f"compare_{name}.jpg", quality=85)
    print("->", OUT / f"compare_{name}.jpg")
