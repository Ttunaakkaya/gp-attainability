# GP Attainability: prediction and recovery under execution constraints

Status: direction approved, 18 September 2026. The user confirmed proceeding with
`AGENTS.md` after clarifying that this work refines the existing project. The
experimental protocol, recovery algorithm, and architecture design remain to be
established through the work below.

Engineering progress: the first architecture increment is complete. Following
[the mission execution design recommendation](mission-execution-design.md), the
existing simulator now has one private mission-state owner and shared synchronous
plan-activation bookkeeping. All three approved tickets passed their preservation
checks; the [completion report](../mission-execution-ownership/completion.md)
records the 14 frozen comparisons, full tests and independent reviews.

The second increment adds advancement through complete physical ticks, immutable
diagnostic views and one-time finalization; see its
[completion report](../mission-tick-execution/completion.md). The independently
documented [CI numerical repair](../ci-portability/completion.md) precedes this
refactor. Next, return to the bounded recovery mechanism and estimator/source
questions. State copying, warning/recovery logic and charged planning delay remain
later work; these structural changes establish no new scientific improvement claim.

## Purpose and research question

The primary audience is Professor Hatanaka and his laboratory. The deliverable should
demonstrate a concrete result, careful experimental reasoning, and engineering the
user can explain. Portfolio value is secondary. Build on the user's GP-MPC, safety
filtering, and optimal-control experience; preserve existing evidence while allowing
algorithmic choices to change.

This is the next iteration of the existing GP Attainability / FIELDWORK project.
Build on its simulator, GP implementations, planners, controllers, tests, demo, and
recorded results. Refactor or replace specific code where justified by the research
needs; a ground-up rewrite or a separate replacement project is outside this scope.

**Question:** When motion execution falls behind a sampling plan, can an explainable
warning identify a likely missed GP-uncertainty target early enough for recovery
replanning to improve mission success within the original resources?

The hypothesis to test is that a prediction of the ordinary planner's remaining
mission, combined with a target-directed recovery decision, yields useful lead time
and additional target successes after the cost of computation is included. This is
an empirical hypothesis; prior work already contains threshold-directed planning
and hierarchical GP sampling/control. The distinct mechanism must be established
through focused literature work and experiments.

## Agreed mission contract

- **Target:** average GP uncertainty by the original deadline. Use mean latent field
  variance, consistent with the existing independent profile. Specify and freeze
  the evaluation region and averaging rule with each protocol.
- **Other outcomes:** maximum uncertainty, actual map RMSE, model-mismatch behavior,
  constraint violations, failures, and computation remain visible. Lower model
  uncertainty is reported separately from improved map accuracy.
- **Recovery authority:** change routes and sampling assignments. Keep the target,
  deadline, robot team, sensing limits, and safety constraints fixed.
- **First disruption family:** motion/execution problems. Develop separate controlled
  cases before mixing mechanisms. All methods receive the same known constraints.
- **Later scope:** measurement loss as a separate study; combined loss and execution
  problems are a bonus if preceding stages succeed.
- **Warning output:** an explanation and target margin. A negative margin means the
  named continuation predicts missing the target. Numerical failure probabilities
  are optional and require separate motivation and calibration.
- **Delivery sequence:** establish evidence in the Python simulator, then integrate
  the extension into the lab's benchmark. Benchmark integration is a planned second
  stage. A final demonstration must retain the same mission/measurement semantics.
- **Compute:** a substantial 6–8 hour evaluation, or an occasional longer isolated
  run, is acceptable. Avoid repeated long policy-training cycles. Measure pilot
  runtime before sizing a study; keep normal development feedback short.

## Model assumptions and source alignment

Q14 delegates the model choice to evidence from the paper and lab code. Direct
inspection confirms explicit single-integrator dynamics in ECC Eq. 2 (p. 305),
environmental-field learning in Eqs. 3–4 (p. 306), and deterministic cell transitions
(p. 309). The benchmark uses explicit turn-constrained kinematics. Neither inspected
source requires learning unknown vehicle dynamics.

The selected starting scope is therefore an explicit nominal motion model, known
constraints, and available robot poses, with execution errors observed as they occur.
Use a small holonomic case for source alignment and a declared turn-constrained model
for the USV-oriented study. Keep future disturbance realizations and simulator ground
truth unavailable to online planners. Motion-model learning is outside the first study.

Keep the source-paper model and benchmark model separately identified. Their dynamics,
objectives, and observation interfaces need not be identical. The fixed mean-variance
deadline target is our task definition; the paper uses a summed-variance decay objective.
For a fixed common evaluation grid the normalization can be stated explicitly, but its
numerical thresholds are not transferred unchanged. Motion disturbances,
mismatch tests, and the new fixed-deadline recovery task must be labeled as extensions
where they are not inherited from those sources.

The inspected benchmark provides kinematic motion and route/control interfaces, while
its existing field updater represents coverage importance. GP observations, delivery
events, and estimation require explicit integration. Reusing the benchmark does not
make its coverage metric a GP posterior variance.

Retain an exact-GP reference for numerical checks and make the role of SOGP explicit.
Do not transfer exact covariance-forecast properties to label-dependent SOGP pruning
without checking the approximation. Select the first study's estimator/backend after
the source and cost checks rather than changing estimation and recovery together.

## Proposed evaluation design

### Separate warning assessment from intervention benefit

Define an ordinary adaptive planner that keeps replanning from its actual state and
received data. B2 is a necessary strong comparator given the existing evidence; B3
and the current P remain useful references. Candidate generation, observation access,
decision opportunities, and computation must be recorded so recovery gains can be
separated from a larger search budget.

For diagnostic intervention comparisons, copy the complete simulation state before
the additional recovery decision. Select warning and fork events using information
available at that instant, before seeing future outcomes. One branch continues ordinary
adaptation and the other enables recovery. Pair hidden future exogenous disturbances
by robot and physical time. For state-dependent disturbances share the underlying
environment/process; resulting paths, safety interventions, samples, and beliefs may
differ naturally.
The warning is assessed against ordinary continuation, while recovery benefit is
assessed between outcomes. Thus an effective rescue does not turn a correct warning
into a false alarm.

Assess full missions as well as triggered branches: successes, failures, harmful
interventions, false alarms, missed warnings, and added computation all matter.
Diagnostic forks estimate the added intervention's effect at a common state; they
do not replace the full-system comparison. In full-mission comparisons, each system
pays for its own monitoring and planning. The ordinary baseline is not charged for
recovery-specific forecasting it does not use.
Multiple warning instants from one mission are correlated observations, not additional
independent missions. Include completed and failed missions with explicit failure
categories and denominators.

### Account for the time spent deciding

First verify prediction and intervention logic with controlled timing. Main validation
includes the complete warning/forecast/replanning delay. While waiting for a decision,
robots follow the active plan with ordinary feedback and safety filtering still
enabled, and sensing follows the original clock. Apply the same safety rules to all
methods as conditions change; a previously feasible command is not assumed to remain
feasible. Specify how a result computed from an older state is checked,
updated, accepted, or rejected when it arrives.

Measure latency under a documented hardware/load setup. Separate algorithm cost from
plotting and offline analysis, and avoid double-counting rollout time inside planning.
Use repeatable delay experiments to isolate timing effects and actual runtime
measurements to show practical cost. Ordinary and recovery methods get comparable
compute limits and the same rules for delayed decisions.

### Set targets and tests before final evaluation

Use development tasks to select target-setting rules, warning operating points,
practical effect thresholds, and study size. Freeze these before fresh evaluation.
Choose a declared range of mission difficulty, including ordinary successes,
potentially recoverable misses, and cases the tested methods fail to recover.
Preserve that whole declared range rather than selecting favorable cases afterward.

Keep old protocols and artifacts intact. Historical cases used to refine the new
method are development evidence for this phase. Fresh evaluation should vary relevant
starts, geometries, fields, and execution schedules, rather than treating new field
seeds as automatically new motion-planning problems.

## Proposed gates and stopping rules

1. **Trustworthy baseline:** preserve a recoverable source/config/test baseline; run
   the existing quality checks and independent GP diagnostic. Characterize relevant
   deterministic mission behavior and retain the historical experiment evidence.
   Resolve the flagged source-consistency issues in any component used for the new
   claims; passing existing tests alone does not settle the source audit.
2. **Observable mechanism:** a small controlled experiment explains when execution
   changes the target margin, why a recovery action differs from ordinary adaptation,
   and whether the action can affect a measurement before the deadline. Cases include
   no disruption, a recoverable disruption, and a miss without observed recovery.
3. **Useful warning and intervention:** evaluate lead time after decision latency,
   false alarms, missed failures, gained and lost successes, and cost. Choose numeric
   acceptance thresholds from development evidence before final evaluation; no effect
   size or warning duration is invented in this brief.
4. **Evidence beyond the pilot:** fresh paired missions satisfy the declared practical
   improvement criterion with uncertainty intervals. Report map error, maximum
   uncertainty, failures, mismatch sensitivity, and runtime alongside target success.
5. **Benchmark transfer:** after the mechanism and implementation pass their gates,
   preserve observation times, target semantics, constraints, and timing behavior
   in the actual lab benchmark. Revalidate comparative behavior there; a ROS launch
   or attractive trajectory alone is not a scientific transfer result.

If the recovery mechanism offers no useful benefit beyond ordinary adaptation and
matched computation, diagnose the reason with a bounded follow-up or revise the
hypothesis. Preserve the negative result. Gate decisions determine whether to proceed
to expensive evaluation and benchmark integration.

## Work sequence after shared understanding

1. Repository skill setup is applied: `AGENTS.md`, local Markdown tracking, default
   triage labels, and single-context domain documentation.
2. Resolve focused source/related-work questions and use small diagnostic prototypes
   where a question needs execution. Separate forecasting, recovery, and extra search
   when identifying a plausible mechanism.
3. Run `improve-codebase-architecture` with `codebase-design` against the agreed research
   needs. Likely inspection areas are simulation state, event/measurement records,
   forecast-versus-policy responsibilities, timing, and experiment evaluation. Select
   actual changes from that assessment; preserve useful existing modules.
4. Convert the agreed design into a spec and dependency-ordered local tickets.
5. Implement bounded changes with behavioral tests and review. Distinguish changes
   that preserve behavior from changes to the scientific method or experiment model.
6. Evaluate the first study, then pursue benchmark transfer and later sensing-loss
   work according to the evidence and agreed priorities.

## Review points and sources

The user confirmed this direction and chose `AGENTS.md`. Numerical protocol settings,
the recovery algorithm, and final interfaces need research/pilot/design work.
No professor-contact deadline has been supplied.

- [Interview decisions](interview.md)
- [Current glossary](../../CONTEXT.md)
- [Source motion assumptions](../../docs/research/source_motion_assumptions_2026-09-18.md)
- [Lab fit](../../docs/research/lab_fit_2026-09-18.md)
- [Benchmark source inspection](../../docs/research/benchmark_transfer_scope_2026-09-18.md)
- [Preliminary prior-art check](../../docs/research/recovery_question_prior_art_2026-09-18.md)
- [Existing project review](../../reports/deep_review_2026-09-18_TR.md)
