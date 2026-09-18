# Execution-Aware GP Attainability for Multi-Robot Environmental Sampling

Research concept for Tolga Tuna Akkaya · 8 September 2026

**Status:** Proposed study. The ECC 2025 reproduction and the proposed controller have not yet been completed. Any accompanying exact-GP diagnostic is independent of the paper.

## Motivation and fit

My background combines mechatronics with implementations of Gaussian-process model predictive control, numerical optimization and model predictive safety filtering. I would like to extend this experience to the interaction between estimation and coordinated robot control.

Suenaga, Hanif, Uto and Hatanaka's ECC 2025 work on hierarchical multi-robot environmental sampling provides a relevant starting point. I plan an independent reproduction after auditing the complete paper, including its objective semantics, sparse-GP updates, high-level planner and low-level constraints. [Publication](https://doi.org/10.23919/ECC65951.2025.11187026)

## Research question

How can a multi-robot sampling controller maintain a meaningful uncertainty reference when missed measurements, tracking limitations or safety interventions alter the execution of its sensing plan?

The proposed contribution is a reference-management mechanism that retains an executable backup sampling plan, evaluates its remaining-horizon uncertainty profile, and explicitly detects when its assumptions no longer hold. A feasible plan value is an upper candidate for the optimum of a minimization problem, not a physical uncertainty floor. A new plan would be accepted only after checking its execution and reference implications.

## Method and scope

The initial setting uses fixed GP hyperparameters, a finite evaluation grid, known robot dynamics and bounded execution deviations. A small exact-GP route-enumeration oracle will distinguish reachable targets from optimistic predictions. The scalable method will use bounded candidate search and keep the planned and executed sample histories separate.

The theoretical target is a conditional finite-horizon uncertainty-reference result supported by an executable backup policy. A nominal rollout only validates a nominal witness: a robust claim requires backup viability and the uncertainty bound to hold for every deviation in the admitted set. Otherwise, the method will explicitly retain nominal status and invalidate the witness when necessary. A recurrence for reference error is insufficient unless its one-step condition can be enforced; derivative-level QP slack must also be converted into a valid per-sample variance contribution. Extension to online sparse GP will account explicitly for approximation and dictionary-update discrepancies. General recursive feasibility, continuous-domain estimation guarantees and arbitrary-failure safety are outside the initial claim.

## Evaluation

Compare the audited source-paper baselines, simple informative sampling, an adaptive-rate heuristic, and the proposed method with and without backup-plan retention. Use identical mission time, nominal sample schedules, dynamics and paired execution disturbances. Report field RMSE, common-grid latent variance, reference exceedance and relaxation, collected measurements, task slack, solver failures, separation and runtime.

Success requires improved reliability of useful references without an unacceptable degradation in mapping quality at equal resources. Lower slack alone is not success. An extension to constrained USV dynamics would test transfer after the main result is established.

## Related work and limits

Guaranteed GP uncertainty thresholds and budgeted informative paths already exist. Jakkala et al. discuss online model adaptation and execution uncertainty as limitations; the intended distinction here is maintaining a reference throughout closed-loop execution. Novelty remains to be established against related and ongoing work. [Related paper](https://arxiv.org/html/2602.05198v3)

Planned outputs are a reproducible implementation, a source-to-code audit, a bounded theoretical result or clearly labelled empirical finding, controlled experiments and a short technical report. No outcome or admission guarantee is assumed.
