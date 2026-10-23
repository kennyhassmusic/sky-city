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


class PackLoaderTest(unittest.TestCase):
    def test_missing_library_is_cc0(self):
        record = ops.texture_pack("tech")
        self.assertEqual(record["source"], "cc0")
        self.assertIsNone(record["path"])
        self.assertEqual(record["sets"], [])
        self.assertEqual(record["textures"]["concrete"], "concrete_wall_001")
        self.assertIn("crown", record["mix"]["facade"]["accents"])
        self.assertIn("pothole", record["mix"]["ground"]["scatter"])
        city, _ids = ops.assign_textures(_model([_grammar_building()]))
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


if __name__ == "__main__":
    unittest.main()
