"""Sky City buildings with Epic's City Sample PCG (the "video method").

Every footprint from Saved/Mashup/buildings_v3.json becomes a closed linear spline. Footprints are grouped by district
and height band into actors; each actor carries a PCG component running /Game/SkyCity/PCG/PCG_SkyCity_Buildings
(Get Spline Data -> Assign_CitySampleBuildings -> rooftops) with that group's heights and City Sample styles.

Stages (each runs on the next editor tick; poll Saved/MCPScripts/out.json):
    py .../citysample_buildings.py test        # a few footprints by the Congress Ave bridge, one actor
    py .../citysample_buildings.py footprints  # every footprint, grouped into district actors (replaces old ones)
    py .../citysample_buildings.py generate [label-substring]   # generate the actors one after another
    py .../citysample_buildings.py status      # generation progress
    py .../citysample_buildings.py boxes on|off   # show or hide the placeholder box buildings
"""
import json, math, sys, time, traceback
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


ROOT = _skycity_root()
OUT = ROOT + "/Saved/MCPScripts/out.json"
GRAPH = "/Game/SkyCity/PCG/PCG_SkyCity_Buildings"
TAG = "SC_CitySampleFootprints"
FOLDER = "City/CitySampleBuildings"
CHUNK = 60           # footprints per actor, so each generation is a manageable bite
CELL = 600.0         # metres; footprints are chunked by grid cell so each actor covers one neighbourhood

# district, height band (m), City Sample styles (see Assign_CitySampleBuildings' style list)
BUCKETS = [
    ("ChicagoLoop_Low", "chicago_core", 0, 110, "CHA,CHC,CHD,CHG,CHI"),
    ("ChicagoLoop_Mid", "chicago_core", 110, 180, "CHB,CHE,CHJ,CHC"),
    ("ChicagoLoop_High", "chicago_core", 180, 9999, "CHB,CHJ,CHE"),
    ("Chicago_Neighbourhoods", "chicago", 0, 9999, "CHA,CHC,CHF,CHG,CHH,CHI,NYH,NYG"),
    ("AustinDT_Low", "austin_dt", 0, 90, "SFA,SFB,SFC,SFJ,CHE"),
    ("AustinDT_Mid", "austin_dt", 90, 160, "SFC,SFD,SFE,CHJ"),
    ("AustinDT_High", "austin_dt", 160, 9999, "SFD,SFE,CHJ"),
    ("Austin_LowRise", "austin_low", 0, 9999, "CHH,CHF,NYAA,NYAB,NYAC,NYAD,NYAE,NYAF"),
]
out = {}


def eas():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def ue(p):
    return p[1] * 100.0, p[0] * 100.0


def corners(b):
    """Footprint corners in Unreal space, same frame as build_city's box buildings (yaw = 90 - plan yaw)."""
    X, Y = ue((b["x"], b["y"]))
    a = math.radians(90.0 - b["yaw"])
    ca, sa = math.cos(a), math.sin(a)
    hw, hd = b["w"] * 50.0, b["d"] * 50.0
    pts = []
    for u, v in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)):
        pts.append(unreal.Vector(X + u * ca - v * sa, Y + u * sa + v * ca, 0.0))
    return pts


def footprint_actors():
    return [a for a in eas().get_all_level_actors() if TAG in [str(t) for t in a.tags]]


def add_component(actor, cls, parent=None):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    BFL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=parent or handles[0], new_class=cls, blueprint_context=None)
    h, fail = sds.add_new_subobject(params)
    return h, BFL.get_object(BFL.get_data(h))


def make_actor(label, group, members, hmin, hmax, styles, seed):
    """A PCG Volume sized to the footprints, holding one closed spline per footprint (Get Spline Data reads Self)."""
    pts = [p for b in members for p in corners(b)]
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    X, Y = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    act = eas().spawn_actor_from_class(unreal.PCGVolume, unreal.Vector(X, Y, hmax / 2), unreal.Rotator(0, 0, 0))
    # the default brush is a 200 cm cube: scale it to enclose the footprints and the tallest building
    act.set_actor_scale3d(unreal.Vector((max(xs) - min(xs)) / 200 + 1, (max(ys) - min(ys)) / 200 + 1, hmax / 200 + 2))
    act.set_actor_label(label)
    act.tags = [TAG, "City_Generated", group]
    act.set_folder_path(FOLDER)
    for b in members:
        h, sp = add_component(act, unreal.SplineComponent)
        sp.clear_spline_points(False)
        for p in corners(b):
            sp.add_spline_point(p, unreal.SplineCoordinateSpace.WORLD, False)
        for i in range(4):
            sp.set_spline_point_type(i, unreal.SplinePointType.LINEAR, False)
        sp.set_closed_loop(True, True)
        sp.set_editor_property("component_tags", [b["district"]])
    pcg = act.get_component_by_class(unreal.PCGComponent)
    pcg.set_graph(unreal.EditorAssetLibrary.load_asset(GRAPH))
    pcg.set_editor_property("generation_trigger", unreal.PCGComponentGenerationTrigger.GENERATE_ON_DEMAND)
    pcg.set_editor_property("seed", seed)
    gi = pcg.get_editor_property("graph_instance")
    H = unreal.PCGGraphParametersHelpers
    H.set_double_parameter(gi, "minHeight", float(hmin))
    H.set_double_parameter(gi, "maxHeight", float(hmax))
    H.set_string_parameter(gi, "buildingsStyles", styles)
    H.set_int32_parameter(gi, "seed", seed)
    return act


def clear_footprints():
    acts = footprint_actors()
    for a in acts:
        try:
            pc = a.get_component_by_class(unreal.PCGComponent)
            if pc:
                pc.cleanup_local(True)
        except Exception:
            pass
    # also the hand-made test/probe actors from the first trial
    acts += [a for a in eas().get_all_level_actors() if a.get_actor_label().startswith(("CS_ProbeVolume", "CS_Test"))]
    eas().destroy_actors(acts)
    return len(acts)


def stage_test():
    B = json.load(open(ROOT + "/Saved/Mashup/buildings_v3.json"))["buildings"]
    # the player start is on the Congress Ave bridge; take the closest downtown footprints
    start = (-1421.3, 368.1)
    near = sorted((b for b in B if b["district"] in ("austin_dt", "chicago_core", "chicago")),
                  key=lambda b: math.dist((b["x"], b["y"]), start))[:8]
    out["removed"] = clear_footprints()
    hs = [b["h"] for b in near]
    make_actor("CS_Test", "test", near, 2625, 5250, "CHA", 7)
    out["test"] = {"n": len(near), "heights": hs, "first": near[0]}


def stage_footprints():
    B = json.load(open(ROOT + "/Saved/Mashup/buildings_v3.json"))["buildings"]
    out["removed"] = clear_footprints()
    made, seed = [], 100
    for name, dist, h0, h1, styles in BUCKETS:
        members = [b for b in B if b["district"] == dist and h0 <= b["h"] < h1]
        if not members:
            continue
        cells = {}
        for b in members:
            cells.setdefault((int(b["x"] // CELL), int(b["y"] // CELL)), []).append(b)
        for (i, j), cell in sorted(cells.items()):
            for k in range(0, len(cell), CHUNK):
                part = cell[k:k + CHUNK]
                hmin = max(800.0, min(b["h"] for b in part) * 100.0)
                hmax = max(hmin + 300.0, max(b["h"] for b in part) * 100.0)
                seed += 1
                label = f"CS_{name}_{i}_{j}_{k // CHUNK}"
                act = make_actor(label, name, part, hmin, hmax, styles, seed)
                made.append([label, len(part), round(hmin), round(hmax), act.get_path_name()])
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    out["actors"] = len(made)
    out["footprints"] = sum(m[1] for m in made)
    out["list"] = made
    json.dump(made, open(ROOT + "/Saved/Mashup/citysample_volumes.json", "w"), indent=0)


# ---- sequential generation queue ----
_queue, _cur, _t0, _done = [], None, 0.0, []


def _gen_tick(dt):
    global _cur, _t0
    try:
        if _cur is not None:
            pc = _cur.get_component_by_class(unreal.PCGComponent)
            # Python has no is_generating(); the component's "generated" flag flips once the graph finishes
            if not pc.get_editor_property("generated") and time.time() - _t0 < 1800:
                return
            _done.append([_cur.get_actor_label(), round(time.time() - _t0, 1)])
            _cur = None
        if not _queue:
            unreal.unregister_slate_post_tick_callback(_gen_handle)
            unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
            _write({"stage": "generate", "ok": True, "finished": True, "done": _done})
            return
        _cur = _queue.pop(0)
        _t0 = time.time()
        pc = _cur.get_component_by_class(unreal.PCGComponent)
        pc.cleanup_local(True)
        pc.generate_local(True)
        _write({"stage": "generate", "running": True, "current": _cur.get_actor_label(), "remaining": len(_queue),
                "done": _done})
    except Exception:
        unreal.unregister_slate_post_tick_callback(_gen_handle)
        _write({"stage": "generate", "error": traceback.format_exc(), "done": _done})


def _write(d):
    open(OUT, "w").write(json.dumps(d, indent=1))


_gen_handle = None


def stage_generate(filt=""):
    global _gen_handle
    # keep generating while the editor is in the background
    try:
        perf = unreal.get_default_object(unreal.EditorPerformanceSettings)
        perf.set_editor_property("throttle_cpu_when_not_foreground", False)
    except Exception as e:
        out["throttle_warning"] = str(e)
    acts = sorted(footprint_actors(), key=lambda a: a.get_actor_label())
    _queue[:] = [a for a in acts if filt in a.get_actor_label()]
    out["queued"] = len(_queue)
    _gen_handle = unreal.register_slate_post_tick_callback(_gen_tick)


def stage_status():
    rows = []
    for a in sorted(footprint_actors(), key=lambda a: a.get_actor_label()):
        pc = a.get_component_by_class(unreal.PCGComponent)
        comps = a.get_components_by_class(unreal.InstancedStaticMeshComponent)
        inst = sum(c.get_instance_count() for c in comps)
        rows.append([a.get_actor_label(), pc.get_editor_property("generated"), len(comps), inst])
    out["actors"] = rows


def stage_boxes(state="off"):
    hidden = state == "off"
    n = 0
    for a in eas().get_all_level_actors():
        if a.get_actor_label().startswith("Buildings_"):
            a.set_is_temporarily_hidden_in_editor(hidden)
            a.set_actor_hidden_in_game(hidden)
            a.set_actor_enable_collision(not hidden)
            n += 1
    out["box_actors"] = n
    out["hidden"] = hidden


STAGES = {"test": stage_test, "footprints": stage_footprints, "generate": stage_generate, "status": stage_status,
          "boxes": stage_boxes}


def run(stage, args):
    try:
        out["stage"] = stage
        t0 = time.time()
        STAGES[stage](*args)
        out["seconds"] = round(time.time() - t0, 1)
        out["ok"] = True
    except Exception:
        out["error"] = traceback.format_exc()
    if stage != "generate" or "error" in out:
        _write(out)
    else:
        _write({**out, "running": True})


_stage = sys.argv[1] if len(sys.argv) > 1 else "status"
_args = sys.argv[2:]
_write({"stage": _stage, "running": True})
_h = None


def _tick(dt):
    unreal.unregister_slate_post_tick_callback(_h)
    run(_stage, _args)


_h = unreal.register_slate_post_tick_callback(_tick)
