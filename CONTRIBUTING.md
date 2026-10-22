# Contributing to Sky City

Thanks for helping build Sky City! This guide covers how to contribute and the few rules that keep the project healthy and legally shippable.

**Please read the asset rules (section 3) before adding any model, texture, sound or other content.** They are the rules we are strictest about.

---

## 1. Ways to help

- **Play and report bugs.** Open an issue using the *Bug report* template.
- **Suggest ideas.** Use the *Feature idea* template, or bring it up on the community chat first.
- **Write code.** Car physics, traffic, HUD, game systems, tools.
- **Make content.** Original vehicles, landmarks, props. Check open issues labelled `asset-needed`.
- **Improve the city generator.** The Python and Blender scripts that build the map from OpenStreetMap.

New here? Look for issues labelled **`good first issue`**.

## 2. How to contribute

1. **Check for an issue first.** For anything bigger than a small fix, open or comment on an issue before you start. Nobody likes two people building the same thing.
2. **Fork** the repository and create a branch from `main`:
   `git checkout -b fix/traffic-signal-timing`
3. **Make your change.** Keep each pull request focused on one thing. If it adds or changes art, see [Sending art](#sending-art-git-lfs-files) below.
4. **Sign the CLA** the first time (see section 6). The bot will ask in your pull request.
5. **Open a pull request** and fill in the template, including the asset checklist.
6. **Respond to review.** A maintainer will review it. Most PRs need a round or two of changes, so don't take it personally.

### Branch names

`feature/…`, `fix/…`, `asset/…`, `docs/…`, `tools/…`

### Sending art (Git LFS files)

Everything Git LFS stores (`.uasset`, `.umap`, images, models, sounds, see `.gitattributes`) downloads from Sky City's own read-only server on Cloudflare, which is set in `.lfsconfig`. To send new or changed art in a pull request, upload it to **your fork** on GitHub instead. Run this once in your clone, with your GitHub name:

```bash
git config lfs.pushurl https://github.com/YOUR-GITHUB-NAME/sky-city.git/info/lfs
```

Then push as usual. If you forget, the push stops with a message that shows this same command. After your pull request is merged, your art is copied to the download server automatically. Code-only changes need none of this.

Keep each file under 100 MB and a pull request's new art under 300 MB in all (the `pr-guard` check enforces this). For anything bigger, share a download link in the pull request instead and Kenny will add it to the download server himself.

## 3. Asset rules — read before adding content

Sky City must be shippable, both free and possibly paid. One badly licensed model can block a release. So:

**Every new asset needs a licence that allows commercial use and redistribution inside a packaged game.**

| Licence | OK? |
|---|---|
| Your own original work, contributed under the [CLA](CLA.md) | ✅ |
| CC0 / public domain (Poly Haven, ambientCG, USGS, USDA NAIP) | ✅ |
| CC BY 4.0 from a trustworthy source | ✅ with credit |
| Anything **NC** (non-commercial) | ❌ |
| Anything **ND** (no derivatives) | ❌ |
| "Editorial use only" | ❌ |
| Paid or royalty-free store assets (CGTrader, TurboSquid, Fab, etc.) | ❌ in this repo — ask a maintainer first |
| Ripped from another game or mod, or "found online" | ❌ never |

**For every asset you add:**
1. Add an entry to `CREDITS_AND_LICENCES.txt`: what it is, the author, a source link and the licence.
2. Tick the asset boxes in the pull request template.

**Real-world places and products:**
- Landmarks should be modelled by you from public references, such as photos and maps. Don't use someone else's model.
- **No real brand names, logos or badges** on vehicles, buildings or signs. Use generic or invented names.
- Copyrighted sculptures and artworks are represented by stand-ins, not faithful replicas. Ask in the issue if you're unsure.

**Never commit:**
- Epic City Sample content (see `docs/SETUP_CITY_SAMPLE.md`)
- Unreal Engine source code or engine tools
- Any third-party asset whose licence doesn't allow public redistribution

## 3b. Security rules for every pull request

These keep the project safe from hidden malicious code (see [SECURITY.md](SECURITY.md)). The `pr-guard` check enforces the first one automatically.

- **No binaries, archives or executables** outside `Content/` and `SourceArt/`: no `.dylib`, `.so`, `.exe`, `.zip`, `.tar.gz` and so on. Test data must be readable text.
- **Nothing that runs by itself.** Don't add editor start-up scripts (`init_unreal.py`, `Content/Python/`), editor-utility assets that run at startup, or build steps that download things. If you think one is needed, propose it in an issue first.
- **No new dependencies or tools** without discussing them in an issue first.
- **Keep build and CI changes small and readable**, with a clear reason. These always need Kenny's review.
- **Explain what your code does** in the pull request. Reviewers are asked to reject changes they can't follow.

## 4. Working with Unreal binary files

`.uasset` and `.umap` files can't be merged. If two people edit the same one, someone loses their work. We use Git LFS **file locking** to prevent this.

```bash
git lfs locks                                # see what's locked and by whom
git lfs lock Content/Maps/SkyCity.umap       # lock before you edit
git lfs unlock Content/Maps/SkyCity.umap     # unlock when your PR is merged or abandoned
```

- **Lock before you edit** any `.uasset` or `.umap`. Lockable files are read-only until you lock them.
- **Don't hold locks for days.** If you're stuck, unlock and say so in the issue.
- **Prefer small, separate assets** over editing big shared maps. Use sub-levels and data assets where you can.

Locking needs write access to the main repository. If you're contributing from a fork, say which assets you plan to touch in the issue, so a maintainer can hold the lock for you.

Maintainers: locks live on GitHub, so point Git LFS's uploads and locks there once per clone:
`git config lfs.pushurl https://github.com/kennyhassmusic/sky-city.git/info/lfs`

## 5. Code style

- Follow the [Epic C++ coding standard](https://dev.epicgames.com/documentation/en-us/unreal-engine/epic-cplusplus-coding-standard-for-unreal-engine).
- **Python:** PEP 8. Scripts must run headless without manual steps.
- Comment the *why*, not the *what*.
- Don't commit generated files: `Binaries/`, `Intermediate/`, `Saved/`, `DerivedDataCache/` or Xcode project files.
- Make sure the project compiles and the map loads before you open a PR.

## 6. The Contributor License Agreement (CLA)

Before your first pull request can be merged, you sign the [Contributor License Agreement](CLA.md). You do it once, by replying in the pull request when the CLA bot asks.

**What you're agreeing to:** you keep the copyright in your work. You give Kenny Hass Music LLC the right to use it in Sky City, including in versions that are sold, and to license it under any terms. Sky City itself is source-available for noncommercial use: anyone can play, change and share it for free, but only Kenny Hass Music LLC may sell it. See [LICENSE](LICENSE) and [LICENSE-ASSETS.md](LICENSE-ASSETS.md).

## 7. Review and merging

- Every pull request needs **at least one approval** from a maintainer or code owner before merging.
- Changes to core systems (car physics, build setup, licences) need approval from their code owner (see `.github/CODEOWNERS`).
- Maintainers merge using **squash and merge**, to keep `main` tidy.

## 8. Becoming a collaborator

Collaborator roles are earned through contributions. See [GOVERNANCE.md](GOVERNANCE.md).

## 9. Getting help

Ask in [GitHub Discussions](https://github.com/kennyhassmusic/sky-city/discussions), or open an issue labelled `question`.
