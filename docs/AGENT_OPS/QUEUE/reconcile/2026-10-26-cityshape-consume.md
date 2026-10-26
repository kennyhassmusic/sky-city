# Reconcile — City Shape v1 consumer

Cloud agent marker for LUCA. Invariants were read from `docs/AGENT_OPS/INVARIANTS.md` before this change. No protected value was edited.

- PR: consume a City Shape v1 document as sky-city drive centrelines
- Branch: `cursor/cityshape-consume-194c`
- Base: `main`
- ALLOW-CHANGE: none
- city-sample: unchanged (`CitySamplePCG` stays)
- pr-guard-lfs: workflow unchanged (25 / 100 / 300 MB). Python and a small JSON fixture only.
- asset-licences: no assets added
- no-real-brands: no brand names added
- lfs-r2: `.gitattributes` / `.lfsconfig` unchanged
- seed-determinism: existing generator path untouched. `seed_from_plan` and `block.py` are not rewritten. New entry is `seed_from_city_shape` / `Scripts/city/cityshape.py`.
- Tests: `python3 -I Scripts/city/test_cityshape.py`, `python3 -I Scripts/city/test_city.py`, `python3 -I Scripts/city/test_generate_city.py`
- What: sky-city loads a City Shape v1 export (nodes, edges, water when present) into the centreline roads `network.py` already splits. The OSM importer stays in building-types. Fixture `fixtures/cityshape/seed7_excerpt.json` is a trimmed stand-in, not a Chicago or Austin dump. No seam, no invented districts or township ids, no invented width/speed/capacity, no roadnet dressing.
