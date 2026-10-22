# The Art Pack (for maintainers)

The **Art Pack** is a zip of Kenny's own art for people who want to use it in *other* projects. It is published as a download on the itch.io page, under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) with credit. It is **never committed** to the repo (it is a zip, `pr-guard` would block it, and the art is already in the repo through Git LFS).

Two different ways to get the art, for two different people:

| Who | How | Needs the Art Pack? |
|---|---|---|
| A contributor to Sky City | `git lfs install`, then `git clone`. The art downloads from Cloudflare R2 by itself (`.lfsconfig`). Then add Epic's City Sample ([SETUP_CITY_SAMPLE.md](SETUP_CITY_SAMPLE.md)). | **No** |
| Someone reusing the art in their own game, video or render | Downloads the Art Pack from itch.io. | Yes |

Credit line the pack asks for:

> Art by Kenny Hass Music LLC, from Sky City (https://kornontheken.itch.io/sky-city)

Commercial use: "message Kenny Hass Music LLC through https://kornontheken.itch.io/sky-city". There is no email address on purpose.

## What is in the pack, and what never is

`tools/package_art.py` builds `SkyCity-Art-Pack-v<version>.zip`:

```
UE/Content/...     the drop-in folder for an Unreal 5.8 project; original paths kept
Source/...         Kenny's original GLB / PNG / WAV files from SourceArt/
LICENSE-ART.txt    CC BY-NC 4.0 in short, the legal-code link, the credit line, commercial use by permission
THIRD_PARTY.txt    the redistributable third-party material that is in the pack, with real licences
README.md          what is inside, how to use it in UE 5.8 / Blender / Godot / Unity, the credit rule
```

**In:** `Content/City` (streets, kits, the L, expressways, landmarks, parks, water, Austin sights, the Capitol, Willis Tower), `Content/McGregor`, `Content/SkyCity/FX`, `Content/SkyCity/Pickups`, `Content/Vehicles/Placeholder` and `Shared` (the blocky stand-in cars), and the matching original files from `SourceArt/`.

**Never in** (the script checks this on every run and refuses to build if one slips in):

- Epic City Sample content: `Content/Building`, `Prop`, `Material`, `Megascans`, `MSPresets`, `Textures`, `Environment`, `Plugins/CitySamplePCG`.
- Licensed vehicles: `Content/Vehicles/Tesla`, and `SourceArt/Vehicles/*` except `Placeholder`.
- Reference photos: `SourceArt/Reference`.
- The Skyster Roadster, reserved by [LICENSE-ASSETS.md](../LICENSE-ASSETS.md) section 4: `Content/Vehicles/Roadster`, `RoadsterRig`, `SourceArt/roadster_master.glb`, `SourceArt/RoadsterRig`.
- The Volta brand logo: `SourceArt/Brand`.
- Stand-ins of artworks that are still in copyright: Cloud Gate ("the Bean"), Jay Pritzker Pavilion and its trellis, BP Bridge, Crown Fountain, Calder's Flamingo, Chagall's Four Seasons, Miro's Chicago. The script also holds back the three Austin statues (`CREDITS_AND_LICENCES.txt` lists them as in-copyright stand-ins) and the twelve Texas Capitol grounds monuments (modern memorials whose sculptors' rights nobody has checked). The exact names are the `ARTWORKS` list at the top of the script, matched in `Content/` and `SourceArt/`. Materials and textures that only these stand-ins use go with them.
- Maps and level data (`Content/Maps`, `Content/__External*`), `Content/Blockout`, `Content/Developers`, and the Blueprints, game data, PCG graph and HUD assets that only make sense with the game's C++.
- Preview renders in `SourceArt/Landmarks` (some show the stand-ins above), CC0 source downloads (`SourceArt/CC0`) and OpenStreetMap extracts (`SourceArt/osm`).

**Third-party, but free to redistribute** (CC0 from Poly Haven and ambientCG, public-domain NAIP aerials): packed **only where an included asset needs it**, at its original path, so UE references do not break. They are listed in `THIRD_PARTY.txt`. Poly Haven props that no included asset uses are left out.

## Build it

You need: Python 3 (standard library only), a full checkout with the art downloaded (`git lfs pull`), and a place to put the zip that is **not inside the project** (the project disk is nearly full, and the script refuses). The editor does not need to be open or closed; the script never starts it.

```bash
# 1. See what would go in (writes nothing). Add --list files.txt for every file with its size.
python3 tools/package_art.py --version 0.1.0 --dry-run

# 2. Build it
python3 tools/package_art.py --version 0.1.0 \
    --out "/Volumes/Sound Libraries/SkyCity Work/Release/ArtPack"
```

What the script does, in order:

1. Takes the files under the include folders that git tracks (a stray local file never slips in; `--include-untracked` lifts that), minus the artworks and the other left-out items.
2. Stops if any file is a Git LFS pointer instead of the art (`git lfs pull` first).
3. **Dependency scan.** Opens every `.uasset`, reads the package names in its name table (and any `/Game/...` text in its bytes), and checks each one leads to a file that is in the pack, to Unreal Engine itself (`/Engine/`, `/Script/`, and the glTF material instances in `/InterchangeAssets/`), or to a content folder (importers record those). Anything else stops the build and names the asset and the missing reference. That is how a material that quietly depends on City Sample or on `Content/Blockout` gets caught.
4. **Never-list check** on the final selection. Any denied path stops the build, with a list of offenders (exit code 1).
5. Writes the zip to `<out>/SkyCity-Art-Pack-v<version>.zip.part`, renames it when finished, and writes a `.sha256` file next to it. It refuses to overwrite an existing zip, so a version you already published cannot be replaced by accident.
6. **Opens the zip again**: CRC test, the never-list against the real entries, and the dependency scan from the zip's own bytes.

Exit codes: `0` built; `1` the pack would break a rule (details printed); `2` a usage or environment problem.

### When it fails

- **"points at X, which is not in the pack"**: an included asset needs something that may not ship. Leave the asset out (add it to `LEFT_OUT` with a reason), or, if X may ship, add its folder to the include lists. Do not delete the check.
- **"N denied path(s) would be in the pack"**: an include rule is too wide. Narrow it. Never remove an entry from `DENY` to make a build pass.
- **"Git LFS pointers"**: run `git lfs pull`.
- **A new artwork stand-in** (a sculpture, a mural, a building with a famous facade that is still in copyright): add its asset name to `ARTWORKS` *before* the next build. The `SourceArt` file and the `Content` folder share the name.
- **New third-party material**: only CC0 / public domain may go in the pack. Add its path pattern to `ON_DEMAND` and teach `make_third_party()` to list it.

### How it was checked (v0.1.0)

The dry run and the build both pass. The mutation tests below were run once to prove the checks bite: leaving `MI_Asphalt` out made the build fail and name the eight assets that use it; adding `Content/Vehicles/Tesla`, `Content/Vehicles/Roadster` or `Content/Environment` made it fail with the list of denied files. The finished zip was unzipped (`unzip -t`, `shasum -c`), grepped for the denied names, and a separate script re-read every `.uasset` and found no reference outside the zip.

## Before you publish

- [ ] `git status` is clean for the folders in the pack, and `main` is what you want to ship (the pack is made from the working tree's tracked files).
- [ ] `CREDITS_AND_LICENCES.txt` and `LICENSE-ASSETS.md` agree with `LICENSE-ART.txt`. (`LICENSE-ASSETS.md` section 1 asks for the credit "Sky City contributors" for the repo's art; the Art Pack's line names Kenny Hass Music LLC. Decide that you want both.)
- [ ] Skim `README.md` and `THIRD_PARTY.txt` inside the zip.
- [ ] **After the Volta rebrand**, rebuild. The stand-in cars still live in folders called `Model3`, `ModelY`, `Cybertruck`, `Robotaxi` (real model names), and the McGregor site has `SK_RaptorCell` / `SK_RaptorEngine`. The rebrand renames those paths, which changes the pack's paths. If you want a pack without the names, hold the stand-in cars back for now by deleting the three `Vehicles` lines in `CONTENT_INCLUDE` and `SOURCE_INCLUDE` at the top of the script.
- [ ] Anything new in the included folders since last time went through the asset rules in [CONTRIBUTING.md](../CONTRIBUTING.md) section 3. The pack picks up new tracked files in those folders on its own.

## Publish it (Kenny only)

Agents and contributors do **not** push to itch. Kenny decides when, from his Mac. butler is already logged in; never put keys or tokens in the repo, in a script or in a chat.

```bash
"$HOME/Library/Application Support/itch-butler/bin/butler" push \
    "/Volumes/Sound Libraries/SkyCity Work/Release/ArtPack/SkyCity-Art-Pack-v0.1.0.zip" \
    kornontheken/sky-city:art-pack --userversion 0.1.0
```

(Use `$HOME`, not `~`: a `~` inside quotes is not expanded.) Then on the itch.io dashboard (Edit game > Uploads):

- Set the upload's display name to **Sky City Art Pack (free for noncommercial use)**.
- Check that it shows as one download and the version is right. Processing can take a while; `butler status kornontheken/sky-city:art-pack` shows the channel once it is done.
- Paste the page copy from [ITCH_CONTRIBUTE.md](ITCH_CONTRIBUTE.md).

For the next pack, bump the version (`--version 0.2.0`), build, and push to the same channel with the new `--userversion`.
