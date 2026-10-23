# Reconcile — generate Sky City from the mashup layout

Cloud agent marker for LUCA. Invariants were read from `docs/AGENT_OPS/INVARIANTS.md` before this change. No protected value was edited.

- PR: https://github.com/kennyhassmusic/sky-city/pull/6
- Commit: `9c82632` (meshes). Spawn record remains `35b8bdd`.
- Branch: `cursor/citywide-generate-04ef`
- Base: `cursor/road-dressing-stage1-04ef`
- ALLOW-CHANGE: none
- city-sample: unchanged (`CitySamplePCG` stays in `SkyCity.uproject`). The new level is `/Game/Maps/SkyCityGenerated`. SkyCityMashup is not edited.
- pr-guard-lfs: unchanged (25 / 100 / 300 MB). New GLBs under `SourceArt/CityGen/city/` are about 66 MB total. Each file is under 22 MB. Spawn JSON is about 6.8 MB and is not LFS.
- asset-licences: no new third-party assets. Meshes are generated. Materials are the existing CC0 slot names and are not embedded in the GLBs.
- no-real-brands: no new brand names
- lfs-r2: unchanged. `buildings_v3.json` and `plan_v3.json` were read, not modified.
- seed-determinism: seed 7. `python3 -I Scripts/city/test_generate_city.py` builds a tiny plan twice and the hashes match. The full city hash is `1e7ebb8635888c40699841b78beac5391e23200eb70247f118f4d0cc2b6390bf`.
- Tests: `python3 -I Scripts/city/test_generate_city.py` (OK). Blender 4.2.15 Cycles, 16 samples, 1280×720: downtown aerial, downtown street, residential street.
- What: generator over every mashup lot and driveable road, then LOD0 meshes for a Chicago-core cluster and one Austin street where a high tier sits beside mid. Street dressing props are simple meshes. Import script brings the GLBs into `/Game/Maps/SkyCityGenerated`. Pack polish and road stages 2–4 not built.
