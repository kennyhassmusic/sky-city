# Reconcile — Chicago generated map (cursor/chicago-gen-map)

Agent marker for LUCA. Invariants were read from `docs/AGENT_OPS/INVARIANTS.md` before this change. No protected value was edited.

- PR: none (committed locally, not pushed). Branch `cursor/chicago-gen-map` off `main` `a25704a`. Report: `CHICAGO_REPORT.md`.
- Agents: Claude (claude.ai, scripts in a Linux VM), then Claude Code on Kenny's Mac (Blender export, UE build, import, PIE).
- Done: region crop (`generate_city.py --region chicago_loop`); pack slots (`pack_slots.py`, incl. `massing_sets`) and editor materials (`city_materials_ue.py`, `facade_material_ue.py`); real glass; `import_city_ue.py` (`--glbs/--level/--spawn`, complex collision, Nanite off, stage, pack-faced massing, tiled ground slab); `import_block_ue.py` on the same path; `blender_city.py` region mode (225 MiB budget); Loop GLBs in `SourceArt/CityGen/chicago`; level `/Game/Maps/SkyCityChicagoGen` with `Content/City/Generated/Chicago`; map in `SkysterCar.h` Maps and `Config/DefaultGame.ini` MapsToCook; C++ rebuilt; PIE drive and screenshots.
- ALLOW-CHANGE: none
- city-sample: unchanged (`CitySamplePCG` in `SkyCity.uproject`; Content/Building, Prop, Material, Megascans, Vehicles, Plugins/CitySamplePCG not touched). SkyCityMashup was not edited. The editor opened it as its startup map on two launches before later launches passed the Chicago map; it was not changed or saved.
- pr-guard-lfs: unchanged (25 / 100 / 300 MB). New LFS in this change: 281.5 MiB. Two street GLBs over 25 MiB (warning only).
- asset-licences: no third-party assets added. Packs are the in-repo AI packs (Kenny Hass Music LLC); CC0 scans as fallback. Previews and screenshots are renders of this project.
- no-real-brands: nothing added.
- lfs-r2: `.gitattributes`, `.lfsconfig`, `lfs-mirror.yml` unchanged.
- seed-determinism: default spawn byte-identical to the committed example (hash `1e7ebb86…90bf`); chicago_loop → `60286e1b…0a65` on every run. `block.py` untouched.
- Sensitive paths: `Config/DefaultGame.ini`, `Source/SkyCity/*` changed on Kenny's brief → a PR needs `maintainer-approved`. The editor's `SecurityToken` line in `Config/DefaultEngine.ini` was reverted, not committed.
- Tests: test_city 46 OK, test_profiles 12 OK, test_packs 13 OK, test_generate_city 10 OK.
