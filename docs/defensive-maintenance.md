# Defensive maintenance boundaries

## Scope files

`recon --scope-file FILE --out-scope-file FILE` uses one ASCII hostname,
`*.hostname`, IP address, or canonical CIDR per line. Blank lines and `#` comment
lines are ignored. URLs, ports, path policies, malformed rules, unreadable files
and empty allow files are rejected rather than guessed. Wildcards include
subdomains, not the apex. Add the apex explicitly when authorized. Exact hosts
never imply `www`, siblings, or another registrable domain. Exclusions always win.

The `exact-urls` and `exact-urls-header` profiles also intersect any explicit
scope with the exact `--url` hostname. They may use that hostname alone when no
scope file is supplied. Scope is independent of `--header` and auth seed data.
The legacy `snap` preset is retained as a reduced stage selection, not a statement
about any program's current authorization.

The runner gates selected tool inputs, including saved history and `--eye`
inputs, immediately before dispatch. Resumed URL/host text artifacts are filtered
before stages, after stages and on promotion. Changed originals are retained in
`.scope-evidence/`; per-dispatch filtered inputs are in `.scope-inputs/`.
These evidence folders are not target inputs and need an operator retention policy.
Scope flags are exported to background work; use `RECON_RY_SCOPE_FILE`,
`RECON_RY_OUT_SCOPE_FILE` and `RECON_RY_EXACT_HOST` only when directly invoking the
internal helpers. Missing scope blocks active dispatch, not passive archive or
local-only processing.

Katana receives an exact-input-host crawl regex, `-fs fqdn` and disabled redirects
(`-dr`). The same restriction is passed to Katana inside param_recon. The latter's
xnLinkFinder host list no longer comes from collapsed archive roots.

### Release blocker: input scope is not an egress firewall

These changes do **not** prove request-level containment for every third-party
crawler, template, browser subresource, redirect, custom command, payload override,
or directly invoked standalone helper. In particular, EyeWitness browsers and
nested param_recon tools need isolated adapter/egress tests before this branch can
claim complete network containment. No target traffic was generated to validate
those integrations. Do not treat post-filtered output or the exact-header profile
as proof that every internal request was scoped or carried the header.
The PR remains draft until that review and verification are complete.

## Port enrichment decision boundary

The existing naabu implementation, stage membership, port set and enablement are
retained. The scope gate accepts explicitly authorized IP addresses **or** CIDRs;
it does not require CIDRs exclusively. A domain's DNS answers are evidence, not
implicit authorization to scan shared infrastructure. If only domain scope is
provided, unlisted resolved IPs cannot pass the active input gate. A run requiring
domain-authorized IP scanning needs an owner decision about authorization and
provenance; this change does not invent an opt-out or weaken that boundary.

## Timeout and evidence contract

Tool exit 124 propagates through the merger and sequential/parallel stage runners.
The tool's raw partial bytes are retained under `.partials/`, including malformed
partial JSON that cannot be parsed. Immutable per-invocation `tool-status/result.*`
TSV receipts record tool, exit code, partial flag and canonical artifact path in
the current history directory (or project directory for standalone tool calls).
They contain no command or header values. A project waits for its launched directory
enumeration job before declaring completion, and returns nonzero when a stage
failed or timed out. Receipts, not result counts, distinguish empty success from
incomplete work. Timeout zero still means unlimited, including absent-config
fallbacks; it does not imply scanning permission.

## Portable retained functionality

Mounted EyeWitness storage is opt-in through `large_project_dir`; repository
configs do not assume `/mnt/bounty`. SQLite-backed cached search/report generation,
run asset prefixes, long artifact-name retry and custom header aliases are retained.
The superseded duplicate `exact-urls` YAML definition is removed so it cannot
silently shadow the dedicated exact stages.

## Unverified external issues

- The Wayback endpoint diagnosis is not reproduced. No installed local collector
  source was available in the repository. No replacement collector or fabricated
  data is included.
- BBH wrapper forwarding belongs to another repository, excluded from this PR.
- Hoster runtime launcher/activation is unresolved. No deployment was performed.

## Script map and offline checks

- `scripts/scope_filter.py`: standard-library offline matcher, filter and crawl regex.
- `src/scope.sh`: runner input and artifact gates.
- `scripts/test_defensive_boundaries.py`: offline matcher and shell-fixture regression tests.
- `scripts/self_test.sh`: existing history, auth and EyeWitness report regressions.

Run from the candidate worktree:

```sh
python3 scripts/test_defensive_boundaries.py
bash scripts/self_test.sh
bash -n main.sh src/*.sh scripts/*.sh
python3 -m py_compile scripts/*.py
git diff --check
```

Do not substitute a live recon run for these offline maintenance checks.
