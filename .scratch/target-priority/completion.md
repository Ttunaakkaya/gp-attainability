# Target-priority selection and bounded recovery pilot

20 September 2026. Implementation and local validation complete.

## What changed

Plan ranking, retention, target-crossing priority and decision reasons now live in
one private pure function. It returns frozen scalar evidence, leaving candidate
rollouts, GP forecasting and artifact assembly with their existing owners. The
public `manage_plan` and mission-execution interfaces remain unchanged.

When an accepted best candidate predicts meeting the fixed target and the retained
route predicts missing it, the best candidate is selected even when its improvement
is inside the ordinary switching margin. All other hysteresis and tie-break rules
remain intact. Equality meets the target; no numerical tolerance relaxes it. Both
demo consumers explain the new reason. This is a deliberate D025 exception,
recorded as [D063](../../docs/decision_log.md), not a rewrite of historical results.

Existing `target_risk.margin/status` still describe the best evaluated candidate.
The selected forecast remains separately identified. No candidate search, planner
horizon, GP model, sensing clock, safety rule or physical resource was changed.

## Research result

Primary-source research led to an ExactGP prototype with historical P,
target-priority P, zero-margin P, B2 and B3. The original pilot and one predeclared
grid-resolution diagnostic comprise 30 comparison runs. **No recovery improvement
was observed**: there were no target-crossing opportunities and target-priority P
matched historical P in every route/receipt comparison. B2 succeeds in two of three
development tasks; the other arms miss the fixed target on both grids.

The coarse grid restricted candidate motion. A denser grid improved mapping but
still produced no added target success. Main retains the [verdict and evidence
pointer](pilot-summary.md); the prototype code, HTML and raw records are archived
on a separate branch at commit `f54435a`. The mechanism gate remains open.

## Validation

- [Red/green record](red-green.md): historical retention fails the real-GP crossing
  regression; the correction passes.
- [Focused checks](focused-tests.log): 109 passed, including 31 policy tests.
- [Reference comparison](final-reference/report.json): all 14 expected cases pass
  exactly under the unchanged runtime normalization. The earlier documented SOGP
  checkpoint remains separate from the original historical comparison.
- [Independent reviews](code-review.md): Standards 0 findings; Spec 0 findings.
  A separate evidence audit checked all 30 raw prototype records with no findings.
- Full suite: **1,065 passed in 365.54 seconds**, **94.66% coverage**.
- Ruff lint/format and Mypy (44 source files) passed; all 11 independent GP
  diagnostic tests passed. Subsequent edits only update documentation.
- [Source integrity](integrity.json), [full test log](full-tests.log),
  [full-test exit status](full-tests-status.json).

The frozen harness and reference artifacts are unchanged. The historical scenarios
do not exercise the corrected target crossing; the added behavior tests do. The
GitHub [quality workflow](https://github.com/Ttunaakkaya/gp-attainability/actions/workflows/ci.yml)
records Windows and Ubuntu results for each pushed main revision.

## Next step

Resolve candidate/action generation and the ordinary adaptive continuation under
matched information/search controls. The current route-plus-hold forecast is not
an ordinary-continuation warning. Do not expand state copying, delay scheduling,
large evaluation or benchmark transfer until a controlled recovery mechanism is
observable. Useful warning lead time, charged planning delay and recovery benefit
are still unvalidated.
