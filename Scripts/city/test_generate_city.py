"""The mashup seeder plus district mix, income tiers, and streetscape.

Uses a tiny plan so it does not need the LFS city files.
Run: python3 -I Scripts/city/test_generate_city.py
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_city
import import_city_ue
import kit_layout
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


class RegionCropTest(unittest.TestCase):
    RECT = [10, 10, 100, 50]

    def _crop(self):
        plan, buildings = _plan()
        plan["roads"].append({"cls": "major", "city": "austin", "pts": [[30, 20], [60, 20]]})
        buildings["buildings"].append(
            {"x": 60, "y": 30, "yaw": 0, "w": 10, "d": 10, "h": 9, "district": "austin_dt", "style": "tower"})
        return plan, buildings, generate_city.crop_inputs(plan, buildings, "chicago_loop", rect=self.RECT)

    def test_keeps_only_inside_and_own_city(self):
        plan, buildings, (cplan, cbuild) = self._crop()
        self.assertEqual(cplan["bounds"], [10.0, 10.0, 100.0, 50.0])
        rows = cbuild["buildings"]
        self.assertEqual([(r["x"], r["y"]) for r in rows], [(50, 24), (90, 24)])
        self.assertEqual(cplan["landmarks"], [])
        for road in cplan["roads"]:
            self.assertNotEqual(road.get("city"), "austin")
            for x, y in road["pts"]:
                self.assertTrue(10 <= x <= 100 and 10 <= y <= 50, (x, y))
        # the minor road x=20 from y=0..70 is clipped to y=10..50
        self.assertIn([[20.0, 10.0], [20.0, 50.0]], [road["pts"] for road in cplan["roads"]])
        # inputs untouched
        self.assertEqual(len(buildings["buildings"]), 5)
        self.assertEqual(plan["bounds"], [0, 0, 160, 100])

    def test_clip_polyline_splits_runs(self):
        runs = generate_city.clip_polyline([[0, 20], [50, 20], [50, 80], [80, 80], [80, 20], [120, 20]], self.RECT)
        self.assertEqual(runs, [[[10.0, 20.0], [50.0, 20.0], [50.0, 50.0]], [[80.0, 50.0], [80.0, 20.0], [100.0, 20.0]]])
        self.assertEqual(generate_city.clip_polyline([[0, 0], [5, 60]], self.RECT), [])

    def test_region_rect_is_loop_sized_and_in_frame(self):
        x0, y0, x1, y1 = generate_city.region_rect("chicago_loop")
        area_km2 = (x1 - x0) * (y1 - y0) / 1e6
        self.assertTrue(1.0 <= area_km2 <= 2.0, area_km2)
        # State Street bridge is the plan origin; the Loop lies south of it, Willis Tower inside
        self.assertTrue(x0 < 0 < x1 and y1 < 0)
        wx, wy = generate_city.latlon_to_plan(41.8789, -87.6359)
        self.assertTrue(x0 <= wx <= x1 and y0 <= wy <= y1)
        with self.assertRaises(ValueError):
            generate_city.region_rect("nowhere")

    def test_cropped_city_is_deterministic_and_spawn_names_region(self):
        _, _, (cplan, cbuild) = self._crop()
        first = generate_city.build_city(cplan, cbuild, cplan["landmarks"], seed=7)
        second = generate_city.build_city(cplan, cbuild, cplan["landmarks"], seed=7)
        self.assertEqual(model_mod.manifest_hash(first), model_mod.manifest_hash(second))
        first["region"] = "chicago_loop"
        spawn = generate_city.spawn_document(first)
        self.assertEqual(spawn["level"], "/Game/Maps/SkyCityChicagoGen")
        self.assertEqual(spawn["folder"], "/Game/City/Generated/Chicago")
        self.assertEqual(spawn["region"], "chicago_loop")
        self.assertEqual(generate_city.spawn_name("chicago_loop"), "sky_city_spawn_chicago_loop.json")
        self.assertEqual(generate_city.spawn_name(), "sky_city_spawn.json")


class ImportArgsTest(unittest.TestCase):
    def test_defaults_are_the_old_behaviour(self):
        run = import_city_ue.resolve(import_city_ue.parse_args(["--spawn", "/nonexistent.json"]))
        self.assertEqual(run["level"], "/Game/Maps/SkyCityGenerated")
        self.assertEqual(run["folder"], "/Game/City/Generated")
        self.assertTrue(run["glbs"].endswith("SourceArt/CityGen/city"))
        self.assertTrue(run["collision"])

    def test_glb_folder_and_level_args(self):
        args = import_city_ue.parse_args(["--glbs", "SourceArt/CityGen/chicago", "--level", "/Game/Maps/SkyCityChicagoGen",
                                          "--spawn", "/nonexistent.json", "--no-collision"])
        run = import_city_ue.resolve(args)
        self.assertEqual(run["level"], "/Game/Maps/SkyCityChicagoGen")
        self.assertEqual(run["label"], "SkyCityChicagoGen")
        self.assertTrue(run["glbs"].endswith("SourceArt/CityGen/chicago"))
        self.assertTrue(os.path.isabs(run["glbs"]))
        self.assertFalse(run["collision"])

    def test_spawn_record_names_level_and_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "spawn.json")
            with open(path, "w") as handle:
                json.dump({"level": "/Game/Maps/SkyCityChicagoGen", "folder": "/Game/City/Generated/Chicago"}, handle)
            run = import_city_ue.resolve(import_city_ue.parse_args(["--spawn", path]))
        self.assertEqual(run["level"], "/Game/Maps/SkyCityChicagoGen")
        self.assertEqual(run["folder"], "/Game/City/Generated/Chicago")

    def test_kit_mode_takes_only_street_tiles(self):
        glbs = ["/x/CG_chicago_loop_core_00.glb", "/x/CG_chicago_loop_core_street_1_2_00.glb", "/x/CG_chicago_loop_res_00.glb"]
        baked = import_city_ue.resolve(import_city_ue.parse_args(["--spawn", "/nonexistent.json"]))
        self.assertEqual(baked["buildings"], "baked")
        self.assertEqual(import_city_ue.select_glbs(glbs, baked), glbs)
        kit = import_city_ue.resolve(import_city_ue.parse_args(["--spawn", "/nonexistent.json", "--buildings", "kit",
                                                                "--ids", "a,b"]))
        self.assertEqual(import_city_ue.select_glbs(glbs, kit), [glbs[1]])
        self.assertEqual(kit["ids"], {"a", "b"})
        self.assertTrue(kit["kit"].endswith("SourceArt/CityGen/kit"))
        self.assertTrue(kit["layout"].endswith("Saved/CityGen/kit_layout_city.json"))
        bare = import_city_ue.resolve(import_city_ue.parse_args(["--spawn", "/nonexistent.json", "--buildings", "kit",
                                                                 "--no-streets"]))
        self.assertEqual(import_city_ue.select_glbs(glbs, bare), [])

    def test_player_start_on_longest_major_street(self):
        document = {"roads": [
            {"cls": "minor", "pts": [[0, 0], [400, 0]]},
            {"cls": "major", "pts": [[10, 10], [10, 110], [10, 310]]},
        ]}
        (x, y, z), (_, _, yaw) = import_city_ue._start_on_street(document)
        self.assertEqual((x, y, z), (6000.0, 1000.0, 150.0))  # UE X = plan y * 100, Y = plan x * 100
        self.assertAlmostEqual(yaw, 0.0)  # plan north is UE +X


class MassingPlanTest(unittest.TestCase):
    def test_unmeshed_buildings_and_far_roads(self):
        document = {
            "buildings": [
                {"kind": "building", "id": "a", "x": 0, "y": 0, "w": 20, "d": 20},
                {"kind": "building", "id": "b", "x": 400, "y": 0, "w": 20, "d": 20},
                {"kind": "landmark", "id": "willis", "x": 10, "y": 10},
            ],
            "roads": [
                {"id": "near", "pts": [[-60, 0], [60, 0]]},
                {"id": "far", "pts": [[300, 100], [500, 100]]},
            ],
        }
        todo, roads = import_city_ue.massing_plan(document, {"a"})
        self.assertEqual([item["id"] for item in todo], ["b"])
        self.assertEqual([road["id"] for road in roads], ["far"])
        todo, roads = import_city_ue.massing_plan(document, set())
        self.assertEqual(len(todo), 2)
        self.assertEqual(len(roads), 2)


class KitLayoutTest(unittest.TestCase):
    """Facade kit: the mesher's pane fit, inward-facing instances, one collision box per tier."""

    @classmethod
    def setUpClass(cls):
        plan, buildings = _plan()
        cls.city = generate_city.build_city(plan, buildings, plan["landmarks"])
        cls.specs = [spec for spec in cls.city["buildings"] if spec.get("facades") and spec.get("role") != "landmark"]

    def test_layout_is_deterministic_and_covers_every_building(self):
        one = kit_layout.build_layout(self.city).document("test")
        two = kit_layout.build_layout(self.city).document("test")
        self.assertEqual(json.dumps(one, sort_keys=True), json.dumps(two, sort_keys=True))
        self.assertEqual(one["buildings"], len(self.specs))
        self.assertGreater(one["counts"].get("KIT_Pane|lit", 0) + one["counts"].get("KIT_Pane|dark", 0)
                           + one["counts"].get("KIT_PaneCurtain|lit", 0) + one["counts"].get("KIT_PaneCurtain|dark", 0), 0)
        for key in one["groups"]:
            self.assertIn(key.split("|")[0], kit_layout.MODULES)

    def test_runs_fill_each_facade_and_point_inward(self):
        for spec in self.specs:
            for facade in spec["facades"]:
                layout = kit_layout.Layout()
                kit_layout.facade_record(layout, spec, facade)
                if not layout.groups:
                    continue
                length = float(facade["length"])
                # Corners, piers and panes tile the edge; a solid edge is one span of the whole length.
                along = sum(item[4] for key, items in layout.groups.items()
                            if key.split("|")[0] in ("KIT_Corner", "KIT_Pier", "KIT_Pane", "KIT_PaneCurtain")
                            for item in items)
                if along == 0:
                    along = max(item[4] for items in layout.groups.values() for item in items)
                self.assertAlmostEqual(along, length, delta=0.01)
                inward = (-float(facade["normal"][0]), -float(facade["normal"][1]))
                inward_ue = (inward[1], inward[0])
                for items in layout.groups.values():
                    for item in items:
                        ly = kit_layout._local_y(item[3])
                        self.assertGreater(ly[0] * inward_ue[0] + ly[1] * inward_ue[1], 0.99)
                        self.assertTrue(all(value > 0 for value in item[4:]))

    def test_one_collision_box_per_tier_on_the_footprint(self):
        layout = kit_layout.build_layout(self.city)
        tiers = sum(len(kit_layout.tiers(spec)) for spec in self.specs)
        boxes = layout.groups[kit_layout.COLLISION]
        self.assertEqual(len(boxes), tiers)
        spec = self.specs[0]
        poly, z0, z1 = kit_layout.tiers(spec)[0]
        box = kit_layout.build_layout(self.city, {spec["id"]}).groups[kit_layout.COLLISION][0]
        area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1]))) / 2.0
        self.assertAlmostEqual(box[4] * box[5], area, delta=area * 0.02)
        self.assertAlmostEqual(box[2], 0.0)  # the ground tier's box starts at the street

    def test_dressing_follows_the_mesher(self):
        spec = self.specs[0]
        facade = spec["facades"][0]
        for bay in range(4):
            lit, leaf = kit_layout.dressing(spec, facade, bay, 1.6)
            self.assertEqual((lit, leaf), kit_layout.dressing(spec, facade, bay, 1.6))
            if leaf:
                mat, along, width, inset = leaf
                self.assertTrue(mat.startswith("M_Blind") or mat.startswith("M_Curtain"))
                self.assertLessEqual(along + width, 1.6 + 1e-6)


if __name__ == "__main__":
    unittest.main()
