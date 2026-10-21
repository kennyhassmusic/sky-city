# Sky City, district 1 ("Congress & Wacker"): the fixed pieces of the blockout.
# PCG fills the city blocks; this script lays what PCG builds around: ground, river, lake,
# bridges, the L deck and ramps, the Capitol hill jump, wall-ride towers and two landmark towers.
# Run in the editor: py Scripts/district1_layout.py
# Re-running deletes and rebuilds everything tagged D1_Layout.
#
# Units below are metres. World axes: +X north, +Y east, +Z up; street level is Z = 0.
# Street grid: centre lines every 120 m on both axes, 24 m wide, so blocks are 96 m squares
# centred on (120k + 60, 120j + 60).
import json, traceback
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


OUT = os.path.join(_skycity_root(), "Saved", "MCPScripts", "out.json")
TAG = "D1_Layout"
EXCLUDE = "PCG_Exclude"   # PCG removes building lots under anything with this tag
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EAL = unreal.EditorAssetLibrary
M = lambda n: EAL.load_asset(f"/Game/Blockout/Materials/{n}")
BOX = EAL.load_asset("/Game/Blockout/Meshes/SM_BlockBox")
RAMP = EAL.load_asset("/Game/Blockout/Meshes/SM_Ramp")
TOWER = EAL.load_asset("/Game/Blockout/Meshes/SM_WallRideTower")
CYL = EAL.load_asset("/Engine/BasicShapes/Cylinder")
SPHERE = EAL.load_asset("/Engine/BasicShapes/Sphere")
out = {"placed": 0}

RIVER_HALF = 60          # river is X -60..60
BRANCH = (-790, -730)    # north branch, Y range
WATER_Z, FLOOR_Z = -6.0, -8.0
L_Z = 9.0                # L deck top
L_X, L_Y = (240, 720), (-480, 480)   # L ring centre lines (street lines)


def spawn(mesh, label, folder, loc, scale, yaw=0.0, mat=None, collide=True, tags=()):
    a = EAS.spawn_actor_from_object(mesh, unreal.Vector(loc[0] * 100, loc[1] * 100, loc[2] * 100),
                                    unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.set_actor_scale3d(unreal.Vector(*scale))
    a.set_actor_label(label)
    a.set_folder_path(f"District1/{folder}")
    a.set_editor_property("tags", [unreal.Name(TAG)] + [unreal.Name(t) for t in tags])
    smc = a.static_mesh_component
    if mat:
        smc.set_material(0, mat)
    if not collide:
        smc.set_collision_profile_name("NoCollision")
    out["placed"] += 1
    return a


def box(label, folder, x0, x1, y0, y1, z0, z1, mat, **kw):
    """Axis-aligned box from metre extents (SM_BlockBox is 1 m with its pivot on the bottom)."""
    return spawn(BOX, label, folder, ((x0 + x1) / 2, (y0 + y1) / 2, z0), (x1 - x0, y1 - y0, z1 - z0), mat=mat, **kw)


def ramp(label, folder, x_low, x_high, y, width, z0, rise, mat, **kw):
    """Wedge rising from x_low to x_high (either direction along X)."""
    yaw = 0.0 if x_high > x_low else 180.0
    return spawn(RAMP, label, folder, ((x_low + x_high) / 2, y, z0), (abs(x_high - x_low), width, rise), yaw=yaw, mat=mat, **kw)


def cyl(label, folder, x, y, z0, radius, height, mat, **kw):
    return spawn(CYL, label, folder, (x, y, z0 + height / 2), (radius * 2, radius * 2, height), mat=mat, **kw)


try:
    old = [a for a in EAS.get_all_level_actors() if unreal.Name(TAG) in a.tags]
    if old:
        EAS.destroy_actors(old)
    out["removed"] = len(old)
    asphalt, sidewalk, water, park = M("M_BO_Asphalt"), M("M_BO_Sidewalk"), M("M_BO_Water"), M("M_BO_Park")
    steel, accent, granite, dome, glass = M("M_BO_LSteel"), M("M_BO_Accent"), M("M_BO_Granite"), M("M_BO_Dome"), M("M_BO_Glass")

    # ground: 8 m deep slabs so the river and lake sit in real channels
    box("Ground_NorthWest", "Ground", RIVER_HALF, 1600, -1000, BRANCH[0], FLOOR_Z, 0, asphalt)
    box("Ground_NorthEast", "Ground", RIVER_HALF, 1600, BRANCH[1], 1000, FLOOR_Z, 0, asphalt)
    box("Ground_South", "Ground", -800, -RIVER_HALF, -1000, 1000, FLOOR_Z, 0, asphalt)
    box("Riverbed", "Water", -RIVER_HALF, RIVER_HALF, -1000, 1000, FLOOR_Z - 2, FLOOR_Z, sidewalk)
    box("Riverbed_NorthBranch", "Water", RIVER_HALF, 1600, BRANCH[0], BRANCH[1], FLOOR_Z - 2, FLOOR_Z, sidewalk)
    box("Lakebed", "Water", -800, 1600, 1000, 2600, FLOOR_Z - 2, FLOOR_Z, sidewalk)
    box("Water_River", "Water", -RIVER_HALF, RIVER_HALF, -1000, 1000, WATER_Z - 0.2, WATER_Z, water, collide=False)
    box("Water_NorthBranch", "Water", RIVER_HALF, 1600, BRANCH[0], BRANCH[1], WATER_Z - 0.2, WATER_Z, water, collide=False)
    box("Water_Lake", "Water", -800, 1600, 1000, 2600, WATER_Z - 0.2, WATER_Z, water, collide=False)
    # Chicago Riverwalk: a ledge 4 m below the street along the north bank
    box("Riverwalk", "Water", RIVER_HALF - 12, RIVER_HALF, -1000, 1000, FLOOR_Z, -4, sidewalk)
    # Lady Bird Lake shoreline park along the south bank
    box("Park_Shoreline", "Parks", -130, -RIVER_HALF, -1000, 1000, 0, 0.05, park)

    # bridges on the street lines
    for y in (-480, -240, 240, 480):
        box(f"Bridge_River_Y{y}", "Bridges", -RIVER_HALF - 2, RIVER_HALF + 2, y - 12, y + 12, -1.5, 0, steel)
    box("Bridge_Congress", "Bridges", -RIVER_HALF - 2, RIVER_HALF + 2, -14, 14, -1.5, 0, accent)
    for x in (240, 600, 960):
        box(f"Bridge_Branch_X{x}", "Bridges", x - 12, x + 12, BRANCH[0] - 2, BRANCH[1] + 2, -1.5, 0, steel)

    # Congress Avenue and Lake Shore Drive centre stripes
    box("Congress_Stripe", "Roads", -800, 900, -0.6, 0.6, 0, 0.03, accent, collide=False)
    box("LakeShore_Stripe", "Roads", -800, 1600, 979.4, 980.6, 0, 0.03, accent, collide=False)

    # the L: 12 m deck, top at 9 m, over the street lines; PCG adds the columns
    x0, x1 = L_X; y0, y1 = L_Y; h = 6
    box("L_Deck_South", "TheL", x0 - h, x0 + h, y0 - h, y1 + h, L_Z - 1.2, L_Z, steel)
    box("L_Deck_North", "TheL", x1 - h, x1 + h, y0 - h, y1 + h, L_Z - 1.2, L_Z, steel)
    box("L_Deck_West", "TheL", x0 - h, x1 + h, y0 - h, y0 + h, L_Z - 1.2, L_Z, steel)
    box("L_Deck_East", "TheL", x0 - h, x1 + h, y1 - h, y1 + h, L_Z - 1.2, L_Z, steel)
    ramp("L_Ramp_SouthWest", "TheL", x0 - h - 64, x0 - h, y0, 12, 0, L_Z, accent)
    ramp("L_Ramp_NorthEast", "TheL", x1 + h + 64, x1 + h, y1, 12, 0, L_Z, accent)

    # Capitol hill jump: Congress climbs to a 12 m plaza, a kicker launches north over a landing slope
    ramp("Capitol_Climb", "Capitol", 900, 1000, 0, 24, 0, 12, accent)
    box("Capitol_Plaza", "Capitol", 1000, 1100, -60, 60, 0, 12, granite)
    ramp("Capitol_Kicker", "Capitol", 1080, 1100, 0, 24, 12, 4, accent)
    ramp("Capitol_Landing", "Capitol", 1220, 1100, 0, 120, 0, 12, granite)
    box("Capitol_Lawn", "Parks", 1100, 1600, -300, 300, 0, 0.05, park)
    box("Capitol_Base", "Capitol", 1360, 1480, -110, 110, 0, 28, granite)
    box("Capitol_Wings", "Capitol", 1385, 1455, -200, 200, 0, 22, granite)
    cyl("Capitol_Drum", "Capitol", 1420, 0, 28, 22, 30, granite)
    spawn(SPHERE, "Capitol_Dome", "Capitol", (1420, 0, 58), (44, 44, 44), mat=dome)
    cyl("Capitol_Lantern", "Capitol", 1420, 0, 78, 4, 14, dome)

    # wall-ride towers rising from the shoreline park, clear of the bridge landings
    for y in (-360, 360, 720):
        spawn(TOWER, f"WallRideTower_Y{y}", "CarFeatures", (-95, y, 0), (1, 1, 1))

    # landmarks: a Willis-style bundled tube in the Loop, an Independent-style "Jenga" tower in Austin
    tube = 23.0
    heights = [[290, 368, 200], [442, 442, 368], [200, 290, 290]]
    cx, cy = 420, -300
    for i in range(3):
        for j in range(3):
            x = cx + (i - 1) * tube; y = cy + (j - 1) * tube
            box(f"Landmark_Willis_{i}{j}", "Landmarks", x - tube / 2, x + tube / 2, y - tube / 2, y + tube / 2, 0,
                heights[i][j], glass, tags=(EXCLUDE,))
    jx, jy = -180, 60
    for k, (dx, dy) in enumerate([(0, 0), (4, -3), (-3, 4), (5, 2), (-4, -4), (2, 5)]):
        box(f"Landmark_Jenga_{k}", "Landmarks", jx - 19 + dx, jx + 19 + dx, jy - 19 + dy, jy + 19 + dy,
            k * 35, (k + 1) * 35, glass, tags=(EXCLUDE,))

    # start on South Congress facing north, toward the bridge and the Loop
    start = unreal.Vector(-400 * 100, -6 * 100, 100)
    for a in EAS.get_all_level_actors():
        if a.get_class().get_name() == "PlayerStart":
            a.set_actor_location_and_rotation(start, unreal.Rotator(roll=0, pitch=0, yaw=0), False, False)
        if a.get_name().startswith("roadster_master_scene"):
            a.set_actor_location_and_rotation(unreal.Vector(-380 * 100, -6 * 100, 0), unreal.Rotator(roll=0, pitch=0, yaw=-90), False, False)

    out["save_dirty"] = unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    out["ok"] = True
except Exception:
    out["error"] = traceback.format_exc()

open(OUT, "w").write(json.dumps(out, indent=1))
