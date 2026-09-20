# Make fixed-target priority explicit and concentrate plan selection

Status: ready-for-agent
Execution: complete
Parent: [spec](../spec.md)

- [x] A real-GP regression fails under the historical target-crossing behavior.
- [x] The fixed target takes priority only in the specified crossing case.
- [x] Ranking, retention and reasons have one private pure implementation.
- [x] Existing no-target, equality, ablation and failed-candidate behavior is tested.
- [x] Both demo reason tables explain the new decision.
- [x] Historical comparison, full/static/diagnostic checks and independent reviews pass.
- [x] Local changes are ready for commit and two-platform CI.

## Comments

This deliberately changes historical D025 for configured fixed targets. No prior
result is relabeled; the historical evaluator and immutable artifacts remain intact.

20 September: complete. See [completion evidence](../completion.md),
[the pilot verdict](../pilot-summary.md) and [independent reviews](../code-review.md).
The prototype is captured and pushed separately as `f54435a`; no recovery benefit
was observed. All 1,065 local tests pass at 94.66% coverage; 14 reference cases,
static checks and 11 independent GP diagnostics also pass. Remote results belong
to the resulting commit's GitHub quality workflow.
