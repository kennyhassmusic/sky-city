# Chicago generated map: report

Branch `cursor/chicago-gen-map`. Pass 1 is `4e33b22`: region crop, Blender export, UE import, drivable. Pass 2 is
this commit, which fixes the import pipeline: Draco and street tiles, import bugs, the facade kit with HISM, and box
collision. Committed locally, not pushed or merged. The generator (`generate_city.py`, `block.py`, the city model)
is unchanged: both spawn hashes are the same as in pass 1.

## Pass 2 in one table

The Chicago Loop level `/Game/Maps/SkyCityChicagoGen`, before (4e33b22) and after (this commit). Same machine,
same cameras, same scripts.

| | Before: baked GLBs + boxes | After: facade kit (HISM) |
|---|---|---|
| Real towers | 58 meshed, 296 boxes | **354 of 354** |
| Load (load_map until render data is ready, warm DDC) | 1.03 s | **0.72 s** |
| Actors / mesh components | 2,217 / 2,212 | 45 / 282 (264 HISM) |
| Drawn mesh sections (draw-call proxy) | 2,494 | **982** |
| Triangles (LOD0, instances counted) | 2.81 M | 8.67 M (×6 the real buildings) |
| GPU frame, aerial camera | 17.3 ms | 23.3 ms |
| GPU frame, street camera | 20.0 ms | **17.8 ms** |
| Memory the level adds: process physical | +2,091 MB | **+1,419 MB** |
| RHI vertex / index buffers | +112 / +64 MB | **+42 / +16 MB** |
| UObject resources | +576 MB | **+256 MB** |
| Level files | 3.5 MB (one map) | 0.06 MB map + 92 MB in 11 tile sublevels (largest 18 MB) |
| Imported content (`Content/City/Generated/Chicago`) | 45 MB | 33 MB (kit modules 1 MB) |
| SourceArt GLBs | 228.6 MiB, 13 files, largest 28.6 MiB | 90.9 MB, 33 files Draco, largest 21.5 MB (street tiles 0.7 MB) |
| Wall ride | stuck at 0 mph about 8 m up | rides the full 263 m face of `b_lot_osm_332` |

How it was measured:
- **Load and scene numbers:** `Scripts/city/measure_city_ue.py`. It runs at editor startup from an empty map, with
  synchronous mesh compilation.
- **GPU:** the inclusive `<root>` time from `ProfileGPU` in the editor viewport, mean of 3 frames. Aerial camera
  (-175000, -80000, 55000) at pitch -24, yaw 30; street camera (-84000, -23500, 250) at pitch 2, yaw 60.
- **Memory:** `memreport -full` with the level loaded, minus one taken with `/Engine/Maps/Entry` in the same editor
  session. Read with `python3 Scripts/city/measure_city_ue.py --memreport <file>`.
- **Draw calls:** Metal's ProfileGPU reports 0 draws, so drawn mesh sections stand in. Each drawn section is at least
  one draw per pass; a HISM draws all of its instances per section.

The raw numbers are in `Saved/CityGen/measure/` (baseline.json, baseline_live.json, kit.json, proto_*.json).

The aerial frame costs 6 ms more because it now draws 354 real towers (8.7 M triangles) instead of 58 towers and
296 boxes. The street frame is faster, and memory is lower on every line.

## What changed in pass 2

### 0. Answers to the two questions
- **Content deleted in pass 1:** I ran `rm -rf Content/City/Generated/Chicago` once, before the last re-import. I
  created that folder myself and it had never been committed. The importer also deletes inside that folder: the glTF
  placeholder materials (`Meshes/*/Materials`), and `M_*` / `MI_Massing_*` before rebuilding them. Outside Content: my
  own `SourceArt/CityGen/chicago` GLBs before a re-export, and 12 corrupt `.o` files in `Intermediate`. Content/Building,
  Prop, Material, Megascans, Vehicles, Plugins/CitySamplePCG, SkyCityMashup.umap and its external actors have not
  changed (checked with `find -newermt`). Pass 2 deleted only its own scratch prototype levels and folders
  (`Content/Maps/Dev`, `Content/City/Generated/ProtoBaked`, `ProtoKit`) and, through the importer, the old baked
  tower meshes in `Content/City/Generated/Chicago/Meshes`.
- **`Source/SkyCity/SkyCourseBuilder.cpp` in 4e33b22:** one line, written in the claude.ai session. `MapName()` maps
  `SkyCityChicagoGen` to "Chicago Loop (generated)". The Garage map list (`SkyCourseBuilderHud.cpp:561`) and its
  "Opening…" toast (`SkyCourseBuilder.cpp:1428`) show `MapName()` for every entry in `Maps[]`; without the line, the
  new map would show as the raw file name. It is display only. Pass 2 does not touch `Source/` or `Config/`.

### 1. Compression and street tiles (`Scripts/city/blender_city.py`)
- **Draco:** every GLB uses `KHR_draco_mesh_compression`. Unreal 5.8's Interchange glTF reader decodes it on Mac; it
  has no meshopt decoder, so meshopt was not an option. Quantization: positions 20 bits (1.4 mm over 1.5 km),
  UVs 16, normals 10, colours 10. Size per triangle went from 170 to 18 bytes.
- **UV check:** `face_uv.py` parses plain glTF buffers, so each GLB is also written uncompressed to
  `Saved/CityGen/stage/<region>` and checked there. It still prints "UV PASS".
- **Street tiles:** street meshes are cut into 300 m tiles, giving 28 GLBs of at most 0.73 MB. The region-wide
  asphalt, sidewalk, curb and paint meshes are split by face centroid; props share their prototype's mesh and go by
  their origin. A GLB still over the cap after export is halved and written again.
- **Coverage:** with Draco, all 346 meshed buildings fit the 225 MB budget (90.9 MB in total).
- `SKYCITY_DRACO=0` turns compression off; `SKYCITY_STREET_TILE_M` sets the tile size.

### 2. Unreal import bugs fixed
| Bug | Cause | Fix |
|---|---|---|
| Material rebuild failed ("'NoneType' has no attribute 'set_editor_property'") | Deleting a material the loaded level still references fails, and `create_asset` then returns None | `facade_material_ue.fresh_material` / `fresh_instance` empty and reuse an existing asset instead of deleting it |
| Old tower meshes stayed after a re-export (the `core_09` leftover) | The importer never removed mesh folders of GLBs it no longer imports | `_drop_stale_meshes` |
| Every save failed: "Cannot remove … as it is read only!" | `.uasset` and `.umap` are `lockable` in `.gitattributes`, so Git LFS leaves committed copies read-only until `git lfs lock` | `chmod u+w` on the generated files only, done locally; see "Process notes" |
| Box facades blank from the aerial camera | **Not texture streaming.** I checked it: switching NeverStream off and on for the wall textures changes nothing (`ue_neverstream_test.jpg`). It is minification: a 4 m tile of mostly light panel with dark windows averages into one wall colour once a window covers 1 to 2 px | Real towers replace the boxes. Kit windows are geometry with emissive lit rooms and read at any distance (`ue_aerial.jpg`). The streaming change I first tried was taken out again |
| Two street GLBs over the cap | One region-wide object per street layer | Street tiles (above) |
| Wall rides snag on sills | Complex collision on every sill and pier | Box collision (step 4) |

### 3. Facade kit and HISM
- **Modules** (`Scripts/city/blender_facade_kit.py` → `SourceArt/CityGen/kit`, 7 GLBs, 20 KB in total):

  | Module | Triangles | Use |
  |---|---|---|
  | KIT_Wall | 10 | wall bay; also the roof slab and collision |
  | KIT_Pane | 24 | window bay: glass, room back, frame, sill, reveals |
  | KIT_PaneCurtain | 20 | curtain-wall window bay |
  | KIT_Corner | 10 | corner pilaster, a little proud of the wall |
  | KIT_Pier | 6 | pier between panes |
  | KIT_Leaf | 2 | a blind or a curtain leaf |
  | KIT_RoofCap | 20 | parapet with coping |

  Every module is 1 m by 1 m and is scaled per instance. Local +Y always points into the building, so no instance is
  mirrored.
- **Layout** (`Scripts/city/kit_layout.py`, plain Python). It follows the mesher exactly
  (`blender_city._fitted_facade`): the same per-floor facade records, the same `face_uv.fit_bays()` pane fit and
  sill/head rule, the same lit rooms (`grammar.room_of` / `bay_lit`), and the same blinds and curtains
  (`realism.dress_opening`). For the Loop that is 702,138 instances in 25 module and material groups, plus 699
  collision boxes, written to `Saved/CityGen/kit_layout_chicago_loop.json` (33.5 MB, 11 s). The output is
  deterministic: three runs give the same SHA-1.
- **Why the layout reads the city model:** the spawn record holds only each building's box. The kit reads the city
  model's facade records, which carry the setbacks and the opening types, and keys everything by the same ids as the
  spawn record.
- **Unreal** (`Scripts/city/kit_city_ue.py`, `import_city_ue.py --buildings kit`):
  - Imports the modules with Nanite off.
  - Gives each 400 m tile an always-loaded sublevel (`/Game/Maps/SkyCityChicagoGen_Kit/…`, 11 of them). Each holds
    one actor with about 25 HISMs.
  - Uses the street tiles from the GLBs, and doesn't import the baked tower GLBs.
  - The tiles are needed because HISM stores about 140 bytes per instance in the level: one level would be
    about 97 MB, at pr-guard's 100 MB per-file failure limit.
  - `M_KitWall` (`city_materials_ue.kit_walls`) lays the pack or scan tile out in metres along each instance's own
    axes, so a scaled module never stretches and brick runs on across piers and spans.
- **Prototype first.** I compared the 9 towers of the old `core_00` chunk, including the 219 m `b_lot_osm_68`, baked
  and kit, at the same cameras:

  | | Baked | Kit |
  |---|---|---|
  | Triangles | 229k | 174k (−24%) |
  | GPU, street | 16.6 ms | 10.5 ms |
  | GPU, tower close-up | 17.0 ms | 11.2 ms |
  | GPU, block aerial | 13.3 ms | 13.3 ms |
  | Drawn sections | 30 | 35 |
  | UObject resources | 134 MB | 88 MB |
  | Vertex buffers | 31 MB | 41 MB |
  | Level file | 0.02 MB | 2.1 MB |
  | Load time | 0.25 s | 0.25 s |

  The kit won on GPU time, triangles and memory, and could cover every building, so I rolled it out to all 354.
  Every Loop building now uses the kit.
- **Baked mode still works:** `--buildings baked` is still the default and imports the tower GLBs and boxes as
  before.

### 4. Box collision
- **No snagging:** the facade HISMs have no collision. One hidden HISM of `KIT_Wall` boxes, one per setback tier
  (every Loop footprint is a quad), blocks the car at the facade plane.
- **PIE, `b_lot_osm_332`:** the car drives into the south face at full throttle with no boost. It rides the whole
  263 m face (HUD: WALL, "Wall ride") and launches off the top to 319 m (`ue_tower_wallride.jpg`).
- **PIE, `b_lot_osm_68`:** it rides the podium to its 12 m top. The podium ends there and the tower stands 2.8 m back,
  so the car goes over the edge, which is the right result. Before, it stuck at 0 mph about 8 m up the same face.
- **Proof for the PIE checks:** I added temporary log lines to `SkysterCar.cpp`. They showed
  `transition kind=1 … HierarchicalInstancedStaticMesh20` and the support lost at z = 11.7 m, at the podium top. The
  file was reverted and the module rebuilt; `git diff Source` is empty.

## Test results
- `python3 -I Scripts/city/test_city.py`: 46 tests OK
- `python3 -I Scripts/roads/test_profiles.py`: 12 tests OK
- `python3 -I Scripts/city/test_packs.py`: 13 tests OK (new: `test_massing_takes_windowed_sets_at_real_size`)
- `python3 -I Scripts/city/test_generate_city.py`: 15 tests OK. New: four `KitLayoutTest` tests (deterministic,
  runs fill each facade edge to 1 cm and point inward, one collision box per tier on the footprint, dressing follows
  the mesher) and `test_kit_mode_takes_only_street_tiles`.
- Determinism: the default spawn hash is still `1e7ebb86…90bf`, chicago_loop is still `60286e1b…0a65`, and the kit
  layout is the same on every run.
- Blender: `blender_city.py` exit 0 with UV PASS; `blender_facade_kit.py` exit 0.
- Import: 325 s, no save, compile or sampler errors. A fresh load of the level gives map check 0 errors.
- PIE: street drive, wall rides and flight as above.
- LFS in this change: 214.9 MiB across 189 files (pr-guard limit 300), none over 25 MiB.

## Screenshots
All in `artifacts/previews/chicago_loop/`. The pass 1 versions are in `4e33b22`
(`git show 4e33b22:artifacts/previews/chicago_loop/ue_aerial.jpg`).
- `ue_aerial.jpg`: aerial, editor camera. All 354 towers with windows and lit rooms; before, 296 were flat boxes.
- `ue_street_level.jpg`: in game, the Roadster down the start street (Draco street tiles, kit towers).
- `ue_street_editor.jpg`: the street camera used for the GPU numbers.
- `ue_tower_closeup.jpg`: kit towers up close: brick in metres, piers, corner pilasters, curtains and blinds behind
  real glass.
- `ue_tower_wallride.jpg`: in game, wall ride up a kit tower (HUD: WALL, 65 mph).
- `ue_neverstream_test.jpg`: the same aerial with NeverStream off (top) and on (bottom). No difference.
- `sky_city_*.jpg`: Blender previews of the Loop, now with all 346 meshed buildings.

Full-size in-game shots are in `Saved/Screenshots/MacEditor/HighresScreenshot00630.png` to `00635.png` (not
committed).

## What didn't work, or isn't done
- **Aerial GPU +6 ms.** The kit has no LODs yet. A 2-triangle LOD1 for the pane modules (213k panes × 24 triangles
  are most of the 8.7 M) is the obvious next step.
- **Left out of the kit:**
  - storefront awnings and shop interiors, doors, air conditioners and roof units;
  - the facade grime (the baked walls' vertex-colour wear) and wall normal maps, because the kit projects in world
    metres, and cube tangents don't follow that;
  - curtains drawn on both sides of a window are drawn as one leaf.
- **Per-instance cost.** The kit stores about 140 bytes per instance in the level (92 MB of sublevels), and the
  prototype showed about 10 MB more vertex buffer per 15k instances. City-wide the kit still uses less vertex
  memory (+42 MB against +112 MB).
- **Building GLBs are kept but unused.** The 79 MB of Draco tower GLBs stay in `SourceArt` for `--buildings baked`.
  Dropping them would take the change to about 136 MiB.
- **Leftover materials.** `M_MassingFacade`, `MI_Massing_*` and the facade-material instances stay in the content
  folder. Kit mode doesn't use them.
- **Small street tiles.** A few edge tiles are under 10 KB and were not merged into neighbours.
- **Screenshot quality.** Late in the session `HighResShot` from the console stopped writing files, so the wall-ride
  shot is an editor capture (1016×582). The aerial is still an editor camera; scripted flight out of the canyons is
  unreliable.
- **Port 8000.** It was held by a CrashReportClient left from pass 1's MassEntity crash. I wasn't allowed to stop it,
  so the editor ran its MCP server on `-ModelContextProtocolPort=8001`. Port 8000 frees up once that crash reporter is
  closed.
- **Not run:** SkyCityMashup (not opened, by the brief), McGregor and McGregorNight, a packaged build, the Garage
  map switch, and `import_block_ue.py` in the editor.
- **Lighting** is unchanged: plain daylight, a little bright and blue.

## Process notes
- **LFS locks.** The generated `.uasset` and `.umap` files from 4e33b22 were read-only, because they are `lockable`.
  I made only `Content/City/Generated/Chicago/**` and `Content/Maps/SkyCityChicagoGen*` writable locally
  (`chmod u+w`), and did not run `git lfs lock`, which would create locks on GitHub. Per CLAUDE.local.md, the
  contributor lock rule in AGENTS.md is for outside contributors. If someone else works on these assets, lock them
  first.
- The editor's `SecurityToken` line in `Config/DefaultEngine.ini` was reverted and is not committed.

## How to rebuild
```bash
python3 -I Scripts/city/generate_city.py --region chicago_loop
python3 -I Scripts/city/kit_layout.py --region chicago_loop
SKYCITY_REGION=chicago_loop /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python-exit-code 1 -P Scripts/city/blender_city.py
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 \
  -P Scripts/city/blender_facade_kit.py
# in the editor, PIE off (or as a startup script, launched with /Engine/Maps/Entry or the Chicago map):
py Scripts/city/import_city_ue.py --glbs SourceArt/CityGen/chicago --buildings kit \
  --level /Game/Maps/SkyCityChicagoGen --spawn Saved/CityGen/sky_city_spawn_chicago_loop.json
# measure:
UnrealEditor SkyCity.uproject /Engine/Maps/Entry \
  -ExecutePythonScript="Scripts/city/measure_city_ue.py --level /Game/Maps/SkyCityChicagoGen --tag kit"
```
C++ builds on this Mac need `-NoUBA`: the build accelerator writes broken `.o` files through the symlinked
`Intermediate` folder.

An AI (Claude) did this work.
