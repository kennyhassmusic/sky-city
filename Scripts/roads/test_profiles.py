"""Curb, gutter and crosswalk profiles.

Run: python3 -I Scripts/roads/test_profiles.py
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import profiles


class ProfilesTest(unittest.TestCase):
    def test_bevel_climbs_outward(self):
        prof = profiles.street_profile("major")
        self.assertTrue(profiles.face_is_bevel(prof))
        # z falls across the pan, then the face rises while x keeps increasing
        self.assertLess(prof[1][1], prof[0][1])
        self.assertGreater(prof[2][0], prof[1][0])
        self.assertGreater(prof[2][1], prof[1][1])

    def test_gutter_drops_toward_the_curb(self):
        prof = profiles.street_profile("minor")
        self.assertLess(prof[1][1], 0.0)
        self.assertAlmostEqual(prof[1][1], -profiles.GUTTER_DROP, places=3)

    def test_carve_preserves_width_and_labels_the_pan(self):
        elems = [["lane", 3.3, -1], ["dy", 0.3, 0], ["lane", 3.3, 1]]
        before = sum(e[1] for e in elems)
        carved, spec = profiles.carve_gutters(elems, "major", False)
        self.assertIsNotNone(spec)
        self.assertAlmostEqual(sum(e[1] for e in carved), before, places=2)
        self.assertEqual(carved[0][0], "gutter")
        self.assertEqual(carved[-1][0], "gutter")
        self.assertEqual(elems[0][0], "lane")

    def test_highway_and_under_have_no_gutter(self):
        elems = [["shoulder", 3.0, 0], ["lane", 3.6, 1], ["shoulder", 3.0, 0]]
        out, spec = profiles.carve_gutters(elems, "highway", False)
        self.assertIsNone(spec)
        self.assertEqual(out, elems)
        out2, spec2 = profiles.carve_gutters([["lane", 3.6, 1], ["lane", 3.6, 1]], "major", True)
        self.assertIsNone(spec2)
        self.assertEqual(len(out2), 2)

    def test_continental_matches_the_roadnet_loop(self):
        span = 12.3
        got = profiles.continental_offsets(span)
        k = -span / 2.0 + 0.6
        expect = []
        while k <= span / 2.0 - 0.5:
            expect.append(round(k, 3))
            k += 1.2
        self.assertEqual(got, expect)
        self.assertGreater(len(got), 3)

    def test_ramp_run_is_twelve_times_the_rise(self):
        ramp = profiles.curb_ramp_spec()
        self.assertAlmostEqual(ramp["run_m"], 0.15 * 12, places=3)
        self.assertAlmostEqual(ramp["rise_m"], 0.15, places=3)

    def test_curb_back_is_positive(self):
        self.assertGreater(profiles.curb_back_from_flow("major"), 0.0)
        self.assertGreater(profiles.curb_back_from_flow("minor"), 0.0)

    def test_preview_minor_oneway_uses_the_wide_lane(self):
        sec = profiles.preview_section("minor", 1, True, True)
        lanes = [e for e in sec["elems"] if e[0] == "lane"]
        self.assertTrue(lanes)
        self.assertAlmostEqual(lanes[0][1], 3.6, places=2)
        again = profiles.preview_section("minor", 1, True, True)
        self.assertAlmostEqual(sec["width"], again["width"], places=2)
        self.assertEqual(sec["elems"][0][0], "gutter")

    def test_parkway_plus_walk_is_the_sidewalk(self):
        sec = profiles.preview_section("mid", 2, False, False)
        self.assertTrue(sec["parkway"])
        self.assertAlmostEqual(sec["parkway_w"] + sec["walk_w"], sec["sidewalk"], places=2)
        core = profiles.preview_section("major", 3, True, True)
        self.assertFalse(core["parkway"])
        self.assertAlmostEqual(core["sidewalk"], profiles.SIDEWALK_CORE, places=2)

    def test_roadnet_source_calls_carve(self):
        src = pathlib.Path(__file__).resolve().parent / "roadnet.py"
        text = src.read_text()
        self.assertIn("carve_gutters(", text)
        self.assertIn("road_profiles", text)


if __name__ == "__main__":
    unittest.main()
