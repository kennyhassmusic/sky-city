# Clean and regenerate every PCG volume in the open level (Sky City blockout zones).
# Run in the editor: py Scripts/regenerate_pcg.py
# Note: the editor only works through PCG generation while it is active, so keep its window up.
import json, traceback
import unreal

import os


def _skycity_root():
    """Project folder: $SKYCITY_ROOT, else the folder above this script that holds SkyCity.uproject."""
    env = os.environ.get("SKYCITY_ROOT")
    if env:
        return env
    try:
        d = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        d = None
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "SkyCity.uproject")):
            return d
        d = os.path.dirname(d)
    import unreal  # running in the editor without __file__
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")


OUT = os.path.join(_skycity_root(), "Saved", "MCPScripts", "out.json")
out = {"volumes": []}
try:
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if not isinstance(a, unreal.PCGVolume):
            continue
        comp = a.get_component_by_class(unreal.PCGComponent)
        comp.cleanup_local(True)
        comp.generate_local(True)
        out["volumes"].append(a.get_actor_label())
except Exception:
    out["error"] = traceback.format_exc()
open(OUT, "w").write(json.dumps(out, indent=1))
