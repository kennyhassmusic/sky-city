# Consuming a City Shape v1 export

City Shape v1 is the master city document. It lives in
[kennyhassmusic/building-types](https://github.com/kennyhassmusic/building-types)
(`Scripts/city/cityshape/`, schema version 1). That repo writes the document:
the seeded road generator, and the OSM importer for Chicago and Austin.
sky-city reads the document. The importer stays in building-types.

This page is the consumer. It turns `roads.nodes` and `roads.edges` into the
drive centrelines sky-city already walks (`Scripts/city/network.py`, the same
`cls` / `pts` filter `Scripts/city/generate_city.py` and `Scripts/roads/roadnet.py`
use before they dress a street).

## Produce a document

In a building-types checkout, one of:

```bash
python3 -I Scripts/city/pipeline.py --seed 7
python3 -I Scripts/city/pipeline.py --osm chicago
python3 -I Scripts/city/pipeline.py --osm austin
python3 -I Scripts/city/pipeline.py --fixture larkhaven
```

Point sky-city at the City Shape v1 JSON that command writes. Full Chicago and
Austin dumps are not stored in this repo. A small seed-7-shaped excerpt is
checked in at `fixtures/cityshape/seed7_excerpt.json` so the consumer can be
run here. It is a few blocks in the v1 shape (an interchange, an alley, a
bridge, a pond). It is not the pipeline's seed-7 city.

## Consume it

```bash
python3 -I Scripts/city/cityshape.py path/to/cityshape.json
python3 -I Scripts/city/cityshape.py path/to/cityshape.json --out Saved/CityGen/from_cityshape.json
python3 -I Scripts/city/cityshape.py fixtures/cityshape/seed7_excerpt.json
```

`--out` writes a sky-city city model (`version` 1). Its `roads` are the drive
centrelines: `polyline`, `cls` (`highway` / `major` / `mid` / `minor`), `lanes`,
`oneway`, `name`. `Scripts/city/seeder.py` `seed_from_city_shape` builds the
same model. `network.node_roads` splits those polylines into the graph the
block builder already walks. Water polygons are copied onto `water` when the
document has them.

Exit 0 when the graph has at least one edge. Exit 1 when the file is not City
Shape v1. Exit 2 when the document is valid and has no drive edge.

```bash
python3 -I Scripts/city/test_cityshape.py
```

## What the reader expects

Schema version 1 (`version` or `schema_version`). Positions are metres, x east,
y north, the city plan frame. A longitude/latitude point is refused.

| City Shape | sky-city road |
|---|---|
| `roads.nodes[].id` + `pos` `[x, y]` | endpoints of each centreline |
| `roads.edges[].from` / `to` | those nodes |
| `class` `highway` | `cls` `highway` |
| `class` `arterial` | `cls` `major` |
| `class` `collector` | `cls` `mid` |
| `class` `local` | `cls` `minor` |
| `class` `alley` | `cls` `minor`, `shape_class` `alley` |
| `polyline` / `pts` on the edge | the centreline, including bends |
| no polyline | the straight segment between the two nodes |
| `lanes`, `oneway`, `name` | copied; missing `lanes` becomes 2, the same default as `draw_road` |
| `bridge`, `tunnel`, `stub` | copied onto the road |
| `water` or `layers.water` | `water` polygons on the city model |
| `districts` with an id and a polygon | copied, including `township_id` when the district already has one |

`roads.nodes` and `roads.edges` may be a list or a dict keyed by id. An edge
may name its ends `from`/`to`, `a`/`b`, `start`/`end`, `start_node`/`end_node`,
or `u`/`v`. A class that is already `major`, `mid`, or `minor` (a compat.py
export) is kept. `source: osm` on the document, or an `osm` city name, marks
the roads `source` `osm`. An edge `city` is copied onto that road only.

## Limits of this step

- The Chicago–Austin seam, stitch roads, and sketch roads stay in the mashup
  scripts. A road gets a `city` only when the City Shape edge already has one.
- Districts are copied only when the document already gives them an id and a
  polygon. A missing `township_id` is left missing.
- `width`, `speed`, and `capacity` are copied only when the edge already has
  them. This step does not look up a cross-section.
- `roadnet.py` is not run. It dresses the mashup from `street_data.json` at
  import time (signals, markings, curb returns). Bridges and tunnels stay in
  the drive list: `elevated` and `skip` stay false, so a bridge is not dropped
  the way an elevated mashup link is.
- Class-pair rules, frontage reach, and the "one connected network" check stay
  in building-types. This side rejects a document it cannot turn into
  centrelines (wrong version, unknown class, unknown node, zero-length edge).
- Blocks, lots, and buildings are left empty. `model.regenerate` still needs
  districts when you want faces turned into lots. The graph and the block
  faces are available from `network.py` as soon as the centrelines exist.
