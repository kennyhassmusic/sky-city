"""Turn the downloaded OpenStreetMap extracts into one compact, same-scale dataset for the mashup page.

Each city is projected to local metres (x east, y north) around a river anchor, so both rivers line up at
(0, 0) by default: Chicago at the State Street bridge, Austin at the Congress Avenue bridge.
Output: Scripts/mashup/mashup_data.json. Data (c) OpenStreetMap contributors, ODbL.

Run: python3 -I Scripts/mashup/build_mashup_data.py
"""
import json, math, pathlib, subprocess, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
OSM = ROOT / "SourceArt" / "osm"
OUT = ROOT / "Scripts" / "mashup" / "mashup_data.json"

CITIES = {
    "chicago": {
        "bbox": (41.860, -87.665, 41.910, -87.600),
        "origin": (41.88756, -87.6278),           # State Street bridge, on the main branch centerline
        "lake": 1205149,                           # Lake Michigan: water lies east of its shoreline here
        "points": {"The Bean": (41.8827, -87.6233), "Navy Pier": (41.8917, -87.6086),
                   "Buckingham Fountain": (41.8758, -87.6189), "Union Station": (41.8786, -87.6403),
                   "Wrigley Building": (41.8892, -87.6247)},
    },
    "austin": {
        "bbox": (30.245, -97.770, 30.290, -97.715),
        "origin": (30.261444, -97.7451),           # Congress Avenue bridge (the bats), on the river centerline
        "lake": None,
        "points": {"Congress Ave Bridge": (30.2617, -97.7451), "6th Street": (30.2672, -97.7397),
                   "Rainey Street": (30.2585, -97.7385), "UT Tower": (30.2862, -97.7394),
                   "South Congress": (30.2500, -97.7493), "Auditorium Shores": (30.2627, -97.7518)},
    },
}
LANDMARK_BUILDINGS = {"Willis Tower", "Merchandise Mart", "Texas State Capitol"}
ROAD_CLASS = {
    "motorway": "highway", "trunk": "highway", "motorway_link": "highway", "trunk_link": "highway",
    "primary": "major", "secondary": "major", "primary_link": "major", "secondary_link": "major",
    "tertiary": "mid", "tertiary_link": "mid",
    "residential": "minor", "unclassified": "minor", "living_street": "minor", "pedestrian": "ped",
}


def overpass(q):
    # the public server rate-limits back-to-back queries (HTML error page instead of JSON): wait and retry
    for attempt in range(5):
        raw = subprocess.run(["curl", "-sS", "-m", "240", "-A", "SkyCity-mashup/1.0", "--data-urlencode", "data@-",
                              "https://overpass-api.de/api/interpreter"], input=q.encode(), capture_output=True,
                             check=True).stdout
        try:
            return json.loads(raw)["elements"]
        except ValueError:
            time.sleep(20 * (attempt + 1))
    raise RuntimeError("Overpass kept refusing: " + raw[:300].decode(errors="replace"))


class Proj:
    def __init__(self, origin):
        self.lat0, self.lon0 = origin
        self.kx = 111320.0 * math.cos(math.radians(self.lat0))
        self.ky = 110574.0

    def __call__(self, lat, lon):
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)


def segments(geom, proj):
    """Split a way's geometry at clipped (null) nodes into projected point runs."""
    runs, cur = [], []
    for g in geom or []:
        if g is None:
            if len(cur) > 1:
                runs.append(cur)
            cur = []
        else:
            cur.append(proj(g["lat"], g["lon"]))
    if len(cur) > 1:
        runs.append(cur)
    return runs


def simplify(pts, tol=2.0):
    """Douglas-Peucker. A closed ring (first point == last) is split at its farthest point first,
    otherwise the zero-length base segment would collapse the whole ring."""
    if len(pts) < 3:
        return pts
    if math.dist(pts[0], pts[-1]) < 1e-6:
        k = max(range(len(pts)), key=lambda i: math.dist(pts[0], pts[i]))
        if k in (0, len(pts) - 1):
            return pts
        return simplify(pts[:k + 1], tol)[:-1] + simplify(pts[k:], tol)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]; bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1e-9
        best, bi = 0.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = abs(dy * (px - ax) - dx * (py - ay)) / L
            if d > best:
                best, bi = d, i
        if best > tol:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def flat(pts):
    out = []
    for x, y in pts:
        out += [round(x), round(y)]
    return out


def stitch(runs, eps=0.5):
    """Join point runs that share endpoints into longer chains."""
    chains = [list(r) for r in runs]
    merged = True
    while merged:
        merged = False
        for i in range(len(chains)):
            for j in range(len(chains)):
                if i == j or not chains[i] or not chains[j]:
                    continue
                a, b = chains[i], chains[j]
                close = lambda p, q: abs(p[0] - q[0]) < eps and abs(p[1] - q[1]) < eps
                if close(a[-1], b[0]):
                    chains[i] = a + b[1:]
                elif close(a[-1], b[-1]):
                    chains[i] = a + b[::-1][1:]
                elif close(a[0], b[-1]):
                    chains[i] = b + a[1:]
                elif close(a[0], b[0]):
                    chains[i] = b[::-1] + a[1:]
                else:
                    continue
                chains[j] = []
                merged = True
        chains = [c for c in chains if c]
    return chains


def clip_ring(ring, box):
    """Sutherland-Hodgman clip of a polygon ring to an axis-aligned box (minx, miny, maxx, maxy)."""
    minx, miny, maxx, maxy = box
    edges = [(lambda p: p[0] >= minx, lambda p, q: (minx, p[1] + (q[1] - p[1]) * (minx - p[0]) / (q[0] - p[0]))),
             (lambda p: p[0] <= maxx, lambda p, q: (maxx, p[1] + (q[1] - p[1]) * (maxx - p[0]) / (q[0] - p[0]))),
             (lambda p: p[1] >= miny, lambda p, q: (p[0] + (q[0] - p[0]) * (miny - p[1]) / (q[1] - p[1]), miny)),
             (lambda p: p[1] <= maxy, lambda p, q: (p[0] + (q[0] - p[0]) * (maxy - p[1]) / (q[1] - p[1]), maxy))]
    pts = ring
    for inside, cut in edges:
        if not pts:
            break
        out = []
        for i, p in enumerate(pts):
            q = pts[i - 1]
            if inside(p):
                if not inside(q):
                    out.append(cut(q, p))
                out.append(p)
            elif inside(q):
                out.append(cut(q, p))
        pts = out
    return pts


def build(name, cfg):
    proj = Proj(cfg["origin"])
    s, w, n, e = cfg["bbox"]
    (x0, y0), (x1, y1) = proj(s, w), proj(n, e)
    box = (x0, y0, x1, y1)
    data = json.load(open(OSM / f"{name}.json"))["elements"]
    city = {"origin": cfg["origin"], "bbox": [round(v) for v in box], "roads": {}, "rail": {"L": [], "subway": [], "rail": []},
            "water": {"outer": [], "inner": []}, "parks": [], "landmarks": []}
    refetch_ways, refetch_rels = [], []
    for el in data:
        t = el.get("tags", {})
        if t.get("natural") == "water" and el["id"] != cfg["lake"]:
            if el["type"] == "relation":
                refetch_rels.append(el["id"])
            elif None in (el.get("geometry") or []):
                refetch_ways.append(el["id"])   # cut by the map edge: fetch the whole outline
    for el in data:
        t = el.get("tags", {})
        if el["type"] != "way":
            continue
        hw = t.get("highway")
        if hw in ROAD_CLASS:
            cls = ROAD_CLASS[hw]
            for run in segments(el.get("geometry"), proj):
                city["roads"].setdefault(cls, []).append([t.get("name", ""), flat(simplify(run))])
        rw = t.get("railway")
        if rw in ("subway", "light_rail", "monorail", "rail"):
            kind = "rail" if rw == "rail" else ("subway" if t.get("tunnel") in ("yes", "building_passage") else "L")
            if rw == "rail" and t.get("service") in ("yard", "siding", "spur"):
                continue
            for run in segments(el.get("geometry"), proj):
                city["rail"][kind].append(flat(simplify(run)))
        if t.get("building") and t.get("name") in LANDMARK_BUILDINGS:
            pts = [proj(g["lat"], g["lon"]) for g in el.get("geometry") or [] if g]
            if pts:
                cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
                city["landmarks"].append([t["name"], round(cx), round(cy), flat(simplify(pts, 1.0))])
        if t.get("leisure") == "park" or t.get("natural") == "water":
            geom = el.get("geometry") or []
            if geom and geom[0] and geom[-1] and geom[0] == geom[-1] and None not in geom:
                ring = clip_ring([proj(g["lat"], g["lon"]) for g in geom], box)
                if len(ring) > 2:
                    (city["parks"] if t.get("leisure") == "park" else city["water"]["outer"]).append(flat(simplify(ring)))
    # park relations (clipped is fine for parks: draw closed chains only)
    for el in data:
        t = el.get("tags", {})
        if el["type"] == "relation" and t.get("leisure") == "park":
            runs = [r for m in el.get("members", []) if m.get("role") == "outer" for r in segments(m.get("geometry"), proj)]
            for c in stitch(runs):
                if math.dist(c[0], c[-1]) < 1.0:
                    ring = clip_ring(c, box)
                    if len(ring) > 2:
                        city["parks"].append(flat(simplify(ring)))
    # rivers, harbours and other edge-cut water fetched whole, then clipped. Outer and inner rings are kept
    # apart: the page fills outers as a union and cuts inners (islands, bridge decks) back out.
    if refetch_ways:
        time.sleep(5)
        for el in overpass(f"[out:json][timeout:180];way(id:{','.join(map(str, refetch_ways))});out geom;"):
            pts = [proj(g["lat"], g["lon"]) for g in el.get("geometry") or [] if g]
            if len(pts) > 3 and math.dist(pts[0], pts[-1]) < 1.0:
                ring = clip_ring(pts, box)
                if len(ring) > 2:
                    city["water"]["outer"].append(flat(simplify(ring)))
    if refetch_rels:
        time.sleep(5)
        for el in overpass(f"[out:json][timeout:180];relation(id:{','.join(map(str, refetch_rels))});out geom;"):
            for role in ("outer", "inner"):
                runs = [r for m in el.get("members", []) if m.get("role") == role for r in segments(m.get("geometry"), proj)]
                for c in stitch(runs):
                    if math.dist(c[0], c[-1]) < 1.0:
                        ring = clip_ring(c, box)
                        if len(ring) > 2:
                            city["water"][role].append(flat(simplify(ring)))
    # Lake Michigan: shoreline ways near downtown, closed far to the east, then clipped
    if cfg["lake"]:
        b = ",".join(str(v) for v in (s - 0.02, w, n + 0.02, e + 0.05))
        ways = overpass(f"[out:json][timeout:180];rel({cfg['lake']});way(r:\"outer\")({b});out geom;")
        runs = [r for wy in ways for r in segments(wy.get("geometry"), proj)]
        for c in stitch(runs):
            if math.dist(c[0], c[-1]) < 1.0:
                ring = c
            else:
                far = x1 + 20000
                ring = c + [(far, c[-1][1]), (far, c[0][1])]
            ring = clip_ring(ring, box)
            if len(ring) > 2:
                city["water"]["outer"].append(flat(simplify(ring)))
    for label, (lat, lon) in cfg["points"].items():
        x, y = proj(lat, lon)
        city["landmarks"].append([label, round(x), round(y), []])
    return city


def main():
    out = {"attribution": "(c) OpenStreetMap contributors (ODbL)", "cities": {}}
    for name, cfg in CITIES.items():
        c = build(name, cfg)
        out["cities"][name] = c
        print(name, {k: (len(v) if isinstance(v, list) else {kk: len(vv) for kk, vv in v.items()}) for k, v in c.items()
                     if k in ("roads", "rail", "water", "parks", "landmarks")}, "bbox_m", c["bbox"])
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print("wrote", OUT, round(OUT.stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
