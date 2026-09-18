# M6 — frozen held-out comparison protocol

Frozen on 17 September 2026, before any held-out run (D048). The machine-readable
version is [`configs/independent/m6_protocol.yaml`](../configs/independent/m6_protocol.yaml),
SHA-256 over its LF text `b409016561c4116cb69a169205754ec46d047695cead9ca03f7a3449dcb80ee2`.
`attain_sampling.eval.m6` pins that hash, and `scripts/run_m6.py` refuses to run if the
file differs. If anything in it changes, earlier results become development evidence
and a new task set is needed (masterplan §11.4).

**Result:** the single held-out batch ran on 17 September 2026 with no failed runs.
See [M6 results](../reports/m6_results_2026-09-17.md) (D049).

## Question

Masterplan §1 and §1.1: in the same mission budget, does the execution-aware policy **P**
(M4) give a measurable benefit in field RMSE, fixed-target attainment or compute over
the periodic replanner **B3**? And how early does each method's forecast call a missed
target? The answer is not assumed; equal and negative results are reported.

## Tasks

- **40 held-out tasks** per block, seeds 9001–9040. Development used 7, 19 and 31
  (independent profile), 43 and 59 (ECC profile) and 731 (M3 stream); none overlap.
- **Fixed for every block:** 4 holonomic robots, 90 s missions, the M1 QP controller,
  exact GP unless a block says otherwise, and the frozen M2–M4 development settings.
- Each task pairs every method on the same field, start, clock, noise and dropout
  schedule. `run_m6.py` checks that schedule across every job that shares a task,
  duration and disturbance setting.

## Blocks

| Block | Scenario | Methods | Varies |
|---|---|---|---|
| main | nominal, dropout, drift, combined, short budget (combined, 45 s) | B0 sweep, B1 greedy, B2 adaptive, B3 periodic DP, P | — |
| ablation | combined | P | no rollout · no plan retention · periodic only |
| sogp | combined | B3, P | bounded SOGP, capacity 32 |
| mismatch | nominal | all five | GP length scale 16 m instead of 8 m |

Full P and B3 in the ablation and SOGP comparisons come from the main block on the same
tasks. SOGP capacity 32 sits below the ~53 samples a combined mission receives, so pruning
is exercised; with 64 the dictionary never filled and SOGP matched exact GP exactly (pilot).
The narrow-passage scenario and field families beyond the seeded bump field are not
implemented, so they are not part of this protocol. The USV comparison belongs to M7.

## Fixed mission target

`0.0474` mean latent variance at mission end, shared by every method. The rule was
fixed before the value was computed: the median over development seeds 7, 19 and 31 of
B3's mission-end mean latent variance (combined, 4 robots, 90 s). The median was
0.047439, rounded to three significant figures. A task **reaches** the target when its
mission-end mean latent variance is at most 0.0474. A failed run does not reach it.

## Analysis

- **Primary:** mission-end field RMSE, paired P − B3, in each main scenario. Reported as
  the mean and median paired difference with a 95 % percentile bootstrap interval
  (10 000 task resamples, seed 20260917), plus counts of P-better / tie (|Δ| ≤ 1e-9) /
  B3-better. With five scenarios there are five primary comparisons; there is no
  multiplicity correction, and every other difference is descriptive.
- **Context pairs:** P − B2, B3 − B2, P − B0, B3 − B0.
- **Secondary:** mean and max latent variance, fixed-target attainment (paired table),
  first time the target is reached, path length, samples received, planning and total
  wall time, minimum separation, solver failures, plan decisions, and the one-step
  forecast error (realised minus forecast mean variance, for B2, B3 and P).
- **Failures:** a failed run is kept and counted. A pair containing one is excluded from
  the paired differences, and the exclusion count is printed next to every statistic.
- **Warnings (main block, exact GP):** a method warns at a sampling epoch when its
  mission-end forecast exceeds the target. For P this is its own `target_risk`: the best
  candidate over its bounded set, with its hold continuation; the selected plan's value is
  kept too. For B3 the evaluator applies the same hold continuation to B3's selected plan
  and recorded belief; B3 never uses this value. Each warning is scored against the
  method's own mission outcome: per-epoch recall and false-alarm rate, the first warning
  epoch, and the earliest epoch from which the warning stays correct.

## Integrity checks

- Before the first job, the job list, protocol copy and source snapshot are written.
- Inside each job: the M1 geometric/control audit on every completed run, the M4
  decision audit (budget, retention rule, independent exact forecast recomputation) on
  every P run, and an exact recomputation of P's selected mission-end forecast.
- `report_m6.py` checks every raw file against the manifest and recomputes every metric
  and warning from it. They must equal the worker's record before any analysis runs.

## What the results may and may not say

- They describe this simulator, this seeded field family, these disturbances and four
  holonomic robots. They are not a guarantee elsewhere.
- A warning says the evaluated plan's forecast misses the target. It does not say that
  no executable route reaches it.
- Timing is wall-clock on a shared machine with 16 parallel workers. Methods within one
  task run sequentially in one process, so their relative cost is comparable; absolute
  times are not.
- A P benefit claimed later must hold in these paired numbers; a tie or a loss is
  reported as one.
