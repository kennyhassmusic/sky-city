"""Annotated top-down maps of the McGregor rocket test campus for the Sky City McGregor rebuild.

campus_map.png          core campus, x -1150..1350, y -2100..800 (map metres), over the USDA NAIP 2022-07-11 photo
                        (public domain, the local tiles from Scripts/mcgregor/fetch_rasters.py), OSM footprints
                        (c) OpenStreetMap contributors drawn thin, every facility of facilities.json numbered, legend with
                        map-frame x/y and real lat/lon, 100 m grid ticks, scale bar, north arrow.
campus_map_overview.png the whole property (x -3000..3100, y -2700..2600) at 4 m/px with the same numbers.
Facilities built after the photo (2023-2025, seen on Esri 2025 imagery) are drawn as dashed cyan boxes.
Map frame: metres, x east, y north, origin lat 31.40375 lon -97.4621 (same as Saved/McGregor/mcgregor_data.json).
Run: python3 -I SourceArt/Reference/McGregor/research/make_campus_map.py
"""
import json, math, os, pathlib
from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RAS = pathlib.Path(os.environ.get("SKYCITY_MCGREGOR_RAW", ROOT / "Saved" / "McGregorRaw"))
META = json.load(open(RAS / "rasters.json"))
LAT0, LON0, KX, KY = 31.40375, -97.4621, 95013.4785371064, 110574.0
PX = 4096 / 2400.0
D = json.load(open(ROOT / "Saved/McGregor/mcgregor_data.json"))
FAC = json.load(open(HERE / "facilities.json"))["facilities"]
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONTB = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

SHORT = {"first_stage_stand": "F9 first-stage stand", "tripod_raptor_vertical": "Tripod (Raptor vertical)",
         "structural_test_stand": "Structural stand", "water_tower_central": "Water tower",
         "ground_water_tanks_central": "Ground water tanks", "central_tank_farm": "Tank farm", "hangar_stands": "Stands hangar",
         "raptor_north_complex": "Raptor horizontal bays", "raptor_vertical_2021": "Raptor vertical (2021)", "raptor_shop": "Raptor shop",
         "raptor_prop_farm": "Raptor prop farm", "raptor_north_stand": "Raptor NORTH (2025)", "raptor_south_stand": "Raptor SOUTH (2025)",
         "stage2_stand_new": "Stage-2 stand", "water_tower_east": "East water tower", "s2_tank_farm": "Tank compounds",
         "merlin_vertical_stands": "Merlin vertical stands", "upper_stage_stand": "Upper-stage stand", "mvac_stand": "MVac stand",
         "merlin_horizontal_stand": "Horizontal M1D (prob.)", "merlin_tank_farm": "Merlin tank row", "merlin_round_tank": "Round tank",
         "merlin_retention_basin": "Retention basin", "blockhouse_control": "Blockhouse", "offices_shops": "Offices / shops",
         "old_core_storage_hangar": "Old core hangar", "office_annexes": "Annexes", "main_parking": "Main parking",
         "main_gate": "Main entrance", "boneyard": "Boneyard", "new_core_storage_hangar": "New core hangar (2015)",
         "dragon_processing": "Dragon site", "small_test_pads": "Small test pads", "superdraco_stand": "SuperDraco stand",
         "grasshopper_pad": "Grasshopper pad", "raptor_assembly_building": "Raptor factory", "rocket_development_hangar": "Rocket Dev. Hangar",
         "storage_building_2026": "Storage bldg 2026", "hls_rig_2025": "2025 rig", "ww2_magazine_igloos": "WWII igloos", "substation": "Substation", "historic_west_plant": "Historic west plant"}
NEW = {"raptor_north_stand": [(812, 589), (1007, 714)], "raptor_south_stand": [(789, 177), (980, 254)]}   # 2025 pads, not in the 2022 photo
LABEL_DX = {"first_stage_stand": "left", "water_tower_central": "left_down", "ground_water_tanks_central": "left_up", "central_tank_farm": "up",
            "merlin_vertical_stands": "right_up", "mvac_stand": "right_down", "merlin_round_tank": "left", "upper_stage_stand": "right",
            "office_annexes": "left", "main_parking": "left", "raptor_shop": "right", "s2_tank_farm": "left"}
INSETS = [("Central stands (NAIP 2022)", (-280, -700, 140, -380)), ("Merlin / stage-2 complex (NAIP 2022)", (380, -1480, 700, -1000))]
CAT_COL = {"test_stand": (255, 70, 60), "tank_farm": (80, 200, 255), "utility": (120, 230, 255), "building": (255, 210, 60),
           "parking": (200, 200, 200), "access": (120, 255, 120), "yard": (210, 160, 110), "historic": (200, 160, 255)}


def ll(x, y):
    return LAT0 + y / KY, LON0 + x / KX


def naip(x0, y0, x1, y1, mpp):
    W, H = int(round((x1 - x0) / mpp)), int(round((y1 - y0) / mpp))
    out = Image.new("RGB", (W, H), (40, 40, 40))
    for t in META["tiles"]:
        tx0, ty0 = t["x0"], t["y0"]
        ix0, iy0, ix1, iy1 = max(x0, tx0), max(y0, ty0), min(x1, tx0 + 2400), min(y1, ty0 + 2400)
        if ix0 >= ix1 or iy0 >= iy1:
            continue
        im = Image.open(RAS / t["file"]).convert("RGB")
        box = ((ix0 - tx0) * PX, (ty0 + 2400 - iy1) * PX, (ix1 - tx0) * PX, (ty0 + 2400 - iy0) * PX)
        w, h = int(round((ix1 - ix0) / mpp)), int(round((iy1 - iy0) / mpp))
        out.paste(im.resize((w, h), Image.LANCZOS, box=box), (int(round((ix0 - x0) / mpp)), int(round((y1 - iy1) / mpp))))
    return out


def text(d, xy, s, f, fill=(255, 255, 255), stroke=(0, 0, 0), sw=3, anchor="la"):
    d.text(xy, s, font=f, fill=fill, stroke_width=sw, stroke_fill=stroke, anchor=anchor)


def dashed_rect(d, a, b, col, w=3, dash=14):
    (x0, y0), (x1, y1) = a, b
    for (p, q) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        L = math.dist(p, q)
        n = max(1, int(L / dash))
        for k in range(0, n, 2):
            t0, t1 = k / n, min(1, (k + 1) / n)
            d.line([(p[0] + (q[0] - p[0]) * t0, p[1] + (q[1] - p[1]) * t0), (p[0] + (q[0] - p[0]) * t1, p[1] + (q[1] - p[1]) * t1)], fill=col, width=w)


def draw_map(x0, y0, x1, y1, mpp, out, title, legend=True, labels=True, footprints=True, grid=100, scale_len=200):
    base = naip(x0, y0, x1, y1, mpp)
    W, H = base.size
    # gently darken the photo so marks read
    base = Image.blend(base, Image.new("RGB", base.size, (0, 0, 0)), 0.18)
    d = ImageDraw.Draw(base)
    P = lambda x, y: ((x - x0) / mpp, (y1 - y) / mpp)
    fs = max(14, int(22 * 1.1 / mpp)) if mpp < 2 else 16
    f = ImageFont.truetype(FONT, fs)
    fb = ImageFont.truetype(FONTB, fs)
    fsm = ImageFont.truetype(FONT, max(12, fs - 6))
    if footprints:
        for b in D["buildings"]:
            r = [P(*p) for p in b["ring"]]
            if any(-50 < u < W + 50 and -50 < v < H + 50 for u, v in r):
                d.line(r + [r[0]], fill=(255, 0, 255), width=1)
        for t in D["tanks"]:
            cx, cy = P(*t["p"])
            rr = min(t["r"], 8) / mpp
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(0, 255, 255))
    for k, box in NEW.items():
        a, b = P(box[0][0], box[1][1]), P(box[1][0], box[0][1])
        dashed_rect(d, a, b, (0, 255, 255), w=max(2, int(3 / mpp * 1.1)))
    # grid ticks + labels
    g = math.ceil(x0 / grid) * grid
    while g < x1:
        X = P(g, 0)[0]
        d.line([(X, 0), (X, 14)], fill=(255, 255, 0), width=2); d.line([(X, H - 14), (X, H)], fill=(255, 255, 0), width=2)
        if (g // grid) % (2 if mpp < 2 else 5) == 0:
            text(d, (X + 3, 16), f"x{int(g)}", fsm, fill=(255, 255, 0))
        g += grid
    g = math.ceil(y0 / grid) * grid
    while g < y1:
        Y = P(0, g)[1]
        d.line([(0, Y), (14, Y)], fill=(255, 255, 0), width=2); d.line([(W - 14, Y), (W, Y)], fill=(255, 255, 0), width=2)
        if (g // grid) % (2 if mpp < 2 else 5) == 0:
            text(d, (18, Y - fs // 2), f"y{int(g)}", fsm, fill=(255, 255, 0))
        g += grid
    # facilities
    offmap = []
    for fct in FAC:
        if fct.get("x") is None:
            continue
        x, y = fct["x"], fct["y"]
        u, v = P(x, y)
        col = CAT_COL.get(fct["category"], (255, 255, 255))
        if not (0 <= u < W and 0 <= v < H):
            offmap.append(fct)
            continue
        r = max(11, int(fs * 0.72))
        d.ellipse([u - r, v - r, u + r, v + r], fill=(0, 0, 0), outline=col, width=3)
        text(d, (u, v), str(fct["map_no"]), fb if fct["map_no"] < 10 else f, fill=col, sw=0, anchor="mm")
        if labels:
            lab = SHORT.get(fct["id"], fct["name"])[:28]
            tw = d.textlength(lab, font=fsm)
            mode = LABEL_DX.get(fct["id"], "right")
            lx, ly = u + r + 4, v - fs // 2 - 1
            if mode.startswith("left"):
                lx = u - r - 4 - tw
            if mode.endswith("up"):
                ly -= fs
            if mode.endswith("down"):
                ly += fs
            if mode == "up":
                lx, ly = u - tw / 2, v - r - fs - 4
            text(d, (lx, ly), lab, fsm, fill=(255, 255, 255))
    for fct in offmap:   # arrows at the edge for facilities beyond the frame
        x, y = fct["x"], fct["y"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ang = math.atan2(y - cy, x - cx)
        # intersect with the frame
        tx = ((x1 - 30 * mpp) - cx) / math.cos(ang) if math.cos(ang) > 1e-6 else ((x0 + 30 * mpp) - cx) / math.cos(ang) if math.cos(ang) < -1e-6 else 1e9
        ty = ((y1 - 30 * mpp) - cy) / math.sin(ang) if math.sin(ang) > 1e-6 else ((y0 + 30 * mpp) - cy) / math.sin(ang) if math.sin(ang) < -1e-6 else 1e9
        t = min(abs(tx), abs(ty))
        ex, ey = cx + t * math.cos(ang), cy + t * math.sin(ang)
        u, v = P(ex, ey)
        dist = math.hypot(x - ex, y - ey)
        col = CAT_COL.get(fct["category"], (255, 255, 255))
        hu, hv = u + 26 * math.cos(ang), v - 26 * math.sin(ang)
        d.line([(u - 30 * math.cos(ang), v + 30 * math.sin(ang)), (hu, hv)], fill=col, width=4)
        d.polygon([(hu + 12 * math.cos(ang), hv - 12 * math.sin(ang)), (hu + 10 * math.cos(ang + 2.4), hv - 10 * math.sin(ang + 2.4)),
                   (hu + 10 * math.cos(ang - 2.4), hv - 10 * math.sin(ang - 2.4))], fill=col)
        s = f"{fct['map_no']} {SHORT.get(fct['id'], fct['name'])} ({x:.0f}, {y:.0f}) {dist / 1000:.1f} km"
        tw = d.textlength(s, font=fsm)
        text(d, (min(max(u - tw / 2, 8), W - tw - 8), v + (18 if v < H / 2 else -38)), s, fsm, fill=col)
    # north arrow + scale bar
    nx, ny = W - 70, 90
    d.polygon([(nx, ny - 50), (nx - 18, ny + 10), (nx, ny), (nx + 18, ny + 10)], fill=(255, 255, 255), outline=(0, 0, 0))
    text(d, (nx, ny + 30), "N", fb, anchor="mm")
    sl = scale_len / mpp
    sx, sy = 40, H - 60
    d.rectangle([sx, sy, sx + sl, sy + 10], fill=(255, 255, 255), outline=(0, 0, 0))
    d.rectangle([sx, sy, sx + sl / 2, sy + 10], fill=(0, 0, 0))
    text(d, (sx, sy - 6), "0", fsm, anchor="ls"); text(d, (sx + sl, sy - 6), f"{scale_len} m", fsm, anchor="ms")
    text(d, (sx, H - 22), "Base photo: USDA NAIP 2022-07-11 (public domain). Footprints magenta/cyan: (c) OpenStreetMap contributors. "
         "Dashed cyan = built after the photo (Esri 2025).", fsm)
    if not legend:
        base.save(out, optimize=True)
        return base
    # legend panel
    LW = 1050 if mpp < 2 else 900
    full = Image.new("RGB", (W + LW, H), (18, 20, 24))
    full.paste(base, (0, 0))
    d = ImageDraw.Draw(full)
    lf = ImageFont.truetype(FONT, 21 if mpp < 2 else 17)
    lfb = ImageFont.truetype(FONTB, 30 if mpp < 2 else 22)
    yy = 24
    text(d, (W + 24, yy), title, lfb, sw=0); yy += 46
    text(d, (W + 24, yy), "Map frame: metres, x east / y north from lat 31.40375, lon -97.4621 (Unreal X = y*100, Y = x*100 cm)", lf, fill=(190, 190, 190), sw=0); yy += 34
    text(d, (W + 24, yy), " #  facility                                  x       y       lat        lon        conf.", lf, fill=(150, 150, 150), sw=0); yy += 30
    rowh = (H - yy - 140) / max(1, len(FAC))
    rowh = min(rowh, 46 if mpp < 2 else 40)
    for fct in FAC:
        col = CAT_COL.get(fct["category"], (255, 255, 255))
        if fct.get("x") is None:
            pos = "position not public / not found"
        else:
            la, lo = ll(fct["x"], fct["y"])
            pos = f"{fct['x']:>6.0f} {fct['y']:>7.0f}   {la:.5f}  {lo:.5f}"
        name = SHORT.get(fct["id"], fct["name"])
        d.ellipse([W + 24, yy + 2, W + 24 + 24, yy + 26], outline=col, width=3)
        text(d, (W + 36, yy + 14), str(fct["map_no"]), ImageFont.truetype(FONT, 14), fill=col, sw=0, anchor="mm")
        text(d, (W + 58, yy + 2), name, lf, fill=col, sw=0)
        text(d, (W + 330 if mpp < 2 else W + 290, yy + 2), pos + f"   {fct.get('confidence', '')}", lf, fill=(225, 225, 225), sw=0)
        yy += rowh
    yy += 12
    for cat, col in CAT_COL.items():
        pass
    keyline = "  ".join(f"{c}" for c in CAT_COL)
    x = W + 24
    for cat, col in CAT_COL.items():
        d.rectangle([x, yy + 4, x + 16, yy + 20], fill=col)
        text(d, (x + 22, yy), cat.replace("_", " "), lf, fill=(200, 200, 200), sw=0)
        x += 34 + d.textlength(cat, font=lf)
        if x > W + LW - 160:
            x, yy = W + 24, yy + 30
    yy += 40
    text(d, (W + 24, yy), "Details, sizes, heights, looks and sources: Saved/McGregor/site_research.json", lf, fill=(160, 160, 160), sw=0)
    yy += 40
    if mpp < 2:   # zoomed insets of the crowded areas
        ix = W + 24
        for title_i, (a0, b0, a1, b1) in INSETS:
            iw = (LW - 72) // 2
            ih_max = H - yy - 70
            m2 = max((a1 - a0) / iw, (b1 - b0) / ih_max)
            iw = int((a1 - a0) / m2)
            ih = int((b1 - b0) / m2)
            if yy + ih + 40 > H:
                break
            ins = naip(a0, b0, a1, b1, m2)
            di = ImageDraw.Draw(ins)
            Q = lambda x, y: ((x - a0) / m2, (b1 - y) / m2)
            for b in D["buildings"]:
                rr_ = [Q(*q) for q in b["ring"]]
                if any(0 <= u_ < iw and 0 <= v_ < ih for u_, v_ in rr_):
                    di.line(rr_ + [rr_[0]], fill=(255, 0, 255), width=1)
            fi = ImageFont.truetype(FONTB, 15)
            for fct in FAC:
                if fct.get("x") is None:
                    continue
                u_, v_ = Q(fct["x"], fct["y"])
                if 0 <= u_ < iw and 0 <= v_ < ih:
                    col = CAT_COL.get(fct["category"], (255, 255, 255))
                    di.ellipse([u_ - 11, v_ - 11, u_ + 11, v_ + 11], fill=(0, 0, 0), outline=col, width=2)
                    text(di, (u_, v_), str(fct["map_no"]), fi, fill=col, sw=0, anchor="mm")
            sb = 50 / m2
            di.rectangle([10, ih - 22, 10 + sb, ih - 14], fill=(255, 255, 255), outline=(0, 0, 0))
            text(di, (14 + sb, ih - 30), "50 m", ImageFont.truetype(FONT, 13))
            full.paste(ins, (ix, yy + 30))
            text(d, (ix, yy + 4), title_i + f"  x {a0}..{a1}, y {b0}..{b1}", ImageFont.truetype(FONT, 15), fill=(200, 200, 200), sw=0)
            ix += iw + 24
    full.save(out, optimize=True)
    return full


if __name__ == "__main__":
    im = draw_map(-1150, -2100, 1350, 800, 1.1, HERE / "campus_map_rgb.png", "McGregor rocket test campus: facility map")
    # quantize to keep the PNG small
    q = im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
    q.save(HERE / "campus_map.png", optimize=True)
    (HERE / "campus_map_rgb.png").unlink()
    ov = draw_map(-3000, -2700, 3100, 2600, 4.0, HERE / "campus_map_overview.png", "McGregor property overview", labels=False, grid=500, scale_len=1000)
    ov.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG).save(HERE / "campus_map_overview.png", optimize=True)
    for n in ("campus_map.png", "campus_map_overview.png"):
        p = HERE / n
        print(n, Image.open(p).size, round(p.stat().st_size / 1e6, 2), "MB")
