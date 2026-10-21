"""Collision for the City Sample buildings, so the Skyster can hit, land on and wall-ride them.

The PCG-generated building pieces (2.2M instances) have no collision, and turning it on per instance would
swamp the physics scene. Instead: measure each footprint's real height from its generated facade pieces, then
build one invisible, low-poly collision mesh with a box per footprint (same footprints as buildings_v3.json).

Height per footprint: the lowest of its four edges' tallest facade piece (a taller neighbour sharing a wall
only raises that one edge), raised by any facade pieces set back inside the footprint (tower setbacks).
Runs in per-frame chunks. Re-run after regenerating the buildings.
    py Scripts/unreal/building_collision.py
Writes Saved/MCPScripts/out_bcoll.json."""
import json, math, time, traceback, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_bcoll.json"
MESH = "/Game/City/Meshes/SM_BuildingCollision"
LABEL = "BuildingCollision"
EDGE = 150.0      # cm: a facade piece within this of a footprint edge belongs to that edge
CELL = 5000.0     # cm: spatial hash for footprints
FACADE = ("_Wall_", "_CornerEx_", "_CornerIn_", "_Column_")

B = json.load(open(ROOT + "/Saved/Mashup/buildings_v3.json"))["buildings"]
fps = []
grid = {}
for i, b in enumerate(B):
    X, Y = b["y"] * 100.0, b["x"] * 100.0           # plan (x, y) metres -> Unreal (X = y, Y = x) cm
    a = math.radians(90.0 - b["yaw"])
    hw, hd = b["w"] * 50.0, b["d"] * 50.0
    fps.append({"X": X, "Y": Y, "ca": math.cos(a), "sa": math.sin(a), "hw": hw, "hd": hd, "yaw": 90.0 - b["yaw"],
                "w": b["w"] * 100.0, "d": b["d"] * 100.0, "edge": [0.0, 0.0, 0.0, 0.0], "edge_n": [0, 0, 0, 0], "inside": 0.0, "bottom": 1e9})
    r = math.hypot(hw, hd) + EDGE
    for gx in range(int((X - r) // CELL), int((X + r) // CELL) + 1):
        for gy in range(int((Y - r) // CELL), int((Y + r) // CELL) + 1):
            grid.setdefault((gx, gy), []).append(i)

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
vols = [a for a in eas.get_all_level_actors() if a.get_actor_label().startswith("CS_")]
st = {"i": 0, "inst": 0, "unassigned": 0, "t0": time.time()}
_h = None


def measure(vol):
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        m = c.static_mesh
        if not m:
            continue
        name = m.get_name()
        if "_decal" in name or not any(k in name for k in FACADE):
            continue
        bb = m.get_bounding_box()
        top_k, bot_k = bb.max.z, bb.min.z
        for n in range(c.get_instance_count()):
            t = c.get_instance_transform(n, True)
            p, sz = t.translation, t.scale3d.z
            top, bot = p.z + top_k * sz, p.z + bot_k * sz
            st["inst"] += 1
            hit = False
            for fi in grid.get((int(p.x // CELL), int(p.y // CELL)), ()):
                f = fps[fi]
                dx, dy = p.x - f["X"], p.y - f["Y"]
                u = dx * f["ca"] + dy * f["sa"]
                v = -dx * f["sa"] + dy * f["ca"]
                du, dv = f["hw"] - abs(u), f["hd"] - abs(v)
                if du < -EDGE or dv < -EDGE:
                    continue
                hit = True
                if du < EDGE or dv < EDGE:
                    e = (0 if u > 0 else 1) if du < dv else (2 if v > 0 else 3)
                    if top > f["edge"][e]:
                        f["edge"][e] = top
                    f["edge_n"][e] += 1
                elif top > f["inside"]:
                    f["inside"] = top
                if bot < f["bottom"]:
                    f["bottom"] = bot
            if not hit:
                st["unassigned"] += 1


def build():
    out = {"volumes": len(vols), "instances": st["inst"], "unassigned": st["unassigned"], "seconds": round(time.time() - st["t0"], 1)}
    P = unreal.GeometryScript_Primitives
    OPT = unreal.GeometryScriptPrimitiveOptions()
    dm = unreal.DynamicMesh()
    made, heights = 0, []
    for f in fps:
        edges = [f["edge"][k] for k in range(4) if f["edge_n"][k] >= 3]
        if not edges:
            continue
        h = max(min(edges), f["inside"])
        z0 = min(f["bottom"], 0.0) - 50.0
        if h - z0 < 300.0:
            continue
        P.append_box(dm, OPT, unreal.Transform(unreal.Vector(f["X"], f["Y"], z0), unreal.Rotator(roll=0, pitch=0, yaw=f["yaw"]), unreal.Vector(1, 1, 1)),
                     f["w"], f["d"], h - z0, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        made += 1
        heights.append(h / 100.0)
    out["boxes"] = made
    heights.sort()
    if heights:
        out["height_m"] = {"min": round(heights[0], 1), "median": round(heights[len(heights) // 2], 1), "max": round(heights[-1], 1)}
    EAL = unreal.EditorAssetLibrary
    if EAL.does_asset_exist(MESH):
        for a in eas.get_all_level_actors():
            if a.get_actor_label() == LABEL:
                eas.destroy_actor(a)
        EAL.delete_asset(MESH)
    opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
    for k, v in (("enable_recompute_normals", False), ("enable_nanite", False), ("enable_collision", True)):
        try:
            opts.set_editor_property(k, v)
        except Exception:
            pass
    res = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, MESH, opts)
    sm = res[0] if isinstance(res, (tuple, list)) else res
    bs = sm.get_editor_property("body_setup")
    bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    EAL.save_loaded_asset(sm)
    act = eas.spawn_actor_from_object(sm, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    act.set_actor_label(LABEL)
    act.set_folder_path("City/Buildings")
    act.tags = ["City_Generated"]
    smc = act.static_mesh_component
    smc.set_collision_profile_name("BlockAll")
    smc.set_editor_property("visible", False)
    smc.set_editor_property("cast_shadow", False)
    act.set_actor_hidden_in_game(True)
    act.set_editor_property("is_spatially_loaded", False)
    out["save_level"] = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    out["save_dirty"] = unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    return out


def tick(dt):
    try:
        if st["i"] < len(vols):
            measure(vols[st["i"]])
            st["i"] += 1
            if st["i"] % 10 == 0:
                open(OUT, "w").write(json.dumps({"running": st["i"], "of": len(vols), "inst": st["inst"]}))
            return
        unreal.unregister_slate_post_tick_callback(_h)
        open(OUT, "w").write(json.dumps(build(), indent=1))
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        open(OUT, "w").write(json.dumps({"error": traceback.format_exc(), "at": st["i"]}, indent=1))


_h = unreal.register_slate_post_tick_callback(tick)
