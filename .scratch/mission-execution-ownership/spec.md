# Preserve mission behavior while concentrating execution ownership

Status: ready-for-agent
Approval: user confirmed the testing seam and ticket order on 18 September 2026.
Prepared: 18 September 2026.

## Problem Statement

The existing GP Attainability project already runs mapping missions and preserves
useful experiments. Its evolving mission state is distributed across local
variables, a sensing closure and a separate progress record used after failure.
This makes it difficult to change execution without accidentally changing
measurement history, plan provenance or failed-outcome evidence.

The researcher needs a trustworthy foundation for later ordinary-continuation and
recovery comparisons. The immediate task is to concentrate existing execution
ownership and demonstrate preserved behavior before introducing new capabilities.

## Solution

Keep the existing whole-mission interface and scientific behavior. One internal
mission execution owner will hold the state needed by successful and failed runs.
After demonstrating parity, consolidate the existing synchronous plan-activation
bookkeeping inside that owner. Existing experiments and artifact consumers continue
to work through their current interfaces.

Capture small, reproducible pre-change reference runs so the refactor can be
compared with independent historical outputs, rather than with another path through
the new implementation. This work establishes engineering preservation, not a
recovery result or a source-equation validation.

## User Stories

1. As the researcher, I want to run a mission through the existing entry point, so that my experiments continue to work.
2. As the researcher, I want the same scientific outputs for the same conditions, so that a structural change cannot masquerade as research improvement.
3. As the researcher, I want executable pre-change references, so that preservation has independent evidence.
4. As the researcher, I want source, configuration and environment provenance for references, so that comparisons can be reproduced.
5. As the researcher, I want a compact development check, so that restructuring does not require another expensive study.
6. As the maintainer, I want one owner of changing mission state, so that success and failure handling cannot drift apart.
7. As the researcher, I want initial sampling to retain its current position in each method's workflow, so that startup failure evidence stays accurate.
8. As the researcher, I want received and assimilated measurements distinguished, so that failed estimation updates remain interpretable.
9. As the researcher, I want the last accepted motion preserved after rejection, so that a failed mission never claims an unexecuted trajectory.
10. As the researcher, I want known failures and unexpected errors to retain their meanings, so that programming defects are not reported as scientific outcomes.
11. As the researcher, I want a common physical sensing clock and original deadline, so that replanning cannot add resources.
12. As the researcher, I want a partial final interval to retain its existing sampling behavior, so that it cannot invent information.
13. As the researcher, I want measurement records to name the incoming plan, so that executed actions remain attributable.
14. As the demo reader, I want outgoing-plan and incoming-forecast identities preserved, so that a replan at a sampling time remains understandable.
15. As the researcher, I want interior P decisions to retain their timing, so that motion-triggered adaptation is preserved.
16. As the researcher, I want replanning to replace only future commands, so that recorded motion cannot change retrospectively.
17. As the researcher, I want both GP backends to retain their existing update and forecast semantics, so that this refactor does not change the estimator.
18. As the researcher, I want each supported motion/controller combination to retain its behavior, so that model comparisons remain meaningful.
19. As the researcher, I want planners to retain their current information access, so that simulation truth and future disturbances do not leak into decisions.
20. As the researcher, I want timing measurements to preserve their scope, so that computation is neither hidden nor counted twice.
21. As the demo user, I want completed and failed artifacts to remain readable, so that the working project stays usable throughout the changes.
22. As the maintainer, I want independent numerical and provenance tests retained, so that reorganizing code cannot remove its scientific checks.
23. As the researcher, I want historical experiments and protocols preserved, so that earlier findings remain auditable.
24. As the researcher, I want a clear completion gate for this increment, so that architecture work leads back to the controlled recovery experiment.

## Implementation Decisions

1. **One existing external seam.** The whole-mission `run_mapping` entry point,
   accepted configurations, return schema and caller-visible error behavior remain
   unchanged. Keep the new execution owner internal to the existing simulation
   module. Existing comparison and persistence interfaces remain its consumers.
2. **One execution owner.** Own robot state, received-data GP, active plan and
   budget, current reference/goals, clock/loop position, forecast links, records,
   counters and timers together. Read that ownership in normal and failed outcomes;
   remove the separately synchronized progress mirror. Short-lived local values
   are allowed; shared state passed through a large parameter bag is not the goal.
3. **Preserve startup.** Sweep/greedy nominal preplanning precedes the initial real
   measurement. If it fails, preserve the empty measurement prefix and existing
   fallback initial motion evidence. Adaptive preview failure occurs after the
   initial assimilation. Keep these distinct paths intact.
4. **Preserve event order.** Accepted motion is committed and recorded before an
   interior P trigger. At sampling arrival, collect and assimilate under the
   incoming plan, predict, activate the outgoing plan where appropriate, then
   record the frame. Preserve the original deadline and partial-tail behavior.
5. **Preserve failure scope.** Only currently handled `ControlFailure` paths become
   failed artifacts. The existing GP-update exception translation stays confined
   to that update path; other prediction, configuration and programming errors
   retain their existing propagation. Failure serialization uses the current
   backend state and receipt/assimilation evidence without replaying rejected data.
6. **Preserve information access.** The execution owner may hold simulation truth
   for sensing and evaluation. Planner calls retain their existing allowed inputs;
   the owner itself, truth and future noise/dropout realizations are not planner
   inputs. SOGP may still depend legitimately on received measurement values.
7. **Preserve numerical behavior.** Reuse GP, planning, motion, safety, budget and
   nominal-rollout implementations. Existing real alternatives justify their
   current seams. Add no general adapter framework or alternate execution engine.
8. **Consolidate activation after parity.** Centralize common active-plan identity,
   provenance and event bookkeeping. Preserve periodic and interior distinctions:
   their trigger metadata differs, interior replacement touches only future
   reference entries, and their no-future-sample forecast updates are not identical.
   Keep this operation internal, synchronous and dependent on the same state.
9. **Preserve artifacts.** Retain statuses, records, schema, IDs, field meanings and
   summary calculation. Incoming sample plan, outgoing frame plan and incoming
   forecast identity remain distinct. Historical bundles remain unchanged.
10. **Preserve timing scope.** Planning remains synchronous and consumes no
    simulated time in this increment. Preserve measured timing categories,
    including failed planning and failure reconstruction, and their existing
    nesting. This does not fulfill the later charged-planning-delay requirement.
11. **Use small green increments.** Capture references before production edits;
    prove ownership parity before consolidating activation. Each implementation
    ticket includes its behavior checks, not a separate later testing ticket.

## Testing Decisions

The primary test seam is the existing whole-mission entry point. Tests inspect its
returned behavior and evidence. Existing comparison validation and save/reload
checks provide consumer coverage without introducing another execution interface.
Failure injection may use existing dependency hooks; assertions concern outcomes,
not the execution owner's fields or private method names.

### Reference capture

- Capture references from source verified against the preserved baseline before
  changing production code. Record exact source identity, full configurations,
  development seeds, runtime/dependency versions and reference hashes. Keep the
  capture instructions and failure triggers reproducible.
- Use short scenarios and small existing test grids. The selected references must
  collectively exercise all five methods; holonomic, original USV and curvature
  USV motion; exact and SOGP beliefs; and supported filter/QP execution. Include
  managed curvature-USV motion and a SOGP case with dictionary pruning. This is a
  representative set, not a full product of every configuration dimension.
- Include fractional sampling clocks, a deadline between sampling epochs, complete
  measurement loss, an actual interior P decision, and different incoming/outgoing
  plan identities. One case may cover several requirements. Record which cases
  actually exercise each behavior rather than relying on their configuration names.
- Cover the distinct startup-preview failure prefixes, a rejected execution step,
  planning failures initially and after a later received epoch, and a rejected GP
  update with received-but-unassimilated measurements. Existing failure-injection
  regression tests are prior art for deterministic triggers.
- Retain raw reference evidence and normalized scientific evidence. Canonicalization
  may remove only an explicit, reviewed list of measured performance fields.
  Physical times, deadlines, budgets, IDs, counts, solver decisions, iteration
  counts and scientific values remain. Never drop every field ending in `_s`.
- Verify repeatability in the recorded environment. Investigate any unexpected
  non-timing variability before setting a comparison rule; do not silently widen
  exclusions or rebaseline after a refactor. Demonstrate that the comparator catches
  changes to scientific values, physical time, provenance and failure status while
  allowing differences only in the listed runtime fields.

### Preservation checks

Retain the existing tests for deterministic artifacts; independent posterior
reconstruction; actual-measurement provenance; shared clock and partial deadlines;
no truth input to exact-GP planning; P triggers and retained plans; QP rejection;
SOGP receipt/assimilation differences; and curvature-USV invariants. These are
behavioral and numerical oracles, not redundant tests of internal structure.

Compare the refactored whole-mission results with the captured references. Keep
existing justified numerical tolerances in independent mathematical tests; they
do not authorize hiding changed event sequences or solver outcomes. Check timing
field presence, type, finite/nonnegative values where applicable and existing
accounting relationships separately from normalized-output equality.

Verify consumer compatibility with completed and failed comparison bundles and a
save/reload path. Existing CLI/demo checks remain part of regression validation.

Relevant preservation checks gate each production change. At completion, run the
repository lint, formatting, type and full coverage checks, plus the independent
GP diagnostic. Use the established direct virtual-environment commands if the
quality launcher's existing local-executable access issue persists; record that
distinction. Do not change dependencies merely to run this refactor.

### Completion criteria

The increment is complete when the progress mirror has been removed, both outcomes
read the same owned state, shared activation bookkeeping has one internal owner,
references match under the reviewed comparison rules, existing consumers remain
compatible, required checks pass and the result is reviewed against this spec.
No research performance improvement is required or claimed.

## Out of Scope

Public execution lifecycle interfaces; tick stepping; pause/resume; snapshots and
forking; new warning or recovery decisions; changing target/forecast/retention
semantics; asynchronous planning or stale-result policies; charging planning time
to simulation; changing sensing or disturbance models; new GP mathematics;
source-equation corrections; benchmark integration; a whole-repository rewrite;
new final-evaluation runs; changing historical results or protocols.

These remain later research or engineering increments under the approved brief.
Known source-consistency questions must still be resolved for components used in
new scientific claims. Structural preservation does not resolve them.

## Further Notes

The previous baseline passed 1,007 main tests with 94.52% coverage and 11 independent
GP diagnostic tests. Those are recorded prior results, not tests run while writing
this spec. The repository has no initial commit; preserve source using its verified
archive and manifest, and avoid treating the entire untracked tree as new work.

Supporting records are linked from the [review overview](review.md). The
approved dependency chain is reference capture, whole-mission ownership, then
synchronous activation. The user approved the tickets and testing seam; implementation can proceed in dependency order.
