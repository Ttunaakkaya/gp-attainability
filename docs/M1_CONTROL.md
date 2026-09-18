# M1 — independent holonomic tracking QP

9 September 2026. Implements the control stage of
[masterplan v2.0](../GP_Attainability_Masterplan_TR.md), retaining all three v0
policies and the default geometric filter. See the
[development validation report](../reports/m1_results_2026-09-09.md) for measured
results and preserved failures. This document records M1's control scope; timed
B3 planning was subsequently added in [M2](M2_PLANNING.md). P and SOGP remain pending.

## Model and constraints

For each control interval, the applied model is `p(t+s) = p(t) + s*u`,
`0 <= s <= dt`. A centralized QP minimizes `0.5 * ||u - u_nom||^2`:

- Each robot's velocity lies in a regular inscribed 16-gon of radius `max_speed`.
  Facet normals at `(2*k+1)*pi/N` use upper bound `max_speed*cos(pi/N)`.
  This is conservative relative to the Euclidean speed ball, not an exact ball QP.
- Endpoints remain within the rectangular domain. Convexity also contains each
  straight segment.
- For every pair, `r = p_i-p_j`, `h = ||r||^2-d_safe^2` and
  `2*r.T*(u_i-u_j) + alpha*h >= 0` impose the nominal current-state CBF condition.
- Additionally, `n.T*(r + dt*(u_i-u_j)) >= d_safe`, `n=r/||r||`, imposes a
  conservative separating plane. A safe starting projection and safe endpoint
  projection protect the whole linear interval; the continuous-time CBF sampled
  only at its start is not treated as sufficient by itself.

There are no soft safety constraints or GP performance constraints. The QP is an
independent design, not an audited ECC controller. Its central joint solve is not
claimed to be distributed. USV + QP is rejected until an appropriate USV controller
and motion check are implemented.

The default `drift_strength` perturbs the requested holonomic tracking velocity,
which is speed-capped **before** the constraint controller. Preview uses no future
unknown perturbations or dropouts. No guarantee covers unknown post-control wind,
hydrodynamics, obstacles or physical robots. The unchanged USV filter retains its
sampled kinematic, bounded-yaw interpretation.

## Numerical acceptance and failure

OSQP receives a positive-definite identity Hessian and linear two-sided constraints.
The pinned environment uses OSQP 1.1.3; the declared dependency requires >=1.1.0.
Default solver settings are `eps_abs=1e-8`, `eps_rel=0`, `max_iter=10000`, fixed
25-iteration termination/rho-update intervals, no warm start and no polishing.
The effective options are recorded in every QP event's `solver_settings`.
[OSQP Python interface](https://osqp.org/docs/interfaces/python.html).

Solved/solved-inaccurate status alone is insufficient. Independent checks cover
finite solution shape, linear feasibility, stationarity, dual sign and normalized
complementarity, Euclidean speed, domain and exact minimum pair separation over
the applied segment. Default acceptance tolerance is `1e-7`; residuals have their
respective numerical/physical units, not a common physical safety margin.
[OSQP status definitions](https://osqp.org/docs/interfaces/status_values.html).

The first four-robot pilot exposed a solver relative-termination tolerance wider
than our absolute postcheck. Setting `eps_rel=0` tightened solving; the acceptance
tolerance was not relaxed. That initial failed bundle is retained in the report.

A rejected command is never propagated, clipped into acceptance or replaced by a
hidden hold/backtracking command. The run ends at the last actually reached state.
A preview failure aborts the current M1 policy run; M4 candidate recovery is not yet
implemented. Solver failure does not establish that the mission target is impossible.

## Logs and timing

- `run.controls`: every attempted preview/execution control, phase, interval end
  time, input state, requested/applied velocity, solver status/settings/residuals,
  constraint labels, geometry and timings. Rejected commands have no applied velocity.
- `motion.control_event_index`: reference to the executed event; the initial state
  has `null`. This avoids duplicated nested logs and preserves Parquet round trips.
- `status`, `failure`, `completion_time_s`: actual outcome and final recorded time.
  Preview's prospective `failure.time_s` is distinct from `last_executed_time_s`.
- `summary.json` and benchmark rows include outcome, requested duration and metric
  scope. Incomplete RMSE is not ranked as a full-horizon score. Failed missions stay
  in the evidence and failure counts.
- `control_s`: total executed control-call wall time, including rejected attempts;
  median/p95/max are across these calls. No-call quantiles are `null`, not zero.
  `control_preview_s` is already included in `planning_s`; do not add it again.
  `gp_s` covers actual assimilation/prediction and, on failure, final belief
  reconstruction (`failure_reconstruction_gp_s` records that subset separately).

Timings include offline nominal preplanning. The simulation clock does not charge
planner/control wall time, so low measured latency is not a real-time guarantee.
The filter uses a speed ball while QP uses an inscribed polygon; resulting path and
map differences are a controller-development comparison, not proof of policy superiority.

## Run and verify

```powershell
.\.venv\Scripts\python.exe -m attain_sampling simulate --controller qp --scenario combined --robots 4
.\.venv\Scripts\python.exe -m attain_sampling simulate --controller qp --qp-max-iter 1 --duration 10 --no-figures
.\.venv\Scripts\python.exe -m pytest tests/unit/test_qp.py tests/unit/test_mapping_qp.py tests/integration/test_demo.py
.\.venv\Scripts\python.exe scripts/validate_m1.py
```

The deliberately iteration-limited command should save failure evidence and return
exit `4`. The HTTP API returns a saved comparison with `completed_with_failures`
and `failure_count` (HTTP 200 means the request succeeded). `DONE` only certifies
finished artifact serialization. Every output directory is new; old bundles and
the imported diagnostic remain untouched.
