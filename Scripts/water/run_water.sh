#!/bin/bash
# Lane 9 water A/B: one Unreal step under the shared lock (owner lane9, held at most ~24 min).
#   Scripts/water/run_water.sh build|shots <tag> [extra py args]
set -u
WHAT="$1"; TAG="${2:-v1}"; shift 2 || true
HERE="$HOME/UnrealProjects/SkyCity-water-link"          # space-free symlink of this worktree
ENGINE="${UE58:-/Users/Shared/Epic Games/UE_5.8}"
UE="$ENGINE/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
UE_CMD="$ENGINE/Engine/Binaries/Mac/UnrealEditor-Cmd"
THROTTLE_OFF='-ini:EditorSettings:[/Script/UnrealEd.EditorPerformanceSettings]:bThrottleCPUWhenNotForeground=False'
export TMPDIR="$HOME/UnrealProjects/_lane9_tmp"; mkdir -p "$TMPDIR"
LOCK="$HOME/UnrealProjects/_bt_mgmt/UNREAL.lock"
LOGS="$HERE/Saved/Water/logs"; mkdir -p "$LOGS"
HELD=0
take_lock() {
  until mkdir "$LOCK" 2>/dev/null; do [ $((SECONDS % 120)) -lt 3 ] && echo "$(date +%H:%M:%S) lock held by $(cat "$LOCK/owner" 2>/dev/null)"; sleep 3; done
  echo "lane9" > "$LOCK/owner"; HELD=1; echo "$(date +%H:%M:%S) lock taken"
}
free_lock() {
  if [ "$HELD" = 1 ] && [ "$(cat "$LOCK/owner" 2>/dev/null)" = lane9 ]; then
    rm -f "$LOCK/owner"; rmdir "$LOCK" 2>/dev/null; echo "$(date +%H:%M:%S) lock freed"; HELD=0
  fi
}
trap free_lock EXIT
take_lock
T0=$(date +%s)
if [ "$WHAT" = all ]; then
  "$UE_CMD" "$HERE/SkyCity.uproject" /Engine/Maps/Entry -unattended -nosplash -abslog="$LOGS/build_$TAG.log" \
    -ExecutePythonScript="$HERE/Scripts/water/build_water_ue.py" > /dev/null 2>&1
  echo "$(date +%H:%M:%S) build done in $(( $(date +%s) - T0 )) s"
  WHAT=shots
fi
if [ "$WHAT" = build ]; then
  "$UE_CMD" "$HERE/SkyCity.uproject" /Engine/Maps/Entry -unattended -nosplash -abslog="$LOGS/build_$TAG.log" \
    -ExecutePythonScript="$HERE/Scripts/water/build_water_ue.py" > /dev/null 2>&1 &
else
  LEVEL="${LEVEL:-/Game/Maps/GenCity_Seed7_Water}"
  "$UE" "$HERE/SkyCity.uproject" "$LEVEL" -nosplash -windowed -resx=1920 -resy=1080 "$THROTTLE_OFF" -abslog="$LOGS/shots_$TAG.log" \
    -ExecCmds="py $HERE/Scripts/water/shots_water_ue.py tag=$TAG $*" > /dev/null 2>&1 &
fi
PID=$!
while kill -0 $PID 2>/dev/null; do
  sleep 5
  if [ $(( $(date +%s) - T0 )) -gt 1380 ]; then echo "$(date +%H:%M:%S) 23 min: stopping the editor"; kill $PID; sleep 10; kill -9 $PID 2>/dev/null; fi
done
echo "$(date +%H:%M:%S) $WHAT done in $(( $(date +%s) - T0 )) s"
