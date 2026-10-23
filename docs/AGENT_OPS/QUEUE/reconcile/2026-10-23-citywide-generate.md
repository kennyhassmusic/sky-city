# Reconcile — generate Sky City from the mashup layout

Cloud agent marker for LUCA. Invariants were read from `docs/AGENT_OPS/INVARIANTS.md` before this change. No protected value was edited.

- PR: https://github.com/kennyhassmusic/sky-city/pull/6
- Commit: `35b8bdd`
- Branch: `cursor/citywide-generate-04ef`
- Base: `cursor/road-dressing-stage1-04ef`
- ALLOW-CHANGE: none
- city-sample: unchanged (`CitySamplePCG` stays in `SkyCity.uproject`). The new level is `/Game/Maps/SkyCityGenerated`. SkyCityMashup is not edited.
- pr-guard-lfs: unchanged (25 / 100 / 300 MB). Spawn JSON is about 6.8 MB, not LFS.
- asset-licences: no new assets. Materials are the existing CC0 slot names.
- no-real-brands: no new brand names
- lfs-r2: unchanged. `buildings_v3.json` and `plan_v3.json` were read, not modified.
- seed-determinism: seed 7. `python3 -I Scripts/city/test_generate_city.py` builds a tiny plan twice and the hashes match. The full city hash is `1e7ebb8635888c40699841b78beac5391e23200eb70247f118f4d0cc2b6390bf`.
- Tests: `python3 -I Scripts/city/test_generate_city.py` (OK)
- What: generator over every mashup lot and driveable road. Street dressing included. Pack polish and road stages 2–4 not built. Import script spawns a comparison level beside City Sample.
