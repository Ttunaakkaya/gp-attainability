# Prediction and recovery: preliminary prior-art check

Status: **preliminary**, 18 September 2026. Input to the interview, not a novelty claim, algorithm selection, or exhaustive survey. Read alongside [the existing literature review](../literature_review.md). Scope: three works/projects; public sources only. No experiments or private papers were accessed.

## Closest overlaps inspected

**Suryan and Tokekar, Learning a Spatial Field in Minimum Time with a Team of Robots.** The inspected v2 formulates a pointwise uncertainty threshold and minimizes travel plus measurement time, including multi-robot makespan. It assumes a squared-exponential GP with known hyperparameters, unit-speed robots, and a common depot for its multi-robot construction. Its discussion explains why fixed-model variance forecasts need sample locations but not sample values, and why updating hyperparameters changes that reasoning. Thus threshold-directed planning, deadline relevance, and multiple robots are established ingredients. This check did not audit the proofs. [Paper v2, Sections II-D and III](https://arxiv.org/html/1909.01895v2)

**Jakkala, Agarwal, O'Kane and Akella, Informative Path Planning with Guaranteed Estimation Uncertainty.** The current arXiv record lists **v3, 26 May 2026**; February v1 alone is insufficient for current comparison. Its formulation targets maximum posterior variance over a finite evaluation set using sensing candidates, coverage maps and routing. Crucially, Appendix C reports an AUV trial that missed the threshold at some evaluation locations; the authors attribute deviations to ocean currents and motion constraints omitted by the TSP planner. Section VII identifies execution uncertainty, model uncertainty and finite-grid coverage as limitations. This is concrete evidence that planned uncertainty success and realized execution success differ, not evidence that our proposed remedy is new. [Version history](https://arxiv.org/abs/2602.05198), [v3, Sections IV/VII and Appendix C](https://arxiv.org/html/2602.05198v3)

**Suenaga et al., Hierarchical Multi-Robot Data Sampling for Environmental State Estimation through Online Gaussian Process (ECC 2025).** The coauthor's public explanation already combines sparse online GP estimation, a higher-level planner, discrete sensing, and local constrained control. It describes deadlock without the planner and eventual decay-rate violations. Therefore adding a planner above a safety/control layer is insufficient differentiation. Access limitation: the web tool returned the coauthor page's indexed contents; direct page opening failed. The complete paper was not inspected, so neither equation-level claims nor absence of a particular recovery mechanism is established. [Coauthor project explanation](https://mhd-hanif.github.io/portfolio/gp-environmental-sampling/)

## Three different claims we must keep separate

The following are logical distinctions for our study, not results established for our implementation:

1. **Prediction for a particular continuation:** given current state, GP model, assumed future sensing/execution and a specified policy, its rollout predicts reaching or missing the threshold. Finding an executable successful plan supplies a conditional success witness. Failure of one plan, heuristic or bounded search does not prove that every admissible plan fails.
2. **Calibrated probability of failure:** a statement such as “70% failure risk” needs an explicit distribution of future disturbances and a named continuation policy. Calibration requires held-out outcome frequencies, alongside discrimination and warning lead time. A deterministic GP covariance rollout does not by itself provide this probability.
3. **Impossibility guarantee:** establishing that no admissible continuation can meet the target requires valid bounds or exhaustive reasoning over the stated feasible set and assumptions. Planner failure and pessimistic heuristics cannot substitute for that argument.

## Interview decisions still needed

- **What causes the initial plan to go wrong?** Choose the first execution disturbance to study: missed sensing, motion/tracking delay, or safety-induced detours. Specify what is observed online versus hidden until later. Model mismatch remains a separate check; the accepted fixed-resource mission contract stays intact.
- **What exactly is the promise?** Fix latent versus observation variance, spatial aggregation (mean/integrated versus maximum), evaluation region/grid, threshold, and deadline. These choices determine what “success” actually means; do not silently substitute one metric for another.
- **What does the warning claim?** Pick the first claim level above. “This continuation is predicted to fail” is materially different from “the mission is impossible.” Decide whether numerical failure probabilities are needed at all.
- **What added value must recovery demonstrate?** Separate warning assessment from intervention benefit. For this project's proposed evaluation, paired continuations from the same state can compare ordinary replanning against additional recovery under matched disturbances and computation accounting. A successful intervention must not automatically make the original warning a false alarm.
- **What counts as enough evidence to integrate?** Define success against a strong ordinary-replanning baseline, useful warning lead time, equal-resource mission success, map-error checks and runtime before moving to the lab benchmark.

No inspected source establishes the proposed project's novelty. A targeted follow-up on execution-aware and event-triggered replanning is still needed once the disturbance and claim level are chosen; broad searches before those choices would obscure the actual comparison.
