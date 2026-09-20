# Artifact contract — offline maintenance handoff

- Status: implemented and locally tested; independent review pending (parent arranges it).
- Owner: parent task `t_3697fb9c`, board `bug-bounty-harness`.
- Branch/worktree: `fix/artifact-contract`, `/home/ryushe/worktrees/recon-ry-artifact-contract`.
- Fetched base and intended PR target: `origin/main` at `95d20a64e38dd9c4e1c7b481086455103900d182`.
- Implementation checkpoint: pending local commit; this dossier travels with the implementation.
- Integration route: parent-reviewed contributor/review branch targeting `origin/main`; no direct main merge, push, runtime activation or descendant propagation in this task.
- Inspiration: explicit owner correction of the artifact contract; supersedes historical proposal directions that treated wild.txt as globally immutable or sought new discovery promotion. Durable contract lives in README.md, not this temporary dossier.

## Implemented boundary

1. `wild.txt` remains agent/operator-maintained authorized wildcard roots input. Agents may update it after verified wildcard scope changes. Automated run output never populates it. No writer, scope gate or discovery configuration changes are made here.
2. `hosts.txt` remains the existing seeded/subdomain-enumeration inventory, distinct from `alive.txt`. Both project summaries and URL-only stdout now display it. No new host extraction or promotion into active inputs is added.
3. `param_recon.sh` filters both normal and interrupted raw-output merges through the same offline URL-shape check: absolute HTTP(S), hostname present, nonempty query, no whitespace/control characters. Other schemes, relative links, bare hosts, logs, malformed bracketed hosts, empty queries and fragment-only queries are rejected. Query flags, empty values, IPv6 URLs and uppercase schemes remain valid. Accepted URL strings are preserved (line endings normalized); sorting/deduplication remains unchanged.
4. Interrupt handling still drops each phase's non-newline-terminated final row, emits surviving output before cleanup, and retains its existing signal status semantics. Normal completion keeps its existing complete-phase concatenation behavior. This is row-shape validation, not authorization, full URL syntax validation, host completeness, or network containment.
5. Documentation examples no longer declare wild.txt as a collector output. Existing synthetic history fixtures, configuration, crawler profiles, scope enforcement, timeout defaults and collector commands remain unchanged.

## Offline evidence

Baseline at the base SHA:

- `python3 -m unittest discover -s scripts -p 'test_*.py' -v`: 36 tests passed.
- `bash scripts/self_test.sh`: PASSED.

Observed RED before each implementation slice:

- Parameter regression: 4 tests run; existing 3 passed, new contract test failed in all 3 subcases (normal, SIGTERM, SIGINT) because non-HTTP/non-query rows leaked into the emit file.
- Summary regression: 1 test failed in both subcases (project and URL-only) because hosts.txt was absent from output.

GREEN:

- Focused parameter module: 4 tests passed, including normal/SIGTERM/SIGINT publication and existing cleanup/persistence checks.
- Focused summary module: 1 test passed (project and URL-only).
- Full unittest discovery: 38 tests passed.
- `bash scripts/self_test.sh`: PASSED.
- `for file in main.sh src/*.sh scripts/*.sh; do bash -n "$file" || exit; done`: passed.
- `python3 -m py_compile scripts/*.py`: passed.
- `git diff --check`: passed.

All fixtures are synthetic, local-only, and use stub collectors/stages. No target requests, live scans, program data, enumeration/crawling changes or scope expansion. Repository fetch was the only intentional network operation.

### Recoverable RED replay

From this branch, export the immutable base with `git archive 95d20a64e38dd9c4e1c7b481086455103900d182` into a disposable directory, then copy this branch's `scripts/test_artifact_contract.py` and `scripts/test_param_recon_interrupt.py` over the exported tests. Run unittest discovery separately with `-p 'test_artifact_contract.py'` and `-p 'test_param_recon_interrupt.py'`. The expected failures are the two summary subcases and three parameter subcases above. Delete only that disposable export afterward. Do not revert a shared checkout to replay RED.

## Deferred findings and activation boundary

- `hosts.txt` is not a complete union of hosts mentioned in URL/archive/JS/parameter artifacts. Existing seeding from wild.txt is conditional on an empty inventory unless an explicit roots file is passed; later maintained root changes can be missing when enumeration is skipped. Recorded in BUGFIXES.md. Do not automatically feed newly extracted hosts to active scanners; any future design needs explicit provenance/authorization decisions and separate offline tests.
- Legacy Waymore root derivation uses last-two-label trimming, and its roots Python output is not redirected into the prepared roots temp file. Recorded in BUGFIXES.md, left untouched; no claims of live archive completeness.
- The new filter governs param_recon publication, not a migration of already accumulated project artifacts or a redesign of other configured producers.
- Existing third-party request-containment blockers remain unchanged. No live verification is required for this offline task or authorized by it.
- Required next gate: parent-arranged independent reviewer reruns the offline commands above against the implementation checkpoint and inspects the exact diff. Until accepted, retain this dossier on the feature branch. On eventual reviewed integration, retire this temporary dossier from the target lane; README.md and BUGFIXES.md are the durable successors.
