"""Leaf-cluster textures for Sky City's street trees, made from ambientCG's CC0 leaf scans.

Each scan holds ~6 leaves or sprigs on a plain background; this cuts them out with the opacity map, then lays
them along a few drawn twigs into a 1024 x 1024 cluster card (colour + alpha, and a matching normal map whose
vectors are rotated with each leaf). Species:
  liveoak      LeafSet002 (small smooth oval leaves on sprigs), darkened   - Austin's live oak
  honeylocust  LeafSet002, small and yellow-green, airy                    - Chicago's honey locust
  linden       LeafSet004 (heart-shaped)                                   - Chicago's linden
  elm          LeafSet005 (serrated)                                       - elm, both cities
Also T_Bark (procedural grey-brown bark, tileable).
Output: SourceArt/StreetKit/textures/T_Leaves_<species>_C.png / _N.png, T_Bark_C.png / _N.png

Run: python3 -I Scripts/streets/make_leaf_textures.py
"""
import math, pathlib
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "SourceArt/CC0/ambientcg"
OUT = ROOT / "SourceArt/StreetKit/textures"
OUT.mkdir(parents=True, exist_ok=True)
SIZE = 1024


def leaves_from(set_id):
    d = SRC / set_id
    col = np.asarray(Image.open(d / f"{set_id}_2K-JPG_Color.jpg").convert("RGB"), np.float32) / 255
    op = np.asarray(Image.open(d / f"{set_id}_2K-JPG_Opacity.jpg").convert("L"), np.float32) / 255
    nor = np.asarray(Image.open(d / f"{set_id}_2K-JPG_NormalGL.jpg").convert("RGB"), np.float32) / 255
    lab, n = ndimage.label(op > 0.5)
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        area = (lab[sl] == i).sum()
        if area < 6000 or min(h, w) < 25:
            continue          # stray guide lines and specks
        m = (lab[sl] == i).astype(np.float32) * op[sl]
        rgba = np.dstack([col[sl], m])
        out.append((rgba, nor[sl]))
    return out


def rotate_leaf(rgba, nor, ang_deg, scale):
    """Rotate and scale one leaf; rotate its tangent-space normals by the same angle."""
    h, w = rgba.shape[:2]
    size = (max(1, int(w * scale)), max(1, int(h * scale)))
    im = Image.fromarray((rgba * 255).astype(np.uint8), "RGBA").resize(size, Image.LANCZOS).rotate(ang_deg, Image.BICUBIC, expand=True)
    nm = Image.fromarray((nor * 255).astype(np.uint8), "RGB").resize(size, Image.LANCZOS).rotate(ang_deg, Image.BICUBIC, expand=True, fillcolor=(128, 128, 255))
    n = np.asarray(nm, np.float32) / 255 * 2 - 1
    a = math.radians(ang_deg)
    # PIL rotates counter-clockwise on screen (y down), which is clockwise in texture space (y up)
    c, s = math.cos(-a), math.sin(-a)
    nx = c * n[..., 0] - s * n[..., 1]
    ny = s * n[..., 0] + c * n[..., 1]
    n = np.dstack([nx, ny, n[..., 2]])
    return np.asarray(im, np.float32) / 255, n


def compose(name, leaves, rng, leaf_len, count, tint, stem_col, twigs):
    C = np.zeros((SIZE, SIZE, 4), np.float32)
    N = np.zeros((SIZE, SIZE, 3), np.float32)
    N[..., 2] = 1.0
    # twigs: from the bottom centre fanning upward
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    dr = ImageDraw.Draw(canvas)
    base = (SIZE * 0.5, SIZE * 0.98)
    tips = []
    for k in range(twigs):
        ang = math.radians(-90 + rng.uniform(-55, 55))
        L = SIZE * rng.uniform(0.55, 0.85)
        pts = [base]
        p = base
        a = ang
        for seg in range(6):
            a += rng.uniform(-0.18, 0.18)
            q = (p[0] + math.cos(a) * L / 6, p[1] + math.sin(a) * L / 6)
            pts.append(q)
            p = q
        dr.line(pts, fill=stem_col + (255,), width=int(rng.uniform(5, 9)), joint="curve")
        tips.append(pts)
    stem = np.asarray(canvas, np.float32) / 255
    C = stem.copy()
    # leaves along the twigs, back to front
    placed = []
    for i in range(count):
        tw = tips[rng.integers(len(tips))]
        t = rng.uniform(0.25, 1.0)
        seg = min(len(tw) - 2, int(t * (len(tw) - 1)))
        u = t * (len(tw) - 1) - seg
        a, b = tw[seg], tw[seg + 1]
        p = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        dirang = math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))      # twig direction, y up
        side = 1 if rng.random() < 0.5 else -1
        ang = dirang + side * rng.uniform(25, 70) - 90                     # leaves point out of the twig, tip first
        rgba, nor = leaves[rng.integers(len(leaves))]
        scale = leaf_len * rng.uniform(0.75, 1.15) / max(rgba.shape[:2])
        r, n = rotate_leaf(rgba, nor, ang, scale)
        placed.append((p, r, n))
    for p, r, n in placed:
        h, w = r.shape[:2]
        x0, y0 = int(p[0] - w / 2), int(p[1] - h / 2)
        xa, ya, xb, yb = max(0, x0), max(0, y0), min(SIZE, x0 + w), min(SIZE, y0 + h)
        if xa >= xb or ya >= yb:
            continue
        rr = r[ya - y0:yb - y0, xa - x0:xb - x0]
        nn = n[ya - y0:yb - y0, xa - x0:xb - x0]
        al = rr[..., 3:4]
        var = rng.uniform(0.85, 1.12)
        col = np.clip(rr[..., :3] * np.array(tint, np.float32) * var, 0, 1)
        C[ya:yb, xa:xb, :3] = C[ya:yb, xa:xb, :3] * (1 - al) + col * al
        C[ya:yb, xa:xb, 3:4] = np.maximum(C[ya:yb, xa:xb, 3:4], al)
        N[ya:yb, xa:xb] = N[ya:yb, xa:xb] * (1 - al) + nn * al
    # bleed colour into transparent texels so mips don't halo
    a = C[..., 3] > 0.05
    if a.any():
        idx = ndimage.distance_transform_edt(~a, return_distances=False, return_indices=True)
        rgb = C[..., :3][idx[0], idx[1]]
        C[..., :3] = np.where(a[..., None], C[..., :3], rgb)
    Image.fromarray((np.clip(C, 0, 1) * 255).astype(np.uint8), "RGBA").save(OUT / f"T_Leaves_{name}_C.png")
    Nn = N / np.maximum(np.linalg.norm(N, axis=2, keepdims=True), 1e-6)
    Image.fromarray(((Nn * 0.5 + 0.5) * 255).astype(np.uint8), "RGB").save(OUT / f"T_Leaves_{name}_N.png")


def bark():
    rng = np.random.default_rng(5)
    h = np.zeros((SIZE, SIZE), np.float32)
    for k, amp in ((4, 1.0), (9, 0.5), (23, 0.25), (61, 0.12)):
        g = rng.normal(size=(k, k * 4)).astype(np.float32)
        im = Image.fromarray(((g - g.min()) / (g.max() - g.min()) * 255).astype(np.uint8)).resize((SIZE, SIZE), Image.BICUBIC)
        h += (np.asarray(im, np.float32) / 255 - 0.5) * amp
    # vertical furrows: stretch noise along y
    furrow = np.asarray(Image.fromarray(((h - h.min()) / (h.max() - h.min()) * 255).astype(np.uint8)).resize((SIZE // 8, SIZE), Image.BICUBIC).resize((SIZE, SIZE), Image.BICUBIC), np.float32) / 255
    hh = 0.6 * furrow + 0.4 * (h - h.min()) / (h.max() - h.min())
    hh = np.tile(hh[:, :SIZE // 2], (1, 2)) * 0 + hh
    base = np.array([0.30, 0.26, 0.22], np.float32)
    col = base[None, None, :] * (0.55 + 0.75 * hh[..., None])
    Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8), "RGB").save(OUT / "T_Bark_C.png")
    gy, gx = np.gradient(hh * 6.0)
    n = np.dstack([-gx, -gy, np.ones_like(hh)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8), "RGB").save(OUT / "T_Bark_N.png")


rng = np.random.default_rng(42)
L002 = leaves_from("LeafSet002")
compose("liveoak", L002, rng, 230, 70, (0.62, 0.72, 0.55), (70, 58, 45), 6)
compose("honeylocust", L002, rng, 150, 95, (1.05, 1.08, 0.70), (80, 66, 50), 8)
compose("linden", leaves_from("LeafSet004"), rng, 210, 42, (0.95, 1.0, 0.9), (85, 70, 52), 5)
compose("elm", leaves_from("LeafSet005") + leaves_from("LeafSet001"), rng, 220, 48, (0.9, 0.95, 0.85), (75, 62, 48), 5)
bark()
print("done")
