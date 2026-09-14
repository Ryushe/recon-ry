# Deferred maintenance

- `config/general.yaml` vs `config/defaults/general.yaml`: current config contains `waymore`, `xnlinkfinder` and `gospider` metadata absent from the default template. This predates the consolidation. Verify fresh-install metadata/installer parity separately; no collector or discovery expansion is included here.
- Complete request-level containment for third-party browser, nested crawler, template and override behavior requires isolated adapter/egress tests. See `docs/defensive-maintenance.md`; this contributor PR is draft, not deployment approval.
