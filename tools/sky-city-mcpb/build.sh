#!/bin/bash
# Pack the Claude Desktop extension (MCP Bundle) the game offers from its LLM link menu ("Install in Claude Desktop").
#   tools/sky-city-mcpb/build.sh        -> Content/SkyCity/Connect/SkyCity.mcpb (staged into the game as a loose file)
# Uses Anthropic's MCPB CLI (pinned). Bump "version" in manifest.json with each game release.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="$ROOT/Content/SkyCity/Connect/SkyCity.mcpb"
mkdir -p "$(dirname "$OUT")"
node --check "$HERE/server/index.js"
npx -y @anthropic-ai/mcpb@2.1.2 validate "$HERE/manifest.json"
rm -f "$OUT"
npx -y @anthropic-ai/mcpb@2.1.2 pack "$HERE" "$OUT"
echo "packed: $OUT"
