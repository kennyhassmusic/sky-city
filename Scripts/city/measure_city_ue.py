"""Measure a generated city level: load time, memory, meshes, triangles and draw-call proxies.

Used to compare the baked-GLB import against the facade-kit import
(CHICAGO_REPORT.md). Run it as the editor's startup script, with an empty map
first so the load is cold for this process:

  UnrealEditor SkyCity.uproject /Engine/Maps/Entry \\
    -ExecutePythonScript="Scripts/city/measure_city_ue.py --level /Game/Maps/SkyCityChicagoGen --tag baseline"

Writes Saved/CityGen/measure/<tag>.json. The editor quits when the script ends.
SkyCityMashup is refused. A memreport asked for inside this script is only
written when it ends, so memory is measured in a live editor instead (console
"memreport -full" once with the level and once with /Engine/Maps/Entry), and
read back with plain Python:

  python3 Scripts/city/measure_city_ue.py --memreport <file.memreport>

Numbers:
- load_s / load_full_s: EditorLoadingAndSavingUtils.load_map, then until every mesh's
  render data is readable (synchronous compilation; meshes come from the warm DDC).
- --memreport: process physical memory, RHI vertex/index/texture memory and the
  UObject resource size (MB).
- actors, components, instances, mesh_sections: what the renderer draws. One static
  mesh component costs one draw per material section (per pass); one HISM costs the
  same for all of its instances, so sections_drawn is the draw-call proxy.
- triangles: LOD0 triangles over every component (instances counted).
- disk_mb: bytes on disk of the level and the content folder it uses.
"""
import json
import os
import re
import sys
import time


def _root():
    env = os.environ.get("SKYCITY_ROOT")
    if env:
        return env
    d = os.path.dirname(os.path.abspath(__file__))
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "SkyCity.uproject")):
            return d
        d = os.path.dirname(d)
    raise SystemExit("SkyCity.uproject not found")


ROOT = _root()
OUT = os.path.join(ROOT, "Saved", "CityGen", "measure")


def parse_args(argv):
    import argparse
    parser = argparse.ArgumentParser(prog="measure_city_ue.py")
    parser.add_argument("--level", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--folder", default="/Game/City/Generated/Chicago",
                        help="content folder whose disk size is reported")
    return parser.parse_args(argv)


def physical_mb(text):
    """'Process Physical Memory: 1234.56 MB used' from a memreport, else None."""
    match = re.search(r"Process Physical Memory:\s*([0-9.]+)\s*MB used", text)
    return float(match.group(1)) if match else None


def memreport_numbers(text):
    """Process memory, RHI buffers and UObject resource size (MB) from a memreport."""
    def stat(label):
        match = re.search(r"([0-9.]+)MB\s+-\s+%s - " % re.escape(label), text)
        return float(match.group(1)) if match else None
    out = {"physical": physical_mb(text), "vertex_buffers": stat("Vertex Buffer Memory"),
           "index_buffers": stat("Index Buffer Memory"), "texture_2d": stat("Texture 2D Memory")}
    match = re.search(r"([0-9.]+)MB total\s*\nMemReport: End command \"rhi.DumpMemory\"", text)
    out["rhi_total"] = float(match.group(1)) if match else None
    match = re.search(r"Objects \(Total: [0-9.]+M / Max: [0-9.]+M / Res: ([0-9.]+)M", text)
    out["uobject_resource"] = float(match.group(1)) if match else None
    return out


def disk_mb(paths):
    total = 0
    for path in paths:
        if os.path.isfile(path):
            total += os.path.getsize(path)
        for folder, _dirs, files in os.walk(path):
            total += sum(os.path.getsize(os.path.join(folder, name)) for name in files)
    return round(total / 1048576.0, 2)


def _scene(unreal):
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    stats = {"actors": len(actors), "components": 0, "instances": 0, "sections_drawn": 0, "triangles": 0}
    for actor in actors:
        for comp in actor.get_components_by_class(unreal.StaticMeshComponent):
            mesh = comp.get_editor_property("static_mesh")
            if mesh is None or not comp.is_visible():
                continue
            count = comp.get_instance_count() if isinstance(comp, unreal.InstancedStaticMeshComponent) else 1
            if count == 0:
                continue
            stats["components"] += 1
            stats["instances"] += count
            stats["sections_drawn"] += mesh.get_num_sections(0)
            stats["triangles"] += count * _tris(unreal, mesh)
    return stats


_TRIS = {}


def _tris(unreal, mesh):
    key = mesh.get_path_name()
    if key not in _TRIS:
        _TRIS[key] = int(mesh.get_num_triangles(0))
    return _TRIS[key]


def main(argv=None):
    import unreal
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.level.rsplit("/", 1)[-1] == "SkyCityMashup":
        raise SystemExit("measure_city_ue.py does not open SkyCityMashup")
    os.makedirs(OUT, exist_ok=True)
    # Build meshes and textures on the calling thread, so the load time includes them.
    for cvar in ("Editor.AsyncStaticMeshCompilation 0", "Editor.AsyncTextureCompilation 0",
                 "Editor.AsyncAssetCompilation 0"):
        unreal.SystemLibrary.execute_console_command(None, cvar)
    t0 = time.time()
    unreal.EditorLoadingAndSavingUtils.load_map(args.level)
    load_s = time.time() - t0
    scene = _scene(unreal)  # reads render data: waits for anything still building
    result = {"tag": args.tag, "level": args.level, "load_s": round(load_s, 2),
              "load_full_s": round(time.time() - t0, 2)}
    result.update(scene)
    level_file = os.path.join(ROOT, "Content", args.level.lstrip("/").split("/", 1)[1] + ".umap")
    folder = os.path.join(ROOT, "Content", args.folder.lstrip("/").split("/", 1)[1])
    result["disk_mb"] = {"level": disk_mb([level_file]), "content": disk_mb([folder])}
    with open(os.path.join(OUT, args.tag + ".json"), "w") as handle:
        json.dump(result, handle, indent=1)
    print("MEASURE", json.dumps(result))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--memreport":
        # Plain Python: numbers from a memreport written in a live editor (console: memreport -full).
        with open(sys.argv[2], errors="replace") as handle:
            print(json.dumps(memreport_numbers(handle.read())))
    else:
        main()
