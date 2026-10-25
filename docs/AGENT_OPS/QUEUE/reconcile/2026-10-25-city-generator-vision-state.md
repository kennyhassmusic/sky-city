# Reconcile — City Generator Vision and State (Phase 0 gap 13)

Cloud agent marker for LUCA. Invariants were read from `docs/AGENT_OPS/INVARIANTS.md` before this change. No protected value was edited.

- PR: docs only — commit Kenny's City Generator Vision and State (2026-10-25) and link them from `AGENTS.md` and `CLAUDE.md`
- Branch: `cursor/city-generator-vision-state-06a4`
- Base: `main` (`a25704a`)
- ALLOW-CHANGE: none
- city-sample: unchanged (`CitySamplePCG` stays)
- pr-guard-lfs: workflow unchanged (25 / 100 / 300 MB). Markdown only.
- asset-licences: no assets added
- no-real-brands: no brand names added
- lfs-r2: `.gitattributes` / `.lfsconfig` unchanged
- seed-determinism: generator code untouched. `Scripts/city/`, `Scripts/roads/`, and the Blender mesher were not edited, so the manifest hash was not re-run.
- Tests: not run. This change is documentation. No Scripts/city or Scripts/roads files changed.
- What: `docs/CITY_GENERATOR_VISION.md` (stable contract) and `docs/CITY_GENERATOR_STATE.md` (living gaps) are copied from Kenny's 2026-10-25 pair. Owner decisions already in those files: City Shape v1 is the master city document; sky-city becomes the OSM importer and City Shape consumer; kit HISM in building-types is the shipping path and the Blender mesher here is study-only; seeded test city first, then the Chicago + Austin mashup; merge at sign-off; assets are not frozen. Existing `Scripts/city` docs were left in place. The OSM seeder and roadnet were not rewritten.
