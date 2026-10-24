# Chicago generated map: report

Branch `cursor/chicago-gen-map` off `main` `a25704a`. Committed locally, not pushed or merged.
The scripts were written in an earlier claude.ai session (Linux VM). This session, on Kenny's Mac, ran
Blender, the UE build, the editor import and the drive, and fixed what the editor showed.

## What changed

**Generator (plain Python)**
- `Scripts/city/generate_city.py --region chicago_loop` keeps only the lots, landmarks and road pieces inside a
  Loop rectangle (Harrison to Lake, Wells-ish to Michigan: 1.08 x 1.33 km, 1.43 km²) inside the Chicago box, in the
  same plan metres. Roads crossing the edge are clipped (Liang-Barsky). Without `--region` nothing changes.
  Output: `Saved/CityGen/sky_city_spawn_chicago_loop.json` and `Scripts/city/examples/sky_city_spawn_chicago_loop.json`
  (354 buildings, 352 roads, 5,997 props).
- `Scripts/city/pack_slots.py`: which texture each engine slot gets (windowless AI pack walls, ground by use, CC0
  fallback), plus `massing_sets()`: windowed pack facades for the massing boxes, at the set's real tile size.

**Blender export**
- `Scripts/city/blender_city.py` region mode (`SKYCITY_REGION=chicago_loop`) writes `SourceArt/CityGen/chicago`:
  12 GLBs, 228.5 MiB (10 core, 1 residential, 2 street), plus `city_manifest.json`. The region budget is now 225 MiB
  (was 240): the PR also carries about 50 MiB of imported Content, and pr-guard stops at 300 MiB.

**Unreal import**
- `Scripts/city/import_city_ue.py --glbs <folder> --level <map> --spawn <record>` imports into a new level, never
  SkyCityMashup. It adds per-triangle collision (complex as simple), a sun, sky, atmosphere and light fog, a ground
  slab and a PlayerStart on the longest street. Buildings past the GLB budget become massing boxes, and road pieces
  outside the meshed streets become strips.
- `Scripts/city/city_materials_ue.py` (new) builds every slot: pack or CC0 textures, real glass (translucent,
  per-pixel lit, Fresnel), so the room shells behind the panes show through, emissive lit rooms, and flat colours for
  the small slots. It also builds `M_MassingFacade`: the pack tile laid out in metres from the box's local position
  and its size (custom primitive data), so floors line up at the base and bays keep their width; the roofs are grey.
  It also builds `M_GroundSlab`, which tiles the paving every tile instead of stretching one tile over 1.4 km.
- `Scripts/city/facade_material_ue.py`: `UVScale` and `RoughFromG` on the facade master.
  `Scripts/city/import_block_ue.py` now uses the same material path (not run this session).
- Level `/Game/Maps/SkyCityChicagoGen` (`Content/Maps/SkyCityChicagoGen.umap`, 3.5 MiB) and its assets in
  `Content/City/Generated/Chicago` (45 MiB).

**Game**
- `Source/SkyCity/SkysterCar.h`: `SkyCityChicagoGen` added to the Garage's `Maps` (the list lives in the header, not
  in `SkysterCar.cpp`). `SkyCourseBuilder.cpp` gives it the name "Chicago Loop (generated)".
- `Config/DefaultGame.ini`: `MapsToCook` lists SkyCityMashup, SkyCityChicagoGen, McGregor and McGregorNight.
- The C++ module was rebuilt and passes.

### Bugs the editor showed, all fixed in this change
| Symptom | Cause | Fix |
|---|---|---|
| Torn facades, bow-tie window panes | The glTF import turns Nanite on; the Mac build is Metal SM5 (no Nanite), so the simplified fallback mesh was drawn | `_no_nanite()` on every imported mesh |
| Grey checker on walls and streets | `M_Facade`, `M_Asphalt`, `M_Paving`, `M_Grass` failed to compile: texture parameters had no default texture, and the roughness samplers were Linear Color for Masks textures | Default textures from the first slot; Masks samplers |
| Massing boxes and road strips pitched instead of turned | `unreal.Rotator(a, b, c)` is roll, pitch, yaw | Keyword arguments in `_actor` |
| Washed-out haze | Default height-fog density over a 1 km city | `FOG_DENSITY = 0.0025` |
| About 20 MB of unused materials | glTF placeholder materials beside each mesh | Deleted after the slots are rebound |
| `M_Hydrant` left on the glTF colour | No material for that slot | Flat red |

## Test results
- `python3 -I Scripts/city/test_city.py`: 46 tests OK
- `python3 -I Scripts/roads/test_profiles.py`: 12 tests OK
- `python3 -I Scripts/city/test_packs.py`: 13 tests OK (1 new: `test_massing_takes_windowed_sets_at_real_size`)
- `python3 -I Scripts/city/test_generate_city.py`: 10 tests OK
- Determinism: the default spawn is byte-identical to the committed example (hash `1e7ebb86…90bf`), and
  `--region chicago_loop` gives `60286e1b…0a65` on every run.
- Blender: exit 0; census and face_uv checks pass; preview exposure check PASS.
- Build: `Build.sh SkyCityEditor Mac Development … -NoUBA` succeeded. Without `-NoUBA`, Unreal's build accelerator
  wrote corrupt `.o` files through the symlinked `Intermediate` folder (`ld: LINKEDIT content … extends beyond end of
  segment`).
- Editor: a fresh load of `SkyCityChicagoGen` gives map check 0 errors, 0 warnings, with no material or load errors
  from the generated content.
- PIE (scripted with the car's `bTestInput` properties):
  - The car drove the start street to 122 mph on the ground (z stays 0).
  - It hit a tower around X = -108,000 and wall-rode up to 58 m; the HUD scored "Wall ride" and "Wall to wall".
  - It flew at 230 mph and landed again.
  - Collision holds on streets, the slab, the meshed towers and the massing boxes.
- LFS in this change: 281.5 MiB (GLBs 228.6, Content 45.4, map 3.5, previews 3.9), under pr-guard's 300 MiB.

## Screenshots
In the repo, `artifacts/previews/chicago_loop/`:
- `ue_aerial.jpg`: aerial of the level (editor camera; see below)
- `ue_street_level.jpg`: in game, the Roadster at 122 mph down a Loop street
- `ue_tower_wallride.jpg`: in game, the Roadster wall-riding a meshed brick tower (HUD: WALL)
- `ue_tower_closeup.jpg`: tower close-up, editor camera: windows, blinds and curtains behind the glass, lit rooms
- `ue_massing_closeup.jpg`: massing towers with the windowed pack facade next to meshed towers
- `sky_city_*.jpg`: the Blender previews of the same Loop (aerial, streets, dusk, tower side, contact sheets)

The full-size in-game shots are in `Saved/Screenshots/MacEditor/HighresScreenshot00622.png` (street) and
`HighresScreenshot00629.png` (wall ride). They are not committed.

## What didn't work, or isn't done
- **Most of the Loop is massing.** Only 58 of the 344 meshed buildings fit the 225 MiB GLB budget; the other 296 are
  boxes with a windowed pack facade. They read as towers from the street, but they have no relief, entrances or
  rooms. The GLBs cost about 170 bytes per triangle (no compression, two vertex-colour sets, every window and sill
  as real geometry). Instancing repeated facade parts, or building the towers in the editor from the spawn record,
  would let far more of the city ship as real meshes.
- **The two street GLBs are 26.1 and 28.6 MiB.** That is over the exporter's 22 MB file cap (each holds a single
  large object) and over pr-guard's 25 MiB warning line; it is not a failure.
- **Wall rides snag on facade ledges.** The car stopped at 0 mph about 8 m up a tower; the complex collision
  includes sills and storefront relief. Simple collision boxes for the facades would fix it.
- **The ground ends at the slab** (40 m past the region). Past it the car sits at z = 0, with nothing drawn below.
- **No in-game aerial shot.** Scripted flight out of the canyons kept wall-riding or turning away from the city, and
  moving the car with `set_actor_transform` does not stick (the car integrates its own position). The aerial is
  therefore the editor camera on the same level.
- **One editor crash at PIE start**, in Epic's MassEntity (`FMassArchetypeSharedFragmentValues`, a mutex
  assertion), after six clean PIE starts on this map. It looks like an engine issue; the level was saved before it.
- **Not run:** SkyCityMashup was not opened, by the brief, so its no-new-errors check was skipped; McGregor and
  McGregorNight were not reloaded; no packaged build; `import_block_ue.py` was not run in the editor; the Garage
  map switch was not tried in PIE.
- **Lighting is plain daylight** (sun, sky light, fog) and somewhat bright and blue. There is no post-process volume.
- **Walls still use the CC0 scans:** no windowless AI pack fits the Loop's district types (tech, eclectic_mix,
  historic_old). The ground uses the tech packs.
- `Config/DefaultGame.ini` and `Source/SkyCity/*` are sensitive paths, so a PR needs `maintainer-approved`.

## How to rebuild
```bash
python3 -I Scripts/city/generate_city.py --region chicago_loop
SKYCITY_REGION=chicago_loop /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python-exit-code 1 -P Scripts/city/blender_city.py
"/Users/Shared/Epic Games/UE_5.8/Engine/Build/BatchFiles/Mac/Build.sh" SkyCityEditor Mac Development \
  -project="$PWD/SkyCity.uproject" -WaitMutex -NoUBA
# in the editor (PIE off), or at launch with -ExecutePythonScript and the map as the first argument:
py Scripts/city/import_city_ue.py --glbs SourceArt/CityGen/chicago --level /Game/Maps/SkyCityChicagoGen \
  --spawn Saved/CityGen/sky_city_spawn_chicago_loop.json
```
Launch the editor with `/Game/Maps/SkyCityChicagoGen` as the first argument so it does not open its startup map
(SkyCityMashup).

An AI (Claude) did this work.
