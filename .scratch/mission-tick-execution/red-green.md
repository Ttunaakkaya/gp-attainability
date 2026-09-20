# Incremental execution: development checks

Approved testing seam: construction/read, advance and finish of the internal
mission execution owner; returned views and artifacts are the observations.

The implementation author recorded these successive tracer bullets:

1. Initial receipt and outgoing plan are complete before the first read.
   Red: `test_constructor_closes_initial_receipt_and_plan_before_reading`
   failed because `read()` was absent. Green: one interface test passed.
2. Advancing closes an interior physical tick or the whole arriving sample epoch.
   Red: `advance()` was absent (one failure, one pass). Green: the explicit cursor
   preserved the reached tick separately from the interval origin.
3. Finish closes the deadline once and returns isolated evidence.
   Red: `finish()` was absent (one failure, two passes). Green: three interface
   tests passed, including off-clock deadline behavior and terminal idempotence.

The independent preservation driver also failed while `finish()` was missing.
After the full interface existed, its first complete run passed all 14 expected
cases: 13 historical outputs and the separately recorded post-SOGP repair case.
The original historical comparator still reports that known numerical delta;
no frozen file or normalization rule was changed.

[Final preservation report](final-reference/report.json).
The finished interface suite contains 27 passing cases. Added checks cover interior
P replacement, startup and mid-mission failures, received-but-unassimilated batches,
immutable views, copied evidence, partial completion, timing, measurement loss,
pre-first-sample deadlines and unrelated exceptions. The focused suite passed in
2.15 seconds. Full-suite and review results are in the [completion report](completion.md).
