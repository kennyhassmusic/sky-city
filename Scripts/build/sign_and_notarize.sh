#!/bin/bash
# Sign a packaged Sky City app with Kenny's Developer ID (hardened runtime), notarize it with Apple and staple the ticket.
#   Scripts/build/sign_and_notarize.sh "<path to SkyCity.app>"
# Needs: the "Developer ID Application: Kenny Hass Music LLC (F89LBX9V56)" identity in the login keychain, and the
# notarytool keychain profile "skycity-notary" (xcrun notarytool store-credentials, done once by Kenny).
set -euo pipefail
APP="$1"
ID="Developer ID Application: Kenny Hass Music LLC (F89LBX9V56)"
ENT="$(cd "$(dirname "$0")" && pwd)/SkyCity.entitlements"   # the sandbox, plus the Course Builder's local MCP server
[ -d "$APP" ] || { echo "no app at $APP"; exit 1; }
xattr -cr "$APP"
# inner code first: dylibs, bundles, then any other executables (deepest paths first)
find "$APP/Contents" -type f \( -name "*.dylib" -o -name "*.so" -o -perm -u+x \) ! -path "*/Contents/MacOS/*" -print0 |
  xargs -0 -I{} codesign --force --timestamp --options runtime --sign "$ID" "{}"
find "$APP/Contents" -depth -type d \( -name "*.framework" -o -name "*.bundle" -o -name "*.app" \) ! -path "$APP" -print0 |
  xargs -0 -I{} codesign --force --timestamp --options runtime --sign "$ID" "{}" 2>/dev/null || true
codesign --force --timestamp --options runtime --entitlements "$ENT" --sign "$ID" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
ZIP="$(dirname "$APP")/$(basename "$APP" .app)-notarize.zip"
ditto -c -k --keepParent "$APP" "$ZIP"
xcrun notarytool submit "$ZIP" --keychain-profile "skycity-notary" --wait
xcrun stapler staple "$APP"
spctl -a -vv "$APP"
rm -f "$ZIP"
echo "signed, notarized and stapled: $APP"
