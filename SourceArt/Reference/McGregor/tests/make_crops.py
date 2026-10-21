"""crop.py SRC x0 x1 y0 y1 m_per_px out.jpg [grid_m]  -- site-frame crop (x east, y north, metres) with a labelled grid.
SRC: esri (World Imagery, current) | wb:<release id> (Esri Wayback) | naip22 | strat20"""
import math, sys, subprocess, io
from PIL import Image, ImageDraw
LAT0, LON0, KX, KY = 31.40375, -97.4621, 95013.4785, 110574.0
src, x0, x1, y0, y1, mpp, out = sys.argv[1], *map(float, sys.argv[2:7]), sys.argv[7]
grid = float(sys.argv[8]) if len(sys.argv) > 8 else 0
W, H = int((x1 - x0) / mpp), int((y1 - y0) / mpp)
def merc(lon, lat):
    R = 6378137.0
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
lon_a, lat_a = LON0 + x0 / KX, LAT0 + y0 / KY
lon_b, lat_b = LON0 + x1 / KX, LAT0 + y1 / KY
mx0, my0 = merc(lon_a, lat_a); mx1, my1 = merc(lon_b, lat_b)
bbox = f"{mx0},{my0},{mx1},{my1}"
if src == "esri":
    url = f"https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/export?bbox={bbox}&bboxSR=102100&imageSR=102100&size={W},{H}&format=jpg&f=image"
elif src == "naip22":
    url = f"https://imagery.geographic.texas.gov/server/rest/services/NAIP/NAIP22_NCCIR_60cm/ImageServer/exportImage?bbox={bbox}&bboxSR=102100&imageSR=102100&size={W},{H}&format=jpg&bandIds=0,1,2&f=image"
elif src == "strat20":
    url = f"https://imagery.geographic.texas.gov/server/rest/services/StratMap/StratMap20_NCCIR_CapArea_McLennan/ImageServer/exportImage?bbox={bbox}&bboxSR=102100&imageSR=102100&size={W},{H}&format=jpg&bandIds=0,1,2&f=image"
else:
    raise SystemExit("src?")
data = subprocess.run(["curl", "-sS", "-m", "120", "-A", "SkyCity-mcgregor/1.0", url], capture_output=True).stdout
if data[:2] != b"\xff\xd8": print(data[:300]); raise SystemExit(1)
im = Image.open(io.BytesIO(data)).convert("RGB")
if im.size != (W, H):
    im = im.resize((W, H))
if grid:
    d = ImageDraw.Draw(im)
    gx = math.ceil(x0 / grid) * grid
    while gx <= x1:
        u = (gx - x0) / mpp; d.line([(u, 0), (u, H)], fill=(255, 255, 0), width=1); d.text((u + 2, 2), f"{gx:.0f}", fill=(255, 255, 0)); gx += grid
    gy = math.ceil(y0 / grid) * grid
    while gy <= y1:
        v = (y1 - gy) / mpp; d.line([(0, v), (W, v)], fill=(0, 255, 255), width=1); d.text((2, v + 2), f"{gy:.0f}", fill=(0, 255, 255)); gy += grid
im.save(out, quality=88)
print(out, im.size)
