"""Build the one-block downtown study from skyline.yaml.

The block is not a special-case mesh. It is a district, four roads and a regenerate,
which is the same path the Map Designer uses. The script then evaluates the same lots
in each style listed under variations, and writes the data the Blender preview reads.

Run: python3 -I Scripts/city/block.py
Writes:
  Scripts/city/examples/loop_block.city_model.json
  Scripts/city/city_model.schema.json
  SourceArt/CityGen/loop_variations.json
  SourceArt/CityGen/block_manifest.json
  SourceArt/CityGen/facades/T_CG_Facade_<style>.png
Running it twice prints the same manifest hash.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grammar
import model as model_mod
import operations as ops
import pngutil
import schema
import skyline
import streets


def build_sample(sky=None):
    """The loop block, built only through add_district, draw_road and regenerate."""
    sky = sky or skyline.load()
    spec = sky["block"]
    x0, x1 = float(spec["x0"]), float(spec["x1"])
    y0, y1 = float(spec["y0"]), float(spec["y1"])
    seed = int(sky.get("seed") or 1)
    city = model_mod.new_model([x0 - 40, y0 - 40, x1 + 40, y1 + 40], seed)
    city, _ids = ops.add_district(
        city, spec["district"], character="downtown", name="Loop",
        district_id="d_loop",
        skyline_overrides={
            "hero_anchor": list(spec["hero_anchor"]),
            "silhouette": spec["silhouette"],
            "centre": [0, 0],
            "reach_m": 80,
        },
    )
    corners = {
        "sw": [x0, y0], "se": [x1, y0], "ne": [x1, y1], "nw": [x0, y1],
    }
    # Each centreline is walked so the block sits to the left. Shared corners match
    # exactly, which is what closes the face.
    order = [
        ("road_south", "south", [corners["sw"], corners["se"]]),
        ("road_east", "east", [corners["se"], corners["ne"]]),
        ("road_north", "north", [corners["ne"], corners["nw"]]),
        ("road_west", "west", [corners["nw"], corners["sw"]]),
    ]
    for road_id, side, pts in order:
        street = spec["streets"][side]
        city, _ids = ops.draw_road(
            city, pts, cls=street["class"], lanes=street["lanes"],
            oneway=street["oneway"], core=street["core"], name=street["name"],
            district_id="d_loop", road_id=road_id,
        )
    city, _ids = ops.regenerate(city, "blocks", sky=sky)
    return city


def context_buildings(city, sky=None):
    """Masses across the outer sidewalk so the block is not floating in a void.

    They are role context. The manifest hash skips that role, and they are not
    written into the city model.
    """
    sky = sky or skyline.load()
    district = next(d for d in city["districts"] if d["id"] == "d_loop")
    params = skyline.for_district(district, sky)
    params = dict(params)
    params["hero_count"] = 0
    params["noise_amplitude_m"] = 6
    # Silhouette of the study is about the block, not the buildings behind the camera.
    params["silhouette"] = {"samples": [40], "mode": "soft_max", "origin": [0, 0], "axis": [1, 0], "length": 1}
    made = []
    # (road id, side away from the block, along-start, count)
    # side +1 is left of the centreline. The loop keeps the block on the left,
    # so the context sits on the right, side -1.
    for road_id, count in (("road_south", 4), ("road_north", 4), ("road_east", 3), ("road_west", 3)):
        road = next(r for r in city["roads"] if r["id"] == road_id)
        length = _length(road)
        sec_w = _half_width(city, road_id) * 2.0
        for i in range(count):
            s = (i + 0.5) * length / count
            lateral = -1.0 * (sec_w / 2.0 + 14.0)
            centre, _d = streets.point_on_road(road, s, lateral)
            lot = {
                "id": "ctx_%s_%d" % (road_id, i),
                "polygon": _square(centre, 16.0, 12.0, road),
                "front_normals": [[0.0, 1.0] if "south" in road_id or "north" in road_id else [1.0, 0.0]],
                "role": "context",
                "district_id": "d_loop",
                "tags": {},
            }
            # Face the block.
            toward = streets.inner_sign(road, (0.0, 0.0))
            # inner_sign is +1 when the block is to the left. The context front
            # points back toward the block, which is the left side of this road.
            d = _dir(road)
            left = (-d[1], d[0])
            lot["front_normals"] = [[round(left[0] * toward, 4), round(left[1] * toward, 4)]]
            spec = grammar.evaluate(lot, "prewar_masonry", params, city["seed"])
            spec["role"] = "context"
            made.append(spec)
    return made


def cameras(city):
    """Street eye on the south sidewalk, an aerial from the southeast, dusk on the street eye."""
    road = next(r for r in city["roads"] if r["id"] == "road_south")
    sec = (city.get("streetscape") or {}).get("sections", {}).get("road_south") or {}
    width = float(sec.get("width") or 12.0)
    back = 0.19
    # Stand in the south lanes, looking east and nearly level, so the zebra a few metres
    # ahead stays in frame. A high target drops the paint below the lens.
    eye, _direction = streets.point_on_road(road, 3.5, width * 0.12)
    target, _d = streets.point_on_road(road, 42.0, width / 2.0 + back + 4.0)
    street = {
        "name": "street",
        "location": [round(eye[0], 2), round(eye[1], 2), 1.65],
        "target": [round(target[0], 2), round(target[1], 2), 2.4],
        "lens": 24,
        "sun": {"elevation": 28, "rotation": 35, "strength": 1.0},
    }
    aerial = {
        "name": "aerial",
        "location": [78.0, -88.0, 110.0],
        "target": [0.0, 0.0, 24.0],
        "lens": 32,
        "sun": {"elevation": 32, "rotation": 20, "strength": 1.0},
    }
    dusk = {
        "name": "dusk",
        "location": street["location"],
        "target": [round(target[0], 2), round(target[1], 2), 14.0],
        "lens": 28,
        "sun": {"elevation": 2.5, "rotation": 70, "strength": 0.35},
    }
    return {"street": street, "aerial": aerial, "dusk": dusk}


def variation_buildings(city, sky=None):
    """The same lots and the same height field, read through each style."""
    sky = sky or skyline.load()
    district = next(d for d in city["districts"] if d["id"] == "d_loop")
    params = skyline.for_district(district, sky)
    styles = list(sky.get("variations") or ["prewar_masonry"])
    out = {}
    for style in styles:
        rows = []
        for lot in city["lots"]:
            if lot.get("district_id") != "d_loop":
                continue
            spec = grammar.evaluate(lot, style, params, city["seed"])
            spec["role"] = "building"
            rows.append(spec)
        rows.sort(key=lambda b: b["id"])
        out[style] = rows
    return out


def write_facades(styles, dest):
    """A small original window grid per style, for the far LOD. Not a photograph."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    grammar_styles = grammar.load_styles()
    paths = {}
    for name in styles:
        style = grammar_styles[name]
        tint = style.get("tint") or [0.7, 0.7, 0.7]
        paths[name] = str(dest / ("T_CG_Facade_%s.png" % name))
        _facade_png(paths[name], tint, style.get("opening") or "punched")
    return paths


def write_outputs(root=None):
    root = Path(root) if root else skyline.project_root()
    sky = skyline.load()
    city = build_sample(sky)
    schema.write_schema_file()
    example = root / "Scripts" / "city" / "examples"
    example.mkdir(parents=True, exist_ok=True)
    example_path = example / "loop_block.city_model.json"
    example_path.write_text(json.dumps(city, indent=2) + "\n")
    styles = list(sky.get("variations") or [])
    facades = write_facades(list(grammar.load_styles().keys()), root / "SourceArt" / "CityGen" / "facades")
    payload = {
        "version": 1,
        "seed": city["seed"],
        "manifest_hash": model_mod.manifest_hash(city),
        "streetscape": city.get("streetscape"),
        "cameras": cameras(city),
        "context": context_buildings(city, sky),
        "styles": variation_buildings(city, sky),
        "facades": facades,
        "blocks": [{"id": b["id"], "polygon": b["polygon"]} for b in city["blocks"]],
        "roads": [{"id": r["id"], "polyline": r["polyline"], "name": r.get("name")} for r in city["roads"]],
    }
    art = root / "SourceArt" / "CityGen"
    art.mkdir(parents=True, exist_ok=True)
    (art / "loop_variations.json").write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    manifest = {
        "version": 1,
        "seed": city["seed"],
        "hash": payload["manifest_hash"],
        "districts": len(city["districts"]),
        "roads": len(city["roads"]),
        "blocks": len(city["blocks"]),
        "lots": len(city["lots"]),
        "buildings": len([b for b in city["buildings"] if b.get("role") != "context"]),
        "styles": styles,
        "props": len((city.get("streetscape") or {}).get("props") or []),
    }
    (art / "block_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return city, manifest


def _facade_png(path, tint, opening):
    w, h = 128, 256
    buf = bytearray(w * h * 3)
    wall = (int(tint[0] * 180), int(tint[1] * 170), int(tint[2] * 160))
    glass = (28, 42, 58) if opening != "curtain" else (70, 110, 140)
    pier = max(6, w // 18)
    floors = 8
    bays = 4
    fh = h // floors
    bw = (w - pier) // bays
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 3
            floor = y // fh
            in_sill = (y % fh) < fh * 0.22 or (y % fh) > fh * 0.82
            bay_x = (x - pier // 2) % bw
            in_pier = x < pier // 2 or bay_x < pier // 2 or bay_x > bw - pier // 2
            lit = (floor + (x // bw)) % 3 == 0 and not in_sill and not in_pier
            if in_pier or in_sill:
                rgb = wall
            elif lit:
                rgb = (255, 196, 120)
            else:
                rgb = glass
            buf[i:i + 3] = bytes(rgb)
    pngutil.write_rgb(path, w, h, bytes(buf))


def _length(road):
    import geom
    pts = road["polyline"]
    return sum(geom.dist(a, b) for a, b in zip(pts, pts[1:]))


def _dir(road):
    import geom
    a, b = road["polyline"][0], road["polyline"][-1]
    return geom.unit(geom.sub(b, a))


def _half_width(city, road_id):
    sec = (city.get("streetscape") or {}).get("sections", {}).get(road_id) or {}
    return float(sec.get("width") or 10) / 2.0


def _square(centre, width, depth, road):
    import geom
    d = _dir(road)
    left = (-d[1], d[0])
    hw, hd = width / 2.0, depth / 2.0
    pts = []
    for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        p = geom.add(centre, geom.add(geom.mul(d, su * hw), geom.mul(left, sv * hd)))
        pts.append([round(p[0], 2), round(p[1], 2)])
    return pts


if __name__ == "__main__":
    city, manifest = write_outputs()
    again, manifest2 = write_outputs()
    print(json.dumps(manifest, indent=2))
    if manifest["hash"] != manifest2["hash"]:
        sys.exit("manifest hash changed between two runs")
    print("stable", manifest["hash"])
