"""Drive-test runs for the L (offline): along every street under the L in both directions, in the outermost travel lane
(the one next to the columns), and turning runs through the junctions under the L. Writes Saved/Rail/drive_runs.json for
Scripts/rail/l_drive_ue.py (in the editor). Plan metres (x east, y north).
Run: python3 -I Scripts/rail/l_drive_runs.py
"""
import json, math, pathlib, sys
import numpy as np
sys.argv = [sys.argv[0], "--lib"]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import l_layout as L  # noqa: E402

ROOT = L.ROOT
runs = []


def lane_offsets(p, t):
    """(left-most, right-most) travel-lane centres as lateral offsets from the L centreline (+ = left), read off the
    ground raster (the travel band round the centreline, 1.7 m in from its edges), or None off the roadway."""
    n = L.left(t)
    offs = np.arange(-16.0, 16.01, 0.25)
    g = L.ground([(p[0] + n[0] * o, p[1] + n[1] * o) for o in offs])
    road = (g == 2) | (g == 3) | (g == 7)
    c = len(offs) // 2
    if not road[c - 4:c + 5].any():
        return None
    i = c
    while i < len(offs) - 1 and road[i + 1]:
        i += 1
    j = c
    while j > 0 and road[j - 1]:
        j -= 1
    lft, rgt = offs[i], offs[j]
    su = L.street_under(p, t)
    if su is None:
        return None
    travel = sum(w for k, w, d in su[0]["elems"] if k not in ("parking", "gutter"))
    if lft - rgt < 5.0 or lft - rgt > travel + 1.5:          # a junction ring or a merge: no lane to keep to here
        return None
    return float(lft - 1.7), float(rgt + 1.7)


def street_runs(route, s0, s1, name, step=15.0):
    """Two runs along route between s0 and s1: in the right-hand outer lane each way."""
    fw, bw = [], []
    s = s0
    while s <= s1:
        p, t = L.P(route, s)
        lo = lane_offsets(p, t)
        n = L.left(t)
        if lo:
            lft, rgt = lo
            fw.append((p[0] + n[0] * rgt, p[1] + n[1] * rgt))      # going +s: right-hand lane = right side
            bw.append((p[0] + n[0] * lft, p[1] + n[1] * lft))      # going -s: left side of +s
        s += step
    if len(fw) >= 3:
        runs.append({"name": f"{name}_fw", "why": f"{route} s {s0:.0f}-{s1:.0f} in the outer lane next to the columns", "wps": [[round(a, 2), round(b, 2)] for a, b in fw], "v": 18.0})
        runs.append({"name": f"{name}_bw", "why": f"{route} s {s1:.0f}-{s0:.0f} in the outer lane next to the columns", "wps": [[round(a, 2), round(b, 2)] for a, b in bw[::-1]], "v": 18.0})


R = L.ROUTES
# the streets under the L (s ranges from the street analysis; the Seam Line arc runs over blocks)
street_runs("LOOP", 2.0, 740.0, "wabash_n")          # Wabash, Jackson -> Lake
street_runs("LOOP", 760.0, 880.0, "lake")            # Lake St, Wabash -> State
street_runs("LOOP", 1700.0, 2170.0, "wells")         # Wells, Madison -> Van Buren
street_runs("LOOP", 2185.0, 2790.0, "vanburen")      # Van Buren, Wells -> Wabash
street_runs("LOOP", 2810.0, R["LOOP"]["len"] - 2.0, "wabash_vb")   # Wabash, Van Buren -> Jackson
street_runs("SOUTH", 10.0, R["SOUTH"]["len"] - 5.0, "south")       # Wabash, Van Buren -> 9th St


def turn(name, J, a_dir, b_dir, rad=11.0, keep=2.0):
    """A turn through junction J: in along a_dir (heading), out along b_dir, right-hand lanes, arc of radius rad."""
    a, b = L.unit(a_dir), L.unit(b_dir)
    ra, rb = (a[1], -a[0]), (b[1], -b[0])                 # right of each heading
    pin = (J[0] - a[0] * 45 + ra[0] * keep, J[1] - a[1] * 45 + ra[1] * keep)
    pout = (J[0] + b[0] * 45 + rb[0] * keep, J[1] + b[1] * 45 + rb[1] * keep)
    cross = a[0] * b[1] - a[1] * b[0]
    pts = [pin]
    # entry and exit of the turn, then a quadratic curve through the corner
    e0 = (J[0] - a[0] * rad + ra[0] * keep, J[1] - a[1] * rad + ra[1] * keep)
    e1 = (J[0] + b[0] * rad + rb[0] * keep, J[1] + b[1] * rad + rb[1] * keep)
    corner = (J[0] + ra[0] * keep + rb[0] * keep, J[1] + ra[1] * keep + rb[1] * keep)
    for k in range(0, 9):
        u = k / 8
        pts.append(((1 - u) ** 2 * e0[0] + 2 * (1 - u) * u * corner[0] + u * u * e1[0], (1 - u) ** 2 * e0[1] + 2 * (1 - u) * u * corner[1] + u * u * e1[1]))
    pts.append(pout)
    runs.append({"name": name, "why": ("left" if cross > 0 else "right") + " turn under the L", "wps": [[round(x, 2), round(y, 2)] for x, y in pts], "v": 10.0, "reach": 5.0})


def junction_on(route, street):
    s = L.street_crossing_s(route, street)
    if s is None:
        return None
    p, t = L.P(route, s)
    best = None
    for J in L.RN["junctions"]:
        d = L.dist(J["c"], p)
        if d < 25 and (best is None or d < best[0]):
            best = (d, J["c"])
    return (best[1] if best else p), t, s


TURNS = [("LOOP", "East Madison Street"), ("LOOP", "East Adams Street"), ("LOOP", "South State Street"), ("LOOP", "South Clark Street"),
         ("LOOP", "West Jackson Boulevard"), ("SOUTH", "East Harrison Street"), ("SOUTH", "East Balbo Avenue"), ("SOUTH", "East 8th Street")]
for route, street in TURNS:
    j = junction_on(route, street)
    if not j:
        print("no junction", route, street)
        continue
    J, t, s = j
    # cross street direction: from roadnet edge geometry near J
    best = None
    for e in L.RN["edges"]:
        if e["name"] != street:
            continue
        d, q, ss, te = L.closest_on_polyline(e["geom"], J)
        if d < 30 and (best is None or d < best[0]):
            best = (d, te)
    if not best:
        continue
    c = best[1]
    if abs(c[0] * t[0] + c[1] * t[1]) > 0.7:
        continue
    key = street.split()[1].lower()
    turn(f"turn_{key}_r", J, c, t)            # in along the cross street, right onto the L street (+s)
    turn(f"turn_{key}_l", J, (-c[0], -c[1]), t)  # in along the cross street the other way, left onto the L street
    turn(f"turn_{key}_r2", J, (-t[0], -t[1]), c)  # along the L street (-s), turn onto the cross street
# the deck: up on the L (the car is put on the deck slab) along Wabash and Van Buren
for nm, route, s0, s1 in (("deck_wabash", "LOOP", 230.0, 560.0), ("deck_vanburen", "LOOP", 2420.0, 2520.0), ("deck_south", "SOUTH", 300.0, 600.0)):
    w = []
    s = s0
    while s <= s1:
        p, t = L.P(route, s)
        n = L.left(t)
        w.append([round(p[0] - n[0] * 1.9, 2), round(p[1] - n[1] * 1.9, 2)])     # right-hand track
        s += 15.0
    runs.append({"name": nm, "why": "driving the deck (on the collision slab, right-hand track)", "wps": w, "z": 7.3, "v": 22.0})

# ---------------------------------------------------------------- tours: one PIE session each (the car spawns at the tour's
# start through StartPIE's start transform: SkysterCar keeps its own physics position, so it can't be teleported from Python)
def uturn(end, h, side=+1, R=8.5, v=6.0, n=7):
    """Semicircle from `end` heading h, turning to the left (side +1) into the opposite lane."""
    h = L.unit(h)
    lf = L.left(h)
    c = (end[0] + lf[0] * R * side, end[1] + lf[1] * R * side)
    pts = []
    for k in range(1, n + 1):
        a = math.pi * k / n
        # start at angle pointing from c to end, sweep 180 deg
        v0 = (end[0] - c[0], end[1] - c[1])
        ca, sa = math.cos(a * side), math.sin(a * side)
        pts.append([round(c[0] + v0[0] * ca - v0[1] * sa, 2), round(c[1] + v0[0] * sa + v0[1] * ca, 2), v])
    return pts


def lane_path(route, s0, s1, side, step=15.0, v=18.0):
    """Waypoints along the outer travel lane: side +1 = right-hand lane going s0 -> s1 (s0 < s1 or s0 > s1)."""
    out = []
    sgn = 1 if s1 > s0 else -1
    s = s0
    while (s - s1) * sgn <= 0:
        p, t = L.P(route, s)
        lo = lane_offsets(p, t)
        if lo:
            off = lo[1] if sgn > 0 else lo[0]
            n = L.left(t)
            out.append([round(p[0] + n[0] * off, 2), round(p[1] + n[1] * off, 2), v])
        s += step * sgn
    return out


def heading(pts):
    a, b = pts[-2], pts[-1]
    return (b[0] - a[0], b[1] - a[1])




def join(*parts):
    """Chain lane paths; where consecutive parts meet at an angle (a corner), a quadratic turn through the junction from
    the end of one lane to the start of the next (control point where the two lane lines cross), at 8 m/s."""
    out = list(parts[0])
    for B in parts[1:]:
        if not B:
            continue
        A = out
        p0, p2 = A[-1][:2], B[0][:2]
        dA = L.unit((A[-1][0] - A[-2][0], A[-1][1] - A[-2][1]))
        dB = L.unit((B[1][0] - B[0][0], B[1][1] - B[0][1]))
        cross = dA[0] * dB[1] - dA[1] * dB[0]
        if abs(cross) > 0.3:
            # p0 + u dA = p2 - v dB
            w = (p2[0] - p0[0], p2[1] - p0[1])
            u = (w[0] * dB[1] - w[1] * dB[0]) / cross
            c = (p0[0] + dA[0] * u, p0[1] + dA[1] * u)
            for k in range(1, 8):
                q = k / 8
                out.append([round((1 - q) ** 2 * p0[0] + 2 * (1 - q) * q * c[0] + q * q * p2[0], 2),
                            round((1 - q) ** 2 * p0[1] + 2 * (1 - q) * q * c[1] + q * q * p2[1], 2), 8.0])
        out += list(B)
    return out


tours = []
LL = R["LOOP"]["len"]
SL = R["SOUTH"]["len"]
# one PIE session per tour, no U-turns (a U-turn on a 9 m street climbs the curb): each street under the L is driven both
# ways in its right-hand outer lane, chained round the L's corners (the turns at Lake/Wabash and Wells/Van Buren)
t1 = join(lane_path("LOOP", 880.0, 745.0, +1), lane_path("LOOP", 735.0, 2.0, +1) + lane_path("LOOP", LL - 2.0, LL - 150.0, +1) + lane_path("SOUTH", 40.0, SL - 10.0, +1))
tours.append({"name": "tour_s", "why": "Lake St eastbound under the NE curve, right onto Wabash southbound under the Loop L, through Tower 12, on down Wabash under the South Side line to the terminal at 9th St", "wps": t1, "secs": 300})
t2 = join(lane_path("SOUTH", SL - 10.0, 40.0, +1) + lane_path("LOOP", LL - 150.0, LL - 2.0, +1) + lane_path("LOOP", 2.0, 735.0, +1), lane_path("LOOP", 745.0, 880.0, +1))
tours.append({"name": "tour_n", "why": "Wabash northbound from 9th St under the South Side line, Tower 12, the Loop L to Lake, left onto Lake westbound to State", "wps": t2, "secs": 300})
t3 = join(lane_path("LOOP", 2790.0, 2195.0, +1), lane_path("LOOP", 2160.0, 1705.0, +1))
tours.append({"name": "tour_w", "why": "Van Buren westbound from Wabash, right onto Wells northbound (under the SW curve) to Madison", "wps": t3, "secs": 240})
t4 = join(lane_path("LOOP", 1705.0, 2160.0, +1), lane_path("LOOP", 2195.0, 2790.0, +1))
tours.append({"name": "tour_e", "why": "Wells southbound from Madison, left onto Van Buren eastbound to Wabash", "wps": t4, "secs": 240})
# the deck (spawned on the deck slab): Wabash, right-hand track, through Washington/Wabash station
dk = []
s = 230.0
while s <= 600.0:
    p, t = L.P("LOOP", s)
    n = L.left(t)
    dk.append([round(p[0] - n[0] * 1.9, 2), round(p[1] - n[1] * 1.9, 2), 22.0])
    s += 15.0
tours.append({"name": "tour_deck", "why": "driving the deck on the collision slab (right-hand track) through a station", "wps": dk, "z": 7.3, "secs": 60})
for tr in tours:
    a, b = tr["wps"][0], tr["wps"][1]
    tr["start"] = {"plan": a[:2], "yaw_ue": round(math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])), 2), "z_m": tr.get("z", 0.0) + 0.8}
runs = tours + [r for r in runs if r["name"].startswith("turn")]
json.dump({"frame": "plan metres", "runs": runs}, open(ROOT / "Saved/Rail/drive_runs.json", "w"), indent=0)
print(len(runs), "runs:", [r["name"] for r in runs])
print("total km", round(sum(sum(L.dist(a, b) for a, b in zip(r["wps"], r["wps"][1:])) for r in runs) / 1000, 2))
