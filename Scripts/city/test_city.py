"""City model, grammar, streets and regeneration. No Unreal, no Blender.

Run: python3 -I Scripts/city/test_city.py
"""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import block
import geom
import grammar
import lots as lots_mod
import model as model_mod
import network
import operations as ops
import schema
import seeder
import skyline
import streets
import yaml_lite


def _square_lot(ident="lot_a", size=24):
    h = size / 2.0
    return {
        "id": ident,
        "polygon": [[-h, -h], [h, -h], [h, h], [-h, h]],
        "front_normals": [[0.0, -1.0]],
        "role": "lot",
        "district_id": "d",
        "tags": {},
    }


def _sky(**over):
    base = {
        "base_height_m": 30, "edge_height_m": 12, "falloff": "smoothstep",
        "reach_m": 0, "coverage": 1, "far": 0, "noise_amplitude_m": 0,
        "hero_count": 0, "hero_height_rank_m": [80], "hero_anchor": [0, 0],
        "centre": [0, 0],
        "silhouette": {"origin": [0, 0], "axis": [1, 0], "length": 1, "samples": [200], "mode": "soft_max"},
    }
    base.update(over)
    return base


class YamlTest(unittest.TestCase):
    def test_skyline_and_grammar_load(self):
        sky = skyline.load()
        self.assertEqual(sky["version"], 1)
        self.assertEqual(len(sky["variations"]), 4)
        styles = grammar.load_styles()
        self.assertEqual(len(styles), 7)
        text = Path(sky["_path"]).read_text()
        self.assertEqual(yaml_lite.loads(text)["seed"], sky["seed"])


class GrammarTest(unittest.TestCase):
    def test_deterministic(self):
        lot = _square_lot()
        sky = _sky()
        a = grammar.evaluate(lot, "prewar_masonry", sky, 1408)
        b = grammar.evaluate(lot, "prewar_masonry", sky, 1408)
        self.assertEqual(a, b)

    def test_osm_height_and_levels(self):
        lot = _square_lot()
        lot["tags"] = {"height": 41}
        spec = grammar.evaluate(lot, "prewar_masonry", _sky(base_height_m=10), 1)
        self.assertEqual(spec["target_height"], 41.0)
        lot["tags"] = {"building:levels": 5}
        spec = grammar.evaluate(lot, "prewar_masonry", _sky(), 1)
        self.assertAlmostEqual(spec["target_height"], 5 * 3.45, places=2)

    def test_roof_shape_tag(self):
        lot = _square_lot()
        lot["tags"] = {"roof:shape": "pyramidal"}
        self.assertEqual(grammar.evaluate(lot, "prewar_masonry", _sky(), 1)["roof"]["shape"], "pyramidal")
        lot["tags"] = {"roof:shape": "dome"}
        self.assertEqual(grammar.evaluate(lot, "prewar_masonry", _sky(), 1)["roof"]["shape"], "dome")

    def test_recess_and_massing(self):
        styles = grammar.load_styles()
        self.assertGreater(styles["prewar_masonry"]["recess_m"], 0.05)
        self.assertGreater(styles["glass_curtain"]["recess_m"], 0.05)
        tall = _sky()
        deco = grammar.evaluate(_square_lot("deco", 40), "art_deco", tall, 1)
        self.assertGreater(deco["floors"][6]["inset"], deco["floors"][0]["inset"])
        glass = grammar.evaluate(_square_lot("gl", 40), "glass_curtain", {**tall, "base_height_m": 80}, 1)
        self.assertEqual(glass["floors"][0]["inset"], 0.0)
        self.assertGreater(glass["floors"][4]["inset"], 3.0)

    def test_low_styles_cap_and_roof(self):
        sky = _sky(base_height_m=80)
        walk = grammar.evaluate(_square_lot(), "brick_walkup", sky, 1)
        self.assertLessEqual(len(walk["floors"]), 4)
        self.assertEqual(walk["roof"]["shape"], "gabled")
        ind = grammar.evaluate(_square_lot(), "industrial", sky, 1)
        self.assertLessEqual(len(ind["floors"]), 4)
        self.assertEqual(ind["roof"]["shape"], "gabled")
        texas = grammar.evaluate(_square_lot(), "texas_lowrise", sky, 1)
        self.assertLessEqual(len(texas["floors"]), 3)
        self.assertEqual(texas["roof"]["shape"], "hipped")

    def test_far_clips_a_normal_building_and_not_a_hero(self):
        lot = _square_lot("far", 30)
        sky = _sky(base_height_m=90, far=1.2)
        normal = grammar.evaluate(lot, "prewar_masonry", sky, 1)
        hero = dict(lot)
        hero["hero"] = True
        hero["hero_rank"] = 0
        tall = grammar.evaluate(hero, "prewar_masonry", {**sky, "hero_height_rank_m": [90]}, 1)
        self.assertLess(len(normal["floors"]), len(tall["floors"]))

    def test_coverage_shrinks_the_footprint(self):
        lot = _square_lot("cov", 30)
        full = grammar.evaluate(lot, "prewar_masonry", _sky(coverage=1), 1)
        half = grammar.evaluate(lot, "prewar_masonry", _sky(coverage=0.5), 1)
        self.assertLess(abs(geom.poly_area(half["footprint"])), abs(geom.poly_area(full["footprint"])) * 0.7)

    def test_soft_max_eases_instead_of_slicing(self):
        lot = _square_lot()
        sky = _sky(base_height_m=100, silhouette={
            "origin": [0, 0], "axis": [1, 0], "length": 1, "samples": [40], "mode": "soft_max",
        })
        h = grammar.target_height(lot, sky, 1, grammar.load_styles()["prewar_masonry"])
        self.assertLess(h, 100)
        self.assertGreater(h, 40)

    def test_front_is_a_storefront_and_the_back_is_an_alley(self):
        spec = grammar.evaluate(_square_lot(), "prewar_masonry", _sky(), 1)
        ground = [f for f in spec["facades"] if f["floor"] == 0]
        fronts = [f for f in ground if f["role"] == "front"]
        backs = [f for f in ground if f["role"] == "back"]
        self.assertTrue(fronts)
        self.assertTrue(all(f["opening"] == "storefront" and f["door"] for f in fronts))
        self.assertTrue(backs)
        self.assertTrue(all(f["opening"] == "alley" for f in backs))
        self.assertTrue(all(f["opening_w"] > 0.3 for f in spec["facades"]))


class NetworkTest(unittest.TestCase):
    def test_crossing_splits_into_four(self):
        roads = [
            {"id": "h", "polyline": [[0, 0], [10, 0]], "cls": "minor", "lanes": 1, "oneway": False, "core": False},
            {"id": "v", "polyline": [[5, -5], [5, 5]], "cls": "minor", "lanes": 1, "oneway": False, "core": False},
        ]
        edges = network.node_roads(roads)
        self.assertEqual(len(edges), 4)

    def test_rectangle_is_one_face(self):
        roads = _loop(0, 0, 100, 80)
        faces = network.faces(network.node_roads(roads))
        self.assertEqual(len(faces), 1)
        self.assertGreater(faces[0]["area"], 0)
        self.assertEqual(len(faces[0]["polygon"]), len(faces[0]["edges"]))

    def test_splitter_makes_two_faces(self):
        roads = _loop(0, 0, 200, 80)
        roads.append({"id": "mid", "polyline": [[100, 0], [100, 80]], "cls": "minor", "lanes": 1,
                      "oneway": False, "core": False, "name": "mid"})
        faces = network.faces(network.node_roads(roads))
        self.assertEqual(len(faces), 2)


class LotsTest(unittest.TestCase):
    def test_rows_alley_and_corners(self):
        poly = [[0, 0], [100, 0], [100, 70], [0, 70]]
        made = lots_mod.subdivide(poly, seed=1408)
        self.assertIsNotNone(made["alley"])
        tags = {lot["tag"][0] for lot in made["lots"]}
        self.assertEqual(tags, {"s", "n"})
        corners = [lot for lot in made["lots"] if len(lot["front_normals"]) == 2]
        self.assertGreaterEqual(len(corners), 4)
        area = sum(abs(geom.poly_area(lot["polygon"])) for lot in made["lots"])
        area += abs(geom.poly_area(made["alley"]))
        self.assertAlmostEqual(area, 100 * 70, delta=80)
        # seed 1408 is even: the north row is not staggered, so the cuts match
        south = sorted(lot["polygon"] for lot in made["lots"] if lot["tag"].startswith("s"))
        widths = []
        for poly in south:
            xs = [p[0] for p in poly]
            widths.append(round(max(xs) - min(xs), 2))
        self.assertEqual(len(set(widths)), 1)

    def test_non_rectangle_still_yields_a_lot(self):
        made = lots_mod.subdivide([[0, 0], [30, 0], [10, 20]], seed=1)
        self.assertGreaterEqual(len(made["lots"]), 1)
        self.assertIsNone(made["alley"])


class RegenTest(unittest.TestCase):
    def _grid(self):
        city = model_mod.new_model([-20, -20, 230, 100], 1408)
        city, _ = ops.add_district(
            city, [[-10, -10], [100, -10], [100, 90], [-10, 90]],
            character="downtown", name="West", district_id="d_west",
            skyline_overrides={"hero_count": 0, "noise_amplitude_m": 0, "base_height_m": 20,
                               "reach_m": 0, "far": 40, "coverage": 0.85,
                               "silhouette": {"samples": [200], "mode": "soft_max",
                                              "origin": [0, 0], "axis": [1, 0], "length": 1}},
        )
        city, _ = ops.add_district(
            city, [[100, -10], [210, -10], [210, 90], [100, 90]],
            character="residential", name="East", district_id="d_east",
            skyline_overrides={"hero_count": 0, "noise_amplitude_m": 0, "base_height_m": 11,
                               "reach_m": 0, "far": 4, "coverage": 0.6,
                               "silhouette": {"samples": [80], "mode": "soft_max",
                                              "origin": [0, 0], "axis": [1, 0], "length": 1}},
        )
        roads = [
            ("h0", [[0, 0], [200, 0]], "major", 2, False, True),
            ("h1", [[200, 80], [0, 80]], "mid", 2, False, False),
            ("v0", [[0, 80], [0, 0]], "minor", 1, True, True),
            ("v1", [[100, 0], [100, 80]], "minor", 1, False, False),
            ("v2", [[200, 0], [200, 80]], "minor", 1, False, False),
        ]
        for ident, pts, cls, lanes, oneway, core in roads:
            district = "d_west" if pts[0][0] < 150 else "d_east"
            city, _ = ops.draw_road(city, pts, cls=cls, lanes=lanes, oneway=oneway, core=core,
                                    district_id=district, road_id=ident, name=ident)
        city, _ = ops.regenerate(city, "blocks")
        return city

    def test_grid_has_streetscape_and_a_stable_hash(self):
        city = self._grid()
        self.assertGreaterEqual(len(city["blocks"]), 2)
        self.assertGreater(len(city["buildings"]), 0)
        sc = city["streetscape"]
        self.assertTrue(sc["surfaces"]["asphalt"])
        self.assertTrue(sc["surfaces"]["gutter"])
        self.assertTrue(sc["surfaces"]["sidewalk"])
        self.assertTrue(sc["surfaces"]["parkway"])
        park_roads = {p["road_id"] for p in sc["surfaces"]["parkway"]}
        self.assertIn("h1", park_roads)
        self.assertNotIn("h0", park_roads)
        h1 = model_mod.manifest_hash(city)
        again, _ = ops.regenerate(city, "blocks")
        self.assertEqual(model_mod.manifest_hash(again), h1)

    def test_lock_keeps_one_building_when_the_skyline_rises(self):
        city = self._grid()
        west = [b for b in city["buildings"] if b.get("district_id") == "d_west" and b.get("role") != "landmark"]
        east_before = copy.deepcopy([b for b in city["buildings"] if b.get("district_id") == "d_east"])
        locked = west[0]
        other = west[1]
        city, _ = ops.lock(city, locked["id"])
        before = copy.deepcopy(next(b for b in city["buildings"] if b["id"] == locked["id"]))
        city, _ = ops.set_skyline(city, "d_west", {"base_height_m": 48})
        city, _ = ops.regenerate(city, "buildings", district_id="d_west")
        after = next(b for b in city["buildings"] if b["id"] == locked["id"])
        self.assertEqual(after, before)
        moved = next(b for b in city["buildings"] if b["id"] == other["id"])
        self.assertNotEqual(moved["height"], other["height"])
        east_after = [b for b in city["buildings"] if b.get("district_id") == "d_east"]
        self.assertEqual(east_after, east_before)

    def test_hand_building_survives_a_style_change(self):
        city = self._grid()
        lot = next(lot for lot in city["lots"] if lot["district_id"] == "d_west")
        city, ids = ops.set_building(city, lot["id"], style="art_deco")
        before = copy.deepcopy(next(b for b in city["buildings"] if b["id"] == ids[0]))
        self.assertEqual(before["source"], "hand")
        city, _ = ops.set_skyline(city, "d_west", {"style": "glass_curtain"})
        city, _ = ops.regenerate(city, "buildings", district_id="d_west")
        after = next(b for b in city["buildings"] if b["id"] == ids[0])
        self.assertEqual(after, before)

    def test_split_is_kept(self):
        city = self._grid()
        parent = next(b for b in city["blocks"] if b["district_id"] == "d_west")
        parent_id = parent["id"]
        city, ids = ops.split_block(city, parent_id, 0.45)
        city, _ = ops.regenerate(city, "blocks")
        have = {b["id"] for b in city["blocks"]}
        self.assertNotIn(parent_id, have)
        self.assertTrue(set(ids) <= have)
        for ident in ids:
            block_ = next(b for b in city["blocks"] if b["id"] == ident)
            self.assertTrue(block_["locked"])
            self.assertEqual(block_["source"], "hand")

    def test_locked_prop_and_screenshot(self):
        city = self._grid()
        prop = city["streetscape"]["props"][0]
        city, _ = ops.lock(city, prop["id"])
        snapshot = model_mod.manifest_hash(city)
        request = ops.screenshot(city, {"name": "street"})
        self.assertEqual(request["op"], "screenshot")
        self.assertEqual(model_mod.manifest_hash(city), snapshot)
        city, _ = ops.regenerate(city, "streetscape")
        found = next(p for p in city["streetscape"]["props"] if p["id"] == prop["id"])
        self.assertTrue(found["locked"])
        self.assertEqual((found["x"], found["y"]), (prop["x"], prop["y"]))
        self.assertEqual(model_mod.manifest_hash(city), snapshot)


class SeederTest(unittest.TestCase):
    def test_landmark_survives_and_pointer_is_refused(self):
        plan = {
            "bounds": [0, 0, 200, 200],
            "roads": [{"id": "r1", "pts": [[0, 10], [80, 10]], "cls": "major", "lanes": 2, "name": "Main"}],
        }
        buildings = {"buildings": [
            {"x": 40, "y": 30, "yaw": 0, "w": 22, "d": 14, "h": 48, "district": "chicago_core", "style": "tower"},
        ]}
        landmarks = [{"name": "River Spire", "pos": [40, 80], "h": 180, "district": "chicago_core"}]
        city = seeder.seed_from_plan(plan, buildings, landmarks, seed=3)
        mark = next(b for b in city["buildings"] if b["role"] == "landmark")
        self.assertTrue(mark["locked"])
        self.assertEqual(mark["source"], "hand")
        city, _ = ops.regenerate(city, "buildings")
        again = next(b for b in city["buildings"] if b["id"] == mark["id"])
        self.assertEqual(again, mark)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            path.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 1\n")
            with self.assertRaises(RuntimeError):
                seeder.read_json(path)

    def test_surveyed_height_survives_a_rebuild(self):
        # The seeder's contract: a measured height is a lot tag, and regenerate
        # honours it instead of inventing a skyline height for that footprint.
        plan = {
            "bounds": [0, 0, 200, 200],
            "districts": [{
                "name": "chicago_core", "id": "d1",
                "polygon": [[-20, -20], [140, -20], [140, 100], [-20, 100]],
            }],
            "roads": [
                {"id": "s", "pts": [[0, 0], [120, 0]], "cls": "major", "lanes": 2, "name": "S", "core": True},
                {"id": "e", "pts": [[120, 0], [120, 80]], "cls": "minor", "lanes": 1, "name": "E", "core": True},
                {"id": "n", "pts": [[120, 80], [0, 80]], "cls": "mid", "lanes": 2, "name": "N"},
                {"id": "w", "pts": [[0, 80], [0, 0]], "cls": "major", "lanes": 2, "name": "W", "core": True},
            ],
        }
        buildings = {"buildings": [
            {"x": 40, "y": 30, "yaw": 0, "w": 22, "d": 16, "h": 77, "district": "chicago_core"},
        ]}
        city = seeder.seed_from_plan(plan, buildings, [], seed=1408)
        city, _ = ops.regenerate(city, "blocks")
        lot = next(item for item in city["lots"] if geom.point_in_poly((40, 30), item["polygon"]))
        self.assertEqual(lot["tags"].get("height"), 77)
        building = next(item for item in city["buildings"] if item.get("lot_id") == lot["id"])
        self.assertEqual(building["target_height"], 77.0)
        self.assertGreater(building["height"], 70.0)
        self.assertLess(building["height"], 85.0)
        others = [item["height"] for item in city["buildings"] if item["id"] != building["id"]]
        self.assertTrue(others)
        self.assertGreater(building["height"], max(others))


class SampleStreetTest(unittest.TestCase):
    def test_loop_block_streetscape(self):
        city = block.build_sample()
        schema.validate(city)
        self.assertEqual(len(city["blocks"]), 1)
        self.assertGreater(len(city["lots"]), 4)
        self.assertTrue(any(b.get("height", 0) > 100 for b in city["buildings"]))
        sc = city["streetscape"]
        roads = {r["id"] for r in city["roads"]}
        for road_id in roads:
            self.assertTrue(any(s["road_id"] == road_id for s in sc["surfaces"]["gutter"]))
            self.assertTrue(any(s["road_id"] == road_id for s in sc["surfaces"]["sidewalk"]))
            self.assertTrue(any(c.get("road_id") == road_id for c in sc["curb_paths"]))
        park = {p["road_id"] for p in sc["surfaces"]["parkway"]}
        self.assertEqual(park, {"road_north"})
        kinds = {c["road_id"]: c["kind"] for c in sc["crosswalks"]}
        self.assertTrue(sc["crosswalks"])
        self.assertEqual(kinds.get("road_east"), "ladder")
        self.assertTrue(sc["ramps"])
        self.assertTrue(any(p["kind"] == "drain" for p in sc["props"]))
        self.assertTrue(any(p["kind"] == "tree" for p in sc["props"]))
        corners = []
        for road in city["roads"]:
            corners.append(tuple(road["polyline"][0]))
            corners.append(tuple(road["polyline"][-1]))
        for prop in sc["props"]:
            if prop["kind"] != "tree":
                continue
            d = min(geom.dist((prop["x"], prop["y"]), c) for c in corners)
            self.assertGreaterEqual(d, 7.0)
        tree_s = {}
        for road in city["roads"]:
            if not road.get("core"):
                continue
            trees = [p for p in sc["props"] if p["kind"] == "tree" and p["road_id"] == road["id"] and p["side"] > 0]
            trees.sort(key=lambda p: p["x"] + p["y"])
            if len(trees) >= 2:
                # core grate spacing is 9 m; allow a metre for the stagger along a straight street
                step = geom.dist((trees[0]["x"], trees[0]["y"]), (trees[1]["x"], trees[1]["y"]))
                tree_s[road["id"]] = step
                self.assertAlmostEqual(step, 9.0, delta=1.2)
        self.assertTrue(tree_s)
        for prop in sc["props"]:
            if prop["kind"] == "drain":
                continue
            road = next(r for r in city["roads"] if r["id"] == prop["road_id"]) if prop.get("road_id") else None
            if road is None:
                continue
            sec = sc["sections"][road["id"]]
            d = _dist_to_centreline(road, (prop["x"], prop["y"]))
            self.assertGreater(d, sec["width"] / 2.0 - 0.05)

    def test_sample_hash_is_stable(self):
        a = model_mod.manifest_hash(block.build_sample())
        b = model_mod.manifest_hash(block.build_sample())
        self.assertEqual(a, b)


def _loop(x0, y0, x1, y1):
    return [
        {"id": "s", "polyline": [[x0, y0], [x1, y0]], "cls": "major", "lanes": 2, "oneway": False, "core": True, "name": "s"},
        {"id": "e", "polyline": [[x1, y0], [x1, y1]], "cls": "minor", "lanes": 1, "oneway": True, "core": True, "name": "e"},
        {"id": "n", "polyline": [[x1, y1], [x0, y1]], "cls": "mid", "lanes": 2, "oneway": False, "core": False, "name": "n"},
        {"id": "w", "polyline": [[x0, y1], [x0, y0]], "cls": "major", "lanes": 2, "oneway": False, "core": True, "name": "w"},
    ]


def _dist_to_centreline(road, p):
    best = 1e9
    pts = road["polyline"]
    for a, b in zip(pts, pts[1:]):
        ab = geom.sub(b, a)
        L2 = geom.dot(ab, ab) or 1e-9
        t = max(0.0, min(1.0, geom.dot(geom.sub(p, a), ab) / L2))
        q = geom.lerp(a, b, t)
        best = min(best, geom.dist(p, q))
    return best


if __name__ == "__main__":
    unittest.main()
