#!/usr/bin/env python3
"""A tiny command-line client for Sky City's course MCP server, for trying the tools by hand or from a script.
Standard library only. The game must be running with the LLM link on (course menu -> LLM link).

    python3 Scripts/course/mcp_cli.py tools                          # every tool: name, description, input schema
    python3 Scripts/course/mcp_cli.py call get_course_guide
    python3 Scripts/course/mcp_cli.py call new_course '{"near_player": true}'
    python3 Scripts/course/mcp_cli.py call add_pieces '{"pieces":[{"type":"straight","length":60}]}'
    python3 Scripts/course/mcp_cli.py call get_course '{"include_course": false}'
    python3 Scripts/course/mcp_cli.py --url http://127.0.0.1:47800/mcp call list_courses

It prints the tool's text reply. The exit code is 1 when the tool reported an error (isError), 2 when the server can't be reached.
"""
import argparse
import http.client
import json
import sys
import urllib.parse


def post(conn, path, payload, session=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session:
        h["Mcp-Session-Id"] = session
    conn.request("POST", path, json.dumps(payload), h)
    r = conn.getresponse()
    data = r.read()
    return r.status, r.getheader("Mcp-Session-Id"), (json.loads(data) if data else None)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:47800/mcp")
    ap.add_argument("what", choices=["tools", "call"])
    ap.add_argument("name", nargs="?", help="tool name (for call)")
    ap.add_argument("arguments", nargs="?", default="{}", help="the tool's arguments as JSON")
    a = ap.parse_args()
    u = urllib.parse.urlparse(a.url)
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=60)
    try:
        status, session, r = post(conn, u.path or "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "mcp_cli", "version": "1"}}})
    except OSError as e:
        print("Can't reach %s: %s\nIs the game running with the LLM link on?" % (a.url, e), file=sys.stderr)
        return 2
    post(conn, u.path or "/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
    if a.what == "tools":
        _, _, r = post(conn, u.path or "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session)
        for t in r["result"]["tools"]:
            print("== %s\n%s\ninput: %s\n" % (t["name"], t["description"], json.dumps(t["inputSchema"])))
        return 0
    if not a.name:
        ap.error("call needs a tool name")
    try:
        args = json.loads(a.arguments)
    except ValueError as e:
        ap.error("the arguments are not valid JSON: %s" % e)
    _, _, r = post(conn, u.path or "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": a.name, "arguments": args}}, session)
    if "error" in r:
        print("protocol error: %s" % json.dumps(r["error"]))
        return 1
    res = r["result"]
    print("".join(c.get("text", "") for c in res.get("content", [])))
    return 1 if res.get("isError") else 0


if __name__ == "__main__":
    sys.exit(main())
