# Course Builder (game mode) and the Sky City MCP server: design

Draft, 22 Oct 2026. Kenny's brief: a Hot Wheels-style way for players to build their own courses in the game, probably on
the daytime McGregor map, as its own game mode; and a local MCP server the player's own LLM can use to build courses
for them.

## Player experience
- **Enter:** Garage (Menu) → *Course Builder*. Loads McGregor (day) with the `?mode=build` option. The open ground east
  of the show set is the build area (bounds in `Content/SkyCity/Data/course_area.json`, from demo_layout.json).
- **Build view:** a top-down/orbit camera over a glowing cursor at the end of the course. The piece palette sits at the
  bottom of the screen. D-pad left/right picks a piece, D-pad up/down changes its main setting (length, angle, height),
  RB/LB change the second setting (bank, side), A places it, B removes the last piece, Y starts or ends a test drive,
  X opens the course menu (new, save, load, rename, LLM link on/off). Keyboard: arrows, Q/E, Enter, Backspace, T, M.
- **Pieces snap end to end** like Hot Wheels track: each piece starts where the last one ended, facing the same way,
  at the same height and bank. A course is just the start point plus a list of pieces, so it can never come apart.
- **Test drive / race:** the car drops in at the start gate. Pass every checkpoint in order and cross the finish (or the
  start gate again for a lap course) for a time. The HUD shows the lap time, best time and splits. Falling off returns
  you to the last checkpoint. Y goes back to building.
- **Saving and sharing:** courses are small JSON files in the game's save folder (`Saved/Courses/<name>.json`, inside
  the sandbox container in the packaged game). Players share them by sending the file; a later version can add share codes.

## Track look and physics
- Classic orange track, 4.5 m wide (Roadster 2 m wide, room to drift), 0.25 m thick, 0.6 m side rails (the car bounces
  off rails; anything under 2.5 m tall isn't a wall it can ride), blue boosters, a chequered start/finish gate.
- Built at runtime as procedural mesh sections (ProceduralMeshComponent), one section per piece, from a centre-line
  sampled every ~0.5 m with a full frame (forward, left, up) so banks, loops and corkscrews are exact. Collision is the
  same mesh (the car's ground and wall traces use the Visibility channel, which hits complex collision).
- Actors are tagged `SkyTrack`. **Loops need one physics addition:** today the car leaves a surface when gravity pulls
  it off harder than the fans' suction, with no allowance for speed. On `SkyTrack` surfaces the car will also count the
  centripetal force of a concave curve, speed x the rate the surface normal turns (v^2/r), so a loop holds you if you're
  fast enough, at any car level, as on a real Hot Wheels loop. Nothing changes off the track.
- Boosters add speed along the track (like a boost pad); a "launch" ramp lip throws the car into a jump.

## Course file (format version 1)
Units: metres and degrees. Positions are in the map's frame (x east, y north, z up, metres; Unreal cm / 100 with y
flipped: the same frame as the car sim). `start` is where the first piece begins; `yaw` 0 = east, 90 = north.

```json
{
  "format": "skycity-course", "version": 1,
  "name": "Desert Loop", "author": "kenny",
  "start": { "x": 120.0, "y": -40.0, "z": 0.5, "yaw": 90 },
  "laps": 1,
  "pieces": [
    { "type": "start" },
    { "type": "straight", "length": 40 },
    { "type": "booster", "length": 10 },
    { "type": "loop", "radius": 9 },
    { "type": "curve", "angle": 90, "radius": 30, "bank": 20 },
    { "type": "ramp", "length": 20, "rise": 6 },
    { "type": "jump", "gap": 18 },
    { "type": "checkpoint" },
    { "type": "finish" }
  ]
}
```

Pieces (ranges are hard limits; the game and the MCP server both reject anything outside them):

| type | parameters | notes |
|---|---|---|
| `start` | none | start gate (must be first) |
| `finish` | none | finish gate (must be last); a lap course instead ends where it started |
| `checkpoint` | none | gate; up to 32 |
| `straight` | `length` 2-200 | |
| `curve` | `angle` -270..270 (+ = left), `radius` 8-200, `bank` -45..45 | flat or banked turn |
| `ramp` | `length` 4-120, `rise` -60..60 | smooth S-shaped slope up or down; steepest point 45 deg |
| `jump` | `gap` 4-80, `drop` -20..20 | a ramp lip, an open gap and a landing pad lower or higher by `drop` |
| `loop` | `radius` 6-25, `offset` 4.5-10 | 360 deg vertical loop; exits shifted sideways by `offset` so it doesn't hit itself |
| `corkscrew` | `length` 20-120, `turns` 0.5-2 | track rolls about its own axis |
| `wallride` | `length` 10-120, `side` left/right | track twists up to a vertical wall and back |
| `booster` | `length` 4-20 | speed strip |

Limits: up to 400 pieces, the whole course inside the build area, no piece closer than 3 m to another (except the
pieces it joins), lowest point at least 0.3 m above the ground (the game raises the start to fit).

## The MCP server (in the game)
- Off by default. The player switches it on in the course menu (*LLM link*). It listens on **127.0.0.1 only**, port
  **47800**, MCP Streamable HTTP at `/mcp` (JSON responses, protocol 2025-03-26 and later), and rejects requests whose
  Origin isn't local (DNS-rebinding protection).
- **It can only edit courses.** No file paths, no shell, no code: tools read and change the current course, save and load
  courses by name (letters, numbers, spaces and dashes only) inside the courses folder, and start a test drive. Every
  course is validated before it's built.
- Tools:
  - `get_course_guide`: the format above, the piece table with limits, tips for good courses (and what makes loops work).
  - `get_course`: the current course JSON plus computed facts: total length, bounding box, end point and heading,
    lowest and highest points, warnings.
  - `set_course(course)`: replace the whole course (validated; returns errors with the piece index).
  - `add_pieces(pieces)`, `remove_pieces(count)`, `update_piece(index, piece)`: edit in place.
  - `list_courses`, `save_course(name)`, `load_course(name)`.
  - `get_player`: where the car is, which way it faces, its speed, and the build area, so the LLM can build near the player.
  - `start_test_drive`, `stop_test_drive`, `get_results`: best times and splits after a run.
- Hooking up an LLM: Claude Code `claude mcp add --transport http skycity http://127.0.0.1:47800/mcp`; Claude Desktop
  and other stdio-only clients through `npx mcp-remote http://127.0.0.1:47800/mcp`. Documented in `docs/COURSE_MCP.md`.
- Packaged Mac app: add `com.apple.security.network.server` to the sandbox entitlements (the app is sandboxed with no
  network today), or the server can't listen.

## Code plan
- `Source/SkyCity/SkyCourse.h/.cpp`: the course model (parse, validate, serialize), the piece generator (centre-line
  frames → mesh), `ASkyCourse` (builds the sections, gates, checkpoints and timing).
- `SkyCourseBuilder.h/.cpp`: build mode (cursor, palette, camera, input) and the HUD panels for it.
- `SkyCourseMcp.h/.cpp`: the HTTP listener (Unreal's HTTPServer module) and the JSON-RPC tools, calling into ASkyCourse
  on the game thread.
- `SkysterCar`: the `SkyTrack` centripetal adhesion, a Garage entry for the mode, respawn at the last checkpoint.
- Build.cs: `ProceduralMeshComponent`, `HTTPServer`, `Json`, `JsonUtilities`; enable the ProceduralMeshComponent plugin.
- Tests: a headless course-validation test (C++ automation test), a PIE drive of a sample course (loop, banked curve,
  jump) with the car's test hooks, and an MCP session from a script (initialize, get_course_guide, set_course, save).
