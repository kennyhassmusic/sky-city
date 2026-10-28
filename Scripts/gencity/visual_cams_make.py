"""Writes visual_cams.json (Lane V): the fixed cameras and their sources, the render settings and the level rules.
  python3 -I Scripts/gencity/visual_cams_make.py
Poses come from lane P's revisit/inspection runs and the seed-7/17 side files (see each camera's source)."""
import json, math
def ue(px, py, z): return [round(py*100.0,1), round(px*100.0,1), z]
def yaw_plan(dx, dy): return round(math.degrees(math.atan2(dx, dy)), 1)
def orbit(target, dist_m, elev, yaw):
    r = math.radians(yaw); e = math.radians(elev)
    h = dist_m*100*math.cos(e)
    return [round(target[0]-h*math.cos(r)), round(target[1]-h*math.sin(r)), round(dist_m*100*math.sin(e))]
C = []
def cam(seed, name, loc, yaw, pitch, src, tags=(), **kw):
    d = {"name": name, "seed": seed, "loc_ue": [round(v,1) for v in loc], "yaw": yaw, "pitch": pitch,
         "source": src, "tags": list(tags)}
    d.update(kw); C.append(d)
R = "revisit_in_v10_last.json (lane P v10 pairs/beach shots)"
cam(7, "curved_bend", [15863.0, 82395.9, 120], 28.1, -3.0, R, ["roads", "curb"])
cam(7, "downtown_corner", [68100, 71100, 170], 45.0, -4.0, R, ["downtown", "curb", "paint"])
cam(7, "empty_lot", [54048.7, 40005.9, 170], -88.3, -6.0, R + " parcel p_a90dca4b_b0101", ["vacant", "veg"])
cam(7, "driveway", [37775.0, 58348.2, 170], -170.4, -6.0, R + " parcel p_72729686_a0204", ["suburbs", "curb"])
cam(7, "veg_spot", [68388.7, 124416.5, 170], 45.0, -12.0, R + " (Kenny's plants-in-road spot)", ["veg", "roads"],
    ssim_tol=0.05, frac_tol=0.03)
# STOP approach: inspect_v9 stop_corners suburbs/0011_fwd, car_ue 45202,104389, travel yaw 0.6; camera 12 m back
ty = math.radians(0.6)
cam(7, "stop_approach", [45202 - 1200*math.cos(ty), 104389 - 1200*math.sin(ty), 130], 0.6, -3.0,
    "inspect_v9 stop_corners suburbs/0011_fwd (edge r_loc_005), 12 m before the corner", ["signs", "paint"])
# skewed junction n_plat_55ab26ab1_x1_1_1_b at plan (1261.8, 1211.5): legs 180, -4, 40, -140 deg (plan)
cam(7, "skewed_junction_eye", ue(1238, 1212.5, 150), yaw_plan(1, 0), -4.0,
    "placed_city node n_plat_55ab26ab1_x1_1_1_b (most skewed 4-way, IN_UNREAL_CHECKLIST_v10 note), on the west local leg",
    ["roads", "paint", "curb"])
cam(7, "skewed_junction_air", ue(1261.8, 1186.5, 3500), 0.0, -55.0,
    "same node, 35 m up, 25 m south, looking north", ["roads", "paint", "curb", "aerial"])
cam(7, "bridge_deck", ue(345, 268, 150), yaw_plan(1, 0), -3.0,
    "bridges_seed7 br_r_art_027 (deck plan y 270, x 361-423), 16 m before the west abutment", ["bridge", "paint"])
cam(7, "bridge_side", ue(380, 650, 250), 0.0, -2.0,
    "bridges_seed7 br_r_art_034 from the south bank (girders, piers, parapets, water)", ["bridge", "water"],
    ssim_tol=0.05, frac_tol=0.03)
cam(7, "civic_river_bridge", [90170, 41052, 120], -90.0, -3.0,
    "inspect_v9 civic_river/0081_fwd (bridge r_col_061)", ["bridge", "water"])
cam(7, "beach_eye", [-9500, 33000, 120.0], 168.7, -3.0, R, ["beach", "shore"], roi=[0.0, 0.45, 1.0, 1.0])
cam(7, "beach_dunes", [-4500, 42000, 380.0], 98.5, -6.0, R, ["beach", "shore", "veg"], ssim_tol=0.05, frac_tol=0.03)
cam(7, "beach_carpark", [800, 31800, 300.0], -154.7, -12.0, R, ["beach", "shore", "parking"])
cam(7, "beach_air", [-42000, 70000, 14000], 0.0, -28.0, R, ["beach", "shore", "aerial", "water"])
cam(7, "county_ditch", ue(302, 1250, 150), 0.0, -4.0,
    "ditches_seed7 strips on r_art_006 (both sides, plan x 288-312, y 1203-1500), looking north", ["county", "ditch"])
cam(7, "farm_belt", [21750.0, 129200.0, 170], 90.0, -3.0,
    "plan_seed7_city shot 'farmland' (corn field f_11c2596b_a0102_01)", ["farm", "veg", "county"],
    ssim_tol=0.05, frac_tol=0.03)
cam(7, "downtown_street", [48000.0, 85650.0, 170], 90.0, -3.0, "plan_seed7_city shot 'downtown' (r_col_044)", ["downtown"])
cam(7, "suburbs_street", [140925.0, 122650.0, 170], 180.0, -3.0, "plan_seed7_city shot 'suburbs'", ["suburbs", "veg"])
cam(7, "industrial_street", [111000.0, 57300.0, 170], 90.0, -3.0, "plan_seed7_city shot 'industrial'", ["industrial", "pack"])
cam(7, "civic_street", [103642.3, 92664.7, 170], 2.6, -3.0, "plan_seed7_city shot 'civic'", ["civic"])
cam(7, "crosswalk_ramp", ue(285, 200, 170), yaw_plan(15, -5.3), -12.0,
    "props_seed7 crosswalk at n_ix_x02 (ends plan (292,194.7)-(308,194.7)), pedestrian on the corner", ["curb", "paint", "ada"])
t = [37500.0, 72000.0]
cam(7, "aerial_city", orbit(t, 450, 40, 0.0), 0.0, -40.0, "plan_seed7_city shot 'aerial' (450 m, 40 deg)", ["aerial"])
cam(7, "aerial_downtown", [39000, 72000, 30000], 0.0, -45.0, "over the Core district (plan 457-982, 427-952)", ["aerial", "downtown"])
cam(7, "aerial_north_farms", [100000, 75000, 35000], 0.0, -45.0, "over North Fields, looking north", ["aerial", "farm"])
cam(7, "aerial_river", [75000, 80000, 35000], -90.0, -40.0, "over the river Longcut from the east, looking west", ["aerial", "water", "bridge"])
# seed 17 subset
cam(17, "s17_garage_entry", [101950, 65480, 300], 180.0, -10.0,
    "plan_seed17_city ramp start_ue 101350,65480 (lot g_p_30d1a2fd_a0100_lot0), 6 m behind", ["garage"])
cam(17, "s17_garage_ramp", [98930, 65900, 200], 90.0, 4.0, "plan_seed17_city ramp first plate 98930,66080, looking up the ramp", ["garage"])
cam(17, "s17_downtown", [69100.0, 89170.0, 170], 90.0, -3.0, "plan_seed17_city shot 'downtown'", ["downtown"])
cam(17, "s17_farmland", [80000.0, 132190.0, 170], 90.0, -3.0, "plan_seed17_city shot 'farmland'", ["farm", "veg"], ssim_tol=0.05, frac_tol=0.03)
cam(17, "s17_aerial", orbit([37500.0, 31400.0], 450, 40, 0.0), 0.0, -40.0, "plan_seed17_city shot 'aerial'", ["aerial"])
spec = {
 "version": 1,
 "about": "Lane V fixed-camera golden-image check. UE centimetres, yaw/pitch degrees (UE: yaw 0 = +X = plan north). Edit cameras here; re-approve goldens after moving one.",
 "levels": {"7": "/Game/Maps/GenCity_Seed7", "17": "/Game/Maps/GenCity_Seed17"},
 "render": {"res": "1280x720", "fov": 80.0, "settle_s": 45, "per_shot_wait_s": 4.0, "repeat_for_noise": False,
            "console": ["r.MotionBlurQuality 0", "r.AntiAliasingMethod 1", "r.DepthOfFieldQuality 0"],
            "watch_assets": ["M_Shore_Sand", "MI_Shore_Sea", "MI_KitRoad_asphalt", "MI_L9_Water", "M_L9_Water"],
            "freeze_wind": {"mpc": "/Game/CityGen/Wind/MPC_Wind", "TimeScale": 0.0, "TimeOffset": 0.0},
            "exposure": {"mode": "auto_fast", "ev100": None, "bias": 0.0,
                         "note": "auto_fast: histogram AE converging in <1 s with a fixed bias; set mode lock + ev100 to pin it"}},
 "thresholds": {"ssim_tol": 0.03, "frac_tol": 0.015, "pix_delta": 0.10, "color_tol": 0.02, "work_width": 640, "noise_mult": 3.0,
                "blank_mean": 0.03, "blank_std": 0.01},
 "rules": [
  {"id": "veg_on_hard", "kind": "veg_on_hard", "max": 0,
   "why": "Kenny 2026-10-28: ~4,000 plants on roads and sidewalks (v9 side files 3,981 on hard surface)"},
  {"id": "road_tiles", "kind": "count_min", "key": "labels.F8_Road", "min": 1},
  {"id": "road_asphalt", "kind": "material_on", "actor": "F8_Road", "material": "MI_KitRoad_asphalt"},
  {"id": "curbs", "kind": "count_min", "key": "labels.F7_curb", "min": 1},
  {"id": "walks", "kind": "count_min", "key": "labels.F7_walk", "min": 1},
  {"id": "parkway", "kind": "count_min", "key": "labels.F7_parkway", "min": 1},
  {"id": "ada_warning", "kind": "count_min", "key": "labels.F7_warning", "min": 1},
  {"id": "ditch_slabs", "kind": "count_min", "key": "meshes.KIT_SS_SlabWedge", "min": 1, "seeds": [7]},
  {"id": "ground_cut", "kind": "count_min", "key": "labels.L9_GroundCut", "min": 1},
  {"id": "wear_decals", "kind": "count_min", "key": "meshes.KIT_DecalFloor", "min": 1},
  {"id": "paint_bars", "kind": "count_min", "key": "meshes.KIT_SS_PaintBar", "min": 1},
  {"id": "vacant_fences", "kind": "count_min", "key": "meshes.KIT_FS_Post*", "min": 1},
  {"id": "crack_weeds", "kind": "count_min", "key": "meshes.SM_VEG_CrackWeed*", "min": 1},
  {"id": "shore_terrain", "kind": "count_min", "key": "labels.Shore_Terrain", "min": 1, "seeds": [7]},
  {"id": "shore_sand_material", "kind": "material_on", "actor": "Shore_Terrain", "material": "M_Shore_Sand", "seeds": [7]},
  {"id": "shore_sea", "kind": "count_min", "key": "labels.Shore_Sea", "min": 1, "seeds": [7]},
  {"id": "dune_grass", "kind": "count_min", "key": "meshes.SM_VEG_DuneGrass*", "min": 1, "seeds": [7]},
  {"id": "pebbles_shells", "kind": "count_min_each", "keys": ["meshes.SM_Shore_Pebble", "meshes.SM_Shore_Shell"], "min": 1, "seeds": [7]},
  {"id": "bridges", "kind": "count_min", "key": "tags.BX_Bridge", "min": 1},
  {"id": "river", "kind": "count_min", "key": "labels.L9_River*", "min": 1},
  {"id": "wind_flags", "kind": "count_min", "key": "labels.Wind_Flags", "min": 1},
  {"id": "wind_mpc", "kind": "truthy", "key": "mpc_wind"},
  {"id": "signal_masts", "kind": "count_min", "key": "meshes.KIT_SS_SignalMast*", "min": 1},
  {"id": "street_props", "kind": "count_min_each",
   "keys": ["meshes.KIT_SS_Hydrant", "meshes.KIT_SS_StopSign", "meshes.KIT_SS_CarSedan", "meshes.KIT_SS_StreetLight", "meshes.KIT_SS_Bench"], "min": 1},
  {"id": "crops", "kind": "count_min", "key": "meshes.SM_CROP_*", "min": 1},
  {"id": "kit_walls", "kind": "count_min", "key": "meshes.KIT_Wall", "min": 1},
  {"id": "game_pack", "kind": "count_min", "key": "meshes.SM_UP_*", "min": 1, "seeds": [7], "optional_flag": "pack"},
  {"id": "lights", "kind": "count_eq_golden", "key": "classes.DirectionalLight",
   "why": "one Sun + ShadeFill; a second sun or a lost fill changes every shot"},
  {"id": "no_big_drop", "kind": "no_big_drop", "max_drop": 0.5,
   "why": "any tracked mesh/label count falling by more than half against the golden level dump"}
 ],
 "cameras": C,
}
import os
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "visual_cams.json")
json.dump(spec, open(out, "w"), indent=1)
print(len(C), sum(1 for c in C if c["seed"] == 7), sum(1 for c in C if c["seed"] == 17))
