"""Rename step for the elevated expressway past the Capitol: "Ida B. Wells Expressway" -> "Interstate 35".

Why: the road was invented when Kenny's 19 Oct sketch was applied to the plan (Scripts/mashup/apply_sketch.py) and got the
name of the Chicago street it grew out of, but it runs west past the Texas State Capitol on the Austin side, and on
20 Oct Kenny confirmed it should be Austin's I-35 upper deck ("make it accurate to real life"). The name lives in two
data files that everything downstream reads, so it is changed there, by this documented step, never by hand:
  Saved/Mashup/plan_v3.json        (build_city.py, make_minimaps.py, the expressway layout, roadnet via street data)
  Saved/Streets/street_data.json   (roadnet.py reads its roads; traffic.json link names come from roadnet)
Each renamed road also gets "ref" (the shield text, e.g. "I-35") so signs and labels can use it.
The sketch's at-grade "Ida B. Wells ramp" (from the 15th St cluster to 15th St) follows the road it serves.

Idempotent (a second run changes nothing) and atomic per file (written to a temp file, then renamed). The first run that
changes a file keeps a copy of the original in Saved/Expressway/backup/. Formatting matches the files (compact JSON).
**Re-run this after anything regenerates plan_v3.json or street_data.json** (apply_sketch.py, integrate_v2.py,
build_street_data.py), then re-run roadnet.py (seam-junctions) so traffic.json and the mini map pick it up.

Run: python3 -I Scripts/roads/expressway_names.py [--check]      (--check: report only, write nothing)
(20 Oct 2026, agent highway-capitol)
"""
import json, os, pathlib, shutil, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
FILES = [ROOT / "Saved/Mashup/plan_v3.json", ROOT / "Saved/Streets/street_data.json"]
RENAME = {  # old name -> (new name, ref)
    "Ida B. Wells Expressway": ("Interstate 35", "I-35"),
    "Ida B. Wells ramp": ("Interstate 35 Frontage Road", "I-35"),
}
NEW = {v[0]: v[1] for v in RENAME.values()}
CHECK = "--check" in sys.argv


def main():
    report = {}
    for f in FILES:
        text = f.read_text()
        data = json.loads(text)
        n = 0
        for r in data.get("roads", []):
            nm = r.get("name")
            if nm in RENAME:
                r["name"], r["ref"] = RENAME[nm]
                n += 1
            elif nm in NEW and r.get("ref") != NEW[nm]:
                r["ref"] = NEW[nm]
                n += 1
        report[str(f.relative_to(ROOT))] = {"changed": n, "now": sorted({r["name"] for r in data.get("roads", []) if r.get("name") in NEW})}
        if n and not CHECK:
            bk = ROOT / "Saved/Expressway/backup"
            bk.mkdir(parents=True, exist_ok=True)
            dst = bk / (f.stem + "_before_rename" + f.suffix)
            if not dst.exists():
                shutil.copy2(f, dst)
            tmp = f.with_suffix(f.suffix + ".tmp")
            tmp.write_text(json.dumps(data, separators=(",", ":")))
            os.replace(tmp, f)
    report["when"] = time.strftime("%Y-%m-%d %H:%M")
    report["check_only"] = CHECK
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
