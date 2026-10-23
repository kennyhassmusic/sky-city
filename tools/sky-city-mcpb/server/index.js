#!/usr/bin/env node
// Sky City Course Builder link for Claude Desktop (and any app that runs local MCP servers over stdio).
//
// The game itself runs the real MCP server, inside Sky City, on this Mac only: http://127.0.0.1:47800/mcp, while the
// Course Builder's "LLM link" is switched on. Claude Desktop only starts local servers that talk over stdin/stdout, so
// this file is a small pass-through: each message Claude sends is posted to the game and the game's answer goes back.
// It touches no files and talks to nothing but the game on this computer. No dependencies (Node 18+).
//
// If the game isn't running (or the link is off), Claude still connects: it sees one tool, sky_city_status, that says
// how to switch the link on, and the real course tools appear by themselves as soon as the game answers.
"use strict";

const readline = require("readline");

const DEFAULT_URL = "http://127.0.0.1:47800/mcp";
const URL_ = (() => {
  const u = process.env.SKYCITY_MCP_URL || DEFAULT_URL;
  // the promise is "this computer only": refuse anything that isn't a loopback address
  try {
    const p = new URL(u);
    if (p.protocol === "http:" && ["127.0.0.1", "localhost", "[::1]"].includes(p.hostname)) return u;
  } catch (e) { /* fall through */ }
  return DEFAULT_URL;
})();
const POLL_MS = 4000;
const HELP =
  "Sky City isn't answering yet. In the game: open the Garage (Menu button or P) and choose Course Builder, " +
  "then press X for the course menu and switch LLM link ON. The course tools show up by themselves once it's on " +
  "(or call sky_city_status again).";
const STATUS_TOOL = {
  name: "sky_city_status",
  title: "Check the link to Sky City",
  description:
    "Checks whether the Sky City game is running with its LLM link on. Call this if the course-building tools are " +
    "missing: it says what the player needs to do in the game.",
  inputSchema: { type: "object", properties: {} },
  annotations: { readOnlyHint: true, openWorldHint: false },
};

let session = null;      // the game's Mcp-Session-Id
let clientInit = null;   // the client's initialize params, replayed to the game when it (re)appears
let gameUp = false;
let pollTimer = null;

function send(obj) { process.stdout.write(JSON.stringify(obj) + "\n"); }
function log(...a) { process.stderr.write("[sky-city-link] " + a.join(" ") + "\n"); }

async function post(msg) {
  const headers = { "Content-Type": "application/json", Accept: "application/json, text/event-stream" };
  if (session) headers["Mcp-Session-Id"] = session;
  const r = await fetch(URL_, { method: "POST", headers, body: JSON.stringify(msg) });
  const sid = r.headers.get("mcp-session-id");
  if (sid) session = sid;
  if (r.status === 202 || r.status === 204) return null;
  const text = await r.text();
  if (!r.ok && !text) throw new Error(`HTTP ${r.status}`);
  if (!text) return null;
  if ((r.headers.get("content-type") || "").includes("text/event-stream")) {
    const line = text.split("\n").find((l) => l.startsWith("data:"));
    return line ? JSON.parse(line.slice(5)) : null;
  }
  return JSON.parse(text);
}

const defaultInit = () => ({
  protocolVersion: "2025-06-18",
  capabilities: {},
  clientInfo: { name: "sky-city-link", version: "1" },
});

// (Re)open a session with the game. True if it answered.
async function connect() {
  try {
    session = null;
    const r = await post({ jsonrpc: "2.0", id: "sky-city-link-init", method: "initialize", params: clientInit || defaultInit() });
    if (!r || r.error) return false;
    await post({ jsonrpc: "2.0", method: "notifications/initialized" });
    return true;
  } catch (e) {
    return false;
  }
}

function setUp(up) {
  if (up === gameUp) return;
  gameUp = up;
  log(up ? "Sky City answered" : "lost Sky City");
  if (up) {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    // tell the client its tool list changed: the real course tools are here now
    send({ jsonrpc: "2.0", method: "notifications/tools/list_changed" });
  } else {
    startPolling();
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => { if (!gameUp && (await connect())) setUp(true); }, POLL_MS);
}

async function forward(msg) {
  try {
    return await post(msg);
  } catch (e) {
    setUp(false);
    return undefined;   // couldn't reach the game
  }
}

async function handle(msg) {
  const { id, method, params } = msg;
  const isRequest = id !== undefined && id !== null && typeof method === "string";

  if (method === "initialize") {
    clientInit = params || defaultInit();
    const up = await connect();
    gameUp = up;
    if (!up) startPolling();
    send({
      jsonrpc: "2.0", id,
      result: {
        protocolVersion: (params && params.protocolVersion) || "2025-06-18",
        capabilities: { tools: { listChanged: true } },
        serverInfo: { name: "sky-city-courses", title: "Sky City Course Builder", version: "link-1.0" },
        instructions: up
          ? "Connected to Sky City. Call get_course_guide first: it explains the course format and every track piece."
          : HELP,
      },
    });
    return;
  }
  if (method === "notifications/initialized" || (typeof method === "string" && method.startsWith("notifications/"))) {
    if (gameUp) await forward(msg);
    return;
  }
  if (method === "ping") { send({ jsonrpc: "2.0", id, result: {} }); return; }

  if (method === "tools/list") {
    if (!gameUp && (await connect())) setUp(true);
    if (gameUp) {
      const r = await forward(msg);
      if (r) { send(r); return; }
    }
    send({ jsonrpc: "2.0", id, result: { tools: [STATUS_TOOL] } });
    return;
  }

  if (method === "tools/call") {
    const name = params && params.name;
    if (name === "sky_city_status") {
      if (!gameUp && (await connect())) setUp(true);
      const text = gameUp
        ? "Sky City is connected: the course tools are ready. Start with get_course_guide."
        : HELP;
      send({ jsonrpc: "2.0", id, result: { content: [{ type: "text", text }], isError: !gameUp } });
      return;
    }
    if (!gameUp && (await connect())) setUp(true);
    if (gameUp) {
      const r = await forward(msg);
      if (r) { send(r); return; }
    }
    send({ jsonrpc: "2.0", id, result: { content: [{ type: "text", text: HELP }], isError: true } });
    return;
  }

  // anything else: pass it on if we can
  if (gameUp) {
    const r = await forward(msg);
    if (r) { send(r); return; }
  }
  if (isRequest) send({ jsonrpc: "2.0", id, error: { code: -32603, message: HELP } });
}

// one message at a time, in order
let chain = Promise.resolve();
const rl = readline.createInterface({ input: process.stdin });
rl.on("line", (line) => {
  const t = line.trim();
  if (!t) return;
  let msg;
  try { msg = JSON.parse(t); } catch (e) { return; }
  const batch = Array.isArray(msg) ? msg : [msg];
  for (const m of batch) chain = chain.then(() => handle(m)).catch((e) => log("error:", e && e.message));
});
rl.on("close", () => { if (pollTimer) clearInterval(pollTimer); setTimeout(() => process.exit(0), 50); });
