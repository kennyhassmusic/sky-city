"""Wind for a generated-city drive level (lane 8), headless, after the import: one city wind field drives the flags,
awnings, trees, shrubs and crops. The building-types hook (Scripts/city/wind/wind_ue.py on fx/wind) does the work:
  - Saved/CityGen/wind_<region>.json in the building-types worktree (wind_field.py; written here if missing)
  - /Game/CityGen/Wind: MPC_Wind, T_WindExposure, SM_FlagCloth, M_FlagWave, M_WindAwning + MIs
  - the level: the kit's stiff flag boxes hidden, Wind_Flags (HISM of the cloth, NoCollision), Wind_Source
    (WindDirectionalSource), awnings on M_WindAwning, /Game/LandCover's M_LC_Foliage and M_LC_Bark swaying.
Run after import_gencity_ue.py (same environment, same editor kind):
  GEN_BT=<building-types worktree> GEN_SEED=7 "$UE_CMD" "$PWD/SkyCity.uproject" /Game/Maps/GenCity_Seed7 \
    -unattended -nosplash -ExecutePythonScript="$PWD/Scripts/gencity/wind_gencity_ue.py"
Writes Saved/GenCity/wind_status_<region>.json.
"""
import json
import os
import sys
import traceback

import unreal


def main():
    root = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")
    bt = os.environ["GEN_BT"]
    seed = int(os.environ.get("GEN_SEED", "7"))
    region = "seed%d_city" % seed
    out = os.path.join(root, "Saved", "GenCity")
    os.makedirs(out, exist_ok=True)
    status = os.path.join(out, "wind_status_%s.json" % region)
    try:
        for p in (os.path.join(bt, "Scripts", "city", "wind"), os.path.join(bt, "Scripts", "city")):
            if p not in sys.path:
                sys.path.insert(0, p)
        import wind_ue
        stats = wind_ue.hook(unreal, bt, region, os.path.join(out, "wind_scratch"),
                             level="/Game/Maps/GenCity_Seed%d" % seed)
        result = {"wind": "ok", "region": region, "stats": stats}
    except BaseException:
        result = {"wind": "error", "region": region, "trace": traceback.format_exc()}
    with open(status, "w") as handle:
        json.dump(result, handle, indent=1, sort_keys=True, default=str)
        handle.write("\n")


main()
