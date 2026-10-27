"""Lane 9: the B water's textures, made by code (no third-party art). Tileable: built in the frequency domain.
  T_L9_WaterNormal  512² ripple normal map (a spectrum of small waves), tangent space, +Z up
  T_L9_Foam         256² foam breakup (band-passed noise, thresholded softly)
  T_L9_BedNoise     256² silt and pebble breakup for the riverbed
python3 make_textures.py <out dir>"""
import sys
import numpy as np
from PIL import Image

out = sys.argv[1]
rng = np.random.default_rng(9)


def spectral(n, lo, hi, power):
    f = np.fft.fftfreq(n) * n
    kx, ky = np.meshgrid(f, f)
    k = np.hypot(kx, ky)
    amp = np.where((k >= lo) & (k <= hi), (k + 1e-6) ** (-power), 0.0)
    phase = rng.uniform(0, 2 * np.pi, (n, n))
    field = np.real(np.fft.ifft2(amp * np.exp(1j * phase)))
    field -= field.min()
    return field / field.max()


n = 512
h = spectral(n, 3, 60, 1.6) * 0.75 + spectral(n, 20, 120, 1.2) * 0.25
gy, gx = np.gradient(h * 6.0)
# wrap-aware gradient at the edges
gx[:, 0] = (h[:, 1] - h[:, -1]) * 3.0
gx[:, -1] = (h[:, 0] - h[:, -2]) * 3.0
gy[0, :] = (h[1, :] - h[-1, :]) * 3.0
gy[-1, :] = (h[0, :] - h[-2, :]) * 3.0
nx, ny, nz = -gx * 8, -gy * 8, np.ones_like(h)
ln = np.sqrt(nx * nx + ny * ny + nz * nz)
rgb = np.stack([nx / ln, ny / ln, nz / ln], -1) * 0.5 + 0.5
Image.fromarray((rgb * 255).astype(np.uint8)).save(out + "/T_L9_WaterNormal.png")
foam = spectral(256, 4, 40, 1.0)
foam = np.clip((foam - 0.35) * 2.2, 0, 1) ** 1.3
Image.fromarray((foam * 255).astype(np.uint8)).convert("RGB").save(out + "/T_L9_Foam.png")
bed = spectral(256, 2, 90, 1.1)
Image.fromarray((bed * 255).astype(np.uint8)).convert("RGB").save(out + "/T_L9_BedNoise.png")
print("ok")
