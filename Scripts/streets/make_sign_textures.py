"""Road-sign artwork for Sky City's street kit (PIL, fonts from macOS).

  T_Sign_Stop.png        red octagon STOP face (1024 square, alpha outside the octagon)
  T_Sign_Speed.png       SPEED LIMIT faces, 4 x 3 atlas of 512 x 640 cells (15..65 mph)
  T_Sign_Names.png       street-name blades, 8 x 40 atlas of 512 x 102 cells, white on green
  sign_atlas.json        speed -> cell index, street name -> cell index (for per-instance UV offsets)

Run: python3 -I Scripts/streets/make_sign_textures.py
"""
import json, math, pathlib, re
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "SourceArt/StreetKit/textures"
OUT.mkdir(parents=True, exist_ok=True)
D = json.load(open(ROOT / "Saved/Streets/street_data.json"))
FONT_DIN = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"
FONT_ARIAL = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
GREEN = (0, 104, 71)          # MUTCD guide green
RED = (176, 26, 32)
WHITE = (248, 248, 246)
BLACK = (18, 18, 18)


def font(path, size):
    return ImageFont.truetype(path, size)


def fit(draw, text, path, box_w, box_h, start):
    s = start
    while s > 8:
        f = font(path, s)
        l, t, r, b = draw.textbbox((0, 0), text, font=f)
        if r - l <= box_w and b - t <= box_h:
            return f, (l, t, r, b)
        s -= 2
    f = font(path, 8)
    return f, draw.textbbox((0, 0), text, font=f)


def centered(draw, text, f, bbox, cx, cy, fill):
    l, t, r, b = bbox
    draw.text((cx - (r - l) / 2 - l, cy - (b - t) / 2 - t), text, font=f, fill=fill)


# ---- STOP
S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)


def octagon(r, c=S / 2):
    return [(c + r * math.cos(math.radians(22.5 + 45 * k)), c + r * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)]


d.polygon(octagon(S / 2 / math.cos(math.radians(22.5)) * 0.995), fill=WHITE)
d.polygon(octagon(S / 2 / math.cos(math.radians(22.5)) * 0.93), fill=RED)
f, bb = fit(d, "STOP", FONT_ARIAL, S * 0.78, S * 0.36, 420)
centered(d, "STOP", f, bb, S / 2, S / 2, WHITE)
img.save(OUT / "T_Sign_Stop.png")

# ---- SPEED LIMIT atlas
speeds = [15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65]
CW, CH = 512, 640
atlas = Image.new("RGBA", (2048, 2048), WHITE + (255,))
d = ImageDraw.Draw(atlas)
speed_index = {}
for i, mph in enumerate(speeds):
    cx, cy = (i % 4) * CW, (i // 4) * CH
    d.rounded_rectangle([cx + 6, cy + 6, cx + CW - 7, cy + CH - 7], radius=28, fill=WHITE, outline=BLACK, width=14)
    f, bb = fit(d, "SPEED", FONT_DIN, CW * 0.8, 120, 150)
    centered(d, "SPEED", f, bb, cx + CW / 2, cy + 110, BLACK)
    f, bb = fit(d, "LIMIT", FONT_DIN, CW * 0.8, 120, 150)
    centered(d, "LIMIT", f, bb, cx + CW / 2, cy + 230, BLACK)
    f, bb = fit(d, str(mph), FONT_DIN, CW * 0.8, 300, 360)
    centered(d, str(mph), f, bb, cx + CW / 2, cy + 455, BLACK)
    speed_index[mph] = i
atlas.save(OUT / "T_Sign_Speed.png")

# ---- street-name blades
ABBR = [(r"\bNorth\b", "N"), (r"\bSouth\b", "S"), (r"\bEast\b", "E"), (r"\bWest\b", "W"), (r"\bStreet\b", "St"),
        (r"\bAvenue\b", "Ave"), (r"\bBoulevard\b", "Blvd"), (r"\bDrive\b", "Dr"), (r"\bRoad\b", "Rd"), (r"\bPlace\b", "Pl"),
        (r"\bCourt\b", "Ct"), (r"\bLane\b", "Ln"), (r"\bParkway\b", "Pkwy"), (r"\bTerrace\b", "Ter"), (r"\bExpressway\b", "Expy"),
        (r"\bHighway\b", "Hwy"), (r"\bSquare\b", "Sq"), (r"\bJean Baptiste Point DuSable\b", "DuSable")]


def short(name):
    s = name
    for a, b in ABBR:
        s = re.sub(a, b, s)
    return s


BW, BH, COLS, ROWS = 512, 102, 8, 40
names = D["names"][: COLS * ROWS]
atlas = Image.new("RGBA", (BW * COLS, 4096), GREEN + (255,))
d = ImageDraw.Draw(atlas)
name_index = {}
for i, n in enumerate(names):
    cx, cy = (i % COLS) * BW, (i // COLS) * BH
    d.rounded_rectangle([cx + 3, cy + 3, cx + BW - 4, cy + BH - 4], radius=12, fill=GREEN, outline=WHITE, width=5)
    text = short(n)
    f, bb = fit(d, text, FONT_DIN, BW - 40, BH - 26, 90)
    centered(d, text, f, bb, cx + BW / 2, cy + BH / 2 + 2, WHITE)
    name_index[n] = i
atlas.save(OUT / "T_Sign_Names.png")
json.dump({"speed": speed_index, "speed_grid": [4, 3, CW / 2048, CH / 2048], "names": name_index,
           "names_grid": [COLS, ROWS, BW / (BW * COLS), BH / 4096]}, open(OUT / "sign_atlas.json", "w"), indent=0)
print("names", len(name_index), "speeds", len(speed_index))
