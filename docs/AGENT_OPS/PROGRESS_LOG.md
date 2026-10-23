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

## 2026-10-23 06:30 UTC — cursor cloud agent — texture pack floor wrap and equipment
- State at start: `cursor/texture-pack-loader-04ef` (PR #5) at `28eb643`. A cold audit of the loader: upper floors missed the tile's window rects, and `floors_in_tile` never survived `normalize_set`.
- Did: commit `953399e`. `_for_floor` uses `floor % floors_in_tile`, so a 2-floor tile's row 0 is the rect on building floors 0, 2, 4 while the glass mask stays. `normalize_set` keeps `floors_in_tile`, `bays_in_tile`, and window `wrap_group` / `pieces`. The `equipment/` folder loads as its own kind and is stamped on the building. `python3 -I Scripts/city/test_packs.py` 6 OK, `python3 -I Scripts/city/test_city.py` 46 OK. Sample hash unchanged. An AI wrote this.
- Found: without the modulo, floors 2+ took grammar rects (sill at v 0.22) under the real glass mask.
- Asks for Kenny: none
- SCALE CHECK: no change
- Next: when `Art/ai_textures/` lands, the same schema picks it up

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
