"""Collect the HighResShots of a vehicle_shots_ue.py run (offline, plain python3 with Pillow): matches the PNGs in
Saved/Screenshots/MacEditor to the run's shot list by time, moves them to Saved/VehicleModels/shots/<tag>/
<veh>_<view>.png and writes a JPG contact sheet Saved/VehicleModels/sheet_<tag>.jpg (one row per vehicle).
Side by side: collect_shots.py compare <tagA> <tagB> [view ...] -> Saved/VehicleModels/compare_<tagA>_<tagB>.jpg
Run: python3 Scripts/vehicles/collect_shots.py <tag>"""
import glob, json, os, shutil, sys
from PIL import Image, ImageDraw

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
    raise RuntimeError("Cannot find the SkyCity project folder (SkyCity.uproject): set SKYCITY_ROOT")


ROOT = _skycity_root()
VM = f"{ROOT}/Saved/VehicleModels"
NAMES = {1: "Sedan", 2: "Crossover", 3: "Pickup", 4: "Robotaxi", 5: "Semi"}


def collect(tag):
    run = json.load(open(f"{VM}/out_{tag}.json"))
    pngs = sorted(glob.glob(f"{ROOT}/Saved/Screenshots/MacEditor/HighresScreenshot*.png"), key=os.path.getmtime)
    od = f"{VM}/shots/{tag}"
    os.makedirs(od, exist_ok=True)
    shots = run["shots"]
    # one PNG per HighResShot, written in order (asynchronously, so a file can land after the next shot's command):
    # take the run's PNGs in time order and hand them out in shot order
    t0 = shots[0]["wall"] - 0.5 if shots else 0
    cand = [p for p in pngs if os.path.getmtime(p) >= t0][:len(shots)]
    if len(cand) < len(shots):
        print("only", len(cand), "PNGs for", len(shots), "shots")
    for s, src in zip(shots, cand):
        dst = f"{od}/{s['veh']}_{s['view']}.png"
        shutil.move(src, dst)
        s["file"] = dst
    json.dump(run, open(f"{VM}/out_{tag}.json", "w"), indent=1)
    sheet(tag, shots)


def sheet(tag, shots, w=480):
    views = []
    for s in shots:
        if s["view"] not in views:
            views.append(s["view"])
    vehs = sorted({s["veh"] for s in shots})
    h = w * 9 // 16
    img = Image.new("RGB", (w * len(views), (h + 18) * len(vehs)), "black")
    d = ImageDraw.Draw(img)
    for s in shots:
        if "file" not in s or not os.path.exists(s["file"]):
            continue
        x, y = views.index(s["view"]) * w, vehs.index(s["veh"]) * (h + 18)
        img.paste(Image.open(s["file"]).convert("RGB").resize((w, h)), (x, y + 18))
        d.text((x + 4, y + 3), f"{tag}  {NAMES.get(s['veh'], s['veh'])}  {s['view']}", fill="white")
    img.save(f"{VM}/sheet_{tag}.jpg", quality=82)
    print("sheet", f"{VM}/sheet_{tag}.jpg")


def compare(a, b, views):
    ra, rb = json.load(open(f"{VM}/out_{a}.json")), json.load(open(f"{VM}/out_{b}.json"))
    fa = {(s["veh"], s["view"]): s.get("file") for s in ra["shots"]}
    fb = {(s["veh"], s["view"]): s.get("file") for s in rb["shots"]}
    keys = [k for k in fa if k in fb and (not views or k[1] in views)]
    w, h = 560, 315
    img = Image.new("RGB", (w * 2, (h + 18) * len(keys)), "black")
    d = ImageDraw.Draw(img)
    for i, k in enumerate(keys):
        for j, (t, f) in enumerate(((a, fa[k]), (b, fb[k]))):
            if f and os.path.exists(f):
                img.paste(Image.open(f).convert("RGB").resize((w, h)), (j * w, i * (h + 18) + 18))
            d.text((j * w + 4, i * (h + 18) + 3), f"{t}  {NAMES.get(k[0], k[0])}  {k[1]}", fill="white")
    out = f"{VM}/compare_{a}_{b}.jpg"
    img.save(out, quality=80)
    print("compare", out)


if __name__ == "__main__":
    if sys.argv[1] == "compare":
        compare(sys.argv[2], sys.argv[3], sys.argv[4:])
    else:
        collect(sys.argv[1])
