# Reconcile — JOB 2: PR stack order (#3, #5, #4, #6, #7)

Cloud agent marker for LUCA. Invariants were read from `docs/AGENT_OPS/INVARIANTS.md` before this change. No protected value was edited. Nothing was pushed, merged or retargeted on GitHub; Kenny reviews `JOB2_REPORT.md` first.

- PR: none new. Re-stacks open PRs #3, #4, #5, #6, #7 locally.
- Agent: Claude (claude.ai cloud session, no luca connector on this host)
- New stack (base ← head):
  - `main` (`d0dd69c`) ← #3 `cursor/city-block-realism-04ef` (`cd8b893` → `788c507`, 6 commits)
  - #3 ← #5 `cursor/texture-pack-loader-04ef` (`8d7e6d0` → `fe5bd70`, 4 commits)
  - #5 ← #4 `cursor/road-dressing-stage1-04ef` (`6f06166` → `e150ce8`, 3 commits) — base moves from #3 to #5
  - #4 ← #6 `cursor/citywide-generate-04ef` (`5fbee4c` → `466ea12`, 28 commits) — now contains #3 and #5
  - #5 ← #7 `cursor/texture-packs-wired-04ef` (`2af75ea` → `7cc1f27`, 4 commits)
- Merge order: #3, #5, #4, #6, then #7 (needs `maintainer-approved`: ~887 MB LFS, over the 300 MB per-PR limit).
- Conflicts: only `docs/AGENT_OPS/PROGRESS_LOG.md` (every branch adds entries at the top; #3 and `main` both added the LUCA files). Resolved as a union of entries, newest first. `INVARIANTS.md` and the reconcile `.gitkeep` from #3 matched `main` exactly. Code diffs of #4, #5, #6, #7 are byte-identical to the originals (patch-id checked, log excluded).
- ALLOW-CHANGE: none
- city-sample: unchanged (`CitySamplePCG` in `SkyCity.uproject`)
- pr-guard-lfs: unchanged (25 / 100 / 300 MB)
- asset-licences: no assets added
- no-real-brands: nothing added
- lfs-r2: `.gitattributes`, `.lfsconfig`, `lfs-mirror.yml` unchanged
- seed-determinism: `block.py` twice on the rebased #6 → same hash `6ffee243…ecdb8d`. Note: the committed sample outputs on #4 and #6 still carry the pre-dressing hash `3b867770…50632b`; the original `pr/4` and `pr/6` heads show the same gap, so it predates this job.
- Tests after every rebase (`test_packs` where present, `test_city`, `test_profiles`): all OK on all five branches.
