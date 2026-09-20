# CI portability repair

20 September 2026. Local validation complete; pushed two-platform CI is the final gate.

## Original failure and correction

[Initial CI](https://github.com/Ttunaakkaya/gp-attainability/actions/runs/35370396325)
passed Windows and failed two of 1,023 tests on Ubuntu.

The DP sample/reference test compared interpolated coordinates by exact equality.
Seed 2 reproduced a residual of 8.881784197001252e-16 locally. It was added to the
existing test matrix and observed failing before the assertion was changed to
zero relative tolerance and 1e-12 absolute tolerance. Plan/time identities and all
motion/safety checks remain exact or retain their existing tolerance. No simulator
code changed for this issue; all 30 DP tests pass.

The SOGP dense-stream test exposed roundoff in recursive dictionary inverse
contractions. A 103-observation real stream was reduced to 77 necessary rows. Its
old novelty was -1.013e-8; Cholesky of the same unregularized dictionary gave +1.194e-9.
The repair recomputes numerically unresolved novelty with triangular solves and
refreshes that inverse on the transactional state copy. The kernel, sensor noise,
jitter, admission threshold, pruning rule and negative-variance guard are unchanged.

The minimized regression failed before the fix and passed afterward. All 65
SOGP/ECC-SOGP tests pass, including corrupted-state rejection and rollback.
Twelve bounded 2,500-observation streams: old code failed two; corrected code
passed all with finite means and covariance eigenvalues above -1e-8. Median update
runtime rose from 0.657 s to 0.864 s (about 31%) at capacity 128, with no persistent
memory increase. This is a small diagnostic, not a general performance claim.

## Preservation

[Original-reference comparison](final-reference/report.json): 13 of 14 cases match
exactly under the existing runtime-only normalization. In `dp_sogp_pruning`, 34
numeric fields differ by at most 2.1094237467877974e-15. Shape, identifiers, timing,
counts and outcomes remain unchanged; see [every numeric delta](numerical-delta.json).
The frozen original files and normalizer were not altered.

A [separate post-repair checkpoint](numerical-reference/manifest.json) retains the
single intentionally affected case, its source identity and hashes, before any
tick-execution edits. Its [repeat comparison](repair-repeat-reference/report.json)
passes exactly. Subsequent structural changes must preserve this checkpoint plus
the 13 unaffected historical cases; this is not permission to relax comparison.

## Final local checks and review

- Full suite: 1,030 passed in 97.07 seconds; coverage 94.52% (threshold 80%).
- Ruff lint and format: passed; Mypy: 44 source files passed.
- Independent exact-GP diagnostic: 11 passed.
- Independent Standards review against c256bac: 0 findings.
- Independent Spec review against c256bac: 0 implementation findings; remote CI pending.

The reviews checked only `gp/sogp.py`, `test_sogp.py` and `test_mapping_dp.py` against
[the repair spec](spec.md). The reviewed production correction uses the same
unregularized Gram matrix, bounded state and transactional error handling.

Evidence: `full-tests.log`, `full-tests-status.json`, `static-status.json`, the
comparison reports and numerical-delta report. No tick-execution production change
belongs to this repair commit.
