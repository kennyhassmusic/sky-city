#!/usr/bin/env python3
"""Switch Config/DefaultGame.ini between the two vehicle flavours of Sky City.

  personal   Kenny's own build: the real third-party vehicle models (Semi, Model 3, ...) everywhere.
  public     the itch.io build: the Semi (editorial licence) and the Model 3 (licence in doubt) are not allowed to ship, so the
             blocky stand-ins from /Game/Vehicles/Placeholder (Scripts/vehicles/PLACEHOLDERS.md) take their place:
               [SkyFleet]
               +PlaceholderCars=Semi                    <- read by SkyFleet::UsePlaceholder in Source/SkyCity/SkysterFleet.h
               +PlaceholderCars=Model3
               [/Script/UnrealEd.ProjectPackagingSettings]
               +DirectoriesToAlwaysCook=(Path="/Game/Vehicles/Placeholder")      <- cooked although only C++ refers to them
               +DirectoriesToNeverCook=(Path="/Game/Vehicles/Tesla/Semi")        <- the real meshes stay out of the package
               +DirectoriesToNeverCook=(Path="/Game/Vehicles/Tesla/Model3")
             (the open-source repo needs no flavour: the real models aren't in it, and SkyFleet::UsePlaceholder falls back to the
             placeholders for any car whose package is missing)

Usage:  python3 Scripts/build/set_vehicle_flavor.py public|personal|status [--cars Semi,Model3] [--dry-run] [--ini PATH]
Only those lines are touched (everything else in the ini stays as it is, byte for byte); running it twice changes nothing the
second time. Before the first change of a run the ini is copied to Saved/VehicleFlavor/DefaultGame.ini.<date-time>.bak, and a
unified diff of what changed is printed. `status` prints which flavour the file is in.
The line-up in the McGregor maps references meshes directly, not through the ini: after a switch re-place it in both maps
(lineup_ue.py `place save`, which follows the [SkyFleet] list by default; `placeholders=Semi,Model3` / `placeholders=none` override
it; see Scripts/vehicles/PLACEHOLDERS.md), and the public cook must not reach /Game/Vehicles/Tesla/Semi or Model3 (the cook log
names any asset that still points at them).
The game reads the ini at start-up (and the cook reads the packaging lines), so re-cook / re-stage after switching."""
import argparse, difflib, os, shutil, sys, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PKG = "[/Script/UnrealEd.ProjectPackagingSettings]"
FLEET = "[SkyFleet]"
NEVER = ["/Game/Vehicles/Tesla/Semi", "/Game/Vehicles/Tesla/Model3"]
ALWAYS = ["/Game/Vehicles/Placeholder"]
NOTE = "; public build: these cars use the placeholder meshes (Scripts/build/set_vehicle_flavor.py personal removes this section)"


def managed(cars):
    """(section, line) pairs this script owns."""
    m = [(FLEET, f"+PlaceholderCars={c}") for c in cars]
    m += [(PKG, f'+DirectoriesToAlwaysCook=(Path="{p}")') for p in ALWAYS]
    m += [(PKG, f'+DirectoriesToNeverCook=(Path="{p}")') for p in NEVER]
    return m


def parse(text):
    """Lines with the section each one is in."""
    sec, rows = "", []
    for ln in text.split("\n"):
        s = ln.strip()
        if s.startswith("[") and s.endswith("]"):
            sec = s
        rows.append((sec, ln))
    return rows


def remove(text, cars):
    own = set(managed(cars))
    rows = [(s, ln) for s, ln in parse(text) if (s, ln.strip()) not in own and not (s == FLEET and ln.strip() == NOTE)]
    # an empty [SkyFleet] section (header and blank lines only) goes too
    out, i = [], 0
    while i < len(rows):
        s, ln = rows[i]
        if ln.strip() == FLEET:
            j = i + 1
            while j < len(rows) and rows[j][0] == FLEET and not rows[j][1].strip():
                j += 1
            if j >= len(rows) or rows[j][0] != FLEET:
                while out and not out[-1].strip():
                    out.pop()                       # the blank line that separated it
                i = j
                continue
        out.append(ln)
        i += 1
    res = "\n".join(out)
    return res + "\n" if text.endswith("\n") and not res.endswith("\n") else res


def add(text, cars):
    text = remove(text, cars)
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    # packaging lines: after the last DirectoriesTo*Cook line of that section, else at its end
    pk = [(PKG, f'+DirectoriesToAlwaysCook=(Path="{p}")') for p in ALWAYS] + [(PKG, f'+DirectoriesToNeverCook=(Path="{p}")') for p in NEVER]
    if PKG not in [ln.strip() for ln in lines]:
        lines += ["", PKG]
    start = [ln.strip() for ln in lines].index(PKG)
    end = start + 1
    while end < len(lines) and not lines[end].strip().startswith("["):
        end += 1
    last = max([k for k in range(start + 1, end) if lines[k].strip().startswith("+DirectoriesToAlwaysCook=")] or [end - 1 if lines[end - 1].strip() else start])
    lines[last + 1:last + 1] = [ln for _, ln in pk]
    lines += ["", FLEET, NOTE] + [ln for s, ln in managed(cars) if s == FLEET]
    return "\n".join(lines) + "\n"


def flavour(text, cars):
    own = set(managed(cars))
    have = {(s, ln.strip()) for s, ln in parse(text)}
    n = len(own & have)
    return "public" if n == len(own) else ("personal" if n == 0 else f"mixed ({n} of {len(own)} public lines present)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=["public", "personal", "status"])
    ap.add_argument("--cars", default="Semi,Model3", help="cars that get placeholders in the public flavour (default Semi,Model3)")
    ap.add_argument("--dry-run", action="store_true", help="print the diff, change nothing")
    ap.add_argument("--ini", default=os.path.join(ROOT, "Config", "DefaultGame.ini"))
    a = ap.parse_args()
    cars = [c for c in a.cars.split(",") if c]
    with open(a.ini, newline="") as f:
        old = f.read()
    print(f"{a.ini}: {flavour(old, cars)}")
    if a.mode == "status":
        return
    new = add(old, cars) if a.mode == "public" else remove(old, cars)
    if new == old:
        print(f"already {a.mode}: nothing to change")
        return
    diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), "DefaultGame.ini (before)", "DefaultGame.ini (after)"))
    print(diff, end="" if diff.endswith("\n") else "\n")
    if a.dry_run:
        print("dry run: nothing written")
        return
    default = os.path.abspath(a.ini) == os.path.join(ROOT, "Config", "DefaultGame.ini")
    bk = os.path.join(ROOT, "Saved", "VehicleFlavor") if default else os.path.dirname(os.path.abspath(a.ini))   # (Saved/ is never in the repo)
    os.makedirs(bk, exist_ok=True)
    bak = os.path.join(bk, os.path.basename(a.ini) + "." + time.strftime("%Y%m%d-%H%M%S") + ".bak")
    shutil.copy2(a.ini, bak)
    with open(a.ini, "w", newline="") as f:
        f.write(new)
    print(f"backup: {bak}\nnow {flavour(new, cars)}: rebuild / re-stage the game for it to take effect")


if __name__ == "__main__":
    sys.exit(main())
