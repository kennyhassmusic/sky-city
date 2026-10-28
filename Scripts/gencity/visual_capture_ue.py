"""Fixed-camera capture for the visual check (Lane V, 2026-10-28). Runs INSIDE the Unreal editor, editor world (no
PIE), on an imported drive level; the build lane runs it under UNREAL.lock right after each import. Never saves the
level or any asset. Normally started by Scripts/gencity/run_visual_check.sh; by hand:

  VISUAL_OUT=<run dir> VISUAL_SPEC=<visual_cams.json> VISUAL_SEED=7 VISUAL_TAG=v10 GEN_BT=<bt worktree> \
  "$UE" "$PROJECT/SkyCity.uproject" /Game/Maps/GenCity_Seed7 -nosplash "$THROTTLE_OFF" -abslog=<log> \
    -ExecCmds="py <space-free path>/Scripts/gencity/visual_capture_ue.py"

(paths with spaces go in the environment: -ExecCmds splits on spaces.)

What it does, once the level has settled (render.settle_s):
  1. refuses to start when ~/UnrealProjects/_bt_mgmt/DISK_LOW exists or the internal disk has < 15 GB free;
  2. level dump -> <out>/level_dump.json: what level_dump_ue.py (lane P) writes (labels, classes, tags, meshes with
     instance counts and materials, mpc_wind) plus veg_xy (every vegetation instance's X/Y, for the
     vegetation-on-hard-surface rule), label_materials, bt_side_dir, and md5 of the watched asset packages
     (render.watch_assets, for --expect asset:<name>);
  3. fixes the look: an unbound PostProcessVolume (priority 10000) with motion blur and DoF off and exposure per
     render.exposure (auto_fast: histogram, fast adaptation, fixed bias; lock: min = max = ev100); wind frozen
     (MPC_Wind TimeScale 0, TimeOffset 0 on the world's collection instance);
  4. for every camera of this seed in the spec (VISUAL_CAMS=glob narrows it): pilots a CameraActor to loc_ue / yaw /
     pitch (FOV render.fov), waits per_shot_wait_s, HighResShot render.res, moves the PNG to <out>/shots/<cam>.png
     (and a second one, <cam>__b.png, when render.repeat_for_noise or VISUAL_REPEAT=1: the approval measures each
     camera's noise floor from the pair);
  5. writes <out>/capture.json (cameras, files, settings, project commit, flags) and quits the editor.
"""
import builtins
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import time
import traceback

import unreal

ROOT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()).rstrip("/")
ENV = os.environ
OUT = ENV.get("VISUAL_OUT") or os.path.join(ROOT, "Saved", "VisualCheck", "run_%s" % time.strftime("%Y%m%d-%H%M%S"))
SPEC = json.load(open(ENV.get("VISUAL_SPEC") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "visual_cams.json")))
SEED = str(ENV.get("VISUAL_SEED", "7"))
TAG = ENV.get("VISUAL_TAG", "run")
ONLY = ENV.get("VISUAL_CAMS", "*")
RENDER = SPEC["render"]
REPEAT = ENV.get("VISUAL_REPEAT", "1" if RENDER.get("repeat_for_noise") else "0") == "1"
MGMT = os.path.expanduser("~/UnrealProjects/_bt_mgmt")
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "MacEditor")
MIN_FREE_GB = 15.0

ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
os.makedirs(os.path.join(OUT, "shots"), exist_ok=True)
CAP = {"version": 1, "tag": TAG, "seed": int(SEED), "region": "seed%s_city" % SEED, "map": None,
       "res": RENDER["res"], "fov": RENDER["fov"], "render": RENDER, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
       "finished": None, "done": False, "cams": [], "log": [], "level_dump": "level_dump.json",
       "flags": (["pack"] if ENV.get("GEN_PACK") == "game" else []), "project": ROOT}
S = {"t0": time.time(), "q": None}


def write():
    CAP["secs"] = round(time.time() - S["t0"], 1)
    with open(os.path.join(OUT, "capture.json"), "w") as h:
        json.dump(CAP, h, indent=1, default=str)


def quit_soon(delay=2.0):
    S["quit_at"] = time.time() + delay

    def later(_d):
        if time.time() > S["quit_at"]:
            unreal.SystemLibrary.quit_editor()
    builtins._lanev_quit = unreal.register_slate_post_tick_callback(later)


def refuse(why):
    CAP["error"] = why
    write()
    unreal.log_error("visual capture refused: " + why)
    quit_soon()


def cmd(c):
    unreal.SystemLibrary.execute_console_command(ues.get_editor_world(), c)


def git_commit():
    try:
        return subprocess.check_output(["git", "-C", ROOT, "rev-parse", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------------------------------------------ level dump
VEG_WORDS = ("VEG_", "CROP_", "TREE", "Tree", "hedge", "Hedge", "SHRUB", "Shrub", "GRASS", "Grass", "FLOWER", "Weed",
             "WEED", "LeafLitter")
NOT_VEG = ("TreePit", "TreeGrate", "KIT_SS_TreeL", "KIT_SS_TreeS")


def is_veg(key):
    return not any(w in key for w in NOT_VEG) and any(w in key for w in VEG_WORDS)


def prefix(label):
    import re
    return re.sub(r"[_\d]+$", "", re.sub(r"_\d+(_\d+)*$", "", label))


def watched_assets(names):
    out = {}
    if not names:
        return out
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    flt = unreal.ARFilter(package_paths=["/Game"], recursive_paths=True)
    want = set(names)
    for ad in ar.get_assets(flt):
        n = str(ad.asset_name)
        if n not in want:
            continue
        pkg = str(ad.package_name)
        f = os.path.join(ROOT, "Content", pkg[len("/Game/"):] + ".uasset")
        if os.path.isfile(f):
            h = hashlib.md5()
            h.update(open(f, "rb").read())
            out[n] = h.hexdigest()
    return out


def level_dump():
    world = ues.get_editor_world()
    labels, meshes, classes, tags, lmats, veg = {}, {}, {}, {}, {}, {}
    for a in eas.get_all_level_actors():
        pre = prefix(a.get_actor_label())
        labels[pre] = labels.get(pre, 0) + 1
        c = a.get_class().get_name()
        classes[c] = classes.get(c, 0) + 1
        for t in a.get_editor_property("tags") or []:
            tags[str(t)] = tags.get(str(t), 0) + 1
        for comp in a.get_components_by_class(unreal.StaticMeshComponent):
            sm = comp.get_editor_property("static_mesh")
            if sm is None:
                continue
            key = sm.get_path_name().split(".")[-1]
            ism = isinstance(comp, unreal.InstancedStaticMeshComponent)
            n = comp.get_instance_count() if ism else 1
            rec = meshes.setdefault(key, {"instances": 0, "components": 0, "materials": set(), "actors": set()})
            rec["instances"] += n
            rec["components"] += 1
            rec["actors"].add(pre)
            for m in comp.get_materials():
                if m:
                    rec["materials"].add(m.get_name())
                    lmats.setdefault(pre, set()).add(m.get_name())
            if is_veg(key):
                pts = veg.setdefault(key, [])
                if ism:
                    for i in range(n):
                        t = comp.get_instance_transform(i, True).translation
                        pts.append([round(t.x), round(t.y)])
                else:
                    t = comp.get_world_location()
                    pts.append([round(t.x), round(t.y)])
    bt = ENV.get("GEN_BT")
    out = {"map": world.get_name(), "labels": labels, "classes": classes, "tags": tags,
           "meshes": {k: {"instances": v["instances"], "components": v["components"], "materials": sorted(v["materials"]),
                          "actors": sorted(v["actors"])[:5]} for k, v in meshes.items()},
           "mpc_wind": unreal.EditorAssetLibrary.does_asset_exist("/Game/CityGen/Wind/MPC_Wind"),
           "label_materials": {k: sorted(v) for k, v in lmats.items()},
           "veg_xy": veg, "veg_total": sum(len(v) for v in veg.values()),
           "bt_side_dir": os.path.join(bt, "Saved", "CityGen") if bt else None,
           "assets": watched_assets(RENDER.get("watch_assets") or [])}
    CAP["map"] = world.get_name()
    with open(os.path.join(OUT, "level_dump.json"), "w") as h:
        json.dump(out, h, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------------------------------- fixed look
def set_pp(ps, name, value):
    try:
        ps.set_editor_property("override_" + name, True)
    except Exception:  # noqa: BLE001
        pass
    try:
        ps.set_editor_property(name, value)
        return True
    except Exception as exc:  # noqa: BLE001
        CAP["log"].append("pp %s: %s" % (name, exc))
        return False


def fix_look():
    ppv = eas.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    ppv.set_actor_label("LaneV_VisualCheckPP")
    ppv.set_editor_property("unbound", True)
    ppv.set_editor_property("priority", 10000.0)
    ps = ppv.get_editor_property("settings")
    ex = RENDER.get("exposure") or {}
    set_pp(ps, "motion_blur_amount", 0.0)
    set_pp(ps, "depth_of_field_fstop", 32.0)
    set_pp(ps, "auto_exposure_bias", float(ex.get("bias") or 0.0))
    if ex.get("mode") == "lock" and ex.get("ev100") is not None:
        set_pp(ps, "auto_exposure_method", unreal.AutoExposureMethod.AEM_HISTOGRAM)
        set_pp(ps, "auto_exposure_min_brightness", float(ex["ev100"]))
        set_pp(ps, "auto_exposure_max_brightness", float(ex["ev100"]))
    else:
        set_pp(ps, "auto_exposure_method", unreal.AutoExposureMethod.AEM_HISTOGRAM)
    set_pp(ps, "auto_exposure_speed_up", 20.0)
    set_pp(ps, "auto_exposure_speed_down", 20.0)
    ppv.set_editor_property("settings", ps)
    S["ppv"] = ppv
    fw = RENDER.get("freeze_wind") or {}
    if fw.get("mpc"):
        mpc = unreal.EditorAssetLibrary.load_asset(fw["mpc"]) if unreal.EditorAssetLibrary.does_asset_exist(fw["mpc"]) else None
        if mpc is None:
            CAP["log"].append("no %s: wind not frozen" % fw["mpc"])
        else:
            for k, v in fw.items():
                if k != "mpc":
                    try:
                        unreal.MaterialLibrary.set_scalar_parameter_value(ues.get_editor_world(), mpc, k, float(v))
                    except Exception as exc:  # noqa: BLE001
                        CAP["log"].append("wind %s: %s" % (k, exc))
    for c in RENDER.get("console") or []:
        cmd(c)


def files():
    return set(os.listdir(SHOTS)) if os.path.isdir(SHOTS) else set()


def queue():
    q = []
    for c in SPEC["cameras"]:
        if str(c["seed"]) != SEED or not fnmatch.fnmatchcase(c["name"], ONLY):
            continue
        q.append((c, ""))
        if REPEAT:
            q.append((c, "__b"))
    return q


def tick(_dt):
    try:
        now = time.time()
        if S["q"] is None:
            if now - S["t0"] < float(RENDER.get("settle_s", 45)):
                return
            level_dump()
            fix_look()
            cam = eas.spawn_actor_from_class(unreal.CameraActor, unreal.Vector(0, 0, 5000), unreal.Rotator(0, 0, 0))
            cam.set_actor_label("LaneV_VisualCheckCam")
            cam.camera_component.set_editor_property("field_of_view", float(RENDER["fov"]))
            cam.camera_component.set_editor_property("constrain_aspect_ratio", False)
            S["cam"] = cam
            try:
                les.editor_set_game_view(True)
            except Exception:  # noqa: BLE001
                pass
            les.pilot_level_actor(cam)
            S["q"] = queue()
            CAP["commit"] = git_commit()
            write()
            return
        if not S["q"]:
            unreal.unregister_slate_post_tick_callback(builtins._lanev_tick)
            try:
                les.eject_pilot_level_actor()
                eas.destroy_actor(S["cam"])
                eas.destroy_actor(S["ppv"])
            except Exception:  # noqa: BLE001
                pass
            CAP["done"] = True
            CAP["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            write()
            quit_soon()
            return
        c, suffix = S["q"][0]
        st = S.setdefault("st", "set")
        if st == "set":
            loc = unreal.Vector(*[float(v) for v in c["loc_ue"]])
            S["cam"].set_actor_location_and_rotation(loc, unreal.Rotator(0.0, float(c["pitch"]), float(c["yaw"])), False, True)
            S["until"] = now + float(RENDER.get("per_shot_wait_s", 4.0))
            S["st"] = "wait"
            return
        if st == "wait":
            if now < S["until"]:
                return
            S["before"] = files()
            cmd("HighResShot %s" % RENDER["res"])
            S["until"] = now + 20.0
            S["st"] = "file"
            return
        if st == "file":
            new = sorted(f for f in files() - S["before"] if f.lower().endswith(".png"))
            if not new and now < S["until"]:
                return
            if new:                                     # let the PNG finish writing (1 s)
                if "grace" not in S:
                    S["grace"] = now + 1.0
                if now < S["grace"]:
                    return
            S.pop("grace", None)
            rel = "shots/%s%s.png" % (c["name"], suffix)
            rec = next((r for r in CAP["cams"] if r["name"] == c["name"]), None)
            if rec is None:
                rec = {"name": c["name"], "loc_ue": c["loc_ue"], "yaw": c["yaw"], "pitch": c["pitch"], "file": None}
                CAP["cams"].append(rec)
            if new:
                shutil.move(os.path.join(SHOTS, new[-1]), os.path.join(OUT, rel))
                rec["file_b" if suffix else "file"] = rel
            else:
                rec["error"] = "HighResShot wrote no file in 20 s"
            S["q"].pop(0)
            S["st"] = "set"
            write()
    except Exception:  # noqa: BLE001
        CAP["error"] = traceback.format_exc()
        write()
        unreal.SystemLibrary.quit_editor()


if os.path.exists(os.path.join(MGMT, "DISK_LOW")):
    refuse("~/UnrealProjects/_bt_mgmt/DISK_LOW is there (internal disk under 20 GB): not capturing")
elif shutil.disk_usage("/System/Volumes/Data").free / 1e9 < MIN_FREE_GB:
    refuse("internal disk has %.1f GB free (< %.0f): not capturing" % (shutil.disk_usage("/System/Volumes/Data").free / 1e9, MIN_FREE_GB))
else:
    builtins._lanev_tick = unreal.register_slate_post_tick_callback(tick)
    write()
