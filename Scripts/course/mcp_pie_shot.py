"""Editor Python: aim the Course Builder camera and take a HighResShot (for showing a course an LLM built). PIE must be running
with the Course Builder (see mcp_pie_start.py). Run from the editor's console box:
py /abs/path/Scripts/course/mcp_pie_shot.py [yaw=0] [pitch=55] [dist=300] [name=mcp] [res=1920x1080] [wait=90]
Writes Saved/MCPScripts/out_mcp_shot.json; the picture lands in Saved/Screenshots/ (HighResShot)."""
import json, os, sys, unreal

ROOT = os.environ.get("SKYCITY_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = ROOT + "/Saved/MCPScripts/out_mcp_shot.json"
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
YAW, PITCH, DIST = float(KV.get("yaw", 0)), float(KV.get("pitch", 55)), float(KV.get("dist", 300))
RES, WAIT = KV.get("res", "1920x1080"), int(KV.get("wait", 90))
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
PAWN = unreal.load_class(None, "/Script/SkyCity.SkyCourseBuilderPawn")
out = {"yaw": YAW, "pitch": PITCH, "dist": DIST}
st = {"n": 0, "phase": 0, "h": None}


def finish():
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    unreal.unregister_slate_post_tick_callback(st["h"])


def tick(dt):
    st["n"] += 1
    w = ues.get_game_world()
    if not w:
        out["error"] = "no PIE world"
        finish()
        return
    if st["phase"] == 0:
        pawns = unreal.GameplayStatics.get_all_actors_of_class(w, PAWN)
        if not pawns:
            out["error"] = "no builder pawn"
            finish()
            return
        pawns[0].call_method("TestCamera", (YAW, PITCH, DIST, True))
        out["builder"] = pawns[0].get_name()
        st["phase"], st["n1"] = 1, st["n"]
    elif st["phase"] == 1 and st["n"] - st["n1"] > WAIT:
        unreal.SystemLibrary.execute_console_command(w, "HighResShot " + RES)
        out["shot"] = "requested"
        st["phase"], st["n1"] = 2, st["n"]
    elif st["phase"] == 2 and st["n"] - st["n1"] > 90:
        finish()


st["h"] = unreal.register_slate_post_tick_callback(tick)
