"""Import a generated city (building-types generator) into a drive level in this project, from a fresh editor that
quits when done. The building-types importer (Scripts/city/import_city_ue.py in that repo) does the work, with:
  --buildings kit --no-streets   the city's kit layout (HISM), roads and pads included
  --drive                        every imported mesh complex-as-simple, the PlayerStart at the start of the longest
                                 straight major street, the route in <bt>/Saved/CityGen/drive_<region>.json
  --game-mode BP_SkyCityGameMode the level spawns the Skyster (ASkysterCar) as the player pawn
  --project <this project>       the read-only check looks at this project's Content
  --water b                      water B: our own river and lake water, the channel and banks cut into the ground
                                 (GEN_WATER=flat for the older flat surface, GEN_WATER_LOOK=v1|bright)
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
# The drive level's own light (v3, after v2's street-level shots): sunlit ground and sidewalks blew out and shaded
# facades went near-black. Less exposure, a stronger sky fill and local exposure (UE's per-region tone curve:
# scales < 1 compress the highlight and shadow contrast) keep detail at both ends. GEN_LIGHT=0 keeps the importer's.
# The importer's sun (pitch -38, yaw -35) lights south and east faces and leaves north and west fronts in shade
# (lane 2's check); a higher sun (pitch -48) shortens the street shadows and the stronger sky lifts the shaded fronts.
DRIVE_LIGHT = {"sun_intensity": 7.0, "sun_pitch": -48.0, "sun_yaw": -35.0, "sky_intensity": 5.0, "exposure_bias": -0.2,
               "local_highlight_contrast": 0.55, "local_shadow_contrast": 0.7}


def drive_light(unreal):
    """Apply DRIVE_LIGHT to the open level's Sun, SkyLight and Grade (the importer's stage)."""
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    done = []
    for actor in sub.get_all_level_actors():
        label = actor.get_actor_label()
        if label == "Sun":
            actor.modify()
            actor.light_component.set_editor_property("intensity", DRIVE_LIGHT["sun_intensity"])
            actor.set_actor_rotation(unreal.Rotator(0.0, DRIVE_LIGHT["sun_pitch"], DRIVE_LIGHT["sun_yaw"]), False)
            done.append(label)
        elif label == "SkyLight":
            actor.modify()
            actor.light_component.set_editor_property("intensity", DRIVE_LIGHT["sky_intensity"])
            done.append(label)
        elif label == "Grade":
            actor.modify()
            settings = actor.get_editor_property("settings")
            for name, value in (("auto_exposure_bias", DRIVE_LIGHT["exposure_bias"]),
                                ("local_exposure_highlight_contrast_scale", DRIVE_LIGHT["local_highlight_contrast"]),
                                ("local_exposure_shadow_contrast_scale", DRIVE_LIGHT["local_shadow_contrast"])):
                try:
                    settings.set_editor_property("override_" + name, True)
                    settings.set_editor_property(name, value)
                except Exception as exc:  # noqa: BLE001
                    print("GENCITY note: post-process %s not set (%s)" % (name, exc))
            actor.set_editor_property("settings", settings)
            done.append(label)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print("GENCITY drive light", DRIVE_LIGHT, "on", done)
    return done


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
                             "--project", root,
                             # Water B (Kenny's pick, 2026-10-27): our own river/lake water and the channel cut into
                             # the ground (building-types water_ue.py). GEN_WATER=flat keeps the older flat surface;
                             # GEN_WATER_LOOK picks a water_ue.LOOKS entry (default "bright").
                             "--water", os.environ.get("GEN_WATER", "b")]
                            + (["--water-look", os.environ["GEN_WATER_LOOK"]] if os.environ.get("GEN_WATER_LOOK") else []))
        result = {"import": "ok", "region": region, "level": "/Game/Maps/GenCity_%s" % name}
        if os.environ.get("GEN_LIGHT", "1") != "0":
            import unreal
            result["light"] = drive_light(unreal)
    except BaseException:
        result = {"import": "error", "region": region, "trace": traceback.format_exc()}
    with open(status, "w") as handle:
        json.dump(result, handle, indent=1, sort_keys=True)
        handle.write("\n")


main()
