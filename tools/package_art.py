#!/usr/bin/env python3
"""Build the Sky City Art Pack: Kenny's own art, zipped for reuse in other projects (CC BY-NC 4.0, with credit).

    python3 tools/package_art.py --version 0.1.0 --dry-run
    python3 tools/package_art.py --version 0.1.0 --out "/Volumes/Sound Libraries/SkyCity Work/Release/ArtPack"

Python 3 standard library only. Run it from a clone with the art downloaded (`git lfs pull`). Maintainer notes:
docs/ART_PACK.md.

The zip, SkyCity-Art-Pack-v<version>.zip, holds
    UE/Content/...       Unreal 5.8 assets to drop into a project's Content/ folder, original paths kept
    Source/...           Kenny's original GLB / PNG / WAV files from SourceArt/
    LICENSE-ART.txt      the licence in short, the credit line, how to ask about commercial use
    THIRD_PARTY.txt      the CC0 / public-domain / OpenStreetMap material that Kenny's assets use, with real licences
    README.md            what is inside and how to use it

How the selection works (everything is plain data near the top of this file, so it is easy to read and to change):
  1. INCLUDE lists name the folders of Kenny's own art. Only files that git tracks are packed (a stray local file never
     slips in); `--include-untracked` lifts that.
  2. LEFT_OUT and ARTWORKS carve things out of those folders, each with a reason. Materials and textures that only the
     left-out artworks use go with them.
  3. ON_DEMAND is third-party material that may be redistributed (Poly Haven and ambientCG CC0, public-domain NAIP
     aerials). It is packed only where an included asset needs it, at its original path, so UE references do not break.
  4. DENY is the never-list. After the selection is made, any denied path still in it stops the build (exit 1, with a
     list of the offenders).
  5. Dependency scan: every .uasset is opened and the package names in its name table (and any /Game/... or
     /<Plugin>/... text in its bytes) are read. If an asset points at a package that is not in the pack, the build
     stops and names the asset and the missing reference. References to /Engine/, /Script/ and engine plugin content
     (ENGINE_MOUNTS) are fine: they come with Unreal.
  6. After the zip is written it is opened again: CRC test, the DENY list against the real entries, and the dependency
     scan once more, from the zip's own bytes.

Exit codes: 0 fine; 1 the pack would break a rule (the details are printed); 2 usage or environment problem.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(os.environ.get("SKYCITY_ROOT") or Path(__file__).resolve().parent.parent)

CREDIT_LINE = "Art by Kenny Hass Music LLC, from Sky City (https://kornontheken.itch.io/sky-city)"
ITCH_URL = "https://kornontheken.itch.io/sky-city"
REPO_URL = "https://github.com/kennyhassmusic/sky-city"
CC_URL = "https://creativecommons.org/licenses/by-nc/4.0/"
CC_LEGAL_URL = "https://creativecommons.org/licenses/by-nc/4.0/legalcode"

# ============================================================================================ what goes in

# Kenny's own folders in Content/ (UE assets only: .uasset). Description = the line in the pack's README.
CONTENT_INCLUDE = [
    ("Content/City", "The city: street surfaces, kerbs and blocks, road, street and expressway kits, the elevated L, "
                     "Chicago and Austin landmarks, parks, water and boats, the Texas Capitol, Willis Tower"),
    ("Content/McGregor", "The McGregor test site and show set: terrain, kit pieces, buildings, props, materials"),
    ("Content/SkyCity/FX", "Smoke, fire and spark materials and textures"),
    ("Content/SkyCity/Pickups", "Pressure points, wireless chargers and fuel add-ons"),
    ("Content/Vehicles/Placeholder", "Blocky stand-in cars (sedan, crossover, pickup, robotaxi, semi)"),
    ("Content/Vehicles/Shared", "Car paint, glass and lamp materials used by the stand-in cars"),
]

# Kenny's original source files in SourceArt/, by folder and file type. Metadata (.json) and scratch files are skipped.
SOURCE_INCLUDE = [
    ("SourceArt/Expressway", (".glb", ".png")),
    ("SourceArt/FX", (".png",)),
    ("SourceArt/Landmarks", (".glb", ".png", ".jpg")),      # preview renders are left out below
    ("SourceArt/McGregor", (".glb", ".png", ".wav")),
    ("SourceArt/Pickups", (".glb", ".png")),
    ("SourceArt/Rail", (".glb", ".png")),
    ("SourceArt/RoadKit", (".glb", ".png")),
    ("SourceArt/StreetKit", (".glb", ".png")),
    ("SourceArt/Vehicles/Placeholder", (".glb",)),
]

# What each group of the pack is, for its README (longest matching prefix wins).
GROUP_NOTES = {
    "Content/City/AustinSights": "Austin: bridges, boats and docks, 6th Street neon, storefronts, the moonlight tower, Treaty Oak",
    "Content/City/Capitol": "The Texas Capitol building, dome, fence and grounds",
    "Content/City/Expressway": "Elevated expressway kit: decks, piers, ramps, signs",
    "Content/City/Landmarks": "Chicago landmarks: Buckingham Fountain, Navy Pier and its wheel, bridges, plazas",
    "Content/City/Parks": "Grant Park, Millennium Park and other Chicago parks and buildings",
    "Content/City/Rail": "The elevated L: spans, columns, stations, a train car",
    "Content/City/Roads": "Road kit and road meshes",
    "Content/City/Street": "Street kit: signals, lamps, signs, trees, street furniture, surface materials and textures",
    "Content/City/Water": "The Chicago River and lakefront: docks, locks, boats, riverwalk",
    "Content/City/Willis": "Willis Tower",
    "Content/McGregor": "The McGregor test site and show set",
    "Content/SkyCity/FX": "Smoke, fire and spark effects",
    "Content/SkyCity/Pickups": "Pressure points, chargers and fuel add-ons",
    "Content/Vehicles/Placeholder": "Blocky stand-in cars",
    "Content/Vehicles/Shared": "Car paint, glass and lamp materials",
    "SourceArt/Expressway": "Expressway kit models and textures",
    "SourceArt/FX": "Effect textures",
    "SourceArt/Landmarks": "Landmark, park, water, Austin, Capitol and Willis Tower models",
    "SourceArt/McGregor": "McGregor kit and site models, textures and the engine-test roar (WAV)",
    "SourceArt/Pickups": "Pickup and charger models",
    "SourceArt/Rail": "The elevated L kit",
    "SourceArt/RoadKit": "Road kit models and textures",
    "SourceArt/StreetKit": "Street kit models and textures",
    "SourceArt/Vehicles/Placeholder": "Blocky stand-in cars",
}

# Third-party material that is free to redistribute. Packed only where an included asset needs it (see the docstring).
ON_DEMAND = [
    r"^Content/City/Street/PolyHaven/",                                   # Poly Haven props (CC0)
    r"^Content/City/Street/Textures/(?!Kit/)[^/]+/",                      # Poly Haven surface scans (CC0)
    r"^Content/McGregor/Textures/(naip_[^/]*|overview_2048)\.uasset$",    # USDA NAIP aerial photos (public domain)
]

# Artworks that are still in copyright. Sky City has simplified stand-ins for them; the stand-ins stay in the game and
# the repo but are not in the Art Pack. Names are matched as whole file or folder names, in Content/ and SourceArt/.
ARTWORKS = [
    ("Cloud Gate (the Bean), Anish Kapoor", ["LM_CloudGate", "SM_Landmark_TheBean"]),
    ("Jay Pritzker Pavilion and its trellis, Frank Gehry", ["PK_PritzkerPavilion", "PK_PritzkerTrellis"]),
    ("BP Bridge, Frank Gehry", ["PK_BPBridge"]),
    ("Crown Fountain, Jaume Plensa", ["PK_CrownFountain", "PK_CrownFountainWater"]),
    ("Flamingo, Alexander Calder", ["PK_Flamingo"]),
    ("The Four Seasons, Marc Chagall", ["PK_FourSeasons"]),
    ("Miro's Chicago, Joan Miro", ["PK_MiroChicago"]),
    ("Austin statues (Stevie Ray Vaughan, Angelina Eberly, Willie Nelson); CREDITS_AND_LICENCES.txt lists 'the Austin statues'",
     ["LM_ATX_SRVStatue", "LM_ATX_EberlyStatue", "LM_ATX_WillieStatue"]),
    ("Texas Capitol grounds monuments (modern memorials; their sculptors' rights are not checked, so they are held back)",
     ["LM_ATX_Cap_" + n for n in ("AfricanAmerican", "Children", "DisabledVets", "Liberty", "NationalGuard",
                                  "PeaceOfficers", "PearlHarbor", "PioneerWoman", "Tejano", "TenCommandments",
                                  "Vietnam", "WWII")]),
]
ART_RE = re.compile(r"(?:^|/)(?P<name>%s)(?:/|\.[A-Za-z0-9]+$)" % "|".join(
    re.escape(n) for _, names in ARTWORKS for n in names), re.I)

# Other things left out of the folders above. (path prefix, reason)
LEFT_OUT = [
    ("Content/City/Meshes", "greybox meshes from before the real models: they use Content/Blockout materials "
                            "(Blockout never ships) and one of them is a Cloud Gate stand-in"),
    ("Content/McGregor/Meshes/SM_MG_Ponds.uasset", "uses a Content/Blockout water material (Blockout never ships)"),
]
# Preview renders: some show the artwork stand-ins above, so none of them are packed.
PREVIEW_RE = re.compile(r"^SourceArt/Landmarks/(?:.*/)?(?:preview|overview)_[^/]*$", re.I)

# The never-list. Checked against the final selection and against the zip itself. (regex, reason)
DENY = [
    (r"^Content/(Building|Prop|Material|Megascans|MSPresets|Textures|Environment)(/|$)", "Epic City Sample content"),
    (r"^Plugins(/|$)", "plugins (City Sample's PCG plugin and others)"),
    (r"^Content/Vehicles/Tesla(/|$)", "licensed vehicle models"),
    (r"^SourceArt/Vehicles/(?!Placeholder(/|$))", "licensed vehicle models"),
    (r"^SourceArt/Reference(/|$)", "reference photos"),
    (r"^Content/Vehicles/(Roadster|RoadsterRig)(/|$)", "the Skyster Roadster (LICENSE-ASSETS.md section 4)"),
    (r"^SourceArt/(roadster_master\.glb|RoadsterRig)(/|$)", "the Skyster Roadster (LICENSE-ASSETS.md section 4)"),
    (r"^SourceArt/Brand(/|$)", "the Volta brand logo"),
    (ART_RE.pattern, "stand-in of an artwork that is still in copyright"),
    (PREVIEW_RE.pattern, "preview render (some show the artwork stand-ins)"),
    (r"^Content/(Maps|__External\w*|Blockout|Developers|Collections)(/|$)", "maps, level data, blockout, per-user folders"),
    (r"^Content/SkyCity/(Blueprints|Data|PCG|HUD)(/|$)", "Blueprints, game data and HUD: only make sense with the game's C++"),
    (r"^SourceArt/(CC0|osm)(/|$)", "CC0 source downloads and OpenStreetMap extracts (not Kenny's art)"),
    (r"^(Source|Scripts|Config|Saved|Binaries|Intermediate|Build|DerivedDataCache|\.git|\.github|docs|Design)(/|$)",
     "code, config and project files: not art"),
]
DENY_RES = [(re.compile(rx, re.I), why) for rx, why in DENY]

# Package mounts that ship with Unreal Engine 5.8, so assets may point at them freely.
ENGINE_MOUNTS = {"engine", "script", "interchangeassets"}

# ============================================================================================ small helpers


def under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%d %s" % (n, unit) if unit == "B" else "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f GB" % n


def die(msg: str, code: int = 2):
    print("error: " + msg, file=sys.stderr)
    sys.exit(code)


def deny_reason(rel: str):
    for rx, why in DENY_RES:
        if rx.search(rel):
            return why
    return None


def group_of(rel: str) -> str:
    """The README group a file belongs to: the longest GROUP_NOTES key that is a prefix of it."""
    best = ""
    for key in GROUP_NOTES:
        if under(rel, key) and len(key) > len(best):
            best = key
    return best or "/".join(rel.split("/")[:2])


def pack_path(rel: str) -> str:
    """Where a project file lives inside the zip."""
    if rel.startswith("Content/"):
        return "UE/" + rel
    if rel.startswith("SourceArt/"):
        return "Source/" + rel[len("SourceArt/"):]
    raise ValueError(rel)


def rel_from_pack_path(name: str):
    if name.startswith("UE/Content/"):
        return name[len("UE/"):]
    if name.startswith("Source/"):
        return "SourceArt/" + name[len("Source/"):]
    return None


# ============================================================================================ reading .uasset files

LFS_MAGIC = b"version https://git-lfs.github.com/spec"
PKG_NAME_RE = re.compile(r"^/[A-Za-z0-9_]+(?:/[A-Za-z0-9_\-+. ]+)+$")
_SUFFIX_NUM = re.compile(r"^(.*)_(0|[1-9][0-9]{0,8})$")        # how Unreal splits "Name_12" into "Name" + number


def parse_summary(b: bytes):
    """(total header size, name count, name offset) from a UE 5.x package header, or None if the layout is unknown."""
    try:
        tag, legacy = struct.unpack_from("<ii", b, 0)
        if (tag & 0xFFFFFFFF) != 0x9E2A83C1 or legacy > -7:
            return None
        off = 8
        if legacy != -4:
            off += 4                                        # legacy UE3 version
        off += 4                                            # UE4 file version
        ue5 = 0
        if legacy <= -8:
            ue5 = struct.unpack_from("<i", b, off)[0]
            off += 4
        off += 4                                            # licensee version
        if ue5 >= 1016:
            off += 20                                       # saved hash (FIoHash)
        total = struct.unpack_from("<i", b, off)[0]
        off += 4
        custom = struct.unpack_from("<i", b, off)[0]
        off += 4
        if not 0 <= custom <= 4096:
            return None
        off += 20 * custom                                  # custom versions: GUID + int32
        flen = struct.unpack_from("<i", b, off)[0]
        off += 4
        off += flen if flen >= 0 else -2 * flen             # folder name
        _flags, ncount, noff = struct.unpack_from("<iii", b, off)
        if not (0 < ncount < 5_000_000 and 0 < noff < total):
            return None
        return total, ncount, noff
    except struct.error:
        return None


def read_names(b: bytes, count: int, offset: int):
    """The package's name table."""
    p = offset
    for _ in range(count):
        n = struct.unpack_from("<i", b, p)[0]
        p += 4
        if n < 0:
            end = p - 2 * n
            s = b[p:end - 2].decode("utf-16-le", "replace")
            p = end
        else:
            s = b[p:p + n - 1].decode("latin-1")
            p += n
        p += 4                                              # the two name hashes
        yield s


def normalize(name: str) -> str:
    """'/Game/A/B.B', '/Game/A/B:Sub' and '/Game/A/B/' -> '/Game/A/B'."""
    name = name.rstrip("./").split(":")[0]
    head, _, last = name.rpartition("/")
    return head + "/" + last.split(".")[0]


class Mounts:
    """The package mount points of this project: /Game and one per plugin folder in Plugins/."""

    def __init__(self):
        self.plugins = {}
        pdir = ROOT / "Plugins"
        if pdir.is_dir():
            for d in sorted(pdir.iterdir()):
                if (d / "Content").is_dir():
                    self.plugins[d.name.lower()] = d.name
        names = ["Game"] + sorted(self.plugins.values())
        self.byte_re = re.compile(rb"/(?:%s)/[A-Za-z0-9_\-+./]+" % b"|".join(n.encode() for n in names))


def package_refs(data: bytes, mounts: Mounts):
    """Names of the packages that a .uasset's bytes point at, and whether its name table could be read."""
    found = set()
    parsed = False
    s = parse_summary(data[:8192])
    if s:
        total, ncount, noff = s
        try:
            for n in read_names(data[:total], ncount, noff):
                if PKG_NAME_RE.match(n):
                    found.add(n)
            parsed = True
        except (struct.error, IndexError, ValueError):
            parsed = False
    for m in mounts.byte_re.finditer(data):                  # the audit's way: look for the text itself
        found.add(m.group(0).decode("latin-1"))
    return {normalize(n) for n in found}, parsed


class Project:
    """Every package in the project, so a reference can be turned back into a file."""

    def __init__(self):
        self.mounts = Mounts()
        self.index = {}                                      # lower-case package name -> (package name, relative path)
        self.by_base = collections.defaultdict(set)          # name without Unreal's trailing _<number> -> package names
        self.folders = set()                                 # lower-case content folders (importers record those too)
        self._add("Game", ROOT / "Content")
        for real in self.mounts.plugins.values():
            self._add(real, ROOT / "Plugins" / real / "Content")
        for low in self.index:
            m = _SUFFIX_NUM.match(low)
            self.by_base[m.group(1) if m else low].add(low)

    def _add(self, mount: str, base: Path):
        for dp, _dn, fn in os.walk(base):
            for f in fn:
                stem, ext = os.path.splitext(f)
                if ext.lower() in (".uasset", ".umap"):
                    full = Path(dp) / stem
                    pkg = "/" + mount + "/" + full.relative_to(base).as_posix()
                    rel = (Path(dp) / f).relative_to(ROOT).as_posix()
                    self.index[pkg.lower()] = (pkg, rel)
                    parent = pkg.lower().rpartition("/")[0]
                    while parent.count("/") >= 1 and parent not in self.folders:
                        self.folders.add(parent)
                        parent = parent.rpartition("/")[0]

    def resolve(self, name: str):
        """Files that a package name may mean. Unreal stores 'Foo_3' as the name 'Foo' plus a number, so a name can stand
        for several packages; all of them count (the check is on the safe side)."""
        low = name.lower()
        if low in self.folders and low not in self.index:
            return []                                        # a content folder (an importer's destination), not a package
        hits = {low} if low in self.index else set()
        hits |= self.by_base.get(low, set())
        return sorted(self.index[h] for h in hits)

    def kind(self, name: str) -> str:
        """'engine' (ships with Unreal), 'project' (/Game or a plugin folder here) or 'other'."""
        mount = name.split("/")[1].lower()
        if mount in ENGINE_MOUNTS:
            return "engine"
        if mount == "game" or mount in self.mounts.plugins:
            return "project"
        return "other"


# ============================================================================================ choosing the files


def git_tracked():
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", "Content", "SourceArt"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {p for p in out.decode("utf-8", "surrogateescape").split("\0") if p}


class Selection:
    def __init__(self):
        self.core = {}                                       # rel -> size: Kenny's own files
        self.pool = {}                                       # rel -> size: third-party files, only if needed
        self.needed = {}                                     # pool rel -> the file that needs it
        self.left_out = collections.defaultdict(list)        # reason -> [rel]
        self.artworks = []                                   # rel of the artwork stand-ins found (not packed)
        self.untracked = []
        self.ignored = collections.Counter()                 # extension -> count (SourceArt metadata etc.)

    def files(self) -> dict:
        out = dict(self.core)
        for rel in self.needed:
            out[rel] = self.pool[rel]
        return out


def walk_files(prefix: str):
    base = ROOT / prefix
    if not base.is_dir():
        die("%s is not here. Is this a full checkout (git lfs pull)?" % prefix)
    for dp, dn, fn in os.walk(base):
        dn[:] = sorted(d for d in dn if not d.startswith("."))
        for f in sorted(fn):
            if f.startswith("."):
                continue
            p = Path(dp) / f
            if p.is_symlink():
                continue
            yield p.relative_to(ROOT).as_posix(), p


def collect(tracked, include_untracked: bool, errors: list) -> Selection:
    sel = Selection()
    on_demand = [re.compile(rx) for rx in ON_DEMAND]
    todo = [(p, None) for p, _ in CONTENT_INCLUDE] + [(p, e) for p, e in SOURCE_INCLUDE]
    for prefix, exts in todo:
        for rel, path in walk_files(prefix):
            ext = os.path.splitext(rel)[1].lower()
            if exts is None:
                if ext != ".uasset":
                    errors.append("%s: unexpected file type in an included Content folder (only .uasset is packed)" % rel)
                    continue
            elif ext not in exts:
                sel.ignored[ext or "(none)"] += 1
                continue
            if tracked is not None and not include_untracked and rel not in tracked:
                sel.untracked.append(rel)
                continue
            size = path.stat().st_size
            if ART_RE.search(rel):
                sel.artworks.append(rel)
                continue
            if PREVIEW_RE.search(rel):
                sel.left_out["preview render (some show the in-copyright artwork stand-ins)"].append(rel)
                continue
            why = next((w for p, w in LEFT_OUT if under(rel, p)), None)
            if why:
                sel.left_out[why].append(rel)
                continue
            if any(rx.search(rel) for rx in on_demand):
                sel.pool[rel] = size
            else:
                sel.core[rel] = size
    return sel


def check_lfs(sel: Selection, errors: list):
    pointers = []
    for rel in list(sel.core) + list(sel.pool):
        if sel.core.get(rel, sel.pool.get(rel, 1 << 30)) < 1024:
            with open(ROOT / rel, "rb") as f:
                if f.read(len(LFS_MAGIC)) == LFS_MAGIC:
                    pointers.append(rel)
    if pointers:
        errors.append("%d file(s) are Git LFS pointers, not the art (run `git lfs pull`), for example:\n    %s"
                      % (len(pointers), "\n    ".join(pointers[:10])))


class RefCache:
    def __init__(self, project: Project):
        self.project = project
        self.cache = {}
        self.unparsed = []

    def refs(self, rel: str):
        """The package names that the .uasset at rel points at (read once, then remembered)."""
        if rel not in self.cache:
            data = (ROOT / rel).read_bytes()
            names, parsed = package_refs(data, self.project.mounts)
            if not parsed:
                self.unparsed.append(rel)
            self.cache[rel] = names
        return self.cache[rel]


def prune_artwork_leftovers(sel: Selection, project: Project, cache: RefCache):
    """Materials and textures that only the left-out artworks use go with them (found by their references)."""
    art_files = {rel for rel in sel.artworks if rel.endswith(".uasset")}
    referrers = collections.defaultdict(set)
    for src in list(sel.core) + sorted(art_files):
        if not src.endswith(".uasset"):
            continue
        for name in cache.refs(src):
            if project.kind(name) != "project":
                continue
            for _pkg, target in project.resolve(name):
                if target != src:
                    referrers[target].add(src)
    pruned = {}
    changed = True
    while changed:
        changed = False
        like_art = art_files | set(pruned)
        for rel in sorted(sel.core):
            if rel in pruned or not rel.endswith(".uasset"):
                continue
            who = referrers.get(rel, set())
            if who and who <= like_art:
                pruned[rel] = sorted(who)[0]
                changed = True
    for rel in pruned:
        del sel.core[rel]
        sel.left_out["only used by the left-out artwork stand-ins"].append(rel)


def close_over_dependencies(sel: Selection, project: Project, cache: RefCache):
    """Pull in the on-demand third-party files that included assets need; report every other missing reference."""
    problems = []
    queue = sorted(r for r in sel.core if r.endswith(".uasset"))
    pool_by_rel = sel.pool
    left_out_set = {rel for rels in sel.left_out.values() for rel in rels}
    art_set = set(sel.artworks)
    untracked = set(sel.untracked)
    queue_seen = set(queue)
    while queue:
        src = queue.pop()
        for name in sorted(cache.refs(src)):
            kind = project.kind(name)
            if kind == "engine":
                continue
            if kind == "other":
                problems.append((src, name, "mount point is not in this project and not a known Unreal Engine mount "
                                            "(add it to ENGINE_MOUNTS if it ships with UE 5.8)"))
                continue
            hits = project.resolve(name)
            if not hits:
                if name.lower() not in project.folders:
                    problems.append((src, name, "no such package in the project"))
                continue
            for pkg, target in hits:
                if target == src or target in sel.core or target in sel.needed:
                    continue
                if target in pool_by_rel:
                    sel.needed[target] = src
                    if target not in queue_seen:
                        queue_seen.add(target)
                        queue.append(target)
                    continue
                if target in art_set:
                    why = "an in-copyright artwork stand-in (left out)"
                elif target in untracked:
                    why = "not tracked by git"
                elif target in left_out_set:
                    why = "left out of the pack"
                elif deny_reason(target):
                    why = "never goes in the pack: " + deny_reason(target)
                else:
                    why = "not on the include list"
                problems.append((src, name, "%s is %s" % (pkg, why)))
    return problems


def check_deny(files, errors: list):
    bad = [(rel, deny_reason(rel)) for rel in sorted(files) if deny_reason(rel)]
    if bad:
        lines = ["%d denied path(s) would be in the pack:" % len(bad)]
        lines += ["    %s   [%s]" % (rel, why) for rel, why in bad[:50]]
        if len(bad) > 50:
            lines.append("    ... and %d more" % (len(bad) - 50))
        errors.append("\n".join(lines))


def report_problems(problems, errors: list):
    if not problems:
        return
    lines = ["Dependency check failed: %d reference(s) to packages that are not in the pack:" % len(problems)]
    for src, name, why in problems[:60]:
        lines.append("    %s\n        points at %s: %s" % (src, name, why))
    if len(problems) > 60:
        lines.append("    ... and %d more" % (len(problems) - 60))
    lines.append("  Fix: leave the asset out (LEFT_OUT), or add the folder it needs to the include lists if it may ship.")
    errors.append("\n".join(lines))


# ============================================================================================ the text files

OSM_FOLDERS = [
    "UE/Content/City/Street/Meshes (block, kerb, overlay and paint tiles)",
    "UE/Content/City/Roads/Meshes (road tiles)",
    "UE/Content/McGregor/Meshes (roads, buildings, lots)",
    "the outlines and positions of the landmark, park, water and Austin models",
]


def third_party_entries(files):
    """Group the packed third-party files by provider, from their paths."""
    ph_models, ph_tex = set(), set()
    naip = []
    for rel in files:
        m = re.match(r"^Content/City/Street/PolyHaven/([^/]+)/", rel)
        if m:
            ph_models.add(m.group(1))
        m = re.match(r"^Content/City/Street/Textures/(?!Kit/)([^/]+)/", rel)
        if m:
            ph_tex.add(m.group(1))
        if re.match(r"^Content/McGregor/Textures/(naip_[^/]*|overview_2048)\.uasset$", rel):
            naip.append(rel)
    return sorted(ph_models), sorted(ph_tex), sorted(naip)


def make_third_party(files) -> str:
    ph_models, ph_tex, naip = third_party_entries(files)
    has = lambda pat: any(re.search(pat, r) for r in files)       # noqa: E731
    out = []
    w = out.append
    w("SKY CITY ART PACK - THIRD-PARTY MATERIAL")
    w("")
    w("Most of this pack is Kenny Hass Music LLC's own art (see LICENSE-ART.txt). The material below is made by others.")
    w("All of it may be redistributed. Each item keeps its own licence, which is not CC BY-NC.")
    w("")
    w("Not in this pack, on purpose: Epic's City Sample, licensed car models, reference photos, the Skyster Roadster,")
    w("and stand-ins of artworks that are still in copyright.")
    w("")
    w("-" * 78)
    w("1. POLY HAVEN (CC0 1.0, public domain dedication)")
    w("   Licence: https://polyhaven.com/license  (https://creativecommons.org/publicdomain/zero/1.0/)")
    w("   Credit is not required; it is given here anyway. Included because Sky City's materials use them.")
    if ph_tex:
        w("   Surface scans (textures), UE/Content/City/Street/Textures/<name>/ :")
        for n in ph_tex:
            w("     %-24s https://polyhaven.com/a/%s" % (n, n))
    if ph_models:
        w("   Props (models and their textures), UE/Content/City/Street/PolyHaven/<name>/ :")
        for n in ph_models:
            w("     %-24s https://polyhaven.com/a/%s" % (n, n))
    w("")
    w("2. AMBIENTCG (CC0 1.0)")
    w("   Licence: https://docs.ambientcg.com/license/")
    if has(r"T_Leaves_"):
        w("   The street trees' leaf-cluster textures (T_Leaves_*_C / _N, in UE/Content/City/Street/Textures/Kit and")
        w("   Source/StreetKit/textures) were cut and composed from ambientCG's leaf scans:")
        w("     LeafSet002 https://ambientcg.com/view?id=LeafSet002  (live oak, honey locust)")
        w("     LeafSet004 https://ambientcg.com/view?id=LeafSet004  (linden)")
        w("     LeafSet005 https://ambientcg.com/view?id=LeafSet005  (elm)")
    w("")
    if has(r"T_Expwy_") or has(r"^SourceArt/Expressway/textures/"):
        w("3. POLY HAVEN, AS A BASE (CC0 1.0)")
        w("   The expressway panel texture T_Expwy_MSE_C was painted over Poly Haven's concrete_floor_01")
        w("   (https://polyhaven.com/a/concrete_floor_01).")
        w("")
    w("4. USDA NAIP AERIAL IMAGERY (public domain)")
    w("   National Agriculture Imagery Program, US Department of Agriculture, fetched from the USGS National Map")
    w("   (https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer). Works of the US federal")
    w("   government are in the public domain.")
    if naip:
        w("   Used for the McGregor terrain and horizon:")
        for rel in naip:
            w("     UE/%s" % rel)
    w("")
    w("5. USGS 3D ELEVATION PROGRAM (public domain)")
    w("   The McGregor terrain meshes (UE/Content/McGregor/Meshes/SM_MG_Terrain_*) were built from USGS 3DEP elevation")
    w("   data (https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer). US federal government")
    w("   data is in the public domain.")
    w("")
    w("6. OPENSTREETMAP (ODbL 1.0)")
    w("   (c) OpenStreetMap contributors. https://www.openstreetmap.org/copyright")
    w("   Some geometry was generated from OpenStreetMap data (street, block, building-footprint and landmark outlines).")
    w("   We treat the meshes as 'produced works' under the Open Database License (https://opendatacommons.org/licenses/odbl/):")
    w("   you may use them under CC BY-NC as described in LICENSE-ART.txt, and you must credit OpenStreetMap, for example")
    w("   'Contains information from OpenStreetMap, (c) OpenStreetMap contributors'. If you share the underlying street")
    w("   data itself, the ODbL's share-alike rule applies to that data. Most affected:")
    for f in OSM_FOLDERS:
        w("     " + f)
    w("")
    w("7. FONTS")
    w("   Lettering on some sign and road-marking textures (Source/StreetKit/textures, Source/RoadKit/textures,")
    w("   Source/Expressway/textures and the matching UE textures) was drawn with fonts installed in macOS. Only the finished")
    w("   pictures are in this pack; no font files are.")
    w("")
    w("8. UNREAL ENGINE")
    w("   The .uasset files were saved with Unreal Engine 5.8 (5.8.3). Many materials use Epic's engine-supplied glTF")
    w("   material instances (the 'InterchangeAssets' plugin, on by default); they come with Unreal and are not in this")
    w("   pack. Unreal(R) and its logo are Epic Games' trademarks or registered trademarks in the US and elsewhere.")
    w("")
    w("9. HOW THE ART WAS MADE")
    w("   The models are built by Python scripts in headless Blender (Sky City repository, Scripts/) and imported into")
    w("   Unreal. Parts of the code and art were made with the help of generative AI (Claude).")
    w("")
    return "\n".join(out) + "\n"


def make_license(version: str) -> str:
    year = datetime.date.today().year
    return """SKY CITY ART PACK, version %(v)s
(c) %(y)s Kenny Hass Music LLC. %(itch)s

LICENCE
  Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
  Summary:     %(cc)s
  Legal code:  %(legal)s
  This text is a short guide. The legal code is what counts.

IN SHORT
  You may copy, share, remix and build on this art, in any format, for NONCOMMERCIAL purposes, if you
    - give credit (the line below), link to the licence, and say if you changed the art; and
    - add no extra legal terms or technical locks that stop others doing what this licence lets them do.
  "Noncommercial" means not primarily meant to earn money. Selling the art, selling or monetizing a game or product that
  contains it, or using it in advertising is commercial use.

CREDIT LINE (use it as written)
  %(credit)s

COMMERCIAL USE
  Commercial use needs written permission. Message Kenny Hass Music LLC through %(itch)s

STREAMS AND VIDEOS
  Monetized streams and videos are OK. Showing the art, or your noncommercial project made with it, in a monetized
  stream or video is fine (credit it as usual). This is a permission on top of CC BY-NC.

NOT INCLUDED AND NOT LICENSED
  - The names "Sky City" and "Skyster" and their logos, and the Skyster Roadster car. The Roadster is not in this pack.
    Do not use the names, logos or the car design in your own project without written permission.
  - The Volta Motors logo. It is not in this pack.
  - Epic's City Sample, licensed car models, reference photos, and stand-ins of artworks that are still in copyright:
    none of these are in this pack.

THIRD-PARTY MATERIAL
  A few items (CC0 textures and props, public-domain aerial photos, OpenStreetMap-derived geometry) keep their own
  licences. THIRD_PARTY.txt lists them. They are not covered by CC BY-NC.

REAL PLACES
  Sky City shows real cities as its setting. Names of real places and buildings only identify them. Their owners do not
  sponsor or endorse this art.

NO WARRANTY
  The art is provided as it is, without any warranty. The full wording is in the legal code above.
""" % {"v": version, "y": year, "itch": ITCH_URL, "cc": CC_URL, "legal": CC_LEGAL_URL, "credit": CREDIT_LINE}


def make_readme(version: str, files, left_out_summary, artworks_left) -> str:
    groups = collections.OrderedDict()
    for rel in sorted(files):
        g = group_of(rel)
        e = groups.setdefault(g, [0, 0])
        e[0] += 1
        e[1] += files[rel]
    rows_ue, rows_src = [], []
    for g, (n, size) in groups.items():
        row = "| `%s` | %s | %d | %s |" % (pack_path(g) if "/" in g else g, GROUP_NOTES.get(g, ""), n, human(size))
        (rows_ue if g.startswith("Content") else rows_src).append(row)
    head = "| Folder | What it is | Files | Size |\n|---|---|---:|---:|\n"
    left = "\n".join("- %s" % s for s in left_out_summary)
    return """# Sky City Art Pack v%(v)s

Kenny Hass Music LLC's art from **Sky City**, a driving and flying game set in a fusion of Chicago and Austin
(%(itch)s). Free to use in your own **noncommercial** projects, **with credit**.

> **Credit line:** %(credit)s

Licence: [CC BY-NC 4.0](%(cc)s). Details and how to ask about commercial use: `LICENSE-ART.txt`.
Monetized streams and videos are OK. Third-party material (CC0 textures, public-domain aerials, OpenStreetMap-derived
geometry) is listed in `THIRD_PARTY.txt`.

## What is inside

```
UE/Content/...     Unreal Engine 5.8 assets (.uasset), original paths kept
Source/...         the original GLB / PNG / WAV files they were made from
LICENSE-ART.txt    the licence in short and the credit line
THIRD_PARTY.txt    third-party material and its licences
README.md          this file
```

### UE/Content (Unreal Engine 5.8)

%(head)s%(ue)s

### Source (GLB / PNG / WAV)

%(head)s%(src)s

The models are glTF 2.0 binary files (`.glb`), in metres, made by Python scripts that run in Blender (the scripts are in
the Sky City repository, %(repo)s, folder `Scripts/`). Single objects are centred on their origin. "Site" pieces
(plazas, parks, Navy Pier, bridge additions) are modelled around their real-world site origin and turned to Unreal's
axes, so in another program they may look offset or rotated: use the Move / Rotate tools to put them where you want.

## Use in Unreal Engine 5.8

1. Unzip the pack into a new, empty folder.
2. Close your project's editor (optional, but tidier).
3. Copy the folders inside `UE/Content/` (`City`, `McGregor`, `SkyCity`, `Vehicles`) into your project's `Content/`
   folder, merging with what is there. **Keep the folder names and layout exactly:** assets find each other by path
   (for example `/Game/City/Street/Materials/MI_Asphalt`), so renaming or moving a folder breaks the links.
4. Open your project. The assets appear in the Content Browser under `City`, `McGregor`, `SkyCity` and `Vehicles`.

Good to know:
- The assets were saved with **Unreal Engine 5.8.3**. Older engine versions cannot open them.
- The meshes came in through Unreal's glTF (Interchange) importer, and many materials are children of Epic's
  `InterchangeAssets` material instances. That plugin is on by default; if you see missing `/InterchangeAssets/...`
  parents, turn it on in Edit > Plugins.
- Keep a backup of your project before you merge; the copy overwrites files that have the same path.

## Use in Blender, Godot, Unity or anything else

Use the files in `Source/`.
- **Blender:** File > Import > glTF 2.0 (.glb/.gltf).
- **Godot 4:** drop the `.glb` files into your project; Godot imports them as scenes.
- **Unity:** Unity does not read glTF by itself. Add the glTFast package (Package Manager), or import into Blender and
  export FBX.
- The GLBs carry named material slots (`M_...`) with plain colours, **not textures**. The textures are the PNG files in
  the `textures` folders next to the models (`Source/StreetKit/textures`, `Source/Expressway/textures`, ...), and the
  finished materials are in `UE/Content`. In another program, make your own materials for the slots.
- glTF is Y-up, in metres. The engine-test roar is a WAV.

## Credit rule

Anything you make with this art that people can see (a game, a video, a render, a website) needs the credit line
somewhere findable, such as your credits screen, your page description or the video description:

> %(credit)s

If you changed the art, say so ("modified from ..."). Please also credit the third-party sources in `THIRD_PARTY.txt`
where they apply (OpenStreetMap needs it).

## Not in the pack

%(left)s

## Names

Some stand-in assets still carry the names of real cars (folders such as `Vehicles/Placeholder/Model3`) because the game
is being moved to its invented brand, Volta Motors. The models are blocky originals, not the real cars. The names are
expected to change in a later pack, and so will the paths.

## Questions

Message Kenny Hass Music LLC through %(itch)s . The source code of Sky City, and the scripts that made this art, are at
%(repo)s .
""" % {"v": version, "itch": ITCH_URL, "credit": CREDIT_LINE, "cc": CC_URL, "head": head,
       "ue": "\n".join(rows_ue), "src": "\n".join(rows_src), "repo": REPO_URL, "left": left}


# ============================================================================================ the zip


def left_out_lines(sel: Selection):
    """The README's 'not in the pack' list."""
    arts = ", ".join(t.split(",")[0].split(" (")[0] for t, _ in ARTWORKS[:7])
    lines = [
        "Epic's City Sample (buildings, props, materials, Megascans, the PCG plugin): Epic's content, never redistributed.",
        "Licensed car models: only the blocky stand-ins are here.",
        "The Skyster Roadster and its rig, and the Volta Motors logo: reserved.",
        "Reference photos, CC0 source downloads and OpenStreetMap extracts.",
        "Maps and level data, Blueprints, game data and the HUD: they only make sense with the game's C++.",
        "Preview renders: some show the in-copyright artwork stand-ins.",
        "Stand-ins of artworks that are still in copyright (%s), plus the Austin statues and the Texas Capitol "
        "grounds monuments." % arts,
    ]
    for prefix, why in LEFT_OUT:
        if sel.left_out.get(why):
            lines.append("`%s`: %s." % (prefix, why))
    return lines


def compress_type(rel: str):
    return zipfile.ZIP_STORED if rel.lower().endswith((".png", ".jpg", ".jpeg")) else zipfile.ZIP_DEFLATED


def write_zip(zip_path: Path, files, texts, say):
    part = zip_path.with_name(zip_path.name + ".part")
    total = sum(files.values())
    done = 0
    t0 = time.time()
    with zipfile.ZipFile(part, "w", allowZip64=True) as zf:
        for name, body in texts:
            zi = zipfile.ZipInfo(name, date_time=time.localtime()[:6])
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, body)
        for rel in sorted(files):
            src = ROOT / rel
            st = src.stat()
            zi = zipfile.ZipInfo(pack_path(rel), date_time=time.localtime(max(st.st_mtime, 315532800))[:6])
            zi.compress_type = compress_type(rel)
            zi.external_attr = 0o644 << 16
            with open(src, "rb") as fin, zf.open(zi, "w", force_zip64=st.st_size > (1 << 30)) as fout:
                shutil.copyfileobj(fin, fout, 1 << 20)
            done += st.st_size
            if say and time.time() - t0 > 5:
                print("  ... %s of %s packed" % (human(done), human(total)), flush=True)
                t0 = time.time()
    os.replace(part, zip_path)


def verify_zip(zip_path: Path, planned, project: Project, errors: list) -> dict:
    """Open the finished zip again: CRC test, the never-list on the real entries, and the dependency scan from the zip's
    own bytes (every reference must lead to a file that is really in the zip, or to Unreal Engine)."""
    info = {"entries": 0, "ue": 0, "source": 0}
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad:
            errors.append("zip CRC test failed at " + bad)
            return info
        names = [i.filename for i in zf.infolist()]
        info["entries"] = len(names)
        in_pack = {}                                         # project path -> zip entry name
        for n in names:
            rel = rel_from_pack_path(n)
            if rel is None:
                if n not in ("LICENSE-ART.txt", "THIRD_PARTY.txt", "README.md"):
                    errors.append("unexpected entry in the zip: " + n)
                continue
            info["ue" if n.startswith("UE/") else "source"] += 1
            in_pack[rel] = n
        check_deny(in_pack, errors)
        extra = set(in_pack) - set(planned)
        missing = set(planned) - set(in_pack)
        if extra or missing:
            errors.append("zip does not match the plan: %d unexpected, %d missing" % (len(extra), len(missing)))
        problems = []
        for rel, n in sorted(in_pack.items()):
            if not rel.endswith(".uasset"):
                continue
            names_, _ = package_refs(zf.read(n), project.mounts)
            for name in sorted(names_):
                kind = project.kind(name)
                if kind == "engine":
                    continue
                if kind == "other":
                    problems.append((rel, name, "unknown mount point"))
                    continue
                hits = project.resolve(name)
                if not hits and name.lower() not in project.folders:
                    problems.append((rel, name, "no such package"))
                for pkg, target in hits:
                    if target != rel and target not in in_pack:
                        problems.append((rel, name, "%s is not in the zip" % pkg))
        if problems:
            lines = ["dependency check on the finished zip failed (%d):" % len(problems)]
            lines += ["    %s points at %s: %s" % p for p in problems[:30]]
            errors.append("\n".join(lines))
    return info


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================================================ main


def summarise(files, title):
    groups = collections.OrderedDict()
    for rel in sorted(files):
        g = group_of(rel)
        e = groups.setdefault(g, [0, 0])
        e[0] += 1
        e[1] += files[rel]
    print(title)
    for g, (n, size) in groups.items():
        print("  %-38s %6d files %10s" % (g, n, human(size)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the Sky City Art Pack zip (see docs/ART_PACK.md).")
    ap.add_argument("--version", required=True, help="pack version, like 0.1.0 (also the file name)")
    ap.add_argument("--out", help="folder for the zip; must be outside the project (the project disk is tight)")
    ap.add_argument("--dry-run", action="store_true", help="choose and check the files, print the list, write nothing")
    ap.add_argument("--list", metavar="FILE", help="also write every selected file with its size to FILE")
    ap.add_argument("--include-untracked", action="store_true", help="also pack files that git does not track")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?", args.version):
        die("--version should look like 0.1.0")
    if not (ROOT / "SkyCity.uproject").exists():
        die("%s is not the Sky City project folder (no SkyCity.uproject). Set SKYCITY_ROOT." % ROOT)
    out_dir = None
    if not args.dry_run:
        if not args.out:
            die("--out DIR is required (or use --dry-run). Use a folder on the external drive, for example\n"
                '  --out "/Volumes/Sound Libraries/SkyCity Work/Release/ArtPack"')
        out_dir = Path(args.out).expanduser().resolve()
        root_real = ROOT.resolve()
        if out_dir == root_real or root_real in out_dir.parents:
            die("--out %s is inside the project. The project disk is nearly full: write the zip somewhere else." % out_dir)

    tracked = git_tracked()
    if tracked is None and not args.include_untracked:
        die("could not ask git which files are tracked (is git installed and is this a checkout?). "
            "Use --include-untracked to skip that safety check.")

    errors: list = []
    t0 = time.time()
    print("Sky City Art Pack v%s from %s" % (args.version, ROOT))
    sel = collect(tracked, args.include_untracked, errors)
    check_lfs(sel, errors)
    if errors:
        print("\n\n".join(errors), file=sys.stderr)
        return 1
    project = Project()
    cache = RefCache(project)
    print("Reading %d assets' references ..." % (len([r for r in sel.core if r.endswith(".uasset")]) + len(sel.artworks)),
          flush=True)
    prune_artwork_leftovers(sel, project, cache)
    problems = close_over_dependencies(sel, project, cache)
    files = sel.files()
    check_deny(files, errors)
    report_problems(problems, errors)
    if cache.unparsed:
        print("note: the header of %d asset(s) could not be read; their bytes were scanned for /Game/... text instead"
              % len(cache.unparsed))

    # ---- the report
    summarise({r: s for r, s in files.items() if r.startswith("Content")}, "\nUnreal assets (UE/Content):")
    summarise({r: s for r, s in files.items() if r.startswith("SourceArt")}, "\nSource files (Source):")
    ph_models, ph_tex, naip = third_party_entries(files)
    print("\nThird-party material packed because an included asset needs it: %d Poly Haven props, %d Poly Haven textures, "
          "%d NAIP aerials" % (len(ph_models), len(ph_tex), len(naip)))
    unused_pool = [r for r in sel.pool if r not in sel.needed]
    print("  (not needed, so not packed: %d files, %s)" % (len(unused_pool), human(sum(sel.pool[r] for r in unused_pool))))
    print("\nLeft out of the folders above:")
    found = {ART_RE.search(r).group("name").lower() for r in sel.artworks}
    print("  %-8d in-copyright artwork stand-ins: %d of the %d names in ARTWORKS found (see ARTWORKS)"
          % (len(sel.artworks), len(found), sum(len(n) for _, n in ARTWORKS)))
    for why, rels in sorted(sel.left_out.items(), key=lambda kv: -len(kv[1])):
        print("  %-8d %s" % (len(rels), why))
    if sel.untracked:
        print("  %-8d not tracked by git (skipped; --include-untracked to pack them)" % len(sel.untracked))
    if sel.ignored:
        print("  (ignored metadata: %s)" % ", ".join("%d %s" % (n, e) for e, n in sel.ignored.most_common()))
    total = sum(files.values())
    print("\nTotal: %d files, %s before compression (%d under UE/Content, %d under Source)" % (
        len(files), human(total), sum(1 for r in files if r.startswith("Content")),
        sum(1 for r in files if r.startswith("SourceArt"))))
    big = sorted(files.items(), key=lambda kv: -kv[1])[:8]
    print("Largest files: " + "; ".join("%s (%s)" % (os.path.basename(r), human(sz)) for r, sz in big))
    if args.list:
        with open(args.list, "w") as fh:
            for rel in sorted(files):
                fh.write("%12d  %s\n" % (files[rel], pack_path(rel)))
        print("File list written to " + args.list)

    if errors:
        print("\n" + "\n\n".join(errors), file=sys.stderr)
        print("\nNOT BUILT: the pack would break a rule.", file=sys.stderr)
        return 1
    print("\nChecks: never-list clear; every reference from every asset is in the pack or in Unreal Engine.")
    if args.dry_run:
        print("Dry run: nothing written (%.1f s)." % (time.time() - t0))
        return 0

    # ---- build
    out_dir.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(out_dir).free
    if free < total * 1.05:
        die("%s has %s free; the pack needs about %s." % (out_dir, human(free), human(total)))
    zip_path = out_dir / ("SkyCity-Art-Pack-v%s.zip" % args.version)
    if zip_path.exists():
        die("%s already exists. Move it away or pick another --version." % zip_path)
    left_summary = left_out_lines(sel)
    texts = [("README.md", make_readme(args.version, files, left_summary, sel.artworks)),
             ("LICENSE-ART.txt", make_license(args.version)),
             ("THIRD_PARTY.txt", make_third_party(files))]
    print("Writing %s ..." % zip_path, flush=True)
    write_zip(zip_path, files, texts, say=True)
    print("Checking the finished zip ...", flush=True)
    info = verify_zip(zip_path, files, project, errors)
    if errors:
        failed = zip_path.with_name(zip_path.name + ".FAILED")      # so nobody publishes it by mistake
        os.replace(zip_path, failed)
        print("\n" + "\n\n".join(errors), file=sys.stderr)
        print("\nThe zip was written but FAILED its check; it was renamed to %s" % failed, file=sys.stderr)
        return 1
    digest = sha256_of(zip_path)
    (out_dir / (zip_path.name + ".sha256")).write_text("%s  %s\n" % (digest, zip_path.name))
    print("\nDone: %s" % zip_path)
    print("  size    %s (%d bytes)" % (human(zip_path.stat().st_size), zip_path.stat().st_size))
    print("  entries %d (%d under UE/Content, %d under Source, plus README.md, LICENSE-ART.txt, THIRD_PARTY.txt)"
          % (info["entries"], info["ue"], info["source"]))
    print("  sha256  %s" % digest)
    print("  took    %.0f s" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
