"""PIE drive tests through the simplified seam junctions (seam-junctions agent, 20 Oct night). Read-only for the level.

For every route in Saved/Roads/seam/drive_plan.json (Scripts/roads/seam_drive_plan.py) it teleports the Skyster car to
the route's start (ASkysterCar::TestTeleport), lets it settle, then drives the route through the junction on its lanes
(pure pursuit on traffic.json lane lines with curves round the corners, 25-35 mph, slowing for stop signs and rolling
through red lights slowly: coverage over compliance), and logs what a player would notice:
  done / timeout, time, max distance from the lane line, getting stuck, hits (a sudden deceleration with no brake, with
  what a forward trace names), the ground under the car (asphalt "Ground", bridge decks, or a raised block: a curb, a
  sidewalk or an island in the way), bumps (z jumps).
One chase-camera shot per route as it crosses the junction (HighResShot into a 10-slot PNG ring, sips -> JPG):
Saved/Roads/seam/drive/<tag>_<site>_<n>.jpg. The adapted parts (pure pursuit, junction curves, shots) come from
Saved/Playtest/pt2_austin/pt2.py (playtest-austin).
Run (editor lock held, kenny_playing.sh says no, SkyCityMashup loaded, PIE off):
  py Scripts/roads/junction_drive_ue.py [tag=after] [sites=a,b] [endpie=1]
Out: Saved/Roads/seam/drive/out_<tag>.json (written as it goes). PIE is stopped at the end.
"""
import builtins, json, math, os, subprocess, sys, time, traceback, unreal

import os


def _skycity_root():
    """Project folder: $SKYCITY_ROOT, else the folder above this script that holds SkyCity.uproject."""
    env = os.environ.get("SKYCITY_ROOT")
    if env:
        return env
    try:
        d = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        d = None
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "SkyCity.uproject")):
            return d
        d = os.path.dirname(d)
    import unreal  # running in the editor without __file__
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")


ROOT = _skycity_root()
OUTD = ROOT + "/Saved/Roads/seam/drive"
TMP = ROOT + "/Saved/Roads/seam/tmp"
os.makedirs(OUTD, exist_ok=True)
os.makedirs(TMP, exist_ok=True)
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
TAG = KV.get("tag", "after")
OUT = f"{OUTD}/out_{TAG}.json"
PLAN = json.load(open(ROOT + "/Saved/Roads/seam/drive_plan.json"))
TRAF = json.load(open(ROOT + "/" + PLAN.get("traffic", "Content/SkyCity/Data/traffic.json")))
LINKS = TRAF["links"]
UNITS = {int(k): v for k, v in TRAF["units"].items()}
GT = TRAF["group_time"]
ONLY = [s for s in KV.get("sites", "").split(",") if s]
JOBS = [(s["name"], s["c"], k, r) for s in PLAN["sites"] if not ONLY or s["name"] in ONLY for k, r in enumerate(s["routes"])]
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
if not ues.get_game_world():
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()
ZERO = {"test_throttle": 0.0, "test_brake": 0.0, "test_steer": 0.0, "test_pitch": 0.0, "test_roll": 0.0,
        "test_jump": False, "test_boost": False, "test_fly": False, "test_slide": False}
st = {"wait": 60, "started": False, "ji": 0, "phase": "tp", "pt": 0.0, "shotk": 0, "pending": [], "res": [], "cur": None,
      "endt": None, "wall0": time.time()}
_h = None


def ue(x, y):
    return (y * 100.0, x * 100.0)


def ue_yaw(h_plan_deg):
    return 90.0 - h_plan_deg


def wrap(a):
    while a > 180:
        a -= 360
    while a < -180:
        a += 360
    return a


def signal(unit, group, T):
    u = UNITS.get(unit)
    if not u:
        return 0
    N = max(1, u[0])
    t = (T / (GT * N) + u[1]) % 1.0
    s = t * N - group
    s -= N * math.floor(s / N)
    return 0 if s < 0.8 else 1 if s < 1.0 else 2


def link_pts_ue(l):
    o = l["o"]
    off = o[len(o) // 2]
    pts = l["p"]
    res = []
    for k in range(len(pts)):
        a = pts[max(0, k - 1)]
        b = pts[min(len(pts) - 1, k + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy) or 1.0
        tx, ty = dx / n, dy / n
        x, y = pts[k][0] + ty * off, pts[k][1] - tx * off
        res.append((y * 100.0, x * 100.0))
    return res


def junction_curve(a0, a1, b0, b1):
    dax, day = a1[0] - a0[0], a1[1] - a0[1]
    dbx, dby = b1[0] - b0[0], b1[1] - b0[1]
    la, lb = math.hypot(dax, day) or 1.0, math.hypot(dbx, dby) or 1.0
    dax, day, dbx, dby = dax / la, day / la, dbx / lb, dby / lb
    den = dax * dby - day * dbx
    gap = math.hypot(b0[0] - a1[0], b0[1] - a1[1])
    ang = abs(math.degrees(math.atan2(den, dax * dbx + day * dby)))
    if abs(den) < 0.17 or gap < 200 or ang < 20:
        return []
    t = ((b0[0] - a1[0]) * dby - (b0[1] - a1[1]) * dbx) / den
    u = ((b0[0] - a1[0]) * day - (b0[1] - a1[1]) * dax) / den
    if t <= 0 or u >= 0 or t > 4500 or -u > 4500:
        return []
    cx, cy = a1[0] + dax * t, a1[1] + day * t
    n = max(3, int((t - u) / 200))
    return [((1 - k / n) ** 2 * a1[0] + 2 * (1 - k / n) * (k / n) * cx + (k / n) ** 2 * b0[0],
             (1 - k / n) ** 2 * a1[1] + 2 * (1 - k / n) * (k / n) * cy + (k / n) ** 2 * b0[1]) for k in range(1, n)]


def build_path(route):
    path, prev = [], None
    for li in route:
        pts = link_pts_ue(LINKS[li])
        if prev is not None and len(prev) >= 2 and len(pts) >= 2:
            for q in junction_curve(prev[-2], prev[-1], pts[0], pts[1]):
                path.append((q[0], q[1], li))
        for q in pts:
            if path and math.hypot(q[0] - path[-1][0], q[1] - path[-1][1]) < 50:
                continue
            path.append((q[0], q[1], li))
        prev = pts
    return path


def ground(gw, p):
    loc = p.get_actor_location()
    try:
        r = unreal.SystemLibrary.line_trace_single(gw, loc + unreal.Vector(0, 0, 150), loc - unreal.Vector(0, 0, 600),
                                                   unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [p],
                                                   unreal.DrawDebugTrace.NONE, True)
        t = r.to_tuple() if r else None
        if t and t[0]:
            a = t[9]
            return (a.get_actor_label() if a and hasattr(a, "get_actor_label") else (a.get_name() if a else "")), t[5].z
    except Exception:
        pass
    return "", None


def ahead(gw, p):
    loc = p.get_actor_location()
    f = p.get_actor_forward_vector()
    try:
        r = unreal.SystemLibrary.line_trace_single(gw, loc + unreal.Vector(0, 0, 60), loc + unreal.Vector(0, 0, 60) + f * 500,
                                                   unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [p],
                                                   unreal.DrawDebugTrace.NONE, True)
        t = r.to_tuple() if r else None
        if t and t[0]:
            a = t[9]
            return a.get_actor_label() if a and hasattr(a, "get_actor_label") else (a.get_name() if a else "")
    except Exception:
        pass
    return ""


def shot(gw, cs, label):
    k = st["shotk"]
    st["shotk"] += 1
    tmp = f"{TMP}/d{k % 10}.png"
    out = f"{OUTD}/{TAG}_{cs['site']}_{cs['k']}_{label}.jpg"
    unreal.SystemLibrary.execute_console_command(gw, f"HighResShot 1 filename={tmp}")
    st["pending"].append({"tmp": tmp, "out": out, "t": time.time()})
    cs["shots"].append(os.path.basename(out))


def pump():
    now, keep = time.time(), []
    for pd in st["pending"]:
        f = None
        for c in (pd["tmp"], pd["tmp"] + ".png"):
            try:
                if os.path.getmtime(c) > pd["t"] - 0.05:
                    f = c
            except OSError:
                pass
        if f and now - os.path.getmtime(f) > 0.6:
            subprocess.Popen(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "62", "-Z", "1280", f, "--out", pd["out"]],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif now - pd["t"] < 8.0:
            keep.append(pd)
    st["pending"] = keep


def set_controls(p, c):
    for k, v in c.items():
        p.set_editor_property(k, v)


def write(done=False):
    json.dump({"tag": TAG, "done": done, "routes": st["res"], "wall_s": round(time.time() - st["wall0"], 1)},
              open(OUT, "w"), indent=1)


class Drive:
    def __init__(self, path):
        self.path, self.idx, self.u, self.lat = path, 0, 0.0, 0.0

    def step(self, p, T):
        loc = p.get_actor_location()
        P = self.path
        best = (1e18, self.idx, 0.0)
        for k in range(self.idx, min(self.idx + 30, len(P) - 1)):
            ax, ay, _ = P[k]
            bx, by, _ = P[k + 1]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy or 1.0
            u = max(0.0, min(1.0, ((loc.x - ax) * dx + (loc.y - ay) * dy) / L2))
            d = math.hypot(ax + dx * u - loc.x, ay + dy * u - loc.y)
            if d < best[0] - 1.0:
                best = (d, k, u)
        self.idx, self.u, self.lat = best[1], best[2], best[0] / 100.0
        if self.idx >= len(P) - 2 and self.u > 0.9:
            return None
        v = p.get_speed_mph() / 2.23694
        acc, h0, mt = 0.0, None, 0.0
        for k in range(self.idx, len(P) - 1):
            h = math.degrees(math.atan2(P[k + 1][1] - P[k][1], P[k + 1][0] - P[k][0]))
            h0 = h if h0 is None else h0
            mt = max(mt, abs(wrap(h - h0)))
            acc += math.hypot(P[k + 1][0] - P[k][0], P[k + 1][1] - P[k][1])
            if acc > 1500:
                break
        Ld = max(8.0 if mt < 45 else 5.0, v * 0.85) * 100.0
        seg0 = math.hypot(P[self.idx + 1][0] - P[self.idx][0], P[self.idx + 1][1] - P[self.idx][1])
        acc = -self.u * seg0
        tx, ty = P[-1][0], P[-1][1]
        for k in range(self.idx, len(P) - 1):
            seg = math.hypot(P[k + 1][0] - P[k][0], P[k + 1][1] - P[k][1])
            if acc + seg >= Ld:
                uu = (Ld - acc) / seg
                tx, ty = P[k][0] + (P[k + 1][0] - P[k][0]) * uu, P[k][1] + (P[k + 1][1] - P[k][1]) * uu
                break
            acc += seg
        err = wrap(math.degrees(math.atan2(ty - loc.y, tx - loc.x)) - p.get_actor_rotation().yaw)
        steer = max(-1.0, min(1.0, err / 22.0))
        cur = P[self.idx][2]
        l = LINKS[cur]
        vt = min(15.0, max(10.0, l["v"]))
        acc, h0, maxturn = 0.0, None, 0.0
        for k in range(self.idx, len(P) - 1):
            h = math.degrees(math.atan2(P[k + 1][1] - P[k][1], P[k + 1][0] - P[k][0]))
            h0 = h if h0 is None else h0
            maxturn = max(maxturn, abs(wrap(h - h0)))
            acc += math.hypot(P[k + 1][0] - P[k][0], P[k + 1][1] - P[k][1])
            if acc > 4000:
                break
        vt = min(vt, 5.5 if maxturn > 120 else 8.0 if maxturn > 60 else 11.0 if maxturn > 30 else 14.0 if maxturn > 15 else vt)
        if abs(err) > 60:
            vt = min(vt, 5.0)
        elif abs(err) > 25:
            vt = min(vt, 8.0)
        if l["c"] in (1, 2):
            dend = -self.u * seg0
            for k in range(self.idx, len(P) - 1):
                if P[k][2] != cur:
                    break
                dend += math.hypot(P[k + 1][0] - P[k][0], P[k + 1][1] - P[k][1])
            dstop = dend / 100.0 - 6.0
            if l["c"] == 1:
                s = signal(l["u"], l["g"], T)
                if (s == 2 or (s == 1 and v * v / 6.0 < dstop)) and -1.0 < dstop < 30:
                    vt = min(vt, 9.0)
            elif dstop < 18:
                vt = min(vt, 5.0)
        thr = max(0.0, min(1.0, (vt - v) * 0.35 + (0.25 if vt > v else 0.0)))
        brk = max(0.0, min(1.0, (v - vt) * 0.3)) if v > vt + 0.8 else 0.0
        return {"test_throttle": thr, "test_brake": brk, "test_steer": steer, "link": cur}


def tick(dt):
    try:
        if st["endt"] is not None:
            pump()
            if not st["pending"] or time.time() - st["endt"] > 10:
                unreal.unregister_slate_post_tick_callback(_h)
                write(True)
                if KV.get("endpie", "1") == "1" and ues.get_game_world():
                    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_end_play()
            return
        gw = ues.get_game_world()
        if not gw:
            return
        pc = unreal.GameplayStatics.get_player_controller(gw, 0)
        p = pc.get_controlled_pawn() if pc else None
        if p is None or not hasattr(p, "test_teleport"):
            return
        if st["wait"] > 0:
            st["wait"] -= 1
            return
        pump()
        if not st["started"]:
            p.set_editor_property("test_input", True)
            p.set_editor_property("test_set_level", 6)
            p.set_editor_property("test_full_tank", True)
            st["started"] = True
            return
        dt = min(dt, 0.1)
        if st["ji"] >= len(JOBS):
            set_controls(p, ZERO)
            p.set_editor_property("test_input", False)
            st["endt"] = time.time()
            write(False)
            return
        site, c, k, r = JOBS[st["ji"]]
        if st["cur"] is None:
            st["cur"] = {"site": site, "k": k, "move": r["move"], "names": sorted(set(n for n in r["names"] if n)), "m": r["m"],
                         "result": None, "t": 0.0, "max_lat": 0.0, "stuck": 0, "hits": [], "on_blocks": [], "bumps": 0,
                         "shots": [], "ground": {}, "min_mph": 99.0, "max_mph": 0.0}
            st["phase"], st["pt"] = "tp", 0.0
        cs = st["cur"]
        st["pt"] += dt
        T = unreal.GameplayStatics.get_time_seconds(gw)
        if st["phase"] == "tp":
            set_controls(p, ZERO)
            pc.set_view_target_with_blend(p, 0.0)
            X, Y = ue(r["start"][0], r["start"][1])
            p.test_teleport(unreal.Vector(X, Y, 120.0), ue_yaw(r["yaw_plan"]))
            st["drive"] = Drive(build_path(r["links"]))
            st["phase"], st["pt"], st["prev"] = "settle", 0.0, None
            return
        if st["phase"] == "settle":
            set_controls(p, ZERO)
            if st["pt"] > 1.2:
                st["phase"], st["pt"], st["shot_done"] = "drive", 0.0, False
            return
        # drive
        cmd = st["drive"].step(p, T)
        loc = p.get_actor_location()
        v = p.get_speed_mph() / 2.23694
        if cmd is None or st["pt"] > 45.0:
            cs["result"] = "done" if cmd is None else "timeout"
            cs["t"] = round(st["pt"], 1)
            cs["max_lat"] = round(cs["max_lat"], 2)
            cs["min_mph"] = round(cs["min_mph"], 1)
            cs["max_mph"] = round(cs["max_mph"], 1)
            st["res"].append(cs)
            write(False)
            st["cur"] = None
            st["ji"] += 1
            return
        set_controls(p, {k_: v_ for k_, v_ in cmd.items() if k_.startswith("test_")})
        cs["max_lat"] = max(cs["max_lat"], st["drive"].lat)
        if st["pt"] > 3.0:
            cs["min_mph"] = min(cs["min_mph"], v * 2.23694)
        cs["max_mph"] = max(cs["max_mph"], v * 2.23694)
        g, gz = ground(gw, p)
        key = "Ground" if g == "Ground" else ("bridge" if "Bridge" in g else ("block" if "R2Blocks" in g else (g[:24] or "none")))
        cs["ground"][key] = cs["ground"].get(key, 0) + 1
        if key == "block" and len(cs["on_blocks"]) < 6:
            cs["on_blocks"].append({"t": round(st["pt"], 1), "plan": [round(loc.y / 100, 1), round(loc.x / 100, 1)]})
        prev = st["prev"]
        if prev:
            dv = (v - prev[0]) / max(dt, 1e-3)
            if dv < -7.0 and cmd["test_brake"] < 0.1 and prev[0] > 4.0:
                cs["hits"].append({"t": round(st["pt"], 1), "plan": [round(loc.y / 100, 1), round(loc.x / 100, 1)],
                                   "mph": round(prev[0] * 2.23694, 1), "what": ahead(gw, p)})
            if abs(loc.z - prev[1]) > 25.0 and dt < 0.1:
                cs["bumps"] += 1
        st["prev"] = (v, loc.z)
        if v < 0.6 and cmd["test_throttle"] > 0.3:
            st["stuck_t"] = st.get("stuck_t", 0.0) + dt
            if st["stuck_t"] > 4.0:
                cs["stuck"] += 1
                st["stuck_t"] = 0.0
        else:
            st["stuck_t"] = 0.0
        if not st["shot_done"] and math.hypot(loc.y / 100 - c[0], loc.x / 100 - c[1]) < 18.0:
            shot(gw, cs, cs["move"])
            st["shot_done"] = True
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        st["error"] = traceback.format_exc()
        json.dump({"tag": TAG, "error": st["error"], "routes": st["res"]}, open(OUT, "w"), indent=1)


for _old in getattr(builtins, "_sc_ticks", []):
    try:
        unreal.unregister_slate_post_tick_callback(_old)
    except Exception:
        pass
_h = unreal.register_slate_post_tick_callback(tick)
builtins._sc_ticks = [_h]
write(False)
