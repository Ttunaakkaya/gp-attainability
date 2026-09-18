# 03: Consolidate synchronous activation and verify preserved delivery

Status: ready-for-agent
Execution: complete
Approval: user confirmed the testing seam and ticket order on 18 September 2026.

**What to build:** Periodic replanning and interior P events update active-plan
provenance through common internal ownership, and existing experiments and saved
results retain their meanings after the complete refactor.

**Blocked by:** 02 — Give complete and failed missions one execution owner.

**Parent:** [Mission execution ownership spec](../spec.md)

- [x] Shared plan activation/bookkeeping has one internal implementation using owned state; planner selection, trigger conditions and synchronous activation timing are unchanged.
- [x] Plan IDs, preceding-plan links, starts, belief telemetry, received-sample keys, budgets and P decision events retain their current values and order.
- [x] Sampling-arrival records still name the incoming plan; frames may name the outgoing plan while retaining the incoming forecast identity. Both normal and no-future-sample paths remain correct.
- [x] Interior P replanning follows recorded motion and changes only future reference entries; branch-specific trigger metadata and forecast-update behavior are preserved rather than flattened into one rule.
- [x] Existing bounded-planner and control/GP failure semantics remain intact, including partial records and timing scopes.
- [x] All captured reference cases still match; independent numerical, provenance and failure regressions pass without weakening their assertions or regenerating references from changed code.
- [x] Existing comparison, saved-bundle reload and CLI/demo regression checks pass for the relevant completed and failed outcomes.
- [x] Repository lint, formatting, type, full coverage checks and the independent GP diagnostic pass; any launcher fallback is documented accurately.
- [x] A final review checks the change against the parent spec, confirms scope limits and records preservation evidence and any unresolved issue before marking the increment complete.

## Verification

Use the same reference comparator from ticket 01 plus existing behavior/consumer
checks. Perform the final quality pass once the completed change is stable, and
repeat only when fixes or unresolved concerns justify it. Report preservation
without claiming a recovery benefit or charged planning-delay validation.

## Comments

The dependency on ticket 02 deliberately isolates two changes: state ownership
must demonstrate parity before repeated activation bookkeeping is consolidated.
No public activation interface or delayed-plan scheduler is introduced.

Completed 18 September 2026. Periodic and interior P activation share plan
provenance and event bookkeeping, with branch-specific reference and forecast
updates retained. All 14 frozen cases still match. The final suite passed 1,023
tests with 94.51% coverage; lint, formatting, types and 11 independent GP diagnostics
also passed. Standards and spec reviews reported no findings. Existing archived
tests were not modified, and no new recovery or delay behavior is claimed.

Evidence: [activation comparison](../reference/after-activation/report.json),
[final comparison](../reference/final-parity/report.json),
[completion report](../completion.md), and [review](../code-review.md).
