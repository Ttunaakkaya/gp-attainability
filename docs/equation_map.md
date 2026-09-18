# ECC 2025 equation map

Status: **audited 15 September 2026** from the full text.

Anchor: Suenaga, Hanif, Uto and Hatanaka, *Hierarchical Multi-Robot Data Sampling for
Environmental State Estimation through Online Gaussian Process*, 2025 23rd European
Control Conference (ECC), Thessaloniki, 24–27 June 2025, pp. 304–311,
doi:10.23919/ECC65951.2025.11187026. Local copy recorded as S01 in
[source_manifest.md](source_manifest.md).

This is the `ecc2025` profile's equation ledger, part of M5 in the
[active masterplan v2.0](../GP_Attainability_Masterplan_TR.md). Every row below was read
directly from the paper at the cited page. Rows marked **not stated** are gaps in the
source itself: they become recorded project choices, never inferred from a neighbouring
value. Independent design choices stay documented separately.

Each `Object` row is claimed by one or more ledger topics in
`attain_sampling.sources.ecc2025`; a test asserts the eighteen rows are covered exactly.
See the [M5 protocol](M5_SOURCE_ALIGNMENT.md).

Symbols follow the paper: `σ_ε` sensor-noise std, `γ` performance level, `ω` SOGP
novelty threshold, `β` novelty, `η` removal score, `ρ` DP discount, `κ` nominal feedback
gain, `ε_opt` QP weight, `α_J`/`α_ca` extended class-K functions.

| Paper eq./page | Object | Semantics and units | Clock | Code object | Required test | Status |
|---|---|---|---|---|---|---|
| eq. (2), p. 305 | Robot dynamics | Single integrator `ṗ_i = u_i`; `u_i ∈ U ⊆ R²`, m/s. Input set `U` **not stated** numerically | control | `sim.dynamics` | propagation and units | audited; `U` is a project choice |
| eq. (3), p. 306 | Field/observation | `y_i(t_l) = f(p_i(t_l)) + ε(t_l)`, `ε ~ N(0, σ_ε²)`, sampled every `t_s`; `f` in an RKHS over polygonal `F ⊂ R²` | sample | `fields.*` | indexed noise | audited |
| Thm. 1, p. 307 | Kernel/prior | RBF `k(x,x') = exp(−‖x−x'‖²/(2L²))`; **no signal-variance prefactor**, so `k(x,x) = 1`. Zero prior mean | GP update | `gp.kernels` | PSD and diagonal | audited |
| eq. (4), p. 306 | SOGP mean | `μ(x) = a_lᵀ k_{x,l}`, field units; `k_{x,l}` over the BV set `Z[l]`, `N[l] = |Z[l]|` | GP update | `gp.sogp` | exact replay | audited |
| eq. (4), p. 306 | SOGP variance | `σ²(x) = k(x,x) + k_{x,l}ᵀ C_l k_{x,l}` — **latent**: no `σ_ε²` term is added | GP/update | `gp.sogp` | variance branch | audited |
| p. 305 | Basis admission | Novelty `β_{τ+1} = k(x_{τ+1},x_{τ+1}) − k_{x_{τ+1},τ}ᵀ Q_τ k_{x_{τ+1},τ}`; admit iff `β_{τ+1} ≥ ω`, else project. **Label-free** | GP update | `gp.sogp` | label scenario | audited |
| p. 305 | Basis pruning | At capacity `n_d,max`, remove `argmin_i η_i`, `η_i = |[a_{τ+1}]_i| / [Q_{τ+1}]_ii`; `a` depends on observations, so pruning is **label-dependent** | GP update | `gp.sogp` | prune replay | audited |
| p. 306 | Global objective | `J = Σ_{x∈F_d} σ²(x)` — **unnormalized sum** over `m = |F_d|` evenly distributed points; field-units² | control/sample | `control.objective` | direct grid sum | audited |
| p. 306, eq. (7) p. 307 | Local decomposition | Voronoi `V_i(p)`; `J̃_l(t) = Σ_i I_il(t)`, `I_il(t) = Σ_{x∈F_d∩V_i} σ̃_l²(x; Z̃_t[l])`. Approximated by `Ĩ_il` using `Z̃_ti[l] = Z[l] ∪ p_i(t)` only, assuming robot `i`'s contribution outside `V_i` is negligible | control | `planning.partition` | local-to-global sum | audited; approximation is the paper's own |
| eqs. (5)–(7), pp. 306–307 | Desired rate | Global `J[l] ≤ J[0] − lγ`; continuous `J̃_l(t) ≤ J[0] − γt/t_s`; per-robot `Ĩ_il(t) ≤ I_i0 − γt/(n t_s)`. `γ > 0` in field-units² per sample. Paper states meeting (5) for all `l` is **infeasible**; only the transient is targeted | control | `control.rate_constraint` | analytic row | audited |
| eqs. (10)–(11), p. 307 | QP objective | `(u_i,w_i) = argmin ε_opt‖u_i‖² + |w_i|²` over `U × R` (constraint-only); hierarchical form uses `‖u_i − u_nom,i‖²`, eq. (17), p. 309 | control | `control.distributed_qp` | centralized oracle | audited |
| eq. (8) p. 307, eqs. (12)–(13) p. 308 | Task slack | Constraint `ḣ_Ji + α_J(h_Ji) ≥ w_i` with `h_Ji = I_i0 − γt/(n t_s) − Ĩ_il(t)`; reduces to **`ξ_i1ᵀ u_i + ξ_i2 ≥ w_i`** (eq. (11); note `≥`). `α_J` names both the class-K function and its gain. `ξ_i2 = −γ/(n t_s) − α_J(Ĩ_il + γt/(n t_s) − I_i0)`. `w_i` is one slack per robot in the derivative row's units | control | `control.rate_constraint` | finite-difference check against eq. (15) | audited; see reading note below |
| eq. (9), p. 307 | Collision CBF | `h_ca,ij = ‖p_i − p_j‖² − d_ca²`, `ḣ_ca,ij + α_ca(h_ca,ij) ≥ 0`; `α_ca` **not stated** (form and gain) | control | `control.cbf` | head-on/sample-data | audited; `α_ca` is a project choice |
| eq. (2), p. 305 | Input/boundary | Only `u_i ∈ U ⊆ R²`; no speed bound, workspace-containment constraint or input limit is **stated** numerically | control | `control.cbf` | saturation/boundary | audited; bounds are project choices |
| p. 308 | MDP state/action | `(B_i, A_i, T_i, R_i)`; cells `C_1..C_nc` partition `F`, `n_c < m`; `B_i[l] = {b | x_c,b ∈ V_i(p(t_l))}`; `A_i = {a_bb'}` inter-cell transitions; deterministic `T_i(b,a_bb',b') = 1` | planning | `planning.cell_mdp` | tiny exhaustive DP | audited |
| p. 308 (rep.), p. 309 (reward) | MDP reward | `R_i(b,a_bb') = σ²_c,b' / ‖x_c,b' − x_c,b‖`, where `σ²_c,b = Σ_{x∈C_b,d} σ²(x)/|C_b,d|` (**mean**) and `x_c,b` is the cell centroid, `C_b,d = F_d ∩ C_b` | planning | `planning.cell_mdp` | numeric fixture | audited |
| eq. (16) p. 309, Alg. 1 p. 310 | Planning/replanning | `V_i(b) = max_{a_bb'} [R_i(b,a_bb') + ρ V_i(b')]`, `π_i(b) = argmax`; waypoints popped on arrival within `ε_tol`; path recomputed after each sample at `t_l+1`; nominal `u_nom,i = κ(x_ci − p_i)` | planning | `sim.coordinator` | event order | audited; horizon/termination of (16) **not stated** |
| pp. 306, 310 | Sampling/control clocks | Sampling every `t_s = 10 s`; control is continuous-time in the derivation and a loop in Alg. 1; the control period is **not stated** | multi-rate | `sim.scheduler` | integer-tick order | audited; control period is a project choice |

## Table I parameters (p. 310)

| Symbol | Value | Meaning (page) |
|---|---|---|
| `L` | 4.0 | RBF length scale (Thm. 1, p. 307) |
| `σ_ε` | 0.4 | Sensor-noise standard deviation (eq. (3), p. 306) |
| `ω` | 0.1 | SOGP novelty threshold (p. 305) |
| `ρ` | 0.9 | DP discount rate (eq. (16), p. 309) |
| `ε_opt` | 0.1 | QP input weight (eq. (10), p. 307) |
| `t_s` | 10 s | Sampling period (p. 306) |
| `α_J` | 10⁻⁴ | Linear gain of the class-K function `α_J(h) = γ_J h` (p. 307) |
| `d_ca` | 3.0 m | Minimum inter-robot distance (p. 307) |
| `γ` | 60 | Performance level in (5) (p. 306) |
| `ε_tol` | 3.0 m | Waypoint arrival tolerance (Alg. 1, p. 310) |
| `n_d,max` | 360 | SOGP BV-set capacity (p. 305) |
| `κ` | 15 | Nominal feedback gain (p. 309) |

## Setup stated in the text

- `n = 3` robots (p. 308); field `F = [−60 m, 60 m] × [−60 m, 60 m]` (p. 308).
- `|F_d| = 900` evenly distributed evaluation points (p. 308).
- Planner cells are 10 m × 10 m (p. 310).
- Ground truth `f` is a mixed Gaussian distribution "whose parameters are randomly
  generated over appropriately defined sets" (p. 308).
- Robots start outside the field (p. 310).
- Figure snapshot times: `t = 0, 320, 640, 1000 s` (Fig. 2, p. 308); Fig. 4 covers
  `t ∈ [0, 640] s` (p. 309).
- Implemented in Python with CVXOPT; Intel i7-1260P, 32 GB RAM (p. 310).

## Reading note: equation (12) versus its own derivation

Implementing `ξ_i1` exposed two places where **equation (12) as printed does not agree with
the derivation of (14)–(15) on the same pages**. Both are resolved in favour of the
derivation, because `ξ_i1` is *defined* as the gradient of `Ĩ_il` and eq. (15) states
`dĨ_il/dt = −ξ_i1ᵀ u_i`.

1. **Summation set.** (12) sums over `x* ∈ F_d`, while `I_il`, `Ĩ_il` and the derivation
   all restrict to `F_d ∩ V_i`.
2. **Missing factor.** In (12) the basis term carries only `[z*]_j`. Expanding (14) gives
   `2 [z*]_{N+1} ( k̇(p_i,x*) + Σ_j [z*]_j k̇(p_i,x_j) )`, because only the appended row of
   `k*` and the last row/column of `K̃_tl` depend on `p_i` — so **both** terms carry
   `[z*]_{N+1}`.

Evidence: central finite differences of `Ĩ_il` against `−ξ_i1ᵀu`. The derivation form
agrees to ~1e-10 on every scene tested; the printed grouping departs by a relative 1.1–9.5
on scenes where the missing factor does not cancel. Pinned by
`tests/unit/test_rate_constraint.py`.

This is a reading of the source, not a claim about the paper's results: Theorem 1's
substance and the reported behaviour are unaffected.

## Reading notes found while running the source profile

Implementing the closed loop exposed further places where the text, the algorithm listing
and the figures do not describe the same run. None is resolved by guessing: each is
recorded, and the two open quantitative questions (scale and start) are run both ways.
Figure values below are read approximately off the plots.

1. **Replanning.** The text (p. 309) recomputes the path from `p_i(t_{l+1})` after every
   sample. Algorithm 1 (p. 310) only runs the DP when the waypoint list is empty and
   otherwise pops the next waypoint. The profile follows the text.
2. **Novelty test.** p. 305 describes the `β < ω` discard only for a sample that arrives
   "when the number of samples is already at its maximum". Read literally, every sample
   below capacity is admitted, which divides by a vanishing `β` whenever a robot resamples
   a site. The paper says it uses the SOGP of [22], which tests novelty at every step; the
   profile does the same.
3. **Scale of `J`.** Figs. 3 and 6 (pp. 307, 311) start at `J[0] ≈ 3600`. With
   `|F_d| = 900` (p. 308) and Theorem 1's prefactor-free kernel, `J[0] = 900`. Either
   `k(x,x) ≈ 4` or about 3600 evaluation points produced the figure; the text states
   neither. Both figures also run to 1200 s, while Fig. 2 covers `[0, 1000]` s.
4. **Attainable decay.** In Figs. 3 and 6, `J` follows the `−γ/t_s` line for about the
   first 150 s, a drop of about 57 per epoch. A sample at a site with no nearby data lowers
   `J` by about `k(x,x)² π L² / (A (k(x,x) + σ_ε²))`, with `A` the area per evaluation
   point. For three robots that is about 8 per epoch at `k(x,x) = 1` with 900 points, about
   33 with 3600 points and about 36 at `k(x,x) = 4` with 900 points. None reaches 57 with
   `L = 4` and `t_s = 10 s`.
5. **Start and entry.** p. 310 states that all robots start outside the field, not where.
   At `t = 0`, Figs. 2 and 4a show one robot at the starting square near `(0, 75)` and the
   others above or on the top edge of `F`, at different positions in the two figures. From
   the square, 16–17 m from the nearest evaluation point, eq. (12) with `L = 4 m` gives
   `|ξ_i1| ≈ 4e-8` to `3e-7`. Controller (10) then moves the robot at about 1e-6 to 1e-5 m/s;
   within about 8 m of `F_d` it moves at 0.5–3 m/s. Yet Fig. 2 shows every robot inside
   `F` by `t = 320 s` under (10). The printed values do not explain how the robot at the
   square entered.
6. **Magnitudes.** Fig. 6 ends with `J ≈ 1000` for (11) and `≈ 780` for (17), and
   mean-squared errors of about 150 and nearly 0, from an initial error of about 3900.
   Fig. 4b shows `μ ≈ 0` wherever no data was taken, consistent with a zero prior mean;
   the text does not state it.

## Not stated in the source

These force recorded project choices and bound what a reproduction may claim:

| Item | Consequence |
|---|---|
| Order of simultaneous multi-robot samples within one epoch | Label-dependent pruning can differ; the order is a project choice |
| Random seeds | Numerically identical figures cannot be reproduced |
| Ground-truth mixture parameters and their sampling sets | Same; only qualitative behaviour is comparable |
| Exact initial robot positions ("outside the field") | Same |
| `α_ca` form and gain | Collision-constraint tuning is a project choice |
| Input set `U`, speed/workspace bounds | Motion limits are project choices |
| Control period of the low-level loop | Discretization is a project choice |
| Horizon/termination rule of the Bellman recursion (16) | Planner stopping is a project choice |
| Class-K form for `α_J` beyond linearity, and the `γ_J`/`α_J` naming | Recorded as the table's `α_J = 10⁻⁴` gain |
