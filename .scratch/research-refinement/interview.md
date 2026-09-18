# GP Attainability refinement interview

Status: research direction confirmed; `AGENTS.md` setup applied. The algorithm
and implementation design remain open.
Updated: 18 September 2026.

This note records the current user's answers. It is not an implementation spec or
a replacement masterplan. Existing experiments, reports, and negative results remain
evidence for the next research decisions.

## Confirmed priorities — round 1

- Primary audience: the professor and laboratory the user hopes to join for a
  master's degree and future research collaboration. Portfolio value is secondary.
- Desired outcome: a concrete, demonstrated research result. "Attainable" in the
  user's request means feasible to complete with solid results; it does not itself
  select a mathematical attainability theorem as the project objective.
- Preserve the motivating problem and existing evidence. Algorithm choices may be
  simplified or replaced on their merits; the current P method is not mandatory.
- Laboratory alignment matters. The next direction should build on the user's
  education and prior technical experience.
- The user is willing to devote substantial personal effort. See round 2 for the
  clarified compute tolerance; no delivery or professor-contact date is agreed.
- Work should proceed through understanding and research refinement, architecture
  design, implementation with validation, and subsequent extensions.

## Confirmed choices — round 2

- Strongest areas reported by the user: GP-MPC, safety filtering, optimal control
  generally, computer vision, and RL/ML. Do not treat every topic in historical
  background notes as an equally strong area.
- Primary empirical aim: A, early prediction that a fixed mapping target is likely
  to be missed, followed by replanning that measurably improves target attainment.
- A substantial evaluation run lasting 6–8 hours is acceptable; an isolated run may
  take longer. The objection is repeated, training-heavy work on the order of
  30–40 hours to learn a policy, as in RL projects. This is not a strict GPU ban or
  a hard eight-hour cutoff. Short development feedback remains a recommendation.
- Selecting aim A does not settle a method or establish novelty, calibrated
  probabilities, or a theoretical guarantee. Subsequent rounds refine its scope.

## Confirmed choices — round 3

- The mission target is fixed GP uncertainty. Actual map error and model mismatch
  are checked separately, and improvements must be described at the level the
  evidence supports.
- Recovery may change routes and sampling assignments. The original target,
  deadline, robot team, sensing limits, and safety constraints stay fixed.
- First establish the result in simulation. After sufficient validation, integrate
  with the lab's own benchmark so the final demonstration builds on the lab's work.
  Benchmark integration is a planned second stage, not merely an optional extension.
- Round 4 resolves the uncertainty aggregation, first disturbance family, and
  warning format. Evidence required before transfer still needs specification.

## Confirmed choices — round 4

- Average GP uncertainty is the first primary target; maximum uncertainty is
  reported separately. Actual map error and model mismatch checks remain required.
- Motion/execution problems anchor the first study, connecting to the user's
  control background and the lab benchmark.
- Measurement loss is a later separate study. Combining measurement loss with
  execution problems is a bonus if the preceding work goes well, not a condition
  that must expand the first study.
- Start with an explainable warning and a predicted target margin. Evaluate warning
  lead time, false alarms, missed failures, and recovery benefit. Numerical failure
  probabilities are optional and require a demonstrated purpose before being added.

## Confirmed choices — round 5

- Q14 delegates the predictor's motion assumptions to what matches the paper and
  lab's previous work. Direct PDF and benchmark-code checks support explicit nominal
  kinematics and available robot poses. The GP learns the environmental field;
  learning unknown vehicle dynamics is outside the first study. Execution errors
  and mismatch tests are declared extensions, not attributed to the source paper.
- Q15 requires planning delay in the main validation. First verify the decision
  logic under controlled timing, then evaluate measured delays and late-arriving
  plans while the mission clock continues.
- The source check is `docs/research/source_motion_assumptions_2026-09-18.md`.
  All eight source-paper pages were visually inspected for that bounded question.
- The review draft is `.scratch/research-refinement/research-brief.md`. It combines
  the user decisions with proposed validation criteria and the subsequent workflow;
  shared understanding was subsequently confirmed as recorded below.

## Scope clarification and approval

- The user clarified that this is refinement and extension of the existing GP
  Attainability / FIELDWORK project, not a new project or a ground-up rewrite.
  Preserve useful code, tests, demo, and experimental evidence; change specific
  modules where the agreed research and maintainability needs justify it.
- After confirming that the installed skills will guide that incremental work,
  the user instructed: "alright then lets move forward with the agents.md then".
- The research direction is approved. `AGENTS.md` and the three `docs/agents/`
  configuration files have been created from the reviewed setup draft.

## Existing background records

The historical note at
`docs/handoffs/2026-09-08/Hatanaka_Proje_Karari_ve_Uygulama_TR.md` records mechatronics,
GP-MPC, numerical optimization, model predictive safety filtering, and an active
learning prototype. It identifies Hatanaka Lab as the intended laboratory.
These are prior records, not a new verification of the user's current education or
implementation ownership. The user's current self-assessment is recorded in round 2.

A focused primary-source lab check is recorded in
`docs/research/lab_fit_2026-09-18.md`. Its suggested research directions are inputs
to the interview, not accepted method choices or evidence of novelty.

The subsequent bounded source inspection is
`docs/research/benchmark_transfer_scope_2026-09-18.md`. It identifies kinematic
vehicle/route interfaces and a coverage-importance updater in the inspected lab
code; GP observation acquisition and delivery require explicit integration. It is
not an executed compatibility check or a complete repository audit.

`docs/research/recovery_question_prior_art_2026-09-18.md` records a preliminary
three-work comparison. Threshold-directed GP planning already exists, and one
inspected study reports execution-related target misses. The new study must specify
what online prediction and recovery add beyond ordinary replanning; novelty remains
unestablished. These findings do not choose the disturbance or warning claim level.

## Evidence that informs the next decisions

- The masterplan's early-warning/recovery emphasis differs from the main
  experiments' primary RMSE outcome. The next primary question must be explicit.
- The current reports do not demonstrate P's primary RMSE superiority or earlier
  warning, and report substantial planning costs. They also report narrower
  uncertainty/arrival benefits and a strong adaptive-greedy baseline, B2.
- Refer to `reports/deep_review_2026-09-18_TR.md`, `docs/M6_PROTOCOL.md`, and the
  milestone reports for the evidence and its limits. No test suite or experiment
  has been rerun as part of this interview.
- Source inspection found concentrated responsibilities in `sim/mapping.py`,
  dictionary-based event/decision records, and hard-coded historical figure inputs.
  These are architecture candidates; no replacement interfaces have been selected.
- Inspection for aim A confirmed that `eval/m6.py:560` scores warnings against the
  same method's eventual mission outcome. A warning followed by successful recovery
  would therefore count as a false alarm. This implements the old protocol, but
  cannot distinguish rescue from an unnecessary warning for the new research aim.
- A proposed evaluation approach is to compare ordinary replanning and an added
  recovery intervention from the same pre-intervention state with paired future
  disturbances. The reference behavior and scoring criteria still need agreement;
  this note does not authorize an implementation or replace the frozen protocol.
- Current success uses final mean latent GP variance, not true map RMSE
  (`docs/M6_PROTOCOL.md`, Fixed mission target). Current P warnings use the best
  examined candidate, rather than explicitly predicting failure of the ordinary
  policy without an added recovery action. Its forecasts assume no future losses
  or disturbances (`attainability/policy.py:527`). These distinctions must inform
  the new question and evaluation design.
- The adaptive B2 baseline already replans from actual posterior/positions/headings
  and uses turn-limited controller predictions for USV candidates
  (`sim/mapping.py:593`, `:1423`). A fair no-recovery branch must retain its ordinary
  adaptation. B3 also sees actual state; existing P additionally changes candidate
  generation. An apparent benefit must be separated from extra search or compute.
- Current planning wall time is logged but does not advance the mission clock
  (`sim/mapping.py:1420`, `:1605`, `:1635`). Complete decision latency, hardware/load,
  and robot behavior while awaiting a plan need explicit treatment if computation
  is charged against the mission. Rollout time is already included in planning;
  counting both again would overstate cost.
- Proposed paired-branch principle: start from the same complete belief, vehicle,
  active-plan, and clock state; keep common keyed future disturbance schedules
  hidden from both planners. Different routes naturally produce different sample
  locations and subsequent beliefs, which must not be artificially forced equal.

## Remaining checkpoint and research/design work

1. Focused research/pilots: a distinct recovery mechanism, estimator choice,
   target-setting procedure, practical effect/lead-time criteria, and study size.
2. Design: faithful paired continuations, delayed-plan handling, timing measurements,
   and behavior-preserving module changes before new method implementation.
3. Transfer: effective benchmark configuration, observation semantics and safety
   behavior, followed by revalidation of the chosen mechanism.
4. No professor-contact deadline has been supplied; it is not a blocker or a reason
   to invent a fixed project duration.

## Workflow state

Use `grill-with-docs` to resolve the decisions, with bounded research or prototypes
where facts cannot be settled in conversation. Record domain terms in `CONTEXT.md`
only as they are agreed. Propose ADRs only for substantive, hard-to-reverse trade-offs.
Research findings are inputs to the interview, not automatically accepted decisions.

The user selected Local Markdown tracking, default triage labels, and `AGENTS.md`.
The active setup is `AGENTS.md` plus `docs/agents/*.md`. The original review artifact
at `tmp/matt-pocock-setup-draft.md` is retained as the applied setup record.

## Mission execution design step — 18 September 2026

The user asked to proceed with `codebase-design` after clarifying that the research
grilling was already complete. Reuse the confirmed answers; do not restart that
interview or require the user to invoke skills individually.

Three independent designs were compared for the first recommended architecture
candidate. The engineering recommendation is an internal mission execution owner,
with the existing `run_mapping` interface preserved. First establish historical
behavior parity; then add advancement through complete physical ticks. Predecision
state copying, recovery choices and charged planning delay remain later increments.

See [the design recommendation](mission-execution-design.md) for contracts,
alternatives, code evidence and preservation checks. This turn produced design
documentation and glossary additions only. No implementation or new research
result is claimed. The next workflow step is a bounded implementation spec and
local tickets for the state-ownership refactor.

## Implementation-spec draft — 18 September 2026

The user then requested the next step/skill. `to-spec` and `to-tickets` produced
[a review packet](../mission-execution-ownership/review.md) containing the complete
spec and three draft tickets: capture references, concentrate whole-mission
ownership, then consolidate synchronous plan activation. The testing seam remains
the existing whole-mission entry point, with current consumer checks retained.

The installed skills explicitly request confirmation of the testing seam and
approval of the ticket breakdown before publication. The concrete drafts are
ready; this combined review checkpoint is pending. No implementation tickets have
been published as agent-ready, and no source refactor or new test run occurred
during this documentation step.

## Implementation authorization — 18 September 2026

The user replied: "yes i approve if everything is good move to the next task/skill".
The testing seam and three-ticket order are approved. The spec and individual
tickets have been published under the local mission-execution-ownership feature.
`implement` and `tdd` are now being used in dependency order, beginning with
source-verified reference capture. No repeated approval of these decisions is needed.

## Implementation completion — 18 September 2026

All three approved tickets are complete. Source-verified references were captured
before production edits; all 14 cases match after state ownership and activation
changes. The final checks passed: 1,023 tests, 94.51% coverage, lint, formatting,
types and 11 independent GP diagnostics. Separate standards and spec reviews
reported no findings. Existing scientific helpers and archived tests are unchanged.

See [the completion report](../mission-execution-ownership/completion.md) for evidence.
The next bounded engineering increment is advancement through complete physical
ticks. Paired state copying, recovery choices and charged planning delay remain
later increments, and no recovery benefit is claimed by this refactor.
