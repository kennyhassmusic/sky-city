# Sky City roadmap

What's being built next, in order. Kenny decides the order; ideas from contributors go in GitHub Discussions first.

## Now: open source
- The source on GitHub (github.com/kennyhassmusic/sky-city), with the CLA check, the pr-guard check and code-owner review.
- The McGregor line-up and the blocky stand-in cars work in a clone that has no licensed car models.

## Next
Deferred from the texture-stretch pass. Do not start these until asked:
- Floating bases (the census now flags a building whose base is not on the sidewalk)
- Ground surfaces
- Grime
- Roofs
- Loader floor bugs

## Next: Course Builder (its own game mode)
- A Hot Wheels-style track builder: snap together orange track pieces (straights, curves, banked turns, ramps, jumps,
  loops, corkscrews, boosters, wall-ride walls, a start/finish gate and checkpoints) and race them with lap times.
- Built on the daytime McGregor map's open ground; courses saved as small JSON files you can share.
- A local MCP server in the game, so a player's own LLM (Claude, or any MCP client) can build courses for them while
  they watch: it only edits courses, listens on this computer only, and can't touch files or run code.

### Then: flight and boost pieces (Kenny: right after the MCP link works)
- **Sky gates:** checkpoint rings floating in the air, flown or jumped through.
- **Flight gaps:** gaps longer than any jump (up to a few hundred metres), crossed only with boost and flight, with a
  landing deck on the far side.
- **Climb walls:** vertical track sections that need the wall-grip fans.
- **AI opponents that boost and fly** through all of these.

### Then: split-screen multiplayer (Kenny: once he has played the Course Builder, used the MCP link and run a race himself)
- Two or more players on one Mac, each with a controller and their own view of the screen, racing on Course Builder
  courses (and free-roaming the city).

## Next round: Volta rebrand
- Replace real carmaker and model names in asset, folder and script names with the game's invented brand,
  Volta Motors, and put the Volta badge on the cars, the chargers, signs and the McGregor event.
- Then publish the **Art Pack** (`tools/package_art.py`, `docs/ART_PACK.md`): Kenny is holding it until the real car
  names are gone from the stand-in cars and asset names.

## Next week: Car Designer
- Pick a car and paint it: body colour, finish (gloss, matte, metallic, chrome), accent and wheel colours, decals.
- Import your own car: a model your LLM made for you (glTF/GLB), checked for size and wheel positions, then driven with
  the same Skyster physics so you can try it out. Imported cars stay on your computer.

## Later
- Story and progression, easter eggs and achievements (see Places_and_Easter_Eggs.md), races across the city.
- A Windows build.
