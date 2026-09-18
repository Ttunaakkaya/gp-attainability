# FIELDWORK — execution-aware multi-robot GP mapping

An independent, CPU-only simulator for multi-robot environmental mapping with Gaussian
processes. Two to four robots sample a seeded field, update an exact or sparse-online
GP, plan timed sampling locations with Bellman dynamic programming, and move under a
constrained controller. It asks one question: **does a policy that tracks the gap
between plan and execution map better than a strong periodic replanner?**

The design starts from the hierarchy of Suenaga, Hanif, Uto and Hatanaka,
*Hierarchical Multi-Robot Data Sampling for Environmental State Estimation through
Online Gaussian Process*, ECC 2025, pp. 304–311
([doi:10.23919/ECC65951.2025.11187026](https://doi.org/10.23919/ECC65951.2025.11187026)).
It is not a reproduction of that paper: the paper publishes no seeds, ground truth or
exact starting positions. A separate source profile implements its equations for a
qualitative comparison.

All nine milestones of [masterplan v2.0](GP_Attainability_Masterplan_TR.md) are
complete (M0–M8, 18 September 2026).

**Technical note (8 pages, PDF):**
[docs/technical_note/FIELDWORK_technical_note.pdf](docs/technical_note/FIELDWORK_technical_note.pdf)

## Results

The results come from protocols frozen before the runs, 40 unseen tasks per block and
paired bootstrap intervals. Figures: [reports/figures/m8](reports/figures/m8/).

- **No map-error benefit.** The proposed policy P is not measurably better than the
  periodic replanner B3 in field RMSE. The 95% interval includes zero in all 10
  blocks: five scenarios × a holonomic and a turn-constrained vehicle.
- **Effects on the belief and on execution.** On a forward-only USV with a 4.44 m
  turning radius, P's controller rollout changes its decisions in every task. P
  samples about 2 m closer to its commanded cells under drift and ends with lower
  variance. The map error does not follow.
- **Cost, and the strongest baseline.** P plans 4.5–50 times longer than B3. The
  simple adaptive greedy planner B2 is the strongest method overall.
- **No early warning.** Forecasts of a fixed uncertainty target separate hits from
  misses only in the last few epochs. They turn optimistic whenever measurements are
  lost, because every forecast assumes each sample arrives.
- **A defect caught and fixed.** A first USV study appeared to favour P. The raw
  records traced this to a defect in the comparator's planner. It is reported as run,
  fixed, and re-tested on new tasks: the apparent advantage disappeared.

Detailed milestone reports are in Turkish: [M6](reports/m6_results_2026-09-17.md) and
[M7](reports/m7_results_2026-09-17.md). Design documents and this README are in English.

## Quick start (Windows, PowerShell)

```powershell
.\scripts\bootstrap.ps1                        # creates .venv from the locked dependencies
.\scripts\check.ps1                            # Ruff, format, strict Mypy, tests with coverage
.\.venv\Scripts\python.exe scripts\make_showcases.py   # four recorded showcases, about 5 min
.\scripts\demo.ps1                             # dashboard at http://127.0.0.1:8765
```

With uv installed: `uv sync --locked --extra dev --extra oracle`.

The dashboard runs locally and binds only to loopback. It shows:

- **Guided showcases.** Four recorded missions: the nominal loop, a plan update under
  loss and drift, the USV turn limit, and a case without a gain. Each card names the
  held-out result that carries its claim.
- **Side by side.** B3 and P replayed together on the same world.
- **Plain-language decisions.** Why P kept or replaced its plan, and the fixed mission
  target against P's forecast.
- **Maps.** Four layers: true field, GP estimate, uncertainty and error.
- **Controller evidence.** QP solves, arc-filter loiter holds and failures.

Walkthrough: [docs/DEMO.md](docs/DEMO.md).

Command line (every run writes a new folder under `outputs/`):

```powershell
# Five methods on the holonomic robots with the velocity QP
.\.venv\Scripts\python.exe -m attain_sampling simulate --methods sweep,greedy,adaptive,dp,p --controller qp --scenario combined --robots 4
# The turn-constrained USV (motion-primitive planners, certified arc filter)
.\.venv\Scripts\python.exe -m attain_sampling simulate --model usv_curvature --methods sweep,greedy,adaptive,dp,p --robots 4
# The ECC 2025 source profile (qualitative comparison)
.\.venv\Scripts\python.exe -m attain_sampling ecc-profile --seed 7
```

Exit code `4` means at least one mission failed; failed runs are saved with their real
prefix, never dropped.

## What comes from the paper, and what is independent

| Part | ECC 2025 source profile (`ecc-profile`) | Independent simulator (`simulate`, demo, M6/M7) |
|---|---|---|
| Belief | The paper's SOGP (β/ω acceptance, η pruning) | Exact GP reference; bounded Csató–Opper SOGP |
| Performance constraint | Variance-decay-rate row inside the QP | None; performance and safety are kept separate |
| Planner | Cell MDP with the paper's Bellman recursion | B0–B2 baselines; timed Bellman DP (B3); P |
| Control | Per-robot QP with a collision barrier | Central OSQP velocity QP; USV arc filter |
| Claim | Qualitative comparison only | Frozen, held-out statistical comparison |

Values the paper does not state are recorded as project choices and never inferred
([equation map](docs/equation_map.md), [M5 alignment](docs/M5_SOURCE_ALIGNMENT.md)). The
licensed PDF lives in the gitignored `references/private/` and is never committed.

## Methods compared

| Code | Method | In one line |
|---|---|---|
| B0 | Sweep | Fixed lawnmower coverage |
| B1 | Nominal greedy | Variance-reduction targets planned once, executed open loop |
| B2 | Adaptive greedy | One-step targets re-planned every epoch from the actual posterior and positions |
| B3 | Periodic DP | Timed Bellman DP over 9 × 7 cells (motion primitives on the USV), re-planned every epoch |
| P | Execution-aware | B3 plus controller rollout, plan retention, event triggers and equal remaining budget |

## Reproduce the evidence

| Milestone | Command | Evidence | Report |
|---|---|---|---|
| M6 holonomic, held-out | `python scripts/run_m6.py` | `outputs/m6-20260916/heldout/…609588` | [M6](reports/m6_results_2026-09-17.md) |
| M7 v2 USV, held-out | `python scripts/run_m6.py --milestone m7v2` | `outputs/m7v2-20260917/heldout/…7f95f2` | [M7](reports/m7_results_2026-09-17.md) |
| Analysis of any batch | `python scripts/report_m6.py <batch>` | recomputes every metric from raw records | |
| M8 figures and note | `python scripts/figures_m8.py`, `python scripts/build_note.py` | [reports/figures/m8](reports/figures/m8/) (hash manifest) | [note](docs/technical_note/FIELDWORK_technical_note.pdf) |
| M8 video | `python scripts/make_video.py` | `outputs/m8/FIELDWORK_m8_demo.mp4` | |

Protocols are frozen YAML files pinned by SHA-256 ([configs/independent](configs/independent/)).
Every design decision and its reason is in the [decision log](docs/decision_log.md). The
artifact contract is in [REPRODUCIBILITY.md](REPRODUCIBILITY.md).

## Repository map

- `src/attain_sampling/gp/`: exact GP and the sparse online GP.
- `src/attain_sampling/planning/`: timed Bellman DP, motion-primitive DP, sampling clock and the ECC cell MDP.
- `src/attain_sampling/attainability/`: P, meaning budget, rollout and the plan manager.
- `src/attain_sampling/control/`: the M1 QP and the ECC per-robot QP.
- `src/attain_sampling/sim/`: field, policies, dynamics, the USV model and the ECC profile.
- `src/attain_sampling/eval/`: the frozen M6/M7 protocols and their analysis.
- `src/attain_sampling/demo/`: paired runner, loopback server, dashboard and renderer.
- `scripts/`: held-out runner and report, validators, showcase, figure, note and video builders.
- `docs/`: design notes M1–M7, source ledgers, decision log, [continuation note](docs/CONTINUE_HERE.md) (Turkish).
- `reports/`: measured results per milestone. `outputs/`: generated evidence, not versioned.

## Evidence boundaries

- **Simulation only.** A kinematic simulator with one family of synthetic fields. There
  is no hydrodynamics, current or hardware. Safety statements are audits inside the
  model, not certificates.
- **Variance is not error.** Lower posterior variance does not imply lower field error.
  A target defined on variance cannot certify a map when the GP model is wrong.
- **Demo seeds are not evidence.** Showcases and demo runs use development seeds (7, 19,
  31). Only the frozen held-out studies carry claims.
- **Timings.** Wall-clock times come from a shared machine: ratios are comparable,
  absolute values are not.

Authored code is MIT licensed; third-party material keeps its original rights.
