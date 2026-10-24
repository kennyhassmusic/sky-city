# Chicago walk-ups and tower shadows: report

Branch `cursor/chicago-gen-map`, level `/Game/Maps/SkyCityChicagoGen`. Two jobs:

1. The 61 `brick_walkup` buildings rebuilt to the walk-up rule set (`Design/WALKUP_RULES.md`).
2. The towers' striped shadows fixed with shadow-only proxies.

Everything here was done by an AI (Claude), with one helper agent for the textures, decals and kit meshes.

## 1. Walk-ups

### What changed
- **`Scripts/city/walkup.py` (new).** Each walkup's front is cut into lots of 6.1-7.6 m, and an end lot can be a
  double lot. 61 buildings became 157 lots, 4 of them vacant. Every lot is laid out as its own building:
  - 1-4 floors; a storefront floor of 4.0-4.6 m, 25-40% taller than the 3.05-3.35 m upper floors.
  - 1:2 sash windows, stacked, with the glass 15 cm behind the wall, stone sills, and flat, segmental or
    keystone lintels.
  - An oriel bay on about 40% of lots.
  - A storefront with bulkhead, display glass, transom lights, sign band and storefront cornice, a recessed
    entry with a step, and a separate stair door. The condition is original, remuddled or boarded, with
    awnings and roll-down or accordion gates.
  - A bracketed metal, corbelled brick or stone cornice that returns 0.3-0.9 m around a side that shows.
  - A 0.6-1.2 m front parapet, with a raised name plaque on some lots; side parapets stepping down to the rear.
  - Blind common-brick side walls, with a few small rear windows, and ghost signs on exposed walls.
  - Wooden back porches with stairs on every floor.
  - A membrane roof with 3-5 pieces of clutter toward the rear.
  - Streaks, soot and brick patches.
- **Variety rule.** No two lots within four lots share brick + cornice + floors + storefront. Neighbours differ in
  brick, and their tops differ by at least 30 cm.
- **Numbers.** All the numbers are in `walkup.RULES`. `kit_layout.build_layout` hands styled walkups to `walkup.py`;
  every other style is unchanged.
- **New placeholder art, all original, no third-party assets:**
  - Kit meshes (`blender_facade_kit.py`): `KIT_Box`, `KIT_Bracket`, `KIT_ArchLintel`, `KIT_Keystone`,
    `KIT_Awning`, `KIT_Dish`.
  - Brick textures (`brick_swatches.py`): red, brown, buff, cream and clinker face brick, Chicago common brick,
    and roof membrane. 2.4 m tiles, per-brick tint.
  - Decals (`walkup_decals.py`): streaks, soot, patches, six ghost signs, ten shop signs, gates and plywood.
    Generic words only, no brands.
- **Tests.** `Scripts/city/test_walkup.py` (15 tests) checks the checklist's numbers. All existing tests still pass:
  test_city 46, test_generate_city 23, test_packs 13, test_profiles 12.
- **Rerun check.** Layout, swatches and decals are byte-identical on a second run.
- **Import.** 354 buildings, 949,765 instances, 208 HISM components in 10 sublevels; map check 0 errors, 0 warnings.
  Walkups are about 37k instances; the generic kit they replace was about 31k.

### Screenshot grading
The shots are in `artifacts/previews/chicago_loop/walkup/`:
- three rows (`b_lot_osm_83`, 6 lots; `_58`, 5 lots; `_22`, 2 lots), five views each;
- the "before" is `artifacts/previews/chicago_loop/ue_styles_street.jpg` (b_lot_osm_22 as one 12.6 m block);
- they are editor viewport captures, taken over MCP.

| # | Checklist item | Grade | Evidence |
|---|---|---|---|
| 1 | Ground floor visibly taller than upper floors | **PASS** | `walkup_83_street`, `walkup_58_close` |
| 2 | Facade reads as 20-25 ft per lot | **PASS** | `walkup_83_street`: six lots on 41.5 m |
| 3 | Upper windows tall, narrow (1:2), stacked | **PASS** | `walkup_83_street`, `walkup_22_close` |
| 4 | Windows recessed, with lintels and sills | **PASS** | `walkup_58_close`, `walkup_22_close` (keystones, arches, sills past the jambs) |
| 5 | Cornice projects and casts a shadow | **PASS** | `walkup_58_corner`, `walkup_58_parapet_steps_crop.png` (brackets in shadow) |
| 6 | Storefront has bulkhead, glass, transom, sign band | **PASS** | `walkup_83_street` (transom lights, sign band, storefront cornice) |
| 7 | Recessed store entry and separate upstairs door | **PASS** | `walkup_58_close` (painted stair doors), `walkup_83_street` (recess) |
| 8 | Front brick differs from side and rear common brick | **PASS** | `walkup_58_corner` (red front, common side), `walkup_83_rear` |
| 9 | Ornament stops 1-3 ft around the corner | **PASS** | `walkup_58_parapet_steps_crop.png`: the cornice turns the corner and stops |
| 10 | Party walls mostly blind | **PASS** | `walkup_58_corner`, `walkup_83_corner`, `walkup_22_corner` |
| 11 | Parapet rises above the roof | **PASS** | `walkup_83_roofs`, `walkup_58_roofs` |
| 12 | Side parapets step down toward the rear | **PASS (weak)** | `walkup_58_parapet_steps_crop.png`: two 0.3-0.4 m steps behind the cornice. Hard to see from the street, because the rule's 2-4 ft parapet leaves little to step down |
| 13 | Roof has 3-5 clutter items | **PASS** | `walkup_83_roofs`, `walkup_22_roofs` (vents, hatch, condensers, skylight, antenna). Small at that range |
| 14 | No water tank | **PASS** | none in the code (`ROOF_KINDS`); none in the roof shots |
| 15 | Rear porches present | **PASS** | `walkup_83_rear`, `walkup_58_rear` (decks, railings, stairs every floor) |
| 16 | No two adjacent buildings share brick, cornice, height and storefront | **PASS** | `test_walkup.VarietyTest`; `walkup_83_street` |
| 17 | Rooflines vary along the block | **PASS** | `walkup_83_street`, `walkup_58_street` (1-4 floors, tops at least 30 cm apart) |
| 18 | Weathering visible: streaks, soot, patches | **FAIL** | Patches read as dark rectangles (`walkup_83_street`, under the second-floor windows). Streaks and soot are too faint to see. The decals need lighter alpha, and the patch should take the wall's tone |
| 19 | Window interiors vary | **PASS** | blinds, curtains, AC units, lit and dark rooms (`walkup_83_close`, `walkup_58_close`) |
| 20 | No visible texture tiling at 20 m | **PASS** | `walkup_83_street`, `walkup_58_street`: no repeat visible across a 41 m row |

**19 PASS (one weak), 1 FAIL, 0 MISSING PIECE** on the checklist. The rules call for these pieces, and none are
built as kit art; all are MISSING PIECE:
- **Corner chamfer or turret:** MISSING PIECE. Every Chicago walkup footprint has a single street front, so no
  lot is a corner lot.
- **Open sashes:** MISSING PIECE. Window variety is blinds, curtains, AC units and lit or dark rooms.
- **Roof pitch toward the rear (1/4 in per ft):** MISSING PIECE. The deck is flat; at that slope nobody would see it.
- **Gangways between buildings:** MISSING PIECE. The OSM footprints touch or leave their own gaps; nothing is cut.

### Fixed along the way
- **Signs upside down.** `KIT_Decal` shows its texture turned 180 degrees in Unreal. The generated decals are now
  stored rotated (`walkup_decals.py`). The pack decals and pack storefront panels (`KIT_Panel`) the other styles
  use go through the same UVs, so their graffiti and lettering are probably upside down too. Not changed here;
  worth a look.
- **28 MapCheck warnings.** The new flat materials lacked the instanced-static-mesh usage flag, which a cooked
  build would draw with the default material. `city_materials_ue._flat` now sets it.
- **Ghost-sign text** ran off its panel; it now fits.

### Still weak
- **Shade.** North-facing fronts are lit only by the blue sky, so their brick reads grey (`walkup_83_street`). In
  sun the tones are clear (`walkup_58_close`, `walkup_22_close`). It is the lighting, not the material.
- **Lit shops blow out** in shade. The chance of a lit shop is down to 35%, but the lit interior material is
  bright for a display window.
- **Stairs** are treads without stringers.

## 2. Tower shadows

**Cause:** the kit's glass casts no shadow, and nothing opaque sits behind it. Sun went through every window band,
so the streets and facades were striped (`shadow_before_street.jpg`).

**Fix:**
- Each kit tower tier gets a hidden box, inset 0.85 m behind the panes' room backs.
- Each walk-up lot gets one too; it is inset only at the row's ends, so no light leaks between lots.
- The boxes are one group, `KIT_Wall|shadow`: 791 boxes in one HISM. The component is not visible, is hidden in
  game, casts a hidden shadow, and has no collision.
- The glass still casts no shadow.
- Code: `kit_layout.SHADOW` / `SHADOW_INSET`, `walkup._collision`, `kit_city_ue` (the component settings).
- Baked mode (`--buildings baked`) is not covered; the level uses the kit.

**How it was measured** (`Scripts/city/shadow_ab_ue.py`):
- One editor session, four cameras: the GPU cameras from `CHICAGO_REPORT.md` (aerial, street) and two walk-up
  streets.
- The proxies' casting is switched off, then on, twice per camera.
- Each pass waits 8 s for streaming and the shadow cache, then reads 3 `ProfileGPU` dumps (`<root>` and
  `ShadowDepths`, inclusive). That is 6 samples per side.

| Camera | GPU frame off → on | ShadowDepths off → on |
|---|---|---|
| street (report camera) | 16.40 → 17.01 ms (+0.6) | 1.36 → 1.06 ms |
| b_lot_osm_58 street | 16.14 → 16.52 ms (+0.4) | 0.90 → 1.13 ms |
| b_lot_osm_22 street | 14.84 → 15.71 ms (+0.9) | 0.94 → 1.04 ms |
| aerial (report camera) | 19.62 → 21.92 ms (+2.3) | 0.46 → 0.92 ms |

The samples are noisy: they swing 1.5-4 ms within one state. At street level the cost is under about 1 ms and
can't be told apart from that noise. From the aerial camera, which sees every tower, it is about +2 ms.

Before and after shots, same camera, proxies off and on:
- `shadow_before_street.jpg` / `shadow_after_street.jpg`: the stripes on the street and on the left facade become
  one solid shadow.
- The same pair for `b_lot_osm_58_street`, `b_lot_osm_22_street` and `aerial`.

## How to rebuild
```bash
python3 -I Scripts/city/brick_swatches.py        # brick and roof swatches (merged into swatches.json)
python3 -I Scripts/city/walkup_decals.py         # walk-up decals
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 \
  -P Scripts/city/blender_facade_kit.py           # kit meshes, now 18
python3 -I Scripts/city/kit_layout.py --region chicago_loop
# in the editor (or as a startup script): the import, as in CHICAGO_REPORT.md
py Scripts/city/import_city_ue.py --glbs SourceArt/CityGen/chicago --buildings kit \
  --level /Game/Maps/SkyCityChicagoGen --spawn Saved/CityGen/sky_city_spawn_chicago_loop.json
# review shots and the shadow A/B (live editor, level open):
python3 -I Scripts/city/walkup_shots_ue.py --plan
py Scripts/city/walkup_shots_ue.py tag=after
py Scripts/city/shadow_ab_ue.py frames=3 settle=8 rounds=2
python3 -I Scripts/city/shadow_ab_ue.py --read
python3 -I Scripts/city/test_walkup.py
```

**Process notes:**
- As in pass 3, the generated `Content/City/Generated/Chicago/**` and `SkyCityChicagoGen*` files were made
  writable locally (`chmod u+w`); no `git lfs lock`.
- The editor's `SecurityToken` line in `Config/DefaultEngine.ini` was reverted.
- `-ExecutePythonScript` quits the editor when the script ends, and logs a harmless crash in SemanticSearch on the
  way out. The tick-based shot scripts need a live editor (`-ExecCmds="py <absolute path>"`, or the console).
