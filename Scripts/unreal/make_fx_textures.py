"""Textures for the car's thrust and smoke (Scripts/unreal/fx_ue.py imports them):
T_SkyNoise: tileable cloudy noise (FFT-filtered, 1/f^2), sampled stretched and scrolling in the plume material.
T_SkyPuff: one soft, billowy puff on black, for the vapour, smoke, dust and fire sprites.
Run: python3 Scripts/unreal/make_fx_textures.py  (writes SourceArt/FX/*.png)"""
import os
import numpy as np
from PIL import Image

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "SourceArt", "FX")
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(7)


def fbm(n, beta, lo=1.0):
    """Tileable noise of size n x n with a 1/f^beta amplitude spectrum, scaled to 0..1."""
    fx = np.fft.fftfreq(n)[:, None]
    fy = np.fft.rfftfreq(n)[None, :]
    f = np.sqrt(fx * fx + fy * fy) * n
    amp = np.where(f < lo, 0.0, 1.0 / np.maximum(f, 1e-6) ** (beta / 2 + 0.5))
    spec = amp * (rng.normal(size=amp.shape) + 1j * rng.normal(size=amp.shape))
    img = np.fft.irfft2(spec, s=(n, n))
    img -= img.min()
    return img / img.max()


def save(name, a):
    Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), "L").save(os.path.join(OUT, name))
    print("wrote", name)


# plume turbulence: mid-frequency clouds with some fine grain
noise = 0.75 * fbm(256, 1.6, 2.0) + 0.25 * fbm(256, 0.9, 6.0)
noise = (noise - noise.min()) / (noise.max() - noise.min())
save("T_SkyNoise.png", noise)

# puff: a round, lumpy cloud whose edge wanders with the noise and fades to zero well inside the quad
n = 256
y, x = (np.mgrid[0:n, 0:n] + 0.5) / n * 2 - 1
r = np.sqrt(x * x + y * y)
billow = fbm(n, 1.4, 1.5)
fine = fbm(n, 0.8, 4.0)
edge = 0.8 + 0.3 * (billow - 0.5)
shape = np.clip(1 - r / edge, 0, 1) ** 1.3
body = 0.3 + 0.7 * billow ** 1.2 * (0.8 + 0.2 * fine)
puff = shape * body
puff *= np.clip((0.97 - r) / 0.12, 0, 1)                   # nothing at the quad's edge
save("T_SkyPuff.png", puff / puff.max())

# --smoke: pack the Blender smoke flipbook (blender_smoke_flipbook.py, 64 frames of 256 px) into an 8 x 8 atlas, its
# light and shade normalised so the brightest billows are white (Unreal's lighting and the particle colour do the rest)
import sys
if "--smoke" in sys.argv:
    src = os.path.join(os.environ.get("TMPDIR", "/tmp"), "skysmoke")
    frames = [np.asarray(Image.open(os.path.join(src, f"f_{i:02d}.png")).convert("RGBA"), dtype=np.float32) / 255 for i in range(64)]
    lit = np.concatenate([f[..., :3][f[..., 3] > 0.3].ravel() for f in frames])
    gain = 1.0 / max(np.percentile(lit, 98), 1e-3)
    atlas = np.zeros((2048, 2048, 4), np.float32)
    for i, f in enumerate(frames):
        y, x = divmod(i, 8)
        g = f.copy()
        g[..., :3] = np.clip(g[..., :3] * gain, 0, 1)
        atlas[y * 256:(y + 1) * 256, x * 256:(x + 1) * 256] = g
    Image.fromarray((atlas * 255 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(OUT, "T_SkySmoke.png"))
    print("wrote T_SkySmoke.png, light gain", round(float(gain), 2))
