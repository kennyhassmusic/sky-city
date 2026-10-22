"""Editor Python: start PIE on the Course Builder map and switch the LLM link (the course MCP server) on, for testing.
Run it from the editor's console box:  py /abs/path/Scripts/course/mcp_pie_start.py [map=/Game/Maps/McGregor] [build=1] [via=mode]
  build=1   reopen the map as the Garage does (McGregor?mode=build) so the car spawns the Course Builder director (default)
  build=0   stay in the plain PIE world; with via=console the SkyCourse.Mcp console command spawns a director itself
  via=mode  switch the link on through ASkyCourseMode::TestSetMcp (the real switch, default); via=console: SkyCourse.Mcp 1
PIE keeps running afterwards (talk to the server from outside, e.g. Scripts/course/mcp_smoke_test.py); stop it with
mcp_pie_stop.py. Writes Saved/MCPScripts/out_mcp_pie.json."""
import json, os, sys, unreal

ROOT = os.environ.get("SKYCITY_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = ROOT + "/Saved/MCPScripts/out_mcp_pie.json"
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
MAP = KV.get("map", "/Game/Maps/McGregor")
BUILD = KV.get("build", "1") == "1"
VIA = KV.get("via", "mode")
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
MODE = unreal.load_class(None, "/Script/SkyCity.SkyCourseMode")
out = {"map": MAP, "build": BUILD, "via": VIA}
st = {"n": 0, "phase": 0, "n1": 0, "h": None}

if ues.get_game_world():
    les.editor_request_end_play()
les.load_level(MAP)
les.editor_request_begin_play()


def finish():
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    if st["h"] is not None:
        unreal.unregister_slate_post_tick_callback(st["h"])


def tick(dt):
    st["n"] += 1
    w = ues.get_game_world()
    if not w:
        if st["n"] > 1800:
            out["error"] = "PIE never started"
            finish()
        return
    if st["phase"] == 0:
        if st["n"] < 90:
            return
        if BUILD:
            unreal.SystemLibrary.execute_console_command(w, "open " + MAP + "?mode=build")
            st["phase"], st["n1"] = 1, st["n"]
            return
        st["phase"] = 2
    if st["phase"] == 1:
        if st["n"] - st["n1"] < 45:
            return
        if not unreal.GameplayStatics.get_all_actors_of_class(w, MODE):
            if st["n"] - st["n1"] > 1500:
                out["error"] = "no Course Builder director appeared after reopening with ?mode=build"
                finish()
            return
        st["phase"] = 2
    if st["phase"] == 2:
        modes = unreal.GameplayStatics.get_all_actors_of_class(w, MODE)
        if VIA == "console" or not modes:
            unreal.SystemLibrary.execute_console_command(w, "SkyCourse.Mcp 1")
            out["switched"] = "console"
        else:
            out["switched"] = bool(modes[0].call_method("TestSetMcp", (True,)))
        st["phase"], st["n1"] = 3, st["n"]
        return
    if st["phase"] == 3 and st["n"] - st["n1"] > 20:
        modes = unreal.GameplayStatics.get_all_actors_of_class(w, MODE)
        out["directors"] = len(modes)
        if modes:
            try:
                out["state"] = json.loads(modes[0].call_method("TestStateJson", ()))
            except Exception as e:
                out["state_error"] = repr(e)
        finish()


st["h"] = unreal.register_slate_post_tick_callback(tick)
