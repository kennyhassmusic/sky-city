"""Revisit given camera poses and STOP-sign corners on a drive level, in the editor world (no PIE), then quit.
Lane P, 2026-10-28 (v9 street-fix check).
  "$UE" "$PWD/SkyCity.uproject" /Game/Maps/GenCity_Seed7 -nosplash ... \
    -ExecCmds="py <space-free path>/Scripts/gencity/revisit_gencity_ue.py in=Saved/GenCity/revisit_v9.json tag=v9"
Input json: poses[] (name, cam_ue, yaw, pitch: re-shot as they were, 1280x720, FOV 80, through a piloted camera) and
spots[] (car_ue, travel_yaw: a corner where a STOP sign read backwards). For each spot: the STOP-sign instances within
40 m, read from the level's own instanced meshes (the HISM/ISM components whose mesh is KIT_SS_StopSign), each with
its world yaw, and the mesh's own facing (the average normal of its red face section, from the static mesh in
Unreal, turned by the instance's rotation) against the approach: a sign meant for the approach faces back toward the
car (dot of its face normal with the travel direction < 0). A close pedestrian set (1.7 m eye height, 6 m from the
sign) looks at each sign from the front, the back and both sides. Also counts the level's light and sky actors.
Writes Saved/GenCity/revisit_<tag>.json.
"""
import builtins
import json
import math
import os
import sys
import time
import traceback

import unreal

ROOT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")
KV = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
TAG = KV.get("tag", "revisit")
INP = json.load(open(os.path.join(ROOT, KV.get("in", "Saved/GenCity/revisit.json"))))
SETTLE = float(KV.get("settle", "45"))
RES = KV.get("res", "1280x720")
OUT = os.path.join(ROOT, "Saved", "GenCity", "revisit_%s.json" % TAG)
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "MacEditor")
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
res = {"tag": TAG, "done": False, "shots": [], "spots": [], "lights": {}, "log": []}
S = {"t0": time.time(), "q": None}


def write():
    res["secs"] = round(time.time() - S["t0"], 1)
    with open(OUT, "w") as h:
        json.dump(res, h, indent=1, default=str)


def files():
    return set(os.listdir(SHOTS)) if os.path.isdir(SHOTS) else set()


def cmd(c):
    unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), c)


def light_check():
    out = {}
    for a in eas.get_all_level_actors():
        c = a.get_class().get_name()
        if c in ("DirectionalLight", "SkyLight", "SkyAtmosphere", "ExponentialHeightFog", "PostProcessVolume",
                 "VolumetricCloud"):
            out.setdefault(c, []).append(a.get_actor_label())
    return out


def stop_components():
    comps = []
    for a in eas.get_all_level_actors():
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            m = c.get_editor_property("static_mesh")
            if m and "StopSign" in m.get_name():
                comps.append((a, c, m))
    return comps


def mesh_face(mesh):
    """Mesh-local facing of the sign: the area-weighted normal of each material section; the red face is the section
    whose material isn't the back, the post or the galvanised parts. Returns {section material: [nx, ny, nz]}."""
    out = {}
    mats = [s.get_editor_property("material_interface") for s in mesh.get_editor_property("static_materials")]
    names = [s.get_editor_property("material_slot_name") for s in mesh.get_editor_property("static_materials")]
    n_sec = mesh.get_num_sections(0)
    for si in range(n_sec):
        try:
            r = unreal.ProceduralMeshLibrary.get_section_from_static_mesh(mesh, 0, si)
        except Exception as exc:  # noqa: BLE001
            res["log"].append("section %d: %s" % (si, exc))
            continue
        verts, tris = r[0], r[1]
        sx = sy = sz = 0.0
        for k in range(0, len(tris) - 2, 3):
            a, b, c = verts[tris[k]], verts[tris[k + 1]], verts[tris[k + 2]]
            ux, uy, uz = b.x - a.x, b.y - a.y, b.z - a.z
            vx, vy, vz = c.x - a.x, c.y - a.y, c.z - a.z
            sx += uy * vz - uz * vy
            sy += uz * vx - ux * vz
            sz += ux * vy - uy * vx
        L = math.sqrt(sx * sx + sy * sy + sz * sz) or 1.0
        # the material on this section
        mi = None
        try:
            mi = mesh.get_section_info(0, si) if hasattr(mesh, "get_section_info") else None
        except Exception:
            mi = None
        label = str(names[si]) if si < len(names) else "sec%d" % si
        out[label] = {"n": [round(sx / L, 3), round(sy / L, 3), round(sz / L, 3)], "tris": len(tris) // 3,
                      "area_vec_len": round(L, 1)}
    return out


def spots():
    comps = stop_components()
    res["stop_components"] = [(a.get_actor_label(), c.get_name(), c.get_instance_count()) for a, c, m in comps]
    faces = {}
    for a, c, m in comps:
        if m.get_name() not in faces:
            faces[m.get_name()] = mesh_face(m)
    res["stop_mesh_sections"] = faces
    q = []
    for sp in INP.get("spots", []):
        cx, cy = sp["car_ue"][0], sp["car_ue"][1]
        ty = math.radians(sp["travel_yaw"])
        tdir = (math.cos(ty), math.sin(ty))
        found = []
        for a, c, m in comps:
            for i in range(c.get_instance_count()):
                t = c.get_instance_transform(i, True)
                loc = t.translation
                d = math.hypot(loc.x - cx, loc.y - cy)
                if d > 4000:
                    continue
                yaw = t.rotation.rotator().yaw
                sec = faces[m.get_name()]
                # the face: the section whose local normal is most horizontal and not the "back" slot
                cand = [(k, v) for k, v in sec.items() if "back" not in k.lower() and abs(v["n"][2]) < 0.5
                        and math.hypot(v["n"][0], v["n"][1]) > 0.3]
                face = max(cand, key=lambda kv: kv[1]["area_vec_len"]) if cand else None
                fw = None
                if face:
                    n = face[1]["n"]
                    r = math.radians(yaw)
                    fw = (n[0] * math.cos(r) - n[1] * math.sin(r), n[0] * math.sin(r) + n[1] * math.cos(r))
                ahead = (loc.x - cx) * tdir[0] + (loc.y - cy) * tdir[1]
                found.append({"comp": c.get_name(), "i": i, "loc": [round(loc.x), round(loc.y), round(loc.z)],
                              "yaw": round(yaw, 1), "dist_m": round(d / 100.0, 1), "ahead_m": round(ahead / 100.0, 1),
                              "face_section": face[0] if face else None,
                              "face_world_dir": [round(fw[0], 3), round(fw[1], 3)] if fw else None,
                              "faces_approach": (fw[0] * tdir[0] + fw[1] * tdir[1]) < 0 if fw else None,
                              "face_vs_approach_deg": round(math.degrees(math.acos(max(-1, min(1, -(fw[0] * tdir[0] + fw[1] * tdir[1])))))) if fw else None})
        found.sort(key=lambda f: f["dist_m"])
        entry = dict(sp)
        entry["signs"] = found[:4]
        res["spots"].append(entry)
        for k, s in enumerate(found[:2]):
            for view, ang in (("front", 0.0), ("back", 180.0), ("left", 90.0), ("right", -90.0)):
                # the camera 6 m from the sign along the travel axis: "front" is where the approaching car sees it
                base = math.atan2(-tdir[1], -tdir[0]) + math.radians(ang)       # from the sign toward the camera
                cam = unreal.Vector(s["loc"][0] + math.cos(base) * 600, s["loc"][1] + math.sin(base) * 600,
                                    s["loc"][2] + 170)
                look = unreal.MathLibrary.find_look_at_rotation(cam, unreal.Vector(s["loc"][0], s["loc"][1],
                                                                                   s["loc"][2] + 200))
                name = "stop_%s_s%d_%s" % (os.path.basename(sp["v8_file"]).split(".")[0], k, view)
                q.append(("shot", {"name": name, "cam": cam, "rot": look, "spot": sp["v8_file"], "sign": s["loc"]}))
    return q


def poses():
    q = []
    for p in INP.get("poses", []):
        cam = unreal.Vector(*p["cam_ue"])
        q.append(("shot", {"name": "after_" + p["name"], "cam": cam, "rot": unreal.Rotator(0.0, p["pitch"], p["yaw"]),
                           "v8_file": p["v8_file"]}))
    return q


def tick(_dt):
    try:
        now = time.time()
        if S["q"] is None:
            if now - S["t0"] < SETTLE:
                return
            res["lights"] = light_check()
            cam = eas.spawn_actor_from_class(unreal.CameraActor, unreal.Vector(0, 0, 5000), unreal.Rotator(0, 0, 0))
            cam.camera_component.set_editor_property("field_of_view", 80.0)
            cam.camera_component.set_editor_property("constrain_aspect_ratio", False)
            S["cam"] = cam
            try:
                les.editor_set_game_view(True)
            except Exception:
                pass
            for c in ("r.MotionBlurQuality 0", "r.AntiAliasingMethod 1"):
                cmd(c)
            les.pilot_level_actor(cam)
            S["q"] = poses() + spots()
            write()
            return
        if not S["q"]:
            unreal.unregister_slate_post_tick_callback(builtins._lanep_revisit)
            try:
                les.eject_pilot_level_actor()
                eas.destroy_actor(S["cam"])          # never saved: the level isn't saved by this script
            except Exception:
                pass
            res["done"] = True
            write()
            S["quit_at"] = now + 2.0

            def later(_d):
                if time.time() > S["quit_at"]:
                    unreal.SystemLibrary.quit_editor()
            builtins._lanep_revisit_quit = unreal.register_slate_post_tick_callback(later)
            return
        kind, it = S["q"][0]
        st = S.setdefault("st", "set")
        if st == "set":
            S["cam"].set_actor_location_and_rotation(it["cam"], it["rot"], False, True)
            S["until"] = now + 3.0
            S["st"] = "wait"
            return
        if st == "wait":
            if now < S["until"]:
                return
            S["before"] = files()
            cmd("HighResShot %s" % RES)
            S["until"] = now + 15.0
            S["st"] = "file"
            return
        if st == "file":
            new = sorted(files() - S["before"])
            if not new and now < S["until"]:
                return
            rec = {k: v for k, v in it.items() if k not in ("cam", "rot")}
            rec["cam_ue"] = [round(it["cam"].x), round(it["cam"].y), round(it["cam"].z)]
            rec["cam_yaw"] = round(it["rot"].yaw, 1)
            rec["file"] = os.path.join(SHOTS, new[-1]) if new else None
            res["shots"].append(rec)
            S["q"].pop(0)
            S["st"] = "set"
            write()
    except Exception:
        res["error"] = traceback.format_exc()
        write()
        unreal.SystemLibrary.quit_editor()


builtins._lanep_revisit = unreal.register_slate_post_tick_callback(tick)
write()
