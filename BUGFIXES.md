# Deferred maintenance

- `config/general.yaml` vs `config/defaults/general.yaml`: current config contains `waymore`, `xnlinkfinder` and `gospider` metadata absent from the default template. This predates the consolidation. Verify fresh-install metadata/installer parity separately; no collector or discovery expansion is included here.
- `src/tools.sh`: the inputless custom-tool URL/domain denial path returns 2 without a per-tool receipt. Nonblocking follow-up from independent review; normal selected-input denial, missing-tool and skipped-tool outcomes are recorded and tested.
- Complete request-level containment for third-party browser, nested crawler, template and override behavior requires isolated adapter/egress tests. See `docs/defensive-maintenance.md`; this contributor PR is draft, not deployment approval.

## katana crawl-scope construction is duplicated

**Location:** `src/scope.sh` `katana_crawl_args()` and `scripts/param_recon.sh:379-385`.

**Evidence:** both build `-cs <crawl-regex> -dr` independently. The printf
option-parsing defect existed only in the param_recon.sh copy, so the
url_discovery crawler was scoped correctly while the param_discovery crawler
was not — for 16h, producing a 6.1GB unscoped crawl before it was killed.

**Impact:** the two call sites can drift again. param_recon.sh runs standalone,
so sharing the helper means sourcing `src/scope.sh` from it; that is a larger
change than this defect fix and is left to its own task.
