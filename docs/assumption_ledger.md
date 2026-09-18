# Assumption ledger

Each experiment, plot and any later theorem must name the assumptions it uses. This
ledger retains source and numerical cautions under the
[active masterplan v2.0](../GP_Attainability_Masterplan_TR.md), not the old proof-first
completion requirements. `OPEN` means unestablished, not assumed true; `LOCKED_G0` applies
only to ECC source semantics. It does not block independent SOGP/DP/QP development.
The current independent model explicitly chooses Gaussian observation noise and mean
latent variance; those choices do not settle the paper's definitions.

| ID | Assumption | Status | Required evidence / test |
|---|---|---|---|
| A01 | ECC GP likelihood is Gaussian | `OPEN` | Anchor audit plus paper-configuration lock |
| A02 | Kernel and noise hyperparameters stay fixed during a covariance rollout | `DESIGN` | State hash before/after rollout; not itself a certificate |
| A03 | ECC objective uses latent variance | `LOCKED_G0` | Anchor equation/page citation; independent metric is already chosen |
| A04 | Evaluation set and weights are fixed and fully enumerated | `DESIGN` | Evaluation-set hash and normalized-weight test |
| A05 | Future exact covariance update is label-free | `SUPPORTED` | Different-label and joint/sequential oracle tests |
| A06 | Future sparse covariance update is label-free | `FALSE_WITH_PRUNING` | Counterexample and prune diagnostics |
| A07 | Executable rollout uses the same dynamics, constraints, clocks, and safety layer as execution | `DESIGN` | Rollout-vs-execution contract test |
| A08 | QP is feasible at every control tick | `OPEN` | Infeasibility policy and stress tests |
| A09 | Continuous-time CBF inequality protects sampled-data execution | `OPEN` | Discrete/robust margin analysis |
| A10 | ECC global information task can be partitioned without changing its derivative | `LOCKED_G0` | Paper equation plus centralized-vs-local oracle comparison |
| A11 | Weighted IVAR reduction is submodular | `REJECTED_GENERAL` | Do not assert; retain counterexample fixture |
| A12 | Planner visits every scheduled sample in its claimed window | `DESIGN` | Timestamped rollout coverage validation |
| A13 | Slack, reference drift, and SOGP discrepancy close a finite-horizon bound | `DEFERRED_UNPROVEN` | Later research; not a v2 completion requirement |
| A14 | Posterior variance is a calibrated proxy for true field error | `EMPIRICAL_ONLY` | Calibration/coverage experiment; never assume identity |
| A15 | Simultaneous sparse observations are order invariant | `REJECTED_GENERAL` | Deterministic order plus sensitivity metric |
| A16 | The hold continuation used for every mission-end forecast is executable | `SUPPORTED_HOLONOMIC_ONLY` | Zero velocity keeps domain and separation unchanged; recorded static check per candidate. Says nothing about a turn-constrained vehicle |
| A17 | A nominal controller rollout predicts the sample sites execution will reach | `DESIGN_NOMINAL_ONLY` | Rollout uses the executing controller with no future disturbance, dropout or ground truth; measured landing error and interventions are recorded |
| A18 | A feasible plan's mission-end value upper-bounds the attainable optimum | `SUPPORTED_EXACT_GP_ONLY` | Holds for fixed-kernel exact GP over the same feasible-route problem; an approximate SOGP forecast carries no bound property |
| A19 | Scoring every candidate over the same remaining epochs makes their values comparable | `DESIGN` | Per-decision equal-budget check over accepted candidates; 2,756 checks recorded in the M4 validation batch |
| A20 | A candidate set that misses the mission target shows the target is unattainable | `REJECTED_GENERAL` | Bounded search only; every target-risk record carries the claim limit and skipped candidates are listed |

Status changes require an entry in `decision_log.md` and, for paper facts, a page/equation
entry in `equation_map.md`.

M4 additions A16-A20 are recorded design and evidence statements, not proofs; none of
them establishes A13, and none converts a bounded candidate search into an impossibility
or recovery result.

Scope-only revisions for v2 do not establish previously open mathematical assumptions.
In particular, the new waypoint-tracking QP must not fabricate a continuous derivative
of fixed-data GP variance when no measurement is received.
