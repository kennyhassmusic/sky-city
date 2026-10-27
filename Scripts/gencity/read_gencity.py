"""Summarise a drive round (plain Python): the drive test, frame time, shots, and the clean load from the editor log.
  python3 -I Scripts/gencity/read_gencity.py <tag>
Clean load: the errors and warnings the editor logged between opening the level and the end of the settle window
(the "GENCITY settle done" line), minus engine noise seen on every launch (KNOWN). Exit 1 unless the drive passed.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KNOWN = ("GameFeatureData", "Error querying Sample Rate", "SemanticSearch", "idevice_id", "libimobiledevice",
         "LogMetalShaderCompiler", "LogDerivedDataCache", "ModelContextProtocol", "LogPython: Warning: GENCITY",
         "LogPixelStreaming2RTC: Error: Cannot set target window - GEngine is not valid",
         "FDataflowToolNodeSnapshot")


def clean_load(log):
    if not os.path.isfile(log):
        return {"log": None}
    lines = open(log, errors="replace").read().splitlines()
    end = next((i for i, l in enumerate(lines) if "GENCITY settle done" in l), len(lines))
    errs, warns, noise = [], [], 0
    for line in lines[:end]:
        m = re.search(r"\b(Error|Warning):", line)
        if not m:
            continue
        if any(k in line for k in KNOWN):
            noise += 1
            continue
        (errs if m.group(1) == "Error" else warns).append(line[:220])
    mapcheck = [l for l in lines[:end] if "Map check complete" in l]
    return {"errors": len(errs), "warnings": len(warns), "noise": noise, "first_errors": errs[:12],
            "first_warnings": warns[:12], "map_check": mapcheck[-1:] if mapcheck else None}


def main(tag):
    out = json.load(open(os.path.join(ROOT, "Saved", "GenCity", "drive_%s.json" % tag)))
    out["clean_load"] = clean_load(os.path.join(ROOT, "Saved", "GenCity", "logs", "drive_%s.log" % tag))
    d = out.get("drive") or {}
    print("pawn", out.get("pawn_class"), "game mode", out.get("game_mode"), "spawn", out.get("spawn_at_ue"))
    print("drive: pass=%s dist=%s m in %s s, max %s mph, below_ground=%s no_ground=%s outside=%s min_clear=%s cm"
          % (d.get("pass"), d.get("dist_m"), d.get("secs_driven"), d.get("max_mph"), d.get("below_ground"),
             d.get("no_ground"), d.get("outside"), d.get("min_clear_cm")))
    print("modes", d.get("modes"), "surfaces", dict(sorted((d.get("surfaces") or {}).items(), key=lambda kv: -kv[1])[:6]))
    print("frame ms", out.get("frame_ms"))
    if out.get("ramp"):
        r = out["ramp"]
        print("garage ramp: pass=%s climb=%s cm (z %s -> %s) below_ground=%s no_ground=%s"
              % (r.get("pass"), r.get("climb_cm"), r.get("z0"), r.get("max_z"), r.get("below_ground"), r.get("no_ground")))
    for s in out.get("shots") or []:
        print("shot", s["name"], s.get("mode"), s.get("file"))
    print("clean load", {k: v for k, v in out["clean_load"].items() if not k.startswith("first")})
    for line in out["clean_load"].get("first_errors") or []:
        print("  E", line)
    for line in out["clean_load"].get("first_warnings") or []:
        print("  W", line)
    if out.get("error"):
        print("ERROR", out["error"])
    with open(os.path.join(ROOT, "Saved", "GenCity", "drive_%s.json" % tag), "w") as handle:
        json.dump(out, handle, indent=1, sort_keys=True)
    return 0 if d.get("pass") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
