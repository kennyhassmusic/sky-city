# Progress log — Sky City agent shifts

One entry per shift or shipped change. Newest first. Mirror of the LUCA ledger (`luca ledger --repo skycity`).
Keep to facts an agent or Kenny can act on: paths, commits, PRs, review states, asks. No secrets.

## Template
```
## YYYY-MM-DD HH:MM CDT — <agent> — <one-line outcome>
- State at start: branch <…>, tests <…>
- Did: <changes with commit hashes; tests>
- Found: <bugs / red flags> → <fixed / escalated>
- Asks for Kenny: <bulleted, or "none">
- SCALE CHECK: <"no change" | path to the note>
- Next: <one line>
```

## Entries

## 2026-10-23 20:45 UTC — Claude (claude.ai cloud) — JOB 2: PR stack re-ordered locally, not pushed
- State at start: #3 on `main` (4 behind), #4 and #5 both on #3, #6 on #4 (without #5), #7 on #5; tests OK on all five heads
- Did: rebased locally to `main` ← #3 `788c507` ← #5 `fe5bd70` ← #4 `e150ce8` ← #6 `466ea12`, and #5 ← #7 `7cc1f27`. Only `PROGRESS_LOG.md` conflicted (union, newest first). Tests after each rebase: test_packs (where present), test_city, test_profiles all OK. Marker: `docs/AGENT_OPS/QUEUE/reconcile/2026-10-23-job2-pr-stack-order.md`
- Found: #6 sat on #4 (road dressing), which was not in the brief, and did not include #5 → #4 moved onto #5 so #6 gets both. #7 is ~887 MB of LFS, over the 300 MB per-PR guard → needs `maintainer-approved`. Committed sample outputs on #4/#6 still carry the pre-dressing hash (pre-existing).
- Asks for Kenny: review `JOB2_REPORT.md`, then run its push and `gh pr edit 4 --base` commands; merge #3, #5, #4, #6, #7
- SCALE CHECK: no change
- Next: after each squash merge, rebase the next branch with `--onto origin/main <old parent tip>`

## 2026-10-23 06:40 UTC — cursor cloud agent — per-set texel density check
- State at start: `cursor/citywide-generate-04ef` (PR #6) at `71361ec`. Mesh faces already pass U/V density within 3%. A set can still stretch when its metres ignore the image aspect.
- Did: commit `132da03`. `face_uv.set_density_ratio` and `score_sets` compare pixels per metre on U and V for each scan, before metres are rewritten to the image aspect. A set outside 3% fails the build. `python3 -I Scripts/city/test_face_uv.py` OK. Exported buildings: UV faces 371996, density fails 0, windows 54448, window fails 0, sets 7, set fails 0. The city cameras were not re-rendered. Loader floor bugs are fixed on PR #5, not on this branch.
- Found: the seven wall and ground scans in `materials.json` are square 1024² with square `uv_m`, so the new check passes. `Leaking006` is 256×1024 and is not one of those sets.
- Asks for Kenny: none
- SCALE CHECK: no change
- Next: still deferred on this branch — floating bases, ground surfaces, roofs.

## 2026-10-23 06:30 UTC — cursor cloud agent — texture pack floor wrap and equipment
- State at start: `cursor/texture-pack-loader-04ef` (PR #5) at `28eb643`. A cold audit of the loader: upper floors missed the tile's window rects, and `floors_in_tile` never survived `normalize_set`.
- Did: commit `953399e`. `_for_floor` uses `floor % floors_in_tile`, so a 2-floor tile's row 0 is the rect on building floors 0, 2, 4 while the glass mask stays. `normalize_set` keeps `floors_in_tile`, `bays_in_tile`, and window `wrap_group` / `pieces`. The `equipment/` folder loads as its own kind and is stamped on the building. `python3 -I Scripts/city/test_packs.py` 6 OK, `python3 -I Scripts/city/test_city.py` 46 OK. Sample hash unchanged. An AI wrote this.
- Found: without the modulo, floors 2+ took grammar rects (sill at v 0.22) under the real glass mask.
- Asks for Kenny: none
- SCALE CHECK: no change
- Next: when `Art/ai_textures/` lands, the same schema picks it up

## 2026-10-23 06:24 UTC — cursor cloud agent — procedural facade grime
- State at start: `cursor/citywide-generate-04ef` (PR #6) at `455e8f5`. Grime was still on the Next list.
- Did: commit `0e7c633`. Wall slots no longer use the leak card or the cracked-concrete multiply. `Scripts/city/facade_grime.py` maps district age and tier to a 0–1 wear (brand_new and tech near zero, historic_old and distressed heavy). The Blender materials in `Scripts/city/realism.py` read that wear from the mesh colour attribute `Col` and add a short bevel for edge chips, ambient occlusion for corners, world-Z drip bands under sills and ledges, and dirt from the sidewalk up to 1.4 m. `Scripts/city/facade_material_ue.py` builds the same graph as `M_Facade` (vertex colour red times WearScale, screen-space curvature, precomputed AO). `python3 -I Scripts/city/test_facade_grime.py` (6 OK). Cycles preview `artifacts/previews/facade_grime.png`: joined wear 0.05 and 0.896, base luma 0.3618 (brand-new) vs 0.2874 (distressed), glass band 0.3782 vs 0.3727. The city cameras were not re-rendered and the GLBs were not rewritten. The Unreal master was not compiled here (no editor).
- Found: Pointiness on one quad per wall sits near 0.7 everywhere, so the edge mask is a bevel. A wide bevel painted the sill and the AC unit white; the radius is 3 cm so only the rim chips.
- Asks for Kenny: run `py Scripts/city/import_city_ue.py` (PIE off) so `M_Facade` compiles. The pin names are resolved in the editor and a missed pin raises.
- SCALE CHECK: no change
- Next: still deferred — floating bases, ground surfaces, roofs, loader floor bugs. Do not start them until asked.

## 2026-10-23 05:50 UTC — cursor cloud agent — Blender 5.2 census and hero sheets
- State at start: `cursor/citywide-generate-04ef` (PR #6) pinned the mesher to Blender 4.2.15.
- Did: commit `a59dfa5`. The mesher now requires Blender 5.2.x LTS on Python 3.13 (ran 5.2.3 / 3.13.13) and `--background --factory-startup --python-exit-code 1`. One unit is one metre and the glTF export is 1:1 (a 2 m cube exported with span 2). Booleans use the EXACT solver and are read with `evaluated_get().to_mesh()` (a cube difference came back with 10 faces). Mesh and object operators are rejected at startup. `Scripts/city/census.py` counts non-manifold edges, loose verts, degenerate faces and BVHTree self-intersections, and fails the build when the base is off the sidewalk (`profiles.CURB_RISE`, 0.15 m), or the footprint or height misses the plan. `python3 -I Scripts/city/test_census.py` (4 OK). `SKYCITY_HERO_ONLY=1` meshed three buildings in 88.8 s, census PASS, and wrote Workbench six-view sheets. The city GLBs were not re-exported and the locked cameras were not re-rendered. Hash unchanged `1e7ebb8635888c40699841b78beac5391e23200eb70247f118f4d0cc2b6390bf`.
- Found: heroes sit on the sidewalk (base 0.150). Counts, not failures: tower `b_lot_osm_702` 70343 faces, nonmanifold 15456, intersect 135852; mid-rise `b_lot_osm_2038` nonmanifold 194, intersect 2553; house `b_lot_osm_160` nonmanifold 191, intersect 2952. Loose 0, degenerate 0. Stacked boxes welded by remove_doubles produce those edges. Sheets: the tower is a slender shaft with a small roof cap; the mid-rise steps back and carries an antenna; the house is one gable. All three meet the ground line. No floating mass and no second building fused on. Workbench drew flat silhouettes.
- Asks for Kenny: none. Still deferred: floating-base fixes (the gate is in), ground surfaces, grime, roofs, loader floor bugs.
- SCALE CHECK: no change
- Next: the deferred list. Do not start it until asked.

## 2026-10-23 05:30 UTC — cursor cloud agent — pin the city mesher to Blender 4.2.15
- State at start: `cursor/citywide-generate-04ef` (PR #6) at `43f0528`. UV pass already pushed. This add-on was requested after the deferred list was written.
- Did: commit `d8e6720`. `Scripts/city/blender_city.py` prints `bpy.app.version` and stops unless it is 4.2.15. The run line in `README.md` includes `--python-exit-code 1`. A Python warning (via `warnings.showwarning`, because an "error" filter is ignored inside a destructor), a deprecated-API log line, or a missing node or socket calls `os._exit(1)`. After creation, each material and UV map is required on the object, and each modifier goes through `_add_modifier` and is checked the same way. `load_material_record` closes its file. Blender 4.2.15 smoke: library of 40 materials plus one box (`M_Brick`, `UVMap`, Bevel) exits 0. A missing socket, `warnings.warn`, a "deprecated" stderr line, and a launch without `--python-exit-code 1` each exit 1. The city was not re-rendered. GLBs and the hash are unchanged.
- Found: `warnings.simplefilter("error")` does not stop the process for a ResourceWarning raised in a file destructor. `showwarning` does.
- Asks for Kenny: none. The mesh census, and the rest of the Next list in `Design/ROADMAP.md`, stay deferred.
- SCALE CHECK: no change
- Next: the deferred list. Do not start it until asked.

## 2026-10-23 05:20 UTC — cursor cloud agent — per-face facade UVs
- State at start: `cursor/citywide-generate-04ef` (PR #6) at `a8e211a`. Kenny: brick windows were wide and short, and tower sides were stretched.
- Did: commits `a4ca888` and `a8d7ef8`. Each face is UV'd from its own width and height (`U = width / meters_u`, `V = height / meters_v`) with one scale on both axes. Whole windows keep the 24×19 lit rect in `T_CG_Facade_*.png`. Leftover length is a pilaster. `python3 -I Scripts/city/test_face_uv.py` checks exported buildings and the Blender build exits if density or window aspect is outside 3%. Commit `9c6b8bf` re-exports the GLBs (47.4 MB, each file under 22 MB) and re-renders downtown street day plus a tower-side close-up. Hash unchanged `1e7ebb8635888c40699841b78beac5391e23200eb70247f118f4d0cc2b6390bf`. UV faces 371996, density fails 0, windows 54448, window fails 0, target aspect 1.2632. Worst density ratio 1.0134 (1.3%). Histograms at exposure 0: downtown street day median 107.3, crushed 0.006, midtones 0.977, p95 193.7; tower side day median 173.1, crushed 0.000, midtones 0.881, p95 212.0.
- Found: the shop-band call was one argument short and stopped the first mesh. Fixed before the render.
- Asks for Kenny: none tonight. Deferred in `Design/ROADMAP.md` under Next: floating bases, ground surfaces, grime, roofs, Blender hardening and a mesh census, six-view sheets, loader floor bugs.
- SCALE CHECK: no change
- Next: the deferred list above. Do not start it until asked.

## 2026-10-23 04:48 UTC — cursor cloud agent — bases, streets and flat roofs
- State at start: `cursor/citywide-generate-04ef` (PR #6) had curtain-wall daylight frames. Kenny: buildings floated, the ground was one olive plane, facade stains looked like holes, and flat roofs were bare.
- Did: commit `1eeae41` in `Scripts/city/blender_city.py`. A concrete plinth meets each wall. The fill plane is concrete at street level. Sidewalks follow the ground-floor frontage. Grass stays on the planned parkway. A street camera that is not on asphalt or sidewalk gets a carriageway under it. Leak decals are skipped. Flat roofs keep a parapet at least a metre tall, plus HVAC, a stair bulkhead and a water tank when the roof record lacks them. Commit `44715a5` replaces the city GLBs (about 85 MB, each file under 22 MB, 22 core buildings) and re-renders the same four cameras. Hash unchanged `1e7ebb8635888c40699841b78beac5391e23200eb70247f118f4d0cc2b6390bf`. Tests: `python3 -I Scripts/city/test_generate_city.py` (OK), `python3 -I Scripts/city/test_city.py` (46 OK). Histograms at exposure 0: aerial day median 143.3 (crushed 0.000), downtown street day 77.5 (0.007), residential day 132.6 (0.005), downtown street dusk 85.2 (0.006, p95 203.5).
- Found: both street cameras were standing off the planned asphalt, so the shot laid a carriageway under them. The script cap meshes 22 core buildings; the previous GLBs had 14.
- Asks for Kenny: PIE off, `py Scripts/city/import_city_ue.py`, open `SkyCityGenerated`. The GLBs are still the downtown cluster and one residential street.
- SCALE CHECK: no change
- Next: mesh more of the core when a larger LFS budget is available. Do not start road stages 2–4 or pack polish unless asked.

## 2026-10-23 04:40 UTC — cursor cloud agent — curtain walls and real-scale bays
- State at start: `cursor/citywide-generate-04ef` (PR #6) had daylight frames. Kenny: the central tower was a hollow glass cutaway, and some windows were stretched across the wall.
- Did: commit `dfaf119` in `Scripts/city/blender_city.py`. Glazed floors are mullions, a metal spandrel at each slab, tinted reflective glass, and an opaque interior per pane. Facade UVs use meters_u / meters_v from the texture record. Bay count is round(length / bay_m) and the glass stays within that module. Commit `c365320` replaces the downtown GLBs (about 50 MB, each file under 22 MB) and re-renders the same four cameras. Hash unchanged `1e7ebb8635888c40699841b78beac5391e23200eb70247f118f4d0cc2b6390bf`. Tests: `python3 -I Scripts/city/test_generate_city.py` (OK), `python3 -I Scripts/city/test_city.py` (46 OK). Histograms at exposure 0: aerial day median 138.4 (crushed 0.002), downtown street day 66.4 (0.012), residential day 126.1 (0.006), downtown street dusk 86.9 (0.012, p95 203.5).
- Found: a glass wall slot used the clear pane shader, so the slab edges and the empty upper floors showed through. Upper room shells on towers are not built; the pane back is the interior.
- Asks for Kenny: PIE off, `py Scripts/city/import_city_ue.py`, open `SkyCityGenerated`. The GLBs are still the downtown cluster and one residential street.
- SCALE CHECK: no change
- Next: mesh more of the core when a larger LFS budget is available. Do not start road stages 2–4 or pack polish unless asked.

## 2026-10-23 04:20 UTC — cursor cloud agent — daylight and dusk previews
- State at start: `cursor/citywide-generate-04ef` (PR #6) at `67e1f29`. Meshes in `9c82632`. The Cycles frames were crushed; the residential street median luma was 1.
- Did: commit `a46b4e9` relights `Scripts/city/blender_city.py` only (CC0 Poly Haven `kloofendal_43d_clear_puresky` plus a sun, AgX, no world volume; dusk uses `kiara_9_dusk`, sun elevation 4.5°, windows glowing). Commit `8d07576` adds `artifacts/previews/sky_city_*_{day,dusk}.png`. Cameras stayed the ones in `city_manifest.json`. GLBs were not rewritten. Hash unchanged `1e7ebb8635888c40699841b78beac5391e23200eb70247f118f4d0cc2b6390bf`. Test: `python3 -I Scripts/city/test_generate_city.py` (OK). Cycles 24 samples, denoise, 1280×720. Histograms passed at exposure 0: aerial day median 138.2 (crushed 0.001), downtown street day 74.5 (0.011), residential day 126.3 (0.006), downtown street dusk 84.8 (0.012, p95 206.5).
- Found: the block Filmic grade, a world volume, and generated-coordinate HDRI mapping were what crushed the streets. An unconnected environment vector plus the sun lamp lights the same cameras.
- Asks for Kenny: none beyond the earlier import note. PIE off, `py Scripts/city/import_city_ue.py`, open `SkyCityGenerated`.
- SCALE CHECK: no change
- Next: mesh more of the core when a larger LFS budget is available. Do not start road stages 2–4 or pack polish unless asked.

## 2026-10-23 04:05 UTC — cursor cloud agent — real meshes for downtown and one residential street
- State at start: `cursor/citywide-generate-04ef` (PR #6) had the spawn record and cube import. Flat street preview was colour planes.
- Did: commit `9c82632`. `Scripts/city/blender_city.py` builds LOD0 with the CG block facade, roof and storefront path. Chicago core cluster (14 buildings) and one Austin low-rise street (high beside mid) are chunked GLBs under `SourceArt/CityGen/city/` (about 66 MB, each file under 22 MB). Street surfaces and simple dressing props are in the street chunks. Trees are not meshed. `import_city_ue.py` imports those GLBs into `/Game/Maps/SkyCityGenerated` at the origin and binds the existing CC0 scans. Cycles previews: downtown aerial oblique, downtown street, residential street. Hash unchanged `1e7ebb8635888c40699841b78beac5391e23200eb70247f118f4d0cc2b6390bf`. Test: `python3 -I Scripts/city/test_generate_city.py` (OK).
- Found: the block volume haze blacks out the sky at city clip range → density lowered for these shots. A residential camera inside a footprint rendered black → the eye now sits off the pair of houses.
- Asks for Kenny: PIE off, `py Scripts/city/import_city_ue.py`, open `SkyCityGenerated`. The GLBs are the downtown cluster and one residential street, not all 3,336 lots.
- SCALE CHECK: no change
- Next: mesh more of the core when a larger LFS budget is available. Do not start road stages 2–4 or pack polish unless asked.

## 2026-10-23 03:30 UTC — cursor cloud agent — generate the mashup city
- State at start: street dressing on `cursor/road-dressing-stage1-04ef` (PR #4). Pack polish and road stages 2–4 deferred. Invariants read. City Sample plugin still present.
- Did: `Scripts/city/generate_city.py` runs the generator over `buildings_v3.json` footprints and `plan_v3.json` roads (seed 7). 3336 buildings, 1635 driveable roads, sidewalks, curbs, parkway on 369 roads, stage-1 dressing. Spawn `Scripts/city/examples/sky_city_spawn.json`. Editor import `Scripts/city/import_city_ue.py` creates `/Game/Maps/SkyCityGenerated` under `/Game/City/Generated` and does not open SkyCityMashup. Hash `1e7ebb8635888c40699841b78beac5391e23200eb70247f118f4d0cc2b6390bf`. Test: `python3 -I Scripts/city/test_generate_city.py` (two builds match). Commit `35b8bdd`. PR https://github.com/kennyhassmusic/sky-city/pull/6
- Found: a camera aimed along a centreline looked at empty pavement → street preview now faces a downtown facade.
- Asks for Kenny: run `py Scripts/city/import_city_ue.py` with PIE off, then open `SkyCityGenerated` next to the City Sample map.
- SCALE CHECK: no change
- Next: Kenny compares the generated level with City Sample. Do not start road stages 2–4 or pack polish unless asked.

## 2026-10-23 03:05 UTC — cursor cloud agent — texture pack loader schema
- State at start: branch `cursor/texture-pack-loader-04ef` off `cd8b893`. AI packs are not on main (`art/ai-texture-packs` is not a remote branch).
- Did: `Scripts/city/packs.py` loads the manifest schema (role basic|accent, suggested use, district/tier, power-of-two size, scale_m, per-facade glass masks, window/bay/floor rects, decal alpha). `packs/districts.json` mix: one basic body, optional crown/ground-band/corner accent, neighbors avoid repeating a basic. Potholes and stains stay decals. Missing art falls back to CC0. `assign_textures` stamps buildings without changing the sample hash `3b867770796a5ab07187d1c962f2f6a6d91a00b6b8eab4b6466ccbabdf50632b`. Tests: `python3 -I Scripts/city/test_packs.py` 3 OK, `python3 -I Scripts/city/test_city.py` 46 OK. Commit `784177c`. PR https://github.com/kennyhassmusic/sky-city/pull/5
- Found: none
- Asks for Kenny: none
- SCALE CHECK: no change
- Next: when `Art/ai_textures/` lands on main, point the loader at it; no schema change expected

## 2026-10-23 02:50 UTC — cursor cloud agent — road dressing stage 1
- State at start: branch `cursor/road-dressing-stage1-04ef` off `cursor/city-block-realism-04ef` (`cd8b893`); city tests 46 OK, profile tests 12 OK
- Did: `Scripts/roads/dressing.py` dresses existing centrelines (signals, stop/yield, street names, arrows, keep-clear, stalls, parked cars, bus stops, district wear). Stages 2–4 are described in `Scripts/roads/ROADMAP.md` and not built. Commit `8c307c2`. Tests: `python3 -I Scripts/roads/test_dressing.py` 5 OK, `python3 -I Scripts/city/test_city.py` 46 OK, `python3 -I Scripts/roads/test_profiles.py` 12 OK. Sample hash `6ffee243bf43fe6d29c2e1cd14880e731374590f7ca4fde6e7eefaed15ecdb8d` (two builds matched). Plan previews in the PR artifacts, not committed. Marker: `docs/AGENT_OPS/QUEUE/reconcile/2026-10-23-road-dressing-stage1.md`. PR https://github.com/kennyhassmusic/sky-city/pull/4
- Found: signs placed next to the first lamp were dropped when that lamp was locked (1.5 m merge) → signs sit in the corner-clear gap. Mid-edge crossings are not junctions; stage 2 owns a real graph.
- Asks for Kenny: none
- SCALE CHECK: no change
- Next: stage 2 road graph (types, intersections, medians) when asked

## 2026-10-23 02:40 UTC — cursor cloud agent — per-room interiors on PR #3
- State at start: branch `cursor/city-block-realism-04ef`, parent `e1f8edf`, city tests 41 OK, profile tests 12 OK
- Did: room volumes in `Scripts/city/grammar.py` (`layout_rooms`, `room_of`); preview shell in `realism.build_rooms` and `blender_block.py`; streetscape assertion for parkway, sidewalk, straight curb and curb return. Commit `2c569c5`. Tests: `python3 -I Scripts/city/test_city.py` 46 OK, `python3 -I Scripts/roads/test_profiles.py` 12 OK. Sample hash unchanged `3b867770796a5ab07187d1c962f2f6a6d91a00b6b8eab4b6466ccbabdf50632b`. Marker: `docs/AGENT_OPS/QUEUE/reconcile/2026-10-23-pr3-per-room-interiors.md`. PR https://github.com/kennyhassmusic/sky-city/pull/3
- Found: interiors were per window (one card and one light roll per bay) → rooms share one id, one light and one curtain. Grass, sidewalks and curbs were already in the streetscape; the test now names them.
- Asks for Kenny: none
- SCALE CHECK: no change
- Next: bind a parallax interior material in the editor from `rooms` and `bay_rooms`

## 10/22/2026, 20:14:36 CT — Reconciled (grok) — reconcile-20261023T011436: Register sky-city with LUCA
- State at start: branch `main` off `main`; host Worship-Al-Pastor-2
- Did: reconciled; 0 files changed; ? turns; $0.00; no PR
- Found: Warden PASS — 
- Asks for Kenny: none
- SCALE CHECK: no change
- Next: Verifier/Manager reviews; ledger `luca ledger --repo skycity`; session log `n/a`
