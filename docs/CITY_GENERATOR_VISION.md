# City Generator — Master Vision & Build Path
Oct 25, 2026 · @Kenny

## Purpose and how to use this document
This is the single source of truth for what the city generator is, how its layers fit together, what exists today, and what gets built next. Any agent (human or AI) that touches the project reads this first, finds its layer and phase, and works only inside the contract defined here.

- If you are the management agent: use the Build Path here to place work, and the State & Gaps document to prioritize it. Update that document, not this one, when a milestone lands.
- If you are a build agent: read Architecture Contract and Agent Operating Rules, then the one layer you are assigned. Never change another layer's interface without a contract change recorded here.
- If you are the owner: this is the document to revise when the vision changes. Everything downstream (tasks, PRs, agent prompts) derives from it.

## The vision
Sky City is a layered city generator for Unreal Engine: a creator describes a region, and the system produces a complete, believable city that any AI-driven game can be built on top of. Every layer of the city is a separate module with a fixed data contract, so any one layer can be rebuilt, restyled, or swapped for better assets without breaking the layers above or below it.

The ordering principle: the world is built the way a real one is. Nothing is placed before the thing it depends on exists.

1. Terrain — elevation, water (rivers, lakes, coast), soil and slope. The foundation nothing else can move.
2. Infrastructure graph — a wire graph of roads, highways, rail and bridges laid around the terrain. Every edge carries class, width, lanes, speed and capacity; every node carries intersection type. This graph is the spine of the city: everything else hangs off it.
3. Land use and zoning — the graph cuts the land into blocks and parcels; each parcel receives a zone (downtown core, commercial strip, residential, industrial, civic, park, rural) driven by distance to center, road class, terrain and population targets.
4. Lots and placement — parcels become buildable lots; rule-driven placement decides which building type, size and orientation goes where, plus parking (lots, garages, street) sized to population and capacity.
5. Buildings — each building type (walk-ups, homes, condos, towers, schools, hospitals, stadiums, theaters, churches, gas stations, government, police, fire) is its own generator that reads a lot and a style and produces geometry.
6. Street furniture and props — signage, lights, hydrants, trees, benches, utilities, placed from the graph and lots.
7. Agents and vehicles — traffic, parking occupancy, pedestrians, driven by the graph's capacity data.
8. Style and asset packs — materials, meshes, Megascans or any other source, resolved at the very end through a style resolver so the same city can be photoreal, stylized or retro.

What "independently upgradable" means in practice. A layer is upgradable when (a) its inputs and outputs are typed data with a schema version, (b) it never reads another layer's internals, only its published output, (c) it can be re-run alone from its inputs and produce a valid output, and (d) a validation suite checks the output against the contract before anything downstream runs. Replacing the skyscraper generator, the river model or the vehicle set is then a one-module change.

What "holistic" means. Upstream changes propagate downstream automatically: move the river and the roads re-route, the parcels re-cut, the buildings re-place. Downstream never propagates upstream. Cross-cutting needs (a hospital needs a garage, a stadium needs capacity roads) are expressed as placement rules that read upstream data, never as special cases inside a generator.

The product promise. A creator opens the tool, chooses a terrain seed or imports one, sets population and style, and gets a playable city in minutes. A creator who wants to go deeper swaps one layer. An AI agent assigned to the project can read this document, find its layer, and ship work that fits.

Where things stand against this vision lives in a separate, living document, City Generator — State & Gaps: the current state of both repos per layer, the ranked gaps, the open decisions, and the position in the build path. This document holds only what is stable.

## Architecture contract
Eight layers, one direction of data flow, one schema per boundary. Each layer is a module that owns exactly one output table and reads only the outputs of layers above it.

| # | Layer | Reads | Publishes | Must never |
|---|-------|-------|-----------|------------|
| 0 | Terrain | seed or imported heightmap, water mask | TerrainData: heightfield, slope, water polygons, flow direction, buildable mask | know roads or buildings exist |
| 1 | Infrastructure graph | TerrainData, region config (population, city center, highway entries) | RoadGraph: nodes (id, pos, type), edges (id, from, to, class, lanes, width, speed, capacity, one-way), bridges, rail | place a building or a parcel |
| 2 | Zoning | TerrainData, RoadGraph | ZoneMap: blocks (polygon, bounding edges), parcels (polygon, zone, density, frontage edge) | pick a building type |
| 3 | Placement | ZoneMap, RoadGraph, TerrainData, building catalog | PlacementSet: lots (polygon, footprint, orientation, building_type, style_tag, height_target), parking (lot/garage/street, capacity) | generate geometry |
| 4 | Building generators | one lot from PlacementSet, style resolver | BuildingInstance: geometry or ISM references, door and service points, footprint occupancy | read neighbors or roads directly |
| 5 | Props and furniture | RoadGraph, PlacementSet, BuildingInstances | PropSet: placed props with type, transform, owner lot/edge | modify lots or buildings |
| 6 | Agents and vehicles | RoadGraph, parking capacity, BuildingInstances (doors, use) | AgentConfig: spawn tables, routes, parking assignments | modify geometry |
| 7 | Style and asset resolver | style_tag + a pack manifest | concrete mesh and material references for every placeholder | change any transform |

### Invariants every layer must honor
- Every published table carries schema_version and the seed it was built from. Same inputs + same seed = identical output.
- Outputs are plain data (DataAssets, DataTables, or JSON). Geometry is never the interface between layers; placeholders and references are.
- A layer re-runs alone from its inputs. If a layer cannot be run in isolation, it is not finished.
- Every boundary has a validator (Validate<Layer>Data) that runs before the next layer starts: no overlapping parcels, no edges off the terrain, no lot without a frontage edge, no building without a door on its frontage.
- Cross-cutting requirements (hospital needs garage, stadium needs arterial access) live in the placement rule catalog as data, never as if statements inside a generator.
- Dirty tracking is per layer: changing TerrainData invalidates layers 1–7; changing a building generator invalidates only that building type's instances.
- Each layer has a fixture: a small canned input and a golden output checked into the repo, so an agent can verify a change without running the whole pipeline.

### Minimum repo shape to support this
- Schemas/ — one file per boundary (TerrainData, RoadGraph, ZoneMap, PlacementSet, BuildingInstance, PropSet, AgentConfig, StylePack) with field docs and version.
- Layers/<N>_<Name>/ — generator, validator, fixtures, README stating reads, publishes, status.
- Rules/ — the placement rule catalog as data (see next section).
- Catalog/ — the building type registry: for each type, its generator, size range, zone affinities, parking ratio, service needs.
- Styles/ — pack manifests mapping style tags to mesh and material sources.
- Docs/ — this document, a changelog, and one decision record per contract change.

### Mapping onto today's repos
The contract's boundary tables live inside the City Shape document (building-types Scripts/city/cityshape/schema.py), each as a top-level list with its own version. Terrain → a new terrain key, generator in Scripts/city/terrain/. Infrastructure graph → roads.nodes / roads.edges (done) plus the OSM importer ported from sky-city roadnet.py and a seeded generator. Zoning and lots → districts[] plus skyline (skyline.yaml) and sky-city lots.py as a consumer. Placement → sites[], PLACEMENT_RULES, and a new place.py. Building generators → the kit pipeline (kit_layout.py, style_kit.py, one KIT_TYPE package per type). Props → Scripts/city/streetscape/ and the kit's prop groups. Agents and vehicles → sky-city Scripts/vehicles/ emitting traffic.json. Style → style_kit grown into a StylePack manifest. sky-city's city_model stays as the mashup's intermediate and is fed from the City Shape export, not the other way round.

## Placement rules catalog
Placement is a scored search, not a script. Each building type declares needs (what must be nearby), affinities (what makes a site better), repulsions (what makes it worse), and supply targets (how many per population). The placer fills parcels by priority, scoring every candidate lot against these, and records why each choice was made. New types are added by adding a row, not code.

| Type | Priority | Needs (hard) | Affinities (score up) | Repulsions (score down) | Supply target | Parking rule |
|------|----------|--------------|----------------------|-------------------------|---------------|--------------|
| Highway interchange | 1 | highway edge | city edge, arterial | downtown core | per highway entry | none |
| Gas station | 2 | arterial or highway frontage, corner | ≤ 800 m of interchange, town edge | residential interior | 1 per 2,500 pop, min 1 per highway entry | 8–16 bays |
| Hospital | 2 | arterial access, flat lot ≥ 2 ha | midway between center and edge | industrial, floodplain | 1 per 50,000 pop, min 1 | garage, 1 space / 2 beds |
| Stadium / arena | 2 | arterial + highway within 1.5 km, lot ≥ 6 ha | edge of downtown, rail | residential interior | 1 per 250,000 pop | garage + surface, 1 space / 4 seats |
| Government / city hall | 2 | downtown core, main street | civic plaza, park | industrial | 1 per township | garage or lot |
| Police station | 3 | arterial | each district centroid | floodplain | 1 per 25,000 pop, min 1 per township | surface lot |
| Fire station | 3 | arterial, corner | 5-min drive coverage gaps | dead-end streets | coverage-based (every parcel within 2.5 km) | apron |
| School (K–12) | 3 | residential zone, local road | park, low traffic | highway, industrial | 1 elementary per 5,000 pop, 1 high per 20,000 | lot + bus loop |
| Church | 4 | residential or mixed | corner, older district | industrial | 1 per 3,000 pop | surface lot |
| Theater / amphitheater | 4 | commercial or downtown | entertainment cluster | industrial | 1 per 40,000 pop | shared garage |
| Parking garage | 4 | within 300 m of any type whose parking rule says garage | downtown core | residential interior | derived from demand | — |
| Skyscraper / tower | 5 | downtown core, parcel ≥ 0.2 ha | highest land value, transit | slope > 8 % | fills core by density target | underground, 1 / 100 m² |
| Mixed-use walk-up | 5 | commercial strip or downtown edge, frontage | corner, arterial | highway | fills strip | street + rear lot |
| Condo / apartment | 6 | residential or mixed | near transit, parks | industrial, highway noise | fills by density | lot or garage, 1 / unit |
| Single-family home | 6 | residential, local road | cul-de-sac, park, lake view | arterial, industrial | fills by density | driveway |
| Industrial / warehouse | 6 | highway or rail, flat | city edge | residential, downtown | by zone share | truck lot |
| Surface parking lot | 7 | any leftover parcel near demand | — | — | until street + off-street supply ≥ demand | — |
| Park / plaza | 7 | leftover, waterfront, steep | residential, civic | — | ≥ 10 % of residential land | — |

### Parking demand model (drives lots, garages and street parking together)
- Demand per lot = building type ratio × size (units, beds, seats, m²). Street parking supply = frontage length ÷ 6 m on edges with class ≤ collector.
- Deficit at any lot is covered first by street supply within 150 m, then surface lots within 250 m, then garages within 300 m; unmet deficit spawns a new lot or garage on the best leftover parcel.

### District and township rules
- The RoadGraph is partitioned into districts (downtown, inner, suburban, rural) by distance and road density; each township (a connected cluster outside the main city) gets its own civic minimums: government building, police, fire, school, church, gas station.
- Every rule row records its rationale so an agent can see why a gas station is sitting where it is, and the placer logs the winning score per lot into PlacementSet for debugging.

Numbers above are starting defaults to tune, not facts; they live in Rules/ as data and can be overridden per region.

## Build path
The order follows the gap ranking: pick the spine, put ground under it, then turn the checker into a generator, and only then widen the building types. City Shape's document, ops and validator are kept as they are; each phase adds a table or a stage that reads them. The type lanes in BUILDER_BACKLOG.md keep running in parallel because a type is content on a fixed layout contract; the one change asked of them is a merge cadence. Phases 0–4 are the spine; nothing in 5–8 should start until 4 is done, except data-only rows in the catalogs and the type lanes.

1. **Phase 0 — Spine** (gaps 1, 7, 8, 13). Decide and record: City Shape document v1 is the master city document. Commit this document to both repos. Merge type/cityshape, type/streetscape and type/storenames to main at their current passes. Build pipeline.py in building-types: stages terrain → cityshape → placement → streetscape → kit types → import, each with a fixture and a golden output, dirty tracking by stage, one `--fixture larkhaven` run. Stand up the citywide test street on main that loads every merged type. Done when: `python3 -I Scripts/city/pipeline.py --fixture larkhaven` runs every stage, every validator passes, and the walk-up fingerprint still matches main.
2. **Phase 1 — Terrain** (gap 2). Add terrain to the City Shape document (v2 with a migrator, per CITY_SHAPE_RULES.md item 3): heightfield reference, slope grid, buildable mask, flow direction; a seeded generator and a heightmap importer; water features snap to it. Streetscape pass 3 reads lot z0 from it; the kit importer places on it. Done when: a 2 km × 2 km fixture with one river and one lake validates, no site or lot crosses water, and the Larkhaven demo regenerates on a sloped field with every streetscape transition still legal.
3. **Phase 2 — Roads from a seed, roads from OSM** (gaps 6, 9). Port sky-city's roadnet.py + seeder.py into an OSM importer that writes a City Shape document (classes mapped highway/major/mid/minor → highway/arterial/collector/local). Then a seeded generator that calls the existing ops: stubs at the map edge → highway with interchanges → arterials → collectors → locals; grid downtown, organic suburban, sparse rural; bridges where edges cross water. Partition into districts and townships. Done when: the Chicago + Austin import validates with zero errors, a blank seed produces a graph that validates, and every township is a connected cluster with a township_id.
4. **Phase 3 — Zoning and population** (gap 4). Zone assignment reads distance to centre, road class, terrain and township; residents and jobs per site or lot from floor area and type; totals per district and township in the document. Done when: shares hit the region config within ±5 % and population totals are queryable by township.
5. **Phase 4 — Generative placement** (gaps 3, 5, 12). place.py in cityshape: a catalog of site types with supply targets per population and parking ratios; candidates enumerated on parcels and scored with PLACEMENT_RULES (errors reject, warnings cost, affinities bonus); parking supply counted against demand; civic minimums per township; the EV placer reads the wire graph and flips its checks to errors. Every placed site is a grey box until its type lands. Done when: a Larkhaven run places every catalog type with zero priority-1 problems, parking supply ≥ demand per district, every township has its civic minimums, and the placer logs the winning score per site.
6. **Phase 5 — Building types** (gap 8, widen). The two lanes continue as queued (condo, houses, parking, schools and churches, civic, retail, warehouses; skyscraper, hotel, hospital, university, venues, transit). Each type lands on main at sign-off and is added to the citywide test street. Types read lot base / floor from Streetscape instead of CURB_RISE once phase 1 lands. Done when: every catalog type in phase 4 has a signed-off generator on main and the citywide test street loads clean.
7. **Phase 6 — Style packs** (gap 10). StylePack manifest over style_kit: slot name → swatch, mesh, material; the generated-texture pack and an optional Megascans pack as the two proofs; kit_style_materials and the importer resolve through it. Done when: the same kit_layout renders in two packs with no type code change.
8. **Phase 7 — Props, agents, vehicles** (gap 11). Park and plaza prop policy in City Shape (CITYSHAPE_REQUESTS #3), vegetation art in Streetscape; AgentConfig from edge class, capacity and parking supply fed to SkysterTraffic; vehicle sets as a pack. Done when: vehicle and prop packs replace without touching layers 0–5 and traffic density follows edge class.
9. **Phase 8 — Creator experience.** The in-game editor and the MCP link over City Shape's ops (already pure and diffed): terrain seed or import, population, style pack, per-stage re-run, progress per stage, export. Done when: a new user gets a playable city in under 10 minutes without reading docs.

## Rules for the management agent
- Never start a phase N+1 task while phase N's definition of done is unmet, except data-only rows in Catalog/, Rules/ and Styles/.
- Prefer tasks that make the thin slice pass over tasks that make one layer prettier. The deferred realism list in Design/ROADMAP.md (floating bases, ground surfaces, roofs) stays deferred until phase 4 is done, as Kenny already asked.
- Each task hands an agent: layer, phase, inputs available, output expected, validator to satisfy, fixture to update, invariant labels that apply.
- Re-rank the gaps and update the current-state table in the State & Gaps document after every merged milestone, in the same PR.
- One PR per layer per task; a PR that touches two layers is two PRs or a contract change.

## Agent operating rules
An agent that has never seen this project should be productive within one read of this document and one read of its assigned layer's README. These rules make that true.

### Orient (before any change)
1. Read this document top to bottom. Find your task in the Build Path; note its layer and phase.
2. Read Layers/<N>_<Name>/README.md: what it reads, what it publishes, current status, known gaps.
3. Read the schema files for that layer's input and output. Run the layer's fixture test and confirm it passes before you touch anything.
4. State in your first message: layer, phase, the exact contract fields you will touch, and whether any other layer's interface changes. If it does, stop and raise a contract change first.

Until the per-layer READMEs exist (phase 0), the orientation set is: AGENTS.md → docs/AGENT_OPS/INVARIANTS.md → this document → the header docstring of each module you will touch → the matching test_*.py. Run `python3 -I Scripts/city/test_city.py` and `python3 -I Scripts/roads/test_profiles.py` before changing anything; both print OK. Leave a reconcile marker in docs/AGENT_OPS/QUEUE/reconcile/ and a PROGRESS_LOG.md entry with every PR, as the invariants file already requires.

In building-types the orientation set is: README.md → CLAUDE.md → Design/handoff/HANDOFF.md (branches, pipeline, commands, pitfalls) → this document → the mechanic's own brief and report (Design/CITY_SHAPE.md + CITYSHAPE_REPORT.md, Design/STREETSCAPE_*.md + STREETSCAPE_REPORT.md) or the type's Design/<TYPE>_RULES.md. A type session commits only on type/<type>; a shared change goes on shared/<topic> and must keep the walk-up fingerprint byte-identical; a cross-mechanic ask goes in <MECHANIC>_REQUESTS.md, never as an edit to the other mechanic. Use `/usr/bin/python3 -I` on the main Mac. Grade every visual pass against Design/handoff/CHECKLIST.md with named shots.

### Work
- One layer per task. Do not reach into another layer's internals to make your layer work; if you need data it doesn't publish, that is a contract change.
- Data over code: new building types, rules, style packs and parking ratios are rows in Catalog/, Rules/ and Styles/, never new branches in generator code.
- Determinism is a requirement: same seed, same output. Any randomness goes through the seeded stream passed in; never rand() directly.
- Every output passes its validator before the task is done. A validator that doesn't exist yet is part of the task.
- Keep the fixture current: if your change alters the golden output legitimately, regenerate it and say why in the PR.
- Unreal specifics: generators are editor-time (Editor Utility / PCG / Blueprint or C++ callable), outputs are DataAssets or DataTables, geometry uses ISM/HISM or PCG spawners, never hand-placed actors. No hard references to a specific asset pack inside a generator; go through the style resolver.

### Report (every task ends with this)
- Update the layer README's status line and known gaps.
- Append one line to Docs/CHANGELOG.md: date, layer, what changed, schema version if bumped.
- If a contract changed, add Docs/decisions/NNNN-<title>.md: what changed, why, what it invalidates downstream.
- Tell the management agent: done / blocked / needs a contract change, and the next smallest task you see in this layer.

## Contract change procedure
1. Propose: name the schema, the field, the reason, and every downstream layer affected.
2. Bump schema_version; update the validator and the fixture for that boundary.
3. Re-run every downstream fixture. Anything that fails is part of the change, not someone else's problem.
4. Record the decision; then merge.

## Definition of done for any layer
- Runs alone from fixture input and matches golden output.
- Validator exists and passes.
- README states reads, publishes, status, gaps.
- Can be invalidated and re-run by the pipeline runner without manual steps.

## Owner decisions recorded 2026-10-25
Recorded from Kenny on voice (Oct 25, 2026). These move out of State & Gaps Open Decisions. All four Phase-0 decisions are settled.

1. **Spine document:** City Shape document v1 is the master city document. sky-city's generator becomes an OSM importer that writes a City Shape document, plus a consumer of City Shape export. (Closes gap 1 framing.)
2. **Geometry path:** The kit HISM pipeline in building-types is the shipping path. The sky-city Blender mesher is the study tool only. LOD and pack work (gap 10) target the HISM path.
3. **First product (phase 2 order):** Seeded test city first — roughly a quarter the size of SkyCity — so Kenny can play with it and get a feel before applying the approach to SkyCity. Long-term goal remains recreating something like SkyCity with what is built here. Chicago + Austin OSM mashup follows after the seeded path proves out. (Seeded generator / gap 9 before mashup importer priority in phase 2.)
4. **Type-lane merge cadence:** Merge at sign-off — when Kenny visually signs off a type (or a mechanic pass), it lands on main that same day and joins the citywide test street. Not batched.

### Standing expectation (2026-10-25)
Kenny expects to make upgrades as development goes — for example, the base asset collection may be entirely replaced with upgraded assets, or old assets improved and swapped in. That kind of change may alter prior work. Lanes and merges must assume assets are not frozen; style packs / asset swaps are normal, not exceptional invalidations of the shipping path.

