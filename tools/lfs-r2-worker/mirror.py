#!/usr/bin/env python3
"""Copies Sky City's Git LFS files into R2, behind the download server in this folder.

GitHub stays the source of truth: every LFS upload (the maintainer's and contributors') goes to GitHub first, and
this script makes sure R2 has a copy, so clones download from R2 for free. It only uploads what R2 is missing, and
R2 checks every upload against the file's SHA-256, so running it twice is harmless.

  python3 tools/lfs-r2-worker/mirror.py --all            every LFS file in the history, read from .git/lfs (maintainer)
  python3 tools/lfs-r2-worker/mirror.py --all --check    only report what R2 is missing (or has with the wrong size)
  python3 tools/lfs-r2-worker/mirror.py --source github --range BEFORE AFTER     what the lfs-mirror Action runs

The upload password comes from $LFS_UPLOAD_TOKEN, or from git's credential store (the macOS keychain), where
rotate-upload-token.sh puts it. With --source github, $GITHUB_TOKEN (if set) is used to download from GitHub.
Only the Python standard library is used.
"""

import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

SERVER = "https://sky-city-lfs.goodmorrow.workers.dev/sky-city"
GITHUB_LFS = "https://github.com/kennyhassmusic/sky-city.git/info/lfs"
LFS_JSON = "application/vnd.git-lfs+json"
POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"
BATCH = 40  # the server checks at most 40 files per request
WORKERS = 8
ZERO_SHA = "0" * 40

print_lock = threading.Lock()


def say(*args):
    with print_lock:
        print(*args, flush=True)


def git(*args, data=None):
    return subprocess.run(["git", *args], check=True, capture_output=True, input=data).stdout


# ----------------------------------------------------------------------------------------- which files to mirror


def pointer_blobs(rev_args):
    """Returns {oid: size} for every LFS pointer among the blobs that `git rev-list --objects <rev_args>` lists."""
    listing = git("rev-list", "--objects", *rev_args).decode().split("\n")
    shas = "\n".join(line.split(" ", 1)[0] for line in listing if line).encode() + b"\n"
    checks = git("cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)", data=shas).decode().split("\n")
    small = []  # pointers are ~130 bytes
    for line in checks:
        parts = line.split()
        if len(parts) == 3 and parts[1] == "blob" and int(parts[2]) < 1024:
            small.append(parts[0])
    if not small:
        return {}
    raw = git("cat-file", "--batch", data=("\n".join(small) + "\n").encode())
    found, pos = {}, 0
    while pos < len(raw):
        end = raw.index(b"\n", pos)
        header = raw[pos:end].split()
        pos = end + 1
        if len(header) < 3:  # "<sha> missing"
            continue
        size = int(header[2])
        body, pos = raw[pos:pos + size], pos + size + 1
        if not body.startswith(POINTER_PREFIX):
            continue
        fields = dict(line.split(" ", 1) for line in body.decode("utf-8", "replace").splitlines() if " " in line)
        oid = fields.get("oid", "").removeprefix("sha256:")
        if len(oid) == 64 and fields.get("size", "").isdigit():
            found[oid] = int(fields["size"])
    return found


def objects_for(args):
    if args.all:
        return pointer_blobs(["--all"])
    before, after = args.range
    if before == ZERO_SHA or subprocess.run(["git", "cat-file", "-e", f"{before}^{{commit}}"],
                                            capture_output=True).returncode != 0:
        return pointer_blobs([after])  # new branch or rewritten history: check everything reachable
    return pointer_blobs([f"{before}..{after}"])


# ------------------------------------------------------------------------------------------------------- HTTP


def use_system_certificates():
    # python.org's Python on macOS ships without root certificates until "Install Certificates" is run; the system's
    # own bundle works just as well.
    context = ssl.create_default_context()
    if os.path.exists("/etc/ssl/cert.pem"):
        context.load_verify_locations("/etc/ssl/cert.pem")
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPSHandler(context=context)))


def http(method, url, body=None, headers=None, timeout=120):
    """Small request helper with retries for busy servers and dropped connections. Returns (status, bytes)."""
    for attempt in range(5):
        try:
            data = body() if callable(body) else body
            # Cloudflare turns away Python's default User-Agent (error 1010).
            req = urllib.request.Request(url, data=data, method=method,
                                         headers={"User-Agent": "sky-city-lfs-mirror", **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as err:
            text = err.read()[:400]
            if err.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(int(err.headers.get("Retry-After") or 0) or 2 ** attempt)
                continue
            raise RuntimeError(f"{method} {url.split('?')[0]} -> HTTP {err.code}: {text!r}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            if attempt < 4:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"{method} {url.split('?')[0]} failed: {err}") from None
    raise AssertionError("unreachable")


def lfs_batch(url, operation, objects, auth):
    body = json.dumps({"operation": operation, "transfers": ["basic"], "hash_algo": "sha256",
                       "objects": [{"oid": oid, "size": size} for oid, size in objects]}).encode()
    headers = {"Accept": LFS_JSON, "Content-Type": LFS_JSON}
    if auth:
        headers["Authorization"] = auth
    _, data = http("POST", url + "/objects/batch", body, headers)
    return json.loads(data)["objects"]


def basic(user, password):
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def upload_token():
    token = os.environ.get("LFS_UPLOAD_TOKEN", "").strip()
    if token:
        return token
    host = urllib.parse.urlsplit(SERVER).hostname
    res = subprocess.run(["git", "credential", "fill"], input=f"protocol=https\nhost={host}\nusername=upload\n\n",
                         capture_output=True, text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    for line in res.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    sys.exit("No upload password: set LFS_UPLOAD_TOKEN, or run tools/lfs-r2-worker/rotate-upload-token.sh first.")


# ---------------------------------------------------------------------------------------------- file sources


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class LocalSource:
    """Reads objects from this clone's .git/lfs/objects (shared by all worktrees)."""

    def __init__(self):
        common = git("rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip()
        self.root = os.path.join(common, "lfs", "objects")

    def prepare(self, objects):
        return {}

    def fetch(self, oid, size, _hint, _tmp):
        path = os.path.join(self.root, oid[:2], oid[2:4], oid)
        if not os.path.exists(path):
            raise RuntimeError("not in .git/lfs (run `git lfs fetch --all` first)")
        return path


class GitHubSource:
    """Downloads objects from GitHub's LFS server (where pushes and pull requests put them)."""

    def __init__(self):
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        self.auth = basic("x-access-token", token) if token else None

    def prepare(self, objects):
        hints = {}
        for start in range(0, len(objects), 100):
            for entry in lfs_batch(GITHUB_LFS, "download", objects[start:start + 100], self.auth):
                hints[entry["oid"]] = entry
        return hints

    def fetch(self, oid, size, hint, tmp):
        action = (hint or {}).get("actions", {}).get("download")
        if not action:
            raise RuntimeError(f"GitHub doesn't have it: {(hint or {}).get('error')}")
        path = os.path.join(tmp, oid)
        req = urllib.request.Request(action["href"],
                                     headers={"User-Agent": "sky-city-lfs-mirror", **(action.get("header") or {})})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=300) as res, open(path, "wb") as out:
                    shutil.copyfileobj(res, out, 1 << 20)
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        return path


# ----------------------------------------------------------------------------------------------------- mirror


def upload_one(oid, size, actions, source, hint, tmp, auth):
    path = source.fetch(oid, size, hint, tmp)
    if os.path.getsize(path) != size or sha256_of(path) != oid:
        raise RuntimeError("the source copy is damaged (size or SHA-256 doesn't match)")
    up = actions["upload"]
    headers = {**(up.get("header") or {}), "Content-Type": "application/octet-stream", "Content-Length": str(size)}
    opened = []

    def body():
        f = open(path, "rb")
        opened.append(f)
        return f

    try:
        http("PUT", up["href"], body, headers, timeout=600)
    finally:
        for f in opened:
            f.close()
    if "verify" in actions:
        ver = actions["verify"]
        http("POST", ver["href"], json.dumps({"oid": oid, "size": size}).encode(),
             {**(ver.get("header") or {}), "Content-Type": LFS_JSON, "Accept": LFS_JSON})
    if isinstance(source, GitHubSource):
        os.remove(path)


def mirror_chunk(chunk, args, source, auth, tmp, totals):
    try:
        entries = lfs_batch(SERVER, "upload", chunk, auth)
    except Exception as err:  # keep going; the summary lists every failure
        for oid, _ in chunk:
            totals.fail(oid, str(err))
        return
    todo = [e for e in entries if e.get("actions")]
    for e in entries:
        if e.get("error"):
            totals.fail(e["oid"], e["error"].get("message"))
    totals.add("present", len(entries) - len(todo) - sum(1 for e in entries if e.get("error")))
    if args.check:
        for e in todo:
            totals.fail(e["oid"], "missing from R2")
        return
    try:
        hints = source.prepare([(e["oid"], e["size"]) for e in todo])
    except Exception as err:
        for e in todo:
            totals.fail(e["oid"], str(err))
        return
    for e in todo:
        try:
            upload_one(e["oid"], e["size"], e["actions"], source, hints.get(e["oid"]), tmp, auth)
            totals.add("uploaded", 1, e["size"])
        except Exception as err:  # keep going; the summary lists every failure
            totals.fail(e["oid"], str(err))


class Totals:
    def __init__(self, total):
        self.total, self.counts, self.bytes, self.failures = total, {"present": 0, "uploaded": 0}, 0, []
        self.lock = threading.Lock()

    def add(self, key, n, nbytes=0):
        with self.lock:
            self.counts[key] += n
            self.bytes += nbytes
            done = self.counts["present"] + self.counts["uploaded"] + len(self.failures)
            if key == "uploaded" and self.counts["uploaded"] % 100 == 0:
                say(f"  {done}/{self.total} checked, {self.counts['uploaded']} uploaded ({self.bytes / 1e6:.0f} MB)")

    def fail(self, oid, why):
        with self.lock:
            self.failures.append((oid, why))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--all", action="store_true", help="every LFS file reachable from any branch or tag")
    what.add_argument("--range", nargs=2, metavar=("BEFORE", "AFTER"), help="files added between two commits")
    parser.add_argument("--source", choices=["local", "github"], default="local",
                        help="where to read missing files from (default: this clone's .git/lfs)")
    parser.add_argument("--check", action="store_true", help="only report what R2 is missing")
    args = parser.parse_args()

    os.chdir(git("rev-parse", "--show-toplevel").decode().strip())
    use_system_certificates()
    objects = sorted(objects_for(args).items())
    total_bytes = sum(size for _, size in objects)
    say(f"{len(objects)} LFS files ({total_bytes / 1e6:.0f} MB) to {'check' if args.check else 'mirror'}.")
    if not objects:
        return 0

    auth = basic("upload", upload_token())
    source = GitHubSource() if args.source == "github" else LocalSource()
    totals = Totals(len(objects))
    chunks = [objects[i:i + BATCH] for i in range(0, len(objects), BATCH)]
    with tempfile.TemporaryDirectory(prefix="lfs-mirror-") as tmp, \
            concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        for future in [pool.submit(mirror_chunk, c, args, source, auth, tmp, totals) for c in chunks]:
            future.result()

    say(f"R2 already had {totals.counts['present']}, uploaded {totals.counts['uploaded']} "
        f"({totals.bytes / 1e6:.1f} MB), problems: {len(totals.failures)}.")
    for oid, why in totals.failures[:30]:
        say(f"  {oid}: {why}")
    if len(totals.failures) > 30:
        say(f"  ...and {len(totals.failures) - 30} more")
    return 1 if totals.failures else 0


if __name__ == "__main__":
    sys.exit(main())
