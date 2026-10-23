# Reconcile — texture packs wired to the loader

Cloud agent marker for LUCA. Invariants were read from `docs/AGENT_OPS/INVARIANTS.md` before this change. No protected value was edited.

- PR: (JOB 1) texture packs committed and loader wired; not yet opened
- Commits:
  - `05d3670` wire `packs.load_library` / `districts.load_pack` to `SourceArt/ai_textures` (then legacy `Art/ai_textures`); warn on stderr when a district drops to CC0 while packs are installed; tests updated + per-district resolution test added
  - `e0cb54b` add the AI texture packs under `SourceArt/ai_textures` (1384 PNGs via Git LFS, 416 set manifests, `packs/districts.json`, root `manifest.json`, `LICENSE.json`, `README.md`)
  - `070422d` credit the packs in `CREDITS_AND_LICENCES.txt`
- Branch: `cursor/texture-packs-wired-04ef`
- Base / Parent: `cursor/texture-pack-loader-04ef` (`05d3670` after the loader commit's parent `8d7e6d0`)
- ALLOW-CHANGE: none
- city-sample: unchanged (`CitySamplePCG` stays)
- pr-guard-lfs: workflow unchanged (25 / 100 / 300 MB). NOTE: this PR adds ~887 MB of new LFS (largest file ~0.9 MB, so no per-file breach), over the 300 MB per-PR limit. This is expected for an art drop; the PR needs a maintainer's `maintainer-approved` label (the workflow routes very large art to a maintainer). No limit was changed.
- asset-licences: new assets are original / AI-generated (Grok Bot), owned by Kenny Hass Music LLC, under CC BY-NC 4.0 (project asset licence). Not third-party, no NC/SA third-party licence added. Recorded in `CREDITS_AND_LICENCES.txt` and `SourceArt/ai_textures/LICENSE.json`.
- no-real-brands: no brand names added (checked manifests/catalogue).
- lfs-r2: `.gitattributes` / `.lfsconfig` unchanged; PNG already routed to LFS, no new extension needed (packs are PNG only).
- seed-determinism: sample manifest hash still `3b867770796a5ab07187d1c962f2f6a6d91a00b6b8eab4b6466ccbabdf50632b` (two `block.py` builds matched). Texture-pack choice is not part of the manifest hash, so shipping the packs does not change it.
- Tests: `python3 -I Scripts/city/test_packs.py` (9 OK), `python3 -I Scripts/city/test_city.py` (46 OK), `python3 -I Scripts/roads/test_profiles.py` (12 OK). Pack audit (`tools/audit_check.py`, pointed at the in-repo copy): ALL BLOCKING PASS, incl. map paths resolve 1359/1359.
- What: the loader now resolves the real packs, so every district (houses/apartments by income tier) binds a pack facade instead of silently falling back to CC0. CC0 stays only as a genuine fallback and is now announced. Scratch (backups, audit examples, contact sheets, tiled previews) was not copied. The `packs.py` floor-modulo and other loader issues are left for JOB 2 as briefed.
