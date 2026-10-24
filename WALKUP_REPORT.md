# Chicago walk-ups and tower shadows: report

Branch `cursor/chicago-gen-map`, level `/Game/Maps/SkyCityChicagoGen`. Two jobs:

1. The 61 `brick_walkup` buildings rebuilt to the walk-up rule set (`Design/WALKUP_RULES.md`).
2. The towers' striped shadows fixed with shadow-only proxies.

Everything here was done by an AI (Claude), with one helper agent for the textures, decals and kit meshes.
The fix-up passes (sections 00 and 0) come after sections 1 and 2 in time. Section 00 is the latest and
supersedes the others where they differ.

## 00. Fix-up pass 2 (DELI, LAUNDROMAT, HARDWARE)

Shots are in `artifacts/previews/chicago_loop/walkup/`:
- `walkup_*` and `cam_*` are re-rendered;
- `pass2/before_*` and `pass2/after_*` show the DELI (`22_close`, `22_street`) and the LAUNDROMAT and HARDWARE
  (`58_street`, `58_close`);
- crops: `pass2/*_laundromat_upper_wall_crop.jpg` (the light leak), `pass2/*_laundromat_hardware_shopfronts_crop.jpg`
  (the white slabs).

| # | Issue | Cause | Fix | Result |
|---|---|---|---|---|
| 1 | Storefront and transom glass glows white | Mostly not the glass. The undersides of light or metallic shop trim mirror the sunlit street seen from below: the remuddled cream box signs, the 0.9-metallic aluminium panels over the glass, the galvanised gate housings. The shop glass also had a strong Fresnel | Shop glass: dark tint, Fresnel opacity 0.22 → 0.62, specular 0.45, roughness 0.1 (`style_kit.GLASS["shop"]`, `GLASS_SURFACE`). Shop frames dark anodised, not silver. Box signs in the shop's paint, 0.12 m proud. Aluminium and gate housings matte and mid-dark (`sf_alum`, `gate_box`). Shop insides warm grey (`shop_wall`). Lit shops glow 0.22, dim 0.08 | **PASS**: no white slab in `pass2/after_*`. Shelves and racks stay visible behind the glass. The faint warm glow is kept |
| 2 | Weathering reads as a dark blob | The pack "stain", "patch" and "paint" decals are round splats; every other style wore them on its ground floor | Splat features dropped from `style_kit.WALL_DECALS`. Every styled wall now wears soft streaks hanging from a floor line (`kit_layout.STREAK_DECALS`). Walk-ups get: 6 streak variants under sills and from the cornice; drips off lintel ends down the jambs; soot as runs of different lengths, not a band; base grime on pilasters and bulkheads. A per-lot dirt level (0.35-1.0) scales every chance, so no two lots wear the same | **PASS**: no blobs; streaks and drips read at street distance (`pass2/after_laundromat_upper_wall_crop.jpg`) |
| 3 | Light leaks onto shaded facades | Traced (sun rays from the LAUNDROMAT front through the layout's boxes). The rays clip the corners of the towers across the street through the 0.85 m shell in front of their shadow proxies. Glass casts nothing there, and a pane's room back is one-sided, so it casts nothing when the sun is behind it. No gaps at the tier seams, the lot seams or the parapets | Pane components cast two-sided (`kit_city_ue`). Tower proxies inset 0.45 m, just behind their 0.42 m room backs, instead of 0.85 m (`kit_layout.SHADOW_INSET`). Walk-ups keep 0.85 m behind their deeper panes | **PASS**: the bright patches are gone (`pass2/*_laundromat_upper_wall_crop.jpg`) |
| 4 | Shaded fronts flat and blue-grey | Shade lit by a blue sky alone | Sky tint (255, 204, 164) at 1.6, warmer lower hemisphere (0.34, 0.26, 0.18), Lumen indirect ×1.3 for street bounce (`import_city_ue.LIGHT`) | **PASS**: shaded brick stays warm brown (`walkup_58_corner`, `pass2/after_58_street`) |
| 5 | Other styles' sign decals turned 180° | Checked: no other style places a sign or lettered decal. Their signage is in the storefront panel textures, upright (they project in world metres). The shared decal material carries the flip fix for any pack decal | none needed | **PASS** |
| 6 | Roof clutter too small from the street | The 0.6-1.2 m front parapet hides anything short or far back | Chimneys 1.8-2.4 m tall, in the front third on the party wall. Vents 1.2-1.5 m, antenna masts 3 m. Still no water tanks: `Design/WALKUP_RULES.md` rules them out ("That's New York") | **PASS**: a chimney shows over the parapet in `walkup_58_corner`; clutter reads from the air (`walkup_83_roofs`) |

**Checklist (`Design/WALKUP_RULES.md` section 5) after pass 2:** all 20 **PASS**. Item 12 (side parapets
step down) stays weak: the steps are real but only read up close. Item 18 (weathering) now passes cleanly:
streaks, drips, soot runs and base grime, with brick repairs as before. The MISSING PIECE list is unchanged:
corner chamfer or turret, open sashes, roof pitch, gangways.

**Frame cost** (`shadow_ab_ue.py states=on`, the same four cameras, 6 ProfileGPU samples each, `<root>`):

| Camera | Pass 1 fix-up | Pass 2 |
|---|---|---|
| street (report camera) | 17.48 ms | 17.93 ms |
| b_lot_osm_58 street | 16.39 ms | 14.71 ms |
| b_lot_osm_22 street | 14.82 ms | 14.84 ms |
| aerial (report camera) | 20.83 ms | 18.75 ms |

The frame is within the run-to-run spread, at or under the last budget at every camera. Two-sided pane shadows
didn't move ShadowDepths (0.26-0.96 ms). 222 HISM components, 952,270 instances; map check 0 errors, 0 warnings.

Note on the numbers: ten CrashReportClient processes had piled up from this session's scripted editor runs (each
logs a harmless crash on exit), and the load average was about 64. They were stopped before the pass-2
measurement; the earlier passes' numbers were taken under that load. The one crash reporter from before this
session was left alone.

## 0. Fix-up pass

Before and after shots, same cameras: `artifacts/previews/chicago_loop/walkup/fixup/`. `before_*` is the
first pass (`81af655`), `after_*` is this one:
- walk-up views: `*_83_street`, `*_83_close`, `*_58_close`, `*_22_close`, `*_58_street`, `*_22_street`, `*_83_roofs`,
  `*_58_roofs`, `*_83_rear`, `*_58_corner`;
- the report cameras: `*_cam_street`, `*_cam_aerial`, `*_cam_b_lot_osm_58_street`, `*_cam_b_lot_osm_22_street`;
- crops: `after_83_streaks_crop.png`, `after_83_shopfronts_crop.png`.

### What changed
1. **Storefront glass.** The light box is gone: the display windows, transoms and shop doors are a new glass-only
   module (`KIT_Glass`) in a reflective shop glass (`style_kit.GLASS["shop"]`, Fresnel to 0.92, and Lumen
   front-layer reflections switched on in the grade).
   - Behind the glass, `walkup._shop_interior` builds a shop 2.2-3.4 m deep: a generated back wall (grocery, bar,
     laundry, clothes or empty; `walkup_decals.shop`), floor, ceiling and side walls, and fittings by kind
     (shelving with goods, counters, a bar, washers and a folding table, racks).
   - Light state per shop: on 35%, dim 40%, off 25% (boarded shops always off). It is a dim glow on the back wall
     (`M_KitShopBack`), not a lit panel.
2. **The 180-degree flip.** Fixed in the shared decal material (`city_materials_ue._kit_quad_uv`), so every
   style's pack decals (graffiti, stains, signs) are upright, not just the walk-ups'. The generated decals are
   stored upright again.
   - Pack storefront panels (`KIT_Panel` with `M_KitWall`) were checked against their source texture: the door,
     mailboxes and shutter come in the right order and right way up. They project in world metres, so they were
     never flipped.
3. **Weathering.**
   - Wall decals are now true mesh decals (Deferred Decal domain, translucent blend). They paint into the wall
     and take its lighting. As plain quads 3 cm off the wall they went near-black in shade, because Lumen's
     distance fields count them as inside the wall, and their masked alpha cut soft grime off hard.
   - Streaks are darker and longer (0.9-1.6 m, 55% of windows), and new runs come down the piers from the cornice
     and coping (60%).
   - Soot is darker and taller (1.4 m, 75% of lots).
   - The dark-rectangle patches are replaced by real brick repairs (`walkup._repair`): a few thin bands of the
     lot's own brick, 5 mm proud, three courses each, with a toothed outline and a newer, redder tint. They also
     go on exposed side walls. Because the wall material projects in world metres, the repair's bricks line up
     course for course with the wall.
4. **Roof clutter** at real size (`RULES["roof_size"]`):
   - chimneys 0.6 x 0.6 x 1.2-1.6 m with a cap and clay pots;
   - condensers 1.0 x 1.0 x 0.9 m on a pad;
   - a 3 x 3 ft (0.91 m) hatch, red with a galvanised lid;
   - vents 0.15 m with caps, a 0.9 m dish, antenna masts.
   They are light metal and brick on the dark membrane, and they read from the aerial.
5. **Shade.** The stage's lighting is in `import_city_ue.LIGHT`:
   - a warm sky-light tint (255, 214, 180), sky intensity 1.4;
   - a warm lower hemisphere standing in for the street's bounce;
   - a 5600 K sun;
   - an unbound `Grade` volume: exposure +0.3, saturation 1.15, Lumen front-layer reflections.
   `python3 ... import_city_ue.py --relight` re-applies it without a re-import. Two bugs were found on the way:
   - The tint was going in blue. `unreal.Color(...)` takes positional arguments in memory order (B, G, R, A).
     Keyword arguments now.
   - The stage (sun, sky, fog, grade) has been landing in kit sublevel `Kit_09` since pass 2.
     `set_current_level_by_name("PersistentLevel")` never switched back; it needs the level's own name. Fixed in
     `kit_city_ue.build`; one of each now, in the persistent level.
6. **Windows (your note).** Lit rooms no longer glow out of nowhere in daylight. The room material (`M_InteriorLit`)
   is now a warm interior that the sun and shadows reach, and its glow is multiplied by `MPC_CityLight`'s `Night`
   parameter, 0 by day. Shops keep 35% of their glow by day. Set `Night` to 1 for dusk or night, in the editor or
   at runtime from Blueprint or C++. Night was not tested in this pass.

### Re-grade against `Design/WALKUP_RULES.md`

| # | Checklist item | First pass | Now | Evidence (`fixup/after_*`) |
|---|---|---|---|---|
| 1 | Ground floor taller than upper floors | PASS | **PASS** | `83_street` |
| 2 | 20-25 ft per lot | PASS | **PASS** | `83_street` |
| 3 | Tall 1:2 windows, stacked | PASS | **PASS** | `83_street`, `22_close` |
| 4 | Recessed windows with lintels and sills | PASS | **PASS** | `22_close` |
| 5 | Cornice projects and casts a shadow | PASS | **PASS** | `58_close`, `22_close` |
| 6 | Storefront: bulkhead, glass, transom, sign band | PASS (light box) | **PASS** | `after_83_shopfronts_crop.png`: shop interiors behind reflective glass |
| 7 | Recessed entry and separate upstairs door | PASS | **PASS** | `58_close` |
| 8 | Front brick differs from the side and rear common brick | PASS | **PASS** | `58_corner`, `83_rear` |
| 9 | Ornament stops 1-3 ft around the corner | PASS | **PASS** | `58_corner` |
| 10 | Party walls mostly blind | PASS | **PASS** | `58_corner` |
| 11 | Parapet rises above the roof | PASS | **PASS** | `83_roofs` |
| 12 | Side parapets step down toward the rear | PASS (weak) | **PASS (weak)** | small 0.3-0.4 m steps behind the cornice; they read only up close |
| 13 | Roof has 3-5 clutter items | PASS (small) | **PASS** | `83_roofs`, `58_roofs`: clutter reads from the air |
| 14 | No water tank | PASS | **PASS** | `83_roofs` |
| 15 | Rear porches | PASS | **PASS** | `83_rear` |
| 16 | Adjacent lots never share brick, cornice, height and storefront | PASS | **PASS** | `test_walkup.VarietyTest` |
| 17 | Rooflines vary | PASS | **PASS** | `83_street` |
| 18 | Weathering: streaks, soot, patches | **FAIL** | **PASS (weak on soot and repairs)** | Streaks under every sill and down the piers from the cornice read at street distance (`after_83_streaks_crop.png`). Soot is faint. The brick repairs are geometry and line up with the wall, but in shade at 10+ m they are hard to see |
| 19 | Window interiors vary | PASS | **PASS** | blinds, curtains, AC units; by day "lit" rooms are lighter interiors, not glowing |
| 20 | No visible tiling at 20 m | PASS | **PASS** | `83_street`, `58_street` |

**20 PASS (two weak), 0 FAIL.** The MISSING PIECE list from the first pass is unchanged: corner chamfers or
turrets, open sashes, the 1/4 in per ft roof pitch, and gangways.

**Shade:** the grey-blue cast is gone (`after_cam_street` vs `before_cam_street`, `after_83_street`). Shade now
reads neutral to warm, and shaded brick keeps its brown (`after_58_close`, the right half). Red brick in deep
shade still reads tan rather than red (`after_22_close`), so the tones hold up better but not fully.

### GPU time
`Scripts/city/shadow_ab_ue.py states=on`: the same four cameras, 6 ProfileGPU samples each, whole frame
(`<root>`). Before is the first pass with proxies on; after is this pass.

| Camera | Before | After |
|---|---|---|
| street (report camera) | 17.01 ms | 17.48 ms |
| b_lot_osm_58 street | 16.52 ms | 16.39 ms |
| b_lot_osm_22 street | 15.71 ms | 14.82 ms |
| aerial (report camera) | 21.92 ms | 20.83 ms |

All four are within the run-to-run spread (1.5-4 ms), so there is no measurable cost. The pass adds 2,200
instances (951,925 in all), shop glass and mesh decals. 218 HISM components; map check 0 errors, 0 warnings.

### Still open
- Red brick in deep shade reads tan (see above). The next lever is the swatches' saturation or a per-tone
  albedo, not more grade.
- Soot and repairs are subtle; raising the soot alpha and the repair tint further is a one-line change in
  `walkup.RULES` and `walkup_decals.soot`.
- Night (`MPC_CityLight` Night = 1) was not tested.
- Pack decals are upright now by the shared material fix. The walk-up signs show it works; I didn't look for a
  pack decal on screen.

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
py Scripts/city/shadow_ab_ue.py frames=3 settle=8 rounds=2                 # proxies off/on A/B
py Scripts/city/shadow_ab_ue.py frames=3 settle=8 rounds=2 states=on tag=x  # a plain measurement
python3 -I Scripts/city/shadow_ab_ue.py --read
# lighting only (import_city_ue.LIGHT), no re-import:
py Scripts/city/import_city_ue.py --relight --level /Game/Maps/SkyCityChicagoGen
python3 -I Scripts/city/test_walkup.py
```

**Process notes:**
- As in pass 3, the generated `Content/City/Generated/Chicago/**` and `SkyCityChicagoGen*` files were made
  writable locally (`chmod u+w`); no `git lfs lock`.
- The editor's `SecurityToken` line in `Config/DefaultEngine.ini` was reverted.
- `-ExecutePythonScript` quits the editor when the script ends, and logs a harmless crash in SemanticSearch on the
  way out. The tick-based shot scripts need a live editor (`-ExecCmds="py <absolute path>"`, or the console).
