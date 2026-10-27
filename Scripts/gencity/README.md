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

Every editor run takes the shared Unreal lock (`~/UnrealProjects/_bt_mgmt/UNREAL.lock`). Generated content is not
committed (`.gitignore`). No City Sample content goes into the level: the generator's content lives under
`/Game/GenCity`, `/Game/CityGen` and `/Game/LandCover`, and this branch switches the CitySamplePCG plugin off.
The Skyster (ASkysterCar, `/Game/Vehicles/Roadster`) is Kenny's design (LICENSE-ASSETS.md section 4) and is used as is.
