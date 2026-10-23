# Reconcile — generate Sky City from the mashup layout

Cloud agent marker for LUCA. Invariants were read from `docs/AGENT_OPS/INVARIANTS.md` before this change. No protected value was edited.

- PR: https://github.com/kennyhassmusic/sky-city/pull/6
- Commit: `9c6b8bf` (uniform facade UVs, downtown street day, tower-side close-up). Code is `a8d7ef8`. Spawn record remains `35b8bdd`.
- Branch: `cursor/citywide-generate-04ef`
- Base: `cursor/road-dressing-stage1-04ef`
- ALLOW-CHANGE: none
- city-sample: unchanged (`CitySamplePCG` stays in `SkyCity.uproject`). The new level is `/Game/Maps/SkyCityGenerated`. SkyCityMashup is not edited.
- pr-guard-lfs: unchanged (25 / 100 / 300 MB). GLBs under `SourceArt/CityGen/city/` are about 47.4 MB total. Each file is under 22 MB. `CG_chicago_core_03.glb` is gone because the repack fit in three core files. Preview PNGs stay small. Spawn JSON is about 6.8 MB and is not LFS.
- asset-licences: no new third-party assets. Meshes are generated. Materials are the existing CC0 slot names and are not embedded in the GLBs.
- no-real-brands: no new brand names
- lfs-r2: unchanged. `buildings_v3.json` and `plan_v3.json` were read, not modified.
- seed-determinism: seed 7. `python3 -I Scripts/city/test_generate_city.py` builds a tiny plan twice and the hashes match. The full city hash is `1e7ebb8635888c40699841b78beac5391e23200eb70247f118f4d0cc2b6390bf`.
- Tests: `python3 -I Scripts/city/test_generate_city.py` (OK), `python3 -I Scripts/city/test_city.py` (46 OK), `python3 -I Scripts/city/test_face_uv.py` (OK). UV faces 371996, density fails 0, windows 54448, window fails 0, target aspect 1.2632. Worst density U/V is 1.0134. Blender 4.2.15 Cycles, 24 samples, denoise, 1280×720, AgX. This pass re-rendered downtown street day and a tower-side close-up. The other three cameras were not moved and were not re-rendered. Display-referred histograms (luma 0–255), exposure 0, both passed on the first try: downtown street day median 107.3, crushed 0.006, midtones 0.977, p95 193.7; tower side day median 173.1, crushed 0.000, midtones 0.881, p95 212.0.
- What: generator over every mashup lot and driveable road, then LOD0 meshes for a Chicago-core cluster (22 buildings, the script cap) and one Austin street where a high tier sits beside mid. Every facade face is projected from its own width and height, U and V at one scale. Windows match the 24×19 lit rect. Leftover length is a pilaster. The build fails if texel density or window aspect is outside 3%. Glazed floors stay a curtain wall. Import script brings the GLBs into `/Game/Maps/SkyCityGenerated`. Deferred and not started: floating bases, ground surfaces, grime, roofs, Blender hardening and a mesh census, six-view sheets, loader floor bugs (`Design/ROADMAP.md`, Next).
