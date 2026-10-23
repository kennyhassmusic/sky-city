"""Mesh the generated city with the same facade, roof and storefront builder as the CG_* blocks.

Downtown (Chicago core) is meshed first, then one Austin low-rise street whose
lots carry different income tiers. Buildings are written in small GLBs so a
pull request stays under the LFS cap. Street surfaces in each shot are clipped
to that block, and dressing props are simple meshes (no trees).

The GLB vertices are the block exporter's -90 degree Z turn, baked in, so
Unreal imports them at the world origin: plan north on +X, plan east on +Y.

A glazed floor is a curtain wall: mullions, a spandrel at each slab, tinted
reflective glass, and an opaque interior behind every pane. Every face
(front, side, back, each setback) is UV'd from its own width and height:
U = width / meters_u, V = height / meters_v, with one scale on both axes.
Whole windows keep the facade texture's lit rect (24 by 19). Leftover length
is a pilaster, not a wider pane. face_uv.py checks the exported GLBs and
stops the build when texel density or window aspect is off by more than 3%.
The base is a concrete plinth on the planned sidewalks and asphalt. Grass is
only the parkway. Flat roofs get a parapet and roof units.

Run:
  blender -b --factory-startup -P Scripts/city/blender_city.py
Output:
  SourceArt/CityGen/city/CG_<district>_<index>.glb
  SourceArt/CityGen/city/CG_<district>_street_<index>.glb
  SourceArt/CityGen/city/city_manifest.json
  artifacts/previews/sky_city_downtown_aerial_day.png
  artifacts/previews/sky_city_downtown_street_day.png
  artifacts/previews/sky_city_residential_street_day.png
  artifacts/previews/sky_city_downtown_street_dusk.png
  artifacts/previews/sky_city_tower_side_day.png

SKYCITY_BUDGET_MB (default 220) stops the export. SKYCITY_CORE_MAX and
SKYCITY_RES_MAX cap how many buildings are even considered. SKYCITY_EXPORT=0
skips the GLB write and keeps the cameras already stored in city_manifest.json.
Daylight uses the CC0 Poly Haven sky (kloofendal) plus a sun; dusk uses kiara_9_dusk.
"""
import json
import math
import os
import shutil
import struct
import sys
import time
import zlib

import bpy

CITY = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("SKYCITY_ROOT") or os.path.dirname(os.path.dirname(CITY))
sys.path.insert(0, CITY)
sys.path.insert(0, os.path.join(ROOT, "Scripts", "streets"))
sys.path.insert(0, os.path.join(ROOT, "Scripts", "roads"))

import blender_block as bb  # noqa: E402
import face_uv  # noqa: E402
import generate_city  # noqa: E402
import geom  # noqa: E402
import grammar  # noqa: E402
import model as model_mod  # noqa: E402
import profiles  # noqa: E402
import realism  # noqa: E402

OUT = os.environ.get("SKYCITY_CITY_OUT") or os.path.join(ROOT, "SourceArt", "CityGen", "city")
REPO_PREVIEWS = os.path.join(ROOT, "artifacts", "previews")
PREVIEWS = os.environ.get("SKYCITY_PREVIEWS") or "/opt/cursor/artifacts/previews"
DAY_EXPOSURE = 0.0
DUSK_EXPOSURE = 0.0
DUSK_ELEVATION = 4.5
BUDGET = int(os.environ.get("SKYCITY_BUDGET_MB", "220")) * 1024 * 1024
FILE_CAP = 22 * 1024 * 1024
CORE_MAX = int(os.environ.get("SKYCITY_CORE_MAX", "22"))
RES_MAX = int(os.environ.get("SKYCITY_RES_MAX", "12"))
CORE_RADIUS = 170.0
RES_RADIUS = 70.0

DRESS = {
    "lamp", "bench", "bin", "hydrant", "signal", "stop", "yield",
    "street_name", "bus_stop", "parked", "drain", "bollard", "grate",
    "sign", "fence",
}


def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(REPO_PREVIEWS, exist_ok=True)
    os.makedirs(PREVIEWS, exist_ok=True)
    print("CITY build", flush=True)
    city = generate_city.build_from_disk()
    digest = model_mod.manifest_hash(city)
    print("CITY hash", digest, "seconds", round(time.time() - t0, 1), flush=True)
    lots = {lot["id"]: lot for lot in city.get("lots") or []}
    tier_counts = {}
    for spec in city.get("buildings") or []:
        if _district(city, spec) != "austin_low":
            continue
        tier_counts[_tier(spec, lots) or "none"] = tier_counts.get(_tier(spec, lots) or "none", 0) + 1
    print("AUSTIN TIERS", tier_counts, flush=True)
    anchor, core = _select_core(city)
    pair, residential = _select_residential(city, lots)
    core = core[:CORE_MAX]
    residential = residential[:RES_MAX]
    tier_names = [_tier(spec, lots) for spec in residential]
    print("CITY core", len(core), "of", _count(city, "chicago_core"),
          "residential", len(residential), "tiers", tier_names, flush=True)
    bb.reset()
    record = bb.load_material_record()
    lib = bb.make_library(record)
    _install_facades(lib, record)
    protos = _prototypes(lib)
    core_col = bb.collection("CoreBuildings")
    res_col = bb.collection("ResBuildings")
    core_obs = _mesh_list(core, lib, core_col, keep_tall_rooms=False)
    res_obs = _mesh_list(residential, lib, res_col, keep_tall_rooms=True)
    core_bounds = _bounds(core, 28.0)
    res_bounds = _bounds(residential, 22.0)
    core_street = _street(city, core_bounds, lib, protos, "CoreStreet", core)
    res_street = _street(city, res_bounds, lib, protos, "ResStreet", residential)
    locked = _cameras_from_manifest()
    cams = locked if locked else _cameras(anchor, pair, core, residential)
    cams = dict(cams)
    side = _tower_side(core)
    if side:
        cams["tower_side"] = side
    core_col = bpy.data.collections["CoreStreet"]
    res_col = bpy.data.collections["ResStreet"]
    core_street.extend(_camera_asphalt(city, cams["downtown_street"], lib, core_col, "downtown"))
    res_street.extend(_camera_asphalt(city, cams["residential_street"], lib, res_col, "residential"))
    if locked:
        print("CITY cameras from manifest", flush=True)
    if os.environ.get("SKYCITY_EXPORT", "1") == "0":
        _render(cams, core_obs, core_street, res_obs, res_street)
        print("CITY export skipped", round(time.time() - t0, 1), "s", flush=True)
        return
    files, spent = _export_all(core, core_obs, core_street, residential, res_obs, res_street)
    _require_face_uvs()
    manifest = {
        "seed": int(city.get("seed") or generate_city.SEED),
        "hash": digest,
        "frame": "Baked -90 Z, same turn as the CG block GLBs. Plan metres. Actor at the origin.",
        "budget_bytes": BUDGET,
        "bytes": spent,
        "chicago_core_total": _count(city, "chicago_core"),
        "chicago_core_meshed": len(core_obs),
        "austin_low_meshed": len(res_obs),
        "tiers": [_tier(spec, lots) for spec in residential],
        "cameras": cams,
        "files": files,
        "note": "Chicago core around one downtown street, then one residential street. The rest of the city is the spawn record until a larger budget is set.",
    }
    path = os.path.join(OUT, "city_manifest.json")
    with open(path, "w") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    print("CITY done", len(files), "files", round(spent / (1024 * 1024), 1), "MB",
          round(time.time() - t0, 1), "s", flush=True)
    _render(cams, core_obs, core_street, res_obs, res_street)


def _count(city, name):
    return sum(1 for spec in city.get("buildings") or [] if _district(city, spec) == name)


def _district(city, spec):
    wanted = spec.get("district_id")
    for district in city.get("districts") or []:
        if district.get("id") == wanted:
            return district.get("name") or ""
    return ""


def _tier(spec, lots):
    return (lots.get(spec.get("lot_id")) or {}).get("tier") or ""


def _centre(spec):
    pts = [(float(p[0]), float(p[1])) for p in spec.get("footprint") or []]
    if not pts:
        return (0.0, 0.0)
    return geom.centroid(pts)


def _select_core(city):
    named = []
    for spec in city.get("buildings") or []:
        if spec.get("role") == "landmark" or not spec.get("floors") or not spec.get("facades"):
            continue
        if _district(city, spec) == "chicago_core":
            named.append(spec)
    best = None
    for spec in named:
        height = float(spec.get("height") or 0)
        if height < 16 or height > 64:
            continue
        centre = _centre(spec)
        near = sum(1 for other in named if other is not spec and geom.dist(centre, _centre(other)) < 48)
        rank = (near, -abs(height - 30))
        if best is None or rank > best[0]:
            best = (rank, spec)
    anchor = best[1] if best else max(named, key=lambda spec: float(spec.get("height") or 0))
    origin = _centre(anchor)
    cluster = [spec for spec in named if geom.dist(_centre(spec), origin) <= CORE_RADIUS]
    cluster.sort(key=lambda spec: geom.dist(_centre(spec), origin))
    if anchor not in cluster:
        cluster.insert(0, anchor)
    return anchor, cluster


def _select_residential(city, lots):
    named = []
    for spec in city.get("buildings") or []:
        if not spec.get("floors") or not spec.get("facades"):
            continue
        if _district(city, spec) != "austin_low":
            continue
        if _tier(spec, lots):
            named.append(spec)
    best = None
    for left in named:
        left_tier = _tier(left, lots)
        if left_tier not in ("high", "low", "distressed", "mid"):
            continue
        for right in named:
            right_tier = _tier(right, lots)
            if right is left or right_tier == left_tier:
                continue
            if right_tier not in ("high", "low", "distressed", "mid"):
                continue
            span = geom.dist(_centre(left), _centre(right))
            if span < 8 or span > 45:
                continue
            kinds = {left_tier, right_tier}
            # Neighbours along the income axis. High beside mid reads in one frame.
            rank = 0 if "high" in kinds else 1 if "distressed" in kinds else 2
            key = (rank, span)
            if best is None or key < best[0]:
                best = (key, left, right)
    if best is None:
        origin = _centre(named[0]) if named else (0.0, 0.0)
        cluster = sorted(named, key=lambda spec: geom.dist(_centre(spec), origin))[:RES_MAX]
        return (cluster[0] if cluster else None, None), cluster
    _rank, left, right = best
    mid = geom.lerp(_centre(left), _centre(right), 0.5)
    cluster = [spec for spec in named if geom.dist(_centre(spec), mid) <= RES_RADIUS]
    cluster.sort(key=lambda spec: geom.dist(_centre(spec), mid))
    for spec in (left, right):
        if spec not in cluster:
            cluster.insert(0, spec)
    return (left, right), cluster


def _prototypes(lib):
    import blender_street_kit as kit
    made = {}
    for key, build in (("lamp", kit.street_lamp), ("drain", kit.storm_drain), ("bollard", kit.bollard)):
        ob = build(do_export=False)
        ob.hide_render = True
        ob.hide_set(True)
        made[key] = ob
    made["bench"] = bb._bench()
    made["hydrant"] = bb._hydrant()
    made["signal"] = bb._signal()
    made["stop"] = bb._blade_sign((0.62, 0.08, 0.07), "SK_Stop")
    made["yield"] = bb._blade_sign((0.86, 0.68, 0.12), "SK_Yield")
    made["street_name"] = bb._blade_sign((0.12, 0.32, 0.22), "SK_StreetName")
    made["bus_stop"] = bb._blade_sign((0.12, 0.28, 0.48), "SK_BusStop")
    made["parked"] = bb._parked_car()
    made.update(realism.prototypes(lib, bb.Mesh))
    made["fence_iron"] = _fence("SK_FenceIron", "iron")
    made["fence_wood"] = _fence("SK_FenceWood", "wood")
    return made


def _fence(name, style):
    mesh = bb.Mesh(name)
    metal = bb.flat("M_FenceIron", (0.16, 0.17, 0.18), 0.4)
    wood = bb.flat("M_FenceWood", (0.36, 0.24, 0.14), 0.65)
    mat = metal if style == "iron" else wood
    for x in (-3.5, -1.15, 1.15, 3.5):
        mesh.box((x, 0, 0.55), (1, 0, 0), (0, 1, 0), (0, 0, 1), (0.08, 0.08, 1.1), mat)
    if style == "iron":
        for z in (0.38, 0.92):
            mesh.box((0, 0, z), (1, 0, 0), (0, 1, 0), (0, 0, 1), (7.6, 0.025, 0.025), mat)
    else:
        mesh.box((0, 0, 0.55), (1, 0, 0), (0, 1, 0), (0, 0, 1), (7.4, 0.04, 0.85), mat)
    ob = mesh.finish(bpy.data.collections["Prototypes"])
    ob.hide_render = True
    ob.hide_set(True)
    return ob


def _metres(mat):
    """Texture size in metres. materials.json stores uv_m as [meters_u, meters_v]."""
    if mat is None:
        return 1.0, 1.0
    try:
        keys = mat.keys()
    except (AttributeError, TypeError):
        keys = ()
    try:
        if "meters_u" in keys:
            mu = float(mat["meters_u"] or 1.0)
            mv = float(mat["meters_v"] or mu) if "meters_v" in keys else mu
        else:
            raw = mat.get("uv_m") if hasattr(mat, "get") else None
            if isinstance(raw, (list, tuple)) and len(raw) >= 2:
                mu, mv = float(raw[0] or 1.0), float(raw[1] or 1.0)
            elif raw:
                mu = mv = float(raw)
            else:
                mu, mv = 1.0, 1.0
    except (TypeError, ValueError):
        mu, mv = 1.0, 1.0
    return (mu if mu > 1e-4 else 1.0), (mv if mv > 1e-4 else 1.0)


def _uv_metres(self, u_len, v_len, mat):
    """One density on both axes. U = width / meters_u, V = height / meters_v.

    meters_v follows the image pixel aspect, so a square scan is not stretched
    by scaling only U or only V. uv_origin_m continues the same grid along the wall.
    """
    mu, mv = _metres(mat)
    px, py = 1.0, 1.0
    try:
        if mat is not None and "px" in mat.keys():
            px = float(mat["px"] or 1.0)
            py = float(mat["py"] or px)
    except (AttributeError, TypeError, ValueError):
        px, py = 1.0, 1.0
    mu, mv = face_uv.uniform_metres(mu, mv, px, py)
    origin = getattr(self, "uv_origin_m", (0.0, 0.0)) or (0.0, 0.0)
    u0 = float(origin[0]) / mu
    v0 = float(origin[1]) / mv
    u = abs(float(u_len)) / mu
    v = abs(float(v_len)) / mv
    return [(u0, v0), (u0 + u, v0), (u0 + u, v0 + v), (u0, v0 + v)]


def _stamp_scales(lib, record):
    for slot, ident in bb.SLOT.items():
        info = record.get(ident) or {}
        pair = info.get("uv_m") or [2.0, 2.0]
        if not isinstance(pair, (list, tuple)):
            pair = [pair, pair]
        mu = float(info.get("meters_u") or pair[0] or 2.0)
        mv = float(info.get("meters_v") or (pair[1] if len(pair) > 1 else pair[0]) or mu)
        mat = lib.get(slot)
        if mat is not None:
            color = ((info.get("maps") or {}).get("color")) or ""
            px, py = face_uv.image_size(os.path.join(bb.ART, "materials", color))
            mu, mv = face_uv.uniform_metres(mu, mv, px, py)
            mat["meters_u"] = mu
            mat["meters_v"] = mv
            mat["px"] = px
            mat["py"] = py


def _curtain_glass(name, emit):
    """Tinted reflective curtain glass. The clear pane was a hole into the floor plates."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.55, 0.68, 0.74, 1)
    bsdf.inputs["Roughness"].default_value = 0.045
    bb._set(bsdf, ("Metallic",), 0.72)
    bb._set(bsdf, ("Emission Color", "Emission"), (0.75, 0.86, 0.95, 1))
    bb._set(bsdf, ("Emission Strength",), emit)
    transp = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = 0.08
    out = nt.nodes.get("Material Output")
    nt.links.new(bsdf.outputs["BSDF"], mix.inputs[1])
    nt.links.new(transp.outputs["BSDF"], mix.inputs[2])
    for link in list(nt.links):
        if link.to_node == out:
            nt.links.remove(link)
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    mat["emit"] = emit
    return mat


def _whole_bays(length, bay_m, pier):
    """Whole modules of bay_m. Leftover widens the mullions; the glass is never wider than the module."""
    bay_m = max(1.4, float(bay_m))
    pier = max(0.08, min(float(pier), bay_m * 0.4))
    glass = max(0.75, bay_m - pier)
    count = max(1, int(round(float(length) / bay_m)))
    need = count * glass + (count + 1) * pier
    if need > length:
        glass = (length - (count + 1) * pier) / count
        if glass < 0.7 and count > 1:
            count -= 1
            glass = min(bay_m - pier, (length - (count + 1) * pier) / max(1, count))
    if glass < 0.45:
        glass = max(0.35, length * 0.62)
        pier_w = max(0.06, (length - glass) / 2.0)
        return 1, glass, pier_w
    need = count * glass + (count + 1) * pier
    slack = max(0.0, length - need)
    pier_w = pier + slack / (count + 1)
    return count, glass, pier_w


def _pane_slots(width, module):
    """Split one opening into whole panes. A 7 m hole becomes two modules, not one stretched window."""
    module = max(0.9, float(module))
    if width <= module * 1.15:
        return [("pane", 0.0, width)]
    count = max(2, int(round(width / module)))
    bar = 0.1
    pane = module
    need = count * pane + (count - 1) * bar
    if need > width:
        pane = (width - (count - 1) * bar) / count
    slack = max(0.0, width - (count * pane + (count - 1) * bar))
    x = slack / 2.0
    slots = []
    for i in range(count):
        slots.append(("pane", x, pane))
        x += pane
        if i + 1 < count:
            slots.append(("bar", x, bar))
            x += bar
    return slots


def _bay_at(building, facade, along):
    """The grammar bay that owns this point, so a split pane keeps that room."""
    bays = max(1, int(facade.get("bays") or 1))
    opening = float(facade.get("opening_w") or 1.0)
    pier = float(facade.get("pier_w") or 0.2)
    pitch = pier + opening
    bay = int((along - pier) / pitch) if pitch > 1e-4 else 0
    bay = max(0, min(bays - 1, bay))
    return grammar.room_of(building, facade, bay), bay


def _curtain_pane(mesh, building, facade, along, width, ax, ay, tx, ty, tangent, inward, gz0, gz1, metal, lib):
    origin = (ax + tx * along, ay + ty * along)
    room, bay = _bay_at(building, facade, along + width / 2.0)
    if room is not None:
        lit = bool(room.get("lit"))
    else:
        lit = grammar.bay_lit(building.get("seed") or 1, building["id"], facade.get("floor") or 0, bay)
    glass = lib["curtain_glass_lit"] if lit else lib["curtain_glass"]
    panel = lib["interior_lit"] if lit else lib.get("plaster", metal)
    mid_z = (gz0 + gz1) / 2.0
    gh = gz1 - gz0
    centre = (origin[0] + tx * width / 2.0 + inward[0] * 0.07,
              origin[1] + ty * width / 2.0 + inward[1] * 0.07, mid_z)
    mesh.box(centre, tangent, inward, (0, 0, 1), (max(0.2, width - 0.02), 0.015, max(0.3, gh)), glass)
    # Transom in front of the glass, so the bay reads as a frame and not one sheet.
    bb._span(mesh, origin, tangent, inward, (0, 0, 1), width, 0.1, mid_z - 0.04, mid_z + 0.04, metal)
    # Opaque room back, tucked behind the mullions and the spandrel. Nothing sees the hollow.
    back = (origin[0] + tx * width / 2.0 + inward[0] * 0.46,
            origin[1] + ty * width / 2.0 + inward[1] * 0.46, mid_z)
    mesh.box(back, tangent, inward, (0, 0, 1), (width + 0.1, 0.05, gh + 0.12), panel)
    realism.dress_opening(mesh, building, facade, bay, origin, tangent, inward, width, gz0, gz1, 0.4, lib, "curtain")


def _curtain_facade(mesh, building, facade, metal, lib):
    ax, ay = float(facade["a"][0]), float(facade["a"][1])
    bx, by = float(facade["b"][0]), float(facade["b"][1])
    length = float(facade["length"] or 1.0) or 1.0
    tx, ty = (bx - ax) / length, (by - ay) / length
    nx, ny = float(facade["normal"][0]), float(facade["normal"][1])
    tangent = (tx, ty, 0.0)
    inward = (-nx, -ny, 0.0)
    up = (0.0, 0.0, 1.0)
    z0 = float(facade["z"]) + profiles.CURB_RISE
    h = float(facade["h"])
    count, glass_w, pier_w = _whole_bays(length, building.get("bay_m") or 3.0, building.get("pier_m") or 0.14)
    bot = min(0.72, max(0.42, h * 0.18))
    top = min(0.52, max(0.32, h * 0.14))
    if bot + top + 0.85 > h:
        bot = h * 0.2
        top = h * 0.14
    gz0, gz1 = z0 + bot, z0 + h - top
    thick = 0.26
    # Spandrels cover the slab at this floor and the one above. They are metal, not glass.
    bb._span(mesh, (ax, ay), tangent, inward, up, length, thick, z0, gz0, metal)
    bb._span(mesh, (ax, ay), tangent, inward, up, length, thick, gz1, z0 + h, metal)
    cursor = 0.0
    for i in range(count):
        bb._span(mesh, (ax + tx * cursor, ay + ty * cursor), tangent, inward, up, pier_w, thick + 0.05, z0, z0 + h, metal)
        cursor += pier_w
        _curtain_pane(mesh, building, facade, cursor, glass_w, ax, ay, tx, ty, tangent, inward, gz0, gz1, metal, lib)
        cursor += glass_w
    bb._span(mesh, (ax + tx * cursor, ay + ty * cursor), tangent, inward, up,
             max(0.05, length - cursor), thick + 0.05, z0, z0 + h, metal)
    cornice = float(facade.get("cornice") or 0)
    if cornice > 0.05:
        scale = 0.65 + 0.7 * geom.rnd(int(building.get("seed") or 1), building["id"], int(facade.get("floor") or 0), "cornice")
        depth = min(0.75, cornice * 0.42 * scale)
        centre = (ax + tx * length / 2.0 - nx * depth / 2.0,
                  ay + ty * length / 2.0 - ny * depth / 2.0,
                  z0 + h - 0.08)
        mesh.box(centre, tangent, (nx, ny, 0.0), up, (length, depth, 0.16 + 0.14 * scale), metal)


def _target_window_h(building, floor_h, opening):
    """The pane is this tall before the fitter keeps the source aspect."""
    floor_h = float(floor_h or 3.0)
    if opening == "curtain":
        return min(floor_h * 0.76, floor_h - 0.48)
    frac = float(building.get("head") or 0.74) - float(building.get("sill") or 0.32)
    return floor_h * max(0.36, min(0.58, frac))


def _fitted_facade(mesh, building, facade, wall, trim, metal, lib):
    """One projection per edge. Whole panes; pilasters take the leftover length."""
    ax, ay = float(facade["a"][0]), float(facade["a"][1])
    bx, by = float(facade["b"][0]), float(facade["b"][1])
    length = float(facade.get("length") or 0.0) or math.hypot(bx - ax, by - ay)
    if length < 0.4:
        return
    tx, ty = (bx - ax) / length, (by - ay) / length
    nx, ny = float(facade["normal"][0]), float(facade["normal"][1])
    tangent = (tx, ty, 0.0)
    inward = (-nx, -ny, 0.0)
    up = (0.0, 0.0, 1.0)
    z0 = float(facade["z"]) + profiles.CURB_RISE
    floor_h = float(facade["h"])
    z1 = z0 + floor_h
    opening = facade.get("opening") or "punched"
    pier = float(building.get("pier_m") or 0.3)
    lay = face_uv.fit_bays(length, floor_h, pier, face_uv.WINDOW_ASPECT,
                           _target_window_h(building, floor_h, opening))
    field = metal if opening == "curtain" else wall
    glass_mat_lit = lib["curtain_glass_lit"] if opening == "curtain" else lib["glass_lit"]
    glass_mat = lib["curtain_glass"] if opening == "curtain" else lib["glass"]
    # A short edge cannot hold a real pane. The wall is solid rather than a stretched slot.
    if lay["wh"] < 0.4 or lay["ww"] < 0.45 or lay["ww"] / lay["wh"] < 0.2:
        mesh.uv_origin_m = (0.0, z0)
        bb._span(mesh, (ax, ay), tangent, inward, up, length, 0.28, z0, z1, field)
        mesh.uv_origin_m = (0.0, 0.0)
        return
    sill = z0 + max(0.2, (floor_h - lay["wh"]) * (0.28 if opening == "curtain" else 0.55))
    head = sill + lay["wh"]
    if head > z1 - 0.12:
        head = z1 - 0.12
        sill = head - lay["wh"]
    mesh.uv_origin_m = (0.0, z0)
    bb._span(mesh, (ax, ay), tangent, inward, up, length, 0.28, z0, sill, field)
    mesh.uv_origin_m = (0.0, head)
    bb._span(mesh, (ax, ay), tangent, inward, up, length, 0.28, head, z1, field)
    cursor = 0.0
    for index in range(lay["count"]):
        pier_w = lay["end"] if index == 0 else lay["pier"]
        mesh.uv_origin_m = (cursor, z0)
        bb._span(mesh, (ax + tx * cursor, ay + ty * cursor), tangent, inward, up, pier_w, 0.34, z0, z1, trim)
        cursor += pier_w
        origin = (ax + tx * cursor, ay + ty * cursor)
        _fitted_pane(mesh, building, facade, index, origin, tangent, inward, lay["ww"], sill, head,
                     glass_mat, glass_mat_lit, lib, opening)
        cursor += lay["ww"]
    rest = length - cursor
    if rest > 0.02:
        mesh.uv_origin_m = (cursor, z0)
        bb._span(mesh, (ax + tx * cursor, ay + ty * cursor), tangent, inward, up,
                 rest, 0.34, z0, z1, trim)
    mesh.uv_origin_m = (0.0, 0.0)
    if opening == "storefront":
        realism.shop_band(mesh, building, facade, 0, (ax, ay), tangent, inward, min(length, lay["ww"] * 2), z1 - 0.05, lib)


def _fitted_pane(mesh, building, facade, bay, origin, tangent, inward, width, z0, z1, glass, glass_lit, lib, opening):
    """A pane whose glass quad is exactly the source aspect. The frame does not inset it."""
    room = grammar.room_of(building, facade, min(bay, max(0, int(facade.get("bays") or 1) - 1)))
    if room is not None:
        lit = bool(room.get("lit"))
    else:
        lit = grammar.bay_lit(building.get("seed") or 1, building["id"], facade.get("floor") or 0, bay)
    height = z1 - z0
    centre = (origin[0] + tangent[0] * width / 2.0 + inward[0] * 0.08,
              origin[1] + tangent[1] * width / 2.0 + inward[1] * 0.08,
              (z0 + z1) / 2.0)
    mesh.uv_origin_m = (0.0, 0.0)
    mesh.box(centre, tangent, inward, (0.0, 0.0, 1.0), (width, 0.02, height), glass_lit if lit else glass)
    back = (origin[0] + tangent[0] * width / 2.0 + inward[0] * 0.42,
            origin[1] + tangent[1] * width / 2.0 + inward[1] * 0.42,
            (z0 + z1) / 2.0)
    panel = lib["interior_lit"] if lit else lib.get("plaster", lib["interior"])
    mesh.box(back, tangent, inward, (0.0, 0.0, 1.0), (width, 0.04, height), panel)
    kind = "curtain" if opening == "curtain" else "window"
    realism.dress_opening(mesh, building, facade, bay, origin, tangent, inward, width, z0, z1, 0.35, lib, kind)


def _city_facade(mesh, building, facade, wall, trim, metal, lib):
    """Front, side, back and every setback. The grammar bay width is not reused.

    That width was stretched so the openings filled the edge. The fitter keeps
    the source window aspect and puts the leftover into the end pilasters.
    """
    _fitted_facade(mesh, building, facade, wall, trim, metal, lib)


def _panel_behind(mesh, building, facade, bay, origin, tangent, inward, width, z0, z1, lib):
    """Tall towers skip the upper room shells. The pane still needs a solid back."""
    if float(building.get("height") or 0) < 22:
        return
    room = grammar.room_of(building, facade, bay)
    if room is None:
        return
    mat = lib["interior_lit"] if room.get("lit") else lib.get("plaster", lib["interior"])
    centre = (origin[0] + tangent[0] * width / 2.0 + inward[0] * 1.15,
              origin[1] + tangent[1] * width / 2.0 + inward[1] * 1.15,
              (z0 + z1) / 2.0)
    mesh.box(centre, tangent, inward, (0, 0, 1), (width * 0.98, 0.05, max(0.3, (z1 - z0) * 0.98)), mat)


def _city_window(mesh, building, facade, bay, origin_xy, tangent, inward, width, z0, z1, recess, lib, kind="window"):
    module = float(building.get("bay_m") or 3.2) - float(building.get("pier_m") or 0.3)
    slots = _pane_slots(width, module)
    if kind in ("door", "storefront") or len(slots) <= 1:
        _ORIG_WINDOW(mesh, building, facade, bay, origin_xy, tangent, inward, width, z0, z1, recess, lib, kind)
        _panel_behind(mesh, building, facade, bay, origin_xy, tangent, inward, width, z0, z1, lib)
        return
    ox, oy = origin_xy
    tx, ty = tangent[0], tangent[1]
    metal = lib.get("metal", lib["plaster"])
    for kind_s, along, span in slots:
        origin = (ox + tx * along, oy + ty * along)
        if kind_s == "bar":
            bb._span(mesh, origin, tangent, inward, (0, 0, 1), span, 0.2, z0, z1, metal)
            continue
        _ORIG_WINDOW(mesh, building, facade, bay, origin, tangent, inward, span, z0, z1, recess, lib, kind)
        _panel_behind(mesh, building, facade, bay, origin, tangent, inward, span, z0, z1, lib)


def _city_rooms(mesh, building, lib):
    """Upper floors of a tower are the curtain panels, not an empty office you can see through."""
    if float(building.get("height") or 0) < 22:
        return _ORIG_ROOMS(mesh, building, lib)
    kept = [room for room in (building.get("rooms") or []) if int(room.get("floor") or 0) == 0]
    if not kept:
        return None
    copy = dict(building)
    copy["rooms"] = kept
    return _ORIG_ROOMS(mesh, copy, lib)


def _no_streak(*_args, **_kwargs):
    return None


def _tall_parapet(mesh, poly, z, height, mat):
    """A low lip disappears against a flat grey deck. Keep at least a metre."""
    _ORIG_PARAPET(mesh, poly, z, max(float(height or 0), 1.05), mat)


def _deck_z(building):
    floors = building.get("floors") or []
    if not floors:
        return 0.0
    roof = building.get("roof") or {}
    top = floors[-1]
    z = float(roof.get("z") or (float(top["z"]) + float(top["h"]))) + profiles.CURB_RISE
    shape = roof.get("shape") or "flat"
    h = float(roof.get("h") or 1.0)
    if shape == "setback":
        return z + max(3.0, h)
    if shape == "mansard":
        return z + max(2.2, h * 0.72) + 0.16
    return z + 0.16


def _ensure_clutter(mesh, building, deck, metal, roof_mat):
    """HVAC, a stair bulkhead and a tank, when the roof record does not already have them."""
    floors = building.get("floors") or []
    roof = building.get("roof") or {}
    if not floors or (roof.get("shape") or "flat") not in ("flat", "parapet", "setback", "mansard"):
        return
    poly = [(float(p[0]), float(p[1])) for p in floors[-1]["polygon"]]
    if len(poly) < 3 or abs(geom.poly_area(poly)) < 40:
        return
    have = {unit.get("kind") for unit in roof.get("units") or []}
    centre = geom.centroid(poly)
    span = max(geom.spans(poly))
    offsets = {"hvac": (0.22, 0.06), "stair": (-0.18, 0.14), "water_tank": (0.04, -0.2)}
    for kind, (ox, oy) in offsets.items():
        if kind in have:
            continue
        x = centre[0] + ox * span * 0.4
        y = centre[1] + oy * span * 0.4
        if not geom.point_in_poly((x, y), poly):
            x, y = centre
        bb._unit(mesh, {"kind": kind, "x": x, "y": y, "z": deck}, metal, roof_mat)


def _terrace_parapets(mesh, building, trim, metal, roof_mat):
    """A setback leaves a bare slab. Give that terrace a parapet and one unit."""
    floors = building.get("floors") or []
    for index in range(len(floors) - 1):
        lower, upper = floors[index], floors[index + 1]
        if float(upper.get("inset") or 0) < float(lower.get("inset") or 0) + 0.8:
            continue
        poly = [(float(p[0]), float(p[1])) for p in lower.get("polygon") or []]
        if len(poly) < 3:
            continue
        z = float(lower["z"]) + profiles.CURB_RISE + float(lower["h"])
        bb._parapet(mesh, poly, z, 0.95, trim)
        if abs(geom.poly_area(poly)) < 120:
            continue
        inner = [(float(p[0]), float(p[1])) for p in upper.get("polygon") or []]
        centre = geom.centroid(poly)
        tower = geom.centroid(inner) if len(inner) >= 3 else centre
        dx, dy = centre[0] - tower[0], centre[1] - tower[1]
        length = math.hypot(dx, dy) or 1.0
        x = tower[0] + dx / length * (length + 2.5)
        y = tower[1] + dy / length * (length + 2.5)
        if geom.point_in_poly((x, y), poly) and not (inner and geom.point_in_poly((x, y), inner)):
            bb._unit(mesh, {"kind": "hvac", "x": x, "y": y, "z": z}, metal, roof_mat)


def _city_roof(mesh, building, wall, trim, metal, roof_mat):
    mesh.uv_origin_m = (0.0, 0.0)
    _ORIG_ROOF(mesh, building, wall, trim, metal, roof_mat)
    _ensure_clutter(mesh, building, _deck_z(building), metal, roof_mat)
    _terrace_parapets(mesh, building, trim, metal, roof_mat)


def _install_facades(lib, record):
    """City-only. The CG block previews keep the original facade builder."""
    global _ORIG_FACADE, _ORIG_WINDOW, _ORIG_ROOMS, _ORIG_ROOF, _ORIG_PARAPET
    _stamp_scales(lib, record)
    if "curtain_glass" not in lib:
        lib["curtain_glass"] = _curtain_glass("M_CurtainGlass", 0.04)
        lib["curtain_glass_lit"] = _curtain_glass("M_CurtainGlassLit", 0.45)
    _ORIG_FACADE = bb._facade
    _ORIG_WINDOW = bb._window
    _ORIG_ROOMS = realism.build_rooms
    _ORIG_ROOF = bb._roof
    _ORIG_PARAPET = bb._parapet
    bb.Mesh._uv = _uv_metres
    bb._facade = _city_facade
    bb._window = _city_window
    realism.build_rooms = _city_rooms
    # The leak decal reads as a dark cone stuck in the wall. City shots skip it.
    realism._streak_under = _no_streak
    bb._parapet = _tall_parapet
    bb._roof = _city_roof


def _shell(spec, keep_tall_rooms):
    """A glass wall slot is the clear shader. The mass and the spandrels need an opaque metal."""
    del keep_tall_rooms
    mats = dict(spec.get("materials") or {})
    if mats.get("wall") != "glass":
        return spec
    mats["wall"] = "metal"
    copy = dict(spec)
    copy["materials"] = mats
    return copy


def _mesh_list(specs, lib, col, keep_tall_rooms):
    made = []
    for index, spec in enumerate(specs):
        t0 = time.time()
        ob = bb.build_lod0(_shell(spec, keep_tall_rooms), lib, col)
        made.append(ob)
        print("MESH", spec.get("id"), "h", spec.get("height"), "tris", len(ob.data.polygons),
              "s", round(time.time() - t0, 1), flush=True)
        if index + 1 >= (CORE_MAX if not keep_tall_rooms else RES_MAX):
            break
    return made


def _bounds(specs, pad):
    xs, ys = [], []
    for spec in specs:
        for point in spec.get("footprint") or []:
            xs.append(float(point[0]))
            ys.append(float(point[1]))
    if not xs:
        return (0, 0, 1, 1)
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def _inside(point, bounds):
    return bounds[0] <= point[0] <= bounds[2] and bounds[1] <= point[1] <= bounds[3]


def _hit_x(a, b, x):
    dx = b[0] - a[0]
    t = 0.0 if abs(dx) < 1e-9 else (x - a[0]) / dx
    t = max(0.0, min(1.0, t))
    return (x, a[1] + (b[1] - a[1]) * t)


def _hit_y(a, b, y):
    dy = b[1] - a[1]
    t = 0.0 if abs(dy) < 1e-9 else (y - a[1]) / dy
    t = max(0.0, min(1.0, t))
    return (a[0] + (b[0] - a[0]) * t, y)


def _clip_polygon(poly, bounds):
    """Sutherland-Hodgman clip against an axis-aligned rectangle."""
    x0, y0, x1, y1 = bounds
    pts = [(float(p[0]), float(p[1])) for p in poly]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]

    def cut(pts, inside, hit):
        if not pts:
            return []
        out = []
        prev = pts[-1]
        prev_in = inside(prev)
        for cur in pts:
            cur_in = inside(cur)
            if cur_in:
                if not prev_in:
                    out.append(hit(prev, cur))
                out.append(cur)
            elif prev_in:
                out.append(hit(prev, cur))
            prev = cur
            prev_in = cur_in
        return out

    pts = cut(pts, lambda p: p[0] >= x0 - 1e-6, lambda a, b: _hit_x(a, b, x0))
    pts = cut(pts, lambda p: p[0] <= x1 + 1e-6, lambda a, b: _hit_x(a, b, x1))
    pts = cut(pts, lambda p: p[1] >= y0 - 1e-6, lambda a, b: _hit_y(a, b, y0))
    pts = cut(pts, lambda p: p[1] <= y1 + 1e-6, lambda a, b: _hit_y(a, b, y1))
    return pts


def _clip_chain(pts, bounds):
    """Open polyline clipped to the rectangle, as one chain per visit inside the box."""
    chains = []
    current = []
    points = [(float(p[0]), float(p[1])) for p in pts]
    for index, point in enumerate(points):
        inside = _inside(point, bounds)
        if index:
            prev = points[index - 1]
            if inside != _inside(prev, bounds):
                hit = _segment_enter(prev, point, bounds)
                if hit is not None:
                    current.append(hit)
            if not inside:
                if len(current) >= 2:
                    chains.append(current)
                current = []
        if inside:
            current.append(point)
    if len(current) >= 2:
        chains.append(current)
    return chains


def _segment_enter(a, b, bounds):
    x0, y0, x1, y1 = bounds
    dx, dy = b[0] - a[0], b[1] - a[1]
    hits = []
    if abs(dx) > 1e-9:
        for x in (x0, x1):
            t = (x - a[0]) / dx
            y = a[1] + dy * t
            if 0.0 <= t <= 1.0 and y0 - 1e-6 <= y <= y1 + 1e-6:
                hits.append((t, (x, y)))
    if abs(dy) > 1e-9:
        for y in (y0, y1):
            t = (y - a[1]) / dy
            x = a[0] + dx * t
            if 0.0 <= t <= 1.0 and x0 - 1e-6 <= x <= x1 + 1e-6:
                hits.append((t, (x, y)))
    if not hits:
        return None
    hits.sort(key=lambda item: item[0])
    return hits[0][1]


def _on_surface(city, x, y, kind):
    surfaces = ((city.get("streetscape") or {}).get("surfaces") or {}).get(kind) or []
    point = (float(x), float(y))
    for poly in surfaces:
        ring = [(float(p[0]), float(p[1])) for p in poly.get("polygon") or []]
        if len(ring) >= 3 and geom.point_in_poly(point, ring):
            return True
    return False


def _lot_pads(specs, lib, col, name):
    """A plinth under each wall, and a sidewalk band so the lot meets the facade."""
    plinth = bb.Mesh(name + "_Plinth")
    walk = bb.Mesh(name + "_Frontage")
    rise = profiles.CURB_RISE
    for spec in specs:
        ring = [(float(p[0]), float(p[1])) for p in spec.get("footprint") or []]
        if len(ring) < 3:
            continue
        plinth.prism(ring, 0.0, rise + 0.02, lib["concrete"])
        outer = geom.offset_polygon(ring, -0.45)
        if outer and abs(geom.poly_area(outer)) > abs(geom.poly_area(ring)) + 0.5:
            plinth.prism(outer, 0.0, rise + 0.01, lib["concrete"])
        for facade in spec.get("facades") or []:
            if int(facade.get("floor") or 0) != 0:
                continue
            a, b = facade.get("a"), facade.get("b")
            normal = facade.get("normal") or (0.0, 1.0)
            if not a or not b:
                continue
            width = 2.8
            nx, ny = float(normal[0]), float(normal[1])
            poly = [
                (float(a[0]), float(a[1])),
                (float(b[0]), float(b[1])),
                (float(b[0]) + nx * width, float(b[1]) + ny * width),
                (float(a[0]) + nx * width, float(a[1]) + ny * width),
            ]
            band = geom.ensure_ccw(poly)
            if abs(geom.poly_area(band)) < 0.4:
                continue
            walk.prism(band, 0.12, rise - 0.004, lib["paving"])
    made = []
    for mesh in (plinth, walk):
        if mesh.bm.faces:
            made.append(mesh.finish(col))
        else:
            mesh.bm.free()
    return made


def _camera_asphalt(city, cam, lib, col, tag):
    """Lay a carriageway under a street camera that is standing on the fill plane."""
    eye = cam["location"]
    target = cam["target"]
    dx, dy = target[0] - eye[0], target[1] - eye[1]
    length = math.hypot(dx, dy) or 1.0
    tx, ty = dx / length, dy / length
    samples = [(eye[0], eye[1])]
    for dist in (4.0, 9.0):
        samples.append((eye[0] + tx * dist, eye[1] + ty * dist))
    if all(_on_surface(city, x, y, "asphalt") or _on_surface(city, x, y, "sidewalk") for x, y in samples):
        print("STREET cam on plan", tag, flush=True)
        return []
    px, py = -ty, tx
    half = 8.0
    back, fwd = 12.0, max(6.0, min(length - 2.0, 26.0))

    def corner(along, side):
        return (eye[0] + tx * along + px * side, eye[1] + ty * along + py * side)

    ring = geom.ensure_ccw([
        corner(-back, -half), corner(fwd, -half), corner(fwd, half), corner(-back, half),
    ])
    mesh = bb.Mesh("CamStreet_" + tag)
    mesh.prism(ring, -0.01, 0.02, lib["asphalt"])
    print("STREET cam paved", tag, flush=True)
    return [mesh.finish(col)]


def _street(city, bounds, lib, protos, name, specs):
    col = bb.collection(name)
    made = []
    ground = bb.Mesh(name + "_Ground")
    # A concrete fill, level with the carriageway. Grass is only a planned parkway.
    x0, y0, x1, y1 = bounds[0] - 600, bounds[1] - 600, bounds[2] + 600, bounds[3] + 600
    ground.prism([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], -0.08, 0.0, lib["concrete"])
    made.append(ground.finish(col))
    made.extend(_lot_pads(specs, lib, col, name))
    sc = city.get("streetscape") or {}
    surfaces = sc.get("surfaces") or {}
    for kind, z0, z1, slot in (
        ("asphalt", -0.02, 0.012, "asphalt"),
        ("sidewalk", profiles.CURB_RISE - 0.04, profiles.CURB_RISE, "paving"),
        ("parkway", profiles.CURB_RISE - 0.04, profiles.CURB_RISE, "grass"),
        ("alley", profiles.CURB_RISE - 0.04, profiles.CURB_RISE, "asphalt"),
    ):
        mesh = bb.Mesh(name + "_" + kind)
        for index, poly in enumerate(surfaces.get(kind) or []):
            ring = _clip_polygon(poly.get("polygon") or [], bounds)
            if len(ring) >= 3:
                lift = 0.0012 * (index % 5) if kind == "asphalt" else 0.0
                mesh.prism(ring, z0 + lift, z1 + lift, lib[slot])
        if mesh.bm.faces:
            made.append(mesh.finish(col))
        else:
            mesh.bm.free()
    curbs = bb.Mesh(name + "_Curbs")
    for curb in sc.get("curb_paths") or []:
        for clipped in _clip_chain(curb.get("polyline") or [], bounds):
            piece = dict(curb)
            piece["polyline"] = clipped
            bb._sweep_curb(curbs, piece, sc.get("sections") or {}, lib["curb"])
    if curbs.bm.faces:
        made.append(curbs.finish(col))
    else:
        curbs.bm.free()
    paint = bb.Mesh(name + "_Paint")
    for cross in sc.get("crosswalks") or []:
        for mark in cross.get("marks") or []:
            ring = _clip_polygon(mark.get("polygon") or [], bounds)
            if len(ring) >= 3:
                paint.prism(ring, 0.03, 0.055, lib["lane"])
    for mark in sc.get("markings") or []:
        centre = geom.centroid([(float(p[0]), float(p[1])) for p in mark.get("polygon") or [(0, 0)]])
        if not _inside(centre, bounds):
            continue
        ring = mark.get("polygon") or []
        material = mark.get("material")
        if material == "M_Puddle":
            realism.uv_cover(paint, ring, 0.022, 0.032, lib["puddle"])
        elif material == "M_Manhole":
            realism.uv_cover(paint, ring, 0.02, 0.04, lib["manhole"])
        else:
            slot = lib["lane_yellow"] if material == "M_LanePaintYellow" else lib["lane"]
            paint.prism(ring, 0.028, 0.048, slot)
    if paint.bm.faces:
        made.append(paint.finish(col))
    else:
        paint.bm.free()
    ramps = bb.Mesh(name + "_Ramps")
    for ramp in sc.get("ramps") or []:
        if _inside((float(ramp.get("x") or 0), float(ramp.get("y") or 0)), bounds):
            bb._ramp(ramps, ramp, lib["concrete"])
    if ramps.bm.faces:
        made.append(ramps.finish(col))
    else:
        ramps.bm.free()
    props = []
    for prop in sc.get("props") or []:
        if prop.get("kind") not in DRESS:
            continue
        if _inside((float(prop.get("x") or 0), float(prop.get("y") or 0)), bounds):
            props.append(prop)
    made.extend(_place(props, protos, col, lib))
    print("STREET", name, "props", len(props), "meshes", len(made), flush=True)
    return made


def _place(props, protos, col, lib):
    made = []
    for prop in props:
        kind = prop.get("kind")
        if kind == "fence":
            style = prop.get("style") or "wood"
            src = protos.get("fence_iron" if style == "iron" else "fence_wood")
            yaw = math.radians(float(prop.get("yaw") or 0))
            z = profiles.CURB_RISE
        elif kind == "sign":
            src = protos.get("sign_" + (prop.get("label") or "CAFE"))
            yaw = bb._yaw_to_road(prop)
            z = profiles.CURB_RISE
        else:
            src = protos.get(kind)
            yaw = bb._yaw_to_road(prop)
            if kind == "drain":
                z = 0.02
            elif kind == "parked":
                z = 0.28
            else:
                z = profiles.CURB_RISE
        if src is None:
            continue
        ob = bpy.data.objects.new(str(prop.get("id") or kind)[:60], src.data)
        ob.location = (float(prop["x"]), float(prop["y"]), z)
        ob.rotation_euler = (0.0, 0.0, yaw)
        col.objects.link(ob)
        made.append(ob)
    wires = bb.Mesh("Wires")
    realism.wires(wires, props, lib["metal"])
    if wires.bm.faces:
        made.append(wires.finish(col))
    else:
        wires.bm.free()
    return made


def _longest_facade(spec):
    faces = spec.get("facades") or []
    return max(faces, key=lambda face: float(face.get("length") or 0))


def _inside_any(specs, x, y):
    for spec in specs:
        poly = [(float(p[0]), float(p[1])) for p in spec.get("footprint") or []]
        if len(poly) >= 3 and geom.point_in_poly((x, y), poly):
            return True
    return False


def _eye_outside(specs, origin, normal, other, dist):
    """A sidewalk eye: outside every footprint, looking toward the neighbour."""
    best = None
    for sign in (1.0, -1.0):
        n = (normal[0] * sign, normal[1] * sign)
        x, y = origin[0] + n[0] * dist, origin[1] + n[1] * dist
        for _ in range(14):
            if not _inside_any(specs, x, y):
                break
            x += n[0] * 8.0
            y += n[1] * 8.0
        if _inside_any(specs, x, y):
            continue
        view = (other[0] - x, other[1] - y)
        score = view[0] * n[0] + view[1] * n[1]
        if best is None or score > best[0]:
            best = (score, x, y, n[0], n[1])
    if best is None:
        return origin[0] + normal[0] * dist, origin[1] + normal[1] * dist, normal[0], normal[1]
    return best[1], best[2], best[3], best[4]


def _clear_of(specs, point, normal, start):
    """Step out along the facade normal until the eye is not inside a footprint."""
    x, y = point[0] + normal[0] * start, point[1] + normal[1] * start
    for _ in range(8):
        if not any(geom.point_in_poly((x, y), spec.get("footprint") or []) for spec in specs):
            return x, y
        x += normal[0] * 6.0
        y += normal[1] * 6.0
    return x, y


def _tower_side(specs):
    """A close view of the tallest tower's side, the face most perpendicular to its long front."""
    if not specs:
        return None
    tower = max(specs, key=lambda spec: float(spec.get("height") or 0))
    faces = [face for face in (tower.get("facades") or []) if int(face.get("floor") or 0) == 0]
    if len(faces) < 2:
        faces = list(tower.get("facades") or [])
    if not faces:
        return None
    longest = max(faces, key=lambda face: float(face.get("length") or 0))
    front = longest.get("normal") or (1.0, 0.0)

    def alignment(face):
        normal = face.get("normal") or (0.0, 1.0)
        return abs(float(normal[0]) * float(front[0]) + float(normal[1]) * float(front[1]))

    side = min(faces, key=alignment)
    ax, ay = float(side["a"][0]), float(side["a"][1])
    bx, by = float(side["b"][0]), float(side["b"][1])
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    nx, ny = float(side["normal"][0]), float(side["normal"][1])
    ex, ey = _clear_of(specs, (mx, my), (nx, ny), 12.0)
    height = float(tower.get("height") or 24.0)
    look_z = min(16.0, max(8.0, height * 0.18))
    eye = [round(ex, 2), round(ey, 2), 12.0]
    target = [round(mx, 2), round(my, 2), round(look_z, 2)]
    print("TOWER SIDE", tower.get("id"), "h", round(height, 1), "eye", eye, "target", target, flush=True)
    return {
        "location": eye,
        "target": target,
        "lens": 50,
        "fstop": 8.0,
        "sun": _sun_for(eye, target, 28),
    }


def _require_face_uvs():
    """Texel density and window aspect on every exported building. The build stops when either is off."""
    sink = face_uv.check_folder(OUT)
    print(face_uv.format_report(sink, 10), flush=True)
    if not face_uv.passed(sink):
        print("UV FAIL", flush=True)
        raise SystemExit(1)
    print("UV PASS", flush=True)


def _cameras_from_manifest():
    """The three shipped views. Relighting must not recompute them."""
    path = os.path.join(OUT, "city_manifest.json")
    if not os.path.isfile(path):
        return None
    with open(path) as handle:
        data = json.load(handle)
    cams = data.get("cameras") or {}
    needed = ("downtown_street", "aerial", "residential_street")
    if not all(key in cams for key in needed):
        return None
    return {key: cams[key] for key in needed}


def _sun_for(eye, target, elevation):
    """Key light from the camera side, so the facade in frame is the lit one."""
    dx, dy = target[0] - eye[0], target[1] - eye[1]
    # Sun direction in plan is (sin rot, cos rot). Match the view bearing.
    return {"elevation": elevation, "rotation": round(math.degrees(math.atan2(dx, dy)), 1), "strength": 1.0}


def _cameras(anchor, pair, core, residential):
    face = _longest_facade(anchor)
    ax, ay = float(face["a"][0]), float(face["a"][1])
    bx, by = float(face["b"][0]), float(face["b"][1])
    length = float(face.get("length") or 1.0) or 1.0
    tx, ty = (bx - ax) / length, (by - ay) / length
    nx, ny = float(face["normal"][0]), float(face["normal"][1])
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    ex, ey = _clear_of(core, (mx - tx * 8, my - ty * 8), (nx, ny), 14.0)
    street_eye = [round(ex, 2), round(ey, 2), 1.6]
    street_tgt = [round(mx + tx * 22, 2), round(my + ty * 22, 2), 4.2]
    street = {
        "location": street_eye,
        "target": street_tgt,
        "lens": 32,
        "fstop": 8.0,
        "sun": _sun_for(street_eye, street_tgt, 28),
    }
    centres = [_centre(spec) for spec in core]
    cx = sum(p[0] for p in centres) / len(centres)
    cy = sum(p[1] for p in centres) / len(centres)
    span = max(geom.dist((cx, cy), point) for point in centres) if centres else 80.0
    tall = max(float(spec.get("height") or 12) for spec in core) if core else 40.0
    back = max(110.0, span * 1.25)
    air_eye = [round(cx - back * 0.72, 2), round(cy - back * 0.58, 2), round(max(80.0, span * 0.55 + 28), 2)]
    air_tgt = [round(cx, 2), round(cy, 2), round(min(28.0, tall * 0.15), 2)]
    aerial = {
        "location": air_eye,
        "target": air_tgt,
        "lens": 35,
        "fstop": 0,
        "sun": _sun_for(air_eye, air_tgt, 32),
    }
    left, right = pair if pair else (None, None)
    if left is None:
        res = dict(street)
    else:
        ca, cb = _centre(left), _centre(right or left)
        mid = ((ca[0] + cb[0]) / 2.0, (ca[1] + cb[1]) / 2.0)
        dx, dy = cb[0] - ca[0], cb[1] - ca[1]
        span = math.hypot(dx, dy) or 1.0
        px, py = -dy / span, dx / span
        ex, ey = mid
        for sign in (1.0, -1.0):
            tx, ty = mid[0] + px * sign * 22.0, mid[1] + py * sign * 22.0
            if not _inside_any(residential, tx, ty):
                ex, ey = tx, ty
                break
        res_eye = [round(ex, 2), round(ey, 2), 1.7]
        res_tgt = [round(mid[0], 2), round(mid[1], 2), 4.0]
        print("RES CAM", res_eye, res_tgt, "tiers",
              left.get("lot_id"), right.get("lot_id") if right else None, flush=True)
        res = {
            "location": res_eye,
            "target": res_tgt,
            "lens": 24,
            "fstop": 8.0,
            "sun": _sun_for(res_eye, res_tgt, 34),
        }
    return {"downtown_street": street, "aerial": aerial, "residential_street": res}


def _grade_daylight(scene, exposure):
    """AgX at a daylight exposure. The block grade (Filmic, 0.15) crushed these frames."""
    try:
        scene.view_settings.view_transform = "AgX"
    except (TypeError, ValueError):
        scene.view_settings.view_transform = "Filmic"
    for look in ("None",):
        try:
            scene.view_settings.look = look
            break
        except (TypeError, ValueError):
            continue
    scene.view_settings.exposure = float(exposure)
    scene.view_settings.gamma = 1.0
    scene.cycles.volume_bounces = 0


def _hdr_path(record, key):
    rel = (realism._map(record, key) or {}).get("hdr")
    path = realism._abs(bb.ART, rel)
    if path and os.path.isfile(path):
        return path
    return None


def _light_city(world, sun_spec, dusk, record):
    """CC0 Poly Haven sky plus a sun. The environment vector stays unconnected.

    Generated coordinates turn the HDRI into a flat field, and the block volume
    blacks out a city-sized clip range. Nishita is only the fallback.
    """
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    key = "kiara_9_dusk" if dusk else "kloofendal_43d_clear_puresky"
    path = _hdr_path(record, key)
    if path:
        image = bpy.data.images.load(path, check_existing=True)
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = image
        nt.links.new(env.outputs["Color"], bg.inputs["Color"])
        print("SKY", os.path.basename(path), flush=True)
    else:
        sky = nt.nodes.new("ShaderNodeTexSky")
        sky.sky_type = "NISHITA"
        sky.sun_elevation = math.radians(float(sun_spec["elevation"]))
        sky.sun_rotation = math.radians(float(sun_spec["rotation"]))
        sky.sun_disc = True
        nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
        print("SKY nishita", sun_spec["elevation"], flush=True)
    bg.inputs["Strength"].default_value = 0.85 if dusk else 1.0
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    light_data = bpy.data.lights.get("Key") or bpy.data.lights.new("Key", "SUN")
    light = bpy.data.objects.get("Key")
    if light is None:
        light = bpy.data.objects.new("Key", light_data)
        bpy.context.scene.collection.objects.link(light)
    light.data.energy = 1.8 if dusk else 5.0
    light.data.angle = math.radians(2.2 if dusk else 0.6)
    light.data.color = (1.0, 0.55, 0.32) if dusk else (1.0, 0.96, 0.9)
    elev = math.radians(float(sun_spec["elevation"]))
    rot = math.radians(float(sun_spec["rotation"]))
    light.rotation_euler = (math.pi / 2.0 - elev, 0.0, rot)


def _glow(dusk):
    glass, interior = (4.0, 14.0) if dusk else (0.6, 1.2)
    curtain = 2.6 if dusk else 0.35
    for name, strength in (
        ("M_GlassLit", glass),
        ("M_InteriorLit", interior),
        ("M_CurtainGlass", 0.12 if dusk else 0.04),
        ("M_CurtainGlassLit", curtain),
    ):
        if name in bpy.data.materials:
            bb.set_emission(bpy.data.materials[name], strength)


def _png_luma(path):
    """Display-referred luma samples from an 8-bit PNG. Blender writes the view transform into it."""
    with open(path, "rb") as handle:
        if handle.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError("not a png: %s" % path)
        chunks = []
        width = height = color_type = None
        while True:
            size = struct.unpack(">I", handle.read(4))[0]
            kind = handle.read(4)
            data = handle.read(size)
            handle.read(4)
            if kind == b"IHDR":
                width, height, _depth, color_type = struct.unpack(">IIBB", data[:10])
            elif kind == b"IDAT":
                chunks.append(data)
            elif kind == b"IEND":
                break
    raw = zlib.decompress(b"".join(chunks))
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    stride = width * channels
    cursor = 0
    prev = bytearray(stride)
    samples = []

    def paeth(left, up, up_left):
        guess = left + up - up_left
        da, db, dc = abs(guess - left), abs(guess - up), abs(guess - up_left)
        if da <= db and da <= dc:
            return left
        return up if db <= dc else up_left

    for y in range(height):
        filt = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor:cursor + stride])
        cursor += stride
        for x in range(stride):
            left = row[x - channels] if x >= channels else 0
            up = prev[x]
            up_left = prev[x - channels] if x >= channels else 0
            if filt == 1:
                row[x] = (row[x] + left) & 255
            elif filt == 2:
                row[x] = (row[x] + up) & 255
            elif filt == 3:
                row[x] = (row[x] + ((left + up) // 2)) & 255
            elif filt == 4:
                row[x] = (row[x] + paeth(left, up, up_left)) & 255
            elif filt != 0:
                raise ValueError("png filter %s" % filt)
        prev = row
        if y % 2:
            continue
        for x in range(0, width, 4):
            offset = x * channels
            red = row[offset]
            green = row[offset + 1] if channels > 1 else red
            blue = row[offset + 2] if channels > 2 else red
            samples.append(0.2126 * red + 0.7152 * green + 0.0722 * blue)
    samples.sort()
    count = len(samples)
    crushed = sum(1 for value in samples if value < 12) / count
    mid = sum(1 for value in samples if 48 <= value <= 200) / count
    return {
        "median": samples[count // 2],
        "crushed": crushed,
        "mid": mid,
        "p95": samples[int(count * 0.95)],
        "mean": sum(samples) / count,
    }


def _midtones_ok(stats, dusk):
    """Daylight keeps a real midtone body. Dusk may be dimmer, but the sky and windows stay lit."""
    if dusk:
        return (stats["crushed"] < 0.55 and stats["median"] >= 30
                and stats["mid"] >= 0.18 and stats["p95"] >= 140)
    return stats["crushed"] < 0.45 and stats["median"] >= 55 and stats["mid"] >= 0.25


def _publish(path):
    if os.path.abspath(PREVIEWS) == os.path.abspath(REPO_PREVIEWS):
        return
    os.makedirs(PREVIEWS, exist_ok=True)
    shutil.copy2(path, os.path.join(PREVIEWS, os.path.basename(path)))


def _render(cams, core_obs, core_street, res_obs, res_street):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    samples = int(os.environ.get("SKYCITY_SAMPLES", "24"))
    scene.cycles.samples = max(16, min(32, samples))
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 6
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 2
    scene.cycles.transparent_max_bounces = 8
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("Sky_City")
    scene.world = world
    world.use_nodes = True
    record = bb.load_material_record()
    groups = {
        "aerial": core_obs + core_street,
        "downtown_street": core_obs + core_street,
        "residential_street": res_obs + res_street,
        "tower_side": core_obs + core_street,
    }
    shots = [
        ("aerial", False, "sky_city_downtown_aerial_day.png"),
        ("downtown_street", False, "sky_city_downtown_street_day.png"),
        ("residential_street", False, "sky_city_residential_street_day.png"),
        ("downtown_street", True, "sky_city_downtown_street_dusk.png"),
        ("tower_side", False, "sky_city_tower_side_day.png"),
    ]
    wanted = [item for item in os.environ.get("SKYCITY_SHOTS", "").split(",") if item]
    if wanted:
        shots = [shot for shot in shots
                 if shot[0] in wanted or ("%s_%s" % (shot[0], "dusk" if shot[1] else "day")) in wanted]
    everything = core_obs + core_street + res_obs + res_street
    for shot, dusk, name in shots:
        show = set(groups[shot])
        for ob in everything:
            ob.hide_render = ob not in show
        bb._look(cams[shot])
        scene.camera.data.clip_end = 2000.0
        sun = dict(cams[shot]["sun"])
        if dusk:
            sun["elevation"] = DUSK_ELEVATION
        _light_city(world, sun, dusk, record)
        _glow(dusk)
        exposure = DUSK_EXPOSURE if dusk else DAY_EXPOSURE
        dest = os.path.join(REPO_PREVIEWS, name)
        scene.render.filepath = dest
        passed = False
        for attempt in range(3):
            _grade_daylight(scene, exposure)
            t0 = time.time()
            bpy.ops.render.render(write_still=True)
            stats = _png_luma(dest)
            passed = _midtones_ok(stats, dusk)
            print("HIST", name, "exposure", round(exposure, 2),
                  "median", round(stats["median"], 1),
                  "crushed", round(stats["crushed"], 3),
                  "mid", round(stats["mid"], 3),
                  "p95", round(stats["p95"], 1),
                  "mean", round(stats["mean"], 1),
                  "PASS" if passed else "RETRY",
                  round(time.time() - t0, 1), flush=True)
            if passed or attempt == 2:
                break
            exposure += 0.7
        _publish(dest)
        if not passed:
            print("HIST FAIL", name, flush=True)


def _export_baked(path, objects):
    copies = []
    for ob in objects:
        copy = ob.copy()
        copy.data = ob.data.copy()
        bpy.context.scene.collection.objects.link(copy)
        copies.append(copy)
    pivot = bpy.data.objects.new("PivotBake", None)
    bpy.context.scene.collection.objects.link(pivot)
    pivot.rotation_euler = (0.0, 0.0, -math.pi / 2.0)
    for copy in copies:
        copy.parent = pivot
    bpy.context.view_layer.update()
    for copy in copies:
        world = copy.matrix_world.copy()
        copy.parent = None
        copy.matrix_world = world
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action="DESELECT")
    for copy in copies:
        copy.select_set(True)
    bpy.context.view_layer.objects.active = copies[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(copies) > 1:
        bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    bb._export(path, [joined])
    mesh = joined.data
    bpy.data.objects.remove(joined, do_unlink=True)
    if mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)
    bpy.data.objects.remove(pivot, do_unlink=True)
    return os.path.getsize(path)


def _pack(prefix, objects, labels, budget, ratio):
    """Group meshes into GLBs under FILE_CAP, stopping at the remaining budget."""
    files = []
    batch = []
    batch_labels = []
    batch_tris = 0
    spent = 0

    def flush():
        nonlocal batch, batch_labels, batch_tris, spent
        if not batch:
            return True
        path = os.path.join(OUT, "%s_%02d.glb" % (prefix, len(files)))
        size = _export_baked(path, batch)
        files.append({
            "file": os.path.basename(path),
            "bytes": size,
            "buildings": batch_labels,
        })
        spent += size
        print("EXPORT", os.path.basename(path), round(size / (1024 * 1024), 2), "MB", flush=True)
        batch = []
        batch_labels = []
        batch_tris = 0
        return spent < budget

    for ob, label in zip(objects, labels):
        tris = len(ob.data.polygons) if ob.data else 1
        estimate = tris * ratio
        if batch and (batch_tris * ratio + estimate > FILE_CAP):
            if not flush():
                return files, spent
        if spent >= budget:
            break
        if spent + estimate > budget and batch:
            if not flush():
                return files, spent
        if spent >= budget:
            break
        batch.append(ob)
        batch_labels.append(label)
        batch_tris += tris
    flush()
    return files, spent


def _export_all(core, core_obs, core_street, residential, res_obs, res_street):
    for name in os.listdir(OUT):
        if name.endswith(".glb"):
            os.remove(os.path.join(OUT, name))
    sample = core_obs[0] if core_obs else res_obs[0]
    probe = os.path.join(OUT, "_probe.glb")
    probe_size = _export_baked(probe, [sample])
    os.remove(probe)
    tris = max(1, len(sample.data.polygons))
    ratio = probe_size / float(tris)
    print("CITY bytes/tri", round(ratio, 2), flush=True)
    # Streets are small next to towers. Give buildings most of the budget.
    files, spent = _pack("CG_chicago_core", core_obs, [spec.get("id") for spec in core[:len(core_obs)]],
                         int(BUDGET * 0.72), ratio)
    more, more_spent = _pack("CG_austin_low", res_obs, [spec.get("id") for spec in residential[:len(res_obs)]],
                             int(BUDGET * 0.18), ratio)
    files.extend(more)
    spent += more_spent
    left = max(0, BUDGET - spent)
    street_files, street_spent = _pack("CG_chicago_core_street", core_street, ["street"] * len(core_street), left, ratio)
    files.extend(street_files)
    spent += street_spent
    left = max(0, BUDGET - spent)
    street_files, street_spent = _pack("CG_austin_low_street", res_street, ["street"] * len(res_street), left, ratio)
    files.extend(street_files)
    spent += street_spent
    return files, spent


if __name__ == "__main__":
    main()
