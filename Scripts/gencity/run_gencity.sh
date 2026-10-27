#!/bin/bash
# One round of the generated-city drive level: import (headless), plan, drive test + shots (PIE), clean-load read.
#   Scripts/gencity/run_gencity.sh <building-types worktree> <seed> <tag> [import|landcover|drive|all]
# Takes the shared Unreal lock (~/UnrealProjects/_bt_mgmt/UNREAL.lock, owner lane7) for the editor runs and frees it
# after. The generator run (pipeline.py --seed N) happens before this, in the building-types worktree.
set -u
BT="$1"; SEED="$2"; TAG="$3"; WHAT="${4:-all}"
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
REGION="seed${SEED}_city"
ENGINE="${UE58:-/Users/Shared/Epic Games/UE_5.8}"
UE="$ENGINE/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
UE_CMD="$ENGINE/Engine/Binaries/Mac/UnrealEditor-Cmd"
THROTTLE_OFF='-ini:EditorSettings:[/Script/UnrealEd.EditorPerformanceSettings]:bThrottleCPUWhenNotForeground=False'
export TMPDIR="${GEN_TMPDIR:-$HOME/UnrealProjects/_laneU_tmp}"     # no spaces: the Metal shader compiler breaks on them
LOCK="$HOME/UnrealProjects/_bt_mgmt/UNREAL.lock"
LOGS="$HERE/Saved/GenCity/logs"; mkdir -p "$LOGS" "$TMPDIR"
# -ExecCmds="py <path> ..." splits on spaces: give the script a path without them (a symlink to this worktree).
PYHERE="${GEN_LINK:-$HERE}"
case "$PYHERE" in *" "*) echo "set GEN_LINK to a space-free symlink of $HERE" >&2; exit 2;; esac

take_lock() {
  until mkdir "$LOCK" 2>/dev/null; do [ $((SECONDS % 60)) -lt 2 ] && echo "$(date +%H:%M:%S) lock held by $(cat "$LOCK/owner" 2>/dev/null)"; sleep 2; done
  echo "lane7" > "$LOCK/owner"; HELD=1; echo "$(date +%H:%M:%S) lock taken"
}
HELD=0
free_lock() {   # only ever the lock this run took (never another lane's)
  if [ "$HELD" = 1 ] && [ "$(cat "$LOCK/owner" 2>/dev/null)" = lane7 ]; then
    rm -f "$LOCK/owner"; rmdir "$LOCK" 2>/dev/null; echo "$(date +%H:%M:%S) lock freed"
  fi
}
trap free_lock EXIT

sync_pack() {
  # The starter pack's Unreal content (building-types assets/starter-pack, /Game/LandCover), copied in, not committed.
  PACK="${GEN_PACK:-$BT/Content/LandCover}"
  if [ -f "$PACK/Materials/MPC_LC_Season.uasset" ] && head -c 4 "$PACK/Materials/MPC_LC_Season.uasset" | xxd | grep -q c183; then
    rsync -a "$PACK/" "$HERE/Content/LandCover/" && chmod -R u+w "$HERE/Content/LandCover"
  else
    echo "no Unreal starter pack at $PACK (LFS not pulled?); keeping $HERE/Content/LandCover as it is"
  fi
}
take_lock
if [ "$WHAT" = import ] || [ "$WHAT" = all ]; then
  sync_pack
  rm -f "$HERE/Saved/GenCity/import_status_$REGION.json"
  GEN_BT="$BT" GEN_SEED="$SEED" "$UE_CMD" "$HERE/SkyCity.uproject" /Engine/Maps/Entry -unattended -nosplash \
    -abslog="$LOGS/import_$TAG.log" -ExecutePythonScript="$HERE/Scripts/gencity/import_gencity_ue.py" > /dev/null 2>&1
  cat "$HERE/Saved/GenCity/import_status_$REGION.json" || exit 1
  grep -q '"ok"' "$HERE/Saved/GenCity/import_status_$REGION.json" || exit 1
  python3 -I "$HERE/Scripts/gencity/plan_gencity.py" --bt "$BT" --seed "$SEED" || exit 1
  if [ "${GEN_WIND:-0}" = 1 ]; then
    # Lane 8's wind (gen/wind + building-types fx/wind): flags, wind source, foliage/awning sway on the level.
    GEN_BT="$BT" GEN_SEED="$SEED" "$UE_CMD" "$HERE/SkyCity.uproject" "/Game/Maps/GenCity_Seed$SEED" -unattended -nosplash \
      -abslog="$LOGS/wind_$TAG.log" -ExecutePythonScript="$HERE/Scripts/gencity/wind_gencity_ue.py" > /dev/null 2>&1
  fi
fi
# v3: lane 4's land-cover ground, crops and hero scatter come in with the import (building-types
# landcover/unreal-ground, import_city_ue.merge_landcover). This older step (hero HISMs + flat field slabs) runs only
# when asked for by name.
if [ "$WHAT" = landcover ]; then
  sync_pack
  rm -f "$HERE/Saved/GenCity/landcover_status_$REGION.json"
  GEN_BT="$BT" GEN_SEED="$SEED" "$UE_CMD" "$HERE/SkyCity.uproject" "/Game/Maps/GenCity_Seed$SEED" -unattended -nosplash \
    -abslog="$LOGS/landcover_$TAG.log" -ExecutePythonScript="$HERE/Scripts/gencity/landcover_gencity_ue.py" > /dev/null 2>&1
  cat "$HERE/Saved/GenCity/landcover_status_$REGION.json"
fi
if [ "$WHAT" = drive ] || [ "$WHAT" = all ]; then
  rm -f "$HERE/Saved/GenCity/drive_$TAG.json"
  "$UE" "$HERE/SkyCity.uproject" "/Game/Maps/GenCity_Seed$SEED" -nosplash "$THROTTLE_OFF" -abslog="$LOGS/drive_$TAG.log" \
    -ExecCmds="py $PYHERE/Scripts/gencity/drive_gencity_ue.py region=$REGION tag=$TAG" > /dev/null 2>&1
  python3 -I "$HERE/Scripts/gencity/read_gencity.py" "$TAG"
fi
