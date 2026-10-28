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

Shoreline (lane F6, building-types `fx/shoreline`): the pipeline's kit stage writes `shoreline_<region>.json` and the
shore textures (`Saved/CityGen/shoreline/textures`); the import then cuts the ground slab back to the city edge and
draws the beach terrain (`M_Shore_Sand`), the sea (water B's `MI_L9_Water`, foam from UV1), the wrack line, the
car parks at the edge stubs and the dune grass / scrub / pebble / shell HISMs under `/Game/GenCity/<Name>/Shore`.
`GEN_SHORE=0` keeps the old flat slab. Missing textures: `python3 -I Scripts/city/shoreline_textures.py
Saved/CityGen/shoreline/textures` in the building-types checkout.

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
