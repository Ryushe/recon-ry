# Fractional rate limits and url_discovery corpus promotion (open / draft)

## Intent and ownership

Fix three defects observed 2026-11-04 on the linktree-mbb-og snap run (log
`recon-ry-logs/linktree-mbb-og-20261104T022756Z.log`): fractional
`rate_limit.conf` values killed every ProjectDiscovery tool via int-only `-rl`
flags, the url_discovery corpus was stranded in `.tmp_run` when url_ranking
skipped, and skipped stages were invisible in the completion summary.

- Base / defect owner: `origin/main` at `e98816e` (PR #30 merge). `main` is an
  ancestor of `beta` (verified `git merge-base --is-ancestor main beta`);
  propagate to `beta` after merge.
- Task branch: `fix/fractional-ratelimit-and-ranking-merge`; isolated worktree
  `~/worktrees/recon-ry-fix-rl`.
- Publication: push branch to `prfork` (ryushepwn), PR to `Ryushe/recon-ry:main`.

## Implemented contract

1. `apply_rate_limit_substitution` (src/tools.sh) wraps both `{{RATE_LIMIT}}`
   substitution sites: integers pass through; httpx fractional req/s → exact
   `-rlm N` per-minute (0.5→30, 0.25→15); all other int-flag consumers
   (nuclei `-rlm` deprecated, katana v1.8.0 ignores `-rlm`, subfinder/ffuf lack
   per-minute) clamp to `1` with a warning. Empty/`0` behave exactly as before.
2. `promote_temp_urls_to_project` (src/output.sh), called after the
   url_discovery stage in `run_recon_project`: merges the scope-filtered
   `.tmp_run/urls.txt` corpus into project `urls.txt` (dedup via
   anew/sort-u), so a skipped url_ranking or a wiped `.tmp_run` can no longer
   destroy the harvest (observed: 1,399,847 URLs stranded; project urls.txt
   left with 13 seed lines while the run printed "Recon completed!").
3. url_ranking `depends_on` `[http_fingerprinting]` → `[alive_check]`
   (config/general.yaml + config/defaults/general.yaml): rank-urls reads
   alive.txt, not fingerprint sidecars; httpx failure no longer double-penalizes.
4. Honesty: `SKIPPED_STAGES` tracks dep/disabled skips (execute_stage), and the
   final summary prints "Recon completed with issues: N failed, M skipped
   (list)" instead of plain "Recon completed!" when anything went wrong.
5. Observability: tool-failure merge line now includes the exit code (waymore
   failed silently with an empty partial; config note documents its isatty
   gate — environmental, no behavior change made for it).

## Evidence

- New `scripts/test_rate_limit_and_corpus_promotion.py`: 30 tests OK
  (translation table, pass-through, clamp, promotion dedup/idempotency/noop,
  bash -n syntax, YAML dependency assertion).
- Existing suites all OK: self_test.sh, test_defensive_boundaries,
  test_param_recon_interrupt, test_printf_option_injection,
  test_review_regressions, test_wild_roots_preserved.
- Offline end-to-end smoke with the real config template and real binaries:
  httpx v1.9.0 accepts `-rlm 30`; nuclei accepts clamped `-rl 1`; integers
  untouched. No network traffic, no project dirs touched.

## Blockers / deferred

- waymore_urls exit≠0 with empty output: provider/env (isatty-gated silence per
  config note; likely missing provider keys). Not patched; exit code now
  logged for the next occurrence.
- Propagation to `beta`: after PR merge (bugfix-lifecycle: merge corrected
  main into beta, rerun focused checks).
- BBH wrapper `--rate-limit-rps` could additionally warn on fractional input;
  separate repo, not required now that recon-ry is robust.

## Activation boundary / next

PR to Ryushe/recon-ry:main from ryushepwn:fix/fractional-ratelimit-and-ranking-merge.
Next: merge, propagate to beta, retire the worktree.
