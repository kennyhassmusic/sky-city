"""Texel density and window aspect for the generated city meshes.

Every facade face is projected from its own width and height:

    U = width / meters_u
    V = height / meters_v

meters_v is kept in step with meters_u and the image's pixel aspect, so one
axis is never scaled on its own. Each texture set is also checked on its
own: pixels per metre on U and on V have to agree within 3%. A set whose
meters_u/v ignore the image aspect stretches the wall even when every face
is projected from those metres. A window's width/height matches the lit
opening in the facade textures (24 by 19 pixels on T_CG_Facade_*.png).
Leftover wall length becomes a pilaster, not a wider pane.

Run:
  python3 -I Scripts/city/test_face_uv.py
"""
import glob
import math
import os
import struct

# The lit opening on the first floor of T_CG_Facade_*.png. Glass runs beside
# it are 24 or 25 pixels; the clean rectangle is 24 wide and 19 tall.
WINDOW_RECT = (24, 19)
WINDOW_ASPECT = WINDOW_RECT[0] / float(WINDOW_RECT[1])
TOLERANCE = 0.03

# Grammar wall slot -> materials.json id. Matches blender_block.SLOT.
SLOT = {
    "brick": "brick_wall_001",
    "concrete": "concrete_wall_001",
    "plaster": "grey_plaster",
    "metal": "metal_plate",
    "asphalt": "asphalt_02",
    "paving": "PavingStones092",
    "grass": "Grass004",
}
GLASS = ("M_Glass", "M_GlassLit", "M_CurtainGlass", "M_CurtainGlassLit")


def project_root():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.environ.get("SKYCITY_ROOT") or os.path.dirname(os.path.dirname(here))


def image_size(path):
    """Pixel width and height of a PNG or JPEG. (1, 1) when the file is missing."""
    if not path or not os.path.isfile(path):
        return 1, 1
    with open(path, "rb") as handle:
        head = handle.read(26)
        if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
            width, height = struct.unpack(">II", head[16:24])
            return int(width), int(height)
        if head[:2] != b"\xff\xd8":
            return 1, 1
        handle.seek(0)
        data = handle.read()
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack(">HH", data[index + 5:index + 9])
            return int(width), int(height)
        if marker in (0xD8, 0x01):
            index += 2
            continue
        if marker == 0xD9 or index + 4 > len(data):
            break
        segment = struct.unpack(">H", data[index + 2:index + 4])[0]
        if segment < 2:
            break
        index += 2 + segment
    return 1, 1


def authored_scans(root=None):
    """material name -> (pixels_u, pixels_v, meters_u, meters_v) as written.

    meters_v is not rewritten here. The set check needs the authored pair.
    """
    import json
    root = root or project_root()
    path = os.path.join(root, "SourceArt", "CityGen", "materials", "materials.json")
    if not os.path.isfile(path):
        return {}
    with open(path) as handle:
        record = json.load(handle)
    scans = {}
    for slot, ident in SLOT.items():
        info = record.get(ident) or {}
        pair = info.get("uv_m") or [1.0, 1.0]
        if not isinstance(pair, (list, tuple)):
            pair = [pair, pair]
        meters_u = float(info.get("meters_u") or pair[0] or 1.0)
        meters_v = float(info.get("meters_v") or (pair[1] if len(pair) > 1 else pair[0]) or meters_u)
        color = ((info.get("maps") or {}).get("color")) or ""
        pixels_u, pixels_v = image_size(os.path.join(root, "SourceArt", "CityGen", "materials", color))
        name = "M_" + slot.capitalize()
        scans[name] = (pixels_u, pixels_v, meters_u, meters_v)
    return scans


def load_scans(root=None):
    """material name -> (pixels_u, pixels_v, meters_u, meters_v) for tiled scans.

    The metres used to score a mesh are the uniform pair. The set check uses
    authored_scans, before this rewrite.
    """
    scans = {}
    for name, (pixels_u, pixels_v, meters_u, meters_v) in authored_scans(root).items():
        meters_u, meters_v = uniform_metres(meters_u, meters_v, pixels_u, pixels_v)
        scans[name] = (pixels_u, pixels_v, meters_u, meters_v)
    return scans


def set_density_ratio(pixels_u, pixels_v, meters_u, meters_v):
    """Pixels per metre on U, divided by pixels per metre on V.

    1.0 means the set's real-world size matches its pixel aspect. None when
    the image or the metres are missing.
    """
    try:
        pixels_u = float(pixels_u)
        pixels_v = float(pixels_v)
        meters_u = float(meters_u)
        meters_v = float(meters_v)
    except (TypeError, ValueError):
        return None
    if pixels_u < 2 or pixels_v < 2 or meters_u < 1e-6 or meters_v < 1e-6:
        return None
    per_v = pixels_v / meters_v
    if per_v < 1e-8:
        return None
    return (pixels_u / meters_u) / per_v


def score_sets(scans, sink):
    """Fail a set whose U and V texel densities differ by more than 3%."""
    for name in sorted(scans):
        pixels_u, pixels_v, meters_u, meters_v = scans[name]
        ratio = set_density_ratio(pixels_u, pixels_v, meters_u, meters_v)
        if ratio is None:
            continue
        sink["set_n"] += 1
        err = abs(ratio - 1.0)
        if err > TOLERANCE:
            sink["set_fail"] += 1
        _keep(sink["sets"], err, {
            "kind": "set",
            "material": name,
            "ratio": ratio,
            "error": err,
            "area": 0.0,
        })


def uniform_metres(meters_u, meters_v, pixels_u, pixels_v):
    """meters_v that keeps texel density matched to meters_u."""
    meters_u = float(meters_u) if meters_u else 1.0
    meters_v = float(meters_v) if meters_v else meters_u
    if pixels_u > 1 and pixels_v > 1 and meters_u > 1e-6:
        meters_v = meters_u * (float(pixels_v) / float(pixels_u))
    if meters_u < 1e-4:
        meters_u = 1.0
    if meters_v < 1e-4:
        meters_v = meters_u
    return meters_u, meters_v


def fit_bays(length, floor_h, pier, aspect, window_h):
    """Whole windows of a fixed aspect. The slack is split into the end pilasters.

    The footprint edge is not resized. A short edge shrinks the window on both
    axes, so the pane stays the source aspect instead of getting wider.
    count * ww + 2 * end + (count - 1) * pier == length.
    """
    aspect = float(aspect) if aspect and float(aspect) > 1e-4 else WINDOW_ASPECT
    floor_h = max(0.8, float(floor_h or 3.0))
    cap_h = floor_h * 0.92
    window_h = min(max(0.3, float(window_h or floor_h * 0.5)), cap_h)
    window_w = window_h * aspect
    pier = max(0.08, float(pier or 0.2))
    length = max(0.3, float(length or 0.3))
    count = int(math.floor((length - pier) / (window_w + pier) + 1e-6))
    while count > 1 and count * window_w + (count + 1) * pier > length + 1e-4:
        count -= 1
    if count >= 1 and count * window_w + (count + 1) * pier <= length + 1e-4:
        need = count * window_w + (count + 1) * pier
        slack = max(0.0, length - need)
        return {
            "count": int(count),
            "ww": window_w,
            "wh": window_h,
            "pier": pier,
            "end": pier + slack / 2.0,
            "aspect": window_w / window_h,
        }
    # One pane. Shrink width and height together, and give the leftover to the pilasters.
    count = 1
    spare = min(pier, max(0.06, length * 0.12))
    window_w = min(window_w, max(0.2, length - 2.0 * spare))
    window_h = window_w / aspect
    if window_h > cap_h:
        window_h = cap_h
        window_w = window_h * aspect
    if window_w > length - 1e-4:
        window_w = length * 0.72
        window_h = window_w / aspect
    pier_used = max(0.0, (length - window_w) / 2.0)
    return {
        "count": 1,
        "ww": window_w,
        "wh": window_h,
        "pier": pier_used,
        "end": pier_used,
        "aspect": window_w / window_h if window_h else aspect,
    }


def _triangle_ratio(p0, p1, p2, uv0, uv1, uv2, pixels_u, pixels_v):
    """Texel density U over texel density V. None when the triangle is degenerate."""
    e1 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    e2 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
    du1, dv1 = uv1[0] - uv0[0], uv1[1] - uv0[1]
    du2, dv2 = uv2[0] - uv0[0], uv2[1] - uv0[1]
    det = du1 * dv2 - dv1 * du2
    if abs(det) < 1e-8:
        return None
    xu = ((e1[0] * dv2 - e2[0] * dv1) / det,
          (e1[1] * dv2 - e2[1] * dv1) / det,
          (e1[2] * dv2 - e2[2] * dv1) / det)
    xv = ((e2[0] * du1 - e1[0] * du2) / det,
          (e2[1] * du1 - e1[1] * du2) / det,
          (e2[2] * du1 - e1[2] * du2) / det)
    metres_u = math.sqrt(xu[0] ** 2 + xu[1] ** 2 + xu[2] ** 2)
    metres_v = math.sqrt(xv[0] ** 2 + xv[1] ** 2 + xv[2] ** 2)
    if metres_u < 1e-5 or metres_v < 1e-5:
        return None
    cross = (
        e1[1] * e2[2] - e1[2] * e2[1],
        e1[2] * e2[0] - e1[0] * e2[2],
        e1[0] * e2[1] - e1[1] * e2[0],
    )
    area = 0.5 * math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2)
    if area < 0.02:
        return None
    density_u = float(pixels_u) / metres_u
    density_v = float(pixels_v) / metres_v
    if density_v < 1e-8:
        return None
    return density_u / density_v, area


def _window_aspect(p0, p1, p2):
    """Width/height of a rectangular pane, as the longer leg over the shorter."""
    edges = (
        math.dist(p0, p1),
        math.dist(p1, p2),
        math.dist(p2, p0),
    )
    legs = sorted(edges)
    if legs[0] < 0.35:
        return None
    hypot2 = legs[2] * legs[2]
    expect = legs[0] * legs[0] + legs[1] * legs[1]
    if abs(hypot2 - expect) > 0.04 * hypot2:
        return None
    return legs[1] / legs[0], legs[0] * legs[1] * 0.5


def consider_polygon(points, uvs, material, scans, sink):
    """Score one tri or quad. `sink` collects worst rows and failure counts."""
    n = len(points)
    if n < 3:
        return
    tris = [(0, 1, 2)] if n == 3 else [(0, 1, 2), (0, 2, 3)]
    scan = scans.get(material)
    for a, b, c in tris:
        if scan is not None and uvs and len(uvs) >= c + 1:
            scored = _triangle_ratio(points[a], points[b], points[c], uvs[a], uvs[b], uvs[c], scan[0], scan[1])
            if scored is not None:
                ratio, area = scored
                sink["density_n"] += 1
                err = abs(ratio - 1.0)
                if err > TOLERANCE:
                    sink["density_fail"] += 1
                _keep(sink["density"], err, {
                    "kind": "density", "material": material, "ratio": ratio,
                    "error": err, "area": area,
                })
        if material in GLASS:
            aspect = _window_aspect(points[a], points[b], points[c])
            if aspect is None:
                continue
            got, area = aspect
            sink["window_n"] += 1
            err = abs(got / WINDOW_ASPECT - 1.0)
            if err > TOLERANCE:
                sink["window_fail"] += 1
            _keep(sink["windows"], err, {
                "kind": "window", "material": material, "aspect": got,
                "target": WINDOW_ASPECT, "error": err, "area": area,
            })


def _keep(bucket, score, row):
    row["score"] = score
    bucket.append(row)
    if len(bucket) > 40:
        bucket.sort(key=lambda item: item["score"], reverse=True)
        del bucket[20:]


def new_sink():
    return {
        "density": [], "windows": [], "sets": [],
        "density_n": 0, "density_fail": 0,
        "window_n": 0, "window_fail": 0,
        "set_n": 0, "set_fail": 0,
    }


def _accessor_array(gltf, blob, index):
    import numpy as np
    accessor = gltf["accessors"][index]
    view = gltf["bufferViews"][accessor["bufferView"]]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    count = accessor["count"]
    components = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor["type"]]
    dtype = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}[accessor["componentType"]]
    width = components * np.dtype(dtype).itemsize
    stride = view.get("byteStride", width)
    if stride == width:
        return np.frombuffer(blob, dtype=dtype, count=count * components, offset=start).reshape(count, components)
    rows = np.empty((count, components), dtype=dtype)
    for i in range(count):
        rows[i] = np.frombuffer(blob, dtype=dtype, count=components, offset=start + i * stride)
    return rows


def _score_indexed(positions, uvs, indices, material, scans, sink):
    """Vectorised triangle score. Positions are Nx3, uvs Nx2, indices flat or Nx1."""
    import numpy as np
    pos = np.asarray(positions, dtype=np.float64)
    idx = np.asarray(indices, dtype=np.int64).reshape(-1)
    if idx.size < 3:
        return
    idx = idx[:idx.size - (idx.size % 3)].reshape(-1, 3)
    tri = pos[idx]
    e1 = tri[:, 1] - tri[:, 0]
    e2 = tri[:, 2] - tri[:, 0]
    cross = np.cross(e1, e2)
    area = 0.5 * np.linalg.norm(cross, axis=1)
    scan = scans.get(material)
    if scan is not None and uvs is not None:
        uv = np.asarray(uvs, dtype=np.float64)
        tuv = uv[idx]
        du1 = tuv[:, 1, 0] - tuv[:, 0, 0]
        dv1 = tuv[:, 1, 1] - tuv[:, 0, 1]
        du2 = tuv[:, 2, 0] - tuv[:, 0, 0]
        dv2 = tuv[:, 2, 1] - tuv[:, 0, 1]
        det = du1 * dv2 - dv1 * du2
        ok = (np.abs(det) > 1e-8) & (area > 0.02)
        safe = np.where(ok, det, 1.0)
        xu = (e1 * dv2[:, None] - e2 * dv1[:, None]) / safe[:, None]
        xv = (e2 * du1[:, None] - e1 * du2[:, None]) / safe[:, None]
        metres_u = np.linalg.norm(xu, axis=1)
        metres_v = np.linalg.norm(xv, axis=1)
        ok = ok & (metres_u > 1e-5) & (metres_v > 1e-5)
        ratio = (float(scan[0]) / metres_u) / (float(scan[1]) / metres_v)
        picked = np.flatnonzero(ok)
        sink["density_n"] += int(picked.size)
        err = np.abs(ratio[picked] - 1.0)
        sink["density_fail"] += int(np.count_nonzero(err > TOLERANCE))
        if picked.size:
            order = picked[np.argsort(-np.abs(ratio[picked] - 1.0))[:8]]
            for i in order:
                _keep(sink["density"], abs(float(ratio[i]) - 1.0), {
                    "kind": "density", "material": material, "ratio": float(ratio[i]),
                    "error": abs(float(ratio[i]) - 1.0), "area": float(area[i]),
                })
    if material not in GLASS:
        return
    lengths = np.stack((
        np.linalg.norm(tri[:, 1] - tri[:, 0], axis=1),
        np.linalg.norm(tri[:, 2] - tri[:, 1], axis=1),
        np.linalg.norm(tri[:, 0] - tri[:, 2], axis=1),
    ), axis=1)
    legs = np.sort(lengths, axis=1)
    hypot2 = legs[:, 2] ** 2
    expect = legs[:, 0] ** 2 + legs[:, 1] ** 2
    pane = (legs[:, 0] >= 0.35) & (np.abs(hypot2 - expect) <= 0.04 * hypot2)
    aspect = legs[:, 1] / np.maximum(legs[:, 0], 1e-8)
    chosen = np.flatnonzero(pane)
    sink["window_n"] += int(chosen.size)
    if not chosen.size:
        return
    err = np.abs(aspect[chosen] / WINDOW_ASPECT - 1.0)
    sink["window_fail"] += int(np.count_nonzero(err > TOLERANCE))
    order = chosen[np.argsort(-np.abs(aspect[chosen] / WINDOW_ASPECT - 1.0))[:8]]
    for i in order:
        got = float(aspect[i])
        error = abs(got / WINDOW_ASPECT - 1.0)
        _keep(sink["windows"], error, {
            "kind": "window", "material": material, "aspect": got,
            "target": WINDOW_ASPECT, "error": error, "area": float(area[i]),
        })


def scan_glb(path, scans):
    """Score one exported GLB. Returns the sink, with a file name on each worst row."""
    import json
    with open(path, "rb") as handle:
        data = handle.read()
    json_len, json_type = struct.unpack_from("<II", data, 12)
    if json_type != 0x4E4F534A:
        raise ValueError("not a glTF JSON chunk: %s" % path)
    gltf = json.loads(data[20:20 + json_len])
    bin_off = 20 + json_len
    bin_len, bin_type = struct.unpack_from("<II", data, bin_off)
    if bin_type != 0x004E4942:
        raise ValueError("not a glTF BIN chunk: %s" % path)
    blob = data[bin_off + 8:bin_off + 8 + bin_len]
    names = [mat.get("name") or "" for mat in gltf.get("materials") or []]
    sink = new_sink()
    base = os.path.basename(path)
    for mesh in gltf.get("meshes") or []:
        for prim in mesh.get("primitives") or []:
            material = names[prim.get("material", 0)] if names else ""
            if material not in scans and material not in GLASS:
                continue
            attrs = prim.get("attributes") or {}
            if "POSITION" not in attrs or "indices" not in prim:
                continue
            positions = _accessor_array(gltf, blob, attrs["POSITION"])
            uvs = _accessor_array(gltf, blob, attrs["TEXCOORD_0"]) if "TEXCOORD_0" in attrs else None
            indices = _accessor_array(gltf, blob, prim["indices"])
            _score_indexed(positions, uvs, indices, material, scans, sink)
    for row in sink["density"] + sink["windows"] + sink.get("sets", []):
        row["file"] = base
    return sink


def building_glbs(folder):
    paths = sorted(glob.glob(os.path.join(folder, "CG_*.glb")))
    return [path for path in paths if "street" not in os.path.basename(path)]


def merge_sinks(sinks):
    total = new_sink()
    for sink in sinks:
        total["density_n"] += sink["density_n"]
        total["density_fail"] += sink["density_fail"]
        total["window_n"] += sink["window_n"]
        total["window_fail"] += sink["window_fail"]
        total["set_n"] += sink.get("set_n", 0)
        total["set_fail"] += sink.get("set_fail", 0)
        total["density"].extend(sink["density"])
        total["windows"].extend(sink["windows"])
        total["sets"].extend(sink.get("sets") or [])
    total["density"].sort(key=lambda row: row["score"], reverse=True)
    total["windows"].sort(key=lambda row: row["score"], reverse=True)
    total["sets"].sort(key=lambda row: row["score"], reverse=True)
    return total


def check_folder(folder, root=None):
    authored = authored_scans(root)
    scans = {}
    for name, (pixels_u, pixels_v, meters_u, meters_v) in authored.items():
        meters_u, meters_v = uniform_metres(meters_u, meters_v, pixels_u, pixels_v)
        scans[name] = (pixels_u, pixels_v, meters_u, meters_v)
    sinks = [scan_glb(path, scans) for path in building_glbs(folder)]
    total = merge_sinks(sinks)
    score_sets(authored, total)
    return total


def worst(sink, limit=10):
    rows = []
    seen = set()
    for row in sink["density"] + sink["windows"] + sink.get("sets", []):
        key = (row.get("file"), row["kind"], row["material"], round(row["score"], 4), round(row["area"], 2))
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    rows.sort(key=lambda row: row["score"], reverse=True)
    return rows[:limit]


def format_report(sink, limit=10):
    lines = [
        "UV faces %d  density fails %d  windows %d  window fails %d  sets %d  set fails %d  target aspect %.4f"
        % (
            sink["density_n"], sink["density_fail"], sink["window_n"], sink["window_fail"],
            sink.get("set_n", 0), sink.get("set_fail", 0), WINDOW_ASPECT,
        ),
        "worst %d" % limit,
    ]
    for index, row in enumerate(worst(sink, limit), 1):
        where = row.get("file") or ""
        if row["kind"] == "density":
            lines.append("%d. %s %s density U/V %.4f  area %.2f" % (index, where, row["material"], row["ratio"], row["area"]))
        elif row["kind"] == "set":
            lines.append("%d. %s set px/m U/V %.4f" % (index, row["material"], row["ratio"]))
        else:
            lines.append("%d. %s %s window aspect %.4f target %.4f  err %.1f%%  area %.2f"
                         % (index, where, row["material"], row["aspect"], row["target"], row["error"] * 100.0, row["area"]))
    return "\n".join(lines)


def passed(sink):
    return (
        sink["density_fail"] == 0 and sink["window_fail"] == 0
        and sink.get("set_fail", 0) == 0
        and sink["window_n"] > 0 and sink["density_n"] > 0
    )
