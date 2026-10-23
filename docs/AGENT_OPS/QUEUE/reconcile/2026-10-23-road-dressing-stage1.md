# Reconcile — road dressing stage 1

Cloud agent marker for LUCA. Invariants were read from `docs/AGENT_OPS/INVARIANTS.md` before this change. No protected value was edited.

- PR: opened from branch `cursor/road-dressing-stage1-04ef` (URL filled in when the pull request exists)
- Branch: `cursor/road-dressing-stage1-04ef`
- Base: `cursor/city-block-realism-04ef` (stacked on the city-generator work; not folded into PR #3)
- Commit: `8c307c2094ff07a454bd80085b4bd18db8c12556`
- ALLOW-CHANGE: none
- city-sample: unchanged (`CitySamplePCG` stays)
- pr-guard-lfs: unchanged (25 / 100 / 300 MB)
- asset-licences: no new assets
- no-real-brands: generic labels only (STOP, YIELD, BUS, and the model's own street names)
- lfs-r2: unchanged
- seed-determinism: two `build_sample()` calls produced the same hash `6ffee243bf43fe6d29c2e1cd14880e731374590f7ca4fde6e7eefaed15ecdb8d`. Streetscape markings are in the hash, so this replaces the pre-dressing sample hash. PR #3's hash `3b867770796a5ab07187d1c962f2f6a6d91a00b6b8eab4b6466ccbabdf50632b` is unchanged on that branch.
- Tests: `python3 -I Scripts/roads/test_dressing.py` (5 OK), `python3 -I Scripts/city/test_city.py` (46 OK), `python3 -I Scripts/roads/test_profiles.py` (12 OK)
- What: stage 1 street dressing on existing roads. Stages 2–4 are written in `Scripts/roads/ROADMAP.md` and not built. Plan renders only; Blender was not run.
