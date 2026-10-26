"""City Shape v1 consumer. No Unreal, no Blender, no roadnet dressing.

Run: python3 -I Scripts/city/test_cityshape.py
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cityshape
import generate_city
import network
import schema
import seeder

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "cityshape" / "seed7_excerpt.json"
SCRIPT = Path(__file__).resolve().parent / "cityshape.py"


def _load():
    return json.loads(FIXTURE.read_text())


class FixtureTest(unittest.TestCase):
    def test_excerpt_becomes_a_drive_graph(self):
        first = cityshape.consume(_load())
        second = cityshape.consume(cityshape.load(FIXTURE))
        self.assertEqual(first["model"]["seed"], 7)
        self.assertGreaterEqual(first["shape_nodes"], 9)
        self.assertGreaterEqual(len(first["drive"]), 9)
        self.assertGreater(len(first["graph_edges"]), 0)
        self.assertGreaterEqual(len(first["faces"]), 1)
        self.assertEqual(len(first["water"]), 1)
        self.assertEqual(first["water"][0]["id"], "pond")
        self.assertEqual(first["model"]["roads"], second["model"]["roads"])
        self.assertEqual(len(first["graph_edges"]), len(second["graph_edges"]))

    def test_classes_map_onto_the_existing_drive_filter(self):
        result = cityshape.consume(_load())
        by_id = {road["id"]: road for road in result["model"]["roads"]}
        self.assertEqual(by_id["e_north"]["cls"], "major")
        self.assertEqual(by_id["e_north"]["shape_class"], "arterial")
        self.assertEqual(by_id["e_north"]["lanes"], 4)
        self.assertEqual(by_id["e_west"]["cls"], "mid")
        self.assertEqual(by_id["e_south"]["cls"], "minor")
        self.assertEqual(by_id["e_east"]["cls"], "minor")
        self.assertEqual(by_id["e_east"]["shape_class"], "alley")
        self.assertEqual(by_id["e_east"]["lanes"], 1)
        self.assertEqual(by_id["e_hwy"]["cls"], "highway")
        self.assertTrue(by_id["e_hwy"]["bridge"])
        self.assertTrue(by_id["e_hwy"]["oneway"])
        self.assertEqual(by_id["e_hwy"]["polyline"][1], [40.0, 130.0])
        self.assertTrue(by_id["e_stub"]["stub"])
        for road in result["model"]["roads"]:
            self.assertNotIn("width", road)
            self.assertNotIn("speed", road)
            self.assertNotIn("capacity", road)
            self.assertNotIn("township_id", road)
        self.assertEqual(result["model"]["districts"], [])
        self.assertNotIn("township_id", result["model"])
        # The same rows roadnet keeps before it dresses anything.
        self.assertEqual(len(result["drive"]), len(result["model"]["roads"]))
        for row in result["drive"]:
            self.assertIn(row["cls"], cityshape.DRIVE)
            self.assertFalse(row["skip"])
            self.assertFalse(row["elevated"])
            self.assertGreaterEqual(len(row["pts"]), 2)

    def test_shared_nodes_are_one_graph(self):
        result = cityshape.consume(_load())
        ends = []
        for edge in result["graph_edges"]:
            if edge["road_id"] in ("e_south", "e_west"):
                ends.append(edge["a"])
                ends.append(edge["b"])
        self.assertIn((0.0, 0.0), ends)
        self.assertEqual(cityshape._components(result["graph_edges"]), 1)
        again = network.node_roads(result["model"]["roads"])
        self.assertEqual(len(again), len(result["graph_edges"]))

    def test_seeder_entry_validates(self):
        city = seeder.seed_from_city_shape(_load())
        schema.validate(city)
        self.assertGreater(len(city["roads"]), 0)
        self.assertEqual(city["blocks"], [])
        self.assertEqual(city["lots"], [])


class AliasAndOsmTest(unittest.TestCase):
    def test_schema_version_and_endpoint_aliases(self):
        doc = {
            "schema_version": "1",
            "seed": 3,
            "roads": {
                "nodes": [
                    {"id": "a", "at": {"x": 0, "y": 0}},
                    {"id": "b", "x": 40, "y": 0},
                ],
                "edges": [{
                    "id": "ab",
                    "a": "a",
                    "b": "b",
                    "cls": "major",
                    "pts": [[0, 0], [20, 5], [40, 0]],
                }],
            },
        }
        result = cityshape.consume(doc)
        road = result["model"]["roads"][0]
        self.assertEqual(road["cls"], "major")
        self.assertEqual(road["shape_class"], "major")
        self.assertEqual(road["polyline"][1], [20.0, 5.0])
        self.assertEqual(road["lanes"], 2)
        self.assertFalse(road["oneway"])
        self.assertEqual(len(result["graph_edges"]), 2)

    def test_dict_keyed_graph_and_the_drive_names_match(self):
        self.assertEqual(cityshape.DRIVE, generate_city.DRIVE)
        doc = {
            "version": 1,
            "seed": 7,
            "roads": {
                "nodes": {
                    "a": {"pos": [0, 0]},
                    "b": {"pos": [25, 0]},
                },
                "edges": {
                    "ab": {"start_node": "a", "end_node": "b", "class": "local"},
                },
            },
        }
        result = cityshape.consume(doc)
        self.assertEqual(result["model"]["roads"][0]["id"], "ab")
        self.assertEqual(result["drive"][0]["cls"], "minor")
        self.assertEqual(len(result["graph_edges"]), 1)

    def test_osm_city_is_copied_and_no_seam_is_added(self):
        doc = {
            "version": 1,
            "seed": 7,
            "source": "osm",
            "osm": "chicago",
            "roads": {
                "nodes": [
                    {"id": "a", "pos": [0, 0]},
                    {"id": "b", "pos": [30, 0]},
                    {"id": "c", "pos": [30, 20]},
                ],
                "edges": [
                    {"id": "lake", "from": "a", "to": "b", "class": "arterial", "city": "chicago", "bridge": True},
                    {"id": "side", "from": "b", "to": "c", "class": "local"},
                ],
            },
            "layers": {"water": [{"id": "river", "polygon": [[0, 5], [10, 5], [10, 8]]}]},
        }
        result = cityshape.consume(doc)
        by_id = {road["id"]: road for road in result["model"]["roads"]}
        self.assertEqual(by_id["lake"]["source"], "osm")
        self.assertEqual(by_id["lake"]["city"], "chicago")
        self.assertNotIn("city", by_id["side"])
        self.assertTrue(by_id["lake"]["bridge"])
        self.assertNotIn("elevated", by_id["lake"])
        cities = {road.get("city") for road in result["model"]["roads"]}
        self.assertNotIn("austin", cities)
        self.assertEqual(result["model"]["districts"], [])
        self.assertEqual(result["water"][0]["id"], "river")
        for row in result["drive"]:
            self.assertNotIn("width", row)
            self.assertFalse(row["elevated"])

    def test_existing_width_is_kept_and_missing_districts_stay_missing(self):
        doc = {
            "version": 1,
            "seed": 1,
            "roads": {
                "nodes": [{"id": "a", "pos": [0, 0]}, {"id": "b", "pos": [10, 0]}],
                "edges": [{
                    "id": "wide", "from": "a", "to": "b", "class": "highway",
                    "width": 18.5, "speed": 25, "capacity": 4,
                }],
            },
            "districts": [
                {"polygon": [[0, 0], [1, 0], [1, 1]]},
                {
                    "id": "d1",
                    "polygon": [[0, 0], [20, 0], [20, 20]],
                    "township_id": "t1",
                    "character": "downtown",
                },
            ],
        }
        city = cityshape.to_city_model(doc)
        self.assertEqual(len(city["districts"]), 1)
        self.assertEqual(city["districts"][0]["township_id"], "t1")
        self.assertEqual(city["roads"][0]["width"], 18.5)
        self.assertEqual(city["roads"][0]["speed"], 25)
        self.assertEqual(city["roads"][0]["capacity"], 4)


class RejectTest(unittest.TestCase):
    def test_version_class_and_dangling_node(self):
        with self.assertRaises(ValueError):
            cityshape.parse({"version": 2, "roads": {"nodes": [], "edges": []}})
        doc = {
            "version": 1,
            "roads": {
                "nodes": [{"id": "a", "pos": [0, 0]}, {"id": "b", "pos": [5, 0]}],
                "edges": [{"id": "e", "from": "a", "to": "b", "class": "pedestrian"}],
            },
        }
        with self.assertRaises(ValueError):
            cityshape.parse(doc)
        doc["roads"]["edges"][0]["class"] = "local"
        doc["roads"]["edges"][0]["to"] = "missing"
        with self.assertRaises(ValueError):
            cityshape.parse(doc)
        with self.assertRaises(ValueError):
            cityshape.parse({"version": 1, "roads": [{"cls": "minor", "pts": [[0, 0], [1, 0]]}]})

    def test_lon_lat_is_refused(self):
        doc = {
            "version": 1,
            "roads": {
                "nodes": [{"id": "a", "pos": {"lon": -87.6, "lat": 41.8}}, {"id": "b", "pos": [1, 0]}],
                "edges": [{"id": "e", "from": "a", "to": "b", "class": "local"}],
            },
        }
        with self.assertRaises(ValueError) as caught:
            cityshape.parse(doc)
        self.assertIn("metres", str(caught.exception))


class CliTest(unittest.TestCase):
    def test_fixture_command_exits_clean(self):
        proc = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), str(FIXTURE)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("graph edges", proc.stdout)
        self.assertIn("drive roads", proc.stdout)
        self.assertNotIn("graph edges 0", proc.stdout)

    def test_empty_document_exits_2(self):
        doc = {"version": 1, "seed": 1, "roads": {"nodes": [], "edges": []}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.json"
            path.write_text(json.dumps(doc))
            proc = subprocess.run(
                [sys.executable, "-I", str(SCRIPT), str(path)],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("no drive edge", proc.stderr)

    def test_out_writes_a_city_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.json"
            proc = subprocess.run(
                [sys.executable, "-I", str(SCRIPT), str(FIXTURE), "--out", str(dest)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            written = json.loads(dest.read_text())
        schema.validate(written)
        self.assertGreater(len(written["roads"]), 0)
        self.assertEqual(written["version"], 1)
        self.assertIn("water", written)


if __name__ == "__main__":
    unittest.main()
