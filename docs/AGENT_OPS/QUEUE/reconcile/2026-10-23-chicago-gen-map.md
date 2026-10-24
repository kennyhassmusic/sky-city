# Reconcile — Chicago generated map (cursor/chicago-gen-map)

Agent marker for LUCA. Invariants were read from `docs/AGENT_OPS/INVARIANTS.md` before each pass. No protected value was edited.

- PR: none (committed locally, not pushed). Branch `cursor/chicago-gen-map` off `main` `a25704a`. Pass 1 `4e33b22`; pass 2 is the commit carrying this marker. Report: `CHICAGO_REPORT.md`.
- Agents: Claude (claude.ai, scripts in a Linux VM), then Claude Code on Kenny's Mac (both passes' Blender, UE build, import, PIE).
- Pass 1: region crop, pack slots, real glass, `import_city_ue.py` with GLB folder and level, Loop GLBs, `/Game/Maps/SkyCityChicagoGen`, Maps[] and MapsToCook.
- Pass 2 (import pipeline only; generator untouched): Draco GLBs and 300 m street tiles (`blender_city.py`); facade kit (`blender_facade_kit.py` → `SourceArt/CityGen/kit`, `kit_layout.py`, `kit_city_ue.py`, `city_materials_ue.kit_walls`); `import_city_ue.py --buildings kit` with 11 tile sublevels (`/Game/Maps/SkyCityChicagoGen_Kit/`); box collision per setback tier; material reuse instead of delete; stale mesh cleanup; `measure_city_ue.py`.
- ALLOW-CHANGE: none
- city-sample: unchanged (`CitySamplePCG` in `SkyCity.uproject`; Content/Building, Prop, Material, Megascans, Vehicles, Plugins/CitySamplePCG not touched, checked with `find -newermt`). SkyCityMashup was not opened in pass 2 (every launch passed `/Engine/Maps/Entry` or the Chicago map).
- pr-guard-lfs: unchanged (25 / 100 / 300 MB). New LFS in pass 2: 214.9 MiB in 189 files, none over 25 MiB (largest sublevel 18 MB, largest GLB 21.5 MB).
- asset-licences: no third-party assets added. Kit modules are original (built by script); packs are the in-repo AI packs, CC0 scans as fallback.
- no-real-brands: nothing added.
- lfs-r2: `.gitattributes`, `.lfsconfig`, `lfs-mirror.yml` unchanged. Lockable generated assets were made writable locally (`chmod u+w`); no `git lfs lock` was taken.
- seed-determinism: default spawn hash `1e7ebb86…90bf` and chicago_loop `60286e1b…0a65` unchanged; kit layout identical over three runs. `block.py` untouched.
- Sensitive paths: pass 2 changes nothing in `Config/`, `Source/` or `.github/` (a temporary debug log in `SkysterCar.cpp` was reverted; `git diff Source` empty). Pass 1's Config/Source lines still need `maintainer-approved`.
- Tests: test_city 46 OK, test_profiles 12 OK, test_packs 13 OK, test_generate_city 15 OK.
