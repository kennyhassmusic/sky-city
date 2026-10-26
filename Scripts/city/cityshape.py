"""Turn a City Shape v1 document into sky-city drive centrelines.

building-types (kennyhassmusic/building-types) owns the City Shape document and
the OSM importer. This module is the consumer. It reads roads.nodes and
roads.edges (schema version 1) and writes the centreline roads that
Scripts/city/network.py already splits into a graph. Water polygons are copied
when the document has them.

The reader does not invent a Chicago–Austin seam, districts, or township ids,
and it does not fill in width, speed, or capacity. It does not run roadnet
dressing: roadnet.py builds the mashup from street_data.json when it is
imported, which is a different job.

A City Shape edge class maps back the way the importer mapped forward:
highway stays highway, arterial → major, collector → mid, local → minor.
An alley is driveable here as minor, with shape_class "alley" so the original
class is still on the road. A class that is already a sky-city drive name
(compat.py's translated export) is kept.

Node positions are metres, x east, y north, the same frame as the city model.
An edge polyline is the centreline. An edge with no polyline is the straight
segment between its nodes.

Run:
  python3 -I Scripts/city/cityshape.py fixtures/cityshape/seed7_excerpt.json
  python3 -I Scripts/city/cityshape.py path/to/cityshape.json --out Saved/CityGen/from_cityshape.json

Exit 0 when the document is valid and the drive graph has at least one edge.
Exit 1 when the document is not City Shape v1. Exit 2 when it is valid but
yields no drive edge.
"""
import json
import math
import sys
from pathlib import Path

# python3 -I does not put the script directory on sys.path. The city modules
# live next to this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import model as model_mod  # noqa: E402
import network  # noqa: E402
import schema  # noqa: E402

# City Shape class → the drive class generate_city and roadnet already filter on.
# The four sky-city names are accepted so a compat.py export still loads.
SHAPE_TO_DRIVE = {
    "highway": "highway",
    "arterial": "major",
    "collector": "mid",
    "local": "minor",
    "alley": "minor",
    "major": "major",
    "mid": "mid",
    "minor": "minor",
}
DRIVE = ("highway", "major", "mid", "minor")
_END_PAIRS = (
    ("from", "to"),
    ("a", "b"),
    ("start", "end"),
    ("start_node", "end_node"),
    ("u", "v"),
    ("from_id", "to_id"),
)
_POS_KEYS = ("pos", "position", "at", "xy")
_LINE_KEYS = ("polyline", "pts", "points")


def load(path):
    """Read a City Shape JSON file. Reject a Git LFS pointer."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    head = text[:180]
    if head.startswith("version https://git-lfs") or "git-lfs.github.com/spec" in head:
        raise ValueError(
            "city shape: %s is a Git LFS pointer, not a City Shape document" % path)
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("city shape: %s is not JSON (%s)" % (path, exc)) from exc
    return doc


def parse(doc):
    """Check a City Shape v1 document and return its nodes, edges and water.

    The return value is the normalized graph. It is not a city model yet.
    """
    if not isinstance(doc, dict):
        raise ValueError("city shape: document is not an object")
    _version(doc)
    roads = doc.get("roads")
    if isinstance(roads, list):
        raise ValueError(
            "city shape: roads is a list. A City Shape document has roads.nodes and "
            "roads.edges. This file looks like a sky-city city model.")
    if not isinstance(roads, dict):
        raise ValueError("city shape: roads must be an object with nodes and edges")
    if "nodes" not in roads or "edges" not in roads:
        seen = ", ".join(sorted(str(key) for key in roads)) or "(empty)"
        raise ValueError("city shape: roads needs nodes and edges (found %s)" % seen)
    node_rows = _records(roads["nodes"], "nodes")
    edge_rows = _records(roads["edges"], "edges")

    nodes = {}
    for raw in node_rows:
        if not isinstance(raw, dict):
            raise ValueError("city shape: a node is not an object")
        ident = _ident(raw.get("id"), "a node")
        if ident in nodes:
            raise ValueError("city shape: duplicate node id %s" % ident)
        nodes[ident] = _node_pos(raw, ident)

    edges = []
    seen_edges = set()
    for raw in edge_rows:
        if not isinstance(raw, dict):
            raise ValueError("city shape: an edge is not an object")
        ident = _ident(raw.get("id"), "an edge")
        if ident in seen_edges:
            raise ValueError("city shape: duplicate edge id %s" % ident)
        seen_edges.add(ident)
        edges.append(_edge(raw, ident, nodes))

    return {
        "version": 1,
        "seed": _seed(doc, None),
        "source": _document_source(doc),
        "bounds": _bounds(doc, _all_points(nodes, edges)),
        "nodes": nodes,
        "edges": edges,
        "water": _water_features(doc),
        "districts": _districts(doc, _document_source(doc)),
    }


def to_city_model(doc, seed=None):
    """A sky-city city model whose roads are the City Shape drive centrelines.

    Blocks, lots and buildings stay empty. Regenerating them is a later step,
    and it needs districts the document may not have. This function does not
    call streets or roadnet, so it does not invent a cross-section.
    """
    parsed = parse(doc)
    if seed is not None:
        parsed["seed"] = int(seed)
    return _city_from_parsed(parsed)


def _city_from_parsed(parsed):
    city = model_mod.new_model(parsed["bounds"], parsed["seed"])
    city["districts"] = parsed["districts"]
    city["roads"] = [_road_record(edge, parsed["source"]) for edge in parsed["edges"]]
    if parsed["water"]:
        city["water"] = parsed["water"]
    schema.validate(city)
    return city


def drive_table(model):
    """Centreline rows in the shape roadnet's drive filter already uses.

    skip and elevated stay false. A bridge or a tunnel is still a centreline;
    this consumer does not apply roadnet's under-street skip, and a bridge is
    not the elevated flag that drops a road from the drive set. width, speed
    and capacity are copied only when the road already carries them.
    """
    rows = []
    for road in model.get("roads") or []:
        row = {
            "id": road["id"],
            "cls": road.get("cls"),
            "name": road.get("name") or "",
            "pts": [list(p) for p in (road.get("polyline") or [])],
            "lanes": int(road.get("lanes") or 2),
            "oneway": bool(road.get("oneway")),
            "skip": False,
            "elevated": False,
        }
        for key in ("width", "speed", "capacity", "bridge", "tunnel", "stub", "shape_class", "city"):
            if key in road:
                row[key] = road[key]
        rows.append(row)
    return rows


def drive_roads(model):
    """The same predicate roadnet uses before it builds a graph."""
    return [
        row for row in drive_table(model)
        if row["cls"] in DRIVE and not row["skip"] and not row["elevated"] and len(row["pts"]) >= 2
    ]


def consume(doc, seed=None):
    """City model plus the graph network.py builds from those centrelines."""
    parsed = parse(doc)
    if seed is not None:
        parsed["seed"] = int(seed)
    city = _city_from_parsed(parsed)
    graph = network.node_roads(city["roads"])
    return {
        "model": city,
        "drive": drive_roads(city),
        "graph_edges": graph,
        "faces": network.faces(graph),
        "water": list(city.get("water") or []),
        "shape_nodes": len(parsed["nodes"]),
    }


def summary(result):
    """One block of text for the command line."""
    city = result["model"]
    counts = {}
    for road in city.get("roads") or []:
        counts[road.get("cls") or "?"] = counts.get(road.get("cls") or "?", 0) + 1
    classes = ", ".join("%s %d" % (name, counts[name]) for name in DRIVE if counts.get(name))
    lines = [
        "City Shape v1, seed %s" % city.get("seed"),
        "nodes %d, edges %d" % (result["shape_nodes"], len(city.get("roads") or [])),
        "drive roads %d%s" % (len(result["drive"]), (" (" + classes + ")") if classes else ""),
        "graph edges %d" % len(result["graph_edges"]),
        "block faces %d" % len(result["faces"]),
        "water polygons %d" % len(result["water"]),
        "components %d" % _components(result["graph_edges"]),
    ]
    return "\n".join(lines)


def main(argv):
    args = list(argv)
    if not args or "--help" in args or "-h" in args:
        print(__doc__.strip())
        return 0 if args else 1
    out = None
    if "--out" in args:
        slot = args.index("--out")
        if slot + 1 >= len(args):
            print("city shape: --out needs a path", file=sys.stderr)
            return 1
        out = args[slot + 1]
        del args[slot:slot + 2]
    if len(args) != 1:
        print("city shape: give one City Shape v1 JSON file", file=sys.stderr)
        return 1
    try:
        result = consume(load(args[0]))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    text = summary(result)
    print(text)
    if out:
        dest = Path(out)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(result["model"], indent=2, sort_keys=True) + "\n")
        print("wrote %s" % dest)
    if not result["graph_edges"]:
        print("city shape: document has no drive edge", file=sys.stderr)
        return 2
    return 0


def _components(edges):
    parent = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    nodes = set()
    for edge in edges:
        nodes.add(edge["a"])
        nodes.add(edge["b"])
        ra, rb = find(edge["a"]), find(edge["b"])
        if ra != rb:
            parent[ra] = rb
    if not nodes:
        return 0
    return len({find(node) for node in nodes})


def _version(doc):
    present = [key for key in ("version", "schema_version") if key in doc]
    if not present:
        raise ValueError("city shape: document needs version 1")
    for key in present:
        if not _is_one(doc[key]):
            raise ValueError("city shape: %s must be 1 (got %r)" % (key, doc[key]))
    if len(present) == 2 and int(doc["version"]) != int(doc["schema_version"]):
        raise ValueError("city shape: version and schema_version disagree")


def _is_one(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value == 1
    if isinstance(value, str):
        return value.strip() == "1"
    return False


def _seed(doc, override):
    if override is not None:
        return int(override)
    if "seed" not in doc or doc["seed"] is None:
        return 1
    value = doc["seed"]
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("city shape: seed must be an integer")
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("city shape: seed must be an integer") from exc


def _document_source(doc):
    for key in ("source", "origin", "mode"):
        value = doc.get(key)
        if value in schema.SOURCES:
            return value
    osm = doc.get("osm")
    if osm is True or (isinstance(osm, str) and osm.strip()):
        return "osm"
    return "generated"


def _records(value, what):
    """A list of objects, or a dict keyed by id (the id is filled in when missing)."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        rows = []
        for key, item in value.items():
            if not isinstance(item, dict):
                raise ValueError("city shape: %s %s is not an object" % (what, key))
            row = dict(item)
            if row.get("id") in (None, ""):
                row["id"] = key
            rows.append(row)
        return rows
    raise ValueError("city shape: roads.%s must be a list" % what)


def _ident(value, what):
    if isinstance(value, bool) or value is None or value == "":
        raise ValueError("city shape: %s is missing an id" % what)
    if not isinstance(value, (str, int)):
        raise ValueError("city shape: %s has a bad id" % what)
    return str(value)


def _node_pos(node, ident):
    for key in _POS_KEYS:
        if node.get(key) is not None:
            return _point(node[key], "node %s" % ident)
    if "x" in node and "y" in node:
        return _point(node, "node %s" % ident)
    raise ValueError("city shape: node %s needs a pos [x, y] in metres" % ident)


def _edge(raw, ident, nodes):
    a_id, b_id = _ends(raw, ident)
    a_id, b_id = _ident(a_id, "edge %s endpoint" % ident), _ident(b_id, "edge %s endpoint" % ident)
    if a_id not in nodes or b_id not in nodes:
        missing = a_id if a_id not in nodes else b_id
        raise ValueError("city shape: edge %s references unknown node %s" % (ident, missing))
    shape_class = _shape_class(raw, ident)
    polyline = _polyline(raw, ident, nodes, a_id, b_id)
    cleaned = _clean_line(polyline, ident)
    record = {
        "id": ident,
        "a": a_id,
        "b": b_id,
        "shape_class": shape_class,
        "cls": SHAPE_TO_DRIVE[shape_class],
        "lanes": _lanes(raw, ident),
        "oneway": _flag(raw, "oneway", "one_way"),
        "bridge": _flag(raw, "bridge"),
        "tunnel": _flag(raw, "tunnel"),
        "stub": _flag(raw, "stub"),
        "name": "" if raw.get("name") is None else str(raw.get("name")),
        "polyline": cleaned,
    }
    if raw.get("city") not in (None, ""):
        record["city"] = str(raw["city"])
    if isinstance(raw.get("core"), bool):
        record["core"] = raw["core"]
    for key in ("width", "speed", "capacity"):
        if key in raw and raw[key] is not None:
            record[key] = raw[key]
    if raw.get("district_id") not in (None, ""):
        record["district_id"] = str(raw["district_id"])
    return record


def _ends(edge, ident):
    for left, right in _END_PAIRS:
        if left in edge or right in edge:
            if left not in edge or right not in edge:
                present = left if left in edge else right
                missing = right if left in edge else left
                raise ValueError(
                    "city shape: edge %s has %s without %s" % (ident, present, missing))
            return edge[left], edge[right]
    raise ValueError("city shape: edge %s needs from and to node ids" % ident)


def _shape_class(edge, ident):
    if "class" in edge and edge["class"] is not None:
        raw = edge["class"]
    elif "cls" in edge and edge["cls"] is not None:
        raw = edge["cls"]
    else:
        raise ValueError(
            "city shape: edge %s needs a class "
            "(highway, arterial, collector, local or alley)" % ident)
    if not isinstance(raw, str):
        raise ValueError("city shape: edge %s has class %r" % (ident, raw))
    name = raw.strip().lower()
    if name not in SHAPE_TO_DRIVE:
        raise ValueError(
            "city shape: edge %s has class %r; want highway, arterial, collector, "
            "local or alley" % (ident, raw))
    return name


def _polyline(edge, ident, nodes, a_id, b_id):
    for key in _LINE_KEYS:
        if key in edge and edge[key] is not None:
            raw = edge[key]
            if not isinstance(raw, list) or len(raw) < 2:
                raise ValueError("city shape: edge %s %s needs two points" % (ident, key))
            return [_point(point, "edge %s" % ident) for point in raw]
    return [nodes[a_id], nodes[b_id]]


def _clean_line(points, ident):
    rounded = [[round(float(point[0]), 2), round(float(point[1]), 2)] for point in points]
    cleaned = [rounded[0]]
    for point in rounded[1:]:
        if point != cleaned[-1]:
            cleaned.append(point)
    if len(cleaned) < 2:
        raise ValueError("city shape: edge %s has no length" % ident)
    length = 0.0
    for start, end in zip(cleaned, cleaned[1:]):
        length += math.hypot(end[0] - start[0], end[1] - start[1])
    if length < 0.05:
        raise ValueError("city shape: edge %s has no length" % ident)
    return cleaned


def _lanes(edge, ident):
    if "lanes" not in edge or edge["lanes"] is None:
        return 2
    value = edge["lanes"]
    if isinstance(value, bool):
        raise ValueError("city shape: edge %s lanes must be an integer" % ident)
    try:
        lanes = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("city shape: edge %s lanes must be an integer" % ident) from exc
    if lanes < 1:
        raise ValueError("city shape: edge %s lanes must be at least 1" % ident)
    return lanes


def _flag(edge, *keys):
    for key in keys:
        if key not in edge or edge[key] is None:
            continue
        value = edge[key]
        if isinstance(value, bool):
            return value
        raise ValueError("city shape: edge %s %s must be true or false" % (edge.get("id"), key))
    return False


def _point(value, what):
    if isinstance(value, dict):
        if "lon" in value or "lat" in value:
            raise ValueError(
                "city shape: %s is longitude/latitude. The city plan is metres, x east, y north"
                % what)
        if "x" not in value or "y" not in value:
            raise ValueError("city shape: %s is not a point" % what)
        return (float(value["x"]), float(value["y"]))
    if isinstance(value, (list, tuple)) and len(value) >= 2 and not isinstance(value[0], (list, tuple, dict)):
        return (float(value[0]), float(value[1]))
    raise ValueError("city shape: %s is not a point" % what)


def _road_record(edge, source):
    road = {
        "id": edge["id"],
        "source": source,
        "locked": False,
        "polyline": edge["polyline"],
        "cls": edge["cls"],
        "lanes": edge["lanes"],
        "oneway": edge["oneway"],
        "core": bool(edge.get("core")),
        "name": edge["name"],
        "shape_class": edge["shape_class"],
        "bridge": edge["bridge"],
        "tunnel": edge["tunnel"],
        "stub": edge["stub"],
    }
    for key in ("city", "district_id", "width", "speed", "capacity"):
        if key in edge:
            road[key] = edge[key]
    return road


def _all_points(nodes, edges):
    points = list(nodes.values())
    for edge in edges:
        points.extend((point[0], point[1]) for point in edge["polyline"])
    return points


def _bounds(doc, points):
    raw = doc.get("bounds")
    if isinstance(raw, (list, tuple)) and len(raw) >= 4:
        try:
            return [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]
        except (TypeError, ValueError) as exc:
            raise ValueError("city shape: bounds must be four numbers") from exc
    if not points:
        return [0.0, 0.0, 1.0, 1.0]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _districts(doc, source_default):
    """Copy districts that already have an id and a polygon. Do not create any."""
    raw = doc.get("districts")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("city shape: districts must be a list")
    districts = []
    for item in raw:
        if not isinstance(item, dict) or item.get("id") in (None, ""):
            continue
        ring = item.get("polygon") or item.get("ring")
        if not isinstance(ring, list) or len(ring) < 3:
            continue
        source = item.get("source") if item.get("source") in schema.SOURCES else source_default
        district = {
            "id": str(item["id"]),
            "source": source,
            "locked": item["locked"] if isinstance(item.get("locked"), bool) else False,
            "polygon": [[round(float(point[0]), 2), round(float(point[1]), 2)] for point in ring],
        }
        if item.get("name") not in (None, ""):
            district["name"] = str(item["name"])
        if item.get("character") in schema.CHARACTERS:
            district["character"] = item["character"]
        if item.get("township_id") not in (None, ""):
            district["township_id"] = str(item["township_id"])
        districts.append(district)
    return districts


def _water_features(doc):
    raw = doc.get("water")
    if raw is None and isinstance(doc.get("layers"), dict):
        raw = doc["layers"].get("water")
    if raw is None:
        return []
    if isinstance(raw, dict):
        features = []
        for role in ("outer", "inner"):
            rings = raw.get(role) or []
            if not isinstance(rings, list):
                raise ValueError("city shape: water.%s must be a list of polygons" % role)
            for index, ring in enumerate(rings):
                features.append(_water_feature(ring, "water-%s-%d" % (role, index), role))
        return features
    if not isinstance(raw, list):
        raise ValueError("city shape: water must be a list of polygons")
    return [_water_feature(item, "water-%d" % index, "") for index, item in enumerate(raw)]


def _water_feature(item, default_id, role):
    if isinstance(item, dict):
        ident = default_id if item.get("id") in (None, "") else str(item["id"])
        ring = item.get("polygon") or item.get("ring") or item.get("pts") or item.get("points")
        feature_role = item.get("role") or role
    else:
        ident, ring, feature_role = default_id, item, role
    if not isinstance(ring, list) or len(ring) < 3:
        raise ValueError("city shape: water %s needs a polygon" % ident)
    points = [_point(point, "water %s" % ident) for point in ring]
    if len(points) >= 2 and math.hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1]) < 0.05:
        points = points[:-1]
    if len(points) < 3:
        raise ValueError("city shape: water %s needs a polygon" % ident)
    feature = {
        "id": ident,
        "polygon": [[round(point[0], 2), round(point[1], 2)] for point in points],
    }
    if feature_role:
        feature["role"] = feature_role
    return feature


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
