"""Before/after for the kit's shadow-only proxies (kit_layout.SHADOW): GPU time and shots, in one editor session.

Runs in a live editor with the Chicago level open (it ticks across frames, so start it from the
console, or at launch with -ExecCmds, not -ExecutePythonScript, which quits when the script ends):
  py Scripts/city/shadow_ab_ue.py [frames=3] [settle=8] [rounds=2]
For each camera and state (proxies casting off, then on; `rounds` times) it waits `settle` seconds
(streaming and the shadow cache), runs
ProfileGPU `frames` times (the results go to the log, between "CITYGEN_AB begin" and "end" markers)
and takes a high-res shot to Saved/CityGen/shots/shadow_<state>_<camera>.png. Then it leaves the
proxies casting and writes Saved/CityGen/shots/shadow_ab.json. Read the log with
  python3 -I Scripts/city/shadow_ab_ue.py --read
Cameras: the report's measurement cameras (aerial, street) and two walk-up streets.
"""
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else None


def _root():
    env = os.environ.get("SKYCITY_ROOT")
    if env:
        return env
    d = _HERE
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "SkyCity.uproject")):
            return d
        d = os.path.dirname(d)
    import unreal
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")


ROOT = _root()
SHOTS = os.path.join(ROOT, "Saved", "CityGen", "shots")
OUT = os.path.join(SHOTS, "shadow_ab.json")
LOG = os.path.expanduser("~/Library/Logs/Unreal Engine/SkyCityEditor/SkyCity.log")
# name: (x, y, z cm, pitch, yaw); CHICAGO_REPORT.md's GPU cameras, then walk-up streets.
CAMERAS = {
    "aerial": (-175000.0, -80000.0, 55000.0, -24.0, 30.0),
    "street": (-84000.0, -23500.0, 250.0, 2.0, 60.0),
}
WALKUP_POSES = ("b_lot_osm_58_street", "b_lot_osm_22_street")


def cameras():
    out = dict(CAMERAS)
    plan = os.path.join(ROOT, "Saved", "CityGen", "walkup_shots.json")
    if os.path.isfile(plan):
        with open(plan) as handle:
            for name, x, y, z, pitch, yaw in json.load(handle)["poses"]:
                if name in WALKUP_POSES:
                    out[name] = (x, y, z, pitch, yaw)
    return out


def shoot(argv):
    import time
    import traceback
    import unreal
    kv = dict(arg.split("=", 1) for arg in argv if "=" in arg)
    frames = int(kv.get("frames", "3"))
    settle = float(kv.get("settle", "8"))  # seconds after a camera or state change (streaming, shadow cache)
    rounds = int(kv.get("rounds", "2"))    # off/on repeated, so warm-up doesn't favour one side
    os.makedirs(SHOTS, exist_ok=True)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    proxies = []
    for actor in actors:
        proxies.extend(actor.get_components_by_tag(unreal.HierarchicalInstancedStaticMeshComponent, "kit_shadow"))
    steps = [(r, state, name, pose) for r in range(rounds) for name, pose in sorted(cameras().items())
             for state in ("off", "on")]
    world = ues.get_editor_world()
    # Slate ticks run several times per engine frame, so everything here goes by the clock.
    st = {"i": 0, "phase": "move", "t": time.time(), "n": 0, "files": [], "t0": time.time()}

    def tick(_dt):
        try:
            now = time.time()
            if st["i"] >= len(steps):
                unreal.unregister_slate_post_tick_callback(handle)
                for comp in proxies:
                    comp.set_cast_shadow(True)
                with open(OUT, "w") as fh:
                    json.dump({"done": True, "proxies": len(proxies), "files": st["files"],
                               "secs": round(now - st["t0"], 1)}, fh, indent=1)
                return
            rnd, state, name, (x, y, z, pitch, yaw) = steps[st["i"]]
            if st["phase"] == "move":
                for comp in proxies:
                    comp.set_cast_shadow(state == "on")
                ues.set_level_viewport_camera_info(unreal.Vector(x, y, z), unreal.Rotator(roll=0, pitch=pitch, yaw=yaw))
                st.update(phase="settle", t=now)
            elif st["phase"] == "settle" and now - st["t"] >= settle:
                unreal.log("CITYGEN_AB begin state=%s cam=%s round=%d" % (state, name, rnd))
                st.update(phase="profile", t=now, n=0)
            elif st["phase"] == "profile" and now - st["t"] >= 1.0:
                unreal.SystemLibrary.execute_console_command(world, "ProfileGPU")
                st["n"] += 1
                st["t"] = now
                if st["n"] >= frames:
                    st["phase"] = "shot"
            elif st["phase"] == "shot" and now - st["t"] >= 1.0:
                unreal.log("CITYGEN_AB end state=%s cam=%s round=%d" % (state, name, rnd))
                # State first: the screenshot call can tick Slate again before it returns.
                st.update(phase="next", t=now)
                if rnd == 0:
                    path = os.path.join(SHOTS, "shadow_%s_%s.png" % (state, name))
                    st["files"].append(path)
                    unreal.AutomationLibrary.take_high_res_screenshot(1600, 900, path)
            elif st["phase"] == "next" and now - st["t"] >= 2.0:
                st.update(phase="move", i=st["i"] + 1)
        except Exception:  # noqa: BLE001 - report and stop
            unreal.unregister_slate_post_tick_callback(handle)
            with open(OUT, "w") as fh:
                json.dump({"error": traceback.format_exc(), "files": st["files"]}, fh, indent=1)

    with open(OUT, "w") as fh:
        json.dump({"started": True, "proxies": len(proxies), "steps": len(steps)}, fh)
    handle = unreal.register_slate_post_tick_callback(tick)
    __import__("builtins")._shadow_ab_handle = handle


def read(log=LOG):
    """{(state, camera): {"root": [ms], "shadow": [ms]}}: each ProfileGPU dump's <root> and ShadowDepths
    inclusive times, from the dumps between the markers (all rounds)."""
    text = open(log, errors="replace").read()
    out = {}
    pattern = r"CITYGEN_AB begin state=(\w+) cam=(\S+) round=\d+(.*?)CITYGEN_AB end"
    for m in re.finditer(pattern, text, re.S):
        rec = out.setdefault((m.group(1), m.group(2)), {"root": [], "shadow": []})
        for line in m.group(3).splitlines():
            hit = re.search(r"([\d.]+) ms \S\s+(<root>|ShadowDepths)\s", line)
            if hit:
                rec["root" if hit.group(2) == "<root>" else "shadow"].append(float(hit.group(1)))
    return out


def _mean(values):
    return sum(values) / len(values) if values else float("nan")


if __name__ == "__main__":
    if "--read" in sys.argv:
        found = read()
        for cam in sorted({cam for _state, cam in found}):
            off, on = found.get(("off", cam), {}), found.get(("on", cam), {})
            print("%-22s root off %.2f on %.2f (%+.2f) | ShadowDepths off %.2f on %.2f (%+.2f) ms  n=%d/%d" % (
                cam, _mean(off.get("root", [])), _mean(on.get("root", [])),
                _mean(on.get("root", [])) - _mean(off.get("root", [])),
                _mean(off.get("shadow", [])), _mean(on.get("shadow", [])),
                _mean(on.get("shadow", [])) - _mean(off.get("shadow", [])),
                len(off.get("root", [])), len(on.get("root", []))))
    else:
        shoot(sys.argv[1:])
