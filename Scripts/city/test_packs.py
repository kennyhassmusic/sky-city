"""Texture-pack schema, CC0 fallback, and seeded facade assignment.

The AI images are not in this repo. Fixtures are temporary manifests.
Run: python3 -I Scripts/city/test_packs.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import districts as district_types
import grammar
import model as model_mod
import operations as ops
import packs
import skyline


def _library(root):
    """Two facade basics, a crown accent, a tiling ground, and a pothole decal."""
    mix = {
        "facade": {
            "body": "basic",
            "accents": ["crown", "ground_band", "corner"],
            "neighbors_avoid_repeat_basic": True,
        },
        "ground": {"body": "basic", "scatter": ["pothole", "stain"]},
    }
    (root / "packs").mkdir(parents=True)
    (root / "packs" / "districts.json").write_text(json.dumps(mix))
    _set(root, "facades", "brick_a", _facade("brick_a", "basic", "body"))
    _set(root, "facades", "brick_b", _facade("brick_b", "basic", "body"))
    _set(root, "facades", "crown_a", _facade("crown_a", "accent", "crown"))
    _set(root, "facades", "houses_only", _facade("houses_only", "basic", "body", districts=["houses"], tiers=["high"]))
    _set(root, "ground", "asphalt_a", {
        "id": "asphalt_a", "role": "basic", "suggested_use": "body",
        "districts": ["tech"],
        "maps": {"albedo": "albedo.png", "normal": "normal.png", "roughness": "roughness.png"},
        "size_px": [1024, 1024], "scale_m": {"width": 4.0, "height": 4.0},
    })
    _set(root, "decals", "pot_hole", {
        "id": "pot_hole", "role": "accent", "suggested_use": "pothole", "feature": "pothole",
        "districts": ["tech"], "alpha": "alpha.png", "size_px": [512, 512],
        "scale_m": [2.4, 1.6],
    })
    _set(root, "facades", "odd_size", {
        "id": "odd_size", "role": "basic", "suggested_use": "body",
        "districts": ["tech"], "size_px": [1000, 1024],
    })
    _set(root, "facades", "bad_scale", {
        "id": "bad_scale", "role": "basic", "suggested_use": "body",
        "districts": ["tech"], "scale_m": {"width": 0, "height": 4},
    })
    _set(root, "facades", "bad_rect", {
        "id": "bad_rect", "role": "basic", "suggested_use": "body", "districts": ["tech"],
        "facades": [{"role": "front", "glass_mask": "g.png", "windows": [{"bay": 0, "floor": 0, "rect": [0, 0, 2, 1]}]}],
    })
    _set(root, "interiors", "room_a", {
        "id": "room_a", "suggested_use": "room", "districts": ["tech"],
        "maps": {"albedo": "room.png"},
    })
    _set(root, "storefronts", "shop_a", {
        "id": "shop_a", "suggested_use": "storefront", "districts": ["tech"],
    })


def _facade(ident, role, use, districts=None, tiers=None):
    return {
        "id": ident,
        "role": role,
        "suggested_use": use,
        "districts": districts or ["tech"],
        "tiers": tiers or [],
        "maps": {"albedo": "albedo.png", "normal": "normal.png", "roughness": "roughness.png"},
        "size_px": [2048, 2048],
        "scale_m": {"width": 6.0, "height": 3.2},
        "facades": [{
            "role": "front",
            "glass_mask": ident + "_glass.png",
            "windows": [{"bay": 0, "floor": 0, "rect": [0.12, 0.2, 0.34, 0.62]}],
            "bays": [{"index": 0, "floor": 0, "rect": [0.08, 0.0, 0.4, 1.0]}],
            "floors": [{"index": 0, "floor": 0, "rect": [0.0, 0.0, 1.0, 0.22]}],
        }],
    }


def _set(root, kind, ident, manifest):
    folder = root / kind / ident
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps(manifest))


def _model(buildings):
    return {
        "version": 1,
        "seed": 7,
        "bounds": [0, 0, 80, 40],
        "districts": [{
            "id": "d0", "name": "Loop", "source": "hand", "locked": False,
            "polygon": [[0, 0], [80, 0], [80, 40], [0, 40]],
            "character": "downtown", "district_type": "tech",
        }],
        "roads": [],
        "blocks": [],
        "lots": [{
            "id": building["lot_id"], "source": "generated", "locked": False,
            "polygon": building["footprint"], "district_id": "d0",
            "district_type": "tech", "block_id": building.get("block_id"),
        } for building in buildings],
        "buildings": buildings,
        "overrides": [],
    }


def _shell(ident, x, block="bk"):
    return {
        "id": ident, "lot_id": ident, "block_id": block, "district_id": "d0",
        "source": "generated", "locked": False, "role": "building",
        "style": "prewar_masonry", "seed": 7, "height": 18,
        "footprint": [[x, 0], [x + 10, 0], [x + 10, 12], [x, 12]],
        "facades": [],
    }


def _grammar_building():
    district = {"id": "d0", "character": "downtown", "district_type": "tech"}
    params = skyline.for_district(district, skyline.load())
    lot = {
        "id": "lot_g", "district_id": "d0", "district_type": "tech",
        "polygon": [[-12, -8], [12, -8], [12, 8], [-12, 8]],
    }
    spec = grammar.evaluate(lot, "prewar_masonry", params, 4)
    spec["block_id"] = "bk"
    return spec


class RepoPacksTest(unittest.TestCase):
    """The packs that ship in SourceArt/ai_textures, read through the default root.

    Manifests are plain JSON (not LFS), so this resolves even in a checkout that
    has not pulled the images. Guards the bug where every district silently fell
    back to CC0 because the loader read a path that did not exist.
    """

    def _tier_for(self, district):
        return "high" if district in district_types.TIERED_TYPES else None

    def test_packs_are_installed(self):
        base = packs._root(None)
        if base is None:
            self.skipTest("no texture packs under SourceArt/ai_textures")
        self.assertTrue((Path(base) / "packs" / "districts.json").is_file())

    def test_every_district_gets_a_pack_facade_not_cc0(self):
        if packs._root(None) is None:
            self.skipTest("no texture packs under SourceArt/ai_textures")
        for district in district_types.TYPE_NAMES:
            tier = self._tier_for(district)
            record = ops.texture_pack(district, tier=tier)
            self.assertEqual(record["source"], "pack", "%s should resolve to a pack" % district)
            facades = [item for item in record["sets"] if item["kind"] == "facade"]
            self.assertTrue(facades, "%s has no facade set" % district)
            self.assertEqual(record["skipped"], [], "%s dropped a manifest: %s" % (district, record["skipped"]))

    def test_assign_stamps_a_pack_body_on_a_building(self):
        if packs._root(None) is None:
            self.skipTest("no texture packs under SourceArt/ai_textures")
        dressed, _ids = ops.assign_textures(_model([_grammar_building()]))
        pack = dressed["buildings"][0]["pack"]
        self.assertEqual(pack["source"], "pack")
        self.assertIsNotNone(pack["facade"]["basic"])


class PackLoaderTest(unittest.TestCase):
    def test_missing_library_is_cc0(self):
        # Packs ship in the repo now; an empty root shows the CC0 fallback.
        with tempfile.TemporaryDirectory() as empty:
            record = ops.texture_pack("tech", root=empty)
            self.assertEqual(record["source"], "cc0")
            self.assertIsNone(record["path"])
            self.assertEqual(record["sets"], [])
            self.assertEqual(record["textures"]["concrete"], "concrete_wall_001")
            self.assertIn("crown", record["mix"]["facade"]["accents"])
            self.assertIn("pothole", record["mix"]["ground"]["scatter"])
            city, _ids = ops.assign_textures(_model([_grammar_building()]), root=empty)
            pack = city["buildings"][0]["pack"]
            self.assertEqual(pack["source"], "cc0")
            front = next(face for face in pack["facade"]["faces"] if face["role"] == "front")
            self.assertIsNone(front["glass_mask"])
            self.assertTrue(front["windows"])
            self.assertTrue(front["bays"])
            self.assertTrue(front["floors"])
            self.assertEqual(model_mod.manifest_hash(city), model_mod.manifest_hash(_model([_grammar_building()])))

    def test_schema_mix_masks_and_decals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _library(root)
            record = ops.texture_pack("tech", root=tmp)
            self.assertEqual(record["source"], "pack")
            ids = {item["id"] for item in record["sets"]}
            self.assertIn("brick_a", ids)
            self.assertIn("crown_a", ids)
            self.assertIn("pot_hole", ids)
            self.assertNotIn("houses_only", ids)
            self.assertNotIn("odd_size", ids)
            reasons = {item["id"]: item["reason"] for item in record["skipped"]}
            self.assertIn("power-of-two", reasons["odd_size"])
            self.assertIn("positive", reasons["bad_scale"])
            self.assertIn("rect", reasons["bad_rect"])
            ground = next(item for item in record["sets"] if item["id"] == "asphalt_a")
            self.assertEqual(ground["scale_m"], {"width": 4.0, "height": 4.0})
            self.assertEqual(ground["size_px"], [1024, 1024])
            self.assertTrue(ground["tile"])
            hole = next(item for item in record["sets"] if item["id"] == "pot_hole")
            self.assertFalse(hole["tile"])
            self.assertEqual(hole["placement"], "decal")
            self.assertEqual(hole["alpha"], "alpha.png")
            houses = ops.texture_pack("houses", root=tmp, tier="high")
            self.assertIn("houses_only", {item["id"] for item in houses["sets"]})
            self.assertNotIn("brick_a", {item["id"] for item in houses["sets"]})

    def test_neighbors_avoid_the_same_basic_and_repeat_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _library(root)
            near = _model([_shell("b_a", 0), _shell("b_b", 14)])
            first, ids = ops.assign_textures(near, root=tmp)
            second, _ids = ops.assign_textures(near, root=tmp)
            pack_a = first["buildings"][0]["pack"]
            pack_b = next(item["pack"] for item in first["buildings"] if item["id"] == "b_b")
            self.assertNotEqual(pack_a["facade"]["basic"], pack_b["facade"]["basic"])
            self.assertEqual(set(pack_a["facade"]["accents"]), {"crown"})
            self.assertEqual(pack_a["ground"]["basic"], "asphalt_a")
            self.assertTrue(pack_a["ground"]["tile"])
            self.assertEqual([item["id"] for item in pack_a["ground"]["decals"]], ["pot_hole"])
            self.assertFalse(pack_a["ground"]["decals"][0]["tile"])
            self.assertEqual(pack_a["storefront"], "shop_a")
            self.assertEqual(pack_a["interior"], "room_a")
            self.assertEqual(ids, ["b_a", "b_b"])
            again = {item["id"]: item["pack"] for item in second["buildings"]}
            for item in first["buildings"]:
                self.assertEqual(item["pack"], again[item["id"]])
            spec = _grammar_building()
            dressed, _ids = ops.assign_textures(_model([spec]), root=tmp)
            faces = dressed["buildings"][0]["pack"]["facade"]["faces"]
            ground_front = next(face for face in faces if face["role"] == "front" and face["floor"] == 0)
            upper = next(face for face in faces if face["role"] == "front" and face["floor"] != 0)
            self.assertTrue(ground_front["glass_mask"].endswith("_glass.png"))
            self.assertEqual(ground_front["windows"][0]["rect"], [0.12, 0.2, 0.34, 0.62])
            self.assertTrue(upper["glass_mask"].endswith("_glass.png"))
            self.assertNotEqual(upper["windows"][0]["rect"], [0.12, 0.2, 0.34, 0.62])
            kept = _shell("b_lock", 0)
            kept["locked"] = True
            kept["pack"] = {"source": "cc0", "marker": "stay"}
            city, touched = ops.assign_textures(_model([kept, _shell("b_open", 40, block="other")]), root=tmp)
            locked = next(item for item in city["buildings"] if item["id"] == "b_lock")
            self.assertEqual(locked["pack"]["marker"], "stay")
            self.assertNotIn("b_lock", touched)

    def test_upper_floors_use_the_tile_row_not_a_made_up_rect(self):
        """Floor 2 of a 2-floor tile is row 0. The glass mask stays with that rect."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _library(root)
            low = [0.12, 0.2, 0.34, 0.62]
            high = [0.12, 0.55, 0.34, 0.9]
            manifest = _facade("tile_two", "basic", "body")
            manifest["floors_in_tile"] = 2
            manifest["bays_in_tile"] = 3
            manifest["facades"][0]["windows"] = [
                {"bay": 0, "floor": 0, "rect": low, "wrap_group": "stack", "pieces": 2},
                {"bay": 0, "floor": 1, "rect": high, "wrap_group": "stack", "pieces": ["a", "b"]},
            ]
            manifest["facades"][0]["bays"] = [
                {"index": 0, "floor": 0, "rect": [0.08, 0.0, 0.4, 0.5]},
                {"index": 0, "floor": 1, "rect": [0.08, 0.5, 0.4, 1.0]},
            ]
            manifest["facades"][0]["floors"] = [
                {"index": 0, "floor": 0, "rect": [0.0, 0.0, 1.0, 0.5]},
                {"index": 1, "floor": 1, "rect": [0.0, 0.5, 1.0, 1.0]},
            ]
            _set(root, "facades", "tile_two", manifest)
            # brick_a and brick_b are also eligible. Pin the body by dropping them.
            for other in ("brick_a", "brick_b", "houses_only"):
                folder = root / "facades" / other
                for path in folder.glob("manifest.json"):
                    path.unlink()
            building = _shell("tower", 0)
            building["facades"] = []
            for floor in range(4):
                building["facades"].append({
                    "floor": floor, "role": "front", "length": 10.0, "bays": 1,
                    "pier_w": 0.4, "opening_w": 1.2, "bay_kinds": ["window"],
                })
            dressed, _ids = ops.assign_textures(_model([building]), root=tmp)
            pack = dressed["buildings"][0]["pack"]
            self.assertEqual(pack["facade"]["basic"], "tile_two")
            self.assertEqual(pack["facade"]["floors_in_tile"], 2)
            self.assertEqual(pack["facade"]["bays_in_tile"], 3)
            faces = {face["floor"]: face for face in pack["facade"]["faces"]}
            self.assertEqual(faces[2]["windows"][0]["rect"], low)
            self.assertEqual(faces[2]["windows"][0]["wrap_group"], "stack")
            self.assertEqual(faces[2]["windows"][0]["pieces"], 2)
            self.assertEqual(faces[3]["windows"][0]["rect"], high)
            self.assertEqual(faces[2]["bays"][0]["rect"], [0.08, 0.0, 0.4, 0.5])
            self.assertEqual(faces[3]["floors"][0]["rect"], [0.0, 0.5, 1.0, 1.0])
            self.assertTrue(faces[2]["glass_mask"].endswith("_glass.png"))
            # The invented grammar rect starts at v 0.22. The tile row does not.
            self.assertNotEqual(faces[2]["windows"][0]["rect"][1], 0.22)

    def test_normalize_keeps_tile_counts_and_window_wrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "packs").mkdir(parents=True)
            (root / "packs" / "districts.json").write_text("{}")
            manifest = _facade("kept", "basic", "body")
            manifest["floors_in_tile"] = 3
            manifest["bays_in_tile"] = 4
            manifest["facades"][0]["windows"] = [{
                "bay": 1, "floor": 0, "rect": [0.1, 0.2, 0.3, 0.6],
                "wrap_group": "bay-stack", "pieces": ["left", "right"],
            }]
            _set(root, "facades", "kept", manifest)
            record = ops.texture_pack("tech", root=tmp)
            item = next(row for row in record["sets"] if row["id"] == "kept")
            self.assertEqual(item["floors_in_tile"], 3)
            self.assertEqual(item["bays_in_tile"], 4)
            window = item["facades"][0]["windows"][0]
            self.assertEqual(window["wrap_group"], "bay-stack")
            self.assertEqual(window["pieces"], ["left", "right"])
            self.assertEqual(window["rect"], [0.1, 0.2, 0.3, 0.6])

    def test_equipment_category_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _library(root)
            _set(root, "equipment", "roof_unit", {
                "id": "roof_unit",
                "suggested_use": "roof",
                "districts": ["tech"],
                "maps": {"albedo": "unit.png"},
                "size_px": [512, 512],
                "scale_m": {"width": 1.2, "height": 0.8},
            })
            record = ops.texture_pack("tech", root=tmp)
            unit = next(item for item in record["sets"] if item["id"] == "roof_unit")
            self.assertEqual(unit["kind"], "equipment")
            self.assertEqual(unit["role"], "basic")
            self.assertTrue(unit["tile"])
            dressed, _ids = ops.assign_textures(_model([_shell("b_eq", 0)]), root=tmp)
            self.assertEqual(dressed["buildings"][0]["pack"]["equipment"], "roof_unit")


if __name__ == "__main__":
    unittest.main()
