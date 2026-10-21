"""Low-res overview of the whole McGregor aerial mosaic for the horizon skirt: 2048 x 2048 px over a 9600 m square
centred on the map (4.7 m/px). The 7200 m tall map fills the middle 1536 rows; the 256-row strips above and below are
mirrored copies, so with mirror addressing the fields carry on past the map edge without a seam.
Run: python3 -I Scripts/mcgregor/make_overview.py  ->  $SKYCITY_MCGREGOR_RAW/overview_2048.png (default Saved/McGregorRaw) (PNG: the JPEG built black in UE)"""
import json, os, pathlib
from PIL import Image, ImageOps
ROOT = pathlib.Path(__file__).resolve().parents[2]
RAS = pathlib.Path(os.environ.get("SKYCITY_MCGREGOR_RAW", ROOT / "Saved" / "McGregorRaw"))
M = json.load(open(RAS / "rasters.json"))
mos = Image.new("RGB", (2048, 1536))
for t in M["tiles"]:
    im = Image.open(RAS / t["file"]).convert("RGB").resize((512, 512), Image.LANCZOS)
    mos.paste(im, (t["i"] * 512, (2 - t["j"]) * 512))          # row 0 = north
out = Image.new("RGB", (2048, 2048))
out.paste(mos, (0, 256))
out.paste(ImageOps.flip(mos.crop((0, 0, 2048, 256))), (0, 0))
out.paste(ImageOps.flip(mos.crop((0, 1280, 2048, 1536))), (0, 1792))
out.save(RAS / "overview_2048.png")
M["overview"] = {"file": "overview_2048.png", "x0": -M["w_m"] / 2, "y0": -M["w_m"] / 2, "size_m": M["w_m"]}
json.dump(M, open(RAS / "rasters.json", "w"), indent=1)
print("overview written")
