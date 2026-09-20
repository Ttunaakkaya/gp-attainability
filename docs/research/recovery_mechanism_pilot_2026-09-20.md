# A bounded recovery mechanism pilot

20 September 2026. Recommendation, not a research result or a replacement protocol.
Repository source inspected at `bf6bdf3f05f43e6fc0c7d4c04ff2b5ccb00addb9`.
This note applies the approved [research brief](../../.scratch/research-refinement/research-brief.md)
and preserves the historical experiments. Public primary sources were reopened for
the specific claims below; this is not an exhaustive novelty search.

## Recommendation

Start with **target-aware plan retention**, ExactGP, and a small holonomic mission.
At an existing decision instant, use the same accepted candidates already scored by
P. If the retained candidate predicts missing the fixed target and another candidate
predicts meeting it, test overriding the normal switching margin. Otherwise keep
ordinary P's selection unchanged. This asks a concrete question: does a target-aware
exception to hysteresis improve deadline success beyond ordinary adaptive planning,
without obtaining extra candidate search?

Treat the first experiment as a diagnostic of this decision rule. It cannot yet
establish a warning about ordinary continuation, useful warning lead time, charged
planning delay, or recovery under unknown future disturbances. Those require the
continuation and timing checks below. The existing [M4 implementation](../../src/attain_sampling/attainability/policy.py)
already supplies the candidate scores and retained-plan check, so this experiment
does not require replacing the planner or estimator architecture.

## The observable gap in the current code

`manage_plan` selects the smallest mission-end mean variance, then retains the
previous plan when the improvement is no larger than `switch_margin * current_mean`.
The configured target is used only afterward when reporting `target_risk`; it does
not participate in selection. The risk status and `margin` describe the **best
accepted candidate**, while the record also contains the selected candidate's value.
Consequently, a positive reported candidate-set margin does not establish that the
plan actually selected predicts success. These are direct source observations,
not defects inferred from a paper. [Selection and reporting source](../../src/attain_sampling/attainability/policy.py)

The preserved [retention probe](../../reports/audit_retention_probe_2026-09-18.json)
demonstrates the distinction: the retained/selected forecast is
`0.764094979487776`, the best candidate is `0.7640913812127328`, and the constructed
target is `0.7640931803502544`. The candidate gain is about `3.60e-6`, well below the
recorded switching margin `0.00887765449869795`. This is a synthetic contract
counterexample; the target was placed between the values. It is neither a practical
effect size nor fresh evaluation evidence.

For the prototype, record two named margins, `target - selected_forecast` and
`target - best_candidate_forecast`, with the continuation each describes. Preserve
the historical schema and records. Any new production selection rule would be a
versioned method change to [decision D025](../decision_log.md), not a silent
correction of an already evaluated baseline.

## Why use ExactGP first?

With fixed kernel and Gaussian observation-noise parameters, GPML Eq. 2.24 gives a
posterior covariance determined by input locations, independent of their observed
values. This supports forecasting latent variance at nominal future sample sites
without knowing the field. It does not imply that a realized field's RMSE equals
that variance. [GPML Chapter 2, Eqs. 2.22-2.24 and discussion on p. 18](https://gaussianprocess.org/gpml/chapters/RW2.pdf)

The repository's [ExactGP](../../src/attain_sampling/gp/exact.py) exposes that
operation as `fantasy_variance`, conditioning jointly on future noisy locations
without mutating the real belief. Its fixed numerical jitter and physical noise
must remain identical across comparisons. For the independent profile, current
[B2 selection, nominal tracking and P integration](../../src/attain_sampling/sim/mapping.py)
use covariance and physical state for motion decisions. Thus a nominal adaptive
continuation can remain independent of future labels **while that policy/controller
contract remains true**. This is an inference from the inspected implementation;
it does not cover mean-dependent policies, online hyperparameter fitting or the
separate ECC controller profile.

The sparse alternative has a different contract. Csató-Opper's deletion score in
Eq. 27 contains the mean coefficient `alpha`; Eq. 25 changes the posterior's
covariance representation after the selected basis vector is removed. The online
update includes the observed value, so future basis selection cannot generally be
predicted from future locations alone. [Csató and Opper, Sections 3.2-3.3, Eqs. 25-27](https://publications.aston.ac.uk/id/eprint/40231/1/NCRG_2001_014.pdf)

The repository directly implements that score in `_prune`. Its
`fantasy_variance` instead freezes the current approximate posterior; it does not
simulate future admissions and removals. Inventing zero-valued future observations
and treating their pruned covariance as a label-free prediction would change the
scientific meaning. Keep SOGP for a later, explicitly approximate sensitivity study,
after a same-data comparison characterizes forecast error and cost.
[SOGP source](../../src/attain_sampling/gp/sogp.py), [existing estimator contract](../M3_SOGP.md)

ExactGP is an interpretability choice for a small pilot, not a claim that its cost
is negligible or that it should replace SOGP everywhere. Measure complete decision
wall time before choosing a larger study. Nothing in this recommendation requires
policy training or a GPU.

## Plan-plus-hold is not ordinary continuation

P evaluates each short route followed by holding its endpoint at every remaining
sensing epoch. The [source](../../src/attain_sampling/attainability/policy.py) and
[decision D024](../decision_log.md) make that continuation explicit. A successful
nominal route-plus-hold forecast is conditional evidence for that candidate under
the stated execution and sensing assumptions. Its failure says nothing about all
other routes. In particular, the ordinary policy may replan after the next received
measurement and do better or worse than the hold continuation.

Therefore a warning about **ordinary continuation** must roll out the named
ordinary policy, preserving its normal decision instants, retained plan, global
sample clock, physical constraints and nominal sensing assumptions. Do not replace
that policy with a frozen route or the hold suffix and call the resulting error a
warning error. Likewise, do not use a simulation of hidden future disturbances or
true field values as an online forecast. Offline realized paired branches may use
the shared hidden disturbance process to measure outcomes; that is a different role.
[Agreed vocabulary](../../CONTEXT.md), [evaluation contract](../../.scratch/research-refinement/research-brief.md)

Threshold-directed informative planning is already established: Suryan and Tokekar
minimize measurement/travel resources subject to pointwise uncertainty requirements,
under fixed GP hyperparameters. Their formulation differs from this project's fixed
deadline and mean-variance target, but adding a threshold is not by itself a novelty
claim. [Paper, Sections II-D and III](https://arxiv.org/html/1909.01895v2)

Execution remains a real distinction to test: the inspected uncertainty-guaranteed
IPP paper reports an AUV run missing its target at some evaluation locations and
attributes path deviations to currents and motion constraints omitted by its TSP
planner. That motivates checking realized execution, not an assertion that this
prototype remedies those effects. [Jakkala et al., v3, Appendix C](https://arxiv.org/html/2602.05198v3)

## Smallest useful experiment

1. **Decision check.** Replay the same accepted candidate records through ordinary
   retention and the target-aware exception. Include both candidates meeting the
   target, only the alternative meeting it, both missing, no retained candidate,
   and exact threshold equality. Preserve candidate budgets and scores. A constructed
   straddling target is acceptable here only when explicitly labeled a logic test.
2. **Execution pilot.** Use short ExactGP missions and one declared motion-disruption
   family, initially with controlled zero decision delay. Freeze a common target
   from development tasks before evaluating the mission comparisons; do not fit it
   between each pair's final outcomes. Compare ordinary P, target-aware P and P with
   zero switching margin. Keep B2 adaptive greedy and B3 periodic replanning visible
   as strong mission-level comparators. The zero-margin control tests whether removing
   hysteresis generally explains an apparent gain.
3. **Continuation check.** Distinguish the selected route-plus-hold margin, the nominal
   ordinary-policy deadline margin, and the realized ordinary outcome. Record their
   disagreement instead of treating them as interchangeable. Include no disruption,
   disruption with a useful intervention, and misses no tested intervention rescues;
   if a category is absent, report it rather than manufacturing a success.
4. **Decision gate.** Report gained and lost target successes, final mean/max variance,
   actual map RMSE, plan changes, failures and complete decision cost. If gains occur
   only for targets within tiny post-hoc intervals, or zero-margin P explains them,
   preserve that result and reconsider the mechanism before building a large recovery
   framework. Any follow-up warning study must add original-clock planning delay and
   stale-plan acceptance rules before claiming practical recovery benefit.

These are proposed engineering and experimental controls derived from the agreed
brief, not guarantees supplied by the cited papers. The full-system scientific
question remains open even if the decision check passes.
