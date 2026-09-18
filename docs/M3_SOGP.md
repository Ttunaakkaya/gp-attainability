# M3 — bounded online GP

15 September 2026. Independent implementation, not an ECC2025 reproduction.
The active masterplan and its M0–M8 order are unchanged.

## Source and implementation choices

The algorithm reference is Csató–Opper, *Sparse Online Gaussian Processes*,
[Aston technical report NCRG/2001/014](https://publications.aston.ac.uk/id/eprint/40231/1/NCRG_2001_014.pdf),
corrected 9 October 2002 version. Equations 9, 11, 16, 23–27 and 31 were checked.
The Southampton copy previously inspected is separately recorded in the source
ledger; matching those PDF bytes is not claimed. ECC-specific pruning is unverified.

With basis B, Q = inverse(K_BB), the representation is
`mean(x) = k_x alpha`, `cov(x,z) = k(x,z) + k_x C k_z.T`.
Geometric novelty is `gamma = kxx - k_x Q k_x.T`.
Gaussian likelihood derivatives use current predictive variance v:
`q = (y - mean(x))/v`, `r = -1/v`.
Admitted points extend the basis; otherwise the update projects onto its span.
Overflow removes the first minimum of `abs(alpha_i)/Q_ii`, using equation 25's
projection downdate. This is not last-N truncation or a KL-removal variant.

Project settings: fixed isotropic RBF, zero prior mean, unchanged physical noise;
relative novelty threshold defaults to `1e-6 * signal_variance`, capacity to 64.
The core permits finite relative thresholds in `[1e-12,1)`; simulator capacities
are bounded to 1–512, with 32/64/128 exposed as demo candidates. Numerical sensor
conditioning adds `1e-10 * signal_variance`, matching ExactGP. The prior dictionary
Gram matrix is not regularized with sensor noise. Small negative variance within
`1e-8 * signal_variance` is roundoff-clipped; material violations raise errors.

The persistent numeric posterior arrays scale with dictionary size squared, not
the observation count. `state_nbytes` excludes Python objects, event logs, batch
scratch arrays and planner workspace; it is not process peak RAM. A transactional
batch temporarily copies the bounded state. Full audit events belong to the run,
not an ever-growing training history hidden in the GP model.

## Actual observations and planning

All policies assimilate received values in ascending `(sample_tick, robot_id)`
order. Projected observations still affect the posterior. Equal-time ordering is
deterministic, not asserted to be statistically invariant. Pruning depends on y;
changing labels can change future covariance through the selected dictionary.

B2 adaptive greedy and B3 timed DP query the current real posterior. Future joint
conditioning freezes that approximate posterior: no imaginary labels are passed
through SOGP admission/pruning. The forecast includes all nominal future receipts,
so it is not exact SOGP evolution, a physical attainability bound, or an RMSE promise.
DP records `gp_backend`, `forecast_scope` and `belief_telemetry` per plan.

B0 sweep and B1 nominal greedy retain their existing full-mission open-loop design
using a fixed exact-prior covariance surrogate for both estimators. Their real
measurements use the selected backend. This explicit route-design surrogate keeps
the baselines unchanged and avoids zero-valued hypothetical SOGP pruning. B0/B1
forecast gaps therefore have a different reference history from B2/B3 gaps.

Default backend remains exact to preserve old commands and reference results.
Choosing SOGP applies to every real belief within that comparison; it is not a
policy-specific advantage. Same-data replay isolates estimator error, whereas
closed-loop comparisons also include estimator-induced route changes.

## Evidence contract

- `samples.assimilated` separates successful model updates from sensor receipt.
- `frames.gp_telemetry` is the state at that replay time, never the final dictionary.
- `run.gp_telemetry` records final count/capacity, admissions, projections, removals
  and numeric state bytes. Exact records use null dictionary fields.
- `gp_updates` records zero-based observation index, robot/tick, geometric novelty,
  update kind, removed observation/site/score and dictionary size. Per-removal
  variance jump is measured at the removed site immediately before/after pruning;
  it is not a whole-grid error bound. The full stream remains in the run artifact.
- Rejected update batches retain received-but-unassimilated samples and the last
  committed belief, with explicit partial mission failure. They are not restarted
  with an exact GP or silently padded to mission end.

Runtime measures distinguish online update/map prediction from planning. ExactGP
factorization is lazy, so replay timing must include its first prediction after
each update. Source hashes, raw observations and both posterior outputs accompany
validation; negative accuracy/runtime outcomes must remain in the report.

## Run

```powershell
.\.venv\Scripts\python.exe -m attain_sampling simulate --gp-backend sogp --sogp-max-basis 64 --methods sweep,greedy,adaptive,dp --controller qp --scenario combined --robots 4
.\.venv\Scripts\python.exe scripts/validate_m3.py --replay-only
.\.venv\Scripts\python.exe scripts/validate_m3.py --pilot-only
```

In the offline demo select SOGP, its capacity, QP and optional periodic DP.
The dictionary panel follows the replay cursor. Existing exact bundles still load.
M4 controller rollout, retained-plan checks and remaining-budget recovery are next;
this estimator does not implement the proposed recovery policy P.
