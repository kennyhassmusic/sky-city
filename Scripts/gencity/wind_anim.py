"""Animated GIFs and stills from a wind proof run (wind_shots_gencity_ue.py): per subject, wind off still, wind on still,
the wind-on frames as a GIF at fps, and an off | on side-by-side GIF. Needs Pillow (no ffmpeg on this Mac).
  python3 Scripts/gencity/wind_anim.py Saved/GenCity/wind_<tag>.json <out dir> [prefix=lane8_wind] [fps=10] [width=960]
"""
import json
import os
import sys

from PIL import Image, ImageDraw


def main(argv):
    run = json.load(open(argv[0]))
    out = argv[1]
    kv = dict(a.split("=", 1) for a in argv[2:] if "=" in a)
    prefix = kv.get("prefix", "lane8_wind")
    fps = float(kv.get("fps", "10"))
    width = int(kv.get("width", "960"))
    os.makedirs(out, exist_ok=True)
    by = {}
    for c in run["clips"]:
        if c.get("file") and os.path.isfile(c["file"]):
            by.setdefault(c["subject"], {}).setdefault(c["state"], []).append((c["k"], c["file"]))
    made = []
    for subject, states in sorted(by.items()):
        def load(path):
            im = Image.open(path).convert("RGB")
            return im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
        on = [load(f) for _, f in sorted(states.get("on", []))]
        off = [load(f) for _, f in sorted(states.get("off", []))]
        if off:
            p = os.path.join(out, "%s_%s_off.jpg" % (prefix, subject))
            off[0].save(p, quality=90)
            made.append(p)
        if on:
            p = os.path.join(out, "%s_%s_on.jpg" % (prefix, subject))
            on[0].save(p, quality=90)
            made.append(p)
            p = os.path.join(out, "%s_%s_on.gif" % (prefix, subject))
            pal = [f.quantize(colors=255, method=Image.MEDIANCUT) for f in on]
            pal[0].save(p, save_all=True, append_images=pal[1:], duration=int(1000 / fps), loop=0)
            made.append(p)
        if on and off:
            w, h = on[0].size
            frames = []
            for i, f in enumerate(on):
                sb = Image.new("RGB", (w * 2 + 8, h + 28), (20, 20, 20))
                sb.paste(off[min(i, len(off) - 1)], (0, 28))
                sb.paste(f, (w + 8, 28))
                d = ImageDraw.Draw(sb)
                d.text((10, 8), "WIND OFF (before: stiff)", fill=(255, 255, 255))
                d.text((w + 18, 8), "WIND ON (city wind field)", fill=(255, 255, 255))
                frames.append(sb.resize((sb.width // 2 * 2 * 3 // 4, sb.height * 3 // 4), Image.LANCZOS)
                              .quantize(colors=255, method=Image.MEDIANCUT))
            p = os.path.join(out, "%s_%s_off_vs_on.gif" % (prefix, subject))
            frames[0].save(p, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0)
            made.append(p)
    print("\n".join(made))


if __name__ == "__main__":
    main(sys.argv[1:])
