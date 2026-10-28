"""Tests for visual_check.py (Lane V). python3 -I Scripts/gencity/test_visual_check.py

Synthetic images and dumps prove each verdict; the "today's misses" cases prove the two things Kenny caught by eye on
2026-10-28 would have failed the run:
  * plants on roads/sidewalks: a level whose vegetation was placed without veg_clear (the v9 import) fails the
    veg_on_hard rule, and the filtered one (v10) passes; on the real seed-7 side files when they are on this Mac
    (VISUAL_TEST_SIDE, default lane V's snapshot or BuildingTypes-drive/Saved/CityGen): ~3,986 before, 0 after;
  * beach sand unchanged in Unreal: an import that said it changed the beach (--expect 'beach_*') but whose beach
    frame equals the golden fails; with the real drive_v10_beach_eye.jpg when it is on this Mac.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import visual_check as V  # noqa: E402

WORK = "/Volumes/Sound Libraries/SkyCity Work"
SIDE_CANDIDATES = [os.environ.get("VISUAL_TEST_SIDE") or "", os.path.join(WORK, "LaneV", "data_snapshot", "seed7"),
                   os.path.join(WORK, "BuildingTypes-drive", "Saved", "CityGen")]
REAL_BEACH = os.path.expanduser("~/UnrealProjects/_bt_mgmt/shots/v10/drive_v10_beach_eye.jpg")
REAL_DUMP_V10 = os.path.join(WORK, "SkyCity-drive", "Saved", "GenCity", "level_dump_GenCity_Seed7.json")


def scene(w=320, h=180, sand=(222, 196, 150), seed=0, noise=0.0):
    """A street-ish picture: sky gradient, buildings, a road, and sand across the bottom 40%."""
    rng = np.random.default_rng(seed)
    a = np.zeros((h, w, 3), np.float32)
    for y in range(h):
        a[y, :, :] = (120 + y * 0.4, 160 + y * 0.3, 220)
    for i in range(6):
        x0 = 20 + i * 50
        a[40 - i * 3:int(h * 0.6), x0:x0 + 30] = (90 + i * 20, 80 + i * 10, 70)
        a[50:int(h * 0.6):8, x0 + 4:x0 + 26] = (40, 50, 70)
    a[int(h * 0.55):int(h * 0.6), :] = (60, 60, 62)
    a[int(h * 0.6):, :] = sand
    a[int(h * 0.6):, :] += rng.normal(0, 6, (h - int(h * 0.6), w, 1)).astype(np.float32)   # sand grain (fixed)
    if noise:
        a += np.random.default_rng(seed + 99).normal(0, noise, a.shape).astype(np.float32)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


SPEC = {
    "thresholds": {"ssim_tol": 0.03, "frac_tol": 0.015, "pix_delta": 0.10, "color_tol": 0.02, "work_width": 320, "noise_mult": 3.0,
                   "blank_mean": 0.03, "blank_std": 0.01},
    "rules": [{"id": "veg_on_hard", "kind": "veg_on_hard", "max": 0},
              {"id": "road_tiles", "kind": "count_min", "key": "labels.F8_Road", "min": 1},
              {"id": "road_asphalt", "kind": "material_on", "actor": "F8_Road", "material": "MI_KitRoad_asphalt"},
              {"id": "no_big_drop", "kind": "no_big_drop", "max_drop": 0.5}],
    "cameras": [
        {"name": "beach_eye", "seed": 7, "tags": ["beach", "shore"], "roi": [0.0, 0.6, 1.0, 1.0],
         "loc_ue": [0, 0, 120], "yaw": 0, "pitch": 0},
        {"name": "downtown_corner", "seed": 7, "tags": ["downtown"], "loc_ue": [0, 0, 170], "yaw": 0, "pitch": 0},
        {"name": "aerial_city", "seed": 7, "tags": ["aerial"], "loc_ue": [0, 0, 9000], "yaw": 0, "pitch": -40},
        {"name": "s17_downtown", "seed": 17, "tags": ["downtown"], "loc_ue": [0, 0, 170], "yaw": 0, "pitch": 0},
    ],
}


def road_side_dir(d):
    """A 10 m x 10 m road square at plan (0..10, 0..10) and a walk band x 10..12; a tree pit at (11, 5)."""
    rs = {"chunks": {"0_0": {"p": [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]], "tris": [[0, 1, 2], [0, 2, 3]]}}}
    sw = {"chunks": {"0_0": {"walk": {"p": [[10, 0, .15], [12, 0, .15], [12, 10, .15], [10, 10, .15]],
                                      "tris": [[0, 1, 2], [0, 2, 3]]}}}}
    pr = {"groups": {"KIT_SS_TreePit|prop": [[500.0, 1100.0, 0, 0]]}}
    sh = {"pads": [{"polygon": [[20, 20], [30, 20], [30, 30], [20, 30]]}]}
    for name, doc in (("roadsurface", rs), ("sidewalks", sw), ("props", pr), ("shoreline", sh)):
        json.dump(doc, open(os.path.join(d, "%s_seed7_city.json" % name), "w"))
    return d


def ue(x, y):
    return [y * 100.0, x * 100.0]


def good_dump(side, veg):
    return {"labels": {"F8_Road": 33, "F7_walk": 34}, "classes": {"DirectionalLight": 2}, "tags": {},
            "meshes": {"SM_F8_Road_0_0": {"instances": 1, "components": 1, "materials": ["MI_KitRoad_asphalt"],
                                          "actors": ["F8_Road"]},
                       "KIT_SS_PaintBar": {"instances": 13594, "components": 9, "materials": [], "actors": []}},
            "mpc_wind": True, "veg_xy": veg, "bt_side_dir": side, "assets": {"M_Shore_Sand": "aaa"}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="visual_check_test_")
        os.makedirs(os.path.join(self.tmp, "side"))
        self.side = road_side_dir(os.path.join(self.tmp, "side"))
        self.goldens = os.path.join(self.tmp, "goldens")
        self.clean_veg = {"SM_VEG_GrassTall_A": [ue(20, 5), ue(-4, 4)], "SM_VEG_SilverMaple_S": [ue(11.0, 5.2)]}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_run(self, name, images, dump=None, seed=7):
        run = os.path.join(self.tmp, name)
        os.makedirs(os.path.join(run, "shots"))
        cams = []
        for cam, im in images.items():
            rec = {"name": cam}
            if im is not None:
                im.save(os.path.join(run, "shots", cam + ".png"))
                rec["file"] = "shots/%s.png" % cam
            cams.append(rec)
        json.dump({"seed": seed, "tag": name, "cams": cams, "level_dump": "level_dump.json"},
                  open(os.path.join(run, "capture.json"), "w"))
        json.dump(dump if dump is not None else good_dump(self.side, self.clean_veg),
                  open(os.path.join(run, "level_dump.json"), "w"))
        return run

    def base_images(self, **over):
        im = {"beach_eye": scene(seed=1), "downtown_corner": scene(seed=2, sand=(90, 120, 60)),
              "aerial_city": scene(seed=3, sand=(70, 100, 140))}
        im.update(over)
        return im

    def approved(self):
        run = self.make_run("golden_run", self.base_images())
        rep = V.check(run, [], SPEC, self.goldens)
        self.assertEqual(rep["verdict"], "NEEDS_APPROVAL")
        V.approve(run, "Kenny", self.goldens, note="test")
        return run

    def cam(self, rep, name):
        return next(c for c in rep["cams"] if c["name"] == name)


class Verdicts(Base):
    def test_first_run_needs_approval_then_approve_records_who_when(self):
        self.approved()
        g = json.load(open(os.path.join(self.goldens, "seed7", "golden.json")))
        self.assertEqual(g["approved_by"], "Kenny")
        self.assertTrue(g["approved_at"])
        self.assertEqual(sorted(g["cams"]), ["aerial_city", "beach_eye", "downtown_corner"])
        self.assertTrue(os.path.isfile(os.path.join(self.goldens, "seed7", "level_dump.json")))

    def test_no_change_expected_none_passes_and_writes_report(self):
        self.approved()
        run = self.make_run("same", self.base_images())
        rep = V.check(run, [], SPEC, self.goldens)
        self.assertEqual(rep["verdict"], "PASS", rep)
        html = open(os.path.join(run, "report.html")).read()
        self.assertIn("beach_eye", html)
        self.assertIn("approved by Kenny", html.replace("Goldens approved by", "approved by"))

    def test_render_noise_is_not_a_change(self):
        self.approved()
        im = {k: scene(seed=s, sand=sd, noise=2.0) for k, s, sd in (("beach_eye", 1, (222, 196, 150)),
                                                                      ("downtown_corner", 2, (90, 120, 60)),
                                                                      ("aerial_city", 3, (70, 100, 140)))}
        rep = V.check(self.make_run("noisy", im), [], SPEC, self.goldens)
        self.assertEqual(rep["verdict"], "PASS", [c.get("metrics") for c in rep["cams"]])

    def test_sand_unchanged_when_expected_fails(self):
        """Today's miss 2: the shoreline code changed, the import ran, the beach in Unreal did not."""
        self.approved()
        rep = V.check(self.make_run("noop", self.base_images()), ["beach_*"], SPEC, self.goldens)
        self.assertEqual(rep["verdict"], "FAIL")
        c = self.cam(rep, "beach_eye")
        self.assertEqual(c["status"], "FAIL")
        self.assertIn("expected a change", c["why"])

    def test_sand_changed_when_expected_passes(self):
        self.approved()
        rep = V.check(self.make_run("sand", self.base_images(beach_eye=scene(seed=1, sand=(238, 214, 170)))),
                      ["tag:beach"], SPEC, self.goldens)
        self.assertEqual(rep["verdict"], "PASS", self.cam(rep, "beach_eye"))
        self.assertTrue(self.cam(rep, "beach_eye")["changed"])

    def test_unexpected_change_fails(self):
        self.approved()
        rep = V.check(self.make_run("drift", self.base_images(downtown_corner=scene(seed=2, sand=(160, 60, 60)))),
                      ["beach_*"], SPEC, self.goldens)
        self.assertEqual(rep["verdict"], "FAIL")
        self.assertIn("not expected", self.cam(rep, "downtown_corner")["why"])

    def test_expected_change_outside_roi_does_not_count(self):
        self.approved()
        im = self.base_images()
        a = np.asarray(im["beach_eye"]).copy()
        a[:40, :, :] = 255 - a[:40, :, :]              # the sky changed, the sand did not
        im["beach_eye"] = Image.fromarray(a)
        rep = V.check(self.make_run("sky", im), ["beach_eye"], SPEC, self.goldens)
        self.assertEqual(self.cam(rep, "beach_eye")["status"], "FAIL")

    def test_blank_and_missing_frames_fail(self):
        self.approved()
        im = self.base_images(downtown_corner=Image.new("RGB", (320, 180)), aerial_city=None)
        rep = V.check(self.make_run("broken", im), [], SPEC, self.goldens)
        self.assertIn("blank", self.cam(rep, "downtown_corner")["why"])
        self.assertIn("no frame", self.cam(rep, "aerial_city")["why"])
        self.assertEqual(rep["verdict"], "FAIL")

    def test_expect_that_matches_nothing_fails(self):
        self.approved()
        rep = V.check(self.make_run("typo", self.base_images(beach_eye=scene(seed=1, sand=(238, 214, 170)))),
                      ["beahc_*", "beach_*"], SPEC, self.goldens)
        self.assertEqual(rep["unused_expect"], ["beahc_*"])
        self.assertEqual(rep["verdict"], "FAIL")

    def test_expect_is_required(self):
        with self.assertRaises(SystemExit):
            V.parse_expect(None)
        self.assertEqual(V.parse_expect(["none"]), [])
        self.assertEqual(V.parse_expect(["beach_*,tag:shore"]), ["beach_*", "tag:shore"])

    def test_asset_unchanged_when_expected_fails(self):
        self.approved()
        rep = V.check(self.make_run("asset", self.base_images(beach_eye=scene(seed=1, sand=(238, 214, 170)))),
                      ["beach_*", "asset:M_Shore_Sand"], SPEC, self.goldens)
        self.assertEqual(rep["verdict"], "FAIL")
        self.assertIn("UNCHANGED", rep["assets"][0]["detail"])

    def test_second_approval_keeps_history(self):
        self.approved()
        run = self.make_run("v2", self.base_images(beach_eye=scene(seed=1, sand=(238, 214, 170))))
        V.check(run, ["beach_*"], SPEC, self.goldens)
        V.approve(run, "Kenny", self.goldens)
        hist = os.listdir(os.path.join(self.goldens, "seed7", "history"))
        self.assertEqual(len(hist), 1)
        self.assertTrue(os.path.isfile(os.path.join(self.goldens, "seed7", "history", hist[0], "golden.json")))
        rep = V.check(self.make_run("v3", self.base_images(beach_eye=scene(seed=1, sand=(238, 214, 170)))), [],
                      SPEC, self.goldens)
        self.assertEqual(rep["verdict"], "PASS")

    def test_approve_refuses_a_run_with_failed_rules(self):
        bad = good_dump(self.side, {"SM_VEG_GrassTall_A": [ue(5, 5)]})
        run = self.make_run("veggy", self.base_images(), dump=bad)
        V.check(run, [], SPEC, self.goldens)
        with self.assertRaises(SystemExit):
            V.approve(run, "Kenny", self.goldens)

    def test_only_this_seeds_cameras(self):
        rep = V.check(self.make_run("s7", self.base_images()), [], SPEC, self.goldens)
        self.assertNotIn("s17_downtown", [c["name"] for c in rep["cams"]])

    def test_cli_exit_codes(self):
        self.approved()
        spec = os.path.join(self.tmp, "spec.json")
        json.dump(SPEC, open(spec, "w"))
        run = self.make_run("cli", self.base_images())
        py = [sys.executable, "-I", os.path.join(HERE, "visual_check.py"), "check", "--run", run, "--goldens",
              self.goldens, "--spec", spec]
        self.assertEqual(subprocess.run(py + ["--expect", "none"], capture_output=True).returncode, 0)
        self.assertEqual(subprocess.run(py + ["--expect", "beach_*"], capture_output=True).returncode, 1)


class Rules(Base):
    def rules(self, dump, golden=None, seed=7):
        return {r["id"]: r for r in V.run_rules(SPEC, dump, seed, golden, None, "seed7_city")}

    def test_plants_on_road_and_walk_fail_tree_pit_and_off_road_pass(self):
        """Today's miss 1 in miniature: grass on the road and the walk, a pad; the tree in its pit is fine."""
        veg = {"SM_VEG_GrassTall_A": [ue(5, 5), ue(11, 2), ue(20, 5), ue(25, 25)],
               "SM_VEG_SilverMaple_S": [ue(11.0, 5.2)], "KIT_SS_Hydrant": [ue(5, 5)]}
        r = self.rules(good_dump(self.side, veg))["veg_on_hard"]
        self.assertFalse(r["ok"])
        self.assertEqual(r["value"], 3)               # road, walk, beach car-park pad
        r = self.rules(good_dump(self.side, self.clean_veg))["veg_on_hard"]
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["value"], 0)

    def test_veg_rule_fails_closed_without_positions_or_side_files(self):
        d = good_dump(self.side, self.clean_veg)
        d.pop("veg_xy")
        self.assertFalse(self.rules(d)["veg_on_hard"]["ok"])
        d = good_dump(os.path.join(self.tmp, "nowhere"), self.clean_veg)
        self.assertFalse(self.rules(d)["veg_on_hard"]["ok"])

    def test_feature_to_zero_and_wrong_material_and_big_drop(self):
        g = good_dump(self.side, self.clean_veg)
        d = json.loads(json.dumps(g))
        d["labels"]["F8_Road"] = 0
        d["meshes"]["SM_F8_Road_0_0"]["materials"] = ["WorldGridMaterial"]
        d["meshes"]["KIT_SS_PaintBar"]["instances"] = 100
        r = self.rules(d, golden=g)
        self.assertFalse(r["road_tiles"]["ok"])
        self.assertFalse(r["road_asphalt"]["ok"])
        self.assertFalse(r["no_big_drop"]["ok"])
        self.assertIn("KIT_SS_PaintBar", r["no_big_drop"]["detail"])
        r = self.rules(g, golden=g)
        self.assertTrue(all(x["ok"] for x in r.values()), r)


def side_dir():
    for d in SIDE_CANDIDATES:
        if d and os.path.isfile(os.path.join(d, "roadsurface_seed7_city.json")) and \
                os.path.isfile(os.path.join(d, "landcover_seed7_city.json")):
            return d
    return None


def unfiltered_veg(base):
    """What a v9-style import put in the level: every vegetation instance of the side files, no veg_clear."""
    veg = {}
    lc = json.load(open(os.path.join(base, "landcover_seed7_city.json")))
    for b in ("hero", "fill", "crops"):
        for k, v in (lc.get(b) or {}).items():
            veg.setdefault(k, []).extend([it[0], it[1]] for it in v)
    p = os.path.join(base, "lotdress_seed7_city.json")
    if os.path.isfile(p):
        for k, v in (json.load(open(p)).get("plants") or {}).items():
            veg.setdefault(k if V.is_veg(k) else "VEG_" + k, []).extend([it[0], it[1]] for it in v)
    p = os.path.join(base, "kit_layout_seed7_city.json")
    if os.path.isfile(p):
        for k, v in json.load(open(p))["groups"].items():
            if V.is_veg(k):
                veg.setdefault(k, []).extend([it[0], it[1]] for it in v)
    p = os.path.join(base, "shoreline_seed7_city.json")
    if os.path.isfile(p):
        sc = json.load(open(p)).get("scatter") or {}
        for g in ("dune_grass", "scrub"):
            for m, v in (sc.get(g) or {}).items():
                veg.setdefault(m if V.is_veg(m) else "VEG_" + m, []).extend([it[1] * 100, it[0] * 100] for it in v)
    return veg


class TodaysMissesRealData(Base):
    @unittest.skipUnless(side_dir(), "seed-7 side files not on this Mac")
    def test_v9_plants_on_roads_fail_v10_filtered_pass(self):
        base = side_dir()
        veg = unfiltered_veg(base)
        r = {x["id"]: x for x in V.run_rules(SPEC, good_dump(base, veg), 7, None, base, "seed7_city")}["veg_on_hard"]
        self.assertFalse(r["ok"])
        self.assertGreater(r["value"], 3500)          # lane P's audit: 3,981 on hard surface before veg_clear
        print("\n  v9-style level (no veg_clear): %s" % r["detail"][:160])
        hs = V.HardSurface.for_dir(base, "seed7_city")
        filt = {k: [p for p in v if not hs.hard_ue(p[0], p[1])] for k, v in veg.items()}
        r = {x["id"]: x for x in V.run_rules(SPEC, good_dump(base, filt), 7, None, base, "seed7_city")}["veg_on_hard"]
        self.assertTrue(r["ok"])
        self.assertEqual(r["value"], 0)

    @unittest.skipUnless(os.path.isfile(REAL_BEACH), "drive_v10_beach_eye.jpg not on this Mac")
    def test_real_beach_frame_unchanged_fails_when_sand_expected(self):
        im = Image.open(REAL_BEACH).convert("RGB")
        golden = self.make_run("g", {"beach_eye": im, "downtown_corner": scene(seed=2), "aerial_city": scene(seed=3)})
        V.check(golden, [], SPEC, self.goldens)
        V.approve(golden, "Kenny", self.goldens)
        rep = V.check(self.make_run("n", {"beach_eye": im, "downtown_corner": scene(seed=2),
                                          "aerial_city": scene(seed=3)}), ["beach_*"], SPEC, self.goldens)
        self.assertEqual(self.cam(rep, "beach_eye")["status"], "FAIL")
        a = np.asarray(im).astype(np.float32)
        h = a.shape[0]
        a[int(h * 0.6):] = a[int(h * 0.6):] * np.array([1.08, 1.04, 0.92], np.float32)   # warmer sand
        rep = V.check(self.make_run("n2", {"beach_eye": Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)),
                                           "downtown_corner": scene(seed=2), "aerial_city": scene(seed=3)}),
                      ["beach_*"], SPEC, self.goldens)
        self.assertEqual(self.cam(rep, "beach_eye")["status"], "PASS", self.cam(rep, "beach_eye"))

    @unittest.skipUnless(os.path.isfile(REAL_DUMP_V10), "lane P's v10 level dump not on this Mac")
    def test_spec_rules_on_lane_p_v10_dump(self):
        spec = json.load(open(os.path.join(HERE, "visual_cams.json")))
        res = V.run_rules(spec, json.load(open(REAL_DUMP_V10)), 7, None, None, "seed7_city", ["pack"])
        bad = [r["id"] for r in res if not r["ok"]]
        self.assertEqual(bad, ["veg_on_hard"])        # that dump has no positions: only the new capture has them


class Spec(unittest.TestCase):
    def test_camera_spec(self):
        spec = json.load(open(os.path.join(HERE, "visual_cams.json")))
        cams = spec["cameras"]
        names = [c["name"] for c in cams]
        self.assertEqual(len(names), len(set(names)))
        s7 = [c for c in cams if c["seed"] == 7]
        self.assertGreaterEqual(len(s7), 20)
        self.assertGreaterEqual(sum(1 for c in s7 if "aerial" in c["tags"]), 3)
        for want in ("curved_bend", "downtown_corner", "skewed_junction_eye", "empty_lot", "driveway",
                     "stop_approach", "bridge_deck", "beach_eye", "beach_dunes", "beach_air", "beach_carpark",
                     "county_ditch", "farm_belt"):
            self.assertIn(want, names)
        self.assertTrue(any(c["seed"] == 17 and "garage" in c["tags"] for c in cams))
        for c in cams:
            self.assertEqual(len(c["loc_ue"]), 3)
            self.assertTrue(-90 <= c["pitch"] <= 90)


if __name__ == "__main__":
    unittest.main(verbosity=1)
