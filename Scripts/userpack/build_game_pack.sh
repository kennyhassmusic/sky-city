#!/bin/bash
# Rebuild the game pack's GLBs from the packs on the external drive (reproducible: same recipes, same Blender, same
# output). Nothing is committed: the GLBs land in $GAME_PACK_GLB, Unreal imports them into Content/UserPack (gitignored)
# when run_gencity.sh runs with GEN_PACK=game.
#   Scripts/userpack/build_game_pack.sh [asset,asset,...|all] [--qa]
# Needs: Blender 5.2 (BLENDER), the drive mounted (USERPACK_DRIVE, default /Volumes/Sound Libraries).
set -eu
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
export USERPACK_DRIVE="${USERPACK_DRIVE:-/Volumes/Sound Libraries}"
OUT="${GAME_PACK_GLB:-$USERPACK_DRIVE/SkyCity Work/AssetBuilds/game_pack}"
WHICH="${1:-all}"
[ -d "$USERPACK_DRIVE/3D Assets" ] || { echo "packs not found under $USERPACK_DRIVE/3D Assets (drive not mounted?)" >&2; exit 2; }
mkdir -p "$OUT"
"$BLENDER" -b -t 2 --python "$HERE/Scripts/userpack/convert_blender.py" -- "$HERE/UserPacks/game/recipes.json" "$WHICH" "$OUT" \
  2>&1 | grep -E "^USERPACK|Traceback|Error" || true
if [ "${2:-}" = "--qa" ]; then
  "$BLENDER" -b -t 2 --python "$HERE/Scripts/userpack/qa_render.py" -- "$OUT" "$OUT/qa" > /dev/null 2>&1
  echo "QA renders in $OUT/qa"
fi
# The manifest must still match what was built (budget, every variant's file present).
python3 -I - "$HERE/UserPacks/game/userpack.json" "$OUT" <<'PY'
import json, os, sys
m = json.load(open(sys.argv[1])); out = sys.argv[2]; bad = []
for slot, entry in m["slots"].items():
    for v in entry["variants"]:
        glb = os.path.join(out, v["asset"]); stats = glb[:-4] + ".json"
        if not os.path.isfile(glb):
            bad.append("%s: %s missing" % (slot, v["asset"])); continue
        st = json.load(open(stats))
        if st["tris"] > m["budget"]["tris_lod0"] or st["tex_max_px"] > m["budget"]["texture_px"]:
            bad.append("%s: %s over budget (%d tris, %d px)" % (slot, v["asset"], st["tris"], st["tex_max_px"]))
print("game pack check:", "OK" if not bad else "; ".join(bad))
sys.exit(1 if bad else 0)
PY
