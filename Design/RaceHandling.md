# Course Builder races: easy and fun to control

22 Oct 2026. Approved by Kenny (parts 1-4 and the light catch-up) and built the same night. Applies only to Course Builder races and test drives; free roam doesn't change.

## Why the car falls off today
- **No edges.** The `unveil` skin's red trim is an 8 cm strip. Nothing stops a car that drifts wide.
- **Narrow deck for the speed.** 2 lanes = 11 m. At 100+ mph a car is ~2 m wide, and Skyster steers like
  Rocket League: quick to rotate, easy to swing the tail out.
- **Harsh recovery.** After 2 s off the track you go back to the *last checkpoint*, stopped. One slip can cost 10-20 s.
- **Air is all on you.** No help to land straight on a jump's pad.

## What the best arcade racers do
| Game | Edges | Assists | Off-track / falls |
|---|---|---|---|
| Mario Kart 8 / World | Walls on most turns; open drops on some | **Smart Steering** (on by default, antenna on the kart shows when it works) keeps you off edges and grass; Auto-Accelerate | Lakitu picks you up and puts you back where you fell, about 2-3 s lost |
| Fortnite Rocket Racing | Track pieces with walls; cars bounce off them ("wall ricochet") | Drift charges boost; air roll to land | Respawn on the track you were last on, never ahead of your best progress |
| Hot Wheels Unleashed | Side walls on almost every piece; magnet pieces stick you to loops | Drift-boost | Reset button and auto-reset, back to the track at once |
| Trackmania | Borders on most blocks; skill tracks have none | None | Instant respawn at a checkpoint (one key). Losing a few seconds is the game |
| Rocket League | Curved walls you drive up | None | None needed (arena) |

What they share:
1. **Edges you bounce off.** You scrape along the wall and keep going, with no crash and little speed lost.
2. **Assists for beginners, on by default.** Experts can turn them off, and the game shows when an assist is helping.
3. **Losing time instead of the race.** Falling off costs about 2 s, and you go back to where you fell.
4. **A wide track** compared with the car, and wider still in the hard parts.

## Proposal (each part can be approved on its own)

### 1. Bumpers on both sides (your idea, yes)
- A **1 m bumper** along both edges of every piece, in every skin (`unveil`: the red LED bar becomes a glowing bumper
  rail). It stays under 2.5 m, so the car never tries to wall-ride it.
- **Glancing bounce, not a crash.** A new `SkyRail` tag gets its own response in the car:
  - the push away from the wall is removed, with a soft bounce (about 0.2);
  - the car turns to run along the wall;
  - it keeps 90-95% of its speed and takes no damage.

  This also fixes the old rail bug on tilted decks (the bounce now uses the deck's frame, not the horizontal).
- **Gaps:** no bumpers over a jump's open gap or where branches share a deck at a split (the car must cross there).
- Loops, corkscrews and wall rides keep their tall rails.

### 2. A wider track
- Your idea was 2 lanes as wide as today's 4 (22 m). **My pick: 8 m lanes** (2 lanes = 16 m, 4 lanes = 32 m). That's
  about 7 car widths per lane pair. It's wide enough to drift through the corners, but loops and corkscrews still fit
  the build area and keep their 3 m clearance.
- A course setting **Track width: Standard 5.5 / Wide 8 (default) / Extra wide 11 m per lane**, in the course menu and
  in the file (`"lane_width"`). Your 22 m idea is Extra wide.
- **Old files:** a file without `lane_width` loads exactly as it was built (5.5 m), so it can't stop fitting. New
  courses and the example courses are Wide. One click in the menu widens an old course; it's checked like any edit.
- Corkscrews twist a little more slowly when the deck is wide. A wider deck pushes off-centre cars out harder (found
  by the AI tuning), so this keeps them as easy as today's.

### 3. Race assists for the player (setting: Full / Light / Off, default **Full**)
These go in `SkysterCar.cpp` and work only on Course Builder track, during a race or test drive (a flag the race sets
on its cars):
- **Smart steering** (Full): if your path would leave the deck within about 0.6 s, a gentle steering nudge points you
  back. While the car slides it nudges half as hard, so a drift stays yours, and a small STEER ASSIST tag shows
  while it helps. It uses the AI's
  deck-frame steering, already tuned.
- **Track grip** (Full, Light): extra downforce on the deck, so banks, crests and the bottoms of ramps don't throw you.
  Small crests no longer launch you (a jump's lip still does).
- **Stability** (Full): yaw damping when you aren't holding drift, so S-bends don't spin you. Holding drift
  (powerslide) turns it off, so you can still slide on purpose.
- **Landing help** (Full, Light): in the air above the track, the car turns to land wheels-down and straight along the
  deck. It gets a light sideways pull toward the pad's middle, like Mario Kart's glider: never more than a few m/s.
- **Off**: pure Skyster, as in 0.2.2. Best times record which assist level set them.
- The AI opponents don't use these (they have their own driver). Kenny's autopilot test runs with assists off, as now.

### 4. Lakitu-style recovery
- **Where:** the last spot your wheels were on the deck (a trail kept every few metres), set back 10 m, centred,
  facing along the track. Never ahead of your best progress this lap, so falling can't be a shortcut.
- **How fast:** off the deck and falling → back on the track in **about 1 s** (now 2 s), with a quick fade, not a cut.
- **Speed:** you keep about 70% of your speed (at least 25 m/s), instead of stopping. If you fell in a jump's gap,
  you're put on the run-in at the speed that jump needs.
- **Ghost for 1.5 s:** no car-to-car contact while you get going.
- **Reset button** (Trackmania-style): the car's own reset (**View** button, keyboard R), in a race, puts you back at
  the last good spot. It's useful when you're stuck facing the wrong way.
- The AIs use the same recovery, so a fall costs them the same time.

### 5. Catch-up (light, optional)
- **Slipstream for everyone:** right behind a car, you get up to +4% speed. It's fair, and makes passing fun.
- **AI rubber band** (setting, default on): an AI far ahead eases off a little, and one far behind pushes a little,
  scaled by skill, so races stay close. The player's car is never sped up, so best times stay honest.
- No items or weapons. Those belong in a separate design if you want them.

## Recommendation
Do **1, 2, 3 and 4** now; they fix "kept falling off" from four sides. Make **5** slipstream plus the AI rubber band,
both easy to switch off.

Settings, in the course menu: **Assists** (Full / Light / Off), **Track width** (Standard / Wide / Extra wide),
**Catch-up** (on / off).

## How it's checked
Console variable `SkyCourse.RaceAssist` (0/1/2) forces the assists on the player's car, autopilot included (-1, the
default, uses the menu setting; the autopilot then drives with assists off).

Results, 22 Oct (3 laps, 3 AIs plus the autopilot, one AI dropped off the side on purpose):

| Race | Width | Assists | Falls (besides the drop) | Dropped car back |
|---|---|---|---|---|
| Example | 8 m | Off | 0 | 1.5 s, moving |
| Example | 8 m | Full | 0 | 1.5 s, moving |
| Canyon Run (old file) | 5.5 m | Off | 0 | 1.5 s, moving |
| Canyon Run | 8 m | Full | 0 | 1.5 s, at the jump's speed (78 mph) |

- `Scripts/course/race_test.py` on the example course and Canyon Run, at Wide width:
  - every AI and the autopilot finish with 0 falls;
  - once with assists Full, once Off.
- A drop test: a car pushed off the side is back on the deck within 1.5 s, moving, no more than 15 m back.
- Old course files load and build unchanged (Standard width).
- Free roam in SkyCityMashup: no change (every assist checks the race flag and the `SkyTrack` tag).

## Files
`SkyCourse.h` (width setting, `SkyRail` tag, assist level), `SkyCourseModel.cpp` (lane width, limits, file field),
`SkyCourseTrack.cpp` (bumpers, slower corkscrew twist when wide), `SkyCourseRace.cpp` / `SkyCourseAI.cpp`
(recovery, reset button, slipstream, rubber band), `SkysterCar.cpp/.h` (rail bounce, race assists, race flag),
`SkyCourseMode.cpp` (menu settings), HUD (assist icon), `Design/CourseBuilder.md`, `docs/COURSE_MCP.md` (new field).
