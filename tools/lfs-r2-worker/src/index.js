// Sky City's Git LFS server: a Cloudflare Worker in front of the R2 bucket that holds the repo's art.
//
// - Downloads are public. The Worker answers git-lfs "batch" requests with short-lived signed links straight to R2,
//   so file bytes never pass through it (the free plan allows 100,000 Worker requests a day; a full clone needs ~50).
// - Uploads need UPLOAD_TOKEN, which only the lfs-mirror GitHub Action and the maintainer's keychain have.
//   Contributors keep uploading their art to their own fork on GitHub; the Action copies it here after a merge.
// - Lock listing is passed through to GitHub, where file locks live.
//
// Protocol: https://github.com/git-lfs/git-lfs/blob/main/docs/api/batch.md
// Setup, costs and secret rotation: docs/MAINTAINER_SETUP.md

const REPO = "sky-city"; // URL path (/sky-city/objects/batch) and key prefix in the bucket (sky-city/<oid>)
const LFS_JSON = "application/vnd.git-lfs+json";
const LINK_TTL = 7200; // signed links stay valid for 2 hours...
const CLIENT_TTL = 3600; // ...git-lfs is told 1 hour, so it asks for fresh ones well before they run out
const MAX_CHECKS = 40; // the free plan allows 50 storage/network calls per request
const MAX_OBJECTS = 1000;
const MAX_SIZE = 5 * 1024 ** 3; // R2's limit for a single upload
const OID = /^[0-9a-f]{64}$/;
const DOCS = "https://github.com/kennyhassmusic/sky-city/blob/main/CONTRIBUTING.md";

const UPLOAD_HELP =
  "Sky City's LFS server only serves downloads. To send new art in a pull request, store it in your fork on GitHub " +
  "by running this once in your clone, then push again:\n" +
  "  git config lfs.pushurl https://github.com/YOUR-GITHUB-NAME/sky-city.git/info/lfs\n" +
  "(Maintainers use kennyhassmusic as the name.)";
const LOCK_HELP =
  "File locks are kept on GitHub and need write access to kennyhassmusic/sky-city. Maintainers run this once:\n" +
  "  git config lfs.pushurl https://github.com/kennyhassmusic/sky-city.git/info/lfs\n" +
  "Contributors: say in the issue which assets you'll touch and a maintainer will hold the lock.";

export default {
  async fetch(request, env) {
    try {
      return await route(request, env);
    } catch (err) {
      if (err instanceof Response) return err;
      console.error("unhandled", err && err.stack ? err.stack : String(err));
      return lfsError(500, "Internal error in the Sky City LFS server. Please try again.");
    }
  },
};

async function route(request, env) {
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, "");
  const base = `/${REPO}`;

  if (request.method === "GET" && (path === "" || path === base)) {
    return new Response(
      "Sky City Git LFS downloads (Cloudflare R2).\n" +
        "Clone https://github.com/kennyhassmusic/sky-city with Git LFS installed and this server is used automatically.\n",
      { headers: { "Content-Type": "text/plain; charset=utf-8" } },
    );
  }
  if (path === `${base}/objects/batch`) {
    return request.method === "POST" ? batch(request, env) : notAllowed("POST");
  }
  if (path === `${base}/objects/verify`) {
    return request.method === "POST" ? verify(request, env) : notAllowed("POST");
  }
  if (path === `${base}/locks` && request.method === "GET") {
    return githubLocks(request, url, env);
  }
  if (path === `${base}/locks/verify` && request.method === "POST") {
    // Pre-push asks this before every push whose LFS uploads would come here. Nothing is locked on this server.
    return lfsJson(200, { ours: [], theirs: [], next_cursor: "" });
  }
  if (path.startsWith(`${base}/locks`)) {
    return lfsError(403, LOCK_HELP);
  }
  return lfsError(404, "Not found. The LFS endpoint is /sky-city.");
}

// ---------------------------------------------------------------------------------------------------- batch API

async function batch(request, env) {
  const uploader = await isUploader(request, env);
  if (!uploader && !(await allowed(env.BATCH_LIMIT, request))) return tooMany();

  const body = await readJson(request);
  const { operation, objects } = body;
  if (operation !== "download" && operation !== "upload") {
    return lfsError(422, "operation must be 'download' or 'upload'.");
  }
  if (!Array.isArray(objects)) return lfsError(422, "objects must be a list.");
  if (objects.length > MAX_OBJECTS) return lfsError(413, `At most ${MAX_OBJECTS} objects per batch.`);
  if (body.hash_algo && body.hash_algo !== "sha256") return lfsError(409, "Only sha256 is supported.");
  if (Array.isArray(body.transfers) && body.transfers.length && !body.transfers.includes("basic")) {
    return lfsError(422, "Only the 'basic' transfer is supported.");
  }
  if (!env.R2_ACCESS_KEY_ID || !env.R2_SECRET_ACCESS_KEY) {
    return lfsError(503, "The Sky City LFS server is not fully set up yet. Please try again later.");
  }

  if (operation === "upload") {
    if (!uploader) return lfsError(403, UPLOAD_HELP);
    return lfsJson(200, { transfer: "basic", hash_algo: "sha256", objects: await planUploads(objects, request, env) });
  }
  return lfsJson(200, {
    transfer: "basic",
    hash_algo: "sha256",
    objects: await planDownloads(objects, request, env, uploader),
  });
}

async function planDownloads(objects, request, env, uploader) {
  const sign = await linkSigner(env, new Date());
  const out = new Array(objects.length);
  const valid = validate(objects, out);

  // Small batches (an incremental pull, checking out a pull request) are checked file by file, and anything not in
  // R2 yet comes from GitHub instead: the mirror runs a minute or two after a merge, and pull-request art lives only
  // on GitHub. Big batches (a fresh clone) skip the checks to stay inside the free plan's 50 calls per request.
  const missing = [];
  if (valid.length <= MAX_CHECKS && (uploader || (await allowed(env.CHECK_LIMIT, request)))) {
    const heads = await Promise.all(valid.map((i) => env.BUCKET.head(keyFor(objects[i].oid)).catch(() => "error")));
    heads.forEach((head, n) => {
      const i = valid[n];
      if (head === null || (head !== "error" && head.size !== objects[i].size)) missing.push(i);
    });
  }
  const skip = new Set(missing);
  for (const i of valid) {
    if (skip.has(i)) continue;
    const { oid, size } = objects[i];
    out[i] = {
      oid,
      size,
      authenticated: true,
      actions: { download: { href: sign("GET", keyFor(oid)), expires_in: CLIENT_TTL } },
    };
  }
  if (missing.length) {
    const found = await fromGitHub(
      missing.map((i) => objects[i]),
      env,
    );
    for (const i of missing) {
      const { oid, size } = objects[i];
      out[i] = found.get(oid) || {
        oid,
        size,
        error: { code: 404, message: "Not on the server yet. If this was just merged, try again in a few minutes." },
      };
    }
  }
  return out;
}

async function planUploads(objects, request, env) {
  const sign = await linkSigner(env, new Date());
  const out = new Array(objects.length);
  const valid = validate(objects, out);
  const checked = valid.slice(0, MAX_CHECKS); // anything past the limit is simply uploaded again (same bytes)
  const heads = await Promise.all(checked.map((i) => env.BUCKET.head(keyFor(objects[i].oid)).catch(() => null)));
  const present = new Set(checked.filter((i, n) => heads[n] && heads[n].size === objects[i].size));
  const verifyHref = `${new URL(request.url).origin}/${REPO}/objects/verify`;
  const auth = request.headers.get("Authorization");

  for (const i of valid) {
    const { oid, size } = objects[i];
    if (present.has(i)) {
      out[i] = { oid, size }; // already there: no actions means "nothing to do"
      continue;
    }
    const checksum = oidBase64(oid); // R2 rejects the upload if the bytes don't hash to the object ID
    out[i] = {
      oid,
      size,
      authenticated: true,
      actions: {
        upload: {
          href: sign("PUT", keyFor(oid), checksum),
          header: { "x-amz-checksum-sha256": checksum },
          expires_in: CLIENT_TTL,
        },
        verify: { href: verifyHref, header: { Authorization: auth }, expires_in: CLIENT_TTL },
      },
    };
  }
  return out;
}

function validate(objects, out) {
  const valid = [];
  objects.forEach((o, i) => {
    const oid = o && typeof o.oid === "string" ? o.oid : "";
    const size = o && Number.isSafeInteger(o.size) ? o.size : -1;
    if (!OID.test(oid)) out[i] = { oid, size: Math.max(size, 0), error: { code: 422, message: "Invalid object ID" } };
    else if (size < 0 || size > MAX_SIZE) out[i] = { oid, size: 0, error: { code: 422, message: "Invalid size" } };
    else valid.push(i);
  });
  return valid;
}

// Asks GitHub's own LFS server for files that aren't in R2 yet. Public repo, so no credentials are involved.
async function fromGitHub(objects, env) {
  const found = new Map();
  try {
    const res = await fromGitHubApi(`https://github.com/${env.GITHUB_REPO}.git/info/lfs/objects/batch`, {
      method: "POST",
      headers: { Accept: LFS_JSON, "Content-Type": LFS_JSON, "User-Agent": "sky-city-lfs-worker" },
      body: JSON.stringify({
        operation: "download",
        transfers: ["basic"],
        hash_algo: "sha256",
        objects: objects.map(({ oid, size }) => ({ oid, size })),
      }),
    });
    if (!res.ok) {
      console.error("github batch", res.status);
      return found;
    }
    const data = await res.json();
    for (const o of data.objects || []) {
      const download = o && o.actions && o.actions.download;
      if (!o || !OID.test(o.oid)) continue;
      if (download && typeof download.href === "string" && download.href.startsWith("https://")) {
        found.set(o.oid, { oid: o.oid, size: o.size, authenticated: true, actions: { download } });
      } else if (o.error) {
        found.set(o.oid, { oid: o.oid, size: o.size, error: o.error });
      }
    }
  } catch (err) {
    console.error("github batch failed", String(err));
  }
  return found;
}

// ------------------------------------------------------------------------------------------- verify and locks

async function verify(request, env) {
  if (!(await isUploader(request, env))) {
    if (!(await allowed(env.BATCH_LIMIT, request))) return tooMany();
    return lfsError(403, "Only the Sky City mirror can verify uploads.");
  }
  const { oid, size } = await readJson(request);
  if (typeof oid !== "string" || !OID.test(oid) || !Number.isSafeInteger(size)) {
    return lfsError(422, "Invalid object.");
  }
  const head = await env.BUCKET.head(keyFor(oid));
  if (!head) return lfsError(404, "The upload did not arrive in R2. Push again.");
  if (head.size !== size) {
    await env.BUCKET.delete(keyFor(oid));
    return lfsError(422, `Upload has ${head.size} bytes, expected ${size}. The bad copy was removed; push again.`);
  }
  return new Response(null, { status: 200 });
}

async function githubLocks(request, url, env) {
  if (!(await allowed(env.BATCH_LIMIT, request))) return tooMany();
  const res = await fromGitHubApi(`https://github.com/${env.GITHUB_REPO}.git/info/lfs/locks${url.search}`, {
    headers: { Accept: LFS_JSON, "User-Agent": "sky-city-lfs-worker" },
  });
  if (!res.ok && !(res.headers.get("Content-Type") || "").includes("json")) {
    return lfsError(503, "GitHub's lock list is busy right now. Please try again in a minute.", { "Retry-After": "60" });
  }
  return new Response(res.body, { status: res.status, headers: { "Content-Type": LFS_JSON } });
}

// Workers share outgoing addresses, so GitHub sometimes rate-limits one; a second try usually goes out from another.
async function fromGitHubApi(url, init) {
  let res = await fetch(url, init);
  if (res.status === 429 || res.status >= 500) res = await fetch(url, init);
  return res;
}

// -------------------------------------------------------------------------------------- signed links (SigV4)

const enc = new TextEncoder();
let keyCache = { scope: "", key: null };

// Returns sign(method, objectKey, checksum?) -> URL for this request; the parts all links share are worked out once.
async function linkSigner(env, now) {
  const host = `${env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`;
  const amzDate = now.toISOString().replace(/[-:]/g, "").replace(/\.\d+/, ""); // 20261022T153000Z
  const date = amzDate.slice(0, 8);
  const scope = `${date}/auto/s3/aws4_request`;
  const key = await signingKey(env, date);
  const queryFor = (signedHeaders) =>
    [
      ["X-Amz-Algorithm", "AWS4-HMAC-SHA256"],
      ["X-Amz-Credential", `${env.R2_ACCESS_KEY_ID}/${scope}`],
      ["X-Amz-Date", amzDate],
      ["X-Amz-Expires", String(LINK_TTL)],
      ["X-Amz-SignedHeaders", signedHeaders],
    ]
      .map(([k, v]) => `${k}=${awsEncode(v)}`)
      .join("&"); // already in sorted order
  const plainQuery = queryFor("host");
  const checksumQuery = queryFor("host;x-amz-checksum-sha256");

  return (method, objectKey, checksum) => {
    const path = `/${env.R2_BUCKET_NAME}/${objectKey.split("/").map(awsEncode).join("/")}`;
    const query = checksum ? checksumQuery : plainQuery;
    const canonical = checksum
      ? `${method}\n${path}\n${query}\nhost:${host}\nx-amz-checksum-sha256:${checksum}\n\nhost;x-amz-checksum-sha256\nUNSIGNED-PAYLOAD`
      : `${method}\n${path}\n${query}\nhost:${host}\n\nhost\nUNSIGNED-PAYLOAD`;
    const signature = hmacHex(key, `AWS4-HMAC-SHA256\n${amzDate}\n${scope}\n${sha256Hex(canonical)}`);
    return `https://${host}${path}?${query}&X-Amz-Signature=${signature}`;
  };
}

// The signing key only changes once a day (or when the R2 key is rotated), so it's cached between requests.
async function signingKey(env, date) {
  const scope = `${env.R2_ACCESS_KEY_ID}/${date}`;
  if (keyCache.scope === scope) return keyCache.key;
  let k = await hmac(enc.encode("AWS4" + env.R2_SECRET_ACCESS_KEY), date);
  for (const part of ["auto", "s3", "aws4_request"]) k = await hmac(k, part);
  const key = hmacKey(k);
  keyCache = { scope, key };
  return key;
}

async function hmac(keyBytes, data) {
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(data)));
}

function awsEncode(s) {
  return encodeURIComponent(s).replace(/[!'()*]/g, (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase());
}

// SHA-256 and HMAC-SHA256 for the short ASCII strings above. A batch signs up to 100 links, and doing it in plain
// JavaScript costs about a tenth of the CPU of 200 WebCrypto calls: the free plan allows 10 ms of CPU per request.
// The HMAC key's two pad blocks are hashed once (hmacKey), so each signature hashes only the message.
const K = new Int32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98,
  0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8,
  0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819,
  0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
  0xc67178f2,
]);
const H0 = new Int32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
const W = new Int32Array(64);
const BUF = new Uint8Array(2048);
const HEX = Array.from({ length: 256 }, (_, i) => i.toString(16).padStart(2, "0"));

function compress(h, b, o) {
  for (let i = 0; i < 16; i++, o += 4) W[i] = (b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3];
  for (let i = 16; i < 64; i++) {
    const x = W[i - 15];
    const y = W[i - 2];
    const s0 = ((x >>> 7) | (x << 25)) ^ ((x >>> 18) | (x << 14)) ^ (x >>> 3);
    const s1 = ((y >>> 17) | (y << 15)) ^ ((y >>> 19) | (y << 13)) ^ (y >>> 10);
    W[i] = (W[i - 16] + s0 + W[i - 7] + s1) | 0;
  }
  let a = h[0], b1 = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], k = h[7];
  for (let i = 0; i < 64; i++) {
    const s1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
    const t1 = (k + s1 + ((e & f) ^ (~e & g)) + K[i] + W[i]) | 0;
    const s0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
    const t2 = (s0 + ((a & b1) ^ (a & c) ^ (b1 & c))) | 0;
    k = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b1; b1 = a; a = (t1 + t2) | 0;
  }
  h[0] = (h[0] + a) | 0; h[1] = (h[1] + b1) | 0; h[2] = (h[2] + c) | 0; h[3] = (h[3] + d) | 0;
  h[4] = (h[4] + e) | 0; h[5] = (h[5] + f) | 0; h[6] = (h[6] + g) | 0; h[7] = (h[7] + k) | 0;
}

// Hashes the first `len` bytes of BUF, continuing from `state`, which has already hashed `done` bytes (0 or 64).
function finish(state, len, done) {
  const h = state.slice();
  const end = ((len + 9 + 63) >> 6) << 6;
  BUF.fill(0, len, end);
  BUF[len] = 0x80;
  const bits = (done + len) * 8;
  BUF[end - 4] = bits >>> 24; BUF[end - 3] = bits >>> 16; BUF[end - 2] = bits >>> 8; BUF[end - 1] = bits;
  for (let o = 0; o < end; o += 64) compress(h, BUF, o);
  return h;
}

function ascii(s) {
  if (s.length > BUF.length - 72) throw new Error("string too long to sign");
  for (let i = 0; i < s.length; i++) BUF[i] = s.charCodeAt(i);
  return s.length;
}

function hexOf(h) {
  let out = "";
  for (let i = 0; i < 8; i++) {
    const w = h[i];
    out += HEX[(w >>> 24) & 255] + HEX[(w >>> 16) & 255] + HEX[(w >>> 8) & 255] + HEX[w & 255];
  }
  return out;
}

function sha256Hex(s) {
  return hexOf(finish(H0, ascii(s), 0));
}

function hmacKey(keyBytes) {
  const pad = new Uint8Array(64);
  const inner = H0.slice();
  const outer = H0.slice();
  pad.fill(0x36);
  keyBytes.forEach((byte, i) => (pad[i] ^= byte));
  compress(inner, pad, 0);
  pad.fill(0x5c);
  keyBytes.forEach((byte, i) => (pad[i] ^= byte));
  compress(outer, pad, 0);
  return { inner, outer };
}

function hmacHex(key, s) {
  const inner = finish(key.inner, ascii(s), 64);
  for (let i = 0; i < 8; i++) {
    const w = inner[i];
    BUF[i * 4] = w >>> 24; BUF[i * 4 + 1] = w >>> 16; BUF[i * 4 + 2] = w >>> 8; BUF[i * 4 + 3] = w;
  }
  return hexOf(finish(key.outer, 32, 64));
}

function oidBase64(oid) {
  return btoa(String.fromCharCode(...oid.match(/../g).map((h) => parseInt(h, 16))));
}

// --------------------------------------------------------------------------------------------------- helpers

function keyFor(oid) {
  return `${REPO}/${oid}`;
}

async function isUploader(request, env) {
  const match = /^Basic\s+(\S+)$/i.exec(request.headers.get("Authorization") || "");
  if (!env.UPLOAD_TOKEN || !match) return false;
  let decoded;
  try {
    decoded = atob(match[1]);
  } catch {
    return false;
  }
  const password = decoded.slice(decoded.indexOf(":") + 1);
  // Compare hashes so the comparison takes the same time whatever the input.
  const [a, b] = await Promise.all(
    [password, env.UPLOAD_TOKEN].map((s) => crypto.subtle.digest("SHA-256", enc.encode(s))),
  );
  return crypto.subtle.timingSafeEqual(a, b);
}

async function allowed(limiter, request) {
  if (!limiter) return true;
  try {
    const { success } = await limiter.limit({ key: request.headers.get("CF-Connecting-IP") || "unknown" });
    return success;
  } catch {
    return true;
  }
}

async function readJson(request) {
  if (Number(request.headers.get("Content-Length") || 0) > 1_000_000) throw lfsError(413, "Request too large.");
  const text = await request.text();
  if (text.length > 1_000_000) throw lfsError(413, "Request too large.");
  try {
    const value = JSON.parse(text);
    if (value && typeof value === "object") return value;
  } catch {
    // fall through
  }
  throw lfsError(400, "Expected a JSON body.");
}

function lfsJson(status, data, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": LFS_JSON, "Cache-Control": "no-store", ...extra },
  });
}

function lfsError(status, message, extra) {
  return lfsJson(status, { message, documentation_url: DOCS }, extra);
}

function tooMany() {
  return lfsError(429, "Too many requests from your address. Please wait a minute.", { "Retry-After": "60" });
}

function notAllowed(allow) {
  return lfsError(405, "Method not allowed.", { Allow: allow });
}
