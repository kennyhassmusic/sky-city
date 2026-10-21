#!/bin/bash
# Move Sky City's big, rebuildable data to an external drive and leave symlinks behind, so every path
# (scripts, the editor, UAT packaging) keeps working. Nothing is deleted: each folder is copied, verified,
# then the original is replaced by a link. Run with the editor closed:
#   Scripts/move_to_external.sh "/Volumes/<Drive>"
# Moves: the engine's shared DerivedDataCache and Zen data, the project's DerivedDataCache and Intermediate,
#        Build/ (packaged app) and Saved/StagedBuilds (packaging scratch), Saved/Autosaves and Saved/Overnight.
set -euo pipefail
DRIVE="${1:?usage: move_to_external.sh /Volumes/<Drive>}"
[ -d "$DRIVE" ] || { echo "no such drive: $DRIVE" >&2; exit 1; }
pgrep -f "MacOS/UnrealEditor " >/dev/null && { echo "close the Unreal editor first" >&2; exit 1; }
DEST="$DRIVE/SkyCity Work"
mkdir -p "$DEST"
PROJ="$(cd "$(dirname "$0")/.." && pwd)"
EPIC="${EPIC_COMMON:-$HOME/Library/Application Support/Epic/UnrealEngine/Common}"   # override if the engine data lives elsewhere

move() {   # move <source dir> <name on drive>
  local src="$1" name="$2" dst="$DEST/$2"
  if [ -L "$src" ]; then echo "already linked: $src"; return; fi
  mkdir -p "$src" "$dst"
  rsync -a "$src/" "$dst/"
  # verify the copy before replacing the original
  local a b
  a=$(cd "$src" && find . -type f | wc -l | tr -d ' ')
  b=$(cd "$dst" && find . -type f | wc -l | tr -d ' ')
  [ "$a" = "$b" ] || { echo "copy mismatch for $src ($a vs $b files), left as is" >&2; return 1; }
  mv "$src" "$src.moving" && ln -s "$dst" "$src" && rm -rf "$src.moving"
  echo "moved $src -> $dst"
}

move "$EPIC/DerivedDataCache" "EngineDerivedDataCache"
move "$EPIC/Zen/Data" "ZenData"
move "$PROJ/DerivedDataCache" "ProjectDerivedDataCache"
move "$PROJ/Intermediate" "Intermediate"
move "$PROJ/Build" "Build"
move "$PROJ/Saved/StagedBuilds" "StagedBuilds"
move "$PROJ/Saved/Autosaves" "Autosaves"
move "$PROJ/Saved/Overnight" "Overnight"
df -h "$HOME" "$DRIVE" | tail -2
