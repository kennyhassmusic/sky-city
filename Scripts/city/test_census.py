"""Plan checks for the city census. Topology counts need Blender.

Run: python3 -I Scripts/city/test_census.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census


def _box(z0, z1, x0=0.0, x1=8.0, y0=0.0, y1=6.0):
    return [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]


def _spec(height=10.0, roof_h=1.0):
    return {
        "id": "b",
        "height": height,
        "parapet_m": 1.1,
        "footprint": [[0, 0], [8, 0], [8, 6], [0, 6]],
        "roof": {"h": roof_h},
    }


class TestCensus(unittest.TestCase):
    def test_a_mass_on_the_sidewalk_passes(self):
        ground = 0.15
        deck, _roof = census.expected_deck(_spec(), ground)
        report = census.check_dimensions(_box(ground, deck), _spec(), ground)
        self.assertEqual(report["reasons"], [])

    def test_a_floating_base_fails(self):
        ground = 0.15
        deck, _roof = census.expected_deck(_spec(), ground)
        report = census.check_dimensions(_box(ground + 1.5, deck + 1.5), _spec(), ground)
        self.assertTrue(any(reason.startswith("base") for reason in report["reasons"]))

    def test_a_short_mass_fails(self):
        ground = 0.15
        report = census.check_dimensions(_box(ground, ground + 2.0), _spec(), ground)
        self.assertTrue(any(reason.startswith("height short") for reason in report["reasons"]))

    def test_a_wide_footprint_fails(self):
        ground = 0.15
        deck, _roof = census.expected_deck(_spec(), ground)
        report = census.check_dimensions(_box(ground, deck, x1=14.0), _spec(), ground)
        self.assertTrue(any(reason.startswith("footprint") for reason in report["reasons"]))


if __name__ == "__main__":
    unittest.main()
