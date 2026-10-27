"""Lane 9: the A/B pictures to Dropbox: per-pose JPGs, flow GIFs, and the side-by-side sheet.
python3 -I Scripts/water/sheet_water.py <tag> [out dir]"""
import json
import os
import sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TAG = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/Dropbox/Sky City Shots/2026-10-27")
res = json.load(open(os.path.join(ROOT, "Saved", "Water", "shots_%s.json" % TAG)))
os.makedirs(OUT, exist_ok=True)
NAMES = {"A": "A: Unreal Water plugin (Epic default materials)", "B": "B: our own water (code-made textures)"}
POSES = ["bridge", "riverbank", "aerial"]   # the demo-pond shot is not valid yet (park lawn still covers it)
font = ImageFont.load_default()
try:
    font = ImageFont.load_default(size=22)
except TypeError:
    pass
made = []
shots = {(s["mode"], s["pose"]): s["file"] for s in res["shots"] if s.get("file")}
for (mode, pose), f in sorted(shots.items()):
    if pose not in POSES:
        continue
    name = "lane9_water_%s_%s.jpg" % (mode, pose) if mode != "none" else "lane9_water_none_%s.jpg" % pose
    Image.open(f).convert("RGB").save(os.path.join(OUT, name), quality=90)
    made.append(name)
for key, frames in sorted(res["frames"].items()):
    imgs = [Image.open(fr["file"]).convert("RGB").resize((800, 450)) for fr in frames if fr.get("file")]
    if len(imgs) < 2:
        continue
    ts = [fr["t"] for fr in frames if fr.get("file")]
    real = int(1000 * (ts[-1] - ts[0]) / max(1, len(ts) - 1))
    gap = 125                                          # played ~8x faster than captured (one frame per ~1 s)
    name = "lane9_water_%s_flow.gif" % key           # e.g. lane9_water_A_bridge_flow.gif
    pal = [im.quantize(colors=200, method=Image.Quantize.MEDIANCUT) for im in imgs]
    pal[0].save(os.path.join(OUT, name), save_all=True, append_images=pal[1:], duration=gap, loop=0)
    made.append("%s (%d frames, captured %d ms apart, played at %d ms)" % (name, len(imgs), real, gap))
W, H, PADT = 960, 540, 40
modes = [m for m in ("A", "B") if any((m, p) in shots for p in POSES)]
sheet = Image.new("RGB", (W * len(modes), PADT + H * len(POSES)), (24, 24, 24))
d = ImageDraw.Draw(sheet)
for i, m in enumerate(modes):
    d.text((i * W + 12, 8), NAMES[m], fill=(240, 240, 240), font=font)
    for j, p in enumerate(POSES):
        f = shots.get((m, p))
        if f:
            sheet.paste(Image.open(f).convert("RGB").resize((W, H)), (i * W, PADT + j * H))
        d.text((i * W + 12, PADT + j * H + 10), p, fill=(255, 255, 255), font=font)
sheet.save(os.path.join(OUT, "lane9_water_compare.jpg"), quality=88)
made.append("lane9_water_compare.jpg")
print("\n".join(made))
