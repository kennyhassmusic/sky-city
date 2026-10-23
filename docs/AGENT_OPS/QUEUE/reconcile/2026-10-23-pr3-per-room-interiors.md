# Reconcile — PR #3 per-room interiors

Cloud agent marker for LUCA. Invariants were read from `docs/AGENT_OPS/INVARIANTS.md` before this change. No protected value was edited.

- PR: https://github.com/kennyhassmusic/sky-city/pull/3
- Branch: `cursor/city-block-realism-04ef`
- Base: `main`
- Parent at start: `e1f8edf`
- Commit: `2c569c5172b17a748b8ea0813799f533c8b9188b`
- ALLOW-CHANGE: none
- city-sample: unchanged (`CitySamplePCG` stays)
- pr-guard-lfs: unchanged (25 / 100 / 300 MB)
- asset-licences: no new assets
- no-real-brands: no new brand names
- lfs-r2: unchanged
- seed-determinism: sample manifest hash still `3b867770796a5ab07187d1c962f2f6a6d91a00b6b8eab4b6466ccbabdf50632b`
- Tests: `python3 -I Scripts/city/test_city.py` (46 OK), `python3 -I Scripts/roads/test_profiles.py` (12 OK)
- What: per-room window interiors on every building type (room id, bounds, one light, one curtain). Grass (parkway), sidewalks, and straight plus return curbs confirmed in the streetscape test.
