#!/usr/bin/env python3
"""Smoke test for Sky City's course MCP server (the "LLM link" in the Course Builder).

Standard library only. Run it against a running game (or PIE) that has the LLM link on:

    python3 Scripts/course/mcp_smoke_test.py                 # http://127.0.0.1:47800/mcp
    python3 Scripts/course/mcp_smoke_test.py --url http://127.0.0.1:47800/mcp
    python3 Scripts/course/mcp_smoke_test.py --protocol-only # skip the tests that need the course model

It checks the transport (initialize, tools/list, ping, GET = 405, a bad Origin or Host = 403, the 2 MB limit, batches,
chunked bodies, sessions) and then walks the course tools: new_course, add_pieces, get_course, an invalid piece (must be
an error), save_course, list_courses, load_course. The course tools are reported as SKIP while the course model still
says "not implemented yet". It leaves one small saved course called "MCP smoke test" in the courses folder.

Exit code 0 = everything passed (or skipped), 1 = something failed, 2 = the server isn't reachable.
"""
import argparse
import http.client
import json
import sys
import urllib.parse

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results = []


def report(status, name, detail=""):
    results.append(status)
    print("%-5s %s%s" % (status, name, (": " + detail) if detail else ""))


def check(cond, name, detail=""):
    report(PASS if cond else FAIL, name, "" if cond else detail)
    return cond


class Client:
    def __init__(self, url):
        u = urllib.parse.urlparse(url)
        self.host, self.port, self.path = u.hostname, u.port or 80, u.path or "/mcp"
        self.session = None
        self.next_id = 1

    def raw(self, method, body=None, headers=None, path=None, chunked=False):
        """One HTTP request. Returns (status, headers dict lower-cased, body bytes)."""
        c = http.client.HTTPConnection(self.host, self.port, timeout=30)
        h = {} if headers is None else dict(headers)
        try:
            c.request(method, path or self.path, body=body, headers=h, encode_chunked=chunked)
            r = c.getresponse()
            data = r.read()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, data
        finally:
            c.close()

    def post(self, payload, extra=None, session=True, raw_body=None):
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if session and self.session:
            h["Mcp-Session-Id"] = self.session
        if extra:
            h.update(extra)
        body = raw_body if raw_body is not None else json.dumps(payload)
        status, hdr, data = self.raw("POST", body.encode() if isinstance(body, str) else body, h)
        parsed = None
        if data:
            try:
                parsed = json.loads(data)
            except ValueError:
                parsed = None
        return status, hdr, parsed

    def rpc(self, method, params=None, extra=None):
        msg = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            msg["params"] = params
        self.next_id += 1
        return self.post(msg, extra)

    def call(self, name, args=None):
        """tools/call. Returns (is_error, text, raw result)."""
        status, _, r = self.rpc("tools/call", {"name": name, "arguments": args or {}})
        if status != 200 or not r or "result" not in r:
            return True, "HTTP %s %s" % (status, json.dumps(r)[:300]), r
        res = r["result"]
        text = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        return bool(res.get("isError")), text, res

    def call_json(self, name, args=None):
        err, text, res = self.call(name, args)
        try:
            return err, json.loads(text)
        except ValueError:
            return err, text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:47800/mcp")
    ap.add_argument("--protocol-only", action="store_true", help="skip the tests that need the course model")
    args = ap.parse_args()
    c = Client(args.url)
    print("Testing %s\n" % args.url)

    try:
        status, hdr, body = c.raw("OPTIONS", headers={})
    except OSError as e:
        print("Can't reach the server: %s\nIs the game running with the LLM link switched on (course menu -> LLM link)?" % e)
        return 2

    # ---- transport ----
    status, hdr, body = c.raw("GET", headers={"Accept": "text/event-stream"})
    check(status == 405, "GET /mcp is 405 (no SSE stream)", "got %s" % status)
    check("post" in hdr.get("allow", "").lower(), "405 carries an Allow header", hdr.get("allow", "(none)"))

    status, _, _ = c.raw("GET", path="/nope")
    check(status == 404, "unknown path is 404", "got %s" % status)

    status, _, _ = c.raw("POST", b'{"jsonrpc":"2.0","id":1,"method":"ping"}', {"Content-Type": "text/plain"})
    check(status == 415, "POST without application/json is 415", "got %s" % status)

    ping = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
    for origin in ["https://evil.example", "http://evil.example:47800", "null", "http://localhost.evil.com",
                   "http://127.0.0.1.evil.com", "http://user@localhost", "file://", "http://192.168.1.5:3000"]:
        status, _, _ = c.raw("POST", ping, {"Content-Type": "application/json", "Origin": origin})
        check(status == 403, "Origin %r is refused with 403" % origin, "got %s" % status)
    for origin in ["http://localhost", "http://localhost:3000", "https://127.0.0.1:8443", "http://[::1]:6274"]:
        status, hdr, _ = c.raw("POST", ping, {"Content-Type": "application/json", "Origin": origin})
        check(status == 200 and hdr.get("access-control-allow-origin") == origin,
              "Origin %r is allowed" % origin, "got %s %s" % (status, hdr.get("access-control-allow-origin")))
    status, _, _ = c.raw("OPTIONS", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    check(status == 403, "CORS preflight from a bad Origin is 403", "got %s" % status)
    status, hdr, _ = c.raw("OPTIONS", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    check(status == 204 and "access-control-allow-methods" in hdr, "CORS preflight from localhost is 204", "got %s" % status)

    for host in ["evil.example", "evil.example:47800", "localhost.evil.com", "127.0.0.1.evil.com:47800"]:
        status, _, _ = c.raw("POST", ping, {"Content-Type": "application/json", "Host": host})
        check(status == 403, "Host %r is refused with 403 (DNS rebinding)" % host, "got %s" % status)
    status, _, _ = c.raw("POST", ping, {"Content-Type": "application/json", "Host": "localhost:47800"})
    check(status == 200, "Host localhost:47800 is accepted", "got %s" % status)

    big = b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"pad":"' + b"x" * (2 * 1024 * 1024 + 10) + b'"}}'
    try:
        status, _, _ = c.raw("POST", big, {"Content-Type": "application/json"})
    except OSError as e:
        status = "connection error (%s)" % e
    check(status == 413, "a body over 2 MB is refused with 413", "got %s" % status)

    status, _, r = c.post(None, raw_body="{not json")
    check(status == 400 and r and r.get("error", {}).get("code") == -32700, "malformed JSON is 400 / -32700", "got %s %s" % (status, r))

    # ---- initialize ----
    status, hdr, r = c.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                          "clientInfo": {"name": "mcp_smoke_test", "version": "1"}})
    ok = status == 200 and r and "result" in r
    check(ok, "initialize (2025-06-18)", "got %s %s" % (status, r))
    if ok:
        res = r["result"]
        check(res.get("protocolVersion") == "2025-06-18", "protocol version negotiated", res.get("protocolVersion"))
        check(res.get("serverInfo", {}).get("name") == "sky-city-courses", "serverInfo.name is sky-city-courses", json.dumps(res.get("serverInfo")))
        check(bool(res.get("serverInfo", {}).get("version")), "serverInfo.version is set")
        check("tools" in res.get("capabilities", {}), "capabilities has tools")
        check("get_course_guide" in res.get("instructions", ""), "instructions point at get_course_guide")
        c.session = hdr.get("mcp-session-id")
        check(bool(c.session), "initialize issues an Mcp-Session-Id")
    status, _, r = c.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
    check(status == 200 and r["result"]["protocolVersion"] == "2025-03-26", "initialize (2025-03-26)")
    status, _, r = c.rpc("initialize", {"protocolVersion": "2099-01-01", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
    check(status == 200 and r["result"]["protocolVersion"] == "2025-06-18", "an unknown version gets the latest we support")

    status, hdr, body = c.raw("POST", json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode(),
                              {"Content-Type": "application/json", "Mcp-Session-Id": c.session or ""})
    check(status == 202 and not body, "notifications/initialized is 202 with no body", "got %s %r" % (status, body[:50]))

    status, _, r = c.rpc("ping")
    check(status == 200 and r.get("result") == {}, "ping")
    status, _, r = c.post({"jsonrpc": "2.0", "id": "abc-1", "method": "ping"})
    check(r and r.get("id") == "abc-1", "string ids echo back")
    status, _, r = c.post({"jsonrpc": "2.0", "id": 7, "method": "no/such/method"})
    check(status == 200 and r.get("error", {}).get("code") == -32601, "unknown method is -32601")
    status, _, r = c.rpc("tools/call", {"name": "no_such_tool", "arguments": {}})
    check(status == 200 and r.get("error", {}).get("code") == -32602, "unknown tool is -32602")
    status, _, r = c.rpc("ping", extra={"MCP-Protocol-Version": "1999-01-01"})
    check(status == 400, "an unsupported MCP-Protocol-Version header is 400", "got %s" % status)
    status, _, r = c.rpc("ping", extra={"MCP-Protocol-Version": "2025-06-18"})
    check(status == 200, "a supported MCP-Protocol-Version header is fine")
    status, _, r = c.post([{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "id": 2, "method": "ping"},
                           {"jsonrpc": "2.0", "method": "notifications/initialized"}])
    check(status == 200 and isinstance(r, list) and len(r) == 2, "a batch of 2 requests + 1 notification returns 2 responses", "got %s %s" % (status, r))
    # a chunked request body (no Content-Length)
    status, _, data = c.raw("POST", iter([b'{"jsonrpc":"2.0",', b'"id":5,"method":"ping"}']),
                            {"Content-Type": "application/json"}, chunked=True)
    check(status == 200 and b'"id":5' in data, "a chunked request body works", "got %s %r" % (status, data[:80]))
    # a session that was never opened (e.g. the game restarted) is still served; one that was ended is not
    status, _, r = c.post({"jsonrpc": "2.0", "id": 9, "method": "ping"}, extra={"Mcp-Session-Id": "left-over-from-an-old-run"})
    check(status == 200, "an unknown session id is accepted (the game may have restarted)", "got %s" % status)

    # ---- tools/list ----
    status, _, r = c.rpc("tools/list")
    tools = r["result"]["tools"] if status == 200 and r and "result" in r else []
    names = [t["name"] for t in tools]
    wanted = ["get_course_guide", "get_course", "set_course", "add_pieces", "remove_pieces", "update_piece", "new_course",
              "list_courses", "save_course", "load_course", "get_player", "start_race", "stop_race", "get_results"]
    check(all(n in names for n in wanted), "tools/list has all %d tools" % len(wanted), "missing %s" % [n for n in wanted if n not in names])
    check(all(t.get("description") and t.get("inputSchema", {}).get("type") == "object" for t in tools), "every tool has a description and an object inputSchema")
    check(all(len(t.get("description", "")) > 40 for t in tools), "descriptions are real sentences")

    if args.protocol_only:
        print("\n--protocol-only: skipping the course tools")
        return summary()

    # ---- the course tools ----
    err, guide, _ = c.call("get_course_guide")
    check(not err and "add_pieces" in guide, "get_course_guide returns the guide", guide[:120])
    if "not implemented yet" in guide:
        report(SKIP, "the course model isn't written yet (guide says 'not implemented yet'): course-tool tests skipped")
        return summary()

    err, player = c.call_json("get_player")
    if err:
        report(SKIP, "get_player", "no player car in this world (%s)" % str(player)[:80])
        near = False
    else:
        check(all(k in player for k in ("x", "y", "z", "heading_deg", "speed_mph", "build_area")), "get_player has position, heading, speed and build area", json.dumps(player)[:200])
        near = True

    err, res = c.call_json("new_course", {"name": "MCP smoke test", "near_player": near})
    if not check(not err and isinstance(res, dict) and res.get("valid") is True, "new_course makes a valid course", str(res)[:300]):
        return summary()
    check(isinstance(res.get("ends"), list) and res["ends"] and res["ends"][0].get("path") == "pieces", "new_course reports the end frame of the main line", json.dumps(res.get("ends"))[:200])

    err, res = c.call_json("add_pieces", {"pieces": [{"type": "straight", "length": 60}, {"type": "booster", "length": 10},
                                                       {"type": "curve", "angle": 90, "radius": 40}, {"type": "straight", "length": 40},
                                                       {"type": "checkpoint"}]})
    if check(not err and isinstance(res, dict) and res.get("valid") is True, "add_pieces adds 5 pieces", str(res)[:400]):
        check(res.get("piece_count") == 6, "piece_count is start + 5 = 6", str(res.get("piece_count")))
    err, res = c.call_json("get_course")
    if check(not err and isinstance(res, dict) and "course" in res, "get_course returns the course and the facts", str(res)[:300]):
        check(len(res["course"].get("pieces", [])) == 6, "the course JSON has 6 pieces", str(len(res["course"].get("pieces", []))))
        check(res.get("length_m", 0) > 100, "length_m is plausible", str(res.get("length_m")))
        for key in ("valid", "errors", "warnings", "bounds", "min_z", "max_z", "gates", "splits", "ends", "build_area"):
            check(key in res, "get_course has '%s'" % key)

    err, text, _ = c.call("add_pieces", {"pieces": [{"type": "curve", "angle": 90, "radius": 1}]})
    check(err and "radius" in text and "NOT" in text, "an invalid piece is an isError result that names the problem", text[:300])
    err, text, _ = c.call("add_pieces", {"pieces": [{"type": "banana"}]})
    check(err and "banana" in text, "an unknown piece type is an isError result", text[:300])
    err, res = c.call_json("get_course", {"include_course": False})
    check(not err and res.get("piece_count") == 6, "a rejected add leaves the course unchanged", str(res)[:200])

    err, res = c.call_json("update_piece", {"path": "pieces[3]", "piece": {"radius": 50}})
    check(not err and res.get("valid") is True, "update_piece changes one piece", str(res)[:300])
    err, res = c.call_json("update_piece", {"path": "pieces[3]", "piece": {"radius": 45}, "compact": True})
    check(not err and "ends" in res and "gates" not in res and "bounds" not in res, "compact: true leaves the repeated facts out", str(res)[:200])
    err, text, _ = c.call("update_piece", {"path": "pieces[99]", "piece": {"radius": 50}})
    check(err and "pieces[99]" in text, "update_piece with a bad path explains it", text[:200])
    err, res = c.call_json("update_piece", {"path": "course", "piece": {"opponents": 1}})
    check(not err and res.get("valid") is True, "update_piece with path 'course' changes course settings", str(res)[:300])
    err, res = c.call_json("get_course", {"include_course": True})
    check(not err and res["course"].get("opponents") == 1, "...and the setting is in the course", str(res)[:200])
    check(not err and "ground_z" in res and "start" in res, "get_course has ground_z and start")
    err, text, _ = c.call("update_piece", {"path": "course", "piece": {"laps": 3}})
    check(err and "lap" in text.lower(), "laps above 1 on an open course is refused with a reason", text[:200])
    course = res["course"]
    del course["start"]["z"]
    err, res2 = c.call_json("set_course", {"course": course})
    check(not err and res2.get("valid") is True and "no z" in res2.get("summary", ""), "set_course fills in a missing start.z", str(res2)[:300])
    err, res = c.call_json("remove_pieces", {"count": 1})
    check(not err and res.get("piece_count") == 5, "remove_pieces takes the last piece off", str(res)[:300])

    err, res = c.call_json("save_course", {"name": "MCP smoke test", "overwrite": True})
    check(not err and res.get("ok") is True, "save_course", str(res)[:300])
    err, text, _ = c.call("save_course", {"name": "MCP smoke test"})
    check(err and "overwrite" in text, "saving over an existing course needs overwrite: true", text[:200])
    err, res = c.call_json("list_courses")
    check(not err and any(n.lower() == "mcp smoke test" for n in res.get("courses", [])), "list_courses shows it", str(res)[:300])
    c.call_json("remove_pieces", {"count": 1})
    err, res = c.call_json("load_course", {"name": "MCP smoke test"})
    check(not err and res.get("piece_count") == 5, "load_course brings the saved course back", str(res)[:300])
    err, text, _ = c.call("load_course", {"name": "../../etc/passwd"})
    check(err, "a path-like course name is refused", text[:200])

    err, res = c.call_json("get_results")
    check(not err and "results" in res, "get_results", str(res)[:200])
    err, res = c.call_json("stop_race")
    check(not err, "stop_race with no race running is harmless", str(res)[:200])

    # ---- sessions ----
    if c.session:
        status, _, _ = c.raw("DELETE", headers={"Mcp-Session-Id": c.session})
        check(status in (200, 204), "DELETE ends the session", "got %s" % status)
        status, _, r = c.rpc("ping")
        check(status == 404, "a request on the ended session is 404", "got %s" % status)
    return summary()


def summary():
    n_fail = results.count(FAIL)
    print("\n%d passed, %d failed, %d skipped" % (results.count(PASS), n_fail, results.count(SKIP)))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
