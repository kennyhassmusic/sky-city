"""Turn a saved mashup layout into one integrated city plan, ready for Unreal.

Applies the layout (Austin moved/rotated, each city kept on its side of the seam), then makes the join
make sense:
  - a diagonal Seam Boulevard runs along the seam; every street the seam cut is extended into it,
  - water on both sides is joined with a tapered channel where a river meets the seam on both sides,
  - cut ends of Chicago's elevated L are reconnected by a new elevated line along the boulevard,
  - everything is clipped to the play area plus a margin, and leftover scraps are dropped.

Usage: python3 -I Scripts/mashup/integrate_layout.py <layout.json> <plan_out.json>
Units: metres, x east, y north, origin = Chicago State St bridge (the layout's frame).
"""
import json, math, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
DATA = json.load(open(HERE / "mashup_data.json"))["cities"]
BOULEVARD_W = 32.0     # carriageway + medians
TRIM = 20.0            # streets stop this far from the seam centreline, then extend into it
MARGIN = 300.0         # keep this much city around the play area
MIN_SCRAP = 35.0       # drop clipped street pieces shorter than this (unless they reach the boulevard)
JOIN_GAP = 260.0       # river mouths this close along the seam get joined
JOIN_DEPTH = 45.0      # how far the tapered join reaches into each side


def load_layout(path):
    L = json.load(open(path))
    return L.get("data", L)


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
        self.off = (L["austin"]["x"], L["austin"]["y"])
        pa = L["playArea"]
        h = pa["sizeM"] / 2 + MARGIN
        self.box = (pa["x"] - h, pa["y"] - h, pa["x"] + h, pa["y"] + h)
        self.play = (pa["x"] - pa["sizeM"] / 2, pa["y"] - pa["sizeM"] / 2, pa["x"] + pa["sizeM"] / 2, pa["y"] + pa["sizeM"] / 2)

    def tf(self, city):
        if city == "chicago":
            return lambda x, y: (x, y)
        return lambda x, y: (self.rc * x - self.rs * y + self.off[0], self.rs * x + self.rc * y + self.off[1])

    def sd(self, p):   # signed distance from the seam centreline (+ = left of the seam direction)
        return (p[0] - self.S[0]) * self.n[0] + (p[1] - self.S[1]) * self.n[1]

    def t(self, p):    # position along the seam
        return (p[0] - self.S[0]) * self.d[0] + (p[1] - self.S[1]) * self.d[1]

    def at(self, t, s=0.0):
        return (self.S[0] + self.d[0] * t + self.n[0] * s, self.S[1] + self.d[1] * t + self.n[1] * s)


def pairs(flat):
    return [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]


def length(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


# ---- clipping helpers -------------------------------------------------------------------------------
def clip_polyline_halfplane(pts, f):
    """Keep the parts of a polyline where f(p) >= 0. Returns [(points, start_cut, end_cut)]."""
    out, cur, cut_start = [], [], False
    for i, p in enumerate(pts):
        inside = f(p) >= 0
        if i == 0:
            if inside:
                cur = [p]
            continue
        q = pts[i - 1]
        fin = f(q) >= 0
        if inside and fin:
            cur.append(p)
        elif inside and not fin:      # entering: start a new piece at the boundary
            u = f(q) / (f(q) - f(p))
            x = (q[0] + (p[0] - q[0]) * u, q[1] + (p[1] - q[1]) * u)
            cur, cut_start = [x, p], True
        elif fin and not inside:      # leaving: close the piece at the boundary
            u = f(q) / (f(q) - f(p))
            x = (q[0] + (p[0] - q[0]) * u, q[1] + (p[1] - q[1]) * u)
            cur.append(x)
            out.append((cur, cut_start, True))
            cur, cut_start = [], False
    if len(cur) > 1:
        out.append((cur, cut_start, False))
    return out


def clip_polyline_box(pts, box):
    pieces = [(pts, False, False)]
    x0, y0, x1, y1 = box
    for f in (lambda p: p[0] - x0, lambda p: x1 - p[0], lambda p: p[1] - y0, lambda p: y1 - p[1]):
        nxt = []
        for seg, cs, ce in pieces:
            for s2, c2s, c2e in clip_polyline_halfplane(seg, f):
                # cuts made by the box are not seam cuts: keep only the seam flags that survive at the same ends
                nxt.append((s2, cs and not c2s and s2[0] == seg[0], ce and not c2e and s2[-1] == seg[-1]))
        pieces = nxt
    return pieces


def clip_ring(ring, planes):
    """Sutherland-Hodgman against half-planes f(p) >= 0."""
    pts = ring
    for f in planes:
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


def box_planes(box):
    x0, y0, x1, y1 = box
    return [lambda p: p[0] - x0, lambda p: x1 - p[0], lambda p: p[1] - y0, lambda p: y1 - p[1]]


def r1(pts):
    return [[round(x, 1), round(y, 1)] for x, y in pts]


# ---- the integration ---------------------------------------------------------------------------------
def integrate(L):
    F = Frame(L)
    plan = {"frame": {"origin": "Chicago State St bridge", "units": "m, x east, y north"},
            "layout": L, "playArea": F.play, "bounds": F.box,
            "roads": [], "rail": [], "water": {"outer": [], "inner": []}, "parks": [], "landmarks": [],
            "seam": {"start": None, "end": None, "width": BOULEVARD_W}, "stats": {}}
    stats = plan["stats"]

    # Seam Boulevard: the seam line clipped to the bounds
    far = 20000
    blvd = clip_polyline_box([F.at(-far), F.at(far)], F.box)
    if blvd:
        a, b = blvd[0][0][0], blvd[0][0][-1]
        plan["seam"]["start"], plan["seam"]["end"] = r1([a])[0], r1([b])[0]
        plan["roads"].append({"cls": "boulevard", "name": "Seam Boulevard", "city": "new", "pts": r1([a, b])})

    def extend_to_seam(piece, at_end):
        """Extend a cut street end along its own heading until it meets the boulevard centreline."""
        pts = piece if at_end else piece[::-1]
        q, p = pts[-2], pts[-1]
        dx, dy = p[0] - q[0], p[1] - q[1]
        L_ = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L_, dy / L_
        s = F.sd(p)
        dn = ux * F.n[0] + uy * F.n[1]
        if abs(dn) > 0.35:                       # heading crosses the seam: run straight into it
            k = -s / dn
            end = (p[0] + ux * k, p[1] + uy * k)
        else:                                    # nearly parallel: turn and meet it square
            end = (p[0] - F.n[0] * s, p[1] - F.n[1] * s)
        return end

    # streets
    roads_kept = connectors = 0
    for city in ("chicago", "austin"):
        tf, sg = F.tf(city), F.sgn[city]
        keep = lambda p, sg=sg: sg * F.sd(p) - TRIM
        for cls, lines in DATA[city]["roads"].items():
            for name, flat in lines:
                pts = [tf(x, y) for x, y in pairs(flat)]
                for piece, cs, ce in clip_polyline_halfplane(pts, keep):
                    for seg, bs, be in clip_polyline_box(piece, F.box):
                        cut_s = cs and seg[0] == piece[0]
                        cut_e = ce and seg[-1] == piece[-1]
                        if cut_e:
                            seg = seg + [extend_to_seam(seg, True)]; connectors += 1
                        if cut_s:
                            seg = [extend_to_seam(seg, False)] + seg; connectors += 1
                        clipped = seg[0] != pts[0] or seg[-1] != pts[-1]
                        if clipped and length(seg) < MIN_SCRAP and not (cut_s or cut_e):
                            continue   # a sliver left by the map edge (OSM's own short pieces are kept)
                        plan["roads"].append({"cls": cls, "name": name, "city": city, "pts": r1(seg)})
                        roads_kept += 1
    stats["roads"] = roads_kept
    stats["streets_joined_to_boulevard"] = connectors

    # water and parks: each side clipped at the seam centreline (the boulevard bridges the water)
    touch = {"chicago": [], "austin": []}
    for city in ("chicago", "austin"):
        tf, sg = F.tf(city), F.sgn[city]
        side = lambda p, sg=sg: sg * F.sd(p)
        planes = [side] + box_planes(F.box)
        for role in ("outer", "inner"):
            for flat in DATA[city]["water"][role]:
                ring = clip_ring([tf(x, y) for x, y in pairs(flat)], planes)
                if len(ring) < 3:
                    continue
                plan["water"][role].append(r1(ring))
                if role == "outer":   # record where this water meets the seam
                    for p, q in zip(ring, ring[1:] + ring[:1]):
                        if abs(F.sd(p)) < 0.05 and abs(F.sd(q)) < 0.05:
                            touch[city].append(sorted((F.t(p), F.t(q))))
        for flat in DATA[city]["parks"]:
            ring = clip_ring([tf(x, y) for x, y in pairs(flat)], planes)
            if len(ring) >= 3:
                plan["parks"].append(r1(ring))

    def merge(iv):
        iv = sorted(i for i in iv if i[1] - i[0] > 3)
        out = []
        for a, b in iv:
            if out and a <= out[-1][1] + 5:
                out[-1][1] = max(out[-1][1], b)
            else:
                out.append([a, b])
        return out

    ch, au = merge(touch["chicago"]), merge(touch["austin"])
    joins = []
    for a1, a2 in au:
        best = None
        for c1, c2 in ch:
            gap = max(0.0, max(a1, c1) - min(a2, c2))
            wa, wc = a2 - a1, c2 - c1
            similar = max(wa, wc) <= 4 * min(wa, wc) and max(wa, wc) < 600   # river to river, not creek to lake
            if similar and gap <= JOIN_GAP and (best is None or gap < best[0]):
                best = (gap, c1, c2)
        if best:
            _, c1, c2 = best
            sa, sc = F.sgn["austin"] * JOIN_DEPTH, F.sgn["chicago"] * JOIN_DEPTH
            # taper from the Austin mouth to the Chicago mouth, spanning both where they meet at the seam
            lo, hi = min(a1, c1), max(a2, c2)
            quad = [F.at(a1, sa), F.at(a2, sa), F.at(hi, 0), F.at(c2, sc), F.at(c1, sc), F.at(lo, 0)]
            ring = clip_ring(quad, box_planes(F.box))
            if len(ring) >= 3:
                plan["water"]["outer"].append(r1(ring))
                joins.append({"austin": [round(a1), round(a2)], "chicago": [round(c1), round(c2)]})
    stats["water_joins"] = joins
    stats["river_mouths_at_seam"] = {"chicago": [[round(a), round(b)] for a, b in ch], "austin": [[round(a), round(b)] for a, b in au]}

    # rail: keep each side's lines; reconnect cut L ends along the boulevard
    l_ends = []
    for city in ("chicago", "austin"):
        tf, sg = F.tf(city), F.sgn[city]
        keep = lambda p, sg=sg: sg * F.sd(p) - TRIM
        for kind in ("L", "subway", "rail"):
            for flat in DATA[city]["rail"][kind]:
                pts = [tf(x, y) for x, y in pairs(flat)]
                for piece, cs, ce in clip_polyline_halfplane(pts, keep):
                    for seg, _, _ in clip_polyline_box(piece, F.box):
                        if length(seg) < MIN_SCRAP and (seg[0] != pts[0] or seg[-1] != pts[-1]):
                            continue
                        plan["rail"].append({"kind": kind, "city": city, "pts": r1(seg)})
                        if kind == "L":
                            if cs and seg[0] == piece[0]:
                                l_ends.append(seg[0])
                            if ce and seg[-1] == piece[-1]:
                                l_ends.append(seg[-1])
    # pair the cut L ends in order along the seam and join each pair with an elevated run over the boulevard
    l_ends.sort(key=F.t)
    seam_lines = 0
    for p, q in zip(l_ends[0::2], l_ends[1::2]):
        if abs(F.t(q) - F.t(p)) > 2500:
            continue
        pm, qm = F.at(F.t(p), 0), F.at(F.t(q), 0)
        plan["rail"].append({"kind": "L", "city": "new", "name": "Seam Line", "pts": r1([p, pm, qm, q])})
        seam_lines += 1
    stats["L_cut_ends"] = len(l_ends)
    stats["seam_L_links"] = seam_lines

    # landmarks: keep each where its own city survives; flag the ones the seam removed
    lost = []
    for city in ("chicago", "austin"):
        tf, sg = F.tf(city), F.sgn[city]
        for name, x, y, outline in DATA[city]["landmarks"]:
            p = tf(x, y)
            entry = {"name": name, "city": city, "pos": r1([p])[0],
                     "outline": r1([tf(a, b) for a, b in pairs(outline)]) if outline else []}
            inbox = F.box[0] <= p[0] <= F.box[2] and F.box[1] <= p[1] <= F.box[3]
            if sg * F.sd(p) >= 0 and inbox:
                plan["landmarks"].append(entry)
            elif inbox:
                lost.append(name)
    stats["landmarks_cut_by_seam"] = lost
    return plan


def main():
    L = load_layout(sys.argv[1])
    plan = integrate(L)
    out = pathlib.Path(sys.argv[2])
    out.write_text(json.dumps(plan, separators=(",", ":")))
    print(json.dumps(plan["stats"], indent=1))
    print("wrote", out, round(out.stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
