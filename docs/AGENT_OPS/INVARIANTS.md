# INVARIANTS — Sky City (Warden-checked)

Things a Builder session (Claude Code, Cursor cloud agent, Grok, a human) must **not** silently undo in
`kennyhassmusic/sky-city`. The JSON block is read by `luca warden` and injected into every `luca build`
prompt. Cloud agents without the luca connector read this file at the start of work and leave a marker in
`docs/AGENT_OPS/QUEUE/reconcile/` with each PR (see `~/luca-harness/LUCA.md`).

**How to change a protected value on purpose:** put `ALLOW-CHANGE: <label>` on its own line in the job brief
or reconcile marker. Without it, a session that breaks a rule below FAILS Warden and the PR is not merged.

## Rules in plain words

1. **city-sample** — City Sample content and the `CitySamplePCG` plugin stay in the project until Kenny
   explicitly OKs removing them (`ALLOW-CHANGE: city-sample`).
2. **pr-guard-lfs** — `.github/workflows/pr-guard.yml` limits stay: warning over 25 MB per file, failure over
   100 MB per file or 300 MB per PR.
3. **asset-licences** — assets must be CC0, CC-BY, or original/AI-generated only. No NC, no ShareAlike. Every
   added asset is recorded in `CREDITS_AND_LICENCES.txt`. (Review rule, not machine-checked: that file
   already lists one older CC BY-NC vehicle and the project's own CC BY-NC terms, so a text ban would
   false-fail. New entries must not add NC or SA.)
4. **no-real-brands** — never name real car or rocket companies (in-game names, assets, copy, file names).
5. **lfs-r2** — the Git LFS / R2 setup (`.gitattributes`, `.lfsconfig`, `.github/workflows/lfs-mirror.yml`)
   is unchanged unless Kenny asks.
6. **seed-determinism** — the city generator is deterministic: the same seed gives the same manifest hash
   (`python3 -I Scripts/city/block.py` twice → same hash; `Scripts/city/test_city.py` checks it).

Tests: there is no pytest suite. Run the scripts directly: `python3 -I Scripts/city/test_city.py`,
`python3 -I Scripts/roads/test_profiles.py` (each prints `OK`). Editor checks are in `AGENTS.md`.

```json luca-invariants
{
  "version": 1,
  "protectedTokens": [
    {
      "label": "city-sample",
      "file": "SkyCity.uproject",
      "mustMatch": "CitySamplePCG",
      "why": "Kenny: City Sample and the CitySamplePCG plugin stay until he OKs removing them."
    },
    {
      "label": "pr-guard-lfs",
      "file": ".github/workflows/pr-guard.yml",
      "mustMatch": "WARN_MB: \"25\"",
      "why": "pr-guard warns over 25 MB per file."
    },
    {
      "label": "pr-guard-lfs",
      "file": ".github/workflows/pr-guard.yml",
      "mustMatch": "FILE_MAX_MB: \"100\"",
      "why": "pr-guard fails over 100 MB per file."
    },
    {
      "label": "pr-guard-lfs",
      "file": ".github/workflows/pr-guard.yml",
      "mustMatch": "TOTAL_MAX_MB: \"300\"",
      "why": "pr-guard fails over 300 MB per PR."
    },
    {
      "label": "seed-determinism",
      "file": "Scripts/city/block.py",
      "mustMatch": "manifest hash",
      "why": "Same seed -> same manifest hash; the generator's locked regeneration depends on it."
    }
  ],
  "writeScope": {
    "why": "Sky City sessions stay in this repo unless the brief names another path.",
    "extraAllowedRoots": []
  },
  "testEvidence": {
    "why": "Generator and road changes must run their script tests.",
    "rules": {
      "Scripts/city/": ["Scripts/city/test_city.py"],
      "Scripts/roads/": ["Scripts/roads/test_profiles.py"]
    }
  },
  "noOp": {
    "why": "A session with no commits ahead of base is flagged so it can't be counted as done.",
    "flag": true
  }
}
```
