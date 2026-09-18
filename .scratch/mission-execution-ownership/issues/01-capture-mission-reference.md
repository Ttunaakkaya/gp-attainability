# 01: Capture reproducible mission behavior references

Status: ready-for-agent
Execution: complete
Approval: user confirmed the testing seam and ticket order on 18 September 2026.

**What to build:** A small, executable preservation check that records today's
whole-mission behavior and detects scientific changes when the implementation is
refactored. It must demonstrate its own sensitivity before production edits begin.

**Blocked by:** None (can start immediately).

**Parent:** [Mission execution ownership spec](../spec.md)

- [x] Source identity is verified against the preserved archive before production edits; the capture manifest records full configurations, development seeds, runtime/dependency versions, hashes and reproducible failure triggers.
- [x] The compact reference set satisfies the spec's method, motion, GP, controller, clock, activation and failure coverage requirements, with observed coverage recorded for each case.
- [x] Raw reference artifacts and normalized scientific evidence are retained independently of the later implementation; repeating capture with the recorded source/environment confirms the comparison is usable.
- [x] Runtime exclusions are an explicit reviewed list; physical time, budgets, IDs, solver evidence, values and failure status remain checked. Existing timing-accounting assertions run separately.
- [x] Controlled changes to copied reference evidence prove the comparator detects altered scientific values, physical times, plan/receipt provenance and failure status; changes to listed runtime measurements alone are accepted.
- [x] The check reports case and differing record/field when a comparison fails, rather than only an opaque hash mismatch.
- [x] Capture uses short development cases, preserves historical outputs and leaves production behavior unchanged.

## Verification

Run the capture and repeatability comparison on the unchanged production source,
then exercise the comparator's positive and negative controls. Record the outcome
and measured runtime. Production edits are gated on this usable baseline.

## Comments

Prepared as the independent-evidence prerequisite. Existing regression tests remain
valuable but cannot substitute for comparing with pre-change outputs.

Completed 18 September 2026. The source-verified frozen reference contains 14
observed cases. Pre-change repetition matched every case; copied-evidence controls
detected scientific, clock, provenance and failure changes while allowing only
listed runtime measurements. Sixteen comparator tests and existing timing checks
passed. Production edits began only after this gate passed.

Evidence: [reference instructions](../reference/README.md),
[frozen manifest](../reference/frozen-20260918/manifest.json),
[repeatability report](../reference/repeat-frozen-20260918/report.json), and
[sensitivity controls](../reference/sensitivity-controls.json).
