# The LLM link: let your own AI build Sky City courses

The Course Builder can open a small door on your computer so that an AI assistant you already use (Claude Code, Claude
Desktop, or any other app that speaks MCP) can build courses for you. You tell it what you want, in plain words, and
the track appears piece by piece in the game while you watch. Then you drive it.

- **It is off by default.** You switch it on yourself, and it closes again when you switch it off or leave the Course
  Builder.
- **It only works on courses.** It can add, change and remove track pieces, save and load courses, start a race and read
  the results. It cannot touch anything else on your computer.
- **It never leaves your computer.** It listens on `127.0.0.1` (your own machine) and nowhere else.

## Turn it on

1. In the Garage (Menu button), press X until you reach **Course Builder**.
2. Open the course menu (X) and switch **LLM link** to **ON**.
3. The address is `http://127.0.0.1:47800/mcp`. Leave the game running; your AI connects to that address.

Switch it **OFF** in the same menu (or quit the game) and the door closes: nothing is listening any more.

## Connect your AI

You only do this once.

### Claude Code

With the game running and the LLM link on, in a terminal:

```
claude mcp add --transport http skycity http://127.0.0.1:47800/mcp
```

Start `claude` and type `/mcp`: **skycity** should be listed as connected. If you add it while the link is off, the
connection fails; switch the link on and reconnect from `/mcp`. Use `--scope user` to have it in every project.

### Claude Desktop

Claude Desktop talks to local programs, not to web addresses, so it needs a small bridge (`mcp-remote`, which needs
[Node.js](https://nodejs.org) installed). Open **Settings > Developer > Edit Config** (the file is
`~/Library/Application Support/Claude/claude_desktop_config.json` on a Mac) and add the server:

```json
{
  "mcpServers": {
    "skycity": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://127.0.0.1:47800/mcp", "--allow-http"]
    }
  }
}
```

If the file already has an `mcpServers` section, add just the `"skycity": { ... }` part inside it. Quit and reopen Claude
Desktop. The bridge refuses plain `http://` addresses unless told they are trusted, which is what `--allow-http` is for (the
address is your own machine, so that is fine). The game must be running with the link on when Claude Desktop starts, or
reconnect after.

### Other apps

Any app that supports MCP over **Streamable HTTP** can use the address directly; there is no sign-in. Apps that only
support local (stdio) servers can use `npx -y mcp-remote http://127.0.0.1:47800/mcp --allow-http` as the command, as above. To look at
the tools by hand, `npx @modelcontextprotocol/inspector` (choose the Streamable HTTP transport) works, and so does:

```
python3 Scripts/course/mcp_cli.py tools
python3 Scripts/course/mcp_cli.py call get_player
```

## Things to ask for

Start with the first one. The AI reads the course guide by itself, then builds.

- "Build me a 3-lap course with a big loop and a split that alternates each lap."
- "Make a point-to-point stunt course: a long boosted straight, a jump over a big gap, a corkscrew and a finish."
- "Start a new course next to my car and build a fast banked oval with a wall-ride on the back straight. Save it as Oval Rush."
- "Look at the course I have built and make the corners smoother. Add a booster before the loop."
- "Make it wider (4 lanes) for the first 100 metres, then a split with lights over each branch."
- "Load Oval Rush, then start a race with 4 opponents."
- "Tell me what you built and how long a lap is."

You can keep building by hand in the game while it works; it always looks at the course as it is now. While it builds, short
"LLM link" messages appear on screen. The AI can't steer your car: you drive. Edits are refused while a race is running, so
press Y to go back to building (or ask it to stop the race).

## What the AI can do

| Tool | In plain words |
|---|---|
| `get_course_guide` | Read the rules: the course format, every piece and its limits, tips. |
| `get_player` | Where your car is and which way it faces, and the build area. |
| `new_course` | Start a fresh course (optionally right next to your car, and with a track width: lanes are 8 m by default, or 5.5 / 11). |
| `add_pieces` | Add pieces to the end of the track, or to a branch of a split. |
| `remove_pieces`, `update_piece` | Take pieces off the end, or change one piece (or the course settings: laps, name, skin, opponents, `lane_width` 5.5 / 8 / 11 m per lane, `catch_up` on/off). |
| `get_course`, `set_course` | Read the whole course, or replace it. |
| `list_courses`, `save_course`, `load_course` | Work with saved courses. |
| `start_race`, `stop_race`, `get_results` | Put you on the grid (with opponents if you like), stop, read the times. |

Every change is checked before it is built. If it would put the track outside the build area, through itself, or break a
limit, nothing changes and the AI is told exactly why, with the piece that is wrong, so it can fix it.

## Safety

- **Local only.** The server is bound to `127.0.0.1`, so other computers, your Wi-Fi and the internet can't reach it. It
  also turns away any request whose `Origin` or `Host` isn't `localhost`, `127.0.0.1` or `[::1]` (a web page in your
  browser can't use it, even through DNS tricks) with an error 403.
- **No password.** While the link is on, any program running on your own computer can use it, just like any local server.
  That's why it is off until you switch it on. What it can do is limited to the course tools above.
- **Courses only.** There is no file path, shell command or code in any tool. A course name keeps only letters, digits,
  spaces, dashes and underscores, and courses are only read from and written to the game's courses folder
  (`Saved/Courses`). Saving over an existing course needs an explicit "overwrite" from the AI.
- **Small requests.** A request bigger than 2 MB is refused, and there is a limit on connections.
- Your saved courses are plain JSON files; read them, share them, delete them as you like.

## If it doesn't connect

- **"Connection refused"**: the LLM link is off, or the game isn't in the Course Builder. Switch it on in the course menu.
- **"Address already in use"** in the game log: another copy of the game (or something else) already uses port 47800.
  Quit it.
- Use `127.0.0.1`, not `localhost`: on some machines `localhost` tries the IPv6 address first and the server only
  listens on IPv4.
- **It connected before but now fails**: the game was restarted. Reconnect from your AI app (in Claude Code, `/mcp`).
- The game's log (`~/Library/Logs/Unreal Engine/SkyCityEditor/SkyCity.log` in the editor) shows each call as
  `LogSkyMcp: Course MCP: add_pieces -> ok (35 ms)`.

## For developers

- Source: `Source/SkyCity/SkyCourseMcp.cpp` (`FSkyCourseMcp`, started by `ASkyCourseMode::SetMcpEnabled`; `-SkyCourseMcp` on
  the command line turns it on at launch). Design: `Design/CourseBuilder.md`.
- Protocol: MCP Streamable HTTP, JSON responses only. `POST /mcp` carries JSON-RPC 2.0 (`initialize`, `notifications/initialized`,
  `ping`, `tools/list`, `tools/call`; batches work), protocol versions 2025-03-26 and 2025-06-18. `GET` is 405 (no SSE
  stream), `DELETE` ends a session. An `Mcp-Session-Id` is issued on `initialize` but not required.
- It is a small socket server of its own (macOS and Linux), not Unreal's `HTTPServer` module: that module can't close a single
  port (only all listeners at once, which would also stop the editor's own MCP server on 8000), takes its bind address from
  an ini setting, and costs a millisecond per idle connection every frame. Requests are read, run and answered on the game
  thread, one tool call per frame at most.
- Test: with the link on, `python3 Scripts/course/mcp_smoke_test.py` (add `--protocol-only` before the course model exists).
  In the editor, the console command `SkyCourse.Mcp 1` starts a server on the Course Builder in the PIE world (spawning
  one if needed) and `SkyCourse.Mcp 0` stops it.
- Prove it is local: `lsof -nP -iTCP:47800 -sTCP:LISTEN` shows `127.0.0.1:47800` and nothing else.
- Packaged Mac app: the sandbox needs the `com.apple.security.network.server` entitlement or the server can't listen.
