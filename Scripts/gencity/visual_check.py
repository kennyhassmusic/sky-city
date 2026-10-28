"""Fixed-camera golden-image check for the generated-city drive levels (Lane V, 2026-10-28).

Runs after every Unreal import, offline (plain Python 3 + Pillow + numpy, `python3 -I`), on a capture set written by
visual_capture_ue.py (one PNG per camera in visual_cams.json, capture.json, level_dump.json). It fails the run
before Kenny looks, so he only reviews the contact sheet of a run that passed.

  check    compare a run with the approved goldens; rule checks on the level dump; report.html + report.json
  approve  promote a run to goldens once Kenny OKs it (who/when recorded; the old goldens move to history/)
  rules    rule checks only, on any level dump (e.g. lane P's Saved/GenCity/level_dump_GenCity_Seed7.json)

  python3 -I Scripts/gencity/visual_check.py check --run <run dir> --expect 'beach_*' --expect 'tag:shore'
  python3 -I Scripts/gencity/visual_check.py check --run <run dir> --expect none
  python3 -I Scripts/gencity/visual_check.py approve --run <run dir> --by Kenny
  python3 -I Scripts/gencity/visual_check.py rules --dump <level_dump.json> --side <bt>/Saved/CityGen --seed 7

Per camera (pictures):
  * a structural score (1 - SSIM on luminance, at work_width) and the fraction of pixels whose colour moved more
    than pix_delta (after a 3x3 blur); "changed" when either is over the camera's tolerance (spec thresholds, the
    camera's own ssim_tol/frac_tol, raised to noise_mult x the noise floor measured when the goldens were approved);
  * an import must say what it meant to change: --expect <glob on camera name> | tag:<tag> | asset:<name> | none.
    Expected and unchanged -> FAIL (a no-op import, e.g. the beach sand that never reached Unreal);
    not expected and changed -> FAIL (something moved that shouldn't); a blank/black or missing frame -> FAIL;
    an --expect that matches no camera -> FAIL (typo guard). A camera's roi [x0, y0, x1, y1] (fractions) narrows
    the expected-change test to that part of the frame (e.g. the sand in beach_eye).
Per level (data, not pixels): the spec's rules on the level dump: vegetation on hard surfaces (road, walk, curb,
beach car-park pads; tree pits allowed) must be 0, per-feature counts from the v10 checklist must not be 0, materials
on the road tiles / shore terrain, no tracked count falling by more than half against the golden dump.

Exit: 0 PASS, 1 FAIL, 2 usage/input error, 3 NEEDS_APPROVAL (no goldens yet for some cameras; nothing failed).
"""
import argparse
import datetime
import fnmatch
import getpass
import hashlib
import html
import json
import math
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "visual_cams.json")
WORK = "/Volumes/Sound Libraries/SkyCity Work"
GOLDENS = os.path.join(WORK, "AssetBuilds", "visual_goldens")
EXIT = {"PASS": 0, "FAIL": 1, "ERROR": 2, "NEEDS_APPROVAL": 3}


# ---------------------------------------------------------------------------------------------------------- images
def load_img(path, width):
    im = Image.open(path).convert("RGB")
    if width and im.width != width:
        im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
    return np.asarray(im, dtype=np.float32) / 255.0


def luma(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def box(a, r):
    """Mean over a (2r+1)^2 window (edges clamped), via an integral image."""
    p = np.pad(a, r, mode="edge")
    c = np.cumsum(np.cumsum(p, 0), 1)
    c = np.pad(c, ((1, 0), (1, 0)))
    k = 2 * r + 1
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return s / float(k * k)


def ssim(x, y, r=3):
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    mx, my = box(x, r), box(y, r)
    vx = box(x * x, r) - mx * mx
    vy = box(y * y, r) - my * my
    cxy = box(x * y, r) - mx * my
    m = ((2 * mx * my + c1) * (2 * cxy + c2)) / ((mx * mx + my * my + c1) * (vx + vy + c2))
    return float(m.mean()), m


def crop(a, roi):
    if not roi:
        return a
    h, w = a.shape[:2]
    x0, y0, x1, y1 = roi
    return a[int(y0 * h):max(int(y0 * h) + 1, int(y1 * h)), int(x0 * w):max(int(x0 * w) + 1, int(x1 * w))]


def cell_means(a, gx=16, gy=9):
    h, w = a.shape[:2]
    ys = np.linspace(0, h, min(gy, h) + 1).astype(int)
    xs = np.linspace(0, w, min(gx, w) + 1).astype(int)
    return np.array([[a[ys[j]:ys[j + 1], xs[i]:xs[i + 1]].reshape(-1, 3).mean(0) for i in range(len(xs) - 1)]
                     for j in range(len(ys) - 1)])


def metrics(a, b, pix_delta, roi=None):
    """{dssim, frac, dcolor} of b against a (same size float RGB), optionally inside roi. dssim: structure (1-SSIM
    on luminance); frac: share of pixels whose colour moved > pix_delta; dcolor: the largest shift of a cell's mean
    colour on a 16x9 grid (a tone or tint change, e.g. grey sand turned warm beige, that SSIM barely sees)."""
    a, b = crop(a, roi), crop(b, roi)
    s, _ = ssim(luma(a), luma(b))
    d = np.abs(a - b).max(axis=2)
    d = box(d, 1)
    dc = float(np.abs(cell_means(a) - cell_means(b)).max())
    return {"dssim": round(1.0 - s, 5), "frac": round(float((d > pix_delta).mean()), 5), "dcolor": round(dc, 5)}


def is_changed(m, tol):
    return m["dssim"] > tol["dssim"] or m["frac"] > tol["frac"] or m.get("dcolor", 0) > tol["dcolor"]


def blank(a, th):
    l = luma(a)
    return float(l.mean()) < th["blank_mean"] or float(l.std()) < th["blank_std"]


def diff_image(a, b, out):
    """The new frame in grey with the difference painted red (x4)."""
    g = luma(b)[..., None].repeat(3, 2) * 0.6
    d = np.clip(np.abs(a - b).max(axis=2) * 4.0, 0, 1)
    g[..., 0] = np.clip(g[..., 0] + d, 0, 1)
    g[..., 1] = g[..., 1] * (1 - d)
    g[..., 2] = g[..., 2] * (1 - d)
    Image.fromarray((g * 255).astype(np.uint8)).save(out, quality=85)


def thumb(src, out, width):
    im = Image.open(src).convert("RGB")
    im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
    im.save(out, quality=85)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------------------- vegetation on hard ground
VEG_WORDS = ("VEG_", "CROP_", "TREE", "Tree", "hedge", "Hedge", "SHRUB", "Shrub", "GRASS", "Grass", "FLOWER", "Weed",
             "WEED", "LeafLitter")
NOT_VEG = ("TreePit", "TreeGrate", "KIT_SS_TreeL", "KIT_SS_TreeS")
CELL = 8.0
PIT_R = 1.2


def is_veg(key):
    """Same words as building-types Scripts/city/veg_clear.is_veg (the importer's filter)."""
    if any(w in key for w in NOT_VEG):
        return False
    return any(w in key for w in VEG_WORDS)


class HardSurface(object):
    """Road surface + walk/curb top faces + beach car-park pads, plan metres; tree pits allowed. Mirrors
    building-types veg_clear.HardSurface (+ the shoreline pads its filter_shore_scatter adds), so the check measures
    what the importer's filter is meant to remove, in the level."""

    def __init__(self, tris, pits=(), pads=()):
        self.grid = {}
        for a, b, c in tris:
            x0, x1 = min(a[0], b[0], c[0]), max(a[0], b[0], c[0])
            y0, y1 = min(a[1], b[1], c[1]), max(a[1], b[1], c[1])
            t = ((a[0], a[1]), (b[0], b[1]), (c[0], c[1]))
            for i in range(int(math.floor(x0 / CELL)), int(math.floor(x1 / CELL)) + 1):
                for j in range(int(math.floor(y0 / CELL)), int(math.floor(y1 / CELL)) + 1):
                    self.grid.setdefault((i, j), []).append(t)
        self.pits = {}
        for x, y in pits:
            self.pits.setdefault((int(x // 4), int(y // 4)), []).append((x, y))
        self.pads = [(min(p[0] for p in poly), min(p[1] for p in poly), max(p[0] for p in poly),
                      max(p[1] for p in poly), [tuple(p[:2]) for p in poly]) for poly in pads]

    @staticmethod
    def _in_tri(x, y, t):
        (ax, ay), (bx, by), (cx, cy) = t
        d1 = (x - bx) * (ay - by) - (ax - bx) * (y - by)
        d2 = (x - cx) * (by - cy) - (bx - cx) * (y - cy)
        d3 = (x - ax) * (cy - ay) - (cx - ax) * (y - ay)
        return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))

    def _in_pit(self, x, y):
        i, j = int(x // 4), int(y // 4)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for px, py in self.pits.get((i + di, j + dj), ()):
                    if (px - x) ** 2 + (py - y) ** 2 <= PIT_R * PIT_R:
                        return True
        return False

    def _in_pad(self, x, y):
        for x0, y0, x1, y1, poly in self.pads:
            if x0 <= x <= x1 and y0 <= y <= y1:
                inside = False
                n = len(poly)
                for k in range(n):
                    ax, ay = poly[k]
                    bx, by = poly[(k + 1) % n]
                    if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
                        inside = not inside
                if inside:
                    return True
        return False

    def hard(self, x, y):
        for t in self.grid.get((int(math.floor(x / CELL)), int(math.floor(y / CELL))), ()):
            if self._in_tri(x, y, t):
                return not self._in_pit(x, y)
        return self._in_pad(x, y)

    def hard_ue(self, X, Y):
        """Unreal cm (X = plan y * 100, Y = plan x * 100)."""
        return self.hard(Y / 100.0, X / 100.0)

    @classmethod
    def for_dir(cls, base, region):
        tris, pits, pads = [], [], []
        rpath = os.path.join(base, "roadsurface_%s.json" % region)
        spath = os.path.join(base, "sidewalks_%s.json" % region)
        if not os.path.isfile(rpath) and not os.path.isfile(spath):
            return None
        if os.path.isfile(rpath):
            for ch in load_json(rpath).get("chunks", {}).values():
                p = ch["p"]
                tris += [(p[t[0]], p[t[1]], p[t[2]]) for t in ch["tris"]]
        if os.path.isfile(spath):
            for ch in load_json(spath).get("chunks", {}).values():
                for kind in ("walk", "curb"):
                    part = ch.get(kind)
                    if not part:
                        continue
                    p = part["p"]
                    for t in part["tris"]:
                        a, b, c = p[t[0]], p[t[1]], p[t[2]]
                        if abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) > 1e-4:
                            tris.append((a, b, c))
        ppath = os.path.join(base, "props_%s.json" % region)
        if os.path.isfile(ppath):
            for key, items in load_json(ppath).get("groups", {}).items():
                if "TreePit" in key or "TreeGrate" in key:
                    pits += [(it[1] / 100.0, it[0] / 100.0) for it in items]
        shpath = os.path.join(base, "shoreline_%s.json" % region)
        if os.path.isfile(shpath):
            pads = [q["polygon"] for q in (load_json(shpath).get("pads") or ())]
        return cls(tris, pits, pads)


def veg_on_hard(veg_xy, hs, examples=5):
    """veg_xy: {mesh: [[X, Y], ...]} Unreal cm. -> (total, {mesh: n}, examples)."""
    by, ex, n = {}, [], 0
    for mesh, pts in veg_xy.items():
        if not is_veg(mesh):
            continue
        for p in pts:
            if hs.hard_ue(p[0], p[1]):
                n += 1
                by[mesh] = by.get(mesh, 0) + 1
                if len(ex) < examples:
                    ex.append([mesh, [round(p[0]), round(p[1])]])
    return n, by, ex


# ------------------------------------------------------------------------------------------------------- rules
def count(dump, key):
    """'labels.F8_Road', 'meshes.SM_CROP_*' (instances, glob summed), 'tags.X', 'classes.X', 'mpc_wind'."""
    if "." not in key:
        v = dump.get(key)
        return v if isinstance(v, (int, float)) else (1 if v else 0)
    sect, pat = key.split(".", 1)
    d = dump.get(sect) or {}
    tot = 0
    for k, v in d.items():
        if fnmatch.fnmatchcase(k, pat):
            tot += v.get("instances", 0) if isinstance(v, dict) else v
    return tot


def materials_on(dump, actor):
    mats = set()
    for k, v in (dump.get("meshes") or {}).items():
        if any(fnmatch.fnmatchcase(a, actor) for a in v.get("actors") or ()):
            mats.update(v.get("materials") or ())
    for m in (dump.get("label_materials") or {}).get(actor, ()):
        mats.add(m)
    return mats


def tracked_counts(dump):
    out = {}
    for sect in ("labels", "tags", "classes"):
        for k, v in (dump.get(sect) or {}).items():
            out["%s.%s" % (sect, k)] = v
    for k, v in (dump.get("meshes") or {}).items():
        out["meshes." + k] = v.get("instances", 0)
    return out


def run_rules(spec, dump, seed, golden_dump=None, side=None, region=None, flags=()):
    res = []
    for r in spec.get("rules", []):
        if r.get("seeds") and int(seed) not in r["seeds"]:
            continue
        if r.get("optional_flag") and r["optional_flag"] not in flags:
            continue
        out = {"id": r["id"], "kind": r["kind"], "why": r.get("why", "")}
        k = r["kind"]
        try:
            if k == "count_min":
                n = count(dump, r["key"])
                out.update(value=n, ok=n >= r.get("min", 1), detail="%s = %s (min %s)" % (r["key"], n, r.get("min", 1)))
            elif k == "count_min_each":
                vals = {key: count(dump, key) for key in r["keys"]}
                bad = [key for key, n in vals.items() if n < r.get("min", 1)]
                out.update(value=vals, ok=not bad,
                           detail=("zero: " + ", ".join(bad)) if bad else ", ".join("%s %s" % (a.split(".", 1)[1], b) for a, b in vals.items()))
            elif k == "truthy":
                v = dump.get(r["key"])
                out.update(value=v, ok=bool(v), detail="%s = %s" % (r["key"], v))
            elif k == "material_on":
                mats = materials_on(dump, r["actor"])
                out.update(value=sorted(mats), ok=r["material"] in mats,
                           detail="%s on %s: %s" % (r["material"], r["actor"], "yes" if r["material"] in mats else
                                                   "NO (has %s)" % (", ".join(sorted(mats)) or "nothing")))
            elif k == "count_eq_golden":
                n = count(dump, r["key"])
                if golden_dump is None:
                    out.update(value=n, ok=True, skipped=True, detail="%s = %s (no golden dump yet)" % (r["key"], n))
                else:
                    g = count(golden_dump, r["key"])
                    out.update(value=n, ok=n == g, detail="%s = %s, golden %s" % (r["key"], n, g))
            elif k == "no_big_drop":
                if golden_dump is None:
                    out.update(ok=True, skipped=True, detail="no golden dump yet")
                else:
                    new, old = tracked_counts(dump), tracked_counts(golden_dump)
                    md = r.get("max_drop", 0.5)
                    drops = sorted((key, g, new.get(key, 0)) for key, g in old.items()
                                   if g >= r.get("min_golden", 20) and new.get(key, 0) < g * (1 - md))
                    out.update(value=[list(d) for d in drops], ok=not drops,
                               detail=("; ".join("%s %d -> %d" % d for d in drops[:12]) + (" ..." if len(drops) > 12 else ""))
                               if drops else "no tracked count fell by more than %d%%" % round(md * 100))
            elif k == "veg_on_hard":
                if "veg_on_hard" in dump and "veg_xy" not in dump:
                    n = int(dump["veg_on_hard"])
                    out.update(value=n, ok=n <= r.get("max", 0), detail="%d vegetation instances on road/walk (dump)" % n)
                elif "veg_xy" not in dump:
                    out.update(value=None, ok=False, detail="level dump has no vegetation positions (veg_xy): "
                                                            "capture with visual_capture_ue.py")
                else:
                    side = side or dump.get("bt_side_dir")
                    hs = HardSurface.for_dir(side, region) if side and os.path.isdir(side) else None
                    if hs is None:
                        out.update(value=None, ok=False,
                                   detail="no road/walk side files for %s in %s (pass --side <bt>/Saved/CityGen)" % (region, side))
                    else:
                        n, by, ex = veg_on_hard(dump["veg_xy"], hs)
                        tot = sum(len(v) for m, v in dump["veg_xy"].items() if is_veg(m))
                        top = sorted(by.items(), key=lambda kv: -kv[1])[:6]
                        out.update(value=n, ok=n <= r.get("max", 0), by_mesh=by, examples=ex,
                                   detail="%d of %d vegetation instances on road/walk/curb/car-park%s" % (
                                       n, tot, (": " + ", ".join("%s %d" % t for t in top)) if top else ""))
            else:
                out.update(ok=False, detail="unknown rule kind %s" % k)
        except Exception as exc:  # noqa: BLE001
            out.update(ok=False, detail="rule error: %r" % exc)
        res.append(out)
    return res


# ------------------------------------------------------------------------------------------------- expectations
def parse_expect(items):
    if not items:
        raise SystemExit("--expect is required: what this import meant to change ('beach_*', 'tag:shore', "
                         "'asset:M_Shore_Sand'), or --expect none")
    pats = []
    for it in items:
        for p in it.split(","):
            p = p.strip()
            if p and p.lower() != "none":
                pats.append(p)
    return pats


def cam_expected(cam, pats):
    hit = []
    for p in pats:
        if p.startswith("asset:"):
            continue
        if p.startswith("tag:"):
            if p[4:] in (cam.get("tags") or ()):
                hit.append(p)
        elif fnmatch.fnmatchcase(cam["name"], p):
            hit.append(p)
    return hit


# ---------------------------------------------------------------------------------------------------------- check
def golden_dir(goldens, seed):
    return os.path.join(goldens, "seed%s" % seed)


def load_json(p, default=None):
    if not p or not os.path.isfile(p):
        return default
    with open(p) as h:
        return json.load(h)


def save(p, text):
    with open(p, "w") as h:
        h.write(text)


def check(run, pats, spec, goldens=GOLDENS, side=None, flags=(), write=True):
    cap = load_json(os.path.join(run, "capture.json"))
    if cap is None:
        raise SystemExit("no capture.json in %s" % run)
    seed = cap["seed"]
    region = cap.get("region") or "seed%s_city" % seed
    th = dict(spec["thresholds"])
    gd = golden_dir(goldens, seed)
    gold = load_json(os.path.join(gd, "golden.json"), {}) or {}
    gcams = gold.get("cams", {})
    flags = set(flags) | set(cap.get("flags") or ())
    shots = {c["name"]: c for c in cap.get("cams", [])}
    cams = [c for c in spec["cameras"] if str(c["seed"]) == str(seed)]
    W = th["work_width"]
    for d in ("thumbs/golden", "thumbs/new", "thumbs/diff"):
        os.makedirs(os.path.join(run, d), exist_ok=True)
    rows = []
    used = set()
    for cam in cams:
        name = cam["name"]
        exp = cam_expected(cam, pats)
        used.update(exp)
        row = {"name": name, "tags": cam.get("tags", []), "expected": exp, "source": cam.get("source", "")}
        shot = shots.get(name) or {}
        newp = os.path.join(run, shot["file"]) if shot.get("file") else None
        g = gcams.get(name)
        goldp = os.path.join(gd, g["file"]) if g else None
        tol_s = cam.get("ssim_tol", th["ssim_tol"])
        tol_f = cam.get("frac_tol", th["frac_tol"])
        tol_c = cam.get("color_tol", th.get("color_tol", 0.02))
        if g and g.get("noise"):
            tol_s = max(tol_s, th["noise_mult"] * g["noise"].get("dssim", 0))
            tol_f = max(tol_f, th["noise_mult"] * g["noise"].get("frac", 0))
            tol_c = max(tol_c, th["noise_mult"] * g["noise"].get("dcolor", 0))
        tol = {"dssim": round(tol_s, 4), "frac": round(tol_f, 4), "dcolor": round(tol_c, 4)}
        row["tol"] = tol
        if not newp or not os.path.isfile(newp):
            row.update(status="FAIL", why="no frame captured" + (" (%s)" % shot.get("error") if shot.get("error") else ""))
            rows.append(row)
            continue
        b = load_img(newp, W)
        thumb(newp, os.path.join(run, "thumbs/new/%s.jpg" % name), 480)
        row["new"] = "thumbs/new/%s.jpg" % name
        if blank(b, th):
            row.update(status="FAIL", why="blank or black frame (mean %.3f, std %.3f)" % (float(luma(b).mean()), float(luma(b).std())))
            rows.append(row)
            continue
        if not goldp or not os.path.isfile(goldp):
            row.update(status="NEW", why="no golden yet: approve this run once Kenny OKs it")
            rows.append(row)
            continue
        a = load_img(goldp, W)
        if a.shape != b.shape:
            row.update(status="FAIL", why="frame size %s differs from golden %s" % (b.shape[:2], a.shape[:2]))
            rows.append(row)
            continue
        thumb(goldp, os.path.join(run, "thumbs/golden/%s.jpg" % name), 480)
        row["golden"] = "thumbs/golden/%s.jpg" % name
        diff_image(a, b, os.path.join(run, "thumbs/diff/%s.jpg" % name))
        row["diff"] = "thumbs/diff/%s.jpg" % name
        m = metrics(a, b, th["pix_delta"])
        row["metrics"] = m
        changed = is_changed(m, tol)
        if exp and cam.get("roi"):
            mr = metrics(a, b, th["pix_delta"], cam["roi"])
            row["metrics_roi"] = mr
            changed = is_changed(mr, tol)
        row["changed"] = changed
        if exp and not changed:
            row.update(status="FAIL", why="expected a change (%s) but the frame matches the golden: the import "
                                          "did not reach Unreal?" % ", ".join(exp))
        elif not exp and changed:
            row.update(status="FAIL", why="changed but not expected (1-SSIM %.4f/%.4f, pixels %.2f%%/%.2f%%, "
                                          "colour shift %.3f/%.3f)" % (m["dssim"], tol_s, m["frac"] * 100, tol_f * 100,
                                                                      m["dcolor"], tol_c))
        elif exp:
            row.update(status="PASS", why="changed as expected (%s): Kenny to judge the look" % ", ".join(exp))
        else:
            row.update(status="PASS", why="matches the golden")
        rows.append(row)
    # assets (material packages etc.) named in --expect: the md5 must differ from the golden dump's
    dump = load_json(os.path.join(run, cap.get("level_dump", "level_dump.json")), {}) or {}
    gdump = load_json(os.path.join(gd, "level_dump.json"))
    assets = []
    for p in pats:
        if not p.startswith("asset:"):
            continue
        used.add(p)
        nm = p[6:]
        new_h = (dump.get("assets") or {}).get(nm)
        old_h = ((gdump or {}).get("assets") or {}).get(nm)
        if new_h is None:
            assets.append({"asset": nm, "ok": False, "detail": "not in the level dump's watched assets"})
        elif old_h is None:
            assets.append({"asset": nm, "ok": True, "skipped": True, "detail": "no golden hash yet"})
        else:
            assets.append({"asset": nm, "ok": new_h != old_h,
                           "detail": "changed" if new_h != old_h else "UNCHANGED since the goldens: the new material never reached Unreal"})
    unused = [p for p in pats if p not in used]
    rules = run_rules(spec, dump, seed, gdump, side, region, flags) if dump else [
        {"id": "level_dump", "kind": "file", "ok": False, "detail": "no level dump in the run"}]
    fail = any(r["status"] == "FAIL" for r in rows) or any(not r["ok"] for r in rules) or \
        any(not a["ok"] for a in assets) or bool(unused)
    verdict = "FAIL" if fail else ("NEEDS_APPROVAL" if any(r["status"] == "NEW" for r in rows) else "PASS")
    rep = {"verdict": verdict, "run": os.path.abspath(run), "seed": seed, "map": cap.get("map"), "tag": cap.get("tag"),
           "expect": pats, "unused_expect": unused, "cams": rows, "rules": rules, "assets": assets,
           "golden": {k: gold.get(k) for k in ("approved_by", "approved_at", "source_run", "tag")},
           "checked_at": now_iso(), "capture": {k: cap.get(k) for k in ("tag", "commit", "started", "finished", "res")}}
    if write:
        save(os.path.join(run, "report.json"), json.dumps(rep, indent=1, default=str))
        save(os.path.join(run, "report.html"), render(rep))
    return rep


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------------------------------------- report
CSS = """
:root{--bg:#f6f6f4;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#deded8;--pass:#1f7a3a;--fail:#b3261e;--new:#8a5a00}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecece8;--mut:#a0a09a;--card:#21211f;--line:#34342f;
--pass:#5cc97a;--fail:#ff7b72;--new:#e8b44c}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,system-ui,sans-serif;margin:0;padding:16px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:24px 0 8px}.mut{color:var(--mut)}
.v{display:inline-block;padding:2px 10px;border-radius:4px;color:#fff;font-weight:600}
.PASS{background:var(--pass)}.FAIL{background:var(--fail)}.NEW,.NEEDS_APPROVAL{background:var(--new)}
table{border-collapse:collapse;width:100%;background:var(--card)}td,th{border:1px solid var(--line);padding:4px 8px;
text-align:left;vertical-align:top}.cam{background:var(--card);border:1px solid var(--line);border-radius:6px;
margin:0 0 12px;padding:10px}.row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}
.row img{width:100%;display:block;border-radius:3px}.cap{font-size:12px;color:var(--mut)}
@media (max-width:700px){.row{grid-template-columns:1fr}}
"""


def esc(s):
    return html.escape(str(s))


def render(rep):
    v = rep["verdict"]
    out = ["<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
           "initial-scale=1'><title>Visual check</title><style>%s</style></head><body>" % CSS]
    out.append("<h1>Visual check: seed %s, %s <span class='v %s'>%s</span></h1>" % (esc(rep["seed"]), esc(rep.get("tag")), v, v))
    g = rep.get("golden") or {}
    out.append("<p class='mut'>Run %s<br>Checked %s. Goldens approved by %s at %s (from %s).<br>Expected to change: %s</p>" % (
        esc(rep["run"]), esc(rep["checked_at"]), esc(g.get("approved_by") or "-"), esc(g.get("approved_at") or "-"),
        esc(g.get("source_run") or "-"), esc(", ".join(rep["expect"]) or "nothing (--expect none)")))
    if v == "PASS":
        out.append("<p><b>Kenny:</b> everything below matched or changed where this import said it would. Judge the look of the changed cameras.</p>")
    elif v == "FAIL":
        out.append("<p><b>Not for Kenny yet:</b> the build lane fixes the failures first.</p>")
    if rep.get("unused_expect"):
        out.append("<p class='FAIL v'>--expect matched no camera or asset: %s</p>" % esc(", ".join(rep["unused_expect"])))
    out.append("<h2>Level rules</h2><table><tr><th>rule</th><th>result</th><th>detail</th></tr>")
    for r in rep["rules"]:
        s = "PASS" if r["ok"] else "FAIL"
        if r.get("skipped"):
            s = "PASS"
        out.append("<tr><td>%s</td><td><span class='v %s'>%s</span></td><td>%s%s</td></tr>" % (
            esc(r["id"]), s, s + (" (skip)" if r.get("skipped") else ""), esc(r.get("detail", "")),
            ("<br><span class='mut'>%s</span>" % esc(r["why"])) if r.get("why") else ""))
    for a in rep.get("assets", []):
        s = "PASS" if a["ok"] else "FAIL"
        out.append("<tr><td>asset %s</td><td><span class='v %s'>%s</span></td><td>%s</td></tr>" % (esc(a["asset"]), s, s, esc(a["detail"])))
    out.append("</table>")
    order = {"FAIL": 0, "NEW": 1, "PASS": 2}
    cams = sorted(rep["cams"], key=lambda r: (order.get(r["status"], 3), not r.get("expected"), r["name"]))
    np_ = sum(1 for r in cams if r["status"] == "PASS")
    out.append("<h2>Cameras: %d pass, %d fail, %d new</h2>" % (np_, sum(1 for r in cams if r["status"] == "FAIL"),
                                                                sum(1 for r in cams if r["status"] == "NEW")))
    for r in cams:
        m = r.get("metrics") or {}
        out.append("<div class='cam'><b>%s</b> <span class='v %s'>%s</span> <span class='mut'>%s</span><br>%s" % (
            esc(r["name"]), r["status"], r["status"], esc(", ".join(r.get("tags", []))), esc(r.get("why", ""))))
        if m:
            out.append("<div class='cap'>1-SSIM %.4f (tol %.4f) &middot; pixels changed %.2f%% (tol %.2f%%) &middot; "
                       "colour shift %.3f (tol %.3f)%s</div>" % (
                           m["dssim"], r["tol"]["dssim"], m["frac"] * 100, r["tol"]["frac"] * 100, m["dcolor"],
                           r["tol"]["dcolor"],
                           (" &middot; in roi: 1-SSIM %.4f, %.2f%%, colour %.3f" % (
                               r["metrics_roi"]["dssim"], r["metrics_roi"]["frac"] * 100, r["metrics_roi"]["dcolor"]))
                           if r.get("metrics_roi") else ""))
        out.append("<div class='row'>")
        for k, lab in (("golden", "golden"), ("new", "new"), ("diff", "difference (red)")):
            if r.get(k):
                out.append("<div><img loading='lazy' src='%s' alt='%s %s'><div class='cap'>%s</div></div>" % (
                    esc(r[k]), esc(r["name"]), lab, lab))
            else:
                out.append("<div class='cap'>%s: none</div>" % lab)
        out.append("</div><div class='cap'>%s</div></div>" % esc(r.get("source", "")))
    out.append("</body></html>")
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------------------- approve
def approve(run, by, goldens=GOLDENS, note="", force=False, cams=None):
    cap = load_json(os.path.join(run, "capture.json"))
    if cap is None:
        raise SystemExit("no capture.json in %s" % run)
    rep = load_json(os.path.join(run, "report.json"))
    if rep is None and not force:
        raise SystemExit("run the check first (no report.json); --force to approve anyway")
    if rep is not None and not force:
        bad_rules = [r["id"] for r in rep["rules"] if not r["ok"]]
        bad_cams = [r["name"] for r in rep["cams"] if r["status"] == "FAIL" and
                    not r.get("why", "").startswith("changed but not expected")
                    and not r.get("why", "").startswith("expected a change")]
        if bad_rules or bad_cams:
            raise SystemExit("refusing: rules failed %s, broken frames %s (fix, or --force with a --note)" % (bad_rules, bad_cams))
    seed = cap["seed"]
    gd = golden_dir(goldens, seed)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    old = load_json(os.path.join(gd, "golden.json"))
    if old is not None:
        hist = os.path.join(gd, "history", stamp)
        os.makedirs(hist, exist_ok=True)
        for f in os.listdir(gd):
            if f != "history":
                shutil.move(os.path.join(gd, f), os.path.join(hist, f))
    os.makedirs(os.path.join(gd, "shots"), exist_ok=True)
    th = None
    spec = load_json(SPEC, {})
    if spec:
        th = spec.get("thresholds")
    gold = {"seed": seed, "map": cap.get("map"), "tag": cap.get("tag"), "approved_by": by, "approved_at": now_iso(),
            "approved_on_host": os.uname().nodename, "approved_by_login": getpass.getuser(), "note": note,
            "forced": bool(force), "source_run": os.path.abspath(run), "capture_commit": cap.get("commit"),
            "previous": (old or {}).get("approved_at"), "cams": {}}
    keep = (old or {}).get("cams", {}) if cams else {}
    for c in cap.get("cams", []):
        name = c["name"]
        if not c.get("file"):
            continue
        if cams and name not in cams:
            if name in keep:   # partial approval: keep the old golden for the other cameras (copied back from history)
                src = os.path.join(gd, "history", stamp, keep[name]["file"])
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(gd, keep[name]["file"]))
                    gold["cams"][name] = keep[name]
            continue
        src = os.path.join(run, c["file"])
        dst = "shots/%s.png" % name
        shutil.copy2(src, os.path.join(gd, dst))
        rec = {"file": dst, "sha256": sha256(src), "loc_ue": c.get("loc_ue"), "yaw": c.get("yaw"), "pitch": c.get("pitch")}
        if c.get("file_b") and os.path.isfile(os.path.join(run, c["file_b"])) and th:
            a = load_img(src, th["work_width"])
            b = load_img(os.path.join(run, c["file_b"]), th["work_width"])
            rec["noise"] = metrics(a, b, th["pix_delta"])
        gold["cams"][name] = rec
    dname = cap.get("level_dump", "level_dump.json")
    if os.path.isfile(os.path.join(run, dname)):
        shutil.copy2(os.path.join(run, dname), os.path.join(gd, "level_dump.json"))
    save(os.path.join(gd, "golden.json"), json.dumps(gold, indent=1))
    return gold


# ---------------------------------------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--run", required=True)
    c.add_argument("--expect", action="append", help="camera glob | tag:<tag> | asset:<name> | none (repeatable)")
    c.add_argument("--goldens", default=GOLDENS)
    c.add_argument("--side", help="building-types Saved/CityGen (road/walk side files); default from the dump")
    c.add_argument("--spec", default=SPEC)
    c.add_argument("--flags", default="", help="comma list, e.g. pack (GEN_PACK=game imports)")
    a = sub.add_parser("approve")
    a.add_argument("--run", required=True)
    a.add_argument("--by", required=True, help="who OK'd it (Kenny)")
    a.add_argument("--note", default="")
    a.add_argument("--cams", default="", help="comma list: approve only these cameras")
    a.add_argument("--goldens", default=GOLDENS)
    a.add_argument("--force", action="store_true")
    r = sub.add_parser("rules")
    r.add_argument("--dump", required=True)
    r.add_argument("--seed", default="7")
    r.add_argument("--side")
    r.add_argument("--golden-dump")
    r.add_argument("--spec", default=SPEC)
    r.add_argument("--flags", default="")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        spec = load_json(args.spec)
        rep = check(args.run, parse_expect(args.expect), spec, args.goldens, args.side,
                    [f for f in args.flags.split(",") if f])
        bad = [x for x in rep["cams"] if x["status"] == "FAIL"]
        print("%s  seed %s  cams %d (fail %d, new %d)  rules fail %d  -> %s" % (
            rep["verdict"], rep["seed"], len(rep["cams"]), len(bad), sum(1 for x in rep["cams"] if x["status"] == "NEW"),
            sum(1 for x in rep["rules"] if not x["ok"]), os.path.join(args.run, "report.html")))
        for x in bad:
            print("  FAIL cam %s: %s" % (x["name"], x["why"]))
        for x in rep["rules"]:
            if not x["ok"]:
                print("  FAIL rule %s: %s" % (x["id"], x["detail"]))
        for x in rep["assets"]:
            if not x["ok"]:
                print("  FAIL asset %s: %s" % (x["asset"], x["detail"]))
        if rep["unused_expect"]:
            print("  FAIL --expect matched nothing: %s" % rep["unused_expect"])
        return EXIT[rep["verdict"]]
    if args.cmd == "approve":
        g = approve(args.run, args.by, args.goldens, args.note, args.force, [x for x in args.cams.split(",") if x])
        print("approved %d cameras for seed %s by %s at %s -> %s" % (len(g["cams"]), g["seed"], g["approved_by"],
                                                                      g["approved_at"], golden_dir(args.goldens, g["seed"])))
        return 0
    if args.cmd == "rules":
        spec = load_json(args.spec)
        dump = load_json(args.dump)
        res = run_rules(spec, dump, args.seed, load_json(args.golden_dump), args.side, "seed%s_city" % args.seed,
                        [f for f in args.flags.split(",") if f])
        for x in res:
            print("%s %-20s %s" % ("PASS" if x["ok"] else "FAIL", x["id"], x["detail"]))
        return 0 if all(x["ok"] for x in res) else 1


if __name__ == "__main__":
    sys.exit(main())
