# Maintainer setup checklist

One-time setup for Kenny before the repo goes public. Work through it top to bottom.

## Before anything is public

- [ ] **Run the build-agent audit** (the separate `AGENT_BRIEF.md` — not part of the repo) and review the report.
- [ ] **Remove restricted content** from the repo, *and from its history* if it was ever committed. Content that is only deleted in a new commit can still be downloaded from history. If history is contaminated, the simplest fix is a **fresh public repo** with clean history.
- [ ] **Replace or remove** the sedan, crossover and semi models. Keep the CGTrader pickup and robotaxi out of the public repo.
- [ ] **Scan for secrets:** API keys, tokens, personal paths, signing certificates.
- [ ] **Search for real brand names** in asset names, file names, code and in-game text, and rename them.
- [ ] **Decide** whether the Roadster model stays reserved or goes CC BY (see `LICENSE-ASSETS.md`).
- [ ] **Consider** a short consult with a lawyer about the vehicle shapes and the McGregor reveal event.

## GitHub

- [ ] **Create a GitHub organization** (free) to own the repo, and add yourself as owner.
- [ ] **Create the repo** in the organization. Start it private, flip to public when the list above is done.
- [ ] **Fill in placeholders:** `YOUR-ORG`, `YOUR-GITHUB-USERNAME`, contact email, community link, itch.io link, and every `TODO` comment.
- [ ] **Branch protection (ruleset) on `main`:**
  - Require a pull request before merging
  - Require 1 approval
  - Require review from code owners
  - Block force pushes and deletion
- [ ] **Git LFS:**
  - Clones download LFS files from Cloudflare R2, not GitHub (see [Git LFS downloads from Cloudflare R2](#git-lfs-downloads-from-cloudflare-r2)).
  - GitHub still stores every LFS upload, including art pushed to forks for pull requests, so set a **Git LFS budget** (even $0) at github.com/settings/billing/budgets as a safety net.
  - Check usage in billing settings now and then.
- [ ] **CLA check:** add the CLA Assistant Lite GitHub Action (contributor-assistant/github-action), pointing at `CLA.md`, so each first-time contributor signs before their pull request can merge. Signatures are stored in the repo.
- [ ] **Security (see SECURITY.md):**
  - Require two-factor authentication for everyone in the organization.
  - Ruleset on `main`: also require **signed commits**, **linear history**, and the **pr-guard** and CLA checks to pass.
  - Only Kenny adds the `maintainer-approved` label (pr-guard's gate for start-up scripts, build files and CI).
  - Turn on **private vulnerability reporting**, Dependabot alerts, secret scanning and push protection.
  - Restrict who can create releases and tags to Kenny.
  - Actions settings: allow only GitHub-made actions and ones you've reviewed; set the default workflow token to read-only; require approval to run workflows from first-time contributors.
  - Every 3 months, review who has access and step back unused roles.
- [ ] **Labels:** `good first issue`, `help wanted`, `bug`, `idea`, `asset`, `asset-needed`, `proposal`, `question`, `windows`, `performance`
- [ ] **Project board** for the public roadmap, with columns *Ideas → Planned → In progress → Done*.
- [ ] **Merge settings:** allow squash merging only, and auto-delete head branches.

## Git LFS downloads from Cloudflare R2

GitHub bills every Git LFS download to the repo owner: 10 GB a month free, and one full clone pulls about 2 GB. So clones download LFS files from a Cloudflare R2 bucket instead, where downloads are free.

### How it works

- **Downloads.** `.lfsconfig` sets `lfs.url` to the Worker `https://sky-city-lfs.goodmorrow.workers.dev/sky-city` (source in `tools/lfs-r2-worker/`). The Worker answers git-lfs's requests with short-lived signed links straight to the R2 bucket `sky-city-lfs`, so file bytes never pass through it. Small requests (an ordinary pull, checking out a pull request) are checked file by file, and anything not in R2 yet is fetched from GitHub instead.
- **Uploads go to GitHub, as before.** GitHub stays the source of truth.
  - Maintainers set `lfs.pushurl` to the main repo once per clone (below).
  - Contributors set it to their fork (CONTRIBUTING.md, "Sending art"). The Worker refuses uploads from anyone else, with a message that shows them the command.
- **The mirror.** The `lfs-mirror` GitHub Action runs after every push to `main`. It copies any new LFS files from GitHub into R2, so merged art reaches R2 a minute or two after the merge. R2 checks every upload against the file's SHA-256.
- **Locks.** Locking stays on GitHub: lock and unlock go to `lfs.pushurl`, and the Worker passes lock lists through to GitHub.
- **Abuse guards.** Per-address rate limits; uploads need the upload password; signed links expire after 2 hours. The Worker has no other access to the account.

### On each maintainer clone (already done on Kenny's Mac)

```bash
git config lfs.pushurl https://github.com/kennyhassmusic/sky-city.git/info/lfs
```

### The pieces

| Piece | Where |
|---|---|
| Cloudflare account | kennyhass@me.com (R2 needs a payment method on file, even on the free tier) |
| R2 bucket | `sky-city-lfs`; objects are stored as `sky-city/<sha256>` |
| Worker | `sky-city-lfs` at `sky-city-lfs.goodmorrow.workers.dev`; config in `tools/lfs-r2-worker/wrangler.toml` |
| Worker secrets | `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` (an R2 Account API token named `sky-city-lfs`: Object Read & Write, this bucket only); `UPLOAD_TOKEN` (the upload password) |
| GitHub secret | `LFS_UPLOAD_TOKEN`: the same upload password, used by the `lfs-mirror` Action |
| Kenny's Mac | the upload password in the macOS keychain, via git's credential helper (host `sky-city-lfs.goodmorrow.workers.dev`, user `upload`) |

### What it costs

At today's size it's **$0**:

- **R2 free tier, each month:** 10 GB of storage, 1 million writes (Class A), 10 million reads (Class B). Downloads (egress) are always free.
- **Workers free tier:** 100,000 requests a day.

One full clone uses about 50 Worker requests and about 4,700 R2 reads (one per file). So roughly **2,000 full clones a month** fit in the free tier. Beyond that:

- R2 reads cost $0.36 per million, about $0.002 per extra clone.
- Storage over 10 GB costs $0.015 per GB a month.
- If more than about 2,000 clones a day hit the Worker's daily limit, git-lfs shows an error until midnight UTC. Workers Paid ($5/month) lifts that limit.

To get a warning if anything starts costing money, turn on **Billing notifications** in the Cloudflare dashboard (Manage Account > Notifications). On GitHub, set the **Git LFS budget** (even $0) at github.com/settings/billing/budgets: fork uploads and the mirror's one-time download of new art still use GitHub's LFS quota.

### Common jobs

Run these from the repo root unless noted.

- **Rotate the upload password** (if it leaks, or once a year). It stores a new one in the Worker, the GitHub secret and this Mac's keychain, never printing it, and the old one stops working immediately:
  ```bash
  tools/lfs-r2-worker/rotate-upload-token.sh
  ```
- **Rotate the R2 key.**
  1. In the Cloudflare dashboard, go to R2 > Manage API tokens and create a new **Account API token**: Object Read & Write, bucket `sky-city-lfs` only.
  2. Store its two values. Each command asks you to paste a value:
     ```bash
     npx wrangler@4.151.3 secret put R2_ACCESS_KEY_ID --name sky-city-lfs
     ```
     ```bash
     npx wrangler@4.151.3 secret put R2_SECRET_ACCESS_KEY --name sky-city-lfs
     ```
  3. Delete the old token in the dashboard.
- **Check that R2 has every LFS file** (it compares sizes too):
  ```bash
  python3 tools/lfs-r2-worker/mirror.py --all --check
  ```
  To fill any gaps from this Mac, run it without `--check`. Or run the `lfs-mirror` Action by hand (Actions > lfs-mirror > Run workflow), which re-checks the whole history from GitHub.
- **Change the Worker.** Edit `tools/lfs-r2-worker/`, then from that folder run:
  ```bash
  npx wrangler@4.151.3 deploy
  ```
  Logs are in the Cloudflare dashboard under Workers & Pages > sky-city-lfs > Logs.
- **If R2 or the Worker is down.** Anyone can download straight from GitHub for a while:
  ```bash
  git -c lfs.url=https://github.com/kennyhassmusic/sky-city.git/info/lfs lfs pull
  ```
  To move everyone back to GitHub for good, delete `.lfsconfig`.

## Community

- [ ] **Community chat** (e.g. Discord), with channels for announcements, playtesting, bugs, dev and assets.
- [ ] **Contact email** for code-of-conduct reports, ideally not your personal address.
- [ ] **Seed 5–10 issues** before launch, including a few `good first issue`s. The vehicle replacements are perfect for this.

## Distribution

- [ ] **itch.io page:**
  - Start it restricted for a closed playtest.
  - Install **butler** and push builds to a `mac-arm64` channel.
- [ ] **Apple Developer Program** membership, for a **Developer ID** certificate.
- [ ] **Sign and notarize** each release so macOS doesn't block first launch.
- [ ] **Make a Shipping build** (not Development) for public releases.

## Every release

1. Bump the version and tag it in git (`v0.x.y`).
2. Build Shipping for Apple Silicon.
3. Check that `CREDITS_AND_LICENCES.txt` is current and included in the build.
4. Sign and notarize.
5. Push to itch.io with butler.
6. Publish GitHub release notes, linking to itch.io for the download.
7. Announce it on the community chat.
