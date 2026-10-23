"""The mashup seeder plus district mix, income tiers, and streetscape.

Uses a tiny plan so it does not need the LFS city files.
Run: python3 -I Scripts/city/test_generate_city.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_city
import model as model_mod


def _plan():
    plan = {
        "bounds": [0, 0, 160, 100],
        "roads": [
            {"cls": "major", "pts": [[0, 0], [140, 0]]},
            {"cls": "major", "pts": [[0, 0], [0, 80]]},
            {"cls": "minor", "pts": [[20, 0], [20, 70]]},
            {"cls": "ped", "pts": [[10, 10], [40, 10]]},
        ],
        "landmarks": [{"name": "Test Tower", "pos": [8, 8], "h": 40}],
    }
    buildings = {"buildings": [
        {"x": 50, "y": 24, "yaw": 0, "w": 28, "d": 20, "h": 36, "district": "chicago_core", "style": "tower"},
        {"x": 90, "y": 24, "yaw": 0, "w": 22, "d": 16, "h": 18, "district": "chicago_core", "style": "tower"},
        {"x": 40, "y": 60, "yaw": 0, "w": 16, "d": 14, "h": 7, "district": "austin_low", "style": "lowrise"},
        {"x": 70, "y": 60, "yaw": 90, "w": 18, "d": 12, "h": 8, "district": "austin_low", "style": "lowrise"},
    ]}
    return plan, buildings


class GenerateCityTest(unittest.TestCase):
    def test_seed_mix_streetscape_and_spawn_frame(self):
        plan, buildings = _plan()
        first = generate_city.build_city(plan, buildings, plan["landmarks"], seed=7)
        second = generate_city.build_city(plan, buildings, plan["landmarks"], seed=7)
        self.assertEqual(model_mod.manifest_hash(first), model_mod.manifest_hash(second))
        self.assertEqual(first["seed"], 7)
        classes = {road["cls"] for road in first["roads"]}
        self.assertNotIn("ped", classes)
        types = {lot.get("district_type") for lot in first["lots"]}
        self.assertTrue(types & {"tech", "eclectic_mix", "apartments_condos", "houses"})
        low = [lot for lot in first["lots"] if lot.get("district_type") in ("houses", "apartments_condos")]
        if low:
            self.assertTrue(any(lot.get("tier") for lot in low))
        surfaces = first["streetscape"]["surfaces"]
        self.assertTrue(surfaces["asphalt"])
        self.assertTrue(surfaces["sidewalk"])
        self.assertTrue(any(curb.get("kind") == "straight" for curb in first["streetscape"]["curb_paths"]))
        props = {prop["kind"] for prop in first["streetscape"]["props"]}
        self.assertIn("lamp", props)
        self.assertTrue(props & {"signal", "stop", "yield", "street_name"})
        spawn = generate_city.spawn_document(first)
        self.assertEqual(spawn["level"], "/Game/Maps/SkyCityGenerated")
        self.assertEqual(spawn["folder"], "/Game/City/Generated")
        self.assertNotIn("ped", {road["cls"] for road in spawn["roads"]})
        block = next(item for item in spawn["buildings"] if item["kind"] == "building")
        self.assertEqual(block["ue"][0], round(block["y"] * 100.0, 1))
        self.assertEqual(block["ue"][1], round(block["x"] * 100.0, 1))
        self.assertEqual(generate_city._ue_yaw(0), 90.0)
        self.assertTrue(any(item["kind"] == "landmark" for item in spawn["buildings"]))
        self.assertIn("sidewalk", surfaces)


if __name__ == "__main__":
    unittest.main()
