# GP Mapping Lab — recorded development results

8 September 2026. Independent exact-GP multi-robot mapping simulation.

The working system completes the loop from a synthetic field and noisy measurements
through GP estimation, information planning, constrained robot motion, and recorded
evaluation. These results cover **54 policy runs in 18 paired comparisons**. They are
development evidence, not an ECC2025 reproduction, a held-out benchmark, or a claim of
general method superiority.

## Recorded experiment

Every comparison uses three robots in a 60 × 40 m rectangular domain for 90 simulated
seconds. Motion is updated every 0.5 s; sampling occurs at 0, 5, …, 90 s, yielding 57
attempted fleet measurements. The common evaluation grid contains 24 × 16 points.
The exact GP has fixed length scale 8 m, signal variance 1, and observation noise
standard deviation 0.15 field units. Maximum translational speed is 2 m/s and required
inter-robot separation is 2 m. Seeds are **7, 19, and 31**.

Within each scenario and seed, all three policies share the field, initial positions,
measurement clock, noise innovations, dropout outcomes, and motion-disturbance keys.
Successful measurements update the GP at their **actual** positions. The policies are:

- **Sweep:** a predetermined spatial lawnmower route.
- **Nominal greedy:** a nominal information-gain sensing route computed before execution,
  assuming scheduled measurements succeed; waypoint tracking still uses robot position.
- **Execution-aware:** joint information targets recomputed at sampling epochs using
  actual robot positions and the posterior from received measurements.

Nominal scenarios have no dropout or motion disturbance. Dropout scenarios use a 0.30
loss probability; observed received counts are 43, 31, and 39 for seeds 7, 19, and 31,
respectively, for every policy. Drift scenarios use disturbance strength 0.35. Combined
scenarios enable both. Holonomic drift is an additive velocity disturbance with standard
deviation 0.35 m/s. USV drift is a yaw-rate disturbance with standard deviation 0.35 rad/s,
before applying the turn-rate limit. Equal numerical drift settings across these models
therefore do not describe equal physical disturbances.

## Holonomic results — 36 policy runs

RMSE, variance, path, and received measurements are arithmetic means across the three
seeds. Runtime is the median with the observed minimum–maximum in brackets. Path is
the sum of all three **executed** robot path lengths. Every row has 57 attempted
measurements per run; fractional received counts are averages, not individual outcomes.

| Scenario | Policy | RMSE | Mean latent variance | Fleet path (m) | Received | Runtime (s), median [min, max] |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Nominal | Sweep | 0.1386 | 0.0509 | 512.67 | 57.00 | 0.0708 [0.0677, 0.0739] |
| Nominal | Nominal greedy | 0.1263 | 0.0337 | 527.32 | 57.00 | 0.0842 [0.0800, 0.0968] |
| Nominal | Execution-aware | 0.1263 | 0.0337 | 527.32 | 57.00 | 0.0957 [0.0783, 0.1154] |
| Dropout | Sweep | 0.1707 | 0.1067 | 512.67 | 37.67 | 0.0603 [0.0541, 0.0621] |
| Dropout | Nominal greedy | 0.1707 | 0.1133 | 527.32 | 37.67 | 0.0742 [0.0737, 0.0768] |
| Dropout | Execution-aware | 0.1497 | 0.0852 | 429.64 | 37.67 | 0.0839 [0.0743, 0.0942] |
| Drift | Sweep | 0.1470 | 0.0537 | 497.79 | 57.00 | 0.0809 [0.0795, 0.0863] |
| Drift | Nominal greedy | 0.1226 | 0.0437 | 475.31 | 57.00 | 0.1029 [0.0961, 0.1060] |
| Drift | Execution-aware | 0.1305 | 0.0389 | 481.26 | 57.00 | 0.1131 [0.1012, 0.1157] |
| Combined | Sweep | 0.1910 | 0.1210 | 497.79 | 37.67 | 0.0743 [0.0688, 0.0796] |
| Combined | Nominal greedy | 0.1784 | 0.1194 | 475.31 | 37.67 | 0.0949 [0.0886, 0.1020] |
| Combined | Execution-aware | 0.1556 | 0.0800 | 429.00 | 37.67 | 0.0968 [0.0881, 0.1032] |

## Turn-limited USV results — 18 policy runs

The second motion model is a sampled kinematic unicycle with variable forward speed
and maximum yaw rate 0.45 rad/s. It permits yaw at zero speed and includes no
hydrodynamics. Candidate sensing locations are scored using nominal turn-limited
endpoint rollouts. These runs validate this implemented model, not a physical vessel.

| Scenario | Policy | RMSE | Mean latent variance | Fleet path (m) | Received | Runtime (s), median [min, max] |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Nominal | Sweep | 0.1486 | 0.0427 | 490.66 | 57.00 | 0.0709 [0.0648, 0.0747] |
| Nominal | Nominal greedy | 0.1483 | 0.0484 | 467.24 | 57.00 | 0.3875 [0.3466, 0.4013] |
| Nominal | Execution-aware | 0.1483 | 0.0484 | 467.24 | 57.00 | 0.3768 [0.3665, 0.4267] |
| Combined | Sweep | 0.1711 | 0.1002 | 484.42 | 37.67 | 0.0848 [0.0792, 0.0958] |
| Combined | Nominal greedy | 0.1898 | 0.1371 | 455.39 | 37.67 | 0.3721 [0.3651, 0.4254] |
| Combined | Execution-aware | 0.1537 | 0.0996 | 410.01 | 37.67 | 0.3580 [0.3451, 0.3954] |

## What these runs show

With nominal execution, greedy and execution-aware policies have identical final RMSE,
variance, and path metrics for each seed in both models. Under dropout and combined
holonomic disturbance, execution-aware replanning has lower RMSE than nominal greedy
in all three recorded seeds. It also has lower RMSE in all three combined USV seeds.

The counterexample to universal improvement is explicit: with holonomic drift alone,
execution-aware RMSE is **higher** than nominal greedy in all three seeds, despite lower
mean posterior variance. Mean RMSE is 0.1305 versus 0.1226. Posterior variance describes
the fixed GP model; it does not certify error against the actual synthetic field.

These comparisons hold mission time, motion bounds, and sensing schedules fixed;
they do not enforce identical executed distance. Shorter paths in some execution-aware
runs are recorded outcomes. Three development seeds do not establish statistical
superiority, generalization, large-scale runtime, or performance for other team sizes.

Planned-variance plots also require a distinction. Sweep and nominal greedy preserve
a forecast based on the complete nominal sample history and assumed receipt. The
execution-aware policy resets its next-epoch forecast from each actual posterior.
Consequently, a smaller execution-aware forecast gap is not a like-for-like comparison
of whole-mission forecast accuracy. These curves are diagnostics, not bounds.

## Runtime and constraint checks

The first recorded three-policy comparison served as the pilot: **0.2804 s** for the
holonomic batch and **0.8396 s** for the USV batch. Subsequent comparisons ran after
these pilots. Sum of recorded policy compute time is **3.0942 s** for the 36 holonomic
runs and **5.0366 s** for the 18 USV runs, or **8.1308 s** in total. Individual
three-policy comparison times range from 0.2086 to 0.9170 s.

Timings include each policy's planning, GP updates/predictions, and simulation, including
offline nominal preplanning. Artifact serialization, figure/video rendering, and browser
work are excluded. `planning_s` includes covariance work performed inside planning;
`gp_s` counts the actual-belief updates and map predictions outside planning. These are
local wall-clock measurements, not worst-case online latency guarantees. Recorded
environment: Intel Core i9-14900HX (queried from the local processor registry),
Python 3.11.16, Windows build 10.0.26200, NumPy 2.4.6, SciPy 1.17.1.

All stored trajectories were checked again, independently recomputing closest pair
distance over each simultaneous straight timestep segment, rather than checking
endpoints alone. The audit covers **9,720 fleet timestep segments**:

| Check | Recorded/recomputed extreme | Configured limit |
| --- | ---: | ---: |
| Minimum pair separation, all models | 2.0000001727 m | At least 2 m |
| Maximum translational speed, all models | 2.0000000000000093 m/s | At most 2 m/s |
| Maximum absolute yaw rate, USV only | 0.45000000000000284 rad/s | At most 0.45 rad/s |
| Domain containment | Every recorded position inside the rectangle | 60 × 40 m |

The speed/yaw excesses above the decimal limits are floating-point rounding; all checks
pass with absolute tolerance 1e-9. There are **434 fleet timestep constraint interventions**
across the runs. These count common displacement backtracking/stopping for domain or
separation constraints; they are not a count of collisions. Convex domain containment
and segment distances apply to the declared sampled straight-segment motion. They
do not constitute a continuous physical USV, obstacle-avoidance, or formal CBF certificate.

## Artifact audit and sources

This report was computed from these two saved benchmark indexes and their referenced
completed bundles:

- [Holonomic benchmark, 36 policy runs](../outputs/validation/holonomic/benchmark-20260908T132115471574Z.json)
- [USV benchmark, 18 policy runs](../outputs/validation/usv/benchmark-20260908T132145261679Z.json)

All **306 manifest-listed artifact SHA-256 hashes** matched. Each benchmark record
matched its bundled policy summary exactly (**918 summary fields**). All 18 bundles
passed the field/start/configuration and event-by-event noise/dropout pairing checks.
Final RMSE, mean/max latent variance, fleet path length, attempted measurements, and
received measurements were recomputed from saved maps and raw records. The largest
absolute difference from stored metrics was 2.28e-13.

Each bundle includes configuration, seed manifest, environment metadata, source hashes
and a source snapshot, raw robot/sample Parquet records, time-series metrics, and complete
JSON replay data. Git revision was unavailable and the checkout was recorded as dirty;
the archived source and content hashes, rather than an invented commit identifier,
provide the recorded source provenance.

## Additional team-size and packaging smoke checks

Separately from the 54-run development benchmark, twelve policy runs covered the
combined scenario, seed 7, 90 s, with 2 and 4 robots in both motion models. All matched
event schedules, speed/separation checks and applicable USV yaw limits passed at
absolute tolerance 1e-8. Recorded three-policy compute times were 0.30/0.58 s for
2/4 holonomic robots and 1.19/2.44 s for 2/4 USVs. These are bounded smoke checks,
not a scalability benchmark or additional statistical evidence.

The wheel was extracted into an isolated package directory ahead of the editable
source; imported module paths, all three static assets, a tiny packaged CLI mission,
and source-snapshot hashes were verified. See
[package/scaling validation evidence](../outputs/package-validation-20260908/validation_evidence.json).
The final wheel and sdist, including the subsequent video-layout correction, are in
`outputs/package-final-20260908/`. No extra learning framework or dependency was added.
