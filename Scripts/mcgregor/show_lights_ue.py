"""McGregorNight show lights (Kenny, 20 Oct 2026, agent "show-lights"): the runtime lighting that reacts to the car.

Kenny: "those red bar lights, when the car passes by them, they should get brighter as the car gets near them." and
"in the night time scene, we need a set of sky floodlights to turn on facing the fleet lineup, shining toward the
roadster/car to trigger and turn on when the roadster starts to drive on the white line toward the fleet jump. it should
stay on for 12 seconds and then fade off again."

The behaviour is C++ (Source/SkyCity/SkysterShowLights.h/.cpp, class ASkysterShowLights); this script places and tunes
it from Saved/McGregor/demo_layout.json, so it follows the layout (rerun it after demo_layout.py / an unveil rebuild /
night_ue.py). Everything it adds carries the tag SC_ShowLights and a "Show_" label (no MG_Generated / SC_Night tag, so
build_mcgregor_ue.py and night_ue.py leave it alone); rerunning replaces it.

  map        open /Game/Maps/McGregorNight
  inventory  list the red LED pieces in the level (actor, mesh, instances, slots) -> out JSON (read-only)
  mats       MI_Show_FloodBeam (the floods' light shafts, child of night_ue.py's M_SkyBeam)
  place      remove the old Show_* actors, then place:
               Show_FloodMasts     MG_StadiumLight masts beyond the line-up (both sides of the kickflip run-out,
                                   clear of every keep_clear lane and the buildings), facing back along the fleet line
               Show_Flood_<k>_*    their spot lights: a wide wash on the approach and a tighter one that follows the car
               Show_FloodBeam_*    light shafts from each bank toward the approach
               Show_Lights         the ASkysterShowLights actor: trigger corridor = the fleet line (white line toward the
                                   fleet jump), the LED strips (demo_layout "paint" entries with mat "led", sampled on the
                                   lot), the glow and flood numbers below
             and tags the reactive pieces SC_ShowBar (Demo_MG_LanePost, Demo_MG_ShowWall, Demo_MG_LEDStrip; the C++ also
             finds them by mesh name, so an unveil rebuild that drops the tag doesn't break them).
             Needs the rebuilt editor (unreal.SkysterShowLights). Without it, `place` refuses unless given `proto`:
             then it places only the masts / lights / shafts (lit, as in the editor) for a look test; run `remove`
             afterwards, because without the C++ actor nothing would switch them off in game.
  shots      captures of the show area (Saved/McGregor/shots/show/<tag>_*.png; tag=..., set=look|bars), or
             shots@<tag>@<sets> to have several in one run
  remove     delete every Show_* actor and the SC_ShowBar tags
  save       save the level
  finish     save everything and load SkyCityMashup (before dropping the editor lock)
Run in the editor (PIE off, editor lock held):
  py Scripts/mcgregor/show_lights_ue.py            (= map mats place save)
  py .../show_lights_ue.py map inventory          py .../show_lights_ue.py map place proto shots tag=proto
Writes Saved/MCPScripts/out_show_lights.json. Test in PIE: Saved/Playtest/showlights_pt.py (see its docstring).
"""
import json, math, os, sys, time, traceback, types, unreal

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
OUT = ROOT + "/Saved/MCPScripts/out_show_lights.json"
SHOTS = ROOT + "/Saved/McGregor/shots/show"
NIGHT = "/Game/Maps/McGregorNight"
src = open(ROOT + "/Scripts/mcgregor/build_mcgregor_ue.py").read().split("QUEUE = [")[0]
B = types.ModuleType("mcg_defs")
B.__file__ = ROOT + "/Scripts/mcgregor/build_mcgregor_ue.py"
exec(compile(src.replace("STAGES = sys.argv[1:] or", "STAGES = [] or"), "mcg_defs", "exec"), B.__dict__)
EAL, EAS, MEL = B.EAL, B.EAS, B.MEL
L = json.load(open(ROOT + "/Saved/McGregor/demo_layout.json"))
ARGS = [a for a in sys.argv[1:] if "=" not in a]
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
PROTO = "proto" in ARGS
STAGES = [a for a in ARGS if a != "proto"] or ["map", "mats", "place", "save"]
TAG = "SC_ShowLights"
FOLDER = "McGregorNight/Show"
K_LIGHT = 0.14             # night_ue.py's light scale (this level's daylight is a 10 lux sun)

# ================================================================= KEY NUMBERS
# --- proximity glow (Kenny: the red bars get brighter as the car gets near them)
GLOW = {
    "boost": 3.0,             # brightness x (1 + boost): four times as bright right by the car
    "near_m": 10.0,           # full boost within this of the car ...
    "far_m": 35.0,            # ... back to normal by this
    "rise_s": 0.12,           # easing time constants (brighten fast, dim a bit slower: a short trail behind the car)
    "fall_s": 0.6,
    "strip_segment_m": 2.5,   # the LED ribbons are re-laid as glowing bars of about this length
    "strip_width_m": 0.14,    # a touch wider and taller than the painted 0.12 m ribbon, which hides inside them
    "strip_thick_m": 0.065,
    "strip_light_every_m": 10.0, "strip_light_lm": 3000.0, "strip_light_radius_m": 6.0, "strip_light_h_m": 0.4,
    "post_light_lm": 6000.0, "post_light_radius_m": 9.0,     # a red light at each lane post's pole (MG_LanePost)
}
REACTIVE_LABELS = ["Demo_MG_LanePost", "Demo_MG_ShowWall", "Demo_MG_LEDStrip"]
REACTIVE_MESHES = ["MG_LanePost", "MG_ShowWall", "MG_LEDStrip"]
# --- the trigger: the car enters the start of the fleet line, moving along it toward the line-up
TRIGGER = {
    "from_m": 0.0,            # zone along the line from its start (the kickflip run's start, by the lane posts) ...
    "to_m": 35.0,             # ... to here (capped at 45 % of the line); it ends well before the run-up crosses the line
    "half_m": 9.0,            # either side of the white line (the lane posts stand at 7.5 m)
    "max_up_m": 8.0,          # not when flying over it
    "min_speed_ms": 5.0,      # along the line, toward the line-up
    "min_align": 0.6,         # share of the car's speed that is along the line
    "rearm_half_m": 14.0, "rearm_before_m": 15.0, "rearm_past_m": 30.0,   # leave this corridor to re-arm
}
# --- the floods: masts beyond the line-up, aimed back along the fleet line at the approaching car
FLOOD = {
    "fade_in_s": 0.4, "hold_s": 12.0, "fade_out_s": 1.5,
    # (distance m from the line-up's centre, degrees off the fleet line's axis beyond the row); each one mirrored to
    # both sides of the line. They must clear the kickflip run-out (42 m either side, 75 m past the row): placed ones
    # that don't are pushed further out.
    "masts": [(76.0, 52.0), (100.0, 38.0)],   # (21 Oct, Kenny: lights in the fleet-jump path) was (70, 50), (95, 35): now >= 59 m off the line
    "aim_back_m": 50.0,       # they aim at the fleet line this far before the row (where the car comes from), 1 m up
    "head_z_m": 22.4,         # MG_StadiumLight's lamp bank
    "wash": {"lm": 1200000.0, "outer": 24.0, "inner": 10.0, "radius_m": 320.0},
    "track": {"lm": 800000.0, "outer": 12.0, "inner": 5.0, "radius_m": 320.0},
    "shadows": 2,             # the two masts nearest the line's axis cast shadows (the car's shadow runs back at you)
    "beams": 3, "beam_len_m": 120.0, "beam_spread": 0.05, "beam_fan_m": 12.0, "beam_strength": 0.05,
    # the visible light shafts never enter the fleet-jump corridor (21 Oct, Kenny: "weird lights in the way of the fleet
    # jump"): each one is cut where it would come within shaft_clear_m of the fleet line (run start -> past the row ->
    # corridor_far_m beyond the row's centre, i.e. the landing and the whole run-out) and stays fixed (not tracked), so
    # it can't swing across the line; the spot lights still aim at / follow the approaching car
    "shaft_clear_m": 14.0, "corridor_far_m": 135.0,
    "track_max_deg": 30.0, "track_rate": 3.0,
    "color": (0.82, 0.9, 1.0),   # cold white, like night_ue.py's stadium banks
}
# =================================================================
out = {"stages": STAGES, "proto": PROTO}


def log(k, v):
    out[k] = v
    open(OUT, "w").write(json.dumps(out, indent=1, default=str))


def U(x, y, z=0.0):
    return unreal.Vector(y * 100.0, x * 100.0, z * 100.0)


def yaw_to(a, b):
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))


def look_rot(a, b):
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    return unreal.Rotator(roll=0, pitch=math.degrees(math.atan2(dz, math.hypot(dx, dy))), yaw=math.degrees(math.atan2(dx, dy)))


def seg_dist(p, a, b):
    ab = (b[0] - a[0], b[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / ((ab[0] ** 2 + ab[1] ** 2) or 1.0)))
    return math.dist(p, (a[0] + ab[0] * t, a[1] + ab[1] * t))


def lanes_clear(p, pad):
    return all(seg_dist(p, c["a"], c["b"]) > c["half"] + pad for c in L.get("keep_clear", []))


def in_building(p, pad=4.0):
    for b in L.get("buildings", []):
        r = math.radians(b["yaw"])
        dx, dy = p[0] - b["p"][0], p[1] - b["p"][1]
        a, w = dx * math.sin(r) + dy * math.cos(r), dx * math.cos(r) - dy * math.sin(r)
        if abs(a) < b["len"] / 2 + pad and abs(w) < b["wid"] / 2 + pad:
            return True
    return False


def tags_of(a):
    return [str(t) for t in a.tags]


def world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def lot_z(x, y):
    """The surface under a plan point, skipping anything standing on the lot (line-up cars, set pieces, lights, our own
    masts): retrace past such hits, up to 8 times."""
    v = U(x, y)
    ignore = []
    t = None
    for _ in range(8):
        hit = unreal.SystemLibrary.line_trace_single(world(), unreal.Vector(v.x, v.y, 50000), unreal.Vector(v.x, v.y, -50000),
                                                     unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, ignore, unreal.DrawDebugTrace.NONE, True)
        if not hit:
            break
        t = hit.to_tuple()
        act = t[9]
        if act is None:
            break
        lab = act.get_actor_label()
        tg = tags_of(act)
        if not (lab.startswith(STANDING) or any(x_ in tg for x_ in ("SC_Lineup", "SC_Night", TAG))):
            break
        ignore.append(act)
    return t[4].z / 100.0 if t else 0.0


STANDING = ("Lineup_", "Demo_", "Show_", "Night_", "UV_", "Pickup", "SC_", "BP_")


def actor_by_label(lab):
    return [a for a in EAS.get_all_level_actors() if a.get_actor_label() == lab]


def show_actor(a, label, extra_tags=()):
    a.set_actor_label(label)
    a.tags = [TAG] + list(extra_tags)
    a.set_folder_path(FOLDER)
    return a


# ------------------------------------------------------------------ geometry from the layout
def frame():
    A, K = L["lines"]["fleet"]                                  # kickflip run start -> the row's near end
    d = (K[0] - A[0], K[1] - A[1])
    n = math.hypot(*d)
    u = (d[0] / n, d[1] / n)                                    # along the run, toward the line-up
    left = (-u[1], u[0])
    row = L["lineup"]
    rc = (sum(v["p"][0] for v in row) / len(row), sum(v["p"][1] for v in row) / len(row))
    return A, K, n, u, left, rc


def mast_spots():
    A, K, n, u, left, rc = frame()
    spots = []
    for R, ang in FLOOD["masts"]:
        for s_ in (1, -1):
            a = math.radians(ang)
            p = None
            for push in range(0, 41, 4):                        # pushed straight out from the row until clear
                r = R + push
                q = (rc[0] + u[0] * r * math.cos(a) + left[0] * s_ * r * math.sin(a),
                     rc[1] + u[1] * r * math.cos(a) + left[1] * s_ * r * math.sin(a))
                if lanes_clear(q, 6.0) and not in_building(q):
                    p = q
                    break
            if p:
                spots.append({"p": p, "R": R, "ang": ang, "side": s_})
    return spots


# ------------------------------------------------------------------ stages
def stage_map():
    if world().get_path_name().split(".")[0] != NIGHT:
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(NIGHT)
    log("map", world().get_path_name())


def stage_inventory():
    """Every static mesh component with a red LED slot (MI_Night_LEDRed, or a slot named *LEDRed* / *RedLamp* /
    *RampTrim*): actor label, mesh, instance count, the matching slots and their materials, position."""
    led = EAL.load_asset(f"{B.DIR}/Materials/MI_Night_LEDRed")
    rows = []
    for a in EAS.get_all_level_actors():
        for c in a.get_components_by_class(unreal.StaticMeshComponent):
            sm = c.static_mesh
            if not sm:
                continue
            names = [str(s.get_editor_property("material_slot_name")) for s in sm.get_editor_property("static_materials")]
            hits = []
            for i, nm in enumerate(names):
                m = c.get_material(i)
                if (led and m == led) or any(w in nm for w in ("LEDRed", "RedLamp", "RampTrim")):
                    hits.append({"slot": i, "name": nm, "mat": m.get_name() if m else None})
            if not hits:
                continue
            n = c.get_instance_count() if isinstance(c, unreal.InstancedStaticMeshComponent) else 1
            org, ext, _r = unreal.SystemLibrary.get_component_bounds(c)
            rows.append({"actor": a.get_actor_label(), "class": a.get_class().get_name(), "comp": c.get_name(), "mesh": sm.get_name(),
                         "instances": n, "slots": hits, "tags": tags_of(a), "size_m": [round(v / 50.0, 1) for v in ext.to_tuple()],
                         "centre_plan_m": [round(org.y / 100.0, 1), round(org.x / 100.0, 1), round(org.z / 100.0, 1)],
                         "reactive": sm.get_name() in REACTIVE_MESHES or a.get_actor_label() in REACTIVE_LABELS or sm.get_name() == "SM_MG_DemoLines"})
    log("inventory", rows)
    log("strips", [p for p in L.get("paint", []) if p.get("mat") == "led"])


def stage_mats():
    jet = EAL.load_asset("/Game/SkyCity/Pickups/Materials/M_SkyBeam")
    m = B.mi("MI_Show_FloodBeam", jet, {"Strength": FLOOD["beam_strength"]}, {"Color": FLOOD["color"]})
    log("mats", m.get_path_name())


def remove_show():
    gone = 0
    for a in EAS.get_all_level_actors():
        if TAG in tags_of(a):
            EAS.destroy_actor(a)
            gone += 1
    untag = 0
    for a in EAS.get_all_level_actors():
        if "SC_ShowBar" in tags_of(a):
            a.modify()
            a.tags = [t for t in a.tags if str(t) != "SC_ShowBar"]
            untag += 1
    return gone, untag


def stage_remove():
    log("removed", dict(zip(("actors", "untagged"), remove_show())))


def instanced(label, mesh, xfs, tags):
    act = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    show_actor(act, label, tags)
    c = B.add_component(act, unreal.HierarchicalInstancedStaticMeshComponent)
    c.set_static_mesh(mesh)
    c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_editor_property("cast_shadow", True)
    c.set_collision_profile_name("BlockAll")
    c.set_cull_distances(320000, 400000)
    c.add_instances(xfs, False, True)
    return act, c


def spot(label, at, target, p, color, shadows, tags):
    a = EAS.spawn_actor_from_class(unreal.SpotLight, U(*at), look_rot(at, target))
    show_actor(a, label, tags)
    c = a.get_component_by_class(unreal.SpotLightComponent)
    c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
    c.set_editor_property("intensity", p["lm"] * K_LIGHT)
    c.set_editor_property("attenuation_radius", p["radius_m"] * 100.0)
    c.set_editor_property("outer_cone_angle", p["outer"])
    c.set_editor_property("inner_cone_angle", p["inner"])
    c.set_editor_property("cast_shadows", shadows)
    c.set_editor_property("light_color", unreal.Color(r=int(color[0] * 255), g=int(color[1] * 255), b=int(color[2] * 255), a=255))
    return a


def beam(label, mesh, mat, at, target, length, spread, tags):
    a = EAS.spawn_actor_from_object(mesh, U(*at), look_rot(at, target))
    show_actor(a, label, tags)
    c = a.static_mesh_component
    c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_collision_profile_name("NoCollision")
    c.set_editor_property("cast_shadow", False)
    c.set_material(0, mat)
    a.set_actor_scale3d(unreal.Vector(length, length * spread, length * spread))
    return a


def setp(obj, name, value):
    obj.set_editor_property(name, value)
    return name


def stage_place():
    have_cls = hasattr(unreal, "SkysterShowLights")
    if not have_cls and not PROTO:
        log("place", "REFUSED: unreal.SkysterShowLights is missing (editor not rebuilt yet). Use `place proto` for a look "
                     "test and `remove` afterwards: without the C++ actor the floods would stay lit in game.")
        return
    gone, _ = remove_show()
    A, K, n, u, left, rc = frame()
    zA, zK, zr = lot_z(*A), lot_z(*K), lot_z(*rc)
    report = {"removed_first": gone, "class": have_cls, "line": [A, K], "line_len_m": round(n, 1), "row_centre": rc}
    # ---- the flood masts, lights and shafts
    mast = B.kit_mesh("MG_StadiumLight")
    cone = B.kit_mesh("MG_BeamCone")
    lamp = EAL.load_asset(f"{B.DIR}/Materials/MI_Night_Lamp")
    shaft = EAL.load_asset(f"{B.DIR}/Materials/MI_Show_FloodBeam") or EAL.load_asset(f"{B.DIR}/Materials/MI_Night_Beam")
    aim = (rc[0] - u[0] * FLOOD["aim_back_m"], rc[1] - u[1] * FLOOD["aim_back_m"])
    za = lot_z(*aim)
    spots = mast_spots()
    cor_far = (rc[0] + u[0] * FLOOD["corridor_far_m"], rc[1] + u[1] * FLOOD["corridor_far_m"])   # corridor: A -> cor_far
    shafts_cut = []

    def shaft_length(bh, bt, full):
        """Longest length (<= full) a shaft from bh toward bt can have before it comes within shaft_clear_m of the corridor."""
        dxy = math.hypot(bt[0] - bh[0], bt[1] - bh[1]) or 1.0
        dz = bt[2] - bh[2]
        d3 = math.hypot(dxy, dz) or 1.0
        for i in range(0, int(full) + 1):
            t = i / d3                                         # i metres along the 3D direction
            q = (bh[0] + (bt[0] - bh[0]) * t, bh[1] + (bt[1] - bh[1]) * t)
            if seg_dist(q, A, cor_far) < FLOOD["shaft_clear_m"]:
                return float(max(0, i - 1))
        return float(full)
    xfs, masts = [], []
    for s in spots:
        x, y = s["p"]
        z = lot_z(x, y)
        yw = yaw_to((x, y), aim)
        xfs.append(unreal.Transform(U(x, y, z), unreal.Rotator(roll=0, pitch=0, yaw=yw + B.KIT_FRONT), unreal.Vector(1, 1, 1)))
        masts.append((x, y, z, yw, s))
    if mast and xfs:
        act, hism = instanced("Show_FloodMasts", mast, xfs, ("SC_ShowFlood", "NoWallRide"))
        sm = hism.static_mesh
        for i, slot in enumerate(sm.get_editor_property("static_materials")):
            if "LampLens" in str(slot.get_editor_property("material_slot_name")) and lamp:
                hism.set_material(i, lamp)
    near_axis = sorted(range(len(masts)), key=lambda k: abs(masts[k][4]["ang"]) + masts[k][4]["R"] * 0.01)[:FLOOD["shadows"]]
    col = FLOOD["color"]
    for k, (x, y, z, yw, s) in enumerate(masts):
        f = (math.sin(math.radians(yw)), math.cos(math.radians(yw)))
        sd = (f[1], -f[0])                                       # the bank's right
        head = (x + f[0] * 1.0, y + f[1] * 1.0, z + FLOOD["head_z_m"])
        tgt = (aim[0], aim[1], za + 1.0)
        spot(f"Show_Flood_{k}_wash", (head[0] - sd[0] * 0.8, head[1] - sd[1] * 0.8, head[2]), tgt, FLOOD["wash"], col, k in near_axis, ("SC_ShowFlood",))
        spot(f"Show_Flood_{k}_track", (head[0] + sd[0] * 0.8, head[1] + sd[1] * 0.8, head[2]), tgt, FLOOD["track"], col, False, ("SC_ShowFlood", "SC_ShowTrack"))
        if cone and shaft:
            for j in range(FLOOD["beams"]):
                o = (j - (FLOOD["beams"] - 1) / 2) * FLOOD["beam_fan_m"]
                bt = (aim[0] + left[0] * o, aim[1] + left[1] * o, za + 1.0 + abs(o) * 0.15)
                bh = (head[0] + sd[0] * 0.8, head[1] + sd[1] * 0.8, head[2] - 0.3)
                full = FLOOD["beam_len_m"]
                blen = shaft_length(bh, bt, full)
                if blen < 8.0:
                    shafts_cut.append({"beam": f"{k}_{j}", "len_m": 0.0, "skipped": True})
                    continue
                # the cone's far radius is length x spread: keep that ratio, so a cut shaft is a shorter, thinner one
                beam(f"Show_FloodBeam_{k}_{j}", cone, shaft, bh, bt, blen, FLOOD["beam_spread"], ("SC_ShowFloodBeam",))
                d3 = math.dist(bh, bt) or 1.0
                tip = (bh[0] + (bt[0] - bh[0]) * blen / d3, bh[1] + (bt[1] - bh[1]) * blen / d3)
                shafts_cut.append({"beam": f"{k}_{j}", "len_m": round(blen, 1), "of_m": full, "tip_to_line_m": round(seg_dist(tip, A, cor_far), 1)})
    report["masts"] = [{"plan": [round(x, 1), round(y, 1)], "z": round(z, 2), "yaw": round(yw, 1), "R": s["R"], "ang": s["ang"], "side": s["side"],
                        "to_line_start_m": round(math.dist((x, y), A), 1), "to_aim_m": round(math.dist((x, y), aim), 1)} for x, y, z, yw, s in masts]
    report["aim"] = [round(aim[0], 1), round(aim[1], 1), round(za, 2)]
    report["mast_to_corridor_m"] = [round(seg_dist((x, y), A, cor_far), 1) for x, y, z, yw, s in masts]
    report["shafts"] = shafts_cut
    # ---- tag the reactive pieces (the C++ also matches their mesh names)
    tagged = []
    for lab in REACTIVE_LABELS:
        for a in actor_by_label(lab):
            if "SC_ShowBar" not in tags_of(a):
                a.modify()
                a.tags = list(a.tags) + ["SC_ShowBar"]
            tagged.append(lab)
    report["tagged"] = tagged
    # ---- the LED strips, sampled every 2 m on the lot (same sampling as build_mcgregor_ue.py's ribbons)
    strips = []
    for pt in L.get("paint", []):
        if pt.get("mat") != "led":
            continue
        pts = []
        for a, b in zip(pt["pts"], pt["pts"][1:]):
            m = max(1, int(math.dist(a, b) / 2.0))
            pts += [(a[0] + (b[0] - a[0]) * i / m, a[1] + (b[1] - a[1]) * i / m) for i in range(m)]
        pts.append(tuple(pt["pts"][-1]))
        strips.append([U(x, y, lot_z(x, y)) for x, y in pts])
    report["strips"] = [{"points": len(s), "len_m": round(sum((s[i] - s[i - 1]).length() for i in range(1, len(s))) / 100.0, 1)} for s in strips]
    # ---- the ASkysterShowLights actor
    if have_cls:
        a = EAS.spawn_actor_from_class(unreal.SkysterShowLights, U(rc[0], rc[1], zr + 1.0), unreal.Rotator(0, 0, 0))
        show_actor(a, "Show_Lights")
        led = EAL.load_asset(f"{B.DIR}/Materials/MI_Night_LEDRed")
        g = GLOW
        sl = []
        for s in strips:
            o = unreal.SkyShowStrip()
            o.set_editor_property("points", s)
            o.set_editor_property("width", g["strip_width_m"] * 100.0)
            sl.append(o)
        to_m = min(TRIGGER["to_m"], 0.45 * n)
        props = {
            "glow": True, "reactive_tag": "SC_ShowBar", "reactive_mesh_names": REACTIVE_MESHES,
            "led_materials": [led] if led else [], "led_slot_names": ["LEDRed"], "glow_param": "Strength",
            "boost": g["boost"], "near_dist": g["near_m"] * 100.0, "far_dist": g["far_m"] * 100.0,
            "rise_time": g["rise_s"], "fall_time": g["fall_s"],
            "strips": sl, "strip_material": led, "strip_segment": g["strip_segment_m"] * 100.0,
            "strip_thickness": g["strip_thick_m"] * 100.0, "strip_lift": 0.5,
            "strip_light_spacing": g["strip_light_every_m"] * 100.0, "strip_light_lumens": g["strip_light_lm"] * K_LIGHT,
            "strip_light_radius": g["strip_light_radius_m"] * 100.0, "strip_light_height": g["strip_light_h_m"] * 100.0,
            "piece_light_meshes": ["MG_LanePost"], "piece_light_lumens": g["post_light_lm"] * K_LIGHT,
            "piece_light_radius": g["post_light_radius_m"] * 100.0,
            "floods": True, "flood_tag": "SC_ShowFlood", "flood_beam_tag": "SC_ShowFloodBeam", "track_tag": "SC_ShowTrack",
            "fade_in_time": FLOOD["fade_in_s"], "hold_time": FLOOD["hold_s"], "fade_out_time": FLOOD["fade_out_s"],
            "track_car": True, "track_max_angle": FLOOD["track_max_deg"], "track_rate": FLOOD["track_rate"],
            "line_start": U(A[0], A[1], zA), "line_end": U(K[0], K[1], zK),
            "trigger_from": TRIGGER["from_m"] * 100.0, "trigger_to": to_m * 100.0, "trigger_half_width": TRIGGER["half_m"] * 100.0,
            "trigger_max_height": TRIGGER["max_up_m"] * 100.0, "min_speed": TRIGGER["min_speed_ms"] * 100.0,
            "min_align": TRIGGER["min_align"], "rearm_half_width": TRIGGER["rearm_half_m"] * 100.0,
            "rearm_before": TRIGGER["rearm_before_m"] * 100.0, "rearm_past": TRIGGER["rearm_past_m"] * 100.0,
        }
        bad = []
        for k_, v in props.items():
            try:
                setp(a, k_, v)
            except Exception as e:
                bad.append(f"{k_}: {e}")
        report["actor"] = a.get_actor_label()
        report["props_failed"] = bad
        report["trigger_zone_m"] = [TRIGGER["from_m"], round(to_m, 1)]
    else:
        report["actor"] = "none (proto: masts, lights and shafts only, LIT; run `remove` after the look test)"
    log("place", report)


def stage_shots(tag=None, sets=None):
    """Viewport captures (level viewport camera, high-res screenshot), like Saved/MCPScripts/unveil_shots.py.
    Stage token `shots` (tag= / set= arguments) or `shots@<tag>@<set,set>`."""
    os.makedirs(SHOTS, exist_ok=True)
    A, K, n, u, left, rc = frame()
    run_from = (A[0] - u[0] * 25, A[1] - u[1] * 25)
    poses = {
        "look": [("approach", run_from, 1.6, 2.0, yaw_to(run_from, rc)),
                 ("approach_high", (A[0] - u[0] * 40 + left[0] * 25, A[1] - u[1] * 40 + left[1] * 25), 14.0, -6.0, yaw_to(A, rc)),
                 ("from_row", (rc[0] - u[0] * 15, rc[1] - u[1] * 15), 2.0, 3.0, yaw_to(rc, A)),
                 ("drone", (rc[0] - u[0] * 60 - left[0] * 120, rc[1] - u[1] * 60 - left[1] * 120), 60.0, -22.0, yaw_to((rc[0] - u[0] * 60 - left[0] * 120, rc[1] - u[1] * 60 - left[1] * 120), (rc[0] + u[0] * 40, rc[1] + u[1] * 40)))],
        "bars": [("line_start", run_from, 1.6, 0.0, yaw_to(run_from, rc)),
                 ("runup", tuple(L["start"]["p"]), 1.8, 1.0, L["start"]["yaw"]),
                 ("posts_close", (A[0] + u[0] * 6 + left[0] * 2, A[1] + u[1] * 6 + left[1] * 2), 1.5, 0.0, yaw_to(A, rc) - 20.0),
                 ("top", ((A[0] + rc[0]) / 2, (A[1] + rc[1]) / 2), 160.0, -90.0, 0.0)],
    }
    sel = []
    for s in (sets or KV.get("set", "look,bars")).split(","):
        sel += poses.get(s, [])
    tag = tag or KV.get("tag", "show")
    res = [int(v) for v in KV.get("res", "1280x720").split("x")]
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    st = {"i": 0, "k": 0, "files": []}
    wait = int(KV.get("wait", "45"))

    def tick(dt):
        try:
            if st["i"] >= len(sel):
                unreal.unregister_slate_post_tick_callback(st["h"])
                log("shots", st["files"])
                SHOOTING[0] = False
                return
            name, p, zm, pitch, yaw = sel[st["i"]]
            if st["k"] == 0:
                z = zm + (lot_z(*p) if zm < 40 else 0.0)
                ues.set_level_viewport_camera_info(U(p[0], p[1], z), unreal.Rotator(roll=0, pitch=pitch, yaw=yaw))
            if st["k"] == wait:
                fn = f"{SHOTS}/{tag}_{st['i']:02d}_{name}.png"
                unreal.AutomationLibrary.take_high_res_screenshot(res[0], res[1], fn)
                st["files"].append(fn)
            st["k"] += 1
            if st["k"] > wait + 20:
                st["k"] = 0
                st["i"] += 1
        except Exception:
            unreal.unregister_slate_post_tick_callback(st["h"])
            log("shots_error", traceback.format_exc())
            SHOOTING[0] = False

    log("shots_started", [s[0] for s in sel])
    SHOOTING[0] = True
    st["h"] = unreal.register_slate_post_tick_callback(tick)


def stage_save():
    log("save_level", unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level())
    log("save_dirty", unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True))


def stage_finish():
    """The agents' rule before dropping the editor lock: everything saved, back on SkyCityMashup."""
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level("/Game/Maps/SkyCityMashup")
    log("finish", {"now": world().get_path_name(),
                   "dirty": [str(p.get_name()) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]})


def _stage(tok):
    if tok.startswith("shots@"):
        _, tg, sets = (tok.split("@") + ["", ""])[:3]
        return (tok, lambda: stage_shots(tg or None, sets or None))
    return (tok, globals()["stage_" + tok])


if unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world():
    log("error", "PIE is running: stop it first")
    STAGES = []
QUEUE = [_stage(s) for s in STAGES]
BUSY = [False]
SHOOTING = [False]          # the shots stage runs over many frames: the queue waits for it
T0 = time.time()
_h = None


def tick(dt):
    if BUSY[0] or SHOOTING[0]:
        return
    BUSY[0] = True
    try:
        if not QUEUE:
            unreal.unregister_slate_post_tick_callback(_h)
            log("done", round(time.time() - T0, 1))
            return
        name, fn = QUEUE.pop(0)
        fn()
        log("stage", name)
    except Exception:
        unreal.unregister_slate_post_tick_callback(_h)
        log("error", traceback.format_exc())
    finally:
        BUSY[0] = False


_h = unreal.register_slate_post_tick_callback(tick)
