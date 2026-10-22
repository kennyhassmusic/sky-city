# Sky City LFS server (Cloudflare Worker + R2)

Clones of Sky City download their Git LFS files from here instead of GitHub, which bills every LFS download to the
repo owner. Uploads still go to GitHub; the `lfs-mirror` Action copies new files into R2 after each push to `main`.

| File | What it is |
|---|---|
| `src/index.js` | The Worker: the Git LFS Batch API, answered with signed links to the R2 bucket. No dependencies. |
| `wrangler.toml` | Worker config: the bucket binding, rate limits and the names of its secrets. |
| `mirror.py` | Copies LFS files R2 is missing, from this clone's `.git/lfs` or from GitHub. Python standard library only. |
| `rotate-upload-token.sh` | Makes a new upload password and stores it in Cloudflare, GitHub Actions and the macOS keychain. |

How it all fits together, what it costs and the maintenance jobs: [docs/MAINTAINER_SETUP.md](../../docs/MAINTAINER_SETUP.md#git-lfs-downloads-from-cloudflare-r2).
