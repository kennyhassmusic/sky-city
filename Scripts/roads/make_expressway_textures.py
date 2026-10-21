"""Textures for the elevated expressways (PIL, fonts from macOS), written to SourceArt/Expressway/textures/.

  T_Expwy_SignAtlas.png   2048 x 4096, 2 columns x 8 rows of 1024 x 512 cells (16 sign faces, 2:1). Green guide signs
                          with white legend and border, the Interstate shield (red top band, blue body, white numerals),
                          in DIN Alternate Bold (the nearest macOS face to the FHWA highway alphabet). No logos, no brands.
                          Cell order = SIGN_IDS below (the Blender kit maps each sign face to its cell).
  T_Expwy_Grime.png       1024 x 1024 multiplier for weathered concrete, used on the kit's second UV set (u along the
                          structure, v = 0 at an element's bottom, 1 at its top): dark grey-brown water streaks running
                          down from the top (the leaking joints and deck drains of the old decks), rust drips, a
                          dirt/splash band at the bottom, efflorescence, broad mottling. White = clean.
  T_Expwy_MSE_C.png       1024 x 1024 base colour of the precast panel retaining walls on the ramps (1.52 m square
                          panels, two by two per tile, joints and a chamfer line), built over Poly Haven's CC0
                          concrete_floor_01 so it matches the rest of the concrete.
Run: python3 -I Scripts/roads/make_expressway_textures.py       (20 Oct 2026, agent highway-capitol)
"""
import math, pathlib, random
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "SourceArt/Expressway/textures"
OUT.mkdir(parents=True, exist_ok=True)
FONT = "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf"
GREEN = (0, 102, 64)          # FHWA guide-sign green (approx. sRGB)
WHITE = (240, 240, 236)
RED = (178, 34, 52)
BLUE = (0, 59, 135)

# id -> (top caption, shield number or None, shield kind, lines of text, small bottom line)
SIGNS = {
    "I35N_DALLAS": ("NORTH", "35", "I", ["Waco", "Dallas"], None),
    "UPPER_THRU": (None, None, None, ["Upper Level", "Thru Traffic"], "NO EXITS NEXT 2 MILES"),
    "I35N_GEORGETOWN": ("NORTH", "35", "I", ["Round Rock", "Georgetown"], None),
    "MILEAGE_N": (None, None, None, ["Round Rock   18", "Georgetown   27", "Waco   102"], None),
    "I35S_SANANTONIO": ("SOUTH", "35", "I", ["San Marcos", "San Antonio"], None),
    "TO290E_CHICAGO": ("TO  EAST", "290", "I", ["Chicago Loop"], None),
    "CAPITOL_CONGRESS": (None, None, None, ["State Capitol", "Congress Av"], "NEXT EXIT BELOW"),
    "MILEAGE_S": (None, None, None, ["San Marcos   30", "New Braunfels   47", "San Antonio   79"], None),
    # Wacker Canal Expressway (Chicago side style, same green guide signs)
    "WCX_N_CROSSTOWN": ("NORTH", None, None, ["Crosstown Pkwy", "Lady Bird Lake"], None),
    "WCX_N_6TH": (None, None, None, ["W 6th St", "Seam Circle"], "1/2 MILE"),
    "WCX_N_LAKE": (None, None, None, ["Lady Bird Lake", "South Congress"], None),
    "WCX_N_PKWY": (None, None, None, ["Crosstown Pkwy", "West"], "MERGE AHEAD"),
    "WCX_S_LOOP": ("SOUTH", None, None, ["Chicago Loop", "Lower Wacker Dr"], None),
    "WCX_S_290": ("WEST", "290", "I", ["Eisenhower", "Expwy"], None),
    "WCX_S_WILLIS": (None, None, None, ["Van Buren St", "Willis Tower"], None),
    "WCX_S_ADAMS": (None, None, None, ["Adams St", "Union Station"], "END EXPWY 1/4 MILE"),
}
SIGN_IDS = list(SIGNS)


def font(size):
    return ImageFont.truetype(FONT, size)


def shield(d, cx, cy, h, num):
    """Interstate shield (approximate MUTCD M1-1 outline): white border, red crown band, blue body."""
    w = h * 1.0
    def outline(scale):
        pts = []
        for k in range(41):            # top edge: a shallow double curve with the two crown points
            x = -0.5 + k / 40
            y = -0.5 + 0.06 * abs(math.sin(math.pi * (x + 0.5))) - 0.05 * math.cos(2 * math.pi * x) ** 8
            pts.append((x, y))
        for k in range(1, 40):         # sides curving into the bottom point
            a = k / 40
            pts.append((0.5 - 0.02 * math.sin(a * math.pi) - 0.5 * a ** 2.2, -0.45 + 0.95 * a))
        pts.append((0.0, 0.5))
        for k in range(39, 0, -1):
            a = k / 40
            pts.append((-(0.5 - 0.02 * math.sin(a * math.pi) - 0.5 * a ** 2.2), -0.45 + 0.95 * a))
        return [(cx + x * w * scale, cy + y * h * scale) for x, y in pts]
    d.polygon(outline(1.0), fill=WHITE)
    d.polygon(outline(0.9), fill=BLUE)
    band = [p for p in outline(0.9)]
    top = min(p[1] for p in band)
    d.polygon([(x, min(y, top + h * 0.22)) for x, y in band if y <= top + h * 0.22] or band[:2], fill=RED)
    d.rectangle([cx - w * 0.44, top + h * 0.2, cx + w * 0.44, top + h * 0.235], fill=WHITE)
    d.text((cx, top + h * 0.11), "INTERSTATE", font=font(int(h * 0.09)), fill=WHITE, anchor="mm")
    f = font(int(h * (0.5 if len(num) <= 2 else 0.36)))
    d.text((cx, cy + h * 0.1), num, font=f, fill=WHITE, anchor="mm")


def sign_cell(sid):
    cap, num, kind, lines, small = SIGNS[sid]
    W, H = 1024, 512
    im = Image.new("RGB", (W, H), GREEN)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([10, 10, W - 11, H - 11], radius=34, outline=WHITE, width=12)
    x_text = 70
    if cap and not num:
        d.text((W / 2, 70), cap, font=font(58), fill=WHITE, anchor="mm")
    if num:
        sh = 250
        if cap:
            d.text((185, 92), cap, font=font(66), fill=WHITE, anchor="mm")
        shield(d, 185, 290, sh, num)
        x_text = 360
    n = len(lines)
    if n == 1:
        sizes = [120]
    elif n == 2:
        sizes = [104, 104]
    else:
        sizes = [86, 86, 86]
    total = sum(sizes) * 1.12
    y = (H - total) / 2 + (0 if not small else -36)
    for line, sz in zip(lines, sizes):
        f = font(sz)
        if "   " in line:                     # mileage sign: name left, number right
            name, dist = line.split("   ")
            d.text((x_text, y), name.strip(), font=f, fill=WHITE, anchor="la")
            d.text((W - 80, y), dist.strip(), font=f, fill=WHITE, anchor="ra")
        else:
            # fit the line into the space right of the shield
            while d.textlength(line, font=f) > W - x_text - 60 and sz > 40:
                sz -= 4
                f = font(sz)
            d.text((x_text if num else W / 2, y), line, font=f, fill=WHITE, anchor="la" if num else "ma")
        y += sz * 1.12
    if small:
        d.text((W / 2, H - 70), small, font=font(46), fill=WHITE, anchor="mm")
    return im


def atlas():
    A = Image.new("RGB", (2048, 4096), (40, 40, 40))
    for k, sid in enumerate(SIGN_IDS):
        c, r = k % 2, k // 2
        A.paste(sign_cell(sid), (c * 1024, r * 512))
    A.save(OUT / "T_Expwy_SignAtlas.png")


def grime(seed=7):
    rnd = random.Random(seed)
    N = 1024
    from PIL import ImageChops
    im = Image.new("L", (N, N), 255)
    d = ImageDraw.Draw(im)
    # water streaks from the top (v=1 is the top: image row 0)
    for _ in range(260):
        x = rnd.uniform(0, N)
        L = rnd.uniform(0.08, 0.9) ** 1.4 * N
        w = rnd.uniform(2, 14)
        a = rnd.randint(25, 85)
        for k in range(int(L / 4)):
            y = k * 4
            fade = 1.0 - y / L
            xx = x + math.sin(y * 0.01 + x) * 2
            d.line([(xx, y), (xx, y + 5)], fill=255 - int(a * fade), width=max(1, int(w * (0.6 + 0.4 * fade))))
    # rust drips (narrow, warm in the colour pass)
    rust = Image.new("L", (N, N), 0)
    dr = ImageDraw.Draw(rust)
    for _ in range(40):
        x = rnd.uniform(0, N)
        L = rnd.uniform(0.05, 0.35) * N
        dr.line([(x, 0), (x + rnd.uniform(-3, 3), L)], fill=rnd.randint(60, 140), width=rnd.randint(2, 6))
    rust = rust.filter(ImageFilter.GaussianBlur(2))
    # bottom splash / dirt band (v < ~0.1)
    for y in range(N - 140, N):
        f = (y - (N - 140)) / 140
        d.line([(0, y), (N, y)], fill=int(255 - 70 * f ** 1.5), width=1)
    im = im.filter(ImageFilter.GaussianBlur(1.2))
    # broad mottling, multiplied in (never lightens)
    mott = Image.effect_noise((48, 48), 50).resize((N, N), Image.BICUBIC).filter(ImageFilter.GaussianBlur(24))
    im = ImageChops.multiply(im, mott.point(lambda v: int(min(255, 215 + v * 0.3))))
    # efflorescence: a few pale streaks
    eff = Image.new("L", (N, N), 0)
    de = ImageDraw.Draw(eff)
    for _ in range(30):
        x = rnd.uniform(0, N)
        de.line([(x, rnd.uniform(0, 80)), (x, rnd.uniform(100, 380))], fill=rnd.randint(30, 70), width=rnd.randint(3, 9))
    eff = eff.filter(ImageFilter.GaussianBlur(3))
    # combine: dark grey-brown streaks, rust tint, pale efflorescence
    base = im.convert("RGB")
    px = base.load(); rp = rust.load(); ep = eff.load()
    for y in range(N):
        for x in range(N):
            v = px[x, y][0]
            r_, g_, b_ = v, v * 0.97, v * 0.92            # streaks lean grey-brown
            ru = rp[x, y] / 255.0
            r_, g_, b_ = r_ * (1 - 0.15 * ru), g_ * (1 - 0.35 * ru), b_ * (1 - 0.55 * ru)
            e = ep[x, y] / 255.0
            r_, g_, b_ = r_ + (255 - r_) * e * 0.5, g_ + (255 - g_) * e * 0.5, b_ + (255 - b_) * e * 0.5
            px[x, y] = (int(min(255, r_)), int(min(255, g_)), int(min(255, b_)))
    # make it tile horizontally: blend the left and right 64 px
    left = base.crop((0, 0, 64, N)); right = base.crop((N - 64, 0, N, N))
    mask = Image.linear_gradient("L").rotate(90).resize((64, N))
    base.paste(Image.composite(left, right, mask), (N - 64, 0))
    base.save(OUT / "T_Expwy_Grime.png")


def mse():
    src = ROOT / "SourceArt/CC0/polyhaven/concrete_floor_01/concrete_floor_01_diff_2k.jpg"
    N = 1024
    im = Image.open(src).convert("RGB").resize((N, N), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    p = N // 2                                     # 2 x 2 panels per tile (tile = 3.05 m)
    for k in range(3):
        y = k * p
        d.line([(0, y), (N, y)], fill=(70, 66, 60), width=7)
    for row in range(2):
        off = 0 if row == 0 else p // 2            # staggered vertical joints
        for k in range(-1, 3):
            x = k * p + off
            d.line([(x, row * p), (x, row * p + p)], fill=(70, 66, 60), width=7)
    # a chamfer highlight under each horizontal joint
    for k in range(2):
        y = k * p + 6
        d.line([(0, y), (N, y)], fill=(150, 146, 138), width=3)
    im = im.filter(ImageFilter.GaussianBlur(0.6))
    im.save(OUT / "T_Expwy_MSE_C.png")


def atlas_index():
    """Where each sign face sits in the atlas, for the Blender kit (which can't import PIL)."""
    import json
    cells = {sid: {"col": k % 2, "row": k // 2} for k, sid in enumerate(SIGN_IDS)}
    json.dump({"image": "T_Expwy_SignAtlas.png", "cols": 2, "rows": 8, "cell_px": [1024, 512], "cells": cells},
              open(OUT / "sign_atlas.json", "w"), indent=1)


if __name__ == "__main__":
    atlas_index()
    atlas()
    grime()
    mse()
    print("textures written to", OUT, SIGN_IDS)
