"""Exhaust soot / burnt-ground masks for the McGregor test stands (mcgregor-tests agent, 20 Oct 2026), procedural (numpy),
no downloads:
  T_MG_SootStreaks  1024 x 1024, R = soot density on a blast apron in its UV frame (tests_layout.axis_uv): U across the
                    exhaust (0.5 = the trench axis), V along it (0 = the trench mouth). Dense near the mouth, long streaks
                    fanning out and thinning with distance, patchy (as the Raptor South apron in Apple's 2025-26 image)
  T_MG_Scorch       512 x 512, R = burnt-ground coverage for the scorch skins (UV 0..1 over the patch): a ragged blotch,
                    darkest toward the exhaust side (V < 0.5), fingers of burn along V
Run: python3 -I Scripts/mcgregor/make_scorch_textures.py  -> SourceArt/McGregor/textures/*.png (site_tests_ue.py imports them)
"""
import pathlib
import numpy as np
from PIL import Image

OUT = pathlib.Path(__file__).resolve().parents[2] / "SourceArt/McGregor/textures"
OUT.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(20261020)


def fbm(h, w, octaves=5, sx=1.0, sy=1.0, seed=0):
    """Tileable-ish value noise sum, stretched by (sx, sy) (bigger = longer features along that axis)."""
    r = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        gh, gw = max(2, int(4 * 2 ** o / sy)), max(2, int(4 * 2 ** o / sx))
        g = r.random((gh + 1, gw + 1)).astype(np.float32)
        yy = np.linspace(0, gh, h, endpoint=False)
        xx = np.linspace(0, gw, w, endpoint=False)
        y0, x0 = yy.astype(int), xx.astype(int)
        fy, fx = (yy - y0)[:, None], (xx - x0)[None, :]
        fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
        a = g[y0][:, x0] * (1 - fx) + g[y0][:, x0 + 1] * fx
        b = g[y0 + 1][:, x0] * (1 - fx) + g[y0 + 1][:, x0 + 1] * fx
        acc += amp * (a * (1 - fy) + b * fy)
        tot += amp
        amp *= 0.55
    return acc / tot


def soot():
    N = 1024
    v = np.linspace(0, 1, N, dtype=np.float32)[:, None]          # row = V (along the exhaust)
    u = np.linspace(0, 1, N, dtype=np.float32)[None, :]          # column = U (across)
    width = 0.12 + 0.38 * v                                       # the fan widens away from the mouth
    fan = np.exp(-((u - 0.5) / width) ** 2)
    streak = 0.6 * fbm(N, N, 7, sx=1.0, sy=12.0, seed=1) + 0.4 * fbm(N, N, 7, sx=0.5, sy=30.0, seed=7)   # long streaks along V
    streak = np.clip((streak - 0.42) * 3.5, 0, 1)
    patch = fbm(N, N, 5, 2.0, 2.0, seed=2)
    near = np.exp(-v / 0.18)                                      # dense band at the mouth
    d = fan * (0.35 + 0.65 * streak) * (1.0 - 0.75 * v) + near * fan * 0.6
    d *= 0.75 + 0.5 * patch
    d += 0.08 * np.clip(fbm(N, N, 4, 3, 3, seed=3) - 0.5, 0, 1)    # faint general grime
    d = np.clip(d, 0, 1)
    Image.fromarray((d * 255).astype(np.uint8)).save(OUT / "T_MG_SootStreaks.png")


def scorch():
    N = 512
    y, x = np.mgrid[0:N, 0:N].astype(np.float32) / (N - 1)
    dx, dy = (x - 0.5) * 2, (y - 0.5) * 2                        # dy < 0: the side toward the exhaust source (V < 0.5)
    r = np.sqrt(dx * dx * 1.0 + dy * dy * 0.8)
    edge = 0.74 + 0.5 * (fbm(N, N, 6, 0.7, 0.7, seed=4) - 0.5) * 2
    blot = np.clip((edge - r) / 0.12, 0, 1)
    fingers = np.clip((fbm(N, N, 6, 0.5, 5.0, seed=5) - 0.45) * 3.5, 0, 1)
    toward = np.clip(1.0 - (dy + 1) * 0.35, 0.3, 1.0)
    d = blot * (0.55 + 0.45 * fingers) * toward
    d *= 0.8 + 0.4 * fbm(N, N, 4, 4, 4, seed=6)
    d = np.clip(d, 0, 1)
    Image.fromarray((d * 255).astype(np.uint8)).save(OUT / "T_MG_Scorch.png")


soot()
scorch()
print("textures ->", OUT)
