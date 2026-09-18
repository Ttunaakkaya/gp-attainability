# Literature review and implementation consequences

Last audited: 2026-09-01. This is a technical decision record, not a claim that every
adjacent paper has been exhaustively surveyed. Source-access classes and hashes are in
`source_manifest.md`.

Retained as implementation background under the
[active masterplan v2.0](../GP_Attainability_Masterplan_TR.md). This is not an instruction
to restart a broad literature survey or prove a new theorem. Earlier research-gap language
below records hypotheses, not current completion criteria or an established novelty claim.

## Anchor system: Suenaga et al. (ECC 2025)

The publicly available [author project explanation](https://mhd-hanif.github.io/portfolio/gp-environmental-sampling/)
describes three robots in a 120 m by 120 m environment, a 10 s sampling interval, a
central online sparse GP, local Voronoi/QP control with a collision barrier, and a
coarse MDP that trades uncertainty against travel distance. The reported qualitative
failure is that both the constraint-only and hierarchical controllers eventually fail
to maintain the requested decay rate.

The complete ECC text was not accessible through the routes checked in that audit. Therefore
the public explanation is evidence for architecture and qualitative targets only. It is
not evidence for equation signs, variance semantics, dictionary policy, barrier form,
QP weights, or numerical reproduction values. Only paper-specific implementation and
reproduction claims stay locked on that source audit. Independent primary-source SOGP,
own MDP/Bellman-DP and QP designs are active development work; document their choices
without representing them as ECC equations.

## Exact Gaussian-process semantics

[Gaussian Processes for Machine Learning, Chapter 2](https://gaussianprocess.org/gpml/chapters/RW2.pdf)
fixes the main contract:

\[
\Sigma_f(Q\mid X)=K_{QQ}-K_{QX}(K_{XX}+R)^{-1}K_{XQ},
\qquad
\Sigma_y(Q\mid X)=\Sigma_f(Q\mid X)+R_Q.
\]

The latent covariance is independent of observed labels for fixed inputs, kernel
hyperparameters, and noise. A joint fantasy update for future sample inputs \(S\) is

\[
\Sigma^+_{QQ}=\Sigma_{QQ}-\Sigma_{QS}
(\Sigma_{SS}+R_S)^{-1}\Sigma_{SQ}.
\]

Consequences:

- `latent` and `predictive` variance must be requested explicitly;
- fixed-hyperparameter exact covariance rollout is label-free;
- simultaneous robot samples must be conditioned jointly, because adding independent
  one-step gains can double-count correlated or duplicate measurements;
- repeated noisy samples can drive latent variance toward zero, while observation
  predictive variance approaches the measurement-noise floor;
- linear integrated predictive variance differs from integrated latent variance by a
  fixed noise term only under the corresponding fixed-noise/weight assumptions.

The existing exact backend uses Cholesky solves and diagnostics, never an explicit inverse or
silent clipping of materially negative variance.

## Sparse online GP: Csató and Opper (2002)

The [open full text](https://eprints.soton.ac.uk/259182/1/gp2.pdf) represents the posterior
using a basis-vector dictionary, mean coefficients \(\alpha\), covariance correction
\(C\), and inverse dictionary Gram matrix \(Q\). For a new input, the geometric novelty
is

\[
\gamma(x)=k(x,x)-k_x^\top Qk_x.
\]

The canonical admission decision compares \(\gamma\) with a tolerance and is label-free.
The projection-induced mean-error proxy \(|q|\gamma\), however, is label-dependent. More
importantly, fixed-budget removal uses a score proportional to
\(|\alpha_i|/Q_{ii}\). Thus the removed basis vector depends on observed labels.

Consequences:

- a pruning-enabled future SOGP trajectory is not a deterministic label-free covariance
  rollout, even with fixed kernel hyperparameters;
- a future SOGP forecast must declare its approximation: exact-GP surrogate, conditional
  frozen-dictionary forecast, or another explicit approximate/scenario forecast; it is
  not automatically an exact label-free or certified bound;
- the actual SOGP/surrogate difference, pruning index, order sensitivity, and positive
  variance jumps must be logged as discrepancy terms;
- simultaneous sparse updates use a deterministic `(sample_tick, robot_id)` order and
  order sensitivity is measured separately.

## Information objectives and guarantees

[Krause, Singh, and Guestrin (2008)](https://www.jmlr.org/papers/v9/krause08a.html)
prove submodularity for a complement mutual-information objective under stated noise,
discretization, and approximate-monotonicity conditions. Their result is not a guarantee
for weighted integrated posterior variance (Bayesian A-optimality); the paper gives a
counterexample to general A-optimality submodularity. It also does not turn a
path-constrained greedy route into a \(1-1/e\) approximation.

Consequences:

- integrated-variance gains may be computed exactly for a proposed set, but greedy
  selection is a heuristic unless a separate theorem is proved;
- only an exhaustive tiny set/route oracle is accepted as an exact optimum in tests;
- an executable rollout produces an achievable upper candidate for a minimization
  objective, not a global lower bound;
- a relaxed lower bound must come from a valid relaxation, not from greedy IVAR.

## Closest informative-path-planning work

- [Suryan and Tokekar (2020)](https://arxiv.org/abs/1909.01895) formulate minimum-time
  multi-robot field learning with an uncertainty threshold. Terminal threshold/minimum
  time is therefore prior art.
- [Jakkala and Akella (2024)](https://arxiv.org/abs/2309.07050) optimize continuous paths
  through a variational sparse-GP objective and a soft route penalty; this is not a hard
  online execution or safety certificate.
- [Jakkala et al. (2026)](https://arxiv.org/abs/2602.05198) is the closest uncertainty-
  guaranteed IPP comparison: finite candidate/evaluation sets, route budget, terminal
  maximum latent-variance threshold, and coverage algorithms. Its guarantees are not
  automatically preserved by actual robot dynamics or online model updates.

The earlier research-gap hypothesis was narrow: online hierarchical multi-robot SOGP,
prefix references built from plans executable through the same dynamics/safety layer,
and explicit accounting of task slack, reference drift, and sparse-update discrepancy.
No priority or “first” claim is authorized. The active deliverable is an evaluated
engineering system, with strong replanning baselines and negative findings retained;
formal analysis and proposal writing follow the working results.

## Control and safety boundaries

[Notomista and Egerstedt](https://arxiv.org/abs/1811.02465) already establish task-as-
constraint QPs with slack and distributed coordination structure. Slack itself is not a
novel contribution, and a global GP objective is not automatically separable.

[Wang, Ames, and Egerstedt (2017)](https://doi.org/10.1109/TRO.2017.2659727) provide
multi-robot barrier-certificate constructions. A CBF safety statement remains conditional
on the dynamics model, feasibility, solver accuracy, and enforcement assumptions. A
continuous-time condition does not by itself certify a sampled-data controller.

[Tanaka et al. (2025)](https://doi.org/10.1080/18824889.2025.2485496) formulate prescribed
dual-function increase through a slackened QP. It is an adjacent convergence-speed
design, not evidence that the GP information-decay request is attainable. Its numerical
discussion reinforces that an aggressive requested rate can cause large controls and
discretization instability.

## Stack decision

The core stays CPU-first and paper-auditable: NumPy/SciPy for GP algebra, CVXPY with OSQP
and Clarabel for optimization, Shapely/NetworkX for geometry/graphs, PyArrow/Zarr/NPZ for
artifacts, and pytest/Hypothesis for oracle and property tests. Scikit-learn is an optional
development oracle. GPflow, TensorFlow, JAX, GPyTorch, and SGP-Tools are not core
dependencies; an external baseline may later live in a separately locked environment.
