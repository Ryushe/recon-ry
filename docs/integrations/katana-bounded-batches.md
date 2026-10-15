# Katana bounded-batches integration dossier

- **Status:** review-ready (parent review and integration pending)
- **Owner:** Hermes bugfix subagent
- **Branch / owning ref:** `fix/katana-bounded-batches`
- **Worktree:** `/home/ryushe/worktrees/recon-ry-katana-batches`
- **Base commit:** `a16578c7abb3a7b80470c273f720dd21845360f0` (fetched `origin/main`)
- **Intended integration target:** `origin/main` / `main`, parent-controlled only
- **Last updated:** 2026-10-15
- **Latest immutable recovery checkpoint:** `4cbee7ed892b45412a57de76642d9a6bc3d607eb`
- **Feature implementation commit(s):** `4cbee7ed892b45412a57de76642d9a6bc3d607eb`
- **Inspiration:** papercut PC-20260917-195548-b1701c3f; no closure authorized

## Intent and contract

Split authorized Katana seed lines into host groups whose shell-encoded crawl regex is at most 32768 bytes. Each group receives only its own seed lines, `-fs fqdn -cs <approved-input-host regex> -dr`; exclusions and exact-host intersection precede grouping. The shared dispatcher is used by scoped `katana`/`exact_katana` tool execution and by scoped `param_recon.sh`. Unscoped behavior remains unchanged. A single overall tool timeout wraps all batches; a failed group returns nonzero, retains partial output, and does not pretend remaining groups ran. The param path emits partial raw output on failure/TERM and fails if an enabled Katana is missing. Final output filtering remains in the existing pipeline.

## Evidence and review

- `python3 -m unittest discover -s scripts -p 'test_*.py' -v`: 44 tests passed, offline.
- `python3 -m unittest scripts.test_katana_batches -q`: 8 passed after final template guard.
- `bash -n src/scope.sh src/tools.sh scripts/param_recon.sh` and `git diff --check`: passed.
- Synthetic 20,000-host fixture validates complete authorized coverage, multi-host batches, regex byte cap, exclusions, suffix attacks, and exact-host denial. Stub Katana validates success, failure, partial output, and aggregate timeout across dispatcher and consumers. No target requests.
- Independent review: pending parent.
- Merge/ancestry: base `origin/main` at a16578c; no merge or push by this worker.

## Blockers and deferred work

- No blocking local test gaps identified. Parent must review, re-fetch integration tip, test/reconcile any intervening changes, and decide integration. No live target exercise authorized; that remains outside this handoff.

## Interruption / resume handoff

- **Owning feature branch/ref:** `fix/katana-bounded-batches`
- **Latest immutable recovery checkpoint:** `4cbee7ed892b45412a57de76642d9a6bc3d607eb`; subsequent dossier-only handoff commit at branch tip.
- **Feature implementation commit(s):** `4cbee7ed892b45412a57de76642d9a6bc3d607eb`
- **Exact resume point:** Review the diff and receipts, integrate only under parent authority; do not push or close papercut here.
- **Working-tree state at handoff:** expected clean after commit.

## Decision gates

- **Integration gate:** independent parent diff review and focused offline tests.
- **Activation / cohort gate:** none attempted.
- **Promotion gate:** no main merge/push by this worker.

## Decision record

- 2026-10-15 — Prepared bounded dispatch and offline regression suite; awaiting parent review.
