# Reconcile — generate Sky City from the mashup layout

Cloud agent marker for LUCA. Invariants were read from `docs/AGENT_OPS/INVARIANTS.md` before this change. No protected value was edited.

- PR: https://github.com/kennyhassmusic/sky-city/pull/6
- Commit: `44715a5` (plinths, streets, roof clutter, four cameras re-rendered). Ground code is `1eeae41`. Spawn record remains `35b8bdd`.
- Branch: `cursor/citywide-generate-04ef`
- Base: `cursor/road-dressing-stage1-04ef`
- ALLOW-CHANGE: none
- city-sample: unchanged (`CitySamplePCG` stays in `SkyCity.uproject`). The new level is `/Game/Maps/SkyCityGenerated`. SkyCityMashup is not edited.
- pr-guard-lfs: unchanged (25 / 100 / 300 MB). GLBs under `SourceArt/CityGen/city/` are about 85 MB total. Each file is under 22 MB. The four preview PNGs add about 6 MB. Spawn JSON is about 6.8 MB and is not LFS.
- asset-licences: no new third-party assets. Meshes are generated. Materials are the existing CC0 slot names and are not embedded in the GLBs.
- no-real-brands: no new brand names
- lfs-r2: unchanged. `buildings_v3.json` and `plan_v3.json` were read, not modified.
- seed-determinism: seed 7. `python3 -I Scripts/city/test_generate_city.py` builds a tiny plan twice and the hashes match. The full city hash is `1e7ebb8635888c40699841b78beac5391e23200eb70247f118f4d0cc2b6390bf`.
- Tests: `python3 -I Scripts/city/test_generate_city.py` (OK) and `python3 -I Scripts/city/test_city.py` (46 OK). Blender 4.2.15 Cycles, 24 samples, denoise, 1280×720, AgX. Same three cameras from `city_manifest.json`, plus a dusk pass of the downtown street. Display-referred histograms (luma 0–255), exposure 0, all passed on the first try after the plinth and street pass: aerial day median 143.3, crushed 0.000, midtones 0.970; downtown street day median 77.5, crushed 0.007, midtones 0.896; residential day median 132.6, crushed 0.005, midtones 0.976; downtown street dusk median 85.2, crushed 0.006, midtones 0.908, p95 203.5.
- What: generator over every mashup lot and driveable road, then LOD0 meshes for a Chicago-core cluster (22 buildings, the script cap) and one Austin street where a high tier sits beside mid. Glazed floors are a curtain wall (mullions, a metal spandrel at each slab, tinted glass, an opaque room behind each pane). Facade UVs repeat at meters_u / meters_v, and bays are whole modules of bay_m. Each building sits on a concrete plinth. The fill is concrete at street level; sidewalks, curbs and asphalt come from the plan, with a frontage band at the wall. Grass is only the parkway. Street cameras that were off the carriageway stand on an asphalt pad. Leak decals are not meshed. Flat roofs have a parapet at least a metre tall, plus HVAC, a stair bulkhead and a water tank when the roof record is missing one. Street dressing props are simple meshes. Import script brings the GLBs into `/Game/Maps/SkyCityGenerated`. Daylight is CC0 Poly Haven `kloofendal_43d_clear_puresky` plus a sun; dusk is `kiara_9_dusk` with the sun at 4.5°. Pack polish and road stages 2–4 not built.
