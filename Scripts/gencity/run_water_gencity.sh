#!/bin/bash
# Water B on a drive level, under the shared lock (owner $GEN_LOCK_OWNER, default lane9; waits on UNREAL.next):
#   Scripts/gencity/run_water_gencity.sh <building-types worktree> <seed> <tag> look <v1|bright>   retune the materials
#   Scripts/gencity/run_water_gencity.sh <building-types worktree> <seed> <tag> shots              aerial/bridge/bank shots
# Shots use Saved/Water/plan.json (lane 9's camera poses) and land in Saved/Screenshots/MacEditor (map in
# Saved/Water/shots_<tag>.json).
set -u
BT="$1"; SEED="$2"; TAG="$3"; WHAT="$4"; LOOK="${5:-bright}"
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
PYHERE="${GEN_LINK:-$HERE}"
ENGINE="${UE58:-/Users/Shared/Epic Games/UE_5.8}"
UE="$ENGINE/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
UE_CMD="$ENGINE/Engine/Binaries/Mac/UnrealEditor-Cmd"
THROTTLE_OFF='-ini:EditorSettings:[/Script/UnrealEd.EditorPerformanceSettings]:bThrottleCPUWhenNotForeground=False'
export TMPDIR="${GEN_TMPDIR:-$HOME/UnrealProjects/_laneU_tmp}"
LOCK="$HOME/UnrealProjects/_bt_mgmt/UNREAL.lock"; NEXT="$HOME/UnrealProjects/_bt_mgmt/UNREAL.next"
OWNER="${GEN_LOCK_OWNER:-lane9}"
LOGS="$HERE/Saved/GenCity/logs"; mkdir -p "$LOGS" "$TMPDIR"
HELD=0
next_ok() { [ ! -f "$NEXT" ] || grep -qx "$OWNER" "$NEXT"; }
until next_ok && mkdir "$LOCK" 2>/dev/null; do sleep 3; done
echo "$OWNER" > "$LOCK/owner"; HELD=1; echo "$(date +%H:%M:%S) lock taken"
free_lock() { if [ "$HELD" = 1 ] && [ "$(cat "$LOCK/owner" 2>/dev/null)" = "$OWNER" ]; then rm -f "$LOCK/owner"; rmdir "$LOCK"; echo "$(date +%H:%M:%S) lock freed"; fi; }
trap free_lock EXIT
if [ "$WHAT" = look ]; then
  GEN_BT="$BT" GEN_SEED="$SEED" GEN_WATER_LOOK="$LOOK" "$UE_CMD" "$HERE/SkyCity.uproject" /Engine/Maps/Entry -unattended -nosplash \
    -abslog="$LOGS/water_look_$TAG.log" -ExecutePythonScript="$HERE/Scripts/gencity/water_look_gencity_ue.py" > /dev/null 2>&1
  cat "$HERE/Saved/GenCity/water_look_status.json"
else
  "$UE" "$HERE/SkyCity.uproject" "/Game/Maps/GenCity_Seed$SEED" -nosplash -windowed -resx=1920 -resy=1080 "$THROTTLE_OFF" \
    -abslog="$LOGS/water_shots_$TAG.log" \
    -ExecCmds="py $PYHERE/Scripts/gencity/water_shots_gencity_ue.py tag=$TAG modes=B none=0 car=0 timing=0 seqs=none poses=aerial+bridge+riverbank settle=${SETTLE:-90}" > /dev/null 2>&1
  python3 -c "import json;d=json.load(open('$HERE/Saved/Water/shots_$TAG.json'));print(d.get('done'),d.get('error'),[(s['pose'],s['file']) for s in d['shots']])"
fi
