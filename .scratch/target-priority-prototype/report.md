# Target-priority prototype: no observed recovery benefit

20 September 2026. Throwaway branch `codex/target-priority-prototype`, base `bf6bdf3`.

The fixed-target selection rule is coherent in the illustrative logic cases: if an
already-scored, feasible candidate meets the target and the retained route misses,
the target takes priority over hysteresis. These simulator pilots do **not** show
that this rule improves outcomes. There were no target-crossing opportunities in
any P mission, so target-priority P made exactly the same route and receipt choices
as historical P. B2 succeeded at nominal and moderate drift and missed at severe
drift. Every B3/P arm missed at all three drifts, on both grids.

The initial protocol is [preserved](protocol.md), as is the separately predeclared,
post-pilot [grid diagnostic](grid-diagnostic-protocol.md). No seed, target, candidate
cap or further grid was searched. Neither batch is held-out evaluation. The six B2
entries across the two grids repeat the same three physical tasks; they are not six
independent missions for statistical inference.

## Experiment and target

ExactGP, holonomic motion, two robots, 20 x 14 m, 20 s, control dt 0.5 s, samples
every 2 s, evaluation grid 12 x 8, planning horizon two samples, length scale 3 m,
maximum speed 2 m/s, minimum separation 2 m, filter controller, seed 7, sensor noise
standard deviation 0.15 and no dropout. Motion errors use the same existing indexed
stream for corresponding robot/tick. All methods keep the same physical resources.
The numeric target **0.17797860776402111** was frozen as 1.05 times nominal B2's
mean variance, before the original comparison, and reused without recalibration.

The original planner grid is 5 x 4. After inspecting that batch, one diagnostic
changed only the planner grid to 7 x 5. Planning costs below are measured wall
seconds; decision time is not charged against simulated mission time. The P
forecast is a nominal route plus hold, not closed-loop adaptive continuation.
There are no claimed warning lead times, false-alarm rates, or recovery guarantees.

Every one of the 30 comparison missions completed, with no simulator failures and
22 received samples. A completed mission is a target success only if its final mean
latent variance is at or below the fixed target. Variance and actual RMSE remain
separate: for example, on the 7 x 5 nominal case P has higher variance than B2 but
lower RMSE; this is not contradictory.


## Original 5 x 4 grid

[Full summary](results/summary.json) and [provenance](results/metadata.json).

| Arm | Drift | Mean variance | Max variance | RMSE | Target met | Plan / total seconds | P candidates scored |
|---|---:|---:|---:|---:|:---:|---:|---:|
| [B2](results/B2-drift-0.json.gz) | 0 | 0.169503 | 0.723145 | 0.195768 | Yes | 0.020 / 0.031 | - |
| [B3](results/B3-drift-0.json.gz) | 0 | 0.761352 | 1.000000 | 0.319179 | No | 0.067 / 0.079 | - |
| [Historical P](results/historical_P-drift-0.json.gz) | 0 | 0.761352 | 1.000000 | 0.319179 | No | 0.274 / 0.287 | 55 |
| [Target-priority P](results/target_priority_P-drift-0.json.gz) | 0 | 0.761352 | 1.000000 | 0.319179 | No | 0.274 / 0.288 | 55 |
| [P, zero margin](results/zero_margin_P-drift-0.json.gz) | 0 | 0.761352 | 1.000000 | 0.319179 | No | 0.305 / 0.319 | 55 |
| [B2](results/B2-drift-0.35.json.gz) | 0.35 | 0.149943 | 0.824529 | 0.168246 | Yes | 0.024 / 0.040 | - |
| [B3](results/B3-drift-0.35.json.gz) | 0.35 | 0.715514 | 1.000000 | 0.298637 | No | 0.086 / 0.103 | - |
| [Historical P](results/historical_P-drift-0.35.json.gz) | 0.35 | 0.720025 | 1.000000 | 0.293051 | No | 0.298 / 0.315 | 55 |
| [Target-priority P](results/target_priority_P-drift-0.35.json.gz) | 0.35 | 0.720025 | 1.000000 | 0.293051 | No | 0.289 / 0.305 | 55 |
| [P, zero margin](results/zero_margin_P-drift-0.35.json.gz) | 0.35 | 0.709548 | 1.000000 | 0.302990 | No | 0.294 / 0.310 | 57 |
| [B2](results/B2-drift-1.json.gz) | 1 | 0.215634 | 0.785068 | 0.204475 | No | 0.022 / 0.036 | - |
| [B3](results/B3-drift-1.json.gz) | 1 | 0.650625 | 1.000000 | 0.296410 | No | 0.141 / 0.176 | - |
| [Historical P](results/historical_P-drift-1.json.gz) | 1 | 0.663015 | 1.000000 | 0.283435 | No | 1.137 / 1.178 | 109 |
| [Target-priority P](results/target_priority_P-drift-1.json.gz) | 1 | 0.663015 | 1.000000 | 0.283435 | No | 1.117 / 1.158 | 109 |
| [P, zero margin](results/zero_margin_P-drift-1.json.gz) | 1 | 0.645803 | 1.000000 | 0.346513 | No | 1.043 / 1.090 | 94 |

Total recorded mission runtime: 5.715 s. One timing observation per mission; concurrent development load was not controlled. Timing differences between scientifically identical arms are not evidence of algorithmic cost differences.


## Single 7 x 5 grid diagnostic

[Full summary](results-grid7x5/summary.json) and [provenance](results-grid7x5/metadata.json).

| Arm | Drift | Mean variance | Max variance | RMSE | Target met | Plan / total seconds | P candidates scored |
|---|---:|---:|---:|---:|:---:|---:|---:|
| [B2](results-grid7x5/B2-drift-0.json.gz) | 0 | 0.169503 | 0.723145 | 0.195768 | Yes | 0.029 / 0.047 | - |
| [B3](results-grid7x5/B3-drift-0.json.gz) | 0 | 0.226594 | 0.890357 | 0.152553 | No | 0.110 / 0.125 | - |
| [Historical P](results-grid7x5/historical_P-drift-0.json.gz) | 0 | 0.226594 | 0.890357 | 0.152553 | No | 0.421 / 0.437 | 59 |
| [Target-priority P](results-grid7x5/target_priority_P-drift-0.json.gz) | 0 | 0.226594 | 0.890357 | 0.152553 | No | 0.566 / 0.589 | 59 |
| [P, zero margin](results-grid7x5/zero_margin_P-drift-0.json.gz) | 0 | 0.226594 | 0.890357 | 0.152553 | No | 0.548 / 0.570 | 59 |
| [B2](results-grid7x5/B2-drift-0.35.json.gz) | 0.35 | 0.149943 | 0.824529 | 0.168246 | Yes | 0.035 / 0.058 | - |
| [B3](results-grid7x5/B3-drift-0.35.json.gz) | 0.35 | 0.267907 | 0.916802 | 0.255775 | No | 0.123 / 0.148 | - |
| [Historical P](results-grid7x5/historical_P-drift-0.35.json.gz) | 0.35 | 0.267566 | 0.916798 | 0.255238 | No | 1.240 / 1.282 | 107 |
| [Target-priority P](results-grid7x5/target_priority_P-drift-0.35.json.gz) | 0.35 | 0.267566 | 0.916798 | 0.255238 | No | 1.396 / 1.449 | 107 |
| [P, zero margin](results-grid7x5/zero_margin_P-drift-0.35.json.gz) | 0.35 | 0.267566 | 0.916798 | 0.255238 | No | 1.362 / 1.413 | 107 |
| [B2](results-grid7x5/B2-drift-1.json.gz) | 1 | 0.215634 | 0.785068 | 0.204475 | No | 0.053 / 0.098 | - |
| [B3](results-grid7x5/B3-drift-1.json.gz) | 1 | 0.259234 | 0.894293 | 0.258329 | No | 0.190 / 0.250 | - |
| [Historical P](results-grid7x5/historical_P-drift-1.json.gz) | 1 | 0.260014 | 0.894164 | 0.255263 | No | 1.187 / 1.238 | 89 |
| [Target-priority P](results-grid7x5/target_priority_P-drift-1.json.gz) | 1 | 0.260014 | 0.894164 | 0.255263 | No | 1.125 / 1.176 | 89 |
| [P, zero margin](results-grid7x5/zero_margin_P-drift-1.json.gz) | 1 | 0.260014 | 0.894164 | 0.255263 | No | 1.064 / 1.111 | 89 |

Total recorded mission runtime: 9.990 s. One timing observation per mission; concurrent development load was not controlled. Timing differences between scientifically identical arms are not evidence of algorithmic cost differences.


## What the grid diagnosis establishes

At 5 x 4, grid gaps of 5 m horizontally and 4.666667 m vertically exceed the 4 m
per-sampling-interval speed budget. The first off-grid start can reach a grid cell,
but moving from that cell to another at the next sample is infeasible. Recorded
nominal B3/P candidates repeat the first reached cells. Their complete routes total
6.732363 m and their 22 measurements revisit only four distinct sites. B2 totals
78.411353 m and samples 22 distinct sites.

With 7 x 5, the gaps are 3.333333 and 3.5 m. Nominal P then travels 63.727610 m and
samples 22 distinct sites; final mean variance falls from 0.761352 to 0.226594.
This supports a grid-resolution limitation in the original bounded candidate search.
It still does not reach the fixed target or beat B2 on target success. See the
[derived reachability evidence](reachability-evidence.json); full candidate routes
are in the linked compressed raw artifacts.

## Route, receipt and decision evidence

For target-priority P versus historical P, first changed route and first changed
receipt are both absent in all six comparisons. All accepted-candidate target
crossing counts, hysteresis-override-needed counts and override counts are zero.
Every P decision is saved in a companion `*-decisions.json`, including time, retained
and best forecasts, chosen route, switching margin, target-risk and explanation.
The compressed mission records retain every candidate, control event, sample and
full outcome. `summary.json` records each first changed route/receipt versus
historical P. Route time is the first recorded target-command difference in the
motion trace, not a fabricated decision time.

On the original grid, zero-margin P first changes its command/receipt at 6.5/8 s
for drift 0.35 and 4.5/6 s for drift 1. It lowers mean variance slightly but gains
no successes, and its severe-drift RMSE worsens from 0.283435 to 0.346513. On the
7 x 5 grid its routes and receipts equal historical P for all three drifts. No
negative or null outcome was removed.

Candidate counts in the tables are P's accepted/rejected rollout evaluations.
B3 has 30 candidate records per mission in these runs, without P's controller
rescoring; its count is not equivalent. B2's internal greedy targets are not saved
as plan records, so its zero recorded `decision_count`/`candidate_records` does
**not** mean no planning or no candidate search. Its measured planning time is
reported and its normal adaptation remains active.

## Decision and next gate

A narrow fixed-target selection correction can be justified by its decision
contract and targeted behavioral evidence; this pilot supplies no claim of
additional mission success. No practically recoverable example was demonstrated, and
the observable-mechanism gate remains open. Keep ordinary adaptive B2 as the comparator. Do not
launch an expensive study or benchmark-transfer effort on the strength of this
negative pilot. The next research design must establish a candidate/action mechanism
that can affect a real receipt before the deadline and adds benefit over B2, then
separately assess warning accuracy and decision latency. Broader tuning is outside
this completed prototype.

The [HTML logic demo](../../src/attain_sampling/attainability/target_priority_prototype.html)
contains free play and guided nominal, target-crossing, infeasible-alternative and
no-observed-recovery cases. Its values are explicitly illustrative. A browser
preview of the local file was blocked by the browser URL policy; the file was
inspected as source, but rendered appearance and clicks were not verified. No
alternate browser or policy workaround was attempted. Open the HTML directly to
explore it; it has no external dependencies or persistence.

## Reproduce and inspect provenance

From this worktree, use its parent project's existing Python environment:

```powershell
& '..\..\.venv\Scripts\python.exe' src/attain_sampling/attainability/target_priority_prototype.py --output .scratch/target-priority-prototype/repeat-original
& '..\..\.venv\Scripts\python.exe' src/attain_sampling/attainability/target_priority_prototype.py --grid-diagnostic --output .scratch/target-priority-prototype/repeat-grid7x5
```

Outputs must not already exist. The diagnostic intentionally reads the original
frozen `results/calibration.json`. The script inserts this worktree's `src` before
installed packages and records actual imported paths, source SHA-256, environment,
full config, and protocol hash. The historical policy was copied before edits and
is loaded in a separate module; its settings are reconstructed without changing
values. Only its old selection is used for historical/zero-margin comparisons.

The final script includes the diagnostic switch added after the initial batch.
`pilot_initial.py` preserves the exact initial-run script bytes and matches that
batch's recorded script hash. It is an archival source copy: rerun using the module
path shown above, which has the correct repository-root calculation. The final
module script matches the diagnostic metadata hash. Source and all raw artifacts
are preserved on the throwaway branch; no production code was changed by this
prototype task. No prototype tests or framework were added.
