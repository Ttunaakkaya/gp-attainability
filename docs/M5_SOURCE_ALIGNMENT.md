# M5 — ECC 2025 source alignment

16 September 2026. Masterplan v2 M5 asks for three things: the anchor paper's equations,
parameters and baselines in a separate `ecc2025` profile; reproduced figures; and a
difference report. The full text was obtained on 15 September through the TUM IEEE Xplore
subscription and audited the same day. The profile, its figures and a pre-declared
validation batch were completed on 16 September.

**This is a qualitative comparison, not a numerical reproduction.** The paper publishes no
random seeds, no ground-truth parameters and no exact initial positions, so its curves
cannot be matched number for number. No run calls itself an ECC reproduction, and a
repository-wide test enforces that.

Anchor: Suenaga, Hanif, Uto and Hatanaka, *Hierarchical Multi-Robot Data Sampling for
Environmental State Estimation through Online Gaussian Process*, ECC 2025, pp. 304–311,
[doi:10.23919/ECC65951.2025.11187026](https://doi.org/10.23919/ECC65951.2025.11187026).
The licensed PDF is recorded as S01 in [source_manifest.md](source_manifest.md). It lives in
the gitignored private reference directory and is never committed or redistributed.

## What M5 delivers

| Deliverable | Where |
|---|---|
| Equation and parameter record, with page citations | [equation_map.md](equation_map.md), `sources/ecc2025.py` (`ECC2025_AUDIT`, `ECC2025_PARAMETERS`) |
| Paper SOGP (β/ω admission, η pruning), checked against a literal transcription | `gp/sogp.py`, `tests/unit/test_sogp_ecc2025.py` |
| Decay-rate row, eqs. (8), (11)–(13), (15); objective `J`; Voronoi split | `control/rate_constraint.py` |
| Per-robot QP (10)/(11)/(17) with the collision CBF (9) | `control/ecc_qp.py` |
| Cell MDP and Bellman recursion (16) | `planning/cell_mdp.py` |
| Closed-loop profile: E0 constraint-only (10), E1 hierarchical (17) + Algorithm 1 | `sim/ecc2025.py`, `ecc-profile` command |
| Figures of the kind in Figs. 2, 3, 4 and 6 | `sim/ecc2025_figures.py`, `scripts/figures_m5.py` |
| Pre-declared qualitative criteria and audits | `scripts/validate_m5.py` |
| Difference report | `difference_report()`, `doctor --source-report`, this document |

Every piece is checked against the paper's own equations: eq. (15) by finite differences,
the cached row against the reference implementation, (16) against discounted enumeration,
and the SOGP against a literal transcription of p. 305. Each validation run then
recomputes `J` independently from its recorded samples.

## The nine audit topics

Each mirrors one question in [paper_audit.md](paper_audit.md) and claims the
[equation_map.md](equation_map.md) rows it closes. A test asserts that the three records
cannot drift apart and that the ledger covers all eighteen equation rows exactly. All
nine are **verified** from page/equation citations; the third column lists what each one
still bounds because the paper itself does not state it.

| ID | Closes | Source gap bounds |
|---|---|---|
| T01 | Objective variance semantics | objective semantics, figure reproduction |
| T02 | Field integral form and normalization | objective semantics |
| T03 | Csató–Opper equations, admission score | SOGP equivalence |
| T04 | Pruning label dependence, sample order | SOGP equivalence, forecast semantics |
| T05 | Desired-decay inequality, slack convention | performance constraint, slack comparison |
| T06 | Safety CBF, dynamics, input/workspace bounds | controller reproduction |
| T07 | Objective partition and centralized information | distributed claim |
| T08 | MDP state/action/reward/horizon/trigger | planner reproduction |
| T09 | Numerical parameters, field, seeds, snapshots | figure reproduction, parameter lock |

A topic unlocks only from a page and equation number read in the full text, recorded here
and in the decision log; the `AuditTopic` dataclass refuses a verified topic without a
citation. Settings the text does not state are **project choices**, never inferred from a
neighbouring value, and every run lists them in `project_choices`.

## Difference report

### Where the paper disagrees with itself

Found while implementing the profile. The ledger carries them as `SOURCE_INCONSISTENCIES`
(R01–R06); [equation_map.md](equation_map.md) gives the reading notes in full.

| ID | Finding | Handling |
|---|---|---|
| R01 | Printed eq. (12) omits the `[z*]_{N+1}` factor and the `∩V_i` restriction of its own derivation | Derivation implemented; finite differences reject the printed grouping (D037) |
| R02 | Text and Fig. 5 replan after every sample; Algorithm 1 only on an empty route | Text followed (D041) |
| R03 | The `β < ω` discard is described only at capacity | Novelty tested at every step, as in the cited SOGP (D041) |
| R04 | 900 points with `k(x,x) = 1` give `J[0] = 900`; Figs. 3 and 6 start near 3600 | `k = 1` primary, `k = 4` recorded sensitivity (D042) |
| R05 | The figures follow `γ = 60` for about 150 s (~57 per epoch); an isolated sample allows ~8 (`k = 1`) or ~36 (`k = 4`) per epoch for three robots | Reported; `γ` kept at the printed value (D042) |
| R06 | From the starting square, (10) moves a robot at 1e-6–1e-5 m/s, yet Fig. 2 has all robots inside `F` by 320 s | Square start primary, edge start recorded sensitivity (D043) |

### Where the source profile differs from the independent profile

These are real differences, not errors on either side:

- `J` is an **unnormalized sum** over 900 points; the independent profile uses a weighted
  **mean** latent variance.
- The paper's RBF has **no signal-variance prefactor**, so `k(x,x) = 1`.
- The paper's field is `[−60, 60]²` m with `t_s = 10 s`; the independent development
  profile uses 60 × 40 m with `t_s = 5 s`.
- The paper states that its decay constraint is **infeasible for all `l`** and targets only
  the transient. That is the attainability question M4 measures, stated by the source.
- The paper solves its QPs with CVXOPT (interior point); the source profile uses Clarabel,
  also interior point (D039, D040). The independent M1 controller keeps OSQP.

### Project choices the paper leaves open

Ground truth (a 40-bump Gaussian mixture fixed before any controller ran), the 30 × 30
cell-centred evaluation grid, initial positions, Euler `dt = 0.1 s`, the first sample at
`t_1 = t_s`, robot-index assimilation order, linear `α_ca` with gain 1, a 2 m/s speed
polygon, no workspace constraint, `I_i0` evaluated at `t = 0`, value iteration with
self-transitions excluded, and a route stopped on its first revisit.

## Validation

`scripts/validate_m5.py` writes eight criteria, each taken from a sentence of the paper,
to `criteria_declared.json` before any run starts. It then runs four configurations × five
paired seeds × two controllers for 1000 s each:

| | Scale | Start | Role |
|---|---|---|---|
| A | `k(x,x) = 1` (Theorem 1) | `(0, 75)`, the figures' starting square | primary |
| B | `k(x,x) = 1` | `(0, 58)`, the top edge of `F` | E0 can reach `F` (R06) |
| C | `k(x,x) = 4` (Figs. 3 and 6) | `(0, 75)` | figure scale (R04) |
| D | `k(x,x) = 4` | `(0, 58)` | both |

Batch `11099e`: 40 runs, none failed. For every run, `J` recomputed from the recorded
samples matches the recorded value exactly, and the two controllers' noise innovations
agree to 5e-14. Minimum separation is 4.44 m and maximum speed 2.000 m/s. Full tables
and figures are in [M5 results](../reports/m5_results_2026-09-15.md).

| Criterion (paper page) | A | B | C | D |
|---|---|---|---|---|
| C1 an E0 robot stalls (p. 308) | 0/5 | 0/5 | 0/5 | 0/5 |
| C2 E0 violates (5) by `l = 5` (p. 308) | 5/5 | 5/5 | 5/5 | 5/5 |
| C3 both meet (5) at `l = 1` (p. 310) | 0/5 | 0/5 | 0/5 | 0/5 |
| C4 both end violating with `J > 0` (p. 310) | 5/5 | 5/5 | 5/5 | 5/5 |
| C5 final `J(E0) > J(E1)` (p. 310) | 5/5 | 0/5 | 5/5 | 0/5 |
| C6 final MSE(E0) > MSE(E1) (p. 310) | 5/5 | 2/5 | 5/5 | 0/5 |
| C7 MSE(E1) ≤ 5 % of initial (p. 310) | 0/5 | 0/5 | 5/5 | 2/5 |
| C8 E1 covers more, no E1 stall (p. 309) | 5/5 | 0/5 | 5/5 | 0/5 |

What the batch shows:

- **Paths do not depend on the measurements.** With at most 300 samples against
  `n_d,max = 360`, nothing that moves a robot reads a label. Within a configuration the
  five seeds therefore give identical paths and `J`, and only the field (hence MSE)
  changes. C1–C5 and C8 are one outcome repeated five times; a test pins this.
- **The paper's ranking appears only where E0 never enters `F`** (A, C: E0 moves at most
  4e-6 m/s). That is a missing gradient outside `F`, not the in-field stall the paper
  describes.
- **From the edge, E0 does better** (B, D): lower final `J` (349 vs 401, 1189 vs 1399),
  less of `F_d` left uncovered, and E1 has the lower MSE in only 2 of 10 seeds. No E0
  robot meets the pre-declared stall test.
- **Post-hoc observation, not counted:** in D, all E0 robots stay at `y ≤ 22` for the last
  360 s, leaving the top of `F` at mean variance 1.95 against 0.77 at the bottom. That
  resembles Fig. 2, but the pre-declared path-length test does not capture it.
- **E1 runs at the speed bound** 86–88 % of the time, so its samples are about 19 m (≈ 5L)
  apart. That may explain its sparser coverage; this is untested, and `U` is a project
  choice.
- **The initial tracking of (5) is not reproduced** (C3 0/20), as R05 predicts.
- **At figure scale the magnitudes are close to Fig. 6** (C/E1 `J` 3600 → 1260 and MSE
  65–122; D/E0 `J` 1189). This is not a match claim.

## What stays out of scope

The independent profile is unaffected and complete through M4. Its results are never
presented as the paper's results, and its `scope` records say so on every run. The
reserved `reproduce`/`compare`/`figures` commands belong to the M6–M8 research gates and
stay locked; the source profile has its own `ecc-profile` command.

M5 does not block M6, M7 or M8: the masterplan runs those on the independent profile.

## Limits

- Qualitative only. Without the paper's seeds, ground truth and initial positions, a
  matching or non-matching curve says nothing about the paper's exact numbers.
- The barrier row is evaluated at the start of each 0.1 s interval, so it is not a
  sampled-data safety certificate; separation is re-checked on the executed trajectory.
- Five seeds per configuration is a development sample, not a statistical test.
- Figure values quoted from the paper are read approximately off the plots.
