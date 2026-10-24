"""Walkup street-level decals: grime, faded wall ads, shop signs and gates.

walkup.py dresses the brick walk-ups with these the way kit_layout.py dresses
the rest of the kit: wall decals (KIT_Decal) and storefront fittings. Pure
procedural art (Pillow + NumPy, no AI, no network), RGBA PNGs with soft or
masked alpha so they read as grime and paint on the brick swatches
(brick_swatches.py) underneath, not as a sticker.

Writes SourceArt/CityGen/kit/decals/<name>.png and decals.json there:
  {name: {file, size_m: [w, h]}}.

  streak_01..03  (0.9 x 1.2 m)  dark grime streaks down from the top edge, soft alpha.
  soot_01..02    (4.0 x 1.2 m)  a soot band, darkest at the top, fading down.
  shop_<kind>    (2.4 x 2.4 m)  a shop's back wall seen through its window (grocery, bar, laundry, clothes, empty).
  ghost_01..06   (6.0 x 4.0 m)  faded painted wall ads, generic words, heavily worn.
  sign_01..10    (4.0 x 0.6 m)  shop-sign lettering, generic words, transparent background.
  gate_rolldown  (2.0 x 2.0 m)  corrugated steel roll-down gate slats, opaque.
  gate_accordion (2.0 x 2.0 m)  accordion security-gate lattice, transparent background.
  plywood        (2.0 x 2.0 m)  plywood boarding with screws and a stain, opaque.

No real brand names: ghost signs and shop signs use generic trade words only
(AGENTS.md). Fonts: the env var SKYCITY_FONT, else the first of a few macOS
system fonts that exists; fails with a clear message if none do.

Run (plain Python 3 with Pillow and NumPy):
  python3 -I Scripts/city/walkup_decals.py
Safe to rerun: deterministic seeds, same files. SKYCITY_ROOT overrides the project folder.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

PX_PER_M = {
    "streak": 150, "soot": 100, "ghost": 80, "sign": 150, "shop": 200,
    "gate_rolldown": 150, "gate_accordion": 150, "plywood": 150,
}
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)
GHOST_WORDS = ("FURNITURE", "HOTEL ROOMS", "COAL & ICE", "DRY GOODS", "HARDWARE", "BAKERY - FRESH DAILY")
SIGN_WORDS = ("GROCERY", "TAQUERIA", "LAUNDROMAT", "BARBER", "DELI", "TAVERN", "BOOKS", "TAILOR", "HARDWARE", "CAFE")
GHOST_PAINTS = ((228, 220, 200), (240, 236, 224), (226, 196, 96), (176, 58, 46), (222, 214, 190), (234, 224, 198))
SIGN_INKS = ((196, 160, 64), (240, 238, 230), (226, 214, 180), (210, 176, 90), (238, 236, 228))


def _root():
    env = os.environ.get("SKYCITY_ROOT")
    if env:
        return env
    d = _HERE
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "SkyCity.uproject")):
            return d
        d = os.path.dirname(d)
    raise SystemExit("SkyCity.uproject not found")


def _font_path():
    env = os.environ.get("SKYCITY_FONT")
    if env:
        if not os.path.isfile(env):
            raise SystemExit("SKYCITY_FONT=%s does not exist" % env)
        return env
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    raise SystemExit("no usable font found; set SKYCITY_FONT to a .ttf/.ttc path")


def _font(size):
    return ImageFont.truetype(_font_path(), size)


def _hash(seed, *vals):
    x = np.zeros_like(vals[0], dtype=np.float64) + float(seed) * 37.719
    for k, v in enumerate(vals):
        x = x + v.astype(np.float64) * (12.9898 + 17.233 * k) + 78.233 * k
    frac = np.sin(x) * 43758.5453
    return frac - np.floor(frac)


def _size_px(kind, size_m):
    px = PX_PER_M[kind]
    return (max(8, int(round(size_m[0] * px))), max(8, int(round(size_m[1] * px))))


def _rgba(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


# ------------------------------------------------------------------ streaks, soot, patches


def streak(seed, size_m):
    """Rain-washed grime running down from a sill or coping: dark, opaque near the top, soft sides."""
    w, h = _size_px("streak", size_m)
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    n_streaks = 5 + int(5 * _hash(seed, np.array([0]), np.array([0]))[0])
    alpha = np.zeros((h, w), dtype=np.float64)
    # A grime band right under the ledge, then the runs.
    alpha = np.maximum(alpha, np.clip(1.0 - yy / (h * 0.12), 0.0, 1.0) ** 1.2 * 0.75)
    for i in range(n_streaks):
        cx = (0.05 + 0.9 * _hash(seed, np.array([i]), np.array([1]))[0]) * w
        width = (0.05 + 0.12 * _hash(seed, np.array([i]), np.array([2]))[0]) * w
        length = (0.45 + 0.55 * _hash(seed, np.array([i]), np.array([3]))[0]) * h
        strength = 0.6 + 0.35 * _hash(seed, np.array([i]), np.array([4]))[0]
        wiggle = (_hash(seed, np.array([i]), (yy[:, 0] // 8)) - 0.5) * width * 0.5
        dx = xx - (cx + wiggle[:, None])
        band = np.clip(1.0 - np.abs(dx) / (width * 0.5), 0.0, 1.0) ** 1.2
        fade = np.clip(1.0 - yy / length, 0.0, 1.0) ** 0.9
        alpha = np.maximum(alpha, band * fade * strength)
    shade = 22.0 + 18.0 * _hash(seed + 3, xx // 3, yy // 3)
    color = np.dstack([shade, shade * 0.95, shade * 0.88])
    img = np.dstack([color, np.clip(alpha * 255, 0, 255)[..., None]]).astype(np.uint8)
    return Image.fromarray(img, "RGBA").filter(ImageFilter.GaussianBlur(radius=max(1, w // 160)))


def soot(seed, size_m):
    """Soot under a cornice: near-black at the top, blotchy, fading out over the band's height."""
    w, h = _size_px("soot", size_m)
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    blotch = 0.6 * _hash(seed, xx // 18, yy // 18) + 0.4 * _hash(seed + 1, xx // 5, yy // 5)
    top_fade = np.clip(1.0 - (yy / h) ** 0.7, 0.0, 1.0)
    edge = np.clip(1.0 - np.abs(xx - w / 2.0) / (w / 2.0 + 1.0), 0.0, 1.0) ** 0.15
    alpha = np.clip((0.7 + 0.35 * blotch) * top_fade * edge, 0.0, 0.92) * 255.0
    color = np.full((h, w, 3), 14.0)
    img = np.dstack([color, alpha[..., None]]).astype(np.uint8)
    return Image.fromarray(img, "RGBA").filter(ImageFilter.GaussianBlur(radius=max(1, w // 140)))


SHOPS = ("grocery", "bar", "laundry", "clothes", "empty")


def shop(seed, size_m, kind):
    """A shop's back wall and fittings seen through the window: dim, warm, varied (RGB, opaque)."""
    w, h = _size_px("shop", size_m)
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    wall = {"grocery": (150, 140, 118), "bar": (70, 42, 30), "laundry": (176, 182, 178),
            "clothes": (168, 150, 132), "empty": (96, 90, 82)}[kind]
    img = Image.new("RGB", (w, h), wall)
    d = ImageDraw.Draw(img)
    floor_y = int(h * 0.9)
    d.rectangle([0, floor_y, w, h], fill=(64, 58, 50))
    rnd = lambda *k: float(_hash(seed, np.array([k[0]]), np.array([k[1] if len(k) > 1 else 0]))[0])  # noqa: E731
    if kind == "grocery":
        for row in range(5):
            y0 = int(h * (0.14 + 0.15 * row))
            d.rectangle([int(w * 0.04), y0 + int(h * 0.12), int(w * 0.96), y0 + int(h * 0.135)], fill=(90, 84, 76))
            x = int(w * 0.05)
            while x < w * 0.95:
                bw = int(w * (0.03 + 0.04 * rnd(row, x)))
                bh = int(h * (0.06 + 0.05 * rnd(x, row)))
                c = [(186, 58, 44), (230, 198, 76), (64, 112, 168), (232, 226, 210), (82, 140, 74)][int(rnd(x, row + 9) * 5) % 5]
                d.rectangle([x, y0 + int(h * 0.12) - bh, x + bw, y0 + int(h * 0.12)], fill=c)
                x += bw + 2
    elif kind == "bar":
        d.rectangle([0, int(h * 0.12), w, int(h * 0.5)], fill=(40, 46, 52))  # back-bar mirror
        for row in range(2):
            y = int(h * (0.3 + 0.18 * row))
            d.rectangle([int(w * 0.05), y, int(w * 0.95), y + int(h * 0.015)], fill=(110, 80, 50))
            for k in range(28):
                x = int(w * (0.07 + 0.03 * k))
                c = [(120, 70, 30), (60, 110, 60), (200, 180, 120), (160, 40, 30)][int(rnd(k, row) * 4) % 4]
                d.rectangle([x, y - int(h * 0.09), x + int(w * 0.012), y], fill=c)
        d.rectangle([0, int(h * 0.6), w, int(h * 0.9)], fill=(88, 52, 30))  # the bar
        d.rectangle([0, int(h * 0.6), w, int(h * 0.63)], fill=(130, 90, 56))
    elif kind == "laundry":
        for row in range(2):
            for k in range(6):
                cx, cy = int(w * (0.1 + 0.16 * k)), int(h * (0.42 + 0.27 * row))
                r = int(w * 0.055)
                d.rectangle([cx - r - 8, cy - r - 8, cx + r + 8, cy + r + 8], fill=(226, 228, 224))
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(60, 72, 80), outline=(150, 156, 160), width=4)
    elif kind == "clothes":
        d.rectangle([int(w * 0.05), int(h * 0.3), int(w * 0.95), int(h * 0.31)], fill=(70, 70, 72))
        x = int(w * 0.06)
        while x < w * 0.93:
            gw = int(w * (0.03 + 0.03 * rnd(x, 1)))
            c = [(40, 50, 80), (150, 40, 50), (210, 200, 180), (60, 90, 70), (30, 30, 34)][int(rnd(x, 2) * 5) % 5]
            d.rectangle([x, int(h * 0.31), x + gw, int(h * (0.62 + 0.12 * rnd(x, 3)))], fill=c)
            x += gw + 3
        d.rectangle([int(w * 0.3), int(h * 0.72), int(w * 0.7), int(h * 0.9)], fill=(120, 96, 70))
    else:
        d.rectangle([int(w * 0.6), int(h * 0.25), int(w * 0.8), int(h * 0.5)], fill=(170, 150, 110))
        d.rectangle([int(w * 0.1), int(h * 0.55), int(w * 0.35), int(h * 0.9)], fill=(70, 62, 54))
    arr = np.asarray(img).astype(np.float64)
    # A ceiling light pool and dark corners: dim, not a light box.
    glow = np.clip(1.0 - (((xx - w * 0.5) / (w * 0.7)) ** 2 + ((yy - h * 0.15) / (h * 0.9)) ** 2), 0.25, 1.0)
    arr = arr * glow[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


# ------------------------------------------------------------------ ghost signs and shop signs


def ghost(seed, size_m, word):
    w, h = _size_px("ghost", size_m)
    img = _rgba(w, h)
    paint = GHOST_PAINTS[seed % len(GHOST_PAINTS)]
    draw = ImageDraw.Draw(img)
    margin = int(w * 0.03)
    draw.rectangle([margin, margin, w - margin, h - margin], fill=paint + (255,))
    border = max(2, w // 220)
    dark = tuple(max(0, c - 70) for c in paint)
    for off in range(border):
        draw.rectangle([margin + off, margin + off, w - margin - off, h - margin - off], outline=dark + (255,))
    lines = word.split(" - ") if " - " in word else [word]
    # The biggest letters that fit inside the panel, with a margin.
    size = max(16, int(h * 0.22))
    while size > 16:
        font = _font(size)
        widest = max(draw.textbbox((0, 0), line, font=font)[2] - draw.textbbox((0, 0), line, font=font)[0]
                     for line in lines)
        if widest <= (w - 2 * margin) * 0.86 and len(lines) * size * 1.3 <= (h - 2 * margin) * 0.86:
            break
        size = int(size * 0.92)
    font = _font(size)
    total_h = len(lines) * font.size * 1.3
    y = (h - total_h) / 2.0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        ink = tuple(max(0, c - 110) for c in paint)
        draw.text(((w - tw) / 2.0, y), line, font=font, fill=ink + (255,))
        y += font.size * 1.3
    arr = np.asarray(img).astype(np.float64)
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    wear = _hash(seed + 5, xx // 5, yy // 5)
    big_wear = _hash(seed + 6, xx // 40, yy // 40)
    alpha_factor = np.clip(0.42 + 0.22 * wear + 0.14 * big_wear - np.abs((yy / h) - 0.5) * 0.1, 0.25, 0.60)
    alpha = arr[..., 3] * alpha_factor
    alpha = np.where(alpha_factor > 0, np.maximum(alpha, 40.0), 0.0)
    out = np.dstack([arr[..., :3], alpha[..., None]]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def sign(seed, size_m, word):
    w, h = _size_px("sign", size_m)
    img = _rgba(w, h)
    draw = ImageDraw.Draw(img)
    ink = SIGN_INKS[seed % len(SIGN_INKS)]
    font = _font(max(16, int(h * 0.62)))
    bbox = draw.textbbox((0, 0), word, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    scale = min((w * 0.92) / max(1, tw), 1.0)
    if scale < 1.0:
        font = _font(max(12, int(font.size * scale)))
        bbox = draw.textbbox((0, 0), word, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (w - tw) / 2.0 - bbox[0]
    y = (h - th) / 2.0 - bbox[1]
    draw.text((x + 2, y + 2), word, font=font, fill=(0, 0, 0, 120))  # drop shadow
    draw.text((x, y), word, font=font, fill=ink + (255,))
    return img


# ------------------------------------------------------------------ gates and boarding


def gate_rolldown(seed, size_m):
    w, h = _size_px("gate_rolldown", size_m)
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    slat_h = max(4, h // 26)
    phase = (yy % slat_h) / float(slat_h)
    shade = 0.55 + 0.35 * np.sin(phase * np.pi)
    grime = _hash(seed, xx // 6, yy // 10) * 0.12
    rust = (_hash(seed + 1, xx // 10, yy // 14) > 0.93) * (0.15 + 0.25 * _hash(seed + 2, xx, yy))
    base = np.array([112.0, 112.0, 114.0])
    rust_rgb = np.array([110.0, 62.0, 40.0])
    factor = (shade - grime)[..., None]
    color = base * factor
    color = color * (1 - rust[..., None]) + rust_rgb * rust[..., None]
    seam = (yy % slat_h) < 1
    color = np.where(seam[..., None], color * 0.5, color)
    color = np.clip(color, 0, 255)
    alpha = np.full((h, w), 255.0)
    img = np.dstack([color, alpha[..., None]]).astype(np.uint8)
    return Image.fromarray(img, "RGBA")


def gate_accordion(seed, size_m):
    w, h = _size_px("gate_accordion", size_m)
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    period = max(8, w // 14)
    a = ((xx + yy) % period)
    b = ((xx - yy) % period)
    bar_w = max(2, period // 6)
    on = (a < bar_w) | (b < bar_w)
    color = np.full((h, w, 3), 60.0)
    noise = _hash(seed, xx // 5, yy // 5) * 20.0
    color = color + noise[..., None]
    alpha = np.where(on, 230.0, 0.0)
    img = np.dstack([np.clip(color, 0, 255), alpha[..., None]]).astype(np.uint8)
    return Image.fromarray(img, "RGBA")


def plywood(seed, size_m):
    w, h = _size_px("plywood", size_m)
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    grain = np.sin(xx / 9.0 + np.sin(yy / 40.0 + seed) * 2.0) * 6.0
    base = 150.0 + grain + (_hash(seed, xx // 3, yy // 3) - 0.5) * 14.0
    panel_w = w // 2
    seam = (xx % panel_w) < 2
    base = np.where(seam, base * 0.6, base)
    tint = np.array([1.0, 0.82, 0.58])
    color = np.stack([base * tint[0], base * tint[1], base * tint[2]], axis=-1)
    stain_cx, stain_cy = w * 0.65, h * 0.3
    dist = np.sqrt((xx - stain_cx) ** 2 + ((yy - stain_cy) * 1.4) ** 2)
    stain = np.clip(1.0 - dist / (w * 0.35), 0, 1) ** 2
    color = color * (1.0 - stain[..., None] * 0.35)
    screw_positions = [(0.1, 0.1), (0.9, 0.1), (0.1, 0.9), (0.9, 0.9), (0.5, 0.1), (0.5, 0.9),
                       (0.1, 0.5), (0.9, 0.5), (0.5, 0.5)]
    img = Image.fromarray(np.clip(color, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    draw = ImageDraw.Draw(img)
    r = max(2, w // 120)
    for fx, fy in screw_positions:
        cx, cy = fx * w, fy * h
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(70, 68, 64, 255))
        draw.ellipse([cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5], fill=(120, 118, 112, 255))
    img.putalpha(255)
    return img


def build(out_dir, seed=771):
    out_dir = str(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    record = {}
    jobs = []
    for i in range(1, 4):
        jobs.append(("streak_%02d" % i, (0.9, 1.2), lambda s, sm: streak(s, sm)))
    for i in range(1, 3):
        jobs.append(("soot_%02d" % i, (4.0, 1.2), lambda s, sm: soot(s, sm)))
    for kind in SHOPS:
        jobs.append(("shop_" + kind, (2.4, 2.4), (lambda s, sm, k=kind: shop(s, sm, k))))
    for i, word in enumerate(GHOST_WORDS, 1):
        jobs.append(("ghost_%02d" % i, (6.0, 4.0), (lambda s, sm, w=word: ghost(s, sm, w))))
    for i, word in enumerate(SIGN_WORDS, 1):
        jobs.append(("sign_%02d" % i, (4.0, 0.6), (lambda s, sm, w=word: sign(s, sm, w))))
    jobs.append(("gate_rolldown", (2.0, 2.0), lambda s, sm: gate_rolldown(s, sm)))
    jobs.append(("gate_accordion", (2.0, 2.0), lambda s, sm: gate_accordion(s, sm)))
    jobs.append(("plywood", (2.0, 2.0), lambda s, sm: plywood(s, sm)))
    for index, (name, size_m, fn) in enumerate(jobs):
        image = fn(seed + index * 11, size_m)
        path = os.path.join(out_dir, name + ".png")
        image.save(path, optimize=True)
        record[name] = {"file": name + ".png", "size_m": list(size_m)}
        print("decal", name, image.size, os.path.getsize(path), "bytes")
    with open(os.path.join(out_dir, "decals.json"), "w") as handle:
        json.dump(record, handle, indent=1, sort_keys=True)
        handle.write("\n")
    return record


def main():
    build(os.path.join(_root(), "SourceArt", "CityGen", "kit", "decals"))


if __name__ == "__main__":
    main()
