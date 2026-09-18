# 02: Give complete and failed missions one execution owner

Status: ready-for-agent
Execution: complete
Approval: user confirmed the testing seam and ticket order on 18 September 2026.

**What to build:** Existing experiments run through one internal owner of changing
mission state. Completed and failed results preserve the current scientific and
artifact contracts while no longer depending on a separate progress mirror.

**Blocked by:** 01 — Capture reproducible mission behavior references.

**Parent:** [Mission execution ownership spec](../spec.md)

- [x] The existing whole-mission entry point, supported configurations, returned schema and caller-visible exception behavior are unchanged.
- [x] Robot state, actual GP, active plan/budget, clock and interval state, records, counters and timers have one internal owner; the separately synchronized progress mirror is removed from success and failure paths.
- [x] All methods retain existing startup, sampling, prediction, planning, frame and motion ordering, including the different pre-observation and post-observation preview failures.
- [x] Failed outcomes preserve last accepted motion, attempted controls, actual receipts and assimilation flags, backend state and existing summaries without padding or replaying rejected data.
- [x] Existing planning/control/GP helpers and planner input restrictions remain intact; unsupported configurations and exceptions outside existing handled paths still propagate as before.
- [x] The current periodic/interior activation behavior remains equivalent; duplicate bookkeeping may remain until ticket 03, keeping this parity check attributable to ownership changes.
- [x] Captured references match under the reviewed comparison rules, relevant independent/provenance/failure tests pass, and completed/failed consumer validation succeeds.
- [x] Static quality checks pass; the change provides no public stepping, pause/resume, copying, recovery, delay or adapter framework.

## Verification

Compare complete artifacts against ticket 01's references and run relevant mission,
consumer and failure regressions. Review state ownership directly as an architectural
acceptance condition; behavior tests must not require private field names.

## Comments

Success and failure migrate together because they describe the same executed
mission. Splitting them into separate tickets would prolong the duplicated-state
risk. This ticket must be independently green before activation consolidation.

Completed 18 September 2026. Complete and failed missions share one private
execution owner. The progress mirror and nested sensing closure are removed;
numerical helpers and the public whole-mission interface are preserved. This slice
passed all 14 frozen comparisons, 149 focused mission tests and static checks
before activation bookkeeping was consolidated.

Evidence: [ownership comparison](../reference/after-ownership/report.json),
[focused test log](../ownership-tests.log), and
[final review](../code-review.md).
