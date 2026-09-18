# Mission execution ownership: completed increment

18 September 2026. All three approved tickets are complete.

## Result

The existing whole-mission entry point delegates to one private execution owner.
Successful execution and failure serialization read the same owned mission state;
the separate progress mirror and nested sensing closure are removed. Periodic
and interior P plan activation share provenance/event bookkeeping while retaining
their different future-reference and forecast-update rules.

The numerical helpers before the whole-mission entry point are AST-identical to
the preserved source. Other existing source, test and configuration files match
their snapshot hashes. One reference script and one test file were added.

## Preservation evidence

The frozen reference includes 14 short cases covering all methods and motion
models, both GP backends, pruning, filter/QP execution, fractional and partial
clocks, receipt loss, interior replanning, plan provenance and six failure paths.

Every case matched exactly after the ownership change and again after activation
consolidation. Only the named measured runtime paths are normalized; physical
times, budgets, IDs, scientific values, solver outcomes and record structure remain
compared. Frozen inputs, source provenance and the checker are hash-verified.

- [Reference instructions and coverage](reference/README.md)
- [Frozen reference manifest](reference/frozen-20260918/manifest.json)
- [Pre-change repeatability](reference/repeat-frozen-20260918/report.json)
- [Ownership-only comparison](reference/after-ownership/report.json)
- [Activation comparison](reference/after-activation/report.json)
- [Final source comparison](reference/final-parity/report.json)
- [Sensitivity controls on copied evidence](reference/sensitivity-controls.json)

## Validation

| Check | Result |
| --- | --- |
| Focused mission behavior tests after ownership change | 149 passed |
| Final full pytest suite | 1,023 passed in 87.13 seconds |
| Coverage, including configured branch measurement | 94.51%; required threshold 80% |
| Ruff lint | Passed |
| Ruff formatting | Passed; 85 files |
| Mypy | Passed; 44 source files |
| Independent exact-GP diagnostic | 11 passed |
| Reference comparator tests | 16 passed, included in the full suite |
| Independent Standards review | 0 findings |
| Independent Spec review of simulator changes | 0 findings |

The full suite includes the existing comparison, save/reload, failure, CLI and demo
checks. It was run once after the completed production changes. Quality commands
used the existing virtual environment directly because the earlier normal launcher
had a local-executable access issue. No dependency update was required.

Logs: `ownership-tests.log`, `full-tests.log`, `full-tests-status.json`, `lint.log`,
`format.log`, `types.log`, `static-status.json`, and `diagnostic.log`.
See [the two-axis review](code-review.md) and `implementation.patch` for review scope.

## Research meaning and next increment

This is evidence that the structural change preserves the covered behavior. It
does not establish recovery benefit or resolve the known source-consistency issues.
Planning remains synchronous and is not yet charged against simulated mission time.

The next bounded engineering increment is advancement through complete physical
ticks, checked against uninterrupted execution and these references. Predecision
copying, a distinct recovery mechanism and charged planning delay follow under the
approved research brief. The existing project and its historical findings remain
the starting point.

## Local version-control scope

The repository began without commits or a configured author. On 18 September 2026,
the user requested repository creation and selected a private GitHub repository.
The initial snapshot includes the complete runnable project and this increment's
tracking documents, preserved baseline and evidence. It supersedes the earlier
increment-only commit scope. The baseline archive remains the reproducible
pre-change source reference.

The explicit [initial commit manifest](../repository-setup/initial-commit-files.json)
records the included paths. Local environments, generated runs, temporary refactor
material and licensed papers remain outside version control.
