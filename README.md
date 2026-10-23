# Sky City

An open-world driving and flying game built in Unreal Engine 5.8. The Chicago Loop and lakefront are stitched to downtown Austin, with a Texas rocket test site on the side. Drive, boost, wall-ride and fly the Skyster Roadster through all of it.

Sky City grew out of the browser game *Skyster* and is now a native Unreal Engine app. Its source is open to read, change and share for noncommercial use (it's source-available, not open source in the strict sense), and we'd love your help building it.

> **Status:** early and playable. Apple Silicon Macs only for now. Expect rough edges.

---

## Play it

Download the latest build from **[itch.io](https://kornontheken.itch.io/sky-city)**. It's free, signed and notarized.

**You need:**
- An Apple Silicon Mac (M1 or newer). UE 5.8 no longer renders on Intel Macs.
- About 6 GB of free disk space.
- An Xbox controller (recommended) or keyboard.

A Windows build is planned. If you have a Windows PC and want to help make it happen, see [Contributing](#contributing).

## What's in the game

| Part | Status |
|---|---|
| **Sky City map**: about 3.6 × 3.6 km of Chicago + Austin, streets generated from OpenStreetMap | Playable |
| **The L**: Chicago's elevated Loop, a South line, 7 stations, a drivable deck | Done |
| **Landmarks**: fountain, pier and wheel, the Texas Capitol, more on the way | Partly done |
| **McGregor maps** (day and night): the rocket test site and the Roadster reveal | Playable |
| **Traffic**: ground cars and flying cabs, with signals | Playable |
| **Game systems**: self-driving mode, mini map, chargers, pickups, 6 levels, Garage | Playable |

**Where it's heading:** a Hot Wheels-style Course Builder (with an MCP server so your LLM can build courses for you), a Car Designer, easter eggs, achievements, races, and a story in which the player makes flying cars possible. See [Design/ROADMAP.md](Design/ROADMAP.md).

---

## Build from source

### Requirements

- Apple Silicon Mac
- **Unreal Engine 5.8** from the Epic Games Launcher (built and tested with 5.8.3)
- **Xcode 26** (tested with 26.5) for compiling the C++ module. Xcode 26 installs the Metal compiler separately: `xcodebuild -downloadComponent MetalToolchain`
- **Git** and **[Git LFS](https://git-lfs.com)**
- A free **Epic Games account**, to download City Sample (see below)

### Steps

```bash
git lfs install
git clone https://github.com/kennyhassmusic/sky-city.git
cd sky-city
git lfs pull
```

The art (about 2 GB) comes from Sky City's own download server on Cloudflare, set in `.lfsconfig`, so cloning costs nobody anything and there's nothing extra to configure.

1. **Add the City Sample buildings.** They are Epic's content and can't live in this repo, but they're free on Fab. Follow [docs/SETUP_CITY_SAMPLE.md](docs/SETUP_CITY_SAMPLE.md).
2. **The generated city is already in the repo**, so there's nothing to run first. To change it, edit the generator scripts in `Scripts/` and rerun them (see `CLAUDE.md` for how the scripts are run). The city mesher is pinned to **Blender 5.2.x LTS** on **Python 3.13** (tested on 5.2.3). It prints `bpy.app.version` at startup and stops on any other series. One Blender unit is one metre, and the glTF export is 1:1. `primitive_cube_add`'s size is the full edge length (a size of 2 is a 2 m cube). Run it headless so a Python error cannot exit 0. A Python warning, a deprecated-API message, or a missing node or socket fails the build:

```bash
blender --background --factory-startup --python-exit-code 1 -P Scripts/city/blender_city.py
```
3. **Open the project**: double-click `SkyCity.uproject` and let the editor compile the C++ module. Open the `SkyCityMashup` map for the city, or `McGregor` / `McGregorNight` for the test site.

### What's in this repo, and what isn't

| In the repo | Not in the repo |
|---|---|
| All game C++ code | Unreal Engine itself (install it from Epic) |
| City generation scripts (Python and headless Blender) | City Sample buildings (download from Fab) |
| The Roadster and original landmark models | Third-party vehicle models we can't redistribute (the repo has blocky stand-ins of the same size) |
| CC0 textures and props | Packaged game builds (those go on itch.io) |
| OpenStreetMap-derived street data | |

---

## Contributing

Anyone can contribute: code, 3D models, landmarks, bug reports, playtesting. Start with **[CONTRIBUTING.md](CONTRIBUTING.md)**, then look for issues labelled **good first issue**.

**Working with an AI assistant?** Hand it **[AGENTS.md](AGENTS.md)** first: setup, the folder map, the rules and what to work on, in one file.

**Want to reuse the art in your own project?** Download the free **Sky City Art Pack** from [itch.io](https://kornontheken.itch.io/sky-city) (noncommercial use with credit; see [docs/ART_PACK.md](docs/ART_PACK.md)). You don't need it to contribute: `git clone` already gets the art.

**High-value help right now:**
- **Original vehicle models** (sedan, crossover, pickup, semi) to replace placeholder third-party models
- **Landmarks and Austin sights** built from public references
- **A Windows build**, if you have a Windows PC

How the team is organised, and how contributors become collaborators, is in [GOVERNANCE.md](GOVERNANCE.md). Please also read the [Code of Conduct](CODE_OF_CONDUCT.md).

## Licences

**Free for everyone to play, mod, share, stream (monetized videos too) and contribute to. The only thing reserved is selling the game itself: only Kenny Hass Music LLC may do that.**

| What | Licence |
|---|---|
| Code | [PolyForm Noncommercial 1.0.0](LICENSE) |
| Original art and models (except as noted below) | [CC BY-NC 4.0](LICENSE-ASSETS.md) |
| Street data derived from OpenStreetMap | [ODbL](LICENSE-ASSETS.md): © OpenStreetMap contributors |
| The Sky City and Skyster names, logos, and the Roadster design | All rights reserved: see [LICENSE-ASSETS.md](LICENSE-ASSETS.md) |
| Third-party content | Its own licence: see `CREDITS_AND_LICENCES.txt` |
| Your contributions | You keep the copyright and license them to the project under the [CLA](CLA.md) |

Sky City is built with Unreal® Engine. Unreal and its logo are Epic Games' trademarks or registered trademarks in the US and elsewhere.

## Disclaimer

Sky City features real-world cities and places as its setting. It is a fan-made game. It is not affiliated with, sponsored by, or endorsed by any company, landmark owner, artist, or government body.
