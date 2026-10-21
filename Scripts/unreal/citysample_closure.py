"""Work out which City Sample /Game packages Sky City needs, by following package references offline.

Seeds come from Saved/MCPScripts/out.json (deps.py: the /Game packages the CitySamplePCG building graphs reference
that Sky City lacks). Each .uasset's name table holds the paths of the packages it imports, so scanning the bytes
for /Game/... strings and following them gives the closure. Writes the file list to Saved/Mashup/citysample_files.txt.
Usage: python3 -I citysample_closure.py [--copy]
"""
import json, os, re, shutil, sys



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
SRC = os.environ.get("SKYCITY_CITYSAMPLE_SRC", os.path.expanduser("~/UnrealProjects/CitySample/Content"))   # the City Sample project's Content folder
DST = os.path.join(ROOT, "Content")
OUT = os.path.join(ROOT, "Saved", "MCPScripts", "out.json")
LIST = os.path.join(ROOT, "Saved", "Mashup", "citysample_files.txt")
PAT = re.compile(rb"/Game/[A-Za-z0-9_\-/]+")
EXTS = (".uasset", ".umap", ".uexp", ".ubulk", ".uptnl")


def pkg_file(pkg):
    rel = pkg[len("/Game/"):]
    for ext in (".uasset", ".umap"):
        f = os.path.join(SRC, rel + ext)
        if os.path.exists(f):
            return f
    return None


# index every City Sample package; FNames store a trailing _<number> separately, so a name-table string
# "/Game/.../MI_Wall_01" can stand for MI_Wall_01_0, MI_Wall_01_1, ...
INDEX, SUFFIXED = set(), {}
for d, _, fs in os.walk(SRC):
    for f in fs:
        if f.endswith((".uasset", ".umap")):
            pkg = "/Game/" + os.path.relpath(os.path.join(d, f.rsplit(".", 1)[0]), SRC)
            INDEX.add(pkg)
            m = re.match(r"(.*)_(\d+)$", pkg)
            if m:
                SUFFIXED.setdefault(m.group(1), []).append(pkg)

seeds = json.load(open(OUT))["missing"]
seen, stack, absent = set(), list(seeds), set()
while stack:
    p = stack.pop()
    if p in seen:
        continue
    seen.add(p)
    f = pkg_file(p)
    if not f:
        absent.add(p)
        continue
    data = open(f, "rb").read()
    for m in PAT.findall(data):
        q = m.decode()
        # a name entry can be the package or Package/Object, try both
        for c in [q] + SUFFIXED.get(q, []) + ([q.rsplit("/", 1)[0]] if "/" in q[6:] else []):
            if c not in seen and c in INDEX:
                stack.append(c)

files, total = [], 0
for p in sorted(seen - absent):
    base = os.path.join(SRC, p[len("/Game/"):])
    for ext in EXTS:
        if os.path.exists(base + ext):
            files.append(base + ext)
            total += os.path.getsize(base + ext)
open(LIST, "w").write("\n".join(files))
groups = {}
for p in seen - absent:
    k = "/".join(p.split("/")[:3])
    groups[k] = groups.get(k, 0) + 1
print("packages", len(seen - absent), "absent", len(absent), "files", len(files), "GB", round(total / 1e9, 2))
print(sorted(groups.items(), key=lambda kv: -kv[1]))
print("absent sample", sorted(absent)[:10])

if "--copy" in sys.argv:
    n = 0
    for f in files:
        d = os.path.join(DST, os.path.relpath(f, SRC))
        if os.path.exists(d) and os.path.getsize(d) == os.path.getsize(f):
            continue
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(f, d)
        n += 1
    print("copied", n)
