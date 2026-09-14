# Consolidated defensive maintenance (open / draft)

## Intent and ownership
User-authorized consolidation of existing local and Hoster patches plus defensive scope containment and honest timeout reporting. No target traffic, recon, scans, new collectors, merge, deployment, or BBH wrapper changes are authorized.

- Base / defect owner: upstream `origin/main` at `c70447ce1cf63c833f5ba7be59e55bd7ef28a52c`.
- Task branch: `fix/consolidated-scope-timeouts`; isolated contributor worktree.
- Publication: `ghostonbutterbread/recon-ry`, PR to `ryushe/recon-ry:main` only.
- Imported local main: `f202dfc`; custom-header implementation `86c2e9f` (task copy `af75ca9`); missing-timeout fallback `66ec9fd` (task copy `b8cd666`). No ancestor/shared runtime branch edited.

## Reconciliation
Hoster HEAD `3f091dd096719b0a760119e59c32ea5e29f1c4bf` and complete tracked/untracked source snapshot privately preserved read-only. Operational state.yaml and .bak files are not publishable defaults. Existing local EyeWitness implementation already contains the mounted storage, SQLite cache and searchable report work, plus newer run asset-prefix regression fixes; retain those rather than overwrite with older Hoster copies. Exact-header profile and fqdn crawler restriction still need consolidation. No secrets or target/run artifacts are to be imported.

## Contract / success criteria
Exact hosts never imply www or sibling hosts; exclusions override inclusions. Explicit scope controls tool input and artifact promotion, including resumed/history inputs. Crawler scope must be constrained before requests, not only filtered afterward. DNS answers do not grant scan authorization; retain existing port enrichment, accepting only explicitly authorized IPs/networks until domain-to-IP authorization semantics are decided. Timeouts retain evidence but remain incomplete/nonzero through tool, stage and project status.

## Evidence and blockers
Implemented strict offline scope matcher, pre-dispatch selected-input gates, resumed/history text artifact filtering, exact Katana host regex, explicit IP/CIDR containment, immutable timeout receipts and nonzero tool/stage/project status. Local `python3 scripts/test_defensive_boundaries.py` passed 12 tests; `bash scripts/self_test.sh` passed. Shell syntax, Python compilation and `git diff --check` passed. Hoster snap preset retained without program-authorization claims; duplicate exact-urls YAML key removed; header profile mirrored to default configs. Mounted storage default made portable (empty opt-in), retaining cache and asset fixes. See docs/defensive-maintenance.md for adapter/egress release blockers. No live target testing permitted. Independent reviewer CLI gate pending. Project Kanban access denied in delegated child context; parent must reconcile its owning card. Hoster cleanup sidecar unavailable (no native delegation); no remote processes touched. Runtime launcher remains unresolved and no deployment is intended.

## Independent review and verified follow-up

Reviewed implementation checkpoint: `e2fb5739e63935ece64db7db33471f51e9b2448b`, reachable on this branch and its fork review ref. A fresh Claude CLI reviewer independently reviewed the full upstream diff and reran 12 boundary tests, 26 existing self-test assertions and shell syntax. Its first run exhausted the turn budget; resuming it with exact allowed test commands produced a completed review, not an invented approval. Verdict: draft publication appropriate; no release approval.

The follow-up addresses review findings F1–F11: keep timeout status on receipt/archive I/O failure; use artifact-local paths for standalone callers; reject missing allow/exclusion paths before exporting; exercise actual parallel and verbose timeout paths; add explicit preflight receipt outcomes; recheck saved EyeWitness chunks before dispatch; remove unverified header claims; preserve IPv6 and bare-host parsing; document the inherited EyeWitness timeout exemption; include source_base in report-cache identity; prominently document the active-scope compatibility change. The exclusion-path defect was reproduced by an offline CLI dry-run returning 0 at the prior checkpoint, then covered by a regression requiring exit 2.

Current local verification: `python3 -m unittest discover -s scripts -p 'test_*.py' -v` passed **22 tests**, `bash scripts/self_test.sh` passed (including exact_katana header coverage), shell syntax, Python compilation and diff whitespace checks passed. Follow-up independent review pending. Browser/third-party adapter and domain-to-IP authorization decisions remain release blockers, not reasons to weaken scope.

Hoster tracked diff, status and HEAD were read back unchanged after snapshot collection. The older Hoster `non-404-error -> errors` alias is not copied over the local `capture-error` mapping, which matches the current report filter names. Its cached report implementation is otherwise preserved by the newer local version with fixed asset prefixes. Hoster operational configs and backup files remain private, not PR defaults.

## Deferred evidence / resume
Run `bash scripts/self_test.sh` and focused offline boundary/status tests from this worktree; independently review full diff against fetched upstream. Review nested crawler/redirect behavior before claiming complete network containment. Verify published ref and PR by exact read-back. Wayback endpoint diagnosis is unverified; investigate installed source offline only, do not replace its collector. Remove this branch-local dossier only on accepted integration or supersession.
