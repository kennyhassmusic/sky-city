"""Build Sky City's base geometry in Unreal from the integrated plan (Saved/Mashup/plan_v3.json).

Run inside the editor, one stage at a time (each stage saves its own assets):
    py Scripts/unreal/build_city.py map
    py .../build_city.py ground      # land slab with rivers, canal and lake cut 8 m deep, riverbed, water surface
    py .../build_city.py overlays    # parks and beach
    py .../build_city.py roads       # every street as a solid ribbon; bridges where they cross water
    py .../build_city.py elevated    # elevated expressways on pillars, the L deck on pillars
    py .../build_city.py landmarks   # stand-ins: Willis, Capitol, the Bean, Buckingham Fountain, Navy Pier wheel
Results go to Saved/MCPScripts/out.json.

Frames: the plan is metres with x east, y north. Unreal gets X = north, Y = east (centimetres), Z up, so north is
the editor's forward axis and east is to the right, like the earlier blockout.
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
PLAN = json.load(open(ROOT + "/Saved/Mashup/plan_v3.json"))
OUT = ROOT + "/Saved/MCPScripts/out.json"
MAP = "/Game/Maps/SkyCityMashup"
MESH_DIR = "/Game/City/Meshes"
MAT_DIR = "/Game/Blockout/Materials"
P = unreal.GeometryScript_Primitives
EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
OPT = unreal.GeometryScriptPrimitiveOptions()
TAG = "City_Generated"

WATER_Z, BED_Z, GROUND_THICK = -550.0, -800.0, 1000.0
ROAD = {  # width (cm), top above ground (cm)
    "ped": (350, 3), "minor": (900, 4), "mid": (1200, 5), "major": (1600, 6), "highway": (2400, 7),
}
ELEV_Z, ELEV_RAMP = 900.0, 15000.0     # elevated expressway deck height and ramp length (cm)
L_Z, L_W = 750.0, 900.0                # the L deck
out = {"stage": None}


def ue(p):
    return (p[1] * 100.0, p[0] * 100.0)


def v2(p):
    return unreal.Vector2D(p[0], p[1])


def ring_ue(ring):
    pts = [ue(p) for p in ring]
    if len(pts) > 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    return pts if area > 0 else pts[::-1]      # counter-clockwise in Unreal's XY so faces point up


def mat(name):
    return EAL.load_asset(f"{MAT_DIR}/{name}")


def ensure_material(name, rgb, rough=0.8):
    path = f"{MAT_DIR}/{name}"
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path)
    MEL = unreal.MaterialEditingLibrary
    m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    c = MEL.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -300, 0)
    c.set_editor_property("constant", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1))
    MEL.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    r = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, -300, 150)
    r.set_editor_property("r", rough)
    MEL.connect_material_property(r, "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def save_mesh(dm, name, material, collide=True):
    path = f"{MESH_DIR}/{name}"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
    for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", True), ("enable_nanite", False),
                 ("enable_collision", collide)):
        try:
            opts.set_editor_property(k, v)
        except Exception:
            pass
    res = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, opts)
    sm = res[0] if isinstance(res, (tuple, list)) else res
    bs = sm.get_editor_property("body_setup")
    if bs:
        bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if collide
                               else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
    sm.set_material(0, material)
    EAL.save_loaded_asset(sm)
    return sm


def place(sm, label, folder, collide=True):
    for a in EAS.get_all_level_actors():
        if a.get_actor_label() == label and unreal.Name(TAG) in a.tags:
            EAS.destroy_actor(a)
    a = EAS.spawn_actor_from_object(sm, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    a.set_actor_label(label)
    a.set_folder_path(f"City/{folder}")
    a.set_editor_property("tags", [unreal.Name(TAG)])
    if not collide:
        a.static_mesh_component.set_collision_profile_name("NoCollision")
    return a


def tris_count(dm):
    try:
        return unreal.GeometryScript_MeshQueries.get_num_triangle_ids(dm)
    except Exception:
        return -1


# ---- stages -----------------------------------------------------------------------------------------
def stage_map():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not EAL.does_asset_exist(MAP):
        out["new_level"] = les.new_level_from_template(MAP, "/Engine/Maps/Templates/OpenWorld")
    elif unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name().split(".")[0] != MAP:
        les.load_level(MAP)
    land = [a for a in EAS.get_all_level_actors() if a.get_class().get_name() in ("Landscape", "LandscapeStreamingProxy")]
    if land:
        EAS.destroy_actors(land)
    out["landscape_removed"] = len(land)
    out["saved"] = les.save_current_level()
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)


def stage_ground():
    x0, y0, x1, y1 = PLAN["bounds"]
    X0, X1, Y0, Y1 = y0 * 100, y1 * 100, x0 * 100, x1 * 100
    cx, cy = (X0 + X1) / 2, (Y0 + Y1) / 2
    land = unreal.DynamicMesh()
    P.append_box(land, OPT, unreal.Transform(unreal.Vector(cx, cy, -GROUND_THICK), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                 X1 - X0, Y1 - Y0, GROUND_THICK, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
    cut = unreal.DynamicMesh()
    n = 0
    for ring in PLAN["water"]["outer"]:
        pts = ring_ue(ring)
        if len(pts) < 3:
            continue
        P.append_simple_extrude_polygon(cut, OPT, unreal.Transform(unreal.Vector(0, 0, -GROUND_THICK - 500), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                        [v2(p) for p in pts], GROUND_THICK + 1500, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        n += 1
    bopt = unreal.GeometryScriptMeshBooleanOptions()
    try:
        unreal.GeometryScript_MeshBooleans.apply_mesh_self_union(cut, unreal.GeometryScriptMeshSelfUnionOptions())
    except Exception as e:
        out["self_union_error"] = str(e)
    I = unreal.Transform()
    unreal.GeometryScript_MeshBooleans.apply_mesh_boolean(land, I, cut, I, unreal.GeometryScriptBooleanOperation.SUBTRACT, bopt)
    # islands (Goose Island and friends) go back in as land
    isl = unreal.DynamicMesh()
    for ring in PLAN["water"]["inner"]:
        pts = ring_ue(ring)
        if len(pts) >= 3:
            P.append_simple_extrude_polygon(isl, OPT, unreal.Transform(unreal.Vector(0, 0, -GROUND_THICK), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                            [v2(p) for p in pts], GROUND_THICK, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
    if tris_count(isl) > 0:
        unreal.GeometryScript_MeshBooleans.apply_mesh_boolean(land, I, isl, I, unreal.GeometryScriptBooleanOperation.UNION, bopt)
    unreal.GeometryScript_Normals.set_per_face_normals(land)
    unreal.GeometryScript_UVs.set_mesh_u_vs_from_planar_projection(land, 0, unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(2000, 2000, 2000)), unreal.GeometryScriptMeshSelection())
    out["water_cuts"] = n
    out["ground_tris"] = tris_count(land)
    place(save_mesh(land, "SM_Ground", mat("M_BO_Sidewalk")), "Ground", "Ground")
    # riverbed under everything, water surface over the cuts
    bed = unreal.DynamicMesh()
    P.append_box(bed, OPT, unreal.Transform(unreal.Vector(cx, cy, BED_Z - 200), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                 X1 - X0, Y1 - Y0, 200, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
    place(save_mesh(bed, "SM_Riverbed", mat("M_BO_Asphalt")), "Riverbed", "Ground")
    water = unreal.DynamicMesh()
    for ring in PLAN["water"]["outer"]:
        pts = ring_ue(ring)
        if len(pts) >= 3:
            P.append_triangulated_polygon(water, OPT, unreal.Transform(unreal.Vector(0, 0, WATER_Z), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                          [v2(p) for p in pts], True)
    place(save_mesh(water, "SM_Water", mat("M_BO_Water"), collide=False), "Water", "Ground", collide=False)
    out["water_tris"] = tris_count(water)


def stage_overlays():
    sand = ensure_material("M_BO_Sand", (0.78, 0.68, 0.45), 0.9)
    for key, name, m, z in (("parks", "SM_Parks", mat("M_BO_Park"), 3.0), ("beaches", "SM_Beach", sand, 4.0)):
        dm = unreal.DynamicMesh()
        n = 0
        for ring in PLAN.get(key, []):
            pts = ring_ue(ring)
            if len(pts) >= 3:
                P.append_triangulated_polygon(dm, OPT, unreal.Transform(unreal.Vector(0, 0, z), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                              [v2(p) for p in pts], True)
                n += 1
        if n:
            place(save_mesh(dm, name, m), name[3:], "Ground")
        out[key] = n


def path_transforms(pts_ue, zs):
    T = []
    for i, (p, z) in enumerate(zip(pts_ue, zs)):
        a = pts_ue[max(0, i - 1)]; b = pts_ue[min(len(pts_ue) - 1, i + 1)]
        za = zs[max(0, i - 1)]; zb = zs[min(len(zs) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ds = math.hypot(dx, dy) or 1.0
        yaw = math.degrees(math.atan2(dy, dx))
        pitch = math.degrees(math.atan2(zb - za, ds))
        T.append(unreal.Transform(unreal.Vector(p[0], p[1], z), unreal.Rotator(roll=0, pitch=pitch, yaw=yaw), unreal.Vector(1, 1, 1)))
    return T


def resample(pts, step):
    out_ = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(math.dist(a, b) / step))
        for i in range(1, n + 1):
            out_.append((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n))
    return out_


def sweep_deck(dm, pts_ue, zs, width, thick):
    if len(pts_ue) < 2:
        return
    prof = [v2((-width / 2, -thick)), v2((width / 2, -thick)), v2((width / 2, 0)), v2((-width / 2, 0))]
    P.append_sweep_polygon(dm, OPT, unreal.Transform(), prof, path_transforms(pts_ue, zs), False, True, 1.0, 1.0, 0.0, 1.0)


def stage_roads():
    asphalt = mat("M_BO_Asphalt")
    total = 0
    for cls in ("minor", "mid", "major", "highway"):
        w, top = ROAD[cls]
        dm = unreal.DynamicMesh()
        n = 0
        for r in PLAN["roads"]:
            if r["cls"] != cls or r.get("elevated"):
                continue
            pts = resample([ue(p) for p in r["pts"]], 2500.0)
            if len(pts) < 2:
                continue
            sweep_deck(dm, pts, [top] * len(pts), w, 80.0)
            n += 1
        if n:
            unreal.GeometryScript_UVs.set_mesh_u_vs_from_planar_projection(dm, 0, unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(1500, 1500, 1500)), unreal.GeometryScriptMeshSelection())
            place(save_mesh(dm, f"SM_Roads_{cls}", asphalt), f"Roads_{cls}", "Roads")
        out[f"roads_{cls}"] = n
        total += n
    out["roads_total"] = total


def elevated_profile(pts_ue, z_top, ramp):
    """Heights along a path: ramp up from the ground at each end unless that end touches another elevated piece."""
    s = [0.0]
    for a, b in zip(pts_ue, pts_ue[1:]):
        s.append(s[-1] + math.dist(a, b))
    L = s[-1]
    r = min(ramp, L / 2.5)
    zs = []
    for d in s:
        f = min(1.0, d / r, (L - d) / r)
        f = f * f * (3 - 2 * f)          # ease in and out
        zs.append(ROAD["highway"][1] + (z_top - ROAD["highway"][1]) * f)
    return zs


def stage_elevated():
    deck = unreal.DynamicMesh()
    piers = unreal.DynamicMesh()
    n = 0
    # Roads the expressway kit builds (Scripts/roads/build_expressway_ue.py, layout in Saved/Expressway) are skipped, so a
    # rerun of this stage doesn't put the generic slab back over them (20 Oct 2026, agent highway-capitol).
    try:
        kit_roads = {r["plan_name"] for r in json.load(open(ROOT + "/Saved/Expressway/expressway_layout.json"))["roads"].values()}
    except Exception:
        kit_roads = set()
    for r in PLAN["roads"]:
        if not r.get("elevated") or r.get("name") in kit_roads:
            continue
        pts = resample([ue(p) for p in r["pts"]], 1500.0)
        zs = elevated_profile(pts, ELEV_Z, ELEV_RAMP)
        sweep_deck(deck, pts, zs, ROAD[r["cls"]][0], 150.0)
        acc = 0.0
        for i in range(1, len(pts)):
            acc += math.dist(pts[i - 1], pts[i])
            if acc >= 4000 and zs[i] > 400:
                acc = 0.0
                P.append_box(piers, OPT, unreal.Transform(unreal.Vector(pts[i][0], pts[i][1], 0), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                             220, 220, zs[i] - 150, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        n += 1
    if n:
        place(save_mesh(deck, "SM_ElevatedExpressways", mat("M_BO_Asphalt")), "ElevatedExpressways", "Roads")
    out["elevated_roads"] = n
    # the L is a real elevated railway now (bents, spans, stations): Scripts/roads/build_l_ue.py
    m = 0
    if tris_count(piers) > 0:
        place(save_mesh(piers, "SM_Piers", mat("M_BO_Sidewalk")), "Piers", "Roads")
    out["L_pieces"] = m     # 0: see Scripts/roads/build_l_ue.py


def stage_landmarks():
    glass, granite, dome, steel, water = mat("M_BO_Glass"), mat("M_BO_Granite"), mat("M_BO_Dome"), mat("M_BO_LSteel"), mat("M_BO_Water")
    placed = []
    for lm in PLAN["landmarks"]:
        X, Y = ue(lm["pos"])
        dm = unreal.DynamicMesh()
        name = lm["name"]
        m = glass
        if name == "Willis Tower":
            tube = 2300.0
            hs = [[290, 368, 200], [442, 442, 368], [200, 290, 290]]
            for i in range(3):
                for j in range(3):
                    P.append_box(dm, OPT, unreal.Transform(unreal.Vector(X + (i - 1) * tube, Y + (j - 1) * tube, 0), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                                 tube, tube, hs[i][j] * 100.0, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        elif name == "Texas State Capitol":
            m = granite
            T = lambda z: unreal.Transform(unreal.Vector(X, Y, z), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1))
            P.append_box(dm, OPT, T(0), 7000, 17000, 2600, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
            P.append_cylinder(dm, OPT, T(2600), 1800, 2400, 32, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
            P.append_sphere_lat_long(dm, OPT, T(5000), 1800, 24, 32, unreal.GeometryScriptPrimitiveOriginMode.CENTER)
            P.append_cylinder(dm, OPT, T(6600), 350, 2600, 16, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        elif name == "The Bean":
            m = dome
            P.append_sphere_lat_long(dm, OPT, unreal.Transform(unreal.Vector(X, Y, 500), unreal.Rotator(0, 0, 0), unreal.Vector(1.0, 0.6, 0.45)), 1000, 24, 32,
                                     unreal.GeometryScriptPrimitiveOriginMode.CENTER)
        elif name == "Buckingham Fountain":
            m = granite
            T = lambda z: unreal.Transform(unreal.Vector(X, Y, z), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1))
            P.append_cylinder(dm, OPT, T(0), 2400, 120, 48, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
            P.append_cylinder(dm, OPT, T(120), 900, 300, 32, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
            P.append_cylinder(dm, OPT, T(420), 450, 300, 24, 0, True, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        elif name == "Navy Pier":
            m = steel
            P.append_torus(dm, OPT, unreal.Transform(unreal.Vector(X, Y + 6000, 4600), unreal.Rotator(roll=90, pitch=0, yaw=0), unreal.Vector(1, 1, 1)),
                           unreal.GeometryScriptRevolveOptions(), 4200, 150, 48, 8, unreal.GeometryScriptPrimitiveOriginMode.CENTER)
            P.append_box(dm, OPT, unreal.Transform(unreal.Vector(X, Y + 6000, 0), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                         300, 300, 4600, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        else:
            continue
        safe = "".join(ch for ch in name if ch.isalnum())
        place(save_mesh(dm, f"SM_Landmark_{safe}", m), f"Landmark_{safe}", "Landmarks")
        placed.append(name)
    out["landmarks"] = placed


def vertex_color_material(name, rough, metal, emissive=0.0):
    """Material whose base colour is the mesh's vertex colour (each building is tinted when built)."""
    path = f"{MAT_DIR}/{name}"
    MEL = unreal.MaterialEditingLibrary
    if EAL.does_asset_exist(path):
        m = EAL.load_asset(path)
        MEL.delete_all_material_expressions(m)
    else:
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    vc = MEL.create_material_expression(m, unreal.MaterialExpressionVertexColor, -400, 0)
    MEL.connect_material_property(vc, "", unreal.MaterialProperty.MP_BASE_COLOR)
    for val, prop, y in ((rough, unreal.MaterialProperty.MP_ROUGHNESS, 150), (metal, unreal.MaterialProperty.MP_METALLIC, 230)):
        c = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, -400, y)
        c.set_editor_property("r", val)
        MEL.connect_material_property(c, "", prop)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def stage_buildings():
    import random
    rnd = random.Random(11)
    B = json.load(open(ROOT + "/Saved/Mashup/buildings_v3.json"))["buildings"]
    mats = {"tower": vertex_color_material("M_City_Tower", 0.5, 0.15), "glass": vertex_color_material("M_City_Glass", 0.12, 0.65),
            "lowrise": vertex_color_material("M_City_LowRise", 0.85, 0.0)}

    def tint(style):
        if style == "tower":
            r = rnd.random()
            if r < 0.18:
                g = rnd.uniform(0.10, 0.20); return (g, g, g * 1.08)            # dark glass and steel
            if r < 0.30:
                return (rnd.uniform(0.40, 0.52), rnd.uniform(0.22, 0.30), rnd.uniform(0.16, 0.22))   # brick
            g = rnd.uniform(0.55, 0.86); return (g, g * 0.98, g * 0.93)          # limestone and terracotta
        if style == "glass":
            return (rnd.uniform(0.10, 0.28), rnd.uniform(0.28, 0.46), rnd.uniform(0.40, 0.62))
        return rnd.choice([(0.80, 0.72, 0.58), (0.86, 0.82, 0.72), (0.70, 0.45, 0.32), (0.62, 0.64, 0.66), (0.78, 0.60, 0.42)])

    merged = {s: unreal.DynamicMesh() for s in mats}
    counts = {s: 0 for s in mats}
    VC = unreal.GeometryScript_VertexColors
    for b in B:
        X, Y = ue((b["x"], b["y"]))
        yaw = 90.0 - b["yaw"]
        h = b["h"] * 100.0
        w, d = b["w"] * 100.0, b["d"] * 100.0
        tmp = unreal.DynamicMesh()
        tiers = [(0.0, 1.0, 1.0)]
        if b["style"] == "tower" and b["h"] > 110:
            tiers = [(0.0, 0.58, 1.0), (0.58, 0.84, 0.76), (0.84, 1.0, 0.5)]
        elif b["style"] == "glass" and b["h"] > 90:
            tiers = [(0.0, 0.9, 1.0), (0.9, 1.0, 0.82)]
        for z0, z1, s in tiers:
            P.append_box(tmp, OPT, unreal.Transform(unreal.Vector(X, Y, z0 * h), unreal.Rotator(roll=0, pitch=0, yaw=yaw), unreal.Vector(1, 1, 1)),
                         w * s, d * s, (z1 - z0) * h, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        c = tint(b["style"])
        VC.set_mesh_constant_vertex_color(tmp, unreal.LinearColor(c[0], c[1], c[2], 1.0), unreal.GeometryScriptColorFlags(), False)
        unreal.GeometryScript_MeshEdits.append_mesh(merged[b["style"]], tmp, unreal.Transform())
        counts[b["style"]] += 1
    for s, dm in merged.items():
        if counts[s]:
            place(save_mesh(dm, f"SM_Buildings_{s}", mats[s]), f"Buildings_{s}", "Buildings")
    out["buildings"] = counts


def stage_horizon():
    """Sky City sits on an island: lake water out to the horizon around the map, and invisible walls (plus a ceiling)
    a few hundred metres past the edge so a flight can't leave the world."""
    x0, y0, x1, y1 = PLAN["bounds"]
    X0, X1, Y0, Y1 = y0 * 100, y1 * 100, x0 * 100, x1 * 100
    L = 6_000_000.0          # 60 km of lake in every direction
    sea = unreal.DynamicMesh()
    for (ax, bx, ay, by) in ((-L, L, -L, Y0), (-L, L, Y1, L), (-L, X0, Y0, Y1), (X1, L, Y0, Y1)):
        P.append_box(sea, OPT, unreal.Transform(unreal.Vector((ax + bx) / 2, (ay + by) / 2, WATER_Z - 2), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                     bx - ax, by - ay, 2, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
    unreal.GeometryScript_UVs.set_mesh_u_vs_from_planar_projection(sea, 0, unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(2000, 2000, 2000)), unreal.GeometryScriptMeshSelection())
    place(save_mesh(sea, "SM_HorizonLake", mat("M_BO_Water"), collide=False), "HorizonLake", "Ground", collide=False)
    M, H, T = 80000.0, 150000.0, 5000.0      # 800 m past the edge, 1.5 km ceiling, 50 m thick
    walls = unreal.DynamicMesh()
    for (cx, cy, sx, sy) in (((X0 + X1) / 2, Y0 - M, X1 - X0 + 2 * M, T), ((X0 + X1) / 2, Y1 + M, X1 - X0 + 2 * M, T),
                             (X0 - M, (Y0 + Y1) / 2, T, Y1 - Y0 + 2 * M), (X1 + M, (Y0 + Y1) / 2, T, Y1 - Y0 + 2 * M)):
        P.append_box(walls, OPT, unreal.Transform(unreal.Vector(cx, cy, -2000), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                     sx, sy, H + 2000, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
    P.append_box(walls, OPT, unreal.Transform(unreal.Vector((X0 + X1) / 2, (Y0 + Y1) / 2, H), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1)),
                 X1 - X0 + 2 * M, Y1 - Y0 + 2 * M, T, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
    a = place(save_mesh(walls, "SM_WorldBounds", mat("M_BO_Glass")), "WorldBounds", "Ground")
    a.set_actor_hidden_in_game(True)
    a.set_is_temporarily_hidden_in_editor(True)
    for act in (a, next(x for x in EAS.get_all_level_actors() if x.get_actor_label() == "HorizonLake")):
        act.set_editor_property("is_spatially_loaded", False)
    out["horizon"] = True


STAGES = {"horizon": stage_horizon, "buildings": stage_buildings, "map": stage_map, "ground": stage_ground, "overlays": stage_overlays, "roads": stage_roads,
          "elevated": stage_elevated, "landmarks": stage_landmarks}

def run_stage(stage):
    try:
        out["stage"] = stage
        t0 = time.time()
        EAL.make_directory(MESH_DIR)
        STAGES[stage]()
        if stage != "map":
            unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
        out["seconds"] = round(time.time() - t0, 1)
        out["ok"] = True
    except Exception:
        out["error"] = traceback.format_exc()
    open(OUT, "w").write(json.dumps(out, indent=1))


# Run on the next editor tick, so the console command (and the MCP call that typed it) returns at once;
# poll out.json for the result.
_stage = sys.argv[1] if len(sys.argv) > 1 else "map"
open(OUT, "w").write(json.dumps({"stage": _stage, "running": True}))
_handle = None


def _tick(dt):
    unreal.unregister_slate_post_tick_callback(_handle)
    run_stage(_stage)


_handle = unreal.register_slate_post_tick_callback(_tick)
