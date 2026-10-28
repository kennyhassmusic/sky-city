#!/bin/bash
# Visual check after an Unreal import (Lane V): capture the fixed cameras of visual_cams.json in the drive level,
# then compare with the approved goldens and run the level rules. One exit code; report.html in the run folder.
#
#   Scripts/gencity/run_visual_check.sh <seed> <tag> <expect> [<expect> ...]
#     <expect>: what this import meant to change: a camera glob ('beach_*'), tag:<tag> ('tag:shore'),
#               asset:<name> ('asset:M_Shore_Sand'), or 'none'. Required: a no-op import must not pass silently.
#
# Env:
#   VISUAL_PROJECT  the SkyCity project with the imported level (default the drive copy, SkyCity-drive)
#   GEN_BT          the building-types worktree of the import (its Saved/CityGen has the road/walk side files)
#   GEN_PACK        game when the import had the game pack on (turns the pack rule on)
#   VISUAL_LOCK     'held' when the caller already holds UNREAL.lock (the build lane, mid-round); otherwise this
#                   script takes it as $GEN_LOCK_OWNER (default laneV) and frees only its own lock
#   VISUAL_RUNS     where run folders go (default AssetBuilds/visual_runs on the external drive)
#   VISUAL_GOLDENS  goldens (default AssetBuilds/visual_goldens)
#   VISUAL_CAMS     camera glob to capture a subset; VISUAL_REPEAT=1 shoots each camera twice (noise floor; use on
#                   the run you will approve)
#   VISUAL_SKIP_CAPTURE=<run dir>  re-check an existing run without Unreal
# Exit: 0 PASS, 1 FAIL, 2 error, 3 NEEDS_APPROVAL (first run: no goldens yet), 4 refused (disk / DISK_LOW / lock).
set -u
SEED="${1:?seed}"; TAG="${2:?tag}"; shift 2
[ $# -ge 1 ] || { echo "say what this import meant to change: <expect>... or none" >&2; exit 2; }
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="/Volumes/Sound Libraries/SkyCity Work"
PROJECT="${VISUAL_PROJECT:-$WORK/SkyCity-drive}"
RUNS="${VISUAL_RUNS:-$WORK/AssetBuilds/visual_runs}"
GOLDENS="${VISUAL_GOLDENS:-$WORK/AssetBuilds/visual_goldens}"
MGMT="$HOME/UnrealProjects/_bt_mgmt"
ENGINE="${UE58:-/Users/Shared/Epic Games/UE_5.8}"
UE="$ENGINE/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
THROTTLE_OFF='-ini:EditorSettings:[/Script/UnrealEd.EditorPerformanceSettings]:bThrottleCPUWhenNotForeground=False'
# -ExecCmds splits on spaces: the capture script is run through a space-free symlink to this worktree
LINK="${VISUAL_LINK:-$HOME/UnrealProjects/SkyCity-visual-link}"
EXPECT=(); for e in "$@"; do EXPECT+=(--expect "$e"); done
FLAGS=""; [ "${GEN_PACK:-}" = game ] && FLAGS="pack"
SIDE=(); [ -n "${GEN_BT:-}" ] && SIDE=(--side "$GEN_BT/Saved/CityGen")

if [ -n "${VISUAL_SKIP_CAPTURE:-}" ]; then
  RUN="$VISUAL_SKIP_CAPTURE"
else
  [ -f "$MGMT/DISK_LOW" ] && { echo "DISK_LOW is set: not starting Unreal" >&2; exit 4; }
  FREE=$(df -g /System/Volumes/Data | awk 'NR==2{print $4}')
  [ "$FREE" -lt 15 ] && { echo "internal disk ${FREE} GB free (< 15): not starting Unreal" >&2; exit 4; }
  [ -e "$LINK/Scripts/gencity/visual_capture_ue.py" ] || ln -s "$HERE" "$LINK" 2>/dev/null
  case "$LINK" in *" "*) echo "VISUAL_LINK must have no spaces" >&2; exit 2;; esac
  RUN="$RUNS/${TAG}_seed${SEED}_$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$RUN/logs"
  export TMPDIR="${GEN_TMPDIR:-$HOME/UnrealProjects/_laneU_tmp}"; mkdir -p "$TMPDIR"
  LOCK="$MGMT/UNREAL.lock"; OWNER="${GEN_LOCK_OWNER:-laneV}"; HELD=0
  free_lock() {
    if [ "$HELD" = 1 ] && [ "$(cat "$LOCK/owner" 2>/dev/null)" = "$OWNER" ]; then rm -f "$LOCK/owner"; rmdir "$LOCK" 2>/dev/null; fi
  }
  trap free_lock EXIT
  if [ "${VISUAL_LOCK:-}" != held ]; then
    NEXT="$MGMT/UNREAL.next"
    until { [ ! -f "$NEXT" ] || grep -qx "$OWNER" "$NEXT"; } && mkdir "$LOCK" 2>/dev/null; do
      [ $((SECONDS % 60)) -lt 2 ] && echo "$(date +%H:%M:%S) lock held by $(cat "$LOCK/owner" 2>/dev/null)"; sleep 2
    done
    echo "$OWNER" > "$LOCK/owner"; HELD=1
  fi
  VISUAL_OUT="$RUN" VISUAL_SPEC="$HERE/Scripts/gencity/visual_cams.json" VISUAL_SEED="$SEED" VISUAL_TAG="$TAG" \
    "$UE" "$PROJECT/SkyCity.uproject" "/Game/Maps/GenCity_Seed$SEED" -nosplash "$THROTTLE_OFF" \
    -abslog="$RUN/logs/capture.log" -ExecCmds="py $LINK/Scripts/gencity/visual_capture_ue.py" > /dev/null 2>&1
  free_lock; HELD=0
  python3 -I -c "import json,sys; c=json.load(open(sys.argv[1])); print('capture:', 'done' if c.get('done') else 'NOT done', len(c.get('cams',[])), 'cams', c.get('error') or '')" "$RUN/capture.json" || exit 2
  grep -q '"error"' "$RUN/capture.json" && { grep -q 'DISK_LOW\|GB free' "$RUN/capture.json" && exit 4; }
fi
python3 -I "$HERE/Scripts/gencity/visual_check.py" check --run "$RUN" --goldens "$GOLDENS" ${SIDE[@]+"${SIDE[@]}"} \
  --flags "$FLAGS" "${EXPECT[@]}"
RC=$?
echo "report: $RUN/report.html (exit $RC)"
exit $RC
