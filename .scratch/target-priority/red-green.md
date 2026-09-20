# Development evidence

Tests use the existing `manage_plan` public interface, real ExactGP computations
and existing candidate/nominal-stepper fixtures. The new private decision helper
is not tested directly.

1. A fixed target of 0.76410 lies between a real fixture's best forecast
   (~0.76409138) and retained forecast (~0.76411325). The new assertion expected
   replacement and failed under historical retention:
   [red output](red-target-priority.log), one failure.
2. The smallest target-crossing exception made all 24 policy tests pass:
   [green output](green-target-priority.log).
3. Boundary and preservation cases increased the policy suite to 31 passing tests.
   The subsequent structural extraction retained all of them without changing
   their interface. No acceptance threshold was widened.
4. The existing explanation completeness check failed when it saw the seventh
   decision reason: [red output](red-decision-language.log). Updating both existing
   consumer tables and the expected count made the focused suite pass.
5. [Focused suite](focused-tests.log): 109 passed. [Final reference comparison](final-reference/report.json):
   all 14 expected cases pass, including the prior independently documented SOGP
   checkpoint. The new crossing regression is deliberately a changed decision;
   the historical reference scenarios do not exercise that crossing.
