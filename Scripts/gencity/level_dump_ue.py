"""Dump what is actually in the open level (lane P, v10 checklist): every actor label (grouped by prefix), and every
instanced / static mesh component's mesh with its instance count and materials. Headless:
  UnrealEditor-Cmd SkyCity.uproject /Game/Maps/GenCity_Seed7 -unattended -nosplash -ExecutePythonScript=<this>
Writes Saved/GenCity/level_dump_<map>.json."""
import json
import os
import re

import unreal

ROOT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
name = world.get_name()
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
labels, meshes, classes, tags = {}, {}, {}, {}
for a in sub.get_all_level_actors():
    lab = a.get_actor_label()
    pre = re.sub(r"[_\d]+$", "", re.sub(r"_\d+(_\d+)*$", "", lab))
    labels[pre] = labels.get(pre, 0) + 1
    c = a.get_class().get_name()
    classes[c] = classes.get(c, 0) + 1
    for t in a.get_editor_property("tags") or []:
        tags[str(t)] = tags.get(str(t), 0) + 1
    for comp in a.get_components_by_class(unreal.StaticMeshComponent):
        sm = comp.get_editor_property("static_mesh")
        if sm is None:
            continue
        key = sm.get_path_name().split(".")[-1]
        n = comp.get_instance_count() if isinstance(comp, unreal.InstancedStaticMeshComponent) else 1
        rec = meshes.setdefault(key, {"instances": 0, "components": 0, "materials": set(), "actors": set()})
        rec["instances"] += n
        rec["components"] += 1
        rec["actors"].add(pre)
        for m in comp.get_materials():
            if m:
                rec["materials"].add(m.get_name())
out = {"map": name, "labels": labels, "classes": classes, "tags": tags,
       "meshes": {k: {"instances": v["instances"], "components": v["components"], "materials": sorted(v["materials"]),
                      "actors": sorted(v["actors"])[:5]} for k, v in meshes.items()}}
mpc = unreal.EditorAssetLibrary.does_asset_exist("/Game/CityGen/Wind/MPC_Wind")
out["mpc_wind"] = mpc
with open(os.path.join(ROOT, "Saved", "GenCity", "level_dump_%s.json" % name), "w") as h:
    json.dump(out, h, indent=1, sort_keys=True)
