#!/bin/bash
# Lane 8: wind on a generated-city drive level (after run_gencity.sh's import), then the wind proof (PIE).
#   Scripts/gencity/run_wind.sh <building-types worktree, space-free path> <seed> <tag> [hook|shots|all]
# GEN_PROJ: the drive project to run in (default: this folder), GEN_LINK: a space-free path to this folder's
# scripts. Takes UNREAL.lock as lane8 and frees it only if lane8 owns it.
set -u
BT="$1"; SEED="$2"; TAG="$3"; WHAT="${4:-all}"
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
PROJ="${GEN_PROJ:-$HERE}"
PYHERE="${GEN_LINK:-$HERE}"
REGION="seed${SEED}_city"
ENGINE="${UE58:-/Users/Shared/Epic Games/UE_5.8}"
UE="$ENGINE/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
UE_CMD="$ENGINE/Engine/Binaries/Mac/UnrealEditor-Cmd"
THROTTLE_OFF='-ini:EditorSettings:[/Script/UnrealEd.EditorPerformanceSettings]:bThrottleCPUWhenNotForeground=False'
export TMPDIR="${GEN_TMPDIR:-$HOME/UnrealProjects/_laneU_tmp}"
LOCK="$HOME/UnrealProjects/_bt_mgmt/UNREAL.lock"
LOGS="$PROJ/Saved/GenCity/logs"; mkdir -p "$LOGS" "$TMPDIR"
case "$PYHERE$BT" in *" "*) echo "GEN_LINK and the bt path must have no spaces" >&2; exit 2;; esac
HELD=0
take_lock() {
  NEXT="$HOME/UnrealProjects/_bt_mgmt/UNREAL.next"   # another lane queued first: wait for it to clear
  until { [ ! -f "$NEXT" ] || grep -q lane8 "$NEXT"; } && mkdir "$LOCK" 2>/dev/null; do [ $((SECONDS % 60)) -lt 2 ] && echo "$(date +%H:%M:%S) lock held by $(cat "$LOCK/owner" 2>/dev/null)"; sleep 2; done
  echo "lane8" > "$LOCK/owner"; HELD=1; echo "$(date +%H:%M:%S) lock taken"
}
free_lock() {
  if [ "$HELD" = 1 ] && [ "$(cat "$LOCK/owner" 2>/dev/null)" = lane8 ]; then
    rm -f "$LOCK/owner"; rmdir "$LOCK" 2>/dev/null; echo "$(date +%H:%M:%S) lock freed"
  fi
}
trap free_lock EXIT
take_lock
if [ "$WHAT" = hook ] || [ "$WHAT" = all ]; then
  grep -q '"ok"' "$PROJ/Saved/GenCity/import_status_$REGION.json" || { echo "the level's last import failed; run the import first"; exit 3; }
fi
if [ "$WHAT" = hook ] || [ "$WHAT" = all ]; then
  rm -f "$PROJ/Saved/GenCity/wind_status_$REGION.json"
  GEN_BT="$BT" GEN_SEED="$SEED" "$UE_CMD" "$PROJ/SkyCity.uproject" "/Game/Maps/GenCity_Seed$SEED" -unattended -nosplash \
    -abslog="$LOGS/wind_hook_$TAG.log" -ExecutePythonScript="$PYHERE/Scripts/gencity/wind_gencity_ue.py" > /dev/null 2>&1
  cat "$PROJ/Saved/GenCity/wind_status_$REGION.json" || exit 1
  grep -q '"ok"' "$PROJ/Saved/GenCity/wind_status_$REGION.json" || exit 1
fi
if [ "$WHAT" = shots ] || [ "$WHAT" = all ]; then
  rm -f "$PROJ/Saved/GenCity/wind_$TAG.json"
  "$UE" "$PROJ/SkyCity.uproject" "/Game/Maps/GenCity_Seed$SEED" -nosplash "$THROTTLE_OFF" -abslog="$LOGS/wind_shots_$TAG.log" \
    -ExecCmds="py $PYHERE/Scripts/gencity/wind_shots_gencity_ue.py region=$REGION bt=$BT tag=$TAG settle=${SETTLE:-180}" > /dev/null 2>&1
  python3 -I "$PYHERE/Scripts/gencity/wind_shots_gencity_ue.py" --read "$LOGS/wind_shots_$TAG.log"
  python3 -c "import json;d=json.load(open('$PROJ/Saved/GenCity/wind_$TAG.json'));print({k:d.get(k) for k in ('done','error','perf','cams_found')}, len(d.get('clips',[])),'frames')"
fi
