"""Weathering, window dress, street clutter and the graded sky for the block preview.

The city model stays the source of the props and the puddles. This module only
meshes and shades them. Scans stay out of the GLB: materials name their slots,
and Scripts/city/import_block_ue.py binds the JPGs.

CC0 overlays (cracked concrete, sparse grass, leak and asphalt-damage decals,
a manhole, two small HDRIs) are blended here. Signs are original bitmaps.
"""
import math
import os

import bpy

import profiles
import signs

DOOR_W = profiles.DOOR_W
DOOR_H = profiles.DOOR_H
STORE_SILL = profiles.STORE_SILL
STORE_HEAD = profiles.STORE_HEAD

CURTAINS = (
    ("M_CurtainRed", (0.45, 0.16, 0.14)),
    ("M_CurtainGreen", (0.16, 0.28, 0.22)),
    ("M_CurtainCream", (0.72, 0.66, 0.52)),
    ("M_CurtainBlue", (0.18, 0.24, 0.38)),
)
AWNINGS = (
    ("M_AwningRed", (0.42, 0.12, 0.12)),
    ("M_AwningGreen", (0.12, 0.28, 0.24)),
    ("M_AwningNavy", (0.12, 0.16, 0.28)),
    ("M_AwningCream", (0.78, 0.74, 0.64)),
)


def extend_library(lib, record, art):
    """Dress materials, decals and sign boards. Wall slots already exist."""
    lib["blind"] = _blind("M_Blind", (0.78, 0.76, 0.7), (0.42, 0.4, 0.36))
    lib["blind_warm"] = _blind("M_BlindWarm", (0.86, 0.78, 0.62), (0.5, 0.4, 0.28))
    for name, rgb in CURTAINS:
        lib[name] = _flat(name, rgb, 0.72)
    for name, rgb in AWNINGS:
        lib[name] = _flat(name, rgb, 0.55)
    lib["puddle"] = _flat("M_Puddle", (0.03, 0.03, 0.035), 0.06)
    _set_spec(lib["puddle"], 0.5)
    lib["wood"] = _flat("M_Wood", (0.28, 0.18, 0.1), 0.62)
    lib["counter"] = _flat("M_Counter", (0.32, 0.28, 0.24), 0.4)
    streak = _map(record, "Leaking006")
    crack = _map(record, "AsphaltDamage001")
    cover = _map(record, "ManholeCover009")
    lib["streak"] = _decal("M_Streak", art, streak, (0.25, 0.22, 0.18), 0.7)
    lib["crack"] = _decal("M_Crack", art, crack, (1.0, 1.0, 1.0), 0.85)
    lib["oil"] = _decal("M_Oil", art, streak, (0.04, 0.035, 0.03), 0.12)
    lib["manhole"] = _decal("M_Manhole", art, cover, (1.0, 1.0, 1.0), 0.55)
    sign_dir = os.path.join(art, "signs")
    signs.write(sign_dir)
    for word in signs.WORDS:
        path = os.path.join(sign_dir, "T_CG_Sign_%s.png" % word)
        lib["sign_" + word] = _image_mat("M_Sign" + word.title(), path, 0.5)
    _age_flat(lib["curb"], "curb")
    _age_flat(lib["lane"], "paint")
    for slot in ("brick", "concrete", "plaster", "metal", "asphalt", "paving", "grass"):
        if slot in lib:
            _age_textured(lib[slot], slot, record, art)


def prototypes(lib, mesh_cls):
    """Shared meshes for bins, grates, weeds and blade signs. Hidden; instances show."""
    import blender_street_kit as kit
    col = bpy.data.collections.get("Prototypes") or _collection("Prototypes")
    out = {
        "bin": _bin(lib, col, mesh_cls),
        "grate": _grate(lib, col, mesh_cls),
        "weed": _weed(kit, col, mesh_cls),
    }
    for word in signs.WORDS:
        out["sign_" + word] = _blade(lib["sign_" + word], lib["metal"], col, word, mesh_cls)
    return out


def scatter_decals(mesh, data, lib):
    """Cracks and oil on the carriageway. Positions come from the seed, not a new file."""
    import geom
    import streets
    seed = int(data.get("seed") or 1)
    for road in data.get("roads") or []:
        length = _length(road)
        if length < 12:
            continue
        s = 9.0
        n = 0
        while s < length - 6 and n < 8:
            if geom.rnd(seed, road["id"], n, "crack") < 0.8:
                lat = (geom.rnd(seed, road["id"], n, "crackx") - 0.5) * float(
                    (data.get("streetscape") or {}).get("sections", {}).get(road["id"], {}).get("width") or 8) * 0.5
                p, d = streets.point_on_road(road, s, lat)
                _card(mesh, p, d, 1.7, 1.15, 0.03, lib["crack"])
            if geom.rnd(seed, road["id"], n, "oil") < 0.45:
                p, d = streets.point_on_road(road, s + 2.2, (geom.rnd(seed, road["id"], n, "oily") - 0.5) * 3.0)
                _card(mesh, p, d, 1.3, 0.9, 0.032, lib["oil"])
            s += 11.0
            n += 1


def wires(mesh, props, metal):
    """A sagging span between lamps on the same side of a road."""
    groups = {}
    for prop in props:
        if prop.get("kind") != "lamp":
            continue
        groups.setdefault((prop.get("road_id"), prop.get("side")), []).append(prop)
    for items in groups.values():
        items.sort(key=lambda p: (p["x"], p["y"]))
        for a, b in zip(items, items[1:]):
            dx, dy = b["x"] - a["x"], b["y"] - a["y"]
            dist = math.hypot(dx, dy)
            if dist < 8 or dist > 42:
                continue
            segs = 4
            z = 6.4
            for i in range(segs):
                t0, t1 = i / segs, (i + 1) / segs
                sag0 = math.sin(t0 * math.pi) * 0.55
                sag1 = math.sin(t1 * math.pi) * 0.55
                p0 = (a["x"] + dx * t0, a["y"] + dy * t0, z - sag0)
                p1 = (a["x"] + dx * t1, a["y"] + dy * t1, z - sag1)
                _cable(mesh, p0, p1, metal)


def pedestrian_door(mesh, building, facade, bay, origin, tangent, inward, width, z0, head, lib):
    """A 0.91 by 2.10 m leaf centred in the bay, with wall around it and a transom."""
    import geom
    leaf_w = min(DOOR_W, max(0.7, width - 0.12))
    leaf_h = min(DOOR_H, max(1.8, head - z0 - 0.3))
    side = (width - leaf_w) / 2.0
    wall = _wall(lib, building)
    if side > 0.02:
        _span(mesh, origin, tangent, inward, side, 0.4, z0, head, wall)
        _span(mesh, _along(origin, tangent, side + leaf_w), tangent, inward, side, 0.4, z0, head, wall)
    _span(mesh, _along(origin, tangent, side), tangent, inward, leaf_w, 0.4, z0 + leaf_h, head, wall)
    # Lower leaf is solid. The upper part is glass, so the door is not a second wall.
    leaf_o = _along(origin, tangent, side)
    _span(mesh, leaf_o, tangent, inward, leaf_w, 0.12, z0, z0 + leaf_h * 0.62, lib["metal"])
    _plane(mesh, _along(leaf_o, tangent, leaf_w * 0.12), tangent, inward, leaf_w * 0.76,
           z0 + leaf_h * 0.62, z0 + leaf_h - 0.08, 0.08, lib["glass"])
    if head > z0 + leaf_h + 0.25:
        _window_pane(mesh, leaf_o, tangent, inward, leaf_w, z0 + leaf_h + 0.08, min(head, z0 + leaf_h + 0.7), 0.35, lib, lit=False)
    _streak_under(mesh, building, facade, bay, origin, tangent, inward, width, z0 + leaf_h, lib)


def dress_opening(mesh, building, facade, bay, origin, tangent, inward, width, z0, z1, depth, lib, kind):
    """Curtain or blind, a rare air conditioner, a leak decal, and a shop interior.

    When the bay belongs to a room, the curtain and the blind come from that room,
    so every window of a corner unit or an office matches. The shop shell is one
    volume in build_rooms, not a box behind each pane.
    """
    import geom
    import grammar
    seed = int(building.get("seed") or 1)
    bid = building["id"]
    floor = int(facade.get("floor") or 0)
    room = grammar.room_of(building, facade, bay)
    if kind == "storefront" and room is None:
        _shop(mesh, building, facade, bay, origin, tangent, inward, width, z0, z1, lib)
        return
    if kind == "door":
        return
    if room is not None:
        _dress_room(mesh, room, origin, tangent, inward, width, z0, z1, depth, lib, kind)
    else:
        roll = geom.rnd(seed, bid, floor, bay, "dress")
        if roll < 0.28:
            mat = lib["blind_warm"] if geom.rnd(seed, bid, floor, bay, "blind") < 0.5 else lib["blind"]
            _plane(mesh, origin, tangent, inward, width * 0.92, z0 + 0.05, z1 - 0.05, depth * 0.55, mat)
        elif roll < 0.62:
            name, _rgb = CURTAINS[int(geom.rnd(seed, bid, floor, bay, "curtain") * len(CURTAINS)) % len(CURTAINS)]
            frac = 0.34 + 0.28 * geom.rnd(seed, bid, floor, bay, "curtainw")
            side = 0.0 if geom.rnd(seed, bid, floor, bay, "curtainside") < 0.5 else width * (1.0 - frac)
            _plane(mesh, _along(origin, tangent, side), tangent, inward, width * frac, z0 + 0.04, z1 - 0.04, depth * 0.5, lib[name])
    if floor > 0 and kind in ("window", "narrow") and geom.rnd(seed, bid, floor, bay, "ac") < 0.22:
        _ac(mesh, origin, tangent, inward, width, z0, lib["metal"])
    if kind != "storefront" and geom.rnd(seed, bid, floor, bay, "streak") < 0.42:
        _streak_under(mesh, building, facade, bay, origin, tangent, inward, width, z0, lib)


def _dress_room(mesh, room, origin, tangent, inward, width, z0, z1, depth, lib, kind):
    """The same curtain, colour, side and width on every window of the room."""
    if kind == "door":
        return
    curtain = room.get("curtain") or "none"
    if curtain == "none":
        return
    if curtain == "blind":
        mat = lib["blind_warm"] if room.get("blind_warm") else lib["blind"]
        _plane(mesh, origin, tangent, inward, width * 0.92, z0 + 0.05, z1 - 0.05, depth * 0.55, mat)
        return
    names = {"red": "M_CurtainRed", "green": "M_CurtainGreen", "cream": "M_CurtainCream", "blue": "M_CurtainBlue"}
    name = names.get(curtain)
    if not name or name not in lib:
        return
    frac = max(0.2, min(0.7, float(room.get("curtain_frac") or 0.45)))
    side = room.get("curtain_side") or "left"
    if side == "both":
        leaf = width * frac * 0.5
        _plane(mesh, origin, tangent, inward, leaf, z0 + 0.04, z1 - 0.04, depth * 0.5, lib[name])
        _plane(mesh, _along(origin, tangent, width - leaf), tangent, inward, leaf, z0 + 0.04, z1 - 0.04, depth * 0.5, lib[name])
    elif side == "right":
        _plane(mesh, _along(origin, tangent, width * (1.0 - frac)), tangent, inward, width * frac,
               z0 + 0.04, z1 - 0.04, depth * 0.5, lib[name])
    else:
        _plane(mesh, origin, tangent, inward, width * frac, z0 + 0.04, z1 - 0.04, depth * 0.5, lib[name])


def build_rooms(mesh, building, lib):
    """One shell per room: floor, ceiling, interior partitions, one lamp.

    An edge of the room that lies on the floor footprint is the exterior wall.
    The facade shell and the glass are that opening, so no partition is built
    there. An open office therefore has no interior walls, and a window sees
    the far window. Partition windows between rooms are not built.
    """
    import geom
    floors = list(building.get("floors") or [])
    wall = _wall(lib, building)
    wood = lib.get("wood", lib.get("plaster"))
    plaster = lib.get("plaster", wall)
    for room in building.get("rooms") or []:
        poly = room.get("polygon") or []
        if len(poly) < 3:
            continue
        floor_i = int(room.get("floor") or 0)
        floor_poly = (floors[floor_i].get("polygon") if floor_i < len(floors) else None) or building.get("footprint") or []
        base = float(room.get("z") or 0.0) + profiles.CURB_RISE
        height = float(room.get("h") or 3.0)
        z0 = base + 0.06
        z1 = base + height - 0.30
        if z1 <= z0 + 0.4:
            z1 = z0 + 0.4
        slab = wood if room.get("kind") in ("storefront", "lobby") else lib.get("interior", plaster)
        _slab(mesh, poly, z0, slab)
        _slab(mesh, poly, z1, plaster)
        _room_walls(mesh, poly, floor_poly, z0, z1, wall)
        if room.get("lit"):
            centre = geom.centroid([(float(p[0]), float(p[1])) for p in poly])
            mesh.box((centre[0], centre[1], z1 - 0.22), (1, 0, 0), (0, 1, 0), (0, 0, 1),
                     (0.42, 0.42, 0.12), lib["interior_lit"])
        if room.get("kind") == "storefront":
            _counter(mesh, poly, floor_poly, z0, lib.get("counter", plaster))


def _slab(mesh, poly, z, mat):
    """Plan projection. U and V are world metres over the same repeat, so a long room is not stretched."""
    top = [(float(p[0]), float(p[1]), z) for p in poly]
    mu, mv = _repeat(mat)
    uvs = [(p[0] / mu, p[1] / mv) for p in top]
    mesh.face(top, mat, uvs)
    mesh.face([(p[0], p[1], z - 0.02) for p in reversed(top)], mat, list(reversed(uvs)))


def _room_walls(mesh, poly, floor_poly, z0, z1, mat):
    n = len(poly)
    for i in range(n):
        a = (float(poly[i][0]), float(poly[i][1]))
        b = (float(poly[(i + 1) % n][0]), float(poly[(i + 1) % n][1]))
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        if _near_boundary(mid, floor_poly, 0.4):
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 0.15:
            continue
        tx, ty = dx / length, dy / length
        ix, iy = -dy / length, dx / length
        thick = 0.08
        centre = ((a[0] + b[0]) / 2.0 + ix * thick / 2.0,
                  (a[1] + b[1]) / 2.0 + iy * thick / 2.0,
                  (z0 + z1) / 2.0)
        mesh.box(centre, (tx, ty, 0), (ix, iy, 0), (0, 0, 1), (length, thick, z1 - z0), mat)


def _counter(mesh, poly, floor_poly, z0, mat):
    """One counter on the longest exterior edge of a shop, shared by its windows."""
    best = None
    n = len(poly)
    for i in range(n):
        a = (float(poly[i][0]), float(poly[i][1]))
        b = (float(poly[(i + 1) % n][0]), float(poly[(i + 1) % n][1]))
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        if not _near_boundary(mid, floor_poly, 0.45):
            continue
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if best is None or length > best[0]:
            best = (length, a, b)
    if best is None or best[0] < 0.8:
        return
    length, a, b = best
    dx, dy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    ix, iy = -dy, dx
    span = length * 0.62
    start = (length - span) / 2.0
    origin = (a[0] + dx * start + ix * 0.55, a[1] + dy * start + iy * 0.55)
    _span(mesh, origin, (dx, dy, 0), (ix, iy, 0), span, 0.55, z0, z0 + 0.95, mat)


def _near_boundary(point, poly, tol):
    if not poly or len(poly) < 2:
        return False
    n = len(poly)
    for i in range(n):
        a = (float(poly[i][0]), float(poly[i][1]))
        b = (float(poly[(i + 1) % n][0]), float(poly[(i + 1) % n][1]))
        if _dist_to_seg(point, a, b) <= tol:
            return True
    return False


def _dist_to_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    if length2 < 1e-10:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
    return math.hypot(p[0] - (a[0] + dx * t), p[1] - (a[1] + dy * t))


def shop_band(mesh, building, facade, bay, origin, tangent, inward, width, z0, z1, lib):
    """Awning and a sign in the band above a shopfront."""
    import geom
    seed = int(building.get("seed") or 1)
    word = signs.WORDS[int(geom.rnd(seed, building["id"], int(facade.get("floor") or 0), bay, "sign") * len(signs.WORDS)) % len(signs.WORDS)]
    board_h = 0.46
    board_z = z1 + 0.08
    _plane(mesh, _along(origin, tangent, width * 0.12), tangent, inward, width * 0.76, board_z, board_z + board_h, -0.04, lib.get("sign_" + word, lib["plaster"]))
    if geom.rnd(seed, building["id"], bay, "awning") < 0.72:
        name = AWNINGS[int(geom.rnd(seed, building["id"], bay, "awningc") * len(AWNINGS)) % len(AWNINGS)][0]
        _awning(mesh, origin, tangent, inward, width * 0.92, z1 - 0.02, lib[name])


def uv_cover(mesh, poly, z0, z1, mat):
    """A thin plate whose top uses the whole texture, for a manhole or a puddle."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    spanx = (maxx - minx) or 1.0
    spany = (maxy - miny) or 1.0

    def uv(p):
        return ((p[0] - minx) / spanx, (p[1] - miny) / spany)

    top = [(p[0], p[1], z1) for p in poly]
    mesh.face(top, mat, [uv(p) for p in poly])
    mesh.face([(p[0], p[1], z0) for p in reversed(poly)], mat, [uv(p) for p in reversed(poly)])


def sky(world, sun_spec, dusk, record, art):
    """HDRI plus a sun. Dusk swaps the sky. A light volume is the aerial haze."""
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    key = "kiara_9_dusk" if dusk else "kloofendal_43d_clear_puresky"
    path = _abs(art, (_map(record, key) or {}).get("hdr"))
    if path and os.path.isfile(path):
        img = bpy.data.images.load(path, check_existing=True)
        env.image = img
        mapping = nt.nodes.new("ShaderNodeMapping")
        coord = nt.nodes.new("ShaderNodeTexCoord")
        mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(float(sun_spec.get("rotation") or 0)))
        nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
        nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    else:
        sky = nt.nodes.new("ShaderNodeTexSky")
        sky.sky_type = "NISHITA"
        sky.sun_elevation = math.radians(float(sun_spec["elevation"]))
        sky.sun_rotation = math.radians(float(sun_spec["rotation"]))
        sky.sun_disc = True
        nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.45 if dusk else 0.9
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = 0.0045 if dusk else 0.0032
    vol.inputs["Anisotropy"].default_value = 0.35
    vol.inputs["Color"].default_value = (0.55, 0.45, 0.38, 1) if dusk else (0.62, 0.7, 0.8, 1)
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    light_data = bpy.data.lights.get("Key") or bpy.data.lights.new("Key", "SUN")
    light = bpy.data.objects.get("Key")
    if light is None:
        light = bpy.data.objects.new("Key", light_data)
        bpy.context.scene.collection.objects.link(light)
    light.data.energy = 1.4 if dusk else 3.2
    light.data.angle = math.radians(2.2 if dusk else 0.8)
    light.data.color = (1.0, 0.5, 0.28) if dusk else (1.0, 0.96, 0.9)
    elev = math.radians(float(sun_spec["elevation"]))
    rot = math.radians(float(sun_spec["rotation"]))
    light.rotation_euler = (math.pi / 2.0 - elev, 0.0, rot)


def grade(scene):
    """Filmic, a slightly lifted exposure, and a little depth of field on the street."""
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium Contrast"
    scene.view_settings.exposure = 0.15
    scene.view_settings.gamma = 1.0
    scene.cycles.volume_bounces = 0
    try:
        scene.cycles.volume_step_rate = 2.0
    except (AttributeError, TypeError):
        pass


def focus(cam, spec):
    fstop = float(spec.get("fstop") or 0)
    loc = spec["location"]
    tgt = spec["target"]
    dist = math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(loc, tgt)))
    cam.data.dof.use_dof = fstop > 0.5
    if cam.data.dof.use_dof:
        cam.data.dof.focus_distance = max(2.0, dist)
        cam.data.dof.aperture_fstop = fstop


def _shop(mesh, building, facade, bay, origin, tangent, inward, width, z0, z1, lib):
    """A mapped room behind the glass: floor, walls, a counter, one hanging lamp."""
    import geom
    depth = 2.4
    wall = _wall(lib, building)
    # Floor and ceiling run back into the building (along inward).
    _floor(mesh, origin, tangent, inward, width, z0 + 0.04, depth, lib["wood"])
    _floor(mesh, origin, tangent, inward, width, z1 - 0.06, depth, lib["plaster"])
    back = _shift(origin, inward, depth)
    _span(mesh, back, tangent, inward, width, 0.08, z0, z1, wall)
    _span(mesh, origin, tangent, inward, 0.08, depth, z0, z1, wall)
    _span(mesh, _along(origin, tangent, width - 0.08), tangent, inward, 0.08, depth, z0, z1, wall)
    counter_w = width * 0.62
    c_o = _along(_shift(origin, inward, 0.7), tangent, (width - counter_w) / 2.0)
    _span(mesh, c_o, tangent, inward, counter_w, 0.55, z0, z0 + 0.95, lib["counter"])
    seed = int(building.get("seed") or 1)
    if geom.rnd(seed, building["id"], bay, "shoplight") < 0.8:
        lamp_c = (
            origin[0] + tangent[0] * width * 0.5 + inward[0] * 1.1,
            origin[1] + tangent[1] * width * 0.5 + inward[1] * 1.1,
            z1 - 0.28,
        )
        mesh.box(lamp_c, tangent, inward, (0, 0, 1), (0.35, 0.35, 0.12), lib["interior_lit"])
    _awning_and_sign = None  # signs are placed by shop_band
    return _awning_and_sign


def _ac(mesh, origin, tangent, inward, width, z0, metal):
    w = min(0.72, width * 0.7)
    o = _along(origin, tangent, (width - w) / 2.0)
    centre = (
        o[0] + tangent[0] * w / 2.0 - inward[0] * 0.22,
        o[1] + tangent[1] * w / 2.0 - inward[1] * 0.22,
        z0 - 0.22,
    )
    mesh.box(centre, tangent, inward, (0, 0, 1), (w, 0.38, 0.32), metal)


def _streak_under(mesh, building, facade, bay, origin, tangent, inward, width, z0, lib):
    import geom
    h = 0.55 + 0.7 * geom.rnd(int(building.get("seed") or 1), building["id"], int(facade.get("floor") or 0), bay, "streakh")
    w = max(0.28, width * 0.42)
    o = _along(origin, tangent, (width - w) / 2.0)
    _plane(mesh, o, tangent, inward, w, z0 - h, z0 - 0.02, -0.03, lib["streak"])


def _awning(mesh, origin, tangent, inward, width, z, mat):
    """A short slope out from the shop head. Outward is the opposite of inward."""
    run = 0.85
    drop = 0.32
    a = _shift(origin, inward, -0.02)
    b = _along(a, tangent, width)
    c = (b[0] - inward[0] * run, b[1] - inward[1] * run)
    d = (a[0] - inward[0] * run, a[1] - inward[1] * run)
    top = [(a[0], a[1], z), (b[0], b[1], z), (c[0], c[1], z - drop), (d[0], d[1], z - drop)]
    mesh.face(top, mat, [(0, 0), (1, 0), (1, 1), (0, 1)])
    mesh.face([(p[0], p[1], p[2] - 0.03) for p in reversed(top)], mat, [(0, 0), (1, 0), (1, 1), (0, 1)])


def _repeat(mat):
    """Metres per repeat on U and V. One number when the slot only stored uv_m."""
    mu, mv = 1.0, 1.0
    try:
        keys = mat.keys() if mat is not None else ()
        if "meters_u" in keys:
            mu = float(mat["meters_u"] or 1.0)
            mv = float(mat["meters_v"] or mu) if "meters_v" in keys else mu
        else:
            raw = mat.get("uv_m") if mat is not None and hasattr(mat, "get") else 1.0
            if isinstance(raw, (list, tuple)):
                mu = float(raw[0] or 1.0)
                mv = float(raw[1] if len(raw) > 1 else raw[0] or mu)
            else:
                mu = mv = float(raw or 1.0)
    except (AttributeError, TypeError, ValueError):
        mu, mv = 1.0, 1.0
    if mu < 1e-4:
        mu = 1.0
    if mv < 1e-4:
        mv = mu
    return mu, mv


def _floor(mesh, origin, tangent, inward, width, z, depth, mat):
    a = origin
    b = _along(origin, tangent, width)
    c = _shift(b, inward, depth)
    d = _shift(a, inward, depth)
    # The quad's own width and depth. A 0-1 map would stretch a long room.
    mesh.face(
        [(a[0], a[1], z), (b[0], b[1], z), (c[0], c[1], z), (d[0], d[1], z)],
        mat, mesh._uv(width, depth, mat),
    )


def _plane(mesh, origin, tangent, inward, width, z0, z1, depth, mat):
    if z1 <= z0 + 0.02 or width < 0.08:
        return
    o = _shift(origin, inward, depth)
    a = (o[0], o[1], z0)
    b = (o[0] + tangent[0] * width, o[1] + tangent[1] * width, z0)
    c = (b[0], b[1], z1)
    d = (a[0], a[1], z1)
    mesh.face([a, b, c, d], mat, [(0, 0), (1, 0), (1, 1), (0, 1)])
    # The other side, a few millimetres back, so a one-sided face still reads from the street.
    back = _shift(o, inward, 0.008)
    ba = (back[0], back[1], z0)
    bb = (back[0] + tangent[0] * width, back[1] + tangent[1] * width, z0)
    bc = (bb[0], bb[1], z1)
    bd = (ba[0], ba[1], z1)
    mesh.face([ba, bd, bc, bb], mat, [(0, 0), (0, 1), (1, 1), (1, 0)])


def _window_pane(mesh, origin, tangent, inward, width, z0, z1, depth, lib, lit):
    _plane(mesh, origin, tangent, inward, width, z0, z1, depth, lib["glass_lit"] if lit else lib["glass"])


def _span(mesh, origin, tangent, inward, length, thick, z0, z1, mat):
    if length <= 0.02 or z1 <= z0 + 0.01:
        return
    centre = (origin[0] + tangent[0] * length / 2.0 + inward[0] * thick / 2.0,
              origin[1] + tangent[1] * length / 2.0 + inward[1] * thick / 2.0,
              (z0 + z1) / 2.0)
    mesh.box(centre, tangent, inward, (0, 0, 1), (length, thick, z1 - z0), mat)


def _wall(lib, building):
    return lib.get(building.get("materials", {}).get("wall") or "brick", lib["brick"])


def _along(origin, tangent, dist):
    return (origin[0] + tangent[0] * dist, origin[1] + tangent[1] * dist)


def _shift(origin, inward, dist):
    return (origin[0] + inward[0] * dist, origin[1] + inward[1] * dist)


def _card(mesh, p, d, along, across, z, mat):
    t = (d[0], d[1])
    n = (-t[1], t[0])
    ha, hc = along / 2.0, across / 2.0
    poly = []
    for sa, sc in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        poly.append((p[0] + t[0] * sa * ha + n[0] * sc * hc, p[1] + t[1] * sa * ha + n[1] * sc * hc))
    uv_cover(mesh, poly, z - 0.01, z, mat)


def _cable(mesh, a, b, mat):
    d = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    length = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2) or 1e-4
    tangent = (d[0] / length, d[1] / length, d[2] / length)
    up = (0, 0, 1)
    side = (
        tangent[1] * up[2] - tangent[2] * up[1],
        tangent[2] * up[0] - tangent[0] * up[2],
        tangent[0] * up[1] - tangent[1] * up[0],
    )
    centre = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0)
    mesh.box(centre, tangent, side, up, (length, 0.02, 0.02), mat)


def _bin(lib, col, mesh_cls):
    B = mesh_cls("Bin")
    body = lib["metal"]
    B.box((0, 0, 0.48), (1, 0, 0), (0, 1, 0), (0, 0, 1), (0.58, 0.5, 0.9), body)
    B.box((0, 0, 0.96), (1, 0, 0), (0, 1, 0), (0, 0, 1), (0.62, 0.54, 0.06), lib["trim_dark"])
    ob = B.finish(col)
    ob.hide_render = True
    ob.hide_set(True)
    return ob


def _grate(lib, col, mesh_cls):
    B = mesh_cls("Grate")
    iron = lib["metal"]
    s = 1.4
    t = 0.07
    z = 0.02
    B.box((0, 0, z), (1, 0, 0), (0, 1, 0), (0, 0, 1), (s, t, 0.04), iron)
    B.box((0, 0, z), (1, 0, 0), (0, 1, 0), (0, 0, 1), (t, s, 0.04), iron)
    B.box((0, s / 2 - t / 2, z), (1, 0, 0), (0, 1, 0), (0, 0, 1), (s, t, 0.04), iron)
    B.box((0, -s / 2 + t / 2, z), (1, 0, 0), (0, 1, 0), (0, 0, 1), (s, t, 0.04), iron)
    B.box((s / 2 - t / 2, 0, z), (1, 0, 0), (0, 1, 0), (0, 0, 1), (t, s, 0.04), iron)
    B.box((-s / 2 + t / 2, 0, z), (1, 0, 0), (0, 1, 0), (0, 0, 1), (t, s, 0.04), iron)
    for i in (-0.32, 0.0, 0.32):
        B.box((i, 0, z), (1, 0, 0), (0, 1, 0), (0, 0, 1), (t * 0.7, s - 2 * t, 0.03), iron)
        B.box((0, i, z), (1, 0, 0), (0, 1, 0), (0, 0, 1), (s - 2 * t, t * 0.7, 0.03), iron)
    ob = B.finish(col)
    ob.hide_render = True
    ob.hide_set(True)
    return ob


def _weed(kit, col, mesh_cls):
    B = mesh_cls("Weed")
    leaf = kit.mat("M_Leaves_linden", (0.2, 0.35, 0.12), 0.0, 0.6)
    kit.bind_cluster(leaf)
    for yaw in (0.0, 1.1, 2.2):
        c, s = math.cos(yaw), math.sin(yaw)
        B.face(
            [(0, 0, 0.02), (c * 0.28, s * 0.28, 0.05), (c * 0.22, s * 0.22, 0.42), (0, 0, 0.36)],
            leaf, [(0, 0), (1, 0), (1, 1), (0, 1)],
        )
    ob = B.finish(col)
    ob.hide_render = True
    ob.hide_set(True)
    return ob


def _blade(sign_mat, metal, col, word, mesh_cls):
    B = mesh_cls("Sign" + word.title())
    B.box((0, 0, 1.3), (1, 0, 0), (0, 1, 0), (0, 0, 1), (0.08, 0.08, 2.6), metal)
    B.box((0.55, 0, 2.35), (1, 0, 0), (0, 1, 0), (0, 0, 1), (0.9, 0.04, 0.36), sign_mat)
    ob = B.finish(col)
    ob.hide_render = True
    ob.hide_set(True)
    return ob


def _collection(name):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def _flat(name, rgb, rough):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Roughness"].default_value = rough
    return mat


def _set_spec(mat, value):
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    for name in ("Specular IOR Level", "Specular"):
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = value
            return


def _blind(name, light, dark):
    """Slats follow the pane's own UV. Generated coordinates used the whole building and stretched the stripes."""
    mat = _flat(name, light, 0.55)
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Y"
    wave.inputs["Scale"].default_value = 22.0
    nt.links.new(coord.outputs["UV"], wave.inputs["Vector"])
    mix = _mix(nt)
    mix.inputs[0].default_value = 1.0
    nt.links.new(wave.outputs["Fac"], mix.inputs[0])
    mix.inputs[6].default_value = (*light, 1)
    mix.inputs[7].default_value = (*dark, 1)
    _relink(nt, bsdf.inputs["Base Color"], mix.outputs[2])
    return mat


def _image_mat(name, path, rough):
    mat = _flat(name, (0.2, 0.2, 0.22), rough)
    if not os.path.isfile(path):
        return mat
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path, check_existing=True)
    _relink(nt, bsdf.inputs["Base Color"], tex.outputs["Color"])
    return mat


def _decal(name, art, maps, tint, rough):
    mat = _flat(name, tint, rough)
    color = _abs(art, (maps or {}).get("color"))
    if not color:
        return mat
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(color, check_existing=True)
    mix = _mix(nt, "MULTIPLY")
    mix.inputs[0].default_value = 1.0
    nt.links.new(tex.outputs["Color"], mix.inputs[6])
    mix.inputs[7].default_value = (*tint, 1)
    _relink(nt, bsdf.inputs["Base Color"], mix.outputs[2])
    opacity = _abs(art, (maps or {}).get("opacity"))
    if opacity:
        op = nt.nodes.new("ShaderNodeTexImage")
        img = bpy.data.images.load(opacity, check_existing=True)
        try:
            img.colorspace_settings.name = "Non-Color"
        except TypeError:
            pass
        op.image = img
        nt.links.new(op.outputs["Color"], bsdf.inputs["Alpha"])
        try:
            mat.blend_method = "HASHED"
        except TypeError:
            pass
    return mat


def _age_textured(mat, slot, record, art):
    """Grime, base splash, streaks, edge wear, and a little per-face colour jitter."""
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if bsdf is None:
        return
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    color_out = _socket_source(nt, bsdf.inputs["Base Color"])
    # Per-island hue, small enough that a pier does not change material.
    hue = nt.nodes.new("ShaderNodeHueSaturation")
    hue.inputs["Saturation"].default_value = 0.92
    ramp = nt.nodes.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value = 0.0
    ramp.inputs["From Max"].default_value = 1.0
    ramp.inputs["To Min"].default_value = 0.47
    ramp.inputs["To Max"].default_value = 0.53
    nt.links.new(geo.outputs["Random Per Island"], ramp.inputs["Value"])
    nt.links.new(ramp.outputs["Result"], hue.inputs["Hue"])
    if color_out is not None:
        nt.links.new(color_out, hue.inputs["Color"])
    else:
        hue.inputs["Color"].default_value = bsdf.inputs["Base Color"].default_value
    current = hue.outputs["Color"]
    grime_rel = (_map(record, "cracked_concrete_wall") or {}).get("color")
    if slot != "grass" and grime_rel:
        current = _multiply_image(nt, current, _abs(art, grime_rel), 0.34 if slot in ("brick", "concrete", "plaster", "paving") else 0.22, 0.18)
    if slot == "grass":
        grass = (_map(record, "sparse_grass") or {}).get("color")
        if grass:
            current = _mix_image(nt, current, _abs(art, grass), 0.5, 0.22)
        current = _splash(nt, geo, current, 0.45)
    elif slot == "asphalt":
        current = _asphalt_wear(nt, geo, current)
    elif slot in ("brick", "concrete", "plaster", "metal", "paving"):
        current = _splash(nt, geo, current, 0.62)
        current = _streaks(nt, geo, current)
        current = _edges(nt, geo, current)
    _relink(nt, bsdf.inputs["Base Color"], current)
    _rough_jitter(nt, bsdf, geo)


def _age_flat(mat, kind):
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    if kind == "paint":
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 4.0
        mix = _mix(nt)
        nt.links.new(noise.outputs["Fac"], mix.inputs[0])
        mix.inputs[6].default_value = bsdf.inputs["Base Color"].default_value
        mix.inputs[7].default_value = (0.72, 0.72, 0.68, 1)
        # Keep the bars white. The noise only knocks the brightness down a little.
        scale = nt.nodes.new("ShaderNodeMath")
        scale.operation = "MULTIPLY"
        scale.inputs[1].default_value = 0.28
        nt.links.new(noise.outputs["Fac"], scale.inputs[0])
        nt.links.new(scale.outputs["Value"], mix.inputs[0])
        _relink(nt, bsdf.inputs["Base Color"], mix.outputs[2])
    elif kind == "curb":
        current = _splash(nt, geo, None, 0.4, default=(0.78, 0.76, 0.72, 1))
        _relink(nt, bsdf.inputs["Base Color"], current)


def _multiply_image(nt, color_socket, path, factor, scale):
    if not path or not os.path.isfile(path):
        return color_socket
    tex, _mapping = _object_image(nt, path, scale)
    mix = _mix(nt, "MULTIPLY")
    mix.inputs[0].default_value = factor
    nt.links.new(color_socket, mix.inputs[6])
    nt.links.new(tex.outputs["Color"], mix.inputs[7])
    return mix.outputs[2]


def _mix_image(nt, color_socket, path, factor, scale):
    if not path or not os.path.isfile(path):
        return color_socket
    tex, _mapping = _object_image(nt, path, scale)
    mix = _mix(nt)
    mix.inputs[0].default_value = factor
    nt.links.new(color_socket, mix.inputs[6])
    nt.links.new(tex.outputs["Color"], mix.inputs[7])
    return mix.outputs[2]


def _object_image(nt, path, scale):
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path, check_existing=True)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (scale, scale, scale)
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    return tex, mapping


def _splash(nt, geo, color_socket, strength, default=None):
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sep.inputs["Vector"])
    band = nt.nodes.new("ShaderNodeMapRange")
    band.inputs["From Min"].default_value = 0.15
    band.inputs["From Max"].default_value = 1.35
    band.inputs["To Min"].default_value = 1.0
    band.inputs["To Max"].default_value = 0.0
    nt.links.new(sep.outputs["Z"], band.inputs["Value"])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.4
    nt.links.new(geo.outputs["Position"], noise.inputs["Vector"])
    fac = nt.nodes.new("ShaderNodeMath")
    fac.operation = "MULTIPLY"
    nt.links.new(band.outputs["Result"], fac.inputs[0])
    nt.links.new(noise.outputs["Fac"], fac.inputs[1])
    gain = nt.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = strength
    nt.links.new(fac.outputs["Value"], gain.inputs[0])
    mix = _mix(nt, "MULTIPLY")
    nt.links.new(gain.outputs["Value"], mix.inputs[0])
    if color_socket is not None:
        nt.links.new(color_socket, mix.inputs[6])
    else:
        mix.inputs[6].default_value = default or (0.7, 0.7, 0.7, 1)
    mix.inputs[7].default_value = (0.42, 0.38, 0.32, 1)
    return mix.outputs[2]


def _streaks(nt, geo, color_socket):
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.4, 1.4, 9.0)
    nt.links.new(geo.outputs["Position"], mapping.inputs["Vector"])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.0
    noise.inputs["Detail"].default_value = 6.0
    nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    band = nt.nodes.new("ShaderNodeMapRange")
    band.inputs["From Min"].default_value = 0.62
    band.inputs["From Max"].default_value = 0.82
    band.inputs["To Min"].default_value = 0.0
    band.inputs["To Max"].default_value = 0.45
    nt.links.new(noise.outputs["Fac"], band.inputs["Value"])
    mix = _mix(nt, "MULTIPLY")
    nt.links.new(band.outputs["Result"], mix.inputs[0])
    nt.links.new(color_socket, mix.inputs[6])
    mix.inputs[7].default_value = (0.35, 0.32, 0.28, 1)
    return mix.outputs[2]


def _edges(nt, geo, color_socket):
    band = nt.nodes.new("ShaderNodeMapRange")
    band.inputs["From Min"].default_value = 0.45
    band.inputs["From Max"].default_value = 0.75
    band.inputs["To Min"].default_value = 0.0
    band.inputs["To Max"].default_value = 0.35
    nt.links.new(geo.outputs["Pointiness"], band.inputs["Value"])
    mix = _mix(nt)
    nt.links.new(band.outputs["Result"], mix.inputs[0])
    nt.links.new(color_socket, mix.inputs[6])
    mix.inputs[7].default_value = (0.8, 0.78, 0.72, 1)
    return mix.outputs[2]


def _asphalt_wear(nt, geo, color_socket):
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.45
    nt.links.new(geo.outputs["Position"], noise.inputs["Vector"])
    band = nt.nodes.new("ShaderNodeMapRange")
    band.inputs["From Min"].default_value = 0.48
    band.inputs["From Max"].default_value = 0.72
    band.inputs["To Min"].default_value = 0.0
    band.inputs["To Max"].default_value = 0.55
    nt.links.new(noise.outputs["Fac"], band.inputs["Value"])
    mix = _mix(nt, "MULTIPLY")
    nt.links.new(band.outputs["Result"], mix.inputs[0])
    nt.links.new(color_socket, mix.inputs[6])
    mix.inputs[7].default_value = (0.55, 0.55, 0.55, 1)
    # A few darker, smoother blobs read as oil before the decals do.
    oil = nt.nodes.new("ShaderNodeTexNoise")
    oil.inputs["Scale"].default_value = 0.18
    nt.links.new(geo.outputs["Position"], oil.inputs["Vector"])
    oband = nt.nodes.new("ShaderNodeMapRange")
    oband.inputs["From Min"].default_value = 0.62
    oband.inputs["From Max"].default_value = 0.8
    oband.inputs["To Min"].default_value = 0.0
    oband.inputs["To Max"].default_value = 0.7
    nt.links.new(oil.outputs["Fac"], oband.inputs["Value"])
    omix = _mix(nt, "MULTIPLY")
    nt.links.new(oband.outputs["Result"], omix.inputs[0])
    nt.links.new(mix.outputs[2], omix.inputs[6])
    omix.inputs[7].default_value = (0.15, 0.14, 0.12, 1)
    return omix.outputs[2]


def _rough_jitter(nt, bsdf, geo):
    if "Roughness" not in bsdf.inputs:
        return
    ramp = nt.nodes.new("ShaderNodeMapRange")
    ramp.inputs["To Min"].default_value = 0.82
    ramp.inputs["To Max"].default_value = 1.15
    nt.links.new(geo.outputs["Random Per Island"], ramp.inputs["Value"])
    mathn = nt.nodes.new("ShaderNodeMath")
    mathn.operation = "MULTIPLY"
    src = _socket_source(nt, bsdf.inputs["Roughness"])
    if src is not None:
        nt.links.new(src, mathn.inputs[0])
    else:
        mathn.inputs[0].default_value = bsdf.inputs["Roughness"].default_value
    nt.links.new(ramp.outputs["Result"], mathn.inputs[1])
    _relink(nt, bsdf.inputs["Roughness"], mathn.outputs["Value"])


def _mix(nt, blend="MIX"):
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = blend
    return mix


def _relink(nt, socket, source):
    for link in list(nt.links):
        if link.to_socket == socket:
            nt.links.remove(link)
    nt.links.new(source, socket)


def _socket_source(nt, socket):
    for link in nt.links:
        if link.to_socket == socket:
            return link.from_socket
    return None


def _map(record, ident):
    info = (record or {}).get(ident) or {}
    return info.get("maps") or {}


def _abs(art, rel):
    if not rel:
        return None
    return os.path.join(art, "materials", rel)


def _length(road):
    import geom
    pts = road.get("polyline") or []
    return sum(geom.dist(a, b) for a, b in zip(pts, pts[1:]))
