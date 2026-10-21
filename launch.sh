#!/bin/bash
# Open Sky City in Unreal Engine 5.8 with its MCP server running, so Claude can drive the editor.
# The server listens on http://127.0.0.1:8000/mcp (Claude's "unreal-mcp" connector).
set -euo pipefail
cd "$(dirname "$0")"
ENGINE="${UE58:-/Users/Shared/Epic Games/UE_5.8}"
EDITOR="$ENGINE/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
if [ ! -x "$EDITOR" ]; then
  echo "Unreal Engine 5.8 not found at $ENGINE (set UE58=/path/to/UE_5.8 if it's elsewhere)." >&2
  exit 1
fi
"$EDITOR" "$PWD/SkyCity.uproject" -ModelContextProtocolStartServer > /dev/null 2>&1 &
echo "Sky City is opening; the MCP server comes up once the editor has loaded."
