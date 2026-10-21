"""Sky City road kit textures (PIL + numpy, macOS fonts). Pairs with Scripts/roads/blender_signal_kit.py.

  T_RoadGlyphs.png       2048 x 1024 RGBA, 4 x 2 cells of 512: white paint, alpha = coverage. Lane-use arrows
                         (S, L, R, LS, SR, LR), ONLY, bicycle. The TOP of each cell is the direction of travel.
                         Arrows are drawn in true metres for a 1.2 x 3.0 m decal, so the decal's scale undoes the
                         squeeze; ONLY and the bike are stretched to fill their cells (see decal_m in textures.json).
  T_SignAtlas2.png       2048 x 2048 RGBA, 4 x 4 cells of 512, each a whole sign face, pre-distorted so that it looks
                         right on its real panel size (panel_m in textures.json). Outside rounded corners / octagon /
                         diamond the alpha is 0 (RGB there = the sign's edge colour, so mips don't fringe).
  T_BarricadeStripe.png  512 x 128 orange / white 45-degree stripes, tiles horizontally (one tile = 0.8 x 0.2 m of rail).
  textures.json          cell index -> name, grid, UV offsets (top-down glTF/Unreal convention), panel / decal sizes.

Signs are drawn at 2x in their real proportions (MUTCD inch layouts), then resampled into the square cell.
Run: python3 -I Scripts/roads/make_road_textures.py
"""
import json, math, pathlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "SourceArt/RoadKit/textures"
OUT.mkdir(parents=True, exist_ok=True)
FONT_DINC = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"    # ~ Highway Gothic Series C
FONT_DINA = "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf"    # ~ Series D/E
CELL = 512
RED = (176, 26, 32)
WHITE = (248, 248, 246)
BLACK = (18, 18, 18)
YELLOW = (252, 200, 0)


# ------------------------------------------------------------------ 2D geometry helpers (convex polygons)
def inset(poly, d):
    """Move every edge of a convex polygon inward by d and re-intersect."""
    P = [np.asarray(p, float) for p in poly]
    n = len(P)
    c = sum(P) / n
    lines = []
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        e = (b - a) / np.linalg.norm(b - a)
        nr = np.array([-e[1], e[0]])
        if np.dot(nr, c - a) < 0:
            nr = -nr
        lines.append((a + nr * d, e))
    out = []
    for i in range(n):
        (p1, e1), (p2, e2) = lines[i - 1], lines[i]
        t, _ = np.linalg.solve(np.array([e1, -e2]).T, p2 - p1)
        out.append(tuple(p1 + t * e1))
    return out


def rounded(poly, r, steps=14):
    """Replace each corner of a convex polygon with a tangent arc of radius r."""
    if r <= 0.5:
        return [tuple(p) for p in poly]
    P = [np.asarray(p, float) for p in poly]
    n = len(P)
    out = []
    for i in range(n):
        p0, p1, p2 = P[i - 1], P[i], P[(i + 1) % n]
        a = (p0 - p1) / np.linalg.norm(p0 - p1)
        b = (p2 - p1) / np.linalg.norm(p2 - p1)
        ang = math.acos(max(-1.0, min(1.0, float(np.dot(a, b)))))
        t = r / math.tan(ang / 2)
        bis = (a + b) / np.linalg.norm(a + b)
        c = p1 + bis * (r / math.sin(ang / 2))
        t1, t2 = p1 + a * t, p1 + b * t
        a1 = math.atan2(*(t1 - c)[::-1])
        a2 = math.atan2(*(t2 - c)[::-1])
        da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
        for k in range(steps + 1):
            out.append((c[0] + r * math.cos(a1 + da * k / steps), c[1] + r * math.sin(a1 + da * k / steps)))
    return out


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def stroke(center, width):
    """Polygon of a thick open polyline (flat ends, mitred joints from averaged normals)."""
    C = [np.asarray(p, float) for p in center]
    L, R = [], []
    for i, p in enumerate(C):
        a = C[max(0, i - 1)]
        b = C[min(len(C) - 1, i + 1)]
        t = (b - a) / np.linalg.norm(b - a)
        nr = np.array([-t[1], t[0]])
        # miter correction at joints
        if 0 < i < len(C) - 1:
            t0 = (p - a) / np.linalg.norm(p - a)
            n0 = np.array([-t0[1], t0[0]])
            k = max(0.3, float(np.dot(nr, n0)))
            nr = nr / k
        L.append(tuple(p + nr * width / 2))
        R.append(tuple(p - nr * width / 2))
    return L + R[::-1]


def arc(c, r, a0, a1, n=20):
    return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)), c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * k / n)))
            for k in range(n + 1)]


def head(base_c, direction, length, width):
    """Triangle arrowhead: base centred on base_c, pointing along direction."""
    d = np.asarray(direction, float)
    d /= np.linalg.norm(d)
    p = np.array([-d[1], d[0]])
    b = np.asarray(base_c, float)
    return [tuple(b + d * length), tuple(b + p * width / 2), tuple(b - p * width / 2)]


def dedupe(pts):
    out = []
    for p in pts:
        if not out or math.dist(out[-1], p) > 1e-9:
            out.append(p)
    return out


def text(d, s, path, cx, cy, cap, max_w=None, fill=BLACK):
    """Draw s centred on (cx, cy) with ink height = cap (capital letters), shrunk to max_w if needed."""
    f = ImageFont.truetype(path, 400)
    l, t, r, b = d.textbbox((0, 0), s, font=f)
    size = 400 * cap / (b - t)
    if max_w and (r - l) * size / 400 > max_w:
        size = 400 * max_w / (r - l)
    f = ImageFont.truetype(path, max(8, int(round(size))))
    l, t, r, b = d.textbbox((0, 0), s, font=f)
    d.text((cx - (l + r) / 2, cy - (t + b) / 2), s, font=f, fill=fill)


def thick_path(d, pts, w, fill):
    d.line(pts, fill=fill, width=int(round(w)), joint="curve")
    for p in (pts[0], pts[-1]):
        d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=fill)


# ------------------------------------------------------------------ sign faces (drawn in inches, u = px per inch)
def framed(d, poly, r, u, face, border, inset_in, width_in):
    """Sign blank: face colour, border band from inset_in to inset_in + width_in."""
    d.polygon(rounded(poly, r), fill=face)
    if border is not None:
        d.polygon(rounded(inset(poly, inset_in * u), max(0, r - inset_in * u)), fill=border)
        d.polygon(rounded(inset(poly, (inset_in + width_in) * u), max(0, r - (inset_in + width_in) * u)), fill=face)


def s_one_way(img, d, W, H, u):                     # R6-1, 36 x 12 in
    R = rect(0, 0, W, H)
    framed(d, R, 1.5 * u, u, BLACK, WHITE, 0.375, 0.625)
    d.polygon([(3.0 * u, 3.4 * u), (25.0 * u, 3.4 * u), (25.0 * u, 8.6 * u), (3.0 * u, 8.6 * u)], fill=WHITE)
    d.polygon([(24.9 * u, 1.5 * u), (33.6 * u, 6.0 * u), (24.9 * u, 10.5 * u)], fill=WHITE)
    text(d, "ONE WAY", FONT_DINA, 14.0 * u, 6.0 * u, 3.9 * u, 20.5 * u, BLACK)


def s_do_not_enter(img, d, W, H, u):                # R5-1, 30 x 30 in
    framed(d, rect(0, 0, W, H), 1.875 * u, u, WHITE, None, 0, 0)
    c, r = 15 * u, 13.9 * u
    d.ellipse([c - r, c - r, c + r, c + r], fill=RED)
    d.rectangle([4.2 * u, 12.6 * u, 25.8 * u, 17.4 * u], fill=WHITE)
    text(d, "DO NOT", FONT_DINA, c, 8.2 * u, 4.0 * u, 18.5 * u, WHITE)
    text(d, "ENTER", FONT_DINA, c, 21.8 * u, 4.0 * u, 18.5 * u, WHITE)


def octagon(c, flat_r):
    R = flat_r / math.cos(math.radians(22.5))
    return [(c + R * math.cos(math.radians(22.5 + 45 * k)), c + R * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)]


def s_stop(img, d, W, H, u):                        # R1-1, 30 in octagon
    framed(d, octagon(15 * u, 15 * u), 1.6 * u, u, WHITE, None, 0, 0)
    d.polygon(rounded(inset(octagon(15 * u, 15 * u), 0.9 * u), 0.9 * u), fill=RED)
    text(d, "STOP", FONT_DINC, 15 * u, 15 * u, 10.0 * u, 23.0 * u, WHITE)


def s_all_way(img, d, W, H, u):                     # R1-3P, 18 x 6 in
    framed(d, rect(0, 0, W, H), 0.75 * u, u, RED, WHITE, 0.25, 0.5)
    text(d, "ALL WAY", FONT_DINC, 9.0 * u, 3.0 * u, 3.0 * u, 14.6 * u, WHITE)


def diamond(W, H):
    return [(W / 2, 0), (W, H / 2), (W / 2, H), (0, H / 2)]


def s_dead_end(img, d, W, H, u):                    # W14-1, 30 in diamond
    framed(d, diamond(W, H), 1.875 * u, u, YELLOW, BLACK, 0.6, 0.9)
    text(d, "DEAD", FONT_DINA, 15 * u, 11.7 * u, 5.0 * u, 15.5 * u, BLACK)
    text(d, "END", FONT_DINA, 15 * u, 18.3 * u, 5.0 * u, 15.5 * u, BLACK)


def s_road_closed(img, d, W, H, u):                 # R11-2 laid out 48 x 24 in (Kenny's 1.2 x 0.6 m panel)
    framed(d, rect(0, 0, W, H), 2.0 * u, u, WHITE, BLACK, 0.6, 1.2)
    text(d, "ROAD", FONT_DINA, 24 * u, 7.9 * u, 6.2 * u, 40 * u, BLACK)
    text(d, "CLOSED", FONT_DINA, 24 * u, 16.1 * u, 6.2 * u, 40 * u, BLACK)


def speed(mph):
    def f(img, d, W, H, u):                         # R2-1, 24 x 30 in
        framed(d, rect(0, 0, W, H), 1.5 * u, u, WHITE, BLACK, 0.5, 0.75)
        text(d, "SPEED", FONT_DINA, 12 * u, 5.6 * u, 3.6 * u, 17.5 * u, BLACK)
        text(d, "LIMIT", FONT_DINA, 12 * u, 10.8 * u, 3.6 * u, 17.5 * u, BLACK)
        text(d, str(mph), FONT_DINA, 12 * u, 20.6 * u, 10.5 * u, 18.5 * u, BLACK)
    return f


def turn_arrow_mask(W, H, u):
    """Black turn-left arrow (shaft up, curving left) for R3-2, centred in a 30 in square; returns an L mask."""
    m = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(m)
    sw = 4.4
    xs, y0, y1, R = 18.6, 25.0, 15.2, 4.6
    path = dedupe([(xs, y0), (xs, y1)] + arc((xs - R, y1), R, 0, -90, 18))     # y down: -90 deg = up
    end = path[-1]
    path.append((end[0] - 0.4, end[1]))
    hd = head((end[0] - 0.4, end[1]), (-1, 0), 6.4, 11.4)
    pts = [p for p in stroke(path, sw)] + hd
    xs_all = [p[0] for p in pts]
    ys_all = [p[1] for p in pts]
    dx = 15.0 - (min(xs_all) + max(xs_all)) / 2
    dy = 15.3 - (min(ys_all) + max(ys_all)) / 2
    sc = lambda poly: [((x + dx) * u, (y + dy) * u) for x, y in poly]
    md.polygon(sc(stroke(path, sw)), fill=255)
    md.polygon(sc(hd), fill=255)
    return m


def no_turn(right):
    def f(img, d, W, H, u):                         # R3-2 / R3-1, 30 x 30 in
        framed(d, rect(0, 0, W, H), 1.875 * u, u, WHITE, BLACK, 0.5, 0.75)
        m = turn_arrow_mask(W, H, u)
        if right:
            m = m.transpose(Image.FLIP_LEFT_RIGHT)
        img.paste(Image.new("RGBA", (W, H), BLACK + (255,)), (0, 0), m)
        d2 = ImageDraw.Draw(img)
        c, ro, rw = 15 * u, 12.6 * u, 2.5 * u
        ring = Image.new("L", (W, H), 0)
        rd = ImageDraw.Draw(ring)
        rd.ellipse([c - ro, c - ro, c + ro, c + ro], fill=255)
        rd.ellipse([c - ro + rw, c - ro + rw, c + ro - rw, c + ro - rw], fill=0)
        # slash from upper-left to lower-right (always this way, also on R3-1)
        e = np.array([1, 1]) / math.sqrt(2)
        p = np.array([-e[1], e[0]])
        L = ro - rw / 2
        cc = np.array([c, c])
        rd.polygon([tuple(cc - e * L + p * rw / 2), tuple(cc + e * L + p * rw / 2), tuple(cc + e * L - p * rw / 2), tuple(cc - e * L - p * rw / 2)], fill=255)
        img.paste(Image.new("RGBA", (W, H), RED + (255,)), (0, 0), ring)
    return f


def s_keep_right(img, d, W, H, u):                  # R4-7, 24 x 30 in
    framed(d, rect(0, 0, W, H), 1.5 * u, u, WHITE, BLACK, 0.5, 0.75)
    # island: a solid capsule, left of centre
    x0, x1, y0, y1 = 6.6, 10.6, 8.6, 21.0
    d.rounded_rectangle([x0 * u, y0 * u, x1 * u, y1 * u], radius=2.0 * u, fill=BLACK)
    # arrow: from below the island, angling right, then straight up past its right side
    path = [(8.6, 27.0), (8.6, 24.6), (15.6, 17.6), (15.6, 10.0)]
    d.polygon([(x * u, y * u) for x, y in stroke(path, 3.2)], fill=BLACK)
    d.polygon([(x * u, y * u) for x, y in head((15.6, 10.2), (0, -1), 6.2, 8.4)], fill=BLACK)


def s_ped_xing(img, d, W, H, u):                    # W11-2, 30 in diamond
    framed(d, diamond(W, H), 1.875 * u, u, YELLOW, BLACK, 0.6, 0.9)
    k = lambda pts: [(x * u, y * u) for x, y in pts]
    hx, hy, hr = 15.7, 8.4, 1.75
    d.ellipse([(hx - hr) * u, (hy - hr) * u, (hx + hr) * u, (hy + hr) * u], fill=BLACK)
    thick_path(d, k([(15.2, 11.4), (14.3, 16.2)]), 2.9 * u, BLACK)                    # torso
    thick_path(d, k([(15.0, 11.9), (12.9, 14.3), (11.5, 16.6)]), 1.35 * u, BLACK)      # front arm
    thick_path(d, k([(15.3, 12.0), (16.9, 14.4), (18.6, 15.9)]), 1.35 * u, BLACK)      # back arm
    thick_path(d, k([(14.4, 16.0), (12.6, 19.4), (10.9, 22.6), (9.6, 22.7)]), 1.8 * u, BLACK)   # front leg + foot
    thick_path(d, k([(14.4, 16.0), (15.9, 19.6), (17.9, 22.4), (19.1, 22.4)]), 1.8 * u, BLACK)  # back leg + foot


SIGNS = [
    # name,            MUTCD,   panel_m,      inches,     draw,              edge colour, shape
    ("ONE_WAY",        "R6-1",  (0.9, 0.3),   (36, 12),   s_one_way,         BLACK,  "rect"),
    ("DO_NOT_ENTER",   "R5-1",  (0.75, 0.75), (30, 30),   s_do_not_enter,    WHITE,  "rect"),
    ("STOP",           "R1-1",  (0.75, 0.75), (30, 30),   s_stop,            WHITE,  "octagon"),
    ("ALL_WAY",        "R1-3P", (0.45, 0.15), (18, 6),    s_all_way,         RED,    "rect"),
    ("DEAD_END",       "W14-1", (0.75, 0.75), (30, 30),   s_dead_end,        YELLOW, "diamond"),
    ("ROAD_CLOSED",    "R11-2", (1.2, 0.6),   (48, 24),   s_road_closed,     WHITE,  "rect"),
    ("SPEED_LIMIT_25", "R2-1",  (0.6, 0.75),  (24, 30),   speed(25),         WHITE,  "rect"),
    ("SPEED_LIMIT_30", "R2-1",  (0.6, 0.75),  (24, 30),   speed(30),         WHITE,  "rect"),
    ("SPEED_LIMIT_35", "R2-1",  (0.6, 0.75),  (24, 30),   speed(35),         WHITE,  "rect"),
    ("SPEED_LIMIT_40", "R2-1",  (0.6, 0.75),  (24, 30),   speed(40),         WHITE,  "rect"),
    ("SPEED_LIMIT_45", "R2-1",  (0.6, 0.75),  (24, 30),   speed(45),         WHITE,  "rect"),
    ("SPEED_LIMIT_55", "R2-1",  (0.6, 0.75),  (24, 30),   speed(55),         WHITE,  "rect"),
    ("NO_LEFT_TURN",   "R3-2",  (0.75, 0.75), (30, 30),   no_turn(False),    WHITE,  "rect"),
    ("NO_RIGHT_TURN",  "R3-1",  (0.75, 0.75), (30, 30),   no_turn(True),     WHITE,  "rect"),
    ("KEEP_RIGHT",     "R4-7",  (0.6, 0.75),  (24, 30),   s_keep_right,      WHITE,  "rect"),
    ("PED_XING",       "W11-2", (0.75, 0.75), (30, 30),   s_ped_xing,        YELLOW, "diamond"),
]


def sign_cell(draw, inches, edge):
    wi, hi = inches
    # 2x design canvas in the sign's real proportions (square pixels), long side >= 1024
    if wi >= hi:
        W, H = round(2 * CELL * wi / hi), 2 * CELL
    else:
        W, H = 2 * CELL, round(2 * CELL * hi / wi)
    u = W / wi
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw(img, ImageDraw.Draw(img), W, H, u)
    cell = img.resize((CELL, CELL), Image.LANCZOS)          # premultiplied resample; squeezes to the square cell
    a = np.array(cell)
    a[a[..., 3] == 0, :3] = edge
    return Image.fromarray(a, "RGBA")


def build_signs():
    atlas = Image.new("RGBA", (4 * CELL, 4 * CELL), (0, 0, 0, 0))
    cells = []
    for i, (name, mutcd, panel, inches, draw, edge, shape) in enumerate(SIGNS):
        col, row = i % 4, i // 4
        atlas.paste(sign_cell(draw, inches, edge), (col * CELL, row * CELL))
        cells.append({"index": i, "name": name, "mutcd": mutcd, "col": col, "row": row,
                      "uv_offset": [col / 4, row / 4], "uv_scale": [0.25, 0.25],
                      "panel_m": list(panel), "panel_scale_from_RK_SignPanel": [round(panel[0] / 0.9, 4), round(panel[1] / 0.9, 4)],
                      "shape": shape, "alpha_outside_shape": True})
    atlas.save(OUT / "T_SignAtlas2.png")
    return cells


# ------------------------------------------------------------------ road glyphs (white paint, alpha = coverage)
GSS = 4                    # supersampling for glyph masks
PAD = 6                    # final-pixel padding inside each cell
SW = 0.15                  # arrow shaft width (m), MUTCD 6 in


def glyph_canvas():
    return Image.new("L", (CELL * GSS, CELL * GSS), 0)


def metre_xf(W, L):
    """Decal metres (x right as the driver sees it, y forward, 0..L) -> supersampled cell pixels."""
    n = CELL * GSS
    p = PAD * GSS
    return lambda pts: [(p + (x / W + 0.5) * (n - 2 * p), p + (1 - y / L) * (n - 2 * p)) for x, y in pts]


def arrow_polys(kind):
    """Lane-use arrow polygons in decal metres for a 1.2 x 3.0 m decal; kind in S, L, R, LS, SR, LR."""
    polys = []
    mirror = kind in ("R", "SR")
    k = {"R": "L", "SR": "LS"}.get(kind, kind)
    if k == "S":
        polys += [stroke([(0, 0.05), (0, 2.06)], SW), head((0, 2.05), (0, 1), 0.9, 0.56)]
    elif k == "L":
        xs, y1, R = 0.38, 2.25, 0.35
        path = dedupe([(xs, 0.05), (xs, y1)] + arc((xs - R, y1), R, 0, 90, 20))
        end = path[-1]
        polys += [stroke(path + [(end[0] - 0.01, end[1])], SW), head(end, (-1, 0), 0.55, 0.56)]
    elif k == "LS":
        xs = 0.2
        polys += [stroke([(xs, 0.05), (xs, 2.06)], SW), head((xs, 2.05), (0, 1), 0.88, 0.52)]
        y1, R = 0.95, 0.38
        path = dedupe([(xs, 0.80), (xs, y1)] + arc((xs - R, y1), R, 0, 90, 20))
        end = path[-1]
        polys += [stroke(path + [(end[0] - 0.01, end[1])], SW), head(end, (-1, 0), 0.40, 0.50)]
    elif k == "LR":
        y1, R = 2.25, 0.2
        polys.append(stroke([(0, 0.05), (0, y1 + 0.01)], SW))
        for s in (-1, 1):
            path = dedupe([(0, y1 - 0.05), (0, y1)] + [(s * -x, y) for x, y in arc((-R, y1), R, 0, 90, 16)])
            end = path[-1]
            polys += [stroke(path + [(end[0] + s * 0.01, end[1])], SW), head(end, (s, 0), 0.40, 0.50)]
    if mirror:
        polys = [[(-x, y) for x, y in p] for p in polys]
    return polys


def glyph_arrow(kind):
    m = glyph_canvas()
    d = ImageDraw.Draw(m)
    xf = metre_xf(1.2, 3.0)
    for p in arrow_polys(kind):
        d.polygon(xf(p), fill=255)
    return m


def fill_cell(src):
    """Crop a mask to its ink and stretch it to fill the cell (inside the padding)."""
    bb = src.getbbox()
    src = src.crop(bb)
    n, p = CELL * GSS, PAD * GSS
    m = glyph_canvas()
    m.paste(src.resize((n - 2 * p, n - 2 * p), Image.LANCZOS), (p, p))
    return m


def glyph_only():
    f = ImageFont.truetype(FONT_DINC, 900)
    big = Image.new("L", (3000, 1200), 0)
    ImageDraw.Draw(big).text((100, 50), "ONLY", font=f, fill=255)
    return fill_cell(big)


def glyph_bike():
    """Side-view bicycle (MUTCD 9C-3A style, no rider), upright for an approaching rider, front wheel on the right."""
    S = 2000                                 # unit -> px
    big = Image.new("L", (S, int(S * 0.66)), 0)
    d = ImageDraw.Draw(big)
    k = lambda pts: [(x * S, (0.66 - y) * S) for x, y in pts]
    w = 0.042 * S
    for cx in (0.2, 0.8):                    # wheels
        r = 0.18 * S
        X, Y = k([(cx, 0.21)])[0]
        d.ellipse([X - r - w / 2, Y - r - w / 2, X + r + w / 2, Y + r + w / 2], fill=255)
        d.ellipse([X - r + w / 2, Y - r + w / 2, X + r - w / 2, Y + r - w / 2], fill=0)
    rh, bb, st, ht, hb, fh = (0.2, 0.21), (0.46, 0.2), (0.4, 0.45), (0.71, 0.46), (0.73, 0.39), (0.8, 0.21)
    for seg in ([rh, bb], [rh, st], [bb, st], [st, ht], [bb, hb], [ht, hb, fh]):
        thick_path(d, k(seg), w * 0.9, 255)
    thick_path(d, k([ht, (0.70, 0.53), (0.63, 0.555)]), w * 0.85, 255)       # stem + handlebar
    thick_path(d, k([st, (0.39, 0.50)]), w * 0.85, 255)                      # seat post
    thick_path(d, k([(0.32, 0.525), (0.45, 0.525)]), w * 1.2, 255)           # saddle
    X, Y = k([bb])[0]
    r = 0.045 * S
    d.ellipse([X - r, Y - r, X + r, Y + r], fill=255)                        # chainring
    return fill_cell(big)


GLYPHS = [
    ("S",    "lane-use arrow, straight",       (1.2, 3.0), lambda: glyph_arrow("S")),
    ("L",    "lane-use arrow, left turn",      (1.2, 3.0), lambda: glyph_arrow("L")),
    ("R",    "lane-use arrow, right turn",     (1.2, 3.0), lambda: glyph_arrow("R")),
    ("LS",   "lane-use arrow, left + straight", (1.2, 3.0), lambda: glyph_arrow("LS")),
    ("SR",   "lane-use arrow, straight + right", (1.2, 3.0), lambda: glyph_arrow("SR")),
    ("LR",   "lane-use arrow, left + right",   (1.2, 3.0), lambda: glyph_arrow("LR")),
    ("ONLY", "word ONLY, elongated letters",   (1.5, 2.4), glyph_only),
    ("BIKE", "bicycle symbol (bike lane)",     (1.0, 1.8), glyph_bike),
]


def build_glyphs():
    alpha = Image.new("L", (4 * CELL, 2 * CELL), 0)
    cells = []
    for i, (name, desc, decal, fn) in enumerate(GLYPHS):
        col, row = i % 4, i // 4
        alpha.paste(fn().resize((CELL, CELL), Image.BOX), (col * CELL, row * CELL))
        cells.append({"index": i, "name": name, "desc": desc, "col": col, "row": row,
                      "uv_offset": [col / 4, row / 2], "uv_scale": [0.25, 0.5], "decal_m": list(decal)})
    img = Image.merge("RGBA", (Image.new("L", alpha.size, 255),) * 3 + (alpha,))
    img.save(OUT / "T_RoadGlyphs.png")
    return cells


# ------------------------------------------------------------------ barricade stripes
def build_stripe():
    W, H, ss, period = 512, 128, 4, 256        # 45-degree bands 128 px wide (horizontally) -> 0.2 m on a 0.8 m tile
    ys, xs = np.mgrid[0:H * ss, 0:W * ss] / ss
    orange = (((xs + ys) % period) < period / 2).astype(float)
    cov = orange.reshape(H, ss, W, ss).mean(axis=(1, 3))[..., None]
    o, w = np.array([255, 110, 0], float), np.array([255, 255, 255], float)
    rgb = (cov * o + (1 - cov) * w).round().astype(np.uint8)
    Image.fromarray(rgb, "RGB").save(OUT / "T_BarricadeStripe.png")


if __name__ == "__main__":
    sign_cells = build_signs()
    glyph_cells = build_glyphs()
    build_stripe()
    meta = {
        "uv_convention": "uv_offset / uv_scale are top-down (glTF / Unreal: v = 0 at the image top). Atlas UV = mesh UV * uv_scale + uv_offset; "
                         "RK_SignPanel and RK_Glyph carry 0..1 UVs over the whole face.",
        "glyphs": {"file": "T_RoadGlyphs.png", "size": [4 * CELL, 2 * CELL], "grid": [4, 2], "cell_px": CELL,
                   "note": "white RGB, alpha = paint. Top of each cell = direction of travel; image right = the driver's right. "
                           "decal_m = [width across the lane, length along it]: scale RK_Glyph by Unreal X = length, Y = width.",
                   "cells": glyph_cells},
        "signs": {"file": "T_SignAtlas2.png", "size": [4 * CELL, 4 * CELL], "grid": [4, 4], "cell_px": CELL,
                  "note": "each cell is one whole sign face pre-distorted for panel_m = [width, height] in metres. "
                          "panel_scale_from_RK_SignPanel = [width, height] scale of the 0.9 x 0.9 m RK_SignPanel. Alpha 0 outside the sign shape.",
                  "cells": sign_cells},
        "stripe": {"file": "T_BarricadeStripe.png", "size": [512, 128], "tile_m": [0.8, 0.2],
                   "note": "orange (255,110,0) / white 45-degree stripes, tiles in U; RK_Barricade rails are UV'd U = metres / 0.8, V = 0..1 per rail."},
    }
    json.dump(meta, open(OUT / "textures.json", "w"), indent=1)
    print("wrote", OUT)
