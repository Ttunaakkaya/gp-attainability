# Independent review

Date: 20 September 2026.
Fixed base: `bf6bdf3f05f43e6fc0c7d4c04ff2b5ccb00addb9`.
Production diff: `git diff bf6bdf3 -- src scripts tests`.
Both reviewers were read-only and did not author the production implementation.

## Standards

**Zero findings.** Repository standards and the 12-smell checklist were reviewed.
The private decision function concentrates ranking, retention and explanations,
and returns immutable scalar evidence. Tests use the existing public interface
and real GP evaluation. Two explanation-table additions follow the current Python
and browser consumers; a cross-language abstraction would add unnecessary scope.
The research/documents author's own files were excluded from this production review.

## Spec

**Zero findings.** The precise target-crossing rule and inclusive equality are
implemented. All other ranking/retention behavior, existing interfaces and
candidate-best reporting remain intact. Tests cover target crossing, equality,
both non-crossing outcomes, no target, rejected candidates and retention ablation.
Both explanation tables and the seven-reason completeness check are updated.
There is no scheduler or speculative framework.

Full checks, prototype capture and CI are separately validated by the parent;
the reviews do not stand in for their results.

## Evidence audit

A separate read-only review checked the prototype protocols, import/call-site
selection, all 30 raw outcomes, byte hashes, target and resource equality, all six
priority/historical route and receipt pairs, absence of crossing opportunities,
and grid-reachability diagnosis. **Zero substantive issues.** Main keeps the
[verdict and immutable evidence pointer](pilot-summary.md).
