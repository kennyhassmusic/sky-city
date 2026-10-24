"""Tests for walkup.py: the walk-up rule set as checks (Design/WALKUP_RULES.md, the screenshot checklist).

Run: python3 -I Scripts/city/test_walkup.py
Pure Python; the city-wide checks use the Chicago Loop region when its inputs are there.
"""
import math
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import kit_layout  # noqa: E402
import walkup  # noqa: E402

R = walkup.RULES


def row(bid, x0, length, depth=18.0, seed=11):
    """A synthetic walkup: front along +x at y = 0, facing -y, depth along +y."""
    poly = [[x0, 0.0], [x0 + length, 0.0], [x0 + length, depth], [x0, depth]]
    return {"id": bid, "style": "brick_walkup", "seed": seed, "footprint": poly,
            "facades": [{"a": [x0, 0.0], "b": [x0 + length, 0.0], "normal": [0.0, -1.0], "length": length,
                         "z": 0.0, "h": 3.5, "floor": 0, "role": "front"}]}


def street():
    return [row("b%02d" % k, k * 31.0, 30.0) for k in range(6)] + [row("short", 200.0, 9.8)]


def chicago():
    try:
        import generate_city
        import skyline
        return generate_city.build_from_disk(skyline.project_root(), region="chicago_loop")
    except Exception:  # noqa: BLE001 - the region inputs are optional for these tests
        return None


class ProportionTest(unittest.TestCase):
    def setUp(self):
        self.lots = walkup.plan_city(street())

    def test_lots_read_as_25_ft(self):
        for lot in self.lots:
            w = lot["s1"] - lot["s0"]
            self.assertGreaterEqual(w, R["lot_w"][0] * 0.92, lot["id"])
            self.assertLessEqual(w, R["double_lot_max"], lot["id"])
        single = [lot["s1"] - lot["s0"] for lot in self.lots if lot["building"] != "short"]
        self.assertGreater(sum(1 for w in single if w <= R["lot_w"][1] * 1.08), len(single) * 0.7)

    def test_ground_floor_25_to_40_percent_taller(self):
        for lot in self.lots:
            ratio = lot["ground_h"] / lot["upper_h"]
            self.assertGreaterEqual(ratio, 1.25 - 1e-6, lot["id"])
            self.assertLessEqual(ratio, 1.4 + 1e-6, lot["id"])
            self.assertTrue(4.0 - 1e-6 <= lot["ground_h"] <= 4.6 + 1e-6)
            self.assertTrue(3.05 - 1e-6 <= lot["upper_h"] <= 3.35 + 1e-6)

    def test_windows_tall_narrow_and_placed(self):
        for lot in self.lots:
            aspect = lot["ww"] / lot["wh"]
            self.assertTrue(0.42 <= aspect <= 0.56, (lot["id"], aspect))
            self.assertTrue(R["sill_above_floor"][0] <= lot["sill_above"] <= R["sill_above_floor"][1])
            # The head sits 12-18 in (0.3-0.46 m) or a bit more below the ceiling.
            upper = lot["upper_h"] - (R["top_shorter"] if lot["top_shorter"] else 0.0)
            self.assertGreaterEqual(upper - lot["sill_above"] - lot["wh"], R["head_below_ceiling"][0] - 1e-6)
        self.assertTrue(0.1 <= R["recess"] <= 0.2)

    def test_storefront_parts(self):
        for lot in self.lots:
            sf = lot["storefront"]
            parts = sf["bulkhead"] + sf["display"] + sf["transom"] + sf["sign_h"] + R["sf_cornice"]["h"]
            self.assertLessEqual(parts, lot["ground_h"] + 1e-6, lot["id"])
            self.assertTrue(0.45 <= sf["bulkhead"] <= 0.75 and 2.13 <= sf["display"] <= 2.44)
            self.assertTrue(0.6 <= sf["sign_h"] <= 0.9 and 0.9 <= sf["entry_d"] <= 1.5)

    def test_cornice_and_parapet(self):
        for lot in self.lots:
            c = lot["cornice"]
            self.assertTrue(0.45 <= c["proud"] <= 0.9 and 0.3 <= c["ret"] <= 0.9)
            self.assertTrue(0.6 <= lot["parapet"] <= 1.2)
            self.assertGreater(walkup.cornice_bottom(lot), lot["ground_h"] if lot["floors"] > 1 else 0.0)


class VarietyTest(unittest.TestCase):
    def setUp(self):
        self.lots = walkup.plan_city(street())

    def test_neighbours_differ(self):
        rows = {}
        for lot in self.lots:
            rows.setdefault(lot["building"], []).append(lot)
        window = R["repeat_window"]
        for row_lots in rows.values():
            built = [lot for lot in row_lots if not lot["vacant"]]
            for a, b in zip(built, built[1:]):
                if b["index"] != a["index"] + 1:
                    continue
                self.assertNotEqual(a["tone"], b["tone"], (a["id"], b["id"]))
                self.assertGreaterEqual(abs(a["top"] - b["top"]), R["roofline_step"] - 1e-6, (a["id"], b["id"]))
            for k, lot in enumerate(row_lots):
                for other in row_lots[max(0, k - window):k]:
                    self.assertNotEqual(walkup.combo(lot["look"]), walkup.combo(other["look"]), (lot["id"], other["id"]))

    def test_everything_varies(self):
        self.assertGreater(len({lot["floors"] for lot in self.lots}), 2)
        self.assertEqual(len({lot["tone"] for lot in self.lots}), len(walkup.TONES))
        self.assertEqual(len({lot["cornice"]["kind"] for lot in self.lots}), len(walkup.CORNICES))
        self.assertGreater(len({lot["lintel"] for lot in self.lots}), 1)
        oriels = sum(1 for lot in self.lots if lot["oriel"])
        self.assertTrue(0.15 * len(self.lots) <= oriels <= 0.6 * len(self.lots), oriels)

    def test_roof_clutter(self):
        for lot in self.lots:
            self.assertTrue(3 <= len(lot["roof_items"]) <= 5)
            self.assertNotIn("water_tank", lot["roof_items"])


class LayoutTest(unittest.TestCase):
    def setUp(self):
        self.layout = kit_layout.Layout()
        self.lots = walkup.layout_buildings(self.layout, street())

    def test_deterministic(self):
        again = kit_layout.Layout()
        walkup.layout_buildings(again, street())
        self.assertEqual(self.layout.groups, again.groups)

    def test_modules_known_and_tints_consistent(self):
        for key, items in self.layout.groups.items():
            self.assertIn(key.split("|")[0], kit_layout.MODULES, key)
            self.assertEqual(len({len(item) for item in items}), 1, key)

    def test_front_and_common_brick(self):
        keys = set(self.layout.groups)
        self.assertTrue(any(key.endswith("set:" + walkup.COMMON) for key in keys))
        for tone in walkup.TONES:
            self.assertTrue(any(key.endswith("set:brk_" + tone) for key in keys), tone)

    def test_storefront_pieces_present(self):
        keys = set(self.layout.groups)
        for needed in ("KIT_Glass|shopglass:", "KIT_Panel|shopback:", "KIT_Cornice|trim:", "KIT_Decal|gdecal:sign_", "KIT_Box|trim:sf_tile",
                       "KIT_Bracket|", "KIT_Decal|gdecal:streak_", "KIT_Box|trim:wood"):
            self.assertTrue(any(key.startswith(needed) for key in keys), needed)

    def test_windows_stack(self):
        # Every upper-floor window column repeats on each upper floor.
        for lot in self.lots:
            cols = walkup.window_columns(lot)
            self.assertTrue(cols or lot["oriel"], lot["id"])
            for c0, c1 in cols:
                self.assertGreater(c0, 0.2)
                self.assertLess(c1, lot["s1"] - lot["s0"] - 0.2)

    def test_collision_per_lot(self):
        built = [lot for lot in self.lots if not lot["vacant"]]
        self.assertEqual(len(self.layout.groups[kit_layout.COLLISION]), len(built))


@unittest.skipIf(chicago() is None, "no Chicago Loop inputs")
class ChicagoTest(unittest.TestCase):
    def test_chicago_walkups(self):
        city = chicago()
        layout = kit_layout.build_layout(city)
        lots = layout.lots
        self.assertGreater(len(lots), 100)
        widths = [lot["s1"] - lot["s0"] for lot in lots]
        self.assertGreater(sum(1 for w in widths if 5.6 <= w <= 8.2), len(lots) * 0.6)
        self.assertGreater(len({round(lot["top"], 1) for lot in lots}), 40)
        self.assertTrue(all(math.isfinite(v) for items in layout.groups.values() for item in items for v in item))


if __name__ == "__main__":
    unittest.main()
