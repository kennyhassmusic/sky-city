"""Capture review shots through the editor's MCP server (viewport captures, not HighResShot).

The live editor must be running with its MCP server (./launch.sh, or the editor started with
-ModelContextProtocolStartServer) and the level open. For each pose in a plan file (from
walkup_shots_ue.py --plan, or any {"poses": [[name, x, y, z, pitch, yaw], ...]} in Unreal cm and
degrees) it moves the level viewport camera there, waits for streaming, captures the viewport and
writes Saved/CityGen/shots/<tag>_<name>.png.

Run (plain Python 3, standard library only):
  python3 -I Scripts/city/mcp_capture.py --tag after [--plan Saved/CityGen/walkup_shots.json]
                                         [--only name1,name2] [--wait 6] [--url http://127.0.0.1:8000/mcp]
One call at a time: the MCP server runs on the editor's game thread.
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    env = os.environ.get("SKYCITY_ROOT")
    if env:
        return env
    d = _HERE
    while d and d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "SkyCity.uproject")):
            return d
        d = os.path.dirname(d)
    raise SystemExit("SkyCity.uproject not found")


class Mcp(object):
    """A minimal streamable-HTTP MCP client: initialize once, then tools/call."""

    def __init__(self, url):
        self.url = url
        self.session = None
        self.ids = 0
        reply, headers = self._post({"method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "mcp_capture", "version": "1"}}})
        self.session = headers.get("Mcp-Session-Id")
        self._post({"method": "notifications/initialized"}, notify=True)

    def _post(self, body, notify=False):
        body = dict(body, jsonrpc="2.0")
        if not notify:
            self.ids += 1
            body["id"] = self.ids
        request = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="POST", headers={
            "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
        if self.session:
            request.add_header("Mcp-Session-Id", self.session)
        with urllib.request.urlopen(request, timeout=600) as response:
            text = response.read().decode()
            headers = dict(response.headers)
        if notify or not text.strip():
            return None, headers
        if text.lstrip().startswith("data:") or "\ndata:" in text:
            text = [line[5:] for line in text.splitlines() if line.startswith("data:")][-1]
        return json.loads(text), headers

    def tool(self, name, arguments, toolset="EditorToolset.EditorAppToolset"):
        reply, _headers = self._post({"method": "tools/call", "params": {"name": "call_tool", "arguments": {
            "toolset_name": toolset, "tool_name": name, "arguments": arguments}}})
        return reply


def _image(reply):
    for item in (reply or {}).get("result", {}).get("content", []):
        if item.get("type") == "image" and item.get("data"):
            return item["data"]
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])["returnValue"]["image"]["data"]
            except (ValueError, KeyError, TypeError):
                continue
    return None


def main(argv=None):
    root = _root()
    parser = argparse.ArgumentParser(description="Viewport captures over the editor's MCP server.")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--plan", default=os.path.join(root, "Saved", "CityGen", "walkup_shots.json"))
    parser.add_argument("--only", default="")
    parser.add_argument("--wait", type=float, default=6.0, help="seconds for streaming after each move")
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    args = parser.parse_args(argv)
    with open(args.plan) as handle:
        poses = json.load(handle)["poses"]
    only = set(filter(None, args.only.split(",")))
    out_dir = os.path.join(root, "Saved", "CityGen", "shots")
    os.makedirs(out_dir, exist_ok=True)
    mcp = Mcp(args.url)
    failed = 0
    for name, x, y, z, pitch, yaw in poses:
        if only and name not in only:
            continue
        pose = {"location": {"x": x, "y": y, "z": z}, "rotation": {"pitch": pitch, "yaw": yaw, "roll": 0},
                "scale": {"x": 1, "y": 1, "z": 1}}
        mcp.tool("SetCameraTransform", {"transform": pose})
        time.sleep(args.wait)
        data = _image(mcp.tool("CaptureViewport", {"captureTransform": pose,
                                                   "annotations": {"gridSpacing": 0, "maxLabelDistance": 0}}))
        if not data:
            print("no image for", name)
            failed += 1
            continue
        path = os.path.join(out_dir, "%s_%s.png" % (args.tag, name))
        with open(path, "wb") as handle:
            handle.write(base64.b64decode(data))
        print("saved", path)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
