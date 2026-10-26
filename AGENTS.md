# AGENTS.md: Sky City, for your AI assistant

Hand this file to your AI coding assistant (Claude Code, Codex, Cursor or any other) before it touches the repo. The person you work for should skim it too.

## City Generator

Read these before changing the city generator.

- [`docs/CITY_GENERATOR_VISION.md`](docs/CITY_GENERATOR_VISION.md) is the **stable contract**: layers, invariants, placement rules, and the build path. Change it only when the owner changes the vision.
- [`docs/CITY_GENERATOR_STATE.md`](docs/CITY_GENERATOR_STATE.md) is the **living gaps** record: current state per layer, ranked gaps, and where the build path stands. Update it when a milestone merges.

**City Shape** (in the building-types repo) is the master spine. The OSM importer that writes a City Shape document lives in building-types. This repo consumes that export: `python3 -I Scripts/city/cityshape.py <file>` (see [`docs/CITY_SHAPE_CONSUME.md`](docs/CITY_SHAPE_CONSUME.md)).

## What Sky City is

An open-world driving and flying game in **Unreal Engine 5.8** for **Apple Silicon Macs**. The Chicago Loop and lakefront are stitched to downtown Austin (about 3.6 x 3.6 km, streets generated from OpenStreetMap), with a Texas rocket test site ("McGregor") on the side. You drive, boost, wall-ride and fly the **Skyster Roadster**, whose physics are ported from Kenny's browser game Skyster. Early and playable. Free: https://kornontheken.itch.io/sky-city. Repo: https://github.com/kennyhassmusic/sky-city. Owner: Kenny Hass Music LLC (Kenny Hass reviews everything).

Maps (`Content/Maps`): `SkyCityMashup` is the city and the default; `McGregor` and `McGregorNight` are the test site; there is also an older `SkyCity` map.

## Rules for you, the AI

- Work in the contributor's fork, on a branch, in **small focused pull requests**. Never push to `main`.
- Read the header comment of every file you change. Most files start with a comment that says what the file is for and why.
- Do not touch anything in "What not to touch" below. If the job needs it, stop and tell the person.
- Never add third-party assets, City Sample content, or real brand names and logos. The game's car brand is the invented **Volta Motors**.
- Do not sign the CLA for the person. They reply to the bot themselves.
- Do not commit generated files, secrets or tokens. Say in the PR what you changed, why, how you tested it, and that an AI helped.
- Prefer scripts and data (Python generators, PCG, splines, EditAnywhere properties) to hand-placing hundreds of actors.

## Licences and the CLA, in short

| What | Licence |
|---|---|
| Code | PolyForm Noncommercial 1.0.0 (`LICENSE`) |
| Original art and models | CC BY-NC 4.0 (`LICENSE-ASSETS.md`) |
| Street data from OpenStreetMap | ODbL, (c) OpenStreetMap contributors |
| Names "Sky City" and "Skyster", their logos, the Roadster design | All rights reserved |
| Third-party content | Its own licence, listed in `CREDITS_AND_LICENCES.txt` |

Anyone may play, mod, share and stream Sky City (monetized videos too). Only Kenny Hass Music LLC may sell it.

**CLA** (`CLA.md`): you keep your copyright and license your work to Kenny Hass Music LLC, including for sold versions. Sign **once, in your first PR**: the bot asks, and the person replies `I have read the CLA Document and I hereby sign the CLA`. **Every change is reviewed by Kenny** (code owner of everything; squash and merge).

## Setup (Apple Silicon Mac only)

1. **Unreal Engine 5.8** from the Epic Games Launcher (built and tested with 5.8.3).
2. **Xcode 26** (tested with 26.5). If the editor quits with "missing Metal Toolchain": `xcodebuild -downloadComponent MetalToolchain` (again after Xcode updates).
3. **Git and Git LFS**, then `git lfs install` **before** cloning:
   ```bash
   git lfs install
   git clone https://github.com/kennyhassmusic/sky-city.git
   cd sky-city
   ```
   The art (about 2 GB, every `.uasset`, `.umap`, model, image and sound) downloads from Sky City's own server on Cloudflare R2, set in `.lfsconfig`. Nothing to configure. If a clone stops half way, `git lfs pull` finishes it.
4. **Epic's City Sample** (the buildings): free on Fab, not allowed in this repo. Follow `docs/SETUP_CITY_SAMPLE.md`. Without its `CitySamplePCG` plugin the editor reports a missing plugin.
5. Open `SkyCity.uproject`. The first launch compiles the C++ module.

**The Art Pack is not needed for contributing.** It is a separate itch.io download for people who reuse Kenny's art in other projects (see `docs/ART_PACK.md`). You get the same art from `git clone`.

Sending **art** in a PR (code-only PRs skip this): LFS downloads come from the read-only server, so upload to your fork once per clone:
`git config lfs.pushurl https://github.com/YOUR-GITHUB-NAME/sky-city.git/info/lfs`.

## Folder map

**`Source/SkyCity`** (C++ module `SkyCity`; read the header of each file first):

| Files | What they do |
|---|---|
| `SkysterCar.*` | `ASkysterCar`, the Roadster pawn: the car physics from Skyster 4.0 (grip tyres, flight, hover, wall riding, boost, damage, chargers, fuel add-ons, levels) |
| `SkysterTypes.*`, `SkysterProgress.*` | shared types and handling numbers; the six car levels and the "Skyster" save slot |
| `SkysterPickups.*`, `SkysterFX.*` | pressure points, chargers and add-ons found by actor tag; the soft particle pools |
| `SkysterHUD.*` | the canvas HUD and the Garage menu |
| `SkysterTraffic.*`, `SkysterFleet.h` | city traffic on the street network in `Content/SkyCity/Data/traffic.json`; the drivable line-up table and the rule for blocky stand-in cars |
| `SkysterShowLights.*`, `SkysterEngineTests.*` | McGregor's show lights and timed engine tests |
| `SkyCourse*.cpp/.h` | the **Course Builder** (in progress): `SkyCourse.h` is the contract; Model (course file and bake), Track (meshes), Race/RaceImpl/AI, Mode (director), Builder/BuilderImpl/BuilderHud (editor UI), Geom, Mcp (local MCP server on 127.0.0.1:47800). Design: `Design/CourseBuilder.md` |
| `SkyCity.Build.cs`, `*.Target.cs` | build rules (Kenny reviews changes) |

**`Scripts/`**: generators for most of the world. Three ways to run them:
- **In the editor** (names ending `_ue.py`, `Scripts/unreal/`, a few top-level files): Output Log / Python console, `py Scripts/roads/build_roads_ue.py`. Many take stage names; results go to `Saved/MCPScripts/`.
- **In headless Blender** (`blender_*.py`, they write `.glb` into `SourceArt/`): `/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P Scripts/landmarks/blender_landmarks.py`.
- **Plain Python 3** (offline data and layout steps): `python3 -I Scripts/mashup/build_mashup_data.py`. The texture scripts also need Pillow, NumPy and SciPy.

They find the project folder themselves; set `SKYCITY_ROOT` to override. They are meant to be re-runnable. Flow: `SourceArt/osm` and `Scripts/mashup`, `streets`, `roads` produce JSON in `Saved/`, and the `*_ue.py` scripts build from it in the editor. Folders: `mashup` (city plan), `streets`, `roads`, `rail` (the elevated L), `landmarks`, `mcgregor`, `vehicles` (stand-in cars, line-up; see `Scripts/vehicles/PLACEHOLDERS.md`), `hud`, `unreal` (game setup, FX, pickups), `course` (Course Builder tests), `build` (Kenny's release scripts). The data is already in the repo; you only rerun a script to change what it makes.

**`Content/`**: `City/` (everything generated for the streets and landmarks: AustinSights, Capitol, Expressway, Landmarks, Parks, Rail, Roads, Street, Water, Willis; `Meshes` is old greybox), `McGregor/`, `SkyCity/` (Blueprints, Data, FX, HUD, PCG, Pickups), `Vehicles/` (Placeholder stand-ins, Shared materials, the Roadster), `Maps/`, `Blockout/` (old greybox), `__ExternalActors__` and `__ExternalObjects__` (the maps' per-actor files; the editor writes them, never edit by hand). **Not in the repo** (git-ignored): City Sample's `Building`, `Prop`, `Material`, `Megascans`, `MSPresets`, `Textures`, `Environment`, and `Plugins/CitySamplePCG`.

**`SourceArt/`**: the Blender-made `.glb` models and PNG/WAV sources (`Landmarks`, `Expressway`, `Rail`, `RoadKit`, `StreetKit`, `McGregor`, `Pickups`, `FX`, `HUD`, `Vehicles/Placeholder`), OpenStreetMap extracts in `osm`, downloaded CC0 sources in `CC0`, `Brand/Volta`, and the Roadster (`roadster_master.glb`, `RoadsterRig`; reserved).

**`Saved/`**: git-ignored except the small generated inputs the scripts read: `Mashup`, `Roads`, `Streets`, `McGregor` (JSON and `terrain_*.f32`), `Expressway`, `Rail`. They change only when you rerun a generator.

**Elsewhere:** `Design/` (ROADMAP, Course Builder design, ideas), `docs/` (setup and maintainer notes), `Config/` (Kenny reviews it), `.github/` (PR template, workflows, CODEOWNERS), `tools/` (maintainer tools, not for contributors).

## Naming and style, as in the code

- **C++:** Epic's C++ standard; **tabs**; types `ASkysterCar`, `USkysterSave`, `FSkyProgress`; the `Sky` / `Skyster` / `SkyCourse` prefixes; `SKYCITY_API`; `TEXT("...")`. Comment the *why*; every file opens with a comment on what it is for. Numbers live in `EditAnywhere` properties or data, not magic constants. Mind the frames: the car sim is metres, x forward, y left, z up; Unreal is centimetres, y right (convert with `ToUE` / `FromUE`).
- **Python:** 4 spaces, PEP 8 in spirit, a docstring on top that says what the script does and **how to run it**, `SKYCITY_ROOT`, safe to rerun, no secrets, standard library where you can.
- **Assets:** prefixes `SM_` mesh, `M_` material, `MI_` material instance, `T_` texture, `BP_` Blueprint, `S_` sound; area prefixes `LM_` landmarks, `PK_` parks, `CW_` water, `L_` the L, `SK_` street kit, `MG_`/`SK_`/`UV_` McGregor, `TV_` vehicle parts. glTF imports land as `<Asset>/StaticMeshes|Materials|Textures`. Blender material slots are `M_*` and Unreal maps them to `MI_*`.
- **Brands:** no real brand names or logos in code, assets, file names or on-screen text. A few old folders still carry real car names (`Model3`, `Cybertruck`, ...); they are being replaced by Volta Motors. Do not add more, and do not rename them unless asked.
- Line endings are LF (`.gitattributes`). Keep PRs free of editor noise: the editor re-adds a `SecurityToken` line to `Config/DefaultEngine.ini`; do not commit that.

## Build, run and test

- **Open:** double-click `SkyCity.uproject`, or `./launch.sh` (also starts the editor's MCP server; `UE58=/path/to/UE_5.8` if the engine is not in `/Users/Shared/Epic Games`).
- **Compile from the command line** (close the editor first):
  ```bash
  "/Users/Shared/Epic Games/UE_5.8/Engine/Build/BatchFiles/Mac/Build.sh" SkyCityEditor Mac Development -project="$PWD/SkyCity.uproject" -WaitMutex
  ```
- **Unsigned Mac build** (a local test build, not a release):
  ```bash
  "/Users/Shared/Epic Games/UE_5.8/Engine/Build/BatchFiles/RunUAT.sh" BuildCookRun -project="$PWD/SkyCity.uproject" \
    -noP4 -platform=Mac -clientconfig=Development -build -cook -stage -pak -compressed \
    -map=/Game/Maps/SkyCityMashup+/Game/Maps/McGregor+/Game/Maps/McGregorNight \
    -archive -archivedirectory="$HOME/SkyCityBuild" -utf8output -unattended
  ```
  The `.app` ends up in `~/SkyCityBuild/Mac/`. It takes a while and a lot of disk. Signing and releases are Kenny's job; do not add them to a PR.
- **AI route into the editor (MCP):** `./launch.sh` starts Epic's built-in MCP server at `http://127.0.0.1:8000/mcp` (the repo's `.mcp.json` names it `unreal-mcp`). It runs in tool-search mode: `list_toolsets`, `describe_toolset`, `call_tool` (the tool's inputs go in `arguments`). **One call at a time**: the server runs on the editor's game thread. Look before and after every change (viewport capture), keep the level saved, and if a tool is missing run the console command `ModelContextProtocol.RefreshTools`. The plugin is experimental. Editor logs on macOS: `~/Library/Logs/Unreal Engine/SkyCityEditor/SkyCity.log`. A connected Xbox controller can nudge the editor camera; that is not the MCP.
- **Test:** there is no automated suite yet. Before a PR: it compiles; `SkyCityMashup`, `McGregor` and `McGregorNight` load with no new errors in the Output Log; you drove or flew to what you changed in PIE; scripts run twice with the same result. For the Course Builder, `Scripts/course/` has editor tests and `mcp_smoke_test.py` (needs the game running with the LLM link on; see `docs/COURSE_MCP.md`). Add screenshots to the PR for anything visual.
- **Binary files:** `.uasset` and `.umap` cannot be merged. `git lfs lock <path>` before you edit one, `git lfs unlock <path>` when done (`git lfs locks` lists them). From a fork, say in the issue which assets you will touch so a maintainer can hold the lock.

## Workflow

Fork, then a branch (`feature/...`, `fix/...`, `asset/...`, `docs/...`, `tools/...`), then a small PR. For anything bigger than a small fix, open or comment on an issue first. Ideas go in GitHub Discussions. Checks that must pass: `pr-guard` (no binaries or archives outside `Content/` and `SourceArt/`, nothing that runs by itself, nothing in sensitive files without Kenny's `maintainer-approved` label) and the CLA. Fill in `.github/pull_request_template.md`:

- [ ] The project compiles and the affected map(s) load without errors
- [ ] I have signed the CLA (the bot asks on the first PR)
- [ ] I unlocked any `.uasset` / `.umap` files I locked (or will once this merges)
- [ ] No generated files (`Binaries/`, `Intermediate/`, `Saved/`, `DerivedDataCache/`)

If the PR adds or changes art, it also ticks:

- [ ] No third-party assets (everything is my own work under the CLA), **or** every third-party asset is CC0 or CC BY with credit (never NC, ND, editorial-only or a store licence)
- [ ] Each third-party asset is in `CREDITS_AND_LICENCES.txt` with author, source link and licence
- [ ] No real brand names, logos or badges anywhere, also in file names
- [ ] Nothing from Epic City Sample or Unreal Engine itself

Also fill in "What this changes" (link the issue, `Closes #123`), "How to test it" and screenshots.

## What not to touch

These need Kenny's approval and often the `maintainer-approved` label. Do not edit them in a normal PR:

- Licences and policy: `LICENSE`, `LICENSE-ASSETS.md`, `CLA.md`, `SECURITY.md`, `GOVERNANCE.md`, `CREDITS_AND_LICENCES.txt` (only add rows for assets you add, and say so in the PR)
- `.github/` (workflows, CODEOWNERS, templates), `.gitattributes`, `.gitignore`
- `Config/`, above all the signing settings (`CodeSigningTeam`, `CodeSigningPrefix`), and `SkyCity.uproject`, `Plugins/`, `*.Build.cs`, `*.Target.cs`, `launch.sh`
- `Scripts/build/` (including `sign_and_notarize.sh`), `tools/` and `.lfsconfig`
- Anything the editor runs by itself: `init_unreal.py`, `Content/Python/`, startup editor-utility assets
- Third-party assets, and the reserved Roadster files, the Volta logo and the Sky City / Skyster names
- New dependencies or downloaded tools. Propose them in an issue first.

## Priorities (`Design/ROADMAP.md`; Kenny decides the order)

1. **Now:** open source (this repo, the CLA check, code-owner review).
2. **In progress:** the **Course Builder**, a Hot Wheels-style track builder and race mode on the McGregor map, and its **MCP link**: a local server in the game (`127.0.0.1:47800`, off by default) so a player's own AI can build courses while they watch. Design in `Design/CourseBuilder.md`, player docs in `docs/COURSE_MCP.md`.
3. **Then:** the Volta Motors rebrand (real car names out of asset and script names), and the **Car Designer** (paint a car; import a GLB car your AI made, drive it with the Skyster physics).
4. **Later:** story, easter eggs, achievements, races, a Windows build.

## Good first issues (ideas to turn into GitHub issues)

1. **Write `Scripts/README.md`.** A map of the `Scripts/` folders: what each script does, how it runs (editor, Blender or plain Python), what it reads and writes, and a safe order. The docstrings already say most of it. Docs only; no Unreal needed.
2. **Add a troubleshooting section to `docs/SETUP_CITY_SAMPLE.md`.** The errors a new contributor really hits: the missing `CitySamplePCG` plugin, grey boxes, "missing Metal Toolchain", LFS pointer files. Copy the exact messages while you set up.
3. **Round the stand-in cars.** `Scripts/vehicles/PLACEHOLDERS.md` says "rounder shapes can come later". In `blender_placeholder_cars.py`, soften the boxy bodies within 300 to 500 triangles each, keep the sizes and wheel pivots in the table, and run `placeholders_ue.py meshes verify` in the editor.
4. **A km/h switch for the speedometer.** `SkysterHUD.cpp` shows MPH only. Add a key that toggles km/h (display only; the physics stay as they are) and test it in PIE.
5. **One new street-kit prop.** A generic food-truck stand or bike-share dock (no brands) in `Scripts/streets/blender_street_kit.py`, imported with `import_kit_ue.py`, named `SK_...`, low-poly, with a preview render.
6. **Three sample courses** for the Course Builder, once it is merged. Add JSON files next to the ones in `Scripts/course/courses/` (a speed run, a loop-the-loop, a split with lap routing). Format in `Design/CourseBuilder.md`; check with `python3 Scripts/course/layout_check.py <file>`.
7. **Make the font path configurable in the texture scripts.** `make_sign_textures.py`, `make_road_textures.py` and `make_expressway_textures.py` hard-code macOS system fonts. Read the path from an environment variable, fall back to today's default, and fail with a clear message if the font is missing. It also helps the future Windows build.
8. **Playtest and report.** Play `McGregorNight` and the L for half an hour and file three bug reports with the *Bug report* template, each with a screenshot and your setup.
