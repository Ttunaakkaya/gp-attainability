# Configuration status after masterplan v2.0 activation

[Masterplan v2.0](../GP_Attainability_Masterplan_TR.md) defines active scope. This
cleanup does not create fictitious independent/ECC implementations or frozen trials.

- `development/smoke.yaml`: retained working infrastructure YAML example, accepted
  by `validate-config` and `doctor --config`; not the FIELDWORK scenario config.
- `reproduction/ecc2025.yaml`: retained source-provenance placeholder, locked only
  for paper reproduction pending full-text audit. It does not block independent code.
- `sweeps/budget.yaml`, `noise.yaml`, `mismatch.yaml`: inactive v1 axis ideas. Their
  subjects remain relevant, so they were preserved; no current runner consumes them.
  Values are not approved v2 experiment settings or completion conditions.

Active v0 simulator settings are validated by `MappingConfig` in
`src/attain_sampling/sim/mapping.py`; presets live in `demo/runner.py`.
The obsolete method IDs, main slack-comparison protocol and old scaling draft were
archived as described in [cleanup report](../docs/cleanup_report.md). Future v2
configuration namespaces must be added with real implementations, not empty claims.
