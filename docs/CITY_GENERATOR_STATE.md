# City Generator — State & Gaps
Oct 25, 2026 · @Kenny

## How to use this document
This is the living record of where the city generator stands against the Master Vision. The Vision changes when the owner changes his mind; this document changes every time a milestone merges. The management agent owns it.

- Update on every merged milestone: the Current State row for that layer, the gap it closed or narrowed, and the "Where we are" line. Re-rank the gaps if the order changed.
- Update on every owner decision: move the item from Open Decisions into the Vision (contract or build path) and note the date here.
- Never put here: rules, contracts, or phase definitions. Those live in the Vision; this document only says how far along they are.
- Commit as docs/CITY_GENERATOR_STATE.md in both repos next to the Vision; the dated progress logs (docs/AGENT_OPS/PROGRESS_LOG.md, the *_REPORT.md files) stay the per-shift detail that feeds this summary.

## Current state (read 2026-10-25)
The system lives in two repos. sky-city (public) holds the OSM-seeded mashup generator: a versioned city model, per-layer regeneration, lots, a seven-style shape grammar, income tiers, texture packs, a Blender mesher and an Unreal importer; as of 2026-10-23 it generates Chicago + Austin at seed 7 (3,336 buildings, 1,635 driveable roads). building-types (private, cut from sky-city at walkup-signoff on 2026-10-24) holds the newer kit pipeline, the building-type lanes, and three mechanics on their own branches: City Shape (road graph, draw layers, sites, wires, placement checklist), Streetscape (sidewalks, curbs, grade blending) and Store names. Neither repo has a terrain layer.

### sky-city, mapped onto the contract (Scripts/city/, Scripts/roads/, Scripts/streets/)

| Contract layer | What exists today | Where | Status |
|----------------|-------------------|-------|--------|
| 0 Terrain | Nothing in the generator. Everything sits on z = 0 with a concrete plinth. Chicago water and parks are bespoke editor scripts; McGregor has its own terrain_*.f32. | Scripts/roads/place_chicago_water_ue.py, place_chicago_parks_ue.py, Scripts/mcgregor/ | Not started as a layer |
| 1 Infrastructure graph | Roads are a flat centreline list (cls highway/major/mid/minor, lanes, oneway, core, name). network.py splits crossings and T-junctions into edges and walks faces. roadnet.py (143 KB) builds the full-city network from OSM. profiles.py holds cross-sections. Stages 2–4 of the road roadmap are written down and not built. | Scripts/city/network.py, Scripts/roads/roadnet.py, profiles.py, ROADMAP.md | Partial |
| 2 Zoning | Districts carry a character and one of nine district types with heights, roofs, materials, wear, furniture, nested mixes. Houses and apartments get income tiers (high/mid/low/distressed) setting lot sizes, setbacks, coverage, upkeep, parked cars per 100 m, lighting, sidewalk condition. Blocks from road faces; lots by frontage-first subdivision with alleys. | districts.py, skyline.yaml, lots.py, model.py | Built, flat-ground only |
| 3 Placement | Per-lot style roll, hero towers by rank and spacing, surveyed OSM heights honoured, vacant and informal lots on distressed tiers. No catalog beyond residential, mixed and industrial; no scoring; no parking lots or garages. | model.py, districts.py | Minimal |
| 4 Building generators | One shape grammar, seven styles: massing, setbacks, podium and tower, bays, five roof types, roof units, balconies, per-room interiors, storefronts. Mesher pinned to Blender 5.2 LTS, UV density and window-aspect checks within 3 %, geometry census. | grammar.py, grammar.yaml, realism.py, blender_city.py, census.py, face_uv.py | Built for residential, office and industrial masses |
| 5 Props | Sidewalks, curbs, gutters, parkway, crosswalks, ramps, lane paint; stage-1 dressing (signals, stop/yield, street names, arrows, stalls, parked cars, bus stops, district wear). | streets.py, Scripts/roads/dressing.py | Built |
| 6 Agents and vehicles | In-game traffic on traffic.json; flying cabs; stand-in vehicles. Not driven by generator capacity data. | Source/SkyCity/SkysterTraffic.*, Scripts/vehicles/ | Separate system |
| 7 Style | Texture-pack loader with manifest schema, CC0 fallback, 1,384 AI PNGs in nine packs, procedural grime, M_Facade master. Textures only. | packs.py, facade_grime.py, SourceArt/ai_textures/ | Built for textures only |
| Cross-cutting | city_model.schema.json v1 with source and locked on every element; model.regenerate(layer) district-scoped, non-destructive; deterministic manifest_hash (Warden-checked); operations.py with 17 ops and an audit trail. Tests via python3 -I: test_city.py 46, test_packs.py 9, test_profiles.py 12. | model.py, schema.py, operations.py, seeder.py | Built |

### building-types, mapped onto the contract (main plus type/* and shared/* branches)

| Contract layer | What exists | Where | Status |
|----------------|-------------|-------|--------|
| 0 Terrain | Nothing. City Shape "has no elevation yet"; Streetscape runs on a SyntheticGrade and its pass 3 is "read lot z0 from the city document's heightfield". | streetscape/grade.py, CITYSHAPE_REPORT.md bite C | Not started; both mechanics waiting |
| 1 Infrastructure graph | City Shape document v1 (frozen 2026-10-24): nodes with kinds incl. interchange; edges with class (highway / arterial / collector / local / alley), lanes, bridge, tunnel, stub; class-pair connection rules; one connected network; frontage reach per class (20/15/12/8 m). 24 pure editor ops, CLI, 68 tests. No generator: roads are drawn by a person or an LLM. | type/cityshape: cityshape/schema.py, validate.py, ops.py, Design/CITY_SHAPE.md | Built as editor and validator |
| 0/2 Geography and zoning | Draw layers water, beach, waterfront_walk, access_point, park, plaza, structure_zone, wire_corridor with interaction rules. Districts carry kind plus skyline character / district_type; exported to skyline_districts.json. Water is a drawn polygon. | validate.py check_layers, compat.py | Built (2-D only) |
| 3 Placement | Typed sites (hospital, school, big_box, ev_lot, parking_garage, surface_lot, fire_station, landing_pad, substation, …) with a 21-rule checklist as data; priorities 1–3 = error / warning / note; add_site returns the checklist. Nothing proposes sites. | validate.py PLACEMENT_RULES, wires.py | Validation built; generation missing |
| 1b Utilities | Wire graph (power, charging, rail power; data separate), substations as roots, provisional kW capacity, routing along roads or corridors, six checks, all warnings until a consumer reads the graph. | cityshape/wires.py | Built, provisional |
| 4 Building generators | Kit pipeline: test_block.py → kit_layout.build_layout (registry: any package with KIT_TYPE) → style_kit → layout + spawn JSON → blender_facade_kit.py → import_test_street_ue.py → city_materials_ue.py + kit_city_ue.py (HISM sublevels, shadow proxies, mesh decals, shop interiors). Gates: clean load 0/0, RERUN SAME, GPU budget, 27-item checklist. Types: walk-up signed off on main; condo pass 6c (38 PASS / 2 FAIL); skyscraper (28 PASS); branches cut for houses, parking, schools, civic, hospital, hotel, retail, warehouses, venues, transit, university (heads not read). Two machine lanes per BUILDER_BACKLOG.md. | kit_layout.py, style_kit.py, walkup/, type/*, HANDOFF.md | Pipeline built; 1 type on main, 2 in review, 11 branches open |
| 5 Props and streetscape | Lot → zones with per-family profiles; 4.6 m band; curb reveal 0.10–0.30 m; transitions flush / slope / ramp / stair; retaining walls, aprons, driveways, lay-bys, alleys on the lower rear grade; typed props; export to kit pieces; open lot; reader for City Shape blocks; 44 tests; hook on main behind BT_STREETSCAPE. Pass 2b (meshes, swatches) and pass 3 (heightfield) open. | type/streetscape, STREETSCAPE_REPORT.md | Built for flat and synthetic grades |
| 6 Agents and vehicles | None here. | — | Not started |
| 7 Style | style_kit tables (swatches, flats, panes, shop glass, decals); every texture generated in-repo; Megascans optional, never committed. Not a swappable manifest yet. | style_kit.py, city_materials_ue.py | Partial |
| Cross-cutting | City Shape exports (parcels.json, streetscape_blocks/*.json, skyline_districts.json, manifest.json) derived and deterministic; errors block export. Branch discipline: type/<type> owns its folders; shared/<topic> keeps the walk-up byte-identical; <TYPE>_REQUESTS.md for cross-mechanic asks; locked decisions dated. | export.py, compat.py, HANDOFF.md §0 | Built |

The two repos do not share a city document: sky-city's city_model v1 and City Shape's document v1 describe the same thing twice, and City Shape's export translates its classes back to sky-city's. That is gap 1.

## Gap analysis
Two holes dominate: two city documents with no declared spine, and no terrain under either. After those the pattern is consistent: validation exists where generation is missing, and the work is spread over 36 branches with one building type on main. Ranked by how much each blocks, with the smallest fix that closes it. Phase numbers refer to the Vision's build path.

| # | Gap | Why it blocks | Evidence | Smallest fix | Phase |
|---|-----|---------------|----------|--------------|-------|
| 1 | Two city documents, no declared spine. sky-city city_model v1 and City Shape document v1 both claim to be the city. | Every module has to pick one; the OSM seeder, lots, grammar and mesher read the old one, streetscape, store names and kit types read the new one. | cityshape/compat.py maps classes back; seeder.py builds city_model; CITY_SHAPE.md §1. | Declare City Shape v1 master. sky-city seeder.py + roadnet.py become an OSM importer writing a City Shape document; model.regenerate consumes the export. Record in CITY_SHAPE_RULES.md. | 0 |
| 2 | No terrain layer. Water is a drawn polygon; elevation exists nowhere. | Streetscape pass 3, City Shape bite C, Chicago water scripts and every flat plinth wait on it. | CITYSHAPE_REPORT.md; streetscape/grade.py; generate_city.py z = 0. | terrain in the City Shape document (heightfield ref, slope, buildable mask, flow) with a seeded generator and an importer; water snaps to it; Streetscape reads lot z0. | 1 |
| 3 | Placement validates but does not generate. The 21-rule checklist judges a site; nothing proposes one. | The "randomized logic that makes sense" is the generator, not the checker. | CITY_SHAPE.md §4; no propose_* op. | place.py: enumerate candidates per catalog type, score with PLACEMENT_RULES (errors reject, warnings cost, affinities bonus), take the best, re-validate. | 4 |
| 4 | No population or demand model. No residents, jobs, beds, seats. | Supply targets and parking demand have no input. | skyline.yaml has coverage and tiers only; wires.DEMAND_KW is the only demand table. | Residents and jobs per site or lot from floor area and type; totals per district and township; supply-target table per type. | 3 |
| 5 | Parking is checked, not balanced. Garage and lot site types exist with proximity rules; no totals. | Towers, hospitals, stadiums get no parking unless a person adds it. | PLACEMENT_RULES; dressing.py stalls. | Demand per site from gap 4; supply from frontage, lots, garages; the placer adds parking until supply ≥ demand per district. | 4 |
| 6 | No townships, city edge or civic minimums. stub edges exist; no partition; no per-township rule. | The township rule has no unit. | CITY_SHAPE.md §2. | Cluster the graph by distance and density; township_id on districts; civic minimums as supply rows keyed by township. | 2 |
| 7 | No end-to-end runner. The chain export → cityshape-blocks → kit_layout → import is four CLIs in three worktrees; sky-city regenerate is separate. | Upgradability is only real when one command re-runs from any stage. | CITYSHAPE_REPORT.md commands; HANDOFF.md §2. | pipeline.py with stages, fixtures, golden outputs, dirty tracking, one --fixture larkhaven run. | 0 |
| 8 | Branch and merge debt. 16 type/*, 3 mechanics, 20 shared/*; only the walk-up on main; binaries never merge. | The city cannot be assembled from types on different branches; contract drift shows up late. | Branch list 2026-10-25; HANDOFF.md §0; CITYSHAPE_REPORT.md bite G. | Merge cadence (type at sign-off, mechanic per pass) and a citywide test street on main as the integration gate. | 0 |
| 9 | Seeded road generation does not exist. Ops and validator exist; a blank document stays blank. OSM roads live only in sky-city. | Seed → playable city is not reachable. | ops.py has add_edge, no generate. | After gap 2: a generator calling the same ops (stubs → highway with interchanges → arterials → collectors → locals) that must validate clean; the OSM importer is the other entry. | 2 |
| 10 | Style packs are tables, not manifests. style_kit and per-type textures are the right shape but not swappable without code. | "Upgrade the look" is a code change. | style_kit.py; Megascans optional in HANDOFF.md. | StylePack JSON manifest (slot → swatch, mesh, material); kit_style_materials and the importer resolve through it. | 6 |
| 11 | Vehicles and traffic are decoupled. SkysterTraffic reads a separate traffic.json. | Swapping vehicles or scaling by road class is manual. | sky-city SkysterTraffic.*. | Emit AgentConfig from the graph and parking supply; vehicle sets as a pack. | 7 |
| 12 | Wires have no consumer. Every check is a warning; kW are placeholders. | Harmless now; a gap once charging or lighting drives placement. | CITY_SHAPE.md §8. | First consumers: the EV placer and street lighting; flips the relevant checks to errors as the rules say. | 4 |
| 13 | Docs split across two repos; no layer index. sky-city AGENTS.md does not mention building-types; building-types says "no city generator here". | A new agent cannot find the spine in one read. | AGENTS.md, README.md, three *_REPORT.md. | Commit the Vision and this document to both repos, link from AGENTS.md / CLAUDE.md, README per layer. | 0 |

## Open decisions for the owner
Each of these blocks a phase-0 task. When decided, the answer moves into the Vision and this list shrinks.

### Recorded 2026-10-25 (all four Phase-0 decisions closed — moved into Vision)
- [x] **City Shape v1 master** — sky-city becomes OSM importer + consumer (gap 1).
- [x] **Geometry path** — kit HISM shipping; Blender mesher study-only (gap 10 targets HISM).
- [x] **First product** — seeded test city first (~¼ SkyCity size) so Kenny can play-test the feel before applying to SkyCity; long-term still recreate something like SkyCity. Mashup (Chicago + Austin OSM) after. Phase 2: seeded generator before mashup importer.
- [x] **Merge cadence** — at sign-off (not batches). Types/mechanic passes land on main the day Kenny visually signs off.

### Standing note (2026-10-25)
Assets are not frozen. Base packs may be replaced or upgraded mid-development; prior work may change. Lanes/merges assume swappable assets.

### Still open
_(none for Phase 0)_

## Where we are
Phase 0 (Spine) has not started; phase 5 (Building types) is running ahead of it in two lanes. That is fine for content, because a type is built on a fixed layout contract, but nothing in phases 0–4 is done: no declared spine, no terrain, no runner, no generative placement, no population model. City Shape and Streetscape are the strongest pieces of phases 1–4 and are both complete to their own pass plans.

**2026-10-25 owner update:** All four Phase-0 decisions recorded (City Shape master, HISM shipping, seeded test city first, merge at sign-off). Asset-upgrade standing note recorded. Phase 0 unblocked for BuildingTypes Lead (docs PRs + spine).
