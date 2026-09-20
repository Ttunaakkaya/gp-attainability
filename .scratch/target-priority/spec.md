# Fixed-target priority in plan selection

Status: ready-for-agent
Base: `bf6bdf3`.
Date: 20 September 2026.
Authorization: the user requested continuing the research/prototype and improving
the existing code with the appropriate skills. The fixed mission target is already
an approved requirement; no new research objective or resource is introduced.

## Question and scope

Can a target-directed choice among the same evaluated routes make a useful
difference? First resolve a prerequisite: historical P may retain a route predicted
to miss its target even though an accepted alternative is predicted to meet it.
The [source investigation](../../docs/research/recovery_mechanism_pilot_2026-09-20.md)
identifies this as a selection-rule change, not proof of recovery benefit.

Prototype the exception and compare it with historical P, zero-margin P, ordinary
adaptive B2 and periodic B3 in a small development pilot. Keep the target, deadline,
team, sensing, safety and candidate-generation rules fixed across corresponding
arms. Preserve negative outcomes and separate the selected route's forecast from
the best examined candidate. This pilot does not validate an ordinary-continuation
warning, charged planning delay, field accuracy or superiority.

## Validated rule and restructuring

Historical D025's switch margin remains in force except when
`best_mean <= target < retained_mean`. In that case choose the already-evaluated
best accepted candidate and record a specific target-crossing reason. Equality
meets the target, as in the existing mission success definition. Do not invent a
tolerance that relaxes the target. With no target, both candidates meeting it, or
both missing it, preserve the existing retention rule, tie breaks and failure cases.

Concentrate ranking, retention and its reasons in one private pure decision
function returning immutable scalar values. Keep candidate search, controller
rollouts, posterior forecasting and artifact construction in their existing modules.
Do not introduce a scheduler, public decision interface or general plugin layer.
Retain `target_risk.margin/status` as best-candidate assessments; selected forecast
values already have distinct fields. Update the demo's explanation of the new reason.

## Testing and preservation

Tests stay at the existing `manage_plan` public interface and the previously approved
whole-mission/read/advance/finish interfaces. The new private decision function is
not a new test seam. Use real GP/candidate evaluation; no mock numerical scores.
Develop one failing behavior at a time, then run focused checks, the complete suite,
independent diagnostics and separate standards/spec reviews.

Do not rewrite historical experiments or frozen references. Compare all 14 expected
reference cases and report every changed case honestly. The separate earlier SOGP
checkpoint remains the expected result for its single affected case. Preserve a
source-identified prototype on a throwaway Git branch; main keeps the validated rule
and evidence pointer. Commit the finished improvement and verify both CI platforms.

## Local tickets

- [Research and prototype](issues/01-recovery-prototype.md)
- [Selection refactor and validation](issues/02-target-priority-selection.md)
