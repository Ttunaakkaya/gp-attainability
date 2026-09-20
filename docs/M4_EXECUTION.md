# M4 — execution-aware plan management (policy P)

15 September 2026. Independent masterplan v2 M4 implementation on the M1 controller,
M2 timed candidate search and M3 belief backends. This is the proposed policy **P**,
not an ECC2025 reproduction and not evidence that P is better than B3. See the
[M4 development report](../reports/m4_results_2026-09-15.md) for measured evidence.

20 September 2026 update: the selection section below records the fixed-target
priority correction. Earlier implementation descriptions and measured results
remain historical evidence; the correction does not rerun or replace them. See
[the current spec](../.scratch/target-priority/spec.md) and
[the bounded mechanism investigation](research/recovery_mechanism_pilot_2026-09-20.md).

## What P adds to B3

B3 replans periodically from the real posterior and scores each candidate on the
geometric assumption that a robot arrives at its planned cell by the sampling
deadline. P keeps that candidate search and adds exactly the three things
masterplan v2 §9 asks for:

| Addition | B3 | P |
|---|---|---|
| Sample sites used for scoring | commanded grid cells | positions a controller rollout says the fleet reaches |
| Plan in force | discarded every epoch | re-checked from the current state and kept within an explicit margin |
| Scoring horizon | the planner horizon | every remaining epoch, via an executable hold continuation |
| Decision times | sampling epochs only | epochs plus deviation/intervention events |

The §1.1 focus — how early a missed decay is visible and whether the remaining
budget can recover it — is served by the recorded `target_risk` and `decision`
blocks, not by a new claim.

## Candidate set

Candidates come from `plan_timed_dp` with `include_greedy_candidates=True`:

- **Bellman routes**, one per searched robot order (unchanged M2 search).
- **Greedy routes**, the same frozen surrogate without lookahead, so the value of
  the planning horizon can be separated from the value of plan management.
- **Nominal hold**, always available and always executable.
- **Retained remainder**, the still-future part of the plan in force, aligned to the
  epochs both plans share. It is re-rolled from the *current* actual state; it is
  never assumed still valid.

Rolling every candidate through the controller dominates the decision cost, so the
rollout set is bounded by `p_max_rollout_candidates` (default 6). Candidates are
pre-ranked by the cheap geometric score the search already produced; the hold and the
retained plan are never dropped. Skipped candidates are recorded with status
`not_evaluated`. A bounded search says nothing about the routes it never scored.

After the 17 September resilience correction, `candidates_evaluated` counts only
accepted plus rejected candidates; `candidates_rejected` excludes skipped routes,
and `candidates_not_evaluated` records the cap separately. New records are checked
against candidate statuses. Historical bundles are not rewritten; the demo derives
its displayed counts from those statuses.

## Controller rollout

`attainability/rollout.py` replays a candidate through the same controller the
mission executes, injected as a stepper so the package never imports the simulator.
Each interval requests arrival at its own deadline, exactly as execution does, so a
rollout is not a shortcut geometry with a different speed profile.

The rollout is **nominal**: no future disturbance, no future dropout, no ground
truth. It predicts execution under the controller, not under the weather. A feasible
rollout means the candidate is executable from here; it is not a robust guarantee
over the admitted deviation set.

A rejected command stops that candidate, retains its completed prefix and removes it
from the candidate set. It is never replaced by a hidden hold or a clipped command,
and it never becomes a shorter plan by accident. If every candidate is rejected the
mission fails explicitly with `no_executable_candidate`; that is a statement about
this bounded candidate set, not a proof that the mission target is unreachable.

If rejection occurs before any accepted interval, `min_separation_m` is `null`
(unobserved), not zero or NaN. Rejected candidates remain in the decision evidence
without preventing a different accepted candidate from being selected or saved.

Rollout control events carry `phase="candidate_rollout"` and no `plan_id`: they are
neither applied motion nor open-loop preplanning. Their wall time is inside
`planning_s` and is reported separately as `control_rollout_s`.

## Equal remaining budget

`attainability/budget.py` derives the budget from the global clock and the common
deadline only, never from a plan's own generation time, so replanning cannot reset
it. `MissionBudget.is_successor_of` is asserted at every decision: time and sensing
epochs may only run down.

Every candidate is extended to the deadline by holding its final positions for the
epochs it does not cover, so **all candidates are scored over the same remaining
sensing epochs**. A retained remainder that covers three of four epochs therefore
holds for one more epoch than a fresh route, and is scored — not excused — for it.

Holding applies zero velocity, so for the holonomic model the recorded static
geometry check (domain, separation) is the complete feasibility check for the
continuation. It is not a controller rollout and says nothing about a
turn-constrained vehicle.

Because the continuation belongs to a plan the fleet can actually execute, the
mission-end value is an **upper candidate** for the best attainable value. It is not
a floor, not a certificate and not an RMSE promise. With SOGP the forecast freezes
the current approximate posterior and does not model future dictionary pruning, so
it carries no bound property at all.

## Selection and retention

**Historical rule, 15 September 2026 (D025).**
Selection is by mission-end mean latent variance over those equal epochs, then
travel, then candidate id. The plan in force is kept unless another candidate
improves that value by more than `p_switch_margin` times the current mean variance
(default 1%), which stops the fleet oscillating between equivalent plans. The margin,
the retained value, the selected value and the expected gain are all recorded.

**Current rule, 20 September 2026 (D063).** The fixed mission target takes priority
over retention only when `best_mean <= target < retained_mean`, where both values
come from accepted candidates under the same remaining-budget forecast. Choose the
already-evaluated best candidate in this case, even if the improvement is within
the switching margin, and record the target-crossing reason. Equality meets the
target; no additional numerical tolerance relaxes it. With no configured target,
both candidates meeting it, or both missing it, the previous switching margin,
tie breaks and selection behavior remain unchanged.

This is a source-versioned fixed-target contract correction: D063 supersedes D025
only for that case. It changes no candidate search, execution constraints, sensing
budget, target or deadline. Historical P artifacts retain the old rule and must
not be relabeled as evidence for the corrected version. The small prototype
separately compares the decision with historical P and zero-margin P; passing a
decision test or observing a candidate forecast crossing establishes neither
empirical recovery nor superiority over ordinary adaptive replanning. In particular,
the route-plus-hold forecast is not an ordinary-policy continuation forecast, and
this correction does not establish warning lead time or benefit after planning
delay.

`switch_margin`, `deviation_trigger_m` and `intervention_trigger_mps` are development
settings chosen against physical scales — a fraction of the per-interval reachable
distance and of the speed bound — not fitted to observed results. They are frozen
before the final evaluation.

## Triggers

Decisions happen at every sampling epoch, labelled `initial`, `missed_measurement`
when that epoch lost a measurement, or `periodic_sampling_epoch`. Between epochs,
`execution_deviation` fires when a robot is further than `p_deviation_trigger_m` from
its geometric planned position, and `control_intervention` when the applied command
differs from the requested one by more than `p_intervention_trigger_mps`. The
magnitude matters: the QP nudges almost every command, so the boolean intervention
flag would re-decide on numerical noise rather than real execution loss.

An event-triggered plan inherits the same budget and the same deadline. It is the
only case where a plan's `sample_times_s` may be a strict prefix of the epochs a
fresh plan would cover, and only when the retained plan was kept.

## Ablations

The three mandatory ablations of §10 are configuration flags, so M6 can run them
without a separate code path:

```powershell
.\.venv\Scripts\python.exe -m attain_sampling simulate --methods dp,p --controller qp --robots 4
.\.venv\Scripts\python.exe -m attain_sampling simulate --methods p --controller qp --p-no-rollout
.\.venv\Scripts\python.exe -m attain_sampling simulate --methods p --controller qp --p-no-retain
.\.venv\Scripts\python.exe -m attain_sampling simulate --methods p --controller qp --p-periodic-only
```

`--target-mean-variance` sets the fixed mission target the risk record is measured
against and, from the 20 September correction, the target-priority exception above.
It is chosen before a run and shared by every method; it is not a threshold the
policy may relax.

## Evidence contract

- `plans[].budget`: remaining time, remaining/elapsed/total epochs, fleet travel bound.
- `plans[].decision`: action, trigger, reason, retained and selected values, expected
  gain, switch margin, candidates evaluated and rejected.
- `plans[].candidates[]`: generator, source, status, rollout summary, continuation
  check, horizon and mission-end variance, travel, and an explicit claim limit on
  every rejected or skipped entry.
- `plans[].targets_by_epoch` are the **commanded** cells; `predicted_sample_sites`
  are the rolled-out arrival positions the forecast uses. Execution steers to the
  former, so a plan record never silently commands a predicted landing point.
- `plans[].mission_end_forecast`: value, continuation epochs and scope.
- `plans[].target_risk`: configured target, best candidate value, margin, status and
  claim limits. `margin` remains target minus the best accepted candidate's forecast;
  `status` likewise assesses the candidate set. The separate
  `selected_mission_end_mean_variance` records the selected candidate. These fields
  keep their historical meanings; a candidate-set assessment is not a forecast of
  the ordinary policy's adaptive continuation.
- `plan_events`: one row per decision, mirroring the plan and adding the measured
  deviation and control correction that triggered it.

`_validate_managed_plans` re-checks all of this after every comparison: one decision
event per plan, budget matching the global clock and never increasing, exactly one
selected and accepted candidate, a retained action selecting the retained candidate,
a continuation covering exactly the epochs beyond the plan, and rollout evidence
present whenever rollout is enabled.

## Limits

P is holonomic-only, like the M1 QP and the M2 planner; USV management waits for a
heading-state graph and a turn-constrained rollout. The nominal rollout is not a
robust feasibility result, the hold continuation is not a robust backup invariant,
and none of this is a recursive-feasibility or attainability certificate. Rollout
cost is real and is reported: on the recorded four-robot pilot P spent about
twenty-two times B3's planning time, and in the recorded ablation the rollout never
changed a selection. Implementing P is not evidence that P beats B3. The frozen M6 held-out comparison
then found no measurable P benefit over B3 in any scenario, and the rollout changed
the outcome in 3 of 40 tasks ([M6 results](../reports/m6_results_2026-09-17.md)).
