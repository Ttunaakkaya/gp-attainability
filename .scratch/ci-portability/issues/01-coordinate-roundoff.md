# Preserve geometric assertions across floating-point implementations

Status: ready-for-agent
Execution: complete
Parent: [CI portability spec](../spec.md)

- [x] Reproduce the Ubuntu symptom through a real mission locally.
- [x] Preserve plan/time identity checks and all motion/safety assertions.
- [x] Compare interpolated target coordinates with explicit absolute tolerance.
- [x] Keep the reproducing seed in the regression matrix.

## Comments

The existing case at seed 7 failed on Ubuntu by one ULP. Seed 2 reproduces the
same failure locally: planned coordinate 8.881784197001252e-16 versus target 0.0.
Adding seed 2 to the existing matrix made pytest fail before changing the assertion.
The coordinate assertion now uses rtol=0, atol=1e-12; no production code or plan,
clock, receipt or geometry semantics changed. All 30 DP mission tests pass.
