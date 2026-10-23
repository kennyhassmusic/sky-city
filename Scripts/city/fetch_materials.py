"""Download the small CC0 set the block preview uses.

Poly Haven and ambientCG, JPG, 1k. No zips are kept. Running it again skips a file
that is already on disk. Sources and authors are written to materials.json; the
credits file lists the same rows.

Run: python3 -I Scripts/city/fetch_materials.py
"""
import json
import sys
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skyline

UA = "SkyCityCityGen/1.0 (sky-city; CC0 material fetch)"
DATE = "2026-10-22"

# id, maps we keep, page. Poly Haven file API names the maps Diffuse/nor_gl/Rough.
POLYHAVEN = [
    ("brick_wall_001", "https://polyhaven.com/a/brick_wall_001"),
    ("concrete_wall_001", "https://polyhaven.com/a/concrete_wall_001"),
    ("grey_plaster", "https://polyhaven.com/a/grey_plaster"),
    ("metal_plate", "https://polyhaven.com/a/metal_plate"),
    ("asphalt_02", "https://polyhaven.com/a/asphalt_02"),
]
# ambientCG id, page. Color, NormalGL and Roughness JPGs are extracted from the 1k zip.
AMBIENT = [
    ("PavingStones092", "https://ambientcg.com/a/PavingStones092"),
    ("Grass004", "https://ambientcg.com/a/Grass004"),
]


def main():
    root = skyline.project_root()
    dest = root / "SourceArt" / "CityGen" / "materials"
    dest.mkdir(parents=True, exist_ok=True)
    record = {}
    for ident, page in POLYHAVEN:
        record[ident] = fetch_polyhaven(ident, page, dest / ident)
    for ident, page in AMBIENT:
        record[ident] = fetch_ambient(ident, page, dest / ident)
    (dest / "materials.json").write_text(json.dumps(record, indent=2) + "\n")
    print("materials", len(record), "->", dest)


def fetch_polyhaven(ident, page, folder):
    folder.mkdir(parents=True, exist_ok=True)
    info = _get_json("https://api.polyhaven.com/files/" + ident)
    meta = _get_json("https://api.polyhaven.com/info/" + ident)
    authors = _authors(meta.get("authors") or {})
    dims = meta.get("dimensions") or [2000, 2000]
    # dimensions are millimetres on Poly Haven
    uv = [round(float(dims[0]) / 1000.0, 3), round(float(dims[1]) / 1000.0, 3)]
    wanted = {"Diffuse": "color", "nor_gl": "normal", "Rough": "rough"}
    maps = {}
    for api_name, slot in wanted.items():
        url = _poly_url(info, api_name)
        name = "%s_%s_1k.jpg" % (ident, slot)
        path = folder / name
        if not path.is_file() or path.stat().st_size < 1000:
            _download(url, path)
        maps[slot] = "%s/%s" % (ident, name)
    return {"author": authors, "url": page, "licence": "CC0", "date": DATE,
            "maps": maps, "uv_m": uv, "source": "Poly Haven"}


def fetch_ambient(ident, page, folder):
    folder.mkdir(parents=True, exist_ok=True)
    url = "https://ambientcg.com/get?file=%s_1K-JPG.zip" % ident
    blob = _download_bytes(url)
    wanted = {"Color": "color", "NormalGL": "normal", "Roughness": "rough"}
    maps = {}
    with zipfile.ZipFile(BytesIO(blob)) as zf:
        for info in zf.infolist():
            lower = info.filename.lower()
            if not lower.endswith(".jpg"):
                continue
            for token, slot in wanted.items():
                if token.lower() in lower and "preview" not in lower:
                    name = "%s_%s_1k.jpg" % (ident, slot)
                    path = folder / name
                    if not path.is_file() or path.stat().st_size < 1000:
                        path.write_bytes(zf.read(info))
                    maps[slot] = "%s/%s" % (ident, name)
    if set(maps) != set(wanted.values()):
        raise RuntimeError("%s zip did not contain Color, NormalGL and Roughness (%s)" % (ident, sorted(maps)))
    return {"author": "Lennart Demes", "url": page, "licence": "CC0", "date": DATE,
            "maps": maps, "uv_m": [2.0, 2.0], "source": "ambientCG",
            "licence_url": "https://docs.ambientcg.com/license/"}


def _poly_url(info, map_name):
    node = info[map_name]["1k"]["jpg"]
    return node["url"]


def _authors(authors):
    parts = []
    for name, role in authors.items():
        if isinstance(role, dict):
            role = role.get("role") or role.get("contribution") or ""
        parts.append("%s (%s)" % (name, role) if role else name)
    return ", ".join(parts) or "Poly Haven"


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _download(url, path):
    path.write_bytes(_download_bytes(url))
    print("got", path.name, path.stat().st_size)


def _download_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


if __name__ == "__main__":
    main()
