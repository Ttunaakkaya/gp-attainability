# Test the target-priority decision in a bounded pilot

Status: ready-for-agent
Execution: complete
Parent: [spec](../spec.md)

- [x] Inspect primary sources and current selection/forecast behavior.
- [x] Produce the throwaway logic demo and predeclared development pilot.
- [x] Compare historical P, target-priority P, zero-margin P, B2 and B3.
- [x] Record the verdict, limits and reproducible prototype branch/commit.

## Comments

The source note is complete. Prototype work is isolated at
`tmp/recovery-prototype`, branch `codex/target-priority-prototype`, from `bf6bdf3`.
The tiny historical synthetic counterexample is not an empirical recovery result.

20 September: complete. See [completion evidence](../completion.md),
[the pilot verdict](../pilot-summary.md) and [independent reviews](../code-review.md).
The prototype is captured and pushed separately as `f54435a`; no recovery benefit
was observed. All 1,065 local tests pass at 94.66% coverage; 14 reference cases,
static checks and 11 independent GP diagnostics also pass. Remote results belong
to the resulting commit's GitHub quality workflow.
