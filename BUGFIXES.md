# Deferred maintenance

- `config/general.yaml` vs `config/defaults/general.yaml`: current config contains `waymore`, `xnlinkfinder` and `gospider` metadata absent from the default template. This predates the consolidation. Verify fresh-install metadata/installer parity separately; no collector or discovery expansion is included here.
- `src/tools.sh`: the inputless custom-tool URL/domain denial path returns 2 without a per-tool receipt. Nonblocking follow-up from independent review; normal selected-input denial, missing-tool and skipped-tool outcomes are recorded and tested.
- Complete request-level containment for third-party browser, nested crawler, template and override behavior requires isolated adapter/egress tests. See `docs/defensive-maintenance.md`; this contributor PR is draft, not deployment approval.
