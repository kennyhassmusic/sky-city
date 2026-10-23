"""City model, grammar, streets and regeneration. No Unreal, no Blender.

Run: python3 -I Scripts/city/test_city.py
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import block
import districts as district_types
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

    def test_study_styles_use_four_roofs(self):
        sky = _sky()
        expect = {
            "prewar_masonry": "parapet",
            "glass_curtain": "setback",
            "art_deco": "mansard",
            "modern_mixed": "hipped",
        }
        for style, shape in expect.items():
            spec = grammar.evaluate(_square_lot(style), style, sky, 2)
            self.assertEqual(spec["roof"]["shape"], shape)
            kinds = {k for face in spec["facades"] for k in face.get("bay_kinds") or []}
            self.assertGreater(len(kinds), 1)

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


class RoomTest(unittest.TestCase):
    def _open_bays(self, spec):
        found = []
        for index, face in enumerate(spec["facades"]):
            for bay, kind in enumerate(face.get("bay_kinds") or []):
                if kind != "blind":
                    found.append((index, bay, face["bay_rooms"][bay]))
        return found

    def test_every_opening_has_one_room_and_the_layout_repeats(self):
        lot = _square_lot()
        sky = _sky()
        a = grammar.evaluate(lot, "prewar_masonry", sky, 1408)
        b = grammar.evaluate(lot, "prewar_masonry", sky, 1408)
        self.assertEqual(a["rooms"], b["rooms"])
        self.assertTrue(a["rooms"])
        for _index, _bay, rid in self._open_bays(a):
            self.assertTrue(rid)
            self.assertEqual(sum(1 for room in a["rooms"] if room["id"] == rid), 1)
        for room in a["rooms"]:
            self.assertEqual(room["interior"], "parallax")
            ids = {a["facades"][w["facade"]]["bay_rooms"][w["bay"]] for w in room["windows"]}
            self.assertEqual(ids, {room["id"]})
            curtains = {room["curtain"]}
            self.assertEqual(len(curtains), 1)

    def test_corner_room_is_one_interior_on_two_facades(self):
        spec = grammar.evaluate(_square_lot(), "prewar_masonry", _sky(base_height_m=24), 1408)
        hit = None
        for room in spec["rooms"]:
            if room["floor"] == 0 or room["kind"] != "corner":
                continue
            faces = {}
            for window in room["windows"]:
                faces.setdefault(window["facade"], []).append(window["bay"])
            if len(faces) < 2:
                continue
            normals = [spec["facades"][i]["normal"] for i in faces]
            dot = normals[0][0] * normals[1][0] + normals[0][1] * normals[1][1]
            if dot < 0.5:
                hit = room
                break
        self.assertIsNotNone(hit)
        self.assertTrue(hit["see_through"])
        self.assertGreaterEqual(len(hit["windows"]), 2)
        self.assertIn(hit["curtain"], ("none", "blind", "red", "green", "cream", "blue"))
        room = grammar.room_of(spec, spec["facades"][hit["windows"][0]["facade"]], hit["windows"][0]["bay"])
        self.assertEqual(room["id"], hit["id"])
        self.assertEqual(room["lit"], hit["lit"])

    def test_wide_room_shares_one_facade(self):
        spec = grammar.evaluate(_square_lot("wide", 36), "prewar_masonry", _sky(base_height_m=18), 7)
        wide = [room for room in spec["rooms"]
                if room["kind"] == "room" and room["floor"] > 0 and len(room["windows"]) >= 2]
        self.assertTrue(wide)
        faces = {window["facade"] for window in wide[0]["windows"]}
        self.assertEqual(len(faces), 1)
        self.assertFalse(wide[0]["see_through"])

    def test_curtain_floor_is_one_open_office(self):
        spec = grammar.evaluate(_square_lot("gl", 30), "glass_curtain", _sky(base_height_m=40), 3)
        upper = [room for room in spec["rooms"] if room["floor"] > 0]
        self.assertTrue(upper)
        by_floor = {}
        for room in upper:
            by_floor.setdefault(room["floor"], []).append(room)
        for floor, rooms in by_floor.items():
            self.assertEqual(len(rooms), 1)
            room = rooms[0]
            self.assertEqual(room["kind"], "office")
            self.assertTrue(room["see_through"])
            self.assertEqual(len(room["polygon"]), len(spec["floors"][floor]["polygon"]))
            ids = set()
            for face in spec["facades"]:
                if face["floor"] != floor:
                    continue
                for rid in face["bay_rooms"]:
                    if rid:
                        ids.add(rid)
            self.assertEqual(ids, {room["id"]})

    def test_ground_floor_has_a_lobby_and_a_storefront(self):
        spec = grammar.evaluate(_square_lot(), "prewar_masonry", _sky(), 1)
        front = next(i for i, face in enumerate(spec["facades"]) if face["floor"] == 0 and face["role"] == "front")
        face = spec["facades"][front]
        door = next(i for i, kind in enumerate(face["bay_kinds"]) if kind == "door")
        lobby = grammar.room_of(spec, face, door)
        self.assertEqual(lobby["kind"], "lobby")
        self.assertEqual(lobby["curtain"], "none")
        self.assertGreaterEqual(len(lobby["windows"]), 2)
        shops = [room for room in spec["rooms"] if room["kind"] == "storefront"]
        self.assertTrue(shops)
        for shop in shops:
            self.assertEqual(shop["curtain"], "none")
            ids = {spec["facades"][w["facade"]]["bay_rooms"][w["bay"]] for w in shop["windows"]}
            self.assertEqual(ids, {shop["id"]})
            self.assertIn(shop["lit"], (True, False))


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
        # Grass is the parkway. Sidewalks and both curb kinds are part of the streetscape.
        self.assertTrue(sc["surfaces"]["parkway"])
        self.assertTrue(sc["surfaces"]["sidewalk"])
        self.assertTrue(any(c.get("kind") == "straight" for c in sc["curb_paths"]))
        self.assertTrue(any(c.get("kind") == "return" for c in sc["curb_paths"]))
        kinds = {c["road_id"]: c["kind"] for c in sc["crosswalks"]}
        self.assertTrue(sc["crosswalks"])
        self.assertEqual(kinds.get("road_east"), "ladder")
        self.assertTrue(sc["ramps"])
        self.assertTrue(any(m["kind"] == "dash" for m in sc["markings"]))
        self.assertTrue(any(m["kind"] == "stop" for m in sc["markings"]))
        paint = [m for m in sc["markings"] if m["kind"] in ("dash", "stop", "edge")]
        self.assertTrue(paint)
        self.assertTrue(all(m.get("material") == "M_LanePaint" for m in paint))
        centres = [m for m in sc["markings"] if m["kind"] == "centre"]
        self.assertTrue(centres)
        self.assertTrue(all(m.get("material") == "M_LanePaintYellow" for m in centres))
        self.assertTrue(any(m["kind"] == "puddle" and m.get("material") == "M_Puddle" for m in sc["markings"]))
        self.assertTrue(any(m["kind"] == "manhole" and m.get("material") == "M_Manhole" for m in sc["markings"]))
        south = next(r for r in city["roads"] if r["id"] == "road_south")
        radius = sc["sections"]["road_south"]["curb"]["return_radius_m"]
        south_s = [c["s"] for c in sc["crosswalks"] if c["road_id"] == "road_south"]
        self.assertTrue(south_s)
        self.assertGreater(min(south_s), radius + 1.0)
        # The bars themselves start past the curb-return trim.
        self.assertGreater(min(south_s) - 1.5, radius)
        self.assertTrue(any(p["kind"] == "drain" for p in sc["props"]))
        self.assertTrue(any(p["kind"] == "tree" for p in sc["props"]))
        self.assertTrue(any(p["kind"] == "grate" for p in sc["props"]))
        self.assertTrue(any(p["kind"] == "bin" for p in sc["props"]))
        self.assertTrue(any(p["kind"] == "weed" for p in sc["props"]))
        self.assertTrue(any(p["kind"] == "sign" and p.get("label") for p in sc["props"]))
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
        dressed = {prop["kind"] for prop in sc["props"]}
        for kind in ("lamp", "signal", "stop", "yield", "street_name", "bus_stop", "parked", "hydrant", "bench", "bin"):
            self.assertIn(kind, dressed)
        mark_kinds = {mark["kind"] for mark in sc["markings"]}
        for kind in ("arrow", "stall", "keep_clear", "dash", "stop", "centre"):
            self.assertIn(kind, mark_kinds)
        self.assertTrue(any(mark["kind"] == "arrow" and mark.get("legend") in ("left", "right") for mark in sc["markings"]))
        self.assertTrue(any(prop.get("label") == "BUS" for prop in sc["props"] if prop["kind"] == "bus_stop"))
        names = {prop.get("label") for prop in sc["props"] if prop["kind"] == "street_name"}
        self.assertTrue(names & {"South Avenue", "North Avenue", "East Street", "West Avenue"})
        self.assertTrue(all(mark.get("wear") is not None for mark in sc["markings"]))
        self.assertTrue(sc.get("road_layer", {}).get("stage") == 1)
        for prop in sc["props"]:
            if prop["kind"] in ("drain", "parked"):
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

    def test_streetscape_changes_the_hash(self):
        city = block.build_sample()
        original = model_mod.manifest_hash(city)
        moved = copy.deepcopy(city)
        mark = moved["streetscape"]["markings"][0]
        p0 = mark["polygon"][0]
        mark["polygon"][0] = (p0[0] + 4.0, p0[1])
        self.assertNotEqual(model_mod.manifest_hash(moved), original)
        hashed = model_mod.streetscape_manifest(city)
        self.assertTrue(hashed["markings"])
        self.assertTrue(hashed["props"])


class DistrictTypeTest(unittest.TestCase):
    def test_nine_types_and_the_downtown_mix(self):
        sky = skyline.load()
        styles = grammar.load_styles()
        table = district_types.table(sky)
        self.assertEqual(set(table), set(district_types.TYPE_NAMES))
        for name in district_types.TYPE_NAMES:
            spec = table[name]
            for key in district_types.REQUIRED:
                self.assertIn(key, spec, name)
            self.assertGreaterEqual(len(spec["buildings"]), 1)
            for style_name in spec["buildings"]:
                self.assertIn(style_name, styles)
            for shape in spec["roofs"]:
                self.assertIn(shape, grammar.SHAPES)
            self.assertGreaterEqual(float(spec["wear"]), 0.0)
            self.assertLessEqual(float(spec["wear"]), 1.0)
            self.assertEqual(len(spec["height_m"]), 2)
            self.assertLess(float(spec["height_m"][0]), float(spec["height_m"][1]))
        downtown = district_types.resolve_mix(sky, "downtown")
        self.assertEqual(downtown, {"tech": 40, "eclectic_mix": 30, "apartments_condos": 30})
        city_mix = district_types.resolve_mix(sky, None)
        self.assertEqual(city_mix["houses"], 15)
        self.assertEqual(city_mix["utilities"], 2)
        self.assertEqual(city_mix["industrial_commercial"], 5)
        self.assertIn("utilities", district_types.conflicts("houses"))
        self.assertIn("industrial_commercial", district_types.conflicts("houses"))
        self.assertIn("houses", district_types.conflicts("utilities"))
        self.assertIn("apartments_condos", district_types.conflicts("utilities"))
        self.assertNotIn("tech", district_types.conflicts("houses"))

    def test_untyped_district_keeps_the_character_skyline(self):
        sky = skyline.load()
        params = skyline.for_district(
            {"character": "downtown", "style": "prewar_masonry", "trees": ["linden", "elm"]}, sky)
        self.assertEqual(params["base_height_m"], 52)
        self.assertEqual(params["style"], "prewar_masonry")
        self.assertNotIn("buildings", params)
        self.assertNotIn("district_type", params)

    def test_type_heights_yield_to_a_district_override(self):
        sky = skyline.load()
        district = {
            "character": "custom", "district_type": "houses",
            "buildings": ["texas_lowrise", "brick_walkup"],
            "height_m": [6, 12], "wear": 0.35, "trees": ["liveoak", "elm"],
            "skyline": {},
        }
        params = skyline.for_district(district, sky)
        self.assertAlmostEqual(params["base_height_m"], 9.0)
        self.assertAlmostEqual(params["edge_height_m"], 6.0)
        district["skyline"] = {"base_height_m": 22}
        params = skyline.for_district(district, sky)
        self.assertEqual(params["base_height_m"], 22)

    def test_assign_is_seeded_and_keeps_utilities_off_houses(self):
        mix = {"houses": 40, "utilities": 30, "industrial_commercial": 30, "tech": 40}
        base = _district_row(6)
        first, _ = ops.assign_districts(base, mix=mix)
        second, _ = ops.assign_districts(base, mix=mix)
        kinds = [district["district_type"] for district in first["districts"]]
        self.assertEqual(kinds, [district["district_type"] for district in second["districts"]])
        again, _ = ops.assign_districts(first, mix=mix)
        self.assertEqual(kinds, [district["district_type"] for district in again["districts"]])
        for left, right in zip(kinds, kinds[1:]):
            self.assertNotIn(right, district_types.conflicts(left))
        self.assertTrue(set(kinds) <= set(mix))
        # Nothing in the mix is allowed next to houses, so the lighter share wins.
        forced = _district_row(2)
        forced, _ = ops.set_district_type(forced, "d0", "houses")
        forced, _ = ops.assign_districts(
            forced, mix={"utilities": 1, "industrial_commercial": 5})
        neighbour = next(district for district in forced["districts"] if district["id"] == "d1")
        self.assertEqual(neighbour["district_type"], "utilities")

    def test_locked_and_hand_types_stay(self):
        city = _district_row(3)
        city["districts"][0]["locked"] = True
        painted, _ = ops.assign_districts(city, region="downtown")
        locked = next(district for district in painted["districts"] if district["id"] == "d0")
        self.assertNotIn("district_type", locked)
        hand, _ = ops.set_district_type(city, "d1", "green_renewable")
        painted, _ = ops.assign_districts(hand, region="downtown")
        kept = next(district for district in painted["districts"] if district["id"] == "d1")
        self.assertEqual(kept["district_type"], "green_renewable")
        self.assertEqual(kept["type_source"], "hand")
        for district in painted["districts"]:
            if district["id"] == "d0":
                continue
            self.assertIn(district["district_type"], ("tech", "eclectic_mix", "apartments_condos", "green_renewable"))

    def test_nested_mix_and_boundary(self):
        city = _district_row(1, width=80)
        city["blocks"] = [_block("b%d" % i, "d0", i * 20, 0, 20, 20) for i in range(4)]
        typed, _ = ops.set_district_type(city, "d0", "eclectic_mix")
        self.assertEqual(typed["districts"][0]["mix"]["historic_old"], 40)
        leaves = [block["district_type"] for block in typed["blocks"]]
        self.assertEqual(len(leaves), 4)
        self.assertTrue(set(leaves) <= {"historic_old", "brand_new", "tech"})
        again, _ = ops.set_district_type(city, "d0", "eclectic_mix")
        self.assertEqual(leaves, [block["district_type"] for block in again["blocks"]])

        # A hand mix replaces the type's mix, and a houses neighbour bans utilities.
        pair = _district_row(2, width=40)
        pair, _ = ops.set_district_type(pair, "d0", "houses")
        pair["blocks"] = [
            _block("b_near", "d1", 40, 0, 15, 40),
            _block("b_far", "d1", 72, 5, 8, 30),
        ]
        mixed, _ = ops.set_mix(pair, "d1", {"utilities": 50, "tech": 50, "industrial_commercial": 20})
        near = next(block for block in mixed["blocks"] if block["id"] == "b_near")
        self.assertEqual(near["district_type"], "tech")
        self.assertEqual(mixed["districts"][1]["mix_source"], "hand")
        far = next(block for block in mixed["blocks"] if block["id"] == "b_far")
        self.assertIn(far["district_type"], ("tech", "utilities", "industrial_commercial"))

    def test_typed_buildings_use_the_recipe(self):
        city = _district_row(1, width=80)
        city["blocks"] = [_block("block_a", "d0", 5, 5, 50, 50)]
        city["lots"] = []
        for index in range(6):
            x0 = 8 + (index % 3) * 16
            y0 = 8 + (index // 3) * 20
            city["lots"].append({
                "id": "lot_%d" % index,
                "source": "generated",
                "locked": False,
                "district_id": "d0",
                "block_id": "block_a",
                "polygon": [[x0, y0], [x0 + 12, y0], [x0 + 12, y0 + 14], [x0, y0 + 14]],
                "front_normals": [[0.0, -1.0]],
                "role": "lot",
                "tags": {},
            })
        city, _ = ops.set_district_type(city, "d0", "tech")
        city, _ = ops.regenerate(city, "buildings")
        roofs = set()
        for building in city["buildings"]:
            self.assertIn(building["style"], ("glass_curtain", "modern_mixed"))
            self.assertIn(building["roof"]["shape"], ("flat", "setback"))
            self.assertAlmostEqual(building["wear"], 0.08)
            self.assertGreaterEqual(building["target_height"], 24)
            self.assertLessEqual(building["target_height"], 96)
            roofs.add(building["roof"]["shape"])
        self.assertTrue(roofs)
        pinned, _ = ops.set_skyline(city, "d0", {"style": "prewar_masonry"})
        pinned, _ = ops.regenerate(pinned, "buildings")
        self.assertTrue(all(building["style"] == "prewar_masonry" for building in pinned["buildings"]))

    def test_typed_street_furniture(self):
        plain = _two_streets(None)
        plain_kinds = {prop["kind"] for prop in plain["streetscape"]["props"]}
        self.assertIn("hydrant", plain_kinds)
        self.assertIn("weed", plain_kinds)
        self.assertIn("bench", plain_kinds)
        self.assertIn("grate", plain_kinds)
        typed = _two_streets("tech")
        props = typed["streetscape"]["props"]
        kinds = {prop["kind"] for prop in props}
        self.assertIn("lamp", kinds)
        self.assertIn("tree", kinds)
        self.assertIn("grate", kinds)
        self.assertIn("bin", kinds)
        self.assertNotIn("hydrant", kinds)
        self.assertNotIn("weed", kinds)
        self.assertNotIn("bench", kinds)
        species = {prop["species"] for prop in props if prop["kind"] == "tree"}
        self.assertEqual(species, {"honeylocust"})

    def test_texture_pack_falls_back_to_cc0(self):
        missing = ops.texture_pack("tech")
        self.assertEqual(missing["source"], "cc0")
        self.assertIsNone(missing["path"])
        self.assertEqual(missing["textures"]["glass"], "glass")
        self.assertEqual(missing["textures"]["concrete"], "concrete_wall_001")
        self.assertEqual(missing["textures"]["metal"], "metal_plate")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "packs" / "tech"
            folder.mkdir(parents=True)
            manifest = {
                "district": "tech",
                "materials": ["glass", "metal"],
                "textures": {"glass": "glass_color.png"},
            }
            (folder / "manifest.json").write_text(json.dumps(manifest))
            found = ops.texture_pack("tech", root=tmp)
            self.assertEqual(found["source"], "pack")
            self.assertEqual(found["materials"], ["glass", "metal"])
            self.assertEqual(found["textures"]["glass"], "glass_color.png")
            (folder / "manifest.json").write_text("{")
            broken = ops.texture_pack("tech", root=tmp)
            self.assertEqual(broken["source"], "cc0")
        with self.assertRaises(ValueError):
            ops.texture_pack("suburbs")
        city = _district_row(1)
        with self.assertRaises(ValueError):
            ops.set_district_type(city, "d0", "suburbs")
        city["districts"][0]["district_type"] = "mall"
        with self.assertRaises(ValueError):
            schema.validate(city)


class IncomeTierTest(unittest.TestCase):
    def test_flow_map_and_tier_recipes(self):
        parsed = yaml_lite.loads("houses: {high: 20, mid: 50, low: 25, distressed: 5}")
        self.assertEqual(parsed["houses"], {"high": 20, "mid": 50, "low": 25, "distressed": 5})
        sky = skyline.load()
        table = district_types.table(sky)
        for name in district_types.TIERED_TYPES:
            spec = table[name]
            self.assertEqual(spec["tier_mix"], {"high": 20, "mid": 50, "low": 25, "distressed": 5})
            for tier in district_types.TIER_NAMES:
                recipe = spec["income_tiers"][tier]
                for key in district_types.TIER_KEYS:
                    self.assertIn(key, recipe, "%s %s" % (name, tier))
                self.assertIsNotNone(recipe["fence"])
            distress = spec["income_tiers"]["distressed"]
            for key in district_types.DISTRESS_KEYS:
                self.assertIn(key, distress)
            self.assertTrue(distress["boarded"])
            self.assertTrue(distress["informal"])
            self.assertTrue(distress["encampment"])
        self.assertEqual(table["houses"]["income_tiers"]["high"]["fence"], "iron")
        self.assertEqual(table["houses"]["income_tiers"]["distressed"]["fence"], "open")
        self.assertEqual(table["houses"]["income_tiers"]["high"]["wear"], 0.05)
        self.assertEqual(table["houses"]["income_tiers"]["distressed"]["wear"], 0.9)

    def test_assign_tiers_clusters_along_the_axis(self):
        city = _tier_lots(20)
        first, _ = ops.assign_tiers(city, "d0")
        second, _ = ops.assign_tiers(city, "d0")
        lots = first["lots"]
        again = second["lots"]
        self.assertEqual([lot["tier"] for lot in lots], [lot["tier"] for lot in again])
        counts = {}
        for lot in lots:
            counts[lot["tier"]] = counts.get(lot["tier"], 0) + 1
        self.assertEqual(counts, {"high": 4, "mid": 10, "low": 5, "distressed": 1})
        order = {"high": 0, "mid": 1, "low": 2, "distressed": 3}
        ranked = sorted(lots, key=lambda lot: (lot["tier_score"], lot["id"]))
        indexes = [order[lot["tier"]] for lot in ranked]
        for left, right in zip(indexes, indexes[1:]):
            self.assertGreaterEqual(right - left, 0)
            self.assertLessEqual(right - left, 1)
        high = next(lot for lot in lots if lot["tier"] == "high")
        poor = next(lot for lot in lots if lot["tier"] == "distressed")
        self.assertGreater(high["target_frontage_m"], poor["target_frontage_m"])
        self.assertAlmostEqual(high["wear"], 0.05)
        self.assertAlmostEqual(poor["wear"], 0.9)
        self.assertEqual(high["front_setback_m"], 8)
        self.assertEqual(high["sidewalk"], "good")
        self.assertEqual(high["lighting"], "high")
        self.assertEqual(high["fence"], "iron")
        self.assertTrue(high["gate"])
        self.assertEqual(poor["lighting"], "out")
        self.assertEqual(poor["sidewalk"], "broken")
        self.assertEqual(poor["fence"], "open")
        self.assertFalse(poor["gate"])
        self.assertEqual(poor["encampment_zone"]["people"], 0)
        self.assertTrue(poor["boarded"])
        self.assertFalse(poor["vacant"])

    def test_distressed_lots_board_or_sit_empty(self):
        city = _tier_lots(20)
        city, _ = ops.set_tier_mix(city, "d0", {"high": 5, "mid": 5, "low": 10, "distressed": 80})
        distressed = [lot for lot in city["lots"] if lot["tier"] == "distressed"]
        self.assertGreaterEqual(len(distressed), 4)
        self.assertTrue(any(lot["vacant"] and lot["informal"] for lot in distressed))
        self.assertTrue(any(lot["boarded"] and not lot["vacant"] for lot in distressed))
        for lot in distressed:
            if lot["vacant"]:
                self.assertFalse(lot["boarded"])
            zone = lot.get("encampment_zone")
            if zone:
                self.assertEqual(zone["people"], 0)
                self.assertEqual(zone["kind"], "encampment")
        self.assertTrue(any(lot.get("encampment_zone") for lot in distressed))

    def test_hand_tier_survives_and_unknown_tiers_fail(self):
        city = _tier_lots(20)
        city, _ = ops.assign_tiers(city, "d0")
        city, _ = ops.set_tier(city, "lot_00", "distressed")
        pinned = next(lot for lot in city["lots"] if lot["id"] == "lot_00")
        self.assertEqual(pinned["tier_source"], "hand")
        self.assertEqual(pinned["encampment_zone"]["people"], 0)
        again, _ = ops.assign_tiers(city, "d0")
        kept = next(lot for lot in again["lots"] if lot["id"] == "lot_00")
        self.assertEqual(kept["tier"], "distressed")
        self.assertEqual(kept["tier_source"], "hand")
        with self.assertRaises(ValueError):
            ops.set_tier(city, "lot_00", "palace")
        tech = _district_row(1)
        tech, _ = ops.set_district_type(tech, "d0", "tech")
        with self.assertRaises(ValueError):
            ops.set_tier(tech, "d0", "mid")
        bad = _district_row(1)
        bad["lots"] = [{
            "id": "lot_bad", "source": "generated", "locked": False,
            "district_id": "d0",
            "polygon": [[0, 0], [8, 0], [8, 8], [0, 8]],
            "tier": "palace",
        }]
        with self.assertRaises(ValueError):
            schema.validate(bad)

    def test_plan_and_regenerate_change_lot_and_building_size(self):
        sky = skyline.load()
        types = district_types.table(sky)
        district = {
            "id": "d0", "district_type": "houses", "tier_axis": [1, 0],
            "polygon": [[0, 0], [180, 0], [180, 40], [0, 40]],
            "tier_mix": dict(types["houses"]["tier_mix"]),
        }
        block = [[0, 0], [180, 0], [180, 40], [0, 40]]
        pieces = district_types.plan_block(block, district, 1408, types)
        high = [piece["width"] for piece in pieces if piece["tier"] == "high"]
        low = [piece["width"] for piece in pieces if piece["tier"] == "low"]
        self.assertTrue(high and low)
        self.assertGreater(sum(high) / len(high), sum(low) / len(low))
        made = lots_mod.subdivide(block, seed=1408, frontages=pieces)
        self.assertTrue(all(lot.get("tier") for lot in made["lots"]))

        city = _houses_neighbourhood()
        city, _ = ops.regenerate(city, "blocks")
        lots = {lot["id"]: lot for lot in city["lots"]}
        high_lots = [lot for lot in city["lots"] if lot["tier"] == "high"]
        low_lots = [lot for lot in city["lots"] if lot["tier"] == "low"]
        self.assertTrue(high_lots and low_lots)
        self.assertGreater(_mean_span(high_lots), _mean_span(low_lots))
        high_buildings = [b for b in city["buildings"] if lots[b["lot_id"]]["tier"] == "high"]
        low_buildings = [b for b in city["buildings"] if lots[b["lot_id"]]["tier"] == "low"]
        self.assertTrue(high_buildings and low_buildings)
        self.assertTrue(all(abs(b["wear"] - 0.05) < 1e-6 for b in high_buildings))
        self.assertTrue(all(abs(b["wear"] - 0.62) < 1e-6 for b in low_buildings))
        self.assertLess(_mean_cover(high_buildings, lots), _mean_cover(low_buildings, lots))

        heavy = _houses_neighbourhood({"high": 15, "mid": 15, "low": 15, "distressed": 55})
        heavy, _ = ops.regenerate(heavy, "blocks")
        by_lot = {lot["id"]: lot for lot in heavy["lots"]}
        distressed_lots = [lot for lot in heavy["lots"] if lot["tier"] == "distressed"]
        self.assertTrue(distressed_lots)
        boarded = [b for b in heavy["buildings"] if b.get("boarded")]
        sheds = [b for b in heavy["buildings"] if b.get("informal")]
        self.assertTrue(boarded or sheds)
        for shed in sheds:
            self.assertTrue(by_lot[shed["lot_id"]]["vacant"])
            self.assertFalse(shed.get("boarded"))
        for building in boarded:
            self.assertFalse(by_lot[building["lot_id"]]["vacant"])

    def test_tier_streetscape_and_pack_paths(self):
        rich = _houses_neighbourhood({"high": 97, "mid": 1, "low": 1, "distressed": 1})
        poor = _houses_neighbourhood({"high": 1, "mid": 1, "low": 1, "distressed": 97})
        rich, _ = ops.regenerate(rich, "blocks")
        poor, _ = ops.regenerate(poor, "blocks")
        rich_props = rich["streetscape"]["props"]
        poor_props = poor["streetscape"]["props"]
        rich_trees = sum(1 for prop in rich_props if prop["kind"] == "tree")
        poor_trees = sum(1 for prop in poor_props if prop["kind"] == "tree")
        self.assertGreater(rich_trees, poor_trees)
        self.assertTrue(any(prop["kind"] == "parked" for prop in poor_props))
        rich_wear = [mark.get("wear") or 0 for mark in rich["streetscape"]["markings"]]
        poor_wear = [mark.get("wear") or 0 for mark in poor["streetscape"]["markings"]]
        self.assertTrue(rich_wear and poor_wear)
        self.assertGreater(sum(poor_wear) / len(poor_wear), sum(rich_wear) / len(rich_wear))
        self.assertTrue(any(prop["kind"] == "fence" and prop.get("style") == "iron" for prop in rich_props))
        self.assertTrue(any(prop.get("lighting") == "high" for prop in rich_props if prop["kind"] == "lamp"))
        self.assertTrue(any(prop.get("lighting") == "out" for prop in poor_props if prop["kind"] == "lamp"))
        rich_walks = rich["streetscape"]["surfaces"]["sidewalk"]
        poor_walks = poor["streetscape"]["surfaces"]["sidewalk"]
        self.assertTrue(any(walk.get("condition") == "good" for walk in rich_walks))
        self.assertTrue(any(walk.get("condition") == "broken" for walk in poor_walks))
        camps = [prop for prop in poor_props if prop["kind"] == "encampment"]
        self.assertTrue(camps)
        self.assertTrue(all(prop.get("people") == 0 for prop in camps))
        for props in (rich_props, poor_props):
            self.assertFalse(any(prop["kind"] in ("person", "pedestrian", "occupant") for prop in props))

        missing = ops.texture_pack("houses", tier="high")
        self.assertEqual(missing["source"], "cc0")
        self.assertEqual(missing["tier"], "high")
        self.assertIsNone(missing["path"])
        self.assertEqual(missing["materials"], ["brick", "plaster"])
        self.assertEqual(missing["textures"]["brick"], "brick_wall_001")
        tech = ops.texture_pack("tech")
        self.assertEqual(tech["source"], "cc0")
        self.assertIsNone(tech["tier"])
        with tempfile.TemporaryDirectory() as tmp:
            tier_dir = Path(tmp) / "packs" / "houses" / "high"
            tier_dir.mkdir(parents=True)
            (tier_dir / "manifest.json").write_text(json.dumps({
                "materials": ["glass"], "textures": {"glass": "glass_color.png"},
            }))
            found = ops.texture_pack("houses", root=tmp, tier="high")
            self.assertEqual(found["source"], "pack")
            self.assertEqual(found["tier"], "high")
            self.assertEqual(found["materials"], ["glass"])
            self.assertEqual(found["textures"]["glass"], "glass_color.png")
            (tier_dir / "manifest.json").write_text("{")
            (Path(tmp) / "packs" / "houses" / "manifest.json").write_text(json.dumps({
                "materials": ["metal"], "textures": {"metal": "plate.png"},
            }))
            fallen = ops.texture_pack("houses", root=tmp, tier="high")
            self.assertEqual(fallen["source"], "pack")
            self.assertEqual(fallen["materials"], ["metal"])
            (Path(tmp) / "packs" / "houses" / "manifest.json").write_text("{")
            empty = ops.texture_pack("houses", root=tmp, tier="high")
            self.assertEqual(empty["source"], "cc0")
        with self.assertRaises(ValueError):
            ops.texture_pack("houses", tier="palace")
        plain = skyline.for_lot(
            {"character": "downtown", "style": "prewar_masonry", "trees": ["linden", "elm"]},
            {"id": "lot_a"}, skyline.load())
        self.assertEqual(plain["base_height_m"], 52)
        self.assertNotIn("buildings", plain)
        self.assertNotIn("tier", plain)


def _tier_lots(count):
    city = _district_row(1, width=max(80, count * 12))
    city, _ = ops.set_district_type(city, "d0", "houses")
    city["districts"][0]["tier_axis"] = [1, 0]
    width = city["districts"][0]["polygon"][1][0]
    lots = []
    for index in range(count):
        x0 = 4 + index * ((width - 8) / count)
        x1 = x0 + ((width - 8) / count) * 0.8
        lots.append({
            "id": "lot_%02d" % index,
            "source": "generated",
            "locked": False,
            "district_id": "d0",
            "polygon": [[x0, 8], [x1, 8], [x1, 36], [x0, 36]],
            "front_normals": [[0.0, -1.0]],
            "role": "lot",
            "tags": {},
        })
    city["lots"] = lots
    return city


def _houses_neighbourhood(mix=None, length=200, depth=48):
    city = model_mod.new_model([-30, -30, length + 40, depth + 40], 1408)
    city, _ = ops.add_district(
        city,
        [[-5, -5], [length + 5, -5], [length + 5, depth + 5], [-5, depth + 5]],
        character="residential", name="Houses", district_id="d0",
    )
    for road in _loop(0, 0, length, depth):
        city, _ = ops.draw_road(
            city, road["polyline"], cls=road["cls"], lanes=road["lanes"],
            oneway=road["oneway"], core=road["core"], name=road["name"],
            road_id=road["id"], district_id="d0",
        )
    city, _ = ops.set_district_type(city, "d0", "houses")
    city["districts"][0]["tier_axis"] = [1, 0]
    if mix:
        city, _ = ops.set_tier_mix(city, "d0", mix)
    return city


def _mean_span(lots):
    spans = []
    for lot in lots:
        xs = [point[0] for point in lot["polygon"]]
        spans.append(max(xs) - min(xs))
    return sum(spans) / len(spans)


def _mean_cover(buildings, lots):
    ratios = []
    for building in buildings:
        lot_area = abs(geom.poly_area(lots[building["lot_id"]]["polygon"])) or 1.0
        ratios.append(abs(geom.poly_area(building["footprint"])) / lot_area)
    return sum(ratios) / len(ratios)


def _district_row(count, width=40):
    city = model_mod.new_model([-5, -5, count * width + 5, width + 5], 1408)
    for index in range(count):
        x0 = index * width
        city, _ = ops.add_district(
            city, [[x0, 0], [x0 + width, 0], [x0 + width, width], [x0, width]],
            character="custom", name="D%d" % index, district_id="d%d" % index,
        )
    return city


def _block(ident, district_id, x, y, w, h):
    return {
        "id": ident,
        "source": "generated",
        "locked": False,
        "district_id": district_id,
        "polygon": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
    }


def _two_streets(type_name):
    city = model_mod.new_model([-30, -30, 160, 80], 1408)
    city, _ = ops.add_district(
        city, [[-20, -20], [150, -20], [150, 60], [-20, 60]],
        character="residential", name="Row", district_id="d0",
    )
    city, _ = ops.draw_road(
        city, [[0, 0], [120, 0]], cls="major", lanes=2, core=True, district_id="d0", road_id="h", name="h")
    city, _ = ops.draw_road(
        city, [[0, 0], [0, 40]], cls="minor", lanes=1, core=True, district_id="d0", road_id="v", name="v")
    if type_name:
        city, _ = ops.set_district_type(city, "d0", type_name)
    city, _ = ops.regenerate(city, "streetscape")
    return city


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
