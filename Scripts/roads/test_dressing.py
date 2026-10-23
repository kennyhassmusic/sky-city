"""Stage 1 road dressing. No Unreal, no city model, no roadnet.

Run: python3 -I Scripts/roads/test_dressing.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dressing
import profiles


def _road(ident, pts, cls, lanes=2, oneway=False, name="Lane", core=False):
    return {
        "id": ident, "polyline": pts, "cls": cls, "lanes": lanes,
        "oneway": oneway, "core": core, "name": name, "district_id": "d0",
    }


def _sections(roads):
    return {
        road["id"]: profiles.preview_section(road["cls"], road["lanes"], road["oneway"], road["core"])
        for road in roads
    }


def _model(roads, seed=7, wear=None, lots=None):
    district = {"id": "d0", "district_type": "houses"}
    if wear is not None:
        district["wear"] = wear
    return {"seed": seed, "roads": roads, "districts": [district], "lots": lots or []}


class DressingTest(unittest.TestCase):
    def test_same_seed_is_the_same_dressing(self):
        roads = [
            _road("h", [[0, 0], [80, 0]], "major", name="Harbor"),
            _road("v", [[40, -40], [40, 40]], "minor", lanes=1, oneway=True, name="Orchard"),
        ]
        model = _model(roads)
        sections = _sections(roads)
        a_props, a_marks = dressing.dress(model, sections)
        b_props, b_marks = dressing.dress(model, sections)
        self.assertEqual(a_props, b_props)
        self.assertEqual(a_marks, b_marks)

    def test_two_majors_get_signals_not_stop_signs(self):
        # Existing roads meet at a shared endpoint. A mid-edge crossing is stage 2.
        roads = [
            _road("h", [[0, 0], [90, 0]], "major", lanes=3, oneway=True, name="South Avenue"),
            _road("v", [[0, -50], [0, 0]], "major", lanes=3, oneway=True, name="West Avenue"),
        ]
        props, marks = dressing.dress(_model(roads), _sections(roads))
        kinds = {prop["kind"] for prop in props}
        self.assertIn("signal", kinds)
        self.assertNotIn("stop", kinds)
        self.assertNotIn("yield", kinds)
        self.assertTrue(any(mark["kind"] == "keep_clear" for mark in marks))
        self.assertTrue(any(mark["kind"] == "arrow" and mark["legend"] in ("left", "right") for mark in marks))
        names = {prop["label"] for prop in props if prop["kind"] == "street_name"}
        self.assertTrue(names <= {"South Avenue", "West Avenue"})

    def test_a_minor_street_stops_and_a_collector_yields(self):
        minor = [
            _road("h", [[0, 0], [80, 0]], "major", name="Arterial"),
            _road("v", [[0, -40], [0, 0]], "minor", lanes=1, oneway=True, name="Local"),
        ]
        props, _marks = dressing.dress(_model(minor), _sections(minor))
        self.assertTrue(any(prop["kind"] == "stop" and prop["road_id"] == "v" for prop in props))
        self.assertFalse(any(prop["kind"] == "signal" for prop in props))
        mid = [
            _road("h", [[0, 0], [80, 0]], "major", name="Arterial"),
            _road("v", [[0, -40], [0, 0]], "mid", name="Collector"),
        ]
        props, _marks = dressing.dress(_model(mid), _sections(mid))
        self.assertTrue(any(prop["kind"] == "yield" and prop["road_id"] == "v" for prop in props))
        self.assertFalse(any(prop["kind"] == "stop" for prop in props))

    def test_stalls_cars_and_a_bus_stop_and_wear(self):
        roads = [_road("h", [[0, 0], [120, 0]], "mid", name="North Avenue", core=False)]
        bare = _model(roads, wear=0.1)
        faded = _model(roads, wear=0.8)
        _props, marks = dressing.dress(bare, _sections(roads))
        dressing.finish(marks, _props, bare)
        self.assertTrue(any(mark["kind"] == "stall" for mark in marks))
        self.assertTrue(any(prop["kind"] == "parked" for prop in _props))
        self.assertTrue(any(prop["kind"] == "bus_stop" and prop.get("label") == "BUS" for prop in _props))
        self.assertTrue(all(abs(mark["wear"] - 0.1) < 1e-6 for mark in marks))
        again, _ = dressing.dress(faded, _sections(roads))
        dressing.finish(again, [], faded)
        self.assertTrue(all(abs(mark["wear"] - 0.8) < 1e-6 for mark in again))
        labels = " ".join(prop.get("label") or "" for prop in _props)
        for banned in ("Ford", "Toyota", "Chevy", "Tesla", "BMW"):
            self.assertNotIn(banned, labels)

    def test_finish_paints_the_centre_line_yellow(self):
        marks = [{"kind": "centre", "district_id": "d0", "material": "M_LanePaint", "polygon": []}]
        marks.append({"kind": "dash", "district_id": "d0", "material": "M_LanePaint", "polygon": []})
        dressing.finish(marks, [], _model([], wear=0.2))
        self.assertEqual(marks[0]["material"], "M_LanePaintYellow")
        self.assertEqual(marks[1]["material"], "M_LanePaint")
        self.assertEqual(marks[1]["wear"], 0.2)


if __name__ == "__main__":
    unittest.main()
