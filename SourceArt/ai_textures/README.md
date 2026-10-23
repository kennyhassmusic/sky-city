# Sky City AI texture packs

AI-generated PBR texture packs that dress the procedural city. Original work owned
by Kenny Hass Music LLC, under the project asset licence (CC BY-NC 4.0). Generating
tool and licence: `LICENSE.json`. Full generation record: `manifest.json`.

## Layout

- `facades/`, `ground/`, `storefronts/`, `interiors/`, `decals/`, `equipment/`, `props/`
  — one folder per *set*, each with a `manifest.json` (role, district, tier, size,
  scale, glass masks, window/bay/floor rects). These are what the loader reads.
- `packs/` — the actual image maps (`*.png`), organised `packs/<district>/[<tier>/]<kind>/`,
  plus `packs/common/` (graffiti, vegetation, encampment) shared across districts. The
  set manifests point here with relative paths. Through Git LFS.
- `packs/districts.json` — the per-district catalogue (palette, materials, mixing rules).

## Who reads it

`Scripts/city/packs.py` (`load_library`) and `Scripts/city/districts.py` (`load_pack`).
With no explicit root they look here first (`SourceArt/ai_textures`), then the legacy
`Art/ai_textures`. A district that cannot find its pack and drops to the CC0 slots is
warned about on stderr, not silently swallowed. See `Scripts/city/test_packs.py`.

Validate the packs with `python3 tools/audit_check.py` (needs Pillow, NumPy).
