# Generated-city drive levels (`gen/drive-preview`)

Drive the Skyster through a city made by the building-types generator (private repo
`kennyhassmusic/building-types`, branch `integration/drive-preview`). Steps for Kenny: `_bt_mgmt/HOW_TO_DRIVE.md`.

One round, from this project's folder (the building-types worktree has run `pipeline.py --seed 7` first):

```bash
GEN_LINK=<space-free symlink to this folder> GEN_PACK=<building-types assets/starter-pack>/Content/LandCover \
  Scripts/gencity/run_gencity.sh <building-types worktree> 7 v1 all
```

| Step | Script | Writes |
|---|---|---|
| import (headless) | `import_gencity_ue.py` → building-types `Scripts/city/import_city_ue.py --buildings kit --no-streets --drive --game-mode BP_SkyCityGameMode --project <here>` | `/Game/Maps/GenCity_Seed7` (+ `_Kit` sublevels), `/Game/GenCity/Seed7`, `/Game/CityGen/Basics` |
| plan | `plan_gencity.py` | `Saved/GenCity/plan_seed7_city.json`: the drive route (the longest straight major street) and a car pose per zone |
| land cover (headless) | `landcover_gencity_ue.py` | hero trees/shrubs/logs (HISM per slot) and field slabs from the land-cover stage, with the starter pack's `/Game/LandCover` (copied in) |
| drive + shots (PIE) | `drive_gencity_ue.py`, `read_gencity.py` | `Saved/GenCity/drive_<tag>.json`: 20 s full throttle along the route (stays above ground, inside the city), frame time, chase-camera shots per zone + aerial, clean load from the log |

Water B (Kenny's pick, 2026-10-27) comes in with the import: building-types `water_ue.py` cuts the ground slab along
the river (and around lakes), builds the riverbed and banks and the water surfaces with our own `M_L9_Water` /
`M_L9_Bed` (looks in `MI_L9_Water` / `MI_L9_Bed`; `GEN_WATER=flat` for the old flat surface, `GEN_WATER_LOOK=v1|bright`).
`run_water_gencity.sh <bt> <seed> <tag> look <v1|bright>` retunes the instances without a re-import;
`... shots` takes the water poses (Saved/Water/plan.json). The plan adds a `river_bridge` shot.

Every editor run takes the shared Unreal lock (`~/UnrealProjects/_bt_mgmt/UNREAL.lock`). Generated content is not
committed (`.gitignore`). No City Sample content goes into the level: the generator's content lives under
`/Game/GenCity`, `/Game/CityGen` and `/Game/LandCover`, and this branch switches the CitySamplePCG plugin off.
The Skyster (ASkysterCar, `/Game/Vehicles/Roadster`) is Kenny's design (LICENSE-ASSETS.md section 4) and is used as is.

## The game's user asset pack (`gen/game-pack`)

`GEN_PACK=game` puts the game's own asset pack on for the import: `UserPacks/game/userpack.json` (building-types
manifest `bt.userpack/1`, docs/USER_ASSET_PACKS.md there) maps generator slots to converted NVIDIA SimReady and
Scenario 3D Collection meshes (parked SUVs and pickups, forklifts, pallets, drums, people, bikes). It needs a
building-types worktree with `user_pack.py` (`fx/user-pack`). The GLBs are rebuilt from the external drive by
`Scripts/userpack/build_game_pack.sh` (recipes in `UserPacks/game/recipes.json`, choices and rejections in
`curation.json`, credits in `CREDITS.md`) and import into `Content/UserPack` (gitignored). Third-party and AI art
stays in this game project only, never in building-types.

## Visual check after every import (`gen/visual-check`, Lane V)

Fixed cameras, golden images and level rules, so a bad import fails before Kenny looks. Kenny reviews only the
`report.html` of a run that **passed** (golden | new | difference per camera, rule results).

| File | What |
|---|---|
| `visual_cams.json` (made by `visual_cams_make.py`) | 26 seed-7 + 5 seed-17 cameras (curved bend, downtown corner, skewed junction, empty lot, driveway, STOP approach, bridge deck/side, beach eye/dunes/car park/air, county ditch, farm belt, garage ramp, 4 aerials...), render settings (1280x720, FOV 80, wind frozen, fixed post-process), per-camera tolerances, level rules |
| `visual_capture_ue.py` | in the editor (under UNREAL.lock): level dump with vegetation positions, then one HighResShot per camera into the run folder; refuses when `_bt_mgmt/DISK_LOW` exists or the disk has < 15 GB |
| `visual_check.py` | offline: `check` (pictures vs goldens + rules, report, exit code), `approve` (Kenny's OK -> goldens, who/when recorded), `rules` (any level dump) |
| `run_visual_check.sh` | capture + check in one go |
| `test_visual_check.py` | synthetic cases + today's two misses (plants on roads; sand unchanged) |

After each import of seed N (the build lane holds the lock already):

```bash
VISUAL_LOCK=held GEN_BT=<bt worktree> GEN_PACK=game \
  Scripts/gencity/run_visual_check.sh 7 v11 'beach_*' 'tag:shore'     # what this import meant to change
#   ... or: Scripts/gencity/run_visual_check.sh 7 v11 none            # nothing visual meant to change
# exit 0 PASS -> send Kenny report.html; 1 FAIL -> fix first; 3 NEEDS_APPROVAL -> first run, no goldens yet
python3 -I Scripts/gencity/visual_check.py approve --run <run dir> --by Kenny   # only after Kenny's OK
```

Runs go to `AssetBuilds/visual_runs/<tag>_seed<N>_<time>/`, goldens to `AssetBuilds/visual_goldens/seed<N>/`
(older goldens kept under `history/`). Never on the internal disk.
