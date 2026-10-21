"""Top-down debug renders of the road network (Saved/Roads/*.png). Imported by roadnet.py; also usable alone."""
import math
from PIL import Image, ImageDraw

X0, Y0, X1, Y1 = -1600, -1700, 1450, 1350


def canvas(s=1.0, box=None):
    x0, y0, x1, y1 = box or (X0, Y0, X1, Y1)
    im = Image.new("RGB", (int((x1 - x0) * s), int((y1 - y0) * s)), (236, 236, 230))
    P = lambda p: ((p[0] - x0) * s, (y1 - p[1]) * s)
    return im, ImageDraw.Draw(im), P


def graph(G, path, s=1.0, box=None, polys=None, lines=None):
    im, dr, P = canvas(s, box)
    for ring, fill in (polys or []):
        if len(ring) >= 3:
            dr.polygon([P(p) for p in ring], fill=fill)
    col = {"highway": (200, 60, 40), "major": (40, 40, 40), "mid": (60, 90, 160), "minor": (130, 130, 130)}
    for u, v, d in G.edges(data=True):
        w = max(1, int(d.get("width", 6) * s * 0.35))
        dr.line([P(p) for p in d["geom"]], fill=col.get(d["cls"], (0, 0, 0)), width=w)
    for pts, fill, w in (lines or []):
        dr.line([P(p) for p in pts], fill=fill, width=w)
    kc = {"deadend": (230, 0, 0), "edge": (0, 160, 0), "junction": (0, 90, 255), "pass": (200, 160, 0)}
    for n, d in G.nodes(data=True):
        x, y = P(d["p"])
        r = 3 if d.get("kind") == "pass" else 4
        dr.ellipse([x - r, y - r, x + r, y + r], outline=kc.get(d.get("kind"), (0, 0, 0)), width=2)
    im.save(path)
    return im


def render_all(data, outdir):
    """Surfaces everywhere, and a detail crop with markings, signals and signs."""
    polys = [(e["ribbon"], (62, 62, 66)) for e in data["edges"] if e["ribbon"]]
    polys += [(j["ring"], (74, 74, 80)) for j in data["junctions"]]
    polys += [(j, (62, 62, 66)) for j in data["joints"]]
    for box, name, sc in (((-300, -1100, 500, -300), "surf_loop", 2.0), ((-1600, -1700, 1450, 1350), "surf_all", 0.6),
                          ((-60, -760, 200, -500), "detail", 6.0), ((-1500, -600, -1100, -200), "detail_austin", 3.0)):
        im, dr, P = canvas(sc, box)
        for ring, fill in polys:
            if len(ring) >= 3:
                dr.polygon([P(p) for p in ring], fill=fill)
        if name.startswith("detail"):
            MK, SIG = data["markings"], data["signals"]
            lw = lambda m: max(1, int(m * sc))
            for kind, colr, w in (("solid_white", (240, 240, 240), 0.15), ("solid_white_thin", (220, 220, 220), 0.1),
                                  ("dash_white", (240, 240, 240), 0.15), ("solid_yellow", (240, 200, 40), 0.12),
                                  ("dash_yellow", (240, 200, 40), 0.12)):
                for ln in MK[kind]:
                    dr.line([P(p) for p in ln], fill=colr, width=lw(w))
            for r in MK["bars"]:
                dr.polygon([P(p) for p in r], fill=(235, 235, 235))
            for a in MK["arrows"]:
                x, y = P(a["p"]); t = math.radians(a["yaw"])
                dr.line([(x, y), (x + math.cos(t) * 2.5 * sc, y - math.sin(t) * 2.5 * sc)], fill=(255, 255, 255), width=3)
                for ch, da in (("L", 1.57), ("R", -1.57)):
                    if ch in a["kind"]:
                        dr.line([(x, y), (x + math.cos(t + da) * 1.5 * sc, y - math.sin(t + da) * 1.5 * sc)], fill=(255, 255, 255), width=3)
            for w_ in MK["words"]:
                x, y = P(w_["p"]); dr.text((x - 8, y - 4), "ONLY", fill=(255, 255, 255))
            for pl in SIG["poles"]:
                x, y = P(pl["p"]); t = math.radians(pl["yaw"])
                dr.line([(x, y), (x + math.cos(t) * pl["arm"] * sc, y - math.sin(t) * pl["arm"] * sc)], fill=(20, 20, 20), width=3)
                dr.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(20, 20, 20))
            gc = [(255, 60, 60), (60, 200, 90), (80, 140, 255), (230, 160, 30)]
            for hd in SIG["heads"]:
                x, y = P(hd["p"]); dr.rectangle([x - 4, y - 4, x + 4, y + 4], fill=gc[hd["group"] % 4])
            for pd in SIG["peds"]:
                x, y = P(pd["p"]); dr.ellipse([x - 3, y - 3, x + 3, y + 3], fill=gc[pd["group"] % 4])
            for sg in data["signs"]:
                x, y = P(sg["p"])
                colr = {"stop": (220, 0, 0), "oneway": (0, 0, 0), "noentry": (200, 0, 120), "speed": (255, 255, 255), "deadend": (240, 200, 0)}.get(sg["kind"], (0, 0, 200))
                dr.rectangle([x - 4, y - 4, x + 4, y + 4], outline=colr, width=2)
            pc = {"lamp": (255, 230, 120), "tree": (40, 140, 40), "hydrant": (230, 30, 30), "bin": (90, 90, 90), "busstop": (0, 120, 255),
                  "shelter": (0, 80, 200), "bench": (140, 90, 40), "dumpster": (0, 110, 60), "bikerack": (150, 150, 150), "drain": (30, 30, 30)}
            for pr in data["props"]:
                if pr["t"] in pc:
                    x, y = P(pr["p"]); r = 3 if pr["t"] != "tree" else 5
                    dr.ellipse([x - r, y - r, x + r, y + r], outline=pc[pr["t"]], width=2)
        im.save(str(outdir / f"{name}.png"))


def render_box(data, box, scale, path, problems=(), placed=None, water=None, buildings=None):
    """Detail crop of one area (plan metres box x0, y0, x1, y1) for the audit: pavement (edge ribbons dark, junction
    rings outlined in blue, joints), lines and bars, lane arrows (shaft + head pointing where the arrow points), signal
    poles with their arms, heads (square, a tick showing which way they face), signs, props, and the audit's problem
    markers (magenta circles with their kind). placed: Saved/Roads/placed_props.json to draw the level's instances
    instead of the JSON's props. water / buildings: lists of rings drawn under everything."""
    x0, y0, x1, y1 = box
    im, dr, P = canvas(scale, box)
    inb = lambda p, m=30: x0 - m <= p[0] <= x1 + m and y0 - m <= p[1] <= y1 + m
    for ring in (water or []):
        if any(inb(p, 200) for p in ring[::max(1, len(ring) // 200)]) or len(ring) > 200:
            dr.polygon([P(p) for p in ring], fill=(150, 185, 215))
    for ring in (buildings or []):
        if inb(ring[0], 60):
            dr.polygon([P(p) for p in ring], fill=(205, 185, 160), outline=(150, 120, 90))
    for e in data["edges"]:
        if e["ribbon"] and any(inb(p) for p in e["ribbon"]):
            dr.polygon([P(p) for p in e["ribbon"]], fill=(62, 62, 66))
    for j in data["joints"]:
        if len(j) >= 3 and inb(j[0]):
            dr.polygon([P(p) for p in j], fill=(70, 66, 62))
    for j in data["junctions"]:
        if inb(j["c"], 60):
            dr.polygon([P(p) for p in j["ring"]], fill=(74, 74, 84))
    for j in data["junctions"]:
        if inb(j["c"], 60):
            dr.line([P(p) for p in j["ring"] + j["ring"][:1]], fill=(90, 140, 255), width=1)
    for e in data["edges"]:
        if any(inb(p) for p in e["geom"]):
            dr.line([P(p) for p in e["geom"]], fill=(120, 120, 60), width=1)
    MK, SIG = data["markings"], data["signals"]
    lw = lambda m: max(1, int(m * scale))
    for kind, colr, w in (("solid_white", (240, 240, 240), 0.15), ("solid_white_thin", (220, 220, 220), 0.1),
                          ("dash_white", (240, 240, 240), 0.15), ("solid_yellow", (240, 200, 40), 0.12),
                          ("dash_yellow", (240, 200, 40), 0.12)):
        for ln in MK[kind]:
            if inb(ln[0]):
                dr.line([P(p) for p in ln], fill=colr, width=lw(w))
    for r in MK["bars"]:
        if inb(r[0]):
            dr.polygon([P(p) for p in r], fill=(235, 235, 235))
    for a in MK["arrows"]:
        if not inb(a["p"]):
            continue
        x, y = P(a["p"]); t = math.radians(a["yaw"])
        ex, ey = x + math.cos(t) * 2.5 * scale, y - math.sin(t) * 2.5 * scale
        bx, by = x - math.cos(t) * 2.0 * scale, y + math.sin(t) * 2.0 * scale
        dr.line([(bx, by), (ex, ey)], fill=(255, 255, 255), width=max(2, int(0.3 * scale)))
        for da in (2.6, -2.6):
            dr.line([(ex, ey), (ex + math.cos(t + da) * 1.0 * scale, ey - math.sin(t + da) * 1.0 * scale)], fill=(255, 255, 255), width=2)
        for ch, da in (("L", 1.57), ("R", -1.57)):
            if ch in a["kind"]:
                dr.line([(x, y), (x + math.cos(t + da) * 1.5 * scale, y - math.sin(t + da) * 1.5 * scale)], fill=(255, 255, 0), width=2)
    for pl in SIG["poles"]:
        if not inb(pl["p"]):
            continue
        x, y = P(pl["p"]); t = math.radians(pl["yaw"])
        dr.line([(x, y), (x + math.cos(t) * pl["arm"] * scale, y - math.sin(t) * pl["arm"] * scale)], fill=(20, 20, 20), width=3)
        dr.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(20, 20, 20), outline=(255, 255, 0))
    gc = [(255, 60, 60), (60, 200, 90), (80, 140, 255), (230, 160, 30)]
    for hd in SIG["heads"]:
        if not inb(hd["p"]):
            continue
        x, y = P(hd["p"]); t = math.radians(hd["yaw"])
        dr.rectangle([x - 4, y - 4, x + 4, y + 4], fill=gc[hd["group"] % 4])
        dr.line([(x, y), (x + math.cos(t) * 10, y - math.sin(t) * 10)], fill=gc[hd["group"] % 4], width=2)
    for sg in data["signs"]:
        if not inb(sg["p"]):
            continue
        x, y = P(sg["p"])
        colr = {"stop": (220, 0, 0), "oneway": (0, 0, 0), "noentry": (200, 0, 120), "speed": (255, 255, 255), "deadend": (240, 200, 0)}.get(sg["kind"], (0, 0, 200))
        dr.rectangle([x - 4, y - 4, x + 4, y + 4], outline=colr, width=2)
        t = math.radians(sg.get("arrow", sg["yaw"]))
        dr.line([(x, y), (x + math.cos(t) * 9, y - math.sin(t) * 9)], fill=colr, width=2)
    pc = {"lamp": (255, 230, 120), "lamp_hw": (255, 230, 120), "tree": (40, 140, 40), "hydrant": (230, 30, 30), "bin": (90, 90, 90),
          "busstop": (0, 120, 255), "shelter": (0, 80, 200), "bench": (140, 90, 40), "dumpster": (0, 110, 60), "bikerack": (150, 150, 150),
          "pole": (0, 0, 0), "post": (120, 0, 120), "pedpost": (255, 140, 0), "cabinet": (90, 60, 30)}
    if placed:
        for lab, rows in placed["inst"].items():
            k = lab.replace("RProps_", "")
            k = "tree" if k in ("liveoak", "honeylocust", "linden", "elm") else k
            if k not in pc:
                continue
            for row in rows:
                p = (row[1] / 100.0, row[0] / 100.0)
                if inb(p, 0):
                    x, y = P(p); r = 2 if k != "tree" else 4
                    dr.ellipse([x - r, y - r, x + r, y + r], outline=pc[k], width=2)
    else:
        for pr in data["props"]:
            if pr["t"] in pc and inb(pr["p"], 0):
                x, y = P(pr["p"]); r = 3 if pr["t"] != "tree" else 5
                dr.ellipse([x - r, y - r, x + r, y + r], outline=pc[pr["t"]], width=2)
    for pb in problems:
        p = pb["plan"]
        if inb(p, 0):
            x, y = P(p)
            dr.ellipse([x - 9, y - 9, x + 9, y + 9], outline=(255, 0, 255), width=2)
            dr.text((x + 10, y - 6), pb["kind"][:14], fill=(255, 0, 255))
    im.save(str(path))
    return im
