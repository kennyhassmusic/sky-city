# Course Builder (game mode) and the Sky City MCP server: design

22 Oct 2026, approved by Kenny with his changes (lanes, splits, lap routing, AI opponents, the unveil-ramp look).
The code contract is `Source/SkyCity/SkyCourse.h`.

## Player experience
- **Enter:** Garage (Menu) → X cycles maps: Sky City → McGregor → McGregor Night → **Course Builder** (McGregor day
  opened with `?mode=build`). The player's car spawns a director actor, `ASkyCourseMode`, that runs the mode.
- **Build area:** the open ground of the daytime McGregor map away from the show set and buildings. Bounds in
  `Content/SkyCity/Data/course_area.json` (x/y min/max in the course frame, metres), from the map's layout.
- **Build view:** an orbit / top-down camera (`ASkyCourseBuilderPawn`) over a glowing cursor at the end of the track
  being edited, with a see-through ghost of the next piece (green = fits, red = doesn't, with the reason).
  - Palette strip at the bottom: D-pad left/right picks a piece, D-pad up/down changes its main setting (length,
    angle, height), LB/RB its second setting (radius, bank, side, lanes), A places, B removes the last piece.
  - Right stick orbits, left stick pans, triggers zoom.
  - Y: test drive (and back). X: course menu (new, save, load, rename, skin, laps, opponents, AI skill, catch-up, track width, assists, LLM link).
  - View button: next branch while editing a split.
  - Keyboard equivalents: arrows, Q/E, Enter, Backspace, T, M, Tab.
- **Pieces snap end to end:** each piece starts where the last one ended, facing the same way, at the same height and
  lane count. A course is the start point plus lists of pieces, so it can't come apart.
- **Test drive / race:** the car (and any AI opponents) line up on the starting grid behind the start gate.
  - A 3-2-1 countdown, then go. Pass the checkpoints in order and finish (or complete the laps) for a time.
  - The HUD shows lap x/y, time, splits, best lap and position.
  - Falling off the track puts you back about 10 m before where you fell, in about a second, still moving. The car's reset
    (View / R) does the same. See `Design/RaceHandling.md` for bumpers, assists and catch-up. Y returns to building.
- **Saving and sharing:** courses are small JSON files in `Saved/Courses/<name>.json` (inside the sandbox container in
  the packaged game). Players share them by sending the file.

## Track
- **Lanes:** 1 to 4 lanes; **2 by default**, 1 for a solo builder. Each lane is `lane_width` metres, the same all over the
  course: Standard 5.5 (one unveil ramp deck), **Wide 8 (the default)** or Extra wide 11. So 2 lanes are 16 m by default.
  The course menu has a Track width setting; a change is checked like any edit and refused if the course no longer fits.
  Corkscrews twist more slowly on a deck wider than 11 m (and so are longer), because a wide deck throws off-centre cars out harder.
  A `lanes` piece widens or narrows the track (2→3→4 or back) over its length, centred or to one side.
- **Splits (Y pieces):** a `split` piece fans the track out into 2 to 4 branches. Each branch has its own lane count and
  angle and its own list of pieces, and can split again (3 levels deep). The branches rejoin automatically at the merge:
  each branch end gets a smooth generated connector into the merge, which then narrows or widens to the merge's lane
  count, and the main track carries on.
- **Lap routing:** a branch can be open on some laps only (`laps: [1, 3]`), so different laps run different versions
  of the course. The split shows which way to go:
  - `lights`: signal lights over each branch entrance, green for open and red for closed. Driving into a closed
    branch flashes "wrong way" and returns you to the split.
  - `wall`: a barrier slides across the closed branches.
  - `none`: free choice, every branch open.
- **Lap courses** end with a `close` piece, a generated connector back into the start gate, and can have 1-9 laps.
  Point-to-point courses end with `finish` and have 1 lap.
- **Skins** (course setting):
  - `unveil` (default): the McGregor unveil ramp. Weathered concrete deck (`/Game/McGregor/Materials/MI_RampDeck`),
    white painted lane lines (`MI_RampLine`), and red edge trim along both sides (`MI_LEDRed`, glowing) that brightens
    as cars pass, like the unveil's LED bars. The trim is a 1 m bumper (SkyRail) the car glances off.
  - `classic`: orange toy track with 1 m side rails.
  - `neon`: dark glass deck with cyan edge light.
- **Geometry:** built at runtime as procedural mesh, one component per segment, from centre-line frames every 0.5 m
  (position, forward, left, up), so banks, loops and corkscrews are exact. Collision is the same mesh: the car's
  ground and wall traces use the Visibility channel, which hits complex collision. Components are tagged `SkyTrack`;
  boosters are also tagged `SkyBoost`. Anything under 2.5 m tall is a kerb the car bounces off, not a wall to ride.
- **Physics (done):** on `SkyTrack` the car gains grip in concave curves in proportion to speed (v²/r), so loops hold you
  if you're fast enough, at any car level. Booster strips push at 45 m/s². Nothing changes off the track.

## Course file (format version 2)
Version 2 adds `lane_width` and `catch_up`. A version 1 file (no `lane_width`) still loads, with 5.5 m lanes, exactly as it was built.

Metres and degrees, in the car sim's world frame: Unreal cm = (x * 100, -y * 100, z * 100). Yaw is counter-clockwise
from +x (Unreal yaw = -yaw). `start` is where the start piece begins.

```json
{
  "format": "skycity-course", "version": 2,
  "name": "Desert Loop", "author": "kenny",
  "start": { "x": 120.0, "y": -40.0, "z": 0.5, "yaw": 90 },
  "lanes": 2, "lane_width": 8, "skin": "unveil", "laps": 3, "opponents": 3, "skill": 0.8, "catch_up": true,
  "pieces": [
    { "type": "start" },
    { "type": "straight", "length": 60 },
    { "type": "booster", "length": 10 },
    { "type": "loop", "radius": 10 },
    { "type": "curve", "angle": 90, "radius": 40, "bank": 15 },
    { "type": "lanes", "lanes": 4, "length": 25 },
    { "type": "split", "length": 30, "gate": "lights", "merge_length": 30, "merge_lanes": 2,
      "branches": [
        { "lanes": 2, "angle": 12,  "laps": [1, 3], "pieces": [ { "type": "straight", "length": 80 } ] },
        { "lanes": 2, "angle": -12, "laps": [2],    "pieces": [ { "type": "ramp", "length": 30, "rise": 8 },
                                                                { "type": "jump", "gap": 20, "drop": -8 } ] }
      ] },
    { "type": "checkpoint" },
    { "type": "curve", "angle": 180, "radius": 45 },
    { "type": "close" }
  ]
}
```

| type | settings (hard limits) | notes |
|---|---|---|
| `start` | none | start gate and the starting grid (30 m); must be first |
| `finish` | none | finish gate; ends a point-to-point course (laps = 1) |
| `checkpoint` | none | gate; up to 32 in a course |
| `straight` | `length` 2-300 | |
| `curve` | `angle` -270..270 (+ = left), `radius` 8-300, `bank` -45..45 | banks in and out within the piece |
| `ramp` | `length` 4-150, `rise` -60..60 | S-shaped, level at both ends, steepest point ≤ 45° |
| `jump` | `gap` 4-80, `drop` -30..30 | lip, open gap, landing pad `drop` m higher (+) or lower (-) |
| `loop` | `radius` 6-30, `offset` 0 to 4 x `lane_width` + 1 (default the track width + 1 m) | 360° vertical loop, exit shifted sideways |
| `corkscrew` | `length` 20-260, `turns` 0.5-2 | track rolls about its own axis, ends level |
| `wallride` | `length` 15-150, `side` "left"/"right" | twists up to vertical and back |
| `booster` | `length` 4-30 | speed strip |
| `lanes` | `lanes` 1-4, `length` 10-80, `align` "center"/"left"/"right" | widen or narrow |
| `split` | `length` 15-80, `branches` 2-4 of {`lanes` 1-4, `angle` -45..45, `laps`, `pieces`}, `gate` "lights"/"wall"/"none", `merge_length` 15-80, `merge_lanes` 1-4 | |
| `close` | none | last piece of a lap course: connector back to the start gate |

Course limits:
- Up to 400 pieces in all, the whole course inside the build area.
- No two non-adjacent parts closer than 3 m (the track can't run through itself, except a loop over its own entry).
- The deck at least 0.3 m above the ground everywhere it isn't sitting on it.
- Generated connectors (merges, close) no tighter than 15 m radius and no steeper than 35°; otherwise an error says
  which branch can't reach the merge.
- Every lap must have at least one open branch at every split.

## The MCP server (in the game)
- **Off by default.** The player switches *LLM link* on in the course menu (or `-SkyCourseMcp` on the command line, for
  tests).
- **Local only:** it listens on 127.0.0.1, port 47800, MCP Streamable HTTP at `/mcp` (JSON-RPC 2.0, protocol 2025-03-26
  and later, JSON responses), and rejects non-local Origin headers (DNS-rebinding protection).
- **Courses only.** No file paths, no shell, no code.
  - Course names are sanitised to letters, digits, spaces, dashes and underscores and live only in the courses folder.
  - Every change is validated and baked before it's built, and the result comes back to the LLM.
- Tools:
  - `get_course_guide`: the format, the piece table with limits, tips.
  - `get_course`: the course JSON plus facts from the bake: length, bounds, the cursor at each sequence's end (where
    the next piece would start), lowest and highest points, gates, splits, warnings.
  - `set_course(course)`: replace the whole course; errors come back with JSON paths.
  - `add_pieces(pieces, branch_path?)`, `remove_pieces(count, branch_path?)`, `update_piece(path, piece)`: edit in
    place. A path like `pieces[6].branches[1].pieces[0]` addresses any piece.
  - `list_courses`, `save_course(name)`, `load_course(name)`, `new_course(near_player?)`.
  - `get_player`: where the car is, its heading and speed, and the build area, so the LLM can build near the player.
  - `start_race(opponents?, skill?)`, `stop_race`, `get_results`.
- **Connecting an LLM:**
  - Claude Code: `claude mcp add --transport http skycity http://127.0.0.1:47800/mcp`
  - Claude Desktop and other stdio-only clients: `npx -y mcp-remote http://127.0.0.1:47800/mcp`
  - Instructions in `docs/COURSE_MCP.md`.
- **Packaged Mac app:** add `com.apple.security.network.server` to the sandbox entitlements, or the server can't listen.

## AI opponents
- 0-7 opponents, skill 0.3-1.2. `catch_up` (default on) lets a car far ahead ease off and one far behind push, scaled by skill; the player is never sped up. They're more `ASkysterCar`s driven through the car's test-input hooks, with an AI flag:
  no camera, HUD, saved progress or toasts. They use the same physics and level 6 abilities, minus flight.
- They follow their lap's route, each in its own lane, and plan their speed for curves, loops (minimum entry speed) and
  jumps. They boost on straights and recover after crashes or falls (put back on the track like the player).
- Split routing: they take the branch the gate shows open when they get there.

## Code plan and owners
- `SkyCourse.h`: the contract. Changes need the lead's OK.
- `SkyCourseModel.cpp` + `SkyCourseTrack.cpp`: course geometry agent.
- `SkyCourseRace.cpp` (+ `SkyCourseAI.cpp` if wanted), and the AI flag in `SkysterCar.*`: race agent.
- `SkyCourseMode.cpp` (+ `SkyCourseBuilder.cpp` if wanted): builder agent.
- `SkyCourseMcp.cpp`, `docs/COURSE_MCP.md`, `Scripts/course/mcp_smoke_test.py`: MCP agent.
- Done by the lead: track physics hooks in SkysterCar, the Garage entry, the HUD hook, Build.cs and plugins, stubs.
