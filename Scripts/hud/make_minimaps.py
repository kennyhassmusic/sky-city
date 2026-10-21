"""Map images for the HUD mini map, drawn like a Tesla's dark-mode navigation map: charcoal land, deep blue water, dark
green parks, roads in greys that brighten with the road's class. One image per map, 1 m per pixel, north up; the HUD
material (M_MiniMap, Scripts/hud/minimap_ue.py) turns and zooms it around the car, and the HUD draws the car, the route
and the Superchargers on top.

  Sky City  Saved/Roads/roadnet.json (the exact paved surface: ribbons, junctions, joints) + Saved/Mashup/plan_v3.json
            (water, parks, beaches, landmarks, the L)
  McGregor  Saved/McGregor/mcgregor_data.json (roads, buildings, ponds) + Saved/McGregor/demo_layout.json (the unveil lot,
            its two lines, ramp, line-up, show wall, white building)

Writes SourceArt/HUD/T_MiniMap_<map>.png and Content/SkyCity/Data/minimap.json (where each image sits in plan metres).
Run: python3 -I Scripts/hud/make_minimaps.py [SkyCity] [McGregor]   (needs Pillow; no argument = both; naming one map
redraws only that one and keeps the other's entry in minimap.json)
(20 Oct 2026, mcgregor-unveil agent: McGregor draws every building in demo_layout.json's "buildings" and the stage.)
(20 Oct 2026 night, seam-junctions agent: Sky City draws the elevated expressways' decks and ramps from
Saved/Expressway/expressway_footprint.json, highway-capitol's request.)"""
import json, math, pathlib
from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "SourceArt/HUD"
SS = 2                                            # supersampling, for clean edges

LAND = (40, 43, 49)
WATER = (30, 55, 92)
PARK = (37, 60, 46)
BEACH = (66, 63, 53)
BUILD = (54, 58, 66)
ROAD = {"minor": (90, 96, 107), "mid": (108, 115, 127), "major": (128, 135, 148), "highway": (156, 164, 177)}
JUNCTION = (118, 125, 137)
RAIL = (104, 88, 72)
LOT = (76, 80, 88)
PAINT = (225, 225, 220)
LED = (210, 40, 30)


class Canvas:
    def __init__(self, x0, y0, size_m):
        """x0, y0: plan metres of the image's top-left corner (west edge, north edge)."""
        self.x0, self.y0, self.size = x0, y0, size_m
        self.im = Image.new("RGB", (size_m * SS, size_m * SS), LAND)
        self.d = ImageDraw.Draw(self.im)

    def px(self, p):
        return ((p[0] - self.x0) * SS, (self.y0 - p[1]) * SS)

    def poly(self, ring, fill):
        if ring and len(ring) >= 3:
            self.d.polygon([self.px(p) for p in ring], fill=fill)

    def line(self, pts, width_m, fill):
        if len(pts) >= 2:
            self.d.line([self.px(p) for p in pts], fill=fill, width=max(1, round(width_m * SS)), joint="curve")

    def save(self, name):
        img = self.im.resize((self.size, self.size), Image.LANCZOS)
        OUT.mkdir(parents=True, exist_ok=True)
        img.save(OUT / f"T_MiniMap_{name}.png")
        return {"tex": f"/Game/SkyCity/HUD/T_MiniMap_{name}.T_MiniMap_{name}", "x0": self.x0, "y0": self.y0, "size": self.size}


def sky_city():
    P = json.load(open(ROOT / "Saved/Mashup/plan_v3.json"))
    R = json.load(open(ROOT / "Saved/Roads/roadnet.json"))
    bx0, by0, bx1, by1 = P["bounds"]
    size = 4096
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    c = Canvas(round(cx - size / 2), round(cy + size / 2), size)
    c.d.rectangle([0, 0, size * SS, size * SS], fill=WATER)          # past the bounds is all lake
    c.d.rectangle([*c.px((bx0, by1)), *c.px((bx1, by0))], fill=LAND)
    for ring in P["water"]["outer"]:
        c.poly(ring, WATER)
    for ring in P["water"]["inner"]:
        c.poly(ring, LAND)
    for ring in P["parks"]:
        c.poly(ring, PARK)
    for ring in P["beaches"]:
        c.poly(ring, BEACH)
    for lm in P["landmarks"]:
        c.poly(lm.get("outline"), BUILD)
    for r in P["rail"]:
        c.line(r["pts"], 2.5, RAIL)
    rank = {"minor": 0, "mid": 1, "major": 2, "highway": 3}
    for J in R["junctions"]:
        c.poly(J["ring"], JUNCTION)
    for j in R["joints"]:
        c.poly(j, JUNCTION)
    for e in sorted(R["edges"], key=lambda e: rank.get(e["cls"], 0)):
        if e["ribbon"]:
            c.poly(e["ribbon"], ROAD.get(e["cls"], ROAD["minor"]))
    # the elevated expressways (highway-capitol's Saved/Expressway/expressway_footprint.json: decks and ramp fills) on top,
    # in the expressway grey: they aren't in roadnet.json (it is the ground network) - added 20 Oct night, seam-junctions
    fp = ROOT / "Saved/Expressway/expressway_footprint.json"
    if fp.exists():
        X = json.load(open(fp))
        for ring in X.get("deck", []) + X.get("fill", []):
            c.poly(ring, ROAD["highway"])
    return c.save("SkyCity")


def mcgregor():
    M = json.load(open(ROOT / "Saved/McGregor/mcgregor_data.json"))
    L = json.load(open(ROOT / "Saved/McGregor/demo_layout.json"))
    lot = L["lot"]
    cx, cy = sum(p[0] for p in lot) / 4, sum(p[1] for p in lot) / 4
    size = 2048
    c = Canvas(round(cx - size / 2), round(cy + size / 2), size)
    for pd in M["ponds"]:
        c.poly(pd["ring"], WATER)
    for r in M["roads"]:
        paved = r.get("surface") == "asphalt"
        col = ROAD["major"] if paved else (ROAD["minor"] if r["kind"] not in ("track", "footway", "path") else (52, 54, 58))
        c.line(r["pts"], max(2.0, r.get("w", 5.0)), col)
    for b in M["buildings"]:
        c.poly(b["ring"], BUILD)
    c.poly(lot, LOT)
    for wb in L.get("buildings") or [L["white_building"]]:
        a = math.radians(wb["yaw"])
        ax, ny = (math.sin(a), math.cos(a)), (math.sin(a + math.pi / 2), math.cos(a + math.pi / 2))
        hl, hw = wb["len"] / 2, wb["wid"] / 2
        c.poly([(wb["p"][0] + ax[0] * i * hl + ny[0] * j * hw, wb["p"][1] + ax[1] * i * hl + ny[1] * j * hw) for i, j in ((1, 1), (1, -1), (-1, -1), (-1, 1))], (88, 92, 100))
    st = L.get("stage")
    if st:                                        # the stage deck, its LED edge toward the audience
        a = math.radians(st["yaw"])
        f, ax = (math.sin(a), math.cos(a)), (math.sin(a - math.pi / 2), math.cos(a - math.pi / 2))
        hl, hd = st["len"] / 2, st["dep"] / 2
        q = lambda i, j: (st["p"][0] + ax[0] * i * hl + f[0] * j * hd, st["p"][1] + ax[1] * i * hl + f[1] * j * hd)
        c.poly([q(1, 1), q(1, -1), q(-1, -1), q(-1, 1)], (24, 25, 28))
        c.line([q(-1, 1), q(1, 1)], 1.5, LED)
    for it in L["items"]:
        if it["mesh"] == "MG_LineStripe":
            for s in it["at"]:
                y = math.radians(s["yaw"])
                d = (math.sin(y) * 5, math.cos(y) * 5)
                c.line([(s["p"][0] - d[0], s["p"][1] - d[1]), (s["p"][0] + d[0], s["p"][1] + d[1])], 1.2, PAINT)
        if it["mesh"] == "MG_ShowWall":
            for s in it["at"]:
                y = math.radians(s["yaw"])
                d = (math.sin(y) * 10, math.cos(y) * 10)
                c.line([(s["p"][0], s["p"][1]), (s["p"][0] + d[0], s["p"][1] + d[1])], 3.0, LED)
    r = L["ramp"]
    y = math.radians(r["yaw"])
    c.line([r["p"], (r["p"][0] + math.sin(y) * 14, r["p"][1] + math.cos(y) * 14)], 9.0, (200, 200, 200))
    for v in L["lineup"]:
        c.d.ellipse([*(q - 3 * SS for q in c.px(v["p"])), *(q + 3 * SS for q in c.px(v["p"]))], fill=(170, 175, 185))
    return c.save("McGregor")


if __name__ == "__main__":
    import sys
    want = set(sys.argv[1:]) or {"SkyCity", "McGregor"}
    out = ROOT / "Content/SkyCity/Data/minimap.json"
    info = json.load(open(out)) if out.exists() else {}
    if "SkyCity" in want:
        info["SkyCityMashup"] = sky_city()
    if "McGregor" in want:
        info["McGregor"] = mcgregor()
        info["McGregorNight"] = info["McGregor"]
    json.dump(info, open(out, "w"), indent=1)
    print("wrote", out, info)
