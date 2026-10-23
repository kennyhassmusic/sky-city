"""Texel density and window aspect for the city meshes.

Run: python3 -I Scripts/city/test_face_uv.py
A stretched face or a wide window fails. The city GLBs are checked when they exist.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import face_uv


class TestLayout(unittest.TestCase):
    def test_uniform_metres_keeps_a_square_scan_square(self):
        mu, mv = face_uv.uniform_metres(3.0, 1.0, 1024, 1024)
        self.assertAlmostEqual(mu, mv)

    def test_fit_bays_holds_aspect_and_length(self):
        aspect = face_uv.WINDOW_ASPECT
        for length in (0.5, 4.0, 8.2, 11.0, 22.5, 40.0):
            lay = face_uv.fit_bays(length, 3.45, 0.46, aspect, 1.4)
            self.assertAlmostEqual(lay["ww"] / lay["wh"], aspect, places=6)
            total = lay["count"] * lay["ww"] + 2.0 * lay["end"] + (lay["count"] - 1) * lay["pier"]
            self.assertAlmostEqual(total, max(0.3, length), places=4)

    def test_uniform_quad_passes_and_a_stretched_one_fails(self):
        scans = {"M_Brick": (1024, 1024, 3.0, 3.0)}
        points = [(0, 0, 0), (6, 0, 0), (6, 0, 3), (0, 0, 3)]
        good = face_uv.new_sink()
        face_uv.consider_polygon(points, [(0, 0), (2, 0), (2, 1), (0, 1)], "M_Brick", scans, good)
        self.assertGreater(good["density_n"], 0)
        self.assertEqual(good["density_fail"], 0)
        bad = face_uv.new_sink()
        face_uv.consider_polygon(points, [(0, 0), (2, 0), (2, 0.5), (0, 0.5)], "M_Brick", scans, bad)
        self.assertGreater(bad["density_fail"], 0)

    def test_window_aspect_matches_the_source_rect(self):
        aspect = face_uv.WINDOW_ASPECT
        width, height = 1.6 * aspect, 1.6
        points = [(0, 0, 0), (width, 0, 0), (width, 0, height), (0, 0, height)]
        scans = {}
        good = face_uv.new_sink()
        face_uv.consider_polygon(points, None, "M_Glass", scans, good)
        self.assertGreater(good["window_n"], 0)
        self.assertEqual(good["window_fail"], 0)
        wide = face_uv.new_sink()
        stretched = [(0, 0, 0), (width * 2, 0, 0), (width * 2, 0, height), (0, 0, height)]
        face_uv.consider_polygon(stretched, None, "M_Glass", scans, wide)
        self.assertGreater(wide["window_fail"], 0)


class TestExported(unittest.TestCase):
    def test_city_buildings(self):
        folder = os.path.join(face_uv.project_root(), "SourceArt", "CityGen", "city")
        if not face_uv.building_glbs(folder):
            self.skipTest("no exported buildings")
        sink = face_uv.check_folder(folder)
        report = face_uv.format_report(sink, 10)
        print(report)
        self.assertTrue(face_uv.passed(sink), report)


if __name__ == "__main__":
    unittest.main()
