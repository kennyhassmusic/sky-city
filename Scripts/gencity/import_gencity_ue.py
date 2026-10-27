"""Import a generated city (building-types generator) into a drive level in this project, from a fresh editor that
quits when done. The building-types importer (Scripts/city/import_city_ue.py in that repo) does the work, with:
  --buildings kit --no-streets   the city's kit layout (HISM), roads and pads included
  --drive                        every imported mesh complex-as-simple, the PlayerStart at the start of the longest
                                 straight major street, the route in <bt>/Saved/CityGen/drive_<region>.json
  --game-mode BP_SkyCityGameMode the level spawns the Skyster (ASkysterCar) as the player pawn
  --project <this project>       the read-only check looks at this project's Content
Content lands in /Game/GenCity/<Name> (never /Game/City: that is City Sample and Sky City's own city), the level in
/Game/Maps/GenCity_<Name>. Generated content is not committed (.gitignore: Content/GenCity, Content/Maps/GenCity_*).

Run (paths absolute; the editor's TMPDIR must have no spaces, for the Metal shader compiler):
  GEN_BT="/Volumes/Sound Libraries/SkyCity Work/BuildingTypes-drive" GEN_SEED=7 \
  "$UE_CMD" "$PWD/SkyCity.uproject" /Engine/Maps/Entry -unattended -nosplash \
    -ExecutePythonScript="$PWD/Scripts/gencity/import_gencity_ue.py"
Writes Saved/GenCity/import_status_<region>.json ({"import": "ok"} or the traceback). Scripts/gencity/run_gencity.sh
does the whole round (lock, import, plan, drive test, shots).
"""
import json
import os
import sys
import traceback

GAME_MODE = "/Game/SkyCity/Blueprints/BP_SkyCityGameMode.BP_SkyCityGameMode_C"


def _root():
    try:
        d = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        d = None
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "SkyCity.uproject")):
            return d
        d = os.path.dirname(d)
    import unreal
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")


def main():
    root = _root()
    bt = os.environ["GEN_BT"]
    seed = int(os.environ.get("GEN_SEED", "7"))
    region = "seed%d_city" % seed
    name = "Seed%d" % seed
    os.makedirs(os.path.join(root, "Saved", "GenCity"), exist_ok=True)
    status = os.path.join(root, "Saved", "GenCity", "import_status_%s.json" % region)
    try:
        city = os.path.join(bt, "Scripts", "city")
        if city not in sys.path:
            sys.path.insert(0, city)
        os.environ.pop("SKYCITY_ROOT", None)       # the importer finds building-types from its own path
        import import_city_ue
        import_city_ue.main(["--buildings", "kit", "--no-streets", "--drive",
                             "--spawn", os.path.join(bt, "Saved", "CityGen", "spawn_%s.json" % region),
                             "--level", "/Game/Maps/GenCity_%s" % name,
                             "--folder", "/Game/GenCity/%s" % name,
                             "--game-mode", GAME_MODE,
                             "--project", root])
        result = {"import": "ok", "region": region, "level": "/Game/Maps/GenCity_%s" % name}
    except BaseException:
        result = {"import": "error", "region": region, "trace": traceback.format_exc()}
    with open(status, "w") as handle:
        json.dump(result, handle, indent=1, sort_keys=True)
        handle.write("\n")


main()
