"""Watch Sky City's street traffic in PIE and log every car body's position every few seconds, to find cars that get
stuck (stand still far longer than a red light lasts) or vanish and reappear (teleported by ASkysterTraffic when a link
leads nowhere).

Why: the 20 Oct street audit regenerated traffic.json (Content/SkyCity/Data); before, only 311 of 1228 nodes were in one
strongly connected piece, so cars ran into one-way traps. This checks the new network with the real C++ traffic.
Run in the editor with PIE already running (e.g. after Saved/Playtest/pt.py park):
  py Scripts/roads/traffic_probe_ue.py [secs=90] [every=5]
Writes Saved/Roads/traffic_probe.json: samples [[t, [[x, y, z] per body]]]. Read-only.
"""
import json, sys, time, traceback, unreal

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


ROOT = _skycity_root()
OUT = ROOT + "/Saved/Roads/traffic_probe.json"
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
SECS, EVERY = float(KV.get("secs", 90)), float(KV.get("every", 5))
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
st = {"t0": None, "next": 0.0, "samples": []}


def bodies(gw):
    tr = unreal.GameplayStatics.get_all_actors_of_class(gw, unreal.SkysterTraffic) if hasattr(unreal, "SkysterTraffic") else []
    if not tr:
        return []
    return [c for c in tr[0].get_components_by_class(unreal.StaticMeshComponent)
            if c.static_mesh and "Body" in c.static_mesh.get_name()]


def tick(dt):
    try:
        gw = ues.get_game_world()
        if not gw:
            json.dump({"error": "PIE is not running"}, open(OUT, "w"))
            unreal.unregister_slate_post_tick_callback(_h)
            return
        T = unreal.GameplayStatics.get_time_seconds(gw)
        if st["t0"] is None:
            st["t0"] = T
        t = T - st["t0"]
        if t >= st["next"]:
            st["next"] = t + EVERY
            bs = bodies(gw)
            st["samples"].append([round(t, 1), [[round(v) for v in b.get_world_location().to_tuple()] + [int(b.is_visible())] for b in bs]])
            json.dump({"secs": SECS, "every": EVERY, "samples": st["samples"], "done": t >= SECS}, open(OUT, "w"))
        if t >= SECS:
            unreal.unregister_slate_post_tick_callback(_h)
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        json.dump({"error": traceback.format_exc(), "samples": st["samples"]}, open(OUT, "w"))


_h = unreal.register_slate_post_tick_callback(tick)
