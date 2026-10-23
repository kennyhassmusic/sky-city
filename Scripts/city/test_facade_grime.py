"""Wear and drip-band checks for the facade grime. No Unreal, no Blender.

Run: python3 -I Scripts/city/test_facade_grime.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import districts as district_types
import facade_grime
import skyline


class FacadeGrimeTest(unittest.TestCase):
    def test_recipe_wear_tracks_age_and_tier(self):
        types = district_types.table(skyline.load())
        brand = facade_grime.intensity({"wear": types["brand_new"]["wear"], "district_type": "brand_new"})
        tech = facade_grime.intensity({"wear": types["tech"]["wear"], "district_type": "tech"})
        old = facade_grime.intensity({"wear": types["historic_old"]["wear"], "district_type": "historic_old"})
        high = facade_grime.intensity({"wear": types["houses"]["income_tiers"]["high"]["wear"], "tier": "high"})
        poor = facade_grime.intensity({
            "wear": types["houses"]["income_tiers"]["distressed"]["wear"],
            "tier": "distressed",
        })
        apt_high = facade_grime.intensity({
            "wear": types["apartments_condos"]["income_tiers"]["high"]["wear"],
            "tier": "high",
        })
        apt_poor = facade_grime.intensity({
            "wear": types["apartments_condos"]["income_tiers"]["distressed"]["wear"],
            "tier": "distressed",
        })
        self.assertLess(brand, 0.1)
        self.assertLess(tech, 0.1)
        self.assertGreater(old, 0.7)
        self.assertLess(high, 0.1)
        self.assertGreater(poor, 0.85)
        self.assertGreater(poor, old)
        self.assertGreater(poor, high)
        self.assertLess(apt_high, 0.1)
        self.assertGreater(apt_poor, 0.85)
        self.assertGreater(apt_poor, apt_high)

    def test_fallback_matches_the_district_recipe(self):
        types = district_types.table(skyline.load())
        for name in ("brand_new", "tech", "historic_old", "green_renewable", "industrial_commercial"):
            self.assertAlmostEqual(
                facade_grime.intensity({"district_type": name}),
                float(types[name]["wear"]),
            )
        self.assertLess(facade_grime.intensity({"tier": "high"}), 0.1)
        self.assertGreater(facade_grime.intensity({"tier": "distressed"}), 0.85)
        self.assertGreater(
            facade_grime.intensity({"tier": "distressed"}),
            facade_grime.intensity({"tier": "high"}),
        )

    def test_style_fallback_for_an_untyped_preview(self):
        self.assertLess(facade_grime.intensity({"style": "glass_curtain"}), 0.1)
        self.assertLess(facade_grime.intensity({"style": "modern_mixed"}), 0.1)
        self.assertGreater(facade_grime.intensity({"style": "prewar_masonry"}), 0.7)
        # An explicit wear, including a clean one, wins over the style.
        self.assertAlmostEqual(
            facade_grime.intensity({"style": "prewar_masonry", "wear": 0.05}),
            0.05,
        )

    def test_wear_is_clamped(self):
        self.assertEqual(facade_grime.intensity({"wear": -2}), 0.0)
        self.assertEqual(facade_grime.intensity({"wear": 4}), 1.0)
        self.assertAlmostEqual(facade_grime.intensity({}), 0.35)

    def test_drips_sit_under_sills_and_ledges_not_on_the_glass(self):
        ground = facade_grime.GROUND_Z
        floor_h = facade_grime.FLOOR_H
        sill_z = ground + facade_grime.SILL_PEAK * floor_h
        below = ground + (facade_grime.SILL_PEAK - facade_grime.SILL_FADE) * floor_h
        glass_z = ground + 0.70 * floor_h
        ledge_z = ground + facade_grime.LEDGE_PEAK * floor_h
        self.assertAlmostEqual(facade_grime.drip_weight(sill_z), 1.0, places=2)
        self.assertAlmostEqual(facade_grime.drip_weight(below), 0.0, places=2)
        self.assertLess(facade_grime.drip_weight(glass_z), 0.05)
        self.assertAlmostEqual(facade_grime.drip_weight(ledge_z), 1.0, places=2)
        # The next floor repeats the sill band.
        self.assertAlmostEqual(facade_grime.drip_weight(sill_z + floor_h), 1.0, places=2)

    def test_dirt_gathers_at_the_base(self):
        self.assertAlmostEqual(facade_grime.base_weight(facade_grime.BASE_Z0), 1.0)
        self.assertAlmostEqual(facade_grime.base_weight(facade_grime.BASE_Z1), 0.0)
        self.assertEqual(facade_grime.base_weight(10.0), 0.0)
        self.assertGreater(facade_grime.base_weight(0.4), facade_grime.base_weight(1.2))


if __name__ == "__main__":
    unittest.main()
