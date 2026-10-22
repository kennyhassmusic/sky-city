#!/bin/bash
# Makes a new upload password for Sky City's LFS server and stores it in the three places that use it:
#   1. the Worker (a Cloudflare secret, UPLOAD_TOKEN)
#   2. the lfs-mirror GitHub Action (a repository secret, LFS_UPLOAD_TOKEN)
#   3. this Mac's keychain, through git's credential helper (for mirror.py)
# The password is never printed or written to a file, and the old one stops working at once.
# Needs: wrangler logged in to the Cloudflare account, gh logged in as a repo admin, git with osxkeychain.
set -euo pipefail

HOST="sky-city-lfs.goodmorrow.workers.dev"
REPO="kennyhassmusic/sky-city"
WRANGLER=(npx --yes wrangler@4.151.3)

if ! git config --get-all credential.helper | grep -q osxkeychain; then
  echo "git's credential helper isn't the macOS keychain; refusing to store the password elsewhere." >&2
  exit 1
fi

token=$(openssl rand -hex 32)

echo "1/3 Cloudflare Worker secret"
printf %s "$token" | "${WRANGLER[@]}" secret put UPLOAD_TOKEN --name sky-city-lfs
echo "2/3 GitHub Actions secret"
printf %s "$token" | gh secret set LFS_UPLOAD_TOKEN --repo "$REPO"
echo "3/3 macOS keychain"
printf 'protocol=https\nhost=%s\nusername=upload\n\n' "$HOST" | git credential reject
printf 'protocol=https\nhost=%s\nusername=upload\npassword=%s\n\n' "$HOST" "$token" | git credential approve

unset token
echo "Done: new upload password stored in Cloudflare, GitHub Actions and this Mac's keychain."
