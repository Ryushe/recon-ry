# Consolidated defensive maintenance (open / draft)

## Intent and ownership
User-authorized consolidation of existing local and Hoster patches plus defensive scope containment and honest timeout reporting. No target traffic, recon, scans, new collectors, merge, deployment, or BBH wrapper changes are authorized.

- Base / defect owner: upstream `origin/main` at `c70447ce1cf63c833f5ba7be59e55bd7ef28a52c`.
- Task branch: `fix/consolidated-scope-timeouts`; isolated contributor worktree.
- Publication: `ghostonbutterbread/recon-ry`, PR to `ryushe/recon-ry:main` only.
- Imported local main: `f202dfc`; custom-header implementation `86c2e9f` (task copy `af75ca9`); missing-timeout fallback `66ec9fd` (task copy `b8cd666`). No ancestor/shared runtime branch edited.

## Reconciliation
Hoster HEAD `3f091dd096719b0a760119e59c32ea5e29f1c4bf` and complete tracked/untracked source snapshot privately preserved read-only. Operational state.yaml and .bak files are not publishable defaults. Existing local EyeWitness implementation already contains the mounted storage, SQLite cache and searchable report work, plus newer run asset-prefix regression fixes; retain those rather than overwrite with older Hoster copies. Exact-header profile and fqdn crawler restriction are consolidated. No secrets or target/run artifacts are to be imported.

## Contract / success criteria
Exact hosts never imply www or sibling hosts; exclusions override inclusions. Explicit scope controls tool input and artifact promotion, including resumed/history inputs. Crawler scope must be constrained before requests, not only filtered afterward. DNS answers do not grant scan authorization; retain existing port enrichment, accepting only explicitly authorized IPs/networks until domain-to-IP authorization semantics are decided. Timeouts retain evidence but remain incomplete/nonzero through tool, stage and project status.

## Evidence and blockers
Implemented strict offline scope matcher, pre-dispatch selected-input gates, resumed/history text artifact filtering, exact Katana host regex, explicit IP/CIDR containment, immutable timeout receipts and nonzero tool/stage/project status. Local `python3 scripts/test_defensive_boundaries.py` passed 12 tests; `bash scripts/self_test.sh` passed. Shell syntax, Python compilation and `git diff --check` passed. Hoster snap preset retained without program-authorization claims; duplicate exact-urls YAML key removed; header profile mirrored to default configs. Mounted storage default made portable (empty opt-in), retaining cache and asset fixes. See docs/defensive-maintenance.md for adapter/egress release blockers. No live target testing permitted. Independent reviewer CLI gate completed for draft publication; release remains blocked as detailed below. Project Kanban access denied in delegated child context; parent must reconcile its owning card. Hoster cleanup sidecar unavailable (no native delegation); no remote processes touched. Runtime launcher remains unresolved and no deployment is intended.

## Independent review and verified follow-up

Reviewed implementation checkpoint: `e2fb5739e63935ece64db7db33471f51e9b2448b`, reachable on this branch and its fork review ref. A fresh Claude CLI reviewer independently reviewed the full upstream diff and reran 12 boundary tests, 26 existing self-test assertions and shell syntax. Its first run exhausted the turn budget; resuming it with exact allowed test commands produced a completed review, not an invented approval. Verdict: draft publication appropriate; no release approval.

The follow-up addresses review findings F1–F11: keep timeout status on receipt/archive I/O failure; use artifact-local paths for standalone callers; reject missing allow/exclusion paths before exporting; exercise actual parallel and verbose timeout paths; add explicit preflight receipt outcomes; recheck saved EyeWitness chunks before dispatch; remove unverified header claims; preserve IPv6 and bare-host parsing; document the inherited EyeWitness timeout exemption; include source_base in report-cache identity; prominently document the active-scope compatibility change. The exclusion-path defect was reproduced by an offline CLI dry-run returning 0 at the prior checkpoint, then covered by a regression requiring exit 2.

Current local verification: `python3 -m unittest discover -s scripts -p 'test_*.py' -v` passed **22 tests**, `bash scripts/self_test.sh` passed (including exact_katana header coverage), shell syntax, Python compilation and diff whitespace checks passed. Follow-up independent review completed at `3a8d229856d15a9006f834434e01797c1c5355f5`: reviewer independently reran 12 boundary tests, 10 review regressions and 27 self-test assertions, all passing, with no denied commands. It found no correctness regression in the follow-up and closed the prior blocking findings. Verdict: appropriate for draft publication; no release approval until the documented adapter/authorization gates are satisfied. Final local verification also parsed each of 16 shell files individually (not merely passing multiple filenames as bash arguments), compiled Python and checked whitespace. Browser/third-party adapter and domain-to-IP authorization decisions remain release blockers, not reasons to weaken scope.

Hoster tracked diff, status and HEAD were read back unchanged after snapshot collection. The older Hoster `non-404-error -> errors` alias is not copied over the local `capture-error` mapping, which matches the current report filter names. Its cached report implementation is otherwise preserved by the newer local version with fixed asset prefixes. Hoster operational configs and backup files remain private, not PR defaults.

## Remaining nonblocking review notes

- An empty-input tool rejected by the secondary domain/URL check returns 2 without a tool receipt. Scope remains fail-closed; extend outcome coverage separately.
- PyYAML is an existing framework prerequisite (`setup.sh` and `src/config.sh`), not a new runtime dependency. The full test suite requires it; only the scope matcher is standard-library-only. Do not silently skip the configuration gate when that prerequisite is absent.
- The root backlog is retained to record the observed, pre-existing default/current metadata discrepancy under the repository maintenance policy. It does not authorize adding collectors.
- Configuration stage lists are parity-tested; descriptive text is not an authorization control.

## Hoster preservation audit

The captured Hoster committed-plus-dirty diff changes 11 source paths. Ten reusable source/document/config paths are reconciled into the candidate: README, both general configs, both profile configs, main.sh, incremental_eyewitness.py, param_recon.sh, self_test.sh and stages.sh. The eleventh, config/state.yaml, is runtime operator state and is intentionally not published. Untracked backup files are preserved privately. The complete private snapshot and per-file SHA-256 reconciliation manifest remain available to the owner; no target artifacts or secrets are included in this PR.

## Final verification and publication boundary

- Builder verified **22 Python tests**, **27 self-test assertions**, all **16 shell files individually** with `bash -n`, all six Python scripts with `py_compile`, and the complete `origin/main...HEAD` diff with `git diff --check`.
- Shell syntax must be checked in a per-file loop; passing multiple scripts to one `bash -n` only checks the first. The documentation recipe is corrected.
- Remaining nonblocking review notes: an inputless custom-tool scope denial lacks a receipt; descriptions can drift independently of stage parity. Keep the existing PyYAML requirement rather than silently skipping configuration tests: the framework/self-test already depends on PyYAML, while the scope matcher itself remains standard-library-only. Keep `BUGFIXES.md` as the required backlog, not a second integration tracker.
- Compatible concurrent edits to CHANGELOG.md, CONTRIBUTING.md and the shell-check recipe appeared during review. Their diff was privately preserved, inspected and included as task-relevant documentation; their producer was not inferred from timing.
- Local shared main remains `f202dfc68ff7ae0303f8366267912a9d18018d53` and was not edited. Hoster remains at its original HEAD with its dirty diff untouched. The task branch/worktree remains intentionally retained for the blocked PR, not merged or deployed.
- Publication is a single draft PR from `ghostonbutterbread:fix/consolidated-scope-timeouts` to `ryushe/recon-ry:main`. Verify the exact pushed SHA and the PR head/base/draft state by read-back before reporting its URL. Parent owns Kanban reconciliation because this child context is denied tracker access.

## Deferred evidence / resume
Keep the PR draft until isolated nested-crawler/browser/redirect tests and the domain-to-IP authorization decision are complete. Rerun the offline checks and independent review after runtime changes. Verify published ref and PR by exact read-back. Wayback endpoint diagnosis is unverified; investigate installed source offline only, do not replace its collector. Remove this branch-local dossier only on accepted integration or supersession.
