# Building-type handoff: the shared Chicago kit pipeline

For the sessions that build the next building types (condos, towers, industrial, ...) on the generated
Chicago map. Start from tag **`walkup-signoff`** on branch `cursor/chicago-gen-map`:

```bash
git fetch --tags && git checkout -b <type>-pass walkup-signoff
```

The walk-up type (brick storefront walk-ups) is the worked example: `Scripts/city/walkup.py`, its rules
`Design/WALKUP_RULES.md`, its report `WALKUP_REPORT.md`. Open items from the sign-off are in
`Design/BUILDER_BACKLOG.md`: the DELI lot with no shop interior, red brick reading tan, the weak parapet steps,
and the store-naming system. Grade every type against `Design/handoff/CHECKLIST.md`.

Read `AGENTS.md`, `CLAUDE.md` and `CLAUDE.local.md` first. Commit locally; Kenny pushes. Never touch
`Content/Building`, `Prop`, `Material`, `Megascans`, `Vehicles`, `Plugins/CitySamplePCG` or `SkyCityMashup`.

## 1. What the pipeline does, and where

```
generate_city.py ──> city model (buildings, facades, rooms)          plain Python
kit_layout.py ─────> Saved/CityGen/kit_layout_chicago_loop.json      plain Python
   ├─ style_kit.py   per-style numbers, families, colours (FRAMES, TRIMS, GLASS, PANE_LOOKS)
   └─ walkup.py      the walk-up type: lots, storefronts, wear, roofs (one type = one module like this)
brick_swatches.py, walkup_decals.py, kit_swatches.py ─> SourceArt/CityGen/kit/{swatches,decals}
blender_facade_kit.py ─> SourceArt/CityGen/kit/KIT_*.glb             headless Blender
import_city_ue.py ─> the level /Game/Maps/SkyCityChicagoGen          in the editor
   ├─ city_materials_ue.py   every material (walls, flats, glass, decals, shops, MPC)
   └─ kit_city_ue.py         HISM components in 10 sublevels; collision, shadow proxies
```

- **Layout contract.** Everything is a kit module (1 m unit, local +Y into the building), placed as
  `[x, y, z, yaw, sx, sy, sz]` (+ `r, g, b` tint) in groups named `"<module>|<material>"`. The material kinds
  are `set:` (wall swatch, tinted), `trim:` / `frame:` (flats), `lit:` / `dark:` (panes), `shopglass:`,
  `shopback:`, `decal:` (pack), `gdecal:` (generated). The module list is `kit_layout.MODULES`;
  `blender_facade_kit.py` refuses to export if the two disagree.
- **New building type:** write a module like `walkup.py`. It plans lots and looks from the city model and
  emits instances through an `Emit` helper (`put(key, face, s0, s1, d0, d1, z0, z1, tint)` in the lot's
  s/d/z frame). Hook it into `kit_layout.build_layout` the way `walkup.is_walkup` / `layout_buildings` are.
  Put every number in a `RULES` table and give it a `test_<type>.py`.
- **Lighting table and `--relight`.** `import_city_ue.LIGHT` holds the sun temperature, sky intensity and colour,
  lower hemisphere, Lumen indirect, exposure, white balance, skylight leaking and saturation.
  - `_stage` spawns the Sun, SkyLight, SkyAtmosphere, HeightFog and an unbound PostProcessVolume `Grade`.
    `relight()` applies `LIGHT` to them.
  - To change lighting without a re-import, edit `LIGHT`, then:
    `py Scripts/city/import_city_ue.py --relight --level /Game/Maps/SkyCityChicagoGen`. It replaces the three
    lit actors with fresh ones and saves every dirty level.
- **Shadow-only proxy boxes.** Glass casts no shadow, so each building tier and walk-up lot gets a hidden box,
  group `KIT_Wall|shadow` (`kit_layout.SHADOW`). In Unreal it is not visible, hidden in game, casts a hidden
  shadow and has no collision (`kit_city_ue`, component tag `kit_shadow`).
  - Insets: `kit_layout.SHADOW_INSET` = 0.45 m behind tower panes. `walkup.RULES["shadow_inset"]` = 0.85 m behind
    the walk-ups' recessed panes, and only at a row's ends, never between lots.
  - Pane components cast two-sided. Otherwise sun through corner windows leaks onto the facades across the
    street (traced in `WALKUP_REPORT.md` section 00).
  - A new type with deeper windows needs its own inset just behind its pane backs.
- **Decal material.** `city_materials_ue._decal_master`:
  - `M_KitDecal` is a deferred mesh decal, translucent blend. It paints into the wall behind it and takes the
    wall's own lighting. Plain quads 3 cm off a wall go near-black in shade under Lumen.
  - `M_KitDecalSolid` is a masked surface, for things hanging in front of glass (`SOLID_DECALS`: gates,
    plywood).
  - Both use `_kit_quad_uv`: the kit quads show their mesh UVs turned 180°, so the U flip lives there. Store
    decal images upright.
  - The pack splat decals (stain, patch, paint) are excluded city-wide (`style_kit.WALL_DECALS`). Styled walls
    get `kit_layout.STREAK_DECALS` instead.
- **Shop interiors.** In `walkup._storefront` and `_shop_interior`:
  - `KIT_Glass` (glass only) in the shop glass: `style_kit.GLASS["shop"]` with `GLASS_SURFACE` roughness 0.1.
  - Behind it, a shop 2.2-3.4 m deep: back wall `KIT_Panel|shopback:<kind>.<state>` on `M_KitShopBack`, with
    images from `walkup_decals.shop`; floor, ceiling, side walls and fittings.
  - Light states are on, dim or off (`city_materials_ue.SHOP_GLOW`).
  - Keep shop trim matte and mid-dark. Light or metallic undersides mirror the sunlit street from below and read
    as white slabs.
- **`MPC_CityLight` and `Night`.** `city_materials_ue.light_collection` makes
  `/Game/City/Generated/Chicago/Materials/MPC_CityLight` with the scalar `Night` (0 by day).
  - Room glow (`M_InteriorLit`) is multiplied by `Night`. By day a "lit" room is only a lighter interior that sun
    and shadow reach.
  - Shops keep `SHOP_DAY_GLOW` (35%) of their glow by day.
  - For dusk, set `Night` to 1 (Set Scalar Parameter Value on the collection). Not yet tested at night.
- **`import_city_ue.py`.**
  - Opens the level and clears the previous run's outliner folder.
  - Builds the city materials, then the kit materials (`kit_style_materials`), then the HISMs in sublevels
    `<level>_Kit/<level>_Kit_NN` (`kit_city_ue.build`).
  - Returns to the persistent level, stages the lighting, adds the PlayerStart and saves.
  - It refuses to write `SkyCityMashup`, and stops early if the outputs are read-only (LFS).

## 2. Commands

All from the project folder. The editor binary is
`"/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"`
(below: `$UE`).

**Build the data and art (plain Python and Blender):**
```bash
python3 -I Scripts/city/brick_swatches.py            # brick + roof swatches, merged into swatches.json
python3 -I Scripts/city/walkup_decals.py             # streaks, soot, drips, grime, ghost/shop signs, gates, shops
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 \
  -P Scripts/city/blender_facade_kit.py              # the KIT_*.glb modules
python3 -I Scripts/city/kit_layout.py --region chicago_loop
```

**Import into the level.** The generated files are LFS-lockable and read-only: `chmod u+w` them locally, or
`git lfs lock` them if anyone else works on them.
```bash
chmod -R u+w Content/City/Generated/Chicago Content/Maps/SkyCityChicagoGen*
# a startup script that calls import_city_ue.main([...]); the editor quits when it ends:
$UE "$PWD/SkyCity.uproject" /Engine/Maps/Entry -ExecutePythonScript="$PWD/<your_script>.py"
#   where the script does:
#   import_city_ue.main(["--glbs", "SourceArt/CityGen/chicago", "--buildings", "kit",
#                        "--level", "/Game/Maps/SkyCityChicagoGen",
#                        "--spawn", "Saved/CityGen/sky_city_spawn_chicago_loop.json"])
# or, in a live editor's console:
py Scripts/city/import_city_ue.py --glbs SourceArt/CityGen/chicago --buildings kit \
  --level /Game/Maps/SkyCityChicagoGen --spawn Saved/CityGen/sky_city_spawn_chicago_loop.json
```
A full import takes about 6-7 minutes. Then check the log
(`~/Library/Logs/Unreal Engine/SkyCityEditor/SkyCity.log`) for:
- `MapCheck: Map check complete: 0 Error(s), 0 Warning(s)`;
- `CITYGEN kit buildings ...` (at sign-off: 354 buildings, 10 sublevels, 222 components, 952,270 instances);
- no `Failed to compile` after the rebuild started.

**Tests (plain Python):**
```bash
for t in test_walkup test_generate_city test_city test_packs; do python3 -I Scripts/city/$t.py; done
python3 -I Scripts/roads/test_profiles.py
```

**Rerun check (generators are deterministic; expect `RERUN SAME`):**
```bash
md5 -q Saved/CityGen/kit_layout_chicago_loop.json > /tmp/h1
find SourceArt/CityGen/kit/decals SourceArt/CityGen/kit/swatches -type f -exec md5 -q {} \; | sort | md5 -q >> /tmp/h1
python3 -I Scripts/city/kit_layout.py --region chicago_loop >/dev/null
python3 -I Scripts/city/walkup_decals.py >/dev/null; python3 -I Scripts/city/brick_swatches.py >/dev/null
md5 -q Saved/CityGen/kit_layout_chicago_loop.json > /tmp/h2
find SourceArt/CityGen/kit/decals SourceArt/CityGen/kit/swatches -type f -exec md5 -q {} \; | sort | md5 -q >> /tmp/h2
diff /tmp/h1 /tmp/h2 && echo RERUN SAME
```

**Review shots** (the live editor with its MCP server and the level open):
```bash
$UE "$PWD/SkyCity.uproject" /Game/Maps/SkyCityChicagoGen -ModelContextProtocolStartServer &
python3 -I Scripts/city/walkup_shots_ue.py --plan --ids b_lot_osm_83,b_lot_osm_58,b_lot_osm_22
python3 -I Scripts/city/mcp_capture.py --tag after          # Saved/CityGen/shots/after_<pose>.png
```
`walkup_shots_ue.py --plan` gives five poses per row: street, close, corner, roofs, rear. A new type should
plan its own rows the same way. Copy the shots you grade, as JPEGs, to `artifacts/previews/chicago_loop/<type>/`.

## 3. GPU measurement

`Scripts/city/shadow_ab_ue.py`:
- **Cameras** (Unreal cm, degrees):
  - `aerial` (-175000, -80000, 55000), pitch -24, yaw 30;
  - `street` (-84000, -23500, 250), pitch 2, yaw 60. These are the `CHICAGO_REPORT.md` cameras.
  - Plus `b_lot_osm_58_street` and `b_lot_osm_22_street` from `Saved/CityGen/walkup_shots.json`.
- **Method:** each camera waits `settle` seconds, then takes `frames` ProfileGPU dumps and reads the `<root>`
  and `ShadowDepths` inclusive times, `rounds` times over.
- **Run it** at editor launch. It ticks over many frames, so it can't use `-ExecutePythonScript`:
  ```bash
  $UE "$PWD/SkyCity.uproject" /Game/Maps/SkyCityChicagoGen -ModelContextProtocolStartServer \
    -ExecCmds="py $PWD/Scripts/city/shadow_ab_ue.py frames=3 settle=8 rounds=2 states=on tag=mytype"
  # wait for Saved/CityGen/shots/shadow_ab.json to say "done", then:
  python3 -I Scripts/city/shadow_ab_ue.py --read
  ```
- **Options:** `states=off` measures the proxies switched off, for an A/B. Never write `states=off,on`:
  `-ExecCmds` splits on commas. Run each state separately.
- **Sign-off numbers** (`states=on`, the reference for "under budget"): street 17.93 ms, b_lot_osm_58_street
  14.71 ms, b_lot_osm_22_street 14.84 ms, aerial 18.75 ms. Run-to-run spread is about 1.5-4 ms.
- **Before measuring,** check `uptime`. Stale CrashReportClient processes (see the pitfalls) can pile up and
  load the machine.

## 4. Known pitfalls

- **`unreal.Color` is B, G, R, A when positional.** `unreal.Color(255, 204, 164)` is blue. Always use keywords:
  `unreal.Color(r=255, g=204, b=164, a=255)`. (`unreal.LinearColor` is r, g, b, a.)
- **Lighting lives in the persistent level, never a sublevel.**
  - `kit_city_ue.build` makes each kit sublevel current while it fills it. It must switch back with
    `set_current_level_by_name(<level name>)`: `"PersistentLevel"` silently does nothing.
  - Until sign-off, the stage's sun, sky and fog were saved into `SkyCityChicagoGen_Kit_09`.
  - After any change to staging, list the lights per level (label, class, `get_level()`) and expect exactly
    one Sun, SkyLight, SkyAtmosphere, HeightFog and Grade, all in `SkyCityChicagoGen:PersistentLevel`.
  - Two directional lights show an on-screen "Multiple directional lights are competing" warning.
- **Setting properties from Python doesn't dirty the level.** `save_current_level` then skips it. That's why
  `--relight` respawns actors. Read values back in a fresh process before trusting a change, and write any probe
  output to a new file name so a stale file can't fool you.
- **`.uasset` / `.umap` never merge.** They are binary and LFS-lockable. Never resolve a conflict in them;
  regenerate them by import from the scripts. One session imports at a time; lock or coordinate before editing
  any committed asset. Commit the scripts with the regenerated assets in the same commit.
- **The editor edits `Config/DefaultEngine.ini`** (a `SecurityToken` line). Revert it before committing
  (`git checkout Config/DefaultEngine.ini`). Never print it.
- **`-ExecutePythonScript` quits the editor when the script ends** and logs a harmless SemanticSearch crash on
  the way out. Each one leaves a CrashReportClient spinning at 100% CPU. Stop the ones your runs started
  (`ps -Ao pid,lstart,comm | grep CrashReportClient`); leave older ones alone.
- **Relative paths in `-ExecCmds="py ..."`** resolve from the engine's Binaries folder. Use absolute paths.
- **Materials on HISMs need `used_with_instanced_static_meshes`** set when they are built (`_flat`, `_glass`,
  `_emissive` do). Otherwise MapCheck warns, and a cooked build draws the default material.
- **Translucent glass and light trim seen from below** mirror the sunlit street. Keep shop and soffit trim matte
  and mid-dark, and keep the glass Fresnel low (`GLASS["shop"]`).
- **Thin quads near walls under Lumen** go dark in shade. Use mesh decals (`M_KitDecal`) for anything painted
  on a wall.
- **`MaterialExpressionDitherTemporalAA` doesn't exist** in Python; it's a material function. Mesh decals made
  it unnecessary.
- **Lumen front-layer reflections** are set on the Grade volume. Shop glass needs per-pixel translucent lighting
  (`_glass` sets it).
- **The ground floor and the wear rules are per type, the checklist is shared**
  (`Design/handoff/CHECKLIST.md`). No real brand names in any sign, decal or file name (AGENTS.md).
