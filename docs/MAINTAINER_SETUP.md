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
  - Check usage in billing settings.
  - Add a payment method and a budget, so LFS isn't disabled when the free quota runs out.
  - Remember that forks and clones count against the organization.
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
