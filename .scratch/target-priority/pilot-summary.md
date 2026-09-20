# Development pilot: no observed recovery benefit

20 September 2026. This is a small diagnostic, not a held-out study.

The standalone prototype, scripts, raw evidence and detailed report are preserved
on `codex/target-priority-prototype`, commit
[`f54435a4629135df3277aa5a6a942dbf99ae2f84`](https://github.com/Ttunaakkaya/gp-attainability/commit/f54435a4629135df3277aa5a6a942dbf99ae2f84).
They are deliberately outside main. Start with the
[full report and reproduction commands](https://github.com/Ttunaakkaya/gp-attainability/blob/f54435a4629135df3277aa5a6a942dbf99ae2f84/.scratch/target-priority-prototype/report.md).

## Question and design

Does giving a fixed target priority over plan-retention hysteresis add successes
without adding candidates or changing physical resources? Compare ordinary adaptive
B2, periodic B3, historical P, target-priority P and zero-margin P. Use ExactGP,
two holonomic robots, seed 7, a 20-second deadline, samples every two seconds,
no measurement loss, and drift strengths 0, 0.35 and 1.0. Complete decision costs
are recorded but are not charged against simulated time in this diagnostic.

Freeze one target before the comparisons: **0.17797860776402111**, equal to 1.05
times nominal B2's final mean variance in calibration. This is a development target,
not an independent assessment of B2's nominal success. Preserve the original 5x4
planner-grid protocol and its 15 missions. After diagnosing grid reachability,
predeclare one follow-up using 7x5 and the same target/settings: another 15 missions.
No further grid, target or seed search was performed.

## Outcome

All 30 comparison missions completed, each with 22 received samples. B2 meets the
target at drift 0 and 0.35 and misses at 1.0. Every B3/P variant misses in both grids.
The repeated B2 entries refer to the same three tasks, not independent extra evidence.

| Planner grid | Drift | B2 final mean variance | Historical and target-priority P |
| --- | ---: | ---: | ---: |
| 5x4 | 0 | 0.169503 | 0.761352 |
| 5x4 | 0.35 | 0.149943 | 0.720025 |
| 5x4 | 1.0 | 0.215634 | 0.663015 |
| 7x5 | 0 | 0.169503 | 0.226594 |
| 7x5 | 0.35 | 0.149943 | 0.267566 |
| 7x5 | 1.0 | 0.215634 | 0.260014 |

There were **zero target-crossing opportunities**. Target-priority P and historical
P made exactly the same route and receipt choices in all six corresponding tasks.
Zero-margin P changed some coarse-grid routes but gained no successes. Its severe-
drift map RMSE worsened, so lower GP variance was not automatically better map accuracy.
The full report retains final maximum variance, RMSE, failures, runtime, candidate
counts, decision records and first changed command/receipt times for every arm.

The coarse grid's 5 m horizontal and 4.67 m vertical gaps exceed the 4 m travel
budget between samples. After the first arrival, nominal grid routes repeat their
cells. The denser grid restores movement and improves variance, but still does not
produce a recovery benefit. This is a measured candidate-resolution issue, not a
reason to discard the unsuccessful original pilot.

## Decision

The real-GP target-crossing regression justifies the narrow decision-contract fix.
This mission pilot does **not** validate recovery beyond ordinary adaptation.
The observable-mechanism gate remains open. Next investigate candidate generation
and the named ordinary continuation, with matched information/search controls,
before building state-copying or delayed-decision architecture. Neither these
route-plus-hold forecasts nor this pilot establish warning accuracy, meaningful
lead time, numerical failure probabilities or novelty.

An independent read-only audit verified all 30 raw records, fixed resources/target,
source identities, the six unchanged route/receipt pairs, crossing counts and
reported first-change times. The archived artifact manifest contains 78 byte hashes.
The standalone HTML is an illustrative logic model, explicitly separated from
experimental outcomes; its local browser preview was unavailable.
