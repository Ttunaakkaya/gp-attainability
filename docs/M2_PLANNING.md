# M2 — timed Bellman-DP planning

14 September 2026. Independent masterplan v2 M2 implementation on the existing
exact GP and M1 holonomic controller. This is the first periodic DP baseline B3,
not the proposed recovery policy P or an ECC2025 reproduction. See the
[M2 development report](../reports/m2_results_2026-09-14.md) for measured evidence.

## Algorithm and scope

Every physical sensing epoch first assimilates received **actual** measurements.
The planner sees that posterior, actual positions, current time and the unchanged
mission deadline. It sees neither the true field nor future noise/dropouts.

The default horizon is four future sampling epochs, shortened by the remaining
physical sample budget. A 17 s mission with 5 s sensing samples at 0, 5, 10 and
15 s, never 17 s. After the last sample the nominal target is the current position;
no new information is invented. This hold is not a robust backup certificate.

A 9 × 7 rectangular grid has eight-neighbor and stay actions. The actual start is
an extra node with reachable grid connectors, not a discontinuous snap to grid.
Transitions must fit the next sampling deadline at the Euclidean speed limit.
Nominal simultaneous straight segments are screened against earlier assigned
robots, including intermediate times. Geometric roundoff tolerance is 1e-7;
actual states are not silently projected to new positions.

For each robot assignment, state is `(cell, remaining epochs)`. Backward Bellman:

`J[t,i] = max_j { g[j] - c[i,j] + J[t+1,j] }`, with `J[H,i] = 0`.

`g[j] = mean_q(C(q,j)^2)/(C(j,j)+noise_variance+jitter)/signal_variance` is
normalized single-sample mean latent-variance reduction. The unnormalized
reduction has field-value-squared units. The cost is
`travel_weight * distance_m / (robot_count * max_speed * horizon_s)`.
Both surrogate terms are dimensionless; travel weight defaults to 0.01.
Earlier assigned teammates' complete routes condition the current robot's reward,
but its rewards stay frozen along its own Bellman path. This is **not** a full GP
belief-MDP; repeated visits can be overvalued by that surrogate.

Up to four distinct rotated/reversed robot orders and an explicit nominal-hold
candidate are considered. The order set rotates with plan version (two robots
have two distinct orders). Each complete candidate is rescored using the exact
joint covariance of its chronological multi-robot measurement sequence. Lowest
terminal mean latent variance wins; normalized travel only breaks ties within
`1e-10 * signal_variance`. Summed Bellman reward is never total information gain.
Rejected ordered searches are logged, not called proof of impossibility.

Search bounds are explicit: 1–16 horizon epochs, at least two nodes per axis,
at most 400 grid nodes. These are independent development settings. Extra greedy
candidates and retained-plan recovery can be evaluated later; this bounded search
is not a global multi-robot route optimum.

## Execution and forecast

Only the first interval is executed. Requested velocity is remaining displacement
divided by time to its sampling deadline, capped at maximum speed. M1 QP or the
reference filter processes that command; tracking disturbance still enters before
the constraint layer. Nominal unconstrained motion follows a synchronized straight
segment. QP intervention/drift can miss the planned site. **B3 uses no controller
candidate rollout**; evaluating that effect is M4 work. USV + DP is rejected until
a heading-state graph or suitable motion primitives are implemented.

At the next sensing epoch, received actual samples update the GP and a new plan
is generated with the same mission end. Forecasts include current variance and
every joint sample prefix of one selected plan, assuming future measurements at
geometric sites are received. The last forecast is a **planning-horizon value**,
not necessarily a mission-terminal value. Fantasy labels never enter the real GP.
These are conditional predictions, not attainability floors, recovery certificates,
physical safety guarantees or RMSE guarantees.

## Evidence and timing

- `run.plans` / `plans.json`: deterministic ID/version, generation time, mission
  end, actual starts, received sample keys/count, future sites/times, candidate
  scores/orders/rejections, selection, prefix forecasts and nominal checks.
- `planned_samples.parquet`: flattened plan ID, time, robot and geometric site.
- `motion`, `samples`, `controls`: executing `plan_id`; initial motion/samples have
  no preceding plan. A sample at a replan boundary belongs to the just-executed
  interval, not the new outgoing plan.
- `frames.plan_id`: outgoing/current plan. `forecast_plan_id`: incoming plan whose
  forecast applies now. The two IDs can differ.
- `planning_failures`: explicit planner/numerical error and actual state/time.
  Failure retains the real motion/sensor prefix, never a padded complete mission.

`planning_s` includes DP and bookkeeping. `dp_planning_s`, median/p95 summarize
completed planner calls; `dp_failed_planning_s` records failed ones separately.
Nested covariance/candidate timings overlap these totals. Planner wall time is
not charged to the simulation clock, so timings are not hard real-time evidence.

## Run and inspect

Default three methods remain unchanged; opt in to B3:

```powershell
.\.venv\Scripts\python.exe -m attain_sampling simulate --methods sweep,greedy,adaptive,dp --controller qp --scenario combined --robots 4
.\.venv\Scripts\python.exe -m attain_sampling simulate --methods dp --controller qp --dp-horizon-steps 4 --dp-grid-nx 9 --dp-grid-ny 7 --no-figures
.\.venv\Scripts\python.exe scripts/validate_m2.py --pilot-only
.\.venv\Scripts\python.exe scripts/validate_m2.py
```

In the demo choose Include periodic DP · M2, a holonomic model and the desired
controller. Select B3 and replay: the panel/future-site overlay uses only the plan
available at that cursor. Exports/videos support four methods; old bundles work.
M3 now permits joint conditioning of a frozen **approximate** SOGP posterior;
the exact algorithm/results above describe the historical M2 reference backend.
See [M3 scope](M3_SOGP.md). M4 rollout/plan retention/triggering, M6 final comparisons
and USV remain separate work. Implementing B3 is not evidence that B3 or P is superior.
