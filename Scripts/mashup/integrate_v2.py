"""Integrate a saved Chicago x Austin mashup layout into one city plan that reads as a single city.

Compared with v1 (straight Seam Boulevard), this version:
  - meanders the seam, so the cities meet along an organic line,
  - stitches streets: every street the seam cut is paired with a compatible street on the other side
    (big roads first, so arterials carry through) and joined by a smooth curve; leftovers tee into the
    nearest road,
  - continues Lake Michigan across the seam: a new shoreline, beach and lakefront park on the Austin side,
    with Lake Shore Drive carried on unbroken and a frontage street that Austin's grid flows into,
  - joins Lady Bird Lake to the Chicago River, and marks every road crossing water as a bridge,
  - reconnects Chicago's L across the seam with smooth curves.

Usage: python3 -I Scripts/mashup/integrate_v2.py <layout.json> <plan_out.json>
Units: metres, x east, y north, origin = Chicago State St bridge (the layout's frame).
"""
import json, math, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
DATA = json.load(open(HERE / "mashup_data.json"))["cities"]
MARGIN = 300.0          # city kept around the play area
SETBACK = 18.0          # each city stops this far short of the seam; stitches cross the gap
MIN_SCRAP = 35.0
RANK = {"ped": 0, "minor": 1, "mid": 2, "major": 3, "highway": 4}
CLASS_OF = {v: k for k, v in RANK.items()}
# meander of the seam (two sine waves along it)
MEANDER = [(85.0, 1450.0, 0.7), (32.0, 520.0, 2.2)]
# lakefront on the Austin side, measured inland from the new shoreline
BEACH_W, PARK_W, LSD_AT, FRONTAGE_AT, CITY_FROM = 45.0, 175.0, 105.0, 190.0, 205.0
JOIN_GAP = 260.0
JOIN_DEPTH = 45.0


# ---- small geometry helpers ----------------------------------------------------------------------
def pairs(flat):
    return [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]


def length(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def unit(v):
    L = math.hypot(*v) or 1.0
    return (v[0] / L, v[1] / L)


def bezier(p0, h0, p3, h3, k=None, n=14):
    """Cubic from p0 leaving along h0 to p3 arriving against h3 (h3 points out of p3's road)."""
    D = math.dist(p0, p3)
    k = k or max(8.0, 0.42 * D)
    p1 = (p0[0] + h0[0] * k, p0[1] + h0[1] * k)
    p2 = (p3[0] + h3[0] * k, p3[1] + h3[1] * k)
    out = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def nearest_on(pts, p):
    best = (1e18, None, 0)
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy or 1e-9
        u = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
        q = (a[0] + dx * u, a[1] + dy * u)
        d = math.dist(p, q)
        if d < best[0]:
            best = (d, q, i)
    return best


def clip_polyline(pts, f):
    """Parts of a polyline where f(p) >= 0, as [(points, start_cut, end_cut)]."""
    out, cur, cs = [], [], False
    fv = [f(p) for p in pts]
    for i, p in enumerate(pts):
        if i == 0:
            if fv[0] >= 0:
                cur = [p]
            continue
        q, fq, fp = pts[i - 1], fv[i - 1], fv[i]
        if fp >= 0 and fq >= 0:
            cur.append(p)
        elif fp >= 0 > fq:
            u = fq / (fq - fp)
            cur, cs = [(q[0] + (p[0] - q[0]) * u, q[1] + (p[1] - q[1]) * u), p], True
        elif fq >= 0 > fp:
            u = fq / (fq - fp)
            cur.append((q[0] + (p[0] - q[0]) * u, q[1] + (p[1] - q[1]) * u))
            out.append((cur, cs, True))
            cur, cs = [], False
    if len(cur) > 1:
        out.append((cur, cs, False))
    return out


def clip_ring(ring, fs):
    pts = ring
    for f in fs:
        if not pts:
            break
        out = []
        for i, p in enumerate(pts):
            q = pts[i - 1]
            fp, fq = f(p), f(q)
            if fp >= 0:
                if fq < 0:
                    u = fq / (fq - fp)
                    out.append((q[0] + (p[0] - q[0]) * u, q[1] + (p[1] - q[1]) * u))
                out.append(p)
            elif fq >= 0:
                u = fq / (fq - fp)
                out.append((q[0] + (p[0] - q[0]) * u, q[1] + (p[1] - q[1]) * u))
        pts = out
    return pts


def point_in_ring(p, ring):
    x, y, inside = p[0], p[1], False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            inside = not inside
    return inside


def r1(pts):
    return [[round(x, 1), round(y, 1)] for x, y in pts]


# ---- the layout frame and the meandering seam ------------------------------------------------------
class Frame:
    def __init__(self, L):
        a = math.radians(L["seam"]["angleDeg"])
        self.S = (L["seam"]["x"], L["seam"]["y"])
        self.d = (math.cos(a), math.sin(a))
        self.n = (-math.sin(a), math.cos(a))
        self.sgn = {"chicago": -1 if L["seam"]["chicagoSide"] == "south" else 1}
        self.sgn["austin"] = -self.sgn["chicago"]
        t = math.radians(L["austin"]["rotationDeg"])
        self.rc, self.rs = math.cos(t), math.sin(t)
        self.off_xy = (L["austin"]["x"], L["austin"]["y"])
        pa = L["playArea"]
        h = pa["sizeM"] / 2 + MARGIN
        self.box = (pa["x"] - h, pa["y"] - h, pa["x"] + h, pa["y"] + h)
        hp = pa["sizeM"] / 2
        self.play = (pa["x"] - hp, pa["y"] - hp, pa["x"] + hp, pa["y"] + hp)

    def tf(self, city):
        if city == "chicago":
            return lambda x, y: (x, y)
        return lambda x, y: (self.rc * x - self.rs * y + self.off_xy[0], self.rs * x + self.rc * y + self.off_xy[1])

    def t(self, p):
        return (p[0] - self.S[0]) * self.d[0] + (p[1] - self.S[1]) * self.d[1]

    def off(self, t):
        return sum(A * math.sin(2 * math.pi * t / lam + ph) for A, lam, ph in MEANDER)

    def csd(self, p):
        """Signed distance from the meandering seam (+ = left of the seam direction)."""
        sd = (p[0] - self.S[0]) * self.n[0] + (p[1] - self.S[1]) * self.n[1]
        return sd - self.off(self.t(p))

    def at(self, t, s=0.0):
        o = self.off(t) + s
        return (self.S[0] + self.d[0] * t + self.n[0] * o, self.S[1] + self.d[1] * t + self.n[1] * o)

    def inbox(self, p, pad=0.0):
        x0, y0, x1, y1 = self.box
        return x0 - pad <= p[0] <= x1 + pad and y0 - pad <= p[1] <= y1 + pad

    def box_fs(self):
        x0, y0, x1, y1 = self.box
        return [lambda p: p[0] - x0, lambda p: x1 - p[0], lambda p: p[1] - y0, lambda p: y1 - p[1]]


# ---- lakefront continued on the Austin side ---------------------------------------------------------
class Lakefront:
    """A new shoreline that carries Chicago's shore on into the Austin side, with inland offsets."""

    def __init__(self, F, chicago_lake_rings, lake_interval):
        self.F = F
        t_lo, t_hi = lake_interval
        # the shore end of the lake's contact with the seam is the end nearer the play-area centre
        c = ((F.play[0] + F.play[2]) / 2, (F.play[1] + F.play[3]) / 2)
        e_lo, e_hi = F.at(t_lo), F.at(t_hi)
        shore_t, lake_t = (t_lo, t_hi) if math.dist(e_lo, c) < math.dist(e_hi, c) else (t_hi, t_lo)
        self.P0 = F.at(shore_t)
        lake_pt = F.at((shore_t + lake_t) / 2, F.sgn["chicago"] * 60)
        # heading of Chicago's real shore: walk the lake outline away from the seam for ~350 m, then aim back at P0
        best_ring, best_i, best_d = None, 0, 1e18
        for r in chicago_lake_rings:
            for i, q in enumerate(r):
                dd = math.dist(q, self.P0)
                if dd < best_d:
                    best_ring, best_i, best_d = r, i, dd
        h = None
        if best_ring and best_d < 60:
            n = len(best_ring)
            for step in (1, -1):
                nxt = best_ring[(best_i + step) % n]
                if abs(F.csd(nxt)) < 3:          # that way runs along the seam cut, not the shore
                    continue
                walked, i, prev = 0.0, best_i, best_ring[best_i]
                while walked < 350 and abs(i - best_i) < n:
                    i += step
                    q = best_ring[i % n]
                    walked += math.dist(prev, q)
                    prev = q
                h = unit((self.P0[0] - prev[0], self.P0[1] - prev[1]))
                break
        if h is None:
            h = F.d
        # make sure it heads into the Austin side at a sensible angle (at least 20 degrees off the seam)
        along = h[0] * F.d[0] + h[1] * F.d[1]
        across = (h[0] * F.n[0] + h[1] * F.n[1]) * F.sgn["austin"]
        if across < math.sin(math.radians(20)):
            ang = math.radians(20) if along >= 0 else math.radians(160)
            h = (F.d[0] * math.cos(ang) + F.n[0] * F.sgn["austin"] * math.sin(ang),
                 F.d[1] * math.cos(ang) + F.n[1] * F.sgn["austin"] * math.sin(ang))
        self.heading = h
        # lake lies on the side of the heading where lake_pt is
        cross = h[0] * (lake_pt[1] - self.P0[1]) - h[1] * (lake_pt[0] - self.P0[0])
        self.lake_left = cross > 0
        # walk the new shore with a slow organic bend until it leaves the bounds
        base = math.atan2(h[1], h[0])
        pts, p, s = [self.P0], self.P0, 0.0
        while s < 6000 and F.inbox(p, 150):
            s += 25.0
            a = base + math.radians(9.0) * math.sin(2 * math.pi * s / 1700 + 0.4) + math.radians(4.0) * math.sin(2 * math.pi * s / 600)
            p = (p[0] + 25.0 * math.cos(a), p[1] + 25.0 * math.sin(a))
            pts.append(p)
        # extend a little back across the seam so offsets near P0 are well defined
        back = (self.P0[0] - h[0] * 300, self.P0[1] - h[1] * 300)
        self.shore = [back] + pts

    def inland(self, p):
        """Signed distance from the new shore, positive on the land side."""
        d, q, i = nearest_on(self.shore, p)
        a, b = self.shore[i], self.shore[i + 1]
        cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        left = cross > 0
        return -d if left == self.lake_left else d

    def offset_line(self, dist):
        """The shore offset inland by dist (sampled at the shore points)."""
        out = []
        for a, b in zip(self.shore, self.shore[1:]):
            tx, ty = unit((b[0] - a[0], b[1] - a[1]))
            nx, ny = (-ty, tx) if not self.lake_left else (ty, -tx)   # inland normal
            out.append((a[0] + nx * dist, a[1] + ny * dist))
        return out

    def band(self, d0, d1):
        a, b = self.offset_line(d0), self.offset_line(d1)
        return a + b[::-1]

    def lake_poly(self):
        far = self.offset_line(-30000)
        return self.shore[:-1] + far[::-1]


# ---- the integration ---------------------------------------------------------------------------------
def integrate(L):
    F = Frame(L)
    plan = {"frame": {"origin": "Chicago State St bridge", "units": "m, x east, y north"}, "layout": L,
            "playArea": F.play, "bounds": F.box, "roads": [], "bridges": [], "rail": [],
            "water": {"outer": [], "inner": []}, "parks": [], "beaches": [], "landmarks": [], "seam": [], "stats": {}}
    stats = plan["stats"]
    side = {c: (lambda p, sg=F.sgn[c]: sg * F.csd(p)) for c in ("chicago", "austin")}

    # seam polyline for reference
    corners = [(F.box[0], F.box[1]), (F.box[2], F.box[1]), (F.box[0], F.box[3]), (F.box[2], F.box[3])]
    ts = [F.t(c) for c in corners]
    plan["seam"] = r1([F.at(t) for t in [min(ts) + i * 20 for i in range(int((max(ts) - min(ts)) / 20) + 1)] if F.inbox(F.at(t))])

    # 1. water, each side clipped at the meandering seam
    touch = {"chicago": [], "austin": []}
    chicago_lake = []
    clipped_water = {"chicago": {"outer": [], "inner": []}, "austin": {"outer": [], "inner": []}}
    for city in ("chicago", "austin"):
        tf = F.tf(city)
        fs = [side[city]] + F.box_fs()
        for role in ("outer", "inner"):
            for flat in DATA[city]["water"][role]:
                ring = clip_ring([tf(x, y) for x, y in pairs(flat)], fs)
                if len(ring) < 3:
                    continue
                clipped_water[city][role].append(ring)
                if role == "outer":
                    on = [(F.t(p), F.t(q)) for p, q in zip(ring, ring[1:] + ring[:1]) if abs(F.csd(p)) < 3.0 and abs(F.csd(q)) < 3.0]
                    for a, b in on:
                        touch[city].append(sorted((a, b)))
                    if city == "chicago":
                        chicago_lake.append(ring)

    # walk the seam and record where each side is wet: contact runs (t0, t1, area of that water)
    def ring_area(r):
        return abs(sum(r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1] for i in range(len(r)))) / 2

    def seam_runs(city):
        rings = [(r, min(p[0] for p in r), min(p[1] for p in r), max(p[0] for p in r), max(p[1] for p in r), ring_area(r))
                 for r in clipped_water[city]["outer"]]
        islands = clipped_water[city]["inner"]
        tmin, tmax = min(ts), max(ts)
        runs, cur = [], None
        t = tmin
        while t <= tmax:
            q = F.at(t, F.sgn[city] * 2.5)
            hit = None
            if F.inbox(q):
                for r, x0, y0, x1, y1, A in rings:
                    if x0 <= q[0] <= x1 and y0 <= q[1] <= y1 and point_in_ring(q, r) and not any(point_in_ring(q, i) for i in islands):
                        hit = A if hit is None else max(hit, A)
            if hit is not None:
                cur = [t, t, hit] if cur is None else [cur[0], t, max(cur[2], hit)]
            elif cur is not None:
                runs.append(cur); cur = None
            t += 6.0
        if cur is not None:
            runs.append(cur)
        return [r for r in runs if r[1] - r[0] >= 6]

    ch_runs, au_runs = seam_runs("chicago"), seam_runs("austin")
    lakes = [r for r in ch_runs if r[2] > 4.0e5]   # Lake Michigan pieces; river pieces are far smaller
    lake_run = max(lakes, key=lambda r: r[2]) if lakes else None
    ch = [r[:2] for r in ch_runs if r is not lake_run]
    au = [r[:2] for r in au_runs]
    lake_iv = lake_run[:2] if lake_run else None
    stats["seam_water"] = {"chicago": [[round(a), round(b), round(A)] for a, b, A in ch_runs], "austin": [[round(a), round(b)] for a, b, _ in au_runs],
                           "lake": [round(v) for v in lake_iv] if lake_iv else None}
    LF = Lakefront(F, chicago_lake, lake_iv) if lake_iv else None
    stats["lakefront_continued"] = bool(LF)

    land_ok = (lambda p: LF.inland(p)) if LF else (lambda p: 1e9)
    for role in ("outer", "inner"):
        plan["water"][role] += [r1(r) for r in clipped_water["chicago"][role]]
        for r in clipped_water["austin"][role]:
            r2 = clip_ring(r, [land_ok]) if LF else r
            if len(r2) >= 3:
                plan["water"][role].append(r1(r2))
    # river mouths that meet across the seam get a tapered join
    joins = []
    for a1, a2 in au:
        best = None
        for c1, c2 in ch:
            gap = max(0.0, max(a1, c1) - min(a2, c2))
            wa, wc = a2 - a1, c2 - c1
            if max(wa, wc) <= 4 * min(wa, wc) and max(wa, wc) < 600 and gap <= JOIN_GAP and (best is None or gap < best[0]):
                best = (gap, c1, c2)
        if best:
            _, c1, c2 = best
            sa, sc = F.sgn["austin"] * JOIN_DEPTH, F.sgn["chicago"] * JOIN_DEPTH
            lo, hi = min(a1, c1), max(a2, c2)
            quad = [F.at(a1, sa), F.at(a2, sa)] + [F.at(hi - (hi - lo) * i / 8) for i in range(9)][:1] + [F.at(c2, sc), F.at(c1, sc), F.at(lo)]
            ring = clip_ring(quad, F.box_fs())
            if len(ring) >= 3:
                plan["water"]["outer"].append(r1(ring))
                joins.append({"austin": [round(a1), round(a2)], "chicago": [round(c1), round(c2)]})
    stats["river_joins"] = joins

    # 2. the new lake, beach and lakefront park on the Austin side
    if LF:
        fs = [side["austin"]] + F.box_fs()
        lake = clip_ring(LF.lake_poly(), fs)
        if len(lake) >= 3:
            plan["water"]["outer"].append(r1(lake))
        beach = clip_ring(LF.band(0, BEACH_W), fs)
        if len(beach) >= 3:
            plan["beaches"].append(r1(beach))
        park = clip_ring(LF.band(BEACH_W, PARK_W), fs)
        if len(park) >= 3:
            plan["parks"].append(r1(park))

    # 3. parks
    for city in ("chicago", "austin"):
        tf = F.tf(city)
        fs = [side[city]] + F.box_fs() + ([lambda p: LF.inland(p) - PARK_W] if (LF and city == "austin") else [])
        for flat in DATA[city]["parks"]:
            ring = clip_ring([tf(x, y) for x, y in pairs(flat)], fs)
            if len(ring) >= 3:
                plan["parks"].append(r1(ring))

    # 4. streets: clip, remember every cut end
    roads, ends, lake_ends = [], [], []

    def add_road(pts, cls, city, name, new=False):
        roads.append({"cls": cls, "city": city, "name": name, "pts": pts, "new": new})
        return len(roads) - 1

    def heading_out(pts, at_end):
        a, b = (pts[-2], pts[-1]) if at_end else (pts[1], pts[0])
        return unit((b[0] - a[0], b[1] - a[1]))

    def is_lsd(name):
        return "Lake Shore" in name

    for city in ("chicago", "austin"):
        tf = F.tf(city)
        seam_f = side[city]
        for cls, lines in DATA[city]["roads"].items():
            for name, flat in lines:
                pts = [tf(x, y) for x, y in pairs(flat)]
                if city == "austin" and LF:
                    f = lambda p: min(seam_f(p) - SETBACK, LF.inland(p) - CITY_FROM)
                else:
                    f = lambda p: seam_f(p) - SETBACK
                for piece, cs, ce in clip_polyline(pts, f):
                    for seg, bs, be in clip_polyline(piece, lambda p: min(p[0] - F.box[0], F.box[2] - p[0], p[1] - F.box[1], F.box[3] - p[1])):
                        cut_s = cs and seg[0] == piece[0]
                        cut_e = ce and seg[-1] == piece[-1]
                        clipped = seg[0] != pts[0] or seg[-1] != pts[-1]
                        if clipped and length(seg) < MIN_SCRAP and not (cut_s or cut_e):
                            continue
                        idx = add_road(seg, cls, city, name)
                        for flag, at_end in ((cut_s, False), (cut_e, True)):
                            if not flag:
                                continue
                            p = seg[-1] if at_end else seg[0]
                            e = {"p": p, "h": heading_out(seg, at_end), "rank": RANK[cls], "city": city, "road": idx, "name": name, "lsd": is_lsd(name)}
                            if city == "austin" and LF and LF.inland(p) - CITY_FROM < seam_f(p) - SETBACK:
                                lake_ends.append(e)   # cut by the lakefront, not the seam
                            else:
                                ends.append(e)

    # 5. lakefront roads: Lake Shore Drive carried on, and a frontage street the Austin grid flows into
    lsd_idx = frontage_idx = None
    if LF:
        def austin_part(line, need):
            keep = [p for p in line if side["austin"](p) >= need and F.inbox(p)]
            return keep
        lsd_line = austin_part(LF.offset_line(LSD_AT), SETBACK)
        fr_line = austin_part(LF.offset_line(FRONTAGE_AT), SETBACK)
        if len(lsd_line) > 2:
            lsd_idx = add_road(lsd_line, "highway", "new", "DuSable Lake Shore Drive", new=True)
            ends.append({"p": lsd_line[0], "h": heading_out(lsd_line, False), "rank": 4, "city": "austin", "road": lsd_idx,
                         "name": "DuSable Lake Shore Drive", "lsd": True})
        if len(fr_line) > 2:
            frontage_idx = add_road(fr_line, "mid", "new", "Lakeview Avenue", new=True)
            ends.append({"p": fr_line[0], "h": heading_out(fr_line, False), "rank": 2, "city": "austin", "road": frontage_idx,
                         "name": "Lakeview Avenue", "lsd": False})
        # Austin streets cut by the lakefront flow into the frontage street; the big ones carry on to the Drive
        n_front = n_lsd = 0
        for e in lake_ends:
            if frontage_idx is None:
                break
            d, q, _ = nearest_on(roads[frontage_idx]["pts"], e["p"])
            if d < 80:
                add_road(bezier(e["p"], e["h"], q, unit((e["p"][0] - q[0], e["p"][1] - q[1])), n=6), CLASS_OF[max(1, e["rank"])], "stitch", e["name"], True)
                n_front += 1
                if e["rank"] >= 3 and lsd_idx is not None:
                    d2, q2, _ = nearest_on(roads[lsd_idx]["pts"], q)
                    if d2 < 140:
                        add_road([q, q2], "major", "stitch", e["name"], True)
                        n_lsd += 1
        stats["lakefront_streets_to_frontage"] = n_front
        stats["lakefront_streets_to_drive"] = n_lsd

    # 6. stitch across the seam: Lake Shore Drive first, then pair cut ends, big roads first
    used = set()
    lsd_c = [i for i, e in enumerate(ends) if e["lsd"] and e["city"] == "chicago" and e["rank"] >= 3]
    lsd_a = [i for i, e in enumerate(ends) if e["lsd"] and e["city"] == "austin"]
    if lsd_a:
        a = ends[lsd_a[0]]
        for i in lsd_c:
            c = ends[i]
            if math.dist(c["p"], a["p"]) < 900:
                add_road(bezier(c["p"], c["h"], a["p"], a["h"]), "highway", "stitch", "DuSable Lake Shore Drive", True)
                used.add(i)
        used.add(lsd_a[0])
    stats["lake_shore_drive_links"] = len([i for i in lsd_c if i in used])

    cands = []
    for i, c in enumerate(ends):
        if c["city"] != "chicago" or i in used:
            continue
        for j, a in enumerate(ends):
            if a["city"] != "austin" or j in used:
                continue
            D = math.dist(c["p"], a["p"])
            minr = min(c["rank"], a["rank"])
            if D > 120 + 55 * minr:
                continue
            if max(c["rank"], a["rank"]) == 4 and minr < 3:
                continue   # an expressway never runs into a side street
            v = unit((a["p"][0] - c["p"][0], a["p"][1] - c["p"][1]))
            fc = c["h"][0] * v[0] + c["h"][1] * v[1]
            fa = -(a["h"][0] * v[0] + a["h"][1] * v[1])
            if D > 30 and (fc < 0.25 or fa < 0.25):
                continue
            score = D * (1 + (1 - fc) + (1 - fa)) + 70 * abs(c["rank"] - a["rank"]) - 45 * minr
            cands.append((score, i, j))
    cands.sort()
    stitched = 0
    for score, i, j in cands:
        if i in used or j in used:
            continue
        c, a = ends[i], ends[j]
        cls = CLASS_OF[max(c["rank"], a["rank"])] if max(c["rank"], a["rank"]) > 0 else "minor"
        add_road(bezier(c["p"], c["h"], a["p"], a["h"]), cls, "stitch", c["name"] or a["name"], True)
        used.update((i, j))
        stitched += 1
    stats["streets_stitched_pairs"] = stitched

    # leftovers tee into the nearest road ahead of them (any city), so side streets flow on
    teed = dead = 0
    for i, e in enumerate(ends):
        if i in used:
            continue
        best = None
        for k, r in enumerate(roads):
            if k == e["road"] or r["cls"] == "ped" or (e["rank"] == 4 and r["cls"] not in ("major", "highway")):
                continue
            # quick reject by bounding box
            xs = [p[0] for p in r["pts"]]; ys = [p[1] for p in r["pts"]]
            if e["p"][0] < min(xs) - 160 or e["p"][0] > max(xs) + 160 or e["p"][1] < min(ys) - 160 or e["p"][1] > max(ys) + 160:
                continue
            d, q, _ = nearest_on(r["pts"], e["p"])
            if d < 1 or d > (400 if e["rank"] == 4 else 150):
                continue
            v = unit((q[0] - e["p"][0], q[1] - e["p"][1]))
            if e["h"][0] * v[0] + e["h"][1] * v[1] < 0.2:
                continue
            if best is None or d < best[0]:
                best = (d, q)
        if best:
            d, q = best
            add_road(bezier(e["p"], e["h"], q, unit((e["p"][0] - q[0], e["p"][1] - q[1])), n=8), CLASS_OF[max(1, e["rank"])], "stitch", e["name"], True)
            teed += 1
        else:
            dead += 1
    stats["streets_teed_in"] = teed
    stats["streets_left_dead_end"] = dead

    # 7. rail: keep each side; join Chicago's cut L ends with smooth curves
    l_ends = []
    for city in ("chicago", "austin"):
        tf = F.tf(city)
        for kind in ("L", "subway", "rail"):
            for flat in DATA[city]["rail"][kind]:
                pts = [tf(x, y) for x, y in pairs(flat)]
                f = (lambda p: min(side[city](p) - SETBACK, LF.inland(p) - CITY_FROM)) if (city == "austin" and LF) else (lambda p: side[city](p) - SETBACK)
                for seg, cs, ce in clip_polyline(pts, f):
                    seg2 = [p for p in seg if F.inbox(p)]
                    if len(seg2) < 2 or (length(seg2) < MIN_SCRAP and seg2 != pts):
                        continue
                    plan["rail"].append({"kind": kind, "city": city, "pts": r1(seg2)})
                    if kind == "L":
                        if cs and seg2[0] == seg[0]:
                            l_ends.append((seg2[0], heading_out(seg2, False)))
                        if ce and seg2[-1] == seg[-1]:
                            l_ends.append((seg2[-1], heading_out(seg2, True)))
    # pair cut L ends whose directions face each other (parallel tracks of one leg never pair up)
    cand = []
    for i, (p, hp) in enumerate(l_ends):
        for j, (q, hq) in enumerate(l_ends):
            if j <= i:
                continue
            D = math.dist(p, q)
            if D > 1500 or D < 1:
                continue
            v = unit((q[0] - p[0], q[1] - p[1]))
            fp = hp[0] * v[0] + hp[1] * v[1]
            fq = -(hq[0] * v[0] + hq[1] * v[1])
            if fp < 0.2 or fq < 0.2:
                continue
            cand.append((D * (1 + (1 - fp) + (1 - fq)), i, j))
    cand.sort()
    taken, links = set(), 0
    for _, i, j in cand:
        if i in taken or j in taken:
            continue
        (p, hp), (q, hq) = l_ends[i], l_ends[j]
        plan["rail"].append({"kind": "L", "city": "stitch", "name": "Seam Line",
                             "pts": r1(bezier(p, hp, q, hq, k=0.5 * math.dist(p, q), n=24))})
        taken.update((i, j))
        links += 1
    stats["L_links"] = links

    # 8. bridges: road pieces over water
    water_rings = [(r, min(p[0] for p in r), min(p[1] for p in r), max(p[0] for p in r), max(p[1] for p in r)) for r in [list(map(tuple, w)) for w in plan["water"]["outer"]]]
    island_rings = [list(map(tuple, w)) for w in plan["water"]["inner"]]

    def wet(p):
        for r, x0, y0, x1, y1 in water_rings:
            if x0 <= p[0] <= x1 and y0 <= p[1] <= y1 and point_in_ring(p, r):
                return not any(point_in_ring(p, i) for i in island_rings)
        return False

    for r in roads:
        if r["cls"] == "ped":
            continue
        pts = r["pts"]
        run = []
        for a, b in zip(pts, pts[1:]):
            # sample each segment so long spans are caught
            steps = max(1, int(math.dist(a, b) / 12))
            for s in range(steps):
                u0, u1 = s / steps, (s + 1) / steps
                p0 = (a[0] + (b[0] - a[0]) * u0, a[1] + (b[1] - a[1]) * u0)
                p1 = (a[0] + (b[0] - a[0]) * u1, a[1] + (b[1] - a[1]) * u1)
                if wet(((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)):
                    if not run:
                        run = [p0]
                    run.append(p1)
                elif run:
                    if length(run) > 8:
                        plan["bridges"].append({"cls": r["cls"], "name": r["name"], "pts": r1(run)})
                    run = []
        if run and length(run) > 8:
            plan["bridges"].append({"cls": r["cls"], "name": r["name"], "pts": r1(run)})
    stats["bridges"] = len(plan["bridges"])

    # 9. landmarks
    lost = []
    for city in ("chicago", "austin"):
        tf = F.tf(city)
        for name, x, y, outline in DATA[city]["landmarks"]:
            p = tf(x, y)
            if not F.inbox(p):
                continue
            ok = side[city](p) >= 0 and (city != "austin" or not LF or LF.inland(p) > 0)
            if ok:
                plan["landmarks"].append({"name": name, "city": city, "pos": r1([p])[0],
                                          "outline": r1([tf(a, b) for a, b in pairs(outline)]) if outline else []})
            else:
                lost.append(name)
    stats["landmarks_lost"] = lost

    plan["roads"] = [{"cls": r["cls"], "city": r["city"], "name": r["name"], "new": r["new"], "pts": r1(r["pts"])} for r in roads]
    stats["roads"] = len(roads)
    return plan


def main():
    L = json.load(open(sys.argv[1]))
    L = L.get("data", L)
    plan = integrate(L)
    out = pathlib.Path(sys.argv[2])
    out.write_text(json.dumps(plan, separators=(",", ":")))
    print(json.dumps(plan["stats"], indent=1))
    print("wrote", out, round(out.stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
