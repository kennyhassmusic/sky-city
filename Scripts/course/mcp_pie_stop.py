"""Editor Python: end PIE (which closes the course MCP server). Run from the editor's console box:
py /abs/path/Scripts/course/mcp_pie_stop.py        Writes Saved/MCPScripts/out_mcp_pie_stop.json when the PIE world is gone."""
import json, os, unreal

ROOT = os.environ.get("SKYCITY_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = ROOT + "/Saved/MCPScripts/out_mcp_pie_stop.json"
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
st = {"n": 0, "h": None}
had = bool(ues.get_game_world())
if had:
    les.editor_request_end_play()


def tick(dt):
    st["n"] += 1
    if ues.get_game_world() and st["n"] < 900:
        return
    with open(OUT, "w") as f:
        json.dump({"had_pie": had, "pie_gone": not ues.get_game_world(), "ticks": st["n"]}, f)
    unreal.unregister_slate_post_tick_callback(st["h"])


st["h"] = unreal.register_slate_post_tick_callback(tick)
