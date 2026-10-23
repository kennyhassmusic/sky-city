# Reconcile — texture pack loader

Cloud agent marker for LUCA. Invariants were read from `docs/AGENT_OPS/INVARIANTS.md` before this change. No protected value was edited.

- PR: https://github.com/kennyhassmusic/sky-city/pull/5
- Commit: `953399e` wraps facade tiles by `floors_in_tile`, keeps tile and window wrap fields, and loads `equipment/`. Schema loader remains `784177c`.
- Branch: `cursor/texture-pack-loader-04ef`
- Base: `cursor/city-block-realism-04ef`
- Parent: `cd8b893`
- ALLOW-CHANGE: none
- city-sample: unchanged (`CitySamplePCG` stays)
- pr-guard-lfs: unchanged (25 / 100 / 300 MB)
- asset-licences: no new assets (AI packs are not in this change)
- no-real-brands: no new brand names
- lfs-r2: unchanged
- seed-determinism: sample manifest hash still `3b867770796a5ab07187d1c962f2f6a6d91a00b6b8eab4b6466ccbabdf50632b` (two builds matched). Pack choice is not part of the hash.
- Tests: `python3 -I Scripts/city/test_packs.py` (6 OK), `python3 -I Scripts/city/test_city.py` (46 OK)
- What: pack loader against the manifest schema, with CC0 fallback. Per-facade glass masks and window, bay and floor rects. A tile repeats with `floor % floors_in_tile`, so floors above the tile still use the authored rects and the glass mask. `floors_in_tile`, `bays_in_tile`, and window `wrap_group` / `pieces` are kept. `equipment/` is a category. Ground potholes and stains are decals, not tiles. Stages of road dressing are not in this branch.
