# Setting up City Sample buildings

The buildings in the Sky City map come from Epic Games' **City Sample**. Its licence lets us ship it inside the packaged game, but **not** put it in a public repository. So each contributor downloads it with their own free Epic account and copies the parts we use into their local project.

> ⚠️ **Never commit City Sample content.** The `.gitignore` excludes its folder. If `git status` ever shows City Sample files, stop and ask a maintainer.

## What you need

- A free **Epic Games account**, signed in to the Epic Games Launcher
- A lot of free disk space: the City Sample project for 5.8 is about 97 GB. You can delete it after copying; the parts Sky City uses come to about 23 GB.
- Your Sky City checkout, already cloned (see the README)

## Steps

1. **Add City Sample to your library.** Find **City Sample** on [Fab](https://www.fab.com) and add it to your library. It's free.
2. **Create a City Sample project.** In the Epic Games Launcher, go to *Unreal Engine → Library → Fab Library*, find City Sample, and create a project with engine version **5.8** (or the newest version offered, then open it once in 5.8). Put it somewhere outside your Sky City folder.
3. **Copy the folders Sky City uses** from the City Sample project into your Sky City project, keeping the same paths:

   | From the City Sample project | To your Sky City project |
   |---|---|
   | `Content/Building/` (the `CH`, `NY`, `SF`, `Material`, `Texture` and `QB` folders) | `Content/Building/` |
   | `Content/Prop/` | `Content/Prop/` |
   | `Content/Material/` | `Content/Material/` |
   | `Content/Megascans/` (`3D_Assets`, `Atlases`, `Imperfections`, `Surfaces`) | `Content/Megascans/` |
   | `Content/MSPresets/` | `Content/MSPresets/` |
   | `Content/Textures/` | `Content/Textures/` |
   | `Content/Environment/RoofTop/` | `Content/Environment/RoofTop/` |
   | `Plugins/CitySamplePCG/` (the whole plugin) | `Plugins/CitySamplePCG/` |

   The plugin matters most: Sky City's project file enables `CitySamplePCG`, so without it the editor reports a missing plugin. The buildings are placed by the PCG volumes in the `SkyCityMashup` map, which call the plugin's building graphs.

   Copy with Finder or `rsync`. **Don't** use the editor's *Migrate* tool unless the table above says to; it can pull in extra dependencies and change paths.
4. **Open Sky City** and load the `SkyCityMashup` map. Buildings should appear. If you see grey boxes or missing-asset warnings, check that the folders are in exactly the right place.

## Checking it worked

- The Sky City map loads with buildings in the Loop and downtown Austin.
- The Output Log has no "Failed to load" warnings mentioning City Sample paths.
- `git status` shows **no** City Sample files.

## Why it works this way

City Sample is free for anyone with an Epic account. Its licence allows it to be shipped inside a packaged game, but not redistributed on its own or as source content. That's why it's in the game builds on itch.io, but not in this repo.
