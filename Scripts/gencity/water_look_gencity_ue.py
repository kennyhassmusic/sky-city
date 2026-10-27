"""Retune water B on an imported drive level without a re-import: set MI_L9_Water and MI_L9_Bed (instances of
M_L9_Water / M_L9_Bed; no shader compile; GEN_WATER_REBUILD=1 also rebuilds the parents) to a
building-types water_ue.LOOKS entry (headless, quits when done).
  GEN_BT=<building-types worktree> GEN_SEED=7 GEN_WATER_LOOK=bright "$UE_CMD" "$PWD/SkyCity.uproject" \
    /Engine/Maps/Entry -unattended -nosplash -ExecutePythonScript="$PWD/Scripts/gencity/water_look_gencity_ue.py"
Writes Saved/GenCity/water_look_status.json."""
import json
import os
import sys
import traceback

import unreal

root = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")
out = {}
try:
    bt = os.environ["GEN_BT"]
    sys.path.insert(0, os.path.join(bt, "Scripts", "city"))
    import water_ue
    seed = int(os.environ.get("GEN_SEED", "7"))
    look = os.environ.get("GEN_WATER_LOOK", water_ue.DEFAULT_LOOK)
    water, bed = water_ue.materials(unreal, "/Game/GenCity/Seed%d" % seed,
                                    os.path.join(bt, "Saved", "CityGen", "water", "GenCity_Seed%d" % seed), look,
                                    rebuild=os.environ.get("GEN_WATER_REBUILD", "0") == "1")
    out = {"ok": True, "look": look, "water": water.get_path_name(), "bed": bed.get_path_name()}
except Exception:
    out = {"ok": False, "trace": traceback.format_exc()}
with open(os.path.join(root, "Saved", "GenCity", "water_look_status.json"), "w") as h:
    json.dump(out, h, indent=1)
