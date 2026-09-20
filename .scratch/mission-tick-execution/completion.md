# Complete-tick mission execution

20 September 2026. Implementation and local validation are complete.

## What changed

The same mission execution owner now supports construction, `read()`, `advance()`
and `finish()`. Construction closes startup. Each advance performs one physical
transition and all work due there, including sampling, assimilation, planning and
records. The ordinary `run_mapping` entry point delegates to this execution path.

Immutable views expose the last physically reached tick/time, positions/headings,
active-plan identity and observation counts. A rejected motion leaves the preceding
physical state; failures after arrival preserve the reached state and real receipts.
Read operations do not run GP prediction or planning and use owned counters.

Terminal processing runs once. Further advancement leaves it unchanged, and each
artifact read returns an independent copy. Caller pauses while running contribute
to elapsed wall runtime but do not move simulated time. Timing freezes at termination.

No predecision copying, recovery intervention or charged planning delay is added.
Those remain research capabilities to establish after this bounded foundation.

## Evidence and validation

All 22 configuration/control/numerical definitions preceding `run_mapping` remain
AST-identical to commit `8314727`. The existing methods, model equations, planners,
sensing clock and failure policies are preserved.

The independent [preservation driver](../../scripts/check_mission_execution.py)
uses the frozen harness and its explicit timing-only normalization. It compares
real incremental execution with 13 untouched historical cases plus the separately
identified SOGP checkpoint from the [numerical repair](../ci-portability/completion.md).
The historical files remain immutable and the known numerical delta remains visible.

- [Approved interface and spec](spec.md)
- [Implementation ticket](issues/01-complete-tick-advancement.md)
- [Red/green development record](red-green.md)
- [Final preservation report](final-reference/report.json): all 14 expected cases pass.
- [Independent standards and spec reviews](code-review.md): zero findings in each.
- [Integrity checks](integrity.json): helper equality and reviewed source hashes.
- [Full test log](full-tests.log) and [exit status](full-tests-status.json).

The final suite passed **1,057 tests in 114.90 seconds**, with **94.61% coverage**.
This includes 27 new interface cases. Ruff lint and formatting passed, Mypy passed
for 44 source files, and all 11 independent exact-GP diagnostics passed. No full
suite was rerun for the subsequent documentation-only changes.

Run the preservation check with a new output directory:

```powershell
.\.venv\Scripts\python.exe scripts/check_mission_execution.py --output tmp/tick-reference
```

The original historical comparison intentionally remains false for the documented
SOGP repair (34 numeric fields, maximum absolute delta `2.1094237467877974e-15`).
The final exact comparison against the 13 historical cases and the independently
captured post-repair checkpoint passes. Neither the frozen harness nor original
reference manifest was changed.

GitHub runs the same lint, format, type and full-test checks on Windows and Ubuntu
for the committed revision; [workflow runs](https://github.com/Ttunaakkaya/gp-attainability/actions/workflows/ci.yml)
identify each revision's remote result. The preceding numerical repair's two-platform
success is recorded separately in its linked completion report.

## Next research work

Return to the smallest controlled recovery experiment and relevant estimator/source
questions. The new interface gives a complete-tick observation point; it does not
provide a predecision fork or validate an improvement over ordinary replanning.
The fixed target, deadline, robot team, sensing limits and safety rules remain the
approved mission contract.
