"""The engine-test roar for SkysterEngineTests (mcgregor-tests agent, 20 Oct 2026): synthesised here (numpy, no downloads,
no samples), a seamless 8 s mono loop at 22.05 kHz:
  rumble   brown noise (leaky-integrated white noise), the low roar you feel more than hear
  roar     band-limited noise 120-900 Hz with slow turbulent swells
  crackle  rocket "crackle": sparse, sharp, positive-skewed pressure spikes (a few ms each, ~180 a second, random sizes),
           the sound that makes a big engine sound like an engine and not a waterfall
The C++ adds distance (natural fall-off, a low-pass far away) and the speed-of-sound delay.
Run: python3 -I Scripts/mcgregor/make_engine_roar.py  -> SourceArt/McGregor/audio/S_MG_EngineRoar.wav
(site_tests_ue.py `audio` imports it as /Game/McGregor/Audio/S_MG_EngineRoar, looping)
"""
import pathlib, wave
import numpy as np

SR, SECS, FADE = 22050, 8.0, 0.6
OUT = pathlib.Path(__file__).resolve().parents[2] / "SourceArt/McGregor/audio"
OUT.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(6900)
n = int(SR * (SECS + FADE))


def onepole_lp(x, fc):
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):          # small loop, fine for 190k samples
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def band(x, lo, hi):
    return onepole_lp(x, hi) - onepole_lp(x, lo)


w = rng.standard_normal(n).astype(np.float64)
# rumble: leaky integrator -> brown noise, then a gentle low-pass
brown = np.empty(n)
acc = 0.0
for i in range(n):
    acc = 0.995 * acc + w[i] * 0.06
    brown[i] = acc
brown = onepole_lp(brown, 180.0)
brown /= np.abs(brown).max()
# roar: band noise with slow swells (sum of a few slow sines with random phases)
roar = band(rng.standard_normal(n), 120.0, 900.0)
t = np.arange(n) / SR
swell = 1.0 + 0.25 * np.sin(2 * np.pi * 0.37 * t + 1.1) + 0.18 * np.sin(2 * np.pi * 1.3 * t + 2.3) + 0.12 * np.sin(2 * np.pi * 2.9 * t + 0.4)
roar *= swell
roar /= np.abs(roar).max()
# crackle: sparse sharp spikes
crack = np.zeros(n)
k = 0
while True:
    k += int(rng.exponential(SR / 180.0)) + 1
    if k >= n - 200:
        break
    amp = rng.lognormal(0.0, 0.7)
    L = int(SR * rng.uniform(0.0015, 0.005))
    env = np.exp(-np.arange(L) / (L / 4.0))
    crack[k:k + L] += amp * env * (1.0 + 0.3 * rng.standard_normal(L))
crack -= onepole_lp(crack, 300.0)          # keep the sharp part
crack /= np.abs(crack).max()
mix = 0.55 * brown + 0.45 * roar + 0.32 * crack
# seamless loop: crossfade the tail over the head
m = int(SR * SECS)
f = int(SR * FADE)
ramp = np.linspace(0, 1, f)
out = mix[:m].copy()
out[:f] = mix[:f] * ramp + mix[m:m + f] * (1 - ramp)
out /= np.abs(out).max() / 0.89
pcm = (out * 32767).astype("<i2")
with wave.open(str(OUT / "S_MG_EngineRoar.wav"), "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(SR)
    wf.writeframes(pcm.tobytes())
print("roar ->", OUT / "S_MG_EngineRoar.wav", round(len(pcm) / SR, 2), "s")
